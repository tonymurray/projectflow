<script>
  import { projects, pinnedProjects, togglePin, selectProject } from '../lib/store.js';
  import { createEventDispatcher } from 'svelte';

  const dispatch = createEventDispatcher();

  $: sorted = [...$projects].sort((a, b) => a.name.localeCompare(b.name));

  function pick(project) {
    selectProject(project);
    dispatch('close');
  }

  function onBackdrop(e) {
    if (e.target === e.currentTarget) dispatch('close');
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="backdrop" on:click={onBackdrop}>
  <div class="panel">
    <div class="panel-header">
      <span class="title">All Projects</span>
      <button class="close-btn" on:click={() => dispatch('close')}>✕</button>
    </div>
    <div class="grid">
      {#each sorted as project}
        {@const pinned = $pinnedProjects.includes(project.filename)}
        <div class="row" class:pinned>
          <button class="name-btn" on:click={() => pick(project)}>
            {project.name}
          </button>
          <button
            class="pin-btn"
            class:pinned
            on:click={() => togglePin(project.filename)}
            title={pinned ? 'Unpin' : 'Pin to bar'}
          >📌</button>
        </div>
      {/each}
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
    border-radius: 14px; width: 100%; max-width: 680px;
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

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 6px; padding: 12px;
    overflow-y: auto;
  }

  .row {
    display: flex; align-items: stretch;
    background: var(--bg-body); border: 1px solid var(--bd);
    border-radius: 8px; overflow: hidden;
    transition: border-color 0.15s;
  }
  .row.pinned {
    border-color: var(--bd-active);
    background: var(--bg-active);
  }

  .name-btn {
    flex: 1; background: none; border: none;
    color: var(--t-sec); font-size: 0.85rem;
    padding: 10px 6px 10px 12px;
    text-align: left; line-height: 1.3;
    word-break: break-word;
  }
  .row.pinned .name-btn { color: var(--t-active); }

  .pin-btn {
    background: none; border: none;
    border-left: 1px solid var(--bd-sub);
    font-size: 0.75rem; padding: 10px 8px;
    flex-shrink: 0; opacity: 0.25;
    transition: opacity 0.15s;
  }
  .pin-btn.pinned { opacity: 1; }
  .row:hover .pin-btn { opacity: 0.6; }
  .pin-btn.pinned:hover { opacity: 1; }

  @media (min-width: 550px) {
    .grid {
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 8px; padding: 16px;
    }
    .name-btn { font-size: 1.05rem; padding: 14px 8px 14px 16px; }
    .pin-btn  { font-size: 0.95rem; padding: 14px 10px; }
    .title    { font-size: 1.2rem; }
    .close-btn { font-size: 1.3rem; }
  }
</style>
