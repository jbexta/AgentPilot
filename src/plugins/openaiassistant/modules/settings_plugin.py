from datetime import datetime

import openai
from PySide6.QtCore import Signal, QRunnable, Slot
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QHBoxLayout, QTreeWidgetItem, QFileDialog

from src.gui.config import ConfigDBTree, ConfigTabs
from src.gui.widgets import find_main_widget
from src.utils.helpers import block_signals, block_pin_mode


class Page_Settings_OAI(ConfigTabs):
    def __init__(self, parent):
        super().__init__(parent=parent)

        self.pages = {
            'Assistants': self.Page_Settings_OAI_Assistants(parent=self),
            'Files': self.Page_Settings_OAI_Files(parent=self),
        }

    class Page_Settings_OAI_Assistants(ConfigDBTree):
        fetched_rows_signal = Signal(list)

        def __init__(self, parent):
            super().__init__(
                parent=parent,
                propagate=False,
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
                        'type': int,
                        'visible': False,
                    },
                    {
                        'text': '',
                        'type': str,
                        'width': 100,
                    },
                ],
                layout_type=QHBoxLayout,
                add_item_prompt=('Create assistant', 'Enter a name for the assistant:'),
                del_item_prompt=('Delete assistant', 'Are you sure you want to delete this assistant?'),
                tree_width=400
            )
            self.main = find_main_widget(self)
            self.fetched_rows_signal.connect(self.load_rows, Qt.QueuedConnection)

        # @Slot(list)
        def load(self, rows=None):
            load_runnable = self.LoadRunnable(self)
            self.main.page_chat.threadpool.start(load_runnable)

        @Slot(list)
        def load_rows(self, rows):
            with block_signals(self.tree):
                self.tree.clear()
                for row_fields in rows:
                    item = QTreeWidgetItem(self.tree, row_fields)

        class LoadRunnable(QRunnable):
            def __init__(self, parent):
                super().__init__()
                self.parent = parent
                self.page_chat = parent.main.page_chat
                # self.page_chat = parent
                # self.workflow = self.page_chat.workflow

            def run(self):
                try:
                    assistants = openai.beta.assistants.list(limit=100)

                    rows = []
                    for assistant in assistants.data:
                        file_count = len(assistant.file_ids)
                        file_count_str = f'{file_count} file' + ('s' if file_count != 1 else '') \
                                         if file_count > 0 else ''
                        fields = [
                            datetime.utcfromtimestamp(int(assistant.created_at)).strftime('%Y-%m-%d %H:%M:%S'),
                            assistant.name,
                            assistant.id,
                            file_count_str,
                        ]
                        rows.append(fields)
                    self.parent.fetched_rows_signal.emit(rows)
                except Exception as e:
                    self.page_chat.main.error_occurred.emit(str(e))

        def on_item_selected(self):
            pass

        def add_item(self):
            pass

        def delete_item(self):
            pass

    class Page_Settings_OAI_Files(ConfigDBTree):
        fetched_rows_signal = Signal(list)

        def __init__(self, parent):
            super().__init__(
                parent=parent,
                propagate=False,
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
                        'type': int,
                        'visible': False,
                    },
                    {
                        'text': 'purpose',
                        'type': str,
                        'width': 100,
                    },
                ],
                layout_type=QHBoxLayout,
                add_item_prompt=('Create assistant', 'Enter a name for the assistant:'),
                del_item_prompt=('Delete assistant', 'Are you sure you want to delete this assistant?'),
                tree_width=400
            )
            self.main = find_main_widget(self)
            self.fetched_rows_signal.connect(self.load_rows, Qt.QueuedConnection)

        # @Slot(list)
        def load(self, rows=None):
            load_runnable = self.LoadRunnable(self)
            self.main.page_chat.threadpool.start(load_runnable)

        @Slot(list)
        def load_rows(self, rows):
            with block_signals(self.tree):
                self.tree.clear()
                for row_fields in rows:
                    item = QTreeWidgetItem(self.tree, row_fields)

        class LoadRunnable(QRunnable):
            def __init__(self, parent):
                super().__init__()
                self.parent = parent
                self.page_chat = parent.main.page_chat
                # self.page_chat = parent
                # self.workflow = self.page_chat.workflow

            def run(self):
                try:
                    client = openai.OpenAI()
                    files = client.files.list()

                    rows = []
                    for assistant in files.data:
                        file_count = len(assistant.file_ids)
                        file_count_str = f'{file_count} file' + ('s' if file_count != 1 else '') \
                                         if file_count > 0 else ''
                        fields = [
                            datetime.utcfromtimestamp(int(assistant.created_at)).strftime('%Y-%m-%d %H:%M:%S'),
                            assistant.name,
                            assistant.id,
                            file_count_str,
                        ]
                        rows.append(fields)
                    self.parent.fetched_rows_signal.emit(rows)
                except Exception as e:
                    self.page_chat.main.error_occurred.emit(str(e))

        def add_item(self, column_vals=None, icon=None):
            with block_pin_mode():
                file_dialog = QFileDialog()
                file_dialog.setFileMode(QFileDialog.ExistingFile)
                file_dialog.setFileMode(QFileDialog.ExistingFiles)
                # fd.setStyleSheet("QFileDialog { color: black; }")
                path, _ = file_dialog.getOpenFileName(self, "Choose Files", "", options=file_dialog.Options())

            if path:
                client = openai.OpenAI()
                client.files.create(file=open(path, "rb"))

        def delete_item(self):
            item = self.tree.currentItem()
            if not item:
                return None
            tag = item.data(0, Qt.UserRole)

            # if tag == 'folder':
            #     retval = display_messagebox(
            #         icon=QMessageBox.Warning,
            #         title="Delete folder",
            #         text="Are you sure you want to delete this folder? It's contents will be extracted.",
            #         buttons=QMessageBox.Yes | QMessageBox.No,
            #     )
            #     if retval != QMessageBox.Yes:
            #         return False
            #
            #     folder_id = int(item.text(1))
            #     folder_parent = item.parent() if item else None
            #     folder_parent_id = folder_parent.text(1) if folder_parent else None
            #
            #     # Unpack all items from folder to parent folder (or root)
            #     sql.execute(f"""
            #         UPDATE `{self.db_table}`
            #         SET folder_id = {'NULL' if not folder_parent_id else folder_parent_id}
            #         WHERE folder_id = ?
            #     """, (folder_id,))
            #     # Unpack all folders from folder to parent folder (or root)
            #     sql.execute(f"""
            #         UPDATE `folders`
            #         SET parent_id = {'NULL' if not folder_parent_id else folder_parent_id}
            #         WHERE parent_id = ?
            #     """, (folder_id,))
            #
            #     sql.execute(f"""
            #         DELETE FROM folders
            #         WHERE id = ?
            #     """, (folder_id,))
            #
            #     self.load()
            #     return True
            # else:
            #     id = self.get_selected_item_id()
            #     if not id:
            #         return False
            #
            #     if self.db_table == 'agents':
            #         context_count = sql.get_scalar("""
            #             SELECT
            #                 COUNT(*)
            #             FROM contexts_members
            #             WHERE agent_id = ?""", (id,))
            #
            #         if context_count > 0:
            #             name = self.get_column_value(0)
            #             display_messagebox(
            #                 icon=QMessageBox.Warning,
            #                 text=f"Cannot delete '{name}' because it exists in {context_count} contexts.",
            #                 title="Warning",
            #                 buttons=QMessageBox.Ok
            #             )
            #             return False
            #
            #     dlg_title, dlg_prompt = self.del_item_prompt
            #
            #     retval = display_messagebox(
            #         icon=QMessageBox.Warning,
            #         title=dlg_title,
            #         text=dlg_prompt,
            #         buttons=QMessageBox.Yes | QMessageBox.No,
            #     )
            #     if retval != QMessageBox.Yes:
            #         return False
            #
            #     try:
            #         if self.db_table == 'contexts':
            #             context_id = id
            #             context_member_ids = sql.get_results("SELECT id FROM contexts_members WHERE context_id = ?",
            #                                                  (context_id,),
            #                                                  return_type='list')
            #             sql.execute(
            #                 "DELETE FROM contexts_members_inputs WHERE member_id IN ({}) OR input_member_id IN ({})".format(
            #                     ','.join([str(i) for i in context_member_ids]),
            #                     ','.join([str(i) for i in context_member_ids])
            #                 ))
            #             sql.execute("DELETE FROM contexts_messages WHERE context_id = ?;",
            #                         (context_id,))  # todo update delete to cascade branches & transaction
            #             sql.execute('DELETE FROM contexts_members WHERE context_id = ?', (context_id,))
            #             sql.execute("DELETE FROM contexts WHERE id = ?;", (context_id,))
            #
            #         else:
            #             sql.execute(f"DELETE FROM `{self.db_table}` WHERE `id` = ?", (id,))
            #
            #         self.load()
            #         return True
            #
            #     except Exception:
            #         display_messagebox(
            #             icon=QMessageBox.Warning,
            #             title='Error',
            #             text='Item could not be deleted',
            #         )
            #         return False
