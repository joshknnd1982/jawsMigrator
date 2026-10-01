"""1.55: a row that straddles the bottom edge of the page is scrolled in, and pressed inside the page."""
import json, time
from rig2 import Scenario

s = Scenario()
s.fresh()
s.cdp.js("document.querySelector('#address-dropdown').scrollTop = 30; 1")
time.sleep(1.5)
print("inner size (CSS):", s.cdp.js("[innerWidth, innerHeight, devicePixelRatio, scrollY, document.querySelector('#address-dropdown').scrollTop]"))
for _ in range(4):
    s.press("downArrow", show=False)
names = s.cdp.js("[...document.querySelectorAll('#address-dropdown [role=option]')].map(o => o.textContent.trim())")
print("the 4th option:", names[3])
s.press("enter")
print("page after Enter:", s.page())
print("page scroll:", s.cdp.js("[scrollY, document.querySelector('#address-dropdown').scrollTop]"))
code = """
import api
field = api.getFocusObject()
doc = field.treeInterceptor.rootNVDAObject
result = list(doc.location)
"""
print("document rect now:", s.driver("eval", code=code)["result"])
print("the field has the 4th address:", s.page()["value"] == names[3])
