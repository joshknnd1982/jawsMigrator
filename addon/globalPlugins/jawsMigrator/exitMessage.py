# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""NVDA says "Unloading NVDA" as it exits, where JAWS says "Unloading JAWS" (issue 34).

JAWS's Insert+F4 runs its ShutDownJAWS script (Default.jss), which says "Unloading JAWS" (common.jsm, cmsg26_L), then
unloads JAWS::

	SayFormattedMessage (ot_JAWS_message, cmsg26_L) ;"Unloading JAWS"
	ShutDownJAWS()

The message is a JAWS Message (OT_JAWS_MESSAGE), one of the "Items to be Spoken" Settings Center has for each verbosity
level, so JAWS says it only at a level where JAWS Messages are on. Default.jcf has ``[OutputModes] JAWS_MESSAGE=1|2|0``,
Beginner|Intermediate|Advanced: JAWS as it comes says it at Beginner and Intermediate, and not at Advanced. NVDA exits
without a word. The tester turns the message off in JAWS, and asked that NVDA say it where JAWS does, that it can be
turned off, and that nothing changes where JAWS doesn't say it. So a migration brings JAWS's JAWS Messages at the
user's verbosity level over as this setting (settingsMap), and NVDA's Settings, JAWS Migration Assistant turns it on
or off. For a migration made before (the setting is new in 1.37), the assistant looks at JAWS's settings once, a little
after NVDA starts (checkOnce), and turns it on only where JAWS says "Unloading JAWS".

NVDA stops speaking as it exits: asked to exit (core.triggerNVDAExit), it queues its shutdown, and in the tester's log
NVDA's main loop ended 0.2 seconds later, where core.main stops speech (speech.cancelSpeech). A message said as NVDA
exits would be cut off. So NVDA's exit waits for the message: the assistant puts its own triggerNVDAExit in the place
of NVDA's. It says "Unloading NVDA", with a speech callback after it (speech.commands.CallbackCommand), which NVDA's
speech manager runs once the synthesizer has said the message, then asks NVDA's own triggerNVDAExit to exit. A key
pressed meanwhile exits at once, as it stops the message (every key goes through inputCore.decide_executeGesture). A
window change that stops it (NVDA's menu closing gives the foreground back, and NVDA's event_foreground stops speech)
has it said again, once. After LONGEST_WAIT NVDA exits all the same.

It is said only where NVDA exits because you asked, with its exit key, NVDA's menu or its exit dialog. Nothing is said,
and NVDA's own triggerNVDAExit runs at once, when NVDA restarts (a new copy of NVDA is to start, or the exit code asks
for a restart), when NVDA is already exiting or can't exit yet (a message box is open, and NVDA's own function says so),
off NVDA's main thread or once NVDA's main loop has ended (Windows closing NVDA), and when speech is off, beeps, on
demand, paused or silent (nothing would be heard).
"""

from __future__ import annotations

import functools
import threading

#: The assistant's setting (state.json) that turns this on or off; JAWS's JAWS Messages at the user's verbosity level.
STATE_KEY = "sayUnloadingNvda"
#: True once the assistant looked at JAWS's settings for a migration made before 1.37, or a migration set STATE_KEY.
CHECKED_KEY = "exitMessageChecked"
#: What NVDA says, as JAWS's "Unloading JAWS" (common.jsm, cmsg26_L; its short form, Default.jsm msg29_S, is the same).
MESSAGE = "Unloading NVDA"
#: What JAWS says, for the assistant's own words.
JAWS_MESSAGE = "Unloading JAWS"
#: The longest NVDA waits for the message before it exits all the same, in milliseconds.
LONGEST_WAIT = 4000
#: How many times the message is said again when a window change stops it.
MOST_REPEATS = 1
#: JAWS's own JAWS Messages row (Default.JCF, JAWS 2026), Beginner|Intermediate|Advanced, for a JAWS without one.
JAWS_DEFAULT_ROW = "1|2|0|JAWS Message"
VERBOSITY_LEVELS = ("Beginner", "Intermediate", "Advanced")
#: Marks the assistant's triggerNVDAExit, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorExitMessage"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: NVDA's own function, kept on the assistant's.
ORIGINAL = "_jawsMigratorOriginal"
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: The assistant's triggerNVDAExit, while it is in NVDA's place.
_installed = None
#: The exit waiting for the message, while it is said.
_waiting = None


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
	"""Whether NVDA says "Unloading NVDA" as it exits: off unless a migration or the user turned it on."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, False))


