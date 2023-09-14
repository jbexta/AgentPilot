import os
import platform
import re
import time

from operations.fvalues import ImageFValue
from toolkits import spotify
from utils.apis import oai, tts
from operations.action import BaseAction, ActionSuccess
from utils import helpers, sql, config


# class Greeting(Action):
#     def __init__(self):
#         super().__init__(agent, example='greet the user')
#         self.desc_prefix = ''
#         self.desc = 'Greet'
#
#     def run_action(self):
#         yield ActionResult('Greet the user in the style of {char_name}')


class What_Can_I_Do(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='what actions can I do')
        self.desc_prefix = 'requires me to'
        self.desc = 'Say what actions the assistant can do'
        self.inputs.add('of-a-particular-category', examples=['media'])

    def run_action(self):
        # convert time to a human spoken time (eg. eight forty in the evening)
        # timee = time.time()
        # localtime 24 hrs
        t = time.localtime()
        spoken_time = helpers.time_to_human_spoken(t)

        self.result_message = f"[SAY]it's {spoken_time}"
        yield ActionSuccess(f"[SAY]it's {spoken_time}")


class Time(BaseAction):
    def __init__(self, agent):
        super().__init__(agent)
        self.desc_prefix = 'requires me to'
        self.desc = 'Get the current time'
        self.inputs.add('what-location-has-been-specified', required=False)

    def run_action(self):  # , agent):
        location = self.inputs.get('what-location-has-been-specified').value
        if not location:
            location = config.get_value('user.location')

        date = time.strftime("%a, %b %d, %Y", time.gmtime())
        time_ = time.strftime("%I:%M %p", time.gmtime())
        timezone = oai.get_scalar(f"""
Given the following location: "{location}"
Return the timezone of this location in the format "UTC+/-<hours>"
Consider any daylight savings time if applicable, the current date and time is {date} {time_} (UTC).
Output timezone:
""")
        extracted_hour_diff_int = re.search(r'UTC([+-]\d+)', timezone).group(1)
        t = time.gmtime(time.time() + int(extracted_hour_diff_int) * 3600)
        spoken_time = helpers.time_to_human_spoken(t)
        yield ActionSuccess(f'[SAY] "It is {spoken_time}"')


class Date(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='what day is it')
        self.desc_prefix = 'requires me to'
        self.desc = 'Get the current date/day/month/year'

    def run_action(self):
        # get date formatted as (Monday 1st of January 2021)
        date = time.strftime('%A %d %B %Y')

        # self.result_message = f"[SAY]it is {date}"
        yield ActionSuccess(f"[ANS]it is {date}")


class MouseClick(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='what day is it')
        self.desc_prefix = 'requires me to'
        self.desc = 'Click/Press A mouse button/On the screen'

    def run_action(self):
        # get date formatted as (Monday 1st of January 2021)
        date = time.strftime('%A %d %B %Y')

        # self.result_message = f"[SAY]it is {date}"
        yield ActionSuccess(f"")


class Use_Advanced_Reasoning(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='what day is it')
        self.desc_prefix = 'requires me to'
        self.desc = 'Use advanced reasoning, give my best answer, etc.'

    def run_action(self):
        yield ActionSuccess(f"[GPT4]")


# class Enhance_Or_Augment_Request(Action):
#     def __init__(self):
#         super().__init__(agent, example='what day is it')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Enhance/Augment the users request/prompt/instruction'
#
#     def run_action(self):
#         last_msg = self.agent.context.message_history.messages[-1]
#         enhanced_request = oai.get_scalar(f"""
# Act as a prompt augmenter for ChatGPT. I will give the base prompt and you will engineer a prompt around it that would yield the best and most desirable response from ChatGPT. The prompt can involve asking ChatGPT to "act as [role]", for example, "act as a lawyer". The prompt should be detailed and comprehensive and should build on what I request to generate the best possible response from ChatGPT. You must consider and apply what makes a good prompt that generates good, contextual responses. Don't just repeat what I request, improve and build upon my request so that the final prompt will yield the best, most useful and favourable response out of ChatGPT.
# Here is the message to augment: `{last_msg.content}`
# Begin output of the prompt you have engineered: """, model='gpt-4').replace('"', '')
#         self.agent.context.message_history.messages[-1].set_content(enhanced_request)
#         yield ActionResult('Reply to the user')


