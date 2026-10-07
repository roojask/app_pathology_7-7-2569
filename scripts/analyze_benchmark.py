"""
analyze_benchmark.py  (revised)
Reproduces every WER / CER / latency statistic of the thesis from the per-case CSV.

Changes from the earlier version:
  * normalize_criteria_b() now implements the criterion actually used for the reported
    WER-B numbers (7.25% vs 2.78%). The earlier version produced 13.51% vs 11.41% because
    its dimension regex consumed the first number of a chain such as 11.4x14.9x7.8,
    leaving the rest ("x7.8") unmatched.
  * No statistic is hard-coded: WER-B means, difference, bootstrap CI, Wilcoxon test and win
    rates are all computed from the data.
  * No dependency on jiwer (own word/char Levenshtein; identical to jiwer.wer / jiwer.cer).
  * Adds per-category paired statistics and an error-rate-by-word-class table.

Usage:  python analyze_benchmark.py [benchmark_1000_cases_overnight.csv]
Requires: numpy, pandas, scipy
"""
import sys, re, collections
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats

SEED, NBOOT = 42, 5000

def lev(r, h):
    prev = list(range(len(h) + 1))
    for i, a in enumerate(r, 1):
        cur = [i]
        for j, b in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a != b)))
        prev = cur
    return prev[-1]

def wer(ref, hyp):
    r, h = ref.split(), hyp.split()
    return lev(r, h) / max(1, len(r))

def cer(ref, hyp):
    return lev(list(ref), list(hyp)) / max(1, len(ref))

def norm_a(t):
    t = str(t).lower()
    t = re.sub(r"[.,;:!?\-]", " ", t)
    return " ".join(t.split())

def norm_b(t):
    """Criterion A plus: 'x' / 'by' between numbers -> ' x ', and number+unit separated."""
    t = str(t).lower()
    for _ in range(2):                       # second pass handles chains a x b x c
        t = re.sub(r"(\d)\s*(?:x|by)\s*(?=\d)", r"\1 x ", t)
    t = re.sub(r"(\d)(cm|mm|g|kg)\b", r"\1 \2", t)
    t = re.sub(r"[.,;:!?\-]", " ", t)
    return " ".join(t.split())

def boot_ci(d, seed=SEED, n=NBOOT):
    rng = np.random.RandomState(seed)
    m = [np.mean(rng.choice(d, size=len(d), replace=True)) for _ in range(n)]
    return np.percentile(m, 2.5), np.percentile(m, 97.5)

def paired(name, b, p, unit="%"):
    d = b - p
    w = stats.wilcoxon(b, p, alternative="greater")
    lo, hi = boot_ci(d)
    print(f"{name}: base {b.mean():.3f}{unit} | PW {p.mean():.3f}{unit} | diff {d.mean():.3f} "
          f"(rel {100*d.mean()/b.mean():.2f}%) | 95% CI [{lo:.2f}, {hi:.2f}] | "
          f"W+ {w.statistic:.1f} p {w.pvalue:.3e} | PW better {100*np.mean(d>1e-3):.1f}% worse {100*np.mean(d<-1e-3):.1f}%")
    return d

MED = set("mastectomy modified radical simple infiltrative mass quadrant margin deep superior inferior "
          "medial lateral lymph nodes axillary specimen skin ellipse formalin surgical discrete fibrocystic "
          "parenchyma circumscribed right left upper outer inner lower central".split())
UNIT = {"cm", "mm", "x", "g", "kg"}

def wclass(w):
    if re.search(r"\d", w): return "number"
    if w in MED: return "medical term"
    if w in UNIT: return "unit/dimension symbol"
    return "other word"

def ref_errors(r, h):
    """per-reference-token error flag (substitution or deletion) and insertion count"""
    n, m = len(r), len(h)
    D = np.zeros((n + 1, m + 1), int); D[:, 0] = range(n + 1); D[0, :] = range(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i, j] = min(D[i-1, j] + 1, D[i, j-1] + 1, D[i-1, j-1] + (r[i-1] != h[j-1]))
    i, j, err, ins = n, m, [0] * n, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and D[i, j] == D[i-1, j-1] + (r[i-1] != h[j-1]):
            err[i-1] = int(r[i-1] != h[j-1]); i -= 1; j -= 1
        elif i > 0 and D[i, j] == D[i-1, j] + 1:
            err[i-1] = 1; i -= 1
        else:
            ins += 1; j -= 1
    return err, ins

