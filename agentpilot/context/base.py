import asyncio
import json
import threading
import time
import tiktoken
from termcolor import cprint

from agentpilot.utils.apis.llm import get_scalar
# import oai
from agentpilot.utils import sql, embeddings
from agentpilot.context.iterators import SequentialIterator

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


class Context:
    def __init__(self, context_id=None, agent_id=None):
        self.loop = asyncio.get_event_loop()
        self.id = context_id
        self.chat_name = ''
        self.leaf_id = context_id
        self.context_path = {context_id: None}
        self.participants = {}  # {agent_id: agent_config_dict}
        self.participant_inputs = {}  # {participant_id: [input_participant_id]}
        self.iterator = SequentialIterator(self)  # 'SEQUENTIAL'  # SEQUENTIAL, RANDOM, REALISTIC
        self.message_history = None
        if agent_id is not None:
            context_id = sql.get_scalar('SELECT context_id AS id FROM contexts_members WHERE agent_id = ? ORDER BY context_id DESC LIMIT 1',
                                        (agent_id,))

        if context_id is None:
            latest_context = sql.get_scalar('SELECT id FROM contexts WHERE parent_id IS NULL ORDER BY id DESC LIMIT 1')
            if latest_context:
                self.id = latest_context
                # self.leaf_id = 398  # latest_context
            else:
                raise NotImplementedError("No context ID provided and no contexts in database")
                # make new context

        self.blocks = {}
        self.roles = {}
        self.load()

        if len(self.participants) == 0:
            raise Exception("No participants in context")

    def load(self):
        self.load_context_settings()
        self.load_participants()
        # self.load_context_path()
        self.message_history = MessageHistory(self)

    def load_context_settings(self):
        self.blocks = sql.get_results("""
            SELECT
                name,
                text
            FROM blocks""", return_type='dict')
        self.roles = sql.get_results("""
            SELECT
                name,
                config
            FROM roles""", return_type='dict')
        for k, v in self.roles.items():
            self.roles[k] = json.loads(v)

    def load_participants(self):
        from agentpilot.agent.base import Agent
        # Fetch the participants associated with the context
        context_participants = sql.get_results("""
            SELECT 
                cp.id AS member_id,
                cp.agent_id,
                cp.agent_config
            FROM contexts_members cp
            WHERE cp.context_id = ? 
            ORDER BY 
                cp.ordr""",
            params=(self.id,))

        unique_participants = set()
        for participant_id, agent_id, agent_config in context_participants:
            # Load participant inputs
            participant_inputs = sql.get_results("""
                SELECT 
                    input_member_id
                FROM contexts_members_inputs
                WHERE member_id = ?""",
                params=(participant_id,))

            # Initialize participant inputs in the dictionary
            self.participant_inputs[participant_id] = [row[0] for row in participant_inputs]

            # Instantiate the agent
            agent = Agent(agent_id, context=self, override_config=agent_config, wake=True)
            self.participants[agent_id] = json.loads(agent_config)
            unique_participants.add(agent.name)

        self.chat_name = ', '.join(unique_participants)
        # do the reverse, taking self.participants and getting it in t

    # def load_context_path(self):
    #     self.context_path = sql.get_results("""
    #         WITH RECURSIVE context_path(context_id, parent_id, branch_msg_id, prev_branch_msg_id) AS (
    #           SELECT id, parent_id, branch_msg_id,
    #                  null
    #           FROM contexts
    #           WHERE id = ?
    #           UNION ALL
    #           SELECT c.id, c.parent_id, c.branch_msg_id, cp.branch_msg_id
    #           FROM context_path cp
    #           JOIN contexts c ON cp.parent_id = c.id
    #         )
    #         SELECT m.id, m.unix, m.context_id, m.agent_id, m.role, m.msg, m.embedding_id, m.del
    #         FROM contexts_messages m
    #         JOIN context_path cp ON m.context_id = cp.context_id
    #         WHERE (cp.prev_branch_msg_id IS NULL OR m.id < cp.prev_branch_msg_id)
    #         ORDER BY m.id;""", (self.current_leaf_id,), return_type='dict')
    #     # self.context_path = sql.get_results("""
    #     #     WITH RECURSIVE context_path(context_id, parent_id, branch_msg_id, prev_branch_msg_id) AS (
    #     #       SELECT id, parent_id, branch_msg_id,
    #     #              null
    #     #       FROM contexts
    #     #       WHERE id = ?
    #     #       UNION ALL
    #     #       SELECT c.id, c.parent_id, c.branch_msg_id, cp.branch_msg_id
    #     #       FROM context_path cp
    #     #       JOIN contexts c ON cp.parent_id = c.id
    #     #     )
    #     #     SELECT context_id,
    #     #         prev_branch_msg_id
    #     #     FROM context_path;""", (self.current_leaf_id,), return_type='dict')
    #     self.context_path = sql.get_results("""
    #         WITH RECURSIVE context_path(context_id, parent_id, branch_msg_id) AS (
    #           SELECT id, parent_id, branch_msg_id FROM contexts WHERE id = ?
    #           UNION ALL
    #           SELECT c.id, c.parent_id, c.branch_msg_id
    #           FROM context_path cp
    #           JOIN contexts c ON cp.parent_id = c.id
    #         )
    #         SELECT context_id, branch_msg_id FROM context_path;""", (self.current_leaf_id,), return_type='dict')

    def save_message(self, role, content):  # , branch_msg_id=None):
        if role == 'assistant':
            content = content.strip().strip('"').strip()  # hack to clean up the assistant's messages from FB and DevMode
        elif role == 'output':
            content = 'The code executed without any output' if content.strip() == '' else content

        if content == '':
            return None

        return self.message_history.add(role, content)


        # if role == 'user':
        #     if self.message_history.last_role() == 'user':
        #         # return None  # Don't allow double user messages
        #         pass  # Allow for now
        # elif role == 'assistant':
        #     content = content.strip().strip('"').strip()  # hack to clean up the assistant's messages from FB and DevMode
        # elif role == 'output':
        #     content = 'The code executed without any output' if content.strip() == '' else content
        #
        # if content == '':
        #     return None
        # return self.message_history.add(role, content)

        # def submit_message(self, role, content):
        #     next_agents = next(self.iterator.cycle())
        #
        #     pass

    def new_context(self, parent_id=None):
        # get count of contexts_messages in this context
        old_context_id = self.message_history.context_id
        msg_count = sql.get_scalar('SELECT COUNT(*) FROM contexts_messages WHERE context_id = ?',
                                   (old_context_id,))
        if msg_count == 0:
            return
        # get count of contexts_messages in context where id is max
        max_id = sql.get_scalar('SELECT MAX(id) FROM contexts')
        max_msg_count = sql.get_scalar('SELECT COUNT(*) FROM contexts_messages WHERE context_id = ?', (max_id,))
        if max_msg_count == 0:
            sql.execute('DELETE FROM contexts WHERE id = ?', (max_id,))
            sql.execute('DELETE FROM contexts_members WHERE context_id = ?', (max_id,))

        sql.execute("INSERT INTO contexts (id) VALUES (NULL)")
        context_id = sql.get_scalar('SELECT MAX(id) FROM contexts')

        sql.execute("""
            INSERT INTO contexts_members (context_id, agent_id, agent_config, ordr)
            SELECT ?, agent_id, agent_config, ordr
            FROM contexts_members
            WHERE context_id = ?;
        """, (context_id, old_context_id))

        self.message_history.context_id = sql.get_scalar("SELECT id FROM contexts ORDER BY id DESC LIMIT 1")
        self.load()


