# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""Get to the suggestions an edit field on a web page offers, go through them, and choose one (issue 47).

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

1.46 to 1.53 tried to keep the focus in the field and take Down Arrow for the suggestions, and never did, for the tester or
for anyone. 1.54 was tried in a second NVDA 2026.2 on its own Windows desktop, with Microsoft Edge 154 on the live page, and
the shipped 1.53 was tried there too. What that showed, in NVDA itself:

- **NVDA looks for the script of a key in the keyboard hook's thread** (the tester's log: ``executeGesture`` on
  ``winInputHook``). NVDA's main thread is an STA, so none of its objects can be read there: the COM call fails with "The
  application called an interface that was marshalled for a different thread", and NVDA catches it and answers "none". 1.53's
  ``getScript`` asked whether the field had a list (``controllerFor``) and its states there, so the answer was always that it had
  none, Down Arrow went to the page, which did the first thing above, and NVDA said the first suggestion as the list closed.
  NVDA's debug log had the COMError the moment Down Arrow was pressed. Windows also gives that hook about 300 milliseconds. So
  the hook's side here (``scriptFor``, ``_wantsDown``) looks at nothing but what is Python's, and everything that reads an NVDA
  object is in the script, which NVDA runs in its main thread;
- **browse mode has one suggestion, not all of them.** NVDA's buffer is made by nvdaHelper's gecko_ia2 backend, which renders
  only the selected item of an interactive list (``renderSelectedItemOnly`` for ``ROLE_SYSTEM_LIST`` without
  ``STATE_SYSTEM_READONLY``): of the twenty suggestions the buffer had the first, before and after NVDA made it again, and the
  line after it was the "Check availability" button. So browse mode's cursor can't go through the suggestions, whatever is done
  about the focus. The objects NVDA has for the list (``list.children``) are all twenty, each with its name, its place ("2 of
  20", IAccessible2's group position) and its place on the screen; making them takes about 200 milliseconds, so it is done once
  for each visit;
- a browser says which list a field controls (``aria-controls``, IAccessible2's controller-for relation) only for a list it
  knew when it described the field. Edge 154 gave it for the address list the first time, and once gave nothing for it after
  the address was cleared and typed again, as the tester did in his log. The page keeps the list in the same container as the
  field, next to it, and that is where the list is looked for when the browser says nothing.

What this module does, for an edit field of a web page of one line that says it has autocomplete and isn't a combo box, and for
those alone:

- NVDA's global plugins are asked about each object as it is made, in the main thread, where its states can be read
  (``chooseOverlay``): such a field gets a class that takes Down Arrow alone. Its script, in the main thread, looks whether
  suggestions are showing. If not, NVDA does with the key what it does without the assistant (``_passOn``: its own script for
  it, or the key to the page), and the log says so once for the field. If they are, Down Arrow says the first suggestion with its
  list and its place ("Address suggestions, list, 241 W PINE ST, ..., 1 of 20");
- from then on Down Arrow and Up Arrow go from one suggestion to the next, Home and End to the first and the last, each said with
  its place. None of these keys reaches the page, whose own Down Arrow would move the focus into the list and close it. The focus
  stays in the field, in the mode it was in; Enter, or Space, presses the suggestion with the mouse, as NVDA does for a control
  without a default action (``BrowseModeTreeInterceptor._activateNVDAObject``): the page scrolls the suggestion into view when
  its list has it out of sight (IAccessible2's ``scrollTo``, which NVDA's ``scrollIntoView`` calls; NVDA reports the new place
  about twelve milliseconds later), the pointer goes to it, presses and lets go, and goes back. The page gets ``mousedown``,
  ``mouseup`` and ``click``, which chooses a suggestion on this page and on one that listens for ``click``. NVDA says the
  suggestion and "selected". The pointer goes to the middle of the part of the suggestion that shows in its list's box and in the
  page (the document's rectangle, less the scrollbars at its right and bottom edges): where all of it shows, its middle. In a
  window so small that the list runs past the page's bottom edge, NVDA doesn't call the row at the edge off screen though its
  middle is outside the page, and 1.54 pressed there; scrolling can't bring such a row in (the address form stays where it is
  when the page scrolls, and neither ``scrollTo`` of any kind nor the page's ``scrollIntoView`` moved anything), so a row that
  shows too little is not pressed and NVDA says so;
- any other key goes to the page as it does, and the visit is over: typing goes on in the field, Escape and Tab do what NVDA does
  with them. These keys, once Down Arrow has begun a visit, are the assistant's from the keyboard hook's side (``scriptFor``),
  which knows nothing but the key and which object has the focus. A key pressed before the first Down Arrow has made the
  objects is the visit's too (it waits in NVDA's queue behind it), for two seconds;
- where browse mode's cursor does come to the one suggestion its buffer has (Escape, then Down Arrow), the focus stays in the
  field and Enter presses it, as in 1.46. Browse mode itself is not changed: Down Arrow goes into the suggestions in focus
  mode, where the tester types;
- once Enter has chosen a suggestion, the page has its address in the field and has shut its list, and it brings suggestions back only
  when the text changes (its input event also makes it forget the choice). So someone who pressed Enter on the wrong one had no way
  back to the list: the tester wrote on 1 October 2026 "if I accidently select the wrong one I can't unselect it", and his log shows
  Up Arrow, Down Arrow, which found no list showing, and Down Arrow again, which left the field (his NVDA has automatic focus mode for
  caret movement on). Control+Z, while the field still holds what the choice put there, puts back the text that was in it when Down
  Arrow began the visit, and the page shows its suggestions for that text again; Down Arrow goes into them as before, waiting up to
  a second and a half for them if the page has not shown them yet. The text is put through the page's accessibility (IAccessible's
  ``accValue``). Measured in NVDA 2026.2 with Edge 154 on a stand-in for the page's picker (tests/live_nvda/pages/address.html, so
  that nothing was typed into the live site): Backspace once brings back a list of the one address chosen; Control+A and the street
  typed again brings back all twenty; the browser's own Control+Z brings back the one address, not the street; ``accValue`` brings back
  all twenty, the page gets a real input event, and NVDA says nothing of the change. A press of Control+Z when the field holds anything
  else goes on as NVDA has it;
