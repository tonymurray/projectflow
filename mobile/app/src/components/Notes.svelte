<script>
  import { activeNote, noteSaved, queueNoteSave, activeProject } from '../lib/store.js';

  let editing = false;
  let textarea;

  function startEdit() {
    editing = true;
    setTimeout(() => textarea?.focus(), 50);
  }

  function handleInput(e) {
    queueNoteSave(e.target.value);
  }

  // Simple markdown → HTML (headings, bold, italic, code, lists, links)
  function renderMarkdown(md) {
    if (!md) return '<p style="color:#555">No notes yet. Tap ✏️ to add.</p>';
    let html = md
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      // Code blocks
      .replace(/```[\s\S]*?```/g, m => `<pre><code>${m.slice(3, -3).trim()}</code></pre>`)
      // Headings
      .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^# (.+)$/gm, '<h1>$1</h1>')
      // Bold / italic
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      // Inline code
      .replace(/`(.+?)`/g, '<code>$1</code>')
      // Links
      .replace(/\[(.+?)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
      // Checkboxes
      .replace(/^- \[x\] (.+)$/gim, '<li class="done">✓ $1</li>')
      .replace(/^- \[ \] (.+)$/gim, '<li class="todo">☐ $1</li>')
      // Unordered list items
      .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
      // Wrap consecutive <li> in <ul>
      .replace(/(<li>[\s\S]+?<\/li>)(?!\s*<li>)/g, '<ul>$1</ul>')
      // Horizontal rules
      .replace(/^---+$/gm, '<hr>')
      // Paragraphs (double newline)
      .replace(/\n\n+/g, '</p><p>')
      // Single newlines → <br>
      .replace(/\n/g, '<br>');
    return `<p>${html}</p>`;
  }
</script>

<div class="notes">
  <div class="toolbar">
    <span class="save-status" class:saved={$noteSaved} class:unsaved={!$noteSaved}>
      {$noteSaved ? '● Saved' : '● Saving…'}
    </span>
    <button class="edit-btn" on:click={() => editing = !editing}>
      {editing ? '👁 View' : '✏️ Edit'}
    </button>
  </div>

  {#if editing}
    <textarea
      bind:this={textarea}
      value={$activeNote}
      on:input={handleInput}
      placeholder="Write your notes here (Markdown supported)…"
      spellcheck="true"
    ></textarea>
  {:else}
    <div
      class="rendered"
      on:dblclick={startEdit}
      role="button"
      tabindex="0"
      on:keypress={e => e.key === 'Enter' && startEdit()}
    >
      {@html renderMarkdown($activeNote)}
      <p class="hint">Double-tap to edit</p>
    </div>
  {/if}
</div>

<style>
  .notes { display: flex; flex-direction: column; height: 100%; }

  .toolbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 14px; border-bottom: 1px solid var(--bd-sub); flex-shrink: 0;
  }
  .save-status { font-size: 0.75rem; }
  .saved   { color: var(--t-saved); }
  .unsaved { color: var(--t-unsaved); }

  .edit-btn {
    background: var(--bg-card); color: var(--t-muted); border: 1px solid var(--bd);
    border-radius: 5px; padding: 5px 12px; font-size: 0.82rem;
  }

  textarea {
    flex: 1; background: var(--bg-body); color: var(--t-primary);
    border: none; padding: 16px; font-size: 0.95rem;
    font-family: 'Courier New', monospace; line-height: 1.6;
    resize: none;
  }
  textarea:focus { outline: none; }

  .rendered {
    flex: 1; padding: 16px; overflow-y: auto;
    line-height: 1.7; font-size: 0.95rem;
  }
  .hint { font-size: 0.72rem; color: var(--t-darkest); margin-top: 24px; text-align: center; }

  /* Rendered markdown styles */
  .rendered :global(h1) { font-size: 1.3rem; color: var(--accent-hi); margin: 16px 0 8px; border-bottom: 1px solid var(--bd-sub); padding-bottom: 4px; }
  .rendered :global(h2) { font-size: 1.1rem; color: var(--t-heading); margin: 14px 0 6px; }
  .rendered :global(h3) { font-size: 0.95rem; color: var(--t-heading); margin: 12px 0 4px; }
  .rendered :global(h4) { font-size: 0.88rem; color: var(--t-faint); margin: 10px 0 4px; }
  .rendered :global(p)  { margin-bottom: 10px; }
  .rendered :global(code) { background: var(--bg-card); padding: 2px 5px; border-radius: 3px; font-size: 0.85em; font-family: monospace; }
  .rendered :global(pre)  { background: var(--bg-card); padding: 12px; border-radius: 5px; overflow-x: auto; margin: 10px 0; }
  .rendered :global(pre code) { background: none; padding: 0; }
  .rendered :global(ul)  { padding-left: 20px; margin-bottom: 10px; }
  .rendered :global(li)  { margin-bottom: 4px; }
  .rendered :global(li.done) { color: var(--t-saved); list-style: none; }
  .rendered :global(li.todo) { list-style: none; }
  .rendered :global(a)   { color: var(--t-link); }
  .rendered :global(hr)  { border: none; border-top: 1px solid var(--bd); margin: 16px 0; }
  .rendered :global(strong) { color: var(--t-primary); }

  @media (min-width: 550px) {
    .toolbar    { padding: 12px 18px; }
    .save-status { font-size: 1rem; }
    .edit-btn   { font-size: 1.05rem; padding: 8px 18px; }
    textarea    { font-size: 1.15rem; padding: 20px; }
    .rendered   { font-size: 1.15rem; padding: 20px; }
    .hint       { font-size: 0.9rem; }
    .rendered :global(h1) { font-size: 1.6rem; }
    .rendered :global(h2) { font-size: 1.35rem; }
    .rendered :global(h3) { font-size: 1.15rem; }
    .rendered :global(h4) { font-size: 1.05rem; }
  }
</style>
