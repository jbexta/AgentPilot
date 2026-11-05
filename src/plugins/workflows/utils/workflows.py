import asyncio
import json
from typing import Any, Dict

from jinja2 import TemplateSyntaxError, meta
from PySide6.QtWidgets import QMessageBox

from gui import system
from utils import sql
from utils.helpers import display_message, flatten_list


def get_avatar_paths_from_config(config, merge_multiple=False) -> Any:
    member_type = config.get('_TYPE', 'agent')
    if member_type == 'workflow':
        if 'avatar_path' in config:
            return config['avatar_path']

        paths = []
        members = config.get('members', [])
        for member_data in members:
            member_config = member_data.get('config', {})
            member_type = member_config.get('_TYPE', 'agent')
            if member_type == 'user':
                continue
            paths.append(get_avatar_paths_from_config(member_config))
        return paths if paths else ':/resources/icon-user.png'
        # return paths # if not merge_multiple else '//##//##//'.join(flatten_list(paths))

    member_class = system.manager.modules.get_module_class('Members', module_name=member_type)
    if not member_class:
        display_message(
            message=f"Member module '{member_type}' not found.",
            icon=QMessageBox.Warning,
        )
        return ':/resources/icon-agent-solid.png'  # todo error icon

    avatar_key = getattr(member_class, 'avatar_key', None)
    default_avatar = getattr(member_class, 'default_avatar', ':/resources/icon-agent-solid.png')
    if avatar_key:
        avatar_path = config.get(avatar_key, default_avatar)
        return avatar_path
    else:
        return default_avatar


def get_member_name_from_config(config, incl_types=('agent', 'workflow')) -> str:
    member_type = config.get('_TYPE', 'agent')
    if member_type == 'workflow':
        names = []
        members = config.get('members', [])
        for member_data in members:
            member_config = member_data.get('config', {})
            member_type = member_config.get('_TYPE', 'agent')
            if member_type == 'user':
                continue
            names.append(get_member_name_from_config(member_config))
        return ', '.join(flatten_list(names))
        # return paths  # if not merge_multiple else '//##//##//'.join(flatten_list(paths))

    member_class = system.manager.modules.get_module_class('Members', module_name=member_type)
    if not member_class:
        display_message(
            message=f"Member module '{member_type}' not found.",
            icon=QMessageBox.Warning,
        )
        return 'Invalid member'

    name_key = getattr(member_class, 'name_key', None)
    default_name = getattr(member_class, 'default_name', 'Assistant')
    if name_key:
        name = config.get(name_key, default_name)
        return name
    else:
        return default_name


def resolve_linked_config(linked_id, visited=None):
    """Fetch config from DB for a linked_id like 'entities.{uuid}'.

    Recursively resolves nested linked_ids in the config.
    Uses visited set to detect circular references.

    Parameters
    ----------
    linked_id : str
        Format: 'table.uuid'
    visited : set, optional
        Set of already-visited linked_ids for cycle detection.

    Returns
    -------
    dict or None
        Resolved config, or None if entity not found.
    """
    if not linked_id:
        return None

    if visited is None:
        visited = set()

    if linked_id in visited:
        return None

    visited.add(linked_id)

    parts = linked_id.split('.', 1)
    if len(parts) != 2:
        return None

    table, entity_uuid = parts

    config_json = sql.get_scalar(
        f"SELECT config FROM `{table}` WHERE uuid = ?",
        (entity_uuid,)
    )
    if config_json is None:
        return None

    config = json.loads(config_json) if isinstance(config_json, str) else config_json

    # Recursively resolve nested linked_ids in members
    members = config.get('members', [])
    for member in members:
        nested_linked_id = member.get('linked_id')
        if nested_linked_id:
            nested_config = resolve_linked_config(nested_linked_id, visited=set(visited))
            if nested_config is not None:
                member['config'] = nested_config

    return config


def save_linked_config(linked_id, config):
    """Write config back to the source entity.

    Parameters
    ----------
    linked_id : str
        Format: 'table.uuid'
    config : dict
        Config to save.
    """
    if not linked_id:
        return

    parts = linked_id.split('.', 1)
    if len(parts) != 2:
        return

    table, entity_uuid = parts
    config_to_save = {k: v for k, v in config.items() if k != 'linked_id'}
    sql.execute(
        f"UPDATE `{table}` SET config = ? WHERE uuid = ?",
        (json.dumps(config_to_save), entity_uuid)
    )

    # Recursively save nested linked members
    for member in config_to_save.get('members', []):
        nested_linked_id = member.get('linked_id')
        if nested_linked_id:
            nested_config = member.get('config', {})
            save_linked_config(nested_linked_id, nested_config)


