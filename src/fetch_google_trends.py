from __future__ import annotations

import argparse
import logging
import time
import uuid
from datetime import datetime, timezone

import pandas as pd

from utils import RAW_TRENDS_DIR, ensure_directories, read_active_config, slugify

GEO = "US"
TIMEFRAME = "today 5-y"
HL = "en-US"
TZ = 360
MAX_KEYWORDS_PER_REQUEST = 5

RAW_COLUMNS = [
    "pull_id", "pull_ts", "pull_date", "segment", "category", "brand", "keyword", "keyword_type",
    "geo", "timeframe", "batch_id", "anchor_keyword", "date", "raw_interest", "is_partial", "is_sample_data",
]


def build_category_batches(category_keywords: pd.DataFrame, anchor_keyword: str) -> list[pd.DataFrame]:
    anchor_rows = category_keywords[category_keywords["keyword"].str.lower() == anchor_keyword.lower()]
    if anchor_rows.empty:
        raise ValueError(f"Anchor keyword {anchor_keyword!r} is missing from keywords config")
    anchor = anchor_rows.iloc[[0]]
    others = category_keywords[category_keywords["keyword"].str.lower() != anchor_keyword.lower()]
    batches = []
    for start in range(0, len(others), MAX_KEYWORDS_PER_REQUEST - 1):
        batches.append(pd.concat([anchor, others.iloc[start:start + MAX_KEYWORDS_PER_REQUEST - 1]], ignore_index=True))
    return batches or [anchor.reset_index(drop=True)]


def fetch_batch_pytrends(batch: pd.DataFrame, retries: int, sleep_seconds: float) -> pd.DataFrame:
    from pytrends.request import TrendReq

    keywords = batch["keyword"].tolist()
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            trends = TrendReq(hl=HL, tz=TZ)
            trends.build_payload(keywords, timeframe=TIMEFRAME, geo=GEO)
            result = trends.interest_over_time()
            if result.empty:
                raise RuntimeError("pytrends returned an empty response")
            return result.reset_index()
        except Exception as exc:  # pragma: no cover
            last_error = exc
            logging.warning("pytrends attempt %s/%s failed for %s: %s", attempt, retries, keywords, exc)
            time.sleep(sleep_seconds * attempt)
    raise RuntimeError(f"pytrends failed after {retries} attempts") from last_error


def generate_sample_interest(batch: pd.DataFrame, pull_ts: str) -> pd.DataFrame:
    end = pd.Timestamp.utcnow().normalize()
    dates = pd.date_range(end=end, periods=156, freq="W-SUN")
    frame = pd.DataFrame({"date": dates, "isPartial": False})
    anchor_keyword = batch.iloc[0]["keyword"]
    idx_series = pd.Series(range(len(dates)))
    for idx, keyword in enumerate(batch["keyword"]):
        base = 65 if keyword == anchor_keyword else 28 + idx * 9
        seasonal = (idx_series % 52) / 52 * 18
        trend = idx_series * (0.04 + idx * 0.01)
        wave = idx_series.map(lambda x: ((x + idx * 7) % 13) - 6)
        frame[keyword] = (base + seasonal + trend + wave).clip(lower=1, upper=100).round().astype(int)
    logging.info("Generated sample Google Trends-shaped data for local development at %s", pull_ts)
    return frame


def to_long_raw(trends_df: pd.DataFrame, batch: pd.DataFrame, batch_id: int, anchor_keyword: str, pull_id: str, pull_ts: str, pull_date: str, is_sample_data: bool) -> pd.DataFrame:
    partial_col = "isPartial" if "isPartial" in trends_df.columns else "is_partial"
    id_vars = ["date"] + ([partial_col] if partial_col in trends_df.columns else [])
    long_df = trends_df.melt(id_vars=id_vars, value_vars=batch["keyword"], var_name="keyword", value_name="raw_interest")
    if partial_col in long_df.columns:
        long_df = long_df.rename(columns={partial_col: "is_partial"})
    else:
        long_df["is_partial"] = False
    long_df = long_df.merge(batch[["segment", "category", "brand", "keyword", "keyword_type"]], on="keyword", how="left")
    long_df["pull_id"] = pull_id
    long_df["pull_ts"] = pull_ts
    long_df["pull_date"] = pull_date
    long_df["geo"] = GEO
    long_df["timeframe"] = TIMEFRAME
    long_df["batch_id"] = batch_id
    long_df["anchor_keyword"] = anchor_keyword
    long_df["is_sample_data"] = is_sample_data
    return long_df[RAW_COLUMNS]


def fetch_all(use_sample_on_failure: bool = True, retries: int = 3, sleep_seconds: float = 5.0) -> list[str]:
    ensure_directories()
    categories, keywords = read_active_config()
    pull_id = str(uuid.uuid4())
    pull_ts = datetime.now(timezone.utc).isoformat()
    pull_date = datetime.now(timezone.utc).date().isoformat()
    output_dir = RAW_TRENDS_DIR / f"pull_date={pull_date}"
    output_dir.mkdir(parents=True, exist_ok=True)
    written_files = []
    for _, category_row in categories.iterrows():
        category = category_row["category"]
        anchor_keyword = category_row["anchor_keyword"]
        category_keywords = keywords[keywords["category"] == category].sort_values(["priority", "brand", "keyword"])
        for batch_id, batch in enumerate(build_category_batches(category_keywords, anchor_keyword), start=1):
            is_sample_data = False
            try:
                trends = fetch_batch_pytrends(batch, retries=retries, sleep_seconds=sleep_seconds)
                time.sleep(sleep_seconds)
            except Exception as exc:  # pragma: no cover
                logging.error("Batch failed for %s batch %s: %s", category, batch_id, exc)
                if not use_sample_on_failure:
                    continue
                trends = generate_sample_interest(batch, pull_ts)
                is_sample_data = True
            raw = to_long_raw(trends, batch, batch_id, anchor_keyword, pull_id, pull_ts, pull_date, is_sample_data)
            output_path = output_dir / f"{slugify(category)}_{batch_id}.parquet"
            raw.to_parquet(output_path, index=False)
            written_files.append(str(output_path))
            logging.info("Wrote %s rows to %s", len(raw), output_path)
    return written_files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-sample-fallback", action="store_true")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep-seconds", type=float, default=5.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    files = fetch_all(not args.no_sample_fallback, args.retries, args.sleep_seconds)
    logging.info("Finished Google Trends pull. Files written: %s", len(files))


if __name__ == "__main__":
    main()
