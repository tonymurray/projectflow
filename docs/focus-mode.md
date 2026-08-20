# Focus Mode

Focus mode is an alternative layout for projects that are heavy on reading —
documentation, research, reference material — where you want less clicking
around and more screen space for the thing you're actually reading.

## Switching layouts

Every project has two layouts:

- **Standard layout** (default): the usual three columns — Launchers | Viewer | Notes.
- **Focus layout**: two columns — Launchers (narrow) | Viewer (wide). Your notes
  move into a tab inside the viewer instead of sitting in their own column.

Toggle between them with the button at the right of the title bar:

| Button | Meaning |
|---|---|
| `⊞ Focus` | You're in Standard layout — click to switch to Focus |
| `▣ Notes` | You're in Focus layout — click to switch back to Standard |

Each project remembers its own layout choice. Switch a project to Focus mode,
close ProjectFlow, and it reopens in Focus mode next time — the setting is
saved into that project's own config file, so it travels with the project
(e.g. if it syncs via Nextcloud).

## What changes in Focus mode

Two things happen automatically when you switch to Focus:

1. **Clicking launchers opens them in the built-in viewer instead of an
   external app.** A web link, an image, a PDF, or a local `.md`/`.html`
   file that would normally launch Firefox, Gwenview, etc., instead opens
   right there in the wide viewer panel next to your launchers. This is the
   whole point of Focus mode — stay in one window, don't context-switch to
   other apps.

   Every launcher that supports this still has a small preview-style button
   next to it. In Focus mode, that button flips its meaning to **"open
   externally"** — it's your escape hatch when you *do* want the real
   external app instead (e.g. editing an image in GIMP rather than just
   viewing it).

2. **Launchers are automatically grouped by type** (see below), so a long,
   mixed list of links becomes three tidy sections instead of whatever
   category structure you set up. You can turn this off if you'd rather see
   your normal categories — see below.

## Group-by-Type view

Toggle: the **☰ Group** button in the launcher column header.

Normally your launchers are organized into whatever categories you created
(e.g. "Dev Tools", "Client Docs", "Backups"). Group-by-Type is a different
way of *looking* at the same launchers — it re-sorts everything into three
fixed sections instead:

- **Documentation** — local `.md`, `.html`, `.htm`, `.pdf`, `.txt` files
- **Websites** — links opened via Firefox/Chrome, or anything starting with `http://`/`https://`
- **Resources** — everything else

This is purely a display mode. **It never edits your project file or moves
anything between categories.** Your real categories are still there,
unchanged — Group-by-Type is just a different lens over the same data.
Turning it off instantly restores your normal category view.

Focus mode turns this on by default, since a flat Documentation / Websites /
Resources split usually fits a reading-focused project better than
hand-maintained categories. You can turn it off per-session with the ☰
button any time; it won't be forced back on until you switch away from the
project and back (or reopen it).

### Fixing a misclassified item

The heuristic above is simple (mostly based on file extension), so it will
occasionally put something in the "wrong" bucket — a `.txt` changelog you'd
rather see as a Resource, for instance. Right-click the item and choose
**"📁 Move display to…"**, then pick the bucket you want. This preference is
remembered per item and always wins over the automatic guess from then on.

It's saved to your local `.projectflow_settings.json`, not the project file
— so, like the grouping view itself, it's a personal display preference
rather than something that changes what the project "is."

## Adding a new launcher while grouped

Because Documentation/Websites/Resources aren't real categories, you can't
add an item directly "into" one from the grouped view. Add it the normal
way and let it fall into place automatically:

1. Click **✏️ Edit**. This temporarily turns off Group-by-Type and shows
   your real categories, so you always add/edit against real project
   structure — never the virtual grouped view.
2. Click **Add Entry** under whichever real category makes sense to you
   (or use the **+ Add** button, which adds to your first category).
3. Set its path. If you want it to land in **Documentation**, give it a
   `.md`, `.html`, `.htm`, `.pdf`, or `.txt` path. For **Websites**, use a
   `firefox`/`chrome` launcher or an `http(s)://` link. Anything else lands
   in **Resources**.
4. Click **✏️ Edit** again to leave edit mode. Grouping resumes, and the new
   item appears in the section its extension/type matches.

If it lands in the bucket you didn't want, right-click → "📁 Move display
to…" to override it, as above.

## Summary

| Feature | Where | Persisted where |
|---|---|---|
| Focus vs. Standard layout | `⊞ Focus` / `▣ Notes` button, title bar | Project's own config file (`layout_mode`) |
| Group-by-Type view | `☰ Group` button, launcher header | Not persisted — resets to layout default each time you open the project |
| Per-item bucket override | Right-click → "📁 Move display to…" | Local `.projectflow_settings.json` (per machine) |
| Open externally instead | Small button next to a launcher, in Focus mode | N/A (one-off action) |
