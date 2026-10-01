"""Install some of the tester's other add-ons into the private NVDA's config (never into Josh's NVDA)."""
import json
import os
import subprocess
import sys
import zipfile

here = os.path.dirname(os.path.abspath(__file__))
dst = os.path.join(here, "cfg", "addons")
tmp = os.path.join(here, "addondl")
os.makedirs(tmp, exist_ok=True)

# the tester's version of each, as in his log
WANTED = {
	"customBrowseMode": "7.0.0",
	"enhancedControlSupport": "1.2.2",
	"controlUsageAssistant": "20260826.0.0",
	"windowState": "1.3.0",
	"screenWrapping": "26.1",
	"SentenceNav": "2.14.2",
	"numpadNavMode": "26.2.500",
	"CustomLabels": "2026.3.1",
	"virtualRevision": "2026.07.29",
	"placeMarkers": "53.0.0",
	"unmute": "1.7.0",
}


def gh(path):
	out = subprocess.check_output(["gh", "api", "-H", "Accept: application/vnd.github.raw", path])
	return out


for name, version in WANTED.items():
	try:
		meta = json.loads(gh(f"repos/nvaccess/addon-datastore/contents/addons/{name}/{version}.json"))
	except Exception as error:
		print("no metadata", name, version, error)
		continue
	url = meta["URL"]
	target = os.path.join(tmp, f"{name}-{version}.nvda-addon")
	if not os.path.exists(target):
		subprocess.check_call(["curl", "-sL", "-o", target, url])
	folder = os.path.join(dst, meta.get("addonId", name))
	with zipfile.ZipFile(target) as package:
		package.extractall(folder)
	print("installed", meta.get("addonId", name), version, meta.get("displayName"))
