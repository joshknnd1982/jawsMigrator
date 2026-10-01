# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""What NVDA said, kept as JAWS keeps its speech history: NVDA+Shift+J, then H shows it, Control+H copies it
and Shift+H clears it.

A tester found the Speech History add-on a pain to use (issue 28), and they use it to tell us what NVDA said. It
goes back through what NVDA said one thing at a time, with Shift+F11 and Shift+F12, and F12 copies the one thing
it is on; its NVDA+H list shows the newest first. JAWS keeps the last 500 things it said and has three layered
keystrokes for them (Default.JKM; the scripts are in Default.jss):

- Insert+Space, H (ShowSpeechHistory) opens them in JAWS's Results Viewer, titled "Speech History", the oldest
  first, on the line of the most recent one. The arrow keys go back through them, and any of it can be selected
  and copied. JAWS's training says so ("JAWS maintains a history of the last 500 strings of text that is sent
  to the speech synthesizer").
- Insert+Space, Control+H (CopySpeechHistoryToClipboard) copies all of it to the clipboard and says "Copy speech
  history to clipboard".
- Insert+Space, Shift+H (ClearSpeechHistory) says "Speech history cleared", then clears it, so the history starts
  empty and the words aren't in it.

NVDA has no layered keystrokes; the assistant's layer after NVDA+Shift+J has the same three, on the same keys.
The history is what NVDA says, one line each time NVDA speaks, the oldest first: the text NVDA's Speech Viewer
shows, its parts two spaces apart (speechViewer.SPEECH_ITEM_SEPARATOR), with any line break in a part made a
space. It is heard through NVDA's own speech.extensions.pre_speech, which NVDA's speech.speak notifies with what it
is about to say, after every add-on's filter_speechSequence (ClassicSpeech's changes, so it is what you hear), and
before speech dictionaries and symbols. It wraps nothing, so the Speech History add-on, which replaces
speech.speech.speak, and ClassicSpeech keep working as they do. It is kept in memory, never written to disk, and
goes when NVDA exits. As in NVDA's Speech Viewer, which stops adding lines while its own text box has the focus,
nothing NVDA says while the Speech History window is in front is added: reading the history doesn't push out what
you want from it, or fill what you copy next.

As the window opens, NVDA says what JAWS says as its Results Viewer opens: the title, "Speech History", then the most
recent line. On its own, NVDA said "Speech History, dialog", then "edit", the line and "read only" (issue 36, the
tester's log on 1.38). So the window and its text box get classes of the assistant's (chooseOverlay): NVDA says the
window's title without its role, and the line at the caret as the arrow keys say it. Braille and NVDA's other
commands still give the role and states.

JAWS's option for it is [Options] SpeechHistory in Default.jcf, on as JAWS comes (with it off, JAWS says "Speech
history disabled"). The migration brings it over as this setting (settingsMap), which NVDA's Settings, JAWS
Migration Assistant can turn off; turned off, the history is forgotten.

JAWS's history holds what JAWS sent to the synthesizer. pre_speech tells what NVDA is about to say, and NVDA's speech
manager can still drop it before the synthesizer says a word: what NVDA says for the focus once the focus has moved
on, and all it hasn't said yet when NVDA cuts speech short (issue 30: the tester's pasted history had a whole page
NVDA never said, from a tab Edge was leaving). So the history leaves out what NVDA dropped that way, as far as the
speech manager tells it (speechQueue.neverSaid): speech for the focus, and for the places the focus is in in Edge and
Chrome (browserPages). What is still to be said, or was cut short after the synthesizer started it, stays.
"""

from __future__ import annotations

import collections

from . import debugLog, speechQueue

#: The assistant's setting (state.json) that turns this on or off; JAWS's [Options] SpeechHistory.
STATE_KEY = "keepSpeechHistory"
#: As many things said as JAWS 2021 and later keep.
MOST = 500
#: Between the parts of one thing said: NVDA's speechViewer.SPEECH_ITEM_SEPARATOR, as its Speech Viewer shows them.
SEPARATOR = "  "
#: The window's title, as JAWS's (common.jsm, cmsgSpeechHistoryTitle).
TITLE = "Speech History"
#: What JAWS says (common.jsm): cmsgClearSpeechHistory, cmsgCopySpeechHistory, cmsgSpeechHistoryNotAvailable.
CLEARED = "Speech history cleared"
COPIED = "Copy speech history to clipboard"
DISABLED = "Speech history disabled. Turn it on in NVDA's Settings, JAWS Migration Assistant."
#: When it was turned on, but NVDA wouldn't let the assistant hear its speech.
UNAVAILABLE = "The speech history can't be kept. The assistant's debug log says why."
#: Where JAWS would open an empty viewer or copy nothing.
EMPTY = "No speech history"
NOT_COPIED = "The speech history could not be copied to the clipboard"

#: What NVDA said: (the line, the commands by which NVDA's speech manager could drop it), the oldest first.
_history: collections.deque = collections.deque(maxlen=MOST)
_registered = False
#: Whether the assistant was asked to keep it (register), even if NVDA wouldn't let it.
_wanted = False
_failed = False
#: The Speech History window while it is open, and whether it is in front, when nothing is added.
_viewer = None
_viewerActive = False
#: While it is open, the window handles of the Speech History window and its text box, for chooseOverlay, which NVDA
#: may call off its main thread, where wx can't be asked.
_viewerHandles = (None, None)


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
	"""Whether a speech history is kept, as JAWS keeps one: on unless the user or JAWS turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def lineOf(speechSequence) -> str:
	"""What NVDA says in ``speechSequence``, as one line: its text parts two spaces apart. Empty for no text."""
	parts = []
	for item in speechSequence or ():
		if isinstance(item, str):
			text = " ".join(item.split())
			if text:
				parts.append(text)
	return SEPARATOR.join(parts)


