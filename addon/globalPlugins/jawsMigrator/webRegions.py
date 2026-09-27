# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Regions, groups, lists and articles on web pages are said with JAWS's words.

A tester switched to a GitHub tab in Edge (issue 30). JAWS said "MainRegion", then "new Comment group", then the
focused button. NVDA said "main landmark", then "new Comment grouping". Asked whether NVDA should use JAWS's words, the
tester asked back whether it should match, and asked for JAWS to be tested to make sure nothing was missed. So JAWS
2026 was run on Edge 154, on copies of the tester's reddit and GitHub pages, and its speech history was copied after
each key:

- As the focus moves (Tab, or coming back to a page with the focus in it), JAWS names each region the focus comes into
  as "region": "BannerRegion", "Global NavigationRegion" (a named one: its name first), "MainRegion", "Reply
  FormRegion", "ContentInfoRegion". NVDA says "banner landmark", "Global navigation landmark", "main landmark",
  "Reply form landmark", "content info landmark". A grouping is JAWS's "new Comment group", NVDA's "new Comment
  grouping".
- Reading with the arrow keys, JAWS names only the main and navigation regions, as JAWS comes (Default.jcf,
  [VirtualCursorVerbosity] at Medium: MainRegion and NavigationRegion 1; BannerRegion, ComplementaryRegion,
  ContentInfoRegion, FormRegion and SearchRegion 0), and says where each ends: "Reddit navigation region" ... "Reddit
  navigation region end", "main region" ... "main region end". NVDA says each landmark it comes into, "banner
  landmark", "search landmark" and "complementary landmark" too, and never where one ends.
- A list is JAWS's "list of 2 items" ... "list end" (jfw.exe: "List of %d items", "list end"), NVDA's "list with 2
  items" ... "out of list". A region with a name is "Community actions region" in both, and it ends in JAWS's "Community
  actions region end", NVDA's "out of region"; an article ends in "Comment by visible_help article end", NVDA's "out of
  article". A group, reading, is JAWS's "group start new Comment" ... "group end new Comment" (FsDomSrv.dll: "group start
  %s", "group end %s"), NVDA's "new Comment grouping" ... "out of grouping".

So on web pages (Edge, Chrome and Firefox, read through IAccessible2), these are said with JAWS's words:

- what NVDA says for a field of the page's text (virtualBuffers.gecko_ia2.Gecko_ia2_TextInfo, as browse mode reads it
  and says the focus in it): for the focus and quick navigation, a landmark is "X region" and a grouping is "group";
  reading (arrow keys, Say All), the banner, search, form, complementary and content info regions aren't said (except in
  Say All, where JAWS names them too), the main and navigation regions are said with "region" and where they end, and
  lists, regions, articles and groups start and end in JAWS's words. Where NVDA's settings have it say no landmarks,
  lists, articles or groupings (Document Formatting), nothing more is said for them than NVDA says.
- what NVDA says for a web page's object that is the focus or that the focus comes into
  (speech.speech.getObjectPropertiesSpeech): a landmark is "X region" and a grouping is "group".

A field or an object with a role text of its page's own (aria-roledescription) is said as NVDA says it, and so is
everything else. Braille is unchanged. It works while the assistant runs, unless it is turned off in NVDA's Settings,
JAWS Migration Assistant.

