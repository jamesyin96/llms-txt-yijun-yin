const form = document.querySelector("[data-scan-form]");
const input = document.querySelector("[data-url-input]");
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
      body: JSON.stringify({ url: input.value }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Unable to start scan.");
    }

    const data = await response.json();
    pollScan(data.scan_id);
  } catch (error) {
    setStatus(error.message, true);
  }
});

async function pollScan(scanId) {
  const response = await fetch(`/api/scans/${scanId}`);
  const scan = await response.json();

  if (scan.status === "complete") {
    const pageLabel = scan.pages_included === 1 ? "page" : "pages";
    setStatus(`Complete. Version ${scan.version_number}. ${scan.pages_included} ${pageLabel} included.`);
    resultEl.innerHTML = `<a class="download-link" href="${scan.download_url}">Download llms-v${scan.version_number}.txt</a>`;
    return;
  }

  if (scan.status === "failed") {
    setStatus(scan.error || "Scan failed.", true);
    return;
  }

  setStatus(`Status: ${scan.status}`);
  window.setTimeout(() => pollScan(scanId), 1000);
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}
