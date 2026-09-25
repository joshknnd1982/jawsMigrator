# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Backspace says what it deletes, even where the program is slow to delete it, as JAWS does.

NVDA reads the character before the caret, sends Backspace, and says the character only once it sees the
caret move (``editableText.EditableText._backspaceScriptHelper``, then ``_hasCaretMoved``, which gives up
after NVDA's caret movement timeout, 100 ms). In a UIA document it can only see that from a caret event
within 60 ms: a UIA text range moves with the text, so the caret's old place still compares equal once the
character before it is gone. A tester pasted a 3-million-character NVDA log into Windows 11's Notepad,
deleted text, and heard nothing: after each silent Backspace NVDA's log says "Caret didn't move before
timeout", after 0.11 to 0.35 seconds, while Notepad took a while longer to delete. JAWS's DoBackSpace
(Default.JSS) says the character before the caret as it presses Backspace, without waiting.

So when NVDA gives up on a Backspace that way, the assistant looks at the text around the caret, for up to
``EXTRA_WAIT`` seconds more: once it has changed, the character was deleted, and NVDA says it as it would
have, with braille and the review cursor following. The text around the caret is read before Backspace is
sent, a few characters each side. Nothing changes where NVDA saw the caret move, in a read-only field, at
the start of the text, or when another key was pressed meanwhile (NVDA then says only what the last key
did). It works while the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration
Assistant.
"""

from __future__ import annotations

import functools
import threading
import time

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "sayWhatBackspaceDeletes"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorBackspaceEcho"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: NVDA's Backspace (and Control+Backspace) script helper, and its wait for the caret to move.
HELPER = "_backspaceScriptHelper"
WAIT = "_hasCaretMoved"
#: How much longer than NVDA to wait for the program to delete, in seconds, and how often to look.
EXTRA_WAIT = 0.4
STEP = 0.02
#: How many characters each side of the caret are compared.
AROUND = 8
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: For each thread: the Backspace going on, as (the text object, the text around its caret before the key).
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
	"""Whether Backspace says what it deletes in a slow program too: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have Backspace say what it deletes where NVDA doesn't see the caret move in time, from now on."""
	global _enabled
	if _enabled:
		return
	_enabled = True
	try:
		import editableText

		owner = editableText.EditableText
		with _lock:
			# Without NVDA's wait there is nothing to extend, and its Backspace is left alone too.
			if _replace(owner, WAIT, _waitGuarded):
				_replace(owner, HELPER, _helperGuarded)
	except Exception:
		_failure("can't have Backspace say what it deletes in slow programs")


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
		_failure(f"NVDA has no {name} the assistant knows, so Backspace works as it does in NVDA")
		return False
	installed = guarded(current)
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, current))
	_log().debug(f"jawsMigrator: Backspace says what it deletes in slow programs too ({getattr(owner, '__name__', owner)}.{name})")
	return True


def _around(obj, needBefore: bool = False):
	"""The text ``AROUND`` characters each side of ``obj``'s caret. None when ``needBefore`` and nothing is before the caret."""
	import textInfos

	window = obj.makeTextInfo(textInfos.POSITION_CARET).copy()
	moved = window.move(textInfos.UNIT_CHARACTER, -AROUND, endPoint="start")
	if needBefore and not moved:
		return None
	window.move(textInfos.UNIT_CHARACTER, AROUND, endPoint="end")
	return window.text


def _isReadOnly(obj) -> bool:
	try:
		from controlTypes import State

		return State.READONLY in obj.states
	except Exception:
		return False


def _alive() -> None:
	"""Tell NVDA's watchdog that NVDA's main thread is still working, not frozen, while it waits."""
	try:
		import watchdog

		watchdog.alive()
	except Exception:
		pass


def _scriptWaiting() -> bool:
	try:
		import scriptHandler

		return scriptHandler.isScriptWaiting()
	except Exception:
		return False


def _waitForDeletion(obj, before: str):
	"""Wait for the text around ``obj``'s caret to change from ``before``: the caret then, or None if it didn't, or another key came."""
	import textInfos

	start = time.monotonic()
	while True:
		if _scriptWaiting():
			return None
		try:
			if _around(obj) != before:
				return obj.makeTextInfo(textInfos.POSITION_CARET)
		except Exception:
			# The program may be busy; look again.
			pass
		waited = time.monotonic() - start
		if waited >= EXTRA_WAIT:
			return None
		_alive()
		time.sleep(STEP)


def _helperGuarded(original):
	"""NVDA's Backspace: first the text around the caret is noted, so a deletion NVDA misses can be seen."""

	@functools.wraps(original)
	def _backspaceScriptHelper(obj, *args, **kwargs):
		if not _enabled:
			return original(obj, *args, **kwargs)
		before = None
		try:
			if not _isReadOnly(obj):
				before = _around(obj, needBefore=True)
		except Exception:
			before = None
		previous = getattr(_local, "pending", None)
		_local.pending = (obj, before) if before is not None else None
		try:
			return original(obj, *args, **kwargs)
		finally:
			_local.pending = previous

	setattr(_backspaceScriptHelper, MARK, _TOKEN)
	setattr(_backspaceScriptHelper, ORIGINAL, original)
	return _backspaceScriptHelper


def _waitGuarded(original):
	"""NVDA's wait for the caret to move: after a Backspace NVDA gave up on, the assistant waits for the text to change."""

	@functools.wraps(original)
	def _hasCaretMoved(obj, *args, **kwargs):
		moved, info = original(obj, *args, **kwargs)
		pending = getattr(_local, "pending", None)
		# NVDA saw the caret move, a focus change came, or another key is waiting (NVDA says only the last).
		if moved or info is None or not _enabled or pending is None or pending[0] is not obj:
			return moved, info
		_local.pending = None
		started = time.monotonic()
		try:
			newInfo = _waitForDeletion(obj, pending[1])
		except Exception:
			_failure("could not tell whether Backspace deleted anything")
			newInfo = None
		if newInfo is None:
			return moved, info
		try:
			_log().debug(
				f"jawsMigrator: the program deleted the character {(time.monotonic() - started) * 1000:.0f} ms after NVDA stopped "
				"waiting for the caret, so NVDA says it, as JAWS does",
			)
		except Exception:
			pass
		return True, newInfo

	setattr(_hasCaretMoved, MARK, _TOKEN)
	setattr(_hasCaretMoved, ORIGINAL, original)
	return _hasCaretMoved
