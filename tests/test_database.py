import unittest
from app import app
from src.database.models import db, User, FormHistory, AudioTask

class TestDatabaseModels(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_user_creation(self):
        user = User(username="testpathologist", email="test@hospital.com", name="Dr. Test")
        user.set_password("SecurePass123")
        db.session.add(user)
        db.session.commit()

        queried = User.query.filter_by(username="testpathologist").first()
        self.assertIsNotNone(queried)
        self.assertTrue(queried.check_password("SecurePass123"))
        self.assertFalse(queried.check_password("WrongPass"))

    def test_audio_task_creation(self):
        task = AudioTask(id="test-uuid-1234", file_path="data/uploads/sample.wav", status="pending")
        db.session.add(task)
        db.session.commit()

        queried = AudioTask.query.get("test-uuid-1234")
        self.assertIsNotNone(queried)
        self.assertEqual(queried.status, "pending")

if __name__ == "__main__":
    unittest.main()
