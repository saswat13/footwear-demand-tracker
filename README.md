# Footwear Demand Tracker

Footwear Demand Tracker creates a weekly demand signal layer for athletic footwear. It uses Google Trends search-interest data to compare brand and category momentum for Running Shoes, Trail Running Shoes, and Training Shoes.

This project does not estimate actual sales, actual units, company-reported revenue, or inventory movement. The output is a weekly Demand Signal Index based on search intent. It is intended as a first data layer that can later support forecasting once calibrated with richer marketplace and sales data.

## Publishing Cadence

This project is designed for a Thursday evening publishing cycle. Each weekly report looks forward from the coming immediate Sunday and produces a 13-week forward demand-signal view by brand and category.

Business weeks start on Sunday and represent Sunday through Saturday. Historical tables use `week_start_sunday`; forecast tables use `forecast_week_start_sunday`.

Example: a report issued on Thursday 2026-07-09 has `forecast_issue_date = 2026-07-09`, `forecast_start_week_sunday = 2026-07-12`, and horizon week 1 covers the Sunday-starting week of 2026-07-12.

## How Google Trends Data Is Normalized

Google Trends normalizes every request independently, and pytrends can only request a small number of keywords at a time. To make batches comparable within a category, every request includes the category anchor keyword:

- Running Shoes uses `running shoes`
- Trail Running Shoes uses `trail running shoes`
- Training Shoes uses `training shoes`

The first batch in each category is treated as the reference batch. Other batches are scaled week by week using the ratio between the reference anchor interest and that batch's anchor interest. If an anchor value is zero or missing for a week, adjusted interest for that batch-week is left null.

## Pipeline

```bash
pip install -r requirements.txt

python src/fetch_google_trends.py
python src/build_clean_trends.py
python src/build_signal_mart.py
python src/build_13w_forecast.py --forecast-issue-date 2026-07-09
python src/data_quality_checks.py

streamlit run app/streamlit_app.py
```

Updated full pipeline:

```bash
python src/fetch_google_trends.py
python src/build_clean_trends.py
python src/build_signal_mart.py
python src/build_13w_forecast.py
python src/data_quality_checks.py
streamlit run app/streamlit_app.py
```

If live Google Trends fetching fails because of rate limits or connection issues, the fetch script generates clearly labeled sample data with the same raw schema so the project can run locally.

## Outputs

- `data/raw/google_trends/pull_date=YYYY-MM-DD/*.parquet`: raw batched Google Trends pulls
- `data/clean/weekly_keyword_trends.parquet`: normalized weekly keyword trends with Sunday-starting weeks
- `data/mart/weekly_brand_category_signal.parquet`: weekly brand/category Demand Signal Index
- `data/mart/model_weekly_demand_features.parquet`: modeling-ready signal features
- `data/mart/weekly_brand_category_forecast_13w.parquet`: 13-week forward demand signal by report issue date

The 13-week forecast mart is an archive by `forecast_issue_date`. Running a new issue date appends a new report publication. Rerunning the same issue date replaces that issue date's rows, so the file does not accumulate duplicates.

## Forecast Method

The v1 13-week forward demand signal uses a blended baseline, not advanced ML:

- 60% recent 4-week average signal
- 25% recent 13-week average signal
- 15% same-week-last-year signal when available

If same-week-last-year signal is unavailable, it uses 70% recent 4-week average and 30% recent 13-week average. Confidence bands are simple v1 bands: +/-10% for High, +/-20% for Medium, and +/-35% for Low.

## Dashboard

The Streamlit sidebar is grouped into analysis pages and data operations.

Analysis views:

- Weekly Leaderboard
- Category Trends
- Brand Page
- 13-Week Forward View

Data Controls & Know-How:

- Pipeline Runner
- Data Quality

Dashboard wording intentionally refers to estimated demand signal, projected demand signal, forecasted demand index, and Demand Signal Index. It does not describe results as actual sales or units sold.

The Pipeline Runner page can trigger the full refresh from the dashboard. It lets the user choose a forecast issue date, run the full pipeline, or run one pipeline step at a time.

Dashboard interpretation features include:

- Weekly Leaderboard summary with current signal leader, largest movements, category share, column glossary, and Base Signal context.
- Category Trends tabs for Current Snapshot, Rank Movement, Signal Heatmap, Small Multiples, and annotated Trend Lines.
- Category Trends start/end date filters that drive all charts and summaries.
- Brand Page start/end date filters and a brand summary describing latest strongest category, signal movement, and rank range.
- 13-Week Forward View summary showing projected final-week leader, biggest projected gain/drop, and widest uncertainty band.

## Current Limitations

These are search-intent signals, not actual sales. Google Trends values are sampled and normalized, and the signal can move for reasons other than purchase demand.

Future layers may include:

- Amazon search/autocomplete signals
- Amazon marketplace visibility
- Keepa/BSR data
- Real sales/unit calibration
- Forecasting model