class MessageHistory:
    def __init__(self, context):
        self.context = context
        self.branches = {}  # {branch_msg_id: [child_msg_ids]}
        self.messages = []  # [Message(m['id'], m['role'], m['content']) for m in (messages or [])]
        self.load()
        self.thread_lock = threading.Lock()

    def load(self):
        self.load_branches()
        self.load_messages()

    def load_branches(self):
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
        self.branches = {int(k): [int(i) for i in v.split(',')] for k, v in result.items()}

    # active_leaf_id = '''
    # '''

    backwards_loader_w_leaf = '''
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
    SELECT m.id, m.role, m.msg, m.agent_id, m.context_id, m.embedding_id
    FROM contexts_messages m
    JOIN context_path cp ON m.context_id = cp.context_id
    WHERE (cp.prev_branch_msg_id IS NULL OR m.id < cp.prev_branch_msg_id)
    ORDER BY m.id
    '''

    forwards_loader_w_leaf = '''
    '''

    ''' FORWARDS LOADER - GIVEN ROOT
    '''

    def load_messages(self):
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
            SELECT m.id, m.role, m.msg, m.context_id, m.member_id, m.embedding_id
            FROM contexts_messages m
            JOIN context_path cp ON m.context_id = cp.context_id
            WHERE m.id > ?
                AND (cp.prev_branch_msg_id IS NULL OR m.id < cp.prev_branch_msg_id)
            ORDER BY m.id;""", (self.context.leaf_id, last_msg_id,))

        # for msg_id, role, content, agent_id, context_id, embedding_id in msg_log:
        #     has_siblings = True  # any(msg_id in value for value in self.branches.values())
        #     self.messages.append(Message(msg_id, role, content, embedding_id, has_siblings))

        self.messages.extend([Message(msg_id, role, content, context_id, agent_id, embedding_id)
                         for msg_id, role, content, context_id, agent_id, embedding_id in msg_log])
        gg = 4

    # def get_child_contexts(self, root_id):
    #     rows = sql.get_results("""
    #             WITH RECURSIVE child_contexts (id, branch_msg_id) AS (
    #                 SELECT id, branch_msg_id
    #                 FROM contexts
    #                 WHERE parent_id = ?
    #                 UNION ALL
    #                 SELECT c.id, c.branch_msg_id
    #                 FROM contexts c
    #                 JOIN child_contexts cc ON c.parent_id = cc.id
    #             )
    #             SELECT branch_msg_id, id
    #             FROM child_contexts
    #             ORDER BY branch_msg_id;
    #         """, (root_id,))
    #
    #     result = {}
    #     for row in rows:
    #         result.setdefault(row[0], []).append(row[1])
    #
    #     return result

    def add(self, role, content, embedding_id=None):
        with self.thread_lock:
            max_id = sql.get_scalar("SELECT COALESCE(MAX(id), 0) FROM contexts_messages")
            new_msg = Message(max_id + 1, role, content, context_id=self.context.leaf_id, embedding_id=embedding_id)

            if self.context is None:
                raise Exception("No context ID set")

            sql.execute("INSERT INTO contexts_messages (id, context_id, role, msg, embedding_id) VALUES (?, ?, ?, ?, ?)",
                        (new_msg.id, self.context.leaf_id, role, content, new_msg.embedding_id))
            self.messages.append(new_msg)
            self.load_messages()

            return new_msg

    def get(self,
            incl_roles=('user', 'assistant'),
            llm_format=False,
            msg_limit=8,
            pad_consecutive=True,
            from_msg_id=0):
        def add_padding_to_consecutive_messages(msg_list):
            result = []
            last_seen_role = None
            for msg in msg_list:
                is_same_role = last_seen_role == msg['role']
                if is_same_role and pad_consecutive and msg['role'] == 'assistant':
                    pad_role = 'assistant' if msg['role'] == 'user' else 'user'
                    pad_msg = Message(msg_id=0, role=pad_role, content='ok')
                    result.append({
                        'id': pad_msg.id,
                        'role': pad_msg.role,
                        'content': pad_msg.content,
                        'embedding_id': pad_msg.embedding_id
                    })
                elif is_same_role and pad_consecutive and msg['role'] == 'user':
                    result[-1]['content'] = msg['content']
                    continue

                result.append(msg)
                last_seen_role = msg['role']
            return result

        assistant_msg_prefix = ''  # self.agent.config.get('context.prefix_all_assistant_msgs')  todo
        if assistant_msg_prefix is None: assistant_msg_prefix = ''

        pre_formatted_msgs = [{
            'id': msg.id,
            'role': msg.role,
            'content': f"{assistant_msg_prefix} {msg.content}" if msg.role == 'assistant' and llm_format else msg.content,
            'embedding_id': msg.embedding_id
        } for msg in self.messages if msg.id >= from_msg_id
                                      and (msg.role in incl_roles
                                            or (llm_format
                                                and msg.role in ('output', 'code')
                                                )
                                            )
        ]
        if llm_format:
            formatted_msgs = []
            last_ass_msg = None
            for msg in pre_formatted_msgs:
                if msg['role'] == 'user':
                    formatted_msgs.append(msg)
                elif msg['role'] == 'assistant':
                    formatted_msgs.append(msg)
                    last_ass_msg = formatted_msgs[-1]
                elif msg['role'] == 'output':
                    msg['role'] = 'function'
                    msg['name'] = 'execute'
                    formatted_msgs.append(msg)
                elif msg['role'] == 'code':
                    if last_ass_msg is None: continue
                    last_ass_msg['content'] += f"\n{msg['content']}"

            pre_formatted_msgs = formatted_msgs

        # Apply padding between consecutive messages of same role
        pre_formatted_msgs = add_padding_to_consecutive_messages(pre_formatted_msgs)
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
    def __init__(self, msg_id, role, content, context_id=None, agent_id=None, embedding_id=None):
        self.id = msg_id
        self.role = role
        self.content = content
        self.agent_id = agent_id
        self.token_count = len(tiktoken.encoding_for_model("gpt-3.5-turbo").encode(content))
        # self.unix_time = unix_time or int(time.time())
        self.embedding_id = embedding_id
        # if self.embedding_id and isinstance(self.embedding, str):
        #     self.embedding = embeddings.string_embeddings_to_array(self.embedding)
        self.embedding_data = None
        if self.embedding_id is None:
            if role == 'user' or role == 'assistant' or role == 'request' or role == 'result':
                self.embedding_id, self.embedding_data = embeddings.get_embedding(content)

    # def change_content(self, new_content):
    #     self.content = new_content
    #     self.token_count = len(tiktoken.encoding_for_model("gpt-3.5-turbo").encode(new_content))
    #     self.embedding = embeddings.get_embedding(new_content)
    #     sql.execute(f"UPDATE contexts_messages SET msg = '{new_content}' WHERE id = {self.id}")
    # # def __repr__(self):
    # #     return f"{self.role}: {self.content}"


