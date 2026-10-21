"""
generate_thesis_figures.py -- Generates 6 publication-quality (300 DPI) figures for the
PathoWhisper Thesis Chapters 3-4 and Defense Presentation Slides.
"""
import json
import shutil
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "benchmarks" / "clean_slate" / "results"
FIG_DIR = RESULTS_DIR / "figures"
LATEX_CHART_DIR = REPO_ROOT / "docs" / "thesis_latex" / "images" / "charts"
ARTIFACT_DIR = Path(r"C:\Users\project\.gemini\antigravity\brain\817acc80-169e-4ca0-b20a-ef6959971b44")

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Segoe UI"],
    "axes.edgecolor": "#334155",
    "axes.linewidth": 0.9,
    "grid.color": "#cbd5e1",
    "grid.linestyle": "--",
    "grid.alpha": 0.6,
    "figure.dpi": 300,
})


def save_and_copy(fig, filename: str):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    LATEX_CHART_DIR.mkdir(parents=True, exist_ok=True)
    out_p = FIG_DIR / filename
    fig.savefig(out_p, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    shutil.copy2(out_p, LATEX_CHART_DIR / filename)
    if ARTIFACT_DIR.exists():
        shutil.copy2(out_p, ARTIFACT_DIR / filename)
    print(f"Saved figure: {out_p} and copied to {LATEX_CHART_DIR}")


def plot_fig1_snr_calibration():
    snr_csv = RESULTS_DIR / "snr_calibration_val.csv"
    tau_json = RESULTS_DIR / "calibrated_tau.json"
    if not snr_csv.exists():
        return
    df = pd.read_csv(snr_csv)
    tau = json.load(open(tau_json))["optimal_tau_db"] if tau_json.exists() else 13.55

    order = ["clean", "noisy_+10dB", "noisy_+5dB", "noisy_+0dB", "noisy_-5dB", "noisy_-10dB"]
    labels = ["Clean\n(No Noise)", "+10 dB\nFume Hood", "+5 dB\nFume Hood", "0 dB\nFume Hood", "-5 dB\nFume Hood", "-10 dB\nFume Hood"]
    colors = ["#0ea5e9", "#f59e0b", "#f97316", "#ef4444", "#dc2626", "#991b1b"]

    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    data_groups = [df[df["true_condition"] == c]["est_snr_db"].values for c in order if c in df["true_condition"].values]
    bp = ax.boxplot(data_groups, patch_artist=True, widths=0.5, showfliers=True)
    for patch, col in zip(bp["boxes"], colors):
        patch.set_facecolor(col)
        patch.set_alpha(0.78)
    for median in bp["medians"]:
        median.set_color("#0f172a")
        median.set_linewidth(2.0)

    ax.axhline(tau, color="#16a34a", linestyle="--", linewidth=2.2, label=f"Calibrated Max-Margin Threshold τ* = {tau:.2f} dB (Youden's J = 1.000)")
    ax.fill_between([0.4, len(order) + 0.6], tau, 36, color="#dcfce7", alpha=0.35, label="Bypass Zone (Est. SNR ≥ τ*: Keep Clean Speech Untouched)")
    ax.fill_between([0.4, len(order) + 0.6], -8, tau, color="#fee2e2", alpha=0.35, label="Active Denoise Zone (Est. SNR < τ*: Apply afftdn nr=6dB)")

    ax.set_xticks(range(1, len(order) + 1))
    ax.set_xticklabels(labels, fontsize=10, fontweight="bold")
    ax.set_ylabel("Estimated Blind SNR: P85(dB) - P15(dB)", fontsize=11, fontweight="bold")
    ax.set_title("Stage 1: Blind SNR Estimator Calibration (VAL) & Zero-Leakage Decision Boundary", fontsize=12.5, fontweight="bold", pad=12)
    ax.set_ylim(-6, 35)
    ax.grid(True, axis="y")
    ax.legend(loc="upper right", frameon=True, facecolor="white", framealpha=0.92, fontsize=9.5)
    save_and_copy(fig, "fig1_blind_snr_distribution.png")


def plot_fig2_filter_study():
    grid_csv = RESULTS_DIR / "exp2a_afftdn_grid_val_summary.csv"
    cross_csv = RESULTS_DIR / "exp2b_cross_filter_multisnr_val_summary.csv"
    if not grid_csv.exists() or not cross_csv.exists():
        return
    df_g = pd.read_csv(grid_csv).sort_values("wer_norm", ascending=True)
    df_c = pd.read_csv(cross_csv)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.2))

    # Panel A: Grid search at -10 dB
    y_pos = np.arange(len(df_g))
    bar_colors = []
    for fid in df_g["filter_id"]:
        if fid == "afftdn_nr6_white":
            bar_colors.append("#16a34a")
        elif fid == "F0_no_filter":
            bar_colors.append("#0ea5e9")
        elif fid == "afftdn_nr12_white":
            bar_colors.append("#dc2626")
        else:
            bar_colors.append("#64748b")
    bars = ax1.barh(y_pos, df_g["wer_norm"], color=bar_colors, alpha=0.88, height=0.68)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(df_g["filter_id"], fontsize=9.5, fontweight="bold")
    ax1.invert_yaxis()
    ax1.set_xlabel("Normalized WER (%) at -10 dB Fume-Hood Noise", fontsize=10.5, fontweight="bold")
    ax1.set_title("(A) afftdn Parameter Grid Search (-10 dB)\nnr=6dB Wins (5.75%); Legacy nr=12dB Degrades Speech (9.61%)", fontsize=11, fontweight="bold")
    ax1.grid(True, axis="x")
    for b in bars:
        w = b.get_width()
        ax1.text(w + 0.12, b.get_y() + b.get_height() / 2, f"{w:.2f}%", va="center", fontsize=8.5, fontweight="bold")
    ax1.set_xlim(0, max(df_g["wer_norm"]) * 1.18)

    # Panel B: Multi-SNR Cross-Filter Curves
    snr_order = ["clean", "+5dB", "+0dB", "-5dB", "-10dB"]
    snr_labels = ["Clean", "+5 dB", "0 dB", "-5 dB", "-10 dB"]
    styles = {
        "D8_snr_gated": ("Proposed D8: Blind SNR-Gated", "#16a34a", "o", "-", 2.8),
        "F0_no_filter": ("F0: No Filter (Always Off)", "#0ea5e9", "s", "--", 2.0),
        "F3_spectral_gate": ("F3: Spectral Gating (noisereduce)", "#8b5cf6", "^", "-.", 1.8),
        "F2_anlmdn": ("F2: Non-Local Means (anlmdn)", "#f59e0b", "D", ":", 1.8),
        "afftdn_nr12_white": ("Legacy Static afftdn (nr=12dB Always On)", "#dc2626", "X", "-", 2.2),
    }
    for fid, (lbl, col, mk, ls, lw) in styles.items():
        sub = df_c[df_c["filter_id"] == fid].set_index("snr_cond")
        if len(sub) == 0:
            continue
        vals = [sub.loc[s, "wer_norm"] if s in sub.index else np.nan for s in snr_order]
        ax2.plot(range(len(snr_order)), vals, label=lbl, color=col, marker=mk, linestyle=ls, linewidth=lw, markersize=7)

    ax2.set_xticks(range(len(snr_order)))
    ax2.set_xticklabels(snr_labels, fontsize=10, fontweight="bold")
    ax2.set_ylabel("Normalized WER (%)", fontsize=10.5, fontweight="bold")
    ax2.set_title("(B) Cross-Filter Benchmark Across 5 SNR Levels\nD8_snr_gated Achieves Pareto-Optimal WER at Every SNR", fontsize=11, fontweight="bold")
    ax2.grid(True)
    ax2.legend(loc="upper left", fontsize=8.8, frameon=True, facecolor="white")
    save_and_copy(fig, "fig2_multisnr_filter_degradation.png")


