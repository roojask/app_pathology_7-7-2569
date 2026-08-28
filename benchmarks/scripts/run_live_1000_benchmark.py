import sys
import json
import time
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from configs.config import Config
from src.stt.whisper_model import transcribe_audio
from src.nlp.normalizer import normalize_text
from src.nlp.extractor import extract_data_15_sections

def calculate_levenshtein_cer(ref, hyp):
    ref_norm = re.sub(r'\s+', '', ref.lower())
    hyp_norm = re.sub(r'\s+', '', hyp.lower())
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

def calculate_simple_wer(ref, hyp):
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

def evaluate_15_sections_accuracy(extracted_dict, gt_dict):
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
                gt_floats = [float(x) for x in gt_val if isinstance(x, str) and x.replace('.', '', 1).isdigit()]
                ext_floats = [float(x) for x in ext_val if isinstance(x, str) and x.replace('.', '', 1).isdigit()]
                if gt_floats and ext_floats and len(gt_floats) == len(ext_floats):
                    correct += 1
                elif "".join(map(str, gt_val)) in "".join(map(str, ext_val)):
                    correct += 1
        elif isinstance(gt_val, bool):
            if ext_val == gt_val:
                correct += 1
        else:
            gt_s = str(gt_val).lower().strip().replace("-", "")
            ext_s = str(ext_val).lower().strip().replace("-", "")
            if gt_s == ext_s or gt_s in ext_s or ext_s in gt_s:
                correct += 1
                
    return (correct / total) * 100.0

