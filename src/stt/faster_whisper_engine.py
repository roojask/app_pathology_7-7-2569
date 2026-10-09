import os
import threading
from pathlib import Path
from faster_whisper import WhisperModel
from configs.config import Config

_faster_whisper_model = None
_model_lock = threading.Lock()

def get_faster_whisper_model(model_size="small", compute_type="int8", device="cpu"):
    """
    Lazy loads Faster-Whisper (CTranslate2 INT8 Engine)
    for 4x-6x CPU inference speedup and lower memory usage.
    Prioritizes local offline model directory if available.
    """
    global _faster_whisper_model
    if _faster_whisper_model is None:
        with _model_lock:
            if _faster_whisper_model is None:
                import sys
                from configs.config import BASE_DIR
                local_model_dir = BASE_DIR / "models" / "faster_whisper_small"
                if not local_model_dir.exists() and getattr(sys, 'frozen', False):
                    local_model_dir = Path(getattr(sys, '_MEIPASS', '')) / "models" / "faster_whisper_small"

                model_target = str(local_model_dir) if (local_model_dir.exists() and (local_model_dir / "model.bin").exists()) else model_size
                print(f"[Loading] Loading Faster-Whisper from {model_target} [{compute_type} on {device}]...")
                _faster_whisper_model = WhisperModel(
                    model_size_or_path=model_target,
                    device=device,
                    compute_type=compute_type,
                    cpu_threads=8
                )
                print(f"[Success] Faster-Whisper loaded successfully from {model_target}!")
    return _faster_whisper_model

def transcribe_faster_whisper(audio_path, initial_prompt=None, language="en"):
    """
    Transcribes audio using Faster-Whisper (CTranslate2 INT8)
    Returns transcribed string. Strictly constrained to English.
    """
    if initial_prompt is None:
        initial_prompt = getattr(Config, "PATHOLOGY_PROMPT", "")

    lang = language or getattr(Config, "DEFAULT_LANGUAGE", "en")
    model_engine = get_faster_whisper_model()
    
    # Transcribe with domain prompt and greedy search (beam_size=1) for maximum CPU speedup
    segments, info = model_engine.transcribe(
        str(audio_path),
        beam_size=1,
        best_of=1,
        language=lang,
        initial_prompt=initial_prompt,
        vad_filter=False
    )
    
    text_segments = [segment.text for segment in segments]
    full_text = " ".join(text_segments).strip()
    return full_text
