# Unit tests for the follow-up to issue 40 ("Pressing insert V doesn't bring up quick settings for that program"), from the
# tester's answer to the first QuickSettings (1.42), with his NVDA log (NVDA 2026.2, the assistant 1.42, Outlook First Line
# Silence 1.0.30, Outlook 2024):
#   This doesn't work. A few observations. I changed it to automatically read a message it didn't. Also with Jaws pressing
#   spacebar on something will toggle that choice. I had to tab in NVDA's implementation.
# What his log showed:
# - Space on "Messages Automatically Read: not checked" in the tree did nothing (12:10:3x: Space, Down Arrow, Enter, Right
#   Arrow, then Tab to the check box and Space there: "checked"). JAWS's tree toggles the setting with Space. Now Space does,
#   and on a setting with several choices it goes to the next. SpaceInTheTreeTests.
# - The setting was saved (quick settings: the assistant's readOutlookMessagesOnOpen = True; the read-on-open hook went in
#   at 12:10:39), yet the message he opened at 12:10:45 was not read. The log shows Outlook First Line Silence silencing
#   the message's opening (event_treeInterceptor_gainFocus) and dropping the speech of it, the same lines as before the
#   setting was on, and no "an Outlook message you opened is read from the top". That add-on drops everything said for 1.5
#   seconds after a message opened (its trailing gate), so the start of Say All would have been dropped too; and the
#   assistant's hook did not show that it ran. Now: the assistant opens that add-on's gate before it reads the message; a
#   message that took the focus and wasn't read as browse mode came into it is read when it takes the focus; and the debug
#   log says what became of each message. ReadingOnOpenTests.
# Opening a message runs NVDA 2026.2's own browse mode code (the imitation of test_v125_outlookMessages); Outlook First
# Line Silence is imitated as it acts in the log: its wrapper around NVDA's event drops speech afterwards for a while, and
# its module lets speech through again. Nothing here ran inside a live NVDA or classic Outlook.
# Run: python -m unittest tests.test_v150_quickSettingsFollowUp -v

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
from jawsMigrator import outlookMessages, quickSettings, state  # noqa: E402

setUpModule = qs.setUpModule


# -- Space in the tree --------------------------------------------------------------------------------------------------


