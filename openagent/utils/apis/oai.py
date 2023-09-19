import time
import openai
import tiktoken
from utils import logs, api

api_config = api.apis['openai']
openai.api_key = api_config['priv_key']


def get_function_call_response(messages, sys_msg=None, stream=True, model='gpt-3.5-turbo'):  # 4'):  #
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
                temperature=0.01,
                functions=[
                    {
                        "name": "get_current_weather",
                        "description": "Get the current weather in a given location",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "The city and state, e.g. San Francisco, CA",
                                },
                                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                            },
                            "required": ["location"],
                        },
                    }
                ],
                function_call="auto",
            )  # , presence_penalty=0.4, frequency_penalty=-1.8)
            initial_prompt = '\n\n'.join([f"{msg['role']}: {msg['content']}" for msg in push_messages])
            return cc, initial_prompt
        except openai.error.APIError as e:
            ex = e
            time.sleep(0.5 * i)
        except Exception as e:
            ex = e
            time.sleep(0.3 * i)
    raise ex


def get_chat_response(messages, sys_msg=None, stream=True, model='gpt-3.5-turbo'):  # 4'):  #
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
                temperature=0.01
            )  # , presence_penalty=0.4, frequency_penalty=-1.8)
            initial_prompt = '\n\n'.join([f"{msg['role']}: {msg['content']}" for msg in push_messages])
            return cc, initial_prompt
        except openai.error.APIError as e:
            ex = e
            time.sleep(0.5 * i)
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
            return openai.Completion.create(model="text-davinci-003", prompt=prompt, stream=stream, max_tokens=max_tokens)
        except openai.error.APIError as e:
            ex = e
            time.sleep(0.5 * i)
        except Exception as e:
            ex = e
            time.sleep(0.3 * i)
    raise ex


def gen_embedding(text, model="text-embedding-ada-002"):
    ex = None
    for i in range(5):
        try:
            response = openai.Embedding.create(input=[text], model=model)
            return response["data"][0]["embedding"]
        except Exception as e:
            ex = e
            time.sleep(0.5 * i)
    raise ex
