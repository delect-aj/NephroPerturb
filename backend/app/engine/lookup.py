"""Shared lightweight lookup helpers for target mimicry and ECFP4 Tanimoto search.

Used by both REST API (main.py) and MCP Server (mcp_server.py) to avoid
code duplication and eliminate 1.5 GB genetic_consensus / float32 fingerprint
reads in Lite mode.
"""
import numpy as np
import pandas as pd

from ..core.store import get_store

_POPCNT_LUT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint16)


def clean_val(value):
    if value is None:
        return None
    try:
        if value != value:  # NaN
            return None
    except Exception:
        pass
    return value


def target_mimicry_top(symbol: str, top_k: int = 50):
    store = get_store()
    sym_upper = symbol.strip().upper()

    if store.is_lite:
        con = store.db()
        try:
            rows = con.execute(
                "SELECT pert_id, pert_iname, similarity FROM target_mimicry "
                "WHERE gene_symbol = ? ORDER BY rank ASC LIMIT ?",
                (sym_upper, int(top_k)),
            ).fetchall()
        finally:
            con.close()
        return [{"pert_id": r[0], "pert_iname": r[1], "similarity": float(r[2])}
                for r in rows]

    genetic = store.genetic_index_map()
    ko = genetic[genetic["pert_iname"].fillna("").str.upper() == sym_upper]
    if ko.empty:
        return []
    gen_mat = np.load(store.store / "matrices" / "genetic_consensus.npy", mmap_mode="r")
    kprl = store.matrix("kprl")
    ko_rows = ko["matrix_row_idx"].astype(int).tolist()[:3]
    ko_vec = np.mean([np.asarray(gen_mat[r]) for r in ko_rows], axis=0)
    ko_norm = np.linalg.norm(ko_vec) + 1e-9
    sims = []
    for start in range(0, kprl.shape[0], 4000):
        block = np.asarray(kprl[start:start + 4000])
        num = block @ ko_vec
        den = np.linalg.norm(block, axis=1) * ko_norm + 1e-9
        sims.append(num / den)
    sims = np.concatenate(sims)
    idx = np.argsort(-sims)[:top_k]
    return [{"pert_id": store.cp_index["pert_id"].iloc[i],
             "pert_iname": store.cp_index["pert_iname"].iloc[i],
             "similarity": float(sims[i])} for i in idx]


def _clean_float(value):
    v = clean_val(value)
    return None if v is None else float(v)


def _clean_int(value):
    v = clean_val(value)
    return None if v is None else int(v)


def _neighbor_record(pid, row, tani_score: float) -> dict:
    return {
        "pert_id": pid,
        "pert_iname": clean_val(row.get("pert_iname")),
        "tanimoto": float(tani_score),
        "moa": clean_val(row.get("moa")),
        "clinical_phase": clean_val(row.get("clinical_phase")),
        "tdiki_tier": clean_val(row.get("tdiki_tier")),
        "tdiki_prob": _clean_float(row.get("tdiki_prob")),
        "diril_label": _clean_int(row.get("diril_label")),
    }


def structure_similarity_search(smiles: str = None, pert_id: str = None, top_k: int = 20):
    store = get_store()

    if store.is_lite:
        packed, popcnt = store.ecfp4_packed()
        if pert_id:
            comp = store.find_compound(pert_id)
            if comp is None:
                raise LookupError("compound not found")
            pos = store.fp_position[comp["pert_id"]]
            q_packed = packed[pos]
            q_bits = int(popcnt[pos])
        elif smiles:
            try:
                from rdkit import Chem
                from rdkit.Chem import rdFingerprintGenerator
            except ImportError as exc:
                raise NotImplementedError(
                    "RDKit is not installed in this lite environment; query by pert_id instead"
                ) from exc
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                raise ValueError("invalid SMILES")
            gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
            bits = (np.frombuffer(gen.GetFingerprint(mol).ToBitString().encode(),
                                  dtype=np.uint8) - ord("0"))
            q_packed = np.packbits(bits)
            q_bits = int(bits.sum())
        else:
            raise ValueError("provide smiles or pert_id")

        inter = _POPCNT_LUT[np.bitwise_and(packed, q_packed[None, :])].sum(axis=1, dtype=np.float32)
        union = popcnt.astype(np.float32) + float(q_bits) - inter
        tani = inter / np.maximum(union, 1.0)
        k = min(int(top_k), len(tani))
        cand = np.argpartition(-tani, k - 1)[:k]
        cand = cand[np.argsort(-tani[cand])]
        pert_ids = store.compounds["pert_id"].to_numpy()
        results = []
        for idx in cand:
            pid = pert_ids[idx]
            row = store.compounds.loc[pid]
            if hasattr(row, "ndim") and row.ndim > 1:
                row = row.iloc[0]
            results.append(_neighbor_record(pid, row, tani[idx]))
        return results

    # Full mode fallback
    from rdkit import Chem
    from rdkit.Chem import rdFingerprintGenerator

    if pert_id:
        comp = store.find_compound(pert_id)
        if comp is None:
            raise LookupError("compound not found")
        fps = np.load(store.store / "chem" / "ecfp4_cp.npy", mmap_mode="r")
        query = np.asarray(fps[store.fp_position[comp["pert_id"]]], dtype=np.float32)
    elif smiles:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("invalid SMILES")
        gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
        query = np.frombuffer(gen.GetFingerprint(mol).ToBitString().encode(),
                              dtype=np.uint8) - ord("0")
        query = query.astype(np.float32)
    else:
        raise ValueError("provide smiles or pert_id")

    fps = np.load(store.store / "chem" / "ecfp4_cp.npy", mmap_mode="r")
    qsum = query.sum()
    hits = []
    for start in range(0, fps.shape[0], 4000):
        block = np.asarray(fps[start:start + 4000], dtype=np.float32)
        inter = block @ query
        union = block.sum(axis=1) + qsum - inter
        tani = inter / np.maximum(union, 1)
        idx = np.argsort(-tani)[:top_k]
        for i in idx:
            hits.append((float(tani[i]), start + int(i)))
    hits = sorted(hits, reverse=True)[:top_k]
    pert_ids = store.compounds["pert_id"].to_numpy()
    results = []
    for score, idx in hits:
        pid = pert_ids[idx]
        row = store.compounds.loc[pid]
        if hasattr(row, "ndim") and row.ndim > 1:
            row = row.iloc[0]
        results.append(_neighbor_record(pid, row, score))
    return results
