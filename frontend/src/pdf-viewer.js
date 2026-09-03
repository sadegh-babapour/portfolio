import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.mjs?url";
import "./pdf-viewer.css";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

const pagesElement = document.querySelector("#pdf-pages");
const errorElement = document.querySelector("#pdf-error");
const statusElement = document.querySelector("#page-status");
const zoomInButton = document.querySelector("#zoom-in");
const zoomOutButton = document.querySelector("#zoom-out");
const fitWidthButton = document.querySelector("#fit-width");

const requestedFile = new URLSearchParams(window.location.search).get("file");
const documentUrl = requestedFile ? new URL(requestedFile, window.location.origin) : null;

let pdfDocument = null;
let zoom = 1;
let renderVersion = 0;
let resizeTimer = null;

function applyStoredTheme() {
  const mode = localStorage.getItem("portfolio-theme-mode");
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Edmonton", hour: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date());
  const hour = Number(parts.find((part) => part.type === "hour")?.value || 0);
  const automatic = hour >= 7 && hour < 19 ? "light" : "dark";
  const theme = mode === "light" || mode === "dark" ? mode : automatic;
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

function showError(message) {
  pagesElement.hidden = true;
  pagesElement.setAttribute("aria-busy", "false");
  errorElement.hidden = false;
  errorElement.textContent = message;
  statusElement.textContent = "Unavailable";
}

async function renderDocument() {
  if (!pdfDocument) return;

  const version = ++renderVersion;
  pagesElement.replaceChildren();
  pagesElement.hidden = false;
  pagesElement.setAttribute("aria-busy", "true");
  statusElement.textContent = `Rendering ${pdfDocument.numPages} page${pdfDocument.numPages === 1 ? "" : "s"}…`;

  const availableWidth = Math.max(280, pagesElement.clientWidth - 24);
  const outputScale = Math.min(window.devicePixelRatio || 1, 2);

  for (let pageNumber = 1; pageNumber <= pdfDocument.numPages; pageNumber += 1) {
    if (version !== renderVersion) return;

    const page = await pdfDocument.getPage(pageNumber);
    const naturalViewport = page.getViewport({ scale: 1 });
    const fitScale = availableWidth / naturalViewport.width;
    const cssViewport = page.getViewport({ scale: fitScale * zoom });
    const renderViewport = page.getViewport({ scale: fitScale * zoom * outputScale });

    const pageElement = document.createElement("section");
    pageElement.className = "pdf-page";
    pageElement.setAttribute("aria-label", `Page ${pageNumber}`);

    const canvas = document.createElement("canvas");
    canvas.width = Math.floor(renderViewport.width);
    canvas.height = Math.floor(renderViewport.height);
    canvas.style.width = `${Math.floor(cssViewport.width)}px`;
    canvas.style.height = `${Math.floor(cssViewport.height)}px`;
    pageElement.append(canvas);
    pagesElement.append(pageElement);

    await page.render({ canvas, viewport: renderViewport }).promise;
  }

  if (version === renderVersion) {
    pagesElement.setAttribute("aria-busy", "false");
    statusElement.textContent = `${pdfDocument.numPages} page${pdfDocument.numPages === 1 ? "" : "s"} · ${Math.round(zoom * 100)}%`;
  }
}

function updateZoom(nextZoom) {
  zoom = Math.min(2.5, Math.max(0.6, nextZoom));
  void renderDocument();
}

zoomInButton.addEventListener("click", () => updateZoom(zoom + 0.2));
zoomOutButton.addEventListener("click", () => updateZoom(zoom - 0.2));
fitWidthButton.addEventListener("click", () => updateZoom(1));

window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => void renderDocument(), 180);
});
window.addEventListener("storage", applyStoredTheme);

if (!documentUrl || documentUrl.origin !== window.location.origin) {
  showError("The résumé URL is invalid.");
} else {
  try {
    pdfDocument = await pdfjsLib.getDocument({ url: documentUrl.href }).promise;
    await renderDocument();
  } catch (error) {
    console.error("Unable to render résumé PDF", error);
    showError("The résumé could not be displayed. Use Open full-screen PDF or Download PDF above.");
  }
}
