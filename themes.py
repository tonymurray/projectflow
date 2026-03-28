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
        "header_btn_height": 28,
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

        # Category/accent colors
        "bg_category": "#3498db",
        "bg_category_hover": "#2980b9",
        "bg_success": "#27ae60",
        "bg_success_hover": "#2ecc71",
        "bg_danger": "#e74c3c",
        "bg_danger_hover": "#c0392b",
        "bg_warning": "#f39c12",
        "bg_purple": "#8e44ad",
        "bg_purple_light": "#f5eef8",

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
        "border_light": "#cccccc",

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

        # Category/accent colors
        "bg_category": "#283136",
        "bg_category_hover": "#394459",
        "bg_success": "#1a5a3a",
        "bg_success_hover": "#228b4a",
        "bg_danger": "#8b2a2a",
        "bg_danger_hover": "#a83232",
        "bg_warning": "#8b6914",
        "bg_purple": "#4a2a6a",
        "bg_purple_light": "#1a1028",

        # Navy/action buttons
        "bg_navy": "#283136",
        "bg_navy_hover": "#394459",
        "bg_navy_checked": "#b86a1a",

        # Green gradient for bottom buttons (darker variants)
        "bg_green_1": "#202B31",
        "bg_green_2": "#202B31",
        "bg_green_3": "#202B31",
        "bg_green_4": "#202B31",
        "bg_green_4": "#202B31",

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
    }
}


def get_theme(theme_name="light"):
    """Get a theme dictionary by name"""
    return THEMES.get(theme_name, THEMES["light"])


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
