<script>
  import { createEventDispatcher } from 'svelte';
  import { setConfig, listProjects } from '../lib/webdav.js';
  import { precacheAllProjects } from '../lib/store.js';
  import QrScanner from './QrScanner.svelte';

  // The existing config to pre-fill from — null on first run (Setup.svelte), the current
  // $config object when revisiting (Settings.svelte). Shared by both so there is exactly
  // one place that knows the field set and the test-before-save logic.
  export let initial = null;

  const dispatch = createEventDispatcher();

  let server          = initial?.server          || '';
  let username        = initial?.username        || '';
  let password        = initial?.password        || '';
  let projectsPath    = initial?.projectsPath    || '';
  let notesPath       = initial?.notesPath       || '';
  let openMethod      = initial?.openMethod      || 'browser';
  let documentsRoot   = initial?.documentsRoot   || '';

  // Each row: a local filesystem path that's known to be synced into Nextcloud, plus the
  // Nextcloud-relative path it maps to. Leave "Nextcloud path" blank when the local folder
  // itself IS the root of your Nextcloud sync (the common "main path" case) — e.g.
  // /home/user/Nextcloud with a blank Nextcloud path. A folder that's a subfolder of your
  // Nextcloud sync (e.g. a documents/images folder the desktop app symlinks in) gets its
  // own row with the matching relative path, e.g. /home/user/Nextcloud/ProjectFlowDocuments
  // → "ProjectFlowDocuments".
  let locations = initial?.nextcloudLocations?.length
    ? initial.nextcloudLocations.map(l => ({ local: l.local || '', remote: l.remote || '' }))
    : [{ local: '', remote: '' }];

  let status       = '';
  let testing      = false;
  let scanning     = false;
  let showPassword = false;
  let caching      = false;
  let cacheStatus  = '';

  async function cacheAllNow() {
    caching = true;
    cacheStatus = 'Caching projects…';
    try {
      const { succeeded, failed, total } = await precacheAllProjects();
      cacheStatus = failed
        ? `Cached ${succeeded}/${total} — ${failed} failed (check connection)`
        : `✓ Cached all ${succeeded} project(s) for offline use`;
    } catch (e) {
      cacheStatus = `✗ ${e.message}`;
    } finally {
      caching = false;
    }
  }

  function addLocation() {
    locations = [...locations, { local: '', remote: '' }];
  }
  function removeLocation(i) {
    locations = locations.filter((_, idx) => idx !== i);
  }

  function onScanned(e) {
    server   = e.detail.server;
    username = e.detail.username;
    password = e.detail.password;
    scanning = false;
    status   = '✓ QR scanned — check folder paths then Connect';
  }

  async function testAndSave() {
    if (!server || !username || !password) {
      status = 'Fill in server, username, and password first.';
      return;
    }
    testing = true;
    status = 'Testing connection…';
    try {
      const nextcloudLocations = locations
        .map(l => ({ local: l.local.trim(), remote: l.remote.trim() }))
        .filter(l => l.local);
      const cfg = {
        server: server.replace(/\/$/, ''), username, password, projectsPath, notesPath,
        nextcloudLocations, openMethod, documentsRoot: documentsRoot.trim(),
      };
      setConfig(cfg);
      const projects = await listProjects();
      status = `✓ Connected — found ${projects.length} project(s)`;
      dispatch('save', cfg);
    } catch (e) {
      status = `✗ ${e.message}`;
    } finally {
      testing = false;
    }
  }
</script>

