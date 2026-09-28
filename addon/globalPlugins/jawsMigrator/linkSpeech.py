# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Links on web pages are said as JAWS says them: "same page" only for a link to a place on the page, no link titles
but on Tab, "link" after the heading a link is in, and, in quick navigation, no description.

A tester pressed H on profootballrumors.com. JAWS said "HEADLINES, heading level 3, Link", "Pro Football Rumors,
heading level 1, Link" and "Vikings To Sign P Johnny Hekker, heading level 2, Link". NVDA said "HEADLINES, same page,
link, Homepage, heading, level 3", "Pro Football Rumors, same page, link, Home, heading, level 1" and "Vikings To Sign P
Johnny Hekker, link, heading, level 2". Each heading holds a link from start to end: ``<h3><a href="/"
title="Homepage">Headlines</a></h3>``, and on reddit.com JAWS said "Feels to good to be true, visited, heading level
2". Three things differ:

- "same page". NVDA calls a link same page when its address, without what follows "#", is the page's own
  (``utils.urlUtils.isSamePageURL``), so a link to the home page, on the home page, is "same page". JAWS's "Identify
  same page links" (IdentifySamePageLinks, on as JAWS comes) names a link to a place on the page, such as "Skip to
  content" (#content). NVDA asks ``browseMode.BrowseModeTreeInterceptor.getLinkTypeInDocument`` for every link it
  reads in a document and for a link that has the focus; it now says "same page" only when the link's address has a "#".
- "Homepage", "Home": the links' title attribute. Edge and Chrome give NVDA a link's title as its description
  ("description-from" tooltip), and NVDA says descriptions when it reads a field for the focus or for quick
  navigation (Object Presentation, "Report object descriptions"). JAWS says a link's text: its option for how text
  links are shown (LinkText) is 1, "Screen Text", as JAWS comes, not "Title". So when NVDA says a link it reads in a
  document (``textInfos.TextInfo.getControlFieldSpeech``), a description from its title isn't said. Firefox doesn't
  tell NVDA where a description comes from, so there a title is said as any other description. When the focus moves
  to a link (Tab), NVDA says its title again since 1.36: JAWS 2026 says it then, run live on a copy of Wikipedia
  (issue 35): "Create account Link | You are encouraged to create an account and log in; however, it is not
  mandatory".
- The order. NVDA says a heading and a link in it text first (``speech._shouldSpeakContentFirst``), and after the text
  it names the innermost field first: "link" comes before "heading, level 3". When quick navigation reports a heading
  on a web page (H, Shift+H, 1 to 9, Move to in the Elements List: ``virtualBuffers.VirtualBufferQuickNavItem.report``)
  that holds a link from its start to its end, or is in one, NVDA now says the text, the link's states ("visited",
  "same page"), the heading and its level, then "link" and whatever NVDA says after it. A link that ends before the
  heading does is said where NVDA says it. K and Tab say a link in a heading as NVDA does.
- The order, reading a line (the arrow keys, NVDA+Up Arrow, and the line read after Alt+Left). On reddit.com NVDA said
  "heading, level 2, visited, link, Downgrading is a nightmare" for a post's title, a heading holding a link, and
  "link, heading, level 2, Bi-weekly Megathread..." for a highlight, a link holding a heading (issue 38). JAWS 2026,
  run live on a copy of the page, said "visited heading level 2 Link Downgrading is a nightmare" and "heading level 2
  Link Bi-weekly Megathread..." on SayLine and on the arrow keys: the link's states, the heading, then "Link", however
  the two are nested. When a line NVDA reads as the caret moves (OutputReason.CARET) starts in a heading and a link
  right inside it, or a link and a heading right inside it, NVDA now says them in that order, before the text.
