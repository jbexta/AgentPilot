import json
import os
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_json_tree import ConfigJsonTree
from gui.widgets.config_tabs import ConfigTabs
from utils.helpers import (
    block_signals,
    convert_to_safe_case,
    display_message,
    set_module_type,
)


def settings_path(scope, project_dir=None):
    """Resolve a Claude Code settings.json path for ``scope``.

    Scopes: ``user`` (``~/.claude/settings.json``), ``project``
    (``<dir>/.claude/settings.json``) and ``project_local``
    (``<dir>/.claude/settings.local.json``).
    """
    if scope == 'user' or not project_dir:
        return Path.home() / '.claude' / 'settings.json'
    base = Path(project_dir) / '.claude'
    return base / ('settings.local.json' if scope == 'project_local'
                   else 'settings.json')


def resolve_settings_path(widget):
    """Walk up the widget's parent chain for a ``cc_settings_path``
    provider; fall back to the user scope."""
    w = widget
    while w is not None:
        getter = getattr(w, 'cc_settings_path', None)
        if callable(getter):
            return getter()
        w = getattr(w, 'parent', None)
    return settings_path('user')


def load_file(path):
    """Return the full settings.json dict, or {} if missing/invalid."""
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_file(path, data):
    """Atomically write the full settings.json dict."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent),
        prefix='.settings.', suffix='.tmp',
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(payload)
            fh.write('\n')
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _dig(data, path):
    """Walk ``path`` (tuple of keys) into ``data``; return None if absent."""
    cur = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _set_nested(data, path, value):
    """Set ``value`` at ``path`` in ``data``, creating dicts as needed."""
    cur = data
    for key in path[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[path[-1]] = value


def _prune_empty(data, path):
    """Remove ``path`` from ``data`` and clean up empty parent dicts."""
    stack = []
    cur = data
    for key in path[:-1]:
        if not isinstance(cur, dict) or key not in cur:
            return
        stack.append((cur, key))
        cur = cur[key]
    if isinstance(cur, dict):
        cur.pop(path[-1], None)
    for parent, key in reversed(stack):
        if isinstance(parent.get(key), dict) and not parent[key]:
            parent.pop(key, None)


class _FileBackedFields(ConfigFields):
    """ConfigFields backed by a Claude Code settings.json file.

    The file is resolved per-call via :func:`resolve_settings_path`, so
    an ancestor widget can switch scope (user / project / project-local)
    by providing ``cc_settings_path``. Subclasses declare
    ``FIELD_PATHS`` mapping each schema field's safe-case key to a
    nested path tuple inside settings.json.
    """

    FIELD_PATHS = {}

    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.propagate_config = False

    def load_config(self, json_config=None):
        data = load_file(resolve_settings_path(self))
        cfg = {}
        for safe_key, path in self.FIELD_PATHS.items():
            val = _dig(data, path)
            if val is not None:
                cfg[safe_key] = val
        self.config = cfg

    def load(self):
        # Re-read the file on every load so external edits surface.
        self.load_config()
        super().load()

    def get_config(self):
        return {}

    def update_config(self):
        path = resolve_settings_path(self)
        data = load_file(path)
        for param_dict in self.schema:
            if param_dict.get('type', 'text') == 'stretch':
                continue
            safe_key = convert_to_safe_case(
                param_dict.get('key', param_dict['text'].lower())
            )
            path = self.FIELD_PATHS.get(safe_key)
            if not path:
                continue

            toggle = getattr(self, f'{safe_key}_tgl', None)
            if toggle is not None and not toggle.isChecked():
                _prune_empty(data, path)
                continue

            widget = getattr(self, f'{safe_key}_wgt', None)
            if not widget or not hasattr(widget, 'get_value'):
                continue
            value = widget.get_value()

            if isinstance(value, str) and value == '':
                _prune_empty(data, path)
            else:
                _set_nested(data, path, value)

        try:
            save_file(path, data)
        except OSError as exc:
            display_message(
                f'Failed to write {path}: {exc}',
                title='Save failed', icon=QMessageBox.Warning,
            )
        self.refresh_visibility()


class _FileBackedJsonTree(ConfigJsonTree):
    """ConfigJsonTree backed by a Claude Code settings.json file.

    The file is resolved per-call via :func:`resolve_settings_path`.
    Subclasses implement :meth:`rows_from_file` and
    :meth:`write_rows_to_file`.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.propagate_config = False

    def load_config(self, json_config=None):
        self.config = {}

    def get_config(self):
        return {}

    def load(self):
        with block_signals(self):
            self.tree.clear()
            data = load_file(resolve_settings_path(self))
            for row in self.rows_from_file(data):
                self.add_new_entry(row)
            self.set_height()

    def update_config(self):
        rows = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            row = {}
            for j, col in enumerate(self.schema):
                key = convert_to_safe_case(
                    col.get('key', col['text'].lower())
                )
                cell = self.tree.itemWidget(item, j)
                if cell is not None and hasattr(cell, 'get_value'):
                    row[key] = cell.get_value()
                else:
                    row[key] = item.text(j)
            rows.append(row)

        path = resolve_settings_path(self)
        data = load_file(path)
        self.write_rows_to_file(data, rows)
        try:
            save_file(path, data)
        except OSError as exc:
            display_message(
                f'Failed to write {path}: {exc}',
                title='Save failed', icon=QMessageBox.Warning,
            )
        self.refresh_visibility()

    # Subclasses override:
    def rows_from_file(self, data):
        return []

    def write_rows_to_file(self, data, rows):
        pass


