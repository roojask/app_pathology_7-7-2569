import sys
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from src.stt.whisper_model import transcribe_audio
from src.nlp.normalizer import normalize_text
from src.nlp.extractor import extract_data_15_sections

def calculate_simple_wer(ref, hyp):
    ref_words = ref.lower().split()
    hyp_words = hyp.lower().split()
    if not ref_words: return 0.0
    errors = abs(len(ref_words) - len(hyp_words))
    for r, h in zip(ref_words, hyp_words):
        if r != h: errors += 1
    return round((errors / len(ref_words)) * 100, 2)

def evaluate_15_sections(extracted_dict, gt_dict):
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
                gt_str = "".join(map(str, gt_val)).lower().replace(".0", "")
                ext_str = "".join(map(str, ext_val)).lower().replace(".0", "")
                if gt_str == ext_str or gt_str in ext_str or ext_str in gt_str:
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

def evaluate_terminal_benchmark():
    gt_path = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000.json"
    audio_dir = BASE_DIR / "data" / "dataset_1000" / "audio"
    
    if not gt_path.exists():
        print(f"Error: Ground truth JSON not found at {gt_path}")
        return

    with open(gt_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    print("=" * 80)
    print("SCIENTIFIC BENCHMARK EVALUATION RUN (LIVE TERMINAL OUTPUT)")
    print("=" * 80)
    print(f"Dataset Path  : {gt_path}")
    print(f"Audio Path    : {audio_dir}")
    print(f"STT Model     : OpenAI Whisper Small (Standard Baseline)")
    print(f"NLP Engine    : 15-Section Medical Extractor + Phonetic Normalizer")
    print("=" * 80)
    print(f"{'Case ID':<12} | {'Category':<12} | {'STT Time':<10} | {'WER (%)':<10} | {'Mapping Acc':<12} | {'Status':<8}")
    print("-" * 80)

    # Evaluate 30 representative cases across all 10 categories (3 cases per category)
    selected_cases = [f"case_{((c-1)*10 + cat):04d}" for c in range(1, 4) for cat in range(1, 11)]
    
    cat_names = {
        1: "Standard", 2: "Out-of-Order", 3: "Self-Correct", 4: "Multi-Margin",
        5: "Heavy-Nodes", 6: "Fibrocystic", 7: "High-Speed", 8: "Fume-Noise",
        9: "Thai-Hybrid", 10: "Edge-Cases"
    }

    results = []
    cat_stats = {cat: {"correct": 0, "total": 0, "times": [], "wers": []} for cat in range(1, 11)}

    for idx, case_id in enumerate(selected_cases, 1):
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
        
        acc = evaluate_15_sections(ext_data, gt)
        
        cat_stats[cat_id]["correct"] += (acc / 100.0) * 7.0
        cat_stats[cat_id]["total"] += 7.0
        cat_stats[cat_id]["times"].append(elapsed)
        cat_stats[cat_id]["wers"].append(wer)

        status_str = "PASS" if acc >= 66.6 else "PARTIAL"
        print(f"{case_id:<12} | {cat_label:<12} | {elapsed:>8.2f}s | {wer:>8.2f}% | {acc:>10.2f}% | {status_str:<8}")

    print("=" * 80)
    print("CATEGORY-BY-CATEGORY BENCHMARK SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Cat ID':<8} | {'Category Name':<18} | {'Avg Latency (s)':<16} | {'Avg WER (%)':<12} | {'Mapping Acc (%)':<15}")
    print("-" * 80)
    
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
        
        print(f"{cat_id:<8} | {cat_names[cat_id]:<18} | {avg_t:>14.2f}s | {avg_w:>10.2f}% | {acc_pct:>13.2f}%")

    print("=" * 80)
    print("FINAL SYSTEM BENCHMARK RESULTS")
    print("=" * 80)
    print(f"Evaluated Cases Summary     : 30 Representative Benchmark Cases")
    print(f"Overall Average Latency     : {total_time_sum / count:.2f} s/case")
    print(f"Overall Word Error Rate     : {total_wer_sum / count:.2f}%")
    print(f"Overall Field Mapping Acc   : {total_acc_sum / count:.2f}%")
    print("=" * 80)

if __name__ == "__main__":
    evaluate_terminal_benchmark()
