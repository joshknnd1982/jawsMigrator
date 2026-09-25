# Unit tests for version 1.11, from a tester's report on version 1.8: pressing the Mail key in Edge
# brought Outlook up, but NVDA said "NVDA window" and the focus never went to Outlook (outlookFocus).
# The imitation NVDA below does what NVDA 2026.2 does, as far as Outlook's object model goes: its
# AutoPropertyType, whose getters have no setter, so an app module can keep a value of its own; the
# Outlook app module's nativeOm, outlookVersion and _registerCOMWithFocusJuggle, as in
# appModules/outlook.py; comHelper.getActiveObject, which fails with MK_E_UNAVAILABLE until Outlook has
# lost the focus once; gui.mainFrame.prePopup, which brings NVDA's hidden window to the front; and wx,
# whose windows work only on NVDA's main thread. The questions come on the threads they came on in the
# tester's log. The assistant's register, guard and appModuleHandler wrapper are the real ones.
# Run: python -m unittest tests.test_v111_fixes -v

import os
import sys
import threading
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import outlookFocus  # noqa: E402

MAIN = threading.get_ident()
NVDA_PID = 6208
OUTLOOK_PID = 22100
EDGE_PID = 9120
#: NVDA's hidden main window, its "Waiting for Outlook..." dialog, and the tester's Outlook and Edge windows.
NVDA_WINDOW = 0x40A2E
WAITING_DIALOG = 0x40A30
OUTLOOK_WINDOW = 1640246
EDGE_WINDOW = 199662
MK_E_UNAVAILABLE = -2147221021


class Getter:
	"""NVDA 2026.2's baseObject.Getter: it has no __set__, so an instance can keep a value of its own."""

	def __init__(self, fget):
		self.fget = fget

	def __get__(self, instance, owner):
		if instance is None:
			return self
		return self.fget(instance)


class AutoPropertyType(type):
	"""NVDA's baseObject.AutoPropertyType, for getters: _get_x makes the property x."""

	def __init__(cls, name, bases, namespace):
		super().__init__(name, bases, namespace)
		for key, value in namespace.items():
			if key.startswith("_get_"):
				setattr(cls, key[5:], Getter(value))


class ObjectModel:
	"""Outlook.Application."""

	version = "16.0.0.19127"


class Desktop:
	"""Windows and NVDA, as far as the focus and Outlook's object model go."""

	def __init__(self):
		self.windows = {
			NVDA_WINDOW: (NVDA_PID, False, "wxWindowNR"),
			OUTLOOK_WINDOW: (OUTLOOK_PID, True, "rctrl_renwnd32"),
			EDGE_WINDOW: (EDGE_PID, True, "Chrome_WidgetWin_1"),
		}
		self.reset()

	def reset(self):
		self.windows.pop(WAITING_DIALOG, None)
		self.foreground = OUTLOOK_WINDOW
		#: Outlook is in Windows' list of running programs once it has lost the focus after starting.
		self.outlookListed = False
		#: Whether NVDA's own way of letting the focus go back works this time.
		self.nvdaGivesFocusBack = False
		#: What happens during the second NVDA waits for Outlook.
		self.meanwhile = None
		self.asked = []
		self.waitedOn = []
		self.spoken = []
		self.madeForeground = []
		self.errors = []

	def setForeground(self, window, bySetForegroundWindow=False):
		if bySetForegroundWindow:
			self.madeForeground.append(window)
		if self.foreground == OUTLOOK_WINDOW and window != OUTLOOK_WINDOW:
			self.outlookListed = True
		self.foreground = window

	def getActiveObject(self, progid, dynamic=False, appModule=None):
		"""comHelper.getActiveObject: nvda_slave's GetActiveObject, for NVDA running with uiAccess."""
		self.asked.append(threading.current_thread().name)
		if not self.outlookListed:
			raise OSError(MK_E_UNAVAILABLE, "Operation unavailable")
		return ObjectModel()

	def winUser(self):
		return types.SimpleNamespace(
			getForegroundWindow=lambda: self.foreground,
			setForegroundWindow=lambda window: self.setForeground(window, True),
			isWindow=lambda window: window in self.windows,
			isWindowVisible=lambda window: window in self.windows and self.windows[window][1],
			getWindowThreadProcessID=lambda window: (self.windows[window][0] if window in self.windows else 0, 1),
			getClassName=lambda window: self.windows[window][2] if window in self.windows else "",
		)

	def gui(self):
		desktop = self

		class MainFrame:
			def prePopup(self):
				desktop.waitedOn.append(threading.current_thread().name)
				if desktop.windows.get(desktop.foreground, (0,))[0] != NVDA_PID:
					# This process is not the foreground process, so bring it to the foreground.
					desktop.setForeground(NVDA_WINDOW)
					desktop.spoken.append(["NVDA", "window"])

			def postPopup(self):
				if desktop.nvdaGivesFocusBack and threading.get_ident() == MAIN:
					desktop.setForeground(OUTLOOK_WINDOW)

		return types.SimpleNamespace(mainFrame=MainFrame())

	def wx(self):
		desktop = self

		class Dialog:
			"""A wx window works only on the thread NVDA runs wx on, its main thread."""

			def __init__(self, parent, title=""):
				self.title = title
				self.onMainThread = threading.get_ident() == MAIN

			def CentreOnScreen(self):
				pass

			def Show(self):
				if self.onMainThread:
					desktop.windows[WAITING_DIALOG] = (NVDA_PID, True, "#32770")
					desktop.setForeground(WAITING_DIALOG)
					desktop.spoken.append([self.title, "dialog"])

			def Destroy(self):
				# wx deletes it when NVDA is idle; meanwhile it keeps the focus.
				pass

		return types.SimpleNamespace(Dialog=Dialog)


