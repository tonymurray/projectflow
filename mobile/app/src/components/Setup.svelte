<script>
  import { config } from '../lib/store.js';
  import { setConfig, listProjects } from '../lib/webdav.js';
  import QrScanner from './QrScanner.svelte';

  let server          = $config?.server          || '';
  let username        = $config?.username        || '';
  let password        = $config?.password        || '';
  let projectsPath    = $config?.projectsPath    || '';
  let notesPath       = $config?.notesPath       || '';
  let localAlias      = $config?.localAlias      || '';
  let nextcloudAlias  = $config?.nextcloudAlias  || '';
  let status       = '';
  let testing      = false;
  let scanning     = false;
  let showPassword = false;

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
      const cfg = { server: server.replace(/\/$/, ''), username, password, projectsPath, notesPath,
                    localAlias: localAlias.trim(), nextcloudAlias: nextcloudAlias.trim() };
      setConfig(cfg);
      const projects = await listProjects();
      status = `✓ Connected — found ${projects.length} project(s)`;
      config.set(cfg);
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

<div class="setup">
  <h1>ProjectFlow</h1>
  <p class="sub">Connect to your Nextcloud</p>

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
      <button class="qr-btn" on:click={() => scanning = true}>Scan QR Code</button>
    </label>
    <label>Projects folder path
      <input type="text" bind:value={projectsPath} placeholder="ProjectFlow" />
      <span class="hint">Folder containing your .json project files</span>
    </label>
    <label>Notes folder path
      <input type="text" bind:value={notesPath} placeholder="Notes/@Project Notes" />
      <span class="hint">Folder containing your .md notes files</span>
    </label>
    <label>Local path prefix <span class="opt">(optional)</span>
      <input type="text" bind:value={localAlias} placeholder="~/Projects" />
      <span class="hint">If a local path is symlinked into Nextcloud (e.g. ~/Projects → ~/Nextcloud/Projects), enter the local prefix here</span>
    </label>
    <label>Nextcloud path for that prefix <span class="opt">(optional)</span>
      <input type="text" bind:value={nextcloudAlias} placeholder="Projects" />
      <span class="hint">Nextcloud root-relative path the above prefix resolves to</span>
    </label>

    <button on:click={testAndSave} disabled={testing}>
      {testing ? 'Connecting…' : 'Connect & Save'}
    </button>

    {#if status}
      <p class="status" class:ok={status.startsWith('✓')} class:err={status.startsWith('✗')}>
        {status}
      </p>
    {/if}
  </div>
</div>

<style>
  .setup {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 40px 24px;
    min-height: 100dvh;
  }
  h1 { font-size: 1.8rem; color: var(--accent-hi); margin-bottom: 4px; }
  .sub { color: var(--t-faint); margin-bottom: 32px; font-size: 0.9rem; }
  .form { width: 100%; max-width: 440px; display: flex; flex-direction: column; gap: 16px; }
  label {
    display: flex; flex-direction: column; gap: 4px;
    font-size: 0.85rem; color: var(--t-muted);
  }
  input {
    background: var(--bg-card); border: 1px solid var(--bd); border-radius: 6px;
    color: var(--t-primary); padding: 10px 12px; font-size: 0.95rem;
  }
  input:focus { outline: none; border-color: var(--accent); }
  .pw-row { display: flex; gap: 6px; align-items: stretch; }
  .pw-row input { flex: 1; min-width: 0; }
  .pw-toggle {
    flex-shrink: 0; background: var(--bg-card); border: 1px solid var(--bd);
    border-radius: 6px; padding: 0 12px; font-size: 1.1rem; margin-top: 0;
  }
  .hint { font-size: 0.75rem; color: var(--t-dim); }
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
</style>
