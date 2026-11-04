from dataclasses import asdict, dataclass
from datetime import date
from typing import Optional

from guitar_practice_app.cycles import cycle_start
from guitar_practice_app.tempo import DURATION_FACTORS


def validate_goal(tempo, duration):
    if tempo is None:
        if duration:
            raise ValueError("Укажите темп цели вместе с длительностью.")
        return
    if type(tempo) is not int or tempo <= 0:
        raise ValueError("Целевой темп должен быть положительным целым числом.")
    if duration not in DURATION_FACTORS:
        raise ValueError("Выберите длительность цели из списка.")


@dataclass(frozen=True)
class WeeklyGoal:
    week_start: str
    tempo: int
    duration: str

    def __post_init__(self):
        start = date.fromisoformat(self.week_start)
        object.__setattr__(self, "week_start", start.isoformat())
        if start.weekday() != 2:
            raise ValueError("Цикл недельной цели должен начинаться в среду.")
        if self.tempo is None:
            raise ValueError("Укажите темп недельной цели.")
        validate_goal(self.tempo, self.duration)


@dataclass(frozen=True)
class Exercise:
    name: str
    description: str = ""
    target_tempo: Optional[int] = None
    target_duration: str = ""
    target_week_start: str = ""
    weekly_goals: tuple = ()
    total_target_tempo: Optional[int] = None
    total_target_duration: str = ""
    archived: bool = False

    def __post_init__(self):
        if type(self.archived) is not bool:
            raise ValueError("Статус архива должен быть логическим значением.")
        validate_goal(self.target_tempo, self.target_duration)
        validate_goal(self.total_target_tempo, self.total_target_duration)
        if self.target_tempo is not None:
            start = self.target_week_start or cycle_start().isoformat()
            object.__setattr__(self, "target_week_start", start)
            goal = WeeklyGoal(start, self.target_tempo, self.target_duration)
            goals = tuple(item for item in self.weekly_goals if item.week_start != start) + (goal,)
            object.__setattr__(self, "weekly_goals", goals)

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            target_tempo=data.get("target_tempo"),
            target_duration=data.get("target_duration", ""),
            target_week_start=data.get("target_week_start", ""),
            weekly_goals=tuple(WeeklyGoal(**item) for item in data.get("weekly_goals", [])),
            total_target_tempo=data.get("total_target_tempo"),
            total_target_duration=data.get("total_target_duration", ""),
            archived=data.get("archived", False),
        )

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class GoalProgress:
    exercise: Exercise
    maximum_text: str
    maximum_normalized: int
    target_normalized: Optional[int]
    target_tempo: Optional[int] = None
    target_duration: str = ""
    week_start: str = ""

    @property
    def percent(self):
        if self.target_normalized is None:
            return None
        return min(100.0, self.maximum_normalized * 100 / self.target_normalized)

    @property
    def reached(self):
        return (self.target_normalized is not None
                and self.maximum_normalized >= self.target_normalized)


@dataclass(frozen=True)
class TempoLog:
    exercise: str
    tempo: int
    duration: str
    date: str
    success: int = 0
    fail: int = 0

    @classmethod
    def from_dict(cls, data):
        return cls(
            exercise=data.get("exercise", ""),
            tempo=int(data.get("tempo", 0)),
            duration=data.get("duration", ""),
            date=data.get("date", ""),
            success=int(data.get("success", 0)),
            fail=int(data.get("fail", 0)),
        )

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class PracticePlanItem:
    exercise: str
    weekly_practice_count: int
    max_tempo: str
    max_normalized_tempo: int
    last_tempo: str
    start_tempo: Optional[int]
    start_duration: str
    last_date: str
