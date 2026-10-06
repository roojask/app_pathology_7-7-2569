"""
run_real_ablation_study.py
Executes a REAL Ablation Study across configurations on Category 8 (Fume Hood Noise -10dB)
and Category 7 (High-Speed Rapid Speech) using authentic audio files.
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

# Ensure bin/ffmpeg is in PATH for whisper and ffmpeg calls
os.environ['PATH'] = str(BASE_DIR / 'bin') + os.pathsep + os.environ.get('PATH', '')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import whisper
from faster_whisper import WhisperModel
import jiwer

from configs.config import Config
from src.stt.whisper_model import denoise_audio

GT_PATH = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000.json"
AUDIO_DIR = BASE_DIR / "data" / "dataset_1000" / "audio"
OUTPUT_CSV = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "ablation_study_results.csv"

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
    print("=" * 80)
    print("[SECTION] REAL ABLATION STUDY (CATEGORY 8: FUME HOOD & CATEGORY 7: RAPID SPEECH)")
    print("=" * 80)

    with open(GT_PATH, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    # Select representative cases from Cat 8 and Cat 7 (10 cases each for fast, rigorous verification)
    cat8_cases = [cid for cid, d in gt_data.items() if d.get("category_id") == 8][:10]
    cat7_cases = [cid for cid, d in gt_data.items() if d.get("category_id") == 7][:10]
    target_cases = cat8_cases + cat7_cases
    print(f"Selected {len(cat8_cases)} cases from Cat 8 and {len(cat7_cases)} cases from Cat 7 (Total {len(target_cases)} cases)", flush=True)

    # Models
    print("[Loading] Loading Standard PyTorch Whisper Small (FP32)...")
    pytorch_small = whisper.load_model("small")

    print("[Loading] Loading Faster-Whisper Small (INT8)...")
    ct2_int8 = WhisperModel("small", device="cpu", compute_type="int8")

    configurations = [
        {"id": "cfg1_baseline", "name": "Whisper Small FP32 (Baseline)", "model": "pytorch", "beam": 5, "afftdn": False, "prompt": False},
        {"id": "cfg2_afftdn", "name": "+ afftdn Spectral Denoise", "model": "pytorch", "beam": 5, "afftdn": True, "prompt": False},
        {"id": "cfg3_prompt", "name": "+ CAP Pathology Prompt", "model": "pytorch", "beam": 5, "afftdn": True, "prompt": True},
        {"id": "cfg4_int8", "name": "+ INT8 Quantization (Beam 5)", "model": "ct2_int8", "beam": 5, "afftdn": True, "prompt": True},
        {"id": "cfg5_full", "name": "+ Greedy Beam 1 (Full PathoWhisper)", "model": "ct2_int8", "beam": 1, "afftdn": True, "prompt": True},
    ]

    results_table = []

    for cfg in configurations:
        print(f"\n---> Evaluating Configuration: {cfg['name']} ...")
        latencies = []
        wers_cat8 = []
        wers_cat7 = []

        for cid in target_cases:
            gt = gt_data[cid]
            ref_text = gt.get("raw_text", "")
            cat_id = gt.get("category_id")
            audio_path = AUDIO_DIR / gt["audio_filename"]

            t0 = time.time()
            # 1. Audio Prep
            processed_audio = str(denoise_audio(audio_path)) if cfg["afftdn"] else str(audio_path)

            # 2. Transcribe
            hyp_text = ""
            prompt_text = Config.PATHOLOGY_PROMPT if cfg["prompt"] else None

            if cfg["model"] == "pytorch":
                res = pytorch_small.transcribe(processed_audio, initial_prompt=prompt_text, beam_size=cfg["beam"], language="en")
                hyp_text = res.get("text", "")
            else:
                segments, info = ct2_int8.transcribe(processed_audio, initial_prompt=prompt_text, beam_size=cfg["beam"], language="en")
                hyp_text = " ".join([seg.text for seg in segments]).strip()

            elapsed = time.time() - t0
            latencies.append(elapsed)
            w = calc_wer(ref_text, hyp_text)
            if cat_id == 8:
                wers_cat8.append(w)
            elif cat_id == 7:
                wers_cat7.append(w)

        avg_lat = round(sum(latencies) / len(latencies), 2)
        avg_w8 = round(sum(wers_cat8) / len(wers_cat8), 2)
        avg_w7 = round(sum(wers_cat7) / len(wers_cat7), 2)
        avg_overall_wer = round((avg_w8 + avg_w7) / 2.0, 2)

        results_table.append({
            "config_id": cfg["id"],
            "config_name": cfg["name"],
            "wer_cat8_fume_hood": avg_w8,
            "wer_cat7_rapid_speech": avg_w7,
            "wer_combined": avg_overall_wer,
            "avg_latency_sec": avg_lat
        })
        print(f"     Result: Cat 8 WER = {avg_w8}% | Cat 7 WER = {avg_w7}% | Latency = {avg_lat}s")

    # Save to CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["config_id", "config_name", "wer_cat8_fume_hood", "wer_cat7_rapid_speech", "wer_combined", "avg_latency_sec"])
        writer.writeheader()
        writer.writerows(results_table)

    print("\n" + "=" * 90)
    print("FINAL ABLATION STUDY TABLE (AUTHENTIC EMPIRICAL BENCHMARK):")
    print("=" * 90)
    print(f"{'Configuration':<42} | {'WER Cat 8 (Noise)':<18} | {'WER Cat 7 (Rapid)':<18} | {'Latency (s)':<12}")
    print("-" * 90)
    for r in results_table:
        print(f"{r['config_name']:<42} | {r['wer_cat8_fume_hood']:>16.2f}% | {r['wer_cat7_rapid_speech']:>16.2f}% | {r['avg_latency_sec']:>10.2f}s")
    print("=" * 90)
    print(f"Saved Ablation Study results to: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
