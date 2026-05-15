const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:5000" : "";

const tools = [
  ["youtube", "YouTube Video Downloader", "Download HD videos up to 4K when available.", "youtube", "linear-gradient(135deg,#ff0033,#ff7a59)", "/youtube-video-downloader"],
  ["pinterest", "Pinterest Downloader", "Download public Pinterest videos and media.", "pinterest", "linear-gradient(135deg,#e60023,#ff758f)", "/pinterest-downloader"],
  ["thumbnail", "YouTube Thumbnail Downloader", "Download high-resolution YouTube thumbnails.", "youtube", "linear-gradient(135deg,#ff0033,#ff7a59)", "/youtube-thumbnail-downloader"],
  ["qr", "QR Code Generator", "Create crisp QR codes for URLs, payments, and profiles.", "qr", "linear-gradient(135deg,#111827,#f59e0b)", "/qr-code-generator"],
  ["pdfimage", "PDF To Image", "Export PDF pages as high-quality PNG images.", "pdf", "linear-gradient(135deg,#7c3aed,#f59e0b)", "/pdf-to-image"],
  ["instagram", "Instagram Reel Downloader", "Save reels and posts from public Instagram URLs.", "instagram", "linear-gradient(135deg,#833ab4,#fd1d1d,#fcb045)", "/instagram-reel-downloader"],
  ["upscale", "Image Upscale", "Enhance images with crisp 2x to 4x resizing.", "upscale", "linear-gradient(135deg,#2563eb,#06b6d4)", "/image-upscale"],
  ["enhance", "AI Image Enhancer", "Premium color, sharpness, light, and clarity enhancement.", "enhance", "linear-gradient(135deg,#0ea5e9,#8b5cf6)", "/ai-image-enhancer"],
  ["blur", "Blur Background", "DSLR-style portrait blur effects.", "blur", "linear-gradient(135deg,#111827,#14b8a6)", "/blur-background"],
  ["compress", "Image Compress", "Reduce image size while keeping clean quality.", "compress", "linear-gradient(135deg,#10b981,#22c55e)", "/image-compressor"],
  ["removebg", "Remove Background", "Create transparent PNG cutouts from images.", "removebg", "linear-gradient(135deg,#7c3aed,#ec4899)", "/remove-background"],
  ["audio", "Video To MP3", "Convert supported public videos to MP3 audio.", "audio", "linear-gradient(135deg,#0f766e,#06b6d4)", "/video-to-mp3"],
  ["convert", "Image Converter", "Convert PNG, JPG, and WEBP without quality damage.", "convert", "linear-gradient(135deg,#14b8a6,#2563eb)", "/image-converter"],
  ["imagepdf", "Image To PDF", "Convert JPG, PNG, and WEBP images into one clean PDF.", "pdf", "linear-gradient(135deg,#ef4444,#f97316)", "/image-to-pdf"],
  ["invoice", "Invoice Generator", "Create print-ready business invoices with totals and tax.", "invoice", "linear-gradient(135deg,#0f766e,#f59e0b)", "/invoice-generator"],
];

const comingSoonTools = new Set(["invoice"]);

function icon(name, size = 20) {
  const icons = {
    menu: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>`,
    sun: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>`,
    moon: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5 7 7 0 1 0 20.5 14.5Z"/></svg>`,
    search: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`,
    upload: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12"/><path d="m17 8-5-5-5 5"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/></svg>`,
  };
  return icons[name] || "";
}

