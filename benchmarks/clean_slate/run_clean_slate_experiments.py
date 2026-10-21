"""
run_clean_slate_experiments.py -- Master Runner for the Clean-Slate Thesis Redesign.
Strictly isolated in benchmarks/clean_slate/ (does not touch any legacy tables or files).

Stages:
  1. snr_calib    : Build Multi-SNR audio benchmark (+10, +5, 0, -5, -10 dB), calibrate max-margin
                    blind SNR threshold tau* on VAL, and verify blind routing on TEST_SEEN & TEST_UNSEEN.
  2. filter_study : Part 2A: afftdn Parameter Grid Search (nr in {6,12,18,24} x nt in {white,vinyl,custom}) on -10 dB noise.
                    Part 2B: Cross-Filter Benchmark (No Filter, Band-pass, anlmdn, Spectral Gate, afftdn, D8 SNR-Gated)
                             across SNR in {Clean, +5, 0, -5, -10 dB}.
  3. prompt_study : Systematic Prompt Structure & Token-Budget Ablation (P0..P4 + token lengths) on Unseen Phrasings,
                    plus Static afftdn vs. SNR-Gated D8 comparison on full Test Set.
  4. arch_study   : Cross-Architecture (Vosk, Wav2Vec2, Whisper FP32) & Quantized Model Size Study (Tiny, Base, Small, Medium INT8).
  5. lora_eval    : Evaluate CTranslate2 INT8 LoRA Fine-Tuned Model vs Zero-Shot & Prompt-Conditioned on Test-Seen & Test-Unseen.
"""
import argparse
import csv
import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.io import wavfile
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
import configs.config  # Ensure bin/ffmpeg is in PATH

from scripts.make_finetune_data import mix_noise
from benchmarks.clean_slate.metrics_clean import (
    compute_asr_metrics,
    evaluate_case_ie,
    compute_macro_f1_active11,
)
from benchmarks.clean_slate.acoustic_filters import (
    FILTER_CONFIGS,
    estimate_blind_snr,
    process_audio_with_filter,
)

DATASET_DIR = REPO_ROOT / "data" / "dataset_ft"
RESULTS_DIR = REPO_ROOT / "benchmarks" / "clean_slate" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Systematic Prompt Variants (Zero sentence-template overlap with test_seen/test_unseen)
# ---------------------------------------------------------------------------
PROMPT_VARIANTS = {
    "P0_no_prompt": None,
    "P1_domain_role": (
        "Surgical pathology gross examination report of breast cancer specimen following CAP protocol."
    ),
    "P2_unstructured_glossary": (
        "surgical number, modified radical mastectomy, simple mastectomy, formalin, "
        "skin ellipse, nipple everted, inverted, retracted, biopsy scar, biopsy cavity, residual mass, "
        "infiltrative mass, fibrocystic change, discrete mass, "
        "upper outer quadrant, upper inner quadrant, lower outer quadrant, lower inner quadrant, central, "
        "deep resection margin, superior margin, inferior margin, medial margin, lateral margin, "
        "axillary lymph nodes, ductal carcinoma in situ, microinvasion, unremarkable parenchyma, cm, mm."
    ),
    "P3_numerical_format": (
        "Accession number S-00-0000. Dimensions 0.0 x 0.0 x 0.0 cm. "
        "Skin 0.0 x 0.0 cm. Margin 0.0 cm. Ranging from 0.0 to 0.0 cm."
    ),
    "P4_phonetic_contrastive": (
        "Gross pathology breast specimen (CAP protocol). "
        "Terminology & homophone disambiguation: right breast vs left breast (not write), "
        "modified radical mastectomy, simple mastectomy, skin ellipse, "
        "nipple everted, inverted, retracted, healed biopsy scar, biopsy cavity with residual mass, "
        "infiltrative mass vs no discrete mass (not discreet), entirely fibrocystic change (not fibrousistic), "
        "ductal carcinoma in situ with microinvasion, "
        "upper outer, upper inner, lower outer, lower inner, central quadrant, "
        "deep surgical margin (not lymph or weight margin), superior, inferior, medial, lateral margin, "
        "axillary lymph nodes. Format: S-00-0000, 0.0 x 0.0 x 0.0 cm."
    ),
    "P4_budget_50tok": (
        "Breast gross pathology: right or left modified radical mastectomy, simple mastectomy, "
        "nipple everted, biopsy scar, cavity, infiltrative mass, no discrete mass, fibrocystic change, "
        "deep surgical margin, axillary lymph nodes, S-00-0000, cm."
    ),
    "P4_budget_100tok": (
        "Breast gross pathology (CAP protocol): right breast, left breast, modified radical mastectomy, "
        "simple mastectomy, skin ellipse, nipple everted, inverted, retracted, biopsy scar, biopsy cavity, residual mass, "
        "infiltrative mass, no discrete mass, fibrocystic change, "
        "ductal carcinoma in situ, microinvasion, upper outer, upper inner, lower outer, lower inner, central quadrant, "
        "deep resection margin, superior, inferior, medial, lateral margin, axillary lymph nodes. S-00-0000, 0.0 x 0.0 x 0.0 cm."
    ),
}


