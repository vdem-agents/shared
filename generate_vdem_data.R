#!/usr/bin/env Rscript
# Generate panel_means.csv and human_ratings.csv from V-Dem v15 coder-level data.
#
# Outputs (written to vdem-data/ alongside this script):
#   vdem-data/panel_means.csv   — country_text_id, year, indicator, raw_mean, n_coders,
#                                  theta_quintile, v2x_regime
#   vdem-data/human_ratings.csv — country_text_id, iso3, year, indicator, coder_id, rating
#
# Restricted to STUDY_YEARS (2010–2024): covers fine-tuning window (2013–2018),
# calibration year (2019), few-shot selection (2020), attrition reference (2015, 2022),
# and deployment robustness check (2024).
#
# Dec 31 filter: the coder-level dataset has two rows per coder-country-year (Jan 1 and
# Dec 31) as a structural feature. Filtering to Dec 31 gives one rating per coder per
# year, matching V-Dem's published end-of-year values.
#
# Run from any directory:
#   Rscript /path/to/shared/generate_vdem_data.R

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(readr)
  library(vdemdata)   # install via: remotes::install_github("vdeminstitute/vdemdata")
})

STUDY_YEARS <- 2010:2024

# ── Paths ─────────────────────────────────────────────────────────────────────
args        <- commandArgs(trailingOnly = FALSE)
script_file <- sub("--file=", "", args[grep("--file=", args)])
SHARED_DIR  <- if (length(script_file) && nzchar(script_file)) {
  normalizePath(dirname(script_file))
} else {
  normalizePath(".")  # interactive fallback: run from shared/
}
RDS_PATH <- file.path(SHARED_DIR, "vdem-data", "V-Dem-Coder-Level-v15_rds",
                      "Coder-Level-Dataset-v15.rds")
OUT_DIR  <- file.path(SHARED_DIR, "vdem-data")

# ── Load and filter ───────────────────────────────────────────────────────────
cat("Loading coder-level data...\n")
cl <- read_rds(RDS_PATH) |>
  mutate(
    year = as.integer(format(as.Date(historical_date), "%Y")),
    iso3 = country_text_id
  ) |>
  filter(
    format(as.Date(historical_date), "%m-%d") == "12-31",
    year %in% STUDY_YEARS
  )
cat(sprintf("  After Dec 31 + year filter: %s rows (%d–%d)\n",
            format(nrow(cl), big.mark = ","), min(cl$year), max(cl$year)))

# ── Identify Type C indicator columns ────────────────────────────────────────
# vartype == "C" in vdemdata::codebook identifies expert-coded ordinal indicators.
# Intersect with columns present in the RDS, then keep only numeric ones.
type_c_tags <- vdemdata::codebook |>
  filter(vartype == "C") |>
  pull(tag)

indicator_cols <- cl |>
  select(all_of(intersect(type_c_tags, names(cl)))) |>
  select(where(is.numeric)) |>
  names()

cat(sprintf("  Identified %d Type C indicator columns\n", length(indicator_cols)))

# ── Country-year covariates from vdemdata::vdem ───────────────────────────────
# theta_quintile: ntile() rank of v2x_polyarchy across study-period country-years.
#   Used in the signed-deviation diagnostic to detect compression bias by democracy level.
# v2x_regime: 4-category regime type (0 closed autocracy → 3 liberal democracy).
#   Used alongside quintile for a cleaner categorical breakdown.
cat("Joining covariates from vdemdata::vdem...\n")
vdem_cy <- vdemdata::vdem |>
  filter(year %in% STUDY_YEARS) |>
  select(country_text_id, year, v2x_polyarchy, v2x_regime) |>
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
  ) |>
  left_join(vdem_cy, by = c("country_text_id", "year")) |>
  mutate(theta_quintile = coalesce(theta_quintile, 0L)) |>
  select(country_text_id, year, indicator, raw_mean, n_coders, theta_quintile, v2x_regime)

out_pm <- file.path(OUT_DIR, "panel_means.csv")
write_csv(panel_means, out_pm)
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
