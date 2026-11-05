# -*- mode: python ; coding: utf-8 -*-
import glob
import os
import platform

from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT, BUNDLE
from PyInstaller.utils.hooks import copy_metadata, collect_data_files

datas = []

json_dir = 'src/utils/baked'
if os.path.exists(json_dir):
    datas.append((json_dir, 'utils/baked'))
for plugin_baked_dir in glob.glob('src/plugins/*/baked'):
    datas.append((plugin_baked_dir, os.path.relpath(plugin_baked_dir, 'src')))

if os.path.exists('src/utils/models.json'):
    datas.append(('src/utils/models.json', 'utils'))

datas.append(('src/utils/resources.rcc', 'utils'))
datas.append(('src/utils/lang', 'utils/lang'))

datas += copy_metadata('jupyter_client')
datas += copy_metadata('jupyter_core')
datas += copy_metadata('traitlets')
datas += copy_metadata('ipykernel')

datas += collect_data_files('litellm')
datas += collect_data_files('debugpy')
datas += collect_data_files('ipykernel')
datas += collect_data_files('jupyter_core')

a = Analysis(
    ['src/__main__.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'jupyter_core',
        'jupyter_client',
        'jupyter_client.provisioning.local_provisioner',
        'traitlets',
        'ipykernel',
        'tiktoken_ext',
        'tiktoken_ext.openai_public',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# Thanks to @mruderman for this solution to exclude libraries
# & thanks to @Sang-Buster for adding more libraries

excluded_libs = ['libstdc++.so', 'iris_dri.so', 'swrast_dri.so']  # , 'libssl.so', 'libcrypto.so']
a.binaries = [(pkg, src, typ) for pkg, src, typ in a.binaries
              if not any(lib in src for lib in excluded_libs)]
a.datas = [d for d in a.datas if not d[0].endswith('.env')]

pyz = PYZ(a.pure)

exe_args = {
    'debug': False,
    'strip': False,
    'upx': True,
    'console': True if platform.system() == 'Windows' else False,
    'name': 'AgentPilot',
}
if platform.system() == 'Darwin':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        **exe_args
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        name='AgentPilot',
    )

    app = BUNDLE(
        coll,
        name='AgentPilot.app',
        icon='icon.icns',
        bundle_identifier='com.pilotworks.agentpilot',
        info_plist={
            'NSHighResolutionCapable': 'True',
        },
    )

else:
    if platform.system() == 'Windows':
        exe_args['icon'] = 'icon.ico'

    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        bootloader_ignore_signals=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        **exe_args
    )