function toolIcon(name) {
  const common = `width="28" height="28" viewBox="0 0 24 24" aria-hidden="true"`;
  const stroke = `fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"`;
  const icons = {
    youtube: `<svg width="34" height="24" viewBox="0 0 34 24" aria-hidden="true"><rect x="1" y="1" width="32" height="22" rx="6" fill="#ff0000"/><path d="M14 7.2v9.6L22.4 12 14 7.2Z" fill="#fff"/></svg>`,
    instagram: `<svg ${common} viewBox="0 0 24 24"><defs><linearGradient id="igLogo" x1="3" x2="21" y1="21" y2="3"><stop stop-color="#feda75"/><stop offset=".28" stop-color="#fa7e1e"/><stop offset=".52" stop-color="#d62976"/><stop offset=".75" stop-color="#962fbf"/><stop offset="1" stop-color="#4f5bd5"/></linearGradient></defs><rect x="2.5" y="2.5" width="19" height="19" rx="5.5" fill="url(#igLogo)"/><circle cx="12" cy="12" r="4.1" fill="none" stroke="#fff" stroke-width="1.8"/><circle cx="17.3" cy="6.7" r="1.25" fill="#fff"/></svg>`,
    pinterest: `<svg ${common} viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="#e60023"/><path fill="#fff" d="M12.2 5.1c-4 0-6 2.8-6 5.3 0 1.5.6 2.8 1.8 3.3.2.1.4 0 .5-.2l.2-.9c.1-.3 0-.4-.2-.7-.4-.5-.6-.9-.6-1.7 0-2.1 1.6-4 4.1-4 2.3 0 3.6 1.4 3.6 3.2 0 2.5-1.1 4.5-2.7 4.5-.9 0-1.5-.7-1.3-1.6.3-1.1.8-2.3.8-3.1 0-.7-.4-1.3-1.1-1.3-.9 0-1.6.9-1.6 2.1 0 .8.3 1.3.3 1.3l-1.1 4.5c-.3 1.3-.1 2.9 0 3.1.1.1.2.1.2 0 .1-.1 1.4-1.7 1.8-3.2l.5-1.9c.3.6 1.1 1.1 2 1.1 2.6 0 4.4-2.4 4.4-5.5 0-2.4-2-4.7-5.6-4.7Z"/></svg>`,
    audio: `<svg ${common} ${stroke}><path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/></svg>`,
    removebg: `<svg ${common} viewBox="0 0 24 24" aria-hidden="true"><defs><linearGradient id="removeBgLogo" x1="3" y1="21" x2="21" y2="3"><stop stop-color="#7c3aed"/><stop offset=".52" stop-color="#ec4899"/><stop offset="1" stop-color="#06b6d4"/></linearGradient><pattern id="cutoutGrid" width="4" height="4" patternUnits="userSpaceOnUse"><path d="M0 0h2v2H0zM2 2h2v2H2z" fill="rgba(255,255,255,.55)"/></pattern></defs><rect x="2.5" y="2.5" width="19" height="19" rx="5.5" fill="url(#removeBgLogo)"/><path d="M13 4.5h3.8c1.5 0 2.7 1.2 2.7 2.7V11H13V4.5Z" fill="url(#cutoutGrid)" opacity=".9"/><path d="M13 13h6.5v3.8c0 1.5-1.2 2.7-2.7 2.7H13V13Z" fill="url(#cutoutGrid)" opacity=".72"/><path fill="#fff" d="M10.8 7.2c1.6 0 2.9 1.3 2.9 2.9 0 1-.5 1.9-1.2 2.4 1.9.7 3.2 2.3 3.5 4.3.1.5-.3 1-.9 1H6.5c-.6 0-1-.5-.9-1 .3-2 1.6-3.6 3.5-4.3-.8-.5-1.2-1.4-1.2-2.4 0-1.6 1.3-2.9 2.9-2.9Z"/></svg>`,
    qr: `<svg ${common} ${stroke}><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4z"/><path d="M14 14h2M20 14v2M14 18h2M18 18h2M18 20v-6"/></svg>`,
    convert: `<svg ${common} ${stroke}><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5M8 14h8M13 11l3 3-3 3"/></svg>`,
    invoice: `<svg ${common} ${stroke}><path d="M7 3h10l3 3v15l-2-1-2 1-2-1-2 1-2-1-2 1-2-1V3z"/><path d="M17 3v4h4M9 9h6M9 13h6M9 17h3"/></svg>`,
    pdf: `<svg ${common} ${stroke}><path d="M6 3h9l4 4v14H6z"/><path d="M15 3v5h5"/><path d="M8 16h8"/><path d="M8 12h3"/></svg>`,
    watermark: `<svg ${common} ${stroke}><path d="M4 19V5h16v14z"/><path d="M7 15l3-4 2 3 2-2 3 3"/><path d="M17 7h.01"/></svg>`,
    enhance: `<svg ${common} ${stroke}><path d="M12 3l1.6 4.7L18 9.3l-4.4 1.6L12 16l-1.6-5.1L6 9.3l4.4-1.6L12 3Z"/><path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8L19 14Z"/><path d="M5 15l.7 1.8L8 17.5l-2.3.7L5 20l-.7-1.8L2 17.5l2.3-.7L5 15Z"/></svg>`,
    blur: `<svg ${common} ${stroke}><circle cx="12" cy="12" r="3"/><path d="M3.5 12h2M18.5 12h2M12 3.5v2M12 18.5v2M5.6 5.6 7 7M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4"/><path d="M4 4h16v16H4z"/></svg>`,
    upscale: `<svg ${common} ${stroke}><path d="M4 14V4h10"/><path d="M4 4l7 7"/><path d="M14 20h6v-6"/><path d="M20 20l-7-7"/></svg>`,
    compress: `<svg ${common} ${stroke}><path d="M8 3v5H3M16 3v5h5M8 21v-5H3M16 21v-5h5"/><path d="M3 8l5-5M21 8l-5-5M3 16l5 5M21 16l-5 5"/></svg>`,
    thumbnail: `<svg ${common} ${stroke}><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m10 9 5 3-5 3z"/></svg>`,
  };
  return icons[name] || `<span>${name}</span>`;
}

function initShell() {
  document.body.classList.toggle("tool-page", location.pathname.includes("/pages/") || !!document.querySelector(".tool-shell"));
  document.addEventListener("submit", (event) => {
    if (event.target.matches("[data-upload-form], [data-video-upload-form], [data-url-form], [data-json-form]")) {
      event.preventDefault();
    }
  }, true);
  document.querySelectorAll("[data-icon]").forEach(el => el.innerHTML = icon(el.dataset.icon));
  const menu = document.querySelector(".menu-btn");
  const links = document.querySelector(".nav-links");
  menu?.addEventListener("click", () => links?.classList.toggle("open"));
  links?.querySelectorAll("a").forEach(link => link.addEventListener("click", () => links.classList.remove("open")));
  initThemeToggle();
  const obs = new IntersectionObserver(entries => entries.forEach(e => e.isIntersecting && e.target.classList.add("visible")), { threshold: .14 });
  document.querySelectorAll(".reveal").forEach(el => obs.observe(el));
  document.querySelectorAll("img:not([loading])").forEach((img) => {
    img.loading = "lazy";
    img.decoding = "async";
  });
  initAdSlots();
  initPolicyLinks();
  initProFormEnhancements();
}

