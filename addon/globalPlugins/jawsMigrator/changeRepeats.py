# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""A change said once, when a control is activated in browse mode.

Pressing Space on a radio button in browse mode, NVDA moves the focus to the button, notes what the
button is ("not checked"), and clicks it. When the focus arrives, NVDA says what the click changed:
"As low as $49.97/mo for 36 months 0% APR + taxes, checked" (browseMode's event_gainFocus, NVDA
2026.2). NVDA makes a new object for the focus, though, and each object keeps its own notes of what
NVDA last said about it (``_speakObjectPropertiesCache``). The change was said, and noted, for the
object NVDA clicked, while the button's own notices of the change (state changes, label changes) go
to the focus object, whose notes can still say "not checked". NVDA then says "checked" a second
time. A tester heard it on visible.com, whose payment options rewrite their label when checked.

So after browse mode says what an activation changed, the focus object's notes get the values NVDA
just said, as the control's first notice of the same change comes in; NVDA then finds nothing new
to say. Only a value NVDA said, only once for each property, and only within a few seconds of saying
it: any other change, and any later one, is said as usual. Braille follows every notice as before.
It is part of saying a control's type and state once, and turned off with it.
"""

from __future__ import annotations

import time

from . import labelRepeats

#: The notices whose change NVDA says for the focus, by the name of what they change in NVDA's notes.
PROPERTIES = ("name", "states")
#: A notice this long after browse mode said what an activation changed is said as usual, in seconds.
REPEATS_WITHIN = 3.0

_enabled = False
#: What browse mode just said about an activated control: [focus object, time, {property: value}], or None.
_said: list | None = None
_failed = False
_MISSING = object()


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
	"""Whether a change is said once: with saying a control's type and state once (see labelRepeats)."""
	return labelRepeats.wanted(stateData)


def register() -> None:
	global _enabled
	_enabled = True


def unregister() -> None:
	global _enabled, _said
	_enabled = False
	_said = None


def isRegistered() -> bool:
	return _enabled


def _notes(obj) -> dict:
	notes = getattr(obj, "_speakObjectPropertiesCache", None)
	return notes if isinstance(notes, dict) else {}


def beforeFocus(obj):
	"""As the focus arrives on ``obj``, before NVDA handles it: ``(object browse mode activated, its notes)``, or None.

	Browse mode activates a control through another object for it than the focus object, and waits for
	the focus to say what changed (see afterFocus).
	"""
	if not _enabled:
		return None
	try:
		activated = getattr(obj.treeInterceptor, "_objPendingFocusBeforeActivate", None)
		if activated is None or activated is obj or activated != obj:
			return None
		return activated, getattr(activated, "_speakObjectPropertiesCache", None)
	except Exception:
		_failure("could not check which control browse mode activated")
		return None


def afterFocus(obj, activation) -> None:
	"""After NVDA handled the focus arriving on ``obj``: keep what browse mode said about the control it activated."""
	global _said
	_said = None
	if activation is None or not _enabled:
		return
	try:
		activated, notesBefore = activation
		notes = getattr(activated, "_speakObjectPropertiesCache", None)
		# NVDA gives an object new notes whenever it speaks about it: the same notes mean browse mode said nothing.
		if not isinstance(notes, dict) or notes is notesBefore:
			return
		values = {name: notes[name] for name in PROPERTIES if name in notes}
		if values:
			_said = [obj, time.monotonic(), values]
	except Exception:
		_failure("could not keep what browse mode said about an activated control")


def beforeChange(obj, name: str) -> None:
	"""Before NVDA handles a notice that ``name`` ("name" or "states") of ``obj`` changed: leave out what it just said.

	The focus object's notes get the value NVDA said, when that is the control's value now, so NVDA
	doesn't say it again. When its notes already have that value, or the control has changed since,
	NVDA goes on as usual, and the value is no longer kept. When nothing changed yet, the value is kept
	for the next notice: the one that comes in first can find the control as it was a moment earlier.
	"""
	global _said
	said = _said
	if said is None or said[0] is not obj or name not in said[2]:
		return
	try:
		if time.monotonic() - said[1] > REPEATS_WITHIN:
			_said = None
			return
		value = said[2][name]
		notes = _notes(obj)
		noted = notes.get(name, _MISSING)
		if noted == value:
			del said[2][name]
			return
		current = getattr(obj, name)
		if current == noted:
			return
		del said[2][name]
		if current != value:
			return
		obj._speakObjectPropertiesCache = {**notes, name: current}
		try:
			_log().debug(f"jawsMigrator: NVDA already said this change when the control was activated, so it isn't said again: {name} {current!r}")
		except Exception:
			pass
	except Exception:
		_failure("could not check a change NVDA had already said")
