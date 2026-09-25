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
- When the page changed while NVDA filled the list, NVDA fills it again, so that the list shows the page
  as it is now; and when filling it fails all the same (an element the page took away, say), NVDA fills
  it again too: three times in all. If the page still won't hold still, the list is left empty and NVDA
  says that the page changed: the dialog still opens, and Escape closes it.

It needs no setting: while the page doesn't change, NVDA fills its list as it always does, with one
look at each heading's place added.
"""

from __future__ import annotations

import functools
import threading

#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorElementsList"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: How many times NVDA fills its Elements List before leaving it empty.
ATTEMPTS = 3
#: What NVDA says when the list is left empty, and how long after (in ms), so it comes after the dialog.
PAGE_CHANGED = "The page changed while NVDA listed its elements. Press Escape, then NVDA+F7 again."
SAY_AFTER = 800
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
#: How many elements have been found at another place than NVDA found them, since NVDA started.
_moved = 0
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []


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
	except Exception:
		_failure("can't keep NVDA's Elements List from being left half made")


def unregister() -> None:
	"""Give NVDA its own Elements List back, where nothing has been put over the assistant's since."""
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
	only its place in the virtual buffer moves. True when it was found at another place than before.
	"""
	global _moved
	try:
		from textInfos.offsets import Offsets

		docHandle, identifier = item.vbufFieldIdentifier
		start, end = item.textInfo._getOffsetsFromFieldIdentifier(docHandle, identifier)
		if (start, end) == (getattr(item.textInfo, "_startOffset", None), getattr(item.textInfo, "_endOffset", None)):
			return False
		item.textInfo = item.document.makeTextInfo(Offsets(start, end))
	except Exception:
		# Not in the page any more, or the page itself is gone.
		return False
	_moved += 1
	return True


def _labelGuarded(original):
	"""NVDA's label for an element in its Elements List, read where the element is now when the page moved it."""
	getter = original.fget

	@functools.wraps(getter)
	def label(self):
		if not _enabled:
			return getter(self)
		if getattr(self, "itemType", None) == "heading":
			# NVDA reads a heading's text where it found the heading, without looking whether the heading is still there.
			try:
				self.textInfo._getControlFieldAttribs(*self.vbufFieldIdentifier)
			except LookupError:
				if not relocate(self):
					raise
		try:
			return getter(self)
		except LookupError:
			if not relocate(self):
				raise
		return getter(self)

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
