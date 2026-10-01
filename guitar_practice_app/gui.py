import json
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

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
        self.journal = self.load_journal()
        self.durations = DEFAULT_DURATIONS

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.counter_tab = ttk.Frame(self.notebook)
        self.journal_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.counter_tab, text="Счётчик попыток")
        self.notebook.add(self.journal_tab, text="Журнал занятий")

        self.create_counter_tab()
        self.create_journal_tab()
        self.refresh_exercise_list()
        self.refresh_journal_table()

    def load_journal(self):
        try:
            exercises, logs = self.storage.load()
        except (json.JSONDecodeError, OSError, ValueError):
            messagebox.showwarning(
                "Журнал занятий",
                "Не удалось прочитать файл журнала. Будет создан пустой журнал.",
            )
            exercises, logs = [], []

        return Journal(exercises=exercises, logs=logs)

    def save_journal(self):
        self.storage.save(self.journal.exercises, self.journal.logs)

    def create_counter_tab(self):
        counter_frame = ttk.Frame(self.counter_tab)
        counter_frame.pack(expand=True)

        self.label_success = tk.Label(
            counter_frame, text="Удачно: 0 (0%)", font=("Arial", 14), fg="green"
        )
        self.label_success.pack(pady=10)

        self.label_fail = tk.Label(
            counter_frame, text="Неудачно: 0 (0%)", font=("Arial", 14), fg="red"
        )
        self.label_fail.pack(pady=10)

        self.label_decision = tk.Label(
            counter_frame, text="", font=("Arial", 14), fg="green"
        )
        self.label_decision.pack(pady=10)

        btn_frame = tk.Frame(counter_frame)
        btn_frame.pack(pady=15)

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
            counter_frame,
            text="Сбросить статистику",
            font=("Arial", 10),
            command=self.reset,
        ).pack(pady=10)

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

    def add_exercise(self):
        name = self.exercise_name_entry.get()
        description = self.exercise_description_text.get("1.0", "end")

        try:
            self.journal.add_exercise(name, description)
        except DuplicateExerciseError as error:
            messagebox.showerror("Ошибка", str(error))
            return
        except ValueError as error:
            messagebox.showerror("Ошибка", str(error))
            return

        self.save_journal()
        self.exercise_name_entry.delete(0, "end")
        self.exercise_description_text.delete("1.0", "end")
        self.refresh_exercise_list()
        self.refresh_journal_table()

    def add_tempo_log(self):
        try:
            self.journal.add_tempo_log(
                exercise=self.exercise_combobox.get(),
                tempo=self.tempo_entry.get(),
                duration=self.duration_combobox.get(),
                log_date=self.date_entry.get(),
            )
        except ValueError as error:
            messagebox.showerror("Ошибка", str(error))
            return

        self.save_journal()
        self.tempo_entry.delete(0, "end")
        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, date.today().isoformat())
        self.refresh_journal_table()

    def refresh_exercise_list(self):
        exercises = self.journal.exercise_names()
        self.exercise_combobox["values"] = exercises

        if exercises and not self.exercise_combobox.get():
            self.exercise_combobox.current(0)

    def refresh_journal_table(self):
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
        self.stats.add_success()
        self.update_stats()

    def add_fail(self):
        self.stats.add_fail()
        self.update_stats()

    def reset(self):
        self.stats.reset()
        self.update_stats()


def run_app():
    window = tk.Tk()
    GuitarPracticeApp(window)
    window.mainloop()
