import sys
import time

import pyautogui
from PySide6.QtCore import QRunnable
from PySide6.QtWidgets import QWidget, QGraphicsItem, QApplication

from src.utils import sql
from src.utils.helpers import convert_to_safe_case, compute_workflow

SPEED_RUN = False


def check_alive():
    # Check if the main window is alive
    if not QApplication.instance():
        sys.exit(0)
    if not QApplication.activeWindow():
        sys.exit(0)


def get_widget_coords(widget, top_left=False):
    if isinstance(widget, QWidget):
        point = widget.rect().center() if not top_left else widget.rect().topLeft()
        global_point = widget.mapToGlobal(point)
    elif isinstance(widget, QGraphicsItem):
        center = widget.boundingRect().center()
        scene_center = widget.mapToScene(center)
        view = widget.scene().views()[0]
        viewport_center = view.mapFromScene(scene_center)
        global_point = view.viewport().mapToGlobal(viewport_center)
    else:
        raise ValueError("Unsupported widget type")
    return global_point.x(), global_point.y()


def click_widget(widget, double=False, nb=False):
    x, y = get_widget_coords(widget)
    click_coords(x, y, double)


def hover_widget(widget):
    x, y = get_widget_coords(widget)
    move_mouse(x, y)


def move_mouse(x, y, speed=1000):  # speed is px/s
    current_pos = pyautogui.position()
    duration = ((x - current_pos.x) ** 2 + (y - current_pos.y) ** 2) ** 0.5 / speed
    check_alive()
    if SPEED_RUN:
        duration = 0.0
    pyautogui.moveTo(x, y, duration=duration)


def type_text(text, interval=20):
    for c in text:
        check_alive()
        pyautogui.typewrite(c)
        pyautogui.sleep(interval/1000)


def click_coords(x, y, double=False):
    check_alive()
    move_mouse(x, y)
    pyautogui.click(x, y)
    if double:
        pyautogui.sleep(0.1)
        pyautogui.click(x, y)

    pyautogui.sleep(0.2)


def click_tree_item_cell(tree_widget, index, column, double=False, only_hover=False):
    # If tree has a header, it is included in the index
    if isinstance(column, str):
        columns = [convert_to_safe_case(item.get('key', item['text'])) for item in tree_widget.parent.schema]
        if column not in columns:
            raise ValueError(f'Column {column} not found in tree widget')
        column = columns.index(column)

    if isinstance(index, str):
        row_vals = [tree_widget.topLevelItem(i).text(column) for i in range(tree_widget.topLevelItemCount())]
        if index not in row_vals:
            raise ValueError(f'Item {index} not found in column {column}')
        index = row_vals.index(index)

    item_rect = tree_widget.visualRect(tree_widget.model().index(index, column))
    center = item_rect.center()
    global_center = tree_widget.mapToGlobal(center)
    if only_hover:
        move_mouse(global_center.x(), global_center.y())
    else:
        click_coords(global_center.x(), global_center.y(), double)


