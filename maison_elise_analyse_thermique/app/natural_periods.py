from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


def _day_start(value: datetime) -> datetime:
    return datetime.combine(value.date(), time.min, tzinfo=value.tzinfo)


def resolve_natural_period(text: str, now: datetime, timezone: str = "Europe/Paris") -> tuple[datetime, datetime]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("period text must be non-empty")
    tz = ZoneInfo(timezone)
    local_now = now.astimezone(tz) if now.tzinfo is not None else now.replace(tzinfo=tz)
    today = _day_start(local_now)
    phrase = " ".join(text.lower().strip().split())
    if phrase in {"aujourd'hui", "aujourdhui"}: return today, local_now
    if phrase == "hier":
        start = today - timedelta(days=1); return start, today
    if phrase in {"cette semaine", "semaine en cours"}:
        start = today - timedelta(days=today.weekday()); return start, local_now
    if phrase == "semaine dernière":
        end = today - timedelta(days=today.weekday()); return end - timedelta(days=7), end
    if phrase in {"ce mois", "mois en cours"}:
        return today.replace(day=1), local_now
    if phrase == "mois dernier":
        end = today.replace(day=1); previous_month_end = end - timedelta(days=1); return previous_month_end.replace(day=1), end
    match = re.fullmatch(r"(?:les )?(\d{1,3}) derniers jours", phrase)
    if match:
        days = int(match.group(1))
        if not 1 <= days <= 366: raise ValueError("number of days must be between 1 and 366")
        return local_now - timedelta(days=days), local_now
    if phrase in {"dernières 24 heures", "dernieres 24 heures", "24 dernières heures", "24 dernieres heures"}:
        return local_now - timedelta(hours=24), local_now
    raise ValueError("unsupported natural period")
