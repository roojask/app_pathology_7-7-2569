"""
eval_clinical_core_metrics.py  (revised)
Case-level clinical metrics for the PathoWhisper thesis.

Differences from the earlier version:
  * Field comparison is identical to eval_pure_gt_15_fields.py (same tolerances, order-sensitive
    dimensions, separator-insensitive strings), so the numbers agree with the field tables.
    The earlier version compared dimensions as sorted lists, which hid order errors.
  * Adds a paired comparison (McNemar exact test and paired bootstrap CI) for the critical error rate,
    the "perfect-transcript" floor (extractor run on the script text), the rate excluding category 2,
    critical-field omission/commission counts, and case-level flag coverage.
  * No numbers are typed by hand.

Usage:
  python eval_clinical_core_metrics.py [ground_truth_1000_pure.json] [benchmark_1000_cases_overnight.csv] [fair_empirical_comparison_20cases.csv]
Requires: numpy, pandas, scipy
"""
import sys, re, json, math
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.nlp.extractor import extract_data_15_sections, generate_confidence_flags

KEYS = ["s0_surgical_no","s1_side","s2_proc","s3_dims","s4_skin","s5_dims","s6_nipple","s7_biopsy_scar",
        "s8_cavity","s9_residual_mass","s10_infiltrative","s10_inf_dims","s10_5_quadrant","s11_deep_margin","s14_check"]
CRIT = ["s1_side","s3_dims","s10_infiltrative","s10_inf_dims","s11_deep_margin","s14_check"]
INACT = ["s6_nipple","s7_biopsy_scar","s8_cavity","s9_residual_mass"]

def dims_eq(a, b):
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b): return False
    try: return all(abs(float(x) - float(y)) < 0.05 for x, y in zip(a, b))
    except (ValueError, TypeError): return [str(x).strip().lower() for x in a] == [str(x).strip().lower() for x in b]
def num_eq(a, b):
    try: return abs(float(a) - float(b)) < 0.05
    except (ValueError, TypeError): return str(a).strip().lower() == str(b).strip().lower()
def str_eq(a, b):
    f = lambda s: re.sub(r"[\s\-_]+", "", str(s).lower()); return f(a) == f(b)
has = lambda v: v is not None and v != "" and v != [] and v is not False

def mapped(p):
    q = " ".join(p["s10_5_quadrant_vals"]) if p.get("s10_5_quadrant_vals") else ("central" if p.get("s10_5_central") else None)
    return {"s0_surgical_no": p.get("s0_surgical_no"), "s1_side": p.get("s1_side"), "s2_proc": p.get("s2_proc"),
            "s3_dims": p.get("s3_dims"), "s4_skin": bool(p.get("s5_appears_normal") or p.get("s5_dims")), "s5_dims": p.get("s5_dims"),
            "s6_nipple": p.get("s9_val"), "s7_biopsy_scar": p.get("s6_check"), "s8_cavity": p.get("s10_prev1") or p.get("s10_prev2"),
            "s9_residual_mass": p.get("s10_prev2_mass_dims"), "s10_infiltrative": p.get("s10_infiltrative"),
            "s10_inf_dims": p.get("s10_inf_dims"), "s10_5_quadrant": q, "s11_deep_margin": p.get("s11_deep"), "s14_check": p.get("s14_check")}

def cmp(k, g, p):
    G, P = has(g), has(p)
    if not G and not P: return "TN"
    if G and not P: return "FN"            # omission
    if not G and P: return "FP"            # commission (false fill)
    if k in ("s3_dims", "s5_dims", "s10_inf_dims"): m = dims_eq(g, p)
    elif k == "s11_deep_margin": m = num_eq(g, p)
    elif isinstance(g, bool): m = (p == g)
    else: m = str_eq(g, p)
    return "TP" if m else "WRONG"          # wrong value = commission

def run(texts, gt):
    out = {}
    for cid, t in texts.items():
        pred = extract_data_15_sections(str(t))
        pm = mapped(pred)
        out[cid] = ({k: cmp(k, gt[cid][k], pm[k]) for k in KEYS}, generate_confidence_flags(pred))
    return out

def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    m = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return 100 * (c - m), 100 * (c + m)

MED = set("mastectomy modified radical simple infiltrative mass quadrant margin deep superior inferior medial lateral lymph nodes axillary right left cm mm x".split())
def norm_b(t):
    t = str(t).lower()
    for _ in range(2): t = re.sub(r"(\d)\s*(?:x|by)\s*(?=\d)", r"\1 x ", t)
    t = re.sub(r"(\d)(cm|mm|g|kg)\b", r"\1 \2", t); t = re.sub(r"[.,;:!?\-]", " ", t); return " ".join(t.split())
def concept_counts(ref, hyp):
    r, h = norm_b(ref).split(), norm_b(hyp).split(); n, m = len(r), len(h)
    D = np.zeros((n + 1, m + 1), int); D[:, 0] = range(n + 1); D[0, :] = range(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1): D[i, j] = min(D[i-1, j] + 1, D[i, j-1] + 1, D[i-1, j-1] + (r[i-1] != h[j-1]))
    isc = lambda w: bool(re.search(r"\d", w)) or re.sub(r"[^a-z0-9]", "", w) in MED
    tot = err = 0; i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and D[i, j] == D[i-1, j-1] + (r[i-1] != h[j-1]):
            if isc(r[i-1]): tot += 1; err += int(r[i-1] != h[j-1])
            i -= 1; j -= 1
        elif i > 0 and D[i, j] == D[i-1, j] + 1:
            if isc(r[i-1]): tot += 1; err += 1
            i -= 1
        else: j -= 1
    return tot, err

