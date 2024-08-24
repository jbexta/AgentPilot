from datetime import datetime

import openai
from PySide6.QtCore import Signal, QRunnable, Slot
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QHBoxLayout, QTreeWidgetItem, QFileDialog, QApplication, QInputDialog, QMessageBox, \
    QVBoxLayout
from openai import OpenAI

from src.gui.config import ConfigDBTree, ConfigTabs, ConfigExtTree
from src.gui.widgets import find_main_widget, find_attribute
from src.utils.helpers import block_signals, block_pin_mode, display_messagebox


class Page_Settings_OAI(ConfigTabs):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.conf_namespace = 'plugins.openai'
        self.client = None

        self.pages = {
            'Assistants': self.Page_Settings_OAI_Assistants(parent=self),
            'Files': self.Page_Settings_OAI_Files(parent=self),
            'Vector Stores': self.Page_Settings_OAI_VecStores(parent=self),
        }

    def load(self):
        from src.system.base import manager
        model_params = manager.providers.get_model_parameters('gpt-3.5-turbo')  # hack to get OAI api key
        api_key = model_params.get('api_key', None)
        api_base = model_params.get('api_base', None)
        self.client = OpenAI(api_key=api_key, base_url=api_base)
        super().load()

    class Page_Settings_OAI_Assistants(ConfigExtTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                conf_namespace='plugins.openai.assistants',
                schema=[
                    {
                        'text': 'Created on',
                        'type': str,
                        'width': 150,
                    },
                    {
                        'text': 'Name',
                        'type': str,
                        'width': 150,
                    },
                    {
                        'text': 'id',
                        'type': str,
                        'visible': False,
                    },
                ],
                add_item_prompt=('Create assistant', 'Enter a name for the assistant:'),
                del_item_prompt=('Delete assistant', 'Are you sure you want to delete this assistant?'),
                tree_width=400
            )

        class LoadRunnable(QRunnable):
            def __init__(self, parent):
                super().__init__()
                self.parent = parent
                self.page_chat = parent.main.page_chat
                self.client = find_attribute(self, 'client')

            def run(self):
                # from src.system.base import manager
                # QApplication.setOverrideCursor(Qt.BusyCursor)
                try:
                    assistants = self.client.beta.assistants.list(limit=100)

                    rows = []
                    for assistant in assistants.data:
                        fields = [
                            datetime.utcfromtimestamp(int(assistant.created_at)).strftime('%Y-%m-%d %H:%M:%S'),
                            assistant.name,
                            assistant.id,
                        ]
                        rows.append(fields)
                    self.parent.fetched_rows_signal.emit(rows)
                except Exception as e:
                    self.page_chat.main.error_occurred.emit(str(e))
                # finally:
                #     QApplication.setOverrideCursor(Qt.ArrowCursor)

    class Page_Settings_OAI_VecStores(ConfigExtTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                conf_namespace='plugins.openai.vecstores',
                schema=[
                    {
                        'text': 'Created on',
                        'type': str,
                        'width': 150,
                    },
                    {
                        'text': 'id',
                        'type': str,
                        'visible': False,
                    },
                    {
                        'text': 'Name',
                        'type': str,
                        'width': 150,
                    },
                    {
                        'text': 'Size',
                        'type': str,
                        'width': 100,
                    },
                    {
                        'text': 'File count',
                        'type': str,
                        'width': 100,
                    }
                ],
                add_item_prompt=('Create vector store', 'Enter a name for the vector store:'),
                del_item_prompt=('Delete vector store', 'Are you sure you want to delete this vector store?'),
                tree_width=500,
                tree_height=400,
                config_widget=self.Page_Settings_OAI_VecStore_Files(parent=self),
                layout_type=QVBoxLayout
            )

        class LoadRunnable(QRunnable):
            def __init__(self, parent):
                super().__init__()
                self.parent = parent
                self.page_chat = parent.main.page_chat
                self.client = find_attribute(self, 'client')

            def run(self):
                # QApplication.setOverrideCursor(Qt.BusyCursor)
                try:
                    all_vec_stores = self.client.beta.vector_stores.list(limit=100)

                    rows = []
                    for vec_store in all_vec_stores.data:
                        files_completed = vec_store.file_counts.completed
                        files_in_progress = vec_store.file_counts.in_progress
                        fields = [
                            datetime.utcfromtimestamp(int(vec_store.created_at)).strftime('%Y-%m-%d %H:%M:%S'),
                            vec_store.id,
                            vec_store.name,
                            vec_store.usage_bytes,
                            f'{files_completed} ({files_in_progress})',
                        ]
                        rows.append(fields)
                    self.parent.fetched_rows_signal.emit(rows)
                except Exception as e:
                    self.page_chat.main.error_occurred.emit(str(e))
                # finally:
                #     QApplication.setOverrideCursor(Qt.ArrowCursor)

        def get_selected_item_id(self):
            item = self.tree.currentItem()
            if not item:
                return None
            return item.text(1)

        def add_item(self):
            with block_pin_mode():
                text, ok = QInputDialog.getText(self, "Enter name", "Enter a name for the vector store:")

                if not ok:
                    return False

                openai.beta.vector_stores.create(name=text)
            self.load()

        def delete_item(self):
            id = self.get_selected_item_id()
            if not id:
                return False

            retval = display_messagebox(
                icon=QMessageBox.Warning,
                title="Delete vector store",
                text="Are you sure you want to delete this vector store? It's contents will be lost.",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return False

            openai.beta.vector_stores.delete(vector_store_id=id)
            self.load()

        class Page_Settings_OAI_VecStore_Files(ConfigExtTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    conf_namespace='plugins.openai.vecstores.files',
                    schema=[
                        {
                            'text': 'Created on',
                            'type': str,
                            'width': 150,
                        },
                        {
                            'text': 'id',
                            'type': str,
                            'visible': False,
                        },
                        {
                            'text': 'Name',
                            'type': str,
                            'width': 150,
                        },
                        {
                            'text': 'Size',
                            'type': str,
                            'width': 100,
                        },
                        {
                            'text': 'File count',
                            'type': str,
                            'width': 100,
                        }
                    ],
                    add_item_prompt=('Create vector store', 'Enter a name for the vector store:'),
                    del_item_prompt=('Delete vector store', 'Are you sure you want to delete this vector store?'),
                    tree_width=500
                )

            class LoadRunnable(QRunnable):
                def __init__(self, parent):
                    super().__init__()
                    self.parent = parent
                    self.page_chat = parent.main.page_chat
                    self.client = find_attribute(self, 'client')

                def run(self):
                    # QApplication.setOverrideCursor(Qt.BusyCursor)
                    try:
                        all_vec_stores = openai.beta.vector_stores.list(limit=100)

                        rows = []
                        for vec_store in all_vec_stores.data:
                            files_completed = vec_store.file_counts.completed
                            files_in_progress = vec_store.file_counts.in_progress
                            fields = [
                                datetime.utcfromtimestamp(int(vec_store.created_at)).strftime('%Y-%m-%d %H:%M:%S'),
                                vec_store.id,
                                vec_store.name,
                                vec_store.usage_bytes,
                                f'{files_completed} ({files_in_progress})',
                            ]
                            rows.append(fields)
                        self.parent.fetched_rows_signal.emit(rows)
                    except Exception as e:
                        self.page_chat.main.error_occurred.emit(str(e))
                    # finally:
                    #     QApplication.setOverrideCursor(Qt.ArrowCursor)

            def get_selected_item_id(self):
                item = self.tree.currentItem()
                if not item:
                    return None
                return item.text(1)

            def add_item(self):
                with block_pin_mode():
                    text, ok = QInputDialog.getText(self, "Enter name", "Enter a name for the vector store:")

                    if not ok:
                        return False

                    openai.beta.vector_stores.create(name=text)
                self.load()

            def delete_item(self):
                id = self.get_selected_item_id()
                if not id:
                    return False

                retval = display_messagebox(
                    icon=QMessageBox.Warning,
                    title="Delete vector store",
                    text="Are you sure you want to delete this vector store? It's contents will be lost.",
                    buttons=QMessageBox.Yes | QMessageBox.No,
                )
                if retval != QMessageBox.Yes:
                    return False

                openai.beta.vector_stores.delete(vector_store_id=id)
                self.load()

        # class Page_Settings_OAI_VecStores_Files(ConfigAsyncTree):
        #     def __init__(self, parent):
        #         super().__init__(

    class Page_Settings_OAI_Files(ConfigExtTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                conf_namespace='plugins.openai.files',
                schema=[
                    {
                        'text': 'Created on',
                        'type': str,
                        'width': 150,
                    },
                    {
                        'text': 'id',
                        'type': str,
                        'visible': False,
                    },
                    {
                        'text': 'Filename',
                        'type': str,
                        'width': 150,
                    },
                    {
                        'text': 'Size',
                        'type': str,
                        'width': 100,
                    },
                    {
                        'text': 'Purpose',
                        'type': str,
                        'width': 100,
                    }
                ],
                add_item_prompt=None,  # ('Create vector store', 'Enter a name for the vector store:'),
                del_item_prompt=('Delete file', 'Are you sure you want to delete this file?'),
                tree_width=500,
                # tree_height=400,
                # config_widget=self.Page_Settings_OAI_VecStore_Files(parent=self),
                # layout_type=QVBoxLayout
            )

        class LoadRunnable(QRunnable):
            def __init__(self, parent):
                super().__init__()
                self.parent = parent
                self.page_chat = parent.main.page_chat
                self.client = find_attribute(self, 'client')

            def run(self):
                # QApplication.setOverrideCursor(Qt.BusyCursor)
                try:
                    all_files = self.client.files.list()

                    rows = []
                    for file in all_files.data:
                        fields = [
                            datetime.utcfromtimestamp(int(file.created_at)).strftime('%Y-%m-%d %H:%M:%S'),
                            file.id,
                            file.filename,
                            file.bytes,
                            file.purpose,
                        ]
                        rows.append(fields)
                    self.parent.fetched_rows_signal.emit(rows)
                except Exception as e:
                    self.page_chat.main.error_occurred.emit(str(e))
                # finally:
                #     QApplication.setOverrideCursor(Qt.ArrowCursor)

        def get_selected_item_id(self):
            item = self.tree.currentItem()
            if not item:
                return None
            return item.text(1)

        # def add_item(self):
        #     with block_pin_mode():
        #         text, ok = QInputDialog.getText(self, "Enter name", "Enter a name for the vector store:")
        #
        #         if not ok:
        #             return False
        #
        #         openai.beta.vector_stores.create(name=text)
        #     self.load()

        def delete_item(self):
            id = self.get_selected_item_id()
            if not id:
                return False

            retval = display_messagebox(
                icon=QMessageBox.Warning,
                title="Delete file",
                text="Are you sure you want to delete this file?",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return False

            openai.beta.vector_stores.delete(vector_store_id=id)
            self.load()
