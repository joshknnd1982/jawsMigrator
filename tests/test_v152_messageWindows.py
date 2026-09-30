# Unit tests for the second follow-up to issue 40 ("Pressing insert V doesn't bring up quick settings for that program"):
# the tester turned "Messages Automatically Read" on with 1.50 and the message he opened was not read again. He wrote:
#   Now I normally have automatically reading turned off. I tested it just to see if it works. it doesn't hear is the log.
# His log (NVDA 2026.2, the assistant 1.50, Outlook First Line Silence 1.0.30, Outlook 2024, 15:48 to 15:51):
# - NVDA started at 15:48:13 with a message open, and made ONE browse mode for the message window ("Adding new treeInterceptor
#   to runningTable", 15:48:18). Each of the six times he opened that message after, Outlook First Line Silence said
#   "armed message-inspector entry suppression" (an opening) and "silencing event_treeInterceptor_gainFocus", and no other
#   browse mode was made: Outlook had hidden the window he closed with Escape and showed it again, and NVDA used its browse
#   mode again.
# - At 15:49:13, the first opening after he turned reading on (15:49:06), the assistant's debug line said: "browse mode came
#   into an Outlook message you read: first time False, read already True, not read from the top". 1.50 took a message to be
#   opening when browse mode came into it for the first time, and that was at NVDA's start; it had marked the message read
#   then, while reading was off. The next openings had no line at all (the line came once for each browse mode).
# - At 15:50:26 he came back to the open message window with Alt+Tab: Outlook First Line Silence said "back in an open message
#   window", which has to stay unread.
# Now a message opening is a message window the assistant did not know was open (outlookMessages.noteForeground, isOpeningWindow).
# The browse mode is the real browse mode event of NVDA 2026.2 (test_v125_outlookMessages), Outlook First Line Silence is
# imitated as in test_v150_quickSettingsFollowUp, and the windows are imitated, except in RealWindowsTests, where user32 is asked
# about real windows. Nothing here ran inside a live NVDA or classic Outlook.
# Run: python -m unittest tests.test_v152_messageWindows -v

import ctypes
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import wx  # noqa: E402

import jawsMigrator  # noqa: E402
import test_v125_outlookMessages as opening  # noqa: E402
import test_v126_outlookOpen as opened  # noqa: E402
import test_v142_quickSettings as qs  # noqa: E402
import test_v150_quickSettingsFollowUp as followUp  # noqa: E402
from jawsMigrator import outlookMessages, state  # noqa: E402

setUpModule = qs.setUpModule

#: The window handles of the imitation: Outlook's main window, a message's window, and the window of the message's text in it.
MAIN, MESSAGE, BODY = 500, 1000, 1001
OTHER, OTHER_BODY = 2000, 2001


class Desktop:
	"""What user32 says of classic Outlook's windows: which are showing, and the top-level window of each window."""

	def __init__(self):
		self.showing = set()
		self.roots = {BODY: MESSAGE, OTHER_BODY: OTHER}

	def patch(self, test):
		for name, value in (
			("_isVisible", lambda window: window in self.showing),
			("_visibleWindows", lambda: sorted(self.showing)),
			("_rootWindow", lambda window: self.roots.get(window, window) if window else 0),
		):
			patcher = mock.patch.object(outlookMessages, name, value)
			patcher.start()
			test.addCleanup(patcher.stop)


