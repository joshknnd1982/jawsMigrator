# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""An edit field on a web page is said as JAWS says it when the focus moves to it.

A tester replied to a reddit post in Edge. They pressed E to the reply box, then Enter, and JAWS said "edit, blank,
placeholder, Join the conversation". NVDA said "main landmark", then "Join the conversation, edit, multi line, blank"
(ClassicSpeech put "blank" before "multi line"). Three things differ:

- The placeholder. The box has no label, only the grey text "Join the conversation", so Edge and Chrome make that text
  its name and tell screen readers so (IAccessible2's "name-from:placeholder"); they then give no "placeholder" of its
  own, and NVDA says the text as the box's name. JAWS's scripts for Edge, Chrome and Firefox (IA2Browser.jss,
  HandleSayObjectForEdit) say an empty edit field as its name and "edit", its states, "blank", then "placeholder" and
  the placeholder, then its description; a name made from the placeholder isn't said as the name. NVDA said a
  placeholder of its own before "blank" (``speech._getPlaceholderSpeechIfTextEmpty``), without the word. Now, when the
  focus moves to an empty edit field on a web page, or NVDA+Tab reports one, NVDA says its placeholder after "blank",
  after the word "placeholder", then its description; a name the browser made from the placeholder is said there, not
  as the name. NVDA says no placeholder for a field with text in it, and JAWS doesn't either.
- "multi line". JAWS says "edit" for an edit field of several lines too, as JAWS comes: its "Announce multi-line edit"
  option (AnnounceMultilineEdit in Default.jcf) is off. NVDA doesn't say "multi line" for an edit field any more,
  anywhere it speaks one (``speech.getPropertiesSpeech``). Braille still shows it.
- "main landmark". NVDA said it when E moved browse mode's cursor to the box, and again when Enter put the focus in it:
  on a focus change in focus mode, NVDA says each landmark, region, list or grouping the focus has entered since the
  last focus (``browseMode.BrowseModeDocumentTreeInterceptor._replayFocusEnteredEvents``), and in browse mode the focus
  stays where it was. JAWS's virtual cursor takes the focus with it, so the focus hasn't entered anything JAWS's
  cursor wasn't in already. Now, when the focus moves within a web page, NVDA doesn't say again what browse mode's
  cursor was in (NVDA said that when the cursor got there); Tab to a field in another landmark still says it.

None of these is what another part of the assistant changes, so each gives NVDA its own back when it is turned off. It
works while the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import functools
import threading
import weakref

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "sayFormFieldsAsJaws"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorFormFields"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: What NVDA says for an object (speech.speech.getObjectSpeech), for its properties (getPropertiesSpeech), and for an
#: empty field's placeholder (_getPlaceholderSpeechIfTextEmpty).
OBJECT_SPEECH = "getObjectSpeech"
PROPERTIES_SPEECH = "getPropertiesSpeech"
PLACEHOLDER_SPEECH = "_getPlaceholderSpeechIfTextEmpty"
#: What JAWS says before a placeholder (common.jsm, cmsgPlaceholder).
PLACEHOLDER = "placeholder"
#: The IAccessible2 attribute where Edge and Chrome say what an object's name was made from, and its value for a name
#: made from the placeholder.
NAME_FROM = "name-from"
FROM_PLACEHOLDER = "placeholder"
#: A virtual buffer's control field names the object it stands for with these.
FIELD_DOCUMENT = "controlIdentifier_docHandle"
FIELD_ID = "controlIdentifier_ID"
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: NVDA's Role.EDITABLETEXT, State.MULTILINE and the OutputReasons used here, once known.
_editRole = None
_multiLine = None
_focus = None
_query = None
_focusEntered = None
#: For each thread: the fields browse mode's cursor was in as a focus event started (``heard``: a weak reference to the
#: document, and the fields' identifiers), and the edit field whose speech is being made (``field``: [obj, textEmpty]).
_local = threading.local()
#: "multi line" left out is logged once.
_loggedMultiLine = False


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


def wanted(stateData: dict) -> bool:
	"""Whether edit fields on web pages are said as JAWS says them: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have NVDA say edit fields as JAWS says them, from now on."""
	global _enabled, _editRole, _multiLine, _focus, _query, _focusEntered
	if _enabled:
		return
	_enabled = True
	try:
		from controlTypes import OutputReason, Role, State
		from speech import speech

		_editRole, _multiLine = Role.EDITABLETEXT, State.MULTILINE
		_focus, _query, _focusEntered = OutputReason.FOCUS, OutputReason.QUERY, OutputReason.FOCUSENTERED
		with _lock:
			_replace(speech, PROPERTIES_SPEECH, _propertiesGuarded)
			# The object's speech changes only where NVDA's own placeholder can be taken out of it, so a name made from
			# the placeholder is never left out without the placeholder said after "blank".
			if _replace(speech, PLACEHOLDER_SPEECH, _placeholderGuarded):
				_replace(speech, OBJECT_SPEECH, _objectGuarded)
	except Exception:
		_failure("can't have NVDA say edit fields as JAWS says them")


def unregister() -> None:
	"""Give NVDA its own functions back, where nothing has been put over the assistant's since."""
	global _enabled
	if not _enabled:
		return
	_enabled = False
	_local.heard = None
	_local.field = None
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
		_failure(f"NVDA has no {name} the assistant knows, so NVDA says edit fields there as it does")
		return False
	installed = guarded(current)
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, current))
	_debug(f"jawsMigrator: edit fields are said as JAWS says them ({getattr(owner, '__name__', owner)}.{name})")
	return True


