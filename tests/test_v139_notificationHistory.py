# Unit tests for version 1.39, from a tester's answers (issue 33, 28 September 2026): "Yes to both questions."
# Question 5: a notification history, NVDA+Shift+J, then N to list the recent notifications and NVDA+Shift+J, then
# Shift+N to hear the last one again, as JAWS's Insert+Space, N and Shift+N. Question 6: D after NVDA+Shift+J, as JAWS's
# Insert+Space, D for audio ducking (F11 and Print Screen, for the screen curtain, are issue 37's).
# - notificationHistory: every UI Automation notification and every toast NVDA gets is kept, as JAWS keeps them
#   (Default.JSS UIANotificationEvent, ProcessNotificationTextAndSpeakIfAllowed, StoreSpokenNotificationForRepeat), and
#   passed on unchanged, so what NVDA says is as before.
# - duckingToggle: D goes between no ducking and ducking while NVDA speaks, with JAWS's "Duck other audio" and "Do not
#   duck other audio".
# The imitation NVDA is NVDA 2026.2's own code, word for word: eventHandler._EventExecuter (the chain of global plugins,
# app module, tree interceptor and object), NVDAObjects.UIA.UIA.event_UIA_notification, NVDAObjects.UIA.Toast_win10
# .event_UIA_window_windowOpen, NVDAObjects.behaviors.Notification.event_alert and globalCommands.GlobalCommands
# .script_cycleAudioDuckingMode, checked against release-2026.2 by CodeTests when NVDA_SOURCE is set. The Edge app module
# is MSEdgeDiscardAnnouncements 0.11.0's own event_UIA_notification (checked when MSEDGE_DISCARD_SOURCE is set), which
# the tester runs. The assistant's code is the real one.
# Run: python -m unittest tests.test_v139_notificationHistory -v

import ast
import enum
import os
import sys
import textwrap
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import duckingToggle, notificationHistory  # noqa: E402

#: NVDA 2026.2, source/eventHandler.py, _EventExecuter.__init__, word for word.
NVDA_EXECUTER_INIT = r'''
def __init__(self, eventName, obj, kwargs):
	self.kwargs = kwargs
	self._gen = self.gen(eventName, obj)
	try:
		self.next()
	except StopIteration:
		pass
	finally:
		del self._gen
'''

#: NVDA 2026.2, source/eventHandler.py, _EventExecuter.next, word for word.
NVDA_EXECUTER_NEXT = r'''
def next(self):
	func, args = next(self._gen)
	try:
		return func(*args, **self.kwargs)
	except TypeError:
		log.warning(
			"Could not execute function {func} defined in {module} module; kwargs: {kwargs}".format(
				func=func.__name__,
				module=func.__module__ or "unknown",
				kwargs=self.kwargs,
			),
			exc_info=True,
		)
		return extensionPoints.callWithSupportedKwargs(func, *args, **self.kwargs)
'''

#: NVDA 2026.2, source/eventHandler.py, _EventExecuter.gen, word for word.
NVDA_EXECUTER_GEN = r'''
def gen(self, eventName, obj):
	funcName = "event_%s" % eventName

	# Global plugin level.
	for plugin in globalPluginHandler.runningPlugins:
		func = getattr(plugin, funcName, None)
		if func:
			yield func, (obj, self.next)

	# App module level.
	app = obj.appModule
	if app:
		func = getattr(app, funcName, None)
		if func:
			yield func, (obj, self.next)

	# Tree interceptor level.
	treeInterceptor = obj.treeInterceptor
	if treeInterceptor:
		func = getattr(treeInterceptor, funcName, None)
		if func and (getattr(func, "ignoreIsReady", False) or treeInterceptor.isReady):
			yield func, (obj, self.next)

	# NVDAObject level.
	func = getattr(obj, funcName, None)
	if func:
		yield func, ()
'''

