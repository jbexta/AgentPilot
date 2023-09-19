from utils import sql
from utils.apis import oai


def get_embedding(text):
    clean_text = text.lower().strip()
    found_embedding = sql.get_scalar('SELECT embedding FROM embeddings WHERE original_text = ?', (clean_text,))
    if not found_embedding:
        gen_embedding = oai.gen_embedding(clean_text)
        str_embedding = ','.join([str(x) for x in gen_embedding])
        sql.execute('INSERT INTO embeddings (original_text, embedding) VALUES (?, ?)', (clean_text, str_embedding))
        found_embedding = str_embedding

    return string_embeddings_to_array(found_embedding)


def string_embeddings_to_array(embedding_str):
    return [float(x) for x in embedding_str.split(',')]


def array_embeddings_to_string(embeddings):
    if not embeddings: return ''
    return ','.join([str(x) for x in embeddings])
