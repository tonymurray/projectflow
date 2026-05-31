<script>
  import { orderedProjects, pinnedProjects, activeProject, activeTab, loading, error, fetchProjects, selectProject, theme } from '../lib/store.js';
  import Launchers from './Launchers.svelte';
  import Notes from './Notes.svelte';
  import ProjectPicker from './ProjectPicker.svelte';

  fetchProjects();

  let showPicker = false;

  function toggleTheme() {
    theme.update(t => t === 'dark' ? 'light' : 'dark');
  }
</script>

<div class="shell">
  <!-- Project switcher -->
  <header>
    <div class="project-bar">
      {#if $loading && $orderedProjects.length === 0}
        <span class="hint">Loading…</span>
      {:else}
        {#each $orderedProjects as project}
          {@const pinned = $pinnedProjects.includes(project.filename)}
          <button
            class="proj-btn"
            class:active={$activeProject?.filename === project.filename}
            class:pinned
            on:click={() => selectProject(project)}
          >
            {project.name}
          </button>
        {/each}
      {/if}
    </div>
    <button class="all-btn" on:click={() => showPicker = true} title="All projects">≡</button>
  </header>

  {#if showPicker}
    <ProjectPicker on:close={() => showPicker = false} />
  {/if}

  <!-- Main content -->
  <main>
    {#if $loading && $activeProject}
      <div class="status-msg">Loading…</div>
    {:else if $error}
      <div class="status-msg err">{$error}</div>
    {:else if !$activeProject}
      <div class="status-msg">Select a project above</div>
    {:else if $activeTab === 'launchers'}
      <Launchers />
    {:else if $activeTab === 'notes'}
      <Notes />
    {/if}
  </main>

  <!-- Tab bar -->
  <nav>
    <button class:active={$activeTab === 'launchers'} on:click={() => activeTab.set('launchers')}>🚀 Resources</button>
    <button class:active={$activeTab === 'notes'}    on:click={() => activeTab.set('notes')}>📝 Notes</button>
    <button class="theme-btn" on:click={toggleTheme} title="Toggle theme">
      {$theme === 'dark' ? '☀️' : '🌙'}
    </button>
  </nav>
</div>

<style>
  .shell { display: flex; flex-direction: column; height: 100dvh; }

  header {
    flex-shrink: 0;
    background: var(--bg-header);
    border-bottom: 1px solid var(--bd-sub);
    display: flex; align-items: center;
    gap: 4px; padding: 8px 6px 8px 10px;
  }
  .project-bar {
    display: flex; gap: 6px;
    overflow-x: auto; flex: 1;
    -webkit-overflow-scrolling: touch;
  }
  .proj-btn {
    background: var(--bg-card); color: var(--t-faint); border: 1px solid var(--bd);
    border-radius: 16px; padding: 5px 14px; font-size: 0.82rem; white-space: nowrap;
    flex-shrink: 0;
  }
  .proj-btn.active  { background: var(--bg-active); color: var(--t-active); border-color: var(--bd-active); }
  .proj-btn.pinned  { border-style: solid; border-bottom-width: 2px; border-bottom-color: var(--accent); }
  .hint { color: var(--t-ghost); font-size: 0.85rem; padding: 4px 0; }

  .all-btn {
    flex-shrink: 0;
    background: none; border: 1px solid var(--bd);
    border-radius: 8px; color: var(--t-muted);
    font-size: 1.1rem; padding: 4px 10px; line-height: 1;
  }
  .all-btn:hover { background: var(--bg-hover); }

  main { flex: 1; overflow-y: auto; }

  .status-msg {
    display: flex; align-items: center; justify-content: center;
    height: 100%; color: var(--t-ghost); font-size: 0.9rem;
  }
  .status-msg.err { color: var(--t-error); }

  nav {
    flex-shrink: 0;
    display: flex;
    background: var(--bg-header);
    border-top: 1px solid var(--bd-sub);
  }
  nav button {
    flex: 1; background: none; border: none; color: var(--t-dim);
    padding: 12px 4px 10px; font-size: 0.78rem;
  }
  nav button.active { color: var(--accent-hi); border-top: 2px solid var(--accent); }
  .theme-btn { flex: 0 !important; padding: 12px 14px 10px; font-size: 1rem; }

  @media (min-width: 550px) {
    nav button { font-size: 1.2rem; padding: 18px 8px 16px; }
    .theme-btn { font-size: 1.5rem; padding: 18px 20px 16px; }
    .proj-btn  { font-size: 1.05rem; padding: 8px 20px; border-radius: 20px; }
    .hint      { font-size: 1.05rem; }
    header     { padding: 10px 10px 10px 14px; }
    .all-btn   { font-size: 1.4rem; padding: 6px 14px; }
  }
</style>
