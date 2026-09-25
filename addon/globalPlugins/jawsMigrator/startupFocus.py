# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

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
"""

from __future__ import annotations

import ctypes
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

_failed = False


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
		return target
	except Exception:
		_failure("could not give the focus back to the window you were in, as NVDA started with it on the taskbar")
		return 0
