# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""An item's position in a list ("3 of 3") is said in File Explorer and Alt+Tab where JAWS says it.

With version 1.13 a tester still heard "Data (D:), 3 of 3" when Alt+Tab brought This PC back, where JAWS
says "Data (D:)", and Alt+Tab itself said "This PC - File Explorer, 2 of 11" at each press. NVDA says the
position of whatever gets the focus when "Report object position information" is on, which the migration
sets from JAWS's "Announce Position and Count" at the user's verbosity level. JAWS's scripts say it in
fewer places:

- Alt+Tab: JAWS says only the window's name (Default.JSS, ProcessTaskSwitchList: ``Say(GetObjectName(),
  OT_WINDOW_NAME)`` for the "SwitchItemListControl" list). NVDA's own File Explorer support marks these
  items as MultitaskingViewFrameListItem.
- File Explorer's files, folders and drives (its DirectUIHWND items view, also in Open and Save As
  dialogs): JAWS adds the position when the active item changes as you move from item to item, if
  "Announce Position and Count" is on (ExplorerFrame.jss, ActiveItemChangedEvent). When the focus comes to
  the list from elsewhere, JAWS reads the item through FocusChangedEventProcessAncestors, and the tester
  heard no position.

So what NVDA may say about an object (``speech._objectSpeech_calculateAllowedProps``, which listCoordinates
wraps, applying this rule while it is on) has no ``positionInfo_indexInGroup`` and
``positionInfo_similarItemsInGroup`` for the focus (OutputReason.FOCUS, Role.LISTITEM) when it is an Alt+Tab
item, or an item of File Explorer's items view whose list is one of the ancestors NVDA has just said as the
focus entered them (``globalVars.focusAncestors`` from ``globalVars.focusDifferenceLevel`` on): switching
windows, opening a folder, Tab or Shift+Tab to the list. Moving through the list keeps NVDA's own choice, and
so does NVDA+Tab (OutputReason.QUERY). Other lists, menus and tree views are unchanged. It works while the
assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "positionLikeJawsInExplorer"
#: The properties that make NVDA say "3 of 3".
POSITION = ("positionInfo_indexInGroup", "positionInfo_similarItemsInGroup")
#: NVDA's class for an Alt+Tab item (appModules.explorer: its list's UIA automation ID is "SwitchItemListControl").
ALT_TAB_CLASS = "MultitaskingViewFrameListItem"
#: The window class of File Explorer's items view (JAWS's cwc_DirectUIHWND).
ITEMS_VIEW_WINDOW = "DirectUIHWND"

_enabled = False
_failed = False
#: NVDA's Role.LISTITEM, Role.LIST and OutputReason.FOCUS, once known.
_listItem = None
_list = None
_focus = None
#: What the log has said once: "altTab", "entered".
_logged: set = set()


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
	"""Whether File Explorer and Alt+Tab say a position only where JAWS does: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have NVDA say a position in File Explorer and Alt+Tab where JAWS says it, from now on."""
	global _enabled, _listItem, _list, _focus
	if _enabled:
		return
	_enabled = True
	try:
		from controlTypes import OutputReason, Role

		from . import listCoordinates

		_listItem, _list, _focus = Role.LISTITEM, Role.LIST, OutputReason.FOCUS
		listCoordinates.setPositionRule(leaveOutPosition)
	except Exception:
		_failure("can't have NVDA say a position in File Explorer and Alt+Tab where JAWS says it")


def unregister() -> None:
	"""Stop: NVDA says a position wherever it does."""
	global _enabled
	if not _enabled:
		return
	_enabled = False
	try:
		from . import listCoordinates

		if listCoordinates._positionRule is leaveOutPosition:
			listCoordinates.setPositionRule(None)
	except Exception:
		pass


def isRegistered() -> bool:
	return _enabled


def _isAltTabItem(obj) -> bool:
	"""Whether ``obj`` is an item of Alt+Tab's list of windows, as NVDA's own File Explorer support tells."""
	return any(cls.__name__ == ALT_TAB_CLASS for cls in type(obj).__mro__)


def _enteredItemsViewList(obj) -> str | None:
	"""The name of the list, when ``obj`` is in File Explorer's items view and the focus has just come to that list.

	NVDA keeps the ancestors of the focus in ``globalVars.focusAncestors``; those from
	``globalVars.focusDifferenceLevel`` on are the ones the focus has just entered, which NVDA says before the item.
	"""
	if getattr(obj, "windowClassName", None) != ITEMS_VIEW_WINDOW:
		return None
	import globalVars

	ancestors = globalVars.focusAncestors or []
	level = globalVars.focusDifferenceLevel
	if not isinstance(level, int):
		return None
	for index in range(len(ancestors) - 1, -1, -1):
		if ancestors[index].role == _list:
			return (ancestors[index].name or "list") if index >= level else None
	return None


def leaveOutPosition(allowed: dict, reason) -> None:
	"""listCoordinates calls this with what NVDA may say about a list item: no position for the focus in Alt+Tab,
	or when the focus has just come to a list in File Explorer."""
	if not _enabled or reason != _focus:
		return
	try:
		if not any(allowed.get(name) for name in POSITION):
			return
		import api

		obj = api.getFocusObject()
		if obj is None or obj.role != _listItem:
			return
		if _isAltTabItem(obj):
			why, once = "Alt+Tab says a window without its position, as JAWS says only the window's name (NVDA+Tab still says it)", "altTab"
		else:
			entered = _enteredItemsViewList(obj)
			if entered is None:
				return
			why = f"the focus came to File Explorer's list ({entered}), so the item is said without its position, as JAWS says it"
			why, once = why + " (moving through the list and NVDA+Tab still say it)", "entered"
		for name in POSITION:
			allowed[name] = False
		if once not in _logged:
			_logged.add(once)
			_log().debug(f"jawsMigrator: {why}")
	except Exception:
		_failure("could not leave out a position in File Explorer or Alt+Tab")
