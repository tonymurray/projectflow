# Capacitor Mobile App — Build Plan & History

This document records the planning notes and completed milestones for the ProjectFlow Android companion app (`mobile/`).

---

## Completed: Demote Viewers tab — merge webview_url into Launchers

The Viewers tab offered inline doc-file rendering (readme.md etc. from Nextcloud) and a button for the project's `webview_url`. In practice neither worked reliably — websites block iframes, remote .md files rarely exist, and the full-screen viewer was heavy for what it delivered. The Viewers tab was dropped; two content tabs remain (Resources + Notes). The project's `webview_url` surfaces as a "Links (viewers)" section at the bottom of the Resources tab.

### Files changed

| File | Change |
|------|--------|
| `mobile/app/src/components/Main.svelte` | Removed Viewers import, content block, and nav button |
| `mobile/app/src/components/Launchers.svelte` | Added "Links (viewers)" section after regular categories |
| `mobile/app/src/lib/store.js` | Updated activeTab type comment |

`Viewers.svelte` — left in place (unused).

---

## Completed: Android App Icon

The APK previously used the default Capacitor robot placeholder icon. The custom SVG (`mobile/app/src/assets/projectflow-launch.svg`) is now used as the Android home screen icon.

### Approach

1. **Convert SVG → 1024×1024 PNG** using Inkscape.
2. **Generate all Android icon sizes** using `@capacitor/assets` — the official Capacitor tool that auto-generates every `mipmap-*` PNG and the adaptive icon XML from a single source image.

`@capacitor/assets` expects a `resources/icon.png` (1024×1024) at the Capacitor project root (`mobile/app/`). Running `npx @capacitor/assets generate --android` writes:
- `android/app/src/main/res/mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher.png`
- `android/app/src/main/res/mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher_round.png`
- `android/app/src/main/res/mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher_foreground.png`
- `android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml` (adaptive icon)

### Files changed

| File | Change |
|------|--------|
| `mobile/app/package.json` | added `@capacitor/assets` as devDependency |
| `mobile/app/resources/icon.png` | new — 1024×1024 PNG rendered from the SVG |
| `mobile/app/android/app/src/main/res/mipmap-*/ic_launcher*.png` | replaced by `@capacitor/assets generate` |
| `mobile/app/android/app/src/main/res/mipmap-anydpi-v26/*.xml` | updated by `@capacitor/assets generate` |

---

## Completed: QR Code App Password Scan

Transferring a Nextcloud app password to the phone by typing it manually is error-prone. When you create an app password in Nextcloud (Settings → Security → App passwords), Nextcloud offers a "Show QR code" button. That QR code encodes all three credentials at once:

```
nc://login/server:https://your.server.com&user:tony&password:abcd-efgh-ijkl
```

Scanning it auto-fills Server URL, Username, and App Password in one step.

### Approach: Pure-JS QR scanning with `jsQR`

No new native Capacitor plugin needed. `jsQR` is a pure-JS library (~86 KB, MIT) that decodes QR codes from raw pixel data. Combined with the browser-standard `getUserMedia` API (supported in Capacitor's WebView on Android), the app opens the rear camera, streams frames to a hidden `<canvas>`, decodes each frame with jsQR, and closes the scanner when a valid `nc://login/` URL is detected.

### Files changed

| File | Change |
|------|--------|
| `mobile/app/package.json` | added `"jsqr": "^1.4.0"` to dependencies |
| `mobile/app/android/app/src/main/AndroidManifest.xml` | added CAMERA permission |
| `mobile/app/src/components/QrScanner.svelte` | new — camera overlay with jsQR decode loop |
| `mobile/app/src/components/Setup.svelte` | added "Scan QR" button + scanner wiring |

---

## Feasibility Notes — Options Compared

### A — Pure PWA (Progressive Web App)

| | |
|--|--|
| **Pros** | No build toolchain, no APK, works in any browser, fastest to build |
| **Cons** | **CORS blocks WebDAV by default on Nextcloud**. Cannot open Android native intents. |
| **Effort** | ~1–2 weeks if CORS is solved |

### B — Capacitor (chosen)

| | |
|--|--|
| **Pros** | Solves CORS natively. Can open Android intents. One codebase for web preview and APK. |
| **Cons** | Requires Android Studio + Node.js for builds (one-time setup). APK must be rebuilt when updating. |
| **Effort** | ~2–3 weeks for MVP |

### C — Flutter

| | |
|--|--|
| **Pros** | Best native feel, strong WebDAV libraries available |
| **Cons** | Dart is a new language to learn. Most complex option. |
| **Effort** | 4–6 weeks |

### D — BeeWare / Kivy (Python)

| | |
|--|--|
| **Pros** | Same language as desktop app |
| **Cons** | Toga Android support is still immature (2025). Kivy has a completely different UI paradigm. |
| **Recommendation** | Avoid |

---

## Architecture

```
Capacitor shell (Android APK)
  └── Svelte web app (runs locally on device)
        └── Nextcloud WebDAV client
              └── GET/PUT/PROPFIND → Nextcloud server (local network)
```

**Why Svelte over React/Vue**: Smaller output, simpler syntax, good fit for a focused utility app.

**Key technical decision — `WebDavPlugin.java`**: Capacitor's built-in `CapacitorHttp` only accepts standard HTTP methods and rejects `PROPFIND`. `WebDavPlugin` wraps OkHttp directly, allowing arbitrary methods.

**CORS in browser testing**: Use `proxy.py` which forwards WebDAV requests to Nextcloud with CORS headers. Run with `python3 proxy.py https://your-nextcloud-url`. Set Server URL in the app to `http://localhost:8765`.

---

## MVP Scope

**In:**
- First-run setup screen (Nextcloud URL, username, app password, folder paths)
- Project list from `projects/*.json` — sorted by pinned/recent order
- Launcher categories per project, desktop-only entries hidden
- URL launchers open in system browser
- Nextcloud file paths detected and opened via Nextcloud web UI (NC↗)
- Notes: view rendered markdown + edit raw markdown + save via WebDAV PUT
- Light/dark theme

**Out of MVP:**
- `.projectflow` folder-project configs
- PDF/image viewer tab
- Drag-to-reorder, edit mode, add launchers
- Offline caching (Phase 2)
