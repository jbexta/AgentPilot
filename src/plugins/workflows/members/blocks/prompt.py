"""Prompt Block Member Module.

This module provides the PromptBlock member, an AI-powered block that processes
text prompts through language models to generate intelligent responses. Prompt
blocks serve as the core building blocks for AI interactions within workflows,
enabling sophisticated text generation, reasoning, and conversational capabilities.

Key Features:
- AI language model integration and prompt processing
- Configurable model selection and parameters
- Dynamic prompt generation and templating
- Integration with the LLM member framework
- Message handling and conversation context management
- Structured and unstructured text generation
- Support for various AI model providers
- Workflow integration and parameter passing

Prompt blocks enable users to create intelligent workflows that leverage
large language models for text generation, analysis, and reasoning tasks.
"""

from typing import Any

from plugins.workflows.members import LlmMember
from utils.helpers import set_module_type


@set_module_type(module_type='Members', plugin='BLOCK', settings='prompt_settings')
class Prompt(LlmMember):
    default_role = 'block'
    default_avatar = ':/resources/icon-brain.png'
    default_name = 'Prompt'
    workflow_insert_mode = 'list'
    OUTPUT = str

    @property
    def INPUTS(self):
        return {
            'CONFIG': {
                'data': str,
            },
        }

    def __init__(self, **kwargs):
        super().__init__(model_config_key='prompt_model', **kwargs)

    async def get_messages(self):  # todo
        return [{'role': 'user', 'content': await self.get_content()}]