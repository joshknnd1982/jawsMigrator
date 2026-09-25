# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""NVDA's Elements List shows links as JAWS's Links List does.

A tester compared the two on a github.com page. JAWS's Links List (Insert+F7) said "Skip to content, 1 of 34",
"Homepage ( g then d ), 2 of 34", "Current Page Code, 10 of 34" and "joshknnd1982 Alt+ArrowUp, 19 of 34". NVDA's
Elements List (NVDA+F7), on a page of the same site, said "Skip to content; same page, 1 of 50, level 0",
"Homepage ( g then d ); visited, 2 of 50, level 0" and "joshknnd1982; visited, 3 of 50, level 0". Three things differ:

- NVDA's label for a link (``browseMode.TextInfoQuickNavItem._getLabelForProperties``) is its text, then its states
  after a semicolon: "visited", and "same page" for a link to another place on the same page. JAWS's list leaves
  them out.
- JAWS says two things NVDA's label leaves out: "Current Page" before a link the page marks as the one for the page
  you are on (aria-current, as GitHub marks the repository tab you are on), and the link's shortcut key after its
  text (aria-keyshortcuts, as GitHub gives its user and commit links: "Alt+ArrowUp"). NVDA has both in its copy of
  the page, as the link's "current" and "keyboardShortcut", and says them when you move to the link in browse mode.
- NVDA's list is a tree (a wx.TreeCtrl), and NVDA says each item's level in it
  (``NVDAObjects.IAccessible.sysTreeView32.TreeViewItem``, from the tree's accValue). Links are all at the top of the
  tree, which Windows numbers 0, so NVDA says "level 0" with every one. JAWS's Links List is a plain list.

So, while the assistant runs:

- A link in the Elements List is its text, with "current page" (or current step, current location...) before it
  when the page marks it as current, and its shortcut key after it: "current page Code", "joshknnd1982
  Alt+ArrowUp". "visited" and "same page" are left out. The Filter box finds links by that label. Buttons, form
  fields, headings and landmarks keep NVDA's labels.
- Where no item of the list is under another, as with links, buttons and form fields, NVDA doesn't say "level 0"
  with each item, in speech or in braille. Where headings or landmarks are under others, NVDA says each one's level
  in the tree as before.

With 1.19 the tester pressed Alt+Left on a GitHub page and came to Edge's New Tab page, which has no links. NVDA+F7
opened an empty list, and NVDA said only "Elements List dialog, tree view"; the tester wrote down "It said element tree
view." JAWS's Insert+F7 says "no links" there and opens nothing (Virtual.jss, SelectALinkDialog and
ReportLinksNotAvailable; common.jsm, cmsgNoLinks). And on the page listing their repositories the tester chose
"reply-to-sender-outlook" in the list and pressed Enter, went back with Alt+Left, and NVDA+F7 opened on "Current page
Repositories (48), 10 of 128", the link NVDA's cursor had been on before, not the one chosen. NVDA's list starts on
the link at its browse mode cursor, as JAWS's Links List starts on the link at its virtual cursor. But NVDA activates a
link from the list without moving its cursor there (``browseMode.TextInfoQuickNavItem.activate``), so the cursor stayed
where it was, and so did the place Browse Mode Caret Fix keeps for Alt+Left, which is where the cursor was.

So, also:

- When the Elements List would open on links and the page has none, NVDA says "no links", as JAWS does, and doesn't
  open the list. A list you left on headings, form fields, buttons or landmarks opens as before, even when the page
  has none of them, so that you can choose another kind there.
- Activating a link or button from the Elements List moves browse mode's cursor to it first, as the list's Move to
  does, without saying it, then activates it: as moving to the link and pressing Enter does. Coming back to the page
  with Alt+Left brings you back to that link, and the list opens on it again. In focus mode NVDA activates it as
  before.