def jawsSays(row, verbosity) -> bool | None:
	"""Whether JAWS says "Unloading JAWS", from its ``[OutputModes] JAWS_MESSAGE`` row and its ``[options] Verbosity``
	(0 Beginner, 1 Intermediate, 2 Advanced). None when the row has nothing for that level."""
	if verbosity not in (0, 1, 2):
		verbosity = 0
	parts = str(row if row is not None else JAWS_DEFAULT_ROW).split("|")
	if verbosity >= len(parts):
		return None
	from . import jawsFiles

	level = jawsFiles.parseInt(parts[verbosity])
	return None if level is None else level != 0


def jawsSaysIn(ini) -> tuple:
	"""``(whether JAWS says "Unloading JAWS", where that comes from)`` for JAWS's settings as JAWS runs them (Default.jcf,
	the user's over JAWS's own); ``(None, why)`` when it can't be told."""
	from . import jawsFiles

	verbosity = jawsFiles.parseInt(ini.get("options", "Verbosity"), 0)
	if verbosity not in (0, 1, 2):
		verbosity = 0
	row = ini.get("OutputModes", "JAWS_MESSAGE")
	where = f"[OutputModes] JAWS_MESSAGE={row}" if row is not None else f"JAWS's default JAWS_MESSAGE={JAWS_DEFAULT_ROW}"
	return jawsSays(row, verbosity), f"{where}, {VERBOSITY_LEVELS[verbosity]} level"


# -- the exit ---------------------------------------------------------------------------------------------------------


def register() -> None:
	"""Have NVDA say "Unloading NVDA" when you exit it, from now on."""
	global _enabled, _installed
	if _enabled:
		return
	_enabled = True
	try:
		import core

		with _lock:
			current = getattr(core, "triggerNVDAExit", None)
			if _isOurs(current):
				# Still there from before, or another add-on has put its own around it since.
				return
			if not callable(current):
				_failure("NVDA has no triggerNVDAExit the assistant knows, so NVDA exits without a word")
				return
			_installed = _guarded(current)
			core.triggerNVDAExit = _installed
	except Exception:
		_failure('can\'t have NVDA say "Unloading NVDA" as it exits')


def unregister() -> None:
	"""Give NVDA its own triggerNVDAExit back, where nothing has been put over the assistant's since."""
	global _enabled, _installed
	if not _enabled:
		return
	_enabled = False
	with _lock:
		try:
			import core

			# Put over by another add-on since, the assistant's stays, and does nothing until it is turned on again.
			if _installed is not None and getattr(core, "triggerNVDAExit", None) is _installed:
				core.triggerNVDAExit = getattr(_installed, ORIGINAL)
				_installed = None
		except Exception:
			pass


def isRegistered() -> bool:
	return _enabled


def isWaiting() -> bool:
	"""Whether an exit is waiting for the message."""
	return _waiting is not None


def _isOurs(function) -> bool:
	"""Whether ``function`` is this copy of the assistant's, or wraps it (as another add-on's functools.wraps wrapper would)."""
	for _ in range(_MOST_WRAPPERS):
		if function is None:
			return False
		if getattr(function, MARK, None) is _TOKEN:
			return True
		function = getattr(function, "__wrapped__", None)
	return False


