import { writable, derived, get } from 'svelte/store';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { Network } from '@capacitor/network';
import { setConfig, listProjects, loadProject, saveProjectConfig, loadNote, saveNote, notesFilename, resolveToNextcloudRelPath, uploadDocumentToProject, loadTodo, saveTodo, isOfflineish, NetworkError } from './webdav.js';
import { cacheProject, getCachedProject, cacheNote, getCachedNote, cacheTodo, getCachedTodo } from './cache.js';
import { parseTodos, toggleLine, renameLine, appendLine } from './todoParser.js';

// ── Theme ─────────────────────────────────────────────────────────────────────

const THEME_KEY = 'pf_theme';

export const theme = writable(localStorage.getItem(THEME_KEY) || 'dark');

theme.subscribe(t => {
  localStorage.setItem(THEME_KEY, t);
  document.documentElement.setAttribute('data-theme', t);
});

// ── Pinned / recent project ordering ─────────────────────────────────────────

const PINNED_KEY = 'pf_pinned';
const RECENT_KEY = 'pf_recent';

export const pinnedProjects = writable(
  JSON.parse(localStorage.getItem(PINNED_KEY) || '[]')
);
export const recentProjects = writable(
  JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
);

pinnedProjects.subscribe(v => localStorage.setItem(PINNED_KEY, JSON.stringify(v)));
recentProjects.subscribe(v => localStorage.setItem(RECENT_KEY, JSON.stringify(v)));

export function togglePin(filename) {
  pinnedProjects.update(pins =>
    pins.includes(filename) ? pins.filter(f => f !== filename) : [filename, ...pins]
  );
}

// ── Config ────────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'pf_config';

function loadStoredConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return migrateConfig(JSON.parse(raw));
  } catch {}
  return null;
}

// Migrates the old single localAlias/nextcloudAlias pair (pre-Settings-screen) into the
// new repeatable nextcloudLocations list, so an existing user's saved alias keeps working
// without having to re-enter it. The legacy fields are left in place but unused once this
// has run — nextcloudLocations (even as []) is authoritative from here on.
function migrateConfig(cfg) {
  if (!cfg) return cfg;
  if (!cfg.nextcloudLocations) {
    cfg.nextcloudLocations = (cfg.localAlias && cfg.nextcloudAlias)
      ? [{ local: cfg.localAlias, remote: cfg.nextcloudAlias }]
      : [];
  }
  if (!cfg.openMethod) cfg.openMethod = 'browser';
  return cfg;
}

export const config = writable(loadStoredConfig());

config.subscribe(cfg => {
  if (cfg) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg));
    setConfig(cfg);
  }
});

// ── Projects ──────────────────────────────────────────────────────────────────

// Cached to localStorage (unlike loading/error/offline below, which are pure runtime
// status) so a cold start while offline still has a project list to pick a share target
// from — a successful fetchProjects() refreshes the cache via this same subscribe, so
// there's no separate "update the cache" step anywhere else. First-ever launch while
// offline (nothing cached yet) still has nothing to show — unavoidable without having
// been online at least once.
const PROJECTS_CACHE_KEY = 'pf_projects_cache';

export const projects = writable(
  JSON.parse(localStorage.getItem(PROJECTS_CACHE_KEY) || '[]')
);
projects.subscribe(v => {
  if (v.length) localStorage.setItem(PROJECTS_CACHE_KEY, JSON.stringify(v));
});

export const activeProject = writable(null);
export const activeConfig = writable(null);
export const loading = writable(false);
export const error = writable(null);
export const offline = writable(false); // "can we currently reach the WebDAV server"

// Set by selectProject() whenever the active project/note is showing a locally cached
// fallback copy rather than a fresh network response — see cache.js. null = showing live
// data (or nothing loaded yet).
export const usingCachedCopy = writable(null); // { projectFilename, cachedAt } | null

function clearStatus() {
  error.set(null);
  offline.set(false);
}

// Exactly one of {offline, error} is ever true after this runs — avoids a stale
// offline=true lingering next to a fresh unrelated error, or vice versa.
function handleFailure(e, prefix = '') {
  if (isOfflineish(e)) {
    offline.set(true);
    error.set(null);
  } else {
    error.set(prefix + e.message);
    offline.set(false);
  }
}

