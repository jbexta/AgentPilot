import asyncio
import json
from functools import partial
import os
from pathlib import Path

from PySide6.QtWidgets import *
from PySide6.QtCore import Signal, QSize, QEvent, QRunnable, Slot, QPoint, QTimer
from PySide6.QtGui import QAction, QCursor, QPixmap, QPalette, QColor, QIcon, QFont, Qt, QPainter, \
    QTextOption, QTextDocument, QKeyEvent, QTextCursor, QFontMetrics, QStandardItem, QStandardItemModel

from gui import system
from gui.style import TEXT_COLOR, ACCENT_COLOR_1
from utils import sql, resources_rc
from utils.helpers import convert_to_safe_case, path_to_pixmap, display_message_box, block_signals, apply_alpha_to_hex, \
    get_avatar_paths_from_config, display_message, get_metadata, merge_config_into_workflow_config
from PySide6.QtWidgets import QAbstractItemView


class FramelessResizeMixin:
    """Mixin providing frameless window resize and move behaviour.

    Call :meth:`init_frameless_resize` from the subclass ``__init__``
    after setting the ``Qt.FramelessWindowHint`` window flag.
    """

    def init_frameless_resize(self, margin=10):
        """Initialise resize state variables.

        Parameters
        ----------
        margin : int
            Pixel width of the resize grab area along each edge.
        """
        self._mouse_pressed = False
        self._mouse_pos = None
        self._mouse_global_pos = None
        self._resizing = False
        self._resize_margins = margin

    # -- mouse events -----------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._mouse_pressed = True
            self._mouse_pos = event.pos()
            self._mouse_global_pos = event.globalPos()
            self._resizing = self._is_mouse_on_edge(event.pos())
            self._update_cursor_shape(event.pos())

    def mouseMoveEvent(self, event):
        if self._mouse_pressed:
            if self._resizing:
                self._resize_window(event.globalPos())
            else:
                self._move_window(event.globalPos())

    def mouseReleaseEvent(self, event):
        self._mouse_pressed = False
        self._resizing = False
        self._mouse_pos = None
        self._mouse_global_pos = None
        self.setCursor(Qt.ArrowCursor)

    # -- helpers ----------------------------------------------------

    def _is_mouse_on_edge(self, pos):
        rect = self.rect()
        m = self._resize_margins
        return (pos.x() < m
                or pos.x() > rect.width() - m
                or pos.y() < m
                or pos.y() > rect.height() - m)

    def _move_window(self, global_pos):
        if self._mouse_global_pos is None:
            return
        diff = global_pos - self._mouse_global_pos
        self.move(self.pos() + diff)
        self._mouse_global_pos = global_pos

    def _resize_window(self, global_pos):
        diff = global_pos - self._mouse_global_pos
        new_rect = self.geometry()
        m = self._resize_margins

        if self._mouse_pos.x() < m:
            new_rect.setLeft(new_rect.left() + diff.x())
        elif self._mouse_pos.x() > self.width() - m:
            new_rect.setRight(new_rect.right() + diff.x())

        if self._mouse_pos.y() < m:
            new_rect.setTop(new_rect.top() + diff.y())
        elif self._mouse_pos.y() > self.height() - m:
            new_rect.setBottom(new_rect.bottom() + diff.y())

        self.setGeometry(new_rect)
        self._mouse_pos = self.mapFromGlobal(global_pos)
        self._mouse_global_pos = global_pos

    def _update_cursor_shape(self, pos):
        rect = self.rect()
        m = self._resize_margins
        left = pos.x() < m
        right = pos.x() > rect.width() - m
        top = pos.y() < m
        bottom = pos.y() > rect.height() - m

        if (left and top) or (right and bottom):
            self.setCursor(Qt.SizeFDiagCursor)
        elif (left and bottom) or (right and top):
            self.setCursor(Qt.SizeBDiagCursor)
        elif left or right:
            self.setCursor(Qt.SizeHorCursor)
        elif top or bottom:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)


def find_main():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app:
        for widget in app.topLevelWidgets():
            if widget.__class__.__name__ == 'Main':
                return widget
    return None


def find_chat_widget(widget):
    from plugins.workflows.widgets.chat_widget import ChattableWorkflowWidget
    # is instance ChattableWorkflowWidget
    if isinstance(widget, ChattableWorkflowWidget):
        return widget
    if not hasattr(widget, 'parent'):
        return None
    return find_chat_widget(widget.parent)


def find_workflow_widget(widget):
    from plugins.workflows.widgets.workflow_settings import WorkflowSettings
    if isinstance(widget, WorkflowSettings):
        return widget
    if hasattr(widget, 'workflow_settings'):
        return widget.workflow_settings
    if not hasattr(widget, 'parent'):
        return None
    return find_workflow_widget(widget.parent)


def find_attribute(widget, attribute, default=None):
    if hasattr(widget, attribute):
        return getattr(widget, attribute)
    if not hasattr(widget, 'parent'):
        return default
    return find_attribute(widget.parent, attribute)


def find_ancestor_tree_widget(widget):
    from gui.widgets.config_db_tree import ConfigDBTree
    if isinstance(widget, ConfigDBTree):
        return widget
    if not hasattr(widget, 'parent'):
        return None
    return find_ancestor_tree_widget(widget.parent)


def find_ancestor_tree_item_id(widget):
    from gui.widgets.config_db_tree import ConfigDBTree
    if isinstance(widget, ConfigDBTree):
        return widget.get_selected_item_id()
    if not hasattr(widget, 'parent'):
        return None
    return find_ancestor_tree_item_id(widget.parent)


def get_member_settings_class(member_type):
    member_class = system.manager.modules.get_module_class('Members', module_name=member_type)

    if not member_class:
        display_message(
            message=f"Member module '{member_type}' not found.",
            icon=QMessageBox.Warning,
        )
        return None

    member_settings_module = getattr(member_class, '_ap_settings_module', None)
    if not member_settings_module:
        return None

    member_settings_class = system.manager.modules.get_module_class('Widgets', module_name=member_settings_module)
    if not member_settings_class:
        display_message(
            message=f"Member settings module '{member_settings_module}' not found.",
            icon=QMessageBox.Warning,
        )
        return None

    return member_settings_class


def get_project_type_class(project_type):
    project_type_class = system.manager.modules.get_module_class('Project_types', module_name=project_type)
    if not project_type_class:
        display_message(
            message=f"Project type module '{project_type}' not found.",
            icon=QMessageBox.Warning,
        )
        return None

    return project_type_class


class BreadcrumbWidget(QWidget):
    def __init__(self, parent, root_title=None):
        super().__init__(parent=parent)

        self.setFixedHeight(45)
        self.parent = parent
        self.root_title = root_title

        self.back_button = IconButton(parent=self, icon_path=':/resources/icon-back.png', size=40)
        self.back_button.setFixedSize(40, 40)
        self.back_button.setStyleSheet("border-top-left-radius: 22px;")
        self.back_button.clicked.connect(self.go_back)

        self.title_layout = CHBoxLayout(self)
        self.title_layout.setSpacing(20)
        self.title_layout.setContentsMargins(0, 0, 10, 0)
        self.title_layout.addWidget(self.back_button)

        self.label = QLabel(root_title)
        self.font = QFont()
        self.font.setPointSize(15)
        self.label.setFont(self.font)

        self.title_layout.addWidget(self.label)

        self.edit_btn = IconButton(
            parent=self,
            icon_path=':/resources/icon-edit.png',
            tooltip='Edit this page'
        )
        self.edit_btn.setFixedSize(25, 25)
        self.edit_btn.clicked.connect(self.edit_page)
        self.edit_btn.hide()

        self.finish_btn = IconButton(
            parent=self,
            icon_path=':/resources/icon-tick.svg',
            tooltip='Finish editing'
        )
        self.finish_btn.setFixedSize(25, 25)
        self.finish_btn.clicked.connect(self.finish_edit)
        self.finish_btn.hide()

        self.title_layout.addWidget(self.edit_btn)
        self.title_layout.addWidget(self.finish_btn)

    def load(self):
        sel_pages = get_selected_pages(self.parent, incl_objects=True, stop_at_tree=True)
        sel_page_tuples = list(sel_pages.values())
        page_names = [getattr(p, 'display_name', p_name) for p_name, p in sel_page_tuples if p is not None]
        page_names.insert(0, self.root_title)
        breadcrumb_text = '   >   '.join(page_names)
        if breadcrumb_text:
            self.label.setText(breadcrumb_text)

    def go_back(self):
        main = find_main()
        history = main.page_history
        if len(history) > 1:
            last_page_index = history[-2]
            main.page_history.pop()
            main.sidebar.button_group.button(last_page_index).click()
        else:
            main.main_pages.goto_page('chat')
            # self.main.page_chat.ensure_visible()

    def edit_page(self):  # todo
        main = find_main()
        page_widget = self.parent
        module_name = None
        for name, page in main.main_pages.pages.items():
            if page is page_widget:
                module_name = name
                break
        if not module_name:
            return

        if hasattr(page_widget, 'toggle_widget_edit'):
            page_widget.toggle_widget_edit(True)

        from gui.pages.modules import PageEditor
        if getattr(main, 'module_popup', None):
            main.module_popup.close()
            main.module_popup = None
        main.module_popup = PageEditor(main, module_name)
        main.module_popup.load()
        main.module_popup.show()
        self.edit_btn.hide()
        self.finish_btn.show()

    def finish_edit(self):
        page_widget = self.parent
        if hasattr(page_widget, 'toggle_widget_edit'):
            page_widget.toggle_widget_edit(False)

        main = find_main()
        if getattr(main, 'module_popup', None):
            main.module_popup.close()
            main.module_popup = None

        edit_bar = getattr(self.parent, 'edit_bar', None)
        if edit_bar:
            edit_bar.hide()

        self.finish_btn.hide()
        self.edit_btn.show()

    def enterEvent(self, event):
        user_editing = find_attribute(self.parent, 'user_editing', False)
        if user_editing:
            self.finish_btn.show()
            return

        allow_db = sql.get_scalar("""
            SELECT json_extract(value, '$."system.allow_importing_db_modules"')
            FROM settings WHERE field = 'app_config'
        """)
        module_id = find_attribute(self.parent, 'module_id')
        can_edit = module_id is not None and allow_db
        if can_edit:
            self.edit_btn.show()
            self.finish_btn.hide()

    def leaveEvent(self, event):
        self.edit_btn.hide()


