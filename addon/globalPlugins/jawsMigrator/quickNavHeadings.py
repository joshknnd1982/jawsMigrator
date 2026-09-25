# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Quick navigation to a heading says the heading, not the landmark, region or list it is in, as JAWS does.

NVDA says each container a move takes it into, whatever made the move (``speech.getTextInfoSpeech``
speaks every field "start_addedToControlFieldStack"). A landmark or a region is never read text first
(``speech._shouldSpeakContentFirst``), so when H moves into one, it comes before the heading. A tester
pressed H on applevis.com and heard "main landmark, Welcome to AppleVis, heading, level 1", and on
reddit.com "Community actions, region, r/Visible, heading, level 1": "It identifies headings as main
landmark. JAWS doesn't do this." JAWS's H (Virtual.jss, ProcessMoveToHeading) runs SayCurrentHeading,
which says the heading alone, its text first: on reddit.com the tester's JAWS said "Feels to good to be
true, visited, heading level 2".

So while quick navigation reports a heading, NVDA leaves out the containers the move enters around the
heading: landmarks, regions, lists, tables and their cells, articles, groupings and frames (the fields
outside the heading whose presentation category is a container or a table cell). The heading itself, a
link in it or around it, and the name and description quick navigation adds are said as NVDA says them,
in NVDA's order: the text first, then "heading, level 2". That is H and Shift+H, 1 to 9, and Move to in
the Elements List: ``browseMode.TextInfoQuickNavItem.report`` for the item types "heading" and "heading1"
to "heading9". D still says the landmark it moves to, and the arrow keys and Tab still say the landmarks
and lists they enter. It works while the assistant runs, unless it is turned off in NVDA's Settings, JAWS
Migration Assistant.

Version 1.12 read a heading level first when quick navigation moved to it (headingOrder), from a report
that turned out to be about "main landmark". JAWS says the text first, so that is gone, and the text
comes first again.
"""

from __future__ import annotations

import functools
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "sayHeadingAlone"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorQuickNavHeadings"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: Quick navigation's item types for headings: "heading", and "heading1" to "heading9" for one level.
HEADING = "heading"
#: How NVDA says a field (in the speech package, where textInfos.TextInfo looks it up), and how quick navigation reports an item.
FIELD_SPEECH = "getControlFieldSpeech"
REPORT = "report"
#: The field types of a field NVDA has just moved into, and of one it names after the text: an article is read text first.
AROUND = ("start_addedToControlFieldStack", "end_inControlFieldStack")
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: NVDA's OutputReason.QUICKNAV and Role.HEADING, once known.
_quickNav = None
_headingRole = None
#: For each thread: how many heading reports are going on (``headings``), and what they left out (``leftOut``).
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
	"""Whether quick navigation says a heading without what it is in: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def isHeading(item) -> bool:
	"""Whether the quick navigation item ``item`` is a heading: "heading", or "heading1" to "heading9"."""
	itemType = getattr(item, "itemType", None)
	if not isinstance(itemType, str) or not itemType.startswith(HEADING):
		return False
	level = itemType[len(HEADING) :]
	return not level or level.isdigit()


def register() -> None:
	"""Have quick navigation say the headings it moves to without what they are in, from now on."""
	global _enabled, _quickNav, _headingRole
	if _enabled:
		return
	_enabled = True
	try:
		import browseMode
		import speech
		from controlTypes import OutputReason, Role

		_quickNav = OutputReason.QUICKNAV
		_headingRole = Role.HEADING
		with _lock:
			# Without NVDA's field speech there is nothing to leave out, and NVDA's reports are left alone too.
			if _replace(speech, FIELD_SPEECH, _fieldSpeechGuarded):
				_replace(browseMode.TextInfoQuickNavItem, REPORT, _reportGuarded)
	except Exception:
		_failure("can't have quick navigation say a heading without what it is in")


def unregister() -> None:
	"""Give NVDA its own functions back, where nothing has been put over the assistant's since."""
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
		_failure(f"NVDA has no {name} the assistant knows, so quick navigation says headings as NVDA does")
		return False
	installed = guarded(current)
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, current))
	_log().debug(f"jawsMigrator: quick navigation says a heading without the landmark, region or list it is in ({getattr(owner, '__name__', owner)}.{name})")
	return True


def _isHeadingField(field) -> bool:
	return hasattr(field, "get") and field.get("role") == _headingRole


def _argument(args: tuple, kwargs: dict, name: str, index: int, default=None):
	"""An argument of getControlFieldSpeech after attrs, ancestorAttrs and fieldType: formatConfig, extraDetail or reason."""
	if name in kwargs:
		return kwargs[name]
	return args[index] if len(args) > index else default


def _isAround(attrs, ancestorAttrs, args: tuple, kwargs: dict) -> bool:
	"""Whether the field ``attrs`` is a container or table cell around the heading quick navigation reports."""
	if _argument(args, kwargs, "reason", 2) != _quickNav or not hasattr(attrs, "getPresentationCategory"):
		return False
	# The heading, and whatever is in it, are said. So is a link or button around it, which isn't a container.
	if _isHeadingField(attrs) or any(_isHeadingField(ancestor) for ancestor in ancestorAttrs or ()):
		return False
	formatConfig = _argument(args, kwargs, "formatConfig", 0)
	if not formatConfig:
		import config

		formatConfig = config.conf["documentFormatting"]
	extraDetail = _argument(args, kwargs, "extraDetail", 1, False)
	category = attrs.getPresentationCategory(ancestorAttrs, formatConfig, reason=_quickNav, extraDetail=extraDetail)
	return category in (getattr(attrs, "PRESCAT_CONTAINER", "container"), getattr(attrs, "PRESCAT_CELL", "cell"))


def _words(sequence) -> str:
	"""What NVDA would have said, for the log: "main landmark", "list with 2 items", "Community actions region"."""
	return " ".join(item for item in sequence if isinstance(item, str) and item.strip())


def _fieldSpeechGuarded(original):
	"""NVDA's speech for a field: nothing for a container around a heading quick navigation reports."""

	@functools.wraps(original)
	def getControlFieldSpeech(attrs, ancestorAttrs, fieldType, *args, **kwargs):
		sequence = original(attrs, ancestorAttrs, fieldType, *args, **kwargs)
		if not sequence or not _enabled or fieldType not in AROUND or not getattr(_local, "headings", 0):
			return sequence
		try:
			around = _isAround(attrs, ancestorAttrs, args, kwargs)
		except Exception:
			_failure("could not tell what a heading is in")
			around = False
		if not around:
			return sequence
		_local.leftOut.append(_words(sequence))
		return []

	setattr(getControlFieldSpeech, MARK, _TOKEN)
	setattr(getControlFieldSpeech, ORIGINAL, original)
	return getControlFieldSpeech


def _reportGuarded(original):
	"""NVDA's report of what quick navigation moved to, which says a heading without what it is in."""

	@functools.wraps(original)
	def report(item, *args, **kwargs):
		if not _enabled or not isHeading(item):
			return original(item, *args, **kwargs)
		depth = getattr(_local, "headings", 0)
		if not depth:
			_local.leftOut = []
		_local.headings = depth + 1
		try:
			return original(item, *args, **kwargs)
		finally:
			_local.headings = depth
			if not depth and _local.leftOut:
				try:
					_log().debug(
						f"jawsMigrator: quick navigation moved to a heading ({item.itemType}), so NVDA doesn't say what it is in: {'; '.join(_local.leftOut)}",
					)
				except Exception:
					pass

	setattr(report, MARK, _TOKEN)
	setattr(report, ORIGINAL, original)
	return report
