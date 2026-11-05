from plugins.workflows.members import Member
from plugins.workflows.utils.git_checkpoints import checkpoint_ref, save_checkpoint, snapshot
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='git_checkpoint_settings')
class GitCheckpoint(Member):
    """Snapshots a repo's working tree as a commit kept under
    `refs/agentpilot/checkpoints/<name>`, and outputs its hash."""
    default_role = 'block'
    default_avatar = ':/resources/icon-blocks.png'
    default_name = 'Git Checkpoint'
    workflow_insert_mode = 'single'
    OUTPUT = str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = self.receive

    async def receive(self):
        cwd = await self.format_config_value('directory', '{{ cwd }}')
        name = await self.format_config_value('checkpoint_name', '{{ project_name }}_snapshot')
        expire = (await self.format_config_value('expire', '30 days')).strip()
        exclude = await self.format_config_value('exclude', '*.db')
        current = await snapshot(cwd, self.config.get('include_untracked', True), exclude)
        await save_checkpoint(cwd, checkpoint_ref(name), current, expire)
        self.workflow.save_message(self.default_role, current, self.full_member_id())
        yield self.default_role, current
