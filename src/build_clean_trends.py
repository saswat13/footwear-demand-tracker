from __future__ import annotations

import logging

import pandas as pd

from utils import CLEAN_DIR, convert_to_sunday_week, ensure_directories, latest_pull_dir, pct_change

CLEAN_OUTPUT = CLEAN_DIR / "weekly_keyword_trends.parquet"


def read_latest_raw() -> pd.DataFrame:
    pull_dir = latest_pull_dir()
    if pull_dir is None:
        raise FileNotFoundError("No raw Google Trends pull found under data/raw/google_trends")
    files = sorted(pull_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files found in {pull_dir}")
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)


def normalize_category(category_df: pd.DataFrame) -> pd.DataFrame:
    category_df = category_df.copy()
    reference_batch = int(category_df["batch_id"].min())
    anchor_keyword = category_df["anchor_keyword"].iloc[0]
    anchors = category_df[category_df["keyword"].str.lower() == anchor_keyword.lower()]
    reference = anchors[anchors["batch_id"] == reference_batch][["week_start_sunday", "raw_interest"]].rename(columns={"raw_interest": "reference_anchor_interest"})
    batch_anchor = anchors[["week_start_sunday", "batch_id", "raw_interest"]].rename(columns={"raw_interest": "batch_anchor_interest"})
    category_df = category_df.merge(reference, on="week_start_sunday", how="left").merge(batch_anchor, on=["week_start_sunday", "batch_id"], how="left")
    valid = category_df["batch_anchor_interest"].notna() & (category_df["batch_anchor_interest"] != 0)
    category_df["scale_factor"] = pd.NA
    category_df.loc[valid, "scale_factor"] = category_df.loc[valid, "reference_anchor_interest"] / category_df.loc[valid, "batch_anchor_interest"]
    category_df["adjusted_interest"] = category_df["raw_interest"] * category_df["scale_factor"]
    duplicated_anchor = (category_df["keyword"].str.lower() == anchor_keyword.lower()) & (category_df["batch_id"] != reference_batch)
    return category_df[~duplicated_anchor].drop(columns=["reference_anchor_interest", "batch_anchor_interest", "scale_factor"])


def add_features(clean: pd.DataFrame) -> pd.DataFrame:
    clean = clean.sort_values(["category", "brand", "keyword", "week_start_sunday"]).copy()
    group_cols = ["segment", "category", "brand", "keyword"]
    grouped = clean.groupby(group_cols, dropna=False)["adjusted_interest"]
    clean["interest_4wk_avg"] = grouped.transform(lambda s: s.rolling(4, min_periods=1).mean())
    clean["interest_13wk_avg"] = grouped.transform(lambda s: s.rolling(13, min_periods=1).mean())
    clean["wow_change_pct"] = pct_change(clean["adjusted_interest"], grouped.shift(1))
    clean["yoy_change_pct"] = pct_change(clean["adjusted_interest"], grouped.shift(52))
    clean["data_quality_flag"] = "OK"
    clean.loc[clean["adjusted_interest"].isna(), "data_quality_flag"] = "MISSING_ADJUSTED_INTEREST"
    low_signal = grouped.transform(lambda s: s.fillna(0).rolling(8, min_periods=4).mean()) < 2
    clean.loc[(clean["data_quality_flag"] == "OK") & low_signal, "data_quality_flag"] = "LOW_SIGNAL"
    volatile = clean["wow_change_pct"].abs() >= 75
    clean.loc[(clean["data_quality_flag"] == "OK") & volatile, "data_quality_flag"] = "VOLATILE"
    return clean


def build_clean_trends(raw: pd.DataFrame | None = None) -> pd.DataFrame:
    ensure_directories()
    raw = read_latest_raw() if raw is None else raw.copy()
    raw["date"] = pd.to_datetime(raw["date"])
    raw["week_start_sunday"] = convert_to_sunday_week(raw["date"])
    raw = raw[~raw["is_partial"].fillna(False)].copy()
    raw["raw_interest"] = pd.to_numeric(raw["raw_interest"], errors="coerce")
    normalized = pd.concat([normalize_category(df) for _, df in raw.groupby("category", sort=False)], ignore_index=True)
    clean = add_features(normalized)
    columns = ["week_start_sunday", "segment", "category", "brand", "keyword", "keyword_type", "geo", "raw_interest", "adjusted_interest", "interest_4wk_avg", "interest_13wk_avg", "wow_change_pct", "yoy_change_pct", "pull_ts", "batch_id", "anchor_keyword", "data_quality_flag"]
    clean = clean[columns].sort_values(["week_start_sunday", "category", "brand", "keyword"])
    clean.to_parquet(CLEAN_OUTPUT, index=False)
    return clean


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    clean = build_clean_trends()
    logging.info("Wrote %s rows to %s", len(clean), CLEAN_OUTPUT)


if __name__ == "__main__":
    main()
