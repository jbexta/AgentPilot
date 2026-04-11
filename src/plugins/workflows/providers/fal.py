
import json
import asyncio
import os
import re
import time

from PySide6.QtWidgets import QMessageBox
import fal_client
import requests

from gui import system
from utils.reset import reset_table
from utils import sql
from utils.helpers import display_message, convert_model_json_to_obj
from plugins.workflows.managers.providers import Provider


class FalProvider(Provider):
    from gui.widgets.config_fields import ConfigFields
    def __init__(self, parent):
        super().__init__(parent=parent)
        
        # patch todo
        api_key = sql.get_scalar("""
            SELECT api_key FROM apis
            WHERE LOWER(name) = "fal ai"
        """)
        if api_key.startswith('$'):
            api_key = os.environ.get(api_key[1:], '')
        os.environ['FAL_KEY'] = api_key
        
    def get_model_parameters(self, model_obj, incl_api_data=True):
        raise NotImplementedError("Not implemented")
        provider, kind, model_name = model_obj['provider'], model_obj['kind'], model_obj['_model_name']
        if kind == 'CHAT':
            accepted_keys = [
                'temperature',
                'top_p',
                'presence_penalty',
                'frequency_penalty',
                'max_tokens',
            ]
            if incl_api_data:
                accepted_keys.extend([
                    'api_key',
                    'api_base',
                    'api_version',
                    'custom_provider',
                ])
        else:
            accepted_keys = []

        model_config = self.models.get((provider, kind, model_name), {})
        cleaned_model_config = {k: v for k, v in model_config.items() if k in accepted_keys}
        return cleaned_model_config

    async def run_model(self, model_obj, **kwargs):
        """Submit a Fal AI model request to queue and return request_id.

        Args:
            model_obj: Dict containing model_name, model_params, kind, provider
            **kwargs: Additional arguments (filepath, etc.)

        Returns:
            Generator yielding JSON string with request_id
        """
        # 1. Prepare model object
        model_obj = convert_model_json_to_obj(model_obj)
        model_s_params = system.manager.models.get_model(model_obj)
        model_obj['model_params'] = {**model_obj.get('model_params', {}), **model_s_params}
        model_name = model_obj['_model_name']

        # 2. Extract and validate API key
        api_key = model_obj['model_params'].get('api_key')
        if not api_key or api_key == 'NA':
            raise ValueError("FAL_API_KEY environment variable not set")
        os.environ['FAL_API_KEY'] = api_key

        # 3. Build arguments from model_params (Fal uses model-specific params)
        arguments = {k: v for k, v in model_obj.get('model_params', {}).items()
                     if k not in ['api_key', 'api_base']}

        # Media upload fields store {"url": ..., "local_path": ...} —
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

        # 4. Submit to queue (returns immediately)
        handler = await fal_client.submit_async(model_name, arguments=arguments)
        request_id = handler.request_id

        # 5. Return generator that yields request_id as JSON string
        def request_id_generator():
            yield json.dumps({
                'request_id': request_id,
                'model_name': model_name,
                'provider': 'fal',
                'status': 'queued',
            })

        return request_id_generator()

    # async def get_transcription_result(self, model_name, request_id):
    #     """Poll and return transcription result as dict.

    #     Unlike get_result() which downloads binary media, this returns
    #     structured JSON containing text and timestamp chunks.

    #     Parameters
    #     ----------
    #     model_name : str
    #         Fal model endpoint (e.g., "fal-ai/whisper").
    #     request_id : str
    #         Saved request ID from run_model().

    #     Returns
    #     -------
    #     dict
    #         Response dict with text and chunks/segments.
    #     """
    #     while True:
    #         status = await fal_client.status_async(model_name, request_id)
    #         if isinstance(status, fal_client.Completed):
    #             break
    #         await asyncio.sleep(2)
    #     return await fal_client.result_async(model_name, request_id)

    def sync_models(self):
        reset_table(
            table_name='apis',
            item_configs={
                (('name', 'Fal AI'),): {}
            },
            delete_existing=False,
        )
        api_id = sql.get_scalar("SELECT id FROM apis WHERE LOWER(name) = 'fal ai'")

        mode_maps = {
            'image': 'IMAGE',
            'video': 'VIDEO',
            'speech': 'AUDIO',
            'audio': 'AUDIO',
            '3d': '3D',
            'text': 'TEXT',
        }

        # # get all categories from the api
        # all_categories = requests.get(
        #     'https://api.fal.ai/v1/categories',
        #     params={
        #         "limit": 100,
        #     }
        # ).json()
        # all_categories = [category['name'] for category in all_categories.get('categories', [])]

        get_categories = [
            'audio-to-video',
            'text-to-image',
            'image-to-image',
            'text-to-video',
            'image-to-video',
            'video-to-video',
            'text-to-audio',
            'audio-to-audio',
            'video-to-audio',
            'text-to-speech',
            'speech-to-speech',
            'speech-to-text',
            'text-to-3d',
            'image-to-3d',
            '3d-to-3d',
            'unknown',
        ]

        # temp_list = []
        try:
            for category in get_categories:
                all_models = {}

                next_cursor = None
                while True:
                    time.sleep(7)
                    response = requests.get(
                        'https://api.fal.ai/v1/models',
                        params={
                            "expand":"openapi-3.0",
                            "cursor": next_cursor,
                            "status": "active",
                            "limit": 10,
                            "category": category,
                        }
                    )
                    is_error = response.status_code != 200
                    if is_error:
                        raise Exception(f"Error syncing models: {response.text}")

                    response = response.json()
                    for model in response.get('models', []):
                        model_name = model['endpoint_id']
                        metadata = model.get('metadata', {})
                        category = metadata.get('category', None)
                        cat_end = category.split('-')[-1].lower() if '-' in category else None
                        mode = mode_maps.get(cat_end, None)
                        if not mode:
                            # patch for any broken api data
                            if 'fal-ai/qwen-3-tts' in model_name:
                                mode = 'AUDIO'
                            else:
                                print(f"Skipping {model_name} - No valid mode")
                                continue
                        # all_categories.add(category)

                        if 'openapi' not in model:
                            print(f"Skipping {model_name} - No openapi schema")

                            continue
                        if 'components' not in model['openapi']:
                            # print(f"Skipping {model_name} - No openapi components")
                            # continue
                            time.sleep(7)
                            # model_name_last_segment = model_name.split('/')[-1]
                            orig_model_name = model_name
                            model_name = model_name.rsplit('/', 1)[0]
                            fallback_resp = requests.get(  # todo dedupe
                                'https://api.fal.ai/v1/models',
                                params={
                                    "expand":"openapi-3.0",
                                    "cursor": next_cursor,
                                    "status": "active",
                                    "endpoint_id": model_name,
                                }
                            )
                            if fallback_resp.status_code != 200:
                                print(f"Skipping {orig_model_name} - No openapi components")
                                continue

                            fallback_data = fallback_resp.json()
                            if len(fallback_data['models']) == 0:
                                print(f"Skipping {orig_model_name} - No openapi components")
                                continue

                            model = fallback_data['models'][0]
                            metadata = model.get('metadata', {})
                            category = metadata.get('category', None)
                            cat_end = category.split('-')[-1].lower() if '-' in category else None
                            mode = mode_maps.get(cat_end, None)
                            if not mode:  # todo dedupe
                                # patch for any broken api data
                                if 'fal-ai/qwen-3-tts' in model_name:
                                    mode = 'AUDIO'
                                else:
                                    print(f"Skipping {model_name} - No valid mode")
                                continue
                        
                        openapi_schema = model['openapi']['components']['schemas']
                        
                        # # if 'longcat' in model_name:  #  == 'fal-ai/longcat-single-avatar/audio-to-video':
                        # #     temp_list.append(model_name)
                        input_schema, output_schema = [], []
                        for schema_name, schema_data in openapi_schema.items():
                            if schema_name.endswith('Input'):  # todo how else to identify input/output schemas?
                                properties = schema_data.get('properties', {})
                                property_order = schema_data.get('x-fal-order-properties', [])
                                input_schema = self.convert_all_openapi_properties(properties, property_order)

                            elif schema_name.endswith('Output'):
                                output_schema = schema_data

                        if not (input_schema):
                            print(f"Skipping {model_name} - No input/output schemas")
                            continue

                        metadata['input_schema'] = input_schema
                        metadata['output_schema'] = output_schema

                        display_name = model_name
                        if display_name.startswith('fal-ai/'):
                            display_name = display_name[len('fal-ai/'):]

                        all_models[
                            ('name', display_name), # metadata.get('display_name', model_name)),
                            ('kind', mode),
                            ('api_id', api_id),
                            ('metadata', json.dumps(metadata)),
                            ('provider_plugin', 'fal'),
                        ] = {
                            '_model_name': model_name,
                        }
                        # print(f"Found {model_name}")

                    if not response.get('has_more', False):
                        break
                    next_cursor = response.get('next_cursor', None)

                reset_table(
                    table_name='models',
                    item_configs=all_models,
                    delete_existing=False,
                )
            pass

        except Exception as e:
            display_message(
                icon=QMessageBox.Critical,
                title="FalAI model sync error",
                message=f"An error occurred while syncing FalAI models: {e}"
            )
            return

    def resolve_schema(self, schema):
        # Helper function to resolve complex JSON schemas into a single type definition
        """
        Returns a tuple: (resolved_schema_dict, is_nullable)
        Recurses through anyOf/oneOf/allOf to find the 'dominant' type for the UI.
        """
        is_nullable = False
        
        # 1. Handle anyOf / oneOf (Choice structures)
        # Logic: Check if 'null' is an option. Then pick the first non-null schema.
        if 'anyOf' in schema or 'oneOf' in schema:
            choices = schema.get('anyOf') or schema.get('oneOf')
            valid_options = []
            
            for choice in choices:
                if choice.get('type') == 'null':
                    is_nullable = True
                else:
                    valid_options.append(choice)
            
            if valid_options:
                inner_array = next((choice for choice in valid_options if choice.get('type') == 'array'), None)
                inner_string = next((choice for choice in valid_options if choice.get('type') == 'string'), None)
                inner_enum = next((choice for choice in valid_options if choice.get('enum')), None)
                inner_number = next((choice for choice in valid_options if choice.get('type') == 'number'), None)
                inner_integer = next((choice for choice in valid_options if choice.get('type') == 'integer'), None)
                
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
                    else:
                        pass
                elif len(valid_options) > 2:
                    pass
                    
                chosen_schema, inner_nullable = self.resolve_schema(chosen)
                # Propagate nullability
                return chosen_schema, (is_nullable or inner_nullable)
            
            # If only null is available (weird, but possible)
            return {'type': 'null'}, True

        # 2. Handle allOf (Combination structures)
        # Logic: Merge properties from all schemas.
        elif 'allOf' in schema:
            merged_schema = {}
            for sub_schema in schema['allOf']:
                resolved_sub, _ = self.resolve_schema(sub_schema)
                merged_schema.update(resolved_sub)
            return merged_schema, False

        # 3. Handle Standard Types
        return schema, False

    async def upload_file(self, file_path):
        """Upload a local file to Fal CDN and return the URL."""
        url = await fal_client.upload_file_async(file_path)
        return url

    async def get_request_result(self, model_name, request_id):
        response = await fal_client.result_async(
            model_name, request_id
        )
        all_media_urls = []
        coll_keys = ['images', 'image', 'video', 'videos', 'audio', 'audios']
        coll_keys.extend([f'{s}_url' for s in coll_keys])
        for key in coll_keys:
            if key in response:
                if isinstance(response[key], dict):
                    all_media_urls.append(response[key]['url'])
                elif isinstance(response[key], list):
                    all_media_urls.extend([item['url'] for item in response[key]])
                else:
                    raise NotImplementedError(f"Unknown type: {type(response[key])}")
                    # all_media_urls.extend([item['url'] for item in response[key]])
        return all_media_urls
    
    async def get_request_status(self, model_name, request_id):
        """Return normalized status dict.

        Returns
        -------
        dict
            ``{'status': 'queued', 'position': int}``
            ``{'status': 'in_progress'}``
            ``{'status': 'completed'}``
        """
        status = await fal_client.status_async(model_name, request_id)
        if isinstance(status, fal_client.Queued):
            return {
                'status': 'queued',
                'position': getattr(status, 'position', None),
            }
        elif isinstance(status, fal_client.InProgress):
            return {'status': 'in_progress'}
        elif isinstance(status, fal_client.Completed):
            return {'status': 'completed'}
        return {'status': 'unknown'}