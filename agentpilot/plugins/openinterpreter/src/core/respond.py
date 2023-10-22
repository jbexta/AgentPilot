from ..utils.merge_deltas import merge_deltas


def respond(interpreter, base_agent):
    """
    Yields tokens, but also adds them to interpreter.messages. TBH probably would be good to seperate those two responsibilities someday soon
    Responds until it decides not to run any more code or say anything else.
    """
    try:
        interpreter.current_deltas = {}
        messages = base_agent.context.message_history.get(llm_format=True)
        for key, chunk in interpreter._llm(messages):
            interpreter.current_deltas = merge_deltas(interpreter.current_deltas, {key: chunk})

            print(f'YIELDED: {str(key)}, {str(chunk)}  - FROM Respond')
            yield key, chunk

        # RUN CODE (if it's there) #
        if "code" in interpreter.current_deltas:
            # What code do you want to run?
            language = interpreter.current_deltas["language"]
            code = interpreter.current_deltas["code"]

            print(f'RETURNED: CONFIRM, {str((language, code))}  - FROM Respond')
            # yield 'CONFIRM', (language, code)
            # return (language, code)
            yield 'CONFIRM', (language, code)
        else:
            print(f'RETURNED: PAUSE, None  - FROM Respond')
            # yield 'PAUSE', None
            yield 'PAUSE', ''

    except Exception as e:
        print('ERROR: 895495: ' + str(e))