- some addresses have units, and then the page does more (its script, read on 1 October 2026: ``selectAddress`` and ``showUnitField``). It
  shows a unit box, ``input#unit-input`` with its own list (``role="listbox"``, "Unit suggestions"), and moves the focus to it with a
  zero-delay timer; the unit box asks for its list when it gets the focus (it shows "Loading..." and then the units and the two fixed
  choices "I can't find my unit" and "I don't live in a unit"), closes it 150 milliseconds after the focus leaves, and a change of the
  address box's text hides the unit box again, which is why the focus then falls to the page. The tester's 1.57 log of 1 October (10:03)
  has it: he chose the eleventh address, GROVE CITY, PA, with Enter ("..., selected"), NVDA said "Enter Unit Label, edit, has auto
  complete, blank", and Control+Z there was not the assistant's, because the focus was no longer in the field the choice was made in. NVDA
  said "Undo", the page's own undo (the browser's) fired the address box's input event with the chosen address, which hid the unit box
  and left a list of three variants of the address, and nothing he tried after that brought back the twenty. So the box the page moves
  the focus to right after a choice is part of the choice: it is the box whose object NVDA made within a few seconds after the choice
  (``_madeAfter``; the field class is stamped with the time as NVDA makes an object, by ``chooseOverlay``, because NVDA gives a field
  object its focus event only in focus mode, and not at all while its buffer is not ready: the field class's ``event_gainFocus`` was tried
  first and was never called in the second NVDA's browse mode). While it holds nothing, Control+Z in it takes the address choice back as
  well. The focus goes back to the address box first (the page hides the unit box when the address changes, and the focus would fall to
  the page), then the text is put back, and Down Arrow goes into the suggestions as before. Down Arrow in the unit box goes into its
  units like any box's. The unit box's list says "Loading..." for a moment after the focus arrives, and the page's list comes back a
  moment after a choice is taken back (300 milliseconds of quiet and its service), so a Down Arrow pressed before the suggestions are
  there waits for them (``_wait``, ``_poll``): one look every 50 milliseconds, from NVDA's own timer, for at most a second and a half, and the
  visit begins at the last of the Down Arrows pressed meanwhile. NVDA's main thread is not held for it. 1.57 held it (a loop that slept
  between looks), and NVDA's watchdog gives up on a core that has not come round for half a second and cancels the COM calls made until
  it does: measured in the second NVDA, a loop of looks at the unit list had them fail with "COM call cancelled" on and off from a second
  in, and NVDA's call for a node of the list that the page had just replaced ("Loading..." for the units) raised as well, so a look that
  fails is a look to make again (``_tryList``). If no list comes in time NVDA says "No suggestions yet" and the focus stays: NVDA's own
  Down Arrow in the box walks into the buffer's "Loading..." and leaves the field (measured). A unit chosen with Enter is a choice too:
  Control+Z puts back the empty box and the page shows all the units again (the page asks its service for the units that go with the text in
  the box when the focus comes back to a box that holds one). Where a box held nothing when the visit began (NVDA's ``value`` is None for nothing,
  for only spaces and for an error alike, so it is asked again through IAccessible, which raises on an error), that is what is put back.

