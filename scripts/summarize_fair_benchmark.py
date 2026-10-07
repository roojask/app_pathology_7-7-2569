import sys
import json
import re
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "src" / "nlp"))
from extractor import extract_data_15_sections

csv_path = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "fair_empirical_comparison_20cases.csv"
json_path = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "fair_empirical_comparison_20cases.json"
gt_path = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000_pure.json"

with open(gt_path, "r", encoding="utf-8") as f:
    gt_all = json.load(f)

df = pd.read_csv(csv_path)

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

def norm_a(t):
    t = str(t).lower()
    t = re.sub(r"[.,;:!?\-]", " ", t)
    return " ".join(t.split())

def norm_b(t):
    """Criterion B normalization from analyze_benchmark.py."""
    t = str(t).lower()
    for _ in range(2):
        t = re.sub(r"(\d)\s*(?:x|by)\s*(?=\d)", r"\1 x ", t)
    t = re.sub(r"(\d)(cm|mm|g|kg)\b", r"\1 \2", t)
    t = re.sub(r"[.,;:!?\-]", " ", t)
    return " ".join(t.split())

field_keys = [
    "s0_surgical_no", "s1_side", "s2_proc", "s3_dims", "s4_skin",
    "s5_dims", "s6_nipple", "s7_biopsy_scar", "s8_cavity", "s9_residual_mass",
    "s10_infiltrative", "s10_inf_dims", "s10_5_quadrant", "s11_deep_margin", "s14_check"
]

def are_dims_equal(d1, d2):
    if not d1 or not d2: return False
    try:
        f1 = [float(x.rstrip('.')) for x in d1]
        f2 = [float(x.rstrip('.')) for x in d2]
        return sorted(f1) == sorted(f2)
    except:
        return False

def are_numbers_equal(n1, n2):
    try:
        return abs(float(str(n1).rstrip('.')) - float(str(n2).rstrip('.'))) < 1e-4
    except:
        return False

def are_strings_equal(s1, s2):
    return str(s1).lower().strip() == str(s2).lower().strip()

def eval_text_slots(text, gt):
    pred = extract_data_15_sections(text)
    p_quad = None
    if pred.get("s10_5_quadrant_vals"):
        p_quad = " ".join(pred["s10_5_quadrant_vals"])
    elif pred.get("s10_5_central"):
        p_quad = "central"
        
    pred_mapped = {
        "s0_surgical_no": pred.get("s0_surgical_no"),
        "s1_side": pred.get("s1_side"),
        "s2_proc": pred.get("s2_proc"),
        "s3_dims": pred.get("s3_dims"),
        "s4_skin": bool(pred.get("s5_appears_normal") or pred.get("s5_dims")),
        "s5_dims": pred.get("s5_dims"),
        "s6_nipple": pred.get("s9_val"),
        "s7_biopsy_scar": pred.get("s6_check"),
        "s8_cavity": pred.get("s10_prev1") or pred.get("s10_prev2"),
        "s9_residual_mass": pred.get("s10_prev2_mass_dims"),
        "s10_infiltrative": pred.get("s10_infiltrative"),
        "s10_inf_dims": pred.get("s10_inf_dims"),
        "s10_5_quadrant": p_quad,
        "s11_deep_margin": pred.get("s11_deep"),
        "s14_check": pred.get("s14_check")
    }
    
    correct = 0
    for k in field_keys:
        gv = gt.get(k)
        pv = pred_mapped.get(k)
        g_has = (gv is not None and gv != "" and gv != [] and gv is not False)
        p_has = (pv is not None and pv != "" and pv != [] and pv is not False)
        if not g_has and not p_has:
            correct += 1
        elif g_has and p_has:
            if k in ["s3_dims", "s5_dims", "s10_inf_dims"]:
                if are_dims_equal(gv, pv): correct += 1
            elif k in ["s11_deep_margin"]:
                if are_numbers_equal(gv, pv): correct += 1
            elif isinstance(gv, bool):
                if pv == gv: correct += 1
            else:
                if are_strings_equal(gv, pv): correct += 1
    return correct

