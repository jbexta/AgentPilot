import json


def convert_to_openai_messages(messages):
    new_messages = []
    try:
        for message in messages:
            if 'message' in message:
                new_message = {
                    "role": message["role"],
                    "content": message["message"]
                }
            else:
                new_message = {
                    "role": message["role"],
                    "content": message["content"]
                }

            if "message" in message:
                new_message["content"] = message["message"]

            if "code" in message:
                new_message["function_call"] = {
                    "name": "execute",
                    "arguments": json.dumps({
                        "language": message["language"],
                        "code": message["code"]
                    }),
                    # parsed_arguments isn't actually an OpenAI thing, it's an OI thing.
                    # but it's soo useful! we use it to render messages to text_llms
                    "parsed_arguments": {
                        "language": message["language"],
                        "code": message["code"]
                    }
                }

            new_messages.append(new_message)

            if "output" in message:
                output = message["output"]

                new_messages.append({
                    "role": "function",
                    "name": "execute",
                    "content": output
                })
    except Exception as e:
        print("Error in convert_to_openai_messages", e)
        print("Message:", message)
        raise e
    return new_messages
