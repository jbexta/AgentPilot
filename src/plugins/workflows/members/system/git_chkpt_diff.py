from plugins.workflows.members import Member
from plugins.workflows.utils.git_checkpoints import checkpoint_ref, diff, git, save_checkpoint, snapshot
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='git_checkpoint_settings')
class GitChkptDiff(Member):
    """Snapshots a repo's working tree as a commit kept under
    `refs/agentpilot/checkpoints/<name>`, and outputs the diff from the
    previous snapshot."""
    default_role = 'block'
    default_avatar = ':/resources/icon-blocks.png'
    default_name = 'Git ChkPt Diff'
    workflow_insert_mode = 'single'
    display_markdown = False
    OUTPUT = str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = self.receive

    async def receive(self):
        cwd = await self.format_config_value('directory', '{{ cwd }}')
        ref = checkpoint_ref(await self.format_config_value('checkpoint_name', '{{ project_name }}_snapshot'))
        expire = (await self.format_config_value('expire', '30 days')).strip()
        previous = await git(cwd, 'for-each-ref', '--format=%(objectname)', ref)
        exclude = await self.format_config_value('exclude', '*.db')
        current = await snapshot(cwd, self.config.get('include_untracked', True), exclude)
        await save_checkpoint(cwd, ref, current, expire)
        if previous:
            content = await diff(cwd, previous, current) or 'No changes since the last checkpoint.'
        else:
            content = f'First checkpoint ({current[:8]}), nothing to compare yet.'
        self.workflow.save_message(self.default_role, content, self.full_member_id())
        yield self.default_role, content
