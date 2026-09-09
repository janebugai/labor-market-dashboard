"""
Labor Market KPIs — a FastAPI dashboard.

A consolidated read on the U.S. labor market built on BLS household (CPS),
establishment (CES) and job-openings (JOLTS) data, plus a Census ACS
cross-section of the states. The page is rendered server-side; charts are
Plotly figures embedded as HTML.

Run locally:   uvicorn dashboard.app:app --reload
Serve (Render): gunicorn dashboard.app:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT
"""
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from plotly.offline.offline import get_plotlyjs_version
from sqlalchemy import create_engine

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "..", "data", "labor_market.db")
PLOTLYJS_VERSION = get_plotlyjs_version()

# --------------------------------------------------------------------------
# Design tokens
# --------------------------------------------------------------------------
INK = "#1A2238"
INK_MUTED = "#5B6B87"
SURFACE = "#FFFFFF"
HAIRLINE = "rgba(26, 34, 56, 0.09)"
GRID = "rgba(26, 34, 56, 0.07)"

ACCENT = "#2457C5"
SERIES = ["#2457C5", "#C9631C", "#0B8A78"]   # categorical, CVD-checked, fixed order
POS = "#1B7A3D"
NEG = "#B23A32"
RECESSION_FILL = "rgba(26, 34, 56, 0.06)"
DIVERGING = [[0.0, "#2457C5"], [0.5, "#EDEBE4"], [1.0, "#C9631C"]]

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

# --------------------------------------------------------------------------
# Data — loaded once at import
# --------------------------------------------------------------------------
_engine = create_engine(f"sqlite:///{DB_PATH}")
BLS = pd.read_sql("SELECT * FROM bls_timeseries", _engine, parse_dates=["date"])
CENSUS = pd.read_sql("SELECT * FROM census_state_snapshot", _engine)
NATIONAL = BLS[BLS["state_fips"].isna()].copy()
STATE = BLS[BLS["state_fips"].notna()].copy()


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
    s = NATIONAL[NATIONAL["series_name"] == name].dropna(subset=["value"]).sort_values("date")
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


def month_label(ts):
    return ts.strftime("%B %Y")


# --------------------------------------------------------------------------
# Chart helpers
# --------------------------------------------------------------------------
def theme(fig, height=380, legend=True):
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=INK_MUTED, family=FONT_STACK, size=12),
        margin=dict(l=48, r=64, t=52, b=36),
        title=dict(font=dict(color=INK, size=15), x=0, xanchor="left", y=0.97),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=INK, font_color="white", bordercolor=INK, font_size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(color=INK_MUTED, size=11), bgcolor="rgba(0,0,0,0)"),
        showlegend=legend,
    )
    fig.update_xaxes(showgrid=False, linecolor=HAIRLINE, tickcolor=HAIRLINE,
                     ticks="outside", tickfont=dict(color=INK_MUTED, size=11))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor="rgba(0,0,0,0)",
                     ticks="", tickfont=dict(color=INK_MUTED, size=11))
    return fig


def add_recessions(fig, label=True):
    for x0, x1, name in RECESSIONS:
        fig.add_vrect(x0=x0, x1=x1, fillcolor=RECESSION_FILL, line_width=0, layer="below")
        if label:
            fig.add_annotation(x=x1, y=1, yref="paper", yanchor="bottom", xanchor="left",
                               text=f"  {name} recession", showarrow=False,
                               font=dict(color=INK_MUTED, size=10))
    return fig


