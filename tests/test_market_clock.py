"""Unit tests for ``app/services/market_clock.py`` — the nego time window."""
from datetime import datetime, timedelta

import pytest

from app.services.market_clock import is_nego_window, next_open_window

# 2026-10-26 is a Monday (weekday 0). Use it as the anchor.
_MON = datetime(2026, 10, 26)


def _at(h: int, m: int, day=_MON):
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


@pytest.mark.parametrize("h,m,expected", [
    (9, 54, False),
    (9, 55, True),
    (12, 29, True),
    (12, 30, False),   # end exclusive
    (12, 31, False),
    (14, 24, False),
    (14, 25, True),
    (16, 29, True),
    (16, 30, False),   # end exclusive
    (16, 31, False),
])
def test_nego_window_boundaries(h, m, expected):
    assert is_nego_window(_at(h, m)) is expected


def test_nego_window_closed_on_weekend():
    sat = _MON + timedelta(days=5)   # Saturday
    sun = _MON + timedelta(days=6)   # Sunday
    assert is_nego_window(sat.replace(hour=10, minute=0)) is False
    assert is_nego_window(sun.replace(hour=10, minute=0)) is False


def test_next_open_window_same_day():
    assert next_open_window(_at(9, 0)) == "เปิดอีกครั้ง 09:55"
    assert next_open_window(_at(13, 0)) == "เปิดอีกครั้ง 14:25"


def test_next_open_window_after_close_rolls_to_tomorrow():
    assert next_open_window(_at(16, 45)) == "พรุ่งนี้ 09:55"
    # Friday after close -> Monday (not Saturday).
    fri = _MON + timedelta(days=4)
    assert next_open_window(fri.replace(hour=17, minute=0)) == "พรุ่งนี้ 09:55"