class SpaceInTheTreeTests(qs.NvdaCase):
	def open(self, context=None):
		from jawsMigrator.gui import quickSettingsDialog

		self.saved = []
		session = quickSettings.Session(context or quickSettings.Context("msedge", browse=True, name="msedge"))
		dialog = quickSettingsDialog.QuickSettingsDialog(self.frame, session, self.saved.append)
		self.addCleanup(dialog.Destroy)
		qs.pump()
		return dialog

	def select(self, dialog, text):
		stack = [dialog.tree.GetRootItem()]
		while stack:
			node = stack.pop()
			child, cookie = dialog.tree.GetFirstChild(node)
			while child.IsOk():
				if dialog.tree.GetItemText(child).startswith(text):
					dialog.tree.SelectItem(child)
					qs.pump()
					return child
				stack.append(child)
				child, cookie = dialog.tree.GetNextChild(node, cookie)
		self.fail(f"no row {text}")

	def press(self, dialog, code=wx.WXK_SPACE, shift=False, control=False):
		"""A key pressed with the focus in the tree. Gives back the event, to see whether the tree let it go on."""
		event = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
		event.SetKeyCode(code)
		event.SetShiftDown(shift)
		event.SetControlDown(control)
		event.SetEventObject(dialog.tree)
		dialog.tree.GetEventHandler().ProcessEvent(event)
		return event

	def rowTexts(self, dialog):
		return [text for _depth, text in qs.rows(dialog.tree)]

	def test_spaceChecksACheckBox(self):
		dialog = self.open()
		self.select(dialog, "Use Sound")
		was = dialog.check.GetValue()
		nvdaStubs.spoken.clear()
		event = self.press(dialog)
		self.assertFalse(event.GetSkipped(), "the tree took the key")
		self.assertEqual(dialog.check.GetValue(), not was, "the check box is what the row says")
		self.assertIn(f"Use Sound: {'not checked' if was else 'checked'}", self.rowTexts(dialog))
		self.assertEqual(dialog.session.changes(), {"VirtualCursorOptions.FormsOptions.UseSound": "0" if was else "1"})
		self.assertEqual(self.said(), ["not checked" if was else "checked"], "what it is now is said, as the check box says it")

	def test_spaceAgainIsAsItWas(self):
		dialog = self.open()
		self.select(dialog, "Use Sound")
		was = dialog.check.GetValue()
		self.press(dialog)
		self.press(dialog)
		self.assertEqual(dialog.check.GetValue(), was)
		self.assertEqual(dialog.session.changes(), {}, "nothing is left to save")

	def test_spaceOnASettingWithSeveralChoicesGoesToTheNext(self):
		dialog = self.open(quickSettings.Context("notepad"))
		self.select(dialog, "Punctuation")
		first = dialog.list.GetSelection()
		self.press(dialog)
		self.assertEqual(dialog.list.GetSelection(), (first + 1) % 4)
		self.assertIn(f"Punctuation: {['None', 'Some', 'Most', 'All'][(first + 1) % 4]}", self.rowTexts(dialog))
		self.assertIn("In NVDA: Punctuation level:", dialog.effect.GetValue())

	def test_afterTheLastChoiceTheFirstIsNext(self):
		dialog = self.open(quickSettings.Context("notepad"))
		self.select(dialog, "Punctuation")
		dialog.session.chosen["EditingOptions.Punctuation"] = "3"
		dialog._show(dialog.current)
		nvdaStubs.spoken.clear()
		self.press(dialog)
		self.assertEqual(dialog.list.GetSelection(), 0)
		self.assertEqual(dialog.session.chosen["EditingOptions.Punctuation"], "0")
		self.assertEqual(self.said(), ["None"])

	def test_aSettingThatIsNoChoiceOfJawsGoesToTheFirst(self):
		self.setBase("presentation.progressBarUpdates.progressBarOutputMode", "beep")
		dialog = self.open(quickSettings.Context("notepad"))
		self.select(dialog, "Progress Bars")
		self.assertEqual(dialog.list.GetSelection(), wx.NOT_FOUND)
		self.press(dialog)
		self.assertEqual(dialog.list.GetSelection(), 0)
		self.assertIn("Progress Bars: Spoken", self.rowTexts(dialog))

	def test_aCategoryRowDoesNothing(self):
		dialog = self.open(quickSettings.Context("notepad"))
		self.select(dialog, "Editing Options")
		nvdaStubs.spoken.clear()
		event = self.press(dialog)
		self.assertTrue(event.GetSkipped(), "the tree lets the key go on")
		self.assertEqual((dialog.session.changes(), self.said()), ({}, []))

	def test_otherKeysAreLeftToTheTree(self):
		dialog = self.open()
		self.select(dialog, "Use Sound")
		for kwargs in ({"code": wx.WXK_DOWN}, {"code": wx.WXK_RETURN}, {"code": wx.WXK_SPACE, "shift": True}, {"code": wx.WXK_SPACE, "control": True}):
			self.assertTrue(self.press(dialog, **kwargs).GetSkipped(), kwargs)
		self.assertEqual(dialog.session.changes(), {})

	def test_theControlsStayInStepWithTheTreeWhenYouTab(self):
		dialog = self.open()
		self.select(dialog, "Use Sound")
		was = dialog.check.GetValue()
		self.press(dialog)
		self.select(dialog, "Auto Forms Mode")
		self.select(dialog, "Use Sound")
		self.assertEqual(dialog.check.GetValue(), not was)

	def test_theTestersMessageAutomaticallyReadInOutlook(self):
		# Issue 40: Down Arrow to "Messages Automatically Read: not checked", Space, OK.
		dialog = self.open(quickSettings.Context("outlook", name="Outlook"))
		self.select(dialog, "Messages Automatically Read")
		self.assertEqual(dialog.session.valueText(dialog.current), "not checked")
		self.press(dialog)
		self.assertIn("Messages Automatically Read: checked", self.rowTexts(dialog))
		closed = []
		dialog.EndModal = lambda code: closed.append(code)
		dialog._onOk(None)
		self.assertEqual(closed, [wx.ID_OK])
		self.assertIs(state.get(outlookMessages.READ_KEY), True)
		self.assertEqual(len(self.saved), 1)
		self.assertTrue(self.saved[0].assistant, "the plugin applies the assistant's own settings then")

	def test_theCategoryHintNamesSpace(self):
		dialog = self.open(quickSettings.Context("notepad"))
		self.select(dialog, "Editing Options")
		self.assertIn("press Space to change it", dialog.effect.GetValue())