// ── Pending offline queue (link/note pushes queued while offline) ───────────────
//
// Deliberately stores only the INTENT of each operation (which project, what
// URL/title, or what text) — never a snapshot of the project config/note content.
// addLinkToProject()/addTextToProjectNote() below both already "fetch current server
// state -> apply one small change -> save the whole thing back," so replaying the same
// call later (rather than resubmitting something captured at queue-time) is what keeps
// this safe from clobbering unrelated changes: each replay always acts on whatever is
// actually on the server at the moment it runs, exactly as if it had been done directly
// while online.
const QUEUE_KEY = 'pf_pending_queue';

// { type: 'link', projectFilename, projectName, url, title, queuedAt }
// { type: 'note', projectFilename, projectName, text, queuedAt }
export const pendingQueue = writable(
  JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]')
);
pendingQueue.subscribe(v => localStorage.setItem(QUEUE_KEY, JSON.stringify(v)));

export function queueOperation(op) {
  pendingQueue.update(q => [...q, { ...op, queuedAt: Date.now() }]);
}

// Set by flushQueue() whenever a flush attempt leaves one or more items stuck on a
// per-resource failure (e.g. a locked file) rather than genuine offline — surfaced as a
// dismissible banner so "N pending" isn't a silent dead end. Cleared automatically the
// next time a flush attempt fully succeeds; left untouched on a genuine offline break,
// since the offline pill already covers that case on its own.
export const queueFeedback = writable(null); // string message | null

// Real bug found via testing: flushQueue() can be triggered from more than one place in
// quick succession (Android can fire networkStatusChange more than once for a single
// reconnect, each scheduling its own retryConnection() -> flushQueue() via
// initNetworkWatcher; a manual Retry tap can also land while an auto-triggered flush is
// still in flight). Two concurrent runs both read the same starting queue and each ends
// with its own pendingQueue.set(remaining) — whichever finishes LAST wins and can
// silently overwrite an already-successful, now-empty queue with a stale one, which is
// exactly what "stuck at 1 pending even after reconnecting again" looks like. This flag
// makes a flush a no-op while one is already running, rather than trying to merge two
// concurrent views of the queue.
let _flushing = false;

// A per-item safety net: if a single request never settles (neither resolves nor
// rejects — a true network hang, not a caught HTTP/network error, which the try/catch
// below already handles), a plain `await` would suspend this function forever, and
// since _flushing is only ever reset in the `finally` further down, it would stay stuck
// `true` forever too — permanently blocking every future flush attempt, including a
// manual Retry tap, until the app is force-restarted. Racing each item against a timeout
// guarantees flushQueue() always eventually returns one way or another.
const FLUSH_ITEM_TIMEOUT_MS = 30000;

function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new NetworkError('timed out')), ms)),
  ]);
}

