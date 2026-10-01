# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""NVDA started with its desktop shortcut's key comes up in the window you were in, as JAWS does.

A tester heard "Copilot pinned" when NVDA started. That is the name Windows 11 gives the first button of its
taskbar when Copilot is pinned there, and in the tester's log the focus was already on that button when NVDA
started, before any add-on ran: NVDA says where the focus is as it starts (``core._setInitialFocus``). Windows
puts the focus on the taskbar whenever a desktop shortcut's key starts a program, and the key of NVDA's desktop
shortcut is Control+Alt+N, so starting or restarting NVDA with it takes the focus away from the window you were
in (nvaccess/nvda#13028, open since 2021, and #18897: Windows 10 says "Taskbar", Windows 11 names a taskbar button
or the notification area). NVDA's own restart (NVDA+Q, or after installing an add-on) leaves the focus where it
was. JAWS, started with its own desktop shortcut's key, Control+Alt+J, puts the focus back on the window that was
active before (#13028).

So, as NVDA starts, before it says where the focus is: when the taskbar has the focus, the window you were in
gets it back, the one Alt+Tab goes back to: the top window that isn't minimized, hidden, on another virtual
desktop, or one of Windows' own (the taskbar, Start, search) or NVDA's. NVDA then says that window and its focus,
as after Alt+Tab. When there is no such window, because none is open or all are minimized, the desktop gets the
focus, as that is where you were. It happens once, as NVDA starts: when NVDA reloads its plugins, or at any other
time, the focus stays on the taskbar when you put it there. It works unless it is turned off in NVDA's Settings,
JAWS Migration Assistant.

NVDA then reads the focus there as it reads that program. A tester's NVDA said nothing he typed in a message box in
Edge after it started this way. NVDA reads Edge's web pages through IAccessible2, but it can tell whether it reads a
program through UI Automation only once its helper is in that program (UIAHandler._isUIAWindowHelper). Windows puts the
helper in a program as the program comes to the front, and NVDA takes the helper in on its main thread, which starts
NVDA's plugins first. Edge's UI Automation focus event came while they still started, so NVDA took Edge's focus through
UI Automation, and later, while he typed in the box, it had the page itself as the focus. NVDA echoes typed characters
"only in edit controls" (speech.isFocusEditable), and a page is read only. In the tester's logs, NVDA took Edge through
UI Automation at four of the five starts that went back to Edge, and through IAccessible2 at every other time. So while
NVDA starts, a UI Automation focus event of the program the focus went back to is left out, and NVDA finds the focus
itself once it has started (core._setInitialFocus), as for a window that was in front when it started. Whenever NVDA
takes the focus there through UI Automation, it asks again how it reads that window, and takes the focus as it reads
it. When NVDA's helper comes into the program only after that, NVDA takes the focus there again once it has.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "backFromTaskbarAtStart"
#: The taskbar, and the taskbar on another monitor: the window a desktop shortcut's key leaves the focus in.
TASKBAR_WINDOWS = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd")
#: The desktop's icons are in this window, in Progman or in one of the WorkerW windows behind it.
DESKTOP_VIEW = "SHELLDLL_DefView"
DESKTOP_WORKER = "WorkerW"
#: Windows of Windows itself, never the one you were in: the taskbar and the desktop, the hidden icons, Start,
#: search and Windows 11's other flyouts, Task View, the taskbar's thumbnails and the input switcher.
SHELL_WINDOWS = TASKBAR_WINDOWS + (
	"Progman",
	DESKTOP_WORKER,
	"NotifyIconOverflowWindow",
	"TopLevelWindowForOverflowXamlIsland",
	"XamlExplorerHostIslandWindow",
	"Windows.UI.Core.CoreWindow",
	"ForegroundStaging",
	"MultitaskingViewFrame",
	"TaskListThumbnailWnd",
	"Shell_InputSwitchTopLevelWindow",
	"EdgeUiInputTopWndClass",
)
GA_ROOTOWNER = 3
GW_HWNDNEXT = 2
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
DWMWA_CLOAKED = 14
#: No more windows than this are looked at: Windows can hand back a window twice while windows close.
_MOST_WINDOWS = 4096
#: For how long after it went back to a window NVDA checks how it reads the focus there, in seconds: NVDA takes a few
#: seconds more to start, and its helper can come into the program after that.
SETTLE_SECONDS = 30
#: How often it checks once NVDA has started, in milliseconds.
CHECK_MS = 250

_failed = False
#: The process of the window NVDA went back to as it started, until NVDA reads the focus there as it reads that
#: program; 0 otherwise.
_process = 0
_until = 0.0
_redirecting = False
_heldLogged = False
_overlay = None
_timer = None


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
	"""Whether NVDA started on the taskbar goes back to the window you were in: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


class Win32:
	"""The Windows functions this needs, on a copy of user32 of its own, with their types given."""

	def __init__(self):
		user32 = ctypes.WinDLL("user32", use_last_error=True)
		self._dwmapi = ctypes.WinDLL("dwmapi")
		HWND = wintypes.HWND

		def function(dll, name, restype, *argtypes):
			found = getattr(dll, name)
			found.restype = restype
			found.argtypes = argtypes
			return found

		self._GetForegroundWindow = function(user32, "GetForegroundWindow", HWND)
		self._SetForegroundWindow = function(user32, "SetForegroundWindow", wintypes.BOOL, HWND)
		self._GetTopWindow = function(user32, "GetTopWindow", HWND, HWND)
		self._GetWindow = function(user32, "GetWindow", HWND, HWND, wintypes.UINT)
		self._GetAncestor = function(user32, "GetAncestor", HWND, HWND, wintypes.UINT)
		self._GetLastActivePopup = function(user32, "GetLastActivePopup", HWND, HWND)
		self._IsWindowVisible = function(user32, "IsWindowVisible", wintypes.BOOL, HWND)
		self._IsWindowEnabled = function(user32, "IsWindowEnabled", wintypes.BOOL, HWND)
		self._IsIconic = function(user32, "IsIconic", wintypes.BOOL, HWND)
		self._GetShellWindow = function(user32, "GetShellWindow", HWND)
		self._FindWindowEx = function(user32, "FindWindowExW", HWND, HWND, HWND, wintypes.LPCWSTR, wintypes.LPCWSTR)
		self._GetClassName = function(user32, "GetClassNameW", ctypes.c_int, HWND, wintypes.LPWSTR, ctypes.c_int)
		self._GetWindowTextLength = function(user32, "GetWindowTextLengthW", ctypes.c_int, HWND)
		self._GetWindowRect = function(user32, "GetWindowRect", wintypes.BOOL, HWND, ctypes.POINTER(wintypes.RECT))
		self._GetWindowThreadProcessId = function(
			user32, "GetWindowThreadProcessId", wintypes.DWORD, HWND, ctypes.POINTER(wintypes.DWORD)
		)
		longPtr = "GetWindowLongPtrW" if ctypes.sizeof(ctypes.c_void_p) == 8 else "GetWindowLongW"
		self._GetWindowLong = function(user32, longPtr, ctypes.c_ssize_t, HWND, ctypes.c_int)
		self._DwmGetWindowAttribute = function(
			self._dwmapi, "DwmGetWindowAttribute", ctypes.c_long, HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
		)

	def foreground(self) -> int:
		return self._GetForegroundWindow() or 0

	def setForeground(self, window: int) -> bool:
		return bool(self._SetForegroundWindow(window))

	def zOrder(self):
		"""The top-level windows, from the top of the screen's order down."""
		window = self._GetTopWindow(None)
		for _ in range(_MOST_WINDOWS):
			if not window:
				return
			yield window
			window = self._GetWindow(window, GW_HWNDNEXT)

	def className(self, window: int) -> str:
		buffer = ctypes.create_unicode_buffer(256)
		self._GetClassName(window, buffer, 256)
		return buffer.value

	def processId(self, window: int) -> int:
		process = wintypes.DWORD()
		self._GetWindowThreadProcessId(window, ctypes.byref(process))
		return process.value

	def isVisible(self, window: int) -> bool:
		return bool(self._IsWindowVisible(window))

	def isEnabled(self, window: int) -> bool:
		return bool(self._IsWindowEnabled(window))

	def isMinimized(self, window: int) -> bool:
		return bool(self._IsIconic(window))

	def isCloaked(self, window: int) -> bool:
		"""Whether Windows keeps the window out of sight: on another virtual desktop, or a suspended Store app's."""
		cloaked = wintypes.DWORD()
		if self._DwmGetWindowAttribute(window, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) != 0:
			return False
		return bool(cloaked.value)

	def extendedStyle(self, window: int) -> int:
		return self._GetWindowLong(window, GWL_EXSTYLE) or 0

	def hasTitle(self, window: int) -> bool:
		return self._GetWindowTextLength(window) > 0

	def hasSize(self, window: int) -> bool:
		rect = wintypes.RECT()
		if not self._GetWindowRect(window, ctypes.byref(rect)):
			return False
		return rect.right > rect.left and rect.bottom > rect.top

	def rootOwner(self, window: int) -> int:
		return self._GetAncestor(window, GA_ROOTOWNER) or 0

	def lastActivePopup(self, window: int) -> int:
		return self._GetLastActivePopup(window) or 0

	def shellWindow(self) -> int:
		return self._GetShellWindow() or 0

	def child(self, parent: int, className: str) -> int:
		return self._FindWindowEx(parent, None, className, None) or 0

	def topLevel(self, className: str):
		"""The top-level windows of a class, one after another."""
		window = None
		for _ in range(_MOST_WINDOWS):
			window = self._FindWindowEx(None, window, className, None)
			if not window:
				return
			yield window


def isOnTaskbar(windows) -> bool:
	"""Whether the taskbar has the focus: a button on it, or its notification area."""
	foreground = windows.foreground()
	return bool(foreground) and windows.className(foreground) in TASKBAR_WINDOWS


def canBeYours(windows, window: int, nvdaProcess: int) -> bool:
	"""Whether ``window`` can be one you were working in: a program's window you can see and use, as Alt+Tab lists."""
	if not window or not windows.isVisible(window) or windows.isMinimized(window) or not windows.isEnabled(window):
		return False
	if windows.className(window) in SHELL_WINDOWS or windows.processId(window) == nvdaProcess:
		return False
	style = windows.extendedStyle(window)
	if style & WS_EX_NOACTIVATE or (style & WS_EX_TOOLWINDOW and not style & WS_EX_APPWINDOW):
		return False
	return windows.hasTitle(window) and windows.hasSize(window) and not windows.isCloaked(window)


def windowYouWereIn(windows, nvdaProcess: int) -> int:
	"""The window Alt+Tab goes back to from the taskbar, or 0 when there is none.

	Windows keeps its windows in the order they were last used, the one in use on top. A window that belongs to
	another one, such as a Find dialog, is kept above it even when you went back to the main window after it,
	so for each program the window that had the focus last in it is the one chosen (GetLastActivePopup).
	"""
	for window in windows.zOrder():
		if not canBeYours(windows, window, nvdaProcess):
			continue
		owner = windows.rootOwner(window) or window
		if owner != window and windows.isMinimized(owner):
			continue
		last = windows.lastActivePopup(owner)
		if last and last != window and canBeYours(windows, last, nvdaProcess):
			return last
		return window
	return 0


def desktop(windows) -> int:
	"""The desktop's window: the one that holds its icons, Progman or a WorkerW behind it; 0 when there is none."""
	shell = windows.shellWindow()
	if shell and windows.child(shell, DESKTOP_VIEW):
		return shell
	for worker in windows.topLevel(DESKTOP_WORKER):
		if windows.child(worker, DESKTOP_VIEW):
			return worker
	return shell


def nvdaIsStarting() -> bool:
	"""Whether NVDA is starting, not reloading its plugins: NVDA marks its start finished after the plugins start."""
	try:
		import NVDAState

		return not NVDAState._TrackNVDAInitialization.isInitializationComplete()
	except Exception:
		return False


def atStart(windows=None) -> int:
	"""As NVDA starts, when the taskbar has the focus: give it back to the window you were in, or the desktop.

	The window that got the focus, or 0 when nothing changed. NVDA hasn't said where the focus is yet: it does that
	after its plugins start, and says the window you are back in.
	"""
	try:
		if not nvdaIsStarting():
			return 0
		import globalVars

		windows = windows or Win32()
		if not isOnTaskbar(windows):
			return 0
		taskbar = windows.className(windows.foreground())
		target = windowYouWereIn(windows, globalVars.appPid)
		where = "the window you were in"
		if not target:
			target = desktop(windows)
			where = "the desktop, as no window is open"
		if not target:
			_log().info("jawsMigrator: NVDA started with the focus on the taskbar, and there is no window or desktop to go back to")
			return 0
		if not windows.setForeground(target):
			_log().info(f"jawsMigrator: NVDA started with the focus on the taskbar; Windows didn't let it go back to {where} ({windows.className(target)})")
			return 0
		_log().info(
			f"jawsMigrator: NVDA started with the focus on the taskbar ({taskbar}), as its desktop shortcut's key leaves it, "
			f"so it goes back to {where} ({windows.className(target)}), as JAWS does"
		)
		_follow(windows.processId(target))
		return target
	except Exception:
		_failure("could not give the focus back to the window you were in, as NVDA started with it on the taskbar")
		return 0


# -- NVDA reads the focus there as it reads that program --------------------------------------------------------------


def _follow(process: int) -> None:
	"""From now on, NVDA's focus in ``process``, the program NVDA went back to, is checked (see heldBack and redirect)."""
	global _process, _until, _heldLogged
	_process = process
	_until = time.monotonic() + SETTLE_SECONDS
	_heldLogged = False


def isFollowing() -> bool:
	return bool(_process)


def _isUIA(obj) -> bool:
	from NVDAObjects.UIA import UIA

	return isinstance(obj, UIA)


def heldBack(obj) -> bool:
	"""Whether NVDA leaves out this UI Automation focus event: one of the program NVDA went back to, while NVDA starts.

	NVDA can't tell yet whether it reads that program through UI Automation, and would take the focus through it from any
	program that has it, such as Edge, whose web pages NVDA reads through IAccessible2. NVDA finds the focus itself once
	it has started (core._setInitialFocus), as for a window that was in front when it started.
	"""
	global _heldLogged
	if not _process or not nvdaIsStarting():
		return False
	try:
		if obj.processID != _process:
			return False
	except Exception:
		return False
	if not _heldLogged:
		_heldLogged = True
		try:
			_log().debug(
				"jawsMigrator: NVDA doesn't take the focus in the window it went back to from UI Automation while it starts, "
				"before it can tell how it reads that program; it finds the focus there once it has started"
			)
		except Exception:
			pass
	return True


def redirect(obj):
	"""The focus as NVDA reads the program it went back to, when NVDA takes ``obj``, a UI Automation object there.

	NVDA asks again whether it reads obj's window through UI Automation: its answer from before its helper was in the
	program is forgotten (NVDA keeps an answer for half a second, UIAHandler.isUIAWindow). When NVDA doesn't read the
	window through UI Automation, the focus as NVDA gets it from Windows now (api.getDesktopObject().objectWithFocus()).
	None when NVDA reads the window through UI Automation, or obj isn't in that program.
	"""
	global _process, _redirecting
	if not _process or _redirecting or threading.current_thread() is not threading.main_thread():
		return None
	_redirecting = True
	try:
		if obj.processID != _process:
			return None
		import api
		import UIAHandler

		handler = UIAHandler.handler
		window = obj.windowHandle
		if handler is None or not window:
			return None
		handler.UIAWindowHandleCache.pop(window, None)
		if handler.isUIAWindow(window):
			return None
		focus = api.getDesktopObject().objectWithFocus()
		if focus is None or _isUIA(focus):
			return None
		_process = 0
		try:
			program = obj.appModule.appName
		except Exception:
			program = "the program"
		_log().info(
			f"jawsMigrator: NVDA takes the focus in {program}, where it went back to as it started, as it reads {program} "
			f"({getattr(focus, 'APIClass', type(focus)).__name__}), not through UI Automation as before its helper was in {program}"
		)
		return focus
	except Exception:
		_failure("could not check how NVDA reads the focus in the window it went back to")
		return None
	finally:
		_redirecting = False


def overlayClass():
	"""The class of a UI Automation object of the program NVDA went back to, while NVDA settles on the focus there."""
	global _overlay
	if _overlay is None:
		from NVDAObjects.UIA import UIA

		class BackFromTaskbarUIA(UIA):
			"""NVDA takes the focus here as it reads this program, not as it could before its helper was in it."""

			_cache_shouldAllowUIAFocusEvent = False
			_cache_focusRedirect = False
			#: The focus as NVDA reads the program, once taken for this object: NVDA asks for focusRedirect twice.
			_takenAs = None

			def _get_shouldAllowUIAFocusEvent(self):
				if heldBack(self):
					return False
				return super().shouldAllowUIAFocusEvent

			def _get_focusRedirect(self):
				other = super().focusRedirect
				if other:
					return other
				if self._takenAs is None:
					self._takenAs = redirect(self)
				return self._takenAs

		_overlay = BackFromTaskbarUIA
	return _overlay


def chooseOverlay(obj, clsList) -> None:
	"""NVDA's chooseNVDAObjectOverlayClasses: a UI Automation object of the program NVDA went back to gets the class
	above, until NVDA reads the focus there as it reads that program."""
	if not _process:
		return
	try:
		if _isUIA(obj) and obj.processID == _process:
			clsList.insert(0, overlayClass())
	except Exception:
		_failure("could not check the focus NVDA takes in the window it went back to")


def followUp() -> bool:
	"""Once NVDA has started: the focus it took through UI Automation in the program it went back to, taken again.

	For when NVDA's helper came into the program only after NVDA had taken the focus there. True once there is nothing
	more to do: NVDA reads the focus there as it reads the program, NVDA reads the program through UI Automation itself,
	or the time is up.
	"""
	global _process
	if not _process:
		return True
	if nvdaIsStarting():
		return False
	try:
		if time.monotonic() > _until:
			_process = 0
			return True
		import api

		focus = api.getFocusObject()
		if focus is None or getattr(focus, "processID", None) != _process:
			return False
		if not _isUIA(focus):
			_process = 0
			return True
		taken = redirect(focus)
		if taken is not None:
			import eventHandler

			eventHandler.queueEvent("gainFocus", taken)
			return True
		appModule = focus.appModule
		if appModule is not None and appModule.helperLocalBindingHandle:
			# NVDA's helper is in the program, and NVDA reads it through UI Automation: NVDA's own choice.
			_process = 0
			return True
		return False
	except Exception:
		_process = 0
		_failure("could not check how NVDA reads the focus in the window it went back to")
		return True


def followUntilSettled() -> None:
	"""Checks followUp a few times a second, from when NVDA has started until there is nothing more to do."""
	global _timer
	import wx

	def check():
		global _timer
		_timer = None
		if not followUp():
			_timer = wx.CallLater(CHECK_MS, check)

	stop(keepFollowing=True)
	_timer = wx.CallLater(CHECK_MS, check)


def stop(keepFollowing: bool = False) -> None:
	global _timer, _process
	if not keepFollowing:
		_process = 0
	timer, _timer = _timer, None
	if timer is not None:
		try:
			timer.Stop()
		except Exception:
			pass
