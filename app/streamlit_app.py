from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))
from data_quality_checks import build_quality_report

SIGNAL_PATH = PROJECT_ROOT / "data" / "mart" / "weekly_brand_category_signal.parquet"
FORECAST_PATH = PROJECT_ROOT / "data" / "mart" / "weekly_brand_category_forecast_13w.parquet"

st.set_page_config(page_title="Footwear Demand Tracker", layout="wide")

st.markdown(
    """
<style>
    :root {
        --ft-ink: #172033;
        --ft-muted: #667085;
        --ft-line: #d9e2ec;
        --ft-bg: #f6f8fb;
        --ft-panel: #ffffff;
        --ft-accent: #0f766e;
        --ft-accent-soft: #d9f3ef;
        --ft-gold: #b7791f;
    }

    .stApp {
        background:
            linear-gradient(180deg, #f8fbfd 0%, #eef4f7 42%, #f7f9fb 100%);
        color: var(--ft-ink);
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #102033 0%, #123843 100%);
        border-right: 1px solid rgba(255, 255, 255, 0.14);
    }

    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span {
        color: #edf7f6;
    }

    section[data-testid="stSidebar"] div[data-baseweb="select"] * {
        color: #172033 !important;
    }

    section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background: #ffffff;
        border-color: rgba(255, 255, 255, 0.22);
    }

    div[data-baseweb="popover"] * {
        color: #172033 !important;
    }

    section[data-testid="stSidebar"] [role="radiogroup"] label {
        border-radius: 8px;
        padding: 0.28rem 0.35rem;
        margin-bottom: 0.15rem;
    }

    section[data-testid="stSidebar"] [role="radiogroup"] label:hover {
        background: rgba(255, 255, 255, 0.10);
    }

    h1, h2, h3 {
        color: var(--ft-ink);
        letter-spacing: 0;
    }

    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.86);
        border: 1px solid var(--ft-line);
        border-left: 4px solid var(--ft-accent);
        border-radius: 8px;
        padding: 0.85rem 1rem;
        box-shadow: 0 8px 24px rgba(15, 35, 55, 0.06);
    }

    div[data-testid="stMetricLabel"] p {
        color: var(--ft-muted);
        font-size: 0.82rem;
    }

    div[data-testid="stMetricValue"] {
        color: var(--ft-ink);
    }

    div[data-testid="stInfo"] {
        background: var(--ft-accent-soft);
        border: 1px solid rgba(15, 118, 110, 0.22);
        border-radius: 8px;
    }

    div[data-testid="stExpander"] {
        background: rgba(255, 255, 255, 0.8);
        border: 1px solid var(--ft-line);
        border-radius: 8px;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid var(--ft-line);
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 10px 26px rgba(15, 35, 55, 0.05);
    }

    .stButton > button {
        border-radius: 8px;
        border: 1px solid var(--ft-accent);
        color: var(--ft-accent);
    }

    .stButton > button[kind="primary"] {
        background: var(--ft-accent);
        color: white;
    }
</style>
""",
    unsafe_allow_html=True,
)

LEADERBOARD_COLUMN_CONFIG = {
    "Rank": st.column_config.NumberColumn(
        "Rank",
        help="Brand rank within the selected category and Sunday-starting week. Rank 1 has the strongest demand signal.",
        format="%d",
    ),
    "Brand": st.column_config.TextColumn("Brand", help="Footwear brand measured by its category keyword signal."),
    "Demand Signal Index": st.column_config.NumberColumn(
        "Demand Signal Index",
        help="Relative search-demand score. The strongest brand in the category/week is 100; others are scaled against it.",
        format="%.1f",
    ),
    "Base Signal": st.column_config.NumberColumn(
        "Base Signal",
        help="Smoothed Google Trends demand signal used to calculate the index. This is not actual search volume.",
        format="%.1f",
    ),
    "WoW Change %": st.column_config.NumberColumn(
        "WoW Change %",
        help="Week-over-week change versus the previous Sunday-starting week.",
        format="%.1f",
    ),
    "YoY Change %": st.column_config.NumberColumn(
        "YoY Change %",
        help="Year-over-year change versus the comparable week 52 weeks earlier. Blank means not enough history.",
        format="%.1f",
    ),
    "Category Share Signal": st.column_config.TextColumn(
        "Category Share Signal",
        help="Brand share of the measured demand signal within the selected category/week.",
    ),
    "Momentum": st.column_config.TextColumn(
        "Momentum",
        help="Rising, Falling, or Stable based on week-over-week movement.",
    ),
    "Confidence": st.column_config.TextColumn(
        "Confidence",
        help="High, Medium, or Low based on data quality and available history.",
    ),
}


