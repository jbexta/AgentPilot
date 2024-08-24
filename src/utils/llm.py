# import asyncio
# import time
# from concurrent.futures import ThreadPoolExecutor
#
# import litellm
# from litellm import acompletion
#
# from src.utils.helpers import network_connected
#
#
# # async def get_chat_response(messages, sys_msg=None, stream=True, model_obj=None, tools=None):
# #     model, model_config = model_obj or ('mistral/mistral-large-latest', {})
# #
# #     push_messages = [{'role': msg['role'], 'content': msg['content']} for msg in messages]
# #     ex = None
# #     for i in range(5):
# #         try:
# #             if sys_msg is not None:
# #                 push_messages.insert(0, {"role": "system", "content": sys_msg})
# #
# #             kwargs = dict(
# #                 model=model,
# #                 messages=push_messages,
# #                 stream=stream,
# #                 request_timeout=100,
# #                 **(model_config or {}),
# #             )
# #             if tools:
# #                 kwargs['tools'] = tools
# #                 kwargs['tool_choice'] = "auto"
# #
# #             return await acompletion(**kwargs)  # await acompletion(**kwargs)
# #         except Exception as e:
# #             if not network_connected():
# #                 ex = ConnectionError('No network connection.')
# #                 break
# #             ex = e
# #             await asyncio.sleep(0.3 * i)
# #     raise ex
#
#
# async def get_scalar_async(prompt, single_line=False, num_lines=0, model_obj=None):
#     if single_line:
#         num_lines = 1
#
#     if num_lines <= 0:
#         response = await get_chat_response([{'role': 'user', 'content': prompt}], '', stream=False, model_obj=model_obj)
#         output = response.choices[0]['message']['content']
#     else:
#         response_stream = await get_chat_response([{'role': 'user', 'content': prompt}], '', stream=True, model_obj=model_obj)
#         output = ''
#         line_count = 0
#         async for resp in response_stream:
#             if 'delta' in resp.choices[0]:
#                 delta = resp.choices[0].get('delta', {})
#                 chunk = delta.get('content', '')
#             else:
#                 chunk = resp.choices[0].get('text', '')
#
#             if '\n' in chunk:
#                 chunk = chunk.split('\n')[0]
#                 output += chunk
#                 line_count += 1
#                 if line_count >= num_lines:
#                     break
#                 output += chunk.split('\n')[1]
#             else:
#                 output += chunk
#     return output
#
#
# def get_scalar(prompt, single_line=False, num_lines=0, model_obj=None):
#     loop = asyncio.get_event_loop()
#     result = loop.run_until_complete(get_scalar_async(prompt, single_line, num_lines, model_obj))
#     return result
#
#
# def gen_embedding(text, model="text-embedding-ada-002"):
#     raise NotImplementedError()
#     # ex = None
#     # for i in range(5):
#     #     try:
#     #         response = openai.Embedding.create(input=[text], model=model)  # litellm.embedding(model=model, input=[text])  #
#     #         return response["data"][0]["embedding"]
#     #     except Exception as e:
#     #         ex = e
#     #         time.sleep(0.5 * i)
#     # raise ex
