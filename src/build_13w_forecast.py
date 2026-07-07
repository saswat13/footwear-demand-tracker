from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

import pandas as pd

from utils import MART_DIR, ensure_directories, get_next_sunday

SIGNAL_INPUT = MART_DIR / "weekly_brand_category_signal.parquet"
FORECAST_OUTPUT = MART_DIR / "weekly_brand_category_forecast_13w.parquet"
FORECAST_METHOD = "blended_recent_seasonal_baseline_v1"
FORECAST_KEYS = ["forecast_issue_date", "forecast_week_start_sunday", "segment", "category", "brand"]


def band_pct(confidence_label: str) -> float:
    return {"High": 0.10, "Medium": 0.20}.get(confidence_label, 0.35)


def append_forecast_archive(new_forecast: pd.DataFrame, output_path=None) -> pd.DataFrame:
    output_path = FORECAST_OUTPUT if output_path is None else output_path
    new_forecast = new_forecast.copy()
    new_forecast["forecast_issue_date"] = pd.to_datetime(new_forecast["forecast_issue_date"]).dt.date

    if output_path.exists():
        existing = pd.read_parquet(output_path)
        existing["forecast_issue_date"] = pd.to_datetime(existing["forecast_issue_date"]).dt.date
        issue_dates = set(new_forecast["forecast_issue_date"])
        existing = existing[~existing["forecast_issue_date"].isin(issue_dates)].copy()
        archive = pd.concat([existing, new_forecast], ignore_index=True)
    else:
        archive = new_forecast

    archive = archive.drop_duplicates(FORECAST_KEYS, keep="last")
    archive = archive.sort_values(["forecast_issue_date", "category", "brand", "horizon_week"])
    archive.to_parquet(output_path, index=False)
    return archive


def build_13w_forecast(
    forecast_issue_date: str | None = None,
    signal: pd.DataFrame | None = None,
    append_archive: bool = True,
) -> pd.DataFrame:
    ensure_directories()
    issue_ts = datetime.now(timezone.utc).isoformat()
    issue_date = pd.to_datetime(forecast_issue_date).date() if forecast_issue_date else datetime.now().date()
    start_sunday = get_next_sunday(issue_date)
    signal = pd.read_parquet(SIGNAL_INPUT) if signal is None else signal.copy()
    signal["week_start_sunday"] = pd.to_datetime(signal["week_start_sunday"])
    latest_week = signal["week_start_sunday"].max()
    current = signal[signal["week_start_sunday"] == latest_week].copy()
    current = current.rename(columns={"demand_signal_index": "current_demand_signal_index", "rank_in_category": "rank_in_category_current"})
    history = signal.sort_values(["segment", "category", "brand", "week_start_sunday"]).copy()
    group_cols = ["segment", "category", "brand"]
    grouped = history.groupby(group_cols, dropna=False)["demand_signal_index"]
    history["signal_4wk_avg"] = grouped.transform(lambda s: s.rolling(4, min_periods=1).mean())
    history["signal_13wk_avg"] = grouped.transform(lambda s: s.rolling(13, min_periods=1).mean())
    latest_features = history[history["week_start_sunday"] == latest_week][group_cols + ["signal_4wk_avg", "signal_13wk_avg"]]
    current = current.merge(latest_features, on=group_cols, how="left")

    rows = []
    for _, row in current.iterrows():
        item_history = history[(history["segment"] == row["segment"]) & (history["category"] == row["category"]) & (history["brand"] == row["brand"])]
        for horizon_week in range(1, 14):
            forecast_week = pd.Timestamp(start_sunday) + pd.Timedelta(weeks=horizon_week - 1)
            same_week = item_history[item_history["week_start_sunday"].dt.isocalendar().week == forecast_week.isocalendar().week]
            seasonal = same_week.sort_values("week_start_sunday")["demand_signal_index"].iloc[-1] if not same_week.empty else pd.NA
            if pd.notna(seasonal):
                forecast = 0.60 * row["signal_4wk_avg"] + 0.25 * row["signal_13wk_avg"] + 0.15 * seasonal
            else:
                forecast = 0.70 * row["signal_4wk_avg"] + 0.30 * row["signal_13wk_avg"]
            forecast = max(0, float(forecast)) if pd.notna(forecast) else pd.NA
            band = band_pct(row["confidence_label"])
            rows.append({
                "forecast_issue_date": issue_date,
                "forecast_issue_ts": issue_ts,
                "report_day_name": pd.Timestamp(issue_date).day_name(),
                "forecast_start_week_sunday": pd.Timestamp(start_sunday),
                "forecast_week_start_sunday": forecast_week,
                "horizon_week": horizon_week,
                "segment": row["segment"],
                "category": row["category"],
                "brand": row["brand"],
                "current_demand_signal_index": row["current_demand_signal_index"],
                "forecast_demand_signal_index": forecast,
                "forecast_lower_signal": forecast * (1 - band) if pd.notna(forecast) else pd.NA,
                "forecast_upper_signal": forecast * (1 + band) if pd.notna(forecast) else pd.NA,
                "forecast_method": FORECAST_METHOD,
                "momentum_label": row["momentum_label"],
                "confidence_label": row["confidence_label"],
                "rank_in_category_current": row["rank_in_category_current"],
                "data_quality_flag": row["data_quality_flag"],
            })
    forecast_df = pd.DataFrame(rows)
    forecast_df["projected_rank_in_category"] = forecast_df.groupby(["forecast_issue_date", "forecast_week_start_sunday", "category"])["forecast_demand_signal_index"].rank(method="dense", ascending=False).astype("Int64")
    columns = ["forecast_issue_date", "forecast_issue_ts", "report_day_name", "forecast_start_week_sunday", "forecast_week_start_sunday", "horizon_week", "segment", "category", "brand", "current_demand_signal_index", "forecast_demand_signal_index", "forecast_lower_signal", "forecast_upper_signal", "forecast_method", "momentum_label", "confidence_label", "rank_in_category_current", "projected_rank_in_category", "data_quality_flag"]
    forecast_df = forecast_df[columns].sort_values(["forecast_issue_date", "category", "brand", "horizon_week"])
    if append_archive:
        append_forecast_archive(forecast_df)
    else:
        forecast_df.to_parquet(FORECAST_OUTPUT, index=False)
    return forecast_df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecast-issue-date", default=None)
    parser.add_argument("--overwrite-archive", action="store_true", help="Replace the forecast mart instead of appending by issue date.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    forecast = build_13w_forecast(args.forecast_issue_date, append_archive=not args.overwrite_archive)
    action = "Archived" if not args.overwrite_archive else "Wrote"
    logging.info("%s %s forecast rows for issue date %s to %s", action, len(forecast), forecast["forecast_issue_date"].iloc[0], FORECAST_OUTPUT)


if __name__ == "__main__":
    main()
