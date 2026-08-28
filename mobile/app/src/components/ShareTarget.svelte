<script>
  import { createEventDispatcher } from 'svelte';
  import { projects, activeProject, addLinkToProject, addTextToProjectNote } from '../lib/store.js';

  export let share; // { text, subject }

  const dispatch = createEventDispatcher();

  $: sorted = [...$projects].sort((a, b) => a.name.localeCompare(b.name));
  $: trimmed = (share.text || '').trim();
  $: isUrl = /^https?:\/\/\S+$/.test(trimmed);
  $: preview = trimmed.length > 220 ? trimmed.slice(0, 220) + '…' : trimmed;

  let selected = $activeProject;
  let busy = false;
  let done = false;
  let errorMsg = null;

  function onBackdrop(e) {
    if (e.target === e.currentTarget && !busy) dispatch('close');
  }

  async function add() {
    if (!selected || busy) return;
    busy = true;
    errorMsg = null;
    try {
      if (isUrl) {
        await addLinkToProject(selected, trimmed, share.subject);
      } else {
        await addTextToProjectNote(selected, trimmed);
      }
      done = true;
      setTimeout(() => dispatch('close'), 900);
    } catch (e) {
      errorMsg = e.message;
    } finally {
      busy = false;
    }
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="backdrop" on:click={onBackdrop}>
  <div class="panel">
    <div class="panel-header">
      <span class="title">{isUrl ? 'Add Link' : 'Add to Note'}</span>
      <button class="close-btn" on:click={() => dispatch('close')} disabled={busy}>✕</button>
    </div>

    <div class="content">
      <div class="preview" class:link={isUrl}>{preview || '(empty)'}</div>

      {#if done}
        <div class="status ok">Added ✓</div>
      {:else}
        <div class="hint">
          {isUrl ? 'Adds as a launcher in "Added Resources"' : 'Prepended to the project note'} for:
        </div>
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
            {busy ? 'Adding…' : 'Add'}
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
