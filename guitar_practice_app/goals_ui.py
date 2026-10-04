"""Goal cards and editor, independent of the practice counter."""

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from guitar_practice_app.settings import DEFAULT_DURATIONS
from guitar_practice_app.cycles import cycle_start, cycle_end
from guitar_practice_app.tempo import duration_label


class ExerciseGoalsPanel(ttk.LabelFrame):
    def __init__(self, parent, journal, save_journal):
        super().__init__(parent, text="Прогресс до цели")
        self.journal = journal
        self.save_journal = save_journal
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.selected_cycle = None
        selector = ttk.Frame(self)
        selector.grid(row=0, column=0, sticky="ew")
        ttk.Label(selector, text="Недельный цикл (ср–вт):").pack(side="left", padx=4)
        self.cycle_selector = ttk.Combobox(selector, state="readonly", width=30)
        self.cycle_selector.pack(side="left", padx=4)
        self.cycle_selector.bind("<<ComboboxSelected>>", self.select_cycle)
        self.cards = ttk.Frame(self)
        self.cards.grid(row=1, column=0, sticky="nsew")
        self.card_widgets = []
        self.layout_shape = (0, 0)
        self.bind("<Configure>", self.layout_cards)

    def layout_cards(self, event=None):
        columns = max(1, min(3, self.winfo_width() // 260))
        rows = (len(self.card_widgets) + columns - 1) // columns
        for column in range(self.layout_shape[0]):
            self.cards.columnconfigure(column, weight=0, uniform="")
        for row in range(self.layout_shape[1]):
            self.cards.rowconfigure(row, weight=0, uniform="")
        for column in range(columns):
            self.cards.columnconfigure(column, weight=1, uniform="goal_columns")
        for row in range(rows):
            self.cards.rowconfigure(row, weight=1, uniform="goal_rows")
        self.layout_shape = (columns, rows)
        for index, card in enumerate(self.card_widgets):
            card.grid(row=index // columns, column=index % columns, sticky="nsew", padx=6, pady=4)

    def refresh(self):
        current = cycle_start().isoformat()
        cycles = {current}
        for exercise in self.journal.exercises:
            cycles.update(goal.week_start for goal in exercise.weekly_goals if goal.week_start <= current)
        if self.selected_cycle:
            cycles.add(self.selected_cycle)
        self.cycle_options = sorted(cycles, reverse=True)
        self.cycle_selector["values"] = [
            f"{start} — {cycle_end(date.fromisoformat(start)).isoformat()}"
            for start in self.cycle_options
        ]
        self.cycle_selector.current(self.cycle_options.index(self.selected_cycle or current))
        for child in self.cards.winfo_children():
            child.destroy()
        self.card_widgets = []
        names = self.journal.sorted_exercise_names()
        if not names:
            ttk.Label(self.cards, text="Добавьте упражнение, чтобы задать цель.").pack(padx=12, pady=12)
        for name in names:
            card = ttk.Frame(self.cards, padding=4, relief="groove", borderwidth=1)
            self.card_widgets.append(card)
            card.columnconfigure(0, weight=1)
            ttk.Label(card, text=name, font=("Arial", 11, "bold"), wraplength=225).grid(
                row=0, column=0, sticky="w",
            )
            maximum = self.journal.max_tempo_text(name) or "—"
            ttk.Label(card, text=f"Максимум: {maximum}").grid(row=1, column=0, sticky="w")
            for row, kind, title in ((2, "total", "Общая цель"), (3, "weekly", "Недельная цель")):
                self.create_progress_block(card, row, name, kind, title)
        self.layout_cards()

    def select_cycle(self, event=None):
        selected = self.cycle_options[self.cycle_selector.current()]
        self.selected_cycle = None if selected == cycle_start().isoformat() else selected
        self.refresh()

    def as_of(self):
        if self.selected_cycle is None:
            return date.today()
        return min(date.today(), cycle_end(date.fromisoformat(self.selected_cycle)))

    def create_progress_block(self, card, row, name, kind, title):
        progress = self.journal.goal_progress(name, kind=kind, as_of=self.as_of())
        block = ttk.Frame(card, padding=0)
        block.grid(row=row, column=0, sticky="ew", pady=1)
        block.columnconfigure(0, weight=1)
        ttk.Label(block, text=title).grid(row=0, column=0, sticky="w")
        ttk.Button(block, text="Изменить" if progress.percent is not None else "Задать",
                   command=lambda: self.open_editor(name, kind)).grid(row=0, column=1, sticky="e")
        ttk.Progressbar(block, maximum=100, value=progress.percent or 0).grid(
            row=1, column=0, columnspan=2, sticky="ew",
        )
        text = "Цель: —"
        if progress.percent is not None:
            percent = "100% ✓" if progress.reached else f"{int(progress.percent)}%"
            text = f"Цель: {progress.target_tempo} / {duration_label(progress.target_duration)} · {percent}"
        ttk.Label(block, text=text).grid(row=2, column=0, columnspan=2, sticky="w")

    def open_editor(self, name, kind="weekly"):
        ExerciseGoalWindow(self, self.journal, name, self.save_journal, self.refresh,
                           kind=kind, as_of=self.as_of())


class ExerciseGoalWindow:
    def __init__(self, parent, journal, name, save_journal, refresh, kind="weekly", as_of=None):
        self.journal = journal
        self.name = name
        self.save_journal = save_journal
        self.refresh = refresh
        self.kind = kind
        self.as_of = as_of or date.today()
        self.window = tk.Toplevel(parent)
        title = "Общая цель" if kind == "total" else f"Неделя с {cycle_start(self.as_of).isoformat()}"
        self.window.title(f"{title}: {name}")
        self.window.transient(parent.winfo_toplevel())
        self.window.grab_set()
        self.window.resizable(False, False)
        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=name, wraplength=360).grid(row=0, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Label(frame, text="Целевой темп:").grid(row=1, column=0, sticky="w")
        self.tempo = ttk.Entry(frame)
        self.tempo.grid(row=1, column=1, padx=8, pady=4)
        ttk.Label(frame, text="Длительность:").grid(row=2, column=0, sticky="w")
        self.duration = ttk.Combobox(frame, state="readonly", values=DEFAULT_DURATIONS, width=24)
        self.duration.grid(row=2, column=1, padx=8, pady=4)
        progress = journal.goal_progress(name, kind=kind, as_of=self.as_of)
        if progress.target_tempo is not None:
            self.tempo.insert(0, str(progress.target_tempo))
            self.duration.set(progress.target_duration)
        else:
            self.duration.current(0)
        ttk.Button(frame, text="Сохранить", command=self.save).grid(row=3, column=0, pady=8)
        clear = ttk.Button(frame, text="Убрать цель", command=self.clear)
        clear.grid(row=3, column=1, sticky="w", padx=8)
        if progress.target_tempo is None:
            clear.state(["disabled"])

    def apply_change(self, change):
        original = list(self.journal.exercises)
        try:
            change()
            self.save_journal()
        except (ValueError, OSError) as error:
            self.journal.exercises[:] = original
            messagebox.showerror("Не удалось сохранить цель", str(error), parent=self.window)
            return
        self.refresh()
        self.window.destroy()

    def save(self):
        self.apply_change(lambda: self.journal.set_exercise_goal(
            self.name, self.tempo.get(), self.duration.get(), kind=self.kind, as_of=self.as_of,
        ))

    def clear(self):
        self.apply_change(lambda: self.journal.clear_exercise_goal(self.name, kind=self.kind, as_of=self.as_of))
