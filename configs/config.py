import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "pathology-secret")
    
    # Database setting: Auto-switch between PostgreSQL and SQLite
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", 
        "postgresql://neondb_owner:npg_KCviVYxf46ZT@ep-plain-poetry-azzx4hmt-pooler.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    )
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # SSL/HTTPS Server configuration
    USE_HTTPS = os.environ.get("USE_HTTPS", "True").lower() in ("true", "1", "yes")
    SSL_CERT_PATH = DATA_DIR / "cert.pem"
    SSL_KEY_PATH = DATA_DIR / "key.pem"
    
    # Path settings
    UPLOAD_DIR = DATA_DIR / "uploads"
    OUTPUT_DIR = DATA_DIR / "outputs"
    ASSETS_DIR = DATA_DIR / "assets"
    TEMPLATE_DIR = BASE_DIR / "templates"
    PDF_TEMPLATE_PATH = ASSETS_DIR / "Breast_Gross_Template.pdf"
    
    # Whisper Model settings
    WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
    PATHOLOGY_PROMPT = (
        "Received in formalin. Modified radical mastectomy specimen. "
        "Simple mastectomy. Skin ellipse. The nipple is everted, inverted, shows ulceration. "
        "Infiltrative firm yellow-white mass. Well-defined firm white mass with slit-like appearance. "
        "Poorly circumscribed yellow-white lesion. "
        "Previous surgical cavity with adjacent fibrous tissue. Residual mass. "
        "Beneath the nipple, beneath the scar, subareola. "
        "Upper inner quadrant, lower outer quadrant. "
        "Deep margin, superior margin, inferior margin, medial margin, lateral margin. "
        "Uninvolved breast parenchyma. Lymph nodes ranging from. "
        "Representative sections are submitted as. Nipple, mass, old biopsy cavity."
    )
    
    @staticmethod
    def init_app(app):
        # Create required directories if they don't exist
        for p in [Config.UPLOAD_DIR, Config.OUTPUT_DIR, Config.ASSETS_DIR, DATA_DIR / "instance"]:
            p.mkdir(parents=True, exist_ok=True)
