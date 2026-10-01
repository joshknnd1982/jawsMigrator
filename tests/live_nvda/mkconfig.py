import json
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
what = sys.argv[1] if len(sys.argv) > 1 else "nvda"
start = []
nvda = (
	'"C:\\Program Files\\NVDA\\nvda_noUIAccess.exe" -c "' + os.path.join(here, "cfg") + '" -f "' + os.path.join(here, "nvda.log")
	+ '" --no-sr-flag --debug-logging'
)
start.append({"label": "nvda", "cmd": nvda, "wait": 15})
if what == "full":
	edge = (
		'"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" --user-data-dir="' + os.path.join(here, "edgeprofile")
		+ '" --remote-debugging-port=9444 --remote-allow-origins=* --no-first-run --no-default-browser-check'
		+ " --disable-gpu --force-renderer-accessibility --window-position=0,0 --window-size=1280,1000 about:blank"
	)
	start.append({"label": "edge", "cmd": edge, "wait": 6})
config = {"desktop": "jm47", "start": start}
with open(os.path.join(here, "deskhost.json"), "w", encoding="utf-8") as stream:
	json.dump(config, stream, indent=1)
print(json.dumps(config, indent=1))
