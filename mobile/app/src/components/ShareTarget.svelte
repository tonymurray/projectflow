<script>
  import { createEventDispatcher } from 'svelte';
  import { get } from 'svelte/store';
  import { projects, activeProject, offline, addLinkToProject, addTextToProjectNote, addFileToProject, queueOperation } from '../lib/store.js';
  import { isOfflineish, NetworkError } from '../lib/webdav.js';

  export let share; // { text, subject } | { fileUri, fileName, mimeType }

  const dispatch = createEventDispatcher();

  $: isFile = !!share.fileUri;
  $: sorted = [...$projects].sort((a, b) => a.name.localeCompare(b.name));
  $: trimmed = (share.text || '').trim();
  $: isUrl = !isFile && /^https?:\/\/\S+$/.test(trimmed);
  $: preview = trimmed.length > 220 ? trimmed.slice(0, 220) + '…' : trimmed;

  let selected = $activeProject;
  let busy = false;
  let done = false;
  let queued = false;
  let errorMsg = null;
  let asNote = false; // file shares only: false = add as a launcher, true = reference in note

  function onBackdrop(e) {
    if (e.target === e.currentTarget && !busy) dispatch('close');
  }

  async function add() {
    if (!selected || busy) return;
    busy = true;
    errorMsg = null;

    if (isFile) {
      try {
        // Already known offline — skip the doomed attempt and fail fast with a clear
        // message. Unlike link/text shares, a file upload is never queued for later retry
        // (see addFileToProject()'s own comment on why) — just try again once reconnected.
        if (get(offline)) throw new NetworkError('offline');
        await addFileToProject(selected, share.fileUri, share.fileName || 'shared-file', share.mimeType, asNote);
        done = true;
      } catch (e) {
        errorMsg = e.message;
      } finally {
        busy = false;
      }
      if (done) setTimeout(() => dispatch('close'), 900);
      return;
    }

    const op = isUrl
      ? { type: 'link', projectFilename: selected.filename, projectName: selected.name, url: trimmed, title: share.subject }
      : { type: 'note', projectFilename: selected.filename, projectName: selected.name, text: trimmed };
    try {
      // Already known offline — skip the doomed attempt/timeout and queue right away.
      if (get(offline)) throw new NetworkError('offline');
      if (isUrl) {
        await addLinkToProject(selected, trimmed, share.subject);
      } else {
        await addTextToProjectNote(selected, trimmed);
      }
      done = true;
    } catch (e) {
      if (isOfflineish(e)) {
        queueOperation(op);
        queued = true;
      } else {
        errorMsg = e.message;
      }
    } finally {
      busy = false;
    }
    if (done || queued) setTimeout(() => dispatch('close'), 900);
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="backdrop" on:click={onBackdrop}>
  <div class="panel">
    <div class="panel-header">
      <span class="title">{isFile ? 'Add Shared File' : isUrl ? 'Add Link' : 'Add to Note'}</span>
      <button class="close-btn" on:click={() => dispatch('close')} disabled={busy}>✕</button>
    </div>

    <div class="content">
      <div class="preview" class:link={isUrl}>
        {isFile ? `📎 ${share.fileName || 'Shared file'}` : (preview || '(empty)')}
      </div>

      {#if done}
        <div class="status ok">{isFile ? 'Uploaded ✓' : 'Added ✓'}</div>
      {:else if queued}
        <div class="status queued">📤 Queued — will send when back online</div>
      {:else}
        {#if isFile}
          <div class="hint">Uploads to the project's documents folder, then:</div>
          <div class="file-mode-toggle">
            <label><input type="radio" bind:group={asNote} value={false} disabled={busy} /> Add as a launcher</label>
            <label><input type="radio" bind:group={asNote} value={true} disabled={busy} /> Reference in note</label>
          </div>
        {:else}
          <div class="hint">
            {isUrl ? 'Adds as a launcher in "Added Resources"' : 'Prepended to the project note'} for:
          </div>
        {/if}
        <div class="grid">
          {#each sorted as project}
            <button
              class="proj-btn"
              class:selected={selected?.filename === project.filename}
              on:click={() => selected = project}
              disabled={busy}
            >
              {project.name}
            </button>
          {/each}
        </div>
        {#if errorMsg}
          <div class="status err">{errorMsg}</div>
        {/if}
        <div class="actions">
          <button class="cancel-btn" on:click={() => dispatch('close')} disabled={busy}>Cancel</button>
          <button class="add-btn" on:click={add} disabled={!selected || busy}>
            {busy ? (isFile ? 'Uploading…' : 'Adding…') : (isFile ? 'Upload' : 'Add')}
          </button>
        </div>
      {/if}
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; z-index: 200;
    background: rgba(0, 0, 0, 0.65);
    display: flex; align-items: center; justify-content: center;
    padding: 16px;
  }

  .panel {
    background: var(--bg-card); border: 1px solid var(--bd);
    border-radius: 14px; width: 100%; max-width: 480px;
    max-height: 88vh; display: flex; flex-direction: column;
    overflow: hidden;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  }

  .panel-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 16px; border-bottom: 1px solid var(--bd-sub);
    flex-shrink: 0;
  }
  .title { font-size: 1rem; font-weight: 600; color: var(--t-primary); }
  .close-btn {
    background: none; border: none; color: var(--t-muted);
    font-size: 1.1rem; padding: 2px 8px; line-height: 1;
  }

  .content { padding: 14px 16px; overflow-y: auto; }

  .preview {
    background: var(--bg-body); border: 1px solid var(--bd-sub);
    border-radius: 8px; padding: 10px 12px;
    font-size: 0.85rem; color: var(--t-sec);
    word-break: break-word; margin-bottom: 12px;
    max-height: 120px; overflow-y: auto;
  }
  .preview.link { color: var(--t-link); }

  .hint {
    font-size: 0.78rem; color: var(--t-ghost);
    margin-bottom: 8px;
  }

  .file-mode-toggle {
    display: flex; gap: 16px;
    font-size: 0.85rem; color: var(--t-sec);
    margin-bottom: 12px;
  }
  .file-mode-toggle label {
    display: flex; align-items: center; gap: 6px;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 6px; margin-bottom: 12px;
  }
  .proj-btn {
    background: var(--bg-body); border: 1px solid var(--bd);
    border-radius: 8px; color: var(--t-sec);
    font-size: 0.85rem; padding: 10px 10px; text-align: left;
  }
  .proj-btn.selected { background: var(--bg-active); color: var(--t-active); border-color: var(--bd-active); }

  .status { font-size: 0.85rem; padding: 6px 0; }
  .status.ok  { color: var(--t-saved); text-align: center; padding: 20px 0; font-size: 1rem; }
  .status.err { color: var(--t-error); }
  .status.queued { color: var(--t-unsaved); text-align: center; padding: 20px 0; font-size: 1rem; }

  .actions { display: flex; gap: 8px; justify-content: flex-end; }
  .cancel-btn, .add-btn {
    padding: 9px 16px; border-radius: 8px; font-size: 0.88rem; border: 1px solid var(--bd);
  }
  .cancel-btn { background: none; color: var(--t-muted); }
  .add-btn { background: var(--accent); color: #fff; border-color: var(--accent); }
  .add-btn:disabled { opacity: 0.5; }

  @media (min-width: 550px) {
    .title { font-size: 1.2rem; }
    .close-btn { font-size: 1.3rem; }
    .preview { font-size: 1rem; }
    .proj-btn { font-size: 1rem; padding: 12px; }
    .cancel-btn, .add-btn { font-size: 1.05rem; padding: 11px 20px; }
  }
</style>