export async function flushQueue() {
  if (_flushing) return;
  const queue = get(pendingQueue);
  if (!queue.length) return;
  _flushing = true;
  try {
    const remaining = [...queue];
    // Items that hit a per-resource transient status (e.g. a Nextcloud file lock) this
    // round — kept queued for the next flush, but set aside so one stuck item doesn't
    // block every OTHER item behind it in the same pass (see the real bug this fixes,
    // below). Each item is attempted at most once per flushQueue() call, so this can't
    // spin forever even if the same item keeps coming back locked.
    const stillStuck = [];
    while (remaining.length) {
      const item = remaining[0];
      console.log('[flushQueue] attempting', item.type, item.projectName, item.projectFilename);
      try {
        const proj = { filename: item.projectFilename };
        if (item.type === 'link') {
          await withTimeout(addLinkToProject(proj, item.url, item.title), FLUSH_ITEM_TIMEOUT_MS);
        } else {
          await withTimeout(addTextToProjectNote(proj, item.text), FLUSH_ITEM_TIMEOUT_MS);
        }
        console.log('[flushQueue] succeeded', item.type, item.projectName);
        remaining.shift(); // succeeded — drop it and continue with the rest
      } catch (e) {
        console.warn('[flushQueue] failed', item.type, item.projectName, '-', e.name, e.message, 'status=' + e.status, 'offlineish=' + isOfflineish(e));
        if (e instanceof NetworkError) break; // genuinely can't reach the server at all —
                                               // stop the whole batch, nothing else will work either
        if (isOfflineish(e)) {
          // A real, live bug this fixes: a retryable HTTP status (429/502/503/504, or —
          // the actual case found via testing — 423 Locked on one specific project file)
          // is a PER-RESOURCE issue, not a connectivity one; we're clearly still online
          // (other requests are succeeding). Treating it the same as "offline" used to
          // `break` here too, which silently blocked every OTHER queued item behind
          // whichever one happened to be stuck — e.g. a locked "Home Lab" config kept an
          // unrelated project's queued link from ever getting a chance to send. Leave
          // just this one item queued for next time and keep going with the rest.
          stillStuck.push(remaining.shift());
          continue;
        }
        // A real, item-specific failure (e.g. 404 — project renamed/removed since
        // queueing) — retrying forever won't help. Drop just this one, surface it, and
        // keep going with the rest of the queue.
        remaining.shift();
        error.set(`Queued ${item.type === 'link' ? 'link' : 'note'} for "${item.projectName}" failed: ${e.message}`);
      }
    }
    const finalQueue = [...remaining, ...stillStuck];
    pendingQueue.set(finalQueue);
    if (stillStuck.length) {
      const names = [...new Set(stillStuck.map(i => i.projectName))].join(', ');
      queueFeedback.set(
        `Could not sync ${stillStuck.length === 1 ? 'an item' : stillStuck.length + ' items'} for ${names} — ` +
        `the note or project file may be locked (e.g. still open in Nextcloud's web editor). ` +
        `Check there, then try Retry again.`
      );
    } else if (finalQueue.length === 0) {
      // Everything that was queued this round is now gone (sent, or dropped as a
      // non-retryable failure above) — any earlier "might be locked" message is stale.
      queueFeedback.set(null);
    }
  } finally {
    _flushing = false;
  }
}

// Re-runs whichever operation actually has unfinished business — used by the Retry
// button and by the automatic network-regained watcher (see initNetworkWatcher below).
// Also flushes the pending queue first, so both the manual Retry tap and the automatic
// network-regained watcher below pick up any queued shares, not just resume whatever
// project-loading/note-saving was already in flight.
export async function retryConnection() {
  await flushQueue();
  const proj = get(activeProject);
  if (!proj) return fetchProjects();
  if (!get(activeConfig)) return selectProject(proj);
  if (!get(noteSaved)) return persistNote(get(activeNote));
  return fetchProjects(); // nothing specific pending — cheap reachability check
}

// Listens for the device regaining connectivity and, if we're currently marked
// offline, retries automatically rather than waiting for the user to notice and tap
// Retry. Native-only — no equivalent signal wired up for the browser dev fallback.
export function initNetworkWatcher() {
  if (!Capacitor.isNativePlatform()) return;
  Network.addListener('networkStatusChange', status => {
    if (status.connected && get(offline)) {
      // Give DNS/routing a moment to actually settle before retrying.
      setTimeout(() => retryConnection(), 1500);
    }
  });
}

// Projects to show in the bar: pinned first, then recent (deduplicated), max 8 total.
// "aliases.json" is deliberately excluded here regardless of pinned/recent state — it's a
// desktop-only utility file (shell alias definitions; every launcher item in it is a
// desktop-specific handler), not a real project someone opens day-to-day on mobile. Same
// special-case the desktop app itself already applies elsewhere (e.g.
// _bulk_create_baloo_tags() skips it too), not a new rule invented here. Still fully
// reachable via the ≡ All Projects picker, which reads $projects directly and isn't
// filtered by this at all — so it stays available to open/review, just not cluttering the
// quick-access bar.
const ALIASES_FILENAME = 'aliases.json';
export const orderedProjects = derived(
  [projects, pinnedProjects, recentProjects],
  ([$projects, $pinned, $recent]) => {
    const byFilename = Object.fromEntries($projects.map(p => [p.filename, p]));
    const pinnedList = $pinned
      .filter(f => f !== ALIASES_FILENAME)
      .map(f => byFilename[f])
      .filter(Boolean);
    const pinnedSet = new Set($pinned);
    const recentList = $recent
      .filter(f => f !== ALIASES_FILENAME && !pinnedSet.has(f))
      .map(f => byFilename[f])
      .filter(Boolean)
      .slice(0, 8 - pinnedList.length);
    return [...pinnedList, ...recentList];
  }
);