class Sync_Available_Voices(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='sync voices')
        self.desc_prefix = 'requires me to'
        self.desc = 'Syncronise the available voices of the assistant'

    def run_action(self):
        try:
            tts.sync_all()
            yield ActionSuccess("[SAY]Voices synced successfully")
        except Exception as e:
            yield ActionSuccess("[SAY]there was an error syncing voices.", code=500)


class Modify_Assistant_Responses(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='be more friendly')
        self.desc_prefix = 'requires me to'
        self.desc = 'Change the assistants behaviour'
        self.inputs.add('user-modification-request', examples=['I want you to be more emotionally expressive, talkative, and responsive.'])

    def run_action(self):
        try:
            res = oai.get_scalar(f"""
This is a GPT3 prompt that specifies how an LLM assistant behaves:
```
{self.agent.base_system_behaviour}
```

User's request to assistant: "{self.inputs.get(0).value}"

The user has requested something which requires modification of this behaviour prompt.
Please modify the prompt so that the assistant gracefully honours this request, while maintaining as much of the original prompt as possible. You can add new list items, and you can modify existing list items if it is absolutely necessary.
""", model='gpt-4')
            self.agent.base_system_behaviour = res
            yield ActionSuccess("[SAY]Behaviour changed successfully")
        except Exception as e:
            yield ActionSuccess("[SAY]there was an error changing my behaviour.", code=500)


# class Initiate_Quiz_Or_Test_Or_Other_QA(BaseAction):
#     def __init__(self, agent):
#         super().__init__(agent, example='quiz me on dvla theory test questions')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Start a quiz/test/exam/interview'
#         self.inputs.add('what-type-of-questions-should-be-asked', examples=['UK DVLA Driving Theory Questions'])
#         self.inputs.add('number-of-questions', required=False, hidden=True)
#         self.inputs.add('has-user-asked-to-end-the-quiz', required=False, hidden=True, format='Boolean (True/False)')
#         # self.inputs.add('user-answered-and', required=False))
#         # self.current_question = ''
#         self.past_questions = []
#
#     def run_action(self):
#         try:
#             question_type = self.inputs.get(0).value
#             question_count = 10  # self.inputs.get('number-of-questions').value  # todo add defaults
#
#             for i in range(question_count):
#                 past_questions_str = '\n'.join(self.past_questions)
#                 new_question = oai.get_scalar(f"""
#     Append to the list, a question about {question_type} that has not already been asked:
#     {past_questions_str}
#     """)
#                 new_question_param = 'users-answer-to-the-question_' + ''.join(c for c in new_question.replace(' ', '-') if c.isalnum() or c == '-')
#                 self.inputs.add(new_question_param, required=False)
#                 yield ActionResult("[MI]")
#
#                 self.past_questions.append(new_question)
#                 self.inputs.pop()
#
#         except Exception as e:
#             yield ActionResult("[SAY]there was an error tarting quiz.", code=500)


class Clear_Assistant_Context_Messages(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='clear context')
        self.desc_prefix = 'requires me to'
        self.desc = 'Clear the context/messages/history'

    def run_action(self):
        try:
            # set del = 1 except last message
            sql.execute(f"UPDATE contexts_messages SET del = 1 WHERE id < {self.agent.context.message_history.last()['id']}")
            self.agent.context.message_history.load_context_messages()
            print('\n' * 100)
            yield ActionSuccess('[SAY] "Context has been cleared"')
        except Exception as e:
            yield ActionSuccess('[SAY] "There was an error clearing context"', code=500)