function initThemeToggle() {
  const themeButton = document.querySelector("[data-theme]");
  if (!themeButton) return;
  themeButton.classList.add("theme-toggle");

  const applyTheme = (theme) => {
    document.body.classList.toggle("light", theme === "light");
    document.body.classList.toggle("dark", theme === "dark");
    themeButton.innerHTML = `${icon(theme === "dark" ? "sun" : "moon")}<span>${theme === "dark" ? "Switch to white mode" : "Switch to dark mode"}</span>`;
    themeButton.setAttribute("aria-label", theme === "dark" ? "Switch to white mode" : "Switch to dark mode");
    localStorage.setItem("theme", theme);
  };

  applyTheme(localStorage.getItem("theme") || "dark");
  themeButton.addEventListener("click", () => {
    applyTheme(document.body.classList.contains("dark") ? "light" : "dark");
  });
}

function initAdSlots() {
  if (document.querySelector(".ad-slot")) return;
  const isToolPage = location.pathname.includes("/pages/") || !!document.querySelector(".tool-shell");
  const nav = document.querySelector(".nav");
  const hero = document.querySelector(".hero");
  const toolsSection = document.querySelector("#tools");
  const features = document.querySelector("#popular");
  const footer = document.querySelector(".footer");
  const toolShell = document.querySelector(".tool-shell");
  const makeAd = (slot, size = "Responsive ad slot 728x90 / 320x100") => {
    const ad = document.createElement("div");
    ad.className = `container ad-slot ad-slot-${slot} reveal visible`;
    ad.innerHTML = `<span>Advertisement ${slot}</span><strong>${size}</strong>`;
    return ad;
  };
  if (isToolPage) {
    if (nav) nav.insertAdjacentElement("afterend", makeAd("1", "Top banner 728x90 / 320x100"));
    if (footer) footer.insertAdjacentElement("beforebegin", makeAd("2", "Bottom banner 728x90 / 320x100"));
    return;
  }
  if (hero) hero.insertAdjacentElement("afterend", makeAd("1", "After hero banner 728x90 / 320x100"));
  if (features) {
    features.insertAdjacentElement("afterend", makeAd("2", "Before footer banner 728x90 / 320x100"));
  } else if (footer) {
    footer.insertAdjacentElement("beforebegin", makeAd("2", "Bottom banner 728x90 / 320x100"));
  }
}

function initPolicyLinks() {
  const footer = document.querySelector(".footer-inner");
  if (!footer || footer.querySelector(".policy-links") || footer.querySelector(".footer-content")) return;
  const links = document.createElement("div");
  links.className = "policy-links";
  links.innerHTML = `<a href="/about">About</a><a href="/privacy-policy">Privacy</a><a href="/terms">Terms</a><a href="/dmca">DMCA</a><a href="/contact">Contact</a>`;
  footer.appendChild(links);
}

function toast(message) {
  const host = document.querySelector(".toast") || document.body.appendChild(Object.assign(document.createElement("div"), { className: "toast" }));
  const item = document.createElement("div");
  item.className = "toast-item";
  item.textContent = message;
  host.appendChild(item);
  setTimeout(() => item.remove(), 4200);
}

function loading(show) {
  document.querySelector(".spinner")?.classList.toggle("show", show);
  document.querySelectorAll(".progress-wrap").forEach(item => item.classList.toggle("show", show));
}

async function parseJSONResponse(res) {
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(text ? text.slice(0, 180) : "Server returned an empty response.");
  }
  if (!res.ok || !data.success) throw new Error(data.error || data.message || data.detail || `Request failed (${res.status})`);
  return data;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 90000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (error.name === "AbortError") {
      const isRemoveBg = url.includes("/api/image/removebg");
      const message = isRemoveBg 
        ? "AI background removal is taking longer than expected. Try a smaller image or retry in a moment."
        : "Request timed out. Please try a smaller file or restart the server.";
      throw new Error(message);
    }
    throw new Error("Could not reach the server. Make sure Flask is running on port 5000.");
  } finally {
    clearTimeout(timer);
  }
}

