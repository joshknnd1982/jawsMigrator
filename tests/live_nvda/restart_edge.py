"""Kill Edge on the private desktop and start it again on the rig's page.

Run it after ``restart_nvda.py`` (``deploy.py`` runs that): NVDA injects its helper into the browser when the browser starts after it, and an
Edge that was already running when NVDA started again is left without it ("appModule has no binding handle to injected code, can't prepare
virtualBuffer yet" in NVDA's log). The document then has no buffer (``isReady`` False, browse mode), and NVDA never gives a field its own
focus event: the add-on's field class and the keys' scripts are looked at in a state a user never has.
"""
import json
import os
import sys
import time

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from rig import PAGE, Rig  # noqa: E402

json.dump({"label": "edge"}, open(os.path.join(here, "kill-%d.json" % int(time.time() * 1000)), "w"))
time.sleep(5)
r = Rig()
print("driver:", r.driver("ping"))
r.startEdge(PAGE)
time.sleep(8 if "visible.com" in PAGE else 4)
print("edge up, title:", r.cdp.js("document.title"))
