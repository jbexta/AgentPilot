import os
from src.gui.main import launch
os.environ['LITELLM_LOG'] = 'ERROR'

if __name__ == '__main__':
    launch()
