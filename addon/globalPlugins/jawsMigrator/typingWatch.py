# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""NVDA's log says when a program types a key late or not at all, and what NVDA was doing meanwhile.

A tester opened NVDA's log, about 10 million characters, in Windows 11's Notepad and typed "It isn't reading what I'm
typing". Notepad got "I sn't reetg wt 'mtyping": letters and spaces were missing from the text itself, and NVDA said
nothing as they typed. NVDA says a typed character when the program types it (the program's WM_CHAR, which NVDA's
helper in the program passes on as NVDA's typedCharacter event), not when the key is pressed, so a key the program
never types is never said. The tester's earlier logs show keys lost the same way in Notepad, each while NVDA was
stuck waiting for Notepad ("Potential freeze" from NVDA's watchdog, a second at a time): "message" came out "meg", and
"a bug with" "abugwith". Those logs were from before version 1.15, while Enhanced Control Support read Notepad's whole
document 20 times a second (see documentPolling). The typing this time came after the log the tester sent had been
saved, so nothing shows what held NVDA or Notepad up.

So that the next log shows it, while NVDA logs at its debug level:

- A character key NVDA passes to a program's text field, which the program hasn't typed half a second later, is
  logged when the next key comes ("jawsMigrator: notepad hasn't typed "s", pressed 612 ms ago"), with where NVDA's
  main thread was at that moment when it was busy, once a second at most: a busy NVDA shows what held it up, an idle
  one that the program was slow.
- One the program types late is logged with how late ("notepad typed "s" 1240 ms after the key").
- One the program never types is logged too: as soon as a key pressed after it is typed, as programs type keys in
  the order they come; otherwise at the first key ten seconds on. (In the tester's log Notepad typed a key 2.6
  seconds after it was pressed.)

Nothing is said or changed: the assistant only notes the keys (NVDA's decide_executeGesture, in NVDA's keyboard
thread) and the characters the program types (the typedCharacter event). At any other log level it does nothing.
"""

from __future__ import annotations

import collections
import sys
import threading
import time
import traceback

#: How long a program may take to type a key before the log says so, and before the key counts as lost, in seconds.
LATE = 0.5
LOST = 10.0
#: How often at most the log shows where NVDA's main thread is, in seconds, and how many of its innermost calls.
STACK_EVERY = 1.0
STACK_DEPTH = 16
#: How many keys are waited for at most.
MOST_WAITING = 64

_registered = False
_failed = False
_lock = threading.Lock()
#: The keys waited for, oldest first: [when pressed (time.monotonic()), character, program, reported late].
_waiting: collections.deque = collections.deque(maxlen=MOST_WAITING)
#: When the log last showed where NVDA's main thread was.
_lastStack = 0.0


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


def _debugging() -> bool:
	import logging

	return _log().isEnabledFor(logging.DEBUG)


def register() -> None:
	"""Note the keys NVDA passes to programs' text fields, from now on."""
	global _registered
	if _registered:
		return
	try:
		import inputCore

		inputCore.decide_executeGesture.register(noteKey)
		_registered = True
	except Exception:
		_failure("can't note the keys a program types late or not at all")


def unregister() -> None:
	global _registered
	if not _registered:
		return
	_registered = False
	try:
		import inputCore

		inputCore.decide_executeGesture.unregister(noteKey)
	except Exception:
		pass
	with _lock:
		_waiting.clear()


def isRegistered() -> bool:
	return _registered


def _character(gesture) -> str | None:
	"""The character ``gesture`` types, or None when it isn't a key that types one."""
	if not hasattr(gesture, "vkCode") or getattr(gesture, "isModifier", False) or not getattr(gesture, "isCharacter", False):
		return None
	character = getattr(gesture, "character", None)
	if character is None:
		# NVDA 2026.1 has no KeyboardInputGesture.character: the key's name, for a letter, a digit or space.
		name = getattr(gesture, "mainKeyName", "") or ""
		if name == "space":
			character = " "
		elif len(name) == 1 and name.isalnum():
			character = name
	if not character or not character.isprintable():
		return None
	return character


def _typesInto(focus) -> bool:
	"""Whether a character key on ``focus`` goes to a program's text field, which NVDA hears typing from the program."""
	import editableText
	import keyboardHandler

	if not isinstance(focus, editableText.EditableText):
		return False
	interceptor = getattr(focus, "treeInterceptor", None)
	if interceptor is not None and not getattr(interceptor, "passThrough", True):
		# Browse mode: letters are NVDA's quick navigation keys.
		return False
	# Where NVDA works out typed characters from the keys themselves, the program isn't asked.
	return not keyboardHandler.shouldUseToUnicodeEx(focus)


def _program(focus) -> str:
	try:
		return focus.appModule.appName
	except Exception:
		return "the program"


def _same(one: str, other: str) -> bool:
	# Case aside: NVDA 2026.1 gives only the key's name (see _character).
	return one == other or one.lower() == other.lower()


def noteKey(gesture=None, **kwargs) -> bool:
	"""NVDA's decide_executeGesture handler, in NVDA's keyboard thread: note a character key. Always True: nothing changes."""
	if gesture is None:
		return True
	try:
		if not _debugging():
			return True
		now = time.monotonic()
		_review(now)
		character = _character(gesture)
		if character is None:
			return True
		import api

		focus = api.getFocusObject()
		if focus is None or not _typesInto(focus):
			return True
		with _lock:
			_waiting.append([now, character, _program(focus), False])
	except Exception:
		_failure("could not note a key for the program to type")
	return True


def _mainThreadAt() -> str:
	"""Where NVDA's main thread is now, as its innermost calls, or why not."""
	try:
		import watchdog

		if watchdog.isCoreAsleep():
			return "NVDA's main thread was idle, waiting for something to do"
	except Exception:
		pass
	frame = sys._current_frames().get(threading.main_thread().ident)
	if frame is None:
		return "NVDA's main thread wasn't found"
	# Without the source lines, which NVDA's keyboard thread shouldn't wait to read: the innermost calls, outermost first.
	summary = traceback.StackSummary.extract(traceback.walk_stack(frame), limit=STACK_DEPTH, lookup_lines=False)
	# "at", not a traceback's "File", so that these lines stand out from the warnings in the log.
	calls = "\n".join(f"  at {entry.name} ({entry.filename}, line {entry.lineno})" for entry in reversed(summary))
	return f"NVDA's main thread was busy in:\n{calls}"


def _review(now: float) -> None:
	"""At a key press: log the keys the program hasn't typed after LATE, and give up on those not typed after LOST."""
	global _lastStack
	late = []
	lost = []
	with _lock:
		for entry in list(_waiting):
			waited = now - entry[0]
			if waited >= LOST:
				_waiting.remove(entry)
				lost.append((entry, waited))
			elif waited >= LATE and not entry[3]:
				entry[3] = True
				late.append((entry, waited))
	log = _log()
	for (pressed, character, program, _reported), waited in lost:
		log.debug(f"jawsMigrator: {program} never typed {character!r}, pressed {waited * 1000:.0f} ms ago")
	if not late:
		return
	message = ", ".join(f"{character!r}, pressed {waited * 1000:.0f} ms ago" for (pressed, character, program, _reported), waited in late)
	program = late[0][0][2]
	if now - _lastStack >= STACK_EVERY:
		_lastStack = now
		message += f"; {_mainThreadAt()}"
	log.debug(f"jawsMigrator: {program} hasn't typed {message}")


def typed(character: str) -> None:
	"""NVDA's typedCharacter event, in NVDA's main thread: the program typed ``character``."""
	if not _registered or not character:
		return
	try:
		if not _debugging():
			return
		now = time.monotonic()
		with _lock:
			index = next((index for index, entry in enumerate(_waiting) if _same(entry[1], character)), None)
			if index is None:
				return
			skipped = [_waiting.popleft() for _ in range(index)]
			pressed, _character, program, _reported = _waiting.popleft()
		log = _log()
		for skippedPressed, skippedCharacter, skippedProgram, _skippedReported in skipped:
			# Typed in order: one pressed before this that isn't typed yet never will be.
			log.debug(
				f"jawsMigrator: {skippedProgram} never typed {skippedCharacter!r}, pressed {(now - skippedPressed) * 1000:.0f} ms ago; "
				f"it typed {character!r}, pressed after it",
			)
		waited = now - pressed
		if waited >= LATE:
			log.debug(f"jawsMigrator: {program} typed {character!r} {waited * 1000:.0f} ms after the key")
	except Exception:
		_failure("could not match a typed character with its key")