# class Context:
#     def __init__(self, agent, agent_id=0, context_id=None):
#         self.agent = agent
#         if agent_id is None and context_id is None:
#             latest_context = sql.get_results('SELECT id, agent_id FROM contexts ORDER BY id DESC LIMIT 1',
#                                              return_type='htuple')
#             if latest_context:
#                 context_id, agent_id = latest_context
#             else:
#                 agent_id = 0
#         elif agent_id is not None:
#         elif context_id is not None:
#             agent_id = sql.get_scalar('SELECT agent_id FROM contexts WHERE id = ?', (context_id,))
#
#         self.agent_id = agent_id
#         self.message_history = MessageHistory(agent=self.agent, agent_id=agent_id, context_id=context_id)
#         # self.behaviour = behaviour
#         # self.recent_actions = []
#
#     def new_context(self, parent_id=None):  # todo
#         # get count of contexts_messages in this context
#         msg_count = sql.get_scalar('SELECT COUNT(*) FROM contexts_messages WHERE context_id = ?',
#                                    (self.message_history.context_id,))
#         if msg_count == 0:
#             return
#         # get count of contexts_messages in context where id is max
#         max_id = sql.get_scalar('SELECT MAX(id) FROM contexts')
#         max_msg_count = sql.get_scalar('SELECT COUNT(*) FROM contexts_messages WHERE context_id = ?', (max_id,))
#         if max_msg_count == 0:
#             sql.execute('DELETE FROM contexts WHERE id = ?', (max_id,))
#
#         sql.execute("INSERT INTO contexts (agent_id) VALUES (?)", (self.agent_id,))
#         self.message_history.context_id = sql.get_scalar(
#             "SELECT id FROM contexts WHERE agent_id = ? ORDER BY id DESC LIMIT 1", (self.agent_id,))
#         self.message_history.reload_context_messages()
#
#     def print_history(self, num_msgs=30):
#         pass
#         # for msg in self.message_history.get(msg_limit=num_msgs, pad_consecutive=False):
#         # tcolor = self.agent.config.get_value('system.termcolor_assistant') if msg['role'] == 'assistant' else None
#         # cprint(f"{msg['role'].upper()}: > {msg['content']}", tcolor)
#
#     def wait_until_current_role(self, role, not_equals=False):
#         while True:
#             last_msg = self.message_history.last()
#             if not last_msg: break
#
#             if (last_msg['role'] == role and not not_equals) or (last_msg['role'] != role and not_equals):
#                 break
#             else:
#                 time.sleep(0.05)
#                 continue
#
#     def generate_title(self):
#         user_msg = self.message_history.last(incl_roles=('user',))
#         if not user_msg:
#             return
#         user_msg = user_msg['content']
#         title = get_scalar(
#             prompt=f'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}',
#             model='gpt-3.5-turbo')
#         title = title.replace('\n', ' ').strip("'").strip('"')
#         sql.execute("UPDATE contexts SET summary = ? WHERE id = ?", (title, self.message_history.context_id))
#
#
# class MessageHistory:
#     def __init__(self, agent, context_id=None, agent_id=0):
#         self.agent = agent
#         self.agent_id = agent_id
#         self.context_id = context_id
#         self._messages = []  # [Message(m['id'], m['role'], m['content']) for m in (messages or [])]
#         self.reload_context_messages()
#
#     def reload_context_messages(self):
#         # IF NO CONTEXTS FOR AGENT, CREATE ONE
#         if sql.get_scalar("SELECT COUNT(*) FROM contexts WHERE agent_id = ?", (self.agent_id,)) == 0:
#             sql.execute("INSERT INTO contexts (id, agent_id) VALUES (NULL, ?)", (self.agent_id,))
#
#         if self.context_id is None:
#             self.context_id = sql.get_scalar("SELECT id FROM contexts WHERE agent_id = ? ORDER BY id DESC LIMIT 1",
#                                              (self.agent_id,))
#
#         msg_log = sql.get_results("""
# WITH RECURSIVE ContextTree AS (
#     -- Base case: Select the given leaf context and its parent context
#     SELECT c1.id AS context_id, c2.branch_msg_id AS child_context_branch_msg_id
#     FROM contexts c1
#     LEFT JOIN contexts c2 ON c1.id = c2.parent_id
#     WHERE c1.id = ?  -- Given leaf branch ID
#
#     UNION ALL
#
#     -- Recursive case: Select the parent context and its parent context
#     SELECT c1.parent_id, c1.branch_msg_id
#     FROM contexts c1
#     JOIN ContextTree ct ON c1.id = ct.context_id
#     WHERE c1.parent_id IS NOT NULL
# )
# SELECT tbl.id, tbl.role, tbl.msg, tbl.embedding_id
# FROM (
#     SELECT cm.id, cm.role, cm.msg, cm.embedding_id
#     FROM ContextTree ct
#     JOIN contexts_messages cm
#         ON ct.context_id = cm.context_id
#         AND (cm.id <= ct.child_context_branch_msg_id OR ct.child_context_branch_msg_id IS NULL)
#     ORDER BY cm.id DESC
#     LIMIT ?
# ) tbl
# ORDER BY tbl.id;
#         """, (self.context_id, self.agent.config.get('context.max_messages', 30),))
#
#         self._messages = [Message(msg_id, role, content, embedding_id) for msg_id, role, content, embedding_id in
#                           msg_log]
#
#     def add(self, role, content, embedding_id=None):
#         max_id = sql.get_scalar("SELECT COALESCE(MAX(id), 0) FROM contexts_messages")
#         new_msg = Message(max_id + 1, role, content, embedding_id=embedding_id)
#
#         if self.context_id is None:
#             raise Exception("No context ID set")
#
#         sql.execute("INSERT INTO contexts_messages (id, context_id, role, msg, embedding_id) VALUES (?, ?, ?, ?, ?)",
#                     (new_msg.id, self.context_id, role, content, new_msg.embedding_id))
#         self._messages.append(new_msg)
#
#         self.reload_context_messages()
#
#         # if self.count() > config.get_value('context.max-messages'):  # todo
#         #     self.pop(0)
#
#         return new_msg
#
#     def remove(self, n):
#         if len(self._messages) > 0:
#             sql.execute("""
#                 DELETE
#                 FROM contexts_messages
#                 WHERE id >= (
#                    SELECT
#                        id
#                    FROM
#                        contexts_messages
#                    WHERE
#                        role = "user" OR role = "assistant"
#                    ORDER BY id DESC
#                    LIMIT 1 OFFSET ?
#                 )""", (n - 1,))
#             self.reload_context_messages()
#
#     def get(self,
#             only_role_content=True,
#             incl_roles=('user', 'assistant'),
#             map_to=None,
#             llm_format=False,
#             msg_limit=8,
#             pad_consecutive=True,
#             from_msg_id=0):
#
#         def add_padding_to_consecutive_messages(msg_list):
#             result = []
#             last_seen_role = None
#             for msg in msg_list:
#                 if last_seen_role == msg['role'] and pad_consecutive and msg['role'] == 'assistant':
#                     pad_role = 'assistant' if msg['role'] == 'user' else 'user'
#                     pad_msg = Message(msg_id=0, role=pad_role, content='ok')
#                     result.append({
#                         'id': pad_msg.id,
#                         'role': pad_msg.role,
#                         'content': pad_msg.content,
#                         'embedding_id': pad_msg.embedding_id  # todo fixed id to reduce sql call count
#                     })
#                 elif last_seen_role == msg['role'] and pad_consecutive and msg['role'] == 'user':
#                     result[-1]['content'] = msg['content']
#                     continue
#
#                 result.append(msg)
#                 last_seen_role = msg['role']
#             return result
#
#         assistant_msg_prefix = self.agent.config.get('context.prefix_all_assistant_msgs')
#         if assistant_msg_prefix is None: assistant_msg_prefix = ''
#
#         pre_formatted_msgs = [{
#             'id': msg.id,
#             'role': msg.role,
#             'content': f"{assistant_msg_prefix} {msg.content}" if msg.role == 'assistant' and llm_format else msg.content,
#             'embedding_id': msg.embedding_id
#         } for msg in self._messages if msg.id >= from_msg_id
#                                        and (msg.role in incl_roles
#                                             or (llm_format
#                                                 and msg.role in ('output', 'code')
#                                                 )
#                                             )
#         ]
#         # Loop and replace all outputs role with 'function'
#         if llm_format:
#             formatted_msgs = []
#             last_ass_msg = None
#             for msg in pre_formatted_msgs:
#                 if msg['role'] == 'user':
#                     formatted_msgs.append(msg)
#                 elif msg['role'] == 'assistant':
#                     formatted_msgs.append(msg)
#                     last_ass_msg = formatted_msgs[-1]
#                 elif msg['role'] == 'output':
#                     msg['role'] = 'function'
#                     msg['name'] = 'execute'
#                     formatted_msgs.append(msg)
#                 elif msg['role'] == 'code':
#                     if last_ass_msg is None: continue
#                     last_ass_msg['content'] += f"\n{msg['content']}"
#
#             pre_formatted_msgs = formatted_msgs
#
#         # Apply padding between consecutive messages of same role
#         pre_formatted_msgs = add_padding_to_consecutive_messages(pre_formatted_msgs)
#         # check if limit is within
#         if len(pre_formatted_msgs) > msg_limit:
#             pre_formatted_msgs = pre_formatted_msgs[-msg_limit:]
#
#         # WHAT IS THIS ?
#         # if map_to is not None:
#         #     for msg in pre_formatted_msgs:
#         #         role_idx = incl_roles.index(msg['role'])
#         #         msg['role'] = map_to[role_idx]
#         if llm_format:
#             for msg in pre_formatted_msgs:
#                 accepted_keys = ('role', 'content', 'name')
#                 # pop each key if key not in list
#                 msg_keys = list(msg.keys())  # todo - optimise
#                 for key in msg_keys:
#                     if key not in accepted_keys:
#                         msg.pop(key)
#         #     return pre_formatted_msgs
#         #     # return [{'role': msg['role'], 'content': msg['content']} for msg in
#         #     #         pre_formatted_msgs]
#         # else:
#         return pre_formatted_msgs
#
#         # assistant_msg_prefix = config.get_value('context.prefix-all-assistant-msgs')
#         # formatted_msgs = []
#         # pad_count = 0
#         # for msg in self._messages:
#         #     if msg.role not in incl_roles: continue
#         #     if msg.id < from_msg_id: continue
#         #
#         #     if msg.role == 'assistant' and incl_assistant_prefix:
#         #         msg_content = f"{assistant_msg_prefix} {msg.content}"
#         #     else:
#         #         msg_content = msg.content
#         #
#         #     last_seen_role = formatted_msgs[-1]['role'] if len(formatted_msgs) > 0 else ''
#         #     if pad_consecutive and msg.role in ('user', 'assistant') and msg.role == last_seen_role:
#         #         pad_msg = Message(msg_id=0, role='user', content='ok')
#         #         formatted_msgs.append({
#         #             'id': pad_msg.id, 'role': pad_msg.role, 'content': pad_msg.content, 'embedding': pad_msg.embedding
#         #         })`3
#         #         pad_count += 1
#         #
#         #     formatted_msgs.append({
#         #         'id': msg.id, 'role': msg.role, 'content': msg_content, 'embedding': msg.embedding
#         #     })
#         #
#         # formatted_msgs = formatted_msgs[-(msg_limit + pad_count):]  # HACKY  - todo
#         # if only_role_content:
#         #     return [{'role': msg['role'], 'content': msg['content']}
#         #             for msg in formatted_msgs]
#         # else:
#         #     return formatted_msgs
#
#     def count(self, incl_roles=('user', 'assistant')):
#         return len([msg for msg in self._messages if msg.role in incl_roles])
#
#     def pop(self, indx, incl_roles=('user', 'assistant')):
#         seen_cnt = -1
#         for i, msg in enumerate(self._messages):
#             if msg.role not in incl_roles:
#                 continue
#             seen_cnt += 1
#             if seen_cnt == indx:
#                 return self._messages.pop(i)
#
#     def get_conversation_str(self, msg_limit=4, incl_roles=('user', 'assistant'), prefix='CONVERSATION:\n'):
#         msgs = self.get(msg_limit=msg_limit, incl_roles=incl_roles)
#         formatted_context = [f"{msg['role']}: `{msg['content'].strip()}`" for msg in msgs]
#         formatted_context[-1] = f""">> {formatted_context[-1]} <<"""
#         return prefix + '\n'.join(formatted_context)
#
#     def get_react_str(self, msg_limit=8, from_msg_id=None, prefix='THOUGHTS:\n'):
#         msgs = self.get(incl_roles=('thought', 'result'), msg_limit=msg_limit, from_msg_id=from_msg_id)
#         formatted_context = [f"{msg['role']}: `{msg['content'].strip()}`" for msg in msgs]
#         return prefix + '\n'.join(formatted_context)
#
#     def last(self, incl_roles=('user', 'assistant')):
#         msgs = self.get(incl_roles=incl_roles, only_role_content=False)
#         return msgs[-1] if len(msgs) > 0 else None
#
#     def last_role(self):
#         last = self.last()
#         if last is None:
#             return ''
#         return last['role']
#
#     def last_id(self):
#         last = self.last()
#         if last is None:
#             return 0
#         return last['id']
#
#
# class Message:
#     def __init__(self, msg_id, role, content, embedding_id=None):  # , unix_time=None):
#         self.id = msg_id
#         self.role = role
#         self.content = content
#         self.token_count = len(tiktoken.encoding_for_model("gpt-3.5-turbo").encode(content))
#         # self.unix_time = unix_time or int(time.time())
#         self.embedding_id = embedding_id
#         # if self.embedding_id and isinstance(self.embedding, str):
#         #     self.embedding = embeddings.string_embeddings_to_array(self.embedding)
#         self.embedding_data = None
#         if self.embedding_id is None:
#             if role == 'user' or role == 'assistant' or role == 'request' or role == 'result':
#                 self.embedding_id, self.embedding_data = embeddings.get_embedding(content)
#
#     def change_content(self, new_content):
#         self.content = new_content
#         self.token_count = len(tiktoken.encoding_for_model("gpt-3.5-turbo").encode(new_content))
#         self.embedding = embeddings.get_embedding(new_content)
#         sql.execute(f"UPDATE contexts_messages SET msg = '{new_content}' WHERE id = {self.id}")
#     # def __repr__(self):
#     #     return f"{self.role}: {self.content}"
