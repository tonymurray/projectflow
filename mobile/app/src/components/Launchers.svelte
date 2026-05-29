<script>
  import { activeConfig, isMobileLauncher, getLaunchUrl } from '../lib/store.js';

  $: categories = $activeConfig?.columns?.[0] ?? [];
  $: mobileCats = categories.map(cat => {
    const name = Object.keys(cat)[0];
    const items = (cat[name] || []).filter(item => isMobileLauncher(item[2] || '', item[1] || ''));
    return { name, items };
  }).filter(c => c.items.length > 0);

  function launch(item) {
    const url = getLaunchUrl(item[1], item[2]);
    if (url) window.open(url, '_blank');
  }
</script>

<div class="launchers">
  {#if !$activeConfig}
    <p class="empty">No project selected</p>
  {:else if mobileCats.length === 0}
    <p class="empty">No mobile-compatible launchers</p>
  {:else}
    {#each mobileCats as cat}
      <div class="category">
        <div class="cat-header">{cat.name}</div>
        {#each cat.items as item}
          {@const url = getLaunchUrl(item[1], item[2])}
          <button
            class="launcher"
            class:link={!!url}
            on:click={() => launch(item)}
            disabled={!url}
            title={url ? item[1] : 'Not available on mobile'}
          >
            <span class="name">{item[0]}</span>
            {#if url}
              <span class="arrow">↗</span>
            {:else}
              <span class="na">desktop only</span>
            {/if}
          </button>
        {/each}
      </div>
    {/each}
  {/if}
</div>

<style>
  .launchers { padding: 12px; }
  .empty { color: #555; font-size: 0.9rem; padding: 24px; text-align: center; }

  .category { margin-bottom: 16px; }
  .cat-header {
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: #4a7fc1;
    padding: 4px 0 6px; margin-bottom: 4px;
    border-bottom: 1px solid #1e2235;
  }

  .launcher {
    display: flex; align-items: center; justify-content: space-between;
    width: 100%; background: #1a1d26; border: 1px solid #2e3244;
    border-radius: 6px; padding: 10px 14px; margin-bottom: 4px;
    color: #ccc; font-size: 0.9rem; text-align: left;
  }
  .launcher.link { color: #e0e0e0; }
  .launcher.link:hover { background: #202436; border-color: #3a5580; }
  .launcher:disabled { opacity: 0.45; cursor: default; }

  .name { flex: 1; }
  .arrow { color: #4a7fc1; font-size: 0.8rem; margin-left: 8px; }
  .na { font-size: 0.72rem; color: #444; margin-left: 8px; }
</style>