class IconButton(QPushButton):
    def __init__(
            self,
            parent,
            icon_path=None,
            hover_icon_path=None,
            target=None,
            size=25,
            tooltip=None,
            icon_size_percent=0.75,
            colorize=True,
            opacity=1.0,
            text=None,
            checkable=False,
            **kwargs,
    ):
        super().__init__(parent=parent)
        self.parent = parent
        self.colorize = colorize
        self.opacity = opacity

        self.icon = None
        # if isinstance(icon_path, str):
        self.pixmap = path_to_pixmap(icon_path, diameter=size, opacity=opacity)  if icon_path else QPixmap(0, 0)
        # copy of pixmap to restore when leaving hover state
        self.original_pixmap = self.pixmap.copy()
        self.hover_pixmap = QPixmap(hover_icon_path) if hover_icon_path else None
        self.target = target
        self.clicked.connect(self.on_click)

        character_width = 8
        width = size + (len(text) * character_width if text else 0)
        self.icon_size = int(size * icon_size_percent)
        # self.setFixedSize(width, size)
        self.resize(width, size)
        self.setIconSize(QSize(self.icon_size, self.icon_size))
        self.setIconPixmap(self.pixmap)

        self.setAutoExclusive(False)  # To disable visual selection

        if tooltip:
            self.setToolTip(tooltip)
        if text:
            self.setText(text)
        if checkable:
            self.setCheckable(True)

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.opacity = 1 if enabled else 0.30
        self.setIconPixmap(self.pixmap)

    def on_click(self):
        if self.target:
            self.target()

    def setIconPixmap(self, pixmap=None, color=None):
        if not pixmap:
            pixmap = self.pixmap
        self.pixmap = pixmap

        if self.colorize:
            pixmap = colorize_pixmap(pixmap, opacity=self.opacity, color=color)

        self.icon = QIcon(pixmap)
        self.setIcon(self.icon)

    def enterEvent(self, event):
        if self.hover_pixmap:
            self.setIconPixmap(self.hover_pixmap)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.hover_pixmap:
            if self.original_pixmap.isNull():
                self.setIcon(QIcon())  # Clear the icon completely
            else:
                self.setIconPixmap(self.original_pixmap)
        super().leaveEvent(event)


class ToggleIconButton(IconButton):
    def __init__(self, **kwargs):
        self.icon_path = kwargs.get('icon_path', None)
        self.ttip = kwargs.get('tooltip', '')
        self.icon_path_checked = kwargs.pop('icon_path_checked', self.icon_path)
        self.tooltip_checked = kwargs.pop('tooltip_checked', None)
        self.color_when_checked = kwargs.pop('color_when_checked', None)
        self.opacity = kwargs.pop('opacity', 1)
        self.opacity_when_checked = kwargs.pop('opacity_when_checked', 1)
        self.show_checked_background = kwargs.pop('show_checked_background', True)
        self.target_when_checked = kwargs.pop('target_when_checked', None)
        super().__init__(**kwargs)
        # checkable = kwargs.get('checkable', False)
        self.setCheckable(True)

        # connect signal to refresh icon when checked state changes
        self.toggled.connect(self.refresh_icon)

    def setChecked(self, state):
        super().setChecked(state)
        self.refresh_icon()

    def refresh_icon(self):
        path = self.icon_path
        opacity = self.opacity
        color = None

        is_checked = self.isChecked()
        if self.icon_path == ':/resources/icon-chat.png' and not is_checked:
            pass
        if is_checked:
            path = self.icon_path_checked if self.icon_path_checked else self.icon_path
            opacity = self.opacity_when_checked if self.opacity_when_checked else self.opacity
            color = self.color_when_checked if self.color_when_checked else None

        if self.icon_path == ':/resources/icon-link.png':
            pass
        pixmap = colorize_pixmap(
            QPixmap(path),
            opacity=opacity,
            color=color
        )
        self.setIconPixmap(pixmap, color=self.color_when_checked if is_checked else None)
        # else:

        if self.tooltip_checked:
            self.setToolTip(self.tooltip_checked if is_checked else self.ttip)

    # def paintEvent(self, event):
    #     if not self.show_checked_background and self.isChecked():
    #         # Custom painting to avoid showing the checked background
    #         option = QStyleOptionButton()
    #         option.initFrom(self)
    #         # Remove the checked state for painting purposes only
    #         option.state &= ~QStyle.State_On
    #         option.state &= ~QStyle.State_Sunken

    #         # Set icon and text properties
    #         option.icon = QIcon(colorize_pixmap(QPixmap(self.icon_path_checked)))  # clean
    #         option.iconSize = self.iconSize()
    #         option.text = self.text()

    #         painter = QPainter()
    #         if not painter.begin(self):
    #             super().paintEvent(event)
    #             return
    #         # Draw button background without checked state
    #         self.style().drawControl(QStyle.CE_PushButton, option, painter, self)
    #         # Draw button content (icon and text)
    #         self.style().drawControl(QStyle.CE_PushButtonLabel, option, painter, self)
    #         painter.end()
    #     else:
    #         # Use default painting behavior
    #         super().paintEvent(event)


