# Theme definitions for ProjectFlow
# Light and dark color schemes

# =============================================================================
# DIMENSIONS - Desktop environment specific sizing
# =============================================================================
# Add dimension overrides as needed. Keys not found fall back to "default".
# Usage in code: self.d('btn_height')

DIMENSIONS = {
    "default": {
        # Header toolbar buttons (Edit/Done, Refresh, PDF/Web/Help/Console toggles)
        "header_btn_height": 26,
        # Section title labels (Shortcuts and Actions, Web view, Notes)
        "header_label_height": 28,
        # Padding inside header labels
        "header_label_padding": 5,
    },
    "kde": {
        # KDE-specific overrides (if needed)
        # Usually matches default since that's the development baseline
    },
    "gnome": {
        # GNOME-specific overrides
        # Add overrides here as you find elements that need adjusting
        "header_btn_height": 32,
        "header_label_height": 32,
        "header_label_padding": 5,
    },
}


def get_dimensions(de_name="default"):
    """Get dimensions for a desktop environment with fallback to default"""
    de_dims = DIMENSIONS.get(de_name, {})
    default_dims = DIMENSIONS.get("default", {})
    # Merge: DE-specific overrides default
    merged = default_dims.copy()
    merged.update(de_dims)
    return merged


# =============================================================================
# THEMES - Color schemes
# =============================================================================

