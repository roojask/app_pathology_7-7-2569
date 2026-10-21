---
title: PathoWhisper Assistant
emoji: 🎙️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# 🏥 PathoWhisper: Edge-Native Offline Speech Recognition & Structured Information Extraction for Breast Gross Pathology

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20iPadOS-lightgrey)](#)
[![Inference Engine](https://img.shields.io/badge/engine-CTranslate2%20INT8%20(CPU)-orange)](https://github.com/OpenNMT/CTranslate2)
[![Model Adaptation](https://img.shields.io/badge/adaptation-PEFT%20LoRA%20(r%3D8%2C%20%CE%B1%3D32)-purple)](https://github.com/huggingface/peft)
[![CAP Protocol](https://img.shields.io/badge/protocol-CAP%20Breast%20Cancer%20(15%20Fields)-teal)](https://www.cap.org/)
[![Evaluation](https://img.shields.io/badge/benchmark-Zero--Phrase--Leakage%20(N%3D1%2C000)-success)](benchmarks/clean_slate/)
[![Release](https://img.shields.io/badge/release-v1.0--thesis-blue)](https://github.com/roojask/app_pathology_7-7-2569/releases/tag/v1.0-thesis)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

An end-to-end, edge-native, and fully offline-capable AI speech recognition and structured clinical reporting system designed specifically for **Gross Examination of Breast Cancer Specimens** following the **College of American Pathologists (CAP)** cancer protocol.

PathoWhisper enables hands-free, contaminated-glove gross dictation directly at laboratory grossing stations under fume hood ventilation noise without internet connectivity or external cloud dependencies.

---

## 🎯 System Overview & Technical Pillars

Surgical gross pathology examinations require pathologists to inspect breast resection specimens while wearing gloves contaminated with tissue fluids and formalin. Real-time dictation at the grossing station suffers from loud fume hood exhaust noise, fast speech tempo, and frequent mid-sentence self-corrections.

**PathoWhisper** addresses these operational hurdles through four tightly integrated technological pillars:

```
                        Raw Dictation Audio (16 kHz Mono)
                                      │
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ 1. Adaptive Blind SNR-Gated Acoustic Filter      │
             │    RMS P85 - P15 Frame Energy (tau* = 13.55 dB)   │
             └────────────────────────┬─────────────────────────┘
                                      │
                  ┌───────────────────┴───────────────────┐
                  ▼                                       ▼
        SNR < 13.55 dB (Noisy)                 SNR >= 13.55 dB (Clean)
    [FFmpeg afftdn: nr=6, nf=-30]                  [Bypass Filtering]
                  │                                       │
                  └───────────────────┬───────────────────┘
                                      │ Filtered / Clean Waveform
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ 2. Contextual Orthogonal Prompting (P4)          │
             │    Phonetic Homophone Disambiguation (wait/weight)│
             └────────────────────────┬─────────────────────────┘
                                      │
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ 3. Whisper Small + LoRA (r=8, alpha=32) INT8     │
             │    48 Decoder Projections (0.2434% params)       │
             │    CTranslate2 INT8 Execution on Offline CPU     │
             └────────────────────────┬─────────────────────────┘
                                      │ Medical Transcription Text
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ 4. Deterministic CAP Extractor v3 & Safety Flags │
             │    15 CAP Fields (100% Parser Fidelity)          │
             │    Multi-Signal Risk Coverage & Human Oversight  │
             └────────────────────────┬─────────────────────────┘
                                      │
                                      ▼
                         Standardized Pathology Report
                         (Structured Form / PDF / DOCX)
```

1. **Adaptive Blind SNR-Gated Acoustic Filtering (`D8_snr_gated`):**  
   Non-intrusively evaluates the signal-to-noise ratio ($\widehat{\mathrm{SNR}} = P_{85} - P_{15}$) of 25 ms frames against an optimal threshold calibrated via Youden's Index ($\tau^* = 13.55\text{ dB}$, $J = 1.0000$). When heavy fume hood noise is detected ($\widehat{\mathrm{SNR}} < 13.55\text{ dB}$), it triggers an FFmpeg `afftdn` spectral filter ($\mathrm{nr} = 6\text{ dB}$, $\mathrm{nf} = -30\text{ dB}$). When speech is already clean ($\widehat{\mathrm{SNR}} \ge 13.55\text{ dB}$), it bypasses spectral subtraction entirely, protecting 98.67% of clean speech from musical noise and consonant degradation.
2. **Contextual Orthogonal Prompting ($P_4$):**  
   Injects clinical homophone pairs (e.g., *wait/weight*, *cm/mm*, *medial/lateral*, *margins*) into the decoder context prompt, providing orthogonal control over Clinical-Term Error Rate (C-TER) and Number-Dimension Error Rate (N-DER).
3. **Parameter-Efficient Fine-Tuning (PEFT LoRA) & INT8 CPU Inference:**  
   Adapts Whisper Small across 48 linear decoder projection layers ($r = 8, \alpha = 32$, 597,504 trainable parameters out of 241.7M, or 0.2434% parameter overhead) on 600 training cases. The model is quantized to CTranslate2 INT8, delivering sub-real-time CPU execution ($\text{RTF} \approx 0.23$) on commodity workstation processors.
4. **Deterministic Information Extraction v3 & Multi-Signal Risk Scoring:**  
   Extracts all 15 CAP breast protocol fields using a deterministic rule-based parser (achieving 100% macro-$F_1$ against ground truth text). Incorporates self-correction parsing (e.g., handling *"2.0 x 1.0 cm wait 2.5 x 1.5 cm"* $\rightarrow$ extracting the latest corrected dimensions) and a multi-signal risk flag mechanism to route low-confidence predictions to human pathologist review.

---

## 📊 Comprehensive Academic Benchmarks (N = 1,000 Cases)

The experimental evaluation follows a strict **Zero-Phrase-Leakage** protocol across 1,000 synthetic audio cases (Train: 600, Validation: 100, `test_seen`: 150, and `test_unseen`: 150). All results are reproducible using scripts in `benchmarks/clean_slate/` and match Chapter 4 of the thesis.

### 1. System Progression Benchmark ($S_0 \rightarrow S_3$)

| Evaluation Split | System / Stage Configuration | WER (%) | C-TER (%) | N-DER (%) | Macro-$F_1$ (15) | Slot Acc. (%) | $\mathrm{CER}_{\mathrm{case}}$ (%) | Error Cases | Mean Latency (s) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`test_seen`** | $S_0$: Zero-Shot (No Prompt, SNR-Gated) | 6.56 | 9.10 | 3.54 | 98.46 | 97.96 | 12.67% | 19 / 150 | 5.83 s |
| ($N = 150$, | $S_{1a}$: Zero-Shot + $P_4$ + NoFilter | **2.02** | 3.71 | **0.39** | **99.22** | 98.84 | 7.33% | 11 / 150 | 6.06 s |
| 100% unseen | $S_{1b}$: Zero-Shot + $P_4$ + Static `afftdn` | 2.37 | 4.15 | 0.50 | 97.91 | 98.36 | 12.00% | 18 / 150 | 6.75 s |
| sentence | $S_{1c}$: Zero-Shot + $P_4$ + `D8_snr_gated` | 2.14 | 3.90 | 0.48 | 99.15 | 98.71 | 8.00% | 12 / 150 | 6.02 s |
| syntax) | $S_2$: LoRA (600 cases, INT8, No Prompt) | 3.30 | **3.33** | 0.53 | 99.19 | **99.02** | 6.67% | 10 / 150 | **5.75 s** |
| | **$S_3$: Full PathoWhisper (LoRA + $P_4$ + SNR-Gated)** | 5.34 | 4.09 | 1.31 | 99.13 | 98.89 | **5.33%** | **8 / 150** | 6.07 s |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`test_unseen`** | $S_0$: Zero-Shot (No Prompt, SNR-Gated) | 9.98 | 12.03 | 5.98 | 95.69 | 96.09 | 24.00% | 36 / 150 | 5.90 s |
| ($N = 150$, | $S_{1a}$: Zero-Shot + $P_4$ + NoFilter | **5.47** | 5.46 | 2.85 | 96.07 | 96.98 | 17.33% | 26 / 150 | 6.27 s |
| new speaker & | $S_{1b}$: Zero-Shot + $P_4$ + Static `afftdn` | 6.03 | 6.77 | 3.42 | 95.77 | 96.36 | 24.00% | 36 / 150 | 7.31 s |
| novel clinical | $S_{1c}$: Zero-Shot + $P_4$ + `D8_snr_gated` | 5.72 | 6.05 | 3.06 | 95.70 | 96.67 | 18.00% | 27 / 150 | 6.59 s |
| terms) | $S_2$: LoRA (600 cases, INT8, No Prompt) | 5.79 | 5.11 | 2.28 | 94.35 | 97.47 | **11.33%** | **17 / 150** | **6.05 s** |
| | **$S_3$: Full PathoWhisper (LoRA + $P_4$ + SNR-Gated)** | 7.53 | **4.05** | **1.58** | **96.22** | **97.73** | **11.33%** | **17 / 150** | 6.57 s |

*Note: All improvements over $S_0$ are statistically significant under one-sided Wilcoxon signed-rank test and McNemar's test with Holm-Bonferroni family-wise error rate control ($p_{\mathrm{Holm}} < 0.05$).*

---

### 2. Cross-Architecture Study (4 ASR Paradigms, 11 Models)

Benchmarked on stratified validation cases ($N = 50$) under identical acoustic conditions:

| Paradigm | Model Architecture | Parameters | WER (%) | C-TER (%) | N-DER (%) | Macro-$F_1$ (%) | $\mathrm{CER}_{\mathrm{case}}$ (%) | RTF |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Hybrid FST** | Vosk Small (Kaldi TDNN-F) | ~40M | 26.16 | 23.69 | 15.80 | 51.83 | 100.0% | 0.251 |
| **SSL + CTC** | Meta Wav2Vec 2.0 Base (960h, CTC) | 95M | 30.10 | 39.92 | 19.33 | 49.49 | 100.0% | 0.158 |
| **SSL + CTC** | Microsoft WavLM Base+ (CTC) | 94M | 32.43 | 45.67 | 21.24 | 49.46 | 100.0% | 0.142 |
| **SSL + CTC** | Meta HuBERT Large (LS-960-FT, CTC) | 315M | 29.54 | 36.21 | 14.25 | 46.83 | 100.0% | 0.373 |
| **SSL + CTC** | Meta Wav2Vec 2.0 Large (LV-60k, CTC) | 315M | 21.92 | 27.26 | 14.20 | 55.62 | 100.0% | 0.377 |
| **Seq2Seq (ZS)** | Faster-Whisper Tiny (INT8) | 39M | 16.44 | 17.90 | 7.19 | 92.56 | 26.0% | 0.064 |
| **Seq2Seq (ZS)** | Faster-Whisper Base (INT8) | 74M | 9.34 | 11.66 | 4.67 | 97.18 | 20.0% | 0.090 |
| **Seq2Seq (ZS)** | Faster-Whisper Small (FP32) | 244M | 6.23 | 9.34 | 2.90 | 98.23 | 16.0% | 0.284 |
| **Seq2Seq (ZS)** | Faster-Whisper Small (INT8) | 244M | 6.52 | 9.62 | 3.11 | 98.23 | 14.0% | 0.208 |
| **Seq2Seq (ZS)** | Faster-Whisper Medium (INT8) | 769M | 5.31 | 3.87 | 3.77 | 99.22 | 16.0% | 0.493 |
| **PEFT (Ours)**| **PathoWhisper Small LoRA (INT8)** | **244M** | **5.31** | **4.64** | **1.96** | **99.16** | **6.0%** | **0.227** |

---

## 🏗️ Repository Structure

The repository is structured following modular engineering principles:

```text
app_pathology_7-7-2569/
├── benchmarks/clean_slate/             # Clean-Slate evaluation framework
│   ├── acoustic_filters.py             # Blind SNR estimation & D8_snr_gated logic
│   ├── metrics_clean.py                # Normalized WER, C-TER, N-DER, Macro-F1, CER
│   ├── run_clean_slate_experiments.py  # Calibration & Experiments 1-3 runner
│   ├── expand_arch_study.py            # 11-model cross-architecture evaluation
│   ├── train_whisper_lora.py           # Whisper Small LoRA training & INT8 export
│   ├── fix_longform_lora_eval.py       # Duration-aware long-form chunked decoding
│   ├── generate_final_thesis_tables.py # McNemar, Wilcoxon, Holm tests & Tables 6-13
│   ├── generate_thesis_figures.py      # High-resolution (300 DPI) publication figures
│   └── results/                        # Master JSON & case-level benchmark CSVs
│       ├── final_thesis_master_summary.json  # Consolidated single source of truth
│       ├── calibrated_tau.json         # Calibrated SNR gate threshold (13.55 dB)
│       └── figures/                    # Publication charts (Figures 1-6)
├── data/
│   ├── dataset_ft/                     # 1,000 synthetic audio cases manifest
│   │   ├── ground_truth_ft.json        # 15 CAP fields ground truth definitions
│   │   └── manifest.csv                # Split index (600:100:150:150)
│   └── assets/                         # Pathology report templates (PDF / DOCX)
├── docs/thesis_latex/                  # Complete XeLaTeX thesis manuscript
│   ├── cpkkuproject.cls                # KKU College of Computing thesis style
│   ├── main.tex                        # Thesis entry point
│   ├── chapter1.tex - chapter5.tex     # Chapters 1 through 5
│   ├── appendices.tex                  # Appendices A-F (including AI Declaration)
│   └── images/charts/                  # Rendered thesis publication charts
├── scripts/
│   └── make_finetune_data.py           # 1,000-case generator & Zero-Leakage partition
├── src/
│   ├── core/
│   │   └── engine_faster_whisper.py    # Offline CTranslate2 engine with D8 filter
│   ├── nlp/
│   │   └── extractor_v3.py             # 15-field CAP parser & safety risk flags
│   ├── database/                       # PostgreSQL & local SQLite models
│   └── pdf/                            # PyMuPDF standardized report generator
├── tests/
│   └── test_app_clean_slate_e2e.py     # End-to-end integration and API tests
├── app.py                              # Flask core web application factory
├── gui_app.py                          # Windows system tray standalone desktop GUI
├── run_production.py                   # Multi-threaded Waitress WSGI production server
├── build_installer.ps1                 # Automated Inno Setup Windows packager
├── installer.iss                       # Inno Setup offline desktop installer script
├── requirements.txt                    # Locked production Python dependencies
└── README.md                           # Project documentation
```

---

## 🚀 Quickstart & Usage

### 1. Prerequisites
- **Python 3.10+** (Python 3.10, 3.11, and 3.12 verified)
- **FFmpeg:** Required for audio filtering and format transcoding. Ensure `ffmpeg` is accessible in your system `PATH`.

### 2. Installation
```bash
git clone https://github.com/roojask/app_pathology_7-7-2569.git
cd app_pathology_7-7-2569

# Create and activate Python virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell / CMD
# source .venv/bin/activate     # Linux / macOS

# Install dependencies
pip install -r requirements.txt
```

### 3. Running the Application
- **Option A: Production Waitress Server (Recommended for Laboratory Workstations)**
  ```bash
  python run_production.py
  ```
- **Option B: Local Web Server (Development Mode)**
  ```bash
  python app.py
  ```
- **Option C: Windows System Tray Desktop App**
  ```bash
  python gui_app.py
  ```
- **Option D: Build Offline Windows Desktop Installer**
  ```powershell
  .\build_installer.ps1
  ```
  *(Packages application, Python runtime, FFmpeg, and model into an offline `.exe` installer via Inno Setup).*

---

## 🔬 Reproducibility Guide (Clean-Slate Benchmark Suite)

To reproduce the entire experimental evaluation, statistical tests, and thesis tables/figures from scratch, execute the following 6 steps:

```bash
# Step 1: Generate 1,000-case dataset (15 CAP fields) & verify parser (100% Macro-F1)
python scripts/make_finetune_data.py

# Step 2: Calibrate SNR threshold (tau*=13.55 dB) & run baseline Experiments 1-3
python benchmarks/clean_slate/run_clean_slate_experiments.py --stage all_core
python benchmarks/clean_slate/expand_arch_study.py

# Step 3: Train Whisper Small LoRA (r=8, alpha=32), export INT8 & run progression S0-S3
python benchmarks/clean_slate/train_whisper_lora.py --epochs 3
python benchmarks/clean_slate/fix_longform_lora_eval.py

# Step 4: Run statistical hypothesis tests (McNemar, Wilcoxon, Holm) & generate tables 6-13
python benchmarks/clean_slate/generate_final_thesis_tables.py

# Step 5: Render high-resolution publication figures (300 DPI Figures 1-6)
python benchmarks/clean_slate/generate_thesis_figures.py

# Step 6: Execute end-to-end integration and offline desktop application tests
python tests/test_app_clean_slate_e2e.py
```

---

## 📄 Academic Citation & Thesis Reference

This repository represents the official research codebase and evaluation benchmark for the Bachelor of Science in Artificial Intelligence thesis:

```bibtex
@mastersthesis{pathowhisper2025,
  title={การพัฒนาระบบแปลงเสียงเป็นข้อความโดยใช้ปัญญาประดิษฐ์เพื่อบันทึกข้อมูลอัตโนมัติในงานพยาธิวิทยา (Development of an AI-Based Speech-to-Text System for Automatic Data Recording in Pathology)},
  author={Lohasan, Thaninrat and Klangthin, Chetsada},
  school={College of Computing, Khon Kaen University},
  year={2025},
  type={Senior Project / Bachelor's Thesis},
  address={Khon Kaen, Thailand},
  note={In Collaboration with Department of Pathology, Faculty of Medicine, Khon Kaen University}
}
```

* **Authors:** Mr. Thaninrat Lohasan (นายธนินท์รัฐ โลหะสาร), Mr. Chetsada Klangthin (นายเจษฎา กลางถิ่น)
* **Advisors:** Asst. Prof. Isoon Kanjanasurat, Ph.D. & Asst. Prof. Chaiwat Apiwatnasiri, M.D. (Co-Advisor)
* **Academic Unit:** Artificial Intelligence Program, College of Computing, Khon Kaen University

---

## 📜 License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.
