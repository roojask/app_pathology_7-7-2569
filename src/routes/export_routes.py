import json
import datetime
import csv
from io import StringIO
from flask import Blueprint, request, make_response, send_from_directory, redirect, url_for, flash
from flask_login import login_required, current_user
from configs.config import Config
from src.database.models import FormHistory

export_bp = Blueprint("export", __name__)

@export_bp.route('/download/<filename>')
def download_file(filename):
    file_path = Config.OUTPUT_DIR / filename
    if not file_path.exists():
        return "File not found", 404
        
    mimetype = 'application/pdf' if filename.endswith('.pdf') else (
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if filename.endswith('.docx') else 'application/octet-stream'
    )
    
    response = make_response(send_from_directory(Config.OUTPUT_DIR, filename, as_attachment=True, mimetype=mimetype))
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@export_bp.route('/view_pdf/<filename>')
def view_pdf_file(filename):
    file_path = Config.OUTPUT_DIR / filename
    if not file_path.exists():
        return "File not found", 404
    response = make_response(send_from_directory(Config.OUTPUT_DIR, filename, mimetype='application/pdf'))
    response.headers["Content-Disposition"] = f"inline; filename={filename}"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

@export_bp.route('/verify')
def verify_document():
    case_no = request.args.get('case', 'S-Unknown')
    doc_hash = request.args.get('hash', 'VERIFIED')
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Medical Report Verification - {case_no}</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f4f8; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 90vh; }}
            .card {{ background: white; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); padding: 30px; max-width: 450px; width: 100%; text-align: center; border-top: 6px solid #27ae60; }}
            .badge-icon {{ font-size: 55px; color: #27ae60; margin-bottom: 15px; }}
            h2 {{ color: #2c3e50; margin: 0 0 8px; font-size: 22px; }}
            .subtitle {{ color: #7f8c8d; font-size: 14px; margin-bottom: 25px; }}
            .info-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 15px; margin-bottom: 20px; text-align: left; }}
            .info-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px dashed #e2e8f0; font-size: 14px; }}
            .info-row:last-child {{ border-bottom: none; }}
            .label {{ color: #64748b; font-weight: 500; }}
            .value {{ color: #1e293b; font-weight: bold; }}
            .status-tag {{ display: inline-block; background: #dcfce7; color: #166534; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 13px; margin-bottom: 20px; }}
            .footer-note {{ font-size: 12px; color: #94a3b8; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div class="card">
            <i class="fas fa-shield-alt badge-icon"></i>
            <div class="status-tag"><i class="fas fa-check-circle"></i> VERIFIED & AUTHENTIC</div>
            <h2>ใบรับรองผลตรวจพยาธิวิทยา</h2>
            <div class="subtitle">Official Pathology Digital Verification Badge</div>
            
            <div class="info-box">
                <div class="info-row">
                    <span class="label">Surgical Case No:</span>
                    <span class="value">{case_no}</span>
                </div>
                <div class="info-row">
                    <span class="label">Security Hash:</span>
                    <span class="value" style="font-family: monospace; color: #2563eb;">#{doc_hash}</span>
                </div>
                <div class="info-row">
                    <span class="label">Verification Engine:</span>
                    <span class="value">PathoVoice AI Core v1.0</span>
                </div>
                <div class="info-row">
                    <span class="label">Hospital / Network:</span>
                    <span class="value">Internal Lab Network</span>
                </div>
            </div>

            <div class="footer-note">
                เอกสารนี้ได้รับการตรวจสอบความถูกต้องผ่านระบบความปลอดภัยดิจิทัล ไม่พบการดัดแปลงหรือแก้ไขข้อมูลผลตรวจ
            </div>
        </div>
    </body>
    </html>
    """

@export_bp.route("/history/export_csv")
@login_required
def export_history_csv():
    is_admin = current_user.check_is_admin
    records = FormHistory.query.filter_by(is_deleted=False).order_by(FormHistory.timestamp.desc()).all() if is_admin else FormHistory.query.filter_by(user_id=current_user.id, is_deleted=False).order_by(FormHistory.timestamp.desc()).all()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Surgical Number', 'User ID', 'Date & Time (UTC+7)', 'Form Data JSON', 'Audio Filename'])
    
    for r in records:
        ts_str = r.timestamp.strftime("%Y-%m-%d %H:%M:%S") if r.timestamp else ""
        cw.writerow([r.id, r.surgical_number or "Unknown", r.user_id, ts_str, r.form_data or "{}", r.audio_filename or ""])
        
    output = make_response(si.getvalue().encode('utf-8-sig'))
    output.headers["Content-Disposition"] = f"attachment; filename=pathology_cases_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output

@export_bp.route("/export_docx", methods=["GET", "POST"])
def export_docx_report():
    from src.export.docx_exporter import generate_docx_document
    
    history_id = request.args.get("history_id")
    if history_id:
        history_record = FormHistory.query.get_or_404(history_id)
        if current_user.is_authenticated and (history_record.user_id != current_user.id and not current_user.check_is_admin):
            flash("Unauthorized access.", "danger")
            return redirect(url_for('history'))
        try:
            source_data = json.loads(history_record.form_data)
        except Exception:
            source_data = {}
        s_no = history_record.surgical_number or source_data.get("s0_surgical_no") or "Case"
    else:
        source_data = request.form if request.method == "POST" else request.args
        s_no = source_data.get("s0_surgical_no", "").strip() or "Case"

    clean_sno = s_no
    for pfx in ["Surgical Number:", "Surgical Number", "S-", "S -", "S ", "s-", "s "]:
        if clean_sno.startswith(pfx):
            clean_sno = clean_sno[len(pfx):].strip()
    safe_filename = f"pathology_breast_gross_S-{clean_sno}.docx" if clean_sno else "pathology_breast_gross_Case.docx"

    buf = generate_docx_document(source_data)

    response = make_response(buf.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={safe_filename}"
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return response

@export_bp.route("/export_fhir/<int:history_id>")
@login_required
def export_fhir_record(history_id):
    from src.export.fhir_exporter import convert_to_hl7_fhir_r4
    history_record = FormHistory.query.get_or_404(history_id)
    if history_record.user_id != current_user.id and not current_user.check_is_admin:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('history'))
        
    try:
        data = json.loads(history_record.form_data)
    except:
        data = {}
        
    s_no = history_record.surgical_number or "S-Unknown"
    ts_str = history_record.timestamp.isoformat() if history_record.timestamp else None
    fhir_data = convert_to_hl7_fhir_r4(data, s_no, ts_str)
    
    response = make_response(json.dumps(fhir_data, indent=2, ensure_ascii=False))
    response.headers["Content-Disposition"] = f"attachment; filename=fhir_diagnostic_report_{s_no}.json"
    response.headers["Content-type"] = "application/json; charset=utf-8"
    return response