PIPELINE_STEPS = [
    ("Fetch Google Trends", ["src/fetch_google_trends.py"]),
    ("Build Clean Trends", ["src/build_clean_trends.py"]),
    ("Build Signal Mart", ["src/build_signal_mart.py"]),
    ("Build 13-Week Forecast", ["src/build_13w_forecast.py"]),
    ("Run Data Quality Checks", ["src/data_quality_checks.py"]),
]


def run_pipeline_step(script_args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *script_args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )


def show_leaderboard_guide() -> None:
    st.info(
        "Read this as a relative search-demand leaderboard. A Demand Signal Index of 100 is the strongest "
        "brand signal in the selected category/week; other brands are scaled against that leader."
    )
    with st.expander("How to read these columns"):
        st.markdown(
            """
- **Rank**: brand position within the selected category and week.
- **Brand**: footwear brand being measured.
- **Demand Signal Index**: relative demand signal from Google Trends search interest; 100 is the category/week leader.
- **Base Signal**: smoothed underlying Google Trends demand signal used to calculate the index. It is not actual search volume.
- **WoW Change %**: movement versus the previous week.
- **YoY Change %**: movement versus the comparable week last year.
- **Category Share Signal**: the brand's share of total measured signal in that category/week.
- **Momentum**: Rising if WoW is at least 10%, Falling if WoW is -10% or lower, otherwise Stable.
- **Confidence**: rough reliability label based on history length and data-quality checks.

These metrics are demand signals from search interest, not actual sales, revenue, or units.
"""
        )


def show_leaderboard_summary(view: pd.DataFrame, selected_category: str, selected_week) -> None:
    if view.empty:
        st.warning("No leaderboard rows are available for this category/week.")
        return

    leader = view.sort_values("rank_in_category").iloc[0]
    valid_wow = view.dropna(subset=["wow_change_pct"])
    valid_yoy = view.dropna(subset=["yoy_change_pct"])
    biggest_wow = valid_wow.loc[valid_wow["wow_change_pct"].abs().idxmax()] if not valid_wow.empty else None
    biggest_yoy = valid_yoy.loc[valid_yoy["yoy_change_pct"].abs().idxmax()] if not valid_yoy.empty else None
    top_share = view["category_share_signal"].max()

    st.markdown("#### Leaderboard Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Current signal leader",
        leader["brand"],
        f"{leader['demand_signal_index']:.1f} index",
    )
    if biggest_wow is not None:
        col2.metric(
            "Largest WoW movement",
            biggest_wow["brand"],
            f"{biggest_wow['wow_change_pct']:.1f}%",
        )
    else:
        col2.metric("Largest WoW movement", "n/a")
    if biggest_yoy is not None:
        col3.metric(
            "Largest YoY movement",
            biggest_yoy["brand"],
            f"{biggest_yoy['yoy_change_pct']:.1f}%",
        )
    else:
        col3.metric("Largest YoY movement", "n/a")
    col4.metric("Top share signal", f"{top_share * 100:.1f}%")

    summary_lines = [
        f"For {selected_category} in the Sunday-starting week {selected_week}, {leader['brand']} has the strongest relative demand signal.",
    ]
    if biggest_wow is not None:
        direction = "up" if biggest_wow["wow_change_pct"] > 0 else "down" if biggest_wow["wow_change_pct"] < 0 else "flat"
        summary_lines.append(
            f"The largest week-over-week movement is {biggest_wow['brand']} at {biggest_wow['wow_change_pct']:.1f}%, moving {direction} versus the prior week."
        )
    if biggest_yoy is not None:
        direction = "up" if biggest_yoy["yoy_change_pct"] > 0 else "down" if biggest_yoy["yoy_change_pct"] < 0 else "flat"
        summary_lines.append(
            f"The largest year-over-year movement is {biggest_yoy['brand']} at {biggest_yoy['yoy_change_pct']:.1f}%, moving {direction} versus the comparable week last year."
        )
        if biggest_yoy["brand"] != leader["brand"]:
            summary_lines.append(
                f"That does not mean {biggest_yoy['brand']} is the largest current signal; it means {biggest_yoy['brand']} changed the most versus its own prior-year baseline, while {leader['brand']} still has the highest current relative index."
            )
    if top_share >= 0.35:
        summary_lines.append(
            f"The category is relatively concentrated this week, with the top brand representing {top_share * 100:.1f}% of measured category signal."
        )
    else:
        summary_lines.append(
            "The category signal is fairly distributed across multiple brands this week."
        )

    st.write(" ".join(summary_lines))


