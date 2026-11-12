"""HTTP request and response processing middleware."""

import time
from typing import Callable, Any, Dict


class TimingMiddleware:
    """Track and record request execution durations."""

    def __init__(self, slow_threshold_seconds: float = 0.5) -> None:
        self.slow_threshold = slow_threshold_seconds
        self.recorded_stats: Dict[str, float] = {}

    def before_request(self) -> float:
        """Capture incoming request start timestamp."""
        return time.perf_counter()

    def after_request(self, endpoint: str, start_time: float) -> float:
        """Compute duration and log warnings for slow routes."""
        elapsed = time.perf_counter() - start_time
        self.recorded_stats[endpoint] = round(elapsed, 4)
        return elapsed

    def wrap_handler(self, endpoint: str, handler: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap an execution function with timing metrics."""
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            start = self.before_request()
            try:
                return handler(*args, **kwargs)
            finally:
                self.after_request(endpoint, start)
        return wrapped
