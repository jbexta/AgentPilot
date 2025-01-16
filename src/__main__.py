import os
os.environ['LITELLM_LOG'] = 'ERROR'

from src.gui.main import launch
import logging
# import os
#
# # os.environ['QT_DEBUG_PLUGINS'] = '1'
# logging.basicConfig(level=logging.DEBUG)

if __name__ == '__main__':
    launch()
