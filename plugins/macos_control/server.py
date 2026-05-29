"""MCP server exposing macos-control tools.

Thin wrappers over tools.py so the MCP tool signatures don't leak the internal
`runner` parameter. The `mcp` SDK is imported lazily inside main() so tools.py
stays importable (and testable) without it.
"""

from __future__ import annotations

from typing import Any

from . import tools


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("macos-control")

    @server.tool()
    def list_windows() -> dict[str, Any]:
        """List all on-screen windows as {app, title}."""
        return tools.list_windows()

    @server.tool()
    def focus_app(app_name: str) -> dict[str, Any]:
        """Bring the named application to the foreground."""
        return tools.focus_app(app_name)

    @server.tool()
    def focus_window(app_name: str, title_substring: str) -> dict[str, Any]:
        """Raise a window of app_name whose title contains title_substring."""
        return tools.focus_window(app_name, title_substring)

    @server.tool()
    def screenshot_full(path: str) -> dict[str, Any]:
        """Save a full-display screenshot to path."""
        return tools.screenshot_full(path)

    @server.tool()
    def screenshot_window(window_id: int, path: str) -> dict[str, Any]:
        """Save a single-window screenshot to path."""
        return tools.screenshot_window(window_id, path)

    @server.tool()
    def screenshot_region(x: int, y: int, w: int, h: int, path: str) -> dict[str, Any]:
        """Save a region screenshot to path."""
        return tools.screenshot_region(x, y, w, h, path)

    @server.tool()
    def type_text(text: str) -> dict[str, Any]:
        """Type text into the frontmost window."""
        return tools.type_text(text)

    @server.tool()
    def key_combo(combo: str) -> dict[str, Any]:
        """Send a key combination like 'cmd+c' (single-char key + modifiers)."""
        return tools.key_combo(combo)

    @server.tool()
    def run_applescript(script: str) -> dict[str, Any]:
        """Run raw AppleScript and return its stdout."""
        return tools.run_applescript(script)

    @server.tool()
    def notify(title: str, message: str) -> dict[str, Any]:
        """Post a macOS notification."""
        return tools.notify(title, message)

    server.run()


if __name__ == "__main__":
    main()