def build_leadership_changes(chart_df: pd.DataFrame) -> pd.DataFrame:
    if chart_df.empty:
        return pd.DataFrame()

    weekly = chart_df.sort_values(["week_start_sunday", "demand_signal_index"], ascending=[True, False])
    leaders = weekly.groupby("week_start_sunday", as_index=False).first()
    leaders["previous_leader"] = leaders["brand"].shift(1)
    leaders["leader_changed"] = leaders["brand"].ne(leaders["previous_leader"]) & leaders["previous_leader"].notna()
    changes = leaders[leaders["leader_changed"]].copy()
    if changes.empty:
        return changes

    lookup = chart_df.set_index(["week_start_sunday", "brand"])["demand_signal_index"]
    previous_scores = []
    for _, row in changes.iterrows():
        previous_scores.append(lookup.get((row["week_start_sunday"], row["previous_leader"]), pd.NA))

    changes["previous_leader_index"] = previous_scores
    changes["new_leader_index"] = changes["demand_signal_index"]
    changes["overtake_margin"] = changes["new_leader_index"] - changes["previous_leader_index"]
    return changes.sort_values("overtake_margin", ascending=False)


def build_strongest_turnaround(chart_df: pd.DataFrame, window_weeks: int = 8) -> pd.Series | None:
    if chart_df.empty:
        return None

    trend = chart_df.sort_values(["brand", "week_start_sunday"]).copy()
    grouped = trend.groupby("brand", dropna=False)
    trend["turnaround_start_week"] = grouped["week_start_sunday"].shift(window_weeks)
    trend["turnaround_start_index"] = grouped["demand_signal_index"].shift(window_weeks)
    trend["turnaround_gain"] = trend["demand_signal_index"] - trend["turnaround_start_index"]
    valid = trend.dropna(subset=["turnaround_gain", "turnaround_start_week"])
    valid = valid[valid["turnaround_gain"] > 0]
    if valid.empty:
        return None
    return valid.loc[valid["turnaround_gain"].idxmax()]


def show_category_trend_summary(chart_df: pd.DataFrame, selected_category: str) -> pd.DataFrame:
    st.markdown("#### Trend Summary")
    if chart_df.empty:
        st.warning("Select at least one brand to summarize category trends.")
        return pd.DataFrame()

    changes = build_leadership_changes(chart_df)
    turnaround = build_strongest_turnaround(chart_df)
    latest_week = chart_df["week_start_sunday"].max()
    latest = chart_df[chart_df["week_start_sunday"] == latest_week].sort_values("demand_signal_index", ascending=False)
    current_leader = latest.iloc[0]
    unique_weeks = chart_df["week_start_sunday"].nunique()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Current visible leader", current_leader["brand"], f"{current_leader['demand_signal_index']:.1f} index")
    col2.metric("Leader changes", len(changes), f"across {unique_weeks} weeks")
    if not changes.empty:
        strongest = changes.iloc[0]
        col3.metric(
            "Strongest overtake",
            f"{strongest['brand']} over {strongest['previous_leader']}",
            f"+{strongest['overtake_margin']:.1f} index pts",
        )
    else:
        col3.metric("Strongest overtake", "None")
    if turnaround is not None:
        col4.metric(
            "Strongest 8-week gain",
            turnaround["brand"],
            f"+{turnaround['turnaround_gain']:.1f} index pts",
        )
    else:
        col4.metric("Strongest 8-week gain", "None")

    if changes.empty:
        st.write(
            f"Within the visible {selected_category} time period, the selected brand leader did not change."
        )
        return changes

    strongest = changes.iloc[0]
    summary_text = (
        f"Within the visible {selected_category} time period, leadership changed {len(changes)} times among the selected brands. "
        f"The strongest overtake was {strongest['brand']} moving ahead of {strongest['previous_leader']} in the week starting "
        f"{strongest['week_start_sunday'].date()}, by {strongest['overtake_margin']:.1f} Demand Signal Index points."
    )
    if turnaround is not None:
        summary_text += (
            f" The strongest non-leadership turnaround was {turnaround['brand']}, gaining "
            f"{turnaround['turnaround_gain']:.1f} index points from {pd.Timestamp(turnaround['turnaround_start_week']).date()} "
            f"to {turnaround['week_start_sunday'].date()}."
        )
    st.write(summary_text)

    with st.expander("Show strongest overtakes"):
        overtake_table = changes[
            ["week_start_sunday", "brand", "previous_leader", "new_leader_index", "previous_leader_index", "overtake_margin"]
        ].head(10).rename(
            columns={
                "week_start_sunday": "Week Start Sunday",
                "brand": "New Leader",
                "previous_leader": "Previous Leader",
                "new_leader_index": "New Leader Index",
                "previous_leader_index": "Previous Leader Index",
                "overtake_margin": "Overtake Margin",
            }
        )
        st.dataframe(overtake_table.round(1), hide_index=True, use_container_width=True)

    return changes


