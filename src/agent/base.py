import json
import logging
import re
import time
import string
import asyncio
from queue import Queue
import src.agent.speech as speech
from src.operations import task
from src.utils import sql, logs, helpers
from src.utils.apis import llm
from src.context.member import Member


class Agent(Member):
    def __init__(self, main=None, agent_id=0, member_id=None, workflow=None, wake=False, inputs=None):
        super().__init__(main=main, workflow=workflow, m_id=member_id, inputs=inputs)
        self.workflow = workflow
        self.id = agent_id
        self.member_id = member_id
        self.name = ''
        self.desc = ''
        self.speaker = None
        self.voice_data = None
        self.config = {}
        self.instance_config = {}

        self.intermediate_task_responses = Queue()
        self.speech_lock = asyncio.Lock()

        self.logging_obj = None
        self.active_task = None

        self.new_bubble_callback = None

        self.latest_analysed_msg_id = 0

        self.bg_task = None
        if wake:
            self.bg_task = self.workflow.loop.create_task(self.wake())

    async def wake(self):
        bg_tasks = [
            # self.speaker.download_voices(),
            # self.speaker.speak_voices(),
            # # self.__intermediate_response_thread(),
            # # self.loop.create_task(self.listener.listen())
        ]
        await asyncio.gather(*bg_tasks)

    def __del__(self):
        if self.bg_task:
            self.bg_task.cancel()

    # async def __intermediate_response_thread(self):
    #     while True:
    #         await asyncio.sleep(0.03)
    #         if self.speech_lock.locked():
    #             continue
    #         if self.intermediate_task_responses.empty():
    #             continue
    #
    #         async with self.speech_lock:
    #             response_str = self.format_message(self.intermediate_task_responses.get())
    #             self.get_response(extra_prompt=response_str,
    #                               check_for_tasks=False)

    def load_agent(self):
        logging.debug(f'LOAD AGENT {self.id}')
        if self.member_id:
            agent_data = sql.get_results("""
                SELECT
                    cm.`agent_config`,
                    s.`value` AS `global_config`
                FROM contexts_members cm
                LEFT JOIN settings s 
                    ON s.field = 'global_config'
                WHERE cm.id = ? """, (self.member_id,))[0]
        elif self.id > 0:
            agent_data = sql.get_results("""
                SELECT
                    a.`config`,
                    s.`value` AS `global_config`
                FROM agents a
                LEFT JOIN settings s ON s.field = 'global_config'
                WHERE a.id = ? """, (self.id,))[0]
        else:
            agent_data = sql.get_results("""
                SELECT
                    '{}',
                    s.`value` AS `global_config`
                FROM settings s
                WHERE s.field = 'global_config' """)[0]

        agent_config = json.loads(agent_data[0])
        global_config = json.loads(agent_data[1])

        self.name = agent_config.get('info.name', 'Assistant')
        self.config = {**global_config, **agent_config}
        found_instance_config = {k.replace('instance.', ''): v for k, v in self.config.items() if
                                k.startswith('instance.')}
        self.instance_config = {**self.instance_config, **found_instance_config}  # todo

        voice_id = self.config.get('voice.current_id', None)
        if voice_id is not None and str(voice_id) != '0':  # todo dirty
            self.voice_data = sql.get_results("""
                SELECT
                    v.id,
                    v.api_id,
                    v.uuid,
                    v.display_name,
                    v.known_from,
                    v.creator,
                    v.lang,
                    v.verb
                FROM voices v
                WHERE v.id = ? """, (voice_id,))[0]
        else:
            self.voice_data = None

        # if self.speaker is not None: self.speaker.kill()
        # self.speaker = None  # speech.Stream_Speak(self)  todo

    def system_message(self, msgs_in_system=None, response_instruction='', msgs_in_system_len=0):
        date = time.strftime("%a, %b %d, %Y", time.localtime())
        time_ = time.strftime("%I:%M %p", time.localtime())
        timezone = time.strftime("%Z", time.localtime())
        location = "Sheffield, UK"

        member_names = {k: v.get('info.name', 'Assistant') for k, v in self.workflow.member_configs.items()}
        member_placeholders = {k: v.get('group.output_context_placeholder', f'{member_names[k]}_{str(k)}')
                               for k, v in self.workflow.member_configs.items()}
        member_last_outputs = {member.m_id: member.last_output for k, member in self.workflow.members.items() if member.last_output != ''}
        member_blocks_dict = {member_placeholders[k]: v for k, v in member_last_outputs.items()}
        context_blocks_dict = {k: v for k, v in self.workflow.main.system.blocks.to_dict().items()}

        blocks_dict = helpers.SafeDict({**member_blocks_dict, **context_blocks_dict})

        semi_formatted_sys_msg = string.Formatter().vformat(
            self.config.get('context.sys_msg', ''), (), blocks_dict,
        )

        agent_name = self.config.get('info.name', 'Assistant')
        if self.voice_data:
            char_name = re.sub(r'\([^)]*\)', '', self.voice_data[3]).strip()
            full_name = f"{char_name} from {self.voice_data[4]}" if self.voice_data[4] != '' else char_name
            verb = self.voice_data[7]
            if verb != '': verb = ' ' + verb
        else:
            char_name = agent_name
            full_name = agent_name
            verb = ''

        # ungrouped_actions = [fk for fk, fv in retrieval.all_category_files['_Uncategorised'].all_actions_data.items()]
        # action_groups = [k for k, v in retrieval.all_category_files.items() if not k.startswith('_')]
        all_actions = []  # ungrouped_actions + action_groups

        response_type = self.config.get('context.response_type', 'response')

        # Use the SafeDict class to format the text to gracefully allow non existent keys
        final_formatted_sys_msg = string.Formatter().vformat(
            semi_formatted_sys_msg, (), helpers.SafeDict(
                agent_name=agent_name,
                char_name=char_name,
                full_name=full_name,
                verb=verb,
                actions=', '.join(all_actions),
                response_instruction=response_instruction.strip(),
                date=date,
                time=time_,
                timezone=timezone,
                location=location,
                response_type=response_type
            )
        )

        message_str = ''
        if msgs_in_system:
            if msgs_in_system_len > 0:
                msgs_in_system = msgs_in_system[-msgs_in_system_len:]
            message_str = "\n".join(
                f"""{msg['role']}: \"{msg['content'].strip().strip('"')}\"""" for msg in msgs_in_system)
            message_str = f"\n\nCONVERSATION:\n\n{message_str}\nassistant: "
        if response_instruction != '':
            response_instruction = f"\n\n{response_instruction}\n\n"

        return final_formatted_sys_msg + response_instruction + message_str

    def format_message(self, message):
        dialogue_placeholders = {
            '[RES]': '[ITSOC] very briefly respond to the user in no more than [3S] ',
            '[INF]': '[ITSOC] very briefly inform the user in no more than [3S] ',
            '[ANS]': '[ITSOC] very briefly respond to the user considering the following information: ',
            '[Q]': '[ITSOC] Ask the user the following question: ',
            '[SAY]': '[ITSOC], say: ',
            '[MI]': '[ITSOC] Ask for the following information: ',
            '[ITSOC]': 'In the style of {char_name}{verb}, spoken like a genuine dialogue ',
            '[WOFA]': 'Without offering any further assistance, ',
            '[3S]': 'Three sentences',
        }
        for k, v in dialogue_placeholders.items():
            message = message.replace(k, v)

        if message != '':
            message = f"[INSTRUCTIONS-FOR-NEXT-RESPONSE]\n{message}\n[/INSTRUCTIONS-FOR-NEXT-RESPONSE]"
        return message

    async def run_member(self):
        """The entry response method for the member."""
        for key, chunk in self.receive(stream=True):
            if self.workflow.stop_requested:
                self.workflow.stop_requested = False
                break
            if key == 'assistant':
                self.main.new_sentence_signal.emit(self.m_id, chunk)

    def receive(self, stream=False):
        return self.get_response_stream() if stream else self.get_response()

    def get_response(self):
        response = ''
        for key, chunk in self.get_response_stream():
            response += chunk or ''
        return response

    def get_response_stream(self, extra_prompt='', msgs_in_system=False):
        messages = self.workflow.message_history.get(llm_format=True, calling_member_id=self.member_id)
        use_msgs_in_system = messages if msgs_in_system else None
        system_msg = self.system_message(msgs_in_system=use_msgs_in_system,
                                         response_instruction=extra_prompt)
        model_name = self.config.get('context.model', 'gpt-3.5-turbo')
        model = (model_name, self.workflow.main.system.models.to_dict()[model_name])

        kwargs = dict(messages=messages, msgs_in_system=msgs_in_system, system_msg=system_msg, model=model)
        stream = self.stream(**kwargs)

        response = ''

        for key, chunk in stream:
            if key == 'assistant':
                response += chunk or ''
                yield key, chunk
            elif key == 'tools':
                all_tools = chunk
                for tool_name, tool_args in all_tools.items():
                    tool_name = tool_name.replace('_', ' ').capitalize()
                    self.workflow.save_message('tool', tool_name, self.member_id, self.logging_obj)
        # response = 'k'
        if response != '':
            self.workflow.save_message('assistant', response, self.member_id, self.logging_obj)

    def stream(self, messages, msgs_in_system=False, system_msg='', model=None):
        tools = self.get_function_call_tools()
        stream = llm.get_chat_response(messages if not msgs_in_system else [],
                                       system_msg,
                                       model_obj=model,
                                       tools=tools)
        self.logging_obj = stream.logging_obj

        collected_tools = {}
        current_tool_name = None
        current_args = ''

        for resp in stream:
            delta = resp.choices[0].get('delta', {})
            if not delta:
                continue
            tool_calls = delta.get('tool_calls', None)
            content = delta.get('content', '')
            if tool_calls:
                tool_name = tool_calls[0].function.name
                if tool_name:
                    if current_tool_name is not None:
                        collected_tools[current_tool_name] = current_args
                    current_tool_name = tool_name
                    current_args = ''
                else:
                    current_args += tool_calls[0].function.arguments

            else:
                yield 'assistant', content or ''

        if current_tool_name is not None:
            collected_tools[current_tool_name] = current_args

        if len(collected_tools) > 0:
            yield 'tools', collected_tools
        # else:
        #     raise NotImplementedError('No message or tool calls were returned from the model')

    def get_agent_tools(self, method='Function call'):
        agent_tools = json.loads(self.config.get('tools.data', '[]'))
        agent_tools_ids = [tool['id'] for tool in agent_tools]
        if len(agent_tools_ids) == 0:
            return []

        tools = sql.get_results(f"""
            SELECT
                name,
                config
            FROM tools
            WHERE 
                -- json_extract(config, '$.method') = ? AND
                id IN ({','.join(['?'] * len(agent_tools_ids))})
        """, agent_tools_ids)

        return tools

    def get_function_call_tools(self):
        tools = self.get_agent_tools(method='Function call')
        formatted_tools = []

        for tool_name, tool_config in tools:
            # Parse parameters data
            tool_config = json.loads(tool_config)
            parameters_data = tool_config.get('parameters.data', '[]')
            transformed_parameters = self.transform_parameters(parameters_data)

            # Append the transformed function configuration
            formatted_tools.append(
                {
                    'type': 'function',
                    'function': {
                        'name': tool_name.lower().replace(' ', '_'),
                        'description': tool_config.get('description', ''),
                        'parameters': transformed_parameters
                    }
                }
            )

        return formatted_tools

    def transform_parameters(self, parameters_data):
        """Transform the parameter data from the input format to the output format."""
        # Load the parameters as a JSON object
        parameters = json.loads(parameters_data)

        # Initialize the transformation
        transformed = {
            'type': 'object',
            'properties': {},
            'required': []
        }

        # Iterate through each parameter and convert it
        for parameter in parameters:
            param_name = parameter['name'].lower().replace(' ', '_')
            param_desc = parameter['description']
            param_type = parameter['type'].lower()
            param_required = parameter['req']
            param_default = parameter['default']

            # Build the parameter schema
            transformed['properties'][param_name] = {
                'type': param_type,
                'description': param_desc,
            }
            if param_required:
                transformed['required'].append(param_name)

        return transformed

    def update_instance_config(self, field, value):
        self.instance_config[field] = value
        sql.execute(f"""UPDATE contexts_members SET agent_config = json_set(agent_config, '$."instance.{field}"', ?) WHERE id = ?""",
                    (value, self.member_id))

    # def combine_lang_and_code(self, lang, code):
    #     return f'```{lang}\n{code}\n```'
    # def __wait_until_finished_speaking(self):
    #     while True:
    #         if not self.speaker.speaking: break
    #         time.sleep(0.05)
