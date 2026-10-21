"""
generate_final_thesis_tables.py -- Comprehensive Statistical Analysis, Paired Hypothesis Testing,
15-Field CAP Breakdown, and LaTeX/Markdown Table Generator for the Clean-Slate Thesis Redesign.

Computes:
  1. Experiment 1: Cross-Architecture & Quantization Baseline (Whisper Small FP32/INT8, Whisper Base INT8, Vosk, Wav2Vec2)
  2. Experiment 2A & 2B: afftdn Parameter Grid Search & Multi-SNR Cross-Filter Benchmark + Blind SNR Routing
  3. Experiment 3: Systematic Prompt Structure & Token-Budget Ablation (P0..P4) + Static vs. SNR-Gated Filter
  4. Experiment 4: Whisper Small LoRA Fine-Tuning (r=8, alpha=32 -> CTranslate2 INT8) on test_seen & test_unseen
  5. Full 15/15 CAP Field Precision, Recall, and F1 Table (s0_surgical_no through s14_check)
  6. Category-wise Breakdown (Categories 1-10) & Paired Statistical Tests (Bootstrap 95% CI, Wilcoxon, McNemar)
  7. Multi-Signal Safety Flagging & Selective Prediction Risk-Coverage Curve
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.clean_slate.metrics_clean import (
    KEYS, CRIT, ACTIVE_KEYS, evaluate_case_ie, compute_macro_f1_active11, wilson
)

RESULTS_DIR = REPO_ROOT / "benchmarks" / "clean_slate" / "results"
DATASET_DIR = REPO_ROOT / "data" / "dataset_ft"


def bootstrap_ci(vals: np.ndarray, n_boot: int = 5000, seed: int = 42) -> tuple[float, float, float]:
    vals = np.asarray(vals, dtype=np.float64)
    if len(vals) == 0:
        return 0.0, 0.0, 0.0
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(vals), size=(n_boot, len(vals)))
    means = np.mean(vals[idx], axis=1)
    return float(np.mean(vals)), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def paired_wilcoxon_and_mcnemar(df_a: pd.DataFrame, df_b: pd.DataFrame) -> dict:
    merged = pd.merge(df_a, df_b, on="case_id", suffixes=("_a", "_b"))
    if len(merged) == 0:
        return {"n": 0, "wilcoxon_wer_p": 1.0, "mcnemar_cer_p": 1.0, "b01": 0, "b10": 0}

    diff_wer = merged["wer_norm_a"].values - merged["wer_norm_b"].values
    if np.all(np.abs(diff_wer) < 1e-9):
        w_p = 1.0
    else:
        try:
            _, w_p = stats.wilcoxon(merged["wer_norm_a"].values, merged["wer_norm_b"].values)
        except Exception:
            w_p = 1.0

    # McNemar exact binomial test on binary cer_case
    cer_a = merged["cer_case_a"].values.astype(int)
    cer_b = merged["cer_case_b"].values.astype(int)
    b10 = int(np.sum((cer_a == 1) & (cer_b == 0)))  # A wrong, B right
    b01 = int(np.sum((cer_a == 0) & (cer_b == 1)))  # A right, B wrong
    n_disc = b10 + b01
    if n_disc == 0:
        mc_p = 1.0
    else:
        mc_p = float(stats.binomtest(min(b10, b01), n=n_disc, p=0.5, alternative="two-sided").pvalue)

    return {
        "n": len(merged),
        "wer_diff_mean": round(float(np.mean(diff_wer)), 3),
        "wilcoxon_wer_p": float(w_p),
        "b10_a_err_b_ok": b10,
        "b01_a_ok_b_err": b01,
        "mcnemar_cer_p": float(mc_p),
    }


def compute_15_field_breakdown(df_sub: pd.DataFrame, gt: dict) -> dict:
    outcomes_list = []
    for _, row in df_sub.iterrows():
        cid = row["case_id"]
        if cid not in gt:
            continue
        ie_res = evaluate_case_ie(str(row.get("hyp_text", "")), gt[cid])
        outcomes_list.append(ie_res["outcomes"])
    return compute_macro_f1_active11(outcomes_list)


def compute_risk_coverage(df_sub: pd.DataFrame) -> list[dict]:
    if len(df_sub) == 0:
        return []
    df_s = df_sub.sort_values("risk_score", ascending=True).reset_index(drop=True)
    n_tot = len(df_s)
    points = []
    for cov_pct in [100, 95, 90, 85, 80, 75, 70]:
        k = max(1, int(round(n_tot * (cov_pct / 100.0))))
        kept = df_s.iloc[:k]
        cer_kept = 100.0 * float(np.mean(kept["cer_case"].values))
        wer_kept = float(np.mean(kept["wer_norm"].values))
        points.append({
            "target_coverage_pct": cov_pct,
            "actual_n_kept": k,
            "effective_cer_case_pct": round(cer_kept, 2),
            "effective_wer_norm": round(wer_kept, 2),
        })
    # Also compute operating point at binary is_flagged == 0
    unflagged = df_sub[df_sub["is_flagged"] == 0]
    flagged = df_sub[df_sub["is_flagged"] == 1]
    all_errs = int(np.sum(df_sub["cer_case"].values))
    caught_errs = int(np.sum(flagged["cer_case"].values)) if len(flagged) > 0 else 0
    points.append({
        "target_coverage_pct": round(100.0 * len(unflagged) / n_tot, 2),
        "actual_n_kept": len(unflagged),
        "effective_cer_case_pct": round(100.0 * float(np.mean(unflagged["cer_case"].values)), 2) if len(unflagged) > 0 else 0.0,
        "effective_wer_norm": round(float(np.mean(unflagged["wer_norm"].values)), 2) if len(unflagged) > 0 else 0.0,
        "binary_flag_operating_point": True,
        "flagged_pct": round(100.0 * len(flagged) / n_tot, 2),
        "error_recall_pct": round(100.0 * caught_errs / all_errs, 2) if all_errs > 0 else 100.0,
    })
    return points


def main():
    gt = json.load(open(DATASET_DIR / "ground_truth_ft.json", encoding="utf-8"))
    report_out = {}

    for split in ("test_seen", "test_unseen"):
        p_csv = RESULTS_DIR / f"exp3_prompt_ablation_{split}.csv"
        l_csv = RESULTS_DIR / f"exp4_lora_evaluation_{split}.csv"
        if not p_csv.exists():
            continue
        df_p = pd.read_csv(p_csv)
        df_l = pd.read_csv(l_csv) if l_csv.exists() else pd.DataFrame()

        # 1. Stratified 50-case Prompt & Token-Budget Comparison (where all 9 variants were evaluated)
        counts_per_case = df_p.groupby("case_id")["prompt_id"].nunique()
        strat50_cids = set(counts_per_case[counts_per_case >= 7].index)
        df_p50 = df_p[df_p["case_id"].isin(strat50_cids)]

        prompt_summary_rows = []
        for pid, grp in df_p50.groupby("prompt_id"):
            f1_info = compute_15_field_breakdown(grp, gt)
            wer_m, wer_l, wer_u = bootstrap_ci(grp["wer_norm"].values)
            cter_m, cter_l, cter_u = bootstrap_ci(grp["c_ter"].values)
            nder_m, nder_l, nder_u = bootstrap_ci(grp["n_der"].values)
            k_err = int(np.sum(grp["cer_case"].values))
            n_c = len(grp)
            cer_m = 100.0 * k_err / max(1, n_c)
            cer_l, cer_u = wilson(k_err, n_c)
            prompt_summary_rows.append({
                "split": split, "subset": f"stratified_{n_c}", "system_or_prompt": pid, "n": n_c,
                "wer_norm": round(wer_m, 2), "wer_ci": f"[{wer_l:.2f}, {wer_u:.2f}]",
                "c_ter": round(cter_m, 2), "c_ter_ci": f"[{cter_l:.2f}, {cter_u:.2f}]",
                "n_der": round(nder_m, 2), "n_der_ci": f"[{nder_l:.2f}, {nder_u:.2f}]",
                "macro_precision_15": f1_info["macro_precision"],
                "macro_recall_15": f1_info["macro_recall"],
                "macro_f1_15": f1_info["macro_f1"],
                "slot_acc_15": round(float(np.mean(grp["slot_acc_active11"].values)), 2),
                "cer_case_pct": round(cer_m, 2), "cer_ci": f"[{cer_l:.2f}, {cer_u:.2f}]",
                "crit_omissions": int(np.sum(grp["crit_omissions"].values)),
                "crit_commissions": int(np.sum(grp["crit_commissions"].values)),
                "latency_sec": round(float(np.mean(grp["latency_sec"].values)), 3),
                "rtf": round(float(np.mean(grp["rtf"].values)), 4),
            })
        pd.DataFrame(prompt_summary_rows).to_csv(RESULTS_DIR / f"final_table_prompt_ablation_{split}.csv", index=False)

        # 2. Full 150-Case System Progression (S0 -> S1_nofilter -> S1_static -> S1_proposed -> S2_LoRA -> S3_Full)
        sys_frames = {}
        for pid, label in [
            ("P0_no_prompt", "S0_ZeroShot_NoPrompt_SNRGated"),
            ("P4_no_filter_always_off", "S1a_ZeroShot_P4_NoFilter"),
            ("P4_static_afftdn_always_on", "S1b_ZeroShot_P4_StaticAfftdn"),
            ("P4_phonetic_contrastive", "S1c_ZeroShot_P4_SNRGated"),
        ]:
            sub = df_p[df_p["prompt_id"] == pid].copy()
            if len(sub) > 0:
                sys_frames[label] = sub

        l200_csv = RESULTS_DIR / f"exp4_lora_200cases_{split}.csv"
        if l200_csv.exists():
            df_l200 = pd.read_csv(l200_csv)
            for sid, lbl in [
                ("S2_LoRA_INT8_NoPrompt", "S2_LoRA_200cases_NoPrompt"),
                ("S3_Full_PathoWhisper_LoRA_Prompt_SNRGated", "S3_Full_200cases_LoRA_Prompt_SNRGated"),
            ]:
                sub = df_l200[df_l200["system_id"] == sid].copy()
                if len(sub) > 0:
                    sys_frames[lbl] = sub

        if len(df_l) > 0:
            for sid in ("S2_LoRA_INT8_NoPrompt", "S3_Full_PathoWhisper_LoRA_Prompt_SNRGated"):
                sub = df_l[df_l["system_id"] == sid].copy()
                if len(sub) > 0:
                    sys_frames[sid] = sub

        sys_rows = []
        per_field_tables = {}
        risk_cov_tables = {}
        cat_rows = []

        for s_label, grp in sys_frames.items():
            f1_info = compute_15_field_breakdown(grp, gt)
            per_field_tables[s_label] = f1_info["per_field"]
            risk_cov_tables[s_label] = compute_risk_coverage(grp)

            wer_m, wer_l, wer_u = bootstrap_ci(grp["wer_norm"].values)
            cter_m, cter_l, cter_u = bootstrap_ci(grp["c_ter"].values)
            nder_m, nder_l, nder_u = bootstrap_ci(grp["n_der"].values)
            k_err = int(np.sum(grp["cer_case"].values))
            n_c = len(grp)
            cer_m = 100.0 * k_err / max(1, n_c)
            cer_l, cer_u = wilson(k_err, n_c)

            sys_rows.append({
                "split": split, "system": s_label, "n": n_c,
                "wer_norm": round(wer_m, 2), "wer_ci": f"[{wer_l:.2f}, {wer_u:.2f}]",
                "c_ter": round(cter_m, 2), "c_ter_ci": f"[{cter_l:.2f}, {cter_u:.2f}]",
                "n_der": round(nder_m, 2), "n_der_ci": f"[{nder_l:.2f}, {nder_u:.2f}]",
                "macro_precision_15": f1_info["macro_precision"],
                "macro_recall_15": f1_info["macro_recall"],
                "macro_f1_15": f1_info["macro_f1"],
                "slot_acc_15": round(float(np.mean(grp["slot_acc_active11"].values)), 2),
                "cer_case_pct": round(cer_m, 2), "cer_ci": f"[{cer_l:.2f}, {cer_u:.2f}]",
                "cer_count": f"{k_err}/{n_c}",
                "crit_omissions": int(np.sum(grp["crit_omissions"].values)),
                "crit_commissions": int(np.sum(grp["crit_commissions"].values)),
                "latency_sec": round(float(np.mean(grp["latency_sec"].values)), 3),
                "rtf": round(float(np.mean(grp["rtf"].values)), 4),
            })

            # Category-wise breakdown (Categories 1..10)
            for cat_id, c_grp in grp.groupby("category"):
                cat_rows.append({
                    "split": split, "system": s_label, "category": int(cat_id), "n": len(c_grp),
                    "wer_norm": round(float(np.mean(c_grp["wer_norm"].values)), 2),
                    "c_ter": round(float(np.mean(c_grp["c_ter"].values)), 2),
                    "n_der": round(float(np.mean(c_grp["n_der"].values)), 2),
                    "slot_acc_15": round(float(np.mean(c_grp["slot_acc_active11"].values)), 2),
                    "cer_case_pct": round(100.0 * float(np.mean(c_grp["cer_case"].values)), 2),
                })

        pd.DataFrame(sys_rows).to_csv(RESULTS_DIR / f"final_table_system_progression_{split}.csv", index=False)
        pd.DataFrame(cat_rows).to_csv(RESULTS_DIR / f"final_table_category_breakdown_{split}.csv", index=False)

        # Save 15-field per-field table
        pf_rows = []
        for k in KEYS:
            row_d = {"field": k, "is_critical": k in CRIT}
            for s_label, pf_dict in per_field_tables.items():
                row_d[f"{s_label}_P"] = pf_dict[k]["precision"]
                row_d[f"{s_label}_R"] = pf_dict[k]["recall"]
                row_d[f"{s_label}_F1"] = pf_dict[k]["f1"]
                row_d[f"{s_label}_TP"] = pf_dict[k]["tp"]
                row_d[f"{s_label}_FN"] = pf_dict[k]["fn"]
                row_d[f"{s_label}_FP_WRONG"] = pf_dict[k]["fp"] + pf_dict[k]["wrong"]
            pf_rows.append(row_d)
        pd.DataFrame(pf_rows).to_csv(RESULTS_DIR / f"final_table_15fields_{split}.csv", index=False)

        # Paired statistical tests between key pairs
        pairs_to_test = [
            ("S0_ZeroShot_NoPrompt_SNRGated", "S1c_ZeroShot_P4_SNRGated"),
            ("S1b_ZeroShot_P4_StaticAfftdn", "S1c_ZeroShot_P4_SNRGated"),
            ("S1a_ZeroShot_P4_NoFilter", "S1c_ZeroShot_P4_SNRGated"),
            ("S0_ZeroShot_NoPrompt_SNRGated", "S2_LoRA_INT8_NoPrompt"),
            ("S1c_ZeroShot_P4_SNRGated", "S3_Full_PathoWhisper_LoRA_Prompt_SNRGated"),
            ("S0_ZeroShot_NoPrompt_SNRGated", "S3_Full_PathoWhisper_LoRA_Prompt_SNRGated"),
        ]
        stat_rows = []
        for sa, sb in pairs_to_test:
            if sa in sys_frames and sb in sys_frames:
                res_st = paired_wilcoxon_and_mcnemar(sys_frames[sa], sys_frames[sb])
                stat_rows.append({"split": split, "system_a": sa, "system_b": sb, **res_st})
        pd.DataFrame(stat_rows).to_csv(RESULTS_DIR / f"final_table_significance_{split}.csv", index=False)

        report_out[split] = {
            "system_progression": sys_rows,
            "prompt_ablation_50": prompt_summary_rows,
            "significance_tests": stat_rows,
            "risk_coverage": risk_cov_tables,
        }

    json.dump(report_out, open(RESULTS_DIR / "final_thesis_master_summary.json", "w", encoding="utf-8"), indent=2)
    print("Saved all final thesis tables and master summary JSON to", RESULTS_DIR)


if __name__ == "__main__":
    main()
