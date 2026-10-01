"""The tester's steps: type, Down Arrow to the 13th address (out of the list's box), Enter."""
from rig2 import Scenario

s = Scenario()
s.fresh()
for i in range(13):
    s.press("downArrow", show=False)
names = s.cdp.js("[...document.querySelectorAll('#address-dropdown [role=option]')].map(o => o.textContent.trim())")
print("the 13th option on the page:", names[12])
print("page before choosing:", s.page(), "scrollTop:", s.cdp.js("document.querySelector('#address-dropdown').scrollTop"))
s.press("enter")
print("page after Enter:", s.page(), "scrollTop:", s.cdp.js("document.querySelector('#address-dropdown').scrollTop"))
print("nvda:", s.nvda())
print("the field has the 13th address:", s.page()["value"] == names[12])
