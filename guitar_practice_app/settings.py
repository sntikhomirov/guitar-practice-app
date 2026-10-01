from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = APP_DIR / "journal_data.json"

DEFAULT_DURATIONS = [
    "четверти",
    "восьмые",
    "восьмые триоли",
    "шестнадцатые",
    "шестнадцатые триоли",
]