#: NVDA 2026.2, source/NVDAObjects/UIA/__init__.py, UIA.event_UIA_notification, word for word.
NVDA_UIA_NOTIFICATION = r'''
def event_UIA_notification(
	self,
	notificationKind: int | None = None,
	notificationProcessing: int | None = UIAHandler.NotificationProcessing_CurrentThenMostRecent,
	displayString: str | None = None,
	activityId: str | None = None,
):
	"""
	Introduced in Windows 10 Fall Creators Update (build 16299).
	This base implementation announces all notifications from the UIA element.
	Unlike other events, the text to be announced is not the name of the object, and parameters control how the incoming notification should be processed.
	Subclasses can override this event and can react to notification processing instructions.
	"""
	# Do not announce notifications from background apps.
	if self.appModule != api.getFocusObject().appModule:
		return
	if displayString:
		speechPriority = None
		if notificationProcessing in (
			UIAHandler.NotificationProcessing_ImportantMostRecent,
			UIAHandler.NotificationProcessing_MostRecent,
		):
			# These notifications superseed earlier notifications.
			# Note that no distinction is made between important and non-important.
			# #17986: speak notification message as soon as possible while say all is in progress.
			if speech.sayAll.SayAllHandler.isRunning():
				speechPriority = speech.priorities.Spri.NOW
			else:
				speech.cancelSpeech()
		ui.message(displayString, speechPriority=speechPriority)
'''

#: NVDA 2026.2, source/NVDAObjects/UIA/__init__.py, Toast_win10.event_UIA_window_windowOpen, word for word.
NVDA_TOAST_WINDOW_OPEN = r'''
def event_UIA_window_windowOpen(self):
	if winVersion.getWinVer() >= winVersion.WIN10_1703:
		toastTimestamp = time.time()
		toastRuntimeID = self.UIAElement.getRuntimeID()
		if toastRuntimeID == self._lastToastRuntimeID and toastTimestamp - self._lastToastTimestamp < 1.0:
			return
		self.__class__._lastToastTimestamp = toastTimestamp
		self.__class__._lastToastRuntimeID = toastRuntimeID
	Notification.event_alert(self)
'''

#: NVDA 2026.2, source/NVDAObjects/behaviors.py, Notification.event_alert, word for word.
NVDA_NOTIFICATION_ALERT = r'''
def event_alert(self):
	if not config.conf["presentation"]["reportHelpBalloons"]:
		return
	speech.speakObject(self, reason=controlTypes.OutputReason.FOCUS)
	# Ideally, we wouldn't use getPropertiesBraille directly.
	braille.handler.message(braille.getPropertiesBraille(name=self.name, role=self.role))
'''

#: NVDA 2026.2, source/globalCommands.py, GlobalCommands.script_cycleAudioDuckingMode, word for word.
NVDA_CYCLE_DUCKING = r'''
def script_cycleAudioDuckingMode(self, gesture):
	if not audioDucking.isAudioDuckingSupported() or audioDucking._isAudioDuckingSuspended():
		# Translators: a message when audio ducking is not supported on this machine
		ui.message(_("Audio ducking not supported"))
		return
	curMode = config.conf["audio"]["audioDuckingMode"]
	numModes = len(audioDucking.AudioDuckingMode)
	nextMode = (curMode + 1) % numModes
	audioDucking.setAudioDuckingMode(nextMode)
	config.conf["audio"]["audioDuckingMode"] = nextMode
	nextLabel = audioDucking.AudioDuckingMode(nextMode).displayString
	ui.message(nextLabel)
'''

#: MSEdgeDiscardAnnouncements 0.11.0, addon/appModules/msedge/__init__.py, AppModule.event_UIA_notification, word for word.
ADDON_EDGE_NOTIFICATION = r'''
def event_UIA_notification(self, obj, nextHandler, activityId=None, **kwargs):
    eventConfig = self.eventConfigs.get(activityId)
    if eventConfig is None:
        nextHandler()
        return
    if eventConfig.mode == Mode.OFF:
        return
    if "HubDownloads" in activityId:
        foreground = api.getForegroundObject()
        if obj.appModule == foreground.appModule and not obj.isDescendantOf(foreground):
            return
    if eventConfig.mode == Mode.BEEPS:
        beeps.playPattern(eventConfig.beepPattern)
        return
    if eventConfig.mode == Mode.WAVE:
        if not playFile(eventConfig.waveFile, eventConfig.waveVolume):
            nextHandler()
        return
    if eventConfig.useCustomMessage and eventConfig.customMessage:
        ui.message(eventConfig.customMessage)
        return
    nextHandler()
'''

#: What NVDA said: ui.message's text, and speakObject's object names.
said = []


class Spri(enum.Enum):
	NOW = "now"


