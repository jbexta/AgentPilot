import importlib
import inspect
import os
import re
import time

from termcolor import colored
from utils.apis import oai
from agent.context import Context
from utils import logs, config
from utils.helpers import remove_brackets

# Get the list of files in the 'actions' directory
current_dir = os.path.dirname(os.path.abspath(__file__))
actions_dir = os.path.join(current_dir, 'actions')

# import
action_files = sorted([
    file[:-3]  # Remove the '.py' extension
    for file in os.listdir(actions_dir)
    if file.endswith('.py') and not file.startswith('_') and not file.startswith('zzz')
])
action_files += [
    file[:-3]  # Remove the '.py' extension
    for file in os.listdir(actions_dir)
    if file.endswith('.py') and file.startswith('_')
]


class ActionData:
    def __init__(self, clss):
        self.clss = clss
        class_instance = clss(None)
        self.desc = class_instance.desc
        self.desc_prefix = class_instance.desc_prefix


class ActionCategory:
    def __init__(self, filename):
        self.name = filename
        module = self.module()
        self.desc = getattr(module, 'desc', file_name.replace('_', ' '))
        self.desc_prefix = getattr(module, 'desc_prefix', 'is something related to')
        self.on_scoped_class = getattr(module, '_On_Scoped', None)
        self.group_id = getattr(module, 'group_id', None)
        self.all_actions_data = {}

        self.add_module_actions(module)

    def module(self):
        return importlib.import_module(f'openagent.operations.actions.{self.name}')

    def add_module_actions(self, module):
        members = inspect.getmembers(module)
        for member_name, member_value in members:
            if not inspect.isclass(member_value): continue
            if member_name.startswith('_'):
                continue

            # originates_in_file = member_value.__module__ == f'openagent.operations.actions.{file_name}'
            # if not originates_in_file: continue  # prevents fetching members from imported modules
            originates_in_folder = f'openagent.operations.actions' in member_value.__module__
            if not originates_in_folder: continue  # prevents fetching members from imported modules

            self.all_actions_data[member_name] = ActionData(member_value)


all_category_files = {}

# Import all files
action_groups = {}
for file_path in action_files:
    # Get the file name without the extension
    file_name = os.path.basename(file_path)
    all_category_files[file_name] = ActionCategory(file_name)
    grp = all_category_files[file_name].group_id
    if grp:
        if grp in action_groups:
            action_groups[grp].append(file_name)
        else:
            action_groups[grp] = [file_name]


for grp, files in action_groups.items():
    for file in files:
        for file_merge in files:
            if file_merge == file: continue
            file_merge_actions = all_category_files[file_merge].all_actions_data
            all_category_files[file].all_actions_data.update(file_merge_actions)


def get_action_tree():
    action_tree = {}
    for category in all_category_files.values():
        action_tree[category.name] = {}
        for action_name, action_data in category.all_actions_data.items():
            if len(action_data.desc_prefix) > 0:
                propr_prefix = action_data.desc_prefix[0].upper() + action_data.desc_prefix[1:]
                action_tree[category.name][action_name] = f'{propr_prefix} {action_data.desc}'
    return action_tree

# print pretty tree
def print_tree(tree, indent=0):
    for key, value in tree.items():
        print('\t' * indent + str(key))
        if isinstance(value, dict):
            print_tree(value, indent + 1)
        else:
            print('\t' * (indent + 1) + str(value))

# print_tree(get_action_tree())
# # print(get_action_tree())


def get_action_class(action):
    action_name = action[0]
    for category in all_category_files.values():
        if action_name in category.all_actions_data:
            return category.all_actions_data[action_name].clss
    return action_name


