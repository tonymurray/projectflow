<script>
  import { createEventDispatcher } from 'svelte';
  import { projects, pinnedProjects, orderedProjects, togglePin, selectProject, drawerOpen, theme } from '../lib/store.js';
  import Icon from './Icon.svelte';

  const dispatch = createEventDispatcher();

  $: sorted = [...$projects].sort((a, b) => a.name.localeCompare(b.name));

  function pick(project) {
    selectProject(project);
    drawerOpen.set(false);
  }

  function close() {
    drawerOpen.set(false);
  }

  function onBackdrop(e) {
    if (e.target === e.currentTarget) close();
  }

  function toggleTheme() {
    theme.update(t => t === 'dark' ? 'light' : 'dark');
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="backdrop" class:open={$drawerOpen} on:click={onBackdrop}>
  <div class="drawer" class:open={$drawerOpen}>
    <div class="drawer-header">
      <span class="app-name">ProjectFlow</span>
      <button class="close-btn" on:click={close} title="Close"><Icon name="close" size="1.1em" /></button>
    </div>

    <div class="drawer-scroll">
      {#if $orderedProjects.length}
        <div class="section-label">Pinned &amp; Recent</div>
        <div class="list">
          {#each $orderedProjects as project}
            {@const pinned = $pinnedProjects.includes(project.filename)}
            <div class="row" class:pinned>
              <button class="name-btn" on:click={() => pick(project)}>{project.name}</button>
              <button
                class="pin-btn"
                class:pinned
                on:click={() => togglePin(project.filename)}
                title={pinned ? 'Unpin' : 'Pin to top'}
              ><Icon name="pin" size="0.95em" /></button>
            </div>
          {/each}
        </div>
      {/if}

      <div class="section-label">All Projects</div>
      <div class="list">
        {#each sorted as project}
          {@const pinned = $pinnedProjects.includes(project.filename)}
          <div class="row" class:pinned>
            <button class="name-btn" on:click={() => pick(project)}>{project.name}</button>
            <button
              class="pin-btn"
              class:pinned
              on:click={() => togglePin(project.filename)}
              title={pinned ? 'Unpin' : 'Pin to top'}
            ><Icon name="pin" size="0.95em" /></button>
          </div>
        {/each}
      </div>
    </div>

    <div class="drawer-footer">
      <div class="section-label">Actions</div>
      <button class="action-row" on:click={() => { close(); dispatch('paste'); }}>
        <Icon name="clipboard" size="1.1em" />
        <span>Paste text or link…</span>
      </button>
      <button class="action-row" on:click={toggleTheme}>
        <Icon name={$theme === 'dark' ? 'sun' : 'moon'} size="1.1em" />
        <span>Switch to {$theme === 'dark' ? 'light' : 'dark'} theme</span>
      </button>
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; z-index: 200;
    background: rgba(0, 0, 0, 0.5);
    opacity: 0; visibility: hidden;
    transition: opacity 0.22s ease, visibility 0s linear 0.22s;
  }
  .backdrop.open {
    opacity: 1; visibility: visible;
    transition: opacity 0.22s ease, visibility 0s linear 0s;
  }

  .drawer {
    position: fixed; inset: 0 25% 0 0;
    max-width: 360px;
    background: var(--m3-surface-container-high);
    border-right: 1px solid var(--m3-outline);
    box-shadow: var(--elevation-2);
    display: flex; flex-direction: column;
    transform: translateX(-100%);
    transition: transform 0.22s ease;
  }
  .drawer.open { transform: translateX(0); }

  .drawer-header {
    flex-shrink: 0;
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 16px 12px;
  }
  .app-name { font-size: 1.05rem; font-weight: 700; color: var(--m3-on-primary-container); }
  .close-btn {
    background: none; border: none; color: var(--t-muted);
    padding: 6px; line-height: 1; border-radius: var(--radius-full);
    display: flex; align-items: center; justify-content: center;
  }

  .drawer-scroll { flex: 1; overflow-y: auto; padding: 0 10px; }

  .section-label {
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.02em;
    text-transform: uppercase; color: var(--t-dim);
    padding: 10px 10px 6px;
  }

  .list { display: flex; flex-direction: column; gap: 2px; margin-bottom: 4px; }

  .row {
    display: flex; align-items: stretch;
    border-radius: var(--radius-md); overflow: hidden;
    transition: background 0.15s;
  }
  .row:hover { background: var(--bg-hover); }
  .row.pinned { background: var(--m3-primary-container); }

  .name-btn {
    flex: 1; min-width: 0; background: none; border: none;
    color: var(--t-sec); font-size: 0.92rem;
    padding: 11px 6px 11px 12px;
    text-align: left; line-height: 1.3;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .row.pinned .name-btn { color: var(--m3-on-primary-container); font-weight: 600; }

  .pin-btn {
    background: none; border: none; color: var(--t-ghost);
    padding: 10px 14px; flex-shrink: 0; opacity: 0.4;
    display: flex; align-items: center; justify-content: center;
    transition: opacity 0.15s;
  }
  .pin-btn.pinned { opacity: 1; color: var(--m3-on-primary-container); }
  .row:hover .pin-btn { opacity: 0.8; }

  .drawer-footer {
    flex-shrink: 0;
    border-top: 1px solid var(--m3-outline-variant);
    padding: 4px 10px 10px;
  }
  .action-row {
    width: 100%; display: flex; align-items: center; gap: 12px;
    background: none; border: none; color: var(--t-sec);
    font-size: 0.88rem; padding: 10px 10px;
    border-radius: var(--radius-md); text-align: left;
  }
  .action-row:hover { background: var(--bg-hover); }
  .action-row :global(.icon) { color: var(--t-dim); }

  @media (min-width: 550px) {
    .drawer { max-width: 400px; }
    .app-name { font-size: 1.3rem; }
    .name-btn { font-size: 1.05rem; padding: 13px 8px 13px 16px; }
    .section-label { font-size: 0.85rem; }
    .action-row { font-size: 1rem; padding: 12px; }
  }
</style>
