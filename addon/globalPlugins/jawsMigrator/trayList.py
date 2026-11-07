# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""The System Tray List add-on's list (NVDA+F11) works as JAWS's list (Insert+F11) does (issue 54).

Enter right-clicks the icon. A tester pressed NVDA+F11, moved to "Volume" in the list of system tray icons and
pressed Enter, and Windows' Quick Settings opened, where JAWS would have opened the icon's menu. NVDA itself has no
list of the tray's icons: NVDA+F11 is the System Tray List add-on (systrayList, 2026.08.24), whose dialog has the
buttons Left Click (Alt+L), Left Double Click (Alt+D) and Right Click (Alt+R), and Left Double Click is its default
button, so Enter in the list double-clicks the icon. JAWS's list, Insert+F11 ("Select a System Tray Icon", in jfw.exe
of JAWS 2027), has the buttons Right Single Click, Left Single Click and Left Double Click with the same letters, and
Right Single Click is its default button (BS_DEFPUSHBUTTON); JAWS's own help for the list (common.jsm, cmsg368_L) says
"To simulate a right single mouse click on the selected item, press ENTER." So in JAWS, Enter on an icon in the list
opens its menu, and Alt+L clicks it.

So when System Tray List shows the tray's icons, its Right Click button is made the default, and Enter in the list
right-clicks the icon, as in JAWS. Alt+L, Alt+D and Alt+R, and Enter on a button you Tab to, still press that button.
The same dialog shows the taskbar's programs when NVDA+F11 is pressed twice, which JAWS's list doesn't; there the
add-on's own default comes back.

A click reaches the icon when the taskbar hides automatically. System Tray List notes where each icon is as it makes
the list, and clicks there. With "Automatically hide the taskbar" on, the hidden taskbar is moved down until 2 pixels
of it show (read from Windows 11 build 26300 at 125%: the taskbar at 1140 to 1200 of a 1200-pixel screen when it
shows, 1198 to 1258 when it hides), and its icons with it, so every button of the dialog clicked the bottom edge of
the screen and missed the icon. A list made while the taskbar showed (after Windows+B, say) missed too: the taskbar
hides once the dialog has the focus, and the click went to the window under the place where the icon had been. Windows
says where the taskbar is when it shows, hidden or not (SHAppBarMessage(ABM_GETTASKBARPOS)), and whether it hides
(ABM_GETSTATE, ABS_AUTOHIDE). So when the taskbar hides automatically and is hidden as System Tray List clicks, or was
hidden as it made the list, the assistant first puts the mouse pointer on the part of the taskbar that shows, as a
mouse user does to bring it up; the taskbar comes up (in about 0.2 seconds there) and stays up while the pointer is on
it, and the click is made where the icon then is: where System Tray List noted it, moved as far as the taskbar moved
since. If the taskbar doesn't come up within 2 seconds, System Tray List clicks where it noted the icon, as before. A
taskbar that doesn't hide, or that shows as the list is made and clicked, is clicked as it always was.

Each works while the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant. Nothing
else the add-on does changes, and without it nothing happens.

