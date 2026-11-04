"""Browse archived exercises without removing their history."""

import tkinter as tk
from tkinter import messagebox, ttk

from guitar_practice_app.history_ui import ExerciseHistoryWindow


class ExerciseArchiveWindow:
    def __init__(self, parent, journal, restore_exercise, on_history_changed):
        self.journal = journal
        self.restore_exercise = restore_exercise
        self.on_history_changed = on_history_changed
        self.window = tk.Toplevel(parent)
        self.window.title("Архив упражнений")
        self.window.geometry("750x420")
        self.window.minsize(650, 350)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)
        self.status = ttk.Label(self.window)
        self.status.grid(row=0, column=0, sticky="w", padx=12, pady=8)
        table_frame = ttk.Frame(self.window)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=12)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(table_frame, columns=("name", "count", "date"),
                                  show="headings", selectmode="browse")
        self.table.grid(row=0, column=0, sticky="nsew")
        for key, title, width in (("name", "Упражнение", 340), ("count", "Записей", 100),
                                  ("date", "Последняя запись", 160)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=80)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self.select_record)
        buttons = ttk.Frame(self.window)
        buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=8)
        self.history_button = ttk.Button(buttons, text="История", command=self.open_history)
        self.history_button.pack(side="left", padx=4)
        self.restore_button = ttk.Button(buttons, text="Восстановить", command=self.restore_selected)
        self.restore_button.pack(side="left", padx=4)
        ttk.Button(buttons, text="Закрыть", command=self.window.destroy).pack(side="right")
        self.refresh()

    def refresh(self):
        selected = self.selected_name()
        self.table.delete(*self.table.get_children())
        exercises = self.journal.archived_exercises()
        for index, exercise in enumerate(exercises):
            logs = self.journal.logs_for_exercise(exercise.name)
            last = self.journal.last_log(exercise.name)
            self.table.insert("", "end", iid=str(index), values=(
                exercise.name, len(logs), last.date if last else "—",
            ))
            if exercise.name == selected:
                self.table.selection_set(str(index))
        self.status.configure(text=f"В архиве: {len(exercises)}" if exercises else "Архив пуст.")
        self.select_record()

    def selected_name(self):
        selection = self.table.selection()
        return self.table.item(selection[0], "values")[0] if selection else None

    def select_record(self, event=None):
        state = ["!disabled"] if self.table.selection() else ["disabled"]
        self.history_button.state(state)
        self.restore_button.state(state)

    def restore_selected(self):
        name = self.selected_name()
        if name is None:
            return
        try:
            self.restore_exercise(name)
        except (ValueError, OSError) as error:
            messagebox.showerror("Не удалось восстановить", str(error), parent=self.window)
            return
        self.refresh()

    def open_history(self):
        name = self.selected_name()
        if name is None:
            return
        history = ExerciseHistoryWindow(self.window, self.journal, name, self.on_history_changed)
        self.window.wait_window(history.window)
        if self.window.winfo_exists():
            self.window.grab_set()
            self.refresh()
