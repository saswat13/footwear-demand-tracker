# Development Notes

This document is a handoff guide for the `footwear-demand-tracker` project. It explains what has been built, how the pipeline works, and where to make future changes.

## Project Purpose

`footwear-demand-tracker` is a Python and Streamlit project that builds weekly demand-signal dashboards for athletic footwear.

The project currently tracks Google Trends search-interest signals for:

- Running Shoes
- Trail Running Shoes
- Training Shoes

It compares brand/category demand signals across brands such as Nike, Adidas, Hoka, Brooks, ASICS, On, Saucony, New Balance, Salomon, Altra, Reebok, Under Armour, and NOBULL.

Important: this project does not estimate actual sales, actual units, company-reported revenue, or inventory movement. It creates a search-intent based Demand Signal Index.

## Current Folder Structure

```text
footwear-demand-tracker/
├── README.md
├── DEVELOPMENT_NOTES.md
├── requirements.txt
├── config/
│   ├── categories.csv
│   └── keywords.csv
├── data/
│   ├── raw/google_trends/
│   ├── clean/
│   │   └── weekly_keyword_trends.parquet
│   └── mart/
│       ├── weekly_brand_category_signal.parquet
│       ├── model_weekly_demand_features.parquet
│       └── weekly_brand_category_forecast_13w.parquet
├── src/
│   ├── utils.py
│   ├── fetch_google_trends.py
│   ├── build_clean_trends.py
│   ├── build_signal_mart.py
│   ├── build_13w_forecast.py
│   └── data_quality_checks.py
├── app/
│   └── streamlit_app.py
└── tests/
    ├── test_clean_trends.py
    └── test_signal_mart.py
```

## What Has Been Built

### 1. Configuration

The project is driven by CSV configuration files.

`config/categories.csv`

- Defines active footwear categories.
- Defines the Google Trends anchor keyword for each category.
- Each anchor keyword is used to normalize Google Trends batches.

`config/keywords.csv`

- Defines the tracked category and brand keywords.
- Includes generic category keywords and brand/category keywords.
- Has an `active` flag so keywords can be turned on or off without changing code.

### 2. Google Trends Fetching

File: `src/fetch_google_trends.py`

This script:

- Reads active categories and keywords.
- Splits keywords into batches of up to 5 terms, which matches Google Trends request limits.
- Ensures every batch includes the category anchor keyword.
- Fetches weekly Google Trends interest over time for the US.
- Writes raw batch output to Parquet under:

```text
data/raw/google_trends/pull_date=YYYY-MM-DD/
```

If live Google Trends fetching fails because of rate limits, missing pytrends setup, or connection problems, the script creates sample fallback data. The sample data has the same schema as the real raw output and is labeled with `is_sample_data = true`.

### 3. Clean Weekly Trends

File: `src/build_clean_trends.py`

This script:

- Reads the latest raw Google Trends pull.
- Converts all dates into Sunday-starting business weeks.
- Uses `week_start_sunday` as the canonical historical weekly date column.
- Removes partial weeks.
- Normalizes all batches in the same category onto a comparable scale using the anchor keyword.
- Writes:

```text
data/clean/weekly_keyword_trends.parquet
```

Important logic:

- The first batch in a category is the reference batch.
- Other batches are scaled week by week using:

```text
reference_anchor_interest / batch_anchor_interest
```

- Duplicate anchor rows from non-reference batches are removed.

The clean table also includes rolling and movement features:

- `interest_4wk_avg`
- `interest_13wk_avg`
- `wow_change_pct`
- `yoy_change_pct`
- `data_quality_flag`

### 4. Brand/Category Signal Mart

File: `src/build_signal_mart.py`

This script:

- Reads the clean keyword trend table.
- Uses only `keyword_type = brand_category` for brand rankings.
- Builds the weekly brand/category Demand Signal Index.
- Writes:

```text
data/mart/weekly_brand_category_signal.parquet
```

The grain is:

```text
week_start_sunday + segment + category + brand
```

It also writes modeling-ready features to:

```text
data/mart/model_weekly_demand_features.parquet
```

The Demand Signal Index is normalized within each category/week:

```text
100 * brand_base_signal / max_brand_base_signal_in_category_week
```

### 5. 13-Week Forward Forecast

File: `src/build_13w_forecast.py`

This script creates the 13-week forward demand signal view.

It supports the Thursday evening publishing cycle:

