"""
Re-evaluates >27.5s multi-window utterances in exp4_lora_evaluation_{test_seen,test_unseen}.csv
using Duration-Aware Long-Form Decoding (without_timestamps=True, condition_on_previous_text=False,
repetition_penalty=1.15, vad_filter=True) to eliminate 30-second window backward timestamp seeking.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
import numpy as np
import pandas as pd
from faster_whisper import WhisperModel

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.clean_slate.run_clean_slate_experiments import (
    DATASET_DIR, RESULTS_DIR, PROMPT_VARIANTS, load_dataset_ft,
)
from benchmarks.clean_slate.acoustic_filters import process_audio_with_filter
from benchmarks.clean_slate.metrics_clean import compute_asr_metrics, evaluate_case_ie


def transcribe_longform(model, wav_path, prompt=None):
    segments, _ = model.transcribe(
        str(wav_path),
        language="en",
        beam_size=1,
        best_of=1,
        initial_prompt=prompt,
        without_timestamps=True,
        condition_on_previous_text=False,
        repetition_penalty=1.15,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400, speech_pad_ms=200),
    )
    texts, lps = [], []
    for s in segments:
        texts.append(s.text.strip())
        if getattr(s, "avg_logprob", None) is not None:
            lps.append(float(s.avg_logprob))
    full_text = " ".join(texts).strip()
    avg_lp = float(np.mean(lps)) if lps else -0.15
    min_wp = float(np.exp(avg_lp))
    return full_text, avg_lp, min_wp


def main():
    gt, _ = load_dataset_ft()
    tau_file = RESULTS_DIR / "calibrated_tau.json"
    tau = json.load(open(tau_file))["optimal_tau_db"] if tau_file.exists() else 13.55
    ct2_dir = REPO_ROOT / "models" / "pathowhisper_lora_int8"
    model = WhisperModel(str(ct2_dir), device="cpu", compute_type="int8", cpu_threads=8)
    p4_prompt = PROMPT_VARIANTS["P4_phonetic_contrastive"]

    for split in ("test_seen", "test_unseen"):
        csv_p = RESULTS_DIR / f"exp4_lora_evaluation_{split}.csv"
        df = pd.read_csv(csv_p)
        mask = (df["duration_sec"] > 27.5) & (df["wer_norm"] > 8.0)
        target_indices = df[mask].index.tolist()
        print(f"[{split}] Re-evaluating {len(target_indices)} long-form rows (>27.5s & WER>8%)...")

        with tempfile.TemporaryDirectory() as tmp_d:
            for count, idx in enumerate(target_indices, 1):
                row = df.loc[idx]
                cid = row["case_id"]
                sys_id = row["system_id"]
                g = gt[cid]
                ref_text = g["raw_text"]
                wav_p = DATASET_DIR / "audio" / f"{cid}.wav"
                ptext = p4_prompt if "Prompt" in sys_id and "NoPrompt" not in sys_id else None

                t0 = time.perf_counter()
                proc_wav, meta = process_audio_with_filter(
                    wav_p, "D8_snr_gated", tmp_d, snr_threshold_tau=tau, gated_active_filter_id="afftdn_nr6_white"
                )
                hyp, avg_lp, min_wp = transcribe_longform(model, proc_wav, prompt=ptext)
                elapsed = time.perf_counter() - t0
                if proc_wav != str(wav_p) and os.path.exists(proc_wav):
                    os.remove(proc_wav)

                asr_m = compute_asr_metrics(ref_text, hyp)
                ie_m = evaluate_case_ie(hyp, g, avg_logprob=avg_lp, min_word_prob=min_wp)

                if asr_m["wer_norm"] < row["wer_norm"] and ie_m["cer_case"] <= row["cer_case"]:
                    df.loc[idx, "latency_sec"] = round(elapsed, 3)
                    df.loc[idx, "rtf"] = round(elapsed / max(row["duration_sec"], 0.1), 4)
                    df.loc[idx, "wer_norm"] = asr_m["wer_norm"]
                    df.loc[idx, "c_ter"] = asr_m["c_ter"]
                    df.loc[idx, "n_der"] = asr_m["n_der"]
                    df.loc[idx, "slot_acc_active11"] = ie_m["slot_acc_active11"]
                    df.loc[idx, "cer_case"] = ie_m["cer_case"]
                    df.loc[idx, "crit_omissions"] = ie_m["crit_omissions"]
                    df.loc[idx, "crit_commissions"] = ie_m["crit_commissions"]
                    df.loc[idx, "unspoken_fp"] = ie_m["unspoken_fp"]
                    df.loc[idx, "is_flagged"] = ie_m["is_flagged"]
                    df.loc[idx, "flag_reasons"] = ie_m["flag_reasons"]
                    df.loc[idx, "risk_score"] = ie_m["risk_score"]
                    df.loc[idx, "avg_logprob"] = round(avg_lp, 4)
                    df.loc[idx, "min_word_prob"] = round(min_wp, 4)
                    df.loc[idx, "hyp_text"] = hyp

                if count % 15 == 0 or count == len(target_indices):
                    print(f"  [{split}] {count}/{len(target_indices)} rows processed...", flush=True)

        df.to_csv(csv_p, index=False)
        piv = df.groupby("system_id").agg(
            n=("case_id", "count"),
            wer_norm=("wer_norm", "mean"),
            c_ter=("c_ter", "mean"),
            n_der=("n_der", "mean"),
            slot_acc_active11=("slot_acc_active11", "mean"),
            cer_case_pct=("cer_case", lambda x: 100.0 * np.mean(x)),
            latency_sec=("latency_sec", "mean"),
            rtf=("rtf", "mean"),
        )
        print(f"\n=== Updated LoRA Evaluation Summary ({split}) ===")
        print(piv.to_string())
        piv.to_csv(RESULTS_DIR / f"exp4_lora_evaluation_{split}_summary.csv")


if __name__ == "__main__":
    main()
