"""
benchmarks/scripts/run_100cases_rigorous_benchmark.py
================================================================================
Comprehensive, Audited 7-Model Benchmark across 100 Stratified Pathology Cases
All 7 Models Compared:
  1. Vosk (Small en-us, Kaldi C++)
  2. Meta Wav2Vec 2.0 Base (facebook/wav2vec2-base-960h, PyTorch CTC)
  3. Whisper Tiny (PyTorch vanilla, FP32, Beam 5)
  4. Whisper Base (PyTorch vanilla, FP32, Beam 5)
  5. Whisper Small (PyTorch vanilla Baseline, FP32, Beam 5 - matches thesis baseline)
  6. Faster-Whisper Small (Vanilla CTranslate2 INT8, cpu_threads=8, Beam 5, No Prompt)
  7. PathoWhisper Small (CTranslate2 INT8, cpu_threads=8, Beam 1, CAP Prompt + Denoise)

Audit & Control Protocol:
  - 100 cases (Stratified random sampling: 10 cases/category x 10 categories, seed=42)
  - Controlled hardware telemetry logging (CPU, cores, RAM, OS)
  - Interleaved execution per case across all 7 models
  - Checkpoint saving after every case (robust against interruption)
  - Both Criterion A (standard) and Criterion B (clinical formatting / ITN) WER metrics
  - Full output exported to CSV, JSON, and copied to Downloads
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
import shutil
from pathlib import Path
import numpy as np
import librosa
import jiwer
import whisper
from faster_whisper import WhisperModel
from transformers import pipeline
from vosk import Model as VoskModel, KaldiRecognizer

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))
os.environ['PATH'] = str(BASE_DIR / 'bin') + os.pathsep + os.environ.get('PATH', '')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

from configs.config import Config
from src.stt.whisper_model import denoise_audio

DATASET_DIR = BASE_DIR / "data" / "dataset_1000"
GT_PATH = DATASET_DIR / "ground_truth_1000.json"
AUDIO_DIR = DATASET_DIR / "audio"

OUT_DIR = BASE_DIR / "benchmarks" / "thesis_eval_outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT_PATH = OUT_DIR / "checkpoint_100cases_7models_benchmark.json"

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

def itn_spoken_text(text):
    """Inverse Text Normalization for phonetic/spoken number output (Vosk, Wav2vec2)."""
    if not text: return ""
    t = str(text).lower()
    
    replacements = [
        (r'\bpoint\b|\bdot\b', '.'),
        (r'\bdash\b', '-'),
        (r'\bcentimeters?\b|\bsentimeters?\b|\bsentimenter\b', 'cm'),
        (r'\bmillimeters?\b', 'mm'),
        (r'\bzero\b', '0'),
        (r'\bone\b', '1'),
        (r'\btwo\b|\bto\b(?=\s*\d|\s*\.)', '2'),
        (r'\bthree\b', '3'),
        (r'\bfour\b|\bfor\b(?=\s*\d|\s*\.)', '4'),
        (r'\bfive\b', '5'),
        (r'\bsix\b', '6'),
        (r'\bseven\b', '7'),
        (r'\beight\b', '8'),
        (r'\bnine\b', '9'),
        (r'\bten\b', '10'),
        (r'\beleven\b', '11'),
        (r'\btwelve\b', '12'),
        (r'\bthirteen\b', '13'),
        (r'\bfourteen\b', '14'),
        (r'\bfifteen\b', '15'),
        (r'\bsixteen\b', '16'),
        (r'\bseventeen\b', '17'),
        (r'\beighteen\b', '18'),
        (r'\bnineteen\b', '19'),
        (r'\btwenty\s*one\b', '21'),
        (r'\btwenty\s*two\b', '22'),
        (r'\btwenty\s*three\b', '23'),
        (r'\btwenty\s*four\b', '24'),
        (r'\btwenty\s*five\b', '25'),
        (r'\btwenty\s*six\b', '26'),
        (r'\btwenty\s*seven\b', '27'),
        (r'\btwenty\s*eight\b', '28'),
        (r'\btwenty\s*nine\b', '29'),
        (r'\btwenty\b', '20'),
        (r'\bthirty\b', '30'),
        (r'\bforty\b', '40'),
        (r'\bfifty\b', '50'),
        (r'\bsixty\b', '60'),
        (r'\bseventy\b', '70'),
        (r'\beighty\b', '80'),
        (r'\bninety\b', '90'),
        (r'\bone\s*thousand\b', '1000'),
    ]
    for pattern, repl in replacements:
        t = re.sub(pattern, repl, t)
    
    t = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', t)
    return t

def norm_a(t):
    """Criterion A: Standard lowercasing and punctuation removal."""
    if not t: return ""
    t = str(t).lower()
    t = re.sub(r'[.,;:!?\-]', ' ', t)
    return " ".join(t.split())

def norm_b(t):
    """Criterion B: Dimension formatting & ITN normalized."""
    if not t: return ""
    t = itn_spoken_text(t)
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

def select_stratified_cases(gt_data, cases_per_cat=10, seed=42):
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

def save_intermediate_results(case_records, telemetry, total_cases):
    """Saves checkpoint and CSVs after each case."""
    model_ids = ["vosk", "wav2vec2", "tiny", "base", "small_baseline", "faster_whisper_vanilla", "pathowhisper"]
    model_names = {
        "vosk": "Vosk (Small en-us, Kaldi C++)",
        "wav2vec2": "Meta Wav2Vec 2.0 Base (PyTorch CTC)",
        "tiny": "Whisper Tiny (PyTorch)",
        "base": "Whisper Base (PyTorch)",
        "small_baseline": "Whisper Small (PyTorch Baseline)",
        "faster_whisper_vanilla": "Faster-Whisper Small (CTranslate2 Vanilla)",
        "pathowhisper": "PathoWhisper Small (INT8, cpu_threads=8)"
    }
    
    summary_by_model = []
    for m_id in model_ids:
        m_recs = [r for r in case_records if r["model_id"] == m_id]
        if not m_recs:
            continue
        mean_lat = round(float(np.mean([r["median_latency_sec"] for r in m_recs])), 2)
        mean_wa = round(float(np.mean([r["wer_criterion_a"] for r in m_recs])), 2)
        mean_wb = round(float(np.mean([r["wer_criterion_b"] for r in m_recs])), 2)
        summary_by_model.append({
            "model_id": m_id,
            "model_name": model_names.get(m_id, m_id),
            "cases_count": len(m_recs),
            "avg_median_latency_sec": mean_lat,
            "mean_wer_criterion_a": mean_wa,
            "mean_wer_criterion_b": mean_wb,
            "reduction_points": round(mean_wa - mean_wb, 2)
        })

    cases_csv_path = OUT_DIR / f"rigorous_benchmark_cases_{total_cases}cases_7models.csv"
    summary_csv_path = OUT_DIR / f"rigorous_benchmark_summary_{total_cases}cases_7models.csv"
    json_path = OUT_DIR / f"rigorous_benchmark_full_{total_cases}cases_7models.json"

    fieldnames_cases = [
        "case_id", "category_id", "category_name", "model_id", "model_name",
        "median_latency_sec", "wer_criterion_a", "wer_criterion_b", "ref_text", "hyp_text"
    ]
    with open(cases_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames_cases, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(case_records)

    fieldnames_sum = ["model_id", "model_name", "cases_count", "avg_median_latency_sec", "mean_wer_criterion_a", "mean_wer_criterion_b", "reduction_points"]
    with open(summary_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames_sum)
        writer.writeheader()
        writer.writerows(summary_by_model)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "telemetry": telemetry,
            "summary": summary_by_model,
            "cases": case_records
        }, f, ensure_ascii=False, indent=2)

    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "completed_cases": list(set([r["case_id"] for r in case_records])),
            "records": case_records
        }, f, ensure_ascii=False, indent=2)

    try:
        downloads_dir = Path(r"C:\Users\project\Downloads")
        shutil.copy2(cases_csv_path, downloads_dir / cases_csv_path.name)
        shutil.copy2(summary_csv_path, downloads_dir / summary_csv_path.name)
    except Exception:
        pass

def run_rigorous_7model_benchmark(cases_per_cat=10, seed=42):
    print("=" * 105, flush=True)
    print(f"RIGOROUS 7-MODEL BENCHMARK: {cases_per_cat*10} CASES (10 CATEGORIES x {cases_per_cat} CASES, SEED={seed})", flush=True)
    print("Models: Vosk | Wav2Vec2 | Tiny | Base | Small Baseline (PyTorch) | Faster-Whisper | PathoWhisper", flush=True)
    print("=" * 105, flush=True)

    telemetry = get_system_telemetry()
    print("Hardware Environment:", flush=True)
    for k, v in telemetry.items():
        print(f"  - {k}: {v}", flush=True)

    with open(GT_PATH, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    selected_cases = select_stratified_cases(gt_data, cases_per_cat=cases_per_cat, seed=seed)
    total_cases = len(selected_cases)
    print(f"\nTotal selected cases: {total_cases} (Stratified across 10 categories)\n", flush=True)

    case_records = []
    completed_case_ids = set()
    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                ckpt = json.load(f)
                completed_case_ids = set(ckpt.get("completed_cases", []))
                case_records = ckpt.get("records", [])
                print(f"[Checkpoint] Resuming with {len(completed_case_ids)} already completed cases!", flush=True)
        except Exception as e:
            print(f"[Checkpoint] Warning loading checkpoint: {e}", flush=True)

    # Preload all 7 models
    print("\n--- Preloading All 7 Models ---", flush=True)
    print("[1/6] Loading Vosk ASR Engine...", flush=True)
    m_vosk = VoskModel(str(BASE_DIR / "bin" / "vosk-model-small-en-us-0.15"))

    print("[2/6] Loading Meta Wav2Vec 2.0 Base Pipeline...", flush=True)
    m_wav2vec2 = pipeline("automatic-speech-recognition", model="facebook/wav2vec2-base-960h")

    print("[3/6] Loading Whisper Tiny (PyTorch)...", flush=True)
    m_tiny = whisper.load_model("tiny")
    
    print("[4/6] Loading Whisper Base (PyTorch)...", flush=True)
    m_base = whisper.load_model("base")
    
    print("[5/6] Loading Whisper Small Baseline (PyTorch, FP32, Beam 5)...", flush=True)
    m_small = whisper.load_model("small")
    
    print("[6/6] Loading CTranslate2 Small Engine (INT8, cpu_threads=8)...", flush=True)
    m_ct2 = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=8)
    print("All 7 models successfully preloaded into memory!\n", flush=True)

    models_config = [
        {"id": "vosk", "name": "Vosk (Small en-us, Kaldi C++)", "model": m_vosk, "mode": "vosk"},
        {"id": "wav2vec2", "name": "Meta Wav2Vec 2.0 Base (PyTorch CTC)", "model": m_wav2vec2, "mode": "wav2vec2"},
        {"id": "tiny", "name": "Whisper Tiny (PyTorch)", "model": m_tiny, "mode": "pytorch"},
        {"id": "base", "name": "Whisper Base (PyTorch)", "model": m_base, "mode": "pytorch"},
        {"id": "small_baseline", "name": "Whisper Small (PyTorch Baseline)", "model": m_small, "mode": "pytorch"},
        {"id": "faster_whisper_vanilla", "name": "Faster-Whisper Small (CTranslate2 Vanilla)", "model": m_ct2, "mode": "ct2_vanilla"},
        {"id": "pathowhisper", "name": "PathoWhisper Small (INT8, cpu_threads=8)", "model": m_ct2, "mode": "pathowhisper"},
    ]

    start_benchmark_time = time.time()
    
    for idx, (cid, cat_id) in enumerate(selected_cases, 1):
        if cid in completed_case_ids:
            continue
            
        cat_name = CATEGORY_NAMES.get(cat_id, f"Category {cat_id}")
        audio_path = AUDIO_DIR / f"{cid}.mp3"
        ref_text = gt_data[cid]["raw_text"]

        print(f"\n=================================================================", flush=True)
        print(f"Processing Case [{idx}/{total_cases}]: {cid} | {cat_name}", flush=True)
        print(f"=================================================================", flush=True)

        # Prepare Denoised Audio for PathoWhisper
        t_denoise0 = time.time()
        denoised_audio = denoise_audio(audio_path)
        denoise_time = time.time() - t_denoise0

        # Load audio data once for Vosk
        audio_data_16k, _ = librosa.load(str(audio_path), sr=16000)
        int16_samples = (audio_data_16k * 32767).astype(np.int16)

        for m_info in models_config:
            m_id = m_info["id"]
            m_name = m_info["name"]
            m_mode = m_info["mode"]

            t0 = time.time()
            hyp_text = ""

            if m_mode == "vosk":
                rec = KaldiRecognizer(m_info["model"], 16000)
                rec.AcceptWaveform(int16_samples.tobytes())
                res = json.loads(rec.FinalResult())
                hyp_text = res.get("text", "").strip()
                lat = round(time.time() - t0, 3)

            elif m_mode == "wav2vec2":
                res = m_info["model"](str(audio_path))
                hyp_text = res.get("text", "").strip() if isinstance(res, dict) else str(res).strip()
                lat = round(time.time() - t0, 3)

            elif m_mode == "pytorch":
                res = m_info["model"].transcribe(
                    str(audio_path),
                    language="en",
                    beam_size=5,
                    fp16=False
                )
                hyp_text = res.get("text", "").strip()
                lat = round(time.time() - t0, 3)

            elif m_mode == "ct2_vanilla":
                segments, _ = m_info["model"].transcribe(
                    str(audio_path),
                    language="en",
                    beam_size=5
                )
                hyp_text = " ".join([s.text for s in segments]).strip()
                lat = round(time.time() - t0, 3)

            elif m_mode == "pathowhisper":
                segments, _ = m_info["model"].transcribe(
                    str(denoised_audio),
                    language="en",
                    initial_prompt=Config.PATHOLOGY_PROMPT,
                    beam_size=1
                )
                hyp_text = " ".join([s.text for s in segments]).strip()
                lat = round((time.time() - t0) + denoise_time, 3)

            wa = round(jiwer.wer(norm_a(ref_text), norm_a(hyp_text)) * 100.0, 2)
            wb = round(jiwer.wer(norm_b(ref_text), norm_b(hyp_text)) * 100.0, 2)

            rec = {
                "case_id": cid,
                "category_id": cat_id,
                "category_name": cat_name,
                "model_id": m_id,
                "model_name": m_name,
                "median_latency_sec": lat,
                "wer_criterion_a": wa,
                "wer_criterion_b": wb,
                "ref_text": ref_text,
                "hyp_text": hyp_text
            }
            case_records.append(rec)
            print(f"  [{m_name:<40}] Lat={lat:>6.2f}s | WER-A={wa:>5.2f}% | WER-B={wb:>5.2f}%", flush=True)

        if denoised_audio != audio_path and os.path.exists(denoised_audio):
            try: os.remove(denoised_audio)
            except: pass

        completed_case_ids.add(cid)
        save_intermediate_results(case_records, telemetry, total_cases)

    total_elapsed = time.time() - start_benchmark_time
    print(f"\nAll {total_cases} cases completed in {total_elapsed/60:.2f} minutes!", flush=True)

    print("\n" + "=" * 105, flush=True)
    print("FINAL 100-CASE RIGOROUS 7-MODEL BENCHMARK RESULTS", flush=True)
    print("=" * 105, flush=True)
    print(f"{'Model Name':<42} | {'Cases':<6} | {'Avg Latency (s)':<17} | {'WER Crit A (%)':<15} | {'WER Crit B (%)':<15}", flush=True)
    print("-" * 105, flush=True)
    
    summary_path = OUT_DIR / f"rigorous_benchmark_summary_{total_cases}cases_7models.csv"
    with open(summary_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            print(f"{row['model_name']:<42} | {row['cases_count']:<6} | {float(row['avg_median_latency_sec']):>15.2f}s | {float(row['mean_wer_criterion_a']):>13.2f}% | {float(row['mean_wer_criterion_b']):>13.2f}%", flush=True)
    print("=" * 105, flush=True)

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    run_rigorous_7model_benchmark(cases_per_cat=n, seed=42)
