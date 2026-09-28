# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Alt+Left and Alt+Right in a web browser say "Back" and "Forward", and the page you go back to is read where you are
in it, as JAWS does.

A tester opened a post on reddit.com in Edge, read it, and pressed Alt+Left (issue 32). JAWS 2026 said "Back", then
"Going back", then the line its cursor was on in the subreddit: "visited Link I currently have the Pixel 8 Pro...".
NVDA said nothing at all.

- "Back" and "Forward" are JAWS's own. Its scripts for Edge, Chrome and Firefox bind Alt+LeftArrow to GoBack and
  Alt+RightArrow to GoForward (msedge.jkm, Chrome.jkm, firefox.jkm). IA2Browser.jss's GoBack sends the key, says
  msgBack1_L, "Back" (ie.jsm), and turns forms mode off, because it "doesn't automatically turn off when going either
  back or forward on pages". GoForward says "Forward". NVDA has no command there: the key goes to the browser, and
  NVDA says nothing. Now NVDA says "Back" or "Forward" as the key goes to the browser, and leaves focus mode for
  browse mode.
- "Going back" is Edge's own, a UI Automation notification (its activity ID GoingBack), as are "Going forward",
  "Can't go back, no previous page" and "Can't go forward, no next page". NVDA says Edge's notifications. The tester's
  MSEdgeDiscardAnnouncements add-on keeps these silent, as it comes ("Navigating back": off), so NVDA didn't say it.
  The assistant leaves that add-on's settings alone.
- The page. JAWS reads a page you go back to where its cursor is: on a copy of a plain two-page site, "Plain page
  one", then "heading level 2, Link, Go to page two", the link it had followed. NVDA reads a page it comes into the
  same way (browseMode.BrowseModeDocumentTreeInterceptor.event_treeInterceptor_gainFocus, which
  eventHandler.doPreGainFocus calls when the focus moves into another page): its title and the line at the caret. Run
  live with the Browse Mode Caret Fix add-on (issue 32), NVDA said nothing, for three reasons:
  - Reddit doesn't load a page on Back. It puts the subreddit back in the page that is there, and changes the
    address, so there is no page to come into. Browse Mode Caret Fix put the caret back on the post's link, without
    saying it.
  - Edge keeps the pages you leave (its back/forward cache), and NVDA keeps reading them. Going back to one, Browse
    Mode Caret Fix gave NVDA the page's focus itself (api.setFocusObject) to put the caret back, so NVDA took the
    browser's own focus event for the one it had and dropped it, and never came into the page.
  - Going forward to a kept page, the browser's focus moved into it without a focus event NVDA got, so NVDA's focus
    stayed in the page you had left.
  So once the page and the caret are still, after Browse Mode Caret Fix has put the caret back, and nothing NVDA said
  since the key named the page's title or the line at the caret: in the same page with another address, NVDA reads
  the line at the caret; in another page NVDA's focus was moved to, NVDA says the page's title and the line at the
  caret, as it does coming into a page (NVDA's own event for a page it never came into; for one it had, NVDA's own
  says the title only when its focus came from outside the page, and after Browse Mode Caret Fix's it said the line
  alone); and where NVDA's focus is still in the page you left but the browser's isn't, NVDA takes the browser's focus
  with a focus event of its own (eventHandler.queueEvent), and comes into that page as it does for any focus event.

The line is said as JAWS's SayLine says it, without the regions and lists it is in (issue 38: after reddit drew the
subreddit in a new main region, NVDA said "main region end, main region" before the line): see readLine.

