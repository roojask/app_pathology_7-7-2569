import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from local .env file
load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
BIN_DIR = BASE_DIR / "bin"

# Automatically add project bin folder to PATH (for portable ffmpeg / tools)
if BIN_DIR.exists():
    os.environ["PATH"] = str(BIN_DIR) + os.pathsep + os.environ.get("PATH", "")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "pathology-secret")
    
    # Database setting: PostgreSQL Primary
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "postgresql://postgres:rooj282026@localhost:5432/pathology_db")
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Groq Cloud API Key
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "whisper-large-v3")

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
    PDF_TEMPLATE_PATH = ASSETS_DIR / "Breast_Gross_Template.pdf"
    
    # Language Configuration: Strict English Mode
    DEFAULT_LANGUAGE = "en"
    FORCE_ENGLISH_ONLY = True
    
    # Whisper Model settings
    WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
    USE_FASTER_WHISPER_ENGINE = os.environ.get("USE_FASTER_WHISPER_ENGINE", "False").lower() in ("true", "1", "yes")
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

