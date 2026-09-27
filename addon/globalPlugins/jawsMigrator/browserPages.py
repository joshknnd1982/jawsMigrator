# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""An Edge or Chrome window, and a page in it, are said as JAWS says them as you switch to them or a page opens.

A tester opened a reddit post in Edge (issue 30), and NVDA said:
"Worst three days of my life : r/Visible and 1 more page - Profile 1 - Microsoft Edge, window",
"Worst three days of my life : r/Visible - Microsoft Edge, region",
"Worst three days of my life : r/Visible, document, https://www.reddit.com/r/Visible/comments/...",
then the page's first line. On a copy of that page in Edge, JAWS 2026 said "Worst three days of my life : r/Visible -
Microsoft Edge", then that again with "page", then "Worst three days of my life : r/Visible", then how many regions,
headings and links the page has: the titles alone, never "window", "document" or the page's address. JAWS's scripts
for Chrome, which Edge's use too (Chrome.jss): switching to the browser says the window's name alone
(``HandleCustomAppWindows``, ``ot_window_name``); a window or pane the focus is in isn't said
(``ShouldSpeakItemAtLevel``); and a page that opens is said by its title and its first line or its summary
(IA2Browser.jss ``DoSayObjectTypeAndTextFromLevel``, default.jss ``DoDefaultDocumentLoadActions``).

NVDA says "window" after the name of Edge's and Chrome's windows, which their IAccessible2 and UI Automation give that
role, and "document" after a page's title. The address and "region" are NVDA reading Edge through UI Automation that
time: NVDA 2026.2 reads a Chromium page through IAccessible2 only in the window Chromium keeps for the page
(Chrome_RenderWidgetHostHWND) and only once NVDA's helper is in the browser (``UIAHandler._isUIAWindowHelper``).
Through IAccessible2 a page has no value (``NVDAObjects.IAccessible.ia2Web.Document.value`` is None); through UI
Automation its value is its address (``NVDAObjects.UIA.chromium.ChromiumUIADocument``), which NVDA says with the title.
And through UI Automation, Edge's own frame around the page, "the page's title - Microsoft Edge", is a region
(class BrowserRootView, ARIA role "region"), which NVDA says as the focus enters it. Through IAccessible2, NVDA says
neither.

So, in Edge and Chrome: their window is said by its name, without "window"; a page, when it opens or you come back to
it, by its title, without "document" or its address; and Edge's frame around the page isn't said. Anything else NVDA
says with them (a state, or a description) is said as NVDA says it. A page without a title, NVDA+Tab and every other
program are as before. Braille is unchanged. It works while the assistant runs, unless it is turned off in NVDA's
Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import functools
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "sayBrowserPagesAsJaws"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own version, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorBrowserPages"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: NVDA's function that says an object, in its speech package: NVDAObject.reportFocus and event_focusEntered, and
#: browse mode as a page opens, call it there.
FUNCTION = "speakObject"
#: The names NVDA gives Edge's and Chrome's app modules: JAWS's scripts for Chrome read both (msedge.jss uses chrome.jsb).
BROWSERS = frozenset(("msedge", "chrome"))
#: The start of the class of a Chromium browser's windows.
WINDOW_CLASS = "Chrome_WidgetWin_"
#: What Chromium calls its view that holds a window's frame and page, which UI Automation gives the page's title and
#: the role "region" (views::internal::RootView, BrowserRootView).
FRAME_CLASS = "BrowserRootView"
#: What is said: a browser's window, its frame, a page in it.
WINDOW, FRAME, PAGE = "window", "frame", "page"
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: NVDA's roles and output reasons used here, once known.
_windowRole = None
_regionRole = None
_documentRole = None
_focus = None
_focusEntered = None
_query = None


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


def _debug(message: str) -> None:
	try:
		_log().debug(message)
	except Exception:
		pass


def wanted(stateData: dict) -> bool:
	"""Whether Edge's and Chrome's windows and pages are said as JAWS says them: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have NVDA say Edge's and Chrome's windows and pages as JAWS says them, from now on."""
	global _enabled, _windowRole, _regionRole, _documentRole, _focus, _focusEntered, _query
	if _enabled:
		return
	try:
		import speech
		from controlTypes import OutputReason, Role

		_windowRole, _regionRole, _documentRole = Role.WINDOW, Role.REGION, Role.DOCUMENT
		_focus, _focusEntered, _query = OutputReason.FOCUS, OutputReason.FOCUSENTERED, OutputReason.QUERY
		with _lock:
			if not _replace(speech):
				return
	except Exception:
		_failure("can't say Edge's and Chrome's windows and pages as JAWS says them, so NVDA says them as it does")
		return
	_enabled = True


def unregister() -> None:
	"""Give NVDA its own function back, where nothing has been put over the assistant's since."""
	global _enabled
	if not _enabled:
		return
	_enabled = False
	with _lock:
		for owner, name, installed, original in reversed(_replaced):
			try:
				if vars(owner).get(name) is installed:
					setattr(owner, name, original)
			except Exception:
				pass
		_replaced.clear()


