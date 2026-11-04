import json
import os
import tempfile
from pathlib import Path

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

        temporary_path = None
        try:
            # Same directory keeps replacement on the same filesystem.
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=f".{self.path.name}.", suffix=".tmp", delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
