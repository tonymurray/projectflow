# Plan: Password Saving & Autofill for the Web Viewer

**Status: not started.** This is the follow-up feature scoped out of the 2026-08-25 cookie-persistence work (see `CLAUDE.md`'s "Cookie/session persistence" note and `docs/cookies_and_passwords.md`). Session-cookie persistence alone (already shipped) covers most of the practical "stay logged into Nextcloud" need; this plan exists for the cases it doesn't — sites that force short session lifetimes and require re-entering a password more often than is comfortable.

## Why this hasn't been built yet

QWebEngine (Qt's Chromium wrapper) has no native "Save password?" prompt the way a real browser does — building this means adding a genuinely new subsystem: a credential store, a new dependency, new toolbar/Settings UI, and a JS/Python bridge for reading and filling form fields. That's real scope, not a quick add-on, so it was deliberately left as a separately-scoped plan rather than built alongside the cheap cookie-path fix.

## Current relevant state (as of 2026-08-25)

- `self.webview` / `self.notes_webview` (`projectflow.py`, `__init__`) share Chromium's default `QWebEngineProfile`, now with a pinned, persistent storage path (`~/.local/share/ProjectFlow/webengine-profile/`).
- No `QWebEngineScript`/`QWebEngineScriptCollection`/`QWebChannel` usage exists anywhere in the codebase. Every existing JS bridge (Muya markdown editor, CodeMirror) is **pull-only**: Python calls `page().runJavaScript(js, callback)` on demand; there is no JS→Python push channel, and CLAUDE.md documents this as a deliberate architectural choice.
- `create_webview_toolbar()` (`projectflow.py`) builds Back/Forward/Refresh/Home/URL-bar/Go plus markdown edit/preview controls — nothing related to logins.
- Existing secret-storage precedent in this app: `kimai_token`/`joplin_token` are stored as **plaintext** in `.projectflow_settings.json` (machine-local, gitignored), masked only at the UI-widget level. No keyring/encryption is used anywhere today.
- `shell.nix` / `requirements.txt` list only `pyqt6`, `pyqt6-webengine`, `pymupdf`, `qtconsole`, `ipykernel` — no `keyring`/`secretstorage`.

## Recommended approach

### Storage: OS keyring (KWallet via Secret Service), not plaintext JSON

Add the Python `keyring` package (nixpkgs: `python313Packages.keyring` + `secretstorage`) to `shell.nix`'s `python313.withPackages` list and to `requirements.txt`. On this KDE system, `keyring` talks to KWallet through the Secret Service D-Bus API — this is a genuine security upgrade over the existing `kimai_token`/`joplin_token` plaintext pattern, and fits the app's existing philosophy of integrating with the desktop environment (same spirit as the terminal/editor/file_manager auto-detection).

Schema:
- One keyring secret per site, keyed by origin: `keyring.set_password("ProjectFlow", f"web:{scheme}://{host}:{port}", password)`.
- Usernames are not sensitive — store them, per origin, in `.projectflow_settings.json` under a new `web_logins` list (`[{"origin": "https://nextcloud.example.com", "username": "tony"}, ...]`), machine-local like every other secret-adjacent setting today.
- **Origin matching must be exact** (scheme + host + port) — never match by path or substring. This is the app's one real anti-phishing guardrail; get it wrong and autofill could hand a credential to the wrong site.

### Autofill: pull-based, on page load

On `self.webview.loadFinished`, look up a saved credential for the current URL's origin (`self.webview.url()`). If found, run one `page().runJavaScript(...)` call that:
1. Queries the DOM for `input[type=password]`.
2. Walks backward to the nearest preceding `input[type=text]`/`input[type=email]` as the username field.
3. Sets both `.value` properties and dispatches an `input` event on each (many frameworks only recognize a value change via the event, not a raw property set).

This reuses the exact bridge pattern already used for Muya/CodeMirror — no new push channel needed.

**Known limitation to state plainly, not hide**: this heuristic only handles conventional `<input type=password>` login forms (which Nextcloud's own login page is). JS-heavy SPA logins, multi-step flows, or shadow-DOM forms on other sites won't be covered. That's an acceptable gap for a personal tool, not a bug to chase.

### Saving a credential: explicit button, not auto-detected

Rather than adding `QWebChannel`/a JS→Python push channel to auto-detect form submissions (a real architecture change CLAUDE.md documents as deliberately avoided elsewhere), add a manual **"🔑 Save login for this site"** button to `create_webview_toolbar()`. Clicking it:
1. Runs one `runJavaScript()` call reading the current values of the visible password field (and its paired username field) on the page right now.
2. If a password value is present, stores it via `keyring.set_password(...)` under the current origin, and records/updates the username entry in `web_logins`.

Less magical than a browser's automatic "save this password?" prompt, but it stays consistent with the app's pull-only design instead of introducing its first push channel — a deliberate trade-off, not an oversight.

### Management UI

A small "Web Logins" section, most naturally in the Settings dialog (mirroring the existing Integrations tab's list-with-delete pattern): list saved origins + usernames, with a delete button that removes both the `web_logins` entry and the keyring secret (`keyring.delete_password(...)`).

## Security notes (state explicitly to the user once built, not just in this doc)

- KWallet typically auto-unlocks with the login session on most KDE setups — any other process running as the same OS user has equivalent read access to these secrets via the same Secret Service API. This is the identical trust boundary already accepted and documented for the ttyd terminal feature (loopback-only, no auth, same-user-equivalent-access) — not a new risk category, just worth restating here.
- Exact-origin matching (see above) is the only phishing guard; there is no visual "this login was autofilled" indicator planned, which is worth reconsidering if this ever gets built for more than fully-trusted local-network sites.
- No credential ever leaves the local machine or gets written into a project's own JSON config (which syncs via Nextcloud/Syncthing) — only `.projectflow_settings.json` (machine-local) and the OS keyring are touched.

## Suggested build order

1. Add `keyring`/`secretstorage` to `shell.nix` + `requirements.txt`; confirm `keyring.set_password`/`get_password`/`delete_password` round-trip against KWallet in this environment (a 5-line smoke test, not part of the app yet).
2. Wire up autofill-on-load (read-only path) against a `web_logins` list you populate by hand in `.projectflow_settings.json` for one test site — proves the JS field-detection/fill logic before building any save UI.
3. Add the toolbar "🔑 Save login" button and wire it to the keyring + `web_logins` write path.
4. Add the Settings dialog "Web Logins" list/delete UI.
5. Document in `CLAUDE.md` (a new subsection near the Web-tabs documentation) and `CHANGELOG.md`.

## Verification (once built)

- Visit a local site with a plain login form (e.g. Nextcloud), log in manually once, click "🔑 Save login for this site."
- Fully quit and relaunch ProjectFlow, navigate back to that site's login page, confirm username+password are auto-filled (but not auto-submitted — user still clicks the site's own login button).
- Confirm the credential is retrievable via `keyring.get_password("ProjectFlow", "web:<origin>")` from a plain Python shell, and disappears after using the Settings dialog's delete action.
- Confirm visiting a *different* origin never autofills a credential saved for another site.
