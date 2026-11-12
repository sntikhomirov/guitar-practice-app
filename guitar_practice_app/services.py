from datetime import date, timedelta
from dataclasses import replace
from math import ceil
from uuid import NAMESPACE_URL, uuid4, uuid5

from guitar_practice_app.cycles import cycle_start
from guitar_practice_app.models import Exercise, GoalProgress, PracticePlanItem, PracticeSession, TempoLog
from guitar_practice_app.settings import DEFAULT_DURATIONS
from guitar_practice_app.tempo import duration_label, normalized_tempo


class DuplicateExerciseError(ValueError):
    pass


class Journal:
    def __init__(self, exercises=None, logs=None, sessions=None):
        self.exercises = list(exercises or [])
        self.logs = list(logs or [])
        self.sessions = list(sessions or [])
        # Legacy results on one date formed one completed practice session.
        known = {session.id: session for session in self.sessions}
        for index, log in enumerate(self.logs):
            session_id = log.session_id or str(uuid5(NAMESPACE_URL, f"guitar-practice:{log.exercise}:{log.date}"))
            if session_id not in known:
                session = PracticeSession(session_id, log.exercise, log.date, "completed")
                known[session_id] = session
                self.sessions.append(session)
            session = known[session_id]
            if session.exercise != log.exercise or session.date != log.date:
                raise ValueError("Результат не соответствует своей отработке.")
            self.logs[index] = replace(log, session_id=session_id)

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

    def _make_tempo_log(self, exercise, tempo, duration, log_date, success=0, fail=0):
        exercise = exercise.strip()
        duration = duration.strip()
        log_date = log_date.strip()

        if not exercise:
            raise ValueError("Выберите упражнение.")

        try:
            tempo = int(tempo)
        except (TypeError, ValueError):
            raise ValueError("Темп должен быть положительным целым числом.") from None
        if tempo <= 0:
            raise ValueError("Темп должен быть положительным целым числом.")

        try:
            success = int(success)
            fail = int(fail)
        except (TypeError, ValueError):
            raise ValueError("Количество попыток должно быть целым числом.") from None
        if success < 0 or fail < 0:
            raise ValueError("Количество попыток не может быть отрицательным.")

        try:
            parsed_date = date.fromisoformat(log_date)
        except ValueError:
            raise ValueError("Введите дату в формате ГГГГ-ММ-ДД.") from None

        if duration not in DEFAULT_DURATIONS:
            raise ValueError("Выберите длительность из списка.")

        log = TempoLog(
            exercise=exercise,
            tempo=tempo,
            duration=duration,
            date=parsed_date.isoformat(),
            success=success,
            fail=fail,
        )
        return log

    def add_tempo_log(self, exercise, tempo, duration, log_date, success=0, fail=0):
        if not exercise.strip():
            raise ValueError("Выберите упражнение.")
        selected = self.exercise_by_name(exercise.strip())
        if selected.archived:
            raise ValueError("Упражнение в архиве. Сначала восстановите его.")
        log = self._make_tempo_log(exercise, tempo, duration, log_date, success, fail)
        session = PracticeSession(str(uuid4()), log.exercise, log.date, "completed")
        self.sessions.append(session)
        log = replace(log, session_id=session.id)
        self.logs.append(log)
        return log

    def session_by_id(self, session_id):
        return next((session for session in self.sessions if session.id == session_id), None)

    def session_results(self, session_id):
        return [(index, log) for index, log in enumerate(self.logs) if log.session_id == session_id]

    def sessions_for_exercise(self, exercise):
        indexed = [(index, session) for index, session in enumerate(self.sessions) if session.exercise == exercise]
        return [session for _, session in sorted(indexed, key=lambda item: (item[1].date, item[0]), reverse=True)]

    def append_session_result(self, exercise, tempo, duration, log_date, success, fail, session_id=None):
        selected = self.exercise_by_name(exercise)
        if selected.archived:
            raise ValueError("Упражнение в архиве. Сначала восстановите его.")
        log = self._make_tempo_log(exercise, tempo, duration, log_date, success, fail)
        if log.success + log.fail == 0:
            raise ValueError("Нет попыток для сохранения.")
        session = self.session_by_id(session_id)
        if session is None:
            if session_id is not None:
                raise ValueError("Отработка не найдена.")
            session = PracticeSession(str(uuid4()), exercise, log.date)
            self.sessions.append(session)
        elif session.status != "in_progress" or session.exercise != exercise or session.date != log.date:
            raise ValueError("Упражнение и дата текущей отработки уже зафиксированы.")
        log = replace(log, session_id=session.id)
        self.logs.append(log)
        return log

    def set_session_status(self, session_id, status):
        session = self.session_by_id(session_id)
        if session is None or not self.session_results(session_id):
            raise ValueError("Нет результатов для завершения отработки.")
        replacement = replace(session, status=status)
        self.sessions[self.sessions.index(session)] = replacement
        return replacement

    def exercise_history(self, exercise):
        """Return (list index, record) pairs, newest first, including duplicates."""
        records = [(index, log) for index, log in enumerate(self.logs)
                   if log.exercise == exercise]
        return sorted(records, key=lambda item: (item[1].date, item[0]), reverse=True)

    def update_tempo_log(self, index, tempo, duration, log_date, success=0, fail=0):
        original = self._log_at(index)
        replacement = self._make_tempo_log(
            original.exercise, tempo, duration, log_date, success, fail,
        )
        replacement = replace(replacement, session_id=original.session_id)
        if replacement.date != original.date:
            session = self.session_by_id(original.session_id)
            if session is not None:
                self.sessions[self.sessions.index(session)] = replace(session, date=replacement.date)
            self.logs[:] = [replace(log, date=replacement.date) if log.session_id == original.session_id else log
                            for log in self.logs]
        self.logs[index] = replacement
        return replacement

    def _log_at(self, index):
        if not isinstance(index, int) or not 0 <= index < len(self.logs):
            raise ValueError("Запись не найдена.")
        return self.logs[index]

    def delete_tempo_log(self, index):
        self._log_at(index)
        removed = self.logs.pop(index)
        if not self.session_results(removed.session_id):
            self.sessions[:] = [session for session in self.sessions if session.id != removed.session_id]
        return removed

    def add_practice_session(self, exercise, tempo, duration, log_date, stats):
        return self.add_tempo_log(
            exercise=exercise,
            tempo=tempo,
            duration=duration,
            log_date=log_date,
            success=stats.success,
            fail=stats.fail,
        )

    def exercise_names(self, include_archived=False):
        return [exercise.name for exercise in self.exercises if include_archived or not exercise.archived]

    def archived_exercises(self):
        return sorted((exercise for exercise in self.exercises if exercise.archived), key=lambda item: item.name.lower())

    def archive_exercise(self, name):
        exercise = self.exercise_by_name(name)
        replacement = replace(exercise, archived=True)
        self.exercises[self.exercises.index(exercise)] = replacement
        return replacement

    def restore_exercise(self, name):
        exercise = self.exercise_by_name(name)
        replacement = replace(exercise, archived=False)
        self.exercises[self.exercises.index(exercise)] = replacement
        return replacement

    def exercise_by_name(self, name):
        for exercise in self.exercises:
            if exercise.name == name:
                return exercise
        raise ValueError("Упражнение не найдено.")

    def set_exercise_goal(self, name, tempo, duration, kind="weekly", as_of=None):
        exercise = self.exercise_by_name(name)
        if kind not in ("weekly", "total"):
            raise ValueError("Неизвестный тип цели.")
        if isinstance(tempo, str):
            try:
                tempo = int(tempo.strip())
            except ValueError:
                raise ValueError("Целевой темп должен быть положительным целым числом.") from None
        if kind == "total":
            replacement = replace(exercise, total_target_tempo=tempo, total_target_duration=duration)
        else:
            replacement = replace(exercise, target_tempo=tempo, target_duration=duration,
                                  target_week_start=cycle_start(as_of).isoformat())
        self.exercises[self.exercises.index(exercise)] = replacement
        return replacement

    def clear_exercise_goal(self, name, kind="weekly", as_of=None):
        exercise = self.exercise_by_name(name)
        if kind == "total":
            replacement = replace(exercise, total_target_tempo=None, total_target_duration="")
        elif kind == "weekly":
            start = cycle_start(as_of).isoformat()
            fields = {"weekly_goals": tuple(goal for goal in exercise.weekly_goals if goal.week_start != start)}
            if exercise.target_week_start == start:
                fields.update(target_tempo=None, target_duration="", target_week_start="")
            replacement = replace(exercise, **fields)
        else:
            raise ValueError("Неизвестный тип цели.")
        self.exercises[self.exercises.index(exercise)] = replacement
        return replacement

    def goal_progress(self, name, kind="weekly", as_of=None):
        as_of = as_of or date.today()
        exercise = self.exercise_by_name(name)
        logs = self.logs_for_exercise(name)
        start = ""
        if kind == "total":
            tempo, duration = exercise.total_target_tempo, exercise.total_target_duration
        elif kind == "weekly":
            start = cycle_start(as_of).isoformat()
            goal = next((goal for goal in exercise.weekly_goals if goal.week_start == start), None)
            tempo, duration = (goal.tempo, goal.duration) if goal else (None, "")
            logs = [log for log in logs if start <= log.date <= as_of.isoformat()]
        else:
            raise ValueError("Неизвестный тип цели.")
        best = self.best_log(logs) if logs else None
        return GoalProgress(
            exercise=exercise,
            maximum_text=self.format_max_tempo(best) if best else "",
            maximum_normalized=normalized_tempo(best.tempo, best.duration) if best else 0,
            target_normalized=normalized_tempo(tempo, duration) if tempo is not None else None,
            target_tempo=tempo,
            target_duration=duration,
            week_start=start,
        )

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
        active_names = set(exercises)
        dates = sorted({log.date for log in self.logs if log.exercise in active_names}, reverse=True)

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

        for session in self.sessions:
            log_date = date.fromisoformat(session.date)
            if session.exercise == exercise and week_start <= log_date <= as_of and self.session_results(session.id):
                count += 1

        return count

    def practice_plan(self, as_of=None, active_session_id=None):
        as_of = as_of or date.today()
        items = []

        for exercise in self.exercise_names():
            active = self.session_by_id(active_session_id)
            pinned = active is not None and active.exercise == exercise and active.status == "in_progress"
            if not pinned:
                if self.goal_progress(exercise, as_of=as_of).reached:
                    continue
                if any(session.exercise == exercise and session.status == "completed"
                       and session.date >= as_of.isoformat() for session in self.sessions):
                    continue
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

        if p_success >= 70 or (self.success_streak >= 5 and self.fail == 0):
            return "Прибавляем", "green"

        return "", "green"