- Reports are published every Thursday evening.
- Each report starts from the coming immediate Sunday.
- Forecast weeks are Sunday through Saturday.
- Forecast date column is `forecast_week_start_sunday`.

Example:

```text
forecast_issue_date = 2026-07-09
forecast_start_week_sunday = 2026-07-12
horizon_week = 1 means the week starting 2026-07-12
```

The output is:

```text
data/mart/weekly_brand_category_forecast_13w.parquet
```

This file is now maintained as a forecast archive by `forecast_issue_date`.

- Running a new issue date appends that report publication.
- Rerunning the same issue date replaces only that issue date's rows.
- Each issue date should have exactly 13 horizon weeks per brand/category.

The grain is:

```text
forecast_issue_date + forecast_week_start_sunday + segment + category + brand
```

Forecast method:

```text
blended_recent_seasonal_baseline_v1
```

The v1 forecast is intentionally simple:

- 60% recent 4-week average signal
- 25% recent 13-week average signal
- 15% same-week-last-year signal, if available

If same-week-last-year signal is unavailable:

- 70% recent 4-week average signal
- 30% recent 13-week average signal

Confidence bands:

- High: plus/minus 10%
- Medium: plus/minus 20%
- Low: plus/minus 35%

### 6. Shared Utilities

File: `src/utils.py`

Key functions:

`get_next_sunday(report_date)`

- Returns the coming immediate Sunday after the report date.
- If the report date is already Sunday, returns that same Sunday.
- For Thursday publishing, returns the Sunday 3 days later.

`convert_to_sunday_week(date_col)`

- Converts dates into the Sunday-starting week they belong to.
- Used to ensure historical weekly logic is Sunday-based.

### 7. Data Quality Checks

File: `src/data_quality_checks.py`

This script prints a readable console report covering:

- Missing raw files
- Missing config rows
- Duplicate keyword rows
- Duplicate mart rows
- Adjusted interest null rate
- Latest complete Sunday-starting week available
- Brands with insufficient history
- Categories with fewer than 3 active brands
- Forecast groups without exactly 13 horizon weeks

### 8. Streamlit Dashboard

File: `app/streamlit_app.py`

The dashboard has these pages:

- Weekly Leaderboard
- Category Trends
- Brand Page
- 13-Week Forward View
- Pipeline Runner
- Data Quality

The dashboard uses demand-signal language only:

- Demand Signal Index
- Estimated demand signal
- Projected demand signal
- Forecasted demand index
- 13-week forward demand signal

It avoids implying that the data represents real sales or real units.

The Pipeline Runner page lets a user trigger the project refresh from the dashboard:

- Run the full pipeline
- Run one pipeline step at a time
- Choose the forecast issue date used by the 13-week forecast
- View command output and errors directly in the app

For live usage, keep in mind that Google Trends can rate-limit requests. The dashboard includes quick retry settings for local development, and the fetch script can fall back to sample-shaped data if the live pull fails.

## How To Run The Project

From the `footwear-demand-tracker` folder:

```bash
pip install -r requirements.txt
```

Run the full pipeline:

```bash
python src/fetch_google_trends.py
python src/build_clean_trends.py
python src/build_signal_mart.py
python src/build_13w_forecast.py
python src/data_quality_checks.py
streamlit run app/streamlit_app.py
```

Run a specific Thursday publishing example:

```bash
python src/build_13w_forecast.py --forecast-issue-date 2026-07-09
```

Run tests:

```bash
python -m pytest
```

## Verification Already Completed

During development, the following checks passed:

- `python -m pytest`
- 6 tests passed
- Raw Google Trends/sample fallback Parquet files were generated
- Clean weekly keyword trends were generated
- Brand/category signal mart was generated
- 13-week forecast mart was generated
- Data quality report completed
- Streamlit dashboard was started successfully on port 8501

The tested Thursday example confirmed:

```text
forecast_issue_date = 2026-07-09
forecast_start_week_sunday = 2026-07-12
```

The forecast mart contained exactly 13 horizon weeks per brand/category.

## Where To Make Future Changes

### Add or Remove Brands

Edit:

```text
config/keywords.csv
```

Add a row with:

```text
segment, category, brand, keyword, keyword_type, priority, active
```

Then rerun the pipeline.

### Add a New Category

Edit both:

```text
config/categories.csv
config/keywords.csv
```

Make sure the new category has:

