import os
import zipfile
from pathlib import Path

BASE_DIR = Path("C:/app_pathology_7-7-2569-main")
EVAL_DIR = BASE_DIR / "benchmarks" / "thesis_eval_outputs"

zip_targets = [
    Path("C:/Users/project/Downloads/pathowhisper_evaluation_data.zip"),
    EVAL_DIR / "pathowhisper_evaluation_data.zip"
]

# Files to bundle:
# 1. Everything in benchmarks/thesis_eval_outputs (csv, json, png, etc.)
# 2. Key code files for verification (app.py, configs, extractor, normalizer, templates, scripts)

extra_files = [
    BASE_DIR / "app.py",
    BASE_DIR / "configs" / "config.py",
    BASE_DIR / "src" / "nlp" / "extractor.py",
    BASE_DIR / "src" / "nlp" / "normalizer.py",
    BASE_DIR / "scripts" / "analyze_benchmark.py",
    BASE_DIR / "scripts" / "run_fair_empirical_comparison.py",
    BASE_DIR / "scripts" / "summarize_fair_benchmark.py",
    BASE_DIR / "templates" / "index.html",
    BASE_DIR / "templates" / "dashboard.html",
    BASE_DIR / "templates" / "history.html",
]

for zpath in zip_targets:
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Add evaluation outputs
        for f in EVAL_DIR.iterdir():
            if f.is_file() and not f.name.endswith(".zip"):
                zf.write(f, arcname=f.name)
        
        # 2. Add extra source files under source_code/ folder in zip
        for f in extra_files:
            if f.exists():
                arcname = f"source_code/{f.relative_to(BASE_DIR)}"
                zf.write(f, arcname=arcname)
                # also write at root if it's app.py or extractor.py so easy to find
                if f.name in ["app.py", "extractor.py", "normalizer.py", "analyze_benchmark.py"]:
                    zf.write(f, arcname=f.name)
                    
    print(f"Packaged {zpath} -> {zpath.stat().st_size:,} bytes")
