import re
import time

from termcolor import colored
from utils.apis import oai
from agent.context import Context
from utils import logs, config, semantic, embeddings
from utils.helpers import remove_brackets
from operations import retrieval


class Task:
    def __init__(self, agent, messages=None, parent_react=None):
        # self.task_context = Context(messages=messages)
        self.agent = agent
        self.status = TaskStatus.INITIALISING
        self.time_expression = None
        self.recurring = False
        self.parent_react = parent_react
        self.react = None
        self.actions = []
        self.action_methods = []
        self.current_action_index = 0
        last_msg = agent.context.message_history.last()
        self.objective = last_msg['content']
        self.root_msg_id = last_msg['id']

        react_enabled = config.get_value('react.enabled')
        always_use_react = config.get_value('react.always-use-react')
        validate_guess = config.get_value('actions.validate-decision') if not always_use_react else False

        if self.parent_react is not None:
            react_enabled = False
            validate_guess = False

        actions = self.get_action_guess()
        if self.status == TaskStatus.CANCELLED:
            return

        is_guess_valid = True

        if not react_enabled or (react_enabled and not always_use_react):
            is_guess_valid = self.validate_guess(actions) if validate_guess else True
            if is_guess_valid:
                self.actions = actions
                self.action_methods = [action.run_action() for action in self.actions]
            # else:
            #     on_invalid = config.get_value(actions']['on-invalid-guess']
            #     if on_invalid == 'CANCEL':
            #     if on_invalid == 'CANCEL':
            #         self.status = TaskStatus.CANCELLED
        if react_enabled and (always_use_react or not is_guess_valid):
            self.react = ExplicitReAct(self)

        if self.status != TaskStatus.CANCELLED:
            logs.insert_log('TASK CREATED', self.fingerprint())

    def fingerprint(self, _type='name', delimiter=','):
        if _type == 'name':
            return delimiter.join([action.__class__.__name__ for action in self.actions])
        elif _type == 'desc':
            return delimiter.join([action.desc for action in self.actions])
        elif _type == 'result':
            return delimiter.join([action.result for action in self.actions])
        else:
            raise Exception(f'Unknown fingerprint type: {_type}')

    def validate_guess(self, actions):
        if len(actions) != 1:
            return False
        conversation_str = self.agent.context.message_history.get_conversation_str(msg_limit=2)
        action_str = 'ACTION PLAN OVERVIEW:\nOrder, Action\n----------------\n'\
            + ',\n'.join(f'{actions.index(action) + 1}: {getattr(action, "desc", action.__class__.__name__)}' for action in actions)
        validator_response = oai.get_scalar(f"""
Analyze the provided conversation and action plan overview and return a boolean ('TRUE' or 'FALSE') indicating whether or not the user's request can been fully satisfied given the actions.
The actions may have undisclosed parameters, which aren't shown in this action plan overview.
An action parameter may be time based, and can natively understand expressions of time.
Use the following conversation to guide your analysis. The last user message (denoted with arrows ">> ... <<") is the message with the user request.
The preceding assistant messages are provided to give you context for the users request.

{conversation_str}

{action_str}

Considering the action plan overview, can the users request be fully satisfied?
If more actions are needed to fully satisfy the request, return 'FALSE'.
If the request can be fully satisfied using only these actions, return 'TRUE'.
""", single_line=True)  # If FALSE, explain why
        if config.get_value('system.debug'):
            logs.insert_log('VALIDATOR RESPONSE', validator_response)
        return validator_response == 'TRUE'

    def get_action_guess(self):
        last_2_msgs = self.agent.context.message_history.get(only_role_content=False, msg_limit=2)
        action_data_list = retrieval.match_request(last_2_msgs)

        collected_actions = self.prompt_list_choice(action_data_list)
        if collected_actions:
            actions = [action_class(self.agent) for action_class in collected_actions]
            return actions

        self.status = TaskStatus.CANCELLED
        return None

    def prompt_list_choice(self, action_data_list):
        action_lookback_msg_cnt = config.get_value('actions.action-lookback-msg-count')
        if self.parent_react:
            conversation_str = self.agent.context.message_history.get_conversation_str(msg_limit=1,
                                                                                       incl_roles=('thought', 'result'),
                                                                                       prefix='CONTEXT:\n')
        else:
            conversation_str = self.agent.context.message_history.get_conversation_str(msg_limit=action_lookback_msg_cnt)

        action_str = ',\n'.join(f'{action_data_list.index(act_data) + 1}: {act_data.desc}'
                                for act_data in action_data_list)

