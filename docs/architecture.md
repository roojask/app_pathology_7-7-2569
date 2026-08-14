# 🏛️ Pathology Voice Assistant - Architecture & Project Structure

## 📂 Directory Layout

```text
app_pathology/
├── bin/                 # Local standalone tools & binaries (FFmpeg)
├── benchmarks/          # Comprehensive AI / STT evaluation suite
│   ├── datasets/        # Evaluation audio, mock JSONs & ground truths
│   ├── reports/         # Accuracy reports, charts, and metrics
│   └── scripts/         # Evaluation & stress test runners
├── configs/             # Configuration & environment setup
│   └── config.py        # Centralized Flask & Whisper configuration
├── data/                # Runtime data directory (Database, Uploads, Outputs)
│   ├── backups/         # Auto database backups
│   ├── instance/        # SQLite databases
│   ├── outputs/         # Generated PDF & DOCX reports
│   └── uploads/         # Uploaded pathology voice recordings
├── docs/                # Project documentation & walkthroughs
├── models/              # LoRA adapters & model checkpoints
├── scripts/             # Maintenance, migrations, and setup scripts
├── src/                 # Application source package
│   ├── database/        # SQLAlchemy Models (User, FormHistory, AudioTask)
│   ├── nlp/             # Regex & Spacy Section Extraction & Normalization
│   ├── pdf/             # PDF overlay and Word report generation
│   ├── storage/         # Cloud storage clients (Supabase)
│   ├── stt/             # Speech-to-Text Whisper AI engine
│   └── tasks/           # Background asynchronous job handling
├── static/              # CSS stylesheets, Javascript, icons & assets
├── templates/           # HTML templates (Jinja2)
├── tests/               # Automated unit tests
├── app.py               # Main Flask application & routes
├── run_server.py        # Multi-threaded production server runner
└── run_local.bat        # Windows one-click local launcher
```

## 🔄 Core Pipeline Flow
1. **Audio Input**: Pathologist dictates pathology report via Web Speech or Audio Upload.
2. **Audio Pre-processing**: `src.stt.whisper_model.denoise_audio` applies FFT noise reduction.
3. **STT Transcription**: OpenAI Whisper transcribes speech using domain-specific medical prompts.
4. **Text Normalization**: `src.nlp.normalizer` standardizes measurements and Thai-English terms.
5. **15-Section Extraction**: `src.nlp.extractor` extracts structured sections and evaluates confidence.
6. **Report Generation**: `src.pdf.generator` populates standardized medical PDF and DOCX reports.