def load_dataset_ft():
    gt = json.load(open(DATASET_DIR / "ground_truth_ft.json", encoding="utf-8"))
    manifest = list(csv.DictReader(open(DATASET_DIR / "manifest.csv", encoding="utf-8")))
    return gt, manifest


def transcribe_faster_whisper(
    model: WhisperModel,
    audio_path: str,
    prompt: str | None,
    beam_size: int = 1,
    word_timestamps: bool = False,
) -> tuple[str, float, float]:
    segments, _ = model.transcribe(
        audio_path,
        initial_prompt=prompt,
        beam_size=beam_size,
        language="en",
        word_timestamps=word_timestamps,
        condition_on_previous_text=False,
    )
    texts, logprobs, word_probs = [], [], []
    for seg in segments:
        texts.append(seg.text)
        if seg.avg_logprob is not None:
            logprobs.append(float(seg.avg_logprob))
        if word_timestamps and seg.words:
            for w in seg.words:
                if w.probability is not None:
                    word_probs.append(float(w.probability))
    hyp = " ".join(texts).strip()
    avg_lp = float(np.mean(logprobs)) if logprobs else -0.25
    if word_probs:
        min_wp = float(np.min(word_probs))
    elif logprobs:
        min_wp = float(np.exp(np.min(logprobs)))
    else:
        min_wp = 0.85
    return hyp, avg_lp, min_wp


