
import base64
import json
import mimetypes
import os

import aiohttp

from utils.reset import reset_table
from utils import sql
from utils.helpers import convert_model_json_to_obj
from plugins.workflows.managers.providers import Provider

VERIFY_HELP = (
    "Images containing real people are rejected unless they come from a "
    "verified asset. Have the person verify their identity in the ModelArk "
    "console (Model Playground > Asset library > add real-human asset: they "
    "scan a QR code and complete facial verification), then pass the "
    "resulting asset ID in the 'Real human asset' field. "
    "See https://docs.byteplus.com/en/docs/ModelArk/2315856"
)


class SeedanceProvider(Provider):
    """ByteDance Seedance 2.0 via the first-party ModelArk (Ark v3) API.

    This is the only Seedance route that can generate videos of real,
    identifiable humans. There is no public API for registering a person:
    verification is done in the ModelArk console — the person scans a QR
    code, completes facial verification, and authorizes the account — which
    yields an asset ID the API consumes as ``asset://<asset_id>``.
    """
    BASE_URL = 'https://ark.ap-southeast.bytepluses.com/api/v3'

    # Ark task statuses -> normalized provider statuses
    STATUS_MAP = {
        'queued': 'queued',
        'running': 'in_progress',
        'succeeded': 'completed',
        'failed': 'failed',
        'cancelled': 'failed',
    }

    # Params sent at the top level of the task body, not as content items
    CONTROL_PARAMS = ('resolution', 'ratio', 'duration', 'generate_audio', 'watermark')

    def __init__(self, parent):
        super().__init__(parent=parent)

    def _get_api_key(self):
        """Retrieve and resolve the Seedance (Ark) API key from DB."""
        api_key = sql.get_scalar(
            "SELECT api_key FROM apis "
            "WHERE LOWER(name) = 'seedance'"
        )
        if api_key and api_key.startswith('$'):
            api_key = os.environ.get(api_key[1:], '')
        return api_key

    def _headers(self, api_key):
        return {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

    def _resolve_media(self, value):
        """Resolve a param value to a URL / data URI / asset URI, or None.

        Media upload fields store ``{"url": ..., "local_path": ...}``.
        Prefer the hosted URL; fall back to base64-encoding the local file
        (Ark accepts data URIs). Plain strings pass through, so users can
        supply ``asset://<asset_id>`` URIs directly.
        """
        if not value:
            return None
        if isinstance(value, str):
            try:
                obj = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
            if not isinstance(obj, dict):
                return value
            value = obj
        if isinstance(value, dict):
            url = value.get('url')
            if url:
                return url
            local_path = value.get('local_path')
            if local_path and os.path.exists(local_path):
                return self._file_to_data_uri(local_path)
        return None

    def _file_to_data_uri(self, file_path):
        mime, _ = mimetypes.guess_type(file_path)
        mime = mime or 'application/octet-stream'
        with open(file_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        return f'data:{mime};base64,{b64}'

    async def run_model(self, model_obj, **kwargs):
        """Submit a Seedance video generation task and return request_id.

        Returns
        -------
        generator
            Yields JSON string with request_id.
        """
        from gui import system
        model_obj = convert_model_json_to_obj(model_obj)
        model_s_params = system.manager.models.get_model(model_obj)
        model_obj['model_params'] = {
            **model_obj.get('model_params', {}),
            **model_s_params,
        }
        model_name = model_obj['_model_name']

        api_key = model_obj['model_params'].get('api_key') or self._get_api_key()
        if not api_key or api_key == 'NA':
            raise ValueError("Seedance API key not set (ARK_API_KEY)")

        params = {
            k: v for k, v in model_obj.get('model_params', {}).items()
            if k not in ('api_key', 'api_base')
        }

        content = []
        prompt = params.pop('prompt', '')
        if prompt:
            content.append({'type': 'text', 'text': prompt})

        real_human_asset = params.pop('real_human_asset', None)
        if real_human_asset:
            asset_uri = real_human_asset.strip()
            if not asset_uri.startswith('asset://'):
                asset_uri = f'asset://{asset_uri}'
            content.append({
                'type': 'image_url',
                'image_url': {'url': asset_uri},
                'role': 'reference_image',
            })

        single_roles = {
            'first_frame': ('image_url', 'first_frame'),
            'last_frame': ('image_url', 'last_frame'),
            'reference_video': ('video_url', 'reference_video'),
            'reference_audio': ('audio_url', 'reference_audio'),
        }
        for key, (item_type, role) in single_roles.items():
            url = self._resolve_media(params.pop(key, None))
            if url:
                content.append({
                    'type': item_type,
                    item_type: {'url': url},
                    'role': role,
                })

        ref_images = params.pop('reference_images', None)
        if ref_images:
            if isinstance(ref_images, str):
                try:
                    ref_images = json.loads(ref_images)
                except (json.JSONDecodeError, TypeError):
                    ref_images = [ref_images]
            for item in ref_images or []:
                url = self._resolve_media(item)
                if url:
                    content.append({
                        'type': 'image_url',
                        'image_url': {'url': url},
                        'role': 'reference_image',
                    })

        body = {
            'model': model_name,
            'content': content,
            **{k: v for k, v in params.items() if k in self.CONTROL_PARAMS and v is not None},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{self.BASE_URL}/contents/generations/tasks',
                headers=self._headers(api_key),
                json=body,
            ) as response:
                data = await response.json()
                if not response.ok:
                    err = data.get('error', {}).get('message', str(data))
                    if 'real person' in err.lower():
                        err = f"{err}\n\n{VERIFY_HELP}"
                    raise ValueError(
                        f"Seedance API error "
                        f"({response.status}): {err}")

        task_id = data['id']

        def request_id_generator():
            yield json.dumps({
                'request_id': task_id,
                'model_name': model_name,
                'provider': 'seedance',
                'status': 'queued',
            })

        return request_id_generator()

    async def _get_task(self, request_id):
        api_key = self._get_api_key()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.BASE_URL}/contents/generations/tasks/{request_id}',
                headers=self._headers(api_key),
            ) as response:
                response.raise_for_status()
                return await response.json()

    async def get_request_status(self, model_name, request_id):
        """Return normalized status dict for a queued request."""
        data = await self._get_task(request_id)
        status = data.get('status', 'unknown')
        return {
            'status': self.STATUS_MAP.get(status, 'unknown'),
            'position': None,
        }

    async def get_request_result(self, model_name, request_id):
        """Return a list of media URLs for a completed request."""
        data = await self._get_task(request_id)
        video_url = data.get('content', {}).get('video_url')
        return [video_url] if video_url else []

    async def upload_file(self, file_path):
        """Ark has no upload endpoint; inline the file as a data URI."""
        return self._file_to_data_uri(file_path)

    # ------------------------------------------------------------------
    # Model sync
    # ------------------------------------------------------------------

    INPUT_SCHEMA = [
        {
            'key': 'prompt',
            'text': 'Prompt',
            'type': 'text',
            'default': '',
            'num_lines': 2,
            'stretch_x': True,
            'stretch_y': True,
            'label_position': 'top',
            'wrap_text': True,
            'tooltip': "Text prompt describing the video. Reference inputs "
                       "positionally, e.g. 'the person in Image 1'.",
        },
        {
            'key': 'real_human_asset',
            'text': 'Real human asset',
            'type': 'text',
            'default': '',
            'has_toggle': True,
            'tooltip': "Verified asset ID of a real person "
                       "(asset://<asset_id> or bare ID). Obtain it in the "
                       "ModelArk console: Model Playground > Asset library > "
                       "add real-human asset — the person scans a QR code "
                       "and completes facial verification. Raw photos of "
                       "real people are rejected by the API.",
        },
        {
            'key': 'first_frame',
            'text': 'First frame',
            'type': 'media_upload',
            'default': None,
            'has_toggle': True,
        },
        {
            'key': 'last_frame',
            'text': 'Last frame',
            'type': 'media_upload',
            'default': None,
            'has_toggle': True,
        },
        {
            'key': 'reference_images',
            'text': 'Reference images',
            'type': 'list',
            'of_type': 'media_upload',
            'default': None,
            'has_toggle': True,
            'label_position': 'top',
            'tooltip': 'Up to 9 character/style reference images.',
        },
        {
            'key': 'reference_video',
            'text': 'Reference video',
            'type': 'media_upload',
            'default': None,
            'has_toggle': True,
        },
        {
            'key': 'reference_audio',
            'text': 'Reference audio',
            'type': 'media_upload',
            'default': None,
            'has_toggle': True,
        },
        {
            'key': 'resolution',
            'text': 'Resolution',
            'type': ('480p', '720p', '1080p'),
            'default': '720p',
        },
        {
            'key': 'ratio',
            'text': 'Ratio',
            'type': ('adaptive', '21:9', '16:9', '4:3', '1:1', '3:4', '9:16'),
            'default': 'adaptive',
        },
        {
            'key': 'duration',
            'text': 'Duration',
            'type': 'integer',
            'default': 5,
            'minimum': 4,
            'maximum': 15,
        },
        {
            'key': 'generate_audio',
            'text': 'Generate audio',
            'type': 'boolean',
            'default': True,
        },
        {
            'key': 'watermark',
            'text': 'Watermark',
            'type': 'boolean',
            'default': False,
        },
    ]

    MODELS = {
        'seedance-2.0': 'dreamina-seedance-2-0-260128',
        'seedance-2.0-fast': 'dreamina-seedance-2-0-fast-260128',
    }

    def sync_models(self):
        """Store the Seedance 2.0 models in the DB (no list endpoint)."""
        reset_table(
            table_name='apis',
            item_configs={
                (('name', 'Seedance'),): {}
            },
            delete_existing=False,
        )
        api_id = sql.get_scalar(
            "SELECT id FROM apis WHERE LOWER(name) = 'seedance'"
        )

        metadata = json.dumps({'input_schema': self.INPUT_SCHEMA})
        all_models = {
            (
                ('name', display_name),
                ('kind', 'VIDEO'),
                ('api_id', api_id),
                ('metadata', metadata),
                ('provider_plugin', 'seedance'),
            ): {
                '_model_name': model_id,
            }
            for display_name, model_id in self.MODELS.items()
        }
        reset_table(
            table_name='models',
            item_configs=all_models,
            delete_existing=False,
            match_on=('name', 'api_id'),
        )
