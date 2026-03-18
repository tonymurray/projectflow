# ProjectFlow Vibe Programming Prompts

This document captures the conversation prompts used to develop and modify ProjectFlow with Claude Code.

---

## Session: All Projects Feature & UI Refinements

### 1. Add All Projects Section

**User:**
> I am wondering if it is possible to create a section at the bottom of the page that just lists all configs found in the folder, in alphabetical order. Currently the control buttons are at the bottom, which is nice. It would be good if the new section were 'out of sight' so the control buttons remain at the bottom. If it is easier, there could be a toggle button between Edit Mode and Load Config.. called All configs that reveals all the configs below (buttons). It would also be useful if these buttons triggered new instances of projectflow.py (like 'open new window')

**Claude:**
> Added an "All Configs" feature:
> - Purple "📁 All Configs" toggle button between Edit Mode and Load Config
> - Clicking it reveals a collapsible section below the control buttons
> - Shows all `.json` files from the configs folder in alphabetical order (4-column grid)
> - Current config highlighted in green
> - Clicking any config button launches a new projectflow instance with that config

---

### 2. Rename to "Projects" and Change Colors

**User:**
> That works, but can you change the icon to be same as the projectflow icon (preferences-desktop-icons) or else just a books icon 📚. I would also like to make the term 'configs' in the interface button texts changed to 'Projects', so Load Project, Duplicate Project.. All Projects. Then can you remove the purple color scheme, and instead just use the same green as the right-adjacent button, and for the 'Config/Projects' buttons below, use the same blue color as the recent configs/projects buttons on top? Is this too many changes at once?