- A description, in quick navigation. The tester pressed H on reddit.com (issue 32), and NVDA said "What Phones Work
  Best On Visible?, visited, heading, level 2, link, Author: u/Pikachufourtytwo 2 hr. ago". JAWS said the same without
  "Author: ...", which is the link's description (reddit's aria-describedby). NVDA says a description for the focus and
  for quick navigation (Object Presentation, "Report object descriptions"). JAWS's virtual cursor says none: in its
  Default.jcf, [VirtualCursorVerbosity] has DescribedBy=1|0|0 and ElementDescription=0|0|0, off at the Medium
  verbosity JAWS comes with, and Alt+Insert+R (SayDescribedByText) reads a description when asked. So when quick
  navigation moves to a link or a heading on a web page (H, K, 1 to 9, Move to in the Elements List), its description
  isn't said, whatever it comes from. Tab says it, as JAWS says a link's description when the focus moves to it, and so
  does NVDA+Tab on a link with the focus.

None of these is what another part of the assistant changes (quickNavHeadings changes ``speech.getControlFieldSpeech``
and ``browseMode.TextInfoQuickNavItem.report``), so each gives NVDA its own back when it is turned off. It works while
the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant. Braille is unchanged.
"""

from __future__ import annotations

import copy
import functools
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "sayLinksAsJaws"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorLinkSpeech"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: How a document's text says a field (textInfos.TextInfo), how a web page's quick navigation item is reported
#: (virtualBuffers.VirtualBufferQuickNavItem, which has TextInfoQuickNavItem's), and how a browse mode document tells the
#: type of a link (browseMode.BrowseModeTreeInterceptor).
FIELD_SPEECH = "getControlFieldSpeech"
REPORT = "report"
LINK_TYPE = "getLinkTypeInDocument"
#: Quick navigation's item types for headings: "heading", and "heading1" to "heading9" for one level.
HEADING = "heading"
#: The field type NVDA uses, after a field's text, for a field the text was in from start to end.
AFTER_TEXT = "end_inControlFieldStack"
#: The field types NVDA uses, before a line's text, for a field the line starts in: one the line before was in too,
#: and one it comes into (speech.getTextInfoSpeech).
LINE_START = ("start_inControlFieldStack", "start_addedToControlFieldStack")
#: What marks an address as a place on its page.
PLACE = "#"
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16
#: The log names this many titles and addresses, each once.
_MOST_LOGGED = 50

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)]. NVDA's is None
#: where the class had none of its own and took it from the class it comes from.
_replaced: list = []
#: NVDA's OutputReason.QUICKNAV, FOCUS and CARET, Role.LINK, Role.HEADING, State.INTERNAL_LINK and
#: DescriptionFrom.TOOLTIP, once known.
_quickNav = None
_focus = None
_caret = None
_linkRole = None
_headingRole = None
_samePage = None
_fromTitle = None
#: For each thread: how many heading reports are going on (``headings``), the fields already said with the other of
#: their pair (``said``), the pairs said in the assistant's order, for the log (``pairs``), and, reading a line, the
#: field said already with the one it is right inside (``lineInner``: the text, that field, and its role).
_local = threading.local()
#: What the log has named already.
_loggedLines: set = set()
_loggedTitles: set = set()
_loggedAddresses: set = set()
_loggedDescriptions: set = set()


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
	"""Whether links are said as JAWS says them: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def isHeading(item) -> bool:
	"""Whether the quick navigation item ``item`` is a heading: "heading", or "heading1" to "heading9"."""
	itemType = getattr(item, "itemType", None)
	if not isinstance(itemType, str) or not itemType.startswith(HEADING):
		return False
	level = itemType[len(HEADING) :]
	return not level or level.isdigit()


def isPlaceOnPage(url) -> bool:
	"""Whether a link to ``url`` goes to a place on its page, which JAWS calls a same page link: its address has a "#"."""
	return isinstance(url, str) and PLACE in url


