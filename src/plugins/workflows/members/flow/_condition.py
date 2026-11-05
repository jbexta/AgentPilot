"""Condition Flow Member Module.

Evaluates a CEL expression and sets condition_passed on the member,
allowing downstream routing based on the result.
"""

from plugins.workflows.members import Member
from plugins.workflows.utils.conditions import (
    build_condition_context,
    evaluate_condition,
)
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='condition_settings')
class Condition(Member):
    default_avatar = ':/resources/icon-condition.png'
    default_name = 'Condition'
    workflow_insert_mode = 'single'
    OUTPUT = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def run(self):
        expression = self.config.get('expression', 'true')
        ctx = build_condition_context(self.workflow)
        result = evaluate_condition(expression, ctx)
        self.condition_passed = result
        msg = f'Condition: {result}'
        self.workflow.save_message(
            'sys', msg, self.full_member_id(),
        )
        yield 'SYS', msg