def _onSpeech(speechSequence=None, **kwargs) -> None:
	"""NVDA's pre_speech handler: NVDA is about to say ``speechSequence``. It must never keep NVDA from speaking."""
	try:
		if _viewerActive:
			return
		line = lineOf(speechSequence)
		if line:
			_history.append((line, speechQueue.cancellables(speechSequence)))
	except Exception:
		_failure("could not add what NVDA said to the speech history")


def register() -> bool:
	"""Keep what NVDA says from now on. Returns whether it is kept."""
	global _registered, _wanted
	_wanted = True
	if _registered:
		return True
	try:
		from speech.extensions import pre_speech

		pre_speech.register(_onSpeech)
		_registered = True
	except Exception:
		debugLog.error("the speech history can't be kept: NVDA's speech.extensions.pre_speech can't be used")
		return False
	return True


def unregister() -> None:
	"""Stop keeping what NVDA says, forget it, and close the Speech History window."""
	global _registered, _wanted
	_wanted = False
	if _registered:
		_registered = False
		try:
			from speech.extensions import pre_speech

			pre_speech.unregister(_onSpeech)
		except Exception:
			_failure("could not stop keeping the speech history")
	_history.clear()
	closeViewer()


def isRegistered() -> bool:
	return _registered


def entries() -> list:
	"""What NVDA said, the oldest first, without what NVDA's speech manager dropped before saying any of it."""
	queued = speechQueue.pending()
	return [line for line, commands in list(_history) if not speechQueue.neverSaid(commands, queued)]


def clear() -> None:
	_history.clear()


def text(lineBreak: str = "\n") -> str:
	return lineBreak.join(entries())


# -- the commands -------------------------------------------------------------------------------------------------


def _say(message: str) -> None:
	try:
		import ui

		ui.message(message)
	except Exception:
		pass


def _copy(value: str) -> bool:
	"""Put ``value`` on the clipboard with NVDA's own api.copyToClip, which reads it back to check."""
	try:
		import api

		return bool(api.copyToClip(value))
	except Exception:
		debugLog.error("could not copy the speech history to the clipboard")
		return False


def _sayWhyNot() -> None:
	_say(UNAVAILABLE if _wanted else DISABLED)


def copyAndSay() -> bool:
	"""JAWS's Insert+Space, Control+H: all of the speech history on the clipboard, one line each."""
	if not _registered:
		_sayWhyNot()
		return False
	if not entries():
		_say(EMPTY)
		return False
	# Windows programs take \r\n as a line break; api.copyToClip checks the clipboard holds just that.
	if not _copy(text("\r\n")):
		_say(NOT_COPIED)
		return False
	_say(COPIED)
	return True


