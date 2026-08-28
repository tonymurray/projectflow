/**
 * Minimal WebDAV client for Nextcloud.
 * On Android/Capacitor, uses a native OkHttp plugin to support PROPFIND and bypass CORS.
 * In the browser, falls back to regular fetch (use the local proxy for CORS).
 */

import { Capacitor, registerPlugin } from '@capacitor/core';

const WebDav = registerPlugin('WebDav');

let _config = null;

export function setConfig(cfg) {
  _config = cfg;
}

export function getConfig() {
  return _config;
}

function authHeader() {
  return 'Basic ' + btoa(`${_config.username}:${_config.password}`);
}

function encodePath(p) {
  return p.split('/').map(s => encodeURIComponent(s).replace(/%40/g, '@')).join('/');
}

function projectsBase() {
  const root = `${_config.server}/remote.php/dav/files/${encodeURIComponent(_config.username)}`;
  return _config.projectsPath ? `${root}/${encodePath(_config.projectsPath)}` : root;
}

function notesBase() {
  const root = `${_config.server}/remote.php/dav/files/${encodeURIComponent(_config.username)}`;
  return _config.notesPath ? `${root}/${encodePath(_config.notesPath)}` : root;
}

async function request(method, url, body = null, extraHeaders = {}) {
  const headers = { Authorization: authHeader(), ...extraHeaders };
  if (body !== null) headers['Content-Type'] = 'text/plain; charset=utf-8';

  if (Capacitor.isNativePlatform()) {
    const result = await WebDav.request({ method, url, headers, body: body ?? undefined });
    return {
      ok: result.status >= 200 && result.status < 300,
      status: result.status,
      text: async () => result.data,
      json: async () => JSON.parse(result.data),
    };
  }

  return fetch(url, { method, headers, body });
}

// ── Projects ──────────────────────────────────────────────────────────────────

export async function listProjects() {
  const url = projectsBase();
  const res = await request('PROPFIND', url, null, { Depth: '1' });
  if (!res.ok) throw new Error(`PROPFIND ${res.status}`);
  const xml = await res.text();
  return parseProjectList(xml);
}

function parseProjectList(xml) {
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  return [...doc.querySelectorAll('response')]
    .filter(r => {
      const href = r.querySelector('href')?.textContent || '';
      const isDir = r.querySelector('resourcetype collection') !== null;
      return !isDir && href.endsWith('.json') && !href.includes('.projectflow_settings');
    })
    .map(r => {
      const href = r.querySelector('href')?.textContent || '';
      const filename = decodeURIComponent(href.split('/').pop());
      const name = filename.replace(/\.json$/, '').replace(/[_-]/g, ' ');
      return { filename, name, href };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

export async function loadProject(filename) {
  const url = `${projectsBase()}/${encodeURIComponent(filename)}`;
  const res = await request('GET', url);
  if (!res.ok) throw new Error(`GET ${res.status}`);
  return await res.json();
}

export async function saveProjectConfig(filename, config) {
  const url = `${projectsBase()}/${encodeURIComponent(filename)}`;
  const res = await request('PUT', url, JSON.stringify(config, null, 2));
  if (!res.ok) throw new Error(`PUT ${res.status}`);
  return true;
}

// ── Notes ─────────────────────────────────────────────────────────────────────

export function notesFilename(projectFilename) {
  return projectFilename.replace(/\.json$/, '.md').replace(/_/g, '-');
}

export function notesHtmlFilename(projectFilename) {
  return projectFilename.replace(/\.json$/, '.html').replace(/_/g, '-');
}

export async function loadNote(filename) {
  const url = `${notesBase()}/${encodeURIComponent(filename)}`;
  const res = await request('GET', url);
  if (res.status === 404) return '';
  if (!res.ok) throw new Error(`GET ${res.status}`);
  return await res.text();
}

export async function loadHtml(filename) {
  const url = `${notesBase()}/${encodeURIComponent(filename)}`;
  const res = await request('GET', url);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`GET ${res.status}`);
  return await res.text();
}

// Load a file from the project's own subfolder (e.g. cop/ for cop.json)
export async function loadFromProjectFolder(projectFilename, docFilename) {
  const name = projectFilename.replace(/\.json$/, '');
  const url = `${projectsBase()}/${encodePath(name)}/${encodeURIComponent(docFilename)}`;
  const res = await request('GET', url);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`GET ${res.status}`);
  return await res.text();
}

export async function saveNote(filename, content) {
  const url = `${notesBase()}/${encodeURIComponent(filename)}`;
  const res = await request('PUT', url, content);
  if (!res.ok) throw new Error(`PUT ${res.status}`);
  return true;
}

// ── Settings (optional — for project ordering) ────────────────────────────────

export async function loadSettings() {
  try {
    const url = `${projectsBase()}/.projectflow_settings.json`;
    const res = await request('GET', url);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

// ── Local-path → Nextcloud resolution ─────────────────────────────────────────

/**
 * Given a local filesystem path from a project config, attempt to resolve it
 * to a Nextcloud-relative path (relative to the NC root, e.g. "Projects/cop/guide.md").
 *
 * Handles two cases:
 *   1. The path literally contains /Nextcloud/ (e.g. ~/Nextcloud/Projects/cop/guide.md)
 *   2. An optional configured alias (e.g. ~/Projects → Nextcloud path "Projects")
 *      for symlinks that don't contain "Nextcloud" in the path.
 *
 * Returns null if the path cannot be resolved.
 */
export function resolveToNextcloudRelPath(localPath) {
  if (!localPath || typeof localPath !== 'string') return null;
  if (/^https?:\/\//.test(localPath)) return null;
  if (/&&|\|\||;|^cd /.test(localPath)) return null;

  const path = localPath.trim();

  // ~/Nextcloud/...
  if (path.startsWith('~/Nextcloud/')) {
    return path.slice('~/Nextcloud/'.length);
  }

  // /anything/Nextcloud/...
  const absMatch = path.match(/\/Nextcloud\/(.+)$/);
  if (absMatch) return absMatch[1];

  // Configured alias for symlinks (e.g. ~/Projects alias → NC path "Projects")
  if (_config?.localAlias && _config?.nextcloudAlias) {
    const alias = _config.localAlias.replace(/\/$/, '');
    if (path === alias || path.startsWith(alias + '/')) {
      const rest = path.slice(alias.length).replace(/^\//, '');
      const ncBase = _config.nextcloudAlias.replace(/^\//, '').replace(/\/$/, '');
      return rest ? `${ncBase}/${rest}` : ncBase;
    }
  }

  return null;
}

// Build a Nextcloud web-UI URL that opens the folder containing the given NC-relative path.
// e.g. "Projects/cop/guide.pdf" → "{server}/apps/files/?dir=/Projects/cop"
export function nextcloudWebUrl(relPath) {
  if (!_config) return null;
  const parts = relPath.split('/');
  const dir = parts.length > 1 ? parts.slice(0, -1).join('/') : '';
  return `${_config.server}/apps/files/?dir=/${encodePath(dir)}`;
}