class CustomMenu(QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent
        self.schema = kwargs.get('schema', [])
        self.tool_button_style = kwargs.get('tool_button_style', None)
        self.icon_size = kwargs.get('icon_size', None)

        self.inner_widget = None
        self.layout = CVBoxLayout(self)

    def sizeHint(self):
        if self.inner_widget:
            return self.inner_widget.sizeHint()
        return super().sizeHint()

    def _reload_predicate_for_item(self, item, inner_widget, item_prefix='', parent_visibility=None, parent_enabled=None):
        skip_types = ['separator', 'stretch']
        if item.get('type') in skip_types:
            return

        # 1. Calculate Logic
        item_vis_pred = item.get('visibility_predicate', True)
        item_enabled_pred = item.get('enabled', True)

        is_visible = item_vis_pred() if callable(item_vis_pred) else item_vis_pred
        is_enabled = item_enabled_pred() if callable(item_enabled_pred) else item_enabled_pred

        # 2. Merge with Parent Logic
        if parent_visibility is not None:
            is_visible = is_visible and parent_visibility
        if parent_enabled is not None:
            is_enabled = is_enabled and parent_enabled

        # 3. Handle Recursive Flatmenu
        flatmenu = item.get('flatmenu', None)
        if flatmenu:
            prefix = item.get('prefix', '')
            flat_items = flatmenu() if callable(flatmenu) else flatmenu
            for flat_item in flat_items:
                self._reload_predicate_for_item(
                    flat_item, 
                    inner_widget, 
                    item_prefix=prefix,
                    parent_visibility=is_visible,
                    parent_enabled=is_enabled
                )
            return

        # # Handle widget items
        # widget_factory = item.get('widget', None)
        # if widget_factory:
        #     widget_id = item.get('id', id(widget_factory))
        #     widget_name = f'widget_{item_prefix}{widget_id}'
        #     action = getattr(inner_widget, widget_name, None)
        #     if action is not None:
        #         try:
        #             action.setVisible(bool(is_visible))
        #             action.setEnabled(bool(is_enabled))
        #         except Exception:
        #             pass
        #     return

        if 'text' not in item:
            return

        # 4. Apply State
        # This now retrieves the QAction (or the wrapper action for toolbuttons)
        action_name = f'btn_{item_prefix}{convert_to_safe_case(item["text"].lower())}'
        action = getattr(inner_widget, action_name, None)

        if action is not None:
            try:
                # QAction.setVisible controls the toolbar item visibility
                action.setVisible(bool(is_visible))
                action.setEnabled(bool(is_enabled))
            except Exception:
                pass

            # 5. Update Icon
            is_toolbar = isinstance(inner_widget, QToolBar)
            # Check if widget has icon_path metadata (we attached this in _add_item_to_toolbar)
            if is_toolbar and getattr(action, 'icon_path', None):
                opacity = 1.0 if is_enabled else 0.3

                # Determine target: If it's a wrapper action, update the inner button
                target = getattr(action, 'widget_ref', action)

                icon_pixmap = QPixmap(action.icon_path)
                if not icon_pixmap.isNull():
                    target.setIcon(QIcon(colorize_pixmap(icon_pixmap, opacity=opacity)))
                        
    def reload_predicates(self):
        if not self.inner_widget:
            return

        for item in self.schema:
            self._reload_predicate_for_item(item, self.inner_widget)

    def show_popup_menu(self, parent=None, schema=None, position=None):
        """
        Show a popup context menu at the specified position.

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget
        position : QPoint, optional
            Position to show menu, defaults to cursor position
        """

        def clean_predicates(schema) -> list:
            new_schema = []
            for item in schema:
                new_item = item.copy()
                submenu = item.get('submenu', None)
                if submenu and isinstance(submenu, list):
                    new_item['submenu'] = clean_predicates(submenu)

                ep = item.get('enabled', None)
                if ep is not None:
                    if callable(ep):
                        ep = ep()
                    if not ep:
                        continue

                new_schema.append(new_item)

            return new_schema

        use_schema = schema if schema else self.schema
        use_schema = clean_predicates(use_schema)

        menu = self._create_menu_recursive(title='', schema=use_schema, parent=parent)
        pos = position or QCursor.pos()
        try:
            menu.exec_(pos)
        finally:
            menu.deleteLater()

    def _add_item_to_toolbar(self, toolbar, item, item_prefix=''):
        """Add a single schema item to the toolbar."""
        if item.get('type') == 'separator':
            toolbar.addSeparator()
            return
        elif item.get('type') == 'stretch':
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            toolbar.addWidget(spacer)
            return
        elif item.get('type') == 'create_standard':
            return

        # Handle flatmenu
        flatmenu = item.get('flatmenu', None)
        if flatmenu:
            prefix = item.get('prefix', '')
            if not prefix:
                raise ValueError(f"Flatmenu items must have a 'prefix'")
            flat_items = flatmenu() if callable(flatmenu) else flatmenu
            for flat_item in flat_items:
                self._add_item_to_toolbar(toolbar, flat_item, item_prefix=prefix)
            return
        
        # Skip widget items in toolbar (only supported in menus)
        if 'widget' in item:
            return

        # Determine text and safe name
        text = item.get('text', None)
        # Ensure you have convert_to_safe_case available or imported
        button_name = f'btn_{item_prefix}{convert_to_safe_case(text.lower())}'
        icon_path = item.get('icon_path', None)

        # Handle submenu
        submenu = item.get('submenu', None)
        if submenu:
            menu = QMenu(item['text'], toolbar)
            menu.aboutToShow.connect(
                lambda m=menu, s=submenu: self._populate_menu_on_show(m, s)
            )

            tool_button = QToolButton(toolbar)
            tool_button.setText(item['text'])
            tool_button.setMenu(menu)
            tool_button.setPopupMode(QToolButton.InstantPopup)

            if icon_path:
                icon = QIcon(colorize_pixmap(QPixmap(icon_path)))
                tool_button.setIcon(icon)

            # --- KEY FIX START ---
            # Capture the wrapper action returned by addWidget
            action_proxy = toolbar.addWidget(tool_button)
            
            # Store metadata on the action so reload_predicates works
            action_proxy.icon_path = icon_path 
            
            # Store reference to the real button so we can update icons later
            action_proxy.widget_ref = tool_button 
            
            # Store the ACTION, not the button, in the attribute
            setattr(toolbar, button_name, action_proxy)
            # --- KEY FIX END ---
        else:
            # Regular action item
            icon = QIcon(colorize_pixmap(QPixmap(icon_path))) if icon_path else None
            action = QAction(text, toolbar)
            self._configure_action(action, item)
            action.icon_path = icon_path
            
            setattr(toolbar, button_name, action)
            toolbar.addAction(action)

    def create_toolbar(self, parent=None) -> QToolBar:
        toolbar = QToolBar(parent if parent else self)
        toolbar.setMovable(False)
        icon_size = self.icon_size if self.icon_size else 16
        toolbar.setIconSize(QSize(icon_size, icon_size))

        if self.tool_button_style:
            toolbar.setToolButtonStyle(self.tool_button_style)
        for item in self.schema:
            self._add_item_to_toolbar(toolbar, item)

        self.inner_widget = toolbar
        self.layout.addWidget(self.inner_widget)
        self.reload_predicates()
    
    def create_menubar(self, parent=None) -> QMenuBar:
        """
        Create a QMenuBar from the schema.
        Top-level items with 'submenu' become QMenu objects.
        Items without 'submenu' are ignored at top level (not typical for menubars).
        """
        menubar = QMenuBar(parent if parent else self)
        for item in self.schema:
            if item.get('type') == 'separator':
                menubar.addSeparator()
                continue
            elif item.get('type') == 'stretch':
                continue  # not applicable for QMenuBar
            elif item.get('type') == 'create_standard':
                continue  # not applicable for QMenuBar
            if 'flatmenu' in item:
                print('Skipping flatmenu not supported for QMenuBar')
                continue  # not applicable for QMenuBar

            visibility_predicate = item.get('visibility_predicate', lambda: True)
            if callable(visibility_predicate):
                visibility_predicate = visibility_predicate()
            if not visibility_predicate:
                continue

            submenu = item.get('submenu', None)
            if submenu:
                # Create a QMenu with the item's text as title
                menu = QMenu(item['text'], menubar)

                # Connect aboutToShow to dynamically populate the menu
                menu.aboutToShow.connect(
                    lambda m=menu, s=submenu: self._populate_menu_on_show(m, s)
                )

                menubar.addMenu(menu)
            else:
                # Top-level action without submenu (unusual for menubar)
                action = menubar.addAction(item['text'])
                self._configure_action(action, item)
                
        self.inner_widget = menubar
        self.layout.addWidget(self.inner_widget)
        self.reload_predicates()

    def _populate_menu_on_show(self, menu, schema):
        """Populate menu dynamically when it's about to be shown."""
        menu.clear()
        
        for item in schema:
            self._add_item_to_menu(menu, item)

    def _add_item_to_menu(self, menu, item):
        """Add a single schema item to a menu."""
        if item.get('type') == 'separator':
            menu.addSeparator()
            return
        elif item.get('type') == 'stretch':
            menu.addSeparator()  # add a separator instead because stretch is not supported for QMenu
            return
        elif item.get('type') == 'create_standard':
            widget = item.get('widget', None)
            if callable(widget):
                widget = widget()
            if widget and hasattr(widget, 'createStandardContextMenu'):
                standard_menu = widget.createStandardContextMenu()
                menu.addActions(standard_menu.actions())
                menu.addSeparator()
            return

        visibility_predicate = item.get('visibility_predicate', lambda: True)
        if callable(visibility_predicate):
            visibility_predicate = visibility_predicate()
        if not visibility_predicate:
            return

        # Handle custom widget
        widget_factory = item.get('widget', None)
        if widget_factory:
            widget = widget_factory() if callable(widget_factory) else widget_factory
            widget_action = QWidgetAction(menu)
            widget_action.setDefaultWidget(widget)
            menu.addAction(widget_action)
            return

        # Handle flatmenu - directly add items inline
        flatmenu = item.get('flatmenu', None)
        if flatmenu:
            # Call the flatmenu function to get items
            flat_items = flatmenu() if callable(flatmenu) else flatmenu
            # Recursively add each flat item to the menu
            for flat_item in flat_items:
                self._add_item_to_menu(menu, flat_item)
            return

        # Handle submenu
        submenu = item.get('submenu', None)
        if submenu:
            if callable(submenu):
                submenu = submenu()
            if isinstance(submenu, list):
                # Recursive submenu
                submenu = self._create_menu_recursive(
                    item['text'],
                    submenu,
                    parent=menu
                )

            if item.get('text') == 'Effects':
                pass
            icon_path = item.get('icon_path', None)
            if icon_path:
                submenu.setIcon(QIcon(colorize_pixmap(QPixmap(icon_path))))
            menu.addMenu(submenu)
        else:
            # Regular action
            action = menu.addAction(item['text'])
            self._configure_action(action, item)

    def _create_menu_recursive(self, title, schema, parent=None) -> QMenu:
        """
        Recursively create a QMenu from a schema list.

        Parameters
        ----------
        title : str
            The menu title
        schema : list
            List of menu item dictionaries
        parent : QWidget, optional
            Parent widget

        Returns
        -------
        QMenu
            The created menu with all items
        """
        menu = QMenu(title, parent)
        for item in schema:
            self._add_item_to_menu(menu, item)
        return menu

    def _configure_action(self, action, item):
        """
        Configure a QAction with properties from schema item.

        Parameters
        ----------
        action : QAction
            The action to configure
        item : dict
            Schema item with properties: target, icon, icon_params,
            tooltip, shortcut
        """
        # Set checkable
        checkable = item.get('checkable', False)
        if checkable:
            action.setCheckable(True)

        # Set checked state
        checked_state = item.get('checked_state', None)
        if checked_state:
            if callable(checked_state):
                checked_state = checked_state()
            action.setChecked(checked_state)

        # Set callback
        target = item.get('target', None)
        if target:
            if checkable:
                action.toggled.connect(target)
            else:
                action.triggered.connect(target)
                
        # Set icon
        icon_path = item.get('icon_path', None)
        if icon_path:
            icon_params = item.get('icon_params', {})
            opacity = icon_params.get('opacity', 1.0)
            color = icon_params.get('color', None)
            pixmap = colorize_pixmap(
                QPixmap(icon_path),
                opacity=opacity,
                color=color
            )
            action.setIcon(QIcon(pixmap))

        # Set tooltip
        tooltip = item.get('tooltip', None)
        if tooltip:
            action.setToolTip(tooltip)

        # Set shortcut
        shortcut = item.get('shortcut', None)
        if shortcut:
            action.setShortcut(shortcut)


class TextEnhancerButton(IconButton):
    on_enhancement_chunk_signal = Signal(str)
    enhancement_error_occurred = Signal(str)

    def __init__(self, parent, widget, key):
        super().__init__(parent=parent, size=22, icon_path=':/resources/icon-wand.png', tooltip='Enhance the text using a block. Right click to assign blocks.')
        self.setProperty("class", "send")
        self.widget = widget
        self.enhancement_key = key

        self.available_blocks = {}
        self.enhancing_text = ''

        self.enhancement_runnable = None
        self.on_enhancement_chunk_signal.connect(self.on_enhancement_chunk, Qt.QueuedConnection)
        self.enhancement_error_occurred.connect(self.on_enhancement_error, Qt.QueuedConnection)

    def load_available_blocks(self):
        # Get the enhancement blocks from settings
        enhancement_blocks_json = sql.get_scalar("""
            SELECT value 
            FROM settings 
            WHERE field = 'enhancement_blocks'""")

        enhancement_blocks = json.loads(enhancement_blocks_json) or {}
        block_uuids = enhancement_blocks.get(self.enhancement_key, [])
        # Query blocks by IDs if we have any
        self.available_blocks = {}
        if block_uuids:
            placeholders = ",".join(["?" for _ in block_uuids])
            self.available_blocks = sql.get_results(f"""
                SELECT name, config
                FROM blocks
                    WHERE uuid IN ({placeholders})""", tuple(block_uuids), return_type='dict')

    def on_click(self):
        self.load_available_blocks()
        menu = QMenu(self)
        new_action = menu.addAction("Add block")
        new_action.triggered.connect(self.add_enhancement_block_dialog)

        if len(self.available_blocks) > 0:
            # add separator
            menu.addSeparator()
            for name in self.available_blocks.keys():
                # Create a custom widget for each block item
                widget = QWidget()
                layout = QHBoxLayout(widget)
                layout.setContentsMargins(5, 2, 5, 2)
                layout.setSpacing(5)

                # Block name label (clickable)
                name_label = QLabel(name)
                name_label.setStyleSheet("QLabel { padding: 4px; background-color: #00000000; }")
                name_label.mousePressEvent = lambda event, block_name=name: self.on_block_selected(block_name)
                name_label.setCursor(Qt.PointingHandCursor)

                # Delete button
                delete_btn = QPushButton("×")
                delete_btn.setFixedSize(20, 20)
                delete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ff4444;
                        color: white;
                        border: none;
                        border-radius: 10px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #cc0000;
                    }
                """)
                delete_btn.clicked.connect(partial(self.delete_block, name, menu))

                layout.addWidget(name_label)
                layout.addWidget(delete_btn)

                # Create QWidgetAction and add to menu
                widget_action = QWidgetAction(menu)
                widget_action.setDefaultWidget(widget)
                menu.addAction(widget_action)

        # Bottom right of menu at top right of widget
        menu_pos = self.mapToGlobal(QPoint(self.rect().topRight().x() - menu.sizeHint().width(), self.rect().topRight().y()))
        menu.exec_(menu_pos)

    def on_block_selected(self, block_name):
        messagebox_input = self.widget.toPlainText().strip()
        if messagebox_input == '':
            display_message(
                icon=QMessageBox.Warning,
                title="Warning",
                message="No content to enhance",
            )
            return

        self.run_block(block_name)

    def delete_block(self, block_name, menu):
        # Remove the block from the enhancement_blocks setting
        existing_uuids = sql.get_scalar(f"""
            SELECT json_extract(value, '$.{self.enhancement_key}')
            FROM settings
            WHERE field = 'enhancement_blocks'""") or '[]'
        existing_uuids = json.loads(existing_uuids)

        matching_uuids = sql.get_results("""
            SELECT uuid
            FROM blocks
            WHERE name = ?""", (block_name,), return_type='list')

        new_uuids = [uuid for uuid in existing_uuids if uuid not in matching_uuids]
        # We need to properly format the JSON path for the json_set function
        json_path = f'$.{self.enhancement_key}'
        sql.execute("""
            UPDATE settings
            SET value = json_set(value, ?, json(?))
            WHERE field = 'enhancement_blocks'""", (json_path, json.dumps(new_uuids)))
        # Close the menu
        menu.close()

        # Reopen the menu
        self.click()

    def add_enhancement_block_dialog(self):
        list_dialog = TreeDialog(
            parent=self,
            title="Add Block",
            list_type='BLOCK',
            callback=self.add_enhancement_block,
        )
        list_dialog.open()

    def add_enhancement_block(self, item):
        # item is a QTreeWidgetItem
        if not item:
            return
        item = item.data(0, Qt.UserRole)
        item_id = item['id']

        # json insert into `settings`.`value` where `field` = 'enhancement_blocks'
        # where the key in the json field = self.enhancement_key
        existing_uuids = sql.get_scalar(f"""
            SELECT json_extract(value, '$.{self.enhancement_key}')
            FROM settings
            WHERE field = 'enhancement_blocks'""") or '[]'
        existing_uuids = json.loads(existing_uuids)
        existing_uuids.append(item_id)
        # We need to properly format the JSON path for the json_set function
        json_path = f'$.{self.enhancement_key}'
        sql.execute("""
            UPDATE settings
            SET value = json_set(value, ?, json(?))
            WHERE field = 'enhancement_blocks'""", (json_path, json.dumps(existing_uuids)))
        # Reopen the menu
        self.click()

    def run_block(self, block_name):
        self.enhancing_text = self.widget.toPlainText().strip()
        self.widget.clear()
        enhance_runnable = self.EnhancementRunnable(self, block_name)
        main = find_main()
        main.threadpool.start(enhance_runnable)

    class EnhancementRunnable(QRunnable):
        def __init__(self, parent, block_name):
            super().__init__()
            self.parent = parent
            self.block_name = block_name

        def run(self):
            asyncio.run(self.enhance_text())

        async def enhance_text(self):
            try:
                no_output = True
                params = {'INPUT': self.parent.enhancing_text}
                async for key, chunk in system.manager.blocks.receive_block(self.block_name, params=params):
                    self.parent.on_enhancement_chunk_signal.emit(chunk)
                    no_output = False

                if no_output:
                    self.parent.on_enhancement_error.emit('No output from block')
            except Exception as e:
                self.parent.enhancement_error_occurred.emit(str(e))

    @Slot(str)
    def on_enhancement_chunk(self, chunk):
        self.widget.insertPlainText(chunk)
        # Press key to call resize
        self.widget.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key.Key_End, Qt.KeyboardModifier.NoModifier))
        self.widget.verticalScrollBar().setValue(self.widget.verticalScrollBar().maximum())

    @Slot(str)
    def on_enhancement_error(self, error_message):
        self.widget.setPlainText(self.enhancing_text)
        self.enhancing_text = ''
        display_message_box(
            icon=QMessageBox.Warning,
            title="Enhancement error",
            text=f"An error occurred while enhancing the text: {error_message}",
            buttons=QMessageBox.Ok
        )


def colorize_pixmap(pixmap, opacity=1.0, color=None):
    if pixmap.isNull():
        return pixmap
        
    colored_pixmap = QPixmap(pixmap.size())
    colored_pixmap.fill(Qt.transparent)

    painter = QPainter()
    if not painter.begin(colored_pixmap):
        return pixmap  # Return original pixmap if painting fails
    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.drawPixmap(0, 0, pixmap)
    painter.setOpacity(opacity)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)

    from gui.style import TEXT_COLOR as current_text_color
    painter.fillRect(colored_pixmap.rect(), current_text_color if not color else color)
    painter.end()

    return colored_pixmap


class WrappingDelegate(QStyledItemDelegate):
    def __init__(self, wrap_columns, parent=None):
        super().__init__(parent=parent)
        self.wrap_columns = wrap_columns

    def createEditor(self, parent, option, index):
        if index.column() in self.wrap_columns:
            editor = QTextEdit(parent)
            editor.setWordWrapMode(QTextOption.WordWrap)
            return editor
        else:
            return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() in self.wrap_columns:
            text = index.model().data(index, Qt.EditRole)
            editor.setText(text)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() in self.wrap_columns:
            model.setData(index, editor.toPlainText(), Qt.EditRole)
        else:
            super().setModelData(editor, model, index)

    def paint(self, painter, option, index):
        if index.column() in self.wrap_columns:
            text = index.data()

            # Set the text color for the painter
            textColor = QColor(TEXT_COLOR)  #  option.palette.color(QPalette.Text)
            painter.setPen(textColor)  # Ensure we use a QColor object
            # Apply the default palette text color too
            option.palette.setColor(QPalette.Text, textColor)

            painter.save()

            textDocument = QTextDocument()
            textDocument.setDefaultFont(option.font)
            textDocument.setPlainText(text)
            textDocument.setTextWidth(option.rect.width())
            painter.translate(option.rect.x(), option.rect.y())
            textDocument.drawContents(painter)
            painter.restore()
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option, index):  # V1
        if index.column() in self.wrap_columns:
            textDocument = QTextDocument()
            textDocument.setDefaultFont(option.font)
            textDocument.setPlainText(index.data())
            textDocument.setTextWidth(option.rect.width())
            return QSize(option.rect.width(), int(textDocument.size().height()))
        else:
            return super().sizeHint(option, index)


class BakedItemDelegate(QStyledItemDelegate):
    """Custom delegate to handle styling for baked items in tree widgets"""
    
    def paint(self, painter, option, index):
        # Check if this item is baked by looking for our custom data
        item_data = index.data(Qt.UserRole)
        is_baked = False
        if isinstance(item_data, dict) and item_data.get('id'):
            # Check if the tree widget has baked_ids stored
            tree_widget = option.widget
            if hasattr(tree_widget, '_baked_ids'):
                is_baked = item_data.get('id') in tree_widget._baked_ids
        
        is_disabled = False
        if isinstance(item_data, dict) and item_data.get('id'):
            if hasattr(tree_widget, '_disabled_ids'):
                is_disabled = item_data.get('id') in tree_widget._disabled_ids

        if is_disabled:
            painter.save()
            painter.setOpacity(0.4)
            super().paint(painter, option, index)
            painter.restore()
        elif is_baked:
            super().paint(painter, option, index)

            # add a dot of accent color to the left of the text with thickness 3
            accent_color = QColor(ACCENT_COLOR_1)
            painter.setPen(accent_color)
            painter.setBrush(accent_color)
            radius = 2
            center_x = option.rect.left() - 1  # (15 if has_children else 6)
            center_y = option.rect.center().y()
            painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)
        else:
            # Use default painting for non-baked items
            super().paint(painter, option, index)


class BaseTreeWidget(QTreeWidget):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.main = find_main()
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.folder_items_mapping = {None: self}
        self._baked_ids = []  # Store baked IDs for delegate access
        
        # Set up custom delegate for baked item styling
        self.baked_delegate = BakedItemDelegate(self)
        self.setItemDelegate(self.baked_delegate)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.apply_stylesheet()

        header = self.header()
        header.setDefaultAlignment(Qt.AlignLeft)
        header.setStretchLastSection(False)
        header.setDefaultSectionSize(100)

        self.row_height = kwargs.get('row_height', 20)
        # set default row height

        # Enable drag and drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

        self.setDragDropMode(QTreeWidget.InternalMove)
        self.header().sectionResized.connect(self.update_tooltips)

    def build_columns_from_schema(self, schema):
        if not schema:
            return

        self.setColumnCount(len(schema))
        # add columns to tree from schema list
        for i, header_dict in enumerate(schema):
            # column_type = header_dict.get('type', str)
            column_visible = header_dict.get('visible', True)
            column_width = header_dict.get('width', None)
            column_stretch = header_dict.get('stretch', None)
            header_text = header_dict.get('text', '')
            wrap_text = header_dict.get('wrap_text', False)

            # # combo_widgets = ['EnvironmentComboBox', 'RoleComboBox', 'ModuleComboBox']
            # # is_combo_column = isinstance(column_type, tuple) or column_type in combo_widgets
            # # if is_combo_column:
            # #     combo_delegate = ComboBoxDelegate(self, column_type)
            # #     self.setItemDelegateForColumn(i, combo_delegate)

            if column_width:
                self.setColumnWidth(i, column_width)
            if column_stretch:
                self.header().setSectionResizeMode(i, QHeaderView.Stretch)
            if wrap_text:
                self.setItemDelegateForColumn(i, WrappingDelegate([i], self))
            self.setColumnHidden(i, not column_visible)

        headers = ['' if header_dict.get('hide_header') else header_dict.get('text', '')
                   for header_dict in schema]
        self.setHeaderLabels(headers)

    def load(self, data, **kwargs):
        folder_key = kwargs.get('folder_key', None)
        select_id = kwargs.get('select_id', None)
        select_folder_id = kwargs.get('select_folder_id', None)
        silent_select_id = kwargs.get('silent_select_id', None)  # todo dirty
        init_select = kwargs.get('init_select', False)
        readonly = kwargs.get('readonly', False)
        schema = kwargs.get('schema', [])
        append = kwargs.get('append', False)
        group_folders = kwargs.get('group_folders', False)
        default_item_icon = kwargs.get('default_item_icon', None)
        baked_ids = kwargs.get('baked_ids', [])
        support_item_nesting = kwargs.get('support_item_nesting', False)
        # Store baked_ids in the tree widget for delegate access
        self._baked_ids = baked_ids

        current_selected_id = self.get_selected_item_id()
        if not select_id and current_selected_id:
            select_id = current_selected_id

        kind = self.parent.filter_widget.get_kind() if hasattr(self.parent, 'filter_widget') else getattr(self.parent, 'kind', None)
        # kind_folders = kwargs.get('kind_folders', None)
        folder_key = folder_key.get(kind, None) if isinstance(folder_key, dict) else folder_key
        folders_data = None
        if folder_key:
            if callable(folder_key):  # todo dedupe
                folder_key = folder_key()
            folder_query = """
                SELECT 
                    id, 
                    name, 
                    parent_id, 
                    json_extract(config, '$.icon_path'),
                    type, 
                    expanded, 
                    ordr 
                FROM folders 
                WHERE `type` = ?
                ORDER BY locked DESC, pinned DESC, ordr, name
            """
            folders_data = sql.get_results(query=folder_query, params=(folder_key,))

        with block_signals(self):
            self.items_mapping = {}
            self.folder_items_mapping = {}
            if not append:
                self.clear()
                # Load folders
                dir_icon = self.style().standardIcon(QStyle.SP_DirIcon)

                while folders_data:
                    for folder_id, name, parent_id, icon_path, folder_type, expanded, order in list(folders_data):
                        if parent_id is None:
                            parent_item = self
                        else:
                            parent_item = self.folder_items_mapping.get(parent_id, None)
                            if parent_item is None:
                                continue
                        folder_item = QTreeWidgetItem(parent_item, [str(name), str(folder_id)])
                        folder_item.setData(0, Qt.UserRole, 'folder')

                        use_icon_path = icon_path or ':/resources/icon-folder.png'
                        folder_pixmap = colorize_pixmap(QPixmap(use_icon_path))
                        folder_item.setIcon(0, QIcon(folder_pixmap))
                        self.folder_items_mapping[folder_id] = folder_item
                        
                        folders_data.remove((folder_id, name, parent_id, icon_path, folder_type, expanded, order))
                        expand = (expanded == 1)
                        folder_item.setExpanded(expand)

            col_name_list = [header_dict.get('key', header_dict.get('text', '')) for header_dict in schema]
            while data:
                pass
                del_lst = []
                for r, row_data in enumerate(data):
                    parent_item = self

                    parent_id, folder_id = None, None
                    if support_item_nesting:
                        parent_id = row_data[-1]
                        if parent_id is not None and parent_id not in self.items_mapping:
                            continue
                        parent_item = self.items_mapping.get(parent_id, self)
                        row_data = row_data[:-1]  # remove parent_id

                    if folder_key is not None:
                        if len(col_name_list) != len(row_data) - 1:
                            raise ValueError('BaseTreeWidget: Schema list and row_data mismatch, last column in query must be `folder_id` if `folder_key` is set')
                        folder_id = row_data[-1]
                        if parent_item == self:
                            parent_item = self.folder_items_mapping.get(folder_id, self)
                        row_data = row_data[:-1]  # remove folder_id

                    item = QTreeWidgetItem(parent_item, [str(v) for v in row_data])
                    field_dict = {col_name_list[i]: row_data[i] for i in range(len(row_data))}
                    item.setData(0, Qt.UserRole, field_dict)
                    self.items_mapping[row_data[1]] = item
                    # data_len = len(data)
                    # data.pop(r)
                    del_lst.append(r)
                    # n_data_len = len(data)
                    # if n_data_len == data_len:
                    #     pass

                    if not readonly:
                        item.setFlags(item.flags() | Qt.ItemIsEditable)
                    else:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                    if default_item_icon:
                        pixmap = colorize_pixmap(QPixmap(default_item_icon))
                        item.setIcon(0, QIcon(pixmap))

                    for i in range(len(row_data)):
                        col_schema = schema[i]
                        column_type = col_schema.get('type', str)
                        key = col_schema.get('key', col_schema.get('text', ''))
                        column_visible = col_schema.get('visible', True)

                        if column_visible and column_type != 'text' and column_type != str:
                            widget = get_field_widget(col_schema, parent=self)
                            if not widget:
                                param_type = col_schema.get('type', 'text')
                                print(f'Widget type {param_type} not found in modules. Skipping field: {key}')
                                continue
                            # # point enter event to focus the cell
                            # widget.enterEvent = lambda x: partial(self.widget_enter_event, item, i)()
                            with block_signals(widget):
                                if hasattr(widget, 'set_value'):
                                    widget.set_value(row_data[i])
                            self.setItemWidget(item, i, widget)

                        image_key = col_schema.get('image_key', None)
                        if image_key:
                            if image_key == 'config':
                                config_index = [i for i, d in enumerate(schema) if d.get('key', d['text']) == 'config'][0]
                                config_dict = json.loads(row_data[config_index])
                                image_paths_list = get_avatar_paths_from_config(config_dict)
                            else:
                                image_index = [i for i, d in enumerate(schema) if d.get('key', d['text']) == image_key][0]
                                image_paths = row_data[image_index] or ''
                                image_paths_list = image_paths.split('//##//##//') if isinstance(image_paths, str) else image_paths  # todo
                            pixmap = path_to_pixmap(image_paths_list, diameter=25)
                            item.setIcon(i, QIcon(pixmap))

                            is_encrypted = col_schema.get('encrypt', False)
                            if is_encrypted:
                                pass
                                # todo
                for r in reversed(del_lst):
                    data.pop(r)

            if group_folders:
                for i in range(self.topLevelItemCount()):
                    item = self.topLevelItem(i)
                    if item is None:
                        continue
                    self.group_nested_folders(item)
                    self.delete_empty_folders(item)

            self.update_tooltips()
            if silent_select_id:
                self.select_items_by_id(silent_select_id)

        if init_select and self.topLevelItemCount() > 0:
            if select_id:
                self.select_items_by_id(select_id)
            elif select_folder_id:
                # select the first item in the folder
                folder_item = self.folder_items_mapping.get(select_folder_id)
                if folder_item:
                    self.setCurrentItem(folder_item)
                    item = self.currentItem()
                    self.scrollToItem(item)

            elif not silent_select_id:
                self.setCurrentItem(self.topLevelItem(0))
                item = self.currentItem()
                self.scrollToItem(item)
        else:
            if hasattr(self.parent, 'toggle_config_widget'):
                self.parent.toggle_config_widget(None)
    
    def widget_enter_event(self, item, column):
        self.setCurrentItem(item, column)
    
    def update_config(self):
        if hasattr(self.parent, 'on_cell_edited'):
            item = self.currentItem()
            self.parent.on_cell_edited(item)

    def reload_selected_item(self, data, schema):
        # data is same as in `load`
        current_id = self.get_selected_item_id()
        if current_id is None:
            return

        row_data = next((row for row in data if row[1] == current_id), None)
        if row_data:
            if len(row_data) > len(schema):
                row_data = row_data[:-1]  # remove folder_id

            with block_signals(self):
                item = self.currentItem()
                # set values for each column in item
                for i in range(len(row_data)):
                    item.setText(i, str(row_data[i]))

    def drawBranches(self, painter, rect, index):
        item = self.itemFromIndex(index)
        if item.childCount() > 0:
            icon = ':/resources/icon-expanded-solid.png' if item.isExpanded() else ':/resources/icon-collapsed-solid.png'
            icon = colorize_pixmap(path_to_pixmap(icon, diameter=10))
            indent = self.indentation() * self.getDepth(item)
            painter.drawPixmap(rect.left() + 7 + indent, rect.top() + 7, icon)
        else:
            super().drawBranches(painter, rect, index)
        # pass

    def getDepth(self, item):
        depth = 0
        while item.parent() is not None:
            item = item.parent()
            depth += 1
        return depth

    # Function to group nested folders in the tree recursively
    def group_nested_folders(self, item):
        # Keep grouping while the item has exactly one folder child
        while item.childCount() == 1 and item.child(0).data(0, Qt.UserRole) == 'folder':
            child = item.takeChild(0)

            # Update the text to the current item's text plus the child's text
            item.setText(0, item.text(0) + '/' + child.text(0))

            # Add child's children to the current item
            while child.childCount() > 0:
                item.addChild(child.takeChild(0))

        # Recur into each child item (in case there are other nested structures)
        for i in range(item.childCount()):
            self.group_nested_folders(item.child(i))

    def delete_empty_folders(self, item):
        # First, recursively check and delete empty children
        for i in reversed(range(item.childCount())):  # Reversed because we might remove items
            child = item.child(i)
            if child.data(0, Qt.UserRole) == 'folder':
                self.delete_empty_folders(child)

        # Now check the current item itself
        if item.childCount() == 0 and item.data(0, Qt.UserRole) == 'folder':
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                # If there's no parent, it means this is a top-level item
                index = self.indexOfTopLevelItem(item)
                if index != -1:
                    self.takeTopLevelItem(index)

    def get_column_value(self, column):  # todo clean
        # from gui.widgets.base import get_widget_value
        item = self.currentItem()
        if not item:
            return None

        item_widget = self.itemWidget(item, column)
        if item_widget:
            return item_widget.get_value()

        return item.text(column)
        # is_color_field = isinstance(self.itemWidget(item, column), ColorPickerWidget)
        # if is_color_field:
        #     return get_widget_value(self.itemWidget(item, column))

    def apply_stylesheet(self):
        palette = self.palette()
        palette.setColor(QPalette.Highlight, apply_alpha_to_hex(TEXT_COLOR, 0.05))
        palette.setColor(QPalette.HighlightedText, apply_alpha_to_hex(TEXT_COLOR, 0.80))
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))
        palette.setColor(QPalette.ColorRole.Button, QColor(TEXT_COLOR))
        self.setPalette(palette)

    def update_tooltips(self):
        # Skip tooltip update during initial startup to prevent hangs
        if not self.isVisible() or self.width() <= 1:
            return

        font_metrics = QFontMetrics(self.font())

        def update_item_tooltips(self, item):
            for col in range(self.columnCount()):
                text = item.text(col)
                text_width = font_metrics.horizontalAdvance(text) + 45  # Adding some padding
                column_width = self.columnWidth(col)
                if column_width == 0:
                    continue
                if text_width > column_width:
                    item.setToolTip(col, text)
                else:
                    item.setToolTip(col, "")  # Remove tooltip if not cut off

            # Recursively update tooltips for child items
            for i in range(item.childCount()):
                update_item_tooltips(self, item.child(i))

        # Update tooltips for all top-level items and their children
        # Use direct signal blocking instead of context manager for performance
        was_blocked = self.signalsBlocked()
        self.blockSignals(True)
        try:
            for i in range(self.topLevelItemCount()):
                update_item_tooltips(self, self.topLevelItem(i))
        finally:
            self.blockSignals(was_blocked)

    def get_selected_item_id(self):  # todo clean
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            return None
        id = item.text(1)
        if id.isdigit():
            return int(item.text(1))
        if id == 'None':
            return None
        return id

    def get_selected_item_ids(self):  # todo merge with above
        sel_item_ids = []
        for item in self.selectedItems():
            if item.data(0, Qt.UserRole) != 'folder':
                sel_item_ids.append(int(item.text(1)))
        return sel_item_ids

    def get_selected_folder_id(self):
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag != 'folder':
            return None
        return int(item.text(1))

    def select_items_by_id(self, ids):
        if not isinstance(ids, list):
            ids = [str(ids)]
        # map id ints to strings
        ids = [str(i) for i in ids]

        def select_recursive(item):
            item_in_ids = item.text(1) in ids
            item.setSelected(item_in_ids)

            if item_in_ids:
                self.scrollToItem(item)
                self.setCurrentItem(item)

            for child_index in range(item.childCount()):
                select_recursive(item.child(child_index))

        with block_signals(self):
            for i in range(self.topLevelItemCount()):
                select_recursive(self.topLevelItem(i))

        if hasattr(self.parent, 'on_item_selected'):
            self.parent.on_item_selected()

    def get_selected_tag(self):
        item = self.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        return tag

    def dragMoveEvent(self, event):
        dragging_item = self.currentItem()
        target_item = self.itemAt(event.pos())
        dragging_type = dragging_item.data(0, Qt.UserRole)
        target_type = target_item.data(0, Qt.UserRole) if target_item else None

        can_drop = dragging_item and target_item  # todo dedupe
        if can_drop:
            dragging_type = dragging_item.data(0, Qt.UserRole)
            if dragging_type == 'folder':
                if target_type != 'folder':
                    can_drop = False
            else:
                if target_type != 'folder' and not self.parent.support_item_nesting:
                    can_drop = False

        # distance to edge of the item
        distance = 0
        if target_item:
            rect = self.visualItemRect(target_item)
            bottom_distance = rect.bottom() - event.pos().y()
            top_distance = event.pos().y() - rect.top()
            distance = min(bottom_distance, top_distance)

        # only allow dropping on folders and reordering in between items
        if can_drop or distance < 5:
            super().dragMoveEvent(event)
        else:
            event.ignore()

    def dropEvent(self, event):
        dragging_item = self.currentItem()
        target_item = self.itemAt(event.pos())
        dragging_type = dragging_item.data(0, Qt.UserRole)
        target_type = target_item.data(0, Qt.UserRole) if target_item else None
        dragging_id = dragging_item.text(1)

        if dragging_type == 'folder':
            is_locked = sql.get_scalar(f"""SELECT locked FROM folders WHERE id = ?""", (dragging_id,)) or False
            if is_locked == 1:
                event.ignore()
                return

        can_drop = dragging_item and target_item  # todo dedupe
        if can_drop:
            dragging_type = dragging_item.data(0, Qt.UserRole)
            if dragging_type == 'folder':
                if target_type != 'folder':
                    can_drop = False

        # distance to edge of the item
        distance = 0
        if target_item:
            rect = self.visualItemRect(target_item)
            distance = min(event.pos().y() - rect.top(), rect.bottom() - event.pos().y())

        # only allow dropping on folders and reordering in between items
        if distance < 5:
            # REORDER AND/OR MOVE
            dragging_item_parent = dragging_item.parent() if dragging_item else None

            target_item_parent = target_item.parent() if target_item else None
            target_item_parent_id = target_item_parent.text(1) if target_item_parent else None
            target_item_parent_type = target_item_parent.data(0, Qt.UserRole) if target_item_parent else 'folder'

            is_same_parent = (target_item_parent == dragging_item_parent)  #  and dragging_type == 'folder')
            if is_same_parent:
                display_message('Reordering is not implemented yet', 'Error', QMessageBox.Warning)
                event.ignore()
                return
            
            if target_item_parent_type == 'folder':
                if dragging_type == 'folder':
                    self.update_folder_parent(dragging_id, target_item_parent_id)
                else:  # is an item
                    self.update_item_folder(dragging_id, target_item_parent_id)
            else: # target parent is an item
                if dragging_type == 'folder':
                    display_message('Cannot move folders into items', 'Error', QMessageBox.Warning)
                    event.ignore()
                    return
                else:  # dragging item is an item
                    self.update_item_parent(dragging_id, target_item_parent_id)

        elif not can_drop:
            event.ignore()
            return

        else:
            if target_type == 'folder':
                folder_id = target_item.text(1)
                if dragging_type == 'folder':
                    self.update_folder_parent(dragging_id, folder_id)
                else:
                    self.update_item_folder(dragging_id, folder_id)
            else:  # is an item
                item_id = target_item.text(1)
                if dragging_type == 'folder':
                    event.ignore()
                    return
                
                if not self.parent.support_item_nesting:
                    event.ignore()
                    return

                self.update_item_parent(dragging_id, item_id)

    def setItemIconButtonColumn(self, item, column, icon, func):
        btn_chat = QPushButton('')
        btn_chat.setIcon(icon)
        btn_chat.setIconSize(QSize(25, 25))
        btn_chat.clicked.connect(func)
        self.setItemWidget(item, column, btn_chat)

    def get_expanded_folder_ids(self):
        expanded_ids = []

        def recurse_children(item):
            for i in range(item.childCount()):
                child = item.child(i)
                id = child.text(1)
                if child.isExpanded():
                    expanded_ids.append(id)
                recurse_children(child)

        recurse_children(self.invisibleRootItem())
        return expanded_ids

    def update_folder_parent(self, dragging_folder_id, to_folder_id):
        sql.execute(f"UPDATE folders SET parent_id = ? WHERE id = ?", (to_folder_id, dragging_folder_id))
        if hasattr(self.parent, 'on_edited'):
            self.parent.on_edited()
        self.parent.load()
        # expand the folder
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(1) == to_folder_id:
                item.setExpanded(True)
                break

    def update_item_folder(self, dragging_item_id, to_folder_id):
        parent_id_col_cnt = sql.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{self.parent.table_name}') WHERE `name` = 'parent_id'")
        if parent_id_col_cnt != 0:
            sql.execute(f"UPDATE `{self.parent.table_name}` SET parent_id = NULL WHERE id = ?", (dragging_item_id,))
        sql.execute(f"UPDATE `{self.parent.table_name}` SET folder_id = ? WHERE id = ?", (to_folder_id, dragging_item_id))
        
        is_baked = self.parent.is_tree_item_baked()
        auto_bake = system.manager.config.get('system.auto_bake', False)
        if auto_bake and is_baked:
            self.parent.bake_item(force=True)
        if hasattr(self.parent, 'on_edited'):
            self.parent.on_edited()
        self.parent.load()

        # expand the folder
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(1) == to_folder_id:
                item.setExpanded(True)
                break
    
    def update_item_parent(self, dragging_item_id, to_item_id):
        folder_id_col_cnt = sql.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{self.parent.table_name}') WHERE `name` = 'folder_id'")
        if folder_id_col_cnt != 0:
            sql.execute(f"UPDATE `{self.parent.table_name}` SET folder_id = NULL WHERE id = ?", (dragging_item_id,))
        sql.execute(f"UPDATE `{self.parent.table_name}` SET parent_id = ? WHERE id = ?", (to_item_id, dragging_item_id))
        
        is_baked = self.parent.is_tree_item_baked()
        auto_bake = system.manager.config.get('system.auto_bake', False)
        if auto_bake and is_baked:
            self.parent.bake_item(force=True)
        if hasattr(self.parent, 'on_edited'):
            self.parent.on_edited()
        self.parent.load()
        # # expand the item parent
        # for i in range(self.topLevelItemCount()):
        #     item = self.topLevelItem(i)
        #     if item.text(1) == to_item_id:
        #         item.setExpanded(True)
        #         break


    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton and hasattr(self.parent, 'show_context_menu'):
            self.parent.show_context_menu()
            # return
        elif event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item:
                col = self.columnAt(event.pos().x())
                # # Check if the delegate for this column is an instance of ComboBoxDelegate
                # delegate = self.itemDelegateForColumn(col)
                # if isinstance(delegate, ComboBoxDelegate):
                #     # force the item into edit mode
                #     self.editItem(item, col)
            else:
                window = self.window()
                if window and isinstance(window, FramelessResizeMixin):
                    window.mouseReleaseEvent(event)
                return True  # Event handled

        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item is None:
                window = self.window()
                if window and isinstance(window, FramelessResizeMixin):
                    window.mousePressEvent(event)
                return  # Event handled

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        window = self.window()
        if window and isinstance(window, FramelessResizeMixin):
            window.mouseMoveEvent(event)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() == Qt.Key_Delete and hasattr(self.parent, 'delete_item'):
            self.parent.delete_item()


class NonSelectableItemDelegate(QStyledItemDelegate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def paint(self, painter, option, index):
        is_header = index.data(Qt.UserRole) == 'header'
        if is_header:
            option.font.setBold(True)
        super().paint(painter, option, index)

    def editorEvent(self, event, model, option, index):
        if index.data(Qt.UserRole) == 'header':
            # Disable selection/editing of header items by consuming the event
            return True
        return super().editorEvent(event, model, option, index)

    def sizeHint(self, option, index):
        # Call the base implementation to get the default size hint
        return super().sizeHint(option, index)


class TreeDialog(QDialog):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )

        self.setWindowTitle(kwargs.get('title', ''))
        self.list_type = kwargs.get('list_type', '')
        if self.list_type in ('agent', 'tool', 'module'):
            self.list_type = self.list_type.upper()
        self.callback = kwargs.get('callback', None)
        multiselect = kwargs.get('multiselect', False)
        show_blank = kwargs.get('show_blank', False)

        layout = QVBoxLayout(self)
        self.tree_widget = BaseTreeWidget(self)
        self.tree_widget.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.tree_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.tree_widget)

        # todo refactor
        if self.list_type == 'AGENT':  # or self.list_type == 'CONTACT':
            def_avatar = ':/resources/icon-agent-solid.png'  # if self.list_type == 'AGENT' else ':/resources/icon-user.png'
            col_name_list = ['name', 'id', 'config']
            empty_member_label = 'Empty agent'  # if self.list_type == 'AGENT' else 'You'
            folder_key = 'agents'  # if self.list_type == 'AGENT' else 'users'
            query = f"""
                SELECT 
                    name, 
                    uuid, 
                    config,
                    folder_id
                FROM (
                    SELECT
                        e.id,
                        e.name,
                        e.uuid,
                        e.config,
                        e.folder_id
                    FROM entities e
                    WHERE kind = '{self.list_type}'
                )
                ORDER BY id DESC"""
        elif self.list_type == 'TOOL':
            def_avatar = ':/resources/icon-tool.png'
            col_name_list = ['name', 'id', 'config']
            empty_member_label = None
            folder_key = 'tools'
            query = """
                SELECT
                    name,
                    uuid as id,
                    '{}' as config,
                    folder_id
                FROM tools
                ORDER BY name"""

        elif self.list_type == 'MODULE':
            def_avatar = ':/resources/icon-jigsaw-solid.png'
            col_name_list = ['name', 'id', 'config']
            empty_member_label = None
            folder_key = 'modules'
            query = """
                SELECT
                    name,
                    uuid as id,
                    '{}' as config,
                    folder_id
                FROM modules
                ORDER BY name"""

        # elif self.list_type == 'prompt', 'code']:
        #     def_avatar = ':/resources/icon-blocks.png'
        #     col_name_list = ['block', 'id', 'config']
        #     empty_member_label = None
        #     folder_key = 'blocks'
        #     query = f"""
        #         SELECT
        #             name,
        #             uuid,
        #             COALESCE(json_extract(config, '$.members[0].config'), config) as config,
        #             folder_id
        #         FROM blocks
        #         WHERE (json_array_length(json_extract(config, '$.members')) = 1
        #             OR json_type(json_extract(config, '$.members')) IS NULL)
        #         ORDER BY name"""

        elif self.list_type == 'text':
            def_avatar = ':/resources/icon-blocks.png'
            col_name_list = ['block', 'id', 'config']
            empty_member_label = 'Empty text block'
            folder_key = 'blocks'
            query = f"""
                SELECT
                    name,
                    uuid,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config,
                    folder_id
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                    AND COALESCE(json_extract(config, '$._TYPE'), 'text') = 'text'
                ORDER BY name"""

        elif self.list_type == 'prompt':
            def_avatar = ':/resources/icon-brain.png'
            col_name_list = ['block', 'id', 'config']
            empty_member_label = 'Empty prompt block'
            folder_key = 'blocks'
            # extract members[0] of workflow `block_type` when `members` is not null
            query = f"""
                SELECT
                    name,
                    uuid,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config,
                    folder_id
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                    AND COALESCE(json_extract(config, '$._TYPE'), 'text') = 'prompt'
                ORDER BY name"""

        elif self.list_type == 'code':
            def_avatar = ':/resources/icon-code.png'
            col_name_list = ['block', 'id', 'config']
            empty_member_label = 'Empty code block'
            folder_key = 'blocks'
            query = f"""
                SELECT
                    name,
                    uuid,
                    COALESCE(json_extract(config, '$.members[0].config'), config) as config,
                    folder_id
                FROM blocks
                WHERE (json_array_length(json_extract(config, '$.members')) = 1
                    OR json_type(json_extract(config, '$.members')) IS NULL)
                    AND COALESCE(json_extract(config, '$._TYPE'), 'text') = 'code'
                ORDER BY name"""
        else:
            raise NotImplementedError(f'List type {self.list_type} not implemented')

        column_schema = [
            {
                'text': 'Name',
                'key': 'name',
                'type': str,
                'stretch': True,
                'image_key': 'config' if self.list_type == 'agent' else None,
            },
            {
                'text': 'id',
                'key': 'id',
                'type': int,
                'visible': False,
            },
            {
                'text': 'config',
                'type': str,
                'visible': False,
            },
        ]
        self.tree_widget.build_columns_from_schema(column_schema)
        self.tree_widget.setHeaderHidden(True)

        if self.list_type == 'AGENT':
            tbl_name = 'entities'
        elif self.list_type in ['text', 'prompt', 'code']:
            tbl_name = 'blocks'
        elif self.list_type == 'TOOL':
            tbl_name = 'tools'
        else:
            tbl_name = None

        # todo clean
        data = sql.get_results(query)
        data = [
            (
                row[0],
                row[1],
                json.dumps(
                    merge_config_into_workflow_config(
                        json.loads(row[2]),
                        entity_id=row[1] if tbl_name is not None else None,
                        entity_table=tbl_name
                    )
                ) if self.list_type in ['AGENT', 'TOOL', 'text', 'prompt', 'code'] else row[2],
                row[3],
            )
            for row in data
        ]
        if empty_member_label is not None and show_blank:
            if self.list_type == 'workflow':
                pass
            empty_config = {}
            if self.list_type in ['text', 'prompt', 'code']:
                empty_config = {
                    "_TYPE": self.list_type.lower(),
                    "name": self.list_type.replace('_', ' ').title()
                }
            # elif self.list_type == 'agent':
            #     empty_config = {}
            else:
                empty_config = {
                    "_TYPE": self.list_type.lower(),
                    "name": self.list_type.replace('_', ' ').title()
                }

            data.insert(0, (empty_member_label, '', json.dumps(empty_config), None))

        self.tree_widget.load(
            data=data,
            folder_key=folder_key,
            schema=column_schema,
            readonly=True,
            default_item_icon=def_avatar,
        )

        if self.callback:
            self.tree_widget.itemDoubleClicked.connect(self.itemSelected)

    class TreeWidget(BaseTreeWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def load(self, data, **kwargs):
            super().load(data, **kwargs)

    def open(self):
        self.exec()

    def itemSelected(self, item):
        is_folder = item.data(0, Qt.UserRole) == 'folder'
        if is_folder:
            return
        self.close()
        self.callback(item)  # , linked_id=)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() != Qt.Key_Return:
            return
        item = self.tree_widget.currentItem()
        self.itemSelected(item)


class LibraryDialog(QDialog):
    """Dialog with tabs for browsing Agents, Blocks, and Tools."""

    def __init__(self, parent, callback, kind=None):
        super().__init__(parent=parent)
        self.callback = callback
        self.setWindowTitle('Library')
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )
        self.resize(400, 500)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)

        column_schema = [
            {
                'text': 'Name',
                'key': 'name',
                'type': str,
                'stretch': True,
            },
            {
                'text': 'id',
                'key': 'id',
                'type': int,
                'visible': False,
            },
            {
                'text': 'config',
                'type': str,
                'visible': False,
            },
            {
                'text': 'table',
                'key': 'table',
                'type': str,
                'visible': False,
            },
        ]

        tab_defs = [
            (
                'Agent',
                """SELECT name, uuid, config, folder_id
                   FROM entities
                   WHERE kind = 'AGENT'
                   ORDER BY id DESC""",
                'agents',
                ':/resources/icon-agent-solid.png',
                'entities',
            ),
            (
                'Block',
                """SELECT name, uuid,
                       COALESCE(
                           json_extract(config, '$.members[0].config'),
                           config
                       ) as config,
                       folder_id
                   FROM blocks
                   WHERE (json_array_length(
                              json_extract(config, '$.members')
                          ) = 1
                       OR json_type(
                              json_extract(config, '$.members')
                          ) IS NULL)
                   ORDER BY name""",
                'blocks',
                ':/resources/icon-blocks.png',
                'blocks',
            ),
            (
                'Tool',
                """SELECT name, uuid as id, '{}' as config,
                       folder_id
                   FROM tools
                   ORDER BY name""",
                'tools',
                ':/resources/icon-tool.png',
                'tools',
            ),
        ]

        for label, query, folder_key, icon, tbl_name in tab_defs:
            tree = BaseTreeWidget(self)
            tree.setDragDropMode(QAbstractItemView.NoDragDrop)
            tree.build_columns_from_schema(column_schema)
            tree.setHeaderHidden(True)

            data = sql.get_results(query)
            data = [
                (
                    row[0],
                    row[1],
                    json.dumps(
                        merge_config_into_workflow_config(
                            json.loads(row[2]),
                            entity_id=row[1],
                            entity_table=tbl_name,
                        )
                    ),
                    tbl_name,
                    row[3],
                )
                for row in data
            ]

            tree.load(
                data=data,
                folder_key=folder_key,
                schema=column_schema,
                readonly=True,
                default_item_icon=icon,
            )
            tree.itemDoubleClicked.connect(self.item_selected)
            self.tabs.addTab(tree, label)

        self.link_checkbox = QCheckBox('Link as reference', self)
        layout.addWidget(self.link_checkbox)

        kind_tab_map = {'conversation': 0, 'blocks': 1, 'tool': 2}
        if kind in kind_tab_map:
            self.tabs.setCurrentIndex(kind_tab_map[kind])

    def item_selected(self, item):
        if item.data(0, Qt.UserRole) == 'folder':
            return
        self.close()
        self.callback(item, link=self.link_checkbox.isChecked())

    def open(self):
        self.exec()


