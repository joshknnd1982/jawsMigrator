import time
from rig2 import Scenario
s = Scenario()
w = s.cdp.send("Browser.getWindowForTarget")
s.cdp.send("Browser.setWindowBounds", windowId=w["windowId"], bounds={"width": 1280, "height": 1000, "windowState": "normal"})
time.sleep(2)
print("inner size (CSS):", s.cdp.js("[innerWidth, innerHeight, devicePixelRatio]"))
