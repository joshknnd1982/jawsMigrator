"""With nine of the tester's other add-ons loaded: type, Down Arrow x3, Up, Enter."""
from rig2 import Scenario

s = Scenario()
s.fresh()
print("nvda:", s.nvda())
for key in ("downArrow", "downArrow", "downArrow", "upArrow", "enter"):
    s.press(key)
print("page:", s.page())