What NVDA says itself isn't said again: a page that loads is read by NVDA as before, and so is a link the page moves
the focus to. Another key before the page is back, or going to another program, ends it. Only Edge, Chrome and
Firefox, the browsers JAWS's scripts bind the keys in. It works while the assistant runs, unless it is turned off in
NVDA's Settings, JAWS Migration Assistant. Braille shows "Back" and "Forward" as NVDA shows its messages.
"""

from __future__ import annotations

import sys
import threading
import time

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "backForwardAsJaws"
#: The names NVDA gives the app modules of the browsers JAWS's scripts bind GoBack and GoForward in: msedge.jkm,
#: Chrome.jkm and firefox.jkm.
BROWSERS = frozenset(("msedge", "chrome", "firefox"))
#: The keys: JAWS binds Alt+LeftArrow and Alt+ExtendedLeftArrow, which NVDA calls alt+leftArrow either way.
KEYS = {"alt+leftarrow": -1, "alt+rightarrow": 1}
#: What JAWS says: msgBack1_L and msgForward1_L in its ie.jsm, which IA2Browser.jss includes.
BACK, FORWARD = "Back", "Forward"
#: How often NVDA looks at the page, in milliseconds, and how long it waits for the page to be back, in seconds.
LOOK_EVERY = 100
WAIT = 6.0
#: How long the page and browse mode's caret must stay the same before the line is read, in seconds.
STILL_FOR = 0.35
#: How long after the key NVDA's focus may stay in the page you left before NVDA asks where the browser's focus is.
STALE_AFTER = 0.8
#: The Browse Mode Caret Fix add-on's module, and what it holds while it is still to put the caret back.
CARET_FIX = "globalPlugins.browseModeCaretFix"
CARET_FIX_PENDING = "_pendingNavigation"

_enabled = False
_failed = False
_lock = threading.RLock()
#: Whether decideGesture is registered with NVDA's decide_executeGesture, and heard with NVDA's pre_speech.
_deciding = False
_hearing = False
#: The keys, braille display keys and touch gestures NVDA got, counted, so a wait ends at the next one.
_gestures = 0
#: The page being waited for, while it is: see _Wait.
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
	"""Whether Alt+Left and Alt+Right in a web browser work as in JAWS: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have Alt+Left and Alt+Right in a web browser work as in JAWS, from now on."""
	global _enabled, _deciding, _hearing
	with _lock:
		if _enabled:
			return
		try:
			import inputCore

			if not _deciding:
				inputCore.decide_executeGesture.register(decideGesture)
				_deciding = True
		except Exception:
			_failure("can't say Back and Forward as JAWS does, so NVDA says nothing for Alt+Left and Alt+Right")
			return
		try:
			from speech.extensions import pre_speech

			if not _hearing:
				pre_speech.register(heard)
				_hearing = True
		except Exception:
			# Without it, NVDA can't tell what it said itself: it says "Back" and "Forward", and reads nothing more.
			_failure("can't hear what NVDA says after Back and Forward, so NVDA reads no page after them")
		_enabled = True


def unregister() -> None:
	"""Leave Alt+Left and Alt+Right to NVDA again."""
	global _enabled, _deciding, _hearing, _waiting
	with _lock:
		_enabled = False
		_waiting = None
		if _deciding:
			try:
				import inputCore

				inputCore.decide_executeGesture.unregister(decideGesture)
			except Exception:
				pass
			_deciding = False
		if _hearing:
			try:
				from speech.extensions import pre_speech

				pre_speech.unregister(heard)
			except Exception:
				pass
			_hearing = False


def isRegistered() -> bool:
	return _enabled


def direction(gesture) -> int:
	"""-1 for Alt+Left, 1 for Alt+Right, 0 for any other gesture."""
	for identifier in getattr(gesture, "normalizedIdentifiers", None) or ():
		if not isinstance(identifier, str) or ":" not in identifier:
			continue
		# "kb:alt+leftarrow", or "kb(laptop):alt+leftarrow" for one keyboard layout.
		found = KEYS.get(identifier.split(":", 1)[1].lower())
		if found:
			return found
	return 0


def inBrowser(obj) -> bool:
	"""Whether ``obj`` is in Edge, Chrome or Firefox."""
	return getattr(getattr(obj, "appModule", None), "appName", None) in BROWSERS


def decideGesture(gesture=None, **kwargs) -> bool:
	"""NVDA's decide_executeGesture handler: note Alt+Left and Alt+Right in a browser, and any other key.

	Every gesture goes on as NVDA decides (True): the key goes to the browser. It runs in NVDA's keyboard thread: what
	it does runs in NVDA's core.
	"""
	global _gestures
	if gesture is None or getattr(gesture, "isModifier", False):
		# Shift, Control, Alt or NVDA's key pressed alone, on its way to a key press: not another key yet.
		return True
	_gestures += 1
	if not _enabled:
		return True
	try:
		goes = direction(gesture)
		if not goes:
			return True
		import api
		import inputCore

		if inputCore.manager.isInputHelpActive:
			return True
		focus = api.getFocusObject()
		if focus is None or getattr(focus, "sleepMode", False) or not inBrowser(focus):
			return True
		if gesture.script is not None:
			# NVDA or an add-on has a command for the key here: it does what that command does.
			return True
		import queueHandler

		queueHandler.queueFunction(queueHandler.eventQueue, pressed, goes, _gestures)
	except Exception:
		_failure("could not tell whether Alt+Left or Alt+Right was pressed in a browser")
	return True


def heard(speechSequence=None, **kwargs) -> None:
	"""NVDA's pre_speech handler: while a page is waited for, note the words NVDA says. It never keeps NVDA from speaking."""
	wait = _waiting
	if wait is None or not speechSequence:
		return
	try:
		wait.said.extend(" ".join(item.split()) for item in speechSequence if isinstance(item, str) and item.strip())
	except Exception:
		pass


# -- the key --------------------------------------------------------------------------------------------------------