function renderCards() {
  const grid = document.querySelector("[data-tools-grid]");
  if (!grid) return;
  const hideable = new Set(["youtube", "thumbnail", "instagram", "pinterest"]);
  const getHidden = () => new Set(JSON.parse(localStorage.getItem("hiddenTools") || "[]"));
  const setHidden = (hidden) => localStorage.setItem("hiddenTools", JSON.stringify([...hidden]));
  let currentQuery = "";
  let hiddenBar = document.querySelector("[data-hidden-tools]");
  if (!hiddenBar) {
    hiddenBar = document.createElement("div");
    hiddenBar.className = "hidden-tools-bar";
    hiddenBar.dataset.hiddenTools = "";
    grid.insertAdjacentElement("beforebegin", hiddenBar);
  }
  const draw = (items) => {
    const hidden = getHidden();
    const visibleItems = items.filter(t => !hidden.has(t[0]));
    const hiddenItems = tools.filter(t => hidden.has(t[0]));
    hiddenBar.innerHTML = hiddenItems.length ? `
      <span>Hidden tools</span>
      ${hiddenItems.map(t => `<button type="button" data-unhide-tool="${t[0]}">Unhide ${t[1]}</button>`).join("")}
    ` : "";
    if (!visibleItems.length) {
      grid.innerHTML = `<div class="empty-search">No tools found. Try searching video, image, PDF, QR, or MP3.</div>`;
      return;
    }
    grid.innerHTML = visibleItems.map(t => {
      const isComingSoon = comingSoonTools.has(t[0]);
      return `
      <div class="tool-card reveal visible${isComingSoon ? " coming-soon" : ""}" data-name="${t[1].toLowerCase()}">
        ${hideable.has(t[0]) ? `<button class="tool-hide-btn" type="button" data-hide-tool="${t[0]}">Hide</button>` : ""}
        ${isComingSoon ? `<span class="tool-status">Coming Soon</span>` : ""}
        ${isComingSoon ? `<div class="tool-card-link" aria-disabled="true">` : `<a class="tool-card-link" href="${t[5]}">`}
          <div class="tool-icon" data-tool="${t[0]}" style="--accent-solid:${t[4]}">${toolIcon(t[3])}</div>
          <h3>${t[1]}</h3>
          <p>${t[2]}</p>
          <span class="open">${isComingSoon ? "Coming soon" : "Open tool -&gt;"}</span>
        ${isComingSoon ? `</div>` : `</a>`}
      </div>`;
    }).join("");
  };
  draw(tools);
  document.querySelector("[data-search]")?.addEventListener("input", e => {
    currentQuery = e.target.value.toLowerCase().trim();
    grid.classList.add("is-searching");
    draw(tools.filter(t => `${t[1]} ${t[2]}`.toLowerCase().includes(currentQuery)));
    window.setTimeout(() => grid.classList.remove("is-searching"), 260);
  });
  document.addEventListener("click", (event) => {
    const hide = event.target.closest("[data-hide-tool]");
    const unhide = event.target.closest("[data-unhide-tool]");
    if (!hide && !unhide) return;
    const hidden = getHidden();
    if (hide) hidden.add(hide.dataset.hideTool);
    if (unhide) hidden.delete(unhide.dataset.unhideTool);
    setHidden(hidden);
    draw(tools.filter(t => `${t[1]} ${t[2]}`.toLowerCase().includes(currentQuery)));
  });
}

