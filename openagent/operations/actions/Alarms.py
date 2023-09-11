from openagent.operations.action import BaseAction, ActionInput, ActionResult


# from utils import goto


class Set_Alarm(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='set an alarm in 6 minutes')
        self.desc_prefix = 'requires me to'
        self.desc = 'Set an alarm'
        self.inputs.add('time-of-alarm-in-24h', time_based=True)

    def run_action(self):
        yield ActionResult("[SAY]Alarm has been set for ??")


class View_Alarms(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='what time will that alarm go off')
        self.desc_prefix = 'Asked about '
        self.desc = 'Information on currently set alarms'

    def run_action(self):
        yield ActionResult("""[ANS]Active Alarms:
Alarm  |  Time
---------------
1      |  09:00 am (in 18 hours)
2      |  16:00 pm (in 1 hour)""")


class DeleteOrCancel_Alarm(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='delete that alarm')
        self.desc_prefix = 'requires me to'
        self.desc = 'Delete/Cancel an alarm'
        self.inputs.add('alarm(s)_to_delete', format='x,y,z')
        d = 1

    def run_action(self):  # , bypass_confirmation=False): INSTEAD OF THIS, ACTION GETS PAUSED WHEN DIALOG QUESTION, IF NO PAUSES RUNS TO EXECUTION
        print('RUN ACTION')
        dialog_result = None
        if self.agent.task_worker.active_question():
            dialog_result = self.agent.active_question().answer

        if dialog_result is None:
            yield ActionResult("[Q]Are you sure you want to delete your alarm in 4 minutes?")

        if dialog_result == 'YES':
            yield ActionResult("[SAY]Alarm in 4 minutes deleted")

        # self.agent.task_worker.active_dialog = None
