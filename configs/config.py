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
    
    # Whisper Model settings
    WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
    USE_FASTER_WHISPER_ENGINE = os.environ.get("USE_FASTER_WHISPER_ENGINE", "False").lower() in ("true", "1", "yes")
    PATHOLOGY_PROMPT = (
        "ชิ้นเนื้อ สิ่งส่งตรวจ รหัส Surgical number S-24-1001 เต้านม ข้างซ้าย ข้างขวา "
        "มอดิฟายด์ แรดิคัล แมสเทคโทมี ขนาด เซนติเมตร พบก้อนเนื้อ บริเวณ อัปเปอร์ เอาเตอร์ "
        "ควาแดรนต์ ได้ต่อมน้ำเหลือง จำนวน ต่อม "
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