speech = types.SimpleNamespace(
	cancelSpeech=lambda: said.append("(speech cancelled)"),
	sayAll=types.SimpleNamespace(SayAllHandler=types.SimpleNamespace(isRunning=lambda: False)),
	priorities=types.SimpleNamespace(Spri=Spri),
	speakObject=lambda obj, reason=None: said.append(obj.name),
)
ui = types.SimpleNamespace(message=lambda text, speechPriority=None: said.append(text))
UIAHandler = types.SimpleNamespace(
	NotificationProcessing_ImportantAll=0,
	NotificationProcessing_ImportantMostRecent=1,
	NotificationProcessing_All=2,
	NotificationProcessing_MostRecent=3,
	NotificationProcessing_CurrentThenMostRecent=4,
)
#: NVDA's Report notifications (presentation, reportHelpBalloons), on as NVDA comes.
conf = {"presentation": {"reportHelpBalloons": True}, "audio": {"audioDuckingMode": 0}}
config = types.SimpleNamespace(conf=conf)
braille = types.SimpleNamespace(
	handler=types.SimpleNamespace(message=lambda text: None),
	getPropertiesBraille=lambda **kwargs: "",
)
controlTypes = types.SimpleNamespace(OutputReason=types.SimpleNamespace(FOCUS="focus"))
winVersion = types.SimpleNamespace(getWinVer=lambda: 26200, WIN10_1703=15063, WIN10_1511=10586)
focus = {"object": None}
api = types.SimpleNamespace(getFocusObject=lambda: focus["object"], getForegroundObject=lambda: focus["object"])


class GlobalPluginHandler:
	runningPlugins = []


namespace = {
	"globalPluginHandler": GlobalPluginHandler,
	"log": mock.Mock(),
	"extensionPoints": types.SimpleNamespace(callWithSupportedKwargs=lambda func, *args, **kwargs: func(*args)),
	"speech": speech,
	"ui": ui,
	"UIAHandler": UIAHandler,
	"api": api,
	"config": config,
	"braille": braille,
	"controlTypes": controlTypes,
	"winVersion": winVersion,
	"time": __import__("time"),
}
_methods = {}
for _name, _method in (("NVDA_EXECUTER_INIT", "__init__"), ("NVDA_EXECUTER_NEXT", "next"), ("NVDA_EXECUTER_GEN", "gen")):
	# Taken out of the namespace it was made in: in NVDA it is a method, and "next" in it is Python's own.
	_own = dict(namespace)
	exec(globals()[_name], _own)
	_methods[_method] = _own.pop(_method)
_EventExecuter = type("_EventExecuter", (), _methods)

exec(NVDA_NOTIFICATION_ALERT, namespace)


class Notification:
	"""NVDAObjects.behaviors.Notification."""

	event_alert = namespace["event_alert"]


namespace["Notification"] = Notification
exec(NVDA_UIA_NOTIFICATION, namespace)
exec(NVDA_TOAST_WINDOW_OPEN, namespace)


class AppModule:
	"""NVDA's AppModule, of a program NVDA got a notification from."""

	def __init__(self, appName):
		self.appName = appName


class UIA:
	"""An NVDAObjects.UIA.UIA object, with NVDA's own event_UIA_notification."""

	treeInterceptor = None
	role = "toolTip"
	event_UIA_notification = namespace["event_UIA_notification"]

	def __init__(self, appModule, name=""):
		self.appModule = appModule
		self.name = name
		self.description = ""

	def isDescendantOf(self, obj):
		return True


class RuntimeID:
	def __init__(self, value):
		self.value = value

	def getRuntimeID(self):
		return self.value


class Toast_win10(Notification, UIA):
	"""A Windows notification: NVDAObjects.UIA.Toast_win10, on Windows 11."""

	_lastToastTimestamp = None
	_lastToastRuntimeID = None
	event_UIA_window_windowOpen = namespace["event_UIA_window_windowOpen"]

	def __init__(self, name, runtimeID=(42, 1)):
		super().__init__(AppModule("shellexperiencehost"), name)
		self.UIAElement = RuntimeID(runtimeID)


# MSEdgeDiscardAnnouncements 0.11.0's app module for Edge, with its own event_UIA_notification.
class Mode(enum.Enum):
	OFF = "off"
	SPEAK = "speak"
	BEEPS = "beeps"
	WAVE = "wave"


class EventConfigs(dict):
	pass


