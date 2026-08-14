import os
import torch
import whisper
from pathlib import Path
from transformers import WhisperForConditionalGeneration, WhisperProcessor
from peft import PeftModel

BASE_DIR = Path(__file__).parent.parent.parent
MODEL_PATH = BASE_DIR / "models" / "pathowhisper_lora" / "adapter_model"

_lora_model = None
_lora_processor = None

def get_lora_model():
    global _lora_model, _lora_processor
    if _lora_model is None:
        print("[Loading] Loading PathoWhisper-LoRA Fine-Tuned Specialized Weights...")
        base_name = "openai/whisper-small"
        _lora_processor = WhisperProcessor.from_pretrained(base_name, language="english", task="transcribe")
        base_model = WhisperForConditionalGeneration.from_pretrained(base_name)
        
        # Load fine-tuned LoRA weights
        _lora_model = PeftModel.from_pretrained(base_model, str(MODEL_PATH))
        _lora_model.eval()
        print("[Success] PathoWhisper-LoRA Model loaded successfully!")
    return _lora_model, _lora_processor

def transcribe_lora_whisper(audio_path):
    """
    Transcribes audio using PathoWhisper-LoRA Fine-Tuned Model Weights.
    """
    model, processor = get_lora_model()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    
    # Load audio array
    audio_array = whisper.audio.load_audio(str(audio_path))
    input_features = processor(audio_array, sampling_rate=16000, return_tensors="pt").input_features.to(device)
    
    with torch.no_grad():
        predicted_ids = model.generate(input_features, max_new_tokens=256)
        
    transcription = processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
    return transcription.strip()
