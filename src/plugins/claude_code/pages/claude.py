import asyncio
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import qasync
from claude_agent_sdk import project_key_for_directory
from PySide6.QtCore import QPointF, QRectF, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QWidget,
)

from gui import style
from gui.gui_utils.helpers import clear_layout
from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_tabs import ConfigTabs
from plugins.files.widgets.file_tree import FileTree
from plugins.claude_code.members.conversation.claude_code import format_tool_result_content
from plugins.claude_code.utils.projects import DEFAULT_CWD, get_default_cwd
from plugins.claude_code.widgets.claude_context import ClaudeContext
from plugins.claude_code.widgets.cc_user_settings import (
    CCSettings_Advanced,
    CCSettings_General,
    CCSettings_Hooks,
    CCSettings_Permissions,
    settings_path,
)
from utils import sql
from utils.helpers import (
    display_message,
    display_message_box,
    set_module_type,
)


META_LINE_TYPES = {
    'permission-mode',
    'file-history-snapshot',
    'summary',
    'system',
}


_COMMAND_MESSAGE_PREFIXES = (
    '<command-name>',
    '<command-message>',
    '<command-args>',
    '<local-command-stdout>',
    '<local-command-caveat>',
)


def _is_command_message(text):
    """True if ``text`` is a Claude Code slash-command meta message.

    Slash commands and their stdout are stored as user lines wrapped in
    ``<command-*>`` / ``<local-command-*>`` tags; they are app plumbing,
    not conversation content, so they are skipped on import.
    """
    return text.strip().startswith(_COMMAND_MESSAGE_PREFIXES)


def _iso_to_unix(iso_str):
    if not iso_str:
        return int(datetime.now().timestamp())
    try:
        return int(datetime.fromisoformat(
            iso_str.replace('Z', '+00:00')).timestamp())
    except Exception:
        return int(datetime.now().timestamp())


def _read_jsonl(path):
    lines = []
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    lines.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return lines


def _session_cwd(lines):
    for ln in lines:
        cwd = ln.get('cwd')
        if cwd:
            return cwd
    return None


def _session_id(lines):
    for ln in lines:
        sid = ln.get('sessionId')
        if sid:
            return sid
    return None


def _ensure_project(cwd):
    """Find or create a project row for ``cwd``. Returns project id."""
    row = sql.get_results(
        "SELECT id FROM projects "
        "WHERE json_extract(config, '$.working_dir') = ?",
        (cwd,),
    )
    if row:
        return row[0][0]
    sql.execute(
        "INSERT INTO projects (name, config) VALUES (?, ?)",
        (os.path.basename(cwd) or cwd,
         json.dumps({'working_dir': cwd})),
    )
    return sql.get_scalar(
        "SELECT id FROM projects "
        "WHERE json_extract(config, '$.working_dir') = ?",
        (cwd,),
    )


def _existing_chain_state(source_uuids):
    """Return (context_id, set of already-imported source_uuids).

    A chain is matched by the ``source_uuid`` of its message lines, not
    by session id. When an old session file ages out of
    ``~/.claude/projects/`` the chain root changes, and a resumed
    session may replay its parent's lines verbatim; either case would
    fool a session-id match into re-importing the whole chain. Line
    uuids are stable and globally unique, so they reliably identify a
    chain that has already been imported.

    If no line of the chain has been imported yet, returns (None, set()).
    """
    uuids = [u for u in source_uuids if u]
    context_id = None
    for start in range(0, len(uuids), 500):
        chunk = uuids[start:start + 500]
        placeholders = ','.join('?' * len(chunk))
        row = sql.get_results(
            f"SELECT context_id FROM contexts_messages "
            f"WHERE json_extract(log, '$.source_uuid') IN ({placeholders}) "
            f"LIMIT 1",
            tuple(chunk),
        )
        if row:
            context_id = row[0][0]
            break
    if context_id is None:
        return None, set()
    rows = sql.get_results(
        "SELECT json_extract(log, '$.source_uuid') "
        "FROM contexts_messages WHERE context_id = ?",
        (context_id,),
    )
    return context_id, {r[0] for r in rows if r[0]}


