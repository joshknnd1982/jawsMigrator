# Unit tests for version 1.43, from issue 41, "Should we have a starting announcement when NVDA starts?"
# The tester: "This is what Jaws says when it starts. Of course this should be a check box just like the exiting NVDA.
# Double check me. to see if I'm missing something." What JAWS said was "JAWS". The project's owner: "yes. It should say
# "NVDA is ready." And that announcement should not be interruptable by the user."
# - NVDA says "NVDA is ready." as it starts, after it says where you are, once (StartupTests). NVDA 2026.2's own speech
#   manager, speak, cancelSpeech, doPreGainFocus and NVDAObject.event_foreground run here (test_v133_tabSwitch's, word for
#   word there), with Outlook in front as in test_v139_screenShade, and the assistant's own plugin handling the focus event
#   where NVDA hands it to global plugins. What is imitated: the synthesizer (the test says when it reaches each index),
#   wx's timers, and NVDA's start.
# - Nothing stops it while it is said: a key pressed (NVDA queues speech.cancelSpeech for it) or a window change
#   (NVDAObject.event_foreground) meanwhile leaves the synthesizer saying it; NVDA's speech stops as always before and after
#   (UninterruptibleTests). A stop that comes before the synthesizer has started on it has it queued again.
# - It is a check box, on as the assistant comes (SettingTests); JAWS 2026 has no setting for what it says as it starts,
#   so a migration has nothing to take (JawsTests, checked where JAWS 2026 is installed).
# Run: python -m unittest tests.test_v143_startMessage -v

import inspect
import os
import re
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
import test_v129_speechHistory as v129  # noqa: E402
from jawsMigrator import settingsMap, startMessage, startupFocus  # noqa: E402
from test_v137_exitMessage import Decider, Wx  # noqa: E402
from test_v139_screenShade import JAWS_SCRIPTS, needsJaws  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MESSAGE = ["NVDA is ready."]


