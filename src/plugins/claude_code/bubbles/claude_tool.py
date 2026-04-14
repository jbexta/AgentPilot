import json

from plugins.workflows.bubbles import MessageBubble
from utils.helpers import set_module_type


@set_module_type(module_type='Bubbles')
class ClaudeToolBubble(MessageBubble):
    bubble_bg_color = '#1e222d'
    bubble_text_color = '#8c9fd4'

    def setMarkdownText(self, text, display_text=None):
        if display_text is None:
            try:
                data = json.loads(text)
                name = data.get('name', 'Tool')
                tool_input = data.get('input') or {}
                if name == 'Read':
                    offset = tool_input.get('offset', 0)
                    limit = tool_input.get('limit', 0)
                    file_path = tool_input.get('file_path', '')
                    cwd = self._get_project_cwd()
                    if cwd and file_path.startswith(cwd):
                        file_path = file_path[len(cwd):].lstrip('/\\')
                    header = f"**Read**"
                    display_text = (
                        f"{header}\n```\n{file_path} [{offset}:{offset + limit}]\n```"
                    )
                else:
                    args = json.dumps(tool_input, indent=2)[:500]
                    display_text = f"**{name}**\n\n```\n{args}\n```"
            except (ValueError, TypeError):
                display_text = text
        super().setMarkdownText(text, display_text=display_text)

    def _get_project_cwd(self):
        """Return the project's working_dir for the current chat.

        The member config does not contain ``working_dir`` — it lives on
        the project, so we resolve it via the workflow's context kind
        (``PROJECT:<id>``) and look up the project row directly.
        """
        from utils import sql

        context_id = getattr(self.workflow, 'context_id', None)
        if context_id is None:
            return None
        kind = sql.get_scalar(
            "SELECT kind FROM contexts WHERE id = ?", (context_id,)
        )
        if not kind or not kind.startswith('PROJECT:'):
            return None
        try:
            project_id = int(kind.split(':', 1)[1])
        except (ValueError, IndexError):
            return None
        config = sql.get_scalar(
            "SELECT config FROM projects WHERE id = ?",
            (project_id,),
            load_json=True,
        )
        if not config:
            return None
        return config.get('working_dir')
