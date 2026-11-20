#!/usr/bin/env python
"""Attach public clinical nephrotoxicity evidence (SIDER / CTD / FAERS) for
DISPLAY-ONLY warnings. FDA DIRIL remains the sole training/CV label set.

Downloads (isolated directory per source, read-only inputs):
  SIDER 4.1   meddra_all_se.tsv.gz + drug_names.tsv
  CTD         CTD_chemicals_diseases.tsv.gz (filtered to renal injury terms)
  FAERS       openFDA counts per drug name (renal AE vs all AE reports)

Output: store/annotations/clinical_diki_evidence.parquet
        (pert_iname_lower, source, renal_ae_flag, n_renal, n_total, detail)
Each source is optional; failures are recorded, not fatal.
"""
import gzip
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from common import paths  # noqa: E402

STORE = paths()["store"]
RAW = STORE / "annotations" / "raw" / "clinical_diki"
OUT = STORE / "annotations" / "clinical_diki_evidence.parquet"

SIDER_BASE = "http://sideeffects.embl.de/media/download/"
CTD_URL = "http://ctdbase.org/reports/CTD_chemicals_diseases.tsv.gz"
OPENFDA = "https://api.fda.gov/drug/event.json"

RENAL_TERMS = {
    "acute kidney injury", "renal failure", "renal failure acute", "renal impairment",
    "renal tubular necrosis", "nephropathy toxic", "renal tubular disorder",
    "acute renal failure", "kidney failure", "renal injury", "tubulointerstitial nephritis",
    "nephritis interstitial", "blood creatinine increased", "creatinine renal clearance decreased",
    "kidney failure, acute", "acute kidney failure", "renal insufficiency",
}
FAERS_TERMS = ('"acute kidney injury" OR "renal failure" OR "renal impairment" '
               'OR "renal tubular necrosis" OR "nephropathy toxic"')
# MedDRA-ish SIDER side effects are free text; normalize for matching
FAERS_QUERIES = 0


def norm(name):
    return "".join(ch for ch in str(name).lower().strip()
                   if ch.isalnum() or ch in "- ").strip()


def fetch(url, dest, is_gzip=True, timeout=1800):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return True
    try:
        with urllib.request.urlopen(url, timeout=300) as resp:
            dest.write_bytes(resp.read())
        if is_gzip:
            gzip.open(dest).read(16)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[fetch] FAILED {url}: {exc}")
        dest.unlink(missing_ok=True)
        return False


def read_gz_tsv(path, chunksize=None):
    return pd.read_csv(path, sep="\t", compression="gzip", dtype=str,
                       on_bad_lines="skip", chunksize=chunksize)


def load_sider():
    d = RAW / "sider"
    ok_se = fetch(SIDER_BASE + "meddra_all_se.tsv.gz", d / "meddra_all_se.tsv.gz")
    ok_names = fetch(SIDER_BASE + "drug_names.tsv", d / "drug_names.tsv", is_gzip=False)
    if not (ok_se and ok_names):
        return {}
    se = pd.read_csv(d / "meddra_all_se.tsv.gz", sep="\t", dtype=str,
                     names=["stitch1", "stitch2", "umls", "label",
                            "concept_type", "meddra_id"], on_bad_lines="skip")
    terms = se[(se["concept_type"] == "PT")
               & se["label"].str.lower().isin(RENAL_TERMS)]
    print(f"[sider] renal PT rows: {len(terms)}")
    names = pd.read_csv(d / "drug_names.tsv", sep="\t", dtype=str,
                        names=["stitch", "name"], on_bad_lines="skip")
    id2name = {}
    for stitch, name in zip(names["stitch"], names["name"]):
        id2name.setdefault(stitch, set()).add(norm(name))
    out = {}
    for _, row in terms.iterrows():
        for stitch in (row["stitch1"], row["stitch2"]):
            for name in id2name.get(stitch, ()):
                out.setdefault(name, set()).add(row["label"].lower())
    print(f"[sider] names with renal AE: {len(out)}")
    return {k: sorted(v) for k, v in out.items()}


CTD_COLUMNS = ["ChemicalName", "ChemicalID", "CasRN", "DiseaseName", "DiseaseID",
               "DirectEvidence", "InferenceGeneSymbol", "InferenceScore", "OmimIDs",
               "PubMedIDs"]


