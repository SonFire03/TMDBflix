const VIDKING_BASE = "https://www.vidking.net/embed";
const POSTER_BASE = "https://image.tmdb.org/t/p/w500";
const GENRE_MAP = {
  28: "Action", 12: "Aventure", 16: "Animation", 35: "Comedie", 80: "Crime",
  99: "Documentaire", 18: "Drame", 10751: "Famille", 14: "Fantastique", 36: "Histoire",
  27: "Horreur", 10402: "Musique", 9648: "Mystere", 10749: "Romance", 878: "Science-fiction",
  10770: "TV Movie", 53: "Thriller", 10752: "Guerre", 37: "Western", 10759: "Action & Adventure",
  10762: "Kids", 10763: "News", 10764: "Reality", 10765: "Sci-Fi & Fantasy", 10766: "Soap",
  10767: "Talk", 10768: "War & Politics"
};
const CATALOG_CATEGORIES = [
  { name: "Action", genre: 28 },
  { name: "Romance", genre: 10749 },
  { name: "Fantastique", genre: 14 },
  { name: "Science-fiction", genre: 878 },
  { name: "Thriller", genre: 53 },
  { name: "Animation", genre: 16 }
];

const $ = (id) => document.getElementById(id);
const statusEl = $("status");
const searchInput = $("searchInput");
const searchBtn = $("searchBtn");
const frOnlyBtn = $("frOnlyBtn");
const genreFilter = $("genreFilter");
const langFilter = $("langFilter");
const ratingFilter = $("ratingFilter");
const loadMoreBtn = $("loadMoreBtn");
const trendingGrid = $("trendingGrid");
const resultsGrid = $("resultsGrid");
const favoritesGrid = $("favoritesGrid");
const genreStats = $("genreStats");
const categoryRails = $("categoryRails");
const quickRow = $("quickRow");
const themeToggle = $("themeToggle");
const statTrending = $("statTrending");
const statResults = $("statResults");
const statFav = $("statFav");
const chips = Array.from(document.querySelectorAll(".chip[data-filter]"));

const detailModal = $("detailModal");
const closeModalBtn = $("closeModalBtn");
const modalTitle = $("modalTitle");
const modalPoster = $("modalPoster");
const modalMeta = $("modalMeta");
const modalOverview = $("modalOverview");
const modalGenres = $("modalGenres");
const modalWatch = $("modalWatch");

let currentFilter = "all";
let currentQuery = "";
let currentPage = 0;
let totalPages = 0;
let latestResults = [];
let favorites = [];
let searchTimer = null;
let filteredResultsCache = [];

function setStatus(m) { if (statusEl) statusEl.textContent = m; }

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r.json();
}

async function tmdb(endpoint, params = {}) {
  const qs = new URLSearchParams({ endpoint, ...params }).toString();
  try {
    return await api(`/api/v1/tmdb?${qs}`);
  } catch {
    return api(`/api/tmdb?${qs}`);
  }
}

function loadFavorites() { try { favorites = JSON.parse(localStorage.getItem("tmdb_favorites_local") || "[]"); } catch { favorites = []; } }
function saveFavorites() { localStorage.setItem("tmdb_favorites_local", JSON.stringify(favorites)); }
function isFavorite(id, t) { return favorites.some((f) => f.id === id && f.media_type === t); }
function mediaLabel(t) { return t === "movie" ? "Film" : "Serie"; }
function watchLink(item, t) { return t === "movie" ? `${VIDKING_BASE}/movie/${item.id}?autoPlay=true` : `${VIDKING_BASE}/tv/${item.id}/1/1?autoPlay=true`; }
function detailLink(item, t) { return `/title/${t}/${item.id}`; }
function languageBadge(lang) {
  const code = (lang || "").toLowerCase();
  if (code === "fr") return "🇫🇷 FR";
  if (code === "en") return "🇬🇧 EN";
  if (!code) return "🌐 N/A";
  return `🌐 ${code.toUpperCase()}`;
}

