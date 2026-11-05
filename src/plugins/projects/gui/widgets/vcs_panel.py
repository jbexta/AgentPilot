import qasync
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QLabel, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTabWidget, QWidget,
)

from gui.gui_utils.custom_menu import CustomMenu
from gui.gui_utils.icon_button import IconButton
from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from gui.widgets.config_joined import ConfigJoined
from plugins.projects.gui.gui_utils.git_identity import GitIdentityDialog
from plugins.projects.gui.highlighters.diff import DiffHighlighter
from plugins.projects.utils import vcs
from utils.helpers import display_message, display_message_box

STATUS_LETTERS = {
    'modified': 'M', 'changed': 'M', 'added': 'A', 'untracked': 'U',
    'deleted': 'D', 'conflict': '!',
}


class VcsPanel(QWidget):
    """The changes and history of a FileTree's repo, shown as a preview tab."""

    def __init__(self, tree_vcs):
        super().__init__()
        self.tree_vcs = tree_vcs
        self.changes = self.Changes(self)
        self.history = self.History(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.changes, 'Changes')
        self.tabs.addTab(self.history, 'History')
        self.layout = CVBoxLayout(self)
        self.layout.addWidget(self.tabs)

    def refresh(self):
        self.changes.refresh()
        self.history.refresh()

    class DiffView(QPlainTextEdit):
        def __init__(self):
            super().__init__()
            self.setObjectName('vcsDiff')
            self.setReadOnly(True)
            self.setLineWrapMode(QPlainTextEdit.NoWrap)
            self.highlighter = DiffHighlighter(self.document())

        def show_text(self, text):
            if text != self.toPlainText():
                self.setPlainText(text)

    class Changes(QWidget):
        def __init__(self, panel):
            super().__init__()
            self.tree_vcs = panel.tree_vcs

            self.message_edit = QPlainTextEdit()
            self.message_edit.setPlaceholderText('Commit message')
            self.message_edit.setFixedHeight(64)
            self.commit_btn = QPushButton('Commit')
            self.commit_btn.setProperty('class', 'dialog-button')
            self.commit_btn.setProperty('primary', True)
            self.commit_btn.clicked.connect(self.commit)

            self.staged_lbl = QLabel()
            self.staged_list = self.change_list()
            self.unstaged_lbl = QLabel()
            self.unstaged_list = self.change_list()
            self.diff_view = panel.DiffView()

            lists = ConfigJoined(parent=self, layout_type='vertical', resizable=True, widgets=[
                self.section(
                    self.staged_lbl, self.staged_list, ':/resources/icon-minus.png', 'Unstage All',
                    lambda: self.tree_vcs.run_vcs(vcs.unstage, self.paths(self.staged_list, all_items=True))),
                self.section(
                    self.unstaged_lbl, self.unstaged_list, ':/resources/icon-new.png', 'Stage All',
                    lambda: self.tree_vcs.run_vcs(vcs.stage_all)),
            ])
            lists.build_schema()
            lists.splitter.setSizes([100, 200])

            left = QWidget()
            left_layout = CVBoxLayout(left)
            left_layout.setSpacing(6)
            left_layout.addWidget(self.message_edit)
            left_layout.addWidget(self.commit_btn)
            left_layout.addWidget(lists, 1)

            splitter = QSplitter(Qt.Horizontal)
            splitter.setChildrenCollapsible(False)
            splitter.addWidget(left)
            splitter.addWidget(self.diff_view)
            splitter.setSizes([300, 500])
            self.layout = CVBoxLayout(self)
            self.layout.addWidget(splitter)

        def section(self, label, change_list, icon_path, tooltip, target):
            options_menu = CustomMenu(parent=self, schema=[{
                'text': 'Options',
                'icon_path': ':/resources/icon-dots.png',
                'submenu': [{
                    'text': 'Select All',
                    'target': change_list.selectAll,
                }],
            }])
            options_menu.create_toolbar()

            row = CHBoxLayout()
            row.addWidget(label)
            row.addStretch(1)
            row.addWidget(IconButton(
                parent=self, icon_path=icon_path, tooltip=tooltip,
                target=target, size=20))
            row.addWidget(options_menu)

            section = QWidget()
            section_layout = CVBoxLayout(section)
            section_layout.setSpacing(6)
            section_layout.addLayout(row)
            section_layout.addWidget(change_list)
            return section

        def change_list(self):
            change_list = QListWidget()
            change_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
            change_list.setContextMenuPolicy(Qt.CustomContextMenu)
            change_list.customContextMenuRequested.connect(
                lambda pos: self.show_context_menu(change_list, pos))
            change_list.itemSelectionChanged.connect(
                lambda: self.on_selection_changed(change_list))
            change_list.itemDoubleClicked.connect(
                lambda: self.toggle_stage(change_list))
            return change_list

        def paths(self, change_list, all_items=False):
            items = (
                [change_list.item(i) for i in range(change_list.count())]
                if all_items else change_list.selectedItems()
            )
            return [self.tree_vcs.repo_root / item.data(Qt.UserRole)[0] for item in items]

        def refresh(self):
            entries = self.tree_vcs.repo_status
            staged = [(rel, code) for rel, code in entries.items() if code[0] not in ' ?']
            unstaged = [(rel, code) for rel, code in entries.items() if code[1] != ' ']
            self.fill(self.staged_list, staged)
            self.fill(self.unstaged_list, unstaged)
            self.staged_lbl.setText(f'Staged Changes ({len(staged)})')
            self.unstaged_lbl.setText(f'Changes ({len(unstaged)})')
            self.commit_btn.setText('Commit' if staged else 'Commit All')
            self.commit_btn.setEnabled(bool(entries))
            self.show_diff()

        def fill(self, change_list, changes):
            selected = {item.data(Qt.UserRole)[0] for item in change_list.selectedItems()}
            change_list.blockSignals(True)
            change_list.clear()
            entries = self.tree_vcs.repo_status
            for rel, code in sorted(changes):
                is_dir = rel.endswith('/')
                state = vcs.state(entries, rel.rstrip('/'), is_dir)
                item = QListWidgetItem(f'{STATUS_LETTERS[state]}   {rel}')
                item.setData(Qt.UserRole, (rel, code))
                item.setForeground(self.tree_vcs.item_color(self.tree_vcs.repo_root / rel, is_dir))
                change_list.addItem(item)
                item.setSelected(rel in selected)
            change_list.blockSignals(False)

        def select(self, rel):
            for change_list in (self.unstaged_list, self.staged_list):
                for i in range(change_list.count()):
                    item = change_list.item(i)
                    if item.data(Qt.UserRole)[0] in (rel, rel + '/'):
                        change_list.setCurrentItem(item)
                        return

        def on_selection_changed(self, change_list):
            other = self.unstaged_list if change_list is self.staged_list else self.staged_list
            if change_list.selectedItems():
                other.blockSignals(True)
                other.clearSelection()
                other.blockSignals(False)
            self.show_diff()

        @qasync.asyncSlot()
        async def show_diff(self):
            for change_list, staged in ((self.staged_list, True), (self.unstaged_list, False)):
                items = change_list.selectedItems()
                if items:
                    break
            else:
                self.diff_view.clear()
                return
            target = items[0].data(Qt.UserRole)
            try:
                text = await vcs.diff(self.tree_vcs.repo_root, *target, staged)
            except RuntimeError as e:
                text = str(e)
            if not shiboken6.isValid(self):
                return
            if items[0] in change_list.selectedItems():
                self.diff_view.show_text(text)

        def toggle_stage(self, change_list):
            func = vcs.unstage if change_list is self.staged_list else vcs.stage
            self.tree_vcs.run_vcs(func, self.paths(change_list))

        def show_context_menu(self, change_list, pos):
            items = change_list.selectedItems()
            if not items:
                return
            paths = self.paths(change_list)
            codes = [item.data(Qt.UserRole)[1] for item in items]
            menu = QMenu(self)
            if change_list is self.staged_list:
                menu.addAction('Unstage').triggered.connect(
                    lambda: self.tree_vcs.run_vcs(vcs.unstage, paths))
            else:
                menu.addAction('Stage').triggered.connect(
                    lambda: self.tree_vcs.run_vcs(vcs.stage, paths))
                if any(code != '??' and 'A' not in code and 'R' not in code for code in codes):
                    menu.addAction('Revert Changes').triggered.connect(
                        lambda: self.tree_vcs.revert_paths(paths))
            files = [path for path in paths if path.is_file()]
            if len(files) == 1:
                menu.addSeparator()
                menu.addAction('Open File').triggered.connect(
                    lambda: self.tree_vcs.tree.set_current_file(files[0]))
            menu.exec(change_list.viewport().mapToGlobal(pos))

        def commit(self):
            message = self.message_edit.toPlainText().strip()
            if not message:
                self.message_edit.setFocus()
                return
            self.commit_btn.setEnabled(False)
            self.do_commit(message)

        @qasync.asyncSlot()
        async def do_commit(self, message):
            root = self.tree_vcs.repo_root
            try:
                if not await vcs.identity(root):
                    dialog = GitIdentityDialog(self)
                    dialog.accepted.connect(self.commit)
                    dialog.open()
                    return
                if not any(code[0] not in ' ?' for code in self.tree_vcs.repo_status.values()):
                    await vcs.stage_all(root)
                await vcs.commit(root, message)
            except RuntimeError as e:
                display_message(str(e), 'Commit failed')
            else:
                if shiboken6.isValid(self):
                    self.message_edit.clear()
            finally:
                if shiboken6.isValid(self):
                    self.commit_btn.setEnabled(True)
                self.tree_vcs.refresh()

    class History(QWidget):
        def __init__(self, panel):
            super().__init__()
            self.tree_vcs = panel.tree_vcs
            self.rel = None
            self.shas = []

            self.filter_lbl = QLabel()
            self.filter_lbl.setObjectName('dialogDetail')
            self.filter_row = QWidget()
            filter_layout = CHBoxLayout(self.filter_row)
            filter_layout.addWidget(self.filter_lbl)
            filter_layout.addStretch(1)
            filter_layout.addWidget(IconButton(
                parent=self, icon_path=':/resources/close.png',
                tooltip='Show all history', size=20,
                target=lambda: self.set_filter(None)))
            self.filter_row.hide()

            self.commit_list = QListWidget()
            self.commit_list.itemSelectionChanged.connect(self.show_commit)
            self.commit_list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.commit_list.customContextMenuRequested.connect(self.show_context_menu)
            self.diff_view = panel.DiffView()

            left = QWidget()
            left_layout = CVBoxLayout(left)
            left_layout.addWidget(self.filter_row)
            left_layout.addWidget(self.commit_list)
            splitter = QSplitter(Qt.Horizontal)
            splitter.setChildrenCollapsible(False)
            splitter.addWidget(left)
            splitter.addWidget(self.diff_view)
            splitter.setSizes([300, 500])
            self.layout = CVBoxLayout(self)
            self.layout.addWidget(splitter)

        def set_filter(self, rel):
            self.rel = rel
            self.filter_lbl.setText(f'History of {rel}')
            self.filter_row.setVisible(rel is not None)
            self.shas = []
            self.refresh()

        @qasync.asyncSlot()
        async def refresh(self):
            root = self.tree_vcs.repo_root
            commits = await vcs.log(root, self.rel) if root else []
            if not shiboken6.isValid(self):
                return
            shas = [c['sha'] for c in commits]
            if shas == self.shas:
                return
            self.shas = shas
            self.commit_list.clear()
            for c in commits:
                item = QListWidgetItem(
                    f"{c['subject']}\n{c['author']} · {c['date']} · {c['short']}")
                item.setData(Qt.UserRole, c['sha'])
                self.commit_list.addItem(item)
            if commits:
                self.commit_list.setCurrentRow(0)
            else:
                self.diff_view.clear()

        @qasync.asyncSlot()
        async def show_commit(self):
            item = self.commit_list.currentItem()
            if not item:
                return
            sha = item.data(Qt.UserRole)
            text = await vcs.show(self.tree_vcs.repo_root, sha)
            if shiboken6.isValid(self) and self.commit_list.currentItem() is item:
                self.diff_view.show_text(text)

        def show_context_menu(self, pos):
            item = self.commit_list.itemAt(pos)
            if not item:
                return
            sha = item.data(Qt.UserRole)
            subject = item.text().split('\n')[0]
            menu = QMenu(self)
            menu.addAction('Revert Commit').triggered.connect(lambda: self.confirm_run(
                vcs.revert_commit, sha, 'Revert Commit',
                f'Add a new commit that undoes "{subject}"?'))
            if self.rel is None and self.commit_list.row(item) > 0:
                menu.addAction('Roll Back to Here').triggered.connect(lambda: self.confirm_run(
                    vcs.reset_to, sha, 'Roll Back to Here',
                    f'Remove the commits after "{subject}" from the branch? '
                    'Their changes are kept as staged changes.'))
            menu.exec(self.commit_list.viewport().mapToGlobal(pos))

        def confirm_run(self, func, sha, title, text):
            reply = display_message_box(
                icon=QMessageBox.Question, title=title, text=text,
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.run(func, sha)

        @qasync.asyncSlot()
        async def run(self, func, sha):
            try:
                await func(self.tree_vcs.repo_root, sha)
            except RuntimeError as e:
                display_message(str(e), 'Error')
            self.tree_vcs.refresh()
            if shiboken6.isValid(self):
                self.refresh()
