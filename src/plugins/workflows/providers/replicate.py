
import json
import asyncio
import os
from typing import Any

from PySide6.QtWidgets import QMessageBox
import aiohttp
import replicate

from gui import system
from utils.reset import reset_table
from utils import sql
from utils.helpers import display_message, network_connected, convert_model_json_to_obj
from utils.media import get_media_type_from_ext
from utils.helpers import set_module_type
from plugins.workflows.managers.providers import Provider


@set_module_type(module_type='Providers')
class ReplicateProvider(Provider):
    def __init__(self, parent):
        super().__init__(parent=parent)

    def get_model_parameters(self, model_obj, incl_api_data=True):
        raise NotImplementedError("Not implemented")

    def _get_api_key(self):
        """Retrieve and resolve the Replicate API key from DB."""
        api_key = sql.get_scalar(
            "SELECT api_key FROM apis "
            "WHERE LOWER(name) = 'replicate'"
        )
        if api_key and api_key.startswith('$'):
            api_key = os.environ.get(api_key[1:], '')
        return api_key

    async def run_model(self, model_obj, **kwargs):
        """Submit a Replicate model request and return prediction_id.

        Args:
            model_obj: Dict containing model_name, model_params, kind, provider
            **kwargs: Additional arguments

        Returns:
            Generator yielding JSON string with prediction_id
        """
        model_obj = convert_model_json_to_obj(model_obj)
        model_s_params = system.manager.models.get_model(model_obj)
        model_obj['model_params'] = {**model_obj.get('model_params', {}), **model_s_params}
        model_name = model_obj['_model_name']

        api_key = model_obj['model_params'].get('api_key')
        if not api_key or api_key == 'NA':
            raise ValueError("REPLICATE_API_KEY environment variable not set")
        os.environ['REPLICATE_API_TOKEN'] = api_key

        arguments = {k: v for k, v in model_obj.get('model_params', {}).items()
                     if k not in ['api_key', 'api_base']}

        def extract_url(v):
            if not isinstance(v, str):
                return v
            try:
                obj = json.loads(v)
                if isinstance(obj, dict) and 'url' in obj:
                    return obj['url']
            except (json.JSONDecodeError, TypeError):
                pass
            return v

        for k, v in arguments.items():
            if isinstance(v, list):
                arguments[k] = [extract_url(item) for item in v]
            else:
                arguments[k] = extract_url(v)

        client = replicate.Client(api_token=api_key)
        if ':' in model_name:
            version = model_name.split(':', 1)[1]
            prediction = client.predictions.create(
                version=version,
                input=arguments
            )
        else:
            prediction = client.predictions.create(
                model=model_name,
                input=arguments
            )
        prediction_id = prediction.id

        def prediction_id_generator():
            yield json.dumps({
                'request_id': prediction_id,
                'model_name': model_name,
                'provider': 'replicate',
                'status': 'queued'
            })

        return prediction_id_generator()

    async def get_request_status(self, model_name, request_id):
        """Return normalized status dict for a queued prediction.

        Returns
        -------
        dict
            ``{'status': 'queued'}``
            ``{'status': 'in_progress'}``
            ``{'status': 'completed'}``
            ``{'status': 'failed'}``
        """
        api_key = os.environ.get('REPLICATE_API_TOKEN')
        client = replicate.Client(api_token=api_key)
        prediction = await asyncio.to_thread(client.predictions.get, request_id)
        status = prediction.status
        if status in ('starting', 'queued'):
            return {'status': 'queued'}
        elif status == 'processing':
            return {'status': 'in_progress'}
        elif status == 'succeeded':
            return {'status': 'completed'}
        elif status in ('failed', 'canceled'):
            return {'status': 'failed'}
        return {'status': 'unknown'}

    async def get_request_result(self, model_name, request_id):
        """Return a list of media URLs for a completed prediction.

        Returns
        -------
        list[str]
            Downloadable media URLs.
        """
        api_key = os.environ.get('REPLICATE_API_TOKEN')
        client = replicate.Client(api_token=api_key)
        prediction = await asyncio.to_thread(client.predictions.get, request_id)
        output = prediction.output

        media_urls = []
        if isinstance(output, list):
            for item in output:
                if isinstance(item, str):
                    media_urls.append(item)
                elif hasattr(item, 'url'):
                    media_urls.append(item.url)
        elif isinstance(output, str):
            media_urls.append(output)
        elif hasattr(output, 'url'):
            media_urls.append(output.url)

        return media_urls

    async def get_result(self, model_name, request_id):
        """Poll for completion and download result.

        Args:
            model_name: Replicate model identifier
            request_id: Saved prediction ID from run_model()

        Returns:
            Generator yielding binary chunks
        """
        api_key = os.environ.get('REPLICATE_API_TOKEN')
        client = replicate.Client(api_token=api_key)

        while True:
            prediction = await asyncio.to_thread(client.predictions.get, request_id)
            if prediction.status == 'succeeded':
                break
            elif prediction.status in ('failed', 'canceled'):
                raise ValueError(f"Prediction {prediction.status}: {prediction.error}")
            print(f"[Replicate] Status: {prediction.status}")
            await asyncio.sleep(2)

        output = prediction.output

        media_url = None
        if isinstance(output, list) and len(output) > 0:
            media_url = output[0] if isinstance(output[0], str) else getattr(output[0], 'url', None)
        elif isinstance(output, str):
            media_url = output
        elif hasattr(output, 'url'):
            media_url = output.url

        if not media_url:
            raise ValueError(f"Could not find media URL in response: {output}")

        async with aiohttp.ClientSession() as session:
            async with session.get(media_url) as media_response:
                media_response.raise_for_status()
                content = await media_response.read()

        def chunk_generator():
            for i in range(0, len(content), 8192):
                yield content[i:i + 8192]

        return chunk_generator()

    async def get_transcription_result(self, model_name, request_id):
        """Poll and return transcription result as dict.

        Unlike get_result() which downloads binary media, this returns
        structured JSON/text output directly.

        Parameters
        ----------
        model_name : str
            Replicate model identifier.
        request_id : str
            Saved prediction ID from run_model().

        Returns
        -------
        dict or str
            Transcription output from the model.
        """
        api_key = os.environ.get('REPLICATE_API_TOKEN')
        client = replicate.Client(api_token=api_key)
        while True:
            prediction = await asyncio.to_thread(client.predictions.get, request_id)
            if prediction.status == 'succeeded':
                return prediction.output
            elif prediction.status in ('failed', 'canceled'):
                raise ValueError(
                    f"Prediction {prediction.status}: {prediction.error}"
                )
            await asyncio.sleep(2)

    async def sync_models(self, model_names=None, default_kind=None):
        """Sync Replicate models into the models table.

        With `model_names`, fetches only those models (owner/name) instead of
        paginating the full catalog. `default_kind` is used for targeted models
        whose kind can't be inferred from their default example output.
        """
        reset_table(
            table_name='apis',
            item_configs={
                (('name', 'Replicate'),): {}
            },
            delete_existing=False,
        )
        api_id = sql.get_scalar("SELECT id FROM apis WHERE LOWER(name) = 'replicate'")

        api_key = self._get_api_key()
        if not api_key:
            display_message(
                icon=QMessageBox.Warning,
                title="API Key Required",
                message="Replicate API key not set"
            )
            return

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        try:
            all_models = {}

            async def fetch(url):
                async with session.get(url) as resp:
                    return resp.status, await resp.text()

            async with aiohttp.ClientSession(headers=headers) as session:
                if model_names:
                    for model_name in model_names:
                        status, text = await fetch(
                            f'https://api.replicate.com/v1/models/{model_name}'
                        )
                        if status != 200:
                            print(f"Skipping {model_name} - {text}")
                            continue
                        entry = self._build_model_entry(json.loads(text), api_id, default_kind=default_kind)
                        if entry:
                            all_models[entry[0]] = entry[1]
                else:
                    next_url = 'https://api.replicate.com/v1/models'

                    while next_url:
                        await asyncio.sleep(1)
                        status, text = await fetch(next_url)

                        if status != 200:
                            raise Exception(f"Error syncing models: {text}")

                        data = json.loads(text)

                        for model in data.get('results', []):
                            entry = self._build_model_entry(model, api_id)
                            if entry:
                                all_models[entry[0]] = entry[1]

                        next_url = data.get('next')

            reset_table(
                table_name='models',
                item_configs=all_models,
                delete_existing=False,
                match_on=('name', 'api_id'),
            )

        except Exception as e:
            display_message(
                icon=QMessageBox.Critical,
                title="Replicate model sync error",
                message=f"An error occurred while syncing Replicate models: {e}"
            )
            return

    def _build_model_entry(self, model, api_id, default_kind=None):
        """Convert a Replicate API model dict into a models-table entry.

        Returns (key_tuple, config) for reset_table, or None to skip.
        """
        def get_output_ext(value):
            if isinstance(value, str) and value.startswith('http'):
                return os.path.splitext(value)[1].lower()
            else:
                return None

        owner = model.get('owner')
        name = model.get('name')
        model_name = f"{owner}/{name}"
        description = model.get('description', '') or ''

        latest_version = model.get('latest_version')
        if not latest_version:
            print(f"Skipping {model_name} - No latest version")
            return None

        openapi_schema = latest_version.get('openapi_schema')
        if not openapi_schema:
            print(f"Skipping {model_name} - No openapi schema")
            return None

        components = openapi_schema.get('components', {})
        schemas = components.get('schemas', {})

        mode = 'CHAT'
        default_output = (model.get('default_example') or {}).get('output', None)

        if default_output is None:
            if default_kind is None:
                print(f"Skipping {model_name} - No default output")
                return None
            mode = default_kind

        if default_output:
            # Unwrap single-entry dict wrappers
            # e.g. {"output": {"bass": "https://...", ...}} → {"bass": "https://...", ...}
            while isinstance(default_output, dict) and len(default_output) == 1:
                default_output = next(iter(default_output.values()))

            collection = None
            if isinstance(default_output, dict):
                collection = list(default_output.values())
            elif isinstance(default_output, list):
                collection = default_output

            output_ext = None
            skip = False
            if 'demucs' in model_name.lower():
                output_ext = ".mp3"  # todo hack
            elif collection:
                for value in collection:
                    value_ext = get_output_ext(value)
                    if output_ext is not None and output_ext != value_ext:
                        skip = True
                        break
                    output_ext = value_ext
            else:
                output_ext = get_output_ext(default_output)

            media_type = None if skip else get_media_type_from_ext(output_ext)
            if media_type is None and not skip:
                if isinstance(default_output, str):
                    media_type = 'text'
                elif isinstance(default_output, list) and all(isinstance(item, str) for item in default_output):
                    media_type = 'text'

            if media_type is None:
                if default_kind is None:
                    if skip:
                        print(f"Skipping {model_name} - Output schema not supported")
                    else:
                        default_output_str = str(default_output).replace('\n', '')[:200]
                        print(f"Skipping {model_name} - Unknown output type `{default_output_str}`")
                    return None
                mode = default_kind
            else:
                mode = media_type.upper()

        cover_image = model.get('cover_image_url', '')

        self._component_schemas = schemas

        input_schema = []
        output_schema = {}

        for schema_name, schema_data in schemas.items():
            if schema_name == 'Input':
                properties = schema_data.get('properties', {})
                required_fields = schema_data.get('required', [])
                input_schema = self.convert_all_openapi_properties(properties, required_fields=required_fields)

            elif schema_name == 'Output':
                output_schema = schema_data

        # Duration fields where -1 means "auto" (e.g. Seedance):
        # default to auto instead of a toggleable explicit length,
        # since omitting the field falls back to the API's 5s default.
        for prop in input_schema:
            if prop.get('key') == 'duration' and prop.get('minimum') == -1:
                prop['default'] = -1
                prop['has_toggle'] = False

        if not input_schema:
            print(f"Skipping {model_name} - No input schema")
            return None

        metadata = {
            'description': description,
            'run_count': model.get('run_count', 0),
            'cover_image_url': cover_image,
            'input_schema': input_schema,
            'output_schema': output_schema,
        }

        display_name = model.get('name', model_name)

        version_id = latest_version.get('id', '')
        versioned_name = f"{model_name}:{version_id}" if version_id else model_name

        key = (
            ('name', display_name),
            ('kind', mode),
            ('api_id', api_id),
            ('metadata', json.dumps(metadata)),
            ('provider_plugin', 'replicate'),
        )
        return key, {'_model_name': versioned_name}

    def resolve_schema(self, schema, schemas=None):
        """Resolve complex JSON schemas into a single type definition.

        Handles $ref, anyOf, oneOf, and allOf patterns.

        Parameters
        ----------
        schema : dict
            The schema to resolve.
        schemas : dict, optional
            The components/schemas dict for resolving $ref pointers.

        Returns
        -------
        tuple
            (resolved_schema_dict, is_nullable)
        """
        if schemas is None:
            schemas = getattr(self, '_component_schemas', {})

        is_nullable = False

        # Handle $ref - resolve reference from components/schemas
        if '$ref' in schema:
            ref_path = schema['$ref']
            # Format: "#/components/schemas/{name}"
            if ref_path.startswith('#/components/schemas/'):
                ref_name = ref_path.split('/')[-1]
                if ref_name in schemas:
                    resolved, inner_nullable = self.resolve_schema(schemas[ref_name], schemas)
                    return resolved, inner_nullable
            return schema, False

        if 'anyOf' in schema or 'oneOf' in schema:
            choices = schema.get('anyOf') or schema.get('oneOf')
            valid_options = []

            for choice in choices:
                if choice.get('type') == 'null':
                    is_nullable = True
                else:
                    valid_options.append(choice)

            if valid_options:
                chosen_schema, inner_nullable = self.resolve_schema(valid_options[0], schemas)
                return chosen_schema, (is_nullable or inner_nullable)

            return {'type': 'null'}, True

        elif 'allOf' in schema:
            merged_schema = {}
            for sub_schema in schema['allOf']:
                resolved_sub, _ = self.resolve_schema(sub_schema, schemas)
                merged_schema.update(resolved_sub)
            # Merge any sibling properties (like default, description) from original schema
            for key, value in schema.items():
                if key != 'allOf':
                    merged_schema[key] = value
            return merged_schema, False

        return schema, False

    def media_probe_headers(self):
        """Replicate file URLs require auth even for accessibility checks."""
        return {'Authorization': f'Bearer {self._get_api_key()}'}

    async def upload_file(self, file_path):
        """Upload a local file to Replicate and return the URL."""
        api_key = self._get_api_key()
        client = replicate.Client(api_token=api_key)

        def _upload():
            with open(file_path, 'rb') as f:
                return client.files.create(
                    file=f,
                    filename=os.path.basename(file_path),
                )

        result = await asyncio.to_thread(_upload)
        return result.urls["get"]