# CONTEXT INFORMATION:
# - 'agent sims' is an installed desktop application that allows you to create and customize characters.
        # Note: To identify the primary action in the last request, focus on the main verb that indicates the current or next immediate action the speaker intends to take. Consider the verb's tense to prioritize actions that are planned or ongoing over those that are completed or auxiliary. Disregard actions that are merely described or implied without being the central focus of the current intention.
        # The verb expressing the main action in the sentence is crucial to making the right choice. If a secondary action or condition is described, it should not take precedence over the main action indicated in the last request. Focusing particularly on the tense to identify the valid - yet to be performed - action.
        context_type = 'messages' if self.parent_react else 'conversation'
        last_entity = 'message' if self.parent_react else 'user message'
        prompt = f"""Analyze the provided {context_type} and actions/detections list and if appropriate, return the ID of the most valid Action/Detection based on the last {last_entity}. If none are valid then return "0".

ACTIONS/DETECTIONS LIST:
ID: Description
____________________
0: NO ACTION TO TAKE AND NOTHING DETECTED
{action_str}

Use the following {context_type} to guide your analysis. The last {last_entity} (denoted with arrows ">> ... <<") is the {last_entity} you will use to determine the most valid ID.
The preceding assistant messages are provided to give you context for the last {last_entity}, to determine whether an action/detection is valid.
The higher the ID, the more probable that this is the correct action/detection, however this may not always be the case.

{conversation_str}

TASK:
Examine the {context_type} in detail, applying logic and reasoning to ascertain the most valid ID based on the latest {last_entity}.
If no actions or detections from the list are valid based on the last {last_entity}, simply output "0". 

(Give an explanation of your decision after on the same line in parenthesis)
ID: """
# If it seems like there should be further action(s) to take, but it is not in the list, then add a question mark to the comma separated list (e.g. "1,3,5,?").
        response = oai.get_scalar(prompt, single_line=True)
        # response = re.sub(r'[^0-9,]', '', response)  # this regex removes all non-numeric characters except commas

        response = re.sub(r'([0-9]+).*', r'\1', response)  # this regex only keeps the first integer found in the string
        action_ids = [int(x) for x in response.split(',') if x != '' and int(x) > 0]

        actions = [action_data_list[x - 1].clss for x in action_ids if x <= len(action_data_list)]
        none_existing = [x for x in action_ids if x > len(action_data_list)]
        if none_existing:
            print(f"IDs {none_existing} do not exist in the list and will be ignored.")
        return actions

    def run(self):
        if self.react is not None:
            return self.react.run()

        task_response = ''
        self.status = TaskStatus.RUNNING
        for action_indx, action in enumerate(self.actions):
            # If action is already done, continue
            if action_indx < self.current_action_index:
                continue

            action.extract_inputs()

            if action.cancelled:
                self.status = TaskStatus.CANCELLED
                break

            if action.can_run():  # or force_run:
                action_method = self.action_methods[action_indx]
                try:
                    action_result = next(action_method)
                except StopIteration:
                    continue
                    # todo add action error handling
                    # action_result = None

                response = action_result.response
                if not isinstance(response, str):
                    raise Exception('Response must be a string')

                if '[MI]' in response:
                    response = response.replace('[MI]', action.get_missing_inputs_string())
                if config.get_value('system.debug'):
                    logs.insert_log(f"TASK {'FINISHED' if action_result.code == 200 else 'MESSAGE'}", response)

                if self.parent_react is None or action_result.code != 200:
                    task_response = remove_brackets(response, '(')

                if action_result.code == 200:
                    action.result = response  # remove_brackets(response, '[')
                    self.current_action_index += 1
                else:
                    self.status = TaskStatus.FAILED if action_result.code == 500 else TaskStatus.PAUSED
                    break
            else:
                task_response = action.get_missing_inputs_string()
                self.status = TaskStatus.PAUSED
                break

        if self.status == TaskStatus.RUNNING:
            self.status = TaskStatus.COMPLETED
            logs.insert_log('TASK FINISHED', self.fingerprint(), print_=False)
            time.sleep(0.2)
            return True, task_response
        elif self.status == TaskStatus.PAUSED:
            return False, task_response
        else:
            return True, task_response

        # if self.recurring:
        #     self.status = TaskStatus.SCHEDULED
        #     # self.task_context.  # todo - reschedule task
        #     self.actions = []

    def is_duplicate_action(self):
        return any([action.is_duplicate_action() for action in self.actions])


