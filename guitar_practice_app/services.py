from datetime import date, timedelta
from math import ceil

from guitar_practice_app.models import Exercise, PracticePlanItem, TempoLog
from guitar_practice_app.tempo import duration_label, normalized_tempo


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

    def add_tempo_log(self, exercise, tempo, duration, log_date, success=0, fail=0):
        exercise = exercise.strip()
        duration = duration.strip()
        log_date = log_date.strip()

        if not exercise:
            raise ValueError("Выберите упражнение.")

        tempo = int(tempo)
        if tempo <= 0:
            raise ValueError("Темп должен быть положительным целым числом.")

        success = int(success)
        fail = int(fail)
        if success < 0 or fail < 0:
            raise ValueError("Количество попыток не может быть отрицательным.")

        date.fromisoformat(log_date)

        log = TempoLog(
            exercise=exercise,
            tempo=tempo,
            duration=duration,
            date=log_date,
            success=success,
            fail=fail,
        )
        self.logs.append(log)
        return log

    def add_practice_session(self, exercise, tempo, duration, log_date, stats):
        return self.add_tempo_log(
            exercise=exercise,
            tempo=tempo,
            duration=duration,
            log_date=log_date,
            success=stats.success,
            fail=stats.fail,
        )

    def exercise_names(self):
        return [exercise.name for exercise in self.exercises]

    def sorted_exercise_names(self):
        return sorted(
            self.exercise_names(),
            key=lambda exercise: self.max_normalized_tempo(exercise),
        )

    def format_tempo(self, log):
        return f"{log.tempo} / {duration_label(log.duration)}"

    def format_max_tempo(self, log):
        normalized = normalized_tempo(log.tempo, log.duration)
        return f"{self.format_tempo(log)} (={normalized})"

    def max_normalized_tempo(self, exercise):
        logs = [log for log in self.logs if log.exercise == exercise]
        if not logs:
            return 0

        return max(normalized_tempo(log.tempo, log.duration) for log in logs)

    def best_log(self, logs):
        return max(logs, key=lambda log: normalized_tempo(log.tempo, log.duration))

    def max_tempo_text(self, exercise):
        logs = [log for log in self.logs if log.exercise == exercise]
        if not logs:
            return ""

        return self.format_max_tempo(self.best_log(logs))

    def day_tempo_text(self, log_date, exercise):
        logs = [
            log
            for log in self.logs
            if log.date == log_date and log.exercise == exercise
        ]
        if not logs:
            return ""

        return self.format_tempo(self.best_log(logs))

    def table_rows(self):
        exercises = self.sorted_exercise_names()
        if not exercises:
            return []

        rows = [["Максимум"] + [self.max_tempo_text(exercise) for exercise in exercises]]
        dates = sorted({log.date for log in self.logs}, reverse=True)

        for log_date in dates:
            rows.append(
                [log_date] + [self.day_tempo_text(log_date, exercise) for exercise in exercises]
            )

        return rows

    def logs_for_exercise(self, exercise):
        return [log for log in self.logs if log.exercise == exercise]

    def last_log(self, exercise):
        logs_with_index = [
            (index, log)
            for index, log in enumerate(self.logs)
            if log.exercise == exercise
        ]
        if not logs_with_index:
            return None

        return max(logs_with_index, key=lambda item: (item[1].date, item[0]))[1]

    def weekly_practice_count(self, exercise, as_of=None):
        as_of = as_of or date.today()
        week_start = as_of - timedelta(days=6)
        count = 0

        for log in self.logs_for_exercise(exercise):
            log_date = date.fromisoformat(log.date)
            if week_start <= log_date <= as_of:
                count += 1

        return count

    def practice_plan(self, as_of=None):
        as_of = as_of or date.today()
        items = []

        for exercise in self.exercise_names():
            last_log = self.last_log(exercise)
            start_tempo = None
            start_duration = ""
            last_tempo = ""
            last_date = ""

            if last_log:
                start_tempo = ceil(last_log.tempo * 0.9)
                start_duration = duration_label(last_log.duration)
                last_tempo = self.format_tempo(last_log)
                last_date = last_log.date

            items.append(
                PracticePlanItem(
                    exercise=exercise,
                    weekly_practice_count=self.weekly_practice_count(exercise, as_of),
                    max_tempo=self.max_tempo_text(exercise),
                    max_normalized_tempo=self.max_normalized_tempo(exercise),
                    last_tempo=last_tempo,
                    start_tempo=start_tempo,
                    start_duration=start_duration,
                    last_date=last_date,
                )
            )

        return sorted(
            items,
            key=lambda item: (
                item.weekly_practice_count,
                item.max_normalized_tempo,
                item.exercise.lower(),
            ),
        )


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

    def total(self):
        return self.success + self.fail

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
