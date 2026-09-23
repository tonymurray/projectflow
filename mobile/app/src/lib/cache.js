/**
 * Local read-through cache for project configs and notes, so previously-loaded content
 * stays available when offline. Uses Capacitor's Filesystem plugin against Directory.Data
 * — app-private storage that needs no manifest permissions on any Android version, unlike
 * Directory.Documents/ExternalStorage (which are also either permission-gated or, on
 * Android 11+, not accessible at all).
 *
 * Deliberately network-first, cache-as-fallback only — store.js only ever reads from here
 * after a genuine offline failure, never in preference to a fresh network response. Each
 * entry is wrapped with a cachedAt timestamp so the UI can show how stale a fallback copy
 * is, rather than presenting it as indistinguishable from live data.
 */

import { Filesystem, Directory, Encoding } from '@capacitor/filesystem';

const PROJECTS_DIR = 'projects-cache';
const NOTES_DIR = 'notes-cache';

async function writeEnvelope(dir, filename, data) {
  try {
    await Filesystem.writeFile({
      path: `${dir}/${filename}`,
      data: JSON.stringify({ cachedAt: Date.now(), data }),
      directory: Directory.Data,
      encoding: Encoding.UTF8,
      recursive: true,
    });
  } catch {
    // Best-effort — a failed cache write must never break the caller's own success path
    // (e.g. a full disk, or a filename with characters the filesystem dislikes).
  }
}

async function readEnvelope(dir, filename) {
  try {
    const { data } = await Filesystem.readFile({
      path: `${dir}/${filename}`,
      directory: Directory.Data,
      encoding: Encoding.UTF8,
    });
    return JSON.parse(data); // { cachedAt, data }
  } catch {
    return null; // no cached copy yet — genuinely absent, not a real error worth surfacing
  }
}

export function cacheProject(filename, projectData) {
  return writeEnvelope(PROJECTS_DIR, filename, projectData);
}

export function getCachedProject(filename) {
  return readEnvelope(PROJECTS_DIR, filename);
}

export function cacheNote(filename, text) {
  return writeEnvelope(NOTES_DIR, filename, text);
}

export function getCachedNote(filename) {
  return readEnvelope(NOTES_DIR, filename);
}
