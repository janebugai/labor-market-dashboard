"""
Labor Market Dashboard — Streamlit app.

Run with: streamlit run dashboard/app.py
"""
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.colors import sample_colorscale
import streamlit as st
from sqlalchemy import create_engine

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "labor_market.db")

COLORS = {
    "brown": "#25170B",
    "blue": "#7591BC",
    "blue_light": "#7A96C1",
    "navy": "#0D1A32",
    "green": "#253F2B",
    "yellow": "#C5BF50",
    "sky": "#63BAE4",
    "background": "#F0F0F0",
    "surface": "#FBF8F1",
    "gold": "#C99A45",
}
STATE_COLOR_SCALE = [
    [0.0, "#4747FF"],
    [0.5, "#C4C3CA"],
    [1.0, "#FFC067"],
]

STATE_ABBREVIATIONS_BY_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY", "72": "PR",
}

st.set_page_config(page_title="Labor Market Dashboard", layout="wide")

st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: {COLORS["background"]};
        color: {COLORS["navy"]};
    }}
    .block-container,
    [data-testid="stMainBlockContainer"] {{
        padding-top: 2.5rem;
    }}
    [data-testid="stHeader"] {{
        background-color: rgba(240, 240, 240, 0.92);
    }}
    h1, h2, h3, h4, p, label {{
        color: {COLORS["navy"]};
    }}
    [data-testid="stCaptionContainer"] {{
        margin-bottom: 1.5rem;
    }}
    button[data-baseweb="tab"] {{
        color: {COLORS["blue"]};
        font-weight: 600;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {COLORS["green"]};
        border-bottom-color: {COLORS["yellow"]};
    }}
    [data-testid="stMetric"] {{
        background-color: {COLORS["surface"]};
        border: 1px solid rgba(13, 26, 50, 0.10);
        border-radius: 1rem;
        padding: 0.75rem;
    }}
    [data-testid="stVerticalBlockBorderWrapper"],
    [data-testid="stPlotlyChart"],
    [data-testid="stDataFrame"] {{
        background-color: {COLORS["surface"]};
        border: 1px solid rgba(13, 26, 50, 0.10);
        border-radius: 1rem;
        box-shadow: 0 8px 24px rgba(13, 26, 50, 0.06);
    }}
    [data-testid="stPlotlyChart"] {{
        overflow: hidden;
    }}
    .hero-kicker {{
        color: {COLORS["gold"]};
        font-size: 0.78rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        margin-bottom: 0.5rem;
        text-transform: uppercase;
    }}
    .hero-title {{
        color: {COLORS["navy"]};
        font-family: Georgia, "Times New Roman", serif;
        font-size: clamp(2.25rem, 5vw, 4rem);
        font-weight: 700;
        letter-spacing: -0.04em;
        line-height: 1;
        margin: 0 0 0.65rem;
    }}
    .hero-period {{
        color: {COLORS["gold"]};
        font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: clamp(0.9rem, 1.8vw, 1.4rem);
        font-weight: 700;
        letter-spacing: 0;
        margin-left: 0.6rem;
        vertical-align: 0.35em;
        white-space: nowrap;
    }}
    .hero-copy {{
        color: {COLORS["blue"]};
        font-size: 0.9rem;
        line-height: 1.6;
        margin-bottom: 1rem;
        max-width: none;
    }}
    .kpi-card {{
        background: {COLORS["surface"]};
        border: 1px solid rgba(13, 26, 50, 0.10);
        border-radius: 1rem;
        box-shadow: 0 8px 24px rgba(13, 26, 50, 0.06);
        margin-bottom: 1rem;
        min-height: 138px;
        padding: 1rem 1.1rem;
    }}
    .kpi-top {{
        align-items: center;
        display: flex;
        gap: 0.65rem;
    }}
    .kpi-icon {{
        align-items: center;
        background: {COLORS["navy"]};
        border-radius: 50%;
        color: {COLORS["surface"]};
        display: inline-flex;
        font-size: 1rem;
        height: 2.35rem;
        justify-content: center;
        width: 2.35rem;
    }}
    .kpi-label {{
        color: {COLORS["navy"]};
        font-size: 0.68rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        line-height: 1.2;
        text-transform: uppercase;
    }}
    .kpi-value {{
        color: {COLORS["navy"]};
        font-size: 1.65rem;
        font-weight: 800;
        line-height: 1.2;
        margin: 0.65rem 0 0.2rem;
    }}
    .kpi-note {{
        color: {COLORS["blue"]};
        font-size: 0.72rem;
    }}
    hr {{
        border-color: {COLORS["blue_light"]};
    }}
    @media (max-width: 768px) {{
        .block-container,
        [data-testid="stMainBlockContainer"] {{
            padding: 2.25rem 0.75rem 1rem;
        }}
        h1 {{
            font-size: 1.75rem !important;
            line-height: 1.2 !important;
        }}
        h2, h3 {{
            font-size: 1.25rem !important;
        }}
        [data-testid="stCaptionContainer"] {{
            margin-bottom: 0.75rem;
        }}
        [data-testid="stHorizontalBlock"] {{
            flex-direction: column;
            gap: 0.5rem;
        }}
        [data-testid="stColumn"],
        [data-testid="column"] {{
            width: 100% !important;
            min-width: 100% !important;
            flex: 1 1 100% !important;
        }}
        [data-testid="stPlotlyChart"],
        [data-testid="stDataFrame"] {{
            width: 100% !important;
            overflow-x: auto;
        }}
        .hero-title {{
            font-size: 2.3rem;
        }}
        .kpi-card {{
            min-height: 120px;
        }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data(db_modified_at):
    engine = create_engine(f"sqlite:///{DB_PATH}")
    bls_df = pd.read_sql("SELECT * FROM bls_timeseries", engine, parse_dates=["date"])
    census_df = pd.read_sql("SELECT * FROM census_state_snapshot", engine)
    return bls_df, census_df


def apply_chart_theme(fig):
    fig.update_layout(
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        font={"color": COLORS["navy"]},
        title={"x": 0.5, "xanchor": "center"},
        title_font={"color": COLORS["navy"]},
        hoverlabel={
            "bgcolor": COLORS["navy"],
            "font_color": COLORS["surface"],
            "bordercolor": COLORS["sky"],
        },
    )
    fig.update_xaxes(
        gridcolor="rgba(122, 150, 193, 0.25)",
        linecolor=COLORS["blue_light"],
        tickcolor=COLORS["blue_light"],
    )
    fig.update_yaxes(
        gridcolor="rgba(122, 150, 193, 0.25)",
        linecolor=COLORS["blue_light"],
        tickcolor=COLORS["blue_light"],
    )
    return fig


def series_snapshot(bls_data, series_name):
    series = (
        bls_data[bls_data["series_name"] == series_name]
        .dropna(subset=["value"])
        .sort_values("date")
    )
    if series.empty:
        return None, None, None

    latest = series.iloc[-1]
    previous_value = series.iloc[-2]["value"] if len(series) > 1 else latest["value"]
    return latest["value"], latest["value"] - previous_value, latest["date"]


def render_kpi(icon, label, value, note):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-top">
                <span class="kpi-icon">{icon}</span>
                <span class="kpi-label">{label}</span>
            </div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

try:
    bls_df, census_df = load_data(os.path.getmtime(DB_PATH))
except Exception as e:
    st.error(
        "Couldn't load the database. Run the ETL pipeline first:\n\n"
        "```\npython etl/fetch_bls.py\npython etl/fetch_census.py\npython etl/transform.py\n```"
    )
    st.stop()

dashboard = st.container()

# --- Consolidated dashboard ---
national_dates = bls_df.loc[bls_df["state_fips"].isna(), "date"]
latest_period = (
    national_dates.max().strftime("%B %Y") if not national_dates.dropna().empty else ""
)

with dashboard:
    st.markdown(
        f"""
        <div class="hero-kicker">U.S. economic indicators</div>
        <div class="hero-title">Labor Market<span class="hero-period">{latest_period}</span></div>
        <div class="hero-copy">
            Explore the latest trends in employment, unemployment,
            wages, and state labor-force conditions.
        </div>
        """,
        unsafe_allow_html=True,
    )

    unemployment, unemployment_delta, _ = series_snapshot(
        bls_df, "unemployment_rate_national"
    )
    payrolls, payrolls_delta, _ = series_snapshot(
        bls_df, "nonfarm_payrolls"
    )
    earnings, earnings_delta, _ = series_snapshot(
        bls_df, "avg_hourly_earnings"
    )
    earnings_change_pct = (
        earnings_delta / (earnings - earnings_delta) * 100
        if earnings is not None and earnings_delta is not None
        else None
    )

    kpi_columns = st.columns(3, gap="medium")
    with kpi_columns[0]:
        render_kpi(
            "◎",
            "Unemployment rate",
            f"{unemployment:.1f}%" if unemployment is not None else "—",
            (
                f"{unemployment_delta:+.1f} pp vs last month"
                if unemployment_delta is not None
                else "Latest national reading"
            ),
        )
    with kpi_columns[1]:
        render_kpi(
            "↗",
            "Total nonfarm payrolls",
            f"{payrolls / 1000:.1f}M" if payrolls is not None else "—",
            (
                f"{payrolls_delta:+,.0f}K vs last month"
                if payrolls_delta is not None
                else "Latest national reading"
            ),
        )
    with kpi_columns[2]:
        render_kpi(
            "$",
            "Average hourly earnings",
            f"${earnings:.2f}" if earnings is not None else "—",
            (
                f"{earnings_change_pct:+.1f}% vs last month"
                if earnings_change_pct is not None
                else "Latest national reading"
            ),
        )
    national_charts = [
        (
            "unemployment_rate_national",
            "National Unemployment Rate",
            "Unemployment Rate (%)",
            "#5A5AEE",
        ),
        (
            "nonfarm_payrolls",
            "Total Nonfarm Payroll Employment",
            "Employment (thousands)",
            "#668294",
        ),
        (
            "avg_hourly_earnings",
            "Average Hourly Earnings",
            "U.S. Dollars per Hour",
            "#B07D4A",
        ),
    ]

    chart_columns = st.columns(3, gap="medium")
    for column, (series_name, title, y_label, line_color) in zip(
        chart_columns, national_charts
    ):
        with column:
            plot_df = bls_df[bls_df["series_name"] == series_name]
            if plot_df.empty:
                st.warning(f"No data available for {title}.")
                continue

            fig = px.line(
                plot_df,
                x="date",
                y="value",
                title=title,
                labels={"value": y_label, "date": ""},
            )
            fig.update_traces(
                line={"color": line_color, "width": 3},
                hovertemplate=f"%{{x|%B %Y}}<br>{y_label}: %{{y:,.2f}}<extra></extra>"
            )
            fig.update_layout(
                height=360,
                margin={"l": 40, "r": 15, "t": 55, "b": 35},
                title_font_size=16,
            )
            apply_chart_theme(fig)
            st.plotly_chart(
                fig,
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
            )

    st.divider()

    state_series = [s for s in bls_df["series_name"].unique() if s.startswith("unemployment_rate_")
                     and s != "unemployment_rate_national"]
    state_df = bls_df[bls_df["series_name"].isin(state_series)]

    if not state_df.empty:
        latest_state_df = (
            state_df.dropna(subset=["state_fips", "state_name", "value"])
            .sort_values("date")
            .groupby("state_fips", as_index=False)
            .tail(1)
        )
        latest_state_df["state_abbr"] = latest_state_df["state_fips"].map(
            STATE_ABBREVIATIONS_BY_FIPS
        )

        latest_period = latest_state_df["date"].max().strftime("%B %Y")
        color_range = (
            latest_state_df["value"].min(),
            latest_state_df["value"].max(),
        )
        fig = px.choropleth(
            latest_state_df,
            locations="state_abbr",
            locationmode="USA-states",
            color="value",
            color_continuous_scale=STATE_COLOR_SCALE,
            range_color=color_range,
            scope="usa",
            hover_name="state_name",
            hover_data={
                "state_abbr": False,
                "value": ":.1f",
                "date": "|%B %Y",
            },
            labels={"value": "Unemployment Rate (%)", "date": "Period"},
            title=f"State Unemployment Rates — Latest Available ({latest_period})",
        )
        fig.update_traces(
            marker_line_color=COLORS["surface"],
            marker_line_width=1.5,
            hovertemplate="<b>%{hovertext}</b><br>%{z:.1f}%<extra></extra>",
            selector={"type": "choropleth"},
        )

        state_labels = latest_state_df[latest_state_df["state_fips"] != "72"]
        fig.add_trace(
            go.Scattergeo(
                geo="geo",
                locations=state_labels["state_abbr"],
                locationmode="USA-states",
                text=state_labels["state_abbr"],
                mode="text",
                textfont={"size": 10, "color": COLORS["navy"]},
                hoverinfo="skip",
                showlegend=False,
            )
        )

        puerto_rico = latest_state_df[latest_state_df["state_fips"] == "72"]
        if not puerto_rico.empty:
            puerto_rico_rate = puerto_rico.iloc[0]["value"]
            color_span = color_range[1] - color_range[0]
            color_position = (
                (puerto_rico_rate - color_range[0]) / color_span
                if color_span
                else 0.5
            )
            puerto_rico_color = sample_colorscale(
                STATE_COLOR_SCALE, [color_position]
            )[0]
            puerto_rico_lon = [
                -67.27, -67.17, -66.74, -66.36, -65.90, -65.63,
                -65.65, -65.87, -66.30, -66.72, -67.02, -67.21, -67.27,
            ]
            puerto_rico_lat = [
                18.36, 18.49, 18.51, 18.47, 18.44, 18.36,
                18.18, 18.03, 17.96, 17.98, 18.06, 18.18, 18.36,
            ]
            fig.add_trace(
                go.Scattergeo(
                    geo="geo2",
                    lat=puerto_rico_lat,
                    lon=puerto_rico_lon,
                    mode="lines",
                    fill="toself",
                    fillcolor=puerto_rico_color,
                    line={"color": COLORS["surface"], "width": 1.5},
                    text=[f"Puerto Rico<br>{puerto_rico_rate:.1f}%"]
                    * len(puerto_rico_lon),
                    hovertemplate="%{text}<extra></extra>",
                    showlegend=False,
                )
            )
            fig.add_trace(
                go.Scattergeo(
                    geo="geo2",
                    lat=[18.23],
                    lon=[-66.45],
                    mode="text",
                    text=["PR"],
                    textfont={"size": 10, "color": COLORS["navy"]},
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

        fig.update_layout(
            height=620,
            dragmode=False,
            uirevision="fixed-state-map",
            margin={"l": 0, "r": 0, "t": 90, "b": 0},
            paper_bgcolor=COLORS["surface"],
            font={"color": COLORS["navy"]},
            title={"x": 0.5, "xanchor": "center"},
            title_font={"color": COLORS["navy"], "size": 18},
            coloraxis_colorbar={
                "title": "",
                "orientation": "h",
                "x": 0.02,
                "xanchor": "left",
                "y": 1.04,
                "yanchor": "bottom",
                "len": 0.32,
                "thickness": 14,
                "ticksuffix": "%",
                "tickfont": {"color": COLORS["navy"]},
            },
            geo2={
                "domain": {"x": [0.72, 0.90], "y": [0.04, 0.25]},
                "projection": {"type": "mercator", "scale": 55},
                "center": {"lat": 18.2208, "lon": -66.5901},
                "showland": False,
                "showocean": True,
                "oceancolor": COLORS["surface"],
                "showcountries": False,
                "showframe": True,
                "framecolor": COLORS["blue"],
            },
        )
        fig.update_geos(
            bgcolor=COLORS["surface"],
            lakecolor=COLORS["sky"],
            coastlinecolor=COLORS["blue"],
        )
        if not puerto_rico.empty:
            fig.add_annotation(
                x=0.81,
                y=0.27,
                xref="paper",
                yref="paper",
                text=f"<b>Puerto Rico</b> · {puerto_rico_rate:.1f}%",
                showarrow=False,
                font={"size": 11, "color": COLORS["navy"]},
            )

        st.plotly_chart(
            fig,
            width="stretch",
            config={
                "scrollZoom": False,
                "displayModeBar": False,
                "doubleClick": False,
            },
        )
    else:
        st.info("No state-level series found. Add more state series IDs in etl/fetch_bls.py.")

    st.divider()
    st.markdown(
        f'<div style="font-size:18px;font-weight:600;color:{COLORS["navy"]};">'
        "State Demographics</div>",
        unsafe_allow_html=True,
    )

    census_table = (
        census_df.drop(columns=["state_fips"])
        .rename(columns={
            "state_name": "State",
            "labor_force": "Labor Force",
            "unemployed": "Unemployed",
            "bachelors_degree": "Bachelor's Degree",
            "total_population": "Total Population",
            "unemployment_rate_pct": "Unemployment Rate (%)",
            "bachelors_rate_pct": "Bachelor's Degree Rate (%)",
        })
        .sort_values("State")
    )
    st.dataframe(
        census_table,
        width="stretch",
        height=600,
        hide_index=True,
        column_config={
            "State": st.column_config.TextColumn(alignment="center"),
            "Labor Force": st.column_config.NumberColumn(alignment="center"),
            "Unemployed": st.column_config.NumberColumn(alignment="center"),
            "Bachelor's Degree": st.column_config.NumberColumn(alignment="center"),
            "Total Population": st.column_config.NumberColumn(alignment="center"),
            "Unemployment Rate (%)": st.column_config.NumberColumn(
                alignment="center", format="%.2f"
            ),
            "Bachelor's Degree Rate (%)": st.column_config.NumberColumn(
                alignment="center", format="%.2f"
            ),
        },
    )

st.divider()
st.caption(
    "Sources: U.S. Bureau of Labor Statistics (bls.gov/developers) and "
    "U.S. Census Bureau ACS (census.gov/data/developers)."
)
