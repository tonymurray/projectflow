import { writable, derived } from 'svelte/store';
import { setConfig, listProjects, loadProject, loadNote, saveNote, notesFilename, resolveToNextcloudRelPath } from './webdav.js';

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
    if (raw) return JSON.parse(raw);
  } catch {}
  return null;
}

export const config = writable(loadStoredConfig());

config.subscribe(cfg => {
  if (cfg) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg));
    setConfig(cfg);
  }
});

// ── Projects ──────────────────────────────────────────────────────────────────

export const projects = writable([]);
export const activeProject = writable(null);
export const activeConfig = writable(null);
export const loading = writable(false);
export const error = writable(null);

// Projects to show in the bar: pinned first, then recent (deduplicated), max 8 total
export const orderedProjects = derived(
  [projects, pinnedProjects, recentProjects],
  ([$projects, $pinned, $recent]) => {
    const byFilename = Object.fromEntries($projects.map(p => [p.filename, p]));
    const pinnedList = $pinned.map(f => byFilename[f]).filter(Boolean);
    const pinnedSet  = new Set($pinned);
    const recentList = $recent
      .filter(f => !pinnedSet.has(f))
      .map(f => byFilename[f])
      .filter(Boolean)
      .slice(0, 8 - pinnedList.length);
    return [...pinnedList, ...recentList];
  }
);

export async function fetchProjects() {
  loading.set(true);
  error.set(null);
  try {
    const list = await listProjects();
    projects.set(list);
    return list;
  } catch (e) {
    error.set(e.message);
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
  loading.set(true);
  error.set(null);
  try {
    const cfg = await loadProject(project.filename);
    activeConfig.set(cfg);
    // Load notes for this project
    const nf = notesFilename(project.filename);
    const note = await loadNote(nf);
    activeNote.set(note);
  } catch (e) {
    error.set(e.message);
  } finally {
    loading.set(false);
  }
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
  } catch (e) {
    error.set('Save failed: ' + e.message);
  }
}

// ── Tab ───────────────────────────────────────────────────────────────────────

export const activeTab = writable('launchers'); // 'launchers' | 'notes'

// ── Desktop-only handler filter ───────────────────────────────────────────────

const DESKTOP_ONLY = new Set([
  'terminal','konsole','gnome-terminal','alacritty','kitty','foot','ghostty',
  'wezterm','terminator','tilix','xfce4-terminal','editor','code','kate',
  'gedit','mousepad','vim','nano','directorydev','dolphin_tabs','dolphin',
  'file_manager','nautilus','thunar','npm','ssh_session','ssh_cd_npm',
  'rsync_backup','tail_log',
]);

export function isMobileLauncher(handler, path) {
  if (typeof path === 'string' && /&&|\|\|;|^cd /.test(path)) return false;
  if (resolveToNextcloudRelPath(path)) return true; // accessible via Nextcloud web
  if (DESKTOP_ONLY.has(handler)) return false;
  return true;
}

export function getLaunchUrl(path, handler) {
  if (typeof path === 'string' && /^https?:\/\//.test(path)) return path;
  return null;
}
