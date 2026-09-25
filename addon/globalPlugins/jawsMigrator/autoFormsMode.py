# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Browse mode on a web page's tabs and toolbar buttons, as JAWS's Auto Forms Mode, so letters never reach the page.

A tester typed an issue's title on github.com, pressed Tab and typed its description. The Tab key had
moved the focus to the editor's "Write" tab, not its text box, and NVDA stays in focus mode when the
focus moves to a tab (``browseMode.BrowseModeTreeInterceptor.shouldPassThrough``: Role.TAB is one of its
SWITCH_TO_PASS_THROUGH_ON_FOCUS_ROLES), so the letters went to the page. S is GitHub's key for its
search: the tester was in "Quick search, dialog" before finishing the first word. The editor's toolbar
comes next, and NVDA uses focus mode for anything in a toolbar too. JAWS stays in the virtual cursor on
both: since version 2023 it stays there when Tab moves to a tab (FreedomScientific/standards-support#746),
and its Auto Forms Mode leaves forms mode for buttons and check boxes, in a toolbar too (#708). In the
virtual cursor letters are quick navigation keys, and never reach the page.

So NVDA uses browse mode, as JAWS does, when the focus moves:
- to a tab in a browse mode document from anything but another tab (Tab, Shift+Tab, a click, Enter on
  the tab, or the page itself);
- to a button, toggle button, menu button or check box in a toolbar, with Tab or Shift+Tab.
NVDA says "browse mode" (or plays its sound) when it was in focus mode. From one tab to another, as the
arrow keys move in focus mode, NVDA stays in the mode it is in; so do the arrow keys in a toolbar, and
NVDA+Space switches modes by hand as always. Edit fields, lists, menus and radio buttons keep NVDA's
choice. It works while the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration
Assistant.
"""

from __future__ import annotations

import functools
import threading
import time

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "browseModeOnTabsAndToolbars"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own version, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorAutoFormsMode"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: NVDA's choice between browse mode and focus mode for an object.
DECISION = "shouldPassThrough"
#: How long after Tab or Shift+Tab a focus change counts as made by it, in seconds.
AFTER_TAB = 1.5
#: What NVDA calls the Tab keys, at the end of a gesture's identifiers ("kb:tab", "kb(laptop):shift+tab").
TAB_KEYS = (":tab", ":shift+tab")
#: The roles of NVDA's controlTypes.Role that JAWS's Auto Forms Mode leaves forms mode for, in a toolbar.
TOOLBAR_CONTROL_ROLES = ("BUTTON", "TOGGLEBUTTON", "MENUBUTTON", "SPLITBUTTON", "CHECKBOX")
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: Whether the assistant noted key presses through NVDA's decide_executeGesture.
_noting = False
#: NVDA's OutputReason.FOCUS, Role.TAB, State.EDITABLE and the toolbar control roles, once known.
_focusReason = None
_tabRole = None
_editable = None
_toolbarControls: frozenset = frozenset()
#: The roles of the objects that had the focus before and have it now, as NVDA's focus events reach the assistant.
_roles: tuple = (None, None)
#: When Tab or Shift+Tab was last pressed (time.monotonic()), or None.
_tabPressed = None
#: The focus object browse mode was last kept for, so the log says so once for each.
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
	"""Whether NVDA stays in browse mode on a web page's tabs and toolbar buttons: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def _decider():
	import inputCore

	return inputCore.decide_executeGesture


def register() -> None:
	"""Have NVDA stay in browse mode on a web page's tabs and toolbar buttons, from now on."""
	global _enabled, _noting, _focusReason, _tabRole, _editable, _toolbarControls
	if _enabled:
		return
	_enabled = True
	try:
		import browseMode
		from controlTypes import OutputReason, Role, State

		_focusReason = OutputReason.FOCUS
		_tabRole = Role.TAB
		_editable = State.EDITABLE
		_toolbarControls = frozenset(getattr(Role, name) for name in TOOLBAR_CONTROL_ROLES if hasattr(Role, name))
		with _lock:
			_replace(browseMode.BrowseModeTreeInterceptor, DECISION, _decisionGuarded)
	except Exception:
		_failure("can't keep browse mode on a web page's tabs and toolbar buttons")
	try:
		# Every key press NVDA gets, before NVDA runs it: only Tab and Shift+Tab are noted.
		_decider().register(noteGesture)
		_noting = True
	except Exception:
		_failure("can't tell which focus changes Tab made")


def unregister() -> None:
	"""Give NVDA its own choice back, where nothing has been put over the assistant's since."""
	global _enabled, _noting, _roles, _tabPressed, _noted
	if not _enabled:
		return
	_enabled = False
	_roles = (None, None)
	_tabPressed = None
	_noted = None
	if _noting:
		_noting = False
		try:
			_decider().unregister(noteGesture)
		except Exception:
			pass
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


def noteGesture(gesture=None) -> bool:
	"""NVDA's decide_executeGesture handler: note when Tab or Shift+Tab is pressed, and forget it at any other key.

	Only the focus change Tab makes counts, not one after NVDA+Space and an arrow key, however quick.
	It must return True: a handler that returns anything else stops NVDA from running the gesture,
	and so from reacting to the keyboard at all. It runs in NVDA's keyboard thread, so it only notes.
	"""
	global _tabPressed
	try:
		identifiers = getattr(gesture, "normalizedIdentifiers", None) or ()
		isTab = any(str(identifier).lower().endswith(TAB_KEYS) for identifier in identifiers)
		_tabPressed = time.monotonic() if isTab else None
	except Exception:
		_tabPressed = None
	return True


def noteFocus(obj) -> None:
	"""The focus moved to ``obj``: remember the role of what had it before. The plugin calls this before NVDA's own handlers."""
	global _roles
	if not _enabled:
		return
	try:
		role = obj.role
	except Exception:
		role = None
	_roles = (_roles[1], role)


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
		_failure(f"NVDA has no {name} the assistant knows, so NVDA chooses the mode for tabs and toolbars as it does")
		return False
	installed = guarded(current)
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, current))
	_log().debug(f"jawsMigrator: NVDA stays in browse mode on a web page's tabs and toolbar buttons, as JAWS does ({getattr(owner, '__name__', owner)}.{name})")
	return True


