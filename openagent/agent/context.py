import time
import tiktoken
from termcolor import cprint
from utils import sql, embeddings


class Context:
    def __init__(self, agent, agent_id=0, context_id=None):
        self.agent = agent
        if agent_id is None and context_id is None:
            latest_context = sql.get_results('SELECT id, agent_id FROM contexts ORDER BY id DESC LIMIT 1', return_type='rtuple')
            if latest_context:
                context_id, agent_id = latest_context
            else:
                agent_id = 0
        elif agent_id is not None:
            context_id = sql.get_scalar('SELECT id FROM contexts WHERE agent_id = ? ORDER BY id DESC LIMIT 1', (agent_id,))
        elif context_id is not None:
            agent_id = sql.get_scalar('SELECT agent_id FROM contexts WHERE id = ?', (context_id,))

        self.agent_id = agent_id
        self.message_history = MessageHistory(agent=self.agent, agent_id=agent_id, context_id=context_id)
        # self.behaviour = behaviour
        # self.recent_actions = []

    def new_context(self, parent_id=None):  # todo
        # get count of contexts_messages in last context
        msg_count = sql.get_scalar('SELECT COUNT(*) FROM contexts_messages WHERE context_id = ?', (self.message_history.context_id,))
        if msg_count == 0:
            return
        sql.execute("INSERT INTO contexts (agent_id) VALUES (?)", (self.agent_id,))
        self.message_history.context_id = sql.get_scalar("SELECT id FROM contexts WHERE agent_id = ? ORDER BY id DESC LIMIT 1", (self.agent_id,))
        self.message_history.reload_context_messages()

    # def change_context(self, context_id):
    #     self.message_history.context_id = context_id
    #     self.message_history.reload_context_messages()

    def print_history(self, num_msgs=30):
        for msg in self.message_history.get(msg_limit=num_msgs, pad_consecutive=False):
            tcolor = self.agent.config.get_value('system.termcolor_assistant') if msg['role'] == 'assistant' else None
            cprint(f"{msg['role'].upper()}: > {msg['content']}", tcolor)

    def wait_until_current_role(self, role, not_equals=False):
        while True:
            last_msg = self.message_history.last()
            if not last_msg: break

            if (last_msg['role'] == role and not not_equals) or (last_msg['role'] != role and not_equals):
                break
            else:
                time.sleep(0.05)
                continue


