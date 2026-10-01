"""A row that straddles the bottom edge of the page: where does 1.54 press it?"""
import json, time
from rig2 import Scenario

s = Scenario()
s.fresh()
s.cdp.js("document.querySelector('#address-dropdown').scrollTop = 30; 1")
time.sleep(1.5)
code = """
import api
field = api.getFocusObject()
doc = field.treeInterceptor.rootNVDAObject
box = field.controllerFor[0] if field.controllerFor else field.next
kids = list(box.children)
dl = doc.location
out = {'document': list(dl), 'docBottom': dl.top + dl.height, 'rows': []}
for i, k in enumerate(kids[:6]):
    loc = k.location
    x, y = loc.center
    out['rows'].append({'i': i, 'top': loc.top, 'bottom': loc.top + loc.height, 'center': [x, y], 'offscreenState': k.hasIrrelevantLocation, 'centerInDocument': dl.top <= y < dl.top + dl.height})
result = out
"""
res = s.driver("eval", code=code)["result"]
print("document:", res["document"], "docBottom:", res["docBottom"])
for row in res["rows"]:
    print(row)
for _ in range(4):
    s.press("downArrow", show=False)
s.driver("sent")
s.press("enter")
sent = s.driver("sent")
print("after Enter, said:", s.said() if hasattr(s, "said") else "")
