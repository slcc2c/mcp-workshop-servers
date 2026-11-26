"""Self-contained zero-build HTML/CSS/JS Control Plane for the MCP Workshop Stack Gateway."""

from __future__ import annotations

import html

_DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MCP Workshop Stack Control Plane</title>
  <style>
    :root {
      --bg: #0b1120;
      --panel: #111827;
      --panel-alt: #1f2937;
      --border: #334155;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --ok: #22c55e;
      --warn: #f59e0b;
      --err: #ef4444;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: var(--sans);
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }
    header {
      position: sticky;
      top: 0;
      z-index: 20;
      background: rgba(15, 23, 42, 0.95);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--border);
      padding: 12px 24px 0;
    }
    .header-top {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      padding-bottom: 10px;
    }
    .brand { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .brand h1 { margin: 0; font-size: 1.1rem; font-weight: 600; }
    .tabs {
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
    }
    .tab-btn {
      background: transparent;
      border: 1px solid transparent;
      border-bottom: 2px solid transparent;
      border-radius: 6px 6px 0 0;
      color: var(--muted);
      padding: 8px 14px;
      font-size: 0.86rem;
      font-weight: 600;
      cursor: pointer;
    }
    .tab-btn:hover { color: var(--text); border-color: transparent; }
    .tab-btn.active {
      color: var(--accent);
      background: rgba(56, 189, 248, 0.08);
      border-bottom-color: var(--accent);
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 600;
      background: var(--panel-alt);
      border: 1px solid var(--border);
      max-width: 100%;
      overflow-wrap: anywhere;
      word-break: break-word;
      white-space: normal;
    }
    .pill.ok { color: var(--ok); border-color: rgba(34, 197, 94, 0.4); }
    .pill.warn { color: var(--warn); border-color: rgba(245, 158, 11, 0.4); }
    .pill.err { color: var(--err); border-color: rgba(239, 68, 68, 0.4); }
    .auth-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    input, select, textarea {
      background: var(--panel);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 0.85rem;
    }
    textarea {
      width: 100%;
      font-family: var(--mono);
      font-size: 0.8rem;
      min-height: 110px;
      resize: vertical;
    }
    button {
      background: var(--panel-alt);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 0.85rem;
      cursor: pointer;
    }
    button.mini { padding: 3px 8px; font-size: 0.76rem; }
    button:hover { border-color: var(--accent); }
    button.primary {
      background: #0284c7;
      border-color: #0ea5e9;
      color: #fff;
      font-weight: 600;
    }
    button:disabled { opacity: 0.55; cursor: not-allowed; }
    main {
      max-width: 1360px;
      margin: 0 auto;
      padding: 18px 24px 48px;
      display: grid;
      gap: 16px;
    }
    .tab-panel { display: none; gap: 16px; min-width: 0; }
    .tab-panel.active { display: grid; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
      gap: 14px;
      min-width: 0;
    }
    #tab-registry .grid {
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 480px), 1fr));
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
      min-width: 0;
      overflow-x: auto;
    }
    .pill-wrap {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      align-items: center;
    }
    .card h2 {
      margin: 0 0 10px;
      font-size: 0.95rem;
      color: var(--accent);
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .banner {
      display: none;
      background: rgba(239, 68, 68, 0.12);
      border: 1px solid rgba(239, 68, 68, 0.45);
      border-radius: 10px;
      padding: 12px 16px;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 10px;
    }
    .banner.warn {
      background: rgba(245, 158, 11, 0.12);
      border-color: rgba(245, 158, 11, 0.45);
    }
    .muted { color: var(--muted); font-size: 0.84rem; }
    code, pre { font-family: var(--mono); font-size: 0.8rem; }
    pre {
      background: #020617;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
      overflow-x: auto;
      max-height: 280px;
    }
    table { width: 100%; border-collapse: collapse; font-size: 0.84rem; }
    th, td {
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 600; }
    td code, td .muted { overflow-wrap: anywhere; word-break: break-word; }
    .toolbar, .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
      align-items: center;
    }
    .drawer {
      margin-top: 12px;
      padding: 12px;
      border-radius: 8px;
      background: #0f172a;
      border: 1px solid var(--border);
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .kv {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 0;
      gap: 8px;
    }
    label.inline { display: inline-flex; align-items: center; gap: 6px; font-size: 0.82rem; }
    tr.clickable { cursor: pointer; }
    tr.clickable:hover { background: rgba(56, 189, 248, 0.08); }
    .spark-wrap {
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      align-items: center;
      margin-bottom: 10px;
    }
  </style>
</head>
<body>
  <header>
    <div class="header-top">
      <div class="brand">
        <h1>MCP Workshop Stack Gateway</h1>
        <span class="pill">v__VERSION__</span>
        <span id="overall-pill" class="pill warn">Checking...</span>
        <span id="auth-badge" class="pill warn">Checking session...</span>
      </div>
      <div class="auth-bar">
        <label class="inline muted" for="auto-refresh-select">Auto-refresh
          <select id="auto-refresh-select" aria-label="Auto refresh interval">
            <option value="0" selected>Off</option>
            <option value="15000">15s</option>
            <option value="60000">60s</option>
          </select>
        </label>
        <div id="login-controls" style="display:flex; gap:6px; align-items:center;">
          <input
            id="token-input"
            type="password"
            placeholder="Bearer token or mcp-stack ui open"
            aria-label="Bearer token"
          />
          <button id="login-btn" class="primary" type="button">Sign In</button>
        </div>
        <button id="logout-btn" type="button" style="display:none;">Logout</button>
        <button id="refresh-btn" type="button">Refresh All</button>
      </div>
    </div>
    <nav id="tabs-bar" class="tabs" aria-label="Dashboard sections">
      <button class="tab-btn active" data-tab="overview" type="button">Overview</button>
      <button class="tab-btn" data-tab="playground" type="button">Playground</button>
      <button class="tab-btn" data-tab="traces" type="button">Traces &amp; Evals</button>
      <button class="tab-btn" data-tab="registry" type="button">MLflow Registry</button>
    </nav>
  </header>

  <main>
    <div id="auth-error-banner" class="banner warn">
      <span id="auth-error-text"></span>
      <button id="auth-error-close" class="mini" type="button">Dismiss</button>
    </div>

    <div id="regression-banner" class="banner">
      <div id="regression-text"></div>
      <div style="display:flex; gap:8px; align-items:center;">
        <button id="banner-rebench-btn" class="primary mini" type="button">
          Re-run Golden Benchmark
        </button>
        <button id="banner-traces-btn" class="mini" type="button">Inspect Traces</button>
      </div>
    </div>

    <section id="tab-overview" class="tab-panel active">
      <section class="grid" id="health-grid">
        <div class="card">
          <h2>Gateway &amp; Dependencies</h2>
          <div id="ready-checks" class="muted">Loading /ready...</div>
        </div>
        <div class="card">
          <h2>Profiles &amp; Routes</h2>
          <div id="profiles-box" class="muted">Loading /health...</div>
          <details id="snippets-drawer" style="margin-top:8px;">
            <summary class="muted">Client Config Snippets</summary>
            <div id="snippets-box" class="muted" style="margin-top:6px;">
              Sign in to load client snippets...
            </div>
          </details>
        </div>
        <div class="card">
          <h2>
            <span>Watchdog &amp; Eval Guard</span>
            <span>
              <span id="wd-pill" class="pill">--</span>
              <span id="wd-eval-pill" class="pill">--</span>
            </span>
          </h2>
          <div id="watchdog-box" class="muted">Sign in to load /api/v1/watchdog</div>
        </div>
      </section>

      <section class="card">
        <h2>Operational Actions</h2>
        <div class="actions">
          <button id="act-uc-btn" type="button">Refresh UC Tools</button>
          <button id="act-wd-btn" type="button">Run Watchdog Check (Dry Run)</button>
          <button id="act-eval-btn" type="button">Run Trace Eval (Last 20)</button>
          <button id="bench-btn" class="primary" type="button">Run Golden Benchmark</button>
          <label class="inline muted">
            <input id="judge-toggle" type="checkbox" /> Ollama judge
          </label>
          <input
            id="judge-model-input"
            type="text"
            value="ollama:/qwen3.8:27b"
            aria-label="Ollama judge model"
            style="width:190px;"
          />
          <span id="action-status" class="muted"></span>
        </div>
        <pre id="action-output" style="display:none; margin-top:10px;"></pre>
      </section>

      <section class="card">
        <h2>
          <span>
            Mounted Servers &amp; External Upstreams
            <span id="srv-inv-count" class="pill">0</span>
          </span>
          <span class="muted">Live connection status (gateway &amp; federated proxies)</span>
        </h2>
        <div id="servers-health-box" class="muted">Loading /health...</div>
      </section>
    </section>

    <section id="tab-playground" class="tab-panel">
      <section class="card">
        <h2>
          <span>
            Tool Browser &amp; Playground
            <span id="tool-count" class="pill">0 tools</span>
          </span>
          <span class="muted">Filter, inspect schema, or run live tools</span>
        </h2>
        <div class="toolbar">
          <select id="profile-filter"><option value="">All Profiles</option></select>
          <select id="server-filter"><option value="">All Servers</option></select>
          <input
            id="tool-search"
            type="search"
            placeholder="Search tools or descriptions..."
            style="min-width:260px;"
          />
        </div>
        <div id="playground-card" class="drawer" style="display:none;">
          <div class="kv" style="margin-bottom:8px;">
            <div>
              <strong>Playground:</strong>
              <code id="pg-server"></code> / <code id="pg-tool"></code>
            </div>
            <div style="display:flex; gap:8px; align-items:center;">
              <span id="pg-latency" class="pill">idle</span>
              <button id="pg-close-btn" class="mini" type="button">Close</button>
            </div>
          </div>
          <textarea id="pg-args" aria-label="Tool JSON arguments"></textarea>
          <div class="toolbar" style="margin-top:8px; margin-bottom:0;">
            <button id="pg-run-btn" class="primary" type="button">Run Tool</button>
            <span id="pg-status" class="muted"></span>
          </div>
          <pre id="pg-output" style="display:none; margin-top:10px;"></pre>
        </div>
        <div id="tools-body" class="muted" style="margin-top:10px;">
          Sign in to browse live tools...
        </div>
      </section>
    </section>

    <section id="tab-traces" class="tab-panel">
      <section class="card">
        <h2>
          <span>Eval Run History &amp; Regression Guard</span>
          <a href="http://localhost:5002" target="_blank" rel="noopener">
            Open MLflow UI (:5002) &rarr;
          </a>
        </h2>
        <div id="eval-summary" class="muted" style="margin-bottom:8px;"></div>
        <div class="spark-wrap">
          <div id="eval-sparkline" class="muted"></div>
        </div>
        <div id="eval-history-body" class="muted"></div>
      </section>

      <section class="card">
        <h2>
          <span>MLflow Traces &amp; Span Drilldown</span>
          <span class="muted">Filter by server, user, model, or policy refusal</span>
        </h2>
        <div class="toolbar">
          <select id="tr-experiment-filter" aria-label="MLflow experiment">
            <option value="">Default Experiment</option>
          </select>
          <select id="tr-server-filter"><option value="">All Servers</option></select>
          <select id="tr-user-filter"><option value="">All Users</option></select>
          <select id="tr-model-filter"><option value="">All LoggedModels</option></select>
          <select id="tr-state-filter">
            <option value="">All States</option>
            <option value="OK">OK</option>
            <option value="ERROR">ERROR</option>
          </select>
          <select id="tr-refusal-filter">
            <option value="all">Refusals: All</option>
            <option value="only">Refusals Only</option>
            <option value="exclude">Exclude Refusals</option>
          </select>
          <input id="tr-search" type="search" placeholder="Search trace ID, span, tool..." />
          <button id="tr-apply-btn" class="mini primary" type="button">Filter</button>
          <button id="tr-reset-btn" class="mini" type="button">Reset</button>
        </div>
        <div id="traces-body" class="muted">Sign in to load MLflow traces...</div>
        <div id="trace-detail-box" class="drawer" style="display:none;"></div>
      </section>
    </section>

    <section id="tab-registry" class="tab-panel">
      <section class="card">
        <h2>
          <span>
            MLflow Registry
            <span id="reg-mutations-pill" class="pill">read-only</span>
          </span>
          <button id="reg-refresh-btn" class="mini" type="button">Reload Registry</button>
        </h2>
        <div id="reg-status" class="muted">
          Sign in to inspect MCP Servers, Prompts &amp; Models.
        </div>
        <div id="prompt-preview-box" class="drawer" style="display:none;"></div>
      </section>

      <section class="grid">
        <div class="card">
          <h2>MCP Server Registry <span id="reg-srv-count" class="pill">0</span></h2>
          <div id="reg-mcp-servers" class="muted">Loading...</div>
        </div>
        <div class="card">
          <h2>Prompt Registry <span id="reg-prompt-count" class="pill">0</span></h2>
          <div id="reg-prompts" class="muted">Loading...</div>
        </div>
      </section>

      <section class="grid">
        <div class="card">
          <h2>LoggedModels <span id="reg-lm-count" class="pill">0</span></h2>
          <div id="reg-logged-models" class="muted">Loading...</div>
        </div>
        <div class="card">
          <h2>Registered Models <span id="reg-rm-count" class="pill">0</span></h2>
          <div id="reg-models" class="muted">Loading...</div>
        </div>
      </section>
    </section>
  </main>

  <script>
    let loadedTools = [];
    let profileCountsCache = {};
    let healthProfiles = [];
    let healthServersCount = 0;
    let refreshTimer = null;
    let actionBusy = false;
    let authState = { authenticated: false, authEnabled: true, mlflowMutationsEnabled: false };

    const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[ch]));

    async function apiFetch(path, options = {}) {
      const headers = new Headers(options.headers || {});
      const method = String(options.method || "GET").toUpperCase();
      if (method !== "GET" && method !== "HEAD") {
        headers.set("X-Requested-With", "mcp-ui");
      }
      const res = await fetch(path, {
        ...options,
        headers,
        credentials: "same-origin",
      });
      const text = await res.text();
      let json = null;
      try { json = JSON.parse(text); } catch {}
      if (!res.ok) {
        const msg = json?.error?.message || json?.error || ("HTTP " + res.status);
        const err = new Error(msg);
        err.status = res.status;
        throw err;
      }
      return json;
    }

    function badge(ok, okLabel = "healthy", failLabel = "degraded") {
      const cls = ok ? "ok" : "err";
      return '<span class="pill ' + cls + '">' + esc(ok ? okLabel : failLabel) + "</span>";
    }

    function switchTab(tabName) {
      const valid = new Set(["overview", "playground", "traces", "registry"]);
      const chosen = valid.has(tabName) ? tabName : "overview";
      document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.tab === chosen);
      });
      document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === "tab-" + chosen);
      });
      if (window.location.hash !== "#" + chosen) {
        history.replaceState(null, "", "#" + chosen);
      }
    }

    function copyText(text, btn) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
          const orig = btn.textContent;
          btn.textContent = "Copied";
          setTimeout(() => { btn.textContent = orig; }, 1200);
        });
      }
    }

    function renderRegressionBanner(reg) {
      const banner = document.getElementById("regression-banner");
      const textEl = document.getElementById("regression-text");
      if (!reg || reg.status !== "regression") {
        banner.style.display = "none";
        return;
      }
      const failing = Object.entries(reg.failing_metrics || {}).map(
        ([k, v]) => '<span class="pill err">' + esc(k) + "=" + esc(v) + "</span>"
      ).join(" ");
      textEl.innerHTML =
        "<strong>Eval Regression Detected</strong> (threshold &ge; " +
        esc(reg.threshold) + ", run <code>" + esc(reg.run_id || "n/a") +
        "</code>) " + failing;
      banner.style.display = "flex";
    }

    function renderAuthBar() {
      const pill = document.getElementById("auth-badge");
      const loginCtrls = document.getElementById("login-controls");
      const logoutBtn = document.getElementById("logout-btn");
      if (!authState.authEnabled) {
        pill.textContent = "Local (Open)";
        pill.className = "pill ok";
        loginCtrls.style.display = "none";
        logoutBtn.style.display = "none";
      } else if (authState.authenticated) {
        pill.textContent = "Signed in: " + (authState.clientName || authState.clientId || "client");
        pill.className = "pill ok";
        loginCtrls.style.display = "none";
        logoutBtn.style.display = "inline-block";
      } else {
        pill.textContent = "Locked";
        pill.className = "pill warn";
        loginCtrls.style.display = "flex";
        logoutBtn.style.display = "none";
      }
    }

    async function loadSessionMe() {
      try {
        authState = await apiFetch("/api/v1/auth/me");
      } catch {
        authState = { authenticated: false, authEnabled: true, mlflowMutationsEnabled: false };
      }
      renderAuthBar();
    }

    function renderProfileRows() {
      const origin = window.location.origin;
      const box = document.getElementById("profiles-box");
      if (!healthProfiles.length) return;
      box.innerHTML = healthProfiles.map((p) => {
        const cnt = profileCountsCache[p.name];
        const countTag = typeof cnt === "number" ? " (" + cnt + " tools)" : "";
        const fullUrl = origin + p.route;
        return '<div class="kv"><code>' + esc(p.route) + "</code>" +
          '<span><span class="muted">' + esc((p.servers || []).length) +
          " srv" + esc(countTag) + "</span> " +
          '<button class="mini copy-url-btn" data-url="' + esc(fullUrl) +
          '" type="button">Copy URL</button></span></div>';
      }).join("") + '<div class="kv"><code>/mcp</code>' +
        '<span><span class="muted">' + esc(healthServersCount) +
        ' total mounted</span> <button class="mini copy-url-btn" data-url="' +
        esc(origin + "/mcp") + '" type="button">Copy URL</button></span></div>';

      box.querySelectorAll(".copy-url-btn").forEach((btn) => {
        btn.addEventListener("click", () => copyText(btn.dataset.url || "", btn));
      });
    }

    function seedArgsFromSchema(schema) {
      const props = (schema && schema.properties) || {};
      const req = new Set((schema && schema.required) || []);
      const out = {};
      for (const [k, def] of Object.entries(props)) {
        if (!req.has(k) && def.default === undefined) continue;
        if (def.default !== undefined) out[k] = def.default;
        else if (def.type === "integer" || def.type === "number") out[k] = 0;
        else if (def.type === "boolean") out[k] = false;
        else if (def.type === "array") out[k] = [];
        else if (def.type === "object") out[k] = {};
        else out[k] = "";
      }
      return out;
    }

    function openPlayground(idx) {
      const tool = loadedTools[idx];
      if (!tool) return;
      switchTab("playground");
      const card = document.getElementById("playground-card");
      document.getElementById("pg-server").textContent = tool.server;
      document.getElementById("pg-tool").textContent = tool.name;
      document.getElementById("pg-args").value = JSON.stringify(
        seedArgsFromSchema(tool.parameters), null, 2
      );
      document.getElementById("pg-latency").textContent = "ready";
      document.getElementById("pg-latency").className = "pill";
      document.getElementById("pg-status").textContent = tool.description || "";
      document.getElementById("pg-output").style.display = "none";
      card.style.display = "block";
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    async function runPlaygroundTool() {
      const server = document.getElementById("pg-server").textContent.trim();
      const tool = document.getElementById("pg-tool").textContent.trim();
      const argsRaw = document.getElementById("pg-args").value.trim() || "{}";
      const outEl = document.getElementById("pg-output");
      const statusEl = document.getElementById("pg-status");
      const latEl = document.getElementById("pg-latency");
      const runBtn = document.getElementById("pg-run-btn");

      let parsedArgs;
      try {
        parsedArgs = JSON.parse(argsRaw);
      } catch (err) {
        statusEl.textContent = "Invalid JSON: " + err.message;
        return;
      }

      runBtn.disabled = true;
      actionBusy = true;
      statusEl.textContent = "Invoking...";
      try {
        const res = await apiFetch("/api/v1/actions/call-tool", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ server, tool, arguments: parsedArgs }),
        });
        latEl.textContent = (res.durationMs ?? "-") + " ms";
        if (res.ok) {
          latEl.className = "pill ok";
          statusEl.textContent = res.truncated ? "OK (truncated)" : "OK";
        } else if (res.policyRefusal) {
          latEl.className = "pill warn";
          statusEl.textContent = "Policy Refusal";
        } else {
          latEl.className = "pill err";
          statusEl.textContent = "Error";
        }
        outEl.style.display = "block";
        outEl.textContent = JSON.stringify(res, null, 2);
        loadTraces().catch(() => {});
      } catch (err) {
        latEl.className = "pill err";
        latEl.textContent = "failed";
        statusEl.textContent = err.message;
        outEl.style.display = "block";
        outEl.textContent = err.message;
      } finally {
        actionBusy = false;
        runBtn.disabled = false;
      }
    }

    async function loadHealthAndReady() {
      const [health, ready] = await Promise.all([apiFetch("/health"), apiFetch("/ready")]);
      const pill = document.getElementById("overall-pill");
      const isReady = ready.status === "ready";
      pill.textContent = ready.status.toUpperCase();
      pill.className = "pill " + (isReady ? "ok" : "warn");

      const checks = ready.checks || {};
      document.getElementById("ready-checks").innerHTML =
        Object.entries(checks).map(([k, v]) => {
          const ok = Boolean(v.healthy ?? v.reachable);
          return '<div class="kv"><code>' + esc(k) + "</code>" +
            badge(ok, "ok", "down") + "</div>";
        }).join("");

      healthProfiles = health.profiles || [];
      const servers = health.servers || [];
      healthServersCount = servers.length;

      const profSel = document.getElementById("profile-filter");
      const prevProf = profSel.value;
      profSel.innerHTML = '<option value="">All Profiles</option>' + healthProfiles.map(
        (p) => '<option value="' + esc(p.name) + '">' + esc(p.name) +
          " (" + esc(p.route) + ")</option>"
      ).join("");
      profSel.value = prevProf;

      const srvSel = document.getElementById("server-filter");
      const prevSrv = srvSel.value;
      srvSel.innerHTML = '<option value="">All Servers</option>' + servers.map(
        (s) => '<option value="' + esc(s.slug) + '">' + esc(s.slug) +
          (s.external ? " (external: " + esc(s.connectionStatus || s.status) + ")" : "") +
          "</option>"
      ).join("");
      srvSel.value = prevSrv;

      const invBox = document.getElementById("servers-health-box");
      document.getElementById("srv-inv-count").textContent = servers.length;
      invBox.innerHTML = servers.length
        ? '<div class="grid">' + servers.map((s) => {
            const st = s.connectionStatus || s.status || "enabled";
            const cls = st === "connected" || st === "enabled"
              ? "ok"
              : (st === "auth_required" || st === "configured" ? "warn" : "err");
            const extra = [];
            if (s.external) extra.push('<span class="pill">external</span>');
            if (typeof s.toolCount === "number") {
              extra.push('<span class="pill">' + esc(s.toolCount) + " tools</span>");
            }
            return '<div class="kv"><div><code>' + esc(s.slug) + "</code> " +
              extra.join(" ") +
              (s.detail ? '<div class="muted">' + esc(s.detail) + "</div>" : "") +
              '</div><span class="pill ' + cls + '">' + esc(st) + "</span></div>";
          }).join("") + "</div>"
        : "No servers mounted.";

      renderProfileRows();
    }

    async function loadProfileSnippets() {
      const box = document.getElementById("snippets-box");
      try {
        const data = await apiFetch("/api/v1/profiles");
        const snippets = data.clientSnippets || {};
        const entries = Object.entries(snippets).filter(
          ([k]) => k === "codex" || k === "claude-code" || k === "cursor"
        );
        if (!entries.length) {
          box.textContent = "No client snippets available.";
          return;
        }
        box.innerHTML = entries.map(([name, body]) => (
          '<div style="margin-bottom:8px;">' +
          '<div class="kv"><strong>' + esc(name) + "</strong>" +
          '<button class="mini copy-snip-btn" data-name="' + esc(name) +
          '" type="button">Copy</button></div>' +
          '<pre style="max-height:140px;">' + esc(body) + "</pre></div>"
        )).join("");
        box.querySelectorAll(".copy-snip-btn").forEach((btn) => {
          btn.addEventListener("click", () => {
            copyText(snippets[btn.dataset.name] || "", btn);
          });
        });
      } catch (err) {
        box.textContent = err.status === 401
          ? "Sign in via mcp-stack ui open or token to view client snippets."
          : err.message;
      }
    }

    async function loadWatchdog() {
      const box = document.getElementById("watchdog-box");
      const wdPill = document.getElementById("wd-pill");
      const evalPill = document.getElementById("wd-eval-pill");
      try {
        const data = await apiFetch("/api/v1/watchdog");
        const comps = data.components || {};
        const entries = Object.entries(comps);
        const allOk = entries.length > 0 && entries.every(([, v]) => Boolean(v.healthy));
        wdPill.textContent = entries.length ? (allOk ? "healthy" : "degraded") : "no state";
        wdPill.className = "pill " + (allOk ? "ok" : "warn");

        const reg = data.evalRegression;
        if (reg && reg.status === "ok") {
          evalPill.textContent = "eval " + (reg.min_score ?? 1.0);
          evalPill.className = "pill ok";
        } else if (reg && reg.status === "regression") {
          evalPill.textContent = "eval regression (" + reg.min_score + ")";
          evalPill.className = "pill err";
        } else {
          evalPill.textContent = "eval " + ((reg && reg.status) || "n/a");
          evalPill.className = "pill";
        }
        renderRegressionBanner(reg);

        if (!entries.length) {
          box.textContent = "No watchdog state file found yet.";
          return;
        }
        box.innerHTML = entries.map(([name, info]) => (
          '<div class="kv"><code>' + esc(name) + "</code><span>" +
          badge(Boolean(info.healthy), "ok", "unhealthy") + "</span></div>"
        )).join("") + '<div class="muted" style="margin-top:6px;">Last check: ' +
          esc(data.lastRunAt || "n/a") + "</div>";
      } catch (err) {
        wdPill.textContent = err.status === 401 ? "locked" : "error";
        wdPill.className = "pill warn";
        evalPill.textContent = "--";
        evalPill.className = "pill";
        box.textContent = err.status === 401
          ? "Sign in to view watchdog state."
          : err.message;
      }
    }

    async function loadTools() {
      const body = document.getElementById("tools-body");
      const countEl = document.getElementById("tool-count");
      const profile = document.getElementById("profile-filter").value;
      const server = document.getElementById("server-filter").value;
      const q = document.getElementById("tool-search").value.trim();
      const params = new URLSearchParams();
      if (profile) params.set("profile", profile);
      if (server) params.set("server", server);
      if (q) params.set("q", q);
      const qs = params.toString() ? ("?" + params.toString()) : "";
      try {
        const data = await apiFetch("/api/v1/tools" + qs);
        loadedTools = data.tools || [];
        profileCountsCache = data.profileCounts || {};
        renderProfileRows();
        countEl.textContent = loadedTools.length + " tools";
        if (!loadedTools.length) {
          body.textContent = "No matching tools.";
          return;
        }
        const rows = loadedTools.slice(0, 150).map((t, idx) => (
          "<tr><td><code>" + esc(t.name) + "</code>" +
          '<div style="margin-top:4px;"><button class="mini try-tool-btn" data-idx="' + idx +
          '" type="button">Try Tool</button></div></td>' +
          "<td><span class='pill'>" + esc(t.server) + "</span></td>" +
          "<td>" + esc(t.description || "") +
          "<details style='margin-top:4px;'><summary class='muted'>schema</summary><pre>" +
          esc(JSON.stringify(t.parameters || {}, null, 2)) + "</pre></details></td></tr>"
        )).join("");
        body.innerHTML =
          "<table><thead><tr><th>Tool</th><th>Server</th>" +
          "<th>Description &amp; Schema</th></tr></thead><tbody>" + rows + "</tbody></table>";
        body.querySelectorAll(".try-tool-btn").forEach((btn) => {
          btn.addEventListener("click", () => openPlayground(Number(btn.dataset.idx)));
        });
      } catch (err) {
        countEl.textContent = "0 tools";
        body.textContent = err.status === 401
          ? "Sign in to browse /api/v1/tools."
          : err.message;
      }
    }

    async function curateTrace(traceId, endpoint, body, statusEl) {
      statusEl.textContent = "Saving...";
      try {
        const res = await apiFetch("/api/v1/traces/" + encodeURIComponent(traceId) + endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        statusEl.textContent = res.promoted
          ? "Promoted to " + (res.dataset?.dataset_name || "dataset") + "!"
          : "Saved (" + (res.assessmentId || res.key || "ok") + ").";
        await inspectTrace(traceId);
      } catch (err) {
        statusEl.textContent = "Error: " + err.message;
      }
    }

    async function inspectTrace(traceId) {
      const detailBox = document.getElementById("trace-detail-box");
      detailBox.style.display = "block";
      detailBox.textContent = "Loading spans for " + traceId + "...";
      detailBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
      try {
        const tr = await apiFetch("/api/v1/traces/" + encodeURIComponent(traceId));
        const stPill = badge(String(tr.state).includes("OK"), "OK", tr.state);
        const tagList = Object.entries(tr.tags || {}).slice(0, 8).map(
          ([k, v]) => '<span class="pill">' + esc(k) + "=" + esc(v) + "</span>"
        ).join(" ");
        const metaRow =
          '<div class="toolbar" style="margin:6px 0;">' +
          '<span class="pill">user=' + esc(tr.user || "anonymous") + "</span>" +
          (tr.sessionId ? '<span class="pill">session=' + esc(tr.sessionId) + "</span>" : "") +
          (tr.modelId ? '<span class="pill">model=' + esc(tr.modelId) + "</span>" : "") +
          tagList + "</div>";
        const assessHtml = (tr.assessments || []).length
          ? '<div class="muted" style="margin:6px 0;">Assessments: ' +
            tr.assessments.map((a) =>
              '<span class="pill">' + esc(a.name) + "=" + esc(a.value) + "</span>"
            ).join(" ") + "</div>"
          : "";
        const spansHtml = (tr.spans || []).map((sp) => (
          '<div style="margin-top:8px; padding-top:8px; border-top:1px solid var(--border);">' +
          "<div><strong>" + esc(sp.name) + "</strong> " +
          '<span class="pill">' + esc(sp.spanType) + "</span> " +
          '<span class="muted">' + esc(sp.durationMs ?? "-") + " ms</span></div>" +
          '<div class="muted" style="margin-top:4px;">Inputs</div><pre>' +
          esc(JSON.stringify(sp.inputs, null, 2)) + "</pre>" +
          '<div class="muted">Outputs</div><pre>' +
          esc(JSON.stringify(sp.outputs, null, 2)) + "</pre>" +
          ((sp.events || []).length
            ? '<div class="muted">Events</div><pre>' +
              esc(JSON.stringify(sp.events, null, 2)) + "</pre>"
            : "") +
          "</div>"
        )).join("") || "<div class='muted'>No spans recorded.</div>";
        const curationBar =
          '<div style="margin:10px 0; padding:10px; border:1px solid var(--border); ' +
          'border-radius:6px; background:#0b1120;">' +
          '<div class="toolbar" style="margin-bottom:6px;">' +
          '<input id="cur-rationale" type="text" placeholder="Feedback rationale (optional)" ' +
          'style="min-width:190px;" />' +
          '<button id="cur-yes" class="mini" type="button">Helpful (yes)</button>' +
          '<button id="cur-no" class="mini" type="button">Needs Work (no)</button>' +
          '<select id="cur-exp"><option value="ok">ok</option>' +
          '<option value="policy_refusal">policy_refusal</option></select>' +
          '<button id="cur-log-exp" class="mini" type="button">Log Expectation</button>' +
          '</div><div class="toolbar" style="margin-bottom:0;">' +
          '<input id="cur-tag-k" type="text" placeholder="tag key" style="width:120px;" />' +
          '<input id="cur-tag-v" type="text" placeholder="tag value" style="width:120px;" />' +
          '<button id="cur-add-tag" class="mini" type="button">Add Tag</button>' +
          '<button id="cur-promote" class="mini primary" type="button">' +
          "Promote to Golden Dataset</button>" +
          '<span id="cur-status" class="muted"></span></div></div>';
        detailBox.innerHTML =
          '<div class="kv"><div><strong>Trace:</strong> <code>' + esc(tr.traceId) +
          "</code> " + stPill + ' <span class="muted">' + esc(tr.durationMs) +
          ' ms</span></div><button id="close-trace-btn" class="mini" type="button">' +
          "Close</button></div>" + metaRow + assessHtml + curationBar + spansHtml;
        const curStatus = document.getElementById("cur-status");
        document.getElementById("close-trace-btn").addEventListener("click", () => {
          detailBox.style.display = "none";
        });
        document.getElementById("cur-yes").addEventListener("click", () => curateTrace(
          tr.traceId, "/feedback",
          { name: "human_quality", value: "yes",
            rationale: document.getElementById("cur-rationale").value.trim() || null },
          curStatus
        ));
        document.getElementById("cur-no").addEventListener("click", () => curateTrace(
          tr.traceId, "/feedback",
          { name: "human_quality", value: "no",
            rationale: document.getElementById("cur-rationale").value.trim() || null },
          curStatus
        ));
        document.getElementById("cur-log-exp").addEventListener("click", () => curateTrace(
          tr.traceId, "/expectation",
          { name: "expected_outcome", value: document.getElementById("cur-exp").value },
          curStatus
        ));
        document.getElementById("cur-add-tag").addEventListener("click", () => curateTrace(
          tr.traceId, "/tag",
          { key: document.getElementById("cur-tag-k").value.trim(),
            value: document.getElementById("cur-tag-v").value.trim() },
          curStatus
        ));
        document.getElementById("cur-promote").addEventListener("click", () => curateTrace(
          tr.traceId, "/promote-to-dataset",
          { expected_outcome: document.getElementById("cur-exp").value },
          curStatus
        ));
      } catch (err) {
        detailBox.textContent = "Failed to load trace details: " + err.message;
      }
    }

    function renderEvalSparkline(evalHistory) {
      const sparkEl = document.getElementById("eval-sparkline");
      const histBody = document.getElementById("eval-history-body");
      if (!evalHistory || !evalHistory.length) {
        sparkEl.innerHTML = "";
        histBody.textContent = "No MLflow GenAI eval runs logged yet.";
        return;
      }
      const ordered = [...evalHistory].reverse();
      const w = 240;
      const h = 48;
      const pad = 6;
      const step = ordered.length > 1 ? (w - pad * 2) / (ordered.length - 1) : 0;
      const pts = ordered.map((run, idx) => {
        const val = Math.max(0, Math.min(1, Number(run.min_score ?? 1)));
        const x = ordered.length === 1 ? w / 2 : (pad + idx * step);
        const y = pad + (1 - val) * (h - pad * 2);
        return [x.toFixed(1), y.toFixed(1), val];
      });
      const poly = pts.map(([x, y]) => x + "," + y).join(" ");
      const dots = pts.map(([x, y, val]) => {
        const fill = val < 1.0 ? "#ef4444" : "#22c55e";
        return '<circle cx="' + x + '" cy="' + y + '" r="3.2" fill="' + fill + '" />';
      }).join("");
      const baselineY = pad.toFixed(1);
      sparkEl.innerHTML =
        '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + " " + h +
        '" role="img" aria-label="Eval min score trend">' +
        '<line x1="0" y1="' + baselineY + '" x2="' + w + '" y2="' + baselineY +
        '" stroke="#334155" stroke-dasharray="3,3" />' +
        (ordered.length > 1
          ? '<polyline fill="none" stroke="#38bdf8" stroke-width="2" points="' + poly + '" />'
          : "") +
        dots + "</svg>" +
        '<span class="muted">Min-score trend (last ' + ordered.length + " eval runs)</span>";

      const rows = evalHistory.slice(0, 8).map((r) => {
        const ok = Number(r.min_score ?? 1) >= 1.0;
        const pills = Object.entries(r.metrics || {}).map(
          ([k, v]) => '<span class="pill">' + esc(k.replace("/mean", "")) + "=" + esc(v) + "</span>"
        ).join("");
        return "<tr><td><code>" + esc(r.run_name || r.run_id) + "</code></td>" +
          "<td>" + badge(ok, "min=" + r.min_score, "min=" + r.min_score) + "</td>" +
          '<td><div class="pill-wrap">' + pills + "</div></td></tr>";
      }).join("");
      histBody.innerHTML =
        "<table><thead><tr><th>Eval Run</th><th>Min Score</th><th>Scorers</th></tr></thead>" +
        "<tbody>" + rows + "</tbody></table>";
    }

    function updateFacetSelect(id, values, label) {
      const sel = document.getElementById(id);
      const prev = sel.value;
      const opts = (values || [])
        .map((v) => '<option value="' + esc(v) + '">' + esc(v) + "</option>")
        .join("");
      sel.innerHTML = '<option value="">' + esc(label) + "</option>" + opts;
      sel.value = prev;
    }

    async function loadTraces() {
      const body = document.getElementById("traces-body");
      const evalEl = document.getElementById("eval-summary");
      const params = new URLSearchParams({ limit: "25" });
      const expSel = document.getElementById("tr-experiment-filter");
      const expName = expSel.value;
      const srv = document.getElementById("tr-server-filter").value;
      const usr = document.getElementById("tr-user-filter").value;
      const mdl = document.getElementById("tr-model-filter").value;
      const st = document.getElementById("tr-state-filter").value;
      const pr = document.getElementById("tr-refusal-filter").value;
      const q = document.getElementById("tr-search").value.trim();
      if (expName) params.set("experiment", expName);
      if (srv) params.set("server", srv);
      if (usr) params.set("user", usr);
      if (mdl) params.set("model_id", mdl);
      if (st) params.set("state", st);
      if (pr && pr !== "all") params.set("policy_refusal", pr);
      if (q) params.set("q", q);

      try {
        const data = await apiFetch("/api/v1/traces?" + params.toString());
        if (!data.available) {
          evalEl.textContent = "";
          document.getElementById("eval-sparkline").innerHTML = "";
          document.getElementById("eval-history-body").textContent = "";
          body.textContent = "MLflow unavailable: " + (data.error || "unknown error");
          return;
        }
        const exps = (data.experiments || []).map((e) => e.name);
        if (exps.length) {
          const defExpLabel = "Default (" + (data.experiment || "") + ")";
          updateFacetSelect("tr-experiment-filter", exps, defExpLabel);
          if (expName && exps.includes(expName)) expSel.value = expName;
        }
        const facets = data.facets || {};
        updateFacetSelect("tr-server-filter", facets.servers, "All Servers");
        updateFacetSelect("tr-user-filter", facets.users, "All Users");
        updateFacetSelect("tr-model-filter", facets.modelIds, "All LoggedModels");

        renderRegressionBanner(data.evalRegression);
        renderEvalSparkline(data.evalHistory || []);

        const latest = data.latestEvalRun;
        if (latest && latest.metrics) {
          const pills = Object.entries(latest.metrics).map(
            ([k, v]) => '<span class="pill">' + esc(k) + "=" + esc(v) + "</span>"
          ).join("");
          const expIdPart = encodeURIComponent(String(data.experimentId || "0"));
          const runUrl = "http://localhost:5002/#/experiments/" + expIdPart +
            "/runs/" + encodeURIComponent(latest.run_id);
          evalEl.innerHTML =
            '<div class="pill-wrap"><strong>Latest Eval Run</strong> ' +
            '<a href="' + runUrl + '" target="_blank" rel="noopener"><code>' +
            esc(latest.run_id) + "</code></a>" + pills + "</div>";
        } else {
          evalEl.textContent =
            "Experiment: " + (data.experiment || "n/a") + " (no eval metrics logged yet)";
        }

        const traces = data.traces || [];
        if (!traces.length) {
          body.textContent = "No matching MLflow traces.";
          return;
        }
        const rows = traces.map((tr) => {
          const stPill = tr.policyRefusal
            ? '<span class="pill warn">policy_refusal</span>'
            : badge(String(tr.state).includes("OK"), "OK", tr.state);
          const srvTool = tr.server ? (tr.server + "." + (tr.tool || "")) : (tr.name || "");
          return '<tr class="clickable" data-trace-id="' + esc(tr.traceId) + '">' +
            "<td><code>" + esc(tr.traceId) + "</code></td>" +
            "<td><code>" + esc(srvTool) + "</code></td>" +
            "<td>" + esc(tr.user || "-") + "</td>" +
            "<td><code>" + esc(tr.modelId ? tr.modelId.slice(0, 12) : "-") + "</code></td>" +
            "<td>" + stPill + "</td><td>" + esc(tr.durationMs ?? "-") + " ms</td>" +
            '<td><button class="mini inspect-trace-btn" type="button">Spans</button></td></tr>';
        }).join("");
        body.innerHTML =
          "<table><thead><tr><th>Trace ID</th><th>Server / Tool</th><th>User</th>" +
          "<th>Model</th><th>Outcome</th><th>Duration</th><th>Inspect</th></tr></thead>" +
          "<tbody>" + rows + "</tbody></table>";
        body.querySelectorAll("tr.clickable").forEach((row) => {
          row.addEventListener("click", () => inspectTrace(row.dataset.traceId || ""));
        });
      } catch (err) {
        evalEl.textContent = "";
        document.getElementById("eval-sparkline").innerHTML = "";
        document.getElementById("eval-history-body").textContent = "";
        body.textContent = err.status === 401
          ? "Sign in to view /api/v1/traces."
          : err.message;
      }
    }

    async function previewPrompt(name, versionOrAlias) {
      const box = document.getElementById("prompt-preview-box");
      box.style.display = "block";
      box.textContent = "Loading prompt " + name + "@" + versionOrAlias + "...";
      box.scrollIntoView({ behavior: "smooth", block: "nearest" });
      try {
        const data = await apiFetch(
          "/api/v1/mlflow/prompts/" + encodeURIComponent(name) +
          "?version_or_alias=" + encodeURIComponent(String(versionOrAlias))
        );
        const mlPromptUrl = "http://localhost:5002/#/prompts/" + encodeURIComponent(data.name);
        box.innerHTML =
          '<div class="kv"><div><strong>Prompt:</strong> ' +
          '<a href="' + mlPromptUrl + '" target="_blank" rel="noopener"><code>' +
          esc(data.name) + "</code></a> <span class='pill'>v" + esc(data.version) +
          '</span></div><button id="close-prompt-btn" class="mini" type="button">' +
          "Close</button></div>" +
          (data.commitMessage ? '<div class="muted">' + esc(data.commitMessage) + "</div>" : "") +
          "<pre style='margin-top:8px;'>" + esc(data.template || "") + "</pre>";
        document.getElementById("close-prompt-btn").addEventListener("click", () => {
          box.style.display = "none";
        });
      } catch (err) {
        box.textContent = "Failed to load prompt: " + err.message;
      }
    }

    async function promoteAlias(kind, name, version, statusEl) {
      statusEl.textContent = "Setting @production on " + name + "...";
      try {
        const res = await apiFetch(
          "/api/v1/mlflow/" + kind + "/" + encodeURIComponent(name) + "/alias",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ alias: "production", version }),
          }
        );
        statusEl.textContent = "Updated " + res.name + "@" + res.alias + " -> v" + res.version;
        await loadRegistry();
      } catch (err) {
        statusEl.textContent = "Alias update failed: " + err.message;
      }
    }

    async function loadRegistry() {
      const statusEl = document.getElementById("reg-status");
      const mutPill = document.getElementById("reg-mutations-pill");
      const mcpBox = document.getElementById("reg-mcp-servers");
      const prBox = document.getElementById("reg-prompts");
      const lmBox = document.getElementById("reg-logged-models");
      const rmBox = document.getElementById("reg-models");
      try {
        const data = await apiFetch("/api/v1/mlflow/registry");
        const mutEnabled = Boolean(data.mutationsEnabled);
        mutPill.textContent = mutEnabled ? "mutations enabled" : "read-only";
        mutPill.className = "pill " + (mutEnabled ? "ok" : "warn");
        if (!data.available) {
          statusEl.textContent = "MLflow registry unavailable: " + (data.error || "unknown error");
          return;
        }
        statusEl.textContent = "Experiment: " + (data.experiment || "n/a");

        const srvs = data.mcpServers || [];
        document.getElementById("reg-srv-count").textContent = srvs.length;
        mcpBox.innerHTML = srvs.length
          ? "<table><thead><tr><th>Name</th><th>Aliases &amp; Tags</th></tr></thead><tbody>" +
            srvs.map((s) => {
              const aliases = Object.entries(s.aliases || {}).map(
                ([a, v]) => '<span class="pill ok">@' + esc(a) + "=" + esc(v) + "</span>"
              ).join(" ");
              const tags = Object.entries(s.tags || {}).map(
                ([k, v]) => '<span class="pill">' + esc(k) + "=" + esc(v) + "</span>"
              ).join(" ");
              return "<tr><td><code>" + esc(s.name) + "</code><div class='muted'>" +
                esc(s.url || "") + "</div></td><td><div class='pill-wrap'>" +
                aliases + " " + tags + "</div></td></tr>";
            }).join("") + "</tbody></table>"
          : "No registered MCP servers.";

        const prompts = data.prompts || [];
        document.getElementById("reg-prompt-count").textContent = prompts.length;
        prBox.innerHTML = prompts.length
          ? "<table><thead><tr><th>Prompt</th><th>Latest</th><th>Actions</th></tr></thead><tbody>" +
            prompts.map((p) => {
              const latestVer = (p.versions && p.versions[0]) ? p.versions[0].version : "latest";
              const aliases = (p.versions || []).flatMap((v) => v.aliases || []).map(
                (a) => '<span class="pill ok">@' + esc(a) + "</span>"
              ).join(" ");
              const verLabel = latestVer === "latest" ? "latest" : ("v" + esc(latestVer));
              return "<tr><td><code>" + esc(p.name) + "</code> " + aliases + "</td>" +
                "<td>" + verLabel + "</td>" +
                "<td><button class='mini view-prompt-btn' data-name='" + esc(p.name) +
                "' data-ver='" + esc(latestVer) + "' type='button'>View</button> " +
                (mutEnabled && latestVer !== "latest"
                  ? "<button class='mini promote-prompt-btn' data-name='" + esc(p.name) +
                    "' data-ver='" + esc(latestVer) + "' type='button'>@production</button>"
                  : "") +
                "</td></tr>";
            }).join("") + "</tbody></table>"
          : "No prompts registered in MLflow.";

        prBox.querySelectorAll(".view-prompt-btn").forEach((btn) => {
          btn.addEventListener("click", () => previewPrompt(btn.dataset.name, btn.dataset.ver));
        });
        prBox.querySelectorAll(".promote-prompt-btn").forEach((btn) => {
          btn.addEventListener("click", () => promoteAlias(
            "prompts", btn.dataset.name, Number(btn.dataset.ver), statusEl
          ));
        });

        const lms = data.loggedModels || [];
        document.getElementById("reg-lm-count").textContent = lms.length;
        lmBox.innerHTML = lms.length
          ? "<table><thead><tr><th>Model</th><th>ID / SHA</th></tr></thead><tbody>" +
            lms.map((m) => (
              "<tr><td><code>" + esc(m.name) + "</code></td><td><code>" +
              esc(m.modelId) + "</code> <span class='pill'>" +
              esc((m.tags || {}).git_sha || "-") + "</span></td></tr>"
            )).join("") + "</tbody></table>"
          : "No LoggedModels in experiment yet.";

        const rms = data.registeredModels || [];
        document.getElementById("reg-rm-count").textContent = rms.length;
        rmBox.innerHTML = rms.length
          ? "<table><thead><tr><th>Model</th><th>Aliases</th><th>Action</th></tr></thead><tbody>" +
            rms.map((m) => {
              const latestVer = (m.latestVersions && m.latestVersions[0])
                ? m.latestVersions[0].version
                : "";
              const aliases = Object.entries(m.aliases || {}).map(
                ([a, v]) => '<span class="pill ok">@' + esc(a) + "=v" + esc(v) + "</span>"
              ).join(" ");
              return "<tr><td><code>" + esc(m.name) + "</code></td><td>" +
                (aliases || "-") + "</td><td>" +
                (mutEnabled && latestVer
                  ? "<button class='mini promote-rm-btn' data-name='" + esc(m.name) +
                    "' data-ver='" + esc(latestVer) + "' type='button'>@production</button>"
                  : "") +
                "</td></tr>";
            }).join("") + "</tbody></table>"
          : "No Registered Models in tracking registry.";

        rmBox.querySelectorAll(".promote-rm-btn").forEach((btn) => {
          btn.addEventListener("click", () => promoteAlias(
            "models", btn.dataset.name, btn.dataset.ver, statusEl
          ));
        });
      } catch (err) {
        statusEl.textContent = err.status === 401
          ? "Sign in to load MLflow Registry."
          : err.message;
        mcpBox.textContent = "";
        prBox.textContent = "";
        lmBox.textContent = "";
        rmBox.textContent = "";
      }
    }

    async function runAction(path, payload, btn) {
      const outEl = document.getElementById("action-output");
      const statusEl = document.getElementById("action-status");
      if (btn) btn.disabled = true;
      actionBusy = true;
      statusEl.textContent = "Running " + path + "...";
      try {
        const res = await apiFetch(path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload || {}),
        });
        statusEl.textContent = "Done.";
        outEl.style.display = "block";
        outEl.textContent = JSON.stringify(res, null, 2);
        await Promise.all([loadWatchdog(), loadTools(), loadTraces(), loadRegistry()]);
      } catch (err) {
        statusEl.textContent = "Failed: " + err.message;
        outEl.style.display = "block";
        outEl.textContent = err.message;
      } finally {
        actionBusy = false;
        if (btn) btn.disabled = false;
      }
    }

    async function refreshAll() {
      await Promise.all([loadSessionMe(), loadHealthAndReady()]);
      await Promise.all([
        loadProfileSnippets(),
        loadWatchdog(),
        loadTools(),
        loadTraces(),
        loadRegistry(),
      ]);
    }

    function updateAutoRefresh(ms) {
      if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
      }
      if (ms > 0) {
        refreshTimer = setInterval(() => {
          if (!actionBusy) refreshAll();
        }, ms);
      }
    }

    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });
    document.getElementById("login-btn").addEventListener("click", async () => {
      const input = document.getElementById("token-input");
      const token = input.value.trim();
      if (!token) return;
      try {
        await apiFetch("/api/v1/auth/session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        input.value = "";
        await refreshAll();
      } catch (err) {
        const b = document.getElementById("auth-error-banner");
        document.getElementById("auth-error-text").textContent = "Sign-in failed: " + err.message;
        b.style.display = "flex";
      }
    });
    document.getElementById("logout-btn").addEventListener("click", async () => {
      await apiFetch("/api/v1/auth/logout", { method: "POST" });
      await refreshAll();
    });
    document.getElementById("auth-error-close").addEventListener("click", () => {
      document.getElementById("auth-error-banner").style.display = "none";
    });
    document.getElementById("refresh-btn").addEventListener("click", refreshAll);
    document.getElementById("reg-refresh-btn").addEventListener("click", loadRegistry);
    document.getElementById("auto-refresh-select").addEventListener(
      "change", (e) => updateAutoRefresh(Number(e.target.value))
    );
    document.getElementById("profile-filter").addEventListener("change", loadTools);
    document.getElementById("server-filter").addEventListener("change", loadTools);
    document.getElementById("tool-search").addEventListener("input", loadTools);
    document.getElementById("pg-run-btn").addEventListener("click", runPlaygroundTool);
    document.getElementById("pg-close-btn").addEventListener("click", () => {
      document.getElementById("playground-card").style.display = "none";
    });
    document.getElementById("tr-experiment-filter").addEventListener("change", loadTraces);
    document.getElementById("tr-apply-btn").addEventListener("click", loadTraces);
    document.getElementById("tr-reset-btn").addEventListener("click", () => {
      document.getElementById("tr-experiment-filter").value = "";
      document.getElementById("tr-server-filter").value = "";
      document.getElementById("tr-user-filter").value = "";
      document.getElementById("tr-model-filter").value = "";
      document.getElementById("tr-state-filter").value = "";
      document.getElementById("tr-refusal-filter").value = "all";
      document.getElementById("tr-search").value = "";
      loadTraces();
    });
    document.getElementById("banner-traces-btn").addEventListener("click", () => {
      switchTab("traces");
    });
    document.getElementById("banner-rebench-btn").addEventListener("click", (e) => {
      runAction("/api/v1/actions/benchmark", { with_llm_judge: false }, e.target);
    });
    document.getElementById("act-uc-btn").addEventListener(
      "click", (e) => runAction("/api/v1/actions/refresh-uc", {}, e.target)
    );
    document.getElementById("act-wd-btn").addEventListener(
      "click", (e) => runAction("/api/v1/actions/watchdog", { dry_run: true }, e.target)
    );
    document.getElementById("act-eval-btn").addEventListener(
      "click", (e) => runAction("/api/v1/actions/eval", { limit: 20 }, e.target)
    );
    document.getElementById("bench-btn").addEventListener("click", (e) => {
      const withJudge = document.getElementById("judge-toggle").checked;
      const model = document.getElementById("judge-model-input").value.trim() || null;
      runAction(
        "/api/v1/actions/benchmark",
        { with_llm_judge: withJudge, judge_model: withJudge ? model : null },
        e.target
      );
    });

    const queryParams = new URLSearchParams(window.location.search);
    if (queryParams.get("auth_error")) {
      document.getElementById("auth-error-text").textContent =
        "Login link invalid or expired. Run mcp-stack ui open to mint a fresh link.";
      document.getElementById("auth-error-banner").style.display = "flex";
      history.replaceState(null, "", window.location.pathname + window.location.hash);
    }
    if (window.location.hash) {
      switchTab(window.location.hash.slice(1));
    }
    refreshAll();
  </script>
</body>
</html>
"""


def render_dashboard_html(version: str) -> str:
    """Render the interactive Gateway Control Plane HTML served at GET /ui."""
    return _DASHBOARD_TEMPLATE.replace("__VERSION__", html.escape(version))
