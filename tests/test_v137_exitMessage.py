# Unit tests for version 1.37, from the tester's answer on issue 34, "a few things missing". Asked 'JAWS says "Unloading
# JAWS" as it exits, and NVDA exits without a word. Would you like NVDA to say something as it exits?', the tester wrote:
#   I'm leaning to no as I turn that off in jaws. However probably the best way to handle that is if they have it speak a
#   conformation when unloading Jaws you do the same for NVDA. What are your thoughts. This could be able to be turned
#   off just like you can in Jaws. If it is turned off in Jaws nothing changes.
# JAWS 2026's Insert+F4 runs ShutDownJAWS (Default.JSS), which says cmsg26_L, "Unloading JAWS" (common.jsm), as
# ot_JAWS_message, then unloads JAWS. JAWS Messages are one of Settings Center's "Items to be Spoken" at each verbosity
# level: Default.jcf's [OutputModes] JAWS_MESSAGE=1|2|0|JAWS Message, Beginner|Intermediate|Advanced (checked in
# JawsTests when JAWS 2026 is installed).
# - settingsMap brings JAWS Messages at the user's verbosity level over as the assistant's "sayUnloadingNvda"; for an
#   application's settings nothing (MappingTests).
# - exitMessage.checkOnce does the same once for a migration made before 1.37, from JAWS's Default.jcf as JAWS runs it,
#   and changes nothing where JAWS says no "Unloading JAWS" (CheckOnceTests).
# - exitMessage puts its triggerNVDAExit in the place of NVDA's: NVDA says "Unloading NVDA", and exits once it is said
#   (ExitTests). NVDA 2026.2's own code runs here: core.triggerNVDAExit and core.restart, NVDAState._setExitCode,
#   GlobalCommands.script_quit, MainFrame.onExitCommand and ExitDialog.onOk, checked word for word against NVDA's source
#   when NVDA_SOURCE is set (NvdasOwnCodeTests). What is imitated: NVDA's queue (queueFunction notes what it is given),
#   wx (CallAfter and CallLater note theirs, run by the test), the synthesizer (the test says when it has said the
#   message; NVDA's speech manager then runs the CallbackCommand), speech.cancelSpeech (NVDA's own logic, around an
#   imitation speech manager), and NVDA's _doShutdown (noted). The tester's log (NVDA.log 2026-09-28 11.23.03, nvda-old.log)
#   shows why NVDA must wait: "_doShutdown has been queued", then core.main's "Exiting" 0.2 seconds later, after which
#   NVDA stops speech.
# Run: python -m unittest tests.test_v137_exitMessage -v

import dataclasses
import enum
import os
import sys
import tempfile
import threading
import types
import unittest
from typing import Optional
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import exitMessage, jawsFiles, migrator, nvdaEnv, settingsMap, state  # noqa: E402

JAWS_ROOT = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Freedom Scientific", "JAWS", "2026")

#: NVDA 2026.2, source/core.py.
NVDA_TRIGGER_EXIT = r'''
def triggerNVDAExit(newNVDA: Optional[NewNVDAInstance] = None) -> bool:
	"""
	Used to safely exit NVDA. If a new instance is required to start after exit, queue one by specifying
	instance information with `newNVDA`.
	@return: True if this is the first call to trigger the exit, and the shutdown event was queued.
	"""
	from gui.message import isModalMessageBoxActive
	import queueHandler

	global _hasShutdownBeenTriggered
	with _shuttingDownFlagLock:
		safeToExit = not isModalMessageBoxActive()
		if not safeToExit:
			log.error("NVDA cannot exit safely, ensure open dialogs are closed")
			return False
		elif _hasShutdownBeenTriggered:
			log.debug("NVDA has already been triggered to exit safely.")
			return False
		else:
			# queue this so that the calling process can exit safely (eg a Popup menu)
			queueHandler.queueFunction(queueHandler.eventQueue, _doShutdown, newNVDA)
			_hasShutdownBeenTriggered = True
			log.debug("_doShutdown has been queued")
			return True
'''

#: NVDA 2026.2, source/core.py.
NVDA_RESTART = r'''
def restart(disableAddons=False, debugLogging=False):
	"""Restarts NVDA by starting a new copy."""
	if globalVars.appArgs.launcher:
		NVDAState._setExitCode(3)
		if not triggerNVDAExit():
			log.error("NVDA already in process of exiting, this indicates a logic error.")
		return
	import subprocess

	restartCLIArgs = computeRestartCLIArgs(
		removeArgsList=["disableAddons", "debugLogging", "language", "easeOfAccess"],
	)
	options = []
	if NVDAState.isRunningAsSource():
		options.append(os.path.basename(sys.argv[0]))
	if disableAddons:
		options.append("--disable-addons")
	if debugLogging:
		options.append("--debug-logging")

	if not triggerNVDAExit(
		NewNVDAInstance(
			sys.executable,
			subprocess.list2cmdline(options + restartCLIArgs),
			globalVars.appDir,
		),
	):
		log.error("NVDA already in process of exiting, this indicates a logic error.")
'''

#: NVDA 2026.2, source/NVDAState.py.
NVDA_SET_EXIT_CODE = r'''
def _setExitCode(exitCode: int) -> None:
	globalVars.exitCode = exitCode
'''