class ReadyCase(unittest.TestCase):
	"""NVDA 2026.2 starting in the tester's Outlook, with the assistant's own plugin."""

	def setUp(self):
		import test_v133_tabSwitch as v133

		tab = v133.TabCase("run")
		tab.setUp()
		self.addCleanup(tab.doCleanups)
		self.tab = tab
		self.nvda = nvda = tab.nvda
		# As core._initializeObjectCaches leaves it before NVDA's first focus: the desktop is the foreground and the focus.
		nvda.globalVars.foregroundObject = tab.desktop
		nvda.globalVars.focusObject = tab.desktop
		nvda.globalVars.focusAncestors = []
		nvda.globalVars.focusDifferenceLevel = 0
		tab.foreground = tab.outlook
		self.wx = Wx()
		self.core = types.ModuleType("core")
		self.core.postNvdaStartup = type(nvda.extensions.pre_speech)()
		self.curtain = types.SimpleNamespace(enabled=False, settings={"enabled": False, "warnOnLoad": True, "playToggleSounds": False})
		package = types.ModuleType("screenCurtain")
		package.screenCurtain = self.curtain
		# NVDA's speech package, as the assistant finds NVDA's functions: by the package's attributes, when it needs them.
		self.speech = speech = types.ModuleType("speech")
		speech.speak = nvda.speak
		speech.cancelSpeech = nvda.cancelSpeech
		speech.Spri = nvda.priorities.Spri
		speech.getState = lambda: nvda.base.speechState
		speech.SpeechMode = v129.SpeechMode
		speech._manager = nvda.manager
		#: What NVDA's speech.pauseSpeech was asked, for the Shift key (pause) and for the next Shift (resume).
		self.paused = []
		self.nvdaPause = speech.pauseSpeech = lambda switch: self.paused.append(bool(switch))
		inputCore = sys.modules["inputCore"]
		self.decider = Decider()
		# NVDA's event_foreground stops speech through the package's attribute, whatever it is at that time.
		self.stoppedBy = []
		nvda.synth.name = "sapi5"
		self.synthCancels = []
		synthCancel = nvda.synth.cancel

		def cancel():
			self.synthCancels.append(True)
			synthCancel()

		nvda.synth.cancel = cancel
		patches = (
			mock.patch.dict(
				sys.modules,
				{
					"wx": self.wx,
					"core": self.core,
					"screenCurtain": package,
					"speech": speech,
					"speech.extensions": nvda.extensions,
					"speech.commands": nvda.commands,
				},
			),
			mock.patch.object(inputCore, "decide_executeGesture", self.decider, create=True),
			mock.patch.object(startupFocus, "nvdaIsStarting", lambda: self.starting),
			mock.patch.object(jawsMigrator.state, "load", lambda: dict(self.stateData)),
			mock.patch.object(v133.objectSpeech, "cancelSpeech", lambda: speech.cancelSpeech(), create=True),
		)
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		self.addCleanup(startMessage.stop)
		self.starting = True
		self.stateData = {}
		self.plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		self.plugin._sleepApps = set()
		self.plugin._changeRepeats = None
		self.plugin._screenShade = None
		self.plugin._startMessage = None
		self.othersHeard = []
		self.otherStarted = lambda: self.othersHeard.append("postNvdaStartup")
		self.otherCanceled = lambda: self.othersHeard.append("speechCanceled")

	# -- NVDA's start ----------------------------------------------------------------------------------------------------

	def startPlugin(self):
		"""The plugin's start: NVDA starts its global plugins before it queues its first focus. Another add-on started after
		the assistant registers for the same notices, after the assistant's handlers."""
		self.plugin._readyAtStart()
		self.plugin._screenCurtainAtStart()
		self.core.postNvdaStartup.register(self.otherStarted)
		self.nvda.extensions.speechCanceled.register(self.otherCanceled)

	def focusEvent(self, obj):
		"""NVDA's eventHandler.executeEvent for a focus event: doPreGainFocus (with the foreground event of a new window),
		then the global plugins' handlers, the assistant's first, around the object's own."""
		if self.nvda.eventHandler.doPreGainFocus(obj):
			self.plugin.event_gainFocus(obj, obj.event_gainFocus)

	def startNvda(self):
		"""NVDA's start: plugins, then its first focus (core._setInitialFocus), then postNvdaStartup."""
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.core.postNvdaStartup.notify()

	# -- the synthesizer -------------------------------------------------------------------------------------------------

	def heard(self):
		self.nvda.synth.finish()
		return self.nvda.synth.heard()

	def said(self, heard=None) -> int:
		return sum(utterance == MESSAGE for utterance in (self.nvda.synth.heard() if heard is None else heard))

	def sayUntilTheMessageIsNext(self):
		"""The synthesizer says what NVDA's speech manager gave it before the message, so the manager gives it the message."""
		synth = self.nvda.synth
		for _ in range(50):
			if synth._unfinished and synth.heard()[-1] == MESSAGE:
				return
			self.assertTrue(synth._unfinished, "the message never reached the synthesizer")
			for index in synth._unfinished.pop(0):
				self.nvda.synthDriverHandler.synthIndexReached.notify(synth=synth, index=index)
			self.nvda.synthDriverHandler.synthDoneSpeaking.notify(synth=synth)
		self.fail("the synthesizer never got to the message")

	def reachTheStart(self):
		"""The synthesizer starts on the message: it reaches the index at its start, as a synthesizer does."""
		synth = self.nvda.synth
		self.assertEqual(synth.heard()[-1], MESSAGE)
		index = synth._unfinished[0].pop(0)
		self.nvda.synthDriverHandler.synthIndexReached.notify(synth=synth, index=index)

	def keyPressed(self):
		"""A key: NVDA queues speech.cancelSpeech for it, looked up in NVDA's speech package as it runs."""
		self.speech.cancelSpeech()

	def handlers(self, action) -> list:
		return list(action.handlers)


