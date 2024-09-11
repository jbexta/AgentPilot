# import json
# from src.utils import sql
#
#
# class WorkspaceManager:
#     def __init__(self, parent):
#         self.parent = parent
#         self.workspaces = {}
#
#     def load(self):
#         self.workspaces = sql.get_results("""
#             SELECT
#                 name,
#                 config
#             FROM blocks""", return_type='dict')
#         self.workspaces = {k: json.loads(v) for k, v in self.workspaces.items()}
#
#     def to_dict(self):
#         return self.workspaces