import whisper
import threading
import subprocess
import os
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

def denoise_audio(input_path):
    """
    Applies FFmpeg FFT denoise (afftdn) and silence trimming (VAD)
    to remove fume hood fan hum and trim silence pauses before sending to Whisper.
    """
    denoised_path = Path(input_path).parent / f"denoised_{Path(input_path).name}"
    try:
        cmd = [
            "ffmpeg", "-y", 
            "-i", str(input_path), 
            "-af", "afftdn,silenceremove=start_periods=1:start_duration=0.1:start_threshold=-40dB:stop_periods=-1:stop_duration=0.6:stop_threshold=-40dB", 
            str(denoised_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if res.returncode == 0 and denoised_path.exists() and denoised_path.stat().st_size > 0:
            return denoised_path
        else:
            return Path(input_path)
    except Exception as e:
        return Path(input_path)

def transcribe_audio(audio_path):
    """
    Transcribes audio strictly using local offline Whisper engine.
    Constrained to English language only with CAP pathology vocabulary prompting.
    """
    try:
        # Denoise the audio first to remove background noise!
        processed_audio_path = denoise_audio(audio_path)
        
        # Check if Faster-Whisper CTranslate2 INT8 Engine is explicitly requested
        use_faster = getattr(Config, "USE_FASTER_WHISPER_ENGINE", True)
        if use_faster:
            print("[STT Pipeline] Processing via local CPU PathoWhisper CTranslate2 INT8 Engine (English Only)...")
            from src.stt.faster_whisper_engine import transcribe_faster_whisper
            transcription_text = transcribe_faster_whisper(str(processed_audio_path), initial_prompt=Config.PATHOLOGY_PROMPT, language="en")
            result = {'text': transcription_text}
        else:
            # Default to Standard OpenAI PyTorch Whisper Small Engine
            print("[STT Pipeline] Processing via Standard OpenAI PyTorch Whisper Small Engine (English Only)...")
            with whisper_lock:
                current_model = get_model()
                result = current_model.transcribe(
                    str(processed_audio_path), 
                    language="en",
                    initial_prompt=Config.PATHOLOGY_PROMPT
                )
            
        # Clean up temporary denoised file
        if processed_audio_path != audio_path and os.path.exists(processed_audio_path):
            try:
                os.remove(processed_audio_path)
            except Exception as ex:
                print(f"[Cleanup Error] Failed to delete temporary denoised audio: {ex}")
                
        return result['text']
    except Exception as e:
        print(f"Error during STT transcription: {e}")
        return "Error during transcription"
