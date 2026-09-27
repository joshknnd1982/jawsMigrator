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

JAWS has a list of its own for each kind of element, each with its own key: Insert+F7 lists the links alone (its Links
List), Insert+F6 the headings (Heading List), Insert+F5 the form fields (Select a Form Field), Control+Insert+B the
buttons (Select a Button) and Control+Insert+R the regions (Document Regions); Default.JKM, [virtual keys]. The migration
gives each of those keys to NVDA's Elements List, which lists links, headings, form fields, buttons or landmarks, with
radio buttons to choose which, and opens on the kind chosen last (on links at first). A tester asked, after pressing
NVDA+F7: "When using Jaws pressing insert f7 only brings up links. should we Make the Jaws migrator do the same?" So,
with a setting of its own, also on unless it is turned off:

- A JAWS key for one of those lists opens NVDA's Elements List on that kind alone, whatever kind the list was left on.
  The list has JAWS's title for it, so NVDA says "Links List dialog", and no radio buttons for other kinds: Tab goes
  from the list to the Filter box and the buttons. NVDA keeps the kind of the last list you moved or activated from, to
  open its own Elements List on next time; one of these lists leaves that as it was.
- A page with none of that kind gets JAWS's words, and no list: "no links", "No headings found", "no form fields were
  found", "no buttons were found", "No regions were found on the page" (common.jsm, ie.jsm).
- The keys are JAWS's own, as the migration brings them: NVDA+F7, NVDA+F6 and, when the migration was allowed to take
  NVDA's keys for them, NVDA+F5, NVDA+Control+B and NVDA+Control+R (the Kinesis layout's NVDA+/ opens the links too).
  Any other key given to the Elements List in NVDA's Input Gestures opens NVDA's own list with every kind. So does a key
  where the document's list has no such kind (Word's has no form fields), and a browse mode that isn't a document (Excel).
"""

from __future__ import annotations

import functools
import os
import threading
import weakref

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "linksLikeJaws"
#: The assistant's setting (state.json) for JAWS's list keys: each opens NVDA's Elements List on its own kind alone.
KEYS_KEY = "listKeysLikeJaws"
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
#: What makes the Elements List's dialog, which opens it on a kind of element.
MAKE_DIALOG = "__init__"
#: JAWS's keys for its lists of one kind (Default.JKM: [virtual keys], and JAWSKey+/ in [Kinesis keys]), the JAWS script
#: each runs, and NVDA's name for that kind in its Elements List.
JAWS_LIST_KEYS = (
	("JAWSKey+F7", "SelectALink", "link"),
	("JAWSKey+/", "SelectALink", "link"),
	("JAWSKey+F6", "SelectAHeading", "heading"),
	("JAWSKey+F5", "SelectAFormField", "formField"),
	("Control+JAWSKey+B", "SelectAButtonFormField", "button"),
	("Control+JAWSKey+R", "SelectaRegion", "landmark"),
)
#: The title of JAWS's list of each kind: its own dialogs in jfw.exe (Links List, Heading List, Document Regions), and
#: the form field lists' in Virtual.jss (msgSelectAFormFieldTitle in ie.jsm, cMsgSelectAButton in common.jsm).
TITLES = {
	"link": "Links List",
	"heading": "Heading List",
	"formField": "Select a Form Field",
	"button": "Select a Button",
	"landmark": "Document Regions",
}
#: What JAWS says for a list's key on a page with none of its kind: common.jsm's cMsgNoLinks, cmsgNoRegionsOnPage and
#: CMSGNoTagsFound_L ("no %1 were found", with CVMSGFormFields_L and cVMsgButton1_L), and ie.jsm's msgNoHeadings1_L.
NONE_FOUND = {
	"link": NO_LINKS,
	"heading": "No headings found",
	"formField": "no form fields were found",
	"button": "no buttons were found",
	"landmark": "No regions were found on the page",
}
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

#: Links are shown as JAWS's Links List shows them (STATE_KEY).
_enabled = False
#: JAWS's list keys open a list of their own kind (KEYS_KEY).
_keys = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: The class the assistant gives the Elements List's items, made the first time it is needed (see overlayClass).
_overlay = None
#: The kind of element each JAWS list key opens, by the key as NVDA normalizes it without its source ("f7+nvda").
_keyKinds: dict | None = None
#: The Elements List a JAWS list key asked for, until NVDA makes its dialog: (the document, as a weak reference, the kind).
_opening = None


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


def keysWanted(stateData: dict) -> bool:
	"""Whether each JAWS list key opens the Elements List on its own kind alone: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(KEYS_KEY, True))