A field that is a combo box (its own role, or expanded or collapsed) does as it did: its page handles its keys. It works
while the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import functools
import threading
import time
from collections import namedtuple

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "chooseWebSuggestions"
#: Marks the assistant's own version of NVDA's method, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorSuggestionLists"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: Keeps NVDA's own method on the assistant's.
ORIGINAL = "_jawsMigratorSuggestionListsOriginal"
#: The key that goes into the suggestions, and on to the next one.
DOWN_KEY = "downArrow"
#: How far up from an object the list is looked for (an option, and what an option has in it).
_MOST_LEVELS = 8
#: How many levels down from a list its options are looked for (an option may hold its text in other elements).
_MOST_OPTION_LEVELS = 3
#: How many containers, from the field up, the list that follows it is looked for in, and how many objects after each.
_MOST_CONTAINERS = 3
_MOST_FOLLOWERS = 3
#: How far, in pixels of the screen, a list may be from the field to be the field's: it follows the field closely.
_NEAR = 60
#: How long, in seconds, the keys that follow Down Arrow at once are taken for the suggestions, before its script has begun
#: the visit.
_PENDING_SECONDS = 2.0
#: How many pixels of a suggestion must show, high and wide, for the mouse to press it there.
_LEAST_SHOWING = 6
#: How thick, in pixels, the browser's scrollbars are taken to be where Windows doesn't say (see _scrollbarSize).
_SCROLLBAR = 20
#: How long, in seconds, a suggestion the page scrolls into view is waited for, and the pause between looks: the page took
#: about twelve milliseconds to tell NVDA where the suggestion was (Edge 154, NVDA 2026.2).
_SCROLL_WAIT = 0.4
_SCROLL_STEP = 0.01
#: The key, with Control, that takes back a choice (see _undoChoice).
UNDO_KEY = "z"
#: How long, in seconds, the page is given to put a chosen suggestion, or the text typed before, in the field, and the pause between
#: looks: the page changes the field when it has the mouse press, NVDA reads it a little later.
_TEXT_WAIT = 0.3
_TEXT_STEP = 0.01
#: How long, in seconds, Down Arrow waits for the page's suggestions after a choice was taken back (visible.com asks for them 300 ms
#: after the last change, and its service answers), and the pause between looks. Shorter than _PENDING_SECONDS: the keys pressed
#: meanwhile are the visit's for that long only. NVDA's main thread is not held for it: its watchdog gives up on a core that has not
#: come round for half a second and cancels the COM calls made until it does (measured: "COM call cancelled" from a second into a loop
#: that slept between looks), so the page's list is looked at again by NVDA's own timer (see _wait).
_RETURN_WAIT = 1.5
_RETURN_STEP = 0.05
#: How long, in seconds, after a choice was taken back, or after the page moved the focus to a box following a choice, Down Arrow waits
#: for the suggestions at all.
_RETURN_WINDOW = 5.0
#: How long, in seconds, after a choice the page may move the focus to its next box (visible.com shows a unit box for an address that has
#: units, and focuses it with a zero-delay timer) for that box to be the one Control+Z takes the choice back in: NVDA makes the box's
#: object when the focus arrives, a moment after the page's change, and this is the time that moment is given.
_FOLLOW_SECONDS = 3.0
#: What the assistant stamps on the objects of the fields it gives its class: when NVDA made them (time.monotonic).
MADE_AT = "_jawsMigratorMadeAt"
#: What NVDA says when Down Arrow waited _RETURN_WAIT seconds for a list the page was to show, and it didn't.
NO_SUGGESTIONS_YET = "No suggestions yet"
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: The suggestion browse mode was last kept from, so the log says so once for each.
_noted = None
#: Where the user is in the suggestions of a field: the field, and which suggestion was said last (see _Session).
_session = None
#: Why Down Arrow was last left to NVDA in a field with suggestions, so the log says so once for each.
_declined = None
#: The field Down Arrow was last taken in, and until when (time.monotonic) keys that follow at once are taken too, before the
#: script of Down Arrow has begun the visit (see scriptFor).
_pending = None
#: The suggestion the assistant pressed last, while the field holds what that put there (see _Choice, _undoChoice).
_chosen = None
#: The field whose choice was taken back, and until when (time.monotonic) Down Arrow waits for the page's suggestions to come back.
_returning = None
#: Down Arrow while it waits for the page's list to be shown: see _Waiting.
_waiting = None
#: True while the assistant asks NVDA what it does with a key without the assistant's commands (see _passOn).
_passing = False
#: The class given to edit fields with suggestions (see _overlayClass).
_overlay = None
#: The names of the fields that were given the class, so the log says so once for each.
_noticed: set = set()


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
	global _enabled, _noted, _session, _declined, _pending, _chosen, _returning, _waiting
	_enabled = False
	_noted = None
	_session = None
	_declined = None
	_pending = None
	_chosen = None
	_returning = None
	_waiting = None
	_noticed.clear()
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


def _optionsOf(box) -> list:
	"""The suggestions in a list: the objects with a list item's role in it, shown, in the order of the page.

	NVDA's buffer has only the selected one of an interactive list's items; the objects of the list, which this reads, have
	them all, those scrolled out of the list's box too.
	"""
	from controlTypes import Role, State

	found = []

	def walk(parent, depth):
		for child in parent.children or ():
			if child is None:
				continue
			if child.role == Role.LISTITEM:
				found.append(child)
			elif depth < _MOST_OPTION_LEVELS:
				walk(child, depth + 1)

	walk(box, 1)
	return [option for option in found if State.INVISIBLE not in option.states]


def _isListNextTo(field, candidate) -> bool:
	"""Whether ``candidate`` is a list the page shows next to ``field``: right below it or right above it, as wide as it is."""
	from controlTypes import Role, State

	if candidate.role != Role.LIST:
		return False
	if State.INVISIBLE in candidate.states or State.OFFSCREEN in candidate.states:
		return False
	box, edit = candidate.location, field.location
	if not box or not edit or not box.width or not box.height or not edit.width or not edit.height:
		return False
	below = edit.top + edit.height - _NEAR <= box.top <= edit.top + edit.height + _NEAR
	above = edit.top - _NEAR <= box.top + box.height <= edit.top + _NEAR
	across = box.left < edit.left + edit.width and edit.left < box.left + box.width
	return across and (below or above)


def _listFollowing(field):
	"""The list the page shows next to ``field``, after it in its container; None when there is none.

	A browser says what a field controls (aria-controls) for a list it knew when it described the field. Edge 154 described the
	address field again when its text changed, but not when the page showed its list: after the address was cleared and typed
	again, with the list showing, ``controllerFor`` was empty (NVDA 2026.2, measured up to two seconds later). The page puts the
	list next to the field, in the same container, so it is found there, if a list is right below the field or right above it.
	"""
	node = field
	for _ in range(_MOST_CONTAINERS):
		follower = node.next
		for _ in range(_MOST_FOLLOWERS):
			if follower is None:
				break
			if _isListNextTo(field, follower):
				return follower
			follower = follower.next
		node = node.parent
		if node is None:
			break
	return None


def _suggestionList(field):
	"""The list that holds the suggestions of ``field`` and its suggestions: (None, []) when none are showing.

	The list the field controls, or, where the browser doesn't say, the list that follows the field (see _listFollowing).
	"""
	for box in _controls(field):
		if box.hasIrrelevantLocation:
			continue
		options = _optionsOf(box)
		if options:
			return box, options
	box = _listFollowing(field)
	if box is not None:
		options = _optionsOf(box)
		if options:
			return box, options
	return None, []


def _tryList(field):
	"""The field's list and its suggestions as ``_suggestionList`` has them; (None, []) when NVDA can't read them just now.

	A page may replace the nodes of a list while NVDA makes their objects (visible.com's unit list says "Loading..." and then puts the
	units in its place: NVDA's COM call for a node that has just gone raises), so a read that fails is a list that is not there yet.
	"""
	try:
		return _suggestionList(field)
	except Exception:
		_failure("could not read the field's list, which the page may be changing, so it is looked at again if it is waited for")
		return None, []


