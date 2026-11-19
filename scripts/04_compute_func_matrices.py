#!/usr/bin/env python
"""Compute PROGENy pathway, CollecTRI TF and curated renal module activities
for all compounds from the K-PRL consensus profiles (offline matrices)."""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_settings, paths

NET_DIR = None


def load_networks():
    import decoupler as dc
    NET_DIR.mkdir(parents=True, exist_ok=True)
    progeny_path = NET_DIR / "progeny.csv"
    collectri_path = NET_DIR / "collectri.csv"
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


def run_block(dc, mat, net, method, min_n, chunk):
    fn = dc.run_ulm if method == "ulm" else dc.run_wmean
    acts, pvals = [], []
    for start in range(0, len(mat), chunk):
        block = mat.iloc[start:start + chunk]
        res = fn(mat=block, net=net, source="source", target="target",
                 weight="weight", min_n=min_n, verbose=False)
        acts.append(res[0])
        pvals.append(res[1])
        print(f"  {method}: {min(start + chunk, len(mat))}/{len(mat)}", flush=True)
    return pd.concat(acts), pd.concat(pvals)


def module_activities(matrix, net, pert_ids):
    """Deterministic equal-weight mean z-score per curated renal module."""
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
    out = mat.astype("float32").reset_index(names="pert_id")
    out.to_parquet(path, index=False)
    print(f"[write] {path} {mat.shape}")


def main():
    global NET_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=2000)
    ap.add_argument("--method", default="ulm", choices=["ulm", "wmean"])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    import decoupler as dc
    t0 = time.time()
    cfg = load_settings()
    store = paths()["store"]
    NET_DIR = store / "annotations" / "networks"

    genes = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    cp = pd.read_parquet(store / "cp_index.parquet")
    symbols = genes["symbol"].tolist()
    symbol_to_col = {s.upper(): i for i, s in enumerate(symbols)}

    matrix = np.load(store / "matrices" / "kprl_cp_zscore.npy", mmap_mode="r")
    mat = pd.DataFrame(np.asarray(matrix), index=cp["pert_id"].tolist(), columns=symbols)

    progeny, collectri = load_networks()
    modules = module_net(symbol_to_col, ROOT / "config" / "renal_modules.yaml")

    tasks = [
        ("progeny", progeny, args.method, 5),
        ("collectri", collectri, args.method, 5),
    ]
    for name, net, method, min_n in tasks:
        target = store / "matrices" / f"{name}_cp.parquet"
        if target.exists() and not args.force:
            print(f"[skip] {target} exists")
            continue
        print(f"[run] {name}: {net['source'].nunique()} sources, method={method}")
        acts, pvals = run_block(dc, mat, net, method, min_n, args.chunk)
        write_wide(acts, store / "matrices" / f"{name}_cp.parquet")
        write_wide(pvals, store / "matrices" / f"{name}_cp_pvals.parquet")

    modules_df = module_activities(matrix, modules, cp["pert_id"].tolist())
    write_wide(modules_df, store / "matrices" / "renal_modules_cp.parquet")
    print(f"[done] {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