# ---------- General ----------

class CCSettings_General(_FileBackedFields):
    FIELD_PATHS = {
        'model': ('model',),
        'theme': ('theme',),
        'autoupdates': ('autoUpdates',),
        'includecoauthoredby': ('includeCoAuthoredBy',),
        'cleanupperioddays': ('cleanupPeriodDays',),
        'alwaysthinkingenabled': ('alwaysThinkingEnabled',),
        'effortlevel': ('effortLevel',),
        'outputstyle': ('outputStyle',),
    }

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.label_width = 200
        self.schema = [
            {
                'text': 'Model',
                'key': 'model',
                'type': str,
                'default': '',
                'width': 260,
                'tooltip': "e.g. 'claude-opus-4-7', 'sonnet', or a "
                           "full model id. Leave blank for default.",
            },
            {
                'text': 'Theme',
                'key': 'theme',
                'type': ('dark', 'light', 'dark-daltonized',
                         'light-daltonized', 'dark-ansi', 'light-ansi'),
                'default': 'dark',
                'width': 180,
            },
            {
                'text': 'Effort level',
                'key': 'effortLevel',
                'type': ('low', 'medium', 'high'),
                'default': 'medium',
                'width': 120,
            },
            {
                'text': 'Output style',
                'key': 'outputStyle',
                'type': str,
                'default': '',
                'width': 180,
            },
            {
                'text': 'Auto-updates',
                'key': 'autoUpdates',
                'type': bool,
                'default': True,
            },
            {
                'text': 'Include Co-Authored-By',
                'key': 'includeCoAuthoredBy',
                'type': bool,
                'default': True,
            },
            {
                'text': 'Always thinking enabled',
                'key': 'alwaysThinkingEnabled',
                'type': bool,
                'default': False,
            },
            {
                'text': 'Cleanup period (days)',
                'key': 'cleanupPeriodDays',
                'type': int,
                'minimum': 0,
                'maximum': 3650,
                'default': 30,
                'has_toggle': True,
                'width': 80,
            },
        ]


# ---------- Permissions ----------

