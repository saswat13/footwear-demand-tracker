import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from build_13w_forecast import build_13w_forecast
from build_signal_mart import build_signal_mart


def sample_clean():
    weeks = pd.date_range("2024-01-07", periods=110, freq="W-SUN")
    rows = []
    for i, week in enumerate(weeks):
        rows.append([week, "Footwear", "Running Shoes", "Nike", "nike running shoes", "brand_category", "US", 50 + i * 0.1, 50 + i * 0.1, 50 + i * 0.1, 50 + i * 0.1, 0, 0, "ts", 1, "running shoes", "OK"])
        rows.append([week, "Footwear", "Running Shoes", "Hoka", "hoka running shoes", "brand_category", "US", 25 + i * 0.1, 25 + i * 0.1, 25 + i * 0.1, 25 + i * 0.1, 0, 0, "ts", 1, "running shoes", "OK"])
    return pd.DataFrame(rows, columns=["week_start_sunday", "segment", "category", "brand", "keyword", "keyword_type", "geo", "raw_interest", "adjusted_interest", "interest_4wk_avg", "interest_13wk_avg", "wow_change_pct", "yoy_change_pct", "pull_ts", "batch_id", "anchor_keyword", "data_quality_flag"])


def test_signal_mart_indexes_and_features(tmp_path, monkeypatch):
    monkeypatch.setattr("build_signal_mart.SIGNAL_OUTPUT", tmp_path / "weekly_brand_category_signal.parquet")
    monkeypatch.setattr("build_signal_mart.FEATURE_OUTPUT", tmp_path / "model_weekly_demand_features.parquet")
    mart, features = build_signal_mart(sample_clean())
    latest = mart[mart["week_start_sunday"] == mart["week_start_sunday"].max()]
    assert latest.loc[latest["brand"] == "Nike", "demand_signal_index"].iloc[0] == 100
    assert latest.loc[latest["brand"] == "Hoka", "rank_in_category"].iloc[0] == 2
    assert {"signal_lag_1w", "is_new_year_fitness_window", "is_black_friday_window"}.issubset(features.columns)


def test_13w_forecast_thursday_issue_date(tmp_path, monkeypatch):
    signal_path = tmp_path / "weekly_brand_category_signal.parquet"
    forecast_path = tmp_path / "weekly_brand_category_forecast_13w.parquet"
    monkeypatch.setattr("build_signal_mart.SIGNAL_OUTPUT", signal_path)
    monkeypatch.setattr("build_signal_mart.FEATURE_OUTPUT", tmp_path / "features.parquet")
    monkeypatch.setattr("build_13w_forecast.SIGNAL_INPUT", signal_path)
    monkeypatch.setattr("build_13w_forecast.FORECAST_OUTPUT", forecast_path)
    build_signal_mart(sample_clean())
    forecast = build_13w_forecast("2026-07-09")
    groups = forecast.groupby(["forecast_issue_date", "segment", "category", "brand"]).size()
    assert (groups == 13).all()
    assert forecast["forecast_start_week_sunday"].dt.date.astype(str).unique().tolist() == ["2026-07-12"]
    assert set(forecast["horizon_week"].unique()) == set(range(1, 14))
    assert "forecast_week_start_sunday" in forecast.columns


def test_13w_forecast_archive_appends_and_replaces_issue_dates(tmp_path, monkeypatch):
    signal_path = tmp_path / "weekly_brand_category_signal.parquet"
    forecast_path = tmp_path / "weekly_brand_category_forecast_13w.parquet"
    monkeypatch.setattr("build_signal_mart.SIGNAL_OUTPUT", signal_path)
    monkeypatch.setattr("build_signal_mart.FEATURE_OUTPUT", tmp_path / "features.parquet")
    monkeypatch.setattr("build_13w_forecast.SIGNAL_INPUT", signal_path)
    monkeypatch.setattr("build_13w_forecast.FORECAST_OUTPUT", forecast_path)

    build_signal_mart(sample_clean())
    build_13w_forecast("2026-07-09")
    build_13w_forecast("2026-07-16")
    archive = pd.read_parquet(forecast_path)
    assert sorted(pd.to_datetime(archive["forecast_issue_date"]).dt.date.astype(str).unique()) == [
        "2026-07-09",
        "2026-07-16",
    ]
    assert len(archive) == 52

    build_13w_forecast("2026-07-16")
    rerun_archive = pd.read_parquet(forecast_path)
    assert len(rerun_archive) == 52
    groups = rerun_archive.groupby(["forecast_issue_date", "segment", "category", "brand"]).size()
    assert (groups == 13).all()
