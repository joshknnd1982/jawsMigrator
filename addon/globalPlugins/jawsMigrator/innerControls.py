# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""Space and Enter in browse mode check a web page's check box whose real check box is inside it.

A tester could not add toppings in pizzahut.com's pizza builder (issue 51): X went to "Pepperoni
checkbox, unchecked, check box, not checked", and Space did nothing. Each topping there (Material UI,
measured on 6 November 2026) is a div with role="checkbox", aria-checked and that aria-label, which the
page made neither focusable nor clickable: a click on it does nothing. Inside it are a heading, the
topping's button, and in the button the real check box (input type="checkbox", tabindex="-1", no
name). A click on the button or on the check box adds the topping, and the outer div becomes
"Pepperoni checkbox, checked".

NVDA's browse mode never shows what is inside: a check box or radio button whose label isn't shown
elsewhere on the page has its label as its content, and an explicit label (aria-label) means none of
its children are put in the document (nvdaHelper/vbufBackends/gecko_ia2/gecko_ia2.cpp, nameIsContent
and renderChildren, NVDA 2026.2). So the topping is one line, and Space or Enter does the outer div's
default action (``browseMode.BrowseModeTreeInterceptor._activateNVDAObject``), a click on a div that
does nothing.

So when Space or Enter in browse mode activates a check box, radio button or switch that the page
didn't make focusable and that has a control inside it the page did make focusable, NVDA activates
that control instead: one of the same kind first (a check box or switch for a check box, a radio
button for a radio button), else a button. When the focus is on another control inside it that can be
used, that control is activated: Tab goes to the Extra switch pizzahut.com shows inside a topping once
it is added, browse mode's cursor stays on the topping, and Space is for Extra. Everything NVDA does to
activate an object stays as it is, the click with the mouse when a control has no action included.

Chrome moves the page's focus to a check box it activates for NVDA (measured: Edge 157, and the
focused state is at once on the check box inside), so NVDA gets a focus event for it and says it with
its state, "check box, checked"; and once the focus is on it, NVDA says the next change itself, "not
checked". The assistant says the change only when nothing has the focus in the control, "checked" or
"not checked" in NVDA's own words, once the page has made it (within two seconds): NVDA's speech of a
change says "not checked" only for the focus (controlTypes.processAndLabelStates).

A check box the page made focusable, such as pizzahut.com's Garlic-Parm Hut Blend, which works when
clicked, and one with nothing focusable inside, are activated as NVDA does. It works while the assistant
runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import functools
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "activateInnerControls"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own version, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorInnerControls"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: Browse mode's function that activates an object (Space and Enter, and a link chosen in the Elements List).
FUNCTION = "_activateNVDAObject"
#: The roles of NVDA's controlTypes.Role whose label can stand for a control inside, and the roles of that control, best first.
WRAPPERS = {
	"CHECKBOX": ("CHECKBOX", "SWITCH", "TOGGLEBUTTON"),
	"SWITCH": ("SWITCH", "CHECKBOX", "TOGGLEBUTTON"),
	"RADIOBUTTON": ("RADIOBUTTON",),
}
#: The control inside that is activated when there is none of the same kind.
FALLBACK_ROLES = ("BUTTON", "TOGGLEBUTTON")
#: The states NVDA says for these controls; a change in them is what the activation changed.
STATES = ("CHECKED", "HALFCHECKED", "PRESSED", "HALF_PRESSED", "ON")
#: No more objects than this are looked at inside a control, and no deeper than this (pizzahut.com's check box is 3 down).
MOST_OBJECTS = 60
MOST_DEPTH = 8
#: How often, and for how long, the control is looked at for the change the page makes, in milliseconds.
LOOK_EVERY = 100
LOOK_FOR = 2000
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: The roles, states and output reasons of NVDA's controlTypes, once known.
_wrappers: dict = {}
_fallback: frozenset = frozenset()
_said: frozenset = frozenset()
#: Each state and the one that goes with it: checked and half checked, pressed and half pressed.
_halves: dict = {}
#: A half state and its whole one: half checked and checked, half pressed and pressed.
_wholes: dict = {}
_focusable = None
_focused = None
#: The states of a control the page doesn't let be used: unavailable (disabled) and invisible.
_unusable: frozenset = frozenset()
#: The control whose change is being waited for: [object, its states before, looks left, whether it was seen changed, the
#: control inside it that was activated], or None.
_watched: list | None = None


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
	"""Whether Space and Enter reach the control inside a web page's check box: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have Space and Enter in browse mode reach the control inside a check box that stands for it, from now on."""
	global _enabled, _wrappers, _fallback, _said, _halves, _wholes, _focusable, _focused, _unusable
	if _enabled:
		return
	_enabled = True
	try:
		import browseMode
		from controlTypes import Role, State

		def roles(names):
			return tuple(getattr(Role, name) for name in names if hasattr(Role, name))

		_wrappers = {getattr(Role, name): roles(inner) for name, inner in WRAPPERS.items() if hasattr(Role, name)}
		_fallback = frozenset(roles(FALLBACK_ROLES))
		_said = frozenset(getattr(State, name) for name in STATES if hasattr(State, name))
		_halves, _wholes = {}, {}
		for whole, half in (("CHECKED", "HALFCHECKED"), ("PRESSED", "HALF_PRESSED")):
			if hasattr(State, whole) and hasattr(State, half):
				_halves[getattr(State, whole)] = getattr(State, half)
				_halves[getattr(State, half)] = getattr(State, whole)
				_wholes[getattr(State, half)] = getattr(State, whole)
		_focusable = State.FOCUSABLE
		_focused = getattr(State, "FOCUSED", None)
		_unusable = frozenset(getattr(State, name) for name in ("UNAVAILABLE", "INVISIBLE") if hasattr(State, name))
		with _lock:
			_replace(browseMode.BrowseModeTreeInterceptor, FUNCTION, _activateGuarded)
	except Exception:
		_failure("can't have Space and Enter reach the check box inside a web page's check box")


