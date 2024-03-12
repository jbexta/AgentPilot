import os
import shutil

from src.utils import sql
from packaging import version


class SQLUpgrade:
    def __init__(self):
        pass

    def v0_2_0(self):
        sql.execute("""
            CREATE TABLE "apis_new" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "client_key"	TEXT NOT NULL DEFAULT '',
                "priv_key"	TEXT NOT NULL DEFAULT '',
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        sql.execute("""
            INSERT INTO apis_new (id, name, client_key, priv_key, config) VALUES
                (1, 'FakeYou', '', '', '{}'),
                (2, 'Uberduck', '', '', '{}'),
                (3, 'ElevenLabs', '', '', '{}'),
                (4, 'OpenAI', '', '$OPENAI_API_KEY', '{}'),
                (5, 'AWSPolly', '', '', '{}'),
                (8, 'Replicate', '', '', '{"litellm_prefix": "replicate"}'),
                (10, 'Azure OpenAI', '', '', '{"litellm_prefix": "azure"}'),
                (11, 'Huggingface', '', '', '{"litellm_prefix": "huggingface"}'),
                (12, 'Ollama', '', '', '{"litellm_prefix": "ollama"}'),
                (13, 'VertexAI Google', '', '', '{}'),
                (14, 'PaLM API Google', '', '', '{"litellm_prefix": "palm"}'),
                (15, 'Anthropic', '', '$ANTHROPIC_API_KEY', '{}'),
                (16, 'AWS Sagemaker', '', '', '{"litellm_prefix": "sagemaker"}'),
                (17, 'AWS Bedrock', '', '', '{"litellm_prefix": "bedrock"}'),
                (18, 'Anyscale', '', '', '{"litellm_prefix": "anyscale"}'),
                (19, 'Perplexity AI', '', '$PERPLEXITYAI_API_KEY', '{"litellm_prefix": "perplexity"}'),
                (20, 'VLLM', '', '', '{"litellm_prefix": "vllm"}'),
                (21, 'DeepInfra', '', '', '{"litellm_prefix": "deepinfra"}'),
                (22, 'AI21', '', '', '{}'),
                (23, 'NLP Cloud', '', '', '{}'),
                (25, 'Cohere', '', '', '{}'),
                (26, 'Together AI', '', '', '{"litellm_prefix": "together_ai"}'),
                (27, 'Aleph Alpha', '', '', '{}'),
                (28, 'Baseten', '', '', '{"litellm_prefix": "baseten"}'),
                (29, 'OpenRouter', '', '', '{"litellm_prefix": "openrouter"}'),
                (30, 'Custom API Server', '', '', '{}'),
                (31, 'Petals', '', '', '{"litellm_prefix": "petals"}'),
                (32, 'Mistral', '', '$MISTRAL_API_KEY', '{"litellm_prefix": "mistral"}'),
                (33, 'Groq', '', '', '{"litellm_prefix": "groq"}'),
                (34, 'Cloudflare', '', '', '{"litellm_prefix": "cloudflare"}'),
                (35, 'Voyage', '', '', '{"litellm_prefix": "voyage"}')""")
        sql.execute("""
            DROP TABLE apis""")
        sql.execute("""
            ALTER TABLE apis_new RENAME TO apis""")

        sql.execute("""
        CREATE TABLE "models_new" (
            "id"	INTEGER,
            "api_id"	INTEGER NOT NULL DEFAULT 0,
            "name"	TEXT NOT NULL DEFAULT '',
            "kind"	TEXT NOT NULL DEFAULT 'CHAT',
            "config"	TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY("id" AUTOINCREMENT)
        )""")
        sql.execute("""
        INSERT INTO models_new (id, api_id, name, config) VALUES
            (1, 4, "GPT 3.5 Turbo", "{""model_name"": ""gpt-3.5-turbo""}"),
            (2, 4, "GPT 3.5 Turbo 16k", "{""model_name"": ""gpt-3.5-turbo-16k""}"),
            (3, 4, "GPT 3.5 Turbo (F)", "{""model_name"": ""gpt-3.5-turbo-1106""}"),
            (4, 4, "GPT 3.5 Turbo 16k (F)", "{""model_name"": ""gpt-3.5-turbo-16k-0613""}"),
            (5, 4, "GPT 4", "{""model_name"": ""gpt-4""}"),
            (6, 4, "GPT 4 32k", "{""model_name"": ""gpt-4-32k""}"),
            (7, 4, "GPT 4 (F)", "{""model_name"": ""gpt-4-0613""}"),
            (8, 4, "GPT 4 32k (F)", "{""model_name"": ""gpt-4-32k-0613""}"),
            (9, 8, "llama-2-70b-chat:2796ee9483c3fd7aa2e171d38f4ca12251a30609463dcfd4cd76703f22e96cdf", "{""model_name"": ""llama-2-70b-chat:2796ee9483c3fd7aa2e171d38f4ca12251a30609463dcfd4cd76703f22e96cdf""}"),
            (10, 8, "a16z-infra/llama-2-13b-chat:2a7f981751ec7fdf87b5b91ad4db53683a98082e9ff7bfd12c8cd5ea85980a52", "{""model_name"": ""a16z-infra/llama-2-13b-chat:2a7f981751ec7fdf87b5b91ad4db53683a98082e9ff7bfd12c8cd5ea85980a52""}"),
            (11, 8, "vicuna-13b:6282abe6a492de4145d7bb601023762212f9ddbbe78278bd6771c8b3b2f2a13b", "{""model_name"": ""vicuna-13b:6282abe6a492de4145d7bb601023762212f9ddbbe78278bd6771c8b3b2f2a13b""}"),
            (12, 8, "daanelson/flan-t5-large:ce962b3f6792a57074a601d3979db5839697add2e4e02696b3ced4c022d4767f", "{""model_name"": ""daanelson/flan-t5-large:ce962b3f6792a57074a601d3979db5839697add2e4e02696b3ced4c022d4767f""}"),
            (13, 8, "custom-llm-version-id", "{""model_name"": ""custom-llm-version-id""}"),
            (14, 8, "deployments/ishaan-jaff/ishaan-mistral", "{""model_name"": ""deployments/ishaan-jaff/ishaan-mistral""}"),
            (15, 10, "azure/gpt-4", "{""model_name"": ""gpt-4""}"),
            (16, 10, "azure/gpt-4-0314", "{""model_name"": ""gpt-4-0314""}"),
            (17, 10, "azure/gpt-4-0613", "{""model_name"": ""gpt-4-0613""}"),
            (18, 10, "azure/gpt-4-32k", "{""model_name"": ""gpt-4-32k""}"),
            (19, 10, "azure/gpt-4-32k-0314", "{""model_name"": ""gpt-4-32k-0314""}"),
            (20, 10, "azure/gpt-4-32k-0613", "{""model_name"": ""gpt-4-32k-0613""}"),
            (21, 10, "azure/gpt-3.5-turbo", "{""model_name"": ""gpt-3.5-turbo""}"),
            (22, 10, "azure/gpt-3.5-turbo-0301", "{""model_name"": ""gpt-3.5-turbo-0301""}"),
            (23, 10, "azure/gpt-3.5-turbo-0613", "{""model_name"": ""gpt-3.5-turbo-0613""}"),
            (24, 10, "azure/gpt-3.5-turbo-16k", "{""model_name"": ""gpt-3.5-turbo-16k""}"),
            (25, 10, "azure/gpt-3.5-turbo-16k-0613", "{""model_name"": ""gpt-3.5-turbo-16k-0613""}"),
            (26, 11, "mistralai/Mistral-7B-Instruct-v0.1", "{""model_name"": ""mistralai/Mistral-7B-Instruct-v0.1""}"),
            (27, 11, "meta-llama/Llama-2-7b-chat", "{""model_name"": ""meta-llama/Llama-2-7b-chat""}"),
            (28, 11, "tiiuae/falcon-7b-instruct", "{""model_name"": ""tiiuae/falcon-7b-instruct""}"),
            (29, 11, "mosaicml/mpt-7b-chat", "{""model_name"": ""mosaicml/mpt-7b-chat""}"),
            (30, 11, "codellama/CodeLlama-34b-Instruct-hf", "{""model_name"": ""codellama/CodeLlama-34b-Instruct-hf""}"),
            (31, 11, "WizardLM/WizardCoder-Python-34B-V1.0", "{""model_name"": ""WizardLM/WizardCoder-Python-34B-V1.0""}"),
            (32, 11, "Phind/Phind-CodeLlama-34B-v2", "{""model_name"": ""Phind/Phind-CodeLlama-34B-v2""}"),
            (33, 12, "Mistral", "{""model_name"": ""mistral""}"),
            (34, 12, "Llama2 7B", "{""model_name"": ""llama2""}"),
            (35, 12, "Llama2 13B", "{""model_name"": ""llama2:13b""}"),
            (36, 12, "Llama2 70B", "{""model_name"": ""llama2:70b""}"),
            (37, 12, "Llama2 Uncensored", "{""model_name"": ""llama2-uncensored""}"),
            (38, 12, "Code Llama", "{""model_name"": ""codellama""}"),
            (39, 12, "Llama2 Uncensored", "{""model_name"": ""llama2-uncensored""}"),
            (40, 12, "Orca Mini", "{""model_name"": ""orca-mini""}"),
            (41, 12, "Vicuna", "{""model_name"": ""vicuna""}"),
            (42, 12, "Nous-Hermes", "{""model_name"": ""nous-hermes""}"),
            (43, 12, "Nous-Hermes 13B", "{""model_name"": ""nous-hermes:13b""}"),
            (44, 12, "Wizard Vicuna Uncensored", "{""model_name"": ""wizard-vicuna""}"),
            (45, 13, "chat-bison-32k", "{""model_name"": ""chat-bison-32k""}"),
            (46, 13, "chat-bison", "{""model_name"": ""chat-bison""}"),
            (47, 13, "chat-bison@001", "{""model_name"": ""chat-bison@001""}"),
            (48, 13, "codechat-bison", "{""model_name"": ""codechat-bison""}"),
            (49, 13, "codechat-bison-32k", "{""model_name"": ""codechat-bison-32k""}"),
            (50, 13, "codechat-bison@001", "{""model_name"": ""codechat-bison@001""}"),
            (51, 13, "text-bison", "{""model_name"": ""text-bison""}"),
            (52, 13, "text-bison@001", "{""model_name"": ""text-bison@001""}"),
            (53, 13, "code-bison", "{""model_name"": ""code-bison""}"),
            (54, 13, "code-bison@001", "{""model_name"": ""code-bison@001""}"),
            (55, 13, "code-gecko@001", "{""model_name"": ""code-gecko@001""}"),
            (56, 13, "code-gecko@latest", "{""model_name"": ""code-gecko@latest""}"),
            (57, 14, "palm/chat-bison", "{""model_name"": ""chat-bison""}"),
            (58, 15, "claude-instant-1", "{""model_name"": ""claude-instant-1""}"),
            (59, 15, "claude-instant-1.2", "{""model_name"": ""claude-instant-1.2""}"),
            (60, 15, "claude-2", "{""model_name"": ""claude-2""}"),
            (61, 16, "jumpstart-dft-meta-textgeneration-llama-2-7b", "{""model_name"": ""jumpstart-dft-meta-textgeneration-llama-2-7b""}"),
            (62, 16, "your-endpoint", "{""model_name"": ""your-endpoint""}"),
            (63, 17, "anthropic.claude-v2", "{""model_name"": ""anthropic.claude-v2""}"),
            (64, 17, "anthropic.claude-instant-v1", "{""model_name"": ""anthropic.claude-instant-v1""}"),
            (65, 17, "anthropic.claude-v1", "{""model_name"": ""anthropic.claude-v1""}"),
            (66, 17, "amazon.titan-text-lite-v1", "{""model_name"": ""amazon.titan-text-lite-v1""}"),
            (67, 17, "amazon.titan-text-express-v1", "{""model_name"": ""amazon.titan-text-express-v1""}"),
            (68, 17, "cohere.command-text-v14", "{""model_name"": ""cohere.command-text-v14""}"),
            (69, 17, "ai21.j2-mid-v1", "{""model_name"": ""ai21.j2-mid-v1""}"),
            (70, 17, "ai21.j2-ultra-v1", "{""model_name"": ""ai21.j2-ultra-v1""}"),
            (71, 17, "meta.llama2-13b-chat-v1", "{""model_name"": ""meta.llama2-13b-chat-v1""}"),
            (72, 18, "meta-llama/Llama-2-7b-chat-hf", "{""model_name"": ""meta-llama/Llama-2-7b-chat-hf""}"),
            (73, 18, "meta-llama/Llama-2-13b-chat-hf", "{""model_name"": ""meta-llama/Llama-2-13b-chat-hf""}"),
            (74, 18, "meta-llama/Llama-2-70b-chat-hf", "{""model_name"": ""meta-llama/Llama-2-70b-chat-hf""}"),
            (75, 18, "mistralai/Mistral-7B-Instruct-v0.1", "{""model_name"": ""mistralai/Mistral-7B-Instruct-v0.1""}"),
            (76, 18, "codellama/CodeLlama-34b-Instruct-hf", "{""model_name"": ""codellama/CodeLlama-34b-Instruct-hf""}"),
            (77, 19, "codellama-34b-instruct", "{""model_name"": ""codellama-34b-instruct""}"),
            (78, 19, "llama-2-13b-chat", "{""model_name"": ""llama-2-13b-chat""}"),
            (79, 19, "llama-2-70b-chat", "{""model_name"": ""llama-2-70b-chat""}"),
            (80, 19, "mistral-7b-instruct", "{""model_name"": ""mistral-7b-instruct""}"),
            (82, 20, "meta-llama/Llama-2-7b", "{""model_name"": ""meta-llama/Llama-2-7b""}"),
            (83, 20, "tiiuae/falcon-7b-instruct", "{""model_name"": ""tiiuae/falcon-7b-instruct""}"),
            (84, 20, "mosaicml/mpt-7b-chat", "{""model_name"": ""mosaicml/mpt-7b-chat""}"),
            (85, 20, "codellama/CodeLlama-34b-Instruct-hf", "{""model_name"": ""codellama/CodeLlama-34b-Instruct-hf""}"),
            (86, 20, "WizardLM/WizardCoder-Python-34B-V1.0", "{""model_name"": ""WizardLM/WizardCoder-Python-34B-V1.0""}"),
            (87, 20, "Phind/Phind-CodeLlama-34B-v2", "{""model_name"": ""Phind/Phind-CodeLlama-34B-v2""}"),
            (88, 21, "meta-llama/Llama-2-70b-chat-hf", "{""model_name"": ""meta-llama/Llama-2-70b-chat-hf""}"),
            (89, 21, "meta-llama/Llama-2-7b-chat-hf", "{""model_name"": ""meta-llama/Llama-2-7b-chat-hf""}"),
            (90, 21, "meta-llama/Llama-2-13b-chat-hf", "{""model_name"": ""meta-llama/Llama-2-13b-chat-hf""}"),
            (91, 21, "codellama/CodeLlama-34b-Instruct-hf", "{""model_name"": ""codellama/CodeLlama-34b-Instruct-hf""}"),
            (92, 21, "mistralai/Mistral-7B-Instruct-v0.1", "{""model_name"": ""mistralai/Mistral-7B-Instruct-v0.1""}"),
            (93, 21, "jondurbin/airoboros-l2-70b-gpt4-1.4.1", "{""model_name"": ""jondurbin/airoboros-l2-70b-gpt4-1.4.1""}"),
            (94, 22, "j2-light", "{""model_name"": ""j2-light""}"),
            (95, 22, "j2-mid", "{""model_name"": ""j2-mid""}"),
            (96, 22, "j2-ultra", "{""model_name"": ""j2-ultra""}"),
            (97, 23, "dolphin", "{""model_name"": ""dolphin""}"),
            (98, 23, "chatdolphin", "{""model_name"": ""chatdolphin""}"),
            (99, 25, "command", "{""model_name"": ""command""}"),
            (100, 25, "command-light", "{""model_name"": ""command-light""}"),
            (101, 25, "command-medium", "{""model_name"": ""command-medium""}"),
            (102, 25, "command-medium-beta", "{""model_name"": ""command-medium-beta""}"),
            (103, 25, "command-xlarge-beta", "{""model_name"": ""command-xlarge-beta""}"),
            (104, 25, "command-nightly", "{""model_name"": ""command-nightly""}"),
            (105, 26, "togethercomputer/llama-2-70b-chat", "{""model_name"": ""togethercomputer/llama-2-70b-chat""}"),
            (106, 26, "togethercomputer/llama-2-70b", "{""model_name"": ""togethercomputer/llama-2-70b""}"),
            (107, 26, "togethercomputer/LLaMA-2-7B-32K", "{""model_name"": ""togethercomputer/LLaMA-2-7B-32K""}"),
            (108, 26, "togethercomputer/Llama-2-7B-32K-Instruct", "{""model_name"": ""togethercomputer/Llama-2-7B-32K-Instruct""}"),
            (109, 26, "togethercomputer/llama-2-7b", "{""model_name"": ""togethercomputer/llama-2-7b""}"),
            (110, 26, "togethercomputer/falcon-40b-instruct", "{""model_name"": ""togethercomputer/falcon-40b-instruct""}"),
            (111, 26, "togethercomputer/falcon-7b-instruct", "{""model_name"": ""togethercomputer/falcon-7b-instruct""}"),
            (112, 26, "togethercomputer/alpaca-7b", "{""model_name"": ""togethercomputer/alpaca-7b""}"),
            (113, 26, "HuggingFaceH4/starchat-alpha", "{""model_name"": ""HuggingFaceH4/starchat-alpha""}"),
            (114, 26, "togethercomputer/CodeLlama-34b", "{""model_name"": ""togethercomputer/CodeLlama-34b""}"),
            (115, 26, "togethercomputer/CodeLlama-34b-Instruct", "{""model_name"": ""togethercomputer/CodeLlama-34b-Instruct""}"),
            (116, 26, "togethercomputer/CodeLlama-34b-Python", "{""model_name"": ""togethercomputer/CodeLlama-34b-Python""}"),
            (117, 26, "defog/sqlcoder", "{""model_name"": ""defog/sqlcoder""}"),
            (118, 26, "NumbersStation/nsql-llama-2-7B", "{""model_name"": ""NumbersStation/nsql-llama-2-7B""}"),
            (119, 26, "WizardLM/WizardCoder-15B-V1.0", "{""model_name"": ""WizardLM/WizardCoder-15B-V1.0""}"),
            (120, 26, "WizardLM/WizardCoder-Python-34B-V1.0", "{""model_name"": ""WizardLM/WizardCoder-Python-34B-V1.0""}"),
            (121, 26, "NousResearch/Nous-Hermes-Llama2-13b", "{""model_name"": ""NousResearch/Nous-Hermes-Llama2-13b""}"),
            (122, 26, "Austism/chronos-hermes-13b", "{""model_name"": ""Austism/chronos-hermes-13b""}"),
            (123, 26, "upstage/SOLAR-0-70b-16bit", "{""model_name"": ""upstage/SOLAR-0-70b-16bit""}"),
            (124, 26, "WizardLM/WizardLM-70B-V1.0", "{""model_name"": ""WizardLM/WizardLM-70B-V1.0""}"),
            (125, 27, "luminous-base", "{""model_name"": ""luminous-base""}"),
            (126, 27, "luminous-base-control", "{""model_name"": ""luminous-base-control""}"),
            (127, 27, "luminous-extended", "{""model_name"": ""luminous-extended""}"),
            (128, 27, "luminous-extended-control", "{""model_name"": ""luminous-extended-control""}"),
            (129, 27, "luminous-supreme", "{""model_name"": ""luminous-supreme""}"),
            (130, 27, "luminous-supreme-control", "{""model_name"": ""luminous-supreme-control""}"),
            (131, 28, "Falcon 7B", "{""model_name"": ""qvv0xeq""}"),
            (132, 28, "Wizard LM", "{""model_name"": ""q841o8w""}"),
            (133, 28, "MPT 7B Base", "{""model_name"": ""31dxrj3""}"),
            (134, 29, "openai/gpt-3.5-turbo", "{""model_name"": ""openai/gpt-3.5-turbo""}"),
            (135, 29, "openai/gpt-3.5-turbo-16k", "{""model_name"": ""openai/gpt-3.5-turbo-16k""}"),
            (136, 29, "openai/gpt-4", "{""model_name"": ""openai/gpt-4""}"),
            (137, 29, "openai/gpt-4-32k", "{""model_name"": ""openai/gpt-4-32k""}"),
            (138, 29, "anthropic/claude-2", "{""model_name"": ""anthropic/claude-2""}"),
            (139, 29, "anthropic/claude-instant-v1", "{""model_name"": ""anthropic/claude-instant-v1""}"),
            (140, 29, "google/palm-2-chat-bison", "{""model_name"": ""google/palm-2-chat-bison""}"),
            (141, 29, "google/palm-2-codechat-bison", "{""model_name"": ""google/palm-2-codechat-bison""}"),
            (142, 29, "meta-llama/llama-2-13b-chat", "{""model_name"": ""meta-llama/llama-2-13b-chat""}"),
            (143, 29, "meta-llama/llama-2-70b-chat", "{""model_name"": ""meta-llama/llama-2-70b-chat""}"),
            (146, 4, "GPT 4 Turbo", "{""model_name"": ""gpt-4-1106-preview""}"),
            (153, 19, "mixtral-8x7b-instruct", "{""model_name"": ""mixtral-8x7b-instruct""}"),
            (158, 4, "GPT 4 Vision", "{""model_name"": ""gpt-4-vision-preview""}"),
            (162, 19, "sonar-small-chat", "{""model_name"": ""sonar-small-chat""}"),
            (163, 19, "sonar-medium-chat", "{""model_name"": ""sonar-medium-chat""}"),
            (164, 19, "sonar-small-online", "{""model_name"": ""sonar-small-online""}"),
            (165, 19, "sonar-medium-online", "{""model_name"": ""sonar-medium-online""}"),
            (166, 13, "gemini-pro", "{""model_name"": ""gemini-pro""}"),
            (167, 13, "gemini-1.5-pro", "{""model_name"": ""gemini-1.5-pro""}"),
            (168, 13, "gemini-pro-vision", "{""model_name"": ""gemini-pro-vision""}"),
            (169, 13, "gemini-1.5-pro-vision", "{""model_name"": ""gemini-1.5-pro-vision""}"),
            (173, 32, "mistral-tiny", "{""model_name"": ""mistral-tiny""}"),
            (174, 32, "mistral-small", "{""model_name"": ""mistral-small""}"),
            (175, 32, "mistral-medium", "{""model_name"": ""mistral-medium""}"),
            (176, 32, "mistral-large-latest", "{""model_name"": ""mistral-large-latest""}"),
            (177, 15, "claude-3-opus", "{""model_name"": ""claude-3-opus-20240229""}"),
            (178, 15, "claude-3-sonnet", "{""model_name"": ""claude-3-sonnet-20240229""}"),
            (179, 15, "claude-2.1", "{""model_name"": ""claude-2.1""}"),
            (180, 16, "jumpstart-dft-meta-textgeneration-llama-2-7b-f", "{""model_name"": ""jumpstart-dft-meta-textgeneration-llama-2-7b-f""}"),
            (181, 16, "jumpstart-dft-meta-textgeneration-llama-2-13b", "{""model_name"": ""jumpstart-dft-meta-textgeneration-llama-2-13b""}"),
            (182, 16, "jumpstart-dft-meta-textgeneration-llama-2-13b-f", "{""model_name"": ""jumpstart-dft-meta-textgeneration-llama-2-13b-f""}"),
            (183, 16, "jumpstart-dft-meta-textgeneration-llama-2-70b", "{""model_name"": ""jumpstart-dft-meta-textgeneration-llama-2-70b""}"),
            (184, 16, "jumpstart-dft-meta-textgeneration-llama-2-70b-b-f", "{""model_name"": ""jumpstart-dft-meta-textgeneration-llama-2-70b-b-f""}"),
            (185, 17, "anthropic.claude-3-sonnet-20240229-v1:0", "{""model_name"": ""anthropic.claude-3-sonnet-20240229-v1:0""}"),
            (186, 17, "anthropic.claude-v2:1", "{""model_name"": ""anthropic.claude-v2:1""}"),
            (187, 17, "meta.llama2-70b-chat-v1", "{""model_name"": ""meta.llama2-70b-chat-v1""}"),
            (188, 17, "mistral.mistral-7b-instruct-v0:2", "{""model_name"": ""mistral.mistral-7b-instruct-v0:2""}"),
            (189, 17, "mistral.mixtral-8x7b-instruct-v0:1", "{""model_name"": ""mistral.mixtral-8x7b-instruct-v0:1""}"),
            (190, 33, "llama2-70b-4096", "{""model_name"": ""llama2-70b-4096""}"),
            (191, 33, "mixtral-8x7b-32768", "{""model_name"": ""mixtral-8x7b-32768""}"),
            (192, 34, "mistral/mistral-tiny", "{""model_name"": ""mistral/mistral-tiny""}"),
            (193, 34, "mistral/mistral-small", "{""model_name"": ""mistral/mistral-small""}"),
            (194, 34, "mistral/mistral-medium", "{""model_name"": ""mistral/mistral-medium""}"),
            (195, 34, "codellama/codellama-medium", "{""model_name"": ""codellama/codellama-medium""}"),
            (196, 35, "voyage-01", "{""model_name"": ""voyage-01""}"),
            (197, 35, "voyage-lite-01", "{""model_name"": ""voyage-lite-01""}"),
            (198, 35, "voyage-lite-01-instruct", "{""model_name"": ""voyage-lite-01-instruct""}"),
            (199, 31, "petals-team/StableBeluga2", "{""model_name"": ""petals-team/StableBeluga2""}"),
            (200, 31, "huggyllama/llama-65b", "{""model_name"": ""huggyllama/llama-65b""}"),
            (201, 4, "GPT 4 Turbo (Unlazy?)", "{""model_name"": ""gpt-4-0125-preview""}")
        """)
        sql.execute("""
            DROP TABLE models""")
        sql.execute("""
            ALTER TABLE models_new RENAME TO models""")

        sql.execute("""
            CREATE TABLE "agents_new" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL DEFAULT '' UNIQUE,
                "desc"	TEXT NOT NULL DEFAULT '',
                "config"	TEXT NOT NULL DEFAULT '{}',
                "folder_id"	INTEGER DEFAULT NULL,
                "ordr"	INTEGER DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        # set display markdown to true
        sql.execute("""
            INSERT INTO agents_new (id, name, desc, config, folder_id)
            SELECT 
                id, 
                name, 
                desc, 
                json_object(
                    'info.avatar_path', json_extract(config, '$.general.avatar_path'),
                    'info.name', json_extract(config, '$.general.name'),
                    'info.use_plugin', json_extract(config, '$.general.use_plugin'),
                    'chat.model', '$.context.model',
                    'chat.display_markdown', true,
                    'chat.sys_msg', json_extract(config, '$.context.sys_msg'),
                    'chat.max_messages', json_extract(config, '$.context.max_messages'),
                    'chat.max_turns', json_extract(config, '$.context.max_turns'),
                    'chat.user_msg', json_extract(config, '$.context.user_msg'),
                    'group.hide_responses', json_extract(config, '$.group.hide_responses'),
                    'group.output_placeholder', json_extract(config, '$.group.output_context_placeholder'),
                    'group.show_members_as_user_role', true,
                    'group.on_multiple_inputs', 'Merged user message',
                    'group.member_description', '',
                    'voice.current_id', json_extract(config, '$.voice.current_id')
                ),
                NULL
            FROM agents""")
        sql.execute("""
            DROP TABLE agents""")
        sql.execute("""
            ALTER TABLE agents_new RENAME TO agents""")

        sql.execute("""
            CREATE TABLE "blocks_new" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "config"	TEXT NOT NULL DEFAULT '{}',
                "folder_id"	INTEGER DEFAULT NULL,
                "ordr"	INTEGER DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        sql.execute("""
            INSERT INTO blocks_new (id, name, config, folder_id)
            SELECT 
                id, 
                name, 
                json_object('data', `text`),
                NULL
            FROM blocks""")
        sql.execute("""
            DROP TABLE blocks""")
        sql.execute("""
            ALTER TABLE blocks_new RENAME TO blocks""")

        sql.execute("""
        CREATE TABLE "folders" (
            "id"	INTEGER,
            "name"	TEXT NOT NULL,
            "parent_id"	INTEGER,
            "type"	TEXT,
            "config"	TEXT NOT NULL DEFAULT '{}',
            "ordr"	INTEGER DEFAULT 0,
            PRIMARY KEY("id")
        );
        """)

        sql.execute("""
            CREATE TABLE "roles_new" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "config"	TEXT NOT NULL DEFAULT '{}',
                "schema"	TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        # sql.execute("""
        #     INSERT INTO roles_new (id, name, config)
        #     SELECT
        #         id,
        #         name,
        #         config
        #     FROM roles""")
        sql.execute("""
            DROP TABLE roles""")
        sql.execute("""
            ALTER TABLE roles_new RENAME TO roles""")
        # sql.execute("""
        # DELETE FROM roles;
        # """)
        sql.execute("""
        INSERT INTO roles (name, config) VALUES
            ('user', '{"bubble_bg_color": "#3b3b3b", "bubble_text_color": "#d1d1d1", "bubble_image_size": 25}'),
            ('assistant', '{"bubble_bg_color": "#29282b", "bubble_text_color": "#b2bbcf", "bubble_image_size": 25}'),
            ('tool', '{"bubble_bg_color": "#3b3b3b", "bubble_text_color": "#c4c4c4", "bubble_image_size": 25}'),
            ('file', '{"bubble_bg_color": "#3b3b3b", "bubble_text_color": "#c4c4c4", "bubble_image_size": 25}'),
            ('code', '{"bubble_bg_color": "#3b3b3b", "bubble_text_color": "#c4c4c4", "bubble_image_size": 25}'),
            ('system', '{"bubble_bg_color": "#3b3b3b", "bubble_text_color": "#c4c4c4", "bubble_image_size": 25}')
        """)

        # todo get old config and insert into new config
        app_config = """{"system.language": "English", "system.dev_mode": false, "system.always_on_top": true, "system.auto_title": true, "system.auto_title_model": "claude-3-sonnet-20240229", "system.auto_title_prompt": "Write only a brief and concise title for a chat that begins with the following message:\\n\\n```{user_msg}```", "system.voice_input_method": "None", "display.primary_color": "#262326", "display.secondary_color": "#3f3a3f", "display.text_color": "#c1b5d5", "display.text_font": "", "display.text_size": 15, "display.show_bubble_name": "In Group", "display.show_bubble_avatar": "In Group", "display.bubble_avatar_position": "Top", "display.bubble_spacing": 7}"""
        sql.execute("""
        INSERT INTO settings (field, value) VALUES
            ('app_config', ?)""", (app_config,))

        default_agent = """{"info.name": "Assistant", "info.avatar_path": "", "info.use_plugin": "", "chat.model": "mistral/mistral-medium", "chat.display_markdown": true, "chat.sys_msg": "", "chat.max_messages": 15, "chat.max_turns": 10, "chat.on_consecutive_response": "REPLACE", "chat.user_msg": "", "chat.preload.data": "[]", "group.hide_responses": false, "group.output_placeholder": "", "group.on_multiple_inputs": "Merged user message", "group.show_members_as_user_role": true, "files.data": "[]", "tools.data": "[]"}"""
        sql.execute("""
        UPDATE settings SET field = 'default_agent', value = ? WHERE field = 'global_config'""", (default_agent,))

        sql.execute("""
        CREATE TABLE "tools" (
            "id"	INTEGER,
            "uuid"	TEXT NOT NULL UNIQUE,
            "name"	TEXT NOT NULL DEFAULT '' UNIQUE,
            "config"	TEXT NOT NULL DEFAULT '{}',
            "folder_id"	INTEGER DEFAULT NULL,
            PRIMARY KEY("id" AUTOINCREMENT)
        )""")
        sql.execute("""
        DROP TABLE IF EXISTS functions""")

        sql.execute("""
        CREATE TABLE "contexts_new" (
            "id"	INTEGER,
            "parent_id"	INTEGER,
            "branch_msg_id"	INTEGER DEFAULT NULL,
            "summary"	TEXT NOT NULL DEFAULT '',
            "active"	INTEGER NOT NULL DEFAULT 1,
            "folder_id"	INTEGER DEFAULT NULL,
            "ordr"	INTEGER DEFAULT 0,
            PRIMARY KEY("id" AUTOINCREMENT)
        )""")
        sql.execute("""
        INSERT INTO contexts_new (id, parent_id, branch_msg_id, summary, active)
        SELECT
            id,
            parent_id,
            branch_msg_id,
            summary,
            active
        FROM contexts""")
        sql.execute("""
        DROP TABLE contexts""")
        sql.execute("""
        ALTER TABLE contexts_new RENAME TO contexts""")

        sql.execute("""
            UPDATE settings SET value = '0.2.0' WHERE field = 'app_version'""")
        sql.execute("""
            VACUUM""")
        # Add new tables
        #  - Sandboxes (drop first)
        #  - Folders

        # Add new table fields:
        #  - contexts.folder_id

        return "0.2.0"

    def v0_1_0(self):
        # Update global agent config
        glob_conf = """{"general.name": "Assistant", "general.avatar_path": "", "general.use_plugin": "", "context.model": "gpt-3.5-turbo", "context.sys_msg": "", "context.max_messages": 10, "context.max_turns": 5, "context.auto_title": true, "context.display_markdown": true, "context.on_consecutive_response": "REPLACE", "context.user_msg": "", "actions.enable_actions": false, "actions.source_directory": ".", "actions.replace_busy_action_on_new": false, "actions.use_function_calling": true, "actions.use_validator": false, "actions.code_auto_run_seconds": "5", "group.hide_responses": false, "group.output_context_placeholder": "", "group.on_multiple_inputs": "Use system message", "voice.current_id": 0}"""
        sql.execute("""
            UPDATE settings SET `value` = ? WHERE field = 'global_config'""", (glob_conf,))
            
        # Add key "general.name" to all agents config dict str
        sql.execute("""
            UPDATE agents SET config = json_insert(config, '$."general.name"', name)""")
        # Add new tables
        sql.execute("""
            CREATE TABLE "roles" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        sql.execute("""
            INSERT INTO roles (id, name, config) VALUES
                (1, 'user', '{"display.bubble_bg_color": "#3b3b3b", "display.bubble_text_color": "#d1d1d1", "display.bubble_image_size": "25"}'),
                (2, 'assistant', '{"display.bubble_bg_color": "#29282b", "display.bubble_text_color": "#b2bbcf", "display.bubble_image_size": "25"}'),
                (3, 'code', '{"display.bubble_bg_color": "#151515", "display.bubble_text_color": "#999999", "display.bubble_image_size": "0"}'),
                (4, 'note', '{"display.bubble_bg_color": "#1f1e21", "display.bubble_text_color": "#d1d1d1", "display.bubble_image_size": "0"}'),
                (6, 'output', '{"display.bubble_bg_color": "#111111", "display.bubble_text_color": "#ffffff", "display.bubble_image_size": "0"}')
            """)

        sql.execute("""
            CREATE TABLE "functions" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL DEFAULT '' UNIQUE,
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        sql.execute("""
            CREATE TABLE "contexts_members" (
                "id"	INTEGER,
                "context_id"	INTEGER NOT NULL,
                "agent_id"	INTEGER NOT NULL,
                "agent_config"	TEXT NOT NULL DEFAULT '{}',
                "ordr"	INTEGER NOT NULL DEFAULT 0,
                "loc_x"	INTEGER NOT NULL DEFAULT 37,
                "loc_y"	INTEGER NOT NULL DEFAULT 30,
                "del"	INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT),
                FOREIGN KEY("context_id") REFERENCES "contexts"("id") ON DELETE CASCADE
            )""")
        sql.execute("""
            CREATE TABLE "contexts_members_inputs" (
                "id"	INTEGER,
                "member_id"	INTEGER NOT NULL,
                "input_member_id"	INTEGER,
                "type"	INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT),
                FOREIGN KEY("member_id") REFERENCES "contexts_members"("id") ON DELETE CASCADE,
                FOREIGN KEY("input_member_id") REFERENCES "contexts_members"("id") ON DELETE CASCADE
            )""")

        # Set all contexts agent_id to the first agent if the agent_id = 0
        first_agent_id = sql.get_scalar("SELECT id FROM agents LIMIT 1")
        sql.execute("""
            UPDATE contexts SET agent_id = ? WHERE agent_id = 0""", (first_agent_id,))

        # Insert data from old "contexts" table to new "contexts_members" table
        sql.execute("""
            INSERT INTO contexts_members (context_id, agent_id, agent_config, loc_x, loc_y) 
            SELECT c.id, c.agent_id, a.config, 37, 30
            FROM contexts c
            LEFT JOIN agents a ON c.agent_id = a.id
            WHERE c.agent_id != 0""")

        sql.execute("""
            CREATE TABLE "contexts_messages_new" (
                "id"	INTEGER,
                "unix"	INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS TYPE_NAME)),
                "context_id"	INTEGER,
                "member_id"	INTEGER,
                "role"	TEXT,
                "msg"	TEXT,
                "embedding_id"	INTEGER,
                "log"	TEXT NOT NULL DEFAULT '',
                "del"	INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY("member_id") REFERENCES "contexts_members"("id") ON DELETE CASCADE,
                PRIMARY KEY("id" AUTOINCREMENT),
                FOREIGN KEY("context_id") REFERENCES "contexts"("id") ON DELETE CASCADE
            )""")
        sql.execute("""
            INSERT INTO contexts_messages_new (id, unix, context_id, member_id, role, msg, embedding_id, log, del)
            SELECT 
                cms.id, 
                cms.unix, 
                cms.context_id, 
                CASE WHEN cms.role = 'assistant' THEN cm.id ELSE NULL END, 
                cms.role, 
                cms.msg, 
                cms.embedding_id, 
                '', 
                cms.del
            FROM contexts_messages cms
            LEFT JOIN contexts_members cm 
                ON cms.context_id = cm.context_id""")
        sql.execute("""
            DROP TABLE contexts_messages""")
        sql.execute("""
            ALTER TABLE contexts_messages_new RENAME TO contexts_messages""")

        sql.execute("""
            ALTER TABLE contexts DROP COLUMN 'agent_id'""")
        sql.execute("""
            ALTER TABLE contexts ADD COLUMN "active" INTEGER DEFAULT 1""")

        current_openai_key = sql.get_scalar("SELECT priv_key FROM apis WHERE name = 'OpenAI'")
        sql.execute("""
            DELETE FROM apis""")
        sql.execute("""
            INSERT INTO apis (id, name, client_key, priv_key) VALUES 
                (1, 'FakeYou', '', ''),
                (2, 'Uberduck', '', ''),
                (3, 'ElevenLabs', '', ''),
                (4, 'OpenAI', '', ?),
                (5, 'AWSPolly', '', ''),
                (8, 'Replicate', '', ''),
                (10, 'Azure OpenAI', '', ''),
                (11, 'Huggingface', '', ''),
                (12, 'Ollama', '', ''),
                (13, 'VertexAI Google', '', ''),
                (14, 'PaLM API Google', '', ''),
                (15, 'Anthropic', '', ''),
                (16, 'AWS Sagemaker', '', ''),
                (17, 'AWS Bedrock', '', ''),
                (18, 'Anyscale', '', ''),
                (19, 'Perplexity AI', '', ''),
                (20, 'VLLM', '', ''),
                (21, 'DeepInfra', '', ''),
                (22, 'AI21', '', ''),
                (23, 'NLP Cloud', '', ''),
                (25, 'Cohere', '', ''),
                (26, 'Together AI', '', ''),
                (27, 'Aleph Alpha', '', ''),
                (28, 'Baseten', '', ''),
                (29, 'OpenRouter', '', ''),
                (30, 'Custom API Server', '', ''),
                (31, 'Petals', '', '')""",
            (current_openai_key,))

        sql.execute("""
            ALTER TABLE models DROP COLUMN 'name'""")
        sql.execute("""
            ALTER TABLE models ADD COLUMN "alias" TEXT DEFAULT ''""")
        sql.execute("""
            ALTER TABLE models ADD COLUMN "type" TEXT DEFAULT 'chat'""")
        sql.execute("""
            ALTER TABLE models ADD COLUMN "model_config" TEXT DEFAULT 'chat'""")
        sql.execute("""
            DELETE FROM models""")
        sql.execute("""
            INSERT INTO models (id, api_id, alias, model_name, model_config) VALUES 
                (1, 4, 'GPT 3.5 Turbo', 'gpt-3.5-turbo', '{}'), 
                (2, 4, 'GPT 3.5 Turbo 16k', 'gpt-3.5-turbo-16k', '{}'), 
                (3, 4, 'GPT 3.5 Turbo (F)', 'gpt-3.5-turbo-0613', '{}'), 
                (4, 4, 'GPT 3.5 Turbo 16k (F)', 'gpt-3.5-turbo-16k-0613', '{}'), 
                (5, 4, 'GPT 4', 'gpt-4', '{}'), 
                (6, 4, 'GPT 4 32k', 'gpt-4-32k', '{}'), 
                (7, 4, 'GPT 4 (F)', 'gpt-4-0613', '{}'), 
                (8, 4, 'GPT 32k (F)', 'gpt-4-32k-0613', '{}'), 
                (9, 8, 'replicate/llama-2-70b-chat:2796ee9483c3fd7aa2e171d38f4ca12251a30609463dcfd4cd76703f22e96cdf', 'replicate/llama-2-70b-chat:2796ee9483c3fd7aa2e171d38f4ca12251a30609463dcfd4cd76703f22e96cdf', '{}'), 
                (10, 8, 'replicate/a16z-infra/llama-2-13b-chat:2a7f981751ec7fdf87b5b91ad4db53683a98082e9ff7bfd12c8cd5ea85980a52', 'replicate/a16z-infra/llama-2-13b-chat:2a7f981751ec7fdf87b5b91ad4db53683a98082e9ff7bfd12c8cd5ea85980a52', '{}'), 
                (11, 8, 'replicate/vicuna-13b:6282abe6a492de4145d7bb601023762212f9ddbbe78278bd6771c8b3b2f2a13b', 'replicate/vicuna-13b:6282abe6a492de4145d7bb601023762212f9ddbbe78278bd6771c8b3b2f2a13b', '{}'), 
                (12, 8, 'replicate/daanelson/flan-t5-large:ce962b3f6792a57074a601d3979db5839697add2e4e02696b3ced4c022d4767f', 'replicate/daanelson/flan-t5-large:ce962b3f6792a57074a601d3979db5839697add2e4e02696b3ced4c022d4767f', '{}'), 
                (13, 8, 'replicate/custom-llm-version-id', 'replicate/custom-llm-version-id', '{}'), 
                (14, 8, 'replicate/deployments/ishaan-jaff/ishaan-mistral', 'replicate/deployments/ishaan-jaff/ishaan-mistral', '{}'), 
                (15, 10, 'azure/gpt-4', 'azure/gpt-4', '{}'), 
                (16, 10, 'azure/gpt-4-0314', 'azure/gpt-4-0314', '{}'), 
                (17, 10, 'azure/gpt-4-0613', 'azure/gpt-4-0613', '{}'), 
                (18, 10, 'azure/gpt-4-32k', 'azure/gpt-4-32k', '{}'), 
                (19, 10, 'azure/gpt-4-32k-0314', 'azure/gpt-4-32k-0314', '{}'), 
                (20, 10, 'azure/gpt-4-32k-0613', 'azure/gpt-4-32k-0613', '{}'), 
                (21, 10, 'azure/gpt-3.5-turbo', 'azure/gpt-3.5-turbo', '{}'), 
                (22, 10, 'azure/gpt-3.5-turbo-0301', 'azure/gpt-3.5-turbo-0301', '{}'), 
                (23, 10, 'azure/gpt-3.5-turbo-0613', 'azure/gpt-3.5-turbo-0613', '{}'), 
                (24, 10, 'azure/gpt-3.5-turbo-16k', 'azure/gpt-3.5-turbo-16k', '{}'), 
                (25, 10, 'azure/gpt-3.5-turbo-16k-0613', 'azure/gpt-3.5-turbo-16k-0613', '{}'), 
                (26, 11, 'huggingface/mistralai/Mistral-7B-Instruct-v0.1', 'huggingface/mistralai/Mistral-7B-Instruct-v0.1', '{}'), 
                (27, 11, 'huggingface/meta-llama/Llama-2-7b-chat', 'huggingface/meta-llama/Llama-2-7b-chat', '{}'), 
                (28, 11, 'huggingface/tiiuae/falcon-7b-instruct', 'huggingface/tiiuae/falcon-7b-instruct', '{}'), 
                (29, 11, 'huggingface/mosaicml/mpt-7b-chat', 'huggingface/mosaicml/mpt-7b-chat', '{}'), 
                (30, 11, 'huggingface/codellama/CodeLlama-34b-Instruct-hf', 'huggingface/codellama/CodeLlama-34b-Instruct-hf', '{}'), 
                (31, 11, 'huggingface/WizardLM/WizardCoder-Python-34B-V1.0', 'huggingface/WizardLM/WizardCoder-Python-34B-V1.0', '{}'), 
                (32, 11, 'huggingface/Phind/Phind-CodeLlama-34B-v2', 'huggingface/Phind/Phind-CodeLlama-34B-v2', '{}'), 
                (33, 12, 'Mistral', 'ollama/mistral', '{}'), 
                (34, 12, 'Llama2 7B', 'ollama/llama2', '{}'), 
                (35, 12, 'Llama2 13B', 'ollama/llama2:13b', '{}'), 
                (36, 12, 'Llama2 70B', 'ollama/llama2:70b', '{}'), 
                (37, 12, 'Llama2 Uncensored', 'ollama/llama2-uncensored', '{}'), 
                (38, 12, 'Code Llama', 'ollama/codellama', '{}'), 
                (39, 12, 'Llama2 Uncensored', 'ollama/llama2-uncensored', '{}'), 
                (40, 12, 'Orca Mini', 'ollama/orca-mini', '{}'), 
                (41, 12, 'Vicuna', 'ollama/vicuna', '{}'), 
                (42, 12, 'Nous-Hermes', 'ollama/nous-hermes', '{}'), 
                (43, 12, 'Nous-Hermes 13B', 'ollama/nous-hermes:13b', '{}'), 
                (44, 12, 'Wizard Vicuna Uncensored', 'ollama/wizard-vicuna', '{}'), 
                (45, 13, 'chat-bison-32k', 'chat-bison-32k', '{}'), 
                (46, 13, 'chat-bison', 'chat-bison', '{}'), 
                (47, 13, 'chat-bison@001', 'chat-bison@001', '{}'), 
                (48, 13, 'codechat-bison', 'codechat-bison', '{}'), 
                (49, 13, 'codechat-bison-32k', 'codechat-bison-32k', '{}'), 
                (50, 13, 'codechat-bison@001', 'codechat-bison@001', '{}'), 
                (51, 13, 'text-bison', 'text-bison', '{}'), 
                (52, 13, 'text-bison@001', 'text-bison@001', '{}'), 
                (53, 13, 'code-bison', 'code-bison', '{}'), 
                (54, 13, 'code-bison@001', 'code-bison@001', '{}'), 
                (55, 13, 'code-gecko@001', 'code-gecko@001', '{}'), 
                (56, 13, 'code-gecko@latest', 'code-gecko@latest', '{}'), 
                (57, 14, 'palm/chat-bison', 'palm/chat-bison', '{}'), 
                (58, 15, 'claude-instant-1', 'claude-instant-1', '{}'), 
                (59, 15, 'claude-instant-1.2', 'claude-instant-1.2', '{}'), 
                (60, 15, 'claude-2', 'claude-2', '{}'), 
                (61, 16, 'sagemaker/jumpstart-dft-meta-textgeneration-llama-2-7b', 'sagemaker/jumpstart-dft-meta-textgeneration-llama-2-7b', '{}'), 
                (62, 16, 'sagemaker/your-endpoint', 'sagemaker/your-endpoint', '{}'), 
                (63, 17, 'anthropic.claude-v2', 'anthropic.claude-v2', '{}'), 
                (64, 17, 'anthropic.claude-instant-v1', 'anthropic.claude-instant-v1', '{}'), 
                (65, 17, 'anthropic.claude-v1', 'anthropic.claude-v1', '{}'), 
                (66, 17, 'amazon.titan-text-lite-v1', 'amazon.titan-text-lite-v1', '{}'), 
                (67, 17, 'amazon.titan-text-express-v1', 'amazon.titan-text-express-v1', '{}'), 
                (68, 17, 'cohere.command-text-v14', 'cohere.command-text-v14', '{}'), 
                (69, 17, 'ai21.j2-mid-v1', 'ai21.j2-mid-v1', '{}'), 
                (70, 17, 'ai21.j2-ultra-v1', 'ai21.j2-ultra-v1', '{}'), 
                (71, 17, 'meta.llama2-13b-chat-v1', 'meta.llama2-13b-chat-v1', '{}'), 
                (72, 18, 'anyscale/meta-llama/Llama-2-7b-chat-hf', 'anyscale/meta-llama/Llama-2-7b-chat-hf', '{}'), 
                (73, 18, 'anyscale/meta-llama/Llama-2-13b-chat-hf', 'anyscale/meta-llama/Llama-2-13b-chat-hf', '{}'), 
                (74, 18, 'anyscale/meta-llama/Llama-2-70b-chat-hf', 'anyscale/meta-llama/Llama-2-70b-chat-hf', '{}'), 
                (75, 18, 'anyscale/mistralai/Mistral-7B-Instruct-v0.1', 'anyscale/mistralai/Mistral-7B-Instruct-v0.1', '{}'), 
                (76, 18, 'anyscale/codellama/CodeLlama-34b-Instruct-hf', 'anyscale/codellama/CodeLlama-34b-Instruct-hf', '{}'), 
                (77, 19, 'perplexity/codellama-34b-instruct', 'perplexity/codellama-34b-instruct', '{}'), 
                (78, 19, 'perplexity/llama-2-13b-chat', 'perplexity/llama-2-13b-chat', '{}'), 
                (79, 19, 'perplexity/llama-2-70b-chat', 'perplexity/llama-2-70b-chat', '{}'), 
                (80, 19, 'perplexity/mistral-7b-instruct', 'perplexity/mistral-7b-instruct', '{}'), 
                (81, 19, 'perplexity/replit-code-v1.5-3b', 'perplexity/replit-code-v1.5-3b', '{}'), 
                (82, 20, 'vllm/meta-llama/Llama-2-7b', 'vllm/meta-llama/Llama-2-7b', '{}'), 
                (83, 20, 'vllm/tiiuae/falcon-7b-instruct', 'vllm/tiiuae/falcon-7b-instruct', '{}'), 
                (84, 20, 'vllm/mosaicml/mpt-7b-chat', 'vllm/mosaicml/mpt-7b-chat', '{}'), 
                (85, 20, 'vllm/codellama/CodeLlama-34b-Instruct-hf', 'vllm/codellama/CodeLlama-34b-Instruct-hf', '{}'), 
                (86, 20, 'vllm/WizardLM/WizardCoder-Python-34B-V1.0', 'vllm/WizardLM/WizardCoder-Python-34B-V1.0', '{}'), 
                (87, 20, 'vllm/Phind/Phind-CodeLlama-34B-v2', 'vllm/Phind/Phind-CodeLlama-34B-v2', '{}'), 
                (88, 21, 'deepinfra/meta-llama/Llama-2-70b-chat-hf', 'deepinfra/meta-llama/Llama-2-70b-chat-hf', '{}'), 
                (89, 21, 'deepinfra/meta-llama/Llama-2-7b-chat-hf', 'deepinfra/meta-llama/Llama-2-7b-chat-hf', '{}'), 
                (90, 21, 'deepinfra/meta-llama/Llama-2-13b-chat-hf', 'deepinfra/meta-llama/Llama-2-13b-chat-hf', '{}'), 
                (91, 21, 'deepinfra/codellama/CodeLlama-34b-Instruct-hf', 'deepinfra/codellama/CodeLlama-34b-Instruct-hf', '{}'), 
                (92, 21, 'deepinfra/mistralai/Mistral-7B-Instruct-v0.1', 'deepinfra/mistralai/Mistral-7B-Instruct-v0.1', '{}'), 
                (93, 21, 'deepinfra/jondurbin/airoboros-l2-70b-gpt4-1.4.1', 'deepinfra/jondurbin/airoboros-l2-70b-gpt4-1.4.1', '{}'), 
                (94, 22, 'j2-light', 'j2-light', '{}'), 
                (95, 22, 'j2-mid', 'j2-mid', '{}'), 
                (96, 22, 'j2-ultra', 'j2-ultra', '{}'), 
                (97, 23, 'dolphin', 'dolphin', '{}'), 
                (98, 23, 'chatdolphin', 'chatdolphin', '{}'), 
                (99, 25, 'command', 'command', '{}'), 
                (100, 25, 'command-light', 'command-light', '{}'), 
                (101, 25, 'command-medium', 'command-medium', '{}'), 
                (102, 25, 'command-medium-beta', 'command-medium-beta', '{}'), 
                (103, 25, 'command-xlarge-beta', 'command-xlarge-beta', '{}'), 
                (104, 25, 'command-nightly', 'command-nightly', '{}'), 
                (105, 26, 'together_ai/togethercomputer/llama-2-70b-chat', 'together_ai/togethercomputer/llama-2-70b-chat', '{}'), 
                (106, 26, 'together_ai/togethercomputer/llama-2-70b', 'together_ai/togethercomputer/llama-2-70b', '{}'), 
                (107, 26, 'together_ai/togethercomputer/LLaMA-2-7B-32K', 'together_ai/togethercomputer/LLaMA-2-7B-32K', '{}'), 
                (108, 26, 'together_ai/togethercomputer/Llama-2-7B-32K-Instruct', 'together_ai/togethercomputer/Llama-2-7B-32K-Instruct', '{}'), 
                (109, 26, 'together_ai/togethercomputer/llama-2-7b', 'together_ai/togethercomputer/llama-2-7b', '{}'), 
                (110, 26, 'together_ai/togethercomputer/falcon-40b-instruct', 'together_ai/togethercomputer/falcon-40b-instruct', '{}'), 
                (111, 26, 'together_ai/togethercomputer/falcon-7b-instruct', 'together_ai/togethercomputer/falcon-7b-instruct', '{}'), 
                (112, 26, 'together_ai/togethercomputer/alpaca-7b', 'together_ai/togethercomputer/alpaca-7b', '{}'), 
                (113, 26, 'together_ai/HuggingFaceH4/starchat-alpha', 'together_ai/HuggingFaceH4/starchat-alpha', '{}'), 
                (114, 26, 'together_ai/togethercomputer/CodeLlama-34b', 'together_ai/togethercomputer/CodeLlama-34b', '{}'), 
                (115, 26, 'together_ai/togethercomputer/CodeLlama-34b-Instruct', 'together_ai/togethercomputer/CodeLlama-34b-Instruct', '{}'), 
                (116, 26, 'together_ai/togethercomputer/CodeLlama-34b-Python', 'together_ai/togethercomputer/CodeLlama-34b-Python', '{}'), 
                (117, 26, 'together_ai/defog/sqlcoder', 'together_ai/defog/sqlcoder', '{}'), 
                (118, 26, 'together_ai/NumbersStation/nsql-llama-2-7B', 'together_ai/NumbersStation/nsql-llama-2-7B', '{}'), 
                (119, 26, 'together_ai/WizardLM/WizardCoder-15B-V1.0', 'together_ai/WizardLM/WizardCoder-15B-V1.0', '{}'), 
                (120, 26, 'together_ai/WizardLM/WizardCoder-Python-34B-V1.0', 'together_ai/WizardLM/WizardCoder-Python-34B-V1.0', '{}'), 
                (121, 26, 'together_ai/NousResearch/Nous-Hermes-Llama2-13b', 'together_ai/NousResearch/Nous-Hermes-Llama2-13b', '{}'), 
                (122, 26, 'together_ai/Austism/chronos-hermes-13b', 'together_ai/Austism/chronos-hermes-13b', '{}'), 
                (123, 26, 'together_ai/upstage/SOLAR-0-70b-16bit', 'together_ai/upstage/SOLAR-0-70b-16bit', '{}'), 
                (124, 26, 'together_ai/WizardLM/WizardLM-70B-V1.0', 'together_ai/WizardLM/WizardLM-70B-V1.0', '{}'), 
                (125, 27, 'luminous-base', 'luminous-base', '{}'), 
                (126, 27, 'luminous-base-control', 'luminous-base-control', '{}'), 
                (127, 27, 'luminous-extended', 'luminous-extended', '{}'), 
                (128, 27, 'luminous-extended-control', 'luminous-extended-control', '{}'), 
                (129, 27, 'luminous-supreme', 'luminous-supreme', '{}'), 
                (130, 27, 'luminous-supreme-control', 'luminous-supreme-control', '{}'), 
                (131, 28, 'Falcon 7B', 'baseten/qvv0xeq', '{}'), 
                (132, 28, 'Wizard LM', 'baseten/q841o8w', '{}'), 
                (133, 28, 'MPT 7B Base', 'baseten/31dxrj3', '{}'), 
                (134, 29, 'openrouter/openai/gpt-3.5-turbo', 'openrouter/openai/gpt-3.5-turbo', '{}'), 
                (135, 29, 'openrouter/openai/gpt-3.5-turbo-16k', 'openrouter/openai/gpt-3.5-turbo-16k', '{}'), 
                (136, 29, 'openrouter/openai/gpt-4', 'openrouter/openai/gpt-4', '{}'), 
                (137, 29, 'openrouter/openai/gpt-4-32k', 'openrouter/openai/gpt-4-32k', '{}'), 
                (138, 29, 'openrouter/anthropic/claude-2', 'openrouter/anthropic/claude-2', '{}'), 
                (139, 29, 'openrouter/anthropic/claude-instant-v1', 'openrouter/anthropic/claude-instant-v1', '{}'), 
                (140, 29, 'openrouter/google/palm-2-chat-bison', 'openrouter/google/palm-2-chat-bison', '{}'), 
                (141, 29, 'openrouter/google/palm-2-codechat-bison', 'openrouter/google/palm-2-codechat-bison', '{}'), 
                (142, 29, 'openrouter/meta-llama/llama-2-13b-chat', 'openrouter/meta-llama/llama-2-13b-chat', '{}'), 
                (143, 29, 'openrouter/meta-llama/llama-2-70b-chat', 'openrouter/meta-llama/llama-2-70b-chat', '{}')
            """)

        sql.execute("""
            DELETE FROM embeddings WHERE id > 1984""")

        sql.execute("""
            UPDATE settings SET value = '0.1.0' WHERE field = 'app_version'""")

        # vacuum
        sql.execute("""
            VACUUM""")

        return '0.1.0'

    def upgrade(self, current_version):
        # make a backup of the current data.db
        db_path = sql.get_db_path()
        backup_path = db_path + '.backup_v0.1.0'

        # check if the backup file already exists
        num = 1
        while os.path.isfile(backup_path):
            backup_path = db_path + f'({str(num)}).backup_v0.1.0'
            num += 1
        shutil.copyfile(db_path, backup_path)

        try:
            if current_version < version.parse("0.1.0"):
                return self.v0_1_0()
            elif current_version < version.parse("0.2.0"):
                return self.v0_2_0()
            else:
                return str(current_version)

        except Exception as e:
            # restore the backup
            os.remove(db_path)
            shutil.copyfile(backup_path, db_path)
            raise e


upgrade_script = SQLUpgrade()
versions = ['0.0.8', '0.1.0', '0.2.0']
