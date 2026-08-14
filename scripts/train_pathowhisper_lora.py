import os
import sys
import json
import time
import torch
import whisper
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DATASET_DIR = BASE_DIR / "data" / "dataset_1000"
GT_JSON_PATH = DATASET_DIR / "ground_truth_1000.json"
AUDIO_DIR = DATASET_DIR / "audio"
OUTPUT_MODEL_DIR = BASE_DIR / "models" / "pathowhisper_lora"

from transformers import WhisperForConditionalGeneration, WhisperProcessor
from peft import LoraConfig, get_peft_model

def load_audio_as_array(audio_path):
    """Load MP3 audio file as 16kHz mono float32 numpy array using whisper.audio"""
    return whisper.audio.load_audio(audio_path)

def train_pathowhisper_lora(num_samples=25, epochs=2, batch_size=2):
    print("==================================================")
    print("🚀 [LORA FINE-TUNING] Fast Training PathoWhisper Specialized Model")
    print("==================================================")
    
    OUTPUT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    print("[1/5] Loading Ground Truth Data...")
    with open(GT_JSON_PATH, "r", encoding="utf-8") as f:
        gt_data = json.load(f)
        
    items = list(gt_data.items())[:num_samples]
    print(f"Loaded {len(items)} training pathology cases.")

    print("[2/5] Initializing Base Whisper Small & Processor...")
    model_name = "openai/whisper-small"
    processor = WhisperProcessor.from_pretrained(model_name, language="english", task="transcribe")
    base_model = WhisperForConditionalGeneration.from_pretrained(model_name)

    base_model.config.forced_decoder_ids = None
    base_model.config.suppress_tokens = []

    print("[3/5] Configuring LoRA Adapter Matrices...")
    lora_config = LoraConfig(
        r=8,
        lora_alpha=32,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        bias="none"
    )
    
    model = get_peft_model(base_model, lora_config)
    model.print_trainable_parameters()

    print("[4/5] Pre-processing Audio Features & Token Labels...")
    features_list = []
    labels_list = []
    
    for idx, (case_id, data) in enumerate(items, 1):
        audio_path = AUDIO_DIR / f"{case_id}.mp3"
        raw_text = data.get("raw_text", "")
        
        try:
            audio_array = load_audio_as_array(str(audio_path))
            input_feat = processor(audio_array, sampling_rate=16000, return_tensors="pt").input_features[0]
            label_ids = processor.tokenizer(raw_text).input_ids
            
            features_list.append(input_feat)
            labels_list.append(label_ids)
            print(f"  • Feature Extracted [{idx}/{len(items)}]: {case_id}")
        except Exception as err:
            print(f"  [Warning] Skipping audio {case_id}: {err}")

    print("[5/5] Executing LoRA Fine-Tuning Optimization Loop...")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.train()
    
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    
    t0 = time.time()
    total_batches = (len(features_list) + batch_size - 1) // batch_size
    
    for epoch in range(epochs):
        epoch_loss = 0.0
        for b_idx, i in enumerate(range(0, len(features_list), batch_size), 1):
            batch_feats = features_list[i:i+batch_size]
            batch_labs = labels_list[i:i+batch_size]
            
            # Pad batch features
            padded_feats = processor.feature_extractor.pad(
                [{"input_features": f} for f in batch_feats], 
                return_tensors="pt"
            ).input_features.to(device)
            
            # Pad batch labels
            padded_labs = processor.tokenizer.pad(
                [{"input_ids": l} for l in batch_labs], 
                return_tensors="pt"
            ).input_ids.to(device)
            
            # Replace padding with -100 for loss calculation
            padded_labs = padded_labs.masked_fill(padded_labs == processor.tokenizer.pad_token_id, -100)

            optimizer.zero_grad()
            outputs = model(input_features=padded_feats, labels=padded_labs)
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            
            epoch_loss += loss.item()
            print(f"  Epoch [{epoch+1}/{epochs}] Step [{b_idx}/{total_batches}] Loss: {loss.item():.4f}")

        avg_loss = epoch_loss / total_batches
        print(f"  ==> Epoch [{epoch+1}/{epochs}] Completed - Avg Loss: {avg_loss:.4f}")

    elapsed = time.time() - t0
    print(f"[Success] LoRA Fine-Tuning Completed in {elapsed:.2f} seconds!")

    # Save fine-tuned LoRA model weights
    save_path = OUTPUT_MODEL_DIR / "adapter_model"
    model.save_pretrained(str(save_path))
    processor.save_pretrained(str(save_path))
    print(f"🎉 Saved PathoWhisper-LoRA Model Weights to: {save_path}")

if __name__ == "__main__":
    train_pathowhisper_lora()
