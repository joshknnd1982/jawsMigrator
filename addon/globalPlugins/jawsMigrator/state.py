# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""The assistant's own settings, kept in ``jawsMigrator\\state.json`` in NVDA's settings folder.

They live outside nvda.ini on purpose: restoring a backup of NVDA's settings
must not undo the assistant's record of that backup, and NVDA configuration
profiles must not change them.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading

from . import nvdaEnv, safety

STATE_FILE = "state.json"

DEFAULTS = {
	"version": 1,
	#: The assistant opened itself once after being installed.
	"welcomeShown": False,
	"checkForUpdatesAutomatically": True,
	"lastUpdateCheck": 0,
	#: Name of the NVDA profile holding migrated settings, when one was made.
	"jawsProfileName": "",
	"activateJawsProfileAtStartup": False,
	#: Version 1.1 played JAWS sounds itself; kept only to turn that off (sounds now go through ClassicSpeech).
	"jawsSoundsEnabled": False,
	#: {NVDA sound name: path of the copied JAWS sound}
	"soundReplacements": {},
	#: Executable names (lower case, no extension) where NVDA sleeps, as JAWS did.
	"sleepApps": [],
	"lastReport": "",
	"lastBackup": "",
	"lastMigration": {},
	#: Which JAWS items to import, chosen in JAWS Migration Assistant settings (see selection.py).
	"importSelection": {},
	#: The JAWS sounds given to ClassicSpeech's schemes in place of NVDA's (see classicSounds).
	"classicNvdaSounds": {},
}

_lock = threading.RLock()
_cache: dict | None = None


def statePath() -> str:
	return nvdaEnv.addonDataDir(STATE_FILE)


def load() -> dict:
	global _cache
	with _lock:
		if _cache is not None:
			return _cache
		data = dict(DEFAULTS)
		try:
			with open(statePath(), encoding="utf-8") as stream:
				stored = json.load(stream)
			if isinstance(stored, dict):
				for key, value in stored.items():
					if key in DEFAULTS and isinstance(value, type(DEFAULTS[key])):
						data[key] = value
		except (OSError, ValueError):
			pass
		_cache = data
		return data


def save() -> bool:
	with _lock:
		data = load()
		if not nvdaEnv.shouldWriteToDisk():
			return False
		folder = os.path.dirname(statePath())
		try:
			safety.checkWritable(folder)
			os.makedirs(folder, exist_ok=True)
			handle, temporary = tempfile.mkstemp(prefix="state-", suffix=".tmp", dir=folder)
			with os.fdopen(handle, "w", encoding="utf-8") as stream:
				json.dump(data, stream, ensure_ascii=False, indent="\t")
			os.replace(temporary, statePath())
			return True
		except OSError:
			return False


def get(key: str):
	return load().get(key, DEFAULTS.get(key))


def set(key: str, value, persist: bool = True) -> None:  # noqa: A001 - mirrors dict.set naming
	with _lock:
		load()[key] = value
		if persist:
			save()


def update(values: dict) -> None:
	with _lock:
		load().update(values)
		save()


def forget() -> None:
	"""Drop the cached copy so the next read comes from disk."""
	global _cache
	with _lock:
		_cache = None