def _parts(links: bool, keys: bool) -> list:
	"""What the assistant puts in the place of NVDA's own for links (``links``) and for JAWS's list keys (``keys``)."""
	parts = []
	if links:
		parts.append(("TextInfoQuickNavItem", LABEL, _labelGuarded))
	if links or keys:
		parts.append(("BrowseModeTreeInterceptor", ELEMENTS_LIST, _scriptGuarded))
	if links:
		parts.append(("TextInfoQuickNavItem", ACTIVATE, _activateGuarded))
	if keys:
		parts.append(("ElementsListDialog", MAKE_DIALOG, _dialogGuarded))
	return parts


def register(links: bool = True, keys: bool = False) -> None:
	"""From now on, show links in NVDA's Elements List as JAWS's Links List does (``links``), and open it on one kind
	alone for each JAWS list key (``keys``). What is no longer wanted is NVDA's own again."""
	global _enabled, _keys
	if not links and not keys:
		unregister()
		return
	parts = _parts(links, keys)
	wanted = {(owner, name) for owner, name, _guarded in parts}
	with _lock:
		for entry in list(_replaced):
			owner, name, installed, original = entry
			if (getattr(owner, "__name__", None), name) not in wanted:
				_restore(owner, name, installed, original)
				_replaced.remove(entry)
	_enabled, _keys = bool(links), bool(keys)
	for owner, name, guarded in parts:
		# Each on its own: one NVDA doesn't have leaves the others working.
		try:
			import browseMode

			with _lock:
				_replace(getattr(browseMode, owner), name, guarded)
		except Exception:
			_failure("can't show NVDA's Elements List as JAWS's lists")


def unregister() -> None:
	"""Give NVDA its own labels and Elements List back, where nothing has been put over the assistant's since. Levels
	come back at once."""
	global _enabled, _keys, _opening
	if not _enabled and not _keys:
		return
	_enabled = _keys = False
	_opening = None
	with _lock:
		for owner, name, installed, original in reversed(_replaced):
			_restore(owner, name, installed, original)
		_replaced.clear()


def _restore(owner, name: str, installed, original) -> None:
	try:
		if vars(owner).get(name) is installed:
			setattr(owner, name, original)
	except Exception:
		pass


def isRegistered() -> bool:
	return _enabled or _keys


def keysRegistered() -> bool:
	return _keys


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
	"""Browse mode's script that opens the Elements List: on the kind of a JAWS list key alone, and on a page with none of
	that kind (or without links, when the list opens on links), JAWS's words in its place."""

	@functools.wraps(original)
	def script_elementsList(self, gesture, *args, **kwargs):
		global _opening
		kind = keyKind(self, gesture) if _keys else None
		_opening = None
		kindSaid = kind or (LINK if _enabled and opensOn(self) == LINK else None)
		if kindSaid is not None and not hasAny(self, kindSaid):
			_log().debug(f"jawsMigrator: the page has no {kindSaid}, so NVDA says so, as JAWS does, instead of opening an empty Elements List")
			import ui

			ui.message(NONE_FOUND.get(kindSaid, NO_LINKS))
			return None
		if kind is not None:
			_opening = (_reference(self), kind)
			_log().debug(f"jawsMigrator: {_keyName(gesture)} is JAWS's key for its {TITLES.get(kind)}, so NVDA's Elements List opens on {kind} alone")
		return original(self, gesture, *args, **kwargs)

	setattr(script_elementsList, MARK, _TOKEN)
	setattr(script_elementsList, ORIGINAL, original)
	return script_elementsList


# -- JAWS's list keys ----------------------------------------------------------------------------------------------


