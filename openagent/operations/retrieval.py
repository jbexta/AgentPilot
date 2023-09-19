import importlib
import inspect
import os
import sys

from utils import logs, config, embeddings, semantic


class ActionData:
    def __init__(self, clss):
        self.clss = clss
        class_instance = clss(None)
        self.desc = class_instance.desc
        self.desc_prefix = class_instance.desc_prefix
        self.full_desc = f"The user's request {self.desc_prefix} {self.desc}"
        self.embedding = embeddings.get_embedding(self.desc)


class ActionCategory:
    def __init__(self, filename):
        self.name = filename
        module = self.module()
        self.desc = getattr(module, 'desc', file_name.replace('_', ' '))
        self.desc_prefix = getattr(module, 'desc_prefix', 'is something related to')
        self.on_scoped_class = getattr(module, '_On_Scoped', None)

        self.embedding = embeddings.get_embedding(self.desc)  # f'{self.desc_prefix} {self.desc}')
        self.all_actions_data = {}

        self.add_module_actions(module)

    def module(self):
        module_path = self.name if is_external else f'openagent.operations.actions.{self.name}'
        return importlib.import_module(module_path)

    def add_module_actions(self, module):
        members = inspect.getmembers(module)
        for member_name, member_value in members:
            if not inspect.isclass(member_value): continue
            if member_name.startswith('_'):
                continue

            if is_external:
                originates_in_folder = self.name == member_value.__module__
            else:
                originates_in_folder = f'openagent.operations.actions' in member_value.__module__

            if not originates_in_folder: continue  # prevents fetching members from imported modules

            self.all_actions_data[member_name] = ActionData(member_value)


source_dir = config.get_value('actions.source-directory')
if source_dir != '.' and not os.path.exists(source_dir):
    logs.insert_log('ERROR', f'Could not find source directory: {source_dir}')
    source_dir = '.'

if source_dir != '.':
    sys.path.append(source_dir)
    is_external = True
elif source_dir == '.':
    current_dir = os.path.dirname(os.path.abspath(__file__))
    source_dir = os.path.join(current_dir, 'actions')
    is_external = False

action_files = [
    file[:-3]  # Remove the '.py' extension
    for file in os.listdir(source_dir)
    if file.endswith('.py') and not file.startswith('zzz') and not file.startswith('__')
]


all_category_files = {}

# Import all files
action_groups = {}
for file_path in action_files:
    # Get the file name without the extension
    file_name = os.path.basename(file_path)
    all_category_files[file_name] = ActionCategory(file_name)


def match_request(messages):
    if len(all_category_files) == 0:
        return None

    last_msg = messages[-1]['content']
    prev_msg = messages[-2]['content'] if len(messages) > 1 else None

    req_embedding = embeddings.get_embedding(last_msg)
    prev_embedding = embeddings.get_embedding(prev_msg) if prev_msg else None
    cat_similarities = {}

    uncategorised = []

    for filename, category in all_category_files.items():
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
        category = all_category_files[filename]
        for action_name, action_data in category.all_actions_data.items():
            m1_similarity = semantic.cosine_similarity(action_data.embedding, req_embedding)
            m2_similarity = semantic.cosine_similarity(action_data.embedding, prev_embedding) if prev_embedding else 0
            similarity = max(m1_similarity, m2_similarity)
            action_similarities[action_name] = (similarity, action_data)

    top_actions = sorted(action_similarities.values(), key=lambda x: x[0], reverse=True)[:10]
    top_3_actions_data = [action_data for score, action_data in top_actions]
    return list(reversed(top_3_actions_data))


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