export async function fetchProjects() {
  loading.set(true);
  clearStatus();
  try {
    const list = await listProjects();
    projects.set(list);
    return list;
  } catch (e) {
    handleFailure(e);
    return [];
  } finally {
    loading.set(false);
  }
}

export async function selectProject(project) {
  recentProjects.update(r =>
    [project.filename, ...r.filter(f => f !== project.filename)].slice(0, 20)
  );
  activeProject.set(project);
  activeConfig.set(null);
  activeNote.set('');
  noteSaved.set(true);
  usingCachedCopy.set(null);
  loading.set(true);
  clearStatus();
  const nf = notesFilename(project.filename);
  let projectLoadedFresh = false;
  try {
    const cfg = await loadProject(project.filename);
    activeConfig.set(cfg);
    cacheProject(project.filename, cfg); // fire-and-forget, never blocks the UI
    projectLoadedFresh = true;

    const note = await loadNote(nf);
    activeNote.set(note);
    cacheNote(nf, note);
  } catch (e) {
    // Only fall back to a cached copy for a genuine "can't reach the server" failure —
    // a real error (404, auth failure, etc.) means something actually changed and should
    // surface as an error, not silently paper over it with stale content.
    if (isOfflineish(e)) {
      const cachedProject = projectLoadedFresh ? null : await getCachedProject(project.filename);
      const cachedNote = await getCachedNote(nf);
      if (cachedProject || cachedNote || projectLoadedFresh) {
        if (cachedProject) activeConfig.set(cachedProject.data);
        if (!projectLoadedFresh || cachedNote) activeNote.set(cachedNote ? cachedNote.data : '');
        usingCachedCopy.set({
          projectFilename: project.filename,
          cachedAt: (cachedProject ?? cachedNote)?.cachedAt ?? null,
        });
        clearStatus();
        loading.set(false);
        return;
      }
    }
    handleFailure(e);
  } finally {
    loading.set(false);
  }
}

// Fetches and caches every known project's config + notes + todo.md (if it has a
// documents_subfolder) in one pass, so they're all available offline afterward — not
// just whichever ones happen to have been opened this session. Sequential rather than
// parallel, deliberately: this is a manual, occasional "get ready to go offline" action
// (triggered from Settings), not something latency-sensitive, and sequential avoids
// firing a burst of concurrent requests at the server. Skips past any individual
// project's failure (todo.md included) and keeps going with the rest.
export async function precacheAllProjects() {
  const list = get(projects);
  let succeeded = 0;
  let failed = 0;
  for (const project of list) {
    try {
      const cfg = await loadProject(project.filename);
      await cacheProject(project.filename, cfg);
      const nf = notesFilename(project.filename);
      const note = await loadNote(nf);
      await cacheNote(nf, note);
      if (cfg?.documents_subfolder) {
        const todo = await loadTodo(cfg.documents_subfolder);
        await cacheTodo(cfg.documents_subfolder, todo);
      }
      succeeded++;
    } catch {
      failed++;
    }
  }
  return { succeeded, failed, total: list.length };
}

// ── Notes ─────────────────────────────────────────────────────────────────────

export const activeNote = writable('');
export const noteSaved = writable(true);

let _saveTimer = null;

export function queueNoteSave(content) {
  activeNote.set(content);
  noteSaved.set(false);
  clearTimeout(_saveTimer);
  _saveTimer = setTimeout(() => persistNote(content), 1500);
}

export async function persistNote(content) {
  let proj;
  const unsub = activeProject.subscribe(p => proj = p);
  unsub();
  if (!proj) return;
  try {
    await saveNote(notesFilename(proj.filename), content);
    noteSaved.set(true);
    // Only cleared on a confirmed success, deliberately NOT at the start of this
    // function like fetchProjects()/selectProject() — this fires automatically every
    // 1.5s while typing, so clearing-then-possibly-resetting on every keystroke pause
    // would make the offline indicator flicker during a sustained outage.
    clearStatus();
  } catch (e) {
    handleFailure(e, 'Save failed: ');
  }
}

