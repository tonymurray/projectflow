<script>
  import { projects, activeProject, activeTab, loading, error, fetchProjects, selectProject } from '../lib/store.js';
  import Launchers from './Launchers.svelte';
  import Notes from './Notes.svelte';
  import Viewers from './Viewers.svelte';

  fetchProjects();
</script>

<div class="shell">
  <!-- Project switcher -->
  <header>
    <div class="project-bar">
      {#if $loading && $projects.length === 0}
        <span class="hint">Loading…</span>
      {:else}
        {#each $projects as project}
          <button
            class="proj-btn"
            class:active={$activeProject?.filename === project.filename}
            on:click={() => selectProject(project)}
          >
            {project.name}
          </button>
        {/each}
      {/if}
    </div>
  </header>

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
    {:else if $activeTab === 'viewers'}
      <Viewers />
    {/if}
  </main>

  <!-- Tab bar -->
  <nav>
    <button class:active={$activeTab === 'viewers'}  on:click={() => activeTab.set('viewers')}>🌐 Viewers</button>
    <button class:active={$activeTab === 'launchers'} on:click={() => activeTab.set('launchers')}>🚀 Launchers</button>
    <button class:active={$activeTab === 'notes'}    on:click={() => activeTab.set('notes')}>📝 Notes</button>
  </nav>
</div>

<style>
  .shell { display: flex; flex-direction: column; height: 100dvh; }

  header {
    flex-shrink: 0;
    background: #12151f;
    border-bottom: 1px solid #1e2235;
    overflow-x: auto;
    padding: 8px 10px;
    -webkit-overflow-scrolling: touch;
  }
  .project-bar { display: flex; gap: 6px; width: max-content; }
  .proj-btn {
    background: #1a1d26; color: #888; border: 1px solid #2e3244;
    border-radius: 16px; padding: 5px 14px; font-size: 0.82rem; white-space: nowrap;
  }
  .proj-btn.active { background: #253553; color: #c8ddf7; border-color: #3a5580; }
  .hint { color: #555; font-size: 0.85rem; padding: 4px 0; }

  main { flex: 1; overflow-y: auto; }

  .status-msg {
    display: flex; align-items: center; justify-content: center;
    height: 100%; color: #555; font-size: 0.9rem;
  }
  .status-msg.err { color: #eb5757; }

  nav {
    flex-shrink: 0;
    display: flex;
    background: #12151f;
    border-top: 1px solid #1e2235;
  }
  nav button {
    flex: 1; background: none; border: none; color: #666;
    padding: 12px 4px 10px; font-size: 0.78rem;
  }
  nav button.active { color: #7eb8f7; border-top: 2px solid #4a7fc1; }
</style>
