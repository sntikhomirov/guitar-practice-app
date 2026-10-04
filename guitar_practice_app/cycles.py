"""Weekly practice cycles run from Wednesday through Tuesday."""

from datetime import date, timedelta


def cycle_start(as_of=None):
    as_of = as_of or date.today()
    return as_of - timedelta(days=(as_of.weekday() - 2) % 7)


def cycle_end(as_of=None):
    return cycle_start(as_of) + timedelta(days=6)
