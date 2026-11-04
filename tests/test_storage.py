import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class AtomicJournalStorageTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        self.path = self.folder / "journal.json"
        self.storage = JournalStorage(self.path)
        self.original_exercises = [Exercise("Исходное упражнение")]
        self.original_logs = [TempoLog("Исходное упражнение", 90, "восьмые", "2026-11-01")]
        self.storage.save(self.original_exercises, self.original_logs)
        self.original_bytes = self.path.read_bytes()

    def assert_original_preserved(self):
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        self.assertEqual(self.storage.load(), (self.original_exercises, self.original_logs))
        self.assertEqual(list(self.folder.iterdir()), [self.path])

    def test_partial_write_failure_does_not_touch_original(self):
        def fail_after_partial_write(data, file, **kwargs):
            file.write('{"version": 1, "exercises": [')
            raise OSError("Нет места на диске")

        with patch("guitar_practice_app.storage.json.dump", side_effect=fail_after_partial_write):
            with self.assertRaisesRegex(OSError, "Нет места"):
                self.storage.save([Exercise("Новое")], [])
        self.assert_original_preserved()

    def test_replace_failure_does_not_touch_original(self):
        with patch("guitar_practice_app.storage.os.replace", side_effect=OSError("Замена запрещена")):
            with self.assertRaisesRegex(OSError, "Замена запрещена"):
                self.storage.save([Exercise("Новое")], [])
        self.assert_original_preserved()

    def test_sync_failure_does_not_touch_original(self):
        with patch("guitar_practice_app.storage.os.fsync", side_effect=OSError("Ошибка синхронизации")):
            with self.assertRaises(OSError):
                self.storage.save([Exercise("Новое")], [])
        self.assert_original_preserved()

    def test_temp_creation_failure_does_not_touch_original(self):
        with patch("guitar_practice_app.storage.tempfile.NamedTemporaryFile", side_effect=OSError("Нет доступа")):
            with self.assertRaises(OSError):
                self.storage.save([Exercise("Новое")], [])
        self.assert_original_preserved()

    def test_serialization_failure_does_not_touch_original(self):
        with self.assertRaises(TypeError):
            self.storage.save([Exercise("Некорректное", description=object())], [])
        self.assert_original_preserved()

    def test_failed_first_save_leaves_no_partial_journal(self):
        self.path.unlink()
        with patch("guitar_practice_app.storage.os.replace", side_effect=OSError("Ошибка замены")):
            with self.assertRaises(OSError):
                self.storage.save([Exercise("Новое")], [])
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_success_replaces_complete_file_from_same_directory(self):
        import os

        real_replace = os.replace

        def inspect_and_replace(source, destination):
            self.assertEqual(source.parent, self.path.parent)
            self.assertNotEqual(source, self.path)
            self.assertEqual(destination, self.path)
            self.assertEqual(self.path.read_bytes(), self.original_bytes)
            loaded = JournalStorage(source).load()
            self.assertEqual(loaded, ([Exercise("Новое")], []))
            real_replace(source, destination)

        with patch("guitar_practice_app.storage.os.replace", side_effect=inspect_and_replace) as replace_file:
            self.storage.save([Exercise("Новое")], [])
        replace_file.assert_called_once()
        self.assertEqual(self.storage.load(), ([Exercise("Новое")], []))
        self.assertEqual(list(self.folder.iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()