// ── Todos ─────────────────────────────────────────────────────────────────────
//
// A single aggregated list rather than desktop's "This project"/"All projects" scope
// toggle (a deliberate mobile simplification, by direct request): the current
// project's group is always first, every other known project follows alphabetically.
// No scope/mode to persist — the only thing this feature remembers is the completed-
// tasks filter.

const SHOW_COMPLETED_TODOS_KEY = 'pf_show_completed_todos';

export const showCompletedTodos = writable(localStorage.getItem(SHOW_COMPLETED_TODOS_KEY) === '1');
showCompletedTodos.subscribe(v => localStorage.setItem(SHOW_COMPLETED_TODOS_KEY, v ? '1' : '0'));

// [{ project: {filename, name}, items: [{lineIndex, text, done}], fromCache, cachedAt }]
export const allTodos = writable([]);
export const todosLoading = writable(false);
export const todosError = writable(null);

// Resolves one project's parsed config, reusing the already-in-memory activeConfig for
// whichever project is currently active (saves a round trip) rather than always
// re-fetching — every other project still needs its own loadProject() call, since
// there's no in-memory map of every project's config kept around.
async function resolveProjectConfig(project) {
  const current = get(activeProject);
  if (current && project.filename === current.filename) {
    const cfg = get(activeConfig);
    if (cfg) return cfg;
  }
  return await loadProject(project.filename);
}

// Network-first fetch of one project's todo.md, falling back to its cached copy on an
// offline-ish failure (same convention selectProject() already uses) — a real error
// (404/401/etc.) is NOT swallowed here, it propagates so the caller can decide whether
// to skip just this one project (loadAllTodos) or surface it (a direct write action).
async function fetchTodoWithFallback(documentsSubfolder) {
  try {
    const content = await loadTodo(documentsSubfolder);
    cacheTodo(documentsSubfolder, content); // fire-and-forget, keeps the offline copy fresh
    return { content, fromCache: false, cachedAt: null };
  } catch (e) {
    if (!isOfflineish(e)) throw e;
    const cached = await getCachedTodo(documentsSubfolder);
    if (!cached) throw e;
    return { content: cached.data, fromCache: true, cachedAt: cached.cachedAt };
  }
}

// Rebuilds just ONE project's group from the server (or cache) and splices it back
// into allTodos — used after every toggle/rename/add so a single-line change doesn't
// require re-fetching every other project's todo.md too (unlike desktop's local-disk
// full-rebuild-after-any-action convention, a real network round trip per project is
// too costly to redo N times for a one-line change).
async function refreshOneGroup(project, documentsSubfolder) {
  const { content, fromCache, cachedAt } = await fetchTodoWithFallback(documentsSubfolder);
  const group = {
    project: { filename: project.filename, name: project.name },
    items: parseTodos(content),
    fromCache,
    cachedAt,
  };
  allTodos.update(groups => {
    const exists = groups.some(g => g.project.filename === project.filename);
    return exists
      ? groups.map(g => (g.project.filename === project.filename ? group : g))
      : [...groups, group];
  });
  return group;
}

// Builds the full aggregated list, current project's group plus every other known
// project. A project that can't even have its config read, or that has no
// documents_subfolder yet, is silently skipped — same "absent until used" convention
// listProjectDocuments() already follows, not an error. A non-current project with
// zero checklist lines at all (done or pending) is skipped too — nothing a "Include
// completed" toggle could ever reveal for it. The CURRENT project's group is always
// kept even when empty, since it's the Add Task row's implicit target.
//
// Fetched with TODOS_CONCURRENCY projects in flight at once (a small worker pool
// pulling from a shared index, not Promise.all over everything) rather than fully
// sequential or fully parallel — confirmed live that a strictly sequential pass over
// 50+ projects takes tens of seconds; firing all of them at once risks hammering the
// Nextcloud server/native WebDAV bridge with 100+ simultaneous requests. Each group
// is pushed into `allTodos` as soon as ITS OWN fetch resolves, not batched into one
// allTodos.set() at the end — keeps the UI filling in progressively rather than
// sitting on stale content for the whole pass. Because workers complete out of
// request order under concurrency, `allTodos` does NOT come out in the same order as
// the alphabetical `ordered` list it was built from — Todos.svelte finds the current
// project's group by filename match (not by assuming it's allTodos[0]) and re-sorts
// "Other Projects" alphabetically for display, so the visible order stays stable and
// predictable regardless of which network call happened to finish first.
const TODOS_CONCURRENCY = 6;

