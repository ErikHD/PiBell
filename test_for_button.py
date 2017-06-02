from button import *
import time


b = Button(25)

while True:
    if b.is_pressed():
        print(time.time())
        print("Button press detected")
