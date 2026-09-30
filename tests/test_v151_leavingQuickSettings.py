# Unit tests for leaving the QuickSettings window (issue 40), after 1.50. QuickSettings.exe of JAWS 2026 (27.6.18) holds the
# text "You have made changes to %s's settings. Do you want to save them?", so it looked as if JAWS asks that when you leave
# with choices unsaved, and the assistant's Cancel and Escape threw the choices away. JAWS was watched running, in Notepad
# (tests/jaws_quicksettings_keys_live.json has what was seen): with Typing Echo changed by Space, Escape, the Cancel button
# and the window's Close each closed the window, asked nothing, and left the change in notepad.JCF. Space toggled a check
# box and went round the choices of a list. So the assistant's window does the same: Cancel, Escape and closing keep
# what you changed and ask nothing (LeavingTests), and Space goes round the choices in the order JAWS's list has them
# (SpaceLikeJawsTests, against the record). Nothing here ran in NVDA itself.
# Run: python -m unittest tests.test_v151_leavingQuickSettings -v

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import wx  # noqa: E402

import test_v142_quickSettings as qs  # noqa: E402
from jawsMigrator import quickSettings  # noqa: E402

setUpModule = qs.setUpModule

RECORD = os.path.join(os.path.dirname(__file__), "jaws_quicksettings_keys_live.json")
LEAVING = "leaving with Typing Echo changed from Characters to Words"


def record() -> dict:
	with open(RECORD, encoding="utf-8") as stream:
		return json.load(stream)


class WindowCase(qs.NvdaCase):
	def open(self, context=None):
		from jawsMigrator.gui import quickSettingsDialog

		self.saved = []
		session = quickSettings.Session(context or quickSettings.Context("notepad"))
		dialog = quickSettingsDialog.QuickSettingsDialog(self.frame, session, self.saved.append)
		self.closed = []
		dialog.EndModal = lambda code: self.closed.append(code)
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

	def space(self, dialog):
		event = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
		event.SetKeyCode(wx.WXK_SPACE)
		event.SetEventObject(dialog.tree)
		dialog.tree.GetEventHandler().ProcessEvent(event)

	def label(self, dialog, settingId):
		return dialog.session.valueText(quickSettings.itemById(settingId))


class SpaceLikeJawsTests(WindowCase):
	def test_aListGoesRoundInTheOrderJawsShowedAndCheckBoxesToggle(self):
		seen = record()["space"]
		dialog = self.open()
		self.select(dialog, "Typing Echo")
		self.assertEqual(
			[choice.label for choice in dialog.current.choices],
			seen["Typing Echo"]["choices in the list"],
			"the same choices in the same order as the list JAWS's window has",
		)
		shown = []
		for _ in seen["Typing Echo"]["shown after each Space, from Characters"]:
			self.space(dialog)
			shown.append(self.label(dialog, "EditingOptions.TypingEcho"))
		self.assertEqual(shown, seen["Typing Echo"]["shown after each Space, from Characters"])

	def test_aCheckBoxIsCheckedAndUnchecked(self):
		seen = record()["space"]["Language Detect Change"]["checked after each Space, from checked"]
		dialog = self.open()
		self.select(dialog, "Language Detect Change")
		self.assertEqual(dialog.session.chosen["ReadingOptions.LanguageDetectChange"], "1")
		states = []
		for _ in seen:
			self.space(dialog)
			states.append(int(dialog.session.chosen["ReadingOptions.LanguageDetectChange"]))
		self.assertEqual(states, seen)


