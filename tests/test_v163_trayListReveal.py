# Unit tests for the System Tray List add-on's clicks with a taskbar that hides automatically (trayList, found while
# fixing issue 54). System Tray List notes where each icon is as it makes its list, and clicks there; a hidden taskbar is
# moved down until 2 pixels of it show, so the click missed. The taskbar below has the places read from Windows 11 build
# 26300 at 125% (1920 by 1200): shown at (0, 1140, 1920, 1200), hidden at (0, 1198, 1920, 1258); Volume at
# (1751, 1198, 30, 60) in a list made while it was hidden, (1751, 1140, 30, 60) while it showed.
# Run: python -m unittest tests.test_v163_trayListReveal -v

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import state, trayList  # noqa: E402

TASKBAR = 0x10086
SHOWN = (0, 1140, 1920, 1200)
HIDDEN = (0, 1198, 1920, 1258)
VOLUME_HIDDEN = (1751, 1198, 30, 60)
VOLUME_SHOWN = (1751, 1140, 30, 60)
RIGHT = ("rightDown", "rightUp")


class Taskbar:
	"""What Windows says about the taskbar: trayList._Win32's questions."""

	def __init__(self, rect=HIDDEN, hides=True, shown=SHOWN, window=TASKBAR):
		self.rect = rect
		self.hidesItself = hides
		self.shown = shown
		self.window = window

	def taskbar(self):
		return self.window

	def windowRect(self, window):
		return self.rect if window == self.window else None

	def hides(self, window):
		return self.hidesItself

	def shownRect(self, window):
		return self.shown


def makeModule(clicks):
	"""globalPlugins.systrayList: its plugin makes the list, and each button calls the module's mouseEvents."""
	module = types.ModuleType(trayList.MODULE)

	def mouseEvents(location, *events):
		clicks.append((tuple(location), events))

	class GlobalPlugin:
		def __init__(self):
			self._systrayListDialog = None
			self.systray = []

		def _createSystrayList(self):
			# The icons' places as Windows gives them now: the taskbar's place when the list is made.
			top = taskbarNow[0].rect[1]
			self.systray = [("Volume Speakers: 20%", (1751, top, 30, 60))]

		def _createTaskList(self):
			self.systray = [("Outlook", (900, taskbarNow[0].rect[1], 50, 60))]

		def press(self, index, *events):
			# A button of the dialog: the module's mouseEvents, looked up as the add-on's own code does.
			module.mouseEvents(self.systray[index][1], *events)

	taskbarNow = [None]
	module.mouseEvents = mouseEvents
	module.GlobalPlugin = GlobalPlugin
	module.taskbarNow = taskbarNow
	return module