# -- Reading a message when it opens, with Outlook First Line Silence -------------------------------------------------


class ReadingOnOpenTests(opening.Isolated):
	"""The tester's setup: Outlook First Line Silence around NVDA's event, and the message he opened."""

	def setUp(self):
		super().setUp()
		opened.resetTheAssistant(self)
		self.silence = types.SimpleNamespace(gated=False, opened=0)
		self.dropped = []
		self.later = []
		self.focus = None
		self.tree.event_treeInterceptor_gainFocus = self._firstLineSilence(vars(self.tree)["event_treeInterceptor_gainFocus"])
		# Outlook First Line Silence 1.0.30: _closeGate lets speech through again, _hookDocumentEvent opens the gate after.
		module = types.ModuleType(outlookMessages.SILENCE_MODULE)
		module._closeGate = self._closeGate
		core = types.ModuleType("core")
		core.callLater = lambda delay, function: self.later.append((delay, function))
		api = types.ModuleType("api")
		api.getFocusObject = lambda: self.focus
		patch = mock.patch.dict(sys.modules, {outlookMessages.SILENCE_MODULE: module, "core": core, "api": api})
		patch.start()
		self.addCleanup(patch.stop)
		# Its gate drops what Say All says for a while after a message opened.
		readText = self.speech.sayAll.SayAllHandler.readText

		def gatedReadText(cursor, **kwargs):
			if self.silence.gated:
				self.dropped.append(cursor)
				return
			readText(cursor, **kwargs)

		self.speech.sayAll.SayAllHandler.readText = gatedReadText

	def _firstLineSilence(self, original):
		def event_treeInterceptor_gainFocus(treeInterceptor, *args, **kwargs):
			try:
				return original(treeInterceptor, *args, **kwargs)
			finally:
				self.silence.gated = True

		return event_treeInterceptor_gainFocus

	def _closeGate(self):
		self.silence.gated = False
		self.silence.opened += 1

	def turnOnReading(self):
		opened.applyAsThePluginDoes(dict(state.DEFAULTS, **{outlookMessages.READ_KEY: True}))
		self.addCleanup(outlookMessages.unregister)

	def messageWindow(self, **kwargs):
		"""A message that has opened: its browse mode, and the object that takes the focus in it."""
		treeInterceptor = self.tree(opening.Document(**kwargs))
		focused = types.SimpleNamespace(appModule=treeInterceptor.rootNVDAObject.appModule, treeInterceptor=treeInterceptor)
		return treeInterceptor, focused

	def heard(self):
		return [said for said in self.speech.said if said[0] == "say all"]

	def test_firstLineSilenceWouldDropTheStartOfTheMessageButItsGateIsOpenedFirst(self):
		self.turnOnReading()
		treeInterceptor, _focused = self.messageWindow()
		treeInterceptor.event_treeInterceptor_gainFocus()
		self.assertEqual(self.dropped, [], "nothing of the reading was dropped")
		self.assertEqual(self.heard(), [("say all", self.speech.sayAll.CURSOR.CARET)])
		self.assertEqual(self.silence.opened, 1)

	def test_withoutThatAddOnNothingIsOpened(self):
		self.tree.event_treeInterceptor_gainFocus = self.nvdasGainFocus
		self.turnOnReading()
		with mock.patch.dict(sys.modules):
			sys.modules.pop(outlookMessages.SILENCE_MODULE)
			self.assertFalse(outlookMessages.letSpeechThrough())
			treeInterceptor, _focused = self.messageWindow()
			treeInterceptor.event_treeInterceptor_gainFocus()
		self.assertEqual(self.heard(), [("say all", self.speech.sayAll.CURSOR.CARET)])
		self.assertEqual(self.silence.opened, 0)

	def test_aVersionOfThatAddOnWithoutTheGateIsLeftAlone(self):
		module = types.ModuleType(outlookMessages.SILENCE_MODULE)
		with mock.patch.dict(sys.modules, {outlookMessages.SILENCE_MODULE: module}):
			self.assertFalse(outlookMessages.letSpeechThrough())

	def test_theDebugLogSaysTheGateWasOpened(self):
		self.turnOnReading()
		treeInterceptor, _focused = self.messageWindow()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			treeInterceptor.event_treeInterceptor_gainFocus()
		self.assertTrue(any("is read from the top" in line and "Outlook First Line Silence's gate opened first" in line for line in logged.output), logged.output)

	# -- the message that browse mode did not hand to the first way ---------------------------------------------------------

	def test_aMessageBrowseModeHadBeforeIsReadWhenItTakesTheFocus(self):
		# The first way saw nothing to read (NVDA's _hadFirstGainFocus was already set, as another add-on can leave it).
		self.turnOnReading()
		treeInterceptor, focused = self.messageWindow()
		treeInterceptor._hadFirstGainFocus = True
		treeInterceptor.event_treeInterceptor_gainFocus()
		self.assertEqual(self.heard(), [])
		self.assertTrue(outlookMessages.readWhenFocused(focused))
		self.assertEqual(self.heard(), [], "after the event, not during it")
		(delay, function), = self.later
		self.assertEqual(delay, outlookMessages.READ_DELAY)
		self.focus = focused
		function()
		self.assertEqual(self.dropped, [])
		self.assertEqual(self.heard(), [("say all", self.speech.sayAll.CURSOR.CARET)])
		self.assertEqual(self.silence.opened, 1)

	def test_aMessageIsReadOnce(self):
		self.turnOnReading()
		treeInterceptor, focused = self.messageWindow()
		treeInterceptor.event_treeInterceptor_gainFocus()
		self.assertEqual(len(self.heard()), 1)
		self.assertFalse(outlookMessages.readWhenFocused(focused), "the first way read it")
		self.assertEqual((self.later, len(self.heard())), ([], 1))
		# And the other way round: read at the focus event, then browse mode comes into it again.
		self.speech.readings.clear()
		treeInterceptor, focused = self.messageWindow()
		treeInterceptor._hadFirstGainFocus = True
		self.assertTrue(outlookMessages.readWhenFocused(focused))
		self.assertFalse(outlookMessages.readWhenFocused(focused), "the same focus event again")
		self.assertEqual(len(self.later), 1)

	def test_comingBackToAnOpenMessageIsNotReadAgain(self):
		self.turnOnReading()
		treeInterceptor, focused = self.messageWindow()
		treeInterceptor.event_treeInterceptor_gainFocus()
		self.speech.said.clear()
		treeInterceptor.event_treeInterceptor_gainFocus()
		self.assertEqual(self.heard(), [])
		self.assertFalse(outlookMessages.readWhenFocused(focused))

	def test_withReadingOffAMessageIsNotedAndNotReadWhenItIsTurnedOn(self):
		opened.applyAsThePluginDoes(dict(state.DEFAULTS))
		self.addCleanup(outlookMessages.unregister)
		treeInterceptor, focused = self.messageWindow()
		self.assertFalse(outlookMessages.readWhenFocused(focused))
		self.turnOnReading()
		self.assertFalse(outlookMessages.readWhenFocused(focused), "it was open before reading was turned on")
		self.assertEqual(self.later, [])
		# A message opened after that is read.
		_other, otherFocused = self.messageWindow()
		_other._hadFirstGainFocus = True
		self.assertTrue(outlookMessages.readWhenFocused(otherFocused))

	def test_nvdaReadingItAlreadyIsNotReadAgain(self):
		self.turnOnReading()
		treeInterceptor, focused = self.messageWindow()
		self.speech.sayAll.SayAllHandler.readText(self.speech.sayAll.CURSOR.CARET)
		self.assertFalse(outlookMessages.readWhenFocused(focused))
		self.assertEqual(self.later, [])

	def test_aMessageYouWriteIsNotRead(self):
		self.turnOnReading()
		_treeInterceptor, focused = self.messageWindow(readOnly=False)
		self.assertFalse(outlookMessages.readWhenFocused(focused))

	def test_anotherProgramIsNotRead(self):
		self.turnOnReading()
		_treeInterceptor, focused = self.messageWindow(appName="winword")
		self.assertFalse(outlookMessages.readWhenFocused(focused))
		self.assertFalse(outlookMessages.readWhenFocused(types.SimpleNamespace(appModule=None, treeInterceptor=None)))
		self.assertFalse(outlookMessages.readWhenFocused(types.SimpleNamespace(appModule=focused.appModule, treeInterceptor=None)), "no browse mode")

	def test_focusModeIsNotRead(self):
		self.turnOnReading()
		treeInterceptor, focused = self.messageWindow()
		treeInterceptor.passThrough = True
		self.assertFalse(outlookMessages.readWhenFocused(focused))

	def test_aFocusThatLeftBeforeTheReadingIsNotRead(self):
		self.turnOnReading()
		treeInterceptor, focused = self.messageWindow()
		treeInterceptor._hadFirstGainFocus = True
		outlookMessages.readWhenFocused(focused)
		self.focus = types.SimpleNamespace(treeInterceptor=None)
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.later[0][1]()
		self.assertEqual(self.heard(), [])
		self.assertTrue(any("the focus left the Outlook message" in line for line in logged.output), logged.output)

	def test_aFailureOfTheLaterReadingIsLoggedAndNothingMore(self):
		self.turnOnReading()
		treeInterceptor, focused = self.messageWindow()
		treeInterceptor._hadFirstGainFocus = True
		outlookMessages.readWhenFocused(focused)
		self.focus = focused
		self.speech.readTextFails = True
		with mock.patch.object(outlookMessages, "_failed", False):
			self.later[0][1]()
		self.assertEqual(self.heard(), [])

	def test_withoutTheTimerTheMessageIsReadAtOnce(self):
		self.turnOnReading()
		treeInterceptor, focused = self.messageWindow()
		treeInterceptor._hadFirstGainFocus = True
		self.focus = focused
		with mock.patch.dict(sys.modules, {"core": None}):
			self.assertTrue(outlookMessages.readWhenFocused(focused))
		self.assertEqual(len(self.heard()), 1)

	# -- what the debug log says -----------------------------------------------------------------------------------------

	def test_theDebugLogSaysWhyAMessageWasNotRead(self):
		self.turnOnReading()
		treeInterceptor, _focused = self.messageWindow()
		treeInterceptor._hadFirstGainFocus = True
		with self.assertLogs("nvda", level="DEBUG") as logged:
			treeInterceptor.event_treeInterceptor_gainFocus()
			treeInterceptor.event_treeInterceptor_gainFocus()
		said = [line for line in logged.output if "browse mode came into an Outlook message you read" in line]
		self.assertEqual(len(said), 1, "once for each message")
		self.assertIn("first time False, read already False, not read from the top", said[0])

	def test_theDebugLogSaysAMessageIsRead(self):
		self.turnOnReading()
		treeInterceptor, _focused = self.messageWindow()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			treeInterceptor.event_treeInterceptor_gainFocus()
		self.assertTrue(any("first time True, read already False, read from the top" in line for line in logged.output), logged.output)

	def test_aDocumentOfAnotherProgramAddsNothingToTheLog(self):
		self.turnOnReading()
		treeInterceptor = self.tree(opening.Document(appName="winword"))
		with self.assertLogs("nvda", level="DEBUG") as logged:
			import logging

			logging.getLogger("nvda").debug("marker")
			treeInterceptor.event_treeInterceptor_gainFocus()
		self.assertFalse(any("browse mode came into" in line for line in logged.output))


# -- the plugin ---------------------------------------------------------------------------------------------------------


class PluginTests(unittest.TestCase):
	def plugin(self):
		plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		plugin._sleepApps = set()
		plugin._changeRepeats = None
		plugin._screenShade = None
		plugin._checkSleep = lambda obj: None
		return plugin

	def test_theFocusEventLooksAtTheMessageAfterNvdaHandledIt(self):
		order = []
		plugin = self.plugin()
		obj = object()
		with mock.patch.object(outlookMessages, "readWhenFocused", lambda focused: order.append(("read", focused is obj))):
			plugin.event_gainFocus(obj, lambda: order.append("nvda"))
		self.assertEqual(order, ["nvda", ("read", True)])

	def test_aFailureThereNeverStopsTheFocusEvent(self):
		plugin = self.plugin()
		order = []

		def fails(obj):
			raise RuntimeError("no")

		with mock.patch.object(outlookMessages, "readWhenFocused", fails), mock.patch.object(jawsMigrator.debugLog, "error") as logged:
			plugin.event_gainFocus(object(), lambda: order.append("nvda"))
		self.assertEqual(order, ["nvda"])
		logged.assert_called_once()


if __name__ == "__main__":
	unittest.main()
