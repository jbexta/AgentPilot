
"""Block Manager Module.

This module provides the BlockManager class for managing reusable content blocks within the Agent Pilot system.
Blocks are modular components that can contain text, prompts, code, or entire workflows, allowing for
consistent reuse across different agents and workflows. The BlockManager handles block creation, execution,
and parameter substitution with placeholder resolution.

Key Features:
- Block creation, modification, and deletion with workflow support
- Recursive placeholder resolution and parameter substitution
- Asynchronous block execution and streaming responses
- Template-based content generation with nested block references
- Caching mechanisms for improved performance
- Integration with the workflow execution system

Blocks support various types including text blocks, prompt blocks, and complex workflow blocks,
making them fundamental building blocks for creating sophisticated AI interactions and automations.
"""  # unchecked

import asyncio
import re
from jinja2 import DebugUndefined, Environment, BaseLoader
from PySide6.QtWidgets import QMessageBox
from utils.helpers import BaseManager
from utils.helpers import display_message, receive_workflow


class BlockManager(BaseManager):
    def __init__(self, system):
        super().__init__(
            system,
            table_name='blocks',
            folder_key='blocks',
            load_columns=['name', 'config'],
            default_fields={
                'config': {'_TYPE': 'text'}
            },
            add_item_options={'title': 'Add Block', 'prompt': 'Enter a name for the block:'},
            del_item_options={'title': 'Delete Block', 'prompt': 'Are you sure you want to delete this block?'},
            config_is_workflow=True,
        )
        self.jinja_env = Environment(
            loader=BaseLoader(),
            undefined=DebugUndefined,
            enable_async=True
        )
        pass

    async def receive_block(self, name, params=None):
        print('receive block', name)
        self.load()  # todo temp, find out why model_params getting reset
        name = name.replace('-', '_').replace(' ', '_')
        wf_config = self[name]
        async for key, chunk in receive_workflow(wf_config, kind='BLOCK', params=params, chat_title=name, main=self.system._main_gui):
            yield key, chunk

    async def compute_block_async(self, name, params=None):
        response = ''
        async for _, chunk in self.receive_block(name, params=params):
            response += chunk
        return response

    def compute_block(self, name, params=None):
        return asyncio.run(self.compute_block_async(name, params))

    async def format_string(self, content, ref_workflow=None, additional_blocks=None):
        # Member outputs and Workflow params
        member_outputs = {}
        workflow_params = {}
        if ref_workflow:
            members = ref_workflow.members
            member_names = {m_id: member.config.get('name', 'Assistant') for m_id, member in members.items()}
            member_placeholders = {
                m_id: member.config.get('group.output_placeholder', f'{member_names[m_id]}_{str(m_id)}') if member.config.get('_TYPE') != 'workflow' else member.config.get('config', {}).get('group.output_placeholder', f'{member_names[m_id]}_{str(m_id)}')
                for m_id, member in members.items()}  # todo !
            member_last_outputs = {member.member_id: member.last_output for k, member in ref_workflow.members.items()
                                   if member.last_output != ''}

            member_outputs = {member_placeholders[k].lower(): v for k, v in member_last_outputs.items() if v is not None}
            workflow_params = ref_workflow.params.copy()

        all_params = {**member_outputs, **workflow_params}
        if additional_blocks:
            all_params.update(additional_blocks)

        def merge_headers(content, header_prefix):
            if not header_prefix:
                return content

            lines = content.split('\n')
            
            # Find the level of the first header
            first_header_level = 0
            for line in lines:
                match = re.match(r'^(#+)\s', line)
                if match:
                    first_header_level = len(match.group(1))
                    break
            
            # If no header found, prepend to first line (fallback behavior)
            if first_header_level == 0:
                if lines:
                    lines[0] = f"{header_prefix} {lines[0]}"
                return '\n'.join(lines)

            # Calculate shift
            target_level = len(header_prefix)
            shift = target_level - first_header_level
            
            new_lines = []
            for line in lines:
                match = re.match(r'^(#+)(\s.*)$', line)
                if match:
                    current_level = len(match.group(1))
                    new_level = max(1, current_level + shift)
                    new_lines.append(f"{'#' * new_level}{match.group(2)}")
                else:
                    new_lines.append(line)
                    
            return '\n'.join(new_lines)

        # Global blocks
        class BlockWrapper:
            def __init__(self, manager, block_name):
                self.manager = manager
                self.block_name = block_name
                self._cache = None

            async def _compute(self, **kwargs):
                if self._cache is None:
                    self._cache = await self.manager.compute_block_async(
                        self.block_name,
                        params=kwargs if kwargs else None
                    )
                return self._cache

            def __call__(self, **kwargs):
                header_prefix = kwargs.pop('header_prefix', None)
                # Unwrap ContentWrapper objects to plain strings
                for k, v in kwargs.items():
                    if isinstance(v, ContentWrapper):
                        kwargs[k] = str(v)

                async def wrapper():
                    content = await self._compute(**kwargs)
                    return merge_headers(content, header_prefix)

                return wrapper()

            def __await__(self):
                return self._compute().__await__()

        class ContentWrapper:
            def __init__(self, content):
                self.content = content

            def __call__(self, header_prefix=None):
                return merge_headers(self.content, header_prefix)

            def __str__(self):
                return self.content
            
            def __repr__(self):
                return self.content

        for block_name in self.keys():
            if block_name not in all_params:
                all_params[block_name] = BlockWrapper(self, block_name)
        
        # Wrap string params to support header merging
        for key, value in all_params.items():
            if isinstance(value, str):
                all_params[key] = ContentWrapper(value)

        # System object
        all_params['system'] = self.system

        # Pre-process: convert positional args to keyword args
        # {{ block(artist, song_desc) }} -> {{ block(artist=artist, song_desc=song_desc) }}
        def _positional_to_kwargs(match):
            args_str = match.group(1)
            parts = [p.strip() for p in args_str.split(',')]
            new_parts = []
            for part in parts:
                # If it's a bare identifier (no =), convert to kwarg
                if '=' not in part and re.match(r'^[a-zA-Z_]\w*$', part):
                    new_parts.append(f'{part}={part}')
                else:
                    new_parts.append(part)
            return '(' + ', '.join(new_parts) + ')'

        block_names = list(set(list(self.keys()) + list(all_params.keys())))

        for block_name in block_names:
            if not isinstance(block_name, str): continue

            # Convert positional args to kwargs for this block
            # Matches {{ block_name(args...) }} and replaces bare idents
            pos_pattern = (
                r'\{\{\s*' + re.escape(block_name)
                + r'\(([^)]+)\)\s*\}\}'
            )
            def _replace_positional(m, bn=block_name):
                full = m.group(0)
                args_str = m.group(1)
                new_args = _positional_to_kwargs(
                    re.match(r'\(([^)]+)\)', '(' + args_str + ')')
                )
                return '{{ ' + bn + new_args + ' }}'

            content = re.sub(pos_pattern, _replace_positional, content)

            # Handle headers: ## {{ block }} -> {{ block(header_prefix='##') }}
            header_pattern = r'(#{1,6})\s*\{\{\s*' + re.escape(block_name) + r'(?:\(\))?\s*\}\}'
            content = re.sub(header_pattern, r"{{ " + block_name + r"(header_prefix='\1') }}", content)

            # Match {{ blockname }} but not {{ blockname() }} or {{ blockname(...) }}
            pattern = r'\{\{\s*' + re.escape(block_name) + r'\s*\}\}'
            replacement = '{{ ' + block_name + '() }}'
            content = re.sub(pattern, replacement, content)

        try:
            # Render the template with jinja2
            template = self.jinja_env.from_string(content)
            rendered_content = await template.render_async(**all_params)

            return rendered_content

        except Exception as e:
            display_message(
                message=str(e),
                icon=QMessageBox.Warning,
            )
            return content
