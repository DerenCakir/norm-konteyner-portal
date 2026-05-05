"""Small performance helpers for Streamlit page load timing."""

from __future__ import annotations

import logging
from time import perf_counter


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("norm_portal.performance")


class PageTimer:
    """Log page render duration to the application logs."""

    def __init__(self, page_name: str) -> None:
        self.page_name = page_name
        self.started_at = perf_counter()

    def finish(self) -> None:
        elapsed_ms = (perf_counter() - self.started_at) * 1000
        logger.info("page_render_ms page=%s duration=%.1f", self.page_name, elapsed_ms)


def page_timer(page_name: str) -> PageTimer:
    return PageTimer(page_name)