def has_circular_link(linked_id, existing_chain=None):
    """Check if linking to linked_id would create a cycle.

    Parameters
    ----------
    linked_id : str
        The linked_id to check.
    existing_chain : set, optional
        Set of linked_ids already in the chain.

    Returns
    -------
    bool
        True if a cycle would be created.
    """
    if not linked_id:
        return False

    if existing_chain is None:
        existing_chain = set()

    if linked_id in existing_chain:
        return True

    existing_chain.add(linked_id)

    parts = linked_id.split('.', 1)
    if len(parts) != 2:
        return False

    table, entity_uuid = parts
    config_json = sql.get_scalar(
        f"SELECT config FROM `{table}` WHERE uuid = ?",
        (entity_uuid,)
    )
    if config_json is None:
        return False

    config = json.loads(config_json) if isinstance(config_json, str) else config_json

    members = config.get('members', [])
    for member in members:
        nested_linked_id = member.get('linked_id')
        if nested_linked_id:
            if has_circular_link(nested_linked_id, existing_chain=set(existing_chain)):
                return True

    return False


EXPENSIVE_MEMBER_TYPES = (
    'user', 'agent', 'live_agent', 'claude_code', 'contact',
    'prompt', 'audio', 'image', 'video', 'voice',
)


def is_instant_runnable(config, seen=None):
    """Whether a workflow or member config is cheap to rerun, including
    the blocks its text members reference."""
    member_type = config.get('_TYPE', 'agent')
    if member_type == 'workflow' or 'members' in config:
        return all(is_instant_runnable(m.get('config', {}), seen)
                   for m in config.get('members', []))
    if member_type == 'text':
        return bool(blocks_instant_runnable(config.get('data', ''), seen))
    return member_type not in EXPENSIVE_MEMBER_TYPES


def blocks_instant_runnable(template, seen=None):
    """Whether all blocks a jinja *template* references, transitively, are
    instant runnable, or None if it doesn't parse."""
    blocks = system.manager.blocks
    try:
        ast = blocks.jinja_env.parse(template)
    except TemplateSyntaxError:
        return None
    seen = set() if seen is None else seen
    names = meta.find_undeclared_variables(ast) & blocks.keys() - seen
    seen |= names
    return all(is_instant_runnable(blocks[name], seen) for name in names)


def get_bubble_display_state(config):
    """The parts of a workflow config that its chat bubbles are drawn from."""
    member_keys = (
        '_TYPE', 'name', 'avatar_path',
        'group.hide_bubbles', 'chat.display_markdown',
    )
    members = []
    for member in config.get('members', []):
        member_config = member.get('config', {})
        state = [member_config.get(key) for key in member_keys]
        if member_config.get('_TYPE') == 'workflow':
            state.append(get_bubble_display_state(member_config))
        members.append((member['id'], state))
    options = [
        config.get(section, {}).get(key)
        for section in ('options', 'config')
        for key in ('show_hidden_bubbles', 'show_nested_bubbles')
    ]
    return members, options


def clear_context_messages(context_id):
    """Delete a context's messages and its child contexts."""
    sql.execute("""
        WITH RECURSIVE delete_contexts(id) AS (
            SELECT id FROM contexts WHERE id = ?
            UNION ALL
            SELECT contexts.id FROM contexts
            JOIN delete_contexts ON contexts.parent_id = delete_contexts.id
        )
        DELETE FROM contexts_messages WHERE context_id IN delete_contexts;
    """, (context_id,))
    sql.execute("""
    DELETE FROM contexts_messages WHERE context_id = ?""",
                (context_id,))
    sql.execute("""
        WITH RECURSIVE delete_contexts(id) AS (
            SELECT id FROM contexts WHERE id = ?
            UNION ALL
            SELECT contexts.id FROM contexts
            JOIN delete_contexts ON contexts.parent_id = delete_contexts.id
        )
        DELETE FROM contexts WHERE id IN delete_contexts AND id != ?;
    """, (context_id, context_id,))


def get_entity_workflow_config(entity_val, link=True):
    """Build a workflow config from an entity field value.

    Parameters
    ----------
    entity_val : str
        Stored value in ``name:table:uuid`` format.
    link : bool
        Whether the config is linked to the entity, so edits save back
        to it.

    Returns
    -------
    dict
        A workflow config, or empty dict if the value is invalid.
    """
    if not entity_val:
        return {}
    parts = entity_val.rsplit(':', 2)
    if len(parts) != 3:
        return {}
    _, table, uuid = parts
    raw = sql.get_scalar(
        f"SELECT config FROM `{table}` WHERE uuid = ?", (uuid,),
    )
    if not raw:
        return {}
    config = json.loads(raw) if isinstance(raw, str) else raw
    if not link:
        return merge_config_into_workflow_config(config)
    return merge_config_into_workflow_config(
        config, entity_id=uuid, entity_table=table,
    )


