#!/usr/bin/env python
"""Build the chemical core: pert_info merge, RDKit descriptors, ECFP4,
InChIKey-14 scaffold merge."""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from rdkit import Chem, RDLogger
from rdkit.Chem import Crippen, Descriptors, QED, rdMolDescriptors
from rdkit.Chem import FilterCatalog
from rdkit.Chem import rdFingerprintGenerator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CP_TYPE, load_settings, paths, phase_specs, read_tsv_gz

RDLogger.DisableLog("rdApp.*")
MISSING = {"-666", "", "nan", "None"}


def clean(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    value = str(value).strip()
    return None if value in MISSING else value


def build_pains():
    params = FilterCatalog.FilterCatalogParams()
    for name in ("PAINS_A", "PAINS_B", "PAINS_C"):
        params.AddCatalog(getattr(FilterCatalog.FilterCatalogParams.FilterCatalogs, name))
    return FilterCatalog.FilterCatalog(params)


def main():
    t0 = time.time()
    cfg = load_settings()
    lv = paths()["level5"]
    share = paths()["share_lincs"]
    store = paths()["store"]
    out = store / "chem"
    out.mkdir(parents=True, exist_ok=True)

    p1 = read_tsv_gz(share / phase_specs()["phase1"]["pert"])
    p2 = read_tsv_gz(share / phase_specs()["phase2"]["pert"])
    p1 = p1[p1["pert_type"] == CP_TYPE]
    p2 = p2[p2["pert_type"] == CP_TYPE]
    p1 = p1.drop_duplicates("pert_id").set_index("pert_id")
    p2 = p2.drop_duplicates("pert_id").set_index("pert_id")
    all_ids = list(dict.fromkeys(list(p1.index) + list(p2.index)))
    print(f"[pert_info] p1 cp={len(p1)} p2 cp={len(p2)} union={len(all_ids)}")

    def pick(pid, col):
        for frame in (p1, p2):
            if pid in frame.index and col in frame.columns:
                v = clean(frame.at[pid, col])
                if v:
                    return v
        return None

    catalog = build_pains()
    fpgen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    rows, fps = [], np.zeros((len(all_ids), 2048), dtype=np.uint8)
    for i, pid in enumerate(all_ids):
        smi = pick(pid, "canonical_smiles")
        mol = Chem.MolFromSmiles(smi) if smi else None
        rec = {"pert_id": pid, "pert_iname": pick(pid, "pert_iname"),
               "input_smiles": smi, "pubchem_cid": pick(pid, "pubchem_cid"),
               "is_touchstone": int(pick(pid, "is_touchstone") or 0),
               "has_structure": int(mol is not None)}
        if mol is not None:
            rec.update({
                "canonical_smiles": Chem.MolToSmiles(mol),
                "inchikey": Chem.MolToInchiKey(mol),
                "mw": Descriptors.MolWt(mol),
                "logp": Crippen.MolLogP(mol),
                "hbd": rdMolDescriptors.CalcNumHBD(mol),
                "hba": rdMolDescriptors.CalcNumHBA(mol),
                "tpsa": rdMolDescriptors.CalcTPSA(mol),
                "rotb": rdMolDescriptors.CalcNumRotatableBonds(mol),
                "qed": QED.qed(mol),
            })
            rec["lipinski_violations"] = int(
                rec["mw"] > 500) + int(rec["logp"] > 5) + int(rec["hbd"] > 5) + int(rec["hba"] > 10)
            rec["pains_alerts"] = len(catalog.GetMatches(mol))
            bits = np.frombuffer(fpgen.GetFingerprint(mol).ToBitString().encode(),
                                 dtype=np.uint8) - ord("0")
            fps[i] = bits
        else:
            rec.update({"canonical_smiles": smi, "inchikey": pick(pid, "inchi_key")})
        rows.append(rec)

    compounds = pd.DataFrame(rows)
    compounds["inchikey14"] = compounds["inchikey"].where(
        compounds["inchikey"].notna(), "").str.slice(0, 14).replace("", None)

    cp_index = pd.read_parquet(store / "cp_index.parquet")
    compounds = compounds.merge(
        cp_index[["pert_id", "matrix_row_idx", "n_sigs", "kprl_lambda"]],
        on="pert_id", how="left")
    unmatched = int(compounds["matrix_row_idx"].isna().sum())
    compounds["matrix_row_idx"] = compounds["matrix_row_idx"].astype("Int64")

    struct = compounds[compounds["has_structure"] == 1]
    named = struct.assign(named=~struct["pert_iname"].str.startswith("BRD-", na=True))
    rep = (named.sort_values(["named", "pert_id"], ascending=[False, True])
                .drop_duplicates("inchikey14"))
    counts = struct.groupby("inchikey14").size().rename("member_count")
    scaffolds = rep[["inchikey14", "pert_id", "pert_iname"]].rename(
        columns={"pert_id": "representative_pert_id", "pert_iname": "canonical_name"}
    ).merge(counts, on="inchikey14")
    scaffolds["member_count"] = scaffolds["member_count"].astype(int)

    compounds.to_parquet(out / "compounds.parquet", index=False)
    scaffolds.to_parquet(out / "scaffolds.parquet", index=False)
    np.save(out / "ecfp4_cp.npy", fps)

    print(f"[chem] compounds={len(compounds)} with_structure={len(struct)} "
          f"distinct_inchikey={compounds['inchikey'].nunique()} "
          f"scaffolds={len(scaffolds)} unmatched_matrix_rows={unmatched}")
    print(f"[chem] pa_in_valid={int(struct['pains_alerts'].notna().sum())} "
          f"touchstone={int(compounds['is_touchstone'].sum())}")
    print(f"[time] {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
