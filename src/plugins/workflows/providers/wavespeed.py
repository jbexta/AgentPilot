
import json
import os
import time

import aiohttp
from PySide6.QtWidgets import QMessageBox
import requests

from gui import system
from utils.reset import reset_table
from utils import sql
from utils.helpers import display_message, convert_model_json_to_obj
from plugins.workflows.managers.providers import Provider


class WavespeedProvider(Provider):
    BASE_URL = 'https://api.wavespeed.ai/api/v3'

    def __init__(self, parent):
        super().__init__(parent=parent)

        # # patch todo
        # api_key = sql.get_scalar("""
        #     SELECT api_key FROM apis
        #     WHERE LOWER(name) = "wavespeed"
        # """)
        # if api_key and api_key.startswith('$'):
        #     api_key = os.environ.get(api_key[1:], '')
        # if api_key:
        #     os.environ['WAVESPEED_API_KEY'] = api_key

    def _get_api_key(self):
        """Retrieve and resolve the Wavespeed API key from DB."""
        api_key = sql.get_scalar(
            "SELECT api_key FROM apis "
            "WHERE LOWER(name) = 'wavespeed'"
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
        """Submit a Wavespeed AI model request and return request_id.

        Parameters
        ----------
        model_obj : dict
            Dict containing model_name, model_params, kind, provider.
        **kwargs
            Additional arguments (filepath, etc.).

        Returns
        -------
        generator
            Yields JSON string with request_id.
        """
        # 1. Prepare model object
        model_obj = convert_model_json_to_obj(model_obj)
        model_s_params = system.manager.models.get_model(model_obj)
        model_obj['model_params'] = {
            **model_obj.get('model_params', {}),
            **model_s_params,
        }
        model_name = model_obj['_model_name']

        # 2. Extract and validate API key
        api_key = model_obj['model_params'].get('api_key')
        if not api_key or api_key == 'NA':
            raise ValueError(
                "WAVESPEED_API_KEY environment variable not set"
            )

        # 3. Build arguments from model_params
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

        # 4. Submit task
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{self.BASE_URL}/{model_name}',
                headers=self._headers(api_key),
                json=arguments,
            ) as response:
                body = await response.json()
                if not response.ok:
                    err = body.get('message', str(body))
                    raise ValueError(
                        f"Wavespeed API error "
                        f"({response.status}): {err}")
                data = body

        if data.get('code') != 200:
            raise ValueError(
                f"Wavespeed API error: {data.get('message', 'Unknown')}"
            )

        # Use the poll URL provided by the API as request_id
        poll_url = data['data']['urls']['get']

        # 5. Return generator that yields request_id as JSON string
        def request_id_generator():
            yield json.dumps({
                'request_id': poll_url,
                'model_name': model_name,
                'provider': 'wavespeed',
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
        # request_id is the full poll URL from the submit response
        async with aiohttp.ClientSession() as session:
            async with session.get(
                request_id,
                headers=self._headers(api_key),
            ) as response:
                response.raise_for_status()
                body = await response.json()
        data = body['data']
        status = data.get('status', 'unknown')

        status_map = {
            'created': 'queued',
            'processing': 'in_progress',
            'completed': 'completed',
            'failed': 'failed',
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
        # request_id is the full poll URL from the submit response
        async with aiohttp.ClientSession() as session:
            async with session.get(
                request_id,
                headers=self._headers(api_key),
            ) as response:
                response.raise_for_status()
                body = await response.json()
        data = body['data']
        return data.get('outputs', [])

    async def upload_file(self, file_path):
        """Upload a local file to Wavespeed and return the URL."""
        import aiofiles
        api_key = self._get_api_key()
        async with aiofiles.open(file_path, 'rb') as f:
            file_data = await f.read()
        form = aiohttp.FormData()
        form.add_field(
            'file', file_data,
            filename=os.path.basename(file_path),
        )
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{self.BASE_URL}/media/upload/binary',
                headers={'Authorization': f'Bearer {api_key}'},
                data=form,
            ) as response:
                response.raise_for_status()
                body = await response.json()
        data = body['data']
        return data['download_url']

    def sync_models(self):
        """Fetch all Wavespeed models and store them in the DB."""

        reset_table(
            table_name='apis',
            item_configs={
                (('name', 'Wavespeed'),): {}
            },
            delete_existing=False,
        )
        api_id = sql.get_scalar(
            "SELECT id FROM apis WHERE LOWER(name) = 'wavespeed'"
        )
        # sql.execute(
        #     "UPDATE apis SET api_key = '$WAVESPEED_API_KEY' WHERE id = ?",
        #     (api_id,),
        # )

        api_key = self._get_api_key()
        if not api_key:
            display_message(
                icon=QMessageBox.Warning,
                title="API Key Required",
                message="WAVESPEED_API_KEY environment variable not set",
            )
            return

        mode_map = {
            'text-to-image': 'IMAGE',
            'image-to-image': 'IMAGE',
            'text-to-video': 'VIDEO',
            'image-to-video': 'VIDEO',
            'video-to-video': 'VIDEO',
            'text-to-audio': 'AUDIO',
            'audio-to-audio': 'AUDIO',
        }

        try:
            response = requests.get(
                f'{self.BASE_URL}/models',
                headers=self._headers(api_key),
            )
            if response.status_code != 200:
                raise Exception(
                    f"Error syncing models: {response.text}"
                )

            models_data = response.json().get('data', [])
            all_models = {}

            for model in models_data:
                model_id = model.get('model_id', '')
                model_type = model.get('type', '')
                mode = mode_map.get(model_type)
                if not mode:
                    print(
                        f"Skipping {model_id} - "
                        f"Unknown type '{model_type}'"
                    )
                    continue

                # Parse input schema from api_schema
                api_schema = model.get('api_schema', {})
                api_schemas = api_schema.get('api_schemas', [])
                if not api_schemas:
                    print(
                        f"Skipping {model_id} - No api_schemas"
                    )
                    continue

                request_schema = api_schemas[0].get(
                    'request_schema', {}
                )

                properties = request_schema.get('properties', {})
                required_fields = request_schema.get('required', [])
                input_schema = self.convert_all_openapi_properties(properties, required_fields=required_fields)

                if not input_schema:
                    print(
                        f"Skipping {model_id} - "
                        f"No input schema"
                    )
                    continue

                metadata = {
                    'description': model.get('description', ''),
                    'base_price': model.get('base_price', 0),
                    'input_schema': input_schema,
                }

                display_name = model_id
                if display_name.startswith('wavespeed-ai/'):
                    display_name = display_name[
                        len('wavespeed-ai/'):]

                all_models[
                    ('name', display_name),
                    ('kind', mode),
                    ('api_id', api_id),
                    ('metadata', json.dumps(metadata)),
                    ('provider_plugin', 'wavespeed'),
                ] = {
                    '_model_name': model_id,
                }
                # print(f"Found {model_id}")

            reset_table(
                table_name='models',
                item_configs=all_models,
                delete_existing=False,
            )

        except Exception as e:
            display_message(
                icon=QMessageBox.Critical,
                title="Wavespeed model sync error",
                message=f"An error occurred while syncing Wavespeed models: {e}"
            )
            return

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
                inner_number = next(
                    (c for c in valid_options
                        if c.get('type') == 'number'), None
                )
                inner_integer = next(
                    (c for c in valid_options
                        if c.get('type') == 'integer'), None
                )
                inner_enum = next(
                    (c for c in valid_options
                        if c.get('enum')), None
                )
                inner_string = next(
                    (c for c in valid_options
                        if c.get('type') == 'string'), None
                )
                inner_array = next(
                    (c for c in valid_options
                        if c.get('type') == 'array'), None
                )

                chosen = valid_options[0]

                if len(valid_options) == 2:
                    if inner_number and inner_integer:
                        chosen = inner_number
                        if 'le' in schema:
                            chosen['maximum'] = float(schema['le'])
                        if 'ge' in schema:
                            chosen['minimum'] = float(schema['ge'])
                    elif inner_enum and inner_string:
                        chosen = inner_enum
                    elif inner_array and inner_string:
                        chosen = inner_array

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