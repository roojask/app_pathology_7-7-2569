import os
import sys
import shutil
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent.parent
CHART_DIR = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACT_DIR = Path(r"C:\Users\project\.gemini\antigravity\brain\817acc80-169e-4ca0-b20a-ef6959971b44")

# Set global matplotlib publication style
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['axes.edgecolor'] = '#cccccc'
plt.rcParams['axes.linewidth'] = 0.8
plt.rcParams['grid.color'] = '#e0e0e0'
plt.rcParams['grid.linestyle'] = '--'
plt.rcParams['grid.alpha'] = 0.7

COLOR_PW = '#1f77b4'       # Vibrant Clinical Blue
COLOR_BASE = '#7f7f7f'     # Slate Gray
COLOR_ACCENT = '#2ca02c'   # Success Green
COLOR_ORANGE = '#ff7f0e'   # Warning Orange

print("=" * 70)
print("GENERATING PUBLICATION-GRADE RESEARCH CHARTS FOR THESIS & DEFENSE")
print("=" * 70)

# -------------------------------------------------------------------------
# Figure 1: Field Extraction F1-Score Comparison (Baseline vs PathoWhisper)
# -------------------------------------------------------------------------
print("[1/5] Generating Figure 1: Field Extraction F1-Score Comparison...")
fields = [
    's0_surgical_no', 's1_side', 's2_proc', 's3_dims', 's4_skin',
    's5_dims', 's10_infiltrative', 's10_inf_dims', 's10_5_quadrant',
    's11_deep_margin', 's14_check'
]
labels = [
    'Surgical No\n(s0)', 'Laterality\n(s1)', 'Procedure\n(s2)', 'Specimen 3D\n(s3)',
    'Skin Ellipse\n(s4)', 'Skin 2D\n(s5)', 'Infiltrative\n(s10)', 'Mass 3D\n(s10_dims)',
    'Quadrant\n(s10.5)', 'Deep Margin\n(s11)', 'Lymph Nodes\n(s14)'
]
base_f1 = [97.6, 94.6, 100.0, 89.6, 97.9, 95.9, 98.7, 87.7, 100.0, 99.0, 97.9]
pw_f1 =   [97.9, 99.9, 100.0, 88.8, 99.5, 98.1, 98.6, 88.2,  99.6, 96.3, 99.8]

x = np.arange(len(fields))
width = 0.38

fig, ax = plt.subplots(figsize=(14, 6), dpi=300)
rects1 = ax.bar(x - width/2, base_f1, width, label='Baseline (Whisper FP32)', color=COLOR_BASE, alpha=0.85, edgecolor='black', linewidth=0.5)
rects2 = ax.bar(x + width/2, pw_f1, width, label='PathoWhisper (Optimized)', color=COLOR_PW, alpha=0.95, edgecolor='black', linewidth=0.5)

ax.set_ylabel('F1-Score (%)', fontsize=12, fontweight='bold')
ax.set_title('Clinical Information Extraction Performance by Field (N = 1,000 Cases)\nMacro-F1 (11 Evaluable Fields): Baseline 96.26% vs PathoWhisper 96.97%', fontsize=14, fontweight='bold', pad=15)
ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=10)
ax.set_ylim(75, 105)
ax.axhline(100, color='gray', linestyle=':', alpha=0.5)
ax.grid(axis='y')
ax.legend(loc='lower right', frameon=True, fontsize=11, framealpha=0.95)

# Value annotations
for rect in rects2:
    h = rect.get_height()
    ax.annotate(f'{h:.1f}%',
                xy=(rect.get_x() + rect.get_width() / 2, h),
                xytext=(0, 3), textcoords="offset points",
                ha='center', va='bottom', fontsize=8, fontweight='bold', color='#0d47a1')

plt.tight_layout()
fig1_path = CHART_DIR / "fig1_field_f1_comparison.png"
fig.savefig(fig1_path)
plt.close()

# -------------------------------------------------------------------------
# Figure 2: Word Error Rate (WER) by Clinical Challenge Category
# -------------------------------------------------------------------------
print("[2/5] Generating Figure 2: WER across 10 Clinical Challenge Categories...")
cats = [f"Cat {i}" for i in range(1, 11)]
cat_names = [
    "1. Standard", "2. Out-of-Order", "3. Self-Corr", "4. Multi-Margin",
    "5. Axillary", "6. Fibrocystic", "7. Rapid Speech", "8. Fume Hood",
    "9. Ductal Ca", "10. Edge Cases"
]
base_wer = [24.18, 34.34, 38.49, 30.58, 25.36, 29.18, 70.76, 44.88, 31.77, 33.13]
pw_wer   = [18.13, 25.50, 31.93, 24.60, 16.41, 27.13, 65.90, 31.94, 25.71, 23.27]

x = np.arange(len(cats))
width = 0.38

