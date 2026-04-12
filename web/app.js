/* ============================================================
   Dashboard — app.js
   Handles auth guard, news feed, Q&A, interest filtering,
   and on-demand transformer summarization.
   ============================================================ */

/* ----- Auth guard ----- */
const profile = (() => {
  try {
    const raw = localStorage.getItem("aiks_profile");
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed.name && Array.isArray(parsed.interests) && parsed.interests.length > 0) {
      return parsed;
    }
    return null;
  } catch (_) {
    return null;
  }
})();

if (!profile) {
  window.location.href = "/index.html";
}

/* ----- DOM refs ----- */
const navAvatar = document.getElementById("navAvatar");
const navName = document.getElementById("navName");
const btnLogout = document.getElementById("btnLogout");
const dashGreeting = document.getElementById("dashGreeting");
const metricArticles = document.getElementById("metricArticles");
const metricIndexed = document.getElementById("metricIndexed");
const metricUpdated = document.getElementById("metricUpdated");
const btnRefreshNews = document.getElementById("btnRefreshNews");
const filterBar = document.getElementById("filterBar");
const questionForm = document.getElementById("questionForm");
const questionInput = document.getElementById("questionInput");
const answerPanel = document.getElementById("answerPanel");
const answerText = document.getElementById("answerText");
const relatedPanel = document.getElementById("relatedPanel");
const relatedChips = document.getElementById("relatedChips");
const sourcePanel = document.getElementById("sourcePanel");
const sourceList = document.getElementById("sourceList");
const articleGrid = document.getElementById("articleGrid");

/* ----- State ----- */
let allArticles = [];
let availableInterests = [];
let activeFilter = "all";
let refreshInFlight = false;

/* ----- Init ----- */
function initProfile() {
  if (!profile) return;
  const initial = profile.name.charAt(0).toUpperCase();
  navAvatar.textContent = initial;
  navName.textContent = profile.name;

  const hour = new Date().getHours();
  let greeting = "Good evening";
  if (hour < 12) greeting = "Good morning";
  else if (hour < 17) greeting = "Good afternoon";
  dashGreeting.textContent = `${greeting}, ${profile.name}`;
}
initProfile();

/* ----- Logout ----- */
btnLogout.addEventListener("click", () => {
  localStorage.removeItem("aiks_profile");
  window.location.href = "/index.html";
});

/* ----- Utilities ----- */
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const raw = await response.text();
  let payload = {};
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch (_) {
      payload = { error: `Unexpected response from ${url}.` };
    }
  }
  if (!response.ok) {
    throw new Error(payload.error || `Request failed (${response.status}).`);
  }
  return payload;
}

