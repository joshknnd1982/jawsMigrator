# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""NVDA's Elements List (NVDA+F7) opens while a web page is still changing, as JAWS's lists do.

A tester opened the jawsMigrator page on github.com and pressed NVDA+F7 a quarter of a second after
NVDA said "Page ready", just as the page said "alert". NVDA fills its Elements List in two steps
(``browseMode.ElementsListDialog.initElementType``): it finds every link in its copy of the page (the
virtual buffer), then reads each link's name and states where it found it (``filter``, which reads
``virtualBuffers.VirtualBufferQuickNavItem.label``). GitHub changed the page in between, so a link was
no longer where NVDA had found it, and NVDA 2026.2 stopped with a LookupError
(``VirtualBufferTextInfo._getControlFieldAttribs``) halfway through making its dialog. The dialog was
left half made: its window existed with the focus in its list, but NVDA never showed it, never closed
it, and never gave the focus back (``script_elementsList`` stops before ``ShowModal``, ``Destroy`` and
``gui.mainFrame.postPopup``). NVDA said "Elements List dialog, tree view"; Enter in the list activated
the Issues link on the page behind it but left the list there; Escape did nothing, and neither did
NVDA+F7, because the focus wasn't on the page. The tester got out only with Alt+Tab. JAWS's Links List
(Insert+F7) comes up whatever the page does meanwhile.

So, while the assistant runs:

- A link, heading or other element that isn't where NVDA found it is looked for where it is now, by the
  identifier NVDA keeps for it, and its name and states are read there. Moving to it or activating it
  from the list goes there too. NVDA reads a heading's text without looking whether the heading is still
  there (a page that changed gave a wrong text rather than an error), so for a heading the assistant
  looks first.
- An element the page took away is left out of the list, as JAWS's Links List holds what is on the page;
  an element under it in the list (a heading under a heading) comes under the one above it. This holds when
  you type in the list's Filter box too, where NVDA reads every element's name again.
- When the page changed while NVDA filled the list, NVDA fills it again, so that the list shows the page
  as it is now: three times in all. If the page is still changing, the third list is the one shown. Only
  when filling the list fails three times for another reason is it left empty, and NVDA says why: the
  dialog still opens, and Escape closes it. (Version 1.17 left the list empty when the page took an element
  away each time; since 1.18 NVDA lists what is still there.)

