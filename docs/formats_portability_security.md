# Formats, Portability & Security — Tactical Decisions

This document collects the recurring architectural/philosophical decisions
behind *how* ProjectFlow stores data, stays portable across machines, and
handles anything that can execute a command. These aren't arbitrary
implementation details — most were arrived at after a specific bug, a
specific risk, or a specific "what should this actually do" discussion, and
are worth keeping visible so future changes don't accidentally regress them.

## Plain files over databases or proprietary formats

- **Notes are markdown files on disk** (`notes/*.md`, or a project-local
  `projectflow.md`), never stored in a database or as HTML blobs inside the
  app — specifically so they sync via Nextcloud and stay editable in
  Typora/Zettlr/`kate`/any markdown tool, or under version control. Legacy
  HTML notes were migrated to markdown once, as a one-time move onto this
  convention (`html_to_markdown()`), not an ongoing dual format.
- **Project configs are JSON**, not a binary or database format —
  human-readable, diffable, Nextcloud-syncable, and hand-editable in a pinch
  if the UI can't reach some edge case.
- **Aliases are dual-written**: into the app's own JSON *and* a real
  shell-sourceable file (`projects/aliases.json`/`aliases.html`) — usable
  both inside ProjectFlow and from an ordinary shell.
- **Tags use KDE's actual Baloo/xattr mechanism** (`user.xdg.tags`) rather
  than an app-invented tagging system, so a project's tag shows up in
  Dolphin's own tag autocomplete too — integrate with an existing desktop
  convention instead of reinventing one.

## Portability as a first-class constraint

- **`.projectflow` project-local configs use `.`/`./`-relative paths**
  specifically so the whole project folder can be moved or cloned elsewhere
  and still work — resolved to absolute only at load time
  (`resolve_relative_paths_in_config()`).
- **Global path mappings are a read-time fallback only, never persisted
  back** into a config (`_resolve_existing_path()`). An earlier design that
  unconditionally preferred the mapped path could get read back and saved,
  permanently corrupting a portable path (`~/Public/key` silently becoming
  `~/gtr7/Public/key`) — this was a real bug, not a hypothetical, and the
  fix was to make the fallback strictly read-only and scoped to the single
  action that needed it.
- **Per-project settings vs. per-machine settings are kept strictly
  separate.** Things like theme, terminal, viewer height, folder view mode
  live only in `.projectflow_settings.json` (per-machine, gitignored);
  things like layout mode, pinned defaults, category structure live only in
  the project's own JSON (shared/synced). Neither leaks into the other.
- **Credentials never live in a project file.** Kimai/Joplin tokens live
  only in the machine-local `.projectflow_settings.json`, never in a
  synced/shared project config — a project file can be copied, committed, or
  handed to someone else without leaking a secret.

## Security safeguards

ProjectFlow does **not** sandbox or privilege-separate anything it launches
— a launcher item runs with exactly the same permissions as the user who's
running ProjectFlow, identical to double-clicking a `.desktop` file or
typing the same command into an already-open terminal. That's a deliberate
scope boundary, not an oversight: this is a personal, single-user desktop
convenience tool, not a platform for running untrusted content. The
safeguards below all target a narrower, real risk — *accidental or silent*
execution — not the mechanism of execution itself:

- **Opening a single risky launcher (terminal, editor, `rsync_backup`,
  `alias`, `run`, `ssh_session`, etc.) is treated as no riskier than opening
  any other desktop app**, and gets no special confirmation — clicking it is
  exactly as deliberate an action as clicking any other launcher, or opening
  a terminal from the task bar.
- **The actual risk is "Open All" firing several of these at once with a
  single click**, invisibly. Two independent guards exist for this:
  1. **"Open All" is opt-in per category, off by default — including for
     Documentation.** A category is just whatever's been physically filed
     there, so nothing stops a risky item from ending up somewhere
     unexpected; the header only becomes clickable once explicitly enabled
     via right-click.
  2. **A second guard fires even once a category has Open All enabled**:
     `open_all_in_group()` checks every item's app type against
     `COMMAND_EXECUTING_APPS` (`alias`, `run`, `terminal`, `konsole`,
     `ssh_session`, `npm`, `directorydev`, `terminal_cmd`/`terminal_npm`,
     every `rsync_backup*` variant, or any custom handler explicitly marked
     `"type": "shell"`) and, if any are present, shows a one-line
     confirmation naming exactly what will run before proceeding. This
     catches the case where a category's contents change to include
     something riskier *after* Open All was already turned on for it.
  3. The same `COMMAND_EXECUTING_APPS` set also excludes these handler types
     from the Focus-layout Apps tab's auto-generated tiles — they're actions
     on a specific path, not standalone apps meant to be opened blank.