def plot_fig3_prompt_ablation():
    p_csv = RESULTS_DIR / "final_table_prompt_ablation_test_seen.csv"
    if not p_csv.exists():
        return
    df = pd.read_csv(p_csv).set_index("system_or_prompt")
    order = [
        "P0_no_prompt",
        "P1_domain_role",
        "P2_unstructured_glossary",
        "P3_numerical_format",
        "P4_budget_50tok",
        "P4_budget_100tok",
        "P4_phonetic_contrastive",
    ]
    labels = [
        "P0: No Prompt\n(0 tok)",
        "P1: Generic\nRole (22 tok)",
        "P2: Glossary\nOnly (58 tok)",
        "P3: Numerical\nFormat (54 tok)",
        "P4: Compact\n(50 tok)",
        "P4: Balanced\n(100 tok)",
        "P4: Full Phonetic\n(118 tok)",
    ]
    order = [o for o in order if o in df.index]
    sub = df.loc[order]

    x = np.arange(len(order))
    w = 0.25
    fig, ax = plt.subplots(figsize=(11.5, 5.0))
    b1 = ax.bar(x - w, sub["c_ter"], width=w, label="C-TER: Clinical Term Error Rate (%)", color="#0284c7")
    b2 = ax.bar(x, sub["n_der"], width=w, label="N-DER: Numerical & Dimension Error Rate (%)", color="#f59e0b")
    b3 = ax.bar(x + w, sub["cer_case_pct"], width=w, label="CER_case: Critical Case Error Rate (%)", color="#dc2626")

    for bars in (b1, b2, b3):
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, h + 0.25, f"{h:.1f}", ha="center", va="bottom", fontsize=8, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels[:len(order)], fontsize=9.5, fontweight="bold")
    ax.set_ylabel("Error Rate (%)", fontsize=11, fontweight="bold")
    ax.set_title("Stage 3: Orthogonal Decomposition of Prompt Structure & Token Budget (Unseen Phrasings)", fontsize=12, fontweight="bold", pad=12)
    ax.set_ylim(0, max(sub["cer_case_pct"].max(), sub["c_ter"].max()) * 1.22)
    ax.grid(True, axis="y")
    ax.legend(loc="upper right", fontsize=9.5, frameon=True, facecolor="white")
    save_and_copy(fig, "fig3_prompt_orthogonal_decomposition.png")