- One anchor keyword in `categories.csv`
- A matching generic category keyword row in `keywords.csv`
- At least 3 active brand keywords if you want useful rankings

### Change Forecast Logic

Edit:

```text
src/build_13w_forecast.py
```

The current method is a simple blended baseline. Future versions could add:

- Trend extrapolation
- Seasonal smoothing
- Category-level normalization
- Marketplace signals
- Calibrated unit forecasts

### Change Dashboard Layout

Edit:

```text
app/streamlit_app.py
```

Each dashboard section is controlled by the sidebar page selector.

### Add More Data Quality Rules

Edit:

```text
src/data_quality_checks.py
```

Good next checks might include:

- Stale raw pulls
- Unexpected category/brand drops
- Sudden missing history
- Too many sample-data rows
- Very large week-over-week changes

## Important Design Decisions

### Sunday Weeks

All weekly business logic now uses Sunday-starting weeks.

Historical signal tables use:

```text
week_start_sunday
```

Forecast tables use:

```text
forecast_week_start_sunday
```

### Thursday Publishing

The project assumes reports are generated on Thursday evening and should forecast from the coming Sunday.

This is handled by:

```text
get_next_sunday(report_date)
```

### Anchor-Based Google Trends Normalization

Because Google Trends normalizes each request independently, brand keywords cannot be compared across batches unless batches share a common reference keyword. The anchor keyword provides that reference.

### Forecast Is Still A Demand Signal

The 13-week forecast is a projected demand signal, not a sales forecast. It should not be interpreted as actual units, actual revenue, or company-reported performance.

## Recommended Next Development Steps

1. Add a `Makefile` or `run_pipeline.ps1` wrapper so the full pipeline can be run with one command.
2. Add a small metadata table that records each pipeline run and whether live or sample data was used.
3. Add visual indicators in Streamlit when sample fallback data is present.
4. Add more robust historical same-week-last-year logic for forecast seasonality.
5. Add Amazon search/autocomplete signals as the next demand-signal layer.
6. Add marketplace visibility or Keepa/BSR data.
7. Only after real sales/unit data is available, add calibration and unit forecasting.

## Current Dashboard State

The Streamlit dashboard has been expanded beyond the initial simple line-chart view.

Sidebar navigation is grouped into:

- Analysis Views: Weekly Leaderboard, Category Trends, Brand Page, and 13-Week Forward View.
- Data Controls & Know-How: Pipeline Runner and Data Quality.

Weekly Leaderboard now includes:

- Metric-card summary for current signal leader, largest WoW movement, largest YoY movement, and top share signal.
- Plain-English explanation of what the user is seeing.
- Column glossary under "How to read these columns".
- `Base Signal`, which is the smoothed underlying Google Trends signal used to calculate the index. It is not actual search volume.

Category Trends now includes:

- Category, brand, start date, and end date filters.
- Trend Summary with current visible leader, number of leadership changes, strongest overtake, and strongest 8-week gain.
- Current Snapshot tab with horizontal bars for the latest visible week.
- Rank Movement tab for bump-chart style rank movement.
- Signal Heatmap tab for scanning periods of strength and weakness.
- Small Multiples tab for one mini chart per selected brand.
- Trend Lines tab for detailed annotated line charts.

Brand Page now includes:

- Brand, start date, and end date filters.
- Brand Summary showing latest strongest category, latest average signal, best rank in period, and weakest rank in period.
- Plain-English explanation of how the brand moved over the selected period.

13-Week Forward View now includes:

- Report issue date selector.
- Category and brand filters.
- Forecast Summary showing projected final-week leader, biggest projected gain, biggest projected drop, and widest uncertainty band.
- Forecast chart with confidence bands.

Pipeline Runner now lets users trigger:

- Full pipeline refresh.
- Individual pipeline steps.
- Forecast issue date selection for the 13-week forecast.
- Command output review from inside the dashboard.

The dashboard styling has also been customized with a darker sidebar, cleaner metric cards, framed tables, and readable controls.

## Current Forecast Archive Behavior

The 13-week forecast mart is now maintained as an archive by `forecast_issue_date`.

- Running a new issue date appends that report publication.
- Rerunning the same issue date replaces only that issue date's rows.
- Duplicate forecast rows are avoided.
- Each issue date should contain exactly 13 horizon weeks per brand/category.

This behavior is covered by tests in `tests/test_signal_mart.py`.
