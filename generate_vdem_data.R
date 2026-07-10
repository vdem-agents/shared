#!/usr/bin/env Rscript
# Generate panel_means.csv and human_ratings.csv from V-Dem v15 coder-level data.
#
# Outputs (written to vdem-data/ alongside this script):
#   vdem-data/panel_means.csv   — country_text_id, year, indicator, raw_mean, n_coders, theta_quintile
#   vdem-data/human_ratings.csv — country_text_id, iso3, year, indicator, coder_id, rating
#
# Dec 31 filter: the coder-level dataset has two rows per coder-country-year (Jan 1 and
# Dec 31) as a structural feature. Filtering to Dec 31 gives one rating per coder per
# year, matching V-Dem's published end-of-year values. Without this filter, panel means
# are computed from doubled observations and fine-tuning data is ~2x larger than needed.
#
# Run from any directory:
#   Rscript /path/to/shared/generate_vdem_data.R

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(readr)
  library(vdemdata)   # install via: remotes::install_github("vdeminstitute/vdemdata")
})

# ── Paths ────────────────────────────────────────────────────────────────────
args <- commandArgs(trailingOnly = FALSE)
script_file <- sub("--file=", "", args[grep("--file=", args)])
SHARED_DIR <- if (length(script_file) && nzchar(script_file)) {
  normalizePath(dirname(script_file))
} else {
  normalizePath(".")  # interactive fallback: run from shared/
}
RDS_PATH <- file.path(SHARED_DIR, "vdem-data", "V-Dem-Coder-Level-v15_rds",
                      "Coder-Level-Dataset-v15.rds")
OUT_DIR  <- file.path(SHARED_DIR, "vdem-data")

# V-Dem anchor question columns — excluded from the indicator set
ANCHOR_COLS <- c(
  "v2zzdemcr", "v2zzdemcu", "v2zzdemin", "v2zzdemni", "v2zzdemnk", "v2zzdemru",
  "v2zzdemsaf", "v2zzdemsar", "v2zzdemswe", "v2zzdemswz", "v2zzdemuk",
  "v2zzdemus", "v2zzdemvz"
)

# ── Load ─────────────────────────────────────────────────────────────────────
cat("Loading coder-level data (RDS)...\n")
cl <- readRDS(RDS_PATH)
cat(sprintf("  Loaded: %s rows, %d columns\n",
            format(nrow(cl), big.mark = ","), ncol(cl)))

# Dec 31 filter
cl <- cl |> filter(format(as.Date(historical_date), "%m-%d") == "12-31")
cat(sprintf("  After Dec 31 filter: %s rows\n", format(nrow(cl), big.mark = ",")))

# Derive year if absent
if (!"year" %in% names(cl)) {
  cl <- cl |> mutate(year = as.integer(format(as.Date(historical_date), "%Y")))
}

# V-Dem uses country_text_id as the ISO 3-letter code; iso3 is an alias
cl <- cl |> mutate(iso3 = country_text_id)

# ── Identify coder-level indicator columns ────────────────────────────────────
# Restrict to Type C indicators (vartype == "C" in vdemdata::codebook).
# These are the expert-coded ordinal indicators — the only ones with
# coder-level variation relevant for panel means and fine-tuning.
type_c_tags <- vdemdata::codebook |>
  filter(vartype == "C") |>
  pull(tag)

# Intersect with columns actually present in the coder-level dataset
indicator_cols <- intersect(type_c_tags, names(cl))
indicator_cols <- indicator_cols[vapply(cl[indicator_cols], is.numeric, logical(1))]
cat(sprintf("  Identified %d Type C indicator columns\n", length(indicator_cols)))

# ── theta_quintile from vdemdata ─────────────────────────────────────────────
# v2x_polyarchy comes from the main V-Dem country-year dataset (vdemdata::vdem),
# not from the coder-level data. Quintiles are computed across all available
# country-years so the 20th percentile boundaries are globally consistent.
cat("Computing theta_quintile from vdemdata::vdem...\n")
polyarchy_cy <- vdemdata::vdem |>
  select(country_text_id, year, v2x_polyarchy) |>
  filter(!is.na(v2x_polyarchy)) |>
  mutate(theta_quintile = ntile(v2x_polyarchy, 5))

# ── panel_means.csv ───────────────────────────────────────────────────────────
cat("\nComputing panel means...\n")

panel_means <- cl |>
  select(country_text_id, year, coder_id, all_of(indicator_cols)) |>
  pivot_longer(
    cols      = all_of(indicator_cols),
    names_to  = "indicator",
    values_to = "rating"
  ) |>
  filter(!is.na(rating)) |>
  group_by(country_text_id, year, indicator) |>
  summarise(
    raw_mean = round(mean(rating), 4),
    n_coders = n_distinct(coder_id),
    .groups  = "drop"
  )

panel_means <- panel_means |>
  left_join(
    select(polyarchy_cy, country_text_id, year, theta_quintile),
    by = c("country_text_id", "year")
  ) |>
  mutate(theta_quintile = coalesce(theta_quintile, 0L))

out_pm <- file.path(OUT_DIR, "panel_means.csv")
write_csv(
  select(panel_means, country_text_id, year, indicator, raw_mean, n_coders, theta_quintile),
  out_pm
)
cat(sprintf("  Wrote panel_means.csv: %s rows, %d indicators\n",
            format(nrow(panel_means), big.mark = ","),
            n_distinct(panel_means$indicator)))

# ── human_ratings.csv ─────────────────────────────────────────────────────────
cat("\nGenerating human ratings (long format)...\n")

human_ratings <- cl |>
  select(country_text_id, iso3, year, coder_id, all_of(indicator_cols)) |>
  pivot_longer(
    cols      = all_of(indicator_cols),
    names_to  = "indicator",
    values_to = "rating"
  ) |>
  filter(!is.na(rating)) |>
  select(country_text_id, iso3, year, indicator, coder_id, rating)

out_hr <- file.path(OUT_DIR, "human_ratings.csv")
write_csv(human_ratings, out_hr)
cat(sprintf("  Wrote human_ratings.csv: %s rows\n",
            format(nrow(human_ratings), big.mark = ",")))

cat("\nDone.\n")