def _showing(field):
	"""The list ``field`` has showing, found as cheaply as can be; None when there is none.

	NVDA looks for the script of a key in the keyboard hook (``scriptHandler.findScript``, from ``internal_keyDownEvent``),
	which Windows gives about 300 milliseconds before it stops calling it, and the objects of a list of twenty suggestions took
	about 200 to make (Edge 154, NVDA 2026.2). So the decision about a key looks at the list and how many children it has, which
	NVDA reads without making them; the script, which runs afterwards, makes them (see _suggestionList).
	"""
	for box in _controls(field):
		if not box.hasIrrelevantLocation and _childCount(box):
			return box
	box = _listFollowing(field)
	if box is not None and _childCount(box):
		return box
	return None


def _suggestionAndList(obj):
	"""The suggestion ``obj`` is, or is in, and the list it is in, for the focused edit field's list. (None, None) for anything else."""
	import api

	if obj is None:
		return None, None
	field = api.getFocusObject()
	if field is None or _same(obj, field) or not _suggestingField(field):
		return None, None
	lists = _controls(field)
	if not lists:
		following = _listFollowing(field)
		lists = [following] if following is not None else []
	if not lists:
		return None, None
	child = obj
	for _ in range(_MOST_LEVELS):
		parent = child.parent
		if parent is None:
			return None, None
		for suggestions in lists:
			if _same(parent, suggestions):
				return child, suggestions
		child = parent
	return None, None


def _suggestionOf(obj):
	"""The suggestion ``obj`` is, or is in, in the list the focused edit field controls. None for anything else."""
	return _suggestionAndList(obj)[0]


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


def _nameOf(obj) -> str:
	"""An object's name as one line of words, or an empty line."""
	try:
		return " ".join(str(obj.name or "").split())
	except Exception:
		return ""


def pressSuggestion(obj) -> bool:
	"""Press ``obj``, when it is a suggestion of the focused field, with the mouse. True once the mouse has pressed it."""
	suggestion, box = _suggestionAndList(obj)
	if suggestion is None:
		return False
	import api

	return _press(suggestion, box, _pageOf(api.getFocusObject()))


#: A rectangle on the screen, as NVDA's locations are.
_Area = namedtuple("_Area", "left top width height")


def _scrollbarSize() -> int:
	"""How thick a scrollbar is on this screen, in pixels, as Windows has it (more on a screen that is scaled up)."""
	try:
		import ctypes

		user32 = ctypes.windll.user32
		return max(user32.GetSystemMetrics(2), user32.GetSystemMetrics(3)) or _SCROLLBAR
	except Exception:
		return _SCROLLBAR


def _pageOf(field):
	"""Where the page shows on the screen, or None where NVDA can't say.

	It is the rectangle of the document NVDA's buffer is of, less what the browser's scrollbars may take at its right and
	bottom edges: they are inside that rectangle (measured in Edge 154: the document was 383 pixels high and its page 15 CSS
	pixels less, with a horizontal scrollbar), and a press on a scrollbar chooses nothing.
	"""
	try:
		area = field.treeInterceptor.rootNVDAObject.location
		if area and area.width and area.height:
			room = _scrollbarSize()
			return _Area(area.left, area.top, max(area.width - room, 1), max(area.height - room, 1))
	except Exception:
		pass
	return None


def _part(rectangle, area):
	"""The part of ``rectangle`` that is in ``area``, as (left, top, right, bottom); an area that is not known holds all of it."""
	left, top, right, bottom = rectangle
	if area and area.width and area.height:
		left, top = max(left, area.left), max(top, area.top)
		right, bottom = min(right, area.left + area.width), min(bottom, area.top + area.height)
	return left, top, right, bottom


def _pressPoint(option, box, page=None):
	"""Where the mouse can press ``option``: the middle of the part of it that shows in its list's box and the page. None when none does.

	A press on any part of a suggestion chooses it. NVDA calls a suggestion off screen only when all of it is, and the one at the
	bottom edge of a small window has its top in the page and its middle outside it (measured: the page ended at 526 and the
	middle was at 527, the suggestion not off screen): pressed at its middle, the mouse is outside the page. Where all of
	it shows this is its middle, as it was.
	"""
	if option.hasIrrelevantLocation:
		return None
	location = option.location
	if not location.width or not location.height:
		return None
	rectangle = (location.left, location.top, location.left + location.width, location.top + location.height)
	for area in (box.location if box is not None else None, page):
		rectangle = _part(rectangle, area)
	left, top, right, bottom = rectangle
	if right - left < _LEAST_SHOWING or bottom - top < _LEAST_SHOWING:
		return None
	return (left + right) // 2, (top + bottom) // 2


def _forget(obj) -> None:
	"""Have NVDA read an object's place again: it keeps what it read of an object until the next key."""
	try:
		obj.invalidateCache()
	except Exception:
		pass


def _scrollInto(option, box, page=None):
	"""Have the page scroll ``option`` into its list's box, and wait for NVDA to see it there. Where to press it, or None.

	Scrolling brings a suggestion that is out of its list's box into it. It does not bring one into the page that the page's edge
	hides and the list's box does not: the list is in a part of the page that stays where it is, and neither IAccessible2's
	scrollTo nor the page's own scrollIntoView moves anything then (measured, in Edge 154).
	"""
	try:
		option.scrollIntoView()
	except Exception:
		return None
	deadline = time.monotonic() + _SCROLL_WAIT
	while True:
		_forget(option)
		point = _pressPoint(option, box, page)
		if point is not None:
			return point
		if time.monotonic() >= deadline:
			return None
		time.sleep(_SCROLL_STEP)


