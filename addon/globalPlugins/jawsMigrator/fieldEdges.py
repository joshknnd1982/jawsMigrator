# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""The arrow keys stay in an edit field on a web page when they reach its start or end, as in JAWS's Auto Forms Mode.

A tester wrote a comment on GitHub. At the end of the text he pressed Control+Right Arrow, and NVDA said "out of edit,
button, Paste," and was in browse mode on the button after the comment box. Right Arrow and Down Arrow at the end did
the same. JAWS stays in the comment box. JAWS's Auto Forms Mode is on in the tester's JAWS settings, so the migration
turned on NVDA's "Automatic focus mode for caret movement" (virtualBuffers.autoPassThroughOnCaretMove), its nearest
equivalent. That option also does more: when a caret key can't move the caret any further in the focused field, the
field's caretMovementFailed event reaches browse mode
(``browseMode.BrowseModeDocumentTreeInterceptor.event_caretMovementFailed``), which leaves focus mode, puts browse
mode's cursor at that edge of the field and runs the key again there, so it moves on past the field. It does this for
every caret key but Home and End, in every field. JAWS leaves forms mode only when you "arrow past the control"
(JAWS 2026, UO.jsm, msgUO_vCursorAutoFormsModeHlp): Up Arrow or Down Arrow in a single-line field. In a multi-line
field, and with Left and Right Arrow and Control with an arrow key anywhere, the cursor stays in the field.

So the assistant's global plugin, which NVDA gives the event to before browse mode, keeps focus mode and the caret where
they are, unless the key is Up Arrow or Down Arrow alone in a field of one line. It acts only where NVDA would leave
focus mode: browse mode's document in focus mode, with automatic focus mode for caret movement on. Everything else that
option does stays as it is: moving into a field with the arrow keys still switches to focus mode. It works while the
assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "stayInFieldsAtTheirEdges"
#: The keys, pressed alone, that go on past a field of one line, as JAWS's Auto Forms Mode arrows past it.
LEAVING_KEYS = ("upArrow", "downArrow")
#: The keys browse mode never leaves focus mode for (NVDA's own event_caretMovementFailed).
NVDA_STAYS = ("home", "end")

_enabled = False
_failed = False
#: The field the caret was last kept in, so the log says so once for each.
_noted = None


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
	"""Whether the arrow keys stay in an edit field at its edges: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Keep the caret in an edit field at its edges, from now on."""
	global _enabled
	_enabled = True


def unregister() -> None:
	"""Have NVDA leave an edit field at its edges as it does."""
	global _enabled, _noted
	_enabled = False
	_noted = None


def isRegistered() -> bool:
	return _enabled


def _leavesField(obj, gesture) -> bool:
	"""Whether JAWS's Auto Forms Mode would go on past the field: Up Arrow or Down Arrow alone, in a field of one line."""
	from controlTypes import State

	if gesture.mainKeyName not in LEAVING_KEYS or getattr(gesture, "modifiers", None):
		return False
	return State.MULTILINE not in obj.states


def _nvdaWouldLeave(obj) -> bool:
	"""Whether browse mode leaves focus mode at the field's edge: its document is in focus mode, with the option on."""
	import config

	interceptor = obj.treeInterceptor
	if interceptor is None or not getattr(interceptor, "passThrough", False):
		return False
	return bool(config.conf["virtualBuffers"]["autoPassThroughOnCaretMove"])


def keepsFocusMode(obj, gesture=None) -> bool:
	"""Whether the caret stays in obj, in focus mode, where browse mode would leave the field. False for anything else.

	The global plugin doesn't pass the caretMovementFailed event on to browse mode when this is True.
	"""
	if not _enabled or gesture is None:
		return False
	try:
		if gesture.mainKeyName in NVDA_STAYS or _leavesField(obj, gesture) or not _nvdaWouldLeave(obj):
			return False
	except Exception:
		_failure("could not tell whether a key at the edge of a field should stay in it, so NVDA does as it does")
		return False
	_note(obj, gesture)
	return True


def _note(obj, gesture) -> None:
	global _noted
	if obj is _noted:
		return
	_noted = obj
	try:
		name = obj.name
	except Exception:
		name = None
	try:
		key = "+".join(list(gesture.modifierNames) + [gesture.mainKeyName])
	except Exception:
		key = getattr(gesture, "mainKeyName", None)
	_log().debug(
		f"jawsMigrator: {key} at the edge of the field {name!r} stays in it, in focus mode, as JAWS's Auto Forms Mode does; "
		"NVDA would have gone on in browse mode",
	)