def register() -> None:
	"""Have NVDA say links as JAWS says them, from now on."""
	global _enabled, _quickNav, _focus, _caret, _linkRole, _headingRole, _samePage, _fromTitle
	if _enabled:
		return
	_enabled = True
	try:
		import browseMode
		import textInfos
		from controlTypes import DescriptionFrom, OutputReason, Role, State

		_quickNav, _focus, _caret = OutputReason.QUICKNAV, OutputReason.FOCUS, OutputReason.CARET
		_linkRole, _headingRole = Role.LINK, Role.HEADING
		_samePage = State.INTERNAL_LINK
		_fromTitle = DescriptionFrom.TOOLTIP
		with _lock:
			_replace(browseMode.BrowseModeTreeInterceptor, LINK_TYPE, _linkTypeGuarded)
			# The heading's report only matters where the assistant says the fields.
			if _replace(textInfos.TextInfo, FIELD_SPEECH, _fieldSpeechGuarded):
				import virtualBuffers

				_replace(virtualBuffers.VirtualBufferQuickNavItem, REPORT, _reportGuarded, inherited=True)
	except Exception:
		_failure("can't have NVDA say links as JAWS says them")


def unregister() -> None:
	"""Give NVDA its own functions back, where nothing has been put over the assistant's since."""
	global _enabled
	if not _enabled:
		return
	_enabled = False
	with _lock:
		for owner, name, installed, original in reversed(_replaced):
			try:
				if vars(owner).get(name) is not installed:
					continue
				if original is None:
					# The class had none of its own: it takes the one of the class it comes from again.
					delattr(owner, name)
				else:
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


def _replace(owner, name: str, guarded, inherited: bool = False) -> bool:
	"""Put the assistant's version of ``name`` in the place of NVDA's own on ``owner``, once. True when it is there.
	With ``inherited``, a class that takes ``name`` from the class it comes from gets the assistant's version of that."""
	current = vars(owner).get(name)
	if _isOurs(current):
		# Still there from before: turned off and on again, or another add-on has put its own around it since.
		return True
	if current is None and inherited and callable(getattr(owner, name, None)):
		installed = guarded(_fromBase(owner, name))
		original = None
	elif callable(current):
		installed = guarded(current)
		original = current
	else:
		_failure(f"NVDA has no {name} the assistant knows, so NVDA says links there as it does")
		return False
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, original))
	_log().debug(f"jawsMigrator: links are said as JAWS says them ({getattr(owner, '__name__', owner)}.{name})")
	return True


def _fromBase(owner, name: str):
	"""What ``owner`` takes from the class it comes from, looked up at each call, as Python does."""

	def inherited(self, *args, **kwargs):
		return getattr(super(owner, self), name)(*args, **kwargs)

	inherited.__name__ = name
	return inherited


def _noteOnce(logged: set, key: str, message: str) -> None:
	if key in logged or len(logged) >= _MOST_LOGGED:
		return
	logged.add(key)
	try:
		_log().debug(message)
	except Exception:
		pass


# -- "same page" ----------------------------------------------------------------------------------------------------


def _linkTypeGuarded(original):
	"""NVDA's link type in a browse mode document: no "same page" for a link without a "#" in its address."""

	@functools.wraps(original)
	def getLinkTypeInDocument(self, url, *args, **kwargs):
		linkType = original(self, url, *args, **kwargs)
		if not _enabled or linkType is None or linkType != _samePage or isPlaceOnPage(url):
			return linkType
		_noteOnce(
			_loggedAddresses,
			str(url),
			f"jawsMigrator: NVDA doesn't say same page for a link to {url}: it goes to the page itself, not to a place on it",
		)
		return None

	setattr(getLinkTypeInDocument, MARK, _TOKEN)
	setattr(getLinkTypeInDocument, ORIGINAL, original)
	return getLinkTypeInDocument


# -- a link's title --------------------------------------------------------------------------------------------------


