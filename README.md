# Labor Market Dashboard

An interactive dashboard for reading the U.S. labor market — unemployment,
underemployment, participation, payrolls, wages, job openings, and a state
cross-section — built on public data from the Bureau of Labor Statistics (BLS)
and the U.S. Census Bureau.

## Why this project

Labor market health is a core macro indicator for financial services, economic
research, and workforce planning. This project is an end-to-end data pipeline:
API ingestion → transformation → storage → interactive visualization.

## Architecture

```
[BLS API]   ─┐
             ├─→ [ETL scripts] ─→ [SQLite] ─→ [Streamlit dashboard]
[Census API] ─┘
```

## What's in the dashboard

A four-tab Streamlit app (`dashboard/app.py`):

| Tab | Content |
|-----|---------|
| **Overview** | Six KPI cards (latest value, MoM/YoY change, a 5-year mini chart), a computed "what changed this month" summary, the U-3 vs U-6 series, and a monthly payroll-change bar chart. |
| **Labor supply & churn** | Participation, employment-population ratio (16+ and prime-age 25–54), average weekly hours, and JOLTS job openings and quits. |
| **States** | A choropleth of each state's deviation from the national unemployment rate, a ranked bar chart of the 10 highest/lowest states, and a full table. |
| **Demographics** | Bachelor's-degree share vs unemployment scatter (bubble size = labor force) with an OLS trend line, plus a state detail table. |

Time-series panels carry NBER recession shading, labelled latest-value markers,
and a unified hover. Deltas are coloured by whether the move is favourable for
that specific metric (a falling unemployment rate is good; a falling
participation rate is not).

## Data

`etl/transform.py` loads two tables into `data/labor_market.db`:

- **`bls_timeseries`** — monthly series, seasonally adjusted, 2016–present:
  - *National (10):* unemployment rate (U-3), underemployment rate (U-6),
    labor force participation, employment-population ratio, prime-age (25–54)
    employment rate, total nonfarm payrolls, average hourly earnings, average
    weekly hours, JOLTS job openings, JOLTS quits rate.
  - *State (52):* unemployment rate for every state, D.C. and Puerto Rico.
- **`census_state_snapshot`** — one row per state from the ACS 1-year
  estimates: labor force, unemployed, bachelor's-degree holders, population,
  and derived rates.

JOLTS series run one month behind the household and payroll data; state
unemployment (LAUS) lags the national release by about two weeks. The
generated `data/labor_market.db` is committed so the dashboard runs without
API keys — keys are only needed to refresh it.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. **To view the dashboard**, just launch it — the demo database is included:
   ```bash
   streamlit run dashboard/app.py
   ```
   Open http://localhost:8501.

3. **To refresh the data**, get free API keys and re-run the ETL:
   - BLS: https://data.bls.gov/registrationEngine/ (raises limits from
     25 queries/day, 25 series/query, 10-year range to 500/day, 50/query,
     20-year range)
   - Census: https://api.census.gov/data/key_signup.html (optional, higher
     rate limits)

   Put them in a `.env` file in the project root:
   ```
   BLS_API_KEY=your_key_here
   CENSUS_API_KEY=your_key_here
   ```

   Then:
   ```bash
   python etl/fetch_bls.py      # → data/bls_raw.json
   python etl/fetch_census.py   # → data/census_raw.json
   python etl/transform.py      # → data/labor_market.db
   ```

   `fetch_bls.py` pulls the last 10 years through the current year; the
   dashboard's "latest month" and all currency notes update themselves from
   whatever is in the database.

## Project structure

```
labor-market-dashboard/
├── etl/
│   ├── fetch_bls.py       # Pull national + state BLS series (CPS, CES, JOLTS)
│   ├── fetch_census.py    # Pull Census ACS labor-force / education data
│   └── transform.py       # Clean, join, and load into SQLite
├── data/
│   ├── labor_market.db    # SQLite database (committed; regenerate with the ETL)
│   └── *.json             # Raw API responses (gitignored)
├── dashboard/
│   └── app.py             # Streamlit dashboard
├── notebooks/
│   └── exploration.ipynb  # Exploratory analysis
├── requirements.txt
└── README.md
```

## Roadmap / stretch goals

- [x] Annotate recessions on the timelines (NBER shading)
- [ ] Add a forecasting model (Prophet / ARIMA) for the next-month unemployment rate
- [ ] Deploy to Streamlit Community Cloud
- [ ] Add a caching layer to respect API rate limits on refresh

## Data sources

- [BLS Public Data API](https://www.bls.gov/developers/) — Current Population
  Survey (CPS), Current Employment Statistics (CES), Job Openings and Labor
  Turnover Survey (JOLTS)
- [Census Bureau API](https://www.census.gov/data/developers.html) — American
  Community Survey (ACS) 1-year estimates
