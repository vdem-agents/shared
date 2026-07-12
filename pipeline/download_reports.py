#!/usr/bin/env python3
"""
Download human rights report text for all countries from two sources:

  State Dept (Country Reports on Human Rights Practices)
    Index: state.gov/reports/{year}-country-reports-on-human-rights-practices/
    Strategy: scrape index for country sub-page URLs → scrape HTML from each sub-page
    Saves: source-docs/state-dept/{year}/{slug}.pdf  (PDFs only; HTML ingest via ingest.py)

  Freedom House (Freedom in the World)
    Note: FH report year = data year + 1 (FiW 2021 covers 2020 data)
    Strategy: scrape each country page at freedomhouse.org/country/{slug}/freedom-world/{report_year}
    Saves: processed-text/freedom-house/{year}/{slug}.txt  (plain text, no conversion needed)

No official bulk API exists for either source. Both are HTML-scraped.

Usage:
  python3 download_reports.py --source state-dept --year 2020
  python3 download_reports.py --source freedom-house --year 2020
  python3 download_reports.py --source both --year 2020
  python3 download_reports.py --source state-dept --year 2020 --countries nigeria kenya
"""

import argparse
import json
import time
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent / "source-docs"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed-text"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# FH report year for a given data year (FiW covers the prior calendar year)
# Website URL structure (freedomhouse.org/country/{slug}/freedom-world/{report_year})
# only goes back to FiW 2017 (data year 2016); pre-2016 returns 404.
# Ceiling: V-Dem v15 and State Dept both top out at 2024.
FH_REPORT_YEAR = {
    2016: 2017, 2017: 2018, 2018: 2019, 2019: 2020,
    2020: 2021, 2021: 2022, 2022: 2023, 2023: 2024, 2024: 2025,
}

