# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import copy_metadata, collect_submodules, collect_data_files, collect_dynamic_libs

datas = copy_metadata('readchar') + \
    copy_metadata('jupyter_client') + \
    copy_metadata("jupyter_core") + \
    copy_metadata("traitlets") + \
    copy_metadata("ipykernel") + \
    copy_metadata("html2image")

# Collect data files from litellm
datas.extend(collect_data_files('litellm'))
datas.extend(collect_data_files('debugpy'))
datas.extend(collect_data_files('ipykernel'))
datas.extend(collect_data_files('jupyter_core'))
datas.extend(collect_data_files('yaspin'))
datas.extend(collect_data_files('html2image'))

binaries = collect_dynamic_libs('kiwisolver')

a = Analysis(
    ['src/__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'jupyter_core',
        'jupyter_client',
        'jupyter_client.provisioning.local_provisioner',
        'traitlets',
        'ipykernel',
        'blessed',
        'inquirer',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_agg'
        'tiktoken_ext',
        'tiktoken_ext.openai_public',
        'readchar',
        'kiwisolver',
        'html2image',
        'shortuuid',
        'langchain_community.chat_models.litellm',
        'langchain_community.agent_toolkits',
        'langchain_community.agent_toolkits.json',
        'langchain_community.agent_toolkits.json.base',
        'langchain_community.agent_toolkits.openapi',
        'langchain_community.agent_toolkits.openapi.base',
        'langchain_community.agent_toolkits.powerbi',
        'langchain_community.agent_toolkits.powerbi.base',
        'langchain_community.agent_toolkits.powerbi.chat_base',
        'langchain_community.agent_toolkits.spark_sql',
        'langchain_community.agent_toolkits.spark_sql.base',
        'langchain_community.agent_toolkits.sql',
        'langchain_community.agent_toolkits.sql.base',
        'langchain_community.chat_message_histories.astradb',
        'langchain_community.chat_message_histories.cassandra',
        'langchain_community.chat_message_histories.cosmos_db',
        'langchain_community.chat_message_histories.dynamodb',
        'langchain_community.chat_message_histories.elasticsearch',
        'langchain_community.chat_message_histories.file',
        'langchain_community.chat_message_histories.filestore',
        'langchain_community.chat_message_histories.in_memory',
        'langchain_community.chat_message_histories.momento',
        'langchain_community.chat_message_histories.mongodb',
        'langchain_community.chat_message_histories.neo4j',
        'langchain_community.chat_message_histories.postgres',
        'langchain_community.chat_message_histories.redis',
        'langchain_community.chat_message_histories.rocksetdb',
        'langchain_community.chat_message_histories.singlestoredb',
        'langchain_community.chat_message_histories.sql',
        'langchain_community.chat_message_histories.streamlit',
        'langchain_community.chat_message_histories.tidb',
        'langchain_community.chat_message_histories.upstash_redis',
        'langchain_community.chat_message_histories.xata',
        'langchain_community.chat_message_histories.zep'
	],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# Thanks to @mruderman for this solution to exclude libraries
# & thanks to @Sang-Buster for adding more libraries

excluded_libs = ['libstdc++.so', 'iris_dri.so', 'swrast_dri.so', 'libssl.so', 'libcrypto.so']
a.binaries = [(pkg, src, typ) for pkg, src, typ in a.binaries
              if not any(lib in src for lib in excluded_libs)]
a.datas = [d for d in a.datas if not d[0].endswith('.env')]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='__main__',
    icon='icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)