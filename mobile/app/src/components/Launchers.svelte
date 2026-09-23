<script>
  import { Capacitor, registerPlugin } from '@capacitor/core';
  import { activeConfig, isMobileLauncher, getLaunchUrl, config } from '../lib/store.js';
  import { resolveToNextcloudRelPath, nextcloudWebUrl, getNextcloudFileId } from '../lib/webdav.js';

  const NextcloudApp = Capacitor.isNativePlatform() ? registerPlugin('NextcloudApp') : null;

  $: categories = $activeConfig?.columns?.[0] ?? [];
  $: viewerUrl = $activeConfig?.webview_url || null;
  $: mobileCats = categories.map(cat => {
    const name = Object.keys(cat)[0];
    const items = (cat[name] || []).filter(item => isMobileLauncher(item[2] || '', item[1] || ''));
    return { name, items };
  }).filter(c => c.items.length > 0);

  // Best-effort: builds a Nextcloud "direct link" (https://server/f/{fileid}) from the
  // file's WebDAV oc:fileid and hands it to the native plugin, which targets the Nextcloud
  // app explicitly by package (see NextcloudAppPlugin.java for why — no nc:// scheme is
  // actually involved). Returns false on ANY failure — missing file ID, app not installed,
  // anything — so the caller falls straight through to the normal, always-working browser
  // open. This experimental path must never be able to leave a tap dead.
  async function tryOpenInNextcloudApp(fileId) {
    if (!NextcloudApp || !fileId) return false;
    const directUrl = `${$config.server}/f/${fileId}`;
    try {
      const { opened } = await NextcloudApp.openUri({ uri: directUrl });
      return !!opened;
    } catch {
      return false;
    }
  }

  async function launch(item) {
    const url = getLaunchUrl(item[1], item[2]);
    if (url) { window.open(url, '_blank'); return; }
    const ncRel = resolveToNextcloudRelPath(item[1]);
    if (!ncRel) return;
    // Looked up once and shared by both paths below: the file's own Nextcloud web page
    // deep-links straight to it (not just its containing folder) when the ID is known, and
    // the same ID is what the experimental Nextcloud-app path needs too — no reason to
    // fetch it twice if that path is tried first and falls through to the browser.
    const fileId = await getNextcloudFileId(ncRel);
    if ($config?.openMethod === 'nextcloud-app' && await tryOpenInNextcloudApp(fileId)) return;
    window.open(nextcloudWebUrl(ncRel, fileId), '_blank');
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
          {@const ncRel = resolveToNextcloudRelPath(item[1])}
          <button
            class="launcher"
            class:link={!!url || !!ncRel}
            on:click={() => launch(item)}
            disabled={!url && !ncRel}
            title={url ? item[1] : ncRel ? 'Open in Nextcloud' : 'Not available on mobile'}
          >
            <span class="name">{item[0]}</span>
            {#if url}
              <span class="arrow">↗</span>
            {:else if ncRel}
              <span class="arrow nc">NC↗</span>
            {:else}
              <span class="na">desktop only</span>
            {/if}
          </button>
        {/each}
      </div>
    {/each}
    {#if viewerUrl}
      <div class="category">
        <div class="cat-header">Links (viewers)</div>
        <button class="launcher link" on:click={() => window.open(viewerUrl, '_blank')} title={viewerUrl}>
          <span class="name">Open Web Viewer</span>
          <span class="arrow">↗</span>
        </button>
      </div>
    {/if}
  {/if}
</div>

<style>
  .launchers { padding: 12px; }
  .empty { color: var(--t-ghost); font-size: 0.9rem; padding: 24px; text-align: center; }

  .category { margin-bottom: 16px; }
  .cat-header {
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--accent);
    padding: 4px 0 6px; margin-bottom: 4px;
    border-bottom: 1px solid var(--bd-sub);
  }

  .launcher {
    display: flex; align-items: center; justify-content: space-between;
    width: 100%; background: var(--bg-card); border: 1px solid var(--bd);
    border-radius: 6px; padding: 10px 14px; margin-bottom: 4px;
    color: var(--t-sec); font-size: 0.9rem; text-align: left;
  }
  .launcher.link { color: var(--t-primary); }
  .launcher.link:hover { background: var(--bg-hover); border-color: var(--bd-active); }
  .launcher:disabled { opacity: 0.45; cursor: default; }

  .name { flex: 1; }
  .arrow { color: var(--accent); font-size: 0.8rem; margin-left: 8px; }
  .arrow.nc { color: var(--t-muted); font-size: 0.68rem; }
  .na { font-size: 0.72rem; color: var(--t-dimmer); margin-left: 8px; }

  @media (min-width: 550px) {
    .launchers  { padding: 16px; }
    .empty      { font-size: 1.1rem; }
    .cat-header { font-size: 0.9rem; padding: 6px 0 10px; margin-bottom: 8px; }
    .launcher   { font-size: 1.1rem; padding: 14px 18px; margin-bottom: 8px; }
    .arrow      { font-size: 1rem; }
    .na         { font-size: 0.9rem; }
    .category   { margin-bottom: 24px; }
  }
</style>
