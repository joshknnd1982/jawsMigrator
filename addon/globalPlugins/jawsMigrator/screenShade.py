# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""JAWS's Screen Shade keys and words for NVDA's Screen Curtain, and the curtain said as NVDA starts with it on (issue 37).

JAWS 2026's Insert+Space, F11 and Insert+Space, Print Screen (Default.JKM, [Common Keys]) run ScreenShadeToggle
(Default.JSS), which turns Screen Shade on or off, then says which, as a status message::

	ToggleScreenShade ()
	var int screenShade = IsScreenShadeOn ()
	...
	sayMessage (OT_STATUS, longMessage, shortMessage)

The long messages are cmsgScreenShadeOn_L, "Screen Shade on", and cmsgScreenShadeOff_L, "Screen Shade off" (common.jsm).
JAWS's help: "The Screen Shade remains active until toggled back off, or JAWS is restarted." No JAWS setting turns it on
as JAWS starts, so JAWS never starts with it on.

NVDA's Screen Curtain is JAWS's Screen Shade. NVDA+Control+Escape pressed once turns it on until NVDA restarts, and
pressed twice keeps it on after that; NVDA says "Temporary Screen curtain, enabled until next restart", "Screen curtain
enabled" or "Screen curtain disabled". "Make screen black" in NVDA's Settings, Privacy and Security, turns it on for
good: NVDA then turns it on each time it starts, before any add-on runs, and says so only on a braille display ("NVDA
started with screen curtain enabled", core.main). Speech says nothing. NVDA 2026.2 has a command that says whether the
curtain is on (script_reportScreenCurtainState), with no key. The tester's NVDA started with the curtain on and said
nothing about it; the tester looked for a key that says it, and asked for this to be more like JAWS (issue 37). On issue
33 they asked for "announcements that indicate screen shade is on like Jaws".

So, after NVDA+Shift+J, the assistant's layer, as after JAWS's Insert+Space:

- F11 and Print Screen turn the curtain on or off, JAWS's way: one press, and it stays on until you turn it off or
  NVDA restarts (NVDA's own ScreenCurtain.enable(persist=False)). Off is off, also the next time NVDA starts, as with
  NVDA's own key. NVDA says "Screen curtain on" or "Screen curtain off": JAWS's words, with NVDA's name for the
  feature, as NVDA says "Unloading NVDA" where JAWS says "Unloading JAWS". Where NVDA's "Always show a warning when
  enabling Screen Curtain" is checked, NVDA's own warning comes first, and NVDA's refusal while it recognizes content
  stays, as with NVDA's own key.
- Shift+F11 says whether the curtain is on, and whether NVDA turns it on each time it starts.

And when NVDA starts with the curtain on, it says "Screen curtain on" after it says where you are, unless that is
turned off in NVDA's Settings, JAWS Migration Assistant.

As NVDA starts it says the window and the focus (core._setInitialFocus). The window's foreground event stops speech
first (NVDAObject.event_foreground), so a message said sooner would be cut off. NVDA handles the window before it gives
a global plugin the focus event (eventHandler.executeEvent runs doPreGainFocus first), and the plugin's code after
nextHandler runs once NVDA has queued what it says for the focus. The message is queued there, at normal priority, so
it comes after where you are. When a window change stops it before it is said, it is said after the next focus, up to
MOST_TRIES times in all; once a key has been pressed, speech stopped is not said again, as a key stops any speech. Where
no focus event comes, it is said FALLBACK_MS after NVDA has started. It is said only as NVDA starts, never when NVDA
reloads its plugins.
"""

from __future__ import annotations

#: The assistant's setting (state.json): say "Screen curtain on" when NVDA starts with the curtain on.
STATE_KEY = "sayScreenCurtainAtStart"
#: What NVDA says, as JAWS's ScreenShadeToggle says cmsgScreenShadeOn_L and cmsgScreenShadeOff_L (common.jsm).
ON = "Screen curtain on"
OFF = "Screen curtain off"
#: JAWS's own words, for the assistant's own.
JAWS_ON = "Screen Shade on"
JAWS_OFF = "Screen Shade off"
#: What Shift+F11 says when NVDA's settings turn the curtain on each time NVDA starts.
ON_AT_EVERY_START = "Screen curtain on. NVDA turns it on each time it starts."
#: NVDA's own words, in its script_toggleScreenCurtain (globalCommands).
NOT_AVAILABLE = "Screen curtain not available"
COULD_NOT_DISABLE = "Could not disable screen curtain"
#: NVDA's ERROR_ENABLING_MESSAGE and UNAVAILABLE_WHEN_RECOGNISING_CONTENT_MESSAGE (screenCurtain._screenCurtain), where
#: NVDA has none of its own.
COULD_NOT_ENABLE = "Could not enable screen curtain"
RECOGNIZING_CONTENT = "Cannot enable screen curtain while performing content recognition"
#: NVDA turns the curtain on this long after its warning closes (script_toggleScreenCurtain: wx.CallLater(millis=100)).
AFTER_WARNING_MS = 100
#: How many times in all the message is handed to NVDA's speech as NVDA starts, when a window change stops it.
MOST_TRIES = 3
#: Where no focus event comes, the message is said this long after NVDA has started, in milliseconds. NVDA says where
#: you are first: it queues the initial focus before its postNvdaStartup (0.35 seconds before, in the tester's log).
FALLBACK_MS = 3000
#: After NVDA has started, the message is said within this time or not at all, in milliseconds.
GIVE_UP_MS = 30000

_failed = False
#: As NVDA starts: the message is said after NVDA's next focus announcement.
_waiting = False
#: The message is in NVDA's speech, not said yet.
_queued = False
_tries = 0
#: A key was pressed since NVDA started saying where you are.
_keyPressed = False
_listening = False
_fallbackTimer = None
_giveUpTimer = None
#: NVDA's warning before the curtain comes on, while the layer's key waits for its answer.
_warning = None


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
	"""Whether NVDA says "Screen curtain on" as it starts with the curtain on: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def curtain():
	"""NVDA's Screen Curtain (screenCurtain.screenCurtain), or None where NVDA has none."""
	try:
		import screenCurtain
	except ImportError:
		return None
	return getattr(screenCurtain, "screenCurtain", None)


def isOn() -> bool:
	current = curtain()
	return current is not None and bool(current.enabled)


def _nvdaMessage(name: str, default: str) -> str:
	"""One of NVDA's own messages in screenCurtain._screenCurtain, in NVDA's language, or its English words."""
	try:
		from screenCurtain import _screenCurtain

		return getattr(_screenCurtain, name, default)
	except Exception:
		return default


def _say(message: str) -> None:
	"""Say a message now, in speech and braille, as NVDA says its own screen curtain messages."""
	import ui
	from speech.priorities import Spri

	ui.message(message, speechPriority=Spri.NOW)


# -- the layer's keys ---------------------------------------------------------------------------------------------------


def toggle() -> str | None:
	"""NVDA+Shift+J, then F11 or Print Screen: the curtain on or off, as JAWS's Insert+Space, F11 turns Screen Shade on or
	off. Returns what was said, or None when NVDA's warning opened (or was open) first."""
	global _warning
	current = curtain()
	if current is None:
		_say(NOT_AVAILABLE)
		return NOT_AVAILABLE
	warning = _openWarning()
	if warning is not None:
		# Pressed again while NVDA's warning is open: it comes back to the front and is read again, as NVDA's key does.
		_readAgain(warning)
		return None
	if current.enabled:
		message = OFF
		try:
			# NVDA's own key does the same: the curtain is off, also the next time NVDA starts.
			current.disable()
		except Exception:
			_log().error("jawsMigrator: could not turn the screen curtain off", exc_info=True)
			message = COULD_NOT_DISABLE
		_say(message)
		_note(f'the screen curtain is off, as JAWS\'s Insert+Space, F11 says "{JAWS_OFF}"' if message == OFF else message)
		return message
	settings = current.settings
	if settings["warnOnLoad"]:
		import gui
		import wx
		from screenCurtain import _screenCurtain

		_warning = _screenCurtain.WarnOnLoadDialog(screenCurtainSettingsStorage=settings, parent=gui.mainFrame)
		gui.runScriptModalDialog(_warning, lambda result: wx.CallLater(AFTER_WARNING_MS, _afterWarning, result))
		return None
	if _recognizingContent():
		message = _nvdaMessage("UNAVAILABLE_WHEN_RECOGNISING_CONTENT_MESSAGE", RECOGNIZING_CONTENT)
		_say(message)
		return message
	return _turnOn()


def _openWarning():
	"""NVDA's warning before the curtain comes on, open for the layer's key or for NVDA's own, or None."""
	if _warning is not None:
		return _warning
	try:
		import globalCommands

		return getattr(globalCommands.commands, "_waitingOnScreenCurtainWarningDialog", None)
	except Exception:
		return None


def _readAgain(warning) -> None:
	"""NVDA's own words for it: a key press stops speech, so the warning may not have been heard."""
	import api
	import controlTypes
	import speech

	warning.Raise()
	speech.cancelSpeech()
	speech.speakObject(api.getForegroundObject(), reason=controlTypes.OutputReason.FOCUS)
	speech.speakObject(api.getFocusObject(), reason=controlTypes.OutputReason.FOCUS)


def _afterWarning(result) -> str | None:
	"""NVDA's warning was answered: Yes turns the curtain on; No leaves it off without a word, as NVDA does."""
	global _warning
	import wx

	_warning = None
	if result != wx.YES:
		return None
	return _turnOn()


def _recognizingContent() -> bool:
	"""Whether the focus is in content NVDA is recognizing and keeps refreshing, where NVDA won't turn the curtain on."""
	try:
		import api
		from contentRecog.recogUi import RefreshableRecogResultNVDAObject

		focus = api.getFocusObject()
		return isinstance(focus, RefreshableRecogResultNVDAObject) and bool(focus.recognizer.allowAutoRefresh)
	except Exception:
		return False


def _turnOn() -> str:
	"""On until it is turned off or NVDA restarts, as JAWS's Screen Shade: NVDA's settings are left as they are."""
	current = curtain()
	if current is None:
		_say(NOT_AVAILABLE)
		return NOT_AVAILABLE
	message = ON
	try:
		current.enable(persist=False)
	except Exception:
		_log().error("jawsMigrator: could not turn the screen curtain on", exc_info=True)
		message = _nvdaMessage("ERROR_ENABLING_MESSAGE", COULD_NOT_ENABLE)
	_say(message)
	_note(f'the screen curtain is on until NVDA restarts, as JAWS\'s Insert+Space, F11 says "{JAWS_ON}"' if message == ON else message)
	return message


def report() -> str:
	"""NVDA+Shift+J, then Shift+F11: whether the curtain is on, and whether NVDA turns it on each time it starts."""
	current = curtain()
	if current is None:
		message = NOT_AVAILABLE
	elif not current.enabled:
		message = OFF
	elif current.settings["enabled"]:
		message = ON_AT_EVERY_START
	else:
		message = ON
	_say(message)
	return message


# -- as NVDA starts -----------------------------------------------------------------------------------------------------


def atStart(stateData: dict) -> bool:
	"""From the plugin's start: when NVDA is starting with the curtain on, "Screen curtain on" is said after NVDA says
	where you are. Returns whether it waits for that (the plugin then hands afterFocus its focus events)."""
	global _waiting, _queued, _tries, _keyPressed
	stop()
	if not wanted(stateData):
		return False
	from . import startupFocus

	# NVDA reloading its plugins starts the plugin again, and the curtain was said as NVDA started.
	if not startupFocus.nvdaIsStarting() or not isOn():
		return False
	_waiting, _queued, _tries, _keyPressed = True, False, 0, False
	try:
		_listen()
	except Exception:
		_failure('can\'t say "Screen curtain on" as NVDA starts')
		stop()
		return False
	_note(f'NVDA started with the screen curtain on: "{ON}" is said after NVDA says where you are')
	return True


def isWaiting() -> bool:
	"""Whether the message is still to be said, or said and not heard yet."""
	return _waiting or _queued


def afterFocus() -> bool:
	"""From the plugin's focus event, after NVDA's own: NVDA has queued what it says for the focus, and the message goes
	after it. Returns whether the message is still to be said or heard."""
	if _waiting:
		_queue()
	return isWaiting()


def _listen() -> None:
	global _listening
	import core
	import inputCore
	from speech.extensions import speechCanceled

	core.postNvdaStartup.register(_started)
	inputCore.decide_executeGesture.register(_onGesture)
	speechCanceled.register(_onSpeechCanceled)
	_listening = True


def _queue() -> None:
	global _waiting, _queued, _tries
	if not isOn():
		stop("the screen curtain was turned off before it was said")
		return
	_waiting = False
	import speech
	from speech.commands import CallbackCommand

	_tries += 1
	_queued = True
	# At normal priority: after what NVDA has queued for the window and the focus.
	speech.speak([ON, CallbackCommand(_onSaid, name="jawsMigrator:screenCurtainSaid")], priority=speech.Spri.NORMAL)
	_log().debug(f'jawsMigrator: NVDA says "{ON}" after where you are, as it started with the screen curtain on')


def _started() -> None:
	"""NVDA's postNvdaStartup: NVDA has queued its initial focus, and says it next. NVDA notifies it once; stop takes
	the handler out afterwards, never while NVDA goes through its handlers (see _later)."""
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


def _onSaid(*args, **kwargs) -> None:
	# NVDA's speech manager runs this once the synthesizer has said the message.
	stop("it was said")


def _onGesture(gesture=None, **kwargs) -> bool:
	# Every key NVDA gets comes here first (on NVDA's input thread); the key goes on as always.
	global _keyPressed
	_keyPressed = True
	return True


def _onSpeechCanceled(**kwargs) -> None:
	global _queued, _waiting
	if not _queued:
		return
	_queued = False
	if _keyPressed:
		_later(stop, "a key stopped it")
	elif _tries >= MOST_TRIES:
		_later(stop, f"speech was stopped {_tries} times before it was said")
	else:
		# A window change stopped it: it is said after NVDA says the new focus.
		_waiting = True


def _later(function, *args) -> None:
	"""Run after NVDA's notification: NVDA goes through an extension point's handlers as they are, and a handler taken
	out meanwhile (extensionPoints' unregister) raises "OrderedDict mutated during iteration" there, which would stop
	NVDA's own cancelSpeech. Nothing is said meanwhile: the message is neither waiting nor queued."""
	import wx

	wx.CallAfter(function, *args)


def stop(why: str | None = None) -> None:
	"""Say nothing more about the curtain as NVDA starts (said, stopped, or the plugin ends)."""
	global _waiting, _queued, _listening, _fallbackTimer, _giveUpTimer
	wasWaiting = isWaiting() or _listening
	_waiting = _queued = False
	for timer in (_fallbackTimer, _giveUpTimer):
		try:
			if timer is not None:
				timer.Stop()
		except Exception:
			pass
	_fallbackTimer = _giveUpTimer = None
	if _listening:
		_listening = False
		try:
			import core
			import inputCore
			from speech.extensions import speechCanceled

			core.postNvdaStartup.unregister(_started)
			inputCore.decide_executeGesture.unregister(_onGesture)
			speechCanceled.unregister(_onSpeechCanceled)
		except Exception:
			pass
	if why and wasWaiting:
		_log().debug(f'jawsMigrator: "{ON}" as NVDA started: {why}')
