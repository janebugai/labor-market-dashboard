"""
Fetch time series data from the BLS Public Data API (v2).

Docs: https://www.bls.gov/developers/api_signature_v2.htm

"""
import os
import json
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

BLS_API_KEY = os.getenv("BLS_API_KEY")
BLS_BASE_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# National series (all seasonally adjusted).
#   LNS14000000              Unemployment rate (U-3)
#   LNS13327709              Underemployment rate (U-6)
#   LNS11300000              Labor force participation rate
#   LNS12300000              Employment-population ratio, 16+
#   LNS12300060              Employment-population ratio, prime age (25-54)
#   CES0000000001            Total nonfarm payroll employment (thousands)
#   CES0500000003            Average hourly earnings, total private
#   CES0500000002            Average weekly hours, total private
#   JTS000000000000000JOL    Job openings, total nonfarm (thousands) — JOLTS
#   JTS000000000000000QUR    Quits rate, total nonfarm — JOLTS
NATIONAL_SERIES_IDS = {
    "unemployment_rate_national": "LNS14000000",
    "u6_underemployment": "LNS13327709",
    "labor_force_participation": "LNS11300000",
    "employment_population_ratio": "LNS12300000",
    "prime_age_epop": "LNS12300060",
    "nonfarm_payrolls": "CES0000000001",
    "avg_hourly_earnings": "CES0500000003",
    "avg_weekly_hours": "CES0500000002",
    "job_openings": "JTS000000000000000JOL",
    "quits_rate": "JTS000000000000000QUR",
}

# State FIPS codes, including Washington, D.C. and Puerto Rico, matching the
# geographies returned by the Census API's `for=state:*` query.
STATE_FIPS = {
    "alabama": "01",
    "alaska": "02",
    "arizona": "04",
    "arkansas": "05",
    "california": "06",
    "colorado": "08",
    "connecticut": "09",
    "delaware": "10",
    "district_of_columbia": "11",
    "florida": "12",
    "georgia": "13",
    "hawaii": "15",
    "idaho": "16",
    "illinois": "17",
    "indiana": "18",
    "iowa": "19",
    "kansas": "20",
    "kentucky": "21",
    "louisiana": "22",
    "maine": "23",
    "maryland": "24",
    "massachusetts": "25",
    "michigan": "26",
    "minnesota": "27",
    "mississippi": "28",
    "missouri": "29",
    "montana": "30",
    "nebraska": "31",
    "nevada": "32",
    "new_hampshire": "33",
    "new_jersey": "34",
    "new_mexico": "35",
    "new_york": "36",
    "north_carolina": "37",
    "north_dakota": "38",
    "ohio": "39",
    "oklahoma": "40",
    "oregon": "41",
    "pennsylvania": "42",
    "rhode_island": "44",
    "south_carolina": "45",
    "south_dakota": "46",
    "tennessee": "47",
    "texas": "48",
    "utah": "49",
    "vermont": "50",
    "virginia": "51",
    "washington": "53",
    "west_virginia": "54",
    "wisconsin": "55",
    "wyoming": "56",
    "puerto_rico": "72",
}

STATE_SERIES_IDS = {
    f"unemployment_rate_{state}": f"LASST{fips}0000000000003"
    for state, fips in STATE_FIPS.items()
}
SERIES_IDS = {**NATIONAL_SERIES_IDS, **STATE_SERIES_IDS}

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bls_raw.json")


def fetch_series(series_ids, start_year, end_year):
    """
    Fetch BLS series in batches and combine them into one API-style response.
    """
    headers = {"Content-type": "application/json"}
    series_ids = list(series_ids)
    batch_size = 50 if BLS_API_KEY else 25
    combined = {
        "status": "REQUEST_SUCCEEDED",
        "responseTime": 0,
        "message": [],
        "Results": {"series": []},
    }

    if not BLS_API_KEY:
        print("WARNING: No BLS_API_KEY found in .env — using unregistered "
              "limits (25 queries/day, 25 series/query, 10yr range).")

    for offset in range(0, len(series_ids), batch_size):
        batch = series_ids[offset:offset + batch_size]
        payload = {
            "seriesid": batch,
            "startyear": str(start_year),
            "endyear": str(end_year),
        }
        if BLS_API_KEY:
            payload["registrationkey"] = BLS_API_KEY

        response = requests.post(BLS_BASE_URL, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        result = response.json()

        if result.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS API request failed: {result.get('message')}")

        combined["responseTime"] += result.get("responseTime", 0)
        combined["message"].extend(result.get("message", []))
        combined["Results"]["series"].extend(result["Results"]["series"])

        if offset + batch_size < len(series_ids):
            time.sleep(1)

    return combined


def main():
    current_year = datetime.now().year
    start_year = current_year - 10  # last 10 years; extend to 20 with a registered key

    print(f"Fetching {len(SERIES_IDS)} BLS series from {start_year} to {current_year}...")
    result = fetch_series(SERIES_IDS.values(), start_year, current_year)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Saved raw BLS response to {OUTPUT_PATH}")
    time.sleep(1)  # be polite to the API


if __name__ == "__main__":
    main()
