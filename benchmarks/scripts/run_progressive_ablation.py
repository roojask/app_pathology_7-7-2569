"""
run_progressive_ablation.py
Progressive Ablation Study: saves results after EVERY case to CSV
Evaluates 5 configurations across Category 8 (Fume Hood) and Category 7 (Rapid Speech)
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
os.environ['PATH'] = str(BASE_DIR / 'bin') + os.pathsep + os.environ.get('PATH', '')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from faster_whisper import WhisperModel
import jiwer

from configs.config import Config
from src.stt.whisper_model import denoise_audio

GT_PATH = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000.json"
AUDIO_DIR = BASE_DIR / "data" / "dataset_1000" / "audio"
OUTPUT_CSV = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "progressive_ablation_results.csv"
SUMMARY_CSV = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "ablation_summary_table.csv"

def clean_for_wer(text):
    if not text: return ""
    t = str(text).lower()
    t = re.sub(r'[.,;:!?\-]', ' ', t)
    return " ".join(t.split())

def calc_wer(ref, hyp):
    r = clean_for_wer(ref)
    h = clean_for_wer(hyp)
    if not r or not h: return 100.0
    return round(jiwer.wer(r, h) * 100.0, 2)

def main():
    print("=" * 80, flush=True)
    print("PROGRESSIVE ABLATION BENCHMARK (CAT 8: FUME HOOD & CAT 7: RAPID SPEECH)", flush=True)
    print("=" * 80, flush=True)

    with open(GT_PATH, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    # 5 cases from Cat 8, 5 cases from Cat 7
    cat8_cases = [cid for cid, d in gt_data.items() if d.get("category_id") == 8][:5]
    cat7_cases = [cid for cid, d in gt_data.items() if d.get("category_id") == 7][:5]
    target_cases = cat8_cases + cat7_cases
    print(f"Target cases: {target_cases}", flush=True)

    # Preload models
    print("[Loading] Preloading Faster-Whisper FP32...", flush=True)
    m_fp32 = WhisperModel("small", device="cpu", compute_type="float32")
    print("[Loading] Preloading Faster-Whisper INT8...", flush=True)
    m_int8 = WhisperModel("small", device="cpu", compute_type="int8")

    configurations = [
        {"id": "cfg1_baseline", "name": "Whisper Small FP32 (Baseline)", "model": m_fp32, "beam": 5, "afftdn": False, "prompt": False},
        {"id": "cfg2_afftdn", "name": "+ afftdn Spectral Denoise", "model": m_fp32, "beam": 5, "afftdn": True, "prompt": False},
        {"id": "cfg3_prompt", "name": "+ CAP Pathology Prompt", "model": m_fp32, "beam": 5, "afftdn": True, "prompt": True},
        {"id": "cfg4_int8", "name": "+ INT8 Quantization (Beam 5)", "model": m_int8, "beam": 5, "afftdn": True, "prompt": True},
        {"id": "cfg5_beam1", "name": "+ Greedy Beam 1 (Full PathoWhisper)", "model": m_int8, "beam": 1, "afftdn": True, "prompt": True},
    ]

    # Initialize CSV
    fieldnames = ["config_id", "config_name", "case_id", "category_id", "latency_sec", "wer", "ref_text", "hyp_text"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

    summary_records = []

    for cfg in configurations:
        print(f"\n---> Testing Configuration: {cfg['name']}", flush=True)
        wers_cat8 = []
        wers_cat7 = []
        lats = []

        for cid in target_cases:
            gt = gt_data[cid]
            ref_text = gt.get("raw_text", "")
            cat_id = gt.get("category_id")
            audio_path = AUDIO_DIR / gt["audio_filename"]

            t0 = time.time()
            proc_audio = str(denoise_audio(audio_path)) if cfg["afftdn"] else str(audio_path)
            prompt_arg = Config.PATHOLOGY_PROMPT if cfg["prompt"] else None

            segments, _ = cfg["model"].transcribe(proc_audio, initial_prompt=prompt_arg, beam_size=cfg["beam"], language="en")
            hyp_text = " ".join([s.text for s in segments]).strip()
            elapsed = round(time.time() - t0, 2)

            w = calc_wer(ref_text, hyp_text)
            lats.append(elapsed)
            if cat_id == 8: wers_cat8.append(w)
            elif cat_id == 7: wers_cat7.append(w)

            # Append to detailed CSV immediately
            with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writerow({
                    "config_id": cfg["id"],
                    "config_name": cfg["name"],
                    "case_id": cid,
                    "category_id": cat_id,
                    "latency_sec": elapsed,
                    "wer": w,
                    "ref_text": ref_text,
                    "hyp_text": hyp_text
                })

            print(f"  [{cid}] Cat {cat_id} | Time: {elapsed}s | WER: {w}%", flush=True)

        avg_lat = round(sum(lats) / len(lats), 2)
        avg_w8 = round(sum(wers_cat8) / len(wers_cat8), 2)
        avg_w7 = round(sum(wers_cat7) / len(wers_cat7), 2)
        avg_all = round((avg_w8 + avg_w7) / 2.0, 2)

        summary_records.append({
            "config_id": cfg["id"],
            "config_name": cfg["name"],
            "wer_cat8_noise": avg_w8,
            "wer_cat7_rapid": avg_w7,
            "wer_combined": avg_all,
            "avg_latency": avg_lat
        })
        print(f"==> Finished {cfg['name']}: Cat 8 WER = {avg_w8}% | Cat 7 WER = {avg_w7}% | Latency = {avg_lat}s", flush=True)

    with open(SUMMARY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["config_id", "config_name", "wer_cat8_noise", "wer_cat7_rapid", "wer_combined", "avg_latency"])
        writer.writeheader()
        writer.writerows(summary_records)

    print("\n" + "=" * 90, flush=True)
    print("FINAL ABLATION SUMMARY TABLE:", flush=True)
    print("=" * 90, flush=True)
    print(f"{'Configuration':<40} | {'Cat 8 (Noise)':<15} | {'Cat 7 (Rapid)':<15} | {'Latency (s)':<12}", flush=True)
    print("-" * 90, flush=True)
    for r in summary_records:
        print(f"{r['config_name']:<40} | {r['wer_cat8_noise']:>13.2f}% | {r['wer_cat7_rapid']:>13.2f}% | {r['avg_latency']:>10.2f}s", flush=True)
    print("=" * 90, flush=True)

if __name__ == "__main__":
    main()