def _document(obj):
	"""The browse mode document ``obj`` is in, or None."""
	import browseMode

	document = getattr(obj, "treeInterceptor", None)
	return document if isinstance(document, browseMode.BrowseModeDocumentTreeInterceptor) else None


def address(document):
	"""The address of the page ``document`` shows, or None where NVDA can't tell it."""
	try:
		found = document.documentConstantIdentifier
	except Exception:
		return None
	return found if isinstance(found, str) and found else None


def pressed(goes: int, pressedAt: int) -> None:
	"""Alt+Left (``goes`` -1) or Alt+Right (1) went to the browser: say "Back" or "Forward", leave focus mode, and wait
	for the page. ``pressedAt`` is the count of gestures at the key: a key pressed since ends it."""
	global _waiting
	if not _enabled or _gestures != pressedAt:
		return
	try:
		import api
		import ui

		focus = api.getFocusObject()
		if not inBrowser(focus):
			return
		ui.message(BACK if goes < 0 else FORWARD)
		document = _document(focus)
		if document is None:
			# In the browser's own controls, such as its address bar: JAWS says the word, and there is no page to read.
			_waiting = None
			return
		if document.passThrough:
			import browseMode

			# IA2Browser.jss GoBack: "Forms Mode doesn't automatically turn off when going either back or forward on
			# pages." A new page comes in browse mode; a page that stays, as reddit's does, is left in it too.
			document.passThrough = False
			browseMode.reportPassThrough(document)
			_debug("jawsMigrator: NVDA leaves focus mode for Back or Forward, as JAWS turns forms mode off")
		_waiting = _Wait(goes, pressedAt, document)
		_later(pressedAt)
	except Exception:
		_failure("could not say Back or Forward as JAWS does")


# -- the page -------------------------------------------------------------------------------------------------------


class _Wait:
	"""The page NVDA is waiting for after Alt+Left or Alt+Right."""

	def __init__(self, goes: int, pressedAt: int, document):
		self.goes = goes
		self.pressedAt = pressedAt
		#: The page you were in, and its address.
		self.document = document
		self.address = address(document)
		self.started = time.monotonic()
		self.deadline = self.started + WAIT
		#: What NVDA has said since the key, each word or phrase with its spaces made single.
		self.said = []
		#: Whether the page changed (another page, or another address), the page NVDA's focus is in, where browse mode's
		#: caret is and what its line says, and since when.
		self.changed = False
		self.page = None
		self.caret = None
		self.since = None
		#: Whether NVDA has asked where the browser's focus is.
		self.askedFocus = False


def _later(pressedAt: int) -> None:
	import core

	core.callLater(LOOK_EVERY, look, pressedAt)


def caretFixPending() -> bool:
	"""Whether the Browse Mode Caret Fix add-on is still to put browse mode's caret back (it tries for 5 seconds)."""
	module = sys.modules.get(CARET_FIX)
	return module is not None and getattr(module, CARET_FIX_PENDING, None) is not None


def caretAndLine(document):
	"""Where browse mode's caret is in ``document``, and the text of its line, to tell when they stop changing."""
	import textInfos

	info = document.makeTextInfo(textInfos.POSITION_CARET)
	bookmark = info.bookmark
	info.expand(textInfos.UNIT_LINE)
	return (bookmark, info.text)


def saidOneOf(said, texts) -> bool:
	"""Whether NVDA said one of ``texts`` (a page's title, the line at its caret), or what it says, since the key."""
	wanted = [" ".join(text.split()) for text in texts if isinstance(text, str) and text.strip()]
	return any(text in item for item in said for text in wanted)


def _stop(why: str) -> None:
	global _waiting
	_waiting = None
	_debug(f"jawsMigrator: after Back or Forward, {why}")


