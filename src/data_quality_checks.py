from __future__ import annotations

import pandas as pd

from utils import CONFIG_DIR, MART_DIR, RAW_TRENDS_DIR, read_active_config


def build_quality_report() -> list[str]:
    lines: list[str] = []
    categories, keywords = read_active_config()
    raw_files = list(RAW_TRENDS_DIR.glob("pull_date=*/*.parquet")) if RAW_TRENDS_DIR.exists() else []
    lines.append("Footwear demand signal data-quality report")
    lines.append("=" * 48)
    lines.append(f"Raw Google Trends parquet files: {len(raw_files)}")
    if not raw_files:
        lines.append("WARN: No raw Google Trends files found.")
    lines.append(f"Active categories: {len(categories)}")
    lines.append(f"Active keywords: {len(keywords)}")
    if categories.empty or keywords.empty:
        lines.append("WARN: Missing active config rows.")
    duplicates = keywords.duplicated(["segment", "category", "brand", "keyword"]).sum()
    lines.append(f"Duplicate active keyword rows: {duplicates}")
    brand_counts = keywords[keywords["keyword_type"] == "brand_category"].groupby("category")["brand"].nunique()
    for category in categories["category"]:
        count = int(brand_counts.get(category, 0))
        lines.append(f"Active brands in {category}: {count}")
        if count < 3:
            lines.append(f"WARN: {category} has fewer than 3 active brands.")
    clean_path = CONFIG_DIR.parent / "data" / "clean" / "weekly_keyword_trends.parquet"
    if clean_path.exists():
        clean = pd.read_parquet(clean_path)
        null_rate = clean["adjusted_interest"].isna().mean()
        latest_week = pd.to_datetime(clean["week_start_sunday"]).max()
        lines.append(f"Adjusted interest null rate: {null_rate:.1%}")
        lines.append(f"Latest complete Sunday-starting week available: {latest_week.date() if pd.notna(latest_week) else 'none'}")
    else:
        lines.append("WARN: Clean weekly keyword trends file is missing.")
    signal_path = MART_DIR / "weekly_brand_category_signal.parquet"
    if signal_path.exists():
        mart = pd.read_parquet(signal_path)
        duplicate_mart = mart.duplicated(["week_start_sunday", "segment", "category", "brand"]).sum()
        lines.append(f"Duplicate final mart rows: {duplicate_mart}")
        history = mart.dropna(subset=["demand_signal_index"]).groupby(["category", "brand"]).size()
        insufficient = history[history < 52]
        lines.append(f"Brands with insufficient history (<52 weeks): {len(insufficient)}")
        for (category, brand), weeks in insufficient.head(20).items():
            lines.append(f"  - {category} / {brand}: {weeks} weeks")
    else:
        lines.append("WARN: Weekly brand/category signal mart is missing.")
    forecast_path = MART_DIR / "weekly_brand_category_forecast_13w.parquet"
    if forecast_path.exists():
        forecast = pd.read_parquet(forecast_path)
        issue_counts = forecast.groupby(["forecast_issue_date", "segment", "category", "brand"]).size()
        bad_counts = int((issue_counts != 13).sum())
        lines.append(f"Forecast brand/category groups without exactly 13 horizons: {bad_counts}")
    else:
        lines.append("WARN: 13-week forecast mart is missing.")
    return lines


def main() -> None:
    print("\n".join(build_quality_report()))


if __name__ == "__main__":
    main()
