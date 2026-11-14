"""Regression checks for generate.py. Exits 0 if every check passes, 1 otherwise.

Usage: python3 generator/check.py
"""
import json
import math
import os
import sys
import tempfile

import generate as gen

# 1. Derived geometry each seed racket must reproduce exactly (rule B f).
DERIVED = {
    "yonex-vcore-95-2026": {"f": 0.433, "s_m": 1.24, "gap_m": 2.3, "s_c": 1.326, "gap_top": 2.26,
                            "gap_bot": 2.41, "ntop": 2.28, "nbot": 2.01, "residual": 0.12},
    "head-squared-2026": {"f": 0.465, "s_m": 1.3, "gap_m": 2.15, "s_c": 1.553, "gap_top": 1.74,
                          "gap_bot": 2.19, "ntop": 2.06, "nbot": 1.99, "residual": 0.14},
    "head-gravity-mp-2025": {"f": 0.467, "s_m": 1.3, "gap_m": 2.31, "s_c": 1.384, "gap_top": 2.02,
                             "gap_bot": 2.6, "ntop": 2.01, "nbot": 1.89, "residual": 0.3},
    "wilson-python-98-pro-stock": {"f": 0.472, "s_m": 1.3, "gap_m": 2.0, "s_c": 1.4, "gap_top": 1.86,
                                   "gap_bot": 2.14, "ntop": 2.15, "nbot": 2.15, "residual": 0.23},
}

# 2. Hand charts Duke strung, under the old 3-group / 6-row layout, α 0.25 mains / 0.15 crosses.
#    Indices are 0-based string positions. Head Squared is excluded (hand-nudged crosses).
LEGACY_MAINS = [[0], [1], [2, 3], [4, 5], [6], [7]]
LEGACY_CROSSES = {"out": [0, 1, 2, 17, 18, 19], "mid": [3, 4, 5, 14, 15, 16], "cen": list(range(6, 14))}
LEGACY_CROSSES_SPLIT = {"top": [17, 18, 19], "mid": [3, 4, 5, 14, 15, 16],
                        "cen": list(range(6, 14)), "thr": [0, 1, 2]}
HAND_CHARTS = [
    ("head-gravity-mp-2025", 52, 52, [54, 54, 53, 51.5, 50, 48.5], {"out": 50.5, "mid": 52, "cen": 53}),
    ("head-gravity-mp-2025", 51, 51, [53, 53, 52, 50.5, 49, 47.5], {"out": 49.5, "mid": 51, "cen": 52}),
    ("yonex-vcore-95-2026", 50, 50, [51.5, 51.5, 51, 50, 48.5, 47], {"top": 49, "mid": 50, "cen": 51, "thr": 48}),
    ("yonex-vcore-95-2026", 48, 48, [49.5, 49.5, 49, 48, 46.5, 45], {"top": 47, "mid": 48, "cen": 49, "thr": 46}),
]

results = []


def report(name, who, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name:<16} {who}{'  ' + detail if detail and not ok else ''}")


def mean(v):
    return sum(v) / len(v)


def near_tie(x):
    """Within 1e-9 of a 0.25 boundary, where 0.5-lb half-up rounding flips."""
    return abs(x - (math.floor(x * 2) / 2 + 0.25)) < 1e-9


def main():
    with open(gen.RACKETS_JSON, encoding="utf-8") as fh:
        spec = json.load(fh)
    rackets = spec["rackets"]
    geos = {r["id"]: gen.derive(r) for r in rackets}

    for r in rackets:
        rid = r["id"]
        got, want = geos[rid]["derived"], DERIVED.get(rid)
        report("derived", rid, got == want, f"got {got}")

    for rid, Tm, Tc, want_m, want_c in HAND_CHARTS:
        geo = geos[rid]
        split = next(r for r in rackets if r["id"] == rid)["split_outer_crosses"]
        im, ic = gen.ideals(Tm, 0.25, geo["rm"]), gen.ideals(Tc, 0.15, geo["rc"])
        got_m = [gen.r05(mean([im[i] for i in idx])) for idx in LEGACY_MAINS]
        groups = LEGACY_CROSSES_SPLIT if split else LEGACY_CROSSES
        got_c = {g: gen.r05(mean([ic[i] for i in idx])) for g, idx in groups.items()}
        report("hand chart", f"{rid} {Tm}/{Tc}", got_m == want_m and got_c == want_c,
               f"mains {got_m} crosses {got_c}")

    for r in rackets:
        geo, ties = geos[r["id"]], 0
        for _, Tm, Tc, am, ac in gen.scenarios():
            ties += sum(near_tie(x) for x in gen.ideals(Tm, am, geo["rm"]))
            ties += sum(near_tie(x) for x in gen.band_means(gen.ideals(Tc, ac, geo["rc"]), geo["bands"]))
        report("rounding margin", r["id"], ties == 0, f"{ties} value(s) within 1e-9 of a tie")

    files, fails = gen.generate()
    if fails:
        report("generate", "all", False, f"{len(fails)} failure(s), first: {fails[0]}")
        return 1
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        gen.write(files, d1)
        gen.write(gen.generate()[0], d2)
        for rid in files:
            a = open(os.path.join(d1, f"{rid}.json"), "rb").read()
            b = open(os.path.join(d2, f"{rid}.json"), "rb").read()
            report("rerun identical", rid, a == b)
            committed = os.path.join(gen.DATA_DIR, f"{rid}.json")
            c = open(committed, "rb").read() if os.path.exists(committed) else None
            report("committed data", rid, a == c, "missing" if c is None else "stale — rerun generate.py")

    n_cells = sum(1 for _ in gen.scenarios())
    for r in rackets:
        doc, k, n = json.loads(files[r["id"]]), r["mains"] // 2, r["crosses"]
        comp, bad = doc["layout"]["comp"], []
        if len(doc["cells"]) != n_cells:
            bad.append(f"{len(doc['cells'])} cells")
        for key, c in doc["cells"].items():
            if (list(c["m"]) != [f"M{i}" for i in range(1, k + 1)] or list(c["mm"]) != list(c["m"])
                    or list(c["c"]) != [f"C{i}" for i in range(1, n + 1)] or list(c["cm"]) != list(c["c"])):
                bad.append(f"{key} string keys")
            for t, d in (("m", "mm"), ("c", "cm")):
                if any(c[d][s] - c[t][s] != comp.get(s, 0) for s in c[t]):
                    bad.append(f"{key} {d} comp")
        report("grid sanity", r["id"], not bad, "; ".join(bad[:3]))

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
