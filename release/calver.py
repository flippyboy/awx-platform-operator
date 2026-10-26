"""Calendar versions for operator and chart releases.

Format is ``YYYY.MM.DD`` (zero-padded month and day): the UTC date of the cut.
A later cut the same day appends ``-N``, starting at 1:

    2026.10.26
    2026.10.26-1
    2026.10.26-2

Git tags keep a leading ``v`` (``v2026.10.26``). Image tags, the chart
``version``, and ``appVersion`` do not. The published ``0.1.x`` tags are the
last semver cuts.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

_CALVER_RE = re.compile(
    r"^(?P<year>\d{4})\.(?P<month>0[1-9]|1[0-2])\.(?P<day>0[1-9]|[12]\d|3[01])"
    r"(?:-(?P<micro>[1-9]\d*))?$"
)


def parse(version: str) -> tuple[date, int | None] | None:
    """Return ``(day, micro)`` or ``None``. ``micro`` is ``None`` when omitted."""
    text = (version or "").strip()
    if text.startswith("v"):
        text = text[1:]
    match = _CALVER_RE.fullmatch(text)
    if not match:
        return None
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    try:
        on = date(year, month, day)
    except ValueError:
        return None
    micro = match.group("micro")
    return on, int(micro) if micro else None


def is_calver(version: str) -> bool:
    return parse(version) is not None


def format_calver(day: date, micro: int | None = None) -> str:
    base = f"{day.year:04d}.{day.month:02d}.{day.day:02d}"
    if micro is None:
        return base
    if micro < 1:
        raise ValueError("micro starts at 1")
    return f"{base}-{micro}"


def utc_today(now: datetime | None = None) -> date:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).date()


def next_version(current: str, *, today: date | None = None) -> str:
    """Next operator version.

    A new UTC day starts at ``YYYY.MM.DD``. Another cut that day uses ``-1``,
    ``-2``, and so on. A non-calendar current version (the old ``0.1.x`` tags)
    starts that new day with no micro.
    """
    day = today or utc_today()
    parsed = parse(current)
    if parsed is not None and parsed[0] == day:
        micro = 1 if parsed[1] is None else parsed[1] + 1
        return format_calver(day, micro)
    return format_calver(day)