class StartupTests(ReadyCase):
	def test_saidAfterWhereYouAre(self):
		self.startNvda()
		heard = self.heard()
		self.assertEqual(heard[0][0], "Inbox - Outlook - Outlook", "NVDA's own first words, as in the tester's log")
		self.assertEqual(heard[-1], MESSAGE)
		self.assertEqual(self.said(heard), 1)
		self.assertFalse(startMessage.isWaiting(), "said, and done")
		self.assertFalse(startMessage.isHolding())
		# The plugin's next focus event finds it done, and no focus event goes to it after that.
		self.focusEvent(self.tab.message)
		self.assertIsNone(self.plugin._startMessage)
		self.assertEqual(self.said(self.heard()), 1)
		self.assertEqual(self.handlers(self.core.postNvdaStartup), [self.otherStarted], "the other add-on's stays")
		self.assertEqual(self.handlers(self.nvda.extensions.speechCanceled), [self.otherCanceled])

	def test_theWordsAreTheOwnersAndPlain(self):
		self.assertEqual(startMessage.MESSAGE, "NVDA is ready.")
		self.startNvda()
		self.assertEqual(self.heard()[-1], ["NVDA is ready."])

	def test_notWhenTurnedOff(self):
		self.stateData = {startMessage.STATE_KEY: False}
		self.startNvda()
		heard = self.heard()
		self.assertEqual(heard[0][0], "Inbox - Outlook - Outlook")
		self.assertEqual(self.said(heard), 0)
		self.assertIsNone(self.plugin._startMessage)
		self.assertEqual(self.handlers(self.core.postNvdaStartup), [self.otherStarted])

	def test_notWhenNvdaReloadsItsPlugins(self):
		self.starting = False
		self.startNvda()
		self.assertEqual(self.said(self.heard()), 0)
		self.assertEqual(self.handlers(self.core.postNvdaStartup), [self.otherStarted])
		self.assertEqual(self.handlers(self.nvda.extensions.speechCanceled), [self.otherCanceled])

	def test_withoutAFocusEventItIsSaidAfterNvdaStarted(self):
		# NVDA gives global plugins no focus event in a program in sleep mode.
		self.startPlugin()
		self.core.postNvdaStartup.notify()
		self.assertEqual(self.othersHeard, ["postNvdaStartup"], "NVDA's notification went on to the other add-on")
		fallback = [timer for timer in self.wx.timers if timer.milliseconds == startMessage.FALLBACK_MS]
		self.assertEqual(len(fallback), 1)
		fallback[0].fire()
		self.assertEqual(self.heard(), [MESSAGE])

	def test_theFallbackWaitsForTheFocus(self):
		self.startNvda()
		for timer in list(self.wx.timers):
			timer.fire()
		self.assertEqual(self.said(self.heard()), 1)

	def test_givesUpAfterThirtySeconds(self):
		self.startPlugin()
		self.core.postNvdaStartup.notify()
		giveUp = [timer for timer in self.wx.timers if timer.milliseconds == startMessage.GIVE_UP_MS]
		giveUp[0].fire()
		self.assertFalse(startMessage.isWaiting())
		self.focusEvent(self.tab.message)
		self.assertEqual(self.said(self.heard()), 0)
		self.assertEqual(self.handlers(self.core.postNvdaStartup), [self.otherStarted])

	def test_thePluginsEndStopsIt(self):
		self.startPlugin()
		self.assertIs(self.plugin._startMessage, startMessage)
		self.assertIn("startMessage.stop()", inspect.getsource(jawsMigrator.GlobalPlugin.terminate))
		startMessage.stop()
		self.assertFalse(startMessage.isWaiting())
		self.assertEqual(self.handlers(self.core.postNvdaStartup), [self.otherStarted])
		self.assertEqual(self.handlers(self.nvda.extensions.speechCanceled), [self.otherCanceled])

	def test_notWhereSpeechIsOffOrBeeps(self):
		for mode in (v129.SpeechMode.off, v129.SpeechMode.beeps):
			with self.subTest(mode=mode.name):
				startMessage.stop()
				self.nvda.base.speechState.speechMode = mode
				self.plugin._startMessage = None
				self.startPlugin()
				self.focusEvent(self.tab.message)
				self.assertFalse(startMessage.isWaiting())
				self.assertNotIn(MESSAGE, self.nvda.synth.heard())
				self.assertFalse(startMessage.isHolding())
		self.nvda.base.speechState.speechMode = v129.SpeechMode.talk

	def test_notWithASilentSynthesizer(self):
		self.nvda.synth.name = "silence"
		self.startNvda()
		self.assertNotIn(MESSAGE, self.heard())
		self.assertFalse(startMessage.isWaiting())
		self.assertEqual(self.handlers(self.core.postNvdaStartup), [self.otherStarted])

	def test_eachReasonNothingWouldBeHeard(self):
		# NVDA's speak stops a pause (speech.speak: "if _speechState.isPaused: cancelSpeech()"), so by the time the message is
		# queued, after NVDA has said where you are, speech is not paused; the reasons are checked here as they are asked.
		state = self.nvda.base.speechState
		self.assertIsNone(startMessage._whyNotSaid())
		for mode in (v129.SpeechMode.off, v129.SpeechMode.beeps, v129.SpeechMode.onDemand):
			state.speechMode = mode
			self.assertEqual(startMessage._whyNotSaid(), f"speech mode is {mode.name}")
		state.speechMode = v129.SpeechMode.talk
		state.isPaused = True
		self.assertEqual(startMessage._whyNotSaid(), "speech is paused")
		state.isPaused = False
		self.nvda.synth.name = "silence"
		self.assertEqual(startMessage._whyNotSaid(), "no synthesizer speaks")
		self.nvda.synth.name = "sapi5"
		with mock.patch.object(self.nvda.synthDriverHandler, "getSynth", lambda: None):
			self.assertEqual(startMessage._whyNotSaid(), "no synthesizer speaks")
		self.assertIsNone(startMessage._whyNotSaid())

	def test_beforeTheScreenCurtainMessage(self):
		self.curtain.enabled = True
		self.startNvda()
		heard = self.heard()
		self.assertEqual(heard[-2:], [MESSAGE, ["Screen curtain on"]], "NVDA is ready, then the curtain")
		self.assertEqual(self.said(heard), 1)

	def test_itsFailureLeavesNvdasFocusEventAlone(self):
		self.startPlugin()
		with mock.patch.object(self.speech, "speak", side_effect=RuntimeError("no speech")):
			self.focusEvent(self.tab.message)
		self.assertFalse(startMessage.isWaiting())
		self.assertFalse(startMessage.isHolding())
		self.assertEqual(self.handlers(self.core.postNvdaStartup), [self.otherStarted])
		self.assertIs(self.speech.cancelSpeech, self.nvda.cancelSpeech)

	def test_theMessageCarriesNoMoreThanTheWords(self):
		# Two callbacks around the words: the first runs when the synthesizer starts on them, the second when it has said them.
		self.startPlugin()
		self.focusEvent(self.tab.message)
		given = self.nvda.synth.given
		self.sayUntilTheMessageIsNext()
		utterance = given[-1]
		commands = self.nvda.commands
		self.assertEqual([type(item).__name__ for item in utterance], ["IndexCommand", "str", "IndexCommand"])
		self.assertTrue(all(isinstance(item, (commands.IndexCommand, str)) for item in utterance))