def merge_config_into_workflow_config(config, entity_id=None, entity_table=None) -> Dict[str, Any]:
    """Wrap a non-workflow config into a workflow structure.

    Parameters
    ----------
    entity_id : str or None
        The *uuid* of the source entity (not the integer id).
    entity_table : str or None
        Table name, e.g. 'entities', 'blocks', 'tools'.
    """
    linked_id = f'{entity_table}.{entity_id}' if entity_id is not None else None

    member_type = config.get('_TYPE', 'agent')
    if member_type == 'workflow':
        if linked_id:
            config['linked_id'] = linked_id
        return config
    else:
        name = config.pop('name', 'Workflow')

    if member_type == 'agent':  # !wfdiff! #
        members = [
            {'id': '1', 'linked_id': None, 'loc_x': 20, 'loc_y': 64, 'config': {"_TYPE": "user", "name": "You"}},
            {'id': '2', 'linked_id': linked_id, 'loc_x': 100, 'loc_y': 80, 'config': config | {"name": "Agent"}}
        ]
    else:
        pretty_name = member_type.replace('_', ' ').title()
        members = [{'id': '1', 'linked_id': linked_id, 'loc_x': 100, 'loc_y': 80, 'config': config | {"name": pretty_name}}]

    config_json = {
        '_TYPE': 'workflow',
        'name': name,
        'description': config.get('description', ''),
        'avatar_path': config.get('avatar_path', None),
        'members': members,
        'inputs': [],
    }
    return config_json


def merge_multiple_into_workflow_config(members, inputs) -> Dict[str, Any]:
    """Merge multiple configs into a single workflow config."""
    if not members:
        return {}
    if len(members) == 1 and '_TYPE' in members[0] and members[0]['_TYPE'] == 'workflow':
        return members[0]

    merged_config = {
        '_TYPE': 'workflow',
        'members': [
            {'id': str(i + 1), 'linked_id': None, 'loc_x': 100 + qpoint.x(), 'loc_y': 80 + qpoint.y(), 'config': config}
            for i, (qpoint, config) in enumerate(members)
        ],
        'inputs': [
            {
                'source_member_id': str(source_member_index + 1),
                'target_member_id': str(target_member_index + 1),
                'config': input_config
            }
            for source_member_index, target_member_index, input_config in inputs
        ]
    }

    return merged_config


async def receive_workflow(
    config: Dict[str, Any] = None,
    kind: str = 'BLOCK',
    params: Dict[str, Any] = None,
    tool_uuid: str = None,
    chat_title: str = '',
    main=None,
    workflow=None,
):
    if workflow is None:
        from plugins.workflows.members.workflow import Workflow
        wf_config = merge_config_into_workflow_config(config)
        workflow = Workflow(main=main, config=wf_config, kind=kind, params=params, tool_uuid=tool_uuid, chat_title=chat_title)

    try:
        async for key, chunk in workflow.run():
            yield key, chunk
    except StopIteration:  # !nestmember! #
        raise Exception("Pausing nested workflows isn't implemented yet")


async def compute_workflow_async(  # todo rename, clean
    config: Dict[str, Any] = None,
    kind: str = 'BLOCK',
    params: Dict[str, Any] = None,
    tool_uuid: str = None,
    chat_title: str = '',
    main=None,
    workflow=None,
):
    response = ''
    async for key, chunk in receive_workflow(config=config, kind=kind, params=params, tool_uuid=tool_uuid, chat_title=chat_title, main=main, workflow=workflow):
        response += chunk
    return response


def compute_workflow(  # todo rename
    config: Dict[str, Any],
    kind: str = 'BLOCK',
    params: Dict[str, Any] = None,
    tool_uuid: str = None,
    chat_title: str = '',
    main=None,
    workflow=None,
):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        from gui.main import loop as main_loop
        if main_loop is not None and main_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                compute_workflow_async(config=config, kind=kind, params=params, tool_uuid=tool_uuid, chat_title=chat_title, main=main, workflow=workflow),
                main_loop,
            )
            return future.result()
    return asyncio.run(compute_workflow_async(config=config, kind=kind, params=params, tool_uuid=tool_uuid, chat_title=chat_title, main=main, workflow=workflow))
