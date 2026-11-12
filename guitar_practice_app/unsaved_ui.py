"""Explicit save/discard/cancel choice for attempts that have not been logged."""

import tkinter as tk
from tkinter import ttk


def ask_unsaved_attempts(parent, closing=False):
    window = tk.Toplevel(parent)
    window.title("Несохранённые попытки")
    window.transient(parent)
    window.resizable(False, False)
    answer = None

    def choose(value):
        nonlocal answer
        answer = value
        window.destroy()

    ttk.Label(window, text="Сохранить результат текущего темпа?", padding=12).pack()
    buttons = ttk.Frame(window, padding=8)
    buttons.pack()
    for title, value in (("Сохранить результат", "save"),
                         ("Выйти без сохранения" if closing else "Сбросить попытки", "discard"),
                         ("Отмена", None)):
        ttk.Button(buttons, text=title, command=lambda value=value: choose(value)).pack(side="left", padx=4)
    window.protocol("WM_DELETE_WINDOW", lambda: choose(None))
    window.grab_set()
    parent.wait_window(window)
    return answer
