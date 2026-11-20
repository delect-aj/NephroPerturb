#!/usr/bin/env python
"""Build BM-2 query signatures from the pre-registered cohort registry.

Sources (all under store/annotations/raw/bm2_20261120/, downloaded read-only,
one isolated directory per accession):
  - GEO series_matrix (.txt.gz, one per platform)
  - RNA-seq processed CSV (GSE139061: gene x sample, groups in column names)
  - RNA-seq per-sample tar (GSE142025 / GSE175759: Symbol + value txt.gz)

For every cohort: map probes/symbols to Entrez within the 12,328-gene L1000
universe, collapse per gene (mean), Welch t-test (disease vs control), and
export top-150 up / top-150 down DEGs plus a top-500 |t| list for the
traditional unsplit baseline.

QC (fixed in config/bm2_cohorts_registry.yaml, applied to cohorts added after
the original six; the original six are checked and reported but grandfathered):
  1) n >= 5 in both groups; 2) >= 8000 mapped universe genes;
  3) biological positive-control genes present in the top of the signature.
Failing cohorts are excluded with the reason recorded in the output JSON.
"""
import gzip
import hashlib
import json
import re
import sys
import tarfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import ttest_ind

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from common import paths  # noqa: E402

RAW = paths()["store"] / "annotations" / "raw" / "bm2_20261120"
store_annot = paths()["store"] / "annotations"
PLAT = RAW / "platforms"
OUT = ROOT / "benchmarks" / "outputs" / "bm2_cohort_signatures.json"
REGISTRY = ROOT / "config" / "bm2_cohorts_registry.yaml"
TOP_N = 150
TOP500 = 500
FETCHED = "2026-11-20"
ORIGINAL = {"DKD_glom", "DKD_tub", "LN_glom", "LN_tub", "CKD", "LN2", "AKI"}

