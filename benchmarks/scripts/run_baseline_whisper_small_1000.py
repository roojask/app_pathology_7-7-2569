import sys
import json
import time
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DATASET_DIR = BASE_DIR / "data" / "dataset_1000"
GT_JSON_PATH = DATASET_DIR / "ground_truth_1000.json"
AUDIO_DIR = DATASET_DIR / "audio"

import whisper
from src.stt.whisper_model import denoise_audio
from src.nlp.normalizer import normalize_text
from src.nlp.extractor import extract_data_15_sections

_pytorch_whisper_model = None

def get_pytorch_whisper_model():
    global _pytorch_whisper_model
    if _pytorch_whisper_model is None:
        print("[Loading] Loading Standard PyTorch Whisper Small Model (Baseline)...", flush=True)
        _pytorch_whisper_model = whisper.load_model("small")
        print("[Success] PyTorch Whisper Small Model Loaded!", flush=True)
    return _pytorch_whisper_model

def calculate_cer(ref, hyp):
    ref_norm = normalize_text(ref)
    hyp_norm = normalize_text(hyp)
    if not ref_norm: return 0.0
    
    m, n = len(ref_norm), len(hyp_norm)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1): dp[i][0] = i
    for j in range(n + 1): dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_norm[i-1] == hyp_norm[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
                
    cer = (dp[m][n] / max(m, 1)) * 100.0
    return round(cer, 2)

def calculate_wer(ref, hyp):
    ref_n = normalize_text(ref)
    hyp_n = normalize_text(hyp)
    ref_n = re.sub(r'([\d.]+)\s*x\s*([\d.]+)', r'\1 x \2', ref_n)
    hyp_n = re.sub(r'([\d.]+)\s*x\s*([\d.]+)', r'\1 x \2', hyp_n)
    ref_words = [w.strip('.,;:') for w in ref_n.split() if w.strip('.,;:')]
    hyp_words = [w.strip('.,;:') for w in hyp_n.split() if w.strip('.,;:')]
    if not ref_words: return 0.0
    
    m, n = len(ref_words), len(hyp_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1): dp[i][0] = i
    for j in range(n + 1): dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_words[i-1] == hyp_words[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
                
    wer = (dp[m][n] / max(m, 1)) * 100.0
    return round(wer, 2)

def evaluate_15_sections(extracted_dict, gt_dict):
    keys_to_eval = [
        "s0_surgical_no", "s1_side", "s2_proc", "s3_dims", "s4_skin",
        "s5_dims", "s6_nipple", "s7_biopsy_scar", "s8_cavity", "s9_residual_mass",
        "s10_infiltrative", "s10_inf_dims", "s10_5_quadrant_check", "s12_margins", "s14_check"
    ]
    correct = 0
    total = len(keys_to_eval)
    
    for k in keys_to_eval:
        gt_val = gt_dict.get(k)
        ext_val = extracted_dict.get(k)
        
        if gt_val is None or gt_val == "" or gt_val == [] or gt_val is False:
            if ext_val is None or ext_val == "" or ext_val == [] or ext_val is False:
                correct += 1
            continue
            
        if isinstance(gt_val, list):
            if isinstance(ext_val, list):
                gt_str = "".join(map(str, gt_val)).lower().replace(".0", "")
                ext_str = "".join(map(str, ext_val)).lower().replace(".0", "")
                if gt_str == ext_str or gt_str in ext_str:
                    correct += 1
        elif isinstance(gt_val, bool):
            if ext_val == gt_val:
                correct += 1
        else:
            if str(gt_val).lower().strip() == str(ext_val).lower().strip():
                correct += 1
                
    return round((correct / total) * 100.0, 2)

def run_baseline_whisper_small_1000():
    print("=" * 100, flush=True)
    print("STARTING STANDARD PYTORCH WHISPER SMALL (BASELINE) SCIENTIFIC BENCHMARK (1,000 AUDIO CASES)", flush=True)
    print("=" * 100, flush=True)
    print(f"Ground Truth JSON : {GT_JSON_PATH}", flush=True)
    print(f"Audio Cases Dir   : {AUDIO_DIR}", flush=True)
    print("=" * 100, flush=True)

    with open(GT_JSON_PATH, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    category_names = {
        1: "Standard Breast Pathology",
        2: "Out-of-Order Section Dictation",
        3: "Self-Correction Speech",
        4: "Multi-Margin Complex",
        5: "Heavy Lymph Node Count",
        6: "Fibrocystic / No Discrete Mass",
        7: "High-Speed Rapid Compact",
        8: "Fume Hood Fan Noise (-10dB)",
        9: "Ductal Carcinoma / Atypical Lesion",
        10: "Edge Cases & Missing Fields"
    }

    model = get_pytorch_whisper_model()
    results = []
    text_extraction_scores = []
    total_start_time = time.time()

    print(f"{'Case ID':<12} | {'Category':<34} | {'Latency (s)':<12} | {'WER (%)':<10} | {'CER (%)':<10} | {'Mapping Acc (%)':<15}", flush=True)
    print("-" * 100, flush=True)

    for i in range(1, 1001):
        case_id = f"case_{i:04d}"
        if case_id not in gt_data: continue
        
        gt = gt_data[case_id]
        cat_id = gt.get("category_id", ((i - 1) % 10) + 1)
        cat_name = category_names.get(cat_id, "Unknown Category")
        gt_raw_text = gt.get("raw_text", "")
        audio_filename = gt.get("audio_filename", f"{case_id}.mp3")
        audio_path = AUDIO_DIR / audio_filename

        # Direct NLP Extractor Accuracy on Raw Text
        text_ext_dict = extract_data_15_sections(gt_raw_text)
        text_acc = evaluate_15_sections(text_ext_dict, gt)
        text_extraction_scores.append(text_acc)

        # Audio Pipeline via Standard PyTorch Whisper Small (Baseline)
        case_start = time.time()
        stt_text = ""
        try:
            denoised_path = denoise_audio(audio_path)
            res = model.transcribe(str(denoised_path), language="en")
            stt_text = res.get("text", "")
        except Exception:
            try:
                res = model.transcribe(str(audio_path), language="en")
                stt_text = res.get("text", "")
            except Exception:
                stt_text = ""

        latency = round(time.time() - case_start, 2)
        wer = calculate_wer(gt_raw_text, stt_text)
        cer = calculate_cer(gt_raw_text, stt_text)

        extracted_dict = extract_data_15_sections(stt_text)
        mapping_acc = evaluate_15_sections(extracted_dict, gt)

        res_entry = {
            "case_id": case_id,
            "category_id": cat_id,
            "category": cat_name,
            "latency": latency,
            "wer": wer,
            "cer": cer,
            "mapping_acc": mapping_acc
        }
        results.append(res_entry)

        print(f"{case_id:<12} | {cat_name:<34} | {latency:>10.2f}s | {wer:>8.2f}% | {cer:>8.2f}% | {mapping_acc:>14.2f}%", flush=True)

    total_runtime = round(time.time() - total_start_time, 2)
    avg_latency = round(sum(r["latency"] for r in results) / len(results), 2)
    avg_wer = round(sum(r["wer"] for r in results) / len(results), 2)
    avg_cer = round(sum(r["cer"] for r in results) / len(results), 2)
    avg_mapping_acc = round(sum(r["mapping_acc"] for r in results) / len(results), 2)
    avg_text_acc = round(sum(text_extraction_scores) / len(text_extraction_scores), 2)

    # Output Academic Table 1: KPI Summary
    print("\n" + "=" * 100, flush=True)
    print("TABLE 1: HIGH-LEVEL ACADEMIC KPI SUMMARY TABLE (BASELINE PYTORCH WHISPER SMALL)", flush=True)
    print("=" * 100, flush=True)
    print(f"{'ตัวชี้วัดผลทางวิชาการ (Academic KPI Metric)':<55} | {'ค่าประสิทธิภาพที่วัดได้ (Measured Value)':<35}", flush=True)
    print("-" * 100, flush=True)
    print(f"{'Direct Text Extraction Accuracy (ข้อความ)':<55} | {avg_text_acc:>33.2f}%", flush=True)
    print(f"{'Overall Audio Pipeline Mapping Accuracy (ไฟล์เสียง)':<55} | {avg_mapping_acc:>33.2f}%", flush=True)
    print(f"{'Word Error Rate (WER)':<55} | {avg_wer:>33.2f}%", flush=True)
    print(f"{'Character Error Rate (CER)':<55} | {avg_cer:>33.2f}%", flush=True)
    print(f"{'Average Processing Latency':<55} | {avg_latency:>28.2f} s/case", flush=True)
    print("=" * 100, flush=True)

    # Output Academic Table 2: 10 Categories Breakdown
    print("\n" + "=" * 100, flush=True)
    print("TABLE 2: CATEGORY BENCHMARK SUMMARY TABLE (10 CATEGORIES - BASELINE PYTORCH WHISPER SMALL)", flush=True)
    print("=" * 100, flush=True)
    print(f"{'Cat ID':<8} | {'Category Description':<34} | {'Avg Latency (s)':<16} | {'WER (%)':<10} | {'CER (%)':<10} | {'Mapping Acc (%)':<15}", flush=True)
    print("-" * 100, flush=True)

    for cat_id in range(1, 11):
        cat_res = [r for r in results if r["category_id"] == cat_id]
        if not cat_res: continue
        c_name = category_names[cat_id]
        c_lat = round(sum(r["latency"] for r in cat_res) / len(cat_res), 2)
        c_wer = round(sum(r["wer"] for r in cat_res) / len(cat_res), 2)
        c_cer = round(sum(r["cer"] for r in cat_res) / len(cat_res), 2)
        c_acc = round(sum(r["mapping_acc"] for r in cat_res) / len(cat_res), 2)
        print(f"{cat_id:<8} | {c_name:<34} | {c_lat:>14.2f}s | {c_wer:>8.2f}% | {c_cer:>8.2f}% | {c_acc:>14.2f}%", flush=True)

    print("=" * 100, flush=True)
    print(f"Total Benchmark Runtime: {total_runtime} seconds", flush=True)

if __name__ == "__main__":
    run_baseline_whisper_small_1000()
