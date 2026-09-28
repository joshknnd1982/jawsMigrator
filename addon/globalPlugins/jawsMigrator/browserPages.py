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

With 1.31 the tester switched to Edge with Alt+Tab (issue 30 again), and NVDA still said "document" after a GitHub
page's title. The focus was in the page's comment box, so NVDA said the page as a place the focus is in (reason
FOCUSENTERED, from NVDAObject.event_focusEntered), not as the focus, which is all 1.31 looked at. JAWS said the title
alone, then "MainRegion", "new Comment group" and the focused button. Now a page is said by its title for either
reason, when it is the page itself (its tree interceptor's root), not a frame in it.

When the tester chose their reddit tab in Alt+Tab, Edge first put the focus back where it was in the tab it was
leaving, the GitHub comment box, then moved it to the reddit page. NVDA said the window, the GitHub page, "main
landmark", "new Comment grouping" and the comment box, all of it twice, then the reddit page's title twice. JAWS said
only the reddit page's title. NVDA's speech manager drops what NVDA says for the focus once the focus has moved on
(eventHandler.FocusLossCancellableSpeechCommand), but not what it says for the places the focus is in: those stay
worth saying unless they had the focus themselves. So in Edge and Chrome, what NVDA says for a place the focus is in
now comes with a command of the assistant's own that drops it, if NVDA hasn't said it yet, once the focus isn't in
that place any more. And a window's name or a page's title isn't said again while NVDA is still saying it.

With 1.33 the tester Alt+Tabbed to a reddit window NVDA hadn't read yet (issue 30 again), and NVDA said its name,
the page's title, then "same page link Skip to main content", the page's first line. JAWS 2026, on a copy of the page,
said the window's name and the title and no line. Coming back to a page, JAWS does say the line at its cursor ("same
page link Skip to main content", when it was left there), as NVDA does. But JAWS's cursor starts on the page's title,
which is what JAWS says as the top line (Control+Home says the title), where NVDA's caret starts on the page's first
line. So the first time NVDA comes into an Edge or Chrome page in browse mode, with the focus on the page itself and
its caret on the first line, NVDA says the title and not that line, which it says as you come into a page
(browseMode.BrowseModeDocumentTreeInterceptor.event_treeInterceptor_gainFocus). A page whose caret starts further
down, coming back to a page, focus mode, "Automatic Say All on page load" and every other program are as before.

Since then that first line was never said at all (found running JAWS and NVDA side by side on six sites, issue 35):
NVDA's caret stayed on it, so the first Down Arrow read the second line, where JAWS's first Down Arrow goes from the
title to the first line ("same page link Skip to content" on BBC News). And NVDA's H, K, B and the other quick
navigation keys, and Tab, look for the next element after the caret, so an element the first line starts with was
skipped: on Amazon, H after the page opened went to the second heading, "Keyboard shortcuts", where JAWS's H said the
first, "Skip to, heading level 2", and on BBC News Tab went to "Open menu", where JAWS's went to "Skip to content". Now,
while the caret is still where it was when NVDA held that line back: the Down Arrow says the first line, as JAWS's
does, and leaves the caret there, so the next Down Arrow reads the second line; a quick navigation key or Tab goes to
an element that starts where the caret is (CursorManager._caretMovementScriptHelper, BrowseModeTreeInterceptor.
_quickNavScript and BrowseModeDocumentTreeInterceptor._tabOverride, put on the same classes as the event), and JAWS's
Say Next Sentence says the line's first sentence (see browseSentences). Anything else, and the same keys once the
caret has moved, are as NVDA has them.
"""

from __future__ import annotations

import contextlib
import functools
import importlib
import threading

from . import speechQueue

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
#: NVDA's browse mode event for a page it comes into (browseMode.BrowseModeDocumentTreeInterceptor), which the
#: classes of Edge's and Chrome's pages take from it: through IAccessible2, and through UI Automation. The assistant
#: puts its own on those classes (outlookMessages has the one of browseMode's class).
GAIN_FOCUS = "event_treeInterceptor_gainFocus"
PAGE_CLASSES = (
	("NVDAObjects.IAccessible.chromium", "ChromeVBuf"),
	("NVDAObjects.UIA.chromium", "ChromiumUIATreeInterceptor"),
)
#: What moves browse mode's caret by a line (cursorManager.CursorManager, the Down Arrow), what moves it to the next
#: element of a kind (browseMode.BrowseModeTreeInterceptor, the quick navigation keys) and what Tab does in browse mode
#: (browseMode.BrowseModeDocumentTreeInterceptor). The assistant puts its own on the same classes, for the page's first
#: line NVDA held back as the page opened (no other part of the assistant changes these).
CARET_MOVEMENT = "_caretMovementScriptHelper"
QUICK_NAV = "_quickNavScript"
TAB = "_tabOverride"
#: Where the page keeps the start of the first line NVDA held back, until its caret moves.
UNSAID = "_jawsMigratorUnsaidFirstLine"
#: Quick navigation's kinds that aren't elements of the page (NVDA finds them another way): its first line is said as NVDA
#: says it for them.
TEXT_ITEM_TYPES = frozenset(("notLinkBlock", "textParagraph", "verticalParagraph", "sameStyle", "differentStyle"))
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)]. NVDA's is None
#: where the class had none of its own and took it from the class it comes from.
_replaced: list = []
#: NVDA's roles and output reasons used here, once known.
_windowRole = None
_regionRole = None
_documentRole = None
_focus = None
_focusEntered = None
_query = None
#: NVDA's OutputReason.CARET, textInfos.UNIT_LINE and textInfos.POSITION_FIRST, once known.
_caret = None
_line = None
_first = None
#: textInfos.POSITION_CARET, once known.
_caretPosition = None
#: The window's name and the page's title NVDA was last asked to say, with the commands NVDA's speech manager keeps
#: with them until they are said: {WINDOW or PAGE: (name, commands)}.
_lastSaid: dict = {}
#: The assistant's command that drops what NVDA says for a place the focus is in, once the focus has left it: a class
#: made the first time it is needed, from NVDA's speech.commands._CancellableSpeechCommand.
_whileInItClass = None


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
	global _enabled, _windowRole, _regionRole, _documentRole, _focus, _focusEntered, _query, _caret, _line, _first
	global _caretPosition
	if _enabled:
		return
	try:
		import speech
		import textInfos
		from controlTypes import OutputReason, Role

		_windowRole, _regionRole, _documentRole = Role.WINDOW, Role.REGION, Role.DOCUMENT
		_focus, _focusEntered, _query = OutputReason.FOCUS, OutputReason.FOCUSENTERED, OutputReason.QUERY
		_caret, _line = getattr(OutputReason, "CARET", None), getattr(textInfos, "UNIT_LINE", None)
		_first = getattr(textInfos, "POSITION_FIRST", None)
		_caretPosition = getattr(textInfos, "POSITION_CARET", None)
		with _lock:
			if not _replace(speech):
				return
			for moduleName, className in PAGE_CLASSES if None not in (_caret, _line, _first) else ():
				try:
					owner = getattr(importlib.import_module(moduleName), className)
				except Exception:
					# Not in this NVDA: its pages are said as before.
					continue
				if _addGainFocus(owner) and _caretPosition is not None:
					_addFirstLineKeys(owner)
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
				if vars(owner).get(name) is not installed:
					continue
				if original is None:
					# The class had none of its own: it takes the one of the class it comes from again.
					delattr(owner, name)
				else:
					setattr(owner, name, original)
			except Exception:
				pass
		_replaced.clear()
	_lastSaid.clear()


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


def inBrowser(obj) -> bool:
	"""Whether ``obj`` is in Edge or Chrome."""
	return getattr(getattr(obj, "appModule", None), "appName", None) in BROWSERS


def _isPageItself(obj) -> bool:
	"""Whether ``obj``, a document, is the page itself (its tree interceptor's root), not a frame in the page."""
	treeInterceptor = getattr(obj, "treeInterceptor", None)
	root = getattr(treeInterceptor, "rootNVDAObject", None)
	return root is not None and (root is obj or root == obj)


def kindOf(obj, reason) -> str | None:
	"""What NVDA is about to say for ``reason``: an Edge or Chrome window (WINDOW), Edge's frame around a page (FRAME),
	a page (PAGE), or None for anything else, which NVDA says as it does."""
	if not inBrowser(obj):
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
	if role == _documentRole and obj.name:
		# The page as the focus (it opened, or you came back to it in browse mode), or as a place the focus is in (you
		# came back to a field in it).
		if reason == _focus or (reason == _focusEntered and _isPageItself(obj)):
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


# -- what NVDA says for a place the focus is in -------------------------------------------------------------------


def isAroundFocus(obj) -> bool:
	"""Whether the focus is ``obj`` or in it, or ``obj`` is the window in front: what NVDA says for it is still worth
	saying. True when it can't be told, so nothing is dropped by mistake."""
	try:
		import api

		focus = api.getFocusObject()
		if obj is focus or obj == focus:
			return True
		for ancestor in api.getFocusAncestors():
			if obj is ancestor or obj == ancestor:
				return True
		foreground = api.getForegroundObject()
		return obj is foreground or obj == foreground
	except Exception:
		return True


def whileInItClass():
	"""The assistant's command for what NVDA says for a place the focus is in, made from NVDA's own command."""
	global _whileInItClass
	from speech.commands import _CancellableSpeechCommand

	# Made again if NVDA's own command isn't the one it was made from, or NVDA's speech manager wouldn't know it.
	if _whileInItClass is None or not issubclass(_whileInItClass, _CancellableSpeechCommand):

		class WhileInIt(_CancellableSpeechCommand):
			"""NVDA's speech manager drops the speech this is in, if it hasn't said it yet, once the focus has left the
			place it is about (FocusLossCancellableSpeechCommand does that only for the focus itself)."""

			def __init__(self, obj, words: str = ""):
				self._obj = obj
				self._words = words
				self._noted = False
				super().__init__()

			def _checkIfValid(self) -> bool:
				valid = isAroundFocus(self._obj)
				if not valid and not self._noted:
					self._noted = True
					_debug(f"jawsMigrator: the focus has left {self._words!r}, so NVDA doesn't say it if it hasn't yet, as JAWS doesn't")
				return valid

			def _getDevInfo(self) -> str:
				return f"jawsMigrator: the focus is in it: {isAroundFocus(self._obj)}"

			def __repr__(self):
				return f"CancellableSpeech ({'cancelled' if self._checkIfCancelled() else 'still valid'}, jawsMigrator: while the focus is in it)"

		_whileInItClass = WhileInIt
	return _whileInItClass


def withWhileInIt(sequence: list, obj) -> list:
	"""``sequence``, what NVDA says for a place the focus is in, with the assistant's command that drops it once the
	focus has left. Only where NVDA's speech manager drops speech for the focus (NVDA's own command is in it), and
	while the focus is there."""
	if not speechQueue.cancellables(sequence) or not isAroundFocus(obj):
		return sequence
	return [*sequence, whileInItClass()(obj, _words(sequence))]


# -- a name NVDA is still saying ------------------------------------------------------------------------------------


def stillSaying(kind: str, name: str) -> bool:
	"""Whether NVDA is still saying, or has yet to say, the same window's name or page's title."""
	last = _lastSaid.get(kind)
	return bool(last) and last[0] == name and speechQueue.stillToSay(last[1])


def _remember(kind: str, name: str, sequence) -> None:
	_lastSaid[kind] = (name, speechQueue.cancellables(sequence))


def _guarded(original):
	"""NVDA's speakObject: Edge's and Chrome's windows and pages as JAWS says them, anything else as NVDA says it."""

	@functools.wraps(original)
	def speakObject(obj, *args, **kwargs):
		if not _enabled:
			return original(obj, *args, **kwargs)
		reason = _argument(args, kwargs, "reason", 0, _query)
		try:
			kind = kindOf(obj, reason)
			entered = reason == _focusEntered and inBrowser(obj)
		except Exception:
			_failure("could not tell whether NVDA is saying an Edge or Chrome window or page")
			kind, entered = None, False
		if kind is None and not entered:
			return original(obj, *args, **kwargs)
		if kind == FRAME:
			_debug(f"jawsMigrator: NVDA doesn't say the browser's frame around the page, as JAWS doesn't: {obj.name!r} region")
			return None
		# NVDA's speakObject, word for word, with the words JAWS doesn't say taken out.
		from speech import speech

		sequence = speech.getObjectSpeech(obj, reason, _argument(args, kwargs, "_prefixSpeechCommand", 1))
		said = list(sequence)
		try:
			if kind is not None:
				said = withoutWords(sequence, obj, kind)
				if said != list(sequence):
					_debug(f"jawsMigrator: the browser's {kind} is said as JAWS says it: {_words(said)} (NVDA's: {_words(sequence)})")
			if entered:
				said = withWhileInIt(said, obj)
			if kind in (WINDOW, PAGE) and said and stillSaying(kind, obj.name):
				_debug(f"jawsMigrator: NVDA is still saying the browser's {kind}, so it isn't said again, as JAWS says it once: {_words(said)}")
				return None
		except Exception:
			_failure("could not say an Edge or Chrome window or page as JAWS says it")
			said = list(sequence)
		if said:
			speech.speak(said, priority=_argument(args, kwargs, "priority", 2))
			if kind in (WINDOW, PAGE):
				try:
					_remember(kind, obj.name, said)
				except Exception:
					pass
		return None

	setattr(speakObject, MARK, _TOKEN)
	setattr(speakObject, ORIGINAL, original)
	return speakObject


# -- a page's first line --------------------------------------------------------------------------------------------


def _addGainFocus(owner) -> bool:
	"""Give ``owner``, the class of Edge's and Chrome's pages, the assistant's event for a page NVDA comes into, which
	does what the one it comes from does, and holds back the page's first line the first time. True when it is there."""
	current = vars(owner).get(GAIN_FOCUS)
	if _isOurs(current):
		return True
	if current is not None:
		# The class has one of its own (another add-on's): the page's first line is said as it says it.
		_debug(f"jawsMigrator: {getattr(owner, '__name__', owner)} has its own {GAIN_FOCUS}, so a page's first line is said as before")
		return False
	installed = _gainFocusGuarded(owner)
	setattr(owner, GAIN_FOCUS, installed)
	_replaced.append((owner, GAIN_FOCUS, installed, None))
	return True


def _addFirstLineKeys(owner) -> None:
	"""Give ``owner`` the assistant's Down Arrow, quick navigation and Tab for the first line NVDA held back, which do
	what the ones it comes from do otherwise. A class with one of its own (another add-on's) keeps it."""
	for name, guarded in ((CARET_MOVEMENT, _caretMovementGuarded), (QUICK_NAV, _quickNavGuarded), (TAB, _tabGuarded)):
		current = vars(owner).get(name)
		if _isOurs(current):
			continue
		if current is not None or not callable(getattr(owner, name, None)):
			_debug(f"jawsMigrator: {getattr(owner, '__name__', owner)} has its own {name}, or none, so it is as before")
			continue
		installed = guarded(owner)
		setattr(owner, name, installed)
		_replaced.append((owner, name, installed, None))


def isFirstLine(page, info, args: tuple, kwargs: dict) -> bool:
	"""Whether NVDA is saying ``info`` as the line at the caret of ``page``, an Edge or Chrome page in browse mode with
	the focus on the page itself and the caret on its first line."""
	if getattr(info, "obj", None) is not page:
		return False
	if _argument(args, kwargs, "reason", 3) != _caret or _argument(args, kwargs, "unit", 2) != _line:
		return False
	if getattr(page, "passThrough", False):
		return False
	root = getattr(page, "rootNVDAObject", None)
	if root is None or not inBrowser(root):
		return False
	import api

	focus = api.getFocusObject()
	if not (focus is root or focus == root):
		return False
	return info.compareEndPoints(page.makeTextInfo(_first), "startToStart") == 0


@contextlib.contextmanager
def _firstLineHeldBack(page, held: list):
	"""While NVDA comes into ``page``, the page's first line isn't said; ``held`` gets it instead."""
	import speech

	current = speech.speakTextInfo

	def speakTextInfo(info, *args, **kwargs):
		if not held:
			try:
				first = isFirstLine(page, info, args, kwargs)
			except Exception:
				_failure("could not tell whether NVDA was saying a page's first line, so NVDA says it")
				first = False
			if first:
				held.append(info)
				return False
		return current(info, *args, **kwargs)

	speech.speakTextInfo = speakTextInfo
	try:
		yield
	finally:
		if speech.speakTextInfo is speakTextInfo:
			speech.speakTextInfo = current


def _gainFocusGuarded(owner):
	"""NVDA's browse mode coming into an Edge or Chrome page: the first time, the page's title without its first line."""

	def event_treeInterceptor_gainFocus(self, *args, **kwargs):
		base = getattr(super(owner, self), GAIN_FOCUS)
		if not _enabled or getattr(self, "_hadFirstGainFocus", True):
			return base(*args, **kwargs)
		held = []
		try:
			with _firstLineHeldBack(self, held):
				return base(*args, **kwargs)
		finally:
			if held:
				try:
					text = held[0].text
				except Exception:
					text = ""
				_keepFirstLine(self, held[0])
				_debug(
					f"jawsMigrator: NVDA came into the page for the first time with its caret on the first line, so it says the page's title without that line, as JAWS, whose cursor starts on the title: {text[:80]!r}",
				)

	event_treeInterceptor_gainFocus.__name__ = GAIN_FOCUS
	setattr(event_treeInterceptor_gainFocus, MARK, _TOKEN)
	return event_treeInterceptor_gainFocus


# -- the first line NVDA held back -------------------------------------------------------------------------------------


def _keepFirstLine(page, line) -> None:
	"""Keep where the first line NVDA held back starts, on ``page``, until its caret moves."""
	try:
		start = line.copy()
		start.collapse()
		setattr(page, UNSAID, start)
	except Exception:
		_failure("could not keep where a page's first line starts, so the keys after it are as NVDA has them")


def _forget(page) -> None:
	try:
		if vars(page).get(UNSAID) is not None:
			setattr(page, UNSAID, None)
	except Exception:
		pass


def forgetFirstLine(page) -> None:
	"""Forget the first line NVDA held back as ``page`` opened, once another key has read from it (browseSentences)."""
	_forget(page)


def unsaidFirstLine(page):
	"""Where the first line NVDA held back as ``page`` opened starts, while browse mode's caret is still there; else None
	(and the page forgets it)."""
	try:
		start = vars(page).get(UNSAID)
	except TypeError:
		return None
	if start is None:
		return None
	try:
		still = not getattr(page, "passThrough", False) and page.makeTextInfo(_caretPosition).compareEndPoints(start, "startToStart") == 0
	except Exception:
		still = False
	if not still:
		_forget(page)
		return None
	return start


def _startsAt(item, start) -> bool:
	try:
		return item.textInfo.compareEndPoints(start, "startToStart") == 0
	except Exception:
		return False


def _firstOfKind(page, itemType):
	"""The first element of ``itemType`` on ``page`` (NVDA's search from the top, as its Elements List does), or None."""
	try:
		return next(page._iterNodesByType(itemType, "next", None))
	except (StopIteration, NotImplementedError):
		return None
	except Exception:
		_failure(f"could not find the first {itemType} on a page, so the key is as NVDA has it")
		return None


def _caretMovementGuarded(owner):
	"""Browse mode's caret movement: the Down Arrow on the first line NVDA held back says that line, as JAWS's goes from
	the title to it; anything else as NVDA has it."""

	def _caretMovementScriptHelper(self, gesture, unit, direction=None, *args, **kwargs):
		base = getattr(super(owner, self), CARET_MOVEMENT)
		start = unsaidFirstLine(self) if _enabled else None
		if start is None:
			return base(gesture, unit, direction, *args, **kwargs)
		_forget(self)
		if unit != _line or direction != 1 or args or kwargs:
			return base(gesture, unit, direction, *args, **kwargs)
		from scriptHandler import isScriptWaiting, willSayAllResume

		if isScriptWaiting():
			# As NVDA's own: with more keys waiting, nothing is said or moved.
			return None
		import speech

		info = self.makeTextInfo(_caretPosition)
		info.expand(_line)
		if not willSayAllResume(gesture):
			speech.speakTextInfo(info, unit=_line, reason=_caret)
		_debug("jawsMigrator: the Down Arrow said the page's first line, which NVDA held back as the page opened, as JAWS's goes from the title to it")
		return None

	_caretMovementScriptHelper.__name__ = CARET_MOVEMENT
	setattr(_caretMovementScriptHelper, MARK, _TOKEN)
	return _caretMovementScriptHelper


def _quickNavGuarded(owner):
	"""Browse mode's quick navigation: from the first line NVDA held back, an element that starts where the caret is is
	the next one, as it is for JAWS, whose cursor is on the title above it; anything else as NVDA has it."""

	def _quickNavScript(self, gesture, itemType, direction, *args, **kwargs):
		base = getattr(super(owner, self), QUICK_NAV)
		start = unsaidFirstLine(self) if _enabled else None
		if start is None:
			return base(gesture, itemType, direction, *args, **kwargs)
		_forget(self)
		if direction != "next" or itemType in TEXT_ITEM_TYPES:
			return base(gesture, itemType, direction, *args, **kwargs)
		item = _firstOfKind(self, itemType)
		if item is None or not _startsAt(item, start):
			return base(gesture, itemType, direction, *args, **kwargs)
		readUnit = kwargs.get("readUnit", args[1] if len(args) > 1 else None)
		from scriptHandler import willSayAllResume

		# As NVDA's _quickNavScript does with the item it finds.
		if not gesture or not willSayAllResume(gesture):
			item.report(readUnit=readUnit)
		item.moveTo()
		_debug(f"jawsMigrator: quick navigation went to the {itemType} the page's first line starts with, which NVDA held back as the page opened")
		return None

	_quickNavScript.__name__ = QUICK_NAV
	setattr(_quickNavScript, MARK, _TOKEN)
	return _quickNavScript


def _tabGuarded(owner):
	"""Browse mode's Tab: from the first line NVDA held back, an element that can take the focus and starts where the
	caret is gets it, as it does for JAWS, whose cursor is on the title above it; anything else as NVDA has it."""

	def _tabOverride(self, direction, *args, **kwargs):
		base = getattr(super(owner, self), TAB)
		start = unsaidFirstLine(self) if _enabled else None
		if start is None:
			return base(direction, *args, **kwargs)
		_forget(self)
		if direction != "next" or getattr(self, "_lastCaretMoveWasFocus", False):
			return base(direction, *args, **kwargs)
		item = _firstOfKind(self, "focusable")
		if item is None or not _startsAt(item, start):
			return base(direction, *args, **kwargs)
		import api

		obj = item.obj
		# As NVDA's _tabOverride does with the element it finds.
		if obj == api.getFocusObject():
			import speech

			newCaret = item.textInfo.copy()
			newCaret.collapse()
			self._set_selection(newCaret, reason=_focus)
			if self.passThrough:
				obj.event_gainFocus()
			else:
				speech.speakTextInfo(item.textInfo, reason=_focus)
		else:
			obj.setFocus()
		_debug("jawsMigrator: Tab went to the element the page's first line starts with, which NVDA held back as the page opened")
		return True

	_tabOverride.__name__ = TAB
	setattr(_tabOverride, MARK, _TOKEN)
	return _tabOverride
