"""NephroPerturb REST API (OpenAPI 3.1 via FastAPI) + optional unified MCP & static UI."""
from contextlib import asynccontextmanager
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.routing import Route

from .agent import route as agent_route, summarize as agent_summarize
from .core.store import get_store
from .engine import tdiki as tdiki_explain
from .engine.lookup import structure_similarity_search, target_mimicry_top
from .engine.scoring import score_pathway_tf, score_signature

_MOUNT_MCP = os.environ.get("NEPHRO_MOUNT_MCP", "0") == "1"
_STATIC_DIR = os.environ.get("NEPHRO_STATIC_DIR", "").strip()
_COMPUTE_LOCK = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _MOUNT_MCP:
        from .mcp_server import mcp
        async with mcp.session_manager.run():
            yield
    else:
        yield


app = FastAPI(title="NephroPerturb API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

_DOWNLOADS_DIR = get_store().store / "downloads"


@app.get("/downloads/{filename}")
def download_file(filename: str):
    base = _DOWNLOADS_DIR.resolve()
    target = (base / filename).resolve()
    if target.parent != base or not target.is_file():
        raise HTTPException(status_code=404, detail="download not found")
    return FileResponse(path=str(target), filename=target.name)

if _MOUNT_MCP:
    from .mcp_server import create_mcp_asgi_app
    _mcp_sub = create_mcp_asgi_app("/mcp")
    for _r in _mcp_sub.routes:
        if getattr(_r, "path", None) == "/mcp":
            app.router.routes.append(_r)
            app.router.routes.append(Route("/mcp/", endpoint=_r.endpoint,
                                           methods=getattr(_r, "methods", None)))


class SignatureRequest(BaseModel):
    up_genes: List[str] = Field(default_factory=list)
    down_genes: List[str] = Field(default_factory=list)
    context: str = "kprl"
    gene_tier: str = "all"
    kidney_compartment: Optional[str] = None
    weights: Dict = Field(default_factory=dict)
    filters: Dict = Field(default_factory=dict)
    top_k: int = 50


class PathwayRequest(BaseModel):
    targets: Dict[str, float]
    top_k: int = 20


class StructureRequest(BaseModel):
    smiles: Optional[str] = None
    pert_id: Optional[str] = None
    top_k: int = 20


class AgentRequest(BaseModel):
    text: str
    use_llm: bool = True


class SummarizeRequest(BaseModel):
    results: Dict
    question: str = ""
    use_llm: bool = True


@app.get("/health")
def health():
    store = get_store()
    return {"status": "ok",
            "mode": "lite" if store.is_lite else "full",
            "mcp_mounted": _MOUNT_MCP,
            "compounds": int(len(store.cp_index)),
            "matrices": ["kprl", "pan", "renal_epi", "renal_endo", "renal_immune"]}


def persist_job(store, sop_id, params, result, llm_used=0):
    job_id = uuid.uuid4().hex
    try:
        con = store.db()
        con.execute(
            "INSERT INTO job_provenance (job_id, created_at, query_modality, sop_id,"
            " params_json, input_hash, result_summary_json, llm_used)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (job_id, datetime.now(timezone.utc).isoformat(), "transcriptome", sop_id,
             json.dumps(params, ensure_ascii=False, default=str),
             result.get("provenance", {}).get("input_hash", ""),
             json.dumps({"n_results": len(result.get("results", []))}), int(llm_used)))
        con.commit()
        con.close()
    except Exception:
        pass
    return job_id


