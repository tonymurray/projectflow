import { writable, derived, get } from 'svelte/store';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { setConfig, listProjects, loadProject, saveProjectConfig, loadNote, saveNote, notesFilename, resolveToNextcloudRelPath } from './webdav.js';

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

// ── Share-to-app (Android ACTION_SEND) ──────────────────────────────────────────

const ADDED_RESOURCES_CATEGORY = 'Added Resources';

export const pendingShare = writable(null); // { text, subject } | null

export function initShareReceiver() {
  if (!Capacitor.isNativePlatform()) return;
  const ShareReceiver = registerPlugin('ShareReceiver');

  ShareReceiver.getSharedData().then(data => {
    if (data && data.text) pendingShare.set(data);
  });

  ShareReceiver.addListener('shareReceived', data => {
    if (data && data.text) pendingShare.set(data);
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
  const block = `${separator}\n${shareTimestampHeader()}\n${separator}\n\n${text}\n\n`;
  const newContent = existing ? `${block}\n${existing}` : block;

  await saveNote(nf, newContent);

  if (get(activeProject)?.filename === project.filename) {
    activeNote.set(newContent);
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
  if (typeof path === 'string' && /&&|\|\|;|^cd /.test(path)) return false;
  if (resolveToNextcloudRelPath(path)) return true; // accessible via Nextcloud web
  if (DESKTOP_ONLY.has(handler)) return false;
  return true;
}

export function getLaunchUrl(path, handler) {
  if (typeof path === 'string' && /^https?:\/\//.test(path)) return path;
  return null;
}