def clearAndSay() -> None:
	"""JAWS's Insert+Space, Shift+H: says so, then clears, so the words aren't in the history."""
	_say(CLEARED)
	clear()
	viewer = _viewer
	if viewer is not None:
		try:
			viewer.showText("")
		except Exception:
			pass


def showAndSay() -> bool:
	"""JAWS's Insert+Space, H: the Speech History window, on the most recent line; again, it shows what is new."""
	if not _registered:
		_sayWhyNot()
		return False
	if not entries():
		_say(EMPTY)
		return False
	try:
		_showViewer()
	except Exception:
		debugLog.error("could not show the speech history")
		_say("The speech history could not be shown. The assistant's debug log says why.")
		return False
	return True


# -- the Speech History window ------------------------------------------------------------------------------------


def _setViewerActive(active: bool) -> None:
	global _viewerActive
	_viewerActive = bool(active)


def _viewerClosed(viewer) -> None:
	global _viewer, _viewerHandles
	if _viewer is viewer:
		_viewer = None
		_viewerHandles = (None, None)
		_setViewerActive(False)


def _showViewer() -> None:
	global _viewer, _viewerHandles
	import wx

	from .gui.common import mainFrame, postPopup, prePopup

	viewer = _viewer
	if viewer is not None:
		# JAWS shows it again in the window already open, with what is new.
		viewer.showText(text())
		prePopup()
		try:
			viewer.Raise()
			viewer.text.SetFocus()
		finally:
			postPopup()
		return
	viewer = _viewerClass()(mainFrame(), text())
	_viewer = viewer
	# Before the window shows: NVDA makes its objects for it once it has the focus.
	_viewerHandles = (viewer.GetHandle(), viewer.text.GetHandle())
	# As NVDA opens its own Settings dialogs: prePopup lets the window come in front of the program you were in.
	prePopup()
	try:
		viewer.Show()
		viewer.Raise()
		viewer.text.SetFocus()
	finally:
		postPopup()
	wx.CallAfter(_focusText, viewer)


def _focusText(viewer) -> None:
	try:
		if _viewer is viewer:
			viewer.text.SetFocus()
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


# -- what NVDA says as the window opens ------------------------------------------------------------------------------


def chooseOverlay(obj, clsList) -> None:
	"""NVDA's chooseNVDAObjectOverlayClasses: the Speech History window and its text box get the assistant's classes,
	so NVDA says the title and then the line, as JAWS does."""
	windowHandle, textHandle = _viewerHandles
	if windowHandle is None:
		return
	try:
		handle = getattr(obj, "windowHandle", None)
		if handle is None or handle not in (windowHandle, textHandle):
			return
		# Told by the classes NVDA chose, not by the object's role: NVDA would go on using a property read before the
		# object has its classes (see documentPolling). A window's other objects, such as its frame, have neither.
		if handle == textHandle:
			from editableText import EditableText as wanted
		else:
			from NVDAObjects.behaviors import Dialog as wanted
		if not any(isinstance(cls, type) and issubclass(cls, wanted) for cls in clsList):
			return
		windowClass, textClass = _overlayClasses()
		clsList.insert(0, textClass if handle == textHandle else windowClass)
	except Exception:
		_failure("could not tell whether an object is the Speech History window's")


def _focusLossCommand(obj):
	"""NVDA's command that drops what it says for the focus once the focus has moved on, as NVDA adds it to what it
	says of an object for the focus, or None."""
	try:
		import controlTypes
		from eventHandler import _getFocusLossCancellableSpeechCommand

		return _getFocusLossCancellableSpeechCommand(obj, controlTypes.OutputReason.FOCUS)
	except Exception:
		return None


_overlays = None