def _press(option, box=None, page=None) -> bool:
	"""Press ``option`` with the mouse. True once the mouse has pressed it.

	It is what NVDA does for a control it can't activate any other way (``_activateNVDAObject``): the pointer goes to the
	object, presses and lets go with the primary button, and goes back. The page gets the mouse's ``mousedown``, ``mouseup`` and
	``click``, which the suggestions of visible.com choose by, not the ``click`` alone that ``doAction`` sends. The pointer goes
	to the middle of the part of the suggestion that shows in its list's box and in the page (``page``): one out of its list's box,
	as all but the first seven of visible.com's twenty are, is scrolled into view first (IAccessible2's scrollTo, which NVDA's
	``scrollIntoView`` calls), as it is for NVDA's own cursor. If no part of it shows, nothing is pressed.
	"""
	import mouseHandler
	import winUser

	text = _nameOf(option)
	point = _pressPoint(option, box, page)
	scrolled = point is None
	if scrolled:
		point = _scrollInto(option, box, page)
	if point is None:
		_log().debug(f"jawsMigrator: no part of the suggestion {text!r} shows in the list's box and the page on the screen, so the mouse didn't press it")
		return False
	oldX, oldY = winUser.getCursorPos()
	try:
		winUser.setCursorPos(*point)
		mouseHandler.doPrimaryClick()
	finally:
		winUser.setCursorPos(oldX, oldY)
	_log().debug(
		f"jawsMigrator: the suggestion {text!r} was pressed with the mouse"
		+ (", after the page scrolled it into view" if scrolled else "")
	)
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


class _Session:
	"""Where the user is in the suggestions of one field: its list and the suggestions in it, and the one said last.

	NVDA takes about two hundred milliseconds to make the objects of a list of twenty suggestions (Edge 154, NVDA 2026.2), so
	they are made once for a visit and used again for each key, as long as the list is the same.
	"""

	def __init__(self, field, box, options: list, index: int, typed=None):
		self.field, self.box, self.options, self.index = field, box, list(options), index
		#: What the field held when the visit began, which is what the user typed (see _undoChoice).
		self.typed = typed
		self.name = _nameOf(self.options[index])
		self.count = _childCount(box)

	def holds(self) -> bool:
		"""Whether the list is still the one these suggestions are of: as many items in it, and the one said last is named so."""
		count = _childCount(self.box)
		return count is not None and count == self.count and bool(self.name) and _nameOf(self.options[self.index]) == self.name


def _childCount(box):
	"""How many children a list has, which NVDA reads without making them; None where it can't be read."""
	try:
		return int(box.childCount)
	except Exception:
		return None


def _endSession(why: str) -> None:
	"""The visit to the suggestions is over: the keys go to the page again."""
	global _session, _pending, _waiting
	_pending = None
	_waiting = None
	if _session is not None:
		_session = None
		_log().debug(f"jawsMigrator: the visit to the field's suggestions is over: {why}")


def _visit(field):
	"""The visit to the suggestions of ``field`` that is going on, or None."""
	session = _session
	if session is not None and _same(field, session.field) and session.holds():
		return session
	return None


#: What a choice replaced: the field, the text it held when the visit began (what the user typed; "" for a field that held nothing),
#: the suggestion the choice put there (the page puts its text in the field), and when it was made (time.monotonic).
_Choice = namedtuple("_Choice", "field typed text at")


def _textOf(field):
	"""What an edit field holds, as NVDA reads it from the page; None where it can't be read, and where it holds nothing (see _readText)."""
	try:
		value = field.value
	except Exception:
		return None
	return None if value is None else str(value)


def _readText(field):
	"""What an edit field holds; "" when it holds nothing, which is told from a field that can't be read; None where it can't be read.

	NVDA's ``value`` is None for a field that holds nothing, or only spaces, and for an error alike (``IAccessible._get_value`` keeps
	the COM error to itself), so the field is asked again through IAccessible, which raises on an error.
	"""
	text = _textOf(field)
	if text is not None:
		return text
	try:
		value = field.IAccessibleObject.accValue[field.IAccessibleChildID]
	except Exception:
		return None
	return "" if value is None or not str(value).strip() else str(value)


def _normal(text):
	"""Text as one line of words, to tell whether two texts are the same; "" for nothing."""
	return " ".join(str(text or "").split())


def _waitForText(field, test):
	"""Whether the field's text is such that ``test`` is true of it, looking again for a moment: the page changes it a little after the press
	or the change that was made, and NVDA reads it a little later."""
	deadline = time.monotonic() + _TEXT_WAIT
	while True:
		_forget(field)
		text = _readText(field)
		if text is not None and test(text):
			return True
		if time.monotonic() >= deadline:
			return False
		time.sleep(_TEXT_STEP)


def _putText(field, text) -> bool:
	"""Make the field hold ``text`` through the page's accessibility, as if it were typed: Edge gives the page its input event (measured).

	True once the field says it holds the text.
	"""
	try:
		field.IAccessibleObject.accValue[field.IAccessibleChildID] = text
	except Exception:
		return False
	return _waitForText(field, lambda now: _normal(now) == _normal(text))


def _rememberChoice(field, typed, text) -> None:
	"""Note what the choice that was just made replaced in the field, so that Control+Z can put it back (see _undoChoice).

	``text`` is the suggestion that was pressed: the page puts it in the field a moment later (the press is the mouse's, and the page
	answers it in its own time), so it is not waited for here. Control+Z looks whether the field holds it, and does nothing if not.
	``typed`` is what the field held, "" for a field that held nothing (the unit box, whose list the page shows when it gets the focus),
	and None where that could not be read: then there is nothing to put back. It never raises: the choice has been made, and the key
	that made it must not go on to the page.
	"""
	global _chosen
	_chosen = None
	try:
		if typed is None or not text or not text.strip():
			return
		_chosen = _Choice(field, typed, text, time.monotonic())
		_log().debug(f"jawsMigrator: the suggestion {text!r} was chosen, and Control+Z puts back {typed!r}")
	except Exception:
		_failure("could not note what the choice replaced, so Control+Z doesn't take it back")