def _build_resume_chains(sessions_by_cwd):
    """Merge resumed sessions in each cwd into chronological chains.

    A "chain" is a list of (session_id, lines) ordered oldest-first.
    Sessions are linked by ``parentUuid``: if any uuid in session A appears
    as a ``parentUuid`` reference of session B's first non-meta line, B
    resumes A.
    """
    chains_by_cwd = {}
    for cwd, sessions in sessions_by_cwd.items():
        uuid_to_session = {}
        first_parent = {}
        for sid, lines in sessions.items():
            for ln in lines:
                u = ln.get('uuid')
                if u:
                    uuid_to_session.setdefault(u, sid)
            for ln in lines:
                if ln.get('type') in META_LINE_TYPES:
                    continue
                first_parent[sid] = ln.get('parentUuid')
                break

        # parent session id for each session (None = root)
        parent_session = {}
        for sid, p_uuid in first_parent.items():
            parent_sid = uuid_to_session.get(p_uuid) if p_uuid else None
            if parent_sid == sid:
                parent_sid = None
            parent_session[sid] = parent_sid

        # children index
        children = {}
        for sid, p in parent_session.items():
            children.setdefault(p, []).append(sid)

        def _start_time(sid):
            for ln in sessions[sid]:
                if ln.get('type') in META_LINE_TYPES:
                    continue
                return _iso_to_unix(ln.get('timestamp'))
            return 0

        roots = sorted(children.get(None, []), key=_start_time)
        chains = []
        for root in roots:
            chain = []
            cur = root
            while cur is not None:
                chain.append((cur, sessions[cur]))
                kids = sorted(children.get(cur, []), key=_start_time)
                cur = kids[0] if kids else None
            chains.append(chain)
        chains_by_cwd[cwd] = chains
    return chains_by_cwd


def _extract_messages(chain):
    """Yield (role, msg, unix, source_uuid) tuples from a resume chain.

    Multi-block lines emit one tuple per block; ``source_uuid`` is the
    parent line's uuid in all cases (so dedupe on re-import is by line,
    not by block — re-imports won't double-count a previously-imported
    multi-block line).
    """
    seen_uuids = set()
    for _sid, lines in chain:
        for ln in lines:
            ltype = ln.get('type')
            if ltype in META_LINE_TYPES:
                continue
            if ln.get('isSidechain'):
                continue
            uuid = ln.get('uuid')
            if uuid and uuid in seen_uuids:
                continue
            if uuid:
                seen_uuids.add(uuid)
            ts = _iso_to_unix(ln.get('timestamp'))

            if ltype == 'user':
                msg = ln.get('message') or {}
                content = msg.get('content')
                if isinstance(content, str):
                    if content.strip() and not _is_command_message(content):
                        yield 'user', content, ts, uuid
                elif isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get('type') == 'tool_result':
                            yield ('claude_tool_result',
                                   format_tool_result_content(block.get('content')),
                                   ts, uuid)
                        elif block.get('type') == 'text':
                            text = block.get('text', '')
                            if text.strip():
                                yield 'user', text, ts, uuid
            elif ltype == 'assistant':
                msg = ln.get('message') or {}
                content = msg.get('content')
                if isinstance(content, str):
                    if content.strip():
                        yield 'assistant', content, ts, uuid
                elif isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get('type')
                        if btype == 'text':
                            text = block.get('text', '')
                            if text.strip():
                                yield 'assistant', text, ts, uuid
                        elif btype == 'thinking':
                            think = block.get('thinking', '')
                            if think.strip():
                                yield 'thinking', think, ts, uuid
                        elif btype == 'tool_use':
                            yield ('claude_tool',
                                   json.dumps({
                                       'name': block.get('name', ''),
                                       'input': block.get('input') or {},
                                   }),
                                   ts, uuid)


