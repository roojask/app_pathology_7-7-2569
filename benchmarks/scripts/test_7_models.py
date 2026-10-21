import sys
import os
import re
import json
import time
from pathlib import Path
import numpy as np
import librosa
import jiwer
import whisper
from faster_whisper import WhisperModel
from transformers import pipeline
from vosk import Model as VoskModel, KaldiRecognizer

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

from configs.config import Config
from src.stt.whisper_model import denoise_audio

def itn_spoken_text(text):
    if not text: return ""
    t = str(text).lower()
    
    # Common substitutions for Vosk / Wav2vec phonetic terms
    replacements = [
        (r'\bpoint\b|\bdot\b', '.'),
        (r'\bdash\b', '-'),
        (r'\bcentimeters?\b|\bsentimeters?\b|\bsentimenter\b', 'cm'),
        (r'\bmillimeters?\b', 'mm'),
        (r'\bzero\b', '0'),
        (r'\bone\b', '1'),
        (r'\btwo\b|\bto\b(?=\s*\d|\s*\.)', '2'),
        (r'\bthree\b', '3'),
        (r'\bfour\b|\bfor\b(?=\s*\d|\s*\.)', '4'),
        (r'\bfive\b', '5'),
        (r'\bsix\b', '6'),
        (r'\bseven\b', '7'),
        (r'\beight\b', '8'),
        (r'\bnine\b', '9'),
        (r'\bten\b', '10'),
        (r'\beleven\b', '11'),
        (r'\btwelve\b', '12'),
        (r'\bthirteen\b', '13'),
        (r'\bfourteen\b', '14'),
        (r'\bfifteen\b', '15'),
        (r'\bsixteen\b', '16'),
        (r'\bseventeen\b', '17'),
        (r'\beighteen\b', '18'),
        (r'\bnineteen\b', '19'),
        (r'\btwenty\s*one\b', '21'),
        (r'\btwenty\s*two\b', '22'),
        (r'\btwenty\s*three\b', '23'),
        (r'\btwenty\s*four\b', '24'),
        (r'\btwenty\s*five\b', '25'),
        (r'\btwenty\s*six\b', '26'),
        (r'\btwenty\s*seven\b', '27'),
        (r'\btwenty\s*eight\b', '28'),
        (r'\btwenty\s*nine\b', '29'),
        (r'\btwenty\b', '20'),
        (r'\bthirty\b', '30'),
        (r'\bforty\b', '40'),
        (r'\bfifty\b', '50'),
        (r'\bsixty\b', '60'),
        (r'\bseventy\b', '70'),
        (r'\beighty\b', '80'),
        (r'\bninety\b', '90'),
        (r'\bone\s*thousand\b', '1000'),
    ]
    for pattern, repl in replacements:
        t = re.sub(pattern, repl, t)
    
    # Clean up spaces around dots between digits
    t = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', t)
    return t

def norm_a(t):
    if not t: return ""
    t = str(t).lower()
    t = re.sub(r'[.,;:!?\-]', ' ', t)
    return " ".join(t.split())

def norm_b(t):
    if not t: return ""
    t = itn_spoken_text(t)
    for _ in range(2):
        t = re.sub(r"(\d)\s*(?:x|by)\s*(?=\d)", r"\1 x ", t)
    t = re.sub(r"(\d)(cm|mm|g|kg)\b", r"\1 \2", t)
    t = re.sub(r"[.,;:!?\-]", " ", t)
    return " ".join(t.split())

print("Testing 1 case end-to-end on 7 models...")
audio_path = BASE_DIR / "data" / "dataset_1000" / "audio" / "case_0811.mp3"
with open(BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000.json", "r", encoding="utf-8") as f:
    gt_data = json.load(f)
ref_text = gt_data["case_0811"]["raw_text"]

print("[1] Loading Vosk...")
m_vosk = VoskModel(str(BASE_DIR / "bin" / "vosk-model-small-en-us-0.15"))
print("[2] Loading Wav2Vec2...")
w_pipe = pipeline("automatic-speech-recognition", model="facebook/wav2vec2-base-960h")
print("[3] Loading Whisper Tiny...")
m_tiny = whisper.load_model("tiny")
print("[4] Loading Whisper Base...")
m_base = whisper.load_model("base")
print("[5] Loading Whisper Small...")
m_small = whisper.load_model("small")
print("[6,7] Loading CTranslate2 Small...")
m_ct2 = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=8)

