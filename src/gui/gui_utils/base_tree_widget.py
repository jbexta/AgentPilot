import json
from collections import Counter

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPalette, QPixmap, Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMessageBox, QPushButton, QSizePolicy, QStyle, \
    QTreeWidget, QTreeWidgetItem

from gui.gui_utils.delegates import BakedItemDelegate, WrappingDelegate
from gui.gui_utils.frameless_resize_mixin import FramelessResizeMixin
from gui.gui_utils.helpers import colorize_pixmap, find_main, get_field_widget
from gui.style import TEXT_COLOR
from plugins.workflows.utils.workflows import get_avatar_paths_from_config
from utils import sql
from utils.helpers import apply_alpha_to_hex, block_signals, display_message, path_to_pixmap, tr


class BaseTreeWidget(QTreeWidget):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.main = find_main()
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.folder_items_mapping = {None: self}
        self.items_mapping = {}
        self.kind_folder_items = {}
        self._kind_names = {}  # kind -> (label, icon_path), for kind folder headers
        self._kind_parents = {}  # kind -> the referenced row's own kind, to nest under
        self._baked_ids = []  # Store baked IDs for delegate access
        self._notify_ids = {}  # ID: Attention of its chats, painted by delegate
        self._running_ids = set()  # IDs with a running chat, painted by delegate

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

        headers = ['' if header_dict.get('hide_header') else tr(header_dict.get('text', ''))
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
        group_by_kind = kwargs.get('group_by_kind', False)
        kind_folder_key = kwargs.get('kind_folder_key', None)
        # Store baked_ids in the tree widget for delegate access
        self._baked_ids = baked_ids

        current_selected_id = self.get_selected_item_id()
        if not select_id and current_selected_id:
            select_id = current_selected_id

        kind = self.parent.filter_widget.get_kind() if hasattr(self.parent, 'filter_widget') else getattr(self.parent, 'kind', None)
        # kind_folders = kwargs.get('kind_folders', None)
        folder_key = folder_key.get(kind, None) if isinstance(folder_key, dict) else folder_key
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
        # each entry gets a trailing `kind`, empty for this page's own namespace
        folders_data = []
        if folder_key:
            if callable(folder_key):  # todo dedupe
                folder_key = folder_key()
            folders_data = [tuple(row) + ('',) for row in sql.get_results(query=folder_query, params=(folder_key,))]

        kind_name_map = {}
        if group_by_kind:
            row_kinds = list(dict.fromkeys(row[-1] for row in data if row[-1]))
            kind_name_map = self._resolve_kind_names(row_kinds)
            self._kind_names = kind_name_map
            kind_row_counts = Counter(row[-1] for row in data)
            if kind_folder_key:
                for row_kind in row_kinds:
                    kind_type = kind_folder_key(row_kind)
                    folders_data += [
                        tuple(row) + (row_kind,)
                        for row in sql.get_results(query=folder_query, params=(kind_type,))
                    ]

        # a blocked scrollbar leaves the viewport unscrolled, painting rows over stale pixels
        with block_signals(self, exclude=(self.verticalScrollBar(),)):
            self.items_mapping = {}
            self.folder_items_mapping = {}
            if not append:
                self.clear()
                # `kind_folder` headers persist across `append` (paginated) loads
                self.kind_folder_items = {}
                # Load folders
                dir_icon = self.style().standardIcon(QStyle.SP_DirIcon)

                while folders_data:
                    for folder_row in list(folders_data):
                        folder_id, name, parent_id, icon_path, folder_type, expanded, order, folder_kind = folder_row
                        if parent_id is None:
                            if folder_kind:
                                kind_label, kind_icon = kind_name_map.get(folder_kind, (folder_kind, None))
                                parent_item = self._get_or_create_kind_folder(
                                    folder_kind, kind_label, kind_icon)
                            else:
                                parent_item = self
                        else:
                            parent_item = self.folder_items_mapping.get(parent_id, None)
                            if parent_item is None:
                                continue
                        folder_item = QTreeWidgetItem(parent_item, [str(name), str(folder_id)])
                        folder_item.setData(0, Qt.UserRole, 'folder')
                        folder_item.setData(1, Qt.UserRole, folder_kind)

                        use_icon_path = icon_path or ':/resources/icon-folder.png'
                        folder_pixmap = colorize_pixmap(QPixmap(use_icon_path))
                        folder_item.setIcon(0, QIcon(folder_pixmap))
                        self.folder_items_mapping[folder_id] = folder_item

                        folders_data.remove(folder_row)
                        expand = (expanded == 1)
                        folder_item.setExpanded(expand)

            col_name_list = [header_dict.get('key', header_dict.get('text', '')) for header_dict in schema]
            orphans_to_root = False
            while data:
                pass
                del_lst = []
                for r, row_data in enumerate(data):
                    parent_item = self

                    parent_id, folder_id, row_kind = None, None, None
                    if group_by_kind:
                        row_kind = row_data[-1]
                        row_data = row_data[:-1]  # remove kind

                    if support_item_nesting:
                        parent_id = row_data[-1]
                        if parent_id is not None and parent_id not in self.items_mapping and not orphans_to_root:
                            continue
                        parent_item = self.items_mapping.get(parent_id, self)
                        row_data = row_data[:-1]  # remove parent_id

                    if folder_key is not None:
                        if len(col_name_list) != len(row_data) - 1:
                            raise ValueError('BaseTreeWidget: Schema list and row_data mismatch, last column in query must be `folder_id` if `folder_key` is set')
                        folder_id = row_data[-1]
                        if parent_item == self:
                            folder_item = self.folder_items_mapping.get(folder_id, self)
                            if group_by_kind and folder_item is not self and (folder_item.data(1, Qt.UserRole) or '') != (row_kind or ''):
                                folder_item = self  # stale folder_id from another kind group
                            parent_item = folder_item
                        row_data = row_data[:-1]  # remove folder_id

                    if group_by_kind and row_kind and parent_item is self:
                        kind_label, kind_icon = kind_name_map.get(row_kind, (row_kind, None))
                        # a group holding only its namesake row would just repeat it
                        if (kind_row_counts[row_kind] == 1 and row_kind not in self.kind_folder_items
                                and str(row_data[0]) == str(kind_label)):
                            parent_item = self._get_kind_folder_parent(row_kind)[0]
                        else:
                            parent_item = self._get_or_create_kind_folder(
                                row_kind, kind_label, kind_icon)

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
                orphans_to_root = not del_lst

            if group_folders:
                for i in range(self.topLevelItemCount()):
                    item = self.topLevelItem(i)
                    if item is None:
                        continue
                    self.group_nested_folders(item)
                    self.delete_empty_folders(item)

            self.update_tooltips()
            if silent_select_id:
                self.select_items_by_id(silent_select_id, notify=False)

        if init_select and self.topLevelItemCount() > 0:
            if select_id and str(select_id) not in map(str, self.items_mapping):
                select_id = None
            if select_id:
                self.select_items_by_id(select_id, notify=str(select_id) != str(current_selected_id))
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

    def _resolve_kind_names(self, kinds):
        # Resolve `PREFIX:id` kind values (e.g. `PROJECT:9`, also as the parent
        # of `PROJECT:9:Issues`) to the referenced row's name and the page icon
        # for that type -- batched.
        by_tbl = {}  # table -> {ref_id: kind}
        for k in kinds:
            if not isinstance(k, str):
                continue
            prefix, _, rest = k.partition(':')
            ref_id = rest.partition(':')[0]
            if ref_id.isdigit():
                by_tbl.setdefault(prefix.lower() + 's', {})[int(ref_id)] = f'{prefix}:{ref_id}'
        if not by_tbl:
            return {}

        from gui import system
        page_icons = {
            name: getattr(cls, 'icon_path', None)
            for name, cls in system.manager.modules.get_modules_in_folder(
                module_type='Pages', fetch_keys=('name', 'class'))
        }

        kind_info_map = {}  # kind -> (name, icon_path)
        parent_kinds = []
        for table, id_map in by_tbl.items():
            icon_path = page_icons.get(table)
            placeholders = ','.join('?' * len(id_map))
            has_kind = sql.get_scalar(
                f"SELECT COUNT(*) FROM pragma_table_info('{table}') WHERE name = 'kind'")
            kind_col = 'kind' if has_kind else 'NULL'
            rows = sql.get_results(
                query=f"SELECT id, name, {kind_col} FROM `{table}` WHERE id IN ({placeholders})",
                params=tuple(id_map.keys()),
            )
            for ref_id, name, row_kind in rows:
                kind = id_map[ref_id]
                kind_info_map[kind] = (name, icon_path)
                # nest under the referenced row's own `PREFIX:id` kind, e.g. a
                # project task's `TASK:7` under its `PROJECT:1:Issues`
                if row_kind and row_kind.partition(':')[2].partition(':')[0].isdigit():
                    self._kind_parents[kind] = row_kind
                    parent_kinds.append(row_kind)
        if parent_kinds:
            kind_info_map.update(self._resolve_kind_names(parent_kinds))
        return kind_info_map

    @staticmethod
    def _split_kind(kind):
        """The parent kind and the name of a nested kind: `a/b` nests under
        `a`, and `PROJECT:9:Issues` under `PROJECT:9`."""
        if '/' in kind:
            parent_kind, _, name = kind.rpartition('/')
            return parent_kind, name
        parts = kind.split(':', 2)
        if len(parts) == 3:
            return ':'.join(parts[:2]), parts[2]
        return '', kind

    def _get_kind_folder_parent(self, kind):
        # The item a kind's folder nests under, and the folder's name there
        # when it comes from the kind itself (`PROJECT:9:Issues` -> `Issues`).
        parent_kind = self._kind_parents.get(kind)
        name = None
        if not parent_kind:
            parent_kind, name = self._split_kind(kind)
        if not parent_kind:
            return self, name
        parent_label, parent_icon = self._kind_names.get(
            parent_kind, (self._split_kind(parent_kind)[1], None))
        return self._get_or_create_kind_folder(parent_kind, parent_label, parent_icon), name

    def _get_or_create_kind_folder(self, kind, label, icon_path=None):
        # Lazily create a virtual, non-DB-backed header that groups rows by
        # their `kind` column value. Not user-creatable, renamable or draggable.
        folder_item = self.kind_folder_items.get(kind, None)
        if folder_item is None:
            parent, name = self._get_kind_folder_parent(kind)
            if name is not None and parent is not self:
                label = name
            folder_item = QTreeWidgetItem(parent, [str(label), ''])
            folder_item.setData(0, Qt.UserRole, 'kind_folder')
            folder_item.setData(1, Qt.UserRole, kind)
            folder_pixmap = colorize_pixmap(QPixmap(icon_path or ':/resources/icon-folder.png'))
            folder_item.setIcon(0, QIcon(folder_pixmap))
            folder_item.setFlags(folder_item.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsDragEnabled)
            folder_item.setExpanded(True)
            self.kind_folder_items[kind] = folder_item
        return folder_item

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

    def select_items_by_id(self, ids, notify=True):
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

        with block_signals(self, exclude=(self.verticalScrollBar(),)):
            for i in range(self.topLevelItemCount()):
                select_recursive(self.topLevelItem(i))

        if notify and hasattr(self.parent, 'on_item_selected'):
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

        # `kind_folder` headers only accept drops when the page maps kinds to
        # a folder namespace (`kind_folder_key`)
        supports_kind_drop = getattr(self.parent, 'kind_folder_key', None) is not None
        target_parent_type = target_item.parent().data(0, Qt.UserRole) if (target_item and target_item.parent()) else None
        if 'kind_folder' in (target_type, target_parent_type) and not supports_kind_drop:
            event.ignore()
            return

        folder_target_types = ('folder', 'kind_folder') if supports_kind_drop else ('folder',)
        can_drop = dragging_item and target_item  # todo dedupe
        if can_drop:
            dragging_type = dragging_item.data(0, Qt.UserRole)
            if dragging_type == 'folder':
                if target_type not in folder_target_types:
                    can_drop = False
            else:
                if target_type not in folder_target_types and not self.parent.support_item_nesting:
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

        # `kind_folder` headers only accept drops when the page maps kinds to
        # a folder namespace (`kind_folder_key`)
        supports_kind_drop = getattr(self.parent, 'kind_folder_key', None) is not None
        target_parent_type = target_item.parent().data(0, Qt.UserRole) if (target_item and target_item.parent()) else None
        if 'kind_folder' in (target_type, target_parent_type) and not supports_kind_drop:
            event.ignore()
            return

        if dragging_type == 'folder':
            is_locked = sql.get_scalar(f"""SELECT locked FROM folders WHERE id = ?""", (dragging_id,)) or False
            if is_locked == 1:
                event.ignore()
                return

        move = self.parent.move_folder if dragging_type == 'folder' else self.parent.move_item

        if target_type == 'kind_folder':
            move(dragging_id, kind=target_item.data(1, Qt.UserRole))
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

            if target_item_parent_type == 'kind_folder':
                move(dragging_id, kind=target_item_parent.data(1, Qt.UserRole))
                return

            if target_item_parent_type == 'folder':
                move(dragging_id, target_item_parent_id)
            else: # target parent is an item
                if dragging_type == 'folder':
                    display_message('Cannot move folders into items', 'Error', QMessageBox.Warning)
                    event.ignore()
                    return
                else:  # dragging item is an item
                    self.parent.move_item(dragging_id, parent_item=target_item_parent_id)

        elif not can_drop:
            event.ignore()
            return

        else:
            if target_type == 'folder':
                move(dragging_id, target_item.text(1))
            else:  # is an item
                item_id = target_item.text(1)
                if dragging_type == 'folder':
                    event.ignore()
                    return

                if not self.parent.support_item_nesting:
                    event.ignore()
                    return

                self.parent.move_item(dragging_id, parent_item=item_id)

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

        if getattr(self.parent, 'kind_folder_key', None) is not None:
            # adopt the target folder's kind group ('' when moving to root)
            folder_item = self.folder_items_mapping.get(int(to_folder_id)) if to_folder_id else None
            kind = (folder_item.data(1, Qt.UserRole) if folder_item else None) or ''
            self.set_item_kind(dragging_item_id, kind)

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
        if getattr(self.parent, 'kind_folder_key', None) is not None:
            # adopt the new parent item's kind
            kind = sql.get_scalar(f"SELECT kind FROM `{self.parent.table_name}` WHERE id = ?", (to_item_id,)) or ''
            self.set_item_kind(dragging_item_id, kind)

        if hasattr(self.parent, 'on_edited'):
            self.parent.on_edited()
        self.parent.load()
        # # expand the item parent
        # for i in range(self.topLevelItemCount()):
        #     item = self.topLevelItem(i)
        #     if item.text(1) == to_item_id:
        #         item.setExpanded(True)
        #         break

    def set_item_kind(self, item_id, kind):
        """Set an item's kind, including all its nested subitems."""
        table = self.parent.table_name
        sql.execute(f"""
            WITH RECURSIVE sub(id) AS (
                SELECT ? UNION ALL
                SELECT t.id FROM `{table}` t JOIN sub ON t.parent_id = sub.id
            )
            UPDATE `{table}` SET kind = ? WHERE id IN (SELECT id FROM sub)
        """, (item_id, kind))

    def move_to_kind_group(self, dragging_type, dragging_id, kind):
        """Drop onto a `kind_folder` header: move the item/folder into that group, top-level."""
        table = self.parent.table_name
        if dragging_type == 'folder':
            subtree = """
                WITH RECURSIVE sub(id) AS (
                    SELECT ? UNION ALL
                    SELECT f.id FROM folders f JOIN sub ON f.parent_id = sub.id
                )
            """
            sql.execute(subtree + "UPDATE folders SET type = ? WHERE id IN (SELECT id FROM sub)",
                        (dragging_id, self.parent.kind_folder_key(kind)))
            item_ids = sql.get_results(subtree + f"SELECT id FROM `{table}` WHERE folder_id IN (SELECT id FROM sub)",
                                       (dragging_id,), return_type='list')
            for item_id in item_ids:
                self.set_item_kind(item_id, kind)
            sql.execute("UPDATE folders SET parent_id = NULL WHERE id = ?", (dragging_id,))
        else:
            self.set_item_kind(dragging_id, kind)
            sql.execute(f"UPDATE `{table}` SET folder_id = NULL, parent_id = NULL WHERE id = ?", (dragging_id,))
        if hasattr(self.parent, 'on_edited'):
            self.parent.on_edited()
        self.parent.load()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton and hasattr(self.parent, 'show_context_menu'):
            self.parent.show_context_menu()
            return
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