**Claude:**
> All changes made:
> 1. Icon: Changed from 📁 to 📚 (books)
> 2. Button labels renamed to "Project": All Projects, Load Project, Duplicate Project, Edit Project
> 3. All Projects button: Now uses the same dark green (#094d2e) as Load Project
> 4. Project buttons in grid: Now use the same blue (#1e5a8e) as the recent projects bar
> 5. Header label: Updated text and color to match (blue #1e5a8e)

---

### 3. Add New Window Buttons to Recent Projects

**User:**
> That works great. Now it would also be useful to optionally open the recent configs in a new window. Like we have 'preview' icon for Firefox links that open in web view, could there be a small button to right of each config with icon '↗️' that opens in a new window instead of replacing the current project?

**Claude:**
> Each recent project button now has a small "↗️" button on its right side that opens that project in a new window. The buttons are visually connected (rounded corners only on outer edges) and the new-window button uses a slightly darker shade to distinguish it.

---

### 4. Reorder Buttons and Unify Colors

**User:**
> Just some other cosmetic change. Can the config button order be changed to: Edit mode, Refresh, Edit Project, Set as Default, Duplicate Project, Load Project, All Projects. Then the color of both Edit Mode and All Projects on left and right would the same (a slightly more blue/navy color: #0e3558, with all the 5 center buttons being the same green color #094D2E?

**Claude:**
> Button order is now:
> 1. Edit Mode (navy #0e3558)
> 2. Refresh (green #094D2E)
> 3. Edit Project (green #094D2E)
> 4. Set as Default (green #094D2E)
> 5. Duplicate Project (green #094D2E)
> 6. Load Project (green #094D2E)
> 7. All Projects (navy #0e3558)
>
> The two toggle buttons on the ends are now navy, and all five action buttons in the center share the same green.

---

### 5. Commit and Push

**User:**
> great please commit and push this

**Claude:**
> Committed and pushed with message: "Add All Projects section and new window buttons"

---

### 6. Code Location for Tweaking New Window Buttons

**User:**
> I would like to tweak the spacing, layout heights of the new 'open in new window' buttons at the top. Could you point me to the location in the code?

**Claude:**
> The new window buttons are in `projectflow.py` around lines 740-790, in the `create_recent_configs_bar` method:
> - Line ~714: `btn_container_layout.setSpacing(1)` - gap between main button and ↗️ button
> - Line ~756: `new_window_btn.setFixedWidth(28)` - width of the ↗️ button
> - Lines ~758-772: height and styling for current config's ↗️ button
> - Lines ~774-790: height and styling for other configs' ↗️ buttons

**User:**
> and what about the config buttons themselves?

**Claude:**
> The main recent project buttons are in the same method, just above:
> - Lines ~701-702: `btn = QPushButton(...)` and `btn.setMaximumWidth(150)`
> - Lines ~704-720: styling for current config button (height 32, bold, white border)
> - Lines ~722-738: styling for other config buttons (height 26, smaller font)

**User:**
> how about the gap between the buttons (not between main button and ↗ button)

**Claude:**
> That's set on the main buttons layout:
> - Line ~675: `buttons_layout.setSpacing(5)` - gap between each button pair

---

### 7. Reduce Recent Projects Limit

**User:**
> OK, i adjusted. Could we now make the number of recent configs/projects 5 (including current) instead of 8 - to create more focused view, since there are also all configs at the bottom?

**Claude:**
> Changed the recent projects limit from 8 to 5 in all four locations (comments and code).

---

### 8. Add Edit Mode Button to Column Header

**User:**
> I would like to add a copy of 'Edit Mode off' button with a small pencil icon (no text) at the top of the title of the first column if that is possible? It would have the same functionality, just more accessible

**Claude:**
> Added a small pencil button (✏️) to the left of the first column header:
> - 28x28 pixels with the same grey background as the header
> - Turns green when edit mode is on
> - Stays synced with the main Edit Mode button at the bottom

---

### 9. Add New Window Buttons to All Projects

**User:**
> Another change - I like the functionality of top recent configs with default open in same window, then the small icon to open in a new 'window'. Can that be replicated in the All Projects section at the bottom?

**Claude:**
> The All Projects section now has the same pattern:
> - Main button switches to the config in the current window
> - Small ↗️ button on the right opens it in a new window

---

### 10. Improve Window Title Format

**User:**
> Another usability change. In the window task manager entry, there are two lines like some other projects. Could the config come first, remove the _config if present, and remove the .json if present, and make capitalized. So it would read for example Main - ProjectFlow

**Claude:**
> Window title now shows the cleaned config name first, e.g., "Main - ProjectFlow" instead of "ProjectFlow - main_config.json":
> - Removes `.json` and `_config`
> - Replaces underscores with spaces
> - Capitalizes with `.title()`
> - Format: `{Config Name} - ProjectFlow`

---

### 11. Fix Kate Not Opening Folders

**User:**
> There is another thing - opening a file with the command kate works fine, but if a folder is specified, then kate does not open the folder. Maybe it needs to open new instance. Not sure if there is a command line option - maybe not possible

**Claude:**
> Kate's command line folder support is limited. Added special handling to open Dolphin instead when kate is specified for a directory.

---

### 12. Add Category Button in Edit Mode

**User:**
> Another change - in edit mode, would it be a lot of work to have buttons to 'Add category' under each 'Add entry' Clicking would add a new category, with a blank entry, and under a 'add new entry' button like other sections. Button color can be blue like the category headers?

**Claude:**
> Added:
> - Blue "➕ Add Category" button at the bottom of each column in edit mode
> - Clicking creates a new category called "New Category" with one blank entry
> - The new category has the same "Add Entry" button as other categories

---

### 13. Add Image Viewer to Central Column

**User:**
> In the central column there is either a web browser or a PDF browser, is it possible to also have option to display and load an image - similar to loading a pdf. The button would be called 'Image', similar to pdf/webpage you can specify one in the settings, or load from file picker?

**Claude:**
> Added Image Viewer as third mode in central column:
> - Cycles through PDF → Web → Image → PDF
> - Toolbar with Open button, zoom controls (-/+), and fit-to-width
> - Supports PNG, JPG, GIF, BMP, WebP formats
> - Image path persists in config

---

### 14. Default Image and Column2 Mode Config Options

**User:**
> how to set the image as default for the particular project? ... also maybe an option to determine which out of image_file, pdf_file and webview_url to display when the project is opened. maybe "column2_default": "image" - to display image file first etc.

**Claude:**
> Added config options:
> - `"image_file": "/path/to/image.png"` - default image for a project
> - `"column2_default": "image"` - which viewer (pdf/webview/image) opens by default

---

### 15. Auto-Fit Image to Width

**User:**
> is it possible that the image view always opens in fit mode

**Claude:**
> Images now auto-fit to width when loaded.

**User:**
> i think the image file is still not loading in 'fit' mode on opening a project?

**Claude:**
> Fixed by deferring fit-to-width with 500ms delay using `QTimer.singleShot` to allow viewport to fully size on startup.
