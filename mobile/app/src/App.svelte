<script>
  import { config } from './lib/store.js';
  import Setup from './components/Setup.svelte';
  import Main from './components/Main.svelte';
</script>

{#if $config && $config.password}
  <Main />
{:else}
  <Setup />
{/if}

<style>
  /* ── Theme variables ─────────────────────────────────────────────────────── */
  :global(:root) {
    --bg-body:       #0f1117;
    --bg-header:     #12151f;
    --bg-card:       #1a1d26;
    --bg-hover:      #202436;
    --bg-active:     #253553;
    --bg-active-hi:  #2f4470;
    --bd:            #2e3244;
    --bd-sub:        #1e2235;
    --bd-active:     #3a5580;
    --accent:        #4a7fc1;
    --accent-hi:     #7eb8f7;
    --t-primary:     #ffffff;
    --t-sec:         #f0f0f0;
    --t-muted:       #d8d8d8;
    --t-faint:       #c0c0c0;
    --t-dim:         #a8a8a8;
    --t-ghost:       #909090;
    --t-dimmer:      #787878;
    --t-darkest:     #606060;
    --t-active:      #d8eaff;
    --t-heading:     #c0d8f8;
    --t-saved:       #6fcf97;
    --t-unsaved:     #c07840;
    --t-error:       #eb5757;
    --t-link:        #5b9bd5;

    /* ── Material 3 role tier (additive — existing vars above stay the source of truth for hue) ── */
    --m3-primary:                 var(--accent-hi);
    --m3-on-primary:              #0f1117;
    --m3-primary-container:       #2a3f66;
    --m3-on-primary-container:    #cfe2ff;
    --m3-secondary-container:     #1f3d2c;
    --m3-on-secondary-container:  #9eeec0;
    --m3-surface:                 var(--bg-body);
    --m3-surface-container-low:   var(--bg-header);
    --m3-surface-container:       var(--bg-card);
    --m3-surface-container-high:  #20243a;
    --m3-surface-container-highest: #262b45;
    --m3-outline:                 var(--bd);
    --m3-outline-variant:         var(--bd-sub);
    --m3-nav-pill:                var(--bg-active-hi);
    --m3-on-nav-pill:             var(--accent-hi);

    --elevation-0: none;
    --elevation-1: 0 1px 3px rgba(0,0,0,0.4);
    --elevation-2: 0 8px 32px rgba(0,0,0,0.5);

    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 14px;
    --radius-full: 999px;
  }
  :global([data-theme="light"]) {
    --bg-body:       #f0f2f7;
    --bg-header:     #e2e6f2;
    --bg-card:       #ffffff;
    --bg-hover:      #edf2fa;
    --bg-active:     #dce6f4;
    --bg-active-hi:  #c8d8f0;
    --bd:            #c8ccd8;
    --bd-sub:        #d8dce8;
    --bd-active:     #4a7fc1;
    --accent:        #2b65b5;
    --accent-hi:     #1a4fa0;
    --t-primary:     #1a1d26;
    --t-sec:         #3a3d48;
    --t-muted:       #555555;
    --t-faint:       #777777;
    --t-dim:         #888888;
    --t-ghost:       #999999;
    --t-dimmer:      #aaaaaa;
    --t-darkest:     #bbbbbb;
    --t-active:      #1a3a7a;
    --t-heading:     #2756a0;
    --t-saved:       #2a8a50;
    --t-unsaved:     #b06010;
    --t-error:       #cc2222;
    --t-link:        #1a56c4;

    /* ── Material 3 role tier (additive) ── */
    --m3-primary:                 var(--accent);
    --m3-on-primary:              #ffffff;
    --m3-primary-container:       #d8e6fb;
    --m3-on-primary-container:    #163865;
    --m3-secondary-container:     #d7f3e1;
    --m3-on-secondary-container:  #14602f;
    --m3-surface:                 var(--bg-body);
    --m3-surface-container-low:   var(--bg-header);
    --m3-surface-container:       var(--bg-card);
    --m3-surface-container-high:  #eef1f5;
    --m3-surface-container-highest: #e4e9f5;
    --m3-outline:                 var(--bd);
    --m3-outline-variant:         var(--bd-sub);
    --m3-nav-pill:                var(--bg-active);
    --m3-on-nav-pill:             var(--accent);

    --elevation-0: none;
    --elevation-1: 0 1px 3px rgba(0,0,0,0.4);
    --elevation-2: 0 8px 32px rgba(0,0,0,0.5);

    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 14px;
    --radius-full: 999px;
  }

  /* Scale base font up on larger screens (tablets/e-readers); phones clamp at 16px */
  :global(html) { font-size: clamp(16px, 2.2vw, 26px); }

  :global(*, *::before, *::after) { box-sizing: border-box; margin: 0; padding: 0; }
  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg-body);
    color: var(--t-primary);
    height: 100dvh;
    overflow: hidden;
  }
  :global(button) { cursor: pointer; }
</style>
