"""Stability tables and correction of individual source attempts."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from guitar_practice_app.stability import TRANSITION_NOTICE
from guitar_practice_app.storage import atomic_write_json
from guitar_practice_app.tempo import duration_label


def export_stability(path, journal, exercise, session_id=None, protected_path=None):
    path = Path(path)
    if protected_path is not None and path.resolve() == Path(protected_path).resolve():
        raise ValueError("Экспорт не должен перезаписывать личный журнал.")
    atomic_write_json(path, journal.stability_export(exercise, session_id))


class StabilityWindow:
    def __init__(self, parent, journal, exercise, practice, save, on_change, protected_path=None):
        self.journal, self.exercise, self.practice = journal, exercise, practice
        self.save, self.on_change = save, on_change
        self.protected_path = protected_path
        self.window = tk.Toplevel(parent)
        self.window.title(f"Стабильность: {exercise}")
        self.window.geometry("1120x640")
        self.window.minsize(950, 550)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(2, weight=1)
        controls = ttk.Frame(self.window)
        controls.grid(row=0, column=0, sticky="ew", padx=8, pady=4)
        ttk.Label(controls, text="Область:").pack(side="left")
        self.scope = ttk.Combobox(controls, state="readonly", width=25)
        self.scope.pack(side="left", padx=4)
        self.scope.bind("<<ComboboxSelected>>", lambda event: self.refresh())
        ttk.Button(controls, text="Новый фрагмент", command=self.create_fragment).pack(side="left", padx=2)
        ttk.Button(controls, text="Переименовать", command=self.rename_fragment).pack(side="left", padx=2)
        ttk.Label(controls, text="Окно:").pack(side="left", padx=(12, 2))
        self.size = ttk.Spinbox(controls, from_=10, to=1000, width=5)
        self.size.set(str(journal.settings["stability_window"]))
        self.size.pack(side="left")
        ttk.Button(controls, text="Применить", command=self.change_window).pack(side="left", padx=4)
        ttk.Button(controls, text="JSON", command=self.export).pack(side="right")
        ttk.Label(self.window, text=TRANSITION_NOTICE + " Историческая оценка с 14.11 — по всем агрегатам, не окно последних N.", wraplength=1080).grid(
            row=1, column=0, sticky="w", padx=12, pady=4)
        tabs = ttk.Notebook(self.window)
        tabs.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        exact = ttk.Frame(tabs)
        historical = ttk.Frame(tabs)
        tabs.add(exact, text="Точное окно и текущая отработка")
        tabs.add(historical, text="Исторические агрегаты (не входят в окно)")
        self.table = self.create_table(exact, (
            ("tempo", "BPM", 65), ("duration", "Длит.", 60), ("count", "Удачные / всего", 115),
            ("percent", "Успех", 70), ("last", "Последняя попытка", 200),
            ("status", "Статус", 230), ("current", "Текущая отработка", 155),
            ("historical", "Историческая оценка с 14.11", 215),
        ))
        self.historical = self.create_table(historical, (
            ("date", "Дата", 110), ("tempo", "Темп", 110), ("count", "Удачные / всего", 130),
            ("session", "Отработка", 300),
        ))
        footer = ttk.Frame(self.window)
        footer.grid(row=3, column=0, sticky="ew", padx=8, pady=4)
        ttk.Button(footer, text="Все попытки выбранного темпа", command=self.open_attempts).pack(side="left")
        ttk.Button(footer, text="Закрыть", command=self.window.destroy).pack(side="right")
        ttk.Label(self.window, text="«Повышение разрешено» — не рекомендация повышать. Учитывайте комфорт, усталость и указания преподавателя.",
                  wraplength=1080).grid(row=4, column=0, sticky="w", padx=12, pady=4)
        self.scope_ids = [""]
        self.refresh()

    @staticmethod
    def create_table(parent, columns):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        table = ttk.Treeview(parent, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        table.grid(row=0, column=0, sticky="nsew")
        for key, title, width in columns:
            table.heading(key, text=title)
            table.column(key, width=width, minwidth=55)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(parent, orient="horizontal", command=table.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        table.configure(yscrollcommand=scroll.set, xscrollcommand=x_scroll.set)
        return table

    def scope_id(self):
        index = self.scope.current()
        return self.scope_ids[index] if 0 <= index < len(self.scope_ids) else ""

    def refresh(self):
        selected = self.scope_id()
        fragments = self.journal.fragments_for(self.exercise)
        self.scope_ids = [""] + [f.id for f in fragments]
        self.scope["values"] = ["Целое упражнение"] + [f.name for f in fragments]
        self.scope.current(self.scope_ids.index(selected) if selected in self.scope_ids else 0)
        scope = self.scope_id()
        self.table.delete(*self.table.get_children())
        self.groups = self.journal.stability_groups(self.exercise, scope)
        for index, (tempo, duration) in enumerate(self.groups):
            stats = self.journal.stability(self.exercise, tempo, duration, scope, self.practice.session_id)
            attempts = self.journal.group_attempts(self.exercise, tempo, duration, scope, eligible_only=False)
            last = attempts[-1].recorded_at if attempts else "—"
            current = stats.current_attempts
            estimate = self.journal.historical_estimate(self.exercise, tempo, duration, scope)
            historical_text = (f"{estimate['successes']} / {estimate['total']} · {estimate['percent']:.1f}%"
                               if estimate["total"] else "—")
            current_text = (f"{sum(a.success for a in current)} / {len(current)} · "
                            f"{sum(a.success for a in current) * 100 / len(current):.1f}%") if current else (
                                "0 / 0" if self.practice.session is not None and self.practice.session.exercise == self.exercise else "—")
            self.table.insert("", "end", iid=str(index), values=(
                tempo, duration_label(duration), f"{stats.successes} / {stats.total}",
                f"{stats.percent:.1f}%" if stats.percent is not None else "—",
                last, stats.status, current_text, historical_text,
            ))
        self.historical.delete(*self.historical.get_children())
        for log in self.journal.logs:
            if log.exercise == self.exercise and log.scope_id == scope and not log.exact:
                self.historical.insert("", "end", values=(
                    log.date, self.journal.format_tempo(log), f"{log.success} / {log.success + log.fail}", log.session_id))

    def apply_change(self, change):
        snapshot = self.journal.snapshot()
        try:
            change()
            self.save()
        except (ValueError, OSError) as error:
            self.journal.restore(snapshot)
            messagebox.showerror("Не удалось сохранить", str(error), parent=self.window)
            return False
        self.on_change()
        self.refresh()
        return True

    def change_window(self):
        if not self.apply_change(lambda: self.journal.set_window_size(self.size.get())):
            self.size.set(str(self.journal.settings["stability_window"]))

    def create_fragment(self):
        name = simpledialog.askstring("Новый фрагмент", "Название:", parent=self.window)
        if name is not None:
            self.apply_change(lambda: self.journal.save_fragment(self.exercise, name))

    def rename_fragment(self):
        scope_id = self.scope_id()
        if not scope_id:
            messagebox.showinfo("Фрагмент", "Выберите именованный фрагмент.", parent=self.window)
            return
        name = simpledialog.askstring("Переименовать", "Название:", parent=self.window,
                                      initialvalue=self.journal.scope_name(self.exercise, scope_id))
        if name is not None:
            self.apply_change(lambda: self.journal.save_fragment(self.exercise, name, scope_id))

    def open_attempts(self):
        selection = self.table.selection()
        if not selection:
            return
        tempo, duration = self.groups[int(selection[0])]
        attempts = AttemptWindow(self.window, self, tempo, duration, self.scope_id())
        self.window.wait_window(attempts.window)
        self.window.grab_set()
        self.refresh()

    def export(self):
        filename = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json",
                                              initialfile="stability-export.json", filetypes=[("JSON", "*.json")])
        if not filename:
            return
        try:
            export_stability(filename, self.journal, self.exercise, self.practice.session_id, self.protected_path)
        except (ValueError, OSError) as error:
            messagebox.showerror("Экспорт", str(error), parent=self.window)
            return
        messagebox.showinfo("Экспорт", "JSON сохранён.", parent=self.window)


class AttemptWindow:
    def __init__(self, parent, owner, tempo, duration, scope_id):
        self.owner, self.tempo, self.duration, self.scope_id = owner, tempo, duration, scope_id
        self.window = tk.Toplevel(parent)
        self.window.title(f"Все попытки: {tempo} / {duration_label(duration)}")
        self.window.geometry("850x480")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        frame = ttk.Frame(self.window)
        frame.grid(row=0, column=0, sticky="nsew")
        self.table = StabilityWindow.create_table(frame, (
            ("sequence", "Порядок", 75), ("time", "Реальное время", 230),
            ("success", "Результат", 100), ("session", "Отработка", 280),
        ))
        buttons = ttk.Frame(self.window)
        buttons.grid(row=1, column=0, sticky="ew")
        ttk.Button(buttons, text="Отметить удачной", command=lambda: self.correct(True)).pack(side="left", padx=4)
        ttk.Button(buttons, text="Отметить неудачной", command=lambda: self.correct(False)).pack(side="left", padx=4)
        ttk.Button(buttons, text="Удалить", command=self.delete).pack(side="left", padx=4)
        ttk.Button(buttons, text="Закрыть", command=self.window.destroy).pack(side="right", padx=4)
        self.refresh()

    def refresh(self):
        self.table.delete(*self.table.get_children())
        attempts = self.owner.journal.group_attempts(self.owner.exercise, self.tempo, self.duration,
                                                     self.scope_id, eligible_only=False)
        for attempt in reversed(attempts):
            self.table.insert("", "end", iid=attempt.id, values=(
                attempt.sequence, attempt.recorded_at, "Удачно" if attempt.success else "Неудачно", attempt.session_id))

    def selected_id(self):
        selection = self.table.selection()
        return selection[0] if selection else None

    def correct(self, success):
        attempt_id = self.selected_id()
        if attempt_id and self.owner.apply_change(lambda: self.owner.journal.correct_attempt(attempt_id, success)):
            self.refresh()

    def delete(self):
        attempt_id = self.selected_id()
        if attempt_id and messagebox.askyesno("Удалить попытку?", "Удалить исходную попытку с пересчётом статистики?",
                                              parent=self.window):
            if self.owner.apply_change(lambda: self.owner.journal.delete_attempt(attempt_id)):
                self.refresh()
