"""
Labor Market Dashboard — Streamlit app.

A consolidated read on the U.S. labor market built on BLS household (CPS),
establishment (CES) and job-openings (JOLTS) data, plus a Census ACS
cross-section of the states.

Run with: streamlit run dashboard/app.py
"""
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "labor_market.db")

# --------------------------------------------------------------------------
# Design tokens
# --------------------------------------------------------------------------
INK = "#1A2238"
INK_MUTED = "#5B6B87"
PAGE_BG = "#F4F3EF"
SURFACE = "#FFFFFF"
HAIRLINE = "rgba(26, 34, 56, 0.09)"
GRID = "rgba(26, 34, 56, 0.07)"

ACCENT = "#2457C5"        # primary / single-series
SERIES = ["#2457C5", "#C9631C", "#0B8A78"]   # categorical, CVD-checked, fixed order
POS = "#1B7A3D"
NEG = "#B23A32"
RECESSION_FILL = "rgba(26, 34, 56, 0.06)"

# Diverging scale for state deviation from the national rate:
# below national (better) -> blue, at national -> paper, above (worse) -> orange
DIVERGING = [[0.0, "#2457C5"], [0.5, "#EDEBE4"], [1.0, "#C9631C"]]

# NBER recession(s) inside the 2016+ window.
RECESSIONS = [("2020-02-01", "2020-04-30", "COVID-19")]

FONT_STACK = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

# --------------------------------------------------------------------------
# Series metadata
# --------------------------------------------------------------------------
# kind: "pct" (percentage points), "level_k" (thousands), "dollar", "hours"
# good: which direction is favourable, for colouring deltas
SERIES_META = {
    "unemployment_rate_national": dict(label="Unemployment rate", tag="U-3 · CPS", kind="pct", good="down"),
    "u6_underemployment": dict(label="Underemployment rate", tag="U-6 · CPS", kind="pct", good="down"),
    "labor_force_participation": dict(label="Labor force participation", tag="16+ · CPS", kind="pct", good="up"),
    "employment_population_ratio": dict(label="Employment-population ratio", tag="16+ · CPS", kind="pct", good="up"),
    "prime_age_epop": dict(label="Prime-age employment rate", tag="25–54 · CPS", kind="pct", good="up"),
    "nonfarm_payrolls": dict(label="Nonfarm payrolls", tag="CES", kind="level_k", good="up"),
    "avg_hourly_earnings": dict(label="Average hourly earnings", tag="Total private · CES", kind="dollar", good="up"),
    "avg_weekly_hours": dict(label="Average weekly hours", tag="Total private · CES", kind="hours", good="up"),
    "job_openings": dict(label="Job openings", tag="JOLTS", kind="level_k", good="up"),
    "quits_rate": dict(label="Quits rate", tag="JOLTS", kind="pct", good="up"),
}

STATE_ABBR_BY_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY", "72": "PR",
}

st.set_page_config(page_title="U.S. Labor Market Dashboard", layout="wide")