What the assistant changes is read from the add-on's own code: its plugin (``globalPlugins.systrayList.GlobalPlugin``)
fills and shows the dialog in ``_createSystrayList`` (the tray's icons) and ``_createTaskList`` (the taskbar's
programs), and keeps it in ``_systrayListDialog``; the dialog's buttons, in the order the add-on makes them, are Left
Click, Left Double Click, Right Click and Cancel, and each calls the module's ``mouseEvents(location, *events)``, which
puts the pointer in the middle of ``location`` and presses the buttons. The buttons are found by that order, so the
add-on's translations don't matter.
"""

from __future__ import annotations

import ctypes
import functools
import sys
from ctypes import wintypes

#: The assistant's settings (state.json) that turn each part on or off.
STATE_KEY = "rightClickInSystrayList"
REVEAL_KEY = "revealHiddenTaskbarForSystrayList"
#: System Tray List's global plugin, as NVDA imports it.
MODULE = "globalPlugins.systrayList"
PLUGIN_CLASS = "GlobalPlugin"
#: Its methods that fill and show the dialog: the tray's icons (NVDA+F11), and the taskbar's programs (pressed twice).
TRAY = "_createSystrayList"
TASKS = "_createTaskList"
#: Its function that clicks: mouseEvents(location, *events).
CLICK = "mouseEvents"
#: Where its plugin keeps the dialog.
DIALOG = "_systrayListDialog"
#: The dialog's buttons other than Cancel, in the order the add-on makes them: Left Click, Left Double Click, Right Click.
BUTTONS = 3
RIGHT_CLICK = 2
#: The taskbar System Tray List reads: the one on the main screen.
TASKBAR = "Shell_TrayWnd"
#: How long the assistant waits for a hidden taskbar to come up, and how often it looks, in seconds.
REVEAL_WAIT = 2.0
REVEAL_POLL = 0.05
#: Marks what the assistant put in the place of the add-on's own, and keeps its own.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorTrayList"
#: Where the dialog keeps the add-on's own default button, once the assistant has changed it.
OWN_DEFAULT = "_jawsMigratorOwnDefault"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
#: Each part: Enter right-clicks, and a click brings up a hidden taskbar first.
_rightClick = False
_reveal = False
#: The failures already logged, once each: {what}.
_failed: set = set()
#: What the assistant put in the place of the add-on's own: [(its class or module, name, the assistant's, its own)].
_replaced: list = []
#: The plugin whose dialog the assistant changed last, to give the dialog its own default back when turned off.
_plugin = None
#: The taskbar and where it was as System Tray List made its list: (window, (left, top, right, bottom)), or None.
_listedAt = None
#: The click waiting for a hidden taskbar to come up: its timer, or None.
_waiting = None
#: Whether the log has said once that Enter in the list right-clicks.
_logged = False


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
	"""Whether Enter in System Tray List's list right-clicks the icon, as in JAWS: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def revealWanted(stateData: dict) -> bool:
	"""Whether System Tray List's click brings up a hidden taskbar first: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(REVEAL_KEY, True))


def register(rightClick: bool = True, reveal: bool = True) -> None:
	"""Have System Tray List's list work as JAWS's, from now on: Enter right-clicks, and a click finds a hidden taskbar."""
	global _enabled, _rightClick, _reveal
	hadRightClick = _rightClick
	_rightClick, _reveal = bool(rightClick), bool(reveal)
	if not (_rightClick or _reveal):
		unregister()
		return
	if hadRightClick and not _rightClick:
		try:
			_ownDefault(_dialogOf(_plugin))
		except Exception:
			_failure("could not give System Tray List's dialog its own default button back")
	if not _reveal:
		_stopWaiting()
	if _enabled:
		# Called again after a migration, a restore or a configuration reload: the add-on may have loaded since.
		_install()
		return
	_enabled = True
	if not _install():
		# NVDA imports the global plugins one after another, and System Tray List may come after the assistant.
		try:
			import wx

			wx.CallAfter(_installIfWanted)
		except Exception:
			pass


def unregister() -> None:
	"""Give System Tray List its own methods and its dialog its own default button back."""
	global _enabled, _plugin, _rightClick, _reveal, _listedAt
	_rightClick = _reveal = False
	if not _enabled:
		return
	_enabled = False
	_stopWaiting()
	_listedAt = None
	plugin, _plugin = _plugin, None
	try:
		_ownDefault(_dialogOf(plugin))
	except Exception:
		_failure("could not give System Tray List's dialog its own default button back")
	for owner, name, installed, original in reversed(_replaced):
		try:
			if vars(owner).get(name) is installed:
				setattr(owner, name, original)
		except Exception:
			pass
	_replaced.clear()


def isRegistered() -> bool:
	return _enabled


def isInstalled() -> bool:
	"""Whether the assistant's versions of both methods are in System Tray List now."""
	pluginClass = _pluginClass(sys.modules.get(MODULE))
	return pluginClass is not None and all(_isOurs(vars(pluginClass).get(name)) for name in (TRAY, TASKS))


