# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""Enter on a program's system tray icon clicks it with the mouse, so every program answers it (issue 52).

A tester found that Enter on a system tray icon doesn't always click it. Enter there isn't a click: Windows sends
the program a notice of its own for the keyboard. A program that asked for the current way of being told
(NOTIFYICON_VERSION_4) gets NIN_KEYSELECT for Enter and Space, where a click with the mouse gives it NIN_SELECT and
the mouse button's messages (Shell_NotifyIcon, Remarks). Many programs answer only the mouse, so Enter on their icon
does nothing, while it works on others. NVDA passes Enter on to Windows (its explorer app module has nothing for the
tray's keys), and so does JAWS's own script for the taskbar (explorer.jss); JAWS users click an icon through
JAWS's list of the system tray icons, Insert+F11, which clicks it with the mouse.

So Enter and the keypad's Enter on a program's icon in the system tray, the taskbar's or the hidden icons', put the
mouse pointer on the middle of the icon and click it with the primary button, as a mouse user does, and the pointer
goes back where it was a moment later. Pressed twice quickly, it is a double click, which some programs want. Space
is left to Windows, so Windows' own keyboard notice can still be had. Windows 11's own buttons in the tray (Show Hidden
Icons, the clock, network, volume and battery) answer Enter themselves and are left alone; in Windows 10, network,
volume and battery are icons in the tray's toolbar like the programs', and are clicked like them, and the clock and Show
Hidden Icons are left alone. When the icon isn't on the screen,
or something covers it, Enter goes on to Windows as before. It works while the assistant runs, unless it is turned
off in NVDA's Settings, JAWS Migration Assistant.

What a program's icon is was read from Windows 11 (build 26300) with UI Automation: each icon is a button of class
SystemTray.NormalButton whose automation ID is NotifyItemIcon; Show Hidden Icons has the same class, and it and the
tray's other buttons have the automation ID SystemTrayIcon. In Windows 10 the icons are the buttons of the tray's
toolbars (ToolbarWindow32), Windows' own network, volume and battery icons among them, and the clock and Show Hidden Icons
are windows of their own.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from . import trayChanges

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "clickTrayIconOnEnter"
#: The UI Automation ID of a program's icon in Windows 11's system tray.
PROGRAM_ICON_ID = "NotifyItemIcon"
#: Windows 10's toolbars of icons in the system tray and in the hidden icons.
WINDOWS_10_ICONS = "ToolbarWindow32"
#: The keys that click the icon.
KEYS = ("kb:enter", "kb:numpadEnter")
#: How long the pointer stays on the icon after a click, in seconds: long enough for a second Enter to make it a
#: double click, and for the program to have read where the pointer is.
POINTER_STAYS = 1.5

_enabled = False
#: The failures already logged, once each: {what}.
_failed: set = set()
_overlay = None
_overlayLock = threading.Lock()
#: The pointer's place before the first click, and the place it was put; or None.
_away: tuple | None = None
#: The icon clicked last, while the pointer is on it.
_clicked = None
_timer = None


def _log():
	from logHandler import log

	return log


def _failure(what: str) -> None:
	if what in _failed:
		return
	_failed.add(what)
	try:
		_log().debugWarning(f"jawsMigrator: {what}", exc_info=True)
	except Exception:
		pass


def wanted(stateData: dict) -> bool:
	"""Whether Enter on a program's system tray icon clicks it: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	global _enabled
	_enabled = True


def unregister() -> None:
	global _enabled
	_enabled = False
	pointerBack()


def isRegistered() -> bool:
	return _enabled


def _isButton(obj) -> bool:
	try:
		from controlTypes import Role

		return obj.role == Role.BUTTON
	except Exception:
		return False


def isProgramIcon(obj) -> bool:
	"""Whether ``obj`` is a program's icon in the system tray, not one of the tray's own buttons."""
	if not trayChanges.isTrayIcon(obj):
		return False
	if getattr(obj, "UIAElement", None) is not None:
		# Windows 11.
		try:
			return str(obj.UIAAutomationId or "") == PROGRAM_ICON_ID
		except Exception:
			return False
	import winUser

	# Windows 10.
	return winUser.getClassName(obj.windowHandle) == WINDOWS_10_ICONS and _isButton(obj)


def _middle(obj) -> tuple | None:
	"""The middle of ``obj`` on the screen, or None when it has no place there."""
	location = obj.location
	if not location:
		return None
	left, top, width, height = location
	if width <= 0 or height <= 0:
		return None
	return left + width // 2, top + height // 2


class _Win32:
	"""WindowFromPoint, which NVDA's winUser doesn't have, with its types given."""

	def __init__(self):
		user32 = ctypes.WinDLL("user32")
		self._WindowFromPoint = user32.WindowFromPoint
		self._WindowFromPoint.restype = wintypes.HWND
		self._WindowFromPoint.argtypes = (wintypes.POINT,)

	def windowAt(self, x: int, y: int) -> int:
		return self._WindowFromPoint(wintypes.POINT(x, y)) or 0


_win32 = None


def _windowAt(x: int, y: int) -> int:
	global _win32
	if _win32 is None:
		_win32 = _Win32()
	return _win32.windowAt(x, y)


def _shows(obj, point) -> bool:
	"""Whether a click at ``point`` lands on the tray ``obj`` is in: the window there is in the same top window."""
	import winUser

	root = winUser.getAncestor(obj.windowHandle, winUser.GA_ROOT)
	there = _windowAt(*point)
	return bool(root) and bool(there) and winUser.getAncestor(there, winUser.GA_ROOT) == root


def _pointer() -> tuple:
	import winUser

	place = winUser.getCursorPos()
	if hasattr(place, "x"):
		return place.x, place.y
	return tuple(place)


def _movePointer(point) -> None:
	import mouseHandler
	import winUser

	# NVDA doesn't follow the pointer the assistant moves (mouse tracking would say what is under it).
	with mouseHandler.ignoreInjection():
		winUser.setCursorPos(*point)


def _later(seconds: float, function):
	import wx

	return wx.CallLater(int(seconds * 1000), function)


def _clickAt(point) -> None:
	"""The pointer on ``point``, a click of the primary button there, and the pointer back where it was a moment later."""
	global _away, _timer
	import mouseHandler

	now = _pointer()
	# A second Enter while the pointer is still on the icon: it goes back, later, where it was before the first.
	before = _away[0] if _away is not None and now == tuple(_away[1]) else now
	# Noted before the pointer moves, so that it goes back even when the click fails.
	_away = (before, tuple(point))
	if _timer is not None:
		try:
			_timer.Stop()
		except Exception:
			pass
		_timer = None
	try:
		_movePointer(point)
		# The primary button: the right one when the buttons are swapped. NVDA doesn't follow the click either.
		mouseHandler.doPrimaryClick()
	except Exception:
		pointerBack()
		raise
	try:
		_timer = _later(POINTER_STAYS, pointerBack)
	except Exception:
		# The click is done; only the pointer's return is lost, so it goes back now.
		pointerBack()
		_failure("could not wait to put the mouse pointer back after clicking a system tray icon")


def pointerBack() -> None:
	"""The pointer back where it was before the click, unless it has been moved since."""
	global _away, _timer, _clicked
	away, _away = _away, None
	_clicked = None
	timer, _timer = _timer, None
	if timer is not None:
		try:
			timer.Stop()
		except Exception:
			pass
	if away is None:
		return
	before, put = away
	try:
		if _pointer() == tuple(put):
			_movePointer(before)
	except Exception:
		_failure("could not put the mouse pointer back after clicking a system tray icon")


def focusMoved(obj) -> None:
	"""The focus moved to ``obj``: the pointer goes back at once when ``obj`` isn't the icon it is on, so that Windows 10's
	tray doesn't move the focus back to the icon under the pointer (NVDA's explorer app module, NotificationArea). NVDA makes
	a new object each time the focus comes to a control, so the icon is compared as NVDA compares objects (==): the focus
	coming back to the icon leaves the pointer on it, for a double click."""
	if _away is None:
		return
	try:
		if _clicked is None or obj != _clicked:
			pointerBack()
	except Exception:
		_failure("could not put the mouse pointer back when the focus moved")


def _passOn(gesture, why: str) -> None:
	_log().debug(f"jawsMigrator: Enter on a system tray icon goes on to Windows: {why}")
	gesture.send()


def click(obj, gesture) -> None:
	"""The script of Enter on a program's system tray icon: a click with the mouse, or the key on to Windows."""
	global _clicked
	try:
		import api

		if not _enabled:
			_passOn(gesture, "turned off")
			return
		if api.getFocusObject() is not obj:
			_passOn(gesture, "the focus moved")
			return
		point = _middle(obj)
		if point is None:
			_passOn(gesture, "the icon has no place on the screen")
			return
		if not _shows(obj, point):
			_passOn(gesture, f"something else is on the screen at {point}")
			return
		_clickAt(point)
		_clicked = obj
	except Exception:
		_failure("could not click a system tray icon, so Enter goes on to Windows")
		try:
			gesture.send()
		except Exception:
			pass
		return
	# Clicked: Windows doesn't get Enter as well, whatever happens from here, or the program would get both.
	try:
		_log().debug(f"jawsMigrator: Enter on the system tray icon {obj.name!r} clicks it at {point}, as some programs answer only the mouse")
	except Exception:
		pass


def overlayClass():
	"""The class of a program's system tray icon: Enter clicks it."""
	with _overlayLock:
		return _makeOverlay()


def _makeOverlay():
	global _overlay
	# NVDA makes objects in its UI Automation thread too, so the class is made under a lock: one class, for every icon.
	if _overlay is None:
		from NVDAObjects import NVDAObject

		class ProgramTrayIcon(NVDAObject):
			"""A program's icon in the system tray: Enter and the keypad's Enter click it with the mouse."""

			def script_clickTrayIcon(self, gesture):
				# No description, as NVDA's scripts that may send the key on have none.
				click(self, gesture)

			__gestures = {key: "clickTrayIcon" for key in KEYS}

		_overlay = ProgramTrayIcon
	return _overlay


def chooseOverlay(obj, clsList) -> None:
	"""NVDA's chooseNVDAObjectOverlayClasses: a program's system tray icon gets the class above."""
	if not _enabled:
		return
	try:
		if isProgramIcon(obj):
			clsList.insert(0, overlayClass())
	except Exception:
		_failure("could not tell whether an object is a program's system tray icon, so Enter on it goes on to Windows")
