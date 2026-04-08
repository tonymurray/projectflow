#!/usr/bin/env python3
"""
ProjectFlow - Quick Launcher for Projects and Files
KDE Plasma application with configuration file support
Edit config files and click Refresh to reload!
"""

import sys
import subprocess
import os
import shutil
import shlex
import json
import argparse
import inspect
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QFileDialog, QGroupBox, QMessageBox, QScrollArea, QFrame, QTextEdit, QToolBar,
    QLineEdit, QComboBox, QTextBrowser, QDialog, QDialogButtonBox, QTabWidget, QFormLayout, QCheckBox,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QAbstractItemView, QHeaderView, QSizePolicy,
    QPlainTextEdit, QStackedWidget, QCompleter
)
from PyQt6.QtCore import Qt, QMimeData, QTimer, QPoint, QSize, pyqtSignal, QStringListModel, QEvent
from PyQt6.QtGui import QIcon, QFont, QKeySequence, QShortcut, QTextListFormat, QImage, QPixmap, QDrag, QColor, QPainter
import re
import urllib.request
import urllib.error
import fitz  # PyMuPDF for PDF rendering
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtCore import QUrl
from themes import get_theme, detect_system_theme, THEMES, get_dimensions


# Built-in smart default handlers using xdg-open
# These cannot be overridden by user handlers
BUILTIN_HANDLERS = {
    "browser": lambda path: ["xdg-open", path],
    "file_manager": lambda path: ["xdg-open", path],
    "editor": lambda path: ["xdg-open", path],
    "default": lambda path: ["xdg-open", path],
    # Note: "konsole" and "terminal" are handled dynamically in open_in_app()
    # to use the configured terminal emulator
}


class CleanTextEdit(QTextEdit):
    """QTextEdit subclass that sanitizes pasted HTML to keep only allowed tags"""

    ALLOWED_TAGS = {'b', 'i', 'p', 'br', 'ul', 'ol', 'li', 'strong', 'em',
                    'h1', 'h2', 'h3', 'h4', 'h5', 'a', 'code'}

    def insertFromMimeData(self, source):
        """Override paste to sanitize HTML content"""
        if source.hasHtml():
            clean_html = self.sanitize_html(source.html())
            self.insertHtml(clean_html)
        elif source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)

    def sanitize_html(self, html):
        """Remove all HTML tags except allowed ones, strip all attributes except href on <a>"""
        # First, extract body content if present
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        if body_match:
            html = body_match.group(1)

        # Pattern to match HTML tags
        tag_pattern = re.compile(r'<(/?)(\w+)([^>]*)>', re.IGNORECASE)

        def replace_tag(match):
            slash = match.group(1)  # '/' for closing tags, '' for opening
            tag_name = match.group(2).lower()
            attributes = match.group(3)

            if tag_name not in self.ALLOWED_TAGS:
                return ''  # Remove disallowed tags

            # For <a> tags, preserve href attribute only
            if tag_name == 'a' and not slash:
                href_match = re.search(r'href\s*=\s*["\']([^"\']*)["\']', attributes, re.IGNORECASE)
                if href_match:
                    return f'<a href="{href_match.group(1)}">'
                return '<a>'

            # For all other allowed tags, strip attributes
            return f'<{slash}{tag_name}>'

        cleaned = tag_pattern.sub(replace_tag, html)

        # Clean up extra whitespace but preserve intentional line breaks
        cleaned = re.sub(r'\n\s*\n', '\n', cleaned)

        return cleaned.strip()


class DraggableConfigButton(QPushButton):
    """A QPushButton that supports drag-and-drop for reordering"""

    def __init__(self, text, config_path, parent=None):
        super().__init__(text, parent)
        self.config_path = config_path
        self.drag_start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self.drag_start_pos:
            return

        # Check if we've moved enough to start a drag
        if (event.pos() - self.drag_start_pos).manhattanLength() < 10:
            return

        # Start drag operation
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(self.config_path)
        drag.setMimeData(mime_data)

        # Execute drag
        drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, event):
        self.drag_start_pos = None
        super().mouseReleaseEvent(event)


class ConfigBarWidget(QWidget):
    """Widget that contains config buttons and handles drop events for reordering"""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setAcceptDrops(True)
        self.buttons = []  # List of (button_container, config_path, is_pinned)

    def add_button(self, btn_container, config_path, is_pinned):
        self.buttons.append((btn_container, config_path, is_pinned))

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasText():
            return

        dragged_path = event.mimeData().text()
        drop_pos = event.position().toPoint()

        # Find drop index based on position
        drop_index = self._get_drop_index(drop_pos)

        # Update pinned projects
        self.app.handle_config_drop(dragged_path, drop_index)
        event.acceptProposedAction()

    def _get_drop_index(self, pos):
        """Determine which index the drop should insert at"""
        for i, (btn_container, config_path, is_pinned) in enumerate(self.buttons):
            btn_rect = btn_container.geometry()
            # If drop is to the left of the button's center, insert before it
            if pos.x() < btn_rect.center().x():
                return i
        return len(self.buttons)


class DraggableItemButton(QPushButton):
    """A QPushButton for category items that supports drag-and-drop reordering"""

    def __init__(self, text, col_idx, category_name, item_idx, parent=None):
        super().__init__(text, parent)
        self.col_idx = col_idx
        self.category_name = category_name
        self.item_idx = item_idx
        self.drag_start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self.drag_start_pos:
            return

        # Check if we've moved enough to start a drag
        if (event.pos() - self.drag_start_pos).manhattanLength() < 10:
            return

        # Start drag operation
        drag = QDrag(self)
        mime_data = QMimeData()
        # Encode item info as: col_idx|category_name|item_idx
        mime_data.setText(f"item|{self.col_idx}|{self.category_name}|{self.item_idx}")
        drag.setMimeData(mime_data)

        # Execute drag
        drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, event):
        self.drag_start_pos = None
        super().mouseReleaseEvent(event)


class CategoryDropZone(QWidget):
    """Widget that wraps category items and handles drop events for reordering"""

    def __init__(self, app, col_idx, category_name, parent=None):
        super().__init__(parent)
        self.app = app
        self.col_idx = col_idx
        self.category_name = category_name
        self.setAcceptDrops(True)
        self.item_widgets = []  # List of (widget, item_idx)

    def add_item(self, widget, item_idx):
        self.item_widgets.append((widget, item_idx))

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            data = event.mimeData().text()
            # Only accept drops from same category
            if data.startswith("item|"):
                parts = data.split("|")
                if len(parts) == 4:
                    drag_col = int(parts[1])
                    drag_cat = parts[2]
                    if drag_col == self.col_idx and drag_cat == self.category_name:
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            data = event.mimeData().text()
            if data.startswith("item|"):
                parts = data.split("|")
                if len(parts) == 4:
                    drag_col = int(parts[1])
                    drag_cat = parts[2]
                    if drag_col == self.col_idx and drag_cat == self.category_name:
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasText():
            return

        data = event.mimeData().text()
        if not data.startswith("item|"):
            return

        parts = data.split("|")
        if len(parts) != 4:
            return

        drag_col = int(parts[1])
        drag_cat = parts[2]
        drag_idx = int(parts[3])

        # Only handle drops within same category
        if drag_col != self.col_idx or drag_cat != self.category_name:
            return

        drop_pos = event.position().toPoint()
        drop_idx = self._get_drop_index(drop_pos)

        # Handle reorder
        if drop_idx != drag_idx:
            self.app.handle_item_reorder(self.col_idx, self.category_name, drag_idx, drop_idx)

        event.acceptProposedAction()

    def _get_drop_index(self, pos):
        """Determine which index the drop should insert at based on Y position"""
        for i, (widget, item_idx) in enumerate(self.item_widgets):
            widget_rect = widget.geometry()
            # If drop is above the widget's center, insert before it
            if pos.y() < widget_rect.center().y():
                return i
        return len(self.item_widgets)


class ClickableSearchTitle(QWidget):
    """A title widget that transforms into a search input on click"""

    configSelected = pyqtSignal(str)  # Emits config path when selected

    def __init__(self, current_name, config_paths, theme_func, parent=None):
        """
        Args:
            current_name: Display name (uppercased)
            config_paths: List of available config file paths
            theme_func: Reference to app.t() for theming
        """
        super().__init__(parent)
        self.current_name = current_name
        self.config_paths = config_paths
        self.t = theme_func

        # Build config name to path mapping
        self.config_map = {}
        for path in config_paths:
            name = os.path.basename(path)
            name = os.path.splitext(name)[0]
            if name.endswith('_config'):
                name = name[:-7]
            display_name = name.replace('_', ' ').upper()
            self.config_map[display_name] = path

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stacked widget to switch between label and search
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        # Page 0: Clickable label (display mode)
        self.title_label = QLabel(current_name)
        self.title_label.setStyleSheet(f"font-size: 20pt; font-weight: bold; color: {self.t('fg_secondary')}; padding: 0; margin: 0;")
        self.title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.title_label.mousePressEvent = lambda e: self.enter_search_mode()
        self.stack.addWidget(self.title_label)

        # Page 1: Search input (search mode) - seamless transparent style
        self.search_input = QLineEdit()
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                font-size: 20pt;
                font-weight: bold;
                color: {self.t('fg_secondary')};
                background-color: transparent;
                border: none;
                padding: 0;
                margin: 0;
            }}
        """)
        self.search_input.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.search_input.setPlaceholderText("Search...")

        # Setup completer
        self.completer = QCompleter(list(self.config_map.keys()))
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.popup().setStyleSheet(f"""
            QListView {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                font-size: 14pt;
            }}
            QListView::item:selected {{
                background-color: {self.t('bg_category')};
            }}
        """)
        self.search_input.setCompleter(self.completer)

        # Connect signals
        self.search_input.returnPressed.connect(self.on_return_pressed)
        self.completer.activated.connect(self.on_completer_activated)

        # Use event filter to detect focus out (more reliable than editingFinished)
        self.search_input.installEventFilter(self)

        self.stack.addWidget(self.search_input)
        layout.addWidget(self.stack)

        # Start in display mode
        self.stack.setCurrentIndex(0)

    def eventFilter(self, obj, event):
        """Handle focus out to revert to display mode"""
        if obj == self.search_input and event.type() == QEvent.Type.FocusOut:
            # Small delay to allow completer click to register
            QTimer.singleShot(100, self._check_and_exit_search)
        return super().eventFilter(obj, event)

    def _check_and_exit_search(self):
        """Check if we should exit search mode after focus out"""
        # Don't exit if focus returned to search input or completer is active
        if self.search_input.hasFocus():
            return
        popup = self.completer.popup()
        if popup.isVisible() and popup.hasFocus():
            return
        # Exit search mode - revert to showing current config
        self.exit_search_mode()

    def enter_search_mode(self):
        """Switch to search input mode"""
        self.stack.setCurrentIndex(1)
        self.search_input.clear()
        self.search_input.setFocus()

    def exit_search_mode(self):
        """Switch back to label display (reverts to current config name)"""
        self.stack.setCurrentIndex(0)

    def on_return_pressed(self):
        """Handle Enter key - switch to first/selected match"""
        text = self.search_input.text().strip().upper()
        if not text:
            self.exit_search_mode()
            return

        # Check for exact match first
        if text in self.config_map:
            self.configSelected.emit(self.config_map[text])
            self.exit_search_mode()
            return

        # Check completer popup - use selected item or first match
        popup = self.completer.popup()
        if popup.isVisible():
            # If user selected something, use that
            if popup.currentIndex().isValid():
                selected = popup.currentIndex().data()
                if selected in self.config_map:
                    self.configSelected.emit(self.config_map[selected])
                    self.exit_search_mode()
                    return
            # Otherwise, use the first item in the filtered list
            model = self.completer.completionModel()
            if model.rowCount() > 0:
                first_match = model.index(0, 0).data()
                if first_match in self.config_map:
                    self.configSelected.emit(self.config_map[first_match])
                    self.exit_search_mode()
                    return

        # No match found - just exit
        self.exit_search_mode()

    def on_completer_activated(self, text):
        """Handle selection from completer dropdown"""
        if text in self.config_map:
            self.configSelected.emit(self.config_map[text])
            self.exit_search_mode()

    def update_title(self, new_name):
        """Update the displayed title"""
        self.current_name = new_name
        self.title_label.setText(new_name)

    def update_theme(self, theme_func):
        """Update colors when theme changes"""
        self.t = theme_func
        self.title_label.setStyleSheet(f"font-size: 20pt; font-weight: bold; color: {self.t('fg_secondary')}; padding: 0; margin: 0;")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                font-size: 20pt;
                font-weight: bold;
                color: {self.t('fg_secondary')};
                background-color: transparent;
                border: none;
                padding: 0;
                margin: 0;
            }}
        """)
        self.completer.popup().setStyleSheet(f"""
            QListView {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                font-size: 14pt;
            }}
            QListView::item:selected {{
                background-color: {self.t('bg_category')};
            }}
        """)


