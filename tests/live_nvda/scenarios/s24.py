"""Other ways through: browse mode after Escape; typing and Escape during a visit; Tab; a field with no suggestions."""
import time
from rig2 import Scenario

s = Scenario()
print("=== A: Escape (browse mode, focus stays in the field), then Down Arrow, Down Arrow, Enter")
s.fresh()
s.press("escape")
print("   nvda:", s.nvda(), "page:", s.page())
s.press("downArrow")
s.press("downArrow")
print("   nvda:", s.nvda())
s.press("enter")
print("   page after Enter:", s.page(), "nvda:", s.nvda())

print("=== B: a visit, then a typed letter (goes to the page, visit over), then Down Arrow starts again")
s.fresh()
s.press("downArrow")
s.press("downArrow")
s.press("x")
time.sleep(3)
print("   page:", s.page())
s.press("downArrow")

print("=== C: a visit, then Escape (the page closes its list), then Down Arrow goes to the page")
s.fresh()
s.press("downArrow")
s.press("escape")
print("   page:", s.page(), "nvda:", s.nvda())
s.press("downArrow")

print("=== D: a visit, then Tab (leaves the field)")
s.fresh()
s.press("downArrow")
s.press("tab")
print("   page:", s.page(), "nvda:", s.nvda())