class MessageHistory:
    def __init__(self, agent, context_id=None, agent_id=0):
        self.agent = agent
        self.agent_id = agent_id
        self.context_id = context_id
        self._messages = []  # [Message(m['id'], m['role'], m['content']) for m in (messages or [])]
        self.reload_context_messages()

    def reload_context_messages(self):
        # IF NO CONTEXTS FOR AGENT, CREATE ONE
        if sql.get_scalar("SELECT COUNT(*) FROM contexts WHERE agent_id = ?", (self.agent_id,)) == 0:
            sql.execute("INSERT INTO contexts (id, agent_id) VALUES (NULL, ?)", (self.agent_id,))

        if self.context_id is None:
            self.context_id = sql.get_scalar("SELECT id FROM contexts WHERE agent_id = ? ORDER BY id DESC LIMIT 1", (self.agent_id,))

        msg_log = sql.get_results("""
WITH RECURSIVE ContextTree AS (
    -- Base case: Select the given leaf context and its parent context
    SELECT c1.id AS context_id, c2.branch_msg_id AS child_context_branch_msg_id
    FROM contexts c1
    LEFT JOIN contexts c2 ON c1.id = c2.parent_id
    WHERE c1.id = ?  -- Given leaf branch ID
    
    UNION ALL
    
    -- Recursive case: Select the parent context and its parent context
    SELECT c1.parent_id, c1.branch_msg_id
    FROM contexts c1
    JOIN ContextTree ct ON c1.id = ct.context_id
    WHERE c1.parent_id IS NOT NULL
)
SELECT tbl.id, tbl.role, tbl.msg, tbl.embedding_id
FROM (
    SELECT cm.id, cm.role, cm.msg, cm.embedding_id
    FROM ContextTree ct
    JOIN contexts_messages cm 
        ON ct.context_id = cm.context_id 
        AND (cm.id <= ct.child_context_branch_msg_id OR ct.child_context_branch_msg_id IS NULL)
    ORDER BY cm.id DESC
    LIMIT ?
) tbl
ORDER BY tbl.id;
        """, (self.context_id, self.agent.config.get('context.max_messages'),))

        self._messages = [Message(msg_id, role, content, embedding_id) for msg_id, role, content, embedding_id in msg_log]

    def add(self, role, content, embedding_id=None):
        max_id = sql.get_scalar("SELECT COALESCE(MAX(id), 0) FROM contexts_messages")
        new_msg = Message(max_id + 1, role, content, embedding_id=embedding_id)

        if self.context_id is None:
            raise Exception("No context ID set")

        sql.execute("INSERT INTO contexts_messages (id, context_id, role, msg, embedding_id) VALUES (?, ?, ?, ?, ?)",
                    (new_msg.id, self.context_id, role, content, new_msg.embedding_id))
        self._messages.append(new_msg)

        self.reload_context_messages()

        # if self.count() > config.get_value('context.max-messages'):  # todo
        #     self.pop(0)

        return new_msg

    def remove(self, n):
        if len(self._messages) > 0:
            sql.execute("""
                DELETE 
                FROM contexts_messages 
                WHERE id >= (
                   SELECT 
                       id 
                   FROM 
                       contexts_messages 
                   WHERE 
                       role = "user" OR role = "assistant" 
                   ORDER BY id DESC 
                   LIMIT 1 OFFSET ?
                )""", (n - 1,))
            self.reload_context_messages()

    def get(self,
            only_role_content=True,
            incl_roles=('user', 'assistant'),
            map_to=None,
            llm_format=False,
            msg_limit=8,
            pad_consecutive=True,
            from_msg_id=0):

        def add_padding_to_consecutive_messages(msg_list):
            result = []
            last_seen_role = None
            for msg in msg_list:
                if last_seen_role == msg['role'] and pad_consecutive and msg['role'] == 'assistant':
                    pad_role = 'assistant' if msg['role'] == 'user' else 'user'
                    pad_msg = Message(msg_id=0, role=pad_role, content='ok')
                    result.append({
                        'id': pad_msg.id,
                        'role': pad_msg.role,
                        'content': pad_msg.content,
                        'embedding_id': pad_msg.embedding_id  # todo fixed id to reduce sql call count
                    })
                elif last_seen_role == msg['role'] and pad_consecutive and msg['role'] == 'user':
                    result[-1]['content'] = msg['content']
                    continue

                result.append(msg)
                last_seen_role = msg['role']
            return result

        assistant_msg_prefix = self.agent.config.get('context.prefix_all_assistant_msgs')
        if assistant_msg_prefix is None: assistant_msg_prefix = ''

        pre_formatted_msgs = [{
            'id': msg.id,
            'role': msg.role,
            'content': f"{assistant_msg_prefix} {msg.content}" if msg.role == 'assistant' and llm_format else msg.content,
            'embedding_id': msg.embedding_id
        } for msg in self._messages if msg.id >= from_msg_id
                                       and (msg.role in incl_roles
                                            or (llm_format
                                                and msg.role in ('output', 'code')
                                                )
                                            )
        ]
        # Loop and replace all outputs role with 'function'
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

        # WHAT IS THIS ?
        # if map_to is not None:
        #     for msg in pre_formatted_msgs:
        #         role_idx = incl_roles.index(msg['role'])
        #         msg['role'] = map_to[role_idx]
        if llm_format:
            for msg in pre_formatted_msgs:
                accepted_keys = ('role', 'content', 'name')
                # pop each key if key not in list
                msg_keys = list(msg.keys())  # todo - optimise
                for key in msg_keys:
                    if key not in accepted_keys:
                        msg.pop(key)
        #     return pre_formatted_msgs
        #     # return [{'role': msg['role'], 'content': msg['content']} for msg in
        #     #         pre_formatted_msgs]
        # else:
        return pre_formatted_msgs

        # assistant_msg_prefix = config.get_value('context.prefix-all-assistant-msgs')
        # formatted_msgs = []
        # pad_count = 0
        # for msg in self._messages:
        #     if msg.role not in incl_roles: continue
        #     if msg.id < from_msg_id: continue
        #
        #     if msg.role == 'assistant' and incl_assistant_prefix:
        #         msg_content = f"{assistant_msg_prefix} {msg.content}"
        #     else:
        #         msg_content = msg.content
        #
        #     last_seen_role = formatted_msgs[-1]['role'] if len(formatted_msgs) > 0 else ''
        #     if pad_consecutive and msg.role in ('user', 'assistant') and msg.role == last_seen_role:
        #         pad_msg = Message(msg_id=0, role='user', content='ok')
        #         formatted_msgs.append({
        #             'id': pad_msg.id, 'role': pad_msg.role, 'content': pad_msg.content, 'embedding': pad_msg.embedding
        #         })`3
        #         pad_count += 1
        #
        #     formatted_msgs.append({
        #         'id': msg.id, 'role': msg.role, 'content': msg_content, 'embedding': msg.embedding
        #     })
        #
        # formatted_msgs = formatted_msgs[-(msg_limit + pad_count):]  # HACKY  - todo
        # if only_role_content:
        #     return [{'role': msg['role'], 'content': msg['content']}
        #             for msg in formatted_msgs]
        # else:
        #     return formatted_msgs

    def count(self, incl_roles=('user', 'assistant')):
        return len([msg for msg in self._messages if msg.role in incl_roles])

    def pop(self, indx, incl_roles=('user', 'assistant')):
        seen_cnt = -1
        for i, msg in enumerate(self._messages):
            if msg.role not in incl_roles:
                continue
            seen_cnt += 1
            if seen_cnt == indx:
                return self._messages.pop(i)

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
        msgs = self.get(incl_roles=incl_roles, only_role_content=False)
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
    def __init__(self, msg_id, role, content, embedding_id=None):  # , unix_time=None):
        self.id = msg_id
        self.role = role
        self.content = content
        self.token_count = len(tiktoken.encoding_for_model("gpt-3.5-turbo").encode(content))
        # self.unix_time = unix_time or int(time.time())
        self.embedding_id = embedding_id
        # if self.embedding_id and isinstance(self.embedding, str):
        #     self.embedding = embeddings.string_embeddings_to_array(self.embedding)
        self.embedding_data = None
        if role == 'user' or role == 'assistant' or role == 'request' or role == 'result':
            self.embedding_id, self.embedding_data = embeddings.get_embedding(content)

    def change_content(self, new_content):
        self.content = new_content
        self.token_count = len(tiktoken.encoding_for_model("gpt-3.5-turbo").encode(new_content))
        self.embedding = embeddings.get_embedding(new_content)
        sql.execute(f"UPDATE contexts_messages SET msg = '{new_content}' WHERE id = {self.id}")
    # def __repr__(self):
    #     return f"{self.role}: {self.content}"
