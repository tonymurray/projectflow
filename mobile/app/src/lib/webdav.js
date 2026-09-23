/**
 * Minimal WebDAV client for Nextcloud.
 * On Android/Capacitor, uses a native OkHttp plugin to support PROPFIND and bypass CORS.
 * In the browser, falls back to regular fetch (use the local proxy for CORS).
 */

import { Capacitor, registerPlugin } from '@capacitor/core';

const WebDav = registerPlugin('WebDav');

// Typed errors so callers can tell "never reached the server" (NetworkError) apart from
// "server responded, but with an error status" (HttpError) without parsing message strings.
export class HttpError extends Error {
  constructor(status, method) {
    super(`${method} ${status}`);
    this.name = 'HttpError';
    this.status = status;
  }
}

export class NetworkError extends Error {
  constructor(message) {
    super(message || 'Network request failed');
    this.name = 'NetworkError';
  }
}

// Statuses worth treating the same as "offline" for retry purposes — the server responded,
// but only to say it's temporarily unable to help (Nextcloud's 423 Locked during sync, plus
// the standard "busy/unavailable, try again" statuses). Everything else (401, 404, 400, ...)
// is a real error that needs different user action than "wait and retry."
const RETRYABLE_STATUSES = new Set([429, 502, 503, 504, 423]);

export function isOfflineish(err) {
  if (err instanceof NetworkError) return true;
  if (err instanceof HttpError) return RETRYABLE_STATUSES.has(err.status);
  return false;
}

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

// bodyBase64 is for binary uploads (documents/images) — a plain JS string can't safely
// carry arbitrary bytes across the native bridge or through fetch(), so binary content is
// always base64-encoded by the caller and decoded back to real bytes here.
async function request(method, url, body = null, extraHeaders = {}, bodyBase64 = null) {
  const headers = { Authorization: authHeader() };
  if (body !== null) headers['Content-Type'] = 'text/plain; charset=utf-8';
  Object.assign(headers, extraHeaders); // extraHeaders can override the default above (e.g. a PROPFIND body that isn't plain text)

  try {
    if (Capacitor.isNativePlatform()) {
      const result = await WebDav.request({
        method, url, headers,
        body: body ?? undefined,
        bodyBase64: bodyBase64 ?? undefined,
      });
      return {
        ok: result.status >= 200 && result.status < 300,
        status: result.status,
        text: async () => result.data,
        json: async () => JSON.parse(result.data),
      };
    }

    const fetchBody = bodyBase64 != null ? base64ToBlob(bodyBase64, headers['Content-Type']) : body;
    return await fetch(url, { method, headers, body: fetchBody });
  } catch (e) {
    // Native plugin promise rejection (DNS/timeout/no route — OkHttp only rejects on a
    // real IOException, never on a plain HTTP error status) or the browser fetch()
    // throwing (e.g. "TypeError: Failed to fetch") both mean the same thing: we never
    // got a response at all.
    throw new NetworkError(e.message);
  }
}

function base64ToBlob(base64, contentType) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: contentType || 'application/octet-stream' });
}

// ── Projects ──────────────────────────────────────────────────────────────────

export async function listProjects() {
  const url = projectsBase();
  const res = await request('PROPFIND', url, null, { Depth: '1' });
  if (!res.ok) throw new HttpError(res.status, 'PROPFIND');
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
  if (!res.ok) throw new HttpError(res.status, 'GET');
  return await res.json();
}

export async function saveProjectConfig(filename, config) {
  const url = `${projectsBase()}/${encodeURIComponent(filename)}`;
  const res = await request('PUT', url, JSON.stringify(config, null, 2));
  if (!res.ok) throw new HttpError(res.status, 'PUT');
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
  if (!res.ok) throw new HttpError(res.status, 'GET');
  return await res.text();
}

export async function loadHtml(filename) {
  const url = `${notesBase()}/${encodeURIComponent(filename)}`;
  const res = await request('GET', url);
  if (res.status === 404) return null;
  if (!res.ok) throw new HttpError(res.status, 'GET');
  return await res.text();
}

// Load a file from the project's own subfolder (e.g. cop/ for cop.json)
export async function loadFromProjectFolder(projectFilename, docFilename) {
  const name = projectFilename.replace(/\.json$/, '');
  const url = `${projectsBase()}/${encodePath(name)}/${encodeURIComponent(docFilename)}`;
  const res = await request('GET', url);
  if (res.status === 404) return null;
  if (!res.ok) throw new HttpError(res.status, 'GET');
  return await res.text();
}