async function postJSON(url, body) {
  const res = await fetchWithTimeout(API_BASE + url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseJSONResponse(res);
}

async function postForm(url, formData) {
  const timeoutMs = url.includes("/api/image/removebg") ? 300000 : 90000;
  const res = await fetchWithTimeout(API_BASE + url, { method: "POST", body: formData }, timeoutMs);
  return parseJSONResponse(res);
}

function showError(message) {
  const box = document.querySelector("[data-result]");
  if (!box) return;
  box.classList.add("show", "error");
  box.innerHTML = `
    <div class="result-head"><strong>Could not process</strong><span>Error</span></div>
    <p>${message}</p>
    <div class="result-actions"><button class="btn secondary" type="button" data-dismiss-error>Try again</button></div>`;
  box.querySelector("[data-dismiss-error]")?.addEventListener("click", () => {
    box.classList.remove("show", "error");
    box.innerHTML = "";
  });
}

function showResult(data, options = {}) {
  const box = document.querySelector("[data-result]");
  if (!box) return;
  const autoDownload = options.autoDownload !== false;
  const href = API_BASE + data.download_url + "?download=1";
  const previewHref = data.preview_url ? API_BASE + data.preview_url : API_BASE + data.download_url;
  const label = data.download_label || smartDownloadLabel(data.filename || "");
  const meta = resultMeta(data);
  const preview = resultPreview(data, previewHref);
  box.classList.add("show");
  box.classList.remove("error");
  if (autoDownload) {
    box.innerHTML = `
      <div class="result-head"><strong>${label} started</strong><span>Ready</span></div>
      <p>${data.title || data.filename || "Your file is being prepared."}</p>
      ${meta ? `<div class="result-meta">${meta}</div>` : ""}
      ${preview}
      <div class="result-actions">
        <a class="btn" href="${href}" target="downloadFrame" download>${label}</a>
        <a class="btn secondary" href="${previewHref}" target="_blank" rel="noreferrer">Open result</a>
      </div>
      <iframe name="downloadFrame" title="Download" style="display:none"></iframe>`;
    startDownload(href);
    return;
  }
  box.innerHTML = `
    <div class="result-head"><strong>Ready</strong><span>${label}</span></div>
    <p>${data.title || data.filename || "Your file is ready."}</p>
    ${meta ? `<div class="result-meta">${meta}</div>` : ""}
    ${preview}
    <div class="result-actions">
      <a class="btn" href="${href}" target="downloadFrame" download>${label}</a>
      <a class="btn secondary" href="${previewHref}" target="_blank" rel="noreferrer">Preview</a>
      <button class="btn secondary" type="button" data-copy-link="${previewHref}">Copy link</button>
    </div>
    <iframe name="downloadFrame" title="Download" style="display:none"></iframe>`;
  box.querySelector("[data-copy-link]")?.addEventListener("click", async (event) => {
    try {
      await navigator.clipboard.writeText(event.currentTarget.dataset.copyLink);
      toast("Download link copied.");
    } catch {
      toast("Copy not available in this browser.");
    }
  });
}

function resultPreview(data, previewHref) {
  if (!data.preview_url) return "";
  if (data.preview_type === "pdf") {
    return `<iframe class="result-preview-frame" src="${previewHref}" title="Result preview"></iframe>`;
  }
  return `<img class="result-preview-image" src="${API_BASE + data.preview_url}" alt="Result preview" loading="lazy" decoding="async">`;
}

function startDownload(href) {
  const frame = document.querySelector('iframe[name="downloadFrame"]') || document.body.appendChild(Object.assign(document.createElement("iframe"), {
    name: "downloadFrame",
    title: "Download",
  }));
  frame.style.display = "none";
  frame.src = href;
}

function smartDownloadLabel(filename) {
  const name = filename.toLowerCase();
  if (name.endsWith(".mp3")) return "Download MP3";
  if (name.endsWith(".mp4") || name.endsWith(".webm") || name.endsWith(".mov")) return "Download video";
  if (name.includes("thumbnail")) return "Download thumbnail";
  if (name.includes("qr")) return "Download QR code";
  if (name.endsWith(".pdf")) return "Download PDF";
  if (name.endsWith(".zip")) return "Download ZIP";
  if (name.endsWith(".png") || name.endsWith(".jpg") || name.endsWith(".jpeg") || name.endsWith(".webp")) return "Download image";
  return "Download";
}

function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return "";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function resultMeta(data) {
  const items = [];
  if (data.filename) items.push(data.filename);
  if (data.page_count) items.push(`${data.page_count} page${Number(data.page_count) === 1 ? "" : "s"}`);
  if (data.item_count) items.push(`${data.item_count} item${Number(data.item_count) === 1 ? "" : "s"}`);
  if (data.total) items.push(`Total ${data.total}`);
  if (data.video_height) {
    const fps = data.video_fps ? ` ${Math.round(Number(data.video_fps))}fps` : "";
    items.push(`${data.video_width || ""}${data.video_width ? "x" : ""}${data.video_height}p${fps}`);
  }
  if (data.file_size) items.push(formatBytes(data.file_size));
  if (data.note) items.push(data.note);
  if (data.original_width && data.output_width) {
    items.push(`${data.original_width}x${data.original_height}px to ${data.output_width}x${data.output_height}px`);
  }
  if (data.original_size && data.compressed_size) {
    const saved = Math.max(0, 100 - (Number(data.compressed_size) / Number(data.original_size)) * 100);
    items.push(`${formatBytes(data.original_size)} to ${formatBytes(data.compressed_size)}`);
    items.push(`${saved.toFixed(0)}% smaller`);
  }
  return items.map(item => `<span>${item}</span>`).join("");
}

function appendAutoplayParams(value) {
  if (!value) return "";
  try {
    const url = new URL(value);
    url.searchParams.set("autoplay", "1");
    url.searchParams.set("mute", "1");
    url.searchParams.set("playsinline", "1");
    url.searchParams.set("rel", "0");
    return url.toString();
  } catch {
    return value;
  }
}

function isValidHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function renderPreview(host, data) {
  const ratio = Number(data.aspect_ratio) || 1.7778;
  host.style.setProperty("--preview-ratio", ratio);
  host.classList.add("show");
  host.classList.toggle("is-portrait", ratio < 1);
  const embedUrl = data.embed_url || getYouTubeEmbedUrl(data.webpage_url);
  if (data.preview_video_url) {
    host.classList.remove("embed-preview");
    host.innerHTML = `
      <div class="preview-media">
        <video src="${data.preview_video_url}" ${data.thumbnail ? `poster="${data.thumbnail}"` : ""} controls muted autoplay loop playsinline preload="metadata"></video>
      </div>
      <div class="preview-meta">
        <strong>${data.title || "Media preview"}</strong>
        <p>${data.uploader || "Public source"}${data.duration_text ? ` | ${data.duration_text}` : ""}</p>
        ${data.preview_note ? `<p>${data.preview_note}</p>` : ""}
      </div>`;
    return;
  }
  if (embedUrl) {
    host.classList.add("embed-preview");
    host.innerHTML = `
      <div class="preview-media">
        <iframe src="${appendAutoplayParams(embedUrl)}" title="Video preview" loading="lazy" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen referrerpolicy="no-referrer-when-downgrade"></iframe>
      </div>
      <div class="preview-meta">
        <strong>${data.title || "Video preview"}</strong>
        <p>${data.uploader || "Public source"}</p>
        ${data.preview_note ? `<p>${data.preview_note}</p>` : ""}
      </div>`;
    return;
  }
  host.classList.remove("embed-preview");
  host.innerHTML = `
    <div class="preview-media">
      ${data.thumbnail ? `<img src="${data.thumbnail}" alt="Video preview" loading="lazy" decoding="async">` : `<div class="preview-fallback">Preview</div>`}
    </div>
    <div class="preview-meta">
      <strong>${data.title || "Media preview"}</strong>
      <p>${data.uploader || "Public source"}${data.duration_text ? ` | ${data.duration_text}` : ""}</p>
      ${data.preview_note ? `<p>${data.preview_note}</p>` : ""}
    </div>`;
}

function buildFastPreviewFromUrl(url) {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace("www.", "");
    const youtubeEmbed = getYouTubeEmbedUrl(url);
    if (youtubeEmbed) {
      const isShort = parsed.pathname.includes("/shorts/");
      return {
        success: true,
        title: "YouTube video ready",
        uploader: "youtube.com",
        aspect_ratio: isShort ? 9 / 16 : 16 / 9,
        embed_url: youtubeEmbed,
        webpage_url: url,
        preview_note: "Fast preview loaded. Start download when ready.",
      };
    }
    const instagram = buildSocialPreviewFromUrl(url);
    if (instagram) return instagram;
    if (host.includes("pinterest.")) {
      return {
        success: true,
        title: "Pinterest media ready",
        uploader: host,
        aspect_ratio: 1,
        webpage_url: url,
        preview_note: "Preview is limited, but public media can be downloaded.",
      };
    }
  } catch {
    return null;
  }
  return null;
}

