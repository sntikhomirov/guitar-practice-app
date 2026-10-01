from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Exercise:
    name: str
    description: str = ""

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
        )

    def to_dict(self):
        return asdict(self)


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
