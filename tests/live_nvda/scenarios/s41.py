"""A small window: the list runs past the bottom of the page. What does NVDA say about each suggestion?"""
import json, time
from rig2 import Scenario

s = Scenario()
w = s.cdp.send("Browser.getWindowForTarget")
print("window:", w)
s.cdp.send("Browser.setWindowBounds", windowId=w["windowId"], bounds={"width": 1000, "height": 430, "windowState": "normal"})
time.sleep(2)
print("inner size (CSS):", s.cdp.js("[innerWidth, innerHeight, devicePixelRatio]"))
s.fresh()
print("page:", s.page())
code = """
import api
field = api.getFocusObject()
doc = field.treeInterceptor.rootNVDAObject
box = field.controllerFor[0] if field.controllerFor else field.next
kids = list(box.children)
dl = doc.location
bl = box.location
out = {'document': list(dl), 'box': list(bl), 'docBottom': dl.top + dl.height, 'boxBottom': bl.top + bl.height, 'options': []}
for i, k in enumerate(kids[:9]):
    loc = k.location
    x, y = loc.center
    out['options'].append({'i': i, 'center': [x, y], 'offscreenState': k.hasIrrelevantLocation, 'inBox': bl.left <= x < bl.left + bl.width and bl.top <= y < bl.top + bl.height, 'inDocument': dl.left <= x < dl.left + dl.width and dl.top <= y < dl.top + dl.height})
result = out
"""
res = s.driver("eval", code=code)["result"]
print("document:", res["document"], "box:", res["box"], "docBottom:", res["docBottom"], "boxBottom:", res["boxBottom"])
for o in res["options"]:
    print(o)