_addonNamespace = {"Mode": Mode, "api": api, "ui": ui, "beeps": None, "playFile": None}
exec(
	"class EdgeAppModule(AppModule):\n" + textwrap.indent(ADDON_EDGE_NOTIFICATION.strip(), "    ") + "\n",
	dict(_addonNamespace, AppModule=AppModule),
	_addonNamespace,
)
EdgeAppModule = _addonNamespace["EdgeAppModule"]


def edgeAppModule():
	app = EdgeAppModule("msedge")
	# As the tester has it (their nvda.ini): Edge's "Loading page" off, "Going back" as the add-on comes (off).
	app.eventConfigs = EventConfigs(
		PageLoading=types.SimpleNamespace(mode=Mode.OFF),
		GoingBack=types.SimpleNamespace(mode=Mode.OFF),
		HubDownloadsInProgressState=types.SimpleNamespace(mode=Mode.SPEAK, useCustomMessage=False, customMessage=""),
	)
	return app


def plugin():
	"""The assistant's global plugin, without its start, which needs NVDA."""
	return jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)


def fire(eventName, obj, **kwargs):
	"""NVDA's eventHandler.executeEvent, as far as it runs the chain: the assistant's plugin, then the rest."""
	_EventExecuter(eventName, obj, kwargs)


class _Stubbed(unittest.TestCase):
	def setUp(self):
		patcher = mock.patch.dict(
			sys.modules,
			{
				"ui": ui,
				"api": types.SimpleNamespace(copyToClip=lambda text: True),
				"NVDAObjects": types.ModuleType("NVDAObjects"),
				"NVDAObjects.behaviors": types.SimpleNamespace(Notification=Notification),
			},
		)
		patcher.start()
		self.addCleanup(patcher.stop)
		GlobalPluginHandler.runningPlugins = [plugin()]
		said.clear()
		conf["presentation"]["reportHelpBalloons"] = True
		Toast_win10._lastToastTimestamp = Toast_win10._lastToastRuntimeID = None
		notificationHistory.unregister()
		notificationHistory.register()
		self.addCleanup(notificationHistory.unregister)
		self.edge = edgeAppModule()
		self.outlook = AppModule("outlook")
		self.teams = AppModule("ms-teams")
		focus["object"] = UIA(self.edge, "Issues · joshknnd1982/jawsMigrator")

	def kept(self):
		return [(item.text, item.app) for item in notificationHistory.entries()]


