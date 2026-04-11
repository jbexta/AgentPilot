"""
H5 Studio - HDF5 file viewer and editor.
Provides tree navigation, dataset viewing, and metadata display for HDF5 files.
Optimized for large datasets with lazy loading and pagination.
"""
import os

import h5py
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QHeaderView, QGroupBox,
    QTreeWidgetItem, QSpinBox, QComboBox
)
from PySide6.QtCore import Qt

from gui.util import find_main, CVBoxLayout, CHBoxLayout, BaseTreeWidget
from gui.widgets.config_tabs import ConfigTabs
from gui.widgets.chart_widget import ChartWidget
from core.connectors.h5 import PriceFile
from gui.widgets.config_joined import ConfigJoined
from utils.helpers import set_module_type


@set_module_type('Studios')
class H5Studio(ConfigTabs):
    """
    HDF5 file viewer and editor studio.

    Features:
    - Tree view of HDF5 groups and datasets (lazy loaded)
    - Dataset viewing in table format (paginated)
    - Metadata display (shape, dtype, attributes)
    - Basic editing capabilities
    """

    associated_extensions = ['h5']

    def __init__(self, parent=None):
        super().__init__(parent)

        self.main = find_main()
        self.h5_file = None

        self.pages = {
            'Chart': self.H5StudioChartTab(parent=self),
            'Data': self.H5StudioDataTab(parent=self),
        }
        self.build_schema()

    def open_file(self, filepath=None):
        """Open an HDF5 file."""
        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(
                self,
                "Open HDF5 File",
                "",
                "HDF5 Files (*.h5 *.hdf5);;All Files (*)"
            )

        if not filepath or not os.path.exists(filepath):
            return

        try:
            self.h5_file = PriceFile(filepath)
            self.pages['Data'].load()
            self.pages['Chart'].load()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file: {str(e)}")

    class H5StudioChartTab(ChartWidget):
        """Chart tab for visualizing OHLC data from PriceFile H5 files."""

        def __init__(self, parent):
            super().__init__(parent=parent)

    class H5StudioDataTab(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent, layout_type='horizontal')
            self.current_dataset_path = None
            self.data_panel = self.H5StudioDataConfigWidget(parent=self)
            self.tree_widget = H5TreeWidget(parent=self)
            self.tree_widget.itemClicked.connect(self.on_item_clicked)
            self.widgets = [
                self.tree_widget,
                self.data_panel,
            ]

        @property
        def h5_file(self):
            return self.parent.h5_file

        def on_item_clicked(self, item, column):
            """Handle tree item click."""
            if not self.h5_file:
                return

            item_type = item.data(0, Qt.UserRole)
            path = item.data(0, Qt.UserRole + 1)

            with self.h5_file as f:
                if item_type == 'dataset' and path:
                    dataset = f[path]
                    self.current_dataset_path = path
                    self.data_panel.data_viewer.display_dataset(path, dataset.shape, dataset.dtype)
                    self.data_panel.metadata_panel.display_metadata(dataset, path)
                    # self.status_label.setText(f"Dataset: {path} | Shape: {dataset.shape} | Dtype: {dataset.dtype}")
                elif item_type == 'group':
                    self.current_dataset_path = None
                    self.data_panel.data_viewer.clear()
                    group = f[path] if path and path != '/' else f
                    self.data_panel.metadata_panel.display_group_metadata(group, path or '/')

        class H5StudioDataConfigWidget(ConfigJoined):
            def __init__(self, parent):
                super().__init__(parent)
                self.data_viewer = DatasetViewer(parent=self)
                self.metadata_panel = MetadataPanel(parent=self)

                self.widgets = [
                    self.data_viewer,
                    self.metadata_panel,
                ]


