import { writable, derived, get } from 'svelte/store';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { Network } from '@capacitor/network';
import { setConfig, listProjects, loadProject, saveProjectConfig, loadNote, saveNote, notesFilename, resolveToNextcloudRelPath, uploadDocumentToProject, isOfflineish, NetworkError } from './webdav.js';
import { cacheProject, getCachedProject, cacheNote, getCachedNote } from './cache.js';

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

// Fetches and caches every known project's config + notes in one pass, so they're all
// available offline afterward — not just whichever ones happen to have been opened this
// session. Sequential rather than parallel, deliberately: this is a manual, occasional
// "get ready to go offline" action (triggered from Settings), not something latency-
// sensitive, and sequential avoids firing a burst of concurrent requests at the server.
// Skips past any individual project's failure and keeps going with the rest.
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

// ── Tab ───────────────────────────────────────────────────────────────────────

export const activeTab = writable('launchers'); // 'launchers' | 'notes'

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