def _mark(installed, original):
	setattr(installed, MARK, _TOKEN)
	setattr(installed, ORIGINAL, original)
	return installed


def _argument(args: tuple, kwargs: dict, name: str, index: int, default=None):
	if name in kwargs:
		return kwargs[name]
	return args[index] if len(args) > index else default


# -- "multi line" ----------------------------------------------------------------------------------------------------


def withoutMultiLine(propertyValues: dict) -> dict:
	"""The properties NVDA says, without "multi line" for an edit field: a copy when anything changes."""
	global _loggedMultiLine
	if _multiLine is None:
		return propertyValues
	states = propertyValues.get("states")
	negative = propertyValues.get("negativeStates")
	if not ((states and _multiLine in states) or (negative and _multiLine in negative)):
		return propertyValues
	role = propertyValues.get("role", propertyValues.get("_role"))
	if role is None or role != _editRole:
		return propertyValues
	values = dict(propertyValues)
	# NVDA keeps the sets it passes (the object's cache): the assistant changes copies.
	if states and _multiLine in states:
		values["states"] = set(states) - {_multiLine}
	if negative and _multiLine in negative:
		values["negativeStates"] = set(negative) - {_multiLine}
	if not _loggedMultiLine:
		_loggedMultiLine = True
		_debug('jawsMigrator: NVDA doesn\'t say "multi line" for an edit field, as JAWS doesn\'t with its "Announce multi-line edit" off, as JAWS comes')
	return values


def _propertiesGuarded(original):
	"""NVDA's speech for properties: an edit field's states without "multi line"."""

	@functools.wraps(original)
	def getPropertiesSpeech(*args, **propertyValues):
		if _enabled:
			try:
				propertyValues = withoutMultiLine(propertyValues)
			except Exception:
				_failure('could not leave "multi line" out')
		return original(*args, **propertyValues)

	return _mark(getPropertiesSpeech, original)


# -- the placeholder -------------------------------------------------------------------------------------------------


def placeholderOf(obj):
	"""``(placeholder, name made from it)`` for an edit field on a web page with a placeholder, or None.

	The name is None where the field's name isn't its placeholder.
	"""
	if obj.role != _editRole:
		return None
	attributes = getattr(obj, "IA2Attributes", None)
	if not isinstance(attributes, dict):
		# Not a web page's object (IAccessible2: Edge, Chrome, Firefox), where JAWS's IA2Browser.jss speaks.
		return None
	name = None
	if attributes.get(NAME_FROM) == FROM_PLACEHOLDER:
		name = obj.name or None
	placeholder = getattr(obj, "placeholder", None) or name
	if not placeholder:
		return None
	return placeholder, name


def _firstText(sequence: list) -> int | None:
	for index, item in enumerate(sequence):
		if isinstance(item, str):
			return index
	return None


def rearrange(sequence, placeholder: str, name: str | None, textEmpty: bool, description: str | None = None) -> list:
	"""NVDA's speech for an edit field, as JAWS says it: without a ``name`` made from the placeholder, and, for an empty
	field, "placeholder" and the ``placeholder`` after the rest, then the field's ``description``.

	NVDA's own placeholder is not in ``sequence``: NVDA's _getPlaceholderSpeechIfTextEmpty gave nothing.
	"""
	result = list(sequence)
	if name:
		first = _firstText(result)
		if first is not None and result[first] == name:
			del result[first]
	if not textEmpty:
		return result
	moved = []
	if description:
		first = _firstText(result)
		for index in range(len(result) - 1, -1, -1):
			if index != first and isinstance(result[index], str) and result[index] == description:
				moved.append(result.pop(index))
				break
	result.extend([PLACEHOLDER, placeholder])
	result.extend(moved)
	return result


def _placeholderGuarded(original):
	"""NVDA's placeholder for an empty field: nothing for the field the assistant says, which says it after "blank"."""

	@functools.wraps(original)
	def _getPlaceholderSpeechIfTextEmpty(obj, *args, **kwargs):
		field = getattr(_local, "field", None)
		if not _enabled or field is None or field[0] is not obj:
			return original(obj, *args, **kwargs)
		textEmpty, sequence = original(obj, *args, **kwargs)
		field[1] = bool(textEmpty)
		return textEmpty, []

	return _mark(_getPlaceholderSpeechIfTextEmpty, original)