class DemoRunnable(QRunnable):
    def __init__(self, main):
        super().__init__()
        self.main = main

    def get_first_chat_bubble_container(self):
        page_chat = self.main.page_chat
        first_chat_bubble_container = page_chat.message_collection.chat_bubbles[0]
        return first_chat_bubble_container

    def goto_page(self, page_name, parent_page=None):
        if not parent_page:
            page_in_main = self.main.main_menu.pages.get(page_name, None)
            if page_in_main:
                parent_page = self.main.main_menu
            else:
                parent_page = self.main.page_settings

        btn = parent_page.settings_sidebar.page_buttons.get(page_name, None)
        page = parent_page.pages.get(page_name, None)
        if not btn:
            raise ValueError(f'Page {page_name} not found')

        click_widget(btn)
        return page

    def toggle_chat_settings(self, state):
        page_chat = self.main.page_chat
        currently_visible = page_chat.workflow_settings.isVisible()
        if state != currently_visible:
            widget = page_chat.top_bar.agent_name_label
            click_widget(widget)

    def click_context_menu_item(self, source_widget, item_index, row_height=24):
        bx, by = get_widget_coords(source_widget)
        by += source_widget.height() / 2
        click_coords(bx + 60, by + (item_index * row_height))

    def click_workflow_coords(self, workflow_settings, x, y, double=False):
        vx, vy = get_widget_coords(workflow_settings.workflow_buttons, top_left=True)
        vy += workflow_settings.workflow_buttons.height()
        vx += x
        vy += y
        click_coords(vx, vy, double=double)

    def sleep(self, seconds):
        if SPEED_RUN:
            return
        time.sleep(seconds)

    def send_message(self, message):
        message_input = self.main.message_text
        click_widget(message_input)
        type_text(message)

        send_button = self.main.send_button
        click_widget(send_button)

        while self.main.page_chat.workflow.responding:
            time.sleep(0.1)

    def text_to_speech(self, text, blocking=False, wait_percent=0.0):
        if SPEED_RUN:
            return

        if wait_percent > 0.0:
            blocking = True

        wf_config = {
            "_TYPE": "workflow",
            "config": {
                "autorun": True,
            },
            "inputs": [],
            "members": [
                {
                    "config": {
                        "_TYPE": "model",
                        "model": {
                            "kind": "VOICE",
                            "model_name": "56AoDkrOh6qfVPDXZ7Pt",
                            "model_params": {},
                            "provider": "elevenlabs"
                        },
                        "model_type": "Voice",
                        "text": text,
                        "use_cache": True,
                        "wait_until_finished": blocking,
                        "wait_percent": wait_percent,
                    },
                    "id": "1",
                    "loc_x": 105,
                    "loc_y": 57
                }
            ],
            "params": []
        }
        check_alive()
        with sql.write_to_file(None):
            # None uses default path, this computes with the users database not the demo one
            # This is so voice cache isn't erased
            compute_workflow(wf_config)

    def run(self):
        demo_segments = {
            'Models': False,
            'Chat': False,  # + Images
            'Agents': False,
            'Blocks': False,
            'Workflows': True,
            'Workflows 2': True,
            'Tools': True,
            'Modules': True,
            'Builder': True,
        }
        enable_all = False
        if enable_all:
            demo_segments = {k: True for k in demo_segments.keys()}

        # self.text_to_speech(dedent('''
        #     In this video we'll be showing you the key concepts of Agent Pilot,
        #     starting with the basics and then moving on to more advanced features like multi-member chats,
        #     nested workflows, tool calling, structured outputs and other powerful features.
        # '''),
        # blocking=True)
        global SPEED_RUN
        SPEED_RUN = True

        if demo_segments['Models']:
            self.text_to_speech(blocking=True,
                text="""Let's start by adding an API key in the settings."""
            )
            self.text_to_speech(blocking=False,
                text="""Go to the settings page, then click Models."""
            )
            page_settings = self.goto_page('Settings')
            page_models = self.goto_page('Models', page_settings)
            self.text_to_speech(blocking=True, wait_percent=0.75,
                text="""Here you can manage the models under each provider. Find the provider you want to use, then enter the API key for it here."""
            )
            click_tree_item_cell(page_models.tree, 6, 'api_key')
            # wait_until_finished_speaking()
            self.sleep(2)

        if demo_segments['Chat']:
            self.text_to_speech(blocking=False,
                text="""Head back to the chat page by clicking this Chat icon."""
            )
            self.goto_page('Chat')
            page_chat = self.goto_page('Chat')  # 2 ensure blank chat
            self.sleep(1.5)
            # wait_until_finished_speaking()
            self.text_to_speech(blocking=True, wait_percent=0.3,
                text="""To open the settings for the chat, click the chat name. This is just a chat with a single Agent, but it can be an entire workflow.."""
            )
            self.toggle_chat_settings(True)
            # wait_until_finished_speaking()
            self.sleep(3)
            self.text_to_speech(blocking=False, wait_percent=0.6,
                text="""We'll go over that soon, but first let's set the model for the agent, go to the `Chat` tab and set the chat model, here."""
            )

            chat_workflow_settings = page_chat.workflow_settings
            chat_agent_settings = chat_workflow_settings.member_config_widget.agent_settings
            page_chat_wf_chat = self.goto_page('Chat', chat_agent_settings)
            agent_model_combo = page_chat_wf_chat.pages['Messages'].model
            cb_x, cb_y = get_widget_coords(agent_model_combo)

            click_widget(agent_model_combo)  # BLOCKING
            self.sleep(2)
            pyautogui.press('esc')
            # pyautogui.moveTo(cb_x, cb_y, duration=0.3)
            # QTest.qWait(500)

            self.text_to_speech(blocking=False,
                text="""Try chatting with it."""
            )
            self.send_message('Hello world')

            self.toggle_chat_settings(False)
            # time.sleep(1.5)

            self.text_to_speech(blocking=False,
                text="""You can edit messages and resend them, this creates a branch."""
            )
            first_chat_bubble_container = self.get_first_chat_bubble_container()  # page_chat.message_collection.chat_bubbles[0]
            first_chat_bubble = first_chat_bubble_container.bubble
            click_widget(first_chat_bubble)

            pyautogui.press('end')
            type_text('!!!!!!!')

            resend_button = getattr(first_chat_bubble_container, 'btn_resend', None)
            if resend_button:
                click_widget(resend_button)

            while self.main.page_chat.workflow.responding:
                print('Waiting for response...')
                time.sleep(0.1)

            self.sleep(1)
            self.text_to_speech(blocking=False,
                text="""You can cycle between these branches with these buttons."""
            )
            first_chat_bubble_container = self.get_first_chat_bubble_container()
            first_chat_bubble = first_chat_bubble_container.bubble

            hover_widget(first_chat_bubble)
            branch_btn_back = first_chat_bubble.branch_buttons.btn_back
            branch_btn_next = first_chat_bubble.branch_buttons.btn_next
            click_widget(branch_btn_back)
            click_widget(branch_btn_next)
            click_widget(branch_btn_back)
            click_widget(branch_btn_next)
            self.sleep(1.5)

            self.goto_page('Chat')  # New chat
            self.text_to_speech(blocking=True,
                text="""To start a new chat, click this plus button. This will create a new chat with the exact same settings as the previous one."""
            )
            # time.sleep(0.8)
            # wait_until_finished_speaking()

            self.text_to_speech(blocking=False,
                text="""All your chats are saved in the Chats page - here - so you can continue or refer back to them."""
            )
            self.goto_page('Contexts')
            self.sleep(3)
            self.goto_page('Chat')
            self.sleep(1)

            # self.text_to_speech(blocking=False,
            #     text="""You can quickly cycle between chats by using these navigation buttons"""
            # )
            self.text_to_speech(blocking=False,
                text="""Any chat workflow can be saved for reuse."""
            )
            self.toggle_chat_settings(True)
            chat_save_button = chat_workflow_settings.workflow_buttons.btn_save_as
            click_widget(chat_save_button)  # BLOCKING
            self.sleep(1)
            self.text_to_speech(blocking=True,
                text="""Click this save icon, we can see there's multiple options. We can save as an Agent, Block, Tool or Task. All of these fundamentally use the same workflow engine. But each are used by the system slightly differently."""
            )
            self.text_to_speech(blocking=True,
                text="""Agents are Workflows intended for the user to interact with. This can be anything from a single LLM to a multi-member workflow."""
            )
            self.text_to_speech(blocking=True,
                text="""Blocks are workflows that run behind the scenes. They can be used in any workflow, or text field such as an agent's system message. These allow re-usability and consistency across multiple entities."""
            )
            self.text_to_speech(blocking=True,
                text="""Tools are workflows that can be called by a language model to execute particular actions or retrieve specific information. These often interact with external systems or APIs."""
            )

        if demo_segments['Agents']:
            pyautogui.press('esc')
            page_agents = self.goto_page('Agents')
            self.text_to_speech(blocking=True,
                text="""Let's go to the Agents page, these are the workflows you interact with. They can be Agent workflows or just a single LLM, or just a snippet of code you want to run."""
            )

            click_tree_item_cell(page_agents.tree, 'Dev Help', 'name')
            self.text_to_speech(blocking=True,
                text="""Selecting an agent will open its settings, this is not tied to any chat, these settings will be the default whenever the agent is added to a workflow."""
            )
            self.text_to_speech(blocking=True,
                text="""Start a new chat with an agent by double clicking on it."""
            )
            click_tree_item_cell(page_agents.tree, 'Snoop Dogg', 'name', double=True)

            self.text_to_speech(blocking=True,
                text="""Let's open the chat settings again, here there's a field to set the system message for the agent."""
            )
            self.toggle_chat_settings(True)
            chat_wf_settings = self.main.page_chat.workflow_settings
            chat_agent_settings = chat_wf_settings.member_config_widget.agent_settings
            page_chat_wf_chat = self.goto_page('Chat', chat_agent_settings)
            sys_msg = page_chat_wf_chat.pages['Messages'].sys_msg
            click_widget(sys_msg)
            self.text_to_speech(blocking=True,
                text="""You can write custom instructions here to make it behave how you want."""
            )
            self.text_to_speech(blocking=True,
                text="""Here you can see it says "known personality" enclosed in curly braces."""
            )
            self.text_to_speech(blocking=True,
                text="""This is actually the name of a Block we have in our block collection which you can access here."""
            )

        if demo_segments['Blocks']:
            self.text_to_speech(blocking=False,
                text="""Go to "known personality", and you can see it contains a block of text, the placeholder from the system message will be substituted with the output of this block."""
            )
            page_blocks = self.goto_page('Blocks')
            click_tree_item_cell(page_blocks.tree, 'known-personality', 'name')
            click_tree_item_cell(page_blocks.tree, 'known-personality', 'name')
            block_settings = page_blocks.config_widget.member_config_widget.block_settings
            click_widget(block_settings.data)
            self.sleep(3.5)
            click_widget(block_settings.block_type)
            self.text_to_speech(blocking=True,
                text="""Blocks can either be Text, Code, Prompt or even an entire workflow."""
            )

        if demo_segments['Workflows']:
            self.text_to_speech(blocking=True,
                text="""Lets go over the mechanics of multi-member workflows, and then we'll touch on how to use them practically."""
            )
            self.text_to_speech(blocking=False,
                text="""Go to the chat page and open the settings."""
            )
            self.goto_page('Chat')
            page_chat = self.goto_page('Chat')  # dbl click
            self.toggle_chat_settings(True)

            chat_workflow_settings = page_chat.workflow_settings
            chat_buttons = chat_workflow_settings.workflow_buttons
            click_widget(chat_buttons.btn_add)

            self.text_to_speech(blocking=True,
                text="""Click this plus button to add another member. You'll have a few options. For now let's just add a blank agent."""
            )
            self.click_context_menu_item(chat_buttons.btn_add, item_index=1)

            dialog_window = QApplication.activeWindow()
            dialog_tree = dialog_window.tree_widget
            click_tree_item_cell(dialog_tree, 'Empty agent', 0, double=True)
            # click_widget(active_window)
            self.click_workflow_coords(chat_workflow_settings, 200, 60, double=True)
            self.text_to_speech(blocking=True,
                text="""Drop it on the workflow!"""
            )

            members_in_view = chat_workflow_settings.members_in_view
            members = list(members_in_view.values())

            self.text_to_speech(blocking=False,
                text="""An important thing to know is the order of response flows from left to right, so in this workflow, after you send a message, this member will always respond first, followed by this member."""
            )
            self.sleep(4)
            click_widget(members[0])
            self.sleep(2)
            click_widget(members[1])
            self.sleep(2)
            click_widget(members[2])
            self.sleep(2)

            self.text_to_speech(blocking=False,
                text="""Unless, an input is placed from this member to this one, in this case, because the input of this one flows into this, this member responds first."""
            )
            click_widget(members[2].output_point)
            click_widget(members[1].input_point)
            self.sleep(7)

            click_widget(list(chat_workflow_settings.inputs_in_view.values())[0])
            click_widget(chat_workflow_settings.workflow_buttons.btn_delete)

            delete_dialog = QApplication.activeWindow()
            if delete_dialog:
                # Choose QMessageBox.Yes (delete_dialog is a QMessageBox)
                yes_button = delete_dialog.buttons()[0]  # First button is typically "Yes"
                click_widget(yes_button)

            click_widget(chat_buttons.btn_member_list)
            self.text_to_speech(blocking=True,
                text="""Click on the members button here to show the list of members, in the order they will respond."""
            )
            click_widget(chat_buttons.btn_member_list)

            members_in_view = chat_workflow_settings.members_in_view
            members = list(members_in_view.values())

            hover_widget(members[0])
            self.text_to_speech(blocking=True,
                text="""You should almost always have a user member at the beginning, this represents you. There can be multiple user instances, so you can add your input at any point within a workflow."""
            )

            self.text_to_speech(blocking=True,
                text="""Let's go over the context window of each agent"""
            )

            click_widget(members[1])
            self.text_to_speech(blocking=True,
                text="""If the agent has no predefined inputs, then it can see all other member messages, even members placed AFTER it from previous turns."""
            )
            hover_widget(members[2])
            self.text_to_speech(blocking=False,
                text="""But if an agent has inputs set like this one, then it'll only see messages from the agents flowing into it."""
            )
            click_widget(members[1].output_point)
            click_widget(members[2].input_point)
            self.sleep(4)

            click_widget(list(chat_workflow_settings.inputs_in_view.values())[0])
            self.text_to_speech(blocking=True,
                text="""Clicking on an input will show it's settings, here you can map information between responses, structured outputs and parameters"""
            )

            inputs_json_widget = chat_workflow_settings.member_config_widget.input_settings.widgets[1]
            click_tree_item_cell(inputs_json_widget.tree, 0, 'target', only_hover=True)
            self.text_to_speech(blocking=True,
                text="""By default, there's one mapping, from the source member's output (in this case an LLM response) to the target member's message input."""
            )
            # click_widget(chat_workflow_settings.member_config_widget)
            self.text_to_speech(blocking=True,
                text="""Message inputs can only be sent to Agents. They allow custom user messages with multi turn functionality."""
            )

        if demo_segments['Workflows 2']:

            self.text_to_speech(blocking=True,
                text="""Lets add an empty text block."""
            )
            SPEED_RUN = False
            self.toggle_chat_settings(True)
            page_chat = self.main.page_chat
            chat_workflow_settings = page_chat.workflow_settings
            chat_buttons = chat_workflow_settings.workflow_buttons
            btn_add = chat_buttons.btn_add
            click_widget(btn_add)
            self.click_context_menu_item(btn_add, item_index=4)

            dialog_window = QApplication.activeWindow()
            dialog_tree = dialog_window.tree_widget
            click_tree_item_cell(dialog_tree, 'Empty text block', 0, double=True)

            self.click_workflow_coords(chat_workflow_settings, 300, 120, double=True)
            members = list(chat_workflow_settings.members_in_view.values())

            click_widget(members[2].output_point)
            click_widget(members[3].input_point)
            click_widget(list(chat_workflow_settings.inputs_in_view.values())[1])

            self.text_to_speech(blocking=True,
                text="""Not every member type supports the message attribute, if we add an input to this text block, then we see a dashed line instead. This indicates there is no information transmitted between the members, but before the target member can run, the source member must finish executing."""
            )
            self.text_to_speech(blocking=True,
                text="""These attributes can transmit other data like structured output values and member parameters."""
            )
            self.text_to_speech(blocking=True,
                text="""We'll go over these soon, but first let's make a simple mixture of agents workflow to get a feel for how to use this practically."""
            )
            self.text_to_speech(blocking=True,
                text="""Let's add two agent members, one will be Gpt-4 O and the other Sonnet 3.5. Both of these should only see the user's message, so add a single input from the user to both agents."""
            )
            self.text_to_speech(blocking=True,
                text="""Since they don't depend on each other, they can run concurrently. To do this align them vertically."""
            )
            self.text_to_speech(blocking=True,
                text="""Set their models, and we also need to go into the group tab and set hide bubbles to true, and set the output placeholder to something unique. Remember to do this for both."""
            )
            self.text_to_speech(blocking=True,
                text="""We need another Agent here to use for the final response, place it down and set its model. In the system message, we can use a prompt to combine the outputs of the previous agents, using their output placeholders, enclosed in curly braces."""
            )
            self.text_to_speech(blocking=True,
                text="""Let's try chatting with this workflow. Those asynchronous agents should be working behind the scenes and the final agent should respond with a combined output."""
            )
            self.text_to_speech(blocking=True,
                text="""You can toggle the hidden bubbles by clicking this toggle icon here in the workflow settings."""
            )
            self.text_to_speech(blocking=True,
                text="""Branching chat works for multi member workflows too, giving you a practical way to use and refine your finished workflow."""
            )
            self.text_to_speech(blocking=True,
                text="""Let's save this workflow as an agent, so we can use it later."""
            )
            self.text_to_speech(blocking=True,
                text="""Now you can find it in the agents page, and start a new chat with it."""
            )
            self.text_to_speech(blocking=True,
                text="""Let's go over tool-calling. This gives your agents access to external functions and capabilities."""
            )
            self.text_to_speech(blocking=True,
                text="""Head over to the Tools page by clicking here"""
            )
            self.text_to_speech(blocking=True,
                text="""The list of tools here can be added to any agent."""
            )
            self.text_to_speech(blocking=True,
                text="""By default, a tool is just a code block. But it can be an entire workflow."""
            )
            self.text_to_speech(blocking=True,
                text=""""""
            )
            self.text_to_speech(blocking=True,
                text=""""""
            )
            self.text_to_speech(blocking=True,
                text=""""""
            )
            self.text_to_speech(blocking=True,
                text=""""""
            )
            self.text_to_speech(blocking=True,
                text=""""""
            )
            self.text_to_speech(blocking=True,
                text=""""""
            )

            # self.text_to_speech(blocking=True,
            #     text="""Drop it on the workflow!"""
            # )

        time.sleep(2)
        self.main.test_running = False