class ReopenedMessages(followUp.WithFirstLineSilence):
	"""The tester's session: Outlook's main window, and a message window that Outlook hides when it is closed and shows again,
	with one browse mode all the while."""

	def setUp(self):
		super().setUp()
		self.desk = Desktop()
		self.desk.patch(self)
		self.desk.showing.add(MAIN)
		self.clock = 100.0
		fakeTime = types.SimpleNamespace(monotonic=lambda: self.clock)
		patcher = mock.patch.object(outlookMessages, "time", fakeTime)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.document, self.treeInterceptor, self.focused = self.messageIn(BODY)

	def messageIn(self, body, **kwargs):
		document = opening.Document(**kwargs)
		document.windowHandle = body
		treeInterceptor = self.tree(document)
		focused = types.SimpleNamespace(appModule=document.appModule, treeInterceptor=treeInterceptor, windowHandle=body)
		return document, treeInterceptor, focused

	def foreground(self, window):
		outlookMessages.noteForeground(types.SimpleNamespace(appModule=self.document.appModule, windowHandle=window))

	def enter(self, message=None):
		"""Enter on a message in the list: its window is shown and comes to the front, browse mode comes into the message,
		and the focus event follows."""
		message = message or (MESSAGE, self.treeInterceptor, self.focused)
		window, treeInterceptor, focused = message
		self.desk.showing.add(window)
		self.foreground(window)
		treeInterceptor.event_treeInterceptor_gainFocus()
		outlookMessages.readWhenFocused(focused)

	def escape(self, window=MESSAGE):
		"""Escape in the message: Say All stops, Outlook hides its window, and the main window comes to the front."""
		self.speech.readings.clear()
		self.desk.showing.discard(window)
		self.foreground(MAIN)

	def altTab(self, message=None):
		"""Back to an open message window: it comes to the front, and browse mode comes into it from outside."""
		window, treeInterceptor, focused = message or (MESSAGE, self.treeInterceptor, self.focused)
		self.foreground(window)
		treeInterceptor.event_treeInterceptor_gainFocus()
		outlookMessages.readWhenFocused(focused)

	def settle(self):
		"""The timer of readWhenFocused runs, for a message that was found at its focus event."""
		while self.later:
			_delay, function = self.later.pop(0)
			self.focus = self.focused
			function()

	def readings(self):
		return len(self.heard())


class TheTestersSessionTests(ReopenedMessages):
	def test_aMessageOpenedAgainAndAgainIsReadEachTimeItOpens(self):
		# 15:48:13 NVDA starts with the message open and reading off; he closes it; 15:49:06 he turns reading on.
		self.desk.showing.add(MESSAGE)
		opened.applyAsThePluginDoes(dict(state.DEFAULTS))
		self.addCleanup(outlookMessages.unregister)
		self.treeInterceptor.event_treeInterceptor_gainFocus()
		self.assertEqual(self.readings(), 0, "reading is off")
		self.escape()
		self.turnOnReading()
		self.speech.said.clear()
		self.enter()
		self.assertTrue(self.treeInterceptor._hadFirstGainFocus, "the one browse mode, used before: what 1.50 took for not opening")
		self.assertEqual(self.readings(), 1, "15:49:13: the message he opened is read")
		self.assertEqual(self.dropped, [], "nothing of the reading was dropped")
		self.assertEqual(self.silence.opened, 1)
		self.escape()
		self.enter()
		self.assertEqual(self.readings(), 2, "15:49:32: the next time he opens it")
		self.escape()
		self.enter()
		self.assertEqual(self.readings(), 3, "and the next")
		self.assertEqual(self.later, [], "the focus event had nothing more to read")

	def test_comingBackToTheOpenMessageIsNotReadAgain(self):
		self.turnOnReading()
		self.enter()
		self.assertEqual(self.readings(), 1)
		self.altTab()
		self.altTab()
		self.assertEqual(self.readings(), 1, "15:50:26: back in an open message window")
		self.assertEqual(self.later, [])

	def test_aMessageThatWasOpenWhenNvdaStartedIsNotRead(self):
		self.desk.showing.add(MESSAGE)
		self.turnOnReading()
		self.treeInterceptor.event_treeInterceptor_gainFocus()
		self.altTab()
		self.assertEqual(self.readings(), 0, "it was open before the assistant looked, as at 15:48:18")
		self.escape()
		self.enter()
		self.assertEqual(self.readings(), 1, "but it is read when he opens it again")

	def test_aMessageOpenBeforeReadingWasTurnedOnIsNotRead(self):
		opened.applyAsThePluginDoes(dict(state.DEFAULTS))
		self.addCleanup(outlookMessages.unregister)
		self.enter()
		self.altTab()
		self.assertEqual(self.readings(), 0)
		self.turnOnReading()
		self.altTab()
		self.assertEqual(self.readings(), 0, "it was open when he turned reading on")
		self.escape()
		self.enter()
		self.assertEqual(self.readings(), 1)

	def test_twoMessagesOpenAtOnceAreReadOnceEach(self):
		self.turnOnReading()
		other = self.messageIn(OTHER_BODY)
		second = (OTHER, other[1], other[2])
		self.enter()
		self.enter(second)
		self.assertEqual(self.readings(), 2)
		self.altTab()
		self.altTab(second)
		self.altTab()
		self.assertEqual(self.readings(), 2)
		self.escape(OTHER)
		self.enter(second)
		self.assertEqual(self.readings(), 3)

	def test_aMessageInTheReadingPaneOfTheMainWindowIsNotOneThatOpens(self):
		_document, paneTree, paneFocus = self.messageIn(MAIN)
		self.turnOnReading()
		paneTree.event_treeInterceptor_gainFocus()
		outlookMessages.readWhenFocused(paneFocus)
		self.assertEqual(self.readings(), 0)

	def test_aMessageYouWriteIsNotRead(self):
		self.turnOnReading()
		_document, writeTree, writeFocus = self.messageIn(OTHER_BODY, readOnly=False)
		self.desk.showing.add(OTHER)
		self.foreground(OTHER)
		writeTree.event_treeInterceptor_gainFocus()
		outlookMessages.readWhenFocused(writeFocus)
		self.assertEqual(self.readings(), 0)