def _fieldSpeech(original, obj, args, kwargs):
	"""NVDA's speech for the edit field ``obj`` as the focus moves to it or NVDA+Tab reports it, as JAWS says it."""
	try:
		found = placeholderOf(obj)
	except Exception:
		_failure("could not tell an edit field's placeholder")
		found = None
	if found is None:
		return original(obj, *args, **kwargs)
	placeholder, name = found
	previous = getattr(_local, "field", None)
	field = [obj, False]
	_local.field = field
	try:
		sequence = original(obj, *args, **kwargs)
	finally:
		_local.field = previous
	try:
		description = obj.description if field[1] else None
		result = rearrange(sequence, placeholder, name, field[1], description)
	except Exception:
		_failure("could not say an edit field's placeholder as JAWS does")
		return sequence
	if result != list(sequence):
		said = ", ".join(item for item in result if isinstance(item, str) and item)
		made = " (its name was the placeholder)" if name else ""
		_debug(f"jawsMigrator: an edit field is said as JAWS says it{made}: {said}")
	return result


# -- what browse mode's cursor was in ---------------------------------------------------------------------------------


def _identifier(pair) -> tuple | None:
	try:
		docHandle, ID = pair
		return int(docHandle), int(ID)
	except (TypeError, ValueError):
		return None


def heardFields(stack) -> frozenset:
	"""The identifiers of the fields in ``stack``, the control fields browse mode's cursor was in when NVDA last spoke."""
	found = set()
	for field in stack or ():
		try:
			identifier = _identifier((field.get(FIELD_DOCUMENT), field.get(FIELD_ID)))
		except Exception:
			identifier = None
		if identifier is not None:
			found.add(identifier)
	return frozenset(found)


def _withinPage(document) -> bool:
	"""Whether the focus moved from within ``document``'s page (or from the page itself) to where it is now."""
	import api

	ancestors = api.getFocusAncestors()
	level = api.getFocusDifferenceLevel()
	root = document.rootNVDAObject
	return any(ancestor == root for ancestor in ancestors[:level])


def beforeFocus(obj):
	"""Before NVDA handles the focus moving to ``obj``: note the fields browse mode's cursor is in. Returns what to give
	afterFocus."""
	previous = getattr(_local, "heard", None)
	if not _enabled:
		return previous
	heard = None
	try:
		import browseMode

		document = getattr(obj, "treeInterceptor", None)
		if isinstance(document, browseMode.BrowseModeDocumentTreeInterceptor) and _withinPage(document):
			state = getattr(document, "_speakTextInfoState", None)
			fields = heardFields(getattr(state, "controlFieldStackCache", None))
			if fields:
				heard = (weakref.ref(document), fields)
	except Exception:
		_failure("could not note what browse mode's cursor is in")
	_local.heard = heard
	return previous


def afterFocus(previous) -> None:
	"""After NVDA handled the focus event: forget what beforeFocus noted."""
	_local.heard = previous


def _heardAlready(obj) -> bool:
	"""Whether ``obj``, a field the focus entered, is one browse mode's cursor was in as the focus event started."""
	heard = getattr(_local, "heard", None)
	if not heard:
		return False
	documentRef, fields = heard
	document = documentRef()
	if document is None or getattr(obj, "treeInterceptor", None) is not document:
		return False
	try:
		identifier = _identifier(document.getIdentifierFromNVDAObject(obj))
	except Exception:
		return False
	return identifier is not None and identifier in fields


# -- NVDA's speech for an object ---------------------------------------------------------------------------------------


def _objectGuarded(original):
	"""NVDA's speech for an object: an edit field as JAWS says it, and nothing for a field the focus entered where
	browse mode's cursor already was."""

	@functools.wraps(original)
	def getObjectSpeech(obj, *args, **kwargs):
		if not _enabled:
			return original(obj, *args, **kwargs)
		reason = _argument(args, kwargs, "reason", 0, _query)
		if reason == _focusEntered:
			try:
				heard = _heardAlready(obj)
			except Exception:
				_failure("could not tell whether browse mode's cursor was in a field")
				heard = False
			if heard:
				# NVDA's own, for its caches and for the log; not said.
				sequence = original(obj, *args, **kwargs)
				said = ", ".join(item for item in sequence if isinstance(item, str) and item)
				if said:
					_debug(f"jawsMigrator: the focus moved where browse mode's cursor was, so NVDA doesn't say again what it is in: {said}")
				return []
			return original(obj, *args, **kwargs)
		if reason == _focus or reason == _query:
			return _fieldSpeech(original, obj, args, kwargs)
		return original(obj, *args, **kwargs)

	return _mark(getObjectSpeech, original)