#: NVDA 2026.2, source/gui/exit.py, class ExitDialog: its OK button.
NVDA_EXIT_DIALOG_OK = r'''
def onOk(self, evt):
	action = [a for a in _ExitAction if a.displayString == self.actionsList.GetStringSelection()][0]
	if action == _ExitAction.EXIT:
		WelcomeDialog.closeInstances()
		if core.triggerNVDAExit():
			# there's no need to destroy ExitDialog in this instance as triggerNVDAExit will do this
			return
		else:
			log.error("NVDA already in process of exiting, this indicates a logic error.")
			return
	elif action == _ExitAction.RESTART:
		queueHandler.queueFunction(queueHandler.eventQueue, core.restart)
	elif action == _ExitAction.RESTART_WITH_ADDONS_DISABLED:
		queueHandler.queueFunction(
			queueHandler.eventQueue,
			core.restart,
			disableAddons=True,
		)
	elif action == _ExitAction.RESTART_WITH_ADDONS_DISABLED_AND_DEBUG_LOGGING_ENABLED:
		queueHandler.queueFunction(
			queueHandler.eventQueue,
			core.restart,
			disableAddons=True,
			debugLogging=True,
		)
	elif action == _ExitAction.RESTART_WITH_DEBUG_LOGGING_ENABLED:
		queueHandler.queueFunction(queueHandler.eventQueue, core.restart, debugLogging=True)
	elif action == _ExitAction.INSTALL_PENDING_UPDATE:
		if updateCheck:
			from _remoteClient import _remoteClient

			if (
				_remoteClient is not None
				and _remoteClient.isConnectedAsFollower
				and not updateCheck._warnAndConfirmIfUpdatingRemotely()
			):
				return
			destPath, version, apiVersion, backCompatTo = updateCheck.getPendingUpdate()
			from addonHandler import getIncompatibleAddons
			from gui import mainFrame

			if any(
				getIncompatibleAddons(currentAPIVersion=apiVersion, backCompatToAPIVersion=backCompatTo),
			):
				confirmUpdateDialog = updateCheck.UpdateAskInstallDialog(
					parent=mainFrame,
					destPath=destPath,
					version=version,
					apiVersion=apiVersion,
					backCompatTo=backCompatTo,
				)
				confirmUpdateDialog.callback(displayDialogAsModal(confirmUpdateDialog))
			else:
				updateCheck.executePendingUpdate()
	wx.CallAfter(self.Destroy)
'''

#: NVDA 2026.2, source/globalCommands.py, class GlobalCommands: NVDA+Q (a migration gives it JAWS's Insert+F4).
NVDA_QUIT = r'''
@script(
	# Translators: Input help mode message for quit NVDA command.
	description=_("Quits NVDA!"),
	gesture="kb:NVDA+q",
)
def script_quit(self, gesture):
	wx.CallAfter(gui.mainFrame.onExitCommand, None)
'''

#: NVDA 2026.2, source/gui/__init__.py, class MainFrame: what quit and NVDA's menu's Exit run.
NVDA_ON_EXIT_COMMAND = r'''
@blockAction.when(blockAction.Context.MODAL_DIALOG_OPEN)
def onExitCommand(self, evt):
	if config.conf["general"]["askToExit"]:
		self.prePopup()
		d = ExitDialog(self)
		d.Raise()
		d.Show()
		self.postPopup()
	else:
		if not core.triggerNVDAExit():
			log.error("NVDA already in process of exiting, this indicates a logic error.")
'''

NVDA_CODE_FILES = {
	"NVDA_TRIGGER_EXIT": "core.py",
	"NVDA_RESTART": "core.py",
	"NVDA_SET_EXIT_CODE": "NVDAState.py",
	"NVDA_EXIT_DIALOG_OK": "gui/exit.py",
	"NVDA_QUIT": "globalCommands.py",
	"NVDA_ON_EXIT_COMMAND": "gui/__init__.py",
}

SAID = "Unloading NVDA"


def nvdaSource():
	source = os.environ.get("NVDA_SOURCE")
	if not source:
		raise unittest.SkipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
	return source


def needsJaws(test):
	return unittest.skipUnless(os.path.isdir(os.path.join(JAWS_ROOT, "Scripts")), "JAWS 2026 isn't installed")(test)


class Action:
	"""NVDA's extensionPoints.Action, as far as used: handlers called in order with the keyword arguments."""

	def __init__(self):
		self.handlers = []

	def register(self, handler):
		if handler not in self.handlers:
			self.handlers.append(handler)

	def unregister(self, handler):
		if handler in self.handlers:
			self.handlers.remove(handler)

	def notify(self, **kwargs):
		for handler in list(self.handlers):
			handler(**kwargs)


class Decider(Action):
	"""NVDA's extensionPoints.Decider: NVDA goes on only when every handler returns True."""

	def decide(self, **kwargs):
		return all([handler(**kwargs) for handler in list(self.handlers)])


class Timer:
	def __init__(self, wx, milliseconds, function, args, kwargs):
		self.wx, self.milliseconds, self.function, self.args, self.kwargs = wx, milliseconds, function, args, kwargs
		self.running = True

	def Stop(self):
		self.running = False

	def fire(self):
		if self.running:
			self.running = False
			self.function(*self.args, **self.kwargs)


class Wx(types.ModuleType):
	"""wx, as far as used: CallAfter and CallLater note what they are given; the test runs it."""

	def __init__(self):
		super().__init__("wx")
		self.after = []
		self.timers = []
		self.mainLoopRunning = True
		test = self

		class App:
			def IsMainLoopRunning(self):
				return test.mainLoopRunning

		self._app = App()

	def CallAfter(self, function, *args, **kwargs):
		self.after.append((function, args, kwargs))

	def CallLater(self, milliseconds, function, *args, **kwargs):
		timer = Timer(self, milliseconds, function, args, kwargs)
		self.timers.append(timer)
		return timer

	def GetApp(self):
		return self._app

	def runPending(self):
		while self.after:
			function, args, kwargs = self.after.pop(0)
			function(*args, **kwargs)


class SpeechMode(enum.IntEnum):
	off = 0
	beeps = 1
	talk = 2
	onDemand = 3


class Spri(enum.IntEnum):
	NORMAL = 0
	NEXT = 1
	NOW = 2


class CallbackCommand:
	"""NVDA's speech.commands.CallbackCommand, as far as used: the speech manager runs it once speech reaches it."""

	def __init__(self, callback, name=None):
		self._callback = callback
		self._name = name

	def run(self, *args, **kwargs):
		return self._callback(*args, **kwargs)