def look(pressedAt: int) -> None:
	"""Look at the page NVDA is waiting for after Alt+Left or Alt+Right, and have NVDA read it once it is back and still,
	unless NVDA has."""
	wait = _waiting
	if not _enabled or wait is None or wait.pressedAt != pressedAt:
		return
	if _gestures != pressedAt:
		_stop("another key came first, so NVDA reads nothing more")
		return
	try:
		import api

		now = time.monotonic()
		focus = api.getFocusObject()
		if not inBrowser(focus):
			_stop("the focus left the browser")
			return
		document = _document(focus)
		if document is None:
			_stop("NVDA's focus is in the browser's own controls, which NVDA says as the focus moves there")
			return
		if not getattr(document, "isAlive", True) or document.passThrough:
			_stop("the page is gone or in focus mode, where NVDA says the focus")
			return
		if not wait.changed:
			if document is wait.document and address(document) == wait.address:
				if not wait.askedFocus and now - wait.started >= STALE_AFTER and not caretFixPending():
					wait.askedFocus = True
					takeBrowsersFocus(focus, document)
				if now < wait.deadline:
					_later(pressedAt)
				else:
					_stop("the page's address didn't change, so there is nothing new to read")
				return
			wait.changed = True
		caret = caretAndLine(document)
		if document is not wait.page or caret != wait.caret:
			wait.page, wait.caret, wait.since = document, caret, now
		ready = getattr(document, "isReady", True)
		if not (ready and now - wait.since >= STILL_FOR and not caretFixPending()):
			if now < wait.deadline:
				_later(pressedAt)
			else:
				_stop("the page didn't stop changing, so NVDA reads nothing more")
			return
		title = getattr(getattr(document, "rootNVDAObject", None), "name", None)
		if saidOneOf(wait.said, (title, caret[1])):
			_stop(f"NVDA said the page or the line at its caret itself: {caret[1][:80]!r}")
			return
		if document is wait.document:
			readLine(document)
			_stop(f"the page changed its address without loading, so NVDA reads the line at the caret, as JAWS reads the line at its cursor: {caret[1][:80]!r}")
		else:
			comeInto(document)
			_stop(f"NVDA's focus went to another page without NVDA coming into it, so NVDA comes into it now, its title and the line at the caret, as JAWS reads a page you go back to: {title!r}")
	except Exception:
		_failure("could not read the page after Back or Forward")
		_stop("NVDA reads nothing more")


def takeBrowsersFocus(focus, document) -> bool:
	"""NVDA's focus is still in the page you left: when the browser's focus is in another page or its own controls,
	NVDA gets a focus event for it, as it would from the browser, and says it as it does for any focus event."""
	from NVDAObjects import NVDAObject

	actual = NVDAObject.objectWithFocus()
	if actual is None or not inBrowser(actual) or actual == focus:
		return False
	if _document(actual) is document:
		# Still in the same page: NVDA's focus isn't behind.
		return False
	import eventHandler

	eventHandler.queueEvent("gainFocus", actual)
	_debug("jawsMigrator: after Back or Forward, NVDA's focus was still in the page you left, so NVDA takes the browser's focus, as from a focus event of the browser's")
	return True


def comeInto(document) -> None:
	"""NVDA comes into ``document``, which its focus went to without NVDA doing so: the page's title and the line at the
	caret, as JAWS says a page you go back to."""
	if not getattr(document, "_hadFirstGainFocus", True):
		# A page NVDA never came into: NVDA's own event, as eventHandler.doPreGainFocus calls it, which also puts the
		# caret where NVDA left it and says the page and its line.
		document.event_treeInterceptor_gainFocus()
		return
	# A page NVDA came into before, which Edge kept. NVDA's own event says its title only when NVDA's focus came from
	# outside it (api.getFocusDifferenceLevel), and after Browse Mode Caret Fix's focus NVDA takes it that it didn't:
	# live, NVDA said the line alone. The page is said as NVDA says a page it comes into, then the line.
	import speech
	from controlTypes import OutputReason

	speech.speakObject(document.rootNVDAObject, reason=OutputReason.FOCUS)
	readLine(document)
	try:
		import braille

		braille.handler.handleGainFocus(document)
	except Exception:
		pass


def readLine(document) -> None:
	"""Say the line at browse mode's caret in ``document`` as JAWS's SayLine does after Back and Forward, and as
	NVDA+Up Arrow says it: what is in the line, without the regions, lists and articles it is in.

	NVDA says a region or a list a line is in when the line it said before was outside it, and where one ends when the
	line is outside it (speech.getTextInfoSpeech compares the line's fields with the ones it kept,
	SpeakTextInfoState). The ones it kept are those of the page you left. Reddit draws the subreddit in a new main
	region, which NVDA can't tell from another one, so the tester's NVDA said "main region end, main region, heading,
	level 2, visited, link, Downgrading is a nightmare" (issue 38). JAWS's DocumentLoadedEvent calls SayLine after
	GoBack and GoForward (Default.jss, BackForward), and SayLine says no region. JAWS 2026, run live on a plain
	two-page site, said "Back", "Going back", "Plain page one", then "visited heading level 2 Link Go to page two"; in
	3 of 5 runs it said the title of the page it had left and "main region end" first, as it read before the page was
	back, and never "main region". So NVDA keeps the line's own fields first (OutputReason.ONLYCACHE, which says
	nothing), then reads the line. The fields after it are said as before: a region the next line is out of, or in."""
	import speech
	import textInfos
	from controlTypes import OutputReason

	info = document.makeTextInfo(textInfos.POSITION_CARET)
	info.expand(textInfos.UNIT_LINE)
	speech.speakTextInfo(info, unit=textInfos.UNIT_LINE, reason=OutputReason.ONLYCACHE)
	speech.speakTextInfo(info, unit=textInfos.UNIT_LINE, reason=OutputReason.CARET)