def latest_dot(fig, d, color, y_fmt):
    last = d.iloc[-1]
    fig.add_trace(go.Scatter(
        x=[last["date"]], y=[last["value"]], mode="markers",
        marker=dict(color=color, size=9, line=dict(color=SURFACE, width=2)),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_annotation(x=last["date"], y=last["value"], xshift=8, xanchor="left",
                       yanchor="middle", text=f"<b>{y_fmt(last['value'])}</b>",
                       showarrow=False, font=dict(color=color, size=12))


def line_panel(specs, title, y_fmt, hover_unit="", height=380, rec_label=True):
    """specs: list of (series_name, label, color). One panel, NBER recession shaded."""
    fig = go.Figure()
    multi = len(specs) > 1
    for name, label, color in specs:
        d = NATIONAL[NATIONAL["series_name"] == name].dropna(subset=["value"]).sort_values("date")
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["value"], name=label, mode="lines",
            line=dict(color=color, width=2.2),
            hovertemplate=f"{label}: %{{y:,.1f}}{hover_unit}<extra></extra>",
        ))
        latest_dot(fig, d, color, y_fmt)
    fig.update_layout(title=title)
    theme(fig, height=height, legend=multi)
    add_recessions(fig, label=rec_label)
    span = NATIONAL["date"].max() - NATIONAL["date"].min()
    fig.update_xaxes(range=[NATIONAL["date"].min(), NATIONAL["date"].max() + span * 0.09])
    return fig


def kpi_chart(history, years=5):
    """A compact but real line chart for a KPI card: x = years, y = value."""
    d = history[history["date"] >= history["date"].max() - pd.DateOffset(years=years)]
    fig = go.Figure(go.Scatter(
        x=d["date"], y=d["value"], mode="lines", line=dict(color=ACCENT, width=1.8),
        hovertemplate="%{x|%b %Y}: %{y:,.1f}<extra></extra>",
    ))
    last = d.iloc[-1]
    fig.add_trace(go.Scatter(
        x=[last["date"]], y=[last["value"]], mode="markers",
        marker=dict(color=ACCENT, size=6, line=dict(color=SURFACE, width=1.5)),
        hoverinfo="skip", showlegend=False,
    ))
    fig.update_layout(
        height=150, margin=dict(l=36, r=10, t=6, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False, hovermode="x",
        hoverlabel=dict(bgcolor=INK, font_color="white", font_size=11),
    )
    fig.update_xaxes(tick0="2000-01-01", dtick="M12", tickformat="%Y", showgrid=False,
                     linecolor="rgba(0,0,0,0)", tickcolor="rgba(0,0,0,0)", ticks="",
                     tickfont=dict(color=INK_MUTED, size=10))
    fig.update_yaxes(nticks=4, gridcolor=GRID, zeroline=False, linecolor="rgba(0,0,0,0)",
                     ticks="", tickfont=dict(color=INK_MUTED, size=10))
    return fig


def payroll_change_chart():
    pay = SNAP["nonfarm_payrolls"]["history"].copy()
    pay["change"] = pay["value"].diff() * 1000
    recent = pay.dropna(subset=["change"]).tail(36)
    fig = go.Figure(go.Bar(
        x=recent["date"], y=recent["change"],
        marker_color=[ACCENT if v >= 0 else SERIES[1] for v in recent["change"]],
        hovertemplate="%{x|%b %Y}: %{y:+,.0f} jobs<extra></extra>",
    ))
    fig.update_layout(title="Monthly change in nonfarm payrolls — last 3 years")
    theme(fig, height=340, legend=False)
    fig.update_yaxes(zeroline=True, zerolinecolor=HAIRLINE)
    return fig


def latest_state_frame():
    df = (STATE.dropna(subset=["state_fips", "state_name", "value"])
          .sort_values("date").groupby("state_fips", as_index=False).tail(1).copy())
    df["abbr"] = df["state_fips"].map(STATE_ABBR_BY_FIPS)
    df["gap"] = df["value"] - SNAP["unemployment_rate_national"]["value"]
    return df


def choropleth_chart(states):
    span = max(states["gap"].abs().max(), 0.1)
    fig = go.Figure(go.Choropleth(
        locations=states["abbr"], locationmode="USA-states",
        z=states["gap"], zmin=-span, zmax=span, colorscale=DIVERGING,
        marker_line_color=SURFACE, marker_line_width=1,
        colorbar=dict(title=dict(text="Δ pp", side="right"), thickness=12,
                      len=0.6, x=1.0, tickfont=dict(color=INK_MUTED)),
        customdata=np.stack([states["state_name"], states["value"]], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]:.1f}%  "
                      "(%{z:+.1f} pp vs U.S.)<extra></extra>",
    ))
    fig.update_layout(height=460,
                      geo=dict(scope="usa", bgcolor=SURFACE, lakecolor=SURFACE),
                      margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor=SURFACE,
                      font=dict(color=INK_MUTED, family=FONT_STACK))
    return fig


