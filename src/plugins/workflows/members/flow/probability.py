"""Probability Flow Member Module.

Rolls against a user-configured percentage (0-100) and yields
a pass/fail system message, introducing randomness into workflows.
Supports Uniform (flat chance) and Gaussian (bell curve) modes.
"""

import random

from plugins.workflows.members import Member
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='probability_settings')
class Probability(Member):
    default_avatar = ':/resources/icon-probability.png'
    default_name = 'Probability'
    workflow_insert_mode = 'single'
    OUTPUT = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def run(self):
        mode = self.config.get('mode', 'Uniform')
        roll = random.randint(1, 100)

        if mode == 'Gaussian':
            mean = self.config.get('mean', 50)
            std_dev = self.config.get('std_dev', 15)
            effective = max(0, min(100, random.gauss(mean, std_dev)))
            passed = roll <= effective
            msg = (
                f'Probability: {passed} '
                f'(rolled {roll}, effective {effective:.1f}, '
                f'mean={mean}, std_dev={std_dev})'
            )
        else:
            probability = self.config.get('probability', 50)
            passed = roll <= probability
            msg = (
                f'Probability: {passed} '
                f'(rolled {roll}, needed <={probability})'
            )

        self.workflow.save_message(
            'sys', msg, self.full_member_id(),
        )
        yield 'SYS', msg