class HelpIcon(QLabel):
    def __init__(self, parent, tooltip):
        super().__init__(parent=parent)
        self.parent = parent
        pixmap = colorize_pixmap(QPixmap(':/resources/icon-info.png'), opacity=0.5)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(12, 12, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)
        self.setToolTip(tooltip)


class AlignDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.displayAlignment = Qt.AlignCenter
        super(AlignDelegate, self).paint(painter, option, index)


def clear_layout(layout, skip_count=0):
    """Clear all layouts and widgets from the given layout"""
    while layout.count() > skip_count:
        item = layout.itemAt(skip_count)
        widget = item.widget()
        if isinstance(widget, BreadcrumbWidget):
            skip_count += 1
            continue
        item = layout.takeAt(skip_count)
        if widget is not None:
            widget.deleteLater()
        else:
            child_layout = item.layout()
            if child_layout is not None:
                clear_layout(child_layout)


class EditBar(QWidget):
    def __init__(self, editing_widget):
        super().__init__(parent=None)
        self.editing_widget = editing_widget
        self.editing_module_id = find_attribute(editing_widget, 'module_id')
        self.class_name = editing_widget.__class__.__name__
        module_name = sql.get_scalar(
            "SELECT name FROM modules WHERE id = ?",
            (self.editing_module_id,)
        )
        controller = system.manager.modules.type_controllers.get('pages')
        loaded_module = None
        if controller and module_name:
            module_path = controller.get_module_path(module_name)
            import sys as _sys
            loaded_module = _sys.modules.get(module_path)
        from gui.builder import get_class_path
        class_tup = get_class_path(loaded_module, self.class_name)
        self.class_map = None
        if class_tup:
            self.class_map, _ = class_tup

        # Detect current superclass via MRO against registered Widget modules
        widget_modules = system.manager.modules.get_modules_in_folder(
            'Widgets', fetch_keys=('name', 'class'))
        self.current_superclass = None
        current_mod_name = None
        for base in type(editing_widget).__mro__:
            for mod_name, mod_cls in widget_modules:
                if base is mod_cls:
                    self.current_superclass = base
                    current_mod_name = mod_name
                    break
            if self.current_superclass:
                break

        self.page_editor = find_attribute(editing_widget, 'module_popup')

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setProperty('class', 'edit-bar')

        self.layout = QHBoxLayout(self)

        from gui.fields.combo import BaseCombo
        self.type_combo = BaseCombo()
        self.type_combo.setFixedWidth(150)

        # Group modules by origin (Core vs plugin name)
        def _get_group(cls):
            mod = getattr(cls, '__module__', '')
            if mod.startswith('plugins.'):
                return mod.split('.')[1]
            return 'Core'

        grouped = {}
        for mod_name, mod_cls in widget_modules:
            group = _get_group(mod_cls)
            grouped.setdefault(group, []).append(mod_name)

        combo_model = QStandardItemModel()
        for group in sorted(
            grouped.keys(), key=lambda g: (g != 'Core', g)
        ):
            header = QStandardItem(group)
            header.setData('header', Qt.UserRole)
            header.setEnabled(False)
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            combo_model.appendRow(header)
            for mod_name in grouped[group]:
                combo_model.appendRow(QStandardItem(mod_name))
        self.type_combo.setModel(combo_model)

        if current_mod_name:
            self.type_combo.setCurrentText(current_mod_name)
        self.type_combo.currentIndexChanged.connect(self.on_type_combo_changed)

        # self.btn_add_widget_left = IconButton(
        #     parent=self,
        #     icon_path=':/resources/icon-new.png',
        #     tooltip='Add Widget Left',
        #     size=20,
        # )

        self.layout.addWidget(self.type_combo)

        self.options_btn = IconButton(
            parent=self,
            icon_path=':/resources/icon-settings-solid.png',
            tooltip='Options',
            size=20,
        )
        self.options_btn.setProperty('class', 'send')
        self.options_btn.clicked.connect(self.show_options)
        self.layout.addWidget(self.options_btn)
        from gui.popup import PopupFields
        self.config_widget = PopupFields(self)
        self.rebuild_config_widget()

    def show_options(self):
        if self.config_widget.isVisible():
            self.config_widget.hide()
        else:
            self.config_widget.show()

    def rebuild_config_widget(self):
        new_superclass = self.type_combo.currentText()

        widget_class = system.manager.modules.get_module_class(
            module_type='Widgets',
            module_name=new_superclass,
        )
        self.config_widget.schema = getattr(widget_class, 'param_schema', [])
        self.config_widget.build_schema()

    def on_type_combo_changed(self, index):
        # Skip header items
        model = self.type_combo.model()
        if model and model.item(index):
            if model.item(index).data(Qt.UserRole) == 'header':
                return
        if not self.page_editor:
            return
        if not hasattr(self.page_editor, 'module_id'):
            pass
        if self.editing_module_id != self.page_editor.module_id:
            return
        from gui.builder import modify_class_base
        new_superclass = self.type_combo.currentText()
        new_class = modify_class_base(self.editing_module_id, self.class_map, new_superclass)
        if new_class:
            # `config` is a table json column (a dict)
            # the code needs to go in the 'data' key
            sql.execute("""
                UPDATE modules
                SET config = json_set(config, '$.data', ?)
                WHERE id = ?
            """, (new_class, self.editing_module_id))

            system.manager.load()  # _manager('modules')
            self.page_editor.load()
            self.page_editor.config_widget.widgets[0].reimport()
            self.rebuild_config_widget()

    def leaveEvent(self, event):
        type_combo_is_expanded = self.type_combo.view().isVisible()
        config_widget_shown = self.config_widget.isVisible()
        if not (type_combo_is_expanded or config_widget_shown):
            self.hide()

    def sizeHint(self):
        # size of contents
        width = self.layout.sizeHint().width()
        return QSize(width, 25)

    def showEvent(self, event):
        # move to top left of editing widget
        try:
            if self.editing_widget and not self.editing_widget.isVisible():
                return
            self.move(self.editing_widget.mapToGlobal(
            QPoint(0, -self.sizeHint().height())))
        except RuntimeError:
            pass


