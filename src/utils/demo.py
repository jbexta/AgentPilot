# import pyautogui
#
# from src.utils.helpers import convert_to_safe_case
#
#
#
# # def click_tree_item_at_index(self, tree_widget, index):
# #     # If tree has a header, it is included in the index
# #     first_item_rect = tree_widget.visualRect(tree_widget.model().index(index, 0))
# #     center = first_item_rect.center()
# #     global_center = tree_widget.mapToGlobal(center)
# #     self.click_coords(global_center.x(), global_center.y(), double=True)
#
# def run_demo(main):
#     demo_segments = {
#         'Reset': True,
#         'Models': True,
#         'Chat': True,
#         'Agents': True,
#     }
#
#     if demo_segments['Models']:
#         page_settings = main.goto_page('Settings')
#         page_models = main.goto_page('Models', page_settings)
#         click_tree_item_cell(page_models.tree, 6, 'api_key')
#
#     if demo_segments['Chat']:
#         page_chat = main.goto_page('Chat')
#         chat_icon = page_chat.top_bar.profile_pic_label
#         click_widget(chat_icon)
#         chat_workflow_settings = page_chat.workflow_settings
#         # assert chat_workflow_settings.isVisible()
#
#         chat_agent_settings = chat_workflow_settings.member_config_widget.agent_settings
#         page_chat_wf_chat = main.goto_page('Chat', chat_agent_settings)
#         agent_model_combo = page_chat_wf_chat.pages['Messages'].model
#         cb_x, cb_y = get_widget_coords(agent_model_combo)
#
#     #     pyautogui.moveTo(cb_x, cb_y, duration=0.3)
#     #     QTest.qWait(500)
#     #     # close the combo box
#     #     # agent_model_combo.close()
#     #
#     #     message_input = self.main.message_text
#     #     self.click_widget(message_input)
#     #     self.type_text('Hello world')
#     #
#     #     send_button = self.main.send_button
#     #     self.click_widget(send_button)
#     #
#     #     while self.main.page_chat.workflow.responding:
#     #         print('Waiting for response...')
#     #         QTest.qWait(100)
#     #
#     #     first_chat_bubble_container = self.get_first_chat_bubble_container()  # page_chat.message_collection.chat_bubbles[0]
#     #     first_chat_bubble = first_chat_bubble_container.bubble
#     #     self.click_widget(first_chat_bubble)
#     #
#     #     pyautogui.press('end')
#     #     self.type_text('!!!!!!!')
#     #
#     #     resend_button = getattr(first_chat_bubble_container, 'btn_resend', None)
#     #     if resend_button:
#     #         self.click_widget(resend_button)
#     #
#     #     while self.main.page_chat.workflow.responding:
#     #         print('Waiting for response...')
#     #         QTest.qWait(100)
#     #
#     #     first_chat_bubble_container = self.get_first_chat_bubble_container()
#     #     first_chat_bubble = first_chat_bubble_container.bubble
#     #
#     #     self.hover_widget(first_chat_bubble)
#     #     branch_btn_back = first_chat_bubble.branch_buttons.btn_back
#     #     branch_btn_next = first_chat_bubble.branch_buttons.btn_next
#     #     self.click_widget(branch_btn_back)
#     #     self.click_widget(branch_btn_next)
#     #     self.click_widget(branch_btn_back)
#     #     self.click_widget(branch_btn_next)
#     #     QTest.qWait(500)
#     #
#     #     self.goto_page('Chat')  # New chat
#     #     QTest.qWait(800)
#     #
#     #     self.goto_page('Contexts')
#     #     QTest.qWait(800)
#     #     self.goto_page('Chat')  # New chat
#     #
#     #     chat_save_button = chat_workflow_settings.workflow_buttons.btn_save_as
#     #     self.click_widget(chat_save_button)
#     #
#     # if demo_segments['Agents']:
#     #     page_agents = self.goto_page('Agents')
#
#     # QTest.qWait(1000)
