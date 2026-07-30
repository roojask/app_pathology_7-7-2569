import sys
import json
from pathlib import Path

# Ensure UTF-8 output encoding for Windows terminal
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add project root to sys.path
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

from app import app
from src.database.models import db, User, FormHistory

def inspect_database():
    with app.app_context():
        print("==================================================")
        print("[REPORT] PATHOLOGY DATABASE INSPECTION REPORT")
        print("==================================================")
        print(f"Database File/URI: {app.config['SQLALCHEMY_DATABASE_URI']}\n")
        
        # 1. Inspect Users
        users = User.query.all()
        print(f"[USERS] Total Registered Users: {len(users)}")
        print("-" * 50)
        for u in users:
            print(f"  • ID: {u.id} | Username: {u.username} | Name: {u.name or 'N/A'} | Email: {u.email}")
        print("\n")

        # 2. Inspect Form History Records
        histories = FormHistory.query.order_by(FormHistory.timestamp.desc()).all()
        print(f"📄 Total Saved Pathology Reports: {len(histories)}")
        print("-" * 50)
        for idx, h in enumerate(histories, 1):
            author_name = h.author.name or h.author.username if h.author else f"User ID {h.user_id}"
            print(f"[{idx}] Case Surgical No: {h.surgical_number or 'N/A'}")
            print(f"    - ID: {h.id} | Created By: {author_name}")
            print(f"    - Timestamp: {h.timestamp}")
            print(f"    - Audio File: {h.audio_filename or 'None'}")
            try:
                data_dict = json.loads(h.form_data)
                print(f"    - Sample Extracted Fields: s0_surgical_no={data_dict.get('s0_surgical_no')}, s1_side={data_dict.get('s1_side')}, s2_proc={data_dict.get('s2_proc')}")
            except Exception as e:
                print(f"    - Raw Data Snippet: {h.form_data[:100]}...")
            print("-" * 30)

        print("\n==================================================")
        print("✅ Inspection Complete!")
        print("==================================================")

if __name__ == "__main__":
    inspect_database()
