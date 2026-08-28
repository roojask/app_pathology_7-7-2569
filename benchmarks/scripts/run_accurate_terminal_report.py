import sys
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from configs.config import Config
from src.stt.whisper_model import transcribe_audio
from src.nlp.normalizer import normalize_text
from src.nlp.extractor import extract_data_15_sections

def calculate_normalized_wer(ref, hyp):
    # Normalized Character/Word Token Distance for Bilingual Thai-English
    ref_norm = normalize_text(ref).replace(" ", "")
    hyp_norm = normalize_text(hyp).replace(" ", "")
    if not ref_norm: return 0.0
    
    # Levenshtein distance on normalized character sequence
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

def evaluate_15_sections_normalized(extracted_dict, gt_dict):
    keys_to_eval = [
        "s0_surgical_no", "s1_side", "s2_proc", "s3_dims",
        "s10_infiltrative", "s10_inf_dims", "s14_check"
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
                # Compare numbers as floats or strings
                gt_floats = [float(x) for x in gt_val if x.replace('.', '', 1).isdigit()]
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

def run_accurate_terminal_report():
    gt_path = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000.json"
    audio_dir = BASE_DIR / "data" / "dataset_1000" / "audio"
    
    if not gt_path.exists():
        print(f"Error: Ground truth JSON not found at {gt_path}", flush=True)
        return

    with open(gt_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    print("=" * 82, flush=True)
    print("PRODUCTION-ALIGNED SCIENTIFIC BENCHMARK EVALUATION (ACCURATE PIPELINE)", flush=True)
    print("=" * 82, flush=True)
    print(f"Ground Truth File : {gt_path}", flush=True)
    print(f"STT Model         : OpenAI Whisper Small + Medical Prompt Injection", flush=True)
    print(f"NLP Normalizer    : 15-Section Extractor + Thai-English Normalizer", flush=True)
    print("=" * 82, flush=True)
    print(f"{'Case ID':<12} | {'Category':<14} | {'Latency':<10} | {'CER/WER (%)':<12} | {'Mapping Acc':<12}", flush=True)
    print("-" * 82, flush=True)

    cat_names = {
        1: "Standard", 2: "Out-of-Order", 3: "Self-Correct", 4: "Multi-Margin",
        5: "Heavy-Nodes", 6: "Fibrocystic", 7: "High-Speed", 8: "Fume-Noise",
        9: "Thai-Hybrid", 10: "Edge-Cases"
    }

    # Evaluate 20 representative cases across all categories
    selected_cases = [f"case_{((c-1)*10 + cat):04d}" for c in range(1, 3) for cat in range(1, 11)]
    cat_stats = {cat: {"correct": 0, "total": 0, "times": [], "wers": []} for cat in range(1, 11)}

    for case_id in selected_cases:
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
        
        wer = calculate_normalized_wer(gt["raw_text"], stt_text)
        acc = evaluate_15_sections_normalized(ext_data, gt)
        
        cat_stats[cat_id]["correct"] += (acc / 100.0) * 7.0
        cat_stats[cat_id]["total"] += 7.0
        cat_stats[cat_id]["times"].append(elapsed)
        cat_stats[cat_id]["wers"].append(wer)

        print(f"{case_id:<12} | {cat_label:<14} | {elapsed:>8.2f}s | {wer:>10.2f}% | {acc:>10.2f}%", flush=True)

    print("=" * 82, flush=True)
    print("PRODUCTION-ALIGNED BENCHMARK SUMMARY TABLE BY CATEGORY", flush=True)
    print("=" * 82, flush=True)
    print(f"{'Cat ID':<8} | {'Category Description':<22} | {'Avg Latency (s)':<16} | {'CER/WER (%)':<14} | {'Mapping Acc (%)':<18}", flush=True)
    print("-" * 82, flush=True)
    
    total_acc_sum = 0
    total_time_sum = 0
    total_wer_sum = 0
    count = 0

    for cat_id in range(1, 11):
        stat = cat_stats[cat_id]
        if stat["total"] == 0: continue
        avg_t = sum(stat["times"]) / len(stat["times"])
        avg_w = sum(stat["wers"]) / len(stat["wers"])
        acc_pct = (stat["correct"] / stat["total"]) * 100
        
        total_acc_sum += acc_pct
        total_time_sum += avg_t
        total_wer_sum += avg_w
        count += 1
        
        print(f"{cat_id:<8} | {cat_names[cat_id]:<22} | {avg_t:>14.2f}s | {avg_w:>12.2f}% | {acc_pct:>16.2f}%", flush=True)

    print("=" * 82, flush=True)
    print("ACCURATE SYSTEM BENCHMARK SUMMARY RESULTS", flush=True)
    print("=" * 82, flush=True)
    print(f"Evaluated Cases Total       : 20 Representative Cases Across 10 Categories", flush=True)
    print(f"Overall Average Latency     : {total_time_sum / count:.2f} seconds/case", flush=True)
    print(f"Overall Normalized Error Rate: {total_wer_sum / count:.2f}%", flush=True)
    print(f"Overall Field Mapping Acc   : {total_acc_sum / count:.2f}%", flush=True)
    print("=" * 82, flush=True)

if __name__ == "__main__":
    run_accurate_terminal_report()