def _madeAfter(field, chosen) -> bool:
	"""Whether ``field`` is the box the page moved the focus to right after the choice: NVDA made its object within a few seconds after it.

	visible.com shows a unit box for an address that has units and focuses it at once, so the key that follows the choice is pressed
	there, not in the field the choice was made in (the tester's 1.57 log). The box is the page's next step of the same choice. NVDA makes
	an object for a field when the focus comes to it, and the assistant stamps the time on it when it gives it its class (MADE_AT).
	"""
	made = getattr(field, MADE_AT, None)
	return made is not None and chosen.at <= made <= chosen.at + _FOLLOW_SECONDS and not _same(field, chosen.field)


def _isUndoKey(gesture) -> bool:
	"""Whether the key is Control+Z alone. Python only (see scriptFor)."""
	if getattr(gesture, "mainKeyName", None) != UNDO_KEY or getattr(gesture, "isModifier", False):
		return False
	try:
		return [str(name).lower() for name in gesture.modifierNames] == ["control"]
	except Exception:
		return False


def _giveFocusTo(field) -> None:
	"""Have the page focus ``field``: IAccessible's accSelect with the take-focus flag, which is what NVDA's setFocus does."""
	try:
		field.setFocus()
	except Exception:
		_failure("could not give the focus back to the field the choice was made in")


def _undoChoice(gesture):
	# Control+Z while the field holds what a choice put there, in that field or in the box the page moved the focus to after the choice
	# (and nothing is typed in it): the text typed before is put back, and the page shows its suggestions for it again. In any other case
	# the key goes on as NVDA has it. No description, as NVDA's scripts that may send a key on have none.
	global _chosen, _returning
	chosen = _chosen
	try:
		import api
		import ui

		focus = api.getFocusObject()
		if chosen is not None:
			field = chosen.field
			here = _same(focus, field)
			beside = not here and _madeAfter(focus, chosen)
			box = _nameOf(focus) if beside else ""  # the page hides it when the address changes: its name is gone by then
			if beside and _readText(focus) != "":
				_log().debug("jawsMigrator: Control+Z goes on as NVDA has it: something is typed in the box the page moved the focus to")
				_passOn(gesture)
				return
			if here or beside:
				_chosen = None
				_endSession("the choice was taken back")
				_forget(field)
				if _normal(_textOf(field)) == _normal(chosen.text):
					if beside:
						# The page hides the box that has the focus when the field's text changes, and the focus would fall to the page.
						_giveFocusTo(field)
					if _putText(field, chosen.typed):
						_returning = (field, time.monotonic() + _RETURN_WINDOW)
						ui.message(f"Choice undone, {chosen.typed}" if chosen.typed.strip() else "Choice undone")
						_log().debug(
							f"jawsMigrator: Control+Z took the choice back: the field holds {chosen.typed!r} again"
							+ (f" and has the focus, which the page had moved to {box!r}" if beside else "")
						)
					else:
						ui.message("Can't put back what you typed")
						_log().debug(f"jawsMigrator: Control+Z could not put {chosen.typed!r} back in the field")
					return
				_log().debug("jawsMigrator: Control+Z goes on as NVDA has it: the field no longer holds what the choice put there")
				_passOn(gesture)
				return
		_log().debug("jawsMigrator: Control+Z goes on as NVDA has it: nothing was chosen, or the focus is not where the choice was made")
		_passOn(gesture)
	except Exception:
		_chosen = None
		_failure("could not take the choice back, so the key goes on as NVDA has it")
		_passOn(gesture)


def _expectsList(field) -> bool:
	"""Whether the page is likely to show a list for ``field`` a moment from now: a choice was taken back in it a short while ago, or it is
	the box the page moved the focus to after a choice (the page asks for its list when the box gets the focus)."""
	now = time.monotonic()
	returning = _returning
	if returning is not None and now <= returning[1] and _same(returning[0], field):
		return True
	chosen = _chosen
	return chosen is not None and now <= chosen.at + _RETURN_WINDOW and _madeAfter(field, chosen)


class _Waiting:
	"""Down Arrow, while the page is still to show its list: the field, when the wait began and ends (time.monotonic), the key (it goes on
	as NVDA has it if a look fails) and how many Down Arrows were pressed meanwhile (the visit begins at the last of them)."""

	def __init__(self, field, gesture):
		self.field, self.gesture = field, gesture
		self.since = time.monotonic()
		self.until = self.since + _RETURN_WAIT
		self.presses = 1


def _wait(field, gesture) -> None:
	"""Down Arrow is for the page's list, which it is about to show (see _expectsList): look again in a moment, and begin the visit then.

	NVDA's own timer calls ``_poll`` in its main thread between its other work: the thread is not held (see _RETURN_WAIT). Keys pressed
	meanwhile are the visit's (see scriptFor): Down Arrow counts, any other key ends the wait and goes to the page.
	"""
	global _waiting
	_waiting = _Waiting(field, gesture)
	_later()


def _later() -> None:
	import core

	core.callLater(int(_RETURN_STEP * 1000), _poll)


def _poll() -> None:
	"""A look at the list that Down Arrow waits for: the visit begins when it is there; when it is not within _RETURN_WAIT NVDA says
	NO_SUGGESTIONS_YET (the wait ends at once if the focus moved or another key was pressed, and the key goes on as NVDA has it only if
	the look itself fails)."""
	global _waiting
	waiting = _waiting
	if waiting is None:
		return
	try:
		import api

		field = api.getFocusObject()
		if not _same(field, waiting.field):
			_waiting = None
			return
		_forget(field)
		box, options = _tryList(field) if _showing(field) is not None else (None, [])
		if options:
			_waiting = None
			_log().debug(f"jawsMigrator: the page's suggestions were back {time.monotonic() - waiting.since:.2f} seconds after Down Arrow")
			_beginVisit(field, box, options, min(waiting.presses, len(options)) - 1)
			return
		if time.monotonic() < waiting.until:
			_later()
			return
		_waiting = None
		_log().debug(f"jawsMigrator: the page's suggestions were not back {_RETURN_WAIT} seconds after Down Arrow")
		_endSession("no suggestions are showing")
		# Not the key as NVDA has it: in the field NVDA's own Down Arrow walks into the buffer's "Loading..." and leaves it (measured), and
		# the user is told where they are instead.
		import ui

		ui.message(NO_SUGGESTIONS_YET)
	except Exception:
		_waiting = None
		_endSession("the list could not be looked at")
		_failure("could not look at the list that Down Arrow waited for, so the key goes on as NVDA has it")
		try:
			_passOn(waiting.gesture)
		except Exception:
			pass