class Set_Desktop_Background(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='set desktop background to an image of a dog')
        self.desc_prefix = 'requires me to'
        self.desc = 'Change the desktop background.'
        self.inputs.add('image-to-set-the-background-to', fvalue=ImageFValue)

    def run_action(self):
        try:
            image_path = self.inputs.get('image-to-set-the-background-to').value
            # other set desktop settings

            # Change desktop background on Windows
            sys_platform = platform.system()
            if sys_platform == 'Windows':
                import ctypes
                SPI_SETDESKWALLPAPER = 20
                ctypes.windll.user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, image_path, 3)

            # Change desktop background on macOS
            elif sys_platform == 'Darwin':
                script = f"""osascript -e 'tell application "Finder" to set desktop picture to POSIX file "{image_path}"'"""
                os.system(script)

            # Change desktop background on Linux
            elif sys_platform == 'Linux':
                dektop_env = os.environ.get('XDG_CURRENT_DESKTOP').upper()
                if dektop_env == 'GNOME':
                    # The code below uses the method for GNOME desktop environment.
                    os.system(f"gsettings set org.gnome.desktop.background picture-uri file://{image_path}")
                elif dektop_env == 'KDE':
                    # The code below uses the method for KDE desktop environment.
                    os.system(f"""qdbus org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript 'string: var Desktops = desktops(); \
                    for (i=0;i<Desktops.length;i++) \
                    {{" \
                    d = Desktops[i]; \
                    d.wallpaperPlugin = "org.kde.image"; \
                    d.currentConfigGroup = Array("Wallpaper", "org.kde.image", "General"); \
                    d.writeConfig("Image", "file://{image_path}"); \
                    }}'""")
                elif dektop_env == 'MATE':
                    # The code below uses the method for MATE desktop environment.
                    os.system(f"""gsettings set org.mate.background picture-filename {image_path}""")
                elif dektop_env == 'XFCE':
                    # The code below uses the method for XFCE desktop environment.
                    os.system(f"""xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/workspace0/last-image -s {image_path}""")

            else:
                yield ActionSuccess("[SAY] The desktop background couldn't be changed because the OS is unknown, speaking as {char_name}.")

            yield ActionSuccess("[SAY] The desktop background has been changed to an image of a dog, speaking as {char_name}.")
        except Exception as e:
            yield ActionSuccess("[SAY] There was an error changing the desktop background.")


class Search_Web(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='what time does eastenders start')
        self.desc_prefix = 'Asked something that'
        self.desc = 'requires up-to-date information or any data that is new in the last 2 years'

    def run_action(self):
        try:
            yield ActionSuccess('[SAY] "Searching"')
        except Exception as e:
            yield ActionSuccess('[SAY] "There was an error searching"', code=500)


class Modify_Assistant_Voice(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='be a female voice')
        self.desc_prefix = 'requires me to'
        self.desc = 'Change the assistants behaviour'
        self.inputs.add('user-modification-request', examples=['I want you to be more emotionally expressive, talkative, and responsive.'])

    def run_action(self):
        try:
            res = oai.get_scalar(f"""
This is a GPT3 prompt that specifies how an LLM assistant behaves:
```
{self.agent.base_system_behaviour}
```

User's request to assistant: "{self.inputs.get(0).value}"

The user has requested something which requires modification of this behaviour prompt.
Please modify the prompt so that the assistant gracefully honours this request, while maintaining as much of the original prompt as possible. You can add new list items, and you can modify existing list items if it is absolutely necessary.
""", model='gpt-4')
            self.agent.base_system_behaviour = res
            yield ActionSuccess("[SAY]Behaviour changed successfully")
        except Exception as e:
            yield ActionSuccess("[SAY]there was an error changing my behaviour.", code=500)


class GetNameOfCurrentlyPlayingTrack(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='what song is this?')
        self.desc_prefix = 'requires me to'
        self.desc = 'Get the name of the currently playing song/artist/album/playlist/genre'

    def run_action(self):
        try:
            if not spotify.has_active_device():
                # try to shazam it
                yield ActionSuccess('[SAY] no music is playing.')

            cur_playing = spotify.get_current_track_name()

            yield ActionSuccess(f'[ANS]{cur_playing}.')
        except Exception as e:
            if 'NO_ACTIVE_DEVICE' in str(e):
                yield ActionSuccess("[SAY]spotify isn't open on a device, speaking as {char_name}.")
            yield ActionSuccess("[SAY]there was a problem finding an answer.")



# class Learn_From_Last_Message(BaseAction):
#     def __init__(self, agent):
#         super().__init__(agent, example='make a browser based game of pacman')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Learn from the last message'
#
#     def run_action(self):
#         pass