THEMES = {
    "light": {
        # Backgrounds
        "bg_primary": "#ffffff",
        "bg_secondary": "#f5f5f5",
        "bg_panel": "#5a5a5a",
        "bg_input": "#f5f5f0",
        "bg_button": "#ecf0f1",
        "bg_button_hover": "#3498db",
        "bg_group": "#ffffff",

        # Neutral grey hover for the folder-browser tree/icon-grid views specifically
        # (main Folder viewer + the Focus-layout launcher panel's own copy) — NOT the
        # general bg_button_hover, which is this theme's own #3498db, the exact same blue
        # as the hand-drawn folder icon (_blue_folder_icon()). Hovering a folder item used
        # to make its icon visually vanish into the identical-color hover background — a
        # real reported bug, not just a close call. Picked as a mid-grey (Dolphin itself
        # uses a near-white ~#f2f2f2, but this app's list background is already
        # bg_secondary #f5f5f5, so a hover that light gave almost no visible contrast here)
        # — reuses the same grey as bg_config/bg_config_hover's family rather than
        # inventing an unrelated shade. Item text color is deliberately left unset on
        # hover (no matching fg_list_hover) so it just keeps whatever the item's own
        # fg_primary already is — only the background changes, matching Dolphin's own
        # hover behavior.
        "bg_list_hover": "#e0e0e0",

        # Category/accent colors
        "bg_category": "#3498db",
        "bg_category_hover": "#2980b9",
        # Dedicated resting/active pair for the launcher tab row specifically (not the
        # general bg_category/bg_category_hover above, which are reused in ~30 other
        # places). Active must be *brighter* than resting to match the viewer tab row's
        # convention (see CLAUDE.md's Active-tab indicator note) — but which of
        # bg_category/a scaled variant is naturally brighter flips between themes: in light
        # theme bg_category (L=135.6) is already the brighter of the two so it's reused as
        # tab_launcher_active, and tab_launcher_resting is a new color scaled *down* from it
        # (L=85.6, a -49.9 drop, sized to match the viewer row's own bg_green_1->bg_green_3
        # gap in magnitude). Dark theme is the mirror image — see dark section below.
        "tab_launcher_resting": "#21608a",
        "tab_launcher_active": "#3498db",
        "bg_success": "#27ae60",
        "bg_success_hover": "#2ecc71",
        "bg_danger": "#e74c3c",
        "bg_danger_hover": "#c0392b",
        "bg_warning": "#f39c12",
        "bg_purple": "#3DAEE9",
        "bg_purple_light": "#eaf6fc",

        # Navy/action buttons
        "bg_navy": "#0e3558",
        "bg_navy_hover": "#1a4a6e",
        "bg_navy_checked": "#e67e22",

        # Green gradient for bottom buttons
        "bg_green_1": "#094d2e",
        "bg_green_2": "#0d5f3a",
        "bg_green_3": "#168a5f",
        "bg_green_4": "#27ae60",

        # Recent/All configs (subtle grey)
        "bg_config_current": "#d0d0d0",
        "bg_config": "#e0e0e0",
        "bg_config_hover": "#c0c0c0",
        "bg_config_arrow": "#d8d8d8",
        # All Projects (more subtle than Recent)
        "bg_config_all": "#ebebeb",
        "bg_config_all_current": "#e0e0e0",
        "bg_config_all_arrow": "#e8e8e8",

        # Text colors
        "fg_primary": "#333333",
        "fg_secondary": "#555555",
        "fg_muted": "#888888",
        "fg_on_dark": "#ffffff",
        "fg_on_button": "#333333",
        "fg_link": "#3498db",

        # Borders
        "border": "#bdc3c7",
        "border_dark": "#999999",
        "border_light": "#f4f4f4",

        # Status colors
        "status_success": "#27ae60",
        "status_error": "#e74c3c",
        "status_info": "#17a2b8",
        "status_warning": "#f39c12",

        # Code/console
        "bg_code": "#2d2d2d",
        "fg_code": "#f0f0f0",
        "bg_console": "#1e1e1e",

        # Viewer areas
        "bg_viewer": "#404040",

        # Markdown highlight
        "bg_highlight": "#9c0c15",

        # Help viewer markdown content
        "bg_help": "#f5f5f5",
        "bg_code_inline": "#e8e8e8",
        "fg_help_h1": "#2c3e50",
        "fg_help_h2": "#34495e",
        "fg_help_h3": "#7f8c8d",
        "border_help_h1": "#3498db",
        "border_help_h2": "#bdc3c7",

        # Examples viewer
        "bg_example_card": "#ffffff",
        "border_example_card": "#e0e0e0",
        "bg_example_type_builtin": "#27ae60",   # Green for built-in
        "bg_example_type_simple": "#3498db",    # Blue for simple
        "bg_example_type_complex": "#9b59b6",   # Purple for complex
        "bg_example_type_custom": "#e67e22",    # Orange for custom

        # Footer
        "bg_footer": "#5a5a5a",
        "fg_footer": "#ffffff",

        # Structural polish (border-radius + QGraphicsDropShadowEffect tokens — see
        # "modern" theme below for where these actually have visible effect). Kept at
        # today's existing values here so light theme is visually unchanged; Qt stylesheets
        # have no CSS box-shadow equivalent, so shadow_card_* are plain Python values
        # consumed by _apply_card_effect(), not raw CSS — shadow_card_color is a plain
        # #rrggbb (QColor's string constructor does NOT parse CSS rgba(...) syntax,
        # confirmed empirically: QColor("rgba(0,0,0,0)").isValid() is False), with opacity
        # applied separately via shadow_card_alpha (0.0-1.0, QColor.setAlphaF()).
        "radius_card": "4px",
        "shadow_card_color": "#000000",
        "shadow_card_alpha": 0.0,
        "shadow_card_blur": 0,
        "shadow_card_offset": (0, 0),
    },

    "dark": {
        # Backgrounds
        "bg_primary": "#181B1D",
        "bg_secondary": "#2C373E",
        "bg_panel": "#283136",
        "bg_input": "#2C373E",
        "bg_button": "#283136",
        "bg_button_hover": "#394459",
        "bg_group": "#2C373E",

        # Neutral grey hover for the folder-browser tree/icon-grid views — see the light
        # theme's own comment on this key for why it exists separately from
        # bg_button_hover. Dark theme's blue accents aren't as close a match to the folder
        # icon's #3498db as light theme's identical bg_button_hover was, but kept as a
        # dedicated neutral grey anyway for consistency between themes.
        "bg_list_hover": "#39424a",

        # Category/accent colors
        "bg_category": "#283136",
        "bg_category_hover": "#394459",
        # Mirror image of light theme's pair (see that section's comment): here bg_category
        # (L=47.4) is already the *dimmer* of the two, so it's reused as tab_launcher_resting,
        # and tab_launcher_active is a new color scaled *up* from it (L=109.3, a +61.9 rise,
        # sized to match dark theme's own bg_green_1->bg_green_3 gap of +61.6).
        "tab_launcher_resting": "#283136",
        "tab_launcher_active": "#5c717c",
        "bg_success": "#1a5a3a",
        "bg_success_hover": "#228b4a",
        "bg_danger": "#8b2a2a",
        "bg_danger_hover": "#a83232",
        "bg_warning": "#8b6914",
        "bg_purple": "#3DAEE9",
        "bg_purple_light": "#132733",

        # Navy/action buttons
        "bg_navy": "#283136",
        "bg_navy_hover": "#394459",
        "bg_navy_checked": "#b86a1a",

        # Green gradient for bottom buttons (darker variants) — was previously a flat
        # #202B31 for all four stops (a placeholder that was never filled in), which made
        # the viewer tab row's active-vs-inactive background identical in dark mode and left
        # a border as the *only* selection cue — colliding with the Terminal tab's own
        # always-on border (see CLAUDE.md's Viewer tab buttons bullet) and making it look
        # permanently selected. A real 4-stop progression was then built from the same green
        # family as bg_success/bg_success_hover, darkest to brightest — but that first pass
        # (bg_green_1..4 = #123d28/#1a5a3a/#228b4a/#2fae5c) read as noticeably more saturated/
        # vivid than the launcher tab row's own subdued tab_launcher_resting/active blue-greys
        # (~15% HSL saturation) sitting right next to it, a visible mismatch once both rows
        # were on screen together. Re-derived at the same ~16% saturation and ~150° (green)
        # hue as the blue pair, at roughly the original stops' lightness so the
        # resting->hover->active brightness progression (the actual selection cue, see above)
        # is unchanged — only the saturation/vividness was pulled down to match. No longer
        # numerically identical to bg_success/bg_success_hover as a result (those keep their
        # own, more vivid values — they're a general-purpose "success" accent used elsewhere,
        # e.g. checked-button states, not exclusive to these two tab rows).
        "bg_green_1": "#212e28",
        "bg_green_2": "#31433a",
        "bg_green_3": "#496456",
        "bg_green_4": "#5a7c6b",

        # Recent/All configs
        "bg_config_current": "#394459",
        "bg_config": "#283136",
        "bg_config_hover": "#2a5a9a",
        "bg_config_arrow": "#3C454A",
        # All Projects (more subtle than Recent)
        "bg_config_all": "#212527",
        "bg_config_all_current": "#2a3035",
        "bg_config_all_arrow": "#252a2d",

        # Text colors
        "fg_primary": "#c0c0c0",
        "fg_secondary": "#a0a0a0",
        "fg_muted": "#707070",
        "fg_on_dark": "#ffffff",
        "fg_on_button": "#c0c0c0",
        "fg_link": "#6ab0e0",

        # Borders
        "border": "#344155",
        "border_dark": "#192331",
        "border_light": "#1A212C",

        # Status colors
        "status_success": "#2a8a5a",
        "status_error": "#c04040",
        "status_info": "#2a8aaa",
        "status_warning": "#c09020",

        # Code/console
        "bg_code": "#2C373E",
        "fg_code": "#c0c0c0",
        "bg_console": "#181B1D",

        # Viewer areas
        "bg_viewer": "#2C373E",

        # Markdown highlight
        "bg_highlight": "#6a1a2a",

        # Help viewer markdown content
        "bg_help": "#2C373E",
        "bg_code_inline": "#1a1a3a",
        "fg_help_h1": "#6ab0e0",
        "fg_help_h2": "#8ac0f0",
        "fg_help_h3": "#a0a0a0",
        "border_help_h1": "#182381",
        "border_help_h2": "#192331",

        # Examples viewer
        "bg_example_card": "#283136",
        "border_example_card": "#394459",
        "bg_example_type_builtin": "#1a5a3a",   # Green for built-in (darker)
        "bg_example_type_simple": "#1a4a7a",    # Blue for simple (darker)
        "bg_example_type_complex": "#5a2a7a",   # Purple for complex (darker)
        "bg_example_type_custom": "#8a5a1a",    # Orange for custom (darker)

        # Footer
        "bg_footer": "#363636",
        "fg_footer": "#ffffff",

        # Structural polish — see light theme's identical comment above. Unchanged values,
        # dark theme is visually unaffected.
        "radius_card": "4px",
        "shadow_card_color": "#000000",
        "shadow_card_alpha": 0.0,
        "shadow_card_blur": 0,
        "shadow_card_offset": (0, 0),
    },

    # A third, visually distinct light theme — airy off-white backgrounds, a clean blue
    # accent, and pale-background status badges, loosely inspired by modern SaaS-dashboard
    # UIs (color/shape sense only, not a copy of any specific product). Settings-only for
    # now (see _create_themes_tab()'s combo and toggle_theme()'s docstring) — the footer
    # 🌙/☀️ button deliberately still only ever toggles light<->dark. Paired with a bundled
    # Lato font (see apply_global_styles() for native widgets, _notes_paper_css()/
    # _todo_paper_css() for the Muya webview, and help/shell.html for the Help viewer) and
    # the radius_card/shadow_card_* "structural polish" tokens below, both deliberately
    # curated to a handful of representative surfaces rather than applied everywhere (see
    # CLAUDE.md's Theme System section for the full writeup).
    "modern": {
        # Backgrounds
        "bg_primary": "#ffffff",
        "bg_secondary": "#f4f5f7",
        "bg_panel": "#374151",
        "bg_input": "#f8f9fb",
        "bg_button": "#eef1f5",
        "bg_button_hover": "#2060de",
        "bg_group": "#ffffff",
        "bg_list_hover": "#eef2ff",

        # Category/accent colors
        "bg_category": "#2060de",
        "bg_category_hover": "#2558c4",
        "tab_launcher_resting": "#0a5ca9",
        "tab_launcher_active": "#2060de",
        "bg_success": "#16a34a",
        "bg_success_hover": "#15803d",
        "bg_danger": "#ef4444",
        "bg_danger_hover": "#dc2626",
        "bg_warning": "#f59e0b",
        "bg_purple": "#8b5cf6",
        "bg_purple_light": "#f3f0ff",

        # Navy/action buttons
        "bg_navy": "#1e3a8a",
        "bg_navy_hover": "#1e40af",
        "bg_navy_checked": "#f59e0b",

        # Green gradient for bottom buttons (darkest to brightest, same success-green
        # family convention the dark theme's own comment describes)
        "bg_green_1": "#0d3d26",
        "bg_green_2": "#14532d",
        "bg_green_3": "#16a34a",
        "bg_green_4": "#4ade80",

        # Recent/All configs — a light blue-tinted family (matching the dashboard
        # reference's own soft-blue "selected nav item" pill) rather than neutral grey
        "bg_config_current": "#dbe4ff",
        "bg_config": "#eef1f5",
        "bg_config_hover": "#e0e7ff",
        "bg_config_arrow": "#e5e9f0",
        "bg_config_all": "#f4f5f7",
        "bg_config_all_current": "#eef1f5",
        "bg_config_all_arrow": "#eceff3",

        # Text colors
        "fg_primary": "#1a1a1a",
        "fg_secondary": "#6b7280",
        "fg_muted": "#9ca3af",
        "fg_on_dark": "#ffffff",
        "fg_on_button": "#1a1a1a",
        "fg_link": "#2060de",

        # Borders
        "border": "#e5e7eb",
        "border_dark": "#d1d5db",
        "border_light": "#f3f4f6",

        # Status colors
        "status_success": "#16a34a",
        "status_error": "#ef4444",
        "status_info": "#2563eb",
        "status_warning": "#f59e0b",

        # Code/console — stays dark even in this light theme, matching light theme's own
        # convention that code/terminal surfaces are dark regardless of the app theme
        "bg_code": "#1e293b",
        "fg_code": "#e2e8f0",
        "bg_console": "#0f172a",

        # Viewer areas
        "bg_viewer": "#374151",

        # Markdown highlight
        "bg_highlight": "#b91c1c",

        # Help viewer markdown content
        "bg_help": "#f4f5f7",
        "bg_code_inline": "#eef1f5",
        "fg_help_h1": "#1a1a1a",
        "fg_help_h2": "#2f3b4c",
        "fg_help_h3": "#6b7280",
        "border_help_h1": "#2060de",
        "border_help_h2": "#e5e7eb",

        # Examples viewer
        "bg_example_card": "#ffffff",
        "border_example_card": "#e5e7eb",
        "bg_example_type_builtin": "#16a34a",
        "bg_example_type_simple": "#2060de",
        "bg_example_type_complex": "#8b5cf6",
        "bg_example_type_custom": "#f59e0b",

        # Footer
        "bg_footer": "#1f2937",
        "fg_footer": "#ffffff",

        # Structural polish — see light theme's comment above for what these mean. This is
        # the one theme where they actually have visible effect.
        "radius_card": "14px",
        "shadow_card_color": "#0f172a",
        "shadow_card_alpha": 0.14,
        "shadow_card_blur": 24,
        "shadow_card_offset": (0, 6),
    },
}


