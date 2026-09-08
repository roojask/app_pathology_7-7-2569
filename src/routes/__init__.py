"""
Application Routes & Blueprint Registration
PathoWhisper Assistant
"""

from src.routes.auth_routes import auth_bp
from src.routes.case_routes import cases_bp
from src.routes.dictation_routes import dictation_bp
from src.routes.export_routes import export_bp

def register_blueprints(app):
    """
    Registers all application blueprints and establishes backward-compatible
    endpoint aliases so existing Jinja2 templates and external callers continue
    working seamlessly without modification.
    """
    app.register_blueprint(auth_bp)
    app.register_blueprint(cases_bp)
    app.register_blueprint(dictation_bp)
    app.register_blueprint(export_bp)

    # Automatic root endpoint aliasing for seamless backward compatibility
    endpoints_to_alias = [
        ('auth.login', 'login'),
        ('auth.logout', 'logout'),
        ('auth.register', 'register'),
        ('auth.forgot_password', 'forgot_password'),
        ('cases.index', 'index'),
        ('cases.dashboard', 'dashboard'),
        ('cases.history', 'history'),
        ('cases.load_history', 'load_history'),
        ('cases.generate_pdf', 'generate_pdf'),
        ('cases.get_case_photo', 'get_case_photo'),
        ('cases.get_case_revisions', 'get_case_revisions'),
        ('cases.api_delete_case', 'api_delete_case'),
        ('cases.api_restore_case', 'api_restore_case'),
        ('dictation.api_extract_text', 'api_extract_text'),
        ('dictation.api_upload_audio', 'api_upload_audio'),
        ('dictation.get_upload', 'get_upload'),
        ('dictation.api_flywheel_stats', 'api_flywheel_stats'),
        ('dictation.api_flywheel_export', 'api_flywheel_export'),
        ('export.download_file', 'download_file'),
        ('export.view_pdf_file', 'view_pdf_file'),
        ('export.verify_document', 'verify_document'),
        ('export.export_history_csv', 'export_history_csv'),
        ('export.export_docx_report', 'export_docx_report'),
        ('export.export_fhir_record', 'export_fhir_record'),
    ]

    for bp_endpoint, root_endpoint in endpoints_to_alias:
        if bp_endpoint in app.view_functions and root_endpoint not in app.view_functions:
            view_func = app.view_functions[bp_endpoint]
            app.view_functions[root_endpoint] = view_func
            rules = app.url_map._rules_by_endpoint.get(bp_endpoint, [])
            for rule in rules:
                app.add_url_rule(
                    rule.rule, 
                    endpoint=root_endpoint, 
                    view_func=view_func, 
                    methods=rule.methods
                )