@app.post("/api/v1/query/signature")
def query_signature(req: SignatureRequest):
    try:
        with _COMPUTE_LOCK:
            result = score_signature(req.up_genes, req.down_genes, context=req.context,
                                     gene_tier=req.gene_tier,
                                     compartment=req.kidney_compartment,
                                     weights=req.weights, filters=req.filters,
                                     top_k=req.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result["job_id"] = persist_job(get_store(), "SOP-1", req.model_dump(), result)
    return result


@app.post("/api/v1/query/pathway-tf")
def query_pathway_tf(req: PathwayRequest):
    try:
        with _COMPUTE_LOCK:
            result = score_pathway_tf(req.targets, top_k=req.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result["job_id"] = persist_job(get_store(), "SOP-3", req.model_dump(), result)
    return result


@app.get("/api/v1/compound/{token}")
def compound_profile(token: str, top_genes: int = 12):
    store = get_store()
    comp = store.get_compound_detail(token)
    if comp is None:
        raise HTTPException(status_code=404, detail="compound not found")
    pid = comp["pert_id"]
    row = int(comp["matrix_row_idx"])
    genes = store.genes

    if store.is_lite:
        tg = store.lite_top_genes()
        k = min(int(top_genes), tg["up_idx"].shape[1])
        up = [{"symbol": genes["symbol"].iloc[int(tg["up_idx"][row, j])],
               "z": float(tg["up_z"][row, j])} for j in range(k)]
        dn = [{"symbol": genes["symbol"].iloc[int(tg["dn_idx"][row, j])],
               "z": float(tg["dn_z"][row, j])} for j in range(k)]
    else:
        matrix = store.matrix("kprl")
        profile = np.asarray(matrix[row])
        order = np.argsort(-profile)
        up = [{"symbol": genes["symbol"].iloc[i], "z": float(profile[i])}
              for i in order[:top_genes]]
        dn = [{"symbol": genes["symbol"].iloc[i], "z": float(profile[i])}
              for i in order[::-1][:top_genes]]

    brothers = store.compounds[store.compounds["inchikey14"] == comp.get("inchikey14")]
    con = store.db()
    try:
        targets = pd.read_sql(
            "SELECT target_symbol, entrez_id, moa FROM drug_targets WHERE pert_id = ?",
            con, params=(pid,)).to_dict("records")
    finally:
        con.close()
    expr = store.kidney_expression
    for t in targets:
        key = str(t.get("entrez_id"))
        if key in expr.index:
            t.update({k: (None if pd.isna(v) else float(v))
                      for k, v in expr.loc[key].items()})

    func = {}
    if store.is_lite:
        idx_d = store.lite_active_idx("kprl_delta")
        pos_d = np.searchsorted(idx_d, row)
        if pos_d < len(idx_d) and int(idx_d[pos_d]) == row:
            fblk = store.lite_func_block("kprl_delta")
            f_row = int(pos_d)
        else:
            fblk = store.lite_func_block("pan")
            f_row = row
        for name, prefix in (("progeny", "pw"), ("collectri", "tf"), ("renal_modules", "mod")):
            cols = [f"{prefix}_{c}" for c in fblk[f"{name}_cols"]]
            vals = fblk[f"{name}_raw"][f_row].astype(float)
            s = pd.Series(vals, index=cols)
            func[name] = (s.sort_values(ascending=False).head(10).round(3).to_dict()
                          if name == "renal_modules" else s.round(3).to_dict())
    else:
        for name in ("progeny", "collectri", "renal_modules"):
            frame = store.func_matrix(name)
            if pid in frame.index:
                vals = frame.loc[pid].astype(float)
                func[name] = (vals.sort_values(ascending=False).head(10).round(3)
                              .to_dict()) if name == "renal_modules" else vals.round(3).to_dict()

    return {
        "compound": json.loads(comp.to_frame().T.to_json(orient="records"))[0],
        "scaffold_siblings": brothers["pert_id"].tolist(),
        "top_up_genes": up, "top_down_genes": dn,
        "targets": targets, "functional_activity": func,
        "tdiki": {"prob": float(comp.get("tdiki_prob") or 0),
                  "tier": comp.get("tdiki_tier") or "NA",
                  "struct": None if pd.isna(comp.get("tdiki_struct")) else float(comp.get("tdiki_struct")),
                  "tx": None if pd.isna(comp.get("tdiki_tx")) else float(comp.get("tdiki_tx")),
                  "diril_label": None if pd.isna(comp.get("diril_label")) else int(comp["diril_label"])},
    }


@app.get("/api/v1/compound/{token}/explain")
def compound_explain(token: str, top_n: int = 10):
    store = get_store()
    comp = store.find_compound(token)
    if comp is None:
        raise HTTPException(status_code=404, detail="compound not found")
    try:
        return tdiki_explain.explain(comp["pert_id"], top_n=top_n)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"explanation unavailable: {exc}")


@app.get("/api/v1/target/{symbol}")
def target_profile(symbol: str, top_k: int = 50):
    store = get_store()
    cols, missing = store.resolve_genes([symbol])
    if not cols:
        raise HTTPException(status_code=404, detail="gene not found")
    col = cols[0]
    gene = store.genes.iloc[col]
    expr = store.kidney_expression
    expression = {}
    if str(gene["entrez_id"]) in expr.index:
        expression = {k: (None if pd.isna(v) else float(v))
                      for k, v in expr.loc[str(gene["entrez_id"])].items()}
    con = store.db()
    try:
        drugs = pd.read_sql(
            "SELECT pert_id, target_symbol, moa FROM drug_targets WHERE UPPER(target_symbol)=?",
            con, params=(symbol.upper(),))
        if store.is_lite:
            ko_rows = pd.read_sql(
                "SELECT pert_id, pert_type, n_sigs FROM perturbations_genetic WHERE UPPER(pert_iname)=?",
                con, params=(symbol.upper(),)).to_dict("records")
        else:
            genetic = store.genetic_index_map()
            ko = genetic[genetic["pert_iname"].fillna("").str.upper() == symbol.upper()]
            ko_rows = ko[["pert_id", "pert_type", "n_sigs"]].to_dict("records")
    finally:
        con.close()

    with _COMPUTE_LOCK:
        mimic = target_mimicry_top(symbol, top_k=top_k)
    return {"gene": gene.to_dict(), "kidney_expression": expression,
            "targeting_drugs": drugs.to_dict("records"),
            "genetic_perturbations": ko_rows,
            "mimicking_compounds": mimic}


@app.post("/api/v1/similarity/structure")
def similarity(req: StructureRequest):
    try:
        with _COMPUTE_LOCK:
            results = structure_similarity_search(
                smiles=req.smiles, pert_id=req.pert_id, top_k=req.top_k
            )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return {"results": results}


@app.get("/api/v1/cases")
def list_cases():
    store = get_store()
    con = store.db()
    try:
        frame = pd.read_sql("SELECT * FROM renal_case_studies", con)
    finally:
        con.close()
    return {"cases": json.loads(frame.to_json(orient="records"))}


@app.get("/api/v1/cases/{case_id}")
def get_case(case_id: str):
    store = get_store()
    con = store.db()
    try:
        frame = pd.read_sql("SELECT * FROM renal_case_studies WHERE case_id = ?",
                            con, params=(case_id,))
    finally:
        con.close()
    if frame.empty:
        raise HTTPException(status_code=404, detail="case not found")
    row = frame.iloc[0]
    up = json.loads(row["up_genes_json"])
    down = json.loads(row["down_genes_json"])
    disease_code = row["disease_code"] if "disease_code" in row.index else None
    with _COMPUTE_LOCK:
        result = score_signature(up, down, context="auto",
                                 disease=disease_code,
                                 compartment=row["compartment"], top_k=25)
    result["case"] = json.loads(frame.to_json(orient="records"))[0]
    result["job_id"] = persist_job(get_store(), "SOP-6", {"case_id": case_id}, result)
    return result


@app.post("/api/v1/agent/route")
def api_agent_route(req: AgentRequest):
    return agent_route(req.text, use_llm=req.use_llm)


@app.post("/api/v1/agent/summarize")
def api_agent_summarize(req: SummarizeRequest):
    return agent_summarize(req.results, req.question, use_llm=req.use_llm)


_DOWNLOAD_CACHE = {}


@app.get("/api/v1/downloads")
def downloads():
    store = get_store()
    folder = store.store / "downloads"
    items = []
    for path in sorted(folder.glob("*")):
        if not path.is_file():
            continue
        key = str(path)
        if key not in _DOWNLOAD_CACHE:
            digest = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(chunk)
            _DOWNLOAD_CACHE[key] = digest.hexdigest()
        items.append({"file": path.name, "bytes": path.stat().st_size,
                      "sha256": _DOWNLOAD_CACHE[key],
                      "url": f"/downloads/{path.name}"})
    return {"downloads": items}


if _STATIC_DIR and Path(_STATIC_DIR).is_dir():
    @app.get("/compound/{token}")
    def _redirect_compound(token: str):
        return RedirectResponse(url=f"/compound/?id={token}")

    @app.get("/target/{symbol}")
    def _redirect_target(symbol: str):
        return RedirectResponse(url=f"/target/?symbol={symbol}")

    @app.get("/downloads")
    @app.get("/downloads/")
    def _downloads_page():
        return FileResponse(str(Path(_STATIC_DIR) / "downloads" / "index.html"))

    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static_ui")
