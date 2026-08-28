import sys
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DATASET_DIR = BASE_DIR / "data" / "dataset_1000"
GT_JSON_PATH = DATASET_DIR / "ground_truth_1000.json"

import whisper
from src.stt.whisper_model import denoise_audio
from src.nlp.normalizer import normalize_text
from src.nlp.extractor import extract_data_15_sections

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

def compute_4_subgroups():
    with open(GT_JSON_PATH, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    # 4 Main Environment Groups Breakdown from Category IDs
    # Cat 8: Fume Hood Noise (100 cases)
    # Cat 3: Self-Correction (100 cases)
    # Cat 7: Rapid High-Speed Dictation (100 cases)
    # Cat 1, 2, 4, 5, 6, 9, 10: Clean Audio (700 cases)
    
    # We parse log output of task-2713 or compute directly
    log_path = BASE_DIR / "benchmarks" / "baseline_whisper_small_1000_log.txt"
    
    # Let's aggregate by category IDs:
    # Cat 1: Standard Breast Pathology (100)
    # Cat 2: Out-of-Order Section Dictation (100)
    # Cat 3: Self-Correction Speech (100)
    # Cat 4: Multi-Margin Complex (100)
    # Cat 5: Heavy Lymph Node Count (100)
    # Cat 6: Fibrocystic / No Discrete Mass (100)
    # Cat 7: High-Speed Rapid Compact (100)
    # Cat 8: Fume Hood Fan Noise (100)
    # Cat 9: Ductal Carcinoma / Atypical Lesion (100)
    # Cat 10: Edge Cases & Missing Fields (100)
    
    # Data per category from task-2713 run:
    cat_stats = {
        1:  {"name": "Standard Breast Pathology", "lat": 10.56, "wer": 14.77, "cer": 3.47, "acc": 80.00},
        2:  {"name": "Out-of-Order Section Dictation", "lat": 9.55, "wer": 16.12, "cer": 5.40, "acc": 79.60},
        3:  {"name": "Self-Correction Speech", "lat": 6.48, "wer": 19.45, "cer": 5.91, "acc": 89.73},
        4:  {"name": "Multi-Margin Complex", "lat": 10.22, "wer": 19.99, "cer": 5.95, "acc": 80.53},
        5:  {"name": "Heavy Lymph Node Count", "lat": 5.31, "wer": 17.94, "cer": 5.04, "acc": 90.27},
        6:  {"name": "Fibrocystic / No Discrete Mass", "lat": 5.31, "wer": 18.84, "cer": 4.52, "acc": 100.00},
        7:  {"name": "High-Speed Rapid Compact", "lat": 5.87, "wer": 47.86, "cer": 12.06, "acc": 76.33},
        8:  {"name": "Fume Hood Fan Noise (-10dB)", "lat": 5.39, "wer": 36.54, "cer": 8.70, "acc": 91.00},
        9:  {"name": "Ductal Carcinoma / Atypical Lesion", "lat": 7.68, "wer": 26.75, "cer": 9.20, "acc": 79.67},
        10: {"name": "Edge Cases & Missing Fields", "lat": 4.78, "wer": 22.78, "cer": 4.91, "acc": 79.07}
    }

    # Group 1: Clean Audio (Cats 1, 2, 4, 5, 6, 9, 10 = 700 cases)
    clean_cats = [1, 2, 4, 5, 6, 9, 10]
    clean_count = 700
    clean_wer = round(sum(cat_stats[c]["wer"] for c in clean_cats) / len(clean_cats), 2)
    clean_cer = round(sum(cat_stats[c]["cer"] for c in clean_cats) / len(clean_cats), 2)
    clean_acc = round(sum(cat_stats[c]["acc"] for c in clean_cats) / len(clean_cats), 2)

    # Group 2: Fume Hood Noise (Cat 8 = 100 cases)
    fh_count = 100
    fh_wer = cat_stats[8]["wer"]
    fh_cer = cat_stats[8]["cer"]
    fh_acc = cat_stats[8]["acc"]

    # Group 3: Self-Correction (Cat 3 = 100 cases)
    sc_count = 100
    sc_wer = cat_stats[3]["wer"]
    sc_cer = cat_stats[3]["cer"]
    sc_acc = cat_stats[3]["acc"]

    # Group 4: Rapid High-Speed Dictation (Cat 7 = 100 cases)
    rh_count = 100
    rh_wer = cat_stats[7]["wer"]
    rh_cer = cat_stats[7]["cer"]
    rh_acc = cat_stats[7]["acc"]

    print("=" * 100)
    print("SUB-GROUP ANALYSIS TABLE (4 MAIN ENVIRONMENT GROUPS - 100% ENGLISH DATASET)")
    print("=" * 100)
    print(f"{'สภาวะแวดล้อมหลัก (Environment Sub-Group)':<48} | {'จำนวนเคส':<10} | {'Mapping Acc (%)':<15} | {'WER (%)':<10} | {'CER (%)':<10}")
    print("-" * 100)
    print(f"{'สภาพแวดล้อมเงียบปกติ (Clean Audio)':<48} | {clean_count:<10} | {clean_acc:>14.2f}% | {clean_wer:>8.2f}% | {clean_cer:>8.2f}%")
    print(f"{'สภาพแวดล้อมมีเสียงตู้ดูดควัน (Fume Hood Noise)':<48} | {fh_count:<10} | {fh_acc:>14.2f}% | {fh_wer:>8.2f}% | {fh_cer:>8.2f}%")
    print(f"{'การพูดแก้ไขคำตนเอง (Self-Correction)':<48} | {sc_count:<10} | {sc_acc:>14.2f}% | {sc_wer:>8.2f}% | {sc_cer:>8.2f}%")
    print(f"{'การบรรยายความเร็วสูงกระชับ (Rapid High-Speed)':<48} | {rh_count:<10} | {rh_acc:>14.2f}% | {rh_wer:>8.2f}% | {rh_cer:>8.2f}%")
    print("=" * 100)

if __name__ == "__main__":
    compute_4_subgroups()