def _guarded(original):
	@functools.wraps(original)
	def triggerNVDAExit(*args, **kwargs):
		if not _enabled:
			return original(*args, **kwargs)
		newNVDA = args[0] if args else kwargs.get("newNVDA")
		with _lock:
			waiting = _waiting
			if waiting is not None:
				# Asked again while the message is said (the exit key again, or a restart): NVDA answers this one, now.
				waiting.finish("NVDA was asked to exit again")
				return original(*args, **kwargs)
			try:
				reason = None if newNVDA is not None else _whyNotSaid()
			except Exception:
				_failure("could not tell whether NVDA can say its exit message")
				reason = "NVDA's state could not be read"
			if newNVDA is not None or reason:
				if reason and newNVDA is None:
					_log().debug(f'jawsMigrator: NVDA exits without "{MESSAGE}": {reason}')
				return original(*args, **kwargs)
			return _Exit(original, args, kwargs).start()

	setattr(triggerNVDAExit, MARK, _TOKEN)
	setattr(triggerNVDAExit, ORIGINAL, original)
	return triggerNVDAExit


def _whyNotSaid() -> str | None:
	"""Why NVDA exits without the message now, or None to say it."""
	import core

	if getattr(core, "_hasShutdownBeenTriggered", False):
		return "NVDA is already exiting"
	try:
		from gui.message import isModalMessageBoxActive

		if isModalMessageBoxActive():
			return "a message box is open, so NVDA can't exit yet"
	except Exception:
		pass
	if threading.current_thread() is not threading.main_thread():
		return "not asked on NVDA's main thread"
	try:
		import globalVars

		if getattr(globalVars, "exitCode", 0):
			return "NVDA restarts"
	except Exception:
		pass
	import wx

	app = wx.GetApp()
	if app is None or not app.IsMainLoopRunning():
		return "NVDA's main loop has ended"
	import speech

	speechState = speech.getState()
	if speechState.speechMode != speech.SpeechMode.talk:
		return f"speech mode is {speechState.speechMode.name}"
	if speechState.isPaused:
		return "speech is paused"
	try:
		import synthDriverHandler

		synth = synthDriverHandler.getSynth()
		if synth is None or synth.name == "silence":
			return "no synthesizer speaks"
	except Exception:
		pass
	return None


class _Exit:
	"""One exit, waiting while NVDA says the message."""

	def __init__(self, original, args, kwargs):
		self.original = original
		self.args = args
		self.kwargs = kwargs
		self.repeats = 0
		self.done = False
		self.timer = None

	def start(self) -> bool:
		global _waiting
		try:
			import inputCore
			import wx
			from speech.extensions import speechCanceled

			_waiting = self
			inputCore.decide_executeGesture.register(_onGesture)
			speechCanceled.register(_onSpeechCanceled)
			self.timer = wx.CallLater(LONGEST_WAIT, _exitAfterWaiting)
			self.say()
		except Exception:
			_failure(f'could not say "{MESSAGE}"; NVDA exits without it')
			return self.exitNow("the message could not be said")
		# NVDA's own triggerNVDAExit returns True for the first request to exit; this one is it, NVDA exits once it is said.
		return True

	def say(self) -> None:
		import braille
		import speech
		from speech.commands import CallbackCommand

		speech.speak([MESSAGE, CallbackCommand(_onSaid, name="jawsMigrator:unloadingSaid")], priority=speech.Spri.NOW)
		try:
			braille.handler.message(MESSAGE)
		except Exception:
			pass
		_log().debug(f'jawsMigrator: NVDA says "{MESSAGE}" before it exits, as JAWS says "{JAWS_MESSAGE}"')

	def stopped(self) -> None:
		"""Speech stopped without a key: a window change cut the message off."""
		if self.done:
			return
		if self.repeats >= MOST_REPEATS:
			self.exitNow("the message was stopped again")
			return
		self.repeats += 1
		try:
			self.say()
		except Exception:
			self.exitNow("the message could not be said again")

	def exitNow(self, why: str) -> bool:
		"""Ask NVDA's own triggerNVDAExit to exit, once. Returns what it returns."""
		if not self.finish(why):
			return False
		exiting = self.original(*self.args, **self.kwargs)
		if not exiting:
			_log().debugWarning(f'jawsMigrator: NVDA said "{MESSAGE}", but didn\'t exit')
		return exiting

	def finish(self, why: str) -> bool:
		"""Stop waiting, once: True the first time."""
		global _waiting
		with _lock:
			if self.done:
				return False
			self.done = True
			if _waiting is self:
				_waiting = None
		try:
			import inputCore
			from speech.extensions import speechCanceled

			inputCore.decide_executeGesture.unregister(_onGesture)
			speechCanceled.unregister(_onSpeechCanceled)
		except Exception:
			pass
		try:
			if self.timer is not None:
				self.timer.Stop()
		except Exception:
			pass
		_log().debug(f"jawsMigrator: NVDA's exit waits no longer: {why}")
		return True


