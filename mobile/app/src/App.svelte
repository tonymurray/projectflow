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
  :global(*, *::before, *::after) { box-sizing: border-box; margin: 0; padding: 0; }
  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f1117;
    color: #e0e0e0;
    height: 100dvh;
    overflow: hidden;
  }
  :global(button) { cursor: pointer; }
</style>
