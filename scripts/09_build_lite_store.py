#!/usr/bin/env python
"""Build the ultra-lightweight runtime bundle `store_lite/` from `store/`.

Leaves `store/` and upstream `data/` completely untouched.
Produces a <2 GB gene-major, active-row-compacted, K-PRL-delta-deduplicated,
bit-packed runtime store designed for 1-core / <=1 GB RAM deployment.
"""
import gzip
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import paths  # noqa: E402

FUNC_NAMES = ("progeny", "collectri", "renal_modules")


def build_context(ctx_name, z_path, ranks_path, absranks_path, tau_path,
                  active_mask, out_dir, cp_ids, func_src_ctx):
    out_dir.mkdir(parents=True, exist_ok=True)
    active_idx = np.flatnonzero(active_mask).astype(np.int32)
    np.save(out_dir / "active_idx.npy", active_idx)
    n_act = len(active_idx)

    z_full = np.load(z_path, mmap_mode="r")
    r_full = np.load(ranks_path, mmap_mode="r")
    ar_full = np.load(absranks_path, mmap_mode="r")
    n_genes = z_full.shape[1]

    z_act = np.asarray(z_full[active_idx], dtype=np.float32)
    r_act = np.asarray(r_full[active_idx], dtype=np.uint16)
    ar_act = np.asarray(ar_full[active_idx], dtype=np.float32)

    # 1. Gene-major uint16 ranks_T: (n_genes, n_act)
    np.save(out_dir / "ranks_T.npy", np.ascontiguousarray(r_act.T))

    # 2. Gene-major int8 quantized ZhangScore matrix: (n_genes, n_act)
    z_signed_mag = np.sign(z_act) * (n_genes - ar_act) / float(n_genes)
    zhang_q8 = np.rint(z_signed_mag * 127.0).clip(-127, 127).astype(np.int8)
    np.save(out_dir / "zhang_T.npy", np.ascontiguousarray(zhang_q8.T))
    del z_signed_mag, zhang_q8, ar_act

    # 3. Gene-major CSR sparse float16 extreme matrix (top/bottom 500 per compound)
    ext_mask_T = ((r_act < 500) | (r_act >= n_genes - 500)).T
    g_idx, c_idx = np.nonzero(ext_mask_T)
    indptr = np.zeros(n_genes + 1, dtype=np.int32)
    np.add.at(indptr[1:], g_idx, 1)
    np.cumsum(indptr, out=indptr)
    indices = c_idx.astype(np.uint16)
    data = z_act.T[g_idx, c_idx].astype(np.float16)
    np.save(out_dir / "xsum_T_indptr.npy", indptr)
    np.save(out_dir / "xsum_T_indices.npy", indices)
    np.save(out_dir / "xsum_T_data.npy", data)
    del ext_mask_T, g_idx, c_idx, r_act, z_act, indptr, indices, data

    # 4. Tau quantile tables for active rows (float16)
    tau = np.load(tau_path)
    tau_lite = {k: np.asarray(tau[k][active_idx], dtype=np.float16) for k in tau.files}
    np.savez(out_dir / "tau_quantiles.npz", **tau_lite)

    # 5. Functional activity blocks (single float16 matrix + float32 L2 row norms)
    src_store = paths()["store"] / "matrices"
    act_pids = [cp_ids[i] for i in active_idx]
    func_payload = {}
    for fname in FUNC_NAMES:
        p = src_store / f"{fname}_{func_src_ctx}.parquet"
        if not p.exists():
            p = src_store / f"{fname}_cp.parquet"
        df = pd.read_parquet(p).set_index("pert_id").reindex(act_pids).fillna(0.0)
        arr32 = df.to_numpy(dtype=np.float32)
        norms = np.linalg.norm(arr32, axis=1).astype(np.float32)
        func_payload[f"{fname}_raw"] = arr32.astype(np.float16)
        func_payload[f"{fname}_norm"] = norms
        func_payload[f"{fname}_cols"] = np.array(list(df.columns), dtype=str)
    np.savez(out_dir / "func_blocks.npz", **func_payload)
    print(f"[ctx] {ctx_name}: n_act={n_act} done")


