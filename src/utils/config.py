# from pydantic import BaseModel, TypeAdapter
# from typing import Literal, Union, Dict, Any, List, Optional
#
# # Configuration for "user" type, allowing arbitrary extra fields
# class UserConfig(BaseModel):
#     _TYPE: Literal['user']
#
#     class Config:
#         extra = 'allow'  # Permits additional fields beyond _TYPE
#
# # Configuration for "agent" type, allowing arbitrary extra fields
# class AgentConfig(BaseModel):
#     _TYPE: Literal['agent']
#
#     class Config:
#         extra = 'allow'  # Permits additional fields beyond _TYPE
#
# # Member model, used within WorkflowConfig
# class MemberConfig(BaseModel):
#     config: Union[UserConfig, AgentConfig, 'WorkflowConfig']  # Forward reference to WorkflowConfig
#     id: str
#     linked_id: Optional[str]  # Can be null in JSON, so Optional[str] allows None
#     loc_x: int
#     loc_y: int
#
# # Configuration for "workflow" type, with specific fields
# class WorkflowConfig(BaseModel):
#     _TYPE: Literal['workflow']
#     options: Dict[str, Any]  # Arbitrary fields within options
#     inputs: List[Any]  # Type unspecified in example; using Any for flexibility
#     members: List[MemberConfig]  # List of members, enabling nesting
#     params: List[Any]  # Type unspecified in example; using Any for flexibility
#
# # Define Config as a union type for clarity (optional, but useful for type hints)
# AnyConfig = Union[UserConfig, AgentConfig, WorkflowConfig]
#
# class ConfigDictWrapper:
#     """Wrapper for Pydantic models to support both attribute and dict-like access with validation."""
#     def __init__(self, model: AnyConfig):
#         self._model = model
#         self._adapter = TypeAdapter(type(model))
#
#     @property
#     def model(self) -> AnyConfig:
#         return self._model
#
#     def __getattr__(self, name: str) -> Any:
#         """Delegate attribute access to the Pydantic model."""
#         if hasattr(self._model, name):
#             value = getattr(self._model, name)
#             if isinstance(value, (UserConfig, AgentConfig, WorkflowConfig)):
#                 return ConfigDictWrapper(value)
#             if isinstance(value, list) and value and isinstance(value[0], (UserConfig, AgentConfig, WorkflowConfig, MemberConfig)):
#                 return [ConfigDictWrapper(item) if isinstance(item, (UserConfig, AgentConfig, WorkflowConfig)) else item for item in value]
#             return value
#         raise AttributeError(f"'{self._model.__class__.__name__}' has no attribute '{name}'")
#
#     def __setattr__(self, name: str, value: Any):
#         """Handle setting attributes with validation."""
#         if name in ('_model', '_adapter'):
#             super().__setattr__(name, value)
#         else:
#             if hasattr(self._model, name):
#                 current_value = getattr(self._model, name)
#                 if isinstance(current_value, (UserConfig, AgentConfig, WorkflowConfig)) and isinstance(value, dict):
#                     value = TypeAdapter(type(current_value)).validate_python(value)
#                 elif isinstance(current_value, list) and value and isinstance(value[0], dict):
#                     item_type = type(current_value[0]) if current_value else AnyConfig
#                     value = [TypeAdapter(item_type).validate_python(item) for item in value]
#                 setattr(self._model, name, value)
#             else:
#                 if getattr(self._model.__class__.Config, 'extra', None) == 'allow':
#                     self._model.__dict__[name] = value
#                 else:
#                     raise AttributeError(f"Cannot set attribute '{name}' on '{self._model.__class__.__name__}'")
#
#     def __getitem__(self, key: str) -> Any:
#         """Support dict-like access."""
#         return self.__getattr__(key)
#
#     def __setitem__(self, key: str, value: Any):
#         """Support dict-like setting with validation."""
#         self.__setattr__(key, value)
#
#     def __contains__(self, key: str) -> bool:
#         return hasattr(self._model, key) or key in self._model.__dict__
#
#     def get(self, key: str, default: Any = None) -> Any:
#         try:
#             return self[key]
#         except (AttributeError, KeyError):
#             return default
#
#     def to_dict(self) -> Dict[str, Any]:
#         return self._model.model_dump()
#
#     @classmethod
#     def from_dict(cls, data: Dict[str, Any]) -> 'ConfigDictWrapper':
#         adapter = TypeAdapter(AnyConfig)
#         model = adapter.validate_python(data)
#         return cls(model)
#
#     @classmethod
#     def from_json(cls, json_str: str) -> 'ConfigDictWrapper':
#         adapter = TypeAdapter(AnyConfig)
#         model = adapter.validate_json(json_str)
#         return cls(model)
#
# data = {
#     "_TYPE": "workflow",
#     "options": {"foo": "bar"},
#     "inputs": [],
#     "members": [
#         {
#             "config": {
#                 "_TYPE": "user",
#                 "name": "Alice"
#             },
#             "id": "1",
#             "linked_id": None,
#             "loc_x": 20,
#             "loc_y": 64
#         },
#         {
#             "config": {
#                 "_TYPE": "agent",
#                 "name": "assistant"
#             },
#             "id": "2",
#             "linked_id": None,
#             "loc_x": 100,
#             "loc_y": 80
#         },
#         {
#             "config": {
#                 "_TYPE": "workflow",
#                 "options": {"foo": "baz"},
#                 "inputs": [],
#                 "members": [
#                     {
#                         "config": {
#                             "_TYPE": "user",
#                             "name": "Bob"
#                         },
#                         "id": "1",
#                         "linked_id": None,
#                         "loc_x": 20,
#                         "loc_y": 64
#                     }
#                 ],
#                 "params": []
#             },
#             "id": "3",
#             "linked_id": None,
#             "loc_x": 200,
#             "loc_y": 120
#         }
#     ],
#     "params": []
# }
#
# def test_config():
#     # # Validate and parse the data
#     # adapter = TypeAdapter(Config)
#     # config = adapter.validate_python(data)
#     #
#     # # Access the parsed object
#     # # print(config)
#     # pretty_config = config.model_dump_json(indent=2, exclude_none=True)
#     # print(pretty_config)
#
#     # VALIDATE IT'S A WORKFLOW
#     adapter = TypeAdapter(WorkflowConfig)
#     workflow = adapter.validate_python(data)
#     # Access the parsed object
#     pretty_workflow = workflow.model_dump_json(indent=2, exclude_none=True)
#     print(pretty_workflow)
#
# # ==============================================================================
# # Example Usage
# # ==============================================================================
#
# # # Your example JSON configuration as a string.
# # json_data = """
# # {
# #     "TYPE": "workflow",
# #     "options": {
# #         "autorun": true,
# #         "show_hidden_bubbles": false,
# #         "show_nested_bubbles": false
# #     },
# #     "inputs": [],
# #     "members": [
# #         {
# #             "config": {
# #                 "TYPE": "user"
# #             },
# #             "id": "1",
# #             "linked_id": null,
# #             "loc_x": 20,
# #             "loc_y": 64
# #         },
# #         {
# #             "config": {
# #                 "TYPE": "agent",
# #                 "chat.display_markdown": true,
# #                 "chat.model": {
# #                     "kind": "CHAT",
# #                     "model_name": "claude-3-5-sonnet-20240620",
# #                     "model_params": {
# #                         "structure.data": [
# #                             {
# #                                 "attribute": "description",
# #                                 "req": true,
# #                                 "type": "str"
# #                             },
# #                             {
# #                                 "attribute": "system_message",
# #                                 "req": true,
# #                                 "type": "str"
# #                             }
# #                         ]
# #                     },
# #                     "provider": "litellm"
# #                 },
# #                 "chat.preload.data": [],
# #                 "chat.sys_msg": "",
# #                 "id": null,
# #                 "info.avatar_path": "",
# #                 "info.name": "Assistantttt",
# #                 "tool": null
# #             },
# #             "id": "2",
# #             "linked_id": null,
# #             "loc_x": 100,
# #             "loc_y": 80
# #         },
# #         {
# #             "config": {
# #                 "TYPE": "workflow",
# #                 "options": {
# #                     "autorun": true,
# #                     "show_hidden_bubbles": false,
# #                     "show_nested_bubbles": false
# #                 },
# #                 "inputs": [],
# #                 "members": [
# #                     {
# #                         "config": {
# #                             "TYPE": "user"
# #                         },
# #                         "id": "1",
# #                         "linked_id": null,
# #                         "loc_x": 20,
# #                         "loc_y": 64
# #                     },
# #                     {
# #                         "config": {
# #                             "TYPE": "agent",
# #                             "chat.display_markdown": true,
# #                             "chat.model": {
# #                                 "kind": "CHAT",
# #                                 "model_name": "claude-3-5-sonnet-20240620",
# #                                 "model_params": {
# #                                     "structure.data": [
# #                                         {
# #                                             "attribute": "description",
# #                                             "req": true,
# #                                             "type": "str"
# #                                         },
# #                                         {
# #                                             "attribute": "system_message",
# #                                             "req": true,
# #                                             "type": "str"
# #                                         }
# #                                     ]
# #                                 },
# #                                 "provider": "litellm"
# #                             },
# #                             "chat.preload.data": [],
# #                             "chat.sys_msg": "",
# #                             "id": null,
# #                             "info.avatar_path": "",
# #                             "info.name": "Assistantttt",
# #                             "tool": null
# #                         },
# #                         "id": "2",
# #                         "linked_id": null,
# #                         "loc_x": 100,
# #                         "loc_y": 80
# #                     },
# #                     {
# #                         "config": {
# #                             "TYPE": "workflow",
# #                             "autorun": false
# #                         },
# #                         "id": "3",
# #                         "linked_id": null,
# #                         "loc_x": 200,
# #                         "loc_y": 120
# #                     }
# #                 ],
# #                 "params": []
# #             },
# #             "id": "3",
# #             "linked_id": null,
# #             "loc_x": 200,
# #             "loc_y": 120
# #         }
# #     ],
# #     "params": []
# # }
# # """
# # from pydantic import ValidationError
# # import pytest
# #
# #
# # def test_config(json_config):
# #     try:
# #         # Parse the JSON config into the Workflow model
# #         workflow = Workflow.model_validate(json_config)
# #
# #         # Verify top-level structure
# #         assert workflow.TYPE == "workflow"
# #         assert isinstance(workflow.options, dict)
# #         assert isinstance(workflow.inputs, list)
# #         assert isinstance(workflow.params, list)
# #         assert len(workflow.members) == 3, "Expected 3 members in top-level workflow"
# #
# #         # Verify first member (user)
# #         assert workflow.members[0].config.TYPE == "user"
# #         assert workflow.members[0].id == "1"
# #         assert workflow.members[0].linked_id is None
# #         assert workflow.members[0].loc_x == 20
# #         assert workflow.members[0].loc_y == 64
# #
# #         # Verify second member (agent)
# #         assert workflow.members[1].config.TYPE == "agent"
# #         assert workflow.members[1].id == "2"
# #         assert workflow.members[1].linked_id is None
# #         assert workflow.members[1].loc_x == 100
# #         assert workflow.members[1].loc_y == 80
# #
# #         # Verify third member (nested workflow)
# #         assert workflow.members[2].config.TYPE == "workflow"
# #         assert workflow.members[2].id == "3"
# #         assert workflow.members[2].linked_id is None
# #         assert workflow.members[2].loc_x == 200
# #         assert workflow.members[2].loc_y == 120
# #
# #         # Verify nested workflow members
# #         nested_workflow = workflow.members[2].config
# #         assert len(nested_workflow.members) == 2, "Expected 2 members in nested workflow"
# #         assert nested_workflow.members[0].config.TYPE == "user"
# #         assert nested_workflow.members[1].config.TYPE == "agent"
# #
# #     except ValidationError as e:
# #         pytest.fail(f"Validation failed: {e}")