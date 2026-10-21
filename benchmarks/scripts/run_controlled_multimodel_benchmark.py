"""
benchmarks/scripts/run_controlled_multimodel_benchmark.py
================================================================================
Rigorous, Audited Multi-Model Benchmark Protocol (Tiny vs Base vs Small vs PathoWhisper)
Implements all 5 audit requirements from Claude:
  1. Stratified random sampling with fixed seed (seed=42).
  2. Baseline configured with beam_size=5, fp16=False, language='en' matching thesis.
  3. PathoWhisper explicitly configured with cpu_threads=8, beam_size=1, CAP Prompt.
  4. Interleaved execution across models for each case, with 3 repetitions (median latency).
  5. Automated hardware environment logging (CPU name, cores, memory).
================================================================================
"""

import sys
import os
import re
import csv
import json
import time
import random
import platform
import subprocess
from pathlib import Path
import numpy as np
import jiwer
import whisper
from faster_whisper import WhisperModel

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))
os.environ['PATH'] = str(BASE_DIR / 'bin') + os.pathsep + os.environ.get('PATH', '')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from configs.config import Config
from src.stt.whisper_model import denoise_audio

DATASET_DIR = BASE_DIR / "data" / "dataset_1000"
GT_PATH = DATASET_DIR / "ground_truth_1000.json"
AUDIO_DIR = DATASET_DIR / "audio"

OUT_DIR = BASE_DIR / "benchmarks" / "thesis_eval_outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CATEGORY_NAMES = {
    1: "Cat 1: Standard Protocol",
    2: "Cat 2: Out-of-Order Sequence",
    3: "Cat 3: Self-Correction Speech",
    4: "Cat 4: Multi-Margin Assessment",
    5: "Cat 5: Heavy Lymph Nodes Count",
    6: "Cat 6: Fibrocystic Benign Control",
    7: "Cat 7: High-Speed Rapid Speech",
    8: "Cat 8: Fume Hood Exhaust Noise (-10dB)",
    9: "Cat 9: Ductal Carcinoma / Microinvasion",
    10: "Cat 10: Clinical Edge Cases & Missing Fields"
}

def norm_a(t):
    """Criterion A: Basic lowercasing and punctuation removal."""
    if not t: return ""
    t = str(t).lower()
    t = re.sub(r'[.,;:!?\-]', ' ', t)
    return " ".join(t.split())

def norm_b(t):
    """Criterion B: Dimension formatting normalized (e.g. 11.4x14.9x7.8 -> 11.4 x 14.9 x 7.8)."""
    if not t: return ""
    t = str(t).lower()
    for _ in range(2):
        t = re.sub(r"(\d)\s*(?:x|by)\s*(?=\d)", r"\1 x ", t)
    t = re.sub(r"(\d)(cm|mm|g|kg)\b", r"\1 \2", t)
    t = re.sub(r"[.,;:!?\-]", " ", t)
    return " ".join(t.split())

def get_system_telemetry():
    """Captures exact physical/virtual hardware specs."""
    cpu_name = platform.processor()
    try:
        res = subprocess.run(["powershell", "-Command", "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name"], capture_output=True, text=True, check=False)
        if res.stdout.strip():
            cpu_name = res.stdout.strip().splitlines()[0]
    except: pass
    
    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu_name": cpu_name,
        "logical_cores": os.cpu_count(),
        "python_version": platform.python_version(),
        "openmp_threads": os.environ.get("OMP_NUM_THREADS", "auto"),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

def select_stratified_cases(gt_data, cases_per_cat=5, seed=42):
    """Selects stratified random cases per category with fixed seed."""
    random.seed(seed)
    cats = {}
    for cid, d in gt_data.items():
        c_id = d.get("category_id", 1)
        cats.setdefault(c_id, []).append(cid)
    
    selected = []
    for c_id in sorted(cats.keys()):
        c_list = sorted(cats[c_id])
        sampled = random.sample(c_list, min(cases_per_cat, len(c_list)))
        for cid in sampled:
            selected.append((cid, c_id))
    return selected

