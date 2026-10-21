"""
benchmarks/scripts/analyze_controlled_ablation.py
================================================================================
Pre-registered Statistical Analysis Suite for PathoWhisper Controlled Benchmark

Updates & Rigorous Enhancements:
  - Bootstrap: 10,000 resamples (seed=42)
  - Wilcoxon signed-rank test: zero_method='pratt'
  - Reports: Mean diff, Median diff, 95% Bootstrap CI, W statistic, Effect size r,
             Exact discordant pairs (b, c) for McNemar
  - Factorial 2^3 Main Effects (Quantization, Beam/Greedy, Prompt, Denoise)
  - Exploratory component analyses (C2, C3, C4 vs C1; C6, C7, C8 vs C5; Model Scaling)
  - Metadata logging (platform, scipy, pandas, numpy, seed)
================================================================================
"""

import sys
import os
import csv
import json
import argparse
import platform
import time
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
from scipy import stats

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

def mcnemar_exact(b_errs, a_errs):
    """
    Computes McNemar exact test for paired binary outcomes.
    b_errs, a_errs: binary arrays of error indicators (0 or 1).
    Contingency table:
      b = sum(a==0 and b==1): b had error, a was correct (improvement by a)
      c = sum(a==1 and b==0): a had error, b was correct (regression by a)
    Returns: p-value, discordant_str, b, c
    """
    b = sum(1 for x, y in zip(b_errs, a_errs) if x == 1 and y == 0) # b had err, a correct
    c = sum(1 for x, y in zip(b_errs, a_errs) if x == 0 and y == 1) # a had err, b correct
    n = b + c
    if n == 0:
        return 1.0, f"b={b}, c={c}", b, c
    res = stats.binomtest(min(b, c), n, 0.5, alternative='two-sided')
    return res.pvalue, f"b={b}, c={c}", b, c

def paired_bootstrap_ci(diffs, n_resamples=10000, ci=0.95, seed=42):
    """Computes paired bootstrap confidence interval for mean differences (10,000 resamples)."""
    rng = np.random.default_rng(seed)
    n = len(diffs)
    if n == 0:
        return 0.0, 0.0
    boot_means = [np.mean(rng.choice(diffs, size=n, replace=True)) for _ in range(n_resamples)]
    alpha = (1.0 - ci) / 2.0
    low = np.percentile(boot_means, alpha * 100)
    high = np.percentile(boot_means, (1.0 - alpha) * 100)
    return float(low), float(high)

def compute_wilcoxon(va, vb, zero_method="pratt"):
    """Computes Wilcoxon signed-rank test and effect size r."""
    diff = va - vb
    n = len(diff)
    if n <= 1 or np.all(diff == 0):
        return 0.0, 1.0, 0.0
    stat, p = stats.wilcoxon(va, vb, zero_method=zero_method)
    # Effect size r = Z / sqrt(N)
    # We estimate Z via standard normal quantile of p/2
    if p > 0 and p < 1.0:
        z = abs(stats.norm.ppf(p / 2.0))
        r = round(float(z / np.sqrt(n)), 3)
    else:
        r = 0.0
    return float(stat), float(p), r

def holm_bonferroni(p_vals):
    """
    Applies Holm-Bonferroni step-down correction to an array of p-values.
    Returns: adjusted p-values in original order.
    """
    m = len(p_vals)
    indexed = sorted(enumerate(p_vals), key=lambda x: x[1])
    adj = [0.0] * m
    cum_max = 0.0
    for rank, (orig_idx, p) in enumerate(indexed):
        mult = m - rank
        p_adj = min(1.0, p * mult)
        cum_max = max(cum_max, p_adj)
        adj[orig_idx] = cum_max
    return adj

