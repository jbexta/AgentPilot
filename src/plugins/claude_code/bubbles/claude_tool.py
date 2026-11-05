import difflib
import html
import json

from PySide6.QtCore import QUrl
from PySide6.QtGui import Qt, QTextCursor

from gui import system as gui_system
from plugins.workflows.bubbles import MessageBubble, MessageButton
from plugins.workflows.utils.runs import get_run_manager
from utils.helpers import message_button, set_module_type

DIFF_ADD_COLOR = '#4ade80'
DIFF_DEL_COLOR = '#f87171'
DIFF_ADD_BG = '#1e3227'
DIFF_DEL_BG = '#39222a'
DIFF_LINE_NO_COLOR = '#566181'
DIFF_MAX_ROWS = 40


def _locate_line(file_path, *needles):
    """Best-effort 1-based line number of the first needle found in the file."""
    try:
        with open(file_path, encoding='utf-8') as f:
            content = f.read()
    except OSError:
        return 1
    for needle in needles:
        if needle:
            idx = content.find(needle)
            if idx != -1:
                return content[:idx].count('\n') + 1
    return 1


def build_diff_rows(old_lines, new_lines, start_line):
    """Return diff rows as (old_no, new_no, sign, text) tuples."""
    rows = []
    old_no = new_no = start_line
    matcher = difflib.SequenceMatcher(
        None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ('replace', 'delete'):
            for ln in old_lines[i1:i2]:
                rows.append((old_no, None, '-', ln))
                old_no += 1
        if tag in ('replace', 'insert'):
            for ln in new_lines[j1:j2]:
                rows.append((None, new_no, '+', ln))
                new_no += 1
        if tag == 'equal':
            for ln in old_lines[i1:i2]:
                rows.append((old_no, new_no, ' ', ln))
                old_no += 1
                new_no += 1
    return rows


def _diff_row_html(old_no, new_no, sign, text):
    if sign == '+':
        bg, color = DIFF_ADD_BG, DIFF_ADD_COLOR
    elif sign == '-':
        bg, color = DIFF_DEL_BG, DIFF_DEL_COLOR
    else:
        bg, color = None, '#8c9fd4'
    stripped = text.lstrip(' ')
    indent = '&nbsp;' * (len(text) - len(stripped))
    body = indent + (html.escape(stripped) or '&nbsp;')
    bg_attr = f' bgcolor="{bg}"' if bg else ''
    num_style = f'color:{DIFF_LINE_NO_COLOR};'
    return (
        f'<tr>'
        f'<td align="right"><span style="{num_style}">{old_no or ""}</span></td>'
        f'<td align="right"><span style="{num_style}">{new_no or ""}</span></td>'
        f'<td{bg_attr}><span style="color:{color}">{sign}&nbsp;{body}</span></td>'
        f'</tr>'
    )


class _ApprovalButton(MessageButton):
    approved = True
    hover_toggled = False  # shown only while awaiting approval

    def setVisible(self, visible):
        super().setVisible(self.msg_container.bubble.awaiting_approval())

    def on_clicked(self):
        self.msg_container.bubble.resolve_approval(self.approved)


@set_module_type(module_type='Bubbles')
class ClaudeToolBubble(MessageBubble):
    bubble_bg_color = '#1e222d'
    bubble_text_color = '#8c9fd4'
    wrap_code = True

    def __init__(self, parent, message, **kwargs):
        self.approval_prompt = ''
        super().__init__(parent, message, **kwargs)
        get_run_manager().changed.connect(self.refresh_approval)
        self.refresh_approval()

    def _tool_field(self, key):
        try:
            return json.loads(self.text).get(key)
        except (ValueError, TypeError, AttributeError):
            return None

    @property
    def tool_use_id(self):
        return self._tool_field('id')

    def awaiting_approval(self):
        return get_run_manager().is_awaiting_confirm(self.workflow.context_id, self.tool_use_id)

    def refresh_approval(self):
        """Show the approval prompt and buttons while the run awaits the
        user's decision on this tool use."""
        prompt = get_run_manager().confirm_label(self.workflow.context_id, self.tool_use_id)
        if prompt == (self._tool_field('name') or '').removeprefix('mcp__ui__'):
            prompt = ''  # already shown as the tool name
        if prompt != self.approval_prompt:
            self.approval_prompt = prompt
            self.setMarkdownText(self.text)
        for name in ('btn_accept', 'btn_reject'):
            button = getattr(self.parent, name, None)
            if button:
                button.setVisible(True)
        self.updateGeometry()  # re-fit beside the shown/hidden buttons

    def append_text(self, text):
        super().append_text(text)
        self.refresh_approval()

    def resolve_approval(self, approved):
        get_run_manager().resolve_confirm(self.workflow.context_id, self.tool_use_id, approved)

    @message_button('btn_accept')
    class AcceptButton(_ApprovalButton):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                icon_path=':/resources/icon-tick.svg',
            )

    @message_button('btn_reject')
    class RejectButton(_ApprovalButton):
        approved = False

        def __init__(self, parent):
            super().__init__(
                parent=parent,
                icon_path=':/resources/icon-cross.png',
            )

    def setMarkdownText(self, text, display_text=None):
        if display_text is None:
            try:
                data = json.loads(text)
                name = data.get('name', 'Tool')
                tool_input = data.get('input') or {}
                if name in ('Edit', 'Write'):
                    self._render_diff(text, name, tool_input)
                    return
                if name == 'ExitPlanMode':
                    display_text = (
                        f"**Plan**\n\n{tool_input.get('plan', '')}"
                    )
                elif name == 'WebSearch':
                    display_text = (
                        f"**Searching**\n\n{tool_input.get('query', '')}"
                    )
                elif name == 'Bash':
                    title = '**Bash**' + (' · *background*' if tool_input.get('run_in_background') else '')
                    description = tool_input.get('description', '')
                    display_text = '\n\n'.join(filter(None, (
                        title,
                        f'*{description}*' if description else '',
                        f"```bash\n{tool_input.get('command', '')}\n```",
                    )))
                elif name == 'Read':
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
                elif not tool_input:
                    display_text = f"**{name}**"
                else:
                    args = json.dumps(tool_input, indent=2)[:500]
                    display_text = f"**{name}**\n\n```\n{args}\n```"
            except (ValueError, TypeError):
                display_text = text
        if self.approval_prompt:
            prompt = self.approval_prompt.replace('\n', '  \n')
            display_text = f'*{prompt}*\n\n{display_text}'
        super().setMarkdownText(text, display_text=display_text)

    def _render_diff(self, text, name, tool_input):
        file_path = tool_input.get('file_path', '')
        if name == 'Write':
            old_lines = []
            new_lines = (tool_input.get('content') or '').splitlines()
            start_line = 1
        else:
            old = tool_input.get('old_string') or ''
            new = tool_input.get('new_string') or ''
            old_lines = old.splitlines()
            new_lines = new.splitlines()
            start_line = _locate_line(file_path, old, new)

        rows = build_diff_rows(old_lines, new_lines, start_line)
        adds = sum(1 for r in rows if r[2] == '+')
        dels = sum(1 for r in rows if r[2] == '-')
        first_change = next((r for r in rows if r[2] != ' '), None)
        first_line = (first_change[1] or first_change[0]) if first_change else start_line

        overflow = len(rows) - DIFF_MAX_ROWS
        if overflow > 0:
            rows = rows[:DIFF_MAX_ROWS]
        body = ''.join(_diff_row_html(*r) for r in rows)
        if overflow > 0:
            body += (
                f'<tr><td></td><td></td><td><span style="color:'
                f'{DIFF_LINE_NO_COLOR}">… {overflow} more lines</span>'
                f'</td></tr>'
            )

        display_path = file_path
        cwd = self._get_project_cwd()
        if cwd and display_path.startswith(cwd):
            display_path = display_path[len(cwd):].lstrip('/\\')
        href = f'{QUrl.fromLocalFile(file_path).toString()}#L{first_line}'
        link_color = gui_system.manager.config.get(
            'display.link_color', '#438BB9')
        counts = f'&nbsp;&nbsp;<span style="color:{DIFF_ADD_COLOR}">+{adds}</span>'
        if dels:
            counts += f' <span style="color:{DIFF_DEL_COLOR}">-{dels}</span>'
        prompt = html.escape(self.approval_prompt).replace('\n', '<br>')
        header = (
            (f'<i>{prompt}</i><br>' if prompt else '')
            + f'<b>{name}</b>&nbsp;&nbsp;'
            f'<a href="{href}" style="color:{link_color}">'
            f'{html.escape(display_path)}</a>{counts}'
        )

        font = gui_system.manager.config.get('display.text_font', '')
        size = gui_system.manager.config.get('display.text_size', 15)
        self.text = text
        self.setHtml(
            f'<body style="color:{self.bubble_text_color};'
            f'font-family:{font};font-size:{size}px">'
            f'{header}'
            f'<table cellspacing="0" cellpadding="1" '
            f'style="font-family:monospace;font-size:{size - 2}px">'
            f'{body}</table></body>'
        )
        self.code_blocks = []

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            cursor = self.cursorForPosition(event.pos())
            if cursor.charFormat().isAnchor():
                href = cursor.charFormat().anchorHref()
                if href.startswith('file://'):
                    if not self._open_in_file_tree(href):
                        from PySide6.QtGui import QDesktopServices
                        url = QUrl(href)
                        url.setFragment(None)
                        QDesktopServices.openUrl(url)
                    return
        super().mousePressEvent(event)

    def _open_in_file_tree(self, href):
        """Open the file in the nearest ancestor's FileTree.

        Both project pages and the PageEditor popup embed a GeneralProject
        widget tree whose ``widgets`` list holds the tabs with the FileTree,
        so walking up the Qt parent chain finds the tree belonging to this
        chat.
        """
        from pathlib import Path

        from plugins.files.widgets.file_tree import FileTree

        url = QUrl(href)
        path = Path(url.toLocalFile()).resolve()
        frag = url.fragment()
        line = int(frag[1:]) if frag.startswith('L') and frag[1:].isdigit() else None
        w = self.parentWidget()
        while w is not None:
            for child in getattr(w, 'widgets', []):
                files = getattr(child, 'pages', {}).get('Files')
                if isinstance(files, FileTree):
                    child.goto_page('Files')
                    child = files
                if isinstance(child, FileTree):
                    child.navigate_to(path)
                    if line:
                        self._scroll_preview_to_line(child, path, line)
                    return True
            w = w.parentWidget()
        return False

    def _scroll_preview_to_line(self, file_tree, path, line):
        studio = file_tree.file_preview.open_files.get(str(path))
        editor = getattr(studio, 'editor', None)
        if editor is None:
            return
        block = editor.document().findBlockByNumber(line - 1)
        editor.setTextCursor(QTextCursor(block))
        editor.centerCursor()

    def _get_project_cwd(self):
        """Return the project's working_dir for the current chat."""
        return getattr(self.workflow, 'params', {}).get('cwd')
