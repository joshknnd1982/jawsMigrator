import json
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
what = sys.argv[1] if len(sys.argv) > 1 else "nvda"
#: A rig of its own needs its own desktop name and DevTools port when another rig runs at the same time (two sessions): NVDA's single
#: instance is per desktop, so a second NVDA on a desktop that already has one ends the first. JM_RIG_DESKTOP and JM_RIG_PORT change them.
desktop = os.environ.get("JM_RIG_DESKTOP", "jm47")
port = os.environ.get("JM_RIG_PORT", "9444")
start = []
nvda = (
	'"C:\\Program Files\\NVDA\\nvda_noUIAccess.exe" -c "' + os.path.join(here, "cfg") + '" -f "' + os.path.join(here, "nvda.log")
	+ '" --no-sr-flag --debug-logging'
)
start.append({"label": "nvda", "cmd": nvda, "wait": 15})
if what == "full":
	edge = (
		'"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" --user-data-dir="' + os.path.join(here, "edgeprofile")
		+ '" --remote-debugging-port=' + port + ' --remote-allow-origins=* --no-first-run --no-default-browser-check'
		+ " --disable-gpu --force-renderer-accessibility --window-position=0,0 --window-size=1280,1000 about:blank"
	)
	start.append({"label": "edge", "cmd": edge, "wait": 6})
config = {"desktop": desktop, "start": start}
with open(os.path.join(here, "deskhost.json"), "w", encoding="utf-8") as stream:
	json.dump(config, stream, indent=1)
print(json.dumps(config, indent=1))