def load_ctd():
    """Stream the CTD chemical-disease table, keeping renal-injury rows only."""
    d = RAW / "ctd"
    path = d / "CTD_chemicals_diseases.tsv.gz"
    if not fetch(CTD_URL, path):
        return {}
    out = {}
    buf_lines = []
    size = 0
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            buf_lines.append(line)
            size += len(line)
            if size > 64_000_000:
                frame = pd.read_csv(io.StringIO("".join(buf_lines)), sep="\t",
                                    names=CTD_COLUMNS, dtype=str, on_bad_lines="skip",
                                    usecols=[0, 3])
                sub = frame[frame["DiseaseName"].str.lower().isin(RENAL_TERMS)]
                for name, dis in zip(sub["ChemicalName"], sub["DiseaseName"]):
                    out.setdefault(norm(name), set()).add(dis.lower())
                buf_lines, size = [], 0
    print(f"[ctd] names with renal disease associations: {len(out)}")
    return {k: sorted(v) for k, v in out.items()}


def openfda_count(name, search):
    global FAERS_QUERIES
    query = urllib.parse.quote(f'{search} AND patient.drug.openfda.generic_name:"{name}"')
    url = f"{OPENFDA}?search={query}&limit=1"
    for attempt in range(3):
        try:
            time.sleep(0.3)
            FAERS_QUERIES += 1
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read())
            return int(data.get("meta", {}).get("results", {}).get("total", 0))
        except Exception:  # noqa: BLE001
            if attempt == 2:
                return None
            time.sleep(2 + attempt * 2)
    return None


def load_faers(names):
    out = {}
    for i, name in enumerate(sorted(names)):
        renal = openfda_count(name, f"patient.reaction.reactionmeddrapt:({FAERS_TERMS})")
        total = openfda_count(name, "patient.reaction.reactionmeddrapt:*")
        if renal is None or total is None:
            continue
        if renal > 0:
            out[norm(name)] = {"renal_reports": renal, "total_reports": total,
                               "renal_fraction": round(renal / max(total, 1), 5)}
        if i % 50 == 0:
            print(f"  [faers] {i}/{len(names)}", flush=True)
    print(f"[faers] names with renal AE reports: {len(out)} (queries={FAERS_QUERIES})")
    return out


def main():
    store = STORE
    compounds = pd.read_parquet(store / "chem" / "compounds.parquet")
    compounds["name_lower"] = compounds["pert_iname"].fillna("").str.lower().str.strip()
    norm_to_pids = {}
    for name, pid in zip(compounds["name_lower"], compounds["pert_id"]):
        norm_to_pids.setdefault(norm(name), set()).add(pid)

    labels = pd.read_parquet(store / "annotations" / "nephrotoxicity_diril.parquet")
    diril_names = set(compounds[compounds["pert_id"].isin(labels["pert_id"])]["name_lower"])
    tier_a_names = set()
    cfg_path = ROOT / "config" / "bm2_clinical_positives.yaml"
    if cfg_path.exists():
        import yaml
        cfg = yaml.safe_load(cfg_path.read_text())["tier_a"]
        for drugs in cfg.values():
            for d in drugs:
                tier_a_names.add(d["name"].lower())

    sider = load_sider()
    ctd = load_ctd()
    faers_names = {norm(n) for n in diril_names | tier_a_names}
    faers = load_faers(faers_names)

    rows = []
    for source, table in (("sider", sider), ("ctd", ctd), ("faers", faers)):
        for name_norm, evidence in table.items():
            pids = norm_to_pids.get(name_norm)
            if not pids:
                continue
            for pid in pids:
                if source == "faers":
                    detail = json.dumps(evidence)
                    renal, total = evidence["renal_reports"], evidence["total_reports"]
                else:
                    detail = json.dumps(evidence)
                    renal, total = len(evidence), None
                rows.append({"pert_id": pid, "source": source, "renal_ae_flag": 1,
                             "n_renal": renal, "n_total": total, "detail": detail})
    frame = pd.DataFrame(rows)
    frame.to_parquet(OUT, index=False)
    print(f"[done] {len(frame)} evidence rows, {frame['pert_id'].nunique()} compounds "
          f"-> {OUT}")


if __name__ == "__main__":
    main()