# Complete Freedom House slug list (from freedomhouse.org/country/scores)
FH_COUNTRIES = {
    "Abkhazia": "abkhazia",
    "Afghanistan": "afghanistan",
    "Albania": "albania",
    "Algeria": "algeria",
    "Andorra": "andorra",
    "Angola": "angola",
    "Antigua and Barbuda": "antigua-and-barbuda",
    "Argentina": "argentina",
    "Armenia": "armenia",
    "Australia": "australia",
    "Austria": "austria",
    "Azerbaijan": "azerbaijan",
    "Bahrain": "bahrain",
    "Bangladesh": "bangladesh",
    "Barbados": "barbados",
    "Belarus": "belarus",
    "Belgium": "belgium",
    "Belize": "belize",
    "Benin": "benin",
    "Bhutan": "bhutan",
    "Bolivia": "bolivia",
    "Bosnia and Herzegovina": "bosnia-and-herzegovina",
    "Botswana": "botswana",
    "Brazil": "brazil",
    "Brunei": "brunei",
    "Bulgaria": "bulgaria",
    "Burkina Faso": "burkina-faso",
    "Burundi": "burundi",
    "Cabo Verde": "cabo-verde",
    "Cambodia": "cambodia",
    "Cameroon": "cameroon",
    "Canada": "canada",
    "Central African Republic": "central-african-republic",
    "Chad": "chad",
    "Chile": "chile",
    "China": "china",
    "Colombia": "colombia",
    "Comoros": "comoros",
    "Costa Rica": "costa-rica",
    "Crimea": "crimea",
    "Croatia": "croatia",
    "Cuba": "cuba",
    "Cyprus": "cyprus",
    "Czechia": "czechia",
    "Cote d'Ivoire": "cote-divoire",
    "Democratic Republic of the Congo": "democratic-republic-congo",
    "Denmark": "denmark",
    "Djibouti": "djibouti",
    "Dominica": "dominica",
    "Dominican Republic": "dominican-republic",
    "Eastern Donbas": "eastern-donbas",
    "Ecuador": "ecuador",
    "Egypt": "egypt",
    "El Salvador": "el-salvador",
    "Equatorial Guinea": "equatorial-guinea",
    "Eritrea": "eritrea",
    "Estonia": "estonia",
    "Eswatini": "eswatini",
    "Ethiopia": "ethiopia",
    "Fiji": "fiji",
    "Finland": "finland",
    "France": "france",
    "Gabon": "gabon",
    "Gaza Strip": "gaza-strip",
    "Georgia": "georgia",
    "Germany": "germany",
    "Ghana": "ghana",
    "Greece": "greece",
    "Grenada": "grenada",
    "Guatemala": "guatemala",
    "Guinea": "guinea",
    "Guinea-Bissau": "guinea-bissau",
    "Guyana": "guyana",
    "Haiti": "haiti",
    "Honduras": "honduras",
    "Hong Kong": "hong-kong",
    "Hungary": "hungary",
    "Iceland": "iceland",
    "India": "india",
    "Indian Kashmir": "indian-kashmir",
    "Indonesia": "indonesia",
    "Iran": "iran",
    "Iraq": "iraq",
    "Ireland": "ireland",
    "Israel": "israel",
    "Italy": "italy",
    "Jamaica": "jamaica",
    "Japan": "japan",
    "Jordan": "jordan",
    "Kazakhstan": "kazakhstan",
    "Kenya": "kenya",
    "Kiribati": "kiribati",
    "Kosovo": "kosovo",
    "Kuwait": "kuwait",
    "Kyrgyzstan": "kyrgyzstan",
    "Laos": "laos",
    "Latvia": "latvia",
    "Lebanon": "lebanon",
    "Lesotho": "lesotho",
    "Liberia": "liberia",
    "Libya": "libya",
    "Liechtenstein": "liechtenstein",
    "Lithuania": "lithuania",
    "Luxembourg": "luxembourg",
    "Madagascar": "madagascar",
    "Malawi": "malawi",
    "Malaysia": "malaysia",
    "Maldives": "maldives",
    "Mali": "mali",
    "Malta": "malta",
    "Marshall Islands": "marshall-islands",
    "Mauritania": "mauritania",
    "Mauritius": "mauritius",
    "Mexico": "mexico",
    "Micronesia": "micronesia",
    "Moldova": "moldova",
    "Monaco": "monaco",
    "Mongolia": "mongolia",
    "Montenegro": "montenegro",
    "Morocco": "morocco",
    "Mozambique": "mozambique",
    "Myanmar": "myanmar",
    "Nagorno-Karabakh": "nagorno-karabakh",
    "Namibia": "namibia",
    "Nauru": "nauru",
    "Nepal": "nepal",
    "Netherlands": "netherlands",
    "New Zealand": "new-zealand",
    "Nicaragua": "nicaragua",
    "Niger": "niger",
    "Nigeria": "nigeria",
    "North Korea": "north-korea",
    "North Macedonia": "north-macedonia",
    "Northern Cyprus": "northern-cyprus",
    "Norway": "norway",
    "Oman": "oman",
    "Pakistan": "pakistan",
    "Pakistani Kashmir": "pakistani-kashmir",
    "Palau": "palau",
    "Panama": "panama",
    "Papua New Guinea": "papua-new-guinea",
    "Paraguay": "paraguay",
    "Peru": "peru",
    "Philippines": "philippines",
    "Poland": "poland",
    "Portugal": "portugal",
    "Qatar": "qatar",
    "Republic of the Congo": "republic-congo",
    "Romania": "romania",
    "Russia": "russia",
    "Rwanda": "rwanda",
    "Samoa": "samoa",
    "San Marino": "san-marino",
    "Saudi Arabia": "saudi-arabia",
    "Senegal": "senegal",
    "Serbia": "serbia",
    "Seychelles": "seychelles",
    "Sierra Leone": "sierra-leone",
    "Singapore": "singapore",
    "Slovakia": "slovakia",
    "Slovenia": "slovenia",
    "Solomon Islands": "solomon-islands",
    "Somalia": "somalia",
    "Somaliland": "somaliland",
    "South Africa": "south-africa",
    "South Korea": "south-korea",
    "South Ossetia": "south-ossetia",
    "South Sudan": "south-sudan",
    "Spain": "spain",
    "Sri Lanka": "sri-lanka",
    "St. Kitts and Nevis": "st-kitts-and-nevis",
    "St. Lucia": "st-lucia",
    "St. Vincent and the Grenadines": "st-vincent-and-grenadines",
    "Sudan": "sudan",
    "Suriname": "suriname",
    "Sweden": "sweden",
    "Switzerland": "switzerland",
    "Syria": "syria",
    "Sao Tome and Principe": "sao-tome-and-principe",
    "Taiwan": "taiwan",
    "Tajikistan": "tajikistan",
    "Tanzania": "tanzania",
    "Thailand": "thailand",
    "The Bahamas": "bahamas",
    "The Gambia": "gambia",
    "Tibet": "tibet",
    "Timor-Leste": "timor-leste",
    "Togo": "togo",
    "Tonga": "tonga",
    "Transnistria": "transnistria",
    "Trinidad and Tobago": "trinidad-and-tobago",
    "Tunisia": "tunisia",
    "Turkey": "turkey",
    "Turkmenistan": "turkmenistan",
    "Tuvalu": "tuvalu",
    "Uganda": "uganda",
    "Ukraine": "ukraine",
    "United Arab Emirates": "united-arab-emirates",
    "United Kingdom": "united-kingdom",
    "United States": "united-states",
    "Uruguay": "uruguay",
    "Uzbekistan": "uzbekistan",
    "Vanuatu": "vanuatu",
    "Venezuela": "venezuela",
    "Vietnam": "vietnam",
    "West Bank": "west-bank",
    "Western Sahara": "western-sahara",
    "Yemen": "yemen",
    "Zambia": "zambia",
    "Zimbabwe": "zimbabwe",
}


