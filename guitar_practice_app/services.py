from datetime import date

from guitar_practice_app.models import Exercise, TempoLog


class DuplicateExerciseError(ValueError):
    pass


class Journal:
    def __init__(self, exercises=None, logs=None):
        self.exercises = list(exercises or [])
        self.logs = list(logs or [])

    def add_exercise(self, name, description=""):
        name = name.strip()
        description = description.strip()

        if not name:
            raise ValueError("Введите название упражнения.")

        if any(exercise.name.lower() == name.lower() for exercise in self.exercises):
            raise DuplicateExerciseError("Упражнение с таким названием уже есть.")

        exercise = Exercise(name=name, description=description)
        self.exercises.append(exercise)
        return exercise

    def add_tempo_log(self, exercise, tempo, duration, log_date):
        exercise = exercise.strip()
        duration = duration.strip()
        log_date = log_date.strip()

        if not exercise:
            raise ValueError("Выберите упражнение.")

        tempo = int(tempo)
        if tempo <= 0:
            raise ValueError("Темп должен быть положительным целым числом.")

        date.fromisoformat(log_date)

        log = TempoLog(
            exercise=exercise,
            tempo=tempo,
            duration=duration,
            date=log_date,
        )
        self.logs.append(log)
        return log

    def exercise_names(self):
        return [exercise.name for exercise in self.exercises]

    def format_tempo(self, log):
        return f"{log.tempo} / {log.duration}"

    def max_tempo_text(self, exercise):
        logs = [log for log in self.logs if log.exercise == exercise]
        if not logs:
            return ""

        best_log = max(logs, key=lambda log: log.tempo)
        return self.format_tempo(best_log)

    def day_tempo_text(self, log_date, exercise):
        logs = [
            log
            for log in self.logs
            if log.date == log_date and log.exercise == exercise
        ]
        if not logs:
            return ""

        best_log = max(logs, key=lambda log: log.tempo)
        return self.format_tempo(best_log)

    def table_rows(self):
        exercises = self.exercise_names()
        if not exercises:
            return []

        rows = [["Максимум"] + [self.max_tempo_text(exercise) for exercise in exercises]]
        dates = sorted({log.date for log in self.logs}, reverse=True)

        for log_date in dates:
            rows.append(
                [log_date] + [self.day_tempo_text(log_date, exercise) for exercise in exercises]
            )

        return rows


class AttemptStats:
    def __init__(self):
        self.success = 0
        self.success_streak = 0
        self.fail = 0
        self.fail_streak = 0

    def add_success(self):
        self.success += 1
        self.success_streak += 1
        self.fail_streak = 0

    def add_fail(self):
        self.fail += 1
        self.fail_streak += 1
        self.success_streak = 0

    def reset(self):
        self.success = 0
        self.success_streak = 0
        self.fail = 0
        self.fail_streak = 0

    def percentages(self):
        total = self.success + self.fail
        if total == 0:
            return 0.0, 0.0

        base = 10 if total < 10 else total
        return round((self.success / base) * 100, 1), round((self.fail / base) * 100, 1)

    def decision(self):
        total = self.success + self.fail
        if total == 0:
            return "", "green"

        p_success, p_fail = self.percentages()

        if p_fail > 50 or total > 30 or self.fail_streak >= 5:
            return "Убавляем", "red"

        if p_success >= 70 or self.success_streak >= 5:
            return "Прибавляем", "green"

        return "", "green"
