# Unit tests for issue 54: Enter on an icon in the System Tray List add-on's list doesn't do what it does in JAWS (trayList).
# NVDA+F11 is the System Tray List add-on (systrayList 2026.08.24), whose dialog's default button is Left Double Click;
# in JAWS's list, Insert+F11, the default button is Right Single Click. With the assistant, Enter in the add-on's list of
# the tray's icons right-clicks the icon. The add-on below has what the real one has, as read from its code: a GlobalPlugin
# with _createSystrayList, _createTaskList and _systrayListDialog, and a wx dialog with a list and the buttons Left Click,
# Left Double Click, Right Click and Cancel, made in that order, Left Double Click the default.
# Run: python -m unittest tests.test_v162_trayList -v

import functools
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import wx  # noqa: E402

from jawsMigrator import state, trayList  # noqa: E402

_app = wx.App.Get() or wx.App(False)


class SystrayListDialog(wx.Dialog):
	"""System Tray List's dialog, as the add-on makes it; each button notes which click it would make."""

	def __init__(self, parent=None):
		super().__init__(parent, title="")
		self.clicks = []
		self.listBox = wx.ListBox(self, style=wx.LB_SINGLE)
		self.left = wx.Button(self, label="&Left Click")
		self.double = wx.Button(self, label="Left &Double Click")
		self.right = wx.Button(self, label="&Right Click")
		self.cancel = wx.Button(self, wx.ID_CANCEL)
		for button, click in ((self.left, "left"), (self.double, "double"), (self.right, "right")):
			button.Bind(wx.EVT_BUTTON, lambda event, click=click: self.clicks.append(click))
		self.double.SetDefault()

	def updateSystray(self, systray, title, label):
		self.SetTitle(title)
		self.listBox.SetItems([name for name, location in systray])
		self.listBox.Select(0)


def makeModule():
	"""globalPlugins.systrayList as NVDA imports it."""
	module = types.ModuleType(trayList.MODULE)

	class GlobalPlugin:
		def __init__(self):
			self._systrayListDialog = None
			self.shown = []

		def _createSystrayList(self):
			self._createObjectsWindow([("Volume Speakers: 100%", (10, 10, 20, 20))], "System Tray List")

		def _createTaskList(self):
			self._createObjectsWindow([("Outlook", (40, 10, 20, 20))], "Taskbar List")

		def _createObjectsWindow(self, objects, title):
			if not self._systrayListDialog:
				self._systrayListDialog = SystrayListDialog()
			self._systrayListDialog.updateSystray(objects, title, "")
			self.shown.append(title)

	module.GlobalPlugin = GlobalPlugin
	return module