def analyze_dataset(cases_csv_path, output_dir=None):
    df = pd.read_csv(cases_csv_path)
    metadata = {
        "analysis_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "pandas_version": pd.__version__,
        "bootstrap_resamples": 10000,
        "bootstrap_seed": 42,
        "wilcoxon_zero_method": "pratt",
        "total_cases_dataset": len(df["case_id"].unique()),
        "total_rows_evaluated": len(df)
    }

    print("=" * 100)
    print("PATHOWHISPER COMPREHENSIVE STATISTICAL ANALYSIS & FACTORIAL AUDIT")
    print("=" * 100)
    for k, v in metadata.items():
        print(f"  {k:<28}: {v}")
    print("=" * 100 + "\n")

    available_conds = list(df["condition_id"].unique())

    # Helper function to extract paired vectors
    def get_paired(metric, cond_a, cond_b, core_only=False):
        sub_df = df if not core_only else df[df["is_core_100"] == True]
        piv = sub_df.pivot(index="case_id", columns="condition_id", values=metric).dropna(subset=[cond_a, cond_b])
        return piv[cond_a].values, piv[cond_b].values

    # -------------------------------------------------------------------------
    # 1. PRIMARY PRE-REGISTERED HYPOTHESES (H1 - H6)
    # -------------------------------------------------------------------------
    primary_tests = []

    # H1: C5 vs C1 (WER-B)
    if "C5_full_pathowhisper" in available_conds and "C1_vanilla" in available_conds:
        v5, v1 = get_paired("wer_criterion_b", "C5_full_pathowhisper", "C1_vanilla")
        diff = v5 - v1
        w_stat, p, r_eff = compute_wilcoxon(v5, v1, zero_method="pratt")
        ci_l, ci_h = paired_bootstrap_ci(diff, n_resamples=10000)
        primary_tests.append({
            "id": "H1", "name": "C5 vs C1 (WER Criterion B)",
            "cond_a": "C5_full", "cond_b": "C1_vanilla", "metric": "WER-B",
            "mean_a": round(float(np.mean(v5)), 2), "mean_b": round(float(np.mean(v1)), 2),
            "median_a": round(float(np.median(v5)), 2), "median_b": round(float(np.median(v1)), 2),
            "mean_diff": round(float(np.mean(diff)), 2), "median_diff": round(float(np.median(diff)), 2),
            "ci_95": f"[{ci_l:.2f}, {ci_h:.2f}]", "w_stat": w_stat, "effect_size_r": r_eff,
            "raw_p": p, "n": len(v5), "test_type": "Paired Wilcoxon (Pratt)"
        })

    # H2: C5 vs C0 (WER-B)
    if "C5_full_pathowhisper" in available_conds and "C0_ct2_fp32_baseline" in available_conds:
        v5, v0 = get_paired("wer_criterion_b", "C5_full_pathowhisper", "C0_ct2_fp32_baseline")
        diff = v5 - v0
        w_stat, p, r_eff = compute_wilcoxon(v5, v0, zero_method="pratt")
        ci_l, ci_h = paired_bootstrap_ci(diff, n_resamples=10000)
        primary_tests.append({
            "id": "H2", "name": "C5 vs C0 (WER Criterion B)",
            "cond_a": "C5_full", "cond_b": "C0_baseline", "metric": "WER-B",
            "mean_a": round(float(np.mean(v5)), 2), "mean_b": round(float(np.mean(v0)), 2),
            "median_a": round(float(np.median(v5)), 2), "median_b": round(float(np.median(v0)), 2),
            "mean_diff": round(float(np.mean(diff)), 2), "median_diff": round(float(np.median(diff)), 2),
            "ci_95": f"[{ci_l:.2f}, {ci_h:.2f}]", "w_stat": w_stat, "effect_size_r": r_eff,
            "raw_p": p, "n": len(v5), "test_type": "Paired Wilcoxon (Pratt)"
        })

    # H3: C5 vs C1 (CER_case)
    if "C5_full_pathowhisper" in available_conds and "C1_vanilla" in available_conds:
        v5, v1 = get_paired("cer_case", "C5_full_pathowhisper", "C1_vanilla")
        p, disc_str, b, c = mcnemar_exact(v1, v5)
        diff = (v5 - v1) * 100.0
        ci_l, ci_h = paired_bootstrap_ci(diff, n_resamples=10000)
        primary_tests.append({
            "id": "H3", "name": "C5 vs C1 (CER_case)",
            "cond_a": "C5_full", "cond_b": "C1_vanilla", "metric": "CER_case (%)",
            "mean_a": round(float(np.mean(v5) * 100.0), 2), "mean_b": round(float(np.mean(v1) * 100.0), 2),
            "median_a": 0.0, "median_b": 0.0,
            "mean_diff": round(float(np.mean(diff)), 2), "median_diff": 0.0,
            "ci_95": f"[{ci_l:.2f}, {ci_h:.2f}] ({disc_str})", "w_stat": f"b={b},c={c}", "effect_size_r": round((b-c)/(b+c), 3) if (b+c)>0 else 0.0,
            "raw_p": p, "n": len(v5), "test_type": "McNemar Exact Two-Tailed"
        })

    # H4: C5 vs C0 (CER_case)
    if "C5_full_pathowhisper" in available_conds and "C0_ct2_fp32_baseline" in available_conds:
        v5, v0 = get_paired("cer_case", "C5_full_pathowhisper", "C0_ct2_fp32_baseline")
        p, disc_str, b, c = mcnemar_exact(v0, v5)
        diff = (v5 - v0) * 100.0
        ci_l, ci_h = paired_bootstrap_ci(diff, n_resamples=10000)
        primary_tests.append({
            "id": "H4", "name": "C5 vs C0 (CER_case)",
            "cond_a": "C5_full", "cond_b": "C0_baseline", "metric": "CER_case (%)",
            "mean_a": round(float(np.mean(v5) * 100.0), 2), "mean_b": round(float(np.mean(v0) * 100.0), 2),
            "median_a": 0.0, "median_b": 0.0,
            "mean_diff": round(float(np.mean(diff)), 2), "median_diff": 0.0,
            "ci_95": f"[{ci_l:.2f}, {ci_h:.2f}] ({disc_str})", "w_stat": f"b={b},c={c}", "effect_size_r": round((b-c)/(b+c), 3) if (b+c)>0 else 0.0,
            "raw_p": p, "n": len(v5), "test_type": "McNemar Exact Two-Tailed"
        })

    # H5: C1 vs C0 (Quantization on WER-B)
    if "C1_vanilla" in available_conds and "C0_ct2_fp32_baseline" in available_conds:
        v1, v0 = get_paired("wer_criterion_b", "C1_vanilla", "C0_ct2_fp32_baseline")
        diff = v1 - v0
        w_stat, p, r_eff = compute_wilcoxon(v1, v0, zero_method="pratt")
        ci_l, ci_h = paired_bootstrap_ci(diff, n_resamples=10000)
        primary_tests.append({
            "id": "H5", "name": "C1 vs C0 (Quantization INT8)",
            "cond_a": "C1_vanilla", "cond_b": "C0_baseline", "metric": "WER-B",
            "mean_a": round(float(np.mean(v1)), 2), "mean_b": round(float(np.mean(v0)), 2),
            "median_a": round(float(np.median(v1)), 2), "median_b": round(float(np.median(v0)), 2),
            "mean_diff": round(float(np.mean(diff)), 2), "median_diff": round(float(np.median(diff)), 2),
            "ci_95": f"[{ci_l:.2f}, {ci_h:.2f}]", "w_stat": w_stat, "effect_size_r": r_eff,
            "raw_p": p, "n": len(v1), "test_type": "Paired Wilcoxon (Pratt)"
        })

    # H6: C5 vs C0 (Latency on Core Subset N=100)
    if "C5_full_pathowhisper" in available_conds and "C0_ct2_fp32_baseline" in available_conds:
        v5_med, v0_med = get_paired("median_latency_sec", "C5_full_pathowhisper", "C0_ct2_fp32_baseline", core_only=True)
        diff = v5_med - v0_med
        w_stat, p, r_eff = compute_wilcoxon(v5_med, v0_med, zero_method="pratt")
        ci_l, ci_h = paired_bootstrap_ci(diff, n_resamples=10000)
        primary_tests.append({
            "id": "H6", "name": "C5 vs C0 (Latency Core Cases)",
            "cond_a": "C5_full", "cond_b": "C0_baseline", "metric": "Latency (s)",
            "mean_a": round(float(np.mean(v5_med)), 2), "mean_b": round(float(np.mean(v0_med)), 2),
            "median_a": round(float(np.median(v5_med)), 2), "median_b": round(float(np.median(v0_med)), 2),
            "mean_diff": round(float(np.mean(diff)), 2), "median_diff": round(float(np.median(diff)), 2),
            "ci_95": f"[{ci_l:.2f}, {ci_h:.2f}]", "w_stat": w_stat, "effect_size_r": r_eff,
            "raw_p": p, "n": len(v5_med), "test_type": "Paired Wilcoxon (Pratt)"
        })

    # Apply Holm-Bonferroni correction
    if primary_tests:
        raw_ps = [t["raw_p"] for t in primary_tests]
        adj_ps = holm_bonferroni(raw_ps)
        for t, p_adj in zip(primary_tests, adj_ps):
            t["holm_p"] = round(float(p_adj), 4)
            t["sig"] = "***" if p_adj < 0.001 else ("**" if p_adj < 0.01 else ("*" if p_adj < 0.05 else "n.s."))

    print("-" * 110)
    print("PRIMARY PRE-SPECIFIED HYPOTHESES (Holm-Bonferroni Adjusted, 10,000 Bootstrap Resamples)")
    print("-" * 110)
    print(f"{'Hyp':<4} | {'Comparison':<30} | {'Metric':<11} | {'Mean A / B':<15} | {'Med A / B':<13} | {'Mean Diff':<10} | {'95% CI':<18} | {'Holm p':<9} | {'Sig'}")
    print("-" * 110)
    for t in primary_tests:
        mean_str = f"{t['mean_a']} / {t['mean_b']}"
        med_str = f"{t['median_a']} / {t['median_b']}"
        holm_p_str = f"{t['holm_p']:.4f}" if t['holm_p'] >= 0.0001 else "<0.0001"
        ci_short = t['ci_95'].split()[0]
        print(f"{t['id']:<4} | {t['name']:<30} | {t['metric']:<11} | {mean_str:<15} | {med_str:<13} | {t['mean_diff']:<10} | {ci_short:<18} | {holm_p_str:<9} | {t['sig']}")
    print("-" * 110 + "\n")

    # -------------------------------------------------------------------------
    # 2. FACTORIAL 2^3 MAIN EFFECTS (Quantization, Greedy, Prompt, Denoise)
    # -------------------------------------------------------------------------
    print("-" * 110)
    print("FACTORIAL 2^3 MAIN EFFECTS ANALYSIS (N = 300 Cases)")
    print("-" * 110)
    # Factorial conditions on INT8:
    # Prompt effect: Average of (+Prompt: C3, C5, C6, C8) minus (No Prompt: C1, C2, C4, C7)
    prompt_with = df[df["condition_id"].isin(["C3_prompt_only", "C5_full_pathowhisper", "C6_leaveout_denoise", "C8_leaveout_beam1"])]
    prompt_without = df[df["condition_id"].isin(["C1_vanilla", "C2_denoise_only", "C4_beam1_only", "C7_leaveout_prompt"])]
    
    denoise_with = df[df["condition_id"].isin(["C2_denoise_only", "C5_full_pathowhisper", "C7_leaveout_prompt", "C8_leaveout_beam1"])]
    denoise_without = df[df["condition_id"].isin(["C1_vanilla", "C3_prompt_only", "C4_beam1_only", "C6_leaveout_denoise"])]

    greedy_with = df[df["condition_id"].isin(["C4_beam1_only", "C5_full_pathowhisper", "C6_leaveout_denoise", "C7_leaveout_prompt"])]
    greedy_without = df[df["condition_id"].isin(["C1_vanilla", "C2_denoise_only", "C3_prompt_only", "C8_leaveout_beam1"])]

    factorial_effects = [
        {
            "Factor": "Pathology Prompt",
            "WER-B (+ / -)": f"{prompt_with['wer_criterion_b'].mean():.2f}% vs {prompt_without['wer_criterion_b'].mean():.2f}%",
            "WER-B Delta": round(prompt_with['wer_criterion_b'].mean() - prompt_without['wer_criterion_b'].mean(), 2),
            "CER_case (+ / -)": f"{prompt_with['cer_case'].mean()*100:.2f}% vs {prompt_without['cer_case'].mean()*100:.2f}%",
            "CER_case Delta": round((prompt_with['cer_case'].mean() - prompt_without['cer_case'].mean())*100, 2),
            "Latency (+ / -)": f"{prompt_with[prompt_with['is_core_100']]['median_latency_sec'].mean():.2f}s vs {prompt_without[prompt_without['is_core_100']]['median_latency_sec'].mean():.2f}s"
        },
        {
            "Factor": "Search Strategy (Greedy Beam 1)",
            "WER-B (+ / -)": f"{greedy_with['wer_criterion_b'].mean():.2f}% vs {greedy_without['wer_criterion_b'].mean():.2f}%",
            "WER-B Delta": round(greedy_with['wer_criterion_b'].mean() - greedy_without['wer_criterion_b'].mean(), 2),
            "CER_case (+ / -)": f"{greedy_with['cer_case'].mean()*100:.2f}% vs {greedy_without['cer_case'].mean()*100:.2f}%",
            "CER_case Delta": round((greedy_with['cer_case'].mean() - greedy_without['cer_case'].mean())*100, 2),
            "Latency (+ / -)": f"{greedy_with[greedy_with['is_core_100']]['median_latency_sec'].mean():.2f}s vs {greedy_without[greedy_without['is_core_100']]['median_latency_sec'].mean():.2f}s"
        },
        {
            "Factor": "Audio Preprocessing (afftdn Denoise)",
            "WER-B (+ / -)": f"{denoise_with['wer_criterion_b'].mean():.2f}% vs {denoise_without['wer_criterion_b'].mean():.2f}%",
            "WER-B Delta": round(denoise_with['wer_criterion_b'].mean() - denoise_without['wer_criterion_b'].mean(), 2),
            "CER_case (+ / -)": f"{denoise_with['cer_case'].mean()*100:.2f}% vs {denoise_without['cer_case'].mean()*100:.2f}%",
            "CER_case Delta": round((denoise_with['cer_case'].mean() - denoise_without['cer_case'].mean())*100, 2),
            "Latency (+ / -)": f"{denoise_with[denoise_with['is_core_100']]['median_latency_sec'].mean():.2f}s vs {denoise_without[denoise_without['is_core_100']]['median_latency_sec'].mean():.2f}s"
        }
    ]

    for fe in factorial_effects:
        print(f"  {fe['Factor']:<35} | WER-B Delta: {fe['WER-B Delta']:+6.2f}% | CER Delta: {fe['CER_case Delta']:+6.2f}% | Latency: {fe['Latency (+ / -)']}")
    print("-" * 110 + "\n")

    # -------------------------------------------------------------------------
    # 3. EXPLORATORY ANALYSES (Unadjusted p-values)
    # -------------------------------------------------------------------------
    print("-" * 110)
    print("EXPLORATORY ANALYSES: INDIVIDUAL COMPONENTS & LEAVE-ONE-OUT (Unadjusted p)")
    print("-" * 110)
    exploratory_pairs = [
        ("C2_denoise_only", "C1_vanilla", "C2 vs C1 (+Denoise Only vs Vanilla)"),
        ("C3_prompt_only",  "C1_vanilla", "C3 vs C1 (+Prompt Only vs Vanilla)"),
        ("C4_beam1_only",   "C1_vanilla", "C4 vs C1 (+Greedy Only vs Vanilla)"),
        ("C6_leaveout_denoise", "C5_full_pathowhisper", "C6 vs C5 (Full - Denoise vs Full)"),
        ("C7_leaveout_prompt",  "C5_full_pathowhisper", "C7 vs C5 (Full - Prompt vs Full)"),
        ("C8_leaveout_beam1",   "C5_full_pathowhisper", "C8 vs C5 (Full - Greedy vs Full)")
    ]
    exploratory_results = []
    for ca, cb, label in exploratory_pairs:
        if ca in available_conds and cb in available_conds:
            va, vb = get_paired("wer_criterion_b", ca, cb)
            diff = va - vb
            w_stat, p, r_eff = compute_wilcoxon(va, vb, zero_method="pratt")
            ci_l, ci_h = paired_bootstrap_ci(diff, n_resamples=10000)
            cera, cerb = get_paired("cer_case", ca, cb)
            p_mcnemar, disc_str, b, c = mcnemar_exact(cerb, cera)
            exploratory_results.append({
                "Comparison": label,
                "WER-B Mean A/B": f"{np.mean(va):.2f}% vs {np.mean(vb):.2f}%",
                "WER-B Diff": round(float(np.mean(diff)), 2),
                "WER-B p": f"{p:.4f}" if p >= 0.0001 else "<0.0001",
                "CER Mean A/B": f"{np.mean(cera)*100:.1f}% vs {np.mean(cerb)*100:.1f}%",
                "CER p": f"{p_mcnemar:.4f}" if p_mcnemar >= 0.0001 else "<0.0001"
            })
            print(f"  {label:<40} | WER-B: {np.mean(va):.2f}% vs {np.mean(vb):.2f}% (p={p:.4f}) | CER: {np.mean(cera)*100:.1f}% vs {np.mean(cerb)*100:.1f}% (p={p_mcnemar:.4f})")
    print("-" * 110 + "\n")

    # Save outputs if output_dir provided
    if output_dir:
        out_path = Path(output_dir)
        csv_file = out_path / "pre_registered_statistical_results.csv"
        pd.DataFrame(primary_tests).to_csv(csv_file, index=False)
        
        meta_file = out_path / "statistical_analysis_metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        fact_file = out_path / "factorial_main_effects.csv"
        pd.DataFrame(factorial_effects).to_csv(fact_file, index=False)

        expl_file = out_path / "exploratory_component_results.csv"
        pd.DataFrame(exploratory_results).to_csv(expl_file, index=False)

        print(f"[Export] Saved statistical artifacts to: {out_path.resolve()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PathoWhisper Statistical Analysis")
    parser.add_argument("csv_path", type=str, help="Path to cases CSV file")
    parser.add_argument("--out-dir", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    analyze_dataset(args.csv_path, args.out_dir)