Other parts of the assistant change NVDA's getControlFieldSpeech in the speech package (quickNavHeadings) and in
textInfos.TextInfo (linkSpeech), and getObjectSpeech and getPropertiesSpeech (formFields). This one puts a
getControlFieldSpeech on the class of a web page's text, which takes the one it comes from, whatever is there, and
getObjectPropertiesSpeech, which no other part changes. So each gives NVDA its own back when it is turned off.
"""

from __future__ import annotations

import functools
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "sayWebRegionsAsJaws"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorWebRegions"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: How NVDA says a field of a web page's text, and the properties of an object.
FIELD_SPEECH = "getControlFieldSpeech"
OBJECT_PROPERTIES = "getObjectPropertiesSpeech"
#: NVDA's field types: a field the text comes into, and one it leaves.
STARTS = frozenset(("start_addedToControlFieldStack", "start_relative"))
ENDS = frozenset(("end_removedFromControlFieldStack", "end_relative"))
#: The landmarks JAWS names as it reads a page with the arrow keys, as JAWS comes (Default.jcf, Medium verbosity).
READ_LANDMARKS = frozenset(("main", "navigation"))
#: The landmark that is a form: Edge gives a named form the role form, and NVDA says "form".
FORM = "form"
#: JAWS's words.
REGION = "region"
END = "end"
GROUP = "group"
GROUP_START = "group start"
GROUP_END = "group end"
LIST_OF = "list of {} items"
LIST_END = "list end"
#: The number of a list's items, in NVDA's field.
ITEM_COUNT = "_childcontrolcount"
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16
#: The log names this many changes, each once.
_MOST_LOGGED = 50

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)]. NVDA's is None
#: where the class had none of its own and took it from the class it comes from.
_replaced: list = []
#: NVDA's roles, output reasons and landmark names, once known.
_roles = None
_focus = None
_focusEntered = None
_quickNav = None
_sayAll = None
_landmarkNames: dict = {}
#: NVDA's class of a web page's object read through IAccessible2 (NVDAObjects.IAccessible.ia2Web.Ia2Web).
_webObjectClass = None
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


def _debug(message: str) -> None:
	try:
		_log().debug(message)
	except Exception:
		pass


def _noteOnce(key: str, message: str) -> None:
	if key in _logged or len(_logged) >= _MOST_LOGGED:
		return
	_logged.add(key)
	_debug(message)


def wanted(stateData: dict) -> bool:
	"""Whether regions, groups, lists and articles on web pages are said with JAWS's words: on unless turned off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have NVDA say regions, groups, lists and articles on web pages with JAWS's words, from now on."""
	global _enabled, _roles, _focus, _focusEntered, _quickNav, _sayAll, _landmarkNames, _webObjectClass
	if _enabled:
		return
	_enabled = True
	try:
		import aria
		from controlTypes import OutputReason, Role
		from speech import speech

		_roles = Role
		_focus, _focusEntered = OutputReason.FOCUS, OutputReason.FOCUSENTERED
		_quickNav, _sayAll = getattr(OutputReason, "QUICKNAV", None), getattr(OutputReason, "SAYALL", None)
		_landmarkNames = dict(aria.landmarkRoles)
		with _lock:
			try:
				from virtualBuffers.gecko_ia2 import Gecko_ia2_TextInfo

				_replace(Gecko_ia2_TextInfo, FIELD_SPEECH, _fieldSpeechGuarded, inherited=True)
			except ImportError:
				_failure("NVDA has no web page text the assistant knows, so NVDA says what a page's text is in as it does")
			try:
				from NVDAObjects.IAccessible.ia2Web import Ia2Web

				_webObjectClass = Ia2Web
				_replace(speech, OBJECT_PROPERTIES, _objectPropertiesGuarded)
			except ImportError:
				_failure("NVDA has no web page objects the assistant knows, so NVDA says landmarks and groupings as it does")
	except Exception:
		_failure("can't have NVDA say regions, groups, lists and articles on web pages with JAWS's words")


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
		_failure(f"NVDA has no {name} the assistant knows, so NVDA says landmarks there as it does")
		return False
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, original))
	_debug(f"jawsMigrator: regions, groups, lists and articles on web pages are said with JAWS's words ({getattr(owner, '__name__', owner)}.{name})")
	return True


def _fromBase(owner, name: str):
	"""What ``owner`` takes from the class it comes from, looked up at each call, as Python does."""

	def inherited(self, *args, **kwargs):
		return getattr(super(owner, self), name)(*args, **kwargs)

	inherited.__name__ = name
	return inherited


def _mark(function, original):
	setattr(function, MARK, _TOKEN)
	setattr(function, ORIGINAL, original)
	return function


def _argument(args: tuple, kwargs: dict, name: str, index: int, default=None):
	if name in kwargs:
		return kwargs[name]
	return args[index] if len(args) > index else default


def _words(sequence) -> str:
	return ", ".join(item for item in sequence if isinstance(item, str) and item.strip())


# -- JAWS's words -----------------------------------------------------------------------------------------------------


def nvdaLandmark(landmark: str) -> str:
	"""What NVDA says for a landmark: "main landmark" (NVDAObject.roleText, speech.getControlFieldSpeech)."""
	return f"{_landmarkNames[landmark]} {_roles.LANDMARK.displayString}"


def jawsLandmark(landmark: str) -> str:
	"""What JAWS says for a landmark: "main region"."""
	return f"{_landmarkNames[landmark]} {REGION}"


def _swapped(sequence, old: str, new: str):
	"""``sequence`` with its first item ``old`` put as ``new``, or None when it has no such item."""
	result = list(sequence)
	for index, item in enumerate(result):
		if isinstance(item, str) and item == old:
			result[index] = new
			return result
	return None


def _without(sequence, old: str):
	"""``sequence`` without its first item ``old``, or None when it has no such item."""
	result = list(sequence)
	for index, item in enumerate(result):
		if isinstance(item, str) and item == old:
			del result[index]
			return result
	return None


def _said(sequence) -> bool:
	"""Whether NVDA says anything with ``sequence`` (its speech leaves out empty words)."""
	return any(isinstance(item, str) and item.strip() for item in sequence)


def _withName(sequence, name: str, before: str):
	"""``sequence`` with ``name`` before its item ``before``, where NVDA left the name out (it names a landmark, a region
	or an article only for the focus and quick navigation; JAWS names them as you read too)."""
	if sequence is None or not name or any(isinstance(item, str) and item == name for item in sequence):
		return sequence
	result = list(sequence)
	for index, item in enumerate(result):
		if isinstance(item, str) and item == before:
			result.insert(index, name)
			return result
	return result


def _named(name, *words) -> list:
	return [word for word in (name, *words) if word]


def _listWords(attrs, sequence):
	"""NVDA's "list", "with 2 items" as JAWS's "list of 2 items", or None when NVDA gave no number."""
	count = attrs.get(ITEM_COUNT)
	if not count:
		return None
	result = list(sequence)
	listWord = _roles.LIST.displayString
	for index, item in enumerate(result):
		if isinstance(item, str) and item == listWord:
			for later in range(index + 1, len(result)):
				other = result[later]
				if isinstance(other, str) and str(count) in other.split():
					del result[later]
					result[index] = LIST_OF.format(count)
					return result
			return None
	return None


def isLandmark(attrs) -> str | None:
	"""The landmark a field is, "main", or None: a landmark, or a named form (which Edge gives the role form)."""
	landmark = attrs.get("landmark")
	if landmark not in _landmarkNames:
		return None
	role = attrs.get("role")
	if role == _roles.LANDMARK or (landmark == FORM and role == _roles.FORM):
		return landmark
	return None


def fieldWords(attrs, fieldType: str, reason, said: list, formatConfig=None, extraDetail: bool = False):
	"""What JAWS says for a field of a web page's text, where NVDA would say ``said``; None to say what NVDA says."""
	if attrs.get("roleText"):
		# The page's own role text (aria-roledescription).
		return None
	role = attrs.get("role")
	name = attrs.get("name") or ""
	start = fieldType in STARTS
	end = fieldType in ENDS and not extraDetail
	if not start and not end:
		return None
	focus = reason is not None and reason in (_focus, _quickNav)
	sayAll = reason is not None and reason == _sayAll
	landmark = isLandmark(attrs)
	if landmark:
		if not focus and not sayAll and landmark not in READ_LANDMARKS:
			# JAWS doesn't name it as you read.
			return [] if (start or _said(said)) else None
		if start:
			if not _said(said):
				return None
			nvdaWords = _roles.FORM.displayString if role == _roles.FORM else nvdaLandmark(landmark)
			return _withName(_swapped(said, nvdaWords, jawsLandmark(landmark)), name, jawsLandmark(landmark))
		if focus:
			return None
		if formatConfig is None:
			import config

			formatConfig = config.conf["documentFormatting"]
		if not formatConfig["reportLandmarks"]:
			return None
		return _named(name, f"{jawsLandmark(landmark)} {END}")
	if role == _roles.GROUPING:
		if not _said(said):
			return None
		if start:
			if focus:
				return _swapped(said, _roles.GROUPING.displayString, GROUP)
			rest = _without(said, _roles.GROUPING.displayString)
			if rest is None:
				return None
			if name:
				withoutName = _without(rest, name)
				if withoutName is not None:
					rest = withoutName
			return _named(GROUP_START, name) + rest
		return None if focus else _named(GROUP_END, name)
	if role == _roles.LIST:
		if not _said(said):
			return None
		if start:
			return _listWords(attrs, said)
		return None if focus else [LIST_END]
	if role in (_roles.REGION, _roles.ARTICLE):
		if focus or not _said(said):
			return None
		if start:
			return _withName(said, name, role.displayString) if name else None
		return _named(name, f"{role.displayString} {END}")
	return None