function getYouTubeEmbedUrl(value) {
  if (!value) return "";
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.replace("www.", "");
    let id = parsed.searchParams.get("v");
    if (!id && host === "youtu.be") id = parsed.pathname.slice(1).split("/")[0];
    if (!id && parsed.pathname.includes("/shorts/")) id = parsed.pathname.split("/shorts/")[1].split(/[/?#]/)[0];
    return id ? `https://www.youtube.com/embed/${id}` : "";
  } catch {
    return "";
  }
}

function buildSocialPreviewFromUrl(url) {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace("www.", "");
    const instagramMatch = parsed.pathname.match(/\/(reel|p|tv)\/([^/?#]+)/);
    if (host.includes("instagram.com") && instagramMatch) {
      const type = instagramMatch[1] === "reel" ? "reel" : "p";
      return {
        success: true,
        title: "Instagram preview",
        uploader: "instagram.com",
        aspect_ratio: 1,
        embed_url: `https://www.instagram.com/${type}/${instagramMatch[2]}/embed`,
        preview_note: "Instagram direct thumbnail blocked hai, isliye embed preview dikhaya ja raha hai.",
      };
    }
  } catch {
    return null;
  }
  return null;
}

function initLinkPreview(form) {
  const input = form.querySelector('input[name="url"]');
  if (!input) return;
  const host = document.createElement("div");
  host.className = "link-preview";
  input.insertAdjacentElement("afterend", host);
  let timer = null;
  let lastValue = "";

  const loadPreview = async () => {
    const url = input.value.trim();
    if (!isValidHttpUrl(url) || url === lastValue) return;
    lastValue = url;
    const fastPreview = buildFastPreviewFromUrl(url);
    if (fastPreview) {
      renderPreview(host, fastPreview);
      return;
    }
    host.classList.add("show");
    host.innerHTML = `<div class="preview-fallback">...</div><div><strong>Fetching preview</strong><p>Please wait a moment</p></div>`;
    try {
      const data = await postJSON("/api/media/info", { url });
      renderPreview(host, data);
    } catch {
      const fallback = buildSocialPreviewFromUrl(url);
      if (fallback) {
        renderPreview(host, fallback);
      } else {
        host.classList.add("show");
        host.classList.remove("embed-preview");
        host.innerHTML = `<div class="preview-fallback">Preview</div><div><strong>Limited preview</strong><p>Link public hai to download try kar sakte ho.</p></div>`;
      }
      toast("Preview limited hai. Public link ho to download try karo.");
    }
  };

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(loadPreview, 900);
  });
  input.addEventListener("blur", loadPreview);
}

function initUrlTool() {
  const form = document.querySelector("[data-url-form]");
  if (!form) return;
  initLinkPreview(form);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const endpoint = form.dataset.endpoint;
    const body = Object.fromEntries(new FormData(form));
    const submit = form.querySelector('button[type="submit"]');
    try {
      if (submit) submit.disabled = true;
      loading(true);
      const data = await postJSON(endpoint, body);
      showResult(data);
      toast("Download started.");
    } catch (err) {
      toast(err.message);
      showError(err.message);
    } finally {
      loading(false);
      if (submit) submit.disabled = false;
    }
  });
}

function initJsonTool() {
  const form = document.querySelector("[data-json-form]");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const endpoint = form.dataset.endpoint;
    const body = form.matches("[data-invoice-form]") ? buildInvoicePayload(form) : Object.fromEntries(new FormData(form));
    const submit = form.querySelector('button[type="submit"]');
    try {
      if (submit) submit.disabled = true;
      loading(true);
      const data = await postJSON(endpoint, body);
      showResult(data, { autoDownload: !form.matches("[data-preview-result]") });
      toast(form.matches("[data-preview-result]") ? "Result ready." : "Download started.");
    } catch (err) {
      toast(err.message);
      showError(err.message);
    } finally {
      loading(false);
      if (submit) submit.disabled = false;
    }
  });
}

function buildInvoicePayload(form) {
  const fd = new FormData(form);
  const body = Object.fromEntries(fd);
  const items = [];
  form.querySelectorAll("[data-invoice-items] .invoice-row").forEach((row) => {
    const description = (row.querySelector('[name^="item_desc_"]')?.value || "").trim();
    const qty = row.querySelector('[name^="item_qty_"]')?.value || "";
    const rate = row.querySelector('[name^="item_rate_"]')?.value || "";
    const amount = row.querySelector('[name^="item_amount_"]')?.value || "";
    if (description || qty || rate || amount) {
      items.push({ description, qty, rate, amount });
    }
  });
  body.items = items;
  return body;
}

