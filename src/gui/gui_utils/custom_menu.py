from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QCursor, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QMenuBar, QSizePolicy, QToolBar, QToolButton, QWidget, QWidgetAction

from gui.gui_utils.layouts import CVBoxLayout
from gui.gui_utils.helpers import colorize_pixmap
from utils.helpers import convert_to_safe_case


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

        if callable(schema):
            schema = schema()
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

        # Set enabled state
        enabled = item.get('enabled', None)
        if enabled is not None:
            if callable(enabled):
                enabled = enabled()
            action.setEnabled(bool(enabled))

        # Set tooltip
        tooltip = item.get('tooltip', None)
        if tooltip:
            action.setToolTip(tooltip)

        # Set shortcut
        shortcut = item.get('shortcut', None)
        if shortcut:
            action.setShortcut(shortcut)
