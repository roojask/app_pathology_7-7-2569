"""
benchmarks/scripts/run_vosk_wav2vec2_300cases.py
================================================================================
Evaluation of Vosk and Meta Wav2Vec 2.0 Base across the EXACT SAME 300 cases
as the PathoWhisper Controlled Factorial Benchmark.

Generates:
  1. vosk_wav2vec2_cases_300cases.csv
  2. vosk_wav2vec2_summary_300cases.csv
  3. table6_cross_architecture_300cases.csv (Unified Table 6 with Whisper models)
================================================================================
"""

import sys
import os
import re
import csv
import json
import time
import ctypes
import platform
from pathlib import Path
import numpy as np
import pandas as pd
import jiwer
import librosa
from vosk import Model as VoskModel, KaldiRecognizer
from transformers import pipeline

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

# Windows Sleep Prevention
def prevent_windows_sleep():
    try:
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ES_AWAYMODE_REQUIRED = 0x00000040
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED)
        print("[Power Management] Windows sleep prevention active.", flush=True)
    except Exception as e:
        print(f"[Power Management] Warning: {e}", flush=True)

# Clinical evaluation
from scripts.eval_clinical_core_metrics import KEYS, CRIT, cmp, mapped
from src.nlp.extractor import extract_data_15_sections
from benchmarks.scripts.text_norm_utils import norm_a, norm_b

DATASET_DIR = BASE_DIR / "data" / "dataset_1000"
GT_PATH = DATASET_DIR / "ground_truth_1000_pure.json"
AUDIO_DIR = DATASET_DIR / "audio"
ABLATION_CASES_CSV = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "controlled_ablation_cases_300cases.csv"

OUT_DIR = BASE_DIR / "benchmarks" / "thesis_eval_outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT_PATH = OUT_DIR / "checkpoint_vosk_wav2vec2_300cases.json"

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

def norm_b_itn(t):
    """Criterion B with ITN for phonetic models."""
    if not t: return ""
    t = itn_spoken_text(t)
    return norm_b(t)

def evaluate_case_clinical_cer(hyp_text, gt_case_dict):
    """Evaluates extraction using Extractor v2.1 on ITN-normalized text."""
    norm_text = itn_spoken_text(str(hyp_text))
    pred_raw = extract_data_15_sections(norm_text)
    pm = mapped(pred_raw)
    
    err_count = 0
    crit_err_count = 0
    for k in KEYS:
        status = cmp(k, gt_case_dict.get(k), pm.get(k))
        if status in ("FN", "FP", "WRONG"):
            err_count += 1
            if k in CRIT:
                crit_err_count += 1
                
    cer_case = 1 if crit_err_count > 0 else 0
    slot_acc = round(((len(KEYS) - err_count) / len(KEYS)) * 100.0, 2)
    return cer_case, slot_acc

