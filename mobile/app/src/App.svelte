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
