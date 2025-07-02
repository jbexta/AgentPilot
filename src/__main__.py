import os
from gui.main import launch
os.environ['LITELLM_LOG'] = 'ERROR'

if __name__ == '__main__':
    launch()
