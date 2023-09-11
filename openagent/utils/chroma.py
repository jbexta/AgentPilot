# import chromadb
# from chromadb.utils import embedding_functions
# from chromadb.config import Settings
# client = chromadb.Client(Settings(
#     chroma_db_impl="duckdb+parquet",
#     persist_directory="/home/jb/Documents/AI/chroma" # Optional, defaults to .chromadb/ in the current directory
# ))
#
# persist_directory = 'db'
# default_ef = embedding_functions.DefaultEmbeddingFunction()
# vectordb = chromadb..from_documents(documents=texts, embedding=embedding, persist_directory=persist_directory)