def _normalized(identifier: str) -> tuple[str, str]:
	"""A gesture identifier as NVDA normalizes it (``inputCore.normalizeGestureIdentifier``): (its source, its keys)."""
	source, _sep, keys = str(identifier).lower().partition(":")
	return source, "+".join(sorted(keys.split("+")))


def keyKinds() -> dict:
	"""The kind of element each JAWS list key opens, by its keys as NVDA normalizes them ("f7+nvda"), as the migration
	converts JAWS's keys."""
	global _keyKinds
	if _keyKinds is None:
		from . import jawsKeyMap

		kinds = {}
		for jawsKey, _script, kind in JAWS_LIST_KEYS:
			gesture = jawsKeyMap.jawsKeyToNvdaGesture(jawsKey, "common")
			if gesture:
				kinds[_normalized(gesture)[1]] = kind
		_keyKinds = kinds
	return _keyKinds


def keyKind(document, gesture) -> str | None:
	"""The kind JAWS lists for the key ``gesture``, where ``document``'s Elements List has it alone; else None.

	None for any other key or gesture, and in a browse mode that isn't a document, such as Excel's.
	"""
	try:
		identifiers = list(getattr(gesture, "identifiers", None) or ())
		if not identifiers:
			return None
		import browseMode

		if not isinstance(document, browseMode.BrowseModeDocumentTreeInterceptor):
			return None
		kinds = keyKinds()
		for source, keys in map(_normalized, identifiers):
			if source.startswith("kb") and keys in kinds:
				kind = kinds[keys]
				break
		else:
			return None
		return kind if kind in (elementType[0] for elementType in document.ElementsListDialog.ELEMENT_TYPES) else None
	except Exception:
		_failure("could not tell which of JAWS's lists a key opens")
		return None


def _keyName(gesture) -> str:
	try:
		return gesture.displayName
	except Exception:
		identifiers = getattr(gesture, "identifiers", None) or ("the key",)
		return str(identifiers[0])


def _reference(document):
	"""A weak reference to ``document``, or something that gives it back like one."""
	try:
		return weakref.ref(document)
	except TypeError:
		return lambda: document


def _takeOpening(document) -> str | None:
	"""The kind a JAWS list key asked NVDA's next Elements List of ``document`` to open on alone, once; else None."""
	global _opening
	opening, _opening = _opening, None
	if opening is None:
		return None
	reference, kind = opening
	return kind if reference() is document else None


def _dialogGuarded(original):
	"""NVDA's making of its Elements List: for a JAWS list key, on its kind alone, as JAWS's list."""

	@functools.wraps(original)
	def __init__(self, document, *args, **kwargs):
		kind = _takeOpening(document) if _keys else None
		index = None
		if kind is not None:
			try:
				index = [elementType[0] for elementType in self.ELEMENT_TYPES].index(kind)
			except Exception:
				index = None
		if index is None:
			return original(self, document, *args, **kwargs)
		# NVDA's __init__ checks the radio button of this kind and fills the list with it.
		self.lastSelectedElementType = index
		try:
			original(self, document, *args, **kwargs)
		finally:
			# NVDA keeps the kind a list was on when you move or activate from it (onAction), to open its own list on it
			# next time: this one leaves that as it was.
			try:
				del self.lastSelectedElementType
			except AttributeError:
				pass
		showOnly(self, kind)

	setattr(__init__, MARK, _TOKEN)
	setattr(__init__, ORIGINAL, original)
	return __init__


def showOnly(dialog, kind: str) -> None:
	"""Make NVDA's Elements List ``dialog`` JAWS's list of ``kind``: its title, and no radio buttons for other kinds."""
	try:
		import wx

		for child in dialog.GetChildren():
			if isinstance(child, wx.RadioBox):
				# Disabled too, so that its access keys (Alt+K, Alt+H...) do nothing.
				child.Disable()
				child.Hide()
		title = TITLES.get(kind)
		if title:
			dialog.SetTitle(title)
		sizer = dialog.GetSizer()
		if sizer is not None:
			dialog.Layout()
			sizer.Fit(dialog)
			dialog.CentreOnScreen()
	except Exception:
		_failure("could not show NVDA's Elements List as JAWS's list of one kind")


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
