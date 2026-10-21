"""
benchmarks/scripts/test_threads_4_vs_8.py
Direct empirical test comparing cpu_threads=4 vs cpu_threads=8 on 5 cases (offline)
"""
import sys
import os
import time
import json
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

from configs.config import Config

DATASET_DIR = BASE_DIR / "data" / "dataset_1000"
AUDIO_DIR = DATASET_DIR / "audio"

model_dir = str(BASE_DIR / "models" / "faster_whisper_small")
if not os.path.exists(model_dir):
    model_dir = "small"

cases_test = [f"case_{i:04d}" for i in range(1, 6)]

print(f"Loading model with cpu_threads=4 from {model_dir}...", flush=True)
m4 = WhisperModel(model_dir, device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)

print(f"Loading model with cpu_threads=8 from {model_dir}...", flush=True)
m8 = WhisperModel(model_dir, device="cpu", compute_type="int8", cpu_threads=8, local_files_only=True)

lats_4 = []
lats_8 = []

print(f"\n{'Case':<12} | {'4 Threads (s)':<15} | {'8 Threads (s)':<15} | {'Diff / Speedup':<15}", flush=True)
print("-" * 65, flush=True)

for cid in cases_test:
    audio_path = AUDIO_DIR / f"{cid}.mp3"
    
    t0 = time.time()
    segs4, _ = m4.transcribe(str(audio_path), language="en", initial_prompt=Config.PATHOLOGY_PROMPT, beam_size=1)
    text4 = " ".join([s.text for s in segs4])
    dur4 = time.time() - t0
    lats_4.append(dur4)
    
    t0 = time.time()
    segs8, _ = m8.transcribe(str(audio_path), language="en", initial_prompt=Config.PATHOLOGY_PROMPT, beam_size=1)
    text8 = " ".join([s.text for s in segs8])
    dur8 = time.time() - t0
    lats_8.append(dur8)
    
    print(f"{cid:<12} | {dur4:>13.2f}s | {dur8:>13.2f}s | {dur4/dur8:>13.2f}x", flush=True)

print("=" * 65, flush=True)
print(f"Mean Latency (4 threads): {np.mean(lats_4):.2f}s", flush=True)
print(f"Mean Latency (8 threads): {np.mean(lats_8):.2f}s", flush=True)
print(f"Speedup of 8 vs 4 threads: {np.mean(lats_4)/np.mean(lats_8):.2f}x", flush=True)