def run_vosk_wav2vec2_300cases():
    prevent_windows_sleep()
    print("=" * 100, flush=True)
    print("CROSS-ARCHITECTURE BENCHMARK: VOSK & WAV2VEC 2.0 (N = 300 EXACT CASES)", flush=True)
    print("=" * 100, flush=True)

    if not ABLATION_CASES_CSV.exists():
        print(f"Error: Could not find ablation cases CSV at {ABLATION_CASES_CSV}")
        return

    # Load 300 cases from ablation benchmark
    df_ablation = pd.read_csv(ABLATION_CASES_CSV)
    unique_cases = df_ablation.drop_duplicates(subset=["case_id"])[["case_id", "category_id", "category_name", "is_core_100"]].to_dict("records")
    print(f"Loaded {len(unique_cases)} unique cases matching the 300-case ablation benchmark.", flush=True)

    with open(GT_PATH, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    # Checkpoint logic
    case_records = []
    completed_keys = set()
    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                ckpt = json.load(f)
                case_records = ckpt.get("records", [])
                completed_keys = set((r["case_id"], r["model_id"]) for r in case_records)
                print(f"[Checkpoint] Resuming with {len(completed_keys)} model-case passes completed!", flush=True)
        except Exception as e:
            print(f"[Checkpoint] Warning: {e}", flush=True)

    # Load Models
    print("\n[Loading Models] Initializing Vosk & Wav2Vec 2.0...", flush=True)
    vosk_path = BASE_DIR / "bin" / "vosk-model-small-en-us-0.15"
    if not vosk_path.exists():
        print(f"Error: Vosk model not found at {vosk_path}")
        return
    m_vosk = VoskModel(str(vosk_path))
    print("  [1/2] Vosk Small (en-us) successfully loaded!", flush=True)

    print("  [2/2] Loading Meta Wav2Vec 2.0 Base (facebook/wav2vec2-base-960h)...", flush=True)
    m_w2v = pipeline("automatic-speech-recognition", model="facebook/wav2vec2-base-960h")
    print("  Both models successfully loaded!\n", flush=True)

    models = [
        {"id": "vosk", "name": "Vosk (Small en-us, Kaldi C++)", "type": "vosk"},
        {"id": "wav2vec2", "name": "Meta Wav2Vec 2.0 Base (PyTorch CTC)", "type": "wav2vec2"}
    ]

    total_cases = len(unique_cases)
    t_start_global = time.time()

    for idx, c_info in enumerate(unique_cases, 1):
        cid = c_info["case_id"]
        cat_id = c_info["category_id"]
        cat_name = c_info["category_name"]
        is_core = c_info["is_core_100"]

        audio_path = AUDIO_DIR / f"{cid}.mp3"
        ref_text = gt_data[cid]["raw_text"]
        gt_dict = gt_data[cid]

        # Load 16kHz audio for Vosk
        y_16k, _ = librosa.load(str(audio_path), sr=16000)
        int16_samples = (y_16k * 32767).astype(np.int16)

        case_results = []
        for m in models:
            m_id = m["id"]
            if (cid, m_id) in completed_keys:
                continue

            t0 = time.time()
            hyp_text = ""
            if m["type"] == "vosk":
                rec = KaldiRecognizer(m_vosk, 16000)
                rec.AcceptWaveform(int16_samples.tobytes())
                res = json.loads(rec.FinalResult())
                hyp_text = res.get("text", "").strip()
            elif m["type"] == "wav2vec2":
                res = m_w2v(y_16k)
                hyp_text = res.get("text", "").strip() if isinstance(res, dict) else str(res).strip()

            lat = round(time.time() - t0, 3)

            wa = round(jiwer.wer(norm_a(ref_text), norm_a(hyp_text)) * 100.0, 2)
            wb = round(jiwer.wer(norm_b(ref_text), norm_b_itn(hyp_text)) * 100.0, 2)
            cer, slot_acc = evaluate_case_clinical_cer(hyp_text, gt_dict)

            rec_data = {
                "case_id": cid,
                "category_id": cat_id,
                "category_name": cat_name,
                "is_core_100": is_core,
                "model_id": m_id,
                "model_name": m["name"],
                "latency_sec": lat,
                "wer_criterion_a": wa,
                "wer_criterion_b": wb,
                "cer_case": cer,
                "slot_accuracy": slot_acc,
                "ref_text": ref_text,
                "hyp_text": hyp_text
            }
            case_records.append(rec_data)
            completed_keys.add((cid, m_id))
            case_results.append((m_id, lat, wa, wb, cer, slot_acc))

        if case_results:
            res_str = " | ".join([f"{mid}: {lat:.2f}s, WER-B={wb:.1f}%, CER={cer}" for mid, lat, wa, wb, cer, _ in case_results])
            print(f"[{idx:3d}/{total_cases}] {cid} ({cat_name}) -> {res_str}", flush=True)

        # Checkpoint every 5 cases
        if idx % 5 == 0 or idx == total_cases:
            with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
                json.dump({"records": case_records}, f, indent=2)

    total_time = round(time.time() - t_start_global, 1)
    print(f"\n[Completed] Finished all 300 cases in {total_time}s ({total_time/60:.1f} min)!", flush=True)

    # 1. Save Case-level CSV
    cases_csv_path = OUT_DIR / "vosk_wav2vec2_cases_300cases.csv"
    pd.DataFrame(case_records).to_csv(cases_csv_path, index=False)
    print(f"Saved: {cases_csv_path}")

    # 2. Save Vosk/Wav2Vec2 Summary CSV
    df_res = pd.DataFrame(case_records)
    sum_rows = []
    for m in models:
        m_id = m["id"]
        sub = df_res[df_res["model_id"] == m_id]
        sum_rows.append({
            "model_id": m_id,
            "model_name": m["name"],
            "cases_count": len(sub),
            "mean_latency_sec": round(sub["latency_sec"].mean(), 2),
            "median_latency_sec": round(sub["latency_sec"].median(), 2),
            "mean_wer_criterion_a": round(sub["wer_criterion_a"].mean(), 2),
            "mean_wer_criterion_b": round(sub["wer_criterion_b"].mean(), 2),
            "median_wer_criterion_b": round(sub["wer_criterion_b"].median(), 2),
            "cer_case_percent": round(sub["cer_case"].mean() * 100.0, 2),
            "mean_slot_accuracy": round(sub["slot_accuracy"].mean(), 2)
        })
    summary_csv_path = OUT_DIR / "vosk_wav2vec2_summary_300cases.csv"
    pd.DataFrame(sum_rows).to_csv(summary_csv_path, index=False)
    print(f"Saved: {summary_csv_path}")

    # 3. Compile Unified Table 6 (Cross-Architecture Comparison across 300 cases)
    # Merging with C0, C1, C5 from controlled ablation
    ablation_sum_path = OUT_DIR / "controlled_ablation_summary_300cases.csv"
    if ablation_sum_path.exists():
        df_abl = pd.read_csv(ablation_sum_path)
        c0 = df_abl[df_abl["condition_id"] == "C0_ct2_fp32_baseline"].iloc[0]
        c1 = df_abl[df_abl["condition_id"] == "C1_vanilla"].iloc[0]
        c5 = df_abl[df_abl["condition_id"] == "C5_full_pathowhisper"].iloc[0]

        unified_table6 = [
            {
                "system": "Vosk (Small en-us, Kaldi C++)",
                "sample_size": 300,
                "latency_mean_sec": sum_rows[0]["mean_latency_sec"],
                "wer_b_percent": sum_rows[0]["mean_wer_criterion_b"],
                "cer_case_percent": sum_rows[0]["cer_case_percent"],
                "slot_acc_percent": sum_rows[0]["mean_slot_accuracy"]
            },
            {
                "system": "Meta Wav2Vec 2.0 Base (PyTorch CTC)",
                "sample_size": 300,
                "latency_mean_sec": sum_rows[1]["mean_latency_sec"],
                "wer_b_percent": sum_rows[1]["mean_wer_criterion_b"],
                "cer_case_percent": sum_rows[1]["cer_case_percent"],
                "slot_acc_percent": sum_rows[1]["mean_slot_accuracy"]
            },
            {
                "system": "Whisper Small Baseline (CT2 FP32, Beam 5)",
                "sample_size": 300,
                "latency_mean_sec": c0["mean_latency_core_sec"],
                "wer_b_percent": c0["mean_wer_criterion_b_all"],
                "cer_case_percent": c0["cer_case_percent_all"],
                "slot_acc_percent": c0["mean_slot_accuracy_all"]
            },
            {
                "system": "Faster-Whisper Small (CT2 INT8, Beam 5)",
                "sample_size": 300,
                "latency_mean_sec": c1["mean_latency_core_sec"],
                "wer_b_percent": c1["mean_wer_criterion_b_all"],
                "cer_case_percent": c1["cer_case_percent_all"],
                "slot_acc_percent": c1["mean_slot_accuracy_all"]
            },
            {
                "system": "PathoWhisper Small (INT8, Prompt, afftdn, Beam 1)",
                "sample_size": 300,
                "latency_mean_sec": c5["mean_latency_core_sec"],
                "wer_b_percent": c5["mean_wer_criterion_b_all"],
                "cer_case_percent": c5["cer_case_percent_all"],
                "slot_acc_percent": c5["mean_slot_accuracy_all"]
            }
        ]
        t6_path = OUT_DIR / "table6_cross_architecture_300cases.csv"
        pd.DataFrame(unified_table6).to_csv(t6_path, index=False)
        print(f"\n[UNIFIED TABLE 6 GENERATED (N = 300 Cases Uniform Cohort)]\nSaved: {t6_path}")

        print("\n" + "=" * 100)
        print("TABLE 6: CROSS-ARCHITECTURE COMPARISON (N = 300 CASES UNIFORM COHORT)")
        print("=" * 100)
        print(f"{'System':<48} | {'N':<4} | {'Latency (s)':<12} | {'WER-B (%)':<10} | {'CER_case (%)':<13} | {'Slot Acc (%)'}")
        print("-" * 100)
        for row in unified_table6:
            print(f"{row['system']:<48} | {row['sample_size']:<4} | {row['latency_mean_sec']:<12.2f} | {row['wer_b_percent']:<10.2f} | {row['cer_case_percent']:<13.2f} | {row['slot_acc_percent']:.2f}%")
        print("=" * 100 + "\n")

    # Copy to Downloads
    dl = Path(r"C:\Users\project\Downloads")
    for fname in ["vosk_wav2vec2_cases_300cases.csv", "vosk_wav2vec2_summary_300cases.csv", "table6_cross_architecture_300cases.csv"]:
        f_src = OUT_DIR / fname
        if f_src.exists():
            import shutil
            shutil.copy2(f_src, dl / fname)

if __name__ == "__main__":
    run_vosk_wav2vec2_300cases()