class Speech(types.ModuleType):
	"""NVDA's speech, as far as used, with a synthesizer the test drives."""

	def __init__(self, extensions):
		super().__init__("speech")
		self.SpeechMode = SpeechMode
		self.Spri = Spri
		self.extensions = extensions
		self.state = types.SimpleNamespace(speechMode=SpeechMode.talk, isPaused=False, beenCanceled=True)
		#: Every sequence speak was given, with its priority.
		self.spoken = []
		#: What the synthesizer is still to say.
		self.current = []

	def getState(self):
		return types.SimpleNamespace(**vars(self.state))

	def speak(self, speechSequence, symbolLevel=None, priority=None):
		self.spoken.append((list(speechSequence), priority))
		if self.state.speechMode != SpeechMode.talk or self.state.isPaused:
			return
		self.state.beenCanceled = False
		self.current.append(list(speechSequence))

	def cancelSpeech(self):
		# NVDA 2026.2's cancelSpeech, around this speech manager.
		self.extensions.pre_speechCanceled.notify()
		if self.state.beenCanceled:
			return
		elif self.state.speechMode in (SpeechMode.off, SpeechMode.beeps):
			return
		self.current.clear()
		self.extensions.speechCanceled.notify()
		self.state.beenCanceled = True
		self.state.isPaused = False

	def synthSaysAll(self):
		"""The synthesizer says what it was given; NVDA's speech manager runs each CallbackCommand as speech reaches it."""
		while self.current:
			for item in self.current.pop(0):
				if isinstance(item, CallbackCommand):
					item.run()


@dataclasses.dataclass
class NewNVDAInstance:
	filePath: str
	parameters: Optional[str] = None
	directory: Optional[str] = None


class ExitAction(enum.Enum):
	"""NVDA's gui.exit._ExitAction, with its display strings."""

	EXIT = "Exit"
	RESTART = "Restart"
	RESTART_WITH_ADDONS_DISABLED_AND_DEBUG_LOGGING_ENABLED = "Restart with add-ons disabled and debug logging enabled"
	RESTART_WITH_ADDONS_DISABLED = "Restart with add-ons disabled"
	RESTART_WITH_DEBUG_LOGGING_ENABLED = "Restart with debug logging enabled"
	INSTALL_PENDING_UPDATE = "Install pending update"

	@property
	def displayString(self):
		return self.value


def run(code: str, namespace: dict, name: str):
	exec(compile(code, name, "exec"), namespace)
	return namespace


