"""Down Arrow right after Control+Z when the page is slow to show its suggestions again (issue 47, 1.57).

A: the service answers 900 ms after the 300 ms of quiet: Down Arrow waits for the list (it waits at most 1.5 seconds) and says the first suggestion.
B: the service answers after 4 seconds: Down Arrow waits the 1.5 seconds, then goes on as NVDA has it (here it leaves the field: automatic focus mode for caret movement).
"""
import time

from rig2 import Scenario

s = Scenario()


def chooseThird():
    s.fresh()
    for key in ["downArrow"] * 3 + ["enter"]:
        s.press(key, wait=0.5, show=False)
    time.sleep(0.3)


def gestureTimes():
    out = []
    for line in s.newLog("DRIVER gesture|Speaking \\[|were (not )?back", limit=400):
        out.append(line[:230])
    return out


for label, delay in (("A: slow service (900 ms)", 900), ("B: very slow service (4000 ms)", 4000)):
    print("===", label)
    chooseThird()
    s.cdp.js(f"window.__serviceDelay = {delay}; 1")
    s.newLog()
    s.press("control+z", wait=0.05, show=False)
    s.press("downArrow", wait=0.2, show=False)
    for line in gestureTimes():
        print("   ", line)
    print("    page:", s.page())
    print("    nvda:", {k: v for k, v in s.nvda().items() if k in ("passThrough", "caretLine")})
    time.sleep(4.5)
s.cdp.js("window.__serviceDelay = undefined; 1")
