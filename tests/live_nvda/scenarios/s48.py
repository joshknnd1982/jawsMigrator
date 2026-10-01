import json, time
from rig2 import Scenario

s = Scenario()
print("scroll-behavior html/body:", s.cdp.js("[getComputedStyle(document.documentElement).scrollBehavior, getComputedStyle(document.body).scrollBehavior]"))
RESET = "(() => { window.scrollTo({top: 0, behavior: 'instant'}); document.querySelector('#address-dropdown').scrollTop = 30; return 1; })()"
def probe(i=3):
    return s.cdp.js("(() => { const o = document.querySelectorAll('#address-dropdown [role=option]')[%d].getBoundingClientRect(); return [Math.round(scrollY), Math.round(document.querySelector('#address-dropdown').scrollTop), Math.round(o.top), Math.round(o.bottom), innerHeight]; })()" % i)
for label, js in (
    ("DOM nearest, instant", "document.querySelectorAll('#address-dropdown [role=option]')[3].scrollIntoView({block: 'nearest', behavior: 'instant'}); 1"),
    ("DOM end, instant", "document.querySelectorAll('#address-dropdown [role=option]')[3].scrollIntoView({block: 'end', behavior: 'instant'}); 1"),
    ("DOM start, instant", "document.querySelectorAll('#address-dropdown [role=option]')[3].scrollIntoView({block: 'start', behavior: 'instant'}); 1"),
):
    s.cdp.js(RESET); time.sleep(0.8)
    before = probe()
    s.cdp.js(js)
    for wait in (0.05, 0.3, 1.0):
        time.sleep(wait)
        print(f"{label:22} +{wait:.2f}s before={before} after={probe()}")