def _chain_name(chain):
    for _sid, lines in chain:
        for ln in lines:
            slug = ln.get('slug')
            if slug:
                return slug.replace('-', ' ')
    for _sid, lines in chain:
        for ln in lines:
            if ln.get('type') != 'user':
                continue
            msg = (ln.get('message') or {}).get('content')
            if (isinstance(msg, str) and msg.strip()
                    and not _is_command_message(msg)):
                return msg.strip()[:80]
    return 'Imported chat'


def import_claude_code_sessions():
    """Scan ~/.claude/projects/ and import sessions into AgentPilot.

    Returns a summary dict with counts.
    """
    root = Path.home() / '.claude' / 'projects'
    if not root.is_dir():
        return {
            'new_chats': 0, 'updated_chats': 0, 'new_messages': 0,
            'unchanged': 0, 'projects': 0, 'errors': 0,
        }

    sessions_by_cwd = {}
    errors = 0
    for jsonl_path in root.glob('*/*.jsonl'):
        lines = _read_jsonl(jsonl_path)
        if not lines:
            continue
        cwd = _session_cwd(lines)
        sid = _session_id(lines) or jsonl_path.stem
        if not cwd:
            errors += 1
            continue
        sessions_by_cwd.setdefault(cwd, {})[sid] = lines

    chains_by_cwd = _build_resume_chains(sessions_by_cwd)

    new_chats = 0
    new_messages = 0
    updated_chats = 0
    unchanged = 0
    for cwd, chains in chains_by_cwd.items():
        if not chains:
            continue
        project_id = _ensure_project(cwd)
        kind = f'PROJECT:{project_id}'
        member_id = '2'

        for chain in chains:
            root_sid = chain[0][0]
            messages = list(_extract_messages(chain))
            if not messages:
                unchanged += 1
                continue

            source_uuids = [m[3] for m in messages]
            context_id, existing_uuids = _existing_chain_state(source_uuids)
            is_new = context_id is None

            if is_new:
                name = _chain_name(chain)
                sql.execute(
                    "INSERT INTO contexts (kind, name, config) "
                    "VALUES (?, ?, ?)",
                    (kind, name, '{}'),
                )
                context_id = sql.get_scalar(
                    "SELECT MAX(id) FROM contexts WHERE kind = ?", (kind,)
                )

            inserted = 0
            for role, msg, unix, source_uuid in messages:
                if source_uuid and source_uuid in existing_uuids:
                    continue
                log_obj = {
                    'context_id': context_id,
                    'member_id': member_id,
                    'session_id': root_sid,
                    'source_uuid': source_uuid,
                }
                sql.execute(
                    "INSERT INTO contexts_messages "
                    "(unix, context_id, member_id, role, msg, log) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (unix, context_id, member_id, role, msg,
                     json.dumps(log_obj)),
                )
                inserted += 1

            new_messages += inserted
            if is_new:
                new_chats += 1
            elif inserted:
                updated_chats += 1
            else:
                unchanged += 1

    return {
        'new_chats': new_chats,
        'updated_chats': updated_chats,
        'new_messages': new_messages,
        'unchanged': unchanged,
        'projects': len(chains_by_cwd),
        'errors': errors,
    }


def delete_imported_sessions():
    """Remove every chat and message created by Claude Code import.

    Imported messages carry a ``session_id`` in their ``log`` JSON; their
    parent contexts are deleted along with them.

    Returns a summary dict with ``chats`` and ``messages`` counts.
    """
    rows = sql.get_results(
        "SELECT DISTINCT context_id FROM contexts_messages "
        "WHERE json_extract(log, '$.session_id') IS NOT NULL"
    )
    context_ids = [r[0] for r in rows if r[0] is not None]
    if not context_ids:
        return {'chats': 0, 'messages': 0}

    placeholders = ','.join('?' * len(context_ids))
    params = tuple(context_ids)
    msg_count = sql.get_scalar(
        f"SELECT COUNT(*) FROM contexts_messages "
        f"WHERE context_id IN ({placeholders})",
        params,
    )
    sql.execute(
        f"DELETE FROM contexts_messages "
        f"WHERE context_id IN ({placeholders})",
        params,
    )
    sql.execute(
        f"DELETE FROM contexts WHERE id IN ({placeholders})",
        params,
    )
    return {'chats': len(context_ids), 'messages': msg_count}