def outlookSupport(desktop):
	"""NVDA 2026.2's Outlook app module, as far as Outlook's object model goes (appModules/outlook.py)."""

	class AppModule(metaclass=AutoPropertyType):
		_hasTriedoutlookAppSwitch = False

		def __init__(self, processID=OUTLOOK_PID, appName="outlook"):
			self.processID = processID
			self.appName = appName

		def _registerCOMWithFocusJuggle(self):
			import gui
			import wx

			d = wx.Dialog(None, title="Waiting for Outlook...")
			d.CentreOnScreen()
			gui.mainFrame.prePopup()
			d.Show()
			self._hasTriedoutlookAppSwitch = True
			# api.processPendingEvents(), then comtypes.client.PumpEvents(1): Outlook is behind NVDA's window meanwhile.
			if desktop.meanwhile is not None:
				desktop.meanwhile()
			d.Destroy()
			gui.mainFrame.postPopup()

		def _get_nativeOm(self):
			try:
				nativeOm = desktop.getActiveObject("outlook.application", dynamic=True)
			except (OSError, RuntimeError):
				if self._hasTriedoutlookAppSwitch:
					desktop.errors.append("Failed to get native object model")
				nativeOm = None
			if not nativeOm and not self._hasTriedoutlookAppSwitch:
				self._registerCOMWithFocusJuggle()
				return None
			self.nativeOm = nativeOm
			return self.nativeOm

		def _get_outlookVersion(self):
			nativeOm = self.nativeOm
			if nativeOm:
				return int(nativeOm.version.split(".")[0])
			return 0

	AppModule.__module__ = "appModules.outlook"
	return AppModule


def onThread(function, name):
	"""Run ``function`` on a thread of its own, as a UI Automation event or an add-on's thread does."""
	result = {}

	def run():
		result["value"] = function()

	thread = threading.Thread(target=run, name=name)
	thread.start()
	thread.join()
	return result["value"]


