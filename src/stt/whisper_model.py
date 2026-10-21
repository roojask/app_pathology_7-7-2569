import whisper
import threading
import subprocess
import os
import wave
import numpy as np
from pathlib import Path
from configs.config import Config

# Global lock to prevent Whisper from running concurrently if app scales (optional but safe)
whisper_lock = threading.Lock()

model = None


def get_model():
    global model
    if model is None:
        print("[Loading] Loading Whisper model lazily...")
        model = whisper.load_model(Config.WHISPER_MODEL)
        print("[Success] Whisper model loaded!")
    return model


def estimate_snr_db(audio_path: Path, frame_ms: int = 25) -> float:
    """
    Blind Frame-Energy Percentile SNR Estimator:
      SNR_hat = P85(E_dB) - P15(E_dB)
    where E_dB are short-time 25ms frame RMS energies in dB.
    Supports WAV directly or any format (.webm, .mp3, .m4a) via temporary 16kHz mono WAV decode.
    """
    audio_path = Path(audio_path)
    tmp_wav = None
    try:
        target_wav = audio_path
        if audio_path.suffix.lower() != ".wav":
            tmp_wav = audio_path.parent / f"snr_probe_{audio_path.stem}.wav"
            cmd = [
                "ffmpeg", "-y", "-i", str(audio_path),
                "-ar", "16000", "-ac", "1", str(tmp_wav)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if tmp_wav.exists() and tmp_wav.stat().st_size > 44:
                target_wav = tmp_wav
            else:
                return 25.0

        with wave.open(str(target_wav), "rb") as wf:
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
            n_ch = wf.getnchannels()
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_ch > 1:
            samples = samples[::n_ch]
        frame_len = max(1, int(sr * frame_ms / 1000))
        n_chunks = len(samples) // frame_len
        if n_chunks < 4:
            return 25.0
        frames = samples[: n_chunks * frame_len].reshape(n_chunks, frame_len)
        rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
        db = 20.0 * np.log10(rms + 1e-12)
        valid = db[db > -65.0]
        if len(valid) < 4:
            valid = db
        p85 = float(np.percentile(valid, 85))
        p15 = float(np.percentile(valid, 15))
        return round(float(p85 - p15), 2)
    except Exception:
        return 25.0
    finally:
        if tmp_wav is not None and tmp_wav.exists():
            try:
                tmp_wav.unlink()
            except Exception:
                pass


def denoise_audio_adaptive(input_path):
    """
    Blind SNR-Gated Adaptive Denoising (`D8_snr_gated`):
      - Estimates blind SNR_hat = P85 - P15 on input_path.
      - If SNR_hat >= tau* (13.55 dB, Clean audio): bypasses FFT spectral subtraction (`afftdn`)
        to preserve consonant formants and hyphen/number transitions.
      - If SNR_hat < tau* (Noisy fume-hood audio): applies calibrated `afftdn=nr=6:nf=-30:nt=w`
        followed by silence trimming.
    Returns (processed_path: Path, snr_db: float, denoised_applied: bool).
    """
    input_path = Path(input_path)
    tau_db = float(getattr(Config, "SNR_GATE_THRESHOLD_DB", 13.55))
    nr_db = int(getattr(Config, "AFFTDN_NR_DB", 6))
    snr_db = estimate_snr_db(input_path)
    apply_afftdn = snr_db < tau_db

    if not apply_afftdn:
        # Clean audio: bypass spectral subtraction to avoid consonant over-suppression
        return input_path, snr_db, False

    denoised_path = input_path.parent / f"denoised_{input_path.stem}.wav"
    try:
        af_chain = (
            f"afftdn=nr={nr_db}:nf=-30:nt=w,"
            "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-af", af_chain,
            "-ar", "16000", "-ac", "1",
            str(denoised_path),
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if res.returncode == 0 and denoised_path.exists() and denoised_path.stat().st_size > 44:
            return denoised_path, snr_db, True
        return input_path, snr_db, False
    except Exception:
        return input_path, snr_db, False


def denoise_audio(input_path):
    """Backward-compatible wrapper returning processed_path."""
    processed_path, _, _ = denoise_audio_adaptive(input_path)
    return processed_path


def transcribe_audio_with_metadata(audio_path):
    """
    Full PathoWhisper S3 Pipeline:
      1. Blind SNR-Gated Adaptive Denoising (`D8_snr_gated`, tau*=13.55 dB, afftdn nr=6 dB)
      2. Fine-tuned Whisper Small LoRA CTranslate2 INT8 Engine (`models/pathowhisper_lora_int8`)
      3. Phonetic-Contrastive Prompt (`P4`) + Acoustic Confidence Scoring (`avg_logprob`, `min_word_prob`)
    """
    try:
        processed_audio_path, snr_db, denoised_applied = denoise_audio_adaptive(audio_path)
        use_faster = getattr(Config, "USE_FASTER_WHISPER_ENGINE", True)
        avg_logprob = -0.15
        min_word_prob = 0.90
        model_target = "openai/whisper-small"

        if use_faster:
            print(
                f"[STT Pipeline] Blind SNR={snr_db:.2f} dB | Denoise={'ON (nr=6dB)' if denoised_applied else 'BYPASS (Clean)'} "
                "| Processing via PathoWhisper CTranslate2 INT8 Engine..."
            )
            from src.stt.faster_whisper_engine import transcribe_faster_whisper_with_confidence
            fw_res = transcribe_faster_whisper_with_confidence(
                str(processed_audio_path),
                initial_prompt=Config.PATHOLOGY_PROMPT,
                language="en",
            )
            transcription_text = fw_res["text"]
            avg_logprob = fw_res["avg_logprob"]
            min_word_prob = fw_res["min_word_prob"]
            model_target = fw_res.get("model_target", "faster_whisper")
        else:
            print("[STT Pipeline] Processing via Standard OpenAI PyTorch Whisper Small Engine (English Only)...")
            with whisper_lock:
                current_model = get_model()
                result = current_model.transcribe(
                    str(processed_audio_path),
                    language="en",
                    initial_prompt=Config.PATHOLOGY_PROMPT,
                )
                transcription_text = result["text"]

        if str(processed_audio_path) != str(audio_path) and os.path.exists(processed_audio_path):
            try:
                os.remove(processed_audio_path)
            except Exception as ex:
                print(f"[Cleanup Error] Failed to delete temporary denoised audio: {ex}")

        return {
            "text": transcription_text,
            "snr_db": snr_db,
            "denoised_applied": denoised_applied,
            "avg_logprob": avg_logprob,
            "min_word_prob": min_word_prob,
            "model_target": model_target,
        }
    except Exception as e:
        print(f"Error during STT transcription: {e}")
        return {
            "text": "Error during transcription",
            "snr_db": 0.0,
            "denoised_applied": False,
            "avg_logprob": -1.0,
            "min_word_prob": 0.0,
            "model_target": "error",
        }


def transcribe_audio(audio_path):
    """
    Backward-compatible wrapper returning only the transcribed text string.
    """
    res = transcribe_audio_with_metadata(audio_path)
    return res["text"]