class RevealTests(unittest.TestCase):
	def setUp(self):
		trayList.unregister()
		trayList._failed.clear()
		self.clicks = []
		self.module = makeModule(self.clicks)
		self.ownClick = self.module.mouseEvents
		self.taskbar = Taskbar()
		self.module.taskbarNow[0] = self.taskbar
		self.timers = []
		self.moves = []
		patches = [
			mock.patch.dict(sys.modules, {trayList.MODULE: self.module}),
			mock.patch.object(trayList, "_win", lambda: self.taskbar),
			mock.patch.object(trayList, "_later", self._later),
			mock.patch.object(trayList, "_movePointer", self.moves.append),
		]
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		self.addCleanup(trayList.unregister)
		self.plugin = self.module.GlobalPlugin()

	def _later(self, seconds, function):
		timer = mock.Mock()
		timer.function = function
		timer.seconds = seconds
		self.timers.append(timer)
		return timer

	def runTimer(self):
		timer = self.timers.pop(0)
		self.assertFalse(timer.Stop.called, "a stopped wait doesn't run")
		timer.function()

	def test_aHiddenTaskbarIsBroughtUpAndTheIconClicked(self):
		trayList.register()
		self.assertTrue(trayList.isClickInstalled())
		self.plugin._createSystrayList()
		self.plugin.press(0, *RIGHT)
		self.assertEqual(self.clicks, [], "no click on the edge of the screen")
		self.assertEqual(self.moves, [(1766, 1198)], "the pointer on the part of the taskbar that shows, under the icon")
		self.assertEqual(self.timers[0].seconds, trayList.REVEAL_POLL)
		# Still coming up.
		self.runTimer()
		self.assertEqual(self.clicks, [])
		self.taskbar.rect = SHOWN
		self.runTimer()
		self.assertEqual(self.clicks, [(VOLUME_SHOWN, RIGHT)], "the click lands on Volume, once")
		self.assertEqual(self.timers, [])

	def test_aTaskbarAlreadyUpIsClickedAtOnce(self):
		trayList.register()
		self.plugin._createSystrayList()
		# The pointer was moved onto the taskbar in the meantime.
		self.taskbar.rect = SHOWN
		self.plugin.press(0, *RIGHT)
		self.assertEqual(self.clicks, [(VOLUME_SHOWN, RIGHT)])
		self.assertEqual(self.moves, [])

	def test_aListMadeWhileTheTaskbarShowedIsClickedAsItWas(self):
		trayList.register()
		self.taskbar.rect = SHOWN
		self.plugin._createSystrayList()
		self.plugin.press(0, *RIGHT)
		self.assertEqual(self.clicks, [(VOLUME_SHOWN, RIGHT)])
		self.assertEqual(self.moves, [])

	def test_aTaskbarThatHidBehindTheDialogIsBroughtUpAgain(self):
		# Windows+B, then NVDA+F11: the list is made while the taskbar shows, and it hides once the dialog has the focus.
		trayList.register()
		self.taskbar.rect = SHOWN
		self.plugin._createSystrayList()
		self.taskbar.rect = HIDDEN
		self.plugin.press(0, *RIGHT)
		self.assertEqual(self.clicks, [], "not on the window under where the icon was")
		self.assertEqual(self.moves, [(1766, 1198)])
		self.taskbar.rect = SHOWN
		self.runTimer()
		self.assertEqual(self.clicks, [(VOLUME_SHOWN, RIGHT)])

	def test_aTaskbarThatDoesntHideIsLeftAlone(self):
		trayList.register()
		self.taskbar = Taskbar(rect=SHOWN, hides=False)
		self.module.taskbarNow[0] = self.taskbar
		self.plugin._createSystrayList()
		self.plugin.press(0, *RIGHT)
		self.assertEqual(self.clicks, [(VOLUME_SHOWN, RIGHT)])

	def test_aTaskbarThatNeverComesUpIsClickedAsBefore(self):
		trayList.register()
		self.plugin._createSystrayList()
		self.plugin.press(0, *RIGHT)
		while self.timers:
			self.runTimer()
		self.assertEqual(self.clicks, [(VOLUME_HIDDEN, RIGHT)], "after the wait, where System Tray List noted it, once")

	def test_theWaitIsTwoSeconds(self):
		trayList.register()
		self.plugin._createSystrayList()
		self.plugin.press(0, *RIGHT)
		runs = 0
		while self.timers:
			self.runTimer()
			runs += 1
		self.assertAlmostEqual(runs * trayList.REVEAL_POLL, trayList.REVEAL_WAIT)

	def test_aTaskbarThatChangedSizeIsLeftAlone(self):
		trayList.register()
		self.plugin._createSystrayList()
		self.taskbar.shown = (0, 1128, 1920, 1200)
		self.plugin.press(0, *RIGHT)
		self.assertEqual(self.clicks, [(VOLUME_HIDDEN, RIGHT)])

	def test_aNewTaskbarIsLeftAlone(self):
		trayList.register()
		self.plugin._createSystrayList()
		# Explorer started again: another taskbar window.
		self.taskbar.window = TASKBAR + 1
		self.plugin.press(0, *RIGHT)
		self.assertEqual(self.clicks, [(VOLUME_HIDDEN, RIGHT)])

	def test_theTaskbarsListToo(self):
		trayList.register()
		self.plugin._createTaskList()
		self.taskbar.rect = SHOWN
		self.plugin.press(0, "leftDown", "leftUp")
		self.assertEqual(self.clicks, [((900, 1140, 50, 60), ("leftDown", "leftUp"))])

	def test_aSecondClickWhileWaitingReplacesTheFirst(self):
		trayList.register()
		self.plugin._createSystrayList()
		self.plugin.press(0, *RIGHT)
		first = self.timers[0]
		self.plugin.press(0, "leftDown", "leftUp")
		self.assertTrue(first.Stop.called)
		self.timers.remove(first)
		self.taskbar.rect = SHOWN
		self.runTimer()
		self.assertEqual(self.clicks, [(VOLUME_SHOWN, ("leftDown", "leftUp"))])

	def test_theAddonsOwnClickFailingIsClickedOnce(self):
		calls = []

		def broken(location, *events):
			calls.append(location)
			raise RuntimeError("no mouse")

		self.module.mouseEvents = broken
		trayList.register()
		self.plugin._createSystrayList()
		self.taskbar.rect = SHOWN
		with self.assertRaises(RuntimeError):
			self.plugin.press(0, *RIGHT)
		self.assertEqual(calls, [VOLUME_SHOWN], "once, not again where it was noted")

	def test_aFailureOfTheAssistantClicksAsBefore(self):
		trayList.register()
		self.plugin._createSystrayList()
		with mock.patch.object(self.taskbar, "hides", side_effect=OSError):
			self.plugin.press(0, *RIGHT)
		self.assertEqual(self.clicks, [(VOLUME_HIDDEN, RIGHT)])
		self.assertTrue(trayList._failed)

	def test_aFailureMovingThePointerClicksAsBefore(self):
		trayList.register()
		self.plugin._createSystrayList()
		with mock.patch.object(trayList, "_movePointer", side_effect=OSError):
			self.plugin.press(0, *RIGHT)
		self.assertEqual(self.clicks, [(VOLUME_HIDDEN, RIGHT)])
		self.assertEqual(self.timers, [])

	def test_revealOffClicksAsBefore(self):
		trayList.register(rightClick=True, reveal=False)
		self.assertTrue(trayList.isRegistered())
		self.plugin._createSystrayList()
		self.plugin.press(0, *RIGHT)
		self.assertEqual(self.clicks, [(VOLUME_HIDDEN, RIGHT)])

	def test_rightClickOffRevealStillWorks(self):
		trayList.register(rightClick=False, reveal=True)
		self.plugin._createSystrayList()
		self.taskbar.rect = SHOWN
		self.plugin.press(0, *RIGHT)
		self.assertEqual(self.clicks, [(VOLUME_SHOWN, RIGHT)])

	def test_bothOffIsUnregistered(self):
		trayList.register()
		trayList.register(rightClick=False, reveal=False)
		self.assertFalse(trayList.isRegistered())
		self.assertIs(self.module.mouseEvents, self.ownClick)

	def test_turnedOffWhileWaiting(self):
		trayList.register()
		self.plugin._createSystrayList()
		self.plugin.press(0, *RIGHT)
		timer = self.timers[0]
		trayList.unregister()
		self.assertTrue(timer.Stop.called)
		self.assertIs(self.module.mouseEvents, self.ownClick)
		self.assertFalse(trayList.isClickInstalled())

	def test_revealOffWhileWaiting(self):
		trayList.register()
		self.plugin._createSystrayList()
		self.plugin.press(0, *RIGHT)
		timer = self.timers[0]
		trayList.register(rightClick=True, reveal=False)
		self.assertTrue(timer.Stop.called)

	def test_anAddonWithoutTheClickStillRightClicks(self):
		del self.module.mouseEvents
		trayList.register()
		self.assertTrue(trayList.isInstalled())
		self.assertFalse(trayList.isClickInstalled())

	def test_thePartOfTheTaskbarThatShows(self):
		self.assertEqual(trayList._showing(HIDDEN, SHOWN), (0, 1198, 1920, 1200))
		# At the top of the screen, and at the left.
		self.assertEqual(trayList._showing((0, -58, 1920, 2), (0, 0, 1920, 60)), (0, 0, 1920, 2))
		self.assertEqual(trayList._showing((-78, 0, 2, 1200), (0, 0, 80, 1200)), (0, 0, 2, 1200))
		self.assertIsNone(trayList._showing((0, 1300, 1920, 1360), SHOWN))

	def test_theSetting(self):
		self.assertTrue(trayList.revealWanted({}))
		self.assertFalse(trayList.revealWanted({trayList.REVEAL_KEY: False}))
		self.assertFalse(trayList.revealWanted(None))
		self.assertTrue(state.DEFAULTS[trayList.REVEAL_KEY])


class Win32Tests(unittest.TestCase):
	@unittest.skipUnless(sys.platform == "win32", "Windows")
	def test_windowsAnswers(self):
		win32 = trayList._Win32()
		window = win32.taskbar()
		if not window:
			self.skipTest("no taskbar")
		rect = win32.windowRect(window)
		shown = win32.shownRect(window)
		self.assertEqual(len(rect), 4)
		self.assertEqual(len(shown), 4)
		self.assertIsInstance(win32.hides(window), bool)


if __name__ == "__main__":
	unittest.main()
