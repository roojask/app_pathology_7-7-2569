import whisper
import threading
import subprocess
import os
import requests
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

def transcribe_via_groq(audio_path, api_key):
    """
    Transcribes audio using Groq Cloud API (Whisper Large V3) via REST request.
    This runs in < 0.5s and consumes 0% local CPU.
    """
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 1000:
        print("[Groq STT] Audio file is missing or empty (<1KB). Skipping Groq API request.")
        return None

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    try:
        with open(audio_path, "rb") as f:
            files = {
                "file": (os.path.basename(audio_path), f, "audio/wav")
            }
            data = {
                "model": Config.GROQ_MODEL,
                "prompt": Config.PATHOLOGY_PROMPT,
                "response_format": "json"
            }
            response = requests.post(url, headers=headers, files=files, data=data, timeout=12)
            if response.status_code != 200:
                print(f"[Groq Error] HTTP {response.status_code}: {response.text}")
                return None
            result = response.json()
            print("[Groq Cloud STT] Successfully transcribed using Whisper Large V3!")
            return result.get("text", "")
    except Exception as e:
        print(f"[Groq Error] Failed to transcribe via Groq: {e}. Falling back to local Whisper.")
        return None


def transcribe_audio(audio_path):
    """
    Transcribes audio using Groq Cloud API (if API key is present)
    with a graceful fallback to local CPU Whisper if offline or key is missing.
    """
    try:
        # Denoise the audio first to remove background noise!
        processed_audio_path = denoise_audio(audio_path)
        
        # Check if GROQ_API_KEY is available
        groq_key = os.environ.get("GROQ_API_KEY") or getattr(Config, "GROQ_API_KEY", None)
        if groq_key and groq_key.strip():
            print("[STT Pipeline] GROQ_API_KEY detected. Processing via Groq Cloud Whisper...")
            transcription = transcribe_via_groq(processed_audio_path, groq_key)
            if transcription:
                # Clean up temporary denoised file
                if processed_audio_path != audio_path and os.path.exists(processed_audio_path):
                    try: os.remove(processed_audio_path)
                    except: pass
                return transcription
        
        # Check if Faster-Whisper CTranslate2 INT8 Engine is explicitly requested
        use_faster = getattr(Config, "USE_FASTER_WHISPER_ENGINE", False)
        if use_faster:
            print("[STT Pipeline] Processing via local CPU PathoWhisper CTranslate2 INT8 Engine (Configured Alternative)...")
            from src.stt.faster_whisper_engine import transcribe_faster_whisper
            transcription_text = transcribe_faster_whisper(str(processed_audio_path), initial_prompt=Config.PATHOLOGY_PROMPT)
            result = {'text': transcription_text}
        else:
            # Default to Standard OpenAI PyTorch Whisper Small Engine
            print("[STT Pipeline] Processing via Standard OpenAI PyTorch Whisper Small Engine (Default)...")
            with whisper_lock:
                current_model = get_model()
                result = current_model.transcribe(
                    str(processed_audio_path), 
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