def show_brand_summary(brand_df: pd.DataFrame, selected_brand: str) -> None:
    st.markdown("#### Brand Summary")
    if brand_df.empty:
        st.warning("No rows are available for this brand in the selected period.")
        return

    latest_week = brand_df["week_start_sunday"].max()
    earliest_week = brand_df["week_start_sunday"].min()
    latest = brand_df[brand_df["week_start_sunday"] == latest_week].sort_values("rank_in_category")
    earliest = brand_df[brand_df["week_start_sunday"] == earliest_week]

    best_latest = latest.iloc[0]
    avg_latest_signal = latest["demand_signal_index"].mean()
    avg_earliest_signal = earliest["demand_signal_index"].mean()
    avg_change = avg_latest_signal - avg_earliest_signal
    best_rank = brand_df["rank_in_category"].min()
    worst_rank = brand_df["rank_in_category"].max()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Latest strongest category", best_latest["category"], f"Rank {int(best_latest['rank_in_category'])}")
    col2.metric("Latest avg signal", f"{avg_latest_signal:.1f}", f"{avg_change:+.1f} vs start")
    col3.metric("Best rank in period", int(best_rank))
    col4.metric("Weakest rank in period", int(worst_rank))

    direction = "improved" if avg_change > 0 else "declined" if avg_change < 0 else "held steady"
    st.write(
        f"For {selected_brand}, the selected period runs from {earliest_week.date()} to {latest_week.date()}. "
        f"The latest strongest category is {best_latest['category']} at rank {int(best_latest['rank_in_category'])}. "
        f"Average Demand Signal Index across visible categories {direction} by {avg_change:.1f} points from the start of the period."
    )


