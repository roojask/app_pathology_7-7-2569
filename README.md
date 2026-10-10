---
title: PathoWhisper Assistant
emoji: 🎙️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# 🏥 PathoWhisper: AI-Assisted Gross Pathology Speech-to-Text & Clinical Information Extraction

**An end-to-end, privacy-preserving, and fully offline-capable AI system for automated speech transcription and structured reporting in breast gross pathology examination (15 CAP Protocol Sections).**

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20iPadOS-lightgrey)
![Inference Engine](https://img.shields.io/badge/engine-CTranslate2%20INT8-orange)
[![Release](https://img.shields.io/badge/release-v1.0--thesis-blue)](https://github.com/roojask/app_pathology_7-7-2569/releases/tag/v1.0-thesis)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 🎯 Overview
Surgical gross pathology examinations require pathologists to inspect specimens while simultaneously documenting extensive dimensional, anatomical, and margin parameters. Manual transcription or delayed data entry introduces clerical burden and cognitive distraction.

**PathoWhisper** solves this workflow challenge by providing an end-to-end automated speech-to-report pipeline tailored for College of American Pathologists (CAP) cancer protocol reporting for breast specimens:
1. **FFmpeg Acoustic Denoising:** Real-time fast Fourier transform noise filter (`afftdn`) and silence trimmer calibrated for grossing fume hood ambient environments.
2. **PathoWhisper STT Engine:** Quantized `Faster-Whisper Small (INT8)` powered by CTranslate2 with pathology-specific domain prompting (`PATHOLOGY_PROMPT`), running entirely on edge/CPU hardware without requiring an external internet connection.
3. **Clinical Information Extractor v2.1:** Rule- and context-aware natural language extractor with mid-sentence self-correction disambiguation (e.g., handling *"sorry"*, *"wait/weight"*, and distinction between *skin ellipse* dimensions and *margins*).
4. **Dual-Tier Database Architecture:** Multi-user PostgreSQL for centralized hospital infrastructure paired with automatic offline SQLite shadow sync to guarantee zero clinical data loss.
5. **Instant CAP-Compliant Document Generation:** Automatically generates standardized, publication-grade PDF and DOCX reports with graphical checkboxes and dimension anchors.

> [!NOTE]
> **Acoustic Model Scope & LoRA Disclaimer:**  
> The primary pipeline evaluated in the thesis uses off-the-shelf `Faster-Whisper Small (INT8)` with CTranslate2 and domain prompting (`PATHOLOGY_PROMPT`) **without** fine-tuning. The LoRA adapter located under `models/pathowhisper_lora/` represents an exploratory proof-of-concept and was **not** utilized in the formal experimental benchmark or thesis evaluation.

---

## ✨ Key Features
- **100% Offline & Edge Capable:** Fully self-contained local CPU inference — no audio, patient identifiers, or clinical transcripts leave the local workstation.
- **Microphone Fallback Resilience:** Gracefully falls back from browser Web Speech to native high-fidelity audio capture and local CPU transcription in zero-connectivity environments.
- **Self-Correction Disambiguation:** Intelligently detects and updates in-sentence pathologist corrections (e.g., *"specimen 10 x 5 cm sorry 12 x 6 cm"* $\rightarrow$ extracts latest value).
- **Clinical Commission Error Prevention:** Extractor v2.1 requires explicit margin keyword qualification, preventing specimen skin ellipse dimensions from false-filling margin slots.
- **iPad / Tablet Ergonomics:** Responsive touch targets (44px+) and collapsible gesture interfaces designed for sterile laboratory environments.

---

## 🏗️ System Architecture

```text
app_pathology_7-7-2569/
├── configs/             # Configuration, database URIs, SSL and domain prompts
├── src/                 
│   ├── database/        # SQLAlchemy models (User, FormHistory, Revisions)
│   ├── stt/             # Faster-Whisper INT8 engine (LoRA is exploratory proof-of-concept)
│   ├── nlp/             # Extractor v2.1 and Text Normalizer
│   ├── pdf/             # CAP-compliant PyMuPDF report generator
│   ├── export/          # DOCX & FHIR export utilities
│   ├── routes/          # Flask blueprints (Auth, Dictation, Case, Export)
│   └── storage/         # Local and cloud storage providers
├── data/                # Data assets, templates, and runtime directories
│   ├── assets/          # Gross template PDF and DOCX forms
│   ├── uploads/         # Temporary audio files (.gitkeep)
│   └── outputs/         # Generated pathology documents (.gitkeep)
├── benchmarks/          # Comprehensive academic evaluation testbed (1,000 cases)
│   ├── thesis_eval_outputs/  # Verified benchmark metrics, CSVs, and charts
│   └── scripts/         # Evaluation and statistical analysis scripts
├── docs/thesis_latex/   # Full LaTeX thesis manuscript and publication tables (v9)
├── templates/           # Frontend HTML templates (Responsive & iPad-ready)
├── static/              # CSS styles, FontAwesome assets, and audio scripts
├── tests/               # Unit, integration, and full web validation suites
├── app.py               # Application factory
├── run_server.py        # Development HTTPS server
├── run_production.py    # Multi-threaded Waitress WSGI production server
├── gui_app.py           # Native desktop GUI wrapper
├── LICENSE              # MIT License
└── requirements.txt     # Locked production dependencies
```

---

## 📊 Research Benchmarks & Performance (N = 1,000 Cases)

Evaluated against the baseline (Whisper Small FP32) on a 1,000-case synthetic-speech dataset (15,000 field slots, 10 scenarios). All numbers are reproducible with the scripts in `benchmarks/scripts/` and `scripts/` and match the thesis submitted with release v1.0-thesis.

| Metric | Baseline (Whisper Small FP32) | PathoWhisper (INT8 + afftdn + Prompt) | Difference | Test |
| :--- | :---: | :---: | :---: | :---: |
| **WER, Criterion A** | 36.27% | **29.05%** | −7.21 points (95% CI 6.26–8.14) | Wilcoxon, one-sided, $p = 1.75 \times 10^{-90}$ |
| **WER, Criterion B (dimension formatting normalised)** | 7.25% | **2.78%** | −4.47 points | Wilcoxon, one-sided, $p = 1.02 \times 10^{-110}$ |
| **Concept Error Rate (ConER)** | 6.04% | **1.88%** | −4.16 points | – |
| **Macro-F1 (11 fields with positive reference values)** | 97.79% | **98.61%** | +0.82 points | – |
| **Slot-level agreement (15,000 slots)** | 98.05% (14,708) | **98.93% (14,839)** | +0.88 points | – |
| **Case critical error rate ($\mathrm{CER}_{\mathrm{case}}$, 6 critical fields)** | 18.80% | **11.10%** | −7.70 points (95% CI 5.0–10.5) | McNemar exact, $p = 9.16 \times 10^{-8}$ |
| **Case exactness** | 81.20% | **88.90%** | +7.70 points | – |
| **Mean latency per case** | 20.04 s | **11.50 s** | 1.74× faster | Wilcoxon, one-sided, $p = 9.55 \times 10^{-163}$ |

> **Caveats:** The test audio is synthetic (two TTS voices). The extractor was refined after inspecting errors on this same test set, so extraction figures are upper bounds. PathoWhisper fills in more wrong values than the baseline (77 vs 66 slots), and flags cover only 30.6% of cases with a critical-field error. See the thesis (Chapters 4–5) for details.

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+** (Python 3.11 / 3.12 / 3.13 supported)
- **FFmpeg:** Required for audio filtering and format transcoding. Ensure `ffmpeg` is accessible in System PATH or bundled in `bin/`.

### 2. Installation
```bash
git clone https://github.com/roojask/app_pathology_7-7-2569.git
cd app_pathology_7-7-2569

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate       # Windows PowerShell / CMD
# source .venv/bin/activate  # Linux / macOS

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and configure settings as needed:
```bash
copy .env.example .env
```
*(By default, SQLite `pathology.db` will be initialized automatically if no PostgreSQL `DATABASE_URL` is configured).*

### 4. Running the Application
- **Option A: Production WSGI Server (Recommended)**
  ```bash
  python run_production.py
  ```
- **Option B: Development HTTPS Server (for iPad / LAN testing)**
  ```bash
  python run_server.py
  ```
- **Option C: Standalone Desktop Application**
  ```bash
  python gui_app.py
  ```
- **Option D: Docker Container Deployment**
  ```bash
  docker compose up -d --build
  ```

---

## 🧪 Running Validation & Unit Tests

Run the full automated test suites to verify system integrity:
```bash
# 1. NLP Normalizer & Self-Correction Rules (16/16 Unit Tests)
python tests/run_unit_tests.py

# 2. Context-Aware Extractor & Margin Disambiguation (7/7 Context Tests)
python test_extractor_context.py

# 3. End-to-End Web & Offline Fallback Functional Tests (9/9 Modules)
python tests/test_web_full.py
```

---

## 📄 Academic Citation & Thesis Reference
This repository contains the official codebase and experimental evaluation for the Bachelor of Science in Artificial Intelligence thesis:
* **Title (TH):** การพัฒนาระบบแปลงเสียงเป็นข้อความโดยใช้ปัญญาประดิษฐ์เพื่อบันทึกข้อมูลอัตโนมัติในงานพยาธิวิทยา
* **Title (EN):** Development of an AI-Based Speech-to-Text System for Automatic Data Recording in Pathology
* **Institution:** College of Computing (วิทยาลัยการคอมพิวเตอร์), Khon Kaen University
* **Clinical Collaboration:** Department of Pathology, Faculty of Medicine, Khon Kaen University
* **Authors:** Thaninrat Lohasan (ธนินท์รัฐ โลหะสาร), Chetsada Klangthin (เจษฎา กลางถิ่น)
* **Advisors:** Asst. Prof. Isoon Kanjanasurat, Ph.D. & Asst. Prof. Chaiwat Apiwatnasiri, M.D.

---

## 📜 License
Distributed under the MIT License. See [LICENSE](LICENSE) for more information.