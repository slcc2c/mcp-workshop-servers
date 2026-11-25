"""Self-contained zero-build HTML/CSS/JS dashboard for the MCP Workshop Stack Gateway."""

from __future__ import annotations

import html


def render_dashboard_html(version: str) -> str:
    """Render the interactive Gateway Web Dashboard served at GET /ui."""
    safe_ver = html.escape(version)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MCP Workshop Stack Dashboard</title>
  <style>
    :root {{
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
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--sans);
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(15, 23, 42, 0.94);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--border);
      padding: 14px 24px;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
    }}
    .brand {{ display: flex; align-items: center; gap: 10px; }}
    .brand h1 {{ margin: 0; font-size: 1.1rem; font-weight: 600; }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 600;
      background: var(--panel-alt);
      border: 1px solid var(--border);
    }}
    .pill.ok {{ color: var(--ok); border-color: rgba(34, 197, 94, 0.4); }}
    .pill.warn {{ color: var(--warn); border-color: rgba(245, 158, 11, 0.4); }}
    .pill.err {{ color: var(--err); border-color: rgba(239, 68, 68, 0.4); }}
    .auth-bar {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    input, select, textarea {{
      background: var(--panel);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 0.85rem;
    }}
    textarea {{
      width: 100%;
      font-family: var(--mono);
      font-size: 0.8rem;
      min-height: 110px;
      resize: vertical;
    }}
    button {{
      background: var(--panel-alt);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 0.85rem;
      cursor: pointer;
    }}
    button.mini {{ padding: 3px 8px; font-size: 0.76rem; }}
    button:hover {{ border-color: var(--accent); }}
    button.primary {{
      background: #0284c7;
      border-color: #0ea5e9;
      color: #fff;
      font-weight: 600;
    }}
    button:disabled {{ opacity: 0.55; cursor: not-allowed; }}
    main {{
      max-width: 1320px;
      margin: 0 auto;
      padding: 20px 24px 48px;
      display: grid;
      gap: 18px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
    }}
    .card h2 {{
      margin: 0 0 10px;
      font-size: 0.95rem;
      color: var(--accent);
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }}
    .muted {{ color: var(--muted); font-size: 0.84rem; }}
    code, pre {{ font-family: var(--mono); font-size: 0.8rem; }}
    pre {{
      background: #020617;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
      overflow-x: auto;
      max-height: 280px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.84rem; }}
    th, td {{
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-weight: 600; }}
    .toolbar, .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
      align-items: center;
    }}
    .drawer {{
      margin-top: 12px;
      padding: 12px;
      border-radius: 8px;
      background: #0f172a;
      border: 1px solid var(--border);
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .kv {{ display: flex; justify-content: space-between; align-items: center; padding: 4px 0; }}
    label.inline {{ display: inline-flex; align-items: center; gap: 6px; font-size: 0.82rem; }}
    tr.clickable {{ cursor: pointer; }}
    tr.clickable:hover {{ background: rgba(56, 189, 248, 0.08); }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>MCP Workshop Stack Gateway</h1>
      <span class="pill">v{safe_ver}</span>
      <span id="overall-pill" class="pill warn">Checking...</span>
    </div>
    <div class="auth-bar">
      <label class="inline muted" for="auto-refresh-select">Auto-refresh
        <select id="auto-refresh-select" aria-label="Auto refresh interval">
          <option value="0" selected>Off</option>
          <option value="15000">15s</option>
          <option value="60000">60s</option>
        </select>
      </label>
      <input
        id="token-input"
        type="password"
        placeholder="Bearer token (sessionStorage only)"
        aria-label="Bearer token"
      />
      <button id="save-token-btn" class="primary" type="button">Connect</button>
      <button id="clear-token-btn" type="button">Clear</button>
      <button id="refresh-btn" type="button">Refresh All</button>
    </div>
  </header>

  <main>
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
            Connect token to load client snippets...
          </div>
        </details>
      </div>
      <div class="card">
        <h2>Watchdog <span id="wd-pill" class="pill">--</span></h2>
        <div id="watchdog-box" class="muted">Connect token to load /api/v1/watchdog</div>
      </div>
    </section>

    <section class="card">
      <h2>Operational Actions (Bearer-Authenticated)</h2>
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
        <span>Tool Browser &amp; Playground <span id="tool-count" class="pill">0 tools</span></span>
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
        Connect token (if auth enabled) to browse live tools...
      </div>
    </section>

    <section class="card">
      <h2>
        <span>Recent MLflow Traces &amp; Latest Eval</span>
        <a href="http://localhost:5002" target="_blank" rel="noopener">
          Open MLflow UI (:5002) &rarr;
        </a>
      </h2>
      <div id="eval-summary" class="muted" style="margin-bottom:10px;"></div>
      <div id="traces-body" class="muted">
        Connect token (if auth enabled) to load MLflow traces...
      </div>
      <div id="trace-detail-box" class="drawer" style="display:none;"></div>
    </section>
  </main>

  <script>
    const TOKEN_KEY = "mcp_gateway_token";
    let loadedTools = [];
    let profileCountsCache = {{}};
    let healthProfiles = [];
    let healthServersCount = 0;
    let refreshTimer = null;
    let actionBusy = false;

    const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (ch) => ({{
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }}[ch]));

    function getToken() {{
      return sessionStorage.getItem(TOKEN_KEY) || "";
    }}

    async function apiFetch(path, options = {{}}) {{
      const headers = new Headers(options.headers || {{}});
      const tok = getToken();
      if (tok) headers.set("Authorization", "Bearer " + tok);
      const res = await fetch(path, {{ ...options, headers }});
      const text = await res.text();
      let json = null;
      try {{ json = JSON.parse(text); }} catch {{}}
      if (!res.ok) {{
        const msg = json?.error?.message || json?.error || ("HTTP " + res.status);
        const err = new Error(msg);
        err.status = res.status;
        throw err;
      }}
      return json;
    }}

    function badge(ok, okLabel = "healthy", failLabel = "degraded") {{
      const cls = ok ? "ok" : "err";
      return '<span class="pill ' + cls + '">' + esc(ok ? okLabel : failLabel) + "</span>";
    }}

    function copyText(text, btn) {{
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(text).then(() => {{
          const orig = btn.textContent;
          btn.textContent = "Copied";
          setTimeout(() => {{ btn.textContent = orig; }}, 1200);
        }});
      }}
    }}

    function renderProfileRows() {{
      const origin = window.location.origin;
      const box = document.getElementById("profiles-box");
      if (!healthProfiles.length) return;
      box.innerHTML = healthProfiles.map((p) => {{
        const cnt = profileCountsCache[p.name];
        const countTag = typeof cnt === "number" ? " (" + cnt + " tools)" : "";
        const fullUrl = origin + p.route;
        return '<div class="kv"><code>' + esc(p.route) + '</code>' +
          '<span><span class="muted">' + esc((p.servers || []).length) +
          ' srv' + esc(countTag) + '</span> ' +
          '<button class="mini copy-url-btn" data-url="' + esc(fullUrl) +
          '" type="button">Copy URL</button></span></div>';
      }}).join("") + '<div class="kv"><code>/mcp</code>' +
        '<span><span class="muted">' + esc(healthServersCount) +
        ' total mounted</span> <button class="mini copy-url-btn" data-url="' +
        esc(origin + "/mcp") + '" type="button">Copy URL</button></span></div>';

      box.querySelectorAll(".copy-url-btn").forEach((btn) => {{
        btn.addEventListener("click", () => copyText(btn.dataset.url || "", btn));
      }});
    }}

    function seedArgsFromSchema(schema) {{
      const props = (schema && schema.properties) || {{}};
      const req = new Set((schema && schema.required) || []);
      const out = {{}};
      for (const [k, spec] of Object.entries(props)) {{
        if (!req.has(k)) continue;
        const tp = spec && spec.type;
        if (spec && spec.default !== undefined) out[k] = spec.default;
        else if (tp === "integer" || tp === "number") out[k] = 0;
        else if (tp === "boolean") out[k] = false;
        else if (tp === "array") out[k] = [];
        else if (tp === "object") out[k] = {{}};
        else out[k] = "";
      }}
      return JSON.stringify(out, null, 2);
    }}

    function openPlayground(idx) {{
      const tool = loadedTools[idx];
      if (!tool) return;
      document.getElementById("pg-server").textContent = tool.server;
      document.getElementById("pg-tool").textContent = tool.name;
      document.getElementById("pg-args").value = seedArgsFromSchema(tool.parameters);
      document.getElementById("pg-latency").textContent = "ready";
      document.getElementById("pg-latency").className = "pill";
      document.getElementById("pg-status").textContent = "";
      document.getElementById("pg-output").style.display = "none";
      document.getElementById("playground-card").style.display = "block";
    }}

    async function runPlaygroundTool() {{
      const server = document.getElementById("pg-server").textContent;
      const tool = document.getElementById("pg-tool").textContent;
      const rawArgs = document.getElementById("pg-args").value.trim() || "{{}}";
      const statusEl = document.getElementById("pg-status");
      const latEl = document.getElementById("pg-latency");
      const outEl = document.getElementById("pg-output");
      const runBtn = document.getElementById("pg-run-btn");

      let parsedArgs;
      try {{
        parsedArgs = JSON.parse(rawArgs);
      }} catch (err) {{
        statusEl.textContent = "Invalid JSON: " + err.message;
        return;
      }}

      runBtn.disabled = true;
      actionBusy = true;
      statusEl.textContent = "Invoking...";
      try {{
        const res = await apiFetch("/api/v1/actions/call-tool", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ server, tool, arguments: parsedArgs }}),
        }});
        latEl.textContent = (res.durationMs ?? "-") + " ms";
        if (res.ok) {{
          latEl.className = "pill ok";
          statusEl.textContent = res.truncated ? "OK (truncated)" : "OK";
        }} else if (res.policyRefusal) {{
          latEl.className = "pill warn";
          statusEl.textContent = "Policy Refusal";
        }} else {{
          latEl.className = "pill err";
          statusEl.textContent = "Error";
        }}
        outEl.style.display = "block";
        outEl.textContent = JSON.stringify(res, null, 2);
        await loadTraces();
      }} catch (err) {{
        latEl.className = "pill err";
        latEl.textContent = "failed";
        statusEl.textContent = err.message;
        outEl.style.display = "block";
        outEl.textContent = err.message;
      }} finally {{
        actionBusy = false;
        runBtn.disabled = false;
      }}
    }}

    async function loadHealthAndReady() {{
      const [health, ready] = await Promise.all([apiFetch("/health"), apiFetch("/ready")]);
      const pill = document.getElementById("overall-pill");
      const isReady = ready.status === "ready";
      pill.textContent = ready.status.toUpperCase();
      pill.className = "pill " + (isReady ? "ok" : "warn");

      const checks = ready.checks || {{}};
      document.getElementById("ready-checks").innerHTML =
        Object.entries(checks).map(([k, v]) => {{
          const ok = Boolean(v.healthy ?? v.reachable);
          return '<div class="kv"><code>' + esc(k) + "</code>" +
            badge(ok, "ok", "down") + "</div>";
        }}).join("");

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
        (s) => '<option value="' + esc(s.slug) + '">' + esc(s.slug) + "</option>"
      ).join("");
      srvSel.value = prevSrv;

      renderProfileRows();
    }}

    async function loadProfileSnippets() {{
      const box = document.getElementById("snippets-box");
      try {{
        const data = await apiFetch("/api/v1/profiles");
        const snippets = data.clientSnippets || {{}};
        const entries = Object.entries(snippets).filter(
          ([k]) => k === "codex" || k === "claude-code" || k === "cursor"
        );
        if (!entries.length) {{
          box.textContent = "No client snippets available.";
          return;
        }}
        box.innerHTML = entries.map(([name, body]) => (
          '<div style="margin-bottom:8px;">' +
          '<div class="kv"><strong>' + esc(name) + '</strong>' +
          '<button class="mini copy-snip-btn" data-name="' + esc(name) +
          '" type="button">Copy</button></div>' +
          '<pre style="max-height:140px;">' + esc(body) + '</pre></div>'
        )).join("");
        box.querySelectorAll(".copy-snip-btn").forEach((btn) => {{
          btn.addEventListener("click", () => {{
            copyText(snippets[btn.dataset.name] || "", btn);
          }});
        }});
      }} catch (err) {{
        box.textContent = err.status === 401
          ? "Enter Bearer token to view client config snippets."
          : err.message;
      }}
    }}

    async function loadWatchdog() {{
      const box = document.getElementById("watchdog-box");
      const wdPill = document.getElementById("wd-pill");
      try {{
        const data = await apiFetch("/api/v1/watchdog");
        const comps = data.components || {{}};
        const entries = Object.entries(comps);
        const allOk = entries.length > 0 && entries.every(([, v]) => Boolean(v.healthy));
        wdPill.textContent = entries.length ? (allOk ? "healthy" : "degraded") : "no state";
        wdPill.className = "pill " + (allOk ? "ok" : "warn");
        if (!entries.length) {{
          box.textContent = "No watchdog state file found yet.";
          return;
        }}
        box.innerHTML = entries.map(([name, info]) => (
          '<div class="kv"><code>' + esc(name) + "</code><span>" +
          badge(Boolean(info.healthy), "ok", "unhealthy") + "</span></div>"
        )).join("") + '<div class="muted" style="margin-top:6px;">Last check: ' +
          esc(data.lastRunAt || "n/a") + "</div>";
      }} catch (err) {{
        wdPill.textContent = err.status === 401 ? "locked" : "error";
        wdPill.className = "pill warn";
        box.textContent = err.status === 401
          ? "Enter Bearer token to view watchdog state."
          : err.message;
      }}
    }}

    async function loadTools() {{
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
      try {{
        const data = await apiFetch("/api/v1/tools" + qs);
        loadedTools = data.tools || [];
        profileCountsCache = data.profileCounts || {{}};
        renderProfileRows();
        countEl.textContent = loadedTools.length + " tools";
        if (!loadedTools.length) {{
          body.textContent = "No matching tools.";
          return;
        }}
        const rows = loadedTools.slice(0, 150).map((t, idx) => (
          "<tr><td><code>" + esc(t.name) + "</code>" +
          '<div style="margin-top:4px;"><button class="mini try-tool-btn" data-idx="' + idx +
          '" type="button">Try Tool</button></div></td>' +
          "<td><span class='pill'>" + esc(t.server) + "</span></td>" +
          "<td>" + esc(t.description || "") +
          "<details style='margin-top:4px;'><summary class='muted'>schema</summary><pre>" +
          esc(JSON.stringify(t.parameters || {{}}, null, 2)) + "</pre></details></td></tr>"
        )).join("");
        body.innerHTML =
          "<table><thead><tr><th>Tool</th><th>Server</th>" +
          "<th>Description &amp; Schema</th></tr></thead><tbody>" + rows + "</tbody></table>";
        body.querySelectorAll(".try-tool-btn").forEach((btn) => {{
          btn.addEventListener("click", () => openPlayground(Number(btn.dataset.idx)));
        }});
      }} catch (err) {{
        body.textContent = err.status === 401
          ? "Enter Bearer token to browse /api/v1/tools."
          : err.message;
      }}
    }}

    async function curateTrace(traceId, suffix, payload, statusEl) {{
      statusEl.textContent = "Saving...";
      try {{
        await apiFetch(
          "/api/v1/traces/" + encodeURIComponent(traceId) + suffix,
          {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify(payload || {{}}),
          }}
        );
        await inspectTrace(traceId);
      }} catch (err) {{
        statusEl.textContent = "Failed: " + err.message;
      }}
    }}

    async function inspectTrace(traceId) {{
      const detailBox = document.getElementById("trace-detail-box");
      detailBox.style.display = "block";
      detailBox.textContent = "Loading spans for " + traceId + "...";
      try {{
        const tr = await apiFetch("/api/v1/traces/" + encodeURIComponent(traceId));
        const stPill = tr.policyRefusal
          ? '<span class="pill warn">policy_refusal</span>'
          : badge(String(tr.state).includes("OK"), "OK", tr.state);
        const spansHtml = (tr.spans || []).map((sp) => (
          '<div style="margin-top:8px; padding-top:8px; border-top:1px solid var(--border);">' +
          '<div class="kv"><code>' + esc(sp.name) + '</code>' +
          '<span class="muted">' + esc(sp.spanType) + " · " +
          esc(sp.durationMs ?? "-") + " ms</span></div>" +
          '<pre style="max-height:180px;">' +
          esc(JSON.stringify({{
            status: sp.status,
            inputs: sp.inputs,
            outputs: sp.outputs,
            events: sp.events,
          }}, null, 2)) + "</pre></div>"
        )).join("");
        const metaPills = [
          tr.user ? "user=" + tr.user : null,
          tr.sessionId ? "session=" + tr.sessionId : null,
          tr.modelId ? "model=" + tr.modelId : null,
        ].filter(Boolean).map((m) => '<span class="pill">' + esc(m) + "</span>").join(" ");
        const tagsHtml = Object.entries(tr.tags || {{}})
          .filter(([k]) => !k.startsWith("mlflow."))
          .map(([k, v]) => '<span class="pill">' + esc(k) + "=" + esc(v) + "</span>")
          .join(" ");
        const metaRow = (metaPills || tagsHtml)
          ? '<div style="margin-top:6px;">' + metaPills + " " + tagsHtml + "</div>"
          : "";
        const assessHtml = (tr.assessments || []).length
          ? '<div style="margin-top:8px;"><strong>Assessments:</strong> ' +
            tr.assessments.map((a) => (
              '<span class="pill">' + esc(a.name) + "=" + esc(a.value) + "</span>"
            )).join(" ") + "</div>"
          : "";
        const curationBar =
          '<div id="curation-bar" style="margin-top:10px; padding:8px; ' +
          'border:1px solid var(--border); border-radius:6px;">' +
          '<div class="toolbar" style="margin-bottom:6px;">' +
          '<input id="cur-rationale" type="text" placeholder="Feedback rationale..." ' +
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
        document.getElementById("close-trace-btn").addEventListener("click", () => {{
          detailBox.style.display = "none";
        }});
        document.getElementById("cur-yes").addEventListener("click", () => curateTrace(
          tr.traceId, "/feedback",
          {{ name: "human_quality", value: "yes",
             rationale: document.getElementById("cur-rationale").value.trim() || null }},
          curStatus
        ));
        document.getElementById("cur-no").addEventListener("click", () => curateTrace(
          tr.traceId, "/feedback",
          {{ name: "human_quality", value: "no",
             rationale: document.getElementById("cur-rationale").value.trim() || null }},
          curStatus
        ));
        document.getElementById("cur-log-exp").addEventListener("click", () => curateTrace(
          tr.traceId, "/expectation",
          {{ name: "expected_outcome", value: document.getElementById("cur-exp").value }},
          curStatus
        ));
        document.getElementById("cur-add-tag").addEventListener("click", () => curateTrace(
          tr.traceId, "/tag",
          {{ key: document.getElementById("cur-tag-k").value.trim(),
             value: document.getElementById("cur-tag-v").value.trim() }},
          curStatus
        ));
        document.getElementById("cur-promote").addEventListener("click", () => curateTrace(
          tr.traceId, "/promote-to-dataset",
          {{ expected_outcome: document.getElementById("cur-exp").value }},
          curStatus
        ));
      }} catch (err) {{
        detailBox.textContent = "Failed to load trace details: " + err.message;
      }}
    }}

    async function loadTraces() {{
      const body = document.getElementById("traces-body");
      const evalEl = document.getElementById("eval-summary");
      try {{
        const data = await apiFetch("/api/v1/traces?limit=15");
        if (!data.available) {{
          evalEl.textContent = "";
          body.textContent = "MLflow unavailable: " + (data.error || "unknown error");
          return;
        }}
        const latest = data.latestEvalRun;
        if (latest && latest.metrics) {{
          const pills = Object.entries(latest.metrics).map(
            ([k, v]) => '<span class="pill">' + esc(k) + "=" + esc(v) + "</span>"
          ).join(" ");
          evalEl.innerHTML =
            "<strong>Latest Eval Run</strong> <code>" +
            esc(latest.run_id) + "</code>: " + pills;
        }} else {{
          evalEl.textContent =
            "Experiment: " + (data.experiment || "n/a") + " (no eval metrics logged yet)";
        }}
        const traces = data.traces || [];
        if (!traces.length) {{
          body.textContent = "No recent MLflow traces in experiment.";
          return;
        }}
        const rows = traces.map((tr) => {{
          const st = tr.policyRefusal
            ? '<span class="pill warn">policy_refusal</span>'
            : badge(String(tr.state).includes("OK"), "OK", tr.state);
          return '<tr class="clickable" data-trace-id="' + esc(tr.traceId) + '">' +
            "<td><code>" + esc(tr.traceId) + "</code></td>" +
            "<td><code>" + esc(tr.name || "") + "</code></td><td>" + st +
            "</td><td>" + esc(tr.durationMs ?? "-") + " ms</td>" +
            '<td><button class="mini inspect-trace-btn" type="button">Spans</button></td></tr>';
        }}).join("");
        body.innerHTML =
          "<table><thead><tr><th>Trace ID</th><th>Span</th>" +
          "<th>Outcome</th><th>Duration</th><th>Inspect</th></tr></thead>" +
          "<tbody>" + rows + "</tbody></table>";
        body.querySelectorAll("tr.clickable").forEach((row) => {{
          row.addEventListener("click", () => inspectTrace(row.dataset.traceId || ""));
        }});
      }} catch (err) {{
        evalEl.textContent = "";
        body.textContent = err.status === 401
          ? "Enter Bearer token to view /api/v1/traces."
          : err.message;
      }}
    }}

    async function runAction(path, payload, btn) {{
      const outEl = document.getElementById("action-output");
      const statusEl = document.getElementById("action-status");
      btn.disabled = true;
      actionBusy = true;
      statusEl.textContent = "Running " + path + "...";
      try {{
        const res = await apiFetch(path, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload || {{}}),
        }});
        statusEl.textContent = "Done.";
        outEl.style.display = "block";
        outEl.textContent = JSON.stringify(res, null, 2);
        await Promise.all([loadWatchdog(), loadTools(), loadTraces()]);
      }} catch (err) {{
        statusEl.textContent = "Failed: " + err.message;
        outEl.style.display = "block";
        outEl.textContent = err.message;
      }} finally {{
        actionBusy = false;
        btn.disabled = false;
      }}
    }}

    async function refreshAll() {{
      await loadHealthAndReady();
      await Promise.all([
        loadProfileSnippets(),
        loadWatchdog(),
        loadTools(),
        loadTraces(),
      ]);
    }}

    function updateAutoRefresh(ms) {{
      if (refreshTimer) {{
        clearInterval(refreshTimer);
        refreshTimer = null;
      }}
      if (ms > 0) {{
        refreshTimer = setInterval(() => {{
          if (!actionBusy) refreshAll();
        }}, ms);
      }}
    }}

    document.getElementById("save-token-btn").addEventListener("click", () => {{
      const val = document.getElementById("token-input").value.trim();
      if (val) sessionStorage.setItem(TOKEN_KEY, val);
      refreshAll();
    }});
    document.getElementById("clear-token-btn").addEventListener("click", () => {{
      sessionStorage.removeItem(TOKEN_KEY);
      document.getElementById("token-input").value = "";
      refreshAll();
    }});
    document.getElementById("refresh-btn").addEventListener("click", refreshAll);
    document.getElementById("auto-refresh-select").addEventListener(
      "change", (e) => updateAutoRefresh(Number(e.target.value))
    );
    document.getElementById("profile-filter").addEventListener("change", loadTools);
    document.getElementById("server-filter").addEventListener("change", loadTools);
    document.getElementById("tool-search").addEventListener("input", loadTools);
    document.getElementById("pg-run-btn").addEventListener("click", runPlaygroundTool);
    document.getElementById("pg-close-btn").addEventListener("click", () => {{
      document.getElementById("playground-card").style.display = "none";
    }});
    document.getElementById("act-uc-btn").addEventListener(
      "click", (e) => runAction("/api/v1/actions/refresh-uc", {{}}, e.target)
    );
    document.getElementById("act-wd-btn").addEventListener(
      "click", (e) => runAction("/api/v1/actions/watchdog", {{ dry_run: true }}, e.target)
    );
    document.getElementById("act-eval-btn").addEventListener(
      "click", (e) => runAction("/api/v1/actions/eval", {{ limit: 20 }}, e.target)
    );
    document.getElementById("bench-btn").addEventListener("click", (e) => {{
      const withJudge = document.getElementById("judge-toggle").checked;
      const model = document.getElementById("judge-model-input").value.trim() || null;
      runAction(
        "/api/v1/actions/benchmark",
        {{ with_llm_judge: withJudge, judge_model: withJudge ? model : null }},
        e.target
      );
    }});

    if (getToken()) {{
      document.getElementById("token-input").value = getToken();
    }}
    refreshAll();
  </script>
</body>
</html>
"""