class H5TreeWidget(BaseTreeWidget):
    """
    Tree widget for displaying HDF5 file structure.
    Uses lazy loading - only loads children when a group is expanded.
    """

    PLACEHOLDER_KEY = '_h5_placeholder_'

    def __init__(self, parent):
        super().__init__(parent)
        self.setHeaderLabels(['Name', 'Type'])
        self.setColumnWidth(0, 200)
        self.setColumnWidth(1, 60)
        self.setHeaderHidden(True)
        # self.setRowHead

        # Connect expand signal for lazy loading
        self.itemExpanded.connect(self.on_item_expanded)

    @property
    def h5_file(self):
        return self.parent.parent.h5_file
        # return find_attribute(self, 'h5_file')

    def load(self):
        """Load HDF5 file structure into tree (top level only)."""
        self.clear()
        self.folder_items_mapping = {'/': self}
        with self.h5_file as f:
            self._populate_level(f, self, '/')

        # Select the first item to update DatasetViewer and MetadataPanel
        if self.topLevelItemCount() > 0:
            first_item = self.topLevelItem(0)
            self.setCurrentItem(first_item)
            self.itemClicked.emit(first_item, 0)

    def _populate_level(self, group, parent_item, path):
        """Populate only immediate children of a group (not recursive)."""
        for name in group.keys():
            item_path = f"{path}{name}" if path == '/' else f"{path}/{name}"
            obj = group[name]

            if isinstance(obj, h5py.Group):
                # Group (folder)
                tree_item = QTreeWidgetItem(parent_item)
                tree_item.setText(0, name)
                tree_item.setText(1, 'Group')
                tree_item.setData(0, Qt.UserRole, 'group')
                tree_item.setData(0, Qt.UserRole + 1, item_path)
                tree_item.setData(0, Qt.UserRole + 2, False)  # children_loaded flag

                self.folder_items_mapping[item_path] = tree_item

                # Add placeholder child if group has children (to show expand arrow)
                if len(obj.keys()) > 0:
                    placeholder = QTreeWidgetItem(tree_item)
                    placeholder.setData(0, Qt.UserRole, self.PLACEHOLDER_KEY)

            elif isinstance(obj, h5py.Dataset):
                # Dataset
                tree_item = QTreeWidgetItem(parent_item)
                tree_item.setText(0, name)
                tree_item.setText(1, 'Dataset')
                tree_item.setData(0, Qt.UserRole, 'dataset')
                tree_item.setData(0, Qt.UserRole + 1, item_path)

    def on_item_expanded(self, item):
        """Load children when a group is expanded (lazy loading)."""
        if not self.h5_file:
            return

        item_type = item.data(0, Qt.UserRole)
        children_loaded = item.data(0, Qt.UserRole + 2)

        if item_type == 'group' and not children_loaded:
            # Remove placeholder
            for i in range(item.childCount()):
                child = item.child(i)
                if child and child.data(0, Qt.UserRole) == self.PLACEHOLDER_KEY:
                    item.removeChild(child)
                    break

            # Load actual children
            path = item.data(0, Qt.UserRole + 1)
            with self.h5_file as f:
                group = f[path]
                self._populate_level(group, item, path)

            # Mark as loaded
            item.setData(0, Qt.UserRole + 2, True)