class FilterWidget(QWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent
        self.layout = CHBoxLayout(self)

        self.button_group = QButtonGroup(self)
        self.button_group.buttonClicked.connect(self.on_button_clicked)

        self.kind_buttons = {kind: self.FilterButton(text=kind)
                             for kind in kwargs.get('kind_list', [])}

        for i, (key, btn) in enumerate(self.kind_buttons.items()):
            self.button_group.addButton(btn, i)
            self.layout.addWidget(btn)

        default_kind = kwargs.get('kind', None)
        if default_kind:
            default_btn = self.kind_buttons.get(default_kind)
            if default_btn:
                default_btn.setChecked(True)

        self.layout.addStretch(1)

    def on_button_clicked(self, button):
        self.parent.load()

    def get_kind(self):
        for kind, btn in self.kind_buttons.items():
            if btn.isChecked():
                return kind
        return self.parent.kind

    class FilterButton(QPushButton):
        def __init__(self, text):
            super().__init__()
            self.setCheckable(True)
            self.setText(text.title())
            # set padding
            self.setStyleSheet('padding: 5px;')


class TreeButtons(CustomMenu):
    def __init__(self, parent, extra_buttons=[]):
        super().__init__(parent)
        self.schema = [
            {
                'text': 'Add',
                'icon_path': ':/resources/icon-new.png',
                'target': parent.add_item,
            },
            {
                'text': 'Delete',
                'icon_path': ':/resources/icon-minus.png',
                'target': parent.delete_item,
            },
            {
                'text': 'New Folder',
                'icon_path': ':/resources/icon-new-folder.png',
                'visibility_predicate': lambda: getattr(parent, 'folder_key', None) is not None,
                'target': parent.add_folder,
            },
            {
                'text': 'Filter',
                'icon_path': ':/resources/icon-filter.png',
                'visibility_predicate': lambda: getattr(parent, 'filterable', False),
                'target': lambda: parent.toggle_filter(),
                'checkable': True,
            },
            # {
            #     'text': 'Search',
            #     'icon_path': ':/resources/icon-search.png',
            #     'visibility_predicate': lambda: getattr(parent, 'searchable', False),
            #     'target': parent.search_rows,
            # },
        ]
        self.schema.extend(extra_buttons)
        
        self.create_toolbar(parent)


class CVBoxLayout(QVBoxLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)


class CHBoxLayout(QHBoxLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)


def save_table_config(table_name, item_id, value, ref_widget=None, key_field='config'):
    is_baked = False
    baked_in_table = sql.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{table_name}') WHERE `name` = 'baked'") > 0
    if baked_in_table:
        is_baked = sql.get_scalar(f"SELECT baked FROM {table_name} WHERE id = ?", (item_id,)) == 1

    sql.execute(f"""UPDATE `{table_name}` 
                    SET `{key_field}` = ?
                    WHERE id = ?
                """, (value, item_id,))
    if table_name == 'modules':
        metadata = get_metadata(json.loads(value))
        sql.execute(f"""UPDATE `{table_name}`
                        SET metadata = ?
                        WHERE id = ?
                    """, (json.dumps(metadata), item_id,))

    auto_bake = system.manager.config.get('system.auto_bake', False)
    if auto_bake and is_baked and ref_widget is not None and hasattr(ref_widget, 'bake_item'):
        old_name = sql.get_scalar(f"SELECT name FROM {table_name} WHERE id = ?", (item_id,))
        ref_widget.bake_item(force=True)
        config = sql.get_scalar(f"SELECT config FROM {table_name} WHERE id = ?", (item_id,), load_json=True)
        name = config.get('name', None)
        if not name:
            name = sql.get_scalar(f"SELECT name FROM {table_name} WHERE id = ?", (item_id,))
        if old_name != name:  # todo dedupe
            from gui.pages.modules import get_module_abs_path
            old_file_path = get_module_abs_path(item_id, module_name=old_name)
            os.remove(old_file_path)
    
    if ref_widget:
        current_version = getattr(ref_widget, 'current_version', None) # !! #
        if current_version:
            # Update the versions dict where the key matches current_version
            sql.execute(f"""
                UPDATE `{table_name}` 
                SET metadata = json_set(
                    metadata,
                    '$.versions.{current_version}',
                    JSON(?)
                )
                WHERE id = ?
            """, (value, item_id,))

        if hasattr(ref_widget, 'on_edited'):
            ref_widget.on_edited()


def get_field_widget(col_schema, parent=None):
    column_type = col_schema.get('type', 'text')
    column_key = col_schema.get('key', col_schema.get('name', 'unknown'))
    type_map = {  # todo temp map
        str: 'text',
        int: 'integer',
        float: 'float',
        bool: 'boolean',
    }
    if isinstance(column_type, (tuple, list)):
        col_schema['items'] = tuple(column_type)
        if column_type and not isinstance(column_type[0], str):
            col_schema.setdefault('value_type', type(column_type[0]))
        column_type = 'combo'
    elif column_type in type_map:
        column_type = type_map[column_type]
        
    if column_type == 'member_type_menu':
        pass
    widget_class = system.manager.modules.get_module_class(
        module_type='Fields',
        module_name=column_type,
    )
    widget = widget_class(parent=parent, **col_schema) if widget_class else None
    if not widget:
        print(
            f'Widget type {column_type} not found in modules. Skipping field: {column_key}')
        return None
    return widget


def set_widget_value(widget, value):
    try:
        if hasattr(widget, 'set_value'):
            widget.set_value(value)
    except Exception as e:
        import traceback
        traceback.print_exc()
        display_message(
            f'Error setting value for field {str(widget)}: {type(e).__name__}: {e}',
            icon=QMessageBox.Warning,
        )


def get_selected_pages(widget, incl_objects=False, stop_at_tree=False):  # todo temp stop
    """
    Recursively get all selected pages within the given widget.

    :param widget: The root widget to start the search from.
    :return: A dictionary with class name paths as keys and selected page names as values.
    """
    from gui.widgets.config_db_tree import ConfigDBTree
    from gui.widgets.config_joined import ConfigJoined
    from gui.widgets.config_pages import ConfigPages
    from gui.widgets.config_tabs import ConfigTabs
    from gui.widgets.file_tree import FileTree

    result = {}

    def process_widget(w, path):
        if hasattr(w, 'pages'):
            if isinstance(w, ConfigTabs) or isinstance(w, ConfigPages):
                selected_index = w.content.currentIndex()
                if len(w.pages) - 1 < selected_index or (selected_index == -1 and len(w.pages) == 0):
                    return
                selected_page_name = list(w.pages.keys())[selected_index]
                selected_page = list(w.pages.values())[selected_index]
            else:
                return

            selected_page = w.pages[selected_page_name]
            result[path] = selected_page_name if not incl_objects else (selected_page_name, selected_page)

            process_widget(selected_page, f"{path}.{selected_page_name}")

        elif hasattr(w, 'widgets'):
            for i, child_widget in enumerate(w.widgets):
                process_widget(child_widget, f"{path}.widget_{i}")
        
        elif isinstance(w, FileTree):
            expanded = []
            model = w.nav_panel.dir_model
            tree = w.nav_panel.dir_tree
            def _collect_expanded(parent_index):
                for row in range(model.rowCount(parent_index)):
                    index = model.index(row, 0, parent_index)
                    if tree.isExpanded(index):
                        expanded.append(model.filePath(index))
                        _collect_expanded(index)
            _collect_expanded(tree.rootIndex())
            file_state = {
                'current_path': str(w.current_path),
                'current_file': str(w.current_file) if w.current_file else None,
                'expanded': expanded,
                'open_files': list(w.file_preview.open_files.keys()),
                'active_tab': w.file_preview.tab_widget.currentIndex(),
            }
            result[path] = file_state if not incl_objects else (file_state, w)

        elif hasattr(w, 'config_widget'):
            if isinstance(w, ConfigDBTree):
                item_id = w.get_selected_item_id()
                if item_id is not None:
                    result[path] = item_id if not incl_objects else (item_id, w)
            if stop_at_tree:
                return
            if w.config_widget:
                process_widget(w.config_widget, f"{path}.config_widget")

    process_widget(widget, widget.__class__.__name__)
    return result


def set_selected_pages(widget, selected_pages):
    """
    Set the selected pages within the given widget based on the provided dictionary.

    :param widget: The root widget to start setting pages from.
    :param selected_pages: A dictionary with class name paths as keys and selected page names as values.
    """
    from gui.widgets.config_db_tree import ConfigDBTree
    from gui.widgets.config_joined import ConfigJoined
    from gui.widgets.config_pages import ConfigPages
    from gui.widgets.config_tabs import ConfigTabs
    from gui.widgets.file_tree import FileTree

    def process_widget(w, path):
        if path in selected_pages:
            if isinstance(w, (ConfigTabs, ConfigPages)):
                page_name = selected_pages[path]
                if page_name in w.pages:
                    if isinstance(w, ConfigTabs):
                        index = list(w.pages.keys()).index(page_name)
                        w.content.setCurrentIndex(index)
                    elif isinstance(w, ConfigPages):
                        index = list(w.pages.keys()).index(page_name)
                        w.content.setCurrentIndex(index)
                        # Update sidebar button
                        if w.bottom_to_top:
                            index = len(w.pages) - 1 - index
                        w.settings_sidebar.button_group.button(index).setChecked(True)
                    # elif isinstance(w, FileTree):
                    #     w.navigate_to(Path(selected_pages[path]), update_page_path=False)
            elif isinstance(w, FileTree):
                state = selected_pages[path]
                if not isinstance(state, dict):
                    state = {'current_path': str(state)}
                dir_path = state.get('current_path')
                if dir_path:
                    w.navigate_to(Path(dir_path), update_page_path=False)
                for folder_path in state.get('expanded', []):
                    index = w.nav_panel.dir_model.index(folder_path)
                    if index.isValid():
                        w.nav_panel.dir_tree.expand(index)
                for filepath in state.get('open_files', []):
                    w.file_preview.set_filepath(filepath)
                active_tab = state.get('active_tab', -1)
                if active_tab >= 0:
                    w.file_preview.tab_widget.setCurrentIndex(active_tab)
                current_file = state.get('current_file')
                if current_file:
                    w.current_file = Path(current_file)
                    tree = w.nav_panel.dir_tree                 
                    model = w.nav_panel.dir_model               
                    index = model.index(current_file)
                    if index.isValid():
                        tree.setCurrentIndex(index)

        if hasattr(w, 'pages'):
            for page_name, page_widget in w.pages.items():
                process_widget(page_widget, f"{path}.{page_name}")

        elif hasattr(w, 'widgets'):
            for i, child_widget in enumerate(w.widgets):
                process_widget(child_widget, f"{path}.widget_{i}")

        elif hasattr(w, 'config_widget'):
            if path in selected_pages:
                if isinstance(w, ConfigDBTree):
                    w.load(select_id=selected_pages[path])
            if w.config_widget:
                process_widget(w.config_widget, f"{path}.config_widget")

    process_widget(widget, widget.__class__.__name__)


def safe_single_shot(msec, callback):
    """Wrapper around QTimer.singleShot that catches exceptions"""
    def safe_callback():
        try:
            callback()
        except Exception as e:
            if 'already deleted' in str(e):
                return
            print(f"Timer callback error: {e}")

    QTimer.singleShot(msec, safe_callback)


class TextEditorWindow(QMainWindow):
    def __init__(self, parent):
        super(TextEditorWindow, self).__init__()
        self.parent = parent
        self.setWindowTitle('Edit field')
        self.setWindowIcon(QIcon(':/resources/icon.png'))

        self.resize(800, 600)

        self.editor = QTextEdit()
        self.editor.setPlainText(self.parent.toPlainText())
        self.editor.moveCursor(QTextCursor.End)
        self.editor.textChanged.connect(self.on_edited)
        self.setCentralWidget(self.editor)

    def on_edited(self):
        with block_signals(self.parent):
            self.parent.setPlainText(self.editor.toPlainText())
