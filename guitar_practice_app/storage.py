import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from guitar_practice_app.models import Exercise, PracticeSession, TempoLog


SCHEMA_VERSION = 2


class JournalStorage:
    def __init__(self, path):
        self.path = path

    def _read_data(self):
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def _decode_records(data):
        exercises = [Exercise.from_dict(item) for item in data.get("exercises", [])]
        logs = [TempoLog.from_dict(item) for item in data.get("logs", [])]
        return exercises, logs

    def load(self):
        """Read exercise/result lists; use load_state() to retain session metadata."""
        return self._decode_records(self._read_data())

    def load_state(self):
        data = self._read_data()
        exercises, logs = self._decode_records(data)
        sessions = [PracticeSession.from_dict(item) for item in data.get("sessions", [])]
        # Restart never resumes an unfinished session.
        sessions = [replace(session, status="interrupted") if session.status == "in_progress" else session
                    for session in sessions]
        return exercises, logs, sessions

    def save(self, exercises, logs, sessions=None):
        data = {
            "version": SCHEMA_VERSION,
            "exercises": [exercise.to_dict() for exercise in exercises],
            "logs": [log.to_dict() for log in logs],
        }
        if sessions is not None:
            data["sessions"] = [session.to_dict() for session in sessions]

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