class TrayListTests(unittest.TestCase):
	def setUp(self):
		trayList.unregister()
		trayList._failed.clear()
		self.module = makeModule()
		self.originals = {name: vars(self.module.GlobalPlugin)[name] for name in (trayList.TRAY, trayList.TASKS)}
		patcher = mock.patch.dict(sys.modules, {trayList.MODULE: self.module})
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(trayList.unregister)
		self.plugin = self.module.GlobalPlugin()
		self.addCleanup(self._destroy)

	def _destroy(self):
		dialog = self.plugin._systrayListDialog
		if dialog:
			dialog.Destroy()

	def dialog(self):
		return self.plugin._systrayListDialog

	def pressEnter(self):
		"""Enter in the list: wx presses the dialog's default button."""
		dialog = self.dialog()
		button = dialog.GetDefaultItem()
		button.ProcessWindowEvent(wx.CommandEvent(wx.EVT_BUTTON.typeId, button.GetId()))
		return dialog.clicks[-1]

	def test_enterInTheTraysListRightClicks(self):
		trayList.register()
		self.assertTrue(trayList.isInstalled())
		self.plugin._createSystrayList()
		self.assertEqual(self.plugin.shown, ["System Tray List"], "the add-on still fills and shows its dialog")
		self.assertIs(self.dialog().GetDefaultItem(), self.dialog().right)
		self.assertEqual(self.pressEnter(), "right", "Enter right-clicks the icon, as JAWS's Right Single Click")

	def test_withoutTheAssistantEnterDoubleClicks(self):
		# What the tester had: the add-on's own default button.
		self.plugin._createSystrayList()
		self.assertIs(self.dialog().GetDefaultItem(), self.dialog().double)
		self.assertEqual(self.pressEnter(), "double")

	def test_theOtherButtonsStayTheirOwn(self):
		trayList.register()
		self.plugin._createSystrayList()
		dialog = self.dialog()
		for button, click in ((dialog.left, "left"), (dialog.double, "double"), (dialog.right, "right")):
			button.ProcessWindowEvent(wx.CommandEvent(wx.EVT_BUTTON.typeId, button.GetId()))
			self.assertEqual(dialog.clicks[-1], click)
		self.assertEqual([button.GetLabel() for button in (dialog.left, dialog.double, dialog.right)], ["&Left Click", "Left &Double Click", "&Right Click"])

	def test_theTaskbarsListKeepsTheAddonsOwnDefault(self):
		trayList.register()
		self.plugin._createSystrayList()
		# NVDA+F11 pressed twice: the same dialog shows the taskbar's programs, which JAWS's list doesn't.
		self.plugin._createTaskList()
		self.assertIs(self.dialog().GetDefaultItem(), self.dialog().double)
		self.assertEqual(self.pressEnter(), "double")
		self.plugin._createSystrayList()
		self.assertIs(self.dialog().GetDefaultItem(), self.dialog().right, "and the tray's icons again: Right Click")

	def test_theTaskbarsListFirstIsLeftAlone(self):
		trayList.register()
		self.plugin._createTaskList()
		self.assertIs(self.dialog().GetDefaultItem(), self.dialog().double)

	def test_aNewDialogAfterCancelRightClicksToo(self):
		trayList.register()
		self.plugin._createSystrayList()
		# Cancel destroys the dialog; the add-on makes a new one the next time.
		self.dialog().Destroy()
		wx.GetApp().ProcessPendingEvents()
		wx.SafeYield()
		self.assertFalse(self.dialog())
		self.plugin._createSystrayList()
		self.assertIs(self.dialog().GetDefaultItem(), self.dialog().right)

	def test_turnedOffGivesEverythingBack(self):
		trayList.register()
		self.plugin._createSystrayList()
		trayList.unregister()
		self.assertFalse(trayList.isRegistered())
		self.assertFalse(trayList.isInstalled())
		for name, original in self.originals.items():
			self.assertIs(vars(self.module.GlobalPlugin)[name], original)
		self.assertIs(self.dialog().GetDefaultItem(), self.dialog().double, "the open dialog gets its own default back")
		self.plugin._createSystrayList()
		self.assertIs(self.dialog().GetDefaultItem(), self.dialog().double)

	def test_onAgainAfterOff(self):
		trayList.register()
		trayList.unregister()
		trayList.register()
		self.plugin._createSystrayList()
		self.assertIs(self.dialog().GetDefaultItem(), self.dialog().right)

	def test_registeringTwiceWrapsOnce(self):
		trayList.register()
		trayList.register()
		wrapped = vars(self.module.GlobalPlugin)[trayList.TRAY]
		self.assertIs(getattr(wrapped, trayList.ORIGINAL), self.originals[trayList.TRAY])
		self.assertEqual(len(trayList._replaced), 2)

	def test_anotherAddonsWrapperIsKept(self):
		trayList.register()
		ours = vars(self.module.GlobalPlugin)[trayList.TRAY]

		@functools.wraps(ours)
		def theirs(self, *args, **kwargs):
			return ours(self, *args, **kwargs)

		self.module.GlobalPlugin._createSystrayList = theirs
		trayList.register()
		self.assertIs(vars(self.module.GlobalPlugin)[trayList.TRAY], theirs, "not wrapped again")
		trayList.unregister()
		self.assertIs(vars(self.module.GlobalPlugin)[trayList.TRAY], theirs, "what another add-on put there since is left")

	def test_theAddonLoadedAfterTheAssistant(self):
		with mock.patch.dict(sys.modules):
			del sys.modules[trayList.MODULE]
			with mock.patch.object(wx, "CallAfter") as later:
				trayList.register()
			self.assertFalse(trayList.isInstalled())
			sys.modules[trayList.MODULE] = self.module
			later.call_args[0][0]()
			self.assertTrue(trayList.isInstalled())
			self.plugin._createSystrayList()
			self.assertIs(self.dialog().GetDefaultItem(), self.dialog().right)

	def test_withoutTheAddonNothingHappens(self):
		with mock.patch.dict(sys.modules):
			del sys.modules[trayList.MODULE]
			with mock.patch.object(wx, "CallAfter"):
				trayList.register()
			self.assertTrue(trayList.isRegistered())
			self.assertFalse(trayList.isInstalled())

	def test_aDialogTheAssistantDoesntKnowIsLeftAlone(self):
		trayList.register()
		dialog = SystrayListDialog()
		dialog.right.Destroy()
		self.plugin._systrayListDialog = dialog
		self.plugin._createSystrayList()
		self.assertIs(dialog.GetDefaultItem(), dialog.double)
		self.assertTrue(trayList._failed)

	def test_anAddonWithoutTheMethodsIsLeftAlone(self):
		del self.module.GlobalPlugin._createTaskList
		trayList.register()
		self.assertFalse(trayList.isInstalled())
		self.assertIs(vars(self.module.GlobalPlugin)[trayList.TRAY], self.originals[trayList.TRAY])

	def test_theAddonsOwnFailureIsItsOwn(self):
		def broken(self):
			raise RuntimeError("no tray")

		self.module.GlobalPlugin._createSystrayList = broken
		trayList.register()
		with self.assertRaises(RuntimeError):
			self.plugin._createSystrayList()

	def test_aFailureOfTheAssistantLeavesTheDialogAsItIs(self):
		trayList.register()
		with mock.patch.object(trayList, "_clickButtons", side_effect=RuntimeError):
			self.plugin._createSystrayList()
		self.assertEqual(self.plugin.shown, ["System Tray List"])
		self.assertIs(self.dialog().GetDefaultItem(), self.dialog().double)

	def test_theSetting(self):
		self.assertTrue(trayList.wanted({}))
		self.assertTrue(trayList.wanted({trayList.STATE_KEY: True}))
		self.assertFalse(trayList.wanted({trayList.STATE_KEY: False}))
		self.assertFalse(trayList.wanted(None))
		self.assertIn(trayList.STATE_KEY, state.DEFAULTS)
		self.assertTrue(state.DEFAULTS[trayList.STATE_KEY])


if __name__ == "__main__":
	unittest.main()
