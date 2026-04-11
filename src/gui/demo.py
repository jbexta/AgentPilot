
import sys
import time

import pyautogui
from PySide6.QtCore import QRunnable
from PySide6.QtWidgets import QWidget, QGraphicsItem, QApplication

from utils import sql
from utils.helpers import convert_to_safe_case, compute_workflow

SPEED_RUN = False


def check_alive():
    # Check if the main window is alive
    return True
    if not QApplication.instance():
        sys.exit(0)
    if not QApplication.activeWindow():
        sys.exit(0)


def resolve_widget(widget):
    """Resolve a QAction to its associated toolbar button widget."""
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QToolBar
    if isinstance(widget, QAction):
        for w in widget.associatedObjects():
            if isinstance(w, QToolBar):
                return w.widgetForAction(widget)
    return widget


def get_widget_coords(widget, top_left=False):
    widget = resolve_widget(widget)
    if isinstance(widget, QWidget):
        point = widget.rect().center() if not top_left else widget.rect().topLeft()
        global_point = widget.mapToGlobal(point)
    elif isinstance(widget, QGraphicsItem):
        center = widget.boundingRect().center()
        scene_center = widget.mapToScene(center)
        view = widget.scene().views()[0]
        viewport_center = view.mapFromScene(scene_center)
        if not view.viewport().rect().contains(viewport_center):
            view.ensureVisible(widget.sceneBoundingRect(), 50, 50)
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
        time.sleep(0.5)


