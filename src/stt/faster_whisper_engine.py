import os
import threading
import numpy as np
from pathlib import Path
from faster_whisper import WhisperModel
from configs.config import Config

_faster_whisper_model = None
_loaded_model_target = None
_model_lock = threading.Lock()


def _resolve_best_local_model_dir(model_size="small"):
    import sys
    from configs.config import BASE_DIR
    candidates = [
        BASE_DIR / "models" / "pathowhisper_lora_int8",
        BASE_DIR / "models" / "pathowhisper_lora_200_int8",
        BASE_DIR / "models" / "faster_whisper_small",
    ]
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        candidates.extend([
            meipass / "models" / "pathowhisper_lora_int8",
            meipass / "models" / "faster_whisper_small",
        ])
    for cand in candidates:
        if cand.exists() and (cand / "model.bin").exists():
            return str(cand)
    return model_size


def get_faster_whisper_model(model_size="small", compute_type="int8", device="cpu"):
    """
    Lazy loads Faster-Whisper (CTranslate2 INT8 Engine)
    Prioritizes local fine-tuned LoRA CTranslate2 INT8 directory (`models/pathowhisper_lora_int8`),
    automatically upgrading if the 600-case model becomes available on disk.
    """
    global _faster_whisper_model, _loaded_model_target
    best_target = _resolve_best_local_model_dir(model_size=model_size)
    if _faster_whisper_model is None or _loaded_model_target != best_target:
        with _model_lock:
            best_target = _resolve_best_local_model_dir(model_size=model_size)
            if _faster_whisper_model is None or _loaded_model_target != best_target:
                print(f"[Loading] Loading Faster-Whisper from {best_target} [{compute_type} on {device}]...")
                _faster_whisper_model = WhisperModel(
                    model_size_or_path=best_target,
                    device=device,
                    compute_type=compute_type,
                    cpu_threads=8,
                )
                _loaded_model_target = best_target
                print(f"[Success] Faster-Whisper loaded successfully from {best_target}!")
    return _faster_whisper_model


def transcribe_faster_whisper_with_confidence(audio_path, initial_prompt=None, language="en"):
    """
    Transcribes audio using Faster-Whisper (CTranslate2 INT8) and returns
    both the transcribed string and acoustic confidence metrics (avg_logprob, min_word_prob).
    Uses Duration-Aware Long-Form Decoding (>27.5s) to prevent 30-second window boundary
    backward timestamp seeking on text-only LoRA fine-tuned models.
    """
    if initial_prompt is None:
        initial_prompt = getattr(Config, "PATHOLOGY_PROMPT", "")

    lang = language or getattr(Config, "DEFAULT_LANGUAGE", "en")
    model_engine = get_faster_whisper_model()

    # Check audio duration to select single-window vs multi-window decoding
    dur_sec = 0.0
    try:
        import wave
        with wave.open(str(audio_path), "rb") as wf:
            dur_sec = wf.getnframes() / float(max(1, wf.getframerate()))
    except Exception:
        dur_sec = 0.0

    if dur_sec > 27.5:
        segments, info = model_engine.transcribe(
            str(audio_path),
            beam_size=1,
            best_of=1,
            language=lang,
            initial_prompt=initial_prompt,
            without_timestamps=True,
            condition_on_previous_text=False,
            repetition_penalty=1.15,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400, speech_pad_ms=200),
        )
    else:
        segments, info = model_engine.transcribe(
            str(audio_path),
            beam_size=1,
            best_of=1,
            language=lang,
            initial_prompt=initial_prompt,
            vad_filter=False,
            word_timestamps=True,
        )

    text_segments = []
    logprobs = []
    word_probs = []
    for segment in segments:
        text_segments.append(segment.text)
        if getattr(segment, "avg_logprob", None) is not None:
            logprobs.append(float(segment.avg_logprob))
        if getattr(segment, "words", None):
            for w in segment.words:
                if getattr(w, "probability", None) is not None:
                    word_probs.append(float(w.probability))

    full_text = " ".join(text_segments).strip()
    avg_lp = float(np.mean(logprobs)) if logprobs else -0.15
    min_wp = float(np.min(word_probs)) if word_probs else float(np.exp(avg_lp))
    return {
        "text": full_text,
        "avg_logprob": round(avg_lp, 4),
        "min_word_prob": round(min_wp, 4),
        "model_target": _loaded_model_target,
    }


def transcribe_faster_whisper(audio_path, initial_prompt=None, language="en"):
    """
    Backward-compatible wrapper returning the transcribed string.
    """
    res = transcribe_faster_whisper_with_confidence(
        audio_path=audio_path,
        initial_prompt=initial_prompt,
        language=language,
    )
    return res["text"]

