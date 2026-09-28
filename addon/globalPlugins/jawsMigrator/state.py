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
	#: The JAWS commands learned since the first migrations whose keystrokes were added after an update, or needed none,
	#: such as SayAppVersion (see newKeys).
	"newKeysAdded": [],
	#: True once version 1.32 or later planned those commands again, for a keystroke gestures.ini gives to an add-on that
	#: is off (see newKeys).
	"newKeysRechecked": False,
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
	#: Quick navigation says a heading or an edit field without the landmark, region or list it is in, and an empty edit
	#: field with "blank, placeholder", as JAWS does (see quickNavHeadings). Version 1.12's "sayHeadingLevelFirst" (a
	#: heading's level before its text) is gone: JAWS says the text first.
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
	#: NVDA registers a focused document's UI Automation events without its Value, the whole text, which Windows 11's
	#: Notepad built at every key, slowing typing in a large file (see documentValues).
	"documentsWithoutValueEvents": True,
	#: NVDA started with the focus on the taskbar, as its desktop shortcut's key leaves it, gives the focus back to the
	#: window you were in, or the desktop, as JAWS does (see startupFocus).
	"backFromTaskbarAtStart": True,
	#: NVDA's Elements List shows a link as JAWS's Links List does: "current page" before it and its shortcut key after it,
	#: without visited, same page or "level 0"; NVDA says "no links" on a page without links, and moves browse mode's
	#: cursor to the link it activates from the list (see linksList).
	"linksLikeJaws": True,
	#: Each of JAWS's list keys opens NVDA's Elements List on its own kind alone, with JAWS's title and no radio buttons
	#: for other kinds: Insert+F7 links, Insert+F6 headings, Insert+F5 form fields, Control+Insert+B buttons and
	#: Control+Insert+R regions, and JAWS's words on a page with none (see linksList).
	"listKeysLikeJaws": True,
	#: An alert with nothing in it, which NVDA said as "alert" alone, isn't said, as JAWS says nothing for it (see emptyAlerts).
	"quietEmptyAlerts": True,
	#: An arrow key at the start or end of an edit field on a web page stays in the field, in focus mode, as in JAWS's Auto
	#: Forms Mode; only Up or Down Arrow in a field of one line goes on in browse mode (see fieldEdges).
	"stayInFieldsAtTheirEdges": True,
	#: In Outlook's message list, the message you leave isn't said again, with the status of the one you move to; JAWS
	#: says only the message you move to (see outlookRows).
	"quietLeftOutlookMessage": True,
	#: An Outlook message NVDA reads through UI Automation is said without page and section numbers, as JAWS says it and
	#: as NVDA's Outlook support does through Word's object model (see outlookPages).
	"outlookWithoutPageNumbers": True,
	#: The Columns Review add-on says nothing at the ends of a list where it would say "List top", "List bottom" or
	#: "Mono-item list" with the voice; JAWS says the item alone. Its beeps stay (see listBounds).
	"quietColumnsReviewListBounds": True,
	#: Columns Review and Emoticons don't hold NVDA up each time it switches configuration profiles, as switching
	#: programs or browse mode does: Columns Review keeps the keys of NVDA's own commands until they change, and Emoticons
	#: reads NVDA's dictionaries once for each change (see profileSwitches).
	"quickProfileSwitches": True,
	#: A link on a web page is said as JAWS says it: "same page" only for a link to a place on the page (a "#" in its
	#: address), without the title NVDA says as its description, and, when quick navigation moves to a heading, "link"
	#: after the heading and its level; quick navigation says no description of a link or heading (see linkSpeech).
	"sayLinksAsJaws": True,
	#: Alt+Left and Alt+Right in Edge, Chrome and Firefox say "Back" and "Forward" and leave focus mode, as JAWS's GoBack
	#: and GoForward do, and a page that comes back without loading is read at the caret (see backForward).
	"backForwardAsJaws": True,
	#: An edit field on a web page is said as JAWS says it: an empty one as "edit, blank, placeholder" and its
	#: placeholder, no "multi line" for any edit field, and nothing again of what browse mode's cursor was in when the
	#: focus moves there (see formFields).
	"sayFormFieldsAsJaws": True,
	#: Edge's and Chrome's windows and pages are said as JAWS says them: the window by its name and a page that opens by
	#: its title, without "window", "document", the page's address or Edge's frame around the page (see browserPages).
	"sayBrowserPagesAsJaws": True,
	#: Regions, groups, lists and articles on web pages are said with JAWS's words: "main region", "group", "list of 2
	#: items", "main region end", and, as you read, no banner, search, form, complementary or content info region
	#: (see webRegions).
	"sayWebRegionsAsJaws": True,
	#: An Outlook message you read is said as JAWS says it: "send mail link" for a link to an e-mail address, a list
	#: where it starts and after it, and no "heading level 1" for the From line of a message it quotes (see
	#: outlookMessages).
	"outlookMessagesAsJaws": True,
	#: An Outlook message you open isn't read from the top: the tester's JAWS reads it only with the arrow keys (issue
	#: 23). Turned on, it is, as JAWS's "Messages automatically read" does (see outlookMessages).
	"readOutlookMessagesOnOpen": False,
	#: In Outlook, NVDA's "Report status bar" (JAWS's Insert+Page Down) reads the status bar as JAWS's script for Outlook
	#: does: its items, such as "Items in View" and the zoom, without "Status Bar" and the view and zoom buttons (see
	#: outlookStatusBar).
	"outlookStatusBarLikeJaws": True,
	#: What NVDA says is kept, the last 500 things, for NVDA+Shift+J then H, Control+H and Shift+H, as JAWS keeps its
	#: speech history for Insert+Space then the same keys; JAWS's [Options] SpeechHistory (see speechHistory).
	"keepSpeechHistory": True,
	#: NVDA says "Unloading NVDA" as it exits, as JAWS's Insert+F4 says "Unloading JAWS" where JAWS Messages are on at the
	#: user's verbosity level; off unless a migration or the user turns it on (see exitMessage).
	"sayUnloadingNvda": False,
	#: True once the assistant looked whether JAWS says "Unloading JAWS", for a migration made before 1.37 (see exitMessage).
	"exitMessageChecked": False,
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