def build_top_genes(store_src, out_path, top_n=50):
    kprl = np.load(store_src / "matrices" / "kprl_cp_zscore.npy", mmap_mode="r")
    n_cp = kprl.shape[0]
    up_idx = np.empty((n_cp, top_n), dtype=np.uint16)
    up_z = np.empty((n_cp, top_n), dtype=np.float16)
    dn_idx = np.empty((n_cp, top_n), dtype=np.uint16)
    dn_z = np.empty((n_cp, top_n), dtype=np.float16)
    for start in range(0, n_cp, 2000):
        block = np.asarray(kprl[start:start + 2000], dtype=np.float32)
        order = np.argsort(-block, axis=1)
        u_i = order[:, :top_n]
        d_i = order[:, -top_n:][:, ::-1]
        rows = np.arange(len(block))[:, None]
        up_idx[start:start + 2000] = u_i.astype(np.uint16)
        up_z[start:start + 2000] = block[rows, u_i].astype(np.float16)
        dn_idx[start:start + 2000] = d_i.astype(np.uint16)
        dn_z[start:start + 2000] = block[rows, d_i].astype(np.float16)
    np.savez(out_path, up_idx=up_idx, up_z=up_z, dn_idx=dn_idx, dn_z=dn_z)
    print(f"[top_genes] wrote {out_path}")