class UIANotificationTests(_Stubbed):
	def test_saidAsBeforeAndKept(self):
		fire("UIA_notification", UIA(self.edge), displayString="Download complete", activityId="HubDownloadsInProgressState")
		self.assertEqual(said, ["Download complete"])
		self.assertEqual(self.kept(), [("Download complete", "msedge")])

	def test_oneTheEdgeAddonKeepsSilentIsKept(self):
		# JAWS keeps a notification it doesn't say ("We want to store even if we don't speak").
		fire("UIA_notification", UIA(self.edge), displayString="Loading page", activityId="PageLoading")
		fire("UIA_notification", UIA(self.edge), displayString="Going back", activityId="GoingBack")
		self.assertEqual(said, [])
		self.assertEqual(self.kept(), [("Going back", "msedge"), ("Loading page", "msedge")])

	def test_aProgramInTheBackgroundIsKept(self):
		# NVDA says notifications of the program in front only; JAWS keeps them from any program.
		fire("UIA_notification", UIA(self.teams), displayString="Dennis is calling", activityId="Call")
		self.assertEqual(said, [])
		self.assertEqual(self.kept(), [("Dennis is calling", "ms-teams")])

	def test_whatJawsLeavesOut(self):
		focus["object"] = UIA(self.outlook)
		fire("UIA_notification", UIA(self.outlook), displayString="English (United States)", activityId="Windows.Shell.InputSwitch.SwitchNotification")
		fire("UIA_notification", UIA(self.outlook), displayString="C:\\> dir", activityId="TerminalTextOutput")
		self.assertEqual(said, ["English (United States)", "C:\\> dir"])
		self.assertEqual(self.kept(), [])

	def test_theSameAgainAtOnceIsOne(self):
		import time

		now = time.time()
		self.assertTrue(notificationHistory.note("Saved", "outlook", monotonic=10.0, now=now))
		self.assertFalse(notificationHistory.note("Saved", "outlook", monotonic=10.4, now=now + 0.4))
		self.assertTrue(notificationHistory.note("Saved", "outlook", monotonic=11.0, now=now + 1))
		self.assertEqual(len(notificationHistory.entries()), 2)

	def test_onlyTheLastOfAFlood(self):
		for number in range(5):
			notificationHistory.note(f"Moved to {number * 10}, 100", "snippingtool", "HandleMoved", monotonic=20.0 + number * 0.1)
		notificationHistory.note("Snip saved", "snippingtool", monotonic=21.0)
		self.assertEqual(self.kept(), [("Snip saved", "snippingtool"), ("Moved to 40, 100", "snippingtool")])

	def test_theLast500OfTheLast24Hours(self):
		import time

		now = time.time()
		notificationHistory.note("Yesterday's", "outlook", now=now - 25 * 60 * 60, monotonic=1.0)
		for number in range(600):
			notificationHistory.note(f"Message {number}", "outlook", now=now, monotonic=2.0 + number)
		kept = self.kept()
		self.assertEqual(len(kept), 500)
		self.assertEqual(kept[0][0], "Message 599")
		self.assertNotIn(("Yesterday's", "outlook"), kept)

	def test_withoutAProgram(self):
		notificationHistory.note("Something happened")
		self.assertEqual(self.kept(), [("Something happened", "Unknown app")])

	def test_theEventGoesOnWhenKeepingFails(self):
		with mock.patch.object(notificationHistory, "fromUIANotification", side_effect=RuntimeError):
			fire("UIA_notification", UIA(self.edge), displayString="Download complete", activityId="HubDownloadsInProgressState")
		self.assertEqual(said, ["Download complete"])

	def test_turnedOffNothingIsKeptAndItsForgotten(self):
		fire("UIA_notification", UIA(self.edge), displayString="Download complete", activityId="HubDownloadsInProgressState")
		notificationHistory.unregister()
		self.assertEqual(notificationHistory.entries(), [])
		fire("UIA_notification", UIA(self.edge), displayString="Download complete again", activityId="HubDownloadsInProgressState")
		self.assertEqual(notificationHistory.entries(), [])
		self.assertEqual(said, ["Download complete", "Download complete again"])


class ToastTests(_Stubbed):
	OUTLOOK = "New notification from Outlook, Dennisl123, Re: [joshknnd1982/jawsMigrator] a few things missing (Issue #34)"

	def test_saidAsBeforeAndKeptWithItsProgram(self):
		fire("UIA_window_windowOpen", Toast_win10(self.OUTLOOK))
		self.assertEqual(said, [self.OUTLOOK])
		self.assertEqual(self.kept(), [(self.OUTLOOK, "Outlook")])

	def test_keptWithNotificationsOff(self):
		# NVDA's Report notifications off: NVDA says nothing, and JAWS keeps it all the same.
		conf["presentation"]["reportHelpBalloons"] = False
		fire("UIA_window_windowOpen", Toast_win10(self.OUTLOOK))
		self.assertEqual(said, [])
		self.assertEqual(self.kept(), [(self.OUTLOOK, "Outlook")])

	def test_aToastWindowsSendsTwiceIsOne(self):
		# NVDA's own leaves out the same toast within a second; so does the history.
		toast = Toast_win10(self.OUTLOOK)
		fire("UIA_window_windowOpen", toast)
		fire("UIA_window_windowOpen", toast)
		self.assertEqual(said, [self.OUTLOOK])
		self.assertEqual(len(self.kept()), 1)

	def test_otherWindowsAreNotNotifications(self):
		fire("UIA_window_windowOpen", UIA(self.outlook, "Inbox - Outlook"))
		self.assertEqual(self.kept(), [])

	def test_aToastWithoutItsProgram(self):
		fire("UIA_window_windowOpen", Toast_win10("Your device is up to date", runtimeID=(7,)))
		self.assertEqual(self.kept(), [("Your device is up to date", "Unknown app")])


