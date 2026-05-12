const form = document.querySelector("[data-scan-form]");
const input = document.querySelector("[data-url-input]");
const crawlMaxPagesInput = document.querySelector("[data-crawl-max-pages]");
const crawlMaxDepthInput = document.querySelector("[data-crawl-max-depth]");
const crawlMaxDurationInput = document.querySelector("[data-crawl-max-duration]");
const autoRefreshDailyInput = document.querySelector("[data-auto-refresh-daily]");
const statusEl = document.querySelector("[data-status]");
const resultEl = document.querySelector("[data-result]");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  resultEl.innerHTML = "";
  setStatus("Starting scan...");

  try {
    const response = await fetch("/api/scans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scanPayload()),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Unable to start scan.");
    }

    const data = await response.json();
    if (data.reused_existing) {
      setStatus(`Using recent version ${data.version_number} (updated within 12 hours).`);
      pollScan(data.scan_id);
      return;
    }
    pollScan(data.scan_id);
  } catch (error) {
    setStatus(error.message, true);
  }
});

function scanPayload() {
  return {
    url: input.value,
    crawl_max_pages: Number(crawlMaxPagesInput.value),
    crawl_max_depth: Number(crawlMaxDepthInput.value),
    crawl_max_duration_seconds: Number(crawlMaxDurationInput.value),
    auto_refresh_daily: autoRefreshDailyInput.checked,
  };
}

async function pollScan(scanId) {
  const response = await fetch(`/api/scans/${scanId}`);
  const scan = await response.json();

  if (scan.status === "complete") {
    const pageLabel = scan.pages_included === 1 ? "page" : "pages";
    const changeText = formatChangeSummary(scan.change_summary);
    const suffix = changeText ? ` ${changeText}.` : "";
    setStatus(`Complete. Version ${scan.version_number}. ${scan.pages_included} ${pageLabel} included.${suffix}`);
    renderResult(scan);
    loadHistory(scan.root_url);
    return;
  }

  if (scan.status === "failed") {
    setStatus(scan.error || "Scan failed.", true);
    loadHistory(scan.root_url);
    return;
  }

  setStatus(`Status: ${scan.status}`);
  window.setTimeout(() => pollScan(scanId), 1000);
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function renderResult(scan) {
  resultEl.innerHTML = "";
  if (!scan.download_url) {
    return;
  }

  const downloadLink = document.createElement("a");
  downloadLink.className = "download-link";
  downloadLink.href = scan.download_url;
  downloadLink.textContent = `Download llms-v${scan.version_number}.txt`;
  resultEl.append(downloadLink);
}

async function loadHistory(rootUrl) {
  try {
    const response = await fetch(`/api/scans?url=${encodeURIComponent(rootUrl)}`);
    if (!response.ok) {
      return;
    }

    const history = await response.json();
    renderHistory(history);
  } catch {
    // History is helpful, but the primary scan/download flow should stay quiet
    // if the optional history request fails.
  }
}

function renderHistory(history) {
  const existingHistory = resultEl.querySelector("[data-history]");
  if (existingHistory) {
    existingHistory.remove();
  }

  if (!history.scans.length) {
    return;
  }

  const section = document.createElement("section");
  section.className = "history";
  section.dataset.history = "";

  const heading = document.createElement("h2");
  heading.textContent = "Version History";
  section.append(heading);

  const list = document.createElement("div");
  list.className = "history-list";

  for (const scan of history.scans) {
    list.append(createHistoryRow(scan));
  }

  section.append(list);
  resultEl.append(section);
}

function createHistoryRow(scan) {
  const row = document.createElement("div");
  row.className = "history-row";

  const summary = document.createElement("div");
  summary.className = "history-summary";

  const title = document.createElement("strong");
  title.textContent = `Version ${scan.version_number}`;

  const detail = document.createElement("span");
  const pageLabel = scan.pages_included === 1 ? "page" : "pages";
  const parts = [`${scan.status}`, `${scan.pages_included} ${pageLabel} included`];
  const createdAtText = formatCreatedAt(scan.created_at);
  if (createdAtText) {
    parts.push(`created ${createdAtText}`);
  }
  const changeText = formatChangeSummary(scan.change_summary);
  if (changeText) {
    parts.push(changeText);
  }
  detail.textContent = parts.join(" · ");

  summary.append(title, detail);
  row.append(summary);

  if (scan.download_url) {
    const link = document.createElement("a");
    link.href = scan.download_url;
    link.textContent = "Download";
    row.append(link);
  }

  return row;
}

function formatCreatedAt(createdAt) {
  if (!createdAt) {
    return "";
  }

  const parsed = new Date(createdAt);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }

  return parsed.toLocaleString();
}

function formatChangeSummary(summary) {
  if (!summary) {
    return "";
  }
  return `+${summary.added} added, -${summary.removed} removed, ${summary.changed} changed`;
}
