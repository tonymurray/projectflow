<script>
  import { get } from 'svelte/store';
  import { activeProject, activeConfig, activeTab, loading, error, offline, pendingQueue, queueFeedback, usingCachedCopy, fetchProjects, retryConnection, flushQueue, pendingShare, initShareReceiver, initNetworkWatcher, drawerOpen, requestFocusAddTask } from '../lib/store.js';
  import Launchers from './Launchers.svelte';
  import Notes from './Notes.svelte';
  import Todos from './Todos.svelte';
  import NavDrawer from './NavDrawer.svelte';
  import ShareTarget from './ShareTarget.svelte';
  import PasteText from './PasteText.svelte';
  import Settings from './Settings.svelte';
  import Icon from './Icon.svelte';

  fetchProjects();
  initShareReceiver();
  initNetworkWatcher();
  // Covers the case where the app was closed while offline with items still queued and
  // is later reopened already on wifi — no live "regained connectivity" transition ever
  // fires in that case, so retryConnection()'s own flush (wired via initNetworkWatcher)
  // never gets a chance to run on its own.
  if (get(pendingQueue).length) flushQueue();

  let showPaste = false;
  let showSettings = false;

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
  {#if $offline || $pendingQueue.length || $queueFeedback}
    <header>
      {#if $offline}
        <button class="offline-pill" on:click={retryConnection} title="Retry connection">
          <Icon name="offline" size="0.95em" /> Offline · Retry
        </button>
      {/if}
      {#if $pendingQueue.length}
        <button class="offline-pill" on:click={retryConnection} title="Send queued items now">
          <Icon name="share" size="0.95em" /> {$pendingQueue.length} pending · Retry
        </button>
      {/if}
      {#if $queueFeedback}
        <div class="queue-banner">
          <span>{$queueFeedback}</span>
          <button class="dismiss-btn" on:click={() => queueFeedback.set(null)} title="Dismiss"><Icon name="close" size="0.9em" /></button>
        </div>
      {/if}
    </header>
  {/if}

  {#if $usingCachedCopy && $usingCachedCopy.projectFilename === $activeProject?.filename}
    <div class="cache-banner">
      <Icon name="cached" size="0.95em" /> Showing cached copy from {timeAgo($usingCachedCopy.cachedAt)} — offline
    </div>
  {/if}

  <NavDrawer on:paste={() => showPaste = true} />

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
        <p><Icon name="offline" size="1.3em" /> Currently offline</p>
        <p class="hint">Can't reach the server right now.</p>
        <button on:click={retryConnection}>Retry</button>
      </div>
    {:else if !$activeProject}
      <div class="status-msg">
        <p>Select a project</p>
        <button class="pick-btn" on:click={() => drawerOpen.set(true)}><Icon name="hamburger" size="1em" /> Open project list</button>
      </div>
    {:else if $activeTab === 'launchers'}
      <Launchers />
    {:else if $activeTab === 'notes'}
      <Notes />
    {:else if $activeTab === 'todos'}
      <Todos />
    {/if}
  </main>

  {#if $activeTab === 'todos'}
    <button class="fab" on:click={requestFocusAddTask} title="Add task">
      <Icon name="add" size="1.4em" />
    </button>
  {/if}

  <!-- Bottom nav -->
  <nav>
    <button class="nav-btn trigger" on:click={() => drawerOpen.set(true)} title="Projects">
      <span class="icon-wrap"><Icon name="hamburger" size="1.15em" /></span>
    </button>
    <button class="nav-btn" class:active={$activeTab === 'launchers'} on:click={() => activeTab.set('launchers')}>
      <span class="icon-wrap"><Icon name="resources" size="1.15em" /></span>
      <span class="label">Resources</span>
    </button>
    <button class="nav-btn" class:active={$activeTab === 'notes'} on:click={() => activeTab.set('notes')}>
      <span class="icon-wrap"><Icon name="notes" size="1.15em" /></span>
      <span class="label">Notes</span>
    </button>
    <button class="nav-btn" class:active={$activeTab === 'todos'} on:click={() => activeTab.set('todos')}>
      <span class="icon-wrap"><Icon name="todo" size="1.15em" /></span>
      <span class="label">To-Dos</span>
    </button>
    <button class="nav-btn trigger" on:click={() => showSettings = true} title="Settings">
      <span class="icon-wrap"><Icon name="settings" size="1.15em" /></span>
    </button>
  </nav>
</div>

<style>
  .shell { display: flex; flex-direction: column; height: 100dvh; position: relative; }

  header {
    flex-shrink: 0;
    background: var(--bg-header);
    border-bottom: 1px solid var(--bd-sub);
    display: flex; flex-direction: column;
    gap: 4px; padding: 6px 10px;
  }

  .offline-pill {
    align-self: flex-start;
    display: inline-flex; align-items: center; gap: 6px;
    background: none; border: 1px solid var(--t-unsaved);
    border-radius: var(--radius-full); color: var(--t-unsaved);
    font-size: 0.8rem; padding: 4px 12px; line-height: 1.2;
    white-space: nowrap;
  }
  .offline-pill:hover { background: var(--bg-hover); }

  .queue-banner {
    display: flex; align-items: center; gap: 10px;
    color: var(--t-unsaved); font-size: 0.8rem; line-height: 1.35;
    padding: 4px 2px;
  }
  .queue-banner span { flex: 1; }
  .queue-banner .dismiss-btn {
    flex-shrink: 0; background: none; border: none; color: var(--t-unsaved);
    padding: 2px 4px; display: flex;
  }

  .cache-banner {
    flex-shrink: 0;
    display: flex; align-items: center; gap: 8px;
    background: var(--m3-surface-container-low); border-bottom: 1px solid var(--m3-primary);
    color: var(--m3-primary); font-size: 0.8rem; line-height: 1.35;
    padding: 8px 12px;
  }

  main { flex: 1; overflow-y: auto; }

  .status-msg {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 8px; height: 100%; color: var(--t-ghost); font-size: 0.9rem;
  }
  .status-msg p { display: flex; align-items: center; gap: 8px; }
  .status-msg.err { color: var(--t-error); }
  .status-msg.offline { color: var(--t-unsaved); }
  .status-msg.offline .hint { color: var(--t-ghost); font-size: 0.82rem; }
  .status-msg.offline button, .pick-btn {
    margin-top: 6px; background: var(--m3-surface-container); color: var(--t-sec);
    border: 1px solid var(--m3-outline); border-radius: var(--radius-full);
    padding: 8px 20px; font-size: 0.85rem;
    display: inline-flex; align-items: center; gap: 8px;
  }
  .status-msg.offline button:hover, .pick-btn:hover { background: var(--bg-hover); }

  .fab {
    position: fixed;
    right: 16px;
    bottom: calc(var(--nav-h, 64px) + 16px);
    width: 52px; height: 52px;
    border-radius: var(--radius-lg);
    background: var(--m3-primary-container);
    color: var(--m3-on-primary-container);
    border: none;
    box-shadow: var(--elevation-2);
    display: flex; align-items: center; justify-content: center;
    z-index: 50;
  }

  nav {
    --nav-h: 64px;
    flex-shrink: 0;
    display: flex;
    background: var(--m3-surface-container-high);
    border-top: 1px solid var(--m3-outline-variant);
    padding: 6px 4px;
  }
  .nav-btn {
    flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px;
    background: none; border: none; color: var(--t-dim);
    padding: 4px 2px; font-size: 0.7rem;
  }
  .nav-btn.trigger { flex: 0 0 auto; padding: 4px 14px; }
  .icon-wrap {
    display: inline-flex; align-items: center; justify-content: center;
    padding: 5px 18px; border-radius: var(--radius-full);
    transition: background 0.15s, color 0.15s;
  }
  .nav-btn.trigger .icon-wrap { padding: 7px; color: var(--t-dim); }
  .nav-btn.active .icon-wrap { background: var(--m3-nav-pill); color: var(--m3-on-nav-pill); }
  .nav-btn.active .label { color: var(--m3-on-nav-pill); font-weight: 600; }
  .label { line-height: 1; }

  @media (min-width: 550px) {
    .nav-btn { font-size: 0.85rem; padding: 6px 4px; }
    .icon-wrap { padding: 7px 24px; }
    header { padding: 8px 14px; }
    .queue-banner, .cache-banner { font-size: 0.95rem; }
  }
</style>
