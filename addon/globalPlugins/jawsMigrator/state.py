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
	#: The version of the one-time repair of ClassicSpeech voices from versions 1.0 to 1.2 (see classicRepair).
	"voicesRepaired": 0,
	#: The version of the one-time repair of dictionary rules from versions 1.0 to 1.2 (see dictRepair).
	"dictionariesRepaired": 0,
	#: The version of the one-time repair of keystrokes from versions 1.0 to 1.2 (see gestureRepair).
	"gesturesRepaired": 0,
	#: JAWS Laptop layout keystrokes that run another command with Insert than with Caps Lock:
	#: {normalized gesture: entry} (see insertKeys).
	"insertKeys": {},
	#: 1 once the Insert keystrokes of a migration were worked out (see insertKeys.repairOnce).
	"insertKeysVersion": 0,
	#: The version of the one-time repair of Eloquence rates from versions 1.0 to 1.3 (see rateRepair).
	"eloquenceRateRepaired": 0,
	#: The version of the one-time repair of symbols for spaces and line breaks from versions 1.0 to 1.9 (see symbolRepair).
	"symbolsRepaired": 0,
	#: A user of versions 1.0 to 1.2 was told once why their separate JAWS profile switches off.
	"profileNoticeShown": False,
	#: The user asked not to be offered ClassicSpeech each time the assistant opens.
	"classicSpeechOfferDeclined": False,
	#: NVDA says a control's type and state once, when a web page repeats them in the label (see labelRepeats),
	#: and when NVDA would report a change it has just said (see changeRepeats).
	"sayTypeAndStateOnce": True,
	#: NVDA+Shift+J plays JAWS's layered keystroke sound; a beep when turned off (see layerSound).
	"playJawsLayerSound": True,
	#: NVDA says a system tray icon when the focus moves to it, not each time its program changes it (see trayChanges).
	"quietTrayIconChanges": True,
	#: Quick navigation says a heading without the landmark, region or list it is in, as JAWS does (see quickNavHeadings).
	#: Version 1.12's "sayHeadingLevelFirst" (a heading's level before its text) is gone: JAWS says the text first.
	"sayHeadingAlone": True,
	#: An item in a list is said without its row and column numbers, as JAWS says it (see listCoordinates).
	"listItemsWithoutCoordinates": True,
	#: Alt+Tab says a window without its position, and File Explorer says an item's position only while you move
	#: through its list, as JAWS's scripts do (see listPosition).
	"positionLikeJawsInExplorer": True,
	#: A drive is said without the ":)" after its letter, "Data (D:)" as "Data (D", as JAWS says it (see driveLetters).
	"driveLetterLikeJaws": True,
	#: Backspace says what it deletes when a slow program deletes after NVDA stopped waiting (see backspaceEcho).
	"sayWhatBackspaceDeletes": True,
	#: A web page's tabs, and toolbar buttons reached with Tab, stay in browse mode, as in JAWS's Auto Forms Mode,
	#: so letters don't reach the page (see autoFormsMode).
	"browseModeOnTabsAndToolbars": True,
	#: Enhanced Control Support leaves its 50 ms timer off documents NVDA follows itself, where it read the whole text
	#: each time and a large file froze NVDA (see documentPolling).
	"documentsWithoutControlSupportTimer": True,
	#: NVDA started with the focus on the taskbar, as its desktop shortcut's key leaves it, gives the focus back to the
	#: window you were in, or the desktop, as JAWS does (see startupFocus).
	"backFromTaskbarAtStart": True,
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
