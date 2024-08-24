
from src.gui.config import ConfigTabs, ConfigFields, ConfigPages


class Page_Settings_CrewAI(ConfigTabs):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.conf_namespace = 'plugins.crewai'

        self.pages = {
            'Prompts': self.Page_Settings_CrewAI_Prompts(parent=self),
        }

    # {
    #     "hierarchical_manager_agent": {
    #         "role": "Crew Manager",
    #         "goal": "Manage the team to complete the task in the best way possible.",
    #         "backstory": "You are a seasoned manager with a knack for getting the best out of your team.\nYou are also known for your ability to delegate work to the right people, and to ask the right questions to get the best out of your team.\nEven though you don't perform tasks by yourself, you have a lot of experience in the field, which allows you to properly evaluate the work of your team members."
    #     },
    #     "slices": {
    #         "observation": "\nObservation",
    #         "task": "\nCurrent Task: {input}\n\nBegin! This is VERY important to you, use the tools available and give your best Final Answer, your job depends on it!\n\nThought:",
    #         "memory": "\n\n# Useful context: \n{memory}",
    #         "role_playing": "You are {role}. {backstory}\nYour personal goal is: {goal}",
    #         "tools": "\nYou ONLY have access to the following tools, and should NEVER make up tools that are not listed here:\n\n{tools}\n\nUse the following format:\n\nThought: you should always think about what to do\nAction: the action to take, only one name of [{tool_names}], just the name, exactly as it's written.\nAction Input: the input to the action, just a simple a python dictionary, enclosed in curly braces, using \" to wrap keys and values.\nObservation: the result of the action\n\nOnce all necessary information is gathered:\n\nThought: I now know the final answer\nFinal Answer: the final answer to the original input question\n",
    #         "no_tools": "To give my best complete final answer to the task use the exact following format:\n\nThought: I now can give a great answer\nFinal Answer: my best complete final answer to the task.\nYour final answer must be the great and the most complete as possible, it must be outcome described.\n\nI MUST use these formats, my job depends on it!",
    #         "format": "I MUST either use a tool (use one at time) OR give my best final answer. To Use the following format:\n\nThought: you should always think about what to do\nAction: the action to take, should be one of [{tool_names}]\nAction Input: the input to the action, dictionary enclosed in curly braces\nObservation: the result of the action\n... (this Thought/Action/Action Input/Observation can repeat N times)\nThought: I now can give a great answer\nFinal Answer: my best complete final answer to the task.\nYour final answer must be the great and the most complete as possible, it must be outcome described\n\n ",
    #         "final_answer_format": "If you don't need to use any more tools, you must give your best complete final answer, make sure it satisfy the expect criteria, use the EXACT format below:\n\nThought: I now can give a great answer\nFinal Answer: my best complete final answer to the task.\n\n",
    #         "format_without_tools": "\nSorry, I didn't use the right format. I MUST either use a tool (among the available ones), OR give my best final answer.\nI just remembered the expected format I must follow:\n\nQuestion: the input question you must answer\nThought: you should always think about what to do\nAction: the action to take, should be one of [{tool_names}]\nAction Input: the input to the action\nObservation: the result of the action\n... (this Thought/Action/Action Input/Observation can repeat N times)\nThought: I now can give a great answer\nFinal Answer: my best complete final answer to the task\nYour final answer must be the great and the most complete as possible, it must be outcome described\n\n",
    #         "task_with_context": "{task}\n\nThis is the context you're working with:\n{context}",
    #         "expected_output": "\nThis is the expect criteria for your final answer: {expected_output} \n you MUST return the actual complete content as the final answer, not a summary.",
    #         "human_feedback": "You got human feedback on your work, re-avaluate it and give a new Final Answer when ready.\n {human_feedback}",
    #         "getting_input": "This is the agent final answer: {final_answer}\nPlease provide a feedback: "
    #     },
    #     "errors": {
    #         "force_final_answer": "Tool won't be use because it's time to give your final answer. Don't use tools and just your absolute BEST Final answer.",
    #         "agent_tool_unexsiting_coworker": "\nError executing tool. Co-worker mentioned not found, it must to be one of the following options:\n{coworkers}\n",
    #         "task_repeated_usage": "I tried reusing the same input, I must stop using this action input. I'll try something else instead.\n\n",
    #         "tool_usage_error": "I encountered an error: {error}",
    #         "tool_arguments_error": "Error: the Action Input is not a valid key, value dictionary.",
    #         "wrong_tool_name": "You tried to use the tool {tool}, but it doesn't exist. You must use one of the following tools, use one at time: {tools}.",
    #         "tool_usage_exception": "I encountered an error while trying to use the tool. This was the error: {error}.\n Tool {tool} accepts these inputs: {tool_inputs}"
    #     },
    #     "tools": {
    #         "delegate_work": "Delegate a specific task to one of the following co-workers: {coworkers}\nThe input to this tool should be the co-worker, the task you want them to do, and ALL necessary context to exectue the task, they know nothing about the task, so share absolute everything you know, don't reference things but instead explain them.",
    #         "ask_question": "Ask a specific question to one of the following co-workers: {coworkers}\nThe input to this tool should be the co-worker, the question you have for them, and ALL necessary context to ask the question properly, they know nothing about the question, so share absolute everything you know, don't reference things but instead explain them."
    #     }
    # }
    class Page_Settings_CrewAI_Prompts(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)

            self.pages = {
                'Slices': self.Tab_Slices(parent=self),
                'Errors': self.Tab_Errors(parent=self),
                'Tools': self.Tab_Tools(parent=self),
            }

        class Tab_Slices(ConfigPages):
            def __init__(self, parent):
                super().__init__(parent=parent, align_left=True)  # , text_size=10)

                self.pages = {
                    "Observation": self.Tab_Slices_Observation(parent=self),
                    "Task": self.Tab_Slices_Task(parent=self),
                    "Memory": self.Tab_Slices_Memory(parent=self),
                    "Role playing": self.Tab_Slices_RolePlaying(parent=self),
                    "Tools": self.Tab_Slices_Tools(parent=self),
                    "No tools": self.Tab_Slices_NoTools(parent=self),
                    "Format": self.Tab_Slices_Format(parent=self),
                    "Final answer format": self.Tab_Slices_FinalAnswerFormat(parent=self),
                    "Format without tools": self.Tab_Slices_FormatWithoutTools(parent=self),
                    "Task with context": self.Tab_Slices_TaskWithContext(parent=self),
                    "Expected output": self.Tab_Slices_ExpectedOutput(parent=self),
                    "Human feedback": self.Tab_Slices_HumanFeedback(parent=self),
                    "Getting input": self.Tab_Slices_GettingInput(parent=self),
                }

            class Tab_Slices_Observation(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'observation',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': '\nObservation',
                        },
                    ]

            class Tab_Slices_Task(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'task',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': '\nCurrent Task: {input}\n\nBegin! This is VERY important to you, use the tools available and give your best Final Answer, your job depends on it!\n\nThought:',
                        },
                    ]

            class Tab_Slices_Memory(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'memory',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': '\n\n# Useful context: \n{memory}',
                        },
                    ]

            class Tab_Slices_RolePlaying(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'role_playing',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'You are {role}. {backstory}\nYour personal goal is: {goal}',
                        },
                    ]

            class Tab_Slices_Tools(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'tools',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': "\nYou ONLY have access to the following tools, and should NEVER make up tools that are not listed here:\n\n{tools}\n\nUse the following format:\n\nThought: you should always think about what to do\nAction: the action to take, only one name of [{tool_names}], just the name, exactly as it's written.\nAction Input: the input to the action, just a simple a python dictionary, enclosed in curly braces, using \" to wrap keys and values.\nObservation: the result of the action\n\nOnce all necessary information is gathered:\n\nThought: I now know the final answer\nFinal Answer: the final answer to the original input question\n",
                        },
                    ]

            class Tab_Slices_NoTools(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'no_tools',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'To give my best complete final answer to the task use the exact following format:\n\nThought: I now can give a great answer\nFinal Answer: my best complete final answer to the task.\nYour final answer must be the great and the most complete as possible, it must be outcome described.\n\nI MUST use these formats, my job depends on it!',
                        },
                    ]

            class Tab_Slices_Format(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'format',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'I MUST either use a tool (use one at time) OR give my best final answer. To Use the following format:\n\nThought: you should always think about what to do\nAction: the action to take, should be one of [{tool_names}]\nAction Input: the input to the action, dictionary enclosed in curly braces\nObservation: the result of the action\n... (this Thought/Action/Action Input/Observation can repeat N times)\nThought: I now can give a great answer\nFinal Answer: my best complete final answer to the task.\nYour final answer must be the great and the most complete as possible, it must be outcome described\n\n ',
                        },
                    ]

            class Tab_Slices_FinalAnswerFormat(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'final_answer_format',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'If you don\'t need to use any more tools, you must give your best complete final answer, make sure it satisfy the expect criteria, use the EXACT format below:\n\nThought: I now can give a great answer\nFinal Answer: my best complete final answer to the task.\n\n',
                        },
                    ]

            class Tab_Slices_FormatWithoutTools(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'format_without_tools',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': '\nSorry, I didn\'t use the right format. I MUST either use a tool (among the available ones), OR give my best final answer.\nI just remembered the expected format I must follow:\n\nQuestion: the input question you must answer\nThought: you should always think about what to do\nAction: the action to take, should be one of [{tool_names}]\nAction Input: the input to the action\nObservation: the result of the action\n... (this Thought/Action/Action Input/Observation can repeat N times)\nThought: I now can give a great answer\nFinal Answer: my best complete final answer to the task\nYour final answer must be the great and the most complete as possible, it must be outcome described\n\n',
                        },
                    ]


            class Tab_Slices_TaskWithContext(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'task_with_context',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': '{task}\n\nThis is the context you\'re working with:\n{context}',
                        },
                    ]

            class Tab_Slices_ExpectedOutput(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'expected_output',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': '\nThis is the expect criteria for your final answer: {expected_output} \n you MUST return the actual complete content as the final answer, not a summary.',
                        },
                    ]

            class Tab_Slices_HumanFeedback(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'human_feedback',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'You got human feedback on your work, re-avaluate it and give a new Final Answer when ready.\n {human_feedback}',
                        },
                    ]

            class Tab_Slices_GettingInput(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'getting_input',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'This is the agent final answer: {final_answer}\nPlease provide a feedback: ',
                        },
                    ]

        class Tab_Errors(ConfigPages):
            def __init__(self, parent):
                super().__init__(parent=parent, align_left=True)  # , text_size=10)

                self.pages = {
                    "Force final answer": self.Tab_Errors_ForceFinalAnswer(parent=self),
                    "Agent tool unexsiting coworker": self.Tab_Errors_AgentToolUnexistingCoworker(parent=self),
                    "Task repeated usage": self.Tab_Errors_TaskRepeatedUsage(parent=self),
                    "Tool usage error": self.Tab_Errors_ToolUsageError(parent=self),
                    "Tool arguments error": self.Tab_Errors_ToolArgumentsError(parent=self),
                    "Wrong tool name": self.Tab_Errors_WrongToolName(parent=self),
                    "Tool usage exception": self.Tab_Errors_ToolUsageException(parent=self),
                }

            class Tab_Errors_ForceFinalAnswer(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'force_final_answer',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'Tool won\'t be use because it\'s time to give your final answer. Don\'t use tools and just your absolute BEST Final answer.',
                        },
                    ]

            class Tab_Errors_AgentToolUnexistingCoworker(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'agent_tool_unexsiting_coworker',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': '\nError executing tool. Co-worker mentioned not found, it must to be one of the following options:\n{coworkers}\n',
                        },
                    ]

            class Tab_Errors_TaskRepeatedUsage(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'task_repeated_usage',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'I tried reusing the same input, I must stop using this action input. I\'ll try something else instead.\n\n',
                        },
                    ]

            class Tab_Errors_ToolUsageError(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'tool_usage_error',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'I encountered an error: {error}',
                        },
                    ]

            class Tab_Errors_ToolArgumentsError(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'tool_arguments_error',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'Error: the Action Input is not a valid key, value dictionary.',
                        },
                    ]

            class Tab_Errors_WrongToolName(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'wrong_tool_name',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'You tried to use the tool {tool}, but it doesn\'t exist. You must use one of the following tools, use one at time: {tools}.',
                        },
                    ]

            class Tab_Errors_ToolUsageException(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'tool_usage_exception',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'I encountered an error while trying to use the tool. This was the error: {error}.\n Tool {tool} accepts these inputs: {tool_inputs}',
                        },
                    ]

        class Tab_Tools(ConfigPages):
            def __init__(self, parent):
                super().__init__(parent=parent, align_left=True)  # , text_size=10)

                self.pages = {
                    'Delegate work': self.Tab_Tools_DelegateWork(parent=self),
                    'Ask question': self.Tab_Tools_AskQuestion(parent=self)
                }

            class Tab_Tools_DelegateWork(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'tool_usage_exception',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': 'I encountered an error while trying to use the tool. This was the error: {error}.\n Tool {tool} accepts these inputs: {tool_inputs}',
                        },
                    ]

            class Tab_Tools_AskQuestion(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.parent = parent
                    self.schema = [
                        {
                            'text': '',
                            'key': 'tool_usage_exception',
                            'type': str,
                            'width': 300,
                            'label_position': None,
                            'num_lines': 15,
                            'default': "Delegate a specific task to one of the following co-workers: {coworkers}\nThe input to this tool should be the co-worker, the task you want them to do, and ALL necessary context to exectue the task, they know nothing about the task, so share absolute everything you know, don't reference things but instead explain them.",
                        },
                    ]
