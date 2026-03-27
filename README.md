# imdb-episode-dataset

Daily-updated IMDb ratings dataset for the top 10,000 TV series, built for use with the Jellyfin episode ratings grid JS injector.

## Structure

```
data/
  meta.json          ← build metadata + list of all shows (id, title, votes, rating, ep count)
  index.json         ← flat { episodeTconst: { r, v } } for every episode in the dataset
  shows/
    tt0903747.json   ← per-show: { id, title, votes, seasons: { "1": { "1": { r, v } } } }
    tt1520211.json
    ...
```

## Usage in Jellyfin injector

See `scripts/jellyfin-fetcher.js` — drop the helpers into your injector and swap your existing IMDb fetch calls for `getEpisodeRating(seriesTconst, season, episode)`.

Raw file URLs follow this pattern:
```
https://raw.githubusercontent.com/YOUR_USER/imdb-episode-dataset/main/data/shows/{tconst}.json
https://raw.githubusercontent.com/YOUR_USER/imdb-episode-dataset/main/data/index.json
https://raw.githubusercontent.com/YOUR_USER/imdb-episode-dataset/main/data/meta.json
```

## Updating manually

```bash
python scripts/build.py
```

Requires Python 3.10+. No external dependencies — uses only stdlib.

## How it works

1. Downloads three IMDb public datasets (updated daily by IMDb):
   - `title.basics` — series titles and types
   - `title.episode` — episode → series mappings + season/ep numbers
   - `title.ratings` — ratings and vote counts
2. Ranks series by total vote count, takes the top 10,000
3. Joins episode data with ratings, filters out episodes with <10 votes
4. Writes per-show JSON files and a flat index
5. GitHub Actions commits the result daily at 05:00 UTC

## Data source

[IMDb Non-Commercial Datasets](https://developer.imdb.com/non-commercial-datasets/) — free for non-commercial use.
