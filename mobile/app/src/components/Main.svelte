<script>
  import { get } from 'svelte/store';
  import { orderedProjects, pinnedProjects, activeProject, activeConfig, activeTab, loading, error, offline, pendingQueue, queueFeedback, usingCachedCopy, fetchProjects, selectProject, retryConnection, flushQueue, theme, pendingShare, initShareReceiver, initNetworkWatcher } from '../lib/store.js';
  import Launchers from './Launchers.svelte';
  import Notes from './Notes.svelte';
  import ProjectPicker from './ProjectPicker.svelte';
  import ShareTarget from './ShareTarget.svelte';
  import PasteText from './PasteText.svelte';
  import Settings from './Settings.svelte';

  fetchProjects();
  initShareReceiver();
  initNetworkWatcher();
  // Covers the case where the app was closed while offline with items still queued and
  // is later reopened already on wifi — no live "regained connectivity" transition ever
  // fires in that case, so retryConnection()'s own flush (wired via initNetworkWatcher)
  // never gets a chance to run on its own.
  if (get(pendingQueue).length) flushQueue();

  let showPicker = false;
  let showPaste = false;
  let showSettings = false;

  function toggleTheme() {
    theme.update(t => t === 'dark' ? 'light' : 'dark');
  }

  function timeAgo(ts) {
    if (!ts) return 'unknown time';
    const mins = Math.round((Date.now() - ts) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.round(hours / 24)}d ago`;
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
    {#if $offline}
      <button class="offline-pill" on:click={retryConnection} title="Retry connection">
        📡 Offline · Retry
      </button>
    {/if}
    {#if $pendingQueue.length}
      <button class="offline-pill" on:click={retryConnection} title="Send queued items now">
        📤 {$pendingQueue.length} pending · Retry
      </button>
    {/if}
    <button class="all-btn" on:click={() => showPicker = true} title="All projects">≡</button>
  </header>

  {#if $queueFeedback}
    <div class="queue-banner">
      <span>{$queueFeedback}</span>
      <button class="dismiss-btn" on:click={() => queueFeedback.set(null)} title="Dismiss">✕</button>
    </div>
  {/if}

  {#if $usingCachedCopy && $usingCachedCopy.projectFilename === $activeProject?.filename}
    <div class="cache-banner">
      📦 Showing cached copy from {timeAgo($usingCachedCopy.cachedAt)} — offline
    </div>
  {/if}

  {#if showPicker}
    <ProjectPicker on:close={() => showPicker = false} />
  {/if}

  {#if showPaste}
    <PasteText on:close={() => showPaste = false} />
  {/if}

  {#if showSettings}
    <Settings on:close={() => showSettings = false} />
  {/if}

  {#if $pendingShare}
    <ShareTarget share={$pendingShare} on:close={() => pendingShare.set(null)} />
  {/if}

  <!-- Main content -->
  <main>
    {#if $loading && $activeProject}
      <div class="status-msg">Loading…</div>
    {:else if $error}
      <div class="status-msg err">{$error}</div>
    {:else if $offline && !$activeConfig}
      <div class="status-msg offline">
        <p>📡 Currently offline</p>
        <p class="hint">Can't reach the server right now.</p>
        <button on:click={retryConnection}>Retry</button>
      </div>
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
    <button class="icon-btn" on:click={() => showPaste = true} title="Paste text or link into a note/launcher">📋</button>
    <button class="icon-btn" on:click={toggleTheme} title="Toggle theme">
      {$theme === 'dark' ? '☀️' : '🌙'}
    </button>
    <button class="icon-btn" on:click={() => showSettings = true} title="Settings">⚙</button>
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
    font-size: 1.1rem; padding: 8px 20px; line-height: 1;
  }
  .all-btn:hover { background: var(--bg-hover); }

  .offline-pill {
    flex-shrink: 0;
    background: none; border: 1px solid var(--t-unsaved);
    border-radius: 8px; color: var(--t-unsaved);
    font-size: 0.8rem; padding: 4px 10px; line-height: 1.2;
    white-space: nowrap;
  }
  .offline-pill:hover { background: var(--bg-hover); }

  .queue-banner {
    flex-shrink: 0;
    display: flex; align-items: center; gap: 10px;
    background: var(--bg-card); border-bottom: 1px solid var(--t-unsaved);
    color: var(--t-unsaved); font-size: 0.8rem; line-height: 1.35;
    padding: 8px 12px;
  }
  .queue-banner span { flex: 1; }
  .queue-banner .dismiss-btn {
    flex-shrink: 0;
    background: none; border: none; color: var(--t-unsaved);
    font-size: 1rem; padding: 2px 4px; line-height: 1;
  }

  .cache-banner {
    flex-shrink: 0;
    background: var(--bg-card); border-bottom: 1px solid var(--accent);
    color: var(--accent); font-size: 0.8rem; line-height: 1.35;
    padding: 8px 12px;
  }

  main { flex: 1; overflow-y: auto; }

  .status-msg {
    display: flex; align-items: center; justify-content: center;
    height: 100%; color: var(--t-ghost); font-size: 0.9rem;
  }
  .status-msg.err { color: var(--t-error); }
  .status-msg.offline {
    flex-direction: column; gap: 6px; color: var(--t-unsaved);
  }
  .status-msg.offline .hint { color: var(--t-ghost); font-size: 0.82rem; }
  .status-msg.offline button {
    margin-top: 6px; background: var(--bg-card); color: var(--t-unsaved);
    border: 1px solid var(--t-unsaved); border-radius: 8px;
    padding: 6px 18px; font-size: 0.85rem;
  }
  .status-msg.offline button:hover { background: var(--bg-hover); }

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
  .icon-btn { flex: 0 !important; padding: 12px 14px 10px; font-size: 1rem; }

  @media (min-width: 550px) {
    nav button { font-size: 1.2rem; padding: 18px 8px 16px; }
    .icon-btn { font-size: 1.5rem; padding: 18px 20px 16px; }
    .proj-btn  { font-size: 1.05rem; padding: 8px 20px; border-radius: 20px; }
    .hint      { font-size: 1.05rem; }
    header     { padding: 10px 10px 10px 14px; }
    .all-btn   { font-size: 1.4rem; padding: 12px 28px; }
    .queue-banner { font-size: 0.95rem; padding: 10px 16px; }
    .cache-banner { font-size: 0.95rem; padding: 10px 16px; }
  }
</style>
