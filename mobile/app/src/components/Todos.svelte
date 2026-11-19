<script>
  import {
    allTodos, todosLoading, todosError, showCompletedTodos, projects, activeProject,
    loadAllTodos, toggleTodoTask, renameTodoTask, addTodoTask, selectProject,
    focusAddTaskSignal,
  } from '../lib/store.js';
  import Icon from './Icon.svelte';

  let addInputEl;
  // Bumped by the Todos FAB (Main.svelte) — scrolls/focuses the Add Task input rather
  // than duplicating addTodoTask's logic, so the FAB is purely a focus affordance and
  // the actual add flow stays in exactly one place (handleAdd below).
  $: if ($focusAddTaskSignal && addInputEl) {
    addInputEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    addInputEl.focus();
  }

  // Loads once on first mount (the component is destroyed/recreated every time the
  // user switches away from and back to this tab, so this already doubles as
  // "refresh on tab-entry," matching desktop's own All To-Dos convention) AND
  // reloads whenever the active project itself changes while the tab stays mounted
  // (e.g. tapping a different project in the header bar without leaving this tab) —
  // confirmed live on-device that without this, the "current project pinned first"
  // ordering went stale the moment you switched projects without also switching
  // tabs away and back. Compared by filename, not object identity, and guarded so
  // an unrelated re-render (e.g. toggling a task) doesn't trigger a spurious reload.
  let loadedForProject;
  $: {
    const current = $activeProject?.filename ?? null;
    if (current !== loadedForProject) {
      loadedForProject = current;
      loadAllTodos();
    }
  }

  // Current project's group (always shown, even with zero visible tasks — it's the
  // Add Task row's implicit target) vs. every OTHER project with at least one
  // currently-visible task (per direct user feedback: a project with nothing to show
  // right now — respecting the "Include completed" toggle — shouldn't clutter the list
  // with an empty "Nothing pending" section; toggling "Include completed" can bring it
  // back into view without a refetch, since this filter is purely reactive, not baked
  // into what loadAllTodos() fetched).
  //
  // Found by filename match anywhere in $allTodos, NOT assumed to be at index 0 —
  // loadAllTodos() fetches several projects concurrently (see its own docstring), so
  // groups can land in allTodos in whatever order their network calls happened to
  // resolve, not the alphabetical order they were requested in. "Other Projects" is
  // re-sorted alphabetically here for the same reason, so the visible list stays
  // stable/predictable rather than reshuffling as results trickle in.
  $: currentGroup = $allTodos.find(g => g.project.filename === $activeProject?.filename) ?? null;
  $: currentVisible = currentGroup
    ? currentGroup.items.filter(it => $showCompletedTodos || !it.done)
    : [];
  $: otherSections = $allTodos
    .filter(g => g !== currentGroup)
    .map(g => ({ group: g, visible: g.items.filter(it => $showCompletedTodos || !it.done) }))
    .filter(s => s.visible.length > 0)
    .sort((a, b) => a.group.project.name.localeCompare(b.group.project.name));

  // Collapsed by default — the background fetch in loadAllTodos() is completely
  // decoupled from what's actually rendered (it just keeps writing into the
  // `allTodos` store regardless), so "Other Projects" staying collapsed doesn't
  // pause or skip loading it: by the time this is expanded, whatever's already
  // arrived shows up instantly, with the rest filling in right behind it exactly
  // as if it had been visible the whole time. Session-only, not persisted —
  // resets to collapsed on every fresh visit to the tab.
  let showOthers = false;

  let newTitle = '';
  let targetFilename = ''; // '' = current project (see addTodoTask's own fallback)

  let editingKey = null; // `${projectFilename}:${lineIndex}` | null
  let editText = '';

  function timeAgo(ts) {
    if (!ts) return 'unknown time';
    const mins = Math.round((Date.now() - ts) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.round(hours / 24)}d ago`;
  }

  async function handleAdd() {
    const title = newTitle.trim();
    if (!title) return;
    const target = targetFilename ? $projects.find(p => p.filename === targetFilename) : null;
    try {
      await addTodoTask(target, title);
      newTitle = '';
    } catch (e) {
      todosError.set(e.message || 'Could not add task');
    }
  }

  async function handleToggle(group, item) {
    try {
      await toggleTodoTask(group.project, item.lineIndex, item.text);
    } catch (e) {
      todosError.set(e.message || 'Could not update task');
    }
  }

  function startEdit(group, item) {
    editingKey = `${group.project.filename}:${item.lineIndex}`;
    editText = item.text;
  }

  // Called from both blur and Enter (Enter just blurs the input, see markup below) —
  // the editingKey guard means whichever trigger fires first does the real commit and
  // the other becomes a no-op, rather than risking a double rename.
  async function commitEdit(group, item) {
    const key = `${group.project.filename}:${item.lineIndex}`;
    if (editingKey !== key) return;
    editingKey = null;
    const text = editText.trim();
    if (!text || text === item.text) return; // unchanged or emptied — not worth a write
    try {
      await renameTodoTask(group.project, item.lineIndex, item.text, text);
    } catch (e) {
      todosError.set(e.message || 'Could not rename task');
    }
  }
</script>

<div class="todos">
  <div class="toolbar">
    <button class="icon-btn" on:click={() => loadAllTodos()} title="Refresh"><Icon name="refresh" size="1em" /></button>
    <button class="chip" class:active={$showCompletedTodos} on:click={() => showCompletedTodos.update(v => !v)}>
      {$showCompletedTodos ? 'To-do only' : 'Include completed'}
    </button>
    <button class="chip" class:active={showOthers} on:click={() => showOthers = !showOthers}>
      {#if showOthers}
        Hide Others
      {:else}
        Show Others{otherSections.length > 0 ? ` (${otherSections.length})` : ''}
      {/if}
    </button>
  </div>

  <div class="add-row">
    <input
      class="add-input"
      type="text"
      placeholder="New task…"
      bind:value={newTitle}
      bind:this={addInputEl}
      on:keydown={e => e.key === 'Enter' && handleAdd()}
    />
    <div class="add-row-bottom">
      <select class="add-select" bind:value={targetFilename}>
        <option value="">Current project</option>
        {#each $projects as p (p.filename)}
          <option value={p.filename}>{p.name}</option>
        {/each}
      </select>
      <button class="add-btn" on:click={handleAdd}>Add</button>
    </div>
  </div>

  {#if $todosError}
    <div class="error-banner">
      <span>{$todosError}</span>
      <button class="dismiss-btn" on:click={() => todosError.set(null)} title="Dismiss"><Icon name="close" size="0.9em" /></button>
    </div>
  {/if}

  <div class="groups">
    {#if $todosLoading && $allTodos.length === 0}
      <p class="empty">Loading…</p>
    {:else if !currentGroup && otherSections.length === 0}
      <p class="empty">No to-dos yet</p>
    {:else}
      {#if currentGroup}
        <div class="category current">
          <div class="cat-header">
            <span class="proj-name">{currentGroup.project.name}</span>
            {#if currentGroup.fromCache}
              <span class="cache-mark" title={`Cached ${timeAgo(currentGroup.cachedAt)}`}><Icon name="cached" size="0.85em" /></span>
            {/if}
          </div>
          {#if currentVisible.length === 0}
            <p class="nothing-pending">Nothing pending</p>
          {:else}
            {#each currentVisible as item (item.lineIndex)}
              {@const key = `${currentGroup.project.filename}:${item.lineIndex}`}
              <div class="task-row" class:done={item.done}>
                <button
                  class="circle"
                  class:done={item.done}
                  on:click={() => handleToggle(currentGroup, item)}
                  title={item.done ? 'Mark as not done' : 'Mark as done'}
                >
                  {#if item.done}<Icon name="checkmark" size="0.75em" />{/if}
                </button>
                {#if editingKey === key}
                  <input
                    class="task-edit"
                    type="text"
                    bind:value={editText}
                    autofocus
                    on:blur={() => commitEdit(currentGroup, item)}
                    on:keydown={e => {
                      if (e.key === 'Enter') e.target.blur();
                      else if (e.key === 'Escape') editingKey = null;
                    }}
                  />
                {:else}
                  <span
                    class="task-text"
                    class:done={item.done}
                    on:click={() => startEdit(currentGroup, item)}
                    role="button"
                    tabindex="0"
                    on:keypress={e => e.key === 'Enter' && startEdit(currentGroup, item)}
                  >
                    {item.text}
                  </span>
                {/if}
              </div>
            {/each}
          {/if}
        </div>
      {/if}

      {#if showOthers && otherSections.length > 0}
        <div class="section-label">Other Projects</div>
        {#each otherSections as section (section.group.project.filename)}
          <div class="category">
            <div class="cat-header">
              <button class="proj-name link" on:click={() => selectProject(section.group.project)}>
                {section.group.project.name}
              </button>
              {#if section.group.fromCache}
                <span class="cache-mark" title={`Cached ${timeAgo(section.group.cachedAt)}`}><Icon name="cached" size="0.85em" /></span>
              {/if}
            </div>
            {#each section.visible as item (item.lineIndex)}
              {@const key = `${section.group.project.filename}:${item.lineIndex}`}
              <div class="task-row" class:done={item.done}>
                <button
                  class="circle"
                  class:done={item.done}
                  on:click={() => handleToggle(section.group, item)}
                  title={item.done ? 'Mark as not done' : 'Mark as done'}
                >
                  {#if item.done}<Icon name="checkmark" size="0.75em" />{/if}
                </button>
                {#if editingKey === key}
                  <input
                    class="task-edit"
                    type="text"
                    bind:value={editText}
                    autofocus
                    on:blur={() => commitEdit(section.group, item)}
                    on:keydown={e => {
                      if (e.key === 'Enter') e.target.blur();
                      else if (e.key === 'Escape') editingKey = null;
                    }}
                  />
                {:else}
                  <span
                    class="task-text"
                    class:done={item.done}
                    on:click={() => startEdit(section.group, item)}
                    role="button"
                    tabindex="0"
                    on:keypress={e => e.key === 'Enter' && startEdit(section.group, item)}
                  >
                    {item.text}
                  </span>
                {/if}
              </div>
            {/each}
          </div>
        {/each}
      {/if}

      {#if $todosLoading}
        <p class="loading-more">Loading more projects…</p>
      {/if}
    {/if}
  </div>
</div>

<style>
  .todos { padding: 12px; }

  .toolbar {
    display: flex; align-items: center; flex-wrap: wrap; gap: 8px;
    padding-bottom: 10px; border-bottom: 1px solid var(--bd-sub); margin-bottom: 10px;
  }
  .icon-btn {
    background: var(--m3-surface-container); color: var(--t-muted); border: 1px solid var(--m3-outline);
    border-radius: var(--radius-full); padding: 7px 10px; line-height: 1;
    display: inline-flex; align-items: center;
  }
  .chip {
    background: var(--m3-surface-container); color: var(--t-sec); border: 1px solid var(--m3-outline);
    border-radius: var(--radius-full); padding: 6px 14px; font-size: 0.82rem;
  }
  .chip.active {
    background: var(--m3-primary-container); color: var(--m3-on-primary-container);
    border-color: transparent; font-weight: 600;
  }

  .add-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
  .add-input {
    flex: 1 1 100%;
    background: var(--m3-surface-container); color: var(--t-primary); border: 1px solid var(--m3-outline);
    border-radius: var(--radius-sm); padding: 8px 10px; font-size: 0.9rem;
  }
  .add-row-bottom { flex: 1 1 100%; display: flex; gap: 6px; }
  .add-select {
    flex: 1 1 auto; min-width: 0;
    background: var(--m3-surface-container); color: var(--t-sec); border: 1px solid var(--m3-outline);
    border-radius: var(--radius-sm); padding: 8px 6px; font-size: 0.85rem;
  }
  .add-btn {
    flex: 0 0 auto;
    background: var(--m3-primary); color: var(--m3-on-primary); border: none;
    border-radius: var(--radius-full); padding: 8px 18px; font-size: 0.85rem; font-weight: 600;
  }

  .error-banner {
    display: flex; align-items: center; gap: 10px;
    background: var(--m3-surface-container); border: 1px solid var(--t-error);
    color: var(--t-error); font-size: 0.8rem; line-height: 1.35;
    padding: 8px 12px; border-radius: var(--radius-sm); margin-bottom: 10px;
  }
  .error-banner span { flex: 1; }
  .error-banner .dismiss-btn { background: none; border: none; color: var(--t-error); display: flex; }

  .empty { color: var(--t-ghost); font-size: 0.9rem; padding: 24px; text-align: center; }

  .category { margin-bottom: 18px; }
  .cat-header {
    display: flex; align-items: center; gap: 6px;
    font-size: 0.8rem; font-weight: 600;
    color: var(--m3-primary); padding: 4px 0 6px; margin-bottom: 6px;
    border-bottom: 1px solid var(--m3-outline-variant);
  }
  .category.current .cat-header {
    background: var(--m3-primary-container); border-radius: var(--radius-md); border-bottom: none;
    padding: 8px 12px; margin-bottom: 8px;
  }
  .category.current .cat-header .proj-name { color: var(--m3-on-primary-container); }
  .proj-name { flex: 1; text-align: left; }
  .proj-name.link { color: var(--m3-primary); }
  .cache-mark { flex-shrink: 0; display: flex; opacity: 0.75; }
  .nothing-pending { color: var(--t-dimmer); font-size: 0.82rem; padding: 4px 0 4px 36px; }

  .section-label {
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.06em;
    text-transform: uppercase; color: var(--t-dim);
    padding-top: 10px; margin-top: 4px; margin-bottom: 10px;
    border-top: 1px solid var(--m3-outline-variant);
  }
  .loading-more {
    color: var(--t-ghost); font-size: 0.78rem; text-align: center; padding: 10px 0;
  }

  .task-row {
    display: flex; align-items: center; gap: 10px;
    background: var(--m3-surface-container); border-radius: var(--radius-full);
    padding: 9px 14px; margin-bottom: 6px; box-shadow: var(--elevation-1);
  }
  .task-row.done { background: var(--m3-secondary-container); }
  .circle {
    flex-shrink: 0; width: 24px; height: 24px; border-radius: 50%;
    background: none; border: 2px solid var(--t-dim);
    display: flex; align-items: center; justify-content: center;
    color: transparent; padding: 0;
  }
  .circle.done {
    background: var(--m3-on-secondary-container); border-color: var(--m3-on-secondary-container);
    color: var(--m3-secondary-container);
  }
  .task-text {
    flex: 1; color: var(--t-primary); font-size: 0.88rem; font-weight: 600;
    word-break: break-word;
  }
  .task-text.done { color: var(--m3-on-secondary-container); text-decoration: line-through; opacity: 0.75; }
  .task-edit {
    flex: 1; background: transparent; color: var(--t-primary); border: none;
    border-bottom: 1px solid var(--m3-primary); font-size: 0.88rem; font-weight: 600;
    padding: 0 0 2px;
  }
  .task-edit:focus { outline: none; }

  @media (min-width: 550px) {
    .todos        { padding: 18px; }
    .empty        { font-size: 1.1rem; }
    .chip         { font-size: 1rem; padding: 8px 18px; }
    .icon-btn     { padding: 8px 14px; }
    .add-input    { font-size: 1.05rem; padding: 10px 14px; }
    .add-select   { font-size: 1rem; }
    .add-btn      { font-size: 1rem; padding: 10px 22px; }
    .cat-header   { font-size: 0.95rem; }
    .section-label { font-size: 0.85rem; }
    .loading-more { font-size: 0.9rem; }
    .task-row     { padding: 11px 18px; }
    .task-text    { font-size: 1.05rem; }
    .task-edit    { font-size: 1.05rem; }
    .circle       { width: 28px; height: 28px; }
  }
</style>
