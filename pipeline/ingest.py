#!/usr/bin/env python3
"""
Stage 1: Ingest — extract plain text from State Dept reports and register
Freedom House plain-text files.

State Dept: fetch HTML from the State Dept archive (2017-2021.state.gov or
  state.gov), falling back to local PDFs when HTML is unavailable.
Freedom House: files are already plain text; a symlink is created from
  processed-text/freedom-house/{year}/ → source-docs/freedom-house/{year}/
  so the rest of the pipeline reads them from the standard processed-text path.

Reads:  source-docs/state-dept/{year}/*.pdf   (fallback only)
Writes: processed-text/state-dept/{year}/*.txt
Links:  processed-text/freedom-house/{year}/ → source-docs/freedom-house/{year}/

Usage:
  python3 -m pipeline.ingest --year 2019
  python3 -m pipeline.ingest --year 2019 --countries nigeria kenya
  python3 -m pipeline.ingest --year 2017 --html-first --slug-source-year 2019
"""

import argparse
import re
import time
import urllib.request
from pathlib import Path

import PyPDF2

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

# Ordered list of URL templates to try when fetching a country HTML report.
# {year} and {slug} are substituted.  Stop at the first 200 response with content.
_HTML_URL_TEMPLATES = [
    "https://2017-2021.state.gov/reports/{year}-country-reports-on-human-rights-practices/{slug}/",
    "https://www.state.gov/reports/{year}-country-reports-on-human-rights-practices/{slug}/",
    # Obama-era archive uses a different URL structure (dlid-based); this slug
    # pattern works for 2016 reports published in early 2017 but not earlier years.
    "https://2009-2017.state.gov/reports/{year}-country-reports-on-human-rights-practices/{slug}/",
]

RAW_DIR = Path(__file__).resolve().parent.parent / "source-docs"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed-text"


def extract_pdf_text(pdf_path: Path) -> str | None:
    """Extract plain text from a PDF. Returns None if extraction fails."""
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            full_text = "\n".join(pages).strip()
            return full_text if full_text else None
    except Exception as e:
        print(f"  Error reading {pdf_path.name}: {e}")
        return None


def clean_text(text: str) -> str:
    """Light cleaning: normalize whitespace, remove repeated blank lines."""
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r" +", " ", text)
    # Replace State Dept page-footer boilerplate with a newline so that any
    # section header following it lands at the start of a line for the parser.
    # Use a lookahead so variants like "Human Rights, and Labor" or "Labo r"
    # (PDF word-split artifact) are all handled by one pattern.
    text = re.sub(
        r"United States Department of State\s*[•·]\s*Bureau of[^\n]*?(?=Section\s+\d|\Z)",
        "\n",
        text,
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_html_report(slug: str, year: int) -> str | None:
    """
    Fetch the State Dept HTML report for (slug, year) from the archive site.
    Returns extracted plain text in the same format as PDF extraction, or None.
    """
    html = None
    used_url = None
    for tmpl in _HTML_URL_TEMPLATES:
        url = tmpl.format(year=year, slug=slug)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status == 200:
                    raw = resp.read()
                    candidate = raw.decode("utf-8", errors="replace")
                    # Reject catch-all error pages that return 200 but have no report content.
                    if re.search(r'class="[^"]*entry-content', candidate, re.IGNORECASE):
                        html = candidate
                        used_url = url
                        break
        except Exception:
            continue

    if not html:
        return None

    # Extract content from <section class="entry-content"> blocks only.
    # These hold the actual report text; nav/header/footer are excluded.
    chunks = re.findall(
        r'<section[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</section>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    content = "\n\n".join(chunks) if chunks else html

    # Strip all HTML tags
    text = re.sub(r"<[^>]+>", " ", content)
    # Decode HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&#8217;", "'").replace("&#8220;", '"').replace("&#8221;", '"')
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)

    # Strip per-line leading whitespace so "Section N." always starts at column 0,
    # matching the same structure parse_state_dept() expects from PDF extraction.
    text = "\n".join(line.strip() for line in text.splitlines())
    cleaned = clean_text(text)
    if not cleaned or len(cleaned) < 500:
        return None

    print(f"  (HTML from {used_url})", end=" ")
    time.sleep(1.5)  # avoid rate-limiting the archive servers
    return cleaned


def ingest_state_dept(year: int, country_filter: list[str] | None = None,
                      html_first: bool = False, slug_source_year: int | None = None):
    """
    Extract State Dept report text for all countries in a given year.

    When html_first=True (recommended for 2017+), fetch HTML from the archive
    site and fall back to the local PDF only if HTML is unavailable.
    When html_first=False (default, for 2013–2016), extract the local PDF and
    fall back to HTML only if the PDF fails.

    slug_source_year: if set, borrow the PDF slug list from that year's raw
    directory instead of the target year (useful when no local PDFs exist for
    the target year but the country list is the same).
    """
    raw_dir = RAW_DIR / "state-dept" / str(year)
    out_dir = PROCESSED_DIR / "state-dept" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    slug_dir = RAW_DIR / "state-dept" / str(slug_source_year) if slug_source_year else raw_dir
    pdfs = sorted(slug_dir.glob("*.pdf"))
    if country_filter:
        pdfs = [p for p in pdfs if any(f.lower() in p.stem for f in country_filter)]

    mode = "HTML→PDF" if html_first else "PDF→HTML"
    print(f"Ingesting {len(pdfs)} State Dept reports ({year}, {mode})...")
    success, failed, skipped = 0, [], []

    for pdf_path in pdfs:
        slug = pdf_path.stem
        dest = out_dir / f"{slug}.txt"
        if dest.exists():
            skipped.append(slug)
            continue

        print(f"  {slug}...", end=" ", flush=True)

        local_pdf = raw_dir / pdf_path.name
        if html_first:
            text = fetch_html_report(slug, year)
            if text is None and local_pdf.exists():
                raw = extract_pdf_text(local_pdf)
                text = clean_text(raw) if raw is not None else None
        else:
            raw = extract_pdf_text(local_pdf) if local_pdf.exists() else None
            text = clean_text(raw) if raw is not None else None
            if text is None:
                text = fetch_html_report(slug, year)

        if text:
            dest.write_text(text, encoding="utf-8")
            print(f"OK ({len(text):,} chars, {len(text.split())//1000}K words)")
            success += 1
        else:
            print("FAILED")
            failed.append(slug)

    print(f"\nDone: {success} extracted, {len(failed)} failed, {len(skipped)} skipped")
    if failed:
        print("Failed:", failed)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest State Dept reports from HTML or local PDFs"
    )
    parser.add_argument("--year", type=int, default=2020)
    parser.add_argument("--countries", nargs="*", default=None)
    parser.add_argument(
        "--html-first", action="store_true",
        help="Fetch HTML from archive site first, fall back to local PDF "
             "(recommended for 2017+)",
    )
    parser.add_argument(
        "--slug-source-year", type=int, default=None,
        help="Borrow PDF slug list from this year when no local PDFs exist "
             "for the target year (e.g. --year 2017 --slug-source-year 2019)",
    )
    args = parser.parse_args()
    ingest_state_dept(args.year, country_filter=args.countries,
                      html_first=args.html_first,
                      slug_source_year=args.slug_source_year)


if __name__ == "__main__":
    main()