class UninterruptibleTests(ReadyCase):
	def test_aKeyPressedWhileItIsSaidDoesNotStopIt(self):
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.sayUntilTheMessageIsNext()
		self.reachTheStart()
		self.assertTrue(startMessage.isHolding())
		self.synthCancels.clear()
		self.keyPressed()
		self.assertEqual(self.synthCancels, [], "the synthesizer went on saying it")
		self.assertEqual(self.nvda.synth._unfinished, [[self.nvda.synth._unfinished[0][0]]], "the end of the message is still to come")
		heard = self.heard()
		self.assertEqual(heard[-1], MESSAGE)
		self.assertEqual(self.said(heard), 1)
		self.assertFalse(startMessage.isHolding())
		self.assertFalse(startMessage.isWaiting())

	def test_severalKeysAndTheEndOfTheMessage(self):
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.sayUntilTheMessageIsNext()
		self.reachTheStart()
		self.synthCancels.clear()
		for _ in range(5):
			self.keyPressed()
		self.assertEqual(self.synthCancels, [])
		self.assertEqual(self.said(self.heard()), 1)

	def test_shiftDoesNotPauseIt(self):
		# NVDA pauses speech for the Shift key and lets it go on for the next one (inputCore: speech.pauseSpeech).
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.sayUntilTheMessageIsNext()
		self.reachTheStart()
		self.speech.pauseSpeech(True)
		self.assertEqual(self.paused, [], "not paused while it is said")
		self.speech.pauseSpeech(False)
		self.assertEqual(self.paused, [False], "letting speech go on is NVDA's, as always")
		self.speech.pauseSpeech(switch=True)
		self.assertEqual(self.paused, [False])
		self.assertEqual(self.said(self.heard()), 1)
		self.speech.pauseSpeech(True)
		self.assertEqual(self.paused, [False, True], "Shift pauses speech as always once the message is said")
		self.assertIs(self.speech.pauseSpeech, self.nvdaPause)

	def test_bothOfNvdasFunctionsAreBackOnceItIsSaid(self):
		self.startNvda()
		self.heard()
		self.assertIs(self.speech.cancelSpeech, self.nvda.cancelSpeech)
		self.assertIs(self.speech.pauseSpeech, self.nvdaPause)

	def test_aWindowChangeWhileItIsSaidDoesNotStopIt(self):
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.sayUntilTheMessageIsNext()
		self.reachTheStart()
		self.synthCancels.clear()
		# Edge came to the front: its foreground event stops NVDA's speech (NVDAObject.event_foreground), then NVDA says it.
		self.tab.window.name = "GitHub - Microsoft Edge"
		self.tab.foreground = self.tab.window
		self.focusEvent(self.tab.commentBox)
		self.assertEqual(self.synthCancels, [], "the window's foreground event didn't stop the message")
		heard = self.heard()
		self.assertEqual(self.said(heard), 1)
		message = heard.index(MESSAGE)
		self.assertTrue(any("GitHub" in " ".join(utterance) for utterance in heard[message + 1 :]), "and the window is said after it")

	def test_nobodyIsToldOfAStopThatDidNotHappen(self):
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.sayUntilTheMessageIsNext()
		self.reachTheStart()
		self.othersHeard.clear()
		before = []
		self.nvda.extensions.pre_speechCanceled.register(lambda: before.append(True))
		self.keyPressed()
		self.assertEqual(self.othersHeard, [])
		self.assertEqual(before, [])

	def test_whatAKeySaysComesAfterIt(self):
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.sayUntilTheMessageIsNext()
		self.reachTheStart()
		self.keyPressed()
		self.nvda.speak(["a"])
		heard = self.heard()
		self.assertEqual(heard[-2:], [MESSAGE, ["a"]])

	def test_nvdasSpeechStopsAsAlwaysOnceItIsSaid(self):
		self.startNvda()
		self.heard()
		self.assertIs(self.speech.cancelSpeech, self.nvda.cancelSpeech, "NVDA's own function is back")
		self.nvda.speak(["Something else"])
		self.synthCancels.clear()
		self.keyPressed()
		self.assertEqual(self.synthCancels, [True], "a key stops speech as always")

	def test_nvdasSpeechStopsAsAlwaysBeforeItStarts(self):
		# Where the focus is still being said, a key stops that, as it always does; the message isn't held yet.
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.assertFalse(startMessage.isHolding(), "other speech is being said first")
		self.assertIs(self.speech.cancelSpeech, self.nvda.cancelSpeech)
		self.synthCancels.clear()
		self.keyPressed()
		self.assertEqual(self.synthCancels, [True])

	def test_heldFromTheStartWhereNothingWasWaiting(self):
		# No focus event: the message goes to an idle synthesizer, which starts on it at once.
		self.startPlugin()
		self.core.postNvdaStartup.notify()
		[timer for timer in self.wx.timers if timer.milliseconds == startMessage.FALLBACK_MS][0].fire()
		self.assertTrue(startMessage.isHolding())
		self.keyPressed()
		self.assertEqual(self.synthCancels, [])
		self.assertEqual(self.heard(), [MESSAGE])
		self.assertFalse(startMessage.isHolding())

	def test_heldOnceTheSynthesizerStartsOnItWhereOtherSpeechCameFirst(self):
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.assertFalse(startMessage.isHolding())
		self.sayUntilTheMessageIsNext()
		self.assertFalse(startMessage.isHolding(), "the synthesizer has it, and hasn't started on it")
		self.reachTheStart()
		self.assertTrue(startMessage.isHolding())
		self.assertIsNot(self.speech.cancelSpeech, self.nvda.cancelSpeech, "the assistant's takes NVDA's place")

	def test_stoppedBeforeItStartsItIsQueuedAgain(self):
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.assertTrue(startMessage.isWaiting())
		# A key stopped the focus, and with it the message NVDA had yet to say.
		self.keyPressed()
		self.assertEqual(self.said(), 0)
		self.wx.runPending()
		retry = [timer for timer in self.wx.timers if timer.milliseconds == startMessage.RETRY_MS and timer.running]
		self.assertEqual(len(retry), 1)
		self.assertTrue(startMessage.isWaiting(), "still to be said")
		retry[0].fire()
		heard = self.heard()
		self.assertEqual(self.said(heard), 1)
		self.assertFalse(startMessage.isWaiting())
		self.assertIn("speechCanceled", self.othersHeard, "the other add-on was told of the stop NVDA made")

	def test_aWindowChangeBeforeItStartsQueuesItAgainAfterTheWindow(self):
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.tab.window.name = "GitHub - Microsoft Edge"
		self.tab.foreground = self.tab.window
		self.focusEvent(self.tab.commentBox)
		self.wx.runPending()
		[timer for timer in self.wx.timers if timer.milliseconds == startMessage.RETRY_MS and timer.running][0].fire()
		heard = self.heard()
		self.assertEqual(self.said(heard), 1)
		self.assertEqual(heard[-1], MESSAGE, "after the new window and its focus")

	def test_stoppedTooOften(self):
		self.startPlugin()
		self.focusEvent(self.tab.message)
		for attempt in range(startMessage.MOST_TRIES):
			self.keyPressed()
			self.wx.runPending()
			retry = [timer for timer in self.wx.timers if timer.milliseconds == startMessage.RETRY_MS and timer.running]
			if attempt < startMessage.MOST_TRIES - 1:
				self.assertEqual(len(retry), 1, f"try {attempt + 2}")
				# NVDA is saying something else when the message is queued again, so the synthesizer is not on it yet.
				self.nvda.speak(["Something else"])
				retry[0].fire()
				self.assertFalse(startMessage.isHolding())
			else:
				self.assertEqual(retry, [], "no more tries")
		self.assertFalse(startMessage.isWaiting())
		self.wx.runPending()
		self.assertEqual(self.handlers(self.nvda.extensions.speechCanceled), [self.otherCanceled], "the assistant's handler is gone")
		self.assertEqual(self.said(), 0, "stopped every time: never heard")

	def test_theHoldEndsAfterTheLongestWhenTheSynthesizerNeverFinishes(self):
		self.startPlugin()
		self.core.postNvdaStartup.notify()
		[timer for timer in self.wx.timers if timer.milliseconds == startMessage.FALLBACK_MS][0].fire()
		self.assertTrue(startMessage.isHolding())
		hold = [timer for timer in self.wx.timers if timer.milliseconds == startMessage.LONGEST_HOLD]
		self.assertEqual(len(hold), 1)
		self.keyPressed()
		self.assertEqual(self.synthCancels, [])
		hold[0].fire()
		self.assertFalse(startMessage.isHolding())
		self.assertIs(self.speech.cancelSpeech, self.nvda.cancelSpeech)
		self.assertIs(self.speech.pauseSpeech, self.nvdaPause)
		self.keyPressed()
		self.assertEqual(self.synthCancels, [True], "a key stops speech as always")
		self.assertFalse(startMessage.isWaiting())

	def test_theHoldTimerIsStoppedWhenItIsSaid(self):
		self.startNvda()
		self.heard()
		hold = [timer for timer in self.wx.timers if timer.milliseconds == startMessage.LONGEST_HOLD]
		self.assertEqual(len(hold), 1)
		self.assertFalse(hold[0].running)
		for timer in self.wx.timers:
			self.assertFalse(timer.running, f"{timer.milliseconds} ms timer left running")

	def test_aStopThatReachesNvdasFunctionAnywayQueuesItAgain(self):
		# Something with NVDA's own cancelSpeech in hand (imported by name) stops speech, and the message with it.
		self.startPlugin()
		self.core.postNvdaStartup.notify()
		[timer for timer in self.wx.timers if timer.milliseconds == startMessage.FALLBACK_MS][0].fire()
		self.assertTrue(startMessage.isHolding())
		self.nvda.cancelSpeech()
		self.wx.runPending()
		self.assertFalse(startMessage.isHolding(), "it was stopped, so it isn't held")
		[timer for timer in self.wx.timers if timer.milliseconds == startMessage.RETRY_MS and timer.running][0].fire()
		self.assertEqual(self.said(self.heard()), 2, "cut off once, then said")

	def test_anotherAddonsWrapperStaysAndDoesNothingAfterwards(self):
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.sayUntilTheMessageIsNext()
		self.reachTheStart()
		import functools

		assistants = self.speech.cancelSpeech

		@functools.wraps(assistants)
		def theirs(*args, **kwargs):
			return assistants(*args, **kwargs)

		self.speech.cancelSpeech = theirs
		self.synthCancels.clear()
		self.keyPressed()
		self.assertEqual(self.synthCancels, [], "still held through their wrapper")
		self.heard()
		self.assertIs(self.speech.cancelSpeech, theirs, "theirs is not taken out")
		self.synthCancels.clear()
		self.keyPressed()
		self.assertEqual(self.synthCancels, [True], "and, with nothing held, NVDA's speech stops as always")

	def test_theWrapperIsRecognizedAndKeepsNvdasName(self):
		self.startPlugin()
		self.core.postNvdaStartup.notify()
		[timer for timer in self.wx.timers if timer.milliseconds == startMessage.FALLBACK_MS][0].fire()
		wrapper = self.speech.cancelSpeech
		self.assertTrue(startMessage._isOurs(wrapper))
		self.assertEqual(wrapper.__name__, "cancelSpeech")
		self.assertIs(wrapper.__wrapped__, self.nvda.cancelSpeech)
		self.assertIs(getattr(wrapper, startMessage.ORIGINAL), self.nvda.cancelSpeech)
		self.assertFalse(startMessage._isOurs(self.nvda.cancelSpeech))
		pause = self.speech.pauseSpeech
		self.assertTrue(startMessage._isOurs(pause))
		self.assertEqual(pause.__name__, "<lambda>", "named as NVDA's function is")
		self.assertIs(pause.__wrapped__, self.nvdaPause)

	def test_startingAgainReleasesEverything(self):
		self.startPlugin()
		self.core.postNvdaStartup.notify()
		[timer for timer in self.wx.timers if timer.milliseconds == startMessage.FALLBACK_MS][0].fire()
		self.assertTrue(startMessage.isHolding())
		self.starting = False
		self.assertFalse(startMessage.atStart({}))
		self.assertFalse(startMessage.isHolding())
		self.assertIs(self.speech.cancelSpeech, self.nvda.cancelSpeech)
		self.assertIs(self.speech.pauseSpeech, self.nvdaPause)
		self.assertFalse(startMessage.isWaiting())


