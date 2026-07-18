import whisper
import threading
from configs.config import Config

import subprocess
import os
from pathlib import Path

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
    Applies FFmpeg FFT denoise (afftdn) filter to the audio file
    to remove constant background noise (AC hum, fume hood fan)
    before sending it to Whisper.
    """
    denoised_path = Path(input_path).parent / f"denoised_{Path(input_path).name}"
    try:
        # Run FFmpeg command: afftdn is the built-in FFT denoiser
        cmd = [
            "ffmpeg", "-y", 
            "-i", str(input_path), 
            "-af", "afftdn", 
            str(denoised_path)
        ]
        # Run subprocess silently
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        print(f"[Denoise] Successfully denoised audio file: {denoised_path.name}")
        return denoised_path
    except Exception as e:
        print(f"[Denoise Warning] Failed to denoise audio using FFmpeg: {e}. Falling back to raw audio.")
        return input_path

def transcribe_audio(audio_path):
    """
    Transcribes audio using Whisper with the Medical Prompt from Config.
    Uses a thread lock to prevent simultaneous execution crashes.
    """
    try:
        # Denoise the audio first to remove background noise!
        processed_audio_path = denoise_audio(audio_path)
        
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
