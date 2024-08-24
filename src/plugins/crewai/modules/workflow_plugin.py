# import asyncio
#
# from src.gui.config import ConfigFields
# from members.workflow import WorkflowBehaviour
# from plugins.crewai.src.crew import Crew
#
#
# class CrewAI_Workflow(WorkflowBehaviour):
#     def __init__(self, workflow):
#         super().__init__(workflow=workflow)
#         self.group_key = 'crewai'
#         self.crew = None
#         self.crew_routine = None
#
#     def start(self, from_member_id=None):
#         try:
#             self.crew_routine = self.workflow.loop.create_task(self.run_crew())
#             self.workflow.loop.run_until_complete(self.crew_routine)
#         except Exception as e:
#             raise e
#
#     def stop(self):
#         # """Disable the default stop method"""
#         self.workflow.stop_requested = True
#         if self.crew_routine is not None:
#             self.crew_routine.cancel()
#
#             self.crew_routine = None
#
#         # for member in self.context.members.values():
#         #     if member.response_task is not None:
#         #         member.response_task.cancel()
#
#     async def run_crew(self):
#         agents = [member.agent_object for member in self.workflow.members.values()]
#         tasks = [member.agent_task for member in self.workflow.members.values()]
#         self.crew = Crew(agents=agents, tasks=tasks)  # , step_callback=self.step_callback)
#         self.crew.kickoff()
#
#     def step_callback(self, callback_object):
#         pass
#
#
# class CrewAI_WorkflowConfig(ConfigFields):
#     def __init__(self, parent):
#         super().__init__(parent=parent)
#         self.parent = parent
#         # self.label_width = 125
#         # self.margin_left = 20
#
#         # self.runnable = self.RegisterRunnable(self)
#         self.schema = [
#             {
#                 'text': 'Process',
#                 'type': ('Sequential', 'Hierarchical',),
#                 'default': 'Sequential',
#                 'width': 125,
#             },
#         ]