class OutlookFocusTests(unittest.TestCase):
	def setUp(self):
		self.desktop = desktop = Desktop()
		self.Outlook = outlookSupport(desktop)
		self.fetched = []

		def fetchAppModule(processID, appName):
			appModule = self.Outlook(processID, appName) if appName == "outlook" else types.SimpleNamespace(processID=processID, appName=appName)
			self.fetched.append(appModule)
			return appModule

		self.nvdaFetchAppModule = fetchAppModule
		self.appModuleHandler = types.SimpleNamespace(fetchAppModule=fetchAppModule, runningTable={})
		patcher = mock.patch.dict(
			sys.modules,
			{
				"core": types.SimpleNamespace(mainThreadId=MAIN),
				"winUser": desktop.winUser(),
				"globalVars": types.SimpleNamespace(appPid=NVDA_PID),
				"gui": desktop.gui(),
				"wx": desktop.wx(),
				"appModuleHandler": self.appModuleHandler,
			},
		)
		patcher.start()
		self.addCleanup(patcher.stop)
		outlookFocus.unregister()
		outlookFocus._failed = False
		outlookFocus.register()
		self.addCleanup(outlookFocus.unregister)

	def openOutlook(self):
		"""The Mail key: NVDA meets Outlook, and Outlook comes to the front."""
		appModule = self.appModuleHandler.fetchAppModule(OUTLOOK_PID, "outlook")
		self.appModuleHandler.runningTable[OUTLOOK_PID] = appModule
		self.desktop.foreground = OUTLOOK_WINDOW
		return appModule

	def test_the_testers_mail_key(self):
		desktop = self.desktop
		outlook = self.openOutlook()
		# 14:53:13.8: another thread asks for Outlook's object model while NVDA's main thread is busy with the switch from Edge.
		self.assertIsNone(onThread(lambda: outlook.nativeOm, "Dummy-32"))
		self.assertEqual(desktop.asked, [], "nvda_slave isn't asked on that thread")
		self.assertEqual(desktop.waitedOn, [], "NVDA doesn't wait for Outlook there")
		self.assertEqual(desktop.spoken, [], 'no "NVDA window"')
		self.assertEqual(desktop.foreground, OUTLOOK_WINDOW, "the focus stays in Outlook")
		self.assertNotIn("nativeOm", vars(outlook), "nothing is kept")
		self.assertFalse(outlook._hasTriedoutlookAppSwitch, "NVDA's main thread can still wait for Outlook")
		# NVDA's main thread: the focus comes to a message, whose status NVDA reads from Outlook's object model.
		self.assertIsNone(outlook.nativeOm, "Outlook isn't in Windows' list yet")
		self.assertEqual(desktop.asked, ["MainThread"])
		self.assertEqual(desktop.waitedOn, ["MainThread"])
		self.assertEqual(desktop.spoken, [["NVDA", "window"], ["Waiting for Outlook...", "dialog"]], "NVDA waits for Outlook with its dialog, as without add-ons")
		self.assertEqual(desktop.foreground, OUTLOOK_WINDOW, "then the focus is back in Outlook")
		self.assertEqual(desktop.madeForeground, [OUTLOOK_WINDOW])
		# The message's status: NVDA gets Outlook's object model now, and keeps it.
		model = outlook.nativeOm
		self.assertIsInstance(model, ObjectModel)
		self.assertIs(vars(outlook)["nativeOm"], model)
		self.assertEqual(outlook.outlookVersion, 16)
		self.assertEqual(desktop.errors, [])

	def test_nvda_alone_does_what_the_testers_log_shows(self):
		outlookFocus.unregister()
		desktop = self.desktop
		outlook = self.openOutlook()
		self.assertIsNone(onThread(lambda: outlook.nativeOm, "Dummy-32"))
		self.assertEqual(desktop.asked, ["Dummy-32"], "nvda_slave fails with MK_E_UNAVAILABLE")
		self.assertEqual(desktop.waitedOn, ["Dummy-32"], "NVDA waits for Outlook on that thread")
		self.assertEqual(desktop.spoken, [["NVDA", "window"]], "no dialog comes up")
		self.assertEqual(desktop.foreground, NVDA_WINDOW, "and the focus stays in NVDA's window, until Alt+Tab")
		self.assertTrue(outlook._hasTriedoutlookAppSwitch)

	def test_the_focus_goes_back_only_from_nvdas_own_window(self):
		desktop = self.desktop
		with self.subTest("NVDA gives it back itself"):
			desktop.reset()
			desktop.nvdaGivesFocusBack = True
			outlook = self.openOutlook()
			self.assertIsNone(outlook.nativeOm)
			self.assertEqual(desktop.foreground, OUTLOOK_WINDOW)
			self.assertEqual(desktop.madeForeground, [], "nothing more to do")
		with self.subTest("you went on to Edge meanwhile"):
			desktop.reset()
			desktop.meanwhile = lambda: desktop.setForeground(EDGE_WINDOW)
			outlook = self.openOutlook()
			self.assertIsNone(outlook.nativeOm)
			self.assertEqual(desktop.foreground, EDGE_WINDOW, "left where you went")
			self.assertEqual(desktop.madeForeground, [])
		with self.subTest("NVDA's own window had the focus before"):
			desktop.reset()
			outlook = self.openOutlook()
			desktop.foreground = NVDA_WINDOW
			self.assertIsNone(outlook.nativeOm)
			self.assertEqual(desktop.waitedOn, ["MainThread"])
			self.assertEqual(desktop.madeForeground, [], "an NVDA dialog you opened isn't taken from you")
		with self.subTest("the window is gone"):
			desktop.reset()
			desktop.foreground = NVDA_WINDOW
			self.assertFalse(outlookFocus.giveFocusBack(0x7FFF0))
			self.assertFalse(outlookFocus.giveFocusBack(0))
			self.assertEqual(desktop.madeForeground, [])
		with self.subTest("no window has the focus"):
			desktop.reset()
			desktop.foreground = 0
			self.assertTrue(outlookFocus.giveFocusBack(OUTLOOK_WINDOW))
			self.assertEqual(desktop.foreground, OUTLOOK_WINDOW)

	def test_other_threads_get_what_nvda_keeps(self):
		desktop = self.desktop
		desktop.outlookListed = True
		outlook = self.openOutlook()
		self.assertIsNone(onThread(lambda: outlook.nativeOm, "Dummy-40"), "even when Outlook is listed, another thread doesn't get it first")
		self.assertEqual(desktop.asked, [])
		model = outlook.nativeOm
		self.assertIsInstance(model, ObjectModel)
		self.assertEqual(desktop.waitedOn, [], "no wait: Outlook answers")
		self.assertIs(onThread(lambda: outlook.nativeOm, "Dummy-41"), model, "once NVDA has it, every thread gets it")
		self.assertEqual(onThread(lambda: outlook.outlookVersion, "Dummy-42"), 16)
		self.assertEqual(desktop.asked, ["MainThread"], "nvda_slave is asked once")

	def test_outlook_extended_and_other_add_ons(self):
		desktop = self.desktop
		Outlook = self.Outlook

		class OutlookExtended(Outlook):
			"""Outlook Extended 3.4's app module, built on NVDA's; its NotificationChecker thread starts with it."""

		class OwnObjectModel(Outlook):
			"""An add-on with a nativeOm of its own, built on NVDA's."""

			def _get_nativeOm(self):
				return super()._get_nativeOm()

		self.Outlook = OutlookExtended
		extended = self.openOutlook()
		self.assertIsInstance(vars(Outlook)["nativeOm"], outlookFocus.MainThreadObjectModel, "the guard goes on NVDA's own class")
		self.assertNotIn("nativeOm", vars(OutlookExtended))
		self.assertEqual(onThread(lambda: extended.outlookVersion, "Thread-31"), 0, "no version yet, as when Outlook doesn't answer")
		self.assertEqual((desktop.asked, desktop.waitedOn), ([], []))
		self.Outlook = OwnObjectModel
		own = self.openOutlook()
		self.assertIsInstance(vars(OwnObjectModel)["nativeOm"], outlookFocus.MainThreadObjectModel, "and on an add-on's own nativeOm")
		self.assertIsNone(onThread(lambda: own.nativeOm, "Dummy-50"))
		self.assertEqual((desktop.asked, desktop.waitedOn), ([], []))
		# Called on another thread in some other way, NVDA's wait still doesn't run there.
		self.assertIsNone(onThread(lambda: own._get_nativeOm(), "Dummy-51"))
		self.assertEqual(desktop.asked, ["Dummy-51"])
		self.assertEqual(desktop.waitedOn, [])
		self.assertEqual(desktop.foreground, OUTLOOK_WINDOW)
		self.assertIsNone(own.nativeOm)
		self.assertEqual(desktop.waitedOn, ["MainThread"])
		self.assertEqual(desktop.foreground, OUTLOOK_WINDOW)

	def test_register_and_unregister(self):
		appModuleHandler = self.appModuleHandler
		Outlook = self.Outlook
		nvdaWait = vars(Outlook)["_registerCOMWithFocusJuggle"]
		self.assertIsNot(appModuleHandler.fetchAppModule, self.nvdaFetchAppModule)
		self.assertIs(appModuleHandler.fetchAppModule.__wrapped__, self.nvdaFetchAppModule)
		self.assertTrue(outlookFocus.isRegistered())
		# NVDA's own class is guarded once, however many Outlooks NVDA meets.
		self.openOutlook()
		self.openOutlook()
		model = vars(Outlook)["nativeOm"]
		wait = vars(Outlook)["_registerCOMWithFocusJuggle"]
		self.assertIsInstance(model, outlookFocus.MainThreadObjectModel)
		self.assertIs(wait.__wrapped__, nvdaWait)
		self.assertEqual(len(outlookFocus._replaced), 2)
		self.assertIsInstance(Outlook.nativeOm, Getter, "the class itself still shows NVDA's own")
		outlookFocus.unregister()
		self.assertFalse(outlookFocus.isRegistered())
		self.assertIs(appModuleHandler.fetchAppModule, self.nvdaFetchAppModule, "NVDA's own again")
		self.assertIsInstance(vars(Outlook)["nativeOm"], Getter)
		self.assertIs(vars(Outlook)["_registerCOMWithFocusJuggle"], nvdaWait)
		# An Outlook already running when the assistant starts is guarded too.
		appModuleHandler.runningTable.clear()
		running = self.Outlook(OUTLOOK_PID, "outlook")
		appModuleHandler.runningTable[OUTLOOK_PID] = running
		outlookFocus.register()
		self.assertIsInstance(vars(Outlook)["nativeOm"], outlookFocus.MainThreadObjectModel)
		# Another add-on wraps fetchAppModule after the assistant: unregistering leaves its wrapper working.
		ours = appModuleHandler.fetchAppModule

		def theirs(*args, **kwargs):
			return ours(*args, **kwargs)

		theirs.__wrapped__ = ours
		appModuleHandler.fetchAppModule = theirs
		outlookFocus.unregister()
		self.assertIs(appModuleHandler.fetchAppModule, theirs)
		self.assertIsInstance(vars(Outlook)["nativeOm"], Getter)
		appModuleHandler.fetchAppModule(OUTLOOK_PID, "outlook")
		self.assertIsInstance(vars(Outlook)["nativeOm"], Getter, "the assistant's wrapper does nothing while it is unregistered")
		outlookFocus.register()
		self.assertIs(appModuleHandler.fetchAppModule, theirs, "and it isn't wrapped twice when it registers again")
		appModuleHandler.fetchAppModule(OUTLOOK_PID, "outlook")
		self.assertIsInstance(vars(Outlook)["nativeOm"], outlookFocus.MainThreadObjectModel)

	def test_other_applications_are_left_alone(self):
		edge = self.appModuleHandler.fetchAppModule(EDGE_PID, "msedge")
		self.assertFalse(outlookFocus.guard(edge))
		self.assertEqual(outlookFocus._replaced, [])

		class Other(metaclass=AutoPropertyType):
			def _get_nativeOm(self):
				return "Word's own"

		self.assertFalse(outlookFocus.guard(Other()), "a nativeOm alone isn't Outlook's")
		self.assertIsInstance(vars(Other)["nativeOm"], Getter)

	def test_never_in_the_way_of_nvda(self):
		desktop = self.desktop
		# The guard failing never keeps NVDA from loading an application's support.
		with mock.patch.object(outlookFocus, "guard", side_effect=RuntimeError("broken for the test")), mock.patch.object(outlookFocus, "_log"):
			outlook = self.appModuleHandler.fetchAppModule(OUTLOOK_PID, "outlook")
		self.assertIsInstance(outlook, self.Outlook)
		# Nor giving the focus back.
		with mock.patch.dict(sys.modules, {"winUser": None}), mock.patch.object(outlookFocus, "_log"):
			self.assertFalse(outlookFocus.giveFocusBack(OUTLOOK_WINDOW))
		# A nativeOm the assistant doesn't know is left as it is.
		Outlook = self.Outlook
		Outlook.nativeOm = property(lambda self: None)
		with mock.patch.object(outlookFocus, "_log"):
			self.assertTrue(outlookFocus.guard(Outlook()))
		self.assertIsInstance(vars(Outlook)["nativeOm"], property)
		# Where NVDA can't tell its main thread, every thread counts as it, and NVDA works as it always has.
		with mock.patch.dict(sys.modules, {"core": types.SimpleNamespace()}):
			self.assertTrue(onThread(outlookFocus.onMainThread, "Dummy-60"))
		self.assertFalse(onThread(outlookFocus.onMainThread, "Dummy-61"))
		self.assertTrue(outlookFocus.onMainThread())
		self.assertEqual(desktop.spoken, [])

	def test_what_nvdas_log_says(self):
		outlook = self.openOutlook()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			onThread(lambda: outlook.nativeOm, "Dummy-32")
			onThread(lambda: outlook.nativeOm, "Dummy-33")
			outlook.nativeOm
		lines = [record.getMessage() for record in logged.records]
		self.assertEqual(len([line for line in lines if "was asked for on the thread 'Dummy-32'" in line]), 1)
		self.assertFalse([line for line in lines if "Dummy-33" in line], "once for each run of Outlook")
		# Version 1.13: "Dummy-32" names nothing, so the note carries the stack that asked (issue 5's log said 'Dummy-241').
		noted = [record for record in logged.records if "was asked for on the thread 'Dummy-32'" in record.getMessage()]
		self.assertIn("test_v111_fixes.py", noted[0].stack_info or "", "the code that asked is in the log")
		self.assertIn("jawsMigrator: NVDA waits for Outlook to offer its object model", lines)
		self.assertIn(
			"jawsMigrator: NVDA's own window kept the focus after NVDA waited for Outlook, so it goes back to the window that had it (rctrl_renwnd32)",
			lines,
		)


if __name__ == "__main__":
	unittest.main()
