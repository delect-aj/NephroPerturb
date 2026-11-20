"""Alias resolution invariants (case-insensitive aliases, order-preserving dedupe).

Run on the server: python tests/test_alias_resolution.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    from app.core.store import get_store

    store = get_store()

    # 1) pick real aliases whose canonical universe symbol differs from the
    #    alias text (this L1000 universe uses legacy symbols, e.g. CTGF itself)
    universe_entrez = set(store.genes["entrez_id"].astype(str))
    entrez_to_col = dict(zip(store.genes["entrez_id"], store.genes["matrix_col_idx"]))
    sym_of_col = dict(zip(store.genes["matrix_col_idx"],
                          store.genes["symbol"].astype(str).str.upper()))
    probes = []
    for alias_lower, entrez in store.aliases.items():
        e = str(entrez)
        if e not in universe_entrez or e not in entrez_to_col:
            continue
        canonical = sym_of_col[entrez_to_col[e]]
        if canonical != alias_lower.upper():
            probes.append((alias_lower, canonical))
        if len(probes) >= 20:
            break
    assert probes, "no alias/canonical-name pairs found to test"
    for alias_lower, canonical in probes:
        # 2) case-insensitive alias lookup (uppercase input)
        cols_a, miss_a = store.resolve_genes([alias_lower.upper()])
        assert miss_a == [] and len(cols_a) == 1, f"alias {alias_lower} unresolved"
        assert sym_of_col[cols_a[0]] == canonical, (alias_lower, canonical)
        # 3) mixed case input resolves identically
        cols_b, _ = store.resolve_genes([alias_lower])
        assert cols_b == cols_a

    # 4) synonym + canonical name deduplicate to one column, order preserved
    alias_lower, canonical = probes[0]
    cols3, _ = store.resolve_genes([canonical, "COL1A1", alias_lower])
    assert len(cols3) == 2, f"dedupe failed: {cols3}"
    assert cols3[0] == store.resolve_genes([canonical])[0][0], "order not preserved"

    # 4) every HGNC alias pointing at a universe gene resolves (sample 200)
    field = store.aliases
    universe_entrez = set(store.genes["entrez_id"].astype(str))
    tested = 0
    for alias_lower, entrez in field.items():
        if tested >= 200:
            break
        if str(entrez) not in universe_entrez:
            continue
        cols_a, missing_a = store.resolve_genes([alias_lower.upper()])
        assert missing_a == [] and len(cols_a) == 1, f"alias {alias_lower} failed"
        tested += 1
    assert tested > 0, "no aliases tested"

    # 5) unknown token reported, not silently dropped
    _, miss = store.resolve_genes(["NOT_A_REAL_GENE_XYZ"])
    assert miss == ["NOT_A_REAL_GENE_XYZ"]
    print(f"test_alias_resolution OK ({tested} aliases verified)")


if __name__ == "__main__":
    main()
