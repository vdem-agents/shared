#!/usr/bin/env python3
"""
Download plain-text source documents for the V-Dem AI coding pipeline.

Covers all three HTML sources — run from the shared/ directory:

  State Dept (Human Rights Reports):
    Scrapes HTML from state.gov and archive site.
    Saves: processed-text/state-dept/{year}/{slug}.txt

  Freedom House (Freedom in the World):
    Scrapes HTML from freedomhouse.org.
    Note: FH report year = data year + 1 (FiW 2021 covers 2020 data).
    Saves: processed-text/freedom-house/{year}/{slug}.txt

  IRFR (International Religious Freedom Reports):
    Scrapes executive summary HTML from state.gov.
    Used in place of State Dept section 2c, which universally redirects to IRFR.
    Saves: processed-text/irfr/{year}/{slug}.txt

Usage:
  python3 pipeline/download_reports.py --source state-dept --year 2019
  python3 pipeline/download_reports.py --source freedom-house --year 2019
  python3 pipeline/download_reports.py --source irfr --year 2019
  python3 pipeline/download_reports.py --source all --year 2019
  python3 pipeline/download_reports.py --source state-dept --year 2019 --countries nigeria kenya
"""

import argparse
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed-text"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# FH report year for a given data year (FiW covers the prior calendar year).
FH_REPORT_YEAR = {
    2016: 2017, 2017: 2018, 2018: 2019, 2019: 2020,
    2020: 2021, 2021: 2022, 2022: 2023, 2023: 2024, 2024: 2025,
}

# Complete Freedom House slug list (from freedomhouse.org/country/scores).
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

# Ordered URL templates for State Dept HTML reports.
# {year} and {slug} are substituted; first 200 response with entry-content wins.
_SD_URL_TEMPLATES = [
    "https://2017-2021.state.gov/reports/{year}-country-reports-on-human-rights-practices/{slug}/",
    "https://www.state.gov/reports/{year}-country-reports-on-human-rights-practices/{slug}/",
    "https://2009-2017.state.gov/reports/{year}-country-reports-on-human-rights-practices/{slug}/",
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 30) -> tuple[str | None, int]:
    """Fetch a URL; return (html, status_code)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        return r.text, r.status_code
    except Exception as e:
        print(f"    Request error: {e}")
        return None, 0


def _save_manifest(out_dir: Path, year: int, success: int,
                   failed: list, skipped: list, source: str,
                   report_year: int | None = None) -> None:
    manifest = {
        "source": source, "data_year": year,
        "success": success, "failed": failed, "skipped": skipped,
    }
    if report_year:
        manifest["report_year"] = report_year
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# State Department
# ---------------------------------------------------------------------------

def _fetch_sd_index(year: int) -> dict[str, str]:
    """Scrape the SD index page; return {country_name: country_page_url}."""
    index = f"https://www.state.gov/reports/{year}-country-reports-on-human-rights-practices/"
    print(f"Fetching SD index: {index}")
    html, _ = _get(index)
    if not html:
        print("  Failed to fetch index.")
        return {}
    soup = BeautifulSoup(html, "lxml")
    pattern = "country-reports-on-human-rights-practices"
    urls = {}
    for a in soup.find_all("a", href=True):
        href, name = a["href"], a.get_text(strip=True)
        if pattern in href and name:
            slug = href.rstrip("/").split("/")[-1]
            if slug and slug != str(year):
                full = href if href.startswith("http") else f"https://www.state.gov{href}"
                urls[name] = full
    print(f"  Found {len(urls)} countries")
    return urls


def _fetch_sd_text(slug: str, year: int) -> str | None:
    """
    Fetch State Dept HTML report for (slug, year); return clean plain text.
    Tries archive URLs in order; requires entry-content sections to be present.
    """
    for tmpl in _SD_URL_TEMPLATES:
        url = tmpl.format(year=year, slug=slug)
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                continue
            html = r.text
            if not re.search(r'class="[^"]*entry-content', html, re.IGNORECASE):
                continue
            # Extract only entry-content sections to exclude nav/header/footer.
            chunks = re.findall(
                r'<section[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</section>',
                html, re.DOTALL | re.IGNORECASE,
            )
            content = "\n\n".join(chunks) if chunks else html
            text = re.sub(r"<[^>]+>", " ", content)
            text = (text
                    .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                    .replace("&nbsp;", " ").replace("&#8217;", "'")
                    .replace("&#8220;", '"').replace("&#8221;", '"'))
            text = re.sub(r"&#\d+;", " ", text)
            text = re.sub(r"&[a-z]+;", " ", text)
            text = "\n".join(line.strip() for line in text.splitlines())
            # Remove SD page-footer boilerplate so section headers land at column 0.
            text = re.sub(
                r"United States Department of State\s*[•·]\s*Bureau of[^\n]*?"
                r"(?=Section\s+\d|\Z)",
                "\n", text,
            )
            text = re.sub(r" +", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if len(text) >= 500:
                time.sleep(1.5)
                return text
        except Exception:
            continue
    return None


def download_state_dept(year: int, country_filter: list[str] | None = None,
                        overwrite: bool = False) -> None:
    out_dir = PROCESSED_DIR / "state-dept" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    country_urls = _fetch_sd_index(year)
    if not country_urls:
        return
    if country_filter:
        country_urls = {n: u for n, u in country_urls.items()
                        if any(f.lower() in n.lower() for f in country_filter)}

    print(f"Downloading SD HTML for {len(country_urls)} countries ({year})...")
    success, failed, skipped = 0, [], []

    for name, page_url in sorted(country_urls.items()):
        slug = page_url.rstrip("/").split("/")[-1]
        dest = out_dir / f"{slug}.txt"
        if dest.exists() and not overwrite:
            print(f"  Skip (exists): {dest.name}")
            skipped.append(name)
            continue

        print(f"  {name}...", end=" ", flush=True)
        text = _fetch_sd_text(slug, year)
        if text:
            dest.write_text(text, encoding="utf-8")
            print(f"OK ({len(text):,} chars)")
            success += 1
        else:
            print("FAILED")
            failed.append(name)

    _save_manifest(out_dir, year, success, failed, skipped, "state-dept")
    print(f"\nSD: {success} saved, {len(failed)} failed, {len(skipped)} skipped")
    if failed:
        print("Failed:", failed)


# ---------------------------------------------------------------------------
# Freedom House
# ---------------------------------------------------------------------------

def _extract_fh_text(html: str) -> str | None:
    """Extract narrative text from a Freedom House HTML page."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["nav", "footer", "script", "style", "noscript", "header"]):
        tag.decompose()
    for sel in ["article", "main", '[class*="report"]', '[class*="content"]', "body"]:
        content = soup.select_one(sel)
        if content and len(content.get_text(strip=True)) > 300:
            break
    else:
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


