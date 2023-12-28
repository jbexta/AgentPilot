from agentpilot.gui import GUI
import faulthandler
faulthandler.enable()

def main():
    app = GUI()
    app.run()


if __name__ == '__main__':
    main()
