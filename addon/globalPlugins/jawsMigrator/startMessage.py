# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""NVDA says "NVDA is ready." as it starts, where JAWS says "JAWS", and nothing the user does stops it (issue 41).

The tester, on issue 41: "This is what Jaws says when it starts. Of course this should be a check box just like the
exiting NVDA." What JAWS said was "JAWS". The project's owner answered: 'It should say "NVDA is ready." And that
announcement should not be interruptable by the user.'

JAWS 2026's files have no setting for it: Default.jcf has no option for what JAWS says as it starts, and the
AutoStartEvent of Default.jss and of JAWS Window.jss, the scripts that run as JAWS starts, don't say it. So a migration
has nothing to take from JAWS, as it takes "Unloading NVDA" from JAWS's JAWS Messages (see exitMessage). The message is
on as the assistant comes, and NVDA's Settings, JAWS Migration Assistant turns it off.

When it is said. NVDA says the window and the focus as it starts (core._setInitialFocus), and the window's foreground
event stops speech first (NVDAObject.event_foreground), so a message said sooner would be cut off. NVDA handles the
window before it gives a global plugin the focus event (eventHandler.executeEvent runs doPreGainFocus first), and the
plugin's code after nextHandler runs once NVDA has queued what it says for the focus. The message is queued there, at
normal priority, so it comes after where you are, as "Screen curtain on" does (see screenShade). Where no focus event
comes, it is said FALLBACK_MS after NVDA has started. It is said only as NVDA starts, never when NVDA reloads its
plugins, and only where NVDA speaks (not when speech is off, beeps, on demand, paused or silent).

Why nothing stops it. A key pressed stops NVDA's speech (inputCore queues speech.cancelSpeech for the key, looked up
in NVDA's speech package as the key is pressed), and so does each window change (NVDAObject.event_foreground). The Shift
key pauses it (speech.pauseSpeech, until Shift is pressed again). NVDA's cancelSpeech tells its extension points before
and after it cancels (pre_speechCanceled, speechCanceled), and nothing there can say no. So, from the moment the
synthesizer starts on the message until it has said it, the assistant's cancelSpeech and pauseSpeech take NVDA's place:
cancelSpeech does nothing, and pauseSpeech does nothing when it is asked to pause (asked to resume, it does as NVDA's
does); then NVDA's own come back. The message is a second long, and after LONGEST_HOLD NVDA's speech stops as it always
does, even when the synthesizer never says it has finished. The synthesizer starts on it at once where nothing else was
waiting to be said, and otherwise when NVDA's speech manager reaches a callback at the start of the message
(speech.commands.CallbackCommand, which NVDA runs when the synthesizer reaches that point). The message waits its turn: a key pressed while NVDA is still
saying where you are stops that, as it always does. If it stops the message before the synthesizer has started on it, the
message is said again RETRY_MS later, up to MOST_TRIES times in all, so it is always heard once.
"""

from __future__ import annotations

import functools
import threading

#: The assistant's setting (state.json): say "NVDA is ready." as NVDA starts. On unless the user turned it off.
STATE_KEY = "sayNvdaReady"
#: What NVDA says, as the project's owner asked (issue 41).
MESSAGE = "NVDA is ready."
#: What JAWS says as it starts, for the assistant's own words.
JAWS_MESSAGE = "JAWS"
#: How many times in all the message is handed to NVDA's speech, when a key or a window change stops it before the
#: synthesizer has started on it.
MOST_TRIES = 5
#: After it was stopped before it was heard, the message is queued again this long after, in milliseconds.
RETRY_MS = 300
#: Where no focus event comes, the message is said this long after NVDA has started, in milliseconds. NVDA says where you
#: are first: it queues the initial focus before its postNvdaStartup.
FALLBACK_MS = 3000
#: After NVDA has started, the message is said within this time or not at all, in milliseconds.
GIVE_UP_MS = 30000
#: The longest NVDA's speech is kept from stopping, in milliseconds. The message takes a second.
LONGEST_HOLD = 4000
#: NVDA's functions by which the user stops its speech: a key cancels it, and Shift pauses it.
STOPPERS = ("cancelSpeech", "pauseSpeech")
#: Marks the assistant's cancelSpeech and pauseSpeech, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorStartMessage"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: NVDA's own function, kept on the assistant's.
ORIGINAL = "_jawsMigratorOriginal"
_MOST_WRAPPERS = 16

_lock = threading.RLock()
_failed = False
#: As NVDA starts: the message is said after NVDA's next focus announcement.
_waiting = False
#: The message is in NVDA's speech, not said yet.
_queued = False
_tries = 0
_listening = False
#: NVDA's cancelSpeech does nothing, while the synthesizer says the message.
_holding = False
#: How many times NVDA's cancelSpeech was kept from stopping speech, in this hold.
_kept = 0
#: The assistant's cancelSpeech and pauseSpeech, by name, while they are in NVDA's place.
_installed: dict = {}
_fallbackTimer = None
_giveUpTimer = None
_retryTimer = None
_holdTimer = None


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


def _note(message: str) -> None:
	try:
		from . import debugLog

		debugLog.note(message)
	except Exception:
		pass


def wanted(stateData: dict) -> bool:
	"""Whether NVDA says "NVDA is ready." as it starts: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def isWaiting() -> bool:
	"""Whether the message is still to be said, or said and not heard yet."""
	return _waiting or _queued or _retryTimer is not None


