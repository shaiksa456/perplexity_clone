(() => {
  const hero = document.getElementById("hero");
  const thread = document.getElementById("thread");
  const formHero = document.getElementById("askFormHero");
  const formDock = document.getElementById("askFormDock");
  const inputHero = document.getElementById("questionInputHero");
  const inputDock = document.getElementById("questionInputDock");
  const turnTemplate = document.getElementById("turnTemplate");
  const sourceCardTemplate = document.getElementById("sourceCardTemplate");

  let threadId = null;
  let isFirstTurn = true;

  function domainFromUrl(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return url;
    }
  }

  function renderSources(container, sources) {
    container.innerHTML = "";
    (sources || []).forEach((s) => {
      const node = sourceCardTemplate.content.cloneNode(true);
      const a = node.querySelector(".source-card");
      a.href = s.url;
      node.querySelector(".source-index").textContent = `[${s.n}]`;
      node.querySelector(".source-title").textContent = s.title || s.domain;
      node.querySelector(".source-domain").textContent = s.domain || domainFromUrl(s.url);
      container.appendChild(node);
    });
  }

  function linkifyCitations(html, sources) {
    const byIndex = new Map((sources || []).map((s) => [String(s.n), s]));
    // Replace [1] or [1][2] style markers with anchor chips, skip if not a known source
    return html.replace(/\[(\d+)\]/g, (match, num) => {
      const s = byIndex.get(num);
      if (!s) return match;
      return `<a class="cite" href="${s.url}" target="_blank" rel="noopener">${num}</a>`;
    });
  }

  function renderFollowups(container, followups, onPick) {
    container.innerHTML = "";
    (followups || []).forEach((q) => {
      const btn = document.createElement("button");
      btn.className = "followup-btn";
      btn.textContent = q;
      btn.addEventListener("click", () => onPick(q));
      container.appendChild(btn);
    });
  }

  function addTurn(question) {
    const node = turnTemplate.content.cloneNode(true);
    const article = node.querySelector(".turn");
    article.classList.add("loading");
    article.querySelector(".turn-question").textContent = question;
    article.querySelector(".answer-markdown").innerHTML =
      '<span class="loading-dots">Reading sources</span>';
    thread.appendChild(article);
    thread.hidden = false;
    hero.hidden = true;
    article.scrollIntoView({ behavior: "smooth", block: "start" });
    return article;
  }

  function fillTurn(article, data) {
    article.classList.remove("loading");

    if (data.error) {
      article.querySelector(".answer-markdown").innerHTML =
        `<div class="turn-error">${data.error}</div>`;
      return;
    }

    renderSources(article.querySelector(".sources-strip"), data.sources);

    const rawHtml = marked.parse(data.answer_markdown || "");
    article.querySelector(".answer-markdown").innerHTML = linkifyCitations(
      rawHtml,
      data.sources
    );

    renderFollowups(article.querySelector(".followups"), data.followups || [], ask);
  }

  async function ask(question) {
    if (!question.trim()) return;

    if (isFirstTurn) {
      isFirstTurn = false;
      formDock.hidden = false;
    }

    const article = addTurn(question);
    inputHero.value = "";
    inputDock.value = "";
    inputDock.focus();

    try {
      const resp = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, thread_id: threadId }),
      });
      const data = await resp.json();
      threadId = data.thread_id || threadId;

      if (resp.status === 401) {
        window.location.href = "/login";
        return;
      }

      if (!resp.ok || data.error) {
        fillTurn(article, { error: data.error || "Something went wrong." });
        return;
      }

      fillTurn(article, data);
    } catch (err) {
      fillTurn(article, { error: `Network error: ${err.message}` });
    }
  }

  async function loadThread(id) {
    try {
      const resp = await fetch(`/api/history/${encodeURIComponent(id)}`);
      if (!resp.ok) return;
      const data = await resp.json();
      if (!data.messages || !data.messages.length) return;

      threadId = data.thread_id;
      isFirstTurn = false;
      formDock.hidden = false;
      hero.hidden = true;
      thread.hidden = false;
      thread.innerHTML = "";

      data.messages.forEach((m) => {
        const article = addTurn(m.question);
        fillTurn(article, {
          answer_markdown: m.answer_markdown,
          sources: m.sources,
          followups: m.followups,
        });
      });

      thread.lastElementChild?.scrollIntoView({ behavior: "auto", block: "start" });
    } catch (err) {
      // Silently fall back to a fresh search screen if the thread can't load.
      console.error("Failed to load thread:", err);
    }
  }

  formHero.addEventListener("submit", (e) => {
    e.preventDefault();
    ask(inputHero.value);
  });

  formDock.addEventListener("submit", (e) => {
    e.preventDefault();
    ask(inputDock.value);
  });

  document.querySelectorAll(".example-chip").forEach((chip) => {
    chip.addEventListener("click", () => ask(chip.dataset.q));
  });

  if (window.__INITIAL_THREAD_ID__) {
    loadThread(window.__INITIAL_THREAD_ID__);
  }
})();