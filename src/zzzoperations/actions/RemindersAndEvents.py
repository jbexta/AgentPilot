from src.zzzoperations.action import BaseAction, ActionInput, ActionSuccess

# VIEW REMIINDERS AND EVENTS
# DELETE OR CANCEL REMINDER OR EVENT
# EDIT REMINDER OR EVENT


class Set_Reminder(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='set a reminder to buy milk')
        self.desc_prefix = 'requires me to'
        self.desc = 'Set a reminder'
        self.inputs.add('when_to_remind', time_based=True)
        self.inputs.add('name_of_reminder')

    def run_action(self):
        # when_to_time_expression()
        yield ActionSuccess("[SAY]Reminder has been set for ??")
