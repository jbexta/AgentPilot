from agentpilot.utils import sql


def get_embedding(text):
    from agentpilot.utils.apis import llm
    clean_text = text.lower().strip()
    found_embedding = sql.get_results('SELECT id, embedding FROM embeddings WHERE original_text = ?', (clean_text,), return_type='dict')

    # print('EMBEDDED: ', clean_text)
    if not found_embedding:
        try:
            gen_em = llm.gen_embedding(clean_text)
            str_embedding = ','.join([str(x) for x in gen_em])
            sql.execute('INSERT INTO embeddings (original_text, embedding) VALUES (?, ?)', (clean_text, str_embedding))
            # get last inserted for sqlite
            found_embedding = sql.get_results('SELECT id, embedding FROM embeddings WHERE original_text = ?', (clean_text,), return_type='dict')
        except Exception as e:
            print(e)
            return None, None

    # first item in found_embedding dict using efficient method
    embedding = next(iter(found_embedding.items()))
    # if not embedding:
    #     return None, None
    # else:
    return embedding


def string_embeddings_to_array(embedding_str):
    return [float(x) for x in embedding_str.split(',')]


def array_embeddings_to_string(embeddings):
    if not embeddings: return ''
    return ','.join([str(x) for x in embeddings])
