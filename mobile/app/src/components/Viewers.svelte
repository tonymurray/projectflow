<script>
  import { activeConfig, activeProject, theme } from '../lib/store.js';
  import { notesHtmlFilename, loadHtml, loadFromProjectFolder } from '../lib/webdav.js';
  import { Browser } from '@capacitor/browser';
  import { Capacitor } from '@capacitor/core';

  let viewerContent = null;
  let loading = false;
  let error = false;

  // Files to look for inside the project's own subfolder (cop/ for cop.json)
  const DOC_FILES = [
    { filename: 'readme.md',         type: 'md'   },
    { filename: 'todo.md',           type: 'md'   },
    { filename: 'specifications.md', type: 'md'   },
    { filename: 'index.html',        type: 'html' },
  ];

  $: if ($activeProject) findContent($activeProject.filename);

  async function findContent(projectFilename) {
    viewerContent = null;
    error = false;
    loading = true;
    try {
      // 1. Try project subfolder (e.g. ProjectFlow/cop/ for cop.json) — all in parallel
      const subResults = await Promise.allSettled(
        DOC_FILES.map(c => loadFromProjectFolder(projectFilename, c.filename))
      );
      for (let i = 0; i < DOC_FILES.length; i++) {
        if (subResults[i].status === 'fulfilled' && subResults[i].value) {
          viewerContent = { ...DOC_FILES[i], content: subResults[i].value };
          return;
        }
      }
      // 2. Fall back to project-specific HTML in notes folder
      const notesHtml = await loadHtml(notesHtmlFilename(projectFilename));
      if (notesHtml) {
        viewerContent = { type: 'html', filename: notesHtmlFilename(projectFilename), content: notesHtml };
      }
    } catch {
      error = true;
    } finally {
      loading = false;
    }
  }

  $: url = $activeConfig?.webview_url || null;

  $: srcdoc = viewerContent ? buildSrcdoc(viewerContent, $theme) : null;

  function buildSrcdoc({ type, content }, currentTheme) {
    if (type === 'html') return content;
    const html = renderMarkdown(content);
    const dark = currentTheme !== 'light';
    const bg     = dark ? '#0f1117' : '#f8f9fc';
    const fg     = dark ? '#e0e0e0' : '#1a1d26';
    const accent = dark ? '#7eb8f7' : '#1a4fa0';
    const card   = dark ? '#1a1d26' : '#ffffff';
    const bd     = dark ? '#2e3244' : '#c8ccd8';
    return `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
body{font-family:system-ui,sans-serif;background:${bg};color:${fg};padding:16px 20px;line-height:1.7;font-size:15px;margin:0}
h1{font-size:1.3em;color:${accent};border-bottom:1px solid ${bd};padding-bottom:4px;margin:16px 0 8px}
h2{font-size:1.1em;color:${accent};margin:14px 0 6px}
h3,h4{font-size:.95em;margin:12px 0 4px}
p{margin:0 0 10px}
code{background:${card};padding:2px 5px;border-radius:3px;font-size:.85em;font-family:monospace}
pre{background:${card};padding:12px;border-radius:5px;overflow-x:auto;margin:10px 0}
pre code{background:none;padding:0}
ul,ol{padding-left:20px;margin-bottom:10px}
li{margin-bottom:4px}
li.done{color:#6fcf97;list-style:none}
li.todo{list-style:none}
a{color:${accent}}
hr{border:none;border-top:1px solid ${bd};margin:16px 0}
strong{font-weight:600}
</style></head><body>${html}</body></html>`;
  }

  function renderMarkdown(md) {
    if (!md) return '';
    let html = md
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/```[\s\S]*?```/g, m => `<pre><code>${m.slice(3, -3).trim()}</code></pre>`)
      .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^# (.+)$/gm, '<h1>$1</h1>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      .replace(/\[(.+?)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
      .replace(/^- \[x\] (.+)$/gim, '<li class="done">✓ $1</li>')
      .replace(/^- \[ \] (.+)$/gim, '<li class="todo">☐ $1</li>')
      .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
      .replace(/(<li>[\s\S]+?<\/li>)(?!\s*<li>)/g, '<ul>$1</ul>')
      .replace(/^---+$/gm, '<hr>')
      .replace(/\n\n+/g, '</p><p>')
      .replace(/\n/g, '<br>');
    return `<p>${html}</p>`;
  }

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
  {#if loading}
    <div class="status">Loading…</div>

  {:else if viewerContent}
    <div class="file-label">{viewerContent.filename}</div>
    <iframe
      class="html-frame"
      title="Project page"
      srcdoc={srcdoc}
      sandbox="allow-same-origin allow-scripts"
    ></iframe>
    {#if url}
      <div class="url-footer">
        <button class="url-btn" on:click={openInBrowser}>↗ {url}</button>
      </div>
    {/if}

  {:else if url}
    <div class="launch">
      <p class="url-text">{url}</p>
      <button class="open-big" on:click={openInBrowser}>Open in Browser</button>
      <p class="hint-small">Tip: add a <code>readme.md</code>, <code>todo.md</code>, or <code>specifications.md</code> inside the <code>{$activeProject ? $activeProject.filename.replace(/\.json$/, '') : 'project'}/</code> subfolder of your projects folder.</p>
    </div>

  {:else}
    <div class="empty">
      <p>No viewer content for this project.</p>
      <p class="hint">Set <code>webview_url</code> in the project JSON, or add a <code>readme.md</code>, <code>todo.md</code>, <code>specifications.md</code>, or <code>index.html</code> inside the project's subfolder in your projects directory.</p>
    </div>
  {/if}
</div>

<style>
  .viewers { display: flex; flex-direction: column; height: 100%; }

  .status {
    display: flex; align-items: center; justify-content: center;
    height: 100%; color: var(--t-ghost); font-size: 0.9rem;
  }

  .file-label {
    flex-shrink: 0;
    padding: 4px 12px;
    font-size: 0.72rem; font-family: monospace;
    color: var(--t-dimmer);
    background: var(--bg-header);
    border-bottom: 1px solid var(--bd-sub);
  }

  .html-frame {
    flex: 1; width: 100%; border: none;
  }

  .url-footer {
    flex-shrink: 0;
    border-top: 1px solid var(--bd-sub);
    padding: 6px 12px;
  }
  .url-btn {
    background: none; border: none; color: var(--accent);
    font-size: 0.78rem; padding: 4px 0; text-align: left;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    max-width: 100%; display: block;
  }

  .launch {
    flex: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 20px; padding: 32px 24px; text-align: center;
  }
  .url-text { color: var(--t-ghost); font-size: 0.78rem; word-break: break-all; margin: 0; }
  .open-big {
    background: var(--bg-active); color: var(--t-active); border: 1px solid var(--bd-active);
    border-radius: 8px; padding: 14px 40px; font-size: 1.05rem;
  }
  .open-big:hover { background: var(--bg-active-hi); }
  .hint-small { font-size: 0.72rem; color: var(--t-dimmer); max-width: 280px; line-height: 1.5; }
  .hint-small code { color: var(--accent-hi); }

  .empty {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    height: 100%; gap: 8px; color: var(--t-ghost); font-size: 0.9rem; text-align: center; padding: 24px;
  }
  .hint { font-size: 0.8rem; color: var(--t-dimmer); }
  .empty :global(code) { color: var(--accent-hi); font-size: 0.82rem; }
</style>
