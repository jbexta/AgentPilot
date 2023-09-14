import os
import threading
import pyttsx3
from utils.apis import oai
from agent.base import Agent
from utils import sql, api, config

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


if not os.path.exists(config.get_value('system.db-path')):
    raise Exception('Database not found')

oai_api_exists = api.apis['openai']['priv_key'] != ''
if not oai_api_exists:
    environ_key = os.environ.get('OPENAI_API_KEY')
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
