"""Jupyter notebook and IPython kernel FastMCP server with sandboxed paths."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import nbformat
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.tracing import MLflowTracingMiddleware


def _require_execution(settings: MCPStackSettings) -> None:
    if not settings.jupyter.allow_execution:
        raise ToolError(
            "Jupyter execution/writes are disabled by policy. "
            "Set JUPYTER_ALLOW_EXECUTION=true to enable notebook edits and kernel execution."
        )


def _resolve_notebook_path(settings: MCPStackSettings, path: str) -> Path:
    roots = (
        [settings.jupyter.notebook_dir.resolve()]
        if settings.jupyter.notebook_dir is not None
        else [p.resolve() for p in settings.filesystem.allowed_paths]
    )
    raw_path = Path(path)
    joined = raw_path if raw_path.is_absolute() else (roots[0] / raw_path)
    candidate = joined.resolve()
    if not any(candidate.is_relative_to(r) for r in roots):
        raise ToolError(f"Notebook path '{path}' escapes allowed roots")
    return candidate


def create_jupyter_server(
    settings: MCPStackSettings,
    *,
    kernel_factory: Callable[[], Any] | None = None,
) -> FastMCP:
    """Create the Jupyter notebook and kernel MCP server."""
    mcp = FastMCP("jupyter")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "jupyter"))

    kernels: dict[str, dict[str, Any]] = {}

    def _start_kernel(kernel_name: str = "python3") -> tuple[str, Any, Any]:
        kid = str(uuid.uuid4())[:8]
        if kernel_factory is not None:
            km, kc = kernel_factory()
        else:
            from jupyter_client import KernelManager

            km = KernelManager(kernel_name=kernel_name)
            km.start_kernel()
            kc = km.client()
            kc.start_channels()
            kc.wait_for_ready(timeout=settings.jupyter.kernel_timeout_seconds)
        kernels[kid] = {"km": km, "kc": kc, "kernel_name": kernel_name, "vars": {}}
        return kid, km, kc

    def _run_code(kc: Any, code: str) -> dict[str, Any]:
        msg_id = kc.execute(code)
        outputs: list[dict[str, Any]] = []
        deadline = settings.jupyter.kernel_timeout_seconds
        while True:
            msg = kc.get_iopub_msg(timeout=deadline)
            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue
            mtype = msg.get("msg_type")
            content = msg.get("content", {})
            if mtype == "status" and content.get("execution_state") == "idle":
                break
            if mtype == "stream":
                outputs.append({"type": "stream", "text": content.get("text", "")})
            elif mtype in {"execute_result", "display_data"}:
                data = content.get("data", {})
                outputs.append({"type": mtype, "text": data.get("text/plain", "")})
            elif mtype == "error":
                outputs.append(
                    {
                        "type": "error",
                        "ename": content.get("ename"),
                        "evalue": content.get("evalue"),
                    }
                )
        return {"outputs": outputs}

    @mcp.tool()
    async def jupyter_create_notebook(
        path: str,
        cells: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Create a new .ipynb notebook inside the allowed notebook directory."""
        _require_execution(settings)
        dest = _resolve_notebook_path(settings, path)
        nb = nbformat.v4.new_notebook()
        for cell in cells or []:
            ctype = cell.get("type", "code")
            src = cell.get("source", "")
            nb.cells.append(
                nbformat.v4.new_markdown_cell(src)
                if ctype == "markdown"
                else nbformat.v4.new_code_cell(src)
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(nbformat.write, nb, str(dest))
        return {"path": str(dest), "cells": len(nb.cells)}

    @mcp.tool()
    async def jupyter_open_notebook(path: str) -> dict[str, Any]:
        """Read cells and metadata from an .ipynb notebook."""
        src_path = _resolve_notebook_path(settings, path)
        if not src_path.exists():
            raise ToolError(f"Notebook not found: {src_path}")
        nb = await asyncio.to_thread(nbformat.read, str(src_path), as_version=4)
        return {
            "path": str(src_path),
            "cells": [
                {"index": i, "type": c.cell_type, "source": c.source}
                for i, c in enumerate(nb.cells)
            ],
        }

    @mcp.tool()
    async def jupyter_execute_cell(
        code: str,
        kernel_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a Python snippet on a Jupyter kernel (starts one if omitted)."""
        _require_execution(settings)

        def _exec() -> dict[str, Any]:
            if kernel_id and kernel_id in kernels:
                kid = kernel_id
                kc = kernels[kid]["kc"]
            else:
                kid, _km, kc = _start_kernel()
            res = _run_code(kc, code)
            return {"kernelId": kid, **res}

        return await asyncio.to_thread(_exec)

    @mcp.tool()
    async def jupyter_execute_notebook(path: str) -> dict[str, Any]:
        """Execute every code cell in a notebook sequentially and save outputs."""
        _require_execution(settings)
        nb_path = _resolve_notebook_path(settings, path)
        if not nb_path.exists():
            raise ToolError(f"Notebook not found: {nb_path}")

        def _exec() -> dict[str, Any]:
            nb = nbformat.read(str(nb_path), as_version=4)
            kid, _km, kc = _start_kernel()
            executed = 0
            for cell in nb.cells:
                if cell.cell_type == "code":
                    res = _run_code(kc, cell.source)
                    cell["outputs"] = [
                        nbformat.v4.new_output(
                            output_type="stream", name="stdout", text=str(o.get("text", ""))
                        )
                        for o in res["outputs"]
                        if o.get("type") in {"stream", "execute_result"}
                    ]
                    executed += 1
            nbformat.write(nb, str(nb_path))
            return {"path": str(nb_path), "kernelId": kid, "executedCells": executed}

        return await asyncio.to_thread(_exec)

    @mcp.tool()
    async def jupyter_get_variable(kernel_id: str, variable_name: str) -> dict[str, Any]:
        """Inspect a variable's JSON/repr value inside a running kernel session."""
        if kernel_id not in kernels:
            raise ToolError(f"Unknown kernelId '{kernel_id}'")
        if not variable_name.isidentifier():
            raise ToolError(f"Invalid variable name '{variable_name}'")
        kc = kernels[kernel_id]["kc"]
        res = await asyncio.to_thread(
            _run_code,
            kc,
            f"import json; print(json.dumps({variable_name}, default=repr))",
        )
        return {"kernelId": kernel_id, "variable": variable_name, **res}

    @mcp.tool()
    async def jupyter_plot(
        kernel_id: str,
        plot_type: Literal["line", "scatter", "bar", "hist", "box"],
        x_var: str,
        y_var: str | None = None,
        title: str = "",
    ) -> dict[str, Any]:
        """Render a matplotlib plot on an active Jupyter kernel."""
        _require_execution(settings)
        if kernel_id not in kernels:
            raise ToolError(f"Unknown kernelId '{kernel_id}'")
        for var in (x_var, *( [y_var] if y_var else [] )):
            if not var.isidentifier():
                raise ToolError(f"Invalid variable identifier '{var}'")
        if plot_type == "hist":
            call = f"plt.hist({x_var})"
        elif plot_type == "box":
            call = f"plt.boxplot({x_var})"
        elif y_var:
            fn = "plot" if plot_type == "line" else plot_type
            call = f"plt.{fn}({x_var}, {y_var})"
        else:
            call = f"plt.plot({x_var})"
        snippet = (
            "import matplotlib.pyplot as plt\n"
            f"plt.figure()\n{call}\nplt.title({title!r})\nprint('plot_rendered')"
        )
        res = await asyncio.to_thread(_run_code, kernels[kernel_id]["kc"], snippet)
        return {"kernelId": kernel_id, "plotType": plot_type, **res}

    @mcp.tool()
    async def jupyter_list_kernels() -> dict[str, Any]:
        """List available Jupyter kernel specs and active managed kernels."""
        def _run() -> dict[str, Any]:
            from jupyter_client.kernelspec import find_kernel_specs

            specs = sorted(find_kernel_specs().keys())
            return {
                "availableSpecs": specs,
                "active": [
                    {"kernelId": k, "kernelName": v["kernel_name"]} for k, v in kernels.items()
                ],
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def jupyter_kernel_control(
        kernel_id: str,
        action: Literal["interrupt", "restart", "shutdown"],
    ) -> dict[str, Any]:
        """Interrupt, restart, or shut down a managed Jupyter kernel."""
        _require_execution(settings)
        if kernel_id not in kernels:
            raise ToolError(f"Unknown kernelId '{kernel_id}'")

        def _ctrl() -> None:
            entry = kernels[kernel_id]
            km, kc = entry["km"], entry["kc"]
            if action == "interrupt":
                km.interrupt_kernel()
            elif action == "restart":
                km.restart_kernel(now=True)
            else:
                kc.stop_channels()
                km.shutdown_kernel(now=True)
                kernels.pop(kernel_id, None)

        await asyncio.to_thread(_ctrl)
        return {"kernelId": kernel_id, "action": action, "ok": True}

    @mcp.tool()
    async def jupyter_save_notebook(
        path: str,
        cells: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Write/update notebook cell contents on disk."""
        _require_execution(settings)
        dest = _resolve_notebook_path(settings, path)
        nb = nbformat.v4.new_notebook()
        for cell in cells:
            src = str(cell.get("source", ""))
            nb.cells.append(
                nbformat.v4.new_markdown_cell(src)
                if cell.get("type") == "markdown"
                else nbformat.v4.new_code_cell(src)
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(nbformat.write, nb, str(dest))
        return {"path": str(dest), "saved": True, "cells": len(nb.cells)}

    @mcp.tool()
    async def jupyter_list_sessions() -> dict[str, Any]:
        """List active managed Jupyter notebook/kernel sessions."""
        return {
            "sessions": [
                {"kernelId": kid, "kernelName": data["kernel_name"]}
                for kid, data in kernels.items()
            ]
        }

    @mcp.tool()
    async def jupyter_export(
        path: str,
        format: Literal["python", "markdown", "json"] = "markdown",
    ) -> dict[str, Any]:
        """Export an .ipynb notebook to Python, Markdown, or JSON text."""
        src_path = _resolve_notebook_path(settings, path)
        if not src_path.exists():
            raise ToolError(f"Notebook not found: {src_path}")
        nb = await asyncio.to_thread(nbformat.read, str(src_path), as_version=4)
        if format == "json":
            rendered = json.dumps(nbformat.writes(nb))
        elif format == "python":
            rendered = "\n\n".join(
                c.source if c.cell_type == "code" else f"# {c.source}" for c in nb.cells
            )
        else:
            rendered = "\n\n".join(
                f"```python\n{c.source}\n```" if c.cell_type == "code" else c.source
                for c in nb.cells
            )
        return {
            "path": str(src_path),
            "format": format,
            "content": rendered[: settings.jupyter.max_output_chars],
        }

    return mcp
