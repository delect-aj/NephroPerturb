"""Native MCP server exposing the six NephroPerturb tools."""
import os

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .core.store import get_store
from .engine.lookup import clean_val, structure_similarity_search, target_mimicry_top
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
    return {"pert_id": comp["pert_id"], "pert_iname": clean_val(comp.get("pert_iname")),
            "inchikey": clean_val(comp.get("inchikey")), "moa": clean_val(comp.get("moa")),
            "clinical_phase": clean_val(comp.get("clinical_phase")),
            "tdiki_prob": None if comp.get("tdiki_prob") is None or comp.get("tdiki_prob") != comp.get("tdiki_prob") else float(comp["tdiki_prob"]),
            "tdiki_tier": clean_val(comp.get("tdiki_tier")),
            "diril_label": None if comp.get("diril_label") is None or comp.get("diril_label") != comp.get("diril_label") else int(comp["diril_label"])}


@mcp.tool()
def nephro_query_pathway_tf(targets: dict[str, float], top_k: int = 20) -> dict:
    """Find compounds matching desired pathway/TF directions, e.g. {"SMAD3": -1}."""
    return score_pathway_tf(targets, top_k=top_k)


@mcp.tool()
def nephro_target_mimicry(symbol: str, top_k: int = 25) -> dict:
    """Compounds whose K-PRL profile mimics the genetic knockdown of a target gene."""
    hits = target_mimicry_top(symbol, top_k=top_k)
    if not hits:
        return {"gene": symbol, "results": [], "note": "no genetic perturbation"}
    return {"gene": symbol, "results": hits}


@mcp.tool()
def nephro_infer_moa(smiles: str | None = None, pert_id: str | None = None,
                     top_k: int = 15) -> dict:
    """Structure-neighbour MoA inference for an unknown molecule."""
    try:
        results = structure_similarity_search(smiles=smiles, pert_id=pert_id, top_k=top_k)
        return {"results": results}
    except (LookupError, ValueError, NotImplementedError) as exc:
        return {"error": str(exc)}


@mcp.tool()
def nephro_list_renal_cases() -> dict:
    """List the built-in kidney disease validation cohorts."""
    import json
    import pandas as pd
    store = get_store()
    con = store.db()
    try:
        frame = pd.read_sql("SELECT * FROM renal_case_studies", con)
    finally:
        con.close()
    return {"cases": json.loads(frame.to_json(orient="records"))}


def create_mcp_asgi_app(path: str = "/mcp"):
    return mcp.streamable_http_app(
        streamable_http_path=path,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


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
