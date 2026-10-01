DURATION_LABELS = {
    "четверти": "4",
    "восьмые": "8",
    "восьмые триоли": "8т",
    "шестнадцатые": "16",
    "шестнадцатые триоли": "16т",
}

DURATION_FACTORS = {
    "четверти": 1,
    "восьмые": 2,
    "восьмые триоли": 3,
    "шестнадцатые": 4,
    "шестнадцатые триоли": 6,
}


def duration_label(duration):
    return DURATION_LABELS.get(duration, duration)


def normalized_tempo(tempo, duration):
    return tempo * DURATION_FACTORS.get(duration, 1)
