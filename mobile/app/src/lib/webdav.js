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

// ── Notes ─────────────────────────────────────────────────────────────────────

export function notesFilename(projectFilename) {
  return projectFilename.replace(/\.json$/, '.md');
}

export async function loadNote(filename) {
  const url = `${notesBase()}/${encodeURIComponent(filename)}`;
  const res = await request('GET', url);
  if (res.status === 404) return '';
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
