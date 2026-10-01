"""IAccessible2 scrollToPoint: move a row that the page's bottom edge hides, to the top of its list."""
import json, time
from rig2 import Scenario

s = Scenario()
s.fresh()
RESET = "(() => { window.scrollTo({top: 0, behavior: 'instant'}); document.querySelector('#address-dropdown').scrollTop = 30; return 1; })()"
def probe(i):
    return s.cdp.js("(() => { const o = document.querySelectorAll('#address-dropdown [role=option]')[%d].getBoundingClientRect(); return [Math.round(scrollY), Math.round(document.querySelector('#address-dropdown').scrollTop), Math.round(o.top), Math.round(o.bottom), innerHeight]; })()" % i)
for i in (3, 4, 6):
    s.cdp.js(RESET); time.sleep(0.8)
    before = probe(i)
    code = """
import api, time
field = api.getFocusObject()
box = field.controllerFor[0] if field.controllerFor else field.next
k = list(box.children)[%d]
bl = box.location
try:
    k.IAccessibleObject.scrollToPoint(0, bl.left + 4, bl.top + 4)
    err = None
except Exception as e:
    err = repr(e)
time.sleep(0.3)
k.invalidateCache()
doc = field.treeInterceptor.rootNVDAObject.location
loc = k.location
result = {'err': err, 'center': list(loc.center), 'docBottom': doc.top + doc.height, 'inside': doc.top <= loc.center[1] < doc.top + doc.height, 'offscreen': k.hasIrrelevantLocation}
""" % i
    res = s.driver("eval", code=code)["result"]
    time.sleep(0.4)
    print(f"row {i}: before={before} after={probe(i)} nvda={res}")
