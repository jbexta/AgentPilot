
import json
import os

import aiohttp
from PySide6.QtWidgets import QMessageBox

from gui import system
from utils.reset import reset_table
from utils import sql
from utils.helpers import display_message, convert_model_json_to_obj
from plugins.workflows.managers.providers import Provider


class SonautoProvider(Provider):
    BASE_URL = 'https://api.sonauto.ai/v1'

    def __init__(self, parent):
        super().__init__(parent=parent)

    def _get_api_key(self):
        """Retrieve and resolve the Sonauto API key from DB."""
        api_key = sql.get_scalar(
            "SELECT api_key FROM apis "
            "WHERE LOWER(name) = 'sonauto'"
        )
        if api_key and api_key.startswith('$'):
            api_key = os.environ.get(api_key[1:], '')
        return api_key

    def _headers(self, api_key):
        return {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

    async def run_model(self, model_obj, **kwargs):
        """Submit a Sonauto generation request and return request_id.

        Parameters
        ----------
        model_obj : dict
            Dict containing model_name, model_params, kind, provider.
        **kwargs
            Additional arguments.

        Returns
        -------
        generator
            Yields JSON string with request_id.
        """
        model_obj = convert_model_json_to_obj(model_obj)
        model_s_params = system.manager.models.get_model(model_obj)
        model_obj['model_params'] = {
            **model_obj.get('model_params', {}),
            **model_s_params,
        }
        model_name = model_obj['_model_name']

        api_key = model_obj['model_params'].get('api_key')
        if not api_key or api_key == 'NA':
            raise ValueError(
                "Sonauto API key not set"
            )

        arguments = {
            k: v for k, v in model_obj.get('model_params', {}).items()
            if k not in ['api_key', 'api_base']
        }

        # Media upload fields store {"url": ..., "local_path": ...} --
        # extract just the URL before sending to the API.
        for k, v in arguments.items():
            if not isinstance(v, str):
                continue
            try:
                obj = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(obj, dict) and len(obj) == 2:
                if 'url' in obj and 'local_path' in obj:
                    arguments[k] = obj['url']

        # For inpaint, convert section_start/section_end to sections
        if model_name == 'v2-inpaint':
            start = arguments.pop('section_start', None)
            end = arguments.pop('section_end', None)
            if start is not None and end is not None:
                arguments['sections'] = [[float(start), float(end)]]

        # Map model name to endpoint
        endpoint_map = {
            'v3': '/generations/v3',
            'v2': '/generations/v2',
            'v2-extend': '/generations/v2/extend',
            'v2-inpaint': '/generations/v2/inpaint',
        }
        endpoint = endpoint_map.get(model_name)
        if not endpoint:
            raise ValueError(
                f"Unknown Sonauto model: {model_name}"
            )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{self.BASE_URL}{endpoint}',
                headers=self._headers(api_key),
                json=arguments,
            ) as response:
                body = await response.json()
                if not response.ok:
                    err = body.get('message', str(body))
                    raise ValueError(
                        f"Sonauto API error "
                        f"({response.status}): {err}"
                    )

        task_id = body.get('task_id')
        if not task_id:
            raise ValueError(
                f"Sonauto API did not return a task_id: {body}"
            )

        def request_id_generator():
            yield json.dumps({
                'request_id': task_id,
                'model_name': model_name,
                'provider': 'sonauto',
                'status': 'queued',
            })

        return request_id_generator()

    async def get_request_status(self, model_name, request_id):
        """Return normalized status dict for a queued request.

        Returns
        -------
        dict
            ``{'status': 'queued', 'position': None}``
            ``{'status': 'in_progress'}``
            ``{'status': 'completed'}``
        """
        api_key = self._get_api_key()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.BASE_URL}/generations/status/{request_id}',
                headers=self._headers(api_key),
            ) as response:
                response.raise_for_status()
                body = await response.json()

        if isinstance(body, str):
            status = body
        elif isinstance(body, dict):
            status = body.get('status', 'unknown')
        else:
            status = 'unknown'

        status_map = {
            'RECEIVED': 'queued',
            'PROMPT': 'queued',
            'TASK_SENT': 'queued',
            'GENERATE_TASK_STARTED': 'in_progress',
            'BEGINNING_GENERATION': 'in_progress',
            'GENERATING': 'in_progress',
            'DECOMPRESSING': 'in_progress',
            'SAVING': 'in_progress',
            'SUCCESS': 'completed',
            'FAILURE': 'failed',
        }

        return {
            'status': status_map.get(status, 'unknown'),
            'position': None,
        }

    async def get_request_result(self, model_name, request_id):
        """Return a list of media URLs for a completed request.

        Returns
        -------
        list[str]
            Downloadable media URLs.
        """
        api_key = self._get_api_key()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.BASE_URL}/generations/{request_id}',
                headers=self._headers(api_key),
            ) as response:
                response.raise_for_status()
                body = await response.json()

        return body.get('song_paths', [])

    def sync_models(self):
        """Register Sonauto API entry and hardcoded models."""
        reset_table(
            table_name='apis',
            item_configs={
                (('name', 'Sonauto'),): {}
            },
            delete_existing=False,
        )
        api_id = sql.get_scalar(
            "SELECT id FROM apis WHERE LOWER(name) = 'sonauto'"
        )

        # Shared base fields for v2 models
        shared_fields = [
            {
                'key': 'prompt',
                'text': 'Prompt',
                'type': 'text',
                'default': '',
                'num_lines': 2,
                'stretch_x': True,
                'stretch_y': True,
                'label_position': 'top',
                'highlighter': 'xml',
                'fold_mode': 'xml',
                'format_blocks': True,
                'wrap_text': True,
            },
            {
                'key': 'lyrics',
                'text': 'Lyrics',
                'type': 'text',
                'default': '',
                'num_lines': 2,
                'stretch_x': True,
                'stretch_y': True,
                'label_position': 'top',
                'highlighter': 'xml',
                'fold_mode': 'xml',
                'format_blocks': True,
            },
            {
                'key': 'tags',
                'text': 'Tags',
                'type': 'list',
                'of_type': 'text',
                'default': None,
                'has_toggle': True,
            },
            {
                'key': 'instrumental',
                'text': 'Instrumental',
                'type': 'boolean',
                'default': False,
            },
            {
                'key': 'prompt_strength',
                'text': 'Prompt Strength',
                'type': 'float',
                'default': 2.0,
                'minimum': 0.0,
                'maximum': 10.0,
            },
            {
                'key': 'output_format',
                'text': 'Output Format',
                'type': ('ogg', 'mp3', 'flac', 'wav', 'm4a'),
                'default': 'ogg',
            },
            {
                'key': 'output_bit_rate',
                'text': 'Output Bit Rate',
                'type': (128, 192, 256, 320),
                'default': None,
                'has_toggle': True,
            },
            {
                'key': 'align_lyrics',
                'text': 'Align Lyrics',
                'type': 'boolean',
                'default': False,
                'has_toggle': True,
            },
        ]

        # v2-only additional fields
        v2_extra = [
            {
                'key': 'balance_strength',
                'text': 'Balance Strength',
                'type': 'float',
                'default': 0.7,
                'minimum': 0.0,
                'maximum': 1.0,
            },
            {
                'key': 'seed',
                'text': 'Seed',
                'type': 'integer',
                'default': None,
                'minimum': -2147483648,
                'maximum': 2147483647,
                'has_toggle': True,
            },
            {
                'key': 'num_songs',
                'text': 'Num Songs',
                'type': (1, 2),
                'default': 1,
            },
            {
                'key': 'bpm',
                'text': 'BPM',
                'type': 'integer',
                'default': None,
                'minimum': 40,
                'maximum': 300,
                'has_toggle': True,
            },
        ]

        # v2-extend additional fields
        extend_extra = [
            {
                'key': 'audio_url',
                'text': 'Audio',
                'type': 'media_upload',
                'default': '',
                'tooltip': 'Source song to extend',
            },
            {
                'key': 'side',
                'text': 'Side',
                'type': ('left', 'right'),
                'default': 'left',
            },
            {
                'key': 'extend_duration',
                'text': 'Extend Duration',
                'type': 'float',
                'default': 0.0,
                'minimum': 0.0,
                'maximum': 85.0,
            },
            {
                'key': 'crop_duration',
                'text': 'Crop Duration',
                'type': 'float',
                'default': 0.0,
                'minimum': 0.0,
                'maximum': 85.0,
                'has_toggle': True,
            },
        ]

        # v2-inpaint additional fields
        inpaint_extra = [
            {
                'key': 'audio_url',
                'text': 'Audio',
                'type': 'media_upload',
                'default': '',
                'tooltip': 'Source track to inpaint',
            },
            {
                'key': 'section_start',
                'text': 'Section Start',
                'type': 'float',
                'default': 0.0,
                'minimum': 0.0,
                'maximum': 3.402823466e+38,
                'tooltip': 'Start of section in seconds',
            },
            {
                'key': 'section_end',
                'text': 'Section End',
                'type': 'float',
                'default': 0.0,
                'minimum': 0.0,
                'maximum': 3.402823466e+38,
                'tooltip': 'End of section in seconds',
            },
            {
                'key': 'selection_crop',
                'text': 'Selection Crop',
                'type': 'boolean',
                'default': False,
                'has_toggle': True,
            },
        ]

        # For inpaint, lyrics is required (no toggle)
        def make_inpaint_shared():
            fields = json.loads(json.dumps(shared_fields))
            for f in fields:
                if f['key'] == 'lyrics':
                    f.pop('has_toggle', None)
            return fields

        models = {
            'Sonauto v3': {
                '_model_name': 'v3',
                'schema': list(shared_fields),
            },
            'Sonauto v2': {
                '_model_name': 'v2',
                'schema': shared_fields + v2_extra,
            },
            'Sonauto v2 Extend': {
                '_model_name': 'v2-extend',
                'schema': shared_fields + extend_extra,
            },
            'Sonauto v2 Inpaint': {
                '_model_name': 'v2-inpaint',
                'schema': make_inpaint_shared() + inpaint_extra,
            },
        }

        all_models = {}
        for display_name, model_info in models.items():
            metadata = {
                'input_schema': model_info['schema'],
            }
            all_models[
                ('name', display_name),
                ('kind', 'AUDIO'),
                ('api_id', api_id),
                ('metadata', json.dumps(metadata)),
                ('provider_plugin', 'sonauto'),
            ] = {
                '_model_name': model_info['_model_name'],
            }

        reset_table(
            table_name='models',
            item_configs=all_models,
            delete_existing=False,
        )

    def resolve_schema(self, schema):
        """Resolve complex JSON schemas into a single type.

        Returns
        -------
        tuple
            (resolved_schema_dict, is_nullable)
        """
        is_nullable = False

        if 'anyOf' in schema or 'oneOf' in schema:
            choices = schema.get('anyOf') or schema.get('oneOf')
            valid_options = []

            for choice in choices:
                if choice.get('type') == 'null':
                    is_nullable = True
                else:
                    valid_options.append(choice)

            if valid_options:
                chosen = valid_options[0]
                chosen_schema, inner_nullable = self.resolve_schema(
                    chosen
                )
                return chosen_schema, (is_nullable or inner_nullable)

            return {'type': 'null'}, True

        elif 'allOf' in schema:
            merged_schema = {}
            for sub_schema in schema['allOf']:
                resolved_sub, _ = self.resolve_schema(sub_schema)
                merged_schema.update(resolved_sub)
            return merged_schema, False

        return schema, False
