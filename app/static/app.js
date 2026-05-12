let portfolioChart;
let signalChart;
let latestData;
let activeSymbol = "all";
let activeDebateSymbol = "all";

const form = document.querySelector("#analyze-form");
const statusEl = document.querySelector("#status");
const summaryEl = document.querySelector("#summary");
const dataSourceEl = document.querySelector("#data-source");
const portfolioEl = document.querySelector("#portfolio");
const mastersEl = document.querySelector("#masters");
const debateEl = document.querySelector("#debate");
const tabsEl = document.querySelector("#filter-tabs");
const debateTabsEl = document.querySelector("#debate-tabs");
const introSection = document.querySelector("#intro-section");
const workspaceEl = document.querySelector("#workspace");
const analysisPanelEl = document.querySelector("#analysis-panel");
const resultSections = document.querySelectorAll(".result-section");

const masterAvatars = {
  Buffett: "/static/assets/masters/buffett.png",
  Graham: "/static/assets/masters/graham.png",
  Lynch: "/static/assets/masters/lynch.png",
  Soros: "/static/assets/masters/soros.png",
  Dalio: "/static/assets/masters/dalio.png",
  Templeton: "/static/assets/masters/templeton.png",
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const symbols = document
    .querySelector("#symbols")
    .value.split(/[\s,，;；]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  const capital = Number.parseInt(document.querySelector("#capital").value, 10);

  setBusy(true);
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols, capital }),
    });
    if (!response.ok) {
      const error = await response.text();
      throw new Error(error);
    }
    latestData = await response.json();
    activeSymbol = "all";
    activeDebateSymbol = "all";
    render(latestData);
    statusEl.textContent = "分析完成";
  } catch (error) {
    statusEl.textContent = "运行失败";
    summaryEl.textContent = error.message;
  } finally {
    setBusy(false);
  }
});

function setBusy(isBusy) {
  const button = form.querySelector("button");
  button.disabled = isBusy;
  button.textContent = isBusy ? "Agent 分析中..." : "运行多 Agent 分析";
  workspaceEl.classList.toggle("is-running", isBusy);
  workspaceEl.classList.toggle("pre-result", isBusy || !latestData);
  workspaceEl.classList.toggle("has-results", !isBusy && Boolean(latestData));
  analysisPanelEl.classList.toggle("hidden", !isBusy);
  if (isBusy) {
    statusEl.textContent = "运行中";
    resultSections.forEach((section) => section.classList.add("hidden"));
    introSection.classList.remove("hidden");
  }
}

function render(data) {
  const { summary, source } = splitSummary(data.summary);
  summaryEl.textContent = summary;
  dataSourceEl.textContent = source ? `数据源：${source}` : "";
  introSection.classList.add("hidden");
  analysisPanelEl.classList.add("hidden");
  workspaceEl.classList.remove("pre-result", "is-running");
  workspaceEl.classList.add("has-results");
  resultSections.forEach((section) => section.classList.remove("hidden"));
  renderPortfolio(data);
  renderTabs(data);
  renderMasters(data);
  renderDebateTabs(data);
  renderDebate(data);
  renderCharts(data);
}

function renderPortfolio(data) {
  portfolioEl.innerHTML = data.portfolio
    .map(
      (item) => `
      <tr>
        <td><strong>${item.symbol}</strong><br /><span class="muted">${item.name}</span></td>
        <td>${actionPill(item.action)}</td>
        <td>${formatPct(item.weight)}</td>
        <td>${item.shares}</td>
        <td>${formatMoney(item.amount)}</td>
        <td>${item.alpha.toFixed(2)}</td>
        <td>${item.risk_penalty.toFixed(2)}</td>
        <td>${item.final_score.toFixed(2)}</td>
        <td>${item.rationale}</td>
      </tr>
    `
    )
    .join("");
}

function renderTabs(data) {
  const symbols = ["all", ...data.request.symbols];
  tabsEl.innerHTML = symbols
    .map((symbol) => `<button class="tab ${symbol === activeSymbol ? "active" : ""}" data-symbol="${symbol}">${symbol === "all" ? "全部" : displaySymbol(data, symbol)}</button>`)
    .join("");
  tabsEl.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      activeSymbol = tab.dataset.symbol;
      renderTabs(latestData);
      renderMasters(latestData);
    });
  });
}

