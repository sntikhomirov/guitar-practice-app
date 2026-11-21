"""Exact stability windows. Historical aggregates never become invented events."""

from dataclasses import dataclass, replace
from datetime import date, datetime
from uuid import uuid4

from guitar_practice_app.models import Attempt, Fragment, TempoLog
from guitar_practice_app.settings import DEFAULT_DURATIONS


CUTOFF = date(2026, 11, 14)
MIN_ATTEMPTS = 10
THRESHOLD = 70
TRANSITION_NOTICE = (
    "Точное наблюдение начато с внедрения фичи; учитываются события с 14.11.2026. "
    "Исторические агрегаты в точное окно не входят."
)


@dataclass(frozen=True)
class StabilityResult:
    attempts: tuple
    window_size: int
    current_attempts: tuple = ()

    @property
    def total(self):
        return len(self.attempts)

    @property
    def successes(self):
        return sum(attempt.success for attempt in self.attempts)

    @property
    def percent(self):
        return self.successes * 100 / self.total if self.total else None

    @property
    def status(self):
        if not self.total:
            return "Нет данных"
        if self.total < MIN_ATTEMPTS:
            return "Недостаточно данных"
        if self.successes * 100 >= THRESHOLD * self.total:
            return "Повышение разрешено"
        return "Порог повышения не достигнут"

    def to_dict(self):
        current_success = sum(attempt.success for attempt in self.current_attempts)
        return {
            "window_attempt_ids": [attempt.id for attempt in self.attempts],
            "successes": self.successes, "total": self.total, "percent": self.percent,
            "status": self.status, "window_size": self.window_size,
            "current_session": {
                "successes": current_success, "total": len(self.current_attempts),
                "percent": current_success * 100 / len(self.current_attempts) if self.current_attempts else None,
            },
        }