fig, ax = plt.subplots(figsize=(14, 6), dpi=300)
r1 = ax.bar(x - width/2, base_wer, width, label='Baseline (Whisper FP32)', color=COLOR_BASE, alpha=0.85, edgecolor='black', linewidth=0.5)
r2 = ax.bar(x + width/2, pw_wer, width, label='PathoWhisper (Noise Filter + Prompt)', color='#e65100', alpha=0.9, edgecolor='black', linewidth=0.5)

ax.set_ylabel('Word Error Rate - WER (%) [Lower is Better]', fontsize=12, fontweight='bold')
ax.set_title('Speech-to-Text WER across 10 Clinical Challenge Categories\nOverall Mean WER: Baseline 36.27% vs PathoWhisper 29.05% (p < 0.001)', fontsize=14, fontweight='bold', pad=15)
ax.set_xticks(x)
ax.set_xticklabels(cat_names, rotation=20, ha='right', fontsize=10)
ax.set_ylim(0, 80)
ax.grid(axis='y')
ax.legend(loc='upper left', frameon=True, fontsize=11)

# Annotate Category 8 (Fume hood noise highlight)
ax.annotate('Fume Hood Noise\n12.9 Percentage-Point\nWER Reduction',
            xy=(7 + width/2, pw_wer[7]), xytext=(7 + width/2, pw_wer[7] + 16),
            arrowprops=dict(facecolor='#d84315', shrink=0.08, width=1.5, headwidth=6),
            ha='center', fontsize=9, fontweight='bold', color='#bf360c',
            bbox=dict(boxstyle="round,pad=0.3", fc="#ffecb3", ec="#ffb300", lw=1))

plt.tight_layout()
fig2_path = CHART_DIR / "fig2_wer_by_category.png"
fig.savefig(fig2_path)
plt.close()

# -------------------------------------------------------------------------
# Figure 3: Inference Latency and Processing Speedup
# -------------------------------------------------------------------------
print("[3/5] Generating Figure 3: Inference Latency Comparison...")
base_lat = [28.90, 26.31, 19.73, 27.83, 14.61, 14.11, 16.42, 15.14, 24.32, 12.99]
pw_lat   = [16.81, 15.78, 10.93, 16.54,  8.65,  8.66,  8.99,  8.74, 11.52,  8.39]

fig, ax = plt.subplots(figsize=(14, 5.5), dpi=300)
x = np.arange(len(cats))
width = 0.38

r1 = ax.bar(x - width/2, base_lat, width, label='Baseline FP32 (20.04s Mean)', color=COLOR_BASE, alpha=0.85, edgecolor='black', linewidth=0.5)
r2 = ax.bar(x + width/2, pw_lat, width, label='PathoWhisper INT8 (11.50s Mean - 1.74x Faster)', color='#2e7d32', alpha=0.9, edgecolor='black', linewidth=0.5)

ax.set_ylabel('Inference Time (Seconds/Case) [Lower is Better]', fontsize=12, fontweight='bold')
ax.set_title('On-Device CPU Inference Latency Comparison (N = 1,000 Cases)\nMean Time Reduction: 8.54s per dictation (Wilcoxon p = 9.55e-163)', fontsize=14, fontweight='bold', pad=15)
ax.set_xticks(x)
ax.set_xticklabels(cat_names, rotation=20, ha='right', fontsize=10)
ax.set_ylim(0, 35)
ax.grid(axis='y')
ax.legend(loc='upper right', frameon=True, fontsize=11)

for rect in r2:
    h = rect.get_height()
    ax.annotate(f'{h:.1f}s', xy=(rect.get_x() + rect.get_width()/2, h),
                xytext=(0, 2), textcoords="offset points", ha='center', va='bottom', fontsize=8, fontweight='bold', color='#1b5e20')

plt.tight_layout()
fig3_path = CHART_DIR / "fig3_latency_speedup.png"
fig.savefig(fig3_path)
plt.close()

# -------------------------------------------------------------------------
# Figure 4: Progressive Speech Model Ablation Study
# -------------------------------------------------------------------------
print("[4/5] Generating Figure 4: Progressive Model Ablation...")
# Traceable directly to benchmarks/thesis_eval_outputs/ablation_cat8_fume_hood.csv
df_cat8_abl = pd.read_csv(BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "ablation_cat8_fume_hood.csv")

ablation_configs = [
    "1. Baseline\n(Whisper Small FP32)",
    "2. + afftdn\nSpectral Denoise",
    "3. + Clinical\nInitial Prompt",
    "4. + INT8 CTranslate2\n(Beam 5)",
    "5. + Greedy Beam 1\n(Full PathoWhisper)"
]
wer_noise_cat8 = [round(v, 2) for v in df_cat8_abl['wer_mean'].tolist()]
latencies = [round(v, 2) for v in df_cat8_abl['latency_mean_sec'].tolist()]

fig, ax1 = plt.subplots(figsize=(11, 5.5), dpi=300)

