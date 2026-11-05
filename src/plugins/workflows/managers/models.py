import json
import os

from PySide6.QtWidgets import QMessageBox
from typing_extensions import override

from utils.helpers import BaseManager, convert_model_json_to_obj, display_message
from utils import sql
from gui import system


LIVE_MODELS = ('gpt-live-1',)

class ModelsManager(BaseManager):
    llm_crud = False  # rows need an api_id

    def __init__(self, system):
        super().__init__(
            system,
            table_name='models',
        )
        self.model_api_ids = {}
        self.model_aliases = {}
        self.model_metadata = {}
        self.api_ids = {}

    @override
    def load(self):
        model_res = sql.get_results("""
            SELECT
                COALESCE(json_extract(m.config, '$._model_name'), json_extract(m.config, '$.model_name')) AS model_name,
                m.name AS alias,
                m.config AS model_config,
                a.config AS api_config,
                m.provider_plugin AS provider,
                m.kind,
                m.api_id,
                a.name AS api_name,
                COALESCE(a.api_key, ''),
                m.metadata
            FROM models m
            LEFT JOIN apis a
                ON m.api_id = a.id""")
        for model_name, alias, model_config, api_config, provider, kind, api_id, api_name, api_key, metadata in model_res:
            if provider is None:
                print(f"Skipping model '{model_name}' with no provider.")
                continue

            self.add_model(model_name, provider, alias, model_config, kind, api_id, api_name, api_config, api_key, metadata)

    def add_model(self, model_name, provider, alias, model_config, kind, api_id, api_name, api_config, api_key, metadata=None):
        # model_config overrides api_config
        model_config = {**json.loads(api_config), **json.loads(model_config)}
        if api_key != '':
            # model_config['api_key'] = api_key
            model_config['api_key'] = os.environ.get(api_key[1:], 'NA') if api_key.startswith('$') else api_key
        if api_id not in self.api_ids:
            self.api_ids[api_id] = api_name

        model_key = (provider, kind, model_name)
        self[model_key] = model_config
        self.model_api_ids[model_key] = api_id
        self.model_aliases[model_key] = alias
        try:
            self.model_metadata[model_key] = json.loads(metadata) if metadata else {}
        except (TypeError, json.JSONDecodeError):
            self.model_metadata[model_key] = {}

    def get_model(self, model_obj):  # provider, kind, model_name):
        provider, kind, model_name = model_obj['provider'], model_obj['kind'], model_obj['_model_name']
        model = self.get((provider, kind, model_name), None)
        if model is None:
            raise ValueError(f"Model '{model_name}' not found.")

        return model

    def is_live(self, model_obj):
        """Return True if the model is a GPT-Live (full duplex speech-to-speech) model."""
        model_obj = convert_model_json_to_obj(model_obj)
        return model_obj['_model_name'] in LIVE_MODELS

    async def run_model(self, model_obj, **kwargs):
        model_obj = convert_model_json_to_obj(model_obj)
        provider = system.manager.providers.get(model_obj['provider'])
        if provider is None:
            raise ValueError(f"Provider '{model_obj['provider']}' not found.")
        await self._refresh_stale_media(model_obj, provider)
        rr = await provider.run_model(model_obj, **kwargs)
        return rr

    async def _refresh_stale_media(self, model_obj, provider):
        """Re-upload media-upload params whose hosted URLs have expired.

        MediaUpload values are stored as ``{"url", "local_path"}`` JSON
        strings (scalar or inside lists). Provider-hosted URLs can expire
        (e.g. Replicate deletes uploaded files after ~24h); when a URL is
        no longer accessible and the original file still exists locally,
        the file is uploaded again and the fresh URL swapped in.
        """
        import asyncio
        import requests

        headers = getattr(provider, 'media_probe_headers', dict)()

        def is_dead(value):
            try:
                obj = json.loads(value) if isinstance(value, str) else None
            except (json.JSONDecodeError, TypeError):
                return False
            if not (isinstance(obj, dict)
                    and str(obj.get('url', '')).startswith('http')
                    and 'local_path' in obj):
                return False
            try:
                resp = requests.head(obj['url'], headers=headers,
                                     timeout=10, allow_redirects=True)
                if resp.status_code == 405:  # HEAD not allowed on some CDNs
                    resp = requests.get(obj['url'], headers=headers,
                                        timeout=10, stream=True)
                    resp.close()
                return resp.status_code >= 400
            except requests.RequestException:
                return True

        params = model_obj.get('model_params', {})
        dead = [v for value in params.values()
                for v in (value if isinstance(value, list) else [value])
                if await asyncio.to_thread(is_dead, v)]
        stale = [v for v in dead if os.path.isfile(json.loads(v)['local_path'])]

        missing = len(dead) - len(stale)
        if missing:
            display_message(
                f"{missing} expired media file{'s' if missing != 1 else ''} "
                f"no longer exist locally and can't be reuploaded",
                title='Media missing',
                icon='Warning',
            )

        if not stale or not hasattr(provider, 'upload_file'):
            return

        display_message(
            f"Reuploading {len(stale)} file{'s' if len(stale) != 1 else ''}",
            title='Media expired',
        )
        replacements = {}
        for v in stale:
            obj = json.loads(v)
            obj['url'] = await provider.upload_file(obj['local_path'])
            replacements[v] = json.dumps(obj)
        for key, value in params.items():
            if isinstance(value, list):
                params[key] = [replacements.get(v, v) for v in value]
            else:
                params[key] = replacements.get(value, value)
        # Persist the fresh URLs to any stored config containing the old
        # value (media values are self-contained JSON strings, so an exact
        # text replacement of their escaped form is safe).
        for old, new in replacements.items():
            old_esc = json.dumps(old)[1:-1]
            new_esc = json.dumps(new)[1:-1]
            for table in ('contexts', 'entities', 'modules'):
                sql.execute(
                    f"UPDATE {table} SET config = REPLACE(config, ?, ?)",
                    (old_esc, new_esc))

    @override
    def delete(self, key, where_field='id'):
        sql.execute("DELETE FROM models WHERE api_id = ?;", (key,))
        super().delete(key, where_field)