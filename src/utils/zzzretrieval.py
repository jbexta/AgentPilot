import importlib
import inspect
import os
import re
import sys

from src.utils.embeddings import string_embeddings_to_array
from src.utils import logs, embeddings, semantic, llm


class ActionData:
    def __init__(self, clss):
        self.clss = clss
        self.name = clss.__name__
        self.class_instance = clss(None)
        self.desc = self.class_instance.desc
        self.desc_prefix = self.class_instance.desc_prefix
        self.full_desc = f"The user's request {self.desc_prefix} {self.desc}"
        _, self.embedding = embeddings.get_embedding(self.desc)
        self.embedding = string_embeddings_to_array(self.embedding)


class ActionCategory:
    def __init__(self, filename):
        self.name = filename
        module = self.module()
        self.desc = getattr(module, 'desc', filename.replace('_', ' '))
        self.desc_prefix = getattr(module, 'desc_prefix', 'is something related to')
        self.on_scoped_class = getattr(module, '_On_Scoped', None)

        _, self.embedding = embeddings.get_embedding(self.desc)
        self.embedding = string_embeddings_to_array(self.embedding)
        self.all_actions_data = {}

        self.add_module_actions(module)

    def module(self):
        is_external = False
        # module_path = f'agentpilot.operations.actions.{self.name}'
        module_path = self.name if is_external else f'operations.actions.{self.name}'
        return importlib.import_module(module_path)

    def add_module_actions(self, module):
        members = inspect.getmembers(module)
        for member_name, member_value in members:
            if not inspect.isclass(member_value): continue
            if member_name.startswith('_'):
                continue

            is_external = False
            if is_external:
                originates_in_folder = self.name == member_value.__module__
            else:
                originates_in_folder = f'agentpilot.operations.actions' in member_value.__module__

            if not originates_in_folder: continue  # prevents fetching members from imported modules

            self.all_actions_data[member_name] = ActionData(member_value)


