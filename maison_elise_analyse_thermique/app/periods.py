from calendar import monthrange
from datetime import datetime, timedelta


def validate_period(start: datetime, end: datetime):
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end must be timezone-aware")
    if end <= start:
        raise ValueError("end must be after start")


def previous_period(start: datetime, end: datetime):
    validate_period(start, end)
    duration = end - start
    return start - duration, start


def _shift_month(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + (value.month - 1) + months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def reference_period(start: datetime, end: datetime, compare: str):
    validate_period(start, end)
    aliases = {"previous_period":"previous_period","previous_day":"previous_day","j-1":"previous_day","previous_week":"previous_week","s-1":"previous_week","previous_month":"previous_month","m-1":"previous_month"}
    mode = aliases.get(compare.lower()) if isinstance(compare, str) else None
    if mode is None:
        raise ValueError("unsupported compare mode")
    if mode == "previous_period": return previous_period(start, end)
    if mode == "previous_day": return start - timedelta(days=1), end - timedelta(days=1)
    if mode == "previous_week": return start - timedelta(days=7), end - timedelta(days=7)
    return _shift_month(start, -1), _shift_month(end, -1)
