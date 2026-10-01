"""The tester's steps of 1 October (issue 47): type, Down Arrow to the eighth address, Enter, then Up Arrow and Down Arrow twice in the field."""
import json

from rig2 import Scenario

s = Scenario()
s.fresh()
print("nvda:", s.nvda())
print("page:", s.page())
for key in ["downArrow"] * 8 + ["enter"]:
    s.press(key, wait=1.0)
print("page after Enter:", s.page())
print("nvda after Enter:", s.nvda())
for key in ("upArrow", "downArrow", "downArrow"):
    s.press(key, wait=1.0)
    print("   page:", s.page(), "nvda:", s.nvda())
print("page log:", json.dumps(s.cdp.js("window.__log")))