class ActionCollection:
    def __init__(self, source_dir):
        if source_dir == '':
            source_dir = '.'
        if source_dir != '.' and not os.path.exists(source_dir):
            logs.insert_log('ERROR', f'Could not find source directory: {source_dir}')
            source_dir = '../zzzoperations'

        if source_dir != '.':
            sys.path.append(source_dir)
            self.is_external = True
        elif source_dir == '.':
            current_dir = os.path.dirname(os.path.abspath(__file__))
            source_dir = os.path.join(current_dir, '../operations/actions')
            self.is_external = False

        action_files = [
            file[:-3]  # Remove the '.py' extension
            for file in os.listdir(source_dir)
            if file.endswith('.py') and not file.startswith('zzz') and not file.startswith('__')
        ]

        self.all_category_files = {}

        # Import all files
        action_groups = {}
        for file_path in action_files:
            # Get the file name without the extension
            file_name = os.path.basename(file_path)
            self.all_category_files[file_name] = ActionCategory(file_name)

    def match_request(self, messages):
        if len(self.all_category_files) == 0:
            return None

        last_msg = messages[-1]['content']
        prev_msg = messages[-2]['content'] if len(messages) > 1 else None

        _, req_embedding = embeddings.get_embedding(last_msg)
        _, prev_embedding = embeddings.get_embedding(prev_msg) if prev_msg else (None, None)
        req_embedding = string_embeddings_to_array(req_embedding)
        prev_embedding = string_embeddings_to_array(prev_embedding) if prev_embedding else None
        cat_similarities = {}

        uncategorised = []

        for filename, category in self.all_category_files.items():
            if filename.startswith('_'):
                uncategorised.append(filename)
                continue
            m1_similarity = semantic.cosine_similarity(category.embedding, req_embedding)
            m2_similarity = semantic.cosine_similarity(category.embedding, prev_embedding) if prev_embedding else 0
            cat_similarities[filename] = max(m1_similarity, m2_similarity)

        lookat_cats = sorted(cat_similarities, key=cat_similarities.get, reverse=True)[:len(cat_similarities) // 2]
        lookat_cats.extend(uncategorised)
        #
        # top_3 = []

        action_similarities = {}
        for filename in lookat_cats:
            category = self.all_category_files[filename]
            for action_name, action_data in category.all_actions_data.items():
                m1_similarity = semantic.cosine_similarity(action_data.embedding, req_embedding)
                m2_similarity = semantic.cosine_similarity(action_data.embedding, prev_embedding) if prev_embedding else 0
                similarity = max(m1_similarity, m2_similarity)
                action_similarities[action_name] = (similarity, action_data)

        top_actions = sorted(action_similarities.values(), key=lambda x: x[0], reverse=True)[:10]
        top_3_actions_data = [action_data for score, action_data in top_actions]
        return list(reversed(top_3_actions_data))


def native_decision(task, action_data_list):
    action_lookback_msg_cnt = task.agent.config.get('actions.lookback_msg_count', 2)
    if task.parent_react:
        conversation_str = task.agent.workflow.message_history.get_conversation_str(msg_limit=1,
                                                                                    incl_roles=('thought', 'result'),
                                                                                    prefix='CONTEXT:\n')
    else:
        conversation_str = task.agent.workflow.message_history.get_conversation_str(msg_limit=action_lookback_msg_cnt)

    action_str = ',\n'.join(f'{action_data_list.index(act_data) + 1}: {act_data.desc}'
                            for act_data in action_data_list)

# CONTEXT INFORMATION:
# - 'agent sims' is an installed desktop application that allows you to create and customize characters.
    # Note: To identify the primary action in the last request, focus on the main verb that indicates the current or next immediate action the speaker intends to take. Consider the verb's tense to prioritize actions that are planned or ongoing over those that are completed or auxiliary. Disregard actions that are merely described or implied without being the central focus of the current intention.
    # The verb expressing the main action in the sentence is crucial to making the right choice. If a secondary action or condition is described, it should not take precedence over the main action indicated in the last request. Focusing particularly on the tense to identify the valid - yet to be performed - action.
    context_type = 'messages' if task.parent_react else 'conversation'
    last_entity = 'message' if task.parent_react else 'user message'
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
    response = llm.get_scalar(prompt, single_line=True)
    # response = re.sub(r'[^0-9,]', '', response)  # this regex removes all non-numeric characters except commas

    response = re.sub(r'([0-9]+).*', r'\1', response)  # this regex only keeps the first integer found in the string
    action_ids = [int(x) for x in response.split(',') if x != '' and int(x) > 0]

    actions = [action_data_list[x - 1].clss for x in action_ids if x <= len(action_data_list)]
    none_existing = [x for x in action_ids if x > len(action_data_list)]
    if none_existing:
        print(f"IDs {none_existing} do not exist in the list and will be ignored.")
    return actions


def function_call_decision(task, action_data_list):
    action_lookback_msg_cnt = task.agent.config.get('actions.lookback_msg_count', 2)
    if task.parent_react:
        messages = task.agent.workflow.message_history.get(msg_limit=1,
                                                           incl_roles=['thought'],
                                                           map_to=['user'])
                                                          # incl_roles=('thought', 'result'),
                                                          # map_to=('user', 'assistant'))
    else:
        messages = task.agent.workflow.message_history.get(msg_limit=action_lookback_msg_cnt)

    messages[-1]['content'] = f'>> {messages[-1]["content"]} <<'
    context_type = 'messages' if task.parent_react else 'conversation'
    last_entity = 'message' if task.parent_react else 'user message'
    prompt = f"""Analyze the provided {context_type} and functions and if appropriate, return the most valid function based on the last {last_entity}. If none are valid then respond normally as assistant.

Use the following {context_type} to guide your analysis. The last {last_entity} (denoted with arrows ">> ... <<") is the {last_entity} you will use to determine the most valid function.
The preceding assistant messages are provided to give you context for the last {last_entity}, to determine whether a function is valid.
You must reply normally as assistant if there are no functions needed based on the last {last_entity}.

TASK:
Examine the {context_type} in detail, applying logic and reasoning to ascertain the most valid function based on the latest {last_entity}.
If no functions are valid based on the last {last_entity}, simply respond normally as assistant. 
"""
    functions = get_function_call_list(action_data_list)
    response = llm.get_function_call_response(messages=messages, sys_msg=prompt, functions=functions, stream=False)

    if 'function_call' in response[0]['choices'][0]['message']:
        func_name = response[0]['choices'][0]['message']['function_call']['name']
        actions = [x.clss for x in action_data_list if x.clss.__name__ == func_name]
        return actions
    else:
        return []

    # response = re.sub(r'([0-9]+).*', r'\1', response)  # this regex only keeps the first integer found in the string
    # action_ids = [int(x) for x in response.split(',') if x != '' and int(x) > 0]
    #
    # actions = [action_data_list[x - 1].clss for x in action_ids if x <= len(action_data_list)]
    # none_existing = [x for x in action_ids if x > len(action_data_list)]
    # if none_existing:
    #     print(f"IDs {none_existing} do not exist in the list and will be ignored.")
    # return actions

    # NOW INSTEAD OF ABOVE, GET THE CLASS BY THE FUNCTION NAME:


def get_function_call_list(action_data_list):
    # format output
    # "functions": [
    #   {
    #     "name": "get_current_weather",
    #     "description": "Get the current weather in a given location",
    #     "parameters": {
    #       "type": "object",
    #       "properties": {
    #         "location": {
    #           "type": "string",
    #           "description": "The city and state, e.g. San Francisco, CA"
    #         },
    #         "unit": {
    #           "type": "string",
    #           "enum": ["celsius", "fahrenheit"]
    #         }
    #       },
    #       "required": ["location"]
    #     }
    #   }
    # ]
    functions = []
    for action_data in action_data_list:
        params = action_data.class_instance.inputs.inputs
        required_params = [param.input_name for param in params if param.required]
        properties = {p.input_name: {'type': p.fvalue.type_str, 'description': p.description()} for p in params}
        function = {
            "name": action_data.name,
            "description": action_data.desc,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required_params
            }
        }
        functions.append(function)
    return functions


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
# print(get_action_tree())


def get_action_class(action):
    action_name = action[0]
    for category in all_category_files.values():
        if action_name in category.all_actions_data:
            return category.all_actions_data[action_name].clss
    return action_name