# class Develop_Software_Or_Website(BaseAction):
#     def __init__(self, agent):
#         super().__init__(agent, example='make a browser based game of pacman')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Develop/Make/Build/Code/Program/Write software or a website for the user, not including Help/Assistance/Guidance'
#         self.inputs = ActionInputCollection([
#                 ActionInput('what_to_build'),
#                 ActionInput('has_the_assistant_been_asked_to_continue_without_questions_or_answer_them_itself_or_automatically',
#                             format='Boolean (True/False)',
#                             required=False,
#                             prompted=False,
#                             rerun_on_change=True),
#                 # ActionInput('do_you_want_me_to_ask_additional_questions_before_building', format='Boolean (True/False)', required=False),
#             ])
#         self.questions = {}
#
#     def run_action(self):
#         what_to_build = self.inputs.get('what_to_build').value
#
#         # Gather extra information from the user by giving a numbered list of questions relating to all arbitrary design elements
#         response_questions = oai.get_scalar(f"""
# You will be building the following: "{what_to_build}"
# Gather extra information from the user by returning a numbered list of upto 5 concise sensible questions relating to arbitrary aspects of the project.
# """, model='gpt-4')
#         q_list = helpers.extract_list_from_string(response_questions)
#         if len(q_list) == 0:
#             whyyy = 1
#         question_list = [''.join(c for c in q.replace(' ', '_') if c.isalnum() or c == '_') for q in q_list]
#
#         for q in question_list:
#             self.inputs.add(q))
#             self.questions[q] = ''
#
#         self_answer_param = 'has_the_assistant_been_asked_to_continue_without_questions_or_answer_them_itself_or_automatically'
#         self_answer_param_val = self.inputs.get_value(self_answer_param)
#         self_answer = (self_answer_param_val.lower() == 'true') if self_answer_param_val else False
#         if self_answer:
#             self.auto_populate_inputs(messages=self.agent.context.message_history.get(),
#                                       exclude_inputs=[self_answer_param])
#         if not self.inputs.all_filled():
#             yield ActionResult('[MI]')
#
#         # begin_build_param = self.inputs.get_value('do_you_want_to_begin_building')
#         # if not begin_build_param:
#         #     self.inputs.add('user_provided', format='Boolean (True/False)', examples=['True', 'False']))
#         #     yield ActionResult('[MI] Is there any additional info you would like to provide before building?')
#         #
#         # begin_build = (begin_build_param.lower() == 'true') if begin_build_param else False
#         # if not begin_build:
#         #     yield ActionResult('[ITSOC] wait until I am ready to start building')
#
#         # add_response_func('[SAY] You will start building it.')
#
#         model = "gpt-4"
#         temperature = 0.1
#         steps_config = StepsConfig.DEFAULT
#         verbose = True
#         safe_filename = what_to_build.replace(' ', '_')
#         project_path = f"/home/jb/Desktop/Projects/{safe_filename}"
#
#         if not os.path.exists(project_path):
#             os.makedirs(project_path)
#
#         if os.path.exists(f"{project_path}/prompt"):
#             os.remove(f"{project_path}/prompt")
#
#         with open(f"{project_path}/prompt", 'w') as f:
#             f.write("You will be building the following: " + what_to_build + "\n")
#
#         logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
#
#         # model = fallback_model(model)
#         ai = AI(
#             model=model,
#             temperature=temperature,
#         )
#
#         input_path = Path(project_path).absolute()
#         memory_path = input_path / "memory"
#         workspace_path = input_path / "workspace"
#         archive_path = input_path / "archive"
#
#         dbs = DBs(
#             memory=DB(memory_path),
#             logs=DB(memory_path / "logs"),
#             input=DB(input_path),
#             workspace=DB(workspace_path),
#             preprompts=DB(Path(__file__).parent.parent.parent / "toolkits/gpt_engineer/preprompts"),
#             archive=DB(archive_path),
#         )
#
#         if steps_config not in [
#             StepsConfig.EXECUTE_ONLY,
#             StepsConfig.USE_FEEDBACK,
#             StepsConfig.EVALUATE,
#         ]:
#             archive(dbs)
#
#         steps = STEPS[steps_config]
#         for step in steps:
#             messages = step(ai, dbs)
#             dbs.logs[step.__name__] = json.dumps(messages)
#
#         if collect_consent():
#             collect_learnings(model, temperature, steps, dbs)
#
#         dbs.logs["token_usage"] = ai.format_token_usage_log()
#
#         # self.questions = {q_list[i]: '' for i in range(len(q_list))}
#         #
#         # # get one element from questions where value == ''
#         # question = next((k for k, v in self.questions.items() if v == ''), None)
#         # if question is not None:
#         #     yield ActionResult(f"[Q]{question}")
#         # else:
#         #     yield ActionResult("[SAY]Reminder has been set for ??")
