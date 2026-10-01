"""Does IAccessible2's scrollTo move the page for a row the page's edge hides completely (row 4), and does the DOM's own scrollIntoView move it for row 3?"""
import json, time
from rig2 import Scenario

s = Scenario()
s.fresh()
RESET = "(() => { window.scrollTo(0, 0); document.querySelector('#address-dropdown').scrollTop = 30; return 1; })()"
def probe(i):
    return s.cdp.js("(() => { const o = document.querySelectorAll('#address-dropdown [role=option]')[%d].getBoundingClientRect(); return [Math.round(scrollY), Math.round(document.querySelector('#address-dropdown').scrollTop), Math.round(o.top), Math.round(o.bottom), innerHeight]; })()" % i)

for i in (3, 4, 5):
    s.cdp.js(RESET); time.sleep(0.8)
    before = probe(i)
    code = """
import api, time
field = api.getFocusObject()
box = field.controllerFor[0] if field.controllerFor else field.next
k = list(box.children)[%d]
st = sorted(x.name for x in k.states)
k.scrollIntoView()
time.sleep(0.4)
result = st
""" % i
    st = s.driver("eval", code=code)["result"]
    time.sleep(0.4)
    print(f"IA2 ANYWHERE on row {i}: states={st}\n   before={before} after={probe(i)}")

s.cdp.js(RESET); time.sleep(0.8)
before = probe(3)
s.cdp.js("document.querySelectorAll('#address-dropdown [role=option]')[3].scrollIntoView({block: 'nearest'}); 1")
time.sleep(0.6)
print("DOM scrollIntoView({block:'nearest'}) on row 3: before", before, "after", probe(3))
