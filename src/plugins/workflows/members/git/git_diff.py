from plugins.workflows.members import Member
from plugins.workflows.utils.git_checkpoints import diff, resolve_commit, snapshot
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='git_diff_settings')
class GitDiff(Member):
    """Outputs the diff between two commits, or between a commit and the
    working tree when `To` is empty."""
    default_role = 'block'
    default_avatar = ':/resources/icon-blocks.png'
    default_name = 'Git Diff'
    workflow_insert_mode = 'single'
    display_markdown = False
    OUTPUT = str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = self.receive

    async def receive(self):
        cwd = await self.format_config_value('directory', '{{ cwd }}')
        base = (await self.format_config_value('from')).strip()
        target = (await self.format_config_value('to')).strip()
        base_commit = await resolve_commit(cwd, base)
        if not base_commit:
            content = f'No checkpoint `{base}` to compare with.'
        else:
            if target:
                target_commit = await resolve_commit(cwd, target) or target
            else:
                exclude = await self.format_config_value('exclude', '*.db')
                target_commit = await snapshot(cwd, exclude=exclude)
            content = await diff(cwd, base_commit, target_commit) or 'No changes.'
        self.workflow.save_message(self.default_role, content, self.full_member_id())
        yield self.default_role, content