def isHolding() -> bool:
	"""Whether NVDA's speech is kept from stopping, while the message is said."""
	return _holding


# -- as NVDA starts -----------------------------------------------------------------------------------------------------


def atStart(stateData: dict) -> bool:
	"""From the plugin's start: as NVDA starts, "NVDA is ready." is said after NVDA says where you are. Returns whether it
	waits for that (the plugin then hands afterFocus its focus events)."""
	global _waiting, _queued, _tries
	stop()
	if not wanted(stateData):
		return False
	from . import startupFocus

	# NVDA reloading its plugins starts the plugin again, and the message was said as NVDA started.
	if not startupFocus.nvdaIsStarting():
		return False
	_waiting, _queued, _tries = True, False, 0
	try:
		_listen()
	except Exception:
		_failure('can\'t say "NVDA is ready." as NVDA starts')
		stop()
		return False
	_note(f'NVDA says "{MESSAGE}" after it says where you are, as it starts, as JAWS says "{JAWS_MESSAGE}"')
	return True


def afterFocus() -> bool:
	"""From the plugin's focus event, after NVDA's own: NVDA has queued what it says for the focus, and the message goes
	after it. Returns whether the message is still to be said or heard."""
	if _waiting:
		_queue()
	return isWaiting()


def _listen() -> None:
	global _listening
	import core
	from speech.extensions import speechCanceled

	core.postNvdaStartup.register(_started)
	speechCanceled.register(_onSpeechCanceled)
	_listening = True


def _whyNotSaid() -> str | None:
	"""Why NVDA says nothing now, or None to say the message."""
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


def _queue() -> None:
	"""Hand the message to NVDA's speech. Nothing escapes: this runs in NVDA's focus event, after NVDA's own handling."""
	try:
		_say()
	except Exception:
		_failure(f'could not say "{MESSAGE}" as NVDA started')
		stop()


def _say() -> None:
	global _waiting, _queued, _tries
	try:
		reason = _whyNotSaid()
	except Exception:
		_failure("could not tell whether NVDA can say its ready message")
		reason = "NVDA's state could not be read"
	if reason:
		stop(f"nothing would be heard: {reason}")
		return
	_waiting = False
	import speech
	from speech.commands import CallbackCommand

	from . import speechQueue

	# Nothing else waiting to be said: the synthesizer starts on the message at once (asked before it is queued).
	idle = speechQueue.pending() == set()
	_tries += 1
	_queued = True
	# At normal priority: after what NVDA has queued for the window and the focus. The first callback runs when the synthesizer
	# starts on the message, the second when it has said it.
	speech.speak(
		[
			CallbackCommand(_onStarted, name="jawsMigrator:readyStarted"),
			MESSAGE,
			CallbackCommand(_onSaid, name="jawsMigrator:readySaid"),
		],
		priority=speech.Spri.NORMAL,
	)
	if idle:
		_hold()
	_log().debug(f'jawsMigrator: NVDA says "{MESSAGE}" after where you are, as it started (try {_tries})')


def _started() -> None:
	"""NVDA's postNvdaStartup: NVDA has queued its initial focus, and says it next. NVDA notifies it once; stop takes the
	handler out afterwards, never while NVDA goes through its handlers (see _later)."""
	global _fallbackTimer, _giveUpTimer
	if not isWaiting() or _giveUpTimer is not None:
		return
	import wx

	_fallbackTimer = wx.CallLater(FALLBACK_MS, _sayWithoutFocus)
	_giveUpTimer = wx.CallLater(GIVE_UP_MS, stop, f"not said within {GIVE_UP_MS // 1000} seconds of NVDA's start")


def _sayWithoutFocus() -> None:
	global _fallbackTimer
	_fallbackTimer = None
	if _waiting:
		_queue()


def _onStarted(*args, **kwargs) -> None:
	# NVDA's speech manager runs this once the synthesizer has reached the start of the message.
	if _queued:
		_hold()


def _onSaid(*args, **kwargs) -> None:
	# NVDA's speech manager runs this once the synthesizer has said the message.
	stop("it was said")


def _onSpeechCanceled(**kwargs) -> None:
	# Runs inside NVDA's cancelSpeech, after it dropped everything NVDA had yet to say: the message, if it was queued.
	global _queued
	if not _queued:
		return
	_queued = False
	_later(_stopped)


