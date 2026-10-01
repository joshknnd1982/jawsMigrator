"""1.53 as shipped, the key looked up on the hook-like thread: what does Down Arrow do?"""
from rig2 import Scenario

s = Scenario()
s.fresh()
print("page:", s.page())
s.press("downArrow", wait=2.0)
print("page:", s.page())
print("nvda:", s.nvda())
s.press("downArrow", wait=2.0)