def download_freedom_house(year: int, country_filter: list[str] | None = None,
                           overwrite: bool = False) -> None:
    report_year = FH_REPORT_YEAR.get(year)
    if not report_year:
        print(f"No FH report year mapping for {year}. Known: {list(FH_REPORT_YEAR)}")
        return

    out_dir = PROCESSED_DIR / "freedom-house" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    countries = FH_COUNTRIES
    if country_filter:
        countries = {n: s for n, s in FH_COUNTRIES.items()
                     if any(f.lower() in n.lower() or f.lower() in s for f in country_filter)}

    print(f"Downloading FH HTML for {len(countries)} countries "
          f"(FiW {report_year}, covering {year} data)...")
    success, failed, skipped = 0, [], []

    for name, slug in sorted(countries.items()):
        dest = out_dir / f"{slug}.txt"
        if dest.exists() and not overwrite:
            print(f"  Skip (exists): {dest.name}")
            skipped.append(name)
            continue

        url = f"https://freedomhouse.org/country/{slug}/freedom-world/{report_year}"
        print(f"  {name}...", end=" ", flush=True)
        html, status = _get(url)

        if status == 404 or not html:
            print("NOT FOUND")
            failed.append(name)
            time.sleep(0.5)
            continue
        if "access denied" in html.lower() or "requires you to be logged in" in html.lower():
            print("RATE LIMITED")
            failed.append(name)
            time.sleep(5.0)
            continue

        text = _extract_fh_text(html)
        if text:
            dest.write_text(text, encoding="utf-8")
            print(f"OK ({len(text):,} chars)")
            success += 1
        else:
            print("NO CONTENT")
            failed.append(name)
        time.sleep(1.5)

    _save_manifest(out_dir, year, success, failed, skipped, "freedom-house", report_year)
    print(f"\nFH: {success} saved, {len(failed)} failed, {len(skipped)} skipped")
    if failed:
        print("Failed:", failed)


# ---------------------------------------------------------------------------
# IRFR (International Religious Freedom Reports)
# ---------------------------------------------------------------------------

