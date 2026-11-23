"""MCP Server end-to-end test: all six tools over Streamable HTTP.

Run on the server with the MCP server up:
    python tests/test_mcp_e2e.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import os
URL = os.environ.get("NEPHRO_MCP_URL", "http://127.0.0.1:8092/mcp")
REQUIRED = {"nephro_query_signature", "nephro_profile_compound",
            "nephro_query_pathway_tf", "nephro_target_mimicry",
            "nephro_infer_moa", "nephro_list_renal_cases",
            "nephro_search_literature", "nephro_search_clinical_trials",
            "nephro_compare_compounds"}


def payload(res):
    content = res.content[0].text if res.content else "{}"
    import json
    return json.loads(content)


async def main():
    try:
        from mcp import ClientSession
    except ImportError:
        from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(URL) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            missing = REQUIRED - names
            assert not missing, f"missing tools: {missing}"
            print(f"[mcp] tools listed: {sorted(names)}")

            checks = [
                ("nephro_query_signature",
                 {"up_genes": ["COL1A1", "FN1", "TGFB1"],
                  "down_genes": ["NPHS1", "PPARA"], "top_k": 3},
                 lambda d: d["results"]),
                ("nephro_profile_compound", {"token": "dexamethasone"},
                 lambda d: "pert_id" in d),
                ("nephro_query_pathway_tf", {"targets": {"SMAD3": -1}, "top_k": 3},
                 lambda d: d["results"]),
                ("nephro_target_mimicry", {"symbol": "TGFBR1", "top_k": 3},
                 lambda d: d["results"]),
                ("nephro_infer_moa", {"pert_id": "BRD-K11433652", "top_k": 3},
                 lambda d: d["results"]),
                ("nephro_list_renal_cases", {}, lambda d: d["cases"]),
                ("nephro_compare_compounds", {"tokens": ["dexamethasone", "losartan"]},
                 lambda d: len(d.get("compounds", [])) == 2),
                ("nephro_search_literature",
                 {"entity": "dexamethasone", "disease_context": "DKD", "include_safety": False, "max_papers": 3},
                 lambda d: "evidence_tier" in d),
                ("nephro_search_clinical_trials",
                 {"compound": "dexamethasone", "condition": "kidney disease", "max_trials": 2},
                 lambda d: "total_count" in d),
            ]
            for name, args, check in checks:
                res = await session.call_tool(name, args)
                assert not res.is_error, f"{name} returned an error: {res.content}"
                data = payload(res)
                assert "error" not in data, f"{name}: {data.get('error')}"
                assert check(data), f"{name}: unexpected payload keys {list(data)[:8]}"
                print(f"[mcp] {name} OK")

            bad = await session.call_tool("nephro_profile_compound",
                                          {"token": "not-a-compound"})
            assert "error" in payload(bad), "error handling failed"
            print("[mcp] error handling OK")
    print("test_mcp_e2e OK")


if __name__ == "__main__":
    asyncio.run(main())
