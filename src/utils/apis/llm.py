import time
import litellm


# def completion_callback(
#     kwargs,                 # kwargs to completion
#     completion_response,    # response from completion
#     start_time, end_time    # start/end time
# ):
#     try:
#         # check if it has collected an entire stream response
#         if "complete_streaming_response" in kwargs:
#             # for tracking streaming cost we pass the "messages" and the output_text to litellm.completion_cost
#             completion_response=kwargs["complete_streaming_response"]
#             input_text = kwargs["messages"]
#             output_text = completion_response["choices"][0]["message"]["content"]
#             response_cost = litellm.completion_cost(
#                 model = kwargs["model"],
#                 messages = input_text,
#                 completion=output_text
#             )
#             print("streaming response_cost", response_cost)
#     except:
#         pass
#
#
# # set callback
# litellm.success_callback = [completion_callback]


# thread_lock = threading.Lock()
# member_calls = {}  # {litellm id: member_id}
#
#
# def insert_member_call(litellm_id, member_id):
#     with thread_lock:
#         member_calls[litellm_id] = member_id
#
#
# def finish_member_call(litellm_id):
#     with thread_lock:
#         if litellm_id not in member_calls:
#             return
#         member_id = member_calls.pop(litellm_id)


# def get_function_call_response(messages, sys_msg=None, functions=None, stream=True, model='gpt-3.5-turbo'):  # 4'):  #
#     if functions is None: functions = []
#     push_messages = [{'role': msg['role'], 'content': msg['content']} for msg in messages]
#     ex = None
#     for i in range(5):
#         try:
#             if sys_msg is not None: push_messages.insert(0, {"role": "system", "content": sys_msg})
#             cc = litellm.completion(
#                 model=model,
#                 messages=push_messages,
#                 stream=stream,
#                 temperature=0.01,
#                 functions=functions,
#                 function_call="auto",
#             )  # , presence_penalty=0.4, frequency_penalty=-1.8)
#             initial_prompt = '\n\n'.join([f"{msg['role']}: {msg['content']}" for msg in push_messages])
#             return cc, initial_prompt
#         # except openai.error.APIError as e:
#         #     ex = e
#         #     time.sleep(0.5 * i)
#         except Exception as e:
#             ex = e
#             time.sleep(0.3 * i)
#     raise ex


def get_chat_response(messages, sys_msg=None, stream=True, model_obj=None, tools=None):
    model, model_config = model_obj or ('gpt-3.5-turbo', {})
    if 'temperature' in model_config:
        # if is a valid number, convert value to a float, otherwise remove it
        try:
            model_config['temperature'] = float(model_config['temperature'])
        except ValueError:
            del model_config['temperature']
    if 'custom_provider' in model_config:  # todo patch, remove next breaking version
        del model_config['custom_provider']

    # try with backoff
    push_messages = [{'role': msg['role'], 'content': msg['content']} for msg in messages]
    ex = None
    for i in range(5):
        try:
            if sys_msg is not None: push_messages.insert(0, {"role": "system", "content": sys_msg})

            accepted_keys = [
                'api_base',
            ]
            kwargs = dict(
                model='gpt-3.5-turbo-1106',  # model,
                messages=push_messages,
                stream=stream,
                request_timeout=100,
                **(model_config or {}),
            )
            if tools:
                kwargs['tools'] = tools
                kwargs['tool_choice'] = "auto"

            cc = litellm.completion(**kwargs)
            # , presence_penalty=0.4, frequency_penalty=-1.8)
            # initial_prompt = '\n\n'.join([f"{msg['role']}: {msg['content']}" for msg in push_messages])
            return cc  # , cc.logging_obj
        # except openai.error.APIError as e:  # todo change exceptions for litellm
        #     ex = e
        #     time.sleep(0.5 * i)
        except Exception as e:
            ex = e
            time.sleep(0.3 * i)
    raise ex


def get_scalar(prompt, single_line=False, num_lines=0, model_obj=None):
    if single_line:
        num_lines = 1

    if num_lines <= 0:
        # m_name, m_conf = model_obj
        # m_conf.pop('api_base', None)
        # m_conf.pop('custom_llm_provider', None)
        # new_m_obj = (m_name, m_conf)
        response = get_chat_response([], prompt, stream=False, model_obj=model_obj)
        output = response.choices[0]['message']['content']
    else:
        response_stream = get_chat_response([], prompt, stream=True, model_obj=model_obj)
        output = ''
        line_count = 0
        for resp in response_stream:
            if 'delta' in resp.choices[0]:
                delta = resp.choices[0].get('delta', {})
                chunk = delta.get('content', '')
            else:
                chunk = resp.choices[0].get('text', '')

            # if is_integer:
            #     # check if any non-numeric characters in chunk

            if '\n' in chunk:
                chunk = chunk.split('\n')[0]
                output += chunk
                line_count += 1
                if line_count >= num_lines:
                    break
                output += chunk.split('\n')[1]
            else:
                output += chunk
    # logs.insert_log('PROMPT', f'{initial_prompt}\n\n--- RESPONSE ---\n\n{output}', print_=False)
    return output


# def get_completion(prompt, max_tokens=500, stream=True):
#     # try with backoff
#     # print("FELLBACK TO COMPLETION")
#     ex = None
#     for i in range(5):
#         try:
#             s = openai.Completion(model="text-davinci-003", prompt=prompt, stream=stream, max_tokens=max_tokens)
#             for resp in s:
#                 print(resp)
#             return s
#         # except openai.error.APIError as e:
#         #     ex = e
#         #     time.sleep(0.5 * i)
#         except Exception as e:
#             ex = e
#             time.sleep(0.3 * i)
#     raise ex


def gen_embedding(text, model="text-embedding-ada-002"):
    raise NotImplementedError()
    # ex = None
    # for i in range(5):
    #     try:
    #         response = openai.Embedding.create(input=[text], model=model)  # litellm.embedding(model=model, input=[text])  #
    #         return response["data"][0]["embedding"]
    #     except Exception as e:
    #         ex = e
    #         time.sleep(0.5 * i)
    # raise ex
