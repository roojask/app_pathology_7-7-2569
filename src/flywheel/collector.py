import os
import sys
import json
import time
import re
import wave
import subprocess
import threading
from pathlib import Path
from datetime import datetime

from configs.config import Config
from src.database.models import db, AudioTrainingPair

# Lock for file writing synchronization across background threads
_manifest_lock = threading.Lock()

def standardize_audio_to_16k_wav(src_path: Path, dst_path: Path) -> float:
    """
    Converts any input audio file (WAV, MP3, WEBM, OGG, M4A) to standard
    16kHz Mono 16-bit PCM WAV (the gold-standard format for Whisper ASR training).
    Returns duration in seconds.
    """
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Run FFmpeg conversion
    cmd = [
        "ffmpeg", "-y",
        "-i", str(src_path),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(dst_path)
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if res.returncode != 0 or not dst_path.exists() or dst_path.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg audio standardization failed for {src_path}")

    # Read precise duration using standard wave module
    duration_sec = 0.0
    try:
        with wave.open(str(dst_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration_sec = round(frames / float(rate), 2)
    except Exception:
        # Fallback estimate from file size: 16000 samples/sec * 2 bytes = 32000 bytes/sec
        duration_sec = round(dst_path.stat().st_size / 32000.0, 2)

    return duration_sec

def deidentify_text(text: str) -> str:
    """
    Removes personal identifiable information (PII) such as Patient Names,
    Hospital Numbers (HN), Citizen IDs, and telephone numbers to maintain strict
    HIPAA/PDPA medical privacy compliance.
    """
    if not text:
        return ""
        
    # Mask 13-digit Thai Citizen ID
    text = re.sub(r'\b\d{13}\b', '[ID_MASKED]', text)
    # Mask Hospital Numbers (HN: 123456 or HN123456)
    text = re.sub(r'(?i)\bHN\s*[:#]?\s*\d+\b', '[HN_MASKED]', text)
    # Mask telephone numbers
    text = re.sub(r'\b0\d{1,2}[-\s]?\d{3}[-\s]?\d{4}\b', '[PHONE_MASKED]', text)
    # Mask common Thai name prefixes
    text = re.sub(r'(?i)(?:นาย|นาง|นางสาว|เด็กชาย|เด็กหญิง|ผู้ป่วย)\s+[ก-๙a-zA-Z]+(?:\s+[ก-๙a-zA-Z]+)?', '[PATIENT_NAME_MASKED]', text)
    
    return text.strip()

def construct_verified_narrative(form_data: dict) -> str:
    """
    Constructs a comprehensive, natural clinical narrative from the 15-section
    fields verified and approved by the doctor.
    """
    if not isinstance(form_data, dict):
        return ""
        
    parts = []
    
    s_no = form_data.get("s0_surgical_no", "").strip()
    if s_no:
        parts.append(f"Surgical number {s_no}.")
        
    side = form_data.get("s1_side", "").strip()
    proc = form_data.get("s2_proc", "").strip()
    proc_other = form_data.get("s2_other_text", "").strip()
    if proc == "other" and proc_other:
        proc_str = proc_other
    elif proc == "modified":
        proc_str = "modified radical mastectomy"
    elif proc == "simple":
        proc_str = "simple mastectomy"
    else:
        proc_str = proc or "specimen"

    # 3D dimensions
    s3_dims = form_data.get("s3_dims", [])
    if isinstance(s3_dims, list) and len(s3_dims) >= 3 and any(s3_dims):
        d_str = " x ".join([str(d) for d in s3_dims if str(d).strip()])
        parts.append(f"Received in formalin is a {side} {proc_str} measuring {d_str} cm.")
    elif side or proc_str:
        parts.append(f"Received in formalin is a {side} {proc_str}.")

    # Skin ellipse
    s4_dims = form_data.get("s4_dims", [])
    if isinstance(s4_dims, list) and len(s4_dims) >= 2 and any(s4_dims):
        sd_str = " x ".join([str(d) for d in s4_dims if str(d).strip()])
        parts.append(f"The skin ellipse measures {sd_str} cm and appears normal.")

    # Infiltrative or well-circumscribed mass
    if form_data.get("s10_infiltrative"):
        m_dims = form_data.get("s10_inf_dims", [])
        md_str = " x ".join([str(d) for d in m_dims if str(d).strip()]) if isinstance(m_dims, list) else ""
        quad_vals = form_data.get("s10_5_quadrant_vals", [])
        quad_str = ", ".join(quad_vals) if isinstance(quad_vals, list) else str(quad_vals)
        loc_str = f"at the {quad_str} quadrant" if quad_str else ""
        if md_str:
            parts.append(f"There is an infiltrative firm yellow white mass measuring {md_str} cm {loc_str}.".strip())
        else:
            parts.append(f"There is an infiltrative mass {loc_str}.".strip())

    # Deep margin
    deep_m = form_data.get("s11_deep", "").strip()
    if deep_m:
        parts.append(f"Deep margin is {deep_m} cm.")

    # Lymph nodes
    num_nodes = form_data.get("s14_num", "").strip()
    n_min = form_data.get("s14_min", "").strip()
    n_max = form_data.get("s14_max", "").strip()
    if num_nodes:
        if n_min and n_max:
            parts.append(f"{num_nodes} lymph nodes ranging from {n_min} to {n_max} cm are identified.")
        else:
            parts.append(f"{num_nodes} lymph nodes are identified.")

    narrative = " ".join(parts).strip()
    return deidentify_text(narrative)

def calculate_wer_simple(reference: str, hypothesis: str) -> float:
    """Calculates Word Error Rate using dynamic programming Levenshtein distance."""
    if not reference:
        return 0.0 if not hypothesis else 100.0
    if not hypothesis:
        return 100.0
        
    ref_words = [w.strip('.,;:') for w in reference.lower().split() if w.strip('.,;:')]
    hyp_words = [w.strip('.,;:') for w in hypothesis.lower().split() if w.strip('.,;:')]
    if not ref_words:
        return 0.0
        
    m, n = len(ref_words), len(hyp_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1): dp[i][0] = i
    for j in range(n + 1): dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
                
    return round((dp[m][n] / max(m, 1)) * 100.0, 2)

def _background_collector_worker(app, history_id, surgical_no, audio_clips, form_data, initial_stt_text):
    """Worker executed in separate daemon thread to avoid blocking web responses."""
    with app.app_context():
        try:
            if not Config.ENABLE_DATA_FLYWHEEL:
                return

            verified_text = construct_verified_narrative(form_data)
            if not verified_text or len(verified_text) < 15:
                # If generated narrative is too short, use fallback raw_text if present
                verified_text = deidentify_text(form_data.get("transcription_text") or form_data.get("raw_text") or "")
                
            if not verified_text:
                return

            manifest_path = Config.CLINICAL_DATASET_DIR / "dataset_manifest.jsonl"
            
            for clip_idx, clip in enumerate(audio_clips, 1):
                raw_filename = clip.get("filename")
                if not raw_filename:
                    continue

                # Local uploaded file
                src_path = Config.UPLOAD_DIR / raw_filename
                if not src_path.exists():
                    continue

                # Generate standardized 16kHz WAV filename
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_sno = re.sub(r'[^a-zA-Z0-9_-]', '_', surgical_no or "case")
                wav_filename = f"flywheel_{safe_sno}_{timestamp_str}_clip{clip_idx}.wav"
                dst_path = Config.CLINICAL_AUDIO_DIR / wav_filename

                try:
                    duration = standardize_audio_to_16k_wav(src_path, dst_path)
                except Exception as ex:
                    print(f"[Flywheel Error] Audio standardization failed: {ex}")
                    continue

                # Filter out empty or negligible clips (< 1.0 second)
                if duration < 1.0:
                    try: dst_path.unlink()
                    except: pass
                    continue

                # Compute initial error rate if initial_stt_text was provided
                wer = None
                if initial_stt_text:
                    wer = calculate_wer_simple(verified_text, initial_stt_text)

                # Validate foreign key to prevent FK constraint errors
                valid_hist_id = None
                if history_id:
                    try:
                        from src.database.models import FormHistory
                        if FormHistory.query.get(history_id) is not None:
                            valid_hist_id = history_id
                    except Exception:
                        valid_hist_id = None

                # Save record to Database
                pair_record = AudioTrainingPair(
                    history_id=valid_hist_id,
                    surgical_number=surgical_no,
                    audio_filename=wav_filename,
                    standardized_wav_path=str(dst_path),
                    duration_seconds=duration,
                    initial_stt_text=initial_stt_text or "",

                    verified_ground_truth=verified_text,
                    initial_wer=wer,
                    organ_type="Breast",
                    is_qualified=True
                )
                db.session.add(pair_record)
                db.session.commit()

                # Append to JSONL Manifest
                manifest_entry = {
                    "id": pair_record.id,
                    "history_id": history_id,
                    "surgical_number": surgical_no,
                    "audio_filepath": str(dst_path),
                    "audio_filename": wav_filename,
                    "duration": duration,
                    "text": verified_text,
                    "initial_stt": initial_stt_text or "",
                    "initial_wer": wer,
                    "created_at": datetime.now().isoformat()
                }

                with _manifest_lock:
                    with open(manifest_path, "a", encoding="utf-8") as mf:
                        mf.write(json.dumps(manifest_entry, ensure_ascii=False) + "\n")

                print(f"🌟 [Data Flywheel] Collected Pair #{pair_record.id} ({duration}s) -> {wav_filename}")

            # Update cache statistics
            update_flywheel_stats_cache()

        except Exception as e:
            print(f"[Flywheel Warning] Background capture encountered error: {e}")

def capture_audio_training_pair(app, history_id, surgical_number, audio_clips, form_data, initial_stt_text=None):
    """
    Spawns non-blocking background thread to capture audio training pair.
    """
    if not Config.ENABLE_DATA_FLYWHEEL or not audio_clips:
        return
        
    thread = threading.Thread(
        target=_background_collector_worker,
        args=(app, history_id, surgical_number, audio_clips, form_data, initial_stt_text),
        daemon=True
    )
    thread.start()

def get_flywheel_stats() -> dict:
    """Returns real-time statistics of the collected clinical dataset."""
    stats_cache = Config.CLINICAL_DATASET_DIR / "flywheel_stats.json"
    if stats_cache.exists():
        try:
            with open(stats_cache, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return update_flywheel_stats_cache()

def update_flywheel_stats_cache() -> dict:
    """Recalculates and caches clinical dataset statistics."""
    manifest_path = Config.CLINICAL_DATASET_DIR / "dataset_manifest.jsonl"
    total_clips = 0
    total_duration = 0.0
    wers = []

    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        total_clips += 1
                        total_duration += item.get("duration", 0.0)
                        if item.get("initial_wer") is not None:
                            wers.append(item["initial_wer"])
        except Exception:
            pass

    avg_wer = round(sum(wers) / len(wers), 2) if wers else 0.0
    stats = {
        "total_clips": total_clips,
        "total_seconds": round(total_duration, 1),
        "total_hours": round(total_duration / 3600.0, 2),
        "avg_initial_wer": avg_wer,
        "target_for_finetuning": 100,
        "progress_percent": round(min(100.0, (total_clips / 100.0) * 100.0), 1),
        "last_updated": datetime.now().isoformat()
    }

    try:
        stats_cache = Config.CLINICAL_DATASET_DIR / "flywheel_stats.json"
        with open(stats_cache, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return stats
