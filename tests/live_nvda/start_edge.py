import time
from rig import Rig
r = Rig()
print("driver:", r.driver("ping"))
r.startEdge("https://www.visible.com/shop/home-internet")
time.sleep(8)
print("edge up, title:", r.cdp.js("document.title"))
