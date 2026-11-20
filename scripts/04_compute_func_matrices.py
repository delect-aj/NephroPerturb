#!/usr/bin/env python
"""Compute PROGENy / CollecTRI / renal-module activities per scoring context,
plus full-library precomputed kidney-expression support and genetic-mimicry
columns used by the runtime RTPS (no Top-60 truncation at request time).

Outputs (per context ctx in kprl/pan/renal_epi/renal_endo/renal_immune):
  matrices/progeny_<ctx>.parquet, collectri_<ctx>.parquet,
  matrices/renal_modules_<ctx>.parquet
  matrices/<name>_cp.parquet        legacy aliases for kprl (old readers)
  matrices/<name>_cp_pvals.parquet  p-values (kprl only)
And:
  matrices/expr_kidney_cp.parquet        21,299 x 10 compartment support
  matrices/genetic_mimicry_cp.parquet    21,299 x (max, mean) KD cosine
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, paths  # noqa: E402

CONTEXTS = {
    "kprl": "kprl_cp_zscore.npy",
    "pan": "pan_cp_zscore.npy",
    "renal_epi": "renal_epi_cp_zscore.npy",
    "renal_endo": "renal_endo_cp_zscore.npy",
    "renal_immune": "renal_immune_cp_zscore.npy",
}
KD_TYPES = {"trt_sh", "trt_sh.cgs", "trt_sh.css", "trt_xpr"}
COMPARTMENTS = {
    "podocyte": ["sc_podocyte"],
    "pt": ["sc_pt"],
    "tal": ["sc_tal"],
    "dct": ["sc_dct"],
    "cd": ["sc_cd"],
    "endo": ["sc_endo"],
    "immune": ["sc_immune"],
    "glomerulus": ["sc_podocyte", "sc_endo"],
    "tubule": ["sc_pt", "sc_tal", "sc_dct", "sc_cd"],
    "whole_kidney": ["hpa_kidney_ntpm"],
}


def load_networks(net_dir):
    import decoupler as dc
    net_dir.mkdir(parents=True, exist_ok=True)
    progeny_path = net_dir / "progeny.csv"
    collectri_path = net_dir / "collectri.csv"
    if progeny_path.exists():
        progeny = pd.read_csv(progeny_path)
    else:
        progeny = dc.get_progeny(organism="human", top=500)
        progeny.to_csv(progeny_path, index=False)
    if collectri_path.exists():
        collectri = pd.read_csv(collectri_path)
    else:
        collectri = dc.get_collectri(organism="human", split_complexes=False)
        collectri.to_csv(collectri_path, index=False)
    return progeny[["source", "target", "weight"]], collectri


def module_net(symbol_to_col, yaml_path):
    with open(yaml_path) as fh:
        modules = yaml.safe_load(fh)["modules"]
    rows = []
    for name, genes in modules.items():
        for gene in genes:
            if gene.upper() in symbol_to_col:
                rows.append({"source": name, "target": gene.upper(), "weight": 1.0})
    net = pd.DataFrame(rows)
    print(f"[modules] {net['source'].nunique()} modules / {len(net)} targets")
    return net


def run_ulm(dc, mat, net, chunk):
    """ULM per chunk; all-zero rows (no signatures in this context) score 0.

    decoupler drops constant columns, so a chunk made only of zero rows would
    raise "No sources with more than min_n"; inactive rows are filled with 0.
    """
    net = net.copy()
    net["target"] = net["target"].astype(str).str.upper()
    col_set = set(mat.columns)
    cols = sorted(src for src, sub in net.groupby("source")
                  if len(set(sub["target"]) & col_set) >= 5)
    acts, pvals = [], []
    for start in range(0, len(mat), chunk):
        block = mat.iloc[start:start + chunk]
        active = (block != 0).any(axis=1).to_numpy()
        arr_a = np.zeros((len(block), len(cols)), dtype=np.float64)
        arr_p = np.ones((len(block), len(cols)), dtype=np.float64)
        if active.any():
            res = dc.run_ulm(mat=block[active], net=net, source="source",
                             target="target", weight="weight", min_n=5,
                             verbose=False)
            arr_a[active] = np.asarray(res[0].reindex(columns=cols).fillna(0.0),
                                       dtype=np.float64)
            arr_p[active] = np.asarray(res[1].reindex(columns=cols).fillna(1.0),
                                       dtype=np.float64)
        acts.append(pd.DataFrame(arr_a, index=block.index, columns=cols))
        pvals.append(pd.DataFrame(arr_p, index=block.index, columns=cols))
        print(f"  ulm: {min(start + chunk, len(mat))}/{len(mat)} "
              f"(active {int(active.sum())})", flush=True)
    return pd.concat(acts), pd.concat(pvals)


def module_activities(matrix, net, pert_ids):
    genes = pd.read_parquet(paths()["store"] / "genes" / "gene_universe.parquet")
    symbol_to_col = {s.upper(): i for i, s in enumerate(genes["symbol"])}
    out = {}
    for source, sub in net.groupby("source"):
        cols = [symbol_to_col[t] for t in sub["target"] if t in symbol_to_col]
        if not cols:
            continue
        w = sub.set_index("target")["weight"]
        w = np.array([w[t] for t in sub["target"] if t in symbol_to_col], dtype=np.float32)
        vals = np.asarray(matrix[:, cols], dtype=np.float32) @ w / np.abs(w).sum()
        out[source] = vals
    return pd.DataFrame(out, index=pert_ids)


def write_wide(mat, path):
    out = mat.astype("float32").fillna(0.0).reset_index(names="pert_id")
    out.to_parquet(path, index=False)
    print(f"[write] {path} {mat.shape}")


def precompute_expr(store):
    """21,299 x 10 mean target-gene compartment support (0..1)."""
    expr = pd.read_parquet(store / "annotations" / "kidney_expression.parquet")
    expr = expr.set_index(expr["entrez_id"].astype(str))
    cp_index = pd.read_parquet(store / "cp_index.parquet")
    targets = pd.read_parquet(store / "annotations" / "drug_targets_hub.parquet")
    compounds = pd.read_parquet(store / "chem" / "compounds.parquet")
    compounds["name_lower"] = compounds["pert_iname"].fillna("").str.lower().str.strip()
    name2pids = compounds.groupby("name_lower")["pert_id"].apply(list).to_dict()

    frames = []
    for name, cols in COMPARTMENTS.items():
        available = [c for c in cols if c in expr.columns]
        if not available:
            continue
        vals = np.log1p(expr[available].fillna(0).clip(lower=0)).mean(axis=1)
        frames.append(pd.Series(np.clip(vals / np.log1p(1000), 0, 1), name=name,
                                index=expr.index.astype(str)))
    support = pd.concat(frames, axis=1)
    edges = []
    for lower, entrez in zip(targets["pert_iname_lower"], targets["entrez_id"]):
        e = str(entrez)
        if e not in support.index:
            continue
        for pid in name2pids.get(lower, []):
            edges.append((pid, e))
    edges = pd.DataFrame(edges, columns=["pert_id", "entrez_id"]).drop_duplicates()
    merged = edges.merge(support.reset_index(names="entrez_id"), on="entrez_id", how="inner")
    table = merged.groupby("pert_id")[list(support.columns)].mean()
    table = table.reindex(cp_index["pert_id"]).fillna(0.0)
    table.index.name = "pert_id"
    write_wide(table, store / "matrices" / "expr_kidney_cp.parquet")


def precompute_mimicry(store):
    """21,299 x (max, mean) cosine to target-gene KD consensus profiles."""
    targets = pd.read_parquet(store / "annotations" / "drug_targets_hub.parquet")
    compounds = pd.read_parquet(store / "chem" / "compounds.parquet")
    compounds["name_lower"] = compounds["pert_iname"].fillna("").str.lower().str.strip()
    name2pids = compounds.groupby("name_lower")["pert_id"].apply(list).to_dict()
    genetic = pd.read_parquet(store / "genetic_index.parquet")
    kd = genetic[genetic["pert_type"].isin(KD_TYPES)]
    by_symbol = {}
    for sym, row in zip(kd["pert_iname"].fillna("").str.upper(), kd["matrix_row_idx"]):
        if sym:
            by_symbol.setdefault(sym, []).append(int(row))
    gen_mat = np.load(store / "matrices" / "genetic_consensus.npy", mmap_mode="r")
    kprl = np.load(store / "matrices" / "kprl_cp_zscore.npy", mmap_mode="r")
    cp_index = pd.read_parquet(store / "cp_index.parquet")
    row_of = dict(zip(cp_index["pert_id"], cp_index["matrix_row_idx"]))

    sym_of_entrez = {}
    genes = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    gmap = dict(zip(genes["entrez_id"].astype(str), genes["symbol"].str.upper()))
    for lower, entrez in zip(targets["pert_iname_lower"], targets["entrez_id"]):
        sym = gmap.get(str(entrez))
        if not sym:
            continue
        for pid in name2pids.get(lower, []):
            sym_of_entrez.setdefault(pid, set()).add(sym)

    maxv = np.zeros(len(cp_index), dtype=np.float32)
    meanv = np.zeros(len(cp_index), dtype=np.float32)
    for i, pid in enumerate(cp_index["pert_id"]):
        syms = sym_of_entrez.get(pid)
        if not syms:
            continue
        rows = [r for s in syms for r in by_symbol.get(s, [])][:8]
        if not rows:
            continue
        z = np.asarray(kprl[int(row_of[pid])], dtype=np.float32)
        zn = np.linalg.norm(z)
        if zn == 0:
            continue
        cors = []
        for r in rows:
            g = np.asarray(gen_mat[r], dtype=np.float32)
            gn = np.linalg.norm(g)
            if gn > 0:
                cors.append(float(z @ g / (zn * gn)))
        if cors:
            maxv[i] = max(cors)
            meanv[i] = float(np.mean(cors))
        if i % 4000 == 0:
            print(f"  mimicry {i}/{len(cp_index)}", flush=True)
    table = pd.DataFrame({"mimicry_max": maxv, "mimicry_mean": meanv},
                         index=cp_index["pert_id"].tolist())
    table.index.name = "pert_id"
    write_wide(table, store / "matrices" / "genetic_mimicry_cp.parquet")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=2000)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--contexts", nargs="+", default=list(CONTEXTS))
    ap.add_argument("--skip-precompute", action="store_true")
    args = ap.parse_args()

    import decoupler as dc
    t0 = time.time()
    store = paths()["store"]
    net_dir = store / "annotations" / "networks"

    genes = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    cp = pd.read_parquet(store / "cp_index.parquet")
    symbols = genes["symbol"].tolist()
    symbol_to_col = {s.upper(): i for i, s in enumerate(symbols)}
    progeny, collectri = load_networks(net_dir)
    modules = module_net(symbol_to_col, ROOT / "config" / "renal_modules.yaml")
    pert_ids = cp["pert_id"].tolist()

    for ctx in args.contexts:
        targets = [store / "matrices" / f"{n}_{ctx}.parquet"
                   for n in ("progeny", "collectri", "renal_modules")]
        if all(t.exists() for t in targets) and not args.force:
            print(f"[skip] {ctx} functional matrices exist")
            continue
        print(f"[ctx] {ctx}: loading matrix")
        matrix = np.load(store / "matrices" / CONTEXTS[ctx], mmap_mode="r")
        mat = pd.DataFrame(np.asarray(matrix), index=pert_ids, columns=symbols)
        for name, net in (("progeny", progeny), ("collectri", collectri)):
            print(f"[run] {ctx}/{name}: {net['source'].nunique()} sources")
            acts, pvals = run_ulm(dc, mat, net, args.chunk)
            write_wide(acts, store / "matrices" / f"{name}_{ctx}.parquet")
            if ctx == "kprl":
                write_wide(pvals, store / "matrices" / f"{name}_cp_pvals.parquet")
        mods = module_activities(matrix, modules, pert_ids)
        write_wide(mods, store / "matrices" / f"renal_modules_{ctx}.parquet")
        del mat, matrix
        print(f"[ctx] {ctx} done ({time.time() - t0:.0f}s)")

    # legacy aliases for kprl (old readers)
    for name in ("progeny", "collectri", "renal_modules"):
        src = store / "matrices" / f"{name}_kprl.parquet"
        if src.exists():
            pd.read_parquet(src).to_parquet(store / "matrices" / f"{name}_cp.parquet",
                                            index=False)

    if not args.skip_precompute:
        print("[precompute] expr_kidney_cp")
        precompute_expr(store)
        print("[precompute] genetic_mimicry_cp")
        precompute_mimicry(store)
    print(f"[done] {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