def isClickInstalled() -> bool:
	"""Whether the assistant's version of System Tray List's click is in it now."""
	module = sys.modules.get(MODULE)
	return module is not None and _isOurs(vars(module).get(CLICK))


def _installIfWanted() -> None:
	if _enabled:
		_install()


def _pluginClass(module):
	pluginClass = vars(module).get(PLUGIN_CLASS) if module is not None else None
	return pluginClass if isinstance(pluginClass, type) else None


def _isOurs(function) -> bool:
	"""Whether ``function`` is the assistant's version, or wraps it (as another add-on's functools.wraps wrapper would)."""
	for _ in range(_MOST_WRAPPERS):
		if function is None:
			return False
		if getattr(function, MARK, None) is _TOKEN:
			return True
		function = getattr(function, "__wrapped__", None)
	return False


def _put(owner, name, original, installed) -> None:
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, original))


def _install() -> bool:
	"""Put the assistant's versions of the methods and the click in System Tray List, once. True when they are there."""
	module = sys.modules.get(MODULE)
	if module is None:
		# Not installed, turned off, or not loaded yet.
		return False
	try:
		pluginClass = _pluginClass(module)
		if pluginClass is None:
			_failure(f"System Tray List has no {PLUGIN_CLASS} the assistant knows, so its list works as it always has")
			return False
		current = {name: vars(pluginClass).get(name) for name in (TRAY, TASKS)}
		if not all(callable(function) for function in current.values()):
			_failure(f"System Tray List has no {TRAY} and {TASKS} the assistant knows, so its list works as it always has")
			return False
		for name in (TRAY, TASKS):
			if not _isOurs(current[name]):
				_put(pluginClass, name, current[name], _wrapped(current[name], name == TRAY))
		click = vars(module).get(CLICK)
		if not callable(click):
			_failure(f"System Tray List has no {CLICK} the assistant knows, so its clicks don't bring up a hidden taskbar")
		elif not _isOurs(click):
			_put(module, CLICK, click, _wrappedClick(click))
		_log().debug(f"jawsMigrator: System Tray List's list works as JAWS's list ({MODULE}.{PLUGIN_CLASS}.{TRAY}, {MODULE}.{CLICK})")
		return True
	except Exception:
		_failure("can't have System Tray List's list work as JAWS's list")
		return False


def _dialogOf(plugin):
	"""The dialog System Tray List's plugin shows, while it is there (wx's deleted windows are false), or None."""
	if plugin is None:
		return None
	dialog = getattr(plugin, DIALOG, None)
	try:
		return dialog if dialog else None
	except Exception:
		return None


def _clickButtons(dialog) -> list:
	"""The dialog's buttons other than Cancel, in the order the add-on made them."""
	import wx

	return [child for child in dialog.GetChildren() if isinstance(child, wx.Button) and child.GetId() != wx.ID_CANCEL]


def _note() -> None:
	global _logged
	if _logged:
		return
	_logged = True
	_log().debug(
		"jawsMigrator: Enter in System Tray List's list right-clicks the icon, as Enter in JAWS's list (Insert+F11) does: "
		"its default button is Right Single Click; Alt+L still clicks and Alt+D double-clicks",
	)


def _rightClickDefault(dialog) -> None:
	"""The dialog's Right Click button made its default, so Enter in the list right-clicks; its own default is kept."""
	if dialog is None:
		return
	buttons = _clickButtons(dialog)
	if len(buttons) != BUTTONS:
		_failure(f"System Tray List's dialog has {len(buttons)} buttons, not the {BUTTONS} the assistant knows, so Enter does what it always has")
		return
	if getattr(dialog, OWN_DEFAULT, None) is None:
		setattr(dialog, OWN_DEFAULT, dialog.GetDefaultItem())
	buttons[RIGHT_CLICK].SetDefault()
	_note()


def _ownDefault(dialog) -> None:
	"""The dialog's own default button back, where the assistant changed it."""
	if dialog is None:
		return
	own = getattr(dialog, OWN_DEFAULT, None)
	if own is None:
		return
	setattr(dialog, OWN_DEFAULT, None)
	if own:
		own.SetDefault()