function renderMasters(data) {
  const opinions = data.master_opinions.filter((item) => activeSymbol === "all" || item.symbol === activeSymbol);
  mastersEl.innerHTML = opinions
    .map(
      (item) => `
      <article class="card">
        <div class="card-title">
          <div class="master-identity">
            <img class="master-avatar" src="${masterAvatars[item.master] || masterAvatars.Buffett}" alt="${item.master}" />
            <div>
              <strong>${item.master}</strong>
              <div class="muted">${displaySymbol(data, item.symbol)}</div>
            </div>
          </div>
          ${actionPill(item.action)}
        </div>
        <div class="metric-row">
          <span class="metric">评分 ${item.score.toFixed(2)}</span>
          <span class="metric">修正 ${Number(item.revised_score ?? item.score).toFixed(2)}</span>
          <span class="metric">信心 ${formatPct(item.confidence)}</span>
          <span class="metric">修正信心 ${formatPct(Number(item.revised_confidence ?? item.confidence))}</span>
          <span class="metric">价值 ${item.factors.value.toFixed(2)}</span>
          <span class="metric">质量 ${item.factors.quality.toFixed(2)}</span>
          <span class="metric">成长 ${item.factors.growth.toFixed(2)}</span>
        </div>
        <div class="metric-row">
          ${Object.entries(item.preferred_factors || item.visible_factors || {})
            .sort((a, b) => Number(b[1]) - Number(a[1]))
            .slice(0, 6)
            .map(([key, value]) => `<span class="metric">${key} ${Number(value).toFixed(2)}</span>`)
            .join("")}
        </div>
        <p>${item.reason}</p>
      </article>
    `
    )
    .join("");
}

function renderDebateTabs(data) {
  const symbols = ["all", ...data.request.symbols];
  debateTabsEl.innerHTML = symbols
    .map((symbol) => `<button class="tab ${symbol === activeDebateSymbol ? "active" : ""}" data-symbol="${symbol}">${symbol === "all" ? "全部" : displaySymbol(data, symbol)}</button>`)
    .join("");
  debateTabsEl.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      activeDebateSymbol = tab.dataset.symbol;
      renderDebateTabs(latestData);
      renderDebate(latestData);
    });
  });
}

function renderDebate(data) {
  const debateItems = data.debate.filter((item) => activeDebateSymbol === "all" || item.target_symbol === activeDebateSymbol);
  if (!debateItems.length) {
    debateEl.innerHTML = `<div class="debate-item"><strong>冲突较低</strong><p>大师观点未触发 MAAD 辩论阈值，裁判直接汇总共识。</p></div>`;
    return;
  }
  debateEl.innerHTML = debateItems
    .map(
      (item) => `
      <div class="debate-item">
        <strong>${item.round_name} · ${item.speaker} · ${displaySymbol(data, item.target_symbol)}</strong>
        <p>${item.argument}</p>
      </div>
    `
    )
    .join("");
}

function renderCharts(data) {
  const labels = data.portfolio.map((item) => item.symbol).concat(["现金"]);
  const amounts = data.portfolio.map((item) => item.amount).concat([data.cash]);
  portfolioChart?.destroy();
  portfolioChart = new Chart(document.querySelector("#portfolio-chart"), {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data: amounts,
          backgroundColor: ["#b96f3e", "#6f8d61", "#d8a15f", "#8f7058", "#b65f4f", "#c7b08d", "#d8c8b5"],
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      plugins: { legend: { position: "bottom" } },
    },
  });

  const signalLabels = data.technical_signals.map((item) => item.symbol);
  signalChart?.destroy();
  signalChart = new Chart(document.querySelector("#signal-chart"), {
    type: "bar",
    data: {
      labels: signalLabels,
      datasets: [
        { label: "技术", data: data.technical_signals.map((item) => item.score), backgroundColor: "#b96f3e" },
        { label: "财务", data: data.fundamental_signals.map((item) => item.score), backgroundColor: "#6f8d61" },
        { label: "新闻", data: data.news_signals.map((item) => item.score), backgroundColor: "#d8a15f" },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { min: 0, max: 1 } },
      plugins: { legend: { position: "bottom" } },
    },
  });
}

function actionPill(action) {
  const text = { buy: "买入", hold: "持有", sell: "卖出" }[action] || action;
  return `<span class="pill ${action}">${text}</span>`;
}

function formatPct(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatMoney(value) {
  return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 0 }).format(value);
}

function splitSummary(text) {
  const marker = " 数据源：";
  if (!text.includes(marker)) {
    return { summary: text, source: "" };
  }
  const [summary, sourceWithDot] = text.split(marker);
  return { summary, source: sourceWithDot.replace(/。$/, "") };
}

function displaySymbol(data, symbol) {
  if (symbol === "all") return "全部";
  const price = data.prices.find((item) => item.symbol === symbol);
  if (!price || !price.name || price.name === symbol) return symbol;
  return `${symbol} · ${price.name}`;
}