class NvdaCase(unittest.TestCase):
	"""An imitation NVDA 2026.2 with its own exit code, and the assistant's exitMessage turned on."""

	askToExit = False
	turnedOn = True

	def makeSpeech(self) -> dict:
		"""NVDA's speech, speech.extensions, speech.commands and synthDriverHandler, as sys.modules holds them."""
		extensions = types.ModuleType("speech.extensions")
		extensions.speechCanceled = Action()
		extensions.pre_speechCanceled = Action()
		self.speech = Speech(extensions)
		commands = types.ModuleType("speech.commands")
		commands.CallbackCommand = CallbackCommand
		self.synth = types.SimpleNamespace(name="oneCore")
		synthDriverHandler = types.ModuleType("synthDriverHandler")
		synthDriverHandler.getSynth = lambda: self.synth
		return {"speech": self.speech, "speech.extensions": extensions, "speech.commands": commands, "synthDriverHandler": synthDriverHandler}

	def setUp(self):
		self.wx = Wx()
		speechModules = self.makeSpeech()
		self.brailled = []
		braille = types.ModuleType("braille")
		braille.handler = types.SimpleNamespace(message=self.brailled.append)
		self.modalMessageBox = False
		guiMessage = types.ModuleType("gui.message")
		guiMessage.isModalMessageBoxActive = lambda: self.modalMessageBox
		self.queued = []
		queueHandler = types.ModuleType("queueHandler")
		queueHandler.eventQueue = "eventQueue"
		queueHandler.queueFunction = lambda queue, function, *args, **kwargs: self.queued.append((queue, function, args, kwargs))
		globalVars = types.ModuleType("globalVars")
		globalVars.exitCode = 0
		globalVars.appArgs = types.SimpleNamespace(launcher=False)
		globalVars.appDir = r"C:\Program Files\NVDA"
		self.globalVars = globalVars
		NVDAState = types.ModuleType("NVDAState")
		run(NVDA_SET_EXIT_CODE, vars(NVDAState), "NVDAState.py")
		NVDAState.globalVars = globalVars
		NVDAState.isRunningAsSource = lambda: False
		inputCore = types.ModuleType("inputCore")
		inputCore.decide_executeGesture = Decider()
		# What NVDA's own speak asks of inputCore, for the tests with NVDA's own speech.
		inputCore.logTimeSinceInput = lambda: None
		inputCore.manager = types.SimpleNamespace(isInputHelpActive=False, _captureFunc=None)
		self.inputCore = inputCore
		self.errors = []
		log = types.SimpleNamespace(error=self.errors.append, debug=lambda *args, **kwargs: None)
		self.shutdowns = []
		core = types.ModuleType("core")
		vars(core).update(
			Optional=Optional,
			NewNVDAInstance=NewNVDAInstance,
			_shuttingDownFlagLock=threading.Lock(),
			_hasShutdownBeenTriggered=False,
			log=log,
			_doShutdown=lambda newNVDA: self.shutdowns.append(newNVDA),
			globalVars=globalVars,
			NVDAState=NVDAState,
			computeRestartCLIArgs=lambda removeArgsList=None: [],
			os=os,
			sys=types.SimpleNamespace(executable=r"C:\Program Files\NVDA\nvda.exe", argv=["nvda.exe"]),
		)
		run(NVDA_TRIGGER_EXIT, vars(core), "core.py")
		run(NVDA_RESTART, vars(core), "core.py")
		self.core = core
		self.nvdasOwn = core.triggerNVDAExit
		self.modules = {
			"wx": self.wx,
			"braille": braille,
			"gui.message": guiMessage,
			"queueHandler": queueHandler,
			"globalVars": globalVars,
			"NVDAState": NVDAState,
			"inputCore": inputCore,
			"core": core,
			**speechModules,
		}
		patcher = mock.patch.dict(sys.modules, self.modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(self._forget)
		self._forget()
		# NVDA's MainFrame, its exit dialog and its quit command, with NVDA's own code.
		test = self
		self.dialogs = []

		class ExitDialog:
			def __init__(self, parent):
				test.dialogs.append(self)
				self.actionsList = types.SimpleNamespace(GetStringSelection=lambda: "Exit")
				self.destroyed = False

			def Raise(self):
				pass

			def Show(self):
				pass

			def Destroy(self):
				self.destroyed = True

		ExitDialog.onOk = run(
			NVDA_EXIT_DIALOG_OK,
			{
				"_ExitAction": ExitAction,
				"WelcomeDialog": types.SimpleNamespace(closeInstances=lambda: None),
				"core": core,
				"log": log,
				"queueHandler": queueHandler,
				"updateCheck": None,
				"wx": self.wx,
			},
			"gui/exit.py",
		)["onOk"]
		identity = types.SimpleNamespace(when=lambda *contexts: (lambda function: function), Context=types.SimpleNamespace(MODAL_DIALOG_OPEN="modal"))
		config = types.SimpleNamespace(conf={"general": {"askToExit": self.askToExit}})
		onExitCommand = run(NVDA_ON_EXIT_COMMAND, {"blockAction": identity, "config": config, "ExitDialog": ExitDialog, "core": core, "log": log}, "gui/__init__.py")["onExitCommand"]
		self.mainFrame = type("MainFrame", (), {"onExitCommand": onExitCommand, "prePopup": lambda self: None, "postPopup": lambda self: None})()
		self.quit = run(
			NVDA_QUIT,
			{"script": lambda **kwargs: (lambda function: function), "_": lambda text: text, "wx": self.wx, "gui": types.SimpleNamespace(mainFrame=self.mainFrame)},
			"globalCommands.py",
		)["script_quit"]
		if self.turnedOn:
			exitMessage.register()

	def _forget(self):
		exitMessage.unregister()
		exitMessage._installed = None
		exitMessage._waiting = None
		exitMessage._failed = False

	def pressExitKey(self):
		"""Insert+F4 in the tester's NVDA: NVDA's quit, run as NVDA runs a script, then wx's pending calls."""
		self.quit(None, None)
		self.wx.runPending()

	def said(self):
		return [sequence for sequence, priority in self.speech.spoken]

	def saidText(self):
		return [[item for item in sequence if isinstance(item, str)] for sequence in self.said()]

	def assertExiting(self, newNVDA=None):
		self.assertEqual(self.shutdowns, [], "NVDA's shutdown is queued, not run")
		self.assertEqual([(queue, function) for queue, function, args, kwargs in self.queued], [("eventQueue", self.core._doShutdown)])
		self.assertEqual(self.queued[0][2], (newNVDA,))
		self.assertTrue(self.core._hasShutdownBeenTriggered)

	def assertNotExiting(self):
		self.assertEqual(self.queued, [])
		self.assertFalse(self.core._hasShutdownBeenTriggered)

	def assertNothingLeft(self):
		self.assertFalse(exitMessage.isWaiting())
		self.assertEqual(list(self.inputCore.decide_executeGesture.handlers), [])
		self.assertNotIn(exitMessage._onSpeechCanceled, list(self.modules["speech.extensions"].speechCanceled.handlers))
		self.assertFalse([timer for timer in self.wx.timers if timer.running])


class ExitTests(NvdaCase):
	def test_theExitKeySaysUnloadingNvdaThenExits(self):
		self.pressExitKey()
		self.assertEqual(self.saidText(), [[SAID]])
		sequence, priority = self.speech.spoken[0]
		self.assertIsInstance(sequence[-1], CallbackCommand, "NVDA's speech manager tells when the message is said")
		self.assertEqual(priority, Spri.NOW)
		self.assertEqual(self.brailled, [SAID])
		self.assertTrue(exitMessage.isWaiting())
		self.assertNotExiting()
		self.assertEqual([timer.milliseconds for timer in self.wx.timers], [exitMessage.LONGEST_WAIT])
		# The synthesizer says it; NVDA's speech manager runs the callback, and NVDA's own triggerNVDAExit exits.
		self.speech.synthSaysAll()
		self.assertNotExiting()
		self.wx.runPending()
		self.assertExiting()
		self.assertNothingLeft()
		self.assertEqual(self.errors, [])

	def test_nvdaStopsSpeechOnlyAfterTheMessage(self):
		# As in the tester's log: once _doShutdown runs, core.main ends and stops speech. By then the message was said.
		self.pressExitKey()
		self.speech.synthSaysAll()
		self.wx.runPending()
		function = self.queued[0][1]
		function(*self.queued[0][2])
		self.assertEqual(self.shutdowns, [None])
		self.speech.cancelSpeech()
		self.assertEqual(self.saidText(), [[SAID]])
		self.assertEqual(self.speech.current, [])
		# NVDA's plugins stop in _doShutdown, and the assistant gives NVDA its own function back; core.main's catch-all
		# call then finds NVDA exiting already.
		exitMessage.unregister()
		self.assertIs(self.core.triggerNVDAExit, self.nvdasOwn)
		self.assertFalse(self.core.triggerNVDAExit())
		self.assertEqual(len(self.queued), 1)

	def test_aKeyPressedWhileItIsSaidExitsAtOnce(self):
		self.pressExitKey()
		# NVDA asks its deciders about every key, modifiers too, then stops speech for it.
		self.assertTrue(self.inputCore.decide_executeGesture.decide(gesture="kb:control"), "the key goes on")
		self.speech.cancelSpeech()
		self.wx.runPending()
		self.assertExiting()
		self.assertEqual(self.saidText(), [[SAID]], "not said again")
		self.assertNothingLeft()

	def test_aWindowChangeThatStopsItHasItSaidAgainOnce(self):
		# NVDA's menu closing gives the foreground back, and NVDA's event_foreground stops speech.
		self.pressExitKey()
		self.speech.cancelSpeech()
		self.wx.runPending()
		self.assertNotExiting()
		self.assertEqual(self.saidText(), [[SAID], [SAID]])
		self.speech.synthSaysAll()
		self.wx.runPending()
		self.assertExiting()
		self.assertNothingLeft()

	def test_stoppedTwiceExitsAtOnce(self):
		self.pressExitKey()
		self.speech.cancelSpeech()
		self.wx.runPending()
		self.speech.cancelSpeech()
		self.wx.runPending()
		self.assertExiting()
		self.assertEqual(self.saidText(), [[SAID], [SAID]])
		self.assertNothingLeft()

	def test_nvdaExitsAfterTheLongestWaitAllTheSame(self):
		self.pressExitKey()
		self.assertNotExiting()
		self.wx.timers[0].fire()
		self.assertExiting()
		self.assertNothingLeft()
		# The synthesizer finishing later changes nothing.
		self.speech.synthSaysAll()
		self.wx.runPending()
		self.assertEqual(len(self.queued), 1)

	def test_theExitKeyAgainExitsAtOnce(self):
		self.pressExitKey()
		self.pressExitKey()
		self.assertExiting()
		self.assertEqual(self.saidText(), [[SAID]])
		self.assertNothingLeft()
		self.speech.synthSaysAll()
		self.wx.runPending()
		self.assertEqual(len(self.queued), 1)
		self.assertEqual(self.errors, [])

	def test_aRestartAskedWhileItIsSaidRestarts(self):
		self.pressExitKey()
		self.core.restart()
		self.assertExiting(self.core.NewNVDAInstance(r"C:\Program Files\NVDA\nvda.exe", "", r"C:\Program Files\NVDA"))
		self.assertNothingLeft()

	def test_aRestartSaysNothing(self):
		self.core.restart()
		self.assertEqual(self.said(), [])
		self.assertExiting(self.core.NewNVDAInstance(r"C:\Program Files\NVDA\nvda.exe", "", r"C:\Program Files\NVDA"))
		self.assertNothingLeft()

	def test_theLaunchersRestartSaysNothing(self):
		# NVDA's launcher restarts with exit code 3 and no new copy of NVDA.
		self.globalVars.appArgs.launcher = True
		self.core.restart()
		self.assertEqual(self.said(), [])
		self.assertExiting()

	def test_alreadyExitingSaysNothing(self):
		self.core._hasShutdownBeenTriggered = True
		self.pressExitKey()
		self.assertEqual(self.said(), [])
		self.assertEqual(self.errors, ["NVDA already in process of exiting, this indicates a logic error."])

	def test_aMessageBoxOpenSaysNothing(self):
		self.modalMessageBox = True
		self.pressExitKey()
		self.assertEqual(self.said(), [])
		self.assertNotExiting()
		self.assertEqual(self.errors[0], "NVDA cannot exit safely, ensure open dialogs are closed")

	def test_nothingIsSaidWhereNothingWouldBeHeard(self):
		for setting, value in (("speechMode", SpeechMode.off), ("speechMode", SpeechMode.beeps), ("speechMode", SpeechMode.onDemand), ("isPaused", True)):
			with self.subTest(setting=setting, value=value):
				self.setUp()
				setattr(self.speech.state, setting, value)
				self.pressExitKey()
				self.assertEqual(self.said(), [])
				self.assertExiting()
				self.assertNothingLeft()
		self.setUp()
		self.synth = types.SimpleNamespace(name="silence")
		self.pressExitKey()
		self.assertEqual(self.said(), [])
		self.assertExiting()

	def test_afterNvdasMainLoopNothingIsSaid(self):
		# core.main's catch-all, when Windows ended NVDA's main loop.
		self.wx.mainLoopRunning = False
		self.assertTrue(self.core.triggerNVDAExit())
		self.assertEqual(self.said(), [])
		self.assertExiting()

	def test_offNvdasMainThreadNothingIsSaid(self):
		results = []
		thread = threading.Thread(target=lambda: results.append(self.core.triggerNVDAExit()))
		thread.start()
		thread.join()
		self.assertEqual(results, [True])
		self.assertEqual(self.said(), [])
		self.assertExiting()

	def test_turnedOffNvdaExitsAtOnce(self):
		exitMessage.unregister()
		self.assertIs(self.core.triggerNVDAExit, self.nvdasOwn)
		self.pressExitKey()
		self.assertEqual(self.said(), [])
		self.assertExiting()

	def test_anotherAddOnsWrapperStays(self):
		ours = self.core.triggerNVDAExit
		self.assertTrue(exitMessage._isOurs(ours))
		import functools

		@functools.wraps(ours)
		def theirs(*args, **kwargs):
			return ours(*args, **kwargs)

		self.core.triggerNVDAExit = theirs
		exitMessage.unregister()
		self.assertIs(self.core.triggerNVDAExit, theirs, "the assistant's stays under theirs, doing nothing")
		self.pressExitKey()
		self.assertEqual(self.said(), [])
		self.assertExiting()
		# Turned on again, the assistant's is found under theirs, and not put in twice.
		exitMessage.register()
		self.assertIs(self.core.triggerNVDAExit, theirs)

	def test_registerTwiceWrapsOnce(self):
		exitMessage.register()
		self.assertIs(getattr(self.core.triggerNVDAExit, exitMessage.ORIGINAL), self.nvdasOwn)

	def test_aSpeechFailureExitsAtOnce(self):
		def fails(*args, **kwargs):
			raise RuntimeError("no synthesizer")

		self.speech.speak = fails
		with mock.patch.object(exitMessage, "_log") as log:
			self.pressExitKey()
		self.assertExiting()
		self.assertNothingLeft()
		log.return_value.debugWarning.assert_called()


class ExitDialogTests(NvdaCase):
	askToExit = True

	def test_theExitDialogsExitSaysItThenExits(self):
		self.pressExitKey()
		self.assertEqual(len(self.dialogs), 1)
		self.assertEqual(self.said(), [], "nothing yet: NVDA asks first")
		dialog = self.dialogs[0]
		dialog.onOk(None)
		self.assertEqual(self.saidText(), [[SAID]])
		self.assertNotExiting()
		self.assertFalse(dialog.destroyed, "NVDA's exit closes it, as with NVDA's own triggerNVDAExit")
		self.speech.synthSaysAll()
		self.wx.runPending()
		self.assertExiting()
		self.assertEqual(self.errors, [])


class NvdasSpeechTests(NvdaCase):
	"""The same exits with NVDA 2026.2's own speech manager, speak and cancelSpeech, its CallbackCommand and speech
	extension points, its focus events and NVDAObject.event_foreground (test_v133_tabSwitch's NVDA, checked word for word
	there), and a synthesizer that says what the speech manager gives it: the tester in Outlook's message list."""

	def setUp(self):
		import test_v133_tabSwitch as v133

		self.v133 = v133
		tab = v133.TabCase("run")
		tab.setUp()
		self.addCleanup(tab.doCleanups)
		self.tab = tab
		self.nvda = tab.nvda
		self.nvda.synth.name = "oneCore"
		tab.foreground = tab.outlook
		self.nvda.focus(tab.message)
		self.nvda.synth.finish()
		self.before = len(self.nvda.synth.given)
		super().setUp()

	def makeSpeech(self) -> dict:
		nvda = self.nvda
		speech = types.ModuleType("speech")
		speech.speak = nvda.speak
		speech.cancelSpeech = nvda.cancelSpeech
		speech.Spri = nvda.priorities.Spri
		speech.SpeechMode = self.v133.v129.SpeechMode
		speech.getState = lambda: types.SimpleNamespace(**vars(nvda.base.speechState))
		return {"speech": speech, "speech.extensions": nvda.extensions, "speech.commands": nvda.commands, "synthDriverHandler": nvda.synthDriverHandler}

	def heard(self):
		"""What the synthesizer was given since the exit began, without the separator NVDA's speak adds."""
		return self.nvda.synth.heard()[self.before :]

	def test_theExitKeySaysItToTheEndThenExits(self):
		self.pressExitKey()
		self.assertEqual(self.heard(), [[SAID]])
		self.assertNotExiting()
		# The synthesizer says it and reaches the index after it; NVDA's speech manager runs the callback.
		self.nvda.synth.finish()
		self.assertNotExiting()
		self.wx.runPending()
		self.assertExiting()
		self.assertNothingLeft()

	def test_nvdasMenusExitIsSaidAgainAfterTheForegroundComesBack(self):
		# NVDA's menu, Exit: NVDA's MainFrame.onExitCommand runs as the menu closes, then Windows gives the foreground back
		# to Outlook, and NVDA's event_foreground stops speech, cutting the message off. It is said again, to the end.
		v133 = self.v133
		menu = v133.screenObject(990, v133.Role.MENUITEM, "Exit", self.tab.desktop, appModule=None, windowClassName="#32768")
		self.tab.foreground = menu
		self.nvda.focus(menu)
		self.nvda.synth.finish()
		self.before = len(self.nvda.synth.given)
		self.mainFrame.onExitCommand(None)
		self.assertEqual(self.heard(), [[SAID]])
		self.tab.foreground = self.tab.outlook
		self.nvda.focus(self.tab.message)
		self.wx.runPending()
		self.assertNotExiting()
		heard = self.heard()
		self.assertEqual(heard[-1], [SAID], "said again, ahead of Outlook's message")
		self.assertEqual(heard.count([SAID]), 2)
		self.nvda.synth.finish()
		self.wx.runPending()
		self.assertExiting()
		self.assertNothingLeft()

	def test_aKeyStopsItAndExits(self):
		self.pressExitKey()
		self.assertTrue(self.inputCore.decide_executeGesture.decide(gesture="kb:control"))
		self.nvda.cancelSpeech()
		self.wx.runPending()
		self.assertExiting()
		self.assertEqual(self.heard(), [[SAID]], "not said again")
		self.assertNothingLeft()


class TurnedOffTests(NvdaCase):
	turnedOn = False

	def test_nvdaExitsWithoutAWordAsItComes(self):
		self.assertIs(self.core.triggerNVDAExit, self.nvdasOwn)
		self.pressExitKey()
		self.assertEqual(self.said(), [])
		self.assertExiting()

	def test_offUnlessTurnedOn(self):
		self.assertIs(state.DEFAULTS[exitMessage.STATE_KEY], False)
		self.assertIs(state.DEFAULTS[exitMessage.CHECKED_KEY], False)
		self.assertFalse(exitMessage.wanted({}))
		self.assertTrue(exitMessage.wanted({exitMessage.STATE_KEY: True}))


def ini(text: str):
	return jawsFiles.parseIni(text)


#: JAWS 2026's shared Default.jcf, as far as these rows go.
SHARED = (
	"[options]\nVerbosity=0\nTypingInterrupt=1\n[OutputModes]\nSpeechLevel=1|2|2\nAPP_START=1|0|0|Application Start Message\n"
	"JAWS_MESSAGE=1|2|0|JAWS Message\nACCESS_KEY=1|1|1|Access Key\n"
)


class MappingTests(unittest.TestCase):
	def change(self, result):
		changes = [c for c in result.changes if c.target == settingsMap.ASSISTANT and c.path == (exitMessage.STATE_KEY,)]
		self.assertLessEqual(len(changes), 1)
		return changes[0] if changes else None

	def mapped(self, user: str = "", scope="both"):
		merged = jawsFiles.mergeIni(ini(SHARED), ini(user))
		source = merged if scope == "both" else ini(user)
		return settingsMap.mapSettings(source, merged, effective=scope == "both", userKeys=set())

	def test_jawsAsItComesSaysIt(self):
		change = self.change(self.mapped())
		self.assertIs(change.value, True)
		self.assertEqual(change.source, "[OutputModes] JAWS_MESSAGE=1|2|0|JAWS Message, Beginner level")
		self.assertEqual(change.label, 'Say "Unloading NVDA" as NVDA exits: on, as JAWS says "Unloading JAWS" (JAWS Messages on)')

	def test_eachVerbosityLevel(self):
		for verbosity, says, level in ((0, True, "Beginner"), (1, True, "Intermediate"), (2, False, "Advanced")):
			with self.subTest(verbosity=verbosity):
				change = self.change(self.mapped(f"[options]\nVerbosity={verbosity}\n"))
				self.assertIs(change.value, says)
				self.assertTrue(change.source.endswith(f"{level} level"))
		self.assertEqual(
			self.change(self.mapped("[options]\nVerbosity=2\n")).label,
			'Say "Unloading NVDA" as NVDA exits: off, as JAWS says no "Unloading JAWS" (JAWS Messages off)',
		)

	def test_jawsMessagesTurnedOffAtTheUsersLevel(self):
		# Settings Center, Beginner's Items to be Spoken, JAWS Messages unchecked.
		change = self.change(self.mapped("[OutputModes]\nJAWS_MESSAGE=0|2|0|JAWS Message\n"))
		self.assertIs(change.value, False)
		self.assertEqual(change.source, "[OutputModes] JAWS_MESSAGE=0|2|0|JAWS Message, Beginner level")

	def test_yourSettingsOnly(self):
		# Only what the user changed: nothing unless JAWS Messages or the verbosity level changed.
		self.assertIsNone(self.change(self.mapped("[options]\nTypingInterrupt=0\n", scope="user")))
		self.assertIs(self.change(self.mapped("[options]\nVerbosity=2\n", scope="user")).value, False)
		self.assertIs(self.change(self.mapped("[OutputModes]\nJAWS_MESSAGE=1|1|1|JAWS Message\n", scope="user")).value, True)

	def test_anOlderJawsWithoutTheRowUsesJawsDefault(self):
		source = ini("[options]\nVerbosity=1\n")
		change = self.change(settingsMap.mapSettings(source, source, effective=True))
		self.assertIs(change.value, True)
		self.assertEqual(change.source, "JAWS's default JAWS_MESSAGE=1|2|0|JAWS Message, Intermediate level")

	def test_notListedAsNotMigratedAnyMore(self):
		result = self.mapped()
		self.assertNotIn("JAWS_MESSAGE", [item.key for item in result.notMigrated])
		self.assertIn("APP_START", [item.key for item in result.notMigrated])

	def test_anApplicationsSettingsChangeNothing(self):
		# Exiting is the same in every program; an application's JAWS Messages stay listed as not migrated.
		app = ini("[OutputModes]\nJAWS_MESSAGE=0|0|0|JAWS Message\n")
		result = settingsMap.mapSettings(app, jawsFiles.mergeIni(ini(SHARED), app), isApplication=True)
		self.assertIsNone(self.change(result))
		self.assertIn("JAWS_MESSAGE", [item.key for item in result.notMigrated])

	def test_aMigrationLeavesNothingForTheCheck(self):
		with open(migrator.__file__, encoding="utf-8") as f:
			source = f.read()
		self.assertIn("updates[exitMessage.CHECKED_KEY] = True", source)
		self.assertIn("if change.target == settingsMap.ASSISTANT:\n\t\t\t\t\tupdates[change.path[0]] = change.value", source)

	def test_jawsSays(self):
		self.assertIs(exitMessage.jawsSays("1|2|0", 0), True)
		self.assertIs(exitMessage.jawsSays("1|2|0", 2), False)
		self.assertIs(exitMessage.jawsSays(None, 1), True, "JAWS's default row")
		self.assertIs(exitMessage.jawsSays("1|2|0", 7), True, "an unknown level counts as Beginner, as settingsMap reads it")
		self.assertIsNone(exitMessage.jawsSays("1", 2))
		self.assertEqual(exitMessage.jawsSaysIn(ini(SHARED)), (True, "[OutputModes] JAWS_MESSAGE=1|2|0|JAWS Message, Beginner level"))
		self.assertEqual(exitMessage.jawsSaysIn(ini("[options]\nVerbosity=2\n")), (False, "JAWS's default JAWS_MESSAGE=1|2|0|JAWS Message, Advanced level"))


class CheckOnceTests(unittest.TestCase):
	"""The check once after the update to 1.37, for a migration made before."""

	def setUp(self):
		folder = tempfile.TemporaryDirectory()
		self.addCleanup(folder.cleanup)
		for patcher in (
			mock.patch.object(nvdaEnv, "configDir", return_value=folder.name),
			mock.patch.object(nvdaEnv, "shouldWriteToDisk", return_value=True),
			mock.patch.object(exitMessage, "register"),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		state.forget()
		self.addCleanup(state.forget)
		self.announced = []
		self.done = []
		self.read = []

	def check(self, text=SHARED):
		def jawsSettings():
			self.read.append(True)
			return None if text is None else ini(text)

		exitMessage.checkOnce(jawsSettings, self.announced.append, lambda: self.done.append(True))
		state.forget()
		self.assertEqual(self.done, [True], "done once, whatever happened")
		self.done.clear()

	def earlierMigration(self):
		# The tester's state.json from 1.36: a migration, and neither key.
		state.set("lastMigration", {"when": "2026-09-23T20:43:59", "jaws": "JAWS 2026", "keyboardLayouts": ["laptop"], "overrideConflicts": True})
		state.forget()

	def test_whereJawsSaysItNvdaSaysItFromNowOn(self):
		self.earlierMigration()
		self.check()
		self.assertIs(state.get(exitMessage.STATE_KEY), True)
		self.assertIs(state.get(exitMessage.CHECKED_KEY), True)
		exitMessage.register.assert_called_once_with()
		self.assertEqual(
			self.announced,
			[
				'JAWS Migration Assistant: NVDA now says "Unloading NVDA" as it exits, as your JAWS says "Unloading JAWS". '
				"To turn it off, uncheck it in NVDA's Settings, JAWS Migration Assistant."
			],
		)
		# Once only.
		self.check()
		self.assertEqual(len(self.announced), 1)
		self.assertEqual(len(self.read), 1)

	def test_whereJawsDoesntNothingChanges(self):
		# "If it is turned off in Jaws nothing changes."
		for user in ("[options]\nVerbosity=2\n", "[OutputModes]\nJAWS_MESSAGE=0|2|0|JAWS Message\n"):
			with self.subTest(user=user):
				state.forget()
				os.makedirs(os.path.dirname(state.statePath()), exist_ok=True)
				with open(state.statePath(), "w", encoding="utf-8") as f:
					f.write("{}")
				self.earlierMigration()
				self.check(SHARED + user)
				self.assertIs(state.get(exitMessage.STATE_KEY), False)
				self.assertIs(state.get(exitMessage.CHECKED_KEY), True)
				self.assertEqual(self.announced, [])
				exitMessage.register.assert_not_called()

	def test_withoutAMigrationNothingChanges(self):
		self.check()
		self.assertIs(state.get(exitMessage.STATE_KEY), False)
		self.assertIs(state.get(exitMessage.CHECKED_KEY), True)
		self.assertEqual(self.read, [], "JAWS isn't even read")
		self.assertEqual(self.announced, [])

	def test_withoutJawsNothingChanges(self):
		self.earlierMigration()
		self.check(None)
		self.assertIs(state.get(exitMessage.STATE_KEY), False)
		self.assertIs(state.get(exitMessage.CHECKED_KEY), True)
		self.assertEqual(self.announced, [])

	def test_alreadyTurnedOnIsLeftAlone(self):
		self.earlierMigration()
		state.set(exitMessage.STATE_KEY, True)
		state.forget()
		self.check("[options]\nVerbosity=2\n")
		self.assertIs(state.get(exitMessage.STATE_KEY), True)
		self.assertEqual(self.read, [])
		self.assertEqual(self.announced, [])

	def test_aMigrationBy137IsNotCheckedAgain(self):
		self.earlierMigration()
		state.set(exitMessage.CHECKED_KEY, True)
		state.forget()
		self.check()
		self.assertIs(state.get(exitMessage.STATE_KEY), False, "that migration decided")
		self.assertEqual(self.read, [])

	def test_aFailureIsLoggedAndDoneStillCalled(self):
		self.earlierMigration()

		def broken():
			raise OSError("unreadable")

		with mock.patch("jawsMigrator.debugLog.error") as error:
			exitMessage.checkOnce(broken, self.announced.append, lambda: self.done.append(True))
		error.assert_called_once()
		self.assertEqual(self.done, [True])
		self.assertEqual(self.announced, [])

	def test_thePluginRunsItWithTheOtherStepsAfterAnUpdate(self):
		with open(os.path.join(os.path.dirname(exitMessage.__file__), "__init__.py"), encoding="utf-8") as f:
			source = f.read()
		self.assertIn("exitMessage.checkOnce(self._jawsDefaultJcf, announce, done)", source)
		self.assertIn("if exitMessage.wanted(data):\n\t\t\t\texitMessage.register()\n\t\t\telse:\n\t\t\t\texitMessage.unregister()", source)
		self.assertIn("exitMessage.unregister()\n\t\texcept Exception:\n\t\t\tpass\n\t\tsuper().terminate()", source)


class JawsTests(unittest.TestCase):
	"""What JAWS 2026 on this computer does, from its own files."""

	@needsJaws
	def test_insertF4SaysUnloadingJawsAsAJawsMessage(self):
		with open(os.path.join(JAWS_ROOT, "Scripts", "Default.JSS"), encoding="utf-8-sig", errors="replace") as f:
			script = f.read().replace("\r\n", "\n")
		start = script.index("script ShutDownJAWS()")
		body = script[start : script.index("EndScript", start)]
		self.assertIn('SayFormattedMessage (ot_JAWS_message, cmsg26_L) ;"Unloading JAWS"', body)
		self.assertLess(body.index("cmsg26_L"), body.index("ShutDownJAWS()\n", len("script ShutDownJAWS()")))
		with open(os.path.join(JAWS_ROOT, "Scripts", "common.jsm"), encoding="utf-8-sig", errors="replace") as f:
			messages = f.read().replace("\r\n", "\n")
		self.assertIn("@cmsg26_L\nUnloading JAWS\n@@", messages)
		self.assertEqual(exitMessage.JAWS_MESSAGE, "Unloading JAWS")
		with open(os.path.join(JAWS_ROOT, "Scripts", "HJConst.JSH"), encoding="utf-8-sig", errors="replace") as f:
			self.assertIn("\tOT_JAWS_MESSAGE=3,", f.read())

	@needsJaws
	def test_jawsDefaultRow(self):
		shared = jawsFiles.readIni(os.path.join(JAWS_ROOT, "SETTINGS", "enu", "Default.jcf"), inlineComments=True)
		self.assertEqual(shared.get("OutputModes", "JAWS_MESSAGE"), exitMessage.JAWS_DEFAULT_ROW)
		self.assertEqual(jawsFiles.parseInt(shared.get("options", "Verbosity")), 0)
		self.assertEqual(exitMessage.jawsSaysIn(shared), (True, "[OutputModes] JAWS_MESSAGE=1|2|0|JAWS Message, Beginner level"))


class NvdasOwnCodeTests(unittest.TestCase):
	def test_theCodeIsNvdas(self):
		import textwrap

		source = nvdaSource()
		for name, path in NVDA_CODE_FILES.items():
			with open(os.path.join(source, *path.split("/")), encoding="utf-8") as f:
				text = f.read().replace("\r\n", "\n")
			block = globals()[name].strip("\n")
			self.assertTrue(block in text or textwrap.indent(block, "\t") in text, name)

	def test_nvdasCancelSpeechAndCallback(self):
		# The imitation's cancelSpeech follows NVDA's: speechCanceled only when speech was going on; and NVDA's
		# CallbackCommand runs its function.
		source = nvdaSource()
		with open(os.path.join(source, "speech", "speech.py"), encoding="utf-8") as f:
			text = f.read().replace("\r\n", "\n")
		self.assertIn(
			"\tpre_speechCanceled.notify()\n\tif _speechState.beenCanceled:\n\t\treturn\n\telif _speechState.speechMode == SpeechMode.off:\n"
			"\t\treturn\n\telif _speechState.speechMode == SpeechMode.beeps:\n\t\treturn\n\t_manager.cancel()\n\tspeechCanceled.notify()\n",
			text,
		)
		with open(os.path.join(source, "speech", "commands.py"), encoding="utf-8") as f:
			self.assertIn("\tdef run(self, *args, **kwargs):\n\t\treturn self._callback(*args, **kwargs)\n", f.read().replace("\r\n", "\n"))
		with open(os.path.join(source, "inputCore.py"), encoding="utf-8") as f:
			text = f.read().replace("\r\n", "\n")
		# Every key, modifiers too, goes to the deciders before NVDA stops speech for it.
		self.assertLess(text.index("if not decide_executeGesture.decide(gesture=gesture):"), text.index("if gesture.isModifier:\n\t\t\traise NoInputGestureAction"))
		self.assertLess(text.index("if not decide_executeGesture.decide(gesture=gesture):"), text.index("speechEffect = gesture.speechEffectWhenExecuted"))


if __name__ == "__main__":
	unittest.main()
