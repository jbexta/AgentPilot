# from termcolor import colored
from src.utils import config, embeddings, semantic, logs, llm
from src.utils.helpers import remove_brackets


class ExplicitReAct:
    def __init__(self, parent_task):
        self.parent_task = parent_task
        self.thought_task = None
        self.thought_count = 0
        # self.react_context = Context()

        self.thoughts = []
        self.actions = []
        self.action_names = []
        self.results = []
        self.last_thought_embedding = None
        self.last_result_embedding = None

        self.objective = self.parent_task.objective
        conversation_str = self.parent_task.agent.workflow.message_history.get_conversation_str(msg_limit=2)

        # objective_str = f'Task: {self.objective}\nRequest: ' if self.objective else 'Task: '
        self.prompt = f"""
You are completing an OBJECTIVE by breaking it down into smaller actions that are explicitly expressed in the OBJECTIVE.
You have access to a wide range of actions, which you will search through and select after each thought message, unless the OBJECTIVE is complete or can not complete.

If the last action result indicates a failure then return the thought: "OBJECTIVE FAILED"
If all elements of the OBJECTIVE have been completed then return the thought: "OBJECTIVE COMPLETE"
Otherwise, return a thought that is a description of the next action to take verbatim from the OBJECTIVE.

-- EXAMPLES --

OBJECTIVE: what is the x
Thought: I need to get the x
Action: {{action-desc}}
Result: Done, The x is [x_val]
Thought: OBJECTIVE COMPLETE
END

OBJECTIVE: set x to y
Thought: First, I need to get y
Action: {{action-desc}}
Result: Done, y is [y_val]
Thought: Now, I need to set x to [y_val]
Action: {{action-desc}}
Result: Done, Successfully set x to [y_val]
Thought: OBJECTIVE COMPLETE
END

OBJECTIVE: click x and open y
Thought: I need to click x
Action: {{action-desc}}
Result: Done, clicked on x
Thought: Now, I need to open y
Action: {{action-desc}}
Result: Done, y is now open
Thought: OBJECTIVE COMPLETE
END

OBJECTIVE: do x and y
Thought: First, I need to do x
Action: {{action-desc}}
Result: Done, x and y are finished
Thought: OBJECTIVE COMPLETE
END

OBJECTIVE: what is x
Thought: I need to get x
Action: {{action-desc}}
Result: Failed, There is no x
Thought: OBJECTIVE FAILED
END

OBJECTIVE: do x and y then set z to the cubed root of w
Thought: First, I need to do x and y
Action: {{action-desc}}
Result: Done, x is done
Thought: Now, I need to do y
Action: {{action-desc}}
Result: Done, y is complete
Thought: Now, I need to get the cubed root of w
Action: {{action-desc}}
Result: Done, The cubed root of w is [w3_val]
Thought: Now, I need to set z to [w3_val]
Action: {{action-desc}}
Result: Failed, There was an error setting z to [w3_val]
Thought: OBJECTIVE FAILED
END

OBJECTIVE: what is x
Thought: I need to get x
Action: {{action-desc}}
Result: Done, 
Thought: OBJECTIVE COMPLETE
END

OBJECTIVE: send a x with the y of z
Thought: First, I need to get the y of z
Action {{action-desc}}
Result: Done, The y of z is [yz_val]
Thought: Now, I need to send a x with [yz_val]
Action: {{action-desc}}
Result: Done, Successfully sent a x with [yz_val]
Thought: OBJECTIVE COMPLETE

OBJECTIVE: open x y and z
Thought: I need to open x y and z
Action: {{action-desc}}
Result: Done, x y and z are now open
Thought: OBJECTIVE COMPLETE
END

Use the following conversation as context. The last user message (denoted with arrows ">> ... <<") is the message that triggered the OBJECTIVE.
The preceding assistant messages are only provided to give you context for the last user message.

{conversation_str}

Only return the next thought message. The Action and Result will be returned automatically.
In order to relay/provide information back to the user use the thought "OBJECTIVE COMPLETE". 
The user can see all of the actions and results.

OBJECTIVE: {self.objective}
Thought: """
#         self.prompt = f"""
# You are completing a task by breaking it down into smaller actions that are explicitly expressed in the task.
# You have access to a wide range of actions, which you will search through and select after each thought message, unless the task is complete or can not complete.
#
# If all elements of the task have been completed then return the thought: "TASK COMPLETED"
# Conversely, if an element of the task can not be completed then return the thought: "CAN NOT COMPLETE"
# Otherwise, return a thought that is a description of the next action to take verbatim from the task Assistant.
#
# -- EXAMPLE OUTPUTS --
#
# Task: what is the x
# Thought: I need to get the x
# Action: Get the x
# Result: The x is [x_val]
# Thought: TASK COMPLETED
# END
#
# Task: set x to y
# Thought: First, I need to get y
# Action: Get y
# Result: y is [y_val]
# Thought: Now, I need to set x to [y_val]
# Action: Set x to [y_val]
# Result: I have set x to [y_val]
# Thought: TASK COMPLETED
# END
#
# Task: click x and open y
# Thought: I need to click x
# Action: Click x
# Result: Clicked on x
# Thought: Now, I need to open y
# Action: Open y
# Result: y is now open
# Thought: TASK COMPLETED
# END
#
# Task: do x and y
# Thought: First, I need to do x
# Action: Do x and y
# Result: I have done x and y
# Thought: TASK COMPLETED
# END
#
# Task: what is x
# Thought: I need to get x
# Action: Get x
# Result: There is no x
# Thought: CAN NOT COMPLETE
# END
#
# Task: do x and y then set z to the cubed root of w
# Thought: First, I need to do x and y
# Action: Do x
# Result: I have done x
# Thought: Now, I need to do y
# Action: Do y
# Result: I have done y
# Thought: Now, I need to get the cubed root of w
# Action: Get the cubed root of w
# Result: The cubed root of w is [w3_val]
# Thought: Now, I need to set z to [w3_val]
# Action: Set z to [w3_val]
# Result: There was an error setting z to [w3_val]
# Thought: CAN NOT COMPLETE
# END
#
# Task: send a x with the y of z
# Thought: First, I need to get the y of z
# Action Get the y of z
# Result: The y of z is [yz_val]
# Thought: Now, I need to send a x with [yz_val]
# Action: Send a x with [yz_val]
# Result: I have sent a x with [yz_val]
# Thought: TASK COMPLETED
#
# Task: open x y and z
# Thought: I need to open x y and z
# Action: Open x y and z
# Result: x y and z are now open
# Thought: TASK COMPLETED
# END
#
# Use the following conversation as context. The last user message (denoted with arrows ">> ... <<") is the message that triggered the task.
# The preceding assistant messages are only provided to give you context for the last user message.
#
# {conversation_str}
#
# Only return the next thought message. The Action and Result will be returned automatically.
#
# Task: {self.objective}
# Thought: """
        # self.react_context = {'role': 'Task', 'content': objective}

    def run(self):
        from src.zzzoperations.task import Task, TaskStatus  # Avoid circular import

        max_steps = self.parent_task.agent.config.get('react.max_steps')
        for i in range(max_steps - self.thought_count):
            if self.thought_task is None:
                thought = self.get_thought()
                unique_actions = set(self.action_names)  # temporary until better fingerprint
                if thought.upper().startswith('OBJECTIVE COMPLETE'):
                    if len(unique_actions) == 1:
                        fin_response = self.results[-1]
                        return True, fin_response
                    else:
                        fin_response = f"""[SAY] "The task has been completed" (Task = `{self.parent_task.objective}`)"""
                        return True, fin_response

                elif thought.upper().startswith('OBJECTIVE FAILED'):
                    if len(unique_actions) == 1:
                        fin_response = self.results[-1]
                        return True, fin_response
                    else:
                        fin_response = f"""[SAY] "I can not complete the task" (Task = `{self.parent_task.objective}`)"""
                        return True, fin_response

                self.thought_task = Task(agent=self.parent_task.agent,
                                         objective=thought,
                                         parent_react=self)
            try:
                request_finished, thought_response = self.thought_task.run()
                if request_finished:
                    succeeded = self.thought_task.status == TaskStatus.COMPLETED
                    self.save_action(self.thought_task.fingerprint(_type='desc'))
                    self.action_names.append(self.thought_task.fingerprint(_type='name'))
                    self.save_result(('Done, ' if succeeded else 'Failed, ') + thought_response)
                    self.thought_task = None
                else:
                    return False, thought_response

            except Exception as e:
                logs.insert_log('TASK_ERROR', str(e))
                return True, f'[SAY] "I failed the task" (Task = `{self.parent_task.objective}`)'
        logs.insert_log('TASK_ERROR', 'Max steps reached')
        return True, f'[SAY] "I failed the task because I hit the max steps limit"'

    def get_thought(self):
        thought = llm.get_scalar(self.prompt, num_lines=1)
        remove_prefixes = ['Now, ', 'First, ', 'Second, ', 'Then, ']

        thought_wo_prefix = thought
        for prefix in remove_prefixes:
            if thought_wo_prefix.startswith(prefix):
                thought_wo_prefix = thought_wo_prefix[len(prefix):]
        thought_embedding_id, thought_embedding = embeddings.get_embedding(thought_wo_prefix)

        if self.last_thought_embedding is not None:
            last_thought_similarity = semantic.cosine_similarity(self.last_thought_embedding, thought_embedding)
            if last_thought_similarity > 0.98:
                thought = "OBJECTIVE COMPLETE"
                thought_embedding_id, thought_embedding = embeddings.get_embedding(thought)

        if self.last_result_embedding is not None:
            similarity = semantic.cosine_similarity(thought_embedding, self.last_result_embedding)
            if similarity > 0.94:
                thought = "OBJECTIVE COMPLETE"
                thought_embedding_id, thought_embedding = embeddings.get_embedding(thought)

        self.last_thought_embedding = thought_embedding
        self.thoughts.append(thought)
        self.parent_task.agent.workflow.message_history.add('thought', thought, embedding_id=thought_embedding_id)
        if config.get_value('system.verbose'):
            tcolor = config.get_value('system.termcolor-verbose')
            # print(colored(f'Thought: {thought}', tcolor))
        self.thought_count += 1
        self.prompt += f'{thought}\n'
        return thought

    def save_action(self, action):
        self.actions.append(action)
        self.parent_task.agent.workflow.message_history.add('action', action)
        action = f'Action: {action}'
        if config.get_value('system.verbose'):
            tcolor = config.get_value('system.termcolor-verbose')
            # print(colored(action, tcolor))

        self.prompt += f'{action}\n'

    def save_result(self, result):
        self.results.append(result)
        result = remove_brackets(result, "[")
        msg = self.parent_task.agent.workflow.message_history.add('result', result)
        self.last_result_embedding = msg.embedding
        result = f'Result: {result}'
        if config.get_value('system.verbose'):
            tcolor = config.get_value('system.termcolor-verbose')
            # print(colored(result, tcolor))
        self.prompt += f'{result}\nThought: '