class CommandTests(_Stubbed):
	def test_shiftNSaysTheLastAgain(self):
		fire("UIA_notification", UIA(self.edge), displayString="Download complete", activityId="HubDownloadsInProgressState")
		fire("UIA_notification", UIA(self.edge), displayString="Loading page", activityId="PageLoading")
		said.clear()
		plugin().repeatLastNotification()
		self.assertEqual(said, ["Loading page"])

	def test_shiftNWithoutAny(self):
		plugin().repeatLastNotification()
		self.assertEqual(said, ["No notification"])

	def test_turnedOff(self):
		notificationHistory.unregister()
		plugin().repeatLastNotification()
		self.assertEqual(said, [notificationHistory.DISABLED])

	def test_nWithoutAny(self):
		p = plugin()
		p._secure = False
		p.showNotificationHistory()
		self.assertEqual(said, ["No notification"])

	def test_details(self):
		import time

		now = time.time()
		notificationHistory.note("Download complete", "msedge", now=now)
		text = notificationHistory.details(notificationHistory.last())
		lines = text.split("\n")
		self.assertEqual(lines[0], "Download complete")
		self.assertEqual(lines[1], "Application: msedge")
		self.assertTrue(lines[2].startswith("Received: "))
		self.assertIn(time.strftime("%Y", time.localtime(now)), lines[2])

	def test_theLayersKeys(self):
		keys = {script: (gestures, key) for gestures, script, key, _words in jawsMigrator.LAYER_COMMANDS}
		self.assertEqual(keys["showNotificationHistory"], (("kb:n",), "N"))
		self.assertEqual(keys["repeatLastNotification"], (("kb:shift+n",), "Shift+N"))
		self.assertEqual(keys["toggleAudioDucking"], (("kb:d",), "D"))
		for script in ("showNotificationHistory", "repeatLastNotification", "toggleAudioDucking"):
			self.assertTrue(callable(getattr(jawsMigrator.GlobalPlugin, f"script_{script}", None)), script)


try:
	import wx

	_app = wx.App.Get() or wx.App(False)
except Exception:  # pragma: no cover - wx is part of the test setup
	wx = None


@unittest.skipIf(wx is None, "wxPython isn't installed")
class WindowTests(_Stubbed):
	def tearDown(self):
		notificationHistory.closeViewer()

	def test_theMostRecentFirstAndOnIt(self):
		notificationHistory.note("First", "outlook", monotonic=1.0)
		notificationHistory.note("Second", "msedge", monotonic=2.0)
		self.assertTrue(notificationHistory.showAndSay())
		viewer = notificationHistory._viewer
		self.assertEqual(viewer.GetTitle(), "Notification History")
		self.assertEqual([viewer.list.GetString(index) for index in range(viewer.list.GetCount())], ["Second", "First"])
		self.assertEqual(viewer.list.GetSelection(), 0)
		self.assertEqual(viewer.selected().app, "msedge")

	def test_clearHistory(self):
		notificationHistory.note("First", "outlook", monotonic=1.0)
		notificationHistory.showAndSay()
		viewer = notificationHistory._viewer
		viewer._onClear(None)
		self.assertEqual(viewer.list.GetCount(), 0)
		self.assertEqual(notificationHistory.entries(), [])
		self.assertIn(notificationHistory.CLEARED, said)

	def test_copy(self):
		copied = []
		notificationHistory.note("Copy me", "outlook", monotonic=1.0)
		notificationHistory.showAndSay()
		with mock.patch.dict(sys.modules, {"api": types.SimpleNamespace(copyToClip=lambda text: copied.append(text) or True)}):
			notificationHistory._viewer._onCopy(None)
		self.assertEqual(copied, ["Copy me"])
		self.assertIn("Copied", said)

	def test_nAgainShowsWhatIsNew(self):
		notificationHistory.note("First", "outlook", monotonic=1.0)
		notificationHistory.showAndSay()
		viewer = notificationHistory._viewer
		notificationHistory.note("Newer", "outlook", monotonic=2.0)
		notificationHistory.showAndSay()
		self.assertIs(notificationHistory._viewer, viewer)
		self.assertEqual(viewer.list.GetString(0), "Newer")