function createCard(item, mediaTypeOverride = null, isFavSection = false) {
  const type = mediaTypeOverride || item.media_type || (item.title ? "movie" : "tv");
  const title = item.title || item.name || "Titre inconnu";
  const year = (item.release_date || item.first_air_date || "").split("-")[0] || "N/A";
  const score = typeof item.vote_average === "number" ? item.vote_average.toFixed(1) : "-";
  const lang = languageBadge(item.original_language);
  const poster = item.poster_path ? `${POSTER_BASE}${item.poster_path}` : "";
  const overview = item.overview ? item.overview.slice(0, 100) : "Aucun synopsis disponible.";
  const favActive = isFavorite(item.id, type);
  const imgTag = poster
    ? `<img class="poster is-loading" src="${poster}" alt="Affiche ${title}" loading="lazy" onload="this.classList.remove('is-loading')" onerror="this.classList.remove('is-loading');this.classList.add('is-missing')" />`
    : `<div class="poster is-missing"></div>`;

  const card = document.createElement("article");
  card.className = "card";
  card.innerHTML = `${imgTag}<div class="card-content"><h4 class="card-title">${title}</h4><p class="card-subtitle">${year} · ${overview}</p><div class="meta"><span class="pill">${mediaLabel(type)}</span><span class="lang-badge">${lang}</span><span class="score">⭐ ${score}</span></div><div class="card-actions"><a class="btn btn-outline" href="${watchLink(item, type)}" target="_blank">Regarder</a><a class="btn btn-outline" href="${detailLink(item, type)}" target="_blank">Page</a><button class="btn btn-solid js-details" data-id="${item.id}" data-type="${type}" type="button">Details</button><button class="btn btn-fav js-fav ${favActive ? "active" : ""}" data-id="${item.id}" data-type="${type}" type="button">${favActive ? "Retirer" : "Watchlist"}</button>${isFavSection ? `<button class="btn btn-outline js-remove" data-id="${item.id}" data-type="${type}" type="button">Supprimer</button>` : ""}</div></div>`;
  return card;
}

function renderSkeleton(container, count = 6) {
  if (!container) return;
  container.innerHTML = "";
  for (let i = 0; i < count; i += 1) {
    const b = document.createElement("div");
    b.className = "skeleton";
    container.appendChild(b);
  }
}

function wireCardActions(container, items) {
  if (!container) return;
  container.querySelectorAll(".js-details").forEach((button) => button.addEventListener("click", () => openDetails(button.dataset.id, button.dataset.type).catch(() => setStatus("Erreur detail."))));
  container.querySelectorAll(".js-fav").forEach((button) => button.addEventListener("click", () => {
    const { id, type } = button.dataset;
    const source = items.find((it) => String(it.id) === id && (it.media_type || type) === type);
    if (!source) return;
    if (isFavorite(source.id, type)) favorites = favorites.filter((f) => !(f.id === source.id && f.media_type === type));
    else favorites.unshift({ ...source, media_type: type });
    favorites = favorites.slice(0, 50);
    saveFavorites();
    renderFavorites();
    applyFilterAndRender();
  }));
  container.querySelectorAll(".js-remove").forEach((button) => button.addEventListener("click", () => {
    const id = Number(button.dataset.id);
    const type = button.dataset.type;
    favorites = favorites.filter((f) => !(f.id === id && f.media_type === type));
    saveFavorites();
    renderFavorites();
    applyFilterAndRender();
  }));
}

function renderCards(container, items, mediaTypeOverride = null, isFavSection = false) {
  if (!container) return;
  container.innerHTML = "";
  if (!items.length) { container.innerHTML = '<p class="status status-empty">Aucun element trouve.</p>'; return; }
  items.forEach((item) => container.appendChild(createCard(item, mediaTypeOverride, isFavSection)));
  const mapped = items.map((item) => ({ ...item, media_type: mediaTypeOverride || item.media_type || (item.title ? "movie" : "tv") }));
  wireCardActions(container, mapped);
  bindCarouselButtons();
}

function updateGenreStats(items) {
  if (!genreStats) return;
  const counts = {};
  items.forEach((item) => (item.genre_ids || []).forEach((id) => { counts[id] = (counts[id] || 0) + 1; }));
  const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 6);
  genreStats.innerHTML = top.length
    ? top.map(([id, c]) => `<span class="genre-pill">${GENRE_MAP[id] || `Genre ${id}`}: ${c}</span>`).join("")
    : '<span class="genre-pill">Aucune donnee</span>';
}

function setLoadMoreVisible(show) { if (loadMoreBtn) loadMoreBtn.classList.toggle("hidden", !show); }

