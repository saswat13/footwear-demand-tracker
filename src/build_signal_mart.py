from __future__ import annotations

import logging

import pandas as pd

from utils import CLEAN_DIR, MART_DIR, ensure_directories, pct_change

SIGNAL_OUTPUT = MART_DIR / "weekly_brand_category_signal.parquet"
FEATURE_OUTPUT = MART_DIR / "model_weekly_demand_features.parquet"


def momentum_label(value: float) -> str:
    if pd.isna(value):
        return "Stable"
    if value >= 10:
        return "Rising"
    if value <= -10:
        return "Falling"
    return "Stable"


def build_confidence(history_count: int, quality_flag: str) -> str:
    if quality_flag == "OK" and history_count >= 104:
        return "High"
    if history_count >= 52:
        return "Medium"
    return "Low"


def build_model_features(mart: pd.DataFrame) -> pd.DataFrame:
    features = mart.sort_values(["segment", "category", "brand", "week_start_sunday"]).copy()
    group_cols = ["segment", "category", "brand"]
    grouped = features.groupby(group_cols, dropna=False)["demand_signal_index"]
    features["signal_t"] = features["demand_signal_index"]
    features["signal_lag_1w"] = grouped.shift(1)
    features["signal_lag_4w"] = grouped.shift(4)
    features["signal_4wk_avg"] = grouped.transform(lambda s: s.rolling(4, min_periods=1).mean())
    features["signal_13wk_avg"] = grouped.transform(lambda s: s.rolling(13, min_periods=1).mean())
    features["wow_change_pct"] = pct_change(features["signal_t"], features["signal_lag_1w"])
    features["yoy_change_pct"] = pct_change(features["signal_t"], grouped.shift(52))
    features["week_of_year"] = features["week_start_sunday"].dt.isocalendar().week.astype(int)
    features["month"] = features["week_start_sunday"].dt.month
    features["quarter"] = features["week_start_sunday"].dt.quarter
    features["is_new_year_fitness_window"] = features["month"].eq(1)
    features["is_spring_running_window"] = features["month"].between(3, 5)
    features["is_back_to_school_window"] = features["month"].eq(8) | (features["month"].eq(9) & features["week_start_sunday"].dt.day.le(10))
    features["is_black_friday_window"] = features["month"].eq(11) & features["week_start_sunday"].dt.day.ge(15)
    return features[["week_start_sunday", "segment", "category", "brand", "signal_t", "signal_lag_1w", "signal_lag_4w", "signal_4wk_avg", "signal_13wk_avg", "wow_change_pct", "yoy_change_pct", "week_of_year", "month", "quarter", "is_new_year_fitness_window", "is_spring_running_window", "is_back_to_school_window", "is_black_friday_window"]]


def build_signal_mart(clean: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    ensure_directories()
    clean = pd.read_parquet(CLEAN_DIR / "weekly_keyword_trends.parquet") if clean is None else clean.copy()
    clean["week_start_sunday"] = pd.to_datetime(clean["week_start_sunday"])
    brand_rows = clean[clean["keyword_type"] == "brand_category"].copy()
    brand_rows["base_signal"] = brand_rows["interest_4wk_avg"]
    keys = ["week_start_sunday", "segment", "category", "brand"]
    mart = brand_rows.groupby(keys, as_index=False).agg(base_signal=("base_signal", "mean"), wow_change_pct=("wow_change_pct", "mean"), yoy_change_pct=("yoy_change_pct", "mean"), data_quality_flag=("data_quality_flag", lambda s: "OK" if (s == "OK").all() else s.iloc[-1])).sort_values(keys)
    week_category = mart.groupby(["week_start_sunday", "category"])
    mart["demand_signal_index"] = 100 * mart["base_signal"] / week_category["base_signal"].transform("max")
    mart["category_share_signal"] = mart["base_signal"] / week_category["base_signal"].transform("sum")
    mart["rank_in_category"] = week_category["base_signal"].rank(method="dense", ascending=False).astype("Int64")
    history = mart["base_signal"].notna().groupby([mart["segment"], mart["category"], mart["brand"]]).cumsum()
    mart["momentum_label"] = mart["wow_change_pct"].apply(momentum_label)
    mart["confidence_label"] = [build_confidence(int(count), flag) for count, flag in zip(history, mart["data_quality_flag"])]
    mart = mart[["week_start_sunday", "segment", "category", "brand", "base_signal", "demand_signal_index", "wow_change_pct", "yoy_change_pct", "category_share_signal", "rank_in_category", "momentum_label", "confidence_label", "data_quality_flag"]].sort_values(["week_start_sunday", "category", "rank_in_category"])
    mart.to_parquet(SIGNAL_OUTPUT, index=False)
    features = build_model_features(mart)
    features.to_parquet(FEATURE_OUTPUT, index=False)
    return mart, features


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    mart, features = build_signal_mart()
    logging.info("Wrote %s signal rows to %s", len(mart), SIGNAL_OUTPUT)
    logging.info("Wrote %s feature rows to %s", len(features), FEATURE_OUTPUT)


if __name__ == "__main__":
    main()
