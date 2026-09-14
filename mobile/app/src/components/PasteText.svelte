<script>
  import { createEventDispatcher } from 'svelte';
  import { pendingShare } from '../lib/store.js';

  const dispatch = createEventDispatcher();
  let text = '';
  let textarea;

  function onBackdrop(e) {
    if (e.target === e.currentTarget) dispatch('close');
  }

  // Hands off to the exact same pendingShare/ShareTarget flow the Android share sheet
  // already uses — project picker, URL-vs-text detection, and offline queueing all come
  // for free from there. This component's only job is getting typed/pasted text (e.g.
  // copied out of WhatsApp/Signal, whose own Share action often doesn't offer a clean
  // plain-text option) into that same pipe without going through Android's share sheet.
  function next() {
    const trimmed = text.trim();
    if (!trimmed) return;
    pendingShare.set({ text: trimmed, subject: null });
    dispatch('close');
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="backdrop" on:click={onBackdrop}>
  <div class="panel">
    <div class="panel-header">
      <span class="title">Paste Text or Link</span>
      <button class="close-btn" on:click={() => dispatch('close')}>✕</button>
    </div>

    <div class="content">
      <div class="hint">Paste or type text (e.g. copied from WhatsApp/Signal) or a link — you'll pick which project's note or launchers it goes to next.</div>
      <textarea
        bind:this={textarea}
        bind:value={text}
        placeholder="Paste here…"
      ></textarea>
      <div class="actions">
        <button class="cancel-btn" on:click={() => dispatch('close')}>Cancel</button>
        <button class="add-btn" on:click={next} disabled={!text.trim()}>Next</button>
      </div>
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

  .content { padding: 14px 16px; }

  .hint {
    font-size: 0.78rem; color: var(--t-ghost);
    margin-bottom: 10px;
  }

  textarea {
    width: 100%; min-height: 140px; box-sizing: border-box;
    background: var(--bg-body); color: var(--t-primary);
    border: 1px solid var(--bd-sub); border-radius: 8px;
    padding: 10px 12px; font-size: 0.9rem; line-height: 1.5;
    resize: vertical; margin-bottom: 12px;
  }
  textarea:focus { outline: none; border-color: var(--accent); }

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
    textarea { font-size: 1rem; min-height: 180px; }
    .cancel-btn, .add-btn { font-size: 1.05rem; padding: 11px 20px; }
  }
</style>