// Generation counter guarding against overlapping loadAllTodos() calls — e.g. the
// user switches project A -> B -> C in quick succession, firing three calls before
// the first has finished its pass. Without this, two in-flight calls' incremental
// allTodos.update() pushes can interleave, leaving stale data from an abandoned
// project switch mixed into the list. Same token-and-compare pattern
// Launchers.svelte's loadProjectDocuments() already uses for its own async race.
let _todosLoadToken = 0;

async function loadOneProjectGroup(project, isCurrent, token) {
  let cfg = null;
  try {
    cfg = await resolveProjectConfig(project);
  } catch {
    cfg = null; // for a non-current project this just means "skip it" below; for the
    // current project it still falls through to the empty-anchor branch next.
  }
  if (token !== _todosLoadToken) return;
  if (!cfg?.documents_subfolder) {
    // No documents folder (yet) — same "absent until used" skip every OTHER project
    // gets. The CURRENT project is the one exception: it still gets an EMPTY group
    // pushed, so its section always appears as the Add Task row's obvious anchor,
    // rather than silently vanishing just because it hasn't used Docs/To-Do before.
    // (Confirmed live on-device: without this, a current project with no documents
    // folder dropped out of the list entirely, and whichever OTHER project happened
    // to sort first alphabetically wrongly appeared to be "pinned first" instead.)
    if (isCurrent) {
      allTodos.update(groups => [...groups, {
        project: { filename: project.filename, name: project.name },
        items: [],
        fromCache: false,
        cachedAt: null,
      }]);
    }
    return;
  }
  try {
    const { content, fromCache, cachedAt } = await fetchTodoWithFallback(cfg.documents_subfolder);
    if (token !== _todosLoadToken) return;
    const items = parseTodos(content);
    if (items.length === 0 && !isCurrent) return;
    allTodos.update(groups => [...groups, {
      project: { filename: project.filename, name: project.name },
      items,
      fromCache,
      cachedAt,
    }]);
  } catch {
    // a real error (404/401) for this one project — skip it, not the whole list
  }
}

export async function loadAllTodos() {
  const token = ++_todosLoadToken;
  todosLoading.set(true);
  todosError.set(null);
  allTodos.set([]); // clear up front so a reload never shows a stale mix of old + new
  const current = get(activeProject);
  const list = get(projects);
  const ordered = [
    ...(current ? [current] : []),
    ...list
      .filter(p => !current || p.filename !== current.filename)
      .sort((a, b) => a.name.localeCompare(b.name)),
  ];

  let nextIndex = 0;
  async function worker() {
    while (true) {
      if (token !== _todosLoadToken) return; // a newer load has since started — abandon this one
      const i = nextIndex++;
      if (i >= ordered.length) return;
      const project = ordered[i];
      await loadOneProjectGroup(project, project.filename === current?.filename, token);
    }
  }
  const workerCount = Math.min(TODOS_CONCURRENCY, ordered.length);
  await Promise.all(Array.from({ length: workerCount }, worker));

  if (token === _todosLoadToken) todosLoading.set(false);
}

// Each action reads the LATEST content immediately before writing (never trusts the
// in-memory `allTodos` copy), applies exactly one change, writes back, then refreshes
// just that project's group — so a concurrent edit from desktop is never blindly
// clobbered, and these stay simple discrete read-modify-write actions with no
// debouncing (unlike Notes' continuous-typing autosave, a toggle/rename/add is a single
// tap, not a keystroke stream).

