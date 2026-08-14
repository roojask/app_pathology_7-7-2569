import os

try:
    from celery import Celery
    CELERY_AVAILABLE = True
except ImportError:
    Celery = None
    CELERY_AVAILABLE = False

from app import app, db
from src.database.models import AudioTask
from src.stt.whisper_model import transcribe_audio

# Configure Celery to use SQLite database as the message broker and result backend.
# This removes the dependency on Redis, allowing full queue functionality locally on Windows.
db_dir = os.path.abspath(os.path.join("data", "instance"))
os.makedirs(db_dir, exist_ok=True)
db_path = os.path.join(db_dir, "celery_queue.db")

broker_url = f"sqla+sqlite:///{db_path}"
backend_url = f"db+sqlite:///{db_path}"

if CELERY_AVAILABLE:
    celery_app = Celery(
        "tasks",
        broker=broker_url,
        backend=backend_url
    )
    # Configure celery serialization
    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"]
    )
    task_decorator = celery_app.task
else:
    celery_app = None
    def task_decorator(func):
        return func

@task_decorator
def transcribe_audio_task(task_id, file_path):

    """
    Celery background task to transcribe audio file.
    Updates the database record status to 'processing' and then to 'completed' or 'failed'.
    """
    with app.app_context():
        task = AudioTask.query.get(task_id)
        if not task:
            print(f"[-] Task ID {task_id} not found in database.")
            return
            
        task.status = "processing"
        db.session.commit()
        
        try:
            print(f"[*] Starting transcription for Task ID {task_id}...")
            text = transcribe_audio(file_path)
            
            if "Error during transcription" in text:
                task.status = "failed"
                task.result_text = "Error during transcription"
            else:
                task.status = "completed"
                task.result_text = text
                
            db.session.commit()
            print(f"[+] Task ID {task_id} successfully completed!")
        except Exception as e:
            print(f"[-] Exception in Task ID {task_id}: {e}")
            task.status = "failed"
            task.result_text = f"Exception: {e}"
            db.session.commit()