x = np.arange(len(ablation_configs))
bars = ax1.bar(x, wer_noise_cat8, width=0.45, color='#3949ab', alpha=0.85, edgecolor='black', linewidth=0.8, label='Cat 8 WER (Fume Hood Noise %)')
ax1.set_ylabel('Fume Hood Noise WER (%) [Lower is Better]', color='#1a237e', fontsize=11, fontweight='bold')
ax1.tick_params(axis='y', labelcolor='#1a237e')
ax1.set_ylim(0, 50)
ax1.set_xticks(x)
ax1.set_xticklabels(ablation_configs, fontsize=9.5)
ax1.grid(axis='y')

# Second axis for latency line
ax2 = ax1.twinx()
line = ax2.plot(x, latencies, color='#d32f2f', marker='o', linewidth=2.5, markersize=8, label='Inference Latency (sec)')
ax2.set_ylabel('Inference Latency (Seconds)', color='#b71c1c', fontsize=11, fontweight='bold')
ax2.tick_params(axis='y', labelcolor='#b71c1c')
ax2.set_ylim(0, 25)

# Add values above bars
for bar in bars:
    yval = bar.get_height()
    ax1.text(bar.get_x() + bar.get_width()/2, yval + 1, f"{yval:.1f}%", ha='center', va='bottom', fontsize=9, fontweight='bold', color='#1a237e')

for i, txt in enumerate(latencies):
    ax2.annotate(f"{txt:.1f}s", (x[i], latencies[i]), xytext=(0, 10), textcoords="offset points", ha='center', fontsize=9, fontweight='bold', color='#b71c1c')

plt.title('Progressive Ablation Study of PathoWhisper Components\nWER and On-Device Latency under Fume Hood Noise (N = 5 Cases, Category 8)', fontsize=12, fontweight='bold', pad=15)
plt.tight_layout()
fig4_path = CHART_DIR / "fig4_progressive_ablation.png"
fig.savefig(fig4_path)
plt.close()

# -------------------------------------------------------------------------
# Figure 5: Parser Refinement Impact (Before vs After)
# -------------------------------------------------------------------------
print("[5/5] Generating Figure 5: Before vs After Parser Refinement Comparison...")
# Traceable directly to benchmarks/thesis_eval_outputs/parser_refinement_comparison.csv
df_ref = pd.read_csv(BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "parser_refinement_comparison.csv")
target_flds = ['Surgical Number (s0)', 'Infiltrative Mass 3D (s10)', 'Deep Margin (s11)', 'Macro-F1 (11 Fields)']
f1_base   = df_ref['baseline_f1'].tolist()
f1_before = df_ref['pre_refinement_f1'].tolist()
f1_after  = df_ref['refined_f1'].tolist()

x = np.arange(len(target_flds))
width = 0.28

fig, ax = plt.subplots(figsize=(12, 5.5), dpi=300)
r1 = ax.bar(x - width, f1_base, width, label='Baseline', color=COLOR_BASE, alpha=0.85, edgecolor='black', linewidth=0.5)
r2 = ax.bar(x, f1_before, width, label='PathoWhisper (Pre-refinement)', color='#ef5350', alpha=0.85, edgecolor='black', linewidth=0.5)
r3 = ax.bar(x + width, f1_after, width, label='PathoWhisper (Refined Parser)', color='#2e7d32', alpha=0.95, edgecolor='black', linewidth=0.5)

ax.set_ylabel('F1-Score (%)', fontsize=12, fontweight='bold')
ax.set_title('Targeted Post-hoc Parser Refinement Impact (N = 1,000 Cases)\nTraceable to parser_refinement_comparison.csv', fontsize=13, fontweight='bold', pad=15)
ax.set_xticks(x)
ax.set_xticklabels(target_flds, fontsize=10.5)
ax.set_ylim(60, 105)
ax.grid(axis='y')
ax.legend(loc='lower right', frameon=True, fontsize=10.5)

# Value annotations on Refined
for rect in r3:
    h = rect.get_height()
    ax.annotate(f'{h:.1f}%', xy=(rect.get_x() + rect.get_width()/2, h),
                xytext=(0, 2), textcoords="offset points", ha='center', va='bottom', fontsize=8.5, fontweight='bold', color='#1b5e20')

plt.tight_layout()
fig5_path = CHART_DIR / "fig5_parser_refinement_impact.png"
fig.savefig(fig5_path)
plt.close()

# Copy all figures to artifact directory for instant viewing
for p in [fig1_path, fig2_path, fig3_path, fig4_path, fig5_path]:
    dest = ARTIFACT_DIR / p.name
    shutil.copy(p, dest)
    print(f"  • Saved: {p.name} -> {dest}")

print("=" * 70)
print("ALL 5 HIGH-RESOLUTION PUBLICATION CHARTS GENERATED SUCCESSFULLY!")
print("=" * 70)