# ---------------------------------------------------------------------------
# Stage 1: Multi-SNR Dataset Generation & Blind SNR Threshold Calibration
# ---------------------------------------------------------------------------
def run_snr_calibration():
    print("=" * 80)
    print("[STAGE 1] Generating Controlled Multi-SNR Benchmark & Calibrating Blind SNR Threshold (tau)")
    print("=" * 80)
    gt, manifest = load_dataset_ft()
    noise_wav = DATASET_DIR / "fume_hood_noise.wav"
    noise = decode_audio(str(noise_wav), sampling_rate=16000).astype("float64")

    multisnrs_dir = DATASET_DIR / "audio_multisnrs"
    multisnrs_dir.mkdir(parents=True, exist_ok=True)

    val_rows = [r for r in manifest if r["split"] == "val"]
    snr_levels = [10, 5, 0, -5, -10]

    snr_records = []
    for r in val_rows:
        cid = r["case_id"]
        clean_path = DATASET_DIR / "audio_clean" / f"{cid}.wav"
        if not clean_path.exists():
            continue
        info_clean = estimate_blind_snr(clean_path)
        snr_records.append({
            "case_id": cid, "split": "val", "true_condition": "clean",
            "true_snr_db": 99.0, "est_snr_db": info_clean["snr_db"],
            "p15_db": info_clean["p15_db"], "p85_db": info_clean["p85_db"],
            "duration_sec": info_clean["duration_sec"],
            "audio_path": str(clean_path),
        })
        if (int(cid.split("_")[1]) % 10) < 3:
            x = decode_audio(str(clean_path), sampling_rate=16000).astype("float64")
            for snr_db in snr_levels:
                out_p = multisnrs_dir / f"{cid}_snr{snr_db:+d}dB.wav"
                if not out_p.exists():
                    rng = random.Random(f"multisnr-{cid}-{snr_db}")
                    y = mix_noise(x, noise, snr_db, rng=rng)
                    wavfile.write(str(out_p), 16000, (y * 32767.0).astype(np.int16))
                info_n = estimate_blind_snr(out_p)
                snr_records.append({
                    "case_id": cid, "split": "val_multisnr", "true_condition": f"noisy_{snr_db:+d}dB",
                    "true_snr_db": float(snr_db), "est_snr_db": info_n["snr_db"],
                    "p15_db": info_n["p15_db"], "p85_db": info_n["p85_db"],
                    "duration_sec": info_n["duration_sec"],
                    "audio_path": str(out_p),
                })

    df_snr = pd.DataFrame(snr_records)
    df_snr.to_csv(RESULTS_DIR / "snr_calibration_val.csv", index=False)

    clean_vals = df_snr[df_snr["true_condition"] == "clean"]["est_snr_db"].values
    noisy_vals = df_snr[df_snr["true_condition"] != "clean"]["est_snr_db"].values

    # Find all thresholds achieving maximum Youden's J and take their midpoint (maximum margin)
    taus = np.linspace(5.0, 30.0, 501)
    js = [float(np.mean(clean_vals >= t) + np.mean(noisy_vals < t) - 1.0) for t in taus]
    max_j = max(js)
    optimal_band = [t for t, j in zip(taus, js) if abs(j - max_j) < 1e-6]
    best_tau = round(float(np.mean(optimal_band)), 2)

    print(f"[SNR Calibration on VAL] Clean Est. SNR: {np.mean(clean_vals):.2f} +/- {np.std(clean_vals):.2f} dB (min={np.min(clean_vals):.2f})")
    print(f"[SNR Calibration on VAL] Noisy Est. SNR: {np.mean(noisy_vals):.2f} +/- {np.std(noisy_vals):.2f} dB (max={np.max(noisy_vals):.2f})")
    print(f"[SNR Calibration on VAL] Max-Margin Threshold tau* = {best_tau:.2f} dB (Optimal Plateau: [{min(optimal_band):.2f}, {max(optimal_band):.2f}] dB, Youden's J = {max_j:.4f})")

    summary = df_snr.groupby("true_condition").agg(
        n=("case_id", "count"),
        est_snr_mean=("est_snr_db", "mean"),
        est_snr_std=("est_snr_db", "std"),
        est_snr_min=("est_snr_db", "min"),
        est_snr_max=("est_snr_db", "max"),
        p15_mean=("p15_db", "mean"),
        routed_to_denoise_pct=("est_snr_db", lambda s: round(100.0 * np.mean(s < best_tau), 2)),
    )
    print("\n=== Blind SNR Distribution & Routing Accuracy by True Condition (VAL) ===")
    print(summary.to_string())
    summary.to_csv(RESULTS_DIR / "snr_calibration_summary.csv")

    # Verify blind routing on TEST_SEEN (150) and TEST_UNSEEN (150)
    test_records = []
    for r in manifest:
        if r["split"] not in ("test_seen", "test_unseen"):
            continue
        wav_p = DATASET_DIR / "audio" / f"{r['case_id']}.wav"
        if not wav_p.exists():
            continue
        info_t = estimate_blind_snr(wav_p)
        is_noisy_gt = int(r["category"]) == 8
        routed_denoise = info_t["snr_db"] < best_tau
        test_records.append({
            "case_id": r["case_id"],
            "split": r["split"],
            "category": int(r["category"]),
            "is_noisy_gt": is_noisy_gt,
            "est_snr_db": info_t["snr_db"],
            "p15_db": info_t["p15_db"],
            "routed_denoise": routed_denoise,
            "routing_correct": int(is_noisy_gt == routed_denoise),
        })
    if test_records:
        df_test_snr = pd.DataFrame(test_records)
        df_test_snr.to_csv(RESULTS_DIR / "blind_snr_test_routing.csv", index=False)
        test_piv = df_test_snr.groupby(["split", "is_noisy_gt"]).agg(
            n=("case_id", "count"),
            est_snr_mean=("est_snr_db", "mean"),
            est_snr_min=("est_snr_db", "min"),
            est_snr_max=("est_snr_db", "max"),
            routed_denoise_pct=("routed_denoise", lambda x: round(100.0 * np.mean(x), 2)),
            routing_acc_pct=("routing_correct", lambda x: round(100.0 * np.mean(x), 2)),
        )
        print("\n=== Blind SNR Routing Verification on Unseen Test Sets (TEST_SEEN & TEST_UNSEEN) ===")
        print(test_piv.to_string())
        test_piv.to_csv(RESULTS_DIR / "blind_snr_test_routing_summary.csv")

    json.dump({"optimal_tau_db": best_tau, "youden_j": max_j}, open(RESULTS_DIR / "calibrated_tau.json", "w"))
    return best_tau


