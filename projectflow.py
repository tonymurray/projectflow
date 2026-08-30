#!/usr/bin/env python3
"""
ProjectFlow - Quick Launcher for Projects and Files
KDE Plasma application with configuration file support
Edit config files and save to reload!
"""

import sys
import subprocess
import os
import shutil
import time
import shlex
import json
import argparse
import inspect
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QFileDialog, QGroupBox, QMessageBox, QScrollArea, QFrame, QTextEdit, QToolBar,
    QLineEdit, QComboBox, QTextBrowser, QDialog, QDialogButtonBox, QTabWidget, QFormLayout, QCheckBox,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QSizePolicy,
    QPlainTextEdit, QStackedWidget, QCompleter, QMenu, QStyledItemDelegate, QStyle, QFileIconProvider,
    QSplitter, QSpinBox, QDateEdit, QTimeEdit, QWidgetAction, QWIDGETSIZE_MAX, QRadioButton
)
from PyQt6.QtCore import Qt, QMimeData, QTimer, QPoint, QSize, QRect, pyqtSignal, QStringListModel, QEvent, QFileInfo, QByteArray, QDate, QTime
from PyQt6.QtGui import QIcon, QFont, QKeySequence, QShortcut, QTextListFormat, QImage, QPixmap, QDrag, QColor, QPainter, QFontMetrics
import re
import urllib.request
import urllib.error
import urllib.parse
import datetime
import csv as _csv
import fitz  # PyMuPDF for PDF rendering
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage
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


class DraggableColorSwatch(QPushButton):
    """A color swatch that supports drag-and-drop reordering within the color strip."""
    MIME_TYPE = "application/x-projectflow-color"

    def __init__(self, color_hex, app, parent=None):
        super().__init__(parent)
        self.color_hex = color_hex
        self.app = app
        self._drag_start = None
        self.setAcceptDrops(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or not self._drag_start:
            return
        if (event.pos() - self._drag_start).manhattanLength() < 6:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(self.MIME_TYPE, self.color_hex.encode())
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_TYPE):
            event.acceptProposedAction()

    def dropEvent(self, event):
        dragged = event.mimeData().data(self.MIME_TYPE).data().decode()
        if dragged != self.color_hex:
            self.app._reorder_colors(dragged, self.color_hex)
        event.acceptProposedAction()

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        super().mouseReleaseEvent(event)


class ConfigBarWidget(QWidget):
    """Widget that contains config buttons and handles drop events for reordering"""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setAcceptDrops(True)
        self.buttons = []  # List of (button_container, config_path, is_pinned)
        self._reflow_fn = None  # set by _populate_pinned_projects to sync cell widths

    def showEvent(self, event):
        super().showEvent(event)
        if self._reflow_fn:
            self._reflow_fn(self.width())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._reflow_fn and event.size().width() != event.oldSize().width():
            self._reflow_fn(event.size().width())

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


class FlowWidget(QWidget):
    """Responsive grid widget: target_cols per row, all cells same width stretching to fill.
    Narrows to fewer columns before cells shrink below min_cell_w. Re-elides button text on resize."""

    _ITEM_H = 28  # matches QPushButton min height 26 + layout margins

    def __init__(self, parent=None, target_cols=10, min_cell_w=80, hspacing=5, vspacing=5):
        super().__init__(parent)
        self._widgets = []
        self._target_cols = target_cols
        self._min_cell_w = min_cell_w
        self._hspacing = hspacing
        self._vspacing = vspacing
        self._reflowing = False

    def addWidget(self, widget):
        widget.setParent(self)
        widget.show()
        self._widgets.append(widget)

    def showEvent(self, event):
        super().showEvent(event)
        self._reflow(self.width() or 800)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self._reflow(event.size().width())

    def _reflow(self, width):
        if self._reflowing or width <= 0 or not self._widgets:
            return
        self._reflowing = True
        try:
            n = len(self._widgets)
            # cell_w is always based on target_cols so all lists use the same cell size.
            # Only fall back to fitting fewer cols when the window is genuinely too narrow.
            max_cols = max(1, (width + self._hspacing) // (self._min_cell_w + self._hspacing))
            cols = min(n, self._target_cols, max_cols)
            target_cell_w = (width - (self._target_cols - 1) * self._hspacing) // self._target_cols
            if target_cell_w >= self._min_cell_w:
                cell_w = target_cell_w          # normal: uniform ~10% width, items left-align
            else:
                cell_w = (width - (cols - 1) * self._hspacing) // cols  # narrow: fill the row

            fm = QFontMetrics(QApplication.font())
            for i, w in enumerate(self._widgets):
                col = i % cols
                row = i // cols
                w.setFixedWidth(cell_w)
                w.setGeometry(col * (cell_w + self._hspacing),
                              row * (self._ITEM_H + self._vspacing),
                              cell_w, self._ITEM_H)
                # Re-elide the main button label when cell width changes
                if hasattr(w, '_main_btn') and hasattr(w, '_full_text') and hasattr(w, '_side_w'):
                    left_extra = getattr(w, '_left_extra_w', 0)
                    label_w = max(10, cell_w - w._side_w - left_extra - 18)  # 18px = padding + border
                    w._main_btn.setText(fm.elidedText(w._full_text, Qt.TextElideMode.ElideRight, label_w))

            rows = (n + cols - 1) // cols
            self.setFixedHeight(max(1, rows * self._ITEM_H + (rows - 1) * self._vspacing))
        finally:
            self._reflowing = False

    def sizeHint(self):
        return QSize(self.minimumWidth(), self.minimumHeight())


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
            if data.startswith("item|"):
                parts = data.split("|")
                if len(parts) == 4 and int(parts[1]) == self.col_idx:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            data = event.mimeData().text()
            if data.startswith("item|"):
                parts = data.split("|")
                if len(parts) == 4 and int(parts[1]) == self.col_idx:
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

        if drag_col != self.col_idx:
            return

        drop_pos = event.position().toPoint()
        drop_idx = self._get_drop_index(drop_pos)

        if drag_cat == self.category_name:
            # Same-category reorder
            if drop_idx != drag_idx:
                self.app.handle_item_reorder(self.col_idx, self.category_name, drag_idx, drop_idx)
        else:
            # Cross-category move. If this zone is the Docs bucket's real category and it
            # doesn't exist on disk yet (see the construction-time resolve above, which
            # defaults to "Documentation" without creating it), create it now — this is a
            # direct result of the user's own drop action, not an incidental render side
            # effect, and without it handle_item_move_to_category() would silently lose the
            # item (it re-reads the config from disk and finds no destination category).
            if self.category_name in ("Documentation", "Docs") and not any(
                self.category_name in cd for cd in self.app.COLUMN_1
            ):
                self.category_name = self.app._ensure_documentation_category()
            self.app.handle_item_move_to_category(drag_cat, drag_idx, self.category_name, drop_idx)

        event.acceptProposedAction()

    def _get_drop_index(self, pos):
        """Determine which true item index the drop should insert at, based on Y position.

        Returns the real item_idx from self.item_widgets, not the loop position — those
        are the same thing when every item in the category is rendered (always true until
        Resources categories could have gaps, see _build_grouped_categories()'s
        self._grouped_hidden_item_ids), but diverge once some items are hidden. Returning
        the true index keeps handle_item_reorder()/handle_item_move_to_category() correct
        in both cases, since they already expect true indices."""
        for widget, item_idx in self.item_widgets:
            # If drop is above the widget's center, insert before it
            if pos.y() < widget.geometry().center().y():
                return item_idx
        return self.item_widgets[-1][1] + 1 if self.item_widgets else 0


class DragHandle(QLabel):
    """A visible ⠿ drag handle for reordering launcher items in edit mode"""

    def __init__(self, col_idx, category_name, item_idx, parent=None):
        super().__init__("⠿", parent)
        self.col_idx = col_idx
        self.category_name = category_name
        self.item_idx = item_idx
        self.drag_start_pos = None
        self.setFixedWidth(18)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag to reorder")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or not self.drag_start_pos:
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < 10:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(f"item|{self.col_idx}|{self.category_name}|{self.item_idx}")
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, event):
        self.drag_start_pos = None
        super().mouseReleaseEvent(event)


class ViewerResizeHandle(QLabel):
    """Thin bar at the bottom of the viewer column — drag vertically to resize it.

    Uses setFixedHeight(), not setMinimumHeight(): a minimum is only a floor, and on any
    project with a tall enough launcher column, the surrounding layout stretches column2_stack
    well past that floor anyway (to match the launcher column's height, since both sit in the
    same row) — making the drag have no visible effect, and pushing this handle far down the
    page. A fixed height opts column2_stack out of that stretching entirely: any extra vertical
    space from a tall launcher column is simply left blank below the handle instead, so the
    viewer's actual size always matches what was last dragged (or the viewer_height default),
    and the handle stays at a short, predictable scroll distance rather than however tall the
    launcher list happens to be. Unlike DragHandle above (drag-and-drop reordering), this tracks
    the mouse directly to live-resize target_widget rather than initiating a QDrag.
    """

    def __init__(self, target_widget, on_resize_end, parent=None):
        super().__init__("⋯⋯⋯", parent)
        self.target_widget = target_widget
        self.on_resize_end = on_resize_end
        self.setFixedHeight(10)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip("Drag to resize the viewer (remembered on this machine)")
        self._drag_start_y = None
        self._drag_start_height = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_y = event.globalPosition().y()
            self._drag_start_height = self.target_widget.height()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_y is None:
            return
        delta = event.globalPosition().y() - self._drag_start_y
        new_height = max(400, int(self._drag_start_height + delta))
        self.target_widget.setFixedHeight(new_height)

    def mouseReleaseEvent(self, event):
        if self._drag_start_y is not None:
            self._drag_start_y = None
            self.on_resize_end(self.target_widget.height())
        super().mouseReleaseEvent(event)


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


class FolderBrowserDelegate(QStyledItemDelegate):
    """Custom delegate to render folder items with a card-like border appearance"""

    def __init__(self, app_ref, parent=None):
        super().__init__(parent)
        self.app = app_ref

    def paint(self, painter, option, index):
        item_type = index.data(Qt.ItemDataRole.UserRole + 1)

        if item_type != "dir":
            super().paint(painter, option, index)
            return

        painter.save()

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if is_selected:
            bg_color = QColor(self.app.t('bg_category'))
            text_color = QColor(self.app.t('fg_on_dark'))
            border_color = QColor(self.app.t('bg_category'))
        elif is_hovered:
            bg_color = QColor(self.app.t('bg_button_hover'))
            text_color = QColor(self.app.t('fg_on_dark'))
            border_color = QColor(self.app.t('bg_navy'))
        else:
            bg_color = QColor(self.app.t('bg_button'))
            text_color = QColor(self.app.t('fg_primary'))
            border_color = QColor(self.app.t('border'))

        card_rect = option.rect.adjusted(6, 3, -6, -3)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(bg_color)
        painter.setPen(border_color)
        painter.drawRoundedRect(card_rect, 3, 3)

        # Draw icon if present
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        text_left = 10
        if icon and not icon.isNull():
            icon_size = 16
            icon_x = card_rect.left() + 8
            icon_y = card_rect.center().y() - icon_size // 2
            icon.paint(painter, QRect(icon_x, icon_y, icon_size, icon_size))
            text_left = 8 + icon_size + 4

        painter.setPen(text_color)
        font = option.font
        font.setPointSize(9)
        painter.setFont(font)
        display_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        painter.drawText(card_rect.adjusted(text_left, 0, -4, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         display_text)

        painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), hint.height() + 6)


class MuyaSession:
    """Bundles the state needed to run one Muya WYSIWYG markdown editor instance inside a
    QWebEngineView: which file it's editing, content pending injection once the page loads,
    and its own autosave timer. Lets independent Muya-hosting views (the main viewer, the
    Notes panel) share the same bridge logic (see the _muya_*/_open_path_in_muya_session
    methods on ProjectFlowApp) without stepping on each other's state."""

    def __init__(self, webview, autosave_interval_ms=1200):
        self.webview = webview
        self.editing = False
        self.path = None
        self.pending_markdown = None
        self.autosave_timer = QTimer()
        self.autosave_timer.setInterval(autosave_interval_ms)


class CodeEditorSession:
    """Bundles the state needed to run one CodeMirror 6 code-editor instance inside a
    QWebEngineView: which file it's editing, its language, content pending injection once
    the page loads, and a dirty-state poll timer used ONLY to refresh the Save button's
    UI indicator. Deliberately has NO autosave_timer field (unlike MuyaSession) — it's
    easier to fat-finger an unwanted keystroke into a code file than into prose, so this
    editor saves only via an explicit action (the Save button / Ctrl+S), never silently
    on a timer. Keeping the field itself absent, not just unused, is the guardrail against
    someone later wiring up autosave "for consistency" with Muya."""

    def __init__(self, webview, dirty_poll_interval_ms=800):
        self.webview = webview
        self.editing = False
        self.path = None
        self.language = None
        self.pending_content = None
        self.dirty = False
        # What session.dirty should become once pending_content actually finishes loading
        # (see _on_code_editor_webview_load_finished()) — plain 0/False for a fresh disk
        # read, but True when restoring an Editor tab that had cached unsaved content (see
        # CodeTabState/_activate_code_tab()): the freshly-loaded buffer is "clean" from
        # CodeMirror's own perspective (nothing changed since __initCodeEditor()), even
        # though the content itself differs from what's on disk, so the true dirty state
        # has to be supplied externally rather than trusted from the editor.
        self.pending_dirty = False
        self.dirty_poll_timer = QTimer()
        self.dirty_poll_timer.setInterval(dirty_poll_interval_ms)


class PdfTabState:
    """One open PDF tab: which file/URL, which page, and its PyMuPDF document object.

    Unlike MuyaSession/CodeEditorSession (which each wrap a persistent QWebEngineView —
    an expensive Chromium renderer process), a PDF tab is just a fitz.Document plus a couple
    of Python ints. The multi-instance-tabs exploration plan (see ai/ or the plan history)
    concluded PDF/Image are cheap enough that every open tab's document can just stay open
    for the tab's lifetime — no lazy-loading/tab-cap needed here, unlike the webview-backed
    viewer types. self.doc is None until _pdf_load_tab_doc() successfully opens it."""

    def __init__(self, path, page=0):
        self.path = path
        self.page = page
        self.doc = None
        self.page_count = 0


class ImageTabState:
    """One open Image tab: which file, and its loaded QPixmap. Mirrors PdfTabState — same
    "cheap enough to keep every tab's resource loaded" reasoning, just a QPixmap instead of
    a fitz.Document and no page concept."""

    def __init__(self, path):
        self.path = path
        self.pixmap = None


class WebTabState:
    """One open Web tab: a plain URL, a local HTML file, or a local markdown file (Muya
    editor) — `kind` distinguishes them since they need different QUrl construction
    (`QUrl(url)` vs `QUrl.fromLocalFile(path)`) and markdown needs the Muya bridge rather
    than a plain navigation. Unlike PdfTabState/ImageTabState, the underlying resource here
    (a QWebEngineView) is expensive — a real Chromium renderer process — so unlike PDF/Image,
    only ONE is ever kept live (the app's existing persistent self.webview): switching tabs
    re-navigates that single shared webview rather than creating one per tab. This is the
    simplest faithful reading of the "lazy tab" design from the multi-instance-tabs
    exploration plan — at most one instance of the expensive resource, ever, regardless of
    how many tabs are remembered."""

    def __init__(self, kind, value):
        self.kind = kind    # "url" | "html_file" | "markdown"
        self.value = value  # URL string, or local file path


class NotesTabState:
    """One open Notes tab (Focus layout only — see CLAUDE.md's Notes/webview consolidation
    notes). `path=None` means "this project's own note", mirroring the pre-tab
    `notes_md_path` convention exactly, so `_open_notes_in_muya()`'s existing dispatch logic
    needs no changes at all — it already does the right thing based on that same value.
    Like Web tabs, only the one persistent `self.notes_webview` is ever used; switching
    tabs re-navigates it rather than creating N of them."""

    def __init__(self, path=None):
        self.path = path


class CodeTabState:
    """One open Editor tab: a file path, its CodeMirror language key, and — critically —
    any UNSAVED content, cached here in Python memory (never written to disk) whenever
    switching away from this tab while it's dirty. This is what lets Editor tabs coexist
    with the code editor's deliberate no-autosave design: switching tabs must never force a
    save or a discard, so a dirty tab's in-progress edits are preserved until you switch
    back to it or explicitly save — see _activate_code_tab(). pending_unsaved_content and
    dirty are session-only, never persisted (see the multi-instance-tabs exploration
    notes) — only path/language are written to the project's config."""

    def __init__(self, path, language):
        self.path = path
        self.language = language
        self.pending_unsaved_content = None
        self.dirty = False


class TerminalTabState:
    """One open Terminal tab: a working directory, its own ttyd subprocess/port, and its
    own dedicated QWebEngineView. This is the one tab type that does NOT follow WebTabState's
    "one shared expensive resource, re-navigate on switch" model — a terminal tab's whole
    point is a real, independent, concurrently-running shell (a dev server, a tail -f, an
    SSH session), and killing that on every tab switch (as re-navigating a shared webview
    would require, since ttyd's process dies with its webview's navigation) would defeat the
    feature. Instead this mirrors PdfTabState/ImageTabState's "keep every open tab's resource
    alive for its lifetime" model — except the resource here (a real OS process + port) is
    genuinely expensive, hence the hard TERMINAL_TAB_CAP. webview/proc/port/ready are
    runtime-only and never persisted (see save_notes()) — only cwd is meaningful across an
    app restart, since a running shell's live state can't be resumed regardless."""

    def __init__(self, cwd):
        self.cwd = cwd          # normalized (expanduser'd) working directory
        self.webview = None     # QWebEngineView, created when the tab is first spawned
        self.proc = None        # subprocess.Popen (ttyd), None until spawned
        self.port = None
        self.ready = False      # mirrors the old singleton's _console_ttyd_ready, per-tab now


class LinkOpeningWebPage(QWebEnginePage):
    """QWebEnginePage subclass whose sole job is implementing createWindow() — the hook
    Chromium calls whenever the user picks "Open link in new tab" / "Open link in new
    window" from the page's own right-click context menu (also middle-click and Ctrl-click
    on a link, and JS `window.open()`). QWebEnginePage.createWindow() returns None by
    default, which is exactly why those context-menu items looked broken: Chromium asked
    for a new page to load the link into, got nothing back, and silently dropped the
    navigation — nothing to do with the app's own tab strip at all.

    This app's Web viewer has exactly one real QWebEngineView, not one per tab (see
    WebTabState) — "new tab"/"new window" from a link should still open into that same
    shared viewer as a genuine new WebTabState, not spawn a second on-screen Chromium
    view. So createWindow() hands back a throwaway, unparented QWebEnginePage on the same
    profile purely to let Chromium tell us the destination URL (the first real, non-blank
    urlChanged it fires after we return), then forwards that URL to `open_url_callback`
    (bound to `_open_web_tab('url', ...)`) and discards the throwaway page. A 5s safety
    timer force-cleans the throwaway page if no real navigation ever arrives, so a popup
    that never actually navigates (rare, but JS can do it) can't leak it forever."""

    def __init__(self, profile, parent, open_url_callback):
        super().__init__(profile, parent)
        self._open_url_callback = open_url_callback

    def createWindow(self, window_type):
        temp_page = QWebEnginePage(self.profile(), None)
        state = {"done": False}

        def _finish(url=None):
            if state["done"]:
                return
            state["done"] = True
            try:
                temp_page.urlChanged.disconnect(_on_url_changed)
            except Exception:
                pass
            if url:
                self._open_url_callback(url)
            temp_page.deleteLater()

        def _on_url_changed(url):
            target = url.toString()
            if target and target != "about:blank":
                _finish(target)

        temp_page.urlChanged.connect(_on_url_changed)
        QTimer.singleShot(5000, lambda: _finish(None))
        return temp_page


class ProjectFlowApp(QMainWindow):
    def __init__(self, config_file_arg=None):
        super().__init__()
        self.config = {}
        self.config_file_arg = config_file_arg  # Store CLI argument
        self.edit_mode = False  # Track whether we're in edit mode
        self._pre_fullscreen_state = Qt.WindowState.WindowMaximized  # matches actual startup state (showMaximized())
        self._zen_mode = False  # collapses launcher/notepad columns to focus the active viewer (see toggle_zen_mode)
        # Create the webview here, before init_ui() ever runs, so it's bound to a
        # profile configured while the app name is still the stable "ProjectFlow" —
        # not the per-project "ProjectFlow-{name}" set in init_ui().
        #
        # QWebEngineProfile.defaultProfile() is *permanently* off-the-record in this
        # Qt/PyQt6 build (isOffTheRecord() == True, confirmed empirically with a
        # standalone probe script) — no amount of setPersistentStoragePath() /
        # setCachePath() / setPersistentCookiesPolicy() calls on it ever actually
        # persists anything to disk. The path/cache-type getters faithfully echo
        # back whatever was set, but Chromium still backs the profile with
        # memory-only storage (httpCacheType stays MemoryHttpCache, cookies stay
        # NoPersistentCookies-equivalent regardless of the policy set) since it has
        # no storage name — that's what makes a profile off-the-record. This was
        # the real reason logins never survived an app restart even after the
        # 2026-08-25 storage-path fix (see CHANGELOG) — that fix pinned a path on a
        # profile that was never going to write to disk. The actual fix is a
        # *named* QWebEngineProfile: self.web_profile, explicitly assigned to
        # self.webview/self.notes_webview via setPage() below, since a plain
        # QWebEngineView() always binds itself to defaultProfile() otherwise.
        webengine_profile_dir = os.path.expanduser("~/.local/share/ProjectFlow/webengine-profile")
        os.makedirs(webengine_profile_dir, exist_ok=True)
        self.web_profile = QWebEngineProfile("projectflow", self)
        self.web_profile.setPersistentStoragePath(webengine_profile_dir)
        self.web_profile.setCachePath(os.path.join(webengine_profile_dir, "cache"))
        self.web_profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )

        self.webview = QWebEngineView()
        # LinkOpeningWebPage (not a plain QWebEnginePage) so right-click "Open link in new
        # tab"/"new window" actually does something — see that class's docstring. Routes
        # into this app's own Web-tab system (_open_web_tab()) rather than a second
        # on-screen browser view.
        self.webview.setPage(LinkOpeningWebPage(self.web_profile, self.webview, self._open_link_in_new_web_tab))
        self.webview.urlChanged.connect(self.on_webview_url_changed)
        self._enable_web_fullscreen_support(self.webview)

        # Muya markdown-editor session for the main viewer (see _open_markdown_in_muya_editor,
        # MuyaSession, and the shared _muya_*/_open_path_in_muya_session bridge methods).
        self._muya_session = MuyaSession(self.webview)
        self.webview.loadFinished.connect(
            lambda ok: self._on_muya_webview_load_finished(ok, self._muya_session)
        )
        self._muya_session.autosave_timer.timeout.connect(
            lambda: self._muya_autosave_tick(self._muya_session)
        )

        # Second, independent Muya-hosting webview dedicated to the Notes panel — created here
        # (not in build_main_content()) and never recreated on refresh, for the same reason as
        # self.webview: QWebEngineView breaks if moved via incremental setParent(None) after
        # being shown, so it must follow the "detach to self before central-widget teardown,
        # re-add during build_main_content()" pattern in init_ui() (see notes_webview.setParent
        # there) rather than the notes_panel-style reparenting used elsewhere in Focus/Standard
        # layout switching.
        self.notes_webview = QWebEngineView()
        self.notes_webview.setPage(QWebEnginePage(self.web_profile, self.notes_webview))
        self._enable_web_fullscreen_support(self.notes_webview)
        self._notes_muya_session = MuyaSession(self.notes_webview)
        self.notes_webview.loadFinished.connect(
            lambda ok: self._on_muya_webview_load_finished(ok, self._notes_muya_session)
        )
        self._notes_muya_session.autosave_timer.timeout.connect(
            lambda: self._muya_autosave_tick(self._notes_muya_session)
        )
        # Tracks an explicitly-opened non-project note in the Focus-layout Notes tab (see
        # _open_note_in_notes_tab()/_open_markdown_file()) — None means "show the project's
        # own note". Deliberately NOT reset in load_notes() (which reruns on every incidental
        # refresh — editing a launcher, toggling theme — and would otherwise wipe this the
        # same way load_notes() already wipes webview_md_path, a known "gotcha" documented
        # for toggle_theme() elsewhere). Only switch_to_config() resets it, since only an
        # actual project switch should fall back to the (new) project's own note.
        self.notes_md_path = None
        # Multi-instance Notes tabs (see NotesTabState) — self.notes_tabs/notes_active_index
        # are the source of truth, rebuilt from disk in load_notes() on every refresh (cheap:
        # unlike PDF/Image tabs, a NotesTabState holds no attached resource, just a path).
        # notes_md_path above remains the active-tab proxy for _open_notes_in_muya() to keep
        # working unchanged.
        self.notes_tabs = []
        self.notes_active_index = -1

        # Multi-instance Terminal tabs (see TerminalTabState) — one ttyd subprocess + one
        # dedicated QWebEngineView PER tab (unlike Web/Notes, which share a single persistent
        # webview), because a terminal tab's whole point is a real, independent, concurrently-
        # running shell. self.terminal_tabs/terminal_active_index are the source of truth;
        # TERMINAL_TAB_CAP (class attribute, defined near the terminal tab methods) bounds how
        # many can be open at once — at the cap, opening another is refused outright (no
        # silent eviction) since a background tab may have a real process running in it.
        self.terminal_tabs = []
        self.terminal_active_index = -1
        self._console_active_webview = None  # which tab's webview is currently in console_container_layout

        # Fourth persistent webview, dedicated to the internal CodeMirror 6 code-editor
        # (see CodeEditorSession, _open_code_file_in_editor, and the _code_editor_*/
        # _load_code_editor_shell bridge methods). Same "never recreated on refresh,
        # detach-then-readd" pattern as notes_webview/terminal tab webviews above. No
        # autosave_timer to wire up here — see CodeEditorSession's docstring for why.
        self.code_webview = QWebEngineView()
        self._enable_web_fullscreen_support(self.code_webview)
        self._code_session = CodeEditorSession(self.code_webview)
        self.code_webview.loadFinished.connect(
            lambda ok: self._on_code_editor_webview_load_finished(ok, self._code_session)
        )
        self._code_session.dirty_poll_timer.timeout.connect(
            lambda: self._code_editor_dirty_poll_tick(self._code_session)
        )
        # Multi-instance Editor tabs (see CodeTabState) — restored only on an actual
        # project switch (load_config()'s is_project_switch block), NOT on every incidental
        # refresh, since pending_unsaved_content must survive those (mirrors why
        # notes_md_path isn't reset in load_notes() either).
        self.code_tabs = []
        self.code_active_index = -1

        # Debounce timer for alias file writes — prevents a write per keystroke
        # when the user types in the inline path/app fields.
        self._pending_alias_write = None
        self._alias_write_timer = QTimer()
        self._alias_write_timer.setSingleShot(True)
        self._alias_write_timer.setInterval(800)
        self._alias_write_timer.timeout.connect(self._flush_pending_alias_write)

        # Get the directory where this script is located
        self.script_dir = os.path.dirname(os.path.abspath(__file__))

        # Settings file to store user preferences (machine-specific, not synced)
        self.settings_file = os.path.join(self.script_dir, ".projectflow_settings.json")

        # Load settings (like which config to use)
        self.load_settings()

        # Layout mode: "standard" (3-col) or "focus" (2-col with notes as viewer tab).
        # Per-project — load_config() overrides this once the active project's config is read.
        self.layout_mode = "standard"

        # Dynamic Group-by-Type launcher view (Docs/Resources) — display-only, never
        # rewrites the project's category structure. See _build_grouped_categories.
        # Standard layout only — Focus layout uses active_launcher_tab instead (below).
        self.group_by_type = False
        self._group_view_origin = {}

        # Focus-layout launcher column tab: "files" (Quick File Browser Panel) / "docs" /
        # "resources" / "apps" (per-project curated app grid, see _build_apps_tab_items).
        # Per-project — load_config() overrides this once the active project's config is read.
        self.active_launcher_tab = "files"

        # Folder browser view mode: "tree" (details) or "icons" (Dolphin-style grid) — per-machine preference
        self.folder_view_mode = self.settings.get("folder_view_mode", "tree")

        # Folder browser filter text (Dolphin-style filter bar) — session-only, shared across
        # every folder-browsing surface (main viewer + launcher panel) since they always show
        # the same self.folder_current_path in sync.
        self.folder_filter_text = ""

        # True when self.folder_current_path was reached via the path-mapping fallback (see
        # _resolve_existing_path()) rather than existing directly — drives the pale-blue path
        # label styling in populate_folder_browser() so it's visually obvious you're looking
        # at a mapped/substitute folder, not the one actually saved in the project.
        self.folder_via_mapping = False

        # MIGRATION (temporary): rename archive files to {name}-archive.md format
        self._migrate_archive_filenames()

        # Initialize theme and dimensions (after settings loaded)
        self.init_theme()
        self.init_dimensions()
        self.apply_global_styles()

        # Persistent Project Settings form (see _build_settings_form()) — the Settings
        # viewer (column2_mode == "settings") replaced what used to be a modal dialog.
        # Built once here (needs self.t()/theme, hence after apply_global_styles() above)
        # and reused across every build_main_content() rebuild, like notes_webview/
        # code_webview, rather than recreated fresh each time. self._settings_loaded_for
        # tracks which project's values are currently loaded into it; None forces the next
        # visit to (re)populate — see _populate_settings_form().
        self._build_settings_form()
        self._settings_loaded_for = None

        # Setup first run (copy examples if needed)
        self.setup_first_run()

        # Install .desktop file for GNOME/COSMIC dock icon support
        self.ensure_desktop_file_installed()

        # Determine which config file to use
        self.current_config_file = self.get_config_file_to_use()

        # Persist initial config as last_used so "Last opened project" startup mode works
        self.settings["last_used_project"] = self.current_config_file

        # Add to recent projects (also calls save_settings)
        self.add_to_recent_projects(self.current_config_file)

        self.load_config()
        self.load_notes()
        self.load_launch_handlers()
        self.init_ui()

    def resizeEvent(self, event):
        """Handle window resize"""
        super().resizeEvent(event)
        # Zone 1 (pinned projects row, see _populate_pinned_projects) doesn't reliably receive
        # its own resize events — it's deliberately sized to content with a trailing stretch so
        # pins stay left-aligned rather than stretching to fill, which means its own width
        # rarely changes even as the window does. Force a reflow off the window's resize
        # instead, so it can't get stuck at a stale/narrow cell width.
        #
        # This is a genuine cross-object reach (QMainWindow reaching into a widget owned by
        # a completely separate rebuild cycle), unlike every other resizeEvent/showEvent in
        # this file which only ever touches its own children — so it's the one place a real
        # window resize (confirmed via a crash report: rapid F11/Ctrl+F11 toggling, landing
        # exactly on the native resize fired when Wayland applies the exit-fullscreen
        # configure) can race a refresh_projects()/build_main_content() rebuild: this line
        # can run at a moment where self.config_bar_widget still points at the previous
        # rebuild's ConfigBarWidget (or its _reflow_fn closure still holds that rebuild's now-
        # destroyed button containers) because the attribute hasn't been reassigned to the new
        # instance yet. Reading/calling into an already-deleted PyQt-wrapped C++ object raises
        # RuntimeError, and PyQt6 calls abort() on any exception that escapes an overridden
        # virtual method uncaught (see the identical guard/rationale on _set_viewer_placeholder's
        # apply_fit()) — which is exactly the "fatal error" crash this guards against.
        try:
            config_bar_widget = getattr(self, 'config_bar_widget', None)
            reflow_fn = getattr(config_bar_widget, '_reflow_fn', None) if config_bar_widget else None
            if reflow_fn:
                reflow_fn(config_bar_widget.width())
        except RuntimeError:
            pass

    def closeEvent(self, event):
        """Handle window close — confirm discarding unsaved code-editor changes first (the
        one thing in this app with no autosave, see CodeEditorSession), then terminate every
        open terminal tab's ttyd subprocess.

        Unlike every other subprocess this app spawns (external terminal/editor/file-manager
        launches, always started with start_new_session=True so they outlive the app), a ttyd
        console is an internal implementation detail: it must die with the app, not survive
        it, or every session leaves an orphaned process + open port behind — now one per open
        terminal tab (see TerminalTabState) rather than just one, so this loop is the single
        highest-risk line to get right when the app has several tabs open.
        """
        if not self._confirm_discard_code_changes():
            event.ignore()
            return
        for _terminal_tab in self.terminal_tabs:
            self._stop_terminal_tab(_terminal_tab)
        super().closeEvent(event)

    def keyPressEvent(self, event):
        """Escape exits fullscreen — only reached when no focused child widget already
        consumed the key (ClickableSearchTitle's own "Escape cancels search" and any open
        QDialog's "Escape closes dialog" both still take precedence, exactly as before this
        was added; this is purely a fallback for when nothing else wants Escape)."""
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)

    def toggle_fullscreen(self):
        """F11 toggle. Uses the windowState() bitmask (rather than showNormal()/
        showMaximized() guessing) so the exact prior state — maximized or not — is restored
        on exit. Also the landing point for web content's own HTML5 fullscreen requests
        (see _on_web_fullscreen_requested) so both paths share one consistent notion of
        "the app is fullscreen"."""
        if self.isFullScreen():
            self.setWindowState(self._pre_fullscreen_state)
            self.set_status("")
        else:
            self._pre_fullscreen_state = self.windowState()
            self.setWindowState(self.windowState() | Qt.WindowState.WindowFullScreen)
            self.set_status("Fullscreen — press F11 or Esc to exit", "info")

    def _apply_zen_mode(self):
        """Collapse the launcher/notepad columns so column2_widget fills the splitter.
        Idempotent — safe to call after every rebuild, since launcher_widget/
        notepad_column_widget/columns_splitter are recreated fresh by every
        build_main_content() call and don't retain this collapsed state on their own (see
        init_ui()'s reapplication call, mirroring how _enter_focus_layout() is similarly
        re-invoked after every rebuild for the same reason).

        setMinimumWidth(0) alone (the mechanism _enter_focus_layout() uses for the empty-in-
        Focus-layout notepad_column_widget) is NOT enough here: Qt's splitter sizing falls
        back to a widget's *minimumSizeHint()* (computed from its own layout's real content)
        whenever minimumSize() is (0, 0) — confirmed empirically, a plain setMinimumWidth(0)
        on launcher_widget (which always has real buttons) left it stuck around 300+px instead
        of 0. setMaximumWidth(0) has no such content-based fallback (there's no
        "maximumSizeHint" — the explicit maximum always wins), so it's what actually forces
        the collapse for widgets with real content."""
        if not hasattr(self, 'columns_splitter') or not hasattr(self, 'launcher_widget'):
            return
        self.launcher_widget.setMinimumWidth(0)
        self.launcher_widget.setMaximumWidth(0)
        if self.layout_mode != "focus":
            self.notepad_column_widget.setMinimumWidth(0)
            self.notepad_column_widget.setMaximumWidth(0)
        sizes = [0] * self.columns_splitter.count()
        sizes[self.columns_splitter.indexOf(self.column2_widget)] = (
            sum(self.columns_splitter.sizes()) or 1000
        )
        self.columns_splitter.setSizes(sizes)

    def toggle_zen_mode(self):
        """Ctrl+F11 toggle. Orthogonal to toggle_fullscreen()/window chrome — this only
        collapses the launcher/notepad columns so the active viewer fills the splitter.
        Deliberately not wired into keyPressEvent()'s Escape handling: zen mode still leaves
        the OS title bar/taskbar/borders visible, so there's no "stuck" scenario the way true
        fullscreen has, and overloading Escape with a second meaning could surprise someone
        pressing it for an unrelated reason while zen mode happens to be on."""
        if self._zen_mode:
            self._zen_mode = False
            self.launcher_widget.setMinimumWidth(150)
            self.launcher_widget.setMaximumWidth(QWIDGETSIZE_MAX)
            if self.layout_mode != "focus":
                self.notepad_column_widget.setMinimumWidth(150)
                self.notepad_column_widget.setMaximumWidth(QWIDGETSIZE_MAX)
            self.columns_splitter.setSizes(getattr(self, '_pre_zen_sizes', None) or [1, 1, 1])
            self.set_status("")
        else:
            self._pre_zen_sizes = self.columns_splitter.sizes()
            self._zen_mode = True
            self._apply_zen_mode()
            self.set_status("Zen mode — press Ctrl+F11 to restore panels", "info")

    def _enable_web_fullscreen_support(self, view):
        """Wire a QWebEngineView up to drive the app's own fullscreen state when embedded
        content (e.g. a video) requests HTML5 fullscreen. Escape-to-exit needs no extra
        plumbing here: Chromium already implements Escape-to-exit-fullscreen per the HTML5
        Fullscreen API spec internally, and will simply re-fire fullScreenRequested with
        toggleOn=False on its own, which this same handler folds back out of fullscreen."""
        view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True
        )
        view.page().fullScreenRequested.connect(self._on_web_fullscreen_requested)

    def _on_web_fullscreen_requested(self, request):
        request.accept()
        if request.toggleOn() and not self.isFullScreen():
            self.toggle_fullscreen()
        elif not request.toggleOn() and self.isFullScreen():
            self.toggle_fullscreen()

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
                    "folder_projects": [],  # List of .projectflow configs from folders
                    "enable_baloo_tags": False,  # Query Baloo for tagged files (KDE only)
                    "swap_launcher_viewer": False,  # Swap launcher and viewer column positions
                    "fm_always_tabs": False,  # Open file manager with home tab + target tab
                    "color_order": [],  # user-ordered list of color hex strings for swatch priority
                    "folder_view_mode": "tree",  # Folder browser view: "tree" or "icons"
                }
                self.save_settings()
        except Exception as e:
            print(f"Error loading settings: {e}")
            self.settings = {
                "default_project": None,
                "projects_directory": "projects",
                "last_used_project": None,
                "recent_projects": [],
                "folder_projects": [],
                "enable_baloo_tags": False,
                "swap_launcher_viewer": False,
            }

        # Layout: Viewer column is always first (left)
        self.swap_columns = True

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
        # The general Muya markdown viewer (_open_markdown_in_muya_editor) isn't covered by
        # refresh_projects()'s automatic per-theme reload — that mechanism only exists for the
        # dedicated Notes session (see notes_reload_key in build_main_content()). Its webview
        # base URL points at assets/muya/, not the .md file itself, so the existing "restore
        # webview_url on refresh" path never recognizes it as markdown and never re-fires —
        # and refresh_projects() (via load_notes()) unconditionally clears webview_md_path
        # regardless, so it must be captured here, before that happens, not read afterward.
        reopen_md_path = None
        if getattr(self, '_muya_session', None) and self._muya_session.editing and self.webview_md_path:
            reopen_md_path = self.webview_md_path

        if self.current_theme == "light":
            self.current_theme = "dark"
        else:
            self.current_theme = "light"
        self.settings["theme"] = self.current_theme
        self.save_settings()
        self.theme = get_theme(self.current_theme)
        self.apply_global_styles()
        self.refresh_projects()

        if reopen_md_path:
            self._open_markdown_in_muya_editor(reopen_md_path)

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
        applications_tab = self._create_applications_tab()
        integrations_tab = self._create_integrations_tab()
        icons_tab = self._create_icons_tab()
        handlers_tab = self._create_handlers_tab()

        tabs.addTab(settings_tab, "Settings")
        tabs.addTab(applications_tab, "Applications")
        tabs.addTab(integrations_tab, "Integrations")
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
        """Create the main Settings tab (theme, startup, launcher defaults, notes, projects layout)"""
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

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

        # Actions (top)
        actions_label = QLabel("Actions:")
        actions_label.setStyleSheet(label_style)
        actions_layout = QHBoxLayout()

        upgrade_btn = QPushButton("✨ Check for Updates")
        upgrade_btn.setStyleSheet(action_btn_style)
        upgrade_btn.setToolTip("Check for updates and upgrade")
        upgrade_btn.clicked.connect(self.check_for_upgrade)
        actions_layout.addWidget(upgrade_btn)

        if self.detect_desktop_environment() == 'kde':
            servicemenu_btn = QPushButton("Install Dolphin Service Menu")
            servicemenu_btn.setStyleSheet(action_btn_style)
            servicemenu_btn.setToolTip("Install 'Add to ProjectFlow' right-click menu in Dolphin")
            servicemenu_btn.clicked.connect(self.install_kde_servicemenu)
            actions_layout.addWidget(servicemenu_btn)

        scan_aliases_btn = QPushButton("🔍 Scan Projects for Aliases")
        scan_aliases_btn.setStyleSheet(action_btn_style)
        scan_aliases_btn.setToolTip("Scan all project files for alias launchers and update projectflow_aliases")
        scan_aliases_btn.clicked.connect(lambda: self._do_alias_scan())
        actions_layout.addWidget(scan_aliases_btn)

        actions_layout.addStretch()
        layout.addRow(actions_label, actions_layout)

        layout.addRow(QLabel(""))

        # Theme
        theme_label = QLabel("Theme:")
        theme_label.setStyleSheet(label_style)
        self._settings_theme_combo = QComboBox()
        self._settings_theme_combo.addItems(["system", "light", "dark"])
        self._settings_theme_combo.setCurrentText(self.settings.get("theme", "system"))
        self._settings_theme_combo.setStyleSheet(input_style)
        layout.addRow(theme_label, self._settings_theme_combo)

        # Startup
        startup_label = QLabel("Startup:")
        startup_label.setStyleSheet(label_style)
        startup_outer = QHBoxLayout()
        startup_outer.setSpacing(6)

        self._settings_startup_mode = QComboBox()
        self._settings_startup_mode.addItems(["Last opened project", "Main project", "Specific project"])
        _mode_map = {"last_used": "Last opened project", "main": "Main project", "specific": "Specific project"}
        self._settings_startup_mode.setCurrentText(
            _mode_map.get(self.settings.get("startup_mode", "last_used"), "Last opened project")
        )
        self._settings_startup_mode.setStyleSheet(input_style)
        startup_outer.addWidget(self._settings_startup_mode)

        self._settings_startup_project = QComboBox()
        self._settings_startup_project.setStyleSheet(input_style)
        self._settings_startup_project.setMinimumWidth(160)
        _configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        if os.path.isdir(_configs_dir):
            for _p in sorted(f for f in os.listdir(_configs_dir) if f.endswith('.json') and not f.startswith('.')):
                self._settings_startup_project.addItem(
                    os.path.splitext(_p)[0].replace('_', ' ').replace('-', ' ').title(),
                    os.path.join(_configs_dir, _p)
                )
        _saved_specific = self.settings.get("startup_project", "")
        for i in range(self._settings_startup_project.count()):
            if self._settings_startup_project.itemData(i) == _saved_specific:
                self._settings_startup_project.setCurrentIndex(i)
                break
        self._settings_startup_project.setEnabled(
            self._settings_startup_mode.currentText() == "Specific project"
        )
        self._settings_startup_mode.currentTextChanged.connect(
            lambda t: self._settings_startup_project.setEnabled(t == "Specific project")
        )
        startup_outer.addWidget(self._settings_startup_project)
        layout.addRow(startup_label, startup_outer)

        # Default Launcher
        default_app_label = QLabel("Default Launcher:")
        default_app_label.setStyleSheet(label_style)
        self._settings_default_app = QComboBox()
        self._settings_default_app.setEditable(True)
        app_keys = sorted(self.APP_INFO.keys()) if hasattr(self, 'APP_INFO') else []
        self._settings_default_app.addItems([""] + app_keys)
        current_default_app = self.settings.get("default_app", "")
        idx = self._settings_default_app.findText(current_default_app)
        if idx >= 0:
            self._settings_default_app.setCurrentIndex(idx)
        else:
            self._settings_default_app.setCurrentText(current_default_app)
        self._settings_default_app.setStyleSheet(input_style)
        self._settings_default_app.setToolTip("Default application pre-selected when adding a new launcher (empty = first alphabetically)")
        default_app_row = QHBoxLayout()
        default_app_row.addWidget(self._settings_default_app)
        hint_label = QLabel("Pre-selected when adding new launchers")
        hint_label.setStyleSheet(f"color: {self.t('fg_muted')}; font-size: 11px;")
        default_app_row.addWidget(hint_label)
        layout.addRow(default_app_label, default_app_row)

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

        # Projects per row
        spinbox_style = f"""
            QSpinBox {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 6px;
                min-height: 20px;
            }}
        """
        per_row_label = QLabel("Projects per row:")
        per_row_label.setStyleSheet(label_style)
        self._settings_projects_per_row = QSpinBox()
        self._settings_projects_per_row.setRange(3, 20)
        self._settings_projects_per_row.setValue(self.settings.get("projects_per_row", 10))
        self._settings_projects_per_row.setToolTip("Number of project buttons per row in all list views (default: 10)")
        self._settings_projects_per_row.setStyleSheet(spinbox_style)
        layout.addRow(per_row_label, self._settings_projects_per_row)

        spacing_label = QLabel("Button spacing:")
        spacing_label.setStyleSheet(label_style)
        self._settings_projects_spacing = QSpinBox()
        self._settings_projects_spacing.setRange(2, 15)
        self._settings_projects_spacing.setValue(self.settings.get("projects_spacing", 5))
        self._settings_projects_spacing.setToolTip("Horizontal gap between project buttons in pixels (default: 5)")
        self._settings_projects_spacing.setStyleSheet(spinbox_style)
        layout.addRow(spacing_label, self._settings_projects_spacing)

        # Path Mappings
        mappings_label = QLabel("Path Mappings:")
        mappings_label.setStyleSheet(label_style)
        mappings_label.setToolTip(
            "Remap path prefixes when switching machines (e.g. a folder mounted at a\n"
            "different location here than where it was originally saved from)."
        )
        mappings_outer = QVBoxLayout()
        mappings_outer.setSpacing(4)

        self._path_mappings_table = QTableWidget()
        self._path_mappings_table.setColumnCount(2)
        self._path_mappings_table.setHorizontalHeaderLabels(["From (local path)", "To (remote/mounted path)"])
        self._path_mappings_table.horizontalHeader().setStretchLastSection(True)
        self._path_mappings_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._path_mappings_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._path_mappings_table.setAlternatingRowColors(True)
        self._path_mappings_table.setMinimumHeight(90)
        self._path_mappings_table.setMaximumHeight(140)
        self._path_mappings_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                gridline-color: {self.t('border')};
            }}
            QHeaderView::section {{
                background-color: {self.t('bg_panel')};
                color: {self.t('fg_on_dark')};
                padding: 4px;
                border: none;
                font-size: 11px;
            }}
            QTableWidget::item:selected {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
            }}
            QTableWidget::item:alternate {{
                background-color: {self.t('bg_primary')};
            }}
        """)
        for m in self.settings.get('path_mappings', []):
            row = self._path_mappings_table.rowCount()
            self._path_mappings_table.insertRow(row)
            self._path_mappings_table.setItem(row, 0, QTableWidgetItem(m.get('from', '')))
            self._path_mappings_table.setItem(row, 1, QTableWidgetItem(m.get('to', '')))
        mappings_outer.addWidget(self._path_mappings_table)

        mappings_btn_layout = QHBoxLayout()
        add_mapping_btn = QPushButton("+ Add")
        add_mapping_btn.setStyleSheet(action_btn_style)
        add_mapping_btn.clicked.connect(self._add_path_mapping_row)
        remove_mapping_btn = QPushButton("Remove Selected")
        remove_mapping_btn.setStyleSheet(action_btn_style)
        remove_mapping_btn.clicked.connect(self._remove_path_mapping_row)
        mappings_btn_layout.addWidget(add_mapping_btn)
        mappings_btn_layout.addWidget(remove_mapping_btn)
        mappings_btn_layout.addStretch()
        mappings_outer.addLayout(mappings_btn_layout)

        mappings_desc = QLabel(
            "Applied automatically as a fallback, only when a saved folder or launcher path "
            "isn't found on this machine — e.g. a project folder saved as ~/Public/key that's "
            "only reachable here as ~/gtr7/Public/key. The original path is never changed; "
            "when a mapping is used, the folder browser's path shows in pale blue to make it "
            "clear you're viewing a mapped location, not the one actually saved in the project."
        )
        mappings_desc.setWordWrap(True)
        mappings_desc.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 11px;")
        mappings_outer.addWidget(mappings_desc)

        layout.addRow(mappings_label, mappings_outer)

        return widget

    def _create_applications_tab(self):
        """Create the Applications tab (external apps used by launchers and viewers)"""
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

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
        self._settings_terminal.setEditable(True)
        self._settings_terminal.addItems([
            "", "konsole", "gnome-terminal", "alacritty", "kitty", "wezterm",
            "terminator", "tilix", "xfce4-terminal", "guake", "tilda",
            "foot", "ghostty", "warp-terminal", "hyper", "tabby", "urxvt", "xterm"
        ])
        current_terminal = self.settings.get("terminal", "")
        idx = self._settings_terminal.findText(current_terminal)
        if idx >= 0:
            self._settings_terminal.setCurrentIndex(idx)
        else:
            self._settings_terminal.setCurrentText(current_terminal)
        self._settings_terminal.setStyleSheet(input_style)
        self._settings_terminal.setToolTip(
            f"Terminal used for handlers. Leave empty to auto-detect (currently: {self.detect_default_terminal()})"
        )
        layout.addRow(terminal_label, self._settings_terminal)

        # Code Editor
        editor_label = QLabel("Code Editor:")
        editor_label.setStyleSheet(label_style)
        self._settings_editor = QComboBox()
        self._settings_editor.setEditable(True)
        self._settings_editor.addItems([
            "", "code", "codium", "kate", "gedit", "mousepad", "pluma", "xed",
            "featherpad", "leafpad", "geany", "sublime", "atom",
            "vim", "nvim", "emacs", "nano"
        ])
        current_editor = self.settings.get("editor", "")
        idx = self._settings_editor.findText(current_editor)
        if idx >= 0:
            self._settings_editor.setCurrentIndex(idx)
        else:
            self._settings_editor.setCurrentText(current_editor)
        self._settings_editor.setStyleSheet(input_style)
        self._settings_editor.setToolTip(
            f"Editor for directorydev handler. Leave empty to auto-detect (currently: {self.detect_default_editor()})"
        )
        layout.addRow(editor_label, self._settings_editor)

        # File Manager
        fm_label = QLabel("File Manager:")
        fm_label.setStyleSheet(label_style)
        self._settings_file_manager = QComboBox()
        self._settings_file_manager.setEditable(True)
        self._settings_file_manager.addItems([
            "", "dolphin", "nautilus", "thunar", "nemo", "caja",
            "pcmanfm", "pcmanfm-qt", "cosmic-files"
        ])
        current_fm = self.settings.get("file_manager", "")
        idx = self._settings_file_manager.findText(current_fm)
        if idx >= 0:
            self._settings_file_manager.setCurrentIndex(idx)
        else:
            self._settings_file_manager.setCurrentText(current_fm)
        self._settings_file_manager.setStyleSheet(input_style)
        self._settings_file_manager.setToolTip(
            f"File manager for directorydev handler. Leave empty to auto-detect (currently: {self.detect_default_file_manager()})"
        )
        layout.addRow(fm_label, self._settings_file_manager)

        # Console Backend
        console_backend_label = QLabel("Console Backend:")
        console_backend_label.setStyleSheet(label_style)
        self._settings_console_backend = QComboBox()
        self._settings_console_backend.addItem("Jupyter qtconsole (default)", "qtconsole")
        self._settings_console_backend.addItem("Real terminal via ttyd", "ttyd")
        self._settings_console_backend.addItem("Auto (ttyd if installed, else qtconsole)", "auto")
        current_backend = self.settings.get("console_backend", "qtconsole")
        idx = self._settings_console_backend.findData(current_backend)
        self._settings_console_backend.setCurrentIndex(idx if idx >= 0 else 0)
        self._settings_console_backend.setStyleSheet(input_style)
        self._settings_console_backend.setToolTip(
            "qtconsole runs Python/IPython in-process — no interactive programs (nano, vim, htop).\n"
            "ttyd embeds a real terminal (requires the 'ttyd' binary on PATH) with full PTY support,\n"
            "bound to 127.0.0.1 only."
        )
        layout.addRow(console_backend_label, self._settings_console_backend)

        # File Manager Tabs
        fm_tabs_label = QLabel("File Manager Tabs:")
        fm_tabs_label.setStyleSheet(label_style)
        self._settings_fm_always_tabs = QCheckBox("Always open with home folder as first tab")
        self._settings_fm_always_tabs.setChecked(self.settings.get("fm_always_tabs", False))
        self._settings_fm_always_tabs.setStyleSheet(f"color: {self.t('fg_primary')};")
        self._settings_fm_always_tabs.setToolTip(
            "When enabled, opening a folder in the file manager adds ~/\n"
            "as a first tab so you always have home + target open together."
        )
        layout.addRow(fm_tabs_label, self._settings_fm_always_tabs)

        # Browser Links
        browser_label = QLabel("Browser Links:")
        browser_label.setStyleSheet(label_style)
        self._settings_browser_new_tab = QCheckBox("Open links in new tab (uncheck for new window)")
        self._settings_browser_new_tab.setChecked(self.settings.get('browser_new_tab', True))
        self._settings_browser_new_tab.setStyleSheet(f"color: {self.t('fg_primary')};")
        layout.addRow(browser_label, self._settings_browser_new_tab)

        return widget

    def _create_integrations_tab(self):
        """Create the Integrations tab (Kimai, Joplin)"""
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        input_style = f"""
            QLineEdit {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 6px;
                min-height: 20px;
            }}
            QLineEdit:focus {{
                border-color: {self.t('bg_category')};
            }}
        """
        label_style = f"color: {self.t('fg_primary')}; font-size: 13px;"
        section_style = f"color: {self.t('fg_primary')}; font-weight: bold; font-size: 13px; padding-top: 8px;"

        # === Kimai section ===
        kimai_section = QLabel("Kimai Time Tracker")
        kimai_section.setStyleSheet(section_style)
        layout.addRow(kimai_section)

        kimai_url_label = QLabel("Server URL:")
        kimai_url_label.setStyleSheet(label_style)
        self._settings_kimai_url = QLineEdit()
        self._settings_kimai_url.setText(self.settings.get("kimai_url", ""))
        self._settings_kimai_url.setPlaceholderText("https://kimai.example.com")
        self._settings_kimai_url.setStyleSheet(input_style)
        layout.addRow(kimai_url_label, self._settings_kimai_url)

        kimai_token_label = QLabel("API Token:")
        kimai_token_label.setStyleSheet(label_style)
        self._settings_kimai_token = QLineEdit()
        self._settings_kimai_token.setText(self.settings.get("kimai_token", ""))
        self._settings_kimai_token.setPlaceholderText("Bearer token from your Kimai profile")
        self._settings_kimai_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._settings_kimai_token.setStyleSheet(input_style)
        layout.addRow(kimai_token_label, self._settings_kimai_token)

        kimai_csv_label = QLabel("CSV Import Folder:")
        kimai_csv_label.setStyleSheet(label_style)
        kimai_csv_row = QHBoxLayout()
        self._settings_kimai_csv_folder = QLineEdit()
        self._settings_kimai_csv_folder.setText(self.settings.get("kimai_csv_folder", ""))
        self._settings_kimai_csv_folder.setPlaceholderText("~/Nextcloud/ProjectFlowDocuments/times/")
        self._settings_kimai_csv_folder.setStyleSheet(input_style)
        kimai_csv_browse = QPushButton("Browse…")
        kimai_csv_browse.clicked.connect(lambda: self._browse_folder(self._settings_kimai_csv_folder))
        kimai_csv_row.addWidget(self._settings_kimai_csv_folder)
        kimai_csv_row.addWidget(kimai_csv_browse)
        layout.addRow(kimai_csv_label, kimai_csv_row)

        # === Joplin section ===
        joplin_section = QLabel("Joplin Notes")
        joplin_section.setStyleSheet(section_style)
        layout.addRow(joplin_section)

        joplin_label = QLabel("API Token:")
        joplin_label.setStyleSheet(label_style)
        self._settings_joplin = QLineEdit()
        self._settings_joplin.setText(self.settings.get("joplin_token", ""))
        self._settings_joplin.setPlaceholderText("Joplin Web Clipper API token")
        self._settings_joplin.setEchoMode(QLineEdit.EchoMode.Password)
        self._settings_joplin.setStyleSheet(input_style)
        layout.addRow(joplin_label, self._settings_joplin)

        return widget

    def _ensure_documentation_category(self):
        """Return the real category name to file Documentation items under, creating it
        (canonically "Documentation") if this project has neither that nor the legacy
        "Docs" name yet. Persists immediately via save_config_to_json() when it actually
        creates the category — required because handle_item_move_to_category() re-reads
        the config straight from disk, so an in-memory-only category wouldn't be found
        as a move destination and the item would be lost (removed from source, never
        inserted anywhere). Called lazily wherever something is actually about to be
        filed there (Add Launcher, Move to category, Scan for Docs) — never eagerly on
        project load, so a project that never uses it stays clutter-free."""
        for cd in self.COLUMN_1:
            if any(name in cd for name in ("Documentation", "Docs")):
                return next(name for name in ("Documentation", "Docs") if name in cd)
        self.COLUMN_1.append({"Documentation": []})
        self.save_config_to_json()
        return "Documentation"

    def _ai_hidden_paths_key(self):
        """Absolute path of the current config — scopes ai_hidden_paths per project."""
        if getattr(self, 'current_config_file', None):
            return os.path.abspath(self.current_config_file)
        return None

    def _get_ai_hidden_paths(self):
        key = self._ai_hidden_paths_key()
        if not key:
            return set()
        return set(self.settings.get('ai_hidden_paths', {}).get(key, []))

    def _toggle_ai_item_hidden(self, path):
        """Hide an AI-category item (👁 toggle) — stored in .projectflow_settings.json,
        never the project JSON, since this is a personal declutter preference rather than
        project content. AI items aren't self.COLUMN_1 data — this is the only per-item
        hide mechanism left; real Documentation/Resources items have no hide state."""
        key = self._ai_hidden_paths_key()
        if not key:
            return
        hidden = self.settings.setdefault('ai_hidden_paths', {}).setdefault(key, [])
        abs_path = os.path.abspath(path)
        if abs_path not in hidden:
            hidden.append(abs_path)
        self.save_settings()
        self.refresh_projects()

    def _get_all_hidden_items(self):
        """Everything currently hidden from the AI bucket (the only place a per-item 👁
        hide toggle still exists — real Documentation/Resources items have no hide
        state, only delete) — for the "N hidden — Manage" dialog."""
        return [
            {'label': os.path.basename(abs_path), 'path': abs_path}
            for abs_path in sorted(self._get_ai_hidden_paths())
        ]

    def _unhide_item(self, hidden_entry):
        """Reverse _toggle_ai_item_hidden() for one entry from _get_all_hidden_items()."""
        key = self._ai_hidden_paths_key()
        if key:
            hidden_list = self.settings.get('ai_hidden_paths', {}).get(key, [])
            if hidden_entry['path'] in hidden_list:
                hidden_list.remove(hidden_entry['path'])
            self.save_settings()
        self.refresh_projects()

    def _show_hidden_items_dialog(self):
        """Minimal management dialog for 👁-hidden items — see the "N hidden — Manage"
        link. Deliberately simple (plain list + un-hide), matching the View Archive
        dialog's style — no search/bulk actions, per the "tidy up later" scope decision."""
        hidden = self._get_all_hidden_items()
        dialog = QDialog(self)
        dialog.setWindowTitle("Hidden from Docs")
        dialog.resize(420, 320)
        layout = QVBoxLayout(dialog)

        list_widget = QListWidget()
        for entry in hidden:
            list_item = QListWidgetItem(entry['label'])
            list_item.setData(Qt.ItemDataRole.UserRole, entry)
            list_widget.addItem(list_item)
        layout.addWidget(list_widget)

        btn_row = QHBoxLayout()
        unhide_btn = QPushButton("Show Again")

        def _do_unhide():
            list_item = list_widget.currentItem()
            if not list_item:
                return
            self._unhide_item(list_item.data(Qt.ItemDataRole.UserRole))
            dialog.accept()

        unhide_btn.clicked.connect(_do_unhide)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(unhide_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dialog.exec()

    def _get_ai_category_items(self):
        """Detect an ai/ folder (see ai/.instructions.md's human/AI-shared-docs convention)
        in this project's default folder, and surface it plus well-known AI-authored root
        files as an automatic, non-editable "AI" category — always shown above Docs when
        present. Returns [] if no ai/ subfolder exists, so the bucket stays absent for most
        projects. Items in _get_ai_hidden_paths() (the 👁 hide toggle) are excluded.

        Falls back to the global path mapping (see _resolve_existing_path()) when
        config_folder_path itself isn't reachable directly — safe to do here (unlike Scan for
        Documents, which deliberately does NOT get this treatment) because AI items are purely
        dynamic and never persisted: they're recomputed fresh from disk on every render, so
        there's no "which path do we save" question. Sets self._ai_via_mapping so the render
        loop can apply the same pale-blue "mapped" styling used elsewhere (see
        get_item_button_style()/_path_is_via_mapping()).
        """
        root = getattr(self, 'config_folder_path', None)
        self._ai_via_mapping = False
        if not root:
            return []
        if not os.path.isdir(root):
            resolved, used_mapping = self._resolve_existing_path(root)
            if not used_mapping:
                return []
            root = os.path.expanduser(resolved)
            self._ai_via_mapping = True
        ai_dir = os.path.join(root, "ai")
        if not os.path.isdir(ai_dir):
            return []

        hidden_paths = self._get_ai_hidden_paths()
        items = []
        for name in sorted(os.listdir(ai_dir), key=str.lower):
            if name.startswith('.'):
                continue
            full_path = os.path.join(ai_dir, name)
            if os.path.isfile(full_path) and full_path not in hidden_paths:
                items.append([name, full_path, "default"])

        AI_ROOT_FILES = ["claude.md", "agents.md", "changelog.md", "specification.md", "spec.md"]
        try:
            root_entries = {n.lower(): n for n in os.listdir(root)}
        except OSError:
            root_entries = {}
        seen = set()
        for target in AI_ROOT_FILES:
            real_name = root_entries.get(target)
            if not real_name or real_name.lower() in seen:
                continue
            full_path = os.path.join(root, real_name)
            if os.path.isfile(full_path) and full_path not in hidden_paths:
                items.append([real_name, full_path, "default"])
                seen.add(real_name.lower())
        return items

    def _build_grouped_categories(self):
        """AI/Docs pooled view + real, editable Resources categories over self.COLUMN_1.

        AI stays a non-destructive, purely dynamic pool (see _get_ai_category_items()):
        items are discovered from the filesystem, not from self.COLUMN_1, and never
        written to the project's JSON file. Docs is backed by one real category —
        canonically named "Documentation" ("Docs" is accepted too, as a read-only legacy
        alias for projects created before this name was settled on; see
        _ensure_documentation_category(), which is what all new items get filed under
        going forward) — behaving exactly like any other category (full drag-reorder/
        rename/delete/add-entry, reusing Standard layout's own category rendering, see
        _is_grouped_view_active()/build_main_content()'s dispatch). There's no longer a
        classifier that pools items from OTHER categories into Docs by file extension —
        an item's category membership is simply wherever it's physically filed; use
        "Move to category" (context menu) or drag to relocate it.

        Resources is every other real category, returned under its own real name with
        its full, unfiltered item list intact — the only suppression left is an AI-path
        dedup (self._grouped_hidden_item_ids): if a real item happens to point at the
        same file the AI scan already surfaced, it's hidden from Resources so it doesn't
        show twice.

        Each item's true (category_name, index) is recorded in self._group_view_origin —
        by object identity, since the same list objects are reused, not copies — so
        editing/deleting/context-menu actions triggered from this view act on the real,
        authored data regardless of which bucket it's rendered under.
        """
        # Dict insertion order controls render order — AI declared first so it always
        # renders above Docs (see _get_ai_category_items()); real categories are
        # appended after, in their own self.COLUMN_1 order.
        buckets = {'AI': [], 'Docs': []}
        self._group_view_origin = {}
        self._grouped_hidden_item_ids = set()

        ai_items = self._get_ai_category_items()
        ai_paths = set()
        for item in ai_items:
            buckets['AI'].append(item)
            self._group_view_origin[id(item)] = (None, None)
            ai_paths.add(os.path.abspath(item[1]))

        real_category_buckets = []
        for cat_dict in self.COLUMN_1:
            for category_name, items in cat_dict.items():
                if category_name in ("Documentation", "Docs"):
                    # The real Documentation category — filed here IS the classification,
                    # no heuristic, no hiding; true origin lets these render fully
                    # editable (see docstring above).
                    for idx, item in enumerate(items):
                        buckets['Docs'].append(item)
                        self._group_view_origin[id(item)] = (category_name, idx)
                    continue
                has_visible_resource_item = False
                for idx, item in enumerate(items):
                    path = item[1]
                    self._group_view_origin[id(item)] = (category_name, idx)
                    if os.path.abspath(os.path.expanduser(str(path))) in ai_paths:
                        self._grouped_hidden_item_ids.add(id(item))
                        continue  # already surfaced via the automatic AI category
                    has_visible_resource_item = True
                if has_visible_resource_item:
                    real_category_buckets.append({category_name: items})

        # Always pin the project's own notes as the first Docs entry — a second,
        # non-editable way to reach the same file as the Notes panel/tab (see
        # CLAUDE.md's Group-by-Type Launcher View section). Sentinel origin
        # (None, None) marks it as synthetic so the render loop skips wiring
        # edit/delete/move-bucket context menu actions onto it.
        notes_item = [f"{self.get_project_name()} project notes", self.get_notes_file_path(), "default"]
        buckets['Docs'].insert(0, notes_item)
        self._group_view_origin[id(notes_item)] = (None, None)

        return [{name: items} for name, items in buckets.items() if items] + real_category_buckets

    def _is_grouped_view_active(self):
        """True whenever the launcher column is showing _build_grouped_categories()'s output
        rather than raw self.COLUMN_1 — used to gate the right-click "Move to category" menu,
        the "👁 N hidden — Manage" button, and (per-item, see build_main_content) the
        drag-disable behavior for the still-pooled AI/pinned-notes items. edit_mode does NOT
        blanket-disable this: Docs/Resources both stay on the grouped view while editing
        (Resources categories are real; Docs mixes a real Documentation category with the
        still-pooled AI/pinned-notes entries) — only Files/Apps fall back to raw self.COLUMN_1
        while editing, since there's nothing meaningful to manage on those tabs."""
        if self.layout_mode == "focus" and self.edit_mode and self.active_launcher_tab not in ("docs", "resources"):
            return False
        if self.group_by_type:
            return True
        return self.layout_mode == "focus" and getattr(self, 'active_launcher_tab', 'files') in ('docs', 'resources')

    def _scan_for_docs(self, root_path):
        """Walk root_path and return (display_name, abs_path, app) for doc files."""
        SKIP_DIRS = {
            'node_modules', '.git', 'dist', 'build', '__pycache__',
            'venv', '.venv', '.archive', 'target', '.next', 'out',
            '.nuxt', '.svelte-kit', 'coverage', '.cache', '.tox',
        }
        DOC_DIRS = {'docs', 'documentation', 'manual', 'doc', 'wiki',
                    'help', 'guides', 'reference', 'api', 'spec'}

        is_npm = os.path.exists(os.path.join(root_path, 'package.json'))
        results = []
        seen = set()

        for dirpath, dirnames, filenames in os.walk(root_path):
            rel = os.path.relpath(dirpath, root_path)
            depth = 0 if rel == '.' else rel.count(os.sep) + 1
            if depth > 4:
                dirnames.clear()
                continue

            dirnames[:] = sorted(
                d for d in dirnames
                if d not in SKIP_DIRS and not (d.startswith('.') and d != '.')
            )

            dir_name = os.path.basename(dirpath).lower()
            in_doc_dir = depth == 0 or dir_name in DOC_DIRS

            for filename in sorted(filenames):
                stem, ext = os.path.splitext(filename)
                ext = ext.lower()
                if ext not in ('.md', '.html', '.htm'):
                    continue
                abs_path = os.path.join(dirpath, filename)
                if abs_path in seen:
                    continue
                seen.add(abs_path)
                if ext == '.md':
                    app = 'default'
                else:
                    if is_npm and not in_doc_dir:
                        continue
                    app = 'firefox'
                display = stem.replace('_', ' ').replace('-', ' ')
                results.append((display, abs_path, app))

        return results, is_npm

    def _show_doc_scan_dialog(self):
        """Scan a folder for documentation files and add selected ones to a Documentation category."""
        scan_path = getattr(self, 'config_folder_path', None)
        if not scan_path or not os.path.isdir(scan_path):
            if hasattr(self, 'current_config_file') and self.current_config_file:
                candidate = os.path.dirname(os.path.abspath(self.current_config_file))
                if os.path.isdir(candidate):
                    scan_path = candidate
        if not scan_path or not os.path.isdir(scan_path):
            chosen = QFileDialog.getExistingDirectory(self, "Select Project Folder to Scan", os.path.expanduser("~"))
            if not chosen:
                return
            scan_path = chosen

        dlg = QDialog(self)
        dlg.setWindowTitle("Scan for Documentation")
        dlg.resize(580, 500)
        dlg.setStyleSheet(f"background-color: {self.t('bg_primary')}; color: {self.t('fg_primary')};")

        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(16, 16, 16, 12)
        dlg_layout.setSpacing(10)

        lbl_style = f"color: {self.t('fg_primary')};"
        input_style = f"""
            QLineEdit {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 5px;
            }}
        """
        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 5px 10px;
            }}
            QPushButton:hover {{ background-color: {self.t('bg_button_hover')}; }}
        """
        list_style = f"""
            QListWidget {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
            }}
            QListWidget::item {{ padding: 4px 6px; border-bottom: 1px solid {self.t('border')}; }}
            QListWidget::item:selected {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
            }}
        """

        # Folder row
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        folder_lbl = QLabel("Folder:")
        folder_lbl.setStyleSheet(lbl_style)
        path_edit = QLineEdit(scan_path)
        path_edit.setReadOnly(True)
        path_edit.setStyleSheet(input_style)
        change_btn = QPushButton("Change")
        change_btn.setStyleSheet(btn_style)
        folder_row.addWidget(folder_lbl)
        folder_row.addWidget(path_edit, 1)
        folder_row.addWidget(change_btn)
        dlg_layout.addLayout(folder_row)

        # Select / deselect row
        sel_row = QHBoxLayout()
        sel_row.setSpacing(6)
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.setStyleSheet(btn_style)
        desel_all_btn = QPushButton("Deselect All")
        desel_all_btn.setStyleSheet(btn_style)
        sel_row.addWidget(sel_all_btn)
        sel_row.addWidget(desel_all_btn)
        sel_row.addStretch()
        dlg_layout.addLayout(sel_row)

        # File list
        file_list = QListWidget()
        file_list.setStyleSheet(list_style)
        dlg_layout.addWidget(file_list, 1)

        # Note/warning label
        note_lbl = QLabel("")
        note_lbl.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 11px;")
        note_lbl.setWordWrap(True)
        dlg_layout.addWidget(note_lbl)

        # Bottom buttons
        btm_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(btn_style)
        add_btn = QPushButton("Add to Documentation")
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {self.t('bg_category_hover')}; }}
            QPushButton:disabled {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_secondary')};
            }}
        """)
        btm_row.addStretch()
        btm_row.addWidget(cancel_btn)
        btm_row.addWidget(add_btn)
        dlg_layout.addLayout(btm_row)

        # State
        current_path = [scan_path]

        def populate(path):
            file_list.clear()
            found, is_npm = self._scan_for_docs(path)

            existing_paths = set()
            for cat_dict in self.COLUMN_1:
                for name in ('Documentation', 'Docs'):
                    if name in cat_dict:
                        existing_paths |= {item[1] for item in cat_dict[name] if len(item) > 1}

            for display, abs_path, app in found:
                already = abs_path in existing_paths
                rel = os.path.relpath(abs_path, path)
                list_item = QListWidgetItem(f"{display}  —  {rel}")
                list_item.setData(Qt.ItemDataRole.UserRole, (display, abs_path, app))
                list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                # Opt-in, not opt-out: files already tracked in the project start checked
                # (informational — nothing new happens if left checked, "Add" dedupes by
                # path anyway), while newly-found files start UNCHECKED so adding them is a
                # deliberate choice rather than something that happens unless you notice and
                # uncheck it.
                list_item.setCheckState(Qt.CheckState.Checked if already else Qt.CheckState.Unchecked)
                if already:
                    list_item.setToolTip("Already in Documentation category")
                    list_item.setForeground(QColor(self.t('fg_secondary')))
                file_list.addItem(list_item)

            if not found:
                note_lbl.setText("No documentation files found in this folder.")
                add_btn.setEnabled(False)
            elif is_npm:
                note_lbl.setText("npm project detected — HTML files outside docs/ folders are excluded.")
                add_btn.setEnabled(True)
            else:
                note_lbl.setText("")
                add_btn.setEnabled(True)

        populate(scan_path)

        def change_folder():
            chosen = QFileDialog.getExistingDirectory(dlg, "Select Folder to Scan", current_path[0])
            if chosen:
                current_path[0] = chosen
                path_edit.setText(chosen)
                populate(chosen)

        def select_all():
            for i in range(file_list.count()):
                file_list.item(i).setCheckState(Qt.CheckState.Checked)

        def deselect_all():
            for i in range(file_list.count()):
                file_list.item(i).setCheckState(Qt.CheckState.Unchecked)

        def do_add():
            selected = []
            for i in range(file_list.count()):
                li = file_list.item(i)
                if li.checkState() == Qt.CheckState.Checked:
                    selected.append(li.data(Qt.ItemDataRole.UserRole))
            if not selected:
                dlg.reject()
                return

            doc_category_name = self._ensure_documentation_category()
            doc_items = next(cd[doc_category_name] for cd in self.COLUMN_1 if doc_category_name in cd)

            existing_paths = {item[1] for item in doc_items if len(item) > 1}
            added = 0
            for name, path, app in selected:
                if path not in existing_paths:
                    doc_items.append([name, path, app])
                    added += 1

            self.config_folder_path = current_path[0]
            if hasattr(self, '_proj_folder_path'):
                self._proj_folder_path.setText(current_path[0])

            self._save_project_config()

            dlg.accept()
            QMessageBox.information(
                self, "Done",
                f"Added {added} item{'s' if added != 1 else ''} to Documentation."
            )

        change_btn.clicked.connect(change_folder)
        sel_all_btn.clicked.connect(select_all)
        desel_all_btn.clicked.connect(deselect_all)
        cancel_btn.clicked.connect(dlg.reject)
        add_btn.clicked.connect(do_add)

        dlg.exec()

    def _show_kickstart_dialog(self, folder_path=None, website_url=""):
        """Kickstart / Project Finder: review-and-apply suggestions for a project's base
        folder — detected project-type commands, dev shortcuts, documentation, a project
        alias, and an optional website. Reachable both as a retrofit action (Project
        Settings viewer's "🚀 Kickstart" button, no folder_path needed — falls back the
        same way _show_doc_scan_dialog() does) and automatically right after "Make
        Project" (folder_make_project()/folder_make_project_at(), pre-populated with the
        new project's folder_path) or after "New Project" when a base folder is linked
        (new_project()).

        Detection itself lives in _detect_project_indicators()/
        _build_dev_shortcut_suggestions() — this method is purely the review UI plus the
        Apply handler that writes selections into self.COLUMN_1 and saves.
        """
        if not folder_path:
            folder_path = getattr(self, 'config_folder_path', None)
            if folder_path:
                folder_path = os.path.expanduser(folder_path)
            if not folder_path or not os.path.isdir(folder_path):
                if getattr(self, 'current_config_file', None):
                    candidate = os.path.dirname(os.path.abspath(self.current_config_file))
                    if os.path.isdir(candidate):
                        folder_path = candidate
        if not folder_path or not os.path.isdir(folder_path):
            chosen = QFileDialog.getExistingDirectory(self, "Select Project Folder", os.path.expanduser("~"))
            if not chosen:
                return
            folder_path = chosen
        folder_path = os.path.abspath(os.path.expanduser(folder_path))

        dlg = QDialog(self)
        dlg.setWindowTitle("🚀 Kickstart")
        dlg.resize(640, 660)
        dlg.setStyleSheet(f"background-color: {self.t('bg_primary')}; color: {self.t('fg_primary')};")

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(16, 16, 16, 12)
        outer.setSpacing(10)

        lbl_style = f"color: {self.t('fg_primary')};"
        section_style = f"color: {self.t('fg_primary')}; font-weight: bold; margin-top: 6px;"
        info_style = f"color: {self.t('fg_secondary')}; font-size: 11px;"
        check_style = f"color: {self.t('fg_primary')};"
        input_style = f"""
            QLineEdit {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 5px;
            }}
        """
        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 5px 10px;
            }}
            QPushButton:hover {{ background-color: {self.t('bg_button_hover')}; }}
        """

        # Folder row
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        folder_lbl = QLabel("Folder:")
        folder_lbl.setStyleSheet(lbl_style)
        path_edit = QLineEdit(folder_path)
        path_edit.setReadOnly(True)
        path_edit.setStyleSheet(input_style)
        change_btn = QPushButton("Change")
        change_btn.setStyleSheet(btn_style)
        folder_row.addWidget(folder_lbl)
        folder_row.addWidget(path_edit, 1)
        folder_row.addWidget(change_btn)
        outer.addLayout(folder_row)

        # Scrollable body — heterogeneous sections (checkboxes, radio, text fields),
        # unlike _show_doc_scan_dialog's single flat QListWidget of same-shaped items.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: 1px solid {self.t('border')}; border-radius: 4px; }}")
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(8)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        existing_paths = set()
        for cat_dict in self.COLUMN_1:
            for items in cat_dict.values():
                existing_paths |= {item[1] for item in items if len(item) > 1}

        checkbox_entries = []  # (checkbox, category_name, item)

        def add_checkbox_section(title, suggestions):
            if not suggestions:
                return
            header = QLabel(title)
            header.setStyleSheet(section_style)
            body_layout.addWidget(header)
            for s in suggestions:
                already = s["item"][1] in existing_paths
                cb = QCheckBox(s["label"])
                cb.setStyleSheet(check_style)
                # Opt-in, not opt-out — every suggestion starts unchecked regardless of
                # detection confidence; the user picks what they actually want.
                cb.setChecked(False)
                if already:
                    cb.setEnabled(False)
                    cb.setToolTip("Already in this project")
                body_layout.addWidget(cb)
                checkbox_entries.append((cb, title, s["item"]))

        # --- Website ---
        website_header = QLabel("Website")
        website_header.setStyleSheet(section_style)
        body_layout.addWidget(website_header)
        website_edit = QLineEdit(website_url)
        website_edit.setPlaceholderText("https://example.com")
        website_edit.setStyleSheet(input_style)
        body_layout.addWidget(website_edit)
        website_launcher_cb = QCheckBox('Add "Open Website" launcher')
        website_launcher_cb.setStyleSheet(check_style)
        website_pin_cb = QCheckBox("Set as pinned Web URL (opens by default)")
        website_pin_cb.setStyleSheet(check_style)
        body_layout.addWidget(website_launcher_cb)
        body_layout.addWidget(website_pin_cb)

        def _update_website_checks(text=""):
            # Opt-in, not opt-out: typing a URL only enables these checkboxes — it no
            # longer auto-checks "Add launcher" for you. Clearing the URL still force-
            # unchecks both, since neither makes sense with nothing to point at.
            has_url = bool(website_edit.text().strip())
            website_launcher_cb.setEnabled(has_url)
            website_pin_cb.setEnabled(has_url)
            if not has_url:
                website_launcher_cb.setChecked(False)
                website_pin_cb.setChecked(False)

        website_edit.textChanged.connect(_update_website_checks)
        _update_website_checks()

        # --- Dev Shortcuts ---
        dev_header = QLabel("Dev Shortcuts")
        dev_header.setStyleSheet(section_style)
        body_layout.addWidget(dev_header)
        dev_radio_row = QHBoxLayout()
        dev_combined_radio = QRadioButton("Combined (directorydev)")
        dev_separate_radio = QRadioButton("Three separate launchers")
        dev_combined_radio.setChecked(True)
        for r in (dev_combined_radio, dev_separate_radio):
            r.setStyleSheet(check_style)
        dev_radio_row.addWidget(dev_combined_radio)
        dev_radio_row.addWidget(dev_separate_radio)
        dev_radio_row.addStretch()
        body_layout.addLayout(dev_radio_row)
        dev_checks_container = QWidget()
        dev_checks_layout = QVBoxLayout(dev_checks_container)
        dev_checks_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.addWidget(dev_checks_container)

        dev_checkbox_entries = []

        def rebuild_dev_checks():
            while dev_checkbox_entries:
                cb, _, _ = dev_checkbox_entries.pop()
                cb.setParent(None)
            suggestions = self._build_dev_shortcut_suggestions(folder_path, combined=dev_combined_radio.isChecked())
            for s in suggestions:
                already = s["item"][1] in existing_paths
                cb = QCheckBox(s["label"])
                cb.setStyleSheet(check_style)
                # Opt-in, not opt-out — see add_checkbox_section()'s matching comment above.
                cb.setChecked(False)
                if already:
                    cb.setEnabled(False)
                    cb.setToolTip("Already in this project")
                dev_checks_layout.addWidget(cb)
                dev_checkbox_entries.append((cb, "Development", s["item"]))

        dev_combined_radio.toggled.connect(rebuild_dev_checks)
        rebuild_dev_checks()

        # --- Detected project-type suggestions ---
        indicator_groups = self._detect_project_indicators(folder_path)
        detected_names = ", ".join(g["category"] for g in indicator_groups if g["category"] != "Quick Actions")
        if detected_names:
            detected_lbl = QLabel(f"Detected: {detected_names}")
            detected_lbl.setStyleSheet(info_style)
            body_layout.addWidget(detected_lbl)
        for group in indicator_groups:
            add_checkbox_section(group["category"], group["suggestions"])

        # --- Documentation ---
        found_docs, is_npm = self._scan_for_docs(folder_path)
        doc_suggestions = [
            {"id": f"doc_{i}", "label": f"{display}  —  {os.path.relpath(p, folder_path)}",
             "item": [display, p, app]}
            for i, (display, p, app) in enumerate(found_docs)
        ]
        add_checkbox_section("Documentation", doc_suggestions)
        if is_npm and found_docs:
            npm_doc_note = QLabel("npm project detected — HTML files outside docs/ folders are excluded.")
            npm_doc_note.setStyleSheet(info_style)
            npm_doc_note.setWordWrap(True)
            body_layout.addWidget(npm_doc_note)

        # --- AI (informational only — already fully dynamic, see _get_ai_category_items()) ---
        ai_detected = os.path.isdir(os.path.join(folder_path, "ai")) or any(
            os.path.exists(os.path.join(folder_path, f))
            for f in ("CLAUDE.md", "AGENTS.md", "CHANGELOG.md", "Specification.md", "SPEC.md")
        )
        if ai_detected:
            ai_lbl = QLabel("🤖 AI folder/docs detected — these already show automatically in the AI section, nothing to add here.")
            ai_lbl.setWordWrap(True)
            ai_lbl.setStyleSheet(info_style)
            body_layout.addWidget(ai_lbl)

        # --- Project Alias ---
        # Unlike checkbox_entries/dev_checkbox_entries, this one item isn't built from a
        # generic (checkbox, category, item) list — check separately whether an alias
        # already targets this exact folder, so re-running Kickstart on the same project
        # doesn't silently duplicate the Development-category alias launcher item (the
        # shell-alias-file write itself is idempotent via _write_alias_to_file(force=True),
        # but the launcher item append in _apply_kickstart_selections() is not).
        alias_already_exists = any(
            len(item) >= 3 and item[2] == "alias" and item[1].rstrip().endswith(folder_path)
            for cd in self.COLUMN_1 for items in cd.values() for item in items
        )
        alias_header = QLabel("Project Alias")
        alias_header.setStyleSheet(section_style)
        body_layout.addWidget(alias_header)
        alias_cb = QCheckBox("Create shell alias + launcher to jump to this folder")
        alias_cb.setStyleSheet(check_style)
        # Opt-in, not opt-out — starts unchecked either way now (previously defaulted to
        # checked when no alias existed yet). Still just a tooltip, not disabled, when one
        # already exists: the field stays enabled in case a second, differently-named
        # alias to the same folder is genuinely wanted.
        alias_cb.setChecked(False)
        if alias_already_exists:
            alias_cb.setToolTip("An alias already points at this folder")
        body_layout.addWidget(alias_cb)
        alias_row = QHBoxLayout()
        alias_name_lbl = QLabel("Name:")
        alias_name_lbl.setStyleSheet(lbl_style)
        default_alias_name = getattr(self, 'config_project_name', None) or os.path.basename(folder_path)
        default_alias_name = re.sub(r'[^a-zA-Z0-9_]+', '_', default_alias_name.strip().lower()).strip('_') or "project"
        alias_name_edit = QLineEdit(default_alias_name)
        alias_name_edit.setStyleSheet(input_style)
        alias_row.addWidget(alias_name_lbl)
        alias_row.addWidget(alias_name_edit)
        body_layout.addLayout(alias_row)
        alias_preview = QLabel()
        alias_preview.setStyleSheet(info_style)
        body_layout.addWidget(alias_preview)

        def _update_alias_preview(text=""):
            name = alias_name_edit.text().strip() or "?"
            alias_preview.setText(f"→ {name}  =  cd {folder_path}")

        alias_name_edit.textChanged.connect(_update_alias_preview)
        _update_alias_preview()

        body_layout.addStretch()

        # Bottom buttons
        btm_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(btn_style)
        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {self.t('bg_category_hover')}; }}
        """)
        btm_row.addStretch()
        btm_row.addWidget(cancel_btn)
        btm_row.addWidget(apply_btn)
        outer.addLayout(btm_row)

        def change_folder():
            chosen = QFileDialog.getExistingDirectory(dlg, "Select Project Folder", folder_path)
            if chosen:
                dlg.reject()
                self._show_kickstart_dialog(folder_path=chosen, website_url=website_edit.text().strip())

        def do_apply():
            self._apply_kickstart_selections(
                folder_path=folder_path,
                checkbox_entries=checkbox_entries + dev_checkbox_entries,
                alias_checked=alias_cb.isChecked(),
                alias_name=alias_name_edit.text().strip(),
                website=website_edit.text().strip(),
                website_launcher_checked=website_launcher_cb.isChecked(),
                website_pin_checked=website_pin_cb.isChecked(),
                dialog=dlg,
            )

        change_btn.clicked.connect(change_folder)
        cancel_btn.clicked.connect(dlg.reject)
        apply_btn.clicked.connect(do_apply)

        dlg.exec()

    def _apply_kickstart_selections(self, folder_path, checkbox_entries, alias_checked, alias_name,
                                     website, website_launcher_checked, website_pin_checked, dialog):
        """Apply handler for _show_kickstart_dialog(): writes every checked suggestion
        into self.COLUMN_1 (Documentation items go through _ensure_documentation_category()
        to match Scan-for-Docs' own behavior; everything else creates/reuses a plain
        category dict the same way create_folder_project_config() used to), optionally
        writes a shell alias (_write_alias_to_file(), mirrors the manual add-alias flow —
        see open_in_app()'s app == "alias" branch for how the resulting item is parsed),
        optionally sets the pinned Web URL, then saves via _save_project_config() — the
        one call that persists both the column/category changes and
        config_webview_url/config_column2_default together (see _show_doc_scan_dialog()'s
        own do_add(), which uses the same call for the same reason)."""
        # Pin the reviewed folder as this project's default (mirrors _show_doc_scan_dialog's
        # own do_add(), which does the same) — Kickstart is fundamentally about linking a
        # base folder, so this is an expected side effect, not a surprise one.
        self.config_folder_path = folder_path
        if hasattr(self, '_proj_folder_path'):
            self._proj_folder_path.setText(folder_path)

        selected_by_category = {}
        for cb, category, item in checkbox_entries:
            if cb.isChecked():
                selected_by_category.setdefault(category, []).append(item)

        doc_items = selected_by_category.pop("Documentation", None)
        added = 0

        for category, items in selected_by_category.items():
            existing_cat = next((cd[category] for cd in self.COLUMN_1 if category in cd), None)
            if existing_cat is None:
                existing_cat = []
                self.COLUMN_1.append({category: existing_cat})
            existing_cat.extend(items)
            added += len(items)

        if doc_items:
            doc_category_name = self._ensure_documentation_category()
            doc_cat_items = next(cd[doc_category_name] for cd in self.COLUMN_1 if doc_category_name in cd)
            doc_cat_items.extend(doc_items)
            added += len(doc_items)

        alias_created = False
        if alias_checked and alias_name:
            if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', alias_name):
                self._write_alias_to_file(alias_name, folder_path, force=True)
                dev_cat = next((cd["Development"] for cd in self.COLUMN_1 if "Development" in cd), None)
                if dev_cat is None:
                    dev_cat = []
                    self.COLUMN_1.append({"Development": dev_cat})
                dev_cat.append([alias_name, f"{alias_name} {folder_path}", "alias"])
                added += 1
                alias_created = True
            else:
                QMessageBox.warning(
                    dialog, "Invalid Alias",
                    f"'{alias_name}' isn't a valid alias name (letters, numbers, underscore; "
                    "can't start with a number) — alias was not created."
                )

        if website:
            if website_launcher_checked:
                links_cat = next((cd["Links"] for cd in self.COLUMN_1 if "Links" in cd), None)
                if links_cat is None:
                    links_cat = []
                    self.COLUMN_1.append({"Links": links_cat})
                links_cat.append(["Open Website", website, "firefox"])
                added += 1
            if website_pin_checked:
                self.config_webview_url = website
                if not self.config_column2_default:
                    self.config_column2_default = "webview"

        self._save_project_config()
        self.refresh_projects()
        dialog.accept()

        summary = f"Added {added} item{'s' if added != 1 else ''} to the project."
        if alias_created:
            summary += "\n\nRe-source projects/projectflow_aliases in your shell to activate the new alias there."
        QMessageBox.information(self, "Kickstart Applied", summary)

    def _build_settings_form(self):
        """Build the persistent Project Settings form (self.settings_form), embedded as a
        viewer (column2_mode == "settings") rather than a modal dialog. Built ONCE here and
        reused across every build_main_content() rebuild — like notes_webview/code_webview,
        not recreated fresh each time — so an unrelated refresh_projects() call elsewhere
        (e.g. reordering a launcher while this viewer happens to be open) doesn't silently
        wipe in-progress edits the way a plain per-rebuild QWidget container would. Field
        widgets keep the same _proj_* attribute names the old dialog's
        _create_project_defaults_tab() used, so _apply_settings() (invoked by the toolbar's
        Save button, see create_settings_toolbar()) works completely unchanged.

        Only structure is built here — no values are set, since self.config_* attributes
        aren't populated yet this early in __init__ (load_config() runs after). See
        _populate_settings_form(), called once a project is actually loaded and again
        whenever this viewer is entered for a different project (self._settings_loaded_for,
        checked in switch_to_viewer_mode() and build_main_content()'s mode dispatch, so a
        repeat visit to the same project's settings doesn't reset in-progress edits either).
        Styling (theme-dependent) is likewise applied separately by _style_settings_form(),
        called here once and again on every rebuild in case the theme changed meanwhile.
        """
        self.settings_form = QWidget()
        main_layout = QVBoxLayout(self.settings_form)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # Plain field labels collected here so _style_settings_form() can restyle them all
        # identically in one pass; the two Desktop-Menu-Entry section labels have their own
        # distinct bold/secondary styles and are restyled by name instead (see below).
        self._settings_form_labels = []

        def field_label(text):
            lbl = QLabel(text)
            self._settings_form_labels.append(lbl)
            return lbl

        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        self._settings_form_layout = form_layout

        # Project Name
        self._proj_project_name = QLineEdit()
        form_layout.addRow(field_label("Project Name:"), self._proj_project_name)

        # Project Color
        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        self._proj_color_btn = QPushButton("Choose Color...")
        self._proj_color_value = ""  # tracks the chosen color between picks
        def _pick_project_color():
            from PyQt6.QtWidgets import QColorDialog
            from PyQt6.QtGui import QColor
            used_colors = list(dict.fromkeys(
                self._sorted_colors(list(set(getattr(self, '_color_cache', {}).values())))
            ))
            for i, hex_color in enumerate(used_colors[:16]):
                QColorDialog.setCustomColor(i, QColor(hex_color))
            initial = QColor(self._proj_color_value) if self._proj_color_value else QColor("#3498db")
            chosen = QColorDialog.getColor(initial, self)
            if chosen.isValid():
                self._proj_color_value = chosen.name()
                self._style_project_color_button()
        self._proj_color_btn.clicked.connect(_pick_project_color)
        color_row.addWidget(self._proj_color_btn)
        self._proj_color_clear_btn = QPushButton("Clear")
        def _clear_proj_color():
            self._proj_color_value = ""
            self._style_project_color_button()
        self._proj_color_clear_btn.clicked.connect(_clear_proj_color)
        color_row.addWidget(self._proj_color_clear_btn)
        color_row.addStretch()
        form_layout.addRow(field_label("Project Color:"), color_row)

        # Scan for Documents — a normal field row (label left, action widget right) rather
        # than the separate "Project Actions" section this used to live in further down;
        # moved up next to Project Color since it's one of the first things people reach
        # for when setting up a project. Also repeated inside the Docs launcher section
        # itself in edit mode — see build_main_content()'s "Add Category" handling.
        scan_docs_layout = QVBoxLayout()
        scan_docs_layout.setSpacing(4)
        scan_docs_btn_row = QHBoxLayout()
        self._settings_scan_docs_btn = QPushButton("🔍 Scan for docs")
        self._settings_scan_docs_btn.setToolTip("Scan project folder for documentation files")
        self._settings_scan_docs_btn.clicked.connect(self._show_doc_scan_dialog)
        scan_docs_btn_row.addWidget(self._settings_scan_docs_btn)
        scan_docs_btn_row.addStretch()
        scan_docs_layout.addLayout(scan_docs_btn_row)
        self._settings_scan_docs_desc = QLabel("Scans the default folder for .md, .html files, optionally add to documents/launchers.")
        self._settings_scan_docs_desc.setWordWrap(True)
        scan_docs_layout.addWidget(self._settings_scan_docs_desc)
        form_layout.addRow(field_label("Scan for Documents:"), scan_docs_layout)

        # Kickstart — retrofit entry point for the same suggestion review dialog shown
        # automatically right after "Make Project" (see folder_make_project()). Placed
        # directly below Scan for Documents since it's a superset of that action (docs +
        # dev shortcuts + package-manager commands + alias + website, all in one review).
        kickstart_layout = QVBoxLayout()
        kickstart_layout.setSpacing(4)
        kickstart_btn_row = QHBoxLayout()
        self._settings_kickstart_btn = QPushButton("🚀 Kickstart")
        self._settings_kickstart_btn.setToolTip("Review suggested docs, shortcuts, commands, and an alias for this project's folder")
        self._settings_kickstart_btn.clicked.connect(lambda: self._show_kickstart_dialog())
        kickstart_btn_row.addWidget(self._settings_kickstart_btn)
        kickstart_btn_row.addStretch()
        kickstart_layout.addLayout(kickstart_btn_row)
        self._settings_kickstart_desc = QLabel("Suggests documentation, dev shortcuts, package-manager commands, an alias, and a website launcher — review and pick what to add.")
        self._settings_kickstart_desc.setWordWrap(True)
        kickstart_layout.addWidget(self._settings_kickstart_desc)
        form_layout.addRow(field_label("Kickstart:"), kickstart_layout)

        # Layout mode (Standard 3-column vs Focus 2-column) — moved here from the
        # title-bar ⊞/▣ toggle button so it lives alongside the project's other
        # per-project defaults rather than as a persistent top-right button.
        self._proj_use_three_columns = QCheckBox("Use three columns view")
        form_layout.addRow(field_label("Layout:"), self._proj_use_three_columns)

        # Default Viewer
        self._proj_default_viewer = QComboBox()
        # Order matches the viewer tab row (Notes, Web, Terminal, PDF, Image, Code, Time);
        # "help" isn't a tab (opened via the footer's "❓ Help" button instead), so it's
        # appended last. Unlike pdf/image, there's no dedicated "Code File" field in this
        # form yet — pinning a specific file for "code" is done via the viewer's own 📌
        # (see Code Editor in CLAUDE.md); picking "code" here with no code_file set just
        # opens the editor empty, same as "notes"/"time" having no resource field either.
        self._proj_default_viewer.addItems(["", "notes", "webview", "console", "pdf", "image", "code", "time", "help"])
        form_layout.addRow(field_label("Default Viewer:"), self._proj_default_viewer)

        # Default Launcher Tab (Focus layout) — pins Files/Docs/Resources/Apps, mirrors
        # Default Viewer above (see _set_launcher_tab_as_default())
        self._proj_default_launcher_tab = QComboBox()
        # Order matches the launcher tab row (Docs, Resources, Files, Apps).
        self._proj_default_launcher_tab.addItems(["", "docs", "resources", "files", "apps"])
        form_layout.addRow(field_label("Default Launcher Tab:"), self._proj_default_launcher_tab)

        # PDF File
        pdf_layout = QHBoxLayout()
        self._proj_pdf_file = QLineEdit()
        self._proj_pdf_file.setPlaceholderText("Path to default PDF file")
        self._proj_pdf_browse_btn = QPushButton("Browse")
        self._proj_pdf_browse_btn.clicked.connect(lambda: self._browse_file(self._proj_pdf_file, "PDF Files (*.pdf);;All Files (*)"))
        pdf_layout.addWidget(self._proj_pdf_file)
        pdf_layout.addWidget(self._proj_pdf_browse_btn)
        form_layout.addRow(field_label("PDF File:"), pdf_layout)

        # Web URL
        self._proj_webview_url = QLineEdit()
        self._proj_webview_url.setPlaceholderText("https://example.com")
        form_layout.addRow(field_label("Web URL:"), self._proj_webview_url)

        # Image File
        image_layout = QHBoxLayout()
        self._proj_image_file = QLineEdit()
        self._proj_image_file.setPlaceholderText("Path to default image file")
        self._proj_image_browse_btn = QPushButton("Browse")
        self._proj_image_browse_btn.clicked.connect(lambda: self._browse_file(self._proj_image_file, "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.svg);;All Files (*)"))
        image_layout.addWidget(self._proj_image_file)
        image_layout.addWidget(self._proj_image_browse_btn)
        form_layout.addRow(field_label("Image File:"), image_layout)

        # Console Path
        console_layout = QHBoxLayout()
        self._proj_console_path = QLineEdit()
        self._proj_console_path.setPlaceholderText("Working directory for console")
        self._proj_console_browse_btn = QPushButton("Browse")
        self._proj_console_browse_btn.clicked.connect(lambda: self._browse_folder(self._proj_console_path))
        console_layout.addWidget(self._proj_console_path)
        console_layout.addWidget(self._proj_console_browse_btn)
        form_layout.addRow(field_label("Console Path:"), console_layout)

        # Folder Start Path
        folder_start_layout = QHBoxLayout()
        self._proj_folder_path = QLineEdit()
        self._proj_folder_path.setPlaceholderText("Default folder for browser (leave blank for home)")
        self._proj_folder_browse_btn = QPushButton("Browse")
        self._proj_folder_browse_btn.clicked.connect(lambda: self._browse_folder(self._proj_folder_path))
        folder_start_layout.addWidget(self._proj_folder_path)
        folder_start_layout.addWidget(self._proj_folder_browse_btn)
        form_layout.addRow(field_label("Folder Start Path:"), folder_start_layout)

        # Terminal (per-config override)
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
        form_layout.addRow(field_label("Terminal:"), self._proj_terminal)

        # Browser Links (per-project override)
        self._proj_browser_new_tab = QComboBox()
        self._proj_browser_new_tab.addItems(["(use global setting)", "New tab", "New window"])
        self._proj_browser_new_tab.setToolTip("Override global browser link behaviour for this project")
        form_layout.addRow(field_label("Browser Links:"), self._proj_browser_new_tab)

        # Kimai Project ID — row always exists (unlike the old dialog, which only created
        # it when Kimai was configured); _populate_settings_form() toggles its visibility
        # via QFormLayout.setRowVisible() instead, since this widget is now permanent.
        self._settings_kimai_label = field_label("Kimai Project ID:")
        kimai_pid_row = QHBoxLayout()
        self._proj_kimai_project_id = QLineEdit()
        self._proj_kimai_project_id.setPlaceholderText("Numeric project ID from Kimai")
        self._proj_kimai_browse_btn = QPushButton("Browse…")
        self._proj_kimai_browse_btn.clicked.connect(lambda: self._kimai_pick_project_into(self._proj_kimai_project_id))
        kimai_pid_row.addWidget(self._proj_kimai_project_id)
        kimai_pid_row.addWidget(self._proj_kimai_browse_btn)
        form_layout.addRow(self._settings_kimai_label, kimai_pid_row)

        main_layout.addLayout(form_layout)
        main_layout.addSpacing(20)

        # Desktop Menu Entry section
        self._settings_menu_label = QLabel("Desktop Menu Entry:")
        main_layout.addWidget(self._settings_menu_label)

        self._settings_menu_desc = QLabel("Create a .desktop file for this project in your application menu. Includes a right-click menu to quickly switch between projects.")
        self._settings_menu_desc.setWordWrap(True)
        main_layout.addWidget(self._settings_menu_desc)

        menu_btn_layout = QHBoxLayout()
        self._settings_create_menu_btn = QPushButton("Create Menu Entry")
        self._settings_create_menu_btn.setToolTip("Create/update .desktop file for this project")
        self._settings_create_menu_btn.clicked.connect(self.regenerate_desktop_file)
        menu_btn_layout.addWidget(self._settings_create_menu_btn)
        menu_btn_layout.addStretch()
        main_layout.addLayout(menu_btn_layout)

        main_layout.addStretch()  # Push form to top

        self._style_settings_form()

    def _style_settings_form(self):
        """Re-apply theme-derived stylesheets to the persistent settings form's widgets.
        Called once right after _build_settings_form() and again on every
        build_main_content() rebuild — the widgets themselves survive rebuilds (see
        _build_settings_form()'s docstring) but the active theme can change between them."""
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

        for lbl in self._settings_form_labels:
            lbl.setStyleSheet(label_style)

        for widget in (
            self._proj_project_name, self._proj_default_viewer, self._proj_default_launcher_tab,
            self._proj_pdf_file, self._proj_webview_url, self._proj_image_file,
            self._proj_console_path, self._proj_folder_path, self._proj_terminal,
            self._proj_browser_new_tab, self._proj_kimai_project_id,
        ):
            widget.setStyleSheet(input_style)

        for btn in (
            self._proj_color_clear_btn, self._proj_pdf_browse_btn, self._proj_image_browse_btn,
            self._proj_console_browse_btn, self._proj_folder_browse_btn, self._proj_kimai_browse_btn,
            self._settings_create_menu_btn, self._settings_scan_docs_btn, self._settings_kickstart_btn,
        ):
            btn.setStyleSheet(btn_style)

        self._proj_use_three_columns.setStyleSheet(label_style)
        self._style_project_color_button()
        section_label_style = f"color: {self.t('fg_primary')}; font-weight: bold; font-size: 13px;"
        desc_style = f"color: {self.t('fg_secondary')}; font-size: 12px;"
        self._settings_menu_label.setStyleSheet(section_label_style)
        self._settings_menu_desc.setStyleSheet(desc_style)
        self._settings_scan_docs_desc.setStyleSheet(desc_style)
        self._settings_kickstart_desc.setStyleSheet(desc_style)

    def _style_project_color_button(self):
        """Style self._proj_color_btn to preview the currently-chosen color (or a plain
        unstyled look when none is chosen) — split out so both _style_settings_form()
        (theme changes) and the color-pick/clear handlers (value changes) can call it."""
        color = getattr(self, '_proj_color_value', '') or ''
        if color:
            lum = self._color_luminance(color)
            self._proj_color_btn.setStyleSheet(
                f"background-color: {color}; color: {'#000' if lum > 0.5 else '#fff'}; border: 1px solid {self.t('border')}; border-radius: 4px; padding: 6px;"
            )
            self._proj_color_btn.setText(color)
        else:
            self._proj_color_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.t('bg_button')};
                    color: {self.t('fg_primary')};
                    border: 1px solid {self.t('border')};
                    border-radius: 4px;
                    padding: 6px;
                }}
            """)
            self._proj_color_btn.setText("Choose Color...")

    def _populate_settings_form(self):
        """(Re)load field values from the current project's config into the persistent
        settings form built by _build_settings_form(). Called once a project has actually
        been loaded, and again whenever the Settings viewer is entered for a different
        project than last populated (self._settings_loaded_for — see switch_to_viewer_mode()
        and build_main_content()'s mode dispatch) — deliberately NOT called on every
        incidental rebuild, so in-progress edits survive an unrelated refresh_projects()
        triggered elsewhere while this viewer happens to be open."""
        self._proj_project_name.setText(getattr(self, 'config_project_name', None) or "")
        self._proj_project_name.setPlaceholderText(f"Default: {self.get_project_name()}")

        self._proj_color_value = getattr(self, 'config_project_color', None) or ""
        self._style_project_color_button()

        self._proj_use_three_columns.setChecked(self.layout_mode != "focus")

        self._proj_default_viewer.setCurrentText(getattr(self, 'config_column2_default', None) or "")
        self._proj_default_launcher_tab.setCurrentText(getattr(self, 'config_launcher_tab_default', None) or "")

        self._proj_pdf_file.setText(getattr(self, 'config_pdf_file', None) or "")
        self._proj_webview_url.setText(getattr(self, 'config_webview_url', None) or "")
        self._proj_image_file.setText(getattr(self, 'config_image_file', None) or "")
        self._proj_console_path.setText(getattr(self, 'config_console_path', None) or "")
        self._proj_folder_path.setText(getattr(self, 'config_folder_path', None) or "")

        current_terminal = getattr(self, 'config_terminal', None) or ""
        idx = self._proj_terminal.findText(current_terminal)
        if idx >= 0:
            self._proj_terminal.setCurrentIndex(idx)
        else:
            self._proj_terminal.setCurrentText(current_terminal)
        global_terminal = self.get_configured_terminal()
        self._proj_terminal.setToolTip(f"Override global terminal for this project (empty = use global: {global_terminal})")

        per_config_browser = getattr(self, 'config_browser_new_tab', None)
        if per_config_browser is True:
            self._proj_browser_new_tab.setCurrentText("New tab")
        elif per_config_browser is False:
            self._proj_browser_new_tab.setCurrentText("New window")
        else:
            self._proj_browser_new_tab.setCurrentText("(use global setting)")

        kimai_configured = bool(self.settings.get('kimai_url') and self.settings.get('kimai_token'))
        self._settings_form_layout.setRowVisible(self._settings_kimai_label, kimai_configured)
        current_kid = getattr(self, 'config_kimai_project_id', None)
        self._proj_kimai_project_id.setText(str(current_kid) if current_kid else "")

    def create_settings_toolbar(self, parent_layout):
        """Toolbar for the Settings viewer (column2_mode == "settings") — rebuilt fresh
        every build_main_content() call like every other viewer's toolbar (only
        self.settings_form itself, added below this toolbar, is the persistent part).
        No Save button here — there used to be one, but it duplicated the title-bar
        "💾 Save" button (both called the same _save_project_and_exit_edit_mode()), which
        read as two separate save actions. The title-bar button is now the only Save."""
        toolbar = QHBoxLayout()
        title_label = QLabel(f"Project Settings — {self.get_project_name()}")
        title_label.setStyleSheet(f"color: {self.t('fg_primary')}; font-weight: bold; font-size: 13px;")
        toolbar.addWidget(title_label)
        toolbar.addStretch()

        hint_label = QLabel("💾 Save (top right) to save changes")
        hint_label.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 12px;")
        toolbar.addWidget(hint_label)

        parent_layout.addLayout(toolbar)

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

        if item_data:
            current_app = item_data.get("app", "")
        else:
            current_app = self.settings.get("default_app", "")
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

                # Write alias to projectflow_aliases if this is an alias launcher.
                # force=True so edits always overwrite the previous entry.
                if new_app == "alias":
                    alias_name, _, alias_cmd = new_path.partition(' ')
                    self._write_alias_to_file(alias_name.strip(), alias_cmd.strip(), force=True)
                    if hasattr(self, 'status_label'):
                        self.status_label.setText(f"✓ Alias '{alias_name.strip()}' saved — re-source aliases file to activate")
                        self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")

                # Update UI appropriately
                if inline_widget is not None:
                    # Update the inline widget directly without refreshing
                    inline_widget.name_edit.setText(new_name)
                    inline_widget.path_edit.setPlainText(new_path)
                    inline_widget.app_edit.setText(new_app)
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
            self.refresh_projects()

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

    def _add_path_mapping_row(self):
        """Add an empty row to the path mappings table."""
        if not hasattr(self, '_path_mappings_table'):
            return
        row = self._path_mappings_table.rowCount()
        self._path_mappings_table.insertRow(row)
        self._path_mappings_table.setItem(row, 0, QTableWidgetItem("~/"))
        self._path_mappings_table.setItem(row, 1, QTableWidgetItem("~/"))
        self._path_mappings_table.editItem(self._path_mappings_table.item(row, 0))

    def _remove_path_mapping_row(self):
        """Remove the selected row from the path mappings table."""
        if not hasattr(self, '_path_mappings_table'):
            return
        selected = self._path_mappings_table.selectedItems()
        if selected:
            self._path_mappings_table.removeRow(selected[0].row())

    def _apply_settings(self, dialog, save_project_settings=False):
        """Apply settings without closing the dialog"""
        # === Save Project Settings ===
        # Gated on an explicit save_project_settings flag rather than ambient state
        # (column2_mode, edit_mode, hasattr checks) — the _proj_* field widgets are built
        # once in __init__ (see _build_settings_form()) and always exist, so any ambient
        # check risks also firing when this method is called from the unrelated global ⚙️
        # Settings dialog's Apply/OK (which can be opened regardless of which viewer is
        # active or whether an edit session is underway) or from the title-bar Save button
        # while a different viewer tab happens to be frontmost (see the Settings-viewer
        # cog shortcut in the viewer tab row, which exists precisely so you CAN wander off
        # to another tab mid-edit). An explicit flag encodes caller intent directly instead
        # of inferring it — see _save_project_and_exit_edit_mode(), the only caller that
        # passes True.
        if save_project_settings:
            # Layout mode toggle — was the title-bar ⊞/▣ button, now this checkbox.
            # toggle_layout_mode() already does the full switch (splitter sizes, Notes-tab
            # visibility, Group-by-Type default, persistence, refresh) — reuse it as-is.
            if hasattr(self, '_proj_use_three_columns'):
                want_three_col = self._proj_use_three_columns.isChecked()
                if want_three_col == (self.layout_mode == "focus"):
                    self.toggle_layout_mode()

            # Project color (stored in the project config file)
            if hasattr(self, '_proj_color_value'):
                self.config_project_color = self._proj_color_value or None

            # Project name
            self.config_project_name = self._proj_project_name.text().strip() or None
            # Viewer defaults
            self.config_column2_default = self._proj_default_viewer.currentText() or None
            self.config_launcher_tab_default = self._proj_default_launcher_tab.currentText() or None
            self.config_pdf_file = self._proj_pdf_file.text().strip() or None
            self.config_webview_url = self._proj_webview_url.text().strip() or None
            self.config_image_file = self._proj_image_file.text().strip() or None
            self.config_console_path = self._proj_console_path.text().strip() or None
            self.config_folder_path = self._proj_folder_path.text().strip() or None
            self.config_terminal = self._proj_terminal.currentText().strip() or None

            browser_text = self._proj_browser_new_tab.currentText()
            if browser_text == "New tab":
                self.config_browser_new_tab = True
            elif browser_text == "New window":
                self.config_browser_new_tab = False
            else:
                self.config_browser_new_tab = None

            kimai_id_text = self._proj_kimai_project_id.text().strip()
            self.config_kimai_project_id = int(kimai_id_text) if kimai_id_text.isdigit() else None

            # Save config to JSON (columns already updated by tree editing)
            self._save_project_config()

        # === Save Advanced Settings ===
        # Only save if the settings widgets exist (i.e., we're in the full settings dialog)
        if hasattr(self, '_settings_theme_combo'):
            # Save theme
            new_theme = self._settings_theme_combo.currentText()
            old_theme = self.settings.get("theme", "system")
            self.settings["theme"] = new_theme

            # Save startup mode
            _mode_text = self._settings_startup_mode.currentText()
            _mode_val = {"Last opened project": "last_used", "Main project": "main", "Specific project": "specific"}.get(_mode_text, "last_used")
            self.settings["startup_mode"] = _mode_val
            if _mode_val == "specific":
                _sp_data = self._settings_startup_project.currentData()
                if _sp_data:
                    self.settings["startup_project"] = _sp_data
            elif "startup_project" in self.settings:
                del self.settings["startup_project"]

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

            console_backend = self._settings_console_backend.currentData()
            if console_backend and console_backend != "qtconsole":
                self.settings["console_backend"] = console_backend
            elif "console_backend" in self.settings:
                del self.settings["console_backend"]  # qtconsole is the implicit default

            notes_folder = self._settings_notes_folder.text().strip()
            if notes_folder:
                self.settings["notes_folder"] = notes_folder
            elif "notes_folder" in self.settings:
                del self.settings["notes_folder"]

            self.settings["enable_baloo_tags"] = self._settings_baloo.isChecked()
            self.settings["fm_always_tabs"] = self._settings_fm_always_tabs.isChecked()
            self.settings["browser_new_tab"] = self._settings_browser_new_tab.isChecked()
            self.settings["projects_per_row"] = self._settings_projects_per_row.value()
            self.settings["projects_spacing"] = self._settings_projects_spacing.value()

            default_app = self._settings_default_app.currentText().strip()
            if default_app:
                self.settings["default_app"] = default_app
            elif "default_app" in self.settings:
                del self.settings["default_app"]

            joplin_token = self._settings_joplin.text().strip()
            if joplin_token:
                self.settings["joplin_token"] = joplin_token
            elif "joplin_token" in self.settings:
                del self.settings["joplin_token"]

            kimai_url = self._settings_kimai_url.text().strip().rstrip('/')
            if kimai_url:
                self.settings["kimai_url"] = kimai_url
            elif "kimai_url" in self.settings:
                del self.settings["kimai_url"]

            kimai_token = self._settings_kimai_token.text().strip()
            if kimai_token:
                self.settings["kimai_token"] = kimai_token
            elif "kimai_token" in self.settings:
                del self.settings["kimai_token"]

            kimai_csv_folder = self._settings_kimai_csv_folder.text().strip()
            if kimai_csv_folder:
                self.settings["kimai_csv_folder"] = kimai_csv_folder
            elif "kimai_csv_folder" in self.settings:
                del self.settings["kimai_csv_folder"]

            # Save path mappings from the table
            if hasattr(self, '_path_mappings_table'):
                mappings = []
                for row in range(self._path_mappings_table.rowCount()):
                    from_item = self._path_mappings_table.item(row, 0)
                    to_item = self._path_mappings_table.item(row, 1)
                    from_ = from_item.text().strip() if from_item else ""
                    to_ = to_item.text().strip() if to_item else ""
                    if from_ and to_:
                        mappings.append({"from": from_, "to": to_})
                if mappings:
                    self.settings["path_mappings"] = mappings
                elif "path_mappings" in self.settings:
                    del self.settings["path_mappings"]

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
                if hasattr(self.handlers_module, 'set_fm_always_tabs_config'):
                    self.handlers_module.set_fm_always_tabs_config(self.settings.get("fm_always_tabs", False))

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

            # Update project name
            if self.config_project_name:
                config_data["project_name"] = self.config_project_name
            elif "project_name" in config_data:
                del config_data["project_name"]

            # Update viewer defaults
            if self.config_column2_default:
                config_data["column2_default"] = self.config_column2_default
            elif "column2_default" in config_data:
                del config_data["column2_default"]

            if self.config_launcher_tab_default:
                config_data["launcher_tab_default"] = self.config_launcher_tab_default
            elif "launcher_tab_default" in config_data:
                del config_data["launcher_tab_default"]

            if self.config_pdf_file:
                config_data["pdf_file"] = self.config_pdf_file
                # load_notes() prefers a saved pdf_state (remembered last-viewed file/page)
                # over pdf_file, so a stale pdf_state left over from a previously pinned PDF
                # would silently keep loading instead of this newly-set default. Keep it in
                # sync (resetting the remembered page since it's a different file).
                if config_data.get("pdf_state", {}).get("path") != self.config_pdf_file:
                    config_data["pdf_state"] = {"path": self.config_pdf_file, "page": 0}
            elif "pdf_file" in config_data:
                del config_data["pdf_file"]
                if "pdf_state" in config_data:
                    del config_data["pdf_state"]

            if self.config_webview_url:
                config_data["webview_url"] = self.config_webview_url
            elif "webview_url" in config_data:
                del config_data["webview_url"]

            if self.config_image_file:
                config_data["image_file"] = self.config_image_file
                # Same stale-state issue as pdf_state above.
                if config_data.get("image_state", {}).get("path") != self.config_image_file:
                    config_data["image_state"] = {"path": self.config_image_file}
            elif "image_file" in config_data:
                del config_data["image_file"]
                if "image_state" in config_data:
                    del config_data["image_state"]

            if self.config_console_path:
                config_data["console_path"] = self.config_console_path
            elif "console_path" in config_data:
                del config_data["console_path"]

            if self.config_folder_path:
                config_data["folder_path"] = self.config_folder_path
            elif "folder_path" in config_data:
                del config_data["folder_path"]

            if self.config_terminal:
                config_data["terminal"] = self.config_terminal
            elif "terminal" in config_data:
                del config_data["terminal"]

            if self.config_browser_new_tab is not None:
                config_data["browser_new_tab"] = self.config_browser_new_tab
            elif "browser_new_tab" in config_data:
                del config_data["browser_new_tab"]

            # Update project color
            if self.config_project_color:
                config_data["project_color"] = self.config_project_color
            elif "project_color" in config_data:
                del config_data["project_color"]

            # The per-project "Path mapping" checkbox was removed (see _resolve_existing_path())
            # — mapping is now a global, always-on fallback used only when a path is missing,
            # so this flag is obsolete. Drop it opportunistically on the next save of a project
            # that still has it from before.
            config_data.pop("path_mapping", None)

            # Update linked Kimai project ID and name
            kimai_pid = getattr(self, 'config_kimai_project_id', None)
            if kimai_pid:
                config_data["kimai_project_id"] = kimai_pid
            elif "kimai_project_id" in config_data:
                del config_data["kimai_project_id"]
            kimai_pname = getattr(self, 'config_kimai_project_name', None)
            if kimai_pname:
                config_data["kimai_project_name"] = kimai_pname
            elif "kimai_project_name" in config_data:
                del config_data["kimai_project_name"]

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

    def _save_icon_preferences(self):
        """Save icon preferences to JSON file"""
        icon_prefs_file = os.path.join(self.script_dir, "icon_preferences.json")
        try:
            with open(icon_prefs_file, 'w') as f:
                json.dump(self._icon_prefs, f, indent=2)
        except Exception as e:
            print(f"Error saving icon preferences: {e}")
            QMessageBox.warning(self, "Error", f"Failed to save icon preferences: {e}")

    def get_item_button_style(self, clicked=False, mapped=False):
        """Get stylesheet for item buttons (normal, clicked, or mapped-path state).

        'mapped' takes precedence over 'clicked': a pale-blue background/border indicating
        the item's own path wasn't found directly and is only showing via the global
        path-mapping fallback (see _resolve_existing_path()/_path_is_via_mapping()) — the
        same pale blue and reasoning as the folder browser's path-label badge (see UI
        Features → Folder browser / Settings Dialog → path mappings description)."""
        if mapped:
            if self.current_theme == "dark":
                bg, border, fg = "#1c3a52", "#2a5a82", "#8ecbff"
            else:
                bg, border, fg = "#dbeeff", "#a8d4f5", "#1a5a8a"
            return f"""
                QPushButton {{
                    text-align: left;
                    padding-left: 10px;
                    background-color: {bg};
                    color: {fg};
                    border: 1px solid {border};
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    background-color: {self.t('bg_button_hover')};
                    color: {self.t('fg_on_dark')};
                    border: 1px solid {self.t('bg_category_hover')};
                }}
            """
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

    def _build_doc_preview_icon_button(self, path, app):
        """Small preview/external-open icon button for a pooled AI/pinned-notes item (view
        mode only — see the is_pooled render branch in build_main_content()). Mirrors the
        subset of the main per-item preview-button logic (firefox/chrome-wrapped or plain
        local .md/.html/.htm files — the only shapes AI discovery/the pinned notes entry
        ever produce) rather than the full elif chain, since pooled items can't be
        directorydev/image/folder/terminal launchers. Returns None if nothing applies (e.g.
        a .pdf/.txt doc), same as the main branch falling through to a plain button."""
        exp_path = os.path.expanduser(path)
        exp_lower = exp_path.lower()
        is_local = self._is_local_path(path)

        if app in ("firefox", "chrome") and exp_lower.endswith('.md') and is_local:
            btn = QPushButton("📄")
            btn.setToolTip("Open externally" if self.layout_mode == "focus" else "Open in built-in editor")
            btn.clicked.connect(
                lambda checked=False, md=exp_path, a=app: self.open_in_app(md, a, force_external=True) if self.layout_mode == "focus" else self._open_markdown_file(md)
            )
        elif app in ("firefox", "chrome") and exp_lower.endswith(('.html', '.htm')) and is_local:
            btn = QPushButton("🌐")
            btn.setToolTip("Preview / open externally")
            btn.clicked.connect(
                lambda checked=False, p=exp_path, a=app: self.open_in_app(p, a, force_external=True) if self.layout_mode == "focus" else self._open_file_in_webview(p)
            )
        elif app in ("firefox", "chrome"):
            btn = QPushButton("🌐")
            btn.setToolTip("Preview / open externally")
            btn.clicked.connect(
                lambda checked=False, url=path, a=app: self.open_in_app(url, a, force_external=True) if self.layout_mode == "focus" else self.preview_in_webview(url)
            )
        elif exp_lower.endswith(('.html', '.htm')) and is_local:
            btn = QPushButton("🌐")
            btn.setToolTip("Preview in built-in web viewer")
            btn.clicked.connect(
                lambda checked=False, p=exp_path, a=app: self.open_in_app(p, a, force_external=True) if self.layout_mode == "focus" else self._open_file_in_webview(p)
            )
        elif exp_lower.endswith('.md') and is_local:
            btn = QPushButton("📄")
            btn.setToolTip("Open externally" if self.layout_mode == "focus" else "Open in built-in editor")
            btn.clicked.connect(
                lambda checked=False, md=exp_path, a=app: self.open_in_app(md, a, force_external=True) if self.layout_mode == "focus" else self._open_markdown_file(md)
            )
        else:
            return None

        btn.setMaximumWidth(28)
        btn.setMinimumHeight(30)
        btn.setStyleSheet(f"""
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
        return btn

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

        icon = os.path.join(self.script_dir, "assets", "icon.png")

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
        """Add a project to recent projects or folder projects list"""
        config_name = os.path.basename(config_path)

        # Route .projectflow configs to folder_projects
        if config_name == '.projectflow':
            if "folder_projects" not in self.settings:
                self.settings["folder_projects"] = []

            # Remove if already in list
            if config_path in self.settings["folder_projects"]:
                self.settings["folder_projects"].remove(config_path)

            # Add to front of list
            self.settings["folder_projects"].insert(0, config_path)

            # Keep only 20 most recent folder projects
            self.settings["folder_projects"] = self.settings["folder_projects"][:20]
        else:
            # Regular projects go to recent_projects
            if "recent_projects" not in self.settings:
                self.settings["recent_projects"] = []

            # Remove if already in list
            if config_path in self.settings["recent_projects"]:
                self.settings["recent_projects"].remove(config_path)

            # Add to front of list
            self.settings["recent_projects"].insert(0, config_path)

            # Keep up to 100 so we have usage order for all projects
            self.settings["recent_projects"] = self.settings["recent_projects"][:100]

        self.save_settings()

    def save_settings(self):
        """Save user settings to JSON file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def _save_viewer_height(self, height):
        """Persist the viewer column's manually-resized minimum height (ViewerResizeHandle).
        Per-machine, not per-project: how tall feels comfortable depends on the monitor's
        resolution, not the project being viewed."""
        self.settings["viewer_height"] = height
        self.save_settings()

    def _save_splitter_state(self):
        """Persist column splitter positions to settings (mode-specific key)."""
        if hasattr(self, 'columns_splitter'):
            state = self.columns_splitter.saveState()
            key = "splitter_state_focus" if getattr(self, 'layout_mode', 'standard') == 'focus' else "splitter_state"
            self.settings[key] = bytes(state.toHex()).decode()
            self.save_settings()

    def toggle_layout_mode(self):
        """Toggle between Standard (3-col) and Focus (2-col with Notes tab) layouts.
        Persisted per-project, so each project reopens in whichever layout it was last left in.
        Focus layout defaults the launcher column to Group-by-Type."""
        if self.layout_mode == "standard":
            self._enter_focus_layout()
        else:
            self._enter_standard_layout()
        self.group_by_type = (self.layout_mode == "focus")
        self._save_layout_mode_to_config()
        # Rebuild so the launcher column picks up (or drops) Group-by-Type for the new mode.
        self.refresh_projects()

    def _save_layout_mode_to_config(self):
        """Persist the current layout mode into the active project's own config file."""
        if not getattr(self, 'current_config_file', None):
            return
        try:
            config_data = {}
            if os.path.exists(self.current_config_file):
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)
            if self.layout_mode == "focus":
                config_data['layout_mode'] = 'focus'
            else:
                config_data.pop('layout_mode', None)
            with open(self.current_config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
        except Exception as e:
            print(f"Error saving layout_mode: {e}")

    def _save_group_by_type_to_config(self):
        """Persist the current Group-by-Type choice into the active project's own config file,
        so it's remembered next time this project is opened (see _toggle_group_by_type)."""
        if not getattr(self, 'current_config_file', None):
            return
        try:
            config_data = {}
            if os.path.exists(self.current_config_file):
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)
            config_data['group_by_type'] = self.group_by_type
            with open(self.current_config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
        except Exception as e:
            print(f"Error saving group_by_type: {e}")

    def _save_active_launcher_tab_to_config(self):
        """Persist the active Focus-layout launcher tab (Files/Docs/Resources/Apps) into
        the active project's own config file, so it's remembered next time this project is
        opened (see _switch_launcher_tab). "files" is the default, so it's omitted rather
        than written explicitly, keeping default projects' JSON clean."""
        if not getattr(self, 'current_config_file', None):
            return
        try:
            config_data = {}
            if os.path.exists(self.current_config_file):
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)
            if self.active_launcher_tab != "files":
                config_data['active_launcher_tab'] = self.active_launcher_tab
            else:
                config_data.pop('active_launcher_tab', None)
            with open(self.current_config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
        except Exception as e:
            print(f"Error saving active_launcher_tab: {e}")

    def _set_launcher_tab_as_default(self):
        """Pin the currently active Focus-layout launcher tab as this project's default —
        mirrors set_viewer_as_default(), so launcher_tab_default overrides the last-opened
        active_launcher_tab on future loads (see load_config())."""
        if not getattr(self, 'current_config_file', None):
            return
        try:
            config_data = {}
            if os.path.exists(self.current_config_file):
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)
            config_data['launcher_tab_default'] = self.active_launcher_tab
            with open(self.current_config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            self.config_launcher_tab_default = self.active_launcher_tab
            QMessageBox.information(self, "Set Default", f"Set \"{self.active_launcher_tab.title()}\" as default launcher tab.")
        except Exception as e:
            print(f"Error setting launcher tab default: {e}")
            QMessageBox.warning(self, "Error", f"Failed to set default: {e}")

    def _enter_focus_layout(self):
        """Switch to Focus layout: hide right notes column, move notes into viewer tab."""
        if not hasattr(self, 'notes_panel') or not hasattr(self, 'notes_viewer_container'):
            return

        # Save current standard splitter state before changing it
        if hasattr(self, 'columns_splitter'):
            state = self.columns_splitter.saveState()
            self.settings["splitter_state"] = bytes(state.toHex()).decode()

        # Notes panel placement is decided once, at construction time, inside
        # build_main_content() (based on self.layout_mode) — no reparenting needed here.

        # Override the blanket 150px splitter minimum (set in build_main_content(), so no
        # column can be drag-collapsed away entirely in Standard layout) so the right column
        # can actually reach 0 width below. Deliberately NOT calling notepad_column_widget
        # .hide() here though: at this point it still contains the live, persistent
        # notes_webview (about to be discarded and rebuilt fresh into notes_viewer_container by
        # the refresh_projects() call that always follows this method) — hiding it while
        # notes_webview is still inside leaves the QWebEngineView stuck at a stale tiny size
        # after the rebuild reparents it. setMinimumWidth() alone doesn't trigger that.
        if hasattr(self, 'notepad_column_widget'):
            self.notepad_column_widget.setMinimumWidth(0)

        # Apply focus splitter: launcher LEFT (1/3), viewer RIGHT (2/3)
        # Only move launcher_widget — never reparent column2_widget (contains QWebEngineView
        # which breaks if reparented due to renderer process binding).
        if hasattr(self, 'columns_splitter') and hasattr(self, 'launcher_widget'):
            if getattr(self, 'swap_columns', False):
                # Standard order: [column2@0(viewer,left), launcher@1, notes@2]
                # Focus order:    [launcher@0(left), column2@1(viewer,right), notes@2]
                self.launcher_widget.setParent(None)
                self.columns_splitter.insertWidget(0, self.launcher_widget)
            total = self.columns_splitter.width() or 980
            launcher_w = int(total / 3)
            viewer_w = total - launcher_w
            self.columns_splitter.setSizes([launcher_w, viewer_w, 0])

        # Show the Notes viewer tab button
        if hasattr(self, 'viewer_tab_buttons') and 'notes' in self.viewer_tab_buttons:
            self.viewer_tab_buttons['notes'].setVisible(True)

        self.layout_mode = "focus"

    def _enter_standard_layout(self):
        """Switch to Standard layout: restore right notes column, remove Notes viewer tab."""
        if not hasattr(self, 'notes_panel') or not hasattr(self, 'notepad_column_widget'):
            return

        # Save focus splitter state before changing it
        if hasattr(self, 'columns_splitter'):
            state = self.columns_splitter.saveState()
            self.settings["splitter_state_focus"] = bytes(state.toHex()).decode()

        # If the Notes viewer is active, switch away from it first
        if getattr(self, 'column2_mode', '') == 'notes':
            self.switch_to_viewer_mode("folder")

        # Notes panel placement is decided once, at construction time, inside
        # build_main_content() (based on self.layout_mode) — no reparenting needed here.

        # Restore and show the right column
        self.notepad_column_widget.setMinimumWidth(150)
        self.notepad_column_widget.show()

        # Restore original column order if it was reordered for Focus mode
        if hasattr(self, 'columns_splitter') and hasattr(self, 'launcher_widget'):
            if getattr(self, 'swap_columns', False):
                # Focus order:    [launcher@0(left), column2@1(viewer,right), notes@2]
                # Standard order: [column2@0(viewer,left), launcher@1, notes@2]
                self.launcher_widget.setParent(None)
                self.columns_splitter.insertWidget(1, self.launcher_widget)

        # Restore standard splitter state
        if hasattr(self, 'columns_splitter'):
            std_state = self.settings.get("splitter_state")
            if std_state:
                self.columns_splitter.restoreState(QByteArray.fromHex(std_state.encode()))
            else:
                self.columns_splitter.setSizes([1, 1, 1])

        # Hide the Notes viewer tab button
        if hasattr(self, 'viewer_tab_buttons') and 'notes' in self.viewer_tab_buttons:
            self.viewer_tab_buttons['notes'].setVisible(False)

        self.layout_mode = "standard"

    def get_config_file_to_use(self):
        """Determine which config file to use based on settings"""
        # CLI argument always wins
        if self.config_file_arg:
            if os.path.isabs(self.config_file_arg):
                config_path = self.config_file_arg
            else:
                config_path = os.path.join(self.script_dir, self.config_file_arg)
            if os.path.exists(config_path):
                return config_path
            print(f"Warning: Config file '{self.config_file_arg}' not found. Using default config.")

        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        startup_mode = self.settings.get("startup_mode", "last_used")

        # Specific project
        if startup_mode == "specific":
            specific = self.settings.get("startup_project", "")
            if specific and os.path.exists(specific):
                return specific

        # Last opened project
        if startup_mode == "last_used":
            if self.settings.get("last_used_project") and os.path.exists(self.settings["last_used_project"]):
                return self.settings["last_used_project"]

        # Main project (explicit or fallback for all modes)
        if self.settings.get("default_project"):
            config_path = os.path.join(configs_dir, self.settings["default_project"])
            if os.path.exists(config_path):
                return config_path

        # Fall back to standard default
        if os.path.exists(configs_dir):
            configs_default = os.path.join(configs_dir, "projectflow.json")
            if os.path.exists(configs_default):
                return configs_default

        return os.path.join(self.script_dir, "projectflow.json")

    def load_config(self):
        """Load configuration from JSON config file or use defaults"""
        # Only reset Group-by-Type to its layout-linked default when we're actually switching
        # to a (possibly different) project — not on every incidental refresh_projects() call
        # (editing an item, toggling edit mode, etc.), which would otherwise stomp on a manual
        # Group-by-Type toggle made while staying on the same project.
        is_project_switch = self.current_config_file != getattr(self, '_group_default_applied_for', None)
        self._group_default_applied_for = self.current_config_file
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
                # Load default code file path if specified (pinned via the code editor's 📌)
                self.config_code_file = config_data.get('code_file', None)
                # Load default console path if specified
                self.config_console_path = config_data.get('console_path', None)
                # Load default folder path if specified
                self.config_folder_path = config_data.get('folder_path', None)
                # Load default column2 mode (pdf, webview, or image)
                self.config_column2_default = config_data.get('column2_default', None)
                # Load pinned default Focus-layout launcher tab, if any
                self.config_launcher_tab_default = config_data.get('launcher_tab_default', None)
                # Load per-config terminal override
                self.config_terminal = config_data.get('terminal', None)
                # Load project-local notes file path if specified
                self.config_notes_file = config_data.get('notes_file', None)
                # Load project name if specified (for display in title bar)
                self.config_project_name = config_data.get('project_name', None)
                # Load per-project browser new-tab override
                self.config_browser_new_tab = config_data.get('browser_new_tab', None)
                # Load per-project color for the projects section
                self.config_project_color = config_data.get('project_color', None)
                # Load linked Kimai project ID and name
                self.config_kimai_project_id = config_data.get('kimai_project_id', None)
                self.config_kimai_project_name = config_data.get('kimai_project_name', None)
                # Load per-project layout mode (standard/focus) — remembers the last layout
                # this project was viewed in
                self.layout_mode = config_data.get('layout_mode', 'standard')
                # Group-by-Type: remembers this project's last choice (see
                # _toggle_group_by_type/_save_group_by_type_to_config); if never explicitly
                # set, Focus layout defaults the launcher column to Group-by-Type
                if is_project_switch:
                    if 'group_by_type' in config_data:
                        self.group_by_type = bool(config_data['group_by_type'])
                    else:
                        self.group_by_type = (self.layout_mode == "focus")
                    # Focus-layout launcher tab: remembers this project's last choice (see
                    # _switch_launcher_tab/_save_active_launcher_tab_to_config); defaults to
                    # "files" if never explicitly set. A pinned launcher_tab_default (see
                    # _set_launcher_tab_as_default) wins over the last-opened tab, mirroring
                    # how config_column2_default overrides the viewer's last-opened mode.
                    self.active_launcher_tab = config_data.get('active_launcher_tab', 'files')
                    if self.config_launcher_tab_default:
                        self.active_launcher_tab = self.config_launcher_tab_default

                    # Editor tabs (see CodeTabState) — restored here, gated on an actual
                    # project switch, rather than in load_notes() (which reruns on every
                    # incidental refresh and must NOT clobber cached unsaved content —
                    # see self.code_tabs's own comment in __init__). Only path/language are
                    # ever persisted; pending_unsaved_content/dirty always start fresh.
                    self.code_tabs = []
                    self.code_active_index = -1
                    for _tab_data in config_data.get('code_tabs', []):
                        self.code_tabs.append(CodeTabState(_tab_data.get('path'), _tab_data.get('language')))
                    if self.code_tabs:
                        self.code_active_index = config_data.get('code_active_tab', 0)
                        if not (0 <= self.code_active_index < len(self.code_tabs)):
                            self.code_active_index = 0

                    # Terminal tabs (see TerminalTabState) — restored here, gated on an
                    # actual project switch, mirroring Editor tabs above. Unlike Editor
                    # tabs, each terminal tab owns a real ttyd subprocess + port, so
                    # switching projects must actually STOP every tab belonging to the
                    # OUTGOING project first (_teardown_terminal_tabs() — the plain
                    # process-cleanup half of _close_all_terminal_tabs(), WITHOUT its
                    # save_notes() call, which here would wrongly write this NEW project's
                    # still-partially-loaded in-memory state back over its own config file)
                    # — simply reassigning self.terminal_tabs to a fresh list would drop the
                    # only references to those processes without ever terminating them,
                    # leaking one ttyd process + port per open tab on every project switch.
                    # Tabs are restored as inert placeholders (proc=None, webview=None) —
                    # only cwd is ever persisted, since a running shell can't be resumed
                    # across an app restart regardless — and spawned lazily:
                    # build_main_content() below spawns just the active one; the rest wait
                    # until first clicked (see _activate_terminal_tab).
                    self._teardown_terminal_tabs()
                    for _tab_data in config_data.get('terminal_tabs', []):
                        _terminal_cwd = _tab_data.get('cwd')
                        if _terminal_cwd:
                            self.terminal_tabs.append(TerminalTabState(_terminal_cwd))
                    if self.terminal_tabs:
                        self.terminal_active_index = config_data.get('terminal_active_tab', 0)
                        if not (0 <= self.terminal_active_index < len(self.terminal_tabs)):
                            self.terminal_active_index = 0
                    else:
                        self.terminal_active_index = -1

                # For .projectflow configs, resolve relative paths in launchers
                if os.path.basename(self.current_config_file) == '.projectflow':
                    self.resolve_relative_paths_in_config()
            else:
                # Create default config file
                self.create_default_project(self.current_config_file)
                # Use defaults - single column only
                self.COLUMN_1 = self.get_default_column_1()
                self.COLUMN_HEADERS = ["Shortcuts and Actions"]
                self.config_pdf_file = None
                self.config_webview_url = None
                self.config_image_file = None
                self.config_code_file = None
                self.config_console_path = None
                self.config_folder_path = None
                self.config_column2_default = None
                self.config_launcher_tab_default = None
                self.config_terminal = None
                self.config_browser_new_tab = None
                self.config_notes_file = None
                self.config_project_name = None
                self.config_project_color = None
                # create_default_project() (just called above) writes "layout_mode": "focus"
                # into the new file on disk — match that here too, rather than hardcoding
                # 'standard' and silently overriding what was just written, which left a
                # brand-new project opening in Standard layout until the next reload from
                # disk (e.g. switching away and back) finally picked up the real value.
                self.layout_mode = 'focus'
                if is_project_switch:
                    self.group_by_type = (self.layout_mode == "focus")
                    self.active_launcher_tab = 'files'
                    self.code_tabs = []
                    self.code_active_index = -1
                    self._teardown_terminal_tabs()
        except Exception as e:
            raise Exception(f"Error loading config: {str(e)}")

    def resolve_relative_paths_in_config(self):
        """Resolve relative paths (. and ./) in COLUMN_1 items for .projectflow configs"""
        config_dir = os.path.dirname(self.current_config_file)

        for category_dict in self.COLUMN_1:
            for category_name, items in category_dict.items():
                for item in items:
                    if len(item) >= 2:
                        path = item[1]
                        # Handle "." (current directory)
                        if path == ".":
                            item[1] = config_dir
                        # Handle "./" relative paths
                        elif path.startswith("./"):
                            item[1] = os.path.join(config_dir, path[2:])
                        # Handle ". command" pattern (e.g., ". start" for npm)
                        elif path.startswith(". "):
                            item[1] = config_dir + path[1:]  # Replace "." with config_dir

        # Also resolve console_path if it's relative
        if hasattr(self, 'config_console_path') and self.config_console_path:
            if self.config_console_path == ".":
                self.config_console_path = config_dir
            elif self.config_console_path.startswith("./"):
                self.config_console_path = os.path.join(config_dir, self.config_console_path[2:])

        # Also resolve folder_path if it's relative; default to config dir if not set
        if hasattr(self, 'config_folder_path') and self.config_folder_path:
            if self.config_folder_path == ".":
                self.config_folder_path = config_dir
            elif self.config_folder_path.startswith("./"):
                self.config_folder_path = os.path.join(config_dir, self.config_folder_path[2:])
        else:
            self.config_folder_path = config_dir

    def get_project_name(self):
        """Get the display name for the current project.

        Returns project_name from config if set, otherwise derives from filename.
        For .projectflow files without project_name, uses the parent folder name.
        """
        # Use explicit project_name if set in config
        if hasattr(self, 'config_project_name') and self.config_project_name:
            return self.config_project_name

        # Derive from filename
        config_name = os.path.basename(self.current_config_file)

        # For .projectflow, use parent folder name
        if config_name == '.projectflow':
            return os.path.basename(os.path.dirname(self.current_config_file))

        # Remove .json extension
        return os.path.splitext(config_name)[0]

    def get_display_name_for_config_path(self, config_path):
        """Get the display name for any config file path.

        Reads the config to get project_name if set, otherwise derives from filename.
        For .projectflow files without project_name, uses the parent folder name.
        """
        config_name = os.path.basename(config_path)

        # Try to read project_name from config
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                project_name = config_data.get('project_name')
                if project_name:
                    return project_name
        except:
            pass

        # For .projectflow, use parent folder name
        if config_name == '.projectflow':
            return os.path.basename(os.path.dirname(config_path))

        # Remove .json extension and clean up
        return os.path.splitext(config_name)[0]

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

    def _icon_key_for_app(self, app, path=''):
        """Resolve the best icon_preferences key for a launcher.

        Priority:
        1. Generic app aliases (editor/file_manager/terminal) → configured app name
        2. File-extension entries (e.g. ".md", ".pdf") when app is "default"
        3. Original app key as-is
        """
        generic = {
            'editor': self.get_configured_editor,
            'file_manager': self.get_configured_file_manager,
            'terminal': self.get_configured_terminal,
        }
        if app in generic:
            resolved = os.path.basename(generic[app]()).split()[0].lower()
            if resolved in self.APP_INFO:
                return resolved
        if path and app in ('default', 'browser', 'file_manager', 'editor'):
            ext = os.path.splitext(path)[1].lower()
            if ext and ext in self.APP_INFO:
                return ext
        return app

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

    # ------------------------------------------------------------------
    # Shell alias helpers
    # ------------------------------------------------------------------

    def get_aliases_file_path(self):
        projects_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        return os.path.join(projects_dir, "projectflow_aliases")

    def _validate_alias(self, name, command):
        """Return (valid: bool, reason: str). Checks identifier, danger patterns, bash syntax."""
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
            return False, "invalid identifier"
        danger_patterns = [
            r'rm\s+-[rRf]*f[rR]?\s+[/~$]',   # rm -rf /  rm -rf ~  rm -rf $HOME
            r'dd\s+if=\s*/dev/',               # dd if=/dev/...
            r'\bmkfs\b',                       # format filesystem
            r':\(\)\s*\{',                     # fork bomb
        ]
        for pattern in danger_patterns:
            if re.search(pattern, command):
                return False, "dangerous command"
        try:
            result = subprocess.run(
                ['bash', '-n', '-c', f"alias {name}={shlex.quote(command)}"],
                capture_output=True, timeout=3
            )
            if result.returncode != 0:
                return False, "invalid syntax"
        except Exception:
            pass  # If bash check fails, allow through
        return True, ""

    def _resolve_alias_command(self, command):
        """If command is a bare directory path, prefix with 'cd' for the bash alias."""
        expanded = os.path.expanduser(command)
        if os.path.isdir(expanded) and not command.strip().startswith('cd '):
            return f"cd {command.strip()}"
        return command.strip()

    def _flush_pending_alias_write(self):
        """Called by the debounce timer after the user stops typing."""
        if self._pending_alias_write:
            name, command = self._pending_alias_write
            self._pending_alias_write = None
            self._write_alias_to_file(name, command, force=True)
            if hasattr(self, 'status_label'):
                self.status_label.setText(f"✓ Alias '{name}' saved — re-source aliases file to activate")
                self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")

    def _write_alias_to_file(self, name, command, force=False):
        """Add or update one alias in the projectflow_aliases file.

        force=True: replace any existing entry in-place (used on manual save/edit).
        force=False: skip if the exact alias already exists (used during bulk scan).
        """
        if not name or not command:
            return
        command = self._resolve_alias_command(command)
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
            return  # Not a valid bash identifier — skip silently
        aliases_file = self.get_aliases_file_path()
        header = (
            "# ProjectFlow Aliases\n"
            "# Auto-generated — edit via ProjectFlow, not by hand.\n"
            "# To activate in your shell, add to ~/.bashrc:\n"
            f"#   source {aliases_file}\n"
            "\n"
        )
        content = open(aliases_file).read() if os.path.exists(aliases_file) else header

        valid, reason = self._validate_alias(name, command)
        new_line = (f"alias {name}={shlex.quote(command)}"
                    if valid else f"# alias {name}={shlex.quote(command)}  # {reason.upper()}")

        # Match any existing definition of this alias name (commented or active).
        # Use [ \t]* instead of \s* to avoid consuming blank lines above the entry.
        pattern = re.compile(
            r'^[ \t]*#?[ \t]*alias[ \t]+' + re.escape(name) + r'[ \t]*=.*$', re.MULTILINE
        )
        existing = pattern.search(content)
        if existing:
            if not force and existing.group().strip() == new_line.strip():
                return  # Exact duplicate during scan — skip
            content = pattern.sub(new_line, content, count=1)
        else:
            content = content.rstrip('\n') + '\n' + new_line + '\n'

        with open(aliases_file, 'w', encoding='utf-8') as f:
            f.write(content)

        if force:
            self._regenerate_aliases_project()

    def _scan_all_project_aliases(self):
        """Rebuild projectflow_aliases from scratch from all project JSON files.
        Returns (alias_count, projects_scanned) counts."""
        projects_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        aliases_file = self.get_aliases_file_path()
        header = (
            "# ProjectFlow Aliases\n"
            "# Auto-generated — edit via ProjectFlow, not by hand.\n"
            "# To activate in your shell, add to ~/.bashrc:\n"
            f"#   source {aliases_file}\n\n"
        )

        lines = []
        seen_names = set()
        projects_scanned = 0

        archive_dir = os.path.join(projects_dir, '.archive')
        scan_files = [
            os.path.join(projects_dir, f) for f in sorted(os.listdir(projects_dir))
            if f.endswith('.json') and f != 'aliases.json'
        ]
        if os.path.isdir(archive_dir):
            scan_files += [
                os.path.join(archive_dir, f) for f in sorted(os.listdir(archive_dir))
                if f.endswith('.json')
            ]

        for fpath in scan_files:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                projects_scanned += 1
                for column in cfg.get('columns', []):
                    for category in column:
                        if not isinstance(category, dict):
                            continue
                        for items in category.values():
                            for item in items:
                                if isinstance(item, list) and len(item) >= 3 and item[2] == 'alias':
                                    path_field = str(item[1])
                                    alias_name, _, alias_cmd = path_field.partition(' ')
                                    alias_name = alias_name.strip()
                                    alias_cmd = alias_cmd.strip()
                                    if alias_name and alias_cmd and alias_name not in seen_names:
                                        seen_names.add(alias_name)
                                        alias_cmd = self._resolve_alias_command(alias_cmd)
                                        valid, reason = self._validate_alias(alias_name, alias_cmd)
                                        if valid:
                                            lines.append(f"alias {alias_name}={shlex.quote(alias_cmd)}")
                                        else:
                                            lines.append(f"# alias {alias_name}={shlex.quote(alias_cmd)}  # {reason.upper()}")
            except Exception:
                continue

        content = header + '\n'.join(lines) + ('\n' if lines else '')
        with open(aliases_file, 'w', encoding='utf-8') as f:
            f.write(content)

        self._regenerate_aliases_project()
        return len(lines), projects_scanned

    def _do_alias_scan(self):
        """Rebuild the aliases file and show a result dialog."""
        alias_count, projects = self._scan_all_project_aliases()
        aliases_file = self.get_aliases_file_path()
        msg = QMessageBox(self)
        msg.setWindowTitle("Alias Scan Complete")
        msg.setText(
            f"Rebuilt aliases file from {projects} project(s).\n\n"
            f"Total aliases: {alias_count}\n\n"
            f"File: {aliases_file}\n\n"
            "Re-source the file in your terminal to activate changes."
        )
        msg.exec()

    # ------------------------------------------------------------------
    # Aliases project helpers
    # ------------------------------------------------------------------

    def _parse_aliases_file(self):
        """Parse projectflow_aliases and return {alias_name: command} dict."""
        aliases_file = self.get_aliases_file_path()
        result = {}
        if not os.path.exists(aliases_file):
            return result
        with open(aliases_file, 'r', encoding='utf-8') as f:
            for line in f:
                m = re.match(r"^alias\s+(\w+)='(.*)'$", line.strip())
                if m:
                    result[m.group(1)] = m.group(2)
        return result

    def _regenerate_aliases_project(self):
        """Rebuild aliases.json and aliases.html from current data."""
        all_aliases = self._parse_aliases_file()
        if not all_aliases:
            return

        # Scan project JSONs to map alias_name → project_name
        alias_to_project = {}
        aliases_by_project = {}
        projects_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        archive_dir = os.path.join(projects_dir, '.archive')
        regen_files = [
            os.path.join(projects_dir, f) for f in sorted(os.listdir(projects_dir))
            if f.endswith('.json') and f != 'aliases.json'
        ]
        if os.path.isdir(archive_dir):
            regen_files += [
                os.path.join(archive_dir, f) for f in sorted(os.listdir(archive_dir))
                if f.endswith('.json')
            ]

        for fpath in regen_files:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                project_name = cfg.get('project_name', os.path.splitext(os.path.basename(fpath))[0])
                found = []
                for column in cfg.get('columns', []):
                    for category in column:
                        if not isinstance(category, dict):
                            continue
                        for items in category.values():
                            for item in items:
                                if isinstance(item, list) and len(item) >= 3 and item[2] == 'alias':
                                    aname = str(item[1]).split()[0]
                                    if aname in all_aliases and aname not in alias_to_project:
                                        found.append(aname)
                                        alias_to_project[aname] = project_name
                if found:
                    aliases_by_project[project_name] = found
            except Exception:
                continue

        self._build_aliases_html(aliases_by_project, alias_to_project, all_aliases)
        self._build_aliases_config(all_aliases)

    def _build_aliases_html(self, aliases_by_project, alias_to_project, all_aliases):
        """Write notes/aliases.html — self-contained with inline CSS/JS."""
        notes_folder = self.get_notes_folder()
        os.makedirs(notes_folder, exist_ok=True)
        html_path = os.path.join(notes_folder, "aliases.html")

        def card(aname, cmd, proj=""):
            proj_badge = f'<span class="alias-project">{proj}</span>' if proj else ""
            return (
                f'<div class="alias-card" data-alias="{aname}" '
                f'data-project="{proj}" data-command="{cmd}">'
                f'<span class="alias-name">{aname}</span>'
                f'{proj_badge}'
                f'<span class="alias-command">{cmd}</span>'
                f'</div>'
            )

        by_project_html = ""
        for proj_name in sorted(aliases_by_project.keys()):
            cards = "".join(
                card(a, all_aliases.get(a, ""))
                for a in sorted(aliases_by_project[proj_name])
            )
            by_project_html += (
                f'<div class="project-section">'
                f'<h2 class="project-header">{proj_name}</h2>'
                f'<div class="project-aliases">{cards}</div>'
                f'</div>'
            )

        # Aliases not in any project JSON (parsed from file only)
        unassigned = [a for a in sorted(all_aliases) if a not in alias_to_project]
        if unassigned:
            cards = "".join(card(a, all_aliases[a]) for a in unassigned)
            by_project_html += (
                f'<div class="project-section">'
                f'<h2 class="project-header">Other</h2>'
                f'<div class="project-aliases">{cards}</div>'
                f'</div>'
            )

        alpha_html = "".join(
            card(a, all_aliases[a], alias_to_project.get(a, ""))
            for a in sorted(all_aliases.keys())
        )

        count = len(all_aliases)
        plural = "es" if count != 1 else ""

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ProjectFlow Aliases</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, sans-serif; padding: 12px 16px; font-size: 14px;
       background: #f5f7fa; color: #222; }}
.toolbar {{ background: #fff; border: 1px solid #dde2ea; border-radius: 6px;
            padding: 10px 12px; margin-bottom: 14px; display: flex; gap: 10px; align-items: center; }}
#search {{ flex: 1; border: 1px solid #cdd3dd; border-radius: 4px; padding: 6px 10px;
           font-size: 13px; background: #f9fafb; color: #222; }}
.tab-btn {{ padding: 5px 14px; border: 1px solid #b0bac9; border-radius: 4px;
             cursor: pointer; background: #eef1f6; color: #444; font-size: 13px; }}
.tab-btn.active {{ background: #3498db; color: #fff; border-color: #2980b9; }}
.count {{ font-size: 12px; color: #888; white-space: nowrap; }}
.project-header {{ font-size: 12px; font-weight: 700; color: #3498db;
                   text-transform: uppercase; letter-spacing: .06em;
                   padding: 10px 0 4px; border-bottom: 1px solid #dde2ea; margin-bottom: 6px; }}
.project-section:first-child .project-header {{ padding-top: 0; }}
.alias-card {{ display: flex; align-items: baseline; gap: 10px; padding: 4px 8px;
               border-radius: 4px; margin-bottom: 2px; }}
.alias-card:hover {{ background: #eef1f6; }}
.alias-name {{ font-family: monospace; font-size: 13px; font-weight: 600;
               color: #1a5276; min-width: 140px; flex-shrink: 0; }}
.alias-project {{ font-size: 11px; color: #aaa; min-width: 100px; flex-shrink: 0; }}
.alias-command {{ font-family: monospace; font-size: 12px; color: #555; word-break: break-all; }}
@media (prefers-color-scheme: dark) {{
  body {{ background: #0f1218; color: #dde; }}
  .toolbar {{ background: #1a2030; border-color: #2d3748; }}
  #search {{ background: #111827; border-color: #2d3748; color: #dde; }}
  .tab-btn {{ background: #1e2a3c; border-color: #2d3748; color: #aab; }}
  .tab-btn.active {{ background: #2563eb; color: #fff; border-color: #1d4ed8; }}
  .project-header {{ color: #5dade2; border-color: #2d3748; }}
  .alias-card:hover {{ background: #1a2030; }}
  .alias-name {{ color: #7ec8e3; }}
  .alias-project {{ color: #555; }}
  .alias-command {{ color: #8899aa; }}
  .count {{ color: #666; }}
}}
</style>
</head>
<body>
<div class="toolbar">
  <input type="text" id="search" placeholder="Search aliases…" oninput="filterAliases(this.value)">
  <button class="tab-btn active" id="btn-project" onclick="showView('project')">Projects</button>
  <button class="tab-btn" id="btn-alpha" onclick="showView('alpha')">A-Z</button>
  <span class="count">{count} alias{plural}</span>
</div>
<div id="view-project">{by_project_html}</div>
<div id="view-alpha" style="display:none">{alpha_html}</div>
<script>
function showView(v) {{
  document.getElementById('view-project').style.display = v==='project' ? '' : 'none';
  document.getElementById('view-alpha').style.display = v==='alpha' ? '' : 'none';
  document.getElementById('btn-project').className = 'tab-btn' + (v==='project' ? ' active' : '');
  document.getElementById('btn-alpha').className = 'tab-btn' + (v==='alpha' ? ' active' : '');
  filterAliases(document.getElementById('search').value);
}}
function filterAliases(q) {{
  q = q.toLowerCase();
  document.querySelectorAll('.alias-card').forEach(function(el) {{
    var match = !q || el.dataset.alias.includes(q)
                   || el.dataset.command.includes(q)
                   || el.dataset.project.toLowerCase().includes(q);
    el.style.display = match ? '' : 'none';
  }});
  document.querySelectorAll('.project-section').forEach(function(sec) {{
    var vis = Array.from(sec.querySelectorAll('.alias-card')).some(function(c) {{
      return c.style.display !== 'none';
    }});
    sec.style.display = vis ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return html_path

    def _build_aliases_config(self, all_aliases):
        """Write projects/aliases.json from the given alias dict."""
        projects_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        config_path = os.path.join(projects_dir, "aliases.json")
        notes_folder = self.get_notes_folder()
        html_path = os.path.join(notes_folder, "aliases.html")

        items = [
            [aname, f"{aname} {cmd}", "alias"]
            for aname, cmd in sorted(all_aliases.items())
        ]

        config = {
            "project_name": "Aliases",
            "column_headers": ["Aliases"],
            "column2_default": "webview",
            "webview_url": f"file://{html_path}",
            "columns": [[{"All Aliases": items}]]
        }

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        return config_path

    def open_aliases_project(self):
        """Regenerate alias files and switch to the aliases project."""
        self._regenerate_aliases_project()
        projects_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        aliases_config = os.path.join(projects_dir, "aliases.json")
        if os.path.exists(aliases_config):
            self.switch_to_config(aliases_config)

    # ------------------------------------------------------------------

    def get_notes_file_path(self):
        """Get the markdown file path for current config's notes.

        For .projectflow configs with a notes_file field, returns the resolved path.
        Otherwise uses the global notes folder with a filename derived from the config.
        """
        # Check if config has a project-local notes_file setting
        if hasattr(self, 'config_notes_file') and self.config_notes_file:
            notes_path = self.config_notes_file
            # Resolve relative paths based on config file location
            if notes_path.startswith('./') or notes_path == '.':
                config_dir = os.path.dirname(self.current_config_file)
                notes_path = os.path.join(config_dir, notes_path[2:] if notes_path.startswith('./') else '')
            elif not os.path.isabs(notes_path):
                config_dir = os.path.dirname(self.current_config_file)
                notes_path = os.path.join(config_dir, notes_path)
            return os.path.expanduser(notes_path)

        # Default: use global notes folder
        folder = self.get_notes_folder()
        # Derive filename from config name (underscores become hyphens)
        config_name = os.path.basename(self.current_config_file)
        config_name = os.path.splitext(config_name)[0]
        return os.path.join(folder, f"{config_name.replace('_', '-')}.md")

    def get_archive_folder(self):
        """Get the hidden .archive folder within the notes folder.

        For project-local notes, returns .archive in the project folder.
        Otherwise returns .archive in the global notes folder.
        """
        # For project-local notes, use .archive in the project directory
        if hasattr(self, 'config_notes_file') and self.config_notes_file:
            notes_path = self.get_notes_file_path()
            return os.path.join(os.path.dirname(notes_path), ".archive")

        notes_folder = self.get_notes_folder()
        return os.path.join(notes_folder, ".archive")

    def get_archive_file_path(self):
        """Get the archive file path for current config's notes"""
        archive_folder = self.get_archive_folder()

        # For project-local notes, derive name from the notes filename
        if hasattr(self, 'config_notes_file') and self.config_notes_file:
            notes_path = self.get_notes_file_path()
            stem = os.path.splitext(os.path.basename(notes_path))[0]
            new_path = os.path.join(archive_folder, f"{stem}-archive.md")
            # MIGRATION (temporary): rename old same-name archive file if present
            old_path = os.path.join(archive_folder, f"{stem}.md")
            if os.path.exists(old_path) and not os.path.exists(new_path):
                try:
                    os.rename(old_path, new_path)
                except OSError:
                    pass
            return new_path

        # Default: use same naming convention as notes files
        config_name = os.path.basename(self.current_config_file)
        config_name = os.path.splitext(config_name)[0]
        stem = config_name.replace('_', '-')
        new_path = os.path.join(archive_folder, f"{stem}-archive.md")
        # MIGRATION (temporary): rename old same-name archive file if present
        old_path = os.path.join(archive_folder, f"{stem}.md")
        if os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                os.rename(old_path, new_path)
            except OSError:
                pass
        return new_path

    def _migrate_archive_filenames(self):
        """MIGRATION (temporary): rename {name}.md → {name}-archive.md in the global notes .archive folder.
        Safe to remove once all installs have run this at least once."""
        notes_folder = self.settings.get("notes_folder", "")
        if not notes_folder:
            notes_folder = os.path.join(self.script_dir, "notes")
        else:
            notes_folder = os.path.expanduser(notes_folder)
        archive_dir = os.path.join(notes_folder, ".archive")
        if not os.path.isdir(archive_dir):
            return
        for filename in os.listdir(archive_dir):
            if not filename.endswith(".md"):
                continue
            if filename.endswith("-archive.md"):
                continue  # already migrated
            stem = filename[:-3]  # strip .md
            old_path = os.path.join(archive_dir, filename)
            new_path = os.path.join(archive_dir, f"{stem}-archive.md")
            if not os.path.exists(new_path):
                try:
                    os.rename(old_path, new_path)
                except OSError as e:
                    print(f"Archive migration: could not rename {old_path}: {e}")

    def archive_notes(self):
        """Archive current notes to the archive file with a dated separator"""
        session = self._notes_muya_session
        if not session.webview:
            return

        def on_markdown(markdown_content):
            markdown_content = markdown_content or ""

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

            # Clear the live editor (also resets its dirty flag) and the saved notes file
            session.webview.page().runJavaScript("window.__setMuyaMarkdown && window.__setMuyaMarkdown('')")
            self.save_notes("")

            QMessageBox.information(self, "Archive Notes", "Notes archived successfully.")

        session.webview.page().runJavaScript("window.__getMuyaMarkdown ? window.__getMuyaMarkdown() : null", on_markdown)

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
        archive_dialog.setWindowTitle(f"Archive - {self.get_project_name()}")
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

    def load_notes(self):
        """Load notes from markdown file, PDF state and webview state from JSON config"""
        self.notes_data = {}
        # Rebuilt fresh from disk on every call, like pdf_tabs/image_tabs/web_tabs — cheap
        # here since a NotesTabState holds no attached resource, just a path. Deliberately
        # separate from self.notes_md_path (NOT reset here — see that variable's own
        # comment in __init__ for why), which remains the active-tab proxy.
        self.notes_tabs = []
        self.notes_active_index = -1
        # Initialize PDF state variables. self.pdf_tabs is the source of truth for the
        # multi-tab PDF viewer (see PdfTabState); the rest (pdf_doc/pdf_path/
        # pdf_current_page/pdf_page_count) are proxies that always mirror whichever tab is
        # currently active (kept for every existing render/zoom/nav function to use
        # unchanged — see _activate_pdf_tab()).
        self.pdf_tabs = []
        self.pdf_active_index = -1
        self.pdf_doc = None
        self.pdf_current_page = 0
        self.pdf_page_count = 0
        self.pdf_zoom = 1.5
        # Which fit mode the toolbar's fit-toggle button applies — cycled by
        # pdf_toggle_fit_mode(), applied by pdf_apply_fit(). Per-session only (like
        # viewer_height), not persisted per-project or per-machine.
        self.pdf_fit_mode = "width"
        self.pdf_fit_btn = None
        self.pdf_path = None
        self.pdf_label = None
        self.pdf_scroll = None
        # Initialize webview state variables (self.webview itself lives in __init__).
        # self.web_tabs is the source of truth for the multi-tab Web viewer (see
        # WebTabState) — webview_url/webview_md_path remain proxies mirroring whichever
        # tab is active, for every existing webview function to keep using unchanged.
        # Unlike PDF/Image tabs, only ONE real QWebEngineView is ever kept live (the
        # existing persistent self.webview) — switching web tabs re-navigates it rather
        # than creating N Chromium renderer processes (see WebTabState).
        self.web_tabs = []
        self.web_active_index = -1
        self.webview_url = None
        self.webview_md_path = None
        self.webview_url_bar = None
        self.column2_mode = "pdf"  # "pdf", "webview", or "image"
        # Initialize image state variables. self.image_tabs is the source of truth for the
        # multi-tab Image viewer (see ImageTabState, mirrors the PDF viewer's PdfTabState);
        # image_path/image_pixmap/image_zoom remain proxies mirroring whichever tab is
        # active, for every existing render/zoom function to keep using unchanged.
        self.image_tabs = []
        self.image_active_index = -1
        self.image_path = None
        self.image_zoom = 1.0
        self.image_label = None
        self.image_scroll = None
        # Reset code-editor session state — but ONLY on an actual project switch, not on
        # every incidental load_notes() call (this method runs on every refresh_projects(),
        # e.g. toggling edit mode). Unconditionally wiping session.path/dirty on every
        # incidental refresh (the original behavior here) silently broke the Save button —
        # _code_editor_save() early-returns once session.path is None, so any refresh while
        # editing a non-pinned file made Ctrl+S/Save quietly stop working, even though the
        # live CodeMirror buffer still had real unsaved keystrokes sitting in the DOM
        # untouched. Tracked the same way load_config()'s is_project_switch is, since that
        # variable isn't available here (load_notes() runs independently of load_config()'s
        # call in the same refresh_projects() sequence).
        _code_is_project_switch = self.current_config_file != getattr(self, '_code_session_loaded_for', None)
        self._code_session_loaded_for = self.current_config_file
        if hasattr(self, '_code_session') and _code_is_project_switch:
            self._code_session.editing = False
            self._code_session.path = None
            self._code_session.language = None
            self._code_session.pending_content = None
            self._code_session.dirty = False
            self._code_session.dirty_poll_timer.stop()

        try:
            # Load notes from markdown file
            notes_file = self.get_notes_file_path()
            if os.path.exists(notes_file):
                with open(notes_file, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
                self.notes_data = {"content": markdown_content}

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
                        self.notes_data = {"content": markdown_content}
                        # Remove notes from JSON config
                        del config_data["notes"]
                        with open(self.current_config_file, 'w') as f:
                            json.dump(config_data, f, indent=2)

                # Load PDF tabs. "pdf_tabs" (a list) is the current format; "pdf_state" (a
                # single dict) is the pre-multi-tab format — migrated here into a one-item
                # list rather than requiring a one-time file rewrite, the same way
                # load_config() elsewhere translates old config values on read instead of
                # forcing a migration step.
                if "pdf_tabs" in config_data:
                    for tab_data in config_data["pdf_tabs"]:
                        self.pdf_tabs.append(PdfTabState(tab_data.get("path"), tab_data.get("page", 0)))
                    self.pdf_active_index = config_data.get("pdf_active_tab", 0)
                    if not (0 <= self.pdf_active_index < len(self.pdf_tabs)):
                        self.pdf_active_index = 0 if self.pdf_tabs else -1
                elif "pdf_state" in config_data:
                    pdf_state = config_data["pdf_state"]
                    if pdf_state.get("path"):
                        self.pdf_tabs.append(PdfTabState(pdf_state.get("path"), pdf_state.get("page", 0)))
                        self.pdf_active_index = 0
                if 0 <= self.pdf_active_index < len(self.pdf_tabs):
                    active = self.pdf_tabs[self.pdf_active_index]
                    self.pdf_path = active.path
                    self.pdf_current_page = active.page
                # Load webview state. "mode" drives self.column2_mode regardless of tabs
                # (which viewer tab was last active — unrelated to Web-tab content).
                # "web_tabs" (a list) is the current tab-content format; the old single
                # "url" field is migrated into a one-item list on read, classifying it the
                # same way the pre-multi-tab restore logic did (local .md -> markdown,
                # other local file -> html_file, else a plain url).
                if "webview_state" in config_data:
                    webview_state = config_data["webview_state"]
                    self.column2_mode = webview_state.get("mode", "pdf")
                    if "web_tabs" in config_data:
                        for tab_data in config_data["web_tabs"]:
                            self.web_tabs.append(WebTabState(tab_data.get("kind", "url"), tab_data.get("value")))
                        self.web_active_index = config_data.get("web_active_tab", 0)
                        if not (0 <= self.web_active_index < len(self.web_tabs)):
                            self.web_active_index = 0 if self.web_tabs else -1
                    elif webview_state.get("url"):
                        _old_url = webview_state.get("url")
                        _url_obj = QUrl(_old_url)
                        if _url_obj.isLocalFile() and _url_obj.toLocalFile().endswith('.md'):
                            self.web_tabs.append(WebTabState("markdown", _url_obj.toLocalFile()))
                        elif _url_obj.isLocalFile():
                            self.web_tabs.append(WebTabState("html_file", _url_obj.toLocalFile()))
                        else:
                            self.web_tabs.append(WebTabState("url", _old_url))
                        self.web_active_index = 0
                    if 0 <= self.web_active_index < len(self.web_tabs):
                        self.webview_url = self.web_tabs[self.web_active_index].value
                # Load image tabs. "image_tabs" (a list) is the current format;
                # "image_state" (a single dict) is the pre-multi-tab format — migrated here
                # into a one-item list, same pattern as pdf_tabs/pdf_state above.
                if "image_tabs" in config_data:
                    for tab_data in config_data["image_tabs"]:
                        self.image_tabs.append(ImageTabState(tab_data.get("path")))
                    self.image_active_index = config_data.get("image_active_tab", 0)
                    if not (0 <= self.image_active_index < len(self.image_tabs)):
                        self.image_active_index = 0 if self.image_tabs else -1
                elif "image_state" in config_data:
                    image_state = config_data["image_state"]
                    if image_state.get("path"):
                        self.image_tabs.append(ImageTabState(image_state.get("path")))
                        self.image_active_index = 0
                if 0 <= self.image_active_index < len(self.image_tabs):
                    self.image_path = self.image_tabs[self.image_active_index].path

                # Load Notes tabs (Focus layout only, but harmless to read regardless — see
                # NotesTabState). No legacy migration: notes_md_path was never persisted
                # before multi-tab support, so "notes_tabs" is new-key-only territory.
                if "notes_tabs" in config_data:
                    for tab_data in config_data["notes_tabs"]:
                        self.notes_tabs.append(NotesTabState(tab_data.get("path")))
                    self.notes_active_index = config_data.get("notes_active_tab", 0)
                    if not (0 <= self.notes_active_index < len(self.notes_tabs)):
                        self.notes_active_index = 0 if self.notes_tabs else -1

            # Use config-specified PDF file as fallback if no tabs were restored
            if not self.pdf_tabs and hasattr(self, 'config_pdf_file') and self.config_pdf_file:
                self.pdf_tabs.append(PdfTabState(self.config_pdf_file))
                self.pdf_active_index = 0
                self.pdf_path = self.config_pdf_file
                self.pdf_current_page = 0

            # Use config-specified webview URL as fallback if no tabs were restored.
            # Deliberate behavior change from the pre-multi-tab version of this code, which
            # unconditionally overwrote webview_url with the pinned default on every single
            # load — harmless for one value, but would wipe out multiple open web tabs on
            # every project reload. Now matches the PDF/Image tabs' fallback-only
            # precedence: the pinned default only matters when nothing was remembered yet.
            if not self.web_tabs and hasattr(self, 'config_webview_url') and self.config_webview_url:
                self.web_tabs.append(WebTabState("url", self.config_webview_url))
                self.web_active_index = 0
                self.webview_url = self.config_webview_url

            # Use config-specified image file as fallback if no tabs were restored
            if not self.image_tabs and hasattr(self, 'config_image_file') and self.config_image_file:
                self.image_tabs.append(ImageTabState(self.config_image_file))
                self.image_active_index = 0
                self.image_path = self.config_image_file

            # Notes always shows something — fall back to a single tab for the project's
            # own note (path=None) if nothing was restored, mirroring the pre-tab behavior
            # where notes_md_path=None already meant exactly this.
            if not self.notes_tabs:
                self.notes_tabs.append(NotesTabState(None))
                self.notes_active_index = 0

            # Use config-specified console path, falling back to the project's general folder_path
            # (its "home" directory) when no console-specific path was set — otherwise a project
            # with only folder_path set (no console_path) would open the console at wherever the
            # app happens to be running from instead of the project's own folder.
            if hasattr(self, 'config_console_path') and self.config_console_path:
                self.console_path = self.config_console_path
            else:
                self.console_path = getattr(self, 'config_folder_path', None)

            # Use config-specified column2 default mode if set
            if hasattr(self, 'config_column2_default') and self.config_column2_default:
                # "examples" was merged into "help" (now a combined README + Examples tabbed
                # page, accessed via the footer rather than the viewer tab row) — translate
                # old configs that still have this saved rather than silently ignoring them.
                if self.config_column2_default == "examples":
                    self.config_column2_default = "help"
                if self.config_column2_default in ("pdf", "webview", "image", "help", "console", "folder", "time", "notes", "code"):
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
                if hasattr(handlers_module, 'set_fm_always_tabs_config'):
                    handlers_module.set_fm_always_tabs_config(self.settings.get("fm_always_tabs", False))

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

    def detect_default_browser(self):
        """Detect the system default browser. Returns a friendly name like 'firefox'."""
        try:
            result = subprocess.run(
                ['xdg-settings', 'get', 'default-web-browser'],
                capture_output=True, text=True, timeout=2
            )
            desktop = result.stdout.strip().lower()
            for name in ('firefox', 'chromium', 'chrome', 'epiphany', 'opera', 'brave', 'vivaldi', 'konqueror'):
                if name in desktop:
                    return name
        except Exception:
            pass
        if shutil.which('firefox'):
            return 'firefox'
        if shutil.which('chromium'):
            return 'chromium'
        return 'browser'

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

    def _open_file_manager(self, path):
        """Open a path in the configured file manager, with optional home tab."""
        fm = self.get_configured_file_manager()
        if self.settings.get("fm_always_tabs", False):
            home = os.path.expanduser("~")
            paths = [home, path] if path != home else [path]
            subprocess.Popen([fm] + paths, start_new_session=True)
        else:
            subprocess.Popen([fm, path], start_new_session=True)

    def get_configured_terminal(self):
        """Get the configured terminal, with auto-detection fallback."""
        # Per-config terminal overrides global setting
        terminal = getattr(self, 'config_terminal', None) or self.settings.get("terminal", "")
        if not terminal:
            terminal = self.detect_default_terminal()
        return terminal

    def resolve_console_backend(self):
        """Resolve the "console_backend" setting to an actual backend to use: "qtconsole"
        (default — no behavior change for existing users) or "ttyd" (real terminal via a
        loopback-only ttyd process embedded in a QWebEngineView). "auto" uses ttyd only if
        the binary is found on PATH, else falls back to qtconsole."""
        backend = self.settings.get("console_backend", "qtconsole")
        if backend == "auto":
            return "ttyd" if shutil.which("ttyd") else "qtconsole"
        if backend == "ttyd" and not shutil.which("ttyd"):
            return "qtconsole"
        return backend

    def _get_terminal_command(self, shell_cmd, hold=False, interactive=False):
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
            bash_flags = ["-i", "-c"] if interactive else ["-c"]
            terminal_cmd.extend(["bash"] + bash_flags + [shell_cmd])
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

    def save_notes(self, notes_markdown=None):
        """Save notes to markdown file, PDF/webview state to JSON config"""
        try:
            # Save notes to markdown file if provided
            if notes_markdown is not None:
                notes_file = self.get_notes_file_path()
                folder = self.get_notes_folder()
                os.makedirs(folder, exist_ok=True)
                with open(notes_file, 'w', encoding='utf-8') as f:
                    f.write(notes_markdown)

            # Save PDF/webview state to JSON config
            config_data = {}
            if os.path.exists(self.current_config_file):
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)

            # Remove legacy notes from JSON if present
            if "notes" in config_data:
                del config_data["notes"]

            # Update PDF state. self.pdf_current_page can change via page-nav buttons
            # without going through _activate_pdf_tab(), so flush it back into the active
            # tab's own record first — pdf_current_page is just a proxy for "whichever tab
            # is active" (see PdfTabState/_activate_pdf_tab), the list is the source of truth.
            if 0 <= self.pdf_active_index < len(getattr(self, 'pdf_tabs', [])):
                self.pdf_tabs[self.pdf_active_index].page = self.pdf_current_page
            if self.pdf_tabs:
                config_data["pdf_tabs"] = [{"path": t.path, "page": t.page} for t in self.pdf_tabs]
                config_data["pdf_active_tab"] = self.pdf_active_index
            else:
                config_data.pop("pdf_tabs", None)
                config_data.pop("pdf_active_tab", None)
            # Legacy single-PDF key, kept mirroring the active tab — lets a rollback to a
            # version without multi-tab support (or any external tooling) still see
            # something sensible instead of a suddenly-missing key.
            if self.pdf_path:
                config_data["pdf_state"] = {
                    "path": self.pdf_path,
                    "page": self.pdf_current_page
                }
            elif "pdf_state" in config_data:
                del config_data["pdf_state"]

            # Update webview state. "mode" is unrelated to Web-tab content (it's which
            # viewer tab was last active, restored regardless of tabs) so it always gets
            # written. "url" is kept as a legacy mirror of the active tab's value (same
            # "harmless vestige once the list exists" reasoning as pdf_state/image_state)
            # — only meaningful for non-markdown tabs, since a markdown tab's value is a
            # local path, not really a "url" in the pre-multi-tab sense, but harmless
            # either way since load_notes() only consults it when web_tabs is absent.
            config_data["webview_state"] = {
                "url": self.webview_url,
                "mode": self.column2_mode
            }
            if self.web_tabs:
                config_data["web_tabs"] = [{"kind": t.kind, "value": t.value} for t in self.web_tabs]
                config_data["web_active_tab"] = self.web_active_index
            else:
                config_data.pop("web_tabs", None)
                config_data.pop("web_active_tab", None)

            # Update image tabs — mirrors the PDF tabs handling above.
            if self.image_tabs:
                config_data["image_tabs"] = [{"path": t.path} for t in self.image_tabs]
                config_data["image_active_tab"] = self.image_active_index
            else:
                config_data.pop("image_tabs", None)
                config_data.pop("image_active_tab", None)
            # Legacy single-image key, kept mirroring the active tab (same reasoning as
            # pdf_state above).
            if self.image_path:
                config_data["image_state"] = {
                    "path": self.image_path
                }
            elif "image_state" in config_data:
                del config_data["image_state"]

            # Update Notes tabs. Skipped entirely (keys removed) when it's just the trivial
            # single "project's own note" tab — the common case for most projects — so a
            # plain project's JSON doesn't gain clutter for a feature it never actually uses.
            _notes_is_trivial = len(self.notes_tabs) <= 1 and (not self.notes_tabs or self.notes_tabs[0].path is None)
            if not _notes_is_trivial:
                config_data["notes_tabs"] = [{"path": t.path} for t in self.notes_tabs]
                config_data["notes_active_tab"] = self.notes_active_index
            else:
                config_data.pop("notes_tabs", None)
                config_data.pop("notes_active_tab", None)

            # Update Editor tabs — path/language only, NEVER pending_unsaved_content/dirty
            # (session-only, see CodeTabState's docstring for why actual code content has
            # no business being written into the project's launcher-config JSON).
            if self.code_tabs:
                config_data["code_tabs"] = [{"path": t.path, "language": t.language} for t in self.code_tabs]
                config_data["code_active_tab"] = self.code_active_index
            else:
                config_data.pop("code_tabs", None)
                config_data.pop("code_active_tab", None)

            # Update Terminal tabs — cwd only, NEVER proc/port/webview/ready (all
            # runtime-only, see TerminalTabState's docstring: a running shell can't be
            # resumed across an app restart regardless, so restoring "the same tabs" means
            # fresh shells at the same directories, not resumed sessions). Skipped entirely
            # (keys removed) when it's just the trivial single tab at the project's own
            # default directory — the common case — mirroring Notes tabs' own triviality
            # check above, so a plain project's JSON doesn't gain clutter for a feature it
            # never actually customized.
            _default_terminal_cwd = os.path.expanduser(getattr(self, 'console_path', None) or "~")
            _terminal_is_trivial = (
                len(self.terminal_tabs) <= 1
                and (not self.terminal_tabs or self.terminal_tabs[0].cwd == _default_terminal_cwd)
            )
            if not _terminal_is_trivial:
                config_data["terminal_tabs"] = [{"cwd": t.cwd} for t in self.terminal_tabs]
                config_data["terminal_active_tab"] = self.terminal_active_index
            else:
                config_data.pop("terminal_tabs", None)
                config_data.pop("terminal_active_tab", None)

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
            elif self.column2_mode == "folder":
                if not hasattr(self, 'folder_current_path') or not self.folder_current_path:
                    QMessageBox.information(self, "Set Default", "No folder path set.")
                    return
                resource_key = "folder_path"
                resource_value = self.folder_current_path
            elif self.column2_mode == "code":
                if not self._code_session.path:
                    QMessageBox.information(self, "Set Default", "No code file loaded to set as default.")
                    return
                resource_key = "code_file"
                resource_value = self._code_session.path
            elif self.column2_mode == "time":
                resource_key = None
                resource_value = None
            elif self.column2_mode == "notes":
                resource_key = None
                resource_value = None
            else:
                return

            # Load existing config
            config_data = {}
            if os.path.exists(self.current_config_file):
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)

            # Update the resource and column2_default
            if resource_key:
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
            elif self.column2_mode == "code":
                self.config_code_file = resource_value
            elif self.column2_mode == "console":
                self.config_console_path = resource_value
            elif self.column2_mode == "folder":
                self.config_folder_path = resource_value
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
                        "Websites": [
                            ["GitHub", "https://github.com/", "browser"],
                            ["DuckDuckGo", "https://duckduckgo.com/", "browser"]
                        ]
                    },
                    {
                        "Places": [
                            ["Home", "~/", "file_manager"]
                        ]
                    }
  
                ]
            ],
            "column2_default": "help",
            "layout_mode": "focus"
        }

        with open(config_file, 'w') as f:
            json.dump(default_project, f, indent=2)

    def get_default_column_1(self):
        """In-memory fallback matching create_default_project()'s own template — kept in
        sync with it manually, since this returns Python objects for a fresh project's
        self.COLUMN_1 (used before that project's JSON is ever read back off disk) while
        create_default_project() writes the on-disk JSON template. Lists (not tuples) to
        match what loading real JSON produces, since COLUMN_1 items get mutated in place
        (drag-reorder, edit) elsewhere."""
        return [
            {
                "Websites": [
                    ["GitHub", "https://github.com/", "browser"],
                    ["DuckDuckGo", "https://duckduckgo.com/", "browser"]
                ]
            },
            {
                "Places": [
                    ["Home", "~/", "file_manager"]
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
        # Create a clean display name from project name
        display_name = self.get_project_name().replace('_config', '').replace('_', ' ').replace('-', ' ').title()

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

        # Detach webview before the central widget is replaced so it isn't
        # deleted — the same QWebEngineView (and its profile/cookies) is
        # re-used for the lifetime of the app.
        # setParent() already hides the widget; addWidget() in build_main_content
        # will re-parent and show it again as part of the new layout.
        if self.webview is not None:
            self.webview.setParent(self)
        if self.notes_webview is not None:
            self.notes_webview.setParent(self)
        # Each open terminal tab owns its own QWebEngineView (see TerminalTabState) — unlike
        # notes_webview/code_webview (one persistent webview shared by all tabs of that
        # type), so every tab's webview needs this same detach-before-teardown treatment,
        # not just one. A tab restored from disk but never yet activated has webview=None
        # (nothing spawned yet — see _spawn_terminal_tab) and is simply skipped here.
        for _terminal_tab in self.terminal_tabs:
            if _terminal_tab.webview is not None:
                _terminal_tab.webview.setParent(self)
        if self.code_webview is not None:
            self.code_webview.setParent(self)
        # settings_form is a plain QWidget (not a QWebEngineView, so it doesn't have the
        # "breaks if reparented after being shown" issue the webviews above have) but still
        # needs this same detach-before-teardown treatment: it's the single persistent form
        # whose in-progress field values (_proj_project_name etc.) must survive this rebuild
        # — see _build_settings_form()'s docstring. Without this it would be destroyed along
        # with the old central widget's tree by the setCentralWidget() call just below.
        if getattr(self, 'settings_form', None) is not None:
            self.settings_form.setParent(self)

        # Create central widget and layout
        central_widget = QWidget()
        central_widget.setStyleSheet(f"background-color: {self.t('bg_primary')};")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create the Scroll Area and the "Inner" Container
        self.main_scroll = QScrollArea()
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setStyleSheet(f"QScrollArea {{ background-color: {self.t('bg_primary')}; border: none; }}")
        scroll_content_widget = QWidget()  # This widget will hold all your UI
        scroll_content_widget.setStyleSheet(f"background-color: {self.t('bg_primary')};")
        scroll_layout = QVBoxLayout(scroll_content_widget)  # The new "home" for your elements
        scroll_layout.setContentsMargins(11, 11, 11, 0)  # No bottom margin so footer hugs window edge

        # Connect them
        self.main_scroll.setWidget(scroll_content_widget)
        main_layout.addWidget(self.main_scroll)  # Put the scroll area into the main window

        # Add title bar with project name and status
        self.create_title_bar(scroll_layout)

        # Build main content
        self.build_main_content(scroll_layout)

        # Apply Focus layout immediately if that was the saved mode
        if self.layout_mode == "focus":
            self._enter_focus_layout()

        # Reapply zen mode's collapsed columns after every rebuild — launcher_widget/
        # notepad_column_widget/columns_splitter are recreated fresh by build_main_content()
        # each time and don't retain this on their own (see _apply_zen_mode()'s docstring).
        # Must run after _enter_focus_layout() above, since that also touches splitter sizes.
        if self._zen_mode:
            self._apply_zen_mode()

    def create_title_bar(self, parent_layout):
        """Create a title bar with project name on left and status on right"""
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(5, 5, 5, 10)

        # Hamburger mega-menu button — a fast, additional way to switch projects (Pinned/
        # Recent/All/Folder side by side in one popup) without scrolling to the always-visible
        # Projects section below, which is untouched by this. See _show_project_mega_menu().
        self.mega_menu_btn = QPushButton()
        self.mega_menu_btn.setIcon(self._hamburger_icon())
        self.mega_menu_btn.setIconSize(QSize(18, 18))
        self.mega_menu_btn.setFixedSize(30, 30)
        self.mega_menu_btn.setToolTip("Switch project")
        self.mega_menu_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
            }}
            QPushButton:pressed {{
                background-color: {self.t('bg_category_hover')};
            }}
        """)
        self.mega_menu_btn.clicked.connect(self._show_project_mega_menu)
        title_bar.addWidget(self.mega_menu_btn)

        # Project title on left (clickable search)
        config_name = self.get_project_name()
        if config_name.endswith('_config'):
            config_name = config_name[:-7]
        config_name = config_name.replace('_', ' ').replace('-', ' ').upper()

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
            edit_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
            edit_shortcut.activated.connect(self.toggle_edit_mode)
            save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
            save_shortcut.activated.connect(self._on_global_ctrl_s)
            fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
            fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
            zen_shortcut = QShortcut(QKeySequence("Ctrl+F11"), self)
            zen_shortcut.activated.connect(self.toggle_zen_mode)
            self._search_shortcuts_created = True

        title_bar.addStretch()

        # Status label on right
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 12px;")
        title_bar.addWidget(self.status_label)

        # Edit toolbar on far right — buttons always use the same style
        _in_edit = getattr(self, 'edit_mode', False)

        # The Edit Project/Save button — the only top-right title-bar button now (Project
        # Details/Scan Docs/path-mapping all moved into the Settings viewer itself, see
        # _build_settings_form(); the Layout toggle moved there earlier too). Styled like
        # the footer buttons (New Project, Settings, etc: bg_button + a visible border)
        # rather than the old green edit-toolbar style, with a border specifically so it
        # reads as distinct from the plain app background instead of blending into it.
        _topright_btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QPushButton:checked {{
                background-color: {self.t('bg_success')};
                color: {self.t('fg_on_dark')};
                border-color: {self.t('bg_success')};
            }}
        """

        self.edit_project_btn = QPushButton("  💾 Save" if _in_edit else "  ✏️  Edit Project")
        self.edit_project_btn.setCheckable(True)
        self.edit_project_btn.setChecked(_in_edit)
        self.edit_project_btn.setToolTip("Save and exit edit mode" if _in_edit else "Edit project shortcuts, launchers, and settings")
        self.edit_project_btn.setStyleSheet(_topright_btn_style)
        self.edit_project_btn.clicked.connect(self.toggle_edit_mode)
        title_bar.addWidget(self.edit_project_btn)

        parent_layout.addLayout(title_bar)

    def focus_project_search(self):
        """Focus the project search input (called by keyboard shortcut)"""
        if hasattr(self, 'title_search'):
            self.title_search.enter_search_mode()

    def _show_project_mega_menu(self):
        """Popup mega-menu for fast project switching (☰ button, top-left of title bar) —
        Pinned/Recent/All Projects/Folder Projects/By Color side by side, plus live search.
        Purely additive: the always-visible Projects section (create_projects_section()) is
        unaffected. Uses QWidgetAction to embed a fully custom widget inside a QMenu — the
        standard Qt pattern for rich dropdown ("mega") menus, giving native popup
        outside-click-and-Escape dismissal for free. Sized to ~90% of the current screen
        (rather than QMenu's default shrink-to-content sizing) and centered on it, deliberately
        oversized so it reads as a full pop-over rather than a small dropdown — the ~10%
        margin left on each side is what keeps it legible as an overlay rather than looking
        like it replaced the whole window."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self.t('bg_primary')};
                border: 1px solid {self.t('border')};
            }}
        """)
        screen = self.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry()
        menu_width = int(avail.width() * 0.9)
        menu_height = int(avail.height() * 0.9)

        content = self._build_project_mega_menu_content(menu)
        content.setFixedSize(menu_width, menu_height)
        action = QWidgetAction(menu)
        action.setDefaultWidget(content)
        menu.addAction(action)

        pos = QPoint(avail.x() + (avail.width() - menu_width) // 2,
                     avail.y() + (avail.height() - menu_height) // 2)
        menu.exec(pos)

    def _build_project_mega_menu_content(self, menu):
        """Builds the root widget for the project mega-menu popup (see
        _show_project_mega_menu()) — five columns (Pinned/Recent/All Projects/Folder
        Projects/By Color) plus a live search box filtering across all of them at once,
        mirroring the launcher search box's widget-visibility-toggling pattern rather than
        rebuilding on every keystroke. Archive is deliberately excluded — already the
        deliberately de-emphasized mode in the main Projects section; a quick-switch menu
        shouldn't surface archived projects by default. Column data is read directly from
        settings (the same sources create_projects_section()'s _populate_*() methods use)
        rather than calling those methods, since they render into self.projects_layout and
        carry UI (drag-to-pin zones, sort-toggle headers) that doesn't belong in a transient
        popup. Columns are given equal stretch and each scroll area is added with its own
        stretch factor so, combined with the near-full-screen fixed size set by the caller,
        the whole popup's space is actually used rather than shrinking to fit its content."""
        root = QWidget()
        root.setStyleSheet(f"background-color: {self.t('bg_primary')};")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(18)

        search_input = QLineEdit()
        search_input.setPlaceholderText("Search projects…")
        search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 5px;
                padding: 10px 12px;
                font-size: 14px;
            }}
        """)
        root_layout.addWidget(search_input)

        columns_row = QHBoxLayout()
        columns_row.setSpacing(24)
        root_layout.addLayout(columns_row, 1)

        search_refs = []  # (container_widget, lowercased display name) across all columns
        column_scroll_areas = []  # (scroll_area, [container_widgets in this column])

        def add_column(title, config_paths, empty_text, is_pinned, icon=None):
            col_widget = QWidget()
            col_layout = QVBoxLayout(col_widget)
            col_layout.setContentsMargins(0, 0, 0, 0)
            col_layout.setSpacing(10)

            header_style = f"color: {self.t('fg_secondary')}; font-size: 13px; font-weight: bold;"
            if icon is None:
                header = QLabel(title)
                header.setStyleSheet(header_style)
                col_layout.addWidget(header)
            else:
                # Used for "All Projects" instead of the 📁/📂 emoji — those render as a
                # yellow/manila folder in most color-emoji fonts. Never use a yellow folder
                # glyph for folders/files anywhere in this project (user preference — see
                # CLAUDE.md/_folder_icon()'s own docstring, which already avoids this same
                # thing for the folder-browser icon). Reuses the app's existing hand-drawn
                # blue folder icon (_blue_folder_icon()) instead, for consistency.
                header_row = QWidget()
                header_row_layout = QHBoxLayout(header_row)
                header_row_layout.setContentsMargins(0, 0, 0, 0)
                header_row_layout.setSpacing(5)
                icon_label = QLabel()
                icon_label.setPixmap(icon.pixmap(16, 16))
                header_row_layout.addWidget(icon_label)
                text_label = QLabel(title)
                text_label.setStyleSheet(header_style)
                header_row_layout.addWidget(text_label)
                header_row_layout.addStretch(1)
                col_layout.addWidget(header_row)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            scroll_content = QWidget()
            scroll_layout = QVBoxLayout(scroll_content)
            scroll_layout.setContentsMargins(0, 0, 0, 4)
            scroll_layout.setSpacing(8)

            column_containers = []
            if not config_paths:
                empty_label = QLabel(empty_text)
                empty_label.setStyleSheet(f"color: {self.t('fg_muted')}; font-size: 12px; padding: 8px 0;")
                empty_label.setWordWrap(True)
                scroll_layout.addWidget(empty_label)
            else:
                for path in config_paths:
                    # flow_managed=True (Expanding button, no fixed width) rather than the
                    # fixed-120px path — that fixed width plus the arrow buttons is wider than
                    # a narrow mega-menu column, which was producing an unwanted horizontal
                    # scrollbar alongside the vertical one. Expanding + setWidgetResizable(True)
                    # keeps buttons locked to the scroll area's actual viewport width instead.
                    btn_container = self._create_config_button(
                        path, is_pinned=is_pinned, draggable=False, flow_managed=True,
                        on_select=menu.close
                    )
                    scroll_layout.addWidget(btn_container)
                    display_name = self.get_display_name_for_config_path(path)
                    search_refs.append((btn_container, display_name.lower()))
                    column_containers.append(btn_container)

            scroll_layout.addStretch(1)
            scroll.setWidget(scroll_content)
            col_layout.addWidget(scroll, 1)
            columns_row.addWidget(col_widget, 1)
            column_scroll_areas.append((scroll, column_containers))

        pinned_paths = [p for p in self.settings.get("pinned_projects", [])
                        if os.path.exists(p) and '/.archive/' not in p]
        add_column("📌 Pinned", pinned_paths, "No pinned projects yet.", is_pinned=True)

        recent_paths = [p for p in self.settings.get("recent_projects", [])
                        if os.path.exists(p) and '/.archive/' not in p][:10]
        add_column("🕐 Recent", recent_paths, "No recent projects yet.", is_pinned=False)

        # Computed once, up front, since both "By Color" and "All Projects" derive from the
        # same full project list — By Color is just a different ordering of it.
        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        all_paths = []
        if os.path.isdir(configs_dir):
            all_paths = sorted(
                (os.path.join(configs_dir, f) for f in os.listdir(configs_dir) if f.endswith('.json')),
                key=lambda p: os.path.basename(p).lower()
            )

        # By Color — same ordering as the main Projects section's own 🎨 sort
        # (_populate_color_sorted_projects()): custom color_order priority, uncolored last.
        # Reuses _build_color_cache()/_sorted_colors() rather than duplicating that logic.
        # Placed before "All Projects" (A–Z) per user request.
        self._build_color_cache()
        project_colors = getattr(self, '_color_cache', {})
        unique_colors = list(set(project_colors.values()))
        ordered_colors = self._sorted_colors(unique_colors)
        color_sorted_paths = []
        for color in ordered_colors:
            color_sorted_paths += [p for p in all_paths if project_colors.get(p) == color]
        color_sorted_paths += [p for p in all_paths if not project_colors.get(p)]
        add_column("🎨 By Color", color_sorted_paths, "No projects found.", is_pinned=False)

        # Icon (not emoji) here — see add_column()'s icon branch for why: 📁/📂 render as a
        # yellow/manila folder in most color-emoji fonts.
        add_column("All Projects (A–Z)", all_paths, "No projects found.", is_pinned=False,
                   icon=self._blue_folder_icon())

        folder_paths = [p for p in self.settings.get("folder_projects", []) if os.path.exists(p)]
        add_column("🗂 Folder Projects", folder_paths, "No folder projects yet.", is_pinned=False)

        def on_search_text_changed(text):
            needle = text.strip().lower()
            for container, name_lower in search_refs:
                container.setVisible(not needle or needle in name_lower)
            for scroll, containers in column_scroll_areas:
                scroll.setVisible(not containers or any(c.isVisible() for c in containers))

        search_input.textChanged.connect(on_search_text_changed)

        return root

    def create_projects_section(self, parent_layout):
        """Create unified projects section with toggle between recent, alphabetical, pinned modes"""
        # Initialize mode state (persisted across sessions)
        if not hasattr(self, 'projects_mode'):
            self.projects_mode = self.settings.get('projects_mode', 'recent')
        if not hasattr(self, 'projects_sort_reverse'):
            self.projects_sort_reverse = self.settings.get('projects_sort_reverse', False)
        if not hasattr(self, 'recent_compact'):
            self.recent_compact = self.settings.get('recent_compact', True)
        if not hasattr(self, 'pinned_compact'):
            self.pinned_compact = self.settings.get('pinned_compact', True)
        if not hasattr(self, 'active_color_filter'):
            self.active_color_filter = None
        if not hasattr(self, 'filter_uncolored'):
            self.filter_uncolored = False
        if not hasattr(self, 'color_sort_active'):
            self.color_sort_active = False
        if not hasattr(self, 'color_sort_reverse'):
            self.color_sort_reverse = False

        # Shared button styles — same sizing for all three left tab buttons
        self._toggle_btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_muted')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                font-size: 11px;
                padding: 3px 8px;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """
        self._tab_active_style = f"""
            QPushButton {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-bottom: 2px solid {self.t('bg_category')};
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
                padding: 3px 8px;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """

        # Layout: [🕐] [📌] [A–Z]  [left_line] [title] [right_line]  [Archive]
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(4)

        # Left group: three mode buttons
        self.recent_projects_btn = QPushButton()
        self.recent_projects_btn.clicked.connect(lambda: self.switch_projects_mode('recent'))
        header_row.addWidget(self.recent_projects_btn)

        self.pinned_projects_btn = QPushButton()
        self.pinned_projects_btn.clicked.connect(lambda: self.switch_projects_mode('pinned'))
        header_row.addWidget(self.pinned_projects_btn)

        self.main_projects_btn = QPushButton()
        self.main_projects_btn.clicked.connect(lambda: self.switch_projects_mode('alphabetical'))
        header_row.addWidget(self.main_projects_btn)

        self.folder_projects_btn = QPushButton()
        # The app's own blue folder icon, not QIcon.fromTheme("folder")/SP_DirIcon — both
        # render as a yellow/manila folder on many system icon themes, which this project
        # deliberately avoids everywhere else (see _folder_icon()'s own docstring). Never use
        # a yellow folder glyph for folders/files anywhere in this project.
        self.folder_projects_btn.setIcon(self._blue_folder_icon())
        self.folder_projects_btn.setToolTip("Folder projects")
        self.folder_projects_btn.clicked.connect(lambda: self.switch_projects_mode('folder'))
        header_row.addWidget(self.folder_projects_btn)

        # Color sort button — lives beside the mode buttons on the left
        self.color_sort_btn = QPushButton("🎨")
        self.color_sort_btn.setToolTip("Sort all projects by color")
        self.color_sort_btn.setStyleSheet(self._toggle_btn_style)
        self.color_sort_btn.clicked.connect(self._toggle_color_sort)
        header_row.addWidget(self.color_sort_btn)

        header_row.addSpacing(6)

        # Inline color swatches — grow between the buttons and the title label
        self.color_strip_widget = QWidget()
        self.color_strip_layout = QHBoxLayout(self.color_strip_widget)
        self.color_strip_layout.setContentsMargins(0, 0, 0, 0)
        self.color_strip_layout.setSpacing(3)
        header_row.addWidget(self.color_strip_widget)

        header_row.addSpacing(4)

        # Header label (reflects current mode + sub-state)
        self.projects_header_label = QLabel(self._get_projects_title())
        self.projects_header_label.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 12px;")
        header_row.addWidget(self.projects_header_label)

        header_row.addStretch(1)

        # Right: Archived (hides itself when active)
        self.archive_projects_btn = QPushButton("Archived")
        self.archive_projects_btn.setToolTip("Show archived projects")
        self.archive_projects_btn.setStyleSheet(self._toggle_btn_style)
        self.archive_projects_btn.clicked.connect(lambda: self.switch_projects_mode('archive'))
        self.archive_projects_btn.setVisible(self.projects_mode != 'archive')
        header_row.addWidget(self.archive_projects_btn)

        self._update_project_tab_buttons()

        parent_layout.addLayout(header_row)
        self._update_color_strip()

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

    def _get_projects_title(self):
        """Return the header title for the current mode and sub-state"""
        if self.projects_mode == 'recent':
            return "Recent" if self.recent_compact else "Recent (all)"
        if self.projects_mode == 'alphabetical':
            return "By title (Z–A)" if self.projects_sort_reverse else "By title (A–Z)"
        if self.projects_mode == 'pinned':
            return "Pinned" if self.pinned_compact else "Pinned (all)"
        return {'folder': 'Folder Projects', 'archive': 'Archived'}.get(self.projects_mode, 'Projects')

    def switch_projects_mode(self, mode):
        """Switch project mode; clicking active Recent/Pinned toggles compact/full, active A-Z reverses sort"""
        if mode == self.projects_mode:
            if mode == 'recent':
                self.recent_compact = not self.recent_compact
                self.settings['recent_compact'] = self.recent_compact
                self.save_settings()
            elif mode == 'alphabetical':
                self.projects_sort_reverse = not self.projects_sort_reverse
                self.settings['projects_sort_reverse'] = self.projects_sort_reverse
                self.save_settings()
            elif mode == 'pinned':
                self.pinned_compact = not self.pinned_compact
                self.settings['pinned_compact'] = self.pinned_compact
                self.save_settings()
        else:
            self.projects_mode = mode
            self.settings['projects_mode'] = mode
            self.save_settings()

        # Clicking a mode button always clears color filter/sort
        self.active_color_filter = None
        self.filter_uncolored = False
        self.color_sort_active = False

        self.projects_header_label.setText(self._get_projects_title())

        self._update_project_tab_buttons()
        self._update_color_strip()
        self.archive_projects_btn.setVisible(self.projects_mode != 'archive')

        self.populate_projects()

    def _update_project_tab_buttons(self):
        """Update tab button labels, tooltips, and styles based on current mode and state"""
        # Recent button
        if self.projects_mode == 'recent' and not self.recent_compact:
            clock_label = "🕐 ▾"
            clock_tooltip = "Showing all recent — click to collapse to 10"
        else:
            clock_label = "🕐"
            clock_tooltip = (
                "10 most recent shown — click to show all"
                if self.projects_mode == 'recent'
                else "Most recently used first"
            )

        # Pinned button
        if self.projects_mode == 'pinned' and not self.pinned_compact:
            pin_label = "📌 ▾"
            pin_tooltip = "Showing all projects — click to collapse"
        else:
            pin_label = "📌"
            pin_tooltip = ("Show all to drag-to-pin" if self.projects_mode == 'pinned'
                           else "Show pinned projects")

        # A-Z button
        az_label = "Z–A" if (self.projects_mode == 'alphabetical' and self.projects_sort_reverse) else "A–Z"
        az_tooltip = ("Z→A — click for A→Z" if (self.projects_mode == 'alphabetical' and self.projects_sort_reverse)
                      else "A→Z — click to reverse")

        self.recent_projects_btn.setText(clock_label)
        self.recent_projects_btn.setToolTip(clock_tooltip)
        self.pinned_projects_btn.setText(pin_label)
        self.pinned_projects_btn.setToolTip(pin_tooltip)
        self.main_projects_btn.setText(az_label)
        self.main_projects_btn.setToolTip(az_tooltip)

        active = self._tab_active_style
        inactive = self._toggle_btn_style
        self.recent_projects_btn.setStyleSheet(active if self.projects_mode == 'recent' else inactive)
        self.pinned_projects_btn.setStyleSheet(active if self.projects_mode == 'pinned' else inactive)
        self.main_projects_btn.setStyleSheet(active if self.projects_mode == 'alphabetical' else inactive)
        self.folder_projects_btn.setStyleSheet(active if self.projects_mode == 'folder' else inactive)

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

        # Build color cache from project files before rendering any buttons
        self._build_color_cache()
        self._update_color_strip()

        # Color filter/sort overrides normal mode
        if self.filter_uncolored:
            self._populate_uncolored_projects()
            return
        if self.active_color_filter:
            self._populate_color_filtered_projects(self.active_color_filter)
            return
        if self.color_sort_active:
            self._populate_color_sorted_projects()
            return

        if self.projects_mode == 'recent':
            self._populate_recent_projects()
        elif self.projects_mode == 'alphabetical':
            self._populate_alphabetical_projects()
        elif self.projects_mode == 'pinned':
            self._populate_pinned_projects()
        elif self.projects_mode == 'folder':
            self._populate_folder_projects()
        elif self.projects_mode == 'archive':
            self._populate_archived_projects()

    def _populate_folder_projects(self):
        """Populate with folder projects (.projectflow configs)"""
        folder_projects = self.settings.get("folder_projects", [])

        # Filter to only existing files
        folder_projects = [p for p in folder_projects if os.path.exists(p)]

        # Update settings if any were removed
        if folder_projects != self.settings.get("folder_projects", []):
            self.settings["folder_projects"] = folder_projects
            self.save_settings()

        if not folder_projects:
            label = QLabel("No folder projects yet.\n\nBrowse the file system using the Folder Browser tab,\nthen open or create a project in any folder.")
            label.setStyleSheet(f"color: {self.t('fg_muted')}; font-size: 12px; padding: 20px;")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.projects_layout.addWidget(label)
            return

        _cols = self.settings.get("projects_per_row", 10)
        _spacing = self.settings.get("projects_spacing", 5)
        flow_widget = FlowWidget(target_cols=_cols, hspacing=_spacing, vspacing=3)
        for config_path in folder_projects:
            btn_container = self._create_config_button(config_path, is_pinned=False, draggable=False)
            flow_widget.addWidget(btn_container)
        self.projects_layout.addWidget(flow_widget)

    def _populate_recent_projects(self):
        """Populate all projects sorted by most recently used, falling back to file mtime"""
        recent_projects = self.settings.get("recent_projects", [])
        recent_projects = [c for c in recent_projects if os.path.exists(c) and '/.archive/' not in c]

        # Add remaining projects from projects/ dir not already tracked, sorted by mtime
        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        if os.path.exists(configs_dir):
            untracked = []
            for f in os.listdir(configs_dir):
                if f.endswith('.json') and not f.startswith('.'):
                    full_path = os.path.join(configs_dir, f)
                    if full_path not in recent_projects:
                        untracked.append((full_path, os.path.getmtime(full_path)))
            untracked.sort(key=lambda x: x[1], reverse=True)
            recent_projects.extend(p for p, _ in untracked)

        if not recent_projects:
            return

        cols = self.settings.get("projects_per_row", 10)
        spacing = self.settings.get("projects_spacing", 5)
        items = recent_projects[:cols] if self.recent_compact else recent_projects
        flow_widget = FlowWidget(target_cols=len(items) if self.recent_compact else cols,
                                 hspacing=spacing, vspacing=3)
        for config_path in items:
            btn_container = self._create_config_button(config_path, is_pinned=False, draggable=False)
            flow_widget.addWidget(btn_container)
        self.projects_layout.addWidget(flow_widget)

    def _populate_pinned_projects(self):
        """Pinned view: compact = Zone 1 only (pinned row); expanded = Zone 1 + Zone 2 (all projects, drag-to-pin)"""
        pinned_projects = self.settings.get("pinned_projects", [])
        pinned_projects = [c for c in pinned_projects if os.path.exists(c) and '/.archive/' not in c]
        pinned_set = set(pinned_projects)
        is_full = len(pinned_projects) >= 10

        # ── Zone 1: pinned row (drop target) ──────────────────────────────────
        zone1_header = QHBoxLayout()
        zone1_header.setContentsMargins(0, 0, 0, 2)

        if self.pinned_compact:
            hint_text = ("Pinned list full (10/10)" if is_full
                         else "Right-click to unpin  ·  click 📌 to add more" if pinned_projects
                         else "No pinned projects — click 📌 to add some")
        else:
            hint_text = ("Pinned list full (10/10)" if is_full
                         else "Drag projects below to pin  ·  drag to reorder  ·  right-click to unpin" if pinned_projects
                         else "Drag any project here to pin it (max 10)")
        hint_label = QLabel(hint_text)
        hint_label.setStyleSheet(f"color: {self.t('fg_muted')}; font-size: 11px;")
        zone1_header.addWidget(hint_label)
        zone1_header.addStretch()

        if pinned_projects:
            reset_btn = QPushButton("↺ Clear pins")
            reset_btn.setToolTip("Remove all pins")
            reset_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {self.t('fg_muted')};
                    border: none;
                    font-size: 11px;
                }}
                QPushButton:hover {{ color: {self.t('bg_danger')}; }}
            """)
            reset_btn.clicked.connect(self.reset_pinned_projects)
            zone1_header.addWidget(reset_btn)
        self.projects_layout.addLayout(zone1_header)

        # ConfigBarWidget is the drop target
        self.config_bar_widget = ConfigBarWidget(self)
        self.config_bar_widget.setAcceptDrops(True)
        _cols = self.settings.get("projects_per_row", 10)
        _spacing = self.settings.get("projects_spacing", 5)

        config_bar_layout = QHBoxLayout(self.config_bar_widget)
        config_bar_layout.setContentsMargins(0, 0, 0, 0)
        config_bar_layout.setSpacing(_spacing)

        zone1_containers = []
        for config_path in pinned_projects:
            btn_container = self._create_config_button(config_path, is_pinned=True, draggable=True, flow_managed=True)
            config_bar_layout.addWidget(btn_container)
            self.config_bar_widget.add_button(btn_container, config_path, is_pinned=True)
            zone1_containers.append(btn_container)

        # Deferred reflow — same formula as FlowWidget, called from showEvent/resizeEvent.
        # ConfigBarWidget uses Preferred size policy so self.width() is only as wide as its
        # contents — we must read the projects container width instead to match Zone 2.
        _proj_layout = self.projects_layout

        def _zone1_reflow(_ignored, _containers=zone1_containers, _layout=_proj_layout,
                          _cols=_cols, _spacing=_spacing):
            # This closure is called from three places that can all outlive the rebuild
            # that created it: ConfigBarWidget's own resizeEvent/showEvent, a deferred
            # QTimer.singleShot below, and (indirectly, via self.config_bar_widget._reflow_fn)
            # ProjectFlowApp.resizeEvent() — the last of which is a genuine cross-object
            # reach that can land mid-rebuild. If a newer build_main_content() has already
            # superseded this one by the time any of those fire, _containers/_layout here
            # can point at widgets Qt has already destroyed — touching them raises
            # RuntimeError ("wrapped C/C++ object has been deleted"), which PyQt6 treats as
            # fatal (calls abort()) if it escapes uncaught from an event/timer callback. See
            # ProjectFlowApp.resizeEvent()'s matching guard for the crash this fixes.
            try:
                parent = _layout.parentWidget()
                width = parent.width() if parent and parent.width() > 10 else 0
                if not _containers or width <= 0:
                    return
                target_cell_w = (width - (_cols - 1) * _spacing) // _cols
                n = len(_containers)
                cell_w = (target_cell_w if target_cell_w >= 80
                          else max(80, (width - (n - 1) * _spacing) // n))
                fm = QFontMetrics(QApplication.font())
                for c in _containers:
                    c.setFixedWidth(cell_w)
                    c.setFixedHeight(FlowWidget._ITEM_H)  # match Zone 2's row height exactly
                    if hasattr(c, '_main_btn') and hasattr(c, '_full_text') and hasattr(c, '_side_w'):
                        label_w = max(10, cell_w - c._side_w - 18)
                        c._main_btn.setText(fm.elidedText(
                            c._full_text, Qt.TextElideMode.ElideRight, label_w))
            except RuntimeError:
                pass

        self.config_bar_widget._reflow_fn = _zone1_reflow

        # Also queue a deferred reflow for the next event-loop tick: ConfigBarWidget's own
        # showEvent/resizeEvent are unreliable triggers here since it's Preferred-width +
        # sized-to-content with a trailing stretch (deliberately, so pins stay left-aligned)
        # — its own size rarely changes again after the very first (possibly too-early, before
        # the parent chain has its final width) layout pass, so it may never re-fire. This
        # guarantees at least one reflow call after layout has fully settled.
        def _deferred_zone1_reflow():
            try:
                _zone1_reflow(self.config_bar_widget.width())
            except RuntimeError:
                pass

        QTimer.singleShot(0, _deferred_zone1_reflow)

        config_bar_layout.addStretch()  # keep pins left-aligned, don't stretch to fill
        self.config_bar_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        zone1_row = QHBoxLayout()
        zone1_row.setSpacing(5)
        zone1_row.setContentsMargins(0, 0, 0, 0)
        zone1_row.addWidget(self.config_bar_widget)
        if not pinned_projects:
            # Empty drop zone: give it a visible dashed border so it's clearly a drop target
            self.config_bar_widget.setMinimumHeight(30)
            self.config_bar_widget.setStyleSheet(f"""
                background-color: {self.t('bg_secondary')};
                border: 1px dashed {self.t('border')};
                border-radius: 3px;
            """)
        zone1_row.addStretch()
        self.projects_layout.addLayout(zone1_row)

        # ── Zone 2: all unpinned projects (drag source) — only in expanded mode ──
        if self.pinned_compact:
            return

        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        if not os.path.exists(configs_dir):
            return

        all_configs = []
        for f in os.listdir(configs_dir):
            if f.endswith('.json') and not f.startswith('.'):
                full_path = os.path.join(configs_dir, f)
                if full_path not in pinned_set:
                    all_configs.append(full_path)
        all_configs.sort(key=lambda x: os.path.basename(x).lower())

        if not all_configs:
            return

        _cols = self.settings.get("projects_per_row", 10)
        _spacing = self.settings.get("projects_spacing", 5)
        flow_widget = FlowWidget(target_cols=_cols, hspacing=_spacing, vspacing=3)
        flow_widget.setContentsMargins(0, 6, 0, 0)
        for config_path in all_configs:
            btn_container = self._create_config_button(config_path, is_pinned=False, draggable=True)
            flow_widget.addWidget(btn_container)
        self.projects_layout.addWidget(flow_widget)

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
        config_files.sort(key=lambda x: os.path.basename(x).lower(), reverse=self.projects_sort_reverse)

        if not config_files:
            return

        _cols = self.settings.get("projects_per_row", 10)
        _spacing = self.settings.get("projects_spacing", 5)
        flow_widget = FlowWidget(target_cols=_cols, hspacing=_spacing, vspacing=3)
        for config_path in config_files:
            btn_container = self._create_config_button(config_path, is_pinned=False, draggable=False)
            flow_widget.addWidget(btn_container)
        self.projects_layout.addWidget(flow_widget)

    def _populate_archived_projects(self):
        """Populate with archived projects (main + folder)"""
        # Archived main projects: files in projects/.archive/
        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        archive_dir = os.path.join(configs_dir, ".archive")
        archived_main = []
        if os.path.exists(archive_dir):
            for f in sorted(os.listdir(archive_dir)):
                if f.endswith('.json'):
                    archived_main.append(os.path.join(archive_dir, f))

        # Archived folder projects: settings list
        archived_folder = self.settings.get("archived_folder_projects", [])
        archived_folder = [p for p in archived_folder if os.path.exists(p)]
        if archived_folder != self.settings.get("archived_folder_projects", []):
            self.settings["archived_folder_projects"] = archived_folder
            self.save_settings()

        all_archived = archived_main + archived_folder

        if not all_archived:
            label = QLabel("No archived projects.")
            label.setStyleSheet(f"color: {self.t('fg_muted')}; font-size: 12px; padding: 20px;")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.projects_layout.addWidget(label)
            return

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(5)
        buttons_layout.setContentsMargins(0, 0, 0, 0)

        for config_path in all_archived:
            btn_container = self._create_archived_button(config_path)
            buttons_layout.addWidget(btn_container)

        buttons_layout.addStretch()
        self.projects_layout.addLayout(buttons_layout)

    def _create_archived_button(self, config_path):
        """Create a button for an archived project with Restore action"""
        raw_name = self.get_display_name_for_config_path(config_path)
        display_name = raw_name.replace("_config", "").replace("_", " ").replace("-", " ").title()

        btn_container = QWidget()
        btn_container_layout = QHBoxLayout(btn_container)
        btn_container_layout.setContentsMargins(0, 0, 0, 0)
        btn_container_layout.setSpacing(1)

        color_bar = QFrame()
        color_bar.setFixedWidth(5)
        color_bar.setStyleSheet("background-color: transparent; border: none;")
        btn_container_layout.addWidget(color_bar)

        btn = QPushButton(display_name)
        btn.setMinimumHeight(26)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_muted')};
                border: 1px solid {self.t('border')};
                border-radius: 2px;
                padding: 4px 8px;
                font-size: 12px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """)
        btn.setToolTip(f"Archived: {config_path}\nClick to open (right-click to restore or delete)")
        btn.clicked.connect(lambda checked=False, path=config_path: self.switch_to_config(path))
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda pos, p=config_path: self._project_context_menu(btn, pos, p, archived=True))
        btn_container_layout.addWidget(btn)

        # Restore button
        restore_btn = QPushButton("↩")
        restore_btn.setFixedWidth(26)
        restore_btn.setMinimumHeight(26)
        restore_btn.setToolTip("Restore project")
        restore_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_muted')};
                border: 1px solid {self.t('border')};
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
        restore_btn.clicked.connect(lambda checked=False, path=config_path: self.restore_project(path))
        btn_container_layout.addWidget(restore_btn)

        return btn_container

    def _project_context_menu(self, btn, pos, config_path, archived=False):
        """Show right-click context menu for a project button"""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
            }}
            QMenu::item:selected {{
                background-color: {self.t('bg_config_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """)

        if archived:
            restore_action = menu.addAction("Restore project")
            restore_action.triggered.connect(lambda: self.restore_project(config_path))
            menu.addSeparator()
            delete_action = menu.addAction("Delete permanently")
            delete_action.triggered.connect(lambda: self._delete_project_permanently(config_path))
        else:
            pinned = self.settings.get("pinned_projects", [])
            if config_path in pinned:
                unpin_action = menu.addAction("Unpin")
                unpin_action.triggered.connect(lambda: self._unpin_project(config_path))
                menu.addSeparator()
            elif len(pinned) < 10:
                pin_action = menu.addAction("📌 Pin")
                pin_action.triggered.connect(lambda: self._pin_project(config_path))
                menu.addSeparator()
            archive_action = menu.addAction("Archive project")
            archive_action.triggered.connect(lambda: self.archive_project(config_path))
            menu.addSeparator()
            color_action = menu.addAction("🎨 Set Color...")
            color_action.triggered.connect(lambda: self._set_project_color_dialog(config_path))
            if config_path in getattr(self, '_color_cache', {}):
                clear_color_action = menu.addAction("Clear Color")
                clear_color_action.triggered.connect(lambda: self._clear_project_color(config_path))

        menu.exec(btn.mapToGlobal(pos))

    # ── Color coding helpers ──────────────────────────────────────────────────

    def _sorted_colors(self, unique_colors):
        """Return unique_colors sorted by color_order, then hue for any not yet ordered."""
        order = self.settings.get("color_order", [])
        def key(c):
            try:
                return (0, order.index(c))
            except ValueError:
                return (1, self._color_hue(c))
        return sorted(unique_colors, key=key)

    def _reorder_colors(self, moved_hex, target_hex):
        """Move moved_hex to just before target_hex in color_order, then save and refresh."""
        current_unique = list(set(getattr(self, '_color_cache', {}).values()))
        order = list(self.settings.get("color_order", []))
        # Ensure every live color is in the list (new colors may not be yet)
        for c in self._sorted_colors(current_unique):
            if c not in order:
                order.append(c)
        if moved_hex in order:
            order.remove(moved_hex)
        idx = order.index(target_hex) if target_hex in order else len(order)
        order.insert(idx, moved_hex)
        self.settings["color_order"] = order
        self.save_settings()
        self._update_color_strip()
        if self.color_sort_active:
            self.populate_projects()

    def _build_color_cache(self):
        """Scan all known project files and cache their project_color values."""
        cache = {}
        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        # Main projects directory
        if os.path.exists(configs_dir):
            for fname in os.listdir(configs_dir):
                if fname.endswith('.json'):
                    path = os.path.join(configs_dir, fname)
                    try:
                        with open(path) as f:
                            color = json.load(f).get("project_color")
                        if color:
                            cache[path] = color
                    except Exception:
                        pass
        # Folder projects (.projectflow files)
        for path in self.settings.get("folder_projects", []) + self.settings.get("archived_folder_projects", []):
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        color = json.load(f).get("project_color")
                    if color:
                        cache[path] = color
                except Exception:
                    pass
        self._color_cache = cache

    def _color_hue(self, hex_str):
        """Return HSL hue (0.0–1.0) for sorting colors in rainbow order."""
        import colorsys
        hex_str = hex_str.lstrip('#')
        r = int(hex_str[0:2], 16) / 255
        g = int(hex_str[2:4], 16) / 255
        b = int(hex_str[4:6], 16) / 255
        h, _l, _s = colorsys.rgb_to_hls(r, g, b)
        return h

    def _color_luminance(self, hex_str):
        """Return perceived luminance (0.0–1.0) to pick contrasting text color."""
        hex_str = hex_str.lstrip('#')
        r = int(hex_str[0:2], 16) / 255
        g = int(hex_str[2:4], 16) / 255
        b = int(hex_str[4:6], 16) / 255
        return 0.299 * r + 0.587 * g + 0.114 * b

    def _set_project_color_dialog(self, config_path):
        """Open a color picker and assign the chosen color to a project."""
        from PyQt6.QtWidgets import QColorDialog
        from PyQt6.QtGui import QColor
        # Pre-fill the dialog's custom color slots with currently used project colors
        used_colors = list(dict.fromkeys(  # preserve order, deduplicate
            self._sorted_colors(list(set(getattr(self, '_color_cache', {}).values())))
        ))
        for i, hex_color in enumerate(used_colors[:16]):
            QColorDialog.setCustomColor(i, QColor(hex_color))
        current = getattr(self, '_color_cache', {}).get(config_path, "")
        initial = QColor(current) if current else QColor("#3498db")
        chosen = QColorDialog.getColor(initial, self)
        if chosen.isValid():
            self._set_project_color(config_path, chosen.name())

    def _resolve_path(self, path):
        """Substitute a matching global path-mapping 'from' prefix with its 'to' replacement
        (settings['path_mappings'], configured in Settings → Advanced). Pure string transform —
        doesn't check whether the result exists on disk, and doesn't check whether path even
        looks like a local path (a non-matching prefix is simply a no-op, safe to call on any
        string). See _resolve_existing_path() for the fallback-when-missing behavior actually
        used when opening/browsing paths."""
        mappings = self.settings.get('path_mappings', [])
        if not mappings:
            return path
        expanded = os.path.expanduser(path)
        for m in mappings:
            from_ = os.path.expanduser(m.get('from', ''))
            to_ = m.get('to', '')
            if from_ and to_ and expanded.startswith(from_):
                return to_ + expanded[len(from_):]
        return path

    def _resolve_existing_path(self, path):
        """Try `path` as-is; if it's a local file/folder path that doesn't exist, try the
        global path mapping as a fallback and use that instead IF it exists — e.g. a project
        folder saved as `~/Public/key` that's only reachable as `~/gtr7/Public/key` on this
        machine. Returns (path_to_use, used_mapping).

        Deliberately read-only and call-site-scoped: the caller must never write
        path_to_use back into a config file, only ever use it for the current navigation/
        launch. This replaces the old per-project "Path mapping" checkbox/
        config_path_mapping, which unconditionally preferred the mapped path over the
        original whenever enabled — that meant a resolved (mapped) path could end up
        persisted back into a project's config by whatever flow happened to read the
        resolved value, silently corrupting the portable path for every other machine.
        Falling back ONLY when the direct path is missing, and only for the one action that
        needed it, avoids that failure mode entirely.
        """
        if not self._is_local_path(path):
            return path, False
        if os.path.exists(os.path.expanduser(path)):
            return path, False
        mapped = self._resolve_path(path)
        if mapped != path and os.path.exists(os.path.expanduser(mapped)):
            return mapped, True
        return path, False

    def _path_is_via_mapping(self, path):
        """True if `path` is a local file/folder path that doesn't exist directly but does
        resolve via the global path mappings (see _resolve_existing_path()) — drives the
        pale-blue "mapped path" launcher-button styling (see get_item_button_style()) for
        Documentation/Resources items, matching the folder browser's own pale-blue path-label
        indicator for the same underlying fallback."""
        if not path:
            return False
        _, used_mapping = self._resolve_existing_path(path)
        return used_mapping

    def _write_project_color(self, config_path, color_hex_or_none):
        """Patch project_color into a config JSON file directly."""
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            if color_hex_or_none:
                data["project_color"] = color_hex_or_none
            else:
                data.pop("project_color", None)
            with open(config_path, 'w') as f:
                json.dump(data, f, indent=2)
            # Keep instance var in sync if this is the current project
            if config_path == self.current_config_file:
                self.config_project_color = color_hex_or_none
        except Exception as e:
            print(f"Error writing project color: {e}")

    def _set_project_color(self, config_path, color_hex):
        """Assign a color to a project and refresh UI."""
        self._write_project_color(config_path, color_hex)
        self.populate_projects()  # rebuilds cache + buttons + strip

    def _clear_project_color(self, config_path):
        """Remove a project's color and refresh UI."""
        old_color = getattr(self, '_color_cache', {}).get(config_path)
        self._write_project_color(config_path, None)
        # If the cleared color was the active filter and nothing else uses it, reset
        if old_color and self.active_color_filter == old_color:
            remaining = {c for p, c in getattr(self, '_color_cache', {}).items() if p != config_path}
            if old_color not in remaining:
                self.active_color_filter = None
        self.populate_projects()  # rebuilds cache + buttons + strip

    def _filter_by_color(self, color_hex):
        """Toggle color filter; clicking active color clears it."""
        if self.active_color_filter == color_hex:
            self.active_color_filter = None
            self.color_sort_active = False
            self.projects_header_label.setText(self._get_projects_title())
        else:
            self.active_color_filter = color_hex
            self.filter_uncolored = False
            self.color_sort_active = False
            self.projects_header_label.setText("Color filter")
        self._update_color_strip()
        self.populate_projects()

    def _filter_by_no_color(self):
        """Toggle filter that shows only projects with no color assigned."""
        self.filter_uncolored = not self.filter_uncolored
        self.active_color_filter = None
        self.color_sort_active = False
        self.projects_header_label.setText("No color" if self.filter_uncolored else self._get_projects_title())
        self._update_color_strip()
        self.populate_projects()

    def _toggle_color_sort(self):
        """Activate or reverse color sort; deactivates any color filter."""
        self.active_color_filter = None
        self.filter_uncolored = False
        if not self.color_sort_active:
            self.color_sort_active = True
            self.color_sort_reverse = False
            self.projects_header_label.setText("By color")
        else:
            self.color_sort_reverse = not self.color_sort_reverse
            self.projects_header_label.setText("By color (reversed)" if self.color_sort_reverse else "By color")
        self._update_color_strip()
        self.populate_projects()

    def _update_color_strip(self):
        """Rebuild the inline color swatches in the header row."""
        # Clear existing widgets
        while self.color_strip_layout.count():
            item = self.color_strip_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        project_colors = getattr(self, '_color_cache', {})
        live_colors = set(project_colors.values())

        # Prune stale colors only when the cache has been built (non-empty live_colors
        # doesn't mean no colors exist — guard by checking _color_cache was set)
        if hasattr(self, '_color_cache'):
            color_order = [c for c in self.settings.get("color_order", []) if c in live_colors]
            if color_order != self.settings.get("color_order", []):
                self.settings["color_order"] = color_order
                self.save_settings()

        unique_colors = self._sorted_colors(list(live_colors))

        # Always update the sort button style even when no colors exist
        sort_active = self.color_sort_active
        if sort_active:
            self.color_sort_btn.setStyleSheet(self._tab_active_style)
            self.color_sort_btn.setText("🎨↑" if self.color_sort_reverse else "🎨↓")
            self.color_sort_btn.setToolTip("Sorted by color (reversed) — click to reverse again"
                                           if self.color_sort_reverse else "Sorted by color — click to reverse")
        else:
            self.color_sort_btn.setStyleSheet(self._toggle_btn_style)
            self.color_sort_btn.setText("🎨")
            self.color_sort_btn.setToolTip("Sort all projects by color")

        self.color_strip_widget.setVisible(True)

        for color_hex in unique_colors:
            count = sum(1 for c in project_colors.values() if c == color_hex)
            swatch = DraggableColorSwatch(color_hex, self)
            swatch.setFixedHeight(10)
            swatch.setFixedWidth(72)
            is_active = (self.active_color_filter == color_hex)
            border = "2px solid white" if is_active else "1px solid rgba(0,0,0,0.25)"
            swatch.setStyleSheet(
                f"QPushButton {{ background-color: {color_hex}; border: {border}; border-radius: 2px; }}"
                f"QPushButton:hover {{ border: 2px solid white; }}"
            )
            swatch.setToolTip(f"{color_hex} — {count} project{'s' if count != 1 else ''}\nClick to filter · Drag to reorder")
            swatch.clicked.connect(lambda checked=False, c=color_hex: self._filter_by_color(c))
            self.color_strip_layout.addWidget(swatch)

        # Persistent "no color" swatch — always present when strip is visible
        no_color_btn = QPushButton()
        no_color_btn.setFixedHeight(10)
        no_color_btn.setFixedWidth(72)
        is_nc_active = self.filter_uncolored
        nc_border = "2px solid white" if is_nc_active else f"1px solid {self.t('border_dark')}"
        no_color_btn.setStyleSheet(
            f"QPushButton {{ "
            f"background: repeating-linear-gradient(45deg, "
            f"{self.t('border_dark')} 0px, {self.t('border_dark')} 3px, "
            f"{self.t('bg_secondary')} 3px, {self.t('bg_secondary')} 8px);"
            f"border: {nc_border}; border-radius: 2px; }}"
            f"QPushButton:hover {{ border: 2px solid white; }}"
        )
        no_color_btn.setToolTip("Show projects with no color assigned\nClick to filter")
        no_color_btn.clicked.connect(self._filter_by_no_color)
        self.color_strip_layout.addWidget(no_color_btn)

        # Persistent "archive" swatch — shortcut to archive mode
        archive_swatch = QPushButton()
        archive_swatch.setFixedHeight(10)
        archive_swatch.setFixedWidth(72)
        is_arch_active = (self.projects_mode == 'archive')
        arch_border = "2px solid white" if is_arch_active else f"1px solid {self.t('border_dark')}"
        archive_swatch.setStyleSheet(
            f"QPushButton {{ background-color: #cccccc; border: {arch_border}; border-radius: 2px; }}"
            f"QPushButton:hover {{ border: 2px solid white; }}"
        )
        archive_swatch.setToolTip("Show archived projects\nClick to view archive")
        archive_swatch.clicked.connect(lambda: self.switch_projects_mode('archive'))
        self.color_strip_layout.addWidget(archive_swatch)

    def _populate_uncolored_projects(self):
        """Show only projects with no color assigned."""
        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        project_colors = getattr(self, '_color_cache', {})
        uncolored = []
        if os.path.exists(configs_dir):
            for f in sorted(os.listdir(configs_dir)):
                if f.endswith('.json') and not f.startswith('.'):
                    p = os.path.join(configs_dir, f)
                    if '/.archive/' not in p and not project_colors.get(p):
                        uncolored.append(p)
        if not uncolored:
            label = QLabel("All projects have a color assigned.")
            label.setStyleSheet(f"color: {self.t('fg_muted')}; font-size: 12px; padding: 20px;")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.projects_layout.addWidget(label)
            return
        _cols = self.settings.get("projects_per_row", 10)
        _spacing = self.settings.get("projects_spacing", 5)
        flow_widget = FlowWidget(target_cols=_cols, hspacing=_spacing, vspacing=3)
        for config_path in uncolored:
            btn_container = self._create_config_button(config_path, is_pinned=False, draggable=False)
            flow_widget.addWidget(btn_container)
        self.projects_layout.addWidget(flow_widget)

    def _populate_color_filtered_projects(self, color_hex):
        """Show only projects whose assigned color matches the filter."""
        project_colors = getattr(self, '_color_cache', {})
        matching = [p for p, c in project_colors.items() if c == color_hex and os.path.exists(p)]
        if not matching:
            label = QLabel("No projects with this color.")
            label.setStyleSheet(f"color: {self.t('fg_muted')}; font-size: 12px; padding: 20px;")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.projects_layout.addWidget(label)
            return
        _cols = self.settings.get("projects_per_row", 10)
        _spacing = self.settings.get("projects_spacing", 5)
        flow_widget = FlowWidget(target_cols=_cols, hspacing=_spacing, vspacing=3)
        for config_path in matching:
            btn_container = self._create_config_button(config_path, is_pinned=False, draggable=False)
            flow_widget.addWidget(btn_container)
        self.projects_layout.addWidget(flow_widget)

    def _populate_color_sorted_projects(self):
        """Show all main projects sorted by their assigned color hue, uncolored last."""
        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        if not os.path.exists(configs_dir):
            return
        config_files = [
            os.path.join(configs_dir, f)
            for f in os.listdir(configs_dir)
            if f.endswith('.json') and '/.archive/' not in os.path.join(configs_dir, f)
        ]
        project_colors = getattr(self, '_color_cache', {})

        # Bucket projects by color in custom priority order (drag-to-reorder)
        unique_colors = list(set(project_colors.values()))
        ordered_colors = self._sorted_colors(unique_colors)
        result = []
        for color in ordered_colors:
            result += [p for p in config_files if project_colors.get(p) == color]
        uncolored = [p for p in config_files if not project_colors.get(p)]
        if self.color_sort_reverse:
            result = list(reversed(result))
        config_files = result + uncolored  # uncolored always last regardless of reverse
        if not config_files:
            return
        _cols = self.settings.get("projects_per_row", 10)
        _spacing = self.settings.get("projects_spacing", 5)
        flow_widget = FlowWidget(target_cols=_cols, hspacing=_spacing, vspacing=3)
        for config_path in config_files:
            btn_container = self._create_config_button(config_path, is_pinned=False, draggable=False)
            flow_widget.addWidget(btn_container)
        self.projects_layout.addWidget(flow_widget)

    def archive_project(self, config_path):
        """Archive a project (hide from normal views)"""
        is_folder_project = os.path.basename(config_path) == '.projectflow'

        if is_folder_project:
            folder_projects = self.settings.get("folder_projects", [])
            archived = self.settings.get("archived_folder_projects", [])
            if config_path in folder_projects:
                folder_projects.remove(config_path)
            if config_path not in archived:
                archived.insert(0, config_path)
            self.settings["folder_projects"] = folder_projects
            self.settings["archived_folder_projects"] = archived
        else:
            archive_dir = os.path.join(os.path.dirname(config_path), ".archive")
            os.makedirs(archive_dir, exist_ok=True)
            dest = os.path.join(archive_dir, os.path.basename(config_path))
            if os.path.exists(dest):
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Archive Conflict",
                    f"An archived project named '{os.path.basename(config_path)}' already exists.")
                return
            shutil.move(config_path, dest)
            self._remove_from_project_lists(config_path)
            if self.current_config_file == config_path:
                self._switch_away_from_archived(dest)

        self.save_settings()
        self.refresh_projects()

    def restore_project(self, config_path):
        """Restore an archived project back to normal visibility"""
        is_folder_project = os.path.basename(config_path) == '.projectflow'

        if is_folder_project:
            archived = self.settings.get("archived_folder_projects", [])
            folder_projects = self.settings.get("folder_projects", [])
            if config_path in archived:
                archived.remove(config_path)
            if config_path not in folder_projects:
                folder_projects.insert(0, config_path)
            self.settings["archived_folder_projects"] = archived
            self.settings["folder_projects"] = folder_projects
        else:
            # Move from .archive/ back to projects/
            projects_dir = os.path.dirname(os.path.dirname(config_path))
            dest = os.path.join(projects_dir, os.path.basename(config_path))
            if os.path.exists(dest):
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Restore Conflict",
                    f"A project named '{os.path.basename(config_path)}' already exists in the projects folder.")
                return
            if not os.path.exists(config_path):
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "File Not Found",
                    f"The archived file no longer exists:\n{config_path}")
                self.refresh_projects()
                return
            try:
                shutil.move(config_path, dest)
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Restore Failed", f"Could not move file:\n{e}")
                return

        self.save_settings()
        self.refresh_projects()

    def _delete_project_permanently(self, config_path):
        """Permanently delete an archived project file after confirmation"""
        from PyQt6.QtWidgets import QMessageBox
        name = os.path.basename(config_path)
        reply = QMessageBox.question(
            self, "Delete Permanently",
            f"Permanently delete '{name}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        is_folder_project = os.path.basename(config_path) == '.projectflow'
        if is_folder_project:
            archived = self.settings.get("archived_folder_projects", [])
            if config_path in archived:
                archived.remove(config_path)
            self.settings["archived_folder_projects"] = archived
            self.save_settings()
        else:
            try:
                os.remove(config_path)
            except OSError as e:
                QMessageBox.warning(self, "Delete Failed", str(e))
                return

        self.refresh_projects()

    def _remove_from_project_lists(self, config_path):
        """Remove a project path from recent/pinned/default settings"""
        for key in ("recent_projects", "pinned_projects"):
            lst = self.settings.get(key, [])
            if config_path in lst:
                lst.remove(config_path)
                self.settings[key] = lst
        if self.settings.get("last_used_project") == config_path:
            self.settings["last_used_project"] = ""
        if self.settings.get("default_project") == config_path:
            self.settings["default_project"] = ""

    def _switch_away_from_archived(self, archived_path):
        """Switch to another project when the current one is being archived"""
        # Try recent projects first
        for p in self.settings.get("recent_projects", []):
            if os.path.exists(p) and p != self.current_config_file:
                self.switch_to_config(p)
                return
        # Fall back to any project in projects/
        configs_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        if os.path.exists(configs_dir):
            for f in sorted(os.listdir(configs_dir)):
                if f.endswith('.json'):
                    full_path = os.path.join(configs_dir, f)
                    if os.path.exists(full_path):
                        self.switch_to_config(full_path)
                        return

    def _create_config_button(self, config_path, is_pinned, draggable=False, flow_managed=True, on_select=None):
        """Create a config button with new window button.
        flow_managed=True: FlowWidget controls cell width dynamically (all grid views).
        flow_managed=False: fixed 120px width for Zone 1 pinned drag-reorder row (also used,
        unrelated to Zone 1, by the project mega-menu's narrow columns — see
        _build_project_mega_menu_content()).
        on_select: optional no-arg callback invoked after any of this button's three actions
        (switch/new window/new desktop) — used by the mega menu to close its popup on
        selection, since clicking a plain child widget inside a QWidgetAction does not close
        the QMenu on its own (confirmed empirically; only real QAction triggers do)."""
        # Get display name from config (reads project_name if set)
        raw_name = self.get_display_name_for_config_path(config_path)
        display_name = raw_name.replace("_config", "").replace("_", " ").replace("-", " ").title()
        is_current = (config_path == self.current_config_file)

        def _fire_on_select():
            if on_select:
                on_select()

        def _switch_and_select(path):
            self.switch_to_config(path)
            _fire_on_select()

        def _new_window_and_select(path):
            self.open_config_in_new_window(path)
            _fire_on_select()

        def _new_desktop_and_select(path):
            self.open_config_in_new_desktop(path)
            _fire_on_select()

        btn_container = QWidget()
        btn_container_layout = QHBoxLayout(btn_container)
        btn_container_layout.setContentsMargins(0, 0, 0, 0)
        btn_container_layout.setSpacing(1)

        # 5px colored left bar — always present for uniform text alignment
        _project_color = getattr(self, '_color_cache', {}).get(config_path)
        color_bar = QFrame()
        color_bar.setFixedWidth(5)
        _bar_color = _project_color if _project_color else "transparent"
        color_bar.setStyleSheet(f"background-color: {_bar_color}; border: none;")
        btn_container_layout.addWidget(color_bar)

        if flow_managed:
            # FlowWidget will set cell width dynamically; main button expands to fill
            btn_label = display_name  # FlowWidget re-elides on every resize
            if draggable:
                btn = DraggableConfigButton(btn_label, config_path)
            else:
                btn = QPushButton(btn_label)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setMinimumWidth(30)
        else:
            # Zone 1 fixed-width pinned row — pre-elide at 120px
            _fixed_w = 120
            fm = QFontMetrics(QApplication.font())
            btn_label = fm.elidedText(display_name, Qt.TextElideMode.ElideRight, _fixed_w - 18)
            btn = DraggableConfigButton(btn_label, config_path) if draggable else QPushButton(btn_label)
            btn.setFixedWidth(_fixed_w)

        btn.setMinimumHeight(26)

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
                    text-align: left;
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
                    text-align: left;
                    {border_bottom}
                }}
                QPushButton:hover {{
                    background-color: {self.t('bg_config_hover')};
                    color: {self.t('fg_on_dark')};
                }}
            """)

        btn.clicked.connect(lambda checked=False, path=config_path: _switch_and_select(path))
        if draggable:
            tooltip = f"{display_name}\n📌 {config_path}\n(Drag to reorder)"
        else:
            tooltip = f"{display_name}\n{config_path}"
        btn.setToolTip(tooltip)
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda pos, p=config_path: self._project_context_menu(btn, pos, p, archived=False))
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
        new_window_btn.clicked.connect(lambda checked=False, path=config_path: _new_window_and_select(path))
        new_window_btn.setToolTip("Open in new window")
        btn_container_layout.addWidget(new_window_btn)

        if self._can_open_in_new_desktop():
            new_desktop_btn = QPushButton("⧉")
            new_desktop_btn.setFixedWidth(26)
            new_desktop_btn.setMinimumHeight(26)
            new_desktop_btn.setStyleSheet(f"""
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
            new_desktop_btn.clicked.connect(lambda checked=False, path=config_path: _new_desktop_and_select(path))
            new_desktop_btn.setToolTip("Open in new virtual desktop")
            btn_container_layout.addWidget(new_desktop_btn)

        # Store metadata so FlowWidget can re-elide text on resize
        if flow_managed:
            has_desktop = self._can_open_in_new_desktop()
            btn_container._main_btn = btn
            btn_container._full_text = display_name
            btn_container._side_w = 27 + (27 if has_desktop else 0)  # ↗ + optional ⧉ + spacing
            btn_container._left_extra_w = 6 if _project_color else 0  # 5px color bar + 1px spacing

        return btn_container

    def handle_config_drop(self, dragged_path, drop_index):
        """Handle a config being dropped onto the pinned zone (reorder or add, max 10)"""
        pinned = self.settings.get("pinned_projects", [])
        pinned = [c for c in pinned if os.path.exists(c)]
        if dragged_path not in pinned and len(pinned) >= 10:
            return  # at capacity — hint label already communicates this
        if dragged_path in pinned:
            pinned.remove(dragged_path)
        pinned.insert(min(drop_index, len(pinned)), dragged_path)
        self.settings["pinned_projects"] = pinned
        self.save_settings()
        self.refresh_projects()

    def _pin_project(self, config_path):
        """Add a project to the pinned list (max 10)"""
        pinned = self.settings.get("pinned_projects", [])
        if config_path not in pinned and len(pinned) < 10:
            pinned.append(config_path)
            self.settings["pinned_projects"] = pinned
            self.save_settings()
            self.refresh_projects()

    def _unpin_project(self, config_path):
        """Remove a project from the pinned list"""
        pinned = self.settings.get("pinned_projects", [])
        if config_path in pinned:
            pinned.remove(config_path)
            self.settings["pinned_projects"] = pinned
            self.save_settings()
            self.refresh_projects()

    def reset_pinned_projects(self):
        """Clear all pinned configs"""
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

    def handle_item_move_to_category(self, from_category, item_idx, to_category, drop_idx):
        """Move an item from one category to another"""
        try:
            with open(self.current_config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            column_data = config_data["columns"][0]

            # Remove from source category
            item = None
            for category_dict in column_data:
                if from_category in category_dict:
                    items = category_dict[from_category]
                    if 0 <= item_idx < len(items):
                        item = items.pop(item_idx)
                    break

            if item is None:
                return

            # Insert into destination category at drop position
            for category_dict in column_data:
                if to_category in category_dict:
                    dest_items = category_dict[to_category]
                    drop_idx = max(0, min(drop_idx, len(dest_items)))
                    dest_items.insert(drop_idx, item)
                    break

            with open(self.current_config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2)
            self.load_config()
            self.refresh_projects()
        except Exception as e:
            print(f"Error moving item between categories: {e}")

    def build_main_content(self, parent_layout):
        """Build the main content area with project columns"""
        # Layout: Launchers (COLUMN_1) | Viewer | Notepad
        # Always show all three panels
        all_columns = [self.COLUMN_1]
        self._launcher_search_refs = []

        # Reset every render — only _build_grouped_categories() (called below, conditionally)
        # should populate these. Without this reset, a render pass that DOESN'T call it (the
        # raw self.COLUMN_1 fallback used for Docs/Files/Apps while editing) would keep
        # consulting stale data from whichever grouped/pooled render happened last, silently
        # hiding items that should show up unfiltered in the raw view.
        self._group_view_origin = {}
        self._grouped_hidden_item_ids = set()

        # Resolve the folder browser's starting path before either the launcher-column Quick
        # File Browser Panel or the main Folder viewer consult it — the panel is built first
        # (see _build_launcher_folder_panel's ordering note), and its own fallback used to
        # default straight to "~" whenever folder_current_path had just been reset by
        # switch_to_config(), ignoring config_folder_path entirely and then "sticking" before
        # the main viewer's later init logic ever got a chance to apply the project's own
        # folder_path.
        if not getattr(self, 'folder_current_path', None):
            self.folder_current_path = getattr(self, 'config_folder_path', None) or os.path.expanduser("~")

        for col_idx, column_categories in enumerate(all_columns):
            # Focus-layout launcher column: active_launcher_tab picks what column_categories
            # (if anything) gets rendered — Files/Apps replace it with a panel built directly
            # into column_layout below, and are the only tabs that still fall back to raw
            # self.COLUMN_1 while editing (nothing meaningful to show there otherwise). Docs
            # and Resources both stay on _build_grouped_categories()'s output regardless of
            # edit_mode: Resources categories are real (not pooled), so they get full
            # editing for free; Docs mixes a real "Docs" category (same full editing) with
            # still-pooled AI/discovered items (👁 hide toggle only, no drag) — see the
            # per-item grouped_active check below and "A real 'Docs' category" in CLAUDE.md.
            # Standard layout's legacy group_by_type toggle mirrors this same split.
            focus_launcher_tab_active = col_idx == 0 and self.layout_mode == "focus" and (
                not self.edit_mode or self.active_launcher_tab in ("docs", "resources")
            )
            if focus_launcher_tab_active:
                if self.active_launcher_tab == "resources":
                    column_categories = [c for c in self._build_grouped_categories() if "AI" not in c and "Docs" not in c]
                elif self.active_launcher_tab == "docs":
                    column_categories = [c for c in self._build_grouped_categories() if "AI" in c or "Docs" in c]
                elif not self.edit_mode:
                    column_categories = []  # "files" / "apps" — panel built directly, no categories
                # else: edit_mode and tab is "files"/"apps" — falls through, column_categories
                # stays [self.COLUMN_1] (raw fallback — nothing to manage on these tabs anyway).
            elif col_idx == 0 and self.layout_mode != "focus" and self.group_by_type:
                # Standard layout only — group_by_type is vestigial in Focus layout (still
                # stored/defaulted True, but display is entirely driven by the tab dispatch
                # above; without this layout_mode guard it would incorrectly hijack Focus's
                # own raw-fallback case above whenever that branch falls through unhandled.
                if self.edit_mode:
                    column_categories = [c for c in self._build_grouped_categories() if "AI" not in c and "Docs" not in c]
                else:
                    column_categories = self._build_grouped_categories()

            # Files/Apps tabs (Focus layout) and the legacy expanded-folder-panel both replace
            # the category list with a panel built directly into column_layout — this flag
            # gates the search/add header row too, which has nothing to search/add to then.
            hide_launchers_for_folder_panel = (
                focus_launcher_tab_active and self.active_launcher_tab in ("files", "apps")
            )

            # These widgets only get (re)built below when the panel is actually expanded this
            # pass. Reset them to None on every other build so stale references to widgets Qt
            # already destroyed (from a previous build where the panel WAS expanded) never leak
            # through a getattr(self, 'launcher_folder_x', None) check elsewhere — accessing a
            # PyQt wrapper for an already-deleted C++ object raises "wrapped C/C++ object has
            # been deleted", which is exactly the bug this guards against.
            if col_idx == 0:
                self.launcher_folder_path_label = None
                self.launcher_folder_browser = None
                self.launcher_folder_icon_view = None
                self.launcher_folder_view_stack = None
                self.launcher_folder_view_toggle_btn = None
                self.launcher_folder_filter_input = None

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
                    column_layout.setContentsMargins(0, 4, 0, 0)  # left, top, right, bottom

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

                    # Focus-layout launcher tab row (Files/Docs/Resources/Apps) — replaces the
                    # old separate File-Browser-toggle + "☰ Group" toggle with one tab bar,
                    # styled like the wide-viewer's tab row (see tab_btn_style/active_tab_style
                    # further down in this method) so switching "what the launcher column
                    # shows" feels the same as switching viewers. Standard layout is untouched
                    # (see the "☰ Group" button further below, still built there). Always shown
                    # (even in edit mode) so Resources — real, editable categories — stays
                    # reachable/switchable while editing; switching to Docs/Files/Apps while
                    # editing still falls back to today's raw category list (see the
                    # focus_launcher_tab_active dispatch above), unchanged for now.
                    if self.layout_mode == "focus":
                        # Blue (tab_launcher_resting/active/bg_category_hover) rather than
                        # the wide-viewer tab row's green — matches the category header bars
                        # ("Docs - Open All" etc.) these tabs are effectively switching
                        # between. tab_launcher_resting/tab_launcher_active are a dedicated
                        # pair (not the general bg_category/bg_category_hover, reused ~30
                        # places elsewhere) specifically because "brighter = active" (matching
                        # the viewer tab row's bg_green_1->bg_green_3 convention) flips which
                        # of {bg_category, a scaled variant} is naturally the brighter one
                        # between themes — see themes.py's comment on this pair for why. Hover
                        # uses bg_category_hover, which in both themes happens to sit between
                        # the resting and active values in brightness, so the three states
                        # still form one continuous dim->medium->bright progression:
                        # resting -> hover -> active.
                        launcher_tab_style = f"""
                            QPushButton {{
                                background-color: {self.t('tab_launcher_resting')};
                                color: {self.t('fg_on_dark')};
                                font-weight: bold;
                                border-radius: 3px;
                                padding: 5px 8px;
                                font-size: 11px;
                            }}
                            QPushButton:hover {{
                                background-color: {self.t('bg_category_hover')};
                                color: {self.t('fg_on_dark')};
                            }}
                        """
                        # Active fill, no border — mirrors the viewer tab row's own
                        # bg_green_3 active fill (see active_tab_style's comment in the
                        # viewer tab row section for the fuller history of what was tried
                        # before landing on "just use a different shade, no border").
                        launcher_tab_active_style = f"""
                            QPushButton {{
                                background-color: {self.t('tab_launcher_active')};
                                color: {self.t('fg_on_dark')};
                                font-weight: bold;
                                border-radius: 3px;
                                padding: 5px 8px;
                                font-size: 11px;
                            }}
                            QPushButton:hover {{
                                background-color: {self.t('tab_launcher_active')};
                                color: {self.t('fg_on_dark')};
                            }}
                        """
                        launcher_tabs_layout = QHBoxLayout()
                        launcher_tabs_layout.setContentsMargins(0, 0, 0, 0)
                        launcher_tabs_layout.setSpacing(3)
                        for tab_id, tab_label, tab_tooltip in (
                            ("docs", "Docs", "Local documentation files (.md/.html/.pdf/.txt)"),
                            ("resources", "Resources", "Websites and everything else"),
                            ("files", "Files", "Browse files (opens into the viewer)"),
                            ("apps", "Apps", "Applications relevant to this project"),
                        ):
                            tab_btn = QPushButton(f" {tab_label}")
                            tab_btn.setMinimumHeight(self.d('header_btn_height'))
                            tab_btn.setToolTip(tab_tooltip)
                            tab_icon_path = os.path.join(self.script_dir, "assets", "tab-icons", f"{tab_id}.png")
                            if os.path.exists(tab_icon_path):
                                tab_btn.setIcon(QIcon(tab_icon_path))
                                tab_btn.setIconSize(QSize(16, 16))
                            tab_btn.setStyleSheet(
                                launcher_tab_active_style if self.active_launcher_tab == tab_id
                                else launcher_tab_style
                            )
                            tab_btn.clicked.connect(
                                lambda checked=False, t=tab_id: self._switch_launcher_tab(t)
                            )
                            # Equal stretch so the trailing addSpacing below is a real gap
                            # rather than being absorbed by the buttons expanding into it.
                            launcher_tabs_layout.addWidget(tab_btn, 1)

                        # Pin the active tab as this project's default — mirrors the shared
                        # viewer 📌 button at the end of the viewer tab row (below), so
                        # launcher_tab_default overrides the last-opened tab on load (see
                        # load_config()) the same way column2_default already does for
                        # viewers. No dynamic "currently pinned" highlight, matching every
                        # other pin button in the app. Styled with launcher_tab_style (the
                        # same blue bg_category used by the tabs it pins) rather than a plain
                        # bg_button style, now that it carries a white icon matching the tabs'
                        # own white icons instead of a bare "📌" glyph.
                        pin_tab_btn = QPushButton()
                        pin_tab_icon_path = os.path.join(self.script_dir, "assets", "tab-icons", "pin.png")
                        if os.path.exists(pin_tab_icon_path):
                            pin_tab_btn.setIcon(QIcon(pin_tab_icon_path))
                            pin_tab_btn.setIconSize(QSize(16, 16))
                        pin_tab_btn.setFixedWidth(28)
                        pin_tab_btn.setMinimumHeight(self.d('header_btn_height'))
                        pin_tab_btn.setToolTip(f"Pin \"{self.active_launcher_tab.title()}\" as default launcher tab for this project")
                        pin_tab_btn.setStyleSheet(launcher_tab_style)
                        pin_tab_btn.clicked.connect(self._set_launcher_tab_as_default)
                        launcher_tabs_layout.addWidget(pin_tab_btn)

                        column_layout.addLayout(launcher_tabs_layout)
                        column_layout.addSpacing(3)

                        if not self.edit_mode and self.active_launcher_tab == "files":
                            self._build_launcher_folder_panel(column_layout)
                        elif not self.edit_mode and self.active_launcher_tab == "apps":
                            self._build_apps_tab(column_layout)

                    # First column: add edit mode and refresh buttons (like column 2 style)
                    header_layout = QHBoxLayout()
                    header_layout.setContentsMargins(0, 0, 0, 0)
                    header_layout.setSpacing(3)

                    if not self.edit_mode and not hide_launchers_for_folder_panel:
                        # Search box + Add button (hidden in edit mode — controls are in title bar)
                        self._launcher_search_box = QLineEdit()
                        self._launcher_search_box.setPlaceholderText("🔍  Search…")
                        self._launcher_search_box.setMinimumHeight(self.d('header_btn_height'))
                        self._launcher_search_box.setClearButtonEnabled(True)
                        self._launcher_search_box.setStyleSheet(f"""
                            QLineEdit {{
                                background-color: {self.t('bg_secondary')};
                                color: {self.t('fg_primary')};
                                border: 1px solid {self.t('border')};
                                border-radius: 3px;
                                padding: 2px 4px;
                            }}
                            QLineEdit:focus {{
                                border-color: {self.t('border_dark')};
                            }}
                        """)
                        self._launcher_search_box.textChanged.connect(self._filter_launchers)
                        header_layout.addWidget(self._launcher_search_box, 1)

                        # "☰ Group" toggle is Standard-layout only — Focus layout uses the
                        # tab row above instead (active_launcher_tab subsumes this role).
                        if self.layout_mode != "focus":
                            group_btn = QPushButton("☰ Group")
                            group_btn.setMinimumHeight(self.d('header_btn_height'))
                            group_btn.setToolTip(
                                "Group launchers by type (Docs / Resources) — "
                                "display only, never changes the project file"
                            )
                            group_btn.setCheckable(True)
                            group_btn.setChecked(self.group_by_type)
                            group_btn.setStyleSheet(green_btn_style)
                            group_btn.clicked.connect(self._toggle_group_by_type)
                            header_layout.addWidget(group_btn)

                        add_btn = QPushButton("  +  Add")
                        add_btn.setMinimumHeight(self.d('header_btn_height'))
                        add_btn.setToolTip("Quick-add a launcher to the first category")
                        add_btn.setStyleSheet(green_btn_style)
                        add_btn.clicked.connect(self.quick_add_launcher)
                        header_layout.addWidget(add_btn)

                        column_layout.addLayout(header_layout)

            # Process each category within this column
            for category_dict in column_categories:
                for category_name, items in category_dict.items():
                    # Create a container for the group box with a custom title button
                    group_container = QWidget()
                    group_container_layout = QVBoxLayout(group_container)
                    group_container_layout.setSpacing(0)
                    group_container_layout.setContentsMargins(0, 0, 0, 0)

                    if col_idx == 0:
                        category_ref = {'container': group_container, 'category_name': category_name, 'items': []}
                        self._launcher_search_refs.append(category_ref)

                    # Create category header (editable in edit mode) — AI is excluded even
                    # while editing, since it's purely filesystem-derived, not a real category
                    # to rename/delete (see _build_grouped_categories()). "Docs" is excluded
                    # too: it's a display LABEL that can differ from the real backing category
                    # name ("Documentation", or legacy "Docs" — see
                    # _ensure_documentation_category()), so renaming/deleting via this inline
                    # header could act on the wrong (or a nonexistent) category name. The "+
                    # Add Launcher" button below resolves the real name itself instead.
                    if self.edit_mode and category_name not in ("AI", "Docs"):
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

                        delete_category_btn = QPushButton("🗑")
                        delete_category_btn.setFixedSize(30, 28)
                        delete_category_btn.setToolTip(f"Delete category '{category_name}'")
                        delete_category_btn.setStyleSheet(f"""
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
                        title_btn.setToolTip(f"Click to open all items in {category_name}\nRight-click to rename or delete")
                        title_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                        title_btn.customContextMenuRequested.connect(
                            lambda pos, btn=title_btn, ci=col_idx, cn=category_name:
                                self._show_category_context_menu(btn, ci, cn)
                        )
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

                    # Create drop zone for drag-and-drop reordering (always active). For the
                    # Docs bucket, category_name is the display LABEL ("Docs") which can now
                    # differ from the real backing category ("Documentation", or legacy
                    # "Docs" — see _ensure_documentation_category()); DraggableItemButton is
                    # built with the item's TRUE category (see true_category below), so the
                    # drop zone must resolve to that same true name too, or same-category
                    # reorders would always be misdetected as cross-category moves, and a
                    # genuine cross-category move into this zone would try to move into a
                    # category literally named "Docs" that may not exist — silently losing
                    # the item (handle_item_move_to_category() reads the file fresh from disk
                    # and finds no destination to insert into). Best-effort resolve only, no
                    # creation here — creating on every render would be a side effect a plain
                    # view of the Docs tab shouldn't have.
                    if category_name == "Docs":
                        _docs_real_name = next(
                            (n for n in ("Documentation", "Docs") if any(n in cd for cd in self.COLUMN_1)),
                            "Documentation"
                        )
                        category_drop_zone = CategoryDropZone(self, col_idx, _docs_real_name)
                    else:
                        category_drop_zone = CategoryDropZone(self, col_idx, category_name)
                    drop_zone_layout = QVBoxLayout(category_drop_zone)
                    drop_zone_layout.setContentsMargins(0, 0, 0, 0)
                    drop_zone_layout.setSpacing(3)

                    # Add buttons for each item in this category
                    for idx, item in enumerate(items):
                        # Skip items already surfaced via the AI bucket (same file also
                        # physically filed in this real category) — see
                        # _build_grouped_categories()'s self._grouped_hidden_item_ids. Kept
                        # at true index so drag/edit/delete stay correct for the items shown.
                        if id(item) in getattr(self, '_grouped_hidden_item_ids', ()):
                            continue
                        # Handle both 2-tuple and 3-tuple formats
                        if len(item) == 2:
                            display_name, path = item
                            app = "kate"  # default
                        else:
                            display_name, path, app = item

                        # True origin first: a real category's items map to themselves; AI
                        # items and the pinned-notes entry have no real category backing them
                        # (sentinel None) — everything else filed under the Docs bucket is a
                        # genuine Documentation-category item and resolves to its own real name.
                        true_category, true_idx = self._group_view_origin.get(id(item), (category_name, idx))
                        # Pooled (read-mostly) iff there's no real category behind it at all —
                        # AI items and the pinned-notes entry. Every other Docs-bucket item is
                        # a real Documentation-category item and gets full drag/edit below.
                        is_pooled = self._is_grouped_view_active() and (
                            category_name == "AI" or true_category is None
                        )

                        # Get app icon if available — either emoji text or SVG file (shared by
                        # both the pooled row and the real-item rendering below).
                        app_icon = ""
                        svg_icon_path = None
                        if self._icon_key_for_app(app, path) in self.APP_INFO:
                            icon_val = self.APP_INFO[self._icon_key_for_app(app, path)]["icon"]
                            if icon_val.endswith(('.svg', '.png', '.jpg')):
                                candidate = os.path.join(self.script_dir, icon_val)
                                if os.path.isfile(candidate):
                                    svg_icon_path = candidate
                            else:
                                app_icon = icon_val + " "

                        if is_pooled:
                            # Pooled AI/pinned-notes item: neither has a real category backing it
                            # (true_category is None for both), so no reordering/renaming/
                            # right-click Edit-Delete-Move-to-category here — there's nothing to
                            # act on. Edit mode shows a plain button plus an inline 👁 hide toggle
                            # for AI items only (management controls have no place on the front
                            # end); view mode instead shows the normal preview/open-externally
                            # icon that any other launcher of this type would get (see
                            # _build_doc_preview_icon_button).
                            pooled_row = QWidget()
                            pooled_row_layout = QHBoxLayout(pooled_row)
                            pooled_row_layout.setContentsMargins(0, 0, 0, 0)
                            pooled_row_layout.setSpacing(2)

                            # AI items are sourced from config_folder_path — if that root was
                            # only reachable via the path-mapping fallback (see
                            # _get_ai_category_items()), flag every item it produced as
                            # "mapped" too, same pale-blue treatment as Documentation/Resources
                            # items with their own missing-but-mapped path.
                            is_ai_via_mapping = category_name == "AI" and getattr(self, '_ai_via_mapping', False)
                            btn = QPushButton(f"{app_icon}{display_name}")
                            btn.setMinimumHeight(30)
                            btn.setStyleSheet(self.get_item_button_style(mapped=is_ai_via_mapping))
                            if svg_icon_path:
                                btn.setIcon(QIcon(svg_icon_path))
                                btn.setIconSize(QSize(16, 16))
                            btn.clicked.connect(
                                lambda checked=False, p=path, a=app, b=btn: self.on_item_clicked(b, p, a)
                            )
                            tooltip = f"[{app}] {path}"
                            if is_ai_via_mapping:
                                tooltip += "\n⇄ Project folder not found directly — showing via path mapping (Settings → Advanced)"
                            btn.setToolTip(tooltip)
                            # No context menu here — neither AI items nor the pinned-notes entry
                            # have a real category backing them (true_category is None, see above).
                            pooled_row_layout.addWidget(btn, 1)

                            if self.edit_mode:
                                # No hide toggle for the permanent pinned-notes entry — there's
                                # nothing to hide it from (it's always re-inserted at the top of
                                # the Docs bucket regardless), only AI items get the hide toggle.
                                if category_name == "AI":
                                    hide_btn = QPushButton("👁")
                                    hide_btn.setFixedWidth(28)
                                    hide_btn.setMinimumHeight(30)
                                    hide_btn.setToolTip("Hide from Docs")
                                    hide_btn.setStyleSheet(self.get_item_button_style())
                                    hide_btn.clicked.connect(lambda checked=False, p=path: self._toggle_ai_item_hidden(p))
                                    pooled_row_layout.addWidget(hide_btn)
                            else:
                                preview_btn = self._build_doc_preview_icon_button(path, app)
                                if preview_btn:
                                    pooled_row_layout.addWidget(preview_btn)

                            drop_zone_layout.addWidget(pooled_row)
                            if col_idx == 0 and not self.edit_mode:
                                category_ref['items'].append({
                                    'widget': pooled_row, 'display_name': display_name, 'path': path, 'app': app,
                                })
                            continue

                        if self.edit_mode:
                            # EDIT MODE: compact row with drag handle, launcher, edit + delete buttons
                            item_widget = self.create_edit_item_widget(
                                col_idx, true_category, true_idx, display_name, path, app
                            )
                            drop_zone_layout.addWidget(item_widget)
                            category_drop_zone.add_item(item_widget, true_idx)
                        else:
                            # VIEW MODE: Show normal button
                            btn = DraggableItemButton(f"{app_icon}{display_name}", col_idx, true_category, true_idx)
                            btn.setMinimumHeight(30)
                            is_mapped_item = self._path_is_via_mapping(path)
                            btn.setStyleSheet(self.get_item_button_style(mapped=is_mapped_item))
                            if svg_icon_path:
                                btn.setIcon(QIcon(svg_icon_path))
                                btn.setIconSize(QSize(16, 16))
                            btn.clicked.connect(
                                lambda checked=False, p=path, a=app, b=btn: self.on_item_clicked(b, p, a)
                            )

                            # Set tooltip showing the command and path — always draggable here,
                            # since pooled (non-draggable) items are handled separately above.
                            tooltip = f"[{app}] {path}\n(Drag to reorder)"
                            if is_mapped_item:
                                tooltip += "\n⇄ Not found directly — showing via path mapping (Settings → Advanced)"
                            btn.setToolTip(tooltip)
                            if true_category is not None:
                                self._wire_launcher_context_menu(btn, col_idx, true_category, true_idx)

                            # Shared style for small icon buttons beside launchers
                            icon_btn_style = f"""
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
                                category_drop_zone.add_item(btn_container, true_idx)

                            # Check if this is a web link - add preview button
                            elif app in ("firefox", "chrome"):
                                # Create horizontal layout for button + preview icon
                                btn_layout = QHBoxLayout()
                                btn_layout.setContentsMargins(0, 0, 0, 0)
                                btn_layout.setSpacing(2)
                                btn_layout.addWidget(btn, 1)

                                # Local files need file:// URIs; web URLs load directly
                                _exp_path = os.path.expanduser(path)
                                _exp_lower = _exp_path.lower()
                                if _exp_lower.endswith('.md') and self._is_local_path(path):
                                    preview_btn = QPushButton("📄")
                                    preview_btn.setToolTip("Open externally" if self.layout_mode == "focus" else "Open in built-in editor")
                                    preview_btn.clicked.connect(
                                        lambda checked=False, md=_exp_path, a=app: self.open_in_app(md, a, force_external=True) if self.layout_mode == "focus" else self._open_markdown_file(md)
                                    )
                                elif _exp_lower.endswith(('.html', '.htm')) and self._is_local_path(path):
                                    preview_btn = QPushButton("🌐")
                                    preview_btn.setToolTip("Preview / open externally")
                                    preview_btn.clicked.connect(
                                        lambda checked=False, p=_exp_path, a=app: self.open_in_app(p, a, force_external=True) if self.layout_mode == "focus" else self._open_file_in_webview(p)
                                    )
                                else:
                                    preview_btn = QPushButton("🌐")
                                    preview_btn.setToolTip("Preview / open externally")
                                    preview_btn.clicked.connect(
                                        lambda checked=False, url=path, a=app: self.open_in_app(url, a, force_external=True) if self.layout_mode == "focus" else self.preview_in_webview(url)
                                    )
                                preview_btn.setMaximumWidth(28)
                                preview_btn.setMinimumHeight(30)
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
                                btn_layout.addWidget(preview_btn)

                                # Add layout to group
                                btn_container = QWidget()
                                btn_container.setLayout(btn_layout)
                                drop_zone_layout.addWidget(btn_container)
                                category_drop_zone.add_item(btn_container, true_idx)

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
                                    lambda checked=False, img_path=path, a=app: self.open_in_app(img_path, a, force_external=True) if self.layout_mode == "focus" else self.preview_in_image_viewer(img_path)
                                )
                                btn_layout.addWidget(preview_btn)

                                # Add layout to group
                                btn_container = QWidget()
                                btn_container.setLayout(btn_layout)
                                drop_zone_layout.addWidget(btn_container)
                                category_drop_zone.add_item(btn_container, true_idx)

                            # Check if this is a local HTML file - add built-in web viewer preview button
                            elif os.path.expanduser(path).lower().endswith(('.html', '.htm')) and self._is_local_path(path):
                                btn_layout = QHBoxLayout()
                                btn_layout.setContentsMargins(0, 0, 0, 0)
                                btn_layout.setSpacing(2)
                                btn_layout.addWidget(btn, 1)

                                preview_btn = QPushButton("🌐")
                                preview_btn.setMaximumWidth(28)
                                preview_btn.setMinimumHeight(30)
                                preview_btn.setToolTip("Preview in built-in web viewer")
                                preview_btn.setStyleSheet(icon_btn_style)
                                preview_btn.clicked.connect(
                                    lambda checked=False, p=os.path.expanduser(path), a=app: self.open_in_app(p, a, force_external=True) if self.layout_mode == "focus" else self._open_file_in_webview(p)
                                )
                                btn_layout.addWidget(preview_btn)

                                btn_container = QWidget()
                                btn_container.setLayout(btn_layout)
                                drop_zone_layout.addWidget(btn_container)
                                category_drop_zone.add_item(btn_container, true_idx)

                            # Check if this is a local .md file - add rendered markdown preview button
                            elif os.path.expanduser(path).lower().endswith('.md') and self._is_local_path(path):
                                btn_layout = QHBoxLayout()
                                btn_layout.setContentsMargins(0, 0, 0, 0)
                                btn_layout.setSpacing(2)
                                btn_layout.addWidget(btn, 1)

                                preview_btn = QPushButton("📄")
                                preview_btn.setMaximumWidth(28)
                                preview_btn.setMinimumHeight(30)
                                preview_btn.setToolTip("Open externally" if self.layout_mode == "focus" else "Open in built-in editor")
                                preview_btn.setStyleSheet(icon_btn_style)
                                preview_btn.clicked.connect(
                                    lambda checked=False, md=os.path.expanduser(path), a=app: self.open_in_app(md, a, force_external=True) if self.layout_mode == "focus" else self._open_markdown_file(md)
                                )
                                btn_layout.addWidget(preview_btn)

                                btn_container = QWidget()
                                btn_container.setLayout(btn_layout)
                                drop_zone_layout.addWidget(btn_container)
                                category_drop_zone.add_item(btn_container, true_idx)

                            # Check if this is a folder/terminal item - add terminal button
                            elif app in ("dolphin", "file_manager", "terminal", "tail_log"):
                                # Create horizontal layout for button + terminal icon
                                btn_layout = QHBoxLayout()
                                btn_layout.setContentsMargins(0, 0, 0, 0)
                                btn_layout.setSpacing(2)
                                btn_layout.addWidget(btn, 1)

                                # Add folder browser button — inverts like every other
                                # preview icon in Focus layout (main click there now routes
                                # these app types internally, via open_in_app()'s Focus
                                # block, so the icon's job flips to "open externally"
                                # instead — file manager/external terminal/external tail).
                                # Standard layout is unaffected: main click already opens
                                # externally there, so the icon keeps its original job of
                                # previewing the folder internally.
                                folder_btn = QPushButton()
                                # Blue hand-drawn folder icon, not QIcon.fromTheme("folder")/
                                # SP_DirIcon — both render yellow/manila on many systems; never
                                # use a yellow folder glyph for folders/files in this project.
                                folder_btn.setIcon(self._blue_folder_icon())
                                folder_btn.setIconSize(QSize(16, 16))
                                folder_btn.setMaximumWidth(28)
                                folder_btn.setMinimumHeight(30)
                                folder_btn.setToolTip("Open externally" if self.layout_mode == "focus" else "Open in folder browser")
                                folder_btn.setStyleSheet(icon_btn_style)
                                folder_btn.clicked.connect(
                                    lambda checked=False, p=path, a=app: self.open_in_app(p, a, force_external=True) if self.layout_mode == "focus" else self.preview_in_folder_browser(p)
                                )
                                btn_layout.addWidget(folder_btn)

                                # Add layout to group
                                btn_container = QWidget()
                                btn_container.setLayout(btn_layout)
                                drop_zone_layout.addWidget(btn_container)
                                category_drop_zone.add_item(btn_container, true_idx)
                            else:
                                if self._is_local_path(path):
                                    btn_layout = QHBoxLayout()
                                    btn_layout.setContentsMargins(0, 0, 0, 0)
                                    btn_layout.setSpacing(2)
                                    btn_layout.addWidget(btn, 1)

                                    folder_btn = QPushButton()
                                    # Blue hand-drawn folder icon — see the other folder_btn
                                    # above; never use a yellow folder glyph in this project.
                                    folder_btn.setIcon(self._blue_folder_icon())
                                    folder_btn.setIconSize(QSize(16, 16))
                                    folder_btn.setMaximumWidth(28)
                                    folder_btn.setMinimumHeight(30)
                                    folder_btn.setToolTip("Open in folder browser")
                                    folder_btn.setStyleSheet(icon_btn_style)
                                    folder_btn.clicked.connect(
                                        lambda checked=False, p=path: self.preview_in_folder_browser(p)
                                    )
                                    btn_layout.addWidget(folder_btn)

                                    btn_container = QWidget()
                                    btn_container.setLayout(btn_layout)
                                    drop_zone_layout.addWidget(btn_container)
                                    category_drop_zone.add_item(btn_container, true_idx)
                                else:
                                    drop_zone_layout.addWidget(btn)
                                    category_drop_zone.add_item(btn, true_idx)

                    # Populate search refs from drop zone (normal mode only). `i` is each
                    # item's TRUE index within category_drop_zone's own real category (they
                    # match exactly — pooled/non-real items never get added to a drop zone,
                    # see the `is_pooled` early-continue above) — not necessarily a position
                    # in `items`, which for the Docs bucket is a pooled, mixed-origin list.
                    # Look the real item up by its true category/index instead of `items[i]`.
                    if col_idx == 0 and not self.edit_mode:
                        real_items_for_zone = None
                        for cd in self.COLUMN_1:
                            if category_drop_zone.category_name in cd:
                                real_items_for_zone = cd[category_drop_zone.category_name]
                                break
                        if real_items_for_zone is not None:
                            for w, i in category_drop_zone.item_widgets:
                                if not (0 <= i < len(real_items_for_zone)):
                                    continue
                                it = real_items_for_zone[i]
                                category_ref['items'].append({
                                    'widget': w,
                                    'display_name': it[0],
                                    'path': it[1],
                                    'app': it[2] if len(it) > 2 else 'kate',
                                })

                    # Add the drop zone to group layout (always — drag works in both modes)
                    group_layout.addWidget(category_drop_zone)

                    # Add "Add Launcher" button in edit mode — excluded for AI, same as the
                    # rename/delete category header, since it isn't a real category to add into.
                    if self.edit_mode and category_name != "AI":
                        add_entry_btn = QPushButton("➕ Add Launcher")
                        add_entry_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
                        add_entry_btn.setStyleSheet(f"""
                            QPushButton {{
                                background-color: {self.t('bg_success')};
                                color: {self.t('fg_on_dark')};
                                border: 1px solid {self.t('bg_success_hover')};
                                border-radius: 3px;
                                padding: 4px 8px;
                                font-size: 10px;
                            }}
                            QPushButton:hover {{
                                background-color: {self.t('bg_success_hover')};
                                color: {self.t('fg_on_dark')};
                            }}
                        """)
                        # The Docs bucket's header reads "Docs" (a display label — see
                        # _build_grouped_categories()) but the real backing category may not
                        # exist yet, or may be named "Documentation"/legacy "Docs" — resolve
                        # (and auto-create if needed) via _ensure_documentation_category()
                        # rather than adding into the literal label "Docs".
                        if category_name == "Docs":
                            add_entry_btn.clicked.connect(
                                lambda checked=False, c_idx=col_idx:
                                    self.add_new_entry(c_idx, self._ensure_documentation_category())
                            )
                        else:
                            add_entry_btn.clicked.connect(
                                lambda checked=False, c_idx=col_idx, c_name=category_name: self.add_new_entry(c_idx, c_name)
                            )
                        group_layout.addWidget(add_entry_btn)

                    group_box.setLayout(group_layout)
                    group_container_layout.addWidget(group_box)

                    column_layout.addWidget(group_container)

                    # "Open Project Folder" footer right below the Docs category (only when
                    # a default folder is actually pinned — see the "⌂⌂ project folder"
                    # button/_pin_current_folder_as_project_default()). Deliberately labeled
                    # "Open Project Folder", not "Open in {file manager}" alone, since the
                    # project's default folder isn't necessarily where any given document in
                    # this list actually lives — same _make_viewer_footer() strip used by
                    # every other viewer's own "Open in X" button, for consistency.
                    if category_name == "Docs" and col_idx == 0 and not self.edit_mode and self.config_folder_path:
                        fm_name = os.path.basename(self.get_configured_file_manager()).capitalize()
                        column_layout.addWidget(
                            self._make_viewer_footer(
                                f"Open Project Folder in {fm_name}",
                                "Open this project's default folder in the file manager",
                                self.open_project_folder_external,
                            )
                        )

            # Add Tagged Files category at the bottom of Column 1
            if col_idx == 0 and not hide_launchers_for_folder_panel:
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

            # "N hidden — Manage" — the only way back for items hidden via the inline 👁
            # toggle (see _get_all_hidden_items()/_show_hidden_items_dialog()). Edit-mode
            # only, matching the hide toggle itself — show/hide is a curation action, not
            # something the front end should expose.
            if col_idx == 0 and self._is_grouped_view_active() and self.edit_mode:
                hidden_count = len(self._get_all_hidden_items())
                if hidden_count:
                    manage_hidden_btn = QPushButton(f"👁 {hidden_count} hidden — Manage")
                    manage_hidden_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
                    manage_hidden_btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {self.t('bg_button')};
                            color: {self.t('fg_secondary')};
                            border: 1px solid {self.t('border')};
                            border-radius: 3px;
                            padding: 4px 10px;
                            font-size: 11px;
                        }}
                        QPushButton:hover {{
                            background-color: {self.t('bg_button_hover')};
                            color: {self.t('fg_on_dark')};
                        }}
                    """)
                    manage_hidden_btn.clicked.connect(self._show_hidden_items_dialog)
                    column_layout.addWidget(manage_hidden_btn)

            # Add "Add Category" button in edit mode — hidden for the Focus-layout Docs tab
            # specifically: Docs is backed by one fixed "Documentation" category (see
            # _ensure_documentation_category()), so "add a new category" here doesn't map to
            # anything meaningful the way it does for Resources. A "Scan for docs" button
            # (same action as the Project Settings viewer's own, see _build_settings_form())
            # takes its place instead, since that's the action actually useful on this tab.
            is_docs_tab_editing = (
                focus_launcher_tab_active and self.active_launcher_tab == "docs" and self.edit_mode
            )
            if self.edit_mode and not is_docs_tab_editing:
                add_category_btn = QPushButton("➕ Add Category")
                add_category_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
                add_category_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {self.t('bg_category')};
                        color: {self.t('fg_on_dark')};
                        border: 1px solid {self.t('bg_category_hover')};
                        border-radius: 3px;
                        padding: 5px 10px;
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

            if is_docs_tab_editing:
                docs_scan_btn = QPushButton("🔍 Scan for docs")
                docs_scan_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
                docs_scan_btn.setToolTip("Scan project folder for documentation files")
                docs_scan_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {self.t('bg_category')};
                        color: {self.t('fg_on_dark')};
                        border: 1px solid {self.t('bg_category_hover')};
                        border-radius: 3px;
                        padding: 5px 10px;
                        font-size: 11px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: {self.t('bg_category_hover')};
                        color: {self.t('fg_on_dark')};
                    }}
                """)
                docs_scan_btn.clicked.connect(self._show_doc_scan_dialog)
                column_layout.addWidget(docs_scan_btn)


            # Add stretch at bottom of column
            column_layout.addStretch()

            # Store launcher column layout (will be added after viewer is built)
            launcher_layout = column_layout

            # Build the viewer panel (always shown)
            if col_idx == 0:
                self.column2_layout = QVBoxLayout()
                self.column2_layout.setContentsMargins(0, 4, 0, 0)  # Match column 1 top margin

                # Create viewer tab buttons (replacing header label)
                header_layout = QHBoxLayout()
                header_layout.setContentsMargins(0, 0, 0, 0)
                header_layout.setSpacing(3)

                # Tab button definitions: (mode, label, tooltip). Icons are bundled white
                # flat icons under assets/tab-icons/{mode}.png (see below) rather than
                # system-theme lookups — QIcon.fromTheme() proved unreliable across desktop
                # environments/Nix setups (many common names resolved to nothing at all),
                # so every tab now gets a guaranteed, consistent icon instead of some tabs
                # having one and others not.
                # Ordered action-first, viewing-last: Notes/Editor/Terminal are things you
                # actively work in, Web/PDF/Image are things you mostly look at. "Editor"
                # (not "Edit") to avoid reading like the title-bar "✏️ Edit Project" button
                # right above this row — column2_mode stays "code" internally either way.
                tab_buttons = [
                    ("notes",    "Notes",    "Project notes"),
                    ("code",     "Editor",   "Code editor"),
                    ("console",  "Terminal", "Embedded console"),
                    ("webview",  "Web",      "Web viewer"),
                    ("pdf",      "PDF",      "PDF viewer"),
                    ("image",    "Image",    "Image viewer"),
                ]
                if self.settings.get('kimai_url') and self.settings.get('kimai_token'):
                    tab_buttons.append(("time", "⏱ Time", "Kimai time tracker"))

                # Normal tab button style — bg_green_1 (the darkest stop) at rest.
                tab_btn_style = f"""
                    QPushButton {{
                        background-color: {self.t('bg_green_1')};
                        color: {self.t('fg_on_dark')};
                        font-weight: bold;
                        border-radius: 3px;
                        padding: 5px 8px;
                        font-size: 11px;
                    }}
                    QPushButton:hover {{
                        background-color: {self.t('bg_green_2')};
                        color: {self.t('fg_on_dark')};
                    }}
                """

                # Active tab button style — bg_green_3 (the brightest stop), no border.
                # A same-hue *darker* active fill (mirroring the launcher tab row's
                # bg_category/bg_category_hover direction) was tried and reverted: dark
                # theme's darkest green (bg_green_1, #123d28) sits almost exactly as dark as
                # the page background (#181B1D) behind the tab row, so the active tab nearly
                # vanished while the brighter *inactive* tabs drew all the attention — the
                # opposite of what "active" should signal. The launcher row's own
                # darker-when-active look isn't a deliberate "darker = active" design
                # language to match — it only has two blue shades total, so "active" simply
                # reuses the only other one available (which happens to be darker). Brighter
                # rather than darker is also the more conventional reading of "selected"
                # (most prominent, not least). No border either way, per the same reasoning
                # as the launcher row: once the fill genuinely differs, a same-hue border on
                # top is redundant (see CLAUDE.md's Active-tab border color note for the
                # fuller history — fg_on_dark, fg_secondary, and a bg_green_1 border were all
                # tried before landing here).
                active_tab_style = f"""
                    QPushButton {{
                        background-color: {self.t('bg_green_3')};
                        color: {self.t('fg_on_dark')};
                        font-weight: bold;
                        border-radius: 3px;
                        padding: 5px 8px;
                        font-size: 11px;
                    }}
                    QPushButton:hover {{
                        background-color: {self.t('bg_green_3')};
                        color: {self.t('fg_on_dark')};
                    }}
                """

                # Console tab (inactive state) — plain, identical to every other inactive tab.
                # This used to always carry a 1px solid fg_on_dark border to "stand out
                # slightly as built-in real-terminal access," but that border used the exact
                # same bright color as the active-tab border (just 1px thinner), so next to
                # the plain borderless Edit/PDF/etc tabs it read as "selected" even when it
                # wasn't — confirmed via screenshot, not just a theoretical concern. Border is
                # now reserved solely for genuine selection, matching every other tab.
                console_tab_btn_style = f"""
                    QPushButton {{
                        background-color: {self.t('bg_green_1')};
                        color: {self.t('fg_on_dark')};
                        font-weight: bold;
                        border-radius: 3px;
                        padding: 5px 8px;
                        font-size: 11px;
                    }}
                    QPushButton:hover {{
                        background-color: {self.t('bg_green_2')};
                        color: {self.t('fg_on_dark')};
                    }}
                """

                # Store tab buttons for styling updates
                self.viewer_tab_buttons = {}

                for mode, label, tooltip in tab_buttons:
                    btn = QPushButton(label)
                    btn.setMinimumHeight(self.d('header_btn_height'))
                    # Expanding + a stretch factor on addWidget (below) makes every tab
                    # button grow to fill the row equally, rather than a fixed width —
                    # with Code added as a 6th/7th tab, a flat 175px minimum per button
                    # started overflowing the available width and getting clipped. A small
                    # minimum keeps things sane if the row is ever squeezed very narrow.
                    btn.setMinimumWidth(60)
                    btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                    btn.setToolTip(tooltip)

                    icon_path = os.path.join(self.script_dir, "assets", "tab-icons", f"{mode}.png")
                    if os.path.exists(icon_path):
                        btn.setIcon(QIcon(icon_path))
                        btn.setIconSize(QSize(16, 16))

                    # Set style based on whether this is the active mode
                    if mode == self.column2_mode:
                        btn.setStyleSheet(active_tab_style)
                    elif mode == 'console':
                        btn.setStyleSheet(console_tab_btn_style)
                    else:
                        btn.setStyleSheet(tab_btn_style)

                    # Connect click handler
                    btn.clicked.connect(lambda checked=False, m=mode: self.switch_to_viewer_mode(m))

                    header_layout.addWidget(btn, 1)
                    self.viewer_tab_buttons[mode] = btn
                    # Notes tab only visible in Focus layout
                    if mode == "notes":
                        btn.setVisible(self.layout_mode == "focus")

                # Settings shortcut — always visible, to the LEFT of the pin button below.
                # Effectively a second "Edit Project" entry point: clicking it while NOT in
                # edit mode enters edit mode exactly like the title-bar button does (same
                # toggle_edit_mode(), which also flips that button to "💾 Save"). Clicking it
                # while ALREADY in edit mode must NOT re-toggle (that would exit edit mode
                # and save) — it just needs to jump back to the Settings viewer, since its
                # other job is recovering from having clicked over to another tab (Web/PDF/
                # etc.) mid-edit. Hence the explicit edit_mode check in
                # _settings_shortcut_clicked() rather than connecting straight to
                # toggle_edit_mode(). Not part of set_viewer_as_default()'s pinnable modes
                # (that function already returns early — no case — for "settings", so a
                # project can never accidentally default-load into the Settings viewer).
                # Registered into self.viewer_tab_buttons (even though it's not a full tab,
                # not in the mode_info loop above) purely so update_viewer_tab_styling() —
                # called by switch_to_viewer_mode() on every mode switch, without a full
                # rebuild — keeps its active/resting style in sync like the real tabs.
                settings_tab_btn = QPushButton()
                settings_tab_icon_path = os.path.join(self.script_dir, "assets", "tab-icons", "settings.png")
                if os.path.exists(settings_tab_icon_path):
                    settings_tab_btn.setIcon(QIcon(settings_tab_icon_path))
                    settings_tab_btn.setIconSize(QSize(16, 16))
                settings_tab_btn.setFixedWidth(28)
                settings_tab_btn.setMinimumHeight(self.d('header_btn_height'))
                settings_tab_btn.setToolTip("Edit Project / Project Settings")
                settings_tab_btn.setStyleSheet(active_tab_style if self.column2_mode == "settings" else tab_btn_style)
                settings_tab_btn.clicked.connect(self._settings_shortcut_clicked)
                header_layout.addWidget(settings_tab_btn)
                self.viewer_tab_buttons['settings'] = settings_tab_btn

                # Pin the current viewer as this project's default — a single shared button
                # replacing the old per-viewer 📌 buttons that used to live in each viewer's
                # own toolbar (PDF/webview/image/console/notes/time), mirroring the single
                # pin button on the launcher tab row (see build_main_content's Focus-layout
                # tab row) for consistency. set_viewer_as_default() already dispatches on
                # self.column2_mode, so one button works for whichever tab is active.
                viewer_pin_btn = QPushButton()
                viewer_pin_icon_path = os.path.join(self.script_dir, "assets", "tab-icons", "pin.png")
                if os.path.exists(viewer_pin_icon_path):
                    viewer_pin_btn.setIcon(QIcon(viewer_pin_icon_path))
                    viewer_pin_btn.setIconSize(QSize(16, 16))
                viewer_pin_btn.setFixedWidth(28)
                viewer_pin_btn.setMinimumHeight(self.d('header_btn_height'))
                viewer_pin_btn.setToolTip("Set current viewer as default for this project")
                viewer_pin_btn.setStyleSheet(tab_btn_style)
                viewer_pin_btn.clicked.connect(self.set_viewer_as_default)
                header_layout.addWidget(viewer_pin_btn)

                self.column2_layout.addLayout(header_layout)

                # Create stacked widget for PDF and webview
                self.column2_stack = QWidget()
                self.column2_stack_layout = QVBoxLayout(self.column2_stack)
                self.column2_stack_layout.setContentsMargins(0, 0, 0, 0)
                # Fixed (not minimum) height — see ViewerResizeHandle's docstring for why a
                # minimum isn't enough: on a project with a tall launcher column, the surrounding
                # layout stretches column2_stack past any floor anyway. A fixed height opts it out
                # of that entirely, so it's exactly viewer_height regardless of the launcher
                # column's height, with any extra space left blank below the resize handle
                # instead. Stored per-machine (not per-project) since the comfortable value
                # depends on monitor resolution, not the project.
                self.column2_stack.setFixedHeight(self.settings.get("viewer_height", 1000))

                # PDF viewer container
                self.pdf_container = QWidget()
                pdf_container_layout = QVBoxLayout(self.pdf_container)
                pdf_container_layout.setContentsMargins(0, 0, 0, 0)

                # Create PDF toolbar
                self.create_pdf_toolbar(pdf_container_layout)

                # Multi-instance tab strip (one button+close per open PdfTabState) — see
                # _build_pdf_tab_strip()/PdfTabState. Just builds the (initially empty)
                # strip widgets here; actually loading tabs' documents and activating one
                # happens later in this method, once self.pdf_label exists (see the "Load
                # all remembered PDF tabs" block below).
                self._build_pdf_tab_strip(pdf_container_layout)

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
                self.pdf_label.setStyleSheet(f"background-color: {self.t('bg_viewer')}; color: {self.t('fg_muted')}; font-size: 14px;")
                self._set_viewer_placeholder(self.pdf_label, "pdf", "No PDF loaded\n\nUse the Open button to open a PDF file")
                self.pdf_scroll.setWidget(self.pdf_label)

                pdf_container_layout.addWidget(self.pdf_scroll)

                pdfviewer_setting = self.settings.get('pdfviewer', '')
                if pdfviewer_setting:
                    pdf_ext_name = os.path.splitext(os.path.basename(pdfviewer_setting))[0].capitalize()
                    pdf_footer_label = f"Open in {pdf_ext_name}"
                else:
                    pdf_footer_label = "Open PDF"
                pdf_container_layout.addWidget(
                    self._make_viewer_footer(
                        pdf_footer_label, "Open PDF in external viewer", self.open_pdf_in_external_viewer,
                        left_widget=self._build_pdf_footer_page_nav()
                    )
                )

                # Webview container
                self.webview_container = QWidget()
                webview_container_layout = QVBoxLayout(self.webview_container)
                webview_container_layout.setContentsMargins(0, 0, 0, 0)

                # Create webview toolbar
                self.create_webview_toolbar(webview_container_layout)

                # Multi-instance tab strip — mirrors the PDF/Image viewers' (see
                # _build_pdf_tab_strip()'s comment for why this is built here but actually
                # populated/activated later in this method).
                self._build_web_tab_strip(webview_container_layout)

                # Webview is created once in __init__; just re-add it to the new layout.
                # Dark mode may change between project loads — always (re)apply in both
                # directions. ForceDarkMode is a persistent WebEngine setting that sticks until
                # explicitly changed, so only ever setting it True (never False) left it stuck
                # on permanently once dark mode was toggled on once, even after switching back
                # to light — affecting both plain web pages and the Muya editor (which shares
                # this same webview), where it layered an unwanted extra dark filter on top of
                # the correctly-reloaded light paper CSS.
                try:
                    self.webview.settings().setAttribute(
                        QWebEngineSettings.WebAttribute.ForceDarkMode, self.current_theme == "dark"
                    )
                except AttributeError:
                    pass  # ForceDarkMode requires Qt 6.3+
                webview_container_layout.addWidget(self.webview, 1)  # stretch to fill space

                browser_name = self.detect_default_browser().capitalize()
                webview_container_layout.addWidget(
                    self._make_viewer_footer(f"Open in {browser_name}", "Open URL in external browser", self.open_webview_in_external_browser)
                )

                # Image viewer container
                self.image_container = QWidget()
                image_container_layout = QVBoxLayout(self.image_container)
                image_container_layout.setContentsMargins(0, 0, 0, 0)

                # Create image toolbar
                self.create_image_toolbar(image_container_layout)

                # Multi-instance tab strip — mirrors the PDF viewer's (see
                # _build_pdf_tab_strip()'s comment for why this is built here but actually
                # populated with loaded content later in this method).
                self._build_image_tab_strip(image_container_layout)

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
                self.image_label.setStyleSheet(f"background-color: {self.t('bg_viewer')}; color: {self.t('fg_muted')}; font-size: 14px;")
                self._set_viewer_placeholder(self.image_label, "image", "No image loaded\n\nUse the Open button to open an image")
                self.image_scroll.setWidget(self.image_label)

                image_container_layout.addWidget(self.image_scroll)

                image_container_layout.addWidget(
                    self._make_viewer_footer("Open in Gwenview", "Open image in Gwenview", self.open_image_in_external_viewer)
                )

                # Code editor container — internal CodeMirror 6 editor for JS/Python/HTML/
                # CSS/PHP (see CodeEditorSession, _open_code_file_in_editor). Its own
                # toolbar (filename/language label, Save button — no URL bar/back/forward,
                # unlike the webview toolbar) since this is a different tool, not a "page".
                self.code_container = QWidget()
                code_container_layout = QVBoxLayout(self.code_container)
                code_container_layout.setContentsMargins(0, 0, 0, 0)

                self.create_code_editor_toolbar(code_container_layout)

                # Multi-instance tab strip — mirrors the PDF/Image/Web viewers' (see
                # _build_pdf_tab_strip()'s comment for why this is built here but actually
                # populated/activated later in this method).
                self._build_code_tab_strip(code_container_layout)

                code_container_layout.addWidget(self.code_webview, 1)  # stretch to fill space

                editor_name = os.path.basename(self.get_configured_editor()).capitalize()
                code_container_layout.addWidget(
                    self._make_viewer_footer(f"Open in {editor_name}", "Open this file in the configured editor", self.open_code_file_in_external_editor)
                )

                # Settings viewer container — Project Settings, embedded as a viewer instead
                # of a modal dialog (see _build_settings_form()). Own toolbar (Save button)
                # rebuilt fresh each time like the other viewers'; self.settings_form itself
                # is the persistent part, just re-added into a scroll area here.
                self.settings_container = QWidget()
                settings_container_layout = QVBoxLayout(self.settings_container)
                settings_container_layout.setContentsMargins(0, 0, 0, 0)

                self.create_settings_toolbar(settings_container_layout)
                self._style_settings_form()  # re-apply in case the theme changed since last build

                settings_scroll = QScrollArea()
                settings_scroll.setWidgetResizable(True)
                settings_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
                settings_scroll.setWidget(self.settings_form)
                settings_container_layout.addWidget(settings_scroll, 1)

                # Help viewer container — combines README + Launcher Examples as two HTML tabs
                # in a single page (see _build_help_html). Lives outside the normal project-viewer
                # tab row (accessed via the footer's "❓ Help" button instead) since it's reference
                # material, not something tied to a specific project.
                self.help_container = QWidget()
                help_container_layout = QVBoxLayout(self.help_container)
                help_container_layout.setContentsMargins(0, 0, 0, 0)

                # Create help toolbar
                self.create_help_toolbar(help_container_layout)

                # QWebEngineView (not QTextBrowser) so the combined page's CSS-only tab
                # switching (:checked ~ sibling selectors) actually works.
                self.help_browser = QWebEngineView()
                self._enable_web_fullscreen_support(self.help_browser)
                self.help_browser.setStyleSheet(f"""
                    QWebEngineView {{
                        border: 2px solid {self.t('border')};
                        border-radius: 5px;
                    }}
                """)
                help_container_layout.addWidget(self.help_browser, 1)  # stretch factor

                help_editor = (self.settings.get("open_note_external") or "kate").capitalize()
                help_footer = QWidget()
                help_footer.setStyleSheet(f"background-color: {self.t('bg_secondary')}; border-top: 1px solid {self.t('border')};")
                help_footer_layout = QHBoxLayout(help_footer)
                help_footer_layout.setContentsMargins(6, 4, 6, 4)
                help_footer_layout.addStretch()
                for label, tooltip, callback in (
                    (f"Open README in {help_editor}", "Open README.md in editor", self.open_help_in_external_editor),
                    (f"Open Examples in {help_editor}", "Open EXAMPLES.html in editor", self.open_examples_in_external_editor),
                ):
                    footer_btn = QPushButton(label)
                    footer_btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {self.t('bg_button')};
                            color: {self.t('fg_primary')};
                            border: 1px solid {self.t('border')};
                            border-radius: 4px;
                            padding: 3px 10px;
                            font-size: 11px;
                        }}
                        QPushButton:hover {{
                            background-color: {self.t('bg_button_hover')};
                            color: {self.t('fg_on_dark')};
                        }}
                    """)
                    footer_btn.setToolTip(tooltip)
                    footer_btn.clicked.connect(callback)
                    help_footer_layout.addWidget(footer_btn)
                help_container_layout.addWidget(help_footer)

                # Console container (qtconsole, or a real terminal via ttyd — see
                # resolve_console_backend/_open_terminal_tab). console_container_layout is
                # stashed on self (below) so _activate_terminal_tab()/_close_terminal_tab()
                # can add/remove the active tab's webview in place, without a full rebuild.
                self.console_container = QWidget()
                console_container_layout = QVBoxLayout(self.console_container)
                console_container_layout.setContentsMargins(0, 0, 0, 0)
                self.console_container_layout = console_container_layout
                self.console_available = False
                # Stale-widget-reference guard (same pattern as the Quick File Browser
                # Panel's own widget-reference reset — see CLAUDE.md): these are only
                # (re)built a few lines below when the ttyd backend is active. The OLD
                # tree's widgets were already destroyed by init_ui()'s setCentralWidget()
                # call before this method ever runs — without resetting these to None here,
                # a qtconsole-backend rebuild (which skips rebuilding them) would leave them
                # pointing at already-deleted C++ objects, and _close_all_terminal_tabs()'s
                # _rebuild_terminal_tab_strip() call (from the backend-switch branch just
                # below) would crash touching them.
                self.terminal_tab_strip_widget = None
                self.terminal_tab_strip_layout = None
                self.console_empty_label = None

                # Create console toolbar
                self.create_console_toolbar(console_container_layout)

                if self.resolve_console_backend() == "ttyd":
                    self._build_terminal_tab_strip(console_container_layout)

                    # Placeholder shown only when zero terminal tabs are open (e.g. every
                    # tab was closed) — the "+ New Terminal" toolbar button remains the way
                    # back in. Built once per rebuild like every other viewer's placeholder;
                    # _activate_terminal_tab()/_close_terminal_tab() toggle its visibility.
                    self.console_empty_label = QLabel("No terminal open.\n\nUse '+ New Terminal' above to start one.")
                    self.console_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.console_empty_label.setStyleSheet(f"color: {self.t('fg_secondary')}; padding: 20px;")
                    console_container_layout.addWidget(self.console_empty_label, 1)

                    # A rebuild's fresh console_container_layout is a brand-new object even
                    # though the webview widgets themselves persist (see init_ui()'s detach
                    # loop) — reset the tracked "currently added to a layout" widget so
                    # _activate_terminal_tab() below re-adds it to *this* layout rather than
                    # wrongly assuming it's already placed (it was only ever placed in the
                    # now-discarded previous layout).
                    self._console_active_webview = None

                    if not self.terminal_tabs:
                        self.terminal_tabs.append(
                            TerminalTabState(getattr(self, 'console_path', None) or os.path.expanduser("~"))
                        )
                        self.terminal_active_index = 0
                    if not (0 <= self.terminal_active_index < len(self.terminal_tabs)):
                        self.terminal_active_index = 0
                    self._activate_terminal_tab(self.terminal_active_index)
                    self.console_available = True
                else:
                    self._close_all_terminal_tabs()  # backend switched away from ttyd — don't leak any of them
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

                terminal_name = os.path.basename(self.get_configured_terminal()).capitalize()
                console_container_layout.addWidget(
                    self._make_viewer_footer(f"Open in {terminal_name}", "Open in external terminal", self.console_open_external)
                )

                # Folder browser container
                self.folder_container = QWidget()
                folder_container_layout = QVBoxLayout(self.folder_container)
                folder_container_layout.setContentsMargins(0, 0, 0, 0)

                # Create folder toolbar
                self.create_folder_toolbar(folder_container_layout)

                # QTreeWidget for file/folder display
                self.folder_browser = QTreeWidget()
                self.folder_browser.setHeaderHidden(True)
                self.folder_browser.setStyleSheet(f"""
                    QTreeWidget {{
                        background-color: {self.t('bg_secondary')};
                        border: 2px solid {self.t('border')};
                        border-radius: 5px;
                        color: {self.t('fg_primary')};
                        font-size: 12px;
                    }}
                    QTreeWidget::item {{
                        padding: 4px 8px;
                    }}
                    QTreeWidget::item:hover {{
                        background-color: {self.t('bg_button_hover')};
                        color: {self.t('fg_on_dark')};
                    }}
                    QTreeWidget::item:selected {{
                        background-color: {self.t('bg_category')};
                        color: {self.t('fg_on_dark')};
                    }}
                """)
                self.folder_browser.setMouseTracking(True)
                self.folder_browser.viewport().setMouseTracking(True)
                self.folder_browser.setItemDelegate(FolderBrowserDelegate(self))
                self.folder_browser.itemClicked.connect(self.on_folder_item_clicked)
                self.folder_browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                self.folder_browser.customContextMenuRequested.connect(self.folder_browser_context_menu)

                # QListWidget in icon-grid mode — Dolphin-style alternative to the tree above
                self.folder_icon_view = QListWidget()
                self.folder_icon_view.setViewMode(QListWidget.ViewMode.IconMode)
                self.folder_icon_view.setResizeMode(QListWidget.ResizeMode.Adjust)
                self.folder_icon_view.setMovement(QListWidget.Movement.Static)
                self.folder_icon_view.setWrapping(True)
                self.folder_icon_view.setIconSize(QSize(48, 48))
                self.folder_icon_view.setGridSize(QSize(96, 112))
                self.folder_icon_view.setSpacing(4)
                self.folder_icon_view.setWordWrap(True)
                self.folder_icon_view.setUniformItemSizes(True)
                self.folder_icon_view.setStyleSheet(f"""
                    QListWidget {{
                        background-color: {self.t('bg_secondary')};
                        border: 2px solid {self.t('border')};
                        border-radius: 5px;
                        color: {self.t('fg_primary')};
                        font-size: 11px;
                    }}
                    QListWidget::item {{
                        padding: 4px;
                        border-radius: 3px;
                    }}
                    QListWidget::item:hover {{
                        background-color: {self.t('bg_button_hover')};
                        color: {self.t('fg_on_dark')};
                    }}
                    QListWidget::item:selected {{
                        background-color: {self.t('bg_category')};
                        color: {self.t('fg_on_dark')};
                    }}
                """)
                self.folder_icon_view.itemClicked.connect(self.on_folder_icon_item_clicked)
                self.folder_icon_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                self.folder_icon_view.customContextMenuRequested.connect(self.folder_icon_view_context_menu)

                self.folder_view_stack = QStackedWidget()
                self.folder_view_stack.addWidget(self.folder_browser)
                self.folder_view_stack.addWidget(self.folder_icon_view)
                self.folder_view_stack.setCurrentIndex(1 if self.folder_view_mode == "icons" else 0)
                folder_container_layout.addWidget(self.folder_view_stack)

                self.folder_filter_input = self._build_folder_filter_bar(folder_container_layout)

                fm_name = os.path.basename(self.get_configured_file_manager()).capitalize()
                folder_container_layout.addWidget(
                    self._make_viewer_footer(f"Open in {fm_name}", "Open in file manager", self.folder_open_external)
                )

                # Initialize folder browser state - preserve navigation on same-project refresh;
                # reset to config default only when no path is set (e.g. first load or project switch)
                if not (hasattr(self, 'folder_current_path') and self.folder_current_path):
                    if hasattr(self, 'config_folder_path') and self.config_folder_path:
                        self.folder_current_path = self.config_folder_path
                    else:
                        self.folder_current_path = os.path.expanduser("~")

                # Build Kimai time viewer
                self._build_time_viewer()

                # Notes viewer container — notes_panel is reparented here in Focus layout
                self.notes_viewer_container = QWidget()
                self.notes_viewer_layout = QVBoxLayout(self.notes_viewer_container)
                self.notes_viewer_layout.setContentsMargins(0, 0, 0, 0)

                # Add all containers to stack layout
                self.column2_stack_layout.addWidget(self.pdf_container)
                self.column2_stack_layout.addWidget(self.webview_container)
                self.column2_stack_layout.addWidget(self.image_container)
                self.column2_stack_layout.addWidget(self.help_container)
                self.column2_stack_layout.addWidget(self.console_container)
                self.column2_stack_layout.addWidget(self.folder_container)
                self.column2_stack_layout.addWidget(self.time_container)
                self.column2_stack_layout.addWidget(self.notes_viewer_container)
                self.column2_stack_layout.addWidget(self.code_container)
                self.column2_stack_layout.addWidget(self.settings_container)

                # Show correct container based on mode
                self.pdf_container.hide()
                self.webview_container.hide()
                self.image_container.hide()
                self.help_container.hide()
                self.console_container.hide()
                self.folder_container.hide()
                self.time_container.hide()
                self.notes_viewer_container.hide()
                self.code_container.hide()
                self.settings_container.hide()
                if self.column2_mode == "pdf":
                    self.pdf_container.show()
                elif self.column2_mode == "webview":
                    self.webview_container.show()
                elif self.column2_mode == "image":
                    self.image_container.show()
                elif self.column2_mode == "code":
                    self.code_container.show()
                    self._update_code_editor_buttons()
                elif self.column2_mode == "help":
                    self.help_container.show()
                    self.load_help_content()
                elif self.column2_mode == "console":
                    self.console_container.show()
                elif self.column2_mode == "folder":
                    self.folder_container.show()
                    self.populate_folder_browser(self.folder_current_path)
                elif self.column2_mode == "time":
                    self.time_container.show()
                    self._kimai_load_entries()
                elif self.column2_mode == "notes":
                    self.notes_viewer_container.show()
                elif self.column2_mode == "settings":
                    self.settings_container.show()
                    # Populate only if not already loaded for this project — see
                    # _populate_settings_form()'s docstring for why this guard exists
                    # (preserves in-progress edits across an unrelated rebuild).
                    if getattr(self, '_settings_loaded_for', None) != self.current_config_file:
                        self._populate_settings_form()
                        self._settings_loaded_for = self.current_config_file

                self.column2_layout.addWidget(self.column2_stack, 1)  # stretch factor to fill space

                # Drag handle to manually resize the viewer's height — see the settings comment
                # on column2_stack.setFixedHeight() above for why this is a per-machine setting.
                viewer_resize_handle = ViewerResizeHandle(self.column2_stack, self._save_viewer_height)
                viewer_resize_handle.setStyleSheet(f"""
                    QLabel {{
                        background-color: {self.t('bg_button')};
                        color: {self.t('fg_secondary')};
                        border-top: 1px solid {self.t('border')};
                        border-bottom: 1px solid {self.t('border')};
                    }}
                    QLabel:hover {{
                        background-color: {self.t('bg_button_hover')};
                    }}
                """)
                self.column2_layout.addWidget(viewer_resize_handle)

                # With column2_stack now Fixed-height (see above), nothing left in this layout
                # can expand — and a Qt QBoxLayout with no expansive item centers its packed
                # content within the allocated space rather than top-aligning it. On a project
                # with a tall launcher column (so column2_widget is stretched tall by the
                # splitter), that centered the tab row/viewer/handle in a sea of blank space
                # instead of anchoring them to the top. A trailing stretch forces all the extra
                # space to collect at the bottom instead.
                self.column2_layout.addStretch()

                # Load every remembered PDF tab's document (self.pdf_tabs was populated
                # from disk in load_notes(), with doc=None for each — reopened here every
                # rebuild, matching the old single-PDF behavior of reloading on every
                # refresh_projects() call) and activate whichever tab was active.
                if self.pdf_tabs:
                    for _pdf_tab in self.pdf_tabs:
                        self._pdf_load_tab_doc(_pdf_tab)
                    _restore_index = self.pdf_active_index if 0 <= self.pdf_active_index < len(self.pdf_tabs) else 0
                    self._activate_pdf_tab(_restore_index)

                # Restore every remembered Web tab and activate whichever was active — same
                # pattern as the PDF/Image tabs restore. _activate_web_tab() (not
                # _open_web_tab()/_open_markdown_in_webview()) is used here deliberately: it
                # just navigates to an existing tab, it doesn't create a new one.
                if self.web_tabs:
                    _restore_index = self.web_active_index if 0 <= self.web_active_index < len(self.web_tabs) else 0
                    self._activate_web_tab(_restore_index)

                # Load every remembered Image tab's pixmap (reopened every rebuild, same
                # reasoning as the PDF tabs restore above) and activate whichever was active.
                if self.image_tabs:
                    for _image_tab in self.image_tabs:
                        self._image_load_tab_pixmap(_image_tab)
                    _restore_index = self.image_active_index if 0 <= self.image_active_index < len(self.image_tabs) else 0
                    self._activate_image_tab(_restore_index)

                # Restore Editor tabs (see CodeTabState). Seed a first tab from the pinned
                # default (set_viewer_as_default()'s "code" branch) if there are no tabs at
                # all yet (a brand new project, or one that's never had a file opened).
                # Gated like Notes' own reload-key (project or theme change only — an
                # incidental refresh must not re-trigger _activate_code_tab()'s reload,
                # which would visibly flicker the editor and, if unguarded, could risk
                # losing an unflushed edit for no reason).
                if not self.code_tabs and getattr(self, 'config_code_file', None):
                    self.code_tabs.append(CodeTabState(
                        self.config_code_file, self._code_editor_language_for(self.config_code_file)
                    ))
                    self.code_active_index = 0
                code_reload_key = (self.current_config_file, self.current_theme)
                code_should_reload = getattr(self, '_code_loaded_for', None) != code_reload_key
                self._code_loaded_for = code_reload_key
                if code_should_reload and self.code_tabs:
                    _restore_code_index = self.code_active_index if 0 <= self.code_active_index < len(self.code_tabs) else 0
                    self._activate_code_tab(_restore_code_index)

        # Notes panel: hosts the persistent Muya editor (self.notes_webview). Placed directly
        # into whichever container matches the current layout below — no later reparenting
        # needed (notes_webview's own construction/detach in __init__/init_ui() already
        # handles it safely; _enter_focus_layout()/_enter_standard_layout() no longer move
        # anything notes-related).
        self.notes_panel = QWidget()
        notes_panel_layout = QVBoxLayout(self.notes_panel)
        notes_panel_layout.setContentsMargins(0, 4, 0, 0)  # Match column 1 top margin

        # Toolbar (filename label + Open + Project Note buttons) only makes sense in Focus
        # layout, where the Notes tab can show an arbitrary note (see notes_md_path) —
        # Standard layout's Notes column is a fixed pane that only ever shows the project's
        # own note, so there's nothing for a toolbar to do there.
        self.notes_current_label = None
        self.notes_open_btn = None
        self.notes_home_btn = None
        # Reset before conditional (re)construction, same reasoning as the Quick File
        # Browser Panel's widget references documented elsewhere — otherwise a Standard-
        # layout rebuild leaves these pointing at widgets from a stale Focus-layout build.
        self.notes_tab_strip_widget = None
        self.notes_tab_strip_layout = None
        if self.layout_mode == "focus":
            self.create_notes_toolbar(notes_panel_layout)

        notes_panel_layout.addWidget(self.notes_webview, 1)

        # Only reload notes content into the webview when the project, layout, or theme has
        # actually changed since the last load (the paper CSS depends on layout_mode/
        # current_theme) — an incidental refresh (editing a launcher, etc.) just re-adds the
        # already-loaded, already-live webview to its (possibly freshly-rebuilt) container.
        notes_reload_key = (self.current_config_file, self.layout_mode, self.current_theme)
        notes_should_reload = getattr(self, '_notes_loaded_for', None) != notes_reload_key
        self._notes_loaded_for = notes_reload_key
        if notes_should_reload:
            # self.notes_tabs was already (re)built from disk in load_notes(), above — just
            # activate whichever tab was active (never _open_notes_tab(), which would create
            # a brand new one instead of restoring the existing list).
            _restore_notes_index = self.notes_active_index if 0 <= self.notes_active_index < len(self.notes_tabs) else 0
            self._activate_notes_tab(_restore_notes_index)

        # Archive/Joplin/external-editor controls — all keyed to the project's own
        # get_notes_file_path()/get_archive_file_path() (archive_notes(), view_archive(),
        # sync_to_joplin(), open_note_in_external_editor() none of them take a path
        # parameter), not to whatever's actually displayed. Showing them while an arbitrary
        # note is loaded (Focus layout's Notes tab, see _open_note_in_notes_tab()) would act
        # on the wrong file — archive_notes() in particular would stash the arbitrary note's
        # content into the PROJECT's archive and then wipe the PROJECT's own notes file to
        # empty via save_notes(""), silently destroying unrelated data. Wrapped in one
        # container widget (self.notes_archive_section) rather than gated at construction
        # time, since switching notes (_open_note_in_notes_tab()) does NOT rebuild
        # notes_panel — only _update_notes_toolbar() re-runs — so visibility has to be a
        # live toggle, not a one-time decision baked in when the panel was built.
        archive_section = QWidget()
        archive_section_layout = QVBoxLayout(archive_section)
        archive_section_layout.setContentsMargins(0, 0, 0, 0)
        archive_section_layout.setSpacing(0)
        self.notes_archive_section = archive_section

        # Add archive buttons at the bottom right
        archive_bar = QHBoxLayout()
        archive_bar.setContentsMargins(0, 5, 0, 0)

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

        # Joplin sync / external editor buttons (only shown if configured)
        if self.settings.get("joplin_token"):
            joplin_btn = QPushButton("📓")
            joplin_btn.setStyleSheet(archive_btn_style)
            joplin_btn.setToolTip("Sync to Joplin")
            joplin_btn.clicked.connect(self.sync_to_joplin)
            archive_bar.addWidget(joplin_btn)

        archive_bar.addStretch()

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

        archive_section_layout.addLayout(archive_bar)

        # "Open in {editor}" footer — same _make_viewer_footer() thin right-aligned strip
        # used by every other viewer (PDF/Web/Image/Console/Folder/Help), for consistency,
        # replacing the old bare 📝 icon button that used to sit among the Joplin/archive
        # controls above.
        external_editor = self.settings.get("open_note_external")
        if external_editor:
            archive_section_layout.addWidget(
                self._make_viewer_footer(
                    f"Open in {external_editor.capitalize()}",
                    f"Open note in {external_editor}",
                    self.open_note_in_external_editor,
                )
            )

        notes_panel_layout.addWidget(archive_section)
        archive_section.setVisible(not getattr(self, 'notes_md_path', None))

        # Place notes_panel into whichever container matches the current layout — decided
        # once, here, instead of built into the Standard-layout slot and reparented later.
        if self.layout_mode == "focus":
            self.notes_viewer_layout.addWidget(self.notes_panel)

        # Wrap each column layout in a QWidget (QSplitter requires QWidget children)
        launcher_widget = QWidget()
        launcher_widget.setLayout(launcher_layout)
        self.launcher_widget = launcher_widget

        column2_widget = QWidget()
        column2_widget.setLayout(self.column2_layout)
        self.column2_widget = column2_widget

        # Right-column widget holds notes_panel; stored for show/hide toggling in Focus layout
        self.notepad_column_widget = QWidget()
        notepad_col_layout = QVBoxLayout(self.notepad_column_widget)
        notepad_col_layout.setContentsMargins(0, 0, 0, 0)
        notepad_col_layout.setSpacing(0)
        if self.layout_mode != "focus":
            notepad_col_layout.addWidget(self.notes_panel)
        notepad_widget = self.notepad_column_widget

        # Build splitter
        self.columns_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.columns_splitter.setHandleWidth(6)
        self.columns_splitter.setChildrenCollapsible(False)
        self.columns_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {self.t('bg_secondary')};
                border-radius: 2px;
                margin: 0px 2px;
            }}
            QSplitter::handle:hover {{
                background-color: {self.t('border_light')};
            }}
        """)

        if self.swap_columns:
            self.columns_splitter.addWidget(column2_widget)
            self.columns_splitter.addWidget(launcher_widget)
        else:
            self.columns_splitter.addWidget(launcher_widget)
            self.columns_splitter.addWidget(column2_widget)
        self.columns_splitter.addWidget(notepad_widget)

        # Set minimum widths so columns can't be collapsed to nothing
        for i in range(self.columns_splitter.count()):
            self.columns_splitter.widget(i).setMinimumWidth(150)

        # Restore saved splitter state, or default to equal thirds
        saved_state = self.settings.get("splitter_state")
        if saved_state:
            self.columns_splitter.restoreState(QByteArray.fromHex(saved_state.encode()))
        else:
            self.columns_splitter.setSizes([1, 1, 1])

        self.columns_splitter.splitterMoved.connect(self._save_splitter_state)

        parent_layout.addWidget(self.columns_splitter, 1)  # stretch=1 so it fills available vertical space

        # Add spacer before Projects section
        spacer = QWidget()
        spacer.setFixedHeight(20)
        parent_layout.addWidget(spacer)

        # Create unified projects section
        self.create_projects_section(parent_layout)

        # Spacing above footer
        parent_layout.addSpacing(20)

        # Footer section with background color
        footer_widget = QWidget()
        footer_widget.setStyleSheet(f"background-color: {self.t('bg_footer')};")
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(15, 10, 15, 10)

        # Footer text (left side) with version
        version = self.get_version()
        footer_text = QLabel(f"ProjectFlow  •  Open source project launcher  •  {version}")
        footer_text.setStyleSheet(f"color: {self.t('fg_footer')}; font-size: 11px;")
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

        # Aliases button — shown when projectflow_aliases has entries
        _aliases_file = self.get_aliases_file_path()
        _has_aliases = os.path.exists(_aliases_file) and any(
            line.startswith('alias ') for line in open(_aliases_file, encoding='utf-8')
        )
        if _has_aliases:
            aliases_btn = QPushButton("⌨️ Aliases")
            aliases_btn.setMinimumHeight(30)
            aliases_btn.setStyleSheet(footer_btn_style)
            aliases_btn.setToolTip("Open Aliases project")
            aliases_btn.clicked.connect(self.open_aliases_project)
            footer_layout.addWidget(aliases_btn)

        # Help button — README + Launcher Examples (see _build_help_html). Lives here rather
        # than in the viewer tab row since it's app reference material, not a per-project
        # viewer, and was feeling out of place next to Web/PDF/Image/Terminal.
        help_btn = QPushButton("❓ Help")
        help_btn.setMinimumHeight(30)
        help_btn.setStyleSheet(footer_btn_style)
        help_btn.setToolTip("README and launcher examples")
        help_btn.clicked.connect(lambda: self.switch_to_viewer_mode("help"))
        footer_layout.addWidget(help_btn)

        # New Project button
        new_project_btn = QPushButton("📄 New Project")
        new_project_btn.setMinimumHeight(30)
        new_project_btn.setStyleSheet(footer_btn_style)
        new_project_btn.setToolTip("Create a new project from template")
        new_project_btn.clicked.connect(self.new_project)
        footer_layout.addWidget(new_project_btn)

        footer_layout.addSpacing(16)

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

        parent_layout.addWidget(footer_widget)

    def open_config_in_new_window(self, config_path):
        """Launch a new instance of ProjectFlow with the specified config"""
        script_path = os.path.join(self.script_dir, "projectflow.py")
        subprocess.Popen([script_path, config_path], start_new_session=True)

    def _can_open_in_new_desktop(self):
        """Return True if the current DE supports opening in a new virtual desktop."""
        if self.detect_desktop_environment() == 'kde':
            return shutil.which('qdbus') is not None
        return False

    def _get_browser_new_tab(self):
        """Return True to open browser links in new tab, False for new window.
        Per-config value takes precedence over global setting."""
        per_config = getattr(self, 'config_browser_new_tab', None)
        if per_config is not None:
            return per_config
        return self.settings.get('browser_new_tab', True)

    def open_config_in_new_desktop(self, config_path):
        """Launch a new ProjectFlow instance in a freshly created virtual desktop (KDE only)."""
        try:
            result = subprocess.run(
                ['qdbus', 'org.kde.KWin', '/VirtualDesktopManager',
                 'org.kde.KWin.VirtualDesktopManager.count'],
                capture_output=True, text=True, timeout=3
            )
            count = int(result.stdout.strip())
            project_name = os.path.splitext(os.path.basename(config_path))[0]

            subprocess.run(
                ['qdbus', 'org.kde.KWin', '/VirtualDesktopManager',
                 'org.kde.KWin.VirtualDesktopManager.createDesktop',
                 str(count), f'ProjectFlow: {project_name}'],
                timeout=3
            )
            subprocess.run(
                ['qdbus', 'org.kde.KWin', '/KWin',
                 'org.kde.KWin.setCurrentDesktop', str(count + 1)],
                timeout=3
            )

            script_path = os.path.join(self.script_dir, "projectflow.py")
            subprocess.Popen([script_path, config_path], start_new_session=True)

        except Exception as e:
            QMessageBox.warning(self, "New Desktop", f"Could not create virtual desktop:\n{str(e)}")

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

                # Not every project here is folder-based (e.g. "file quarterly VAT
                # return") — so unlike folder-based "Make Project" (which always has a
                # folder and opens Kickstart automatically), ask first rather than
                # assuming. Default No: most name-only projects created this way have
                # no folder to link.
                link_reply = QMessageBox.question(
                    self,
                    "Link a Folder?",
                    "Link a base folder to this project?\n\n"
                    "This lets Kickstart suggest documentation, dev shortcuts, and "
                    "package-manager commands detected in that folder.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if link_reply == QMessageBox.StandardButton.Yes:
                    chosen_folder = QFileDialog.getExistingDirectory(self, "Select Project Folder", os.path.expanduser("~"))
                    if chosen_folder:
                        self._show_kickstart_dialog(folder_path=chosen_folder)

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
        if not self._confirm_discard_code_changes():
            return

        # Update the current config file path
        self.current_config_file = config_path

        # Save as last used project
        self.settings["last_used_project"] = config_path

        # Add to recent projects
        self.add_to_recent_projects(config_path)

        # Clear folder navigation so the new project starts at its own default folder
        self.folder_current_path = None

        # Reset to the new project's own note — an arbitrary note explicitly loaded into
        # the Notes tab for the OLD project has no meaning here (see notes_md_path's
        # docstring in __init__ for why this reset lives here and not in load_notes()).
        self.notes_md_path = None

        # Force the Settings viewer (see _build_settings_form()) to repopulate from the
        # new project's own config next time it's shown, rather than keeping whatever the
        # OLD project's fields held — any unsaved edits in the old project's Settings form
        # are discarded here, same as they would be by navigating away in the old dialog
        # without clicking OK.
        self._settings_loaded_for = None

        # Reload with the new project
        self.refresh_projects()

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

        session = self._notes_muya_session
        if not session.webview:
            QMessageBox.warning(self, "Joplin Sync", "No notes editor available to sync.")
            return

        # Get config name for note title
        config_name = os.path.basename(self.current_config_file)
        config_name = os.path.splitext(config_name)[0]
        if config_name.endswith('_config'):
            config_name = config_name[:-7]
        title = f"ProjectFlow: {config_name.replace('_', ' ').title()}"

        def on_markdown(markdown_content):
            markdown_content = markdown_content or ""
            if not markdown_content.strip():
                QMessageBox.information(self, "Joplin Sync", "Notes are empty, nothing to sync.")
                return

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

        session.webview.page().runJavaScript("window.__getMuyaMarkdown ? window.__getMuyaMarkdown() : null", on_markdown)

    # ── Kimai integration ─────────────────────────────────────────────────────

    def _kimai_request(self, method, path, data=None, params=None):
        """Make a Kimai REST API request; return parsed JSON."""
        base_url = self.settings.get('kimai_url', '').rstrip('/')
        # Normalise: strip trailing /api if user accidentally included it
        if base_url.endswith('/api'):
            base_url = base_url[:-4]
        token = self.settings.get('kimai_token', '')
        url = base_url + path
        if params:
            url += '?' + urllib.parse.urlencode(params)
        body = json.dumps(data).encode('utf-8') if data is not None else None
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def _kimai_load_activities(self):
        """Fetch activities for the linked Kimai project and populate the combo box."""
        if not hasattr(self, '_time_activity_combo'):
            return
        project_id = getattr(self, 'config_kimai_project_id', None)
        if not project_id:
            return
        try:
            activities = self._kimai_request('GET', '/api/activities', params={'project': project_id, 'visible': 1})
            self._time_activity_combo.clear()
            self._time_activity_data = {}
            for act in activities:
                self._time_activity_combo.addItem(act.get('name', ''), act.get('id'))
                self._time_activity_data[act.get('id')] = act.get('name', '')
        except Exception as e:
            print(f"Kimai: could not load activities: {e}")

    def _kimai_load_entries(self, period=None):
        """Fetch recent time entries for the linked project and refresh the viewer."""
        if not hasattr(self, '_time_entries_table'):
            return
        project_id = getattr(self, 'config_kimai_project_id', None)

        # Show "no project" state
        if not project_id:
            if hasattr(self, '_kimai_no_project_widget'):
                self._kimai_no_project_widget.show()
            if hasattr(self, '_kimai_main_widget'):
                self._kimai_main_widget.hide()
            return

        if hasattr(self, '_kimai_no_project_widget'):
            self._kimai_no_project_widget.hide()
        if hasattr(self, '_kimai_main_widget'):
            self._kimai_main_widget.show()

        if period is not None:
            self._kimai_period = period

        # Compute date range
        now = datetime.datetime.now()
        period_days = {'week': 7, 'month': 30, '3m': 90, '6m': 180}.get(
            getattr(self, '_kimai_period', 'week'), 7
        )
        begin_dt = now - datetime.timedelta(days=period_days)
        begin_str = begin_dt.strftime('%Y-%m-%dT%H:%M:%S')
        end_str = now.strftime('%Y-%m-%dT%H:%M:%S')

        try:
            entries = self._kimai_request('GET', '/api/timesheets', params={
                'project': project_id,
                'begin': begin_str,
                'end': end_str,
                'size': 25,
                'page': 1,
            })
        except Exception as e:
            if hasattr(self, '_kimai_summary_label'):
                self._kimai_summary_label.setText(f"Error: {e}")
            return

        # Populate table
        table = self._time_entries_table
        table.setRowCount(0)
        total_seconds = 0
        for entry in entries:
            row = table.rowCount()
            table.insertRow(row)

            desc = entry.get('description') or ''
            begin_raw = entry.get('begin', '')
            duration_s = entry.get('duration') or 0
            total_seconds += duration_s

            # Parse begin datetime
            try:
                dt = datetime.datetime.fromisoformat(begin_raw)
                date_str = dt.strftime('%a %-d %b')
                time_str = dt.strftime('%H:%M')
            except Exception:
                date_str = begin_raw[:10] if begin_raw else ''
                time_str = ''

            dur_h = duration_s // 3600
            dur_m = (duration_s % 3600) // 60
            dur_str = f"{dur_h}h {dur_m:02d}m" if dur_h else f"{dur_m}m"

            activity_name = ''
            act = entry.get('activity')
            if isinstance(act, dict):
                activity_name = act.get('name', '')
            elif isinstance(act, int) and hasattr(self, '_time_activity_data'):
                activity_name = self._time_activity_data.get(act, '')

            row_bg = QColor(self.t('bg_primary') if row % 2 else self.t('bg_secondary'))
            desc_item = QTableWidgetItem(desc)
            desc_item.setToolTip(f"{activity_name}  |  {desc}" if activity_name else desc)
            desc_item.setBackground(row_bg)
            date_item = QTableWidgetItem(date_str)
            date_item.setBackground(row_bg)
            time_item = QTableWidgetItem(time_str)
            time_item.setBackground(row_bg)
            dur_item = QTableWidgetItem(dur_str)
            dur_item.setBackground(row_bg)
            table.setItem(row, 0, desc_item)
            table.setItem(row, 1, date_item)
            table.setItem(row, 2, time_item)
            table.setItem(row, 3, dur_item)

        # Summary label
        total_h = total_seconds // 3600
        total_m = (total_seconds % 3600) // 60
        period_label = {'week': 'week', 'month': 'month', '3m': '3 months', '6m': '6 months'}.get(
            getattr(self, '_kimai_period', 'week'), 'period'
        )
        n = len(entries)
        if hasattr(self, '_kimai_summary_label'):
            self._kimai_summary_label.setText(
                f"Total: {total_h}h {total_m:02d}m  ·  {n} entr{'y' if n == 1 else 'ies'} this {period_label}"
            )

        # Total row at bottom of table
        if n > 0:
            total_str = f"{total_h}h {total_m:02d}m"
            total_row = table.rowCount()
            table.insertRow(total_row)
            total_bg = QColor(self.t('bg_panel'))
            total_fg = QColor(self.t('fg_on_dark'))
            for col, text in enumerate(["Total", "", "", total_str]):
                item = QTableWidgetItem(text)
                item.setBackground(total_bg)
                item.setForeground(total_fg)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                table.setItem(total_row, col, item)

        # Hide the total bar (no longer used)
        if hasattr(self, '_kimai_total_bar'):
            self._kimai_total_bar.setVisible(False)

        # Load activities into combo box if not yet done
        if hasattr(self, '_time_activity_combo') and self._time_activity_combo.count() == 0:
            self._kimai_load_activities()

        # Refresh pending CSV imports
        self._kimai_refresh_csv_section()

    def _kimai_submit_entry(self):
        """Read the log-time form and POST a new timesheet entry to Kimai."""
        if not hasattr(self, '_time_description'):
            return
        project_id = getattr(self, 'config_kimai_project_id', None)
        if not project_id:
            return

        desc = self._time_description.text().strip()
        if not desc:
            self._kimai_status_label.setText("Description is required.")
            return

        activity_id = self._time_activity_combo.currentData()
        if not activity_id:
            self._kimai_status_label.setText("Please select an activity.")
            return

        date_val = self._time_date.date()
        from_time = self._time_from.time()
        to_time = self._time_to.time()

        begin_dt = datetime.datetime(
            date_val.year(), date_val.month(), date_val.day(),
            from_time.hour(), from_time.minute()
        )
        end_dt = datetime.datetime(
            date_val.year(), date_val.month(), date_val.day(),
            to_time.hour(), to_time.minute()
        )

        if end_dt <= begin_dt:
            self._kimai_status_label.setText("End time must be after start time.")
            return

        payload = {
            'begin': begin_dt.strftime('%Y-%m-%dT%H:%M:%S'),
            'end': end_dt.strftime('%Y-%m-%dT%H:%M:%S'),
            'project': project_id,
            'activity': activity_id,
            'description': desc,
        }

        try:
            self._kimai_request('POST', '/api/timesheets', data=payload)
            self._time_description.clear()
            self._kimai_status_label.setText("Entry logged.")
            self._kimai_load_entries()
        except Exception as e:
            self._kimai_status_label.setText(f"Error: {e}")

    def _kimai_pick_project_into(self, target_field):
        """Fetch Kimai projects and show a picker dialog; write selected ID into target_field."""
        try:
            projects = self._kimai_request('GET', '/api/projects')
        except Exception as e:
            base = self.settings.get('kimai_url', '').rstrip('/')
            if base.endswith('/api'):
                base = base[:-4]
            QMessageBox.warning(self, "Kimai", f"Could not fetch projects:\n{e}\n\nURL tried: {base}/api/projects")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Select Kimai Project")
        dlg.resize(400, 350)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        list_widget = QListWidget()
        list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
            }}
        """)
        project_map = {}
        for p in projects:
            pid = p.get('id')
            name = p.get('name', '')
            customer = p.get('customer', {})
            customer_name = customer.get('name', '') if isinstance(customer, dict) else ''
            display = f"{name}  ({customer_name})" if customer_name else name
            list_widget.addItem(display)
            project_map[list_widget.count() - 1] = (pid, name)

        layout.addWidget(list_widget)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Select")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        list_widget.itemDoubleClicked.connect(lambda _: dlg.accept())

        if dlg.exec() == QDialog.DialogCode.Accepted:
            row = list_widget.currentRow()
            if row >= 0:
                pid, pname = project_map[row]
                target_field.setText(str(pid))
                return pname
        return None

    def _kimai_link_project_dialog(self):
        """Show the Kimai project picker and save the selection to the current project config."""
        tmp_field = QLineEdit()
        current_id = getattr(self, 'config_kimai_project_id', None)
        tmp_field.setText(str(current_id) if current_id else "")
        pname = self._kimai_pick_project_into(tmp_field)
        new_id_text = tmp_field.text().strip()
        if new_id_text.isdigit():
            self.config_kimai_project_id = int(new_id_text)
            self.config_kimai_project_name = pname
            self._save_project_config()
            self._kimai_load_entries()

    def _build_time_viewer(self):
        """Build the Kimai time tracking viewer panel."""
        self.time_container = QWidget()
        outer = QVBoxLayout(self.time_container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 4px 10px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QPushButton:checked {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
                border-color: {self.t('bg_category')};
            }}
        """
        input_style = f"""
            QLineEdit, QComboBox, QDateEdit, QTimeEdit {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 4px 6px;
                font-size: 12px;
            }}
        """

        # ── "No project linked" state ─────────────────────────────────────
        self._kimai_no_project_widget = QWidget()
        no_proj_layout = QVBoxLayout(self._kimai_no_project_widget)
        no_proj_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_proj_lbl = QLabel("This project isn't linked to Kimai yet.")
        no_proj_lbl.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 13px;")
        no_proj_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link_btn = QPushButton("Link Kimai Project…")
        link_btn.setStyleSheet(btn_style)
        link_btn.setFixedWidth(180)
        link_btn.clicked.connect(self._kimai_link_project_dialog)
        no_proj_layout.addStretch()
        no_proj_layout.addWidget(no_proj_lbl)
        no_proj_layout.addSpacing(12)
        no_proj_layout.addWidget(link_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        no_proj_layout.addStretch()
        outer.addWidget(self._kimai_no_project_widget)

        # ── Main content (shown when project is linked) ───────────────────
        self._kimai_main_widget = QWidget()
        main_layout = QVBoxLayout(self._kimai_main_widget)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)

        # Period toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        self._kimai_period = 'week'
        period_labels = [('week', 'Week'), ('month', 'Month'), ('3m', '3M'), ('6m', '6M')]
        self._kimai_period_btns = {}
        for key, label in period_labels:
            pbtn = QPushButton(label)
            pbtn.setCheckable(True)
            pbtn.setChecked(key == 'week')
            pbtn.setStyleSheet(btn_style)
            pbtn.setFixedWidth(48)
            pbtn.clicked.connect(lambda checked=False, k=key: self._kimai_set_period(k))
            toolbar.addWidget(pbtn)
            self._kimai_period_btns[key] = pbtn
        toolbar.addStretch()
        refresh_btn = QPushButton("↻")
        refresh_btn.setStyleSheet(btn_style)
        refresh_btn.setFixedWidth(28)
        refresh_btn.setToolTip("Refresh entries")
        refresh_btn.clicked.connect(lambda: self._kimai_load_entries())
        link_proj_btn = QPushButton("⇄")
        link_proj_btn.setStyleSheet(btn_style)
        link_proj_btn.setFixedWidth(28)
        link_proj_btn.setToolTip("Change linked Kimai project")
        link_proj_btn.clicked.connect(self._kimai_link_project_dialog)
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(link_proj_btn)
        main_layout.addLayout(toolbar)

        # Summary label
        self._kimai_summary_label = QLabel("Loading…")
        self._kimai_summary_label.setStyleSheet(
            f"color: {self.t('fg_secondary')}; font-size: 12px; padding: 2px 0;"
        )
        main_layout.addWidget(self._kimai_summary_label)

        # Entries table
        self._time_entries_table = QTableWidget(0, 4)
        self._time_entries_table.setHorizontalHeaderLabels(["Description", "Date", "Time", "Duration"])
        self._time_entries_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._time_entries_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._time_entries_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._time_entries_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._time_entries_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._time_entries_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._time_entries_table.setAlternatingRowColors(False)
        self._time_entries_table.verticalHeader().setVisible(False)
        self._time_entries_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                font-size: 12px;
                gridline-color: {self.t('border')};
            }}
            QHeaderView::section {{
                background-color: {self.t('bg_panel')};
                color: {self.t('fg_on_dark')};
                padding: 4px;
                border: none;
                border-bottom: 1px solid {self.t('border')};
                font-size: 11px;
            }}
        """)
        main_layout.addWidget(self._time_entries_table, 1)

        # Total bar (replaces total table row — separate widget avoids QSS override)
        self._kimai_total_bar = QLabel("")
        self._kimai_total_bar.setVisible(False)
        self._kimai_total_bar.setStyleSheet(
            f"background-color: {self.t('bg_category')}; color: {self.t('fg_on_dark')};"
            f" font-weight: bold; font-size: 12px; padding: 3px 6px;"
        )
        main_layout.addWidget(self._kimai_total_bar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {self.t('border')};")
        main_layout.addWidget(sep)

        # Log time form
        form_title = QLabel("Log Time")
        form_title.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 11px; font-weight: bold;")
        main_layout.addWidget(form_title)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self._time_description = QLineEdit()
        self._time_description.setPlaceholderText("Description…")
        self._time_description.setStyleSheet(input_style)
        self._time_activity_combo = QComboBox()
        self._time_activity_combo.setStyleSheet(input_style)
        self._time_activity_combo.setFixedWidth(130)
        row1.addWidget(self._time_description, 1)
        row1.addWidget(self._time_activity_combo)
        main_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self._time_date = QDateEdit()
        self._time_date.setCalendarPopup(True)
        self._time_date.setDate(QDate.currentDate())
        self._time_date.setStyleSheet(input_style)
        self._time_date.setFixedWidth(110)
        self._time_from = QTimeEdit()
        self._time_from.setTime(QTime(9, 0))
        self._time_from.setStyleSheet(input_style)
        self._time_from.setFixedWidth(75)
        self._time_to = QTimeEdit()
        self._time_to.setTime(QTime(10, 0))
        self._time_to.setStyleSheet(input_style)
        self._time_to.setFixedWidth(75)
        log_btn = QPushButton("Log Time")
        log_btn.setStyleSheet(btn_style)
        log_btn.clicked.connect(self._kimai_submit_entry)
        row2.addWidget(self._time_date)
        row2.addWidget(self._time_from)
        row2.addWidget(QLabel("→"))
        row2.addWidget(self._time_to)
        row2.addStretch()
        row2.addWidget(log_btn)
        main_layout.addLayout(row2)

        self._kimai_status_label = QLabel("")
        self._kimai_status_label.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 11px;")
        main_layout.addWidget(self._kimai_status_label)

        # CSV import section (shown below Log Time when pending files exist)
        csv_sep = QFrame()
        csv_sep.setFrameShape(QFrame.Shape.HLine)
        csv_sep.setStyleSheet(f"color: {self.t('border')};")
        main_layout.addWidget(csv_sep)

        self._kimai_csv_title = QLabel("Pending Imports")
        self._kimai_csv_title.setStyleSheet(
            f"color: {self.t('fg_secondary')}; font-size: 11px; font-weight: bold;"
        )
        self._kimai_csv_title.hide()
        main_layout.addWidget(self._kimai_csv_title)

        self._kimai_csv_container = QWidget()
        self._kimai_csv_container_layout = QVBoxLayout(self._kimai_csv_container)
        self._kimai_csv_container_layout.setContentsMargins(0, 0, 0, 0)
        self._kimai_csv_container_layout.setSpacing(4)
        main_layout.addWidget(self._kimai_csv_container)

        outer.addWidget(self._kimai_main_widget)

        # Initial visibility
        has_project = bool(getattr(self, 'config_kimai_project_id', None))
        self._kimai_no_project_widget.setVisible(not has_project)
        self._kimai_main_widget.setVisible(has_project)

    @staticmethod
    def _parse_csv_duration(value):
        """Parse a CSV Duration field to seconds. Handles int seconds or 'H:MM' / 'H:MM:SS' strings."""
        s = str(value or '0').strip()
        if ':' in s:
            parts = s.split(':')
            try:
                h, m = int(parts[0]), int(parts[1])
                sec = int(parts[2]) if len(parts) > 2 else 0
                return h * 3600 + m * 60 + sec
            except (ValueError, IndexError):
                return 0
        try:
            return int(s)
        except ValueError:
            return 0

    def _kimai_scan_csv_imports(self):
        """Scan the CSV folder for files with rows matching the current project name."""
        csv_folder = os.path.expanduser(self.settings.get('kimai_csv_folder', ''))
        project_name = getattr(self, 'config_kimai_project_name', None)
        if not csv_folder or not project_name or not os.path.isdir(csv_folder):
            return []
        results = []
        for fname in sorted(os.listdir(csv_folder)):
            if not fname.lower().endswith('.csv'):
                continue
            fpath = os.path.join(csv_folder, fname)
            try:
                with open(fpath, newline='', encoding='utf-8') as f:
                    pname_lower = project_name.strip().lower()
                    rows = [r for r in _csv.DictReader(f)
                            if r.get('Project', '').strip().lower() == pname_lower]
                if rows:
                    results.append((fpath, fname, rows))
            except Exception as e:
                print(f"Kimai CSV scan: could not read {fname}: {e}")
        return results

    def _kimai_refresh_csv_section(self):
        """Rebuild the pending CSV import section in the time viewer."""
        if not hasattr(self, '_kimai_csv_container'):
            return

        # Clear existing widgets
        while self._kimai_csv_container_layout.count():
            item = self._kimai_csv_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        pending = self._kimai_scan_csv_imports()
        self._kimai_csv_title.setVisible(bool(pending))

        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
            }}
        """

        for fpath, fname, rows in pending:
            card = QWidget()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(0, 2, 0, 4)
            card_layout.setSpacing(2)

            # Header row: filename + total + Import button
            total_s = sum(self._parse_csv_duration(r.get('Duration', 0)) for r in rows)
            total_h, total_m = total_s // 3600, (total_s % 3600) // 60
            dur_str = f"{total_h}h {total_m:02d}m" if total_h else f"{total_m}m"
            n = len(rows)

            header = QHBoxLayout()
            file_lbl = QLabel(f"{fname}  ·  {n} entr{'y' if n == 1 else 'ies'}, {dur_str}")
            file_lbl.setStyleSheet(f"color: {self.t('fg_primary')}; font-size: 11px;")
            import_btn = QPushButton("Import")
            import_btn.setStyleSheet(btn_style)
            import_btn.setFixedWidth(60)
            import_btn.clicked.connect(lambda checked=False, p=fpath, r=rows: self._kimai_import_csv_file(p, r))
            header.addWidget(file_lbl, 1)
            header.addWidget(import_btn)
            card_layout.addLayout(header)

            # Entry rows
            for row in rows:
                date = row.get('Date', '')
                from_t = row.get('From', '')[:5]
                to_t = row.get('To', '')[:5]
                desc = row.get('Description', '')
                act = row.get('Activity', '')
                row_lbl = QLabel(f"  {date}  {from_t}→{to_t}  {act}  —  {desc}")
                row_lbl.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 11px;")
                row_lbl.setWordWrap(True)
                card_layout.addWidget(row_lbl)

            self._kimai_csv_container_layout.addWidget(card)

    def _kimai_import_csv_file(self, fpath, rows):
        """POST all rows from a CSV file to Kimai and archive the file on success."""
        project_id = getattr(self, 'config_kimai_project_id', None)
        if not project_id:
            return

        # Build activity name→id lookup
        act_by_name = {}
        if hasattr(self, '_time_activity_data'):
            act_by_name = {v.lower(): k for k, v in self._time_activity_data.items()}

        errors = []
        for row in rows:
            try:
                date = row.get('Date', '')
                from_t = row.get('From', '')
                to_t = row.get('To', '')
                act_name = row.get('Activity', '').strip()
                desc = row.get('Description', '')

                begin_str = f"{date}T{from_t}" if from_t else ''
                end_str = f"{date}T{to_t}" if to_t else ''

                activity_id = act_by_name.get(act_name.lower())
                if not activity_id and self._time_activity_data:
                    activity_id = next(iter(self._time_activity_data.keys()))

                payload = {
                    'begin': begin_str,
                    'end': end_str,
                    'project': project_id,
                    'description': desc,
                }
                if activity_id:
                    payload['activity'] = activity_id

                self._kimai_request('POST', '/api/timesheets', data=payload)
            except Exception as e:
                errors.append(str(e))

        if errors:
            self._kimai_status_label.setText(f"Import errors: {'; '.join(errors[:2])}")
            return

        # Archive the file
        csv_folder = os.path.expanduser(self.settings.get('kimai_csv_folder', ''))
        archive_dir = os.path.join(csv_folder, '.archive')
        os.makedirs(archive_dir, exist_ok=True)
        dest = os.path.join(archive_dir, os.path.basename(fpath))
        try:
            os.rename(fpath, dest)
        except Exception as e:
            self._kimai_status_label.setText(f"Imported, but couldn't archive: {e}")
            return

        self._kimai_status_label.setText(f"Imported and archived {os.path.basename(fpath)}.")
        self._kimai_load_entries()

    def _kimai_set_period(self, period):
        """Switch time period and update button states."""
        self._kimai_period = period
        for key, btn in self._kimai_period_btns.items():
            btn.setChecked(key == period)
        self._kimai_load_entries()

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

    def quick_add_launcher(self):
        """Open the add-item dialog targeting the first category"""
        first_category = None
        for cat_dict in self.COLUMN_1:
            if cat_dict:
                first_category = list(cat_dict.keys())[0]
                break
        if not first_category:
            QMessageBox.information(self, "Quick Add", "No categories found. Add a category first via Edit mode.")
            return
        self._show_item_edit_dialog(0, first_category, None)

    def toggle_edit_mode(self):
        """Toggle edit mode. Turning it ON also opens the Settings viewer directly (see
        switch_to_viewer_mode()) — editing launchers and editing project settings are one
        continuous edit session now, with a single entry point (there's no more separate
        "Project Details" button). Turning it OFF (the "💾 Save" button — the ONLY Save
        button; the Settings viewer used to have its own too, but that duplicated this one
        and was removed) commits the Settings viewer's pending fields — see
        _save_project_and_exit_edit_mode()."""
        if self.edit_mode:
            self._save_project_and_exit_edit_mode()
        else:
            self.edit_mode = True
            # Rebuild first so the edit-mode launcher controls and settings_container
            # actually exist before switch_to_viewer_mode() tries to show the latter.
            self.refresh_projects()
            self.switch_to_viewer_mode("settings")

    def _settings_shortcut_clicked(self):
        """Click handler for the viewer tab row's Settings cog icon — effectively a second
        "Edit Project" entry point, but NOT a plain call to toggle_edit_mode(): that method
        toggles, so calling it unconditionally would exit (and save) an edit session already
        in progress instead of just jumping back to the Settings viewer, which is this
        button's other job (recovering from having clicked over to another viewer tab
        mid-edit). Checking edit_mode first makes both jobs work correctly: enters edit mode
        when not already editing, or just switches viewers when already editing."""
        if self.edit_mode:
            self.switch_to_viewer_mode("settings")
        else:
            self.toggle_edit_mode()

    def _save_project_and_exit_edit_mode(self):
        """Save action for the title-bar Edit Project/Save toggle (the only Save button —
        see toggle_edit_mode()). Combines committing the Settings form's pending fields
        with exiting edit mode, since editing launchers and editing project settings are
        now one continuous edit session reached through a single entry point."""
        self.edit_mode = False
        self._apply_settings(None, save_project_settings=True)
        if hasattr(self, 'status_label'):
            self.status_label.setText("✓ Project settings saved")

    def _on_global_ctrl_s(self):
        """Global Ctrl+S handler. Historically bound directly to toggle_edit_mode — now
        saves the code editor first when it's the active viewer, since Ctrl+S reads as
        "save" there far more than as "toggle launcher edit mode". Falls through to the
        original behavior otherwise, unchanged."""
        if self.column2_mode == "code" and self._code_session.editing:
            self._code_editor_save(self._code_session)
            return
        self.toggle_edit_mode()

    def _toggle_group_by_type(self):
        """Toggle the dynamic Group-by-Type launcher view (display-only, see _build_grouped_categories)."""
        self.group_by_type = not self.group_by_type
        self._save_group_by_type_to_config()
        self.refresh_projects()

    def _switch_launcher_tab(self, tab_name):
        """Switch the Focus-layout launcher column's active tab (Files/Docs/Resources/Apps).
        Display-only, like _toggle_group_by_type — never rewrites the project's category
        structure, just which pooled/panel view build_main_content renders for column 0."""
        if tab_name == self.active_launcher_tab:
            return
        self.active_launcher_tab = tab_name
        self._save_active_launcher_tab_to_config()
        self.refresh_projects()

    def _filter_launchers(self, query):
        """Show/hide launcher items and categories based on search text."""
        q = query.strip().lower()
        for ref in getattr(self, '_launcher_search_refs', []):
            any_visible = False
            for item in ref['items']:
                match = (not q
                         or q in item['display_name'].lower()
                         or q in item['path'].lower()
                         or q in item['app'].lower())
                item['widget'].setVisible(match)
                if match:
                    any_visible = True
            ref['container'].setVisible(not q or any_visible)

    def _wire_launcher_context_menu(self, btn, col_idx, category_name, item_idx):
        """Attach a right-click Edit/Delete menu to a launcher button."""
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, b=btn, ci=col_idx, cn=category_name, ii=item_idx:
                self._show_launcher_context_menu(b, ci, cn, ii)
        )

    def _show_launcher_context_menu(self, btn, col_idx, category_name, item_idx):
        """Show right-click Edit/Delete menu for a launcher."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                padding: 4px;
            }}
            QMenu::item {{ padding: 6px 20px; }}
            QMenu::item:selected {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
            }}
        """)
        edit_action = menu.addAction("✏️  Edit")
        delete_action = menu.addAction("🗑  Delete")

        # "Move to category" physically relocates the item into any real category. A fixed
        # "Documentation (docs)" entry is always offered first regardless of whether that
        # category exists yet — moving into it is how a real item gets promoted to show
        # under the Docs tab — auto-creating it on first use via
        # _ensure_documentation_category(). Real category names come after, deduped against
        # both aliases so the two never show twice once it exists.
        move_actions = {}
        if self._is_grouped_view_active():
            # Blue folder icon, not the 📁 emoji — renders yellow/manila in most color-emoji
            # fonts; never use a yellow folder glyph for folders/files in this project.
            move_menu = menu.addMenu(self._blue_folder_icon(), "Move to category")
            if category_name not in ("Documentation", "Docs"):
                move_actions[move_menu.addAction("📄  Documentation (docs)")] = "__DOCS__"
            real_category_names = [list(cd.keys())[0] for cd in self.COLUMN_1 if cd]
            for real_name in real_category_names:
                if real_name in (category_name, "Documentation", "Docs"):
                    continue  # already there, or already offered as the fixed entry above
                move_actions[move_menu.addAction(real_name)] = real_name

        action = menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        if action == edit_action:
            self._open_item_edit_dialog(col_idx, category_name, item_idx)
        elif action == delete_action:
            self.delete_item(col_idx, category_name, item_idx)
        elif action in move_actions:
            target_category = move_actions[action]
            if target_category == "__DOCS__":
                target_category = self._ensure_documentation_category()
            dest_items = next((cd[target_category] for cd in self.COLUMN_1 if target_category in cd), [])
            self.handle_item_move_to_category(category_name, item_idx, target_category, len(dest_items))

    def _show_category_context_menu(self, btn, col_idx, category_name):
        """Show right-click Rename/Delete menu for a category header."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                padding: 4px;
            }}
            QMenu::item {{ padding: 6px 20px; }}
            QMenu::item:selected {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
            }}
        """)
        rename_action = menu.addAction("✏️  Rename")
        delete_action = menu.addAction("🗑  Delete")

        action = menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        if action == rename_action:
            from PyQt6.QtWidgets import QInputDialog
            new_name, ok = QInputDialog.getText(
                self, "Rename Category", "New name:", text=category_name
            )
            if ok and new_name.strip() and new_name.strip() != category_name:
                for cat_dict in self.COLUMN_1:
                    if category_name in cat_dict:
                        cat_dict[new_name.strip()] = cat_dict.pop(category_name)
                        break
                self.save_config_to_json()
                self.refresh_projects()
        elif action == delete_action:
            self.delete_category(col_idx, category_name)

    def create_edit_item_widget(self, col_idx, category_name, item_idx, name, path, app):
        """Create a compact edit row: drag handle | launcher button | ✏️ | 🗑"""
        item_widget = QWidget()
        row = QHBoxLayout(item_widget)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(4)

        # Drag handle
        handle = DragHandle(col_idx, category_name, item_idx)
        handle.setStyleSheet(f"color: {self.t('fg_secondary')}; font-size: 14px;")
        row.addWidget(handle)

        # Launcher button — same icon/style as view mode, still clickable
        app_icon = ""
        svg_icon_path = None
        if self._icon_key_for_app(app, path) in self.APP_INFO:
            icon_val = self.APP_INFO[self._icon_key_for_app(app, path)]["icon"]
            if icon_val.endswith(('.svg', '.png', '.jpg')):
                candidate = os.path.join(self.script_dir, icon_val)
                if os.path.isfile(candidate):
                    svg_icon_path = candidate
            else:
                app_icon = icon_val + " "

        btn = DraggableItemButton(f"{app_icon}{name}", col_idx, category_name, item_idx)
        btn.setMinimumHeight(30)
        btn.setStyleSheet(self.get_item_button_style())
        if svg_icon_path:
            btn.setIcon(QIcon(svg_icon_path))
            btn.setIconSize(QSize(16, 16))
        btn.clicked.connect(lambda checked=False, p=path, a=app, b=btn: self.on_item_clicked(b, p, a))
        btn.setToolTip(f"[{app}] {path}")
        self._wire_launcher_context_menu(btn, col_idx, category_name, item_idx)
        row.addWidget(btn, 1)

        ctrl_style = f"""
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

        edit_btn = QPushButton("✏️")
        edit_btn.setFixedSize(30, 28)
        edit_btn.setToolTip("Edit launcher")
        edit_btn.setStyleSheet(ctrl_style)
        edit_btn.clicked.connect(
            lambda checked=False, ci=col_idx, cn=category_name, ii=item_idx:
                self._open_item_edit_dialog(ci, cn, ii)
        )
        row.addWidget(edit_btn)

        del_btn = QPushButton("🗑")
        del_btn.setFixedSize(30, 28)
        del_btn.setToolTip("Delete launcher")
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
            lambda checked=False, ci=col_idx, cn=category_name, ii=item_idx:
                self.delete_item(ci, cn, ii)
        )
        row.addWidget(del_btn)

        return item_widget

    def _open_item_edit_dialog(self, col_idx, category_name, item_idx):
        """Look up current item data from COLUMN_1 and open the edit dialog."""
        for cat_dict in self.COLUMN_1:
            if category_name in cat_dict:
                items = cat_dict[category_name]
                if item_idx < len(items):
                    item = items[item_idx]
                    item_data = {
                        "name": item[0] if len(item) > 0 else "",
                        "path": item[1] if len(item) > 1 else "",
                        "app": item[2] if len(item) > 2 else "",
                        "index": item_idx,
                    }
                    self._show_item_edit_dialog(col_idx, category_name, item_data, tree=None, inline_widget=None)
                break

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
            QMessageBox.warning(
                self,
                "Save Error",
                f"Could not save config:\n{self.current_config_file}\n\n{e}"
            )

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
        open_btn = QPushButton(" Open")
        open_btn.setIcon(self._open_icon())
        open_btn.setIconSize(QSize(16, 16))
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

        # Fit-mode toggle button — cycles Fit Width -> Fit Height -> Fit Page (whole
        # page, i.e. autofit both dimensions) -> back to Fit Width. See
        # pdf_toggle_fit_mode()/pdf_apply_fit().
        self.pdf_fit_btn = QPushButton()
        self.pdf_fit_btn.setStyleSheet(btn_style)
        self.pdf_fit_btn.clicked.connect(self.pdf_toggle_fit_mode)
        toolbar_layout.addWidget(self.pdf_fit_btn)
        self._update_pdf_fit_btn()

        # Add stretch to push buttons to the left
        toolbar_layout.addStretch()

        parent_layout.addWidget(toolbar_widget)

    def _build_pdf_footer_page_nav(self):
        """Small prev/page/next controls duplicating the toolbar's paging buttons,
        placed in the footer row (left-aligned, opposite the "Open in {viewer}" button)
        so paging is reachable without scrolling back up to the toolbar on a tall PDF.
        self.pdf_page_label_bottom is kept in sync with self.pdf_page_label wherever the
        latter is updated (render_pdf_page(), the tab-close-to-empty reset)."""
        nav = QWidget()
        layout = QHBoxLayout(nav)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        btn_style = f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """

        prev_btn = QPushButton("<")
        prev_btn.setStyleSheet(btn_style)
        prev_btn.setToolTip("Previous page")
        prev_btn.clicked.connect(self.pdf_prev_page)
        layout.addWidget(prev_btn)

        self.pdf_page_label_bottom = QLabel("0 / 0")
        self.pdf_page_label_bottom.setStyleSheet("margin: 0 8px; font-size: 11px;")
        layout.addWidget(self.pdf_page_label_bottom)

        next_btn = QPushButton(">")
        next_btn.setStyleSheet(btn_style)
        next_btn.setToolTip("Next page")
        next_btn.clicked.connect(self.pdf_next_page)
        layout.addWidget(next_btn)

        return nav

    def _pdf_load_tab_doc(self, tab):
        """Open the PyMuPDF document for `tab` (local file or URL), storing the result on
        the tab object itself. Split out from _open_pdf_tab() so build_main_content()'s
        startup restore (opening every remembered tab) can reuse it without re-appending
        to self.pdf_tabs. Returns True on success, False if the file/URL couldn't load."""
        try:
            if tab.path.startswith(('http://', 'https://')):
                req = urllib.request.Request(tab.path, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    pdf_data = response.read()
                tab.doc = fitz.open(stream=pdf_data, filetype="pdf")
            else:
                expanded_path = os.path.expanduser(tab.path)
                if not os.path.exists(expanded_path):
                    return False
                tab.doc = fitz.open(expanded_path)
            tab.page_count = len(tab.doc)
            if tab.page >= tab.page_count:
                tab.page = 0
            return True
        except Exception as e:
            print(f"Error loading PDF: {e}")
            return False

    def _open_pdf_tab(self, path, page=0):
        """Open `path` as a brand-new PDF tab and make it active. Always-new-tab policy —
        every "open a PDF" action (launcher click, Open button, URL dialog) adds a tab
        rather than replacing whatever's already open, per the multi-instance-tabs plan.
        Returns True on success, False if the file/URL couldn't load (mirrors the old
        load_pdf()'s return contract — callers check this for status-label feedback)."""
        tab = PdfTabState(path, page)
        if not self._pdf_load_tab_doc(tab):
            return False
        self.pdf_tabs.append(tab)
        self._activate_pdf_tab(len(self.pdf_tabs) - 1)
        self.save_notes()  # Persist the new tab list
        return True

    def _activate_pdf_tab(self, index):
        """Make self.pdf_tabs[index] the active tab: flush the previously-active tab's page
        position back into its own record, sync the active-tab proxy scalars (pdf_doc/
        pdf_path/pdf_current_page/pdf_page_count — read by every existing render/zoom/nav
        function, all unchanged), render, fit to width, and refresh the tab strip."""
        if 0 <= self.pdf_active_index < len(self.pdf_tabs):
            self.pdf_tabs[self.pdf_active_index].page = self.pdf_current_page
        self.pdf_active_index = index
        tab = self.pdf_tabs[index]
        self.pdf_doc = tab.doc
        self.pdf_path = tab.path
        self.pdf_current_page = tab.page
        self.pdf_page_count = tab.page_count
        if tab.doc is not None:
            self.render_pdf_page()
            QTimer.singleShot(0, self.pdf_apply_fit)
        elif self.pdf_label is not None:
            self._set_viewer_placeholder(self.pdf_label, "pdf", f"Could not load:\n{tab.path}")
        self._rebuild_pdf_tab_strip()

    def _close_pdf_tab(self, index):
        """Close and discard the PDF tab at `index`, picking a sensible new active tab (the
        one now at the same index, or the last remaining tab, or none if the list becomes
        empty) and persisting the change."""
        if not (0 <= index < len(self.pdf_tabs)):
            return
        closing_active = (index == self.pdf_active_index)
        tab = self.pdf_tabs.pop(index)
        if tab.doc is not None:
            try:
                tab.doc.close()
            except Exception:
                pass
        if not self.pdf_tabs:
            self.pdf_active_index = -1
            self.pdf_doc = None
            self.pdf_path = None
            self.pdf_current_page = 0
            self.pdf_page_count = 0
            if self.pdf_label is not None:
                self._set_viewer_placeholder(self.pdf_label, "pdf", "No PDF loaded\n\nUse the Open button to open a PDF file")
            self._set_pdf_page_label_text("0 / 0")
            self._rebuild_pdf_tab_strip()
        elif closing_active:
            self._activate_pdf_tab(min(index, len(self.pdf_tabs) - 1))
        else:
            if index < self.pdf_active_index:
                self.pdf_active_index -= 1
            self._rebuild_pdf_tab_strip()
        self.save_notes()

    def _close_all_pdf_tabs(self):
        """Close every open PDF tab. _close_pdf_tab() never refuses to close (no confirmation
        dialog — PDFs are read-only), so this always terminates with zero tabs."""
        while self.pdf_tabs:
            self._close_pdf_tab(0)

    def _build_pdf_tab_strip(self, parent_layout):
        """Build the row of PDF tab buttons (one per open PdfTabState, with a close button
        each) — sits between the toolbar and the PDF scroll area. Rebuilt fresh on every
        build_main_content() call like the rest of pdf_container; _rebuild_pdf_tab_strip()
        clears and repopulates the same layout reference afterward for in-place updates
        (opening/closing/switching a tab) without a full UI rebuild."""
        self.pdf_tab_strip_widget = QWidget()
        self.pdf_tab_strip_layout = QHBoxLayout(self.pdf_tab_strip_widget)
        self.pdf_tab_strip_layout.setContentsMargins(0, 0, 0, 4)
        self.pdf_tab_strip_layout.setSpacing(2)
        parent_layout.addWidget(self.pdf_tab_strip_widget)
        self._rebuild_pdf_tab_strip()

    def _viewer_tab_button_style(self, active):
        """Shared style for both the label and close button of one multi-instance tab
        (PDF, Image, and future Web/Notes/Editor tabs) — active tab gets the same
        brighter-fill = selected convention as the main viewer tab row."""
        if active:
            return f"""
                QPushButton {{
                    background-color: {self.t('bg_green_3')};
                    color: {self.t('fg_on_dark')};
                    border: none;
                    padding: 3px 6px;
                    font-size: 11px;
                }}
            """
        return f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                padding: 3px 6px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """

    def _build_tab_group_widget(self, label_text, tooltip, style, on_activate, on_close):
        """One tab's label+close-button pair, grouped with zero internal spacing (no gap
        between a tab's label and its own × — browser-tab convention) so the strip's own
        spacing reads as the gap BETWEEN tabs, not within one. Shared by all three
        multi-instance tab strips (PDF/Image/Web)."""
        group = QWidget()
        group_layout = QHBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(0)

        label_btn = QPushButton(label_text)
        label_btn.setToolTip(tooltip)
        label_btn.setMaximumWidth(140)
        label_btn.setStyleSheet(style)
        label_btn.clicked.connect(on_activate)
        group_layout.addWidget(label_btn)

        close_btn = QPushButton("×")
        close_btn.setFixedWidth(18)
        close_btn.setStyleSheet(style)
        close_btn.setToolTip("Close tab")
        close_btn.clicked.connect(on_close)
        group_layout.addWidget(close_btn)

        return group

    def _build_close_all_tabs_button(self, on_click):
        """"Close All" button for the right-hand end of a multi-instance tab strip (PDF/
        Image/Web/Notes/Editor) — filled with the tab row's own darkest green (bg_green_1,
        the resting-tab color) rather than the plain bg_button the individual tabs use when
        inactive, so it reads as visually distinct without introducing an unrelated accent
        color. Callers only add this when more than one tab is open — with exactly one,
        "close all" is the same as that tab's own ×."""
        btn = QPushButton("X Close All")
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.t('bg_green_1')};
                color: {self.t('fg_on_dark')};
                border: 1px solid {self.t('border')};
                padding: 3px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_green_2')};
                color: {self.t('fg_on_dark')};
            }}
        """)
        btn.setToolTip("Close all open tabs")
        btn.clicked.connect(on_click)
        return btn

    def _rebuild_pdf_tab_strip(self):
        """Clear and repopulate self.pdf_tab_strip_layout from self.pdf_tabs — called after
        every open/close/activate so the strip stays in sync without a full rebuild. A
        no-op if the strip hasn't been built yet this pass (guards startup ordering)."""
        if getattr(self, 'pdf_tab_strip_layout', None) is None:
            return
        while self.pdf_tab_strip_layout.count():
            item = self.pdf_tab_strip_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self.pdf_tab_strip_widget.setVisible(bool(self.pdf_tabs))
        for i, tab in enumerate(self.pdf_tabs):
            is_active = (i == self.pdf_active_index)
            group = self._build_tab_group_widget(
                os.path.basename(tab.path) or tab.path, tab.path,
                self._viewer_tab_button_style(is_active),
                lambda checked=False, idx=i: self._activate_pdf_tab(idx),
                lambda checked=False, idx=i: self._close_pdf_tab(idx),
            )
            self.pdf_tab_strip_layout.addWidget(group)
        self.pdf_tab_strip_layout.addStretch()
        if len(self.pdf_tabs) > 1:
            self.pdf_tab_strip_layout.addWidget(
                self._build_close_all_tabs_button(lambda checked=False: self._close_all_pdf_tabs())
            )

    def render_pdf_page(self):
        """Render the current PDF page"""
        if not self.pdf_doc or not self.pdf_label:
            return

        # Undo the placeholder's centered alignment (_set_viewer_placeholder) now that
        # there's real content — documents read top-down, not centered in the viewport.
        self.pdf_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

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
            self._set_pdf_page_label_text(f"{self.pdf_current_page + 1} / {self.pdf_page_count}")
        except Exception as e:
            print(f"Error rendering PDF page: {e}")

    def _set_pdf_page_label_text(self, text):
        """Update both page-indicator labels (toolbar + footer nav) together — see
        _build_pdf_footer_page_nav()."""
        if hasattr(self, 'pdf_page_label'):
            self.pdf_page_label.setText(text)
        if hasattr(self, 'pdf_page_label_bottom'):
            self.pdf_page_label_bottom.setText(text)

    def open_pdf_file(self):
        """Open a file dialog to select a PDF"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF File",
            os.path.expanduser("~"),
            "PDF Files (*.pdf);;All Files (*)"
        )

        if file_path:
            if self._open_pdf_tab(file_path):
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

            self.status_label.setText("Loading PDF from URL...")
            self.status_label.setStyleSheet("color: #f39c12; margin: 10px; font-weight: bold;")
            QApplication.processEvents()  # Update UI before blocking download

            if self._open_pdf_tab(url):
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

    def _pdf_zoom_for_fit(self, mode):
        """Compute (without applying) the zoom level that satisfies `mode`
        ('width'/'height'/'page') for the current page/scroll-area size. Returns None
        if there's no PDF/scroll area to measure yet. 'page' fits the whole page inside
        the viewport (the smaller of the width-fit and height-fit zooms), i.e. autofit."""
        if not self.pdf_doc or not self.pdf_scroll:
            return None
        try:
            page = self.pdf_doc[self.pdf_current_page]
            viewport = self.pdf_scroll.viewport()
            # Minus some padding for the scrollbar
            zoom_w = (viewport.width() - 20) / page.rect.width
            zoom_h = (viewport.height() - 20) / page.rect.height
            if mode == "height":
                return zoom_h
            elif mode == "page":
                return min(zoom_w, zoom_h)
            return zoom_w
        except Exception as e:
            print(f"Error computing PDF fit zoom ({mode}): {e}")
            return None

    def pdf_apply_fit(self):
        """Apply whichever fit mode is currently selected (self.pdf_fit_mode) — the
        shared entry point every fit-triggering call site uses (the toolbar toggle
        button, tab activation, and switching into the PDF viewer tab) so they all
        honor whichever mode the user last picked instead of hardcoding fit-to-width."""
        zoom = self._pdf_zoom_for_fit(self.pdf_fit_mode)
        if zoom is None:
            return
        self.pdf_zoom = zoom
        self.render_pdf_page()
        if hasattr(self, 'pdf_zoom_label'):
            self.pdf_zoom_label.setText(f"{int(self.pdf_zoom * 100)}%")

    def pdf_toggle_fit_mode(self):
        """Cycle the toolbar's fit button: Width -> Height -> Page -> Width ..."""
        order = ["width", "height", "page"]
        idx = order.index(self.pdf_fit_mode) if self.pdf_fit_mode in order else 0
        self.pdf_fit_mode = order[(idx + 1) % len(order)]
        self._update_pdf_fit_btn()
        self.pdf_apply_fit()

    def _update_pdf_fit_btn(self):
        """Sync the toolbar's fit-mode button label/tooltip to self.pdf_fit_mode."""
        if not self.pdf_fit_btn:
            return
        labels = {"width": "|—|", "height": "|︙|", "page": "⛶"}
        next_mode = {"width": "Height", "height": "Page", "page": "Width"}
        self.pdf_fit_btn.setText(labels.get(self.pdf_fit_mode, "|—|"))
        self.pdf_fit_btn.setToolTip(
            f"Fit to {self.pdf_fit_mode} (click to switch to Fit {next_mode.get(self.pdf_fit_mode, 'Width')})"
        )

    def pdf_fit_width(self):
        """Fit PDF to scroll area width"""
        zoom = self._pdf_zoom_for_fit("width")
        if zoom is None:
            return
        self.pdf_zoom = zoom
        self.render_pdf_page()
        if hasattr(self, 'pdf_zoom_label'):
            self.pdf_zoom_label.setText(f"{int(self.pdf_zoom * 100)}%")

    def _set_viewer_placeholder(self, label, asset_basename, fallback_text):
        """Show a placeholder graphic (assets/placeholders/) on an empty PDF/image viewer label.

        Falls back to plain text if the asset is missing, so a stripped-down install
        (or a future rename) degrades gracefully instead of showing a blank label.

        Standard layout's viewer column is narrow-but-tall; Focus layout's is wide-but-
        shorter. A single graphic can't fit both well, so there are two variants per asset —
        `{asset_basename}-landscape.png` (Focus) and `{asset_basename}-portrait.png`
        (Standard), e.g. "pdf" -> pdf-landscape.png / pdf-portrait.png. Falls back to the
        landscape file if the portrait one is missing.

        Fit-to-box (both width AND height, via QPixmap.scaled with KeepAspectRatio) rather
        than fit-to-width alone, so whichever dimension is more constraining wins — matters
        since landscape and portrait art have very different aspect ratios. One-shot
        deferred, same pattern as image_fit_width (scheduled 500ms after load to let layout
        settle) rather than a live resize handler, matching that existing precedent.

        Measures self.column2_stack rather than the PDF/image scroll area's own viewport:
        column2_stack holds every viewer container stacked together and is always visible/
        laid-out, whereas whichever container isn't the active tab is hidden — and Qt
        layouts skip hidden widgets, leaving a hidden scroll area's viewport width at 0/stale
        until it's actually shown. column2_stack has no such gap since it's never hidden.
        """
        placeholders_dir = os.path.join(self.script_dir, "assets", "placeholders")
        orientation = "portrait" if self.layout_mode == "standard" else "landscape"
        chosen_filename = f"{asset_basename}-{orientation}.png"
        placeholder_path = os.path.join(placeholders_dir, chosen_filename)
        if not os.path.exists(placeholder_path) and orientation == "portrait":
            placeholder_path = os.path.join(placeholders_dir, f"{asset_basename}-landscape.png")
        pixmap = QPixmap(placeholder_path) if os.path.exists(placeholder_path) else None
        if not pixmap or pixmap.isNull():
            label.setText(fallback_text)
            return

        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        def apply_fit():
            # A layout-mode toggle (or any other refresh_projects()) rebuilds the whole UI
            # and deletes the old label/column2_stack before this deferred call fires — a
            # bare RuntimeError here ("wrapped C/C++ object has been deleted") would escape
            # uncaught from a QTimer slot, which PyQt6 treats as fatal and aborts the process.
            try:
                available_width = max(240, self.column2_stack.width() - 40)
                available_height = max(160, self.column2_stack.height() - 150)
                label.setPixmap(pixmap.scaled(
                    available_width, available_height,
                    Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                ))
            except RuntimeError:
                pass

        apply_fit()  # immediate best-effort so something shows before layout settles
        QTimer.singleShot(500, apply_fit)

    def _make_viewer_footer(self, label, tooltip, callback, left_widget=None):
        """Create a thin footer strip with a single right-aligned action button, and an
        optional extra widget pinned to the left (e.g. the PDF viewer's paging controls,
        so paging is reachable without scrolling back up to the toolbar on a tall page)
        so the two don't have to fight over layout. Every other caller leaves this at
        its default of no left content."""
        footer = QWidget()
        footer.setStyleSheet(f"background-color: {self.t('bg_secondary')}; border-top: 1px solid {self.t('border')};")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(6, 4, 6, 4)
        if left_widget is not None:
            layout.addWidget(left_widget)
        layout.addStretch()
        btn = QPushButton(label)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.t('bg_button')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 4px;
                padding: 3px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        layout.addWidget(btn)
        return footer

    def open_webview_in_external_browser(self):
        """Open the current webview URL in the system default browser."""
        url = self.webview_url or (self.webview.url().toString() if self.webview else None)
        if url and url not in ('about:blank', ''):
            subprocess.Popen(['xdg-open', url], start_new_session=True)
        else:
            QMessageBox.information(self, "No URL", "No URL loaded in the web viewer.")

    def open_pdf_in_external_viewer(self):
        """Open the current PDF in an external viewer application."""
        if not self.pdf_path:
            QMessageBox.information(self, "No PDF", "No PDF loaded.")
            return

        # Skip if PDF is a URL (external viewer expects local files)
        if self.pdf_path.startswith(('http://', 'https://')):
            self.status_label.setText("Cannot open URL-based PDF in external viewer")
            return

        pdfviewer = self.settings.get("pdfviewer", "")
        try:
            if pdfviewer:
                subprocess.Popen([os.path.expanduser(pdfviewer), os.path.expanduser(self.pdf_path)], start_new_session=True)
            else:
                subprocess.Popen(['xdg-open', os.path.expanduser(self.pdf_path)], start_new_session=True)
            self.status_label.setText("Opened in external viewer")
        except Exception as e:
            print(f"Error opening PDF in external viewer: {e}")
            self.status_label.setText(f"Error: {e}")

    def get_viewer_cycle_order(self):
        """Get the viewer cycle order: default -> folder -> remaining viewers.

        Help is deliberately not part of this cycle — it's reference material accessed via the
        footer's "❓ Help" button, not a per-project viewer, since combining it with Examples
        into one page (see _build_help_html)."""
        default_viewer = getattr(self, 'config_column2_default', None) or "pdf"
        # Build cycle: default first, then folder (if not default), then remaining viewers
        remaining = [m for m in ["pdf", "webview", "image", "console"] if m != default_viewer]
        cycle = [default_viewer]
        if default_viewer != "folder":
            cycle.append("folder")
        return cycle + remaining

    def toggle_column2_mode(self):
        """Toggle between viewers: default -> folder -> remaining viewers"""
        # Get dynamic cycle order based on default viewer
        cycle = self.get_viewer_cycle_order()
        current_idx = cycle.index(self.column2_mode) if self.column2_mode in cycle else -1
        next_idx = (current_idx + 1) % len(cycle)
        next_mode = cycle[next_idx]

        # Use the direct switch method
        self.switch_to_viewer_mode(next_mode)

    def switch_to_viewer_mode(self, mode):
        """Switch directly to a specific viewer mode"""
        # Hide all containers
        self.pdf_container.hide()
        self.webview_container.hide()
        self.image_container.hide()
        self.help_container.hide()
        self.console_container.hide()
        self.folder_container.hide()
        self.time_container.hide()
        if hasattr(self, 'notes_viewer_container'):
            self.notes_viewer_container.hide()
        if hasattr(self, 'code_container'):
            self.code_container.hide()
        if hasattr(self, 'settings_container'):
            self.settings_container.hide()

        # Mode display info
        mode_info = {
            "pdf": ("PDF", "PDF Viewer", self.pdf_container),
            "webview": ("Web", "Web View", self.webview_container),
            "image": ("Image", "Image Viewer", self.image_container),
            "help": ("Help", "Help", self.help_container),
            "console": ("Console", "Console", self.console_container),
            "folder": ("Folder", "Folder Browser", self.folder_container),
            "time": ("Time", "Kimai Time Tracker", self.time_container),
        }
        if hasattr(self, 'notes_viewer_container'):
            mode_info["notes"] = ("Notes", "Project Notes", self.notes_viewer_container)
        if hasattr(self, 'code_container'):
            mode_info["code"] = ("Editor", "Code Editor", self.code_container)
        if hasattr(self, 'settings_container'):
            mode_info["settings"] = ("Settings", "Project Settings", self.settings_container)

        if mode not in mode_info:
            mode = "folder"

        self.column2_mode = mode
        btn_text, header_text, container = mode_info[mode]
        container.show()

        # Load content for viewers that need it
        if mode == "help":
            self.load_help_content()
        elif mode == "folder":
            self.populate_folder_browser(self.folder_current_path)
        elif mode == "time":
            self._kimai_load_entries()
        elif mode == "code":
            self._update_code_editor_buttons()
        elif mode == "pdf":
            # Re-fit/re-render on every switch INTO this tab, not just when the PDF was
            # first loaded. pdf_apply_fit() sizes to self.pdf_scroll.viewport().width()/
            # height(), which was very likely wrong at load time if the pdf_container
            # happened to be hidden then (e.g. a project rebuild that lands on some other
            # tab — the Settings viewer in particular, since "Edit Project"/its Save
            # button now trigger a rebuild while column2_mode is frequently "settings") —
            # a hidden widget's viewport reports a stale/default size, so the PDF gets
            # rendered at the wrong zoom and nothing re-renders it later on its own.
            # Cheap to redo (recompute zoom, redraw current page), so just always do it
            # on entry. Goes through pdf_apply_fit() (not pdf_fit_width() directly) so
            # whichever fit mode was last selected is honored, not just fit-width.
            if self.pdf_doc:
                self.pdf_apply_fit()
        elif mode == "image":
            # Same latent issue as "pdf" above, same fix — see that branch's comment.
            if getattr(self, 'image_pixmap', None):
                self.image_fit_width()
        elif mode == "settings":
            # Populate only if not already loaded for this project — see
            # _populate_settings_form()'s docstring for why this guard exists (preserves
            # in-progress edits when re-entering the same project's settings viewer).
            if getattr(self, '_settings_loaded_for', None) != self.current_config_file:
                self._populate_settings_form()
                self._settings_loaded_for = self.current_config_file

        # Update tab button styling
        self.update_viewer_tab_styling()

        self.save_notes()  # Save mode preference

    def update_viewer_tab_styling(self):
        """Update viewer tab buttons to highlight the active mode"""
        if not hasattr(self, 'viewer_tab_buttons'):
            return

        # Normal and active button styles — mirrors tab_btn_style/active_tab_style in
        # build_main_content() (bg_green_1 resting, bg_green_3 active, no border — see that
        # definition's comment for the fuller history of what was tried and reverted).
        normal_style = f"""
            QPushButton {{
                background-color: {self.t('bg_green_1')};
                color: {self.t('fg_on_dark')};
                font-weight: bold;
                border-radius: 3px;
                padding: 5px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_green_2')};
                color: {self.t('fg_on_dark')};
            }}
        """

        active_style = f"""
            QPushButton {{
                background-color: {self.t('bg_green_3')};
                color: {self.t('fg_on_dark')};
                font-weight: bold;
                border-radius: 3px;
                padding: 5px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_green_3')};
                color: {self.t('fg_on_dark')};
            }}
        """

        # Mirrors console_tab_btn_style in build_main_content() — no special border, see
        # that definition's comment for why (used to always have one, read as "selected").
        console_normal_style = f"""
            QPushButton {{
                background-color: {self.t('bg_green_1')};
                color: {self.t('fg_on_dark')};
                font-weight: bold;
                border-radius: 3px;
                padding: 5px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {self.t('bg_green_2')};
                color: {self.t('fg_on_dark')};
            }}
        """

        for mode, btn in self.viewer_tab_buttons.items():
            if mode == self.column2_mode:
                btn.setStyleSheet(active_style)
            elif mode == 'console':
                btn.setStyleSheet(console_normal_style)
            else:
                btn.setStyleSheet(normal_style)

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

        # Markdown edit/preview controls — only visible when a .md file is loaded.
        # Editing is the default mode and autosaves; these just swap to/from the
        # read-only rendered view.
        sep_md = QLabel("|")
        sep_md.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep_md)

        self.md_edit_btn = QPushButton("✏️ Edit")
        self.md_edit_btn.setStyleSheet(btn_style)
        self.md_edit_btn.setToolTip("Edit this markdown file (autosaves)")
        self.md_edit_btn.clicked.connect(lambda: self._open_markdown_in_muya_editor())
        toolbar_layout.addWidget(self.md_edit_btn)

        self.md_preview_btn = QPushButton("👁 Preview")
        self.md_preview_btn.setStyleSheet(btn_style)
        self.md_preview_btn.setToolTip("Save and switch to the read-only rendered preview")
        self.md_preview_btn.clicked.connect(self._muya_switch_to_preview)
        toolbar_layout.addWidget(self.md_preview_btn)

        # "Edit Source" — opt-in counterpart to local .html/.htm's default behavior
        # (render it). Only visible when the webview is currently showing a local HTML
        # file as rendered content (not Muya-editing markdown). Mirrors the code editor's
        # own "👁 Rendered" button (create_code_editor_toolbar) going the other direction.
        self.html_source_btn = QPushButton("</> Edit Source")
        self.html_source_btn.setStyleSheet(btn_style)
        self.html_source_btn.setToolTip("Edit this file's source in the internal code editor")
        self.html_source_btn.clicked.connect(self._open_html_source_from_webview)
        self.html_source_btn.setVisible(False)
        toolbar_layout.addWidget(self.html_source_btn)

        parent_layout.addWidget(toolbar_widget)
        self._update_md_edit_buttons()

    def webview_back(self):
        """Go back in webview history"""
        if self.webview:
            self.webview.back()

    def webview_forward(self):
        """Go forward in webview history"""
        if self.webview:
            self.webview.forward()

    def webview_refresh(self):
        if not self.webview:
            return
        if getattr(self, 'webview_md_path', None):
            # Reload the CURRENT tab's content in place — _open_markdown_in_muya_editor()
            # (not _open_markdown_in_webview()) since the latter now creates a new tab.
            self._open_markdown_in_muya_editor(self.webview_md_path)
        else:
            self.webview.reload()

    def _web_tab_title(self, tab):
        """Short display label for one Web tab's strip button."""
        if tab.kind in ("markdown", "html_file"):
            return os.path.basename(tab.value) or tab.value
        parsed = urllib.parse.urlparse(tab.value)
        return parsed.netloc or tab.value

    def _activate_web_tab(self, index):
        """Make self.web_tabs[index] the active tab. Flushes any unsaved markdown content
        in the CURRENTLY displayed tab first (see _muya_flush_before_switch()) — without
        this, switching away from a markdown tab faster than the ~1.2s autosave poll
        silently dropped the last few seconds of edits, since the target tab's content
        below replaces the page outright (a no-op for URL/HTML tabs, which aren't editing
        anything)."""
        self._muya_flush_before_switch(self._muya_session, lambda: self._do_activate_web_tab(index))

    def _do_activate_web_tab(self, index):
        """The actual tab switch, once any previous markdown tab's content has been safely
        flushed: navigates the one shared self.webview to the target tab (markdown files go
        through the existing Muya bridge; URLs/local HTML get a plain setUrl()) and
        refreshes the tab strip. See WebTabState for why there's only ever one real webview
        regardless of tab count."""
        self.web_active_index = index
        tab = self.web_tabs[index]
        if self.column2_mode != "webview":
            self.switch_to_viewer_mode("webview")
        if tab.kind == "markdown":
            self._open_markdown_in_muya_editor(tab.value)
        else:
            self.webview_md_path = None
            self._muya_session.editing = False
            self._muya_session.autosave_timer.stop()
            if tab.kind == "html_file":
                self.webview.setUrl(QUrl.fromLocalFile(tab.value))
            else:
                self.webview.setUrl(QUrl(tab.value))
            self.webview_url = tab.value
            self._update_md_edit_buttons()
        self._rebuild_web_tab_strip()

    def _open_link_in_new_web_tab(self, url):
        """Callback passed to LinkOpeningWebPage — a link opened via right-click "Open
        link in new tab"/"new window" (or middle-click, or JS window.open()) lands here
        with its destination URL and becomes a genuine new Web tab, switching focus to
        it immediately (matching what "open in new tab" does in a real browser)."""
        self._open_web_tab("url", url)

    def _open_web_tab(self, kind, value):
        """Open a new Web tab and make it active — always-new-tab policy, mirroring
        _open_pdf_tab()/_open_image_tab(). Closes the oldest tab first once WEB_TAB_CAP is
        reached (see that constant's comment for why this isn't about renderer-process
        resource pressure)."""
        if len(self.web_tabs) >= self.WEB_TAB_CAP:
            self._close_web_tab(0)
        self.web_tabs.append(WebTabState(kind, value))
        self._activate_web_tab(len(self.web_tabs) - 1)
        self.save_notes()

    def _navigate_active_web_tab(self, kind, value):
        """Navigate the CURRENTLY active tab to a new location in place (URL bar Enter,
        Home button) rather than opening a new one — matches how a real browser's address
        bar navigates the current tab, unlike clicking a launcher item (always a new tab,
        see _open_web_tab()). Falls back to opening a new tab if none is active yet."""
        if 0 <= self.web_active_index < len(self.web_tabs):
            tab = self.web_tabs[self.web_active_index]
            tab.kind = kind
            tab.value = value
            self._activate_web_tab(self.web_active_index)
            self.save_notes()
        else:
            self._open_web_tab(kind, value)

    def _close_web_tab(self, index):
        """Close and discard the Web tab at `index`, picking a sensible new active tab
        (mirrors _close_pdf_tab()/_close_image_tab())."""
        if not (0 <= index < len(self.web_tabs)):
            return
        closing_active = (index == self.web_active_index)
        self.web_tabs.pop(index)
        if not self.web_tabs:
            self.web_active_index = -1
            self.webview_url = None
            self.webview_md_path = None

            def _clear_webview():
                if self.webview:
                    self.webview.setUrl(QUrl("about:blank"))
                self._rebuild_web_tab_strip()
                self.save_notes()

            # Flush first (see _muya_flush_before_switch()) — closing your only open
            # markdown tab shouldn't lose the last few unsaved seconds any more than
            # switching away from it would.
            self._muya_flush_before_switch(self._muya_session, _clear_webview)
            return
        elif closing_active:
            self._activate_web_tab(min(index, len(self.web_tabs) - 1))
        else:
            if index < self.web_active_index:
                self.web_active_index -= 1
            self._rebuild_web_tab_strip()
        self.save_notes()

    def _close_all_web_tabs(self):
        """Close every open Web tab. _close_web_tab() never refuses to close, and any pending
        Muya autosave flush it needs happens internally (via _activate_web_tab()'s own flush
        when closing the active tab mid-list, or the last-tab flush above) — so this always
        terminates with zero tabs."""
        while self.web_tabs:
            self._close_web_tab(0)

    def _build_web_tab_strip(self, parent_layout):
        """Build the row of Web tab buttons — mirrors _build_pdf_tab_strip()."""
        self.web_tab_strip_widget = QWidget()
        self.web_tab_strip_layout = QHBoxLayout(self.web_tab_strip_widget)
        self.web_tab_strip_layout.setContentsMargins(0, 0, 0, 4)
        self.web_tab_strip_layout.setSpacing(2)
        parent_layout.addWidget(self.web_tab_strip_widget)
        self._rebuild_web_tab_strip()

    def _rebuild_web_tab_strip(self):
        """Clear and repopulate self.web_tab_strip_layout from self.web_tabs — mirrors
        _rebuild_pdf_tab_strip()."""
        if getattr(self, 'web_tab_strip_layout', None) is None:
            return
        while self.web_tab_strip_layout.count():
            item = self.web_tab_strip_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self.web_tab_strip_widget.setVisible(bool(self.web_tabs))
        for i, tab in enumerate(self.web_tabs):
            is_active = (i == self.web_active_index)
            group = self._build_tab_group_widget(
                self._web_tab_title(tab), tab.value,
                self._viewer_tab_button_style(is_active),
                lambda checked=False, idx=i: self._activate_web_tab(idx),
                lambda checked=False, idx=i: self._close_web_tab(idx),
            )
            self.web_tab_strip_layout.addWidget(group)
        self.web_tab_strip_layout.addStretch()
        if len(self.web_tabs) > 1:
            self.web_tab_strip_layout.addWidget(
                self._build_close_all_tabs_button(lambda checked=False: self._close_all_web_tabs())
            )

    def webview_home(self):
        """Navigate to home URL from config — navigates the current tab in place."""
        if self.webview and hasattr(self, 'config_webview_url') and self.config_webview_url:
            self._navigate_active_web_tab("url", self.config_webview_url)

    def webview_navigate(self):
        """Navigate to URL in URL bar — navigates the current tab in place, like a real
        browser's address bar (unlike launcher clicks, which always open a new tab)."""
        if self.webview and self.webview_url_bar:
            url = self.webview_url_bar.text().strip()
            if url:
                if not url.startswith(('http://', 'https://', 'file://')):
                    url = 'https://' + url
                self._navigate_active_web_tab("url", url)

    def on_webview_url_changed(self, url):
        """Handle URL changes in webview"""
        if self.webview_url_bar:
            self.webview_url_bar.setText(url.toString())
        self.webview_url = url.toString()
        # Keep the active tab's remembered URL in sync as the user browses within it (e.g.
        # clicking links) — matches how a real browser tab remembers wherever you've
        # navigated to, not just where it was originally opened. Guarded to "url" tabs only:
        # this signal also fires for the Muya shell's own internal navigation when a
        # markdown/html_file tab is active, which must not clobber that tab's remembered path.
        if 0 <= self.web_active_index < len(self.web_tabs) and self.web_tabs[self.web_active_index].kind == "url":
            self.web_tabs[self.web_active_index].value = self.webview_url
        self.save_notes()

    def preview_in_webview(self, url):
        """Preview a URL in the webview panel — always opens as a new tab (see
        _open_web_tab()), even if the same URL is already open in another tab."""
        if not self.webview:
            return
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        self._open_web_tab("url", url)

    def preview_in_image_viewer(self, path):
        """Preview an image in the image viewer panel — always opens as a new tab (see
        _open_image_tab()), even if the same file is already open in another tab."""
        if not hasattr(self, 'image_label') or not self.image_label:
            return

        # Switch to image mode directly
        if self.column2_mode != "image":
            self.switch_to_viewer_mode("image")

        self._open_image_tab(path)

    def preview_in_pdf_viewer(self, path):
        """Preview a PDF in the PDF viewer panel — always opens as a new tab (see
        _open_pdf_tab()), even if the same file is already open in another tab."""
        if self.column2_mode != "pdf":
            self.switch_to_viewer_mode("pdf")
        self._open_pdf_tab(path)

    def _is_local_path(self, path):
        """Return True if path looks like a local file/folder (not remote/URL/command)"""
        if not path:
            return False
        # Exclude anything with a URI scheme (http, https, vscode-remote, ssh, ftp, etc.)
        if '://' in path:
            return False
        # Exclude --flag= style arguments (e.g. --folder-uri=...)
        if path.startswith('--'):
            return False
        # Exclude shell compound commands
        if any(op in path for op in ('&&', '||', ';')):
            return False
        # Exclude SSH-style user@host targets (@ before first slash)
        first_segment = path.split('/')[0]
        if '@' in first_segment:
            return False
        # Accept clear local path prefixes
        if path.startswith(('/', '~/', '~', './', '.')):
            return True
        # Accept if the expanded path actually exists on disk
        return os.path.exists(os.path.expanduser(path))

    def preview_in_folder_browser(self, path):
        """Preview a folder in the folder browser panel"""
        # Expand path and get directory if it's a file
        expanded_path = os.path.expanduser(path)
        if os.path.isfile(expanded_path):
            expanded_path = os.path.dirname(expanded_path)

        # Always set the path first (even if folder_browser doesn't exist yet)
        self.folder_current_path = expanded_path

        # Check if folder browser widget exists before trying to display
        if not hasattr(self, 'folder_browser') or not self.folder_browser:
            return

        # Switch to folder mode (this will call populate_folder_browser with folder_current_path)
        if self.column2_mode != "folder":
            self.switch_to_viewer_mode("folder")
        else:
            # Already in folder mode, just navigate to the new path
            self.populate_folder_browser(expanded_path)

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
        open_btn = QPushButton(" Open")
        open_btn.setIcon(self._open_icon())
        open_btn.setIconSize(QSize(16, 16))
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

        toolbar_layout.addStretch()
        parent_layout.addWidget(toolbar_widget)

    def open_image_in_external_viewer(self):
        """Open the current image in an external viewer (gwenview)"""
        if not self.image_path:
            return
        expanded_path = os.path.expanduser(self.image_path)
        if os.path.exists(expanded_path):
            subprocess.Popen(["gwenview", expanded_path], start_new_session=True)

    def create_code_editor_toolbar(self, parent_layout):
        """Create a toolbar for the internal code editor: filename label, Save button
        (no URL bar/back/forward — this is a different tool from the webview, not a
        'page'), and a Rendered-preview toggle shown only for .html/.htm files."""
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 5)
        toolbar_layout.setSpacing(5)

        btn_style = f"""
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
            QPushButton:pressed {{
                background-color: {self.t('bg_category_hover')};
            }}
            QPushButton:checked {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
                border: 1px solid {self.t('bg_category_hover')};
            }}
        """

        self.code_open_btn = QPushButton(" Open")
        self.code_open_btn.setIcon(self._open_icon())
        self.code_open_btn.setIconSize(QSize(16, 16))
        self.code_open_btn.setStyleSheet(btn_style)
        self.code_open_btn.setToolTip("Open a file in the code editor")
        self.code_open_btn.clicked.connect(self.open_code_file)
        toolbar_layout.addWidget(self.code_open_btn)

        self.code_filename_label = QLabel(os.path.basename(self._code_session.path) if self._code_session.path else "")
        self.code_filename_label.setStyleSheet(f"color: {self.t('fg_primary')}; font-weight: bold; margin-right: 5px;")
        toolbar_layout.addWidget(self.code_filename_label)

        toolbar_layout.addStretch()

        # Line wrapping is off by default in CM6's basicSetup (long lines just scroll
        # horizontally) — this toggle flips a runtime Compartment (__setCodeEditorWrap in
        # editor.html), so it doesn't reload the file or touch undo history/dirty state.
        # Persisted per-machine (like viewer_height/folder_view_mode), not per-project —
        # it's a personal reading preference, not project content.
        self.code_wrap_btn = QPushButton("↩ Wrap")
        self.code_wrap_btn.setStyleSheet(btn_style)
        self.code_wrap_btn.setToolTip("Wrap long lines instead of scrolling horizontally")
        self.code_wrap_btn.setCheckable(True)
        self.code_wrap_btn.setChecked(self.settings.get('code_editor_wrap', True))
        self.code_wrap_btn.clicked.connect(self._code_editor_toggle_wrap)
        toolbar_layout.addWidget(self.code_wrap_btn)

        self.code_source_toggle_btn = QPushButton("👁 Rendered")
        self.code_source_toggle_btn.setStyleSheet(btn_style)
        self.code_source_toggle_btn.setToolTip("Switch back to the rendered HTML preview")
        self.code_source_toggle_btn.clicked.connect(self._code_editor_switch_to_rendered)
        self.code_source_toggle_btn.setVisible(False)
        toolbar_layout.addWidget(self.code_source_toggle_btn)

        self.code_save_btn = QPushButton("💾 Save")
        self.code_save_btn.setStyleSheet(btn_style)
        self.code_save_btn.setToolTip("Save changes to disk (Ctrl+S)")
        self.code_save_btn.clicked.connect(lambda: self._code_editor_save(self._code_session))
        self.code_save_btn.setEnabled(bool(self._code_session.editing and self._code_session.path))
        toolbar_layout.addWidget(self.code_save_btn)

        parent_layout.addWidget(toolbar_widget)

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

        toolbar_layout.addStretch()
        parent_layout.addWidget(toolbar_widget)

    def open_help_in_external_editor(self):
        """Open README.md in the configured editor"""
        readme_path = os.path.join(self.script_dir, "README.md")
        editor = self.settings.get("open_note_external") or "kate"
        if os.path.exists(readme_path):
            subprocess.Popen([editor, readme_path], start_new_session=True)

    def _load_examples_html_fragment(self):
        """Read EXAMPLES.html with theme placeholders substituted — used as the "Launcher
        Examples" tab's iframe content in the combined Help page (_build_help_html)."""
        examples_path = os.path.join(self.script_dir, "EXAMPLES.html")
        if not os.path.exists(examples_path):
            return f"<p style='color: {self.t('fg_primary')}'>EXAMPLES.html not found.</p>"
        try:
            with open(examples_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            return re.sub(r'\{(\w+)\}', lambda m: self.t(m.group(1)), html_content)
        except Exception as e:
            return f"<p style='color: {self.t('fg_primary')}'>Could not load EXAMPLES.html: {e}</p>"

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

        # Open folder button — retargets the ACTIVE terminal tab's directory (see
        # console_open_directory/_retarget_active_terminal_tab)
        open_btn = QPushButton(" Open")
        open_btn.setIcon(self._open_icon())
        open_btn.setIconSize(QSize(16, 16))
        open_btn.setStyleSheet(btn_style)
        open_btn.setToolTip("Change the current terminal's directory")
        open_btn.clicked.connect(self.console_open_directory)
        toolbar_layout.addWidget(open_btn)

        # "+ New Terminal" — always opens a genuinely separate tab (see
        # _new_terminal_tab_dialog), unlike the Open button above which retargets the
        # active one. Only meaningful for ttyd — qtconsole has no tab concept.
        if self.resolve_console_backend() == "ttyd":
            new_tab_btn = QPushButton("+ New Terminal")
            new_tab_btn.setStyleSheet(btn_style)
            new_tab_btn.setToolTip(f"Open a new terminal tab (max {self.TERMINAL_TAB_CAP} at once)")
            new_tab_btn.clicked.connect(self._new_terminal_tab_dialog)
            toolbar_layout.addWidget(new_tab_btn)

        # Separator
        sep1 = QLabel("|")
        sep1.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep1)

        # Path label with limitation hint — shows the ACTIVE terminal tab's directory
        self.console_path_label = QLabel("~")
        self.console_path_label.setStyleSheet(f"font-size: 11px; color: {self.t('fg_secondary')};")
        if self.resolve_console_backend() == "ttyd":
            self.console_path_label.setToolTip(
                "Real terminal (ttyd) - a full interactive shell, including nano/vim/htop."
            )
        else:
            self.console_path_label.setToolTip(
                "Python/IPython console - use !command for shell commands.\n"
                "Limitations: No interactive programs (nano, vim, htop).\n"
                "Use 'External' button for full terminal features."
            )
        toolbar_layout.addWidget(self.console_path_label, 1)

        # Alias quick-jump buttons — only meaningful for a real interactive shell (ttyd);
        # qtconsole has no notion of "type this command into the running session". Capped so a
        # project with many aliases doesn't crowd out the rest of the toolbar; order follows the
        # project's own config (so reordering categories/items there controls which ones make
        # the cut). Anything past the cap is still reachable via the "+N" overflow menu.
        if self.resolve_console_backend() == "ttyd":
            ALIAS_TOOLBAR_LIMIT = 10
            project_aliases = self._get_current_project_aliases()
            for alias_name, alias_command in project_aliases[:ALIAS_TOOLBAR_LIMIT]:
                alias_btn = QPushButton(alias_name)
                alias_btn.setStyleSheet(btn_style)
                alias_btn.setToolTip(f"Run in terminal: {alias_command}")
                alias_btn.clicked.connect(
                    lambda checked=False, cmd=alias_command: self._run_alias_in_ttyd_console(cmd)
                )
                toolbar_layout.addWidget(alias_btn)

            overflow_aliases = project_aliases[ALIAS_TOOLBAR_LIMIT:]
            if overflow_aliases:
                overflow_btn = QPushButton(f"+{len(overflow_aliases)}")
                overflow_btn.setStyleSheet(btn_style)
                overflow_btn.setToolTip(f"{len(overflow_aliases)} more aliases")
                overflow_btn.clicked.connect(
                    lambda checked=False: self._show_alias_overflow_menu(overflow_aliases, overflow_btn)
                )
                toolbar_layout.addWidget(overflow_btn)

        parent_layout.addWidget(toolbar_widget)

    def console_open_directory(self):
        """Open a directory picker and navigate the console to it. For ttyd, this retargets
        the ACTIVE terminal tab (reusing an existing tab already at that directory if one
        exists, else killing and respawning the active tab's own shell there) — the same
        "picking a new directory replaces the current shell" behavior this had before tabs
        existed, not a regression. The toolbar's separate "+ New Terminal" button
        (_new_terminal_tab_dialog) is the one that always opens a genuinely new tab."""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Directory for Console",
            os.path.expanduser("~")
        )
        if folder_path:
            if self.resolve_console_backend() == "ttyd":
                self._retarget_active_terminal_tab(folder_path)
            else:
                self.console_path = folder_path
                self.console_path_label.setText(folder_path)
                if self.console_available and hasattr(self, 'console_widget'):
                    self.console_widget.execute(f'import os; os.chdir("{folder_path}")', hidden=True)
                    self.console_widget.execute('!pwd')

    def _new_terminal_tab_dialog(self):
        """"+ New Terminal" toolbar button: prompts for a directory and always opens it as a
        genuinely new tab (subject to the cwd-reuse rule and TERMINAL_TAB_CAP in
        _open_terminal_tab) — unlike console_open_directory()/the Open button, which
        retarget the currently-active tab instead."""
        folder_path = QFileDialog.getExistingDirectory(
            self, "New Terminal — Select Directory",
            getattr(self, 'console_path', None) or os.path.expanduser("~")
        )
        if folder_path:
            self._open_terminal_tab(folder_path)

    # Hard cap on simultaneously-live terminal tabs (see TerminalTabState) — each one is a
    # real ttyd subprocess + OS port + QWebEngineView, a materially more expensive resource
    # than a PDF/Image tab or the single shared Web/Notes webview. At the cap, opening
    # another tab is REFUSED outright (see _open_terminal_tab) rather than silently
    # evicting the oldest tab the way WEB_TAB_CAP does — a background terminal tab can have
    # a real process running in it (a dev server, a build, tail -f), and silently killing
    # that without warning is exactly the kind of side effect CLAUDE.md's Code Cleanup
    # Guidelines warn against.
    TERMINAL_TAB_CAP = 5

    def _find_terminal_tab_for_cwd(self, cwd):
        """Return the index of an existing, still-alive terminal tab already rooted at
        `cwd` (must already be expanduser()'d), or -1. This is the reuse-by-directory check
        every "open a terminal at this directory" call site goes through, so repeat clicks
        on the same launcher item/log file don't pile up duplicate shells in the same
        folder — the same guarantee the old single-console _ensure_ttyd_console() gave via
        its cwd+liveness check, now scanning N tabs instead of one scalar."""
        for i, tab in enumerate(self.terminal_tabs):
            if tab.cwd == cwd and tab.proc is not None and tab.proc.poll() is None:
                return i
        return -1

    def _spawn_terminal_tab(self, tab):
        """Create `tab`'s QWebEngineView (if it doesn't have one yet) and spawn its ttyd
        subprocess, navigating the webview to it once a port is known. Mutates `tab` in
        place; returns True on success, False if ttyd isn't on PATH or failed to report a
        port in time. Split out from _open_terminal_tab() so a tab restored from disk
        (proc=None, webview=None, only cwd known — see TerminalTabState/load_config()) can
        be spawned lazily the first time it's actually activated, rather than eagerly
        spawning every restored tab's shell the instant a project loads.

        `-O`/`--check-origin` matters even though this only ever binds to 127.0.0.1:
        WebSocket connections aren't subject to the same-origin policy the way fetch/XHR
        are, so without it any JavaScript running in any browser tab on the machine could
        open a WebSocket to this port directly and get a shell — a malicious-webpage attack
        class localhost binding alone doesn't prevent. `-O` makes ttyd reject connections
        whose Origin header doesn't match, closing that off.
        """
        if tab.webview is None:
            tab.webview = QWebEngineView()
            self._enable_web_fullscreen_support(tab.webview)
            tab.webview.loadFinished.connect(lambda ok, t=tab: setattr(t, 'ready', ok))

        shell = os.environ.get("SHELL", "bash")
        try:
            proc = subprocess.Popen(
                ["ttyd", "-i", "127.0.0.1", "-p", "0", "-W", "-O", "-w", tab.cwd, shell],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                start_new_session=False,  # must die with the app, not survive it
            )
        except FileNotFoundError:
            return False  # ttyd not on PATH — resolve_console_backend() should have already avoided this

        port = None
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            match = re.search(r"Listening on port:\s*(\d+)", line)
            if match:
                port = int(match.group(1))
                break

        if port is None:
            proc.terminate()
            return False

        tab.proc = proc
        tab.port = port
        tab.ready = False
        tab.webview.setUrl(QUrl(f"http://127.0.0.1:{port}/"))
        return True

    def _open_terminal_tab(self, cwd):
        """Open (or reuse) a terminal tab rooted at `cwd` and make it active. If a live tab
        already sits at this exact directory, activates it instead of spawning a duplicate
        shell. Otherwise, refuses to open past TERMINAL_TAB_CAP simultaneously-live tabs
        (no silent eviction — see TERMINAL_TAB_CAP's own comment). Returns True if a tab is
        now active at `cwd` (whether reused or newly created), False if refused or ttyd
        failed to start."""
        cwd = os.path.expanduser(cwd)
        existing = self._find_terminal_tab_for_cwd(cwd)
        if existing != -1:
            self._activate_terminal_tab(existing)
            return True

        if len(self.terminal_tabs) >= self.TERMINAL_TAB_CAP:
            self.set_status(
                f"Terminal tab limit reached ({self.TERMINAL_TAB_CAP}) — close a tab first.",
                "warning",
            )
            return False

        tab = TerminalTabState(cwd)
        if not self._spawn_terminal_tab(tab):
            self.set_status("Could not start terminal (ttyd) — is it installed?", "error")
            return False
        self.terminal_tabs.append(tab)
        self._activate_terminal_tab(len(self.terminal_tabs) - 1)
        self.save_notes()
        return True

    def _retarget_active_terminal_tab(self, cwd):
        """Point the currently-active terminal tab at a new directory — reusing an existing
        tab already at that directory if one exists, otherwise killing and respawning the
        ACTIVE tab's own ttyd process there. This is what console_open_directory() (the
        toolbar's directory picker) uses; _open_terminal_tab()/_new_terminal_tab_dialog()
        always open a genuinely separate tab instead."""
        cwd = os.path.expanduser(cwd)
        existing = self._find_terminal_tab_for_cwd(cwd)
        if existing != -1:
            self._activate_terminal_tab(existing)
            return
        if not self.terminal_tabs:
            self._open_terminal_tab(cwd)
            return
        tab = self.terminal_tabs[self.terminal_active_index]
        self._stop_terminal_tab(tab)
        tab.cwd = cwd
        self._spawn_terminal_tab(tab)
        if getattr(self, 'console_path_label', None) is not None:
            self.console_path_label.setText(cwd)
        self.console_path = cwd
        self._rebuild_terminal_tab_strip()
        self.save_notes()

    def _stop_terminal_tab(self, tab):
        """Terminate `tab`'s ttyd subprocess, if any (per-tab equivalent of the old
        singleton console's _stop_ttyd_console())."""
        proc = tab.proc
        if proc is None:
            return
        tab.proc = None
        tab.port = None
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    def _activate_terminal_tab(self, index):
        """Make self.terminal_tabs[index] the active tab: spawn its ttyd process lazily if
        it hasn't been started yet (a tab restored from disk holds only a cwd until first
        activated — see TerminalTabState/load_config()), swap which tab's webview is shown
        in console_container_layout, refresh the toolbar's path label, and rebuild the tab
        strip. Unlike _activate_pdf_tab(), there's no mutable per-tab UI state to flush on
        the way out — the shell itself holds all live state, untouched by switching."""
        if not (0 <= index < len(self.terminal_tabs)):
            return
        tab = self.terminal_tabs[index]
        if tab.proc is None or tab.proc.poll() is not None:
            if not self._spawn_terminal_tab(tab):
                self.set_status("Could not start terminal (ttyd) — is it installed?", "error")
                return
        self.terminal_active_index = index

        if getattr(self, '_console_active_webview', None) is not tab.webview:
            layout = getattr(self, 'console_container_layout', None)
            if layout is not None:
                if getattr(self, '_console_active_webview', None) is not None:
                    layout.removeWidget(self._console_active_webview)
                    self._console_active_webview.setParent(self)
                layout.addWidget(tab.webview, 1)
            tab.webview.show()
            self._console_active_webview = tab.webview

        if getattr(self, 'console_empty_label', None) is not None:
            self.console_empty_label.hide()
        if getattr(self, 'console_path_label', None) is not None:
            self.console_path_label.setText(tab.cwd)
        self.console_path = tab.cwd
        self._rebuild_terminal_tab_strip()

    def _close_terminal_tab(self, index):
        """Close and discard the terminal tab at `index`: stop its ttyd subprocess, detach
        and discard its webview, and pick a sensible new active tab (the one now at the
        same index, the last remaining tab, or none if the list becomes empty) — mirrors
        _close_pdf_tab()."""
        if not (0 <= index < len(self.terminal_tabs)):
            return
        closing_active = (index == self.terminal_active_index)
        tab = self.terminal_tabs.pop(index)
        self._stop_terminal_tab(tab)
        if tab.webview is not None:
            if getattr(self, '_console_active_webview', None) is tab.webview:
                layout = getattr(self, 'console_container_layout', None)
                if layout is not None:
                    layout.removeWidget(tab.webview)
                self._console_active_webview = None
            tab.webview.setParent(None)
            tab.webview.deleteLater()
            tab.webview = None
        if not self.terminal_tabs:
            self.terminal_active_index = -1
            if getattr(self, 'console_empty_label', None) is not None:
                self.console_empty_label.show()
            self._rebuild_terminal_tab_strip()
        elif closing_active:
            self._activate_terminal_tab(min(index, len(self.terminal_tabs) - 1))
        else:
            if index < self.terminal_active_index:
                self.terminal_active_index -= 1
            self._rebuild_terminal_tab_strip()
        self.save_notes()

    def _close_all_terminal_tabs(self):
        """Close every open terminal tab (stopping every ttyd subprocess). Nothing in this
        path can refuse to close (unlike Editor's dirty-tab confirmation), so this always
        terminates with zero tabs — used both by the tab strip's "Close All" button and
        when the console backend switches away from ttyd (build_main_content()), where
        persisting "now zero terminal tabs" via _close_terminal_tab()'s save_notes() call
        is exactly what's wanted."""
        while self.terminal_tabs:
            self._close_terminal_tab(0)

    def _teardown_terminal_tabs(self):
        """Stop every terminal tab's ttyd subprocess and discard its webview, clearing
        self.terminal_tabs — the process-cleanup half of _close_all_terminal_tabs() WITHOUT
        its save_notes() call. Used by load_config() when switching to a different project:
        the outgoing project's terminal tabs must be killed so their processes/ports don't
        leak, but save_notes() would write the (still only partially loaded) NEW project's
        in-memory state back over its own config file, since is_project_switch/
        self.current_config_file already point at the new project by the time this runs."""
        while self.terminal_tabs:
            tab = self.terminal_tabs.pop()
            self._stop_terminal_tab(tab)
            if tab.webview is not None:
                if getattr(self, '_console_active_webview', None) is tab.webview:
                    self._console_active_webview = None
                tab.webview.setParent(None)
                tab.webview.deleteLater()
                tab.webview = None
        self.terminal_active_index = -1

    def _build_terminal_tab_strip(self, parent_layout):
        """Build the row of terminal tab buttons (one per open TerminalTabState, with a
        close button each) — sits between the toolbar and the console webview. Mirrors
        _build_pdf_tab_strip() exactly."""
        self.terminal_tab_strip_widget = QWidget()
        self.terminal_tab_strip_layout = QHBoxLayout(self.terminal_tab_strip_widget)
        self.terminal_tab_strip_layout.setContentsMargins(0, 0, 0, 4)
        self.terminal_tab_strip_layout.setSpacing(2)
        parent_layout.addWidget(self.terminal_tab_strip_widget)
        self._rebuild_terminal_tab_strip()

    def _rebuild_terminal_tab_strip(self):
        """Clear and repopulate self.terminal_tab_strip_layout from self.terminal_tabs —
        called after every open/close/activate so the strip stays in sync without a full
        rebuild. A no-op if the strip hasn't been built yet this pass (guards startup
        ordering, mirrors _rebuild_pdf_tab_strip())."""
        if getattr(self, 'terminal_tab_strip_layout', None) is None:
            return
        while self.terminal_tab_strip_layout.count():
            item = self.terminal_tab_strip_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self.terminal_tab_strip_widget.setVisible(bool(self.terminal_tabs))
        for i, tab in enumerate(self.terminal_tabs):
            is_active = (i == self.terminal_active_index)
            label = os.path.basename(tab.cwd.rstrip('/')) or tab.cwd
            group = self._build_tab_group_widget(
                label, tab.cwd,
                self._viewer_tab_button_style(is_active),
                lambda checked=False, idx=i: self._activate_terminal_tab(idx),
                lambda checked=False, idx=i: self._close_terminal_tab(idx),
            )
            self.terminal_tab_strip_layout.addWidget(group)
        self.terminal_tab_strip_layout.addStretch()
        if len(self.terminal_tabs) > 1:
            self.terminal_tab_strip_layout.addWidget(
                self._build_close_all_tabs_button(lambda checked=False: self._close_all_terminal_tabs())
            )

    def _get_current_project_aliases(self):
        """Return [(name, command), ...] for every alias item in the current project's own
        launcher categories (self.COLUMN_1) — not the separate cross-project alias file/project.
        Parsed the same way open_in_app's alias branch does: path = "name command_or_directory"."""
        aliases = []
        for category_dict in self.COLUMN_1:
            for _category_name, items in category_dict.items():
                for item in items:
                    if len(item) >= 3 and item[2] == "alias":
                        name, _, rest = item[1].partition(' ')
                        rest = rest.strip()
                        if rest:
                            aliases.append((name, rest))
        return aliases

    def _run_alias_in_ttyd_console(self, command):
        """Run an alias's command inside the ACTIVE terminal tab (paste + submit) — "do this
        in the terminal I'm looking at", not a new-tab action (unlike log-tailing/terminal-
        launcher routing below, which open/reuse a tab at a specific directory first).
        Ensures at least one tab exists, spawning one at the project's console_path (or ~)
        if none are open yet.

        window.term.paste() alone does not execute anything — xterm.js always wraps pasted
        text in bracketed-paste escape sequences, and bash's readline treats a bracketed paste
        as literal text to insert rather than auto-submitting it (verified empirically). There
        is no public xterm.js API to simulate pressing Enter, so this reaches into the private
        `_core.coreService` API to submit the line after pasting — wrapped in try/catch so a
        future ttyd/xterm.js bump that changes this internal shape degrades to "text pasted but
        not submitted" rather than a JS error.
        """
        if not self.terminal_tabs:
            if not self._open_terminal_tab(getattr(self, 'console_path', None) or "~"):
                return
        tab = self.terminal_tabs[self.terminal_active_index]
        if tab.proc is None or tab.proc.poll() is not None:
            if not self._spawn_terminal_tab(tab):
                return
        self._run_in_ttyd_when_ready(tab, command)

    def _run_in_ttyd_when_ready(self, tab, command, attempts=0):
        """Pastes+submits `command` in `tab`'s live ttyd terminal once its page has actually
        finished loading (tab.ready), rather than as soon as tab.proc reports the OS process
        alive. Those are NOT the same thing: setUrl() triggers an async page load, and the
        gap is real — even a just-spawned tab isn't necessarily done loading (window.term
        doesn't exist yet) by the time something else tries to paste into it moments later
        (observed empirically: the paste is silently lost, no error). Polls every 100ms for
        up to ~5s rather than hanging forever if something goes wrong.

        Once ready, an additional fixed 500ms settle delay is applied before actually
        pasting — loadFinished firing only means the page's own HTML/JS has loaded, not that
        xterm.js's WebSocket connection to ttyd's backing PTY has finished its handshake.
        Confirmed empirically: pasting immediately on the ready transition is silently
        dropped nearly every time (no error, paste just never reaches the PTY), while the
        same paste 500ms later lands reliably every time tested — a real gap between "page
        loaded" and "terminal actually ready for input", not a page-load race.
        """
        if tab.ready:
            QTimer.singleShot(500, lambda: self._paste_and_submit_in_ttyd(tab, command))
            return
        if attempts >= 50:
            return
        QTimer.singleShot(100, lambda: self._run_in_ttyd_when_ready(tab, command, attempts + 1))

    def _paste_and_submit_in_ttyd(self, tab, command):
        """The actual paste-and-Enter JS call for `tab` — split out from
        _run_alias_in_ttyd_console so _run_in_ttyd_when_ready() can share it.

        The trailing no-op callback is load-bearing, not decoration: page().runJavaScript()
        called WITHOUT a callback was observed to silently no-op on this exact script often
        enough to be unusable (confirmed empirically — same script, same state, only
        difference being presence of a callback argument) — some PyQt6/QtWebEngine internal
        fire-and-forget path apparently doesn't reliably run to completion. Passing any
        callback, even one that discards the result, made it reliable every time tested.
        """
        if tab.webview is None:
            return
        tab.webview.page().runJavaScript(
            f"window.term && window.term.paste({json.dumps(command)});"
            f"try {{ window.term._core.coreService.triggerDataEvent('\\r', true); }} catch(e) {{}}",
            lambda _result: None,
        )

    def _resolve_tail_log_target(self, expanded_path):
        """Mirrors handle_tail_log()'s file resolution (launch_handlers.py, the external-
        terminal handler for app == "tail_log") — given a directory, prefer debug.log,
        fall back to error.log, default to debug.log if neither exists yet (tail -f will
        just wait for it to appear). Given a file path directly, use it as-is."""
        if os.path.isfile(expanded_path):
            return expanded_path
        if os.path.isdir(expanded_path):
            debug_log = os.path.join(expanded_path, 'debug.log')
            error_log = os.path.join(expanded_path, 'error.log')
            if os.path.exists(debug_log):
                return debug_log
            if os.path.exists(error_log):
                return error_log
            return debug_log
        if os.path.splitext(expanded_path)[1]:
            return expanded_path
        return os.path.join(expanded_path, 'debug.log')

    def _open_log_file_in_console(self, expanded_path, lines=300):
        """Focus-layout internal routing for tail_log launcher items and .log files: opens
        (or reuses — see _open_terminal_tab's cwd-reuse rule) a terminal tab rooted at the
        log's directory and tails the file there (tail -n <lines> -f) instead of spawning an
        external terminal. Only reachable when the ttyd backend is active (checked by the
        caller) — qtconsole's kernel would hang forever on a `!tail -f`, since -f never
        exits."""
        log_file = self._resolve_tail_log_target(expanded_path)
        if self.column2_mode != "console":
            self.switch_to_viewer_mode("console")
        workdir = os.path.dirname(log_file) or os.path.expanduser("~")
        if not self._open_terminal_tab(workdir):
            return
        tab = self.terminal_tabs[self.terminal_active_index]
        command = f"tail -n {lines} -f {shlex.quote(log_file)}"
        self._run_in_ttyd_when_ready(tab, command)

    def _open_terminal_launcher_in_console(self, expanded_path):
        """Focus-layout internal routing for terminal/konsole launcher items: opens (or
        reuses — see _open_terminal_tab's cwd-reuse rule) a terminal tab rooted at the
        item's target directory and cd's into it (running its trailing command, if any —
        same "path command args" convention the external terminal/konsole handler already
        parses) instead of spawning an external one. Only reachable when the ttyd backend is
        active (checked by the caller) — qtconsole has no live interactive shell to cd into,
        only discrete `!command` calls."""
        parts = expanded_path.split()
        workdir = parts[0]
        command = " ".join(parts[1:]) if len(parts) > 1 else ""
        if os.path.isfile(workdir):
            workdir = os.path.dirname(workdir)
        if self.column2_mode != "console":
            self.switch_to_viewer_mode("console")
        if not self._open_terminal_tab(workdir):
            return
        tab = self.terminal_tabs[self.terminal_active_index]
        shell_cmd = f"cd {shlex.quote(workdir)}" + (f" && {command}" if command else "")
        self._run_in_ttyd_when_ready(tab, shell_cmd)

    def _show_alias_overflow_menu(self, aliases, anchor_btn):
        """Show the aliases past the console toolbar's cap (see create_console_toolbar) in a
        popup menu, so they're still reachable rather than just silently cut off."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
            }}
            QMenu::item:selected {{
                background-color: {self.t('bg_config_hover')};
                color: {self.t('fg_on_dark')};
            }}
        """)
        for alias_name, alias_command in aliases:
            action = menu.addAction(alias_name)
            action.setToolTip(alias_command)
            action.triggered.connect(
                lambda checked=False, cmd=alias_command: self._run_alias_in_ttyd_console(cmd)
            )
        menu.exec(anchor_btn.mapToGlobal(anchor_btn.rect().bottomLeft()))

    def console_open_external(self):
        """Open external terminal at the current console path"""
        path = getattr(self, 'console_path', None) or os.path.expanduser("~")
        expanded_path = os.path.expanduser(path)
        if os.path.isfile(expanded_path):
            expanded_path = os.path.dirname(expanded_path)
        cmd = self._get_terminal_workdir_command(expanded_path)
        subprocess.Popen(cmd, start_new_session=True)

    def create_folder_toolbar(self, parent_layout):
        """Create a toolbar for the folder browser"""
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

        # Up button
        up_btn = QPushButton("↑")
        up_btn.setStyleSheet(btn_style)
        up_btn.setToolTip("Go up one directory")
        up_btn.clicked.connect(self.folder_go_up)
        toolbar_layout.addWidget(up_btn)

        # Home button
        home_btn = QPushButton("⌂")
        home_btn.setStyleSheet(btn_style)
        home_btn.setToolTip("Go to home directory")
        home_btn.clicked.connect(self.folder_go_home)
        toolbar_layout.addWidget(home_btn)

        # Project default folder button — always shown, greyed out (but still clickable)
        # when this project has no folder_path pinned yet. Clicking it while greyed pins
        # the currently browsed folder as the project default; once pinned, it switches to
        # its active style and navigates there instead (see _pin_current_folder_as_project_default).
        project_home_btn = QPushButton("⌂⌂")
        if self.config_folder_path:
            project_home_btn.setStyleSheet(btn_style)
            project_home_btn.setToolTip(f"Go to project folder: {self.config_folder_path}")
            project_home_btn.clicked.connect(self.folder_go_project_default)
        else:
            project_home_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.t('bg_button')};
                    color: {self.t('border')};
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
            """)
            project_home_btn.setToolTip("Set current folder as this project's default folder")
            project_home_btn.clicked.connect(self._pin_current_folder_as_project_default)
        toolbar_layout.addWidget(project_home_btn)

        # Refresh button
        refresh_btn = QPushButton("↻")
        refresh_btn.setStyleSheet(btn_style)
        refresh_btn.setToolTip("Refresh current directory")
        refresh_btn.clicked.connect(self.folder_refresh)
        toolbar_layout.addWidget(refresh_btn)

        # View mode toggle (tree/details vs Dolphin-style icon grid)
        self.folder_view_toggle_btn = QPushButton("⊞" if self.folder_view_mode == "tree" else "☰")
        self.folder_view_toggle_btn.setStyleSheet(btn_style)
        self.folder_view_toggle_btn.setToolTip(
            "Switch to icon grid view" if self.folder_view_mode == "tree" else "Switch to list view"
        )
        self.folder_view_toggle_btn.clicked.connect(self._toggle_folder_view_mode)
        toolbar_layout.addWidget(self.folder_view_toggle_btn)

        # Separator
        sep1 = QLabel("|")
        sep1.setStyleSheet(f"color: {self.t('border')}; margin: 0 5px;")
        toolbar_layout.addWidget(sep1)

        # Path label
        self.folder_path_label = QLabel("~")
        self.folder_path_label.setStyleSheet(f"font-size: 11px; color: {self.t('fg_secondary')};")
        self.folder_path_label.setToolTip("Current directory")
        toolbar_layout.addWidget(self.folder_path_label, 1)

        # Pin default button
        default_btn = QPushButton()
        default_btn.setIcon(self._pin_icon())
        default_btn.setIconSize(QSize(16, 16))
        default_btn.setStyleSheet(btn_style)
        default_btn.setToolTip("Set this folder as default for this project")
        default_btn.clicked.connect(self.set_viewer_as_default)
        toolbar_layout.addWidget(default_btn)

        parent_layout.addWidget(toolbar_widget)

    def _build_launcher_folder_panel(self, column_layout):
        """Build the compact file-browser panel embedded in the Focus-layout launcher column.

        A lightweight sibling of the main Folder viewer's tree — shares navigation state
        (self.folder_current_path) and is kept in sync by populate_folder_browser(), but
        clicking a file opens it straight into the built-in viewer (see _open_path_in_best_viewer)
        instead of the tree's default navigate/xdg-open behavior.
        """
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 4)
        toolbar_layout.setSpacing(5)

        up_btn = QPushButton("↑")
        up_btn.setStyleSheet(f"""
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
        """)
        up_btn.setToolTip("Go up one directory")
        up_btn.clicked.connect(self.folder_go_up)
        toolbar_layout.addWidget(up_btn)

        mini_btn_style = f"""
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
        """

        home_btn = QPushButton("⌂")
        home_btn.setStyleSheet(mini_btn_style)
        home_btn.setToolTip("Go to home directory")
        home_btn.clicked.connect(self.folder_go_home)
        toolbar_layout.addWidget(home_btn)

        # Always shown; greyed out (but still clickable) when no folder_path is pinned yet
        # — see create_folder_toolbar's matching button for the full explanation.
        project_home_btn = QPushButton("⌂⌂")
        if self.config_folder_path:
            project_home_btn.setStyleSheet(mini_btn_style)
            project_home_btn.setToolTip(f"Go to project folder: {self.config_folder_path}")
            project_home_btn.clicked.connect(self.folder_go_project_default)
        else:
            project_home_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.t('bg_button')};
                    color: {self.t('border')};
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
            """)
            project_home_btn.setToolTip("Set current folder as this project's default folder")
            project_home_btn.clicked.connect(self._pin_current_folder_as_project_default)
        toolbar_layout.addWidget(project_home_btn)

        refresh_btn = QPushButton("↻")
        refresh_btn.setStyleSheet(mini_btn_style)
        refresh_btn.setToolTip("Refresh current directory")
        refresh_btn.clicked.connect(self.folder_refresh)
        toolbar_layout.addWidget(refresh_btn)

        self.launcher_folder_view_toggle_btn = QPushButton(
            "☰" if self.folder_view_mode == "icons" else "⊞"
        )
        self.launcher_folder_view_toggle_btn.setStyleSheet(mini_btn_style)
        self.launcher_folder_view_toggle_btn.setToolTip(
            "Switch to list view" if self.folder_view_mode == "icons" else "Switch to icon grid view"
        )
        self.launcher_folder_view_toggle_btn.clicked.connect(self._toggle_folder_view_mode)
        toolbar_layout.addWidget(self.launcher_folder_view_toggle_btn)

        self.launcher_folder_path_label = QLabel("~")
        self.launcher_folder_path_label.setStyleSheet(f"font-size: 11px; color: {self.t('fg_secondary')};")
        self.launcher_folder_path_label.setToolTip("Current directory")
        toolbar_layout.addWidget(self.launcher_folder_path_label, 1)

        column_layout.addWidget(toolbar_widget)

        self.launcher_folder_browser = QTreeWidget()
        self.launcher_folder_browser.setHeaderHidden(True)
        self.launcher_folder_browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.launcher_folder_browser.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {self.t('bg_secondary')};
                border: 2px solid {self.t('border')};
                border-radius: 5px;
                color: {self.t('fg_primary')};
                font-size: 12px;
            }}
            QTreeWidget::item {{
                padding: 4px 8px;
            }}
            QTreeWidget::item:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QTreeWidget::item:selected {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
            }}
        """)
        self.launcher_folder_browser.setMouseTracking(True)
        self.launcher_folder_browser.viewport().setMouseTracking(True)
        self.launcher_folder_browser.setItemDelegate(FolderBrowserDelegate(self))
        self.launcher_folder_browser.itemClicked.connect(self.on_launcher_folder_item_clicked)
        self.launcher_folder_browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.launcher_folder_browser.customContextMenuRequested.connect(self.launcher_folder_browser_context_menu)

        self.launcher_folder_icon_view = QListWidget()
        self.launcher_folder_icon_view.setViewMode(QListWidget.ViewMode.IconMode)
        self.launcher_folder_icon_view.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.launcher_folder_icon_view.setMovement(QListWidget.Movement.Static)
        self.launcher_folder_icon_view.setWrapping(True)
        self.launcher_folder_icon_view.setIconSize(QSize(40, 40))
        self.launcher_folder_icon_view.setGridSize(QSize(80, 96))
        self.launcher_folder_icon_view.setSpacing(4)
        self.launcher_folder_icon_view.setWordWrap(True)
        self.launcher_folder_icon_view.setUniformItemSizes(True)
        self.launcher_folder_icon_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.launcher_folder_icon_view.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.t('bg_secondary')};
                border: 2px solid {self.t('border')};
                border-radius: 5px;
                color: {self.t('fg_primary')};
                font-size: 11px;
            }}
            QListWidget::item {{
                padding: 4px;
                border-radius: 3px;
            }}
            QListWidget::item:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QListWidget::item:selected {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
            }}
        """)
        self.launcher_folder_icon_view.itemClicked.connect(self.on_launcher_folder_icon_item_clicked)
        self.launcher_folder_icon_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.launcher_folder_icon_view.customContextMenuRequested.connect(self.launcher_folder_icon_view_context_menu)

        self.launcher_folder_view_stack = QStackedWidget()
        self.launcher_folder_view_stack.addWidget(self.launcher_folder_browser)
        self.launcher_folder_view_stack.addWidget(self.launcher_folder_icon_view)
        self.launcher_folder_view_stack.setCurrentIndex(1 if self.folder_view_mode == "icons" else 0)
        column_layout.addWidget(self.launcher_folder_view_stack, 1)

        self.launcher_folder_filter_input = self._build_folder_filter_bar(column_layout)

        fm_name = os.path.basename(self.get_configured_file_manager()).capitalize()
        column_layout.addWidget(
            self._make_viewer_footer(f"Open in {fm_name}", "Open current folder in file manager", self.folder_open_external)
        )

        # populate_folder_browser is otherwise only called when the Folder viewer tab is active
        # (column2_mode == "folder") — this panel must show content regardless of the active tab.
        start_path = getattr(self, 'folder_current_path', None) or os.path.expanduser("~")
        self.populate_folder_browser(start_path)

    def _scan_folder_entries(self, path):
        """Scan a directory into a widget-agnostic list of entry dicts.

        Single source of truth for dotfile-skipping, dir-then-file sort order,
        and the .projectflow "[P]" badge, so the tree and icon views can never drift.
        Returns (entries, error_message) — entries is None on error.
        """
        try:
            raw_entries = os.listdir(path)
        except PermissionError:
            return None, "Permission denied"
        except FileNotFoundError:
            return None, "This folder doesn't exist on this device (moved, deleted, or not mounted?)"
        except Exception as e:
            return None, f"Error: {str(e)}"

        dirs = []
        files = []
        for entry in raw_entries:
            if entry.startswith('.'):
                continue  # Skip hidden files
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                dirs.append(entry)
            else:
                files.append(entry)

        dirs.sort(key=str.lower)
        files.sort(key=str.lower)

        result = []
        for d in dirs:
            full_path = os.path.join(path, d)
            is_project = os.path.exists(os.path.join(full_path, ".projectflow"))
            display_name = f"[P] {d}/" if is_project else f"{d}/"
            result.append({
                'full_path': full_path, 'display_name': display_name,
                'kind': 'dir', 'is_project': is_project,
            })
        for f in files:
            full_path = os.path.join(path, f)
            result.append({
                'full_path': full_path, 'display_name': f,
                'kind': 'file', 'is_project': False,
            })
        return result, None

    def _folder_icon(self, color_hex):
        """Hand-drawn flat folder icon in the given color — used instead of the system theme's
        folder icon (which renders yellow/manila on many setups) so it looks consistent everywhere."""
        cache = self._folder_icon_cache if hasattr(self, '_folder_icon_cache') else {}
        if not hasattr(self, '_folder_icon_cache'):
            self._folder_icon_cache = cache
        if color_hex in cache:
            return cache[color_hex]
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color_hex))
        painter.drawRoundedRect(QRect(8, 16, 24, 10), 2, 2)
        painter.drawRoundedRect(QRect(8, 22, 48, 30), 4, 4)
        painter.end()
        icon = QIcon(pixmap)
        cache[color_hex] = icon
        return icon

    def _blue_folder_icon(self):
        return self._folder_icon("#3498db")

    def _folder_theme_icon(self):
        """Folder icon shared by all folder browser views (tree, icon grid, launcher panel)."""
        return self._blue_folder_icon()

    def _open_icon(self):
        """Plain single-color 'open folder' icon for Open-file buttons (Code/Notes 'Open',
        PDF/Image/Terminal 'Open' toolbar buttons) — replaces the 📂/📤 emoji, which render
        as a yellow/manila Windows-style folder on many systems. Pre-rendered PNGs (not the
        dynamic QPainter approach used by _folder_icon()) since this needs a light-on-dark vs
        dark-on-light variant matched to fg_primary, not an arbitrary single color."""
        cache_attr = f'_open_icon_cache_{self.current_theme}'
        icon = getattr(self, cache_attr, None)
        if icon is None:
            fname = "open-folder-dark.png" if self.current_theme == "dark" else "open-folder-light.png"
            icon = QIcon(os.path.join(self.script_dir, "assets", "icons", fname))
            setattr(self, cache_attr, icon)
        return icon

    def _pin_icon(self):
        """Plain single-color 'pin' icon for pin buttons that sit on a plain, theme-dependent
        button background (e.g. the Folder viewer's own toolbar pin) — same light/dark PNG
        pair convention as _open_icon(). Pin buttons on a colored bar (launcher tab row's blue
        bg_category, viewer tab row's green bg_green_1) use the fixed-white
        assets/tab-icons/pin.png instead, matching how those rows' other icons are white."""
        cache_attr = f'_pin_icon_cache_{self.current_theme}'
        icon = getattr(self, cache_attr, None)
        if icon is None:
            fname = "pin-dark.png" if self.current_theme == "dark" else "pin-light.png"
            icon = QIcon(os.path.join(self.script_dir, "assets", "icons", fname))
            setattr(self, cache_attr, icon)
        return icon

    def _hamburger_icon(self):
        """Plain single-color hamburger (☰) icon for the title-bar project mega-menu button —
        same light/dark PNG pair convention as _open_icon()/_pin_icon(), since it sits on the
        plain title-bar background, not a colored tab row."""
        cache_attr = f'_hamburger_icon_cache_{self.current_theme}'
        icon = getattr(self, cache_attr, None)
        if icon is None:
            fname = "hamburger-dark.png" if self.current_theme == "dark" else "hamburger-light.png"
            icon = QIcon(os.path.join(self.script_dir, "assets", "icons", fname))
            setattr(self, cache_attr, icon)
        return icon

    def _render_folder_tree(self, entries, target=None):
        """Render scanned entries into a tree/details view — self.folder_browser by default,
        or the given target widget (e.g. the launcher-column mini panel)."""
        tree = target if target is not None else self.folder_browser
        tree.clear()
        icon_provider = QFileIconProvider()
        folder_icon = self._folder_theme_icon()

        for e in entries:
            item = QTreeWidgetItem()
            item.setText(0, e['display_name'])
            if e['is_project']:
                item.setToolTip(0, "ProjectFlow project folder")
            item.setIcon(0, folder_icon if e['kind'] == 'dir' else icon_provider.icon(QFileInfo(e['full_path'])))
            item.setData(0, Qt.ItemDataRole.UserRole, e['full_path'])
            item.setData(0, Qt.ItemDataRole.UserRole + 1, e['kind'])
            tree.addTopLevelItem(item)

    def _render_folder_icons(self, entries, target=None):
        """Render scanned entries into an icon grid — self.folder_icon_view by default,
        or the given target widget (e.g. the launcher-column mini panel)."""
        grid = target if target is not None else self.folder_icon_view
        grid.clear()
        # Undo whatever _render_folder_error_into_icon_view() may have left behind (see
        # there) — this is the one place real content gets rendered back into the grid.
        grid.setViewMode(QListWidget.ViewMode.IconMode)
        grid.setWrapping(True)
        icon_provider = QFileIconProvider()
        folder_icon = self._folder_theme_icon()

        for e in entries:
            icon = folder_icon if e['kind'] == 'dir' else icon_provider.icon(QFileInfo(e['full_path']))
            item = QListWidgetItem(icon, e['display_name'])
            # Full name as a tooltip — the grid cell wraps long names but still elides past a
            # couple of lines, so this is the reliable way to always see the whole filename.
            tooltip = e['display_name']
            if e['is_project']:
                tooltip += "\n(ProjectFlow project folder)"
            item.setToolTip(tooltip)
            item.setData(Qt.ItemDataRole.UserRole, e['full_path'])
            item.setData(Qt.ItemDataRole.UserRole + 1, e['kind'])
            grid.addItem(item)

    def _render_folder_error_into_icon_view(self, grid, message):
        """Show a scan error (e.g. "folder doesn't exist") in an icon-grid folder view.

        A plain QListWidgetItem added while the grid is still in IconMode gets forced into
        one fixed-size grid cell (setGridSize()) regardless of text length — the error text
        wraps inside that one small cell and sits alone in the corner of an otherwise empty
        grid, unreadable. Switching to ListMode for the error item makes it lay out as a
        normal full-width, word-wrapped row instead. _render_folder_icons() switches the
        grid back to IconMode the next time real entries are rendered, so this is undone
        automatically on the next successful navigation."""
        grid.clear()
        grid.setViewMode(QListWidget.ViewMode.ListMode)
        grid.setWrapping(False)
        item = QListWidgetItem(message)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        grid.addItem(item)

    def populate_folder_browser(self, path):
        """Populate the folder browser (both tree and icon views) with contents of the given path.

        Note: the main Folder-viewer-tab widgets (folder_path_label/folder_browser/
        folder_icon_view) aren't guaranteed to exist yet — the launcher-column Quick File
        Browser Panel is built earlier in build_main_content() than they are, and can now call
        this on the very first-ever build if it starts pre-expanded (persisted per project).
        """
        path = os.path.expanduser(path)

        # If the direct path doesn't exist, try it once through the global path mappings as
        # a fallback (see _resolve_existing_path()) — e.g. a project's default folder saved
        # as ~/Public/key that's only reachable as ~/gtr7/Public/key on this machine.
        # Read-only: folder_current_path/the path label reflect the resolved path for this
        # navigation only — nothing is written back to any config, so the original portable
        # folder_path is untouched.
        self.folder_via_mapping = False
        if not os.path.exists(path):
            resolved, used_mapping = self._resolve_existing_path(path)
            if used_mapping:
                path = os.path.expanduser(resolved)
                self.folder_via_mapping = True
                self.set_status(f"Folder not found — opened via path mapping instead: {path}", "info")

        self.folder_current_path = path

        # Update path label (shorten home dir to ~)
        display_path = path
        home = os.path.expanduser("~")
        if path.startswith(home):
            display_path = "~" + path[len(home):]
        if self.folder_via_mapping:
            display_path = "⇄ " + display_path
        main_path_label = getattr(self, 'folder_path_label', None)
        if main_path_label is not None:
            main_path_label.setText(display_path)
            self._style_folder_path_label(main_path_label)
        launcher_path_label = getattr(self, 'launcher_folder_path_label', None)
        if launcher_path_label is not None:
            launcher_path_label.setText(display_path)
            self._style_folder_path_label(launcher_path_label)

        self._folder_raw_entries, self._folder_scan_error = self._scan_folder_entries(path)
        self._render_folder_views_from_cache()

    def _style_folder_path_label(self, label):
        """Style a folder-browser path label — plain secondary text normally, or a pale-blue
        badge (background + tooltip) when self.folder_via_mapping is set, so it's visually
        obvious the folder shown isn't the one actually saved in the project (see
        _resolve_existing_path()/Settings → Advanced's path mappings table). Hand-picked pale
        blue per theme rather than a themes.py color, same reasoning as the Notes paper theme
        and code-editor syntax colors — a one-off accent, not part of the general palette."""
        if self.folder_via_mapping:
            if self.current_theme == "dark":
                bg, fg = "#1c3a52", "#8ecbff"
            else:
                bg, fg = "#dbeeff", "#1a5a8a"
            label.setStyleSheet(
                f"font-size: 11px; color: {fg}; background-color: {bg}; "
                f"padding: 2px 6px; border-radius: 3px;"
            )
            label.setToolTip(
                "This folder wasn't found directly — showing the result of a path mapping "
                "(Settings → Advanced → Path Mappings) instead. The project's own saved path "
                "is unchanged."
            )
        else:
            label.setStyleSheet(f"font-size: 11px; color: {self.t('fg_secondary')};")
            label.setToolTip("Current directory")

    def _render_folder_views_from_cache(self):
        """Render self._folder_raw_entries (filtered by self.folder_filter_text, a Dolphin-style
        filter bar) into whichever folder-browsing target widgets currently exist. Shared by
        populate_folder_browser() and the filter bar's textChanged handler so live filtering
        doesn't need to re-scan disk on every keystroke."""
        entries = self._folder_raw_entries
        error = self._folder_scan_error
        main_tree = getattr(self, 'folder_browser', None)
        main_icons = getattr(self, 'folder_icon_view', None)
        launcher_tree = getattr(self, 'launcher_folder_browser', None)
        launcher_icons = getattr(self, 'launcher_folder_icon_view', None)
        if error is not None:
            if main_tree is not None:
                main_tree.clear()
                main_tree.addTopLevelItem(QTreeWidgetItem([error]))
            if main_icons is not None:
                self._render_folder_error_into_icon_view(main_icons, error)
            if launcher_tree is not None:
                launcher_tree.clear()
                launcher_tree.addTopLevelItem(QTreeWidgetItem([error]))
            if launcher_icons is not None:
                self._render_folder_error_into_icon_view(launcher_icons, error)
            return

        filter_text = (self.folder_filter_text or "").strip().lower()
        entries = [e for e in entries if filter_text in e['display_name'].lower()] if filter_text else entries

        if main_tree is not None:
            self._render_folder_tree(entries)
        if main_icons is not None:
            self._render_folder_icons(entries)
        if launcher_tree is not None:
            self._render_folder_tree(entries, target=launcher_tree)
        if launcher_icons is not None:
            self._render_folder_icons(entries, target=launcher_icons)

    def _build_folder_filter_bar(self, parent_layout):
        """Build a Dolphin-style filter bar: a text box that live-filters the current folder's
        entries by substring match against the display name. Returns the QLineEdit — callers
        store their own ref since the main viewer and launcher panel each need their own widget
        instance, kept in sync via self.folder_filter_text / _on_folder_filter_changed()."""
        filter_input = QLineEdit()
        filter_input.setPlaceholderText("Filter...")
        filter_input.setClearButtonEnabled(True)
        filter_input.setText(self.folder_filter_text)
        filter_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.t('bg_secondary')};
                color: {self.t('fg_primary')};
                border: 1px solid {self.t('border')};
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {self.t('border_dark')};
            }}
        """)
        filter_input.textChanged.connect(self._on_folder_filter_changed)
        parent_layout.addWidget(filter_input)
        return filter_input

    def _on_folder_filter_changed(self, text):
        """Keep both filter boxes (main viewer + launcher panel) in sync and re-render from the
        cached scan without touching disk."""
        self.folder_filter_text = text
        for inp in (getattr(self, 'folder_filter_input', None), getattr(self, 'launcher_folder_filter_input', None)):
            if inp is not None and inp.text() != text:
                inp.blockSignals(True)
                inp.setText(text)
                inp.blockSignals(False)
        if getattr(self, '_folder_raw_entries', None) is not None:
            self._render_folder_views_from_cache()

    def folder_go_up(self):
        """Navigate to parent directory"""
        parent = os.path.dirname(self.folder_current_path)
        if parent and parent != self.folder_current_path:
            self.populate_folder_browser(parent)

    def folder_go_home(self):
        """Navigate to home directory"""
        self.populate_folder_browser(os.path.expanduser("~"))

    def folder_go_project_default(self):
        """Navigate to this project's own configured folder_path."""
        if self.config_folder_path:
            self.populate_folder_browser(self.config_folder_path)

    def _pin_current_folder_as_project_default(self):
        """Pin the currently browsed folder as this project's default folder_path — the
        action behind the always-visible "⌂⌂ project folder" button while it's greyed out
        (no folder_path set yet). Mirrors the pin pattern used for viewers/launcher tabs
        (set_viewer_as_default()/_set_launcher_tab_as_default()). refresh_projects() rebuilds
        both folder toolbars so the button switches to its active style/behavior immediately."""
        if not getattr(self, 'current_config_file', None) or not getattr(self, 'folder_current_path', None):
            return
        try:
            config_data = {}
            if os.path.exists(self.current_config_file):
                with open(self.current_config_file, 'r') as f:
                    config_data = json.load(f)
            config_data['folder_path'] = self.folder_current_path
            with open(self.current_config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            self.config_folder_path = self.folder_current_path
            QMessageBox.information(self, "Set Default", f"Set \"{self.folder_current_path}\" as this project's default folder.")
            self.refresh_projects()
        except Exception as e:
            print(f"Error pinning project folder: {e}")
            QMessageBox.warning(self, "Error", f"Failed to set default folder: {e}")

    def folder_refresh(self):
        """Refresh current directory listing"""
        self.populate_folder_browser(self.folder_current_path)

    def _scaled_icon(self, icon):
        """Force an icon down to a genuine single 64x64 pixmap.

        QIcon.pixmap(size) is only a *request* — for icon-engine-backed icons (which most
        system theme icons are) it returns the closest available native resolution rather
        than actually scaling, e.g. asking a Firefox/GIMP/Kate icon for 64x64 still hands
        back its native 128x128 pixmap. QListWidget's IconMode (used by the Apps tab grid)
        sizes each item's on-screen layout off the icon's real pixmap dimensions rather than
        the widget's setIconSize() in that case — empirically confirmed: items with these
        oversized icons rendered with the icon visible but their text label pushed outside
        the 110x130 grid cell entirely, while items with a smaller/null icon laid out fine.
        Explicitly re-scaling the pixmap (not just re-requesting it) sidesteps this.
        """
        pixmap = icon.pixmap(QSize(64, 64))
        if pixmap.isNull():
            return QIcon()
        if pixmap.size() != QSize(64, 64):
            pixmap = pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return QIcon(pixmap)

    def _theme_icon(self, candidate_names, fallback=None):
        """Try system-theme icon names in order, returning the first that resolves, scaled
        via _scaled_icon to a genuine single 64x64 pixmap (see that method's docstring).

        Falls back to the bundled assets/icon-generic-app.png — a plain neutral window
        shape — rather than a further system-theme name like "application-x-executable".
        That name technically exists in many icon themes, but commonly renders as a
        gear/cog (the conventional "generic executable" glyph), which reads as "settings"
        rather than "app" and was confusing next to real launcher tiles. `fallback` is still
        available for a MIME-appropriate intermediate try (e.g. "text-x-generic" before
        giving up entirely) — it just no longer defaults to the cog-prone system name.
        """
        for name in candidate_names:
            icon = QIcon.fromTheme(name)
            if not icon.isNull():
                return self._scaled_icon(icon)
        if fallback:
            icon = QIcon.fromTheme(fallback)
            if not icon.isNull():
                return self._scaled_icon(icon)
        generic_path = os.path.join(self.script_dir, "assets", "icon-generic-app.png")
        return self._scaled_icon(QIcon(generic_path)) if os.path.exists(generic_path) else QIcon()

    def _build_apps_tab_items(self):
        """Curated per-project "Apps" tile list for the Apps launcher tab: distinct real
        applications this project's own launchers reference, plus the project's configured
        Terminal and Editor (always included), plus built-in content-viewer tiles (PDF/
        Image/Markdown) when the project actually has matching content.

        Deliberately excludes structural/path-action handlers (npm, ssh_session,
        directorydev, alias, dolphin_tabs, tail_log, rsync_backup*, file_manager, konsole/
        terminal, and any custom "shell"-type handler) — those are actions on a specific
        path, not standalone applications you'd open blank, so they stay reachable only via
        their normal launcher items in the Resources tab.

        Returns a list of dicts: {'label', 'icon', 'kind': 'viewer'|'markdown'|'app', 'target'}.
        'target' is a switch_to_viewer_mode() mode string for kind='viewer' (PDF/Image, which
        already have known content via config_pdf_file/config_image_file); a concrete file
        path for kind='markdown' (the first local .md item found — there's no per-project
        "default markdown file" setting the way PDF/Image have one); or the resolved app
        binary name for kind='app'.
        """
        STRUCTURAL_APPS = {
            'browser', 'file_manager', 'dolphin', 'editor', 'default',
            'konsole', 'terminal', 'alias', 'projectflowlink',
            'tail_log', 'ssh_session', 'ssh_cd_npm', 'terminal_cmd', 'terminal_npm',
            'npm', 'directorydev', 'dolphin_tabs',
            'rsync_backup', 'rsync_backup_id', 'rsync_backup_id_port',
        }
        IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg')

        # A resolved binary name isn't always a valid theme-icon name too — VS Code's
        # package binary is "code" but its icon is usually registered as "vscode" (or the
        # Flatpak reverse-DNS id), LibreOffice has no single icon at all (only per-app ones
        # like "libreoffice-writer"), etc. Tried in order before falling back to the bundled
        # generic-app icon (_theme_icon).
        ICON_NAME_ALIASES = {
            'code': ['code', 'vscode', 'com.visualstudio.code', 'visual-studio-code'],
            'codium': ['vscodium', 'codium', 'com.vscodium.codium'],
            'konsole': ['konsole', 'org.kde.konsole', 'utilities-terminal'],
            'libreoffice': ['libreoffice-startcenter', 'libreoffice-main', 'libreoffice'],
            'soffice': ['libreoffice-startcenter', 'libreoffice-main', 'libreoffice'],
        }

        resolved_apps = {}  # binary name -> display label, insertion order doesn't matter (sorted later)

        def add_app(binary):
            if not binary:
                return
            name = os.path.basename(str(binary)).split()[0].lower()
            if name and name not in resolved_apps:
                resolved_apps[name] = name.replace('-', ' ').replace('_', ' ').title()

        has_pdf = bool(getattr(self, 'config_pdf_file', None))
        has_image = bool(getattr(self, 'config_image_file', None))
        # Unlike has_pdf/has_image (backed by config_pdf_file/config_image_file, a genuine
        # per-project default that's already loaded into self.pdf_path/self.image_path at
        # project load time), there's no equivalent "default markdown file" setting — the
        # general viewer's self.webview_md_path is purely runtime state, never persisted.
        # So the Markdown tile needs its own concrete path to open, not just a mode switch;
        # markdown_path is the first local .md item found (see 'markdown' kind below).
        markdown_path = None

        for cat_dict in self.COLUMN_1:
            for category_name, items in cat_dict.items():
                for item in items:
                    path, app = (item[1], "kate") if len(item) == 2 else (item[1], item[2])

                    first_token = str(path).split()[0] if ' ' in str(path) else str(path)
                    ext = os.path.splitext(first_token)[1].lower()
                    if ext == '.md':
                        if markdown_path is None:
                            markdown_path = os.path.expanduser(first_token)
                    elif ext == '.pdf':
                        has_pdf = True
                    elif ext in IMAGE_EXTS:
                        has_image = True

                    if app in STRUCTURAL_APPS:
                        continue
                    if self.custom_handlers.get(app, {}).get('type') == 'shell':
                        continue
                    add_app(app)

        # Always include the project's configured Terminal + Editor, resolved to their real
        # binary — merges with any item that already uses that same binary literally.
        add_app(self.get_configured_terminal())
        add_app(self.get_configured_editor())

        # Short, single-word labels — matches the terse style of the real-app tiles
        # (Firefox/Kate/etc.) and avoids wrapping/eliding in the grid's narrow tiles.
        tiles = []
        if markdown_path:
            tiles.append({
                'label': 'Markdown', 'kind': 'markdown', 'target': markdown_path,
                'icon': self._theme_icon(['text-markdown', 'text-x-markdown'], 'text-x-generic'),
            })
        if has_pdf:
            tiles.append({
                'label': 'PDF', 'kind': 'viewer', 'target': 'pdf',
                'icon': self._theme_icon(['application-pdf'], 'text-x-generic'),
            })
        if has_image:
            tiles.append({
                'label': 'Images', 'kind': 'viewer', 'target': 'image',
                'icon': self._theme_icon(['accessories-image-viewer', 'image-viewer'], 'image-x-generic'),
            })

        for name, label in sorted(resolved_apps.items(), key=lambda kv: kv[1]):
            tiles.append({
                'label': label, 'kind': 'app', 'target': name,
                'icon': self._theme_icon(ICON_NAME_ALIASES.get(name, [name])),
            })

        return tiles

    def _build_apps_tab(self, column_layout):
        """Build the Apps tab's content: a large icon-grid of per-project app tiles (see
        _build_apps_tab_items). Mirrors the launcher-panel folder icon grid's QListWidget
        setup (_build_launcher_folder_panel) but with bigger tiles per user request — this
        is meant to read as a small, distinctive app-switcher, not a file list."""
        apps_list = QListWidget()
        apps_list.setViewMode(QListWidget.ViewMode.IconMode)
        apps_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        apps_list.setMovement(QListWidget.Movement.Static)
        apps_list.setWrapping(True)
        apps_list.setIconSize(QSize(64, 64))
        apps_list.setGridSize(QSize(110, 130))
        apps_list.setSpacing(6)
        apps_list.setWordWrap(True)
        # NOT setUniformItemSizes(True) — unlike the folder icon grid (which only ever shows
        # the one same "folder" icon), this grid mixes items with a real theme icon and items
        # whose icon lookup failed (empty QIcon). Empirically confirmed: with uniform sizing
        # on, any item that HAS a real icon renders the icon but its text label vanishes
        # entirely (clipped by a size Qt computed from a differently-shaped item) — off, both
        # icon and text render correctly for every item regardless of icon presence.
        apps_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        apps_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.t('bg_secondary')};
                border: 2px solid {self.t('border')};
                border-radius: 5px;
                color: {self.t('fg_primary')};
                font-size: 12px;
            }}
            QListWidget::item {{
                padding: 6px;
                border-radius: 4px;
            }}
            QListWidget::item:hover {{
                background-color: {self.t('bg_button_hover')};
                color: {self.t('fg_on_dark')};
            }}
            QListWidget::item:selected {{
                background-color: {self.t('bg_category')};
                color: {self.t('fg_on_dark')};
            }}
        """)

        for tile in self._build_apps_tab_items():
            list_item = QListWidgetItem(tile['icon'], tile['label'])
            list_item.setData(Qt.ItemDataRole.UserRole, tile)
            list_item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            apps_list.addItem(list_item)

        apps_list.itemClicked.connect(self._on_apps_tab_item_clicked)
        column_layout.addWidget(apps_list, 1)

    def _on_apps_tab_item_clicked(self, list_item):
        """Launch an Apps-tab tile: built-in PDF/Image viewers switch the wide viewer tab
        (they already have known content via config_pdf_file/config_image_file); the
        Markdown tile opens its concrete file directly (see _build_apps_tab_items — there's
        no equivalent "default markdown file" setting for switch_to_viewer_mode alone to
        reveal); external apps launch pointed at the project's own folder via the existing
        open_in_app() dispatch (so per-app quirks like "kate+directory opens Dolphin
        instead" apply automatically) — with force_external=True so Focus layout's
        content-type routing (which would otherwise intercept e.g. a folder path into the
        internal folder preview) is bypassed, since these tiles are explicitly meant to
        open the real app. Browsers (firefox/chrome) get "about:blank" instead of the
        folder path, since their command always templates the path in as a URL, not a
        directory."""
        tile = list_item.data(Qt.ItemDataRole.UserRole)
        if tile['kind'] == 'viewer':
            self.switch_to_viewer_mode(tile['target'])
            return
        if tile['kind'] == 'markdown':
            self._open_markdown_file(tile['target'])
            return
        app_name = tile['target']
        target = "about:blank" if app_name in ('firefox', 'chrome') else (
            self.config_folder_path or os.path.expanduser("~")
        )
        self.open_in_app(target, app_name, force_external=True)

    def _toggle_folder_view_mode(self):
        """Switch the folder browser(s) between tree/details and Dolphin-style icon grid view —
        applies to both the main Folder viewer and the launcher-column mini panel, whichever exist."""
        self.folder_view_mode = "icons" if self.folder_view_mode == "tree" else "tree"
        self.settings["folder_view_mode"] = self.folder_view_mode
        self.save_settings()
        index = 1 if self.folder_view_mode == "icons" else 0
        btn_text = "☰" if self.folder_view_mode == "icons" else "⊞"
        btn_tooltip = (
            "Switch to list view" if self.folder_view_mode == "icons" else "Switch to icon grid view"
        )
        if getattr(self, 'folder_view_stack', None) is not None:
            self.folder_view_stack.setCurrentIndex(index)
            self.folder_view_toggle_btn.setText(btn_text)
            self.folder_view_toggle_btn.setToolTip(btn_tooltip)
        if getattr(self, 'launcher_folder_view_stack', None) is not None:
            self.launcher_folder_view_stack.setCurrentIndex(index)
            self.launcher_folder_view_toggle_btn.setText(btn_text)
            self.launcher_folder_view_toggle_btn.setToolTip(btn_tooltip)

    def _handle_folder_item_activation(self, path, item_type):
        """Open/navigate to a folder-browser entry — shared by the tree and icon views."""
        if not path:
            return

        if item_type == "dir":
            # Check if it's a project folder
            projectflow_path = os.path.join(path, ".projectflow")
            if os.path.exists(projectflow_path):
                # Open the project
                self.switch_to_config(projectflow_path)
            else:
                # Navigate into the directory
                self.populate_folder_browser(path)
        elif item_type == "file":
            ext = os.path.splitext(path)[1].lower()
            # .html/.htm default into the code editor now (see _CODE_ROUTE_EXTENSIONS) —
            # local files open in the editor, only URLs open in the web viewer.
            if ext == '.md':
                self._open_markdown_file(path)
            elif ext in self._CODE_ROUTE_EXTENSIONS:
                self._open_code_file_in_editor(path)
            else:
                subprocess.Popen(["xdg-open", path], start_new_session=True)

    def on_folder_item_clicked(self, item, column):
        """Handle single-click on a tree-view folder browser item"""
        self._handle_folder_item_activation(
            item.data(0, Qt.ItemDataRole.UserRole),
            item.data(0, Qt.ItemDataRole.UserRole + 1),
        )

    def on_folder_icon_item_clicked(self, item):
        """Handle single-click on an icon-grid folder browser item"""
        self._handle_folder_item_activation(
            item.data(Qt.ItemDataRole.UserRole),
            item.data(Qt.ItemDataRole.UserRole + 1),
        )

    def _open_path_in_best_viewer(self, path):
        """Open a file in whichever built-in viewer matches its extension, else xdg-open."""
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp'):
            self.preview_in_image_viewer(path)
        elif ext == '.pdf':
            self.preview_in_pdf_viewer(path)
        elif ext == '.md':
            self._open_markdown_file(path)
        # .html/.htm default into the code editor now (see _CODE_ROUTE_EXTENSIONS) — local
        # files open in the editor, only URLs open in the web viewer.
        elif ext in self._CODE_ROUTE_EXTENSIONS:
            self._open_code_file_in_editor(path)
        else:
            subprocess.Popen(["xdg-open", path], start_new_session=True)

    def _handle_launcher_folder_item_activation(self, path, item_type):
        """Open/navigate an entry from the launcher-column quick file-browser panel.

        Unlike the main folder browser's default click (_handle_folder_item_activation),
        files always route into the best built-in viewer — that's the point of this panel.
        """
        if not path:
            return
        if item_type == "dir":
            projectflow_path = os.path.join(path, ".projectflow")
            if os.path.exists(projectflow_path):
                self.switch_to_config(projectflow_path)
            else:
                self.populate_folder_browser(path)
        else:
            self._open_path_in_best_viewer(path)

    def on_launcher_folder_item_clicked(self, item, column):
        """Handle single-click in the launcher-column quick file-browser panel"""
        self._handle_launcher_folder_item_activation(
            item.data(0, Qt.ItemDataRole.UserRole),
            item.data(0, Qt.ItemDataRole.UserRole + 1),
        )

    def launcher_folder_browser_context_menu(self, position):
        """Handle right-click in the launcher-column quick file-browser panel"""
        item = self.launcher_folder_browser.itemAt(position)
        if not item:
            self._build_folder_background_context_menu(self.folder_current_path).exec(
                self.launcher_folder_browser.mapToGlobal(position))
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if not path:
            return
        self._build_folder_context_menu(path, item_type).exec(self.launcher_folder_browser.mapToGlobal(position))

    def on_launcher_folder_icon_item_clicked(self, item):
        """Handle single-click in the launcher-column mini panel's icon-grid view"""
        self._handle_launcher_folder_item_activation(
            item.data(Qt.ItemDataRole.UserRole),
            item.data(Qt.ItemDataRole.UserRole + 1),
        )

    def launcher_folder_icon_view_context_menu(self, position):
        """Handle right-click in the launcher-column mini panel's icon-grid view"""
        item = self.launcher_folder_icon_view.itemAt(position)
        if not item:
            self._build_folder_background_context_menu(self.folder_current_path).exec(
                self.launcher_folder_icon_view.mapToGlobal(position))
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        item_type = item.data(Qt.ItemDataRole.UserRole + 1)
        if not path:
            return
        self._build_folder_context_menu(path, item_type).exec(self.launcher_folder_icon_view.mapToGlobal(position))

    def _open_file_in_webview(self, path):
        """Open a local HTML file in the built-in webview panel — always opens as a new tab
        (see _open_web_tab()), even if the same file is already open in another tab."""
        if not self.webview:
            return
        self._open_web_tab("html_file", path)

    def _open_markdown_in_webview(self, path):
        """Open a markdown file — defaults to the live, auto-saving Muya editor. Always
        opens as a new tab (see _open_web_tab()); _open_markdown_in_muya_editor() itself
        stays tab-agnostic (just loads content into the current tab) since it's also used
        internally by _activate_web_tab() and the Edit/Preview toggle buttons to reload
        whatever's already the active tab, not to open a new one."""
        self._open_web_tab("markdown", path)

    def _open_markdown_file(self, path):
        """Layout-aware entry point for "open this markdown file" actions — used by every
        click-routing call site instead of calling _open_markdown_in_webview() directly.
        Focus layout consolidates all notes (project's own or otherwise) onto the Notes tab
        (_open_note_in_notes_tab()); Standard layout is unchanged, since its Notes column is
        a fixed pane that can only ever show the project's own note (see CLAUDE.md)."""
        if self.layout_mode == "focus":
            self._open_note_in_notes_tab(path)
        else:
            self._open_markdown_in_webview(path)

    def _open_markdown_preview(self, path):
        """Render a markdown file as themed, read-only HTML in the built-in webview panel"""
        if not self.webview:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except OSError:
            return

        import re
        from PyQt6.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setMarkdown(content)
        full_html = doc.toHtml()
        body_match = re.search(r'<body[^>]*>(.*)</body>', full_html, re.DOTALL | re.IGNORECASE)
        body_html = body_match.group(1).strip() if body_match else full_html

        bg = self.t('bg_primary')
        fg = self.t('fg_primary')
        border = self.t('border')
        bg2 = self.t('bg_secondary')
        fg2 = self.t('fg_secondary')
        styled = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ background:{bg}; color:{fg}; font-family:sans-serif;
       max-width:860px; margin:30px auto; padding:0 24px; line-height:1.7; font-size:14px; }}
h1,h2,h3,h4 {{ border-bottom:1px solid {border}; padding-bottom:4px; margin-top:1.4em; }}
code {{ background:{bg2}; padding:2px 5px; border-radius:3px; font-size:0.88em; font-family:monospace; }}
pre  {{ background:{bg2}; padding:12px; border-radius:5px; overflow-x:auto; }}
pre code {{ background:none; padding:0; }}
a {{ color:#5b9bd5; }}
blockquote {{ border-left:3px solid {border}; margin-left:0; padding-left:16px; color:{fg2}; }}
</style></head>
<body>{body_html}</body></html>"""

        if self.column2_mode != "webview":
            self.switch_to_viewer_mode("webview")
        self.webview_md_path = path
        self._muya_session.editing = False
        self.webview.setHtml(styled, QUrl.fromLocalFile(path))
        self._update_md_edit_buttons()

    def _on_muya_webview_load_finished(self, ok, session):
        """Fires for every navigation of a Muya-hosting webview. Injects pending content once loaded."""
        if ok and session.pending_markdown is not None:
            js = f"window.__initMuya({json.dumps(session.pending_markdown)})"
            session.webview.page().runJavaScript(js)
            session.pending_markdown = None

    def _load_muya_shell(self, session, path, content, extra_css=""):
        """Load the Muya editor shell into session.webview with the given content, targeting
        path as the save destination. Shared by the file-backed and notes-backed openers below.
        extra_css is injected verbatim into the shell's <style> block (used for the Notes-view
        paper effect; empty for the plain file editor)."""
        if not session.webview:
            return
        editor_dir = os.path.join(self.script_dir, "assets", "muya")
        editor_html = os.path.join(editor_dir, "editor.html")
        if not os.path.exists(editor_html):
            self.status_label.setText("✗ Muya editor assets not found")
            return

        with open(editor_html, 'r', encoding='utf-8') as f:
            shell_html = f.read()
        shell_html = (
            shell_html.replace('__PF_BG__', self.t('bg_primary'))
            .replace('__PF_FG__', self.t('fg_primary'))
            .replace('__PF_EXTRA_CSS__', extra_css)
        )

        session.path = path
        session.editing = True
        session.pending_markdown = content
        session.webview.setHtml(shell_html, QUrl.fromLocalFile(editor_dir + os.sep))
        if not session.autosave_timer.isActive():
            session.autosave_timer.start()

    def _open_path_in_muya_session(self, session, path, extra_css=""):
        """Load a markdown file into the given MuyaSession's webview and start autosaving it."""
        if not path or not session.webview:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except OSError as e:
            self.status_label.setText(f"✗ Could not open {os.path.basename(path)}: {e}")
            return
        self._load_muya_shell(session, path, content, extra_css=extra_css)

    def _notes_paper_css(self):
        """CSS for the 'paper on page' look — a Typora/Documentary-style paper card floating
        on a tinted page background, with a drop shadow. Used both for the Notes panel and
        the general Muya markdown-file viewer (e.g. clicking a Documentation launcher item).
        Light mode uses the user's own Documentary Typora theme colors; dark mode uses their
        specified dark palette. Paper opacity is higher in Standard layout's narrower
        3-column view (90%) than in Focus layout's wider 2-column one (80%)."""
        alpha = 0.80 if self.layout_mode == "focus" else 0.90
        if self.current_theme == "dark":
            page_bg = "#141414"
            paper_rgb = "54, 59, 64"       # #363B40
            ink = "#DEDEDE"
            shadow = "0 18px 46px rgba(0, 0, 0, 0.55)"
            border = "1px solid rgba(255, 255, 255, 0.06)"
        else:
            page_bg = "rgb(229, 231, 237)"
            paper_rgb = "240, 240, 240"    # matches documentary.css --paper base
            ink = "#263241"
            shadow = "0 18px 46px rgba(57, 67, 84, 0.12)"
            border = "1px solid rgba(255, 255, 255, 0.42)"
        return f"""
            body {{ background: {page_bg}; color: {ink}; overflow-x: hidden; }}
            #editor {{
                box-sizing: border-box;
                width: 90%;
                background: rgba({paper_rgb}, {alpha});
                margin: 24px auto 48px;
                border-radius: 8px;
                box-shadow: {shadow};
                border: {border};
            }}
        """

    def create_notes_toolbar(self, parent_layout):
        """Create the Focus-layout Notes panel's toolbar: a filename label (blank when
        showing the project's own note, so it's never ambiguous which note is on screen),
        a "📂 Open" file picker for arbitrary notes, and a "🏠 Project Note" button (visible
        only when viewing something else) to jump back. Mirrors create_code_editor_toolbar()'s
        shape/style."""
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 5)
        toolbar_layout.setSpacing(5)

        btn_style = f"""
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
            QPushButton:pressed {{
                background-color: {self.t('bg_category_hover')};
            }}
        """

        self.notes_open_btn = QPushButton(" Open")
        self.notes_open_btn.setIcon(self._open_icon())
        self.notes_open_btn.setIconSize(QSize(16, 16))
        self.notes_open_btn.setStyleSheet(btn_style)
        self.notes_open_btn.setToolTip("Open a note in the Notes tab")
        self.notes_open_btn.clicked.connect(self.open_note_file)
        toolbar_layout.addWidget(self.notes_open_btn)

        self.notes_current_label = QLabel("")
        self.notes_current_label.setStyleSheet(f"color: {self.t('fg_primary')}; font-weight: bold; margin-right: 5px;")
        toolbar_layout.addWidget(self.notes_current_label)

        toolbar_layout.addStretch()

        self.notes_home_btn = QPushButton("🏠 Project Note")
        self.notes_home_btn.setStyleSheet(btn_style)
        self.notes_home_btn.setToolTip("Back to this project's own note")
        self.notes_home_btn.clicked.connect(self._navigate_notes_home)
        toolbar_layout.addWidget(self.notes_home_btn)

        parent_layout.addWidget(toolbar_widget)
        self._build_notes_tab_strip(parent_layout)
        self._update_notes_toolbar()

    def open_note_file(self):
        """Notes toolbar "📂 Open" button: file picker for opening an arbitrary note, not
        just the project's own — mirrors open_code_file()'s pattern."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Note", os.path.expanduser("~"), "Markdown Files (*.md);;All Files (*)"
        )
        if file_path:
            self._open_note_in_notes_tab(file_path)

    def _update_notes_toolbar(self):
        """Refreshes the Notes toolbar's filename label and Project-Note button visibility
        to reflect self.notes_md_path. No-op if the toolbar doesn't exist (Standard layout,
        or not yet built)."""
        if not self.notes_current_label:
            return
        is_project_note = not self.notes_md_path
        label_text = f"{self.get_project_name()} project notes" if is_project_note else os.path.basename(self.notes_md_path)
        self.notes_current_label.setText(label_text)
        self.notes_home_btn.setVisible(not is_project_note)
        if getattr(self, 'notes_archive_section', None):
            self.notes_archive_section.setVisible(is_project_note)

    def _open_notes_in_muya(self):
        """Load the current project's notes into the persistent Notes-panel Muya session —
        UNLESS an arbitrary other note has been explicitly loaded (self.notes_md_path set,
        see _open_note_in_notes_tab()), in which case that one is (re)loaded instead. This
        is what makes the Notes tab "always shows the project note if another note not
        loaded" — notes_md_path is only ever reset in switch_to_config(), so it survives
        incidental refreshes (editing a launcher, toggling theme) and only resets on an
        actual project switch.

        The project-note branch sources content from self.notes_data (already read by
        load_notes()) rather than re-reading the file, since the notes file may not exist
        yet for a brand-new project; the arbitrary-note branch reads from disk via the same
        _open_path_in_muya_session() the general webview uses — it's already generic over
        which MuyaSession it targets."""
        if self.notes_md_path and self.notes_md_path != self.get_notes_file_path():
            self._open_path_in_muya_session(self._notes_muya_session, self.notes_md_path, extra_css=self._notes_paper_css())
        else:
            content = self.notes_data.get("content", "") if self.notes_data else ""
            self._load_muya_shell(
                self._notes_muya_session, self.get_notes_file_path(), content,
                extra_css=self._notes_paper_css()
            )
        self._update_notes_toolbar()

    def _notes_tab_title(self, tab):
        """Short display label for one Notes tab's strip button."""
        return "Project Note" if tab.path is None else os.path.basename(tab.path)

    def _activate_notes_tab(self, index):
        """Make self.notes_tabs[index] the active tab. Flushes any unsaved content in the
        CURRENTLY displayed note first (see _muya_flush_before_switch()) — without this,
        switching tabs faster than the ~1.2s autosave poll silently dropped the last few
        seconds of edits, since _open_notes_in_muya() below replaces the page outright."""
        self._muya_flush_before_switch(self._notes_muya_session, lambda: self._do_activate_notes_tab(index))

    def _do_activate_notes_tab(self, index):
        """The actual tab switch, once any previous note's content has been safely flushed.
        Syncs the notes_md_path proxy (read by _open_notes_in_muya()'s existing dispatch,
        unchanged) and refreshes the tab strip. Deliberately does NOT touch column2_mode —
        callers that need to switch into the Notes viewer (_open_notes_tab()) do that
        themselves before calling _activate_notes_tab(), matching how the pre-tab
        _open_note_in_notes_tab() already ordered these two steps; calling
        switch_to_viewer_mode() from here would also be unsafe during the initial
        build_main_content() restore, which calls this before the rest of column2_stack
        necessarily exists yet."""
        self.notes_active_index = index
        self.notes_md_path = self.notes_tabs[index].path
        self._open_notes_in_muya()
        self._rebuild_notes_tab_strip()

    def _open_notes_tab(self, path):
        """Open `path` as a new Notes tab and make it active — always-new-tab policy,
        mirroring _open_pdf_tab()/_open_web_tab(). `path` equal to the project's own note
        path is normalized to None (the NotesTabState convention), same as the old
        _open_note_in_notes_tab() did."""
        normalized = path if path != self.get_notes_file_path() else None
        self.notes_tabs.append(NotesTabState(normalized))
        if self.column2_mode != "notes":
            self.switch_to_viewer_mode("notes")
        self._activate_notes_tab(len(self.notes_tabs) - 1)
        self.save_notes()

    def _open_note_in_notes_tab(self, path):
        """Open any .md file in the Focus-layout Notes tab (the consolidated note viewer) —
        stable public entry point used by every "open a markdown file" call site in Focus
        layout (see _open_markdown_file()). Always opens as a new tab (see
        _open_notes_tab()) — the "🏠 Project Note" button uses _navigate_notes_home()
        instead, which navigates the current tab in place rather than opening a new one."""
        self._open_notes_tab(path)

    def _navigate_notes_home(self):
        """"🏠 Project Note" button: navigate the CURRENT tab back to the project's own note
        in place, rather than opening a new tab — mirrors webview_home()'s in-place
        navigation vs. _open_web_tab()'s always-new-tab for launcher clicks."""
        if 0 <= self.notes_active_index < len(self.notes_tabs):
            self.notes_tabs[self.notes_active_index].path = None
            self._activate_notes_tab(self.notes_active_index)
            self.save_notes()
        else:
            self._open_notes_tab(self.get_notes_file_path())

    def _close_notes_tab(self, index):
        """Close and discard the Notes tab at `index`, picking a sensible new active tab.
        Unlike PDF/Image/Web, Notes must never end up with zero tabs — it always falls back
        to showing the project's own note — so closing the last tab recreates a fresh
        project-note tab instead of leaving an empty state."""
        if not (0 <= index < len(self.notes_tabs)):
            return
        closing_active = (index == self.notes_active_index)
        self.notes_tabs.pop(index)
        if not self.notes_tabs:
            self.notes_tabs.append(NotesTabState(None))
            self._activate_notes_tab(0)
        elif closing_active:
            self._activate_notes_tab(min(index, len(self.notes_tabs) - 1))
        else:
            if index < self.notes_active_index:
                self.notes_active_index -= 1
            self._rebuild_notes_tab_strip()
        self.save_notes()

    def _close_all_notes_tabs(self):
        """Close every open Notes tab down to just the project's own note. Can't use a plain
        `while self.notes_tabs:` loop — _close_notes_tab() deliberately re-appends a fresh
        project-note tab whenever the list would otherwise go to zero, so that would never
        terminate. Instead close down to the last one, then close that one too — which
        triggers the same "recreate the project note" fallback, landing on the intended end
        state (exactly one tab: the project's own note) rather than zero."""
        while len(self.notes_tabs) > 1:
            self._close_notes_tab(0)
        if self.notes_tabs:
            self._close_notes_tab(0)

    def _build_notes_tab_strip(self, parent_layout):
        """Build the row of Notes tab buttons — mirrors _build_pdf_tab_strip(). Focus
        layout only (called from create_notes_toolbar(), itself Focus-layout-gated)."""
        self.notes_tab_strip_widget = QWidget()
        self.notes_tab_strip_layout = QHBoxLayout(self.notes_tab_strip_widget)
        self.notes_tab_strip_layout.setContentsMargins(0, 0, 0, 4)
        self.notes_tab_strip_layout.setSpacing(2)
        parent_layout.addWidget(self.notes_tab_strip_widget)
        self._rebuild_notes_tab_strip()

    def _rebuild_notes_tab_strip(self):
        """Clear and repopulate self.notes_tab_strip_layout from self.notes_tabs — mirrors
        _rebuild_pdf_tab_strip(). A no-op in Standard layout, where the strip is never built
        (guarded by the getattr check, same as the other tab strips)."""
        if getattr(self, 'notes_tab_strip_layout', None) is None:
            return
        while self.notes_tab_strip_layout.count():
            item = self.notes_tab_strip_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # Only worth showing once there's more than the trivial single project-note tab —
        # otherwise it's a permanent, always-visible single button doing nothing useful.
        self.notes_tab_strip_widget.setVisible(len(self.notes_tabs) > 1)
        for i, tab in enumerate(self.notes_tabs):
            is_active = (i == self.notes_active_index)
            group = self._build_tab_group_widget(
                self._notes_tab_title(tab), tab.path or "This project's own note",
                self._viewer_tab_button_style(is_active),
                lambda checked=False, idx=i: self._activate_notes_tab(idx),
                lambda checked=False, idx=i: self._close_notes_tab(idx),
            )
            self.notes_tab_strip_layout.addWidget(group)
        self.notes_tab_strip_layout.addStretch()
        if len(self.notes_tabs) > 1:
            self.notes_tab_strip_layout.addWidget(
                self._build_close_all_tabs_button(lambda checked=False: self._close_all_notes_tabs())
            )

    def _open_markdown_in_muya_editor(self, path=None):
        """Switch the main webview into the Muya WYSIWYG markdown editor for the given file."""
        path = path or self.webview_md_path
        if not path or not self.webview:
            return
        if self.column2_mode != "webview":
            self.switch_to_viewer_mode("webview")
        self.webview_md_path = path
        self._open_path_in_muya_session(self._muya_session, path, extra_css=self._notes_paper_css())
        self._update_md_edit_buttons()

    def _muya_autosave_tick(self, session):
        """Runs every ~1.2s while editing; saves the file if the editor reports unsaved changes."""
        if not session.editing or not session.webview:
            session.autosave_timer.stop()
            return

        def on_dirty(is_dirty):
            if is_dirty:
                self._muya_save(session)

        session.webview.page().runJavaScript(
            "window.__muyaIsDirty ? window.__muyaIsDirty() : false", on_dirty
        )

    def _muya_save(self, session):
        """Pull the current markdown out of the given MuyaSession's editor and write it to disk."""
        if not session.editing or not session.path or not session.webview:
            return

        def on_markdown(markdown):
            if markdown is None:
                self.status_label.setText("✗ Autosave failed: no content from editor")
                return
            try:
                with open(session.path, 'w', encoding='utf-8') as f:
                    f.write(markdown)
                session.webview.page().runJavaScript("window.__muyaClearDirty && window.__muyaClearDirty()")
                self.status_label.setText(f"✓ Autosaved {os.path.basename(session.path)}")
                self.status_label.setStyleSheet("color: #27ae60; margin: 10px;")
            except OSError as e:
                self.status_label.setText(f"✗ Autosave failed: {e}")

        session.webview.page().runJavaScript("window.__getMuyaMarkdown ? window.__getMuyaMarkdown() : null", on_markdown)

    def _muya_flush_before_switch(self, session, callback):
        """If `session` currently has unsaved changes, force-write them to disk BEFORE
        `callback` runs — used before switching Notes/Web-markdown tabs (or closing one),
        where the target content is about to replace the page via setHtml(), which
        otherwise races with (and can silently lose) a pending autosave: the autosave timer
        only polls every ~1.2s, so switching tabs faster than that — easy to do right after
        typing — discarded the last few seconds of edits with no save ever happening. Always
        calls `callback` exactly once, whether or not anything needed saving."""
        if not (session.editing and session.path and session.webview):
            callback()
            return

        def on_dirty(is_dirty):
            if not is_dirty:
                callback()
                return

            def on_markdown(markdown):
                if markdown is not None:
                    try:
                        with open(session.path, 'w', encoding='utf-8') as f:
                            f.write(markdown)
                    except OSError as e:
                        self.status_label.setText(f"✗ Autosave failed: {e}")
                callback()

            session.webview.page().runJavaScript("window.__getMuyaMarkdown ? window.__getMuyaMarkdown() : null", on_markdown)

        session.webview.page().runJavaScript("window.__muyaIsDirty ? window.__muyaIsDirty() : false", on_dirty)

    def _muya_switch_to_preview(self):
        """Leave the main webview's Muya editor (autosaving first) and show the rendered read-only preview."""
        session = self._muya_session
        if not session.path or not session.webview:
            return
        path = session.path
        session.autosave_timer.stop()

        def on_markdown(markdown):
            if markdown:
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(markdown)
                except OSError as e:
                    self.status_label.setText(f"✗ Autosave failed: {e}")
            session.editing = False
            session.path = None
            self._open_markdown_preview(path)

        session.webview.page().runJavaScript("window.__getMuyaMarkdown ? window.__getMuyaMarkdown() : null", on_markdown)

    def _update_md_edit_buttons(self):
        """Show Edit or Preview depending on whether a markdown file is loaded and whether we're editing it."""
        if not hasattr(self, 'md_edit_btn'):
            return
        is_md = bool(getattr(self, 'webview_md_path', None))
        self.md_edit_btn.setVisible(is_md and not self._muya_session.editing)
        self.md_preview_btn.setVisible(is_md and self._muya_session.editing)

        # "Edit Source" — visible only when the webview is showing a local .html/.htm
        # file as rendered content (not markdown-editing, not a plain URL/non-HTML file).
        if hasattr(self, 'html_source_btn'):
            is_html_rendered = False
            if not is_md and self.webview:
                url = self.webview.url()
                if url.isLocalFile():
                    ext = os.path.splitext(url.toLocalFile())[1].lower()
                    is_html_rendered = ext in ('.html', '.htm')
            self.html_source_btn.setVisible(is_html_rendered)

    def _open_html_source_from_webview(self):
        """"</> Edit Source" button: open the currently-rendered local HTML file's source
        in the internal code editor instead."""
        if not self.webview:
            return
        url = self.webview.url()
        if not url.isLocalFile():
            return
        self._open_code_file_in_editor(url.toLocalFile())

    # --- CodeMirror 6 code-editor bridge ---------------------------------------------
    # Parallel to the Muya bridge methods above, but deliberately NOT sharing a base
    # class/session type with MuyaSession — see CodeEditorSession's docstring. The one
    # method that ever writes to disk is _code_editor_save(); _code_editor_dirty_poll_tick
    # only ever reads state for the Save button's UI indicator, never writes.

    _CODE_EXT_LANGUAGE = {
        '.js': 'js', '.mjs': 'js', '.jsx': 'js', '.cjs': 'js',
        '.py': 'py', '.pyw': 'py',
        '.html': 'html', '.htm': 'html',
        '.css': 'css',
        '.php': 'php', '.phtml': 'php',
        # No dedicated CodeMirror language package is vendored for JSON (see CLAUDE.md's
        # Code Editor section) — reusing 'js' gives reasonable highlighting for free
        # (valid JSON tokenizes fine as JS object/array literals) without a bundle rebuild.
        '.json': 'js',
        # Plain text has no language extension at all (None, via .get()'s default below) —
        # basicSetup already handles that gracefully (plain text, line numbers, no
        # highlighting, never refuses to open), so .txt doesn't need an entry here.
    }
    # Extensions that route into the internal code editor by default. .html/.htm now
    # default here too (previously excluded, opening rendered in the webview instead) —
    # local FILES open in the editor, only URLs (and explicit firefox/chrome-app launcher
    # items) open in the web viewer. The "👁 Rendered" toggle in the code editor (and
    # "</> Edit Source" the other way from the webview) still exist for switching a given
    # .html file between the two views. .txt/.json are added on top of _CODE_EXT_LANGUAGE's
    # keys since they route here too despite having no language entry (plain text/JS-as-
    # JSON respectively).
    _CODE_ROUTE_EXTENSIONS = tuple(set(_CODE_EXT_LANGUAGE) | {'.txt'})

    # Cap on simultaneously-remembered Web tabs (see WebTabState) — oldest tab is closed
    # to make room once reached (_open_web_tab()). Since only one real QWebEngineView is
    # ever live regardless of tab count (switching tabs re-navigates the same one), this
    # isn't a renderer-process resource cap — it's just to keep the tab strip from growing
    # unbounded over a long session.
    WEB_TAB_CAP = 8

    def _code_editor_language_for(self, path):
        """Maps a file extension to the short language key editor.html's langMap expects,
        or None for an unrecognized extension (the editor still opens, just without a
        language extension — plain text with line numbers, never refuses to open)."""
        return self._CODE_EXT_LANGUAGE.get(os.path.splitext(path)[1].lower())

    def _code_editor_syntax_colors(self):
        """Small, hand-picked syntax-token palette (keyword/string/comment), independent
        of themes.py — same reasoning as the Notes paper theme's hand-picked colors (see
        CLAUDE.md): a 2-3 color accent scheme doesn't map cleanly onto the app's own
        background/foreground palette, so it's picked to look right in each theme instead
        of derived from it."""
        if self.current_theme == "dark":
            return {"keyword": "#ff7b72", "string": "#a5d6ff", "comment": "#8b949e"}
        return {"keyword": "#cf222e", "string": "#0a3069", "comment": "#6e7781"}

    def _load_code_editor_shell(self, session, path, content, language, initial_dirty=False):
        """Load the CodeMirror 6 editor shell into session.webview with the given content.
        initial_dirty is stashed onto session.pending_dirty and applied once loading
        actually finishes (see _on_code_editor_webview_load_finished()) — used when
        restoring an Editor tab whose cached content differs from disk (CodeMirror's own
        dirty tracking would otherwise read false, since nothing's changed since THIS init)."""
        if not session.webview:
            return
        editor_dir = os.path.join(self.script_dir, "assets", "codemirror")
        editor_html = os.path.join(editor_dir, "editor.html")
        if not os.path.exists(editor_html):
            self.status_label.setText("✗ Code editor assets not found")
            return

        with open(editor_html, 'r', encoding='utf-8') as f:
            shell_html = f.read()
        is_dark = self.current_theme == "dark"
        syntax_colors = self._code_editor_syntax_colors()
        shell_html = (
            shell_html.replace('__PF_BG__', self.t('bg_primary'))
            .replace('__PF_FG__', self.t('fg_primary'))
            .replace('__PF_FG_SECONDARY__', self.t('fg_secondary'))
            .replace('__PF_GUTTER_BG__', self.t('bg_secondary'))
            .replace('__PF_ACTIVE_LINE__', self.t('bg_secondary'))
            .replace('__PF_SELECTION__', self.t('bg_category'))
            .replace('__PF_IS_DARK__', 'true' if is_dark else 'false')
            .replace('__PF_SYNTAX_JSON__', json.dumps(syntax_colors))
            .replace('__PF_EXTRA_CSS__', '')
        )

        session.path = path
        session.language = language
        session.editing = True
        session.pending_content = content
        session.pending_dirty = initial_dirty
        session.webview.setHtml(shell_html, QUrl.fromLocalFile(editor_dir + os.sep))
        if not session.dirty_poll_timer.isActive():
            session.dirty_poll_timer.start()

    def _open_path_in_code_editor_session(self, session, path):
        """Read a file from disk and load it into the given CodeEditorSession's editor."""
        if not path or not session.webview:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except OSError as e:
            self.status_label.setText(f"✗ Could not open {os.path.basename(path)}: {e}")
            return
        language = self._code_editor_language_for(path)
        self._load_code_editor_shell(session, path, content, language)

    def _on_code_editor_webview_load_finished(self, ok, session):
        """Fires for every navigation of the code-editor webview. Injects pending content
        once loaded — mirrors _on_muya_webview_load_finished. session.dirty becomes
        session.pending_dirty (not a hardcoded False) — see _load_code_editor_shell()'s
        docstring for why a restored Editor tab's true dirty state can't be trusted to
        CodeMirror's own tracking."""
        if ok and session.pending_content is not None:
            wrap_enabled = self.settings.get('code_editor_wrap', True)
            js = f"window.__initCodeEditor({json.dumps(session.pending_content)}, {json.dumps(session.language)}, {json.dumps(wrap_enabled)})"
            session.webview.page().runJavaScript(js)
            session.pending_content = None
            session.dirty = session.pending_dirty
            self._update_code_editor_buttons()

    def _code_editor_dirty_poll_tick(self, session):
        """Runs every ~800ms while editing; refreshes the Save button's dirty indicator
        ONLY — never writes to disk (see CodeEditorSession's docstring)."""
        if not session.editing or not session.webview:
            session.dirty_poll_timer.stop()
            return

        def on_dirty(is_dirty):
            is_dirty = bool(is_dirty)
            if is_dirty != session.dirty:
                session.dirty = is_dirty
                self._update_code_editor_buttons()

        session.webview.page().runJavaScript(
            "window.__codeEditorIsDirty ? window.__codeEditorIsDirty() : false", on_dirty
        )

    def _code_editor_save(self, session):
        """The only method that ever writes code-editor content to disk. Pulls the current
        content out of the editor and writes it, only in response to an explicit user
        action (Save button / Ctrl+S) — never called from a timer."""
        if not session.editing or not session.path or not session.webview:
            return

        def on_content(content):
            if content is None:
                self.status_label.setText("✗ Save failed: no content from editor")
                return
            try:
                with open(session.path, 'w', encoding='utf-8') as f:
                    f.write(content)
                session.webview.page().runJavaScript("window.__codeEditorClearDirty && window.__codeEditorClearDirty()")
                session.dirty = False
                # Also clear the ACTIVE tab's own sticky dirty flag/cached content (see
                # CodeTabState) — session.dirty alone isn't enough once tabs exist: a tab
                # that was ever flushed while dirty (switched away from at least once) has
                # tab.dirty=True independently, and that's what the tab strip's "●" and the
                # close/discard confirmation actually check, not session.dirty. Without
                # this, a successful save kept showing "unsaved changes" for any tab that
                # had been backgrounded even once — the save genuinely worked, only the
                # tab-level bookkeeping didn't know about it.
                if 0 <= self.code_active_index < len(self.code_tabs):
                    active_tab = self.code_tabs[self.code_active_index]
                    active_tab.dirty = False
                    active_tab.pending_unsaved_content = None
                self._update_code_editor_buttons()
                self._rebuild_code_tab_strip()
                self.status_label.setText(f"✓ Saved {os.path.basename(session.path)}")
                self.status_label.setStyleSheet("color: #27ae60; margin: 10px;")
            except OSError as e:
                self.status_label.setText(f"✗ Save failed: {e}")

        session.webview.page().runJavaScript(
            "window.__getCodeEditorContent ? window.__getCodeEditorContent() : null", on_content
        )

    def _code_editor_toggle_wrap(self):
        """Toggle line-wrapping in the code editor. Flips a runtime CM6 Compartment
        (__setCodeEditorWrap in editor.html) rather than reloading the file, so it never
        touches undo history or the dirty flag. Persisted per-machine in settings, applied
        to future __initCodeEditor() calls too (see _on_code_editor_webview_load_finished)."""
        enabled = self.code_wrap_btn.isChecked() if hasattr(self, 'code_wrap_btn') else True
        self.settings['code_editor_wrap'] = enabled
        self.save_settings()
        if self._code_session.webview:
            js = f"window.__setCodeEditorWrap && window.__setCodeEditorWrap({json.dumps(enabled)})"
            self._code_session.webview.page().runJavaScript(js)

    def _confirm_discard_code_changes(self):
        """Returns True if it's safe to proceed (no dirty code file open anywhere, or the
        user confirmed discarding all of it), False if the caller should abort. Checks
        every Editor tab, not just the currently active one — with multiple tabs, a
        BACKGROUND tab can hold cached pending_unsaved_content (see CodeTabState) that the
        live session.dirty flag alone would never reveal, and that content is deliberately
        never written to disk, so this is the only place that content's loss gets flagged
        before something destroys it (app close, project switch). Uses the timer-polled
        session.dirty flag for the active tab (up to ~800ms stale) rather than a synchronous
        re-query — acceptable for a discard-confirmation on non-realtime paths, and avoids
        restructuring those call sites into async callback chains for a rare edge case."""
        session = self._code_session
        dirty_paths = []
        for i, tab in enumerate(self.code_tabs):
            is_active_live_dirty = (i == self.code_active_index and session.editing and session.dirty)
            if tab.dirty or is_active_live_dirty:
                dirty_paths.append(os.path.basename(tab.path))
        if not dirty_paths:
            return True
        if len(dirty_paths) == 1:
            message = f"'{dirty_paths[0]}' has unsaved changes. Discard them?"
        else:
            message = "These files have unsaved changes. Discard them?\n\n" + "\n".join(f"• {p}" for p in dirty_paths)
        reply = QMessageBox.question(
            self, "Unsaved Changes", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def open_code_file(self):
        """Toolbar "📂 Open" button: file picker for opening an arbitrary file in the code
        editor, not just files already referenced by the project — mirrors open_pdf_file()/
        open_image_file()'s existing QFileDialog pattern."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open File", os.path.expanduser("~"),
            "Code Files (*.js *.jsx *.mjs *.cjs *.py *.html *.htm *.css *.php *.json *.txt);;All Files (*)"
        )
        if file_path:
            self._open_code_file_in_editor(file_path)

    def _code_tab_title(self, tab):
        """Short display label for one Editor tab's strip button."""
        return os.path.basename(tab.path) or tab.path

    def _activate_code_tab(self, index):
        """Make self.code_tabs[index] the active tab. Async: if the editor currently has
        live dirty content, first flushes it out and caches it on the PREVIOUSLY active
        tab's own CodeTabState — never force-saved, never discarded, since the whole point
        of Editor tabs is that switching away from unsaved work must not require either —
        then loads the target tab (_do_activate_code_tab). Deliberately flushes even when
        `index` equals the tab already active (a theme change reloads the shell HTML from
        scratch via setHtml(), which would otherwise silently discard live-typed,
        never-flushed edits just because "switching to the same tab" sounds like a no-op)."""
        session = self._code_session
        prev_index = self.code_active_index
        if session.editing and session.dirty and session.webview and 0 <= prev_index < len(self.code_tabs):
            prev_tab = self.code_tabs[prev_index]

            def on_flushed(content):
                if content is not None:
                    prev_tab.pending_unsaved_content = content
                    prev_tab.dirty = True
                self._do_activate_code_tab(index)

            session.webview.page().runJavaScript(
                "window.__getCodeEditorContent ? window.__getCodeEditorContent() : null", on_flushed
            )
        else:
            self._do_activate_code_tab(index)

    def _do_activate_code_tab(self, index):
        """The actual tab switch, once any previous tab's content has been safely flushed
        (see _activate_code_tab()). Uses the tab's cached pending_unsaved_content if it has
        any, else reads fresh from disk."""
        self.code_active_index = index
        tab = self.code_tabs[index]
        if tab.pending_unsaved_content is not None:
            content = tab.pending_unsaved_content
        else:
            try:
                with open(os.path.expanduser(tab.path), 'r', encoding='utf-8') as f:
                    content = f.read()
            except OSError as e:
                self.status_label.setText(f"✗ Could not open {os.path.basename(tab.path)}: {e}")
                content = ""
        self._load_code_editor_shell(self._code_session, tab.path, content, tab.language, initial_dirty=tab.dirty)
        self._rebuild_code_tab_strip()
        self._update_code_editor_buttons()

    def _open_code_tab(self, path):
        """Open `path` as a new Editor tab and make it active — always-new-tab policy,
        mirroring _open_pdf_tab()/_open_web_tab()/_open_notes_tab(). Unlike the pre-tab
        _open_code_file_in_editor(), opening a different file while the current tab has
        unsaved changes no longer needs a discard confirmation — that tab's content gets
        cached instead of destroyed (see _activate_code_tab())."""
        language = self._code_editor_language_for(path)
        self.code_tabs.append(CodeTabState(path, language))
        if self.column2_mode != "code":
            self.switch_to_viewer_mode("code")
        self._activate_code_tab(len(self.code_tabs) - 1)
        self.save_notes()

    def _close_code_tab(self, index):
        """Close the Editor tab at `index`. Unlike PDF/Image/Web/Notes tabs, this is the one
        place actual unsaved work really could be lost (the Python-cached
        pending_unsaved_content is never written to disk) — so closing a dirty tab asks for
        confirmation, same wording as the pre-tab _confirm_discard_code_changes()."""
        if not (0 <= index < len(self.code_tabs)):
            return
        tab = self.code_tabs[index]
        is_active = (index == self.code_active_index)
        tab_is_dirty = tab.dirty or (is_active and self._code_session.dirty)
        if tab_is_dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                f"'{os.path.basename(tab.path)}' has unsaved changes. Discard them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.code_tabs.pop(index)
        if not self.code_tabs:
            self.code_active_index = -1
            self._code_session.editing = False
            self._code_session.path = None
            self._code_session.language = None
            self._code_session.pending_content = None
            self._code_session.dirty = False
            self._code_session.dirty_poll_timer.stop()
            self._rebuild_code_tab_strip()
            self._update_code_editor_buttons()
        elif is_active:
            self._activate_code_tab(min(index, len(self.code_tabs) - 1))
        else:
            if index < self.code_active_index:
                self.code_active_index -= 1
            self._rebuild_code_tab_strip()
        self.save_notes()

    def _close_all_code_tabs(self):
        """Close every open Editor tab. Unlike the other four tab types, _close_code_tab()
        can genuinely refuse to close (a dirty tab's discard confirmation) and returns
        without popping it if the user clicks No — so a plain `while self.code_tabs:` loop
        would spin forever reprocessing the same declined tab. Stop as soon as an attempt
        doesn't actually shrink the list, leaving that tab (and any after it) open rather
        than looping or silently skipping."""
        while self.code_tabs:
            before = len(self.code_tabs)
            self._close_code_tab(0)
            if len(self.code_tabs) == before:
                break

    def _build_code_tab_strip(self, parent_layout):
        """Build the row of Editor tab buttons — mirrors _build_pdf_tab_strip()."""
        self.code_tab_strip_widget = QWidget()
        self.code_tab_strip_layout = QHBoxLayout(self.code_tab_strip_widget)
        self.code_tab_strip_layout.setContentsMargins(0, 0, 0, 4)
        self.code_tab_strip_layout.setSpacing(2)
        parent_layout.addWidget(self.code_tab_strip_widget)
        self._rebuild_code_tab_strip()

    def _rebuild_code_tab_strip(self):
        """Clear and repopulate self.code_tab_strip_layout from self.code_tabs — mirrors
        _rebuild_pdf_tab_strip()."""
        if getattr(self, 'code_tab_strip_layout', None) is None:
            return
        while self.code_tab_strip_layout.count():
            item = self.code_tab_strip_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self.code_tab_strip_widget.setVisible(bool(self.code_tabs))
        for i, tab in enumerate(self.code_tabs):
            is_active = (i == self.code_active_index)
            label = self._code_tab_title(tab)
            if tab.dirty or (is_active and self._code_session.dirty):
                label += " ●"
            group = self._build_tab_group_widget(
                label, tab.path,
                self._viewer_tab_button_style(is_active),
                lambda checked=False, idx=i: self._activate_code_tab(idx),
                lambda checked=False, idx=i: self._close_code_tab(idx),
            )
            self.code_tab_strip_layout.addWidget(group)
        self.code_tab_strip_layout.addStretch()
        if len(self.code_tabs) > 1:
            self.code_tab_strip_layout.addWidget(
                self._build_close_all_tabs_button(lambda checked=False: self._close_all_code_tabs())
            )

    def _open_code_file_in_editor(self, path=None):
        """Stable public entry point for opening a file in the internal code editor — used
        by all click-routing call sites. Always opens as a new tab (see _open_code_tab());
        no discard-guard needed anymore since opening a different file no longer destroys
        the current tab's unsaved content (it's cached, see _activate_code_tab())."""
        path = path or self._code_session.path
        if not path:
            return
        self._open_code_tab(path)

    def _update_code_editor_buttons(self):
        """Refreshes the Save button's label/enabled-state and the filename/language label
        to reflect the current CodeEditorSession — mirrors _update_md_edit_buttons."""
        session = self._code_session
        if hasattr(self, 'code_save_btn'):
            if session.dirty:
                self.code_save_btn.setText("💾 Save (unsaved changes)")
            else:
                self.code_save_btn.setText("💾 Save")
            self.code_save_btn.setEnabled(bool(session.editing and session.path))
        if hasattr(self, 'code_filename_label'):
            self.code_filename_label.setText(os.path.basename(session.path) if session.path else "")
        if hasattr(self, 'code_source_toggle_btn'):
            is_html = bool(session.path) and os.path.splitext(session.path)[1].lower() in ('.html', '.htm')
            self.code_source_toggle_btn.setVisible(is_html)

    def _code_editor_switch_to_rendered(self):
        """"👁 Rendered" button: leave the code editor for the currently-open .html/.htm
        file and show the rendered read-only preview instead — the counterpart to the
        webview toolbar's "</> Edit Source" button. Guards on unsaved changes first."""
        session = self._code_session
        if not session.path:
            return
        path = session.path
        if session.dirty and not self._confirm_discard_code_changes():
            return
        session.editing = False
        session.dirty = False
        session.dirty_poll_timer.stop()
        # Remove this tab from the Editor tab strip — it's no longer "open in the editor",
        # it's now showing rendered in the Web viewer instead.
        if 0 <= self.code_active_index < len(self.code_tabs):
            self.code_tabs.pop(self.code_active_index)
            self.code_active_index = min(self.code_active_index, len(self.code_tabs) - 1) if self.code_tabs else -1
            self._rebuild_code_tab_strip()
            self.save_notes()
        self._open_file_in_webview(path)

    def open_code_file_in_external_editor(self):
        """Footer "Open in {editor}" button — opens the currently-open file (as it exists
        on disk) in the configured external editor, matching the equivalent footer button
        on every other viewer (PDF/image/folder/webview). Doesn't touch the internal
        editor's own unsaved state either way — it just opens a separate external window."""
        path = self._code_session.path
        if not path or not os.path.exists(path):
            return
        editor = self.get_configured_editor()
        subprocess.Popen([editor, path], start_new_session=True)

    def _build_folder_context_menu(self, path, item_type):
        """Build the right-click menu for a folder-browser entry — shared by the tree and icon views."""
        menu = QMenu(self)

        # Add to Project action
        add_action = menu.addAction("Add to Project...")
        add_action.triggered.connect(lambda: self.show_add_to_project_dialog(path))

        # Add to Documentation action (files only)
        if item_type != "dir":
            doc_action = menu.addAction("Add to Documentation...")
            doc_action.triggered.connect(lambda: self.show_add_to_documentation_dialog(path))

        # For directories: Make Project or Open Project
        if item_type == "dir":
            projectflow_path = os.path.join(path, ".projectflow")
            if os.path.exists(projectflow_path):
                project_action = menu.addAction("Open as Project")
                project_action.triggered.connect(lambda: self.switch_to_config(projectflow_path))
            else:
                project_action = menu.addAction("Make Project")
                project_action.triggered.connect(lambda checked, p=path: self.folder_make_project_at(p))

        menu.addSeparator()

        # Open action
        open_action = menu.addAction("Open")
        open_action.triggered.connect(lambda: self._handle_folder_item_activation(path, item_type))

        # Open in a specific built-in viewer (files only, when a matching viewer exists)
        if item_type == "file":
            ext = os.path.splitext(path)[1].lower()
            if ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp'):
                viewer_action = menu.addAction("🖼️ Open in Image Viewer")
                viewer_action.triggered.connect(lambda: self.preview_in_image_viewer(path))
            elif ext == '.pdf':
                viewer_action = menu.addAction("📄 Open in PDF Viewer")
                viewer_action.triggered.connect(lambda: self.preview_in_pdf_viewer(path))
            elif ext == '.md':
                viewer_action = menu.addAction("📝 Open in Markdown Editor")
                viewer_action.triggered.connect(lambda: self._open_markdown_file(path))
            elif ext in ('.html', '.htm'):
                viewer_action = menu.addAction("🌐 Open in Web Viewer")
                viewer_action.triggered.connect(lambda: self._open_file_in_webview(path))

        # Open in Terminal (for directories only)
        if item_type == "dir":
            terminal_action = menu.addAction("Open in Terminal")
            terminal_action.triggered.connect(lambda: subprocess.Popen(
                self._get_terminal_workdir_command(path), start_new_session=True))

        return menu

    def _get_templates_folder(self):
        """Resolve the freedesktop Templates folder (XDG_TEMPLATES_DIR) — the same folder
        Dolphin/Nautilus's "Create New" reads. Checks ~/.config/user-dirs.dirs for a user
        override (handles renamed/localized folders), falling back to ~/Templates."""
        user_dirs_file = os.path.expanduser("~/.config/user-dirs.dirs")
        if os.path.exists(user_dirs_file):
            try:
                with open(user_dirs_file) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("XDG_TEMPLATES_DIR="):
                            value = line.split("=", 1)[1].strip().strip('"')
                            return os.path.expanduser(value.replace("$HOME", "~"))
            except OSError:
                pass
        return os.path.expanduser("~/Templates")

    def _resolve_desktop_template(self, desktop_path):
        """Parse a KDE/Dolphin-style Type=Link template .desktop file (Name=/URL=, URL
        resolved relative to the .desktop file's own directory). Returns (label,
        source_path), or (None, None) if it isn't a Link template (e.g. a stray launcher
        .desktop someone dropped into Templates, not an actual template wrapper)."""
        import configparser
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(desktop_path, encoding='utf-8')
        except configparser.Error:
            return None, None
        if not parser.has_section('Desktop Entry'):
            return None, None
        section = parser['Desktop Entry']
        if section.get('Type') != 'Link' or not section.get('URL'):
            return None, None
        url = section.get('URL')
        source = url if os.path.isabs(url) else os.path.join(os.path.dirname(desktop_path), url)
        return section.get('Name') or os.path.splitext(os.path.basename(desktop_path))[0], source

    def _get_template_entries(self):
        """Scan the Templates folder into {'label', 'source_path', 'kind': 'file'|'dir'}
        dicts for the "New from Template" background menu — plain files/folders copied
        as-is (the simple freedesktop/Nautilus convention), plus KDE/Dolphin '.desktop'
        Type=Link wrappers resolved to their real target via _resolve_desktop_template()."""
        templates_dir = self._get_templates_folder()
        if not os.path.isdir(templates_dir):
            return []
        entries = []
        for name in sorted(os.listdir(templates_dir), key=str.lower):
            if name.startswith('.'):
                continue
            full_path = os.path.join(templates_dir, name)
            if os.path.isdir(full_path):
                entries.append({'label': name, 'source_path': full_path, 'kind': 'dir'})
            elif name.lower().endswith('.desktop'):
                label, source = self._resolve_desktop_template(full_path)
                if source:
                    entries.append({'label': label, 'source_path': source, 'kind': 'file'})
            else:
                entries.append({'label': name, 'source_path': full_path, 'kind': 'file'})
        return entries

    def _build_folder_background_context_menu(self, target_dir):
        """Right-click menu for empty space in a folder-browser view (no item under the
        cursor) — currently just "New from Template", shared by all four folder-browsing
        view widgets (main tree/icons, launcher-panel tree/icons)."""
        menu = QMenu(self)
        entries = self._get_template_entries()
        template_menu = menu.addMenu("New from Template")
        if not entries:
            placeholder = template_menu.addAction("No templates found")
            placeholder.setEnabled(False)
        for entry in entries:
            icon = self._folder_theme_icon() if entry['kind'] == 'dir' else QIcon()
            action = template_menu.addAction(icon, entry['label'])
            action.triggered.connect(
                lambda checked=False, e=entry: self._create_from_template(e, target_dir)
            )
        return menu

    def _create_from_template(self, entry, target_dir):
        """Copy a template file/folder into target_dir, prompting for a name first. Files:
        the copy is renamed (contents untouched) — e.g. accept 'markdown.md' as-is or
        rename to 'note.md'. Folders: only the resulting folder's name is chosen; contents
        are copied recursively as-is. Mirrors new_project()'s QInputDialog + collision-check
        + shutil.copy2 pattern."""
        from PyQt6.QtWidgets import QInputDialog

        default_name = os.path.basename(entry['source_path'].rstrip('/'))
        prompt = "Folder name:" if entry['kind'] == 'dir' else "File name:"
        new_name, ok = QInputDialog.getText(self, "New from Template", prompt, text=default_name)
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        dest_path = os.path.join(target_dir, new_name)
        if os.path.exists(dest_path):
            QMessageBox.warning(self, "Already Exists", f'"{new_name}" already exists in this folder.')
            return
        try:
            if entry['kind'] == 'dir':
                shutil.copytree(entry['source_path'], dest_path)
            else:
                shutil.copy2(entry['source_path'], dest_path)
        except (OSError, shutil.Error) as e:
            QMessageBox.warning(self, "Error", f"Failed to create from template: {e}")
            return
        self.folder_refresh()

    def folder_browser_context_menu(self, position):
        """Handle right-click context menu in the tree-view folder browser"""
        item = self.folder_browser.itemAt(position)
        if not item:
            self._build_folder_background_context_menu(self.folder_current_path).exec(
                self.folder_browser.mapToGlobal(position))
            return

        path = item.data(0, Qt.ItemDataRole.UserRole)
        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if not path:
            return

        self._build_folder_context_menu(path, item_type).exec(self.folder_browser.mapToGlobal(position))

    def folder_icon_view_context_menu(self, position):
        """Handle right-click context menu in the icon-grid folder browser"""
        item = self.folder_icon_view.itemAt(position)
        if not item:
            self._build_folder_background_context_menu(self.folder_current_path).exec(
                self.folder_icon_view.mapToGlobal(position))
            return

        path = item.data(Qt.ItemDataRole.UserRole)
        item_type = item.data(Qt.ItemDataRole.UserRole + 1)
        if not path:
            return

        self._build_folder_context_menu(path, item_type).exec(self.folder_icon_view.mapToGlobal(position))

    def show_add_to_project_dialog(self, file_path):
        """Show dialog to select which project to add the file/folder to"""
        # Get list of project files
        projects_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        projects = []

        if os.path.isdir(projects_dir):
            for f in os.listdir(projects_dir):
                if f.endswith('.json'):
                    projects.append(f[:-5])  # Remove .json extension

        if not projects:
            QMessageBox.warning(self, "Add to Project", f"No project files found in {projects_dir}")
            return

        projects.sort(key=str.lower)

        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Add to Project")
        dialog.setMinimumWidth(300)
        layout = QVBoxLayout(dialog)

        # Label
        filename = os.path.basename(file_path)
        label = QLabel(f"Add '{filename}' to which project?")
        layout.addWidget(label)

        # Project selector
        combo = QComboBox()
        combo.addItems(projects)

        # Try to pre-select current project
        if self.current_config_file:
            current_name = os.path.basename(self.current_config_file)
            if current_name.endswith('.json'):
                current_name = current_name[:-5]
            if current_name in projects:
                combo.setCurrentText(current_name)

        layout.addWidget(combo)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_project = combo.currentText()
            project_path = os.path.join(projects_dir, f"{selected_project}.json")
            self.add_resource_to_project(file_path, project_path)

    def add_resource_to_project(self, file_path, project_path):
        """Add a file or folder to a project's 'Added Resources' category"""
        try:
            with open(project_path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read config: {e}")
            return

        # Ensure columns exist
        if 'columns' not in data:
            data['columns'] = [[]]
        if not data['columns']:
            data['columns'] = [[]]

        column1 = data['columns'][0]

        # Find or create "Added Resources" category
        added_resources = None
        for category_dict in column1:
            if isinstance(category_dict, dict) and "Added Resources" in category_dict:
                added_resources = category_dict["Added Resources"]
                break

        if added_resources is None:
            # Create the category at the end of column 1
            added_resources = []
            column1.append({"Added Resources": added_resources})

        # Check for duplicates
        existing_paths = [item[1] for item in added_resources if len(item) > 1]
        if file_path in existing_paths:
            QMessageBox.information(self, "Add to Project", "This item is already in the project.")
            return

        # Determine display name and handler
        display_name = os.path.basename(file_path)

        if os.path.isdir(file_path):
            app = "file_manager"
        else:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg'):
                app = "gwenview"
            else:
                app = "default"

        # Add the entry
        added_resources.append([display_name, file_path, app])

        # Save the config
        try:
            with open(project_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config: {e}")
            return

        project_name = os.path.basename(project_path).replace('.json', '')
        QMessageBox.information(self, "Add to Project", f"Added '{display_name}' to {project_name}")

        # Refresh if we added to the current project
        if project_path == self.current_config_file:
            self.refresh_projects()

    def show_add_to_documentation_dialog(self, file_path):
        """Show dialog to select which project to add the file to as a documentation entry"""
        projects_dir = os.path.join(self.script_dir, self.settings.get("projects_directory", "projects"))
        projects = []

        if os.path.isdir(projects_dir):
            for f in os.listdir(projects_dir):
                if f.endswith('.json'):
                    projects.append(f[:-5])

        if not projects:
            QMessageBox.warning(self, "Add to Documentation", f"No project files found in {projects_dir}")
            return

        projects.sort(key=str.lower)

        dialog = QDialog(self)
        dialog.setWindowTitle("Add to Documentation")
        dialog.setMinimumWidth(300)
        layout = QVBoxLayout(dialog)

        filename = os.path.basename(file_path)
        label = QLabel(f"Add '{filename}' to documentation in which project?")
        layout.addWidget(label)

        combo = QComboBox()
        combo.addItems(projects)

        if self.current_config_file:
            current_name = os.path.basename(self.current_config_file)
            if current_name.endswith('.json'):
                current_name = current_name[:-5]
            if current_name in projects:
                combo.setCurrentText(current_name)

        layout.addWidget(combo)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_project = combo.currentText()
            project_path = os.path.join(projects_dir, f"{selected_project}.json")
            self.add_resource_to_documentation(file_path, project_path)

    def add_resource_to_documentation(self, file_path, project_path):
        """Add a file to a project's 'Documentation' category"""
        try:
            with open(project_path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read config: {e}")
            return

        if 'columns' not in data:
            data['columns'] = [[]]
        if not data['columns']:
            data['columns'] = [[]]

        column1 = data['columns'][0]

        # Find or create "Documentation" category
        doc_category = None
        for category_dict in column1:
            if isinstance(category_dict, dict) and "Documentation" in category_dict:
                doc_category = category_dict["Documentation"]
                break

        if doc_category is None:
            doc_category = []
            column1.append({"Documentation": doc_category})

        # Check for duplicates
        existing_paths = [item[1] for item in doc_category if len(item) > 1]
        if file_path in existing_paths:
            QMessageBox.information(self, "Add to Documentation", "This file is already in the Documentation category.")
            return

        # Display name: filename stem with underscores/hyphens replaced by spaces
        stem = os.path.splitext(os.path.basename(file_path))[0]
        display_name = stem.replace('_', ' ').replace('-', ' ').title()

        # Launcher type based on extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.html', '.htm'):
            app = "firefox"
        else:
            app = "default"

        doc_category.append([display_name, file_path, app])

        try:
            with open(project_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config: {e}")
            return

        project_name = os.path.basename(project_path).replace('.json', '')
        QMessageBox.information(self, "Add to Documentation", f"Added '{display_name}' to {project_name}")

        if project_path == self.current_config_file:
            self.refresh_projects()

    def folder_open_external(self):
        """Open current folder in file manager"""
        file_manager = self.get_configured_file_manager()
        subprocess.Popen([file_manager, self.folder_current_path], start_new_session=True)

    def open_project_folder_external(self):
        """Open this project's default folder (config_folder_path, not necessarily where any
        given document actually lives) in the configured file manager — the callback behind
        the "Open Project Folder" footer under the Docs category."""
        if not getattr(self, 'config_folder_path', None):
            return
        file_manager = self.get_configured_file_manager()
        subprocess.Popen([file_manager, os.path.expanduser(self.config_folder_path)], start_new_session=True)

    def folder_make_project(self):
        """Create a .projectflow config and projectflow.md notes file for the current folder"""
        folder_path = self.folder_current_path
        folder_name = os.path.basename(folder_path)

        # Create config content
        config = self.create_folder_project_config(folder_path)

        # Write .projectflow file
        projectflow_path = os.path.join(folder_path, ".projectflow")
        try:
            with open(projectflow_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create .projectflow: {str(e)}")
            return

        # Create projectflow.md notes file
        self.create_project_notes_file(folder_path)

        # Refresh the folder browser to show updated state
        self.populate_folder_browser(folder_path)

        # Ask if user wants to open the project
        reply = QMessageBox.question(
            self,
            "Project Created",
            f"Created ProjectFlow config for '{folder_name}'.\n\nOpen the project now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.switch_to_config(projectflow_path)
            self._show_kickstart_dialog(folder_path=folder_path)

    def folder_make_project_at(self, folder_path):
        """Create a .projectflow config at the specified folder path"""
        folder_name = os.path.basename(folder_path)

        # Create config content
        config = self.create_folder_project_config(folder_path)

        # Write .projectflow file
        projectflow_path = os.path.join(folder_path, ".projectflow")
        try:
            with open(projectflow_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create .projectflow: {str(e)}")
            return

        # Create projectflow.md notes file
        self.create_project_notes_file(folder_path)

        # Refresh the folder browser to show updated state
        self.populate_folder_browser(self.folder_current_path)

        # Ask if user wants to open the project
        reply = QMessageBox.question(
            self,
            "Project Created",
            f"Created ProjectFlow config for '{folder_name}'.\n\nOpen the project now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.switch_to_config(projectflow_path)
            self._show_kickstart_dialog(folder_path=folder_path)

    def create_folder_project_config(self, folder_path):
        """Create a *bare* project config for a folder — no launcher categories.

        Used by "Make Project" (folder_make_project()/folder_make_project_at()), which
        immediately follows up by opening the Kickstart dialog
        (_show_kickstart_dialog()) pre-populated with this same folder's detected
        suggestions for review, rather than baking categories in silently. Detection
        itself lives in _detect_project_indicators() — the single shared source of
        "what does this folder look like", also used when Kickstart is re-run later
        from the Project Settings viewer against an already-existing project.
        """
        folder_name = os.path.basename(folder_path)
        return {
            "project_name": folder_name,
            "column_headers": [f"{folder_name} Project"],
            "columns": [[]],
            "column2_default": "folder",
            "folder_path": ".",
            "notes_file": "./projectflow.md",
            "layout_mode": "focus"
        }

    def _build_dev_shortcut_suggestions(self, folder_path, combined=True):
        """Return the Development-category suggestion list for Kickstart: either one
        combined 'directorydev' launcher (which already renders its own separate icon
        buttons for file manager/terminal/editor — see CLAUDE.md's Launch Handlers →
        directorydev) or three plain separate launcher items. Always absolute paths —
        see _detect_project_indicators()'s docstring for why."""
        if combined:
            return [{
                "id": "dev_combined", "label": "Dev Environment (file manager + terminal + editor)",
                "item": ["Dev Environment", folder_path, "directorydev"]
            }]
        return [
            {"id": "dev_editor", "label": "Open in Editor",
             "item": ["Open in Editor", folder_path, "editor"]},
            {"id": "dev_terminal", "label": "Terminal Here",
             "item": ["Terminal Here", folder_path, "terminal"]},
            {"id": "dev_filemanager", "label": "File Manager",
             "item": ["File Manager", folder_path, "file_manager"]},
        ]

    def _detect_project_indicators(self, folder_path):
        """Scan folder_path for recognizable project types and return suggestion
        groups: [{"category": str, "suggestions": [{"id", "label", "item"}]}]. Every
        suggestion's checkbox starts unchecked in the Kickstart dialog (opt-in, not
        opt-out) — there is no per-suggestion "checked" field to carry that anymore.

        Single shared source of truth for "what does this folder look like" detection —
        used by the Kickstart dialog (_show_kickstart_dialog()) both right after "Make
        Project" and when re-run later against an already-existing project. Every
        suggested item uses an absolute path (folder_path itself) rather than the
        ".projectflow"-only "." convention this detection used to emit via
        create_folder_project_config(): Kickstart also runs against plain
        projects/*.json configs, which never get relative-path resolution
        (resolve_relative_paths_in_config() only fires for .projectflow files), so
        absolute paths are the only form correct for every caller.
        """
        folder_path = os.path.abspath(os.path.expanduser(folder_path))
        groups = []

        def add_group(category, suggestions):
            if suggestions:
                groups.append({"category": category, "suggestions": suggestions})

        def sug(id_, label, item):
            return {"id": id_, "label": label, "item": item}

        # --- npm / yarn / pnpm ---
        pkg_json = os.path.join(folder_path, "package.json")
        if os.path.exists(pkg_json):
            scripts = {}
            try:
                with open(pkg_json, 'r') as f:
                    scripts = json.load(f).get("scripts", {})
            except Exception:
                pass

            if os.path.exists(os.path.join(folder_path, "yarn.lock")):
                runner = "yarn"
            elif os.path.exists(os.path.join(folder_path, "pnpm-lock.yaml")):
                runner = "pnpm"
            else:
                runner = "npm"

            if runner == "npm":
                suggestions = [sug("npm_install", "npm install", ["npm install", f"{folder_path} install", "npm"])]
                for key, label in (("start", "npm start"), ("dev", "npm dev"), ("build", "npm build"), ("test", "npm test")):
                    if key in scripts:
                        suggestions.append(sug(f"npm_{key}", label, [label, f"{folder_path} {key}", "npm"]))
            else:
                install_cmd = f"{runner} install"
                suggestions = [sug(f"{runner}_install", install_cmd, [install_cmd, f"{folder_path} {install_cmd}", "terminal_cmd"])]
                for key in ("start", "dev", "build", "test"):
                    if key in scripts:
                        cmd = f"{runner} {key}" if runner == "yarn" else f"{runner} run {key}"
                        suggestions.append(sug(f"{runner}_{key}", cmd, [cmd, f"{folder_path} {cmd}", "terminal_cmd"]))
            add_group(runner, suggestions)

        # --- Python ---
        if os.path.exists(os.path.join(folder_path, "requirements.txt")):
            cmd = "pip install -r requirements.txt"
            add_group("Python", [sug("pip_install", cmd, [cmd, f"{folder_path} {cmd}", "terminal_cmd"])])
        elif os.path.exists(os.path.join(folder_path, "setup.py")) or os.path.exists(os.path.join(folder_path, "pyproject.toml")):
            cmd = "pip install -e ."
            add_group("Python", [sug("pip_install_e", cmd, [cmd, f"{folder_path} {cmd}", "terminal_cmd"])])

        # --- Rust ---
        if os.path.exists(os.path.join(folder_path, "Cargo.toml")):
            add_group("Rust", [
                sug("cargo_build", "cargo build", ["cargo build", f"{folder_path} cargo build", "terminal_cmd"]),
                sug("cargo_run", "cargo run", ["cargo run", f"{folder_path} cargo run", "terminal_cmd"]),
                sug("cargo_test", "cargo test", ["cargo test", f"{folder_path} cargo test", "terminal_cmd"]),
            ])

        # --- Go ---
        if os.path.exists(os.path.join(folder_path, "go.mod")):
            add_group("Go", [
                sug("go_build", "go build", ["go build", f"{folder_path} go build", "terminal_cmd"]),
                sug("go_run", "go run .", ["go run .", f"{folder_path} go run .", "terminal_cmd"]),
                sug("go_test", "go test ./...", ["go test ./...", f"{folder_path} go test ./...", "terminal_cmd"]),
            ])

        # --- PHP / Composer ---
        if os.path.exists(os.path.join(folder_path, "composer.json")):
            cmd = "composer install"
            add_group("Composer", [sug("composer_install", cmd, [cmd, f"{folder_path} {cmd}", "terminal_cmd"])])

        # --- Makefile ---
        if os.path.exists(os.path.join(folder_path, "Makefile")):
            add_group("Build", [sug("make", "make", ["make", f"{folder_path} make", "terminal_cmd"])])

        # --- Docker ---
        if os.path.exists(os.path.join(folder_path, "docker-compose.yml")) or \
           os.path.exists(os.path.join(folder_path, "docker-compose.yaml")):
            add_group("Docker", [
                sug("docker_up", "docker-compose up", ["docker-compose up", f"{folder_path} docker-compose up", "terminal_cmd"]),
                sug("docker_down", "docker-compose down", ["docker-compose down", f"{folder_path} docker-compose down", "terminal_cmd"]),
            ])

        # --- Git ---
        if os.path.exists(os.path.join(folder_path, ".git")):
            add_group("Git", [
                sug("git_status", "git status", ["git status", f"{folder_path} git status", "terminal_cmd"]),
                sug("git_log", "git log", ["git log", f"{folder_path} git log --oneline -20", "terminal_cmd"]),
            ])

        # --- README ---
        for readme in ["README.md", "README.txt", "README"]:
            readme_path = os.path.join(folder_path, readme)
            if os.path.exists(readme_path):
                app = "default" if readme == "README.md" else "editor"
                add_group("Quick Actions", [sug("readme", f"Open {readme}", [f"Open {readme}", readme_path, app])])
                break

        return groups

    def create_project_notes_file(self, folder_path):
        """Create a starter projectflow.md notes file"""
        folder_name = os.path.basename(folder_path)
        notes_path = os.path.join(folder_path, "projectflow.md")

        # Don't overwrite existing notes
        if os.path.exists(notes_path):
            return

        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")

        content = f"""# {folder_name} Notes

Project created: {date_str}

## TODO

-

## Notes

"""
        try:
            with open(notes_path, 'w') as f:
                f.write(content)
        except Exception as e:
            print(f"Warning: Could not create notes file: {e}")

    def load_help_content(self):
        """Load and display the combined Help page (README + Launcher Examples tabs)"""
        self.help_browser.setHtml(self._build_help_html())

    def _build_help_html(self):
        """Build the combined Help viewer page: a README tab and a "Launcher Examples" tab,
        switched with a pure-CSS (no JavaScript) radio-button tab pattern.

        QWebEngineView does support JavaScript — it's used elsewhere in this app (Muya editor,
        the ttyd terminal, the Aliases page's search box) — but a static two-tab reference page
        has no real need for it, so this avoids the dependency entirely. The Examples tab is
        embedded via <iframe srcdoc="..."> rather than merged into one shared stylesheet, since
        EXAMPLES.html is already a complete, self-contained document with its own <style> block;
        an iframe keeps its CSS isolated instead of risking class-name collisions with the
        README's own styling.
        """
        readme_path = os.path.join(self.script_dir, "README.md")
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                readme_html = self.markdown_to_html(f.read())
        except Exception as e:
            readme_html = f"<p style='color: {self.t('fg_primary')}'>Could not load README.md: {e}</p>"

        examples_html = self._load_examples_html_fragment()
        examples_srcdoc = examples_html.replace('&', '&amp;').replace('"', '&quot;')

        bg_help = self.t('bg_help')
        fg_primary = self.t('fg_primary')
        border = self.t('border')
        bg_button = self.t('bg_button')
        bg_button_hover = self.t('bg_button_hover')
        fg_on_dark = self.t('fg_on_dark')
        bg_category = self.t('bg_category')

        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
    html, body {{ height: 100%; margin: 0; }}
    body {{
        display: flex; flex-direction: column;
        font-family: sans-serif; background: {bg_help}; color: {fg_primary};
    }}
    input[type=radio] {{ display: none; }}
    .tabbar {{ display: flex; flex: 0 0 auto; border-bottom: 2px solid {border}; padding: 10px 10px 0; }}
    .tabbar label {{
        padding: 8px 16px; cursor: pointer; font-weight: bold; font-size: 12pt;
        background: {bg_button}; color: {fg_primary};
        border: 1px solid {border}; border-bottom: none;
        margin-right: 4px; border-radius: 5px 5px 0 0;
    }}
    .tabbar label:hover {{ background: {bg_button_hover}; color: {fg_on_dark}; }}
    #tab-readme:checked ~ .tabbar label[for="tab-readme"],
    #tab-examples:checked ~ .tabbar label[for="tab-examples"] {{
        background: {bg_category}; color: {fg_on_dark};
    }}
    .tabpanel {{ display: none; flex: 1 1 auto; overflow: auto; padding: 15px; box-sizing: border-box; }}
    .tabpanel iframe {{ width: 100%; height: 100%; border: none; }}
    #tab-readme:checked ~ #panel-readme {{ display: block; }}
    #tab-examples:checked ~ #panel-examples {{ display: block; }}
</style></head>
<body>
    <input type="radio" name="helptabs" id="tab-readme" checked>
    <input type="radio" name="helptabs" id="tab-examples">
    <div class="tabbar">
        <label for="tab-readme">README</label>
        <label for="tab-examples">Launcher Examples</label>
    </div>
    <div class="tabpanel" id="panel-readme">{readme_html}</div>
    <div class="tabpanel" id="panel-examples"><iframe srcdoc="{examples_srcdoc}"></iframe></div>
</body></html>"""

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
        """Open an image file via file picker — always opens as a new tab (see
        _open_image_tab())."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            os.path.expanduser("~"),
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;All Files (*)"
        )
        if file_path:
            self._open_image_tab(file_path)

    def _image_load_tab_pixmap(self, tab):
        """Load the QPixmap for `tab`, storing the result on the tab object itself. Split
        out from _open_image_tab() so build_main_content()'s startup restore (loading every
        remembered tab) can reuse it without re-appending to self.image_tabs. Returns True
        on success, False if the file doesn't exist or isn't a valid image."""
        expanded_path = os.path.expanduser(tab.path)
        if not os.path.exists(expanded_path):
            return False
        pixmap = QPixmap(expanded_path)
        if pixmap.isNull():
            return False
        tab.pixmap = pixmap
        return True

    def _open_image_tab(self, path):
        """Open `path` as a brand-new Image tab and make it active. Always-new-tab policy,
        mirroring _open_pdf_tab() — every "open an image" action (launcher click, Open
        button) adds a tab rather than replacing whatever's already open."""
        tab = ImageTabState(path)
        if not self._image_load_tab_pixmap(tab):
            self.status_label.setText(f"Failed to load image: {path}")
            return False
        self.image_tabs.append(tab)
        self._activate_image_tab(len(self.image_tabs) - 1)
        self.save_notes()
        self.status_label.setText(f"✓ Loaded image: {os.path.basename(path)}")
        self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
        return True

    def _activate_image_tab(self, index):
        """Make self.image_tabs[index] the active tab: sync the active-tab proxy scalars
        (image_path/image_pixmap — read by render_image()/image_fit_width()/zoom, all
        unchanged), render, fit to width, and refresh the tab strip."""
        self.image_active_index = index
        tab = self.image_tabs[index]
        self.image_path = tab.path
        self.image_pixmap = tab.pixmap
        if tab.pixmap is not None:
            # Deferred fit-to-width to allow layout to settle (needed on startup/rebuild).
            QTimer.singleShot(500, self.image_fit_width)
        elif self.image_label is not None:
            self._set_viewer_placeholder(self.image_label, "image", f"Could not load:\n{tab.path}")
        self._rebuild_image_tab_strip()

    def _close_image_tab(self, index):
        """Close and discard the Image tab at `index`, picking a sensible new active tab
        (mirrors _close_pdf_tab())."""
        if not (0 <= index < len(self.image_tabs)):
            return
        closing_active = (index == self.image_active_index)
        self.image_tabs.pop(index)
        if not self.image_tabs:
            self.image_active_index = -1
            self.image_path = None
            self.image_pixmap = None
            if self.image_label is not None:
                self._set_viewer_placeholder(self.image_label, "image", "No image loaded\n\nUse the Open button to open an image")
            self._rebuild_image_tab_strip()
        elif closing_active:
            self._activate_image_tab(min(index, len(self.image_tabs) - 1))
        else:
            if index < self.image_active_index:
                self.image_active_index -= 1
            self._rebuild_image_tab_strip()
        self.save_notes()

    def _close_all_image_tabs(self):
        """Close every open Image tab. _close_image_tab() never refuses to close (no
        confirmation dialog — images are read-only), so this always terminates with zero
        tabs."""
        while self.image_tabs:
            self._close_image_tab(0)

    def _build_image_tab_strip(self, parent_layout):
        """Build the row of Image tab buttons — mirrors _build_pdf_tab_strip()."""
        self.image_tab_strip_widget = QWidget()
        self.image_tab_strip_layout = QHBoxLayout(self.image_tab_strip_widget)
        self.image_tab_strip_layout.setContentsMargins(0, 0, 0, 4)
        self.image_tab_strip_layout.setSpacing(2)
        parent_layout.addWidget(self.image_tab_strip_widget)
        self._rebuild_image_tab_strip()

    def _rebuild_image_tab_strip(self):
        """Clear and repopulate self.image_tab_strip_layout from self.image_tabs — mirrors
        _rebuild_pdf_tab_strip()."""
        if getattr(self, 'image_tab_strip_layout', None) is None:
            return
        while self.image_tab_strip_layout.count():
            item = self.image_tab_strip_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self.image_tab_strip_widget.setVisible(bool(self.image_tabs))
        for i, tab in enumerate(self.image_tabs):
            is_active = (i == self.image_active_index)
            group = self._build_tab_group_widget(
                os.path.basename(tab.path) or tab.path, tab.path,
                self._viewer_tab_button_style(is_active),
                lambda checked=False, idx=i: self._activate_image_tab(idx),
                lambda checked=False, idx=i: self._close_image_tab(idx),
            )
            self.image_tab_strip_layout.addWidget(group)
        self.image_tab_strip_layout.addStretch()
        if len(self.image_tabs) > 1:
            self.image_tab_strip_layout.addWidget(
                self._build_close_all_tabs_button(lambda checked=False: self._close_all_image_tabs())
            )

    def render_image(self):
        """Render the image at current zoom level"""
        if not getattr(self, 'image_pixmap', None) or self.image_pixmap.isNull():
            return

        # Undo the placeholder's centered alignment (_set_viewer_placeholder) now that
        # there's a real image — matches the same restore in render_pdf_page.
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

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
        if not getattr(self, 'image_pixmap', None) or self.image_pixmap.isNull() or not self.image_scroll:
            return

        viewport_width = self.image_scroll.viewport().width() - 20
        image_width = self.image_pixmap.width()
        if image_width > 0:
            self.image_zoom = viewport_width / image_width
            self.image_zoom_label.setText(f"{int(self.image_zoom * 100)}%")
            self.render_image()

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

            # Show status message — but only the generic one if nothing more specific was
            # already shown during this rebuild (e.g. a path-mapping fallback hint from
            # populate_folder_browser(), see _resolve_existing_path()). init_ui() rebuilds
            # status_label fresh every time (see create_title_bar()), so an empty label here
            # means nothing set it during the rebuild — otherwise this would silently stomp
            # that hint on every project switch, since switch_to_config() always calls this.
            if not self.status_label.text():
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

    def open_in_app(self, path, app="default", force_external=False):
        """Open the specified path in the given application"""
        try:
            # Fall back to a global path mapping only if the direct path is missing (before
            # ~ expansion) — read-only, never persisted back to the config. See
            # _resolve_existing_path().
            path, _used_mapping = self._resolve_existing_path(path)
            if _used_mapping:
                self.set_status(f"Path not found — opened via mapping instead: {path}", "info")
            # Expand ~ to home directory
            expanded_path = os.path.expanduser(path)

            # Focus layout: route viewable content to internal viewer instead of external apps.
            # force_external=True lets the small icon button bypass this and always launch externally.
            if self.layout_mode == "focus" and not force_external:
                ext = os.path.splitext(expanded_path)[1].lower()
                if app in ("firefox", "chrome") or expanded_path.startswith(("http://", "https://")):
                    if ext == ".md" and self._is_local_path(path):
                        self._open_markdown_file(expanded_path)
                    elif ext in (".html", ".htm") and self._is_local_path(path):
                        self._open_file_in_webview(expanded_path)
                    else:
                        self.preview_in_webview(path)
                    return
                if ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp') or app in ("gwenview", "gimp", "krita"):
                    self.preview_in_image_viewer(expanded_path)
                    return
                if ext == ".pdf":
                    self.preview_in_pdf_viewer(expanded_path)
                    return
                if ext == ".md" and self._is_local_path(path):
                    self._open_markdown_file(expanded_path)
                    return
                # .html/.htm now default into the code editor too, via
                # _CODE_ROUTE_EXTENSIONS below — local files open in the editor, only URLs
                # (and the explicit firefox/chrome-app case above) open in the web viewer.
                # Use the "👁 Rendered"/"</> Edit Source" toggle to switch a given file
                # between the two views.
                if ext in self._CODE_ROUTE_EXTENSIONS and self._is_local_path(path):
                    self._open_code_file_in_editor(expanded_path)
                    return
                if (app == "tail_log" or (ext == ".log" and self._is_local_path(path))) and self.resolve_console_backend() == "ttyd":
                    self._open_log_file_in_console(expanded_path)
                    return
                if app in ("terminal", "konsole") and self.resolve_console_backend() == "ttyd":
                    self._open_terminal_launcher_in_console(expanded_path)
                    return
                if os.path.isdir(expanded_path) and app not in ("terminal", "konsole", "editor", "directorydev"):
                    self.preview_in_folder_browser(expanded_path)
                    return
                # Everything else (terminal/konsole on the qtconsole backend, editor, ssh,
                # npm, directorydev) falls through to the external launch below.

            # 0. File manager: use configured FM with optional home-tab behaviour
            if app in ("file_manager", "dolphin"):
                self._open_file_manager(expanded_path)
                self.status_label.setText(f"✓ Opened in file manager: {path}")
                self.status_label.setStyleSheet("color: #27ae60; margin: 10px; font-weight: bold;")
                return

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

            # 1c. Alias handler — path = "alias_name command_or_directory"
            # The alias name (first word) is stripped; only the command/path is executed.
            if app == "alias":
                _alias_name, _, _rest = path.partition(' ')
                _rest = _rest.strip()
                # "cd <dir>" (no chained commands) → open terminal at that directory
                if _rest.lower().startswith('cd ') and not re.search(r'&&|\|\||;', _rest):
                    _dir = os.path.expanduser(_rest[3:].strip())
                    cmd = self._get_terminal_workdir_command(_dir)
                elif re.match(r'^cd\s+\S+\s*&&', _rest, re.IGNORECASE):
                    # "cd <dir> && cmd" — cd must run outside the subshell so
                    # the interactive bash that follows starts in the right directory.
                    _cd_match = re.match(r'^cd\s+(\S+)\s*&&\s*(.+)$', _rest.strip(), re.IGNORECASE)
                    if _cd_match:
                        _dir = os.path.expanduser(_cd_match.group(1))
                        _subcmd = _cd_match.group(2).strip()
                        shell_cmd = f'cd {shlex.quote(_dir)} && (trap "exit 0" INT; {_subcmd}); exec bash'
                    else:
                        shell_cmd = f'(trap "exit 0" INT; {_rest}); exec bash'
                    cmd = self._get_terminal_command(shell_cmd, hold=False)
                else:
                    _expanded_rest = os.path.expanduser(_rest)
                    if os.path.isdir(_expanded_rest):
                        cmd = self._get_terminal_workdir_command(_expanded_rest)
                    else:
                        # Run command then drop to interactive shell so the user
                        # gets a prompt rather than a frozen/blank terminal window.
                        shell_cmd = f'(trap "exit 0" INT; {_rest}); exec bash'
                        cmd = self._get_terminal_command(shell_cmd, hold=False)
                subprocess.Popen(cmd, start_new_session=True)
                self.status_label.setText(f"✓ Alias '{_alias_name}': {_rest}")
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
                if app in ('firefox', 'chrome') and not self._get_browser_new_tab():
                    handler = dict(handler)
                    handler['command'] = [arg.replace('--new-tab', '--new-window') for arg in handler['command']]
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

            # 7. Special handling for kate with directories (use file manager instead)
            if app == "kate" and os.path.isdir(expanded_path):
                self._open_file_manager(expanded_path)
                self.status_label.setText(f"✓ Opened folder in file manager: {path}")
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

        icon = os.path.join(self.script_dir, "assets", "icon.png")

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

    # Set window icon to the app's own branded icon (assets/icon.png), falling back to a
    # generic theme icon only if that file is somehow missing (e.g. a stripped-down install).
    own_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
    icon = QIcon(own_icon_path) if os.path.exists(own_icon_path) else QIcon()
    if icon.isNull():
        for icon_name in ["application-x-executable", "system-run", "folder"]:
            icon = QIcon.fromTheme(icon_name)
            if not icon.isNull():
                break
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = ProjectFlowApp(config_file_arg=args.config)
    window.showMaximized()
    #window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
