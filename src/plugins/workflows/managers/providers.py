
from abc import abstractmethod

from typing_extensions import override

from gui import system
from utils.helpers import set_module_type
from utils.helpers import BaseManager


@set_module_type(module_type='Managers')
class ProviderManager(BaseManager):
    def __init__(self, system, **kwargs):
        super().__init__(system, **kwargs)

    @override
    def load(self):
        provider_classes = system.manager.modules.get_modules_in_folder(
            module_type='Providers',
            fetch_keys=('name', 'class',),
        )
        for name, provider_class in provider_classes:
            if name not in self:
                self[name] = provider_class(self)
    #     return

    #     model_res = sql.get_results("""
    #         SELECT
    #             CASE
    #                 WHEN json_extract(a.config, '$.litellm_prefix') != '' THEN
    #                     json_extract(a.config, '$.litellm_prefix') || '/' || json_extract(m.config, '$.model_name')
    #                 ELSE
    #                     json_extract(m.config, '$.model_name')
    #             END AS model_name,
    #             m.name AS alias,
    #             m.config AS model_config,
    #             a.config AS api_config,
    #             a.provider_plugin AS provider,
    #             m.kind,
    #             m.api_id,
    #             a.name AS api_name,
    #             COALESCE(a.api_key, '')
    #         FROM models m
    #         LEFT JOIN apis a 
    #             ON m.api_id = a.id""")
    #     for model_name, alias, model_config, api_config, provider, kind, api_id, api_name, api_key in model_res:
    #         if provider is None:
    #             print(f"Skipping model '{model_name}' with no provider.")
    #             continue
    #         if provider not in self:
    #             provider_class = system.manager.modules.get_module_class(
    #                 module_type='Providers',
    #                 module_name=provider,
    #             )
    #             if not provider_class:
    #                 continue
    #             provider_obj = provider_class(self, api_id=api_id)
    #             self[provider] = provider_obj

    #         self[provider].insert_model(model_name, alias, model_config, kind, api_id, api_name, api_config, api_key)

    #         if api_name.lower() == 'openai':
    #             self[provider].visible_tabs = ['Chat', 'Speech']
    #         if api_name.lower() == 'elevenlabs':
    #             pass

    # def get_model(self, model_obj):  # provider, model_name):
    #     model_obj = convert_model_json_to_obj(model_obj)
    #     model_provider = self.get(model_obj.get('provider'))
    #     if not model_provider:
    #         return None
    #     return model_provider.get_model(model_obj)

    # async def run_model(self, model_obj, **kwargs):
    #     model_obj = convert_model_json_to_obj(model_obj)
    #     provider = self.get(model_obj['provider'])
    #     if provider is None:
    #         raise ValueError(f"Provider '{model_obj['provider']}' not found.")
    #     rr = await provider.run_model(model_obj, **kwargs)
    #     return rr

    # async def get_structured_output(self, model_obj, **kwargs):
    #     model_obj = convert_model_json_to_obj(model_obj)
    #     provider = self.get(model_obj['provider'])
    #     if provider is None:
    #         raise ValueError(f"Provider '{model_obj['provider']}' not found.")
    #     if not hasattr(provider, 'get_structured_output'):
    #         return None
    #     return await provider.get_structured_output(model_obj, **kwargs)

    # def get_model_parameters(self, model_obj, incl_api_data=True):
    #     model_obj = convert_model_json_to_obj(model_obj)
    #     model_provider = self.get(model_obj.get('provider'))
    #     if not model_provider:
    #         return {}
    #     return model_provider.get_model_parameters(model_obj, incl_api_data)

    # # async def get_scalar(self, prompt, single_line=False, num_lines=0, model_obj=None):
    # #     model_obj = convert_model_json_to_obj(model_obj)
    # #     provider = self.get(model_obj['provider'])
    # #     if provider is None:
    # #         raise ValueError(f"Provider '{model_obj['provider']}' not found.")
    # #     if not hasattr(provider, 'get_scalar'):
    # #         return None
    # #     return provider.get_scalar(prompt, single_line, num_lines, model_obj)