It works while the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import functools
import os
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "linksLikeJaws"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorLinksList"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: NVDA's label for an element of the Elements List, made from the element's properties.
LABEL = "_getLabelForProperties"
#: The states of a link JAWS's Links List leaves out, by NVDA's names: visited, and a link to the same page ("same page").
LEFT_OUT = ("VISITED", "INTERNAL_LINK")
#: The window class of a Windows tree view, such as the Elements List's.
TREE_CLASS = "SysTreeView32"
#: NVDA's name for the kind of element JAWS's Links List lists, in its Elements List.
LINK = "link"
#: What JAWS says for Insert+F7 on a page without links (Virtual.jss, ReportLinksNotAvailable; common.jsm, cmsgNoLinks).
NO_LINKS = "no links"
#: Browse mode's script that opens the Elements List, and what activates an element from it.
ELEMENTS_LIST = "script_elementsList"
ACTIVATE = "activate"
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: The class the assistant gives the Elements List's items, made the first time it is needed (see overlayClass).
_overlay = None


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
	"""Whether the Elements List shows links as JAWS's Links List does: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Show links in NVDA's Elements List as JAWS's Links List does, from now on."""
	global _enabled
	if _enabled:
		return
	_enabled = True
	for owner, name, guarded in (
		("TextInfoQuickNavItem", LABEL, _labelGuarded),
		("BrowseModeTreeInterceptor", ELEMENTS_LIST, _scriptGuarded),
		("TextInfoQuickNavItem", ACTIVATE, _activateGuarded),
	):
		# Each on its own: one NVDA doesn't have leaves the others working.
		try:
			import browseMode

			with _lock:
				_replace(getattr(browseMode, owner), name, guarded)
		except Exception:
			_failure("can't show links in NVDA's Elements List as JAWS's Links List does")


def unregister() -> None:
	"""Give NVDA its own labels back, where nothing has been put over the assistant's since. Levels come back at once."""
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


def _replace(owner, name: str, guarded) -> bool:
	"""Put the assistant's version of ``name`` in the place of NVDA's own on ``owner``, once. True when it is there."""
	current = vars(owner).get(name)
	if _isOurs(current):
		# Still there from before: turned off and on again, or another add-on has put its own around it since.
		return True
	if not callable(current):
		_failure(f"NVDA has no {name} the assistant knows, so the Elements List shows links as NVDA's own does")
		return False
	installed = guarded(current)
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, current))
	_log().debug(f"jawsMigrator: NVDA's Elements List shows links as JAWS's Links List does ({getattr(owner, '__name__', owner)}.{name})")
	return True


# -- a link's label ----------------------------------------------------------------------------------------------


def _leftOutStates() -> frozenset:
	"""NVDA's states for visited and same page, as far as this NVDA has them."""
	try:
		from controlTypes import State
	except Exception:
		return frozenset()
	return frozenset(state for state in (getattr(State, name, None) for name in LEFT_OUT) if state is not None)


def _currentText(current) -> str:
	"""What NVDA says for a link the page marks as current ("current page"), or "" when it isn't current."""
	if not current:
		return ""
	try:
		text = current.displayString
	except AttributeError:
		# Not NVDA's IsCurrent: the attribute as the page gave it.
		text = "" if str(current).lower() in ("false", "no") else "current"
	return text or ""


def jawsLabel(label: str, current, shortcut) -> str:
	"""A link's label as JAWS's Links List has it: what the page marks it as first, then its text, then its shortcut key."""
	text = _currentText(current)
	if text:
		# At the start of the item, as JAWS's "Current Page Code".
		text = text[:1].upper() + text[1:]
	parts = [text, label or "", str(shortcut).strip() if shortcut else ""]
	return " ".join(part for part in parts if part)


def _labelGuarded(original):
	"""NVDA's label for an element of its Elements List: for a link, JAWS's."""

	@functools.wraps(original)
	def _getLabelForProperties(self, labelPropertyGetter, *args, **kwargs):
		if not _enabled or getattr(self, "itemType", None) != "link":
			return original(self, labelPropertyGetter, *args, **kwargs)
		leftOut = _leftOutStates()

		def getProperty(name):
			# An element the page took away raises LookupError here, which the Elements List needs to see (see elementsList).
			value = labelPropertyGetter(name)
			if name == "states" and value and leftOut:
				value = {state for state in value if state not in leftOut}
			return value

		label = original(self, getProperty, *args, **kwargs)
		try:
			current = labelPropertyGetter("current")
			shortcut = labelPropertyGetter("keyboardShortcut")
		except LookupError:
			raise
		except Exception:
			# The page's copy could not say more: NVDA's label, without the states.
			return label
		return jawsLabel(label, current, shortcut)

	setattr(_getLabelForProperties, MARK, _TOKEN)
	setattr(_getLabelForProperties, ORIGINAL, original)
	return _getLabelForProperties


# -- a page without links ------------------------------------------------------------------------------------------


def opensOn(document) -> str | None:
	"""The kind of element NVDA's Elements List opens on in ``document`` ("link" at first, then the one last chosen in it)."""
	try:
		dialog = document.ElementsListDialog
		return dialog.ELEMENT_TYPES[dialog.lastSelectedElementType][0]
	except Exception:
		return None


def hasAny(document, itemType: str) -> bool:
	"""Whether ``document`` has an element of ``itemType``, as NVDA's Elements List finds them. True when NVDA can't tell."""
	try:
		for _item in document._iterNodesByType(itemType):
			return True
	except Exception:
		return True
	return False


