import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from guitar_practice_app.models import Attempt, Exercise, Fragment, PracticeSession, TempoLog


SCHEMA_VERSION = 3


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

    def load_journal(self):
        from guitar_practice_app.services import Journal

        data = self._read_data()
        if data.get("version", 1) > SCHEMA_VERSION:
            raise ValueError("Версия журнала новее поддерживаемой. Обновите приложение.")
        exercises, logs = self._decode_records(data)
        sessions = [PracticeSession.from_dict(item) for item in data.get("sessions", [])]
        sessions = [replace(s, status="interrupted") if s.status == "in_progress" else s for s in sessions]
        return Journal(exercises, logs, sessions,
                       [Attempt(**item) for item in data.get("attempts", [])],
                       [Fragment(**item) for item in data.get("fragments", [])],
                       data.get("settings"))

    def save_journal(self, journal):
        self.save(journal.exercises, journal.logs, journal.sessions,
                  journal.attempts, journal.fragments, journal.settings)

    def save(self, exercises, logs, sessions=None, attempts=None, fragments=None, settings=None):
        data = {
            "version": SCHEMA_VERSION,
            "exercises": [exercise.to_dict() for exercise in exercises],
            "logs": [log.to_dict() for log in logs],
        }
        if sessions is not None:
            data["sessions"] = [session.to_dict() for session in sessions]
        if attempts is not None:
            data["attempts"] = [attempt.to_dict() for attempt in attempts]
        if fragments is not None:
            data["fragments"] = [fragment.to_dict() for fragment in fragments]
        if settings is not None:
            data["settings"] = settings

        atomic_write_json(self.path, data)


def atomic_write_json(path, data):
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
