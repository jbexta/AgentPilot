
from PySide6.QtCore import Signal, Slot, QRunnable, QTimer
from PySide6.QtWidgets import *
from PySide6.QtGui import Qt
from typing_extensions import override

from src.utils.helpers import block_signals
from src.gui.util import find_main_widget, safe_single_shot

from src.gui.widgets.config_json_tree import ConfigJsonTree


class ConfigExtTree(ConfigJsonTree):
    fetched_rows_signal = Signal(list)

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent=parent,
            conf_namespace=kwargs.get('conf_namespace', None),
            # propagate=False,
            schema=kwargs.get('schema', []),
            layout_type=kwargs.get('layout_type', 'vertical'),
            config_widget=kwargs.get('config_widget', None),
            # add_item_options=kwargs.get('add_item_options', None),
            # del_item_options=kwargs.get('del_item_options', None),
            tree_width=kwargs.get('tree_width', 400)
        )
        self.fetched_rows_signal.connect(self.load_rows, Qt.QueuedConnection)

        # self.main = find_main_widget(self)
        # if not self.main:
        #     # raise ValueError('Main widget not found')
        #     pass
        #     find_main_widget(self)

    @override
    def load(self, rows=None):
        rows = self.config.get(f'{self.conf_namespace}.data', [])
        self.insert_rows(rows)
        main = find_main_widget(self)
        load_runnable = self.LoadRunnable(self)
        main.threadpool.start(load_runnable)

    @Slot(list)
    def load_rows(self, rows):
        # self.config[f'{self.conf_namespace}.data'] = rows
        self.insert_rows(rows)
        # single shot
        safe_single_shot(10, self.update_config)

    def insert_rows(self, rows):
        with block_signals(self.tree):
            self.tree.clear()
            for row_fields in rows:
                item = QTreeWidgetItem(self.tree, row_fields)

    @override
    def get_config(self):
        config = {}
        data = []
        for i in range(self.tree.topLevelItemCount()):
            row_item = self.tree.topLevelItem(i)
            row_data = [row_item.text(j) for j in range(row_item.columnCount())]
            data.append(row_data)
        config[f'{self.conf_namespace}.data'] = data
        return config

    @override
    def update_config(self):
        """Bubble update config dict to the root config widget"""
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

        if hasattr(self, 'save_config'):
            self.save_config()

    # def save_config(self):
    #     """Remove the super method to prevent saving the config"""
    #     pass

    class LoadRunnable(QRunnable):
        def __init__(self, parent):
            super().__init__()
            main = find_main_widget(parent)
            self.page_chat = main.page_chat

        def run(self):
            pass

    def on_item_selected(self):
        pass