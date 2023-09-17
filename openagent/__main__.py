import os
import threading
import pyttsx3
from utils.apis import oai
from agent.base import Agent
from utils import sql, api, config

# test_query = 'Set my wallpaper'
# test_embedding = oai.gen_embedding(test_query)
# all_embeddings = sql.get_results('SELECT original_text, embedding FROM embeddings', return_type='dict')
#
# for original_text, embedding in all_embeddings.items():
#     cs = semantic.cosine_similarity(test_embedding, [float(x) for x in embedding.split(',')])
#     print(original_text, cs)
# d = oai.get_scalar("""Analyze the provided thoughts and actions/detections list and if appropriate, return the ID of the most valid Action/Detection based on the last thought. If none are valid then return "0".
# Note: To identify the primary action in the last thought, focus on the main verb that indicates the current or next immediate action the speaker intends to take. Consider the verb's tense to prioritize actions that are planned or ongoing over those that are completed or auxiliary. Disregard actions that are merely described or implied without being the central focus of the current intention.
#
# ACTIONS/DETECTIONS LIST:
# ID: Description
# ____________________
# 0: NO ACTION TO TAKE AND NOTHING DETECTED
# 1: Change the desktop background,
# 2: Search and Play a specific song/album/artist/playlist/genre,
# 3: Do something like Generate/Create/Make/Draw/Design something like an Image/Picture/Photo/Drawing/Illustration etc,
# 4: Play music / resume playback where what to play is unspecified,
# 5: Switch music playback to smartphone for current music streaming
#
# Use the following thoughts to guide your analysis. The last thought (denoted with arrows ">> ... <<") is the thought you will use to determine the most valid ID.
# The preceding assistant messages are provided to give you context for the last thought, to determine whether an action/detection is valid.
#
# CONTEXT:
# Task: `generate an image of a duck and set it as my background`
# Thought: I need to generate an image of a duck.
# Result: "The image has been successfuly generated." (path = /tmp/tmpfy0f7m0o.png)
# >> Thought: `I need to set the Image(`/tmp/tmpfy0f7m0o.png`) as the background.` <<
#
# TASK:
# Examine the thoughts in detail, applying logic and reasoning to ascertain the most valid ID based on the latest thought.
# The verb expressing the main action in the sentence is crucial to making the right choice. If a secondary action or condition is described, it should not take precedence over the main action indicated in the last thought. Focusing particularly on the tense to identify the valid - yet to be performed - action.
# If no actions or detections from the list are valid based on the last thought, simply output "0".
#
# ID (with reasoning): """)
# print(d)
# d = oai.get_scalar("""
# You are completing a task by breaking it down into smaller actions that are explicitly expressed in the task.
# You have access to a wide range of actions, which you will search through and select after each thought, unless the task is complete or can not complete.
#
# Only return the inferred Task request.
#
# -- EXAMPLE OUTPUTS --
#
# Task: what is the x
# Thought: I need to get the x
# Action: Get the x
# Result: The x is [x_val]
# Thought: I have now completed the task
# END
#
#
# Task: what is x
# Thought: I need to get x
# Action: Get x
# Result: There is no x
# Thought: I can not complete the task
# END
#
#
# Task: do x and y
# Thought: First, I need to do x
# Action: Do x
# Result: I have done x
# Thought: Now, I need to do y
# Action: Do y
# Result: I have done y
# Thought: I have now completed the task
# END
#
#
# Task: do x and y
# Thought: First, I need to do x
# Action: Do x
# Result: I have done x
# Thought: Now, I need to do y
# Action: Do y
# Result: There was an error doing y
# Thought: I can not complete the task
# END
#
#
# Task: set x to y
# Thought: First, I need to get y
# Action: Get y
# Result: y is [y_val]
# Thought: Now, I need to set x to [y_val]
# Action: Set x to [y_val]
# Result: I have set x to [y_val]
# Thought: I have now completed the task
# END
#
#
# Task: send a x with the y of z
# Thought: First, I need to get the y of z
# Action Get the y of z
# Result: The y of z is [yz_val]
# Thought: Now, I need to send a x with [yz_val]
# Action: Send a x with [yz_val]
# Result: I have sent a x with [yz_val]
# Thought: I have now completed the task
# END
#
# Use the following conversation as context. The last user message (denoted with arrows ">> ... <<") is the message that triggered the task.
# The preceding assistant messages are provided to give you context for the task request if necessary.
#
# CONVERSATION:
# assistant: `Ah, my dear interlocutor, I have conjured a delightful image of a cat and a dog frolicking together. Allow me to set it as your wallpaper, so you may bask in their adorable companionship every time you glance at your screen. The task has been completed. Enjoy!`
# >> user: `what time is it` <<
#
# Task: """)
# print(d)
# dd = 1


# Return the next thought.
# If the task is completed then return "I have now completed the task.",
# If the task can not be completed then return "I can not complete task.".
# Otherwise, return a thought that is a description of the next action to take verbatim from the task request.

# test_popup = show_popup(message='Test popup',
#                         backcolor='#8fb7f7',
#                         tick_button_func=None,
#                         cross_button_func=lambda x: print(''))

engine = pyttsx3.init()
voices = engine.getProperty('voices')

agent = Agent()
agent.context.print_history()


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
        agent.send(user_input)  # .save_message('user', user_input)
