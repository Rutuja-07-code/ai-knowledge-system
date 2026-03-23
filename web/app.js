const articleCountEl = document.getElementById("articleCount");
const indexedCountEl = document.getElementById("indexedCount");
const lastUpdatedEl = document.getElementById("lastUpdated");
const activeInterestsEl = document.getElementById("activeInterests");
const interestOptions = document.getElementById("interestOptions");
const interestKeywordsInput = document.getElementById("interestKeywords");
const refreshButton = document.getElementById("refreshButton");
const refreshMessage = document.getElementById("refreshMessage");
const questionForm = document.getElementById("questionForm");
const questionInput = document.getElementById("questionInput");
const answerPanel = document.getElementById("answerPanel");
const answerText = document.getElementById("answerText");
const relatedTopicsPanel = document.getElementById("relatedTopicsPanel");
const relatedTopics = document.getElementById("relatedTopics");
const sourceList = document.getElementById("sourceList");
const articleList = document.getElementById("articleList");
const DEFAULT_INTERESTS = [
  { key: "technology", label: "Technology" },
  { key: "science", label: "Science" },
  { key: "world", label: "World" },
];
const AUTO_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
let availableInterests = [];
let selectedInterests = [];
let interestKeywords = [];
let allArticles = [];
let autoRefreshStarted = false;
let autoRefreshTimer = null;
let refreshInFlight = false;

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
    },
    ...options,
  });

  const rawText = await response.text();
  let payload = {};

  if (rawText) {
    try {
      payload = JSON.parse(rawText);
    } catch (error) {
      payload = {
        error: `The server returned an unexpected response for ${url}.`,
      };
    }
  }

  if (!response.ok) {
    throw new Error(payload.error || `Request failed with status ${response.status}.`);
  }

  return payload;
}