def isRegistered() -> bool:
	return _enabled


def _isOurs(function) -> bool:
	"""Whether ``function`` is the assistant's version, or wraps it (as another add-on's functools.wraps wrapper would)."""
	for _ in range(_MOST_WRAPPERS):
		if function is None:
			return False
		if getattr(function, MARK, None) is _TOKEN:
			return True
		function = getattr(function, "__wrapped__", None)
	return False


def _replace(owner) -> bool:
	"""Put the assistant's version of NVDA's function in its place on ``owner``, once. True when it is there."""
	current = vars(owner).get(FUNCTION)
	if _isOurs(current):
		# Still there from before: turned off and on again, or another add-on has put its own around it since.
		return True
	if not callable(current):
		_failure(f"NVDA has no speech.{FUNCTION} the assistant knows, so NVDA says Edge's and Chrome's windows and pages as it does")
		return False
	installed = _guarded(current)
	setattr(owner, FUNCTION, installed)
	_replaced.append((owner, FUNCTION, installed, current))
	_debug(f"jawsMigrator: Edge's and Chrome's windows and pages are said as JAWS says them (speech.{FUNCTION})")
	return True


def _argument(args: tuple, kwargs: dict, name: str, index: int, default=None):
	"""An argument of speakObject after obj: reason, _prefixSpeechCommand or priority."""
	if name in kwargs:
		return kwargs[name]
	return args[index] if len(args) > index else default


def _uiaClassName(obj) -> str | None:
	"""The class UI Automation gives ``obj``, or None for an object NVDA doesn't get through UI Automation."""
	element = getattr(obj, "UIAElement", None)
	if element is None:
		return None
	try:
		return element.cachedClassName
	except Exception:
		return None


def kindOf(obj, reason) -> str | None:
	"""What NVDA is about to say for ``reason``: an Edge or Chrome window (WINDOW), Edge's frame around a page (FRAME),
	a page (PAGE), or None for anything else, which NVDA says as it does."""
	appModule = getattr(obj, "appModule", None)
	if getattr(appModule, "appName", None) not in BROWSERS:
		return None
	role = obj.role
	if role == _windowRole:
		if reason in (_focus, _focusEntered) and str(getattr(obj, "windowClassName", "")).startswith(WINDOW_CLASS) and obj.name:
			return WINDOW
		return None
	if role == _regionRole:
		if reason == _focusEntered and _uiaClassName(obj) == FRAME_CLASS:
			return FRAME
		return None
	if role == _documentRole and reason == _focus and obj.name:
		return PAGE
	return None


def _roleWords(obj) -> str | None:
	"""What NVDA says for ``obj``'s role (speech.getPropertiesSpeech): its role text, or its role's label."""
	roleText = getattr(obj, "roleText", None)
	if roleText:
		return roleText
	return obj.role.displayString


def withoutWords(sequence, obj, kind: str) -> list:
	"""NVDA's speech for ``obj`` without its role ("window", "document") and, for a page, its value (its address)."""
	result = list(sequence)
	leave = [_roleWords(obj)]
	if kind == PAGE:
		value = getattr(obj, "value", None)
		if isinstance(value, str) and value.strip():
			leave.append(value)
	for word in leave:
		if not word:
			continue
		for index, item in enumerate(result):
			if isinstance(item, str) and item == word:
				del result[index]
				break
	return result


def _words(sequence) -> str:
	"""What is said, for the log."""
	return ", ".join(item for item in sequence if isinstance(item, str) and item.strip())


def _guarded(original):
	"""NVDA's speakObject: Edge's and Chrome's windows and pages as JAWS says them, anything else as NVDA says it."""

	@functools.wraps(original)
	def speakObject(obj, *args, **kwargs):
		if not _enabled:
			return original(obj, *args, **kwargs)
		reason = _argument(args, kwargs, "reason", 0, _query)
		try:
			kind = kindOf(obj, reason)
		except Exception:
			_failure("could not tell whether NVDA is saying an Edge or Chrome window or page")
			kind = None
		if kind is None:
			return original(obj, *args, **kwargs)
		if kind == FRAME:
			_debug(f"jawsMigrator: NVDA doesn't say the browser's frame around the page, as JAWS doesn't: {obj.name!r} region")
			return None
		# NVDA's speakObject, word for word, with the words JAWS doesn't say taken out.
		from speech import speech

		sequence = speech.getObjectSpeech(obj, reason, _argument(args, kwargs, "_prefixSpeechCommand", 1))
		try:
			said = withoutWords(sequence, obj, kind)
		except Exception:
			_failure("could not say an Edge or Chrome window or page as JAWS says it")
			said = sequence
		if said != list(sequence):
			_debug(f"jawsMigrator: the browser's {kind} is said as JAWS says it: {_words(said)} (NVDA's: {_words(sequence)})")
		if said:
			speech.speak(said, priority=_argument(args, kwargs, "priority", 2))
		return None

	setattr(speakObject, MARK, _TOKEN)
	setattr(speakObject, ORIGINAL, original)
	return speakObject
