"""Control Plane SPA static asset loader and unbuilt fallback renderer."""

from __future__ import annotations

import html
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static"

_UNBUILT_FALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MCP Workshop Stack Control Plane</title>
  <style>
    :root { color-scheme: dark; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
      background: #0a0b0e;
      color: #ededef;
    }
    .panel {
      max-width: 560px;
      width: 100%;
      background: #111318;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 12px;
      padding: 24px;
    }
    h1 { margin: 0 0 8px; font-size: 1.1rem; }
    p { margin: 8px 0; color: #8a8f98; font-size: 0.92rem; line-height: 1.5; }
    pre {
      margin: 14px 0 0;
      padding: 12px;
      background: #0a0b0e;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 8px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.84rem;
      overflow-x: auto;
    }
  </style>
</head>
<body>
  <main class="panel">
    <h1>MCP Workshop Stack Gateway &middot; v__VERSION__</h1>
    <p>Control Plane frontend assets have not been built into
    <code>src/mcp_stack/gateway/static</code> yet.</p>
    <p>Build the React workbench with:</p>
    <pre>pnpm --dir web install && pnpm --dir web build
# or
mcp-stack ui build --install</pre>
  </main>
</body>
</html>
"""


def get_static_dir(static_dir: Path | None = None) -> Path:
    """Return the built SPA asset directory."""
    return static_dir or STATIC_DIR


def has_built_dashboard(static_dir: Path | None = None) -> bool:
    """Return True when the compiled Vite index.html is present."""
    return (get_static_dir(static_dir) / "index.html").is_file()


def render_dashboard_html(version: str, static_dir: Path | None = None) -> str:
    """Load the compiled Vite Control Plane HTML or render build instructions if unbuilt."""
    safe_ver = html.escape(version, quote=True)
    index_path = get_static_dir(static_dir) / "index.html"
    if index_path.is_file():
        return index_path.read_text(encoding="utf-8").replace("__VERSION__", safe_ver)
    return _UNBUILT_FALLBACK_HTML.replace("__VERSION__", safe_ver)