class LeavingTests(WindowCase):
	def change(self, dialog):
		"""Typing Echo from Characters to Words, as in the record."""
		self.select(dialog, "Typing Echo")
		self.space(dialog)
		self.assertEqual(self.label(dialog, "EditingOptions.TypingEcho"), "Words")
		nvdaStubs.spoken.clear()

	def cancelButton(self, dialog):
		return next(child for child in qs.descendants(dialog) if isinstance(child, wx.Button) and child.GetId() == wx.ID_CANCEL)

	def leaveByCancelButton(self, dialog):
		button = self.cancelButton(dialog)
		button.GetEventHandler().ProcessEvent(wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId()))

	def leaveByEscape(self, dialog):
		event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
		event.SetKeyCode(wx.WXK_ESCAPE)
		event.SetEventObject(dialog)
		dialog.GetEventHandler().ProcessEvent(event)

	def leaveByClosing(self, dialog):
		event = wx.CloseEvent(wx.wxEVT_CLOSE_WINDOW, dialog.GetId())
		event.SetEventObject(dialog)
		dialog.GetEventHandler().ProcessEvent(event)

	def check(self, leave):
		dialog = self.open()
		self.change(dialog)
		with mock.patch.object(wx, "MessageBox", side_effect=AssertionError("asked a question")), mock.patch.object(wx, "MessageDialog", side_effect=AssertionError("asked a question")):
			leave(dialog)
		self.assertEqual(self.closed, [wx.ID_CANCEL], "the window closed")
		self.assertEqual(self.profileValue("JAWS - notepad", "keyboard.speakTypedWords"), 1, "Words is kept")
		self.assertEqual(self.profileValue("JAWS - notepad", "keyboard.speakTypedCharacters"), 0)
		self.assertEqual(self.said(), ['Saved for notepad in the profile "JAWS - notepad".'])
		self.assertEqual(len(self.saved), 1)

	def test_theCancelButtonKeepsWhatYouChangedAndAsksNothing(self):
		self.check(self.leaveByCancelButton)

	def test_escapeKeepsWhatYouChangedAndAsksNothing(self):
		self.check(self.leaveByEscape)

	def test_closingTheWindowKeepsWhatYouChangedAndAsksNothing(self):
		self.check(self.leaveByClosing)

	def test_nothingChangedNothingIsSavedOrSaid(self):
		for leave in (self.leaveByCancelButton, self.leaveByEscape, self.leaveByClosing):
			nvdaStubs.spoken.clear()
			dialog = self.open()
			leave(dialog)
			self.assertEqual((self.closed, self.said(), self.saved, self.conf.listProfiles()), ([wx.ID_CANCEL], [], [], []), leave.__name__)

	def test_aSaveThatFailsIsSaidAndTheWindowClosesAllTheSame(self):
		dialog = self.open()
		self.change(dialog)
		with mock.patch.object(dialog.session, "save", side_effect=RuntimeError("no")), mock.patch("jawsMigrator.debugLog.error"):
			self.leaveByCancelButton(dialog)
		self.assertEqual(self.closed, [wx.ID_CANCEL], "there is always a way out")
		self.assertEqual(self.said(), ["The QuickSettings choices could not be saved. NVDA's log says why."])

	def test_okIsAsBefore(self):
		dialog = self.open()
		self.change(dialog)
		dialog._onOk(None)
		self.assertEqual(self.closed, [wx.ID_OK])
		self.assertEqual(self.profileValue("JAWS - notepad", "keyboard.speakTypedWords"), 1)

	def test_theWindowStillHasJawsButtonsAndEscapeIsCancel(self):
		dialog = self.open()
		self.assertEqual([child.GetLabel() for child in qs.descendants(dialog) if isinstance(child, wx.Button)], ["&Apply", "OK", "Cancel"])
		self.assertEqual(dialog.GetEscapeId(), wx.ID_CANCEL)


class RecordTests(unittest.TestCase):
	def test_jawsAskedNothingInAnyWayOfLeavingAndKeptTheChange(self):
		seen = record()[LEAVING]
		self.assertEqual(set(seen), {"Escape", "Cancel button (BM_CLICK)", "Close (Alt+F4)"})
		for way, what in seen.items():
			self.assertIs(what["asked a question"], False, way)
			self.assertIs(what["window closed"], True, way)
			self.assertIn("TypingEcho=2", what["notepad.JCF"], way)

	def test_theRecordSaysWhatWasNotSeen(self):
		self.assertIn("no window asked it", record()["not seen"])


if __name__ == "__main__":
	unittest.main()