def summarize(name, res, cat, n):
    crit = {c: any(r[k] not in ("TP", "TN") for k in CRIT) for c, (r, f) in res.items()}
    k = sum(crit.values()); lo, hi = wilson(k, n)
    k2 = sum(v for c, v in crit.items() if cat[c] != 2); n2 = sum(1 for c in crit if cat[c] != 2)
    om = sum(1 for v in res.values() for x in KEYS if v[0][x] == "FN")
    co = sum(1 for v in res.values() for x in KEYS if v[0][x] in ("FP", "WRONG"))
    om_c = sum(1 for v in res.values() for x in CRIT if v[0][x] == "FN")
    co_c = sum(1 for v in res.values() for x in CRIT if v[0][x] in ("FP", "WRONG"))
    ff = sum(1 for v in res.values() for x in INACT if v[0][x] == "FP")
    ce = [c for c, v in crit.items() if v]; fl = sum(1 for c in ce if res[c][1])
    print(f"{name:12s} CER_case {k}/{n} = {100*k/n:.2f}% [Wilson {lo:.2f}, {hi:.2f}] | exactness {100-100*k/n:.2f}% | "
          f"excl. category 2: {k2}/{n2} = {100*k2/n2:.2f}%")
    print(f"{'':12s} omissions {om} (critical fields {om_c}) | commissions {co} (critical fields {co_c}) | false-fill {ff} | "
          f"critical-error cases with >=1 flag: {fl}/{len(ce)}" + (f" = {100*fl/len(ce):.1f}%" if ce else ""))
    return crit

def main():
    gt_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000_pure.json")
    csv_path = Path(sys.argv[2]) if len(sys.argv) > 2 else (BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "benchmark_1000_cases_overnight.csv")
    d20_path = Path(sys.argv[3]) if len(sys.argv) > 3 else (BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "fair_empirical_comparison_20cases.csv")

    gt = json.load(open(gt_path, encoding="utf-8"))
    df = pd.read_csv(csv_path)
    cat = {c: gt[c]["cat_idx"] for c in gt}; res, crit = {}, {}
    print("=" * 100); print("A. CASE-LEVEL CLINICAL METRICS (N = 1,000)"); print("=" * 100)
    for name, kw in (("Baseline", "Baseline"), ("PathoWhisper", "PathoWhisper")):
        s = df[df.system.str.contains(kw)]
        res[name] = run(dict(zip(s.case_id, s.hyp_text)), gt); crit[name] = summarize(name, res[name], cat, len(s))
    res["Script text"] = run({c: gt[c]["raw_text"] for c in gt}, gt); crit["Script text"] = summarize("Script text", res["Script text"], cat, 1000)
    ids = list(gt); b = np.array([crit["Baseline"][c] for c in ids]); p = np.array([crit["PathoWhisper"][c] for c in ids])
    n10, n01 = int((b & ~p).sum()), int((~b & p).sum())
    d = b.astype(float) - p.astype(float); rng = np.random.RandomState(42)
    bs = [d[rng.randint(0, len(d), len(d))].mean() * 100 for _ in range(5000)]
    print(f"\nPaired: baseline-only errors {n10}, PathoWhisper-only errors {n01}, "
          f"McNemar exact p = {stats.binomtest(n10, n10 + n01, 0.5).pvalue:.2e}, "
          f"difference {100*d.mean():.1f} points, bootstrap 95% CI [{np.percentile(bs,2.5):.1f}, {np.percentile(bs,97.5):.1f}]")
    print("\nCritical-field errors (slots with a wrong or missing value):")
    for k in CRIT: print(f"  {k:18s}", {n: sum(1 for v in res[n].values() if v[0][k] not in ("TP", "TN")) for n in res})
    print("\nConcept error rate (numbers, units and medical concept words; criterion-B normalisation):")
    for name, kw in (("Baseline", "Baseline"), ("PathoWhisper", "PathoWhisper")):
        s = df[df.system.str.contains(kw)]; t = e = 0
        for r_, h_ in zip(s.ref_text, s.hyp_text): a, c = concept_counts(r_, h_); t += a; e += c
        print(f"  {name:12s} {100*e/t:.2f}%  ({e}/{t})")
    lat = {n: df[df.system.str.contains(n)].latency_sec.values for n in ("Baseline", "PathoWhisper")}
    print("\nLatency median / P95:", {n: (round(float(np.median(v)), 2), round(float(np.percentile(v, 95)), 2)) for n, v in lat.items()})

    if d20_path.exists():
        d20 = pd.read_csv(d20_path)
        print("\n" + "=" * 100); print("B. FOUR-SYSTEM COMPARISON (20 cases)"); print("=" * 100)
        for name, col, lc in (("Vosk", "vosk_itn", "lat_vosk"), ("wav2vec 2.0", "w2v_itn", "lat_w2v"),
                              ("Baseline", "bs_hyp", "lat_baseline"), ("PathoWhisper", "pw_hyp", "lat_pathowhisper")):
            r = run(dict(zip(d20.case_id, d20[col])), gt); summarize(name, r, cat, len(d20))
            t = e = 0
            for r_, h_ in zip(d20.ref_text, d20[col]): a, c = concept_counts(r_, h_); t += a; e += c
            print(f"{'':12s} concept error {100*e/t:.2f}% | latency median {d20[lc].median():.2f}s P95 {np.percentile(d20[lc],95):.2f}s")

if __name__ == "__main__":
    main()