class ExplicitReAct:
    def __init__(self, parent_task):
        self.parent_task = parent_task
        self.request_task = None
        self.thought_count = 0
        self.react_context = Context()

        self.thoughts = []
        self.actions = []
        self.results = []
        self.last_thought_embedding = None
        self.last_result_embedding = None

        self.objective = self.parent_task.objective
        conversation_str = self.parent_task.agent.context.message_history.get_conversation_str(msg_limit=2)

        # objective_str = f'Task: {self.objective}\nRequest: ' if self.objective else 'Task: '
        self.prompt = f"""
You are completing a task by breaking it down into smaller actions that are explicitly expressed in the task.
You have access to a wide range of actions, which you will search through and select after each thought message, unless the task is complete or can not complete.

If all elements of the task have been completed then return the thought: "TASK COMPLETED"
Conversely, if an element of the task can not be completed then return the thought: "CAN NOT COMPLETE"
Otherwise, return a thought that is a description of the next action to take verbatim from the task Assistant.

-- EXAMPLE OUTPUTS --

Task: what is the x
Thought: I need to get the x
Action: Get the x
Result: The x is [x_val]
Thought: TASK COMPLETED
END


Task: what is x
Thought: I need to get x
Action: Get x
Result: There is no x
Thought: CAN NOT COMPLETE
END


Task: set x to y
Thought: First, I need to get y
Action: Get y
Result: y is [y_val]
Thought: Now, I need to set x to [y_val]
Action: Set x to [y_val]
Result: I have set x to [y_val]
Thought: TASK COMPLETED
END


Task: do x and y
Thought: First, I need to do x
Action: Do x
Result: I have done x
Thought: Now, I need to do y
Action: Do y
Result: There was an error doing y
Thought: CAN NOT COMPLETE
END


Task: send a x with the y of z
Thought: First, I need to get the y of z
Action Get the y of z
Result: The y of z is [yz_val]
Thought: Now, I need to send a x with [yz_val]
Action: Send a x with [yz_val]
Result: I have sent a x with [yz_val]
Thought: TASK COMPLETED
END

Use the following conversation as context. The last user message (denoted with arrows ">> ... <<") is the message that triggered the task.
The preceding assistant messages are provided to give you context for the last user message.

{conversation_str}

Only return the next thought message. The Action and Result will be returned automatically.
        
Task: {self.objective}
Thought: """
        # self.react_context = {'role': 'Task', 'content': objective}

    def run(self):
        max_steps = config.get_value('react.max-steps')
        for i in range(max_steps - self.thought_count):
            if self.request_task is None:
                request = self.get_thought()
                if 'task completed' in request.lower():
                    fin_response = self.results[-1] if len(self.results) == 1 else f"""[SAY] "The task has been completed" (Task = `{self.parent_task.objective}`)"""
                    return True, fin_response
                elif 'can not complete' in request.lower():
                    fin_response = self.results[-1] if len(self.results) == 1 else f"""[SAY] "I can not complete the task" (Task = `{self.parent_task.objective}`)"""
                    return True, fin_response

                self.request_task = Task(agent=self.parent_task.agent,
                                         messages=[{'id': 0, 'role': 'user', 'content': request}],
                                         parent_react=self)
            try:
                request_finished, request_response = self.request_task.run()
                if request_finished:
                    self.save_action(self.request_task.fingerprint(_type='desc'))
                    self.save_result(self.request_task.fingerprint(_type='result'))
                    self.request_task = None
                else:
                    return False, request_response

            except Exception as e:
                logs.insert_log('TASK_ERROR', str(e))
                return True, f'[SAY] "I failed the task" (Task = `{self.parent_task.objective}`)'
        logs.insert_log('TASK_ERROR', 'Max steps reached')
        return True, f'[SAY] "I failed the task because I hit the max steps limit"'

    def get_thought(self):
        thought = oai.get_scalar(self.prompt, num_lines=1)
        remove_prefixes = ['Now, ', 'First, ', 'Second, ', 'Then, ']

        thought_wo_prefix = thought
        for prefix in remove_prefixes:
            if thought_wo_prefix.startswith(prefix):
                thought_wo_prefix = thought_wo_prefix[len(prefix):]
        thought_embedding = embeddings.get_embedding(thought_wo_prefix)

        if self.last_thought_embedding is not None:
            last_thought_similarity = semantic.cosine_similarity(self.last_thought_embedding, thought_embedding)
            if last_thought_similarity > 0.90:
                thought = "TASK COMPLETED"
                thought_embedding = embeddings.get_embedding(thought)

        if self.last_result_embedding is not None:  # todo - re think if this is the best way to solve this
            similarity = semantic.cosine_similarity(thought_embedding, self.last_result_embedding)
            if similarity > 0.94:
                thought = "TASK COMPLETED"
                thought_embedding = embeddings.get_embedding(thought)

        self.last_thought_embedding = thought_embedding
        self.thoughts.append(thought)
        self.parent_task.agent.context.message_history.add('thought', thought, embedding=thought_embedding)
        if config.get_value('system.verbose'):
            tcolor = config.get_value('system.termcolor-verbose')
            print(colored(f'Thought: {thought}', tcolor))
        self.thought_count += 1
        self.prompt += f'{thought}\n'
        return thought

    def save_action(self, action):
        self.actions.append(action)
        self.parent_task.agent.context.message_history.add('action', action)
        action = f'Action: {action}'
        if config.get_value('system.verbose'):
            tcolor = config.get_value('system.termcolor-verbose')
            print(colored(action, tcolor))

        self.prompt += f'{action}\n'

    def save_result(self, result):
        self.results.append(result)
        result = remove_brackets(result, "[")
        msg = self.parent_task.agent.context.message_history.add('result', result)
        self.last_result_embedding = msg.embedding
        result = f'Result: {result}'
        if config.get_value('system.verbose'):
            tcolor = config.get_value('system.termcolor-verbose')
            print(colored(result, tcolor))
        self.prompt += f'{result}\nThought: '


# class Interpreter:
#
#     def run(self):
#


class TaskStatus:
    INITIALISING = 0
    RUNNING = 1
    PAUSED = 2
    CANCELLED = 3
    FAILED = 4
    COMPLETED = 5