class Task:
    def __init__(self, agent, messages=None, parent_react=None):
        self.objective = agent.context.message_history.last()['content']
        self.actions = []
        self.action_methods = []
        self.parent_react = parent_react
        self.react = None
        self.current_action_index = 0
        self.current_msg_id = 0
        self.task_context = Context(messages=messages)
        self.time_expression = None
        self.recurring = False
        self.status = TaskStatus.INITIALISING
        self.agent = agent
        self.add_response_func = lambda response: self.agent.task_worker.task_responses.put(response)

        react_enabled = config.get_value('react.enabled')
        always_use_react = config.get_value('react.always-use-react')
        validate_guess = config.get_value('actions.validate-guess')
        is_guess_valid = True

        recursive = config.get_value('react.recursive')
        if self.parent_react is not None and not recursive:
            react_enabled = False
            validate_guess = False

        if not react_enabled or (react_enabled and not always_use_react):
            actions = self.get_action_guess()
            if self.status == TaskStatus.CANCELLED:
                return

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
If the request can be fully satisfied, return 'TRUE'.
""", single_line=True)  # If FALSE, explain why
        if config.get_value('system.verbose'):
            logs.insert_log('VALIDATOR RESPONSE', validator_response)
        return validator_response == 'TRUE'

    def get_action_guess(self):
        collected_actions = []
        queued_scopes = ['']

        while queued_scopes:
            current_scope = queued_scopes.pop(0)

            if current_scope:
                if config.get_value('system.verbose'):
                    print('SCOPING: ', current_scope)

            if not current_scope:
                action_temp = [
                    [action_name, f"The user's request {action.desc_prefix} {action.desc}"]
                    for cat_name, category in all_category_files.items() if getattr(category.module(), 'elevate_actions', False)
                    for action_name, action in category.all_actions_data.items()
                ]
                action_temp += [
                    [action_name, f"The user's request {action.desc_prefix} {action.desc}"]
                    if cat_name.startswith('_') else
                    [cat_name, f"The user's request {all_category_files[cat_name].desc_prefix} {all_category_files[cat_name].desc}"]
                    for cat_name, category in all_category_files.items() if getattr(category.module(), 'visible', True)
                    for action_name, action in (category.all_actions_data.items() if cat_name.startswith('_') else [(None, None)])
                ]
            else:
                action_temp = [
                    [action_name, f"The user's request {action.desc_prefix} {action.desc}"]
                    for action_name, action in all_category_files[current_scope].all_actions_data.items()  # all_actions[current_scope].items()
                ]

            proposed_actions = self.prompt_list_choice(action_temp)
            action_names_set = {a[0] for a in proposed_actions}

            collected_actions += [get_action_class(a) for a in proposed_actions if a[0] not in all_category_files]
            found_scopes = [name for name in action_names_set if name in all_category_files]
            collected_actions += [all_category_files[name].on_scoped_class for name in found_scopes if all_category_files[name].on_scoped_class is not None]
            queued_scopes += found_scopes

        if collected_actions:
            classes_not_found = [c for c in collected_actions if isinstance(c, str)]
            if classes_not_found:
                print('ACTIONs NOT FOUND: ', ', '.join(classes_not_found))

            actions = [action_class(self.agent) for action_class in collected_actions]
            # self.action_methods = [action.run_action() for action in self.actions]
            return actions

        self.status = TaskStatus.CANCELLED
        return None

    def prompt_list_choice(self, action_temp):
        # conversation_str = self.agent.context.message_history.get_conversation_str(msg_limit=2)
        conversation_str = self.task_context.message_history.get_conversation_str(msg_limit=2)
        action_str = ',\n'.join(f'{action_temp.index(choice) + 1}: {choice[1]}' for choice in action_temp)

# CONTEXT INFORMATION:
# - 'agent sims' is an installed desktop application that allows you to create and customize characters.

        prompt = f"""Analyze the provided conversation and actions/detections list and return all ID(s) that are contextually appropriate based on the given conversation.

ACTIONS/DETECTIONS LIST:
ID: Description
____________________
0: No action to take and nothing detected
{action_str}

Use the following conversation to guide your analysis. The last user message (denoted with arrows ">> ... <<") is the message you will use to determine the appropriate ID(s).
The preceding assistant messages are provided to give you context for the last user message, to determine whether an action/detection is valid.

{conversation_str}

TASK:
Examine the conversation in detail, applying logic and reasoning to ascertain the most relevant ID(s) based on the latest user message. 
If more than one is relevant, write each ID separated by a single comma ',' . 
If no actions or detections from the list are even slightly relevant to the last user message, simply output "0". 