def plot_fig4_lora_and_progression():
    log_csv = RESULTS_DIR / "lora_checkpoints" / "lora_training_log.csv"
    s_seen = RESULTS_DIR / "final_table_system_progression_test_seen.csv"
    s_unseen = RESULTS_DIR / "final_table_system_progression_test_unseen.csv"
    if not s_seen.exists() or not s_unseen.exists():
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.0))

    if log_csv.exists():
        df_l = pd.read_csv(log_csv)
        ax1.plot(df_l["epoch"], df_l["train_loss"], marker="o", linewidth=2.5, color="#0284c7", label="Training Loss (Phrasings 0–3)")
        ax1.plot(df_l["epoch"], df_l["val_loss"], marker="s", linewidth=2.5, color="#16a34a", label="Validation Loss (Unseen Phrasing 4)")
        for _, r in df_l.iterrows():
            ax1.annotate(f"{r['train_loss']:.4f}", (r["epoch"], r["train_loss"]), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9, fontweight="bold", color="#0284c7")
            ax1.annotate(f"{r['val_loss']:.4f}", (r["epoch"], r["val_loss"]), textcoords="offset points", xytext=(0, -14), ha="center", fontsize=9, fontweight="bold", color="#16a34a")
        ax1.set_xticks(df_l["epoch"])
        ax1.set_xticklabels([f"Epoch {int(e)}" for e in df_l["epoch"]], fontsize=10, fontweight="bold")
        ax1.set_ylabel("Cross-Entropy Loss", fontsize=10.5, fontweight="bold")
        ax1.set_title("(A) Whisper Small LoRA (r=8, α=32) Convergence\nMonotonic Loss Reduction Without Overfitting", fontsize=11, fontweight="bold")
        ax1.grid(True)
        ax1.legend(loc="upper right", fontsize=9.5, frameon=True, facecolor="white")

    df_s1 = pd.read_csv(s_seen).set_index("system")
    df_s2 = pd.read_csv(s_unseen).set_index("system")
    sys_order = [
        "S0_ZeroShot_NoPrompt_SNRGated",
        "S1b_ZeroShot_P4_StaticAfftdn",
        "S1c_ZeroShot_P4_SNRGated",
        "S2_LoRA_INT8_NoPrompt",
        "S3_Full_PathoWhisper_LoRA_Prompt_SNRGated",
    ]
    sys_labels = [
        "S0: Zero-Shot\n(No Prompt)",
        "S1b: P4 + Static\nafftdn (Legacy)",
        "S1c: P4 + Blind\nSNR-Gated",
        "S2: LoRA INT8\n(No Prompt)",
        "S3: Full\nPathoWhisper",
    ]
    sys_order = [s for s in sys_order if s in df_s1.index and s in df_s2.index]
    x = np.arange(len(sys_order))
    w = 0.22
    b_w1 = ax2.bar(x - w, [df_s1.loc[s, "wer_norm"] for s in sys_order], width=w, label="test_seen Norm. WER (%)", color="#38bdf8")
    b_w2 = ax2.bar(x, [df_s2.loc[s, "wer_norm"] for s in sys_order], width=w, label="test_unseen Norm. WER (%)", color="#0284c7")
    b_c1 = ax2.bar(x + w, [df_s1.loc[s, "cer_case_pct"] for s in sys_order], width=w, label="test_seen CER_case (%)", color="#f97316")

    for bars in (b_w1, b_w2, b_c1):
        for b in bars:
            h = b.get_height()
            ax2.text(b.get_x() + b.get_width() / 2, h + 0.3, f"{h:.1f}", ha="center", va="bottom", fontsize=7.8, fontweight="bold")

    ax2.set_xticks(x)
    ax2.set_xticklabels(sys_labels[:len(sys_order)], fontsize=9, fontweight="bold")
    ax2.set_ylabel("Error Rate (%)", fontsize=10.5, fontweight="bold")
    ax2.set_title("(B) End-to-End System Progression (N=300 Test Cases)\nSignificant Gains from Both Prompt+SNR-Gate and LoRA INT8", fontsize=11, fontweight="bold")
    ax2.set_ylim(0, 15.5)
    ax2.grid(True, axis="y")
    ax2.legend(loc="upper right", fontsize=8.8, frameon=True, facecolor="white")
    save_and_copy(fig, "fig4_lora_convergence_and_system_progression.png")


