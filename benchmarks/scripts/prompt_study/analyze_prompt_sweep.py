"""
analyze_prompt_sweep.py  --  summary + paired statistics for the prompt study.

Usage:
  python analyze_prompt_sweep.py results/prompt_sweep_test_denoiseoff.csv

Outputs (next to the input CSV):
  *_summary.csv   one row per variant (means, CORPUS-level WER, safety counts)
  *_paired.csv    each variant vs P0 and vs P4: mean diff, 95% CI, Wilcoxon, McNemar, Holm p

Methods (same family as H1-H6 in the thesis):
  * wer_b / wer_a: paired Wilcoxon signed-rank (Pratt) per case
  * cer_case: McNemar exact test (b = reference wrong & variant right, c = the reverse)
  * 95% CI: paired bootstrap, 10,000 resamples, resampling cases WITHIN each category
  * Holm correction over all comparisons of the same metric family
  * Corpus-level WER = total edits / total reference words (reported next to the
    per-case mean, because the thesis reports the per-case mean)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REFS = ["P0_none", "P4_full_cap"]
N_BOOT = 10_000
RNG = np.random.default_rng(42)


def holm(pvals):
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    running = 0.0
    m = len(p)
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p[i])
        adj[i] = min(1.0, running)
    return adj


def strat_boot_ci(diff, cats, n=N_BOOT):
    groups = [diff[cats == c] for c in np.unique(cats)]
    means = np.empty(n)
    for b in range(n):
        means[b] = np.concatenate([g[RNG.integers(0, len(g), len(g))] for g in groups]).mean()
    return np.percentile(means, [2.5, 97.5])


def mcnemar_exact(ref_err, var_err):
    b = int(((ref_err == 1) & (var_err == 0)).sum())   # variant fixes it
    c = int(((ref_err == 0) & (var_err == 1)).sum())   # variant breaks it
    if b + c == 0:
        return b, c, 1.0
    p = min(1.0, 2 * stats.binom.cdf(min(b, c), b + c, 0.5))  # two-sided exact
    return b, c, float(p)


def summary(df):
    rows = []
    for v, g in df.groupby("variant", sort=False):
        n = len(g)
        rows.append(dict(
            variant=v, n_cases=n,
            wer_a_mean=100 * g.wer_a.mean(), wer_b_mean=100 * g.wer_b.mean(),
            wer_a_corpus=100 * (g.S_a + g.D_a + g.I_a).sum() / g.N_a.sum(),
            wer_b_corpus=100 * (g.S_b + g.D_b + g.I_b).sum() / g.N_b.sum(),
            cer_case_pct=100 * g.cer_case.mean(),
            omission=int(g.n_omission.sum()), commission=int(g.n_commission.sum()),
            crit_omission=int(g.crit_omission.sum()), crit_commission=int(g.crit_commission.sum()),
            side_acc_pct=100 * (g.st_s1_side == "TP").mean(),
            s3_dims_exact_pct=100 * (g.st_s3_dims == "TP").mean(),
            inf_dims_exact_pct=100 * (g.st_s10_inf_dims == "TP").mean(),
            deep_margin_exact_pct=100 * (g.st_s11_deep_margin == "TP").mean(),
            lexicon_recall_pct=100 * g.lex_hits.sum() / max(1, g.lex_total.sum()),
            prompt_leak_case_pct=100 * (g.leak_ngrams > 0).mean(),
            flagged_case_pct=100 * ((g.flag_n + g.lowconf_n) > 0).mean(),
            latency_median_s=g.latency_s.median(), prompt_tokens=int(g.prompt_tokens.iloc[0]),
        ))
    return pd.DataFrame(rows)


def paired(df):
    piv = {m: df.pivot(index="case_id", columns="variant", values=m) for m in ("wer_a", "wer_b", "cer_case")}
    cats = df.drop_duplicates("case_id").set_index("case_id").category
    variants = list(piv["wer_b"].columns)
    out = []
    for ref in REFS:
        if ref not in variants:
            continue
        for v in variants:
            if v == ref or (v in REFS and REFS.index(v) < REFS.index(ref)):
                continue
            ok = piv["wer_b"][[ref, v]].dropna().index
            if len(ok) < 5:
                continue
            c = cats.loc[ok].to_numpy()
            r = {"ref": ref, "variant": v, "n": len(ok)}
            for m in ("wer_b", "wer_a"):
                d = (piv[m].loc[ok, v] - piv[m].loc[ok, ref]).to_numpy() * 100  # percentage points
                try:
                    p = stats.wilcoxon(d, zero_method="pratt").pvalue
                except ValueError:
                    p = 1.0
                lo, hi = strat_boot_ci(d, c)
                r.update({f"{m}_diff_pts": d.mean(), f"{m}_ci_lo": lo, f"{m}_ci_hi": hi, f"{m}_p": p})
            re_, ve_ = piv["cer_case"].loc[ok, ref].to_numpy(), piv["cer_case"].loc[ok, v].to_numpy()
            b, c_, p = mcnemar_exact(re_, ve_)
            r.update({"cer_ref_pct": 100 * re_.mean(), "cer_var_pct": 100 * ve_.mean(),
                      "mcnemar_b_fixed": b, "mcnemar_c_broken": c_, "cer_p": p})
            out.append(r)
    res = pd.DataFrame(out)
    for col in ("wer_b_p", "cer_p"):
        res[col + "_holm"] = holm(res[col].to_numpy())
    return res


def main(path):
    path = Path(path)
    df = pd.read_csv(path, keep_default_na=False)
    for c in ("wer_a", "wer_b", "cer_case", "S_a", "D_a", "I_a", "N_a", "S_b", "D_b", "I_b", "N_b",
              "n_omission", "n_commission", "crit_omission", "crit_commission", "lex_hits", "lex_total",
              "leak_ngrams", "flag_n", "lowconf_n", "latency_s", "prompt_tokens", "category"):
        df[c] = pd.to_numeric(df[c])
    # keep only cases that finished for every variant (paired analysis)
    complete = df.groupby("case_id").variant.nunique()
    full = complete[complete == df.variant.nunique()].index
    dropped = df.case_id.nunique() - len(full)
    if dropped:
        print(f"[note] dropping {dropped} cases not finished for all variants")
    df = df[df.case_id.isin(full)]

    s = summary(df)
    p = paired(df)
    s.to_csv(path.with_name(path.stem + "_summary.csv"), index=False)
    p.to_csv(path.with_name(path.stem + "_paired.csv"), index=False)
    pd.set_option("display.width", 220, "display.max_columns", 30)
    print(s.round(2).to_string(index=False))
    print()
    print(p.round(3).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