# =============================================================================
# "modern" theme accent-color customization (Settings -> Themes tab)
# =============================================================================
# A handful of the "modern" theme's color keys are driven by just 2 accent colors
# (a blue and a green, each with an "offset"/darker variant) reused across several
# keys at once — see _create_themes_tab()'s "Modern Theme Colors" section in
# projectflow.py for the picker UI, and derive_modern_overrides() below for exactly
# which keys each of the 4 accent colors drives. These defaults match THEMES["modern"]'s
# own hardcoded values exactly, so a user who never customizes anything sees the
# identical palette either way.
MODERN_ACCENT_DEFAULTS = {
    "accent_blue": "#2060de",
    "accent_blue_offset": "#0a5ca9",
    "accent_green": "#16a34a",
    "accent_green_offset": "#15803d",
}


def _hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return '#{:02x}{:02x}{:02x}'.format(*(max(0, min(255, round(c))) for c in rgb))


def _lerp_rgb(hex1, hex2, t):
    """Linear interpolation between two hex colors at t (0.0 = hex1, 1.0 = hex2)."""
    r1, g1, b1 = _hex_to_rgb(hex1)
    r2, g2, b2 = _hex_to_rgb(hex2)
    return _rgb_to_hex((r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t))


def _lighten_rgb(hex_str, amount):
    """Scale each RGB channel toward 255 by `amount` (0.0-1.0) — same "scale by a ratio,
    preserve hue" technique already used to derive the dark theme's own bg_green_1..4
    gradient (see CLAUDE.md's Theme System section)."""
    r, g, b = _hex_to_rgb(hex_str)
    return _rgb_to_hex((r + (255 - r) * amount, g + (255 - g) * amount, b + (255 - b) * amount))


