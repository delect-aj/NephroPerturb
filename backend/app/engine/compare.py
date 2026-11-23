"""Head-to-head renal pathway, module, and NephroSafe comparison engine."""
import numpy as np
import pandas as pd

from ..core.store import get_store
from .lookup import clean_val

KEY_PATHWAYS = ("TGFb", "NFkB", "JAK-STAT", "Hypoxia", "MAPK", "PI3K", "TNFa", "p53")
KEY_MODULES = (
    "ECM_fibrosis",
    "Podocyte_slit",
    "PT_FAO_mito",
    "Inflammation_NFkB",
    "Tubular_injury_KIM1",
    "TGFb_SMAD",
    "RAAS",
    "Ferroptosis_pyroptosis",
    "ER_stress_UPR",
)


def _extract_functional_vectors(store, pid: str, row_idx: int) -> tuple[dict, dict]:
    """Return full (progeny_dict, renal_modules_dict) for one compound."""
    progeny, modules = {}, {}
    if store.is_lite:
        idx_d = store.lite_active_idx("kprl_delta")
        pos_d = np.searchsorted(idx_d, row_idx)
        if pos_d < len(idx_d) and int(idx_d[pos_d]) == row_idx:
            fblk = store.lite_func_block("kprl_delta")
            f_row = int(pos_d)
        else:
            fblk = store.lite_func_block("pan")
            f_row = row_idx
        for name, target_dict in (("progeny", progeny), ("renal_modules", modules)):
            cols = [str(c) for c in fblk[f"{name}_cols"]]
            vals = fblk[f"{name}_raw"][f_row].astype(float)
            for col, val in zip(cols, vals):
                target_dict[col] = round(float(val), 3)
    else:
        for name, target_dict in (("progeny", progeny), ("renal_modules", modules)):
            frame = store.func_matrix(name)
            if pid in frame.index:
                for k, v in frame.loc[pid].astype(float).items():
                    short = k.split("_", 1)[1] if "_" in k else k
                    target_dict[short] = round(float(v), 3)
    return progeny, modules


def _extract_top_genes(store, row_idx: int, k: int = 5) -> tuple[list[dict], list[dict]]:
    genes = store.genes
    if store.is_lite:
        tg = store.lite_top_genes()
        n = min(int(k), tg["up_idx"].shape[1])
        up = [
            {"symbol": str(genes["symbol"].iloc[int(tg["up_idx"][row_idx, j])]),
             "z": round(float(tg["up_z"][row_idx, j]), 2)}
            for j in range(n)
        ]
        dn = [
            {"symbol": str(genes["symbol"].iloc[int(tg["dn_idx"][row_idx, j])]),
             "z": round(float(tg["dn_z"][row_idx, j]), 2)}
            for j in range(n)
        ]
        return up, dn
    matrix = store.matrix("kprl")
    profile = np.asarray(matrix[row_idx])
    order = np.argsort(-profile)
    up = [{"symbol": str(genes["symbol"].iloc[i]), "z": round(float(profile[i]), 2)}
          for i in order[:k]]
    dn = [{"symbol": str(genes["symbol"].iloc[i]), "z": round(float(profile[i]), 2)}
          for i in order[::-1][:k]]
    return up, dn


def compare_compounds(tokens: list[str]) -> dict:
    """Resolve 2-4 compounds and compare safety, pathways, modules, and K-PRL genes."""
    if not tokens or len(tokens) < 2:
        raise ValueError("Provide at least 2 compounds to compare.")
    store = get_store()
    seen_pids = set()
    items = []
    missing = []
    con = store.db()
    try:
        for raw_tok in tokens[:6]:
            tok = str(raw_tok or "").strip()
            if not tok:
                continue
            comp = store.get_compound_detail(tok)
            if comp is None:
                missing.append(tok)
                continue
            pid = str(comp["pert_id"])
            if pid in seen_pids:
                continue
            seen_pids.add(pid)
            row_idx = int(comp["matrix_row_idx"])
            progeny, modules = _extract_functional_vectors(store, pid, row_idx)
            up_g, dn_g = _extract_top_genes(store, row_idx, k=5)
            targets = pd.read_sql(
                "SELECT target_symbol FROM drug_targets WHERE pert_id = ?",
                con, params=(pid,),
            )["target_symbol"].dropna().astype(str).tolist()
            td_prob = clean_val(comp.get("tdiki_prob"))
            diril = clean_val(comp.get("diril_label"))
            items.append({
                "pert_id": pid,
                "pert_iname": clean_val(comp.get("pert_iname")) or pid,
                "clinical_phase": clean_val(comp.get("clinical_phase")) or "Preclinical/Unknown",
                "moa": clean_val(comp.get("moa")) or "—",
                "targets": targets[:10],
                "tdiki_tier": clean_val(comp.get("tdiki_tier")) or "NA",
                "tdiki_prob": None if td_prob is None else round(float(td_prob), 3),
                "diril_label": None if diril is None else int(diril),
                "qed": None if clean_val(comp.get("qed")) is None else round(float(comp["qed"]), 3),
                "mw": None if clean_val(comp.get("mw")) is None else round(float(comp["mw"]), 1),
                "n_sigs": int(comp.get("n_sigs") or 0),
                "progeny": {k: progeny.get(k) for k in KEY_PATHWAYS if k in progeny},
                "renal_modules": {k: modules.get(k) for k in KEY_MODULES if k in modules},
                "top_up_genes": up_g,
                "top_down_genes": dn_g,
            })
            if len(items) >= 4:
                break
    finally:
        con.close()

    if len(items) < 2:
        raise LookupError(
            f"Need at least 2 resolved compounds to compare (resolved={len(items)}, missing={missing})."
        )

    # Compute highlights deterministically
    safe_pool = [
        c for c in items
        if c["tdiki_tier"] in ("Low", "Moderate") and c["diril_label"] != 1
    ] or items
    safest = min(
        items,
        key=lambda c: (
            1 if c["diril_label"] == 1 else 0,
            c["tdiki_prob"] if c["tdiki_prob"] is not None else 0.5,
        ),
    )
    best_antifibrotic = min(
        safe_pool,
        key=lambda c: (
            c["renal_modules"].get("ECM_fibrosis", 0.0)
            + c["renal_modules"].get("TGFb_SMAD", 0.0)
        ),
    )
    best_podocyte = max(
        safe_pool,
        key=lambda c: (
            c["renal_modules"].get("Podocyte_slit", 0.0)
            + c["renal_modules"].get("PT_FAO_mito", 0.0)
        ),
    )
    return {
        "compounds": items,
        "missing": missing,
        "highlights": {
            "safest_kidney": safest["pert_iname"],
            "best_antifibrotic": best_antifibrotic["pert_iname"],
            "best_podocyte_metabolic": best_podocyte["pert_iname"],
        },
    }
