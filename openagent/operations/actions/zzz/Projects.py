import re

from utils.apis import llm
from operations.action import BaseAction, ActionSuccess
from toolkits import lists
from utils import helpers, sql

desc_prefix = 'mentions'
desc = 'Something about Working-On/Building/Making/Designing a Project/Goal/Song/Book/Recipe/Software/Website etc.'
visible = True
elevate_actions = False

current_project = None
# current_project = {}

# STORES ROADBLOCKS AND ROADMAP


def set_current_project(name):
    global current_project, visible, elevate_actions
    current_project = name
    no_project = (name is None)
    visible = no_project
    elevate_actions = not no_project


class _On_Scoped(BaseAction):
    def __init__(self, agent):
        super().__init__(agent)
        # self.inputs.add('what-is-the-user-working-on', examples=['camper van conversion']))
        self.found_project = None

    def run_action(self):
        self.identify_project()
        if self.found_project == '[MULTIPLE]':
            yield ActionSuccess(f"[SAY]You aren't sure which project they're referring to. There are multiple possible projects.", code=300)
            self.found_project = None
            set_current_project(None)

        if self.found_project is not None:
            set_current_project(self.found_project)
            yield ActionSuccess(f"[RES] User is referencing their project: {self.found_project}", code=200)
        else:
            set_current_project(None)
            # yield ActionResult(f"""Only if it is necessary: [SAY] "I'm not sure which project you're referring to". Please ask them to clarify.""", code=300)

    def identify_project(self):
        last_user_msg = self.agent.context.message_history.last()['content']
        cat = helpers.categorize_item('project-types', last_user_msg, can_make_new=True)

        projects = list(lists.get_list_items('projects').values())

        conversation_str = self.agent.context.message_history.get_conversation_str(msg_limit=2)
        project_str = ',\n'.join(f'{projects.index(proj) + 1}: {proj}' for proj in projects)

        # 0: {cat}: {{new-project-name}}
        project_guess = llm.get_scalar(f"""
Analyze the provided conversation and projects list and return any ID(s) that are contextually appropriate based on the given conversation.

Use the following conversation to guide your analysis. The last user message (denoted with arrows ">> ... <<") is the message you will use to determine the appropriate ID(s).

{conversation_str}

PROJECTS:
ID | project-type | project-name 
---------------------------------
{project_str}

Of these projects that the user is working on, return the ID of the one you think the latest user message is referencing. 
If there are multiple possible projects the user is referencing, then output them comma separated (eg. `2,5,6`)
If none of the projects from the list appear to be referenced on the last user message in the conversation, simply output "0". 
If none of the projects are referenced, but it is necessary to create a new project, then format the output like this: `0: {cat}: {{new-project-name}}`, replacing the placeholder with a brief, fitting name.

OUTPUT: """, model='gpt-3.5-turbo')
        project_guess = helpers.remove_brackets(project_guess).strip('"').strip("'").strip()

        if project_guess == '0':
            pass

        elif project_guess.startswith('0:'):
            project_name = project_guess.split(':')[-1].strip()
            lists.add_list_item('projects', project_name)
            self.found_project = project_name
            # yield ActionResult(f"[ANS] User is referencing their project: {project_name}")
        else:
            project_guesses = [re.sub("[^0-9]", "", i) for i in project_guess.split(',')]
            if len(project_guesses) == 1:
                project_name = projects[int(project_guesses[0]) - 1]
                self.found_project = project_name
                # yield ActionResult(f"[ANS] User is referencing their project: {proj_name}")
            elif len(project_guesses) > 1:
                self.found_project = '[MULTIPLE]'
                # yield ActionResult(f"[SAY]You aren't sure which project they're referring to. There are {str(len(project_guesses))} possible projects.")


class View_All_Active_Projects(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='what projects are we working on')
        self.desc_prefix = 'Asked about '
        self.desc = 'Information on All or Multiple current/active/pending projects'

    def run_action(self):
        projects = sql.get_results(f"SELECT item_name FROM `lists_items` WHERE `list_id` in (SELECT `id` FROM `lists` WHERE `list_name` = 'projects')", return_type='list')
        projects_str = ',\n'.join(projects)
        if len(projects) == 0:
            yield ActionSuccess(f"[SAY] We are not working on any projects at the moment")
        else:
            yield ActionSuccess(f"[SAY] We are working on: {projects_str}")


class Recap_Project(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='recap this project')
        self.desc_prefix = 'requires me to'
        self.desc = 'Provide a Recap/Summary of the current project'

    def run_action(self):
        yield ActionSuccess(f"[SAY] Recapping project")


class Archive_Project(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='archive project')
        self.desc_prefix = 'requires me to'
        self.desc = 'Delete/Archive the current project that is being worked on'

    def run_action(self):
        print(
            f'ASSISTANT: > Are you sure you want to archive this project? (Y/N)')
        user_input = input("User: ")
        if user_input:
            if user_input.lower()[0] != 'y':
                yield ActionSuccess(f'[SAY] "Archiving Cancelled"')
            else:
                yield ActionSuccess(f"[SAY] Archived {current_project}")
        # self.inputs.add('are-you-sure-you-want-to-delete-the-project', format='Boolean (True/False)'))
        # if not self.inputs.all_filled():
        #     yield ActionResult('[SAY] "Are you sure you want to delete the project?"', code=300)
        # yield ActionResult(f"[SAY] Deleted {current_project}")

        #
        # if self.inputs.get('are-you-sure-you-want-to-delete-the-project').value.lower() == 'true':
        #     # try:
        #     #     pass
        #     #     # os.remove(filepath)
        #     # except Exception as e:
        #     #     yield ActionResult('[SAY] "There was an error deleting the project"')
        #     yield ActionResult('[SAY] "Project has been deleted"')
        # else:
        #     yield ActionResult('[SAY] "Deletion was cancelled"')
        #
        # d = 1
        # # projects = sql.get_results(f"SELECT item_name FROM `lists_items` WHERE `list_id` in (SELECT `id` FROM `lists` WHERE `list_name` = 'projects')", return_type='list')
        # # projects_str = ',\n'.join(f'{projects.index(proj) + 1}: {proj}' for proj in projects)
        # # project_to_archive = llm.get_scalar(f"""