class TheOtherWayTests(ReopenedMessages):
	def test_aMessageBrowseModeDidNotHandToTheFirstWayIsReadWhenItTakesTheFocus(self):
		# 1.42's log: event_treeInterceptor_gainFocus was never reached. Only the focus event is.
		self.turnOnReading()
		self.desk.showing.add(MESSAGE)
		self.foreground(MESSAGE)
		self.assertTrue(outlookMessages.readWhenFocused(self.focused))
		self.assertFalse(outlookMessages.readWhenFocused(self.focused), "once")
		self.assertEqual(self.readings(), 0, "after the event, not during it")
		self.settle()
		self.assertEqual(self.readings(), 1)
		self.escape()
		self.desk.showing.add(MESSAGE)
		self.foreground(MESSAGE)
		self.assertTrue(outlookMessages.readWhenFocused(self.focused), "and again when it opens again")

	def test_theFirstWayReadingItLeavesNothingForTheSecond(self):
		self.turnOnReading()
		self.enter()
		self.assertEqual(self.readings(), 1)
		self.assertFalse(outlookMessages.readWhenFocused(self.focused))
		self.assertEqual(self.later, [])

	def test_aWindowNoForegroundEventNotedIsNotedWhenItsMessageTakesTheFocus(self):
		self.turnOnReading()
		self.desk.showing.add(MESSAGE)
		self.treeInterceptor.event_treeInterceptor_gainFocus()
		self.assertEqual(self.readings(), 1)

	def test_theOpeningIsOverAfterAWhile(self):
		self.turnOnReading()
		self.treeInterceptor.passThrough = True
		self.enter()
		self.assertEqual(self.readings(), 0, "focus mode came on as the message opened")
		self.clock += outlookMessages.OPENING_SECONDS + 1
		self.treeInterceptor.passThrough = False
		self.altTab()
		self.assertEqual(self.readings(), 0, "coming back a long while after is not opening it")

	def test_focusModeGoingOffWithinTheOpeningStillReads(self):
		self.turnOnReading()
		self.treeInterceptor.passThrough = True
		self.enter()
		self.clock += 1
		self.treeInterceptor.passThrough = False
		outlookMessages.readWhenFocused(self.focused)
		self.settle()
		self.assertEqual(self.readings(), 1)

	def test_withReadingOffNothingIsTracked(self):
		opened.applyAsThePluginDoes(dict(state.DEFAULTS))
		self.addCleanup(outlookMessages.unregister)
		self.enter()
		self.assertEqual(outlookMessages._windows, {})
		self.assertFalse(outlookMessages.readWhenFocused(self.focused))

	def test_turningReadingOffForgetsTheWindows(self):
		self.turnOnReading()
		self.enter()
		self.assertIn(MESSAGE, outlookMessages._windows)
		opened.applyAsThePluginDoes(dict(state.DEFAULTS))
		self.assertEqual(outlookMessages._windows, {})

	def test_windowsThatAreGoneAreForgottenWhenTheNextWindowComesToTheFront(self):
		self.turnOnReading()
		self.enter()
		self.assertEqual(sorted(outlookMessages._windows), [MAIN, MESSAGE])
		self.desk.showing.discard(MESSAGE)
		self.assertIn(MESSAGE, outlookMessages._windows, "nothing has come to the front yet")
		self.foreground(MAIN)
		self.assertEqual(sorted(outlookMessages._windows), [MAIN])

	def test_aWindowOfAnotherProgramIsNotNoted(self):
		self.turnOnReading()
		outlookMessages.noteForeground(types.SimpleNamespace(appModule=types.SimpleNamespace(appName="notepad"), windowHandle=3000))
		self.assertNotIn(3000, outlookMessages._windows)

	def test_aFailureToListTheWindowsIsLoggedAndNothingMore(self):
		def fails():
			raise OSError("no windows")

		with mock.patch.object(outlookMessages, "_visibleWindows", fails), mock.patch.object(outlookMessages, "_failed", False):
			self.turnOnReading()
		self.assertEqual(outlookMessages._windows, {})
		self.enter()
		self.assertEqual(self.readings(), 1, "a message that opens is read all the same")


