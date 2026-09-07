import os
import json
import csv
from pathlib import Path
from configs.config import Config

def export_clinical_dataset(output_format="jsonl", target_dir=None):
    """
    Exports collected clinical audio-text pairs into training-ready formats:
    - 'jsonl': Standard format for Hugging Face datasets / Whisper training
    - 'csv': Metadata CSV table with audio filepath and transcript
    """
    manifest_path = Config.CLINICAL_DATASET_DIR / "dataset_manifest.jsonl"
    if not manifest_path.exists():
        return {"success": False, "error": "No collected clinical data found yet."}

    if target_dir is None:
        target_dir = Config.CLINICAL_DATASET_DIR / "exports"
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    items = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))

    if not items:
        return {"success": False, "error": "Clinical dataset manifest is empty."}

    if output_format == "csv":
        out_file = target_dir / "train_metadata.csv"
        with open(out_file, "w", encoding="utf-8", newline="") as cf:
            writer = csv.writer(cf)
            writer.writerow(["file_name", "transcription", "duration"])
            for it in items:
                writer.writerow([it.get("audio_filepath"), it.get("text"), it.get("duration")])
        return {"success": True, "path": str(out_file), "count": len(items)}
    else:
        out_file = target_dir / "train_dataset.json"
        with open(out_file, "w", encoding="utf-8") as jf:
            json.dump(items, jf, indent=2, ensure_ascii=False)
        return {"success": True, "path": str(out_file), "count": len(items)}