class DuckingTests(unittest.TestCase):
	def setUp(self):
		said.clear()
		self.modes = types.SimpleNamespace(NONE=0, OUTPUTTING=1, ALWAYS=2)
		self.set = []
		self.supported = True
		audioDucking = types.SimpleNamespace(
			AudioDuckingMode=self.modes,
			isAudioDuckingSupported=lambda: self.supported,
			_isAudioDuckingSuspended=lambda: False,
			setAudioDuckingMode=self.set.append,
		)
		patcher = mock.patch.dict(sys.modules, {"audioDucking": audioDucking, "config": config, "ui": ui})
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_onAndOffAsJaws(self):
		conf["audio"]["audioDuckingMode"] = 0
		self.assertTrue(duckingToggle.toggle())
		self.assertEqual((self.set, conf["audio"]["audioDuckingMode"]), ([1], 1))
		self.assertTrue(duckingToggle.toggle())
		self.assertEqual((self.set, conf["audio"]["audioDuckingMode"]), ([1, 0], 0))
		self.assertEqual(said, ["Duck other audio", "Do not duck other audio"])

	def test_fromAlwaysDuckItGoesOff(self):
		conf["audio"]["audioDuckingMode"] = 2
		duckingToggle.toggle()
		self.assertEqual(conf["audio"]["audioDuckingMode"], 0)
		self.assertEqual(said, ["Do not duck other audio"])

	def test_whereNvdaCantDuck(self):
		self.supported = False
		conf["audio"]["audioDuckingMode"] = 0
		self.assertFalse(duckingToggle.toggle())
		self.assertEqual(said, ["Audio ducking not supported"])
		self.assertEqual(self.set, [])

	def test_nvdasOwnGoesThroughThree(self):
		# NVDA's NVDA+Shift+D, as it is: three modes, where JAWS's D has two.
		conf["audio"]["audioDuckingMode"] = 0
		labels = {0: "No ducking", 1: "Duck when outputting speech and sounds", 2: "Always duck"}
		audioDucking = sys.modules["audioDucking"]
		audioDucking.AudioDuckingMode = type("Modes", (), {"__len__": lambda self: 3, "__call__": lambda self, mode: types.SimpleNamespace(displayString=labels[mode])})()
		cycle = {}
		exec(NVDA_CYCLE_DUCKING, {"audioDucking": audioDucking, "config": config, "ui": ui, "_": lambda text: text}, cycle)
		for _ in range(3):
			cycle["script_cycleAudioDuckingMode"](None, None)
		self.assertEqual(said, ["Duck when outputting speech and sounds", "Always duck", "No ducking"])


#: Where each piece of code above is: NVDA 2026.2's source (NVDA_SOURCE) or the add-on's (MSEDGE_DISCARD_SOURCE):
#: (variable, file, class, function).
CODE = {
	"NVDA_EXECUTER_INIT": ("NVDA_SOURCE", "eventHandler.py", "_EventExecuter", "__init__"),
	"NVDA_EXECUTER_NEXT": ("NVDA_SOURCE", "eventHandler.py", "_EventExecuter", "next"),
	"NVDA_EXECUTER_GEN": ("NVDA_SOURCE", "eventHandler.py", "_EventExecuter", "gen"),
	"NVDA_UIA_NOTIFICATION": ("NVDA_SOURCE", "NVDAObjects/UIA/__init__.py", "UIA", "event_UIA_notification"),
	"NVDA_TOAST_WINDOW_OPEN": ("NVDA_SOURCE", "NVDAObjects/UIA/__init__.py", "Toast_win10", "event_UIA_window_windowOpen"),
	"NVDA_NOTIFICATION_ALERT": ("NVDA_SOURCE", "NVDAObjects/behaviors.py", "Notification", "event_alert"),
	"NVDA_CYCLE_DUCKING": ("NVDA_SOURCE", "globalCommands.py", "GlobalCommands", "script_cycleAudioDuckingMode"),
	"ADDON_EDGE_NOTIFICATION": ("MSEDGE_DISCARD_SOURCE", "addon/appModules/msedge/__init__.py", "AppModule", "event_UIA_notification"),
}


def _find(path, className, name):
	with open(path, encoding="utf-8") as file:
		text = file.read()
	tree = ast.parse(text)
	body = next((node.body for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == className), [])
	for item in body:
		if isinstance(item, ast.FunctionDef) and item.name == name:
			return textwrap.dedent(ast.get_source_segment(text, item, padded=True))
	return ""


class CodeTests(unittest.TestCase):
	def test_theCodeIsNvdasAndTheAddons(self):
		checked = 0
		for name, (variable, path, className, function) in CODE.items():
			source = os.environ.get(variable)
			if not source:
				continue
			self.assertEqual(globals()[name].strip(), _find(os.path.join(source, path), className, function).strip(), name)
			checked += 1
		if not checked:
			self.skipTest("neither NVDA_SOURCE nor MSEDGE_DISCARD_SOURCE is set")


if __name__ == "__main__":
	unittest.main()
