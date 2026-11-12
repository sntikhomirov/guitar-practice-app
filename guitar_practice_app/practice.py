"""Transactional controller for a single exercise practice session."""


class PracticeController:
    def __init__(self, journal, save, stats):
        self.journal = journal
        self.save = save
        self.stats = stats
        self.session_id = None

    @property
    def session(self):
        session = self.journal.session_by_id(self.session_id)
        return session if session is not None and session.status == "in_progress" else None

    def transaction(self, change):
        logs, sessions, session_id = list(self.journal.logs), list(self.journal.sessions), self.session_id
        try:
            result = change()
            self.save()
            return result
        except (ValueError, OSError):
            self.journal.logs[:] = logs
            self.journal.sessions[:] = sessions
            self.session_id = session_id
            raise

    def append_result(self, exercise, tempo, duration, log_date):
        if not self.stats.total():
            raise ValueError("Нет попыток для сохранения.")
        log = self.journal.append_session_result(
            exercise, tempo, duration, log_date, self.stats.success, self.stats.fail,
            self.session.id if self.session else None,
        )
        self.session_id = log.session_id
        return log

    def save_result(self, exercise, tempo, duration, log_date):
        result = self.transaction(lambda: self.append_result(exercise, tempo, duration, log_date))
        self.stats.reset()
        return result

    def finish(self, exercise, tempo, duration, log_date):
        def change():
            if self.stats.total():
                self.append_result(exercise, tempo, duration, log_date)
            if self.session is None:
                raise ValueError("Сначала сохраните хотя бы один результат.")
            if self.session.exercise != exercise or self.session.date != log_date:
                raise ValueError("Упражнение и дата текущей отработки уже зафиксированы.")
            return self.journal.set_session_status(self.session.id, "completed")

        result = self.transaction(change)
        self.stats.reset()
        self.session_id = None
        return result

    def interrupt(self):
        if self.session is not None:
            self.transaction(lambda: self.journal.set_session_status(self.session.id, "interrupted"))
        self.session_id = None
