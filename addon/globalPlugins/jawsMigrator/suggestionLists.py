# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Get to the suggestions an edit field on a web page offers, and choose one (issue 47).

A tester wrote about visible.com's home internet page: "You enter your address. They have suggested addresses. You
can't get to them using NVDA." The page's address field (``input#address-input``, ``aria-autocomplete="list"``,
``aria-controls="address-dropdown"``) shows its suggestions in a ``role="listbox"`` after it, each one a ``div`` with
``role="option"`` and ``tabindex="0"``. Its script (clientlib-fioscheckavailability) does three things, which were
measured in Chromium on 30 September 2026:

- Down Arrow in the field moves the focus to the first suggestion (``first.focus()``), and Up Arrow, Down Arrow, Enter,
  Space and Escape work on the suggestions from there;
- the field's ``blur`` event hides the list 150 milliseconds later (``setTimeout(closeAddressDropdown, 150)``), so the
  suggestion that has the focus is hidden as soon as it gets it, and the focus falls to the page: the keys of the
  page's own suggestions never work, for anyone;
- a suggestion is chosen by its ``mousedown`` event, or by Enter or Space on it when it has the focus. A ``click``
  (``element.click()``, which is all a screen reader's default action sends) chooses nothing.

What NVDA 2026.2 does with that page, in its source:

- Down Arrow in the field goes to the page, which does the first thing above: NVDA says the first suggestion, then the
  list closes;
- Escape, then Down Arrow in browse mode, moves browse mode's cursor to a suggestion. NVDA's "Automatic focus mode for
  caret movement" (virtualBuffers.autoPassThroughOnCaretMove), which the migration turns on for JAWS's Auto Forms
  Mode, has ``browseMode.BrowseModeTreeInterceptor.shouldPassThrough`` choose focus mode for a list item
  (ALWAYS_SWITCH_TO_PASS_THROUGH_ROLES), and ``_set_selection`` then has ``setFocus()`` move the focus to it: the field
  loses it and the list closes;
- Enter on a suggestion in browse mode: ``script_activatePosition`` sets the focus to it
  (``_focusLastFocusableObject``: the list closes), and ``_activatePosition`` chooses focus mode for it, so nothing is
  pressed. Where it does reach ``_activateNVDAObject``, ``doAction`` sends only a ``click``.

So the suggestions can't be chosen with NVDA, and the key that reaches them, Down Arrow, only shows them going. What
this module does about it, for the suggestions of the edit field that has the focus (the list it ``aria-controls``, a
field that says it has autocomplete), and for those alone:

- browse mode leaves the focus in the field, in browse mode, when its cursor is on one of the field's suggestions, so
  the list stays open;
- Enter, or Space, on a suggestion presses it with the mouse, as NVDA does for a control without a default action
  (``BrowseModeTreeInterceptor._activateNVDAObject``): the pointer goes to it, presses and lets go, and goes back. The
  page gets ``mousedown``, ``mouseup`` and ``click``, which chooses a suggestion on this page and on one that listens for
  ``click``. NVDA says the suggestion and "selected";
- Down Arrow alone in that field, in focus mode, goes on in browse mode past the field, to the first suggestion, which
  NVDA says: browse mode's own way when the page doesn't take the key (``event_caretMovementFailed``), and JAWS's Auto
  Forms Mode leaves a field of one line with Down Arrow too (see fieldEdges). The key isn't sent to the page.

A field that is a combo box (its own role, or expanded or collapsed) does as it did: its page handles its keys. It works
while the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import functools
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "chooseWebSuggestions"
#: Marks the assistant's own version of NVDA's method, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorSuggestionLists"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: Keeps NVDA's own method on the assistant's.
ORIGINAL = "_jawsMigratorSuggestionListsOriginal"
#: The key that goes on past a field of one line, in browse mode (see fieldEdges).
LEAVING_KEY = "downArrow"
#: How far up from an object the list is looked for (an option, and what an option has in it).
_MOST_LEVELS = 8
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: The suggestion browse mode was last kept from, so the log says so once for each.
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
	"""Whether a web page's suggestions can be reached and chosen: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have NVDA leave the focus in a field whose suggestion browse mode is on, and press it with the mouse, from now on."""
	global _enabled
	_enabled = True
	try:
		import browseMode

		document = browseMode.BrowseModeDocumentTreeInterceptor
		with _lock:
			# All three on the class of web pages' documents, so nothing is put over what another module has on the class
			# above it: autoFormsMode has its own wrapper of shouldPassThrough there.
			_replace(document, "shouldPassThrough", _decisionGuarded, inherited=True)
			_replace(document, "_shouldSetFocusToObj", _focusGuarded)
			_replace(document, "_activateNVDAObject", _activationGuarded, inherited=True)
	except Exception:
		_failure("can't keep the focus in a field while browse mode is on its suggestion, so NVDA does as it does")


def unregister() -> None:
	"""Give NVDA its own methods back, where nothing has been put over the assistant's since."""
	global _enabled, _noted
	_enabled = False
	_noted = None
	with _lock:
		for owner, name, installed, original in reversed(_replaced):
			try:
				if vars(owner).get(name) is installed:
					if original is None:
						# NVDA's own is on the class above, which the class has again once this is gone.
						delattr(owner, name)
					else:
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


def _replace(owner, name: str, guarded, inherited: bool = False) -> bool:
	"""Put the assistant's version of ``name`` in the place of NVDA's own on ``owner``, once. True when it is there.

	With ``inherited``, ``owner`` has none of its own: the assistant's calls the one ``owner`` has from the class above
	it, whatever that is by then, and taking it away leaves ``owner`` as it was.
	"""
	current = vars(owner).get(name)
	if _isOurs(current):
		return True
	if inherited and current is None:
		if not callable(getattr(owner, name, None)):
			_failure(f"NVDA has no {name} the assistant knows, so NVDA does as it does with a page's suggestions")
			return False

		def current(self, *args, **kwargs):
			return getattr(super(owner, self), name)(*args, **kwargs)

		current.__name__ = name
		installed = guarded(current)
		setattr(owner, name, installed)
		_replaced.append((owner, name, installed, None))
	else:
		if not callable(current):
			_failure(f"NVDA has no {name} the assistant knows, so NVDA does as it does with a page's suggestions")
			return False
		installed = guarded(current)
		setattr(owner, name, installed)
		_replaced.append((owner, name, installed, current))
	_log().debug(f"jawsMigrator: NVDA leaves the focus in a field when browse mode is on its suggestion ({getattr(owner, '__name__', owner)}.{name})")
	return True


def _mark(function, original):
	setattr(function, MARK, _TOKEN)
	setattr(function, ORIGINAL, original)
	return function


def _controls(field) -> list:
	"""The objects the edit field controls (aria-controls), as NVDA reads them."""
	return [control for control in (field.controllerFor or ()) if control is not None]


def _same(one, other) -> bool:
	"""Whether two NVDA objects are the same thing on the page, however each was reached.

	NVDA's own ``==`` is false for two objects of different classes, and the list reached through ``controllerFor`` and the
	same list reached as an option's parent needn't have the same overlay classes. The unique ID within the window
	(IAccessible2) tells, as NVDA's ``_isEqual`` uses it.
	"""
	if one == other:
		return True
	try:
		window, uniqueID = one.IA2WindowHandle, one.IA2UniqueID
		return bool(window and uniqueID) and (window, uniqueID) == (other.IA2WindowHandle, other.IA2UniqueID)
	except Exception:
		return False


def _suggestingField(field) -> bool:
	"""Whether ``field`` is an edit field of one line that says it has suggestions and isn't a combo box.

	A combo box, by its role or by being expanded or collapsed, has its page handle its keys.
	"""
	from controlTypes import Role, State

	if field is None:
		return False
	states = field.states
	if State.EDITABLE not in states or State.MULTILINE in states or State.AUTOCOMPLETE not in states:
		return False
	if field.role == Role.COMBOBOX:
		return False
	return State.EXPANDED not in states and State.COLLAPSED not in states


def _suggestionOf(obj):
	"""The suggestion ``obj`` is, or is in, in the list the focused edit field controls. None for anything else."""
	import api

	if obj is None:
		return None
	field = api.getFocusObject()
	if field is None or _same(obj, field) or not _suggestingField(field):
		return None
	lists = _controls(field)
	if not lists:
		return None
	child = obj
	for _ in range(_MOST_LEVELS):
		parent = child.parent
		if parent is None:
			return None
		if any(_same(parent, suggestions) for suggestions in lists):
			return child
		child = parent
	return None


def _note(obj, what: str) -> None:
	global _noted
	if obj is _noted:
		return
	_noted = obj
	try:
		name = obj.name
	except Exception:
		name = None
	_log().debug(f"jawsMigrator: {what} for the suggestion {name!r}, so the focus stays in the field")


def _decisionGuarded(original):
	"""NVDA's choice of focus mode or browse mode: browse mode on a suggestion, whose focus mode moved the focus to it."""

	@functools.wraps(original, updated=())
	def shouldPassThrough(self, obj, *args, **kwargs):
		answer = original(self, obj, *args, **kwargs)
		if not answer or not _enabled:
			return answer
		try:
			if _suggestionOf(obj) is None:
				return answer
			_note(obj, "NVDA stays in browse mode")
			return False
		except Exception:
			_failure("could not tell whether browse mode is on a suggestion, so NVDA chooses the mode as it does")
			return answer

	return _mark(shouldPassThrough, original)


def _focusGuarded(original):
	"""Whether NVDA sets the focus to an object: not to a suggestion, which would take it from the field and close the list."""

	@functools.wraps(original, updated=())
	def _shouldSetFocusToObj(self, obj):
		answer = original(self, obj)
		if not answer or not _enabled:
			return answer
		try:
			if _suggestionOf(obj) is None:
				return answer
			_note(obj, "NVDA doesn't set the focus")
			return False
		except Exception:
			_failure("could not tell whether browse mode is on a suggestion, so NVDA sets the focus as it does")
			return answer

	return _mark(_shouldSetFocusToObj, original)


def _activationGuarded(original):
	"""NVDA's activation of an object: a suggestion is pressed with the mouse, not sent a click alone."""

	@functools.wraps(original, updated=())
	def _activateNVDAObject(self, obj):
		if _enabled:
			try:
				if pressSuggestion(obj):
					return
			except Exception:
				_failure("could not press the suggestion with the mouse, so NVDA activates it as it does")
		return original(self, obj)

	return _mark(_activateNVDAObject, original)


def pressSuggestion(obj) -> bool:
	"""Press ``obj``, when it is a suggestion of the focused field, with the mouse. True once the mouse has pressed it.

	It is what NVDA does for a control it can't activate any other way (``_activateNVDAObject``): the pointer goes to
	the middle of the object, presses and lets go with the primary button, and goes back. The page gets the mouse's
	``mousedown``, ``mouseup`` and ``click``, which the suggestions of visible.com choose by, not the ``click`` alone
	that ``doAction`` sends.
	"""
	suggestion = _suggestionOf(obj)
	if suggestion is None:
		return False
	import mouseHandler
	import winUser

	if suggestion.hasIrrelevantLocation:
		return False
	location = suggestion.location
	if not location.width or not location.height:
		return False
	try:
		text = suggestion.name
	except Exception:
		text = None
	oldX, oldY = winUser.getCursorPos()
	try:
		winUser.setCursorPos(*location.center)
		mouseHandler.doPrimaryClick()
	finally:
		winUser.setCursorPos(oldX, oldY)
	_log().debug(f"jawsMigrator: the suggestion {text!r} was pressed with the mouse")
	_say(text)
	return True


def _say(text) -> None:
	"""NVDA says what was chosen, and that it was: a page chooses without moving the focus, as this one does."""
	try:
		import ui

		text = " ".join(str(text).split()) if text else ""
		if text:
			ui.message(f"{text}, selected")
	except Exception:
		pass


def scriptFor(gesture):
	"""The command to run for Down Arrow alone in the focused field, when it has suggestions to go to. None: NVDA goes on."""
	if not _enabled:
		return None
	try:
		if getattr(gesture, "mainKeyName", None) != LEAVING_KEY or getattr(gesture, "modifiers", None):
			return None
		import api

		field = api.getFocusObject()
		document = getattr(field, "treeInterceptor", None)
		# Only in focus mode, in a document that browse mode has read: browse mode's own Down Arrow does the rest.
		if document is None or not getattr(document, "isReady", False) or not getattr(document, "passThrough", False):
			return None
		if not _suggestingField(field) or not _hasSuggestions(field):
			return None
	except Exception:
		_failure("could not tell whether the field has suggestions to go to, so Down Arrow goes to the page as it does")
		return None
	return _pastTheField


def _hasSuggestions(field) -> bool:
	"""Whether a list the field controls is showing, with something in it."""
	for control in _controls(field):
		if control.hasIrrelevantLocation:
			continue
		if control.firstChild is not None:
			return True
	return False


def _pastTheField(gesture) -> None:
	"""Down Arrow in browse mode, from the end of the field: to what follows it, the field's suggestions.

	Word for word what NVDA's ``BrowseModeDocumentTreeInterceptor.event_caretMovementFailed`` does when a key can't move
	the caret in a field: browse mode's cursor goes to the field's edge, and browse mode's own script for the key runs
	there. The key isn't sent to the page, which would move the focus into its list and close it.
	"""
	try:
		import api
		import scriptHandler
		import textInfos

		document = api.getFocusObject().treeInterceptor
		script = document.getScript(gesture)
		if script is None:
			raise LookupError("browse mode has no script for the key")
		info = document.makeTextInfo(textInfos.POSITION_CARET)
		info.expand(textInfos.UNIT_CONTROLFIELD)
		info.collapse(end=True)
		info.move(textInfos.UNIT_CHARACTER, -1)
		info.updateCaret()
		# Focus mode, which the caret in the field chose again with automatic focus mode for caret movement, would send
		# the next keys to the page; browse mode's cursor is about to be on a suggestion, which is not in the field.
		document.passThrough = False
		scriptHandler.queueScript(script, gesture)
	except Exception:
		_failure("could not go on past the field with Down Arrow, so the key goes to the page as it does")
		gesture.send()
