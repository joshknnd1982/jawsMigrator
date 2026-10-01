"""Copy the worktree's add-on into the private NVDA's config, and restart that NVDA."""
import os
import shutil
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(here, "..", "..", "addon")
dst = os.path.join(here, "cfg", "addons", "jawsMigrator")
for folder, dirs, names in os.walk(src):
	dirs[:] = [d for d in dirs if d != "__pycache__"]
	for name in names:
		if name.endswith((".pyc", ".pyo")):
			continue
		path = os.path.join(folder, name)
		target = os.path.join(dst, os.path.relpath(path, src))
		os.makedirs(os.path.dirname(target), exist_ok=True)
		if not os.path.exists(target) or open(path, "rb").read() != open(target, "rb").read():
			shutil.copyfile(path, target)
			print("copied", os.path.relpath(path, src))
cache = os.path.join(dst, "globalPlugins", "jawsMigrator", "__pycache__")
shutil.rmtree(cache, ignore_errors=True)
if "--norestart" not in sys.argv:
	subprocess.check_call([sys.executable, os.path.join(here, "restart_nvda.py")])
