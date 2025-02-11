import json
import threading
from typing import List, Dict, Any

import tiktoken

from src.members.node import Node
from src.members.user import User
from src.utils import sql
from src.utils.helpers import convert_to_safe_case, try_parse_json


class Message:
    def __init__(self,
        msg_id: int,
        role: str,
        content: str,
        member_id: str = None,
        alt_turn: int = None,
        log=None
    ):
        self.id: int = msg_id
        self.role: str = role
        self.content: str = content
        self.member_id: str = member_id
        self.token_count = len(tiktoken.encoding_for_model("gpt-3.5-turbo").encode(content or ''))
        self.alt_turn: int = alt_turn
        if log is not None and not isinstance(log, str):
            log = json.dumps(log)  # todo clean
        self.log = None if not log else json.loads(log)


class MessageHistory:
    def __init__(self, workflow):
        self.thread_lock = threading.Lock()

        self.workflow = workflow
        self.branches = {}  # {branch_msg_id: [child_msg_ids]}
        self.messages: List[Message] = []  # [Message(m['id'], m['role'], m['content']) for m in (messages or [])]
        self.alt_turn_state: int = 0  # A flag to indicate if it's a new run

        self.msg_id_buffer: List[int] = []

    def load(self):
        self.messages = []
        self.workflow.leaf_id = sql.get_scalar("""
            WITH RECURSIVE leaf_contexts AS (
                SELECT 
                    c1.id
                FROM contexts c1 
                WHERE c1.id = ?
            UNION ALL
                SELECT 
                    c2.id
                FROM contexts c2 
                JOIN leaf_contexts lc ON lc.id = c2.parent_id
                WHERE c2.active = 1
                AND NOT EXISTS (
                    SELECT 1
                    FROM contexts c3
                    WHERE c3.parent_id = c2.parent_id
                    AND c3.branch_msg_id < c2.branch_msg_id
                    AND c3.active = 1
                )
            )
            SELECT id
            FROM leaf_contexts 
            ORDER BY id DESC;""", (self.workflow.context_id,))

        self.load_branches()
        self.refresh_messages()
        self.load_msg_id_buffer()

    def load_branches(self):
        root_id = self.workflow.context_id
        result = sql.get_results("""
            WITH RECURSIVE context_chain(id, parent_id, branch_msg_id) AS (
              SELECT id, parent_id, branch_msg_id
              FROM contexts
              WHERE id = ?
              UNION ALL
              SELECT c.id, c.parent_id, c.branch_msg_id
              FROM contexts c
              JOIN context_chain cc ON c.parent_id = cc.id
            )
            SELECT
                cc.branch_msg_id,
                group_concat((SELECT MIN(cm.id) FROM contexts_messages cm WHERE cm.context_id = cc.id)) AS context_set
            FROM context_chain cc
            WHERE cc.branch_msg_id IS NOT null
            GROUP BY cc.branch_msg_id;
        """, (root_id,), return_type='dict')
        self.branches = {int(k): [int(i) for i in v.split(',')] for k, v in result.items() if v}
        # print(f"BRANCHES: {self.branches}")

    def refresh_messages(self):
        last_msg_id = self.messages[-1].id if len(self.messages) > 0 else 0

        msg_log = sql.get_results("""
            WITH RECURSIVE context_path(context_id, parent_id, branch_msg_id, prev_branch_msg_id) AS (
              SELECT id, parent_id, branch_msg_id, null
              FROM contexts 
              WHERE id = ?
              UNION ALL
              SELECT c.id, c.parent_id, c.branch_msg_id, cp.branch_msg_id
              FROM context_path cp
              JOIN contexts c ON cp.parent_id = c.id
            )
            SELECT m.id, m.role, m.msg, m.member_id, m.alt_turn, m.log
            FROM contexts_messages m
            JOIN context_path cp ON m.context_id = cp.context_id
            WHERE m.id > ?
                AND (cp.prev_branch_msg_id IS NULL OR m.id < cp.prev_branch_msg_id)
            ORDER BY m.id;""", (self.workflow.leaf_id, last_msg_id,))

        self.messages.extend([Message(int(msg_id), role, content, member_id, alt_turn, log)
                              for msg_id, role, content, member_id, alt_turn, log in msg_log])

        member_turn_outputs = {member.member_id: None for member in self.workflow.get_members()}
        member_last_outputs = {member.member_id: None for member in self.workflow.get_members()}
        for msg in self.messages:
            if msg.alt_turn != self.alt_turn_state:
                self.alt_turn_state = msg.alt_turn
                member_turn_outputs = {member.member_id: None for member in self.workflow.get_members()}

            member_turn_outputs[msg.member_id] = msg.content
            member_last_outputs[msg.member_id] = msg.content

            run_finished = None not in member_turn_outputs.values()  #!looper!#
            if run_finished:
                self.alt_turn_state = 1 - self.alt_turn_state
                member_turn_outputs = {member.member_id: None for member in self.workflow.get_members()}

        self.workflow.reset_last_outputs()
        self.workflow.set_last_outputs(member_last_outputs)
        self.workflow.set_turn_outputs(member_turn_outputs)

    def load_msg_id_buffer(self):
        self.msg_id_buffer = []
        last_msg_id = sql.get_scalar("SELECT seq FROM sqlite_sequence WHERE name = 'contexts_messages'")
        last_msg_id = last_msg_id if last_msg_id is not None else 0
        for msg_id in range(last_msg_id + 1, last_msg_id + 100):
            self.msg_id_buffer.append(msg_id)

    def get_next_msg_id(self) -> int:
        last_id = self.msg_id_buffer[-1]
        self.msg_id_buffer.append(last_id + 1)
        return self.msg_id_buffer.pop(0)

    def add(self,
        role: str,
        content: str,
        member_id: str = '1',
        log_obj=None
    ) -> Message:
        with self.thread_lock:
            next_id = self.get_next_msg_id()
            if log_obj is None:
                log_obj = {}
            log_obj['id'] = next_id
            new_msg = Message(next_id, role, content, member_id, self.alt_turn_state, log_obj)

            log_json_str = json.dumps(log_obj) if log_obj is not None else '{}'
            sql.execute \
                ("INSERT INTO contexts_messages (context_id, member_id, role, msg, alt_turn, embedding_id, log) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (self.workflow.leaf_id, member_id, role, content, new_msg.alt_turn, None, log_json_str))
            self.refresh_messages()

            return new_msg

    def get_workflow_from_full_member_id(self, full_member_id: str):  # !nestmember!
        walk_ids = full_member_id.split('.')[:-1]
        workflow = self.workflow
        for member_id in walk_ids:
            workflow = workflow.members[member_id]
        return workflow

    def get_member_inputs_from_workflow(self, calling_member_id: str) -> List[Any]:  # Tuple[List[str], Dict[str, List[str]], Dict[str, List[str]]]:
        """Recursive function to get the inputs of a member"""
        # member id helpers
        member_split = calling_member_id.split('.')
        member_id = member_split[-1]
        path_to_member = '.'.join(member_split[:-1])

        # member_exclusive_roles = {}  # if inp['source'] == 'Output' this value is inp['source_options'] IF it != 'all'
        # get member_workflow
        member_workflow = self.get_workflow_from_full_member_id(calling_member_id)

        # get member inputs and convert to full member ids
        workflow_inputs = member_workflow.config.get('inputs', [])
        member_inputs = [inp for inp in workflow_inputs
                        if inp['target_member_id'] == member_id
                        and any(mapping.get('target') == 'Message'
                                for mapping in inp['config'].get('mappings.data', []))]
        for inp in member_inputs:
            inp['full_source_member_id'] = f"{path_to_member}{inp['source_member_id']}"
                        # and inp['config'].get('mappings.data', []) == 'Message']

        # inherit inputs from parent
        if member_workflow._parent_workflow is not None:
            del_imps = []
            add_imps = []
            for inp in member_inputs:  # todo allow users in nested workflows
                inp_id = inp['source_member_id']
                inp_member = member_workflow.members.get(inp_id, None)
                if isinstance(inp_member, User):
                    del_imps.append(inp)
                    add_imps += self.get_member_inputs_from_workflow(f"{path_to_member}")
                    # return self.get_member_inputs_from_workflow(f"{path_to_member}")

            for imp in del_imps:
                member_inputs.remove(imp)
            member_inputs += add_imps
            # only_input_id = member_inputs[0]['source_member_id']  # todo
            # only_input = member_workflow.members.get(only_input_id, None)
            # if isinstance(only_input, User):
            #     return self.get_member_inputs_from_workflow(f"{path_to_member}")

        return member_inputs

    def get(self, incl_roles='all', calling_member_id='0', base_member_id=None):
        member_inputs = self.get_member_inputs_from_workflow(calling_member_id)
        input_member_ids = [f"{inp['full_source_member_id']}" for inp in member_inputs]

        member_exclusive_roles: Dict[str, List[str]] = {}
        member_structures: Dict[str, List[str]] = {}
        for inp in member_inputs:
            source_member_id = f"{inp['full_source_member_id']}"
            for mapping in inp['config'].get('mappings.data', []):
                if mapping.get('target') == 'Message' and mapping.get('source') == 'Output':
                    if mapping.get('source_options', 'all') != 'all':
                        if source_member_id not in member_exclusive_roles:
                            member_exclusive_roles[source_member_id] = []
                        member_exclusive_roles[source_member_id].append(mapping['source_options'])
                elif mapping.get('target') == 'Message' and mapping.get('source') == 'Structure':
                    if source_member_id not in member_structures:
                        member_structures[source_member_id] = []
                    member_structures[source_member_id].append(mapping['source_options'])

        # # get show_members_as_user_role setting
        # member_workflow = self.get_workflow_from_full_member_id(calling_member_id)
        # # calling_member = member_workflow.members.get(member_id, None)
        # # member_config = {} if calling_member is None else calling_member.config

        # # # get the member ids to show as user
        # user_members = []
        # set_members_as_user = True
        # if set_members_as_user:
        #     user_members = [f'{path_to_member}{m_id}' for m_id in member_workflow.members if m_id != member_id]

        # get all member ids to include in the response, not just inputs
        all_member_ids = input_member_ids + [calling_member_id]

        # get all messages that match the criteria
        # if message is in `incl_roles`, and the member is at the same depth,
        # and the member is in the input list (if no inputs, include all)
        msgs = [
            {
                'id': msg.id,
                'role': msg.role if msg.role not in ('user', 'assistant')
                else 'user' if (msg.member_id != calling_member_id or msg.role == 'user')
                else 'assistant',
                'member_id': msg.member_id,
                'content': msg.content,
                'alt_turn': msg.alt_turn,
            } for msg in self.messages
            if (incl_roles == 'all' or msg.role in incl_roles)
            and (base_member_id is None or msg.member_id.startswith(f'{base_member_id}.'))
            and (len(input_member_ids) == 0 or msg.member_id in all_member_ids)
            and ((msg.member_id not in member_exclusive_roles)
                or msg.role in member_exclusive_roles.get(msg.member_id, []))
               # and msg.member_id.count('.') == calling_member_id.count('.')
        ]

        # member_structures = {}  # {full_member_id: structure_field}
        # for each msg, if msg.member_id in member_structures, duplicate the message for each item in the list in values().

        # Duplicate messages for structured members
        expanded_msgs = []
        for msg in msgs:
            if msg['member_id'] in member_structures:
                structure_entries = member_structures[msg['member_id']]
                parsed, json_obj = try_parse_json(msg['content'])
                if not parsed:
                    raise ValueError(f"Message content is not valid JSON: {msg['content']}")

                for item in structure_entries:
                    duplicate_msg = msg  # .copy()
                    duplicate_msg['content'] = json_obj.get(convert_to_safe_case(item), 'None')
                    expanded_msgs.append(duplicate_msg)
                    pass
            else:
                expanded_msgs.append(msg)

        return expanded_msgs

    def get_llm_messages(self, calling_member_id='0', msg_limit=None, max_turns=None):
        msgs = self.get(incl_roles='all', calling_member_id=calling_member_id)
        llm_accepted_roles = ('user', 'assistant', 'system', 'function', 'code', 'output', 'tool', 'result')

        member_id = calling_member_id.split('.')[-1]
        calling_member = self.workflow.members.get(member_id, None)
        member_config = {} if calling_member is None else calling_member.config

        # Insert preloaded messages
        preloaded_msgs = member_config.get('chat.preload.data', [])
        preloaded_msgs = [
            {
                'role': msg['role'] if msg['role'] in llm_accepted_roles else 'user',
                'content': msg['content']
            }
            for msg in preloaded_msgs
            if msg['type'] == 'Context'
            # and msg['role'] in llm_accepted_roles
        ]

        msgs = preloaded_msgs + msgs

        # Apply maximum limits
        if msg_limit is None:
            msg_limit = member_config.get('chat.max_messages', None)
        if max_turns is None:
            max_turns = member_config.get('chat.max_turns', None)
        if max_turns:
            state_change_count = 0
            c_state = self.alt_turn_state
            for i, msg in enumerate(reversed(msgs)):
                if msg['alt_turn'] != c_state:
                    c_state = msg['alt_turn']
                    state_change_count += 1
                if state_change_count >= max_turns:
                    msgs = msgs[len(msgs) - i:]
                    break

        if msg_limit:
            if len(msgs) > msg_limit:
                msgs = msgs[-msg_limit:]

        if len(msgs) == 0:
            return []

        # Final LLM formatting
        llm_msgs = []
        for msg in msgs:
            msg_dict = {
                'role': msg['role'] if msg['role'] in llm_accepted_roles else 'user',
                'content': msg['content'],
            }
            if msg['role'] == 'tool':
                parsed, tool_msg_config = try_parse_json(msg['content'])

                if parsed:
                    args = tool_msg_config.get('args', '{}')
                    last_msg = llm_msgs[-1] if llm_msgs else None
                    if last_msg['role'] == 'assistant':
                        llm_msgs[-1]['tool_calls'] = [
                            {
                                "function": {
                                    "arguments": args,
                                    "name": tool_msg_config['name']
                                },
                                "id": tool_msg_config['tool_call_id'],
                                "index": 1,
                                "type": "function"
                            }
                        ]
                        continue
                        #     "name": tool_msg_config['name'],
                        #     "arguments": args,
                        #     "tool_call_id": tool_msg_config['tool_call_id'],
                        # }

                    # raise NotImplementedError('3143')
                    msg_dict['role'] = 'assistant'
                    msg_dict['content'] = ''
                    msg_dict['tool_calls'] = [  # todo de-dupe
                        {
                            "function": {
                                "arguments": args,
                                "name": tool_msg_config['name']
                            },
                            "id": tool_msg_config['tool_call_id'],
                            "index": 1,
                            "type": "function"
                        }
                    ]
                    # msg_dict['role'] = 'assistant'
                    # msg_dict['content'] = ''
                    # msg_dict['function_call'] = {
                    #     "name": tool_msg_config['name'],
                    #     "arguments": args,
                    # }

            elif msg['role'] == 'result':
                from src.system.base import manager
                _, res_dict = try_parse_json(msg['content'])
                if res_dict.get('status') != 'success':
                    continue
                call_id = res_dict.get('tool_call_id')
                tool_uuid = res_dict.get('tool_uuid')
                tool_name = convert_to_safe_case(manager.tools.tool_id_names.get(tool_uuid, ''))
                output = res_dict.get('output', msg['content'])
                msg_dict['role'] = 'tool'  # 'user'
                msg_dict['content'] = output
                # msg_dict['content'] = [
                #     {
                #         'type': 'tool_result',
                #         'tool_use_id': call_id,
                #         'content': output
                #     },
                # ]
                # msg_dict['tool_use_id'] = call_id
                msg_dict['tool_call_id'] = call_id
                msg_dict['name'] = tool_name
                # !toolcall!#

            llm_msgs.append(msg_dict)

        # if first item is assistant, remove it (to avoid errors with some llms like claude)
        first_msg = next(iter(llm_msgs))
        if first_msg:
            if first_msg.get('role', '') != 'user':
                llm_msgs.pop(0)

        accepted_keys = ('role', 'content', 'name', 'function_call', 'tool_call_id', 'tool_calls')  #!toolcall!#
        llm_msgs = [{k: v for k, v in msg.items() if k in accepted_keys}
                    for msg in llm_msgs]

        return llm_msgs

    def count(self, incl_roles=('user', 'assistant')):
        return len([msg for msg in self.messages if msg.role in incl_roles])

    def pop(self, indx, incl_roles=('user', 'assistant')):
        seen_cnt = -1
        for i, msg in enumerate(self.messages):
            if msg.role not in incl_roles:
                continue
            seen_cnt += 1
            if seen_cnt == indx:
                return self.messages.pop(i)

    def last(self, incl_roles=('user', 'assistant')):
        msgs = self.get(incl_roles=incl_roles)
        return msgs[-1] if len(msgs) > 0 else None

    def last_role(self):
        last = self.last()
        if last is None:
            return ''
        return last['role']

    def last_id(self):
        last = self.last()
        if last is None:
            return 0
        return last['id']