def run_benchmark(cases_per_cat=5, repetitions=3, seed=42):
    print("=" * 90)
    print(f"CONTROLLED BENCHMARK: {cases_per_cat*10} CASES ({cases_per_cat}/CAT), {repetitions} REPETITIONS (SEED={seed})")
    print("=" * 90)

    telemetry = get_system_telemetry()
    print(f"System Telemetry:")
    for k, v in telemetry.items():
        print(f"  - {k}: {v}")

    with open(GT_PATH, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    selected_cases = select_stratified_cases(gt_data, cases_per_cat=cases_per_cat, seed=seed)
    total_cases = len(selected_cases)
    print(f"\nTotal selected cases: {total_cases} (Stratified across 10 categories)\n")

    # Preload all models
    print("[1/4] Loading Whisper Tiny (PyTorch)...", flush=True)
    m_tiny = whisper.load_model("tiny")
    
    print("[2/4] Loading Whisper Base (PyTorch)...", flush=True)
    m_base = whisper.load_model("base")
    
    print("[3/4] Loading Whisper Small Baseline (PyTorch, FP32, Beam 5)...", flush=True)
    m_small = whisper.load_model("small")
    
    print("[4/4] Loading PathoWhisper Small (CTranslate2 INT8, cpu_threads=8)...", flush=True)
    m_pw = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=8)

    models = [
        {"id": "tiny", "name": "Whisper Tiny (PyTorch)", "model": m_tiny, "type": "pytorch"},
        {"id": "base", "name": "Whisper Base (PyTorch)", "model": m_base, "type": "pytorch"},
        {"id": "small_baseline", "name": "Whisper Small (PyTorch Baseline)", "model": m_small, "type": "pytorch"},
        {"id": "pathowhisper", "name": "PathoWhisper Small (INT8, cpu_threads=8)", "model": m_pw, "type": "pathowhisper"},
    ]

    case_records = []
    
    print("\nStarting Interleaved Multi-Model Execution...", flush=True)
    start_total = time.time()

    for idx, (cid, cat_id) in enumerate(selected_cases, 1):
        cat_name = CATEGORY_NAMES.get(cat_id, f"Category {cat_id}")
        audio_path = AUDIO_DIR / f"{cid}.mp3"
        ref_text = gt_data[cid]["raw_text"]
        
        print(f"\n--- Case {idx}/{total_cases}: {cid} ({cat_name}) ---", flush=True)

        # For PathoWhisper, prepare denoised audio once
        t_denoise0 = time.time()
        denoised_audio = denoise_audio(audio_path)
        denoise_time = time.time() - t_denoise0

        for m_info in models:
            m_id = m_info["id"]
            m_name = m_info["name"]
            m_type = m_info["type"]
            
            latencies = []
            hyp_text = ""
            
            # Run multiple repetitions to compute median latency
            for rep in range(repetitions):
                t0 = time.time()
                if m_type == "pytorch":
                    res = m_info["model"].transcribe(
                        str(audio_path),
                        language="en",
                        beam_size=5,
                        fp16=False
                    )
                    if rep == 0:
                        hyp_text = res.get("text", "").strip()
                elif m_type == "pathowhisper":
                    segments, _ = m_info["model"].transcribe(
                        str(denoised_audio),
                        language="en",
                        initial_prompt=Config.PATHOLOGY_PROMPT,
                        beam_size=1
                    )
                    if rep == 0:
                        hyp_text = " ".join([s.text for s in segments]).strip()
                
                lat = time.time() - t0
                if m_type == "pathowhisper":
                    lat += denoise_time  # include audio preprocessing time for complete pipeline
                latencies.append(lat)

            med_lat = round(float(np.median(latencies)), 3)
            wa = round(jiwer.wer(norm_a(ref_text), norm_a(hyp_text)) * 100.0, 2)
            wb = round(jiwer.wer(norm_b(ref_text), norm_b(hyp_text)) * 100.0, 2)

            rec = {
                "case_id": cid,
                "category_id": cat_id,
                "category_name": cat_name,
                "model_id": m_id,
                "model_name": m_name,
                "median_latency_sec": med_lat,
                "latency_reps": [round(x, 3) for x in latencies],
                "wer_criterion_a": wa,
                "wer_criterion_b": wb,
                "ref_text": ref_text,
                "hyp_text": hyp_text
            }
            case_records.append(rec)
            print(f"  [{m_name}] Med Lat={med_lat:.2f}s (reps: {[round(x,1) for x in latencies]}) | WER-A={wa:.1f}% | WER-B={wb:.1f}%", flush=True)

        if denoised_audio != audio_path and os.path.exists(denoised_audio):
            try: os.remove(denoised_audio)
            except: pass

    elapsed_all = time.time() - start_total
    print(f"\nBenchmark completed in {elapsed_all/60:.2f} minutes!", flush=True)

    # Compute Summaries
    summary_by_model = []
    for m_info in models:
        m_id = m_info["id"]
        m_recs = [r for r in case_records if r["model_id"] == m_id]
        mean_lat = round(float(np.mean([r["median_latency_sec"] for r in m_recs])), 2)
        mean_wa = round(float(np.mean([r["wer_criterion_a"] for r in m_recs])), 2)
        mean_wb = round(float(np.mean([r["wer_criterion_b"] for r in m_recs])), 2)
        
        summary_by_model.append({
            "model_id": m_id,
            "model_name": m_info["name"],
            "cases_count": len(m_recs),
            "repetitions": repetitions,
            "avg_median_latency_sec": mean_lat,
            "mean_wer_criterion_a": mean_wa,
            "mean_wer_criterion_b": mean_wb,
            "reduction_points": round(mean_wa - mean_wb, 2)
        })

    # Save CSVs
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    cases_csv_path = OUT_DIR / f"rigorous_sizes_benchmark_cases_{cases_per_cat*10}cases.csv"
    summary_csv_path = OUT_DIR / f"rigorous_sizes_benchmark_summary_{cases_per_cat*10}cases.csv"
    json_path = OUT_DIR / f"rigorous_sizes_benchmark_full_{cases_per_cat*10}cases.json"

    # 1. Cases CSV
    fieldnames_cases = [
        "case_id", "category_id", "category_name", "model_id", "model_name",
        "median_latency_sec", "wer_criterion_a", "wer_criterion_b", "ref_text", "hyp_text"
    ]
    with open(cases_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames_cases, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(case_records)

    # 2. Summary CSV
    fieldnames_sum = ["model_id", "model_name", "cases_count", "repetitions", "avg_median_latency_sec", "mean_wer_criterion_a", "mean_wer_criterion_b", "reduction_points"]
    with open(summary_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames_sum)
        writer.writeheader()
        writer.writerows(summary_by_model)

    # 3. JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "telemetry": telemetry,
            "summary": summary_by_model,
            "cases": case_records
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[Saved] Cases CSV: {cases_csv_path}")
    print(f"[Saved] Summary CSV: {summary_csv_path}")
    print(f"[Saved] JSON: {json_path}")

    # Also copy to Downloads for user
    import shutil
    shutil.copy2(cases_csv_path, Path(r"C:\Users\project\Downloads") / cases_csv_path.name)
    shutil.copy2(summary_csv_path, Path(r"C:\Users\project\Downloads") / summary_csv_path.name)

    print("\n" + "=" * 90)
    print("FINAL SUMMARY RESULTS:")
    print("=" * 90)
    print(f"{'โมเดล':<38} | {'Latency (Median s)':<20} | {'WER เกณฑ์ A (%)':<16} | {'WER เกณฑ์ B (%)':<16}")
    print("-" * 90)
    for s in summary_by_model:
        print(f"{s['model_name']:<38} | {s['avg_median_latency_sec']:>18.2f}s | {s['mean_wer_criterion_a']:>14.2f}% | {s['mean_wer_criterion_b']:>14.2f}%")
    print("=" * 90)

if __name__ == "__main__":
    cases_n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    reps_n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    run_benchmark(cases_per_cat=cases_n, repetitions=reps_n, seed=42)