export async function saveNote(filename, content) {
  const url = `${notesBase()}/${encodeURIComponent(filename)}`;
  const res = await request('PUT', url, content);
  if (!res.ok) throw new HttpError(res.status, 'PUT');
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
 *      — a zero-config fallback that always applies, regardless of configured locations.
 *   2. Any number of configured Nextcloud locations (Settings → Advanced) — the main
 *      Nextcloud path plus any additional folders symlinked in from elsewhere (e.g. the
 *      desktop app's documents/images folders), for paths that don't literally contain
 *      "Nextcloud". The longest matching local path wins, so a more specific location
 *      (e.g. .../ProjectFlowDocuments) is preferred over a broader one that also covers
 *      the same file (e.g. the main Nextcloud path).
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

  // Configured Nextcloud locations
  const locations = Array.isArray(_config?.nextcloudLocations) ? _config.nextcloudLocations : [];
  const matches = locations
    .filter(loc => loc?.local)
    .map(loc => ({
      local: loc.local.replace(/\/$/, ''),
      remote: (loc.remote || '').replace(/^\//, '').replace(/\/$/, ''),
    }))
    .filter(loc => path === loc.local || path.startsWith(loc.local + '/'))
    .sort((a, b) => b.local.length - a.local.length);

  if (matches.length) {
    const { local, remote } = matches[0];
    const rest = path.slice(local.length).replace(/^\//, '');
    return rest ? (remote ? `${remote}/${rest}` : rest) : remote;
  }

  return null;
}

// Build a Nextcloud web-UI URL that opens the folder containing the given NC-relative path
// — or, when a fileId is supplied (see getNextcloudFileId below), Nextcloud's own
// file-scoped URL that opens straight to that file within the folder view instead of just
// the bare folder. e.g. "Projects/cop/guide.pdf" → "{server}/apps/files/?dir=/Projects/cop",
// or with fileId 4934534 → "{server}/apps/files/files/4934534?dir=/Projects/cop"
export function nextcloudWebUrl(relPath, fileId = null) {
  if (!_config) return null;
  const parts = relPath.split('/');
  const dir = parts.length > 1 ? parts.slice(0, -1).join('/') : '';
  const dirParam = `dir=/${encodePath(dir)}`;
  return fileId
    ? `${_config.server}/apps/files/files/${fileId}?${dirParam}`
    : `${_config.server}/apps/files/?${dirParam}`;
}

// ── Nextcloud file ID lookup (experimental "open in Nextcloud app" toggle) ─────────────

// Requests Nextcloud's own oc:fileid WebDAV property for a single file, used to build a
// "direct link" URL the Nextcloud Android app can open directly. Best-effort only: any
// failure (property missing, request error, 404) returns null rather than throwing — this
// is purely an optional shortcut, always paired with a browser-based fallback by the caller.
const FILEID_PROPFIND_BODY = `<?xml version="1.0"?>
<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
  <d:prop><oc:fileid/></d:prop>
</d:propfind>`;

export async function getNextcloudFileId(relPath) {
  if (!_config || !relPath) return null;
  try {
    const root = `${_config.server}/remote.php/dav/files/${encodeURIComponent(_config.username)}`;
    const url = `${root}/${encodePath(relPath)}`;
    const res = await request('PROPFIND', url, FILEID_PROPFIND_BODY, {
      Depth: '0',
      'Content-Type': 'application/xml; charset=utf-8',
    });
    if (!res.ok) return null;
    const xml = await res.text();
    const doc = new DOMParser().parseFromString(xml, 'application/xml');
    const idEl = doc.getElementsByTagNameNS('http://owncloud.org/ns', 'fileid')[0];
    return idEl?.textContent?.trim() || null;
  } catch {
    return null;
  }
}

// ── Documents (file-share uploads) ──────────────────────────────────────────────────

// Uploads a shared file into a project's documents folder — resolved from the global
// `documentsRoot` setting (Settings → Advanced → Documents folder) plus the project's own
// `documents_subfolder` field. That field is written by the desktop app's Documents Folder
// feature (a slugified, collision-checked-against-every-other-project name) — mobile has no
// reliable way to invent an equally collision-safe slug of its own, so a project that
// hasn't used that feature on desktop yet is a hard error here rather than a guess. Neither
// documentsRoot nor documents_subfolder's target folder is created if missing — this
// deliberately never invents new canonical structure, only uploads into what already exists.
export async function uploadDocumentToProject(documentsSubfolder, filename, base64Data, mimeType) {
  if (!_config?.documentsRoot) {
    throw new Error('No Documents folder configured — set one in Settings → Advanced.');
  }
  if (!documentsSubfolder) {
    throw new Error("This project has no documents folder yet — open it on desktop and use the Docs tab once first.");
  }
  const root = `${_config.server}/remote.php/dav/files/${encodeURIComponent(_config.username)}`;
  const docsRoot = _config.documentsRoot.replace(/^\//, '').replace(/\/$/, '');
  const relPath = `${docsRoot}/${documentsSubfolder}/${filename}`;
  const url = `${root}/${encodePath(relPath)}`;
  const res = await request('PUT', url, null, { 'Content-Type': mimeType || 'application/octet-stream' }, base64Data);
  if (!res.ok) throw new HttpError(res.status, 'PUT');
  return relPath;
}
