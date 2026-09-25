# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""A system tray icon said when the focus moves to it, not each time its program changes it.

Programs keep the name of their system tray icon up to date. A temperature monitor puts the
temperatures in it and changes them every few seconds, the clock changes every minute, and the
network, volume and battery icons change with what they show. NVDA says the focus's name again
whenever it changes (NVDAObject.event_nameChange, NVDA 2026.2), so while the focus is on such an
icon NVDA keeps reading it. A tester's NVDA started with the focus on a temperature monitor's icon
("CPU 129.9 F; Drive C Temperature 113.0 F; ..., button, 1 of 5") and read new temperatures every
few seconds, until the tester pressed Alt+Tab. NVDA does this without any add-on.

So before NVDA handles a change of the name of a system tray icon that has the focus, the focus
object's notes of what NVDA last said about it (``_speakObjectPropertiesCache``) get the new name,
and NVDA finds nothing new to say. Braille, and everything else that follows the change, goes on as
before, and NVDA+Tab reads the icon as it is now. A change that comes within a moment of a key
pressed on the icon is said as usual, once for each key press, as the key may have made it (a volume
key on the volume icon). It works while the assistant runs, unless it is turned off in NVDA's
Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import time

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "quietTrayIconChanges"
#: The windows the system tray is in: the taskbar, the taskbar on another monitor, and the window of
#: hidden icons (Windows 10's, then Windows 11's).
TRAY_WINDOWS = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland")
#: The windows of hidden icons hold nothing but system tray icons.
HIDDEN_ICONS_WINDOWS = ("NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland")
#: Windows 10's system tray, in the taskbar: the programs' icons, the clock, and the system's own icons and buttons.
TRAY_NOTIFY_WINDOW = "TrayNotifyWnd"
#: How the UI Automation class of each of Windows 11's system tray icons starts: SystemTray.NormalButton
#: for a program's icon, SystemTray.OmniButton for the clock, SystemTray.AccentButton for the network and
#: battery icons. The taskbar's other buttons, in the same window, have other classes.
UIA_CLASS_PREFIX = "SystemTray."
#: A change this soon after a key pressed on the icon may come from that key press, in seconds.
AFTER_KEY_PRESS = 1.5
#: No window is nested deeper than this in the taskbar.
_MOST_WINDOWS = 16

_enabled = False
_failed = False
#: The user's key presses, braille display keys and touch gestures, counted.
_gestures = 0
#: The last of them: (its count, time.monotonic(), the focus it was made on), or None.
_lastGesture: tuple | None = None
#: The count of the key press after which a change was said.
_saidAfter = 0
_MISSING = object()


def _log():
	from logHandler import log

	return log


def _failure(what: str) -> None:
	global _failed
	if _failed:
		return
	_failed = True
	try:
		_log().debugWarning(f"jawsMigrator: {what}", exc_info=True)
	except Exception:
		pass


def wanted(stateData: dict) -> bool:
	"""Whether a system tray icon is said only when the focus moves to it: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def _decider():
	import inputCore

	return inputCore.decide_executeGesture


def register() -> None:
	global _enabled
	if not _enabled:
		try:
			# Every key press NVDA gets, braille display key and touch gesture, before NVDA runs it.
			_decider().register(noteGesture)
		except Exception:
			_failure("can't tell which changes of a system tray icon a key press made")
	_enabled = True


def unregister() -> None:
	global _enabled, _lastGesture
	if not _enabled:
		return
	_enabled = False
	_lastGesture = None
	try:
		_decider().unregister(noteGesture)
	except Exception:
		pass


def isRegistered() -> bool:
	return _enabled


def noteGesture(gesture=None) -> bool:
	"""NVDA's decide_executeGesture handler: note a key press and the focus it was made on.

	It must return True: a handler that returns anything else stops NVDA from running the gesture,
	and so from reacting to the keyboard at all. It runs in NVDA's keyboard thread, so it only notes.
	"""
	global _gestures, _lastGesture
	try:
		import api

		_gestures += 1
		_lastGesture = (_gestures, time.monotonic(), api.getFocusObject())
	except Exception:
		pass
	return True


def isTrayIcon(obj) -> bool:
	"""Whether ``obj`` is in the system tray: a program's icon, the clock, or one of the tray's own buttons."""
	import winUser

	window = obj.windowHandle
	if not window:
		return False
	root = winUser.getAncestor(window, winUser.GA_ROOT)
	rootClass = winUser.getClassName(root) if root else ""
	if rootClass not in TRAY_WINDOWS:
		return False
	if rootClass in HIDDEN_ICONS_WINDOWS:
		return True
	# Windows 11: the tray's icons, the programs' buttons and the Start button are UI Automation elements of one window.
	element = getattr(obj, "UIAElement", None)
	if element is not None:
		try:
			if str(element.cachedClassName or "").startswith(UIA_CLASS_PREFIX):
				return True
		except Exception:
			pass
	# Windows 10: the tray has a window of its own in the taskbar.
	for _ in range(_MOST_WINDOWS):
		if not window or window == root:
			break
		if winUser.getClassName(window) == TRAY_NOTIFY_WINDOW:
			return True
		window = winUser.getAncestor(window, winUser.GA_PARENT)
	return False


def _keyPressedOn(obj) -> tuple | None:
	"""The key press made on ``obj`` a moment ago, when no change was said after it yet; otherwise None."""
	gesture = _lastGesture
	if gesture is None:
		return None
	count, at, focus = gesture
	if count == _saidAfter or focus is not obj or time.monotonic() - at > AFTER_KEY_PRESS:
		return None
	return gesture


def beforeNameChange(obj) -> None:
	"""Before NVDA handles a notice that the name of ``obj`` changed: leave out a system tray icon's own change.

	When ``obj`` is a system tray icon with the focus, and no key pressed on it a moment ago can have
	changed it, the focus object's notes get its new name, so NVDA doesn't say it. Anything else, and
	anything that goes wrong, leaves NVDA to handle the notice as usual.
	"""
	global _saidAfter
	if not _enabled:
		return
	try:
		import api

		if api.getFocusObject() is not obj or not isTrayIcon(obj):
			return
		name = obj.name
		notes = getattr(obj, "_speakObjectPropertiesCache", None)
		notes = notes if isinstance(notes, dict) else {}
		if notes.get("name", _MISSING) == name:
			# NVDA has nothing new to say.
			return
		gesture = _keyPressedOn(obj)
		if gesture is not None:
			_saidAfter = gesture[0]
			_log().debug(f"jawsMigrator: a system tray icon changed after a key press on it, so NVDA says it: {name!r}")
			return
		obj._speakObjectPropertiesCache = {**notes, "name": name}
		_log().debug(f"jawsMigrator: a system tray icon changed by itself, so NVDA doesn't read it again: {name!r}")
	except Exception:
		_failure("could not check a change of a system tray icon")