export async function toggleTodoTask(project, lineIndex, text) {
  const cfg = await resolveProjectConfig(project);
  const slug = cfg.documents_subfolder;
  const content = await loadTodo(slug);
  await saveTodo(slug, toggleLine(content, lineIndex, text));
  return refreshOneGroup(project, slug);
}

export async function renameTodoTask(project, lineIndex, oldText, newText) {
  const cfg = await resolveProjectConfig(project);
  const slug = cfg.documents_subfolder;
  const content = await loadTodo(slug);
  await saveTodo(slug, renameLine(content, lineIndex, oldText, newText));
  return refreshOneGroup(project, slug);
}

// `project` may be the current one or an explicitly different one picked from the Add
// Task row's project <select> (falls back to the current project when left unset).
export async function addTodoTask(project, title) {
  const target = project || get(activeProject);
  const cfg = await resolveProjectConfig(target);
  const slug = cfg?.documents_subfolder;
  if (!slug) {
    throw new Error("This project has no documents folder yet — open it on desktop and use the Docs tab once first.");
  }
  const content = await loadTodo(slug);
  await saveTodo(slug, appendLine(content, title));
  return refreshOneGroup(target, slug);
}

// ── Tab ───────────────────────────────────────────────────────────────────────

export const activeTab = writable('launchers'); // 'launchers' | 'notes' | 'todos'

// ── Navigation UI state ─────────────────────────────────────────────────────
//
// Whether the left-edge project-switcher drawer (NavDrawer.svelte) is open —
// replaces the old top project-chip bar + "≡" ProjectPicker modal. A plain
// boolean store rather than component-local state so the bottom-nav hamburger
// button (in Main.svelte) and the drawer itself (which also self-closes on
// pick/backdrop-tap) can both read/write the same flag.
export const drawerOpen = writable(false);

// Bumped (not booled) each time the Todos FAB is tapped, so Todos.svelte's own
// focus-the-add-task-input effect fires again even on a second consecutive tap
// where a boolean toggle would otherwise look unchanged to a reactive block.
export const focusAddTaskSignal = writable(0);
export function requestFocusAddTask() {
  focusAddTaskSignal.update(n => n + 1);
}

// ── Share-to-app (Android ACTION_SEND) ──────────────────────────────────────────

const ADDED_RESOURCES_CATEGORY = 'Added Resources';

export const pendingShare = writable(null); // { text, subject } | { fileUri, fileName, mimeType } | null

export function initShareReceiver() {
  if (!Capacitor.isNativePlatform()) return;
  const ShareReceiver = registerPlugin('ShareReceiver');

  ShareReceiver.getSharedData().then(data => {
    if (data && (data.text || data.fileUri)) pendingShare.set(data);
  });

  ShareReceiver.addListener('shareReceived', data => {
    if (data && (data.text || data.fileUri)) pendingShare.set(data);
  });
}

export async function addLinkToProject(project, url, title) {
  const cfg = await loadProject(project.filename);
  if (!cfg.columns) cfg.columns = [[]];
  if (!cfg.columns[0]) cfg.columns[0] = [];

  let entry = cfg.columns[0].find(cat => Object.keys(cat)[0] === ADDED_RESOURCES_CATEGORY);
  if (!entry) {
    entry = { [ADDED_RESOURCES_CATEGORY]: [] };
    cfg.columns[0].push(entry);
  }
  entry[ADDED_RESOURCES_CATEGORY].push([title || url, url, 'browser']);

  await saveProjectConfig(project.filename, cfg);

  if (get(activeProject)?.filename === project.filename) {
    activeConfig.set(cfg);
  }
}

function shareTimestampHeader() {
  const d = new Date();
  const day = d.getDate();
  const suffix = (day % 10 === 1 && day !== 11) ? 'st'
    : (day % 10 === 2 && day !== 12) ? 'nd'
    : (day % 10 === 3 && day !== 13) ? 'rd' : 'th';
  const month = d.toLocaleDateString(undefined, { month: 'long' });
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
  return `${time} -- ${day}${suffix} ${month} ${d.getFullYear()} (via Share)`;
}