def _wrapped(original, tray: bool):
	"""System Tray List's method that fills and shows the dialog: where the taskbar is noted first, and the default button
	the list should have chosen after."""

	@functools.wraps(original)
	def create(self, *args, **kwargs):
		global _plugin
		if _enabled and _reveal:
			_noteTaskbar()
		result = original(self, *args, **kwargs)
		if _enabled:
			try:
				_plugin = self
				dialog = _dialogOf(self)
				if tray and _rightClick:
					_rightClickDefault(dialog)
				else:
					_ownDefault(dialog)
			except Exception:
				_failure("could not choose the default button of System Tray List's dialog, so Enter does what it always has")
		return result

	setattr(create, MARK, _TOKEN)
	setattr(create, ORIGINAL, original)
	return create


class _Win32:
	"""What the assistant asks Windows about the taskbar, with the functions' types given."""

	class APPBARDATA(ctypes.Structure):
		_fields_ = [
			("cbSize", wintypes.DWORD),
			("hWnd", wintypes.HWND),
			("uCallbackMessage", wintypes.UINT),
			("uEdge", wintypes.UINT),
			("rc", wintypes.RECT),
			("lParam", wintypes.LPARAM),
		]

	ABM_GETSTATE = 4
	ABM_GETTASKBARPOS = 5
	ABS_AUTOHIDE = 1

	def __init__(self):
		user32 = ctypes.WinDLL("user32")
		shell32 = ctypes.WinDLL("shell32")
		self._FindWindow = user32.FindWindowW
		self._FindWindow.restype = wintypes.HWND
		self._FindWindow.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
		self._GetWindowRect = user32.GetWindowRect
		self._GetWindowRect.restype = wintypes.BOOL
		self._GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
		self._SHAppBarMessage = shell32.SHAppBarMessage
		self._SHAppBarMessage.restype = ctypes.c_size_t
		self._SHAppBarMessage.argtypes = (wintypes.DWORD, ctypes.POINTER(self.APPBARDATA))

	def taskbar(self) -> int:
		return self._FindWindow(TASKBAR, None) or 0

	def windowRect(self, window) -> tuple | None:
		rect = wintypes.RECT()
		if not self._GetWindowRect(window, ctypes.byref(rect)):
			return None
		return rect.left, rect.top, rect.right, rect.bottom

	def _appBar(self, message, window):
		data = self.APPBARDATA()
		data.cbSize = ctypes.sizeof(data)
		data.hWnd = window
		return self._SHAppBarMessage(message, ctypes.byref(data)), data

	def hides(self, window) -> bool:
		"""Whether the taskbar hides automatically."""
		state, data = self._appBar(self.ABM_GETSTATE, window)
		return bool(state & self.ABS_AUTOHIDE)

	def shownRect(self, window) -> tuple | None:
		"""Where the taskbar is when it shows, whether it is hidden now or not."""
		done, data = self._appBar(self.ABM_GETTASKBARPOS, window)
		if not done:
			return None
		return data.rc.left, data.rc.top, data.rc.right, data.rc.bottom


_win32 = None


def _win():
	global _win32
	if _win32 is None:
		_win32 = _Win32()
	return _win32


def _noteTaskbar() -> None:
	"""Where the taskbar is as System Tray List makes its list, for the click to find the icons later."""
	global _listedAt
	_listedAt = None
	try:
		win32 = _win()
		window = win32.taskbar()
		rect = win32.windowRect(window) if window else None
		if rect is not None:
			_listedAt = (window, rect)
	except Exception:
		_failure("could not tell where the taskbar is, so System Tray List's clicks don't bring up a hidden taskbar")


