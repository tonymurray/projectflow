<script>
  // Shared icon component: inline-injects a vendored SVG by name so its stroke/fill
  // can inherit `currentColor` from CSS (an <img src="...svg"> can't theme this way —
  // it's an opaque bitmap-like resource as far as CSS color inheritance is concerned).
  export let name;
  export let size = '1.2em';

  const icons = import.meta.glob('../assets/icons/*.svg', { eager: true, query: '?raw', import: 'default' });
  $: markup = icons[`../assets/icons/${name}.svg`] || '';
</script>

<span class="icon" style="width:{size};height:{size}" aria-hidden="true">
  {@html markup}
</span>

<style>
  .icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: inherit;
    flex-shrink: 0;
  }
  .icon :global(svg) {
    width: 100%;
    height: 100%;
  }
</style>