export async function addTextToProjectNote(project, text) {
  const nf = notesFilename(project.filename);
  const existing = await loadNote(nf);
  const separator = '-'.repeat(30);
  // The blank line before EACH separator below is load-bearing, not cosmetic: a line of
  // "---" immediately below a text line (no blank line between) is Markdown's SETEXT
  // HEADING underline syntax, not a horizontal rule — a real Markdown renderer (verified
  // against the actual synced note content) swallows a closing separator into a heading
  // for whatever text sits directly above it instead of showing it as its own divider.
  // The opening separator doesn't need this — it's always prepended at the very top of
  // the file, so there's never text directly above it to become a heading out of. The
  // closing separator (after `text`, before the old content) does need it, for the same
  // reason — added so the shared block reads as fully closed-off rather than running
  // straight into whatever note content already existed.
  const block = `${separator}\n${shareTimestampHeader()}\n\n${separator}\n\n${text}\n\n${separator}\n\n`;
  const newContent = existing ? `${block}${existing}` : block;

  await saveNote(nf, newContent);

  if (get(activeProject)?.filename === project.filename) {
    activeNote.set(newContent);
  }
}

const PROJECT_FILES_CATEGORY = 'Project Files';

// Uploads a file shared from another app (via the Android share sheet) into the chosen
// project's documents folder, then either references it as a plain note line or files it
// as a real launcher item — the user picks which, in ShareTarget.svelte, mirroring how a
// URL vs. plain text share already gets different treatment above.
//
// Deliberately never queued for offline retry, unlike addLinkToProject()/
// addTextToProjectNote() — the pending queue is a small localStorage-backed list of plain-
// text intents; a base64-encoded file body would bloat it far beyond what that mechanism
// was designed for. A genuine offline failure here just surfaces as an error to retry
// manually once reconnected.
export async function addFileToProject(project, fileUri, fileName, mimeType, asNote) {
  const ShareReceiver = registerPlugin('ShareReceiver');
  const { base64 } = await ShareReceiver.readSharedFile({ uri: fileUri });

  const cfg = await loadProject(project.filename);
  const relPath = await uploadDocumentToProject(cfg.documents_subfolder, fileName, base64, mimeType);

  if (asNote) {
    await addTextToProjectNote(project, `📎 Uploaded: ${fileName}`);
    return;
  }

  // ~/Nextcloud/ is the same zero-config prefix resolveToNextcloudRelPath() always
  // recognizes regardless of configured Nextcloud Locations, so the resulting launcher
  // item shows up as NC↗ immediately without depending on the user having a location row
  // that happens to match `documentsRoot`.
  const localPath = `~/Nextcloud/${relPath}`;
  if (!cfg.columns) cfg.columns = [[]];
  if (!cfg.columns[0]) cfg.columns[0] = [];
  let entry = cfg.columns[0].find(cat => Object.keys(cat)[0] === PROJECT_FILES_CATEGORY);
  if (!entry) {
    entry = { [PROJECT_FILES_CATEGORY]: [] };
    cfg.columns[0].push(entry);
  }
  entry[PROJECT_FILES_CATEGORY].push([fileName, localPath, 'default']);

  await saveProjectConfig(project.filename, cfg);

  if (get(activeProject)?.filename === project.filename) {
    activeConfig.set(cfg);
  }
}

// ── Desktop-only handler filter ───────────────────────────────────────────────

const DESKTOP_ONLY = new Set([
  'terminal','konsole','gnome-terminal','alacritty','kitty','foot','ghostty',
  'wezterm','terminator','tilix','xfce4-terminal','editor','code','kate',
  'gedit','mousepad','vim','nano','directorydev','dolphin_tabs','dolphin',
  'file_manager','nautilus','thunar','npm','ssh_session','ssh_cd_npm',
  'rsync_backup','tail_log',
]);

export function isMobileLauncher(handler, path) {
  if (typeof path === 'string' && /&&|\|\||;|^cd /.test(path)) return false;
  if (resolveToNextcloudRelPath(path)) return true; // accessible via Nextcloud web
  if (DESKTOP_ONLY.has(handler)) return false;
  return true;
}

export function getLaunchUrl(path, handler) {
  if (typeof path === 'string' && /^https?:\/\//.test(path)) return path;
  return null;
}
