# macos-control

An MCP server that lets the Hermes agent drive macOS: list/focus windows,
take screenshots, type text, send key combos, run AppleScript, and post
notifications. Built on `osascript` and `screencapture` only — no third-party
automation framework.

## Tools

| Tool | What it does | Permission needed |
|------|--------------|-------------------|
| `list_windows` | enumerate on-screen windows | Accessibility |
| `focus_app(app_name)` | bring an app to the foreground | Automation (per app) |
| `focus_window(app_name, title_substring)` | raise a matching window | Accessibility |
| `screenshot_full(path)` | full-display screenshot | Screen Recording |
| `screenshot_window(window_id, path)` | one window | Screen Recording |
| `screenshot_region(x,y,w,h,path)` | a region | Screen Recording |
| `type_text(text)` | type into the frontmost window | Accessibility |
| `key_combo(combo)` | e.g. `cmd+c` (single-char key + modifiers) | Accessibility |
| `run_applescript(script)` | run raw AppleScript | varies by target |
| `notify(title, message)` | post a notification | none |

## Required macOS permissions

Grant these to the **terminal application that launches Hermes** (the
responsible process — see the repo `SECURITY.md`). Run `hermes doctor` to check
status and get one-click deep-links.

- **Accessibility** — System Settings → Privacy & Security → Accessibility
  (`x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility`)
- **Screen Recording** — …?Privacy_ScreenCapture
- **Automation** (per controlled app) — …?Privacy_Automation

## Error behavior

When a tool call fails because a TCC permission is missing, it returns a
structured error instead of raising:

```json
{"ok": false, "error": "missing_permission",
 "needed": "Accessibility",
 "how_to_fix": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"}
```

> Screen Recording is special: a missing grant does **not** make
> `screencapture` fail — it silently returns a wallpaper-only image. The
> screenshot tools return the path with a note; use `hermes doctor` to confirm
> the grant is actually in place.
