from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import re

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
RAW_TRENDS_DIR = PROJECT_ROOT / "data" / "raw" / "google_trends"
CLEAN_DIR = PROJECT_ROOT / "data" / "clean"
MART_DIR = PROJECT_ROOT / "data" / "mart"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "unknown"


def ensure_directories() -> None:
    for path in [RAW_TRENDS_DIR, CLEAN_DIR, MART_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def read_active_config() -> tuple[pd.DataFrame, pd.DataFrame]:
    categories = pd.read_csv(CONFIG_DIR / "categories.csv")
    keywords = pd.read_csv(CONFIG_DIR / "keywords.csv")
    categories["active"] = categories["active"].astype(str).str.lower().eq("true")
    keywords["active"] = keywords["active"].astype(str).str.lower().eq("true")
    return categories[categories["active"]].copy(), keywords[keywords["active"]].copy()


def latest_pull_dir(raw_dir: Path = RAW_TRENDS_DIR) -> Path | None:
    if not raw_dir.exists():
        return None
    pull_dirs = sorted([p for p in raw_dir.glob("pull_date=*") if p.is_dir()])
    return pull_dirs[-1] if pull_dirs else None


def get_next_sunday(report_date: date | datetime | str) -> date:
    if isinstance(report_date, str):
        report_date = pd.to_datetime(report_date).date()
    elif isinstance(report_date, datetime):
        report_date = report_date.date()
    days_until_sunday = (6 - report_date.weekday()) % 7
    return report_date + timedelta(days=days_until_sunday)


def convert_to_sunday_week(date_col):
    dates = pd.to_datetime(date_col)
    return (dates - pd.to_timedelta((dates.dt.weekday + 1) % 7, unit="D")).dt.normalize()


def pct_change(current: pd.Series, previous: pd.Series) -> pd.Series:
    previous = previous.replace({0: pd.NA})
    return ((current - previous) / previous) * 100
