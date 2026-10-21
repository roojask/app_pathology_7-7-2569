"""
Expand Stage 4 Cross-Architecture & Quantization Baseline Study on dataset_ft (test_seen, N=50 stratified).
Adds:
  1. Vosk_Kaldi_DNN_HMM (vosk-model-small-en-us-0.15, Kaldi TDNN-F + FST)
  2. Wav2Vec2_Large_LV60_CTC (facebook/wav2vec2-large-960h-lv60-self)
  3. HuBERT_Large_CTC (facebook/hubert-large-ls960-ft)
  4. WavLM_Base_Plus_CTC (patrickvonplaten/wavlm-libri-clean-100h-base-plus)
  5. PathoWhisper_Small_LoRA_INT8 (Proposed S3: Whisper Small LoRA r=8 INT8 + P4 + D8_snr_gated)
"""
import csv
import json
import os
import sys
import time
import wave
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from faster_whisper.audio import decode_audio

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "benchmarks" / "clean_slate"))

from run_clean_slate_experiments import (
    DATASET_DIR,
    RESULTS_DIR,
    load_dataset_ft,
    compute_asr_metrics,
    evaluate_case_ie,
)


def main():
    split = "test_seen"
    max_per_cat = 5
    gt, manifest = load_dataset_ft()
    rows_all = [r for r in manifest if r["split"] == split]
    by_cat = {}
    for r in rows_all:
        c = int(r["category"])
        by_cat.setdefault(c, []).append(r)
    selected_rows = []
    for c in sorted(by_cat.keys()):
        selected_rows.extend(by_cat[c][:max_per_cat])

    out_csv = RESULTS_DIR / f"exp1_cross_arch_{split}.csv"
    done_keys = set()
    if out_csv.exists():
        for row in csv.DictReader(open(out_csv, encoding="utf-8")):
            done_keys.add((row["case_id"], row["arch_id"]))

    fieldnames = [
        "case_id", "category", "split", "arch_id", "duration_sec", "latency_sec", "rtf",
        "wer_norm", "c_ter", "n_der", "slot_acc_active11", "cer_case",
        "crit_omissions", "crit_commissions", "hyp_text",
    ]
    f_out = open(out_csv, "a", encoding="utf-8", newline="")
    writer = csv.DictWriter(f_out, fieldnames=fieldnames)

    # 1. Vosk (Kaldi TDNN-F + FST)
    arch_id = "Vosk_Kaldi_DNN_HMM"
    pending = [r for r in selected_rows if (r["case_id"], arch_id) not in done_keys]
    if pending:
        print(f"--> Evaluating {arch_id} on {len(pending)} cases...", flush=True)
        import vosk
        vosk.SetLogLevel(-1)
        v_model = vosk.Model(lang="en-us")
        for r in pending:
            cid = r["case_id"]
            g = gt[cid]
            wav_p = DATASET_DIR / "audio" / f"{cid}.wav"
            t0 = time.perf_counter()
            wf = wave.open(str(wav_p), "rb")
            dur = wf.getnframes() / float(wf.getframerate())
            rec = vosk.KaldiRecognizer(v_model, wf.getframerate())
            parts = []
            while True:
                data_b = wf.readframes(4000)
                if len(data_b) == 0:
                    break
                if rec.AcceptWaveform(data_b):
                    parts.append(json.loads(rec.Result()).get("text", ""))
            parts.append(json.loads(rec.FinalResult()).get("text", ""))
            wf.close()
            hyp = " ".join(p for p in parts if p).strip()
            elapsed = time.perf_counter() - t0
            asr_m = compute_asr_metrics(g["raw_text"], hyp)
            ie_m = evaluate_case_ie(hyp, g)
            writer.writerow({
                "case_id": cid, "category": g["cat_idx"], "split": split, "arch_id": arch_id,
                "duration_sec": round(dur, 3), "latency_sec": round(elapsed, 3), "rtf": round(elapsed / max(dur, 0.1), 4),
                "wer_norm": asr_m["wer_norm"], "c_ter": asr_m["c_ter"], "n_der": asr_m["n_der"],
                "slot_acc_active11": ie_m["slot_acc_active11"], "cer_case": ie_m["cer_case"],
                "crit_omissions": ie_m["crit_omissions"], "crit_commissions": ie_m["crit_commissions"],
                "hyp_text": hyp,
            })
            f_out.flush()

    # 2. Additional Self-Supervised CTC Models (Wav2Vec 2.0 Large LV-60k, HuBERT Large, WavLM Base+)
    from transformers import AutoProcessor, AutoModelForCTC
    ctc_models = [
        ("Wav2Vec2_Large_LV60_CTC", "facebook/wav2vec2-large-960h-lv60-self"),
        ("HuBERT_Large_CTC", "facebook/hubert-large-ls960-ft"),
        ("WavLM_Base_Plus_CTC", "patrickvonplaten/wavlm-libri-clean-100h-base-plus"),
    ]
    for arch_id, hf_id in ctc_models:
        pending = [r for r in selected_rows if (r["case_id"], arch_id) not in done_keys]
        if not pending:
            continue
        print(f"--> Evaluating {arch_id} ({hf_id}) on {len(pending)} cases...", flush=True)
        processor = AutoProcessor.from_pretrained(hf_id)
        ctc_model = AutoModelForCTC.from_pretrained(hf_id)
        ctc_model.eval()
        for r in pending:
            cid = r["case_id"]
            g = gt[cid]
            wav_p = DATASET_DIR / "audio" / f"{cid}.wav"
            y = decode_audio(str(wav_p), sampling_rate=16000).astype(np.float32)
            dur = len(y) / 16000.0
            t0 = time.perf_counter()
            inputs = processor(y, sampling_rate=16000, return_tensors="pt", padding=True)
            with torch.no_grad():
                logits = ctc_model(inputs.input_values).logits
            pred_ids = torch.argmax(logits, dim=-1)
            hyp = processor.batch_decode(pred_ids)[0].lower()
            elapsed = time.perf_counter() - t0
            asr_m = compute_asr_metrics(g["raw_text"], hyp)
            ie_m = evaluate_case_ie(hyp, g)
            writer.writerow({
                "case_id": cid, "category": g["cat_idx"], "split": split, "arch_id": arch_id,
                "duration_sec": round(dur, 3), "latency_sec": round(elapsed, 3), "rtf": round(elapsed / max(dur, 0.1), 4),
                "wer_norm": asr_m["wer_norm"], "c_ter": asr_m["c_ter"], "n_der": asr_m["n_der"],
                "slot_acc_active11": ie_m["slot_acc_active11"], "cer_case": ie_m["cer_case"],
                "crit_omissions": ie_m["crit_omissions"], "crit_commissions": ie_m["crit_commissions"],
                "hyp_text": hyp,
            })
            f_out.flush()
        del ctc_model

    # 3. PathoWhisper Small LoRA INT8 (S3_Full_PathoWhisper_LoRA_Prompt_SNRGated on the exact same 50 cases)
    arch_id = "PathoWhisper_Small_LoRA_INT8"
    pending = [r for r in selected_rows if (r["case_id"], arch_id) not in done_keys]
    if pending:
        print(f"--> Adding {arch_id} from S3_Full_PathoWhisper_LoRA_Prompt_SNRGated results on {len(pending)} cases...", flush=True)
        s3_map = {}
        s3_csv = RESULTS_DIR / f"exp4_lora_evaluation_{split}.csv"
        for row in csv.DictReader(open(s3_csv, encoding="utf-8")):
            if row["system_id"] in ("S3_Full_LoRA_System", "LoRA_Small_INT8_P4_D8", "S3_Full_PathoWhisper_LoRA_Prompt_SNRGated"):
                s3_map[row["case_id"]] = row
        for r in pending:
            cid = r["case_id"]
            srow = s3_map[cid]
            writer.writerow({
                "case_id": cid,
                "category": srow["category"],
                "split": split,
                "arch_id": arch_id,
                "duration_sec": srow["duration_sec"],
                "latency_sec": srow["latency_sec"],
                "rtf": srow["rtf"],
                "wer_norm": srow["wer_norm"],
                "c_ter": srow["c_ter"],
                "n_der": srow["n_der"],
                "slot_acc_active11": srow["slot_acc_active11"],
                "cer_case": srow["cer_case"],
                "crit_omissions": srow["crit_omissions"],
                "crit_commissions": srow["crit_commissions"],
                "hyp_text": srow["hyp_text"],
            })
            f_out.flush()

    f_out.close()

    # Compute summary including 15-field Macro-F1 across all 11 architectures
    from metrics_clean import compute_macro_f1_active11
    df_res = pd.read_csv(out_csv)
    piv = df_res.groupby("arch_id").agg(
        n=("case_id", "count"),
        wer_norm=("wer_norm", "mean"),
        c_ter=("c_ter", "mean"),
        n_der=("n_der", "mean"),
        slot_acc_active11=("slot_acc_active11", "mean"),
        cer_case_pct=("cer_case", lambda x: 100.0 * np.mean(x)),
        crit_omissions=("crit_omissions", "sum"),
        crit_commissions=("crit_commissions", "sum"),
        latency_sec=("latency_sec", "mean"),
        rtf=("rtf", "mean"),
    )
    macro_f1s = {}
    for aid, grp in df_res.groupby("arch_id"):
        outcomes_list = [
            evaluate_case_ie(str(r["hyp_text"]) if pd.notna(r["hyp_text"]) else "", gt[r["case_id"]])["outcomes"]
            for _, r in grp.iterrows()
        ]
        macro_f1s[aid] = compute_macro_f1_active11(outcomes_list)["macro_f1"]
    piv["macro_f1_15"] = [macro_f1s[aid] for aid in piv.index]
    print("\n=== Expanded Stage 4 Cross-Architecture & Quantization Summary (N=50 Stratified) ===")
    print(piv.to_string())
    piv.to_csv(RESULTS_DIR / f"exp1_cross_arch_{split}_summary.csv")


if __name__ == "__main__":
    main()
