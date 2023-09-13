import os
import threading
import pyttsx3
from utils.apis import oai
from agent.base import Agent
from utils import sql, api, config

#         self.prompt = f"""
# Task request: `{objective}`
# You are a super cognitive thought machine. You can do anything.
# You have access to a wide range of actions, which you will search through and select after each thought, unless the task is completed.
#
# Actions:
#   Tell(x)
#   Ask(x)
#
# Only return the next Thought. The Action and Observation will be returned automatically.
# If the task is completed then return: "Thought: I have no further thoughts."
# Otherwise, return a thought that is a description of the next action to take verbatim from the task request.
#
# -- EXAMPLE OUTPUTS --
#
# Task: what is x
# Thought: I need to get x
# Action: Get x
# Observation: x is [x_val]
# Thought: I have now completed the task.
# END
#
# Task: do x and y
# Thought: I need to do x
# Action: Do x
# Observation: I have done x
# Thought: I need to do y
# Action: Do y
# Observation: I have done y
# Thought: I have now completed the task
# END
#
#
# Task: set x to y
# Thought: I need to get y
# Action: Get y
# Observation: y is [y_val]
# Thought: I need to set x to [y_val]
# Action: Set x to [y_val]
# Observation: I have set x to [y_val]
# Thought: I have now completed the task
# END
#
#
# Task: combine x and y and write it to z
# Thought: I need to get x
# Action: Get x
# Observation: x is [x_val]
# Thought: I need to get y
# Action: Get y
# Observation: y is [y_val]
# Thought: I need to write [x_val] and [y_val] to z
# Action: Write [x_val] and [y_val] to z
# Observation: I have written [x_val] and [y_val] to z
# Thought: I have now completed the task
# END
#
# Return the next thought, or if the task is completed, return "Thought: I have now completed the task."
#
# Task: `{objective}`
# """

# test_popup = show_popup(message='Test popup',
#                         backcolor='#8fb7f7',
#                         tick_button_func=None,
#                         cross_button_func=lambda x: print(''))

engine = pyttsx3.init()
voices = engine.getProperty('voices')

agent = Agent()
agent.context.print_history()

main_thread = threading.Thread(target=agent.run)
main_thread.start()

# conf_db_path = config.get_value('system.db-path')
# while not os.path.exists(conf_db_path):
#     user_input = input(f"Enter the database filepath: ")
#     if not user_input: continue
#     config.set_value('system.db-path', user_input)
#     conf_db_path = user_input
# config.set_value('system.db-path', conf_db_path)


if not os.path.exists(config.get_value('system.db-path')):
    raise Exception('Database not found')

# api.load_api_keys()
oai_api_exists = api.apis['openai']['priv_key'] != ''
if not oai_api_exists:
    environ_key = os.environ['OPENAI_API_KEY'] if 'OPENAI_API_KEY' in os.environ else ''
    if environ_key:
        print('Found OpenAI API key in environment variables')
    user_input = input(f"Enter your OpenAI API key: {'(press enter to use env variable)' if environ_key else ''}")
    if not user_input: user_input = environ_key

    sql.execute(f"UPDATE apis SET priv_key = '{user_input.strip()}' WHERE name = 'OpenAI'")
    api.apis['openai']['priv_key'] = user_input.strip()
    oai.openai.api_key = api.apis['openai']['priv_key']

while True:
    agent.context.wait_until_current_role('user', not_equals=True)
    user_input = input("\nUser: ")
    if user_input:
        agent.save_message('user', user_input)