def _later(function, *args) -> None:
	import wx

	wx.CallAfter(function, *args)


def _exitWaiting(why: str) -> None:
	exit_ = _waiting
	if exit_ is not None:
		exit_.exitNow(why)


def _onSaid(*args, **kwargs) -> None:
	# NVDA's speech manager runs this on NVDA's main thread, from its queue; NVDA's exit starts after it.
	if _waiting is not None:
		_later(_exitWaiting, "the message was said")


def _onGesture(gesture=None, **kwargs) -> bool:
	# Every key NVDA gets, modifiers too, comes here before NVDA stops speech for it; the key goes on as always.
	if _waiting is not None:
		_later(_exitWaiting, "a key was pressed")
	return True


def _onSpeechCanceled(**kwargs) -> None:
	exit_ = _waiting
	if exit_ is not None:
		_later(_stoppedWithoutKey, exit_)


def _stoppedWithoutKey(exit_) -> None:
	# A key pressed first has already exited; otherwise a window change stopped the message.
	if _waiting is exit_:
		exit_.stopped()


def _exitAfterWaiting() -> None:
	_exitWaiting(f"the message wasn't said within {LONGEST_WAIT / 1000:g} seconds")


# -- once, for a migration made before 1.37 -------------------------------------------------------------------------------


def announcement() -> str:
	return (
		f'JAWS Migration Assistant: NVDA now says "{MESSAGE}" as it exits, as your JAWS says "{JAWS_MESSAGE}". '
		"To turn it off, uncheck it in NVDA's Settings, JAWS Migration Assistant."
	)


def checkOnce(jawsSettings, announce, done=None) -> None:
	"""Once after the update to 1.37: turn the message on where the last migration's JAWS says "Unloading JAWS".

	``jawsSettings()`` returns JAWS's Default.jcf as JAWS runs it (the user's over JAWS's own), or None without JAWS.
	``announce(message)`` tells the user; ``done()`` is called at the end, whatever happened. Nothing changes where JAWS
	doesn't say it, where there was no migration, or where you already chose in NVDA's Settings.
	"""
	from . import debugLog, migrator, state

	finished = migrator.callOnce(done)
	try:
		stateData = state.load()
		if stateData.get(CHECKED_KEY):
			return
		if not stateData.get("lastMigration") or wanted(stateData):
			# No migration: nothing to follow. Already on: a migration or you turned it on.
			state.set(CHECKED_KEY, True)
			return
		ini = jawsSettings()
		if ini is None:
			debugLog.note(f'NVDA exits without "{MESSAGE}": JAWS\'s settings were not found, so they could not be followed')
			state.set(CHECKED_KEY, True)
			return
		says, where = jawsSaysIn(ini)
		if not says:
			debugLog.note(f'NVDA exits without a word, as JAWS says no "{JAWS_MESSAGE}" (JAWS Messages are off: {where})')
			state.set(CHECKED_KEY, True)
			return
		state.update({STATE_KEY: True, CHECKED_KEY: True})
		debugLog.note(f'NVDA says "{MESSAGE}" as it exits, as JAWS says "{JAWS_MESSAGE}" (JAWS Messages are on: {where})')
		register()
		announce(announcement())
	except Exception:
		debugLog.error(f'could not tell whether JAWS says "{JAWS_MESSAGE}"')
	finally:
		finished()
