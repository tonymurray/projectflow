<script>
  import { config } from '../lib/store.js';
  import { setConfig, listProjects } from '../lib/webdav.js';
  import QrScanner from './QrScanner.svelte';

  let server       = $config?.server       || '';
  let username     = $config?.username     || '';
  let password     = $config?.password     || '';
  let projectsPath = $config?.projectsPath || '';
  let notesPath    = $config?.notesPath    || '';
  let status       = '';
  let testing      = false;
  let scanning     = false;

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
      setConfig({ server: server.replace(/\/$/, ''), username, password, projectsPath, notesPath });
      const projects = await listProjects();
      status = `✓ Connected — found ${projects.length} project(s)`;
      config.set({ server: server.replace(/\/$/, ''), username, password, projectsPath, notesPath });
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
      <input type="password" bind:value={password} autocomplete="off" />
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
  h1 { font-size: 1.8rem; color: #7eb8f7; margin-bottom: 4px; }
  .sub { color: #888; margin-bottom: 32px; font-size: 0.9rem; }
  .form { width: 100%; max-width: 440px; display: flex; flex-direction: column; gap: 16px; }
  label {
    display: flex; flex-direction: column; gap: 4px;
    font-size: 0.85rem; color: #aaa;
  }
  input {
    background: #1a1d26; border: 1px solid #2e3244; border-radius: 6px;
    color: #e0e0e0; padding: 10px 12px; font-size: 0.95rem;
  }
  input:focus { outline: none; border-color: #4a7fc1; }
  .hint { font-size: 0.75rem; color: #666; }
  button {
    background: #253553; color: #c8ddf7; border: 1px solid #3a5580;
    border-radius: 6px; padding: 12px; font-size: 1rem; margin-top: 8px;
  }
  button:hover:not(:disabled) { background: #2f4470; }
  button:disabled { opacity: 0.5; }
  .qr-btn {
    margin-top: 6px; padding: 8px 12px; font-size: 0.85rem;
    align-self: flex-start;
  }
  .status { font-size: 0.9rem; padding: 8px 12px; border-radius: 6px; background: #1a1d26; }
  .ok  { color: #6fcf97; }
  .err { color: #eb5757; }
</style>