function bindCarouselButtons() {
  document.querySelectorAll(".carousel-btn").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => {
      const targetId = btn.dataset.target;
      const dir = btn.dataset.dir;
      const rail = document.getElementById(targetId);
      if (!rail) return;
      const delta = Math.max(rail.clientWidth * 0.9, 280);
      rail.scrollBy({ left: dir === "left" ? -delta : delta, behavior: "smooth" });
    });
  });
}

function applyFilterAndRender() {
  if (!resultsGrid) return;
  let filtered = currentFilter === "all" ? latestResults : latestResults.filter((x) => x.media_type === currentFilter);
  const genre = genreFilter?.value || "";
  const lang = langFilter?.value || "";
  const minRating = Number(ratingFilter?.value || 0);
  if (genre) filtered = filtered.filter((x) => (x.genre_ids || []).includes(Number(genre)));
  if (lang) filtered = filtered.filter((x) => (x.original_language || "").toLowerCase() === lang);
  if (minRating) filtered = filtered.filter((x) => Number(x.vote_average || 0) >= minRating);
  filteredResultsCache = filtered;
  renderCards(resultsGrid, filtered);
  if (statResults) statResults.textContent = String(filtered.length);
  if (statFav) statFav.textContent = String(favorites.length);
  updateGenreStats(filtered);
  setLoadMoreVisible(Boolean(currentQuery) && currentPage < totalPages);
  setStatus(filtered.length ? `${filtered.length} resultat(s) affiches` : "Aucun resultat pour ce filtre.");
}

function renderFavorites() {
  renderCards(favoritesGrid, favorites, null, true);
  if (statFav) statFav.textContent = String(favorites.length);
}

async function loadTrending() {
  if (!trendingGrid) return;
  renderSkeleton(trendingGrid, 6);
  const data = await tmdb("/trending/movie/week");
  const items = (data.results || []).slice(0, 8);
  renderCards(trendingGrid, items, "movie");
  if (statTrending) statTrending.textContent = String(items.length);
  setStatus("Tendances chargees.");
}

async function loadCategoryCatalog() {
  if (!categoryRails) return;
  categoryRails.innerHTML = "";
  for (const category of CATALOG_CATEGORIES) {
    const block = document.createElement("section");
    block.className = "category-block";
    const railId = `cat-${category.genre}`;
    block.innerHTML = `
      <div class="rail-head"><h3>${category.name}</h3></div>
      <div class="carousel-shell">
        <button class="carousel-btn" data-target="${railId}" data-dir="left" type="button">‹</button>
        <div id="${railId}" class="netflix-carousel"></div>
        <button class="carousel-btn" data-target="${railId}" data-dir="right" type="button">›</button>
      </div>
    `;
    const grid = block.querySelector(".netflix-carousel");
    categoryRails.appendChild(block);
    renderSkeleton(grid, 4);
    try {
      const data = await tmdb("/discover/movie", {
        with_genres: category.genre,
        sort_by: "popularity.desc",
        page: 1
      });
      const items = (data.results || []).slice(0, 8).map((x) => ({ ...x, media_type: "movie" }));
      renderCards(grid, items, "movie");
    } catch {
      grid.innerHTML = '<p class="status status-empty">Categorie indisponible.</p>';
    }
  }
  bindCarouselButtons();
}

function normalizeSearch(data) { return (data.results || []).filter((x) => x.media_type === "movie" || x.media_type === "tv"); }

async function performSearch(query, append = false) {
  if (!resultsGrid) return;
  const q = query.trim();
  if (!q) { setStatus("Tapez au moins 2 caracteres."); return; }
  if (!append) { currentQuery = q; currentPage = 1; totalPages = 1; renderSkeleton(resultsGrid, 8); }
  else currentPage += 1;
  const data = await tmdb("/search/multi", { query: currentQuery, page: currentPage });
  totalPages = Math.min(Number(data.total_pages || 1), 20);
  const incoming = normalizeSearch(data);
  latestResults = append ? [...latestResults, ...incoming] : incoming;
  applyFilterAndRender();
}

async function loadMore() { if (currentPage < totalPages) await performSearch(currentQuery, true); }

