import datetime
import json
from decimal import Decimal
from PySide6.QtGui import QColor, QCursor, QPalette, Qt
from PySide6.QtWidgets import (QLabel, QMenu, QWidget, QSizePolicy, QSplitter, QHeaderView,
                               QTableView, QAbstractItemView, QStyledItemDelegate)
from PySide6.QtCore import QAbstractTableModel, QItemSelectionModel, QModelIndex, QSortFilterProxyModel

from gui.util import FilterWidget, CVBoxLayout, TreeButtons, save_table_config
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_widget import ConfigWidget
from core.connectors.sqlite import SqliteConnector
from utils.helpers import apply_alpha_to_hex, display_message, set_module_type
from utils import sql


class BaseTableModel(QAbstractTableModel):
    """Base table model for ConfigTable"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self._headers = []
        self.schema = []
        self._decorations = {}
        self._foreground_colors = {}

    def set_data(self, data, headers=None, schema=None):
        """Set the table data"""
        self.beginResetModel()
        self._data = data or []
        self._headers = headers or []
        self.schema = schema or []
        self._decorations = {}
        self._foreground_colors = {}
        self.endResetModel()
    
    def rowCount(self, parent=QModelIndex()):
        return len(self._data)
    
    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)
    
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data):
            return None

        if role == Qt.DecorationRole:
            return self._decorations.get((index.row(), index.column()), None)

        if role == Qt.ForegroundRole:
            return self._foreground_colors.get(index.row())

        if role == Qt.DisplayRole or role == Qt.EditRole:
            row_data = self._data[index.row()]
            if index.column() < len(row_data):
                value = row_data[index.column()]
                # Convert Decimal types to string for proper display
                if isinstance(value, Decimal):
                    return str(value)
                # else:
                #     pass
                elif isinstance(value, datetime.datetime):
                    return value.strftime('%Y-%m-%d %H:%M:%S')
                return value
        
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False

        if role == Qt.DecorationRole:
            self._decorations[(index.row(), index.column())] = value
            self.dataChanged.emit(index, index, [Qt.DecorationRole])
            return True

        return False

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if section < len(self._headers):
                return self._headers[section]
        return None
    
    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable
    
    def get_row_data(self, row):
        """Get data for a specific row"""
        if 0 <= row < len(self._data):
            return self._data[row]
        return None


class ForegroundPreservingDelegate(QStyledItemDelegate):
    """Delegate that preserves custom ForegroundRole colors on selected rows."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        fg = index.data(Qt.ForegroundRole)
        if fg is not None:
            option.palette.setColor(QPalette.HighlightedText, fg)


class BaseTableWidget(QTableView):
    """Base table widget with common functionality"""
    
    def __init__(self, parent, *args, **kwargs):
        full_row_select = kwargs.pop('full_row_select', False)

        super().__init__(*args, **kwargs)
        self.parent = parent
        
        # Configure selection behavior
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Set up the model
        self.model = BaseTableModel(self)
        # self.setModel(self.model)
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.setModel(self.proxy_model)
        
        # Enable sorting by default
        self.setSortingEnabled(True)

        # Preserve custom foreground colors on selected rows
        self.setItemDelegate(ForegroundPreservingDelegate(self))

        # Apply styling
        self.apply_stylesheet()
    
    def apply_stylesheet(self):
        from gui.style import TEXT_COLOR
        palette = self.palette()
        palette.setColor(QPalette.Highlight, apply_alpha_to_hex(TEXT_COLOR, 0.05))
        palette.setColor(QPalette.HighlightedText, apply_alpha_to_hex(TEXT_COLOR, 0.80))
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))
        palette.setColor(QPalette.ColorRole.Button, QColor(TEXT_COLOR))
        self.setPalette(palette)

    def build_columns_from_schema(self, schema):
        """Build table columns from schema definition"""
        if not schema:
            return
            
        headers = []
        for header_dict in schema:
            if not isinstance(header_dict, dict):
                continue
            header_text = header_dict.get('text', '')
            headers.append(header_text)
        
        # Set the model data first to establish the correct column structure
        self.model.set_data([], headers, schema)
        
        # Now configure the columns
        for i, header_dict in enumerate(schema):
            if not isinstance(header_dict, dict):
                continue
                
            column_visible = header_dict.get('visible', True)
            column_width = header_dict.get('width', None)
            column_stretch = header_dict.get('stretch', None)
            
            if column_width:
                self.setColumnWidth(i, column_width)
            if column_stretch:
                self.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)
            
            self.setColumnHidden(i, not column_visible)

    def load(self, data, **kwargs):
        """Load data into the table"""
        select_id = kwargs.get('select_id', None)
        schema = kwargs.get('schema', [])
        
        current_selected_id = self.get_selected_item_id()
        if not select_id and current_selected_id:
            select_id = current_selected_id
        
        # Process data for display
        processed_data = []
        for row in data:
            if isinstance(row, (tuple, list)):
                processed_data.append(list(row))
            elif isinstance(row, dict):
                # Convert dict to list based on schema
                row_data = []
                for col_schema in schema:
                    key = col_schema.get('key', col_schema.get('text', '').lower())
                    row_data.append(row.get(key, ''))
                processed_data.append(row_data)
            else:
                processed_data.append([str(row)])
        
        headers = [col.get('text', '') for col in schema] if schema else []
        self.model.set_data(processed_data, headers, schema)

        # Clear any proxy model sorting to preserve original data order (e.g., from SQL ORDER BY)
        self.proxy_model.sort(-1)

        # Select the specified item
        if select_id is not None:
            self.select_item_by_id(select_id)
    
    def get_selected_item_id(self):
        """Get the ID of the currently selected item"""
        selection = self.selectionModel().currentIndex()
        if selection.isValid():
            # Map the proxy index back to the source model
            source_index = self.proxy_model.mapToSource(selection)
            row_data = self.model.get_row_data(source_index.row())
            if row_data and len(row_data) > 0:
                return row_data[0]  # Assume first column is ID
        return None
    
    def get_selected_item_ids(self):
        """Get IDs of all selected items."""
        ids = []
        for index in self.selectionModel().selectedRows():
            source_index = self.proxy_model.mapToSource(index)
            row_data = self.model.get_row_data(source_index.row())
            if row_data and len(row_data) > 0:
                ids.append(row_data[0])
        return ids

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton and hasattr(self.parent, 'show_context_menu'):
            self.parent.show_context_menu()
        super().mouseReleaseEvent(event)

    def select_item_by_id(self, item_id):
        """Select an item by its ID"""
        # from PyQt6.QtCore import QItemSelectionModel
        for row in range(self.model.rowCount()):
            row_data = self.model.get_row_data(row)
            if row_data and len(row_data) > 0 and row_data[0] == item_id:
                # Create source model index and map it to proxy model
                source_index = self.model.index(row, 0)
                proxy_index = self.proxy_model.mapFromSource(source_index)
                self.selectionModel().setCurrentIndex(
                    proxy_index, 
                    QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows | QItemSelectionModel.SelectionFlag.Current
                )
                break