function formatDate(value) {
  if (!value) return "Not yet synced";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function dateRank(value) {
  if (!value) return 0;
  const t = new Date(value).getTime();
  return Number.isNaN(t) ? 0 : t;
}

function interestKeyFromValue(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function contentPreview(article) {
  const text = article.content || article.summary || "";
  const words = text.split(/\s+/).slice(0, 28).join(" ");
  return words ? words + "…" : "No content preview available.";
}

function articleMeta(article) {
  const parts = [];
  if (article.category) parts.push(article.category);
  if (article.published) parts.push(article.published);
  return parts.join(" • ") || "Publication date unavailable";
}

/* ----- Render: Status ----- */
function renderStatus(status) {
  metricArticles.textContent = String(status.article_count ?? 0);
  metricIndexed.textContent = String(status.indexed_count ?? 0);
  metricUpdated.textContent = formatDate(status.last_updated);
}

/* ----- Render: Filter bar ----- */
function renderFilterBar() {
  const chips = [
    { key: "all", label: "All News", icon: "📋" },
    ...availableInterests.map((i) => {
      const icons = {
        technology: "💻", science: "🔬", world: "🌍", business: "📊",
        health: "🏥", sports: "⚽", ai_ml: "🤖", climate: "🌿",
      };
      return { key: i.key, label: i.label, icon: icons[i.key] || "📄" };
    }),
  ];

  filterBar.innerHTML = chips
    .map(
      (chip) => `
        <button
          class="filter-chip ${chip.key === activeFilter ? "active" : ""}"
          data-filter="${escapeAttr(chip.key)}"
        >
          ${chip.icon} ${escapeHtml(chip.label)}
        </button>
      `
    )
    .join("");
}

filterBar.addEventListener("click", (event) => {
  const chip = event.target.closest(".filter-chip");
  if (!chip) return;
  activeFilter = chip.dataset.filter;
  renderFilterBar();
  renderArticles();
});

/* ----- Render: Articles ----- */
function getFilteredArticles() {
  let articles = [...allArticles];

  // Sort by date
  articles.sort(
    (a, b) =>
      dateRank(b.published) - dateRank(a.published) ||
      dateRank(b.fetched_at) - dateRank(a.fetched_at)
  );

  // Prioritize by user interests
  const userInterestLabels = new Set(
    (profile.interests || []).map((k) => k.toLowerCase())
  );

  articles = articles.map((article, idx) => {
    const catKey = interestKeyFromValue(article.category);
    let score = 0;
    if (userInterestLabels.has(catKey)) score += 10;
    return { article, score, idx };
  });
  articles.sort((a, b) => b.score - a.score || a.idx - b.idx);
  articles = articles.map((item) => item.article);

  // Filter by active category
  if (activeFilter !== "all") {
    const filterLabel = availableInterests.find((i) => i.key === activeFilter)?.label;
    if (filterLabel) {
      articles = articles.filter(
        (a) => a.category && a.category.toLowerCase() === filterLabel.toLowerCase()
      );
    }
  }

  return articles;
}

function renderArticles() {
  const articles = getFilteredArticles();

  if (!articles.length) {
    articleGrid.innerHTML = `
      <div class="empty-state">
        ${activeFilter !== "all"
          ? "No articles match this filter. Try selecting a different interest."
          : "No articles loaded yet. Click Refresh News when you want to fetch the latest articles."
        }
      </div>
    `;
    return;
  }

  articleGrid.innerHTML = articles
    .map(
      (article) => `
        <div class="article-card" data-link="${escapeAttr(article.link || "")}">
          ${article.category ? `<span class="card-category">${escapeHtml(article.category)}</span>` : ""}
          <h3 class="card-title">${escapeHtml(article.title || "Untitled Article")}</h3>
          <p class="card-meta">${escapeHtml(articleMeta(article))}</p>
          <p class="card-preview">${escapeHtml(contentPreview(article))}</p>
          <div class="card-summary-slot" id="summary-${escapeAttr(btoa(article.link || "").replace(/[^a-zA-Z0-9]/g, ""))}"></div>
          <div class="card-actions">
            <a class="card-link" href="${escapeAttr(article.link || "#")}" target="_blank" rel="noreferrer">Read article ↗</a>
            <button
              class="btn-summarize"
              data-article-link="${escapeAttr(article.link || "")}"
            >
              ✨ Summarize
            </button>
          </div>
        </div>
      `
    )
    .join("");
}

/* ----- Summarize handler ----- */
articleGrid.addEventListener("click", async (event) => {
  const btn = event.target.closest(".btn-summarize");
  if (!btn || btn.disabled) return;

  const link = btn.dataset.articleLink;
  if (!link) return;

  btn.disabled = true;
  btn.classList.add("loading");
  btn.textContent = "⏳ Generating…";

  try {
    const payload = await fetchJson("/api/summarize", {
      method: "POST",
      body: JSON.stringify({ article_link: link }),
    });

    const card = btn.closest(".article-card");
    const slotId = "summary-" + btoa(link).replace(/[^a-zA-Z0-9]/g, "");
    const slot = card.querySelector(`#${slotId}`) || card.querySelector(".card-summary-slot");

    if (slot) {
      slot.innerHTML = `<div class="card-summary-full">${escapeHtml(payload.summary)}</div>`;
    }

    btn.classList.remove("loading");
    btn.classList.add("done");
    btn.textContent = "✓ Summarized";
  } catch (error) {
    btn.classList.remove("loading");
    btn.disabled = false;
    btn.textContent = "✨ Summarize";
    console.error("Summarize error:", error);
  }
});

/* ----- Q&A ----- */
questionForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const question = questionInput.value.trim();
  if (!question) {
    answerPanel.classList.remove("hidden");
    answerText.textContent = "Please enter a question first.";
    relatedPanel.classList.add("hidden");
    sourcePanel.classList.add("hidden");
    return;
  }

  const submitBtn = questionForm.querySelector("button[type='submit']");
  submitBtn.disabled = true;
  answerPanel.classList.remove("hidden");
  answerText.textContent = "Thinking through your question…";
  relatedPanel.classList.add("hidden");
  sourcePanel.classList.add("hidden");
  sourceList.innerHTML = "";

  try {
    const payload = await fetchJson("/api/ask", {
      method: "POST",
      body: JSON.stringify({ question }),
    });

    answerText.textContent = payload.answer || "No answer returned.";

    // Related topics
    const topics = payload.related_topics || [];
    if (topics.length) {
      relatedPanel.classList.remove("hidden");
      relatedChips.innerHTML = topics
        .map((t) => `<span class="related-chip">${escapeHtml(t)}</span>`)
        .join("");
    }

    // Sources
    const sources = payload.sources || [];
    if (sources.length) {
      sourcePanel.classList.remove("hidden");
      sourceList.innerHTML = sources
        .map(
          (s) => `
            <div class="source-card">
              ${s.category ? `<span class="card-category" style="margin-bottom: 6px;">${escapeHtml(s.category)}</span>` : ""}
              <h4>${escapeHtml(s.title || "Untitled")}</h4>
              <p class="source-meta">${escapeHtml(articleMeta(s))}</p>
              <p class="source-summary">${escapeHtml(contentPreview(s))}</p>
              <a class="source-link" href="${escapeAttr(s.link || "#")}" target="_blank" rel="noreferrer">Read source ↗</a>
            </div>
          `
        )
        .join("");
    }
  } catch (error) {
    answerText.textContent = error.message;
  } finally {
    submitBtn.disabled = false;
  }
});

