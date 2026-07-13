#!/usr/bin/env python3
"""
Download State Dept HR report PDFs and extract plain text from them.

PDFs are a fallback for years or countries where HTML scraping fails.
download_reports.py (HTML) should be tried first — use this script only
when HTML extraction is unavailable or incomplete.

Run from the shared/ directory:

  # Download PDFs only
  python3 pipeline/download_reports_pdf.py --year 2019

  # Download PDFs and immediately extract text
  python3 pipeline/download_reports_pdf.py --year 2019 --extract

  # Extract text from PDFs already on disk (no download)
  python3 pipeline/download_reports_pdf.py --year 2019 --extract-only

  # Subset of countries
  python3 pipeline/download_reports_pdf.py --year 2019 --countries nigeria kenya --extract

Reads:  (index page to get country list)
Saves PDFs:  source-docs/state-dept/{year}/{slug}.pdf
Saves text:  processed-text/state-dept/{year}/{slug}.txt  (with --extract or --extract-only)
"""

import argparse
import json
import re
import time
from pathlib import Path

import PyPDF2
import requests
from bs4 import BeautifulSoup

RAW_DIR = Path(__file__).resolve().parent.parent / "source-docs"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed-text"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 30) -> tuple[str | None, int]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        return r.text, r.status_code
    except Exception as e:
        print(f"    Request error: {e}")
        return None, 0


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


def _find_pdf_link(html: str) -> str | None:
    """Find the 'Download Report' PDF link on a State Dept country page."""
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.endswith(".pdf") and "download" in a.get_text(strip=True).lower():
            return href if href.startswith("http") else f"https://www.state.gov{href}"
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href and "state.gov" in href:
            return href
    return None