def _beginVisit(field, box, options, index: int = 0) -> None:
	"""The visit to ``field``'s suggestions begins at ``index``: it is said, with the list and its place."""
	global _session, _pending, _chosen, _returning
	_pending = None
	# What the field holds as the visit begins is what the user typed: Control+Z puts it back after a choice.
	typed = _readText(field)
	chosen = _chosen
	if chosen is None or _same(field, chosen.field) or not _madeAfter(field, chosen):
		# A visit in the box the page moved the focus to keeps the choice, which Control+Z there takes back; any other forgets it.
		_chosen = None
	_returning = None
	_session = _Session(field, box, options, index, typed)
	_announce(box, options, index, first=True)


def _placeOf(option, index: int, count: int):
	"""A suggestion's place in its list as the page says it (IAccessible2's group position), or as it was counted."""
	try:
		info = option.positionInfo
		position, total = int(info.get("indexInGroup") or 0), int(info.get("similarItemsInGroup") or 0)
		if 0 < position <= total:
			return position, total
	except Exception:
		pass
	return index + 1, count


def _announce(box, options, index: int, first: bool) -> None:
	"""NVDA says the suggestion, with its place in the list, and the list itself the first time."""
	import ui

	option = options[index]
	position, total = _placeOf(option, index, len(options))
	text = f"{_nameOf(option)}, {position} of {total}"
	if first:
		label = _nameOf(box)
		text = f"{label}, list, {text}" if label else f"list, {text}"
	ui.message(text)
	_log().debug(f"jawsMigrator: suggestion {position} of {total} of the field's list said: {text!r}")


def _passOn(gesture) -> None:
	"""Do with the key what NVDA does without the assistant's commands: run the script it has for it, or send the key on.

	It is for a key the assistant took before it knew it was not for the suggestions, which only its script, in NVDA's main
	thread, can know (see chooseOverlay).
	"""
	global _passing
	script = None
	_passing = True
	try:
		import scriptHandler

		script = scriptHandler.findScript(gesture)
	except Exception:
		_failure("could not find what NVDA does with a key the assistant took, so the key goes to the page")
	finally:
		_passing = False
	if script is None:
		gesture.send()
	else:
		script(gesture)


def _go(gesture, target, enter: bool = False) -> None:
	"""Go to a suggestion of the focused field, say it and remember it; the key goes on as NVDA has it when that can't be done.

	``target`` is given where the user is in the list (None before the first suggestion) and how many there are, and gives
	the number of the suggestion to go to, which is kept inside the list. Only a key that ``enter`` the suggestions, Down
	Arrow, begins a visit.
	"""
	global _session, _pending, _waiting
	try:
		import api

		field = api.getFocusObject()
		session = _visit(field)
		if session is not None:
			index = max(0, min(len(session.options) - 1, target(session.index, len(session.options))))
			_session = _Session(field, session.box, session.options, index, session.typed)
			_announce(session.box, session.options, index, first=False)
			return
		if not enter:
			_endSession("the key came with no visit going on")
			_passOn(gesture)
			return
		waiting = _waiting
		if waiting is not None and _same(field, waiting.field):
			# Down Arrow again while the first waits for the page's list: the visit will begin at the last of them.
			waiting.presses += 1
			return
		shown = _showing(field) is not None
		box, options = _tryList(field) if shown else (None, [])
		if options:
			_beginVisit(field, box, options)
			return
		if _expectsList(field):
			# After a choice was taken back, or where the page moved the focus to this box after one, the page shows its suggestions a
			# moment later, its list saying "Loading..." first: the key waits for them (see _wait).
			_wait(field, gesture)
			return
		if shown or _showing(field) is not None:
			_endSession("the list has no suggestions")
		else:
			_decline(field, "no suggestions are showing for it")
			_endSession("no suggestions are showing")
		_passOn(gesture)
	except Exception:
		_session = None
		_pending = None
		_waiting = None
		_failure("could not go through the field's suggestions, so the key goes on as NVDA has it")
		_passOn(gesture)


# The commands. They have no description, as NVDA's scripts that may send the key on have none: NVDA then keeps the keys
# pressed after them in order (scriptHandler._isInterceptedCommandScript).


def _down(gesture):
	# Down Arrow: the first suggestion of the focused field, or the next one.
	_go(gesture, lambda here, count: 0 if here is None else here + 1, enter=True)


def _up(gesture):
	# Up Arrow: the previous suggestion; the first, where the user is on it.
	_go(gesture, lambda here, count: 0 if here is None else here - 1)


def _first(gesture):
	# Home: the first suggestion.
	_go(gesture, lambda here, count: 0)


def _last(gesture):
	# End: the last suggestion.
	_go(gesture, lambda here, count: count - 1)


def _choose(gesture):
	# Enter or Space: the suggestion the user is on is pressed with the mouse.
	global _session, _pending
	try:
		import api
		import ui

		field = api.getFocusObject()
		session = _visit(field)
		if session is None:
			_endSession("the key came with no visit going on")
			_passOn(gesture)
			return
		option = session.options[session.index]
		if _press(option, session.box, _pageOf(field)):
			_endSession("the suggestion was chosen")
			_rememberChoice(field, session.typed, _nameOf(option))
		else:
			ui.message("Can't press this suggestion, it is not on the screen. Make the window bigger or the page smaller.")
	except Exception:
		_session = None
		_pending = None
		_failure("could not choose the suggestion, so the key goes on as NVDA has it")
		_passOn(gesture)