def _plan(location):
	"""For a click on ``location``, as System Tray List noted it: (where the icon is when the taskbar shows, the taskbar,
	where it shows), when the taskbar hides automatically and was hidden as the list was made, or is hidden now; else
	None, and the click is made as it was."""
	if _listedAt is None or not location:
		return None
	window, listed = _listedAt
	win32 = _win()
	if win32.taskbar() != window or not win32.hides(window):
		return None
	shown = win32.shownRect(window)
	if shown is None:
		return None
	if (listed[2] - listed[0], listed[3] - listed[1]) != (shown[2] - shown[0], shown[3] - shown[1]):
		# Not the same taskbar moved: it changed size since the list was made.
		return None
	moveX, moveY = shown[0] - listed[0], shown[1] - listed[1]
	if not (moveX or moveY) and win32.windowRect(window) == shown:
		# The list was made while the taskbar showed, and it shows now.
		return None
	left, top, width, height = location
	return (left + moveX, top + moveY, width, height), window, shown


def _showing(now, shown) -> tuple | None:
	"""The part of the taskbar at ``now`` that is on the screen, where it shows: (left, top, right, bottom), or None."""
	left, top = max(now[0], shown[0]), max(now[1], shown[1])
	right, bottom = min(now[2], shown[2]), min(now[3], shown[3])
	if right <= left or bottom <= top:
		return None
	return left, top, right, bottom


def _clamp(value, low, high):
	return max(low, min(value, high))


def _movePointer(point) -> None:
	import mouseHandler
	import winUser

	# NVDA doesn't follow the pointer the assistant moves (mouse tracking would say what is under it).
	with mouseHandler.ignoreInjection():
		winUser.setCursorPos(*point)


def _later(seconds: float, function):
	import wx

	return wx.CallLater(int(seconds * 1000), function)


def _stopWaiting() -> None:
	global _waiting
	timer, _waiting = _waiting, None
	if timer is not None:
		try:
			timer.Stop()
		except Exception:
			pass


def _clickShown(original, location, plan, events):
	"""The click on an icon of a hidden taskbar: the taskbar brought up with the pointer, then the click where the icon is.
	Returns where to click now, or None when the click waits for the taskbar."""
	global _waiting
	_stopWaiting()
	shifted, window, shown = plan
	win32 = _win()
	now = win32.windowRect(window)
	if now == shown:
		# Up already: the pointer is on it, or it is coming up.
		return shifted
	strip = _showing(now, shown) if now is not None else None
	if strip is None:
		return location
	left, top, width, height = shifted
	# The pointer on the part of the taskbar that shows, as near the icon as it can be: the taskbar comes up.
	_movePointer((_clamp(left + width // 2, strip[0], strip[2] - 1), _clamp(top + height // 2, strip[1], strip[3] - 1)))
	_log().debug(f"jawsMigrator: the taskbar hides automatically and is hidden, so it is brought up for System Tray List to click at {shifted}")
	tries = [int(REVEAL_WAIT / REVEAL_POLL)]

	def look():
		global _waiting
		_waiting = None
		try:
			if win32.windowRect(window) == shown:
				original(shifted, *events)
				return
			tries[0] -= 1
			if tries[0] > 0:
				_waiting = _later(REVEAL_POLL, look)
				return
			_log().debug("jawsMigrator: the hidden taskbar didn't come up, so System Tray List clicks where it noted the icon")
			original(location, *events)
		except Exception:
			_failure("could not click an icon of the hidden taskbar for System Tray List")

	_waiting = _later(REVEAL_POLL, look)
	return None


def _wrappedClick(original):
	"""System Tray List's click: on an icon of a hidden taskbar, the taskbar is brought up first."""

	@functools.wraps(original)
	def mouseEvents(location, *events):
		if _enabled and _reveal:
			try:
				plan = _plan(location)
			except Exception:
				_failure("could not tell whether the taskbar is hidden, so System Tray List clicks where it noted the icon")
				plan = None
			if plan is not None:
				try:
					location = _clickShown(original, location, plan, events)
				except Exception:
					_failure("could not bring up the hidden taskbar for System Tray List, so it clicks where it noted the icon")
				if location is None:
					# The click waits for the taskbar to come up.
					return None
		# System Tray List's own click, once, outside the assistant's handling of its own failures.
		return original(location, *events)

	setattr(mouseEvents, MARK, _TOKEN)
	setattr(mouseEvents, ORIGINAL, original)
	return mouseEvents