def precompute_tdiki_explain(store_src, db_path, top_n=15):
    cal = joblib.load(store_src / "models" / "tdiki_v2_struct.joblib")
    struct_df = pd.read_parquet(store_src / "chem" / "tdiki_v2_struct.parquet").set_index("pert_id")
    tdiki_df = pd.read_parquet(store_src / "matrices" / "tdiki_cp.parquet").set_index("pert_id")
    feat_cols = list(struct_df.columns)
    X = struct_df[feat_cols].astype(float).fillna(0.0).to_numpy()
    probs_struct = cal.predict_proba(X)[:, 1]

    est = cal.calibrated_classifiers_[0].estimator if hasattr(cal, "calibrated_classifiers_") and cal.calibrated_classifiers_ else cal
    names = np.array(feat_cols)
    if hasattr(est, "named_steps") and "clf" in est.named_steps:
        clf = est.named_steps["clf"]
        xs = est.named_steps["scale"].transform(X) if "scale" in est.named_steps else X
        if "select" in est.named_steps and hasattr(est.named_steps["select"], "get_support"):
            sel = est.named_steps["select"].get_support()
            xsel = est.named_steps["select"].transform(xs)
            vals = xsel * clf.coef_[0][None, :]
            names = names[sel]
            xs_used = xsel
        else:
            vals = xs * clf.coef_[0][None, :]
            xs_used = xs
        use_abs = True
    elif hasattr(est, "feature_importances_"):
        vals = np.broadcast_to(est.feature_importances_[None, :], X.shape)
        xs_used = X
        use_abs = False
    else:
        vals = None

    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE IF EXISTS tdiki_explain")
    con.execute("""CREATE TABLE tdiki_explain (
        pert_id TEXT PRIMARY KEY,
        tdiki_struct REAL,
        tdiki_prob REAL,
        tdiki_tier TEXT,
        tdiki_tx REAL,
        contributions_json TEXT
    )""")

    rows = []
    pids = list(struct_df.index)
    for i, pid in enumerate(pids):
        trow = tdiki_df.loc[pid] if pid in tdiki_df.index else None
        if isinstance(trow, pd.DataFrame):
            trow = trow.iloc[0]
        contribs = []
        if vals is not None:
            v = vals[i]
            order = np.argsort(-np.abs(v) if use_abs else -v)[:top_n]
            contribs = [
                {"feature": str(names[j]),
                 "contribution": round(float(v[j]), 5),
                 "value": round(float(xs_used[i, j]), 5)}
                for j in order
            ]
        rows.append((
            pid,
            float(probs_struct[i]),
            None if trow is None or pd.isna(trow["tdiki_prob"]) else float(trow["tdiki_prob"]),
            "NA" if trow is None else str(trow.get("tdiki_tier", "NA")),
            None if trow is None or pd.isna(trow.get("tdiki_tx")) else float(trow["tdiki_tx"]),
            json.dumps(contribs),
        ))
    con.executemany("INSERT INTO tdiki_explain VALUES (?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    print(f"[tdiki_explain] inserted {len(rows)} rows into SQLite")


def precompute_target_mimicry(store_src, db_path, top_k=50):
    cp_index = pd.read_parquet(store_src / "cp_index.parquet")
    genetic = pd.read_parquet(store_src / "genetic_index.parquet")
    kprl = np.asarray(np.load(store_src / "matrices" / "kprl_cp_zscore.npy"), dtype=np.float32)
    gen_mat = np.load(store_src / "matrices" / "genetic_consensus.npy", mmap_mode="r")

    kprl_norm = np.linalg.norm(kprl, axis=1) + 1e-9
    kprl_unit = kprl / kprl_norm[:, None]

    target_syms = genetic["pert_iname"].fillna("").str.upper()
    by_sym = {}
    for idx, sym in enumerate(target_syms):
        if sym:
            by_sym.setdefault(sym, []).append(int(genetic["matrix_row_idx"].iloc[idx]))

    syms = sorted(by_sym.keys())
    ko_vecs = np.empty((len(syms), kprl.shape[1]), dtype=np.float32)
    for i, sym in enumerate(syms):
        rows = by_sym[sym][:3]
        vec = np.mean([np.asarray(gen_mat[r], dtype=np.float32) for r in rows], axis=0)
        ko_vecs[i] = vec / (np.linalg.norm(vec) + 1e-9)

    cp_ids = cp_index["pert_id"].to_numpy()
    cp_names = cp_index["pert_iname"].to_numpy()

    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE IF EXISTS target_mimicry")
    con.execute("""CREATE TABLE target_mimicry (
        gene_symbol TEXT,
        rank INTEGER,
        pert_id TEXT,
        pert_iname TEXT,
        similarity REAL
    )""")

    batch_rows = []
    for start in range(0, len(syms), 1000):
        end = min(start + 1000, len(syms))
        sims = ko_vecs[start:end] @ kprl_unit.T  # (B, 21299)
        top_idx = np.argpartition(-sims, top_k, axis=1)[:, :top_k]
        for b in range(end - start):
            sym = syms[start + b]
            cand = top_idx[b]
            cand = cand[np.argsort(-sims[b, cand])]
            for r_i, idx in enumerate(cand):
                pname = cp_names[idx]
                batch_rows.append((
                    sym, r_i + 1, str(cp_ids[idx]),
                    None if pd.isna(pname) else str(pname),
                    round(float(sims[b, idx]), 5),
                ))
        if len(batch_rows) >= 50000:
            con.executemany("INSERT INTO target_mimicry VALUES (?,?,?,?,?)", batch_rows)
            batch_rows.clear()
    if batch_rows:
        con.executemany("INSERT INTO target_mimicry VALUES (?,?,?,?,?)", batch_rows)
    con.execute("CREATE INDEX idx_tm_gene ON target_mimicry(gene_symbol, rank)")
    con.commit()
    con.close()
    print(f"[target_mimicry] indexed {len(syms)} genes x top-{top_k} in SQLite")


def copy_compact_assets(store_src, lite_dir):
    for rel in [
        "genes/gene_universe.parquet",
        "cp_index.parquet",
        "genetic_index.parquet",
        "chem/compounds.parquet",
        "chem/scaffolds.parquet",
        "matrices/expr_kidney_cp.parquet",
        "matrices/genetic_mimicry_cp.parquet",
        "matrices/tdiki_cp.parquet",
        "annotations/repurposing_hub.parquet",
        "annotations/nephrotoxicity_diril.parquet",
        "annotations/hgnc_aliases.parquet",
        "annotations/kidney_expression.parquet",
        "annotations/networks/progeny.csv",
        "annotations/networks/collectri.csv",
    ]:
        dst = lite_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(store_src / rel, dst)

    # Bit-pack ECFP4 fingerprints: (21299, 2048) -> (21299, 256) uint8
    fps = np.load(store_src / "chem" / "ecfp4_cp.npy")
    packed = np.packbits(fps.astype(np.uint8), axis=1)
    popcnt = fps.sum(axis=1).astype(np.uint16)
    np.save(lite_dir / "chem" / "ecfp4_packed.npy", packed)
    np.save(lite_dir / "chem" / "ecfp4_popcnt.npy", popcnt)
    print(f"[ecfp4] packed {fps.shape} -> {packed.shape} ({packed.nbytes/1e6:.2f} MB)")

    # Gzip downloads
    dl_dir = lite_dir / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    for gmt in sorted((store_src / "downloads").glob("*.gmt")):
        out_gz = dl_dir / (gmt.name + ".gz")
        with open(gmt, "rb") as fin, gzip.open(out_gz, "wb", compresslevel=6) as fout:
            shutil.copyfileobj(fin, fout, length=1 << 20)
    print(f"[downloads] gzipped GMTs into {dl_dir}")


def main():
    t0 = time.time()
    store_src = paths()["store"]
    lite_dir = store_src.parent / "store_lite"
    if lite_dir.exists():
        shutil.rmtree(lite_dir)
    lite_dir.mkdir(parents=True, exist_ok=True)

    cp_index = pd.read_parquet(store_src / "cp_index.parquet")
    cp_ids = cp_index["pert_id"].tolist()
    n_cp = len(cp_ids)
    mdir = store_src / "matrices"

    # Verify K-PRL delta mask against Pan-Cell
    pan_z = np.load(mdir / "pan_cp_zscore.npy", mmap_mode="r")
    kprl_z = np.load(mdir / "kprl_cp_zscore.npy", mmap_mode="r")
    kprl_diff_mask = np.abs(kprl_z - pan_z).max(axis=1) > 1e-6
    print(f"[verify] K-PRL differs from Pan-Cell on {int(kprl_diff_mask.sum())}/{n_cp} rows")

    contexts = [
        ("pan", "pan_cp_zscore.npy", "pan_cp_ranks.npy", "pan_absranks.npy",
         "tau_null_tables_pan.npz", np.ones(n_cp, dtype=bool), "pan"),
        ("kprl_delta", "kprl_cp_zscore.npy", "kprl_ranks.npy", "kprl_absranks.npy",
         "tau_null_tables_kprl.npz", kprl_diff_mask, "kprl"),
    ]
    for ctx in ("renal_epi", "renal_immune", "renal_endo"):
        z_fn = f"{ctx}_cp_zscore.npy"
        z_arr = np.load(mdir / z_fn, mmap_mode="r")
        mask = np.abs(z_arr).sum(axis=1) > 0
        contexts.append((
            ctx, z_fn, f"{ctx}_cp_ranks.npy", f"{ctx}_absranks.npy",
            f"tau_null_tables_{ctx}.npz", mask, ctx,
        ))

    manifest_ctx = {}
    for name, z_fn, r_fn, ar_fn, tau_fn, mask, f_ctx in contexts:
        build_context(
            name, mdir / z_fn, mdir / r_fn, mdir / ar_fn, mdir / tau_fn,
            mask, lite_dir / "matrices" / name, cp_ids, f_ctx,
        )
        manifest_ctx[name] = {"n_active": int(mask.sum())}

    build_top_genes(store_src, lite_dir / "matrices" / "compound_top_genes.npz", top_n=50)
    copy_compact_assets(store_src, lite_dir)

    db_dst = lite_dir / "nephroperturb.db"
    shutil.copy2(store_src / "nephroperturb.db", db_dst)
    precompute_tdiki_explain(store_src, db_dst, top_n=15)
    precompute_target_mimicry(store_src, db_dst, top_k=50)
    con = sqlite3.connect(db_dst)
    con.execute("VACUUM")
    con.close()

    manifest = {
        "format": "nephroperturb-lite-v1",
        "n_compounds": n_cp,
        "n_genes": int(pan_z.shape[1]),
        "contexts": manifest_ctx,
    }
    (lite_dir / "lite_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"[done] built {lite_dir} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