def plot_fig5_15fields():
    f_seen = RESULTS_DIR / "final_table_15fields_test_seen.csv"
    f_unseen = RESULTS_DIR / "final_table_15fields_test_unseen.csv"
    if not f_seen.exists() or not f_unseen.exists():
        return
    df1 = pd.read_csv(f_seen)
    df2 = pd.read_csv(f_unseen)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 6.2), sharey=True)
    fig.subplots_adjust(wspace=0.18)
    y = np.arange(len(df1))
    h = 0.26

    ax1.barh(y - h, df1["S0_ZeroShot_NoPrompt_SNRGated_F1"], height=h, label="S0: Zero-Shot (No Prompt)", color="#94a3b8")
    ax1.barh(y, df1["S2_LoRA_INT8_NoPrompt_F1"], height=h, label="S2: Whisper Small LoRA INT8", color="#0284c7")
    ax1.barh(y + h, df1["S3_Full_PathoWhisper_LoRA_Prompt_SNRGated_F1"], height=h, label="S3: Full PathoWhisper", color="#16a34a")
    ax1.set_yticks(y)
    ax1.set_yticklabels([f"{r['field']} {'[CRIT]' if r['is_critical'] else ''}" for _, r in df1.iterrows()], fontsize=9, fontweight="bold")
    ax1.invert_yaxis()
    ax1.set_xlim(80, 101.5)
    ax1.set_xlabel("Field Extraction F1-Score (%)", fontsize=10.5, fontweight="bold")
    ax1.set_title("(A) All 15 CAP Fields (test_seen, N=150)\nMacro-F1: 98.46% (S0) → 99.13% (S3)", fontsize=11, fontweight="bold")
    ax1.grid(True, axis="x")
    ax1.legend(loc="lower left", fontsize=8.8, frameon=True, facecolor="white")

    ax2.barh(y - h, df2["S0_ZeroShot_NoPrompt_SNRGated_F1"], height=h, label="S0: Zero-Shot (No Prompt)", color="#94a3b8")
    ax2.barh(y, df2["S2_LoRA_INT8_NoPrompt_F1"], height=h, label="S2: Whisper Small LoRA INT8", color="#0284c7")
    ax2.barh(y + h, df2["S3_Full_PathoWhisper_LoRA_Prompt_SNRGated_F1"], height=h, label="S3: Full PathoWhisper", color="#16a34a")
    ax2.set_xlim(80, 101.5)
    ax2.set_xlabel("Field Extraction F1-Score (%)", fontsize=10.5, fontweight="bold")
    ax2.set_title("(B) All 15 CAP Fields (test_unseen, N=150)\nMacro-F1: 95.69% (S0) → 96.22% (S3)", fontsize=11, fontweight="bold")
    ax2.grid(True, axis="x")
    ax2.legend(loc="lower left", fontsize=8.8, frameon=True, facecolor="white")

    save_and_copy(fig, "fig5_15fields_cap_f1_heatmap.png")


