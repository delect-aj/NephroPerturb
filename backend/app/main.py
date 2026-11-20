"""NephroPerturb REST API (OpenAPI 3.1 via FastAPI)."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import route as agent_route, summarize as agent_summarize
from .core.store import get_store
from .engine import tdiki as tdiki_explain
from .engine.scoring import score_pathway_tf, score_signature

app = FastAPI(title="NephroPerturb API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

_DOWNLOADS_DIR = get_store().store / "downloads"
if _DOWNLOADS_DIR.exists():
    app.mount("/downloads", StaticFiles(directory=str(_DOWNLOADS_DIR)), name="downloads")


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
    return {"status": "ok", "compounds": int(len(store.cp_index)),
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
        result = score_pathway_tf(req.targets, top_k=req.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result["job_id"] = persist_job(get_store(), "SOP-3", req.model_dump(), result)
    return result


@app.get("/api/v1/compound/{token}")
def compound_profile(token: str, top_genes: int = 12):
    store = get_store()
    comp = store.find_compound(token)
    if comp is None:
        raise HTTPException(status_code=404, detail="compound not found")
    pid = comp["pert_id"]
    row = int(comp["matrix_row_idx"])
    matrix = store.matrix("kprl")
    profile = np.asarray(matrix[row])
    order = np.argsort(-profile)
    genes = store.genes
    up = [{"symbol": genes["symbol"].iloc[i], "z": float(profile[i])}
          for i in order[:top_genes]]
    dn = [{"symbol": genes["symbol"].iloc[i], "z": float(profile[i])}
          for i in order[::-1][:top_genes]]

    brothers = store.compounds[store.compounds["inchikey14"] == comp.get("inchikey14")]
    targets = []
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
    finally:
        con.close()
    genetic = store.genetic_index_map()
    ko = genetic[genetic["pert_iname"].fillna("").str.upper() == symbol.upper()]
    mimic = []
    if len(ko):
        gen_mat = np.load(store.store / "matrices" / "genetic_consensus.npy", mmap_mode="r")
        kprl = store.matrix("kprl")
        ko_rows = ko["matrix_row_idx"].astype(int).tolist()[:3]
        ko_vec = np.mean([np.asarray(gen_mat[r]) for r in ko_rows], axis=0)
        sims = []
        for start in range(0, kprl.shape[0], 4000):
            block = np.asarray(kprl[start:start + 4000])
            num = block @ ko_vec
            den = np.linalg.norm(block, axis=1) * (np.linalg.norm(ko_vec) + 1e-9)
            sims.append(num / (den + 1e-9))
        sims = np.concatenate(sims)
        idx = np.argsort(-sims)[:top_k]
        mimic = [{"pert_id": store.cp_index["pert_id"].iloc[i],
                  "pert_iname": store.cp_index["pert_iname"].iloc[i],
                  "similarity": float(sims[i])} for i in idx]
    return {"gene": gene.to_dict(), "kidney_expression": expression,
            "targeting_drugs": drugs.to_dict("records"),
            "genetic_perturbations": ko[["pert_id", "pert_type", "n_sigs"]].to_dict("records"),
            "mimicking_compounds": mimic}


@app.post("/api/v1/similarity/structure")
def similarity(req: StructureRequest):
    store = get_store()
    from rdkit import Chem
    from rdkit.Chem import rdFingerprintGenerator
    if req.pert_id:
        comp = store.find_compound(req.pert_id)
        if comp is None:
            raise HTTPException(status_code=404, detail="compound not found")
        fps = np.load(store.store / "chem" / "ecfp4_cp.npy", mmap_mode="r")
        query = np.asarray(fps[store.fp_position[comp["pert_id"]]], dtype=np.float32)
    elif req.smiles:
        mol = Chem.MolFromSmiles(req.smiles)
        if mol is None:
            raise HTTPException(status_code=422, detail="invalid SMILES")
        gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
        query = np.frombuffer(gen.GetFingerprint(mol).ToBitString().encode(),
                              dtype=np.uint8) - ord("0")
        query = query.astype(np.float32)
    else:
        raise HTTPException(status_code=422, detail="provide smiles or pert_id")

    fps = np.load(store.store / "chem" / "ecfp4_cp.npy", mmap_mode="r")
    qsum = query.sum()
    hits = []
    for start in range(0, fps.shape[0], 4000):
        block = np.asarray(fps[start:start + 4000], dtype=np.float32)
        inter = block @ query
        union = block.sum(axis=1) + qsum - inter
        tani = inter / np.maximum(union, 1)
        idx = np.argsort(-tani)[: req.top_k]
        for i in idx:
            hits.append((float(tani[i]), start + int(i)))
    hits = sorted(hits, reverse=True)[: req.top_k]
    pert_ids = store.compounds["pert_id"].to_numpy()
    results = []
    for score, idx in hits:
        pid = pert_ids[idx]
        row = store.compounds.loc[pid]
        if hasattr(row, "ndim") and row.ndim > 1:
            row = row.iloc[0]
        results.append({
            "pert_id": pid,
            "pert_iname": None if pd.isna(row.get("pert_iname")) else row.get("pert_iname"),
            "tanimoto": score,
            "moa": None if pd.isna(row.get("moa")) else row.get("moa"),
            "clinical_phase": None if pd.isna(row.get("clinical_phase")) else row.get("clinical_phase"),
        })
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
