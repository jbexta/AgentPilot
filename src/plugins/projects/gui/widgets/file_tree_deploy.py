import qasync
import shiboken6
from PySide6.QtWidgets import QMessageBox

from gui.gui_utils.custom_menu import CustomMenu
from gui.gui_utils.layouts import CHBoxLayout
from plugins.files.widgets.file_tree import FileTreeExtension
from plugins.projects.gui.gui_utils.deploy_target import DeployTargetDialog
from plugins.projects.gui.widgets.deploy_panel import DeployPanel
from plugins.projects.utils import deploy, vcs
from utils.helpers import (
    display_message, display_message_box, format_llm_tools, llm_tool,
    set_module_type,
)


@set_module_type('Widgets')
class FileTreeDeploy(FileTreeExtension):
    """The Deploy menu of a FileTree: push a repo to web servers and pull
    from them."""

    def __init__(self, tree):
        super().__init__(tree)
        self.repo_root = None
        self.targets = {}
        self.panel = None

        self.menu = CustomMenu(parent=self, schema=[{
            'text': 'Deploy',
            'icon_path': ':/resources/icon-globe.png',
            'submenu': self.menu_schema,
        }])
        self.menu.create_toolbar()
        self.layout = CHBoxLayout(self)
        self.layout.addWidget(self.menu)
        self.hide()

    def menu_schema(self):
        return [
            *({
                'text': name,
                'submenu': [
                    {'text': 'Push...',
                     'target': lambda *_, n=name: self.open_panel(n, 'push')},
                    {'text': 'Pull...',
                     'target': lambda *_, n=name: self.open_panel(n, 'pull')},
                    {'type': 'separator'},
                    {'text': 'Edit Target...',
                     'target': lambda *_, n=name: self.edit_target(n)},
                    {'text': 'Delete Target...',
                     'target': lambda *_, n=name: self.delete_target(n)},
                ],
            } for name in self.targets),
            *([{'type': 'separator'}] if self.targets else []),
            {'text': 'Add Target...', 'target': lambda *_: self.edit_target()},
        ]

    @qasync.asyncSlot()
    async def refresh(self):
        if not shiboken6.isValid(self) or not self.tree.isVisible():
            return
        try:
            root = await vcs.repo_root(self.tree.current_path)
            targets = await deploy.targets(root) if root else {}
        except (RuntimeError, OSError):
            root, targets = None, {}
        if not shiboken6.isValid(self):
            return
        self.repo_root, self.targets = root, targets
        self.setVisible(root is not None)

    def open_panel(self, name, kind):
        tab_widget = self.tree.file_preview.tab_widget
        if not self.panel or not shiboken6.isValid(self.panel):
            self.panel = DeployPanel(self)
            tab_widget.addTab(self.panel, 'Deploy')
        tab_widget.setCurrentWidget(self.panel)
        self.panel.load(self.targets[name], kind)

    def edit_target(self, name=None):
        dialog = DeployTargetDialog(
            self.tree, self.repo_root, self.targets.get(name))
        dialog.accepted.connect(self.refresh)
        dialog.open()

    @qasync.asyncSlot()
    async def delete_target(self, name):
        reply = display_message_box(
            icon=QMessageBox.Question,
            title='Delete Target',
            text=f"Delete deploy target '{name}'? Files on the server are "
                 "not touched.",
            buttons=QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            await deploy.delete_target(self.repo_root, name)
        except RuntimeError as e:
            display_message(str(e), 'Error')
        self.refresh()

    def get_agent_visualisation(self, refs):
        tools = format_llm_tools(self, refs)
        targets = ', '.join(self.targets) or 'none'
        return f'{tools}\n    Deploy targets: {targets}'

    async def run_for_agent(self, name, kind):
        target = self.targets.get(name)
        if not target:
            raise ValueError(
                f"No deploy target '{name}'. Targets: "
                f"{', '.join(self.targets) or 'none'}")
        make_plan = deploy.push_plan if kind == 'push' else deploy.pull_plan
        run = deploy.push if kind == 'push' else deploy.pull
        plan = await make_plan(self.repo_root, target)
        skipped = [
            f'{item.path} ({item.label})'
            for item in plan.items if not item.ticked]
        lines = []
        await run(self.repo_root, plan, lines.append)
        if skipped:
            lines.append('Not ticked, so skipped: ' + ', '.join(skipped))
        self.tree.refresh_extensions()
        return '\n'.join(lines)

    @llm_tool(
        description="Push the repo's last commit to a deploy target and "
                    "run its post-deploy commands. Only ticked-by-default "
                    "changes are sent.",
        params={'target': 'Name of the deploy target'},
        confirm=True,
    )
    async def push(self, target: str):
        return await self.run_for_agent(target, 'push')

    @llm_tool(
        description='Download changed files from a deploy target into the '
                    'working tree. Only ticked-by-default changes are taken.',
        params={'target': 'Name of the deploy target'},
        confirm=True,
    )
    async def pull(self, target: str):
        return await self.run_for_agent(target, 'pull')