The detected ID(s) are:
"""
# If it seems like there should be further action(s) to take, but it is not in the list, then add a question mark to the comma separated list (e.g. "1,3,5,?").
        response = oai.get_scalar(prompt)
        response = re.sub(r'[^0-9,]', '', response)
        action_ids = [int(x) for x in response.split(',') if x != '' and int(x) > 0]

        actions = [action_temp[x - 1] for x in action_ids if x <= len(action_temp)]
        none_existing = [x for x in action_ids if x > len(action_temp)]
        if none_existing:
            print(f"IDs {none_existing} do not exist in the list and will be ignored.")
        return actions

    def run(self):
        if self.react is not None:
            return self.react.run()

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
                if config.get_value('system.verbose'):
                    logs.insert_log(f"TASK {'FINISHED' if action_result.code == 200 else 'MESSAGE'}", response)

                if self.parent_react is None or action_result.code != 200:
                    self.add_response_func(remove_brackets(response, '('))

                if action_result.code == 200:
                    action.result = response  # remove_brackets(response, '[')
                    self.current_action_index += 1
                    # action_name = action.__class__.__name__
                    # self.self.agent.context.recent_actions.append(f"RESULT OF ACTION `{action_name}` ({action.desc}):\n{action_result.output}")
                else:
                    self.status = TaskStatus.FAILED if action_result.code == 500 else TaskStatus.PAUSED
                    break
            else:
                self.add_response_func(action.get_missing_inputs_string())
                self.status = TaskStatus.PAUSED
                break

        if self.status == TaskStatus.RUNNING:
            self.status = TaskStatus.COMPLETED
            logs.insert_log('TASK FINISHED', self.fingerprint(), print_=False)
            time.sleep(0.2)
            return True
        elif self.status == TaskStatus.PAUSED:
            return False
        else:
            return True

        # if self.recurring:
        #     self.status = TaskStatus.SCHEDULED
        #     # self.task_context.  # todo - reschedule task
        #     self.actions = []

    def is_duplicate_action(self):
        return any([action.is_duplicate_action() for action in self.actions])


class ExplicitReAct:
    def __init__(self, parent_task):
        self.parent_task = parent_task
        self.thought_task = None
        self.thought_count = 0
        self.react_context = Context()

        self.thoughts = []
        self.actions = []
        self.observations = []

        objective = self.parent_task.objective
        conversation_str = self.parent_task.task_context.message_history.get_conversation_str(msg_limit=2)
        self.prompt = f"""
Task request: `{objective}`
You are completing a task by breaking it down into smaller actions that are explicitly expressed in the task.
You have access to a wide range of actions, which you will search through and select after each thought, unless the task is completed.

Use the following conversation as context. The last user message (denoted with arrows ">> ... <<") is the message that triggered the task.
The preceding assistant messages are provided to give you context for the last user message, to determine whether an action/detection is valid.

{conversation_str}

Only return the next Thought. The Action and Observation will be returned automatically.
If the task is completed then return: "Thought: I have now completed the task."
Otherwise, return a thought that is a description of the next action to take verbatim from the task request.

-- EXAMPLE OUTPUTS --

Task: what is x
Thought: I need to get x
Action: Get x
Observation: x is [x_val]
Thought: I have now completed the task.
END

Task: do x and y
Thought: I need to do x
Action: Do x
Observation: I have done x
Thought: I need to do y
Action: Do y
Observation: I have done y
Thought: I have now completed the task
END


Task: set x to y
Thought: I need to get y
Action: Get y
Observation: y is [y_val]
Thought: I need to set x to [y_val]
Action: Set x to [y_val]
Observation: I have set x to [y_val]
Thought: I have now completed the task
END


Task: combine x and y and write it to z
Thought: I need to combine x and y
Action: Get x
Observation: x is [x_val]
Thought: I need to get y
Action: Get y
Observation: y is [y_val]
Thought: I need to combine [x_val] and [y_val]
Action: Combine [x_val] and [y_val]
Observation: I have combined [x_val] and [y_val] into [xy_val]
Thought: I need to write [xy_val] to z
Action: Write [xy_val] to z
Observation: I have written [xy_val] to z
Thought: I have now completed the task
END


Task: send a x with the y of z
Thought: I need to get the y of z
Action Get the y of z
Observation: The y of z is [yz_val]
Thought: I need to send a x with [yz_val]
Action: Send a x with [yz_val]
Observation: I have sent a x with [yz_val]
Thought: I have now completed the task
END


Return the next thought, or if the task is completed, return "Thought: I have now completed the task."

