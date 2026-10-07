"""
scripts/run_fair_empirical_comparison.py
================================================================================
Rigorous, Fair, and Empirical Multi-Model Benchmark (20 Representative Cases)
Covers all 10 pathology categories (2 cases each: case_0001 to case_0020)

Compares:
  1. Vosk ASR (bin/vosk-model-small-en-us-0.15)
  2. Meta Wav2Vec 2.0 (facebook/wav2vec2-base-960h)
  3. Baseline Whisper Small (PyTorch FP32)
  4. PathoWhisper (CTranslate2 INT8 + Clinical Prompt + afftdn)

Fairness Protocols:
  - Raw WER (Criterion A: without text normalization)
  - Fair Normalized WER (ITN: Inverse Text Normalization converting number words
    to Arabic digits and normalizing unit symbols so Vosk/Wav2Vec2 are not penalized
    for lack of native numeral formatting)
  - Slot-Level 15-Field Clinical Extraction Agreement
  - Mean CPU Latency per case
================================================================================
"""

import sys
import os
import re
import time
import json
from pathlib import Path
import numpy as np
import pandas as pd
import librosa
from vosk import Model as VoskModel, KaldiRecognizer
from transformers import pipeline

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.nlp.extractor import extract_data_15_sections
from scripts.analyze_benchmark import wer, cer, lev

# 1. Number word mappings for Inverse Text Normalization (ITN)
NUM_WORDS = {
    'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
    'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
    'ten': '10', 'eleven': '11', 'twelve': '12', 'thirteen': '13',
    'fourteen': '14', 'fifteen': '15', 'sixteen': '16', 'seventeen': '17',
    'eighteen': '18', 'nineteen': '19', 'twenty': '20', 'thirty': '30',
    'forty': '40', 'fifty': '50', 'sixty': '60', 'seventy': '70',
    'eighty': '80', 'ninety': '90'
}

TENS = {
    'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
    'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90
}
ONES = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9
}

def apply_itn(text):
    """Fair Inverse Text Normalization (ITN) converting verbal numbers to digits."""
    if not text:
        return ""
    t = str(text).lower()

    # Normalize surgical numbers (e.g. 's twenty four dash one thousand and one' -> 's-24-1001')
    t = re.sub(r'\b(?:as|s)\s+twenty\s+four\s+(?:dash\s+)?one\s+thousand\s+(?:and\s+)?(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\b',
               lambda m: f"s-24-{1000 + (ONES.get(m.group(1), int(m.group(1)) if m.group(1).isdigit() else 0))}", t)

    # Decimal phrases: e.g., 'eleven point four' -> '11.4'
    for w1, d1 in NUM_WORDS.items():
        for w2, d2 in NUM_WORDS.items():
            t = t.replace(f"{w1} point {w2}", f"{d1}.{d2}")
            t = t.replace(f"{w1} pointe {w2}", f"{d1}.{d2}")

    # Compound numbers: e.g. 'twenty four' -> '24'
    for ten_w, ten_v in TENS.items():
        for one_w, one_v in ONES.items():
            t = re.sub(rf'\b{ten_w}\s+{one_w}\b', str(ten_v + one_v), t)

    # Standalone numbers
    for w, d in NUM_WORDS.items():
        t = re.sub(rf'\b{w}\b', d, t)

    # Common year / thousands patterns
    t = re.sub(r'\bone\s+thousand\s+(?:and\s+)?(\d+)\b', lambda m: str(1000 + int(m.group(1))), t)

    # Units
    t = re.sub(r'\b(?:centimeters|centimeter|sentimeters|centimeters)\b', 'cm', t)
    t = re.sub(r'\b(?:millimeters|millimeter|milimeters)\b', 'mm', t)

    # Dimension separators between digits
    for _ in range(2):
        t = re.sub(r'(\d)\s*(?:x|by|times|\*)\s*(?=\d)', r'\1 x ', t)
    t = re.sub(r'(\d)(cm|mm|g|kg)\b', r'\1 \2', t)

    # Punctuation
    t = re.sub(r'[.,;:!?\-]', ' ', t)
    return " ".join(t.split())

def norm_b(t):
    """Criterion B normalization from analyze_benchmark.py."""
    t = str(t).lower()
    for _ in range(2):
        t = re.sub(r"(\d)\s*(?:x|by)\s*(?=\d)", r"\1 x ", t)
    t = re.sub(r"(\d)(cm|mm|g|kg)\b", r"\1 \2", t)
    t = re.sub(r"[.,;:!?\-]", " ", t)
    return " ".join(t.split())

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

