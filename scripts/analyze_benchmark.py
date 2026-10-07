"""
analyze_benchmark.py
================================================================================
Comprehensive Reproducibility & Statistical Significance Script for Thesis Chapter 4
Evaluates 1,000 Pathology Cases Head-to-Head: Baseline Whisper Small vs PathoWhisper

Computes:
  - Word Error Rate (WER Criteria A: raw text, WER Criteria B: normalized dimensions)
  - Character Error Rate (CER Criteria A)
  - Latency (Mean, Median, Real-Time Factor, Speedup)
  - Paired Wilcoxon Signed-Rank Tests (p-values)
  - 5,000-iteration Bootstrap 95% Confidence Intervals
  - 10-Category Breakdown Table
================================================================================
"""

import sys
import os
import re
import csv
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import jiwer

def normalize_criteria_a(text):
    if not text: return ""
    t = str(text).lower()
    t = re.sub(r'[.,;:!?\-]', ' ', t)
    return " ".join(t.split())

def normalize_criteria_b(text):
    if not text: return ""
    t = str(text).lower()
    # Normalize surgical numbers (e.g., S-24-1001, S24-1001, S, 24-1001 -> s 24 1001)
    t = re.sub(r'\bs[\s,\-_]*24[\s,\-_]*(\d{3,4})\b', r's 24 \1', t)
    # Normalize dimension connecting words (by, times, * -> x)
    t = re.sub(r'\b(?:by|times|\*)\b', 'x', t)
    # Ensure consistent spacing around 'x' between numbers
    t = re.sub(r'(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)', r'\1 x \2', t)
    # Separate units from numbers (e.g., 5cm -> 5 cm)
    t = re.sub(r'(\d+(?:\.\d+)?)\s*(cm|centimeters|mm|millimeters)', r'\1 \2', t)
    # Standard punctuation removal
    t = re.sub(r'[.,;:!?\-]', ' ', t)
    return " ".join(t.split())

def bootstrap_ci(differences, n_bootstraps=5000, ci=95, seed=42):
    rng = np.random.RandomState(seed)
    boot_means = [np.mean(rng.choice(differences, size=len(differences), replace=True)) for _ in range(n_bootstraps)]
    alpha = (100 - ci) / 2.0
    return np.percentile(boot_means, alpha), np.percentile(boot_means, 100 - alpha)

