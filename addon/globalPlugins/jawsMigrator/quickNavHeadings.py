# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

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
in NVDA's order: the text first, then "heading, level 2" (on a web page, linkSpeech puts a link's "link"
after the heading, as JAWS does). That is H and Shift+H, 1 to 9, and Move to in
the Elements List: ``browseMode.TextInfoQuickNavItem.report`` for the item types "heading" and "heading1"
to "heading9". D still says the landmark it moves to, and the arrow keys and Tab still say the landmarks
and lists they enter. It works while the assistant runs, unless it is turned off in NVDA's Settings, JAWS
Migration Assistant.

Version 1.12 read a heading level first when quick navigation moved to it (headingOrder), from a report
that turned out to be about "main landmark". JAWS says the text first, so that is gone, and the text
comes first again.

E does the same for an edit field (issue 30). On a reddit post in Edge, NVDA said "banner landmark,
navigation landmark, search landmark, Remove r/Visible filter and expand search to all of Reddit, edit,
Search in r/Visible" for the search box, and "main landmark, edit, Join the conversation" for the reply
box. JAWS's E (MoveToNextEdit) says no landmark: on a copy of the page, JAWS 2026 said "Remove r/Visible
filter and expand search to all of Reddit, edit, blank, placeholder, Search in r/Visible", and on reddit
the tester's JAWS said "edit, blank, placeholder, Join the conversation" (issue 22). JAWS says "blank"
for an edit field with nothing in it, then "placeholder" and its placeholder (common.jsm cmsgBlank1 and
cmsgPlaceholder), as its scripts do for the focus (IA2Browser.jss HandleSayObjectForEdit). NVDA's browse
mode says an empty field's placeholder where its value goes, without either word
(``speech.getControlFieldSpeech``). So E and Shift+E, and Move to in the Elements List (the item type
"edit"), say an edit field without the containers around it, and an empty one with "blank", then
"placeholder" and its placeholder, after its type and states. A field with text in it is said as NVDA
says it.

Every other quick navigation key does the same on a web page (issue 35). The tester asked for tests on
several sites. JAWS 2026 and NVDA 2026.2 with the assistant 1.35 (and the settings a migration from JAWS
gives) were run on copies of Amazon's home page and search results, Wikipedia, BBC News and GitHub, with the
same keys. JAWS's quick keys say the element alone: B "Delivering to Williamstown 17098 Update location,
Button", C "Search in, Combo box, collapsed", G "Wikipedia The Free Encyclopedia, Link, Graphic", I "Link,
Donate", L "list of 3 items", R "Primary navigation region", T "table with 3 columns and 8 rows". NVDA's said
every landmark, region and list the move entered first: "banner region, Primary, navigation region,
Delivering to Williamstown 17098, Update location, button", "banner region, Primary, navigation region,
search region, Search in, combo box, collapsed", "banner region, Personal tools, navigation region, list of 3
items, Donate, link", "main region, Folders and files, table, with 8 rows and 3 columns". So on a web page
read through IAccessible2 (Edge, Chrome, Firefox), quick navigation to anything (B, C, X, G, L, I, K, U, V,
F, D, T, O and the rest, and Move to in the Elements List) leaves out the containers and table cells around
what it moves to. What it moves to is said as NVDA says it, with what is in it: L still says the list and
its first line, D the landmark and its first line, T the table and its first cell, and a link or heading
around a graphic is still said. The item is told apart from what is around it by the page's own identifier
for it (``VirtualBufferQuickNavItem.vbufFieldIdentifier``, the field's "controlIdentifier_docHandle" and
"controlIdentifier_ID"). Anything else, such as quick navigation in Word, is said as NVDA says it.
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
#: Quick navigation's item type for edit fields (E and Shift+E).
EDIT = "edit"
#: What JAWS says for an edit field with nothing in it, and before its placeholder (common.jsm cmsgBlank1, cmsgPlaceholder).
BLANK = "blank"
PLACEHOLDER = "placeholder"
#: The field types of the field quick navigation reports, as NVDA says it where the report starts.
REPORTED = ("start_addedToControlFieldStack", "start_relative")
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
#: NVDA's OutputReason.QUICKNAV, Role.HEADING and Role.EDITABLETEXT, once known.
_quickNav = None
_headingRole = None
_editRole = None
#: For each thread: the reports going on, innermost last (``reports``: [the role of what is reported (None for another
#: element), whether it is an empty edit field, and another element's identifier (None for a heading or edit field)]),
#: and what they left out (``leftOut``).
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
	"""Whether quick navigation says what it moves to without what it is in: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def isHeading(item) -> bool:
	"""Whether the quick navigation item ``item`` is a heading: "heading", or "heading1" to "heading9"."""
	itemType = getattr(item, "itemType", None)
	if not isinstance(itemType, str) or not itemType.startswith(HEADING):
		return False
	level = itemType[len(HEADING) :]
	return not level or level.isdigit()


def isEditField(item) -> bool:
	"""Whether the quick navigation item ``item`` is an edit field: "edit", what E moves to."""
	return getattr(item, "itemType", None) == EDIT


def itemField(item):
	"""The page's identifier for the element quick navigation moved to, ``(docHandle, ID)``, or None where NVDA has none
	(a quick navigation item outside a virtual buffer, such as in Word)."""
	identifier = getattr(item, "vbufFieldIdentifier", None)
	if not isinstance(identifier, tuple) or len(identifier) != 2:
		return None
	try:
		return (int(identifier[0]), int(identifier[1]))
	except (TypeError, ValueError):
		return None


def fieldIdentifier(attrs):
	"""A field's identifier on its page, ``(docHandle, ID)``, as ``itemField`` gives it, or None."""
	if not hasattr(attrs, "get"):
		return None
	docHandle, fieldID = attrs.get("controlIdentifier_docHandle"), attrs.get("controlIdentifier_ID")
	if docHandle is None or fieldID is None:
		return None
	try:
		return (int(docHandle), int(fieldID))
	except (TypeError, ValueError):
		return None


