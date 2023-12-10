import asyncio
import json
import os
import threading

import tiktoken

from agentpilot.utils import sql, embeddings
# from agentpilot.context.iterators import SequentialIterator

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


class Context:
    def __init__(self, main, context_id=None, agent_id=None):
        self.main = main

        self.loop = asyncio.get_event_loop()
        self.responding = False
        self.stop_requested = False

        self.id = context_id
        self.chat_name = ''
        self.chat_title = ''
        self.leaf_id = context_id
        self.context_path = {context_id: None}
        self.members = {}  # {member_id: Member()}
        # self.member_inputs = {}  # {member_id: [input_member_id]}
        self.member_configs = {}  # {member_id: config}
        self.member_outputs = {}

        # self.iterator = SequentialIterator(self)  # 'SEQUENTIAL'  # SEQUENTIAL, RANDOM, REALISTIC
        self.message_history = None
        if agent_id is not None:
            context_id = sql.get_scalar("""
                SELECT context_id AS id 
                FROM contexts_members 
                WHERE agent_id = ? 
                  AND context_id IN (
                    SELECT context_id 
                    FROM contexts_members 
                    GROUP BY context_id 
                    HAVING COUNT(agent_id) = 1
                  ) AND del = 0
                ORDER BY context_id DESC 
                LIMIT 1""", (agent_id,))
            if context_id is None:
                pass
                # make new context
            self.id = context_id

        if self.id is None:
            latest_context = sql.get_scalar('SELECT id FROM contexts WHERE parent_id IS NULL ORDER BY id DESC LIMIT 1')
            if latest_context:
                self.id = latest_context
            else:
                # # make new context
                sql.execute("INSERT INTO contexts (id) VALUES (NULL)")
                c_id = sql.get_scalar('SELECT id FROM contexts ORDER BY id DESC LIMIT 1')
                sql.execute("INSERT INTO contexts_members (context_id, agent_id, agent_config) VALUES (?, 0, '{}')", (c_id,))
                self.id = c_id

        self.blocks = {}
        self.roles = {}
        self.models = {}
        self.load()

        if len(self.members) == 0:
            sql.execute("INSERT INTO contexts_members (context_id, agent_id, agent_config) VALUES (?, 0, '{}')", (self.id,))
            self.load_members()

    def load(self):
        self.load_context_settings()
        self.load_members()
        self.message_history = MessageHistory(self)

    def load_context_settings(self):
        self.load_blocks()
        self.load_roles()
        self.load_models()
        self.chat_title = sql.get_scalar("SELECT summary FROM contexts WHERE id = ?", (self.id,))

    def load_blocks(self):
        self.blocks = sql.get_results("""
            SELECT
                name,
                text
            FROM blocks""", return_type='dict')

    def load_roles(self):
        self.roles = sql.get_results("""
            SELECT
                name,
                config
            FROM roles""", return_type='dict')
        for k, v in self.roles.items():
            self.roles[k] = json.loads(v)

    def load_models(self):
        self.models = {}
        model_res = sql.get_results("""
            SELECT
                m.model_name,
                m.model_config,
                a.priv_key
            FROM models m
            LEFT JOIN apis a ON m.api_id = a.id""")
        for model_name, model_config, priv_key in model_res:
            if priv_key == '$OPENAI_API_KEY':
                priv_key = os.environ.get("OPENAI_API_KEY", '')
            elif priv_key == '$PERPLEXITYAI_API_KEY':
                priv_key = os.environ.get("PERPLEXITYAI_API_KEY", '')

            model_config = json.loads(model_config)
            if priv_key != '':
                model_config['api_key'] = priv_key

            self.models[model_name] = model_config

    def load_members(self):
        from agentpilot.agent.base import Agent
        # Fetch the participants associated with the context
        context_members = sql.get_results("""
            SELECT 
                cm.id AS member_id,
                cm.agent_id,
                cm.agent_config,
                cm.del
            FROM contexts_members cm
            WHERE cm.context_id = ?
            ORDER BY 
                cm.ordr""",
            params=(self.id,))

        self.members = {}
        self.member_configs = {}
        # self.member_inputs
        unique_members = set()
        for member_id, agent_id, agent_config, deleted in context_members:
            self.member_configs[member_id] = json.loads(agent_config)
            if deleted == 1:
                continue

            # Load participant inputs
            participant_inputs = sql.get_results("""
                SELECT 
                    input_member_id
                FROM contexts_members_inputs
                WHERE member_id = ?""",
                params=(member_id,))

            member_inputs = [row[0] for row in participant_inputs]

            # Instantiate the agent
            agent = Agent(agent_id, member_id, context=self, wake=True)
            member = Member(self, member_id, agent, member_inputs)  # , self.signals)
            self.members[member_id] = member  # json.loads(agent_config)
            unique_members.add(agent.name)

        self.chat_name = ', '.join(unique_members)

    def start(self):
        for member in self.members.values():
            member.task = self.loop.create_task(self.run_member(member))

        self.responding = True
        try:
            self.loop.run_until_complete(asyncio.gather(*[m.task for m in self.members.values()]))
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
        except Exception as e:
            self.main.finished_signal.emit()
            raise e

        self.main.finished_signal.emit()

    def stop(self):
        self.stop_requested = True
        for member in self.members.values():
            if member.task is not None:
                member.task.cancel()
        # self.loop.run_until_complete(asyncio.gather(*[m.task for m in self.members.values() if m.task is not None], return_exceptions=True))
        # self.responding = False

    async def run_member(self, member):
        try:
            if member.inputs:
                await asyncio.gather(*[self.members[m_id].task for m_id in member.inputs if m_id in self.members])

            await member.respond()
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
        except Exception as e:
            raise e

    def save_message(self, role, content, member_id=None, log_obj=None):
        if role == 'assistant':
            content = content.strip().strip('"').strip()  # hack to clean up the assistant's messages from FB and DevMode
        elif role == 'output':
            content = 'The code executed without any output' if content.strip() == '' else content

        if content == '':
            return None

        member = self.members.get(member_id, None)
        if member is not None and role == 'assistant':
            member.last_output = content

        return self.message_history.add(role, content, member_id=member_id, log_obj=log_obj)

    def deactivate_all_branches_with_msg(self, msg_id):  # todo - get these into a transaction
        print("CALLED deactivate_all_branches_with_msg: ", msg_id)
        sql.execute("""
            UPDATE contexts
            SET active = 0
            WHERE branch_msg_id = (
                SELECT branch_msg_id
                FROM contexts
                WHERE id = (
                    SELECT context_id
                    FROM contexts_messages
                    WHERE id = ?
                )
            );""", (msg_id,))

    def activate_branch_with_msg(self, msg_id):
        print("CALLED activate_branch_with_msg: ", msg_id)
        sql.execute("""
            UPDATE contexts
            SET active = 1
            WHERE id = (
                SELECT context_id
                FROM contexts_messages
                WHERE id = ?
            );""", (msg_id,))