print("All loaded! Transcribing case_0811...")

# 1. Vosk
t0 = time.time()
audio_data, sr = librosa.load(str(audio_path), sr=16000)
int16_samples = (audio_data * 32767).astype(np.int16)
rec = KaldiRecognizer(m_vosk, 16000)
rec.AcceptWaveform(int16_samples.tobytes())
v_res = json.loads(rec.FinalResult()).get("text", "")
lat_v = round(time.time() - t0, 2)
wb_v = round(jiwer.wer(norm_b(ref_text), norm_b(v_res)) * 100, 2)
print(f"Vosk: Lat={lat_v}s | WER-B={wb_v}% | Text={v_res[:60]}...")

# 2. Wav2Vec2
t0 = time.time()
w_res = w_pipe(str(audio_path))
w_text = w_res.get("text", "") if isinstance(w_res, dict) else str(w_res)
lat_w = round(time.time() - t0, 2)
wb_w = round(jiwer.wer(norm_b(ref_text), norm_b(w_text)) * 100, 2)
print(f"Wav2Vec2: Lat={lat_w}s | WER-B={wb_w}% | Text={w_text[:60]}...")

# 3. Whisper Tiny
t0 = time.time()
res_tiny = m_tiny.transcribe(str(audio_path), language="en", beam_size=5, fp16=False)
lat_tiny = round(time.time() - t0, 2)
wb_tiny = round(jiwer.wer(norm_b(ref_text), norm_b(res_tiny['text'])) * 100, 2)
print(f"Whisper Tiny: Lat={lat_tiny}s | WER-B={wb_tiny}%")

# 4. Whisper Base
t0 = time.time()
res_base = m_base.transcribe(str(audio_path), language="en", beam_size=5, fp16=False)
lat_base = round(time.time() - t0, 2)
wb_base = round(jiwer.wer(norm_b(ref_text), norm_b(res_base['text'])) * 100, 2)
print(f"Whisper Base: Lat={lat_base}s | WER-B={wb_base}%")

# 5. Whisper Small Baseline
t0 = time.time()
res_small = m_small.transcribe(str(audio_path), language="en", beam_size=5, fp16=False)
lat_small = round(time.time() - t0, 2)
wb_small = round(jiwer.wer(norm_b(ref_text), norm_b(res_small['text'])) * 100, 2)
print(f"Whisper Small: Lat={lat_small}s | WER-B={wb_small}%")

# 6. Faster-Whisper Small Vanilla
t0 = time.time()
segs, _ = m_ct2.transcribe(str(audio_path), language="en", beam_size=5)
fw_text = " ".join([s.text for s in segs])
lat_fw = round(time.time() - t0, 2)
wb_fw = round(jiwer.wer(norm_b(ref_text), norm_b(fw_text)) * 100, 2)
print(f"Faster-Whisper Small: Lat={lat_fw}s | WER-B={wb_fw}%")

# 7. PathoWhisper Small
t0 = time.time()
denoised = denoise_audio(audio_path)
t_denoise = time.time() - t0
t0 = time.time()
segs, _ = m_ct2.transcribe(str(denoised), language="en", initial_prompt=Config.PATHOLOGY_PROMPT, beam_size=1)
pw_text = " ".join([s.text for s in segs])
lat_pw = round(time.time() - t0 + t_denoise, 2)
wb_pw = round(jiwer.wer(norm_b(ref_text), norm_b(pw_text)) * 100, 2)
print(f"PathoWhisper Small: Lat={lat_pw}s | WER-B={wb_pw}%")

if os.path.exists(denoised): os.remove(denoised)
print("SUCCESS: ALL 7 MODELS WORKED PERFECTLY!")