def _hasTitle(attrs) -> bool:
	"""Whether the field ``attrs`` is a link whose description is its title attribute."""
	return (
		_fromTitle is not None
		and hasattr(attrs, "get")
		and attrs.get("role") == _linkRole
		and bool(attrs.get("description"))
		and attrs.get("_description-from") == _fromTitle
		and not attrs.get("descriptionIsContent", False)
	)


def withoutTitle(attrs):
	"""The field ``attrs``, without the description a link has from its title: a copy, as NVDA keeps its fields."""
	if not _hasTitle(attrs):
		return attrs
	field = copy.copy(attrs)
	title = field.pop("description", None)
	_noteOnce(_loggedTitles, str(title), f"jawsMigrator: NVDA doesn't say a link's title, as JAWS says its text: {title!r}")
	return field


# -- a description, in quick navigation ------------------------------------------------------------------------------


def _hasDescription(attrs) -> bool:
	"""Whether the field ``attrs`` is a link or a heading with a description NVDA would say (not its content)."""
	return (
		hasattr(attrs, "get")
		and attrs.get("role") in (_linkRole, _headingRole)
		and bool(attrs.get("description"))
		and not attrs.get("descriptionIsContent", False)
	)


def withoutDescription(attrs):
	"""The link or heading field ``attrs`` without its description, as JAWS's virtual cursor says it: a copy."""
	if not _hasDescription(attrs):
		return attrs
	field = copy.copy(attrs)
	description = field.pop("description", None)
	_noteOnce(
		_loggedDescriptions,
		str(description),
		f"jawsMigrator: quick navigation doesn't say a link's or heading's description, as JAWS's virtual cursor doesn't: {description!r}",
	)
	return field


def asJaws(attrs, reason):
	"""The field ``attrs`` as JAWS says it: for the focus (Tab), as NVDA says it, with a link's title and description;
	in quick navigation, a link or heading without its description, whatever it comes from; otherwise a link without its
	title."""
	if reason is not None and reason == _focus:
		return attrs
	if reason is not None and reason == _quickNav:
		return withoutDescription(attrs)
	return withoutTitle(attrs)


# -- the order after a heading ---------------------------------------------------------------------------------------


def _argument(args: tuple, kwargs: dict, name: str, index: int, default=None):
	"""An argument of getControlFieldSpeech after attrs, ancestorAttrs and fieldType: formatConfig, extraDetail or reason."""
	if name in kwargs:
		return kwargs[name]
	return args[index] if len(args) > index else default


def _role(field):
	return field.get("role") if hasattr(field, "get") else None


def _pairedWith(attrs, ancestorAttrs) -> int | None:
	"""Where the other of a heading and a link is among ``ancestorAttrs``: the heading a link is in, or the link a
	heading is in, the nearest. None when ``attrs`` is neither, or has no such field around it."""
	role = _role(attrs)
	if role == _linkRole:
		other = _headingRole
	elif role == _headingRole:
		other = _linkRole
	else:
		return None
	ancestors = list(ancestorAttrs or ())
	for index in reversed(range(len(ancestors))):
		if _role(ancestors[index]) == other:
			return index
	return None


def _stateWords(link, reason) -> list:
	"""What NVDA says for the states of the link field ``link``: "visited", "same page"."""
	import speech

	words = speech.getPropertiesSpeech(reason=reason, states=link.get("states", set()), _role=_linkRole)
	return [word for word in words if isinstance(word, str)]


def _splitAfterStates(sequence: list, words: list) -> tuple:
	"""A link's speech in two: up to its states, and the rest ("link", its description, ...)."""
	count = len(words)
	if count:
		for start in range(len(sequence) - count + 1):
			if sequence[start : start + count] == words:
				return sequence[: start + count], sequence[start + count :]
	return [], sequence


