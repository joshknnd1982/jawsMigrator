import time
from rig import PAGE, Rig
r = Rig()
print("driver:", r.driver("ping"))
r.startEdge(PAGE)
time.sleep(8 if "visible.com" in PAGE else 4)
print("edge up, title:", r.cdp.js("document.title"))
