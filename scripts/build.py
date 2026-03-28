#!/usr/bin/env python3
"""
IMDb Episode Dataset Builder
Downloads IMDb public datasets, filters to top 10,000 TV series by vote count,
and outputs:
  - data/index.json        → { tconst: { r: rating, v: votes } } for ALL episodes
  - data/shows/{tconst}.json → per-show episode data
  - data/meta.json         → build metadata + show index
"""

import gzip
import json
import os
import shutil
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
TOP_N_SHOWS      = 10_000
MIN_VOTES        = 10          # minimum votes for an episode to be included
IMDB_BASE        = "https://datasets.imdbws.com"
DATASETS         = ["title.basics", "title.episode", "title.ratings"]
CACHE_DIR        = Path("/tmp/imdb_cache")
OUTPUT_DIR       = Path("data")
SHOWS_DIR        = OUTPUT_DIR / "shows"

# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def download_dataset(name: str) -> Path:
    """Download and cache a gzipped IMDb TSV dataset."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    gz_path  = CACHE_DIR / f"{name}.tsv.gz"
    tsv_path = CACHE_DIR / f"{name}.tsv"

    if not tsv_path.exists():
        url = f"{IMDB_BASE}/{name}.tsv.gz"
        log(f"Downloading {url} ...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(gz_path, "wb") as f:
            shutil.copyfileobj(resp, f)
        log(f"Decompressing {name} ...")
        with gzip.open(gz_path, "rb") as gz, open(tsv_path, "wb") as out:
            shutil.copyfileobj(gz, out)
        gz_path.unlink()
    else:
        log(f"Using cached {name}")

    return tsv_path


def iter_tsv(path: Path):
    """Yield rows as dicts from a TSV file."""
    with open(path, encoding="utf-8") as f:
        headers = f.readline().rstrip("\n").split("\t")
        for line in f:
            yield dict(zip(headers, line.rstrip("\n").split("\t")))


def null(val: str) -> str | None:
    return None if val == r"\N" else val


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()

    # 1. Download all datasets
    basics_path  = download_dataset("title.basics")
    episode_path = download_dataset("title.episode")
    ratings_path = download_dataset("title.ratings")

    # 2. Load ratings for everything
    log("Loading ratings ...")
    ratings: dict[str, tuple[float, int]] = {}   # tconst → (rating, votes)
    for row in iter_tsv(ratings_path):
        try:
            ratings[row["tconst"]] = (float(row["averageRating"]), int(row["numVotes"]))
        except (ValueError, KeyError):
            pass
    log(f"  {len(ratings):,} rated titles loaded")

    # 3. Find TV series and rank by vote count on the series itself
    log("Identifying TV series ...")
    series_votes: dict[str, int] = {}
    series_names: dict[str, str] = {}
    for row in iter_tsv(basics_path):
        if row.get("titleType") not in ("tvSeries", "tvMiniSeries"):
            continue
        tc = row["tconst"]
        if tc in ratings:
            series_votes[tc] = ratings[tc][1]
            series_names[tc] = row.get("primaryTitle", "")
    log(f"  {len(series_votes):,} rated series found")

    # 4. Select top N
    top_shows = set(
        sorted(series_votes, key=lambda x: series_votes[x], reverse=True)[:TOP_N_SHOWS]
    )
    log(f"  Top {len(top_shows):,} shows selected")

    # 5. Map episodes → parent series
    log("Loading episode map ...")
    ep_to_series: dict[str, str]  = {}   # episode tconst → series tconst
    ep_season:    dict[str, int]  = {}
    ep_number:    dict[str, int]  = {}
    for row in iter_tsv(episode_path):
        parent = row.get("parentTconst", "")
        if parent not in top_shows:
            continue
        tc = row["tconst"]
        ep_to_series[tc] = parent
        try:
            ep_season[tc]  = int(row["seasonNumber"])
            ep_number[tc]  = int(row["episodeNumber"])
        except (ValueError, KeyError):
            ep_season[tc]  = 0
            ep_number[tc]  = 0
    log(f"  {len(ep_to_series):,} episodes mapped")

    # 6. Build per-show data + flat index
    log("Building datasets ...")
    SHOWS_DIR.mkdir(parents=True, exist_ok=True)

    flat_index: dict[str, dict] = {}   # tconst → {r, v}
    show_meta:  list[dict]      = []

    # Group episodes by show
    show_episodes: dict[str, list] = defaultdict(list)
    for ep_tc, series_tc in ep_to_series.items():
        if ep_tc not in ratings:
            continue
        r, v = ratings[ep_tc]
        if v < MIN_VOTES:
            continue
        show_episodes[series_tc].append({
            "tc": ep_tc,
            "s":  ep_season.get(ep_tc, 0),
            "e":  ep_number.get(ep_tc, 0),
            "r":  r,
            "v":  v,
        })
        flat_index[ep_tc] = {"r": r, "v": v}

    # Write per-show JSON files
    for series_tc, episodes in show_episodes.items():
        # Build season map: { "1": { "1": {r, v}, "2": {r, v} } }
        seasons: dict[str, dict] = defaultdict(dict)
        for ep in episodes:
            seasons[str(ep["s"])][str(ep["e"])] = {"r": ep["r"], "v": ep["v"]}

        show_data = {
            "id":      series_tc,
            "title":   series_names.get(series_tc, ""),
            "votes":   series_votes.get(series_tc, 0),
            "seasons": seasons,
        }

        out_path = SHOWS_DIR / f"{series_tc}.json"
        with open(out_path, "w") as f:
            json.dump(show_data, f, separators=(",", ":"))

        # Compute average episode rating for meta
        all_ratings = [ep["r"] for ep in episodes]
        avg = round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else None

        show_meta.append({
            "id":    series_tc,
            "title": series_names.get(series_tc, ""),
            "votes": series_votes.get(series_tc, 0),
            "r":     ratings.get(series_tc, (None,))[0],
            "eps":   len(episodes),
            "avg":   avg,
        })

    log(f"  {len(show_episodes):,} shows with rated episodes written")
    log(f"  {len(flat_index):,} episodes in flat index")

    # 7. Write flat index
    log("Writing index.json ...")
    with open(OUTPUT_DIR / "index.json", "w") as f:
        json.dump(flat_index, f, separators=(",", ":"))

    # 8. Write meta
    log("Writing meta.json ...")
    show_meta.sort(key=lambda x: x["votes"], reverse=True)
    meta = {
        "built":      datetime.now(timezone.utc).isoformat(),
        "top_n":      TOP_N_SHOWS,
        "min_votes":  MIN_VOTES,
        "show_count": len(show_episodes),
        "ep_count":   len(flat_index),
        "shows":      show_meta,
    }
    with open(OUTPUT_DIR / "meta.json", "w") as f:
        json.dump(meta, f, separators=(",", ":"))

    elapsed = round(time.time() - t0, 1)
    log(f"Done in {elapsed}s — {len(flat_index):,} episodes across {len(show_episodes):,} shows")


if __name__ == "__main__":
    main()