class CCSettings_Permissions(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent, layout_type='vertical')
        self.propagate_config = False
        self.widgets = [
            self.Scalars(parent=self),
            self.Lists(parent=self),
        ]

    class Scalars(_FileBackedFields):
        FIELD_PATHS = {
            'defaultmode': ('permissions', 'defaultMode'),
            'disablebypasspermissionsmode': (
                'permissions', 'disableBypassPermissionsMode'),
        }

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.label_width = 200
            self.schema = [
                {
                    'text': 'Default mode',
                    'key': 'defaultMode',
                    'type': ('default', 'acceptEdits', 'plan',
                             'bypassPermissions'),
                    'default': 'default',
                    'width': 180,
                },
                {
                    'text': 'Disable bypass mode',
                    'key': 'disableBypassPermissionsMode',
                    'type': ('', 'disable'),
                    'default': '',
                    'width': 120,
                },
            ]

    class Lists(_FileBackedJsonTree):
        _KIND_TO_FILE_KEY = {
            'allow': 'allow',
            'deny': 'deny',
            'ask': 'ask',
            'additionalDirectories': 'additionalDirectories',
        }

        def __init__(self, parent):
            super().__init__(
                parent=parent,
                tree_header_hidden=False,
                schema=[
                    {
                        'text': 'Kind',
                        'key': 'kind',
                        'type': ('allow', 'deny', 'ask',
                                 'additionalDirectories'),
                        'default': 'allow',
                        'width': 180,
                    },
                    {
                        'text': 'Pattern / path',
                        'key': 'pattern',
                        'type': str,
                        'stretch': True,
                        'default': '',
                    },
                ],
            )

        def rows_from_file(self, data):
            perms = data.get('permissions') or {}
            rows = []
            for kind in self._KIND_TO_FILE_KEY:
                for pat in perms.get(kind) or []:
                    rows.append({'kind': kind, 'pattern': pat})
            return rows

        def write_rows_to_file(self, data, rows):
            buckets = {k: [] for k in self._KIND_TO_FILE_KEY}
            for row in rows:
                kind = row.get('kind') or 'allow'
                pat = (row.get('pattern') or '').strip()
                if not pat or kind not in buckets:
                    continue
                buckets[kind].append(pat)

            perms = data.get('permissions')
            if not isinstance(perms, dict):
                perms = {}
            for kind, items in buckets.items():
                if items:
                    perms[kind] = items
                else:
                    perms.pop(kind, None)
            if perms:
                data['permissions'] = perms
            else:
                data.pop('permissions', None)


# ---------- Hooks ----------

_HOOK_EVENTS = (
    'PreToolUse', 'PostToolUse', 'UserPromptSubmit',
    'Notification', 'Stop', 'SubagentStop',
    'SessionStart', 'SessionEnd', 'PreCompact',
)


class CCSettings_Hooks(_FileBackedJsonTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            tree_header_hidden=False,
            schema=[
                {
                    'text': 'Event',
                    'key': 'event',
                    'type': _HOOK_EVENTS,
                    'default': 'PreToolUse',
                    'width': 160,
                },
                {
                    'text': 'Matcher',
                    'key': 'matcher',
                    'type': str,
                    'default': '',
                    'width': 160,
                },
                {
                    'text': 'Command',
                    'key': 'command',
                    'type': str,
                    'default': '',
                    'stretch': True,
                },
            ],
        )

    def rows_from_file(self, data):
        hooks = data.get('hooks') or {}
        rows = []
        for event, matcher_entries in hooks.items():
            if not isinstance(matcher_entries, list):
                continue
            for entry in matcher_entries:
                if not isinstance(entry, dict):
                    continue
                matcher = entry.get('matcher', '')
                for hook in entry.get('hooks') or []:
                    if not isinstance(hook, dict):
                        continue
                    if hook.get('type') != 'command':
                        continue
                    rows.append({
                        'event': event,
                        'matcher': matcher,
                        'command': hook.get('command', ''),
                    })
        return rows

    def write_rows_to_file(self, data, rows):
        grouped = {}
        for row in rows:
            event = row.get('event') or 'PreToolUse'
            matcher = row.get('matcher') or ''
            command = (row.get('command') or '').strip()
            if not command:
                continue
            grouped.setdefault(event, {}).setdefault(matcher, []).append(
                {'type': 'command', 'command': command}
            )

        if not grouped:
            data.pop('hooks', None)
            return

        hooks_obj = {}
        for event, by_matcher in grouped.items():
            entries = []
            for matcher, hook_list in by_matcher.items():
                entry = {'hooks': hook_list}
                if matcher:
                    entry['matcher'] = matcher
                entries.append(entry)
            hooks_obj[event] = entries
        data['hooks'] = hooks_obj