class SettingTests(unittest.TestCase):
	def test_theCheckBoxIsOnAsItComes(self):
		self.assertTrue(startMessage.wanted({}))
		self.assertTrue(startMessage.wanted({startMessage.STATE_KEY: True}))
		self.assertFalse(startMessage.wanted({startMessage.STATE_KEY: False}))
		self.assertFalse(startMessage.wanted(None))
		self.assertIs(jawsMigrator.state.DEFAULTS[startMessage.STATE_KEY], True)
		self.assertEqual(startMessage.STATE_KEY, "sayNvdaReady")

	def test_aMigrationLeavesItAlone(self):
		# JAWS 2026 has no setting for it, so nothing in a migration reads or writes it.
		for name in ("settingsMap.py", "migrator.py"):
			path = os.path.join(ROOT, "addon", "globalPlugins", "jawsMigrator", name)
			with open(path, encoding="utf-8") as stream:
				self.assertNotIn("startMessage", stream.read(), name)
		self.assertTrue(hasattr(settingsMap, "ASSISTANT"))

	def test_thePluginStartsItBeforeTheCurtainAndHandsItTheFocusFirst(self):
		with open(os.path.join(ROOT, "addon", "globalPlugins", "jawsMigrator", "__init__.py"), encoding="utf-8") as stream:
			source = stream.read()
		self.assertIn("self._readyAtStart),\n\t\t\t(\"say that the screen curtain is on when NVDA starts with it on\", self._screenCurtainAtStart)", source)
		self.assertLess(source.index("startMessage.afterFocus()"), source.index("screenShade.afterFocus()"))
		self.assertIn("self._startMessage = None\n\t\ttry:\n\t\t\tfrom . import startMessage\n\n\t\t\tstartMessage.stop()", source)

	def test_theDocsSayWhatItDoes(self):
		# Whatever number the release has: the manifest and the README agree on it, and both tell of this.
		with open(os.path.join(ROOT, "addon", "manifest.ini"), encoding="utf-8") as stream:
			manifest = stream.read()
		version = re.search(r"^version = (\S+)", manifest, re.M).group(1)
		changelog = manifest.split('changelog = """', 1)[1]
		entries = [entry for entry in re.split(r"(?m)^Version ", changelog) if "issue 41" in entry]
		self.assertEqual(len(entries), 1, "one version's changelog tells of issue 41")
		self.assertIn("NVDA is ready.", entries[0])
		self.assertIn("don't let a key stop it", entries[0])
		with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as stream:
			readme = stream.read()
		self.assertIn(f"- Version: {version}\n", readme)
		self.assertIn(f"jawsMigrator-{version}.nvda-addon", readme)
		sections = [section for section in re.split(r"(?m)^## ", readme) if section.startswith("What's new in ") and "issue 41" in section]
		self.assertEqual(len(sections), 1)
		self.assertIn("NVDA is ready.", sections[0])
		self.assertIn("interruptable", sections[0])
		self.assertIn("Shift", sections[0])
		self.assertRegex(readme, r"- saying \"NVDA is ready\.\" when NVDA starts")


