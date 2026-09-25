# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""A heading said level first when quick navigation moves to it, as the arrow keys and JAWS say it.

NVDA reads what quick navigation moves to the way it reads the focus: the text first, then what it
is (``speech._shouldSpeakContentFirst``, NVDA 2026.1 and 2026.2, for OutputReason.QUICKNAV as for
FOCUS). A tester pressed H on a football news site and heard "main landmark, Texans' Nico Collins
Likely To Miss Week 3, link, heading, level 2": that it was a heading came last. The arrow keys read
the same heading level first: "heading, level 2, link, Texans' Nico Collins Likely To Miss Week 3".
JAWS says a heading's level first too: its H runs SayCurrentHeading (Virtual.jss), and JAWS's own
version of that for Word says "Heading 2", then the text. NVDA does this without any add-on.

So while quick navigation reports a heading, NVDA reads it in the order it reads the caret's line:
the heading, and what is in it, such as a link, say what they are before their text. That is H and
Shift+H, 1 to 9, and Move to in the Elements List: ``browseMode.TextInfoQuickNavItem.report`` for
the item types "heading" and "heading1" to "heading9". NVDA says the same words as before, in that
order. The name and description quick navigation adds are still said, and "out of" messages still
aren't. Everything else quick navigation moves to (links, buttons, form fields) keeps NVDA's order,
and so does the focus. It works while the assistant runs, unless it is turned off in NVDA's
Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import functools
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "sayHeadingLevelFirst"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorHeadingOrder"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: Quick navigation's item types for headings: "heading", and "heading1" to "heading9" for one level.
HEADING = "heading"
#: How NVDA decides whether a field's text comes before what it is, and how quick navigation reports an item.
DECISION = "_shouldSpeakContentFirst"
REPORT = "report"
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: NVDA's OutputReason.QUICKNAV, once known.
_quickNav = None
#: For each thread: how many heading reports are going on (``headings``), and the fields they put type first (``reordered``).
_local = threading.local()


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
	"""Whether quick navigation says a heading's level first: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def isHeading(item) -> bool:
	"""Whether the quick navigation item ``item`` is a heading: "heading", or "heading1" to "heading9"."""
	itemType = getattr(item, "itemType", None)
	if not isinstance(itemType, str) or not itemType.startswith(HEADING):
		return False
	level = itemType[len(HEADING) :]
	return not level or level.isdigit()


def register() -> None:
	"""Have quick navigation read the headings it moves to level first, from now on."""
	global _enabled, _quickNav
	if _enabled:
		return
	_enabled = True
	try:
		import browseMode
		from controlTypes import OutputReason
		from speech import speech

		_quickNav = OutputReason.QUICKNAV
		with _lock:
			# Without NVDA's decision there is nothing to change, and NVDA's reports are left alone too.
			if _replace(speech, DECISION, _decisionGuarded):
				_replace(browseMode.TextInfoQuickNavItem, REPORT, _reportGuarded)
	except Exception:
		_failure("can't have quick navigation say a heading's level first")


def unregister() -> None:
	"""Give NVDA its own order back, where nothing has been put over the assistant's since."""
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
	"""Whether ``function`` is one of the assistant's versions, or wraps one (as another add-on's functools.wraps wrapper would)."""
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
		_failure(f"NVDA has no {name} the assistant knows, so quick navigation reads headings as NVDA does")
		return False
	installed = guarded(current)
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, current))
	_log().debug(f"jawsMigrator: quick navigation says a heading's level before its text ({getattr(owner, '__name__', owner)}.{name})")
	return True


def _decisionGuarded(original):
	"""NVDA's choice between a field's text first and what it is first: what it is first, in a heading quick navigation reports."""

	@functools.wraps(original)
	def _shouldSpeakContentFirst(*args, **kwargs):
		contentFirst = original(*args, **kwargs)
		if not contentFirst or not _enabled:
			return contentFirst
		try:
			if not getattr(_local, "headings", 0):
				return contentFirst
			reason = kwargs["reason"] if "reason" in kwargs else (args[0] if args else None)
			if _quickNav is None or reason != _quickNav:
				return contentFirst
			_local.reordered = getattr(_local, "reordered", 0) + 1
			return False
		except Exception:
			_failure("could not put a heading's level first")
			return contentFirst

	setattr(_shouldSpeakContentFirst, MARK, _TOKEN)
	setattr(_shouldSpeakContentFirst, ORIGINAL, original)
	return _shouldSpeakContentFirst


def _reportGuarded(original):
	"""NVDA's report of what quick navigation moved to, which reads a heading level first."""

	@functools.wraps(original)
	def report(item, *args, **kwargs):
		if not _enabled or not isHeading(item):
			return original(item, *args, **kwargs)
		depth = getattr(_local, "headings", 0)
		if not depth:
			_local.reordered = 0
		_local.headings = depth + 1
		try:
			return original(item, *args, **kwargs)
		finally:
			_local.headings = depth
			if not depth and getattr(_local, "reordered", 0):
				try:
					_log().debug(f"jawsMigrator: quick navigation moved to a heading ({item.itemType}), so NVDA says its level before its text")
				except Exception:
					pass

	setattr(report, MARK, _TOKEN)
	setattr(report, ORIGINAL, original)
	return report