@set_module_type('Widgets')
class ConfigTable(ConfigWidget):
    """Base class for a table widget without folder capabilities"""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        
        self.conf_namespace = kwargs.get('conf_namespace', None)
        self.schema = kwargs.get('schema', [])
        self.layout_type = kwargs.get('layout_type', 'vertical')
        self.resize_inversion = kwargs.get('resize_inversion', False)

        self.db_connector = kwargs.get('db_connector', SqliteConnector())
        self.table_name = kwargs.get('table_name', None)
        self.query = kwargs.get('query', None)
        self.query_params = kwargs.get('query_params', {})
        self.propagate_config = kwargs.get('propagate_config', False)
        # table_height = kwargs.get('table_height', None)
        self.readonly = kwargs.get('readonly', False)
        self.filterable = kwargs.get('filterable', False)
        self.searchable = kwargs.get('searchable', False)
        self.versionable = kwargs.get('versionable', False)
        self.dynamic_load = kwargs.get('dynamic_load', False)
        self.default_item_icon = kwargs.get('default_item_icon', None)
        # table_header_hidden = kwargs.get('table_header_hidden', False)
        # table_header_resizable = kwargs.get('table_header_resizable', True)
        self.config_widget = kwargs.get('config_widget', None)
        
        self.show_table_buttons = kwargs.get('show_table_buttons', True)
        self.add_item_options = kwargs.get('add_item_options', None)
        self.del_item_options = kwargs.get('del_item_options', None)
        self.full_row_select = kwargs.get('full_row_select', False)
        self.extra_tree_buttons = kwargs.get('extra_tree_buttons', [])

        self.layout = CVBoxLayout(self)

        self.table_container = QWidget()
        self.table_layout = CVBoxLayout(self.table_container)
        
        # self.status_label = QLabel("")
        # self.table_layout.addWidget(self.status_label)
        
        if self.filterable:
            self.filter_widget = FilterWidget(parent=self, **kwargs)
            self.filter_widget.hide()
            self.table_layout.addWidget(self.filter_widget)
        
        if self.show_table_buttons:
            self.table_buttons = TreeButtons(parent=self, extra_buttons=self.extra_tree_buttons)
            self.table_layout.addWidget(self.table_buttons)
        
        self.table = BaseTableWidget(parent=self, full_row_select=self.full_row_select)
        # self.tree.itemSelectionChanged.connect(self.on_item_selected)
        self.table.selectionModel().currentChanged.connect(self.on_item_selected)
        # self.table.horizontalHeader().setVisible(not table_header_hidden)
        
        # if not table_header_resizable:
        #     self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        
        # if table_height:
        #     self.table.setFixedHeight(table_height)
        
        # # Connect signals
        # self.table.selectionModel().currentRowChanged.connect(self.on_item_selected)
        
        # if self.dynamic_load:
        #     self.table.verticalScrollBar().valueChanged.connect(self.check_infinite_load)
        #     self.load_count = 0
        
        self.table_layout.addWidget(self.table)
        
        if self.config_widget is not None:
            splitter_orientation = Qt.Horizontal if self.layout_type == 'horizontal' else Qt.Vertical
            self.splitter = QSplitter(splitter_orientation)
            self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.splitter.setChildrenCollapsible(False)
            self.splitter.addWidget(self.table_container)
            
            config_container = QWidget()
            config_layout = CVBoxLayout(config_container)
            config_layout.addWidget(self.config_widget)
            
            self.splitter.addWidget(config_container)
            self.layout.addWidget(self.splitter)
        else:
            self.layout.addWidget(self.table_container)

    def load(self):
        """Load and display users data from database"""
        if not self.query:
            print("ConfigTable.load: No query provided")
            return

        # self.status_label.setText("Loading data...")
        try:
            data = self.db_connector.get_results(self.query, self.query_params)
            
            if hasattr(self, 'transform_data'):
                data = self.transform_data(data)
            
            col_formats = {i: col.get('format', None) for i, col in enumerate(self.schema) if col.get('format', None)}
            if col_formats:
                for i, row in enumerate(data):
                    row = list(data[i])
                    for j, format in col_formats.items():
                        row[j] = format(row[j])
                    data[i] = tuple(row)
            
            self.table.load(data, schema=self.schema)
            # self.status_label.setText(f"Loaded {len(data)}")
            
        except Exception as e:
            # self.status_label.setText(f"Error loading table: {str(e)}")
            display_message(f"Failed to load table data: {str(e)}", "Database Error")
    
    def check_infinite_load(self, value):
        """Handle infinite scrolling if enabled"""
        pass
    
    def on_edited(self, item):
        """Handle item editing"""
        pass
    
    def on_cell_edited(self, item):
        """Handle cell editing"""
        pass
    
    def on_item_selected(self):
        """Handle item selection changes"""
        # todo dedupe
        item_id = self.get_selected_item_id()
        
        if item_id and self.config_widget:
            self.toggle_config_widget(config_type='item')

            # todo clean
            is_config_in_table = self.db_connector.get_scalar(
                f"SELECT COUNT(*) FROM pragma_table_info('{self.table_name}') WHERE name = 'config'"
            ) > 0
            if self.table_name and is_config_in_table:
                json_config = self.db_connector.get_scalar(
                    f"SELECT `config` FROM `{self.table_name}`"
                    " WHERE id = ?",
                    (item_id,), load_json=True,
                )
            else:
                json_config = {'item_id': item_id}
            self.config_widget.load_config(json_config)
            self.config_widget.load()
          
            # # try:
            # #     json_metadata = json.loads(sql.get_scalar(f"""
            # #         SELECT
            # #             `metadata`
            # #         FROM `{self.table_name}`
            # #         WHERE id = ?
            # #     """, (item_id,)))
            # #     self.current_version = json_metadata.get('current_version', None)
            # # except Exception as e:
            # #     pass

            # # if ((self.table_name == 'entities' or self.table_name == 'blocks' or self.table_name == 'tools')
            # #         and json_config.get('_TYPE', 'agent') != 'workflow'):
            # if getattr(self.manager, 'config_is_workflow', False) and json_config.get('_TYPE', 'agent') != 'workflow':
            #     json_config = merge_config_into_workflow_config(json_config, entity_id=item_id, entity_table=self.table_name)

        else:
            self.toggle_config_widget(None)
    
    def save_config(self):
        """Save the config widget's config to the database."""
        if not self.table_name or not self.config_widget:
            return
        item_id = self.get_selected_item_id()
        if item_id is None:
            return
        config = self.config_widget.get_config()
        save_table_config(
            ref_widget=self,
            table_name=self.table_name,
            item_id=item_id,
            value=json.dumps(config),
        )

    def add_item(self):
        """Add a new item to the table"""
        pass
    
    def delete_item(self):
        """Delete the selected item from the table"""
        pass
    
    def rename_item(self):
        """Rename the selected item"""
        pass

    def show_context_menu(self):
        """Show the right-click context menu."""
        menu = QMenu(self)

        btn_delete = menu.addAction('Delete')
        btn_delete.triggered.connect(self.delete_item)

        self.on_context_menu(menu)
        menu.exec_(QCursor.pos())

    def on_context_menu(self, menu):
        """Hook for subclasses to add items to the context menu."""
        pass

    def add_folder(self, name=None, parent_folder=None):
        pass

    def get_selected_item_id(self):
        """Get the ID of the currently selected item"""
        return self.table.get_selected_item_id()

    def get_selected_item_ids(self):
        """Get IDs of all selected items."""
        return self.table.get_selected_item_ids()

    def select_item_by_id(self, item_id):
        """Select an item by its ID"""
        self.table.select_item_by_id(item_id)