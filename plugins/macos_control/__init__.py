"""macos-control — MCP server for macOS window/screenshot/input automation.

Tool logic lives in `tools.py` (pure, testable, shells out to osascript /
screencapture). The MCP server wiring is in `server.py` (lazy-imports the
`mcp` SDK so `tools` can be imported and tested without it).
"""