# ---------------------------------------------------------------------------
# Stage 2: Filter Benchmark, Grid Search, and SNR-Gated Adaptive Denoising (D8)
# ---------------------------------------------------------------------------
def run_filter_study(split: str = "val", max_cases: int = 20):
    print("=" * 80)
    print(f"[STAGE 2] Cross-Filter Benchmark, Parameter Grid Search & SNR-Gated Denoising ({split}, N={max_cases})")
    print("=" * 80)
    gt, manifest = load_dataset_ft()
    tau_file = RESULTS_DIR / "calibrated_tau.json"
    tau = json.load(open(tau_file))["optimal_tau_db"] if tau_file.exists() else 13.55

    model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=8)
    prompt = PROMPT_VARIANTS["P4_phonetic_contrastive"]

    multisnrs_dir = DATASET_DIR / "audio_multisnrs"
    per_cat = max(1, max_cases // 10)
    val_rows = [r for r in manifest if r["split"] == "val" and (int(r["case_id"].split("_")[1]) % 10) < per_cat]

    # Part 2A: Parameter Grid Search of afftdn on -10dB Fume Hood Noise
    grid_csv = RESULTS_DIR / f"exp2a_afftdn_grid_{split}.csv"
    done_grid = set()
    if grid_csv.exists():
        for row in csv.DictReader(open(grid_csv, encoding="utf-8")):
            done_grid.add((row["case_id"], row["filter_id"]))

    grid_filters = [
        "F0_no_filter",
        "afftdn_nr6_white", "afftdn_nr12_white", "afftdn_nr18_white", "afftdn_nr24_white",
        "afftdn_nr6_vinyl", "afftdn_nr12_vinyl", "afftdn_nr18_vinyl", "afftdn_nr24_vinyl",
        "afftdn_nr12_custom", "afftdn_nr18_custom",
    ]
    fieldnames = [
        "case_id", "category", "snr_cond", "filter_id", "est_snr_db", "chosen_filter",
        "gated_decision", "duration_sec", "latency_sec", "rtf",
        "wer_norm", "c_ter", "n_der", "slot_acc_active11", "cer_case",
        "crit_omissions", "crit_commissions", "is_flagged", "risk_score",
    ]
    write_h = not grid_csv.exists()
    f_grid = open(grid_csv, "a", encoding="utf-8", newline="")
    w_grid = csv.DictWriter(f_grid, fieldnames=fieldnames)
    if write_h:
        w_grid.writeheader()

    print(f"--> Running Part 2A: afftdn Parameter Grid Search on -10 dB Fume Hood Noise (N={len(val_rows)})...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        for idx_r, r in enumerate(val_rows, 1):
            cid = r["case_id"]
            g = gt[cid]
            ref_text = g["raw_text"]
            wav_p = multisnrs_dir / f"{cid}_snr-10dB.wav"
            if not wav_p.exists():
                continue
            for fid in grid_filters:
                if (cid, fid) in done_grid:
                    continue
                t0 = time.perf_counter()
                proc_wav, meta = process_audio_with_filter(wav_p, fid, tmp_dir, snr_threshold_tau=tau)
                hyp, avg_lp, min_wp = transcribe_faster_whisper(model, proc_wav, prompt=prompt, beam_size=1)
                elapsed = time.perf_counter() - t0
                if proc_wav != str(wav_p) and os.path.exists(proc_wav):
                    os.remove(proc_wav)
                asr_m = compute_asr_metrics(ref_text, hyp)
                ie_m = evaluate_case_ie(hyp, g, avg_logprob=avg_lp, min_word_prob=min_wp)
                dur = max(meta["duration_sec"], 0.1)
                w_grid.writerow({
                    "case_id": cid, "category": g["cat_idx"], "snr_cond": "-10dB", "filter_id": fid,
                    "est_snr_db": meta["snr_db"], "chosen_filter": meta["chosen_filter"],
                    "gated_decision": meta["gated_decision"], "duration_sec": round(dur, 3),
                    "latency_sec": round(elapsed, 3), "rtf": round(elapsed / dur, 4),
                    "wer_norm": asr_m["wer_norm"], "c_ter": asr_m["c_ter"], "n_der": asr_m["n_der"],
                    "slot_acc_active11": ie_m["slot_acc_active11"], "cer_case": ie_m["cer_case"],
                    "crit_omissions": ie_m["crit_omissions"], "crit_commissions": ie_m["crit_commissions"],
                    "is_flagged": ie_m["is_flagged"], "risk_score": ie_m["risk_score"],
                })
                f_grid.flush()
            if idx_r % 5 == 0 or idx_r == len(val_rows):
                print(f"  [Grid Search Progress] {idx_r}/{len(val_rows)} cases completed...", flush=True)
    f_grid.close()

    df_grid = pd.read_csv(grid_csv)
    piv_grid = df_grid.groupby("filter_id").agg(
        n=("case_id", "count"),
        wer_norm=("wer_norm", "mean"),
        c_ter=("c_ter", "mean"),
        n_der=("n_der", "mean"),
        slot_acc_active11=("slot_acc_active11", "mean"),
        cer_case_pct=("cer_case", lambda x: 100.0 * np.mean(x)),
        latency_sec=("latency_sec", "mean"),
        rtf=("rtf", "mean"),
    ).sort_values("wer_norm")
    print("\n=== Part 2A: afftdn Parameter Grid Search Summary (-10 dB) ===")
    print(piv_grid.to_string())
    piv_grid.to_csv(RESULTS_DIR / f"exp2a_afftdn_grid_{split}_summary.csv")

    # Select best afftdn config from Grid Search
    afftdn_rows = piv_grid[piv_grid.index.str.startswith("afftdn_")]
    best_afftdn_id = str(afftdn_rows.index[0]) if len(afftdn_rows) > 0 else "afftdn_nr12_custom"
    print(f"--> Selected Optimal afftdn Config from Grid Search: {best_afftdn_id}")

    # Part 2B: Cross-Filter Benchmark across SNR levels (Clean, +5, 0, -5, -10 dB)
    cross_csv = RESULTS_DIR / f"exp2b_cross_filter_multisnr_{split}.csv"
    done_cross = set()
    if cross_csv.exists():
        for row in csv.DictReader(open(cross_csv, encoding="utf-8")):
            done_cross.add((row["case_id"], row["snr_cond"], row["filter_id"]))

    cross_filters = [
        "F0_no_filter",
        "F1_bandpass",
        "F2_anlmdn",
        "F3_spectral_gate",
        "afftdn_nr12_white",
        best_afftdn_id,
        "D8_snr_gated",
    ]
    # Remove duplicates while preserving order
    cross_filters = list(dict.fromkeys(cross_filters))
    snr_conds = ["clean", "+5dB", "+0dB", "-5dB", "-10dB"]

    write_hc = not cross_csv.exists()
    f_cross = open(cross_csv, "a", encoding="utf-8", newline="")
    w_cross = csv.DictWriter(f_cross, fieldnames=fieldnames)
    if write_hc:
        w_cross.writeheader()

    print(f"--> Running Part 2B: Cross-Filter Benchmark across 5 SNR levels (N={len(val_rows)} per SNR)...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        for idx_r, r in enumerate(val_rows, 1):
            cid = r["case_id"]
            g = gt[cid]
            ref_text = g["raw_text"]
            for snr_c in snr_conds:
                if snr_c == "clean":
                    wav_p = DATASET_DIR / "audio_clean" / f"{cid}.wav"
                else:
                    snr_val = int(snr_c.replace("dB", ""))
                    wav_p = multisnrs_dir / f"{cid}_snr{snr_val:+d}dB.wav"
                if not wav_p.exists():
                    continue
                for fid in cross_filters:
                    if (cid, snr_c, fid) in done_cross:
                        continue
                    t0 = time.perf_counter()
                    proc_wav, meta = process_audio_with_filter(
                        wav_p, fid, tmp_dir, snr_threshold_tau=tau, gated_active_filter_id=best_afftdn_id
                    )
                    hyp, avg_lp, min_wp = transcribe_faster_whisper(model, proc_wav, prompt=prompt, beam_size=1)
                    elapsed = time.perf_counter() - t0
                    if proc_wav != str(wav_p) and os.path.exists(proc_wav):
                        os.remove(proc_wav)
                    asr_m = compute_asr_metrics(ref_text, hyp)
                    ie_m = evaluate_case_ie(hyp, g, avg_logprob=avg_lp, min_word_prob=min_wp)
                    dur = max(meta["duration_sec"], 0.1)
                    w_cross.writerow({
                        "case_id": cid, "category": g["cat_idx"], "snr_cond": snr_c, "filter_id": fid,
                        "est_snr_db": meta["snr_db"], "chosen_filter": meta["chosen_filter"],
                        "gated_decision": meta["gated_decision"], "duration_sec": round(dur, 3),
                        "latency_sec": round(elapsed, 3), "rtf": round(elapsed / dur, 4),
                        "wer_norm": asr_m["wer_norm"], "c_ter": asr_m["c_ter"], "n_der": asr_m["n_der"],
                        "slot_acc_active11": ie_m["slot_acc_active11"], "cer_case": ie_m["cer_case"],
                        "crit_omissions": ie_m["crit_omissions"], "crit_commissions": ie_m["crit_commissions"],
                        "is_flagged": ie_m["is_flagged"], "risk_score": ie_m["risk_score"],
                    })
                    f_cross.flush()
            if idx_r % 5 == 0 or idx_r == len(val_rows):
                print(f"  [Cross-Filter Progress] {idx_r}/{len(val_rows)} cases completed across all 5 SNRs...", flush=True)
    f_cross.close()

    df_cross = pd.read_csv(cross_csv)
    piv_cross = df_cross.groupby(["snr_cond", "filter_id"]).agg(
        n=("case_id", "count"),
        wer_norm=("wer_norm", "mean"),
        c_ter=("c_ter", "mean"),
        n_der=("n_der", "mean"),
        slot_acc_active11=("slot_acc_active11", "mean"),
        cer_case_pct=("cer_case", lambda x: 100.0 * np.mean(x)),
        rtf=("rtf", "mean"),
    )
    print("\n=== Part 2B: Cross-Filter Multi-SNR Benchmark Summary ===")
    print(piv_cross.to_string())
    piv_cross.to_csv(RESULTS_DIR / f"exp2b_cross_filter_multisnr_{split}_summary.csv")


# ---------------------------------------------------------------------------
# Stage 3: Systematic Prompt Ablation & Static vs. SNR-Gated on Unseen Test
# ---------------------------------------------------------------------------
def run_prompt_study(split: str = "test_seen"):
    print("=" * 80)
    print(f"[STAGE 3] Systematic Prompt Structure, Token-Budget & SNR-Gated Study on {split}")
    print("=" * 80)
    gt, manifest = load_dataset_ft()
    tau_file = RESULTS_DIR / "calibrated_tau.json"
    tau = json.load(open(tau_file))["optimal_tau_db"] if tau_file.exists() else 13.55

    rows_raw = [r for r in manifest if r["split"] == split]
    # Interleave by position within category (0..14 across cats 1..10) so the first 50 cases are 5 per category
    by_cat = {c: [] for c in range(1, 11)}
    for r in rows_raw:
        by_cat[int(r["category"])].append(r)
    rows = []
    for pos in range(15):
        for c in range(1, 11):
            if pos < len(by_cat[c]):
                rows.append((pos, by_cat[c][pos]))

    model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=8)

    out_csv = RESULTS_DIR / f"exp3_prompt_ablation_{split}.csv"
    done_keys = set()
    if out_csv.exists():
        for row in csv.DictReader(open(out_csv, encoding="utf-8")):
            done_keys.add((row["case_id"], row["prompt_id"]))

    # Include Static afftdn comparison alongside Prompt variants with D8_snr_gated
    all_conditions = [
        ("P0_no_prompt", None, "D8_snr_gated"),
        ("P1_domain_role", PROMPT_VARIANTS["P1_domain_role"], "D8_snr_gated"),
        ("P2_unstructured_glossary", PROMPT_VARIANTS["P2_unstructured_glossary"], "D8_snr_gated"),
        ("P3_numerical_format", PROMPT_VARIANTS["P3_numerical_format"], "D8_snr_gated"),
        ("P4_budget_50tok", PROMPT_VARIANTS["P4_budget_50tok"], "D8_snr_gated"),
        ("P4_budget_100tok", PROMPT_VARIANTS["P4_budget_100tok"], "D8_snr_gated"),
        ("P4_phonetic_contrastive", PROMPT_VARIANTS["P4_phonetic_contrastive"], "D8_snr_gated"),
        ("P4_static_afftdn_always_on", PROMPT_VARIANTS["P4_phonetic_contrastive"], "afftdn_nr12_white"),
        ("P4_no_filter_always_off", PROMPT_VARIANTS["P4_phonetic_contrastive"], "F0_no_filter"),
    ]
    core_condition_ids = {
        "P0_no_prompt",
        "P4_phonetic_contrastive",
        "P4_static_afftdn_always_on",
        "P4_no_filter_always_off",
    }

    fieldnames = [
        "case_id", "category", "split", "prompt_id", "filter_mode", "est_snr_db", "gated_decision",
        "duration_sec", "latency_sec", "rtf",
        "wer_norm", "c_ter", "n_der", "slot_acc_active11", "cer_case",
        "crit_omissions", "crit_commissions", "unspoken_fp",
        "is_flagged", "flag_reasons", "risk_score", "avg_logprob", "min_word_prob", "hyp_text",
    ]
    write_header = not out_csv.exists()
    f_out = open(out_csv, "a", encoding="utf-8", newline="")
    writer = csv.DictWriter(f_out, fieldnames=fieldnames)
    if write_header:
        writer.writeheader()

    with tempfile.TemporaryDirectory() as tmp_dir:
        for idx_r, (pos_in_cat, r) in enumerate(rows, 1):
            cid = r["case_id"]
            g = gt[cid]
            ref_text = g["raw_text"]
            wav_p = DATASET_DIR / "audio" / f"{cid}.wav"
            if not wav_p.exists():
                continue
            # First 50 stratified cases (5 per category across all 10 categories) run all 9 prompt/token-budget variants;
            # all 150 cases run the 4 primary system conditions (P0, P4+SNRGated, P4+StaticAfftdn, P4+NoFilter).
            active_conds = all_conditions if pos_in_cat < 5 else [c for c in all_conditions if c[0] in core_condition_ids]
            filter_cache = {}
            for pid, ptext, fmode in active_conds:
                if (cid, pid) in done_keys:
                    continue
                if fmode not in filter_cache:
                    tf0 = time.perf_counter()
                    proc_wav, meta = process_audio_with_filter(
                        wav_p, fmode, tmp_dir, snr_threshold_tau=tau, gated_active_filter_id="afftdn_nr6_white"
                    )
                    tf_el = time.perf_counter() - tf0
                    filter_cache[fmode] = (proc_wav, meta, tf_el)
                proc_wav, meta, tf_el = filter_cache[fmode]

                t0 = time.perf_counter()
                hyp, avg_lp, min_wp = transcribe_faster_whisper(model, proc_wav, prompt=ptext, beam_size=1)
                elapsed = tf_el + (time.perf_counter() - t0)

                asr_m = compute_asr_metrics(ref_text, hyp)
                ie_m = evaluate_case_ie(hyp, g, avg_logprob=avg_lp, min_word_prob=min_wp)
                dur = max(meta["duration_sec"], 0.1)
                writer.writerow({
                    "case_id": cid,
                    "category": g["cat_idx"],
                    "split": split,
                    "prompt_id": pid,
                    "filter_mode": fmode,
                    "est_snr_db": meta["snr_db"],
                    "gated_decision": meta["gated_decision"],
                    "duration_sec": round(dur, 3),
                    "latency_sec": round(elapsed, 3),
                    "rtf": round(elapsed / dur, 4),
                    "wer_norm": asr_m["wer_norm"],
                    "c_ter": asr_m["c_ter"],
                    "n_der": asr_m["n_der"],
                    "slot_acc_active11": ie_m["slot_acc_active11"],
                    "cer_case": ie_m["cer_case"],
                    "crit_omissions": ie_m["crit_omissions"],
                    "crit_commissions": ie_m["crit_commissions"],
                    "unspoken_fp": ie_m["unspoken_fp"],
                    "is_flagged": ie_m["is_flagged"],
                    "flag_reasons": ie_m["flag_reasons"],
                    "risk_score": ie_m["risk_score"],
                    "avg_logprob": round(avg_lp, 4),
                    "min_word_prob": round(min_wp, 4),
                    "hyp_text": hyp,
                })
                f_out.flush()
            for proc_wav, _, _ in filter_cache.values():
                if proc_wav != str(wav_p) and os.path.exists(proc_wav):
                    os.remove(proc_wav)
            if idx_r % 15 == 0 or idx_r == len(rows):
                print(f"  [Prompt Study Progress] {idx_r}/{len(rows)} cases completed on {split}...", flush=True)
    f_out.close()

    df_res = pd.read_csv(out_csv)
    piv = df_res.groupby("prompt_id").agg(
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
    print(f"\n=== Prompt & SNR-Gating Study Summary ({split}) ===")
    print(piv.to_string())
    piv.to_csv(RESULTS_DIR / f"exp3_prompt_ablation_{split}_summary.csv")


# ---------------------------------------------------------------------------
# Stage 4: Cross-Architecture & Quantization Baseline Study
# ---------------------------------------------------------------------------
def run_arch_study(split: str = "test_seen", max_per_cat: int = 5):
    print("=" * 80)
    print(f"[STAGE 4] Cross-Architecture & Quantization Study ({split}, {max_per_cat} per cat = {max_per_cat*10} cases)")
    print("=" * 80)
    gt, manifest = load_dataset_ft()
    rows_all = [r for r in manifest if r["split"] == split]
    # Stratified sample across all 10 categories
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
    write_header = not out_csv.exists()
    f_out = open(out_csv, "a", encoding="utf-8", newline="")
    writer = csv.DictWriter(f_out, fieldnames=fieldnames)
    if write_header:
        writer.writeheader()

    # 1. Faster-Whisper INT8 sizes (Tiny, Base, Small, Medium) + Small FP32 (CTranslate2 float32)
    ct2_models = [
        ("FW_Tiny_INT8", "tiny", "int8"),
        ("FW_Base_INT8", "base", "int8"),
        ("FW_Small_INT8", "small", "int8"),
        ("FW_Small_FP32", "small", "float32"),
        ("FW_Medium_INT8", "medium", "int8"),
    ]
    for arch_id, m_size, comp_type in ct2_models:
        pending = [r for r in selected_rows if (r["case_id"], arch_id) not in done_keys]
        if not pending:
            continue
        print(f"--> Evaluating {arch_id} ({m_size}, {comp_type}) on {len(pending)} cases...", flush=True)
        model = WhisperModel(m_size, device="cpu", compute_type=comp_type, cpu_threads=8)
        for r in pending:
            cid = r["case_id"]
            g = gt[cid]
            wav_p = DATASET_DIR / "audio" / f"{cid}.wav"
            dur = len(decode_audio(str(wav_p), sampling_rate=16000)) / 16000.0
            t0 = time.perf_counter()
            hyp, avg_lp, min_wp = transcribe_faster_whisper(model, str(wav_p), prompt=None, beam_size=1)
            elapsed = time.perf_counter() - t0
            asr_m = compute_asr_metrics(g["raw_text"], hyp)
            ie_m = evaluate_case_ie(hyp, g, avg_logprob=avg_lp, min_word_prob=min_wp)
            writer.writerow({
                "case_id": cid, "category": g["cat_idx"], "split": split, "arch_id": arch_id,
                "duration_sec": round(dur, 3), "latency_sec": round(elapsed, 3), "rtf": round(elapsed / max(dur, 0.1), 4),
                "wer_norm": asr_m["wer_norm"], "c_ter": asr_m["c_ter"], "n_der": asr_m["n_der"],
                "slot_acc_active11": ie_m["slot_acc_active11"], "cer_case": ie_m["cer_case"],
                "crit_omissions": ie_m["crit_omissions"], "crit_commissions": ie_m["crit_commissions"],
                "hyp_text": hyp,
            })
            f_out.flush()
        del model

    # 2. Vosk (Kaldi-based Hybrid DNN-HMM) if available
    try:
        import vosk
        import wave
        vosk.SetLogLevel(-1)
        vosk_dirs = list((REPO_ROOT / "models").glob("*vosk*")) + list(REPO_ROOT.glob("*vosk*"))
        if vosk_dirs:
            v_model = vosk.Model(str(vosk_dirs[0]))
            arch_id = "Vosk_Kaldi_DNN_HMM"
            pending = [r for r in selected_rows if (r["case_id"], arch_id) not in done_keys]
            if pending:
                print(f"--> Evaluating {arch_id} on {len(pending)} cases...", flush=True)
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
    except Exception as e:
        print("  [Vosk skipped]:", e)

    # 3. Wav2Vec 2.0 (CTC Transformer) if available
    try:
        import torch
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        arch_id = "Wav2Vec2_Base_CTC"
        pending = [r for r in selected_rows if (r["case_id"], arch_id) not in done_keys]
        if pending:
            print(f"--> Evaluating {arch_id} on {len(pending)} cases...", flush=True)
            processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-base-960h")
            w2v_model = Wav2Vec2ForCTC.from_pretrained("facebook/wav2vec2-base-960h")
            w2v_model.eval()
            for r in pending:
                cid = r["case_id"]
                g = gt[cid]
                wav_p = DATASET_DIR / "audio" / f"{cid}.wav"
                y = decode_audio(str(wav_p), sampling_rate=16000).astype(np.float32)
                dur = len(y) / 16000.0
                t0 = time.perf_counter()
                inputs = processor(y, sampling_rate=16000, return_tensors="pt", padding=True)
                with torch.no_grad():
                    logits = w2v_model(inputs.input_values).logits
                pred_ids = torch.argmax(logits, dim=-1)
                hyp = processor.batch_decode(pred_ids)[0].lower().strip()
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
    except Exception as e:
        print("  [Wav2Vec2 skipped]:", e)

    f_out.close()
    df_res = pd.read_csv(out_csv)
    piv = df_res.groupby("arch_id").agg(
        n=("case_id", "count"),
        wer_norm=("wer_norm", "mean"),
        c_ter=("c_ter", "mean"),
        n_der=("n_der", "mean"),
        slot_acc_active11=("slot_acc_active11", "mean"),
        cer_case_pct=("cer_case", lambda x: 100.0 * np.mean(x)),
        latency_sec=("latency_sec", "mean"),
        rtf=("rtf", "mean"),
    )
    print(f"\n=== Cross-Architecture & Quantization Summary ({split}) ===")
    print(piv.to_string())
    piv.to_csv(RESULTS_DIR / f"exp1_cross_arch_{split}_summary.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["snr_calib", "filter_study", "prompt_study", "arch_study", "all_core"])
    ap.add_argument("--split", default="val")
    ap.add_argument("--max-cases", type=int, default=20)
    args = ap.parse_args()

    if args.stage == "snr_calib":
        run_snr_calibration()
    elif args.stage == "filter_study":
        run_filter_study(split=args.split, max_cases=args.max_cases)
    elif args.stage == "prompt_study":
        run_prompt_study(split=args.split)
    elif args.stage == "arch_study":
        run_arch_study(split=args.split, max_per_cat=args.max_cases)
    elif args.stage == "all_core":
        run_snr_calibration()
        run_filter_study(split="val", max_cases=args.max_cases)
        run_arch_study(split="test_seen", max_per_cat=5)
        run_prompt_study(split="test_seen")
        run_prompt_study(split="test_unseen")


if __name__ == "__main__":
    main()