def _overlayClasses():
	"""The classes for the Speech History window and its text box, made the first time."""
	global _overlays
	if _overlays is not None:
		return _overlays
	import controlTypes
	import speech
	import textInfos
	from NVDAObjects import NVDAObject

	class SpeechHistoryWindow(NVDAObject):
		"""The Speech History window: its title, as JAWS says the Results Viewer's, without "dialog"."""

		def event_focusEntered(self):
			try:
				speech.speakObjectProperties(self, reason=controlTypes.OutputReason.FOCUS, name=True)
			except Exception:
				_failure("could not say the Speech History window's title")
				super().event_focusEntered()

	class SpeechHistoryText(NVDAObject):
		"""The Speech History window's text box: the line at the caret, as the arrow keys say it, without "edit" and
		"read only", as JAWS says only the line in its Results Viewer."""

		def reportFocus(self):
			try:
				info = self.makeTextInfo(textInfos.POSITION_CARET)
				info.expand(textInfos.UNIT_LINE)
			except Exception:
				_failure("could not read the Speech History window's line")
				super().reportFocus()
				return
			speech.speakTextInfo(
				info,
				unit=textInfos.UNIT_LINE,
				reason=controlTypes.OutputReason.CARET,
				_prefixSpeechCommand=_focusLossCommand(self),
			)

	_overlays = (SpeechHistoryWindow, SpeechHistoryText)
	return _overlays


_viewerType = None


def _viewerClass():
	"""The Speech History window's class, made the first time: wx is imported only once it is needed."""
	global _viewerType
	if _viewerType is not None:
		return _viewerType
	import wx

	from .gui.common import BORDER, readOnlyText

	class SpeechHistoryViewer(wx.Dialog):
		"""What NVDA said, one line each, the oldest first, with the caret on the most recent line."""

		def __init__(self, parent, value: str):
			super().__init__(parent, title=TITLE, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
			sizer = wx.BoxSizer(wx.VERTICAL)
			# No label: NVDA says the window's title, "Speech History", then the line, as JAWS does.
			self.text = readOnlyText(self, "", size=(700, 420))
			sizer.Add(self.text, proportion=1, flag=wx.EXPAND)
			buttons = wx.BoxSizer(wx.HORIZONTAL)
			self.copyButton = wx.Button(self, label="&Copy all")
			self.copyButton.Bind(wx.EVT_BUTTON, self._onCopy)
			buttons.Add(self.copyButton)
			self.clearButton = wx.Button(self, label="C&lear")
			self.clearButton.Bind(wx.EVT_BUTTON, self._onClear)
			buttons.Add(self.clearButton, flag=wx.LEFT, border=8)
			close = wx.Button(self, wx.ID_CANCEL, "Cl&ose")
			close.Bind(wx.EVT_BUTTON, lambda event: self.Close())
			buttons.Add(close, flag=wx.LEFT, border=8)
			sizer.Add(buttons, flag=wx.ALIGN_RIGHT | wx.TOP, border=8)
			outer = wx.BoxSizer(wx.VERTICAL)
			outer.Add(sizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=BORDER)
			self.SetSizerAndFit(outer)
			# Escape presses Close, as in JAWS's Results Viewer.
			self.SetEscapeId(wx.ID_CANCEL)
			self.Bind(wx.EVT_ACTIVATE, self._onActivate)
			self.Bind(wx.EVT_CLOSE, self._onClose)
			self.CentreOnScreen()
			self.showText(value)

		def showText(self, value: str) -> None:
			"""Show ``value`` with the caret at the start of its last line, the most recent thing said."""
			self.text.SetValue(value)
			lines = self.text.GetNumberOfLines()
			position = self.text.XYToPosition(0, max(lines - 1, 0))
			self.text.SetInsertionPoint(position if position >= 0 else 0)
			self.text.ShowPosition(self.text.GetInsertionPoint())

		def _onActivate(self, event):
			_setViewerActive(event.GetActive())
			event.Skip()

		def _onCopy(self, event):
			value = self.text.GetValue()
			if not value:
				_say(EMPTY)
			elif _copy("\r\n".join(value.splitlines())):
				_say(COPIED)
			else:
				_say(NOT_COPIED)

		def _onClear(self, event):
			_say(CLEARED)
			clear()
			self.showText("")
			self.text.SetFocus()

		def _onClose(self, event):
			_viewerClosed(self)
			self.Destroy()

	_viewerType = SpeechHistoryViewer
	return _viewerType