# Re-evaluate all fields with gold-standard definitions
for idx, r in df.iterrows():
    cid = r["case_id"]
    gt = gt_all[cid]
    ref = r["ref_text"]
    
    # Standard Criterion A
    df.at[idx, "wer_v_raw"] = wer(norm_a(ref), norm_a(r["vosk_raw"])) * 100
    df.at[idx, "wer_w_raw"] = wer(norm_a(ref), norm_a(r["w2v_raw"])) * 100
    df.at[idx, "wer_b_raw"] = wer(norm_a(ref), norm_a(r["bs_hyp"])) * 100
    df.at[idx, "wer_p_raw"] = wer(norm_a(ref), norm_a(r["pw_hyp"])) * 100
    
    # Standard Criterion B (with ITN for Vosk & W2V2)
    df.at[idx, "wer_v_itn"] = wer(norm_b(ref), norm_b(r["vosk_itn"])) * 100
    df.at[idx, "wer_w_itn"] = wer(norm_b(ref), norm_b(r["w2v_itn"])) * 100
    df.at[idx, "wer_b_itn"] = wer(norm_b(ref), norm_b(r["bs_hyp"])) * 100
    df.at[idx, "wer_p_itn"] = wer(norm_b(ref), norm_b(r["pw_hyp"])) * 100
    
    # Exact 15-Field Slots Agreement
    df.at[idx, "slots_vosk"] = eval_text_slots(r["vosk_itn"], gt)
    df.at[idx, "slots_w2v"] = eval_text_slots(r["w2v_itn"], gt)
    df.at[idx, "slots_baseline"] = eval_text_slots(r["bs_hyp"], gt)
    df.at[idx, "slots_pathowhisper"] = eval_text_slots(r["pw_hyp"], gt)

# Save updated files
df.to_csv(csv_path, index=False, encoding="utf-8-sig")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(json.loads(df.to_json(orient="records")), f, ensure_ascii=False, indent=2)

print("=" * 105)
print("RE-EVALUATED FAIR HEAD-TO-HEAD BENCHMARK SUMMARY (20 CASES ACROSS 10 CLINICAL CATEGORIES)")
print("=" * 105)

summary_data = [
    ("Vosk (Kaldi HMM-DNN)", df['wer_v_raw'].mean(), df['wer_v_itn'].mean(), df['lat_vosk'].mean(), df['slots_vosk'].sum(), df['slots_vosk'].sum() / 300 * 100),
    ("Meta Wav2Vec 2.0 (CTC)", df['wer_w_raw'].mean(), df['wer_w_itn'].mean(), df['lat_w2v'].mean(), df['slots_w2v'].sum(), df['slots_w2v'].sum() / 300 * 100),
    ("Baseline Whisper Small FP32", df['wer_b_raw'].mean(), df['wer_b_itn'].mean(), df['lat_baseline'].mean(), df['slots_baseline'].sum(), df['slots_baseline'].sum() / 300 * 100),
    ("PathoWhisper INT8 (Proposed)", df['wer_p_raw'].mean(), df['wer_p_itn'].mean(), df['lat_pathowhisper'].mean(), df['slots_pathowhisper'].sum(), df['slots_pathowhisper'].sum() / 300 * 100),
]

header = f"{'ASR Architecture / Model':<30} | {'Raw WER':<10} | {'Fair B/ITN WER':<14} | {'Latency':<10} | {'Slot Agreement (15 fld)':<22}"
print(header)
print("-" * 105)
for name, raw_w, itn_w, lat, slots, slot_acc in summary_data:
    print(f"{name:<30} | {raw_w:>8.2f}% | {itn_w:>12.2f}% | {lat:>7.2f} s | {slots:>3d}/300 ({slot_acc:>5.2f}%)")
print("=" * 105)

print("\n--- CATEGORY-BY-CATEGORY BREAKDOWN (Fair Criterion B / ITN WER %) ---")
cat_summary = df.groupby(["category_id", "category_name"])[['wer_v_itn', 'wer_w_itn', 'wer_b_itn', 'wer_p_itn']].mean().reset_index()
print(f"{'Cat':<4} | {'Category Name':<30} | {'Vosk ITN':<10} | {'W2V2 ITN':<10} | {'Base Small':<10} | {'PathoWhisper':<12}")
print("-" * 90)
for _, r in cat_summary.iterrows():
    print(f"{int(r['category_id']):<4} | {r['category_name'][:30]:<30} | {r['wer_v_itn']:>8.2f}% | {r['wer_w_itn']:>8.2f}% | {r['wer_b_itn']:>8.2f}% | {r['wer_p_itn']:>10.2f}%")
print("=" * 90)

print("\n--- CASE-BY-CASE DETAILS (20 CASES) ---")
print(f"{'Case ID':<10} | {'Cat':<4} | {'Vosk Raw':<9} | {'Vosk ITN':<9} | {'W2V2 Raw':<9} | {'W2V2 ITN':<9} | {'Base B':<9} | {'PW B':<9} | {'Vosk Slots':<10} | {'W2V2 Slots':<10} | {'PW Slots':<10}")
print("-" * 120)
for _, r in df.iterrows():
    print(f"{r['case_id']:<10} | {int(r['category_id']):<4} | {r['wer_v_raw']:>7.1f}% | {r['wer_v_itn']:>7.1f}% | {r['wer_w_raw']:>7.1f}% | {r['wer_w_itn']:>7.1f}% | {r['wer_b_itn']:>7.1f}% | {r['wer_p_itn']:>7.1f}% | {int(r['slots_vosk']):>5}/15     | {int(r['slots_w2v']):>5}/15     | {int(r['slots_pathowhisper']):>5}/15")
print("=" * 120)
