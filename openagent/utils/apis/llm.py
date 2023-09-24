import time
import openai
from utils import logs, api, retrieval


# import litellm

# api_config = api.apis['openai']
# openai.api_key = api_config['priv_key']


# def has_any_llm_api():
#     apis = ['openai']
#     return api_config['priv_key'] is not None

# def set_llm_api_keys():
#     for api_name, api_config in api.apis:
#         if api_name == 'openai':
#             litellm.openai_key = api_config['priv_key']


def get_function_call_response(messages, sys_msg=None, functions=None, stream=True, model='gpt-3.5-turbo'):  # 4'):  #
    if functions is None: functions = []
    push_messages = [{'role': msg['role'], 'content': msg['content']} for msg in messages]
    ex = None
    for i in range(5):
        try:
            if sys_msg is not None: push_messages.insert(0, {"role": "system", "content": sys_msg})
            cc = openai.ChatCompletion.create(
                model=model,
                messages=push_messages,
                stream=stream,
                temperature=0.01,
                functions=functions,
                function_call="auto",
            )  # , presence_penalty=0.4, frequency_penalty=-1.8)
            initial_prompt = '\n\n'.join([f"{msg['role']}: {msg['content']}" for msg in push_messages])
            return cc, initial_prompt
        # except openai.error.APIError as e:
        #     ex = e
        #     time.sleep(0.5 * i)
        except Exception as e:
            ex = e
            time.sleep(0.3 * i)
    raise ex


def get_chat_response(messages, sys_msg=None, stream=True, model='gpt-3.5-turbo', temperature=0.05):  # 4'):  #
    # try with backoff
    push_messages = [{'role': msg['role'], 'content': msg['content']} for msg in messages]
    ex = None
    for i in range(5):
        try:
            if sys_msg is not None: push_messages.insert(0, {"role": "system", "content": sys_msg})
            cc = openai.ChatCompletion.create(
                model=model,
                messages=push_messages,
                stream=stream,
                temperature=temperature,
            )  # , presence_penalty=0.4, frequency_penalty=-1.8)
            initial_prompt = '\n\n'.join([f"{msg['role']}: {msg['content']}" for msg in push_messages])
            return cc, initial_prompt
        # except openai.error.APIError as e:  # todo change exceptions for litellm
        #     ex = e
        #     time.sleep(0.5 * i)
        except Exception as e:
            ex = e
            time.sleep(0.3 * i)
    raise ex


def get_scalar(prompt, single_line=False, num_lines=0, is_integer=False, model='gpt-3.5-turbo'):
    if single_line: num_lines = 1
    if num_lines <= 0:
        response, initial_prompt = get_chat_response([], prompt, stream=False, model=model)
        output = response.choices[0]['message']['content']
    else:
        response_stream, initial_prompt = get_chat_response([], prompt, stream=True, model=model)
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
    logs.insert_log('PROMPT', f'{initial_prompt}\n\n--- RESPONSE ---\n\n{output}', print_=False)
    return output


def get_completion(prompt, max_tokens=500, stream=True):
    # try with backoff
    # print("FELLBACK TO COMPLETION")
    ex = None
    for i in range(5):
        try:
            return openai.Completion(model="text-davinci-003", prompt=prompt, stream=stream, max_tokens=max_tokens)
        # except openai.error.APIError as e:
        #     ex = e
        #     time.sleep(0.5 * i)
        except Exception as e:
            ex = e
            time.sleep(0.3 * i)
    raise ex


def gen_embedding(text, model="text-embedding-ada-002"):
    ex = None
    for i in range(5):
        try:
            response = openai.Embedding.create(input=[text], model=model)  # litellm.embedding(model=model, input=[text])  #
            return response["data"][0]["embedding"]
        except Exception as e:
            ex = e
            time.sleep(0.5 * i)
    raise ex
