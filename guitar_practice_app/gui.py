import json
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from guitar_practice_app.archive_ui import ExerciseArchiveWindow
from guitar_practice_app.history_ui import ExerciseHistoryWindow
from guitar_practice_app.goals_ui import ExerciseGoalsPanel
from guitar_practice_app.practice import PracticeController
from guitar_practice_app.unsaved_ui import ask_unsaved_attempts
from guitar_practice_app.services import AttemptStats, DuplicateExerciseError, Journal
from guitar_practice_app.settings import DATA_FILE, DEFAULT_DURATIONS
from guitar_practice_app.storage import JournalStorage


class GuitarPracticeApp:
    def __init__(self, root, data_file=DATA_FILE):
        self.root = root
        self.root.title("Гитарные упражнения")
        self.root.geometry("1100x650")
        self.root.minsize(1000, 550)

        self.stats = AttemptStats()
        self.storage = JournalStorage(data_file)
        self._storage_load_failed = False
        self.journal = self.load_journal()
        self.practice = PracticeController(self.journal, self.save_journal, self.stats)
        self._session_parameters = None
        self._changing_parameters = False
        self.durations = DEFAULT_DURATIONS

        self.configure_style()

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.counter_tab = ttk.Frame(self.notebook)
        self.journal_tab = ttk.Frame(self.notebook)
        self.goals_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.counter_tab, text="Счётчик попыток")
        self.notebook.add(self.journal_tab, text="Журнал занятий")
        self.notebook.add(self.goals_tab, text="Цели")

        self.create_counter_tab()
        self.update_stats()
        self.create_journal_tab()
        self.create_goals_tab()
        self.refresh_exercise_list()
        self.refresh_journal_table()
        self.refresh_practice_plan()
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

    def configure_style(self):
        style = ttk.Style()
        style.configure("TFrame", padding=4)
        style.configure("TLabelframe", padding=8)
        style.configure("Title.TLabel", font=("Arial", 18, "bold"))
        style.configure("Counter.TLabel", font=("Arial", 15))
        style.configure("Primary.TButton", padding=(12, 6))

    def load_journal(self):
        try:
            exercises, logs, sessions = self.storage.load_state()
            return Journal(exercises=exercises, logs=logs, sessions=sessions)
        except (json.JSONDecodeError, OSError, ValueError):
            self._storage_load_failed = True
            messagebox.showwarning(
                "Журнал занятий",
                "Не удалось прочитать журнал. Сохранение заблокировано, чтобы не перезаписать исходный файл.",
            )
            return Journal()

    def save_journal(self):
        if self._storage_load_failed:
            raise OSError("Журнал не загружен. Проверьте исходный файл перед сохранением.")
        self.storage.save(self.journal.exercises, self.journal.logs, self.journal.sessions)

    def create_counter_tab(self):
        self.counter_tab.columnconfigure(0, weight=1)
        self.counter_tab.rowconfigure(1, weight=1)

        ttk.Label(
            self.counter_tab,
            text="Текущее упражнение",
            style="Title.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))

        counter_frame = ttk.Frame(self.counter_tab)
        counter_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)
        counter_frame.columnconfigure(0, weight=1)
        counter_frame.columnconfigure(1, weight=1)
        counter_frame.rowconfigure(1, weight=1)

        session_frame = ttk.LabelFrame(counter_frame, text="Параметры упражнения")
        session_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        session_frame.columnconfigure(1, weight=1)

        ttk.Label(session_frame, text="Название:").grid(row=0, column=0, sticky="w", padx=8, pady=5)
        self.session_exercise_combobox = ttk.Combobox(session_frame, state="readonly")
        self.session_exercise_combobox.grid(row=0, column=1, sticky="ew", padx=8, pady=5)
        self.session_exercise_combobox.bind("<<ComboboxSelected>>", self.on_session_parameters_changed)

        ttk.Label(session_frame, text="Темп:").grid(row=1, column=0, sticky="w", padx=8, pady=5)
        self.session_tempo_entry = ttk.Entry(session_frame)
        self.session_tempo_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=5)
        self.session_tempo_entry.bind("<Return>", self.on_session_parameters_changed)

        ttk.Label(session_frame, text="Длительность:").grid(row=2, column=0, sticky="w", padx=8, pady=5)
        self.session_duration_combobox = ttk.Combobox(session_frame, state="readonly", values=self.durations)
        self.session_duration_combobox.current(0)
        self.session_duration_combobox.grid(row=2, column=1, sticky="ew", padx=8, pady=5)
        self.session_duration_combobox.bind("<<ComboboxSelected>>", self.on_session_parameters_changed)

        ttk.Label(session_frame, text="Дата:").grid(row=3, column=0, sticky="w", padx=8, pady=5)
        self.session_date_entry = ttk.Entry(session_frame)
        self.session_date_entry.insert(0, date.today().isoformat())
        self.session_date_entry.grid(row=3, column=1, sticky="ew", padx=8, pady=5)
        self.session_date_entry.bind("<Return>", self.on_session_parameters_changed)

        actions = ttk.Frame(session_frame, padding=0)
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        ttk.Button(
            actions,
            text="Сохранить результат",
            style="Primary.TButton",
            command=self.save_practice_session,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(actions, text="Завершить упражнение", style="Primary.TButton",
                   command=self.finish_exercise).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        stats_frame = ttk.LabelFrame(counter_frame, text="Счётчик попыток")
        stats_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        stats_frame.columnconfigure(0, weight=1)

        self.label_success = tk.Label(
            stats_frame, text="Удачно: 0 (0%)", font=("Arial", 14), fg="green"
        )
        self.label_success.grid(row=0, column=0, pady=5)

        self.label_fail = tk.Label(
            stats_frame, text="Неудачно: 0 (0%)", font=("Arial", 14), fg="red"
        )
        self.label_fail.grid(row=1, column=0, pady=5)

        self.label_decision = tk.Label(
            stats_frame, text="", font=("Arial", 14), fg="green"
        )
        self.label_decision.grid(row=2, column=0, pady=5)

        btn_frame = tk.Frame(stats_frame)
        btn_frame.grid(row=3, column=0, pady=5)

        tk.Button(
            btn_frame,
            text="+",
            width=5,
            font=("Arial", 16, "bold"),
            bg="lightgreen",
            command=self.add_success,
        ).grid(row=0, column=0, padx=20)

        tk.Button(
            btn_frame,
            text="-",
            width=5,
            font=("Arial", 16, "bold"),
            bg="lightcoral",
            command=self.add_fail,
        ).grid(row=0, column=1, padx=20)

        tk.Button(
            stats_frame,
            text="Сбросить статистику",
            font=("Arial", 10),
            command=self.reset,
        ).grid(row=4, column=0, pady=5)

        self.create_practice_plan_panel(counter_frame)

    def create_journal_tab(self):
        self.journal_tab.columnconfigure(0, weight=1)
        self.journal_tab.rowconfigure(1, weight=1)

        forms_frame = ttk.Frame(self.journal_tab)
        forms_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        forms_frame.columnconfigure(0, weight=1)
        forms_frame.columnconfigure(1, weight=1)

        self.create_exercise_form(forms_frame)
        self.create_tempo_form(forms_frame)
        self.create_table()

        history_bar = ttk.Frame(self.journal_tab)
        history_bar.grid(row=2, column=0, sticky="ew", pady=8)
        ttk.Label(history_bar, text="История упражнения:").pack(side="left", padx=8)
        self.history_exercise_combobox = ttk.Combobox(history_bar, state="readonly", width=30)
        self.history_exercise_combobox.pack(side="left", padx=8)
        ttk.Button(history_bar, text="Открыть историю", command=self.open_exercise_history).pack(side="left")
        ttk.Button(history_bar, text="В архив", command=self.archive_selected_exercise).pack(side="left", padx=8)
        ttk.Button(history_bar, text="Архив упражнений", command=self.open_archive).pack(side="right")

    def archive_selected_exercise(self):
        name = self.history_exercise_combobox.get()
        if not name:
            messagebox.showerror("Архив", "Выберите упражнение.")
            return
        if self.stats.total() and self.session_exercise_combobox.get() == name:
            messagebox.showerror("Архив", "Сначала сохраните или сбросьте текущие попытки.")
            return
        if not messagebox.askyesno("В архив?", f"Убрать «{name}» из активных упражнений?\nИстория и цели сохранятся.", parent=self.root):
            return
        try:
            self.set_exercise_archived(name, True)
        except (ValueError, OSError) as error:
            messagebox.showerror("Не удалось архивировать", str(error), parent=self.root)

    def set_exercise_archived(self, name, archived):
        if archived and self.stats.total() and self.session_exercise_combobox.get() == name:
            raise ValueError("Сначала сохраните или сбросьте текущие попытки.")
        original = list(self.journal.exercises)
        original_sessions = list(self.journal.sessions)
        practice = self.practice
        current_id = practice.session_id
        try:
            if archived:
                self.journal.archive_exercise(name)
                if practice.session is not None and practice.session.exercise == name:
                    self.journal.set_session_status(practice.session.id, "interrupted")
                    practice.session_id = None
            else:
                self.journal.restore_exercise(name)
            self.save_journal()
        except (ValueError, OSError):
            self.journal.exercises[:] = original
            self.journal.sessions[:] = original_sessions
            practice.session_id = current_id
            raise
        self.refresh_exercise_list()
        self.refresh_journal_table()
        self.refresh_practice_plan(prefill=self.stats.total() == 0)

    def open_archive(self):
        ExerciseArchiveWindow(self.root, self.journal,
                              lambda name: self.set_exercise_archived(name, False), self.on_history_changed)

    def create_goals_tab(self):
        ttk.Label(self.goals_tab, text="Цели упражнений", style="Title.TLabel").pack(
            anchor="w", padx=12, pady=(12, 4),
        )
        ttk.Label(self.goals_tab, text="Общая цель — вся история. Недельная — текущий цикл со среды по вторник.").pack(
            anchor="w", padx=12, pady=(0, 8),
        )
        self.goals_panel = ExerciseGoalsPanel(self.goals_tab, self.journal, self.on_goals_changed)
        self.goals_panel.pack(fill="both", expand=True, padx=12, pady=8)

    def on_goals_changed(self):
        self.save_journal()
        self.refresh_practice_plan(prefill=self.stats.total() == 0)

    def open_exercise_history(self):
        exercise = self.history_exercise_combobox.get()
        if not exercise:
            messagebox.showerror("История", "Выберите упражнение.")
            return
        ExerciseHistoryWindow(self.root, self.journal, exercise, self.on_history_changed)

    def on_history_changed(self):
        self.save_journal()
        self.refresh_journal_table()
        self.refresh_practice_plan(prefill=self.stats.total() == 0)
        self.sync_session_date()

    def create_exercise_form(self, parent):
        exercise_frame = ttk.LabelFrame(parent, text="Добавить упражнение")
        exercise_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        exercise_frame.columnconfigure(1, weight=1)

        ttk.Label(exercise_frame, text="Название:").grid(row=0, column=0, sticky="w", padx=8, pady=5)
        self.exercise_name_entry = ttk.Entry(exercise_frame)
        self.exercise_name_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=5)

        ttk.Label(exercise_frame, text="Описание:").grid(row=1, column=0, sticky="nw", padx=8, pady=5)
        self.exercise_description_text = tk.Text(exercise_frame, height=4, width=30)
        self.exercise_description_text.grid(row=1, column=1, sticky="ew", padx=8, pady=5)

        ttk.Button(
            exercise_frame,
            text="Добавить упражнение",
            command=self.add_exercise,
        ).grid(row=2, column=0, columnspan=2, pady=8)

    def create_tempo_form(self, parent):
        tempo_frame = ttk.LabelFrame(parent, text="Записать темп")
        tempo_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        tempo_frame.columnconfigure(1, weight=1)

        ttk.Label(tempo_frame, text="Упражнение:").grid(row=0, column=0, sticky="w", padx=8, pady=5)
        self.exercise_combobox = ttk.Combobox(tempo_frame, state="readonly")
        self.exercise_combobox.grid(row=0, column=1, sticky="ew", padx=8, pady=5)

        ttk.Label(tempo_frame, text="Темп:").grid(row=1, column=0, sticky="w", padx=8, pady=5)
        self.tempo_entry = ttk.Entry(tempo_frame)
        self.tempo_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=5)

        ttk.Label(tempo_frame, text="Длительность:").grid(row=2, column=0, sticky="w", padx=8, pady=5)
        self.duration_combobox = ttk.Combobox(tempo_frame, state="readonly", values=self.durations)
        self.duration_combobox.current(0)
        self.duration_combobox.grid(row=2, column=1, sticky="ew", padx=8, pady=5)

        ttk.Label(tempo_frame, text="Дата:").grid(row=3, column=0, sticky="w", padx=8, pady=5)
        self.date_entry = ttk.Entry(tempo_frame)
        self.date_entry.insert(0, date.today().isoformat())
        self.date_entry.grid(row=3, column=1, sticky="ew", padx=8, pady=5)

        ttk.Button(
            tempo_frame,
            text="Записать темп",
            command=self.add_tempo_log,
        ).grid(row=4, column=0, columnspan=2, pady=8)

    def create_table(self):
        table_frame = ttk.LabelFrame(self.journal_tab, text="Таблица журнала")
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self.journal_table = ttk.Treeview(table_frame, show="headings")
        self.journal_table.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.journal_table.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.journal_table.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")

        self.journal_table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

    def create_practice_plan_panel(self, parent):
        plan_frame = ttk.LabelFrame(parent, text="План занятия")
        plan_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        plan_frame.columnconfigure(0, weight=1)
        plan_frame.rowconfigure(1, weight=1)

        header_frame = ttk.Frame(plan_frame)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header_frame.columnconfigure(0, weight=1)

        self.session_status = ttk.Label(
            header_frame,
            text="Следующие упражнения",
        )
        self.session_status.grid(row=0, column=0, sticky="w")

        table_frame = ttk.Frame(plan_frame)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = (
            "exercise",
            "start_tempo",
            "weekly_count",
            "last_date",
        )
        self.practice_plan_table = ttk.Treeview(table_frame, columns=columns, show="headings", height=6)
        self.practice_plan_table.grid(row=0, column=0, sticky="nsew")

        headings = {
            "exercise": "Упражнение",
            "start_tempo": "Стартовый темп",
            "weekly_count": "7 дней",
            "last_date": "Последняя дата",
        }
        widths = {
            "exercise": 180,
            "start_tempo": 120,
            "weekly_count": 70,
            "last_date": 105,
        }

        for column in columns:
            self.practice_plan_table.heading(column, text=headings[column])
            self.practice_plan_table.column(column, width=widths[column], minwidth=60, anchor="center")

        self.practice_plan_table.column("exercise", anchor="w")

        self.plan_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.practice_plan_table.yview)
        self.plan_scrollbar.grid(row=0, column=1, sticky="ns")
        self.practice_plan_table.configure(yscrollcommand=self.update_plan_scrollbar)

    def update_plan_scrollbar(self, first, last):
        self.plan_scrollbar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.plan_scrollbar.grid_remove()
        else:
            self.plan_scrollbar.grid()

    def add_exercise(self):
        name = self.exercise_name_entry.get()
        description = self.exercise_description_text.get("1.0", "end")
        original = list(self.journal.exercises)

        try:
            self.journal.add_exercise(name, description)
            self.save_journal()
        except DuplicateExerciseError as error:
            messagebox.showerror("Ошибка", str(error))
            return
        except (ValueError, OSError) as error:
            self.journal.exercises[:] = original
            messagebox.showerror("Ошибка", str(error))
            return

        self.exercise_name_entry.delete(0, "end")
        self.exercise_description_text.delete("1.0", "end")
        self.refresh_exercise_list()
        self.refresh_journal_table()
        self.refresh_practice_plan(prefill=True)

    def add_tempo_log(self):
        original_logs, original_sessions = list(self.journal.logs), list(self.journal.sessions)
        try:
            self.journal.add_tempo_log(
                exercise=self.exercise_combobox.get(),
                tempo=self.tempo_entry.get(),
                duration=self.duration_combobox.get(),
                log_date=self.date_entry.get(),
            )
            self.save_journal()
        except (ValueError, OSError) as error:
            self.journal.logs[:] = original_logs
            self.journal.sessions[:] = original_sessions
            messagebox.showerror("Ошибка", str(error))
            return

        self.tempo_entry.delete(0, "end")
        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, date.today().isoformat())
        self.refresh_journal_table()
        self.refresh_practice_plan(prefill=True)

    def save_practice_session(self):
        previous_count = len(self.journal.logs)
        if not self.resolve_session_parameters():
            return
        try:
            # The parameter guard may already have saved the previous tempo.
            # Do not save twice or report an empty-counter error in that case.
            if self.stats.total() or len(self.journal.logs) == previous_count:
                self.practice.save_result(*self.read_session_parameters())
        except (ValueError, OSError) as error:
            messagebox.showerror("Ошибка", str(error))
            return
        self.update_stats()
        self.refresh_journal_table()
        self.refresh_practice_plan(prefill=False)
        self.sync_session_date()
        self.session_status.configure(text="Результат сохранён. Можно продолжить на другом темпе.")

    def finish_exercise(self):
        if not self.resolve_session_parameters():
            return
        try:
            self.practice.finish(*self.read_session_parameters())
        except (ValueError, OSError) as error:
            messagebox.showerror("Ошибка", str(error))
            return
        self.update_stats()
        self.refresh_journal_table()
        self.refresh_practice_plan(prefill=True)
        self.sync_session_date()
        self.session_status.configure(text="Упражнение завершено.")

    def read_session_parameters(self):
        return (self.session_exercise_combobox.get(), self.session_tempo_entry.get(),
                self.session_duration_combobox.get(), self.session_date_entry.get())

    def write_session_parameters(self, values):
        exercise, tempo, duration, log_date = values
        self.session_exercise_combobox.set(exercise)
        self.session_tempo_entry.delete(0, "end")
        self.session_tempo_entry.insert(0, str(tempo))
        self.session_duration_combobox.set(duration)
        self.session_date_entry.configure(state="normal")
        self.session_date_entry.delete(0, "end")
        self.session_date_entry.insert(0, log_date)
        self._session_parameters = tuple(str(value) for value in values)
        self.sync_session_date()

    def sync_session_date(self):
        session = self.practice.session
        self.session_date_entry.configure(state="normal")
        if session is not None:
            self.session_date_entry.delete(0, "end")
            self.session_date_entry.insert(0, session.date)
            self.session_date_entry.configure(state="readonly")
        if self._session_parameters is not None:
            self._session_parameters = self.read_session_parameters()

    def on_session_parameters_changed(self, event=None):
        self.resolve_session_parameters()

    def resolve_session_parameters(self):
        if self._changing_parameters:
            return True
        new = self.read_session_parameters()
        old = self._session_parameters
        if old is None or old == new:
            self._session_parameters = new
            return True
        self._changing_parameters = True
        try:
            if self.stats.total():
                answer = ask_unsaved_attempts(self.root)
                if answer is None:
                    self.write_session_parameters(old)
                    return False
                if answer == "save":
                    self.practice.save_result(*old)
                    self.refresh_journal_table()
                else:
                    self.stats.reset()
                self.update_stats()
            if old[0] != new[0]:
                self.practice.interrupt()
                new = (*new[:3], date.today().isoformat())
            elif self.practice.session is not None and self.practice.session.date != new[3]:
                new = (*new[:3], self.practice.session.date)
            self.write_session_parameters(new)
            self.refresh_practice_plan(prefill=False)
            return True
        except (ValueError, OSError) as error:
            self.write_session_parameters(old)
            messagebox.showerror("Ошибка", str(error))
            return False
        finally:
            self._changing_parameters = False

    def close_app(self):
        if self._changing_parameters:
            return
        self._changing_parameters = True
        try:
            if self.stats.total():
                answer = ask_unsaved_attempts(self.root, closing=True)
                if answer is None:
                    return
                if answer == "save":
                    self.practice.save_result(*(self._session_parameters or self.read_session_parameters()))
                    self.update_stats()
            self.practice.interrupt()
            self.root.destroy()
        except (ValueError, OSError) as error:
            messagebox.showerror("Не удалось сохранить", str(error))
        finally:
            self._changing_parameters = False

    def refresh_exercise_list(self):
        exercises = self.journal.exercise_names()
        for combobox in (self.exercise_combobox, self.session_exercise_combobox, self.history_exercise_combobox):
            combobox["values"] = exercises
            if combobox.get() not in exercises:
                combobox.set(exercises[0] if exercises else "")

    def refresh_journal_table(self):
        self.goals_panel.refresh()
        exercises = self.journal.sorted_exercise_names()
        columns = ["date"] + exercises

        self.journal_table.delete(*self.journal_table.get_children())
        self.journal_table["columns"] = columns

        self.journal_table.heading("date", text="Дата")
        self.journal_table.column("date", width=120, minwidth=100, anchor="center")

        for exercise in exercises:
            self.journal_table.heading(exercise, text=exercise)
            self.journal_table.column(exercise, width=120, minwidth=100, anchor="center")

        for row in self.journal.table_rows():
            self.journal_table.insert("", "end", values=row)

    def refresh_practice_plan(self, prefill=True):
        self.practice_plan_table.delete(*self.practice_plan_table.get_children())
        plan = self.journal.practice_plan(active_session_id=self.practice.session_id)

        for item in plan:
            start_tempo = ""
            if item.start_tempo is not None:
                start_tempo = f"{item.start_tempo} / {item.start_duration}"

            self.practice_plan_table.insert(
                "",
                "end",
                values=(
                    item.exercise,
                    start_tempo,
                    item.weekly_practice_count,
                    item.last_date,
                ),
            )

        if prefill and self.practice.session is None and self.stats.total() == 0:
            self.prefill_session_from_plan(plan)

    def prefill_session_from_plan(self, plan=None):
        plan = plan if plan is not None else self.journal.practice_plan()

        self.session_date_entry.configure(state="normal")
        self.session_tempo_entry.delete(0, "end")
        self.session_date_entry.delete(0, "end")
        self.session_date_entry.insert(0, date.today().isoformat())

        if not plan:
            self.session_exercise_combobox.set("")
            self.session_duration_combobox.current(0)
            self._session_parameters = self.read_session_parameters()
            return

        item = plan[0]
        self.session_exercise_combobox.set(item.exercise)

        if item.start_tempo is not None:
            self.session_tempo_entry.insert(0, str(item.start_tempo))

        duration_by_label = {
            "4": "четверти",
            "8": "восьмые",
            "8т": "восьмые триоли",
            "16": "шестнадцатые",
            "16т": "шестнадцатые триоли",
        }
        duration = duration_by_label.get(item.start_duration)
        if duration in self.durations:
            self.session_duration_combobox.current(self.durations.index(duration))
        self._session_parameters = self.read_session_parameters()

    def update_stats(self):
        p_success, p_fail = self.stats.percentages()
        decision, color = self.stats.decision()

        self.label_decision.config(text=decision, fg=color)
        self.label_success.config(
            text=f"Удачно: {self.stats.success} ({p_success}%)\nStreak: {self.stats.success_streak}"
        )
        self.label_fail.config(
            text=f"Неудачно: {self.stats.fail} ({p_fail}%)\nStreak: {self.stats.fail_streak}"
        )

    def add_success(self):
        if not self.resolve_session_parameters():
            return
        self.stats.add_success()
        self.update_stats()

    def add_fail(self):
        if not self.resolve_session_parameters():
            return
        self.stats.add_fail()
        self.update_stats()

    def reset(self):
        self.stats.reset()
        self.update_stats()


def run_app():
    window = tk.Tk()
    GuitarPracticeApp(window)
    window.mainloop()