def unregister() -> None:
	"""Give NVDA its own activation back, where nothing has been put over the assistant's since."""
	global _enabled, _watched
	if not _enabled:
		return
	_enabled = False
	_watched = None
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
	"""Whether ``function`` is the assistant's version, or wraps it (as another add-on's functools.wraps wrapper would)."""
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
		_failure(f"NVDA has no {name} the assistant knows, so browse mode activates a check box as NVDA does")
		return False
	installed = guarded(current)
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, current))
	_log().debug(f"jawsMigrator: Space and Enter in browse mode reach the check box inside a web page's check box ({getattr(owner, '__name__', owner)}.{name})")
	return True


def _usable(obj) -> bool:
	"""Whether the page made ``obj`` a control to use: focusable, and neither unavailable nor invisible."""
	states = obj.states
	return _focusable in states and not _unusable.intersection(states)


def _children(obj):
	child = obj.firstChild
	while child is not None:
		yield child
		child = child.next


def innerControl(obj):
	"""The control inside ``obj`` that Space and Enter activate in its place, or None when NVDA activates ``obj`` itself.

	``obj`` is a check box, radio button or switch that the page made neither focusable nor unavailable, with
	a control inside it that the page made focusable: the first of the same kind, in the page's order, else the
	first button.
	"""
	kinds = _wrappers.get(obj.role)
	if not kinds:
		return None
	states = obj.states
	if _focusable in states or _unusable.intersection(states):
		return None
	fallback = None
	seen = 0
	pending = [(child, 1) for child in reversed(list(_children(obj)))]
	while pending and seen < MOST_OBJECTS:
		child, depth = pending.pop()
		seen += 1
		role = child.role
		if role in kinds and _usable(child):
			return child
		if fallback is None and role in _fallback and _usable(child):
			fallback = child
		if depth < MOST_DEPTH:
			pending.extend((grandchild, depth + 1) for grandchild in reversed(list(_children(child))))
	return fallback


def target(obj):
	"""What Space and Enter activate in the place of ``obj``, and whether it has the focus: ``(control, focused)``, or ``(None, False)``.

	The control inside ``obj`` (see innerControl), unless the focus is on another control inside ``obj`` that can be used:
	the one you moved to with Tab (pizzahut.com's Extra switch, shown inside the topping once it is added), as browse
	mode's cursor stays on ``obj``, which has nothing inside it in NVDA's document.
	"""
	inner = innerControl(obj)
	if inner is None:
		return None, False
	import api

	focus = api.getFocusObject()
	if focus is not None and focus != inner and focus != obj and _usable(focus):
		if any(ancestor == obj for ancestor in api.getFocusAncestors()):
			return focus, True
	return inner, False


def _states(obj) -> frozenset:
	return frozenset(obj.states) & _said