class TheRootOfTheBrowseModeIsNotTheWindowTests(ReopenedMessages):
	"""NVDA keeps the browse mode of a message window, made for a root object that may belong to a window Outlook showed before:
	the window of the message is the one the focus is in."""

	def setUp(self):
		super().setUp()
		self.document.windowHandle = 9999  # the window the browse mode was made for: not showing now
		self.desk.roots[9999] = 9999
		self.focus = self.focused

	def test_theWindowTheFocusIsInDecidesWhetherAMessageOpens(self):
		self.turnOnReading()
		self.enter()
		self.assertEqual(self.readings(), 1)
		self.altTab()
		self.assertEqual(self.readings(), 1, "coming back is not opening it")
		self.escape()
		self.enter()
		self.assertEqual(self.readings(), 2)
		self.assertEqual(sorted(outlookMessages._windows), [MAIN, MESSAGE], "the old window is not noted")

	def test_theFocusEventAloneReadsItOnce(self):
		self.turnOnReading()
		self.desk.showing.add(MESSAGE)
		self.foreground(MESSAGE)
		self.assertTrue(outlookMessages.readWhenFocused(self.focused))
		self.assertFalse(outlookMessages.readWhenFocused(self.focused))

	def test_withoutAFocusInTheMessageTheRootObjectIsAsked(self):
		self.focus = types.SimpleNamespace(treeInterceptor=None, windowHandle=MAIN)
		self.assertEqual(outlookMessages.windowOf(self.treeInterceptor), 9999)
		self.focus = None
		self.assertEqual(outlookMessages.windowOf(self.treeInterceptor), 9999)
		with mock.patch.dict(sys.modules, {"api": None}):
			self.assertEqual(outlookMessages.windowOf(self.treeInterceptor), 9999)


class TheDebugLogTests(ReopenedMessages):
	def noted(self, logged):
		return [line for line in logged.output if "browse mode came into an Outlook message you read" in line]

	def test_eachEntryIntoAMessageSaysWhatBecameOfIt(self):
		self.desk.showing.add(MESSAGE)
		self.turnOnReading()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.altTab()
			self.escape()
			self.enter()
			self.clock += 3.5
			self.altTab()
		said = self.noted(logged)
		self.assertEqual(len(said), 3, said)
		self.assertIn("window 0x3e8, open before reading was turned on, not read from the top", said[0])
		self.assertIn("window 0x3e8, open for 0.0 seconds, not read yet, read from the top", said[1])
		self.assertIn("window 0x3e8, open for 3.5 seconds, read already, not read from the top", said[2])

	def test_aNewWindowIsLogged(self):
		self.turnOnReading()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.desk.showing.add(MESSAGE)
			self.foreground(MESSAGE)
		self.assertTrue(any("a window of Outlook, 0x3e8, is new to the assistant: a message in it is read from the top when it opens" in line for line in logged.output), logged.output)

	def test_aWindowTheAssistantDidNotSeeIsSaid(self):
		self.turnOnReading()
		outlookMessages._windows.clear()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			outlookMessages._noteOpening(self.treeInterceptor, False)
		self.assertIn("not known to the assistant, not read from the top", self.noted(logged)[0])

	def test_aBrowseModeWithNoWindowIsNotedOnce(self):
		# Where the window is not known (as in the older tests), it is once for each browse mode, as in 1.50.
		self.turnOnReading()
		_document, bare, _focused = self.messageIn(None)
		with self.assertLogs("nvda", level="DEBUG") as logged:
			bare.event_treeInterceptor_gainFocus()
			bare.event_treeInterceptor_gainFocus()
		said = self.noted(logged)
		self.assertEqual(len(said), 1)
		self.assertIn("first time", said[0])


