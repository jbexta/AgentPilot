import qasync
import shiboken6
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton

from gui.gui_utils.custom_menu import CustomMenu
from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from plugins.files.widgets.file_tree import FileTreeExtension
from plugins.projects.gui.gui_utils.add_remote import AddRemoteDialog
from plugins.projects.gui.gui_utils.github_publish import GitHubPublishDialog
from plugins.projects.gui.gui_utils.github_sign_in import GitHubSignInDialog
from plugins.projects.utils import github, vcs
from plugins.projects.gui.widgets.vcs_panel import VcsPanel
from utils.helpers import display_message, display_message_box, get_text, set_module_type

VCS_COLORS = {
    'modified': '#e2c08d',
    'changed': '#e2c08d',
    'added': '#73c991',
    'untracked': '#73c991',
    'deleted': '#c74e39',
    'conflict': '#e4676b',
}


@set_module_type('Widgets')
class FileTreeVcs(FileTreeExtension):
    """Git status colors, context actions and the VCS menu of a FileTree."""
    _trust_prompted = set()

    def __init__(self, tree):
        super().__init__(tree)
        self.repo_root = None
        self.repo_status = {}
        self.repo_branch = ''
        self.repo_branches = []
        self.repo_remotes = []
        self._vcs_error = None
        self.untrusted_root = None
        self.vcs_panel = None
        self._vcs_timer = QTimer(self)
        self._vcs_timer.timeout.connect(self.refresh)
        self._vcs_timer.start(3000)

        self.vcs_menu = CustomMenu(parent=self, schema=[{
            'text': 'VCS',
            'icon_path': ':/resources/icon-history.png',
            'submenu': self.vcs_menu_schema,
        }])
        self.vcs_menu.create_toolbar()
        self.layout = CHBoxLayout(self)
        self.layout.addWidget(self.vcs_menu)
        self.hide()

    def vcs_menu_schema(self):
        return [
            {'text': 'Changes...', 'target': lambda: self.open_vcs_panel(0)},
            {'text': 'History...', 'target': lambda: self.open_vcs_panel(1)},
            {'type': 'separator'},
            {
                'text': f"Branch: {self.repo_branch or '(detached)'}",
                'submenu': [
                    *({
                        'text': name,
                        'checkable': True,
                        'checked_state': name == self.repo_branch,
                        'target': lambda *_, n=name: self.run_vcs(vcs.checkout, n),
                    } for name in self.repo_branches),
                    {'type': 'separator'},
                    {'text': 'New Branch...', 'target': self.new_branch},
                ],
            },
            {'type': 'separator'},
            *([
                {'text': 'Fetch', 'target': lambda: self.run_vcs(vcs.fetch)},
                {'text': 'Pull', 'target': lambda: self.run_vcs(vcs.pull)},
                {'text': 'Push...', 'target': self.confirm_push},
            ] if self.repo_remotes else [
                {'text': 'Publish to GitHub...', 'target': self.publish_to_github},
                {'text': 'Add Remote...', 'target': self.add_remote},
            ]),
            {'type': 'separator'},
            {'text': 'Refresh', 'target': self.refresh},
        ]

    def options_menu_schema(self):
        return [{
            'text': 'Initialize VCS',
            'visibility_predicate': lambda: (
                self.repo_root is None and self.untrusted_root is None),
            'target': lambda: self.run_vcs(vcs.init),
        }, {
            'text': 'Trust Folder...',
            'visibility_predicate': lambda: self.untrusted_root is not None,
            'target': self.show_trust_dialog,
        }]

    @qasync.asyncSlot()
    async def refresh(self):
        tree = self.tree
        if not shiboken6.isValid(self) or not tree.isVisible():
            return
        try:
            root = await vcs.repo_root(tree.current_path)
            entries = await vcs.status(root) if root else {}
            branch, branches = await vcs.branches(root) if root else ('', [])
            remotes = await vcs.remotes(root) if root else []
            self._vcs_error = None
        except (RuntimeError, OSError) as e:
            root, entries, branch, branches, remotes = None, {}, '', [], []
            untrusted = await vcs.untrusted_root(tree.current_path)
            if not shiboken6.isValid(self):
                return
            self.untrusted_root = untrusted
            if untrusted and untrusted not in FileTreeVcs._trust_prompted:
                FileTreeVcs._trust_prompted.add(untrusted)
                self.show_trust_dialog()
            elif not untrusted and str(e) != self._vcs_error:
                self._vcs_error = str(e)
                display_message(str(e), 'VCS Error')
        else:
            self.untrusted_root = None
        if not shiboken6.isValid(self):
            return
        self.repo_remotes = remotes
        state = (root, entries, branch, branches)
        if state == (self.repo_root, self.repo_status, self.repo_branch, self.repo_branches):
            return
        self.repo_root, self.repo_status, self.repo_branch, self.repo_branches = state
        self.setVisible(root is not None)
        tree.nav_panel.dir_tree.viewport().update()
        tree.file_view.get_current_view().viewport().update()
        if self.vcs_panel and shiboken6.isValid(self.vcs_panel):
            self.vcs_panel.refresh()

    def open_vcs_panel(self, tab=0, path=None):
        """Show the VCS panel's Changes (0) or History (1) tab, optionally
        selecting, or filtering by, `path`."""
        tab_widget = self.tree.file_preview.tab_widget
        if not self.vcs_panel or not shiboken6.isValid(self.vcs_panel):
            self.vcs_panel = VcsPanel(self)
            tab_widget.addTab(self.vcs_panel, 'VCS')
        tab_widget.setCurrentWidget(self.vcs_panel)
        self.vcs_panel.tabs.setCurrentIndex(tab)
        rel = vcs.rel_path(self.repo_root, path) if path else None
        self.vcs_panel.changes.refresh()
        if tab == 1:
            self.vcs_panel.history.set_filter(rel)
        else:
            self.vcs_panel.history.refresh()
            if rel:
                self.vcs_panel.changes.select(rel)

    def show_trust_dialog(self):
        root = self.untrusted_root
        dialog = TrustFolderDialog(self.tree, root)
        dialog.accepted.connect(lambda: self.trust_folder(root))
        dialog.open()

    @qasync.asyncSlot()
    async def trust_folder(self, root):
        await vcs.trust(root)
        self.refresh()

    def item_color(self, path, is_dir):
        if not self.repo_root:
            return None
        state = vcs.state(self.repo_status, vcs.rel_path(self.repo_root, path), is_dir)
        return QColor(VCS_COLORS[state]) if state else None

    @qasync.asyncSlot()
    async def run_vcs(self, func, *args):
        root = self.repo_root or self.tree.current_path
        try:
            await func(root, *args)
        except (RuntimeError, OSError) as e:
            if (
                func in (vcs.fetch, vcs.pull, vcs.push)
                and (await vcs.remote_url(root)).startswith('https://github.com/')
                and not await github.get_token()
            ):
                dialog = GitHubSignInDialog(self.tree)
                dialog.accepted.connect(lambda: self.run_vcs(func, *args))
                dialog.open()
            else:
                display_message(str(e), 'Error')
        self.refresh()

    def new_branch(self):
        name, ok = get_text(self.tree, "New Branch", "Enter branch name:")
        if ok and name.strip():
            self.run_vcs(vcs.create_branch, name.strip())

    def add_remote(self):
        dialog = AddRemoteDialog(self.tree, self.repo_root)
        dialog.accepted.connect(self.refresh)
        dialog.open()

    @qasync.asyncSlot()
    async def publish_to_github(self):
        if await github.get_token():
            dialog = GitHubPublishDialog(self.tree, self.repo_root)
            dialog.accepted.connect(self.refresh)
        else:
            dialog = GitHubSignInDialog(self.tree)
            dialog.accepted.connect(self.publish_to_github)
        dialog.open()

    def revert_paths(self, paths):
        reply = display_message_box(
            icon=QMessageBox.Question,
            title="Revert Changes",
            text=f"Discard all changes to {len(paths)} item(s)? This can't be undone.",
            buttons=QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.run_vcs(vcs.revert, paths)

    def confirm_push(self):
        reply = display_message_box(
            icon=QMessageBox.Question,
            title="Push",
            text=f"Push branch '{self.repo_branch or '(detached)'}' to the remote?",
            buttons=QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.run_vcs(vcs.push)

    def add_context_actions(self, menu, paths):
        if not self.repo_root:
            return
        rels = [vcs.rel_path(self.repo_root, p) for p in paths]
        codes = [
            code for path, code in self.repo_status.items()
            if any(
                path == rel or path.startswith(rel + '/')
                or (path.endswith('/') and rel.startswith(path))
                for rel in rels
            )
        ]
        menu.addSeparator()
        if len(paths) == 1 and not rels[0].startswith('..'):
            if rels[0] in self.repo_status or rels[0] + '/' in self.repo_status:
                menu.addAction("Show Diff").triggered.connect(
                    lambda: self.open_vcs_panel(0, paths[0]))
            menu.addAction("History").triggered.connect(
                lambda: self.open_vcs_panel(1, paths[0]))
        if any(code[1] != ' ' for code in codes):
            menu.addAction("Stage").triggered.connect(
                lambda: self.run_vcs(vcs.stage, paths))
        if any(code[0] not in ' ?' for code in codes):
            menu.addAction("Unstage").triggered.connect(
                lambda: self.run_vcs(vcs.unstage, paths))
        if any(code != '??' and 'A' not in code and 'R' not in code for code in codes):
            menu.addAction("Revert Changes").triggered.connect(
                lambda: self.revert_paths(paths))
        menu.addSeparator()


class TrustFolderDialog(QDialog):
    def __init__(self, parent, root):
        super().__init__(parent)
        self.setObjectName('trustFolderDialog')
        self.setWindowTitle('Trust Folder')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(440)

        title = QLabel('Trust this folder?')
        title.setObjectName('dialogTitle')

        message = QLabel(
            'This folder belongs to another user, so version control is '
            'off for it. Only trust folders you know are safe.')
        message.setWordWrap(True)

        path_lbl = QLabel(str(root))
        path_lbl.setObjectName('dialogDetail')
        path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_lbl.setWordWrap(True)

        cancel_btn = QPushButton('Not Now')
        cancel_btn.setProperty('class', 'dialog-button')
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        trust_btn = QPushButton('Trust Folder')
        trust_btn.setProperty('class', 'dialog-button')
        trust_btn.setProperty('primary', True)
        trust_btn.setDefault(True)
        trust_btn.clicked.connect(self.accept)
        button_row = CHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch(1)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(trust_btn)

        self.layout = CVBoxLayout(self)
        self.layout.setContentsMargins(24, 20, 24, 20)
        self.layout.addWidget(title)
        self.layout.addSpacing(12)
        self.layout.addWidget(message)
        self.layout.addSpacing(8)
        self.layout.addWidget(path_lbl)
        self.layout.addSpacing(18)
        self.layout.addLayout(button_row)