- **The shell-alias-name shadow guardrail**: naming an alias after a real
  shell builtin (most notably `cd`) is a genuine footgun — bash appends the
  invocation argument onto the alias's own command, breaking every later
  bare `cd <dir>` in the same shell. `_classify_shell_name()` checks the
  *real* shell (`bash -c 'type -t <name>'`) rather than maintaining a static
  list of risky names, so it can't go stale as commands come and go. Wired
  into both interactive alias-creation surfaces as a live warning, with a
  second Yes/No confirmation right before the alias is actually written into
  the sourceable shell file (the launcher item itself still saves either
  way, since it's inert project data until sourced).
- **The embedded terminal (ttyd) is loopback-only and origin-checked.**
  Spawned as `ttyd -i 127.0.0.1 -p 0 -W -O -w <cwd> <$SHELL>` — bound to
  `127.0.0.1` only (never `0.0.0.0`), with no authentication configured
  (acceptable since it's loopback-only: any other local process running as
  the same OS user already has equivalent access). The one gap loopback
  binding alone does *not* close: WebSocket connections aren't subject to
  same-origin policy the way `fetch`/XHR are, so without `-O`
  (`--check-origin`) any JavaScript running in *any* browser tab on the
  machine could open a WebSocket straight to the port and get a shell — a
  known attack class against other unauthenticated localhost dev servers.
  `-O` closes that specific hole. A residual gap this does **not** cover:
  a different local account on a shared multi-user machine could still
  connect — explicitly out of scope for a single-user desktop app.
- **ttyd's process does not outlive the app.** Unlike external
  terminal/editor/file-manager launches (`start_new_session=True`, meant to
  keep running after ProjectFlow closes), ttyd is spawned with
  `start_new_session=False` and is explicitly stopped for every open
  terminal tab in `closeEvent()` — it's an internal implementation detail,
  not a standalone app the user asked to keep open.
- **Baloo tagging is non-destructive by construction, so it needs no
  confirmation dialog.** `_baloo_tag_append()` only ever merges into a
  file's existing tags, never removes or overwrites unrelated ones — a file
  already manually tagged in Dolphin keeps those tags. This is why both
  "create Baloo tags" buttons (global and per-project) can run repeatedly
  with no guard, and why the two are allowed to differ in scope (global:
  notes-file-only, fast and predictable; per-project: every real file/folder
  the project's launchers reference, a deliberate one-off deep sweep) rather
  than being unified — confirmed as intentional, not something to converge.
- **No silent network calls.** Kickstart's Website field, for example, takes
  the URL exactly as typed with no fetch/validation — consistent with the
  app's broader "no silent side effects" rule (`refresh_projects()` and
  friends should only do what their name implies), and incidentally means
  nothing in the app makes an outbound request the user didn't directly
  trigger by opening something.
- **Destructive actions get confirmation only where data can genuinely be
  lost**, calibrated to actual risk rather than applied uniformly:
  - The Code Editor has a real discard-changes guard
    (`_confirm_discard_code_changes()`) because its deliberate no-autosave
    design means a background tab's unsaved content only ever exists in
    memory — closing the app, switching projects, or discarding a dirty tab
    are the only places that content can be lost, so those are exactly the
    places guarded.
  - Notes/webview markdown have no equivalent guard because they autosave
    continuously — there's structurally very little to lose.
  - Project Settings form fields have no unsaved-changes guard at all —
    navigating away discards silently, accepted because redoing a form
    field is low-cost compared to redoing typed code.

## Why this grouping matters

The common thread: ProjectFlow treats *file format choice* and *portability*
as trust/ownership questions (whose data is this, and does it survive being
copied, synced, or opened by something else?), and treats *security* as a
"prevent silent/accidental action" question rather than a sandboxing
question. Keeping these two concerns distinct — instead of reaching for a
sandboxing/permission model that would fight the app's whole reason for
existing (fast, low-friction access to real desktop actions) — is itself a
tactical decision worth stating explicitly.