def ranked_states_chart(states):
    national_now = SNAP["unemployment_rate_national"]["value"]
    ranked = states.sort_values("value")
    ends = pd.concat([ranked.head(10), ranked.tail(10)])
    fig = go.Figure(go.Bar(
        x=ends["value"], y=ends["state_name"], orientation="h",
        marker_color=[SERIES[0] if g <= 0 else SERIES[1] for g in ends["gap"]],
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
    ))
    fig.add_vline(x=national_now, line_color=INK_MUTED, line_dash="dot",
                  annotation_text=f"U.S. {national_now:.1f}%",
                  annotation_font_color=INK_MUTED)
    fig.update_layout(title="Unemployment rate — 10 lowest and 10 highest states")
    theme(fig, height=560, legend=False)
    fig.update_layout(margin=dict(l=110, r=40, t=52, b=44), bargap=0.35)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(ticksuffix="%")
    return fig


def scatter_chart():
    dd = CENSUS.dropna(subset=["bachelors_rate_pct", "unemployment_rate_pct"]).copy()
    x, y = dd["bachelors_rate_pct"].to_numpy(), dd["unemployment_rate_pct"].to_numpy()
    slope, intercept = np.polyfit(x, y, 1)
    corr = float(np.corrcoef(x, y)[0, 1])
    xs = np.linspace(x.min(), x.max(), 50)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=slope * xs + intercept, mode="lines",
                             line=dict(color=INK_MUTED, width=1.5, dash="dot"),
                             name="trend", hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=dd["bachelors_rate_pct"], y=dd["unemployment_rate_pct"], mode="markers",
        marker=dict(size=dd["labor_force"], sizemode="area",
                    sizeref=2.0 * dd["labor_force"].max() / (34 ** 2), sizemin=4,
                    color=ACCENT, opacity=0.75, line=dict(color=SURFACE, width=1)),
        text=dd["state_name"], name="states",
        hovertemplate="<b>%{text}</b><br>Bachelor's: %{x:.1f}%<br>"
                      "Unemployment: %{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(title=f"Bachelor's degree share vs unemployment (r = {corr:.2f})",
                      xaxis_title="Population with a bachelor's degree (%)",
                      yaxis_title="Unemployment rate (%)")
    theme(fig, height=460, legend=False)
    fig.update_xaxes(ticksuffix="%")
    fig.update_yaxes(ticksuffix="%")
    return fig


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
    parts.append(f"Employers added <b>{pay['mom'] * 1000:,.0f}</b> jobs, {vs} the "
                 f"{avg12 * 1000:,.0f}/month pace of the past year.")

    parts.append(f"Labor force participation is <b>{part['value']:.1f}%</b> "
                 f"({part['mom']:+.1f} pp MoM), and job openings stand at "
                 f"<b>{jo['value'] / 1000:.1f}M</b> as of {month_label(jo['date'])}.")
    return " ".join(parts)


# --------------------------------------------------------------------------
# HTML assembly
# --------------------------------------------------------------------------
_PLOT_CONFIG = {"displayModeBar": False, "responsive": True}


def fig_div(fig, div_id):
    height = fig.layout.height or 380
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id=div_id,
                       default_width="100%", default_height=f"{height}px",
                       config=_PLOT_CONFIG)


def kpi_cards():
    cards = []
    for name in ["unemployment_rate_national", "nonfarm_payrolls", "labor_force_participation",
                 "u6_underemployment", "job_openings", "avg_hourly_earnings"]:
        snap, meta = SNAP[name], SERIES_META[name]
        cards.append(dict(
            label=meta["label"], tag=meta["tag"],
            value=fmt_value(name, snap["value"]) if snap else "—",
            mom=fmt_delta(name, snap["mom"]) if snap else "—",
            yoy=fmt_delta(name, snap["yoy"]) if snap else "—",
            cls=delta_class(name, snap["mom"]) if snap else "flat",
            chart=fig_div(kpi_chart(snap["history"]), f"kpi-{name}") if snap else "",
        ))
    return cards