def _later(function, *args) -> None:
	"""Run after NVDA's notification: NVDA goes through an extension point's handlers as they are, and a handler taken
	out meanwhile (extensionPoints' unregister) raises "OrderedDict mutated during iteration" there, which would stop
	NVDA's own cancelSpeech."""
	import wx

	wx.CallAfter(function, *args)


def _stopped() -> None:
	"""A key or a window change stopped the message before it was said: it is queued again soon, a few times at most."""
	global _retryTimer
	if not _listening:
		return
	_release()
	if _tries >= MOST_TRIES:
		stop(f"speech was stopped {_tries} times before it was said")
		return
	import wx

	_retryTimer = wx.CallLater(RETRY_MS, _retry)


def _retry() -> None:
	global _retryTimer
	_retryTimer = None
	if _listening and not _queued:
		_queue()


# -- nothing stops it ---------------------------------------------------------------------------------------------------


def _isOurs(function) -> bool:
	"""Whether ``function`` is this copy of one of the assistant's wrappers, or wraps it (as another add-on's
	functools.wraps wrapper would)."""
	for _ in range(_MOST_WRAPPERS):
		if function is None:
			return False
		if getattr(function, MARK, None) is _TOKEN:
			return True
		function = getattr(function, "__wrapped__", None)
	return False


def _stops(name: str, args: tuple, kwargs: dict) -> bool:
	"""Whether this call of one of NVDA's functions stops speech: cancelSpeech always, pauseSpeech(True) and not the
	pauseSpeech(False) that lets it go on."""
	if name == "pauseSpeech":
		return bool(args[0] if args else kwargs.get("switch", True))
	return True


def _guarded(name: str, original):
	@functools.wraps(original)
	def wrapper(*args, **kwargs):
		global _kept
		if not _holding or not _stops(name, args, kwargs):
			return original(*args, **kwargs)
		_kept += 1
		if _kept == 1:
			try:
				_log().debug(f"jawsMigrator: NVDA's speech isn't stopped while it says '{MESSAGE}' ({name})")
			except Exception:
				pass
		return None

	setattr(wrapper, MARK, _TOKEN)
	setattr(wrapper, ORIGINAL, original)
	return wrapper


def _hold() -> None:
	"""NVDA's speech isn't stopped until the message has been said, or for LONGEST_HOLD at the most."""
	global _holding, _kept, _holdTimer
	if _holding:
		return
	_holding = True
	_kept = 0
	try:
		import speech

		with _lock:
			for name in STOPPERS:
				current = getattr(speech, name, None)
				if _isOurs(current):
					# Still there from before, or another add-on has put its own around it since.
					continue
				if callable(current):
					_installed[name] = wrapper = _guarded(name, current)
					setattr(speech, name, wrapper)
				else:
					_failure(f"NVDA has no {name} the assistant knows, so a key can stop the message")
		import wx

		_holdTimer = wx.CallLater(LONGEST_HOLD, _holdEnds)
	except Exception:
		_failure(f"can't keep a key from stopping '{MESSAGE}'")


def _holdEnds() -> None:
	stop(f"not said within {LONGEST_HOLD / 1000:g} seconds of the synthesizer starting on it")


def _release() -> None:
	"""NVDA's speech stops as it always does, and NVDA has its own functions back where nothing has been put over the
	assistant's since."""
	global _holding, _holdTimer
	_holding = False
	timer, _holdTimer = _holdTimer, None
	if timer is not None:
		try:
			timer.Stop()
		except Exception:
			pass
	with _lock:
		try:
			import speech

			for name, wrapper in list(_installed.items()):
				# Put over by another add-on since, the assistant's stays, and does nothing until the next message.
				if getattr(speech, name, None) is wrapper:
					setattr(speech, name, getattr(wrapper, ORIGINAL))
					del _installed[name]
		except Exception:
			pass


def stop(why: str | None = None) -> None:
	"""Say nothing more as NVDA starts (said, given up, or the plugin ends), and let NVDA's speech stop as it always does."""
	global _waiting, _queued, _listening, _fallbackTimer, _giveUpTimer, _retryTimer
	wasActive = isWaiting() or _listening or _holding
	_waiting = _queued = False
	for timer in (_fallbackTimer, _giveUpTimer, _retryTimer):
		try:
			if timer is not None:
				timer.Stop()
		except Exception:
			pass
	_fallbackTimer = _giveUpTimer = _retryTimer = None
	_release()
	if _listening:
		_listening = False
		try:
			import core
			from speech.extensions import speechCanceled

			core.postNvdaStartup.unregister(_started)
			speechCanceled.unregister(_onSpeechCanceled)
		except Exception:
			pass
	if why and wasActive:
		_log().debug(f'jawsMigrator: "{MESSAGE}" as NVDA started: {why}')
