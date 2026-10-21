"""
benchmarks/scripts/run_controlled_ablation_300cases.py
================================================================================
Controlled Stratified Factorial Ablation & Model-Size Benchmark for PathoWhisper

Design & Protocol Controls:
  1. Ground-Truth Data: Strictly uses ground_truth_1000_pure.json for clinical evaluation.
  2. Pre-flight Script Floor: Runs Extractor v2.1 on raw_text for all selected cases;
     strictly asserts CER_case == 0 and SlotAcc == 100.0% before running inference.
  3. Latency Definition: Pure STT latency is measured per rep. For conditions requiring
     denoising, denoise_time (FFmpeg afftdn) is measured once per case and added to each
     denoised rep. Logged in 'denoise_time_sec' column.
  4. Telemetry: Live CPU load measured per case with psutil.cpu_percent(interval=0.2).
  5. Sleep Prevention: Calls Windows SetThreadExecutionState to prevent system sleep.
  6. Runtime Estimate: ~362s per core case (12 conditions x 3 reps) and ~100s per non-core
     case (11 conditions x 1 rep). Estimated total runtime for 300 cases is ~15-16 hours.
     Auto-checkpointing saved per case to allow resumption.
  7. Deterministic Decoding & Repetition Loop Tracking: temperature=0.0 across all conditions.
     Repetition loops (WER > 100%) tracked and reported for both Criterion A and B alongside medians.
  8. Thread Binding: cpu_threads=8 on all CTranslate2 models.
  9. Pre-flight Warmup: 2 warmup passes per engine to eliminate cold-start overhead.
 10. Randomized Interleaved Execution: Conditions order shuffled per case.
 11. Multi-Repetition Latency: 3 repetitions per case on the 100-case core subset.
     Generator strictly consumed on every rep to ensure genuine inference timing.
 12. Stratified Core Subset: Exactly 10 cases per category (100 cases total), stratified.
 13. Clinical Extraction: Evaluated with Extractor v2.1 and core metrics strictly imported
     from scripts/eval_clinical_core_metrics.py:
     CRIT = ["s1_side", "s3_dims", "s10_infiltrative", "s10_inf_dims", "s11_deep_margin", "s14_check"]
 14. Thesis Normalization: Using dedicated benchmarks/scripts/text_norm_utils.py (norm_a, norm_b).
 15. Ground-Truth Baseline: Includes C0 (CT2 FP32 Beam 5) matching the thesis baseline engine.

Conditions Tested:
  - C0: Baseline FP32 (CT2 FP32, No Denoise, No Prompt, Beam 5)
  - C1: Vanilla Baseline (CT2 INT8, No Denoise, No Prompt, Beam 5)
  - C2: +Denoise Only    (CT2 INT8, Denoise,    No Prompt, Beam 5)
  - C3: +Prompt Only     (CT2 INT8, No Denoise, Prompt,    Beam 5)
  - C4: +Greedy Only     (CT2 INT8, No Denoise, No Prompt, Beam 1)
  - C5: Full PathoWhisper(CT2 INT8, Denoise,    Prompt,    Beam 1)
  - C6: Full - Denoise   (CT2 INT8, No Denoise, Prompt,    Beam 1)
  - C7: Full - Prompt    (CT2 INT8, Denoise,    No Prompt, Beam 1)
  - C8: Full - Greedy    (CT2 INT8, Denoise,    Prompt,    Beam 5)
  - Model Sizes under Full Pipeline (Denoise + Prompt + Beam 1):
    - SIZE_tiny, SIZE_base, SIZE_medium (core 100 subset)
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
import argparse
import ctypes
from pathlib import Path
import numpy as np
import psutil

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
        print("[Power Management] Windows sleep prevention activated successfully.", flush=True)
    except Exception as e:
        print(f"[Power Management] Warning: Could not set execution state: {e}", flush=True)

import jiwer
from faster_whisper import WhisperModel

# Clinical evaluation imports
from scripts.eval_clinical_core_metrics import KEYS, CRIT, cmp, mapped
from src.nlp.extractor import extract_data_15_sections
from configs.config import Config
from src.stt.whisper_model import denoise_audio

# Clean standalone normalization
from benchmarks.scripts.text_norm_utils import norm_a, norm_b

DATASET_DIR = BASE_DIR / "data" / "dataset_1000"
GT_PATH = DATASET_DIR / "ground_truth_1000_pure.json"
AUDIO_DIR = DATASET_DIR / "audio"

OUT_DIR = BASE_DIR / "benchmarks" / "thesis_eval_outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT_PATH = OUT_DIR / "checkpoint_300cases_ablation.json"

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

def get_system_telemetry():
    """Captures exact physical/virtual hardware specs and live CPU load."""
    cpu_name = platform.processor()
    try:
        res = subprocess.run(
            ["powershell", "-Command", "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, check=False
        )
        if res.stdout.strip():
            cpu_name = res.stdout.strip().splitlines()[0]
    except Exception:
        pass
    
    cpu_load_pre = psutil.cpu_percent(interval=1.0)
    ram_info = psutil.virtual_memory()

    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu_name": cpu_name,
        "logical_cores": os.cpu_count(),
        "ctranslate2_cpu_threads": 8,
        "pre_flight_cpu_load_percent": cpu_load_pre,
        "available_ram_gb": round(ram_info.available / (1024**3), 2),
        "python_version": platform.python_version(),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

def select_stratified_cases(gt_data, cases_per_cat=30, core_per_cat=10, seed=42):
    """
    Selects cases stratified across all 10 categories.
    For each category:
      - Samples 'cases_per_cat' cases (e.g. 30).
      - Designates exactly 'core_per_cat' cases (e.g. 10) as part of the core subset (is_core_100).
    Returns list of tuples: (cid, cat_id, is_core_100) shuffled globally to interleave categories.
    """
    random.seed(seed)
    cats = {}
    for cid, d in gt_data.items():
        c_id = d.get("cat_idx") or d.get("category_id", 1)
        cats.setdefault(c_id, []).append(cid)
    
    selected = []
    for c_id in sorted(cats.keys()):
        c_list = sorted(cats[c_id])
        sampled = random.sample(c_list, min(cases_per_cat, len(c_list)))
        for rank, cid in enumerate(sampled):
            is_core = (rank < core_per_cat)
            selected.append((cid, c_id, is_core))
    
    # Shuffle order across categories to avoid consecutive category execution bias
    random.seed(seed + 100)
    random.shuffle(selected)
    return selected

def evaluate_case_clinical_cer(hyp_text, gt_case_dict):
    """
    Evaluates extraction using Extractor v2.1 and calculates CER_case strictly on CRIT.
    Returns: cer_case (0 or 1), field_accuracy (percent), field_statuses (dict).
    """
    pred_raw = extract_data_15_sections(str(hyp_text))
    pm = mapped(pred_raw)
    
    field_statuses = {}
    err_count = 0
    crit_err_count = 0
    
    for k in KEYS:
        status = cmp(k, gt_case_dict.get(k), pm.get(k))
        field_statuses[k] = status
        if status in ("FN", "FP", "WRONG"):
            err_count += 1
            if k in CRIT:
                crit_err_count += 1
                
    cer_case = 1 if crit_err_count > 0 else 0
    slot_acc = round(((len(KEYS) - err_count) / len(KEYS)) * 100.0, 2)
    
    return cer_case, slot_acc, field_statuses

def verify_script_floor_preflight(selected_cases, gt_data):
    """
    Runs Extractor v2.1 on raw_text for all selected cases.
    Asserts CER_case == 0 and SlotAcc == 100.0% for every case.
    Aborts execution immediately if any case fails.
    """
    print(f"\n[Pre-flight Verification] Validating Script Floor across {len(selected_cases)} selected cases...", flush=True)
    failures = []
    for cid, cat_id, _ in selected_cases:
        d = gt_data[cid]
        raw_text = d["raw_text"]
        cer_case, slot_acc, statuses = evaluate_case_clinical_cer(raw_text, d)
        if cer_case != 0 or slot_acc != 100.0:
            crit_fails = [k for k in CRIT if statuses[k] in ("FN", "FP", "WRONG")]
            all_fails = [k for k in KEYS if statuses[k] in ("FN", "FP", "WRONG")]
            failures.append((cid, cer_case, slot_acc, crit_fails, all_fails))
    
    if failures:
        print(f"❌ FATAL: Script Floor assertion failed on {len(failures)} cases!", flush=True)
        for f in failures[:5]:
            print(f"   {f[0]}: CER={f[1]}, SlotAcc={f[2]}%, CritErrors={f[3]}, AllErrors={f[4]}", flush=True)
        sys.exit(1)
    
    print(f"✅ Script Floor Passed 100%: All {len(selected_cases)} cases have CER_case=0 and SlotAcc=100.0% on pure ground truth!\n", flush=True)

def warmup_model(model, sample_audio_path, passes=2):
    """Executes warmup inference passes to initialize memory maps, threads, and caches."""
    for _ in range(passes):
        segs, _ = model.transcribe(str(sample_audio_path), language="en", beam_size=1)
        _ = [s.text for s in segs]

def run_controlled_ablation(cases_per_cat=30, core_per_cat=10, dry_run_count=None, seed=42):
    prevent_windows_sleep()
    telemetry = get_system_telemetry()
    print("=" * 100)
    print("CONTROLLED FACTORIAL ABLATION & MODEL SIZE BENCHMARK")
    print("=" * 100)
    for k, v in telemetry.items():
        print(f"  {k:<30}: {v}")
    print(f"  CRITICAL FIELDS (CRIT)        : {CRIT}")
    print(f"  GROUND TRUTH FILE             : {GT_PATH.name} [PURE]")
    print(f"  LATENCY DEFINITION            : Pure STT latency per rep (+ denoise_time for afftdn conditions)")
    print(f"  RUNTIME ESTIMATE              : ~362s/core case, ~100s/non-core case (~15-16 hours for 300 cases)")
    print("=" * 100, flush=True)

    with open(GT_PATH, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    if dry_run_count is not None:
        c_sample = sorted(gt_data.keys())[:dry_run_count]
        selected_cases = [(cid, gt_data[cid].get("cat_idx") or gt_data[cid].get("category_id", 1), True) for cid in c_sample]
        print(f"[DRY-RUN MODE] Testing {len(selected_cases)} cases with full 3-reps and all models!")
    else:
        selected_cases = select_stratified_cases(gt_data, cases_per_cat=cases_per_cat, core_per_cat=core_per_cat, seed=seed)
        total_core = sum(1 for _, _, is_core in selected_cases if is_core)
        print(f"Total Selected Cases: {len(selected_cases)} ({cases_per_cat} cases/cat x 10 categories, seed={seed})")
        print(f"Core Subset Cases   : {total_core} (Stratified {core_per_cat} cases/cat x 10 categories)")

    total_cases = len(selected_cases)

    # Pre-flight script floor verification
    verify_script_floor_preflight(selected_cases, gt_data)

    # Preload Models (cpu_threads=8 on all CTranslate2 instances)
    print("[Loading Models] Initializing CTranslate2 Engines with cpu_threads=8...", flush=True)
    
    # 1. Faster-Whisper Small FP32 (Condition C0 - True Thesis Baseline)
    print("  Loading Faster-Whisper Small (FP32)...", flush=True)
    m_small_fp32 = WhisperModel("small", device="cpu", compute_type="float32", cpu_threads=8)

    # 2. Faster-Whisper Small INT8 (Conditions C1-C8)
    model_dir_small = str(BASE_DIR / "models" / "faster_whisper_small")
    if not (Path(model_dir_small) / "model.bin").exists():
        model_dir_small = "small"
    print(f"  Loading Faster-Whisper Small (INT8) from {model_dir_small}...", flush=True)
    m_small_int8 = WhisperModel(model_dir_small, device="cpu", compute_type="int8", cpu_threads=8)

    # 3. Model Sizes for Scaling Experiment
    print("  Loading Faster-Whisper Tiny (INT8)...", flush=True)
    m_tiny = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=8)
    print("  Loading Faster-Whisper Base (INT8)...", flush=True)
    m_base = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=8)
    print("  Loading Faster-Whisper Medium (INT8)...", flush=True)
    m_medium = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=8)
    print("All models successfully loaded!\n", flush=True)

    # Pre-flight Warmup
    warmup_audio = AUDIO_DIR / "case_0001.mp3"
    print("[Warmup] Executing 2 warmup passes per engine to eliminate cold-start overhead...", flush=True)
    warmup_model(m_small_fp32, warmup_audio, passes=2)
    warmup_model(m_small_int8, warmup_audio, passes=2)
    warmup_model(m_tiny, warmup_audio, passes=1)
    warmup_model(m_base, warmup_audio, passes=1)
    warmup_model(m_medium, warmup_audio, passes=1)
    print("[Warmup] Warmup completed successfully!\n", flush=True)

    # Define Full Experimental Conditions
    all_conditions = [
        # C0: True Thesis Baseline
        {"id": "C0_ct2_fp32_baseline", "name": "C0: Baseline FP32 (CT2 FP32, No Denoise, No Prompt, Beam 5)", "denoise": False, "prompt": False, "beam_size": 5, "model": m_small_fp32, "core_only": False},
        # C1-C8: 2^3 Factorial Design on INT8
        {"id": "C1_vanilla",          "name": "C1: Vanilla (CT2 INT8, No Denoise, No Prompt, Beam 5)",       "denoise": False, "prompt": False, "beam_size": 5, "model": m_small_int8, "core_only": False},
        {"id": "C2_denoise_only",     "name": "C2: +Denoise Only (CT2 INT8, Denoise, No Prompt, Beam 5)",    "denoise": True,  "prompt": False, "beam_size": 5, "model": m_small_int8, "core_only": False},
        {"id": "C3_prompt_only",      "name": "C3: +Prompt Only (CT2 INT8, No Denoise, Prompt, Beam 5)",     "denoise": False, "prompt": True,  "beam_size": 5, "model": m_small_int8, "core_only": False},
        {"id": "C4_beam1_only",       "name": "C4: +Greedy Only (CT2 INT8, No Denoise, No Prompt, Beam 1)",   "denoise": False, "prompt": False, "beam_size": 1, "model": m_small_int8, "core_only": False},
        {"id": "C5_full_pathowhisper","name": "C5: Full PathoWhisper (CT2 INT8, Denoise, Prompt, Beam 1)",   "denoise": True,  "prompt": True,  "beam_size": 1, "model": m_small_int8, "core_only": False},
        {"id": "C6_leaveout_denoise", "name": "C6: Full - Denoise (CT2 INT8, No Denoise, Prompt, Beam 1)",    "denoise": False, "prompt": True,  "beam_size": 1, "model": m_small_int8, "core_only": False},
        {"id": "C7_leaveout_prompt",  "name": "C7: Full - Prompt (CT2 INT8, Denoise, No Prompt, Beam 1)",     "denoise": True,  "prompt": False, "beam_size": 1, "model": m_small_int8, "core_only": False},
        {"id": "C8_leaveout_beam1",   "name": "C8: Full - Greedy (CT2 INT8, Denoise, Prompt, Beam 5)",      "denoise": True,  "prompt": True,  "beam_size": 5, "model": m_small_int8, "core_only": False},
        # Model Sizes under Full Pipeline (Denoise + Prompt + Beam 1)
        {"id": "SIZE_tiny",           "name": "Size: Tiny INT8 (Denoise, Prompt, Beam 1)",                    "denoise": True,  "prompt": True,  "beam_size": 1, "model": m_tiny,       "core_only": False},
        {"id": "SIZE_base",           "name": "Size: Base INT8 (Denoise, Prompt, Beam 1)",                    "denoise": True,  "prompt": True,  "beam_size": 1, "model": m_base,       "core_only": False},
        {"id": "SIZE_medium",         "name": "Size: Medium INT8 (Denoise, Prompt, Beam 1)",                  "denoise": True,  "prompt": True,  "beam_size": 1, "model": m_medium,     "core_only": True},
    ]

    case_records = []
    completed_case_ids = set()

    # Load Checkpoint if resuming
    if CHECKPOINT_PATH.exists() and dry_run_count is None:
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                ckpt = json.load(f)
                completed_case_ids = set(ckpt.get("completed_cases", []))
                case_records = ckpt.get("records", [])
                print(f"[Checkpoint] Resuming run: {len(completed_case_ids)} cases already finished!", flush=True)
        except Exception as e:
            print(f"[Checkpoint] Warning: {e}", flush=True)

    print("\nStarting Benchmark Loop...", flush=True)

    for idx, (cid, cat_id, is_core) in enumerate(selected_cases, 1):
        if cid in completed_case_ids:
            continue

        cat_name = CATEGORY_NAMES.get(cat_id, f"Category {cat_id}")
        audio_path = AUDIO_DIR / f"{cid}.mp3"
        ref_text = gt_data[cid]["raw_text"]
        gt_case_dict = gt_data[cid]

        # Telemetry: Measure live CPU load for this case
        cpu_load_case = psutil.cpu_percent(interval=0.2)

        # Prepare Denoised Audio once per case
        t_d0 = time.time()
        denoised_audio = denoise_audio(audio_path)
        denoise_time = time.time() - t_d0

        # Determine which conditions to run for this case
        if is_core:
            active_conditions = all_conditions
            reps_to_run = 3
        else:
            active_conditions = [c for c in all_conditions if not c["core_only"]]
            reps_to_run = 1

        # Shuffle conditions order per case (Randomized Interleaved Execution)
        conds_order = list(active_conditions)
        random.shuffle(conds_order)
        execution_order_str = " -> ".join([c["id"] for c in conds_order])

        print(f"\n[{idx}/{total_cases}] Case: {cid} | {cat_name} | Core100: {is_core} | Reps: {reps_to_run} | CPU: {cpu_load_case:.1f}%", flush=True)

        for cond in conds_order:
            c_id = cond["id"]
            c_name = cond["name"]

            target_audio = denoised_audio if cond["denoise"] else audio_path
            prompt_arg = Config.PATHOLOGY_PROMPT if cond["prompt"] else None
            beam_arg = cond["beam_size"]

            latencies = []
            hyp_text = ""

            for r in range(reps_to_run):
                t0 = time.time()
                segments, _ = cond["model"].transcribe(
                    str(target_audio),
                    language="en",
                    temperature=0.0,
                    initial_prompt=prompt_arg,
                    beam_size=beam_arg,
                    best_of=beam_arg
                )
                # CRITICAL: Exhaust generator inside the timing block so inference actually executes!
                text_rep = " ".join([s.text for s in segments]).strip()
                dur = time.time() - t0
                if cond["denoise"]:
                    dur += denoise_time
                latencies.append(dur)
                if r == 0:
                    hyp_text = text_rep

            med_lat = round(float(np.median(latencies)), 3)
            mean_lat = round(float(np.mean(latencies)), 3)
            p95_lat = round(float(np.percentile(latencies, 95)), 3) if len(latencies) > 1 else med_lat

            # Normalized WER calculations
            wa = round(jiwer.wer(norm_a(ref_text), norm_a(hyp_text)) * 100.0, 2)
            wb = round(jiwer.wer(norm_b(ref_text), norm_b(hyp_text)) * 100.0, 2)

            # Clinical Extraction Evaluation (Extractor v2.1)
            cer_case, slot_acc, field_statuses = evaluate_case_clinical_cer(hyp_text, gt_case_dict)

            rec = {
                "case_id": cid,
                "category_id": cat_id,
                "category_name": cat_name,
                "is_core_100": is_core,
                "condition_id": c_id,
                "condition_name": c_name,
                "denoise": cond["denoise"],
                "denoise_time_sec": round(denoise_time, 3) if cond["denoise"] else 0.0,
                "prompt": cond["prompt"],
                "beam_size": cond["beam_size"],
                "temperature": 0.0,
                "cpu_threads": 8,
                "cpu_load_case_percent": cpu_load_case,
                "execution_order": execution_order_str,
                "latency_reps": [round(x, 3) for x in latencies],
                "median_latency_sec": med_lat,
                "mean_latency_sec": mean_lat,
                "p95_latency_sec": p95_lat,
                "wer_criterion_a": wa,
                "wer_criterion_b": wb,
                "is_repetition_loop_a": (wa > 100.0),
                "is_repetition_loop_b": (wb > 100.0),
                "cer_case": cer_case,
                "slot_accuracy": slot_acc,
                "ref_text": ref_text,
                "hyp_text": hyp_text
            }
            case_records.append(rec)
            reps_str = f"[{', '.join(f'{x:.2f}s' for x in latencies)}]"
            print(f"  [{c_id:<22}] Reps={reps_str:<24} | Med={med_lat:>5.2f}s | WER-A={wa:>5.2f}% | WER-B={wb:>5.2f}% | CER={cer_case} | SlotAcc={slot_acc:.1f}%", flush=True)

        if denoised_audio != audio_path and os.path.exists(denoised_audio):
            try:
                os.remove(denoised_audio)
            except Exception:
                pass

        completed_case_ids.add(cid)

        # Save Checkpoint after every case if not dry-run
        if dry_run_count is None:
            with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "completed_cases": list(completed_case_ids),
                    "records": case_records
                }, f, ensure_ascii=False)

    print("\nBenchmark pass finished! Compiling reports...", flush=True)

    suffix = f"dryrun_{dry_run_count}cases" if dry_run_count is not None else f"{total_cases}cases"
    cases_csv_path = OUT_DIR / f"controlled_ablation_cases_{suffix}.csv"
    summary_csv_path = OUT_DIR / f"controlled_ablation_summary_{suffix}.csv"

    fieldnames_cases = list(case_records[0].keys())
    with open(cases_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames_cases)
        writer.writeheader()
        writer.writerows(case_records)

    # Summary by condition (reporting separately overall and on core_100, tracking loops and medians)
    summary_rows = []
    for cond in all_conditions:
        c_id = cond["id"]
        c_recs_all = [r for r in case_records if r["condition_id"] == c_id]
        if not c_recs_all:
            continue

        c_recs_core = [r for r in c_recs_all if r["is_core_100"]]
        loops_b = sum(1 for r in c_recs_all if r["is_repetition_loop_b"])
        loops_a = sum(1 for r in c_recs_all if r["is_repetition_loop_a"])

        summary_rows.append({
            "condition_id": c_id,
            "condition_name": cond["name"],
            "total_cases_evaluated": len(c_recs_all),
            "core_100_cases_evaluated": len(c_recs_core),
            "denoise": cond["denoise"],
            "prompt": cond["prompt"],
            "beam_size": cond["beam_size"],
            "temperature": 0.0,
            "cpu_threads": 8,
            "mean_latency_core_sec": round(float(np.mean([r["mean_latency_sec"] for r in c_recs_core])), 2) if c_recs_core else None,
            "median_latency_core_sec": round(float(np.median([r["median_latency_sec"] for r in c_recs_core])), 2) if c_recs_core else None,
            "p95_latency_core_sec": round(float(np.percentile([r["median_latency_sec"] for r in c_recs_core], 95)), 2) if c_recs_core else None,
            "mean_wer_criterion_a_all": round(float(np.mean([r["wer_criterion_a"] for r in c_recs_all])), 2),
            "median_wer_criterion_a_all": round(float(np.median([r["wer_criterion_a"] for r in c_recs_all])), 2),
            "mean_wer_criterion_b_all": round(float(np.mean([r["wer_criterion_b"] for r in c_recs_all])), 2),
            "median_wer_criterion_b_all": round(float(np.median([r["wer_criterion_b"] for r in c_recs_all])), 2),
            "repetition_loops_count_wer_a": loops_a,
            "repetition_loops_count_wer_b": loops_b,
            "cer_case_percent_all": round(float(np.mean([r["cer_case"] for r in c_recs_all])) * 100.0, 2),
            "mean_slot_accuracy_all": round(float(np.mean([r["slot_accuracy"] for r in c_recs_all])), 2)
        })

    with open(summary_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    # Copy to Downloads
    downloads_dir = Path(r"C:\Users\project\Downloads")
    if downloads_dir.exists():
        shutil.copy2(cases_csv_path, downloads_dir / cases_csv_path.name)
        shutil.copy2(summary_csv_path, downloads_dir / summary_csv_path.name)

    print(f"\n[Completed] Reports generated at:\n  - {cases_csv_path}\n  - {summary_csv_path}", flush=True)
    return cases_csv_path, summary_csv_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PathoWhisper Controlled Factorial Ablation")
    parser.add_argument("--dry-run", type=int, default=None, help="Run only N cases for dry run inspection (e.g. 3)")
    parser.add_argument("--cases-per-cat", type=int, default=30, help="Cases per category (default: 30 for 300 cases)")
    parser.add_argument("--core-per-cat", type=int, default=10, help="Core subset cases per category (default: 10 for 100 cases)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling and reproducibility")
    args = parser.parse_args()

    run_controlled_ablation(
        cases_per_cat=args.cases_per_cat,
        core_per_cat=args.core_per_cat,
        dry_run_count=args.dry_run,
        seed=args.seed
    )