The key that opens the list never reaches the program either, as JAWS's Insert+F7 never does. NVDA
has browse mode's commands only while a browse mode document is ready, and gives a key it has no command
for to the program, less NVDA's modifier. With 1.17 a tester pressed Alt+Left in Edge's Downloads panel,
whose document stopped being ready, and pressed NVDA+F7 three seconds later: Edge got F7, its key for
caret browsing, and asked "Turn on caret browsing?". So when a key of the Elements List (NVDA+F7, or one
the migration or you gave it, such as JAWS's Insert+F6) comes where NVDA has no browse mode document
ready, NVDA keeps it from the program. When the document is still loading, NVDA opens its list as soon as
it is ready, if that takes no more than three seconds and you press nothing else meanwhile; otherwise
NVDA says what JAWS says there: "This feature is only available from within a virtual document, such as
a page on the Internet." Where NVDA has a command for the key, NVDA runs it as always.

It needs no setting: while the page doesn't change, NVDA fills its list as it always does, with one
look at each heading's place added.
"""

from __future__ import annotations

import functools
import threading
import time

#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorElementsList"
#: Marks an element of the list (NVDA's VirtualBufferQuickNavItem) that the page took away.
GONE = "_jawsMigratorGone"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: How many times NVDA fills its Elements List before leaving it empty.
ATTEMPTS = 3
#: What NVDA says when the list is left empty, and how long after (in ms), so it comes after the dialog.
PAGE_CHANGED = "The page changed while NVDA listed its elements. Press Escape, then NVDA+F7 again."
SAY_AFTER = 800
#: Browse mode's script that opens the Elements List.
ELEMENTS_LIST = "elementsList"
#: What JAWS says for Insert+F7 where there is no virtual document (Virtual.jss, common.jsm), and NVDA with it.
NOT_IN_DOCUMENT = "This feature is only available from within a virtual document, such as a page on the Internet."
#: How long NVDA waits for a document that is still loading before it says that, and how often it looks, in ms.
WAIT_FOR_DOCUMENT = 3000
LOOK_EVERY = 100
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
#: How many elements have been found at another place than NVDA found them, or not found at all, since NVDA started.
_moved = 0
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: Whether decideGesture is registered with NVDA's decide_executeGesture.
_deciding = False
#: The keys, braille display keys and touch gestures NVDA got, counted, so a wait ends at the next one.
_gestures = 0


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


def register() -> None:
	"""Keep NVDA's Elements List working while a web page changes, from now on."""
	global _enabled
	if _enabled:
		return
	_enabled = True
	try:
		import virtualBuffers

		item = virtualBuffers.VirtualBufferQuickNavItem
		with _lock:
			_replace(item, "label", _labelGuarded, lambda value: isinstance(value, property) and value.fget is not None)
			_replace(item, "isChild", _isChildGuarded, callable)
	except Exception:
		_failure("can't look for an element of the Elements List where the page has moved it")
	try:
		import browseMode

		with _lock:
			_replace(browseMode.ElementsListDialog, "initElementType", _fillingGuarded, callable)
			_replace(browseMode.ElementsListDialog, "filter", _filterGuarded, callable)
	except Exception:
		_failure("can't keep NVDA's Elements List from being left half made")
	global _deciding
	try:
		import inputCore

		if not _deciding:
			inputCore.decide_executeGesture.register(decideGesture)
			_deciding = True
	except Exception:
		_failure("can't keep the Elements List's key from the program where NVDA has no browse mode document")


def unregister() -> None:
	"""Give NVDA its own Elements List back, where nothing has been put over the assistant's since."""
	global _enabled
	if not _enabled:
		return
	_enabled = False
	global _deciding
	if _deciding:
		try:
			import inputCore

			inputCore.decide_executeGesture.unregister(decideGesture)
		except Exception:
			pass
		_deciding = False
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


def _isOurs(value) -> bool:
	"""Whether ``value`` is the assistant's version, or wraps it (as another add-on's functools.wraps wrapper would)."""
	function = getattr(value, "fget", value)
	for _ in range(_MOST_WRAPPERS):
		if function is None:
			return False
		if getattr(function, MARK, None) is _TOKEN:
			return True
		function = getattr(function, "__wrapped__", None)
	return False


def _replace(owner, name: str, guarded, usable) -> bool:
	"""Put the assistant's version of ``name`` in the place of NVDA's own on ``owner``, once. True when it is there."""
	current = vars(owner).get(name)
	if _isOurs(current):
		# Still there from before: turned off and on again, or another add-on has put its own around it since.
		return True
	if current is None or not usable(current):
		_failure(f"NVDA has no {name} the assistant knows, so NVDA's Elements List works as NVDA's own")
		return False
	installed = guarded(current)
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, current))
	_log().debug(f"jawsMigrator: NVDA's Elements List opens while a web page changes ({getattr(owner, '__name__', owner)}.{name})")
	return True


def relocate(item) -> bool:
	"""Move ``item`` (NVDA's VirtualBufferQuickNavItem) to where its element is now in NVDA's copy of the page.

	NVDA knows the element by its identifier in the page, which stays the same when the page changes around it;
	only its place in the virtual buffer moves. True when it was found at another place than before. When the
	page has no element with that identifier any more, the element is marked as taken away (see isGone).
	"""
	global _moved
	try:
		from textInfos.offsets import Offsets

		docHandle, identifier = item.vbufFieldIdentifier
		try:
			start, end = item.textInfo._getOffsetsFromFieldIdentifier(docHandle, identifier)
		except LookupError:
			# Not in the page any more.
			_markGone(item)
			return False
		if (start, end) == (getattr(item.textInfo, "_startOffset", None), getattr(item.textInfo, "_endOffset", None)):
			return False
		item.textInfo = item.document.makeTextInfo(Offsets(start, end))
	except Exception:
		# The page itself is gone, or the element has no identifier.
		return False
	_moved += 1
	return True


def _markGone(item) -> None:
	"""Mark ``item`` as an element the page took away, or whose name can't be read anywhere, once."""
	global _moved
	try:
		if getattr(item, GONE, False):
			return
		setattr(item, GONE, True)
	except Exception:
		return
	_moved += 1


def isGone(item) -> bool:
	return bool(getattr(item, GONE, False))


def _labelGuarded(original):
	"""NVDA's label for an element in its Elements List, read where the element is now when the page moved it."""
	getter = original.fget

	@functools.wraps(getter)
	def label(self):
		if not _enabled:
			return getter(self)
		try:
			if getattr(self, "itemType", None) == "heading":
				# NVDA reads a heading's text where it found the heading, without looking whether the heading is still
				# there, so a heading the page moved gave part of another's text: the assistant looks where it is first.
				relocate(self)
				if isGone(self):
					raise LookupError("the page took the heading away")
			try:
				return getter(self)
			except LookupError:
				if not relocate(self):
					raise
			return getter(self)
		except LookupError:
			# Not where NVDA found it, and not anywhere else: the list leaves it out (see _filterGuarded).
			_markGone(self)
			raise

	setattr(label, MARK, _TOKEN)
	setattr(label, ORIGINAL, original)
	return property(label, doc=original.__doc__)


