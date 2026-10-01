"""After: the tester's steps against the new code, in a real NVDA on the live page."""
import json

from rig2 import Scenario

s = Scenario()
s.fresh()
print("page:", s.page())
print("nvda:", s.nvda())
for key in ("downArrow", "downArrow", "downArrow", "upArrow", "end", "home"):
	s.press(key)
	print("   page:", s.page())
for _ in range(12):
	s.press("downArrow", show=False)
s.press("downArrow")
names = s.cdp.js("[...document.querySelectorAll('#address-dropdown [role=option]')].map(o => o.textContent.trim())")
print("the 13th option on the page:", names[12])
print("page before choosing:", s.page(), "scrollTop:", s.cdp.js("document.querySelector('#address-dropdown').scrollTop"))
s.press("enter")
print("page after Enter:", s.page(), "scrollTop:", s.cdp.js("document.querySelector('#address-dropdown').scrollTop"))
print("nvda:", s.nvda())
print("chosen is the 13th:", s.page()["value"] == names[12])
