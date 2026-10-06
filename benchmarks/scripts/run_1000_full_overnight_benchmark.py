"""
run_1000_full_overnight_benchmark.py
================================================================================
Comprehensive Overnight Benchmark: Evaluates all 1,000 Clinical Pathology Cases
Head-to-Head: Baseline Whisper Small (FP32, Beam 5) vs. PathoWhisper (INT8, afftdn, Prompt)
Features:
  - Real-time Checkpointing (resumes gracefully if interrupted)
  - Detailed CSV Logging (case_id, category, system, ref, hyp, latency, wer, cer, field_acc)
  - Automatic Summary Calculation (Micro/Macro WER/CER, RTF, Category Breakdown)
  - Automatic LaTeX Table Generation for Chapter 4
================================================================================
"""

import sys
import os
import json
import time
import re
import csv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

# Ensure bin/ffmpeg is in PATH
os.environ['PATH'] = str(BASE_DIR / 'bin') + os.pathsep + os.environ.get('PATH', '')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from faster_whisper import WhisperModel
import jiwer

from configs.config import Config
from src.stt.whisper_model import denoise_audio
from src.nlp.normalizer import normalize_text
from src.nlp.extractor import extract_data_15_sections

# Paths
DATASET_DIR = BASE_DIR / "data" / "dataset_1000"
GT_PATH = DATASET_DIR / "ground_truth_1000.json"
AUDIO_DIR = DATASET_DIR / "audio"

OUT_DIR = BASE_DIR / "benchmarks" / "thesis_eval_outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CSV_LOG_PATH = OUT_DIR / "benchmark_1000_cases_overnight.csv"
CHECKPOINT_PATH = OUT_DIR / "benchmark_1000_checkpoint.json"
SUMMARY_JSON_PATH = OUT_DIR / "benchmark_1000_summary_metrics.json"
CAT_CSV_PATH = OUT_DIR / "benchmark_1000_category_breakdown.csv"
LATEX_TABLES_PATH = OUT_DIR / "benchmark_1000_latex_tables.tex"

CATEGORY_NAMES = {
    1: "Standard Protocol",
    2: "Out-of-Order Reporting",
    3: "Self-Correction & Hesitation",
    4: "Multi-Margin Complex Assessment",
    5: "Heavy Axillary Lymph Nodes Staging",
    6: "Fibrocystic / Benign Negative Control",
    7: "High-Speed Rapid Speech",
    8: "Fume Hood Noise (-10 dB)",
    9: "Ductal Carcinoma / Microinvasion",
    10: "Clinical Edge Cases & Missing Fields"
}

def clean_for_wer(text):
    if not text: return ""
    t = str(text).lower()
    t = re.sub(r'[.,;:!?\-]', ' ', t)
    return " ".join(t.split())

def calc_wer_cer(ref, hyp):
    r = clean_for_wer(ref)
    h = clean_for_wer(hyp)
    if not r or not h: return 100.0, 100.0
    w = round(jiwer.wer(r, h) * 100.0, 2)
    c = round(jiwer.cer(r, h) * 100.0, 2)
    return w, c

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
                
    return round((correct / total) * 100.0, 2)