def run_live_1000_benchmark():
    gt_path = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000.json"
    audio_dir = BASE_DIR / "data" / "dataset_1000" / "audio"
    
    if not gt_path.exists():
        print(f"Error: Ground truth JSON not found at {gt_path}", flush=True)
        return

    with open(gt_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    cat_names = {
        1: "Standard Breast Pathology", 
        2: "Out-of-Order Section Dictation", 
        3: "Self-Correction Speech", 
        4: "Multi-Margin Complex",
        5: "Heavy Lymph Node Count", 
        6: "Fibrocystic / No Discrete Mass", 
        7: "High-Speed Rapid Compact", 
        8: "Fume Hood Fan Noise (-10dB)",
        9: "Thai-English Hybrid Speech", 
        10: "Edge Cases & Missing Fields"
    }

    print("=" * 100, flush=True)
    print("STARTING COMPLETE SCIENTIFIC BENCHMARK EVALUATION (1,000 AUDIO CASES FROM SCRATCH)", flush=True)
    print("=" * 100, flush=True)
    print(f"Ground Truth JSON : {gt_path}", flush=True)
    print(f"Audio Cases Dir   : {audio_dir}", flush=True)
    print("=" * 100, flush=True)

    # 1. Direct Text Extraction Accuracy
    text_correct = 0
    text_total = 0
    for case_id, gt in gt_data.items():
        norm = normalize_text(gt.get("raw_text", ""))
        ext = extract_data_15_sections(norm)
        acc = evaluate_15_sections_accuracy(ext, gt)
        text_correct += (acc / 100.0) * 7.0
        text_total += 7.0

    direct_text_acc = (text_correct / max(text_total, 1.0)) * 100.0

    # 2. Live Audio Cases Loop Across All 1,000 Cases
    case_results = []
    cat_stats = {cat: {"correct": 0, "total": 0, "times": [], "wers": [], "cers": []} for cat in range(1, 11)}

    print(f"{'Case ID':<12} | {'Category':<30} | {'Latency (s)':<12} | {'WER (%)':<10} | {'CER (%)':<10} | {'Mapping Acc (%)':<15}", flush=True)
    print("-" * 100, flush=True)

    start_bench_time = time.time()

    for i in range(1, 1001):
        case_id = f"case_{i:04d}"
        if case_id not in gt_data: continue
        gt = gt_data[case_id]
        cat_id = gt["category_id"]
        cat_label = cat_names.get(cat_id, f"Cat-{cat_id}")
        audio_file = audio_dir / gt["audio_filename"]
        
        t0 = time.time()
        stt_text = transcribe_audio(audio_file)
        elapsed = time.time() - t0
        
        norm_text = normalize_text(stt_text)
        ext_data = extract_data_15_sections(norm_text)
        
        wer = calculate_simple_wer(gt["raw_text"], stt_text)
        cer = calculate_levenshtein_cer(gt["raw_text"], stt_text)
        acc = evaluate_15_sections_accuracy(ext_data, gt)
        
        cat_stats[cat_id]["correct"] += (acc / 100.0) * 7.0
        cat_stats[cat_id]["total"] += 7.0
        cat_stats[cat_id]["times"].append(elapsed)
        cat_stats[cat_id]["wers"].append(wer)
        cat_stats[cat_id]["cers"].append(cer)

        res = {
            "case_id": case_id,
            "category": cat_label,
            "category_id": cat_id,
            "latency": elapsed,
            "wer": wer,
            "cer": cer,
            "mapping_acc": acc
        }
        case_results.append(res)

        print(f"{case_id:<12} | {cat_label:<30} | {elapsed:>10.2f}s | {wer:>8.2f}% | {cer:>8.2f}% | {acc:>13.2f}%", flush=True)

    total_bench_elapsed = time.time() - start_bench_time

    # Calculate Summaries
    overall_audio_acc = sum((cat_stats[c]["correct"]/cat_stats[c]["total"])*100 for c in range(1,11))/10.0
    overall_wer = sum(sum(cat_stats[c]["wers"])/len(cat_stats[c]["wers"]) for c in range(1,11))/10.0
    overall_cer = sum(sum(cat_stats[c]["cers"])/len(cat_stats[c]["cers"]) for c in range(1,11))/10.0
    overall_lat = sum(sum(cat_stats[c]["times"])/len(cat_stats[c]["times"]) for c in range(1,11))/10.0

    print("\n" + "=" * 100, flush=True)
    print("TABLE 1: HIGH-LEVEL ACADEMIC KPI SUMMARY TABLE (ตารางตัวชี้วัดผลทางวิชาการ)", flush=True)
    print("=" * 100, flush=True)
    print(f"{'ตัวชี้วัดผลทางวิชาการ (Academic KPI Metric)':<55} | {'ค่าประสิทธิภาพที่วัดได้ (Measured Value)':<35}", flush=True)
    print("-" * 100, flush=True)
    print(f"{'Direct Text Extraction Accuracy (ข้อความ)':<55} | {direct_text_acc:>32.2f}%", flush=True)
    print(f"{'Overall Audio Pipeline Mapping Accuracy (ไฟล์เสียง)':<55} | {overall_audio_acc:>32.2f}%", flush=True)
    print(f"{'Word Error Rate (WER)':<55} | {overall_wer:>32.2f}%", flush=True)
    print(f"{'Character Error Rate (CER)':<55} | {overall_cer:>32.2f}%", flush=True)
    print(f"{'Average Processing Latency':<55} | {overall_lat:>28.2f} s/case", flush=True)
    print("=" * 100, flush=True)

    print("\n" + "=" * 100, flush=True)
    print("TABLE 2: CATEGORY BENCHMARK SUMMARY TABLE (10 CATEGORIES)", flush=True)
    print("=" * 100, flush=True)
    print(f"{'Cat ID':<8} | {'Category Description':<32} | {'Avg Latency (s)':<16} | {'WER (%)':<10} | {'CER (%)':<10} | {'Mapping Acc (%)':<15}", flush=True)
    print("-" * 100, flush=True)
    
    for cat_id in range(1, 11):
        stat = cat_stats[cat_id]
        avg_t = sum(stat["times"]) / len(stat["times"])
        avg_w = sum(stat["wers"]) / len(stat["wers"])
        avg_c = sum(stat["cers"]) / len(stat["cers"])
        acc_p = (stat["correct"] / stat["total"]) * 100.0
        print(f"{cat_id:<8} | {cat_names[cat_id]:<32} | {avg_t:>14.2f}s | {avg_w:>8.2f}% | {avg_c:>8.2f}% | {acc_p:>13.2f}%", flush=True)

    print("=" * 100, flush=True)
    print(f"Total Benchmark Runtime: {total_bench_elapsed:.2f} seconds", flush=True)

    # Save complete JSON report
    with open(BASE_DIR / "benchmarks" / "live_1000_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "kpi_summary": {
                "direct_text_acc": direct_text_acc,
                "overall_audio_acc": overall_audio_acc,
                "overall_wer": overall_wer,
                "overall_cer": overall_cer,
                "overall_latency": overall_lat
            },
            "cases": case_results
        }, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_live_1000_benchmark()
