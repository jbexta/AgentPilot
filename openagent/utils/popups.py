import threading
import tkinter as tk
from tkinter import ttk

# create invisible root window
# root = tk.Tk()
# root.withdraw()
# root.mainloop()

popups = []


def show_popup(message, backcolor, tick_button_func, cross_button_func):
    def popup_thread():
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        popups.append(CustomPopup(root, message, backcolor, tick_button_func, cross_button_func))
        root.mainloop()

    t = threading.Thread(target=popup_thread)
    t.start()


class CustomPopup:
    def __init__(self, root, message, backcolor, tick_button_func, cross_button_func):
        self.root = root
        self.popup = tk.Toplevel(root)
        self.popup.overrideredirect(True)  # Remove window decorations

        self.popup_width = 200
        self.popup_height = 100
        self.popup.configure(bg=backcolor)

        screen_width = self.popup.winfo_screenwidth()
        screen_height = self.popup.winfo_screenheight()

        popup_x = screen_width - self.popup_width
        popup_y = screen_height - self.popup_height

        self.popup.geometry(f"{self.popup_width}x{self.popup_height}+{popup_x}+{popup_y}")

        # Add Close Button
        self.close_button = tk.Button(self.popup, text='X', command=self.close_popup)
        self.close_button.grid(row=0, column=1, rowspan=1, columnspan=1, padx=95, sticky='n')  # Placed in row 0, column 1

        if cross_button_func is not None:
            # Add Wrong Button
            self.wrong_button = tk.Button(self.popup, text='Wrong', command=cross_button_func(self))
            self.wrong_button.grid(row=1, column=0, rowspan=1, columnspan=1, sticky='s')  # Placed in row 0, column 0

        # align centre
        self.label = tk.Label(self.popup, text=f'\n{message}\n', bg=backcolor, fg='black', font=('helvetica', 10), justify='center', anchor='center')
        # label should fill the entire popup
        self.label.grid(row=0, column=0, rowspan=1, columnspan=1, sticky='nsew')

        self.label.bind("<Button-1>", self.start_drag)
        self.label.bind("<B1-Motion>", self.drag)
        self.label.bind("<ButtonRelease-1>", self.stop_drag)

        self.popup.bind("<Button-1>", self.start_drag)
        self.popup.bind("<B1-Motion>", self.drag)
        self.popup.bind("<ButtonRelease-1>", self.stop_drag)

    def submit_wrong_task(self):
        self.clo
        pass

    def start_drag(self, event):
        self.x = event.x
        self.y = event.y

    def drag(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        new_x = self.popup.winfo_x() + deltax
        new_y = self.popup.winfo_y() + deltay
        self.popup.geometry(f"{self.popup_width}x{self.popup_height}+{new_x}+{new_y}")

    def stop_drag(self, event):
        pass

    def close_popup(self):
        self.popup.destroy()