class StabilityJournal:
    """Mixin for event storage, fragments and reproducible calculations."""

    def init_stability(self, attempts, fragments, settings):
        self.attempts = list(attempts or [])
        self.fragments = list(fragments or [])
        self.settings = {"stability_window": 30, "next_attempt_sequence": 1}
        self.settings.update(settings or {})
        if type(self.settings["next_attempt_sequence"]) is not int or self.settings["next_attempt_sequence"] < 1:
            raise ValueError("Некорректный следующий номер попытки.")
        if len({fragment.id for fragment in self.fragments}) != len(self.fragments):
            raise ValueError("Повторяющийся идентификатор фрагмента.")
        for fragment in self.fragments:
            self.exercise_by_name(fragment.exercise)
            if not fragment.id or not fragment.name.strip():
                raise ValueError("Некорректный фрагмент.")
        self.set_window_size(self.settings["stability_window"])
        sequences = [attempt.sequence for attempt in self.attempts]
        if len(sequences) != len(set(sequences)) or len({a.id for a in self.attempts}) != len(self.attempts):
            raise ValueError("Повторяющиеся идентификаторы или порядок попыток.")
        self.settings["next_attempt_sequence"] = max(self.settings["next_attempt_sequence"], max(sequences, default=0) + 1)
        for attempt in self.attempts:
            session = self.session_by_id(attempt.session_id)
            if session is None or session.exercise != attempt.exercise:
                raise ValueError("Попытка не соответствует своей отработке.")
            self.validate_scope(attempt.exercise, attempt.scope_id)
        self.rebuild_exact_logs()

    def snapshot(self):
        return (list(self.exercises), list(self.logs), list(self.sessions), list(self.attempts),
                list(self.fragments), dict(self.settings))

    def restore(self, snapshot):
        exercises, logs, sessions, attempts, fragments, settings = snapshot
        self.exercises[:] = exercises
        self.logs[:] = logs
        self.sessions[:] = sessions
        self.attempts[:] = attempts
        self.fragments[:] = fragments
        self.settings.clear()
        self.settings.update(settings)

    def set_window_size(self, size):
        if isinstance(size, str):
            try:
                size = int(size)
            except ValueError:
                raise ValueError("Размер окна должен быть целым числом от 10 до 1000.") from None
        if type(size) is not int or not 10 <= size <= 1000:
            raise ValueError("Размер окна должен быть целым числом от 10 до 1000.")
        self.settings["stability_window"] = size

    def fragments_for(self, exercise):
        return sorted((fragment for fragment in self.fragments if fragment.exercise == exercise),
                      key=lambda fragment: fragment.name.casefold())

    def scope_name(self, exercise, scope_id):
        if not scope_id:
            return "Целое упражнение"
        self.validate_scope(exercise, scope_id)
        return next(fragment.name for fragment in self.fragments if fragment.id == scope_id)

    def validate_scope(self, exercise, scope_id):
        if scope_id and not any(fragment.id == scope_id and fragment.exercise == exercise for fragment in self.fragments):
            raise ValueError("Фрагмент не принадлежит выбранному упражнению.")

    def save_fragment(self, exercise, name, fragment_id=None):
        self.exercise_by_name(exercise)
        name = name.strip()
        if not name or name.casefold() == "целое упражнение":
            raise ValueError("Введите название фрагмента, отличное от «Целое упражнение».")
        if any(f.exercise == exercise and f.name.casefold() == name.casefold() and f.id != fragment_id
               for f in self.fragments):
            raise ValueError("Фрагмент с таким названием уже существует.")
        if fragment_id is not None:
            self.validate_scope(exercise, fragment_id)
        fragment = Fragment(fragment_id or str(uuid4()), exercise, name)
        self.fragments[:] = [fragment if f.id == fragment.id else f for f in self.fragments]
        if fragment_id is None:
            self.fragments.append(fragment)
        return fragment

    def rebuild_exact_logs(self):
        groups = {}
        for attempt in sorted(self.attempts, key=lambda item: item.sequence):
            groups.setdefault(attempt.approach_id, []).append(attempt)
        derived = {}
        for approach_id, attempts in groups.items():
            first = attempts[0]
            if any((a.exercise, a.session_id, a.tempo, a.duration, a.scope_id) !=
                   (first.exercise, first.session_id, first.tempo, first.duration, first.scope_id) for a in attempts):
                raise ValueError("В одном подходе смешаны разные параметры.")
            session = self.session_by_id(first.session_id)
            if session is None:
                raise ValueError("Отработка исходной попытки не найдена.")
            successes = sum(a.success for a in attempts)
            derived[approach_id] = TempoLog(first.exercise, first.tempo, first.duration, session.date,
                                           successes, len(attempts) - successes, first.session_id,
                                           first.scope_id, approach_id, True)
        rebuilt = []
        for log in self.logs:
            if not log.exact:
                rebuilt.append(log)
            elif log.approach_id in derived:
                rebuilt.append(derived.pop(log.approach_id))
        rebuilt.extend(derived.values())
        self.logs[:] = rebuilt

    def attempt_by_id(self, attempt_id):
        attempt = next((a for a in self.attempts if a.id == attempt_id), None)
        if attempt is None:
            raise ValueError("Попытка не найдена.")
        return attempt

    def correct_attempt(self, attempt_id, success):
        if type(success) is not bool:
            raise ValueError("Выберите результат попытки.")
        original = self.attempt_by_id(attempt_id)
        updated = replace(original, success=success)
        self.attempts[self.attempts.index(original)] = updated
        self.rebuild_exact_logs()

    def delete_attempt(self, attempt_id):
        attempt = self.attempt_by_id(attempt_id)
        self.attempts.remove(attempt)
        self.rebuild_exact_logs()
        if not self.session_results(attempt.session_id):
            self.sessions[:] = [session for session in self.sessions if session.id != attempt.session_id]

    def group_attempts(self, exercise, tempo, duration, scope_id="", eligible_only=True, as_of=None):
        as_of = as_of or datetime.now().astimezone()
        result = [a for a in self.attempts if (a.exercise, a.tempo, a.duration, a.scope_id) ==
                  (exercise, tempo, duration, scope_id)]
        if eligible_only:
            result = [a for a in result if datetime.fromisoformat(a.recorded_at).date() >= CUTOFF
                      and datetime.fromisoformat(a.recorded_at) <= as_of]
        return sorted(result, key=lambda item: item.sequence)

    def stability(self, exercise, tempo, duration, scope_id="", session_id=None, as_of=None):
        as_of = as_of or datetime.now().astimezone()
        attempts = self.group_attempts(exercise, tempo, duration, scope_id, as_of=as_of)
        # Session metrics are independent of cutoff and window, but not of scope/tempo.
        current = self.group_attempts(exercise, tempo, duration, scope_id, eligible_only=False)
        current = tuple(a for a in current if session_id is not None and a.session_id == session_id
                        and datetime.fromisoformat(a.recorded_at) <= as_of)
        size = self.settings["stability_window"]
        return StabilityResult(tuple(attempts[-size:]), size, current)

    def stability_groups(self, exercise, scope_id=""):
        groups = {(a.tempo, a.duration) for a in self.attempts if a.exercise == exercise and a.scope_id == scope_id}
        groups.update((log.tempo, log.duration) for log in self.logs
                      if not log.exact and log.exercise == exercise and log.scope_id == scope_id)
        return sorted(groups, key=lambda item: (
            item[0], DEFAULT_DURATIONS.index(item[1]) if item[1] in DEFAULT_DURATIONS else len(DEFAULT_DURATIONS),
            item[1],
        ))

    def historical_estimate(self, exercise, tempo, duration, scope_id="", as_of=None):
        """All eligible aggregate counts, not a fabricated last-N window."""
        as_of = as_of or datetime.now().astimezone()
        logs = [log for log in self.logs if not log.exact
                and (log.exercise, log.tempo, log.duration, log.scope_id) == (exercise, tempo, duration, scope_id)
                and CUTOFF <= date.fromisoformat(log.date) <= as_of.date()]
        successes = sum(log.success for log in logs)
        total = sum(log.success + log.fail for log in logs)
        return {
            "successes": successes, "total": total,
            "percent": successes * 100 / total if total else None,
            "aggregate_count": len(logs), "cutoff": CUTOFF.isoformat(),
            "date_basis": "session_date", "exact_order_known": False,
            "used_for_status": False, "window_size": None,
        }

    def stability_export(self, exercise, session_id=None, as_of=None):
        self.exercise_by_name(exercise)
        as_of = as_of or datetime.now().astimezone()
        groups = []
        for scope_id in [""] + [f.id for f in self.fragments_for(exercise)]:
            for tempo, duration in self.stability_groups(exercise, scope_id):
                stats = self.stability(exercise, tempo, duration, scope_id, session_id, as_of)
                groups.append({"scope_id": scope_id, "scope_name": self.scope_name(exercise, scope_id),
                               "tempo": tempo, "duration": duration, **stats.to_dict(),
                               "historical_estimate": self.historical_estimate(exercise, tempo, duration, scope_id, as_of)})
        return {
            "metadata": {"calculated_at": as_of.isoformat(), "cutoff": CUTOFF.isoformat(),
                         "window_size": self.settings["stability_window"], "minimum_attempts": MIN_ATTEMPTS,
                         "success_threshold_percent": THRESHOLD, "order_by": "sequence",
                         "cutoff_date_basis": "recorded_at date in its recorded timezone",
                         "current_session_id": session_id, "transition_notice": TRANSITION_NOTICE},
            "exercise": exercise, "groups": groups,
            "fragments": [f.to_dict() for f in self.fragments_for(exercise)],
            "attempts": [a.to_dict() for a in sorted(self.attempts, key=lambda item: item.sequence) if a.exercise == exercise],
            "sessions": [s.to_dict() for s in self.sessions_for_exercise(exercise)],
            "historical_aggregates": [log.to_dict() for log in self.logs if log.exercise == exercise and not log.exact],
        }
