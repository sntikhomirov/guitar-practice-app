import json

from guitar_practice_app.models import Exercise, TempoLog


SCHEMA_VERSION = 1


class JournalStorage:
    def __init__(self, path):
        self.path = path

    def load(self):
        if not self.path.exists():
            return [], []

        with self.path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        exercises = [Exercise.from_dict(item) for item in data.get("exercises", [])]
        logs = [TempoLog.from_dict(item) for item in data.get("logs", [])]
        return exercises, logs

    def save(self, exercises, logs):
        data = {
            "version": SCHEMA_VERSION,
            "exercises": [exercise.to_dict() for exercise in exercises],
            "logs": [log.to_dict() for log in logs],
        }

        with self.path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