def scrape_html(url: str, timeout: int = 30) -> tuple[str | None, int]:
    """Fetch a URL and return (raw_html, status_code)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        return r.text, r.status_code
    except Exception as e:
        print(f"    Request error: {e}")
        return None, 0


def extract_text(html: str, source: str) -> str | None:
    """
    Extract narrative text from HTML. Tries progressively broader selectors.
    Returns plain text with section headers preserved as ## headings.
    """
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["nav", "footer", "script", "style", "noscript", "header"]):
        tag.decompose()

    selectors = ["article", "main", '[class*="report"]', '[class*="content"]', "body"]
    content = None
    for sel in selectors:
        c = soup.select_one(sel)
        if c and len(c.get_text(strip=True)) > 300:
            content = c
            break

    if not content:
        return None

    lines = []
    for elem in content.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = elem.get_text(separator=" ", strip=True)
        if not text:
            continue
        if elem.name in ("h1", "h2", "h3", "h4"):
            lines.append(f"\n## {text}\n")
        elif len(text) >= 15:
            lines.append(text)

    result = "\n".join(lines).strip()
    return result if len(result) > 200 else None


# ---------------------------------------------------------------------------
# State Department
# ---------------------------------------------------------------------------

def fetch_state_dept_country_urls(year: int) -> dict[str, str]:
    """
    Scrape the State Dept index page and return {country_name: sub_page_url}.
    URL pattern: state.gov/reports/{year}-country-reports-on-human-rights-practices/{slug}/
    """
    index = f"https://www.state.gov/reports/{year}-country-reports-on-human-rights-practices/"
    print(f"Fetching State Dept index: {index}")
    html, status = scrape_html(index)
    if not html:
        print("  Failed to fetch index page.")
        return {}

    soup = BeautifulSoup(html, "lxml")
    pattern = f"country-reports-on-human-rights-practices"
    urls = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        name = a.get_text(strip=True)
        if pattern in href and name:
            slug = href.rstrip("/").split("/")[-1]
            if slug and slug not in ("", str(year)):
                full_url = href if href.startswith("http") else f"https://www.state.gov{href}"
                urls[name] = full_url
    print(f"  Found {len(urls)} country pages")
    return urls


def find_pdf_link(html: str) -> str | None:
    """Find the 'Download Report' PDF link on a State Dept country page."""
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if href.endswith(".pdf") and "download" in text:
            return href if href.startswith("http") else f"https://www.state.gov{href}"
    # Fallback: any .pdf link on the page from state.gov
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href and "state.gov" in href:
            return href
    return None


def download_pdf(url: str, dest: Path, retries: int = 3) -> bool:
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=120, stream=True)
            r.raise_for_status()
            dest.write_bytes(r.content)
            kb = len(r.content) // 1024
            print(f"    Saved PDF: {dest.name} ({kb} KB)")
            return True
        except Exception as e:
            print(f"    Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    return False


def download_state_dept(year: int, country_filter: list[str] | None = None):
    """
    State Dept pages are JS-rendered so HTML scraping returns only nav content.
    Instead: visit each country sub-page, find the 'Download Report' PDF link,
    download the PDF. Text extraction happens in ingest.py via PyPDF2.
    Saves: data/raw/state-dept/{year}/{slug}.pdf
    """
    out_dir = BASE_DIR / "state-dept" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    country_urls = fetch_state_dept_country_urls(year)
    if not country_urls:
        return

    if country_filter:
        country_urls = {
            name: url for name, url in country_urls.items()
            if any(f.lower() in name.lower() for f in country_filter)
        }

    print(f"Downloading PDFs for {len(country_urls)} State Dept country reports...")
    success, failed, skipped = 0, [], []

    for name, page_url in sorted(country_urls.items()):
        slug = page_url.rstrip("/").split("/")[-1]
        dest = out_dir / f"{slug}.pdf"

        if dest.exists():
            print(f"  Skip (exists): {dest.name}")
            skipped.append(name)
            continue

        print(f"  {name}: fetching page to find PDF link...")
        html, status = scrape_html(page_url)
        if status == 404 or not html:
            print(f"    Page not found: {name}")
            failed.append(name)
            time.sleep(0.3)
            continue

        pdf_url = find_pdf_link(html)
        if not pdf_url:
            print(f"    No PDF link found: {name}")
            failed.append(name)
            time.sleep(0.3)
            continue

        print(f"    PDF: {pdf_url}")
        if download_pdf(pdf_url, dest):
            success += 1
        else:
            failed.append(name)
        time.sleep(0.5)

    _save_manifest(out_dir, year, success, failed, skipped, "state-dept")
    print(f"\nState Dept: {success} PDFs saved, {len(failed)} failed, {len(skipped)} skipped")
    if failed:
        print("Failed:", failed)


# ---------------------------------------------------------------------------
# Freedom House
# ---------------------------------------------------------------------------

def download_freedom_house(year: int, country_filter: list[str] | None = None,
                           overwrite: bool = False):
    report_year = FH_REPORT_YEAR.get(year)
    if not report_year:
        print(f"No FH report year mapping for data year {year}. Known: {list(FH_REPORT_YEAR)}")
        return

    out_dir = PROCESSED_DIR / "freedom-house" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    countries = FH_COUNTRIES
    if country_filter:
        countries = {
            name: slug for name, slug in FH_COUNTRIES.items()
            if any(f.lower() in name.lower() or f.lower() in slug for f in country_filter)
        }

    print(f"Scraping {len(countries)} Freedom House pages "
          f"(FiW {report_year}, covering {year} data)...")
    success, failed, skipped = 0, [], []

    for name, slug in sorted(countries.items()):
        dest = out_dir / f"{slug}.txt"
        if dest.exists() and not overwrite:
            print(f"  Skip (exists): {dest.name}")
            skipped.append(name)
            continue

        url = f"https://freedomhouse.org/country/{slug}/freedom-world/{report_year}"
        print(f"  Scraping: {name}...")
        html, status = scrape_html(url)

        if status == 404 or not html:
            print(f"    Not found (404): {name}")
            failed.append(name)
            time.sleep(0.5)
            continue

        if "access denied" in html.lower() or "requires you to be logged in" in html.lower():
            print(f"    Access denied (rate-limited?): {name}")
            failed.append(name)
            time.sleep(5.0)
            continue

        text = extract_text(html, "freedom-house")
        if text:
            dest.write_text(text, encoding="utf-8")
            print(f"    Saved: {dest.name} ({len(text):,} chars)")
            success += 1
        else:
            print(f"    No content extracted: {name}")
            failed.append(name)
        time.sleep(1.5)

    _save_manifest(out_dir, year, success, failed, skipped, "freedom-house", report_year)
    print(f"\nFreedom House: {success} saved, {len(failed)} failed, {len(skipped)} skipped")
    if failed:
        print("Failed:", failed)


def _save_manifest(out_dir, year, success, failed, skipped, source, report_year=None):
    manifest = {
        "source": source,
        "data_year": year,
        "success": success,
        "failed": failed,
        "skipped": skipped,
    }
    if report_year:
        manifest["report_year"] = report_year
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Download human rights reports")
    parser.add_argument(
        "--source", choices=["state-dept", "freedom-house", "both"], default="state-dept"
    )
    parser.add_argument("--year", type=int, default=2020)
    parser.add_argument(
        "--countries", nargs="*", default=None,
        help="Filter by country name substrings, e.g. --countries nigeria kenya"
    )
    parser.add_argument(
        "--overwrite", action="store_true", default=False,
        help="Re-download files that already exist (Freedom House only)"
    )
    args = parser.parse_args()

    if args.source in ("state-dept", "both"):
        download_state_dept(args.year, country_filter=args.countries)
    if args.source in ("freedom-house", "both"):
        download_freedom_house(args.year, country_filter=args.countries,
                               overwrite=args.overwrite)


if __name__ == "__main__":
    main()
