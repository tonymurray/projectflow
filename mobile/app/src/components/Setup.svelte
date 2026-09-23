<script>
  import { config } from '../lib/store.js';
  import SettingsForm from './SettingsForm.svelte';
</script>

<div class="setup">
  <h1>ProjectFlow</h1>
  <p class="sub">Connect to your Nextcloud</p>
  <SettingsForm initial={null} on:save={(e) => config.set(e.detail)} />
</div>

<style>
  .setup {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 40px 24px;
    min-height: 100dvh;
  }
  h1 { font-size: 1.8rem; color: var(--accent-hi); margin-bottom: 4px; }
  .sub { color: var(--t-faint); margin-bottom: 32px; font-size: 0.9rem; }
</style>
