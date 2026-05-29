<script>
  import { activeConfig } from '../lib/store.js';
  import { Browser } from '@capacitor/browser';
  import { Capacitor } from '@capacitor/core';

  $: url = $activeConfig?.webview_url || null;

  async function openInBrowser() {
    if (!url) return;
    if (Capacitor.isNativePlatform()) {
      await Browser.open({ url });
    } else {
      window.open(url, '_blank');
    }
  }
</script>

<div class="viewers">
  {#if url}
    <div class="launch">
      <p class="url-text">{url}</p>
      <button class="open-big" on:click={openInBrowser}>Open in Browser</button>
    </div>
  {:else}
    <div class="empty">
      <p>No default URL configured for this project.</p>
      <p class="hint">Set <code>webview_url</code> in the project JSON to show a page here.</p>
    </div>
  {/if}
</div>

<style>
  .viewers { display: flex; flex-direction: column; height: 100%; }

  .launch {
    flex: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 20px; padding: 32px 24px; text-align: center;
  }
  .url-text { color: #555; font-size: 0.78rem; word-break: break-all; margin: 0; }
  .open-big {
    background: #253553; color: #c8ddf7; border: 1px solid #3a5580;
    border-radius: 8px; padding: 14px 40px; font-size: 1.05rem;
  }
  .open-big:hover { background: #2f4470; }

  .empty {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    height: 100%; gap: 8px; color: #555; font-size: 0.9rem; text-align: center; padding: 24px;
  }
  .hint { font-size: 0.8rem; color: #444; }
  .empty :global(code) { color: #7eb8f7; font-size: 0.82rem; }
</style>
