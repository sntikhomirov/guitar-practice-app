import tempfile
import unittest
from pathlib import Path

from guitar_practice_app.models import Exercise, TempoLog
from guitar_practice_app.storage import JournalStorage


class JournalStorageTest(unittest.TestCase):
    def test_save_and_load_journal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "journal.json"
            storage = JournalStorage(path)

            storage.save(
                exercises=[Exercise("Гамма", "Описание")],
                logs=[TempoLog("Гамма", 120, "восьмые", "2026-10-01", success=8, fail=2)],
            )
            exercises, logs = storage.load()

        self.assertEqual(exercises, [Exercise("Гамма", "Описание")])
        self.assertEqual(logs, [TempoLog("Гамма", 120, "восьмые", "2026-10-01", success=8, fail=2)])


if __name__ == "__main__":
    unittest.main()