def _scriptGuarded(original):
	"""Browse mode's script that opens the Elements List: on a page without links, JAWS's "no links" in its place."""

	@functools.wraps(original)
	def script_elementsList(self, gesture, *args, **kwargs):
		if _enabled and opensOn(self) == LINK and not hasAny(self, LINK):
			_log().debug("jawsMigrator: the page has no links, so NVDA says so, as JAWS does, instead of opening an empty Elements List")
			import ui

			ui.message(NO_LINKS)
			return None
		return original(self, gesture, *args, **kwargs)

	setattr(script_elementsList, MARK, _TOKEN)
	setattr(script_elementsList, ORIGINAL, original)
	return script_elementsList


# -- activating a link ---------------------------------------------------------------------------------------------


def moveCursorTo(item) -> bool:
	"""Put browse mode's cursor at the start of ``item``, as the Elements List's Move to does, without saying it.

	True when it moved. In focus mode it doesn't: NVDA activates the element as before.
	"""
	try:
		import browseMode
		from controlTypes import OutputReason

		document = item.document
		if not isinstance(document, browseMode.BrowseModeDocumentTreeInterceptor) or document.passThrough:
			return False
		info = item.textInfo.copy()
		info.collapse()
		document._set_selection(info, reason=OutputReason.QUICKNAV)
	except Exception:
		_failure("could not move browse mode's cursor to the element activated from the Elements List")
		return False
	return True


def _activateGuarded(original):
	"""NVDA's activation of an element from its Elements List, once browse mode's cursor is on it."""

	@functools.wraps(original)
	def activate(self, *args, **kwargs):
		if _enabled and moveCursorTo(self):
			_log().debug("jawsMigrator: browse mode's cursor moved to the element activated from the Elements List")
		return original(self, *args, **kwargs)

	setattr(activate, MARK, _TOKEN)
	setattr(activate, ORIGINAL, original)
	return activate


# -- "level 0" -----------------------------------------------------------------------------------------------------


def _elementsListTree(windowHandle):
	"""The tree of the open Elements List whose window is ``windowHandle``, or None."""
	import browseMode
	import wx

	for window in wx.GetTopLevelWindows():
		if not isinstance(window, browseMode.ElementsListDialog):
			continue
		tree = getattr(window, "tree", None)
		if tree is not None and tree.GetHandle() == windowHandle:
			return tree
	return None


def isFlat(tree) -> bool:
	"""Whether no item of ``tree`` (a wx.TreeCtrl with its root hidden) is under another, as it shows now."""
	root = tree.GetRootItem()
	if not root.IsOk():
		return True
	item, cookie = tree.GetFirstChild(root)
	while item.IsOk():
		if tree.ItemHasChildren(item):
			return False
		item, cookie = tree.GetNextChild(root, cookie)
	return True


def levelSaysNothing(windowHandle) -> bool:
	"""Whether the item's level in the tree ``windowHandle`` says nothing: an Elements List where no item is under another."""
	if not _enabled or threading.current_thread() is not threading.main_thread():
		# wx is for NVDA's main thread only.
		return False
	tree = _elementsListTree(windowHandle)
	return tree is not None and isFlat(tree)


def overlayClass():
	"""NVDA's tree view item, less its level where the Elements List has no item under another."""
	global _overlay
	if _overlay is None:
		from NVDAObjects.IAccessible.sysTreeView32 import TreeViewItem

		class ElementsListItem(TreeViewItem):
			"""An item of NVDA's Elements List: no "level 0" where every item is at the top of the list."""

			def _get_positionInfo(self):
				info = super()._get_positionInfo()
				try:
					if "level" in info and levelSaysNothing(self.windowHandle):
						info = {key: value for key, value in info.items() if key != "level"}
				except Exception:
					_failure("could not tell whether the Elements List has items under others")
				return info

		_overlay = ElementsListItem
	return _overlay


def chooseOverlay(obj, clsList) -> None:
	"""NVDA's chooseNVDAObjectOverlayClasses: an item of NVDA's own Elements List gets the assistant's class."""
	if not _enabled:
		return
	try:
		if getattr(obj, "windowClassName", None) != TREE_CLASS:
			return
		from NVDAObjects.IAccessible.sysTreeView32 import TreeViewItem

		if not any(isinstance(cls, type) and issubclass(cls, TreeViewItem) for cls in clsList):
			return
		if obj.processID != os.getpid() or threading.current_thread() is not threading.main_thread():
			return
		if _elementsListTree(obj.windowHandle) is None:
			return
		clsList.insert(0, overlayClass())
	except Exception:
		_failure("could not tell whether an item is in NVDA's Elements List")