def _isEmpty(item) -> bool:
	"""Whether the edit field quick navigation reports has nothing in it: its text, as browse mode has it, is blank."""
	try:
		text = item.textInfo.text
	except Exception:
		return False
	return isinstance(text, str) and not text.strip()


def register() -> None:
	"""Have quick navigation say the headings and edit fields it moves to without what they are in, from now on."""
	global _enabled, _quickNav, _headingRole, _editRole
	if _enabled:
		return
	_enabled = True
	try:
		import browseMode
		import speech
		from controlTypes import OutputReason, Role

		_quickNav = OutputReason.QUICKNAV
		_headingRole = Role.HEADING
		_editRole = Role.EDITABLETEXT
		with _lock:
			# Without NVDA's field speech there is nothing to leave out, and NVDA's reports are left alone too.
			if _replace(speech, FIELD_SPEECH, _fieldSpeechGuarded):
				_replace(browseMode.TextInfoQuickNavItem, REPORT, _reportGuarded)
	except Exception:
		_failure("can't have quick navigation say what it moves to without what it is in")


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
		_failure(f"NVDA has no {name} the assistant knows, so quick navigation says headings and edit fields as NVDA does")
		return False
	installed = guarded(current)
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, current))
	_log().debug(f"jawsMigrator: quick navigation says what it moves to without the landmark, region or list it is in ({getattr(owner, '__name__', owner)}.{name})")
	return True


def _hasRole(field, role) -> bool:
	return hasattr(field, "get") and field.get("role") == role


def _argument(args: tuple, kwargs: dict, name: str, index: int, default=None):
	"""An argument of getControlFieldSpeech after attrs, ancestorAttrs and fieldType: formatConfig, extraDetail or reason."""
	if name in kwargs:
		return kwargs[name]
	return args[index] if len(args) > index else default


def _isAround(attrs, ancestorAttrs, args: tuple, kwargs: dict, role, field=None) -> bool:
	"""Whether the field ``attrs`` is a container or table cell around what quick navigation reports: the heading or edit
	field (``role``), or the element whose identifier is ``field``."""
	if _argument(args, kwargs, "reason", 2) != _quickNav or not hasattr(attrs, "getPresentationCategory"):
		return False
	# What quick navigation moved to, and whatever is in it, are said. So is a link or button around it, which isn't a
	# container.
	if field is not None:
		if fieldIdentifier(attrs) == field or any(fieldIdentifier(ancestor) == field for ancestor in ancestorAttrs or ()):
			return False
	elif _hasRole(attrs, role) or any(_hasRole(ancestor, role) for ancestor in ancestorAttrs or ()):
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