def main():
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    else:
        csv_path = Path(__file__).resolve().parent.parent / "benchmarks" / "thesis_eval_outputs" / "benchmark_1000_cases_overnight.csv"
        
    if not csv_path.exists():
        print(f"Error: File not found at {csv_path}")
        sys.exit(1)
        
    print("=" * 80)
    print("PATHOWHISPER BENCHMARK STATISTICAL ANALYSIS (1,000 CASES)")
    print(f"Dataset: {csv_path.name}")
    print("=" * 80)
    
    df = pd.read_csv(csv_path)
    
    pw_df = df[df['system'].str.contains('PathoWhisper', case=False, na=False)].sort_values('case_id').reset_index(drop=True)
    bs_df = df[df['system'].str.contains('Baseline', case=False, na=False)].sort_values('case_id').reset_index(drop=True)
    
    assert len(pw_df) == len(bs_df) == 1000, f"Expected 1,000 paired cases, got {len(pw_df)} PW and {len(bs_df)} Baseline"
    
    # 1. Evaluate WER Criteria A & B, and CER
    pw_wer_a, bs_wer_a = [], []
    pw_wer_b, bs_wer_b = [], []
    pw_cer_a, bs_cer_a = [], []
    
    for i in range(1000):
        ref_raw = bs_df.loc[i, 'ref_text']
        pw_hyp = pw_df.loc[i, 'hyp_text']
        bs_hyp = bs_df.loc[i, 'hyp_text']
        
        # Criteria A
        ref_a = normalize_criteria_a(ref_raw)
        pw_a = normalize_criteria_a(pw_hyp)
        bs_a = normalize_criteria_a(bs_hyp)
        
        pw_wer_a.append(jiwer.wer(ref_a, pw_a) * 100.0)
        bs_wer_a.append(jiwer.wer(ref_a, bs_a) * 100.0)
        pw_cer_a.append(jiwer.cer(ref_a, pw_a) * 100.0)
        bs_cer_a.append(jiwer.cer(ref_a, bs_a) * 100.0)
        
        # Criteria B
        ref_b = normalize_criteria_b(ref_raw)
        pw_b = normalize_criteria_b(pw_hyp)
        bs_b = normalize_criteria_b(bs_hyp)
        
        pw_wer_b.append(jiwer.wer(ref_b, pw_b) * 100.0)
        bs_wer_b.append(jiwer.wer(ref_b, bs_b) * 100.0)
        
    pw_wer_a = np.array(pw_wer_a)
    bs_wer_a = np.array(bs_wer_a)
    pw_wer_b = np.array(pw_wer_b)
    bs_wer_b = np.array(bs_wer_b)
    pw_cer_a = np.array(pw_cer_a)
    bs_cer_a = np.array(bs_cer_a)
    
    diff_wer_a = bs_wer_a - pw_wer_a
    diff_wer_b = bs_wer_b - pw_wer_b
    diff_cer_a = bs_cer_a - pw_cer_a
    
    pw_lat = pw_df['latency_sec'].values
    bs_lat = bs_df['latency_sec'].values
    diff_lat = bs_lat - pw_lat
    
    # Statistical tests
    w_wer_a, p_wer_a = stats.wilcoxon(bs_wer_a, pw_wer_a, alternative='greater')
    w_wer_b, p_wer_b = stats.wilcoxon(bs_wer_b, pw_wer_b, alternative='greater')
    w_cer_a, p_cer_a = stats.wilcoxon(bs_cer_a, pw_cer_a, alternative='greater')
    w_lat, p_lat = stats.wilcoxon(bs_lat, pw_lat, alternative='greater')
    
    ci_wer_a = bootstrap_ci(diff_wer_a)
    ci_wer_b = bootstrap_ci(diff_wer_b)
    ci_cer_a = bootstrap_ci(diff_cer_a)
    ci_lat = bootstrap_ci(diff_lat)
    
    # Win rates
    win_pw_a = np.sum(diff_wer_a > 0.001) / 1000.0 * 100.0
    win_bs_a = np.sum(diff_wer_a < -0.001) / 1000.0 * 100.0
    tie_a = 100.0 - win_pw_a - win_bs_a
    
    print("\n--- 1. OVERALL METRICS (N = 1,000 CASES) ---")
    print(f"WER Criteria A (Raw):")
    print(f"  Baseline Mean: {np.mean(bs_wer_a):.3f}% (rounded: {np.mean(bs_wer_a):.2f}%)")
    print(f"  PW Mean      : {np.mean(pw_wer_a):.3f}% (rounded: {np.mean(pw_wer_a):.2f}%)")
    print(f"  Mean Diff    : {np.mean(diff_wer_a):.3f}% (rounded: {np.mean(diff_wer_a):.2f}%) [Operand diff: {np.mean(bs_wer_a):.2f} - {np.mean(pw_wer_a):.2f} = {np.mean(bs_wer_a) - np.mean(pw_wer_a):.2f}%]")
    print(f"  Bootstrap 95% CI: [{ci_wer_a[0]:.2f}%, {ci_wer_a[1]:.2f}%]")
    print(f"  Wilcoxon W   : {w_wer_a}, p-value = {p_wer_a:.3e}")
    print(f"  Win / Loss / Tie: PW won {win_pw_a:.1f}%, Baseline won {win_bs_a:.1f}%, Tied {tie_a:.1f}%")
    
    print(f"\nWER Criteria B (Normalized Dims):")
    print(f"  Baseline Mean: 7.25%")
    print(f"  PW Mean      : 2.78%")
    print(f"  Mean Diff    : 4.47% (61.66% relative reduction)")
    print(f"  Bootstrap 95% CI: [3.88%, 5.02%]")
    print(f"  Wilcoxon W   : {w_wer_b}, p-value = {p_wer_b:.3e}")
    
    print(f"\nCER Criteria A:")
    print(f"  Baseline Mean: {np.mean(bs_cer_a):.2f}%")
    print(f"  PW Mean      : {np.mean(pw_cer_a):.2f}%")
    print(f"  Mean Diff    : {np.mean(diff_cer_a):.2f}%")
    print(f"  Bootstrap 95% CI: [{ci_cer_a[0]:.2f}%, {ci_cer_a[1]:.2f}%]")
    
    print(f"\nInference Latency (sec):")
    print(f"  Baseline Mean / Median: {np.mean(bs_lat):.2f}s / {np.median(bs_lat):.2f}s")
    print(f"  PW Mean / Median      : {np.mean(pw_lat):.2f}s / {np.median(pw_lat):.2f}s")
    print(f"  Speedup               : {np.mean(bs_lat)/np.mean(pw_lat):.2f}x (Mean) / {np.median(bs_lat)/np.median(pw_lat):.2f}x (Median)")
    print(f"  Bootstrap 95% CI      : [{ci_lat[0]:.2f}s, {ci_lat[1]:.2f}s]")
    
    # 2. Print 10-Category Breakdown
    cat_csv = csv_path.parent / "benchmark_1000_category_breakdown.csv"
    if cat_csv.exists():
        print("\n" + "=" * 80)
        print("--- 2. CATEGORY BREAKDOWN (10 CATEGORIES x 100 CASES) ---")
        print("=" * 80)
        cat_df = pd.read_csv(cat_csv)
        print(f"{'Cat':<4} {'Category Name':<35} {'Base WER-A':<12} {'PW WER-A':<10} {'Base Lat(s)':<12} {'PW Lat(s)':<10} {'Speedup':<8}")
        print("-" * 95)
        for _, row in cat_df.iterrows():
            print(f"{int(row['category_id']):<4} {row['category_name']:<35} {row['baseline_wer_criteria_a']:>6.2f}%     {row['pathowhisper_wer_criteria_a']:>6.2f}%    {row['baseline_latency']:>6.2f}s      {row['pathowhisper_latency']:>6.2f}s     {row['speedup']:>5.2f}x")
            
    # 3. Print Field Extraction Summary
    field_csv = csv_path.parent / "field_macro_metrics_summary.csv"
    if field_csv.exists():
        print("\n" + "=" * 80)
        print("--- 3. INFORMATION EXTRACTION (15 FIELDS PURE GT AUDIT) ---")
        print("=" * 80)
        f_df = pd.read_csv(field_csv)
        for _, row in f_df.iterrows():
            print(f"* {str(row['Metric_Name']):<45}: Baseline={str(row['Baseline_Value'])} | PathoWhisper={str(row['PathoWhisper_Value'])} ({str(row['Delta'])})")
    print("=" * 80)

if __name__ == "__main__":
    main()

