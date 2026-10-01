"""1.55 in the small window: a row the page's edge hides completely, then Up Arrow and Enter on one that shows."""
import json, time
from rig2 import Scenario

s = Scenario()
s.fresh()
s.cdp.js("document.querySelector('#address-dropdown').scrollTop = 30; 1")
time.sleep(1.5)
for _ in range(6):
    s.press("downArrow", show=False)
s.press("enter")
print("page after Enter on the hidden row:", s.page())
s.press("upArrow")
s.press("upArrow")
s.press("upArrow")
s.press("enter")
print("page after Up x3 and Enter:", s.page())
