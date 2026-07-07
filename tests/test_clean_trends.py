import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from build_clean_trends import build_clean_trends
from utils import convert_to_sunday_week, get_next_sunday


def test_get_next_sunday_for_thursday_and_sunday():
    assert get_next_sunday("2026-07-09").isoformat() == "2026-07-12"
    assert get_next_sunday("2026-07-12").isoformat() == "2026-07-12"


def test_convert_to_sunday_week():
    dates = pd.Series(pd.to_datetime(["2026-07-09", "2026-07-12", "2026-07-18"]))
    converted = convert_to_sunday_week(dates)
    assert converted.dt.date.astype(str).tolist() == ["2026-07-05", "2026-07-12", "2026-07-12"]


def test_anchor_normalization_drops_duplicate_anchor(tmp_path, monkeypatch):
    monkeypatch.setattr("build_clean_trends.CLEAN_OUTPUT", tmp_path / "weekly_keyword_trends.parquet")
    raw = pd.DataFrame([
        ["1", "2026-01-01T00:00:00Z", "2026-01-01", "Footwear", "Running Shoes", "Generic", "running shoes", "generic_category", "US", "today 5-y", 1, "running shoes", "2026-01-04", 80, False],
        ["1", "2026-01-01T00:00:00Z", "2026-01-01", "Footwear", "Running Shoes", "Nike", "nike running shoes", "brand_category", "US", "today 5-y", 1, "running shoes", "2026-01-04", 40, False],
        ["1", "2026-01-01T00:00:00Z", "2026-01-01", "Footwear", "Running Shoes", "Generic", "running shoes", "generic_category", "US", "today 5-y", 2, "running shoes", "2026-01-04", 40, False],
        ["1", "2026-01-01T00:00:00Z", "2026-01-01", "Footwear", "Running Shoes", "Hoka", "hoka running shoes", "brand_category", "US", "today 5-y", 2, "running shoes", "2026-01-04", 20, False],
    ], columns=["pull_id", "pull_ts", "pull_date", "segment", "category", "brand", "keyword", "keyword_type", "geo", "timeframe", "batch_id", "anchor_keyword", "date", "raw_interest", "is_partial"])
    clean = build_clean_trends(raw)
    assert "week_start_sunday" in clean.columns
    assert len(clean[clean["keyword"] == "running shoes"]) == 1
    assert clean.loc[clean["keyword"] == "hoka running shoes", "adjusted_interest"].iloc[0] == 40