def _afterTypeAndStates(sequence: list, attrs, reason) -> int:
	"""Where NVDA's speech for the edit field ``attrs`` has said its type and its states (speech.getControlFieldSpeech
	says its name, type, states, then its value or placeholder, description and the rest)."""
	# NVDA's getControlFieldSpeech finds getPropertiesSpeech in its own module, where formFields leaves out "multi line".
	from speech import speech

	role = attrs.get("role")
	roleText = attrs.get("roleText")
	typeWords = [roleText] if roleText else list(speech.getPropertiesSpeech(reason=reason, role=role))
	stateWords = list(speech.getPropertiesSpeech(reason=reason, states=attrs.get("states", set()), _role=role))
	size = len(typeWords)
	for start in range(len(sequence) - size + 1):
		if size and sequence[start : start + size] == typeWords:
			end = start + size
			if stateWords and sequence[end : end + len(stateWords)] == stateWords:
				end += len(stateWords)
			return end
	return len(sequence)


def withBlank(sequence, attrs, reason) -> list:
	"""NVDA's speech for an empty edit field quick navigation reports, as JAWS says it: "blank", then "placeholder" and
	its placeholder, after its type and states. NVDA said the placeholder where the field's value goes."""
	result = list(sequence)
	placeholder = attrs.get("placeholder")
	if placeholder:
		for index in range(len(result) - 1, -1, -1):
			if isinstance(result[index], str) and result[index] == placeholder:
				del result[index]
				break
	at = _afterTypeAndStates(result, attrs, reason)
	result[at:at] = [BLANK, PLACEHOLDER, placeholder] if placeholder else [BLANK]
	return result


def _fieldSpeechGuarded(original):
	"""NVDA's speech for a field: nothing for a container around a heading, an edit field or another element on a web page
	that quick navigation reports, and an empty edit field it reports as JAWS says it."""

	@functools.wraps(original)
	def getControlFieldSpeech(attrs, ancestorAttrs, fieldType, *args, **kwargs):
		sequence = original(attrs, ancestorAttrs, fieldType, *args, **kwargs)
		reports = getattr(_local, "reports", None)
		if not sequence or not _enabled or not reports:
			return sequence
		role, empty, field = reports[-1]
		if empty and fieldType in REPORTED and _hasRole(attrs, role) and _argument(args, kwargs, "reason", 2) == _quickNav:
			try:
				said = withBlank(sequence, attrs, _quickNav)
			except Exception:
				_failure('could not say "blank" and the placeholder of an empty edit field')
				return sequence
			try:
				_log().debug(f"jawsMigrator: quick navigation moved to an empty edit field, said as JAWS says it: {', '.join(item for item in said if isinstance(item, str) and item)}")
			except Exception:
				pass
			return said
		if fieldType not in AROUND:
			return sequence
		try:
			around = _isAround(attrs, ancestorAttrs, args, kwargs, role, field)
		except Exception:
			_failure("could not tell what a heading, edit field or other element is in")
			around = False
		if not around:
			return sequence
		_local.leftOut.append(_words(sequence))
		return []

	setattr(getControlFieldSpeech, MARK, _TOKEN)
	setattr(getControlFieldSpeech, ORIGINAL, original)
	return getControlFieldSpeech


def _reportGuarded(original):
	"""NVDA's report of what quick navigation moved to, which says it without what it is in."""

	@functools.wraps(original)
	def report(item, *args, **kwargs):
		if not _enabled:
			return original(item, *args, **kwargs)
		if isHeading(item):
			reported = (_headingRole, False, None)
		elif isEditField(item):
			reported = (_editRole, _isEmpty(item), None)
		else:
			# Anything else on a web page: the element itself, told apart from what is around it by its identifier.
			field = itemField(item)
			if field is None:
				return original(item, *args, **kwargs)
			reported = (None, False, field)
		reports = getattr(_local, "reports", None)
		if not reports:
			reports = _local.reports = []
			_local.leftOut = []
		reports.append(reported)
		try:
			return original(item, *args, **kwargs)
		finally:
			reports.pop()
			if not reports and _local.leftOut:
				if reported[0] == _headingRole:
					what = "a heading"
				elif reported[0] == _editRole:
					what = "an edit field"
				else:
					what = "an element"
				try:
					_log().debug(
						f"jawsMigrator: quick navigation moved to {what} ({item.itemType}), so NVDA doesn't say what it is in: {'; '.join(_local.leftOut)}",
					)
				except Exception:
					pass

	setattr(report, MARK, _TOKEN)
	setattr(report, ORIGINAL, original)
	return report
