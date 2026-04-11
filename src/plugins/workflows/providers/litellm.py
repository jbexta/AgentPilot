"""LiteLLM Provider Module.

This module provides the LiteLLM provider integration for Agent Pilot, enabling
connection to over 100 different AI model providers through a unified interface.
LiteLLM serves as the primary AI model integration layer, supporting text generation,
structured outputs, and various model configurations.

Key Features:
- Support for 100+ AI model providers (OpenAI, Anthropic, Google, etc.)
- Unified API interface for different model providers
- Structured output generation with Instructor integration
- Asynchronous and synchronous completion support
- Network connectivity validation and error handling
- Model configuration and parameter management
- Integration with Agent Pilot's model management system

The LiteLLM provider enables Agent Pilot to work with virtually any AI model
provider while maintaining consistent interfaces and functionality.
"""  # unchecked

import json
import os
import asyncio
import re
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import QMessageBox
import instructor
import litellm
from litellm import acompletion, completion
from pydantic import create_model

from gui import system
from utils.reset import reset_table
from utils import sql
from utils.helpers import display_message, network_connected, convert_model_json_to_obj, convert_to_safe_case
from plugins.workflows.managers.providers import Provider

litellm.log_level = 'ERROR'


class LitellmProvider(Provider):
    from gui.widgets.config_fields import ConfigFields

    ACCEPTED_KEYS = [
        'temperature', 'top_p', 'presence_penalty',
        'frequency_penalty', 'max_tokens',
    ]
    ACCEPTED_KEYS_WITH_API = ACCEPTED_KEYS + [
        'api_key', 'api_base', 'api_version', 'custom_provider',
    ]

    def __init__(self, parent):  # , api_id=None):
        super().__init__(parent=parent)
        # self.visible_tabs = ['Chat', 'Video']
        os.environ['OR_SITE_URL'] = 'https://agentpilot.ai'
        os.environ['OR_APP_NAME'] = 'AgentPilot'

        realtime_model_id = sql.get_scalar("""
            SELECT id 
            FROM models 
            WHERE COALESCE(json_extract(config, '$._model_name'), json_extract(config, '$.model_name')) LIKE 'gpt-4o-realtime%'
                AND kind = 'CHAT'
        """)

        if realtime_model_id:
            self.schema_overrides = {
                # 'gpt-4o-realtime-preview-2024-10-01': [
                int(realtime_model_id): [
                    # {
                    #     'text': 'Model name',
                    #     'type': str,
                    #     'label_width': 125,
                    #     'width': 265,
                    #     'tooltip': 'The name of the model to send to the API',
                    #     'default': '',
                    # },
                    {
                        'text': 'Voice',
                        'type': ('Alloy','Ash','Ballad','Coral','Echo','Sage','Shimmer','Verse',),
                        'label_width': 125,
                        'default': 'Alloy',
                    },
                    {
                        'text': 'Turn detection',
                        'type': bool,
                        'label_width': 125,
                        'default': True,
                    },
                    {
                        'text': 'Temperature',
                        'type': float,
                        'has_toggle': True,
                        'label_width': 145,
                        'minimum': 0.0,
                        'maximum': 1.0,
                        'step': 0.05,
                        'default': 0.6,
                    },
                ],
            }

    def get_model_parameters(self, model_obj, incl_api_data=True):
        provider, kind, model_name = model_obj['provider'], model_obj['kind'], model_obj['_model_name']
        if kind == 'CHAT':
            accepted_keys = self.ACCEPTED_KEYS_WITH_API if incl_api_data else self.ACCEPTED_KEYS
        else:
            accepted_keys = []

        model_config = self.models.get((provider, kind, model_name), {})
        return {k: v for k, v in model_config.items() if k in accepted_keys}

    async def run_model(self, model_obj, **kwargs):
        model_obj = convert_model_json_to_obj(model_obj)
        model_s_params = system.manager.models.get_model(model_obj)
        model_obj['model_params'] = {**model_obj.get('model_params', {}), **model_s_params}
        model_obj['model_params'] = {k: v for k, v in model_obj['model_params'].items() if k in self.ACCEPTED_KEYS_WITH_API}

        stream = kwargs.get('stream', True)
        messages = kwargs.get('messages', [])
        tools = kwargs.get('tools', None)

        model_name = model_obj['_model_name']
        model_params = model_obj.get('model_params', {})

        ex = None
        for i in range(5):
            try:
                kwargs = dict(
                    model=model_name,
                    messages=messages,
                    stream=stream,
                    request_timeout=100,
                    **(model_params or {}),
                )
                if tools:
                    kwargs['tools'] = tools
                    has_computer_tool = any(
                        t.get('type', '').startswith('computer_')
                        for t in tools
                    )
                    if not has_computer_tool:
                        kwargs['tool_choice'] = "auto"

                if next(iter(messages), {}).get('role') != 'user':
                    pass
                return await acompletion(**kwargs)
                
            except Exception as e:
                if not network_connected():
                    ex = ConnectionError('No network connection.')
                    break
                if 'Your organization must be verified to stream this model.' in str(e):
                    display_message(
                        icon=QMessageBox.Warning,
                        title="Warning",
                        message="You must verify your organization to stream this model. Switching to non-streaming response.",
                    )
                    stream = False
                    continue
                ex = e
                await asyncio.sleep(0.3 * i)
        raise ex

    async def get_structured_output(self, model_obj, **kwargs):
        def create_dynamic_model(model_name: str, attributes: List[Dict[str, Any]]) -> Any:
            field_definitions = {}

            type_mapping = {
                "str": str,
                "int": int,
                "float": float,
                "bool": bool
            }

            for attr in attributes:
                field_type = type_mapping.get(attr["type"], Any)
                if not attr["req"]:
                    field_type = Optional[field_type]

                attr["attribute"] = convert_to_safe_case(attr["attribute"])
                field_definitions[attr["attribute"]] = (field_type, ... if attr["req"] else None)

            return create_model(model_name, **field_definitions)

        structured_class_name = model_obj.get('model_params', {}).get('structured.class_name', 'Untitled')
        structured_data = model_obj.get('model_params', {}).get('structure.data', [])
        pydantic_model = create_dynamic_model(structured_class_name, structured_data)

        model_s_params = system.manager.models.get_model(model_obj)
        model_obj['model_params'] = {**model_obj.get('model_params', {}), **model_s_params}
        model_obj['model_params'] = {k: v for k, v in model_obj['model_params'].items() if k in self.ACCEPTED_KEYS_WITH_API}

        client = instructor.from_litellm(completion)

        model_name = model_obj['_model_name']
        model_params = model_obj.get('model_params', {})
        messages = kwargs.get('messages', [])

        resp = client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_model=pydantic_model,
            **(model_params or {}),
        )
        assert isinstance(resp, pydantic_model)
        return resp.json()

    def sync_models(self):
        # return
        try:
            from litellm import model_cost
            all_models = model_cost

            mode_map = {
                'chat': 'CHAT',
                # 'video_generation': 'VIDEO',
                'audio_transcription': 'TRANSCRIPTION',
                'embedding': 'EMBEDDING',
                'image_generation': 'IMAGE',
            }
            skip_subproviders = [
                'FAL_AI',
                'REPLICATE'
            ]
            # distinct_modes = set()
            apis = {}  # api_name_lower: {model_kind: {model_name: {}}}
            for model_name, model_data in all_models.items():
                api_name = model_data.get('litellm_provider', '')  # .lower()
                if api_name == '':
                    continue
                if api_name.upper() in skip_subproviders:
                    continue
                mode = model_data.get('mode', 'chat')
                if mode not in mode_map:
                    continue
                model_kind = mode_map[mode]
                # if ' ' in mode:  # patch bad data in json
                #     continue
                if api_name not in apis:
                    apis[api_name] = {}
                if model_kind not in apis[api_name]:
                    apis[api_name][model_kind] = {}
                apis[api_name][model_kind][model_name] = model_data
                # distinct_modes.add(model_data.get('mode', None))

            reset_table(
                table_name='apis',
                item_configs={
                    (('name', api_name.replace('_', ' ').title()),): {'litellm_prefix': api_name}
                    for api_name, _ in apis.items()
                },
                delete_existing=False,
            )

            # Define generic chat model input schema
            chat_input_schema = [
                # {
                #     'text': 'Model name',
                #     'key': 'model_name',
                #     'type': 'text',
                #     'label_width': 125,
                #     'width': 265,
                #     'tooltip': 'The name of the model to send to the API',
                #     'default': '',
                # },
                {
                    'text': 'Temperature',
                    'key': 'temperature',
                    'type': 'float',
                    'has_toggle': True,
                    'label_width': 125,
                    'minimum': 0.0,
                    'maximum': 1.0,
                    'step': 0.05,
                    'default': 0.6,
                    'row_key': 'A',
                },
                {
                    'text': 'Presence penalty',
                    'key': 'presence_penalty',
                    'type': 'float',
                    'has_toggle': True,
                    'label_width': 140,
                    'minimum': -2.0,
                    'maximum': 2.0,
                    'step': 0.2,
                    'default': 0.0,
                    'row_key': 'A',
                },
                {
                    'text': 'Top P',
                    'key': 'top_p',
                    'type': 'float',
                    'has_toggle': True,
                    'label_width': 125,
                    'minimum': 0.0,
                    'maximum': 1.0,
                    'step': 0.05,
                    'default': 1.0,
                    'row_key': 'B',
                },
                {
                    'text': 'Frequency penalty',
                    'key': 'frequency_penalty',
                    'type': 'float',
                    'has_toggle': True,
                    'label_width': 140,
                    'minimum': -2.0,
                    'maximum': 2.0,
                    'step': 0.2,
                    'default': 0.0,
                    'row_key': 'B',
                },
                {
                    'text': 'Max tokens',
                    'key': 'max_tokens',
                    'type': 'integer',
                    'has_toggle': True,
                    'label_width': 125,
                    'minimum': 1,
                    'maximum': 999999,
                    'step': 1,
                    'default': 100,
                },
            ]

            # Map model kinds to their input schemas
            kind_input_schemas = {
                'CHAT': chat_input_schema,
            }

            api_ids = sql.get_results(f'SELECT json_extract(config, "$.litellm_prefix"), id FROM apis', return_type='dict')
            api_models = {}
            for api_name, model_kinds in apis.items():
                for mode in mode_map.values():
                    mode_models = model_kinds.get(mode, {})
                    for model_name, model_metadata in mode_models.items():
                        if model_name.startswith(f'{api_name}/'):
                            model_name = model_name[len(f'{api_name}/'):]
                        
                        input_schema = kind_input_schemas.get(mode)
                        if input_schema:
                            model_metadata['input_schema'] = input_schema

                        # Replace `-` with space only if it's NOT between two digits
                        display_name = re.sub(r'(?<!\d)-(?!\d)', ' ', model_name)
                        display_name = display_name.replace('_', ' ').replace('/', ' / ').title()
                        # Replace all letters directly after a digit with lower case character
                        display_name = re.sub(r'\d([A-Za-z])', r'\1', display_name)

                        api_models[
                            ('name', display_name),
                            ('kind', mode),
                            ('api_id', api_ids[api_name]),
                            ('metadata', json.dumps(model_metadata)),
                        ] = {
                            '_model_name': model_name,
                        }

            reset_table(
                table_name='models',
                item_configs=api_models,
                delete_existing=False,
            )

        except Exception as e:
            display_message(
                icon=QMessageBox.Critical,
                title="LiteLLM model sync error",
                message=f"An error occurred while syncing LiteLLM models: {e}"
            )

    # class ChatModelParameters(ConfigFields):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.parent = parent
    #         self.schema = [
    #             {
    #                 'text': 'Model name',
    #                 'type': str,
    #                 'label_width': 125,
    #                 'width': 265,
    #                 # 'stretch_x': True,
    #                 'tooltip': 'The name of the model to send to the API',
    #                 'default': '',
    #             },
    #             {
    #                 'text': 'Temperature',
    #                 'type': float,
    #                 'has_toggle': True,
    #                 'label_width': 125,
    #                 'minimum': 0.0,
    #                 'maximum': 1.0,
    #                 'step': 0.05,
    #                 'default': 0.6,
    #                 'row_key': 'A',
    #             },
    #             {
    #                 'text': 'Presence penalty',
    #                 'type': float,
    #                 'has_toggle': True,
    #                 'label_width': 140,
    #                 'minimum': -2.0,
    #                 'maximum': 2.0,
    #                 'step': 0.2,
    #                 'default': 0.0,
    #                 'row_key': 'A',
    #             },
    #             {
    #                 'text': 'Top P',
    #                 'type': float,
    #                 'has_toggle': True,
    #                 'label_width': 125,
    #                 'minimum': 0.0,
    #                 'maximum': 1.0,
    #                 'step': 0.05,
    #                 'default': 1.0,
    #                 'row_key': 'B',
    #             },
    #             {
    #                 'text': 'Frequency penalty',
    #                 'type': float,
    #                 'has_toggle': True,
    #                 'label_width': 140,
    #                 'minimum': -2.0,
    #                 'maximum': 2.0,
    #                 'step': 0.2,
    #                 'default': 0.0,
    #                 'row_key': 'B',
    #             },
    #             {
    #                 'text': 'Max tokens',
    #                 'type': int,
    #                 'has_toggle': True,
    #                 'label_width': 125,
    #                 'minimum': 1,
    #                 'maximum': 999999,
    #                 'step': 1,
    #                 'default': 100,
    #             },
    #         ]

    # class V2VModelParameters(ConfigFields):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.parent = parent
    #         self.schema = [
    #             {
    #                 'text': 'Model name',
    #                 'type': str,
    #                 'label_width': 125,
    #                 'width': 265,
    #                 # 'stretch_x': True,
    #                 'tooltip': 'The name of the model to send to the API',
    #                 'default': '',
    #             },
    #             {
    #                 'text': 'Voice',
    #                 'type': ('Alloy',),
    #                 'label_width': 125,
    #                 'default': 'Alloy',
    #                 # 'row_key': 'A',
    #             },
    #             {
    #                 'text': 'Turn detection',
    #                 'type': bool,
    #                 'default': True,
    #                 'row_key': 'A',
    #             },
    #             {
    #                 'text': 'Temperature',
    #                 'type': float,
    #                 'has_toggle': True,
    #                 'label_width': 125,
    #                 'minimum': 0.0,
    #                 'maximum': 1.0,
    #                 'step': 0.05,
    #                 'default': 0.6,
    #             },
    #         ]