def _isChildGuarded(original):
	"""NVDA's check whether a heading comes under another, read where both are now when the page moved them."""

	@functools.wraps(original)
	def isChild(self, parent, *args, **kwargs):
		try:
			return original(self, parent, *args, **kwargs)
		except LookupError:
			if not _enabled:
				raise
			moved = relocate(self)
			moved = relocate(parent) or moved
			if isGone(self) or isGone(parent):
				# Nothing comes under an element the page took away, and one it took away is left out of the list.
				return False
			if not moved:
				raise
		return original(self, parent, *args, **kwargs)

	setattr(isChild, MARK, _TOKEN)
	setattr(isChild, ORIGINAL, original)
	return isChild


def _fillingGuarded(original):
	"""NVDA's filling of its Elements List, done again when the page changed meanwhile, never leaving the dialog half made."""

	@functools.wraps(original)
	def initElementType(self, *args, **kwargs):
		if not _enabled:
			return original(self, *args, **kwargs)
		for attempt in range(1, ATTEMPTS + 1):
			moved = _moved
			try:
				result = original(self, *args, **kwargs)
			except Exception:
				_log().debugWarning(
					f"jawsMigrator: NVDA could not fill its Elements List ({attempt} of {ATTEMPTS} tries); the page probably changed meanwhile",
					exc_info=True,
				)
				continue
			if _moved == moved or attempt == ATTEMPTS:
				return result
			_log().debug(f"jawsMigrator: the page changed while NVDA filled its Elements List, so NVDA fills it again ({attempt} of {ATTEMPTS} tries)")
		leaveEmpty(self)
		return None

	setattr(initElementType, MARK, _TOKEN)
	setattr(initElementType, ORIGINAL, original)
	return initElementType


def _filterGuarded(original):
	"""NVDA's filling of the list's tree from its elements, without the ones the page took away."""

	@functools.wraps(original)
	def filter(self, *args, **kwargs):
		while True:
			try:
				return original(self, *args, **kwargs)
			except LookupError:
				# Each time round, one element more is left out, so this ends.
				if not _enabled or not leaveOutGone(self):
					raise

	setattr(filter, MARK, _TOKEN)
	setattr(filter, ORIGINAL, original)
	return filter


def leaveOutGone(dialog) -> bool:
	"""Take the elements the page took away out of NVDA's Elements List ``dialog``. True when there were some.

	An element under one taken away comes under the nearest one above it that is still there, and when the
	element NVDA starts the list on was taken away, the one before it takes its place.
	"""
	elements = list(getattr(dialog, "_elements", None) or ())
	if not any(isGone(element.item) for element in elements):
		return False
	make = getattr(dialog, "Element", None) or type(elements[0])
	initial = getattr(dialog, "_initialElement", None)
	#: Each element of the list as it is now: a new one when its parent changed, None when it is left out.
	now = {}
	kept = []
	newInitial = None
	for element in elements:
		parent = element.parent
		while parent is not None and parent in now and now[parent] is None:
			parent = parent.parent
		if parent is not None:
			parent = now.get(parent, parent)
		if isGone(element.item):
			now[element] = None
		else:
			now[element] = element if parent is element.parent else make(element.item, parent)
			kept.append(now[element])
		if initial is not None and element is initial:
			newInitial = now[element] or (kept[-1] if kept else None)
	dialog._elements = kept
	dialog._initialElement = newInitial
	_log().debug(f"jawsMigrator: the page took away {len(elements) - len(kept)} element(s) of NVDA's Elements List, so the list leaves them out")
	return True


def leaveEmpty(dialog) -> None:
	"""Leave NVDA's Elements List ``dialog`` with nothing in it, as NVDA does when a page has nothing of a kind, and say why."""
	try:
		dialog._elements = []
		dialog._initialElement = None
		dialog.filterEdit.ChangeValue("")
		dialog.filter("", newElementType=True)
	except Exception:
		_failure("could not empty NVDA's Elements List")
	try:
		import wx

		wx.CallLater(SAY_AFTER, _sayPageChanged)
	except Exception:
		pass


def _sayPageChanged() -> None:
	try:
		import ui

		ui.message(PAGE_CHANGED)
	except Exception:
		pass