function initInvoiceForm() {
  const form = document.querySelector("[data-invoice-form]");
  if (!form) return;
  const dateInput = form.querySelector('input[name="date"]');
  const itemsHost = form.querySelector("[data-invoice-items]");
  const addButton = form.querySelector("[data-add-invoice-row]");
  if (dateInput && !dateInput.value) dateInput.valueAsDate = new Date();
  const syncRow = (row) => {
    const qty = Number(row.querySelector('[name^="item_qty_"]')?.value || 0);
    const rate = Number(row.querySelector('[name^="item_rate_"]')?.value || 0);
    const amount = row.querySelector('[name^="item_amount_"]');
    if (amount && qty && rate && !amount.matches(":focus")) {
      amount.value = (qty * rate).toFixed(2);
    }
  };
  const bindRow = (row) => {
    row.addEventListener("input", () => syncRow(row));
    syncRow(row);
  };
  const refreshNumbers = () => {
    itemsHost?.querySelectorAll(".invoice-row").forEach((row, index) => {
      row.querySelector("span").textContent = String(index + 1);
      row.querySelectorAll("input").forEach(input => {
        input.name = input.name.replace(/_\d+$/, `_${index + 1}`);
      });
    });
  };
  const addRow = () => {
    if (!itemsHost) return;
    const index = itemsHost.querySelectorAll(".invoice-row").length + 1;
    const row = document.createElement("div");
    row.className = "invoice-row";
    row.innerHTML = `
      <span>${index}</span>
      <input class="input" name="item_desc_${index}" placeholder="Item name">
      <input class="input" name="item_qty_${index}" type="number" min="0" step="0.01">
      <input class="input" name="item_rate_${index}" type="number" min="0" step="0.01">
      <input class="input" name="item_amount_${index}" type="number" min="0" step="0.01" placeholder="Auto">`;
    itemsHost.appendChild(row);
    bindRow(row);
    row.querySelector("input")?.focus();
  };
  itemsHost?.querySelectorAll(".invoice-row").forEach(bindRow);
  refreshNumbers();
  addButton?.addEventListener("click", addRow);
}

function initUploadTool() {
  const form = document.querySelector("[data-upload-form]");
  if (!form) return;
  const input = form.querySelector("input[type=file]");
  const zone = form.querySelector(".upload-zone");
  const before = document.querySelector("[data-before]");
  const after = document.querySelector("[data-after]");
  const name = document.querySelector("[data-file-name]");
  const action = form.querySelector("[data-upload-action]") || form.querySelector('button[type="submit"]');
  let isProcessing = false;
  const setFile = (file) => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    const selected = input.files?.length || 1;
    name.textContent = selected > 1 ? `${selected} files selected` : `${file.name} - ${formatBytes(file.size)}`;
    if (before) {
      if (form.matches("[data-watermark-form]")) {
        before.innerHTML = `
          <div class="watermark-stage" data-watermark-stage>
            <img src="${url}" alt="Before preview" loading="lazy" decoding="async">
            <button class="watermark-marker" type="button" data-watermark-marker></button>
          </div>`;
        requestAnimationFrame(() => form.__updateWatermarkPreview?.());
      } else {
        before.innerHTML = `<img src="${url}" alt="Before preview" loading="lazy" decoding="async">`;
      }
    }
    if (file.type.startsWith("image/")) {
      readImageDimensions(file).then(size => {
        if (size && name && selected === 1) name.textContent = `${file.name} - ${formatBytes(file.size)} - ${size}`;
      });
    }
  };
  zone.addEventListener("click", (e) => {
    if (e.target === input) return;
    e.preventDefault();
    input.click();
  });
  input.addEventListener("change", () => setFile(input.files[0]));
  ["dragenter", "dragover"].forEach(evt => zone.addEventListener(evt, e => { e.preventDefault(); zone.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach(evt => zone.addEventListener(evt, e => { e.preventDefault(); zone.classList.remove("dragover"); }));
  zone.addEventListener("drop", e => {
    input.files = e.dataTransfer.files;
    setFile(input.files[0]);
  });
  const processUpload = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isProcessing) return;
    if (!input.files[0]) return toast(input.accept?.includes("pdf") ? "Please select a PDF first." : "Please select an image first.");
    const fd = new FormData(form);
    try {
      isProcessing = true;
      if (action) action.disabled = true;
      loading(true);
      const data = await postForm(form.dataset.endpoint, fd);
      const outputUrl = API_BASE + (data.preview_url || data.download_url);
      if (after && data.preview_url) {
        after.innerHTML = `<img src="${outputUrl}" alt="After preview">`;
      }
      showResult(data, { autoDownload: false });
      toast(data.download_label?.includes("PDF") || data.download_label?.includes("ZIP") ? "Result ready." : "Image processed successfully.");
    } catch (err) {
      toast(err.message);
      showError(err.message);
    } finally {
      loading(false);
      isProcessing = false;
      if (action) action.disabled = false;
    }
  };
  form.addEventListener("submit", processUpload, true);
  if (action && action.type === "button") {
    action.addEventListener("click", processUpload);
  }
}

function initVideoUploadTool() {
  const form = document.querySelector("[data-video-upload-form]");
  if (!form) return;
  const input = form.querySelector("input[type=file]");
  const zone = form.querySelector(".upload-zone");
  const videoPreview = document.querySelector("[data-video-preview]");
  const name = form.querySelector("[data-file-name]");
  const submit = form.querySelector('button[type="submit"]');

  const setFile = (file) => {
    if (!file) return;
    name.textContent = `${file.name} - ${formatBytes(file.size)}`;
    if (videoPreview) {
      videoPreview.classList.add("show");
      videoPreview.innerHTML = `<video src="${URL.createObjectURL(file)}" controls muted autoplay loop playsinline></video><div><strong>${file.name}</strong><p>${formatBytes(file.size)} local video selected</p></div>`;
    }
  };

  zone.addEventListener("click", (e) => {
    if (e.target === input) return;
    e.preventDefault();
    input.click();
  });
  input.addEventListener("change", () => setFile(input.files[0]));
  ["dragenter", "dragover"].forEach(evt => zone.addEventListener(evt, e => { e.preventDefault(); zone.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach(evt => zone.addEventListener(evt, e => { e.preventDefault(); zone.classList.remove("dragover"); }));
  zone.addEventListener("drop", e => {
    input.files = e.dataTransfer.files;
    setFile(input.files[0]);
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!input.files[0]) return toast("Please select a video first.");
    const fd = new FormData(form);
    try {
      if (submit) submit.disabled = true;
      loading(true);
      const data = await postForm(form.dataset.endpoint, fd);
      showResult(data, { autoDownload: false });
      toast("MP3 file ready.");
    } catch (err) {
      toast(err.message);
      showError(err.message);
    } finally {
      loading(false);
      if (submit) submit.disabled = false;
    }
  });
}

function readImageDimensions(file) {
  return new Promise(resolve => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(`${img.naturalWidth}x${img.naturalHeight}px`);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve("");
    };
    img.src = url;
  });
}

