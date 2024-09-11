# import threading
# import time
#
#
# class MatrixDaemonPlugin:
#     def __init__(self, matrix):
#         self.matrix = matrix
#         self.running = False
#         self.thread = None
#
#     def start(self):
#         if self.running:
#             return
#
#         self.running = True
#         self.thread = threading.Thread(target=self.run)
#         self.thread.start()
#
#     def stop(self):
#         if self.running:
#             self.running = False
#             self.thread.join()
#
#     def run(self):
#         while self.running:
#             self.matrix.update()
#             time.sleep(0.1)
