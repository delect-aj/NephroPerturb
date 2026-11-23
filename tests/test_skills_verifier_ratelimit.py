"""Unit tests for v1.2 Skills, Execution Policy, Citation Verifier, Rate Limiter & Literature."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def test_skills_and_routing():
    from app.skills_loader import list_skills, select_skill

    skills = list_skills()
    assert len(skills) == 6, [s["id"] for s in skills]
    ids = {s["id"] for s in skills}
    expected = {
        "disease-repurposing",
        "toxicity-rescue",
        "target-to-lead",
        "structure-moa-evidence",
        "literature-evidence",
        "compound-compare",
    }
    assert ids == expected, ids

    # Check compact prompt size discipline
    from app.skills_loader import load_skills

    for sid, spec in load_skills().items():
        assert len(spec.instructions) < 2200, f"{sid} too verbose: {len(spec.instructions)} chars"
        assert 1 <= spec.max_steps <= 6, sid
        assert len(spec.allowed_tools) >= 2, sid

    # Routing checks
    s, _ = select_skill("Find reversal drugs for DKD glomeruli case and verify literature")
    assert s and s.id == "disease-repurposing"

    s, _ = select_skill("Is tacrolimus nephrotoxic and are there safer analogs?")
    assert s and s.id == "toxicity-rescue"

    s, _ = select_skill("Which compounds mimic knockdown of TGFBR1?")
    assert s and s.id == "target-to-lead"

    s, _ = select_skill("Find compounds structurally similar to CC(=O)OC1=CC=CC=C1C(=O)O")
    assert s and s.id == "structure-moa-evidence"

    s, _ = select_skill("Compare #1 and #2 head-to-head", session_state={"candidates": [{"pert_iname": "a"}, {"pert_iname": "b"}]})
    assert s and s.id == "compound-compare"

    s, _ = select_skill("Check PubMed literature and clinical trials for dexamethasone")
    assert s and s.id == "literature-evidence"

    s, _ = select_skill("Check papers for #1", session_state={"candidates": [{"pert_iname": "dexamethasone"}]})
    assert s and s.id == "literature-evidence"

    s, _ = select_skill("What is the weather in Tokyo today?")
    assert s is None
    print("  [OK] skills_and_routing")


def test_verifier():
    from app.verifier import EvidencePool, verify_grounded_response

    pool = EvidencePool()
    pool.ingest({
        "results": [
            {"pert_id": "BRD-K11433652", "pert_iname": "dexamethasone", "rtps": 82.45, "tdiki_prob": 0.142},
        ],
        "top_down_genes": [{"symbol": "CCL2", "z": -7.57}],
        "papers": [
            {"pmid": "37762132", "title": "Dexamethasone in 120 patients reduces proteinuria (24 weeks)."}
        ],
        "trials": [
            {"nct_id": "NCT05237388", "title": "Study in kidney disease"}
        ],
    })

    ok_text = (
        "Dexamethasone (`BRD-K11433652`) scored RTPS=82.5 with low T-DIKI prob=0.142 and "
        "downregulated CCL2 by 7.57 [PMID:37762132], studied across 120 patients over 24 weeks [NCT05237388]."
    )
    res_ok = verify_grounded_response(ok_text, pool)
    assert res_ok["verified"] is True, res_ok
    assert res_ok["pmids_cited"] == ["37762132"]
    assert res_ok["ncts_cited"] == ["NCT05237388"]
    assert res_ok["brds_cited"] == ["BRD-K11433652"]

    bad_pmid = verify_grounded_response("Dexamethasone [PMID:99999999] works great.", pool)
    assert bad_pmid["verified"] is False and "99999999" in str(bad_pmid["hard_violations"])

    bad_nct = verify_grounded_response("Trial [NCT99999999] completed.", pool)
    assert bad_nct["verified"] is False and "NCT99999999" in str(bad_nct["hard_violations"])

    bad_brd = verify_grounded_response("Compound BRD-FAKE99999 failed.", pool)
    assert bad_brd["verified"] is False and "BRD-FAKE99999" in str(bad_brd["hard_violations"])

    bad_nums = verify_grounded_response("Dexamethasone achieved RTPS=99.45 and probability 0.876.", pool)
    assert bad_nums["verified"] is False, bad_nums
    print("  [OK] verifier")


def test_rate_limiter():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["NEPHRO_STATE_DIR"] = tmp
        os.environ["AGENT_LLM_HOURLY_LIMIT_PER_IP"] = "2"
        os.environ["AGENT_LLM_DAILY_GLOBAL_LIMIT"] = "5"
        from app.rate_limit import check_llm_quota, record_llm_usage

        q0 = check_llm_quota("203.0.113.10")
        assert q0["allowed"] is True and q0["remaining_hourly"] == 2

        record_llm_usage("203.0.113.10")
        record_llm_usage("203.0.113.10")
        q1 = check_llm_quota("203.0.113.10")
        assert q1["allowed"] is False and q1["remaining_hourly"] == 0, q1

        # Different IP still has hourly quota
        q_other = check_llm_quota("203.0.113.11")
        assert q_other["allowed"] is True
    print("  [OK] rate_limiter")


def test_literature_fallback_and_cache():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["NEPHRO_STATE_DIR"] = tmp
        from app.engine import literature

        literature.reset_circuit_breakers()
        epmc_sample = {
            "hitCount": 12,
            "resultList": {
                "result": [
                    {
                        "pmid": "11122233",
                        "title": "Randomized clinical trial of drug X in diabetic kidney disease",
                        "journalTitle": "Kidney Int",
                        "pubYear": "2024",
                        "authorString": "Doe J",
                        "citedByCount": 42,
                        "pubTypeList": {"pubType": ["Clinical Trial"]},
                        "abstractText": "<p>Patients treated in a randomized placebo-controlled phase 2 study showed improved albuminuria.</p>",
                    }
                ]
            },
        }
        with mock.patch.object(literature, "_http_get", return_value=json.dumps(epmc_sample).encode()):
            res1 = literature.search_kidney_literature("drugx", disease_context="DKD", include_safety=False)
            assert res1["provider"] == "europepmc"
            assert res1["evidence_tier"] == "Clinical"
            assert res1["cached"] is False
            assert res1["papers"][0]["pmid"] == "11122233"

        # Second call MUST hit SQLite cache without calling network
        with mock.patch.object(literature, "_http_get", side_effect=AssertionError("Should hit cache")):
            res2 = literature.search_kidney_literature("drugx", disease_context="DKD", include_safety=False)
            assert res2["cached"] is True
            assert res2["papers"][0]["pmid"] == "11122233"

        # Verify fallback to PubMed if Europe PMC times out
        literature.reset_circuit_breakers()
        esearch = json.dumps({"esearchresult": {"count": "1", "idlist": ["55566677"]}}).encode()
        efetch = b"""<?xml version="1.0"?>
        <PubmedArticleSet><PubmedArticle><MedlineCitation>
          <PMID>55566677</PMID>
          <Article>
            <Journal><ISOAbbreviation>JASN</ISOAbbreviation><JournalIssue><PubDate><Year>2023</Year></PubDate></JournalIssue></Journal>
            <ArticleTitle>Drug Y attenuates renal fibrosis in UUO mice.</ArticleTitle>
            <Abstract><AbstractText>Mouse unilateral ureteral obstruction model.</AbstractText></Abstract>
            <AuthorList><Author><LastName>Smith</LastName><Initials>A</Initials></Author></AuthorList>
            <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
          </Article>
        </MedlineCitation></PubmedArticle></PubmedArticleSet>"""

        def fake_http(url, timeout=8.0):
            if "ebi.ac.uk" in url:
                raise TimeoutError("timed out")
            if "esearch" in url:
                return esearch
            return efetch

        with mock.patch.object(literature, "_http_get", side_effect=fake_http):
            res_fb = literature.search_kidney_literature("drugy", disease_context="CKD", include_safety=False)
            assert res_fb["provider"] == "pubmed", res_fb
            assert res_fb["evidence_tier"] == "Preclinical", res_fb
            assert res_fb["papers"][0]["pmid"] == "55566677"
    print("  [OK] literature_fallback_and_cache")


def main():
    test_skills_and_routing()
    test_verifier()
    test_rate_limiter()
    test_literature_fallback_and_cache()
    print("test_skills_verifier_ratelimit OK")


if __name__ == "__main__":
    main()
