"""Modal exercise history and record editor."""

import tkinter as tk
from tkinter import messagebox, ttk

from guitar_practice_app.settings import DEFAULT_DURATIONS
from guitar_practice_app.tempo import normalized_tempo


class ExerciseHistoryWindow:
    def __init__(self, parent, journal, exercise, on_change):
        self.journal = journal
        self.exercise = exercise
        self.on_change = on_change
        self.selected_index = None
        self.window = tk.Toplevel(parent)
        self.window.title(f"История: {exercise}")
        self.window.geometry("850x550")
        self.window.minsize(750, 450)
        self.window.transient(parent)
        # The journal cannot change elsewhere while indexes are in use.
        self.window.grab_set()
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)

        ttk.Label(self.window, text=exercise, font=("Arial", 16, "bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=8,
        )
        table_frame = ttk.Frame(self.window)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=12)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("date", "tempo", "normalized", "success", "fail")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.table.grid(row=0, column=0, sticky="nsew")
        for column, title in zip(columns, ("Дата", "Темп", "В четвертях", "Удачно", "Неудачно")):
            self.table.heading(column, text=title)
            self.table.column(column, width=120, minwidth=80, anchor="center")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self.select_record)

        editor = ttk.LabelFrame(self.window, text="Редактировать выбранную запись")
        editor.grid(row=2, column=0, sticky="ew", padx=12, pady=8)
        self.fields = {}
        for column, (key, title) in enumerate((
            ("date", "Дата (ГГГГ-ММ-ДД)"), ("tempo", "Темп"),
            ("duration", "Длительность"), ("success", "Удачно"), ("fail", "Неудачно"),
        )):
            editor.columnconfigure(column, weight=1)
            ttk.Label(editor, text=title).grid(row=0, column=column, sticky="w", padx=4)
            widget = (ttk.Combobox(editor, values=DEFAULT_DURATIONS, state="readonly", width=22)
                      if key == "duration" else ttk.Entry(editor, width=14))
            widget.grid(row=1, column=column, sticky="ew", padx=4, pady=4)
            self.fields[key] = widget

        buttons = ttk.Frame(self.window)
        buttons.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.save_button = ttk.Button(buttons, text="Сохранить изменения", command=self.save_record)
        self.save_button.pack(side="left", padx=4)
        self.delete_button = ttk.Button(buttons, text="Удалить запись", command=self.delete_record)
        self.delete_button.pack(side="left", padx=4)
        ttk.Button(buttons, text="Закрыть", command=self.window.destroy).pack(side="right")
        self.refresh()

    def refresh(self):
        self.selected_index = None
        self.table.delete(*self.table.get_children())
        for index, log in self.journal.exercise_history(self.exercise):
            self.table.insert("", "end", iid=str(index), values=(
                log.date, self.journal.format_tempo(log),
                normalized_tempo(log.tempo, log.duration), log.success, log.fail,
            ))
        for field in self.fields.values():
            if isinstance(field, ttk.Combobox):
                field.set("")
            else:
                field.delete(0, "end")
        self.save_button.state(["disabled"])
        self.delete_button.state(["disabled"])

    def select_record(self, event=None):
        selection = self.table.selection()
        if not selection:
            return
        self.selected_index = int(selection[0])
        log = self.journal.logs[self.selected_index]
        for key, field in self.fields.items():
            value = str(getattr(log, key))
            if isinstance(field, ttk.Combobox):
                field.set(value)
            else:
                field.delete(0, "end")
                field.insert(0, value)
        self.save_button.state(["!disabled"])
        self.delete_button.state(["!disabled"])

    def apply_change(self, change):
        original_logs = list(self.journal.logs)
        try:
            change()
            self.on_change()
        except (ValueError, OSError) as error:
            self.journal.logs[:] = original_logs
            messagebox.showerror("Не удалось сохранить", str(error), parent=self.window)
            return
        self.refresh()

    def save_record(self):
        if self.selected_index is None:
            return
        values = {key: field.get() for key, field in self.fields.items()}
        values["log_date"] = values.pop("date")
        self.apply_change(lambda: self.journal.update_tempo_log(self.selected_index, **values))

    def delete_record(self):
        if self.selected_index is None:
            return
        if messagebox.askyesno("Удалить запись?", "Эта запись будет удалена из журнала.", parent=self.window):
            self.apply_change(lambda: self.journal.delete_tempo_log(self.selected_index))