async function loadFrenchCatalog() {
  if (!resultsGrid) return;
  setStatus("Chargement du catalogue FR...");
  renderSkeleton(resultsGrid, 10);
  currentFilter = "movie";
  if (chips.length) chips.forEach((c) => c.classList.toggle("active", c.dataset.filter === "movie"));

  const collected = [];
  const seen = new Set();
  const maxPages = 20;
  for (let page = 1; page <= maxPages; page += 1) {
    const data = await tmdb("/discover/movie", {
      with_original_language: "fr",
      sort_by: "popularity.desc",
      page
    });
    const items = (data.results || []).map((x) => ({ ...x, media_type: "movie" }));
    for (const item of items) {
      if (seen.has(item.id)) continue;
      seen.add(item.id);
      collected.push(item);
    }
    const total = Math.min(Number(data.total_pages || 1), maxPages);
    setStatus(`Chargement catalogue FR: page ${page}/${total}...`);
    if (page >= total) break;
  }

  latestResults = collected;
  currentQuery = "";
  currentPage = 0;
  totalPages = 0;
  applyFilterAndRender();
  setStatus(`${collected.length} films FR charges.`);
}

function scheduleLiveSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    if (searchInput && searchInput.value.trim().length >= 2) performSearch(searchInput.value, false).catch(() => setStatus("Erreur recherche."));
  }, 350);
}

async function openDetails(id, type) {
  if (!detailModal) return;
  const details = await tmdb(`/${type}/${id}`);
  if (modalTitle) modalTitle.textContent = details.title || details.name || "Detail";
  if (modalPoster) modalPoster.src = details.poster_path ? `${POSTER_BASE}${details.poster_path}` : "";
  if (modalMeta) modalMeta.textContent = `${mediaLabel(type)} · ⭐ ${(details.vote_average || 0).toFixed(1)}`;
  if (modalOverview) modalOverview.textContent = details.overview || "Aucun synopsis disponible.";
  if (modalGenres) modalGenres.textContent = `Genres: ${(details.genres || []).map((g) => g.name).join(", ")}`;
  if (modalWatch) modalWatch.href = watchLink(details, type);
  if (!detailModal.open) detailModal.showModal();
}

function initTheme() {
  if (!themeToggle) return;
  const stored = localStorage.getItem("tmdb_theme") || "dark";
  if (stored === "light") document.body.classList.add("light");
  themeToggle.textContent = stored === "light" ? "Mode sombre" : "Mode clair";
  themeToggle.addEventListener("click", () => {
    document.body.classList.toggle("light");
    const isLight = document.body.classList.contains("light");
    localStorage.setItem("tmdb_theme", isLight ? "light" : "dark");
    themeToggle.textContent = isLight ? "Mode sombre" : "Mode clair";
  });
}

async function bootstrap() {
  initTheme();
  bindCarouselButtons();
  if (closeModalBtn && detailModal) closeModalBtn.addEventListener("click", () => detailModal.close());
  loadFavorites();
  renderFavorites();

  try {
    await loadTrending();
    await loadCategoryCatalog();
  } catch {
    if (trendingGrid) setStatus("Impossible de charger les tendances. Verifiez le serveur API.");
  }

  if (searchBtn && searchInput) {
    searchBtn.addEventListener("click", () => performSearch(searchInput.value).catch(() => setStatus("Erreur recherche.")));
    searchInput.addEventListener("input", scheduleLiveSearch);
    searchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") performSearch(searchInput.value).catch(() => setStatus("Erreur recherche.")); });
  }

  if (loadMoreBtn) loadMoreBtn.addEventListener("click", () => loadMore().catch(() => setStatus("Erreur chargement.")));
  if (frOnlyBtn) frOnlyBtn.addEventListener("click", () => loadFrenchCatalog().catch(() => setStatus("Erreur chargement catalogue FR.")));

  if (quickRow) {
    quickRow.querySelectorAll(".quick").forEach((btn) => btn.addEventListener("click", () => {
      if (!searchInput) return;
      searchInput.value = btn.dataset.query || "";
      performSearch(searchInput.value).catch(() => setStatus("Erreur recherche."));
    }));
  }

  if (chips.length) {
    chips.forEach((chip) => chip.addEventListener("click", () => {
      currentFilter = chip.dataset.filter;
      chips.forEach((c) => c.classList.toggle("active", c === chip));
      applyFilterAndRender();
    }));
  }

  [genreFilter, langFilter, ratingFilter].forEach((el) => {
    if (!el) return;
    el.addEventListener("change", () => applyFilterAndRender());
  });
}

bootstrap();
