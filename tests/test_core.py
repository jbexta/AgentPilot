# import src as ap
#
# session = AgentPilot()
# workflow = ap.Workflow(
#     chat_title='Test Workflow',
#     kind='CHAT',  # default is 'CHAT'
#     params={'key': 'value'},  # default is None
# )  # ap.Workflow()
#
# # self.main = kwargs.get('main')
# # self.workflow = kwargs.get('workflow', None)
# # self.config: Dict[str, Any] = kwargs.get('config', {})
# #
# # self.member_id: str = kwargs.get('member_id', '1')
# # self.loc_x: int = kwargs.get('loc_x', 0)
# # self.loc_y: int = kwargs.get('loc_y', 0)
# # self.inputs: List[Dict[str, Any]] = kwargs.get('inputs', [])
#
# agent_1 = ap.Agent(
#     name='Agent 1',
#     kind='AGENT',
#     config={
#         'info.name': 'Agent 1',
#         'info.description': 'This is Agent 1',
#         'info.role': 'Assistant',
#         'info.language': 'English',
#         'info.output_placeholder': 'agent_1_output',
#         # 'group.output_placeholder': 'agent_1_output',
#         # '_TYPE': 'workflow'
#     }, # default is None
#     workflow=workflow,
# )
