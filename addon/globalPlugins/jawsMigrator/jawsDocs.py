# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""What JAWS commands do, from the script documentation (``.jsd``) JAWS ships.

A ``.jsd`` file documents each script in lines such as::

	:Script SayWindowTitle
	:DisplayName Say Window Title
	:Synopsis Speaks the title of the current window
	:Description ...

The JAWS keystroke helper uses these texts to say what a JAWS keystroke did.
"""

from __future__ import annotations

import re

from . import jawsFiles

_ENTRY = re.compile(r"^:(?P<kind>script|function)\s+(?P<name>\w+)", re.IGNORECASE)
_FIELD = re.compile(r"^:(?P<field>displayname|synopsis|description)\s+(?P<text>.*)$", re.IGNORECASE)


def parseJsd(text: str) -> dict:
	"""``{script name (lower case): {"displayName": ..., "synopsis": ..., "description": ...}}``."""
	docs: dict = {}
	current = None
	for rawLine in text.splitlines():
		line = rawLine.strip()
		match = _ENTRY.match(line)
		if match:
			current = None
			if match.group("kind").lower() == "script":
				current = docs.setdefault(match.group("name").lower(), {"name": match.group("name")})
			continue
		if current is None:
			continue
		field = _FIELD.match(line)
		if field:
			key = {"displayname": "displayName", "synopsis": "synopsis", "description": "description"}[field.group("field").lower()]
			current.setdefault(key, field.group("text").strip())
	return docs


def readJsd(paths: list[str]) -> dict:
	docs: dict = {}
	for path in paths:
		try:
			parsed = parseJsd(jawsFiles.readText(path))
		except OSError:
			continue
		for name, entry in parsed.items():
			docs.setdefault(name, entry)
	return docs


def describe(docs: dict, scriptName: str) -> str:
	"""A short description of a JAWS script, or its name split into words."""
	name = (scriptName or "").split("(", 1)[0].strip()
	entry = docs.get(name.lower())
	if entry:
		text = entry.get("synopsis") or entry.get("description") or entry.get("displayName")
		if text:
			return text.rstrip(".")
	return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name) or scriptName
