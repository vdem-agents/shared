#!/usr/bin/env python3
"""
Audit section coverage for a given year.

For every downloaded State Dept and Freedom House file, check which YAML-mapped
section keys are present vs. absent in the parsed output. Reports genuine content
absences (sections simply not in that country's report) vs. parser gaps.

Also flags non-country files (e.g. translations index pages) that should be added
to SLUG_OVERRIDES in run_coding_batch.py.

CONFIG_PATH defaults to config/indicator_sections.yaml relative to the working
directory, so run this from the project root (panel-member/ or bridge-coder/).

Usage:
    python3 -m pipeline.check_section_coverage --year 2019
    python3 -m pipeline.check_section_coverage --year 2019 --source state-dept
"""

import argparse
import yaml
from collections import defaultdict
from pathlib import Path

from pipeline.extract_sections import parse_state_dept, parse_freedom_house

CONFIG_PATH = Path.cwd() / "config" / "indicator_sections.yaml"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed-text"


def check_year(year: int, source: str) -> None:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    keys_used: set[str] = set()
    for cfg in config.values():
        for k in cfg.get(source, []):
            keys_used.add(k)

    src_dir = PROCESSED_DIR / source / str(year)
    if not src_dir.exists():
        print(f"No processed-text for {source} {year} at {src_dir}")
        return

    files = sorted(src_dir.glob("*.txt"))
    parse_fn = parse_state_dept if source == "state-dept" else parse_freedom_house

    missing: dict[str, list[str]] = defaultdict(list)  # key → countries missing it
    no_sections: list[str] = []                          # files with no recognized sections at all

    for path in files:
        parsed = parse_fn(path.read_text(encoding="utf-8"))
        content_keys = {k for k in parsed if k != "exec_summary"}
        if not content_keys:
            no_sections.append(path.stem)
            continue
        for k in keys_used:
            if k not in parsed:
                missing[k].append(path.stem)

    print(f"\n=== {source} {year}: {len(files)} files, {len(keys_used)} mapped keys ===")

    if no_sections:
        print(f"\n  *** Files with NO recognized sections (likely non-country files) ***")
        for s in no_sections:
            print(f"    {s}")

    if missing:
        print(f"\n  Sections absent from ≥1 country report (genuine content gaps):")
        for k in sorted(missing):
            countries = sorted(missing[k])
            print(f"    {k} [{len(countries)}]: {countries}")
    else:
        print(f"\n  All {len(keys_used)} mapped sections present in all {len(files)} files.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit section coverage for a given year")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument(
        "--source",
        choices=["state-dept", "freedom-house", "both"],
        default="both",
    )
    args = parser.parse_args()

    sources = (
        ["state-dept", "freedom-house"] if args.source == "both" else [args.source]
    )
    for src in sources:
        check_year(args.year, src)


if __name__ == "__main__":
    main()
