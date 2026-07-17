import whisper
import threading
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

def transcribe_audio(audio_path):
    """
    Transcribes audio using Whisper with the Medical Prompt from Config.
    Uses a thread lock to prevent simultaneous execution crashes.
    """
    try:
        with whisper_lock:
            current_model = get_model()
            result = current_model.transcribe(
                str(audio_path), 
                language="en", 
                initial_prompt=Config.PATHOLOGY_PROMPT
            )
        return result['text']
    except Exception as e:
        print(f"Error during STT transcription: {e}")
        return "Error during transcription"