def html_table(rows, headers, aligns):
    def cell(tag, value, align):
        return f'<{tag} class="{align}">{value}</{tag}>'
    head = "".join(cell("th", h, a) for h, a in zip(headers, aligns))
    body = "".join(
        "<tr>" + "".join(cell("td", c, a) for c, a in zip(r, aligns)) + "</tr>"
        for r in rows
    )
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def state_table_html(states):
    rows = [
        (r["state_name"], f"{r['value']:.1f}", f"{r['gap']:+.1f}")
        for _, r in states.sort_values("value").iterrows()
    ]
    return html_table(rows, ["State", "Unemployment rate (%)", "vs U.S. (pp)"],
                      ["left", "right", "right"])


def demo_table_html():
    rows = [
        (r["state_name"], f"{r['labor_force']:,.0f}", f"{r['unemployed']:,.0f}",
         f"{r['bachelors_degree']:,.0f}", f"{r['total_population']:,.0f}",
         f"{r['unemployment_rate_pct']:.1f}", f"{r['bachelors_rate_pct']:.1f}")
        for _, r in CENSUS.sort_values("state_name").iterrows()
    ]
    return html_table(
        rows,
        ["State", "Labor force", "Unemployed", "Bachelor's degree", "Population",
         "Unemployment rate (%)", "Bachelor's rate (%)"],
        ["left", "right", "right", "right", "right", "right", "right"],
    )


def build_context():
    states = latest_state_frame()
    national_now = SNAP["unemployment_rate_national"]["value"]
    return dict(
        plotlyjs_version=PLOTLYJS_VERSION,
        period=month_label(LATEST_PERIOD),
        summary=build_summary(),
        kpis=kpi_cards(),
        chart_unemployment=fig_div(line_panel(
            [("unemployment_rate_national", "U-3 headline", SERIES[0]),
             ("u6_underemployment", "U-6 underemployment", SERIES[1])],
            "Unemployment and underemployment rates", lambda v: f"{v:.1f}%", "%"), "c-unemp"),
        chart_payroll=fig_div(payroll_change_chart(), "c-pay"),
        chart_participation=fig_div(line_panel(
            [("labor_force_participation", "Participation (16+)", SERIES[0]),
             ("employment_population_ratio", "Employment-pop. ratio (16+)", SERIES[1]),
             ("prime_age_epop", "Prime-age employment (25–54)", SERIES[2])],
            "Labor force participation and employment rates", lambda v: f"{v:.1f}%", "%"), "c-part"),
        chart_wages=fig_div(line_panel(
            [("avg_hourly_earnings", "Avg hourly earnings", SERIES[0])],
            "Average hourly earnings", lambda v: f"${v:.2f}", height=320, rec_label=False), "c-wage"),
        chart_hours=fig_div(line_panel(
            [("avg_weekly_hours", "Avg weekly hours", SERIES[2])],
            "Average weekly hours", lambda v: f"{v:.1f}", " hrs", height=320, rec_label=False), "c-hrs"),
        chart_openings=fig_div(line_panel(
            [("job_openings", "Job openings", SERIES[0])],
            "Job openings (thousands)", lambda v: f"{v/1000:.1f}M", "K", height=320, rec_label=False), "c-open"),
        chart_quits=fig_div(line_panel(
            [("quits_rate", "Quits rate", SERIES[1])],
            "Quits rate (% of employment)", lambda v: f"{v:.1f}%", "%", height=320, rec_label=False), "c-quit"),
        chart_choropleth=fig_div(choropleth_chart(states), "c-map"),
        chart_ranked=fig_div(ranked_states_chart(states), "c-rank"),
        chart_scatter=fig_div(scatter_chart(), "c-scatter"),
        national_now=f"{national_now:.1f}",
        state_period=month_label(states["date"].max()),
        state_table=state_table_html(states),
        demo_table=demo_table_html(),
        jolts_period=month_label(SNAP["job_openings"]["date"]),
        state_data_period=month_label(STATE["date"].max()),
    )


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
app = FastAPI(title="Labor Market KPIs")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", build_context())


@app.get("/health")
def health():
    return {"status": "ok", "latest_period": month_label(LATEST_PERIOD)}
