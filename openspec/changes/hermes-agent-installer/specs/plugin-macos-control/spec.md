## ADDED Requirements

### Requirement: macOS control plugin is shipped as an MCP server
The repo SHALL contain `plugins/macos_control/` exposing an MCP server named `macos-control`, registered by the manifest. Its implementation MUST use only built-in macOS facilities (`osascript`, `screencapture`, `pbcopy`, `open`) — no third-party automation framework (no Hammerspoon, no Karabiner) as a hard dependency.

#### Scenario: Server registers on install
- **WHEN** `hermes install` finishes on macOS
- **THEN** `claude mcp list` shows `macos-control` as connected

### Requirement: Window/application focus tools
The server SHALL expose:
- `list_windows()`: returns `[{app, title, window_id}, …]` for all on-screen windows.
- `focus_app(app_name)`: brings the named application to the foreground (equivalent to `tell application "<name>" to activate`).
- `focus_window(window_id)`: brings a specific window to the foreground when possible (uses AppleScript window addressing).

#### Scenario: Focus switches the frontmost app
- **WHEN** Claude calls `focus_app("Safari")`
- **THEN** Safari becomes the frontmost application within 1 second
- **AND** the tool returns `{ok: true, previous_frontmost: "<app>"}`

### Requirement: Screenshot tools
The server SHALL expose:
- `screenshot_full(path)`: saves a full-display screenshot.
- `screenshot_window(window_id, path)`: saves a single-window screenshot (uses `screencapture -l <window_id>`).
- `screenshot_region(x, y, w, h, path)`: saves a region screenshot.

Each tool MUST return the file path and the file's size on success.

#### Scenario: Screenshot can be piped into Telegram
- **WHEN** Claude calls `screenshot_full("/tmp/s.png")` and then `tg_send_photo(chat_id, "/tmp/s.png")`
- **THEN** the recipient receives the screenshot of the current macOS screen

### Requirement: Input automation tools
The server SHALL expose:
- `type_text(text)`: types the given string into the frontmost window via AppleScript keystroke events.
- `key_combo(combo)`: sends a key combination like `cmd+tab`, `cmd+shift+4`.
- `run_applescript(script)`: executes raw AppleScript and returns its stdout.
- `notify(title, message)`: posts a macOS user notification.

#### Scenario: Notify posts a macOS notification
- **WHEN** Claude calls `notify("Hermes", "backup done")`
- **THEN** a macOS notification appears with that title and body

### Requirement: Plugin documents required system permissions
The plugin's `README.md` MUST list the macOS permissions it requires (Accessibility, Screen Recording, Automation for controlled apps) and the exact System Settings path to grant them. Tools MUST return a structured error when a call fails due to a missing permission rather than a generic exception.

#### Scenario: Missing Screen Recording permission returns a clear error
- **WHEN** `screenshot_full` is called but the host shell lacks Screen Recording permission
- **THEN** the tool returns `{ok: false, error: "missing_permission", needed: "Screen Recording", how_to_fix: "<settings path>"}`