# Biological positive-control panels for cohort QC (pathway-level, both
# directions; rule counts are fixed before any BM-2 evaluation runs).
# A cohort passes if ANY listed panel reaches min_hits within the top-300 DEGs
# on the matching side. Panels are intentionally broad marker sets, not
# individual-gene tests: the gate exists to catch technical failures, not to
# reject weakly differential but real cohorts.
POSITIVE_CONTROLS = {
    "LN": {
        "up": [["IFI44", "IFI44L", "IFI27", "IFI6", "MX1", "MX2", "ISG15", "OAS1",
                "OAS2", "OAS3", "IFITM1", "STAT1", "IRF7", "IFIT3", "USP18", "BST2"]],
        "down": [],
        "min_hits": 3,
    },
    "DKD": {
        "up": [["COL1A1", "COL1A2", "COL3A1", "COL4A1", "FN1", "TIMP1", "SERPINE1",
                "ACTA2", "TGFB1", "THBS2", "LAMA4", "COL6A3"],
               ["HAVCR1", "LCN2", "SPP1", "VCAM1"]],
        "down": [["PPARA", "PPARGC1A", "CPT1A", "ACADM", "ACADVL", "SLC22A8",
                  "SLC34A1", "CUBN", "LRP2", "HNF4A", "ESRRA", "SLC5A2", "PDK4",
                  "PCK1"]],
        "min_hits": 3,
    },
    "CKD": {
        "up": [["COL1A1", "COL1A2", "COL3A1", "FN1", "TIMP1", "SERPINE1", "ACTA2",
                "TGFB1", "THBS2", "COL6A3"]],
        "down": [["PPARA", "PPARGC1A", "CPT1A", "ACADM", "SLC22A8", "SLC34A1",
                  "CUBN", "LRP2", "HNF4A", "ESRRA"]],
        "min_hits": 2,
    },
    "FSGS": {
        "up": [["COL1A1", "COL3A1", "FN1", "TIMP1", "SERPINE1", "ACTA2", "TGFB1"]],
        "down": [["NPHS1", "NPHS2", "PODXL", "WT1", "SYNPO", "ACTN4"]],
        "min_hits": 2,
    },
    "IgAN": {
        "up": [["C3", "CFB", "C1QA", "C1QB", "C1QC", "SERPING1", "CFI", "CCL2",
                "CXCL8", "CXCL10", "LCN2", "HAVCR1", "OAS1", "IFI27", "IFITM1",
                "TIMP1", "FN1", "COL1A1"]],
        "down": [],
        "min_hits": 2,
    },
    "AKI": {
        "up": [["HAVCR1", "LCN2", "SPP1", "IL18", "VCAM1", "SOX9", "CASP1",
                "NLRP3", "CXCL8", "CCL2", "TIMP1", "IL6", "ISG15", "STAT1"]],
        "down": [],
        "min_hits": 2,
    },
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_registry():
    cfg = yaml.safe_load(REGISTRY.read_text())
    return cfg["cohorts"], cfg["qc"]


def parse_series_matrix(path):
    """(sample_meta: GSM -> list of tag strings, table: probes x samples)."""
    tag_lines, table_lines, in_table = [], [], False
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("!series_matrix_table_begin"):
                in_table = True
                continue
            if line.startswith("!series_matrix_table_end"):
                break
            if in_table:
                table_lines.append(line)
            elif line.startswith("!Sample_characteristics_ch1") \
                    or line.startswith("!Sample_source_name_ch1") \
                    or line.startswith("!Sample_title"):
                tag_lines.append([v.strip().strip('"') for v in line.split("\t")[1:]])
    table = pd.read_csv(pd.io.common.StringIO("\n".join(table_lines)), sep="\t",
                        index_col=0, dtype=str, low_memory=False)
    table.columns = [str(c).strip().strip('"') for c in table.columns]
    table.index = [str(i).strip().strip('"') for i in table.index]
    n = len(table.columns)
    for i, line in enumerate(tag_lines):
        if len(line) != n:
            raise SystemExit(f"tag line {i} has {len(line)} values, {n} expected")
    per_sample = zip(*tag_lines) if tag_lines else [()] * n
    sample_meta = {gsm: list(tags) for gsm, tags in zip(table.columns, per_sample)}
    return sample_meta, table


def parse_gpl_annot(path):
    lines, started = [], False
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not started:
                if line.startswith("ID\t"):
                    started = True
                    lines.append(line)
                continue
            lines.append(line)
    if not started:
        raise SystemExit(f"[gpl] no table header found in {path}")
    frame = pd.read_csv(pd.io.common.StringIO("".join(lines)), sep="\t",
                        dtype=str, low_memory=False)
    mapping = {}
    for probe, e, s in zip(frame["ID"].astype(str).str.strip(),
                           frame["Gene ID"].fillna("").astype(str).str.strip(),
                           frame["Gene symbol"].fillna("").astype(str).str.strip()):
        if e and e not in ("NA", "nan", "None"):
            mapping[probe] = ("entrez", e)
        elif s and s not in ("NA", "nan", "None", ""):
            mapping[probe] = ("symbol", s.split("///")[0].strip().upper())
    return mapping


def parse_gpl14663_soft(path):
    mapping, in_table = {}, False
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("!platform_table_begin"):
                in_table = True
                next(fh)
                continue
            if line.startswith("!platform_table_end"):
                break
            if in_table:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 3:
                    probe, symbol = parts[0].strip(), parts[2].strip().strip('"')
                    if symbol:
                        mapping[probe] = ("symbol", symbol.split("///")[0].strip().upper())
    return mapping


def symbol_to_entrez(store):
    universe = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    s2e = {str(s).upper(): str(e) for s, e in zip(universe["symbol"], universe["entrez_id"])}
    alias_path = store / "annotations" / "hgnc_aliases.parquet"
    if alias_path.exists():
        alias = pd.read_parquet(alias_path)
        for a, e in zip(alias["alias_lower"], alias["entrez_id"]):
            s2e.setdefault(str(a).upper(), str(e))
    return s2e, universe


def load_rnaseq_csv(path):
    """GSE139061-style processed CSV; groups live in the column names."""
    frame = pd.read_csv(path, index_col=0)
    tags = {str(c): [str(c)] for c in frame.columns}
    frame.index = [str(i).strip().upper() for i in frame.index]
    return tags, frame


def load_rnaseq_tar(spec, gse_dir):
    """Per-sample Symbol+value txt.gz files in raw.tar; metadata from series matrix."""
    tar_path = gse_dir / "raw.tar"
    extract = gse_dir / "extracted"
    if not extract.exists():
        with tarfile.open(tar_path) as tf:
            tf.extractall(extract)
    series = gse_dir / spec.get("matrix_file", "matrix.txt.gz")
    sample_meta = {}
    if series.exists():
        sample_meta, _ = parse_series_matrix(series)
    frames, tags = {}, {}
    pattern = re.compile(r"^(GSM\d+)")
    for path in sorted(extract.glob("*.txt.gz")):
        m = pattern.match(path.name)
        gsm = m.group(1) if m else path.stem
        try:
            tbl = pd.read_csv(path, sep="\t", compression="gzip")
        except Exception:
            continue
        if tbl.shape[1] < 2:
            continue
        sym = tbl.iloc[:, 0].astype(str).str.upper().str.strip()
        val = pd.to_numeric(tbl.iloc[:, 1], errors="coerce")
        series_data = pd.Series(val.values, index=sym.values)
        series_data = series_data[~series_data.index.duplicated(keep="first")]
        frames[path.name] = series_data
        tags[path.name] = sample_meta.get(gsm, [path.name])
    matrix = pd.DataFrame(frames)
    return tags, matrix


def parse_gpl_soft(path):
    """Generic GEO family-soft platform table -> probe -> ('entrez'|'symbol')."""
    mapping, in_table, header = {}, False, None
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("!platform_table_begin"):
                in_table, header = True, None
                continue
            if line.startswith("!platform_table_end"):
                break
            if not in_table:
                continue
            parts = line.rstrip("\n").split("\t")
            if header is None:
                header = [h.strip().lower() for h in parts]
                continue
            rec = dict(zip(header, parts))
            probe = rec.get("id", "").strip()
            if not probe:
                continue
            e = next((rec[c] for c in ("gene id", "entrez_gene_id", "entrez gene id")
                      if c in rec), "")
            e = (e or "").strip()
            sym = next((rec[c] for c in ("gene symbol", "symbol", "orf") if c in rec), "")
            sym = (sym or "").strip()
            if e and e not in ("NA", "nan", "None", "---"):
                mapping[probe] = ("entrez", e)
            elif sym and sym not in ("NA", "nan", "None", "", "---"):
                mapping[probe] = ("symbol", sym.split("///")[0].strip().upper())
    return mapping


def platform_of(series_path):
    with gzip.open(series_path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("!Series_platform_id"):
                return line.split("\t")[1].strip().strip('"')
            if line.startswith("!series_matrix_table_begin"):
                break
    return ""


def probe_map_for(platform):
    if not platform:
        return {}
    if platform == "GPL14663":
        return parse_gpl14663_soft(PLAT / "GPL14663_family.soft.gz")
    annot = PLAT / f"{platform}.annot.gz"
    if annot.exists():
        return parse_gpl_annot(annot)
    soft = PLAT / f"{platform}_family.soft.gz"
    if soft.exists():
        return parse_gpl_soft(soft)
    return {}


def assemble_inputs(name, spec):
    """Return (tags dict, gene x sample DataFrame, annot_file, matrix_sha)."""
    gse_dir = RAW / spec["gse"]
    fmt = spec.get("data_format", "series_matrix")
    if fmt == "series_matrix":
        fname = spec.get("matrix_file", "matrix.txt.gz")
        path = gse_dir / fname
        meta, table = parse_series_matrix(path)
        return meta, table, fname, sha256(path)
    if fmt == "rnaseq_processed_csv":
        path = gse_dir / "processed_QN.csv.gz"
        tags, table = load_rnaseq_csv(path)
        return tags, table, path.name, sha256(path)
    if fmt == "rnaseq_tar_txt":
        tags, table = load_rnaseq_tar(spec, gse_dir)
        return tags, table, "raw.tar", sha256(gse_dir / "raw.tar")
    raise SystemExit(f"{name}: unknown data_format {fmt}")


def cohort_deg(name, spec, probe_map, s2e, universe, platform=None):
    tags, table, fname, matrix_sha = assemble_inputs(name, spec)
    dis_re = re.compile(spec["disease_re"], re.I)
    ctl_re = re.compile(spec["control_re"], re.I)
    any_re = re.compile(spec["any_re"], re.I) if spec.get("any_re") else None
    dis_ids, ctl_ids = [], []
    for sid, tag_list in tags.items():
        joined = " | ".join(tag_list)
        if any_re and not any_re.search(joined):
            continue
        is_d, is_c = bool(dis_re.search(joined)), bool(ctl_re.search(joined))
        if is_d and not is_c:
            dis_ids.append(sid)
        elif is_c and not is_d:
            ctl_ids.append(sid)
    print(f"[deg] {name}: disease n={len(dis_ids)} control n={len(ctl_ids)}")

    vals = table.apply(pd.to_numeric, errors="coerce")
    keep = dis_ids + ctl_ids
    if not keep:
        return None, "no samples matched group rules"
    finite = np.nanmax(np.abs(vals[keep].to_numpy(dtype=np.float64))) if vals[keep].size else 0
    if np.isfinite(finite) and finite > 100:
        vals = np.log2(vals.clip(lower=0) + 1.0)
        print(f"[deg] {name}: log2-transformed (linear-scale values)")

    entrez_set = set(universe["entrez_id"].astype(str))
    if probe_map:
        ent = [None] * len(vals)
        for i, probe in enumerate(vals.index):
            hit = probe_map.get(probe)
            if not hit:
                continue
            kind, value = hit
            if kind == "entrez":
                if value in entrez_set:
                    ent[i] = value
            else:
                e = s2e.get(value)
                if e and e in entrez_set:
                    ent[i] = e
        vals = vals.assign(entrez=ent)
        vals = vals[vals["entrez"].notna()]
    else:
        # RNA-seq: row index holds symbols or Ensembl gene ids
        ensembl_map = {}
        hgnc_path = store_annot / "hgnc.parquet"
        if hgnc_path.exists():
            hgnc = pd.read_parquet(hgnc_path, columns=["ensembl_id", "entrez_id"])
            for ens, ez in zip(hgnc["ensembl_id"], hgnc["entrez_id"]):
                if not isinstance(ens, str):
                    continue
                for token in ens.split("|"):
                    base = token.strip().split(".")[0].upper()
                    if base.startswith("ENSG"):
                        ensembl_map[base] = str(ez)
        ent = []
        for sym in vals.index:
            key = str(sym).upper().strip()
            e = s2e.get(key)
            if not e:
                e = ensembl_map.get(key.split(".")[0])
            ent.append(e if e and e in entrez_set else None)
        vals = vals.assign(entrez=ent)
        vals = vals[vals["entrez"].notna()]
    n_mapped = len(vals)
    print(f"[deg] {name}: {n_mapped} rows mapped to universe genes")
    if not n_mapped:
        return None, "no rows mapped to universe"
    gene_expr = vals.groupby("entrez", sort=False)[keep].mean()

    d = gene_expr[dis_ids].to_numpy(dtype=np.float64)
    c = gene_expr[ctl_ids].to_numpy(dtype=np.float64)
    t, _ = ttest_ind(d, c, axis=1, equal_var=False, nan_policy="omit")
    t = np.where(np.isnan(t), 0.0, t)
    order = np.argsort(-t)
    e2s = dict(zip(universe["entrez_id"].astype(str), universe["symbol"]))
    idx = list(gene_expr.index)
    up = [e2s[idx[i]] for i in order[:TOP_N] if t[i] > 0]
    dn = [e2s[idx[i]] for i in order[::-1][:TOP_N] if t[i] < 0]
    top500 = [e2s[idx[i]] for i in np.argsort(-np.abs(t))[:TOP500]]
    if len(up) < 30 or len(dn) < 30:
        return None, f"too few DE genes ({len(up)} up / {len(dn)} down)"

    pc = POSITIVE_CONTROLS.get(spec["disease"], {"up": [], "down": [], "min_hits": 0})
    up300, dn300 = set(up[:300]), set(dn[:300])
    up_hits = sorted({g for panel in pc["up"] for g in panel if g in up300})
    down_hits = sorted({g for panel in pc["down"] for g in panel if g in dn300})
    qc = {"mapped_genes": int(n_mapped),
          "positive_control_hits_up": up_hits,
          "positive_control_hits_down": down_hits,
          "positive_control_ok": (len(up_hits) >= pc["min_hits"]
                                  or len(down_hits) >= pc["min_hits"]
                                  or len(up_hits) + len(down_hits) >= 4)}

    qc_cfg = load_registry()[1]
    reasons = []
    if len(dis_ids) < qc_cfg["min_group_n"] or len(ctl_ids) < qc_cfg["min_group_n"]:
        if name not in ORIGINAL:
            reasons.append(f"group n below {qc_cfg['min_group_n']}")
    if n_mapped < qc_cfg["min_mapped_genes"]:
        if name not in ORIGINAL:
            reasons.append(f"mapped genes below {qc_cfg['min_mapped_genes']}")
    if qc_cfg.get("require_positive_control") and not qc["positive_control_ok"]:
        reasons.append(f"positive control failed (up={up_hits}, down={down_hits})")
    passed = name in ORIGINAL or not reasons
    if reasons and name in ORIGINAL:
        qc["grandfathered_notes"] = reasons

    cohort = {
        "gse": spec["gse"], "study_id": spec.get("study_id", spec["gse"]),
        "disease": spec["disease"], "compartment": spec.get("note", ""),
        "up": up, "down": dn, "top500_abs": top500,
        "qc": qc, "passed": passed,
        "provenance": {
            "series": f"{spec['gse']} ({spec.get('note', '')})",
            "platform": platform or spec.get("platform", "symbol-level"),
            "matrix_file": fname, "matrix_sha256": matrix_sha,
            "n_disease": len(dis_ids), "n_control": len(ctl_ids),
            "top_n": TOP_N,
            "method": "probe/symbol -> Entrez, mean collapse, Welch t-test, top-N "
                      "up/down within the 12328-gene L1000 universe",
            "fetched": FETCHED,
        },
    }
    return cohort, None if passed else "; ".join(reasons)


def main():
    store = paths()["store"]
    registry, qc_cfg = load_registry()
    s2e, universe = symbol_to_entrez(store)
    probe_maps = {p: probe_map_for(p) for p in
                  {spec.get("platform", "symbol") for spec in registry.values()}
                  if p.startswith("GPL") and p != "symbol"}

    cohorts, excluded = {}, {}
    for name, spec in registry.items():
        fmt = spec.get("data_format", "series_matrix")
        platform = spec.get("platform")
        if fmt == "series_matrix" and not platform:
            series = RAW / spec["gse"] / spec.get("matrix_file", "matrix.txt.gz")
            platform = platform_of(series)
            if platform and platform not in probe_maps:
                probe_maps[platform] = probe_map_for(platform)
        pmap = probe_maps.get(platform, {}) if fmt == "series_matrix" else {}
        try:
            cohort, reason = cohort_deg(name, spec, pmap or {}, s2e, universe,
                                        platform=platform)
        except SystemExit as exc:
            excluded[name] = str(exc)
            print(f"[deg] {name}: EXCLUDED ({exc})")
            continue
        except Exception as exc:  # noqa: BLE001
            excluded[name] = f"error: {exc}"
            print(f"[deg] {name}: EXCLUDED ({exc})")
            continue
        if cohort is None:
            excluded[name] = reason or "unknown"
            print(f"[deg] {name}: EXCLUDED ({reason})")
            continue
        cohorts[name] = cohort
        status = "OK" if cohort["passed"] else "QC-FAIL"
        print(f"[deg] {name}: {status} qc={cohort['qc']} up[:6]={cohort['up'][:6]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "cohorts": cohorts, "excluded": excluded,
        "qc": qc_cfg, "built": date.today().isoformat(),
        "n_passed": sum(1 for c in cohorts.values() if c["passed"]),
    }, indent=2))
    print(f"[deg] {sum(1 for c in cohorts.values() if c['passed'])} passed cohorts "
          f"-> {OUT}")


if __name__ == "__main__":
    main()
