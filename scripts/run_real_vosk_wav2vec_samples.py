"""
scripts/run_real_vosk_wav2vec_samples.py
================================================================================
Empirical Transcription Comparison on Real Benchmark Audio Cases:
Runs Vosk (bin/vosk-model-small-en-us-0.15) and Wav2Vec 2.0 (facebook/wav2vec2-base-960h)
on benchmark audio files (data/dataset_1000/audio/case_*.mp3)
and compares head-to-head with Baseline Whisper Small and PathoWhisper INT8.
================================================================================
"""

import sys
import json
import subprocess
from pathlib import Path
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# 1. Imports
import pandas as pd
import librosa
from vosk import Model as VoskModel, KaldiRecognizer
from transformers import pipeline

def load_audio_16k(audio_path):
    """Load audio as 16kHz float32 and int16."""
    y, sr = librosa.load(str(audio_path), sr=16000)
    return y, sr

def main():
    print("=" * 80)
    print("EMPIRICAL COMPARISON: VOSK vs WAV2VEC 2.0 vs BASELINE vs PATHOWHISPER")
    print("=" * 80)

    # Load Vosk
    vosk_path = BASE_DIR / "bin" / "vosk-model-small-en-us-0.15"
    if not vosk_path.exists():
        print(f"Error: Vosk model not found at {vosk_path}")
        return
    print(f"Loading Vosk model from: {vosk_path.name}...")
    v_model = VoskModel(str(vosk_path))

    # Load Wav2Vec 2.0
    print("Loading Meta Wav2Vec 2.0 (facebook/wav2vec2-base-960h)...")
    w2v_pipe = pipeline("automatic-speech-recognition", model="facebook/wav2vec2-base-960h")

    # Load Overnight CSV for Baseline & PathoWhisper references
    csv_path = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "benchmark_1000_cases_overnight.csv"
    df = pd.read_csv(csv_path)
    pw_df = df[df.system.str.contains("PathoWhisper", case=False)].set_index("case_id")
    bs_df = df[df.system.str.contains("Baseline", case=False)].set_index("case_id")

    test_cases = ["case_0001", "case_0002", "case_0003"]
    results = []

    for cid in test_cases:
        mp3_path = BASE_DIR / "data" / "dataset_1000" / "audio" / f"{cid}.mp3"
        if not mp3_path.exists():
            print(f"Warning: Audio file not found at {mp3_path}")
            continue

        print(f"\nProcessing {cid} ({mp3_path.name})...")
        y, sr = load_audio_16k(mp3_path)
        int16_samples = (y * 32767).astype(np.int16)

        # 1. Vosk Inference
        rec = KaldiRecognizer(v_model, 16000)
        rec.AcceptWaveform(int16_samples.tobytes())
        vosk_res = json.loads(rec.FinalResult())
        vosk_text = vosk_res.get("text", "")

        # 2. Wav2Vec 2.0 Inference
        w2v_res = w2v_pipe(y)
        w2v_text = w2v_res.get("text", "")

        # 3. Baseline & PathoWhisper
        ref_text = bs_df.loc[cid, "ref_text"]
        bs_text = bs_df.loc[cid, "hyp_text"]
        pw_text = pw_df.loc[cid, "hyp_text"]

        res_item = {
            "case_id": cid,
            "ref": ref_text,
            "vosk": vosk_text,
            "wav2vec2": w2v_text,
            "baseline": bs_text,
            "pathowhisper": pw_text
        }
        results.append(res_item)

        print("-" * 75)
        print(f"CASE: {cid}")
        print(f"• Reference   : {ref_text}")
        print(f"• Vosk        : {vosk_text}")
        print(f"• Wav2Vec 2.0 : {w2v_text}")
        print(f"• Baseline    : {bs_text}")
        print(f"• PathoWhisper: {pw_text}")

    # Save output json
    out_json = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "vosk_wav2vec2_empirical_samples.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n" + "=" * 80)
    print(f"Saved empirical samples to: {out_json}")
    print("=" * 80)

if __name__ == "__main__":
    main()
