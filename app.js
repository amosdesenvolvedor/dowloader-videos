const form = document.querySelector("#downloadForm");
const button = document.querySelector("#downloadButton");
const statusIcon = document.querySelector("#statusIcon");
const statusTitle = document.querySelector("#statusTitle");
const statusText = document.querySelector("#statusText");
const resultLink = document.querySelector("#resultLink");
const downloadsList = document.querySelector("#downloadsList");
const refreshButton = document.querySelector("#refreshButton");

function setStatus(type, title, text, result) {
  statusIcon.dataset.type = type;
  statusTitle.textContent = title;
  statusText.textContent = text;

  if (result?.url) {
    resultLink.href = result.url;
    resultLink.textContent = result.external ? `Abrir download de ${result.name}` : `Salvar ${result.name}`;
    resultLink.hidden = false;
  } else {
    resultLink.hidden = true;
  }
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) return {};

  try {
    return JSON.parse(text);
  } catch {
    return {
      error: response.ok
        ? "A API retornou uma resposta inválida."
        : `A API retornou erro ${response.status}. Confira os logs da Vercel.`,
    };
  }
}

async function loadDownloads() {
  const response = await fetch("/api/downloads");
  const data = await readJsonResponse(response);
  downloadsList.innerHTML = "";

  const files = Array.isArray(data.files) ? data.files : [];

  if (!files.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = data.message || "Nenhum arquivo baixado ainda.";
    downloadsList.appendChild(empty);
    return;
  }

  for (const file of files) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    const name = document.createElement("strong");
    const size = document.createElement("span");

    item.className = "download-item";
    link.href = file.url;
    link.download = "";
    name.title = file.name;
    name.textContent = file.name;
    size.textContent = formatBytes(file.size);

    link.append(name, size);
    item.appendChild(link);
    downloadsList.appendChild(item);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const payload = {
    url: form.elements.url.value.trim(),
    format: form.elements.format.value,
  };

  button.disabled = true;
  setStatus("working", "Preparando link...", "A API serverless está buscando um link direto para baixar no navegador.");

  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await readJsonResponse(response);

    if (!response.ok || data.error) {
      throw new Error(data.error || "Não foi possível baixar esse link.");
    }

    setStatus("done", "Link pronto", "Abra o link gerado para salvar o arquivo no seu dispositivo.", data.file);
    await loadDownloads();
  } catch (error) {
    setStatus("error", "Falha no download", error.message);
  } finally {
    button.disabled = false;
  }
});

refreshButton.addEventListener("click", loadDownloads);
loadDownloads().catch(() => {
  downloadsList.textContent = "";
  const empty = document.createElement("p");
  empty.className = "empty-state";
  empty.textContent = "Não foi possível carregar a lista.";
  downloadsList.appendChild(empty);
});