def _fetch_irfr_index(year: int) -> dict[str, str]:
    """Scrape the IRFR index page; return {country_name: country_page_url}."""
    index = f"https://www.state.gov/reports/{year}-report-on-international-religious-freedom/"
    print(f"Fetching IRFR index: {index}")
    html, _ = _get(index)
    if not html:
        print("  Failed to fetch index.")
        return {}
    soup = BeautifulSoup(html, "lxml")
    pattern = f"{year}-report-on-international-religious-freedom"
    urls = {}
    for a in soup.find_all("a", href=True):
        href, name = a["href"], a.get_text(strip=True)
        if pattern in href and name and name != "Translations":
            slug = href.rstrip("/").split("/")[-1]
            if slug and slug != str(year):
                full = href if href.startswith("http") else f"https://www.state.gov{href}"
                urls[name] = full
    print(f"  Found {len(urls)} countries")
    return urls


def _extract_irfr_exec_summary(html: str) -> str | None:
    """
    Extract the Executive Summary from an IRFR country page.
    Falls back to the 'Status of Government Respect for Religious Freedom'
    section for pages that omit the Executive Summary heading.
    """
    soup = BeautifulSoup(html, "lxml")

    def _text_after(tag) -> str | None:
        paragraphs = []
        for sib in tag.find_next_siblings():
            if sib.name in ("h1", "h2", "h3", "h4"):
                break
            text = sib.get_text(separator=" ", strip=True)
            if text and len(text) >= 15:
                paragraphs.append(text)
        return "\n\n".join(paragraphs) if paragraphs else None

    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        if "executive summary" in tag.get_text().lower():
            result = _text_after(tag)
            if result:
                return result

    # Fallback: preamble between the report-title heading and the first section heading.
    # Some pages label sections as h3 with no explicit "Executive Summary" h3.
    for tag in soup.find_all(["h1", "h2"]):
        if "international religious freedom report" in tag.get_text().lower():
            result = _text_after(tag)
            if result:
                return result

    return None


def download_irfr(year: int, country_filter: list[str] | None = None,
                  overwrite: bool = False) -> None:
    out_dir = PROCESSED_DIR / "irfr" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    country_urls = _fetch_irfr_index(year)
    if not country_urls:
        return
    if country_filter:
        country_urls = {n: u for n, u in country_urls.items()
                        if any(f.lower() in n.lower() for f in country_filter)}

    print(f"Downloading IRFR executive summaries for {len(country_urls)} countries ({year})...")
    success, failed, skipped = 0, [], []

    for name, page_url in sorted(country_urls.items()):
        slug = page_url.rstrip("/").split("/")[-1]
        dest = out_dir / f"{slug}.txt"
        if dest.exists() and not overwrite:
            print(f"  Skip (exists): {dest.name}")
            skipped.append(name)
            continue

        print(f"  {name}...", end=" ", flush=True)
        html, status = _get(page_url)
        if status == 404 or not html:
            print("NOT FOUND")
            failed.append(name)
            time.sleep(0.5)
            continue

        text = _extract_irfr_exec_summary(html)
        if text:
            dest.write_text(text, encoding="utf-8")
            print(f"OK ({len(text):,} chars)")
            success += 1
        else:
            print("NO EXEC SUMMARY")
            failed.append(name)
        time.sleep(1.5)

    _save_manifest(out_dir, year, success, failed, skipped, "irfr")
    print(f"\nIRFR: {success} saved, {len(failed)} failed, {len(skipped)} skipped")
    if failed:
        print("Failed:", failed)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download HTML source documents for V-Dem AI coding pipeline"
    )
    parser.add_argument(
        "--source",
        choices=["state-dept", "freedom-house", "irfr", "all"],
        default="state-dept",
    )
    parser.add_argument("--year", type=int, default=2020)
    parser.add_argument(
        "--countries", nargs="*", default=None,
        help="Filter by country name substrings, e.g. --countries nigeria kenya",
    )
    parser.add_argument(
        "--overwrite", action="store_true", default=False,
        help="Re-download files that already exist",
    )
    args = parser.parse_args()

    if args.source in ("state-dept", "all"):
        download_state_dept(args.year, args.countries, args.overwrite)
    if args.source in ("freedom-house", "all"):
        download_freedom_house(args.year, args.countries, args.overwrite)
    if args.source in ("irfr", "all"):
        download_irfr(args.year, args.countries, args.overwrite)


if __name__ == "__main__":
    main()