def _fieldSpeechGuarded(original):
	"""NVDA's speech for a field of a web page's text, with JAWS's words for regions, groups, lists and articles."""

	@functools.wraps(original)
	def getControlFieldSpeech(self, attrs, ancestorAttrs, fieldType, *args, **kwargs):
		said = original(self, attrs, ancestorAttrs, fieldType, *args, **kwargs)
		if not _enabled:
			return said
		try:
			words = fieldWords(
				attrs,
				fieldType,
				_argument(args, kwargs, "reason", 2),
				said,
				_argument(args, kwargs, "formatConfig", 0),
				_argument(args, kwargs, "extraDetail", 1, False),
			)
		except Exception:
			_failure("could not say a region, group, list or article on a web page with JAWS's words")
			return said
		if words is None or words == list(said):
			return said
		_noteOnce(
			f"{attrs.get('role')}|{attrs.get('landmark')}|{fieldType}",
			f"jawsMigrator: a web page's field is said with JAWS's words: {_words(words)!r} (NVDA's: {_words(said)!r})",
		)
		return words

	return _mark(getControlFieldSpeech, original)


# -- a web page's objects -------------------------------------------------------------------------------------------


def objectWords(obj, said: list):
	"""What JAWS says for a web page's landmark or grouping as the focus or where the focus is; None for NVDA's."""
	if _webObjectClass is None or not isinstance(obj, _webObjectClass):
		return None
	landmark = getattr(obj, "landmark", None)
	roleText = getattr(obj, "roleText", None)
	if landmark in _landmarkNames:
		if roleText != nvdaLandmark(landmark):
			return None
		return _swapped(said, roleText, jawsLandmark(landmark))
	if obj.role == _roles.GROUPING and not roleText:
		return _swapped(said, _roles.GROUPING.displayString, GROUP)
	return None


def _objectPropertiesGuarded(original):
	"""NVDA's speech for an object's properties, with JAWS's words for a web page's landmark or grouping."""

	@functools.wraps(original)
	def getObjectPropertiesSpeech(obj, *args, **kwargs):
		said = original(obj, *args, **kwargs)
		if not _enabled or _argument(args, kwargs, "reason", 0) not in (_focus, _focusEntered):
			return said
		try:
			words = objectWords(obj, said)
		except Exception:
			_failure("could not say a web page's landmark or grouping with JAWS's words")
			return said
		if words is None or words == list(said):
			return said
		_noteOnce(
			f"object|{getattr(obj, 'landmark', None)}|{obj.role}",
			f"jawsMigrator: a web page's object is said with JAWS's words: {_words(words)!r} (NVDA's: {_words(said)!r})",
		)
		return words

	return _mark(getObjectPropertiesSpeech, original)