def _afterTab() -> bool:
	pressed = _tabPressed
	return pressed is not None and time.monotonic() - pressed <= AFTER_TAB


def _note(obj, what: str) -> None:
	global _noted
	if obj is _noted:
		return
	_noted = obj
	try:
		name = obj.name
	except Exception:
		name = None
	_log().debug(f"jawsMigrator: the focus moved to {what} ({name!r}), so NVDA stays in browse mode there, as JAWS does")


def _decisionGuarded(original):
	"""NVDA's choice of focus mode or browse mode: browse mode on a tab or a toolbar button, where JAWS's virtual cursor stays."""

	@functools.wraps(original)
	def shouldPassThrough(self, obj, *args, **kwargs):
		answer = original(self, obj, *args, **kwargs)
		if not answer or not _enabled:
			return answer
		reason = kwargs["reason"] if "reason" in kwargs else (args[0] if args else None)
		if reason is None or reason != _focusReason:
			# NVDA+Space, the caret and quick navigation choose as NVDA does.
			return answer
		try:
			if _editable in obj.states:
				return answer
			role = obj.role
			if role == _tabRole:
				if _roles[0] == _tabRole:
					# From one tab to the next, as the arrow keys move in focus mode: the mode NVDA is in stays.
					return bool(self.passThrough)
				_note(obj, "a tab from outside its tab list")
				return False
			if role in _toolbarControls and _afterTab():
				# NVDA chose focus mode for a button or check box only because it is in a toolbar.
				_note(obj, "a toolbar's button or check box with Tab")
				return False
			return answer
		except Exception:
			_failure("could not keep browse mode on a web page's tab or toolbar button")
			return answer

	setattr(shouldPassThrough, MARK, _TOKEN)
	setattr(shouldPassThrough, ORIGINAL, original)
	return shouldPassThrough
