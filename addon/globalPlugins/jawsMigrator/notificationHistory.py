# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""The notifications Windows and programs send, kept as JAWS keeps its Notification History: NVDA+Shift+J, then N lists
them, and NVDA+Shift+J, then Shift+N says the last one again.

A tester asked for it (issue 33, Question 5). JAWS keeps the notifications it gets from Windows and programs
(Default.JSS, StoreSpokenNotificationForRepeat) and has two layered keystrokes for them (Default.JKM, [Common Keys]):

- Insert+Space, N (ShowNotificationHistory) opens the Notification History: a list of the notifications "received from
  Windows and applications during the past 24 hours" (NotificationViewer.jsm), the last 500 at most (default.jsd).
  Enter on one shows "the full notification text, the application where it came from, and the time it was received",
  Clear history empties it, and Escape closes it (JAWS's help, Notification History). Its layer help says "List recent
  notifications = N."
- Insert+Space, Shift+N (RepeatLastNotification) says the last notification again, or "No notification"
  (cmsgNoNotification) when there is none: "Repeat last spoken notification = Shift+N."

JAWS keeps a notification whether or not it speaks it (UIANotificationEvent: "We want to store even if we don't speak"):
UI Automation notifications from any program (Edge's "Loading page", Teams...), except those for switching the
keyboard's language (activity ID Windows.Shell.InputSwitch.SwitchNotification) and a terminal's output
(TerminalTextOutput); only the last of a flood from moving a window (HandleMoved, as the Snipping Tool sends); and toasts
(ProcessNotificationTextAndSpeakIfAllowed), such as Outlook's for new mail. The same text again within half a second
isn't kept twice (IsRepeatNotification), and a notification without a program is from "Unknown app" (cmsgUnknownApp).

NVDA 2026.2 has no notification history, and no add-on in its Add-on Store keeps one. NVDA gives the global plugins every
UI Automation notification (event_UIA_notification) before the program's app module or the object says it, and a toast
as it opens (event_UIA_window_windowOpen on NVDAObjects.UIA.Toast_win10, a behaviors.Notification). The assistant notes
each one there and passes it on unchanged, so what NVDA and other add-ons (MS Edge Discard Announcements, Custom
Notifications) say is as before. A toast's program is the one its text names ("New notification from Outlook, ...");
a UI Automation notification's is the program NVDA got it from. The history is kept in memory, never written to disk,
and goes when NVDA exits, as JAWS keeps it while it runs.

The list shows the most recent notification first. It works while the assistant runs, unless it is turned off in NVDA's
Settings, JAWS Migration Assistant; turned off, the history is forgotten.
"""

from __future__ import annotations

import collections
import re
import threading
import time

from . import debugLog

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "keepNotificationHistory"
#: As many notifications as JAWS keeps (default.jsd), and for as long (NotificationViewer.jsm), in seconds.
MOST = 500
KEEP_FOR = 24 * 60 * 60
#: The same text again within this many seconds is the same notification (JAWS's IsRepeatNotification: 500 ms).
REPEAT_WITHIN = 0.5
#: UI Automation notifications JAWS doesn't keep (UIANotificationEvent; HJConst.jsh).
SKIPPED_ACTIVITIES = frozenset({"Windows.Shell.InputSwitch.SwitchNotification", "TerminalTextOutput"})
#: A flood of these (the Snipping Tool's) keeps only its last (JAWS waits 2 tenths of a second for more).
FLOOD_ACTIVITY = "HandleMoved"
FLOOD_WITHIN = 2.0
#: Where a toast names its program (JAWS's help: "^New Notification from Outlook, (.*?),").
TOAST_FROM = re.compile(r"^\s*new notification from (.+?)(?:,|\.|$)", re.IGNORECASE)
#: What JAWS says (common.jsm): cmsgNoNotification, cmsgUnknownApp; and the window's title and list, as JAWS's help
#: names them.
NO_NOTIFICATION = "No notification"
UNKNOWN_APP = "Unknown app"
TITLE = "Notification History"
LIST_LABEL = "&Recent notifications"
DETAILS_TITLE = "Notification details"
CLEARED = "Notification history cleared"
DISABLED = "Notification history disabled. Turn it on in NVDA's Settings, JAWS Migration Assistant."
NOT_COPIED = "The notification could not be copied to the clipboard"
COPIED = "Copied"

Notification = collections.namedtuple("Notification", ("text", "app", "received", "activity"))

#: The notifications, the oldest first.
_history: collections.deque = collections.deque(maxlen=MOST)
_lock = threading.RLock()
_registered = False
#: The last notification noted and when (time.monotonic), to tell a repeat.
_last = None
#: The Notification History window while it is open.
_viewer = None


def _log():
	from logHandler import log

	return log


def _debug(message: str) -> None:
	try:
		_log().debug(message)
	except Exception:
		pass


def wanted(stateData: dict) -> bool:
	"""Whether notifications are kept for NVDA+Shift+J, then N and Shift+N: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Keep the notifications from now on."""
	global _registered
	_registered = True


def unregister() -> None:
	"""Stop keeping notifications, and forget them."""
	global _registered, _last
	_registered = False
	with _lock:
		_history.clear()
		_last = None
	closeViewer()


def isRegistered() -> bool:
	return _registered


# -- keeping them ---------------------------------------------------------------------------------------------------


def _oneLine(text) -> str:
	return " ".join(str(text or "").split())


def note(text, app=None, activity=None, now=None, monotonic=None) -> bool:
	"""Keep a notification. True when it was kept, False for a repeat or one without text."""
	global _last
	if not _registered:
		return False
	text = _oneLine(text)
	if not text:
		return False
	app = _oneLine(app) or UNKNOWN_APP
	now = time.time() if now is None else now
	monotonic = time.monotonic() if monotonic is None else monotonic
	with _lock:
		if _last is not None and _last[0] == text and monotonic - _last[1] <= REPEAT_WITHIN:
			_last = (text, monotonic, activity)
			return False
		if activity == FLOOD_ACTIVITY and _history and _last is not None and _last[2] == FLOOD_ACTIVITY and monotonic - _last[1] <= FLOOD_WITHIN:
			# Only the last of a flood is kept.
			_history.pop()
		_last = (text, monotonic, activity)
		_history.append(Notification(text, app, now, activity))
		_prune(now)
	return True


def _prune(now: float) -> None:
	while _history and now - _history[0].received > KEEP_FOR:
		_history.popleft()


def appOf(obj) -> str | None:
	"""The program a UI Automation notification came from, as NVDA names it (its app module's name, such as msedge)."""
	try:
		return obj.appModule.appName
	except Exception:
		return None


def fromUIANotification(obj, displayString=None, activityId=None) -> bool:
	"""A UI Automation notification NVDA got (event_UIA_notification). True when it was kept."""
	if not _registered or activityId in SKIPPED_ACTIVITIES:
		return False
	return note(displayString, appOf(obj), activityId)


def isToast(obj) -> bool:
	"""Whether ``obj`` is a Windows notification (a toast), as NVDA's UIA Toast classes are."""
	try:
		from NVDAObjects.behaviors import Notification as NotificationBehavior

		return isinstance(obj, NotificationBehavior)
	except Exception:
		return False


def toastText(obj) -> str:
	"""A toast's text: its name, and its description when the name doesn't hold it, as NVDA says it."""
	name = _oneLine(getattr(obj, "name", ""))
	description = _oneLine(getattr(obj, "description", ""))
	if description and description not in name:
		return f"{name} {description}".strip()
	return name


def toastApp(text: str) -> str | None:
	"""The program a toast's text names ("New notification from Outlook, ..."), or None."""
	match = TOAST_FROM.match(text or "")
	return match.group(1).strip() if match else None


def fromToast(obj) -> bool:
	"""A toast that opened (event_UIA_window_windowOpen). True when it was kept."""
	if not _registered or not isToast(obj):
		return False
	text = toastText(obj)
	return note(text, toastApp(text))


def entries() -> list:
	"""The notifications of the last 24 hours, the most recent first."""
	with _lock:
		_prune(time.time())
		return list(reversed(_history))


def clear() -> None:
	global _last
	with _lock:
		_history.clear()
		_last = None


def last() -> Notification | None:
	found = entries()
	return found[0] if found else None


def details(notification: Notification) -> str:
	"""What Enter shows for a notification, as JAWS: its full text, its program and when it came."""
	received = time.strftime("%I:%M:%S %p, %A %d %B %Y", time.localtime(notification.received)).lstrip("0")
	return f"{notification.text}\nApplication: {notification.app}\nReceived: {received}"


# -- the commands ---------------------------------------------------------------------------------------------------


def _say(message: str) -> None:
	try:
		import ui

		ui.message(message)
	except Exception:
		pass


def repeatLast() -> bool:
	"""JAWS's Insert+Space, Shift+N: the last notification again, or "No notification"."""
	if not _registered:
		_say(DISABLED)
		return False
	found = last()
	if found is None:
		_say(NO_NOTIFICATION)
		return False
	_say(found.text)
	return True


def showAndSay() -> bool:
	"""JAWS's Insert+Space, N: the Notification History window, on the most recent notification."""
	if not _registered:
		_say(DISABLED)
		return False
	if not entries():
		_say(NO_NOTIFICATION)
		return False
	try:
		_showViewer()
	except Exception:
		debugLog.error("could not show the notification history")
		_say("The notification history could not be shown. The assistant's debug log says why.")
		return False
	return True


def _copy(value: str) -> bool:
	try:
		import api

		return bool(api.copyToClip(value))
	except Exception:
		debugLog.error("could not copy a notification to the clipboard")
		return False


# -- the Notification History window --------------------------------------------------------------------------------


def _viewerClosed(viewer) -> None:
	global _viewer
	if _viewer is viewer:
		_viewer = None


def _showViewer() -> None:
	global _viewer
	import wx

	from .gui.common import mainFrame, postPopup, prePopup

	viewer = _viewer
	if viewer is None:
		viewer = _viewerClass()(mainFrame())
		_viewer = viewer
	viewer.showNotifications(entries())
	# As NVDA opens its own Settings dialogs: prePopup lets the window come in front of the program you were in.
	prePopup()
	try:
		viewer.Show()
		viewer.Raise()
		viewer.list.SetFocus()
	finally:
		postPopup()
	wx.CallAfter(_focusList, viewer)


def _focusList(viewer) -> None:
	try:
		if _viewer is viewer:
			viewer.list.SetFocus()
	except Exception:
		pass


def closeViewer() -> None:
	viewer = _viewer
	_viewerClosed(viewer)
	if viewer is not None:
		try:
			viewer.Destroy()
		except Exception:
			pass


_viewerType = None


def _viewerClass():
	"""The Notification History window's class, made the first time: wx is imported only once it is needed."""
	global _viewerType
	if _viewerType is not None:
		return _viewerType
	import wx

	from .gui.common import BORDER, messageBox

	class NotificationHistoryViewer(wx.Dialog):
		"""The recent notifications, the most recent first; Enter shows one's details."""

		def __init__(self, parent):
			super().__init__(parent, title=TITLE, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
			self.notifications = []
			sizer = wx.BoxSizer(wx.VERTICAL)
			sizer.Add(wx.StaticText(self, label=LIST_LABEL))
			self.list = wx.ListBox(self, size=(700, 360), style=wx.LB_SINGLE)
			sizer.Add(self.list, proportion=1, flag=wx.EXPAND | wx.TOP, border=4)
			buttons = wx.BoxSizer(wx.HORIZONTAL)
			for label, handler in (
				("&Details", self._onDetails),
				("&Copy", self._onCopy),
				("Clear &history", self._onClear),
			):
				button = wx.Button(self, label=label)
				button.Bind(wx.EVT_BUTTON, handler)
				buttons.Add(button, flag=wx.RIGHT, border=8)
			close = wx.Button(self, wx.ID_CANCEL, "Cl&ose")
			close.Bind(wx.EVT_BUTTON, lambda event: self.Close())
			buttons.Add(close)
			sizer.Add(buttons, flag=wx.ALIGN_RIGHT | wx.TOP, border=8)
			outer = wx.BoxSizer(wx.VERTICAL)
			outer.Add(sizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=BORDER)
			self.SetSizerAndFit(outer)
			# Escape closes it, as JAWS's.
			self.SetEscapeId(wx.ID_CANCEL)
			self.list.Bind(wx.EVT_LISTBOX_DCLICK, self._onDetails)
			self.Bind(wx.EVT_CHAR_HOOK, self._onKey)
			self.Bind(wx.EVT_CLOSE, self._onClose)
			self.CentreOnScreen()

		def showNotifications(self, notifications) -> None:
			"""Show ``notifications``, the most recent first, on the first."""
			self.notifications = list(notifications)
			self.list.Set([notification.text for notification in self.notifications])
			if self.notifications:
				self.list.SetSelection(0)

		def selected(self):
			index = self.list.GetSelection()
			return self.notifications[index] if 0 <= index < len(self.notifications) else None

		def _onKey(self, event):
			# Enter on a notification shows its details, as in JAWS, where a dialog would press its default button.
			if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and self.FindFocus() is self.list:
				self._onDetails(event)
				return
			event.Skip()

		def _onDetails(self, event):
			notification = self.selected()
			if notification is None:
				_say(NO_NOTIFICATION)
				return
			messageBox(details(notification), DETAILS_TITLE, parent=self)
			self.list.SetFocus()

		def _onCopy(self, event):
			notification = self.selected()
			if notification is None:
				_say(NO_NOTIFICATION)
			elif _copy(notification.text):
				_say(COPIED)
			else:
				_say(NOT_COPIED)

		def _onClear(self, event):
			_say(CLEARED)
			clear()
			self.showNotifications([])
			self.list.SetFocus()

		def _onClose(self, event):
			_viewerClosed(self)
			self.Destroy()

	_viewerType = NotificationHistoryViewer
	return _viewerType