def main():
    print("=" * 90, flush=True)
    print("🚀 LAUNCHING FULL OVERNIGHT BENCHMARK (1,000 PATHOLOGY CASES)", flush=True)
    print("   Comparing Baseline Whisper Small (FP32) vs. PathoWhisper (INT8)", flush=True)
    print("=" * 90, flush=True)

    with open(GT_PATH, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    total_cases = len(gt_data)
    print(f"Total Ground Truth Cases: {total_cases}", flush=True)

    # Load checkpoint
    completed_cases = set()
    checkpoint_data = {"baseline": {}, "pathowhisper": {}}
    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                checkpoint_data = json.load(f)
            # Find cases where both baseline and pathowhisper are done
            b_done = set(checkpoint_data.get("baseline", {}).keys())
            p_done = set(checkpoint_data.get("pathowhisper", {}).keys())
            completed_cases = b_done.intersection(p_done)
            print(f"[Checkpoint] Resuming run: {len(completed_cases)} cases already finished!", flush=True)
        except Exception as e:
            print(f"[Warning] Could not load checkpoint: {e}", flush=True)

    # Initialize CSV if not exists
    if not CSV_LOG_PATH.exists():
        with open(CSV_LOG_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "case_id", "category_id", "category_name", "system",
                "latency_sec", "wer", "cer", "field_acc",
                "ref_text", "hyp_text"
            ])

    # Preload Models once for peak stability & speed
    print("\n[Loading Models] Initializing CTranslate2 Engines...", flush=True)
    t0_load = time.time()
    m_baseline = WhisperModel("small", device="cpu", compute_type="float32")
    m_pathowhisper = WhisperModel("small", device="cpu", compute_type="int8")
    print(f"[Loading Models] Both models preloaded successfully in {time.time()-t0_load:.2f}s!\n", flush=True)

    case_keys = sorted(gt_data.keys(), key=lambda x: int(x.split('_')[1]) if '_' in x else 0)
    
    start_time_all = time.time()
    processed_count = len(completed_cases)

    for idx, cid in enumerate(case_keys, 1):
        if cid in completed_cases:
            continue

        gt = gt_data[cid]
        cat_id = gt.get("category_id", 1)
        cat_name = CATEGORY_NAMES.get(cat_id, f"Category {cat_id}")
        ref_text = gt.get("raw_text", "")
        audio_filename = gt.get("audio_filename", f"{cid}.mp3")
        raw_audio_path = AUDIO_DIR / audio_filename

        if not raw_audio_path.exists():
            print(f"⚠️ [Missing] Audio file not found: {raw_audio_path}, skipping...", flush=True)
            continue

        case_t0 = time.time()

        # -------------------------------------------------------------
        # 1. EVALUATE BASELINE (FP32, Beam 5, No afftdn, No Prompt)
        # -------------------------------------------------------------
        if cid in checkpoint_data.get("baseline", {}):
            b_res = checkpoint_data["baseline"][cid]
        else:
            t0_b = time.time()
            segments_b, _ = m_baseline.transcribe(str(raw_audio_path), beam_size=5, language="en")
            hyp_b = " ".join([s.text for s in segments_b]).strip()
            lat_b = round(time.time() - t0_b, 2)
            wer_b, cer_b = calc_wer_cer(ref_text, hyp_b)
            ext_b = extract_data_15_sections(normalize_text(hyp_b))
            acc_b = evaluate_15_sections_accuracy(ext_b, gt)

            b_res = {
                "latency_sec": lat_b, "wer": wer_b, "cer": cer_b, "field_acc": acc_b,
                "hyp_text": hyp_b
            }
            checkpoint_data["baseline"][cid] = b_res

            # Log to CSV
            with open(CSV_LOG_PATH, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([cid, cat_id, cat_name, "Baseline (Whisper Small FP32)", lat_b, wer_b, cer_b, acc_b, ref_text, hyp_b])

        # -------------------------------------------------------------
        # 2. EVALUATE PATHOWHISPER (INT8, Beam 1, afftdn, CAP Prompt)
        # -------------------------------------------------------------
        if cid in checkpoint_data.get("pathowhisper", {}):
            p_res = checkpoint_data["pathowhisper"][cid]
        else:
            t0_p = time.time()
            denoised_audio_path = denoise_audio(raw_audio_path)
            segments_p, _ = m_pathowhisper.transcribe(
                str(denoised_audio_path),
                initial_prompt=Config.PATHOLOGY_PROMPT,
                beam_size=1,
                language="en"
            )
            hyp_p = " ".join([s.text for s in segments_p]).strip()
            lat_p = round(time.time() - t0_p, 2)
            wer_p, cer_p = calc_wer_cer(ref_text, hyp_p)
            ext_p = extract_data_15_sections(normalize_text(hyp_p))
            acc_p = evaluate_15_sections_accuracy(ext_p, gt)

            p_res = {
                "latency_sec": lat_p, "wer": wer_p, "cer": cer_p, "field_acc": acc_p,
                "hyp_text": hyp_p
            }
            checkpoint_data["pathowhisper"][cid] = p_res

            # Log to CSV
            with open(CSV_LOG_PATH, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([cid, cat_id, cat_name, "PathoWhisper (INT8 + afftdn + Prompt)", lat_p, wer_p, cer_p, acc_p, ref_text, hyp_p])

        completed_cases.add(cid)
        processed_count += 1

        # Periodic checkpoint save every 5 cases
        if processed_count % 5 == 0:
            with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, ensure_ascii=False)

        # Print progress
        speedup = round(b_res["latency_sec"] / max(0.01, p_res["latency_sec"]), 2)
        total_elapsed = time.time() - start_time_all
        avg_time_per_case = total_elapsed / max(1, (processed_count - len(completed_cases) + 1))
        est_remaining_sec = avg_time_per_case * (total_cases - processed_count)
        est_hours = est_remaining_sec / 3600.0

        print(f"[{processed_count:04d}/{total_cases}] {cid} (Cat {cat_id}) | "
              f"Base: {b_res['wer']:5.1f}% ({b_res['latency_sec']:4.1f}s) | "
              f"Patho: {p_res['wer']:5.1f}% ({p_res['latency_sec']:4.1f}s) [{speedup:4.2f}x] | "
              f"Rem: ~{est_hours:.2f}h", flush=True)

    # Final Checkpoint Save
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(checkpoint_data, f, ensure_ascii=False)

    print("\n" + "=" * 90, flush=True)
    print("🎉 ALL 1,000 CASES EVALUATED! COMPUTING FINAL SCIENTIFIC METRICS...", flush=True)
    print("=" * 90, flush=True)

    compute_final_summary_and_latex(checkpoint_data, gt_data)

def compute_final_summary_and_latex(data, gt_data):
    base_cases = data["baseline"]
    patho_cases = data["pathowhisper"]
    total = len(patho_cases)

    if total == 0:
        print("No cases to summarize.")
        return

    # Category buckets
    cat_b = {i: {"wer": [], "cer": [], "acc": [], "lat": []} for i in range(1, 11)}
    cat_p = {i: {"wer": [], "cer": [], "acc": [], "lat": []} for i in range(1, 11)}

    for cid in patho_cases:
        c_id = gt_data[cid].get("category_id", 1)
        b = base_cases[cid]
        p = patho_cases[cid]

        cat_b[c_id]["wer"].append(b["wer"])
        cat_b[c_id]["cer"].append(b["cer"])
        cat_b[c_id]["acc"].append(b["field_acc"])
        cat_b[c_id]["lat"].append(b["latency_sec"])

        cat_p[c_id]["wer"].append(p["wer"])
        cat_p[c_id]["cer"].append(p["cer"])
        cat_p[c_id]["acc"].append(p["field_acc"])
        cat_p[c_id]["lat"].append(p["latency_sec"])

    # Build Category Breakdown CSV
    cat_rows = []
    for i in range(1, 11):
        nb = len(cat_b[i]["wer"])
        np_ = len(cat_p[i]["wer"])
        b_w = sum(cat_b[i]["wer"]) / nb if nb else 0
        b_c = sum(cat_b[i]["cer"]) / nb if nb else 0
        b_a = sum(cat_b[i]["acc"]) / nb if nb else 0
        b_l = sum(cat_b[i]["lat"]) / nb if nb else 0

        p_w = sum(cat_p[i]["wer"]) / np_ if np_ else 0
        p_c = sum(cat_p[i]["cer"]) / np_ if np_ else 0
        p_a = sum(cat_p[i]["acc"]) / np_ if np_ else 0
        p_l = sum(cat_p[i]["lat"]) / np_ if np_ else 0

        cat_rows.append({
            "category_id": i,
            "category_name": CATEGORY_NAMES.get(i, f"Category {i}"),
            "baseline_wer": round(b_w, 2), "pathowhisper_wer": round(p_w, 2),
            "baseline_cer": round(b_c, 2), "pathowhisper_cer": round(p_c, 2),
            "baseline_acc": round(b_a, 2), "pathowhisper_acc": round(p_a, 2),
            "baseline_latency": round(b_l, 2), "pathowhisper_latency": round(p_l, 2),
            "speedup": round(b_l / max(0.01, p_l), 2)
        })

    with open(CAT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(cat_rows[0].keys()))
        writer.writeheader()
        writer.writerows(cat_rows)

    # Macro & Micro Metrics
    macro_b_wer = sum(r["baseline_wer"] for r in cat_rows) / 10.0
    macro_p_wer = sum(r["pathowhisper_wer"] for r in cat_rows) / 10.0
    macro_b_cer = sum(r["baseline_cer"] for r in cat_rows) / 10.0
    macro_p_cer = sum(r["pathowhisper_cer"] for r in cat_rows) / 10.0
    macro_b_acc = sum(r["baseline_acc"] for r in cat_rows) / 10.0
    macro_p_acc = sum(r["pathowhisper_acc"] for r in cat_rows) / 10.0
    macro_b_lat = sum(r["baseline_latency"] for r in cat_rows) / 10.0
    macro_p_lat = sum(r["pathowhisper_latency"] for r in cat_rows) / 10.0

    micro_b_wer = sum(b["wer"] for b in base_cases.values()) / total
    micro_p_wer = sum(p["wer"] for p in patho_cases.values()) / total
    micro_b_cer = sum(b["cer"] for b in base_cases.values()) / total
    micro_p_cer = sum(p["cer"] for p in patho_cases.values()) / total
    micro_b_acc = sum(b["field_acc"] for b in base_cases.values()) / total
    micro_p_acc = sum(p["field_acc"] for p in patho_cases.values()) / total
    micro_b_lat = sum(b["latency_sec"] for b in base_cases.values()) / total
    micro_p_lat = sum(p["latency_sec"] for p in patho_cases.values()) / total

    summary_metrics = {
        "total_cases_evaluated": total,
        "macro_metrics": {
            "baseline_wer": round(macro_b_wer, 2), "pathowhisper_wer": round(macro_p_wer, 2),
            "baseline_cer": round(macro_b_cer, 2), "pathowhisper_cer": round(macro_p_cer, 2),
            "baseline_acc": round(macro_b_acc, 2), "pathowhisper_acc": round(macro_p_acc, 2),
            "baseline_latency": round(macro_b_lat, 2), "pathowhisper_latency": round(macro_p_lat, 2)
        },
        "micro_metrics": {
            "baseline_wer": round(micro_b_wer, 2), "pathowhisper_wer": round(micro_p_wer, 2),
            "baseline_cer": round(micro_b_cer, 2), "pathowhisper_cer": round(micro_p_cer, 2),
            "baseline_acc": round(micro_b_acc, 2), "pathowhisper_acc": round(micro_p_acc, 2),
            "baseline_latency": round(micro_b_lat, 2), "pathowhisper_latency": round(micro_p_lat, 2)
        },
        "overall_speedup": round(micro_b_lat / max(0.01, micro_p_lat), 2)
    }

    with open(SUMMARY_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(summary_metrics, f, indent=2, ensure_ascii=False)

    # Generate LaTeX Tables
    generate_latex_file(cat_rows, summary_metrics)

    print("\n" + "=" * 90)
    print("🏆 FINAL BENCHMARK SUMMARY (N = 1,000 CASES)")
    print("=" * 90)
    print(f"{'Metric':<30} | {'Baseline Whisper Small':<25} | {'PathoWhisper INT8':<25}")
    print("-" * 90)
    print(f"{'Macro-Average WER':<30} | {macro_b_wer:>22.2f}% | {macro_p_wer:>22.2f}%")
    print(f"{'Micro-Average WER':<30} | {micro_b_wer:>22.2f}% | {micro_p_wer:>22.2f}%")
    print(f"{'Macro-Average CER':<30} | {macro_b_cer:>22.2f}% | {macro_p_cer:>22.2f}%")
    print(f"{'Micro-Average CER':<30} | {micro_b_cer:>22.2f}% | {micro_p_cer:>22.2f}%")
    print(f"{'Mean Latency per Case':<30} | {micro_b_lat:>20.2f} s | {micro_p_lat:>20.2f} s")
    print(f"{'Overall Field Mapping Acc':<30} | {micro_b_acc:>22.2f}% | {micro_p_acc:>22.2f}%")
    print("=" * 90)
    print(f"Artifacts successfully written:")
    print(f"  - Detailed CSV Log : {CSV_LOG_PATH}")
    print(f"  - Category CSV     : {CAT_CSV_PATH}")
    print(f"  - Summary Metrics  : {SUMMARY_JSON_PATH}")
    print(f"  - LaTeX Source     : {LATEX_TABLES_PATH}")
    print("=" * 90)

def generate_latex_file(cat_rows, summary):
    sm = summary["macro_metrics"]
    smi = summary["micro_metrics"]
    
    latex_content = f"""% ----------------------------------------------------------------------
% Generated LaTeX Tables for Chapter 4 (N = 1,000 Cases Overnight Run)
% ----------------------------------------------------------------------

\\begin{{table}}[htbp]
\\centering
\\caption{{ผลการเปรียบเทียบประสิทธิภาพภาพรวมระหว่างแบบจำลองพื้นฐานและ PathoWhisper ($N=1,000$)}}
\\label{{tab:headtohead_actual}}
\\small
\\begin{{tabular}}{{lcc}}
\\hline
\\textbf{{ตัวชี้วัดประสิทธิภาพ (Metric)}} & \\textbf{{Whisper Small (Baseline)}} & \\textbf{{PathoWhisper (INT8 + afftdn)}} \\\\
\\hline
Word Error Rate (Macro-average WER)    & {sm['baseline_wer']:.2f}\\% & \\textbf{{{sm['pathowhisper_wer']:.2f}\\%}} \\\\
Word Error Rate (Global Micro-average) & {smi['baseline_wer']:.2f}\\% & \\textbf{{{smi['pathowhisper_wer']:.2f}\\%}} \\\\
Character Error Rate (Macro-average)   & {sm['baseline_cer']:.2f}\\% & \\textbf{{{sm['pathowhisper_cer']:.2f}\\%}} \\\\
Character Error Rate (Global Micro)    & {smi['baseline_cer']:.2f}\\% & \\textbf{{{smi['pathowhisper_cer']:.2f}\\%}} \\\\
เวลาประมวลผลเฉลี่ยต่อเคส (Latency)    & {smi['baseline_latency']:.2f} วินาที & \\textbf{{{smi['pathowhisper_latency']:.2f} วินาที}} \\\\
อัตราเร่งความเร็วในการประมวลผล (Speedup) & 1.00$\\times$ & \\textbf{{{summary['overall_speedup']:.2f}$\\times$}} \\\\
ความแม่นยำการสกัดข้อมูลครบ 15 ฟิลด์     & {smi['baseline_acc']:.2f}\\% & \\textbf{{{smi['pathowhisper_acc']:.2f}\\%}} \\\\
\\hline
\\end{{tabular}}
\\end{{table}}

\\begin{{table}}[htbp]
\\centering
\\caption{{ผลการประเมินประสิทธิภาพจำแนกตาม 10 หมวดหมู่ความท้าทายทางคลินิก ($N=1,000$)}}
\\label{{tab:bycat_actual}}
\\small
\\begin{{tabular}}{{clcccccc}}
\\hline
\\textbf{{หมวด}} & \\textbf{{หมวดหมู่ความท้าทาย}} & \\multicolumn{{2}}{{c}}{{\\textbf{{WER (\\%)}}}} & \\multicolumn{{2}}{{c}}{{\\textbf{{Acc (\\%)}}}} & \\multicolumn{{2}}{{c}}{{\\textbf{{เวลา (s)}}}} \\\\
\\cline{{3-8}}
 & & \\textbf{{Base}} & \\textbf{{Patho}} & \\textbf{{Base}} & \\textbf{{Patho}} & \\textbf{{Base}} & \\textbf{{Patho}} \\\\
\\hline
"""
    for r in cat_rows:
        latex_content += f"{r['category_id']} & {r['category_name']} & {r['baseline_wer']:.2f} & \\textbf{{{r['pathowhisper_wer']:.2f}}} & {r['baseline_acc']:.2f} & \\textbf{{{r['pathowhisper_acc']:.2f}}} & {r['baseline_latency']:.2f} & \\textbf{{{r['pathowhisper_latency']:.2f}}} \\\\\n"

    latex_content += f"""\\hline
\\multicolumn{{2}}{{c}}{{\\textbf{{ค่าเฉลี่ยระดับหมวดหมู่ (Macro-average)}}}} & {sm['baseline_wer']:.2f} & \\textbf{{{sm['pathowhisper_wer']:.2f}}} & {sm['baseline_acc']:.2f} & \\textbf{{{sm['pathowhisper_acc']:.2f}}} & {sm['baseline_latency']:.2f} & \\textbf{{{sm['pathowhisper_latency']:.2f}}} \\\\
\\hline
\\end{{tabular}}
\\end{{table}}
"""
    with open(LATEX_TABLES_PATH, "w", encoding="utf-8") as f:
        f.write(latex_content)

if __name__ == "__main__":
    main()
