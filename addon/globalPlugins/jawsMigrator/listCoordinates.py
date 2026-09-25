# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""An item in a list is said without row and column numbers, as JAWS says it.

Windows 11 lays out File Explorer's drives and files, Alt+Tab's windows and Outlook's messages in grids,
and gives each item its row and column (UIA's GridItem pattern). NVDA reads them for whatever has the
focus (NVDAObjects.UIA: rowNumber, columnNumber) and says them when "Cell coordinates" is on in its
Document Formatting settings (``speech.getPropertiesSpeech``), list items included, although it names no
table. A tester heard "Data (D:), row 2, column 1, 3 of 3" in This PC, where JAWS says "Data (D:)"; Alt+Tab
said "row 1, column 2", and Outlook "row 2610, column 1, through 13" after each message. JAWS's scripts say
a row and column only for table cells and headers (Default.JSS), never for list items (ExplorerFrame.jss).

So for a list item NVDA leaves out its row and column numbers, as it does everywhere when "Cell coordinates"
is off: ``speech._objectSpeech_calculateAllowedProps`` allows neither ``includeTableCellCoords`` nor
``cellCoordsText`` for Role.LISTITEM, for every reason but NVDA+Tab (OutputReason.QUERY), which still says
them. NVDA still notes the table as it does (so a table cell after the list is read as usual), and "3 of 3"
still follows NVDA's "Report object position information". Table cells, in Excel, Word and on web pages,
keep their coordinates. It works while the assistant runs, unless it is turned off in NVDA's Settings, JAWS
Migration Assistant.

The same wrapper applies listPosition's rule ("3 of 3" in File Explorer and Alt+Tab only where JAWS says it)
while that is on, so the two settings never stack two wrappers that could only be taken off in one order.
"""

from __future__ import annotations

import functools
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "listItemsWithoutCoordinates"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own version, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorListCoordinates"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: What NVDA may say about an object it reads, in speech.speech (where getObjectSpeech looks it up).
ALLOWED = "_objectSpeech_calculateAllowedProps"
#: The properties that make NVDA say a row and column: the numbers, and a cell's own text for them ("A1").
COORDINATES = ("includeTableCellCoords", "cellCoordsText")
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: NVDA's Role.LISTITEM and OutputReason.QUERY, once known.
_listItem = None
_query = None
#: Whether the log has said once that a list item's row and column were left out.
_logged = False
#: listPosition's rule while it is on: called with what NVDA may say about the list item and why NVDA reads it.
_positionRule = None


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
	"""Whether a list item is said without row and column numbers: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have NVDA say list items without row and column numbers, from now on."""
	global _enabled
	if _enabled:
		return
	_enabled = True
	_install("NVDA says a list item without its row and column numbers", "can't have NVDA say list items without row and column numbers")


def unregister() -> None:
	"""Stop leaving out a list item's row and column; NVDA gets its own function back unless listPosition's rule is on."""
	global _enabled
	if not _enabled:
		return
	_enabled = False
	_uninstallIfUnused()


def setPositionRule(rule) -> bool:
	"""Apply listPosition's ``rule(allowed, reason)`` to each list item NVDA reads, or stop (None). True when it applies."""
	global _positionRule
	_positionRule = rule
	if rule is None:
		_uninstallIfUnused()
		return True
	return _install(
		"NVDA says a position in File Explorer and Alt+Tab where JAWS says it",
		"can't have NVDA say a position in File Explorer and Alt+Tab where JAWS says it",
	)


def _install(said: str, failed: str) -> bool:
	global _listItem, _query
	try:
		from controlTypes import OutputReason, Role
		from speech import speech

		_listItem = Role.LISTITEM
		_query = OutputReason.QUERY
		with _lock:
			return _replace(speech, ALLOWED, _allowedGuarded, said)
	except Exception:
		_failure(failed)
		return False


def _uninstallIfUnused() -> None:
	"""Give NVDA its own function back, once neither rule is on, where nothing has been put over the assistant's since."""
	if _enabled or _positionRule is not None:
		return
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


def _replace(owner, name: str, guarded, said: str) -> bool:
	"""Put the assistant's version of ``name`` in the place of NVDA's own on ``owner``, once. True when it is there."""
	current = vars(owner).get(name)
	if _isOurs(current):
		# Still there from before: turned off and on again, or another add-on has put its own around it since.
		return True
	if not callable(current):
		_failure(f"NVDA has no {name} the assistant knows, so NVDA says a list item's row and column as it does")
		return False
	installed = guarded(current)
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, current))
	_log().debug(f"jawsMigrator: {said} ({getattr(owner, '__name__', owner)}.{name})")
	return True


def _allowedGuarded(original):
	"""What NVDA may say about an object: no row and column numbers for a list item, except for NVDA+Tab,
	and listPosition's rule for its position while that is on."""

	@functools.wraps(original)
	def _objectSpeech_calculateAllowedProps(reason, shouldReportTextContent, objRole, *args, **kwargs):
		global _logged
		allowed = original(reason, shouldReportTextContent, objRole, *args, **kwargs)
		if objRole != _listItem:
			return allowed
		if _enabled and reason != _query:
			try:
				if any(allowed.get(name) for name in COORDINATES):
					for name in COORDINATES:
						allowed[name] = False
					if not _logged:
						_logged = True
						_log().debug("jawsMigrator: a list item's row and column numbers are left out, as JAWS leaves them out (NVDA+Tab still says them)")
			except Exception:
				_failure("could not leave out a list item's row and column numbers")
		rule = _positionRule
		if rule is not None:
			try:
				rule(allowed, reason)
			except Exception:
				_failure("could not leave out a list item's position")
		return allowed

	setattr(_objectSpeech_calculateAllowedProps, MARK, _TOKEN)
	setattr(_objectSpeech_calculateAllowedProps, ORIGINAL, original)
	return _objectSpeech_calculateAllowedProps