class Member:
    def __init__(self, context, m_id, agent, inputs):
        self.context = context
        self.main = context.main
        self.m_id = m_id
        self.agent = agent
        self.inputs = inputs  # [member_id]
        self.task = None
        self.last_output = ''

    async def respond(self):
        for key, chunk in self.agent.receive(stream=True):
            if self.context.stop_requested:
                self.context.stop_requested = False
                break
            if key in ('assistant', 'message'):
                self.main.new_sentence_signal.emit(self.m_id, chunk)  # Emitting the signal with the new sentence.
            else:
                break


class MessageHistory:
    def __init__(self, context):
        self.thread_lock = threading.Lock()
        # self.msg_id_thread_lock = threading.Lock()
        self.context = context
        self.branches = {}  # {branch_msg_id: [child_msg_ids]}
        self.messages = []  # [Message(m['id'], m['role'], m['content']) for m in (messages or [])]
        # self.member_outputs = {}
        self.msg_id_buffer = []
        self.load()

    def load(self):
        print("CALLED message_history.load")
        self.context.leaf_id = sql.get_scalar("""
            WITH RECURSIVE leaf_contexts AS (
                SELECT 
                    c1.id, 
                    c1.parent_id, 
                    c1.active 
                FROM contexts c1 
                WHERE c1.id = ?
                UNION ALL
                SELECT 
                    c2.id, 
                    c2.parent_id, 
                    c2.active 
                FROM contexts c2 
                JOIN leaf_contexts lc ON lc.id = c2.parent_id 
                WHERE 
                    c2.id = (
                        SELECT MIN(c3.id) FROM contexts c3 WHERE c3.parent_id = lc.id AND c3.active = 1
                    )
            )
            SELECT id
            FROM leaf_contexts 
            ORDER BY id DESC 
            LIMIT 1;""", (self.context.id,))

        print(f"LEAF ID SET TO {self.context.leaf_id} BY message_history.load")
        self.load_branches()
        self.load_messages()
        self.load_msg_id_buffer()

    def load_branches(self):
        print("CALLED load_branches")
        root_id = self.context.id
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

    # active_leaf_id = '''
    # '''

    # backwards_loader_w_leaf = '''
    # WITH RECURSIVE context_path(context_id, parent_id, branch_msg_id, prev_branch_msg_id) AS (
    #   SELECT id, parent_id, branch_msg_id,
    #          null
    #   FROM contexts
    #   WHERE id = ?
    #   UNION ALL
    #   SELECT c.id, c.parent_id, c.branch_msg_id, cp.branch_msg_id
    #   FROM context_path cp
    #   JOIN contexts c ON cp.parent_id = c.id
    # )
    # SELECT m.id, m.role, m.msg, m.agent_id, m.context_id, m.embedding_id
    # FROM contexts_messages m
    # JOIN context_path cp ON m.context_id = cp.context_id
    # WHERE (cp.prev_branch_msg_id IS NULL OR m.id < cp.prev_branch_msg_id)
    # ORDER BY m.id
    # '''

    def load_messages(self):
        print("CALLED load_messages")
        # remove all messages where id = -1
        # # self.messages = [msg for msg in self.messages if msg.id != -1]
        # self.context.leaf_id = sql.get_scalar("""
        #     WITH RECURSIVE leaf_contexts AS (
        #         SELECT
        #             c1.id,
        #             c1.parent_id,
        #             c1.active
        #         FROM contexts c1
        #         WHERE c1.id = ?
        #         UNION ALL
        #         SELECT
        #             c2.id,
        #             c2.parent_id,
        #             c2.active
        #         FROM contexts c2
        #         JOIN leaf_contexts lc ON lc.id = c2.parent_id
        #         WHERE
        #             c2.id = (
        #                 SELECT MIN(c3.id) FROM contexts c3 WHERE c3.parent_id = lc.id AND c3.active = 1
        #             )
        #     )
        #     SELECT id
        #     FROM leaf_contexts
        #     ORDER BY id DESC
        #     LIMIT 1;""", (self.context.id,))
        #
        # print(f"LEAF ID SET TO {self.context.leaf_id} BY context.load_messages")

        last_msg_id = self.messages[-1].id if len(self.messages) > 0 else 0

        msg_log = sql.get_results("""
            WITH RECURSIVE context_path(context_id, parent_id, branch_msg_id, prev_branch_msg_id) AS (
              SELECT id, parent_id, branch_msg_id, 
                     null
              FROM contexts 
              WHERE id = ?
              UNION ALL
              SELECT c.id, c.parent_id, c.branch_msg_id, cp.branch_msg_id
              FROM context_path cp
              JOIN contexts c ON cp.parent_id = c.id
            )
            SELECT m.id, m.role, m.msg, m.member_id, m.embedding_id
            FROM contexts_messages m
            JOIN context_path cp ON m.context_id = cp.context_id
            WHERE m.id > ?
                AND (cp.prev_branch_msg_id IS NULL OR m.id < cp.prev_branch_msg_id)
            ORDER BY m.id;""", (self.context.leaf_id, last_msg_id,))

        print(f"FETCHED {len(msg_log)} MESSAGES", )
        self.messages.extend([Message(msg_id, role, content, member_id, embedding_id)
                         for msg_id, role, content, member_id, embedding_id in msg_log])

    def load_msg_id_buffer(self):
        # with self.msg_id_thread_lock:
        self.msg_id_buffer = []
        last_msg_id = sql.get_scalar("SELECT MAX(id) FROM contexts_messages")
        last_msg_id = last_msg_id if last_msg_id is not None else 0
        for msg_id in range(last_msg_id + 1, last_msg_id + 100):
            self.msg_id_buffer.append(msg_id)

    def get_next_msg_id(self):
        # with self.msg_id_thread_lock:
        last_id = self.msg_id_buffer[-1]
        self.msg_id_buffer.append(last_id + 1)
        return self.msg_id_buffer.pop(0)

    def add(self, role, content, embedding_id=None, member_id=None, log_obj=None):
        print("CALLED message_history.add")
        with self.thread_lock:
            # max_id = sql.get_scalar("SELECT COALESCE(MAX(id), 0) FROM contexts_messages")
            next_id = self.get_next_msg_id()
            new_msg = Message(next_id, role, content, embedding_id=embedding_id, member_id=member_id)

            if self.context is None:
                raise Exception("No context ID set")

            sys_msg = ''
            json_str = ''
            if log_obj is not None:
                log_obj_messages = log_obj.messages
                # if first item has role = 'system' then pop it
                if len(log_obj_messages) > 0 and log_obj_messages[0]['role'] == 'system':
                    sys_msg = log_obj_messages.pop(0)['content']

                json_obj = {'system': sys_msg, 'messages': log_obj_messages}
                json_str = json.dumps(json_obj)

            # sql.execute("INSERT INTO contexts_messages (id, context_id, member_id, role, msg, embedding_id, log) VALUES (?, ?, ?, ?, ?, ?, ?)",
            #             (new_msg.id, self.context.leaf_id, member_id, role, content, new_msg.embedding_id, json_str))
            sql.execute("INSERT INTO contexts_messages (context_id, member_id, role, msg, embedding_id, log) VALUES (?, ?, ?, ?, ?, ?)",
                        (self.context.leaf_id, member_id, role, content, new_msg.embedding_id, json_str))
            # self.messages.append(new_msg)
            self.load_messages()

            return new_msg

            # def add_padding_to_consecutive_messages(msg_list):
            #     result = []
            #     last_seen_role = None
            #     for msg in msg_list:
            #         is_same_role = last_seen_role == msg['role']
            #         if is_same_role and pad_consecutive and msg['role'] == 'assistant':
            #             pad_role = 'assistant' if msg['role'] == 'user' else 'user'
            #             pad_msg = Message(msg_id=0, role=pad_role, content='ok')
            #             result.append({
            #                 'id': pad_msg.id,
            #                 'role': pad_msg.role,
            #                 'content': pad_msg.content,
            #                 'embedding_id': pad_msg.embedding_id
            #             })
            #         elif is_same_role and pad_consecutive and msg['role'] == 'user':
            #             result[-1]['content'] = msg['content']
            #             continue
            #
            #         result.append(msg)
            #         last_seen_role = msg['role']
            #     return result

    def get(self,
            incl_roles=('user', 'assistant'),
            llm_format=False,
            calling_member_id=0,
            msg_limit=8,
            pad_consecutive=True,
            from_msg_id=0):

        assistant_msg_prefix = ''  # self.agent.config.get('context.prefix_all_assistant_msgs')  todo
        if assistant_msg_prefix is None: assistant_msg_prefix = ''

        assistant_member = calling_member_id
        member_configs = self.context.member_configs

        set_members_as_user = member_configs.get(calling_member_id, {}).get('group.set_members_as_user_role', True)
        calling_member = self.context.members.get(calling_member_id, None)
        input_members = calling_member.inputs if calling_member else []
        user_members = [] if not set_members_as_user else input_members

        if len(user_members) == 0:
            # set merge members = all members except calling member, use configs to remember deleted members
            user_members = [m_id for m_id in self.context.member_configs if m_id != calling_member_id]

        if llm_format:
            incl_roles = ('user', 'assistant', 'output', 'code')

        pre_formatted_msgs = [
            {
                'id': msg.id,
                'role': msg.role if msg.role not in ('user', 'assistant')
                        else 'user' if (msg.member_id in user_members or msg.role == 'user')
                            else 'assistant',
                'member_id': msg.member_id,
                'content': f"{assistant_msg_prefix}{msg.content}" if msg.role == 'assistant' and llm_format else msg.content,
                'embedding_id': msg.embedding_id
            } for msg in self.messages if msg.id >= from_msg_id and msg.role in incl_roles
        ]

        # merge_multiple_members = member_configs.get(calling_member_id, {}).get('group.merge_multiple_members', True)

        member_names = {}

        if llm_format:
            llm_format_msgs = []
            last_ass_msg = None
            for msg in pre_formatted_msgs:
                if msg['role'] == 'user':
                    llm_format_msgs.append(msg)
                elif msg['role'] == 'assistant':
                    llm_format_msgs.append(msg)
                    last_ass_msg = llm_format_msgs[-1]
                elif msg['role'] == 'output':
                    msg['role'] = 'function'
                    msg['name'] = 'execute'
                    llm_format_msgs.append(msg)
                elif msg['role'] == 'code':
                    if last_ass_msg is None: continue
                    last_ass_msg['content'] += f"\n{msg['content']}"

            pre_formatted_msgs = llm_format_msgs

        # # Apply padding between consecutive messages of same role
        # pre_formatted_msgs = add_padding_to_consecutive_messages(pre_formatted_msgs)
        # check if limit is within
        if len(pre_formatted_msgs) > msg_limit:
            pre_formatted_msgs = pre_formatted_msgs[-msg_limit:]

        if llm_format:
            for msg in pre_formatted_msgs:
                accepted_keys = ('role', 'content', 'name')
                # pop each key if key not in list
                msg_keys = list(msg.keys())  # todo - optimise
                for key in msg_keys:
                    if key not in accepted_keys:
                        msg.pop(key)

        return pre_formatted_msgs

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

    def get_conversation_str(self, msg_limit=4, incl_roles=('user', 'assistant'), prefix='CONVERSATION:\n'):
        msgs = self.get(msg_limit=msg_limit, incl_roles=incl_roles)
        formatted_context = [f"{msg['role']}: `{msg['content'].strip()}`" for msg in msgs]
        formatted_context[-1] = f""">> {formatted_context[-1]} <<"""
        return prefix + '\n'.join(formatted_context)

    def get_react_str(self, msg_limit=8, from_msg_id=None, prefix='THOUGHTS:\n'):
        msgs = self.get(incl_roles=('thought', 'result'), msg_limit=msg_limit, from_msg_id=from_msg_id)
        formatted_context = [f"{msg['role']}: `{msg['content'].strip()}`" for msg in msgs]
        return prefix + '\n'.join(formatted_context)

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


class Message:
    def __init__(self, msg_id, role, content, member_id=None, embedding_id=None):
        self.id = msg_id
        self.role = role
        self.content = content
        self.member_id = member_id
        self.token_count = len(tiktoken.encoding_for_model("gpt-3.5-turbo").encode(content))
        # self.unix_time = unix_time or int(time.time())
        self.embedding_id = embedding_id
        # if self.embedding_id and isinstance(self.embedding, str):
        #     self.embedding = embeddings.string_embeddings_to_array(self.embedding)
        self.embedding_data = None
        if self.embedding_id is None:
            if role == 'user' or role == 'assistant' or role == 'request' or role == 'result':
                self.embedding_id, self.embedding_data = embeddings.get_embedding(content)