#: The keys that go through the suggestions of a field once Down Arrow has gone into them, and what each does.
_COMMANDS = {
	"downArrow": _down,
	"upArrow": _up,
	"home": _first,
	"end": _last,
	"enter": _choose,
	"numpadEnter": _choose,
	"space": _choose,
}


def _decline(field, why: str) -> None:
	"""Down Arrow in an edit field with suggestions is left to NVDA: said once in NVDA's log, with why."""
	global _declined
	if _declined is not None and _declined[1] == why and _declined[0] is field:
		return
	_declined = (field, why)
	_log().debug(f"jawsMigrator: Down Arrow in the edit field {_nameOf(field)!r}, which says it has suggestions, goes on as NVDA has it: {why}")


def _undoScriptFor(gesture):
	"""Control+Z is the assistant's after it chose a suggestion, while an edit field with suggestions has the focus: the field it chose in,
	or the box the page moved the focus to after the choice. Python only (see scriptFor): which of them it is, and what it holds, is
	for the script to find out, in the main thread. NVDA makes a new object each time the focus comes to a field, so the field is
	known by its class, which the assistant gave it."""
	chosen, overlay = _chosen, _overlay
	if chosen is None or overlay is None or not _isUndoKey(gesture):
		return None
	try:
		import api

		return _undoChoice if isinstance(api.getFocusObject(), overlay) else None
	except Exception:
		return None


def scriptFor(gesture):
	"""The command to run for this key when a visit to the suggestions of the focused edit field is going on. None: NVDA goes on.

	NVDA asks for the script of a key in its keyboard hook's thread, where no object of NVDA's can be read (they are made for
	the main thread, and NVDA says "The application called an interface that was marshalled for a different thread."), and
	where Windows gives about 300 milliseconds. So this looks at nothing but what is Python's: the key, and which object has the
	focus. Once Down Arrow has gone into the suggestions (see chooseOverlay), Down Arrow, Up Arrow, Home, End, Enter and Space go
	through them and choose one, until another key is pressed (it goes to the page as it does: typing, Escape to close the list,
	Tab to leave the field) or the focus moves. Where no visit is going on, Control+Z is the assistant's too, after it chose a
	suggestion, while an edit field with suggestions has the focus (see _undoScriptFor); whether it is the field the choice was made in
	or the box the page moved the focus to, and whether the field still holds that suggestion, is for the script to find out, in the
	main thread.
	"""
	if not _enabled or _passing:
		return None
	session, pending = _session, _pending
	if session is None and (pending is None or time.monotonic() > pending[1]):
		return _undoScriptFor(gesture)
	try:
		if getattr(gesture, "isModifier", False) or getattr(gesture, "modifiers", None):
			# Control+Z in the middle of a visit to the units of the box the page moved the focus to is still the choice's to take back.
			return _undoScriptFor(gesture)
		import api

		field = api.getFocusObject()
		if field is not (session.field if session is not None else pending[0]):
			_endSession("the focus moved")
			return None
		key = getattr(gesture, "mainKeyName", None)
		if key in _COMMANDS:
			return _COMMANDS[key]
		_endSession(f"{key} was pressed")
		return None
	except Exception:
		_failure("could not tell whether the key is for the field's suggestions, so it goes on as NVDA has it")
		return None


def _wantsDown(gesture) -> bool:
	"""Whether the key is Down Arrow alone, which a field with suggestions may take. Python only (see scriptFor)."""
	if not _enabled or _passing:
		return False
	if getattr(gesture, "mainKeyName", None) != DOWN_KEY:
		return False
	return not getattr(gesture, "isModifier", False) and not getattr(gesture, "modifiers", None)


def _overlayClass():
	"""The class that gives an edit field with suggestions its Down Arrow, made once when it is first needed."""
	global _overlay
	if _overlay is None:
		from NVDAObjects import NVDAObject

		class SuggestingField(NVDAObject):
			"""An edit field of a web page that says it has suggestions: Down Arrow in it may be the key into them."""

			def getScript(self, gesture):
				# Python only: NVDA asks in the keyboard hook's thread (see scriptFor). Whether suggestions are showing is the
				# script's to find out, in the main thread, and it passes the key on when they aren't.
				global _pending
				if _wantsDown(gesture):
					_pending = (self, time.monotonic() + _PENDING_SECONDS)
					return self.script_suggestionsDown
				return super().getScript(gesture)

			def script_suggestionsDown(self, gesture):
				# No description, as NVDA's scripts that may send a key on have none (see _down).
				_down(gesture)

		_overlay = SuggestingField
	return _overlay


def chooseOverlay(obj, clsList) -> None:
	"""Have an edit field of a web page that says it has suggestions take Down Arrow, to go into them, from NVDA's classes.

	NVDA's global plugins are asked about each object as it is made, in the main thread, where its states can be read. The
	field is one of one line, with autocomplete, that isn't a combo box (see _suggestingField); the class is only for web pages
	(IAccessible2), where NVDA's buffer has one of the suggestions (see the top of this file).
	"""
	if not _enabled:
		return
	try:
		from NVDAObjects.IAccessible.ia2Web import Ia2Web

		if not any(isinstance(cls, type) and issubclass(cls, Ia2Web) for cls in clsList):
			return
		from controlTypes import Role

		if obj.role == Role.EDITABLETEXT and _suggestingField(obj):
			clsList.insert(0, _overlayClass())
			try:
				setattr(obj, MADE_AT, time.monotonic())
			except Exception:
				pass
			name = _nameOf(obj)
			if name not in _noticed:
				_noticed.add(name)
				_log().debug(f"jawsMigrator: the edit field {name!r} says it has suggestions, so Down Arrow in it can go into them")
	except Exception:
		_failure("could not tell whether an edit field has suggestions, so NVDA does as it does with its keys")