class PluginTests(unittest.TestCase):
	def plugin(self):
		plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		plugin._sleepApps = set()
		plugin._checkSleep = lambda obj: None
		return plugin

	def test_aWindowComingToTheFrontIsNotedBeforeNvdaHandlesIt(self):
		order = []
		obj = object()
		with mock.patch.object(outlookMessages, "noteForeground", lambda window: order.append(("note", window is obj))):
			self.plugin().event_foreground(obj, lambda: order.append("nvda"))
		self.assertEqual(order, [("note", True), "nvda"])

	def test_aFailureThereNeverStopsTheForegroundEvent(self):
		order = []

		def fails(window):
			raise RuntimeError("no")

		with mock.patch.object(outlookMessages, "noteForeground", fails), mock.patch.object(jawsMigrator.debugLog, "error") as logged:
			self.plugin().event_foreground(object(), lambda: order.append("nvda"))
		self.assertEqual(order, ["nvda"])
		logged.assert_called_once()


class RealWindowsTests(unittest.TestCase):
	"""user32 asked about real windows: the functions the imitation stands in for in the tests above."""

	def setUp(self):
		self.app = wx.GetApp() or wx.App(False)
		self.frame = wx.Frame(None, title="a message")
		self.body = wx.Panel(self.frame)
		self.addCleanup(self.frame.Destroy)
		self.window = self.frame.GetHandle()
		buffer = ctypes.create_unicode_buffer(256)
		outlookMessages._user32().GetClassNameW(self.window, buffer, 256)
		patcher = mock.patch.object(outlookMessages, "WINDOW_CLASS", buffer.value)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_theTopLevelWindowOfAChildWindow(self):
		self.assertEqual(outlookMessages._rootWindow(self.body.GetHandle()), self.window)
		self.assertEqual(outlookMessages._rootWindow(self.window), self.window)
		self.assertEqual(outlookMessages._rootWindow(0), 0)
		self.assertEqual(outlookMessages._rootWindow(None), 0)

	def test_aWindowThatIsHiddenIsNotShowing(self):
		self.frame.Show()
		qs.pump()
		self.assertTrue(outlookMessages._isVisible(self.window))
		self.frame.Hide()
		qs.pump()
		self.assertFalse(outlookMessages._isVisible(self.window))

	def test_theWindowsOfOutlookThatAreShowing(self):
		self.frame.Show()
		qs.pump()
		self.assertIn(self.window, outlookMessages._visibleWindows())
		self.frame.Hide()
		qs.pump()
		self.assertNotIn(self.window, outlookMessages._visibleWindows())

	def test_aWindowOfAnotherClassIsNotOneOfOutlook(self):
		self.frame.Show()
		qs.pump()
		with mock.patch.object(outlookMessages, "WINDOW_CLASS", "rctrl_renwnd32"):
			self.assertNotIn(self.window, outlookMessages._visibleWindows())

	def test_windowsOpenWhenReadingIsTurnedOnAreKnownAndTheRestIsForgotten(self):
		self.frame.Show()
		qs.pump()
		with mock.patch.object(outlookMessages, "_windows", {12345: outlookMessages._Window(1.0, True)}):
			outlookMessages._noteOpenWindows()
			known = outlookMessages._windows
			self.assertIn(self.window, known)
			self.assertNotIn(12345, known)
			self.assertFalse(known[self.window].unread)
			self.assertEqual(known[self.window].seen, float("-inf"))

	def test_theAssistantsCopyOfUser32LeavesNvdasAlone(self):
		self.assertIsNot(outlookMessages._user32(), ctypes.windll.user32)

	def test_whenVisibilityCannotBeToldAMessageIsNotReadAgain(self):
		# An error asking user32: the window counts as showing, and is its own top-level window.
		with mock.patch.object(outlookMessages, "_user32", side_effect=OSError("no user32")):
			self.assertTrue(outlookMessages._isVisible(self.window))
			self.assertEqual(outlookMessages._rootWindow(self.body.GetHandle()), self.body.GetHandle())


if __name__ == "__main__":
	unittest.main()