class DemoRunnable(QRunnable):
    def __init__(self, main, on_finished=None):
        super().__init__()
        self.main = main
        self.on_finished = on_finished
        self._cancelled = False

    def get_first_chat_bubble_container(self):
        page_chat = self.main.main_pages.get('chat')
        first_chat_bubble_container = page_chat.message_collection.chat_bubbles[0]
        return first_chat_bubble_container

    def goto_page(self, page_name, parent_widget=None):
        if not parent_widget:
            page_in_main = self.main.main_pages.pages.get(page_name, None)
            if page_in_main:
                parent_widget = self.main.main_pages
            else:
                parent_widget = self.main.main_pages.pages['settings']

        page = parent_widget.pages.get(page_name, None)
        sidebar = getattr(parent_widget, 'settings_sidebar', None)
        if sidebar:
            btn = sidebar.page_buttons.get(page_name, None)
            if not btn:
                raise ValueError(f'Page {page_name} not found')
            click_widget(btn)
        else:
            tab_bar = parent_widget.content.tabBar()
            tab_index = list(parent_widget.pages.keys()).index(page_name)
            tab_rect = tab_bar.tabRect(tab_index)
            center = tab_rect.center()
            global_center = tab_bar.mapToGlobal(center)
            click_coords(global_center.x(), global_center.y())

        return page

    def toggle_chat_settings(self, state):
        page_chat = self.main.main_pages.get('chat')
        currently_visible = page_chat.workflow_settings.splitter.isVisible()
        if state != currently_visible:
            widget = page_chat.workflow_settings.header_widget.btn_collapse
            click_widget(widget)
            # self.sleep(0.5)

    def click_context_menu_item(self, source_widget, item_index, row_height=24):
        source_widget = resolve_widget(source_widget)
        bx, by = get_widget_coords(source_widget)
        by += source_widget.height() / 2
        click_coords(bx + 60, by + (item_index * row_height))

    def click_workflow_coords(self, workflow_settings, x, y, double=False):
        vx, vy = get_widget_coords(workflow_settings.workflow_buttons, top_left=True)
        vy += workflow_settings.workflow_buttons.height()
        vx += x
        vy += y
        click_coords(vx, vy, double=double)

    def check_cancelled(self):
        if self._cancelled:
            raise InterruptedError("Demo cancelled")

    def sleep(self, seconds):
        if SPEED_RUN:
            return
        self.check_cancelled()
        time.sleep(seconds)

    def send_message(self, message):
        message_input = self.main.page_chat.input_widget.message_text
        click_widget(message_input)
        type_text(message)

        send_button = self.main.page_chat.input_widget.send_button
        click_widget(send_button)

        page_chat = self.main.main_pages.get('chat')
        while page_chat.workflow.responding:
            time.sleep(0.1)

    def text_to_speech(self, text, blocking=False, wait_percent=0.0):
        if SPEED_RUN:
            return

        if wait_percent > 0.0:
            blocking = True

        voice_model = sql.get_scalar("""
            SELECT json_extract(value, '$."system.default_voice_model"')
            FROM settings WHERE field = 'app_config'
        """, load_json=True) or {}
        voice_model['model_params'] = {
            **voice_model.get('model_params', {}),
            'text': text,
        }

        wf_config = {
            "_TYPE": "workflow",
            "config": {
                "autorun": True,
            },
            "inputs": [],
            "members": [
                {
                    "config": {
                        "_TYPE": "audio",
                        "mode": "Model",
                        "model": voice_model,
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
        # {
        #         "_TYPE": "audio",
        #         "mode": "Model",
        #         "model": {
        #             "kind": "AUDIO",
        #             "model_name": "minimax/music-2.5",
        #             "model_params": {
        #                 "bitrate": 256000,
        #                 "lyrics": "[Instrumental intro – jungle night ambience, shacapa rhythm, low ceremonial drum heartbeat]\r\n\r\n[Verse – soft, almost whispered]\r\nMadre selva, estoy aquí\r\nAbre el camino dentro de mí\r\nQuita el miedo, quita el dolor\r\nLimpia mi sangre con tu canción\r\n\r\n[Verse]\r\nBajo la luna me dejo caer\r\nComo hoja que aprende a volver\r\nNo soy mi nombre, no soy mi piel\r\nSoy solo espíritu en tu poder\r\n\r\n[Pre-Chorus – drum pulse deepens]\r\nSana, sana, corazón\r\nSana, sana, corazón\r\nLuz antigua, dame visión\r\nLuz antigua, dame visión\r\n\r\n[Chorus – call and response energy]\r\nMuero, muero en la oscuridad\r\n[Nazco, nazco en claridad]\r\nCaigo, caigo sin resistir\r\n[Fluyo, fluyo hacia ti]\r\n\r\n[Instrumental – shacapa faster, layered tribal drums]\r\n\r\n[Verse – stronger vocal]\r\nEspíritu del río, ven\r\nEspíritu del fuego, ven\r\nEspíritu del viento, ven\r\nJaguar sagrado, ven\r\n\r\n[Bridge – almost whispered again]\r\nRompe mi ego, rompe mi voz\r\nVacía mi cuerpo de todo temor\r\nHaz de mi herida medicina\r\nHaz de mi sombra bendición\r\n\r\n[Build – drums intensify, chanting layered]\r\n\r\n[Final Chorus – full ceremonial energy]\r\nMuero en la noche\r\nNazco en la luz\r\nRegreso al origen\r\nRegreso a la cruz\r\n\r\nSoy tierra\r\nSoy río\r\nSoy fuego\r\nSoy Dios\r\n\r\n[Outro – drums slow, jungle ambience returns, distant chanting]",
        #                 "prompt": "",
        #                 "sample_rate": 16000
        #             },
        #             "provider": "wavespeed"
        #         },
        #         "name": "Audio",
        #         "preview.pending": [],
        #         "preview.results": []
        #     },
        check_alive()
        with sql.write_to_file(None):
            # None uses default path, this computes with the users database not the demo one
            # This is so voice cache isn't erased
            result = compute_workflow(wf_config)
            print(text)

        if result:
            import json
            from utils.media import play_file
            filepath = json.loads(result).get('filepath')
            if filepath:
                play_file(filepath, blocking=blocking, wait_percent=wait_percent)

    def run(self):
        from PySide6.QtCore import QTimer
        while not self.main.main_pages.isVisible():
            time.sleep(0.1)
        time.sleep(0.5)  # Let layout settle
        try:
            self._run_demo()
        finally:
            if self.on_finished:
                QTimer.singleShot(0, self.on_finished)

    def _run_demo(self):
        demo_segments = {
            'Models': False,
            'Chat': False,
            'Agents': False,
            'Blocks': False,
            'Workflows': False,
            'Workflows 2': False,
            'Tools': False,
            'Modules': False,
            'Builder': False,
            'Projects': True,
        }
        enable_all = True
        if enable_all:
            demo_segments = {k: True for k in demo_segments.keys()}

        # self.text_to_speech(dedent('''
        #     In this video we'll be showing you the key concepts of Agent Pilot,
        #     starting with the basics and then moving on to more advanced features like multi-member chats,
        #     nested workflows, tool calling, structured outputs and other powerful features.
        # '''),
        # blocking=True)
        global SPEED_RUN
        # SPEED_RUN = True

        if demo_segments['Models']:
            self.text_to_speech(blocking=True,
                text="""Let's start by adding an API key in the settings."""
            )
            self.text_to_speech(blocking=False,
                text="""Go to the settings page, then click Models."""
            )
            page_settings = self.goto_page('settings')
            page_models = self.goto_page('models', page_settings)
            self.text_to_speech(blocking=True, wait_percent=0.75,
                text="""Here you can manage the models under each provider. Find the provider you want to use, then enter the API key for it here."""
            )
            click_tree_item_cell(page_models.tree, 6, 'API_Key')
            # wait_until_finished_speaking()
            self.sleep(2)

        if demo_segments['Chat']:
            # # # # # # # # # # # # # # # # # # # # #
            SPEED_RUN = False
            # # # # # # # # # # # # # # # # # # # # #

            self.text_to_speech(blocking=False,
                text="""Head back to the chat page by clicking this Chat icon."""
            )
            self.goto_page('chat')
            page_chat = self.goto_page('chat')  # 2 ensure blank chat
            self.sleep(1.5)
            # wait_until_finished_speaking()
            self.text_to_speech(blocking=True,  # , wait_percent=0.3,
                text="""To open the settings for the chat, click the chat name. This is just a chat with a single Agent, but it can be an entire workflow.."""
            )
            self.toggle_chat_settings(True)
            # wait_until_finished_speaking()
            self.sleep(3)
            self.text_to_speech(blocking=False, wait_percent=0.6,
                text="""We'll go over that soon, but first let's set the model for the agent, go to the `Chat` tab and set the chat model, here."""
            )

            chat_workflow_settings = page_chat.workflow_settings
            chat_agent_settings = chat_workflow_settings.member_config_widget.config_widget
            chat_agent_settings.content.setCurrentIndex(0)
            agent_model_combo = chat_agent_settings.pages['Messages'].model_wgt

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

            page_chat = self.main.main_pages.get('chat')
            while page_chat.workflow.responding:
                print('Waiting for response...')
                time.sleep(0.1)

            self.sleep(1)
            self.text_to_speech(blocking=False,
                text="""You can cycle between these branches with these buttons."""
            )
            first_chat_bubble_container = self.get_first_chat_bubble_container()
            first_chat_bubble = first_chat_bubble_container.bubble

            hover_widget(first_chat_bubble)
            click_widget(first_chat_bubble.branch_buttons.btn_back)
            first_chat_bubble = self.get_first_chat_bubble_container().bubble
            click_widget(first_chat_bubble.branch_buttons.btn_next)
            first_chat_bubble = self.get_first_chat_bubble_container().bubble
            click_widget(first_chat_bubble.branch_buttons.btn_back)
            first_chat_bubble = self.get_first_chat_bubble_container().bubble
            click_widget(first_chat_bubble.branch_buttons.btn_next)
            self.sleep(1.5)

            self.goto_page('chat')  # New chat
            self.text_to_speech(blocking=True,
                text="""To start a new chat, click this plus button. This will create a new chat with the exact same settings as the previous one."""
            )
            # time.sleep(0.8)
            # wait_until_finished_speaking()

            self.text_to_speech(blocking=False,
                text="""All your chats are saved in the Chats page - here - so you can continue or refer back to them."""
            )
            self.goto_page('contexts')
            self.sleep(3)
            self.goto_page('chat')
            self.sleep(1)

            # self.text_to_speech(blocking=False,
            #     text="""You can quickly cycle between chats by using these navigation buttons"""
            # )
            self.text_to_speech(blocking=False,
                text="""Any chat workflow can be saved for reuse."""
            )
            self.toggle_chat_settings(True)
            chat_save_button = chat_workflow_settings.workflow_buttons.inner_widget.btn_save_as
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
            # press escape
            pyautogui.press('esc')

        if demo_segments['Agents']:
            # pyautogui.press('esc')
            page_agents = self.goto_page('agents')
            self.text_to_speech(blocking=True,
                text="""Let's go to the Agents page, these are the workflows you interact with. They can be Agent workflows or just a single LLM, or just a snippet of code you want to run."""
            )

            click_tree_item_cell(page_agents.tree, 'Claude Code', 'name')
            self.text_to_speech(blocking=True,
                text="""Selecting an agent will open its settings, this is not tied to any chat, these settings will be the default whenever the agent is added to a workflow."""
            )
            # sleep
            self.sleep(1)
            self.text_to_speech(blocking=True,
                text="""Start a new chat with an agent by double clicking on it."""
            )
            click_tree_item_cell(page_agents.tree, 'Ayva', 'name', double=True)

            self.text_to_speech(blocking=True,
                text="""Let's open the chat settings again, here there's a field to set the system message for the agent."""
            )
            self.toggle_chat_settings(True)
            self.sleep(3)
            page_chat = self.main.main_pages.get('chat')
            chat_wf_settings = page_chat.workflow_settings
            chat_agent_settings = chat_wf_settings.member_config_widget.config_widget
            chat_agent_settings.content.setCurrentIndex(0)
            sys_msg = chat_agent_settings.pages['Messages'].sys_msg_wgt
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
            page_blocks = self.goto_page('blocks')
            click_tree_item_cell(page_blocks.tree, 'known-personality', 'name')
            # click_tree_item_cell(page_blocks.tree, 'known-personality', 'name')
            block_page_workflow_settings = page_blocks.config_widget.workflow_settings
            block_settings = block_page_workflow_settings.member_config_widget.config_widget
            click_widget(block_settings.data_wgt)
            self.sleep(3.5)
            click_widget(block_page_workflow_settings.workflow_buttons.inner_widget.btn_add)
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
            self.goto_page('chat')
            page_chat = self.goto_page('chat')  # dbl click
            self.toggle_chat_settings(True)

            chat_workflow_settings = page_chat.workflow_settings
            chat_buttons = chat_workflow_settings.workflow_buttons
            click_widget(chat_buttons.inner_widget.btn_add)

            self.text_to_speech(blocking=True,
                text="""Click this plus button to add another member. You'll have a few options. For now let's just add a blank agent."""
            )
            self.click_context_menu_item(chat_buttons.inner_widget.btn_add, item_index=1)

            dialog_window = QApplication.activeWindow()
            dialog_tree = dialog_window.tree_widget
            click_tree_item_cell(dialog_tree, 'Empty agent', 0, double=True)
            # click_widget(active_window)
            self.click_workflow_coords(chat_workflow_settings, 230, 60, double=True)
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
            try:
                click_widget(members[2].output_point)
                click_widget(members[1].input_point)
                self.sleep(7)
            except Exception as e:
                print(f'Error clicking members[2].output_point or members[1].input_point: {e}')
                raise e

            click_widget(list(chat_workflow_settings.inputs_in_view.values())[0])
            click_widget(chat_workflow_settings.workflow_buttons.inner_widget.btn_delete)

            delete_dialog = QApplication.activeWindow()
            if delete_dialog:
                # Choose QMessageBox.Yes (delete_dialog is a QMessageBox)
                yes_button = delete_dialog.buttons()[0]  # First button is typically "Yes"
                click_widget(yes_button)

            # click_widget(chat_buttons.inner_widget.btn_member_list)
            # self.text_to_speech(blocking=True,
            #     text="""Click on the members button here to show the list of members, in the order they will respond."""
            # )
            # click_widget(chat_buttons.inner_widget.btn_member_list)

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

            inputs_json_widget = chat_workflow_settings.member_config_widget.config_widget.widgets[0].widgets[1]
            click_tree_item_cell(inputs_json_widget.tree, 0, 'Target', only_hover=True)
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

            self.toggle_chat_settings(True)
            page_chat = self.main.main_pages.get('chat')
            chat_workflow_settings = page_chat.workflow_settings
            chat_buttons = chat_workflow_settings.workflow_buttons
            btn_add = chat_buttons.inner_widget.btn_add
            click_widget(btn_add)
            self.click_context_menu_item(btn_add, item_index=11)
            self.sleep(1)

            dialog_window = QApplication.activeWindow()
            dialog_tree = dialog_window.tree_widget
            click_tree_item_cell(dialog_tree, 'Empty text block', 0, double=True)

            self.click_workflow_coords(chat_workflow_settings, 330, 110, double=True)
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
                text=""""""
            )
            self.text_to_speech(blocking=True,
                text=""""""
            )
            self.text_to_speech(blocking=True,
                text=""""""
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

        if demo_segments['Projects']:
            self.text_to_speech(blocking=True,
                text="""Let's take a look at the Projects page. Projects let you organize your work into separate workspaces, each with their own files, chats, and block mappings."""
            )
            page_projects = self.goto_page('projects')
            self.sleep(2)

            self.text_to_speech(blocking=False,
                text="""You'll notice there's already an Application project here. This is a special project that points to the actual running source code of Agent Pilot itself."""
            )
            click_tree_item_cell(page_projects.tree, 'Application', 'name')
            self.sleep(2)

            self.text_to_speech(blocking=True,
                text="""If you're running from source, the Application project watches for changes to Python files in the source directory and automatically syncs them to the database. This is how Agent Pilot keeps its modules up to date as you edit them."""
            )
            self.sleep(2)

            self.text_to_speech(blocking=True,
                text="""Let's create a new project to see how it works."""
            )
            click_widget(page_projects.tree_buttons.inner_widget.btn_add)
            self.sleep(0.5)
            type_text('My Demo Project')
            pyautogui.press('enter')
            self.sleep(1.5)

            self.text_to_speech(blocking=True,
                text="""At the top you can set the project's working directory using this file picker. The file tree below will show all the files in that directory, giving you a quick overview of the project structure."""
            )
            self.sleep(2)

            project_bottom_tabs = page_projects.config_widget.widgets[2]

            self.text_to_speech(blocking=False,
                text="""Down here we have tabs for Chat and Block Maps. Let's look at the Chat tab first."""
            )
            self.goto_page('Chat', project_bottom_tabs)
            self.sleep(1)

            self.text_to_speech(blocking=True,
                text="""Each project has its own set of chat contexts, separate from the main chat. You can create tasks and conversations scoped to this project, keeping everything organized."""
            )
            self.sleep(2)

            self.text_to_speech(blocking=False,
                text="""Now let's check out Block Maps."""
            )
            self.goto_page('Block Maps', project_bottom_tabs)
            self.sleep(1)

            self.text_to_speech(blocking=True,
                text="""Block Maps let you map blocks to file paths within your project. Each row links a block from your collection to a specific file. When you click the Bake button, the content of each block is written to its mapped file on disk. This is a powerful way to keep your project files in sync with your block collection."""
            )
            bake_btn = project_bottom_tabs.pages['Block Maps'].bake_btn
            hover_widget(bake_btn)
            self.sleep(3)

        time.sleep(2)
        self.main.test_running = False