class DatasetViewer(QWidget):
    """
    Widget for displaying HDF5 dataset contents.
    Uses pagination to handle large datasets efficiently.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        # self.current_dataset = None
        self.page_size = 1000
        self.current_page = 0
        self.total_rows = 0
        self.total_pages = 0

        layout = CVBoxLayout(self)

        # Slice controls for >2D arrays
        self.slice_widget = QWidget()
        slice_layout = CHBoxLayout(self.slice_widget)
        slice_layout.addWidget(QLabel("Dimension:"))

        self.dim_combo = QComboBox()
        self.dim_combo.currentIndexChanged.connect(self.on_dimension_changed)
        slice_layout.addWidget(self.dim_combo)

        slice_layout.addWidget(QLabel("Slice:"))
        self.slice_spin = QSpinBox()
        self.slice_spin.valueChanged.connect(self.on_slice_changed)
        slice_layout.addWidget(self.slice_spin)

        slice_layout.addStretch()
        self.slice_widget.setVisible(False)
        layout.addWidget(self.slice_widget)

        # Table widget
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setVisible(False)
        self.table.cellChanged.connect(self.on_cell_changed)
        layout.addWidget(self.table)

        # Pagination controls
        self.pagination_widget = QWidget()
        pagination_layout = CHBoxLayout(self.pagination_widget)

        self.first_btn = QPushButton("<<")
        self.first_btn.setFixedWidth(40)
        self.first_btn.clicked.connect(self.go_first)
        pagination_layout.addWidget(self.first_btn)

        self.prev_btn = QPushButton("<")
        self.prev_btn.setFixedWidth(40)
        self.prev_btn.clicked.connect(self.go_prev)
        pagination_layout.addWidget(self.prev_btn)

        self.page_label = QLabel("Page 0 / 0")
        pagination_layout.addWidget(self.page_label)

        self.next_btn = QPushButton(">")
        self.next_btn.setFixedWidth(40)
        self.next_btn.clicked.connect(self.go_next)
        pagination_layout.addWidget(self.next_btn)

        self.last_btn = QPushButton(">>")
        self.last_btn.setFixedWidth(40)
        self.last_btn.clicked.connect(self.go_last)
        pagination_layout.addWidget(self.last_btn)

        pagination_layout.addStretch()

        pagination_layout.addWidget(QLabel("Rows per page:"))
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(['100', '500', '1000', '5000', '10000'])
        self.page_size_combo.setCurrentText('1000')
        self.page_size_combo.currentTextChanged.connect(self.on_page_size_changed)
        pagination_layout.addWidget(self.page_size_combo)

        # self.rows_label = QLabel("(0 total rows)")
        # pagination_layout.addWidget(self.rows_label)

        self.pagination_widget.setVisible(False)
        layout.addWidget(self.pagination_widget)

        self.slice_dim = 0
        self.slice_index = 0

    @property
    def h5_file(self):
        return self.parent.parent.h5_file

    @property
    def current_dataset_path(self):
        return self.parent.current_dataset_path

    @current_dataset_path.setter
    def current_dataset_path(self, value):
        self.parent.current_dataset_path = value

    def display_dataset(self, dataset_path, shape, dtype):
        """Display dataset in table with pagination."""
        self.current_dataset_path = dataset_path
        self.current_page = 0
        self._shape = shape
        self._dtype = dtype

        ndim = len(shape)

        # Check for compound dtype (structured array)
        is_compound = dtype.names is not None

        if ndim == 0:
            # Scalar
            self.slice_widget.setVisible(False)
            self.pagination_widget.setVisible(False)
            self.table.blockSignals(True)
            self.table.setRowCount(1)
            self.table.setColumnCount(1)
            with self.h5_file as f:
                scalar_value = f[dataset_path][()]
            self.table.setItem(0, 0, QTableWidgetItem(str(scalar_value)))
            self.table.blockSignals(False)

        elif ndim == 1:
            # 1D array (or 1D compound array = table with named columns)
            self.slice_widget.setVisible(False)
            self.total_rows = shape[0]
            self._setup_pagination()
            self._load_page(0)

        elif ndim == 2:
            # 2D array
            self.slice_widget.setVisible(False)
            self.total_rows = shape[0]
            self._setup_pagination()
            self._load_page(0)

        else:
            # >2D array - show slice controls
            self.slice_widget.setVisible(True)
            self.dim_combo.blockSignals(True)
            self.dim_combo.clear()
            for i in range(ndim - 2):
                self.dim_combo.addItem(f"Dim {i}")
            self.dim_combo.blockSignals(False)
            self.slice_dim = 0
            self.slice_spin.setRange(0, shape[0] - 1)
            self.slice_spin.setValue(0)
            self._display_slice()

    def _setup_pagination(self):
        """Setup pagination based on total rows."""
        self.total_pages = max(1, (self.total_rows + self.page_size - 1) // self.page_size)
        self.pagination_widget.setVisible(self.total_rows > self.page_size)
        # self.rows_label.setText(f"({self.total_rows:,} total rows)")
        self._update_pagination_buttons()

    def _update_pagination_buttons(self):
        """Update pagination button states."""
        self.first_btn.setEnabled(self.current_page > 0)
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < self.total_pages - 1)
        self.last_btn.setEnabled(self.current_page < self.total_pages - 1)
        self.page_label.setText(f"Page {self.current_page + 1} / {self.total_pages}")

    def _load_page(self, page):
        """Load a specific page of data."""
        if self.current_dataset_path is None:
            return

        self.current_page = page
        self.table.blockSignals(True)

        shape = self._shape
        ndim = len(shape)
        dtype = self._dtype

        start_row = page * self.page_size
        end_row = min(start_row + self.page_size, self.total_rows)
        num_rows = end_row - start_row

        with self.h5_file as f:
            dataset = f[self.current_dataset_path]

            # Check for compound dtype (structured array with named fields)
            if dtype.names is not None:
                # Compound dtype - use field names as columns
                field_names = list(dtype.names)
                num_cols = len(field_names)
                data = dataset[start_row:end_row]

                self.table.setRowCount(num_rows)
                self.table.setColumnCount(num_cols)
                self.table.setHorizontalHeaderLabels(field_names)

                for i in range(num_rows):
                    for j, field in enumerate(field_names):
                        val = data[i][field]
                        self.table.setItem(i, j, QTableWidgetItem(str(val)))

            elif ndim == 1:
                data = dataset[start_row:end_row]
                self.table.setRowCount(num_rows)
                self.table.setColumnCount(1)
                self.table.setHorizontalHeaderLabels(['Value'])
                for i, val in enumerate(data):
                    self.table.setItem(i, 0, QTableWidgetItem(str(val)))

            elif ndim == 2:
                cols = min(shape[1], 100)
                data = dataset[start_row:end_row, :cols]
                self.table.setRowCount(num_rows)
                self.table.setColumnCount(cols)
                # Generate column headers (0, 1, 2, ... or from attributes if available)
                col_headers = self._get_column_headers(cols, dataset)
                self.table.setHorizontalHeaderLabels(col_headers)
                for i in range(num_rows):
                    for j in range(cols):
                        self.table.setItem(i, j, QTableWidgetItem(str(data[i, j])))

        self.table.blockSignals(False)
        self._update_pagination_buttons()

    def _get_column_headers(self, num_cols, dataset=None):
        """Get column headers from dataset attributes or generate default ones."""
        if dataset is None:
            return [str(i) for i in range(num_cols)]

        # Check common attribute names for column headers
        attrs = dataset.attrs
        for attr_name in ['column_names', 'columns', 'col_names', 'headers', 'fields']:
            if attr_name in attrs:
                headers = attrs[attr_name]
                if hasattr(headers, 'tolist'):
                    headers = headers.tolist()
                if isinstance(headers, (list, tuple, np.ndarray)):
                    # Decode bytes if necessary
                    headers = [h.decode('utf-8') if isinstance(h, bytes) else str(h) for h in headers]
                    return headers[:num_cols]

        # Default: numeric column indices
        return [str(i) for i in range(num_cols)]

    def _display_slice(self):
        """Display a 2D slice of a >2D array with pagination."""
        if self.current_dataset_path is None:
            return

        shape = self._shape
        ndim = len(shape)

        # Calculate total rows for the slice
        slices = [slice(None)] * ndim
        slices[self.slice_dim] = self.slice_index

        # Get shape of the resulting slice
        slice_shape = list(shape)
        slice_shape.pop(self.slice_dim)

        # For >2D, we flatten to 2D, taking first indices
        while len(slice_shape) > 2:
            slice_shape.pop(0)

        self.total_rows = slice_shape[0] if slice_shape else 1
        self._setup_pagination()
        self._load_slice_page(0)

    def _load_slice_page(self, page):
        """Load a page from a sliced >2D array."""
        if self.current_dataset_path is None:
            return

        self.current_page = page
        self.table.blockSignals(True)

        shape = self._shape
        ndim = len(shape)

        start_row = page * self.page_size
        end_row = min(start_row + self.page_size, self.total_rows)

        # Build slice tuple
        slices = [slice(None)] * ndim
        slices[self.slice_dim] = self.slice_index

        with self.h5_file as f:
            data = f[self.current_dataset_path][tuple(slices)]

            # Flatten to 2D if needed
            while len(data.shape) > 2:
                data = data[0]

            # Get the page of data
            cols = min(data.shape[1], 100) if len(data.shape) > 1 else 1
            page_data = data[start_row:end_row]

            num_rows = end_row - start_row
            self.table.setRowCount(num_rows)
            self.table.setColumnCount(cols)

            if len(page_data.shape) == 1:
                for i in range(num_rows):
                    self.table.setItem(i, 0, QTableWidgetItem(str(page_data[i])))
            else:
                for i in range(num_rows):
                    for j in range(cols):
                        self.table.setItem(i, j, QTableWidgetItem(str(page_data[i, j])))

        self.table.blockSignals(False)
        self._update_pagination_buttons()

    def go_first(self):
        """Go to first page."""
        if self.slice_widget.isVisible():
            self._load_slice_page(0)
        else:
            self._load_page(0)

    def go_prev(self):
        """Go to previous page."""
        if self.current_page > 0:
            if self.slice_widget.isVisible():
                self._load_slice_page(self.current_page - 1)
            else:
                self._load_page(self.current_page - 1)

    def go_next(self):
        """Go to next page."""
        if self.current_page < self.total_pages - 1:
            if self.slice_widget.isVisible():
                self._load_slice_page(self.current_page + 1)
            else:
                self._load_page(self.current_page + 1)

    def go_last(self):
        """Go to last page."""
        if self.slice_widget.isVisible():
            self._load_slice_page(self.total_pages - 1)
        else:
            self._load_page(self.total_pages - 1)

    def on_page_size_changed(self, text):
        """Handle page size change."""
        self.page_size = int(text)
        self.current_page = 0
        self._setup_pagination()
        if self.slice_widget.isVisible():
            self._load_slice_page(0)
        else:
            self._load_page(0)

    def on_dimension_changed(self, index):
        """Handle dimension selection change."""
        if self.current_dataset_path is None:
            return
        self.slice_dim = index
        shape = self._shape
        self.slice_spin.setRange(0, shape[index] - 1)
        self.slice_spin.setValue(0)
        self._display_slice()

    def on_slice_changed(self, value):
        """Handle slice index change."""
        self.slice_index = value
        self._display_slice()

    def on_cell_changed(self, row, col):
        """Handle cell edit."""
        if self.current_dataset_path is None:
            return

        item = self.table.item(row, col)
        if item is None:
            return

        try:
            value = self._dtype.type(item.text())
            shape = self._shape
            ndim = len(shape)

            # Calculate actual row index including pagination offset
            actual_row = self.current_page * self.page_size + row

            with self.h5_file as f:
                dataset = f[self.current_dataset_path]
                if ndim == 1:
                    dataset[actual_row] = value
                elif ndim == 2:
                    dataset[actual_row, col] = value
                else:
                    # >2D - update the slice
                    idx = [0] * ndim
                    idx[self.slice_dim] = self.slice_index
                    # Fill in remaining dimensions
                    remaining_dims = [i for i in range(ndim) if i != self.slice_dim]
                    if len(remaining_dims) >= 2:
                        idx[remaining_dims[-2]] = actual_row
                        idx[remaining_dims[-1]] = col
                    dataset[tuple(idx)] = value

        except (ValueError, TypeError) as e:
            QMessageBox.warning(self, "Invalid Value", f"Could not convert value: {str(e)}")
            # Reload current page
            if self.slice_widget.isVisible():
                self._load_slice_page(self.current_page)
            else:
                self._load_page(self.current_page)

    def clear(self):
        """Clear the table."""
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.slice_widget.setVisible(False)
        self.pagination_widget.setVisible(False)
        self.current_dataset_path = None


class MetadataPanel(QWidget):
    """Panel for displaying dataset metadata and attributes."""

    def __init__(self, parent):
        super().__init__(parent)
        layout = CVBoxLayout(self)

        # Info group
        self.info_group = QGroupBox("Dataset Info")
        info_layout = CVBoxLayout(self.info_group)

        self.size_label = QLabel("Size: -")
        info_layout.addWidget(self.size_label)

        layout.addWidget(self.info_group)

        # Attributes group
        self.attrs_group = QGroupBox("Attributes")
        attrs_layout = CVBoxLayout(self.attrs_group)

        self.attrs_table = QTableWidget()
        self.attrs_table.setColumnCount(2)
        self.attrs_table.setHorizontalHeaderLabels(['Key', 'Value'])
        self.attrs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        attrs_layout.addWidget(self.attrs_table)

        layout.addWidget(self.attrs_group)

    def display_metadata(self, dataset, path):
        """Display metadata for a dataset."""
        self.info_group.setTitle(f"Dataset: {path}")
        self.size_label.setText(f"Size: {dataset.size:,} elements")

        # Display attributes
        self._display_attributes(dataset.attrs)

    def display_group_metadata(self, group, path):
        """Display metadata for a group."""
        self.info_group.setTitle(f"Group: {path}")

        num_items = len(group.keys())
        self.size_label.setText(f"Size: {num_items} items")

        # Display attributes
        self._display_attributes(group.attrs)

    def _display_attributes(self, attrs):
        """Display HDF5 attributes in table."""
        self.attrs_table.setRowCount(len(attrs))

        for i, (key, value) in enumerate(attrs.items()):
            self.attrs_table.setItem(i, 0, QTableWidgetItem(str(key)))
            self.attrs_table.setItem(i, 1, QTableWidgetItem(str(value)))