def evaluate_slots(pred, gt):
    """Evaluate agreement across 15 fields strictly matching eval_pure_gt_15_fields.py."""
    field_keys = [
        "s0_surgical_no", "s1_side", "s2_proc", "s3_dims", "s4_skin",
        "s5_dims", "s6_nipple", "s7_biopsy_scar", "s8_cavity", "s9_residual_mass",
        "s10_infiltrative", "s10_inf_dims", "s10_5_quadrant", "s11_deep_margin", "s14_check"
    ]
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
    return correct, len(field_keys)

def main():
    print("=" * 90)
    print("RIGOROUS FAIR BENCHMARK: VOSK vs WAV2VEC 2.0 vs BASELINE vs PATHOWHISPER (20 CASES)")
    print("=" * 90)

    # 1. Load Pure Ground Truth
    gt_path = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000_pure.json"
    with open(gt_path, "r", encoding="utf-8") as f:
        gt_all = json.load(f)

    # 2. Load Overnight CSV for Baseline & PathoWhisper
    csv_path = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "benchmark_1000_cases_overnight.csv"
    df = pd.read_csv(csv_path)
    pw_df = df[df.system.str.contains("PathoWhisper", case=False)].set_index("case_id")
    bs_df = df[df.system.str.contains("Baseline", case=False)].set_index("case_id")

    # 3. Load Vosk
    vosk_path = BASE_DIR / "bin" / "vosk-model-small-en-us-0.15"
    print(f"Loading Vosk Kaldi model from {vosk_path.name}...")
    v_model = VoskModel(str(vosk_path))

    # 4. Load Wav2Vec 2.0
    print("Loading Meta Wav2Vec 2.0 (facebook/wav2vec2-base-960h)...")
    w2v_pipe = pipeline("automatic-speech-recognition", model="facebook/wav2vec2-base-960h")

    case_ids = [f"case_{i:04d}" for i in range(1, 21)]
    records = []

    print("\nRunning inference on 20 benchmark audio files...")
    for idx, cid in enumerate(case_ids, 1):
        mp3_path = BASE_DIR / "data" / "dataset_1000" / "audio" / f"{cid}.mp3"
        gt = gt_all.get(cid, {})
        ref_text = bs_df.loc[cid, "ref_text"]
        cat_id = bs_df.loc[cid, "category_id"]
        cat_name = bs_df.loc[cid, "category_name"]

        # Load Audio
        t_load0 = time.time()
        y, sr = librosa.load(str(mp3_path), sr=16000)
        int16_samples = (y * 32767).astype(np.int16)

        # 1. Vosk Inference
        t0 = time.time()
        rec = KaldiRecognizer(v_model, 16000)
        rec.AcceptWaveform(int16_samples.tobytes())
        v_res = json.loads(rec.FinalResult())
        t_vosk = time.time() - t0
        vosk_raw = v_res.get("text", "")
        vosk_itn = apply_itn(vosk_raw)

        # 2. Wav2Vec 2.0 Inference
        t0 = time.time()
        w2v_res = w2v_pipe(y)
        t_w2v = time.time() - t0
        w2v_raw = w2v_res.get("text", "")
        w2v_itn = apply_itn(w2v_raw)

        # 3. Baseline Whisper Small
        bs_raw = bs_df.loc[cid, "hyp_text"]
        bs_itn = apply_itn(bs_raw)
        t_bs = bs_df.loc[cid, "latency_sec"]

        # 4. PathoWhisper INT8
        pw_raw = pw_df.loc[cid, "hyp_text"]
        pw_itn = apply_itn(pw_raw)
        t_pw = pw_df.loc[cid, "latency_sec"]

        # Compute WERs
        # Criteria A (Raw)
        wer_v_raw = wer(norm_criteria_a(ref_text), norm_criteria_a(vosk_raw)) * 100
        wer_w_raw = wer(norm_criteria_a(ref_text), norm_criteria_a(w2v_raw)) * 100
        wer_b_raw = wer(norm_criteria_a(ref_text), norm_criteria_a(bs_raw)) * 100
        wer_p_raw = wer(norm_criteria_a(ref_text), norm_criteria_a(pw_raw)) * 100

        # Fair Criterion B / ITN WER
        wer_v_itn = wer(norm_b(ref_text), norm_b(vosk_itn)) * 100
        wer_w_itn = wer(norm_b(ref_text), norm_b(w2v_itn)) * 100
        wer_b_itn = wer(norm_b(ref_text), norm_b(bs_raw)) * 100
        wer_p_itn = wer(norm_b(ref_text), norm_b(pw_raw)) * 100

        # 15-Section Extractor Agreement
        c_v, tot = evaluate_slots(extract_data_15_sections(vosk_itn), gt)
        c_w, _ = evaluate_slots(extract_data_15_sections(w2v_itn), gt)
        c_b, _ = evaluate_slots(extract_data_15_sections(bs_raw), gt)
        c_p, _ = evaluate_slots(extract_data_15_sections(pw_raw), gt)

        records.append({
            "case_id": cid,
            "category_id": cat_id,
            "category_name": cat_name,
            "ref_text": ref_text,
            "vosk_raw": vosk_raw,
            "vosk_itn": vosk_itn,
            "w2v_raw": w2v_raw,
            "w2v_itn": w2v_itn,
            "bs_hyp": bs_raw,
            "pw_hyp": pw_raw,
            "wer_v_raw": wer_v_raw,
            "wer_v_itn": wer_v_itn,
            "wer_w_raw": wer_w_raw,
            "wer_w_itn": wer_w_itn,
            "wer_b_raw": wer_b_raw,
            "wer_b_itn": wer_b_itn,
            "wer_p_raw": wer_p_raw,
            "wer_p_itn": wer_p_itn,
            "slots_vosk": c_v,
            "slots_w2v": c_w,
            "slots_baseline": c_b,
            "slots_pathowhisper": c_p,
            "lat_vosk": t_vosk,
            "lat_w2v": t_w2v,
            "lat_baseline": t_bs,
            "lat_pathowhisper": t_pw
        })
        print(f"[{idx:02d}/20] {cid} ({cat_name[:20]}): Vosk ITN={wer_v_itn:5.1f}% | W2V2 ITN={wer_w_itn:5.1f}% | Base={wer_b_itn:5.1f}% | PW={wer_p_itn:5.1f}%")

    res_df = pd.DataFrame(records)

    # Save to CSV and JSON
    out_csv = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "fair_empirical_comparison_20cases.csv"
    res_df.to_csv(out_csv, index=False, encoding="utf-8-sig")

    out_json = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "fair_empirical_comparison_20cases.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(json.loads(res_df.to_json(orient="records")), f, ensure_ascii=False, indent=2)

    # Print Summary Tables
    print("\n" + "=" * 90)
    print("FAIR HEAD-TO-HEAD BENCHMARK SUMMARY (20 CASES ACROSS 10 CLINICAL CATEGORIES)")
    print("=" * 90)
    summary_data = [
        ("Vosk (Kaldi HMM-DNN)", res_df['wer_v_raw'].mean(), res_df['wer_v_itn'].mean(),
         res_df['lat_vosk'].mean(), res_df['slots_vosk'].sum() / (20 * 15) * 100),
        ("Meta Wav2Vec 2.0 (CTC)", res_df['wer_w_raw'].mean(), res_df['wer_w_itn'].mean(),
         res_df['lat_w2v'].mean(), res_df['slots_w2v'].sum() / (20 * 15) * 100),
        ("Baseline Whisper Small FP32", res_df['wer_b_raw'].mean(), res_df['wer_b_itn'].mean(),
         res_df['lat_baseline'].mean(), res_df['slots_baseline'].sum() / (20 * 15) * 100),
        ("PathoWhisper INT8 (Proposed)", res_df['wer_p_raw'].mean(), res_df['wer_p_itn'].mean(),
         res_df['lat_pathowhisper'].mean(), res_df['slots_pathowhisper'].sum() / (20 * 15) * 100),
    ]

    print(f"{'ASR Architecture / Model':<30} | {'Raw WER':<10} | {'Fair ITN WER':<13} | {'Latency':<10} | {'Slot Agreement':<15}")
    print("-" * 90)
    for name, raw_w, itn_w, lat, slot_acc in summary_data:
        print(f"{name:<30} | {raw_w:>8.2f}% | {itn_w:>11.2f}% | {lat:>7.2f} s | {slot_acc:>13.2f}%")
    print("=" * 90)

if __name__ == "__main__":
    main()