def show_forecast_summary(view: pd.DataFrame, selected_category: str) -> None:
    st.markdown("#### 13-Week Forecast Summary")
    if view.empty:
        st.warning("Select at least one brand to summarize the forecast.")
        return

    first_week = view["forecast_week_start_sunday"].min()
    final_week = view["forecast_week_start_sunday"].max()
    final = view[view["forecast_week_start_sunday"] == final_week].sort_values(
        "forecast_demand_signal_index",
        ascending=False,
    )
    first = view[view["forecast_week_start_sunday"] == first_week][
        ["brand", "forecast_demand_signal_index"]
    ].rename(columns={"forecast_demand_signal_index": "start_signal"})
    final_with_start = final.merge(first, on="brand", how="left")
    final_with_start["projected_change"] = final_with_start["forecast_demand_signal_index"] - final_with_start["start_signal"]
    biggest_gain = final_with_start.loc[final_with_start["projected_change"].idxmax()]
    biggest_drop = final_with_start.loc[final_with_start["projected_change"].idxmin()]

    band_view = view.copy()
    band_view["band_width"] = band_view["forecast_upper_signal"] - band_view["forecast_lower_signal"]
    widest_band = band_view.loc[band_view["band_width"].idxmax()]
    projected_leader = final.iloc[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Projected final-week leader", projected_leader["brand"], f"{projected_leader['forecast_demand_signal_index']:.1f} index")
    col2.metric("Biggest projected gain", biggest_gain["brand"], f"{biggest_gain['projected_change']:+.1f} pts")
    col3.metric("Biggest projected drop", biggest_drop["brand"], f"{biggest_drop['projected_change']:+.1f} pts")
    col4.metric("Widest uncertainty band", widest_band["brand"], f"{widest_band['band_width']:.1f} pts")

    st.write(
        f"For {selected_category}, this 13-week forward demand signal runs from {first_week.date()} to {final_week.date()}. "
        f"By the final forecast week, {projected_leader['brand']} is projected to have the strongest visible demand signal. "
        f"The biggest projected gain is {biggest_gain['brand']} at {biggest_gain['projected_change']:+.1f} index points, "
        f"while the biggest projected drop is {biggest_drop['brand']} at {biggest_drop['projected_change']:+.1f} index points. "
        f"{widest_band['brand']} has the widest uncertainty band, so interpret that brand's projection with more caution."
    )


@st.cache_data
def load_signal() -> pd.DataFrame:
    if not SIGNAL_PATH.exists():
        return pd.DataFrame()
    df = pd.read_parquet(SIGNAL_PATH)
    df["week_start_sunday"] = pd.to_datetime(df["week_start_sunday"])
    return df


@st.cache_data
def load_forecast() -> pd.DataFrame:
    if not FORECAST_PATH.exists():
        return pd.DataFrame()
    df = pd.read_parquet(FORECAST_PATH)
    df["forecast_issue_date"] = pd.to_datetime(df["forecast_issue_date"]).dt.date
    df["forecast_start_week_sunday"] = pd.to_datetime(df["forecast_start_week_sunday"])
    df["forecast_week_start_sunday"] = pd.to_datetime(df["forecast_week_start_sunday"])
    return df


signal = load_signal()
forecast = load_forecast()
st.title("Footwear Demand Tracker")
st.caption("Weekly athletic footwear Demand Signal Index and 13-week forward demand signal from search-intent data.")

analysis_pages = ["Weekly Leaderboard", "Category Trends", "Brand Page", "13-Week Forward View"]
page = st.sidebar.radio("Analysis Views", analysis_pages)

st.sidebar.divider()
data_control_page = st.sidebar.selectbox(
    "Data Controls & Know-How",
    ["Open an analysis view", "Pipeline Runner", "Data Quality"],
)
if data_control_page != "Open an analysis view":
    page = data_control_page

if signal.empty and page not in ["Data Quality", "Pipeline Runner"]:
    st.warning(
        "No demand signal mart found yet. Open Data Controls & Know-How > Pipeline Runner "
        "and run the full pipeline to create data for this environment."
    )
    st.stop()

if page == "Weekly Leaderboard":
    st.subheader("Weekly Leaderboard")
    col1, col2 = st.columns(2)
    selected_week = col1.selectbox("Sunday-starting week", sorted(signal["week_start_sunday"].dt.date.unique(), reverse=True))
    selected_category = col2.selectbox("Category", sorted(signal["category"].unique()))
    show_leaderboard_guide()
    view = signal[(signal["week_start_sunday"].dt.date == selected_week) & (signal["category"] == selected_category)].sort_values("rank_in_category")
    show_leaderboard_summary(view, selected_category, selected_week)
    table = view[["rank_in_category", "brand", "demand_signal_index", "base_signal", "wow_change_pct", "yoy_change_pct", "category_share_signal", "momentum_label", "confidence_label"]].copy()
    table["demand_signal_index"] = table["demand_signal_index"].round(1)
    table["base_signal"] = table["base_signal"].round(1)
    table["wow_change_pct"] = table["wow_change_pct"].round(1)
    table["yoy_change_pct"] = table["yoy_change_pct"].round(1)
    table["category_share_signal"] = (table["category_share_signal"] * 100).round(1).astype(str) + "%"
    table = table.rename(
        columns={
            "rank_in_category": "Rank",
            "brand": "Brand",
            "demand_signal_index": "Demand Signal Index",
            "base_signal": "Base Signal",
            "wow_change_pct": "WoW Change %",
            "yoy_change_pct": "YoY Change %",
            "category_share_signal": "Category Share Signal",
            "momentum_label": "Momentum",
            "confidence_label": "Confidence",
        }
    )
    st.dataframe(
        table,
        hide_index=True,
        use_container_width=True,
        column_config=LEADERBOARD_COLUMN_CONFIG,
    )

elif page == "Category Trends":
    st.subheader("Category Trends")
    st.info(
        "Each point is a brand's Demand Signal Index for that Sunday-starting week. "
        "A brand reaches 100 only when it is the strongest tracked signal in that category for that week. "
        "If no visible brand is at 100, the weekly leader may be filtered out of the chart."
    )
    selected_category = st.selectbox("Category", sorted(signal["category"].unique()))
    category_df = signal[signal["category"] == selected_category]
    brands = sorted(category_df["brand"].unique())
    selected_brands = st.multiselect("Brands", brands, default=brands[: min(5, len(brands))])
    min_week = category_df["week_start_sunday"].min().date()
    max_week = category_df["week_start_sunday"].max().date()
    date_col1, date_col2 = st.columns(2)
    start_week = date_col1.date_input(
        "Start date",
        value=min_week,
        min_value=min_week,
        max_value=max_week,
    )
    end_week = date_col2.date_input(
        "End date",
        value=max_week,
        min_value=min_week,
        max_value=max_week,
    )
    if start_week > end_week:
        st.warning("Start date must be before end date.")
        st.stop()

    chart_df = category_df[
        (category_df["brand"].isin(selected_brands))
        & (category_df["week_start_sunday"].dt.date >= start_week)
        & (category_df["week_start_sunday"].dt.date <= end_week)
    ]
    leadership_changes = show_category_trend_summary(chart_df, selected_category)
    strongest_turnaround = build_strongest_turnaround(chart_df)

    snapshot_tab, rank_tab, heatmap_tab, small_tab, line_tab = st.tabs(
        ["Current Snapshot", "Rank Movement", "Signal Heatmap", "Small Multiples", "Trend Lines"]
    )

    with snapshot_tab:
        st.caption("Best for seeing who is strongest at the end of the selected period and which brands moved most.")
        if chart_df.empty:
            st.warning("Select at least one brand to show the snapshot.")
        else:
            latest_week = chart_df["week_start_sunday"].max()
            latest = chart_df[chart_df["week_start_sunday"] == latest_week].sort_values("demand_signal_index")
            bar_fig = px.bar(
                latest,
                x="demand_signal_index",
                y="brand",
                color="momentum_label",
                orientation="h",
                text=latest["demand_signal_index"].round(1),
                labels={
                    "demand_signal_index": "Demand Signal Index",
                    "brand": "Brand",
                    "momentum_label": "Momentum",
                },
                color_discrete_map={"Rising": "#0f766e", "Stable": "#64748b", "Falling": "#c2410c"},
            )
            bar_fig.update_layout(yaxis=dict(categoryorder="total ascending"), xaxis_range=[0, 105])
            st.plotly_chart(bar_fig, use_container_width=True)

            movers = latest[
                ["brand", "demand_signal_index", "wow_change_pct", "yoy_change_pct", "rank_in_category", "momentum_label"]
            ].sort_values("wow_change_pct", key=lambda s: s.abs(), ascending=False)
            movers = movers.rename(
                columns={
                    "brand": "Brand",
                    "demand_signal_index": "Demand Signal Index",
                    "wow_change_pct": "WoW Change %",
                    "yoy_change_pct": "YoY Change %",
                    "rank_in_category": "Rank",
                    "momentum_label": "Momentum",
                }
            )
            st.dataframe(movers.round(1), hide_index=True, use_container_width=True)

    with rank_tab:
        st.caption("Best for seeing who overtook whom. Lower rank is better, so rank 1 appears at the top.")
        if chart_df.empty:
            st.warning("Select at least one brand to show rank movement.")
        else:
            rank_fig = px.line(
                chart_df,
                x="week_start_sunday",
                y="rank_in_category",
                color="brand",
                markers=True,
                labels={
                    "week_start_sunday": "Sunday-starting week",
                    "rank_in_category": "Category Rank",
                    "brand": "Brand",
                },
            )
            rank_fig.update_yaxes(autorange="reversed", dtick=1)
            rank_fig.update_layout(yaxis_title="Rank in Category")
            st.plotly_chart(rank_fig, use_container_width=True)

    with heatmap_tab:
        st.caption("Best for scanning periods of strength and weakness. Darker cells mean stronger demand signal.")
        if chart_df.empty:
            st.warning("Select at least one brand to show the heatmap.")
        else:
            heatmap_df = chart_df.copy()
            heatmap_df["Week"] = heatmap_df["week_start_sunday"].dt.strftime("%Y-%m-%d")
            heatmap_pivot = heatmap_df.pivot_table(
                index="brand",
                columns="Week",
                values="demand_signal_index",
                aggfunc="mean",
            )
            heatmap_fig = px.imshow(
                heatmap_pivot,
                aspect="auto",
                color_continuous_scale="Teal",
                labels=dict(x="Sunday-starting week", y="Brand", color="Demand Signal Index"),
            )
            heatmap_fig.update_layout(height=max(360, 46 * len(heatmap_pivot)))
            st.plotly_chart(heatmap_fig, use_container_width=True)

    with small_tab:
        st.caption("Best for comparing each brand's shape without overlapping lines.")
        if chart_df.empty:
            st.warning("Select at least one brand to show small multiples.")
        else:
            small_fig = px.line(
                chart_df,
                x="week_start_sunday",
                y="demand_signal_index",
                facet_col="brand",
                facet_col_wrap=2,
                color="brand",
                labels={
                    "week_start_sunday": "Sunday-starting week",
                    "demand_signal_index": "Demand Signal Index",
                    "brand": "Brand",
                },
            )
            small_fig.add_hline(y=100, line_dash="dot", line_color="#0f766e")
            small_fig.update_yaxes(range=[0, 105])
            small_fig.update_layout(showlegend=False, height=max(420, 230 * ((len(selected_brands) + 1) // 2)))
            st.plotly_chart(small_fig, use_container_width=True)

    with line_tab:
        st.caption("Detailed view with overtake and turnaround annotations. Use this when you need exact event context.")
        fig = px.line(
            chart_df,
            x="week_start_sunday",
            y="demand_signal_index",
            color="brand",
            labels={"week_start_sunday": "Sunday-starting week", "demand_signal_index": "Demand Signal Index"},
        )
        fig.add_hline(y=100, line_dash="dot", line_color="#0f766e", annotation_text="Weekly category leader = 100")
        if not leadership_changes.empty:
            strongest_overtake = leadership_changes.iloc[0]
            overtake_week = strongest_overtake["week_start_sunday"]
            overtake_rows = chart_df[
                (chart_df["week_start_sunday"] == overtake_week)
                & (chart_df["brand"].isin([strongest_overtake["brand"], strongest_overtake["previous_leader"]]))
            ]
            fig.add_vline(
                x=overtake_week,
                line_dash="dash",
                line_color="#b7791f",
                annotation_text="Strongest overtake",
                annotation_position="top left",
            )
            fig.add_trace(
                go.Scatter(
                    x=overtake_rows["week_start_sunday"],
                    y=overtake_rows["demand_signal_index"],
                    mode="markers+text",
                    text=overtake_rows["brand"],
                    textposition="top center",
                    marker=dict(size=13, color="#b7791f", symbol="diamond", line=dict(width=2, color="#ffffff")),
                    name="Strongest overtake point",
                )
            )
        if strongest_turnaround is not None:
            turnaround_brand = strongest_turnaround["brand"]
            turnaround_start_week = pd.Timestamp(strongest_turnaround["turnaround_start_week"])
            turnaround_end_week = pd.Timestamp(strongest_turnaround["week_start_sunday"])
            turnaround_points = pd.DataFrame(
                {
                    "week_start_sunday": [turnaround_start_week, turnaround_end_week],
                    "demand_signal_index": [
                        strongest_turnaround["turnaround_start_index"],
                        strongest_turnaround["demand_signal_index"],
                    ],
                    "label": [f"{turnaround_brand} start", f"{turnaround_brand} gain"],
                }
            )
            fig.add_trace(
                go.Scatter(
                    x=turnaround_points["week_start_sunday"],
                    y=turnaround_points["demand_signal_index"],
                    mode="lines+markers+text",
                    text=turnaround_points["label"],
                    textposition="bottom center",
                    line=dict(color="#c2410c", width=3, dash="dash"),
                    marker=dict(size=12, color="#c2410c", symbol="circle", line=dict(width=2, color="#ffffff")),
                    name="Strongest 8-week gain",
                )
            )
        st.plotly_chart(fig, use_container_width=True)

elif page == "Brand Page":
    st.subheader("Brand Page")
    selected_brand = st.selectbox("Brand", sorted(signal["brand"].unique()))
    all_brand_df = signal[signal["brand"] == selected_brand]
    min_week = all_brand_df["week_start_sunday"].min().date()
    max_week = all_brand_df["week_start_sunday"].max().date()
    date_col1, date_col2 = st.columns(2)
    start_week = date_col1.date_input(
        "Start date",
        value=min_week,
        min_value=min_week,
        max_value=max_week,
        key="brand_start_date",
    )
    end_week = date_col2.date_input(
        "End date",
        value=max_week,
        min_value=min_week,
        max_value=max_week,
        key="brand_end_date",
    )
    if start_week > end_week:
        st.warning("Start date must be before end date.")
        st.stop()

    brand_df = all_brand_df[
        (all_brand_df["week_start_sunday"].dt.date >= start_week)
        & (all_brand_df["week_start_sunday"].dt.date <= end_week)
    ]
    show_brand_summary(brand_df, selected_brand)
    fig = px.line(brand_df, x="week_start_sunday", y="demand_signal_index", color="category", labels={"week_start_sunday": "Sunday-starting week", "demand_signal_index": "Demand Signal Index"})
    st.plotly_chart(fig, use_container_width=True)
    latest = brand_df[brand_df["week_start_sunday"] == brand_df["week_start_sunday"].max()].sort_values("category")
    latest_table = latest[["category", "rank_in_category", "demand_signal_index", "wow_change_pct", "yoy_change_pct", "momentum_label", "confidence_label"]].round(1)
    latest_table = latest_table.rename(
        columns={
            "category": "Category",
            "rank_in_category": "Latest Rank",
            "demand_signal_index": "Demand Signal Index",
            "wow_change_pct": "WoW Change %",
            "yoy_change_pct": "YoY Change %",
            "momentum_label": "Momentum",
            "confidence_label": "Confidence",
        }
    )
    st.dataframe(latest_table, hide_index=True, use_container_width=True)

elif page == "13-Week Forward View":
    st.subheader("13-Week Forward View")
    if forecast.empty:
        st.warning("No 13-week forward demand signal mart found yet. Run python src/build_13w_forecast.py.")
        st.stop()
    issue_date = st.selectbox("Report issue date", sorted(forecast["forecast_issue_date"].unique(), reverse=True))
    issue_df = forecast[forecast["forecast_issue_date"] == issue_date]
    start = issue_df["forecast_start_week_sunday"].iloc[0].date()
    st.caption(f"Forecast start Sunday: {start} | Forecast horizon: 13 weeks")
    selected_category = st.selectbox("Category", sorted(issue_df["category"].unique()))
    category_df = issue_df[issue_df["category"] == selected_category]
    brands = sorted(category_df["brand"].unique())
    selected_brands = st.multiselect("Brands", brands, default=brands[: min(5, len(brands))])
    view = category_df[category_df["brand"].isin(selected_brands)]
    show_forecast_summary(view, selected_category)
    st.dataframe(view[["horizon_week", "forecast_week_start_sunday", "category", "brand", "forecast_demand_signal_index", "forecast_lower_signal", "forecast_upper_signal", "confidence_label", "momentum_label"]].round(1), hide_index=True, use_container_width=True)
    fig = go.Figure()
    for brand, brand_df in view.groupby("brand"):
        fig.add_trace(go.Scatter(x=brand_df["forecast_week_start_sunday"], y=brand_df["forecast_upper_signal"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=brand_df["forecast_week_start_sunday"], y=brand_df["forecast_lower_signal"], mode="lines", line=dict(width=0), fill="tonexty", name=f"{brand} band", opacity=0.15, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=brand_df["forecast_week_start_sunday"], y=brand_df["forecast_demand_signal_index"], mode="lines+markers", name=brand))
    fig.update_layout(yaxis_title="Forecasted demand index", xaxis_title="Forecast week start Sunday")
    st.plotly_chart(fig, use_container_width=True)

elif page == "Pipeline Runner":
    st.subheader("Pipeline Runner")
    st.info(
        "Use this page to refresh Google Trends data, rebuild the demand signal tables, and publish the "
        "13-week forward demand signal. The forecast issue date should usually be the Thursday report date."
    )

    forecast_issue_date = st.date_input("Forecast issue date", value=pd.Timestamp.today().date())
    use_fast_retry = st.checkbox("Use quick fetch retry settings", value=True)

    fetch_args = ["src/fetch_google_trends.py"]
    if use_fast_retry:
        fetch_args.extend(["--retries", "1", "--sleep-seconds", "0"])

    full_pipeline = [
        ("Fetch Google Trends", fetch_args),
        ("Build Clean Trends", ["src/build_clean_trends.py"]),
        ("Build Signal Mart", ["src/build_signal_mart.py"]),
        (
            "Build 13-Week Forecast",
            ["src/build_13w_forecast.py", "--forecast-issue-date", forecast_issue_date.isoformat()],
        ),
        ("Run Data Quality Checks", ["src/data_quality_checks.py"]),
    ]

    if st.button("Run Full Pipeline", type="primary"):
        logs = []
        progress = st.progress(0)
        status = st.empty()
        failed = False
        for index, (step_name, args) in enumerate(full_pipeline, start=1):
            status.write(f"Running: {step_name}")
            result = run_pipeline_step(args)
            logs.append(f"## {step_name}\nExit code: {result.returncode}\n\n{result.stdout}\n{result.stderr}")
            progress.progress(index / len(full_pipeline))
            if result.returncode != 0:
                failed = True
                st.error(f"{step_name} failed. See logs below.")
                break
        if not failed:
            st.cache_data.clear()
            st.success("Pipeline completed. Refresh dashboard pages to see the latest outputs.")
        st.code("\n\n".join(logs), language="text")

    st.divider()
    st.markdown("Run one step")
    selected_step = st.selectbox("Pipeline step", [name for name, _ in PIPELINE_STEPS])
    step_args = dict(PIPELINE_STEPS)[selected_step]
    if selected_step == "Fetch Google Trends":
        step_args = fetch_args
    elif selected_step == "Build 13-Week Forecast":
        step_args = ["src/build_13w_forecast.py", "--forecast-issue-date", forecast_issue_date.isoformat()]

    if st.button("Run Selected Step"):
        result = run_pipeline_step(step_args)
        if result.returncode == 0:
            st.cache_data.clear()
            st.success(f"{selected_step} completed.")
        else:
            st.error(f"{selected_step} failed.")
        st.code(f"Exit code: {result.returncode}\n\n{result.stdout}\n{result.stderr}", language="text")

else:
    st.subheader("Data Quality")
    st.code("\n".join(build_quality_report()), language="text")
    if not signal.empty:
        latest_week = signal["week_start_sunday"].max()
        quality = signal[(signal["week_start_sunday"] == latest_week) & ((signal["confidence_label"] != "High") | (signal["data_quality_flag"] != "OK"))]
        st.dataframe(quality[["week_start_sunday", "category", "brand", "confidence_label", "data_quality_flag"]], hide_index=True, use_container_width=True)