def _download_pdf(url: str, dest: Path, retries: int = 3) -> bool:
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=120, stream=True)
            r.raise_for_status()
            dest.write_bytes(r.content)
            print(f"OK ({len(r.content) // 1024} KB)")
            return True
        except Exception as e:
            print(f"    Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    return False


def _extract_pdf_text(pdf_path: Path) -> str | None:
    """Extract plain text from a PDF via PyPDF2."""
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            pages = [p.extract_text() for p in reader.pages if p.extract_text()]
            full = "\n".join(pages).strip()
            return full if full else None
    except Exception as e:
        print(f"    PDF read error: {e}")
        return None


def _clean_sd_text(text: str) -> str:
    """Normalize whitespace and remove SD page-footer boilerplate."""
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r" +", " ", text)
    text = re.sub(
        r"United States Department of State\s*[•·]\s*Bureau of[^\n]*?"
        r"(?=Section\s+\d|\Z)",
        "\n", text,
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _save_manifest(out_dir: Path, year: int, success: int,
                   failed: list, skipped: list) -> None:
    manifest = {
        "source": "state-dept-pdf", "data_year": year,
        "success": success, "failed": failed, "skipped": skipped,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main operations
# ---------------------------------------------------------------------------

def download_pdfs(year: int, country_filter: list[str] | None = None,
                  overwrite: bool = False) -> None:
    """Download State Dept PDFs to source-docs/state-dept/{year}/."""
    out_dir = RAW_DIR / "state-dept" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    country_urls = _fetch_sd_index(year)
    if not country_urls:
        return
    if country_filter:
        country_urls = {n: u for n, u in country_urls.items()
                        if any(f.lower() in n.lower() for f in country_filter)}

    print(f"Downloading PDFs for {len(country_urls)} countries ({year})...")
    success, failed, skipped = 0, [], []

    for name, page_url in sorted(country_urls.items()):
        slug = page_url.rstrip("/").split("/")[-1]
        dest = out_dir / f"{slug}.pdf"
        if dest.exists() and not overwrite:
            print(f"  Skip (exists): {dest.name}")
            skipped.append(name)
            continue

        print(f"  {name}...", end=" ", flush=True)
        html, status = _get(page_url)
        if status == 404 or not html:
            print("PAGE NOT FOUND")
            failed.append(name)
            time.sleep(0.3)
            continue

        pdf_url = _find_pdf_link(html)
        if not pdf_url:
            print("NO PDF LINK")
            failed.append(name)
            time.sleep(0.3)
            continue

        if not _download_pdf(pdf_url, dest):
            failed.append(name)
        else:
            success += 1
        time.sleep(0.5)

    _save_manifest(out_dir, year, success, failed, skipped)
    print(f"\nPDFs: {success} saved, {len(failed)} failed, {len(skipped)} skipped")
    if failed:
        print("Failed:", failed)


def extract_pdfs(year: int, country_filter: list[str] | None = None,
                 overwrite: bool = False) -> None:
    """Extract text from downloaded PDFs to processed-text/state-dept/{year}/."""
    raw_dir = RAW_DIR / "state-dept" / str(year)
    out_dir = PROCESSED_DIR / "state-dept" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(raw_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {raw_dir}")
        return
    if country_filter:
        pdfs = [p for p in pdfs if any(f.lower() in p.stem for f in country_filter)]

    print(f"Extracting text from {len(pdfs)} PDFs ({year})...")
    success, failed, skipped = 0, [], []

    for pdf_path in pdfs:
        dest = out_dir / f"{pdf_path.stem}.txt"
        if dest.exists() and not overwrite:
            print(f"  Skip (exists): {dest.name}")
            skipped.append(pdf_path.stem)
            continue

        print(f"  {pdf_path.stem}...", end=" ", flush=True)
        raw = _extract_pdf_text(pdf_path)
        if raw:
            text = _clean_sd_text(raw)
            dest.write_text(text, encoding="utf-8")
            print(f"OK ({len(text):,} chars)")
            success += 1
        else:
            print("FAILED")
            failed.append(pdf_path.stem)

    print(f"\nExtraction: {success} saved, {len(failed)} failed, {len(skipped)} skipped")
    if failed:
        print("Failed:", failed)


# ---------------------------------------------------------------------------
# IRFR PDF extraction
# ---------------------------------------------------------------------------

def extract_irfr_exec_summary_from_text(text: str) -> str | None:
    """
    Extract the Executive Summary from raw IRFR PDF text.
    Looks for content between 'EXECUTIVE SUMMARY' and 'I. Religious Demography'.
    """
    # Normalize whitespace and collapsed-character artifacts from PDF extraction.
    # Some PDFs produce "E xecutive S ummary" with a space after the first letter.
    normalized = re.sub(r"\s+", " ", text)
    # Re-join split words: "E xecutive" → "Executive", "T he" → "The"
    normalized = re.sub(r"\b([A-Za-z]) (?=[a-zA-Z])", r"\1", normalized)
    text_upper = normalized.upper()
    start = text_upper.find("EXECUTIVE SUMMARY")
    if start == -1:
        return None
    text = normalized
    start += len("EXECUTIVE SUMMARY")

    # Find end at "I. Religious Demography" or "SECTION I" or "I. RELIGIOUS"
    end = len(text)
    for marker in ["I. RELIGIOUS DEMOGRAPHY", "SECTION I.", "I. RELIGIOUS"]:
        pos = text_upper.find(marker, start)
        if pos != -1 and pos < end:
            end = pos

    excerpt = text[start:end].strip()
    # Clean up whitespace artifacts from PDF extraction
    excerpt = re.sub(r"\n{3,}", "\n\n", excerpt)
    excerpt = re.sub(r" +", " ", excerpt)
    return excerpt if len(excerpt) > 100 else None


def download_irfr_pdf(pdf_url: str, slug: str, year: int,
                      overwrite: bool = False) -> bool:
    """
    Download an IRFR PDF from a direct URL, extract the executive summary,
    and save to processed-text/irfr/{year}/{slug}.txt.
    """
    out_dir = PROCESSED_DIR / "irfr" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{slug}.txt"

    if dest.exists() and not overwrite:
        print(f"Skip (exists): {dest.name}")
        return True

    # Download PDF to a temp file
    tmp = out_dir / f"_tmp_{slug}.pdf"
    print(f"Downloading {pdf_url} ...", end=" ", flush=True)
    try:
        r = requests.get(pdf_url, headers=HEADERS, timeout=60, stream=True)
        r.raise_for_status()
        tmp.write_bytes(r.content)
    except Exception as e:
        print(f"FAILED ({e})")
        return False

    raw = _extract_pdf_text(tmp)
    tmp.unlink()

    if not raw:
        print("FAILED (PDF extraction)")
        return False

    summary = extract_irfr_exec_summary_from_text(raw)
    if not summary:
        print("FAILED (no exec summary found)")
        return False

    dest.write_text(summary, encoding="utf-8")
    print(f"OK ({len(summary):,} chars)")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download State Dept PDFs and/or extract text from them"
    )
    parser.add_argument("--year", type=int, default=2020)
    parser.add_argument(
        "--countries", nargs="*", default=None,
        help="Filter by country name substrings",
    )
    parser.add_argument(
        "--overwrite", action="store_true", default=False,
        help="Re-download/re-extract files that already exist",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--extract", action="store_true",
        help="Download PDFs then extract text",
    )
    group.add_argument(
        "--extract-only", action="store_true",
        help="Extract text from already-downloaded PDFs (no download)",
    )
    group.add_argument(
        "--irfr-pdf", nargs=2, metavar=("SLUG", "PDF_URL"), action="append",
        help="Extract IRFR exec summary from a direct PDF URL; "
             "repeat for multiple: --irfr-pdf colombia URL --irfr-pdf romania URL",
    )
    args = parser.parse_args()

    if args.irfr_pdf:
        for slug, pdf_url in args.irfr_pdf:
            download_irfr_pdf(pdf_url, slug, args.year, args.overwrite)
    elif args.extract_only:
        extract_pdfs(args.year, args.countries, args.overwrite)
    elif args.extract:
        download_pdfs(args.year, args.countries, args.overwrite)
        extract_pdfs(args.year, args.countries, args.overwrite)
    else:
        download_pdfs(args.year, args.countries, args.overwrite)


if __name__ == "__main__":
    main()