CHART_DAYS = 30
SERIES_COLORS = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181']
OTHER_COLOR = '#6b6b68'
TOKEN_FIELDS = (
    ('input', 'input_tokens'),
    ('output', 'output_tokens'),
    ('cache_write', 'cache_creation_input_tokens'),
    ('cache_read', 'cache_read_input_tokens'),
)


def scan_local_usage():
    """Aggregate token usage from every Claude Code session log.

    Streamed responses repeat one message across several lines, so lines
    are deduplicated by message id, keeping the last (final) usage.
    """
    latest = {}
    for path in (Path.home() / '.claude' / 'projects').rglob('*.jsonl'):
        lines = _read_jsonl(path)
        project_dir = _session_cwd(lines) or 'Unknown'
        for ln in lines:
            msg = ln.get('message') or {}
            if (ln.get('type') != 'assistant' or not msg.get('usage')
                    or msg.get('model') == '<synthetic>'):
                continue
            latest[msg.get('id') or ln.get('uuid')] = (project_dir, ln)

    by_day = defaultdict(lambda: defaultdict(int))
    models = defaultdict(lambda: defaultdict(int))
    projects = defaultdict(lambda: {
        'sessions': set(), 'messages': 0, 'tokens': 0, 'last': 0})
    for project_dir, ln in latest.values():
        msg = ln['message']
        counts = {k: msg['usage'].get(f) or 0 for k, f in TOKEN_FIELDS}
        total = sum(counts.values())
        unix = _iso_to_unix(ln.get('timestamp'))
        model = models[msg['model']]
        model['messages'] += 1
        for key, val in counts.items():
            model[key] += val
        model['total'] += total
        by_day[datetime.fromtimestamp(unix).date()][msg['model']] += total
        project = projects[project_dir]
        project['sessions'].add(ln.get('sessionId'))
        project['messages'] += 1
        project['tokens'] += total
        project['last'] = max(project['last'], unix)
    return {'by_day': by_day, 'models': models, 'projects': projects}