class Provider:
    OPENAPI_TYPE_MAP = {
        'string': 'text',
        'boolean': 'boolean',
        'integer': 'integer',
        'number': 'float',
        'array': 'list',
        'media_upload': 'media_upload',
    }

    def __init__(self, parent):
        self.parent = parent

    @abstractmethod
    async def run_model(self, model_obj, **kwargs):
        pass

    async def get_request_status(self, model_name, request_id):
        """Return normalized status dict for a queued request.

        Returns
        -------
        dict
            One of:
            ``{'status': 'queued', 'position': int|None}``
            ``{'status': 'in_progress'}``
            ``{'status': 'completed'}``
        """
        raise NotImplementedError

    async def get_request_result(self, model_name, request_id):
        """Return a list of media URLs for a completed request.

        Returns
        -------
        list[str]
            Downloadable media URLs.
        """
        raise NotImplementedError
    
    def convert_all_openapi_properties(self, properties, property_order=None, required_fields=None):
        if property_order is not None:
            properties = {
                **{k: properties[k] for k in property_order if k in properties},
                **properties
            }
        
        if not getattr(self, 'resolve_schema', None):
            raise NotImplementedError(f"resolve_schema() method not implemented in {self.__class__.__name__}")
        
        input_schema = []
        last_property = {}
        row_key_counter = 0
        for property_name, raw_property_data in properties.items():
            property_data, allow_none = self.resolve_schema(raw_property_data)
            new_property = self.convert_openapi_property(
                property_name, property_data,
                raw_property_data=raw_property_data,
                allow_none=allow_none,
            )

            if required_fields is not None:
                has_toggle = property_name not in required_fields
                new_property['has_toggle'] = has_toggle

            if new_property.get('stretch_x') and new_property.get('stretch_y'):
                if last_property.get('stretch_x') and last_property.get('stretch_y'):
                    input_schema[-1]['row_key'] = row_key_counter
                    new_property['row_key'] = row_key_counter
                    row_key_counter += 1

            last_property = new_property
            input_schema.append(new_property)
        
        return input_schema


    
    def convert_openapi_property(self, property_name, property_data,
                                 raw_property_data=None,
                                 allow_none=False):
        """Convert an OpenAPI schema property to internal schema format.

        Parameters
        ----------
        property_name : str
            The property key name.
        property_data : dict
            The resolved schema dict (after resolve_schema).
        raw_property_data : dict, optional
            The original unresolved schema dict for default/description
            fallback. Defaults to property_data if None.
        allow_none : bool
            Whether the field is nullable.

        Returns
        -------
        dict
            A property dict ready for input_schema.
        """
        if raw_property_data is None:
            raw_property_data = property_data

        default_val = raw_property_data.get(
            'default', property_data.get('default')
        )

        prop_type = property_data.get('type', 'string')
        if prop_type not in self.OPENAPI_TYPE_MAP:
            print(
                f"Warning: Unknown type '{prop_type}' for "
                f"{property_name}. Defaulting to text."
            )
            property_type = 'text'
        else:
            property_type = self.OPENAPI_TYPE_MAP[prop_type]

        # Detect media upload: URI format (Replicate pattern)
        prop_format = property_data.get('format', '')
        if prop_type == 'string' and prop_format == 'uri':
            property_type = 'media_upload'

        # Detect media upload: title-based (Fal/Wavespeed pattern)
        title = property_data.get('title', property_name)
        media_names = {
            'image', 'video', 'audio',
            'image_url', 'video_url', 'audio_url',
        }
        url_media_names = {n for n in media_names if n.endswith('_url')}
        c_title = title.replace(' ', '_').lower()
        if c_title in media_names:
            property_type = 'media_upload'
        elif c_title.endswith('_url') and any(
            mt in c_title for mt in url_media_names
        ):
            property_type = 'media_upload'

        enum = property_data.get('enum')
        if enum:
            property_type = tuple(enum)

        if default_val is None and property_type == 'text':
            default_val = ''

        # Strip trailing ' url' / ' urls' from title
        for suffix in ('url', 'urls'):
            if title.lower().endswith(f' {suffix}'):
                title = title[:-len(suffix) - 1]

        new_property = {
            'key': property_name,
            'text': title,
            'type': property_type,
            'default': default_val,
        }

        desc = (raw_property_data.get('description')
                or property_data.get('description'))
        if desc:
            new_property['tooltip'] = desc

        if allow_none or property_data.get('nullable'):
            new_property['has_toggle'] = True

        if property_type == 'text':
            is_prompt = 'prompt' in property_name.lower()
            is_lyrics = property_name.lower() == 'lyrics'
            if is_prompt or is_lyrics:
                new_property['num_lines'] = 2
                new_property['stretch_x'] = True
                new_property['stretch_y'] = True
                new_property['label_position'] = 'top'
                new_property['highlighter'] = 'xml'
                new_property['fold_mode'] = 'xml'
                new_property['format_blocks'] = True
                if is_prompt:
                    new_property['wrap_text'] = True

        elif property_type == 'list':
            of_type = property_data.get(
                'items', {}
            ).get('type', 'string')
            if ' urls' in property_data.get('title', '').lower():
                of_type = 'media_upload'
            new_property['of_type'] = self.OPENAPI_TYPE_MAP.get(
                of_type, 'text'
            )

        elif property_type in ('integer', 'float'):
            if property_type == 'integer':
                default_min = -2147483648
                default_max = 2147483647
            else:
                default_min = -3.402823466e+38
                default_max = 3.402823466e+38
            new_property['minimum'] = property_data.get(
                'minimum', default_min
            )
            new_property['maximum'] = property_data.get(
                'maximum', default_max
            )

        return new_property



    # def sync_chat(self):
    #     """Implement this method to show sync button for chat models"""
    #     pass

    # class ChatConfig(ConfigFields):
    #     """Implement this method to show custom config tab in chat tab"""
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.schema = []

    # class ChatModelParameters(ConfigFields):
    #     """Implement this method to show custom parameters for chat models"""
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.schema = []