def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        default_p = Path(__file__).resolve().parent.parent / "benchmarks" / "thesis_eval_outputs" / "benchmark_1000_cases_overnight.csv"
        path = default_p if default_p.exists() else Path("benchmark_1000_cases_overnight.csv")
        
    df = pd.read_csv(path)
    pw = df[df.system.str.contains("PathoWhisper", case=False)].sort_values("case_id").reset_index(drop=True)
    bs = df[df.system.str.contains("Baseline", case=False)].sort_values("case_id").reset_index(drop=True)
    assert len(pw) == len(bs) == 1000 and (pw.case_id == bs.case_id).all()
    refs = bs.ref_text.tolist()

    A = lambda H, f: np.array([f(norm_a(r), norm_a(h)) * 100 for r, h in zip(refs, H)])
    B = lambda H: np.array([wer(norm_b(r), norm_b(h)) * 100 for r, h in zip(refs, H)])
    bA, pA = A(bs.hyp_text, wer), A(pw.hyp_text, wer)
    bB, pB = B(bs.hyp_text), B(pw.hyp_text)
    bC, pC = A(bs.hyp_text, cer), A(pw.hyp_text, cer)
    bL, pL = bs.latency_sec.values, pw.latency_sec.values

    print("=" * 90); print("1. OVERALL (N = 1,000 paired cases, bootstrap seed 42, 5,000 resamples)"); print("=" * 90)
    dA = paired("WER criterion A", bA, pA)
    print(f"   (difference of rounded means: {round(bA.mean(),2)} - {round(pA.mean(),2)} = {round(bA.mean(),2)-round(pA.mean(),2):.2f})")
    paired("WER criterion B", bB, pB)
    paired("CER criterion A ", bC, pC)
    paired("Latency (s)     ", bL, pL, unit="s")
    print(f"   median latency {np.median(bL):.2f}s vs {np.median(pL):.2f}s; speedup mean {bL.mean()/pL.mean():.2f}x, median {np.median(bL)/np.median(pL):.2f}x")

    print("\n" + "=" * 90); print("2. PER CATEGORY (paired, one-sided Wilcoxon, no multiplicity correction)"); print("=" * 90)
    print(f"{'cat':<4}{'A base':>8}{'A PW':>8}{'B base':>8}{'B PW':>8}{'CER b':>8}{'CER p':>8}{'diff A':>8}{'CI A':>16}{'p':>11}{'PW worse%':>10}")
    for c in range(1, 11):
        m = (bs.category_id == c).values
        d = bA[m] - pA[m]; lo, hi = boot_ci(d); p = stats.wilcoxon(bA[m], pA[m], alternative="greater").pvalue
        print(f"{c:<4}{bA[m].mean():8.2f}{pA[m].mean():8.2f}{bB[m].mean():8.2f}{pB[m].mean():8.2f}"
              f"{bC[m].mean():8.2f}{pC[m].mean():8.2f}{d.mean():8.2f}{'[%.2f,%.2f]'%(lo,hi):>16}{p:11.2e}{100*np.mean(d<-1e-3):10.1f}")

    print("\n" + "=" * 90); print("3. REFERENCE-TOKEN ERROR RATE BY WORD CLASS (criterion-B normalisation; substitutions + deletions)"); print("=" * 90)
    out = {}
    for name, H in (("Baseline", bs), ("PathoWhisper", pw)):
        tot, bad, ins = collections.Counter(), collections.Counter(), 0
        for r, h in zip(refs, H.hyp_text):
            rt, ht = norm_b(r).split(), norm_b(h).split()
            e, k = ref_errors(rt, ht); ins += k
            for w_, x in zip(rt, e): tot[wclass(w_)] += 1; bad[wclass(w_)] += x
        out[name] = (tot, bad, ins)
    print(f"{'class':<24}{'ref tokens':>11}{'base err':>10}{'base %':>9}{'PW err':>9}{'PW %':>8}")
    for c in ("medical term", "number", "unit/dimension symbol", "other word"):
        t = out["Baseline"][0][c]; b_, p_ = out["Baseline"][1][c], out["PathoWhisper"][1][c]
        print(f"{c:<24}{t:11d}{b_:10d}{100*b_/t:9.2f}{p_:9d}{100*p_/t:8.2f}")
    print(f"inserted words (not attributable to a class): baseline {out['Baseline'][2]}, PathoWhisper {out['PathoWhisper'][2]}")
    print("=" * 90)

if __name__ == "__main__":
    main()