def _fmt_tokens(n):
    for size, suffix in ((1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if n >= size:
            return f'{n / size:.1f}{suffix}'
    return str(n)


def _nice_step(raw):
    mag = 10 ** math.floor(math.log10(raw))
    return next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)


class UsageChart(QWidget):
    """Stacked daily bar chart, one colored segment per series."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFixedHeight(240)
        self.days, self.colors, self.totals, self.tips = [], {}, [], []

    def set_data(self, days, colors, totals, tips):
        self.days, self.colors, self.totals, self.tips = (
            days, colors, totals, tips)
        self.update()

    def _plot_rect(self):
        return QRectF(self.rect()).adjusted(52, 8, -8, -24)

    def paintEvent(self, event):
        if not self.days:
            return
        painter = QPainter(self)
        rect = self._plot_rect()
        peak = max(sum(t.values()) for t in self.totals) or 1
        step = _nice_step(peak / 4)
        top = math.ceil(peak / step) * step
        text = QColor(style.TEXT_COLOR)
        grid = QColor(text)
        grid.setAlphaF(0.15)

        for i in range(round(top / step) + 1):
            y = rect.bottom() - i * step / top * rect.height()
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(text)
            painter.drawText(QRectF(0, y - 8, rect.left() - 6, 16),
                             Qt.AlignRight | Qt.AlignVCenter,
                             _fmt_tokens(i * step))

        slot = rect.width() / len(self.days)
        last = len(self.days) - 1
        for i, (day, totals) in enumerate(zip(self.days, self.totals)):
            if i % 5 == last % 5:
                painter.setPen(text)
                painter.drawText(
                    QRectF(rect.left() + i * slot - 30, rect.bottom() + 4,
                           slot + 60, 18),
                    Qt.AlignHCenter | Qt.AlignTop, f'{day:%d %b}')
            painter.setPen(Qt.NoPen)
            y = rect.bottom()
            for name, color in self.colors.items():
                h = totals.get(name, 0) / top * rect.height()
                if h <= 0:
                    continue
                painter.setBrush(QColor(color))
                painter.drawRect(QRectF(rect.left() + i * slot + slot * 0.1,
                                        y - h, slot * 0.8, max(h - 1, 1)))
                y -= h

    def mouseMoveEvent(self, event):
        rect = self._plot_rect()
        pos = event.position()
        if not self.days or not rect.contains(pos):
            QToolTip.hideText()
            return
        idx = int((pos.x() - rect.left()) / (rect.width() / len(self.days)))
        QToolTip.showText(event.globalPosition().toPoint(),
                          self.tips[idx], self)


def _section_label(text):
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    font.setPointSize(font.pointSize() + 1)
    label.setFont(font)
    return label


def _fill_table(table, headers, rows):
    table.clear()
    table.setColumnCount(len(headers))
    table.setRowCount(len(rows))
    table.setHorizontalHeaderLabels(headers)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            item = QTableWidgetItem(str(val))
            if c:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    table.setFixedHeight(
        table.horizontalHeader().height()
        + sum(table.rowHeight(r) for r in range(len(rows))) + 4)


def auto_memory_dir(scope, project_dir=None):
    """The selected project's auto-memory folder, or None if there isn't
    one. Auto-memory is per project, so ``user`` scope has none."""
    if scope == 'user' or not project_dir:
        return None
    memory_dir = (Path.home() / '.claude' / 'projects'
                  / project_key_for_directory(project_dir) / 'memory')
    return memory_dir if memory_dir.is_dir() else None


def claude_md_location(scope, project_dir=None):
    """(root folder, existing CLAUDE.md file or None) for ``scope``."""
    if scope == 'user' or not project_dir:
        root, names = Path.home() / '.claude', ['CLAUDE.md']
    elif scope == 'project_local':
        root, names = Path(project_dir), ['CLAUDE.local.md']
    else:
        root, names = Path(project_dir), ['CLAUDE.md', '.claude/CLAUDE.md']
    return root, next(
        (root / n for n in names if (root / n).is_file()), None)


class _ImportThread(QThread):
    finished_with = Signal(object, object)

    def run(self):
        try:
            result = import_claude_code_sessions()
            self.finished_with.emit(result, None)
        except Exception as exc:
            self.finished_with.emit(None, exc)


@set_module_type(module_type='Pages')
class Page_Claude_Settings(ConfigTabs):
    display_name = 'Claude'
    page_type = 'settings'

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.conf_namespace = 'claude'
        self.propagate_config = True

        self.scope_bar = self.ScopeBar(parent=self)
        self.layout.insertWidget(0, self.scope_bar)

        self.pages = {
            'Usage': self.Page_Usage(parent=self),
            'Import': self.Page_Import(parent=self),
            'Defaults': self.Page_Defaults(parent=self),
            'CLAUDE.md': self.Page_ClaudeMd(parent=self),
            'Memory': self.Page_Memory(parent=self),
            'General': CCSettings_General(parent=self),
            'Permissions': CCSettings_Permissions(parent=self),
            'Hooks': CCSettings_Hooks(parent=self),
            'MCP & Advanced': CCSettings_Advanced(parent=self),
        }

    def cc_settings_path(self):
        """Settings file for the scope selected in the scope bar.

        Picked up by the ``_FileBacked*`` widgets via their
        ``resolve_settings_path`` parent walk.
        """
        return self.scope_bar.current_path()

    class ScopeBar(QWidget):
        """Selects which settings.json the tabs edit: user (global),
        project, or project-local. Projects come from AgentPilot's
        ``projects`` table (rows with a ``working_dir``)."""

        SCOPES = (
            ('User (global)', 'user'),
            ('Project', 'project'),
            ('Project (local)', 'project_local'),
        )

        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent

            self.scope_combo = QComboBox()
            for label, scope in self.SCOPES:
                self.scope_combo.addItem(label, scope)
            self.scope_combo.currentIndexChanged.connect(self._on_changed)

            self.project_combo = QComboBox()
            self.project_combo.setMinimumWidth(220)
            self.project_combo.currentIndexChanged.connect(self._on_changed)
            self.project_combo.hide()

            self.path_lbl = QLabel('')
            self.path_lbl.setObjectName('claudePathLabel')

            layout = CHBoxLayout(self)
            layout.addWidget(QLabel('Scope:'))
            layout.addWidget(self.scope_combo)
            layout.addWidget(self.project_combo)
            layout.addWidget(self.path_lbl)
            layout.addStretch(1)

            self._refresh_projects()
            self._update_path_label()

        def _refresh_projects(self):
            rows = sql.get_results(
                "SELECT name, json_extract(config, '$.working_dir') "
                "FROM projects "
                "WHERE json_extract(config, '$.working_dir') IS NOT NULL "
                "ORDER BY name COLLATE NOCASE",
            )
            current = self.project_combo.currentData()
            self.project_combo.blockSignals(True)
            self.project_combo.clear()
            for name, working_dir in rows:
                self.project_combo.addItem(name, working_dir)
            if current is not None:
                idx = self.project_combo.findData(current)
                if idx >= 0:
                    self.project_combo.setCurrentIndex(idx)
            self.project_combo.blockSignals(False)

        def current_path(self):
            scope = self.scope_combo.currentData() or 'user'
            project_dir = self.project_combo.currentData()
            return settings_path(scope, project_dir)

        def _on_changed(self, _=None):
            scope = self.scope_combo.currentData() or 'user'
            if scope == 'user':
                self.project_combo.hide()
            else:
                self._refresh_projects()
                self.project_combo.show()
            self._update_path_label()
            self._reload_current_tab()

        def _update_path_label(self):
            self.path_lbl.setText(str(self.current_path()))

        def _reload_current_tab(self):
            tab = self.parent.content.currentWidget()
            if tab is not None and hasattr(tab, 'load'):
                tab.load()

    class Page_Defaults(ConfigJoined):
        """AgentPilot's own Claude settings, stored in the app config."""

        def __init__(self, parent):
            super().__init__(parent=parent, propagate_config=True)
            self.context = ClaudeContext(
                self, get_default_cwd, conf_namespace='claude.context')
            self.context.stretch = 1
            self.widgets = [self.Defaults_Fields(parent=self), self.context]

        class Defaults_Fields(ConfigFields):
            schema = [{
                'text': 'Default working dir', 'key': 'default_working_dir',
                'type': 'file_picker', 'mode': 'directory',
                'default': DEFAULT_CWD, 'stretch_x': True,
                'tooltip': 'Working dir of Claude Code chats outside a '
                           'project.',
            }]

            def __init__(self, parent):
                super().__init__(parent=parent, conf_namespace='claude',
                                 schema=self.schema)

            def update_config(self):
                super().update_config()
                self.parent.context.load()

    class Page_Usage(QScrollArea):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.propagate_config = False
            self.setWidgetResizable(True)
            self.setFrameShape(QFrame.NoFrame)
            body = QWidget()
            self.setWidget(body)
            self.layout = CVBoxLayout(body)
            self.layout.setSpacing(8)

            self.refresh_btn = QPushButton('Refresh')
            self.refresh_btn.clicked.connect(self.refresh)
            self.status_lbl = QLabel('')
            self.status_lbl.setWordWrap(True)
            row = CHBoxLayout()
            row.setSpacing(12)
            row.addWidget(self.status_lbl, 1)
            row.addWidget(self.refresh_btn)
            self.layout.addLayout(row)

            self.local_header = _section_label('Claude Code activity')
            self.layout.addWidget(self.local_header)
            self.tiles_layout = CHBoxLayout()
            self.tiles_layout.setSpacing(24)
            self.layout.addLayout(self.tiles_layout)

            self.layout.addWidget(QLabel(
                f"Daily tokens by model, last {CHART_DAYS} days"))
            self.legend_layout = CHBoxLayout()
            self.legend_layout.setSpacing(16)
            self.layout.addLayout(self.legend_layout)
            self.chart = UsageChart()
            self.layout.addWidget(self.chart)

            self.layout.addWidget(_section_label('By model'))
            self.models_table = self._make_table()
            self.layout.addWidget(self.models_table)
            self.layout.addWidget(_section_label('By project'))
            self.projects_table = self._make_table()
            self.layout.addWidget(self.projects_table)
            self.layout.addStretch(1)

        @staticmethod
        def _make_table():
            table = QTableWidget()
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionMode(QAbstractItemView.NoSelection)
            table.verticalHeader().hide()
            table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            return table

        def load(self):
            self.refresh()

        @qasync.asyncSlot()
        async def refresh(self):
            if not self.refresh_btn.isEnabled():
                return
            self.refresh_btn.setEnabled(False)
            self.status_lbl.setText('Loading…')
            try:
                # TEMP crash diagnosis: suspect off-thread scan disabled
                # self._show_local(await asyncio.to_thread(scan_local_usage))
                self.status_lbl.setText(
                    f"Updated {datetime.now().strftime('%H:%M:%S')}")
            finally:
                self.refresh_btn.setEnabled(True)

        def _show_local(self, data):
            models, projects = data['models'], data['projects']
            first_day = min(data['by_day'], default=None)
            self.local_header.setText(
                'Claude Code activity'
                + (f' (local logs since {first_day:%d %b %Y})'
                   if first_day else ''))

            clear_layout(self.tiles_layout)
            tiles = (
                ('Tokens', _fmt_tokens(
                    sum(m['total'] for m in models.values()))),
                ('Output tokens', _fmt_tokens(
                    sum(m['output'] for m in models.values()))),
                ('Responses', f"{sum(m['messages'] for m in models.values()):,}"),
                ('Sessions', f"{sum(len(p['sessions']) for p in projects.values()):,}"),
                ('Projects', f'{len(projects):,}'),
                ('Active days', f"{len(data['by_day']):,}"),
            )
            for name, value in tiles:
                tile = CVBoxLayout()
                tile.addWidget(_section_label(value))
                tile.addWidget(QLabel(name))
                self.tiles_layout.addLayout(tile)
            self.tiles_layout.addStretch(1)

            self._show_chart(data['by_day'], models)

            _fill_table(
                self.models_table,
                ['Model', 'Responses', 'Input', 'Output', 'Cache write',
                 'Cache read', 'Total'],
                [[name, f"{m['messages']:,}", _fmt_tokens(m['input']),
                  _fmt_tokens(m['output']), _fmt_tokens(m['cache_write']),
                  _fmt_tokens(m['cache_read']), _fmt_tokens(m['total'])]
                 for name, m in sorted(models.items(),
                                       key=lambda kv: -kv[1]['total'])],
            )
            _fill_table(
                self.projects_table,
                ['Project', 'Sessions', 'Responses', 'Tokens',
                 'Last active'],
                [[os.path.basename(cwd) or cwd, len(p['sessions']),
                  f"{p['messages']:,}", _fmt_tokens(p['tokens']),
                  f"{datetime.fromtimestamp(p['last']):%d %b %H:%M}"]
                 for cwd, p in sorted(projects.items(),
                                      key=lambda kv: -kv[1]['tokens'])],
            )

        def _show_chart(self, by_day, models):
            top = sorted(models, key=lambda m: -models[m]['total'])
            series = sorted(top[:len(SERIES_COLORS)])
            colors = dict(zip(series, SERIES_COLORS))
            if len(top) > len(series):
                colors['Other'] = OTHER_COLOR

            today = datetime.now().date()
            days = [today - timedelta(days=i)
                    for i in reversed(range(CHART_DAYS))]
            day_totals = [dict.fromkeys(colors, 0) for _ in days]
            for totals, day in zip(day_totals, days):
                for model, tokens in by_day.get(day, {}).items():
                    totals[model if model in series else 'Other'] += tokens
            tips = [
                f'{day:%a %d %b}: {_fmt_tokens(sum(t.values()))}\n'
                + '\n'.join(f'  {name}: {_fmt_tokens(val)}'
                            for name, val in t.items() if val)
                for day, t in zip(days, day_totals)]
            self.chart.set_data(days, colors, day_totals, tips)

            clear_layout(self.legend_layout)
            for name, color in colors.items():
                self.legend_layout.addWidget(QLabel(
                    f'<span style="color:{color}">■</span> {name}'))
            self.legend_layout.addStretch(1)

    class Page_ClaudeMd(FileTree):
        def __init__(self, parent):
            super().__init__(parent=parent, fixed_directory=True)
            self.propagate_config = False

        def load(self):
            bar = self.parent.scope_bar
            root, claude_md = claude_md_location(
                bar.scope_combo.currentData() or 'user',
                bar.project_combo.currentData(),
            )
            self.set_root_directory(root)
            super().load()
            if claude_md:
                self.navigate_to(claude_md)

    class Page_Memory(FileTree):
        def __init__(self, parent):
            super().__init__(parent=parent, fixed_directory=True)
            self.propagate_config = False

        def load(self):
            bar = self.parent.scope_bar
            memory_dir = auto_memory_dir(
                bar.scope_combo.currentData() or 'user',
                bar.project_combo.currentData(),
            )
            self.horizontal_splitter.setVisible(memory_dir is not None)
            if memory_dir:
                self.set_root_directory(memory_dir)
                super().load()

    class Page_Import(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.propagate_config = False

            self.layout = CVBoxLayout(self)
            self.import_btn = QPushButton('Import Claude Code chats')
            self.import_btn.clicked.connect(self._on_import_clicked)

            self.delete_btn = QPushButton('Delete imported chats')
            self.delete_btn.clicked.connect(self._on_delete_clicked)

            self.status_lbl = QLabel('')
            self.status_lbl.setWordWrap(True)

            row = CHBoxLayout()
            row.addWidget(self.import_btn)
            row.addWidget(self.delete_btn)
            row.addStretch(1)
            self.layout.addLayout(row)
            self.layout.addWidget(self.status_lbl)
            self.layout.addStretch(1)

            self._thread = None

        def _on_import_clicked(self):
            if self._thread and self._thread.isRunning():
                return
            self.import_btn.setEnabled(False)
            self.status_lbl.setText('Importing…')
            self._thread = _ImportThread(self)
            self._thread.finished_with.connect(self._on_import_done)
            self._thread.start()

        def _on_import_done(self, result, exc):
            self.import_btn.setEnabled(True)
            if exc is not None:
                self.status_lbl.setText(f'Import failed: {exc}')
                display_message(str(exc), 'Import failed', icon='Critical')
                return
            msg = (
                f"{result['new_chats']} new chat(s), "
                f"{result['updated_chats']} updated with "
                f"{result['new_messages']} new message(s) across "
                f"{result['projects']} project(s). "
                f"{result['unchanged']} already up-to-date."
            )
            if result.get('errors'):
                msg += (f" {result['errors']} file(s) had no cwd and "
                        "were skipped.")
            self.status_lbl.setText(msg)
            display_message(msg, 'Import complete')

        def _on_delete_clicked(self):
            if self._thread and self._thread.isRunning():
                return
            retval = display_message_box(
                icon=QMessageBox.Warning,
                title='Delete imported chats',
                text='Delete every chat and message imported from '
                     'Claude Code? This cannot be undone.',
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return
            try:
                result = delete_imported_sessions()
            except Exception as exc:
                self.status_lbl.setText(f'Delete failed: {exc}')
                display_message(str(exc), 'Delete failed', icon='Critical')
                return
            msg = (f"Deleted {result['chats']} chat(s) and "
                   f"{result['messages']} message(s).")
            self.status_lbl.setText(msg)
            display_message(msg, 'Delete complete')
