from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class BridgeMetrics:
    upstream_audio_count: int = 0
    upstream_text_count: int = 0
    upstream_bytes_total: int = 0
    downstream_audio_count: int = 0
    downstream_text_count: int = 0
    downstream_bytes_total: int = 0
    errors: int = 0
    start_time: float = field(default_factory=time.monotonic)

    def record_upstream_audio(self, size: int) -> None:
        self.upstream_audio_count += 1
        self.upstream_bytes_total += size

    def record_upstream_text(self) -> None:
        self.upstream_text_count += 1

    def record_downstream_audio(self, size: int) -> None:
        self.downstream_audio_count += 1
        self.downstream_bytes_total += size

    def record_downstream_text(self) -> None:
        self.downstream_text_count += 1

    def record_error(self) -> None:
        self.errors += 1

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.start_time

    def snapshot(self) -> dict[str, int | float]:
        return {
            "upstream_audio_count": self.upstream_audio_count,
            "upstream_text_count": self.upstream_text_count,
            "upstream_bytes_total": self.upstream_bytes_total,
            "downstream_audio_count": self.downstream_audio_count,
            "downstream_text_count": self.downstream_text_count,
            "downstream_bytes_total": self.downstream_bytes_total,
            "errors": self.errors,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }
