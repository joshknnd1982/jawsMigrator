# Builds the JAWS Migration Assistant add-on package.
# Usage: python build.py
# Writes dist/jawsMigrator-<version>.nvda-addon and dist/jawsMigrator-<version>.nvda-addon.sha256.
# The version comes from addon/manifest.ini. The help page, addon/doc/en/readme.html,
# is made from README.md (needs the markdown package: pip install markdown).

import hashlib
import html
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.join(ROOT, "addon")
DIST = os.path.join(ROOT, "dist")
#: A fixed time for every file in the package, so the same source always builds the same bytes.
ZIP_TIME = (2026, 1, 1, 0, 0, 0)
EXCLUDED_DIRS = {"__pycache__"}
EXCLUDED_EXTENSIONS = {".pyc", ".pyo"}


def manifestValue(key):
	with open(os.path.join(ADDON, "manifest.ini"), encoding="utf-8") as stream:
		for line in stream:
			match = re.match(rf"^{key}\s*=\s*(.+?)\s*$", line)
			if match:
				return match.group(1).strip().strip('"')
	raise SystemExit(f"manifest.ini has no {key}")


def buildHelp(version):
	try:
		import markdown
	except ImportError:
		raise SystemExit("The markdown package is needed to build the help page: pip install markdown")
	with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as stream:
		text = stream.read()
	body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"], output_format="html")
	page = (
		"<!DOCTYPE html>\n"
		'<html lang="en">\n<head>\n<meta charset="utf-8">\n'
		f"<title>{html.escape('JAWS Migration Assistant ' + version)}</title>\n"
		"<style>body{font-family:Segoe UI,Arial,sans-serif;max-width:60em;margin:1em auto;padding:0 1em;line-height:1.5}"
		"table{border-collapse:collapse}th,td{border:1px solid #888;padding:.3em .6em;text-align:left;vertical-align:top}"
		"code{font-family:Consolas,monospace}</style>\n"
		"</head>\n<body>\n"
		f"{body}\n"
		"</body>\n</html>\n"
	)
	target = os.path.join(ADDON, "doc", "en", "readme.html")
	os.makedirs(os.path.dirname(target), exist_ok=True)
	with open(target, "w", encoding="utf-8", newline="\n") as stream:
		stream.write(page)
	return target


def packageFiles():
	files = []
	for folder, dirs, names in os.walk(ADDON):
		dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
		for name in sorted(names):
			if os.path.splitext(name)[1].lower() in EXCLUDED_EXTENSIONS:
				continue
			path = os.path.join(folder, name)
			files.append((path, os.path.relpath(path, ADDON).replace(os.sep, "/")))
	return files


def build():
	name = manifestValue("name")
	version = manifestValue("version")
	buildHelp(version)
	os.makedirs(DIST, exist_ok=True)
	fileName = f"{name}-{version}.nvda-addon"
	target = os.path.join(DIST, fileName)
	with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as package:
		for path, archiveName in packageFiles():
			info = zipfile.ZipInfo(archiveName, ZIP_TIME)
			info.compress_type = zipfile.ZIP_DEFLATED
			info.external_attr = 0o644 << 16
			with open(path, "rb") as stream:
				package.writestr(info, stream.read())
	digest = hashlib.sha256(open(target, "rb").read()).hexdigest()
	with open(target + ".sha256", "w", encoding="ascii", newline="\n") as stream:
		stream.write(f"{digest}  {fileName}\n")
	print(f"Built {target}")
	print(f"SHA-256 {digest}")
	return target


if __name__ == "__main__":
	sys.exit(0 if build() else 1)