def derive_modern_overrides(accent_colors):
    """Expand the 4 user-settable accent colors (any subset — missing keys fall back to
    MODERN_ACCENT_DEFAULTS) into the full set of THEMES["modern"] keys they drive. See the
    module-level comment above and projectflow.py's "Modern Theme Colors" Settings section
    for the full writeup of which keys map to which accent."""
    accent_colors = accent_colors or {}
    blue = accent_colors.get("accent_blue", MODERN_ACCENT_DEFAULTS["accent_blue"])
    blue_offset = accent_colors.get("accent_blue_offset", MODERN_ACCENT_DEFAULTS["accent_blue_offset"])
    green = accent_colors.get("accent_green", MODERN_ACCENT_DEFAULTS["accent_green"])
    green_offset = accent_colors.get("accent_green_offset", MODERN_ACCENT_DEFAULTS["accent_green_offset"])

    return {
        # Blue family — literal reuse, matching THEMES["modern"]'s own existing convention
        # of one accent blue repeated across several keys.
        "bg_button_hover": blue,
        "bg_category": blue,
        "tab_launcher_active": blue,
        "fg_link": blue,
        "border_help_h1": blue,
        "bg_example_type_simple": blue,
        "tab_launcher_resting": blue_offset,
        # Folded into Blue Offset too (previously an independent third shade, #2558c4) —
        # a deliberate simplification so this stays "2 blue knobs," not 3.
        "bg_category_hover": blue_offset,

        # Green family — literal reuse (all 4 already share one literal value today).
        "bg_success": green,
        "bg_green_3": green,
        "status_success": green,
        "bg_example_type_builtin": green,
        "bg_success_hover": green_offset,

        # Green gradient (bg_green_1/2/4) — auto-derived, not directly settable (see
        # Context in the plan this was built from for why: a real 4-stop ramp doesn't map
        # cleanly onto 2 knobs, and the resting->hover->active brightness progression has a
        # documented history of bugs when it's not monotonic).
        "bg_green_1": green_offset,
        "bg_green_2": _lerp_rgb(green_offset, green, 0.5),
        "bg_green_4": _lighten_rgb(green, 0.4),
    }


def get_theme(theme_name="light", accent_colors=None):
    """Get a theme dictionary by name. For "modern", an optional accent_colors dict (see
    derive_modern_overrides()) overrides the 16 accent-driven keys on top of a COPY of the
    base theme — light/dark, and a "modern" call with no accent_colors, are unaffected and
    return exactly what they always have."""
    theme = THEMES.get(theme_name, THEMES["light"])
    if theme_name == "modern" and accent_colors:
        theme = dict(theme)
        theme.update(derive_modern_overrides(accent_colors))
    return theme


def detect_system_theme():
    """Detect system dark/light mode preference (KDE/Qt)"""
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QPalette

        app = QApplication.instance()
        if app:
            palette = app.palette()
            # If window background is darker than text, it's dark mode
            bg = palette.color(QPalette.ColorRole.Window)
            fg = palette.color(QPalette.ColorRole.WindowText)
            # Compare luminance
            bg_lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
            fg_lum = 0.299 * fg.red() + 0.587 * fg.green() + 0.114 * fg.blue()
            return "dark" if bg_lum < fg_lum else "light"
    except Exception:
        pass
    return "light"
