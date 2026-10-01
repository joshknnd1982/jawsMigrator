"""Control+Z after the user typed something else (issue 47, 1.56): it is the page's own, not the assistant's, and the page's text is not
replaced by what was typed before the choice."""
import time

from rig2 import Scenario

s = Scenario()
s.fresh()
for key in ["downArrow"] * 8 + ["enter"]:
    s.press(key, wait=0.8, show=False)
time.sleep(0.5)
s.cdp.type("x")
time.sleep(0.8)
print("page before:", s.page())
info = s.press("control+z", wait=1.0)
print("forwarded to the page:", info["forwardedToPage"])
print("page after:", s.page())