def _together(original, info, attrs, ancestorAttrs, fieldType, args, kwargs, index: int) -> list:
	"""The speech of a heading and a link after their text, both at once: the link's states, the heading, then the rest
	of the link. ``attrs`` is the inner of the two, and ``ancestorAttrs[index]`` the outer, which NVDA asks for next."""
	outer = ancestorAttrs[index]
	reason = _argument(args, kwargs, "reason", 2)
	inner = list(original(info, asJaws(attrs, reason), ancestorAttrs, fieldType, *args, **kwargs) or ())
	outerSpeech = list(original(info, asJaws(outer, reason), list(ancestorAttrs[:index]), fieldType, *args, **kwargs) or ())
	_local.said.add(id(outer))
	if _role(attrs) == _linkRole:
		link, linkSpeech, headingSpeech = attrs, inner, outerSpeech
	else:
		link, linkSpeech, headingSpeech = outer, outerSpeech, inner
	states, rest = _splitAfterStates(linkSpeech, _stateWords(link, reason))
	if not headingSpeech or not rest:
		# Nothing to put in between: said as NVDA says it.
		return inner + outerSpeech
	_local.pairs.append(", ".join(word for word in states + headingSpeech + rest if isinstance(word, str) and word))
	return states + headingSpeech + rest


def _innerAtLineStart(info, attrs, ancestorAttrs, formatConfig):
	"""The field right inside ``attrs`` where the line ``info`` starts, which NVDA says next, or None.

	speech.getTextInfoSpeech says the fields a line starts in (its controlStart fields before any text), outermost first:
	``attrs`` is the one after ``ancestorAttrs``. NVDA's fields don't say what is inside them, so the line's are read
	again, as speech.getTextInfoSpeech reads them. The copy leaves out where the field's node starts and ends, as it
	does."""
	import textInfos

	index = len(ancestorAttrs or ())
	fields = []
	for item in info.getTextWithFields(formatConfig):
		if not isinstance(item, textInfos.FieldCommand):
			break
		if item.command == "controlStart":
			fields.append(item.field)
			if len(fields) > index + 1:
				break
		elif item.command != "formatChange":
			break
	if len(fields) <= index + 1 or _role(fields[index]) != _role(attrs):
		return None
	inner = copy.copy(fields[index + 1])
	inner.pop("_startOfNode", None)
	inner.pop("_endOfNode", None)
	return inner


def _lineTogether(original, info, attrs, ancestorAttrs, fieldType, args, kwargs) -> list | None:
	"""A line that starts in a heading and a link right inside it, or a link and a heading right inside it, as JAWS
	says it: the link's states, the heading, then the rest of the link. ``attrs`` is the outer of the two, which NVDA
	asks for first; the inner is said with it, and marked so that NVDA's own ask for it says nothing. None when the line
	doesn't start so, or there is nothing to put in between."""
	role = _role(attrs)
	if role not in (_linkRole, _headingRole):
		return None
	inner = _innerAtLineStart(info, attrs, ancestorAttrs, _argument(args, kwargs, "formatConfig", 0))
	innerRole = _role(inner) if inner is not None else None
	if innerRole not in (_linkRole, _headingRole) or innerRole == role:
		return None
	reason = _argument(args, kwargs, "reason", 2)
	outerSpeech = list(original(info, asJaws(attrs, reason), ancestorAttrs, fieldType, *args, **kwargs) or ())
	# The inner field is said as the outer is: for a heading or a link, NVDA says the same before a line's text whether
	# the line before was in it or not.
	innerSpeech = list(original(info, asJaws(inner, reason), list(ancestorAttrs or ()) + [attrs], fieldType, *args, **kwargs) or ())
	if role == _linkRole:
		link, linkSpeech, headingSpeech = attrs, outerSpeech, innerSpeech
	else:
		link, linkSpeech, headingSpeech = inner, innerSpeech, outerSpeech
	states, rest = _splitAfterStates(linkSpeech, _stateWords(link, reason))
	if not headingSpeech or not rest:
		return None
	_local.lineInner = (info, attrs, innerRole)
	said = states + headingSpeech + rest
	_noteOnce(
		_loggedLines,
		f"{role}/{innerRole}/{bool(states)}",
		f"jawsMigrator: a line that starts in a {'link and a heading' if role == _linkRole else 'heading and a link'} is said as JAWS's SayLine and arrow keys say it, the link's states and the heading before \"link\": {', '.join(word for word in said if isinstance(word, str) and word)}",
	)
	return said


