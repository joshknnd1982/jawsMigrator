# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Enhanced Control Support doesn't read a whole document 20 times a second, so a large file can't freeze NVDA.

A tester pasted 21 million characters into Windows 11's Notepad and pressed Control+Home: NVDA froze, and came
back 17 seconds later only because the tester had pressed Control+Alt+N to restart it. Each time they came back
to a 24-million-character file in Notepad, NVDA was stuck for a second or two. Enhanced Control Support 1.2.2, which
the assistant offers to install for JAWS Window Class Reassign, was checking Notepad's document for changes:
with its "Rely on events by default" off, as it comes, it gives each control it handles a timer (TimerMixin)
that reads the focused control's name, value and states every 50 ms, and once as it makes the control. A
document's value is its whole text. Each read took Notepad 0.2 to 0.3 seconds and then failed ("An unexpected
exception was raised"), so the next check was already due, and NVDA's main thread did little else. Control+Home
has NVDA wait for the caret to move (``editableText.EditableText._hasCaretMoved``, which calls
``api.processPendingEvents``, which calls ``wx.Yield``). ``wx.Yield`` runs whatever is waiting until nothing is,
and a check was always waiting, so it only returned when NVDA's restart ended it.

NVDA follows a text document through the program's caret and text change events, and never reads its whole
value itself, so the timer adds nothing there. The assistant asks Enhanced Control Support's own choice first
(``shouldUseTimerMixin`` in ``globalPlugins.enhancedControlSupport``), and has the answer be no for a document,
or a multi-line text field, that NVDA reads as editable text (NVDA's ``EditableText``). Enhanced Control
Support keeps its timer for its own controls for windows NVDA doesn't know (its ``Win32`` and ``Complex``), and
for a window whose treatment the user chose in Enhanced Control Support (NVDA+Alt+C). Everything else it does
is unchanged. It works while the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration
Assistant.
"""

from __future__ import annotations

import functools
import sys

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "documentsWithoutControlSupportTimer"
#: Enhanced Control Support's global plugin, as NVDA imports it.
MODULE = "globalPlugins.enhancedControlSupport"
#: Its choice of whether a control gets its timer: shouldUseTimerMixin(conf, obj, clsList).
CHOICE = "shouldUseTimerMixin"
#: The class that carries its timer; without it, the choice is not the one the assistant knows.
TIMER_CLASS = "TimerMixin"
#: Its classes for a window NVDA doesn't know, which it always checks with its timer.
OWN_CLASSES = ("Win32", "Complex")
#: Marks what the assistant put in the place of Enhanced Control Support's own, and keeps its own.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's version, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorDocumentPolling"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
#: What the assistant put in the place of Enhanced Control Support's own: [(module, the assistant's, its own)].
_replaced: list = []
#: The window classes whose documents the log has named once.
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


def wanted(stateData: dict) -> bool:
	"""Whether Enhanced Control Support leaves its timer off documents NVDA follows: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have Enhanced Control Support leave its timer off documents NVDA follows, from now on."""
	global _enabled
	if _enabled:
		# Called again after a migration, a restore or a configuration reload: Enhanced Control Support may have
		# loaded since.
		_install()
		return
	_enabled = True
	if not _install():
		# NVDA imports the global plugins one after another, and Enhanced Control Support may come after the
		# assistant. Everything NVDA does as it starts, the first focus included, waits for the plugins.
		try:
			import wx

			wx.CallAfter(_installIfWanted)
		except Exception:
			pass


def unregister() -> None:
	"""Give Enhanced Control Support its own choice back, where nothing has been put over the assistant's since."""
	global _enabled
	if not _enabled:
		return
	_enabled = False
	for module, installed, original in reversed(_replaced):
		try:
			if vars(module).get(CHOICE) is installed:
				setattr(module, CHOICE, original)
		except Exception:
			pass
	_replaced.clear()


def isRegistered() -> bool:
	return _enabled


def isInstalled() -> bool:
	"""Whether the assistant's version of the choice is in Enhanced Control Support now."""
	module = sys.modules.get(MODULE)
	return module is not None and _isOurs(vars(module).get(CHOICE))


def _installIfWanted() -> None:
	if _enabled:
		_install()


def _isOurs(function) -> bool:
	"""Whether ``function`` is the assistant's version, or wraps it (as another add-on's functools.wraps wrapper would)."""
	for _ in range(_MOST_WRAPPERS):
		if function is None:
			return False
		if getattr(function, MARK, None) is _TOKEN:
			return True
		function = getattr(function, "__wrapped__", None)
	return False


def _install() -> bool:
	"""Put the assistant's version of the choice in Enhanced Control Support, once. True when it is there."""
	module = sys.modules.get(MODULE)
	if module is None:
		# Not installed, turned off, or not loaded yet.
		return False
	try:
		current = vars(module).get(CHOICE)
		if _isOurs(current):
			# Still there from before: turned off and on again, or another add-on has put its own around it since.
			return True
		if not callable(current) or not isinstance(vars(module).get(TIMER_CLASS), type):
			_failure(f"Enhanced Control Support has no {CHOICE} the assistant knows, so it checks documents as it always has")
			return False
		installed = _guarded(current, module)
		setattr(module, CHOICE, installed)
		_replaced.append((module, installed, current))
		_log().debug(f"jawsMigrator: Enhanced Control Support leaves its timer off documents NVDA follows ({MODULE}.{CHOICE})")
		return True
	except Exception:
		_failure("can't keep Enhanced Control Support's timer off documents")
		return False


def _followedDocument(conf, obj, clsList, module) -> bool:
	"""Whether ``obj`` is a document, or a multi-line text field, NVDA follows itself, which Enhanced Control Support
	doesn't need to check: not one of Enhanced Control Support's own controls, nor in a window the user set up in it."""
	if conf:
		# The user chose in Enhanced Control Support how to treat this window (NVDA+Alt+C).
		return False
	classes = [cls for cls in clsList if isinstance(cls, type)]
	own = tuple(cls for cls in (getattr(module, name, None) for name in OWN_CLASSES) if isinstance(cls, type))
	if own and any(issubclass(cls, own) for cls in classes):
		return False
	import editableText

	if not any(issubclass(cls, editableText.EditableText) for cls in classes):
		return False
	from controlTypes import Role, State

	role = obj.role
	return role == Role.DOCUMENT or (role == Role.EDITABLETEXT and State.MULTILINE in obj.states)


def _note(obj) -> None:
	windowClass = getattr(obj, "windowClassName", None) or "?"
	if windowClass in _logged:
		return
	_logged.add(windowClass)
	_log().debug(
		f"jawsMigrator: Enhanced Control Support doesn't check this document ({windowClass}) every 50 ms: NVDA follows its "
		"text itself, and reading all of it at once can freeze NVDA in a large file",
	)


def _guarded(original, module):
	"""Enhanced Control Support's choice of whether a control gets its timer: not for a document NVDA follows."""

	@functools.wraps(original)
	def shouldUseTimerMixin(conf, obj, clsList, *args, **kwargs):
		use = original(conf, obj, clsList, *args, **kwargs)
		if not use or not _enabled:
			return use
		try:
			if not _followedDocument(conf, obj, clsList, module):
				return use
			_note(obj)
		except Exception:
			_failure("could not tell whether a control is a document NVDA follows, so Enhanced Control Support checks it")
			return use
		return False

	setattr(shouldUseTimerMixin, MARK, _TOKEN)
	setattr(shouldUseTimerMixin, ORIGINAL, original)
	return shouldUseTimerMixin