/* ----- Refresh ----- */
async function refreshKnowledgeBase() {
  if (refreshInFlight) return;
  refreshInFlight = true;
  if (btnRefreshNews) {
    btnRefreshNews.disabled = true;
    btnRefreshNews.textContent = "Refreshing...";
  }

  try {
    const payload = await fetchJson("/api/refresh", {
      method: "POST",
      body: JSON.stringify({
        selected_interests: profile.interests,
      }),
    });

    renderStatus(payload.status);
    allArticles = payload.articles || [];

    if (Array.isArray(payload.status.available_interests)) {
      availableInterests = payload.status.available_interests;
    }

    renderFilterBar();
    renderArticles();
  } catch (error) {
    console.error("Refresh error:", error);
  } finally {
    refreshInFlight = false;
    if (btnRefreshNews) {
      btnRefreshNews.disabled = false;
      btnRefreshNews.textContent = "Refresh News";
    }
  }
}

/* ----- Load dashboard ----- */
async function loadDashboard() {
  try {
    const [statusPayload, articlesPayload] = await Promise.all([
      fetchJson("/api/status"),
      fetchJson("/api/articles"),
    ]);

    allArticles = articlesPayload.articles || [];
    availableInterests = statusPayload.available_interests || [];

    renderStatus(statusPayload);
    renderFilterBar();
    renderArticles();
  } catch (error) {
    articleGrid.innerHTML = `
      <div class="empty-state">
        <strong>Unable to connect to the backend.</strong>
        <p style="margin: 8px 0 0; font-size: 0.9rem;">${escapeHtml(error.message)}</p>
        <p style="margin: 8px 0 0; font-size: 0.85rem; color: var(--ink-muted);">
          Start the server with <code>python src/web_server.py</code> and open <code>http://127.0.0.1:8000/</code>.
        </p>
      </div>
    `;
    console.error(error);
  }
}

if (btnRefreshNews) {
  btnRefreshNews.addEventListener("click", () => {
    refreshKnowledgeBase();
  });
}

loadDashboard();
