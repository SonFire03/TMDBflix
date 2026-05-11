const POSTER_BASE = "https://image.tmdb.org/t/p/w500";

function parseRoute() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return { type: parts[1], id: parts[2] };
}

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function card(item, type) {
  const el = document.createElement("article");
  el.className = "card";
  const title = item.title || item.name || "Titre";
  const poster = item.poster_path ? `${POSTER_BASE}${item.poster_path}` : "";
  el.innerHTML = `<img class="poster" src="${poster}" alt="${title}" /><div class="card-content"><h4>${title}</h4></div>`;
  return el;
}

async function boot() {
  const { type, id } = parseRoute();
  const details = await api(`/api/v1/tmdb?endpoint=/${type}/${id}`);
  const recos = await api(`/api/v1/tmdb?endpoint=/${type}/${id}/recommendations`);
  document.getElementById("titleMain").textContent = details.title || details.name || "Detail";
  document.getElementById("meta").textContent = `⭐ ${(details.vote_average || 0).toFixed(1)}`;
  document.getElementById("overview").textContent = details.overview || "Aucun synopsis.";
  const grid = document.getElementById("recommendations");
  (recos.results || []).slice(0, 12).forEach((i) => grid.appendChild(card(i, type)));
}

boot().catch((e) => { document.getElementById("titleMain").textContent = `Erreur: ${e.message}`; });