Task: `{objective}`
"""
        # self.react_context = {'role': 'Task', 'content': objective}

    def run(self):
        if config.get_value('system.verbose'):
            print('RUN REACT')
        max_steps = config.get_value('react.max-steps')
        for i in range(max_steps - self.thought_count):
            if self.thought_task is None:
                thought = self.get_thought()
                if thought.lower().startswith('thought: i have now completed the task'):
                    response = self.observations[-1] if len(self.observations) == 1 else f"""[SAY] "The task has been completed" (Task = `{self.parent_task.objective}`)"""
                    self.parent_task.add_response_func(response)
                    return True
                self.thought_task = Task(agent=self.parent_task.agent,
                                         messages=[{'id': 0, 'role': 'user', 'content': thought}],
                                         parent_react=self)
            try:
                task_finished = self.thought_task.run()
                if task_finished:
                    self.save_action(self.thought_task.fingerprint(_type='desc'))
                    self.save_observation(self.thought_task.fingerprint(_type='result'))
                    self.thought_task = None
                else:
                    return False

            except Exception as e:
                logs.insert_log('TASK_ERROR', str(e))
        self.parent_task.add_response_func(f'[SAY] "I failed the task" (Task = `{self.parent_task.objective}`)')
        logs.insert_log('TASK_ERROR', 'Max steps reached')
        return False

    def get_thought(self):
        thought = oai.get_scalar(self.prompt, single_line=True)
        self.thoughts.append(thought)
        self.parent_task.agent.context.message_history.add('thought', thought)
        if config.get_value('system.verbose'):
            tcolor = config.get_value('system.termcolor-verbose')
            print(colored(thought, tcolor))
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

    def save_observation(self, observation):
        self.observations.append(observation)
        observation = remove_brackets(observation, "[")
        self.parent_task.agent.context.message_history.add('observation', observation)
        observation = f'Observation: {observation}'
        if config.get_value('system.verbose'):
            tcolor = config.get_value('system.termcolor-verbose')
            print(colored(observation, tcolor))
        self.prompt += f'{observation}\n'


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

# * = requires info gathering
# $ = requires knowledge retrieval
# % = requires smarter logic
# + = requires action logic
# @ = requires a web search
# - = time based


# LEVEL 1
examples = "*Play tracy chapmans version of this song"
"*Send me an sms with the name of this song"
"*who covers this song"
"*What's the weather forecast for my location this weekend?"
"*Add this website to my reading list"
"*send an sms of a summary of this website in a message to darren"
"*send an email of a summary of this youtube video in an email to darren"
"*what year was this song released"
"*Set my desktop background to a picture of a dog"
"-In 15 minutes, play a relaxing playlist for my meditation session"
"-in 10 minutes set a timer for 4 minutes"
"-every morning I want you to tell me a philosophical quote"
"-tell me a motivating quote just before I sleep every night"
"-Share a new word and its meaning every day."
"-Share a joke every afternoon to lighten up my day."
"-read my reading list every morning"
"-Help me learn a new language by teaching me a few phrases each day."
"-Give me a historical fact every day."
"-Every Saturday, recommend a DIY craft project I can do over the weekend"
"-Teach me a new scientific concept every week.    "
"-every day remind me to do exercise"
"-read the news every morning"
"-set a reminder on the first thursday of every month called event"
"-there's an event that happens on the first friday of every month that i always forget about, can you let me know the day before so i dont forget"
"@Provide a daily brief on the stock market."
"@-*set an alarm for n minutes before east enders starts"
"$which list has cocoa powder in it"
"$what tasks have you done recently"
"$what alarms do you have set"
"$what tasks are you doing"
"$*add milk to whichever list has cocoa powder in"
"$*play that song that i said made me feel good yesterday"
"$-what are the settings for alarm/reminder/task at ten thirty"
"$Provide a recap of my main tasks from last week."
"$How many times did I ask about exercise routines this month"
"Give me a summary of the latest research in artificial intelligence"
"Suggest a healthy meal plan for next week."
"%set a reminder every day with the meal plan for that day"
"Suggest an exercise routine for weight loss."
"Suggest a weekend getaway based on my interest in hiking."
"+Find me a recipe that uses the ingredients I have in my fridge."
"+Help me prepare for my job interview by asking me common interview questions."
"+Quiz me on capital cities of the world."
"teach me a new scientific concept"
"play stone roses"
"Add celery and oil to my shopping list and my garage list"
"set an alarm for 20 minutes in 5 minutes"


"generate an image of a cat and a dog and set it as my wallpaper"
"Sql query of a file"
"open this file and analyse it"
"analyse this folder"
"read this file and tell me x"