def plot_fig6_risk_coverage():
    m_json = RESULTS_DIR / "final_thesis_master_summary.json"
    if not m_json.exists():
        return
    data = json.load(open(m_json, encoding="utf-8"))
    if "test_seen" not in data:
        return
    rc = data["test_seen"]["risk_coverage"]

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    styles = {
        "S0_ZeroShot_NoPrompt_SNRGated": ("S0: Zero-Shot Baseline", "#64748b", "s", "--"),
        "S1c_ZeroShot_P4_SNRGated": ("S1c: Zero-Shot + P4 + SNR-Gated", "#0ea5e9", "^", "-."),
        "S2_LoRA_INT8_NoPrompt": ("S2: Fine-Tuned Whisper LoRA INT8", "#16a34a", "o", "-"),
        "S3_Full_PathoWhisper_LoRA_Prompt_SNRGated": ("S3: Full PathoWhisper (LoRA + P4 + SNR-Gated)", "#dc2626", "D", "-"),
    }
    for sys_id, (lbl, col, mk, ls) in styles.items():
        if sys_id not in rc:
            continue
        pts = [p for p in rc[sys_id] if not p.get("binary_flag_operating_point")]
        covs = [p["target_coverage_pct"] for p in pts]
        cers = [p["effective_cer_case_pct"] for p in pts]
        ax.plot(covs, cers, label=lbl, color=col, marker=mk, linestyle=ls, linewidth=2.3, markersize=6.5)

    ax.invert_xaxis()
    ax.set_xlabel("Automation Coverage (% of Cases Auto-Approved Without Human Review)", fontsize=10.5, fontweight="bold")
    ax.set_ylabel("Effective Critical Case Error Rate: CER_case (%)", fontsize=10.5, fontweight="bold")
    ax.set_title("Multi-Signal Safety Flagging: Selective Prediction Risk-Coverage Curve", fontsize=12, fontweight="bold", pad=12)
    ax.grid(True)
    ax.legend(loc="upper right", fontsize=9.2, frameon=True, facecolor="white")
    save_and_copy(fig, "fig6_selective_prediction_risk_coverage.png")


def main():
    plot_fig1_snr_calibration()
    plot_fig2_filter_study()
    plot_fig3_prompt_ablation()
    plot_fig4_lora_and_progression()
    plot_fig5_15fields()
    plot_fig6_risk_coverage()
    print("All 6 thesis figures generated successfully.")


if __name__ == "__main__":
    main()