class ProjectFlowApp(QMainWindow):
    def __init__(self, config_file_arg=None):
        super().__init__()
        self.config = {}
        self.config_file_arg = config_file_arg  # Store CLI argument
        self.edit_mode = False  # Track whether we're in edit mode

        # Get the directory where this script is located
        self.script_dir = os.path.dirname(os.path.abspath(__file__))

        # Settings file to store user preferences (machine-specific, not synced)
        self.settings_file = os.path.join(self.script_dir, ".projectflow_settings.json")

        # Load settings (like which config to use)
        self.load_settings()

        # Initialize theme and dimensions (after settings loaded)
        self.init_theme()
        self.init_dimensions()
        self.apply_global_styles()

        # Setup first run (copy examples if needed)
        self.setup_first_run()

        # Install .desktop file for GNOME/COSMIC dock icon support
        self.ensure_desktop_file_installed()

        # Determine which config file to use
        self.current_config_file = self.get_config_file_to_use()

        # Add to recent projects
        self.add_to_recent_projects(self.current_config_file)

        self.load_config()
        self.load_notes()
        self.load_launch_handlers()
        self.init_ui()

    def load_settings(self):
        """Load user settings from JSON file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    self.settings = json.load(f)
                # Migrate old settings keys
                self._migrate_settings()
            else:
                # Default settings
                self.settings = {
                    "default_project": None,  # None means use projectflow.json
                    "projects_directory": "projects",  # Subdirectory for project files
                    "last_used_project": None,
                    "recent_projects": [],  # List of recently used projects (max 10)
                    "enable_baloo_tags": False,  # Query Baloo for tagged files (KDE only)
                }
                self.save_settings()
        except Exception as e:
            print(f"Error loading settings: {e}")
            self.settings = {
                "default_project": None,
                "projects_directory": "projects",
                "last_used_project": None,
                "recent_projects": [],
                "enable_baloo_tags": False,
            }

    def _migrate_settings(self):
        """Migrate old settings keys to new names"""
        migrated = False
        # Migrate configs_directory -> projects_directory
        if "configs_directory" in self.settings and "projects_directory" not in self.settings:
            old_value = self.settings.pop("configs_directory")
            # Also rename default "configs" value to "projects"
            self.settings["projects_directory"] = "projects" if old_value == "configs" else old_value
            migrated = True
        elif "configs_directory" in self.settings:
            del self.settings["configs_directory"]
            migrated = True
        # Also update projects_directory if it still says "configs"
        if self.settings.get("projects_directory") == "configs":
            self.settings["projects_directory"] = "projects"
            migrated = True
        # Migrate default_config -> default_project
        if "default_config" in self.settings and "default_project" not in self.settings:
            self.settings["default_project"] = self.settings.pop("default_config")
            migrated = True
        elif "default_config" in self.settings:
            del self.settings["default_config"]
            migrated = True
        # Migrate last_used_config -> last_used_project
        if "last_used_config" in self.settings and "last_used_project" not in self.settings:
            self.settings["last_used_project"] = self.settings.pop("last_used_config")
            migrated = True
        elif "last_used_config" in self.settings:
            del self.settings["last_used_config"]
            migrated = True
        # Migrate recent_configs -> recent_projects
        if "recent_configs" in self.settings and "recent_projects" not in self.settings:
            self.settings["recent_projects"] = self.settings.pop("recent_configs")
            migrated = True
        elif "recent_configs" in self.settings:
            del self.settings["recent_configs"]
            migrated = True
        # Migrate pinned_configs -> pinned_projects
        if "pinned_configs" in self.settings and "pinned_projects" not in self.settings:
            self.settings["pinned_projects"] = self.settings.pop("pinned_configs")
            migrated = True
        elif "pinned_configs" in self.settings:
            del self.settings["pinned_configs"]
            migrated = True
        if migrated:
            self.save_settings()

    def init_theme(self):
        """Initialize the theme based on settings or system preference"""
        theme_setting = self.settings.get("theme", "system")
        if theme_setting == "system":
            self.current_theme = detect_system_theme()
        else:
            self.current_theme = theme_setting
        self.theme = get_theme(self.current_theme)

    def t(self, key):
        """Get a theme color by key (shorthand helper)"""
        return self.theme.get(key, "#ff00ff")  # Magenta fallback for missing colors

    def init_dimensions(self):
        """Initialize DE-specific dimensions"""
        self.current_de = self.detect_desktop_environment()
        self.dimensions = get_dimensions(self.current_de)

    def d(self, key):
        """Get a dimension value by key (shorthand helper)"""
        return self.dimensions.get(key, 0)

    def apply_global_styles(self):
        """Apply application-wide stylesheet for tooltips and global elements"""
        app = QApplication.instance()
        if app:
            # Global stylesheet for tooltips with generous padding and high contrast
            # Use explicit white text in dark mode for maximum readability
            if self.current_theme == "dark":
                tooltip_bg = "#1a2030"  # Dark navy background
                tooltip_fg = "#ffffff"  # Pure white text
                tooltip_border = "#3a4a60"  # Subtle border
            else:
                tooltip_bg = "#ffffd0"  # Light yellow (traditional tooltip color)
                tooltip_fg = "#000000"  # Black text
                tooltip_border = "#808080"  # Gray border

            tooltip_style = f"""
                QToolTip {{
                    background-color: {tooltip_bg};
                    color: {tooltip_fg};
                    border: 1px solid {tooltip_border};
                    border-radius: 4px;
                    padding: 4px 6px;
                    font-size: 13px;
                }}
            """
            app.setStyleSheet(tooltip_style)

    def toggle_theme(self):
        """Toggle between light and dark themes"""
        if self.current_theme == "light":
            self.current_theme = "dark"
        else:
            self.current_theme = "light"
        self.settings["theme"] = self.current_theme
        self.save_settings()
        self.theme = get_theme(self.current_theme)
        self.apply_global_styles()
        self.refresh_projects()

    def _get_tab_style(self):
        """Return common tab widget stylesheet"""
        return f"""
            QTabWidget::pane {{
                border: 1px solid {self.t('border')};
                background-color: {self.t('bg_primary')};
            }}
            QTabBar::tab {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                padding: 8px 16px;
                border: 1px solid {self.t('border')};
                border-bottom: none;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: {self.t('bg_primary')};
                border-bottom: 1px solid {self.t('bg_primary')};
            }}
            QTabBar::tab:hover {{
                background-color: {self.t('bg_button_hover')};
            }}
        """

    def show_project_settings_dialog(self, initial_tab=0):
        """Show project-specific settings dialog.

        Args:
            initial_tab: Index of tab to show (0=Project Launchers, 1=Project Defaults)
        """
        # Get project name for title
        config_name = os.path.basename(self.current_config_file)
        project_name = os.path.splitext(config_name)[0]

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Project Settings - {project_name}")
        dialog.resize(780, 700)

        layout = QVBoxLayout(dialog)

        # Create tab widget
        tabs = QTabWidget()
        tabs.setStyleSheet(self._get_tab_style())

        # Project-specific tabs
        project_items_tab = self._create_project_items_tab()
        project_defaults_tab = self._create_project_defaults_tab()

        tabs.addTab(project_items_tab, "Project Launchers")
        tabs.addTab(project_defaults_tab, "Project Defaults")

        # Set initial tab if specified
        if initial_tab > 0 and initial_tab < tabs.count():
            tabs.setCurrentIndex(initial_tab)

        layout.addWidget(tabs)

        # Button box
        button_box = QDialogButtonBox()
        apply_btn = button_box.addButton("Apply", QDialogButtonBox.ButtonRole.ApplyRole)
        cancel_btn = button_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        ok_btn = button_box.addButton("OK", QDialogButtonBox.ButtonRole.AcceptRole)

        apply_btn.clicked.connect(lambda: self._apply_settings(dialog))
        cancel_btn.clicked.connect(dialog.reject)
        ok_btn.clicked.connect(lambda: self._save_project_settings_and_close(dialog))

        layout.addWidget(button_box)

        dialog.exec()

    def show_settings_dialog(self, initial_tab=0):
        """Show global application settings dialog.

        Args:
            initial_tab: Index of tab to show (0=Settings, 1=Icons, 2=Launch Handlers)
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("ProjectFlow Settings")
        dialog.resize(780, 700)

        layout = QVBoxLayout(dialog)

        # Create tab widget
        tabs = QTabWidget()
        tabs.setStyleSheet(self._get_tab_style())

        # Global settings tabs
        settings_tab = self._create_settings_tab()
        icons_tab = self._create_icons_tab()
        handlers_tab = self._create_handlers_tab()

        tabs.addTab(settings_tab, "Settings")
        tabs.addTab(icons_tab, "Icons")
        tabs.addTab(handlers_tab, "Launch Handlers")

        # Set initial tab if specified
        if initial_tab > 0 and initial_tab < tabs.count():
            tabs.setCurrentIndex(initial_tab)

        layout.addWidget(tabs)

        # Button box
        button_box = QDialogButtonBox()
        apply_btn = button_box.addButton("Apply", QDialogButtonBox.ButtonRole.ApplyRole)
        cancel_btn = button_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        ok_btn = button_box.addButton("OK", QDialogButtonBox.ButtonRole.AcceptRole)

        apply_btn.clicked.connect(lambda: self._apply_settings(dialog))
        cancel_btn.clicked.connect(dialog.reject)
        ok_btn.clicked.connect(lambda: self._save_settings_and_close(dialog))

        layout.addWidget(button_box)

        dialog.exec()

    def _create_settings_tab(self):
        """Create the settings tab content"""
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Style for inputs
        input_style = f"""
            QLineEdit, QComboBox {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 6px;
                min-height: 20px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {self.t('bg_category')};
            }}
        """

        label_style = f"color: {self.t('fg_primary')}; font-size: 13px;"

        # Theme
        theme_label = QLabel("Theme:")
        theme_label.setStyleSheet(label_style)
        self._settings_theme_combo = QComboBox()
        self._settings_theme_combo.addItems(["system", "light", "dark"])
        current_theme = self.settings.get("theme", "system")
        self._settings_theme_combo.setCurrentText(current_theme)
        self._settings_theme_combo.setStyleSheet(input_style)
        layout.addRow(theme_label, self._settings_theme_combo)

        # PDF Viewer
        pdf_label = QLabel("PDF Viewer:")
        pdf_label.setStyleSheet(label_style)
        pdf_layout = QHBoxLayout()
        self._settings_pdfviewer = QLineEdit()
        self._settings_pdfviewer.setText(self.settings.get("pdfviewer", ""))
        self._settings_pdfviewer.setPlaceholderText("Path to external PDF viewer (optional)")
        self._settings_pdfviewer.setStyleSheet(input_style)
        pdf_browse = QPushButton("Browse...")
        pdf_browse.clicked.connect(lambda: self._browse_file(self._settings_pdfviewer))
        pdf_layout.addWidget(self._settings_pdfviewer)
        pdf_layout.addWidget(pdf_browse)
        layout.addRow(pdf_label, pdf_layout)

        # Note Editor
        note_label = QLabel("Note Editor:")
        note_label.setStyleSheet(label_style)
        self._settings_note_editor = QLineEdit()
        self._settings_note_editor.setText(self.settings.get("open_note_external", ""))
        self._settings_note_editor.setPlaceholderText("Command for external editor (e.g., zettlr, code)")
        self._settings_note_editor.setStyleSheet(input_style)
        layout.addRow(note_label, self._settings_note_editor)

        # Terminal
        terminal_label = QLabel("Terminal:")
        terminal_label.setStyleSheet(label_style)
        self._settings_terminal = QComboBox()
        self._settings_terminal.setEditable(True)  # Allow custom entry
        terminal_options = [
            "",  # Empty = auto-detect
            "konsole", "gnome-terminal", "alacritty", "kitty", "wezterm",
            "terminator", "tilix", "xfce4-terminal", "guake", "tilda",
            "foot", "ghostty", "warp-terminal", "hyper", "tabby",
            "urxvt", "xterm"
        ]
        self._settings_terminal.addItems(terminal_options)
        current_terminal = self.settings.get("terminal", "")
        # Set current value (works for both listed and custom values)
        idx = self._settings_terminal.findText(current_terminal)
        if idx >= 0:
            self._settings_terminal.setCurrentIndex(idx)
        else:
            self._settings_terminal.setCurrentText(current_terminal)
        self._settings_terminal.setStyleSheet(input_style)
        detected = self.detect_default_terminal()
        self._settings_terminal.setToolTip(f"Terminal used for handlers. Leave empty to auto-detect (currently: {detected})")
        layout.addRow(terminal_label, self._settings_terminal)

        # Editor
        editor_label = QLabel("Editor:")
        editor_label.setStyleSheet(label_style)
        self._settings_editor = QComboBox()
        self._settings_editor.setEditable(True)
        editor_options = [
            "",  # Empty = auto-detect
            "code", "codium", "kate", "gedit", "mousepad", "pluma", "xed",
            "featherpad", "leafpad", "geany", "sublime", "atom",
            "vim", "nvim", "emacs", "nano"
        ]
        self._settings_editor.addItems(editor_options)
        current_editor = self.settings.get("editor", "")
        idx = self._settings_editor.findText(current_editor)
        if idx >= 0:
            self._settings_editor.setCurrentIndex(idx)
        else:
            self._settings_editor.setCurrentText(current_editor)
        self._settings_editor.setStyleSheet(input_style)
        detected_editor = self.detect_default_editor()
        self._settings_editor.setToolTip(f"Editor for directorydev handler. Leave empty to auto-detect (currently: {detected_editor})")
        layout.addRow(editor_label, self._settings_editor)

        # File Manager
        fm_label = QLabel("File Manager:")
        fm_label.setStyleSheet(label_style)
        self._settings_file_manager = QComboBox()
        self._settings_file_manager.setEditable(True)
        fm_options = [
            "",  # Empty = auto-detect
            "dolphin", "nautilus", "thunar", "nemo", "caja",
            "pcmanfm", "pcmanfm-qt", "cosmic-files"
        ]
        self._settings_file_manager.addItems(fm_options)
        current_fm = self.settings.get("file_manager", "")
        idx = self._settings_file_manager.findText(current_fm)
        if idx >= 0:
            self._settings_file_manager.setCurrentIndex(idx)
        else:
            self._settings_file_manager.setCurrentText(current_fm)
        self._settings_file_manager.setStyleSheet(input_style)
        detected_fm = self.detect_default_file_manager()
        self._settings_file_manager.setToolTip(f"File manager for directorydev handler. Leave empty to auto-detect (currently: {detected_fm})")
        layout.addRow(fm_label, self._settings_file_manager)

        # Notes Folder
        notes_label = QLabel("Notes Folder:")
        notes_label.setStyleSheet(label_style)
        notes_layout = QHBoxLayout()
        self._settings_notes_folder = QLineEdit()
        self._settings_notes_folder.setText(self.settings.get("notes_folder", ""))
        self._settings_notes_folder.setPlaceholderText("Path to notes folder (default: notes/)")
        self._settings_notes_folder.setStyleSheet(input_style)
        notes_browse = QPushButton("Browse...")
        notes_browse.clicked.connect(lambda: self._browse_folder(self._settings_notes_folder))
        notes_layout.addWidget(self._settings_notes_folder)
        notes_layout.addWidget(notes_browse)
        layout.addRow(notes_label, notes_layout)

        # Baloo Tags
        baloo_label = QLabel("Baloo Tags:")
        baloo_label.setStyleSheet(label_style)
        self._settings_baloo = QCheckBox("Enable Baloo tag querying for tagged files")
        self._settings_baloo.setChecked(self.settings.get("enable_baloo_tags", False))
        self._settings_baloo.setStyleSheet(f"color: {self.t('fg_primary')};")
        layout.addRow(baloo_label, self._settings_baloo)

        # Joplin Token
        joplin_label = QLabel("Joplin Token:")
        joplin_label.setStyleSheet(label_style)
        self._settings_joplin = QLineEdit()
        self._settings_joplin.setText(self.settings.get("joplin_token", ""))
        self._settings_joplin.setPlaceholderText("Joplin Web Clipper API token")
        self._settings_joplin.setEchoMode(QLineEdit.EchoMode.Password)
        self._settings_joplin.setStyleSheet(input_style)
        layout.addRow(joplin_label, self._settings_joplin)

        # Spacer
        layout.addRow(QLabel(""))

        # Actions section
        actions_label = QLabel("Actions:")
        actions_label.setStyleSheet(label_style)

        actions_layout = QHBoxLayout()
        action_btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 8px 12px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """

        # Upgrade button
        upgrade_btn = QPushButton("✨ Check for Updates")
        upgrade_btn.setStyleSheet(action_btn_style)
        upgrade_btn.setToolTip("Check for updates and upgrade")
        upgrade_btn.clicked.connect(self.check_for_upgrade)
        actions_layout.addWidget(upgrade_btn)

        # Install KDE service menu button (only show on KDE)
        if self.detect_desktop_environment() == 'kde':
            servicemenu_btn = QPushButton("📂 Install Dolphin Service Menu")
            servicemenu_btn.setStyleSheet(action_btn_style)
            servicemenu_btn.setToolTip("Install 'Add to ProjectFlow' right-click menu in Dolphin")
            servicemenu_btn.clicked.connect(self.install_kde_servicemenu)
            actions_layout.addWidget(servicemenu_btn)

        actions_layout.addStretch()
        layout.addRow(actions_label, actions_layout)

        return widget

    def _create_project_items_tab(self):
        """Create the project items tab for editing categories and items"""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Single tree editor for COLUMN_1 (no tabs needed)
        self._proj_trees = []
        tree = self._create_column_tree(0, self.COLUMN_1)
        self._proj_trees.append(tree)
        main_layout.addWidget(tree, 1)  # Stretch to fill space

        return widget

    def _create_project_defaults_tab(self):
        """Create the project defaults tab for viewer settings"""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # Style for inputs
        input_style = f"""
            QLineEdit, QComboBox {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 6px;
                min-height: 20px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {self.t('bg_category')};
            }}
        """
        label_style = f"color: {self.t('fg_primary')}; font-size: 13px;"

        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        # Default Viewer
        viewer_label = QLabel("Default Viewer:")
        viewer_label.setStyleSheet(label_style)
        self._proj_default_viewer = QComboBox()
        self._proj_default_viewer.addItems(["", "pdf", "webview", "image", "help", "examples", "console"])
        current_viewer = getattr(self, 'config_column2_default', None) or ""
        self._proj_default_viewer.setCurrentText(current_viewer)
        self._proj_default_viewer.setStyleSheet(input_style)
        form_layout.addRow(viewer_label, self._proj_default_viewer)

        # PDF File
        pdf_label = QLabel("PDF File:")
        pdf_label.setStyleSheet(label_style)
        pdf_layout = QHBoxLayout()
        self._proj_pdf_file = QLineEdit()
        self._proj_pdf_file.setText(getattr(self, 'config_pdf_file', None) or "")
        self._proj_pdf_file.setPlaceholderText("Path to default PDF file")
        self._proj_pdf_file.setStyleSheet(input_style)
        pdf_browse = QPushButton("Browse")
        pdf_browse.clicked.connect(lambda: self._browse_file(self._proj_pdf_file, "PDF Files (*.pdf);;All Files (*)"))
        pdf_layout.addWidget(self._proj_pdf_file)
        pdf_layout.addWidget(pdf_browse)
        form_layout.addRow(pdf_label, pdf_layout)

        # Web URL
        web_label = QLabel("Web URL:")
        web_label.setStyleSheet(label_style)
        self._proj_webview_url = QLineEdit()
        self._proj_webview_url.setText(getattr(self, 'config_webview_url', None) or "")
        self._proj_webview_url.setPlaceholderText("https://example.com")
        self._proj_webview_url.setStyleSheet(input_style)
        form_layout.addRow(web_label, self._proj_webview_url)

        # Image File
        image_label = QLabel("Image File:")
        image_label.setStyleSheet(label_style)
        image_layout = QHBoxLayout()
        self._proj_image_file = QLineEdit()
        self._proj_image_file.setText(getattr(self, 'config_image_file', None) or "")
        self._proj_image_file.setPlaceholderText("Path to default image file")
        self._proj_image_file.setStyleSheet(input_style)
        image_browse = QPushButton("Browse")
        image_browse.clicked.connect(lambda: self._browse_file(self._proj_image_file, "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.svg);;All Files (*)"))
        image_layout.addWidget(self._proj_image_file)
        image_layout.addWidget(image_browse)
        form_layout.addRow(image_label, image_layout)

        # Console Path
        console_label = QLabel("Console Path:")
        console_label.setStyleSheet(label_style)
        console_layout = QHBoxLayout()
        self._proj_console_path = QLineEdit()
        self._proj_console_path.setText(getattr(self, 'config_console_path', None) or "")
        self._proj_console_path.setPlaceholderText("Working directory for console")
        self._proj_console_path.setStyleSheet(input_style)
        console_browse = QPushButton("Browse")
        console_browse.clicked.connect(lambda: self._browse_folder(self._proj_console_path))
        console_layout.addWidget(self._proj_console_path)
        console_layout.addWidget(console_browse)
        form_layout.addRow(console_label, console_layout)

        # Terminal (per-config override)
        terminal_label = QLabel("Terminal:")
        terminal_label.setStyleSheet(label_style)
        self._proj_terminal = QComboBox()
        self._proj_terminal.setEditable(True)
        terminal_options = [
            "",  # Empty = use global setting
            "konsole", "gnome-terminal", "alacritty", "kitty", "wezterm",
            "terminator", "tilix", "xfce4-terminal", "guake", "tilda",
            "foot", "ghostty", "warp-terminal", "hyper", "tabby",
            "urxvt", "xterm"
        ]
        self._proj_terminal.addItems(terminal_options)
        current_terminal = getattr(self, 'config_terminal', None) or ""
        idx = self._proj_terminal.findText(current_terminal)
        if idx >= 0:
            self._proj_terminal.setCurrentIndex(idx)
        else:
            self._proj_terminal.setCurrentText(current_terminal)
        self._proj_terminal.setStyleSheet(input_style)
        global_terminal = self.get_configured_terminal()
        self._proj_terminal.setToolTip(f"Override global terminal for this project (empty = use global: {global_terminal})")
        form_layout.addRow(terminal_label, self._proj_terminal)

        main_layout.addLayout(form_layout)

        # Spacer
        main_layout.addSpacing(20)

        # Desktop Menu Entry section
        menu_section_label = QLabel("Desktop Menu Entry:")
        menu_section_label.setStyleSheet(f"color: {self.t('fg_primary')}; font-weight: bold; font-size: 13px;")
        main_layout.addWidget(menu_section_label)

        menu_desc = QLabel("Create a .desktop file for this project in your application menu. Includes a right-click menu to quickly switch between projects.")
        menu_desc.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 12px;")
        menu_desc.setWordWrap(True)
        main_layout.addWidget(menu_desc)

        menu_btn_layout = QHBoxLayout()
        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """
        create_desktop_btn = QPushButton("Create Menu Entry")
        create_desktop_btn.setStyleSheet(btn_style)
        create_desktop_btn.setToolTip("Create/update .desktop file for this project")
        create_desktop_btn.clicked.connect(self.regenerate_desktop_file)
        menu_btn_layout.addWidget(create_desktop_btn)
        menu_btn_layout.addStretch()
        main_layout.addLayout(menu_btn_layout)

        main_layout.addStretch()  # Push form to top

        return widget

    def _create_column_tree(self, col_idx, column_data):
        """Create a QTreeWidget for editing a single column's categories and items"""
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setDragEnabled(True)
        tree.setAcceptDrops(True)
        tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setIndentation(20)

        tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: none;
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 4px 0;
                border-bottom: 1px solid {self.t('border')};
            }}
            QTreeWidget::item:selected {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
            }}
            QTreeWidget::item:hover {{
                background-color: {self.t('bg_button_hover')};
            }}
        """)

        # Store column index
        tree.setProperty("col_idx", col_idx)

        # Populate tree with categories and items
        self._populate_column_tree(tree, column_data)

        # Add category button at the top level
        add_category_item = QTreeWidgetItem(tree)
        add_category_item.setText(0, "+ Add Category")
        add_category_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "add_category"})
        add_category_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        # Connect double-click to edit
        tree.itemDoubleClicked.connect(lambda item: self._on_tree_item_double_click(tree, item))

        # Connect drop event for reordering
        tree.model().rowsMoved.connect(lambda: self._on_tree_rows_moved(tree))

        return tree

    def _populate_column_tree(self, tree, column_data):
        """Populate a tree widget with category and item data"""
        tree.clear()

        for category_dict in column_data:
            for category_name, items in category_dict.items():
                # Create category item
                category_item = QTreeWidgetItem(tree)
                category_item.setText(0, f"📁 {category_name}")
                category_item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "category",
                    "name": category_name
                })
                category_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled |
                    Qt.ItemFlag.ItemIsSelectable |
                    Qt.ItemFlag.ItemIsDragEnabled |
                    Qt.ItemFlag.ItemIsDropEnabled
                )
                category_item.setExpanded(True)

                # Add items under category
                for item_idx, item in enumerate(items):
                    name = item[0] if len(item) > 0 else ""
                    path = item[1] if len(item) > 1 else ""
                    app = item[2] if len(item) > 2 else ""

                    item_widget = QTreeWidgetItem(category_item)
                    item_widget.setText(0, f"  {name}")
                    item_widget.setToolTip(0, f"{path} ({app})")
                    item_widget.setData(0, Qt.ItemDataRole.UserRole, {
                        "type": "item",
                        "name": name,
                        "path": path,
                        "app": app,
                        "index": item_idx
                    })
                    item_widget.setFlags(
                        Qt.ItemFlag.ItemIsEnabled |
                        Qt.ItemFlag.ItemIsSelectable |
                        Qt.ItemFlag.ItemIsDragEnabled
                    )

                # Add "Add Item" entry under category
                add_item = QTreeWidgetItem(category_item)
                add_item.setText(0, "  + Add Item")
                add_item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "add_item",
                    "category": category_name
                })
                add_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

    def _on_tree_item_double_click(self, tree, item):
        """Handle double-click on tree items for editing"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        col_idx = tree.property("col_idx")
        item_type = data.get("type")

        if item_type == "category":
            self._show_category_edit_dialog(col_idx, data.get("name"), tree)
        elif item_type == "item":
            parent = item.parent()
            if parent:
                category_data = parent.data(0, Qt.ItemDataRole.UserRole)
                category_name = category_data.get("name") if category_data else None
                if category_name:
                    self._show_item_edit_dialog(col_idx, category_name, data, tree)
        elif item_type == "add_item":
            category_name = data.get("category")
            if category_name:
                self._show_item_edit_dialog(col_idx, category_name, None, tree)
        elif item_type == "add_category":
            self._show_category_edit_dialog(col_idx, None, tree)

    def _show_category_edit_dialog(self, col_idx, category_name, tree):
        """Show dialog for adding/editing a category"""
        is_new = category_name is None
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Category" if is_new else "Edit Category")
        dialog.resize(350, 120)

        layout = QFormLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        input_style = f"""
            QLineEdit {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 6px;
            }}
        """
        label_style = f"color: {self.t('fg_primary')};"

        name_label = QLabel("Category Name:")
        name_label.setStyleSheet(label_style)
        name_input = QLineEdit(category_name or "")
        name_input.setStyleSheet(input_style)
        name_input.setPlaceholderText("Enter category name")
        layout.addRow(name_label, name_input)

        # Delete button for existing categories
        btn_layout = QHBoxLayout()
        if not is_new:
            delete_btn = QPushButton("Delete")
            delete_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.t('bg_danger')};
                    color: {self.t('fg_on_dark')};
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                }}
                QPushButton:hover {{
                    background-color: {self.t('bg_danger_hover')};
                }}
            """)
            delete_btn.clicked.connect(lambda: self._delete_category_from_dialog(col_idx, category_name, tree, dialog))
            btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        btn_layout.addWidget(button_box)

        layout.addRow(btn_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = name_input.text().strip()
            if new_name:
                if is_new:
                    self._add_category_to_config(col_idx, new_name)
                else:
                    self._rename_category_in_config(col_idx, category_name, new_name)
                self._refresh_column_tree(tree, col_idx)

    def _show_item_edit_dialog(self, col_idx, category_name, item_data, tree=None, inline_widget=None):
        """Show dialog for adding/editing an item"""
        is_new = item_data is None
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Item" if is_new else "Edit Item")
        dialog.resize(450, 280)

        layout = QFormLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        input_style = f"""
            QLineEdit, QComboBox, QPlainTextEdit {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 6px;
            }}
        """
        label_style = f"color: {self.t('fg_primary')};"

        # Name field
        name_label = QLabel("Name:")
        name_label.setStyleSheet(label_style)
        name_input = QLineEdit(item_data.get("name", "") if item_data else "")
        name_input.setStyleSheet(input_style)
        name_input.setPlaceholderText("Display name")
        layout.addRow(name_label, name_input)

        # Path field with browse - multi-line
        path_label = QLabel("Path(s)/Folders:")
        path_label.setStyleSheet(label_style)
        path_layout = QVBoxLayout()
        path_input = QPlainTextEdit(item_data.get("path", "") if item_data else "")
        path_input.setStyleSheet(input_style)
        path_input.setPlaceholderText("File path, folder path, or URL (one per line for multiple)")
        path_input.setMaximumHeight(80)
        path_browse = QPushButton("Browse")
        path_browse.clicked.connect(lambda: self._browse_file_or_folder_multiline(path_input))
        path_layout.addWidget(path_input)
        path_layout.addWidget(path_browse)
        layout.addRow(path_label, path_layout)

        # Application field (combobox from icon_preferences)
        app_label = QLabel("Application:")
        app_label.setStyleSheet(label_style)
        app_combo = QComboBox()
        app_combo.setEditable(True)
        app_combo.setStyleSheet(input_style)

        # Populate from icon_preferences
        app_keys = sorted(self.APP_INFO.keys()) if hasattr(self, 'APP_INFO') else []
        app_combo.addItems(app_keys)

        current_app = item_data.get("app", "") if item_data else ""
        if current_app:
            idx = app_combo.findText(current_app)
            if idx >= 0:
                app_combo.setCurrentIndex(idx)
            else:
                app_combo.setEditText(current_app)

        # Update path placeholder based on selected handler
        default_placeholder = "File path, folder path, or URL (one per line for multiple)"
        def update_path_placeholder(app_name):
            if app_name in self.complex_handler_info:
                example = self.complex_handler_info[app_name].get("example", "")
                desc = self.complex_handler_info[app_name].get("description", "")
                if example:
                    path_input.setPlaceholderText(f"Example: {example}")
                else:
                    path_input.setPlaceholderText(default_placeholder)
            else:
                path_input.setPlaceholderText(default_placeholder)

        app_combo.currentTextChanged.connect(update_path_placeholder)
        # Set initial placeholder if editing existing item
        if current_app:
            update_path_placeholder(current_app)

        layout.addRow(app_label, app_combo)

        # Delete button for existing items
        btn_layout = QHBoxLayout()
        if not is_new:
            delete_btn = QPushButton("Delete")
            delete_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.t('bg_danger')};
                    color: {self.t('fg_on_dark')};
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                }}
                QPushButton:hover {{
                    background-color: {self.t('bg_danger_hover')};
                }}
            """)
            delete_btn.clicked.connect(lambda: self._delete_item_from_dialog(
                col_idx, category_name, item_data.get("index"), tree, dialog
            ))
            btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        btn_layout.addWidget(button_box)

        layout.addRow(btn_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = name_input.text().strip()
            new_path = path_input.toPlainText().strip()
            new_app = app_combo.currentText().strip()

            if new_name and new_path:
                if is_new:
                    self._add_item_to_config(col_idx, category_name, new_name, new_path, new_app)
                else:
                    self._update_item_in_config(col_idx, category_name, item_data.get("index"), new_name, new_path, new_app)

                # Save config to file
                self.save_config_to_json()

                # Update UI appropriately
                if inline_widget is not None:
                    # Update the inline widget directly without refreshing
                    inline_widget.name_edit.setText(new_name)
                    inline_widget.path_edit.setPlainText(new_path)
                    inline_widget.app_edit.setText(new_app)
                elif tree is not None:
                    self._refresh_column_tree(tree, col_idx)
                else:
                    self.refresh_projects()

    def _browse_file_or_folder(self, line_edit):
        """Open a dialog to browse for file or folder"""
        # First try file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File or cancel to select folder",
            os.path.expanduser("~"),
            "All Files (*)"
        )
        if file_path:
            line_edit.setText(file_path)
        else:
            # If cancelled, try folder dialog
            folder_path = QFileDialog.getExistingDirectory(
                self,
                "Select Folder",
                os.path.expanduser("~")
            )
            if folder_path:
                line_edit.setText(folder_path)

    def _browse_file_or_folder_multiline(self, text_edit):
        """Open a dialog to browse for file or folder, appending to QPlainTextEdit"""
        # First try file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File or cancel to select folder",
            os.path.expanduser("~"),
            "All Files (*)"
        )
        if file_path:
            current = text_edit.toPlainText()
            if current and not current.endswith('\n'):
                text_edit.setPlainText(current + '\n' + file_path)
            elif current:
                text_edit.setPlainText(current + file_path)
            else:
                text_edit.setPlainText(file_path)
        else:
            # If cancelled, try folder dialog
            folder_path = QFileDialog.getExistingDirectory(
                self,
                "Select Folder",
                os.path.expanduser("~")
            )
            if folder_path:
                current = text_edit.toPlainText()
                if current and not current.endswith('\n'):
                    text_edit.setPlainText(current + '\n' + folder_path)
                elif current:
                    text_edit.setPlainText(current + folder_path)
                else:
                    text_edit.setPlainText(folder_path)

    def _add_category_to_config(self, col_idx, category_name):
        """Add a new category to a column"""
        column = self.COLUMN_1
        column.append({category_name: []})

    def _rename_category_in_config(self, col_idx, old_name, new_name):
        """Rename a category in the config"""
        if old_name == new_name:
            return
        column = self.COLUMN_1
        for category_dict in column:
            if old_name in category_dict:
                category_dict[new_name] = category_dict.pop(old_name)
                break

    def _delete_category_from_dialog(self, col_idx, category_name, tree, dialog):
        """Delete a category after confirmation"""
        reply = QMessageBox.question(
            dialog,
            "Delete Category",
            f"Delete '{category_name}' and all its items?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            column = self.COLUMN_1
            for i, category_dict in enumerate(column):
                if category_name in category_dict:
                    del column[i]
                    break
            dialog.reject()
            self._refresh_column_tree(tree, col_idx)

    def _add_item_to_config(self, col_idx, category_name, name, path, app):
        """Add a new item to a category"""
        column = self.COLUMN_1
        for category_dict in column:
            if category_name in category_dict:
                category_dict[category_name].append([name, path, app or "kate"])
                break

    def _update_item_in_config(self, col_idx, category_name, item_idx, name, path, app):
        """Update an existing item in the config"""
        column = self.COLUMN_1
        for category_dict in column:
            if category_name in category_dict:
                items = category_dict[category_name]
                if item_idx is not None and item_idx < len(items):
                    items[item_idx] = [name, path, app or "kate"]
                break

    def _delete_item_from_dialog(self, col_idx, category_name, item_idx, tree, dialog):
        """Delete an item after confirmation"""
        reply = QMessageBox.question(
            dialog,
            "Delete Item",
            "Delete this item?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            column = self.COLUMN_1
            for category_dict in column:
                if category_name in category_dict:
                    items = category_dict[category_name]
                    if item_idx is not None and item_idx < len(items):
                        del items[item_idx]
                    break
            dialog.reject()
            if tree is not None:
                self._refresh_column_tree(tree, col_idx)
            else:
                self.refresh_projects()

    def _refresh_column_tree(self, tree, col_idx):
        """Refresh a column tree with current data"""
        column = self.COLUMN_1
        self._populate_column_tree(tree, column)

        # Re-add the "Add Category" item
        add_category_item = QTreeWidgetItem(tree)
        add_category_item.setText(0, "+ Add Category")
        add_category_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "add_category"})
        add_category_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

    def _on_tree_rows_moved(self, tree):
        """Handle drag-drop reordering in the tree"""
        # Rebuild column data from tree structure
        new_column = []

        for i in range(tree.topLevelItemCount()):
            category_item = tree.topLevelItem(i)
            data = category_item.data(0, Qt.ItemDataRole.UserRole)

            if data and data.get("type") == "category":
                category_name = data.get("name")
                items = []

                for j in range(category_item.childCount()):
                    child = category_item.child(j)
                    child_data = child.data(0, Qt.ItemDataRole.UserRole)

                    if child_data and child_data.get("type") == "item":
                        items.append([
                            child_data.get("name", ""),
                            child_data.get("path", ""),
                            child_data.get("app", "")
                        ])

                new_column.append({category_name: items})

        # Update the single column
        self.COLUMN_1 = new_column

    def _create_icons_tab(self):
        """Create the icon preferences tab content"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)

        # List widget for icons
        self._icons_list = QListWidget()
        self._icons_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
            }}
            QListWidget::item {{
                padding: 6px;
                border-bottom: 1px solid {self.t('border')};
            }}
            QListWidget::item:selected {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
            }}
            QListWidget::item:hover {{
                background-color: {self.t('bg_button_hover')};
            }}
        """)
        self._icons_list.itemDoubleClicked.connect(self._edit_icon_entry)
        layout.addWidget(self._icons_list)

        # Button row
        btn_layout = QHBoxLayout()
        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """

        add_btn = QPushButton("Add Icon")
        add_btn.setStyleSheet(btn_style)
        add_btn.clicked.connect(self._add_icon_entry)
        btn_layout.addWidget(add_btn)

        edit_btn = QPushButton("Edit Selected")
        edit_btn.setStyleSheet(btn_style)
        edit_btn.clicked.connect(lambda: self._edit_icon_entry())
        btn_layout.addWidget(edit_btn)

        delete_btn = QPushButton("Delete Selected")
        delete_btn.setStyleSheet(btn_style)
        delete_btn.clicked.connect(self._delete_icon_entry)
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Load icons
        self._populate_icons_list()

        return widget

    def _populate_icons_list(self):
        """Populate the icons list from icon_preferences.json"""
        self._icons_list.clear()
        icon_prefs_file = os.path.join(self.script_dir, "icon_preferences.json")

        try:
            if os.path.exists(icon_prefs_file):
                with open(icon_prefs_file, 'r') as f:
                    self._icon_prefs = json.load(f)
            else:
                self._icon_prefs = {}
        except Exception as e:
            print(f"Error loading icon preferences: {e}")
            self._icon_prefs = {}

        for app_name, prefs in sorted(self._icon_prefs.items()):
            icon = prefs.get("icon", "")
            display_name = prefs.get("name", app_name)
            item = QListWidgetItem(f"{icon}  {app_name} → {display_name}")
            item.setData(Qt.ItemDataRole.UserRole, app_name)
            self._icons_list.addItem(item)

    def _add_icon_entry(self):
        """Add a new icon entry"""
        result = self._show_icon_edit_dialog("Add Icon", "", "", "")
        if result:
            app_name, icon, display_name = result
            if app_name:
                self._icon_prefs[app_name] = {"icon": icon, "name": display_name}
                self._save_icon_preferences()
                self._populate_icons_list()

    def _edit_icon_entry(self, item=None):
        """Edit the selected icon entry"""
        if item is None:
            item = self._icons_list.currentItem()
        if not item:
            return

        app_name = item.data(Qt.ItemDataRole.UserRole)
        prefs = self._icon_prefs.get(app_name, {})
        icon = prefs.get("icon", "")
        display_name = prefs.get("name", "")

        result = self._show_icon_edit_dialog("Edit Icon", app_name, icon, display_name)
        if result:
            new_app_name, new_icon, new_display_name = result
            # Remove old entry if name changed
            if new_app_name != app_name:
                del self._icon_prefs[app_name]
            self._icon_prefs[new_app_name] = {"icon": new_icon, "name": new_display_name}
            self._save_icon_preferences()
            self._populate_icons_list()

    def _show_icon_edit_dialog(self, title, app_name, icon, display_name):
        """Show dialog for adding/editing an icon entry"""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(400, 180)

        layout = QFormLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        input_style = f"""
            QLineEdit {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 6px;
            }}
        """
        label_style = f"color: {self.t('fg_primary')};"

        app_label = QLabel("App Name:")
        app_label.setStyleSheet(label_style)
        app_input = QLineEdit(app_name)
        app_input.setStyleSheet(input_style)
        app_input.setPlaceholderText("e.g., firefox, code, dolphin")
        layout.addRow(app_label, app_input)

        icon_label = QLabel("Icon:")
        icon_label.setStyleSheet(label_style)
        icon_input = QLineEdit(icon)
        icon_input.setStyleSheet(input_style)
        icon_input.setPlaceholderText("Emoji(s) to display, e.g., 🌐")
        layout.addRow(icon_label, icon_input)

        name_label = QLabel("Display Name:")
        name_label.setStyleSheet(label_style)
        name_input = QLineEdit(display_name)
        name_input.setStyleSheet(input_style)
        name_input.setPlaceholderText("Human-readable name")
        layout.addRow(name_label, name_input)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addRow(button_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            return (app_input.text().strip(), icon_input.text().strip(), name_input.text().strip())
        return None

    def _delete_icon_entry(self):
        """Delete the selected icon entry with confirmation"""
        item = self._icons_list.currentItem()
        if not item:
            return

        app_name = item.data(Qt.ItemDataRole.UserRole)

        reply = QMessageBox.question(
            self,
            "Delete Icon",
            f"Are you sure you want to delete the icon for '{app_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            del self._icon_prefs[app_name]
            self._save_icon_preferences()
            self._populate_icons_list()

    def _create_handlers_tab(self):
        """Create the launch handlers tab content"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)

        # Info label
        info_label = QLabel("Configure advanced launch handlers for more complex tasks like viewing a debug log in a terminal, or starting an SSH session. Some examples are provided below, see also the README.md file.")
        info_label.setStyleSheet(f"color: {self.t('fg_secondary')}; margin-bottom: 10px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # List widget for handlers
        self._handlers_list = QListWidget()
        self._handlers_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {self.t('border')};
            }}
            QListWidget::item:selected {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
            }}
            QListWidget::item:hover {{
                background-color: {self.t('bg_button_hover')};
            }}
        """)
        self._handlers_list.itemDoubleClicked.connect(self._edit_handler_entry)
        layout.addWidget(self._handlers_list)

        # Button row
        btn_layout = QHBoxLayout()
        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QPushButton:disabled {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_secondary')};
            }}
        """

        add_btn = QPushButton("Add Handler")
        add_btn.setStyleSheet(btn_style)
        add_btn.clicked.connect(self._add_handler_entry)
        btn_layout.addWidget(add_btn)

        self._edit_handler_btn = QPushButton("Edit Selected")
        self._edit_handler_btn.setStyleSheet(btn_style)
        self._edit_handler_btn.clicked.connect(lambda: self._edit_handler_entry())
        btn_layout.addWidget(self._edit_handler_btn)

        self._delete_handler_btn = QPushButton("Delete Selected")
        self._delete_handler_btn.setStyleSheet(btn_style)
        self._delete_handler_btn.clicked.connect(self._delete_handler_entry)
        btn_layout.addWidget(self._delete_handler_btn)

        self._copy_handler_btn = QPushButton("Copy as Custom")
        self._copy_handler_btn.setStyleSheet(btn_style)
        self._copy_handler_btn.setToolTip("Copy a built-in handler as a custom handler (allows overriding)")
        self._copy_handler_btn.clicked.connect(self._copy_handler_as_custom)
        btn_layout.addWidget(self._copy_handler_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Populate the list
        self._populate_handlers_list()

        # Connect selection change to update button states
        self._handlers_list.itemSelectionChanged.connect(self._update_handler_buttons)
        self._update_handler_buttons()

        return widget

    def _populate_handlers_list(self):
        """Populate the handlers list with all available handlers"""
        self._handlers_list.clear()

        # Collect all handler names
        all_handlers = {}

        # Add built-in simple handlers
        for name, handler in self.builtin_handlers.items():
            all_handlers[name] = {
                'type': 'builtin',
                'data': handler,
                'description': handler.get('description', ''),
                'example': handler.get('example', '')
            }

        # Add custom handlers (may override built-in)
        for name, handler in self.custom_handlers.items():
            all_handlers[name] = {
                'type': 'custom',
                'data': handler,
                'description': handler.get('description', ''),
                'example': handler.get('example', '')
            }

        # Add complex handlers
        for name in self.complex_handlers.keys():
            if name not in all_handlers:  # Don't override if already in simple handlers
                # Get info from COMPLEX_HANDLER_INFO
                info = self.complex_handler_info.get(name, {})
                all_handlers[name] = {
                    'type': 'complex',
                    'data': None,
                    'description': info.get('description', 'Python handler'),
                    'example': info.get('example', '')
                }

        # Sort and add to list
        for name in sorted(all_handlers.keys()):
            info = all_handlers[name]
            handler_type = info['type']
            description = info['description']
            example = info['example']

            # Format display text
            if handler_type == 'custom':
                badge = "[Custom]"
            elif handler_type == 'builtin':
                badge = "[Built-in]"
            else:  # complex
                badge = "[Python]"

            # Two-line display: name + description + badge on line 1, example on line 2
            line1 = f"{name:<20} {description:<40} {badge}"
            if example:
                line2 = f"{'':20} Example: {example}"
                display_text = f"{line1}\n{line2}"
            else:
                display_text = line1

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, {'name': name, 'type': handler_type})

            # Use monospace font for alignment
            font = QFont("monospace")
            font.setPointSize(10)
            item.setFont(font)

            # Set taller size hint for two-line items
            if example:
                item.setSizeHint(QSize(0, 36))

            self._handlers_list.addItem(item)

    def _update_handler_buttons(self):
        """Update button enabled states based on selection"""
        item = self._handlers_list.currentItem()
        if not item:
            self._edit_handler_btn.setEnabled(False)
            self._edit_handler_btn.setText("Edit Selected")
            self._delete_handler_btn.setEnabled(False)
            self._copy_handler_btn.setEnabled(False)
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        handler_type = data.get('type', '')

        # Custom handlers can be edited, others can be viewed
        is_custom = handler_type == 'custom'
        self._edit_handler_btn.setEnabled(True)  # Always enabled for view/edit
        self._edit_handler_btn.setText("Edit Selected" if is_custom else "View Selected")
        self._delete_handler_btn.setEnabled(is_custom)

        # Built-in and complex handlers can be copied as custom
        self._copy_handler_btn.setEnabled(handler_type in ('builtin', 'complex'))

    def _add_handler_entry(self):
        """Add a new custom handler"""
        result = self._show_handler_edit_dialog("Add Handler", "", {})
        if result:
            name, handler_data = result
            if name:
                self.custom_handlers[name] = handler_data
                self._save_custom_handlers()
                # Rebuild merged handlers
                self.launch_handlers = {**self.builtin_handlers, **self.custom_handlers}
                self._populate_handlers_list()

    def _edit_handler_entry(self, item=None):
        """Edit or view the selected handler"""
        if item is None:
            item = self._handlers_list.currentItem()
        if not item:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        name = data.get('name', '')
        handler_type = data.get('type', '')

        # Get handler data based on type
        if handler_type == 'custom':
            handler_data = self.custom_handlers.get(name, {})
            readonly = False
            title = "Edit Handler"
        elif handler_type == 'builtin':
            handler_data = self.builtin_handlers.get(name, {})
            readonly = True
            title = f"View Handler: {name} [Built-in]"
        else:  # complex
            # For complex handlers, show the actual function source code
            func = self.complex_handlers.get(name)
            docstring = func.__doc__ if func and func.__doc__ else "Python function handler"
            try:
                source_code = inspect.getsource(func)
            except (TypeError, OSError):
                source_code = "(Could not retrieve source code)"
            # Get info from COMPLEX_HANDLER_INFO
            info = self.complex_handler_info.get(name, {})
            handler_data = {
                'command': source_code,
                'description': info.get('description', docstring.strip().split('\n')[0]),
                'example': info.get('example', ''),
                '_is_python_func': True  # Flag for dialog to adjust height
            }
            readonly = True
            title = f"View Handler: {name} [Python]"

        result = self._show_handler_edit_dialog(title, name, handler_data, readonly=readonly)
        if result:
            new_name, new_handler_data = result
            # Remove old entry if name changed
            if new_name != name:
                del self.custom_handlers[name]
            self.custom_handlers[new_name] = new_handler_data
            self._save_custom_handlers()
            # Rebuild merged handlers
            self.launch_handlers = {**self.builtin_handlers, **self.custom_handlers}
            self._populate_handlers_list()

    def _delete_handler_entry(self):
        """Delete the selected custom handler"""
        item = self._handlers_list.currentItem()
        if not item:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        name = data.get('name', '')
        handler_type = data.get('type', '')

        if handler_type != 'custom':
            return

        reply = QMessageBox.question(
            self,
            "Delete Handler",
            f"Are you sure you want to delete the handler '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            del self.custom_handlers[name]
            self._save_custom_handlers()
            # Rebuild merged handlers
            self.launch_handlers = {**self.builtin_handlers, **self.custom_handlers}
            self._populate_handlers_list()

    def _copy_handler_as_custom(self):
        """Copy a built-in or complex handler as a new custom handler"""
        item = self._handlers_list.currentItem()
        if not item:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        name = data.get('name', '')
        handler_type = data.get('type', '')

        if handler_type == 'builtin':
            # Copy built-in handler data
            handler_data = self.builtin_handlers.get(name, {}).copy()
        elif handler_type == 'complex':
            # For complex handlers, create a template
            func = self.complex_handlers.get(name)
            docstring = func.__doc__ if func and func.__doc__ else ""
            handler_data = {
                'command': '',  # User must provide
                'description': f"Custom version of {name}"
            }
            QMessageBox.information(
                self,
                "Copy Complex Handler",
                f"Complex handlers use Python functions and cannot be directly copied.\n\n"
                f"A new custom handler template will be created. You'll need to provide "
                f"the command yourself.\n\nOriginal handler documentation:\n{docstring[:300]}..."
                if len(docstring) > 300 else
                f"Complex handlers use Python functions and cannot be directly copied.\n\n"
                f"A new custom handler template will be created. You'll need to provide "
                f"the command yourself."
            )
        else:
            return

        # Show edit dialog with copied data
        result = self._show_handler_edit_dialog(f"Copy Handler: {name}", name, handler_data)
        if result:
            new_name, new_handler_data = result
            if new_name:
                self.custom_handlers[new_name] = new_handler_data
                self._save_custom_handlers()
                # Rebuild merged handlers
                self.launch_handlers = {**self.builtin_handlers, **self.custom_handlers}
                self._populate_handlers_list()

    def _show_handler_edit_dialog(self, title, handler_name, handler_data, readonly=False):
        """Show dialog for adding/editing/viewing a handler entry"""
        is_python_func = handler_data.get('_is_python_func', False)

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        # Larger dialog for Python function source code
        if is_python_func:
            dialog.resize(700, 650)
        else:
            dialog.resize(500, 420)

        layout = QFormLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        input_style = f"""
            QLineEdit, QPlainTextEdit, QComboBox {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 6px;
            }}
        """
        readonly_style = f"""
            QLineEdit, QPlainTextEdit, QComboBox {{
                background-color: {self.t('bg_primary')};
                color: {self.t('fg_secondary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 6px;
            }}
        """
        label_style = f"color: {self.t('fg_primary')};"
        checkbox_style = f"color: {self.t('fg_primary')};"

        style = readonly_style if readonly else input_style

        # Handler Name
        name_label = QLabel("Handler Name:")
        name_label.setStyleSheet(label_style)
        name_input = QLineEdit(handler_name)
        name_input.setStyleSheet(style)
        name_input.setPlaceholderText("e.g., my_terminal, deploy_script")
        name_input.setReadOnly(readonly)
        layout.addRow(name_label, name_input)

        # Command / Source Code
        cmd_label = QLabel("Source Code:" if is_python_func else "Command:")
        cmd_label.setStyleSheet(label_style)
        cmd_input = QPlainTextEdit()
        cmd_input.setStyleSheet(style)
        cmd_input.setReadOnly(readonly)

        # Adjust height based on content type
        if is_python_func:
            cmd_input.setMinimumHeight(300)
            # Use monospace font for code
            code_font = QFont("monospace")
            code_font.setPointSize(9)
            cmd_input.setFont(code_font)
            cmd_input.setPlaceholderText("")
        else:
            cmd_input.setMaximumHeight(80)
            cmd_input.setPlaceholderText("e.g., konsole --workdir {path}\nor for shell: cd {path} && npm start")

        # Convert command to display format
        command = handler_data.get('command', '')
        if isinstance(command, list):
            cmd_input.setPlainText(' '.join(command))
        else:
            cmd_input.setPlainText(command)
        layout.addRow(cmd_label, cmd_input)

        # Type
        type_label = QLabel("Type:")
        type_label.setStyleSheet(label_style)
        type_combo = QComboBox()
        type_combo.addItems(["exec", "shell"])
        type_combo.setCurrentText(handler_data.get('type', 'exec'))
        type_combo.setStyleSheet(style)
        type_combo.setToolTip("exec: Command as list of arguments\nshell: Command run through bash -c")
        type_combo.setEnabled(not readonly)
        layout.addRow(type_label, type_combo)

        # Get configured terminal name for label
        terminal_name = self.get_configured_terminal()

        # Run in Terminal
        terminal_check = QCheckBox(f"Run in terminal ({terminal_name})")
        terminal_check.setChecked(handler_data.get('terminal', False))
        terminal_check.setStyleSheet(checkbox_style)
        terminal_check.setToolTip(f"Wrap command in {terminal_name} terminal")
        terminal_check.setEnabled(not readonly)
        layout.addRow("", terminal_check)

        # Keep Terminal Open
        hold_check = QCheckBox("Keep terminal open after command finishes")
        hold_check.setChecked(handler_data.get('hold', False))
        hold_check.setStyleSheet(checkbox_style)
        hold_check.setToolTip("Use --hold flag to keep terminal open")
        hold_check.setEnabled(not readonly)
        layout.addRow("", hold_check)

        # Description
        desc_label = QLabel("Description:")
        desc_label.setStyleSheet(label_style)
        desc_input = QLineEdit(handler_data.get('description', ''))
        desc_input.setStyleSheet(style)
        desc_input.setPlaceholderText("Human-readable description of what this handler does")
        desc_input.setReadOnly(readonly)
        layout.addRow(desc_label, desc_input)

        # Example
        example_label = QLabel("Example:")
        example_label.setStyleSheet(label_style)
        example_input = QLineEdit(handler_data.get('example', ''))
        example_input.setStyleSheet(style)
        example_input.setPlaceholderText("e.g., ~/source ~/destination")
        example_input.setReadOnly(readonly)
        layout.addRow(example_label, example_input)

        # Buttons - different for readonly vs edit mode
        if readonly:
            button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            button_box.rejected.connect(dialog.reject)
        else:
            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
        layout.addRow(button_box)

        if readonly:
            dialog.exec()
            return None

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = name_input.text().strip()
            cmd_text = cmd_input.toPlainText().strip()
            handler_type = type_combo.currentText()

            # Build handler data
            new_handler = {}

            # Parse command based on type
            if handler_type == 'exec':
                # Split into list for exec type
                new_handler['command'] = cmd_text.split()
            else:
                # Keep as string for shell type
                new_handler['command'] = cmd_text
                new_handler['type'] = 'shell'

            # Only add optional fields if set
            if terminal_check.isChecked():
                new_handler['terminal'] = True
            if hold_check.isChecked():
                new_handler['hold'] = True

            description = desc_input.text().strip()
            if description:
                new_handler['description'] = description

            example = example_input.text().strip()
            if example:
                new_handler['example'] = example

            return (new_name, new_handler)
        return None

    def _save_custom_handlers(self):
        """Save custom handlers to JSON file"""
        custom_handlers_file = os.path.join(self.script_dir, "launch_handlers_custom.json")
        try:
            with open(custom_handlers_file, 'w') as f:
                json.dump(self.custom_handlers, f, indent=2)
        except Exception as e:
            print(f"Error saving custom handlers: {e}")
            QMessageBox.warning(self, "Error", f"Failed to save custom handlers: {e}")

    def _browse_file(self, line_edit, file_filter="All Files (*)"):
        """Open file picker and set result to line edit"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File",
            os.path.expanduser("~"),
            file_filter
        )
        if file_path:
            line_edit.setText(file_path)

    def _browse_folder(self, line_edit):
        """Open folder picker and set result to line edit"""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Folder",
            os.path.expanduser("~")
        )
        if folder_path:
            line_edit.setText(folder_path)

    def _apply_settings(self, dialog):
        """Apply settings without closing the dialog"""
        # === Save Project Settings ===
        if hasattr(self, '_proj_default_viewer'):
            # Viewer defaults
            self.config_column2_default = self._proj_default_viewer.currentText() or None
            self.config_pdf_file = self._proj_pdf_file.text().strip() or None
            self.config_webview_url = self._proj_webview_url.text().strip() or None
            self.config_image_file = self._proj_image_file.text().strip() or None
            self.config_console_path = self._proj_console_path.text().strip() or None
            self.config_terminal = self._proj_terminal.currentText().strip() or None

            # Save config to JSON (columns already updated by tree editing)
            self._save_project_config()

        # === Save Advanced Settings ===
        # Only save if the settings widgets exist (i.e., we're in the full settings dialog)
        if hasattr(self, '_settings_theme_combo'):
            # Save theme
            new_theme = self._settings_theme_combo.currentText()
            old_theme = self.settings.get("theme", "system")
            self.settings["theme"] = new_theme

            # Save other settings
            pdfviewer = self._settings_pdfviewer.text().strip()
            if pdfviewer:
                self.settings["pdfviewer"] = pdfviewer
            elif "pdfviewer" in self.settings:
                del self.settings["pdfviewer"]

            note_editor = self._settings_note_editor.text().strip()
            if note_editor:
                self.settings["open_note_external"] = note_editor
            elif "open_note_external" in self.settings:
                del self.settings["open_note_external"]

            terminal = self._settings_terminal.currentText().strip()
            if terminal:
                self.settings["terminal"] = terminal
            elif "terminal" in self.settings:
                del self.settings["terminal"]  # Remove to enable auto-detection

            editor = self._settings_editor.currentText().strip()
            if editor:
                self.settings["editor"] = editor
            elif "editor" in self.settings:
                del self.settings["editor"]  # Remove to enable auto-detection

            file_manager = self._settings_file_manager.currentText().strip()
            if file_manager:
                self.settings["file_manager"] = file_manager
            elif "file_manager" in self.settings:
                del self.settings["file_manager"]  # Remove to enable auto-detection

            notes_folder = self._settings_notes_folder.text().strip()
            if notes_folder:
                self.settings["notes_folder"] = notes_folder
            elif "notes_folder" in self.settings:
                del self.settings["notes_folder"]

            self.settings["enable_baloo_tags"] = self._settings_baloo.isChecked()

            joplin_token = self._settings_joplin.text().strip()
            if joplin_token:
                self.settings["joplin_token"] = joplin_token
            elif "joplin_token" in self.settings:
                del self.settings["joplin_token"]

            self.save_settings()

            # Update launch handlers with new editor/file_manager/terminal settings
            if self.handlers_module:
                if hasattr(self.handlers_module, 'set_terminal_config'):
                    self.handlers_module.set_terminal_config(
                        self.get_configured_terminal(),
                        self._get_terminal_workdir_command,
                        self._get_terminal_command
                    )
                if hasattr(self.handlers_module, 'set_editor_config'):
                    self.handlers_module.set_editor_config(self.get_configured_editor())
                if hasattr(self.handlers_module, 'set_file_manager_config'):
                    self.handlers_module.set_file_manager_config(self.get_configured_file_manager())

            # Apply theme change if needed
            if new_theme != old_theme:
                if new_theme == "system":
                    self.current_theme = detect_system_theme()
                else:
                    self.current_theme = new_theme
                self.theme = get_theme(self.current_theme)
                self.apply_global_styles()

        # Always refresh to show project setting changes
        self.refresh_projects()

    def _save_project_config(self):
        """Save project settings to the config JSON file"""
        try:
            # Read existing data to preserve other state
            config_data = {}
            if os.path.exists(self.current_config_file):
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)

            # Update viewer defaults
            if self.config_column2_default:
                config_data["column2_default"] = self.config_column2_default
            elif "column2_default" in config_data:
                del config_data["column2_default"]

            if self.config_pdf_file:
                config_data["pdf_file"] = self.config_pdf_file
            elif "pdf_file" in config_data:
                del config_data["pdf_file"]

            if self.config_webview_url:
                config_data["webview_url"] = self.config_webview_url
            elif "webview_url" in config_data:
                del config_data["webview_url"]

            if self.config_image_file:
                config_data["image_file"] = self.config_image_file
            elif "image_file" in config_data:
                del config_data["image_file"]

            if self.config_console_path:
                config_data["console_path"] = self.config_console_path
            elif "console_path" in config_data:
                del config_data["console_path"]

            if self.config_terminal:
                config_data["terminal"] = self.config_terminal
            elif "terminal" in config_data:
                del config_data["terminal"]

            # Update column headers and columns (single column only)
            config_data["column_headers"] = self.COLUMN_HEADERS
            config_data["columns"] = [self.COLUMN_1]

            with open(self.current_config_file, 'w') as f:
                json.dump(config_data, f, indent=2)

        except Exception as e:
            print(f"Error saving project config: {e}")
            QMessageBox.warning(self, "Error", f"Failed to save project: {e}")

    def _save_settings_and_close(self, dialog):
        """Save settings and close the dialog"""
        self._apply_settings(dialog)
        dialog.accept()

    def _save_project_settings_and_close(self, dialog):
        """Save project settings, exit edit mode, and close the dialog"""
        self.edit_mode = False
        self._apply_settings(dialog)
        dialog.accept()

    def _save_icon_preferences(self):
        """Save icon preferences to JSON file"""
        icon_prefs_file = os.path.join(self.script_dir, "icon_preferences.json")
        try:
            with open(icon_prefs_file, 'w') as f:
                json.dump(self._icon_prefs, f, indent=2)
        except Exception as e:
            print(f"Error saving icon preferences: {e}")
            QMessageBox.warning(self, "Error", f"Failed to save icon preferences: {e}")

    def get_item_button_style(self, clicked=False):
        """Get stylesheet for item buttons (normal or clicked state)"""
        if clicked:
            return f"""
                QPushButton {{
                    text-align: left;
                    padding-left: 10px;
                    background-color: {self.t('bg_success')};
                    color: {self.t('fg_on_dark')};
                    border: 1px solid {self.t('bg_success_hover')};
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    background-color: {self.t('bg_button_hover')};
                    color: {self.t('fg_on_dark')};
                    border: 1px solid {self.t('bg_category_hover')};
                }}
            """
        else:
            return f"""
                QPushButton {{
                    text-align: left;
                    padding-left: 10px;
                    background-color: {self.t('bg_button')};
                    color: {self.t('fg_primary')};
                    border: 1px solid {self.t('border')};
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    background-color: {self.t('bg_button_hover')};
                    color: {self.t('fg_on_dark')};
                    border: 1px solid {self.t('bg_category_hover')};
                }}
            """

    def on_item_clicked(self, btn, path, app):
        """Handle item button click - update style and open"""
        btn.setStyleSheet(self.get_item_button_style(clicked=True))
        self.open_in_app(path, app)

    def set_status(self, message, status_type="success"):
        """Set status label with themed color"""
        color_map = {
            "success": self.t('status_success'),
            "error": self.t('status_error'),
            "info": self.t('status_info'),
            "warning": self.t('status_warning'),
        }
        color = color_map.get(status_type, self.t('status_success'))
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color}; margin: 10px; font-weight: bold;")

    def setup_first_run(self):
        """Copy example files to projects/notes directories on first run"""
        examples_dir = os.path.join(self.script_dir, "examples")
        projects_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        notes_dir = self.settings.get("notes_folder", os.path.join(self.script_dir, "notes"))
        notes_dir = os.path.expanduser(notes_dir)

        # Check if examples directory exists
        if not os.path.exists(examples_dir):
            return

        # Migration: if old "configs" directory exists but "projects" doesn't, rename it
        old_configs_dir = os.path.join(self.script_dir, "configs")
        if os.path.exists(old_configs_dir) and not os.path.exists(projects_dir):
            try:
                os.rename(old_configs_dir, projects_dir)
                print(f"Migrated configs/ to projects/")
            except Exception as e:
                print(f"Could not migrate configs/ to projects/: {e}")

        # Copy example project if projects directory doesn't exist or is empty
        if not os.path.exists(projects_dir) or not os.listdir(projects_dir):
            os.makedirs(projects_dir, exist_ok=True)
            example_config = os.path.join(examples_dir, "projectflow.json")
            if os.path.exists(example_config):
                shutil.copy(example_config, os.path.join(projects_dir, "projectflow.json"))

        # Copy example note if notes directory doesn't exist or is empty
        if not os.path.exists(notes_dir) or not os.listdir(notes_dir):
            os.makedirs(notes_dir, exist_ok=True)
            example_note = os.path.join(examples_dir, "projectflow.md")
            if os.path.exists(example_note):
                shutil.copy(example_note, os.path.join(notes_dir, "projectflow.md"))

    def ensure_desktop_file_installed(self):
        """Install base .desktop file for GNOME/COSMIC dock icon matching.

        On KDE, per-project WM_CLASS naming works for Activities pinning.
        On GNOME/COSMIC, the app_id must match an installed .desktop file
        for the dock to show the correct icon.
        """
        desktop_file = os.path.expanduser("~/.local/share/applications/projectflow.desktop")

        # Skip if already installed
        if os.path.exists(desktop_file):
            return

        # Skip on KDE - it doesn't need this mechanism
        de = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
        if 'kde' in de or 'plasma' in de:
            return

        # Use projectflow-nix wrapper if available (for NixOS), otherwise projectflow.py
        nix_wrapper = os.path.join(self.script_dir, "projectflow-nix")
        if os.path.exists(nix_wrapper):
            script_path = nix_wrapper
        else:
            script_path = os.path.join(self.script_dir, "projectflow.py")

        # Choose appropriate icon based on DE
        if 'gnome' in de:
            icon = "text-x-script"
        else:
            icon = "preferences-desktop-icons"

        content = f"""[Desktop Entry]
Type=Application
Name=ProjectFlow
Comment=Quick Launcher for Projects and Files
Exec={script_path} %F
Icon={icon}
Terminal=false
Categories=Utility;Development;
StartupWMClass=projectflow
StartupNotify=true
"""
        os.makedirs(os.path.dirname(desktop_file), exist_ok=True)
        try:
            with open(desktop_file, 'w') as f:
                f.write(content)
        except Exception as e:
            print(f"Could not install desktop file: {e}")

    def add_to_recent_projects(self, config_path):
        """Add a project to recent projects list (max 10)"""
        if "recent_projects" not in self.settings:
            self.settings["recent_projects"] = []

        # Remove if already in list
        if config_path in self.settings["recent_projects"]:
            self.settings["recent_projects"].remove(config_path)

        # Add to front of list
        self.settings["recent_projects"].insert(0, config_path)

        # Keep only 10 most recent
        self.settings["recent_projects"] = self.settings["recent_projects"][:10]

        self.save_settings()

    def save_settings(self):
        """Save user settings to JSON file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get_config_file_to_use(self):
        """Determine which config file to use based on settings"""
        # Priority:
        # 1. Command-line argument
        # 2. Default config set in settings
        # 3. First pinned project
        # 4. Last used config
        # 5. Standard default (projectflow.json)

        # Check if config file was passed as CLI argument
        if self.config_file_arg:
            # Support both relative and absolute paths
            if os.path.isabs(self.config_file_arg):
                config_path = self.config_file_arg
            else:
                config_path = os.path.join(self.script_dir, self.config_file_arg)

            if os.path.exists(config_path):
                return config_path
            else:
                print(f"Warning: Config file '{self.config_file_arg}' not found. Using default config.")

        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))

        # Check if default config is set
        if self.settings.get("default_project"):
            config_path = os.path.join(configs_dir, self.settings["default_project"])
            if os.path.exists(config_path):
                return config_path

        # Check for first pinned project
        pinned = self.settings.get("pinned_projects", [])
        if pinned:
            first_pinned = pinned[0]
            # Handle both relative and absolute paths
            if os.path.isabs(first_pinned):
                pinned_path = first_pinned
            else:
                pinned_path = os.path.join(configs_dir, first_pinned)
            if os.path.exists(pinned_path):
                return pinned_path

        # Check last used config
        if self.settings.get("last_used_project"):
            if os.path.exists(self.settings["last_used_project"]):
                return self.settings["last_used_project"]

        # Fall back to standard default
        default_project = os.path.join(self.script_dir, "projectflow.json")

        # If configs directory exists, look for a default there
        if os.path.exists(configs_dir):
            configs_default = os.path.join(configs_dir, "projectflow.json")
            if os.path.exists(configs_default):
                return configs_default

        return default_project

    def load_config(self):
        """Load configuration from JSON config file or use defaults"""
        try:
            # Load icon preferences from shared file
            self.APP_INFO = self.load_icon_preferences()

            # Try to load config from the current config file
            if os.path.exists(self.current_config_file):
                # Load JSON config
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)

                # Extract configuration from JSON - use only first column
                columns = config_data.get('columns', [[]])
                self.COLUMN_1 = columns[0] if len(columns) > 0 else self.get_default_column_1()
                # Single column header
                self.COLUMN_HEADERS = ["Shortcuts and Actions"]
                # Load default PDF file path if specified
                self.config_pdf_file = config_data.get('pdf_file', None)
                # Load default webview URL if specified
                self.config_webview_url = config_data.get('webview_url', None)
                # Load default image file path if specified
                self.config_image_file = config_data.get('image_file', None)
                # Load default console path if specified
                self.config_console_path = config_data.get('console_path', None)
                # Load default column2 mode (pdf, webview, or image)
                self.config_column2_default = config_data.get('column2_default', None)
                # Load per-config terminal override
                self.config_terminal = config_data.get('terminal', None)
            else:
                # Create default config file
                self.create_default_project(self.current_config_file)
                # Use defaults - single column only
                self.COLUMN_1 = self.get_default_column_1()
                self.COLUMN_HEADERS = ["Shortcuts and Actions"]
                self.config_pdf_file = None
                self.config_webview_url = None
                self.config_image_file = None
                self.config_console_path = None
                self.config_column2_default = None
                self.config_terminal = None
        except Exception as e:
            raise Exception(f"Error loading config: {str(e)}")

    def load_icon_preferences(self):
        """Load icon preferences from shared icon_preferences.json file"""
        icon_prefs_path = os.path.join(self.script_dir, "icon_preferences.json")
        try:
            if os.path.exists(icon_prefs_path):
                with open(icon_prefs_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load icon_preferences.json: {e}")
        return self.get_default_app_info()

    def get_tag_name_for_config(self):
        """Derive Baloo tag name from config filename.

        Examples:
            main.json -> main
            work.json -> work
        """
        config_name = os.path.basename(self.current_config_file)
        # Remove .json extension
        return os.path.splitext(config_name)[0]

    def get_tagged_files(self):
        """Get files from Baloo tags + manually added files.

        Returns a list of file paths tagged in Dolphin/Baloo with this project's tag name.
        """
        tagged = []

        # Get tag name from config filename
        tag_name = self.get_tag_name_for_config()

        # Query Baloo if enabled
        if self.settings.get('enable_baloo_tags', False):
            try:
                result = subprocess.run(
                    ['baloosearch6', f'tag:{tag_name}'],
                    capture_output=True, text=True, timeout=2
                )
                for line in result.stdout.strip().split('\n'):
                    # Skip empty lines and the "Elapsed:" summary line
                    if line and not line.startswith('Elapsed'):
                        tagged.append(line.strip())
            except FileNotFoundError:
                # baloosearch6 not available (non-KDE system)
                pass
            except subprocess.TimeoutExpired:
                # Baloo taking too long, skip
                pass
            except Exception as e:
                print(f"Error querying Baloo: {e}")

        # Filter non-existent files
        return [f for f in tagged if os.path.exists(f)]

    def get_notes_folder(self):
        """Get the folder where notes are stored as markdown files"""
        # Use configured folder, or default to 'notes' subdirectory
        folder = self.settings.get("notes_folder", os.path.join(self.script_dir, "notes"))
        return os.path.expanduser(folder)

    def get_notes_file_path(self):
        """Get the markdown file path for current config's notes"""
        folder = self.get_notes_folder()
        # Derive filename from config name (underscores become hyphens)
        config_name = os.path.basename(self.current_config_file)
        config_name = os.path.splitext(config_name)[0]
        return os.path.join(folder, f"{config_name.replace('_', '-')}.md")

    def get_archive_folder(self):
        """Get the hidden .archive folder within the notes folder"""
        notes_folder = self.get_notes_folder()
        return os.path.join(notes_folder, ".archive")

    def get_archive_file_path(self):
        """Get the archive file path for current config's notes"""
        archive_folder = self.get_archive_folder()
        # Use same naming convention as notes files
        config_name = os.path.basename(self.current_config_file)
        config_name = os.path.splitext(config_name)[0]
        return os.path.join(archive_folder, f"{config_name.replace('_', '-')}.md")

    def archive_notes(self):
        """Archive current notes to the archive file with a dated separator"""
        if not hasattr(self, 'notepad'):
            return

        # Get current notes content
        notes_html = self.notepad.toHtml()
        markdown_content = self.html_to_markdown(notes_html)

        # Don't archive if notes are empty
        if not markdown_content.strip():
            QMessageBox.information(self, "Archive Notes", "No notes to archive.")
            return

        # Confirm with user
        reply = QMessageBox.question(
            self, "Archive Notes",
            "Archive current notes and clear the notepad?\n\n"
            "This will append your notes to the archive file with a timestamp.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Create archive folder if needed
        archive_folder = self.get_archive_folder()
        os.makedirs(archive_folder, exist_ok=True)

        # Create dated separator with human-readable date
        from datetime import datetime
        now = datetime.now()
        day = now.day
        suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        human_date = now.strftime(f"%H:%M -- {day}{suffix} %B %Y")
        separator = f"------------------------------\n{human_date}\n------------------------------\n\n"

        # Read existing archive content
        archive_file = self.get_archive_file_path()
        existing_content = ""
        if os.path.exists(archive_file):
            with open(archive_file, 'r', encoding='utf-8') as f:
                existing_content = f.read()

        # Prepend new content with date header first (newest at top)
        new_archive = separator + markdown_content + "\n\n" + existing_content

        # Write to archive file
        with open(archive_file, 'w', encoding='utf-8') as f:
            f.write(new_archive)

        # Clear the notepad
        self.notepad.clear()
        self.save_notes("")

        QMessageBox.information(self, "Archive Notes", "Notes archived successfully.")

    def view_archive(self):
        """Open a dialog to view the archive for the current config"""
        archive_file = self.get_archive_file_path()

        if not os.path.exists(archive_file):
            QMessageBox.information(self, "View Archive", "No archive exists for this project yet.")
            return

        # Read archive content
        with open(archive_file, 'r', encoding='utf-8') as f:
            archive_content = f.read()

        # Create dialog with scrollable text browser
        archive_dialog = QDialog(self)
        archive_dialog.setWindowTitle(f"Archive - {os.path.basename(self.current_config_file)}")
        archive_dialog.resize(600, 500)

        layout = QVBoxLayout(archive_dialog)

        # Text browser with markdown converted to HTML
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        html_content = self.markdown_to_html(archive_content)
        text_browser.setHtml(html_content)
        text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {self.t('bg_help')};
                color: {self.t('fg_primary')};
                font-family: sans-serif;
                font-size: 13px;
                padding: 10px;
                border: 1px solid {self.t('border')};
            }}
        """)
        layout.addWidget(text_browser)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(archive_dialog.reject)

        # Add "Open in Editor" button if external editor is configured
        external_editor = self.settings.get("open_note_external")
        if external_editor:
            open_btn = button_box.addButton("Open in Editor", QDialogButtonBox.ButtonRole.ActionRole)
            open_btn.clicked.connect(lambda: subprocess.Popen([external_editor, archive_file], start_new_session=True))

        layout.addWidget(button_box)

        archive_dialog.exec()

    def markdown_to_html(self, markdown):
        """Convert markdown to HTML for QTextEdit display"""
        import html as html_module

        text = markdown

        # Convert headings (must do before other processing)
        for level in range(6, 0, -1):
            pattern = rf'^({"#" * level})\s+(.+)$'
            text = re.sub(pattern, rf'<h{level}>\2</h{level}>', text, flags=re.MULTILINE)

        # Convert bold (**text** or __text__)
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

        # Convert italic (*text* or _text_) - but not inside words
        text = re.sub(r'(?<!\w)\*([^*]+?)\*(?!\w)', r'<i>\1</i>', text)
        text = re.sub(r'(?<!\w)_([^_]+?)_(?!\w)', r'<i>\1</i>', text)

        # Convert inline code
        text = re.sub(r'`([^`]+?)`', r'<code style="font-family: monospace; background-color: #2d2d2d; color: #f0f0f0; padding: 2px 5px;">\1</code>', text)

        # Convert emphasis/highlight (==text==) - use span to preserve styling in QTextEdit
        text = re.sub(r'==(.+?)==', r'<span style="background-color: #9c0c15; color: #f0f0f0; padding: 4px 10px;">\1</span>', text)

        # Convert links [text](url)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

        # Convert bullet lists (lines starting with - or *)
        text = re.sub(r'^[\-\*]\s+(.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)

        # Convert numbered lists (lines starting with 1. 2. etc)
        text = re.sub(r'^\d+\.\s+(.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)

        # Convert line breaks (two spaces at end of line or double newline)
        text = re.sub(r'  \n', '<br>', text)
        text = re.sub(r'\n\n', '</p><p>', text)
        text = re.sub(r'\n', '<br>', text)

        # Wrap in paragraph tags
        text = f'<p>{text}</p>'

        # Clean up empty paragraphs
        text = re.sub(r'<p>\s*</p>', '', text)

        return text

    def load_notes(self):
        """Load notes from markdown file, PDF state and webview state from JSON config"""
        self.notes_data = {}
        # Initialize PDF state variables
        self.pdf_doc = None
        self.pdf_current_page = 0
        self.pdf_page_count = 0
        self.pdf_zoom = 1.5
        self.pdf_path = None
        self.pdf_label = None
        self.pdf_scroll = None
        # Initialize webview state variables
        self.webview = None
        self.webview_url = None
        self.webview_url_bar = None
        self.column2_mode = "pdf"  # "pdf", "webview", or "image"
        # Initialize image state variables
        self.image_path = None
        self.image_zoom = 1.0
        self.image_label = None
        self.image_scroll = None

        try:
            # Load notes from markdown file
            notes_file = self.get_notes_file_path()
            if os.path.exists(notes_file):
                with open(notes_file, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
                html_content = self.markdown_to_html(markdown_content)
                self.notes_data = {"content": html_content}

            # Load PDF/webview state from JSON config
            if os.path.exists(self.current_config_file):
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)

                # Migrate legacy notes from JSON to markdown file
                if "notes" in config_data and not os.path.exists(notes_file):
                    legacy_html = config_data["notes"]
                    if legacy_html.strip():
                        # Convert to markdown and save
                        markdown_content = self.html_to_markdown(legacy_html)
                        folder = self.get_notes_folder()
                        os.makedirs(folder, exist_ok=True)
                        with open(notes_file, 'w', encoding='utf-8') as f:
                            f.write(markdown_content)
                        # Load the converted content
                        html_content = self.markdown_to_html(markdown_content)
                        self.notes_data = {"content": html_content}
                        # Remove notes from JSON config
                        del config_data["notes"]
                        with open(self.current_config_file, 'w') as f:
                            json.dump(config_data, f, indent=2)

                # Load PDF state
                if "pdf_state" in config_data:
                    pdf_state = config_data["pdf_state"]
                    self.pdf_path = pdf_state.get("path")
                    self.pdf_current_page = pdf_state.get("page", 0)
                # Load webview state
                if "webview_state" in config_data:
                    webview_state = config_data["webview_state"]
                    self.webview_url = webview_state.get("url")
                    self.column2_mode = webview_state.get("mode", "pdf")
                # Load image state
                if "image_state" in config_data:
                    image_state = config_data["image_state"]
                    self.image_path = image_state.get("path")

            # Use config-specified PDF file as fallback if no saved path
            if not self.pdf_path and hasattr(self, 'config_pdf_file') and self.config_pdf_file:
                self.pdf_path = self.config_pdf_file

            # Use config-specified webview URL, falling back to saved URL
            if hasattr(self, 'config_webview_url') and self.config_webview_url:
                self.webview_url = self.config_webview_url

            # Use config-specified image file as fallback if no saved path
            if not self.image_path and hasattr(self, 'config_image_file') and self.config_image_file:
                self.image_path = self.config_image_file

            # Use config-specified console path
            if hasattr(self, 'config_console_path') and self.config_console_path:
                self.console_path = self.config_console_path
            else:
                self.console_path = None

            # Use config-specified column2 default mode if set
            if hasattr(self, 'config_column2_default') and self.config_column2_default:
                if self.config_column2_default in ("pdf", "webview", "image", "help", "examples", "console"):
                    self.column2_mode = self.config_column2_default
        except Exception as e:
            print(f"Error loading notes: {e}")
            self.notes_data = {}

    def load_launch_handlers(self):
        """Load launch handlers from launch_handlers.py and launch_handlers_custom.json"""
        self.builtin_handlers = {}  # Simple handlers from launch_handlers.py
        self.custom_handlers = {}   # User-defined handlers from JSON
        self.complex_handlers = {}  # Python function handlers (cannot be edited via UI)
        self.complex_handler_info = {}  # Metadata for complex handlers (descriptions, examples)
        self.handlers_module = None  # Store module reference for later config updates

        # Load built-in handlers from launch_handlers.py
        handlers_file = os.path.join(self.script_dir, "launch_handlers.py")
        if os.path.exists(handlers_file):
            try:
                import importlib.util
                import sys
                spec = importlib.util.spec_from_file_location("launch_handlers", handlers_file)
                handlers_module = importlib.util.module_from_spec(spec)
                sys.modules["launch_handlers"] = handlers_module  # Register in sys.modules
                spec.loader.exec_module(handlers_module)
                self.handlers_module = handlers_module  # Store reference

                if hasattr(handlers_module, 'LAUNCH_HANDLERS'):
                    self.builtin_handlers = handlers_module.LAUNCH_HANDLERS.copy()
                if hasattr(handlers_module, 'COMPLEX_HANDLERS'):
                    self.complex_handlers = handlers_module.COMPLEX_HANDLERS
                if hasattr(handlers_module, 'COMPLEX_HANDLER_INFO'):
                    self.complex_handler_info = handlers_module.COMPLEX_HANDLER_INFO
                # Configure terminal for complex handlers
                if hasattr(handlers_module, 'set_terminal_config'):
                    handlers_module.set_terminal_config(
                        self.get_configured_terminal(),
                        self._get_terminal_workdir_command,
                        self._get_terminal_command
                    )
                # Configure editor for complex handlers
                if hasattr(handlers_module, 'set_editor_config'):
                    handlers_module.set_editor_config(self.get_configured_editor())
                # Configure file manager for complex handlers
                if hasattr(handlers_module, 'set_file_manager_config'):
                    handlers_module.set_file_manager_config(self.get_configured_file_manager())

            except Exception as e:
                print(f"Error loading launch_handlers.py: {e}")

        # Load custom handlers from JSON
        custom_handlers_file = os.path.join(self.script_dir, "launch_handlers_custom.json")
        if os.path.exists(custom_handlers_file):
            try:
                with open(custom_handlers_file, 'r') as f:
                    self.custom_handlers = json.load(f)
            except Exception as e:
                print(f"Error loading launch_handlers_custom.json: {e}")

        # Merge handlers: custom overrides built-in
        self.launch_handlers = {**self.builtin_handlers, **self.custom_handlers}

    def detect_desktop_environment(self):
        """Detect the current desktop environment.

        Returns one of: 'kde', 'gnome', 'xfce', 'cosmic', 'mate', 'cinnamon',
        'lxqt', 'lxde', or 'unknown'
        """
        desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()

        if 'kde' in desktop or 'plasma' in desktop:
            return 'kde'
        elif 'gnome' in desktop or 'ubuntu' in desktop:
            return 'gnome'
        elif 'xfce' in desktop:
            return 'xfce'
        elif 'cosmic' in desktop:
            return 'cosmic'
        elif 'mate' in desktop:
            return 'mate'
        elif 'cinnamon' in desktop:
            return 'cinnamon'
        elif 'lxqt' in desktop:
            return 'lxqt'
        elif 'lxde' in desktop:
            return 'lxde'
        return 'unknown'

    def detect_default_terminal(self):
        """Detect appropriate terminal based on desktop environment."""
        # Prefer xdg-terminal-exec if available (freedesktop standard, respects user's default)
        if shutil.which('xdg-terminal-exec'):
            return 'xdg-terminal-exec'

        de = self.detect_desktop_environment()

        terminal_map = {
            'kde': 'konsole',
            'gnome': 'gnome-terminal',
            'xfce': 'xfce4-terminal',
            'cosmic': 'cosmic-term',
            'mate': 'mate-terminal',
            'cinnamon': 'gnome-terminal',
            'lxqt': 'qterminal',
            'lxde': 'lxterminal',
        }

        if de in terminal_map:
            return terminal_map[de]

        # Fallback: check what's installed
        for term in ['konsole', 'gnome-terminal', 'xfce4-terminal', 'alacritty', 'kitty', 'xterm']:
            if shutil.which(term):
                return term

        return 'xterm'  # Ultimate fallback

    def detect_default_editor(self):
        """Detect appropriate editor based on desktop environment."""
        de = self.detect_desktop_environment()

        editor_map = {
            'kde': 'kate',
            'gnome': 'gedit',
            'xfce': 'mousepad',
            'cosmic': 'cosmic-edit',
            'mate': 'pluma',
            'cinnamon': 'xed',
            'lxqt': 'featherpad',
            'lxde': 'leafpad',
        }

        if de in editor_map and shutil.which(editor_map[de]):
            return editor_map[de]

        # Fallback: check what's installed
        for editor in ['code', 'kate', 'gedit', 'nano']:
            if shutil.which(editor):
                return editor

        return 'xdg-open'  # Ultimate fallback

    def get_configured_editor(self):
        """Get the configured editor, with auto-detection fallback."""
        editor = self.settings.get("editor", "")
        if not editor:
            editor = self.detect_default_editor()
        return editor

    def detect_default_file_manager(self):
        """Detect appropriate file manager based on desktop environment."""
        de = self.detect_desktop_environment()

        fm_map = {
            'kde': 'dolphin',
            'gnome': 'nautilus',
            'xfce': 'thunar',
            'cosmic': 'cosmic-files',
            'mate': 'caja',
            'cinnamon': 'nemo',
            'lxqt': 'pcmanfm-qt',
            'lxde': 'pcmanfm',
        }

        if de in fm_map and shutil.which(fm_map[de]):
            return fm_map[de]

        # Fallback: check what's installed
        for fm in ['dolphin', 'nautilus', 'thunar', 'pcmanfm']:
            if shutil.which(fm):
                return fm

        return 'xdg-open'  # Ultimate fallback

    def get_configured_file_manager(self):
        """Get the configured file manager, with auto-detection fallback."""
        fm = self.settings.get("file_manager", "")
        if not fm:
            fm = self.detect_default_file_manager()
        return fm

    def get_configured_terminal(self):
        """Get the configured terminal, with auto-detection fallback."""
        # Per-config terminal overrides global setting
        terminal = getattr(self, 'config_terminal', None) or self.settings.get("terminal", "")
        if not terminal:
            terminal = self.detect_default_terminal()
        return terminal

    def _get_terminal_command(self, shell_cmd, hold=False):
        """Build terminal command based on configured terminal emulator"""
        terminal = self.get_configured_terminal()

        # Terminal-specific argument patterns
        # Format: (hold_flag, execute_separator, needs_shell_wrapper)
        terminal_configs = {
            "xdg-terminal-exec": (None, [], True),  # command passed directly as args
            "konsole": ("--hold", ["-e"], True),
            "gnome-terminal": (None, ["--"], True),  # gnome-terminal doesn't have hold
            "xfce4-terminal": ("--hold", ["-e"], True),
            "terminator": ("--hold", ["-e"], True),
            "tilix": ("--hold", ["-e"], True),
            "alacritty": ("--hold", ["-e"], True),
            "kitty": ("--hold", [], True),  # kitty just appends command
            "wezterm": (None, ["start", "--"], True),  # wezterm start -- cmd
            "foot": ("--hold", [], True),  # foot just appends command
            "xterm": ("-hold", ["-e"], True),
            "urxvt": ("-hold", ["-e"], True),
            "ghostty": (None, ["-e"], True),
            "hyper": (None, ["-e"], True),
            "tabby": (None, ["run"], True),
            "guake": (None, ["-e"], True),
            "tilda": (None, ["-c"], True),
            "warp-terminal": (None, [], True),
        }

        config = terminal_configs.get(terminal, ("--hold", ["-e"], True))
        hold_flag, exec_sep, needs_shell = config

        terminal_cmd = [terminal]

        # Add hold flag if requested and supported
        if hold and hold_flag:
            terminal_cmd.append(hold_flag)

        # Add execute separator
        terminal_cmd.extend(exec_sep)

        # Add the shell command
        if needs_shell:
            terminal_cmd.extend(["bash", "-c", shell_cmd])
        else:
            terminal_cmd.append(shell_cmd)

        return terminal_cmd

    def _get_terminal_workdir_command(self, path):
        """Build command to open terminal at specified directory."""
        terminal = self.get_configured_terminal()

        # Terminal-specific workdir argument patterns
        workdir_args = {
            "xdg-terminal-exec": ["bash", "-c", "cd " + shlex.quote(path) + " && exec $SHELL"],
            "konsole": ["--workdir", path],
            "gnome-terminal": ["--working-directory=" + path],
            "xfce4-terminal": ["--working-directory=" + path],
            "terminator": ["--working-directory=" + path],
            "tilix": ["--working-directory=" + path],
            "alacritty": ["--working-directory", path],
            "kitty": ["--directory", path],
            "wezterm": ["start", "--cwd", path],
            "foot": ["--working-directory=" + path],
            "xterm": ["-e", "cd " + shlex.quote(path) + " && exec $SHELL"],
            "urxvt": ["-cd", path],
            "ghostty": ["--working-directory=" + path],
            "cosmic-term": ["--working-directory", path],
            "mate-terminal": ["--working-directory=" + path],
            "qterminal": ["--workdir", path],
            "lxterminal": ["--working-directory=" + path],
        }

        args = workdir_args.get(terminal, ["--workdir", path])
        return [terminal] + args

    def _build_handler_command(self, handler, expanded_path):
        """Build command list from a simple handler definition"""
        command = handler.get("command", [])
        handler_type = handler.get("type", "exec")
        use_terminal = handler.get("terminal", False)
        hold = handler.get("hold", False)

        # Replace {path} placeholder in command
        if isinstance(command, list):
            cmd = [arg.replace("{path}", expanded_path) for arg in command]
        else:
            # String command (for shell type)
            cmd = command.replace("{path}", expanded_path)

        # Handle shell type commands
        if handler_type == "shell":
            if use_terminal:
                return self._get_terminal_command(cmd, hold)
            else:
                return ["bash", "-c", cmd]

        return cmd

    def save_notes(self, notes_html=None):
        """Save notes to markdown file, PDF/webview state to JSON config"""
        try:
            # Save notes to markdown file if provided
            if notes_html is not None:
                markdown_content = self.html_to_markdown(notes_html)
                notes_file = self.get_notes_file_path()
                folder = self.get_notes_folder()
                os.makedirs(folder, exist_ok=True)
                with open(notes_file, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)

            # Save PDF/webview state to JSON config
            config_data = {}
            if os.path.exists(self.current_config_file):
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)

            # Remove legacy notes from JSON if present
            if "notes" in config_data:
                del config_data["notes"]

            # Update PDF state
            if self.pdf_path:
                config_data["pdf_state"] = {
                    "path": self.pdf_path,
                    "page": self.pdf_current_page
                }

            # Update webview state
            config_data["webview_state"] = {
                "url": self.webview_url,
                "mode": self.column2_mode
            }

            # Update image state
            if self.image_path:
                config_data["image_state"] = {
                    "path": self.image_path
                }

            # Save back to config file
            with open(self.current_config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
        except Exception as e:
            print(f"Error saving notes: {e}")

    def set_viewer_as_default(self):
        """Set the current viewer content as default for this config"""
        try:
            # Determine what to save based on current mode
            if self.column2_mode == "pdf":
                if not self.pdf_path:
                    QMessageBox.information(self, "Set Default", "No PDF loaded to set as default.")
                    return
                resource_key = "pdf_file"
                resource_value = self.pdf_path
            elif self.column2_mode == "webview":
                if not self.webview_url:
                    QMessageBox.information(self, "Set Default", "No webpage loaded to set as default.")
                    return
                resource_key = "webview_url"
                resource_value = self.webview_url
            elif self.column2_mode == "image":
                if not self.image_path:
                    QMessageBox.information(self, "Set Default", "No image loaded to set as default.")
                    return
                resource_key = "image_file"
                resource_value = self.image_path
            elif self.column2_mode == "console":
                if not hasattr(self, 'console_path') or not self.console_path:
                    QMessageBox.information(self, "Set Default", "No console path set.")
                    return
                resource_key = "console_path"
                resource_value = self.console_path
            else:
                return

            # Load existing config
            config_data = {}
            if os.path.exists(self.current_config_file):
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)

            # Update the resource and column2_default
            config_data[resource_key] = resource_value
            config_data["column2_default"] = self.column2_mode

            # Save back to config
            with open(self.current_config_file, 'w') as f:
                json.dump(config_data, f, indent=2)

            # Update internal state
            if self.column2_mode == "pdf":
                self.config_pdf_file = resource_value
            elif self.column2_mode == "webview":
                self.config_webview_url = resource_value
            elif self.column2_mode == "image":
                self.config_image_file = resource_value
            elif self.column2_mode == "console":
                self.config_console_path = resource_value
            self.config_column2_default = self.column2_mode

            QMessageBox.information(self, "Set Default", f"Set as default {self.column2_mode} viewer.")

        except Exception as e:
            print(f"Error setting viewer default: {e}")
            QMessageBox.warning(self, "Error", f"Failed to set default: {e}")

    def create_default_project(self, config_file):
        """Create a default configuration file in JSON format"""
        # Ensure the parent directory exists
        config_dir = os.path.dirname(config_file)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)

        # Ensure .json extension
        if not config_file.endswith('.json'):
            config_file = config_file + '.json'
            self.current_config_file = config_file

        # Create default JSON config (single column layout)
        default_project = {
            "column_headers": ["Shortcuts and Actions"],
            "columns": [
                [
                    {
                        "Places": [
                            ["Home", "~/", "file_manager"],
                            ["Documents", "~/Documents", "file_manager"],
                            ["Downloads", "~/Downloads", "file_manager"]
                        ]
                    },
                    {
                        "Files": [
                            ["Notes", "~/Documents/notes.txt", "editor"],
                            ["Todo", "~/Documents/todo.txt", "editor"]
                        ]
                    },
                    {
                        "Websites": [
                            ["GitHub", "https://github.com/", "browser"],
                            ["DuckDuckGo", "https://duckduckgo.com/", "browser"]
                        ]
                    }
                ]
            ],
            "column2_default": "help"
        }

        with open(config_file, 'w') as f:
            json.dump(default_project, f, indent=2)

    def get_default_column_1(self):
        return [
            {
                "Web Projects": [
                    ("Main Website", "~/projects/website", "kate"),
                    ("Blog", "~/projects/blog", "kate"),
                ]
            },
            {
                "Work": [
                    ("Client A", "~/work/client-a", "kate"),
                ]
            },
            {
                "Personal": [
                    ("Scripts", "~/scripts", "kate"),
                ]
            },
        ]

    def get_default_app_info(self):
        return {
            "kate": {"icon": "📝", "name": "Kate"},
            "libreoffice": {"icon": "📄", "name": "LibreOffice"},
            "gimp": {"icon": "🎨", "name": "GIMP"},
            "okular": {"icon": "📕", "name": "Okular"},
            "code": {"icon": "💻", "name": "VS Code"},
        }

    def init_ui(self):
        # Set window properties
        config_name = os.path.basename(self.current_config_file)

        # Create a clean display name (without extension, capitalized)
        display_name = config_name.replace('.json', '').replace('_config', '').replace('_', ' ').title()

        # Set window title and icon text
        self.setWindowTitle(f"{display_name} - ProjectFlow")
        self.setWindowIconText(display_name)

        # Set application identification based on desktop environment
        desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
        app = QApplication.instance()

        if 'kde' in desktop or 'plasma' in desktop:
            # KDE: Set unique WM_CLASS for per-project pinning in Activities
            app.setApplicationName(f"ProjectFlow-{display_name}")
            app.setApplicationDisplayName(f"{display_name} - ProjectFlow")
            app.setDesktopFileName(f"ProjectFlow-{display_name}")
        else:
            # GNOME/COSMIC/others: Keep consistent app_id for dock icon matching
            # Only change display name - desktopFileName must match installed .desktop file
            app.setApplicationDisplayName(f"{display_name} - ProjectFlow")

        self.setGeometry(100, 100, 1000, 600)

        # Create central widget and layout
        central_widget = QWidget()
        central_widget.setStyleSheet(f"background-color: {self.t('bg_primary')};")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create the Scroll Area and the "Inner" Container
        self.main_scroll = QScrollArea()
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setStyleSheet(f"QScrollArea {{ background-color: {self.t('bg_primary')}; border: none; }}")
        scroll_content_widget = QWidget()  # This widget will hold all your UI
        scroll_content_widget.setStyleSheet(f"background-color: {self.t('bg_primary')};")
        scroll_layout = QVBoxLayout(scroll_content_widget)  # The new "home" for your elements

        # Connect them
        self.main_scroll.setWidget(scroll_content_widget)
        main_layout.addWidget(self.main_scroll)  # Put the scroll area into the main window

        # Add title bar with project name and status
        self.create_title_bar(scroll_layout)

        # Build main content
        self.build_main_content(scroll_layout)

    def create_title_bar(self, parent_layout):
        """Create a title bar with project name on left and status on right"""
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(5, 5, 5, 10)

        # Project title on left (clickable search)
        config_name = os.path.basename(self.current_config_file)
        config_name = os.path.splitext(config_name)[0]
        if config_name.endswith('_config'):
            config_name = config_name[:-7]
        config_name = config_name.replace('_', ' ').upper()

        # Get available configs for search
        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        config_paths = []
        if os.path.isdir(configs_dir):
            config_paths = [os.path.join(configs_dir, f) for f in os.listdir(configs_dir)
                           if f.endswith('.json')]

        self.title_search = ClickableSearchTitle(config_name, config_paths, self.t, self)
        self.title_search.configSelected.connect(self.switch_to_config)
        title_bar.addWidget(self.title_search)

        # Keyboard shortcuts to focus search (only create once)
        if not hasattr(self, '_search_shortcuts_created'):
            search_shortcut1 = QShortcut(QKeySequence("/"), self)
            search_shortcut1.activated.connect(self.focus_project_search)
            search_shortcut2 = QShortcut(QKeySequence("F3"), self)
            search_shortcut2.activated.connect(self.focus_project_search)
            self._search_shortcuts_created = True

        title_bar.addStretch()

        # Status label on right
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 12px;")
        title_bar.addWidget(self.status_label)

        parent_layout.addLayout(title_bar)

    def focus_project_search(self):
        """Focus the project search input (called by keyboard shortcut)"""
        if hasattr(self, 'title_search'):
            self.title_search.enter_search_mode()

    def create_projects_section(self, parent_layout):
        """Create unified projects section with toggle between recent and alphabetical modes"""
        # Initialize mode state
        if not hasattr(self, 'projects_mode'):
            self.projects_mode = 'recent'  # 'recent' or 'alphabetical'

        # Header with lines on either side
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(15)

        left_line = QFrame()
        left_line.setFrameShape(QFrame.Shape.HLine)
        left_line.setStyleSheet(f"background-color: {self.t('border')};")
        left_line.setFixedHeight(1)
        header_row.addWidget(left_line, 1)

        # Header label (changes based on mode)
        self.projects_header_label = QLabel("Recent Projects" if self.projects_mode == 'recent' else "All Projects")
        self.projects_header_label.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 12px;")
        header_row.addWidget(self.projects_header_label)

        right_line = QFrame()
        right_line.setFrameShape(QFrame.Shape.HLine)
        right_line.setStyleSheet(f"background-color: {self.t('border')};")
        right_line.setFixedHeight(1)
        header_row.addWidget(right_line, 1)

        # Reset button (only visible in recent mode when pinned projects exist)
        self.reset_btn = QPushButton("↺")
        self.reset_btn.setFixedWidth(20)
        self.reset_btn.setFixedHeight(20)
        self.reset_btn.setToolTip("Reset to recent order (clear pins)")
        self.reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {self.t('fg_muted')};
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {self.t('bg_danger')};
            }}
        """)
        self.reset_btn.clicked.connect(self.reset_pinned_projects)
        self.reset_btn.setVisible(False)  # Will be shown if pinned projects exist
        header_row.addWidget(self.reset_btn)

        # Mode toggle button - shows opposite mode as clickable option
        self.mode_toggle_btn = QPushButton("All Projects")
        self.mode_toggle_btn.setToolTip("Switch to alphabetical view")
        self.mode_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_muted')};
                border: 1px solid #cccccc;
                border-radius: 3px;
                font-size: 11px;
                padding: 3px 8px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """)
        self.mode_toggle_btn.clicked.connect(self.toggle_projects_mode)
        header_row.addWidget(self.mode_toggle_btn)

        parent_layout.addLayout(header_row)

        # Container for project buttons (content changes based on mode)
        self.projects_container = QWidget()
        projects_container_layout = QVBoxLayout(self.projects_container)
        projects_container_layout.setContentsMargins(0, 10, 0, 0)
        projects_container_layout.setSpacing(5)

        self.projects_layout = QVBoxLayout()
        self.projects_layout.setSpacing(5)
        self.projects_layout.setContentsMargins(0, 0, 0, 0)
        projects_container_layout.addLayout(self.projects_layout)

        parent_layout.addWidget(self.projects_container)

        # Populate based on current mode
        self.populate_projects()

    def toggle_projects_mode(self):
        """Toggle between recent and alphabetical project modes"""
        subtle_btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_muted')};
                border: 1px solid #cccccc;
                border-radius: 3px;
                font-size: 11px;
                padding: 3px 8px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """
        if self.projects_mode == 'recent':
            self.projects_mode = 'alphabetical'
            self.projects_header_label.setText("All Projects")
            self.mode_toggle_btn.setText("Recent Projects")
            self.mode_toggle_btn.setToolTip("Switch to recent projects view")
            self.mode_toggle_btn.setStyleSheet(subtle_btn_style)
            self.reset_btn.setVisible(False)
        else:
            self.projects_mode = 'recent'
            self.projects_header_label.setText("Recent Projects")
            self.mode_toggle_btn.setText("All Projects")
            self.mode_toggle_btn.setToolTip("Switch to alphabetical view")
            self.mode_toggle_btn.setStyleSheet(subtle_btn_style)
        self.populate_projects()

    def populate_projects(self):
        """Populate projects based on current mode (recent or alphabetical)"""
        # Clear existing content
        while self.projects_layout.count():
            item = self.projects_layout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
            if item.widget():
                item.widget().deleteLater()

        if self.projects_mode == 'recent':
            self._populate_recent_projects()
        else:
            self._populate_alphabetical_projects()

    def _populate_recent_projects(self):
        """Populate with recent/pinned projects (drag-drop enabled)"""
        recent_projects = self.settings.get("recent_projects", [])
        pinned_projects = self.settings.get("pinned_projects", [])

        # Filter to only existing files
        recent_projects = [c for c in recent_projects if os.path.exists(c)]
        pinned_projects = [c for c in pinned_projects if os.path.exists(c)]

        # Show/hide reset button based on pinned projects
        self.reset_btn.setVisible(len(pinned_projects) > 0)

        # Build combined list: pinned first, then recent (excluding pinned)
        recent_only = [c for c in recent_projects if c not in pinned_projects]
        combined_projects = pinned_projects + recent_only

        # Backfill from available projects if we have fewer than 10
        if len(combined_projects) < 10:
            configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
            if os.path.exists(configs_dir):
                available = []
                for f in os.listdir(configs_dir):
                    if f.endswith('.json'):
                        full_path = os.path.join(configs_dir, f)
                        available.append((full_path, os.path.getmtime(full_path)))
                available.sort(key=lambda x: x[1], reverse=True)
                for config_path, _ in available:
                    if config_path not in combined_projects:
                        combined_projects.append(config_path)
                        if len(combined_projects) >= 10:
                            break

        if not combined_projects:
            return

        # Create horizontal layout with ConfigBarWidget for drag-drop
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(5)
        buttons_layout.setContentsMargins(0, 0, 0, 0)

        self.config_bar_widget = ConfigBarWidget(self)
        config_bar_layout = QHBoxLayout(self.config_bar_widget)
        config_bar_layout.setContentsMargins(0, 0, 0, 0)
        config_bar_layout.setSpacing(5)

        for config_path in combined_projects[:10]:
            is_pinned = config_path in pinned_projects
            btn_container = self._create_config_button(config_path, is_pinned, draggable=True)
            config_bar_layout.addWidget(btn_container)
            self.config_bar_widget.add_button(btn_container, config_path, is_pinned)

        buttons_layout.addWidget(self.config_bar_widget)

        # Left-align if fewer than 10 projects, otherwise let them stretch to fill
        if len(combined_projects) < 10:
            buttons_layout.addStretch()

        self.projects_layout.addLayout(buttons_layout)

    def _populate_alphabetical_projects(self):
        """Populate with all projects alphabetically in a grid of 10 columns"""
        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))

        if not os.path.exists(configs_dir):
            return

        # Get all config files sorted alphabetically
        config_files = []
        for f in os.listdir(configs_dir):
            if f.endswith('.json'):
                full_path = os.path.join(configs_dir, f)
                config_files.append(full_path)
        config_files.sort(key=lambda x: os.path.basename(x).lower())

        if not config_files:
            return

        # Use grid layout for consistent column widths
        max_per_row = 10
        grid = QGridLayout()
        grid.setSpacing(5)
        grid.setContentsMargins(0, 0, 0, 0)

        for idx, config_path in enumerate(config_files):
            row = idx // max_per_row
            col = idx % max_per_row
            btn_container = self._create_config_button(config_path, is_pinned=False, draggable=False)
            grid.addWidget(btn_container, row, col)

        # Set all columns to stretch equally
        for col in range(max_per_row):
            grid.setColumnStretch(col, 1)

        self.projects_layout.addLayout(grid)

    def _create_config_button(self, config_path, is_pinned, draggable=False):
        """Create a config button with new window button"""
        config_name = os.path.basename(config_path)
        display_name = config_name.replace("_config.json", "").replace(".json", "").replace("_", " ")
        display_name = display_name.title()
        is_current = (config_path == self.current_config_file)

        btn_container = QWidget()
        btn_container_layout = QHBoxLayout(btn_container)
        btn_container_layout.setContentsMargins(0, 0, 0, 0)
        btn_container_layout.setSpacing(1)

        # Main button
        if draggable:
            btn = DraggableConfigButton(display_name, config_path)
        else:
            btn = QPushButton(display_name)

        btn.setMinimumHeight(26)
        if draggable:
            btn.setMaximumWidth(150)
        else:
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Style based on current and pinned status
        border_bottom = f"border-bottom: 3px solid {self.t('bg_category')};" if is_pinned else ""
        if is_current:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.t('bg_config_current')};
                    color: {self.t('fg_primary')};
                    font-weight: bold;
                    border: 1px solid {self.t('border_dark')};
                    border-radius: 2px;
                    padding: 4px 8px;
                    font-size: 12px;
                    {border_bottom}
                }}
                QPushButton:hover {{
                    background-color: {self.t('bg_config_hover')};
                    color: {self.t('fg_on_dark')};
                }}
            """)
        else:
            bg_color = self.t('bg_config') if draggable else self.t('bg_config_all')
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg_color};
                    color: {self.t('fg_secondary')};
                    border: 1px solid {self.t('border')};
                    border-radius: 2px;
                    padding: 4px 8px;
                    font-size: 12px;
                    {border_bottom}
                }}
                QPushButton:hover {{
                    background-color: {self.t('bg_config_hover')};
                    color: {self.t('fg_on_dark')};
                }}
            """)

        btn.clicked.connect(lambda checked=False, path=config_path: self.switch_to_config(path))
        if draggable:
            tooltip = f"{'📌 ' if is_pinned else ''}{config_path}\n(Drag to reorder/pin)"
        else:
            tooltip = f"Switch to {config_name}"
        btn.setToolTip(tooltip)
        btn_container_layout.addWidget(btn)

        # New window button
        new_window_btn = QPushButton("↗️")
        new_window_btn.setFixedWidth(26)
        new_window_btn.setMinimumHeight(26)
        arrow_bg = self.t('bg_config_arrow') if draggable else self.t('bg_config_all_arrow')
        border_color = self.t('border_dark') if is_current else self.t('border')
        text_color = self.t('fg_primary') if is_current else self.t('fg_secondary')
        new_window_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {arrow_bg};
                color: {text_color};
                border: 1px solid {border_color};
                border-left: none;
                border-radius: 2px;
                padding: 0px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_config_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """)
        new_window_btn.clicked.connect(lambda checked=False, path=config_path: self.open_config_in_new_window(path))
        new_window_btn.setToolTip("Open in new window")
        btn_container_layout.addWidget(new_window_btn)

        return btn_container

    def handle_config_drop(self, dragged_path, drop_index):
        """Handle a config being dropped at a new position"""
        pinned_projects = self.settings.get("pinned_projects", [])
        recent_projects = self.settings.get("recent_projects", [])

        # Filter to existing files
        pinned_projects = [c for c in pinned_projects if os.path.exists(c)]
        recent_only = [c for c in recent_projects if c not in pinned_projects and os.path.exists(c)]

        # Remove dragged item from both lists
        if dragged_path in pinned_projects:
            pinned_projects.remove(dragged_path)
        if dragged_path in recent_only:
            recent_only.remove(dragged_path)

        # Insert at new position - anything dropped becomes pinned
        # If dropped in pinned area (index < len(pinned)), insert there
        # Otherwise append to pinned (dragging pins it)
        if drop_index <= len(pinned_projects):
            pinned_projects.insert(drop_index, dragged_path)
        else:
            # Dropped after pinned area - still pin it at the end of pinned
            pinned_projects.append(dragged_path)

        # Save and refresh
        self.settings["pinned_projects"] = pinned_projects
        self.save_settings()
        self.refresh_projects()

    def reset_pinned_projects(self):
        """Clear all pinned configs, reverting to recent order"""
        self.settings["pinned_projects"] = []
        self.save_settings()
        self.refresh_projects()

    def handle_item_reorder(self, col_idx, category_name, from_idx, to_idx):
        """Handle an item being dragged to a new position within its category"""
        # Load current config
        try:
            with open(self.current_config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        except Exception as e:
            print(f"Error loading config for reorder: {e}")
            return

        # Get the column data - config uses "columns" array
        if "columns" not in config_data:
            return

        if col_idx >= len(config_data["columns"]):
            return

        column_data = config_data["columns"][col_idx]

        # Find the category in the column
        for category_dict in column_data:
            if category_name in category_dict:
                items = category_dict[category_name]

                # Perform the reorder
                if 0 <= from_idx < len(items) and 0 <= to_idx <= len(items):
                    item = items.pop(from_idx)
                    # Adjust to_idx if we removed an item before it
                    if to_idx > from_idx:
                        to_idx -= 1
                    items.insert(to_idx, item)

                    # Save back to config
                    try:
                        with open(self.current_config_file, 'w', encoding='utf-8') as f:
                            json.dump(config_data, f, indent=2)
                        self.refresh_projects()
                    except Exception as e:
                        print(f"Error saving reordered config: {e}")
                break

    def build_main_content(self, parent_layout):
        """Build the main content area with project columns"""
        # Create horizontal layout for columns
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(15)

        # Layout: Launchers (COLUMN_1) | Viewer | Notepad
        # Always show all three panels
        all_columns = [self.COLUMN_1]

        for col_idx, column_categories in enumerate(all_columns):
            # Create a vertical layout for this entire column
            column_layout = QVBoxLayout()

            # Add column header if provided
            if self.COLUMN_HEADERS and col_idx < len(self.COLUMN_HEADERS):
                header_style = f"""
                    font-weight: bold;
                    font-size: 14px;
                    padding: {self.d('header_label_padding')}px;
                    background-color: {self.t('bg_panel')};
                    color: {self.t('fg_on_dark')};
                    border-radius: 3px;
                """

                if col_idx == 0:
                    # First column: add edit mode and refresh buttons (like column 2 style)
                    header_layout = QHBoxLayout()
                    header_layout.setContentsMargins(0, 0, 0, 0)
                    header_layout.setSpacing(3)

                    # Green button style (matching column 2 toggle button)
                    green_btn_style = f"""
                        QPushButton {{
                            background-color: {self.t('bg_green_1')};
                            color: {self.t('fg_on_dark')};
                            font-weight: bold;
                            border-radius: 3px;
                            padding: 5px;
                        }}
                        QPushButton:hover {{
                            background-color: {self.t('bg_green_2')};
                            color: {self.t('fg_on_dark')};
                        }}
                        QPushButton:checked {{
                            background-color: {self.t('bg_success')};
                        }}
                    """

                    # Edit button
                    edit_btn = QPushButton("Save" if self.edit_mode else "Edit")
                    edit_btn.setMaximumWidth(50)
                    edit_btn.setMinimumHeight(self.d('header_btn_height'))
                    edit_btn.setCheckable(True)
                    edit_btn.setChecked(self.edit_mode)
                    edit_btn.setToolTip("Save and exit edit mode" if self.edit_mode else "Edit shortcuts")
                    edit_btn.setStyleSheet(green_btn_style)
                    edit_btn.clicked.connect(self.toggle_edit_mode)
                    header_layout.addWidget(edit_btn)

                    if self.edit_mode:
                        # Advanced button - opens Project Items tab in settings
                        advanced_btn = QPushButton("Advanced")
                        advanced_btn.setMaximumWidth(85)
                        advanced_btn.setMinimumHeight(self.d('header_btn_height'))
                        advanced_btn.setToolTip("Open advanced project editor")
                        advanced_btn.setStyleSheet(green_btn_style)
                        advanced_btn.clicked.connect(lambda: self.show_project_settings_dialog(0))
                        header_layout.addWidget(advanced_btn)
                    else:
                        # Refresh button
                        refresh_btn = QPushButton("↻")
                        refresh_btn.setMaximumWidth(50)
                        refresh_btn.setMinimumHeight(self.d('header_btn_height'))
                        refresh_btn.setToolTip("Refresh")
                        refresh_btn.setStyleSheet(green_btn_style)
                        refresh_btn.clicked.connect(self.refresh_projects)
                        header_layout.addWidget(refresh_btn)

                    # Header label
                    header = QLabel(self.COLUMN_HEADERS[col_idx])
                    header.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    header.setMinimumHeight(self.d('header_label_height'))
                    header.setStyleSheet(f"""
                        font-weight: bold;
                        font-size: 14px;
                        margin: 0px;
                        padding: {self.d('header_label_padding')}px;
                        background-color: {self.t('bg_panel')};
                        color: {self.t('fg_on_dark')};
                        border-radius: 3px;
                    """)
                    header_layout.addWidget(header, 1)

                    column_layout.addLayout(header_layout)
                    column_layout.setContentsMargins(0, 4, 0, 0)  # left, top, right, bottom
                else:
                    header = QLabel(self.COLUMN_HEADERS[col_idx])
                    header.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    header.setMinimumHeight(self.d('header_label_height'))
                    header.setStyleSheet(header_style)
                    column_layout.addWidget(header)

            # Process each category within this column
            for category_dict in column_categories:
                for category_name, items in category_dict.items():
                    # Create a container for the group box with a custom title button
                    group_container = QWidget()
                    group_container_layout = QVBoxLayout(group_container)
                    group_container_layout.setSpacing(0)
                    group_container_layout.setContentsMargins(0, 0, 0, 0)

                    # Create category header (editable in edit mode)
                    if self.edit_mode:
                        # EDIT MODE: Show category name editor with delete button
                        category_header = QWidget()
                        category_header_layout = QHBoxLayout(category_header)
                        category_header_layout.setContentsMargins(0, 0, 0, 0)
                        category_header_layout.setSpacing(5)

                        category_name_edit = QLineEdit(category_name)
                        category_name_edit.setMinimumHeight(30)
                        category_name_edit.setStyleSheet(f"""
                            QLineEdit {{
                                background-color: {self.t('bg_category')};
                                color: {self.t('fg_on_dark')};
                                border: 2px solid {self.t('bg_category_hover')};
                                border-radius: 5px;
                                font-weight: bold;
                                font-size: 12px;
                                padding-left: 10px;
                            }}
                        """)
                        # Store original name and use editingFinished to rename once when done
                        category_name_edit.setProperty("original_name", category_name)
                        category_name_edit.editingFinished.connect(
                            lambda edit=category_name_edit, c_idx=col_idx: self.rename_category_from_edit(c_idx, edit)
                        )
                        category_header_layout.addWidget(category_name_edit, 1)

                        delete_category_btn = QPushButton("🗑 Delete Category")
                        delete_category_btn.setMaximumWidth(130)
                        delete_category_btn.setStyleSheet(f"""
                            QPushButton {{
                                background-color: {self.t('bg_danger')};
                                color: {self.t('fg_on_dark')};
                                font-weight: bold;
                                border-radius: 3px;
                            }}
                            QPushButton:hover {{
                                background-color: {self.t('bg_danger_hover')};
                                color: {self.t('fg_on_dark')};
                            }}
                        """)
                        delete_category_btn.clicked.connect(
                            lambda checked=False, c_idx=col_idx, c_name=category_name: self.delete_category(c_idx, c_name)
                        )
                        category_header_layout.addWidget(delete_category_btn)

                        group_container_layout.addWidget(category_header)
                    else:
                        # VIEW MODE: Show normal "Open All" button
                        title_btn = QPushButton(f"⚡ {category_name} - Open All")
                        title_btn.setMinimumHeight(30)
                        title_btn.setStyleSheet(f"""
                            QPushButton {{
                                text-align: left;
                                padding-left: 10px;
                                background-color: {self.t('bg_category')};
                                color: {self.t('fg_on_dark')};
                                border: 2px solid {self.t('bg_category_hover')};
                                border-radius: 5px;
                                font-weight: bold;
                                font-size: 12px;
                            }}
                            QPushButton:hover {{
                                background-color: {self.t('bg_category_hover')};
                                border: 2px solid {self.t('border_dark')};
                                color: {self.t('fg_on_dark')};
                            }}
                        """)
                        title_btn.clicked.connect(
                            lambda checked=False, group_items=items: self.open_all_in_group(group_items)
                        )
                        title_btn.setToolTip(f"Click to open all items in {category_name}")
                        group_container_layout.addWidget(title_btn)

                    # Create a group box for the items (without a title since we have the button)
                    group_box = QGroupBox()
                    group_box.setStyleSheet(f"""
                        QGroupBox {{
                            font-weight: bold;
                            border: 1px solid {self.t('border')};
                            border-top: none;
                            border-top-left-radius: 0px;
                            border-top-right-radius: 0px;
                            border-bottom-left-radius: 5px;
                            border-bottom-right-radius: 5px;
                            padding-top: 10px;
                            background-color: {self.t('bg_group')};
                            margin-top: 0px;
                        }}
                    """)

                    group_layout = QVBoxLayout()
                    group_layout.setSpacing(3)

                    # Create drop zone for drag-and-drop reordering (only in view mode)
                    category_drop_zone = None
                    if not self.edit_mode:
                        category_drop_zone = CategoryDropZone(self, col_idx, category_name)
                        drop_zone_layout = QVBoxLayout(category_drop_zone)
                        drop_zone_layout.setContentsMargins(0, 0, 0, 0)
                        drop_zone_layout.setSpacing(3)

                    # Add buttons for each item in this category
                    for idx, item in enumerate(items):
                        # Handle both 2-tuple and 3-tuple formats
                        if len(item) == 2:
                            display_name, path = item
                            app = "kate"  # default
                        else:
                            display_name, path, app = item

                        if self.edit_mode:
                            # EDIT MODE: Show editable fields with controls
                            item_widget = self.create_edit_item_widget(
                                col_idx, category_name, idx, display_name, path, app
                            )
                            group_layout.addWidget(item_widget)

                            # Add separator line between items with spacing
                            group_layout.addSpacing(10)
                            separator = QFrame()
                            separator.setFrameShape(QFrame.Shape.HLine)
                            separator.setStyleSheet(f"background-color: {self.t('border')}; max-height: 1px;")
                            group_layout.addWidget(separator)
                            group_layout.addSpacing(5)
                        else:
                            # VIEW MODE: Show normal button
                            # Get app icon if available
                            app_icon = ""
                            if app in self.APP_INFO:
                                app_icon = self.APP_INFO[app]["icon"] + " "

                            # Use DraggableItemButton for drag-and-drop reordering
                            btn = DraggableItemButton(f"{app_icon}{display_name}", col_idx, category_name, idx)
                            btn.setMinimumHeight(30)
                            btn.setStyleSheet(self.get_item_button_style())
                            btn.clicked.connect(
                                lambda checked=False, p=path, a=app, b=btn: self.on_item_clicked(b, p, a)
                            )

                            # Set tooltip showing the command and path (with drag hint)
                            btn.setToolTip(f"[{app}] {path}\n(Drag to reorder)")

                            # Check for directorydev handler - special button layout
                            if app == "directorydev":
                                # Create horizontal layout for main button + 4 action icons
                                btn_layout = QHBoxLayout()
                                btn_layout.setContentsMargins(0, 0, 0, 0)
                                btn_layout.setSpacing(2)
                                btn_layout.addWidget(btn, 1)

                                # Parse path for tooltips
                                parts = os.path.expanduser(path).split()
                                project_path = parts[0]
                                npm_cmd = parts[1] if len(parts) > 1 else None
                                npm_commands = ("start", "dev", "build", "test", "install", "run")
                                has_npm_cmd = npm_cmd in npm_commands

                                # Individual action buttons (icons match icon_preferences.json)
                                # Only show npm button if a recognized command is specified
                                file_manager = self.get_configured_file_manager()
                                editor = self.get_configured_editor()
                                actions = [
                                    ("🗄️", "file_manager", f"Open {project_path} in {file_manager}"),
                                    ("$_", "terminal", f"Open terminal at {project_path}"),
                                    ("💠", "editor", f"Open {project_path} in {editor}"),
                                ]
                                if has_npm_cmd:
                                    actions.append(("⚡", "npm", f"Run npm {npm_cmd}"))

                                action_btn_style = f"""
                                    QPushButton {{
                                        background-color: {self.t('bg_button')};
                                        color: {self.t('fg_primary')};
                                        border: 1px solid {self.t('border')};
                                        border-radius: 3px;
                                        font-size: 14px;
                                    }}
                                    QPushButton:hover {{
                                        background-color: {self.t('bg_button_hover')};
                                        border: 1px solid {self.t('bg_category_hover')};
                                        color: {self.t('fg_on_dark')};
                                    }}
                                """

                                for icon, action, tooltip in actions:
                                    action_btn = QPushButton(icon)
                                    action_btn.setMaximumWidth(28)
                                    action_btn.setMinimumHeight(30)
                                    action_btn.setToolTip(tooltip)
                                    action_btn.setStyleSheet(action_btn_style)
                                    action_btn.clicked.connect(
                                        lambda checked=False, p=path, a=action: self.directorydev_action(p, a)
                                    )
                                    btn_layout.addWidget(action_btn)

                                btn_container = QWidget()
                                btn_container.setLayout(btn_layout)
                                drop_zone_layout.addWidget(btn_container)
                                category_drop_zone.add_item(btn_container, idx)

                            # Check if this is a web link - add preview button
                            elif app in ("firefox", "chrome"):
                                # Create horizontal layout for button + preview icon
                                btn_layout = QHBoxLayout()
                                btn_layout.setContentsMargins(0, 0, 0, 0)
                                btn_layout.setSpacing(2)
                                btn_layout.addWidget(btn, 1)

                                # Add small preview button
                                preview_btn = QPushButton("🌐")
                                preview_btn.setMaximumWidth(28)
                                preview_btn.setMinimumHeight(30)
                                preview_btn.setToolTip("Preview in webview")
                                preview_btn.setStyleSheet(f"""
                                    QPushButton {{
                                        background-color: {self.t('bg_button')};
                                        border: 1px solid {self.t('border')};
                                        border-radius: 3px;
                                        font-size: 14px;
                                    }}
                                    QPushButton:hover {{
                                        background-color: {self.t('bg_button_hover')};
                                        border: 1px solid {self.t('bg_category_hover')};
                                        color: {self.t('fg_on_dark')};
                                    }}
                                """)
                                preview_btn.clicked.connect(
                                    lambda checked=False, url=path: self.preview_in_webview(url)
                                )
                                btn_layout.addWidget(preview_btn)

                                # Add layout to group
                                btn_container = QWidget()
                                btn_container.setLayout(btn_layout)
                                drop_zone_layout.addWidget(btn_container)
                                category_drop_zone.add_item(btn_container, idx)

                            # Check if this is an image - add preview button
                            elif app in ("gwenview", "gimp", "krita"):
                                # Create horizontal layout for button + preview icon
                                btn_layout = QHBoxLayout()
                                btn_layout.setContentsMargins(0, 0, 0, 0)
                                btn_layout.setSpacing(2)
                                btn_layout.addWidget(btn, 1)

                                # Add small preview button
                                preview_btn = QPushButton("🖼️")
                                preview_btn.setMaximumWidth(28)
                                preview_btn.setMinimumHeight(30)
                                preview_btn.setToolTip("Preview in image viewer")
                                preview_btn.setStyleSheet(f"""
                                    QPushButton {{
                                        background-color: {self.t('bg_button')};
                                        border: 1px solid {self.t('border')};
                                        border-radius: 3px;
                                        font-size: 14px;
                                    }}
                                    QPushButton:hover {{
                                        background-color: {self.t('bg_button_hover')};
                                        border: 1px solid {self.t('bg_category_hover')};
                                        color: {self.t('fg_on_dark')};
                                    }}
                                """)
                                preview_btn.clicked.connect(
                                    lambda checked=False, img_path=path: self.preview_in_image_viewer(img_path)
                                )
                                btn_layout.addWidget(preview_btn)

                                # Add layout to group
                                btn_container = QWidget()
                                btn_container.setLayout(btn_layout)
                                drop_zone_layout.addWidget(btn_container)
                                category_drop_zone.add_item(btn_container, idx)

                            # Check if this is a folder/terminal item - add terminal button
                            elif app in ("dolphin", "file_manager", "terminal", "tail_log"):
                                # Create horizontal layout for button + terminal icon
                                btn_layout = QHBoxLayout()
                                btn_layout.setContentsMargins(0, 0, 0, 0)
                                btn_layout.setSpacing(2)
                                btn_layout.addWidget(btn, 1)

                                # Terminal preview button style
                                terminal_btn_style = f"""
                                    QPushButton {{
                                        background-color: {self.t('bg_button')};
                                        color: {self.t('fg_primary')};
                                        border: 1px solid {self.t('border')};
                                        border-radius: 3px;
                                        font-size: 14px;
                                    }}
                                    QPushButton:hover {{
                                        background-color: {self.t('bg_navy')};
                                        color: {self.t('fg_on_dark')};
                                        border: 1px solid {self.t('bg_navy_hover')};
                                    }}
                                """

                                # Add terminal button
                                term_btn = QPushButton("$_")
                                term_btn.setMaximumWidth(28)
                                term_btn.setMinimumHeight(30)
                                term_btn.setToolTip("Open terminal here")
                                term_btn.setStyleSheet(terminal_btn_style)
                                term_btn.clicked.connect(
                                    lambda checked=False, p=path: self.open_terminal_at(p)
                                )
                                btn_layout.addWidget(term_btn)

                                # Add layout to group
                                btn_container = QWidget()
                                btn_container.setLayout(btn_layout)
                                drop_zone_layout.addWidget(btn_container)
                                category_drop_zone.add_item(btn_container, idx)
                            else:
                                drop_zone_layout.addWidget(btn)
                                category_drop_zone.add_item(btn, idx)

                    # Add the drop zone to group layout (in view mode)
                    if not self.edit_mode and category_drop_zone:
                        group_layout.addWidget(category_drop_zone)

                    # Add "Add Launcher" button in edit mode
                    if self.edit_mode:
                        add_entry_btn = QPushButton("➕ Add Launcher")
                        add_entry_btn.setStyleSheet(f"""
                            QPushButton {{
                                background-color: {self.t('bg_success')};
                                color: {self.t('fg_on_dark')};
                                border: 1px solid {self.t('bg_success_hover')};
                                border-radius: 3px;
                                padding: 5px;
                                font-size: 10px;
                            }}
                            QPushButton:hover {{
                                background-color: {self.t('bg_success_hover')};
                                color: {self.t('fg_on_dark')};
                            }}
                        """)
                        add_entry_btn.clicked.connect(
                            lambda checked=False, c_idx=col_idx, c_name=category_name: self.add_new_entry(c_idx, c_name)
                        )
                        group_layout.addWidget(add_entry_btn)

                    group_box.setLayout(group_layout)
                    group_container_layout.addWidget(group_box)

                    column_layout.addWidget(group_container)

            # Add Tagged Files category at the bottom of Column 1
            if col_idx == 0:
                tagged_files = self.get_tagged_files()
                if tagged_files:
                    # Create container for tagged files category
                    tagged_container = QWidget()
                    tagged_container_layout = QVBoxLayout(tagged_container)
                    tagged_container_layout.setSpacing(0)
                    tagged_container_layout.setContentsMargins(0, 0, 0, 0)

                    # Category header
                    tagged_header = QPushButton("🏷️ Tagged Files")
                    tagged_header.setMinimumHeight(30)
                    tagged_header.setStyleSheet(f"""
                        QPushButton {{
                            text-align: left;
                            padding-left: 10px;
                            background-color: {self.t('bg_purple')};
                            color: {self.t('fg_on_dark')};
                            border: 2px solid {self.t('bg_purple')};
                            border-radius: 5px;
                            font-weight: bold;
                            font-size: 12px;
                        }}
                        QPushButton:hover {{
                            background-color: {self.t('bg_category_hover')};
                            border: 2px solid {self.t('border_dark')};
                            color: {self.t('fg_on_dark')};
                        }}
                    """)
                    tagged_header.setToolTip(f"Files tagged with '{self.get_tag_name_for_config()}' in Dolphin")
                    tagged_container_layout.addWidget(tagged_header)

                    # Create group box for tagged files
                    tagged_group = QGroupBox()
                    tagged_group.setStyleSheet(f"""
                        QGroupBox {{
                            font-weight: bold;
                            border: 1px solid {self.t('border')};
                            border-top: none;
                            border-top-left-radius: 0px;
                            border-top-right-radius: 0px;
                            border-bottom-left-radius: 5px;
                            border-bottom-right-radius: 5px;
                            padding-top: 10px;
                            background-color: {self.t('bg_purple_light')};
                            margin-top: 0px;
                        }}
                    """)

                    tagged_group_layout = QVBoxLayout()
                    tagged_group_layout.setSpacing(3)

                    for filepath in tagged_files:
                        # Get filename for display
                        filename = os.path.basename(filepath)

                        file_btn = QPushButton(f"🔖 {filename}")
                        file_btn.setMinimumHeight(30)
                        file_btn.setStyleSheet(f"""
                            QPushButton {{
                                text-align: left;
                                padding-left: 10px;
                                background-color: {self.t('bg_button')};
                                color: {self.t('fg_primary')};
                                border: 1px solid {self.t('border')};
                                border-radius: 3px;
                            }}
                            QPushButton:hover {{
                                background-color: {self.t('bg_purple')};
                                color: {self.t('fg_on_dark')};
                                border: 1px solid {self.t('bg_purple')};
                            }}
                        """)
                        file_btn.setToolTip(f"{filepath}\n(Tagged in Dolphin - remove tag there to unlink)")
                        file_btn.clicked.connect(
                            lambda checked=False, p=filepath: subprocess.Popen(["xdg-open", p], start_new_session=True)
                        )
                        tagged_group_layout.addWidget(file_btn)

                    tagged_group.setLayout(tagged_group_layout)
                    tagged_container_layout.addWidget(tagged_group)
                    column_layout.addWidget(tagged_container)

            # Add "Add Category" button in edit mode
            if self.edit_mode:
                add_category_btn = QPushButton("➕ Add Category")
                add_category_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {self.t('bg_category')};
                        color: {self.t('fg_on_dark')};
                        border: 1px solid {self.t('bg_category_hover')};
                        border-radius: 3px;
                        padding: 8px;
                        font-size: 11px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: {self.t('bg_category_hover')};
                        color: {self.t('fg_on_dark')};
                    }}
                """)
                add_category_btn.clicked.connect(
                    lambda checked=False, c_idx=col_idx: self.add_new_category(c_idx)
                )
                column_layout.addWidget(add_category_btn)

                # Add Save button at bottom in edit mode
                save_btn = QPushButton("💾 Save")
                save_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {self.t('bg_success')};
                        color: {self.t('fg_on_dark')};
                        border: 1px solid {self.t('bg_success_hover')};
                        border-radius: 3px;
                        padding: 8px;
                        font-size: 11px;
                        font-weight: bold;
                        margin-top: 10px;
                    }}
                    QPushButton:hover {{
                        background-color: {self.t('bg_success_hover')};
                        color: {self.t('fg_on_dark')};
                    }}
                """)
                save_btn.setToolTip("Save and exit edit mode")
                save_btn.clicked.connect(self.toggle_edit_mode)
                column_layout.addWidget(save_btn)

            # Add stretch at bottom of column
            column_layout.addStretch()

            # Add this column to the horizontal layout with stretch factor
            columns_layout.addLayout(column_layout, 1)

            # After launcher column, add the viewer panel (always shown)
            if col_idx == 0:
                self.column2_layout = QVBoxLayout()
                self.column2_layout.setContentsMargins(0, 4, 0, 0)  # Match column 1 top margin

                # Add header with toggle button
                header_layout = QHBoxLayout()
                header_layout.setContentsMargins(0, 0, 0, 0)
                header_layout.setSpacing(3)  # Match column 1 header spacing

                # Mode toggle button (on the left) - shows current mode, tooltip shows next
                current_mode_text = {"pdf": "PDF", "webview": "Web", "image": "Image", "help": "Help", "console": "Console"}
                next_mode_text = {"pdf": "Web", "webview": "Image", "image": "Help", "help": "Console", "console": "PDF"}
                self.column2_toggle_btn = QPushButton(current_mode_text.get(self.column2_mode, "PDF"))
                self.column2_toggle_btn.setMaximumWidth(70)
                self.column2_toggle_btn.setMinimumHeight(self.d('header_btn_height'))
                self.column2_toggle_btn.setToolTip(f"Click for {next_mode_text.get(self.column2_mode, 'Web')} viewer")
                self.column2_toggle_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {self.t('bg_green_1')};
                        color: {self.t('fg_on_dark')};
                        font-weight: bold;
                        border-radius: 3px;
                        padding: 5px;
                    }}
                    QPushButton:hover {{
                        background-color: {self.t('bg_green_2')};
                        color: {self.t('fg_on_dark')};
                    }}
                """)
                self.column2_toggle_btn.clicked.connect(self.toggle_column2_mode)
                header_layout.addWidget(self.column2_toggle_btn)

                # Header label (on the right)
                header_text = {"pdf": "PDF Viewer", "webview": "Web View", "image": "Image Viewer", "help": "Help", "console": "Console"}
                self.column2_header = QLabel(header_text.get(self.column2_mode, "PDF Viewer"))
                self.column2_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.column2_header.setMinimumHeight(self.d('header_label_height'))
                self.column2_header.setStyleSheet(f"""
                    font-weight: bold;
                    font-size: 14px;
                    margin: 0px;
                    padding: {self.d('header_label_padding')}px;
                    background-color: {self.t('bg_panel')};
                    color: {self.t('fg_on_dark')};
                    border-radius: 3px;
                """)
                header_layout.addWidget(self.column2_header, 1)

                self.column2_layout.addLayout(header_layout)

                # Create stacked widget for PDF and webview
                self.column2_stack = QWidget()
                self.column2_stack_layout = QVBoxLayout(self.column2_stack)
                self.column2_stack_layout.setContentsMargins(0, 0, 0, 0)

                # PDF viewer container
                self.pdf_container = QWidget()
                pdf_container_layout = QVBoxLayout(self.pdf_container)
                pdf_container_layout.setContentsMargins(0, 0, 0, 0)

                # Create PDF toolbar
                self.create_pdf_toolbar(pdf_container_layout)

                # Create PDF scroll area
                self.pdf_scroll = QScrollArea()
                self.pdf_scroll.setWidgetResizable(True)
                self.pdf_scroll.setStyleSheet(f"""
                    QScrollArea {{
                        background-color: {self.t('bg_viewer')};
                        border: 2px solid {self.t('border')};
                        border-radius: 5px;
                    }}
                """)

                # Create label for PDF display
                self.pdf_label = QLabel()
                self.pdf_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                self.pdf_label.setStyleSheet(f"background-color: {self.t('bg_viewer')}; padding-top: 15px;")
                self.pdf_scroll.setWidget(self.pdf_label)

                pdf_container_layout.addWidget(self.pdf_scroll)

                # Webview container
                self.webview_container = QWidget()
                webview_container_layout = QVBoxLayout(self.webview_container)
                webview_container_layout.setContentsMargins(0, 0, 0, 0)

                # Create webview toolbar
                self.create_webview_toolbar(webview_container_layout)

                # Create webview
                self.webview = QWebEngineView()
                self.webview.urlChanged.connect(self.on_webview_url_changed)
                # Enable dark mode for web content if using dark theme
                # ForceDarkMode requires Qt 6.3+, so wrap in try/except
                if self.current_theme == "dark":
                    try:
                        self.webview.settings().setAttribute(
                            QWebEngineSettings.WebAttribute.ForceDarkMode, True
                        )
                    except AttributeError:
                        pass  # ForceDarkMode not available in this Qt version
                webview_container_layout.addWidget(self.webview, 1)  # stretch to fill space

                # Image viewer container
                self.image_container = QWidget()
                image_container_layout = QVBoxLayout(self.image_container)
                image_container_layout.setContentsMargins(0, 0, 0, 0)

                # Create image toolbar
                self.create_image_toolbar(image_container_layout)

                # Create image scroll area
                self.image_scroll = QScrollArea()
                self.image_scroll.setWidgetResizable(True)
                self.image_scroll.setStyleSheet(f"""
                    QScrollArea {{
                        background-color: {self.t('bg_viewer')};
                        border: 2px solid {self.t('border')};
                        border-radius: 5px;
                    }}
                """)

                # Create label for image display
                self.image_label = QLabel()
                self.image_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                self.image_label.setStyleSheet(f"background-color: {self.t('bg_viewer')}; padding-top: 15px;")
                self.image_scroll.setWidget(self.image_label)

                image_container_layout.addWidget(self.image_scroll)

                # Help viewer container
                self.help_container = QWidget()
                help_container_layout = QVBoxLayout(self.help_container)
                help_container_layout.setContentsMargins(0, 0, 0, 0)

                # Create help toolbar
                self.create_help_toolbar(help_container_layout)

                # Create QTextBrowser for help content
                self.help_browser = QTextBrowser()
                self.help_browser.setOpenExternalLinks(True)
                self.help_browser.setStyleSheet(f"""
                    QTextBrowser {{
                        background-color: {self.t('bg_help')};
                        border: 2px solid {self.t('border')};
                        border-radius: 5px;
                        padding: 10px;
                        color: {self.t('fg_primary')};
                    }}
                """)
                help_container_layout.addWidget(self.help_browser)

                # Examples viewer container
                self.examples_container = QWidget()
                examples_container_layout = QVBoxLayout(self.examples_container)
                examples_container_layout.setContentsMargins(0, 0, 0, 0)

                # Create examples toolbar
                self.create_examples_toolbar(examples_container_layout)

                # Create QWebEngineView for examples content (full CSS support)
                self.examples_browser = QWebEngineView()
                self.examples_browser.setStyleSheet(f"""
                    QWebEngineView {{
                        border: 2px solid {self.t('border')};
                        border-radius: 5px;
                    }}
                """)
                examples_container_layout.addWidget(self.examples_browser, 1)  # stretch factor

                # Console container (qtconsole if available)
                self.console_container = QWidget()
                console_container_layout = QVBoxLayout(self.console_container)
                console_container_layout.setContentsMargins(0, 0, 0, 0)
                self.console_available = False

                # Create console toolbar
                self.create_console_toolbar(console_container_layout)

                try:
                    from qtconsole.rich_jupyter_widget import RichJupyterWidget
                    from qtconsole.inprocess import QtInProcessKernelManager

                    # Create kernel manager
                    self.kernel_manager = QtInProcessKernelManager()
                    self.kernel_manager.start_kernel()
                    self.kernel_client = self.kernel_manager.client()
                    self.kernel_client.start_channels()

                    # Create console widget with dark theme
                    self.console_widget = RichJupyterWidget()
                    self.console_widget.kernel_manager = self.kernel_manager
                    self.console_widget.kernel_client = self.kernel_client
                    # Set dark color scheme
                    self.console_widget.syntax_style = 'monokai'
                    self.console_widget.set_default_style('linux')
                    self.console_widget.style_sheet = """
                        .in-prompt { color: #6aaf50; }
                        .in-prompt-number { color: #6aaf50; font-weight: bold; }
                        .out-prompt { color: #bf5656; }
                        .out-prompt-number { color: #bf5656; font-weight: bold; }
                    """
                    # Set LS_COLORS for better directory colors in shell commands
                    self.console_widget.execute('%colors Linux', hidden=True)
                    self.console_widget.execute(
                        'import os; os.environ["LS_COLORS"] = "di=1;38;2;61;174;233"',  # #3DAEE9
                        hidden=True
                    )
                    # Navigate to default console path if set
                    if hasattr(self, 'console_path') and self.console_path:
                        expanded = os.path.expanduser(self.console_path)
                        self.console_widget.execute(f'import os; os.chdir("{expanded}")', hidden=True)
                        self.console_path_label.setText(expanded)
                    self.console_widget.setStyleSheet("""
                        QPlainTextEdit, QTextEdit {
                            background-color: #1e1e1e;
                            color: #d4d4d4;
                            selection-background-color: #264f78;
                            font-family: monospace;
                            font-size: 11pt;
                        }
                        QWidget {
                            background-color: #1e1e1e;
                            border: 2px solid #3c3c3c;
                            border-radius: 5px;
                        }
                    """)
                    console_container_layout.addWidget(self.console_widget)
                    self.console_available = True
                except ImportError:
                    # qtconsole not available - show message
                    console_label = QLabel("Console not available.\n\nInstall qtconsole:\npip install qtconsole ipykernel")
                    console_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    console_label.setStyleSheet("""
                        QLabel {
                            background-color: #2d2d2d;
                            color: #888;
                            font-size: 14px;
                            padding: 20px;
                            border: 2px solid #3c3c3c;
                            border-radius: 5px;
                        }
                    """)
                    console_container_layout.addWidget(console_label)

                # Add all containers to stack layout
                self.column2_stack_layout.addWidget(self.pdf_container)
                self.column2_stack_layout.addWidget(self.webview_container)
                self.column2_stack_layout.addWidget(self.image_container)
                self.column2_stack_layout.addWidget(self.help_container)
                self.column2_stack_layout.addWidget(self.examples_container)
                self.column2_stack_layout.addWidget(self.console_container)

                # Show correct container based on mode
                self.pdf_container.hide()
                self.webview_container.hide()
                self.image_container.hide()
                self.help_container.hide()
                self.examples_container.hide()
                self.console_container.hide()
                if self.column2_mode == "pdf":
                    self.pdf_container.show()
                elif self.column2_mode == "webview":
                    self.webview_container.show()
                elif self.column2_mode == "image":
                    self.image_container.show()
                elif self.column2_mode == "help":
                    self.help_container.show()
                    self.load_help_content()
                elif self.column2_mode == "examples":
                    self.examples_container.show()
                    self.load_examples_content()
                elif self.column2_mode == "console":
                    self.console_container.show()

                self.column2_layout.addWidget(self.column2_stack, 1)  # stretch factor to fill space

                # Load PDF if path is saved
                if self.pdf_path:
                    self.load_pdf(self.pdf_path)

                # Load webview URL if set
                if self.webview_url:
                    self.webview.setUrl(QUrl(self.webview_url))

                # Load image if path is saved
                if self.image_path:
                    self.load_image(self.image_path)

                columns_layout.addLayout(self.column2_layout, 1)

        # Add notepad panel (always shown)
        notepad_layout = QVBoxLayout()
        notepad_layout.setContentsMargins(0, 4, 0, 0)  # Match column 1 top margin

        # Add notepad header
        notepad_header = QLabel("Notes")
        notepad_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        notepad_header.setMinimumHeight(self.d('header_label_height'))
        notepad_header.setStyleSheet(f"""
            font-weight: bold;
            font-size: 14px;
            margin: 0px;
            padding: {self.d('header_label_padding')}px;
            background-color: {self.t('bg_panel')};
            color: {self.t('fg_on_dark')};
            border-radius: 3px;
        """)
        notepad_layout.addWidget(notepad_header)

        # Create formatting toolbar
        self.create_notepad_toolbar(notepad_layout)

        # Create notepad text area with sanitized paste
        self.notepad = CleanTextEdit()
        self.notepad.setPlaceholderText("Project notes (auto-saved)\n\nUse toolbar for formatting: Bold, Italic, Headings, Lists, Links\nUse 📝 to open in external editor, 📥 to archive")
        self.notepad.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.t('bg_input')};
                color: {self.t('fg_primary')};
                border: 2px solid {self.t('border')};
                border-radius: 5px;
                padding: 10px;
                font-family: sans-serif;
                font-size: 12pt;
                line-height: 1.4;
            }}
        """)

        # Load existing notes (supports both plain text and HTML)
        if self.notes_data and "content" in self.notes_data:
            content = self.notes_data["content"]
            if '<' in content and '>' in content:
                self.notepad.setHtml(content)
            else:
                self.notepad.setPlainText(content)

        # Auto-save on text change
        self.notepad.textChanged.connect(self.on_notepad_changed)

        # Add Ctrl+Shift+V shortcut for plain text paste
        paste_plain = QShortcut(QKeySequence("Ctrl+Shift+V"), self.notepad)
        paste_plain.activated.connect(self.paste_plain_text)

        # Add formatting shortcuts
        bold_shortcut = QShortcut(QKeySequence("Ctrl+B"), self.notepad)
        bold_shortcut.activated.connect(self.toggle_bold)
        italic_shortcut = QShortcut(QKeySequence("Ctrl+I"), self.notepad)
        italic_shortcut.activated.connect(self.toggle_italic)

        notepad_layout.addWidget(self.notepad)

        # Add archive buttons at the bottom right
        archive_bar = QHBoxLayout()
        archive_bar.setContentsMargins(0, 5, 0, 0)
        archive_bar.addStretch()

        archive_btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """

        archive_btn = QPushButton("📥 Archive")
        archive_btn.setStyleSheet(archive_btn_style)
        archive_btn.setToolTip("Archive notes (save to archive and clear)")
        archive_btn.clicked.connect(self.archive_notes)
        archive_bar.addWidget(archive_btn)

        view_archive_btn = QPushButton("📜 View")
        view_archive_btn.setToolTip("View archive")
        view_archive_btn.clicked.connect(self.view_archive)
        # Grey out if archive is empty or doesn't exist
        archive_file = self.get_archive_file_path()
        has_archive = os.path.exists(archive_file) and os.path.getsize(archive_file) > 0
        if has_archive:
            view_archive_btn.setStyleSheet(archive_btn_style)
        else:
            view_archive_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.t('bg_button')};
                    color: {self.t('border')};
                    border: 1px solid {self.t('bg_secondary')};
                    border-radius: 3px;
                    padding: 4px 8px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {self.t('bg_button_hover')};
                    color: {self.t('fg_on_dark')};
                }}
            """)
        archive_bar.addWidget(view_archive_btn)

        notepad_layout.addLayout(archive_bar)

        # Notepad gets stretch factor of 1 (so with 2 columns above, it's 33% width)
        columns_layout.addLayout(notepad_layout, 1)

        parent_layout.addLayout(columns_layout)

        # Add spacer before Projects section
        spacer = QWidget()
        spacer.setFixedHeight(20)
        parent_layout.addWidget(spacer)

        # Create unified projects section
        self.create_projects_section(parent_layout)

        # Add separator line before footer
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(f"background-color: {self.t('border')}; margin-top: 15px;")
        separator.setFixedHeight(1)
        parent_layout.addWidget(separator)

        # Footer section
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 10, 0, 5)

        # Footer text (left side) with version
        version = self.get_version()
        footer_text = QLabel(f"ProjectFlow  •  Open source project launcher  •  {version}")
        footer_text.setStyleSheet(f"color: {self.t('fg_muted')}; font-size: 11px;")
        footer_layout.addWidget(footer_text)

        footer_layout.addStretch()

        # Footer button style
        footer_btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """

        # New Project button
        new_project_btn = QPushButton("📄 New Project")
        new_project_btn.setMinimumHeight(30)
        new_project_btn.setStyleSheet(footer_btn_style)
        new_project_btn.setToolTip("Create a new project from template")
        new_project_btn.clicked.connect(self.new_project)
        footer_layout.addWidget(new_project_btn)

        # Theme toggle button (icon only, before Settings)
        theme_icon = "🌙" if self.current_theme == "light" else "☀️"
        theme_btn = QPushButton(theme_icon)
        theme_btn.setMinimumHeight(30)
        theme_btn.setFixedWidth(40)
        theme_btn.setStyleSheet(footer_btn_style)
        theme_btn.clicked.connect(self.toggle_theme)
        theme_btn.setToolTip(f"Switch to {'dark' if self.current_theme == 'light' else 'light'} mode")
        footer_layout.addWidget(theme_btn)

        # Settings button
        settings_btn = QPushButton("⚙️ Settings")
        settings_btn.setMinimumHeight(30)
        settings_btn.setStyleSheet(footer_btn_style)
        settings_btn.clicked.connect(self.show_settings_dialog)
        settings_btn.setToolTip("Open application settings")
        footer_layout.addWidget(settings_btn)

        parent_layout.addLayout(footer_layout)

    def open_config_in_new_window(self, config_path):
        """Launch a new instance of ProjectFlow with the specified config"""
        script_path = os.path.join(self.script_dir, "projectflow.py")
        subprocess.Popen([script_path, config_path], start_new_session=True)

    def edit_config(self):
        """Open the current config file in Kate for editing"""
        if os.path.exists(self.current_config_file):
            self.open_in_app(self.current_config_file, "kate")
        else:
            self.status_label.setText("✗ Config file not found!")
            self.status_label.setStyleSheet("color: #e74c3c; margin: 10px; font-weight: bold;")

    def set_as_default_project(self):
        """Set the current config as the default for this computer"""
        # Get relative path if file is in configs directory
        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))

        if self.current_config_file.startswith(configs_dir):
            # Store relative path from configs directory
            relative_path = os.path.relpath(self.current_config_file, self.script_dir)
            self.settings["default_project"] = os.path.basename(self.current_config_file)
        else:
            # Store absolute path
            self.settings["default_project"] = self.current_config_file

        self.save_settings()

        config_name = os.path.basename(self.current_config_file)
        QMessageBox.information(
            self,
            "Default Config Set",
            f"'{config_name}' is now the default config for this computer.\n\n"
            f"This app will automatically load this config when started."
        )

        self.status_label.setText(f"✓ Set '{config_name}' as default")
        self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")

    def new_project(self):
        """Create a new project from the template"""
        from PyQt6.QtWidgets import QInputDialog

        # Prompt user for new project name
        new_name, ok = QInputDialog.getText(
            self,
            "New Project",
            "Enter name for the new project:",
            text="my_project"
        )

        if not ok or not new_name.strip():
            return

        new_name = new_name.strip()

        # Ensure it has .json extension
        if not new_name.endswith('.json'):
            new_name += '.json'

        # Determine destination path (in configs directory)
        configs_dir = self.settings.get("projects_directory", "projects")
        if not os.path.isabs(configs_dir):
            configs_dir = os.path.join(self.script_dir, configs_dir)
        new_config_path = os.path.join(configs_dir, new_name)

        # Check if file already exists
        if os.path.exists(new_config_path):
            QMessageBox.warning(
                self,
                "File Exists",
                f"A project named '{new_name}' already exists.\nPlease choose a different name."
            )
            return

        try:
            # Copy from template in examples folder
            template_path = os.path.join(self.script_dir, "examples", "projectflow.json")
            if os.path.exists(template_path):
                shutil.copy2(template_path, new_config_path)
            else:
                # Fallback: create a minimal config
                self.create_default_project(new_config_path)

            self.status_label.setText(f"✓ Created '{new_name}'")
            self.status_label.setStyleSheet("color: #17a2b8; margin: 10px; font-weight: bold;")

            # Ask if user wants to switch to the new project
            reply = QMessageBox.question(
                self,
                "Project Created",
                f"Created '{new_name}'.\n\nSwitch to the new project now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.switch_to_config(new_config_path)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create project:\n{str(e)}"
            )

    def open_all_in_group(self, items):
        """Open all items in a group"""
        import time
        opened_count = 0

        for item in items:
            # Handle both 2-tuple and 3-tuple formats
            if len(item) == 2:
                display_name, path = item
                app = "kate"
            else:
                display_name, path, app = item

            try:
                self.open_in_app(path, app)
                opened_count += 1
                # Small delay between opening items to avoid overwhelming the system
                time.sleep(0.3)
            except Exception as e:
                print(f"Error opening {display_name}: {e}")

        self.status_label.setText(f"✓ Opened {opened_count} items from group")
        self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")

    def choose_and_open(self):
        """Let user choose a folder/file and open it in Kate (default)"""
        # Try to get a file first
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File to Open",
            "",
            "All Files (*)"
        )

        if file_path:
            self.open_in_app(file_path, "kate")
        else:
            # If no file selected, try folder
            folder_path = QFileDialog.getExistingDirectory(
                self,
                "Select Folder to Open",
                "",
                QFileDialog.Option.ShowDirsOnly
            )

            if folder_path:
                self.open_in_app(folder_path, "kate")

    def load_different_config(self):
        """Let user select a different config file and load it"""
        # Get the configs directory
        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))

        # Start in configs directory if it exists, otherwise current config dir
        start_dir = configs_dir if os.path.exists(configs_dir) else os.path.dirname(self.current_config_file)

        # Open file picker for config files
        config_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Project",
            start_dir,
            "Project Files (*.json);;All Files (*)"
        )

        if config_path:
            self.switch_to_config(config_path)

    def switch_to_config(self, config_path):
        """Switch to a different config file"""
        # Update the current config file path
        self.current_config_file = config_path

        # Save as last used project
        self.settings["last_used_project"] = config_path

        # Add to recent projects
        self.add_to_recent_projects(config_path)

        # Reload with the new project
        self.refresh_projects()

    def on_notepad_changed(self):
        """Handle notepad text changes - auto-save to markdown file"""
        if hasattr(self, 'notepad'):
            notes_html = self.notepad.toHtml()
            self.save_notes(notes_html)

    def html_to_markdown(self, html):
        """Convert HTML to markdown"""
        import html as html_module

        # Remove DOCTYPE and html/body wrappers
        text = re.sub(r'<!DOCTYPE[^>]*>', '', html)
        text = re.sub(r'</?html[^>]*>', '', text)
        text = re.sub(r'</?head[^>]*>.*?</head>', '', text, flags=re.DOTALL)
        text = re.sub(r'</?body[^>]*>', '', text)
        text = re.sub(r'</?meta[^>]*>', '', text)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)

        # Convert headings
        for level in range(1, 7):
            text = re.sub(rf'<h{level}[^>]*>(.*?)</h{level}>', rf'{"#" * level} \1\n', text, flags=re.DOTALL)

        # Convert bold/strong (HTML tags)
        text = re.sub(r'<(?:b|strong)[^>]*>(.*?)</(?:b|strong)>', r'**\1**', text, flags=re.DOTALL)

        # Convert bold (QTextEdit inline style: font-weight:700 or font-weight:bold)
        text = re.sub(r'<span[^>]*font-weight:\s*(?:700|bold)[^>]*>(.*?)</span>', r'**\1**', text, flags=re.DOTALL)

        # Convert emphasis BEFORE italic (QTextEdit converts <em> to <span> with background-color:#9c0c15)
        # Must come before italic since emphasis spans also have font-style:italic
        text = re.sub(r'<span[^>]*background-color:\s*#9c0c15[^>]*>(.*?)</span>', r'==\1==', text, flags=re.DOTALL)
        text = re.sub(r'<em[^>]*background-color[^>]*>(.*?)</em>', r'==\1==', text, flags=re.DOTALL)

        # Convert code BEFORE removing other spans (QTextEdit converts <code> to <span> with font-family:monospace)
        text = re.sub(r'<span[^>]*font-family:\s*[\'"]?monospace[\'"]?[^>]*>(.*?)</span>', r'`\1`', text, flags=re.DOTALL)
        text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.DOTALL)

        # Convert italic/em (HTML tags) - but not emphasis with background-color
        text = re.sub(r'<(?:i|em)(?![^>]*background-color)[^>]*>(.*?)</(?:i|em)>', r'*\1*', text, flags=re.DOTALL)

        # Convert italic (QTextEdit inline style: font-style:italic) - but not if already processed as emphasis
        text = re.sub(r'<span[^>]*font-style:\s*italic[^>]*>(.*?)</span>', r'*\1*', text, flags=re.DOTALL)

        # Convert links
        text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', text, flags=re.DOTALL)

        # Convert list items (basic handling)
        text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', text, flags=re.DOTALL)
        text = re.sub(r'</?[uo]l[^>]*>', '', text)

        # Convert paragraphs and line breaks
        text = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', text, flags=re.DOTALL)
        text = re.sub(r'<br\s*/?>', '\n', text)

        # Remove remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode HTML entities
        text = html_module.unescape(text)

        # Clean up extra whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        return text

    def sync_to_joplin(self):
        """Sync current notes to Joplin via web clipper API"""
        token = self.settings.get("joplin_token")
        if not token:
            QMessageBox.warning(self, "Joplin Sync", "No Joplin token configured in settings.")
            return

        if not hasattr(self, 'notepad'):
            QMessageBox.warning(self, "Joplin Sync", "No notepad available to sync.")
            return

        # Get config name for note title
        config_name = os.path.basename(self.current_config_file)
        config_name = os.path.splitext(config_name)[0]
        if config_name.endswith('_config'):
            config_name = config_name[:-7]
        title = f"ProjectFlow: {config_name.replace('_', ' ').title()}"

        # Convert HTML to markdown
        html_content = self.notepad.toHtml()
        markdown_content = self.html_to_markdown(html_content)

        if not markdown_content.strip():
            QMessageBox.information(self, "Joplin Sync", "Notes are empty, nothing to sync.")
            return

        # Prepare the request
        url = f"http://127.0.0.1:41184/notes?token={token}"
        data = json.dumps({"title": title, "body": markdown_content}).encode('utf-8')

        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    QMessageBox.information(self, "Joplin Sync", f"Notes synced to Joplin as:\n\"{title}\"")
                else:
                    QMessageBox.warning(self, "Joplin Sync", f"Unexpected response: {response.status}")
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Joplin Sync", f"Could not connect to Joplin.\nIs it running?\n\nError: {e.reason}")
        except Exception as e:
            QMessageBox.warning(self, "Joplin Sync", f"Sync failed: {e}")

    def open_note_in_external_editor(self):
        """Open the current note's markdown file in an external editor"""
        editor = self.settings.get("open_note_external")
        if not editor:
            QMessageBox.warning(self, "External Editor", "No external editor configured.\nSet 'open_note_external' in settings.")
            return

        notes_file = self.get_notes_file_path()
        if not os.path.exists(notes_file):
            # Create empty file if it doesn't exist
            folder = self.get_notes_folder()
            os.makedirs(folder, exist_ok=True)
            with open(notes_file, 'w', encoding='utf-8') as f:
                f.write("")

        try:
            subprocess.Popen([editor, notes_file], start_new_session=True)
            self.status_label.setText(f"✓ Opened in {editor}")
            self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
        except FileNotFoundError:
            QMessageBox.warning(self, "External Editor", f"Editor not found: {editor}")
        except Exception as e:
            QMessageBox.warning(self, "External Editor", f"Failed to open: {e}")

    def toggle_edit_mode(self):
        """Toggle between view mode and edit mode"""
        self.edit_mode = not self.edit_mode

        # Refresh the UI to show/hide edit controls
        self.refresh_projects()

    def create_edit_item_widget(self, col_idx, category_name, item_idx, name, path, app):
        """Create an editable widget for an item in edit mode"""
        item_widget = QWidget()
        main_layout = QVBoxLayout(item_widget)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(3)

        # Shared style for edit fields
        edit_style = f"""
            QLineEdit, QPlainTextEdit {{
                background-color: {self.t('bg_input')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 4px;
            }}
            QLineEdit:focus, QPlainTextEdit:focus {{
                border: 1px solid {self.t('bg_category')};
            }}
        """

        # Button style for edit controls
        edit_btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """

        # Row 1: Name, App, Edit button, Up/Down/Delete buttons
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(5)

        # Name field
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("Name")
        name_edit.setMinimumWidth(120)
        name_edit.setMaximumWidth(200)
        name_edit.setStyleSheet(edit_style)
        row1_layout.addWidget(name_edit)

        # App field
        app_edit = QLineEdit(app)
        app_edit.setPlaceholderText("App")
        app_edit.setMinimumWidth(80)
        app_edit.setMaximumWidth(120)
        app_edit.setStyleSheet(edit_style)
        row1_layout.addWidget(app_edit)

        # Edit button (opens advanced dialog) - right next to app field
        edit_btn = QPushButton("✏️")
        edit_btn.setFixedSize(30, 26)
        edit_btn.setToolTip("Open edit dialog")
        edit_btn.setStyleSheet(edit_btn_style)
        row1_layout.addWidget(edit_btn)

        row1_layout.addStretch()

        # Up button
        up_btn = QPushButton("↑")
        up_btn.setFixedSize(30, 26)
        up_btn.setToolTip("Move up")
        up_btn.setStyleSheet(edit_btn_style)
        up_btn.clicked.connect(
            lambda: self.move_item_up(col_idx, category_name, item_idx)
        )
        row1_layout.addWidget(up_btn)

        # Down button
        down_btn = QPushButton("↓")
        down_btn.setFixedSize(30, 26)
        down_btn.setToolTip("Move down")
        down_btn.setStyleSheet(edit_btn_style)
        down_btn.clicked.connect(
            lambda: self.move_item_down(col_idx, category_name, item_idx)
        )
        row1_layout.addWidget(down_btn)

        # Delete button
        del_btn = QPushButton("🗑")
        del_btn.setFixedSize(30, 26)
        del_btn.setToolTip("Delete item")
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('bg_danger')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_danger')};
                color: {self.t('fg_on_dark')};
            }}
        """)
        del_btn.clicked.connect(
            lambda: self.delete_item(col_idx, category_name, item_idx)
        )
        row1_layout.addWidget(del_btn)

        main_layout.addLayout(row1_layout)

        # Row 2: Path label and multi-line path field
        row2_layout = QVBoxLayout()
        row2_layout.setSpacing(2)

        path_label = QLabel("Path(s)/Folders:")
        path_label.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 11px;")
        row2_layout.addWidget(path_label)

        path_edit = QPlainTextEdit(path)
        path_edit.setPlaceholderText("File path, folder path, or URL (one per line for multiple)")
        path_edit.setStyleSheet(edit_style)
        path_edit.setMaximumHeight(60)
        row2_layout.addWidget(path_edit)

        main_layout.addLayout(row2_layout)

        # Store references to the edit fields for saving later
        item_widget.name_edit = name_edit
        item_widget.path_edit = path_edit
        item_widget.app_edit = app_edit
        item_widget.col_idx = col_idx
        item_widget.category_name = category_name
        item_widget.item_idx = item_idx

        # Connect edit button to open dialog
        edit_btn.clicked.connect(
            lambda: self._open_edit_dialog_from_inline(item_widget)
        )

        # Connect change handlers to auto-save
        name_edit.textChanged.connect(lambda: self.save_item_changes(item_widget))
        path_edit.textChanged.connect(lambda: self.save_item_changes(item_widget))
        app_edit.textChanged.connect(lambda: self.save_item_changes(item_widget))

        return item_widget

    def _open_edit_dialog_from_inline(self, item_widget):
        """Open the edit dialog from inline edit widget"""
        item_data = {
            "name": item_widget.name_edit.text(),
            "path": item_widget.path_edit.toPlainText(),
            "app": item_widget.app_edit.text(),
            "index": item_widget.item_idx
        }
        self._show_item_edit_dialog(
            item_widget.col_idx,
            item_widget.category_name,
            item_data,
            tree=None,
            inline_widget=item_widget
        )

    def save_item_changes(self, item_widget):
        """Save changes from an edit widget back to the config data"""
        col_idx = item_widget.col_idx
        category_name = item_widget.category_name
        item_idx = item_widget.item_idx

        # Get the new values
        new_name = item_widget.name_edit.text()
        new_path = item_widget.path_edit.toPlainText()
        new_app = item_widget.app_edit.text()

        # Update the in-memory config
        column = self.COLUMN_1
        for category_dict in column:
            if category_name in category_dict:
                items = category_dict[category_name]
                if item_idx < len(items):
                    items[item_idx] = [new_name, new_path, new_app]
                break

        # Auto-save to JSON file
        self.save_config_to_json()

    def move_item_up(self, col_idx, category_name, item_idx):
        """Move an item up in the list"""
        if item_idx == 0:
            return  # Already at top

        # Save scroll position
        scroll_pos = self.main_scroll.verticalScrollBar().value() if hasattr(self, 'main_scroll') else None

        column = self.COLUMN_1
        for category_dict in column:
            if category_name in category_dict:
                items = category_dict[category_name]
                # Swap with previous item
                items[item_idx], items[item_idx - 1] = items[item_idx - 1], items[item_idx]
                break

        self.save_config_to_json()
        self.refresh_projects(restore_scroll_pos=scroll_pos)

    def move_item_down(self, col_idx, category_name, item_idx):
        """Move an item down in the list"""
        # Save scroll position
        scroll_pos = self.main_scroll.verticalScrollBar().value() if hasattr(self, 'main_scroll') else None

        column = self.COLUMN_1
        for category_dict in column:
            if category_name in category_dict:
                items = category_dict[category_name]
                if item_idx >= len(items) - 1:
                    return  # Already at bottom
                # Swap with next item
                items[item_idx], items[item_idx + 1] = items[item_idx + 1], items[item_idx]
                break

        self.save_config_to_json()
        self.refresh_projects(restore_scroll_pos=scroll_pos)

    def delete_item(self, col_idx, category_name, item_idx):
        """Delete an item from the config"""
        # Save scroll position
        scroll_pos = self.main_scroll.verticalScrollBar().value() if hasattr(self, 'main_scroll') else None

        column = self.COLUMN_1
        for category_dict in column:
            if category_name in category_dict:
                items = category_dict[category_name]
                if item_idx < len(items):
                    del items[item_idx]
                break

        self.save_config_to_json()
        self.refresh_projects(restore_scroll_pos=scroll_pos)

    def add_new_entry(self, col_idx, category_name):
        """Add a new entry - opens dialog immediately"""
        self._show_item_edit_dialog(
            col_idx=col_idx,
            category_name=category_name,
            item_data=None
        )

    def add_new_category(self, col_idx):
        """Add a new category with a blank entry to a column"""
        # Save scroll position
        scroll_pos = self.main_scroll.verticalScrollBar().value() if hasattr(self, 'main_scroll') else None

        column = self.COLUMN_1
        # Create a new category with one blank entry
        new_category = {"New Category": [["New Launcher", "/path/to/file", "editor"]]}
        column.append(new_category)

        self.save_config_to_json()
        self.refresh_projects(restore_scroll_pos=scroll_pos)

    def rename_category_from_edit(self, col_idx, edit_widget):
        """Rename a category when editing is finished"""
        old_name = edit_widget.property("original_name")
        new_name = edit_widget.text().strip()

        if not new_name or new_name == old_name:
            return

        column = self.COLUMN_1
        for category_dict in column:
            if old_name in category_dict:
                # Rename by creating new key and deleting old
                category_dict[new_name] = category_dict.pop(old_name)
                # Update the stored original name for future edits
                edit_widget.setProperty("original_name", new_name)
                break

        self.save_config_to_json()

    def rename_category(self, col_idx, old_name, new_name):
        """Rename a category (legacy method)"""
        if not new_name or new_name == old_name:
            return

        column = self.COLUMN_1
        for category_dict in column:
            if old_name in category_dict:
                # Rename by creating new key and deleting old
                category_dict[new_name] = category_dict.pop(old_name)
                break

        self.save_config_to_json()

    def delete_category(self, col_idx, category_name):
        """Delete a category"""
        from PyQt6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Delete Category",
            f"Are you sure you want to delete the category '{category_name}' and all its entries?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            column = self.COLUMN_1
            for category_dict in column:
                if category_name in category_dict:
                    del category_dict[category_name]
                    break

            self.save_config_to_json()
            self.refresh_projects()

    def save_config_to_json(self):
        """Save the current config data to JSON file, preserving notes and other state"""
        try:
            # Read existing data to preserve notes, pdf_state, webview_state
            config_data = {}
            if os.path.exists(self.current_config_file):
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)

            # Update only the column/config data (app_info is in icon_preferences.json)
            config_data["column_headers"] = self.COLUMN_HEADERS
            config_data["columns"] = [self.COLUMN_1]

            with open(self.current_config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def paste_plain_text(self):
        """Paste clipboard content as plain text (Ctrl+Shift+V)"""
        if hasattr(self, 'notepad'):
            clipboard = QApplication.clipboard()
            self.notepad.insertPlainText(clipboard.text())

    def create_notepad_toolbar(self, parent_layout):
        """Create a formatting toolbar for the notepad"""
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 5)
        toolbar_layout.setSpacing(3)

        # Button style
        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                min-width: 24px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QPushButton:pressed {{
                background-color: {self.t('bg_category_hover')};
            }}
        """

        # Spacer style
        spacer_style = f"color: {self.t('border')}; margin: 0 3px;"

        # H1, H2 buttons
        for level in range(1, 3):
            h_btn = QPushButton(f"H{level}")
            h_btn.setStyleSheet(btn_style)
            h_btn.setToolTip(f"Heading {level}")
            h_btn.clicked.connect(lambda checked, l=level: self.apply_heading(l))
            toolbar_layout.addWidget(h_btn)

        # Bold button
        bold_btn = QPushButton("B")
        bold_btn.setStyleSheet(btn_style + "QPushButton { font-weight: bold; }")
        bold_btn.setToolTip("Bold (Ctrl+B)")
        bold_btn.clicked.connect(self.toggle_bold)
        toolbar_layout.addWidget(bold_btn)

        # Spacer
        sep1 = QLabel("|")
        sep1.setStyleSheet(spacer_style)
        toolbar_layout.addWidget(sep1)

        # Emphasis/Action button
        em_btn = QPushButton("!")
        em_btn.setStyleSheet(btn_style + "QPushButton { font-weight: bold; }")
        em_btn.setToolTip("Emphasis / Action item")
        em_btn.clicked.connect(self.toggle_emphasis)
        toolbar_layout.addWidget(em_btn)

        # Code button
        code_btn = QPushButton("</>")
        code_btn.setStyleSheet(btn_style + "QPushButton { font-family: monospace; }")
        code_btn.setToolTip("Code / Monospace")
        code_btn.clicked.connect(self.toggle_code)
        toolbar_layout.addWidget(code_btn)

        # Link button
        link_btn = QPushButton("🔗")
        link_btn.setStyleSheet(btn_style)
        link_btn.setToolTip("Insert/Edit Link")
        link_btn.clicked.connect(self.insert_link)
        toolbar_layout.addWidget(link_btn)

        # Spacer
        sep2 = QLabel("|")
        sep2.setStyleSheet(spacer_style)
        toolbar_layout.addWidget(sep2)

        # Numbered list button
        number_btn = QPushButton("1.")
        number_btn.setStyleSheet(btn_style)
        number_btn.setToolTip("Numbered List")
        number_btn.clicked.connect(self.toggle_numbered_list)
        toolbar_layout.addWidget(number_btn)

        # Bullet list button
        bullet_btn = QPushButton("•")
        bullet_btn.setStyleSheet(btn_style)
        bullet_btn.setToolTip("Bullet List")
        bullet_btn.clicked.connect(self.toggle_bullet_list)
        toolbar_layout.addWidget(bullet_btn)

        # External tools section (Joplin sync, external editor)
        has_joplin = self.settings.get("joplin_token")
        has_external_editor = self.settings.get("open_note_external")

        if has_joplin or has_external_editor:
            sep3 = QLabel("|")
            sep3.setStyleSheet(spacer_style)
            toolbar_layout.addWidget(sep3)

        # Joplin sync button (only shown if token is configured)
        if has_joplin:
            joplin_btn = QPushButton("📓")
            joplin_btn.setStyleSheet(btn_style)
            joplin_btn.setToolTip("Sync to Joplin")
            joplin_btn.clicked.connect(self.sync_to_joplin)
            toolbar_layout.addWidget(joplin_btn)

        # External editor button (only shown if open_note_external is configured)
        if has_external_editor:
            external_btn = QPushButton("📝")
            external_btn.setStyleSheet(btn_style)
            external_btn.setToolTip(f"Open in {has_external_editor}")
            external_btn.clicked.connect(self.open_note_in_external_editor)
            toolbar_layout.addWidget(external_btn)

        # Add stretch to push buttons to the left
        toolbar_layout.addStretch()

        parent_layout.addWidget(toolbar_widget)

    def create_pdf_toolbar(self, parent_layout):
        """Create a toolbar for the PDF viewer"""
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 5)
        toolbar_layout.setSpacing(4)

        # Button style
        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 4px 6px;
                font-size: 12px;
                min-width: 28px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QPushButton:pressed {{
                background-color: {self.t('bg_category_hover')};
            }}
        """

        # Open button
        open_btn = QPushButton("📤")
        open_btn.setStyleSheet(btn_style)
        open_btn.setToolTip("Open a PDF file")
        open_btn.clicked.connect(self.open_pdf_file)
        toolbar_layout.addWidget(open_btn)

        # URL button
        url_btn = QPushButton("🌍")
        url_btn.setStyleSheet(btn_style)
        url_btn.setToolTip("Load a PDF from URL")
        url_btn.clicked.connect(self.open_pdf_url)
        toolbar_layout.addWidget(url_btn)

        # Separator
        sep1 = QLabel("|")
        sep1.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep1)

        # Previous page button
        prev_btn = QPushButton("<")
        prev_btn.setStyleSheet(btn_style)
        prev_btn.setToolTip("Previous page")
        prev_btn.clicked.connect(self.pdf_prev_page)
        toolbar_layout.addWidget(prev_btn)

        # Page indicator
        self.pdf_page_label = QLabel("0 / 0")
        self.pdf_page_label.setStyleSheet("margin: 0 10px; font-size: 12px;")
        toolbar_layout.addWidget(self.pdf_page_label)

        # Next page button
        next_btn = QPushButton(">")
        next_btn.setStyleSheet(btn_style)
        next_btn.setToolTip("Next page")
        next_btn.clicked.connect(self.pdf_next_page)
        toolbar_layout.addWidget(next_btn)

        # Separator
        sep2 = QLabel("|")
        sep2.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep2)

        # Zoom out button
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setStyleSheet(btn_style)
        zoom_out_btn.setToolTip("Zoom out")
        zoom_out_btn.clicked.connect(self.pdf_zoom_out)
        toolbar_layout.addWidget(zoom_out_btn)

        # Zoom level indicator
        self.pdf_zoom_label = QLabel(f"{int(self.pdf_zoom * 100)}%")
        self.pdf_zoom_label.setStyleSheet("margin: 0 5px; font-size: 12px;")
        toolbar_layout.addWidget(self.pdf_zoom_label)

        # Zoom in button
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setStyleSheet(btn_style)
        zoom_in_btn.setToolTip("Zoom in")
        zoom_in_btn.clicked.connect(self.pdf_zoom_in)
        toolbar_layout.addWidget(zoom_in_btn)

        # Fit width button
        fit_btn = QPushButton("|—|")
        fit_btn.setStyleSheet(btn_style)
        fit_btn.setToolTip("Fit to width")
        fit_btn.clicked.connect(self.pdf_fit_width)
        toolbar_layout.addWidget(fit_btn)

        # External viewer button (only if pdfviewer setting is configured)
        if self.settings.get("pdfviewer"):
            sep3 = QLabel("|")
            sep3.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
            toolbar_layout.addWidget(sep3)

            external_btn = QPushButton("View")
            external_btn.setStyleSheet(btn_style)
            external_btn.setToolTip("Open in external PDF viewer")
            external_btn.clicked.connect(self.open_pdf_in_external_viewer)
            toolbar_layout.addWidget(external_btn)

        # Set as default button
        sep_default = QLabel("|")
        sep_default.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep_default)

        default_btn = QPushButton("📌")
        default_btn.setStyleSheet(btn_style)
        default_btn.setToolTip("Set this PDF as default for this project")
        default_btn.clicked.connect(self.set_viewer_as_default)
        toolbar_layout.addWidget(default_btn)

        # Add stretch to push buttons to the left
        toolbar_layout.addStretch()

        parent_layout.addWidget(toolbar_widget)

    def load_pdf(self, path):
        """Load a PDF file from local path or URL"""
        try:
            # Check if path is a URL
            if path.startswith(('http://', 'https://')):
                # Download PDF from URL
                req = urllib.request.Request(path, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    pdf_data = response.read()
                self.pdf_doc = fitz.open(stream=pdf_data, filetype="pdf")
            else:
                expanded_path = os.path.expanduser(path)
                if not os.path.exists(expanded_path):
                    return False
                self.pdf_doc = fitz.open(expanded_path)

            self.pdf_page_count = len(self.pdf_doc)
            self.pdf_path = path

            # Clamp current page to valid range
            if self.pdf_current_page >= self.pdf_page_count:
                self.pdf_current_page = 0

            # Render initially, then fit to width after layout is complete
            self.render_pdf_page()
            QTimer.singleShot(0, self.pdf_fit_width)

            self.save_notes()  # Save PDF state per config

            return True
        except Exception as e:
            print(f"Error loading PDF: {e}")
            return False

    def render_pdf_page(self):
        """Render the current PDF page"""
        if not self.pdf_doc or not self.pdf_label:
            return

        try:
            page = self.pdf_doc[self.pdf_current_page]
            mat = fitz.Matrix(self.pdf_zoom, self.pdf_zoom)
            pix = page.get_pixmap(matrix=mat)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)

            # Invert colors in dark mode for better readability
            if self.current_theme == "dark":
                img = img.copy()  # Make a copy since we're modifying
                img.invertPixels()

                # Blend with app background to soften the pure black
                # Create a result image with the app's background color
                bg_color = QColor(self.t('bg_viewer'))
                result = QImage(img.size(), QImage.Format.Format_RGB888)
                result.fill(bg_color)

                # Draw the inverted image with some transparency
                painter = QPainter(result)
                painter.setOpacity(0.92)  # Slight transparency to let bg show through
                painter.drawImage(0, 0, img)
                painter.end()

                img = result

            self.pdf_label.setPixmap(QPixmap.fromImage(img))

            # Update page indicator
            if hasattr(self, 'pdf_page_label'):
                self.pdf_page_label.setText(f"{self.pdf_current_page + 1} / {self.pdf_page_count}")
        except Exception as e:
            print(f"Error rendering PDF page: {e}")

    def open_pdf_file(self):
        """Open a file dialog to select a PDF"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF File",
            os.path.expanduser("~"),
            "PDF Files (*.pdf);;All Files (*)"
        )

        if file_path:
            self.pdf_current_page = 0  # Reset to first page for new file
            if self.load_pdf(file_path):
                self.status_label.setText(f"Loaded PDF: {os.path.basename(file_path)}")
                self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")

    def open_pdf_url(self):
        """Open a dialog to enter a PDF URL"""
        from PyQt6.QtWidgets import QInputDialog

        url, ok = QInputDialog.getText(
            self,
            "Load PDF from URL",
            "Enter PDF URL:",
            QLineEdit.EchoMode.Normal,
            ""
        )

        if ok and url:
            url = url.strip()
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            # Warn about HTTP (non-secure) URLs
            if url.startswith('http://'):
                reply = QMessageBox.warning(
                    self,
                    "Insecure Connection",
                    "This URL uses HTTP (not HTTPS), which means the PDF could be "
                    "intercepted or modified in transit.\n\nDo you want to continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            self.pdf_current_page = 0  # Reset to first page for new file
            self.status_label.setText("Loading PDF from URL...")
            self.status_label.setStyleSheet("color: #f39c12; margin: 10px; font-weight: bold;")
            QApplication.processEvents()  # Update UI before blocking download

            if self.load_pdf(url):
                # Extract filename from URL for display
                filename = url.split('/')[-1].split('?')[0] or "remote PDF"
                self.status_label.setText(f"Loaded: {filename}")
                self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
            else:
                self.status_label.setText("Failed to load PDF from URL")
                self.status_label.setStyleSheet("color: #e74c3c; margin: 10px; font-weight: bold;")

    def pdf_prev_page(self):
        """Go to previous page"""
        if self.pdf_doc and self.pdf_current_page > 0:
            self.pdf_current_page -= 1
            self.render_pdf_page()
            self.save_notes()  # Save page state

    def pdf_next_page(self):
        """Go to next page"""
        if self.pdf_doc and self.pdf_current_page < self.pdf_page_count - 1:
            self.pdf_current_page += 1
            self.render_pdf_page()
            self.save_notes()  # Save page state

    def pdf_zoom_in(self):
        """Increase zoom level"""
        self.pdf_zoom = min(self.pdf_zoom + 0.25, 4.0)
        self.render_pdf_page()
        if hasattr(self, 'pdf_zoom_label'):
            self.pdf_zoom_label.setText(f"{int(self.pdf_zoom * 100)}%")

    def pdf_zoom_out(self):
        """Decrease zoom level"""
        self.pdf_zoom = max(self.pdf_zoom - 0.25, 0.5)
        self.render_pdf_page()
        if hasattr(self, 'pdf_zoom_label'):
            self.pdf_zoom_label.setText(f"{int(self.pdf_zoom * 100)}%")

    def pdf_fit_width(self):
        """Fit PDF to scroll area width"""
        if not self.pdf_doc or not self.pdf_scroll:
            return

        try:
            page = self.pdf_doc[self.pdf_current_page]
            # Get scroll area width (minus some padding for scrollbar)
            scroll_width = self.pdf_scroll.viewport().width() - 20
            # Calculate zoom to fit width
            page_width = page.rect.width
            self.pdf_zoom = scroll_width / page_width
            self.render_pdf_page()
            if hasattr(self, 'pdf_zoom_label'):
                self.pdf_zoom_label.setText(f"{int(self.pdf_zoom * 100)}%")
        except Exception as e:
            print(f"Error fitting PDF to width: {e}")

    def open_pdf_in_external_viewer(self):
        """Open the current PDF in an external viewer application"""
        pdfviewer = self.settings.get("pdfviewer")
        if not pdfviewer or not self.pdf_path:
            return

        # Expand paths
        viewer_path = os.path.expanduser(pdfviewer)
        pdf_path = os.path.expanduser(self.pdf_path)

        # Skip if PDF is a URL (external viewer expects local files)
        if self.pdf_path.startswith(('http://', 'https://')):
            self.status_label.setText("Cannot open URL-based PDF in external viewer")
            return

        try:
            subprocess.Popen([viewer_path, pdf_path], start_new_session=True)
            self.status_label.setText(f"Opened in external viewer")
        except Exception as e:
            print(f"Error opening PDF in external viewer: {e}")
            self.status_label.setText(f"Error: {e}")

    def get_viewer_cycle_order(self):
        """Get the viewer cycle order: default -> examples -> help -> remaining viewers"""
        default_viewer = getattr(self, 'config_column2_default', None) or "pdf"
        # Fixed positions: default first, examples second, help third
        # Remaining viewers fill in after
        remaining = [m for m in ["pdf", "webview", "image", "console"] if m != default_viewer]
        return [default_viewer, "examples", "help"] + remaining

    def toggle_column2_mode(self):
        """Toggle between viewers: default -> examples -> help -> remaining viewers"""
        # Hide all containers
        self.pdf_container.hide()
        self.webview_container.hide()
        self.image_container.hide()
        self.help_container.hide()
        self.examples_container.hide()
        self.console_container.hide()

        # Get dynamic cycle order based on default viewer
        cycle = self.get_viewer_cycle_order()
        current_idx = cycle.index(self.column2_mode) if self.column2_mode in cycle else -1
        next_idx = (current_idx + 1) % len(cycle)
        next_mode = cycle[next_idx]
        next_next_mode = cycle[(next_idx + 1) % len(cycle)]

        # Mode display info
        mode_info = {
            "pdf": ("PDF", "PDF Viewer", self.pdf_container),
            "webview": ("Web", "Web View", self.webview_container),
            "image": ("Image", "Image Viewer", self.image_container),
            "help": ("Help", "Help", self.help_container),
            "examples": ("Examples", "Handler Examples", self.examples_container),
            "console": ("Console", "Console", self.console_container),
        }

        self.column2_mode = next_mode
        btn_text, header_text, container = mode_info[next_mode]
        next_btn_text = mode_info[next_next_mode][0]

        self.column2_toggle_btn.setText(btn_text)
        self.column2_toggle_btn.setToolTip(f"Click for {next_btn_text}")
        self.column2_header.setText(header_text)
        container.show()

        # Load content for viewers that need it
        if next_mode == "help":
            self.load_help_content()
        elif next_mode == "examples":
            self.load_examples_content()

        self.save_notes()  # Save mode preference

    def create_webview_toolbar(self, parent_layout):
        """Create a toolbar for the webview"""
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 5)
        toolbar_layout.setSpacing(5)

        # Button style
        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                min-width: 28px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QPushButton:pressed {{
                background-color: {self.t('bg_category_hover')};
            }}
        """

        # Back button
        back_btn = QPushButton("<")
        back_btn.setStyleSheet(btn_style)
        back_btn.setToolTip("Go back")
        back_btn.clicked.connect(self.webview_back)
        toolbar_layout.addWidget(back_btn)

        # Forward button
        forward_btn = QPushButton(">")
        forward_btn.setStyleSheet(btn_style)
        forward_btn.setToolTip("Go forward")
        forward_btn.clicked.connect(self.webview_forward)
        toolbar_layout.addWidget(forward_btn)

        # Refresh button
        refresh_btn = QPushButton("↻")
        refresh_btn.setStyleSheet(btn_style)
        refresh_btn.setToolTip("Refresh page")
        refresh_btn.clicked.connect(self.webview_refresh)
        toolbar_layout.addWidget(refresh_btn)

        # Home button
        home_btn = QPushButton("⌂")
        home_btn.setStyleSheet(btn_style)
        home_btn.setToolTip("Go to home URL (from project)")
        home_btn.clicked.connect(self.webview_home)
        toolbar_layout.addWidget(home_btn)

        # Separator
        sep1 = QLabel("|")
        sep1.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep1)

        # URL bar
        self.webview_url_bar = QLineEdit()
        self.webview_url_bar.setPlaceholderText("Enter URL...")
        self.webview_url_bar.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.t('bg_input')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {self.t('bg_category')};
            }}
        """)
        self.webview_url_bar.returnPressed.connect(self.webview_navigate)
        toolbar_layout.addWidget(self.webview_url_bar, 1)  # Stretch

        # Go button
        go_btn = QPushButton("Go")
        go_btn.setStyleSheet(btn_style)
        go_btn.setToolTip("Navigate to URL")
        go_btn.clicked.connect(self.webview_navigate)
        toolbar_layout.addWidget(go_btn)

        # Set as default button
        sep_default = QLabel("|")
        sep_default.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep_default)

        default_btn = QPushButton("📌")
        default_btn.setStyleSheet(btn_style)
        default_btn.setToolTip("Set this URL as default for this project")
        default_btn.clicked.connect(self.set_viewer_as_default)
        toolbar_layout.addWidget(default_btn)

        parent_layout.addWidget(toolbar_widget)

    def webview_back(self):
        """Go back in webview history"""
        if self.webview:
            self.webview.back()

    def webview_forward(self):
        """Go forward in webview history"""
        if self.webview:
            self.webview.forward()

    def webview_refresh(self):
        """Refresh current page"""
        if self.webview:
            self.webview.reload()

    def webview_home(self):
        """Navigate to home URL from config"""
        if self.webview and hasattr(self, 'config_webview_url') and self.config_webview_url:
            self.webview.setUrl(QUrl(self.config_webview_url))

    def webview_navigate(self):
        """Navigate to URL in URL bar"""
        if self.webview and self.webview_url_bar:
            url = self.webview_url_bar.text().strip()
            if url:
                # Add https:// if no protocol specified
                if not url.startswith(('http://', 'https://', 'file://')):
                    url = 'https://' + url
                self.webview.setUrl(QUrl(url))

    def on_webview_url_changed(self, url):
        """Handle URL changes in webview"""
        if self.webview_url_bar:
            self.webview_url_bar.setText(url.toString())
        # Save the current URL
        self.webview_url = url.toString()
        self.save_notes()

    def preview_in_webview(self, url):
        """Preview a URL in the webview panel"""
        if not self.webview:
            return

        # Switch to webview mode if not already
        while self.column2_mode != "webview":
            self.toggle_column2_mode()

        # Load the URL
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        self.webview.setUrl(QUrl(url))

    def preview_in_image_viewer(self, path):
        """Preview an image in the image viewer panel"""
        if not hasattr(self, 'image_label') or not self.image_label:
            return

        # Switch to image mode if not already
        while self.column2_mode != "image":
            self.toggle_column2_mode()

        # Load the image
        self.load_image(path)

    def open_terminal_at(self, path):
        """Open a terminal at the specified path"""
        expanded_path = os.path.expanduser(path)
        if os.path.isfile(expanded_path):
            expanded_path = os.path.dirname(expanded_path)
        cmd = self._get_terminal_workdir_command(expanded_path)
        subprocess.Popen(cmd, start_new_session=True)

    def create_image_toolbar(self, parent_layout):
        """Create a toolbar for the image viewer"""
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 5)
        toolbar_layout.setSpacing(5)

        # Button style
        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                min-width: 28px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QPushButton:pressed {{
                background-color: {self.t('bg_category_hover')};
            }}
        """

        # Open button
        open_btn = QPushButton("Open")
        open_btn.setStyleSheet(btn_style)
        open_btn.setToolTip("Open an image file")
        open_btn.clicked.connect(self.open_image_file)
        toolbar_layout.addWidget(open_btn)

        # Separator
        sep1 = QLabel("|")
        sep1.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep1)

        # Zoom out button
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setStyleSheet(btn_style)
        zoom_out_btn.setToolTip("Zoom out")
        zoom_out_btn.clicked.connect(self.image_zoom_out)
        toolbar_layout.addWidget(zoom_out_btn)

        # Zoom level indicator
        self.image_zoom_label = QLabel(f"{int(self.image_zoom * 100)}%")
        self.image_zoom_label.setStyleSheet("margin: 0 5px; font-size: 12px;")
        toolbar_layout.addWidget(self.image_zoom_label)

        # Zoom in button
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setStyleSheet(btn_style)
        zoom_in_btn.setToolTip("Zoom in")
        zoom_in_btn.clicked.connect(self.image_zoom_in)
        toolbar_layout.addWidget(zoom_in_btn)

        # Fit width button
        fit_btn = QPushButton("Fit")
        fit_btn.setStyleSheet(btn_style)
        fit_btn.setToolTip("Fit to width")
        fit_btn.clicked.connect(self.image_fit_width)
        toolbar_layout.addWidget(fit_btn)

        # Separator and external button
        sep2 = QLabel("|")
        sep2.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep2)

        external_btn = QPushButton("External")
        external_btn.setStyleSheet(btn_style)
        external_btn.setToolTip("Open in external image viewer (gwenview)")
        external_btn.clicked.connect(self.open_image_in_external_viewer)
        toolbar_layout.addWidget(external_btn)

        # Set as default button
        sep_default = QLabel("|")
        sep_default.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep_default)

        default_btn = QPushButton("📌")
        default_btn.setStyleSheet(btn_style)
        default_btn.setToolTip("Set this image as default for this project")
        default_btn.clicked.connect(self.set_viewer_as_default)
        toolbar_layout.addWidget(default_btn)

        toolbar_layout.addStretch()
        parent_layout.addWidget(toolbar_widget)

    def open_image_in_external_viewer(self):
        """Open the current image in an external viewer (gwenview)"""
        if not self.image_path:
            return
        expanded_path = os.path.expanduser(self.image_path)
        if os.path.exists(expanded_path):
            subprocess.Popen(["gwenview", expanded_path], start_new_session=True)

    def create_help_toolbar(self, parent_layout):
        """Create a toolbar for the help viewer"""
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 5)
        toolbar_layout.setSpacing(5)

        # Button style
        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                min-width: 28px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QPushButton:pressed {{
                background-color: {self.t('bg_category_hover')};
            }}
        """

        # Reload button
        reload_btn = QPushButton("↻")
        reload_btn.setStyleSheet(btn_style)
        reload_btn.setToolTip("Reload help content")
        reload_btn.clicked.connect(self.load_help_content)
        toolbar_layout.addWidget(reload_btn)

        # Separator
        sep = QLabel("|")
        sep.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep)

        # External button
        external_btn = QPushButton("External")
        external_btn.setStyleSheet(btn_style)
        external_btn.setToolTip("Open README.md in Kate")
        external_btn.clicked.connect(self.open_help_in_external_editor)
        toolbar_layout.addWidget(external_btn)

        toolbar_layout.addStretch()
        parent_layout.addWidget(toolbar_widget)

    def open_help_in_external_editor(self):
        """Open README.md in Kate"""
        readme_path = os.path.join(self.script_dir, "README.md")
        if os.path.exists(readme_path):
            subprocess.Popen(["kate", readme_path], start_new_session=True)

    def create_examples_toolbar(self, parent_layout):
        """Create a toolbar for the examples viewer"""
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 5)
        toolbar_layout.setSpacing(5)

        # Button style
        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                min-width: 28px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QPushButton:pressed {{
                background-color: {self.t('bg_category_hover')};
            }}
        """

        # Reload button
        reload_btn = QPushButton("↻")
        reload_btn.setStyleSheet(btn_style)
        reload_btn.setToolTip("Reload examples content")
        reload_btn.clicked.connect(self.load_examples_content)
        toolbar_layout.addWidget(reload_btn)

        # Separator
        sep = QLabel("|")
        sep.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep)

        # External button
        external_btn = QPushButton("External")
        external_btn.setStyleSheet(btn_style)
        external_btn.setToolTip("Open EXAMPLES.html in editor")
        external_btn.clicked.connect(self.open_examples_in_external_editor)
        toolbar_layout.addWidget(external_btn)

        toolbar_layout.addStretch()
        parent_layout.addWidget(toolbar_widget)

    def load_examples_content(self):
        """Load and display EXAMPLES.html content with theme placeholders replaced"""
        examples_path = os.path.join(self.script_dir, "EXAMPLES.html")
        if not os.path.exists(examples_path):
            self.examples_browser.setHtml(f"<h1 style='color: {self.t('fg_help_h1')}'>Examples</h1><p style='color: {self.t('fg_primary')}'>EXAMPLES.html not found.</p>")
            return

        try:
            with open(examples_path, 'r', encoding='utf-8') as f:
                html_content = f.read()

            # Replace theme placeholders with actual colors
            # Format: {theme_key} -> actual color value
            import re
            def replace_placeholder(match):
                key = match.group(1)
                return self.t(key)

            html_content = re.sub(r'\{(\w+)\}', replace_placeholder, html_content)
            self.examples_browser.setHtml(html_content)
        except Exception as e:
            self.examples_browser.setHtml(f"<h1 style='color: {self.t('fg_help_h1')}'>Error</h1><p style='color: {self.t('fg_primary')}'>Could not load EXAMPLES.html: {e}</p>")

    def open_examples_in_external_editor(self):
        """Open EXAMPLES.html in the configured editor"""
        examples_path = os.path.join(self.script_dir, "EXAMPLES.html")
        editor = self.settings.get("open_note_external") or "kate"
        if os.path.exists(examples_path):
            subprocess.Popen([editor, examples_path], start_new_session=True)

    def create_console_toolbar(self, parent_layout):
        """Create a toolbar for the console"""
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 5)
        toolbar_layout.setSpacing(5)

        # Button style
        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                min-width: 28px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QPushButton:pressed {{
                background-color: {self.t('bg_category_hover')};
            }}
        """

        # Open folder button
        open_btn = QPushButton("Open")
        open_btn.setStyleSheet(btn_style)
        open_btn.setToolTip("Navigate to a directory")
        open_btn.clicked.connect(self.console_open_directory)
        toolbar_layout.addWidget(open_btn)

        # External terminal button
        external_btn = QPushButton("External")
        external_btn.setStyleSheet(btn_style)
        external_btn.setToolTip("Open in Konsole (for interactive programs)")
        external_btn.clicked.connect(self.console_open_external)
        toolbar_layout.addWidget(external_btn)

        # Separator
        sep1 = QLabel("|")
        sep1.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep1)

        # Path label with limitation hint
        self.console_path_label = QLabel("~")
        self.console_path_label.setStyleSheet(f"font-size: 11px; color: {self.t('fg_secondary')};")
        self.console_path_label.setToolTip(
            "Python/IPython console - use !command for shell commands.\n"
            "Limitations: No interactive programs (nano, vim, htop).\n"
            "Use 'External' button for full terminal features."
        )
        toolbar_layout.addWidget(self.console_path_label, 1)

        # Set as default button
        default_btn = QPushButton("📌")
        default_btn.setStyleSheet(btn_style)
        default_btn.setToolTip("Set this directory as default for this project")
        default_btn.clicked.connect(self.set_viewer_as_default)
        toolbar_layout.addWidget(default_btn)

        parent_layout.addWidget(toolbar_widget)

    def console_open_directory(self):
        """Open a directory picker and navigate the console to it"""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Directory for Console",
            os.path.expanduser("~")
        )
        if folder_path:
            self.console_path = folder_path
            self.console_path_label.setText(folder_path)
            if self.console_available and hasattr(self, 'console_widget'):
                self.console_widget.execute(f'import os; os.chdir("{folder_path}")', hidden=True)
                self.console_widget.execute('!pwd')

    def console_open_external(self):
        """Open external terminal at the current console path"""
        path = getattr(self, 'console_path', None) or os.path.expanduser("~")
        expanded_path = os.path.expanduser(path)
        if os.path.isfile(expanded_path):
            expanded_path = os.path.dirname(expanded_path)
        cmd = self._get_terminal_workdir_command(expanded_path)
        subprocess.Popen(cmd, start_new_session=True)

    def load_help_content(self):
        """Load and display README.md content"""
        readme_path = os.path.join(self.script_dir, "README.md")
        if not os.path.exists(readme_path):
            self.help_browser.setHtml(f"<h1 style='color: {self.t('fg_help_h1')}'>Help</h1><p style='color: {self.t('fg_primary')}'>README.md not found.</p>")
            return

        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
            html_content = self.markdown_to_html(markdown_content)
            self.help_browser.setHtml(html_content)
        except Exception as e:
            self.help_browser.setHtml(f"<h1 style='color: {self.t('fg_help_h1')}'>Error</h1><p style='color: {self.t('fg_primary')}'>Could not load README.md: {e}</p>")

    def markdown_to_html(self, text):
        """Convert markdown to HTML with theme-aware colors"""
        import re

        # Get theme colors
        bg_code = self.t('bg_code')
        fg_code = self.t('fg_code')
        bg_code_inline = self.t('bg_code_inline')
        fg_primary = self.t('fg_primary')
        fg_link = self.t('fg_link')
        fg_h1 = self.t('fg_help_h1')
        fg_h2 = self.t('fg_help_h2')
        fg_h3 = self.t('fg_help_h3')
        border_h1 = self.t('border_help_h1')
        border_h2 = self.t('border_help_h2')

        # Escape HTML entities first
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')

        # Code blocks (``` ... ```)
        def replace_code_block(match):
            code = match.group(1)
            return f'<pre style="background-color: {bg_code}; color: {fg_code}; padding: 10px; border-radius: 5px; overflow-x: auto;"><code>{code}</code></pre>'
        text = re.sub(r'```(?:\w+)?\n(.*?)```', replace_code_block, text, flags=re.DOTALL)

        # Inline code (`code`)
        text = re.sub(r'`([^`]+)`', f'<code style="background-color: {bg_code_inline}; color: {fg_primary}; padding: 2px 5px; border-radius: 3px;">\\1</code>', text)

        # Headers
        text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)

        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

        # Italic
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

        # Links
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

        # Unordered lists
        lines = text.split('\n')
        in_list = False
        result = []
        for line in lines:
            if re.match(r'^- (.+)$', line):
                if not in_list:
                    result.append('<ul>')
                    in_list = True
                item = re.sub(r'^- (.+)$', r'<li>\1</li>', line)
                result.append(item)
            else:
                if in_list:
                    result.append('</ul>')
                    in_list = False
                result.append(line)
        if in_list:
            result.append('</ul>')
        text = '\n'.join(result)

        # Paragraphs (blank lines become paragraph breaks)
        text = re.sub(r'\n\n+', '</p><p>', text)

        # Wrap in basic HTML structure with theme-aware styling
        html = f'''
        <html>
        <head>
        <style>
            body {{
                font-family: sans-serif;
                font-size: 12pt;
                line-height: 1.6;
                color: {fg_primary};
                padding: 10px;
            }}
            h1 {{ color: {fg_h1}; border-bottom: 2px solid {border_h1}; padding-bottom: 5px; }}
            h2 {{ color: {fg_h2}; border-bottom: 1px solid {border_h2}; padding-bottom: 3px; }}
            h3 {{ color: {fg_h3}; }}
            a {{ color: {fg_link}; }}
            ul {{ margin-left: 20px; }}
            li {{ margin-bottom: 5px; }}
        </style>
        </head>
        <body>
        <p>{text}</p>
        </body>
        </html>
        '''
        return html

    def open_image_file(self):
        """Open an image file via file picker"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            os.path.expanduser("~"),
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;All Files (*)"
        )
        if file_path:
            self.load_image(file_path)

    def load_image(self, path):
        """Load and display an image"""
        expanded_path = os.path.expanduser(path)
        if not os.path.exists(expanded_path):
            self.status_label.setText(f"Image not found: {path}")
            return

        try:
            self.image_path = path
            self.image_pixmap = QPixmap(expanded_path)
            if self.image_pixmap.isNull():
                self.status_label.setText(f"Failed to load image: {path}")
                return

            # Defer fit-to-width to allow layout to settle (needed on startup)
            QTimer.singleShot(500, self.image_fit_width)
            self.save_notes()  # Save image path
            self.status_label.setText(f"✓ Loaded image: {os.path.basename(path)}")
            self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
        except Exception as e:
            self.status_label.setText(f"Error loading image: {e}")

    def render_image(self):
        """Render the image at current zoom level"""
        if not hasattr(self, 'image_pixmap') or self.image_pixmap.isNull():
            return

        scaled_pixmap = self.image_pixmap.scaled(
            int(self.image_pixmap.width() * self.image_zoom),
            int(self.image_pixmap.height() * self.image_zoom),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)

    def image_zoom_in(self):
        """Zoom in on image"""
        self.image_zoom = min(5.0, self.image_zoom + 0.25)
        self.image_zoom_label.setText(f"{int(self.image_zoom * 100)}%")
        self.render_image()

    def image_zoom_out(self):
        """Zoom out on image"""
        self.image_zoom = max(0.1, self.image_zoom - 0.25)
        self.image_zoom_label.setText(f"{int(self.image_zoom * 100)}%")
        self.render_image()

    def image_fit_width(self):
        """Fit image to viewer width"""
        if not hasattr(self, 'image_pixmap') or self.image_pixmap.isNull() or not self.image_scroll:
            return

        viewport_width = self.image_scroll.viewport().width() - 20
        image_width = self.image_pixmap.width()
        if image_width > 0:
            self.image_zoom = viewport_width / image_width
            self.image_zoom_label.setText(f"{int(self.image_zoom * 100)}%")
            self.render_image()

    def toggle_bold(self):
        """Toggle bold formatting on selected text"""
        if hasattr(self, 'notepad'):
            fmt = self.notepad.currentCharFormat()
            if fmt.fontWeight() == QFont.Weight.Bold:
                fmt.setFontWeight(QFont.Weight.Normal)
            else:
                fmt.setFontWeight(QFont.Weight.Bold)
            self.notepad.mergeCurrentCharFormat(fmt)
            self.notepad.setFocus()

    def toggle_italic(self):
        """Toggle italic formatting on selected text"""
        if hasattr(self, 'notepad'):
            fmt = self.notepad.currentCharFormat()
            fmt.setFontItalic(not fmt.fontItalic())
            self.notepad.mergeCurrentCharFormat(fmt)
            self.notepad.setFocus()

    def toggle_code(self):
        """Toggle code/monospace formatting on selected text"""
        if hasattr(self, 'notepad'):
            cursor = self.notepad.textCursor()
            if cursor.hasSelection():
                selected_text = cursor.selectedText()
                # Wrap in <code> tags with white on dark styling
                cursor.insertHtml(f'<code style="font-family: monospace; background-color: #2d2d2d; color: #f0f0f0; padding: 2px 5px;">{selected_text}</code>')
            self.notepad.setFocus()

    def toggle_emphasis(self):
        """Toggle emphasis/action formatting on selected text"""
        if hasattr(self, 'notepad'):
            cursor = self.notepad.textCursor()
            if cursor.hasSelection():
                selected_text = cursor.selectedText()
                # Wrap in span with red background highlight
                cursor.insertHtml(f'<span style="background-color: #9c0c15; color: #f0f0f0; padding: 4px 10px;">{selected_text}</span>')
            self.notepad.setFocus()

    def apply_heading(self, level):
        """Apply heading style to current paragraph"""
        if hasattr(self, 'notepad'):
            cursor = self.notepad.textCursor()
            cursor.select(cursor.SelectionType.BlockUnderCursor)

            # Set heading size based on level (compact sizes for quick notes)
            sizes = {1: 16, 2: 14}
            fmt = cursor.charFormat()
            fmt.setFontPointSize(sizes.get(level, 12))
            fmt.setFontWeight(QFont.Weight.Bold)
            cursor.mergeCharFormat(fmt)
            self.notepad.setFocus()

    def toggle_bullet_list(self):
        """Toggle bullet list for current paragraph"""
        if hasattr(self, 'notepad'):
            cursor = self.notepad.textCursor()
            current_list = cursor.currentList()

            if current_list and current_list.format().style() == QTextListFormat.Style.ListDisc:
                # Remove from list
                block_fmt = cursor.blockFormat()
                block_fmt.setIndent(0)
                cursor.setBlockFormat(block_fmt)
                # Remove the list
                cursor.currentList().remove(cursor.block())
            else:
                # Create bullet list
                list_fmt = QTextListFormat()
                list_fmt.setStyle(QTextListFormat.Style.ListDisc)
                cursor.createList(list_fmt)
            self.notepad.setFocus()

    def toggle_numbered_list(self):
        """Toggle numbered list for current paragraph"""
        if hasattr(self, 'notepad'):
            cursor = self.notepad.textCursor()
            current_list = cursor.currentList()

            if current_list and current_list.format().style() == QTextListFormat.Style.ListDecimal:
                # Remove from list
                block_fmt = cursor.blockFormat()
                block_fmt.setIndent(0)
                cursor.setBlockFormat(block_fmt)
                cursor.currentList().remove(cursor.block())
            else:
                # Create numbered list
                list_fmt = QTextListFormat()
                list_fmt.setStyle(QTextListFormat.Style.ListDecimal)
                cursor.createList(list_fmt)
            self.notepad.setFocus()

    def insert_link(self):
        """Insert or edit a hyperlink"""
        if hasattr(self, 'notepad'):
            cursor = self.notepad.textCursor()
            selected_text = cursor.selectedText()

            # Simple dialog to get URL
            from PyQt6.QtWidgets import QInputDialog

            url, ok = QInputDialog.getText(
                self, "Insert Link",
                "Enter URL:",
                text="https://"
            )

            if ok and url:
                if not selected_text:
                    # If no text selected, use URL as text
                    selected_text = url

                # Insert the link as HTML
                link_html = f'<a href="{url}">{selected_text}</a>'
                cursor.insertHtml(link_html)
            self.notepad.setFocus()

    def clear_formatting(self):
        """Clear all formatting from selected text"""
        if hasattr(self, 'notepad'):
            cursor = self.notepad.textCursor()
            if cursor.hasSelection():
                # Get plain text
                plain_text = cursor.selectedText()
                # Create a clean format with default font
                from PyQt6.QtGui import QTextCharFormat
                clean_fmt = QTextCharFormat()
                clean_fmt.setFontWeight(QFont.Weight.Normal)
                clean_fmt.setFontItalic(False)
                clean_fmt.setFontUnderline(False)
                clean_fmt.setFontPointSize(12)
                clean_fmt.setForeground(Qt.GlobalColor.black)
                clean_fmt.clearBackground()
                # Insert with clean format
                cursor.insertText(plain_text, clean_fmt)
            self.notepad.setFocus()

    def refresh_projects(self, restore_scroll_pos=None):
        """Refresh the project list by reloading the configuration"""
        try:
            # Store current window geometry
            current_geometry = self.geometry()

            # Reload configuration from file
            self.load_config()
            self.load_notes()

            # Recreate the UI
            self.init_ui()

            # Restore window geometry
            self.setGeometry(current_geometry)

            # Restore scroll position after UI is laid out
            if restore_scroll_pos is not None and hasattr(self, 'main_scroll'):
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self.main_scroll.verticalScrollBar().setValue(restore_scroll_pos))

            # Show status message
            self.status_label.setText("✓ Configuration reloaded successfully!")
            self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
        except Exception as e:
            # Show error dialog if reload fails
            QMessageBox.critical(
                self,
                "Reload Error",
                f"Failed to reload configuration:\n{str(e)}\n\nCheck your syntax and try again."
            )
            self.status_label.setText(f"✗ Reload failed: {str(e)}")
            self.status_label.setStyleSheet("color: #e74c3c; margin: 10px; font-weight: bold;")

    def open_in_app(self, path, app="default"):
        """Open the specified path in the given application"""
        try:
            # Expand ~ to home directory
            expanded_path = os.path.expanduser(path)

            # 1. Check built-in smart defaults first (browser, file_manager, editor, default)
            if app in BUILTIN_HANDLERS:
                cmd = BUILTIN_HANDLERS[app](expanded_path)
                subprocess.Popen(cmd, start_new_session=True)
                self.status_label.setText(f"✓ Opened: {path}")
                self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
                return

            # 1b. Handle terminal/konsole using configured terminal
            # Supports optional command: "~/path command args" -> cd ~/path && command args
            if app in ("konsole", "terminal"):
                parts = expanded_path.split()
                workdir = parts[0]
                command = " ".join(parts[1:]) if len(parts) > 1 else ""

                # Ensure workdir is a directory
                if os.path.isfile(workdir):
                    workdir = os.path.dirname(workdir)

                terminal_name = self.get_configured_terminal()
                if command:
                    # Run command in subshell with trapped INT for clean exit
                    # Then drop to interactive shell
                    shell_cmd = f'cd {shlex.quote(workdir)} && (trap "exit 0" INT; {command}); exec bash'
                    cmd = self._get_terminal_command(shell_cmd, hold=False)
                    subprocess.Popen(cmd, start_new_session=True)
                    self.status_label.setText(f"✓ Running in {terminal_name}: {command}")
                else:
                    # Just open terminal at directory
                    cmd = self._get_terminal_workdir_command(workdir)
                    subprocess.Popen(cmd, start_new_session=True)
                    self.status_label.setText(f"✓ Opened terminal ({terminal_name}): {path}")
                self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
                return

            # 2. Check for projectflowlink (internal config-switching feature)
            if app == "projectflowlink":
                # Link to another config file
                # If just a filename, look in configs directory
                if os.path.sep not in path and not path.startswith('/'):
                    configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
                    config_path = os.path.join(configs_dir, path)
                else:
                    config_path = os.path.expanduser(path)

                if os.path.exists(config_path):
                    self.switch_to_config(config_path)
                else:
                    # Offer to create the missing project
                    msg = QMessageBox(self)
                    msg.setWindowTitle("Project Not Found")
                    msg.setText(f"'{path}' does not exist.\n\nCreate it as a new project?")
                    msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    msg.setDefaultButton(QMessageBox.StandardButton.Yes)
                    msg.raise_()
                    msg.activateWindow()
                    reply = msg.exec()
                    if reply == QMessageBox.StandardButton.Yes:
                        # Create from template
                        template_path = os.path.join(self.script_dir, "examples", "projectflow.json")
                        if os.path.exists(template_path):
                            shutil.copy2(template_path, config_path)
                        else:
                            self.create_default_project(config_path)
                        self.switch_to_config(config_path)
                return

            # 3. Check complex handlers from launch_handlers.py (need Python logic)
            if app in self.complex_handlers:
                try:
                    result = self.complex_handlers[app](path, expanded_path)
                    self.status_label.setText(f"✓ {result}")
                    self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
                except FileNotFoundError as e:
                    self.status_label.setText("✗ Command not found. Check editor/terminal/file manager in Settings.")
                    self.status_label.setStyleSheet("color: #e74c3c; margin: 10px; font-weight: bold;")
                return

            # 4. Check simple handlers from launch_handlers.py
            if app in self.launch_handlers:
                handler = self.launch_handlers[app]
                cmd = self._build_handler_command(handler, expanded_path)
                subprocess.Popen(cmd, start_new_session=True)
                desc = handler.get("description", app)
                self.status_label.setText(f"✓ {desc}: {path}")
                self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
                return

            # 5. Legacy: terminal command patterns (&&, ||, ;, cd, npm)
            if "&&" in app or "||" in app or ";" in app or app.startswith("cd ") or app.startswith("npm "):
                # This is a terminal command, not an application
                command = app.replace("{path}", expanded_path)
                cmd = self._get_terminal_command(command, hold=True)
                subprocess.Popen(cmd, start_new_session=True)
                self.status_label.setText(f"✓ Executed in terminal: {command}")
                self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
                return

            # 6. Legacy: flatpak pattern (com.*)
            if app.startswith("com"):
                subprocess.Popen(["flatpak", "run", app, expanded_path], start_new_session=True)
                self.status_label.setText(f"✓ Opened via Flatpak: {app}")
                self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
                return

            # 7. Special handling for kate with directories (use dolphin instead)
            if app == "kate" and os.path.isdir(expanded_path):
                subprocess.Popen(["dolphin", expanded_path], start_new_session=True)
                self.status_label.setText(f"✓ Opened folder in Dolphin: {path}")
                self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
                return

            # 8. Fallback: direct app launch
            subprocess.Popen([app, expanded_path], start_new_session=True)
            app_name = self.APP_INFO.get(app, {}).get("name", app)
            self.status_label.setText(f"✓ Opened in {app_name}: {path}")
            self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")

        except FileNotFoundError:
            self.status_label.setText(f"✗ Error: {app} not found!")
            self.status_label.setStyleSheet("color: #e74c3c; margin: 10px; font-weight: bold;")
        except Exception as e:
            self.status_label.setText(f"✗ Error: {str(e)}")
            self.status_label.setStyleSheet("color: #e74c3c; margin: 10px; font-weight: bold;")

    def directorydev_action(self, path, action):
        """Execute a single directorydev action (file_manager, terminal, editor, or npm)."""
        from launch_handlers import handle_directorydev_action
        expanded_path = os.path.expanduser(path)

        try:
            handle_directorydev_action(expanded_path, action)
        except FileNotFoundError:
            self.status_label.setText("✗ Command not found. Check editor/terminal/file manager in Settings.")
            self.status_label.setStyleSheet("color: #e74c3c; margin: 10px; font-weight: bold;")
            return

        # Update status with dynamic app names
        parts = expanded_path.split()
        project_path = parts[0]
        file_manager = self.get_configured_file_manager()
        editor = self.get_configured_editor()
        action_names = {
            "file_manager": f"Opened in {file_manager}",
            "dolphin": f"Opened in {file_manager}",  # Legacy alias
            "terminal": "Opened terminal at",
            "editor": f"Opened in {editor}",
            "code": f"Opened in {editor}",  # Legacy alias
            "npm": "Running npm in"
        }
        self.status_label.setText(f"✓ {action_names.get(action, action)}: {project_path}")
        self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")

    def get_version(self):
        """Get the current version from git (short commit hash or tag) with date"""
        try:
            # Get version/tag
            version_result = subprocess.run(
                ["git", "describe", "--tags", "--always", "--dirty"],
                cwd=self.script_dir,
                capture_output=True,
                text=True
            )
            # Get last commit date
            date_result = subprocess.run(
                ["git", "log", "-1", "--format=%cd", "--date=format:%Y-%m-%d %H:%M"],
                cwd=self.script_dir,
                capture_output=True,
                text=True
            )
            if version_result.returncode == 0:
                version = version_result.stdout.strip()
                if date_result.returncode == 0:
                    commit_date = date_result.stdout.strip()
                    return f"{version} [{commit_date}]"
                return version
        except Exception:
            pass
        return "unknown"

    def install_kde_servicemenu(self):
        """Install the KDE Dolphin service menu for 'Add to ProjectFlow' functionality"""
        try:
            # Source files
            servicemenu_src = os.path.join(self.script_dir, "utilities", "projectflow-servicemenu.desktop")
            script_src = os.path.join(self.script_dir, "utilities", "add-projectflow-servicemenu.sh")

            # Check source files exist
            if not os.path.exists(servicemenu_src):
                QMessageBox.warning(self, "Install Service Menu",
                    f"Service menu file not found:\n{servicemenu_src}")
                return
            if not os.path.exists(script_src):
                QMessageBox.warning(self, "Install Service Menu",
                    f"Service menu script not found:\n{script_src}")
                return

            # Destination directory
            servicemenu_dir = os.path.expanduser("~/.local/share/kio/servicemenus")
            os.makedirs(servicemenu_dir, exist_ok=True)

            # Read and modify the desktop file to point to the correct script path
            with open(servicemenu_src, 'r') as f:
                content = f.read()

            # Update the Exec line to use the absolute path
            content = content.replace(
                "Exec=add-projectflow-servicemenu.sh %F",
                f"Exec={script_src} %F"
            )

            # Write to destination
            servicemenu_dest = os.path.join(servicemenu_dir, "projectflow-servicemenu.desktop")
            with open(servicemenu_dest, 'w') as f:
                f.write(content)

            # Make both script and desktop file executable (KDE security requirement)
            os.chmod(script_src, 0o755)
            os.chmod(servicemenu_dest, 0o755)

            QMessageBox.information(self, "Install Service Menu",
                "Service menu installed successfully!\n\n"
                "You can now right-click files/folders in Dolphin\n"
                "and select 'Add to ProjectFlow'.")

        except Exception as e:
            QMessageBox.warning(self, "Install Service Menu", f"Installation failed:\n{str(e)}")

    def check_for_upgrade(self):
        """Check for updates and upgrade if available"""
        try:
            # Check for local changes first
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.script_dir,
                capture_output=True,
                text=True
            )
            if status_result.stdout.strip():
                QMessageBox.warning(self, "Upgrade", "Local changes detected - please commit or stash first")
                return

            # Fetch from remote
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            QApplication.processEvents()

            fetch_result = subprocess.run(
                ["git", "fetch"],
                cwd=self.script_dir,
                capture_output=True,
                text=True,
                timeout=15  # Timeout after 15 seconds
            )
            if fetch_result.returncode != 0:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(self, "Upgrade", "Failed to check for updates")
                return

            # Compare local with remote
            diff_result = subprocess.run(
                ["git", "rev-list", "HEAD..@{u}", "--count"],
                cwd=self.script_dir,
                capture_output=True,
                text=True
            )

            if diff_result.returncode != 0:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(self, "Upgrade", "Could not compare versions")
                return

            commits_behind = int(diff_result.stdout.strip())

            if commits_behind == 0:
                QApplication.restoreOverrideCursor()
                QMessageBox.information(self, "Upgrade", "Already up to date")
                return

            # Pull updates
            pull_result = subprocess.run(
                ["git", "pull"],
                cwd=self.script_dir,
                capture_output=True,
                text=True,
                timeout=30  # Timeout after 30 seconds
            )

            QApplication.restoreOverrideCursor()

            if pull_result.returncode != 0:
                QMessageBox.warning(self, "Upgrade", "Failed to download updates")
                return

            QMessageBox.information(self, "Upgrade", f"Updated with {commits_behind} commit(s). Restarting...")
            QApplication.processEvents()

            # Restart the application
            QTimer.singleShot(500, self.restart_application)

        except subprocess.TimeoutExpired:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Upgrade", "Network timeout - check your connection and try again")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Upgrade Error", str(e))

    def restart_application(self):
        """Restart the application"""
        script_path = os.path.join(self.script_dir, "projectflow.py")
        subprocess.Popen([script_path, self.current_config_file], start_new_session=True)
        QApplication.quit()

    def regenerate_desktop_file(self):
        """Create a .desktop file for the current project with jump list to all projects"""
        import re

        # Get current project info
        current_config_name = os.path.basename(self.current_config_file)
        project_id = current_config_name.replace('.json', '')
        project_display_name = project_id.replace('_', ' ').title()

        # Desktop file named after current project
        desktop_file = os.path.expanduser(f"~/.local/share/applications/projectflow-{project_id}.desktop")
        projects_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))

        # Use projectflow-nix wrapper if available (for NixOS), otherwise projectflow.py
        nix_wrapper = os.path.join(self.script_dir, "projectflow-nix")
        if os.path.exists(nix_wrapper):
            script_path = nix_wrapper
        else:
            script_path = os.path.join(self.script_dir, "projectflow.py")

        # Get all project files for jump list
        project_files = []
        if os.path.exists(projects_dir):
            for f in sorted(os.listdir(projects_dir)):
                if f.endswith('.json') and f != 'template.json':
                    project_files.append(f)

        # Generate jump list actions (excluding current project)
        actions = []
        action_sections = []

        for project_file in project_files:
            if project_file == current_config_name:
                continue  # Skip current project in jump list
            project_path = os.path.join(projects_dir, project_file)
            display_name = project_file.replace('.json', '').replace('_', ' ').title()
            # Create safe action ID (lowercase, no spaces/special chars)
            action_id = re.sub(r'[^a-z0-9]', '', project_file.replace('.json', '').lower())

            actions.append(action_id)
            action_sections.append(f"""[Desktop Action {action_id}]
Name={display_name}
Exec={script_path} "{project_path}"
""")

        # Build desktop file content
        actions_line = f"Actions={';'.join(actions)};" if actions else ""

        # DE-specific icon
        de = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
        if 'gnome' in de:
            icon = "text-x-script"
        else:
            icon = "preferences-desktop-icons"

        content = f"""[Desktop Entry]
Type=Application
Name=ProjectFlow ({project_display_name})
Comment=Project launcher for {project_display_name}
Exec={script_path} "{self.current_config_file}"
Icon={icon}
Terminal=false
Categories=Utility;Development;
StartupWMClass=ProjectFlow-{project_id}
{actions_line}

"""
        content += '\n'.join(action_sections)

        # Write file
        try:
            with open(desktop_file, 'w') as f:
                f.write(content)

            # DE-specific refresh instructions
            de = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
            if 'kde' in de or 'plasma' in de:
                refresh_hint = "Run 'kbuildsycoca6' to refresh menus immediately."
            elif 'gnome' in de:
                refresh_hint = "GNOME should detect the new entry automatically.\nRight-click the app in your dock to see other projects."
            else:
                refresh_hint = "Your desktop should detect the new entry automatically."

            QMessageBox.information(self, "Menu Entry Created",
                f"Created menu entry for '{project_display_name}'\n\n"
                f"File: {desktop_file}\n"
                f"Right-click menu includes {len(actions)} other projects.\n\n"
                f"{refresh_hint}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create desktop file: {str(e)}")


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='ProjectFlow - Quick Launcher for Projects and Files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  ./projectflow.py                            # Use default config
  ./projectflow.py projects/myproject.json     # Use specific project
  ./projectflow.py ~/my_config.json           # Use config from any path
        '''
    )
    parser.add_argument(
        'config',
        nargs='?',
        help='Path to configuration file (relative or absolute)'
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)

    # Detect desktop environment for app identification strategy
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()

    app.setOrganizationName("ProjectFlow")

    if 'kde' in desktop or 'plasma' in desktop:
        # KDE: Per-project naming works for Activities pinning
        app.setApplicationName("ProjectFlow")
        app.setDesktopFileName("ProjectFlow")
    else:
        # GNOME/COSMIC/others: Consistent name for icon matching
        # Must match the installed projectflow.desktop file's StartupWMClass
        app.setApplicationName("projectflow")
        app.setDesktopFileName("projectflow")

    # Set window icon with fallback chain for different desktop environments
    de = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    if 'gnome' in de:
        icon_candidates = [
            "text-x-script",              # GNOME icon
            "application-x-executable",   # Generic app icon
            "system-run",                 # Generic freedesktop
            "folder",                     # Universal fallback
        ]
    else:
        icon_candidates = [
            "preferences-desktop-icons",  # KDE Breeze icon
            "application-x-executable",   # Generic app icon
            "system-run",                 # Generic freedesktop
            "folder",                     # Universal fallback
        ]
    for icon_name in icon_candidates:
        icon = QIcon.fromTheme(icon_name)
        if not icon.isNull():
            app.setWindowIcon(icon)
            break

    window = ProjectFlowApp(config_file_arg=args.config)
    window.showMaximized()
    #window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
