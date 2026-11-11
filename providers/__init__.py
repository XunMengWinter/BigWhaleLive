"""Provider boundaries and content-free call diagnostics."""
from dataclasses import asdict, dataclass


@dataclass
class CallStats:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    cancelled: int = 0
    last_ms: float | None = None
    last_http_status: int | None = None

    def finish(self, outcome, elapsed):
        setattr(self, outcome, getattr(self, outcome) + 1)
        self.last_ms = round(elapsed * 1000, 1)

    def snapshot(self):
        return asdict(self)