# ---------- MCP & Advanced ----------

class CCSettings_Advanced(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent, layout_type='vertical')
        self.propagate_config = False
        self.widgets = [
            self.Scalars(parent=self),
            self.McpServers(parent=self),
        ]

    class Scalars(_FileBackedFields):
        FIELD_PATHS = {
            'apikeyhelper': ('apiKeyHelper',),
            'enableallprojectmcpservers': (
                'enableAllProjectMcpServers',),
            'forceloginmethod': ('forceLoginMethod',),
            'statusline_type': ('statusLine', 'type'),
            'statusline_command': ('statusLine', 'command'),
            'statusline_padding': ('statusLine', 'padding'),
        }

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.label_width = 220
            self.schema = [
                {
                    'text': 'API key helper',
                    'key': 'apiKeyHelper',
                    'type': str,
                    'default': '',
                    'width': 320,
                    'tooltip': 'Path to a script that prints an API key.',
                },
                {
                    'text': 'Force login method',
                    'key': 'forceLoginMethod',
                    'type': ('', 'claudeai', 'console'),
                    'default': '',
                    'width': 180,
                },
                {
                    'text': 'Enable all project MCP servers',
                    'key': 'enableAllProjectMcpServers',
                    'type': bool,
                    'default': False,
                },
                {
                    'text': 'Status line type',
                    'key': 'statusLine_type',
                    'type': ('', 'command'),
                    'default': '',
                    'width': 140,
                },
                {
                    'text': 'Status line command',
                    'key': 'statusLine_command',
                    'type': str,
                    'default': '',
                    'width': 320,
                },
                {
                    'text': 'Status line padding',
                    'key': 'statusLine_padding',
                    'type': int,
                    'minimum': 0,
                    'maximum': 20,
                    'default': 0,
                    'has_toggle': True,
                    'width': 80,
                },
            ]

    class McpServers(_FileBackedJsonTree):
        _KIND_TO_FILE_KEY = {
            'enabled': 'enabledMcpjsonServers',
            'disabled': 'disabledMcpjsonServers',
        }

        def __init__(self, parent):
            super().__init__(
                parent=parent,
                tree_header_hidden=False,
                schema=[
                    {
                        'text': 'State',
                        'key': 'state',
                        'type': ('enabled', 'disabled'),
                        'default': 'enabled',
                        'width': 140,
                    },
                    {
                        'text': 'MCP server name',
                        'key': 'name',
                        'type': str,
                        'default': '',
                        'stretch': True,
                    },
                ],
            )

        def rows_from_file(self, data):
            rows = []
            for state, file_key in self._KIND_TO_FILE_KEY.items():
                for name in data.get(file_key) or []:
                    rows.append({'state': state, 'name': name})
            return rows

        def write_rows_to_file(self, data, rows):
            buckets = {k: [] for k in self._KIND_TO_FILE_KEY}
            for row in rows:
                state = row.get('state') or 'enabled'
                name = (row.get('name') or '').strip()
                if not name or state not in buckets:
                    continue
                buckets[state].append(name)
            for state, file_key in self._KIND_TO_FILE_KEY.items():
                if buckets[state]:
                    data[file_key] = buckets[state]
                else:
                    data.pop(file_key, None)


@set_module_type('Widgets')
class CC_User_Settings(ConfigTabs):
    """Claude Code settings.json editor, bundled as one widget.

    Marked class for the module loader; the Claude settings page
    composes the individual tab widgets directly instead.
    """

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.pages = {
            'General': CCSettings_General(parent=self),
            'Permissions': CCSettings_Permissions(parent=self),
            'Hooks': CCSettings_Hooks(parent=self),
            'MCP & Advanced': CCSettings_Advanced(parent=self),
        }