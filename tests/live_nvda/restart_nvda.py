import json
import os
import sys
import time

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from rig import Rig  # noqa: E402

json.dump({"label": "nvda"}, open(os.path.join(here, "kill-%d.json" % int(time.time() * 1000)), "w"))
time.sleep(4)
for name in ("nvda.log", os.path.join("cfg", "driver", "res.json"), os.path.join("cfg", "driver", "cmd.json")):
	try:
		os.remove(os.path.join(here, name))
	except OSError:
		pass
cmd = (
	'"C:\\Program Files\\NVDA\\nvda_noUIAccess.exe" -c "' + os.path.join(here, "cfg") + '" -f "' + os.path.join(here, "nvda.log")
	+ '" --no-sr-flag --debug-logging'
)
r = Rig()
r.spawn("nvda", cmd)
for _ in range(60):
	try:
		print("driver:", r.driver("ping", timeout=3))
		break
	except Exception:
		time.sleep(1)