st.markdown(
    f"""
    <style>
    .stApp {{ background-color: {PAGE_BG}; }}
    .block-container, [data-testid="stMainBlockContainer"] {{
        padding-top: 2.75rem; max-width: 1280px;
    }}
    [data-testid="stHeader"] {{ background: transparent; }}
    html, body, [class*="css"] {{ font-family: {FONT_STACK}; }}
    h1, h2, h3, h4, p, label, span, div {{ color: {INK}; }}

    .eyebrow {{
        color: {INK_MUTED}; font-size: 0.72rem; font-weight: 700;
        letter-spacing: 0.16em; text-transform: uppercase;
    }}
    .hero-title {{
        font-family: Georgia, 'Times New Roman', serif;
        font-size: clamp(2rem, 4.4vw, 3.4rem); font-weight: 700;
        letter-spacing: -0.03em; line-height: 1.02; margin: 0.35rem 0 0.5rem;
    }}
    .hero-period {{ color: {ACCENT}; font-family: {FONT_STACK};
        font-weight: 700; font-size: 0.5em; vertical-align: 0.42em; }}
    .hero-sub {{ color: {INK_MUTED}; font-size: 0.95rem; line-height: 1.6;
        max-width: 62ch; margin-bottom: 0.4rem; }}

    .summary {{
        background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 14px;
        padding: 1.1rem 1.3rem; margin: 1.4rem 0 0.4rem;
    }}
    .summary p {{ margin: 0; font-size: 0.95rem; line-height: 1.65; color: {INK}; }}
    .summary .lede {{ color: {INK_MUTED}; font-size: 0.72rem; font-weight: 700;
        letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 0.5rem; }}

    .kpi {{
        background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 14px;
        padding: 1rem 1.1rem 0.9rem; height: 100%;
    }}
    .kpi-head {{ min-height: 2.4rem; }}
    .kpi-spark {{ margin-top: 0.75rem; height: 44px; }}
    .kpi-spark svg {{ height: 44px; overflow: visible; }}
    .kpi-label {{ display: block; font-size: 0.82rem; font-weight: 700;
        color: {INK}; line-height: 1.25; }}
    .kpi-tag {{ display: block; font-size: 0.64rem; font-weight: 600;
        letter-spacing: 0.07em; text-transform: uppercase; color: {INK_MUTED};
        margin-top: 0.15rem; }}
    .kpi-value {{ font-size: 1.9rem; font-weight: 800; letter-spacing: -0.02em;
        margin: 0.35rem 0 0.15rem; line-height: 1; }}
    .kpi-delta {{ font-size: 0.8rem; font-weight: 600; }}
    .kpi-delta .muted {{ color: {INK_MUTED}; font-weight: 500; }}
    .pos {{ color: {POS}; }} .neg {{ color: {NEG}; }} .flat {{ color: {INK_MUTED}; }}

    [data-testid="stMetric"] {{
        background: {SURFACE}; border: 1px solid {HAIRLINE};
        border-radius: 12px; padding: 0.85rem 1rem;
    }}
    [data-testid="stPlotlyChart"] {{
        background: {SURFACE}; border: 1px solid {HAIRLINE};
        border-radius: 14px; padding: 0.4rem 0.6rem; overflow: hidden;
    }}
    [data-testid="stDataFrame"] {{ border: 1px solid {HAIRLINE}; border-radius: 12px; }}

    button[data-baseweb="tab"] {{ font-weight: 600; color: {INK_MUTED}; }}
    button[data-baseweb="tab"][aria-selected="true"] {{ color: {INK}; }}
    [data-baseweb="tab-highlight"] {{ background-color: {ACCENT}; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 1.5rem; border-bottom: 1px solid {HAIRLINE}; }}

    .section-h {{ font-size: 1.15rem; font-weight: 700; margin: 1.6rem 0 0.2rem; }}
    .section-note {{ color: {INK_MUTED}; font-size: 0.82rem; margin-bottom: 0.6rem; }}
    .foot {{ color: {INK_MUTED}; font-size: 0.78rem; line-height: 1.7;
        border-top: 1px solid {HAIRLINE}; margin-top: 2.5rem; padding-top: 1rem; }}
    hr {{ border-color: {HAIRLINE}; }}

    @media (max-width: 768px) {{
        .block-container, [data-testid="stMainBlockContainer"] {{ padding: 2.25rem 0.8rem 1rem; }}
        [data-testid="stHorizontalBlock"] {{ flex-direction: column; gap: 0.6rem; }}
        [data-testid="stColumn"] {{ width: 100% !important; min-width: 100% !important; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
@st.cache_data
def load_data(_db_mtime):
    engine = create_engine(f"sqlite:///{DB_PATH}")
    bls = pd.read_sql("SELECT * FROM bls_timeseries", engine, parse_dates=["date"])
    census = pd.read_sql("SELECT * FROM census_state_snapshot", engine)
    return bls, census


try:
    bls_df, census_df = load_data(os.path.getmtime(DB_PATH))
except Exception:
    st.error(
        "Couldn't load the database. Run the ETL pipeline first:\n\n"
        "```\npython etl/fetch_bls.py\npython etl/fetch_census.py\npython etl/transform.py\n```"
    )
    st.stop()

national_df = bls_df[bls_df["state_fips"].isna()].copy()
state_df = bls_df[bls_df["state_fips"].notna()].copy()


# --------------------------------------------------------------------------
# Formatting + snapshots
# --------------------------------------------------------------------------
def fmt_value(name, v):
    if v is None or pd.isna(v):
        return "—"
    kind = SERIES_META[name]["kind"]
    if kind == "pct":
        return f"{v:.1f}%"
    if kind == "dollar":
        return f"${v:,.2f}"
    if kind == "hours":
        return f"{v:.1f} hrs"
    if kind == "level_k":
        return f"{v / 1000:,.1f}M" if v >= 1000 else f"{v:,.0f}K"
    return f"{v:,.1f}"


def fmt_delta(name, d):
    if d is None or pd.isna(d):
        return "—"
    kind = SERIES_META[name]["kind"]
    if kind == "pct":
        return f"{d:+.1f} pp"
    if kind == "dollar":
        return f"{d:+.2f}"
    if kind == "hours":
        return f"{d:+.1f} hr"
    if kind == "level_k":
        return f"{d:+,.0f}K"
    return f"{d:+,.1f}"


def delta_class(name, d):
    if d is None or pd.isna(d) or abs(d) < 1e-9:
        return "flat"
    good = SERIES_META[name]["good"]
    improving = (d > 0 and good == "up") or (d < 0 and good == "down")
    return "pos" if improving else "neg"


def snapshot(name):
    s = (
        national_df[national_df["series_name"] == name]
        .dropna(subset=["value"])
        .sort_values("date")
    )
    if s.empty:
        return None
    latest = s.iloc[-1]
    prev = s.iloc[-2] if len(s) > 1 else latest
    year_ago_rows = s[s["date"] == latest["date"] - pd.DateOffset(years=1)]
    year_ago = year_ago_rows["value"].iloc[0] if not year_ago_rows.empty else np.nan
    return dict(
        value=latest["value"],
        mom=latest["value"] - prev["value"],
        yoy=latest["value"] - year_ago if pd.notna(year_ago) else np.nan,
        date=latest["date"],
        history=s,
    )


SNAP = {name: snapshot(name) for name in SERIES_META}
LATEST_PERIOD = max(s["date"] for s in SNAP.values() if s)


# --------------------------------------------------------------------------
# Chart helpers
# --------------------------------------------------------------------------
def theme(fig, height=380, legend=True):
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(color=INK_MUTED, family=FONT_STACK, size=12),
        margin=dict(l=48, r=64, t=52, b=36),
        title=dict(font=dict(color=INK, size=15), x=0, xanchor="left", y=0.97),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=INK, font_color="white", bordercolor=INK, font_size=12),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            font=dict(color=INK_MUTED, size=11), bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=legend,
    )
    fig.update_xaxes(
        showgrid=False, linecolor=HAIRLINE, tickcolor=HAIRLINE,
        ticks="outside", tickfont=dict(color=INK_MUTED, size=11),
    )
    fig.update_yaxes(
        gridcolor=GRID, zeroline=False, linecolor="rgba(0,0,0,0)",
        ticks="", tickfont=dict(color=INK_MUTED, size=11),
    )
    return fig


def add_recessions(fig, label=True):
    for x0, x1, name in RECESSIONS:
        fig.add_vrect(x0=x0, x1=x1, fillcolor=RECESSION_FILL, line_width=0, layer="below")
        if label:
            fig.add_annotation(
                x=x1, y=1, yref="paper", yanchor="bottom", xanchor="left",
                text=f"  {name} recession", showarrow=False,
                font=dict(color=INK_MUTED, size=10),
            )
    return fig


def latest_dot(fig, d, color, y_fmt):
    last = d.iloc[-1]
    fig.add_trace(go.Scatter(
        x=[last["date"]], y=[last["value"]], mode="markers",
        marker=dict(color=color, size=9, line=dict(color=SURFACE, width=2)),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_annotation(
        x=last["date"], y=last["value"], xshift=8, xanchor="left", yanchor="middle",
        text=f"<b>{y_fmt(last['value'])}</b>", showarrow=False,
        font=dict(color=color, size=12),
    )


def line_panel(specs, title, y_fmt, hover_unit="", height=380, recessions=True, rec_label=True):
    """specs: list of (series_name, label, color)."""
    fig = go.Figure()
    multi = len(specs) > 1
    for name, label, color in specs:
        d = national_df[national_df["series_name"] == name].dropna(subset=["value"]).sort_values("date")
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["value"], name=label, mode="lines",
            line=dict(color=color, width=2.2),
            hovertemplate=f"{label}: %{{y:,.1f}}{hover_unit}<extra></extra>",
        ))
        latest_dot(fig, d, color, y_fmt)
    fig.update_layout(title=title)
    theme(fig, height=height, legend=multi)
    if recessions:
        add_recessions(fig, label=rec_label)
    # headroom on the right so the latest-value labels aren't clipped
    span = national_df["date"].max() - national_df["date"].min()
    fig.update_xaxes(range=[national_df["date"].min(),
                            national_df["date"].max() + span * 0.09])
    return fig


def sparkline_svg(values, color=ACCENT, width=320, height=44, pad=5):
    vs = [float(v) for v in values if pd.notna(v)]
    if len(vs) < 2:
        return ""
    lo, hi = min(vs), max(vs)
    rng = (hi - lo) or 1.0
    n = len(vs)
    xs = [pad + i * (width - 2 * pad) / (n - 1) for i in range(n)]
    ys = [height - pad - (v - lo) / rng * (height - 2 * pad) for v in vs]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" preserveAspectRatio="none" '
        f'style="display:block">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linejoin="round" vector-effect="non-scaling-stroke"/>'
        f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="2.6" fill="{color}" '
        f'vector-effect="non-scaling-stroke"/></svg>'
    )


def render_kpi(col, name, spark_months=36):
    snap = SNAP[name]
    meta = SERIES_META[name]
    if snap is None:
        spark, dc, mom, yoy, val = "", "flat", "—", "—", "—"
    else:
        spark = sparkline_svg(snap["history"]["value"].tail(spark_months))
        dc = delta_class(name, snap["mom"])
        mom = fmt_delta(name, snap["mom"])
        yoy = fmt_delta(name, snap["yoy"])
        val = fmt_value(name, snap["value"])
    with col:
        st.markdown(
            f"""
            <div class="kpi">
              <div class="kpi-head">
                <span class="kpi-label">{meta['label']}</span>
                <span class="kpi-tag">{meta['tag']}</span>
              </div>
              <div class="kpi-value">{val}</div>
              <div class="kpi-delta">
                <span class="{dc}">{mom} MoM</span>
                <span class="muted"> &nbsp;·&nbsp; {yoy} YoY</span>
              </div>
              <div class="kpi-spark">{spark}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------
# Narrative
# --------------------------------------------------------------------------
def month_label(ts):
    return ts.strftime("%B %Y")


def build_summary():
    u3 = SNAP["unemployment_rate_national"]
    pay = SNAP["nonfarm_payrolls"]
    part = SNAP["labor_force_participation"]
    jo = SNAP["job_openings"]
    parts = []

    if abs(u3["mom"]) < 0.05:
        move = "was unchanged at"
    else:
        move = ("rose" if u3["mom"] > 0 else "fell") + f" {abs(u3['mom']):.1f} pp to"
    sentence = f"The unemployment rate {move} <b>{u3['value']:.1f}%</b> in {month_label(u3['date'])}"
    if pd.notna(u3["yoy"]) and abs(u3["yoy"]) >= 0.05:
        direction = "below" if u3["yoy"] < 0 else "above"
        sentence += f", {abs(u3['yoy']):.1f} pp {direction} a year earlier"
    parts.append(sentence + ".")

    mom_jobs = pay["history"]["value"].diff().dropna()
    avg12 = mom_jobs.tail(12).mean()
    if abs(pay["mom"] - avg12) < 15:
        vs = "in line with"
    else:
        vs = "above" if pay["mom"] > avg12 else "below"
    parts.append(
        f"Employers added <b>{pay['mom'] * 1000:,.0f}</b> jobs, {vs} the "
        f"{avg12 * 1000:,.0f}/month pace of the past year."
    )

    parts.append(
        f"Labor force participation is <b>{part['value']:.1f}%</b> "
        f"({part['mom']:+.1f} pp MoM), and job openings stand at "
        f"<b>{jo['value'] / 1000:.1f}M</b> as of {month_label(jo['date'])}."
    )
    return " ".join(parts)


# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------
st.markdown(
    f"""
    <div class="eyebrow">U.S. economic indicators</div>
    <div class="hero-title">The Labor Market
        <span class="hero-period">{month_label(LATEST_PERIOD)}</span></div>
    <div class="hero-sub">Employment, unemployment, participation, wages and job
        turnover — the monthly picture from the Bureau of Labor Statistics,
        with a state cross-section from the Census Bureau.</div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f'<div class="summary"><div class="lede">What changed this month</div>'
    f'<p>{build_summary()}</p></div>',
    unsafe_allow_html=True,
)

tab_overview, tab_detail, tab_states, tab_demo = st.tabs(
    ["Overview", "Labor supply & churn", "States", "Demographics"]
)

# ==========================================================================
# OVERVIEW
# ==========================================================================
with tab_overview:
    st.markdown('<div class="section-h">Headline indicators</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="section-note">Latest reading, month-over-month and '
        f'year-over-year change. Sparklines show the last three years.</div>',
        unsafe_allow_html=True,
    )

    row1 = st.columns(3, gap="medium")
    for col, name in zip(row1, ["unemployment_rate_national", "nonfarm_payrolls", "labor_force_participation"]):
        render_kpi(col, name)
    row2 = st.columns(3, gap="medium")
    for col, name in zip(row2, ["u6_underemployment", "job_openings", "avg_hourly_earnings"]):
        render_kpi(col, name)

    st.markdown('<div class="section-h">Unemployment</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-note">U-3 is the headline rate; U-6 adds '
        'discouraged, marginally-attached and involuntary part-time workers.</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        line_panel(
            [("unemployment_rate_national", "U-3 headline", SERIES[0]),
             ("u6_underemployment", "U-6 underemployment", SERIES[1])],
            "Unemployment and underemployment rates",
            lambda v: f"{v:.1f}%", hover_unit="%",
        ),
        width="stretch",
        config={"displayModeBar": False, "responsive": True},
    )

    st.markdown('<div class="section-h">Payroll employment</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-note">Monthly change in total nonfarm payrolls '
        '(establishment survey). Bars above zero are net hiring.</div>',
        unsafe_allow_html=True,
    )
    pay = SNAP["nonfarm_payrolls"]["history"].copy()
    pay["change"] = pay["value"].diff() * 1000
    recent = pay.dropna(subset=["change"]).tail(36)
    bar = go.Figure(go.Bar(
        x=recent["date"], y=recent["change"],
        marker_color=[ACCENT if v >= 0 else SERIES[1] for v in recent["change"]],
        hovertemplate="%{x|%b %Y}: %{y:+,.0f} jobs<extra></extra>",
    ))
    bar.update_layout(title="Monthly change in nonfarm payrolls — last 3 years")
    theme(bar, height=340, legend=False)
    bar.update_yaxes(ticksuffix="", zeroline=True, zerolinecolor=HAIRLINE)
    st.plotly_chart(bar, width="stretch", config={"displayModeBar": False})

# ==========================================================================
# LABOR SUPPLY & CHURN
# ==========================================================================
with tab_detail:
    st.markdown('<div class="section-h">Who is working</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-note">Participation counts everyone 16+ in the labor '
        'force; the prime-age employment rate (25–54) strips out retirement and '
        'schooling effects and is the cleaner read on labor-market slack.</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        line_panel(
            [("labor_force_participation", "Participation (16+)", SERIES[0]),
             ("employment_population_ratio", "Employment-pop. ratio (16+)", SERIES[1]),
             ("prime_age_epop", "Prime-age employment (25–54)", SERIES[2])],
            "Labor force participation and employment rates",
            lambda v: f"{v:.1f}%", hover_unit="%",
        ),
        width="stretch",
        config={"displayModeBar": False},
    )

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.markdown('<div class="section-h">Wages</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-note">Average hourly earnings, total private.</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(
            line_panel(
                [("avg_hourly_earnings", "Avg hourly earnings", SERIES[0])],
                "Average hourly earnings", lambda v: f"${v:.2f}", hover_unit="",
                height=320, rec_label=False,
            ),
            width="stretch", config={"displayModeBar": False},
        )
    with c2:
        st.markdown('<div class="section-h">Hours</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-note">Average weekly hours — an early '
                    'signal; firms cut hours before headcount.</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(
            line_panel(
                [("avg_weekly_hours", "Avg weekly hours", SERIES[2])],
                "Average weekly hours", lambda v: f"{v:.1f}", hover_unit=" hrs",
                height=320, rec_label=False,
            ),
            width="stretch", config={"displayModeBar": False},
        )

    st.markdown('<div class="section-h">Job openings and quits</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-note">From JOLTS (one month behind the household '
        'and payroll data). A falling quits rate means workers are less '
        'confident about switching jobs.</div>',
        unsafe_allow_html=True,
    )
    d1, d2 = st.columns(2, gap="medium")
    with d1:
        st.plotly_chart(
            line_panel(
                [("job_openings", "Job openings", SERIES[0])],
                "Job openings (thousands)", lambda v: f"{v/1000:.1f}M", hover_unit="K",
                height=320, rec_label=False,
            ),
            width="stretch", config={"displayModeBar": False},
        )
    with d2:
        st.plotly_chart(
            line_panel(
                [("quits_rate", "Quits rate", SERIES[1])],
                "Quits rate (% of employment)", lambda v: f"{v:.1f}%", hover_unit="%",
                height=320, rec_label=False,
            ),
            width="stretch", config={"displayModeBar": False},
        )

# ==========================================================================
# STATES
# ==========================================================================
with tab_states:
    latest_state = (
        state_df.dropna(subset=["state_fips", "state_name", "value"])
        .sort_values("date")
        .groupby("state_fips", as_index=False)
        .tail(1)
        .copy()
    )
    latest_state["abbr"] = latest_state["state_fips"].map(STATE_ABBR_BY_FIPS)
    state_period = latest_state["date"].max()
    national_now = SNAP["unemployment_rate_national"]["value"]
    latest_state["gap"] = latest_state["value"] - national_now
    span = max(latest_state["gap"].abs().max(), 0.1)

    st.markdown('<div class="section-h">State unemployment vs the national rate</div>',
                unsafe_allow_html=True)
    st.markdown(
        f'<div class="section-note">Deviation from the national U-3 rate of '
        f'{national_now:.1f}%. Blue states are running below the national rate, '
        f'orange above. State figures lag the national release — latest available '
        f'is {month_label(state_period)}.</div>',
        unsafe_allow_html=True,
    )

    choro = go.Figure(go.Choropleth(
        locations=latest_state["abbr"], locationmode="USA-states",
        z=latest_state["gap"], zmin=-span, zmax=span,
        colorscale=DIVERGING, marker_line_color=SURFACE, marker_line_width=1,
        colorbar=dict(title=dict(text="Δ pp", side="right"), thickness=12,
                      len=0.6, x=1.0, tickfont=dict(color=INK_MUTED)),
        customdata=np.stack([latest_state["state_name"], latest_state["value"]], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]:.1f}%  "
                      "(%{z:+.1f} pp vs U.S.)<extra></extra>",
    ))
    choro.update_layout(
        height=460, geo=dict(scope="usa", bgcolor=SURFACE, lakecolor=SURFACE),
        margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor=SURFACE,
        font=dict(color=INK_MUTED, family=FONT_STACK),
    )
    st.plotly_chart(choro, width="stretch",
                    config={"displayModeBar": False, "scrollZoom": False})

    st.markdown('<div class="section-h">Ranked — highest and lowest</div>',
                unsafe_allow_html=True)
    ranked = latest_state.sort_values("value")
    ends = pd.concat([ranked.head(10), ranked.tail(10)])
    rank_fig = go.Figure(go.Bar(
        x=ends["value"], y=ends["state_name"], orientation="h",
        marker_color=[SERIES[0] if g <= 0 else SERIES[1] for g in ends["gap"]],
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
    ))
    rank_fig.add_vline(x=national_now, line_color=INK_MUTED, line_dash="dot",
                       annotation_text=f"U.S. {national_now:.1f}%",
                       annotation_font_color=INK_MUTED)
    rank_fig.update_layout(title="Unemployment rate — 10 lowest and 10 highest states")
    theme(rank_fig, height=560, legend=False)
    rank_fig.update_layout(margin=dict(l=110, r=40, t=52, b=44), bargap=0.35)
    rank_fig.update_yaxes(autorange="reversed")
    rank_fig.update_xaxes(ticksuffix="%")
    st.plotly_chart(rank_fig, width="stretch", config={"displayModeBar": False})

    st.markdown('<div class="section-h">All states</div>', unsafe_allow_html=True)
    table = (
        latest_state[["state_name", "value", "gap"]]
        .rename(columns={"state_name": "State", "value": "Unemployment rate (%)",
                         "gap": "vs U.S. (pp)"})
        .sort_values("Unemployment rate (%)")
        .reset_index(drop=True)
    )
    st.dataframe(
        table, width="stretch", hide_index=True, height=440,
        column_config={
            "Unemployment rate (%)": st.column_config.NumberColumn(format="%.1f"),
            "vs U.S. (pp)": st.column_config.NumberColumn(format="%+.1f"),
        },
    )

# ==========================================================================
# DEMOGRAPHICS
# ==========================================================================
with tab_demo:
    st.markdown('<div class="section-h">Education and unemployment across states</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="section-note">Each dot is a state; size is the size of its '
        'labor force. Source: Census Bureau American Community Survey, 2023 '
        '1-year estimates (a different vintage and methodology from the monthly '
        'CPS rate above).</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "“Bachelor's degree” here is the count with a bachelor's as their highest "
        "degree, as a share of total population."
    )
    dd = census_df.dropna(subset=["bachelors_rate_pct", "unemployment_rate_pct"]).copy()
    x, y = dd["bachelors_rate_pct"].to_numpy(), dd["unemployment_rate_pct"].to_numpy()
    slope, intercept = np.polyfit(x, y, 1)
    corr = float(np.corrcoef(x, y)[0, 1])
    xs = np.linspace(x.min(), x.max(), 50)

    scatter = go.Figure()
    scatter.add_trace(go.Scatter(
        x=xs, y=slope * xs + intercept, mode="lines",
        line=dict(color=INK_MUTED, width=1.5, dash="dot"),
        name="trend", hoverinfo="skip",
    ))
    scatter.add_trace(go.Scatter(
        x=dd["bachelors_rate_pct"], y=dd["unemployment_rate_pct"], mode="markers",
        marker=dict(
            size=dd["labor_force"], sizemode="area",
            sizeref=2.0 * dd["labor_force"].max() / (34 ** 2), sizemin=4,
            color=ACCENT, opacity=0.75, line=dict(color=SURFACE, width=1),
        ),
        text=dd["state_name"], name="states",
        hovertemplate="<b>%{text}</b><br>Bachelor's+: %{x:.1f}%<br>"
                      "Unemployment: %{y:.1f}%<extra></extra>",
    ))
    scatter.update_layout(
        title=f"Bachelor's degree share vs unemployment (r = {corr:.2f})",
        xaxis_title="Population with a bachelor's degree (%)",
        yaxis_title="Unemployment rate (%)",
    )
    theme(scatter, height=460, legend=False)
    scatter.update_xaxes(ticksuffix="%")
    scatter.update_yaxes(ticksuffix="%")
    st.plotly_chart(scatter, width="stretch", config={"displayModeBar": False})

    st.markdown('<div class="section-h">State detail</div>', unsafe_allow_html=True)
    demo_table = (
        census_df.drop(columns=["state_fips"])
        .rename(columns={
            "state_name": "State", "labor_force": "Labor force",
            "unemployed": "Unemployed", "bachelors_degree": "Bachelor's degree",
            "total_population": "Population",
            "unemployment_rate_pct": "Unemployment rate (%)",
            "bachelors_rate_pct": "Bachelor's rate (%)",
        })
        .sort_values("State")
        .reset_index(drop=True)
    )
    st.dataframe(
        demo_table, width="stretch", hide_index=True, height=520,
        column_config={
            "Labor force": st.column_config.NumberColumn(format="%,d"),
            "Unemployed": st.column_config.NumberColumn(format="%,d"),
            "Bachelor's degree": st.column_config.NumberColumn(format="%,d"),
            "Population": st.column_config.NumberColumn(format="%,d"),
            "Unemployment rate (%)": st.column_config.NumberColumn(format="%.1f"),
            "Bachelor's rate (%)": st.column_config.NumberColumn(format="%.1f"),
        },
    )

# --------------------------------------------------------------------------
# Footer
# --------------------------------------------------------------------------
jolts = SNAP["job_openings"]["date"]
st.markdown(
    f"""
    <div class="foot">
      <b>Sources.</b> U.S. Bureau of Labor Statistics — Current Population Survey
      (CPS), Current Employment Statistics (CES) and Job Openings and Labor
      Turnover Survey (JOLTS), via the
      <a href="https://www.bls.gov/developers/">BLS Public Data API</a>.
      Census Bureau American Community Survey 1-year estimates, via the
      <a href="https://www.census.gov/data/developers.html">Census API</a>.<br>
      <b>Currency.</b> Household and payroll series through {month_label(LATEST_PERIOD)};
      JOLTS through {month_label(jolts)}; state unemployment through
      {month_label(state_df['date'].max())}; ACS cross-section is 2023.
      All BLS series are seasonally adjusted. Rebuild with the ETL scripts in
      <code>etl/</code> to refresh.
    </div>
    """,
    unsafe_allow_html=True,
)
