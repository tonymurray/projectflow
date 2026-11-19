<script>
  import { createEventDispatcher } from 'svelte';
  import { config } from '../lib/store.js';
  import SettingsForm from './SettingsForm.svelte';
  import Icon from './Icon.svelte';

  const dispatch = createEventDispatcher();

  function onBackdrop(e) {
    if (e.target === e.currentTarget) dispatch('close');
  }

  function onSave(e) {
    config.set(e.detail);
    dispatch('close');
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="backdrop" on:click={onBackdrop}>
  <div class="panel">
    <div class="panel-header">
      <span class="title">Settings</span>
      <button class="close-btn" on:click={() => dispatch('close')}><Icon name="close" size="1.1em" /></button>
    </div>

    <div class="content">
      <SettingsForm initial={$config} on:save={onSave} />
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
    background: var(--m3-surface-container-high); border: 1px solid var(--m3-outline);
    border-radius: var(--radius-lg); width: 100%; max-width: 480px;
    max-height: 88vh; display: flex; flex-direction: column;
    overflow: hidden;
    box-shadow: var(--elevation-2);
  }

  .panel-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 16px; border-bottom: 1px solid var(--m3-outline-variant);
    flex-shrink: 0;
  }
  .title { font-size: 1rem; font-weight: 600; color: var(--t-primary); }
  .close-btn {
    background: none; border: none; color: var(--t-muted);
    padding: 6px; line-height: 1; border-radius: var(--radius-full);
    display: flex; align-items: center;
  }

  .content { padding: 14px 16px; overflow-y: auto; }

  @media (min-width: 550px) {
    .title { font-size: 1.2rem; }
    .close-btn { font-size: 1.3rem; }
  }
</style>
