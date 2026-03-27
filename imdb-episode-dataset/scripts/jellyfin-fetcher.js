/**
 * IMDb Dataset Fetcher — drop this into your Jellyfin JS injector
 *
 * Replace YOUR_GITHUB_USER and YOUR_REPO_NAME below.
 * The fetcher tries the per-show JSON first (fast, ~small).
 * Falls back to the flat index if the show file is missing.
 */

const IMDB_DATA_BASE =
  "https://raw.githubusercontent.com/YOUR_GITHUB_USER/YOUR_REPO_NAME/main/data";

// ── Cache so we don't re-fetch on every episode render ──────────────────────
const _showCache  = new Map();   // seriesTconst → seasons object
const _indexCache = new Map();   // episodeTconst → { r, v }
let   _indexLoaded = false;

/**
 * Fetch ratings for a whole series at once.
 * Returns: { "1": { "1": { r: 9.5, v: 12000 }, "2": { ... } }, "2": { ... } }
 *          (season → episode → rating data)
 */
async function fetchShowRatings(seriesTconst) {
  if (_showCache.has(seriesTconst)) return _showCache.get(seriesTconst);

  try {
    const res = await fetch(`${IMDB_DATA_BASE}/shows/${seriesTconst}.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _showCache.set(seriesTconst, data.seasons ?? {});
    return data.seasons ?? {};
  } catch (err) {
    console.warn(`[IMDb] No per-show file for ${seriesTconst}, falling back to index`, err);
    return null;
  }
}

/**
 * Get rating for a specific episode by its IMDb tconst.
 * Tries the flat index (loads it once, then caches).
 */
async function fetchEpisodeRatingByTconst(episodeTconst) {
  if (_indexCache.has(episodeTconst)) return _indexCache.get(episodeTconst);

  if (!_indexLoaded) {
    try {
      const res = await fetch(`${IMDB_DATA_BASE}/index.json`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const index = await res.json();
      for (const [tc, data] of Object.entries(index)) {
        _indexCache.set(tc, data);
      }
      _indexLoaded = true;
    } catch (err) {
      console.error("[IMDb] Failed to load flat index", err);
      return null;
    }
  }

  return _indexCache.get(episodeTconst) ?? null;
}

/**
 * Main entry point — preferred usage.
 *
 * Given the series tconst + season + episode number,
 * returns { r: number, v: number } or null.
 *
 * Example:
 *   const rating = await getEpisodeRating("tt0903747", 1, 3);
 *   // { r: 9.5, v: 45000 }
 */
async function getEpisodeRating(seriesTconst, season, episode) {
  const seasons = await fetchShowRatings(seriesTconst);

  if (seasons) {
    const ep = seasons?.[String(season)]?.[String(episode)];
    if (ep) return ep;
  }

  // Per-show file missing or episode not in it — shouldn't happen often
  return null;
}

// ── Usage in your grid renderer ─────────────────────────────────────────────
//
// When rendering an episode cell, call:
//
//   const data = await getEpisodeRating(seriesTconst, seasonNum, episodeNum);
//   if (data) {
//     cell.dataset.rating = data.r;
//     cell.dataset.votes  = data.v;
//     cell.title = `${data.r}/10 (${data.v.toLocaleString()} votes)`;
//   }
//
// The seriesTconst comes from the Jellyfin API — look for ProviderIds.Imdb
// on the series item, not the episode.
//
// To get it:
//   const seriesInfo = await ApiClient.getItem(ApiClient.getCurrentUserId(), seriesId);
//   const seriesTconst = seriesInfo.ProviderIds?.Imdb;  // e.g. "tt0903747"