def _saidWithOuter(info, attrs, ancestorAttrs) -> bool:
	"""Whether NVDA asks, reading a line, for the inner field _lineTogether said already with the outer one."""
	pending = getattr(_local, "lineInner", None)
	if pending is None:
		return False
	_local.lineInner = None
	pendingInfo, outer, role = pending
	if pendingInfo is not info or not ancestorAttrs or _role(attrs) != role:
		return False
	last = ancestorAttrs[-1]
	return last is outer or last == outer


def _fieldSpeechGuarded(original):
	"""NVDA's speech for a field of a document's text: a link without its title, in quick navigation a link or heading
	without its description, as quick navigation reports a heading on a web page, the heading before "link", and
	reading a line that starts in a heading and a link, the link's states, the heading, then "link"."""

	@functools.wraps(original)
	def getControlFieldSpeech(self, attrs, ancestorAttrs, fieldType, *args, **kwargs):
		if not _enabled:
			return original(self, attrs, ancestorAttrs, fieldType, *args, **kwargs)
		if fieldType in LINE_START and _caret is not None and _argument(args, kwargs, "reason", 2) == _caret:
			try:
				if _saidWithOuter(self, attrs, ancestorAttrs):
					# Said already, with the field it is right inside.
					return []
				if not _argument(args, kwargs, "extraDetail", 1, False):
					said = _lineTogether(original, self, attrs, ancestorAttrs, fieldType, args, kwargs)
					if said is not None:
						return said
			except Exception:
				_local.lineInner = None
				_failure("could not say a link's states and the heading before \"link\" on a line")
		if fieldType == AFTER_TEXT and getattr(_local, "headings", 0) and _argument(args, kwargs, "reason", 2) == _quickNav:
			if id(attrs) in _local.said:
				# Said already, with the other of its pair.
				return []
			try:
				index = _pairedWith(attrs, ancestorAttrs)
				if index is not None:
					return _together(original, self, attrs, ancestorAttrs, fieldType, args, kwargs, index)
			except Exception:
				_failure("could not say a heading before the link in it")
		try:
			field = asJaws(attrs, _argument(args, kwargs, "reason", 2))
		except Exception:
			_failure("could not leave a link's title or description out")
			field = attrs
		return original(self, field, ancestorAttrs, fieldType, *args, **kwargs)

	setattr(getControlFieldSpeech, MARK, _TOKEN)
	setattr(getControlFieldSpeech, ORIGINAL, original)
	return getControlFieldSpeech


def _reportGuarded(original):
	"""NVDA's report of what quick navigation moved to on a web page, which says a heading before the link in it."""

	@functools.wraps(original)
	def report(item, *args, **kwargs):
		if not _enabled or not isHeading(item):
			return original(item, *args, **kwargs)
		depth = getattr(_local, "headings", 0)
		if not depth:
			_local.said, _local.pairs = set(), []
		_local.headings = depth + 1
		try:
			return original(item, *args, **kwargs)
		finally:
			_local.headings = depth
			if not depth:
				if _local.pairs:
					try:
						_log().debug(
							f"jawsMigrator: quick navigation moved to a heading ({item.itemType}) with a link, so NVDA says the heading before \"link\", as JAWS does: {'; '.join(_local.pairs)}",
						)
					except Exception:
						pass
				_local.said, _local.pairs = set(), []

	setattr(report, MARK, _TOKEN)
	setattr(report, ORIGINAL, original)
	return report