{#if scanning}
  <QrScanner on:scanned={onScanned} on:cancel={() => scanning = false} />
{/if}

<div class="form">
  <label>Server URL
    <input type="url" bind:value={server} placeholder="https://yourserver.example.com" />
  </label>
  <label>Username
    <input type="text" bind:value={username} autocomplete="off" />
  </label>
  <label>App Password
    <div class="pw-row">
      <input type={showPassword ? 'text' : 'password'} bind:value={password} autocomplete="off" />
      <button
        type="button"
        class="pw-toggle"
        on:click={() => showPassword = !showPassword}
        title={showPassword ? 'Hide password' : 'Show password'}
      >{showPassword ? '🙈' : '👁'}</button>
    </div>
    <span class="hint">Nextcloud → Settings → Security → App passwords</span>
    <button type="button" class="qr-btn" on:click={() => scanning = true}>Scan QR Code</button>
  </label>
  <label>Projects folder path
    <input type="text" bind:value={projectsPath} placeholder="ProjectFlow" />
    <span class="hint">Folder containing your .json project files</span>
  </label>
  <label>Notes folder path
    <input type="text" bind:value={notesPath} placeholder="Notes/@Project Notes" />
    <span class="hint">Folder containing your .md notes files</span>
  </label>

  <div class="advanced">
    <h2>Advanced: Nextcloud Locations <span class="opt">(optional)</span></h2>
    <p class="hint block">
      Register local folders on your desktop/laptop that are synced into Nextcloud, so
      launcher items pointing into them show up here as "Open in Nextcloud" instead of
      "desktop only". Leave a row's Nextcloud path blank if that local folder IS the root
      of your Nextcloud sync.
    </p>
    {#each locations as loc, i}
      <div class="loc-group">
        <label class="loc-field">Local path
          <input type="text" bind:value={loc.local} placeholder="/home/user/Nextcloud" />
        </label>
        <label class="loc-field">Nextcloud path
          <input type="text" bind:value={loc.remote} placeholder="(blank = root)" />
        </label>
        <button type="button" class="remove-btn" on:click={() => removeLocation(i)}>✕ Remove this location</button>
      </div>
    {/each}
    <button type="button" class="add-btn" on:click={addLocation}>＋ Add another location</button>
  </div>

  <div class="advanced">
    <h2>Advanced: Documents folder <span class="opt">(optional)</span></h2>
    <p class="hint block">
      Nextcloud-relative path where the desktop app's project documents live (its own
      Documents Folder feature). Needed to upload a file shared from another app into a
      project — see the Share flow.
    </p>
    <input type="text" bind:value={documentsRoot} placeholder="ProjectFlowDocuments" />
  </div>

  <div class="advanced">
    <h2>Advanced: File opening method <span class="opt">(optional)</span></h2>
    <label class="inline">
      <select bind:value={openMethod}>
        <option value="browser">Browser (default)</option>
        <option value="nextcloud-app">Nextcloud App (experimental)</option>
      </select>
    </label>
    <p class="hint block">
      "Nextcloud App" attempts to open the file directly in the Nextcloud Android app
      instead of the web Files UI in your browser. This isn't officially supported by
      Nextcloud and may not work with every server or app version — it automatically falls
      back to Browser whenever it doesn't work, so it's safe to try.
    </p>
  </div>

  <div class="advanced">
    <h2>Advanced: Offline Cache <span class="opt">(optional)</span></h2>
    <p class="hint block">
      Saves a local copy of every project's data and notes, so they're still readable if
      you lose connectivity. Whatever you open normally gets cached automatically too —
      this just does all of them in one go, ahead of time.
    </p>
    <button type="button" class="add-btn" on:click={cacheAllNow} disabled={caching}>
      {caching ? 'Caching…' : '⬇ Cache all projects now'}
    </button>
    {#if cacheStatus}
      <p class="hint block">{cacheStatus}</p>
    {/if}
  </div>

  <button type="button" on:click={testAndSave} disabled={testing}>
    {testing ? 'Connecting…' : 'Connect & Save'}
  </button>

  {#if status}
    <p class="status" class:ok={status.startsWith('✓')} class:err={status.startsWith('✗')}>
      {status}
    </p>
  {/if}
</div>

<style>
  .form { width: 100%; max-width: 440px; display: flex; flex-direction: column; gap: 16px; }
  label {
    display: flex; flex-direction: column; gap: 4px;
    font-size: 0.85rem; color: var(--t-muted);
  }
  label.inline { flex-direction: row; align-items: center; gap: 8px; }
  input, select {
    background: var(--bg-card); border: 1px solid var(--bd); border-radius: 6px;
    color: var(--t-primary); padding: 10px 12px; font-size: 0.95rem;
  }
  input:focus, select:focus { outline: none; border-color: var(--accent); }
  .pw-row { display: flex; gap: 6px; align-items: stretch; }
  .pw-row input { flex: 1; min-width: 0; }
  .pw-toggle {
    flex-shrink: 0; background: var(--bg-card); border: 1px solid var(--bd);
    border-radius: 6px; padding: 0 12px; font-size: 1.1rem; margin-top: 0;
  }
  .hint { font-size: 0.75rem; color: var(--t-dim); }
  .hint.block { margin: 0 0 4px; }
  .opt  { font-size: 0.72rem; color: var(--t-ghost); font-weight: normal; }
  button {
    background: var(--bg-active); color: var(--t-active); border: 1px solid var(--bd-active);
    border-radius: 6px; padding: 12px; font-size: 1rem; margin-top: 8px;
  }
  button:hover:not(:disabled) { background: var(--bg-active-hi); }
  button:disabled { opacity: 0.5; }
  .qr-btn {
    margin-top: 6px; padding: 8px 12px; font-size: 0.85rem;
    align-self: flex-start;
  }
  .status { font-size: 0.9rem; padding: 8px 12px; border-radius: 6px; background: var(--bg-card); }
  .ok  { color: var(--t-saved); }
  .err { color: var(--t-error); }

  .advanced {
    border-top: 1px solid var(--bd-sub);
    padding-top: 14px;
    display: flex; flex-direction: column; gap: 8px;
  }
  .advanced h2 {
    font-size: 0.85rem; color: var(--t-muted); margin: 0;
    display: flex; align-items: center; gap: 6px;
  }
  .loc-group {
    display: flex; flex-direction: column; gap: 8px;
  }
  .loc-group + .loc-group {
    border-top: 1px solid var(--bd-sub);
    padding-top: 12px;
    margin-top: 4px;
  }
  .loc-field {
    display: flex; flex-direction: column; gap: 4px;
    font-size: 0.78rem; color: var(--t-dim);
  }
  .loc-field input { font-size: 0.9rem; padding: 8px 10px; }
  .remove-btn {
    align-self: flex-start; background: none; border: 1px solid var(--bd);
    border-radius: 6px; padding: 6px 10px; font-size: 0.78rem; margin-top: 0; color: var(--t-error);
  }
  .add-btn {
    align-self: flex-start; padding: 8px 12px; font-size: 0.85rem; margin-top: 0;
  }
</style>
