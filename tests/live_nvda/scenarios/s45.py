"""Which IAccessible2 scroll type brings a row that straddles the page's bottom edge into the page?"""
import json, time
from rig2 import Scenario

s = Scenario()
s.fresh()
names = {0: "TOP_LEFT", 1: "BOTTOM_RIGHT", 2: "TOP_EDGE", 3: "BOTTOM_EDGE", 4: "LEFT_EDGE", 5: "RIGHT_EDGE", 6: "ANYWHERE"}
RESET = "(() => { window.scrollTo(0, 0); document.querySelector('#address-dropdown').scrollTop = 30; return 1; })()"
PROBE = "[Math.round(scrollY), Math.round(document.querySelector('#address-dropdown').scrollTop), Math.round(document.querySelectorAll('#address-dropdown [role=option]')[3].getBoundingClientRect().top), Math.round(document.querySelectorAll('#address-dropdown [role=option]')[3].getBoundingClientRect().bottom), innerHeight]"
for kind in (6, 3, 2, 0, 1, 4, 5):
    s.cdp.js(RESET)
    time.sleep(0.8)
    before = s.cdp.js(PROBE)
    code = """
import api, time
from comInterfaces import IAccessible2Lib as IA2
field = api.getFocusObject()
box = field.controllerFor[0] if field.controllerFor else field.next
k = list(box.children)[3]
k.IAccessibleObject.scrollTo(%d)
time.sleep(0.3)
k.invalidateCache()
doc = field.treeInterceptor.rootNVDAObject.location
loc = k.location
result = {'center': list(loc.center), 'docBottom': doc.top + doc.height, 'inside': doc.top <= loc.center[1] < doc.top + doc.height}
""" % kind
    try:
        res = s.driver("eval", code=code)["result"]
    except Exception as e:
        res = repr(e)
    time.sleep(0.4)
    after = s.cdp.js(PROBE)
    print(f"{names[kind]:13} before [scrollY, listTop, rowTop, rowBottom, innerH]={before}  after={after}  nvda={res}")
