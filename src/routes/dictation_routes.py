import uuid
from flask import Blueprint, request, jsonify, send_from_directory, url_for
from werkzeug.utils import secure_filename
from configs.config import Config

dictation_bp = Blueprint("dictation", __name__)

@dictation_bp.route("/api/extract", methods=["POST"])
def api_extract_text():
    try:
        req = request.get_json(silent=True) or {}
        text = req.get("text", "").strip()
        if not text:
            return jsonify({"success": False, "error": "No text provided"}), 400
        
        from src.nlp.extractor import extract_data_15_sections, generate_confidence_flags
        extracted = extract_data_15_sections(text)
        flags = generate_confidence_flags(extracted)
        return jsonify({"success": True, "data": extracted, "flags": flags})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@dictation_bp.route("/api/upload_audio", methods=["POST"])
def api_upload_audio():
    try:
        audio_file = request.files.get("audio")
        if not audio_file or audio_file.filename == "":
            return jsonify({"success": False, "error": "No audio file provided"}), 400

        orig_name = secure_filename(audio_file.filename)
        ext = orig_name.rsplit(".", 1)[-1].lower() if "." in orig_name else "webm"
        if ext not in ["wav", "mp3", "webm", "ogg", "m4a"]:
            ext = "webm"
        
        filename = f"{uuid.uuid4().hex}_mic_record.{ext}"
        save_path = Config.UPLOAD_DIR / filename
        audio_file.save(save_path)
        
        audio_fn = filename
        if Config.SUPABASE_URL and Config.SUPABASE_KEY:
            try:
                from src.storage.supabase_client import upload_audio_to_supabase
                public_url = upload_audio_to_supabase(save_path, filename, Config.SUPABASE_URL, Config.SUPABASE_KEY)
                if public_url:
                    audio_fn = public_url
            except Exception as e:
                print(f"[Storage Warning] Supabase upload error: {e}")

        audio_url = audio_fn if (audio_fn.startswith("http://") or audio_fn.startswith("https://")) else url_for("get_upload", filename=audio_fn)
        return jsonify({
            "success": True,
            "audio_filename": audio_fn,
            "audio_url": audio_url
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@dictation_bp.route('/uploads/<filename>')
@dictation_bp.route('/audio/<filename>')
def get_upload(filename):
    return send_from_directory(Config.UPLOAD_DIR, filename)

@dictation_bp.route("/api/flywheel/stats", methods=["GET"])
def api_flywheel_stats():
    """Returns clinical audio flywheel collection statistics."""
    try:
        from src.flywheel.collector import get_flywheel_stats
        stats = get_flywheel_stats()
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@dictation_bp.route("/api/flywheel/export", methods=["GET"])
def api_flywheel_export():
    """Exports collected dataset manifest as JSON or CSV."""
    try:
        fmt = request.args.get("format", "jsonl")
        from src.flywheel.exporter import export_clinical_dataset
        res = export_clinical_dataset(output_format=fmt)
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
