# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""An alert with nothing in it isn't said as "alert" alone: JAWS says nothing for it.

A tester who went straight to a repository's page on GitHub heard "alert", and nothing more, a moment after
"Skip to content". JAWS says nothing there. As the page finishes loading, GitHub adds an alert (an element with
role="alert") with nothing in it, and Edge tells screen readers about it with an alert event. NVDA says an alert in
two parts. Its live region handling (nvdaHelper's ia2LiveRegions) says the text the alert holds. Its alert event
(``NVDAObjects.IAccessible.IAccessible.event_alert``) says the alert itself: its name, the word "alert", its
description, and each control in it that can take the focus. NVDA 2026.2 leaves out an alert only when it has no
name, no description and no children at all. GitHub's alert has a child that is empty too, so NVDA said "alert"
alone. JAWS says an alert's text and nothing else (Default.JSS, MSAAAlertEvent), so it says nothing for an alert
with no text.

So NVDA leaves out an alert that has nothing in it, as it leaves out one without children: no name, description,
value or text in the alert or in anything in it, and nothing in it that can take the focus. An alert with anything
in it is said as NVDA says it. Only when all of the alert has been looked at is it left out: an alert with more in it
than the assistant looks through, or one that can't be read, is said as NVDA says it. It works while the assistant
runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "quietEmptyAlerts"
#: The most objects looked at in one alert; an alert with more in it is said as NVDA says it.
MOST_OBJECTS = 64
#: What NVDA's text of an object has in the place of an object in it (IAccessible2's embedded object character).
EMBEDDED_OBJECT = "￼"
#: The most characters of an object's own text read to see whether it has any.
MOST_CHARACTERS = 1000

_enabled = False
_failed = False


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
	"""Whether an alert with nothing in it is left out: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Leave out alerts with nothing in them, from now on."""
	global _enabled
	_enabled = True


def unregister() -> None:
	"""Have NVDA say every alert as it does."""
	global _enabled
	_enabled = False


def isRegistered() -> bool:
	return _enabled


def _hasText(value) -> bool:
	return isinstance(value, str) and bool(value.replace(EMBEDDED_OBJECT, "").strip())


def _ownText(obj) -> str:
	"""The text of obj itself, as IAccessible2 gives it (NVDA's IA2TextTextInfo reads it the same way), or ""."""
	textObject = getattr(obj, "IAccessibleTextObject", None)
	if textObject is None:
		return ""
	count = textObject.nCharacters
	if not count or count <= 0:
		return ""
	return textObject.text(0, min(count, MOST_CHARACTERS)) or ""


def _holdsSomething(obj, focusable) -> bool:
	"""Whether NVDA or a page has anything to say about obj itself: a name, a description, a value, text or the focus."""
	for name in ("name", "description", "value"):
		if _hasText(getattr(obj, name, None)):
			return True
	if focusable in (getattr(obj, "states", None) or ()):
		return True
	return _hasText(_ownText(obj))


def nothingToSay(obj) -> bool:
	"""Whether obj is an alert with nothing in it, which NVDA would say as "alert" alone. False for anything else."""
	if not _enabled:
		return False
	try:
		from controlTypes import Role, State

		if getattr(obj, "role", None) != Role.ALERT:
			return False
		focusable = State.FOCUSABLE
		waiting = [obj]
		looked = 0
		while waiting:
			current = waiting.pop()
			looked += 1
			if looked > MOST_OBJECTS or _holdsSomething(current, focusable):
				return False
			waiting.extend(current.children or ())
	except Exception:
		_failure("could not look into an alert, so NVDA says it as it does")
		return False
	try:
		_log().debug('jawsMigrator: an alert with nothing in it is left out; NVDA would have said "alert" alone, and JAWS says nothing')
	except Exception:
		pass
	return True