function initWatermarkStudio() {
  const form = document.querySelector("[data-watermark-form]");
  if (!form) return;
  const textInput = form.querySelector('input[name="text"]');
  const colorInput = form.querySelector('input[name="color"]');
  const fontInput = form.querySelector('select[name="font"]');
  const badgeInput = form.querySelector('select[name="badge"]');
  const positionInput = form.querySelector('select[name="position"]');
  const sizeInput = form.querySelector('input[name="size"]');
  const opacityInput = form.querySelector('input[name="opacity"]');
  const angleInput = form.querySelector('input[name="angle"]');
  const xInput = form.querySelector('input[name="x"]');
  const yInput = form.querySelector('input[name="y"]');
  const presetPositions = {
    "top-left": [18, 18],
    "top-right": [82, 18],
    center: [50, 50],
    "bottom-left": [18, 82],
    "bottom-right": [82, 82],
  };

  const updatePreview = () => {
    const stage = document.querySelector("[data-watermark-stage]");
    const marker = document.querySelector("[data-watermark-marker]");
    if (!stage || !marker) return;
    const x = Number(xInput.value) || 50;
    const y = Number(yInput.value) || 50;
    marker.textContent = (textInput.value || "Watermark").slice(0, 80);
    marker.style.left = `${x}%`;
    marker.style.top = `${y}%`;
    marker.style.color = colorInput.value;
    marker.style.fontFamily = watermarkFontFamily(fontInput.value);
    marker.style.fontSize = `${Math.max(12, Number(sizeInput.value) * 1.35)}px`;
    marker.style.opacity = Math.max(.1, Number(opacityInput.value) / 100);
    marker.style.transform = `translate(-50%, -50%) rotate(${Number(angleInput.value) || 0}deg)`;
    marker.dataset.badge = badgeInput.value;
    stage.classList.toggle("is-tile", positionInput.value === "tile");
  };

  const setPositionFromEvent = (event) => {
    const stage = document.querySelector("[data-watermark-stage]");
    if (!stage) return;
    const rect = stage.getBoundingClientRect();
    const x = Math.max(4, Math.min(96, ((event.clientX - rect.left) / rect.width) * 100));
    const y = Math.max(4, Math.min(96, ((event.clientY - rect.top) / rect.height) * 100));
    xInput.value = x.toFixed(1);
    yInput.value = y.toFixed(1);
    positionInput.value = "manual";
    updatePreview();
  };

  let dragging = false;
  document.addEventListener("pointermove", (event) => {
    if (dragging) setPositionFromEvent(event);
  });
  document.addEventListener("pointerup", () => dragging = false);
  document.addEventListener("pointerdown", (event) => {
    if (event.target.closest("[data-watermark-marker]")) {
      dragging = true;
      setPositionFromEvent(event);
    }
  });
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-watermark-stage]") && !event.target.closest("[data-watermark-marker]")) {
      setPositionFromEvent(event);
    }
  });

  positionInput.addEventListener("change", () => {
    const preset = presetPositions[positionInput.value];
    if (preset) {
      xInput.value = preset[0];
      yInput.value = preset[1];
    }
    updatePreview();
  });

  [textInput, colorInput, fontInput, badgeInput, sizeInput, opacityInput, angleInput].forEach(control => {
    control?.addEventListener("input", updatePreview);
    control?.addEventListener("change", updatePreview);
  });

  form.__updateWatermarkPreview = updatePreview;
}

function watermarkFontFamily(value) {
  const fonts = {
    arial: "Arial, Helvetica, sans-serif",
    "arial-bold": "Arial, Helvetica, sans-serif",
    georgia: "Georgia, serif",
    times: "'Times New Roman', Times, serif",
    verdana: "Verdana, Geneva, sans-serif",
    trebuchet: "'Trebuchet MS', Arial, sans-serif",
  };
  return fonts[value] || fonts.arial;
}

function initProFormEnhancements() {
  document.querySelectorAll(".form-stack").forEach(form => form.classList.add("pro-form"));
  document.querySelectorAll('input[type="range"]').forEach(range => {
    if (range.closest(".range-control")) return;
    const label = range.closest("label");
    if (!label) return;
    const text = Array.from(label.childNodes).find(node => node.nodeType === Node.TEXT_NODE)?.textContent.trim() || "Value";
    const value = document.createElement("strong");
    value.className = "range-value";
    const sync = () => value.textContent = range.value;
    sync();
    range.addEventListener("input", sync);
    label.classList.add("range-control");
    label.innerHTML = `<span>${text}</span>`;
    label.append(range, value);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initShell();
  renderCards();
  initUrlTool();
  initJsonTool();
  initInvoiceForm();
  initWatermarkStudio();
  initUploadTool();
  initVideoUploadTool();
});