function formatDate(value) {
  if (!value) {
    return "Not yet synced";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function dateRank(value) {
  if (!value) {
    return 0;
  }

  const parsed = new Date(value).getTime();
  if (!Number.isNaN(parsed)) {
    return parsed;
  }

  return 0;
}

function sortArticlesByLatest(articles) {
  return [...articles].sort(
    (left, right) =>
      dateRank(right.published) - dateRank(left.published) ||
      dateRank(right.fetched_at) - dateRank(left.fetched_at)
  );
}

function articleSummary(article) {
  return article.summary || article.content || "No summary available yet.";
}

function articleMeta(article) {
  const parts = [];

  if (article.category) {
    parts.push(article.category);
  }

  if (article.published) {
    parts.push(article.published);
  }

  return parts.join(" • ") || "Publication date unavailable";
}

function renderStatus(status) {
  articleCountEl.textContent = String(status.article_count ?? 0);
  indexedCountEl.textContent = String(status.indexed_count ?? 0);
  lastUpdatedEl.textContent = formatDate(status.last_updated);
}

function parseInterestKeywords(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function interestKeyFromValue(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function buildAvailableInterests(status, articles) {
  const merged = [];
  const seen = new Set();
  const backendInterests = Array.isArray(status.available_interests)
    ? status.available_interests
    : [];

  for (const interest of [...DEFAULT_INTERESTS, ...backendInterests]) {
    if (!interest?.key || !interest?.label || seen.has(interest.key)) {
      continue;
    }

    merged.push(interest);
    seen.add(interest.key);
  }

  for (const article of articles) {
    if (!article?.category) {
      continue;
    }

    const key = interestKeyFromValue(article.category);
    if (!key || seen.has(key)) {
      continue;
    }

    merged.push({
      key,
      label: article.category,
    });
    seen.add(key);
  }

  return merged;
}

function syncInterestState(status, articles) {
  availableInterests = buildAvailableInterests(status, articles);

  const availableKeys = new Set(availableInterests.map((interest) => interest.key));
  const requestedSelection = Array.isArray(status.selected_interests)
    ? status.selected_interests
    : [];
  const filteredSelection = requestedSelection.filter((key) => availableKeys.has(key));

  selectedInterests =
    filteredSelection.length > 0
      ? filteredSelection
      : availableInterests.map((interest) => interest.key);

  interestKeywords = Array.isArray(status.interest_keywords)
    ? status.interest_keywords
    : [];
}

function renderInterestOptions() {
  const allSelected =
    availableInterests.length > 0 && selectedInterests.length === availableInterests.length;

  interestOptions.innerHTML = `
    <button
      type="button"
      class="interest-filter ${allSelected ? "selected" : ""}"
      data-interest-key="all"
    >
      All News
    </button>
    ${availableInterests
    .map(
      (interest) => `
        <button
          type="button"
          class="interest-filter ${selectedInterests.includes(interest.key) ? "selected" : ""}"
          data-interest-key="${escapeAttribute(interest.key)}"
        >
          ${escapeHtml(interest.label)}
        </button>
      `
    )
    .join("")}
  `;
}

function renderActiveInterests() {
  const selectedSet = new Set(selectedInterests);
  const chosen = availableInterests.filter((interest) => selectedSet.has(interest.key));
  const keywordPills = interestKeywords.map(
    (keyword) => `<span class="interest-pill keyword-pill">${escapeHtml(keyword)}</span>`
  );

  if (!chosen.length) {
    activeInterestsEl.innerHTML =
      keywordPills.join("") || `<span class="interest-pill muted">None selected</span>`;
    return;
  }

  activeInterestsEl.innerHTML = chosen
    .map(
      (interest) => `<span class="interest-pill">${escapeHtml(interest.label)}</span>`
    )
    .concat(keywordPills)
    .join("");
}

function renderArticles(articles) {
  if (!articles.length) {
    articleList.innerHTML = `
      <div class="empty-state">
        No articles are loaded yet. Refresh the knowledge base to pull in the
        current RSS feed set.
      </div>
    `;
    return;
  }

  articleList.innerHTML = sortArticlesByLatest(articles)
    .map(
      (article) => `
        <article class="article-card">
          ${article.category ? `<span class="category-badge">${escapeHtml(article.category)}</span>` : ""}
          <h3>${escapeHtml(article.title || "Untitled Article")}</h3>
          <p class="card-meta">${escapeHtml(articleMeta(article))}</p>
          <p class="card-summary">${escapeHtml(articleSummary(article))}</p>
          <a class="card-link" href="${escapeAttribute(article.link || "#")}" target="_blank" rel="noreferrer">
            Open article
          </a>
        </article>
      `
    )
    .join("");
}

function getPrioritizedArticles(articles) {
  if (!articles.length) {
    return [];
  }

  const sortedArticles = sortArticlesByLatest(articles);

  const shouldPrioritizeByInterest =
    availableInterests.length > 0 && selectedInterests.length < availableInterests.length;
  const normalizedKeywords = interestKeywords.map((keyword) => keyword.toLowerCase());
  const selectedInterestTerms = availableInterests
    .filter((interest) => selectedInterests.includes(interest.key))
    .map((interest) => interest.label.toLowerCase());

  if (!shouldPrioritizeByInterest && !normalizedKeywords.length) {
    return sortedArticles;
  }

  const selectedSet = new Set(selectedInterests);

  return sortedArticles
    .map((article, index) => {
      const categoryKey = interestKeyFromValue(article.category);
      const textHaystack = `${article.title || ""} ${article.summary || ""} ${article.content || ""}`
        .toLowerCase();
      let score = 0;

      if (
        shouldPrioritizeByInterest &&
        (selectedSet.has(categoryKey) ||
          selectedInterestTerms.some((term) => textHaystack.includes(term)))
      ) {
        score += 100;
      }

      if (normalizedKeywords.some((keyword) => textHaystack.includes(keyword))) {
        score += 10;
      }

      return {
        article,
        index,
        score,
        publishedRank: dateRank(article.published),
        fetchedRank: dateRank(article.fetched_at),
      };
    })
    .sort(
      (left, right) =>
        right.score - left.score ||
        right.publishedRank - left.publishedRank ||
        right.fetchedRank - left.fetchedRank ||
        left.index - right.index
    )
    .map((item) => item.article);
}

function updateArticleList() {
  renderArticles(getPrioritizedArticles(allArticles));
}

async function refreshKnowledgeBase(messagePrefix = "Refreshing feeds and rebuilding the index...") {
  if (refreshInFlight) {
    return;
  }

  if (!selectedInterests.length) {
    refreshMessage.textContent = "Select at least one area of interest before refreshing.";
    return;
  }

  refreshInFlight = true;
  refreshButton.disabled = true;
  refreshMessage.textContent = messagePrefix;

  try {
    const payload = await fetchJson("/api/refresh", {
      method: "POST",
      body: JSON.stringify({
        selected_interests: selectedInterests,
        interest_keywords: parseInterestKeywords(interestKeywordsInput.value),
      }),
    });

    renderStatus(payload.status);
    allArticles = payload.articles || [];
    syncInterestState(payload.status, allArticles);
    renderInterestOptions();
    interestKeywordsInput.value = interestKeywords.join(", ");
    renderActiveInterests();
    updateArticleList();
    refreshMessage.textContent = payload.message;
  } catch (error) {
    refreshMessage.textContent = error.message;
  } finally {
    refreshInFlight = false;
    refreshButton.disabled = false;
  }
}

function startAutoRefresh() {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer);
  }

  autoRefreshTimer = window.setInterval(() => {
    refreshKnowledgeBase("Checking for latest news updates...");
  }, AUTO_REFRESH_INTERVAL_MS);
}

function renderArticlesError(message) {
  articleList.innerHTML = `
    <div class="empty-state">
      <strong>Unable to load articles.</strong>
      <p>${escapeHtml(message)}</p>
      <p>Start the backend with <code>uvicorn src.web_server:app --reload</code> and open <code>http://127.0.0.1:8000</code>.</p>
    </div>
  `;
}

function renderSources(sources) {
  sourceList.innerHTML = sources
    .map(
      (article) => `
        <article class="source-card">
          ${article.category ? `<span class="category-badge">${escapeHtml(article.category)}</span>` : ""}
          <h3>${escapeHtml(article.title || "Untitled Article")}</h3>
          <p class="card-meta">${escapeHtml(articleMeta(article))}</p>
          <p class="card-summary">${escapeHtml(articleSummary(article))}</p>
          <a class="card-link" href="${escapeAttribute(article.link || "#")}" target="_blank" rel="noreferrer">
            Read source
          </a>
        </article>
      `
    )
    .join("");
}

function renderRelatedTopics(topics) {
  if (!topics.length) {
    relatedTopicsPanel.classList.add("hidden");
    relatedTopics.innerHTML = "";
    return;
  }

  relatedTopicsPanel.classList.remove("hidden");
  relatedTopics.innerHTML = topics
    .map(
      (topic) => `<span class="related-topic-chip">${escapeHtml(topic)}</span>`
    )
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

async function loadDashboard() {
  if (window.location.protocol === "file:") {
    throw new Error(
      "This frontend needs the Python API server. Open it through http://127.0.0.1:8000 instead of opening index.html directly."
    );
  }

  const [statusPayload, articlesPayload] = await Promise.all([
    fetchJson("/api/status"),
    fetchJson("/api/articles"),
  ]);
  const articles = articlesPayload.articles || [];
  allArticles = articles;

  renderStatus(statusPayload);
  syncInterestState(statusPayload, articles);
  renderInterestOptions();
  interestKeywordsInput.value = interestKeywords.join(", ");
  renderActiveInterests();
  updateArticleList();

  if (!autoRefreshStarted) {
    autoRefreshStarted = true;
    refreshKnowledgeBase("Loading the latest news automatically...");
    startAutoRefresh();
  }
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    refreshKnowledgeBase("Updating news after returning to the page...");
  }
});

interestOptions.addEventListener("click", (event) => {
  const clickedElement = event.target;
  if (!(clickedElement instanceof Element)) {
    return;
  }

  const target = clickedElement.closest("[data-interest-key]");
  if (!(target instanceof HTMLElement)) {
    return;
  }

  const selectedKey = target.dataset.interestKey;
  if (selectedKey === "all") {
    selectedInterests = availableInterests.map((interest) => interest.key);
  } else if (selectedInterests.includes(selectedKey)) {
    if (selectedInterests.length === 1) {
      selectedInterests = availableInterests.map((interest) => interest.key);
    } else {
      selectedInterests = selectedInterests.filter((interest) => interest !== selectedKey);
    }
  } else {
    selectedInterests = [...selectedInterests, selectedKey];
  }

  renderInterestOptions();
  renderActiveInterests();
  updateArticleList();
});

interestKeywordsInput.addEventListener("input", () => {
  interestKeywords = parseInterestKeywords(interestKeywordsInput.value);
  renderActiveInterests();
  updateArticleList();
});

refreshButton.addEventListener("click", async () => {
  await refreshKnowledgeBase();
});

questionForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const question = questionInput.value.trim();
  if (!question) {
    answerPanel.classList.remove("hidden");
    answerText.textContent = "Please enter a question before submitting.";
    renderRelatedTopics([]);
    sourceList.innerHTML = "";
    return;
  }

  const submitButton = questionForm.querySelector("button[type='submit']");
  submitButton.disabled = true;
  answerPanel.classList.remove("hidden");
  answerText.textContent = "Searching the indexed articles...";
  renderRelatedTopics([]);
  sourceList.innerHTML = "";

  try {
    const payload = await fetchJson("/api/ask", {
      method: "POST",
      body: JSON.stringify({ question }),
    });

    answerText.textContent = payload.answer || "No answer returned.";
    renderRelatedTopics(payload.related_topics || []);
    renderSources(payload.sources || []);
  } catch (error) {
    answerText.textContent = error.message;
    renderRelatedTopics([]);
    sourceList.innerHTML = "";
  } finally {
    submitButton.disabled = false;
  }
});

loadDashboard().catch((error) => {
  renderArticlesError(error.message);
  refreshMessage.textContent = error.message;
});