def _builtInGestures(cls) -> frozenset:
	"""The gestures NVDA itself gives browse mode's Elements List (NVDA+F7), normalized."""
	import inputCore

	gestures = vars(cls).get(f"_{cls.__name__}__gestures") or {}
	return frozenset(inputCore.normalizeGestureIdentifier(identifier) for identifier, name in gestures.items() if name == ELEMENTS_LIST)


def opensElementsList(gesture) -> bool:
	"""Whether ``gesture`` opens browse mode's Elements List: NVDA+F7, or a key the user or the migration gave it.

	Found as NVDA finds it (scriptHandler.getGlobalMapScripts): the user's gestures and the locale's first, then
	browse mode's own. A gesture the user took away from the Elements List doesn't count.
	"""
	import browseMode
	import inputCore

	cls = browseMode.BrowseModeTreeInterceptor
	identifiers = list(getattr(gesture, "normalizedIdentifiers", None) or ())
	for gestureMap in (getattr(inputCore.manager, "userGestureMap", None), getattr(inputCore.manager, "localeGestureMap", None)):
		if gestureMap is None:
			continue
		for identifier in identifiers:
			for boundClass, scriptName in gestureMap.getScriptsForGesture(identifier):
				if isinstance(boundClass, type) and (issubclass(cls, boundClass) or issubclass(boundClass, cls)):
					return scriptName == ELEMENTS_LIST
	builtIn = _builtInGestures(cls)
	return any(identifier in builtIn for identifier in identifiers)


def decideGesture(gesture=None, **kwargs) -> bool:
	"""NVDA's decide_executeGesture handler: False for a key of the Elements List that NVDA would give the program.

	Every other gesture goes on as NVDA decides (True), and so does this one where NVDA has a command for it, in
	input help and in sleep mode. It runs in NVDA's keyboard thread: what it does instead runs in NVDA's core.
	"""
	global _gestures
	if gesture is None or getattr(gesture, "isModifier", False):
		# Shift, Control, Alt or NVDA's key pressed alone, on its way to a key press: not another key yet.
		return True
	_gestures += 1
	if not _enabled:
		return True
	try:
		if not opensElementsList(gesture):
			return True
		import api
		import inputCore

		if inputCore.manager.isInputHelpActive:
			return True
		focus = api.getFocusObject()
		if focus is None or getattr(focus, "sleepMode", False):
			return True
		if gesture.script is not None:
			return True
		import queueHandler

		queueHandler.queueFunction(queueHandler.eventQueue, withoutDocument, _gestures)
	except Exception:
		_failure("could not tell whether NVDA would give the Elements List's key to the program")
		return True
	_log().debug(
		f"jawsMigrator: {getattr(gesture, 'identifiers', ['a key'])[0]} opens the Elements List, and NVDA has no browse mode "
		"document ready, so the key doesn't go to the program"
	)
	return False


def _readyDocument(focus):
	"""The browse mode document ``focus`` is in, when it is ready for the Elements List, else None."""
	import browseMode

	document = getattr(focus, "treeInterceptor", None)
	if isinstance(document, browseMode.BrowseModeTreeInterceptor) and document.isReady:
		return document
	return None


def _loadingDocument(focus):
	"""The browse mode document ``focus`` is in, while it is still loading, else None."""
	import browseMode

	document = getattr(focus, "treeInterceptor", None)
	if isinstance(document, browseMode.BrowseModeTreeInterceptor) and not document.isReady and getattr(document, "isAlive", True):
		return document
	return None


def withoutDocument(pressedAt: int, deadline: float | None = None) -> None:
	"""A key of the Elements List where NVDA had no browse mode document ready: open the list once it is, or say why not.

	``pressedAt`` is the count of gestures at the key press: when another key comes, NVDA stops waiting and says nothing.
	"""
	try:
		import api

		if _gestures != pressedAt:
			return
		focus = api.getFocusObject()
		document = _readyDocument(focus)
		if document is not None:
			_log().debug("jawsMigrator: the browse mode document is ready, so NVDA opens its Elements List")
			document.script_elementsList(None)
			return
		now = time.monotonic()
		if deadline is None:
			deadline = now + WAIT_FOR_DOCUMENT / 1000
		if _loadingDocument(focus) is not None and now < deadline:
			import core

			core.callLater(LOOK_EVERY, withoutDocument, pressedAt, deadline)
			return
		import ui

		ui.message(NOT_IN_DOCUMENT)
	except Exception:
		_failure("could not open the Elements List once the document was ready")
