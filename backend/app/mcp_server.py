"""Native MCP server exposing the six NephroPerturb tools."""
import os

from mcp.server.mcpserver import MCPServer

from .core.store import get_store
from .engine.scoring import score_pathway_tf, score_signature

mcp = MCPServer(
    "NephroPerturb",
    description="Kidney-context drug perturbation knowledge base with nephrotoxicity guardrails",
    version="1.0.0",
)


@mcp.tool()
def nephro_query_signature(up_genes: list[str], down_genes: list[str],
                           context: str = "kprl", gene_tier: str = "all",
                           kidney_compartment: str | None = None,
                           top_k: int = 25) -> dict:
    """Reverse a kidney disease signature against 21,299 compounds (RTPS ranked)."""
    return score_signature(up_genes, down_genes, context=context, gene_tier=gene_tier,
                           compartment=kidney_compartment, top_k=top_k)


@mcp.tool()
def nephro_profile_compound(token: str) -> dict:
    """Full kidney profile of a compound (name, BRD id, InChIKey or SMILES)."""
    store = get_store()
    comp = store.find_compound(token)
    if comp is None:
        return {"error": "compound not found"}
    return {"pert_id": comp["pert_id"], "pert_iname": comp.get("pert_iname"),
            "inchikey": comp.get("inchikey"), "moa": comp.get("moa"),
            "clinical_phase": comp.get("clinical_phase"),
            "tdiki_prob": None if comp.get("tdiki_prob") is None else float(comp["tdiki_prob"]),
            "tdiki_tier": comp.get("tdiki_tier"),
            "diril_label": None if comp.get("diril_label") is None else int(comp["diril_label"])}


@mcp.tool()
def nephro_query_pathway_tf(targets: dict[str, float], top_k: int = 20) -> dict:
    """Find compounds matching desired pathway/TF directions, e.g. {"SMAD3": -1}."""
    return score_pathway_tf(targets, top_k=top_k)


@mcp.tool()
def nephro_target_mimicry(symbol: str, top_k: int = 25) -> dict:
    """Compounds whose K-PRL profile mimics the genetic knockdown of a target gene."""
    import numpy as np
    store = get_store()
    genetic = store.genetic_index_map()
    ko = genetic[genetic["pert_iname"].fillna("").str.upper() == symbol.upper()]
    if ko.empty:
        return {"gene": symbol, "results": [], "note": "no genetic perturbation"}
    gen_mat = np.load(store.store / "matrices" / "genetic_consensus.npy", mmap_mode="r")
    ko_vec = np.mean([np.asarray(gen_mat[int(r)]) for r in ko["matrix_row_idx"][:3]], axis=0)
    kprl = store.matrix("kprl")
    sims = []
    for start in range(0, kprl.shape[0], 4000):
        block = np.asarray(kprl[start:start + 4000])
        sims.append(block @ ko_vec / (np.linalg.norm(block, axis=1)
                                      * (np.linalg.norm(ko_vec) + 1e-9) + 1e-9))
    sims = np.concatenate(sims)
    idx = np.argsort(-sims)[:top_k]
    return {"gene": symbol,
            "results": [{"pert_id": store.cp_index["pert_id"].iloc[i],
                         "pert_iname": store.cp_index["pert_iname"].iloc[i],
                         "similarity": float(sims[i])} for i in idx]}


@mcp.tool()
def nephro_infer_moa(smiles: str | None = None, pert_id: str | None = None,
                     top_k: int = 15) -> dict:
    """Structure-neighbour MoA inference for an unknown molecule."""
    import numpy as np
    from rdkit import Chem
    from rdkit.Chem import rdFingerprintGenerator
    store = get_store()
    if pert_id:
        comp = store.find_compound(pert_id)
        if comp is None:
            return {"error": "compound not found"}
        fps = np.load(store.store / "chem" / "ecfp4_cp.npy", mmap_mode="r")
        query = np.asarray(fps[int(comp["matrix_row_idx"])], dtype=np.float32)
    elif smiles:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"error": "invalid SMILES"}
        gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
        query = (np.frombuffer(gen.GetFingerprint(mol).ToBitString().encode(),
                               dtype=np.uint8) - ord("0")).astype(np.float32)
    else:
        return {"error": "provide smiles or pert_id"}
    fps = np.load(store.store / "chem" / "ecfp4_cp.npy", mmap_mode="r")
    hits = []
    for start in range(0, fps.shape[0], 4000):
        block = np.asarray(fps[start:start + 4000], dtype=np.float32)
        inter = block @ query
        union = block.sum(axis=1) + query.sum() - inter
        tani = inter / np.maximum(union, 1)
        idx = np.argsort(-tani)[:top_k]
        hits.extend((float(tani[i]), start + int(i)) for i in idx)
    hits = sorted(hits, reverse=True)[:top_k]
    results = []
    for score, idx in hits:
        pid = store.cp_index["pert_id"].iloc[idx]
        row = store.compounds.loc[pid]
        if hasattr(row, "ndim") and row.ndim > 1:
            row = row.iloc[0]
        results.append({"pert_id": pid, "pert_iname": row.get("pert_iname"),
                        "tanimoto": score, "moa": row.get("moa")})
    return {"results": results}


@mcp.tool()
def nephro_list_renal_cases() -> dict:
    """List the built-in kidney disease demo signatures."""
    import json
    import pandas as pd
    store = get_store()
    con = store.db()
    try:
        frame = pd.read_sql("SELECT * FROM renal_case_studies", con)
    finally:
        con.close()
    return {"cases": json.loads(frame.to_json(orient="records"))}


def main():
    transport = os.environ.get("NEPHRO_MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http",
                host=os.environ.get("NEPHRO_MCP_HOST", "0.0.0.0"),
                port=int(os.environ.get("NEPHRO_MCP_PORT", "8092")))


if __name__ == "__main__":
    main()
