"""
train_whisper_lora.py -- Parameter-Efficient Fine-Tuning (LoRA) of Whisper Small
+ Merge & Export to CTranslate2 INT8 + Evaluation on Unseen Phrasings (test_seen & test_unseen).

Architecture:
  - Base Model: openai/whisper-small
  - LoRA Config: r=8, lora_alpha=32, lora_dropout=0.05, target_modules=["q_proj", "v_proj"]
  - Train / Val Split: data/dataset_ft/train.jsonl (600 cases), val.jsonl (100 cases)
  - Post-training: Merge LoRA weights -> Export via CTranslate2 INT8 quantization -> Evaluate on CPU
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def train_and_export_lora(
    dataset_dir: Path,
    output_dir: Path,
    ct2_out_dir: Path,
    max_train_samples: int = 300,
    max_val_samples: int = 50,
    epochs: int = 3,
    batch_size: int = 8,
    lr: float = 1e-4,
    lora_r: int = 8,
    lora_alpha: int = 32,
):
    import tempfile
    import torch
    from torch.utils.data import Dataset, DataLoader
    from transformers import WhisperProcessor, WhisperForConditionalGeneration, AutoTokenizer, get_linear_schedule_with_warmup
    from transformers.modeling_outputs import BaseModelOutput
    from peft import LoraConfig, get_peft_model
    from faster_whisper.audio import decode_audio
    from benchmarks.clean_slate.acoustic_filters import process_audio_with_filter

    torch.set_num_threads(8)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[LoRA Trainer] Using device: {device} | train={max_train_samples}, val={max_val_samples}, epochs={epochs}")

    processor = WhisperProcessor.from_pretrained("openai/whisper-small", language="en", task="transcribe")
    fast_tok = AutoTokenizer.from_pretrained("openai/whisper-small")
    base_model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-small")
    base_model.config.forced_decoder_ids = None
    base_model.config.suppress_tokens = []

    target_mods = [
        name for name, mod in base_model.named_modules()
        if isinstance(mod, torch.nn.Linear) and "decoder" in name and any(k in name for k in ("q_proj", "v_proj"))
    ]
    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=target_mods,
        lora_dropout=0.05,
        bias="none",
    )
    model = get_peft_model(base_model, lora_config)
    for n, p in model.named_parameters():
        if "encoder." in n and "encoder_attn" not in n:
            p.requires_grad = False
    model.print_trainable_parameters()
    model.to(device)

    tau_file = REPO_ROOT / "benchmarks" / "clean_slate" / "results" / "calibrated_tau.json"
    tau = json.load(open(tau_file))["optimal_tau_db"] if tau_file.exists() else 13.55

    def load_stratified_rows(jsonl_path: Path, max_n: int):
        raw = [json.loads(line) for line in open(jsonl_path, encoding="utf-8")]
        by_cat = {c: [] for c in range(1, 11)}
        for r in raw:
            by_cat[int(r["category"])].append(r)
        interleaved = []
        max_pos = max(len(v) for v in by_cat.values())
        for pos in range(max_pos):
            for c in range(1, 11):
                if pos < len(by_cat[c]):
                    interleaved.append(by_cat[c][pos])
        return interleaved[:max_n]

    class PathologyASRDataset(Dataset):
        def __init__(self, jsonl_path: Path, max_n: int):
            self.rows = load_stratified_rows(jsonl_path, max_n)
            self.enc_cache = {}
            self.lbl_cache = {}

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, idx):
            if idx in self.lbl_cache:
                return {"idx": idx, "input_features": None, "labels": self.lbl_cache[idx]}
            r = self.rows[idx]
            wav_path = dataset_dir / r["audio"]
            with tempfile.TemporaryDirectory() as tmp_d:
                proc_wav, _ = process_audio_with_filter(
                    wav_path, "D8_snr_gated", tmp_d, snr_threshold_tau=tau, gated_active_filter_id="afftdn_nr6_white"
                )
                y = decode_audio(str(proc_wav), sampling_rate=16000).astype(np.float32)
            input_features = processor.feature_extractor(y, sampling_rate=16000, return_tensors="pt").input_features[0]
            labels = processor.tokenizer(r["text"], truncation=True, max_length=256, return_tensors="pt").input_ids[0]
            if len(labels) > 0 and int(labels[0]) == int(base_model.config.decoder_start_token_id):
                labels = labels[1:]
            self.lbl_cache[idx] = labels
            return {"idx": idx, "input_features": input_features, "labels": labels}

    def make_collate_fn(ds_obj):
        def collate_fn(batch):
            idxs = [b["idx"] for b in batch]
            need_enc = any(i not in ds_obj.enc_cache for i in idxs)
            input_features = torch.stack([b["input_features"] for b in batch]) if need_enc else None
            label_seqs = [b["labels"] for b in batch]
            max_len = max(len(l) for l in label_seqs)
            padded_labels = torch.full((len(batch), max_len), -100, dtype=torch.long)
            for i, l in enumerate(label_seqs):
                padded_labels[i, :len(l)] = l
            return {"idxs": idxs, "input_features": input_features, "labels": padded_labels}
        return collate_fn

    train_ds = PathologyASRDataset(dataset_dir / "train.jsonl", max_train_samples)
    val_ds = PathologyASRDataset(dataset_dir / "val.jsonl", max_val_samples)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, collate_fn=make_collate_fn(train_ds))
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, collate_fn=make_collate_fn(val_ds))

    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.01)
    total_steps = len(train_loader) * epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=max(1, int(0.1 * total_steps)), num_training_steps=total_steps)

    output_dir.mkdir(parents=True, exist_ok=True)
    log_csv = output_dir / "lora_training_log.csv"
    f_log = open(log_csv, "w", encoding="utf-8", newline="")
    w_log = csv.DictWriter(f_log, fieldnames=["epoch", "step", "train_loss", "val_loss", "elapsed_sec"])
    w_log.writeheader()

    encoder_mod = model.base_model.model.model.encoder
    t_start = time.time()
    global_step = 0
    for ep in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        for step, batch in enumerate(train_loader, 1):
            global_step += 1
            optimizer.zero_grad()
            idxs = batch["idxs"]
            if batch["input_features"] is not None:
                with torch.no_grad():
                    feats = batch["input_features"].to(device)
                    enc_hidden = encoder_mod(feats).last_hidden_state.cpu().half()
                for b_i, sample_idx in enumerate(idxs):
                    train_ds.enc_cache[sample_idx] = enc_hidden[b_i]
            enc_batch = torch.stack([train_ds.enc_cache[i] for i in idxs]).to(device, dtype=torch.float32)
            lbls = batch["labels"].to(device)
            outputs = model(encoder_outputs=BaseModelOutput(last_hidden_state=enc_batch), labels=lbls)
            loss = outputs.loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            running_loss += float(loss.detach().item())
            if step % 5 == 0 or step == len(train_loader):
                avg_tr = running_loss / step
                print(f"  [Epoch {ep}/{epochs} | Step {step}/{len(train_loader)}] train_loss={avg_tr:.4f}", flush=True)

        # Validation pass
        model.eval()
        val_losses = []
        with torch.no_grad():
            for batch in val_loader:
                idxs = batch["idxs"]
                if batch["input_features"] is not None:
                    feats = batch["input_features"].to(device)
                    enc_hidden = encoder_mod(feats).last_hidden_state.cpu().half()
                    for b_i, sample_idx in enumerate(idxs):
                        val_ds.enc_cache[sample_idx] = enc_hidden[b_i]
                enc_batch = torch.stack([val_ds.enc_cache[i] for i in idxs]).to(device, dtype=torch.float32)
                lbls = batch["labels"].to(device)
                out = model(encoder_outputs=BaseModelOutput(last_hidden_state=enc_batch), labels=lbls)
                val_losses.append(float(out.loss.detach().item()))
        val_loss = float(np.mean(val_losses))
        avg_train_loss = running_loss / max(1, len(train_loader))
        elapsed = round(time.time() - t_start, 2)
        print(f"==> [Epoch {ep}/{epochs} Complete] train_loss={avg_train_loss:.4f} | val_loss={val_loss:.4f} ({elapsed}s)", flush=True)
        w_log.writerow({"epoch": ep, "step": global_step, "train_loss": round(avg_train_loss, 4), "val_loss": round(val_loss, 4), "elapsed_sec": elapsed})
        f_log.flush()
    f_log.close()

    # Merge LoRA weights into base model and save HuggingFace checkpoint
    merged_dir = output_dir / "merged_hf"
    print(f"[LoRA Trainer] Merging LoRA adapter into base model -> {merged_dir} ...")
    merged_model = model.merge_and_unload()
    merged_model.save_pretrained(merged_dir)
    processor.save_pretrained(merged_dir)
    processor.feature_extractor.save_pretrained(merged_dir)
    fast_tok.save_pretrained(merged_dir)

    # Convert merged HuggingFace model to CTranslate2 INT8 format for CPU inference
    print(f"[LoRA Trainer] Converting merged model to CTranslate2 INT8 -> {ct2_out_dir} ...")
    if ct2_out_dir.exists():
        import shutil
        shutil.rmtree(ct2_out_dir)
    cmd = [
        sys.executable, "-m", "ctranslate2.converters.transformers",
        "--model", str(merged_dir),
        "--output_dir", str(ct2_out_dir),
        "--quantization", "int8",
        "--copy_files", "tokenizer.json", "preprocessor_config.json",
    ]
    subprocess.run(cmd, check=True)
    print(f"[LoRA Trainer] Successfully exported CTranslate2 INT8 LoRA model to {ct2_out_dir}!")


def evaluate_lora_model(ct2_model_dir: Path, splits=("test_seen", "test_unseen")):
    from faster_whisper import WhisperModel
    from benchmarks.clean_slate.run_clean_slate_experiments import (
        DATASET_DIR, RESULTS_DIR, PROMPT_VARIANTS, load_dataset_ft, transcribe_faster_whisper,
    )
    from benchmarks.clean_slate.acoustic_filters import process_audio_with_filter
    from benchmarks.clean_slate.metrics_clean import compute_asr_metrics, evaluate_case_ie
    import pandas as pd
    import tempfile

    gt, manifest = load_dataset_ft()
    tau_file = RESULTS_DIR / "calibrated_tau.json"
    tau = json.load(open(tau_file))["optimal_tau_db"] if tau_file.exists() else 13.55

    lora_model = WhisperModel(str(ct2_model_dir), device="cpu", compute_type="int8", cpu_threads=8)
    prompt = PROMPT_VARIANTS["P4_phonetic_contrastive"]

    for split in splits:
        rows = [r for r in manifest if r["split"] == split]
        out_csv = RESULTS_DIR / f"exp4_lora_evaluation_{split}.csv"
        done_keys = set()
        if out_csv.exists():
            for row in csv.DictReader(open(out_csv, encoding="utf-8")):
                done_keys.add((row["case_id"], row["system_id"]))

        fieldnames = [
            "case_id", "category", "split", "system_id", "duration_sec", "latency_sec", "rtf",
            "wer_norm", "c_ter", "n_der", "slot_acc_active11", "cer_case",
            "crit_omissions", "crit_commissions", "unspoken_fp",
            "is_flagged", "flag_reasons", "risk_score", "avg_logprob", "min_word_prob", "hyp_text",
        ]
        write_h = not out_csv.exists()
        f_out = open(out_csv, "a", encoding="utf-8", newline="")
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        if write_h:
            writer.writeheader()

        systems = [
            ("S2_LoRA_INT8_NoPrompt", None),
            ("S3_Full_PathoWhisper_LoRA_Prompt_SNRGated", prompt),
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            for idx_r, r in enumerate(rows, 1):
                cid = r["case_id"]
                g = gt[cid]
                ref_text = g["raw_text"]
                wav_p = DATASET_DIR / "audio" / f"{cid}.wav"
                if not wav_p.exists():
                    continue
                pending_sys = [(sys_id, ptext) for sys_id, ptext in systems if (cid, sys_id) not in done_keys]
                if not pending_sys:
                    continue
                tf0 = time.perf_counter()
                proc_wav, meta = process_audio_with_filter(
                    wav_p, "D8_snr_gated", tmp_dir, snr_threshold_tau=tau, gated_active_filter_id="afftdn_nr6_white"
                )
                tf_el = time.perf_counter() - tf0
                for sys_id, ptext in pending_sys:
                    t0 = time.perf_counter()
                    hyp, avg_lp, min_wp = transcribe_faster_whisper(lora_model, proc_wav, prompt=ptext, beam_size=1)
                    elapsed = tf_el + (time.perf_counter() - t0)
                    asr_m = compute_asr_metrics(ref_text, hyp)
                    ie_m = evaluate_case_ie(hyp, g, avg_logprob=avg_lp, min_word_prob=min_wp)
                    dur = max(meta["duration_sec"], 0.1)
                    writer.writerow({
                        "case_id": cid, "category": g["cat_idx"], "split": split, "system_id": sys_id,
                        "duration_sec": round(dur, 3), "latency_sec": round(elapsed, 3), "rtf": round(elapsed / dur, 4),
                        "wer_norm": asr_m["wer_norm"], "c_ter": asr_m["c_ter"], "n_der": asr_m["n_der"],
                        "slot_acc_active11": ie_m["slot_acc_active11"], "cer_case": ie_m["cer_case"],
                        "crit_omissions": ie_m["crit_omissions"], "crit_commissions": ie_m["crit_commissions"],
                        "unspoken_fp": ie_m["unspoken_fp"], "is_flagged": ie_m["is_flagged"],
                        "flag_reasons": ie_m["flag_reasons"], "risk_score": ie_m["risk_score"],
                        "avg_logprob": round(avg_lp, 4), "min_word_prob": round(min_wp, 4), "hyp_text": hyp,
                    })
                    f_out.flush()
                if proc_wav != str(wav_p) and os.path.exists(proc_wav):
                    os.remove(proc_wav)
                if idx_r % 25 == 0 or idx_r == len(rows):
                    print(f"  [LoRA Eval {split}] {idx_r}/{len(rows)} cases completed...", flush=True)
        f_out.close()
        df_res = pd.read_csv(out_csv)
        piv = df_res.groupby("system_id").agg(
            n=("case_id", "count"),
            wer_norm=("wer_norm", "mean"),
            c_ter=("c_ter", "mean"),
            n_der=("n_der", "mean"),
            slot_acc_active11=("slot_acc_active11", "mean"),
            cer_case_pct=("cer_case", lambda x: 100.0 * np.mean(x)),
            latency_sec=("latency_sec", "mean"),
            rtf=("rtf", "mean"),
        )
        print(f"\n=== LoRA Evaluation Summary ({split}) ===")
        print(piv.to_string())
        piv.to_csv(RESULTS_DIR / f"exp4_lora_evaluation_{split}_summary.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["train_and_eval", "eval_only"], default="train_and_eval")
    ap.add_argument("--max-train", type=int, default=600)
    ap.add_argument("--max-val", type=int, default=100)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=8)
    args = ap.parse_args()

    ds_dir = REPO_ROOT / "data" / "dataset_ft"
    out_dir = REPO_ROOT / "benchmarks" / "clean_slate" / "results" / "lora_checkpoints"
    ct2_dir = REPO_ROOT / "models" / "pathowhisper_lora_int8"

    if args.mode == "train_and_eval":
        train_and_export_lora(
            ds_dir, out_dir, ct2_dir,
            max_train_samples=args.max_train,
            max_val_samples=args.max_val,
            epochs=args.epochs,
            batch_size=args.batch_size,
        )
    evaluate_lora_model(ct2_dir)
