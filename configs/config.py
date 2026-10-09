import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from local .env file
load_dotenv()

# ถ้าเป็น .exe ให้ชี้ไปที่โฟลเดอร์จริงของโปรแกรมที่ติดตั้ง (ไม่ใช่ Temp)
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
BIN_DIR = BASE_DIR / "bin"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
ASSETS_DIR = DATA_DIR / "assets"
# สั่งสร้างโฟลเดอร์ที่จำเป็นทั้งหมดอัตโนมัติหากยังไม่มี
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Automatically add project bin folder to PATH (for portable ffmpeg / tools)
if BIN_DIR.exists():
    os.environ["PATH"] = str(BIN_DIR) + os.pathsep + os.environ.get("PATH", "")
if getattr(sys, 'frozen', False):
    _meipass = getattr(sys, '_MEIPASS', None)
    if _meipass:
        _int_bin = Path(_meipass) / "bin"
        if _int_bin.exists():
            os.environ["PATH"] = str(_int_bin) + os.pathsep + os.environ.get("PATH", "")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "pathology-secret")
    
    # Database setting: PostgreSQL Primary
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or "sqlite:///pathology.db"
    #SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "postgresql://postgres:rooj282026@localhost:5432/pathology_db")
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    


    # Supabase Configuration
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


    
    # SSL/HTTPS Server configuration
    USE_HTTPS = os.environ.get("USE_HTTPS", "True").lower() in ("true", "1", "yes")
    SSL_CERT_PATH = DATA_DIR / "cert.pem"
    SSL_KEY_PATH = DATA_DIR / "key.pem"
    
        # Path settings
    UPLOAD_DIR = DATA_DIR / "uploads"
    OUTPUT_DIR = DATA_DIR / "outputs"
    ASSETS_DIR = DATA_DIR / "assets"
    TEMPLATE_DIR = BASE_DIR / "templates"
    if getattr(sys, 'frozen', False):
        _ext_template = Path(sys.executable).parent / "data" / "assets" / "Breast_Gross_Template.pdf"
        _int_template = Path(getattr(sys, '_MEIPASS', '')) / "data" / "assets" / "Breast_Gross_Template.pdf"
        PDF_TEMPLATE_PATH = _ext_template if _ext_template.exists() else _int_template
    else:
        PDF_TEMPLATE_PATH = ASSETS_DIR / "Breast_Gross_Template.pdf"
        
    # Language Configuration: Strict English Mode
    DEFAULT_LANGUAGE = "en"
    FORCE_ENGLISH_ONLY = True
    
    # Whisper Model settings: 100% Local Offline Speech-to-Text Engine
    WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
    USE_FASTER_WHISPER_ENGINE = os.environ.get("USE_FASTER_WHISPER_ENGINE", "True").lower() in ("true", "1", "yes")
    PATHOLOGY_PROMPT = (
        "Surgical pathology gross examination report. Surgical number S-26-1001. "
        "Received in formalin is a right modified radical mastectomy specimen. "
        "Left simple mastectomy. Skin ellipse. The nipple is everted, inverted, unremarkable, shows ulceration. "
        "Infiltrative firm yellow-white mass located at upper outer quadrant, upper inner quadrant, "
        "lower outer quadrant, lower inner quadrant, central, subareolar. "
        "Well-defined firm white mass with slit-like appearance. Poorly circumscribed yellow-white lesion. "
        "Previous surgical cavity with adjacent fibrous tissue. Residual mass. "
        "Deep surgical resection margin, superior margin, inferior margin, medial margin, lateral margin, skin margin. "
        "Centimeters, cm, millimeters, mm. Distance from closest margin. Grossly free from tumor. "
        "Representative sections submitted in paraffin blocks. Axillary contents, level 1, level 2, lymph nodes."
    )
    
    # Clinical Audio Data Flywheel settings
    ENABLE_DATA_FLYWHEEL = os.environ.get("ENABLE_DATA_FLYWHEEL", "True").lower() in ("true", "1", "yes")
    CLINICAL_DATASET_DIR = DATA_DIR / "clinical_dataset"
    CLINICAL_AUDIO_DIR = CLINICAL_DATASET_DIR / "audio"
    
    @staticmethod
    def init_app(app):
        # Create required directories if they don't exist
        for p in [Config.UPLOAD_DIR, Config.OUTPUT_DIR, Config.ASSETS_DIR, Config.CLINICAL_DATASET_DIR, Config.CLINICAL_AUDIO_DIR, DATA_DIR / "instance"]:
            p.mkdir(parents=True, exist_ok=True)

