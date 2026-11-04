"""rackets.json -> data/<id>.json, one file per racket.

Every rule lives here; the page only displays. Writes nothing if any check fails.
Spec: Tennis/Stringing/.scratch/stringing-site/generator-spec.md (kept local).
Stdlib only. Usage: python3 generator/generate.py [--out DIR]
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RACKETS_JSON = os.path.join(HERE, "..", "rackets.json")
DATA_DIR = os.path.join(HERE, "..", "data")

TARGETS = range(40, 56)          # whole lb, mains and crosses
ALPHAS = (0.20, 0.35, 0.50)      # mains α and crosses α
MAX_RESIDUAL = 0.305             # cm
AVG_TOL = 0.2 + 1e-9             # lb, inclusive; the epsilon is load-bearing
BAND_SIZES = {20: (2, 3, 3, 4), 19: (2, 3, 3, 3), 18: (2, 3, 3, 2)}
BAND_NAMES = ("outer", "outer-mid", "inner-mid", "centre")
MEASUREMENTS = ("rim_height", "rim_width", "longest_cross", "main_span", "cross_span",
                "top_clearance", "len_outer_main", "len_top_cross", "len_throat_cross")


# ---- rounding (never use round(): it rounds halves to even) ----

def r05(x):
    return math.floor(x * 2 + 0.5) / 2


def half_up_dp(x, dp):
    return math.floor(x * 10 ** dp + 0.5) / 10 ** dp


# ---- head model (ported from the runbook §8 helper) ----

def gaps_from_measurements(H, b, span_main, span_cross, dist_top, k, n):
    s_m = span_main / (2 * k - 1)
    s_c = span_cross / (n - 1)
    return (s_m, (b - span_main / 2) / s_m,
            s_c, dist_top / s_c, (H - dist_top - span_cross) / s_c)


def half_width(y, at, ab, b, ntop, nbot):
    a, k = (at, ntop) if y > 0 else (ab, nbot)
    return b * max(0.0, 1 - (abs(y) / a) ** k) ** (1.0 / k)


def mains_ratio(n_side, at, ab, b, ntop, nbot, s_m):
    L = []
    for i in range(n_side):
        x = s_m * (i + 0.5)
        L.append(at * max(0.0, 1 - abs(x / b) ** ntop) ** (1.0 / ntop) +
                 ab * max(0.0, 1 - abs(x / b) ** nbot) ** (1.0 / nbot))
    m = sum(L) / len(L)
    return [l / m for l in L]             # M1..Mn (centre -> edge)


def cross_ratio(n, at, ab, b, ntop, nbot, gap_top, gap_bot, s_c):
    ys = [at - gap_top * s_c - i * s_c for i in range(n)][::-1]   # C1 (throat) .. Cn (top)
    L = [2 * half_width(y, at, ab, b, ntop, nbot) for y in ys]
    m = sum(L) / len(L)
    return [l / m for l in L]             # C1..Cn (throat -> top)


def fit_exponents(H, b, f, span_main, span_cross, dist_top, meas, k, n):
    at, ab = f * H, (1 - f) * H
    s_m, _, s_c, gap_top, gap_bot = gaps_from_measurements(H, b, span_main, span_cross, dist_top, k, n)
    x_out = s_m * (k - 0.5)
    y_top = at - gap_top * s_c
    y_bot = y_top - (n - 1) * s_c
    best = None
    for ni in range(150, 401):
        for nb in range(150, 401):
            nt, nbo = ni / 100, nb / 100
            pred = (at * max(0.0, 1 - abs(x_out / b) ** nt) ** (1.0 / nt) +
                    ab * max(0.0, 1 - abs(x_out / b) ** nbo) ** (1.0 / nbo),
                    2 * half_width(y_top, at, ab, b, nt, nbo),
                    2 * half_width(y_bot, at, ab, b, nt, nbo))
            e = sum((p - q) ** 2 for p, q in zip(pred, meas))
            if best is None or e < best[0]:
                best = (e, nt, nbo)
    return best[1], best[2], math.sqrt(best[0] / 3)


def true_alpha(ratios, targets, ref):
    n = len(ratios); xb = sum(ratios) / n; tb = sum(targets) / n
    num = sum((x - xb) * (t - tb) for x, t in zip(ratios, targets))
    den = sum((x - xb) ** 2 for x in ratios)
    return (num / den) / ref


# ---- input ----

def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate(doc):
    """Return a list of failure lines; empty means valid."""
    errs = []
    if doc.get("schema") != 1:
        return [f"rackets.json input schema: {doc.get('schema')!r}"]
    rackets = doc.get("rackets")
    if not isinstance(rackets, list) or not rackets:
        return ["rackets.json input rackets: missing or empty"]
    seen = set()
    for i, r in enumerate(rackets):
        rid = r.get("id")
        who = rid if isinstance(rid, str) and rid else f"rackets[{i}]"
        if who != rid:
            errs.append(f"{who} input id: missing")
        elif rid in seen:
            errs.append(f"{who} input id: duplicate")
        seen.add(rid)
        mains, crosses = r.get("mains"), r.get("crosses")
        if not (_is_int(mains) and mains >= 4 and mains % 2 == 0):
            errs.append(f"{who} input mains: {mains!r}")
        if crosses not in BAND_SIZES or not _is_int(crosses):
            errs.append(f"{who} input crosses: {crosses!r}")
        if not isinstance(r.get("split_outer_crosses"), bool):
            errs.append(f"{who} input split_outer_crosses: {r.get('split_outer_crosses')!r}")
        m = r.get("measurements")
        if not isinstance(m, dict):
            errs.append(f"{who} input measurements: missing")
            continue
        for key in MEASUREMENTS:
            v = m.get(key)
            if not _is_num(v) or v <= 0:
                errs.append(f"{who} input {key}: {v!r}")
        j = m.get("longest_cross")
        if _is_int(crosses) and not (_is_int(j) and 1 <= j <= crosses):
            errs.append(f"{who} input longest_cross: {j!r}")
    return errs


# ---- per racket ----

def derive(r):
    """Measurements -> geometry, ratios and layout (everything a cell needs)."""
    M = r["measurements"]
    H, b, j = M["rim_height"], M["rim_width"] / 2, M["longest_cross"]
    k, n = r["mains"] // 2, r["crosses"]
    s_m, gap_m, s_c, gap_top, gap_bot = gaps_from_measurements(
        H, b, M["main_span"], M["cross_span"], M["top_clearance"], k, n)
    f = (M["top_clearance"] + (n - j) * s_c) / H          # rule B: measured position
    ntop, nbot, residual = fit_exponents(
        H, b, f, M["main_span"], M["cross_span"], M["top_clearance"],
        (M["len_outer_main"], M["len_top_cross"], M["len_throat_cross"]), k, n)
    at, ab = f * H, (1 - f) * H
    return {
        "k": k, "n": n,
        "rm": mains_ratio(k, at, ab, b, ntop, nbot, s_m),
        "rc": cross_ratio(n, at, ab, b, ntop, nbot, gap_top, gap_bot, s_c),
        "residual": residual,
        "derived": {
            "f": half_up_dp(f, 3), "s_m": half_up_dp(s_m, 3), "gap_m": half_up_dp(gap_m, 2),
            "s_c": half_up_dp(s_c, 3), "gap_top": half_up_dp(gap_top, 2),
            "gap_bot": half_up_dp(gap_bot, 2), "ntop": ntop, "nbot": nbot,
            "residual": half_up_dp(residual, 2),
        },
        "bands": cross_bands(n, r["split_outer_crosses"]),
        "comp": {"M1": 3, f"M{k}": 6, "C1": 6},
    }


def cross_bands(n, split):
    """[(name, [string numbers ascending]), ...] outer -> centre."""
    bands, lo = [], 0
    for name, size in zip(BAND_NAMES, BAND_SIZES[n]):
        throat = list(range(lo + 1, lo + size + 1))
        top = sorted(n + 1 - x for x in throat)
        lo += size
        if name == "outer" and split:
            bands += [("outer-top", top), ("outer-throat", throat)]
        else:
            bands.append((name, sorted(set(throat + top))))
    return bands


def ideals(T, a, ratios):
    return [T * ((1 - a) + a * r) for r in ratios]


def band_means(ic, bands):
    """Unrounded mean ideal per band, summed in ascending string order."""
    return [sum(ic[x - 1] for x in idx) / len(idx) for _, idx in bands]


def cell(geo, Tm, Tc, am, ac):
    """One scenario -> (cell dict, unrounded averages)."""
    k, n, comp = geo["k"], geo["n"], geo["comp"]
    mv = [r05(x) for x in ideals(Tm, am, geo["rm"])]
    cv = [0.0] * n
    for (_, idx), mean in zip(geo["bands"], band_means(ideals(Tc, ac, geo["rc"]), geo["bands"])):
        for x in idx:
            cv[x - 1] = r05(mean)
    m = {f"M{i + 1}": v for i, v in enumerate(mv)}
    c = {f"C{i + 1}": v for i, v in enumerate(cv)}
    avg_m, avg_c = sum(mv) / k, sum(cv) / n
    return {
        "m": m,
        "mm": {s: v + comp.get(s, 0) for s, v in m.items()},
        "c": c,
        "cm": {s: v + comp.get(s, 0) for s, v in c.items()},
        "avg": [half_up_dp(avg_m, 2), half_up_dp(avg_c, 2)],
        "alpha": [half_up_dp(true_alpha(geo["rm"], mv, Tm), 2),
                  half_up_dp(true_alpha(geo["rc"], cv, Tc), 2)],
    }, (avg_m, avg_c)


def scenarios():
    for Tm in TARGETS:
        for Tc in TARGETS:
            for am in ALPHAS:
                for ac in ALPHAS:
                    yield f"{Tm}-{Tc}-{am:.2f}-{ac:.2f}", Tm, Tc, am, ac


def build(r):
    """Racket spec -> (output doc, failure lines)."""
    rid, fails = r["id"], []
    geo = derive(r)
    if geo["residual"] > MAX_RESIDUAL:
        fails.append(f"{rid} geometry residual: {geo['residual']:.4f} cm > {MAX_RESIDUAL}")
    cells = {}
    for key, Tm, Tc, am, ac in scenarios():
        out, (avg_m, avg_c) = cell(geo, Tm, Tc, am, ac)
        if abs(avg_m - Tm) > AVG_TOL:
            fails.append(f"{rid} {key} mains average: {avg_m!r}")
        if abs(avg_c - Tc) > AVG_TOL:
            fails.append(f"{rid} {key} crosses average: {avg_c!r}")
        mv = list(out["m"].values())
        if any(mv[i] < mv[i + 1] for i in range(len(mv) - 1)):
            fails.append(f"{rid} {key} monotonic mains: {mv}")
        cells[key] = out
    doc = {
        "schema": 1,
        "racket": {"id": rid, "name": r["name"]},
        "derived": geo["derived"],
        "layout": {
            "cross_bands": [{"band": name, "strings": [f"C{x}" for x in idx]}
                            for name, idx in geo["bands"]],
            "comp": geo["comp"],
        },
        "cells": cells,
    }
    return doc, fails


def serialise(doc):
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n"


def generate(rackets_path=RACKETS_JSON):
    """-> ({id: file text}, failure lines). Pure: writes nothing."""
    with open(rackets_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    fails = validate(spec)
    if fails:
        return {}, fails
    files = {}
    for r in spec["rackets"]:
        doc, f = build(r)
        fails += f
        files[r["id"]] = serialise(doc)
    return files, fails


def write(files, out):
    os.makedirs(out, exist_ok=True)
    for rid, text in files.items():
        with open(os.path.join(out, f"{rid}.json.tmp"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    for rid in files:
        os.replace(os.path.join(out, f"{rid}.json.tmp"), os.path.join(out, f"{rid}.json"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=DATA_DIR)
    args = ap.parse_args()
    files, fails = generate()
    if fails:
        for line in fails:
            print(line)
        print(f"FAILED: {len(fails)} problem(s); nothing written.")
        return 1
    write(files, args.out)
    n_cells = sum(1 for _ in scenarios())
    for rid, text in files.items():
        print(f"{rid}: {n_cells} cells, {len(text.encode('utf-8')):,} bytes")
    orphans = sorted(name[:-5] for name in os.listdir(args.out)
                     if name.endswith(".json") and name[:-5] not in files)
    for rid in orphans:
        print(f"orphan (not in rackets.json, not deleted): {rid}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
