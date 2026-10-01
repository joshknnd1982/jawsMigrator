"""What NVDA's hit test says is under the middle of each suggestion, and at some places that aren't the page."""
import json
from rig2 import Scenario

s = Scenario()
s.fresh()
print("page:", s.page())
code = """
import api, time
field = api.getFocusObject()
box = field.controllerFor[0] if field.controllerFor else field.next
kids = list(box.children)
desk = api.getDesktopObject()
def brief(o):
    if o is None: return None
    return {'role': o.role.name, 'name': (o.name or '')[:30], 'cls': [c.__name__ for c in type(o).__mro__[:2]]}
out = []
for i in (0, 3, 6, 7):
    k = kids[i]
    loc = k.location
    x, y = loc.center
    t0 = time.perf_counter()
    hit = desk.objectFromPoint(x, y)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    chain = []
    o = hit
    for _ in range(4):
        if o is None: break
        chain.append(brief(o)); o = o.parent
    out.append({'i': i, 'offscreen': k.hasIrrelevantLocation, 'center': (x, y), 'ms': ms, 'hit==option': hit == k, 'chain': chain})
for pt in ((5, 5), (960, 1190), (1900, 600)):
    out.append({'point': pt, 'hit': brief(desk.objectFromPoint(*pt))})
result = out
"""
for row in s.driver("eval", code=code)["result"]:
    print(json.dumps(row, default=str))
