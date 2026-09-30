# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""ClassicSpeech's "Page ready" message is said for a page that finished loading before NVDA had its buffer ready.

A tester turned on "Notify when page is ready" in ClassicSpeech's settings, Page Summary (issue 43, "It no longer says
page ready"; issue 44 has the same silence with "Loading Complete" as the message). Most pages said it. Two of the
tester's logs (2026-09-29, NVDA 2026.2, Edge, ClassicSpeech 1.18) have pages that did not: typing an address and
pressing Enter, NVDA said the page's title, came into the page, and then nothing, not the message and not the page
summary two seconds after it, where the same address, typed the same way, said both earlier in the same log or in the
other. Nothing else differs in the log: no error, and NVDA's log has no line for the events it got.

ClassicSpeech says the message from its global plugin's ``event_documentLoadComplete``, which NVDA runs when the browser
says a document has finished loading. ClassicSpeech 1.18 does its work after NVDA's own handling, as its docstring says:
``nextHandler()``, and then ``WebPageLifecycle.handle_document_load_complete``. But NVDA 2026.2 gives the event to the
document's tree interceptor, where its own handler is (``VirtualBuffer.event_documentLoadComplete``, the only one NVDA
has for this event), only ``if treeInterceptor.isReady`` (``eventHandler._EventExecuter.gen``), and the buffer is ready
only once it has loaded (``VirtualBuffer._get_isReady``: ``VBufHandle and not isLoading``; 0.03 to 0.07 seconds in the
tester's logs). With no tree interceptor yet, or one whose buffer is still loading, nothing is left in the chain after
the global plugins, and ``nextHandler()`` raises StopIteration into the handler that called it, which ends
ClassicSpeech's handler before its second line. It never knows the page loaded. NVDA doesn't ask again: its own
``VirtualBuffer._loadBufferDone`` reads the page as the buffer is done, and needs no load event for that. So a page
the browser calls loaded just before NVDA's buffer for it is ready, which a page that loads quickly can be, gets no
message and no summary, and one that loads slowly does.

The tester's log can't show the order the events came in, because NVDA doesn't log them and ClassicSpeech logs nothing
for an event it never saw, but this is a way its code leaves a page out that fits the two silent pages, among the 14
that said it. The assistant doesn't touch ClassicSpeech or NVDA's event chain. It notes each document load event
in Edge, Chrome and Firefox (``noteLoad``, from the assistant's global plugin, which NVDA asks first, and which notes the
page in a ``finally`` after the rest of the chain, StopIteration or not). If the page is the document NVDA's focus is
in and its buffer is ready, NVDA ran the whole chain for ClassicSpeech, and whatever it did with the event, nothing
more is done. Otherwise the assistant looks again, every tenth of a second, until the page is the document NVDA's
focus is in and is ready, and then gives ClassicSpeech the event it would have had
(``handle_document_load_complete`` with the document), unless ClassicSpeech has the document's message or summary
pending or said by then. The message and the summary then come as ClassicSpeech makes them, with its settings, its
delay and its message, and once for the page, as ClassicSpeech remembers which page it said them for. It waits three seconds for the focus to come into the page and ten for the
page to be ready, and stops at once if the focus goes to another program, as it does when the Elements List opens
before the page is ready. The assistant also writes to NVDA's log what it saw, so the next log tells which order it
was: whether the page's buffer wasn't ready, or NVDA's focus wasn't in the page, and where the focus was and what
ClassicSpeech had if it still says nothing.

Nothing changes where ClassicSpeech is not installed, for a page whose buffer was ready (ClassicSpeech had the event,
and said its message and summary or left them off as its settings say), or, if ClassicSpeech later does its work in a
``finally``, for any page, as it then takes the page first. The page, the focus and the caret are never touched. It works while the
assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import threading
import time

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "sayPageReadyForEveryPage"
#: The names NVDA gives the app modules of the browsers ClassicSpeech's page message is for.
BROWSERS = frozenset(("msedge", "chrome", "firefox"))
#: When the first look at a page ClassicSpeech didn't take is, and how often the next ones are, in milliseconds.
LOOK_AFTER = 50
LOOK_EVERY = 100
#: How long, in seconds, the focus may take to come into the page that loaded, and the page to be ready.
WAIT_FOR_FOCUS = 3.0
WAIT_FOR_PAGE = 10.0

_enabled = False
_failed = False
_lock = threading.RLock()
#: The page being waited for, while it is: see _Wait. Only the newest page matters.
_waiting = None


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
	"""Whether a page that loaded before its buffer was ready still gets ClassicSpeech's message: on unless turned off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have ClassicSpeech's page message said for every page that loads, from now on."""
	global _enabled
	_enabled = True


def unregister() -> None:
	"""Stop waiting for pages, and leave ClassicSpeech alone."""
	global _enabled, _waiting
	_enabled = False
	with _lock:
		_waiting = None


def isRegistered() -> bool:
	return _enabled


def _now() -> float:
	return time.monotonic()


def _later(milliseconds: int, function, *args):
	"""Run ``function`` on NVDA's main thread after ``milliseconds``."""
	import wx

	return wx.CallLater(milliseconds, function, *args)


# -- ClassicSpeech ------------------------------------------------------------------------------------------------------


def classicSpeech():
	"""ClassicSpeech's running global plugin, or None where it is not running."""
	try:
		import globalPluginHandler

		for plugin in globalPluginHandler.runningPlugins:
			if callable(getattr(plugin, "_get_web_page_lifecycle", None)) and callable(getattr(plugin, "event_documentLoadComplete", None)):
				return plugin
	except Exception:
		_failure("can't look for ClassicSpeech among NVDA's global plugins")
	return None


def _took(plugin, document) -> bool:
	"""Whether ClassicSpeech has ``document``'s message or summary pending (it is on it) or said (it is done)."""
	for name in ("_automaticSummaryPending", "_automaticSummaryReported"):
		held = getattr(plugin, name, None)
		if held is not None and held[0] is document:
			return True
	orientation = getattr(plugin._get_web_page_lifecycle(), "_pageOrientationSummaryPending", None)
	return orientation is not None and orientation[0] is document


# -- NVDA ---------------------------------------------------------------------------------------------------------------


def inBrowser(obj) -> bool:
	"""Whether ``obj`` is in Edge, Chrome or Firefox."""
	return getattr(getattr(obj, "appModule", None), "appName", None) in BROWSERS


def _focusDocument():
	"""The browse mode document NVDA's focus is in, as ClassicSpeech finds it, or None."""
	import api

	document = getattr(api.getFocusObject(), "treeInterceptor", None)
	return document if callable(getattr(document, "_iterNodesByType", None)) else None


def _isDocumentOf(document, obj) -> bool:
	"""Whether ``document``, a browse mode document, is the one of ``obj``, the object of a document load event."""
	if document is None:
		return False
	root = getattr(document, "rootNVDAObject", None)
	if root is not None and (root is obj or root == obj):
		return True
	return getattr(obj, "treeInterceptor", None) is document


def _focusInBrowser() -> bool:
	import api

	return inBrowser(api.getFocusObject())


def _describeFocus() -> str:
	"""What NVDA's focus is, for the log."""
	try:
		import api

		focus = api.getFocusObject()
		document = getattr(focus, "treeInterceptor", None)
		return (
			f"{type(focus).__name__} ({getattr(focus, 'windowClassName', '?')}, in {getattr(getattr(focus, 'appModule', None), 'appName', '?')}), "
			f"browse mode document: {type(document).__name__ if document is not None else 'none'}"
		)
	except Exception:
		return "unknown"


class _Wait:
	"""A page that finished loading, which ClassicSpeech hasn't taken, and what has been seen of it since."""

	def __init__(self, obj, since: float):
		self.obj = obj
		self.since = since
		#: When the page was first the document NVDA's focus is in.
		self.focusedAt = None
		#: The timer of the next look, kept so that nothing lets go of it before it runs.
		self.timer = None


def noteLoad(obj) -> None:
	"""A document finished loading (NVDA's documentLoadComplete, after the rest of the event's chain, finished or not).

	If the page is the one NVDA's focus is in and its buffer is ready, NVDA ran the whole event for ClassicSpeech, and
	nothing more is done. If not, wait for the page to be the one NVDA's focus is in and ready, then have ClassicSpeech
	handle the event.
	"""
	global _waiting
	if not _enabled:
		return
	try:
		if not inBrowser(obj):
			return
		plugin = classicSpeech()
		if plugin is None:
			return
		document = _focusDocument()
		focused = _isDocumentOf(document, obj)
		if focused and (getattr(document, "isReady", False) is True or _took(plugin, document)):
			# The page is the one NVDA's focus is in, with its buffer ready: NVDA gave the event to every global plugin and
			# ran the whole chain, so whatever ClassicSpeech did with it, saying it or not, stands.
			return
		with _lock:
			current = _waiting
			if current is not None and (current.obj is obj or current.obj == obj):
				# The same page's event again, which happens as a page changes: the wait goes on, from the first.
				return
			wait = _waiting = _Wait(obj, _now())
		if not focused:
			why = "NVDA's focus isn't in it yet"
		else:
			why = "its buffer isn't ready, so NVDA's event ended before ClassicSpeech's code after it"
		_debug(
			f"jawsMigrator: a page finished loading, and ClassicSpeech didn't say it was ready: {why}; the assistant waits for the page to be "
			f"the one NVDA's focus is in and ready; focus: {_describeFocus()}"
		)
		wait.timer = _later(LOOK_AFTER, _look, wait)
	except Exception:
		_failure("can't tell whether ClassicSpeech took a page's load event, so a page that loaded early may get no message")


def _stop(wait: _Wait, why: str) -> None:
	global _waiting
	with _lock:
		if _waiting is wait:
			_waiting = None
	_debug(f"jawsMigrator: {why}")


def _again(wait: _Wait) -> None:
	wait.timer = _later(LOOK_EVERY, _look, wait)


def _look(wait: _Wait) -> None:
	"""One look at a page that loaded and that ClassicSpeech hasn't taken."""
	with _lock:
		if not _enabled or _waiting is not wait:
			return
	try:
		elapsed = _now() - wait.since
		plugin = classicSpeech()
		if plugin is None:
			return _stop(wait, "ClassicSpeech isn't running any more, so a page that loaded isn't waited for")
		if not _focusInBrowser():
			return _stop(
				wait,
				f"NVDA's focus left the browser before the page that loaded was ready, so ClassicSpeech's page message isn't asked for; focus: {_describeFocus()}",
			)
		document = _focusDocument()
		if not _isDocumentOf(document, wait.obj):
			if elapsed > WAIT_FOR_FOCUS:
				return _stop(
					wait,
					f"NVDA's focus didn't come into the page that loaded within {WAIT_FOR_FOCUS:g} seconds, so ClassicSpeech's page message isn't asked for; focus: {_describeFocus()}",
				)
			return _again(wait)
		if wait.focusedAt is None:
			wait.focusedAt = _now()
		if _took(plugin, document):
			return _stop(wait, "ClassicSpeech has taken the page that loaded, so the assistant has nothing to add")
		if getattr(document, "isReady", False) is not True:
			if _now() - wait.focusedAt > WAIT_FOR_PAGE:
				return _stop(wait, f"the page that loaded wasn't ready within {WAIT_FOR_PAGE:g} seconds of NVDA's focus coming into it, so ClassicSpeech's page message isn't asked for")
			return _again(wait)
		plugin._get_web_page_lifecycle().handle_document_load_complete(document)
		_stop(
			wait,
			f"{elapsed:.1f} seconds after a page loaded, NVDA's focus is in it and it is ready, and ClassicSpeech had not said it: the assistant asks ClassicSpeech to say it now "
			+ ("(it has it pending now)" if _took(plugin, document) else "(ClassicSpeech's message and summary are off, or it has another way of saying them, so it left it)"),
		)
	except Exception:
		_failure("can't ask ClassicSpeech to say a page that loaded early is ready")
		_stop(wait, "a page that loaded was left after an error")
