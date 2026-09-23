# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""The assistant's promise: JAWS is only ever read, never changed.

The assistant opens JAWS files read-only, copies them into NVDA's settings
folder, and never uninstalls, updates or reconfigures JAWS. Every function that
writes a file asks ``checkWritable`` first, which refuses any path inside a
JAWS program or settings folder, so a mistake anywhere in the assistant cannot
change JAWS.
"""

from __future__ import annotations

import os

from . import jawsDetect


class JawsProtectedError(OSError):
	"""Raised instead of writing to a JAWS folder."""


_roots: list[str] | None = None


def _normalize(path: str) -> str:
	return os.path.normcase(os.path.abspath(path)).rstrip("\\/")


def jawsRoots() -> list[str]:
	"""Every folder JAWS keeps its program or settings in, for every JAWS version found."""
	global _roots
	if _roots is None:
		roots = set()
		for root in (jawsDetect.appDataFolder(), jawsDetect.programDataFolder(), *jawsDetect.programFilesFolders()):
			if root:
				roots.add(_normalize(os.path.join(root, "Freedom Scientific")))
		try:
			for jaws in jawsDetect.findJawsInstallations():
				for folder in (jaws.installDir, jaws.userRoot, jaws.sharedRoot):
					if folder:
						roots.add(_normalize(folder))
		except Exception:
			pass
		_roots = sorted(roots)
	return _roots


def isJawsPath(path: str) -> bool:
	target = _normalize(path)
	return any(target == root or target.startswith(root + os.sep) for root in jawsRoots())


def checkWritable(path: str) -> str:
	"""Return ``path`` if the assistant may write it; raise JawsProtectedError for JAWS folders."""
	if isJawsPath(path):
		raise JawsProtectedError(f"The JAWS Migration Assistant never changes JAWS files: {path}")
	return path


UNINSTALL_NOTE = (
	"JAWS was not changed: the assistant only read your JAWS settings. "
	"Now that they are in NVDA, you can uninstall JAWS yourself if you wish, from Windows Settings, Apps, Installed apps. "
	"The assistant never uninstalls JAWS. Keep JAWS for a while if you like, to compare, or if you still need it for some programs."
)