class JawsTests(unittest.TestCase):
	@staticmethod
	def autoStartEvent(path):
		with open(path, encoding="latin-1") as stream:
			source = stream.read().replace("\r\n", "\n")
		match = re.search(r"function\s+autoStartEvent\s*\(\s*\)\n(.*?)\nendFunction", source, re.I | re.S)
		return match.group(1) if match else None

	@needsJaws
	def test_noJawsScriptSaysItAsJawsStarts(self):
		for name in ("Default.JSS", "JAWS Window.JSS"):
			body = self.autoStartEvent(os.path.join(JAWS_SCRIPTS, name))
			self.assertIsNotNone(body, name)
			self.assertNotRegex(body, r"(?i)SayFormattedMessage|SayMessage|cwn10|\"JAWS\"", name)

	@needsJaws
	def test_jawsHasNoSettingForIt(self):
		settings = os.path.join(os.path.dirname(JAWS_SCRIPTS), "SETTINGS", "enu", "default.jcf")
		with open(settings, encoding="latin-1") as stream:
			options = [line.split("=", 1)[0].strip() for line in stream if "=" in line and not line.lstrip().startswith(";")]
		self.assertFalse([name for name in options if re.search(r"(?i)(announce|say|speak).*(start|launch)|(start|launch).*(announce|say|speak|message)", name)], "an option for what JAWS says as it starts")


if __name__ == "__main__":
	unittest.main()