def changeWords(before: frozenset, now: frozenset) -> list:
	"""What NVDA says for the change from ``before`` to ``now``, in NVDA's own words: "checked", "not checked", "half checked".

	NVDA's speech of a change (speech.getObjectPropertiesSpeech) says "not checked" only for an object with the focus
	(controlTypes.processAndLabelStates), and the check box the page ignores never has it, so the words are NVDA's labels.
	"""
	words = [state.displayString for state in sorted(now - before, key=_order)]
	for state in sorted(before - now, key=_order):
		if state in _halves and _halves[state] in now:
			# Checked to half checked, or the other way: the state it has now is said, and nothing for the one it left.
			continue
		# Half checked to nothing is "not checked", as NVDA says it (#6946 in controlTypes.processAndLabelStates).
		word = _wholes.get(state, state).negativeDisplayString
		if word not in words:
			words.append(word)
	return words


def _order(state):
	return getattr(state, "value", 0)


def _nvdaSaysIt(obj, inner) -> bool:
	"""Whether NVDA says the change itself, so the assistant doesn't.

	It does for the focus and the objects the focus is in (NVDAObject.event_stateChange). And Chrome moves the focus
	to a check box it activates for NVDA, before the page changes anything, so NVDA gets a focus event for the check
	box inside and says it with its state ("check box, checked"); the check box has the focused state at once, and
	NVDA's focus may come a moment later.
	"""
	import api

	focus = api.getFocusObject()
	if any(other == obj for other in (focus, *api.getFocusAncestors())):
		return True
	return _focused is not None and _focused in inner.states


def _watch(obj, inner) -> None:
	"""Wait for the page to change ``obj``, and say what changed, as NVDA does for a check box with the focus."""
	global _watched
	try:
		import core

		watched = [obj, _states(obj), LOOK_FOR // LOOK_EVERY, False, inner]
		_watched = watched
		core.callLater(LOOK_EVERY, _look, watched)
	except Exception:
		_failure("could not wait for a web page's check box to change")


def _look(watched) -> None:
	"""One look at the control activated through the control inside it: say its change once it has come."""
	global _watched
	if watched is not _watched or not _enabled:
		# Another activation since, or turned off.
		return
	obj, before, left = watched[:3]
	try:
		now = _states(obj)
	except Exception:
		# The page took the control away.
		_watched = None
		return
	if now != before:
		try:
			if _nvdaSaysIt(obj, watched[4]):
				# The browser moved the focus to the control inside (Chrome does, for a check box it activates), and NVDA
				# says it with its state, "check box, checked"; or the focus was in it already, and NVDA says the change.
				_watched = None
				return
			if not watched[3]:
				# The focus event can come a moment after the change: one more look before NVDA is the one to say it.
				watched[3] = True
				import core

				core.callLater(LOOK_EVERY, _look, watched)
				return
			_watched = None
			words = changeWords(before, now)
			if words:
				import ui

				ui.message(", ".join(words))
		except Exception:
			_watched = None
			_failure("could not say how a web page's check box changed")
		return
	if left <= 1:
		_watched = None
		_log().debug("jawsMigrator: the web page's check box hadn't changed two seconds after the control inside it was activated")
		return
	watched[2] = left - 1
	try:
		import core

		core.callLater(LOOK_EVERY, _look, watched)
	except Exception:
		_failure("could not wait for a web page's check box to change")


def _activateGuarded(original):
	"""Browse mode's activation of an object: a check box that only stands for a control inside it has that control activated."""

	@functools.wraps(original)
	def _activateNVDAObject(self, obj, *args, **kwargs):
		inner, focused = None, False
		if _enabled and obj is not None:
			try:
				inner, focused = target(obj)
			except Exception:
				_failure("could not look inside a web page's check box")
				inner, focused = None, False
		if inner is None:
			return original(self, obj, *args, **kwargs)
		try:
			which = "the focus, which is inside it," if focused else "the control inside it"
			_log().debug(f"jawsMigrator: {obj.name!r} is a check box the page didn't make a control, so {which} is activated ({inner.role!r}, {inner.name!r})")
		except Exception:
			pass
		if not focused:
			# NVDA says what changes for the focus itself.
			_watch(obj, inner)
		return original(self, inner, *args, **kwargs)

	setattr(_activateNVDAObject, MARK, _TOKEN)
	setattr(_activateNVDAObject, ORIGINAL, original)
	return _activateNVDAObject
