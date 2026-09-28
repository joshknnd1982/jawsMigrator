# Unit tests for version 1.39, from the tester's issue 37, "Status of screen curtain not being said": "The status of the
# screen curtin isn't being said. Also should we make this more like Jaws?", with NVDA's log (NVDA 2026.2, the assistant
# 1.36, nvda-old.log and nvda.log of 2026-09-28 12.49.00). On issue 33 they had also asked for "announcements that indicate
# screen shade is on like Jaws".
# The log: NVDA started with the screen curtain on (nvda.ini [screenCurtain] enabled = True, playToggleSounds = False) and
# its first words were "Inbox - Outlook - Outlook": nothing about the curtain. NVDA says "NVDA started with screen curtain
# enabled" only on a braille display (core.main). They turned "Make screen black" off in NVDA's Settings, pressed
# NVDA+Escape in Outlook and heard nothing (a migration gives NVDA+Escape to JAWS's Insert+Escape, Refresh Screen, which
# is NVDA's refresh of a browse mode document), gave NVDA 2026.2's "Reports the state of the screen curtain", which has
# no key, NVDA+Escape in Input Gestures, heard "Screen curtain disabled", and took the key off again.
# JAWS 2026: Insert+Space, F11 and Insert+Space, Print Screen run ScreenShadeToggle (Default.JKM, Default.JSS), which
# says "Screen Shade on" or "Screen Shade off" (common.jsm); JAWS's help says the shade "remains active until toggled
# back off, or JAWS is restarted". Checked in JawsTests where JAWS 2026 is installed.
# - NVDA+Shift+J, then F11 or Print Screen turns the curtain on or off JAWS's way and says "Screen curtain on" or
#   "Screen curtain off"; Shift+F11 says whether it is on (ToggleTests, ReportTests, LayerTests). NVDA 2026.2's own
#   ScreenCurtain class runs here, and NVDA's own script_toggleScreenCurtain and script_reportScreenCurtainState run
#   beside the layer's keys, word for word (checked against NVDA's source when NVDA_SOURCE is set: NvdasOwnCodeTests).
#   What is imitated: Windows' magnification API (the test says whether the screen went black), wx's timers, NVDA's
#   warning dialog (a window of NVDA's gui) and ui.message.
# - NVDA started with the curtain on says "Screen curtain on" after it says where you are (StartupTests): with
#   test_v133_tabSwitch's NVDA 2026.2 (its own speech manager, speak, cancelSpeech, doPreGainFocus, api's focus code
#   and NVDAObject.event_foreground, word for word there), Outlook in front as in the tester's log, and the assistant's
#   own plugin handling the focus event where NVDA hands it to global plugins.
# Run: python -m unittest tests.test_v139_screenShade -v

import enum
import os
import sys
import textwrap
import types
import typing
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import jawsFiles, screenShade, startupFocus  # noqa: E402
from test_v137_exitMessage import Action, Decider, Wx, run  # noqa: E402

JAWS_SCRIPTS = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Freedom Scientific", "JAWS", "2026", "Scripts")
JAWS_SETTINGS = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Freedom Scientific", "JAWS", "2026", "Settings", "enu")

#: NVDA 2026.2, source/screenCurtain/_screenCurtain.py: the class, to the end of the file.
NVDA_SCREEN_CURTAIN = r'''
class ScreenCurtain:
	"""
	Screen curtain implementation.

	This class should be treated as a singleton:
	There should only ever be a single object created from this class at a time.
	"""

	_MAX_ENABLE_RETRIES: Final[int] = 3
	"""Maximum number of times to try enabling Screen Curtain."""

	def __init__(self):
		"""Initializer."""
		super().__init__()
		self._settings: ScreenCurtainSettings = cast(ScreenCurtainSettings, config.conf["screenCurtain"])
		self._enabled: bool = False
		if self.settings["enabled"]:
			try:
				self.enable()
			except RuntimeError:
				log.error("Failed to enable Screen Curtain", exc_info=True)
				if _TrackNVDAInitialization.isInitializationComplete():
					self._postInitialisationActivationFailureMessage()
				else:
					postNvdaStartup.register(self._postInitialisationActivationFailureMessage)

	def _postInitialisationActivationFailureMessage(self) -> None:
		wx.CallAfter(ModernMessageDialog.alert, ERROR_ENABLING_AT_STARTUP_MESSAGE, ERROR_ENABLING_MESSAGE)
		postNvdaStartup.unregister(self._postInitialisationActivationFailureMessage)

	@property
	def settings(self) -> ScreenCurtainSettings:
		"""The settings for the Screen Curtain."""
		return self._settings

	@property
	def enabled(self) -> bool:
		"""Whether the Screen Curtain is currently enabled."""
		return self._enabled

	def enable(self, *, persist: bool = False) -> None:
		"""Enables the screen curtain.

		This method is idempotent.

		:param persist: Whether to write that the Screen Curtain has been enabled to config, defaults to False
		:raises RuntimeError: On failure to activate the Screen Curtain
		"""
		if self._enabled:
			log.debug("ScreenCurtain is already enabled.")
			return

		# Notify magnifier that screen curtain is being enabled
		import _magnifier

		magnifierInstance = _magnifier.getMagnifier()
		if magnifierInstance:
			magnifierInstance.onScreenCurtainEnabled()

		log.debug("Enabling ScreenCurtain")
		for attempt in range(self._MAX_ENABLE_RETRIES):
			exception: Exception | None = None
			try:
				magnification.MagInitialize()
				magnification.MagSetFullscreenColorEffect(TRANSFORM_BLACK)
				magnification.MagShowSystemCursor(False)
				if not isScreenFullyBlack():
					raise RuntimeError("Screen is not black.")
				break
			except Exception as e:
				# We must call MagUninitialize at least as many times as we call MagInitialize,
				# as if we don't, we are liable to get permission errors
				# when attempting to use the magnification API
				magnification.MagUninitialize()
				log.debugWarning(f"Failed to enable Screen Curtain on attempt {attempt + 1}.", exc_info=e)
				exception = e
		else:
			log.debug(f"Failed to enable Screen Curtain after {self._MAX_ENABLE_RETRIES} attempts.")
			raise RuntimeError("Failed to enable screen curtain") from exception
		log.debug("Screen Curtain enabled")
		self._enabled = True
		if persist:
			self.settings["enabled"] = True
		if self.settings["playToggleSounds"]:
			try:
				nvwave.playWaveFile(os.path.join(globalVars.appDir, "waves", "screenCurtainOn.wav"))
			except Exception:
				log.exception()

	def disable(self, *, persist: bool = True) -> None:
		"""Disables the Screen Curtain.

		This method is idempotent.

		:param persist: Whether to store that the Screen Curtain has been disabled to config, defaults to True
		"""
		if not self._enabled:
			log.debug("ScreenCurtain is already disabled")
			return
		log.debug("Disabling ScreenCurtain")
		magnification.MagShowSystemCursor(True)
		magnification.MagUninitialize()
		self._enabled = False
		if persist:
			self.settings["enabled"] = False
		if self.settings["playToggleSounds"]:
			try:
				nvwave.playWaveFile(os.path.join(globalVars.appDir, "waves", "screenCurtainOff.wav"))
			except Exception:
				log.exception()
		# Notify magnifier that screen curtain is being disabled

		import _magnifier

		magnifierInstance = _magnifier.getMagnifier()
		if magnifierInstance:
			magnifierInstance.onScreenCurtainDisabled()

	def __del__(self) -> None:
		"""Custom deleter that disables the Screen Curtain if necessary when this object is garbage collected."""
		if self._enabled:
			self.disable(persist=False)
		if hasattr(super(), "__del__"):
			super().__del__(self)
'''

#: NVDA 2026.2, source/globalCommands.py, class GlobalCommands: the screen curtain's class attributes, its toggle and its
#: report, one tab less.
NVDA_GLOBAL_COMMANDS = r'''
_tempEnableScreenCurtain = True
_waitingOnScreenCurtainWarningDialog: wx.Dialog | None = None
_toggleScreenCurtainMessage: str | None = None

@script(
	description=_(
		# Translators: Describes a command.
		"Toggles the state of the screen curtain, "
		"enable to make the screen black or disable to show the contents of the screen. "
		"Pressed once, screen curtain is enabled until you restart NVDA. "
		"Pressed twice, screen curtain is enabled until you disable it",
	),
	gesture="kb:NVDA+control+escape",
)
def script_toggleScreenCurtain(self, gesture: inputCore.InputGesture) -> None:
	import screenCurtain

	if screenCurtain.screenCurtain is None:
		# Screen curtain has not been initialized.
		# Translators: Reported when the screen curtain is not available.
		ui.message(_("Screen curtain not available"), speechPriority=speech.priorities.Spri.NOW)
		return

	scriptCount = getLastScriptRepeatCount()
	if scriptCount == 0:  # first call should reset last message
		self._toggleScreenCurtainMessage = None
	alreadyRunning = screenCurtain.screenCurtain.enabled
	GlobalCommands._tempEnableScreenCurtain = scriptCount == 0
	if self._waitingOnScreenCurtainWarningDialog:
		# Already in the process of enabling the screen curtain, exit early.
		# Ensure that the dialog is in the foreground, and read it again.
		self._waitingOnScreenCurtainWarningDialog.Raise()

		# Key presses interrupt speech, so it maybe that the dialog wasn't
		# announced properly (if the user triggered the gesture more
		# than once). So we speak the objects to imitate the dialog getting
		# focus again. It might be useful to have something like this in a
		# script: see https://github.com/nvaccess/nvda/issues/9147#issuecomment-454278313
		speech.cancelSpeech()
		speech.speakObject(
			api.getForegroundObject(),
			reason=controlTypes.OutputReason.FOCUS,
		)
		speech.speakObject(
			api.getFocusObject(),
			reason=controlTypes.OutputReason.FOCUS,
		)
		return

	if scriptCount >= 2 and self._toggleScreenCurtainMessage:
		# Only the first two presses have actions, all subsequent presses should just repeat the last outcome.
		# This is important when not showing warning dialog, otherwise the script completion message can be
		# suppressed.
		# Must happen after the code to raise / read the warning dialog, since if there is a warning dialog
		# it takes preference, and there shouldn't be a valid completion message in this case anyway.
		ui.message(
			self._toggleScreenCurtainMessage,
			speechPriority=speech.priorities.Spri.NOW,
		)
		return

	# Disable if running
	if (
		alreadyRunning and scriptCount == 0  # a second press might be trying to achieve non temp enable
	):
		# Translators: Reported when the screen curtain is disabled.
		message = _("Screen curtain disabled")
		try:
			screenCurtain.screenCurtain.disable()
		except Exception:
			# If the screen curtain was enabled, we do not expect exceptions.
			log.error("Screen curtain termination error", exc_info=True)
			# Translators: Reported when the screen curtain could not be enabled.
			message = _("Could not disable screen curtain")
		finally:
			self._toggleScreenCurtainMessage = message
			ui.message(message, speechPriority=speech.priorities.Spri.NOW)
			return
	elif (  # enable it
		scriptCount in (0, 1)  # 1 press (temp enable) or 2 presses (enable)
	):

		def _enableScreenCurtain(doEnable: bool = True):
			self._waitingOnScreenCurtainWarningDialog = None
			if not doEnable:
				return  # exit early with no ui.message because the user has decided to abort.
			tempEnable = GlobalCommands._tempEnableScreenCurtain
			# Translators: Reported when the screen curtain is enabled.
			enableMessage = _("Screen curtain enabled")
			if tempEnable:
				# Translators: Reported when the screen curtain is temporarily enabled.
				enableMessage = _("Temporary Screen curtain, enabled until next restart")

			try:
				if alreadyRunning:
					screenCurtain.screenCurtain.settings["enabled"] = True
				else:
					screenCurtain.screenCurtain.enable(persist=not tempEnable)
			except Exception:
				log.error("Screen curtain initialization error", exc_info=True)
				enableMessage = screenCurtain._screenCurtain.ERROR_ENABLING_MESSAGE
			finally:
				self._toggleScreenCurtainMessage = enableMessage
				ui.message(enableMessage, speechPriority=speech.priorities.Spri.NOW)

		#  Show warning if necessary and do enable.
		settingsStorage = screenCurtain.screenCurtain.settings
		if settingsStorage["warnOnLoad"]:
			dlg = screenCurtain._screenCurtain.WarnOnLoadDialog(
				screenCurtainSettingsStorage=settingsStorage,
				parent=gui.mainFrame,
			)
			self._waitingOnScreenCurtainWarningDialog = dlg
			gui.runScriptModalDialog(
				dlg,
				lambda res: wx.CallLater(
					millis=100,
					callableObj=_enableScreenCurtain,
					doEnable=res == wx.YES,
				),
			)
		else:
			from contentRecog.recogUi import RefreshableRecogResultNVDAObject

			focusObj = api.getFocusObject()
			if (
				isinstance(focusObj, RefreshableRecogResultNVDAObject)
				and focusObj.recognizer.allowAutoRefresh
			):
				ui.message(
					screenCurtain._screenCurtain.UNAVAILABLE_WHEN_RECOGNISING_CONTENT_MESSAGE,
					speechPriority=speech.priorities.Spri.NOW,
				)
				return
			_enableScreenCurtain()

@script(
	description=_(
		# Translators: Describes a command.
		"Reports the state of the screen curtain.",
	),
	speakOnDemand=True,
)
def script_reportScreenCurtainState(self, gesture: inputCore.InputGesture) -> None:
	import screenCurtain

	if screenCurtain.screenCurtain is None:
		# Screen curtain has not been initialized.
		# Translators: Reported when the screen curtain is not available.
		ui.message(_("Screen curtain not available"), speechPriority=speech.priorities.Spri.NOW)
		return

	if screenCurtain.screenCurtain.enabled:
		if not screenCurtain.screenCurtain.settings["enabled"]:
			# Translators: Reported when the screen curtain is temporarily enabled.
			ui.message(
				_("Temporary Screen curtain, enabled until next restart"),
				speechPriority=speech.priorities.Spri.NOW,
			)
		else:
			# Translators: Reported when the screen curtain is enabled.
			ui.message(_("Screen curtain enabled"), speechPriority=speech.priorities.Spri.NOW)
	else:
		# Translators: Reported when the screen curtain is disabled.
		ui.message(_("Screen curtain disabled"), speechPriority=speech.priorities.Spri.NOW)
'''

#: NVDA 2026.2, source/core.py, main: what NVDA shows as it starts, only on a braille display.
NVDA_STARTUP_MESSAGE = r'''
		if screenCurtain.screenCurtain.enabled:
			# Translators: This is shown on a braille display (if one is connected) when NVDA starts with the screen curtain enabled.
			initialMessage = _("NVDA started with screen curtain enabled")
		else:
			# Translators: This is shown on a braille display (if one is connected) when NVDA starts.
			initialMessage = _("NVDA started")
		try:
			braille.handler.message(initialMessage)
		except:  # noqa: E722
			log.error("", exc_info=True)
'''

NVDA_CODE_FILES = {
	"NVDA_SCREEN_CURTAIN": "screenCurtain/_screenCurtain.py",
	"NVDA_GLOBAL_COMMANDS": "globalCommands.py",
	"NVDA_STARTUP_MESSAGE": "core.py",
}

NVDA_APP_DIR = r"C:\Program Files\NVDA"


def nvdaSource():
	source = os.environ.get("NVDA_SOURCE")
	if not source:
		raise unittest.SkipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
	return source


def needsJaws(test):
	return unittest.skipUnless(os.path.isdir(JAWS_SCRIPTS), "JAWS 2026 isn't installed")(test)


class Spri(enum.IntEnum):
	"""NVDA's speech priorities (speech/priorities.py)."""

	NORMAL = 0
	NEXT = 1
	NOW = 2


class Magnification:
	"""Windows' magnification API, as NVDA's ScreenCurtain calls it (winBindings.magnification)."""

	def __init__(self):
		self.calls = []
		self.failUninitialize = False

	def MagInitialize(self):
		self.calls.append("MagInitialize")

	def MagSetFullscreenColorEffect(self, effect):
		self.calls.append("MagSetFullscreenColorEffect")

	def MagShowSystemCursor(self, show):
		self.calls.append(("MagShowSystemCursor", show))

	def MagUninitialize(self):
		self.calls.append("MagUninitialize")
		if self.failUninitialize:
			raise OSError("MagUninitialize failed")


class Log:
	def __init__(self):
		self.errors = []

	def debug(self, *args, **kwargs):
		pass

	debugWarning = debug

	def error(self, message, *args, **kwargs):
		self.errors.append(message)

	def exception(self, *args, **kwargs):
		self.errors.append("exception")


class WarnOnLoadDialog:
	"""NVDA's warning before the curtain comes on, a window of NVDA's gui: what it is given, and Raise."""

	made = []

	def __init__(self, screenCurtainSettingsStorage, parent):
		self.settings = screenCurtainSettingsStorage
		self.parent = parent
		self.raised = 0
		WarnOnLoadDialog.made.append(self)

	def Raise(self):
		self.raised += 1


class RefreshableRecogResultNVDAObject:
	"""NVDA's content recognition result that refreshes itself (contentRecog.recogUi), as NVDA checks it."""

	def __init__(self, allowAutoRefresh=True):
		self.recognizer = types.SimpleNamespace(allowAutoRefresh=allowAutoRefresh)


class CurtainCase(unittest.TestCase):
	"""NVDA 2026.2's own ScreenCurtain and its own screen curtain commands, around an imitation of Windows."""

	def setUp(self):
		self.settings = {"enabled": False, "warnOnLoad": False, "playToggleSounds": False}
		self.magnification = Magnification()
		self.black = True
		self.played = []
		self.said = []
		self.log = Log()
		self.wx = Wx()
		self.wx.Dialog = type("Dialog", (), {})
		self.wx.YES, self.wx.NO = 2, 8
		self.modal = []
		self.gui = types.ModuleType("gui")
		self.gui.mainFrame = object()
		self.gui.runScriptModalDialog = lambda dialog, callback: self.modal.append((dialog, callback))
		self.spoken = []
		self.cancelled = []
		self.foreground = object()
		self.focus = object()
		WarnOnLoadDialog.made = []

		ui = types.ModuleType("ui")
		ui.message = lambda text, speechPriority=None, **kwargs: self.said.append((text, speechPriority))
		speech = types.ModuleType("speech")
		speech.priorities = types.SimpleNamespace(Spri=Spri)
		speech.cancelSpeech = lambda: self.cancelled.append(True)
		speech.speakObject = lambda obj, reason=None, **kwargs: self.spoken.append((obj, reason))
		priorities = types.ModuleType("speech.priorities")
		priorities.Spri = Spri
		api = types.ModuleType("api")
		api.getForegroundObject = lambda: self.foreground
		api.getFocusObject = lambda: self.focus
		controlTypes = types.ModuleType("controlTypes")
		controlTypes.OutputReason = types.SimpleNamespace(FOCUS="focus")
		magnifier = types.ModuleType("_magnifier")
		magnifier.getMagnifier = lambda: None
		recogUi = types.ModuleType("contentRecog.recogUi")
		recogUi.RefreshableRecogResultNVDAObject = RefreshableRecogResultNVDAObject
		contentRecog = types.ModuleType("contentRecog")
		contentRecog.recogUi = recogUi

		# NVDA's screenCurtain package: its ScreenCurtain class, run from NVDA's own code, and its messages.
		inner = types.ModuleType("screenCurtain._screenCurtain")
		vars(inner).update(
			Final=typing.Final,
			cast=typing.cast,
			ScreenCurtainSettings=dict,
			config=types.SimpleNamespace(conf={"screenCurtain": self.settings}),
			log=self.log,
			_TrackNVDAInitialization=types.SimpleNamespace(isInitializationComplete=lambda: False),
			postNvdaStartup=Action(),
			wx=self.wx,
			ModernMessageDialog=types.SimpleNamespace(alert=lambda *args: None),
			ERROR_ENABLING_AT_STARTUP_MESSAGE="There was a problem enabling Screen Curtain.",
			magnification=self.magnification,
			TRANSFORM_BLACK=object(),
			isScreenFullyBlack=lambda: self.black,
			nvwave=types.SimpleNamespace(playWaveFile=self.played.append),
			globalVars=types.SimpleNamespace(appDir=NVDA_APP_DIR),
			os=os,
			WarnOnLoadDialog=WarnOnLoadDialog,
			# NVDA's own words, as pgettext and _ give them in English.
			ERROR_ENABLING_MESSAGE="Could not enable screen curtain",
			UNAVAILABLE_WHEN_RECOGNISING_CONTENT_MESSAGE="Cannot enable screen curtain while performing content recognition",
		)
		run(NVDA_SCREEN_CURTAIN, vars(inner), "screenCurtain/_screenCurtain.py")
		self.package = types.ModuleType("screenCurtain")
		self.package._screenCurtain = inner
		self.package.screenCurtain = None
		self.ScreenCurtain = inner.ScreenCurtain

		# NVDA's GlobalCommands, with its screen curtain commands from NVDA's own code.
		self.repeatCount = 0
		commandsNamespace = {
			"__name__": "globalCommands",
			"script": lambda **kwargs: (lambda function: function),
			"_": lambda text: text,
			"inputCore": types.SimpleNamespace(InputGesture=object),
			"wx": self.wx,
			"ui": ui,
			"speech": speech,
			"getLastScriptRepeatCount": lambda: self.repeatCount,
			"log": self.log,
			"api": api,
			"controlTypes": controlTypes,
			"gui": self.gui,
		}
		run("class GlobalCommands:\n" + textwrap.indent(NVDA_GLOBAL_COMMANDS.strip("\n"), "\t") + "\n", commandsNamespace, "globalCommands.py")
		self.nvdaCommands = commandsNamespace["GlobalCommands"]()
		globalCommands = types.ModuleType("globalCommands")
		globalCommands.commands = self.nvdaCommands

		patcher = mock.patch.dict(
			sys.modules,
			{
				"wx": self.wx,
				"ui": ui,
				"speech": speech,
				"speech.priorities": priorities,
				"api": api,
				"controlTypes": controlTypes,
				"gui": self.gui,
				"_magnifier": magnifier,
				"contentRecog": contentRecog,
				"contentRecog.recogUi": recogUi,
				"screenCurtain": self.package,
				"screenCurtain._screenCurtain": inner,
				"globalCommands": globalCommands,
			},
		)
		patcher.start()
		self.addCleanup(patcher.stop)
		# Kept when a test starts NVDA again (setUp once more): every curtain made is turned off at the end.
		self.curtains = getattr(self, "curtains", [])
		# Before NVDA's modules go: a curtain left on is turned off, as NVDA's screenCurtain.terminate does.
		self.addCleanup(self._turnOff)
		patcher = mock.patch.object(screenShade, "_log", lambda: self.log)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(self._forget)
		self._forget()

	def _turnOff(self):
		self.magnification.failUninitialize = False
		for curtain in self.curtains:
			curtain.disable(persist=False)

	def _forget(self):
		screenShade._warning = None
		screenShade.stop()

	def startNvda(self, curtainOn: bool = False):
		"""NVDA starts: screenCurtain.initialize makes its ScreenCurtain, which comes on when NVDA's settings say so."""
		self.settings["enabled"] = curtainOn
		self.package.screenCurtain = self.ScreenCurtain()
		self.curtains.append(self.package.screenCurtain)
		return self.package.screenCurtain

	def nvdasKey(self, presses: int = 1):
		"""NVDA's own NVDA+Control+Escape, pressed once or more in a row."""
		for count in range(presses):
			self.repeatCount = count
			self.nvdaCommands.script_toggleScreenCurtain(None)
		self.repeatCount = 0

	def fireTimers(self):
		while True:
			timers = [timer for timer in self.wx.timers if timer.running]
			if not timers:
				return
			for timer in timers:
				timer.fire()


# -- NVDA+Shift+J, then F11 or Print Screen ---------------------------------------------------------------------------


class ToggleTests(CurtainCase):
	def test_f11TurnsItOnUntilNvdaRestarts(self):
		curtain = self.startNvda()
		self.assertEqual(screenShade.toggle(), "Screen curtain on")
		self.assertTrue(curtain.enabled)
		self.assertFalse(self.settings["enabled"], "not saved: off again when NVDA restarts, as JAWS's Screen Shade")
		self.assertEqual(self.said, [("Screen curtain on", Spri.NOW)])
		self.assertIn("MagSetFullscreenColorEffect", self.magnification.calls)

	def test_itIsNvdasOwnKeyPressedOnce(self):
		# NVDA's own NVDA+Control+Escape pressed once leaves NVDA in the same state, with NVDA's own words.
		self.startNvda()
		screenShade.toggle()
		mine = (self.package.screenCurtain.enabled, dict(self.settings))
		self.setUp()
		curtain = self.startNvda()
		self.nvdasKey()
		self.assertEqual((curtain.enabled, dict(self.settings)), mine)
		self.assertEqual(self.said, [("Temporary Screen curtain, enabled until next restart", Spri.NOW)])

	def test_f11AgainTurnsItOff(self):
		curtain = self.startNvda()
		screenShade.toggle()
		self.said.clear()
		self.assertEqual(screenShade.toggle(), "Screen curtain off")
		self.assertFalse(curtain.enabled)
		self.assertFalse(self.settings["enabled"])
		self.assertEqual(self.said, [("Screen curtain off", Spri.NOW)])
		self.assertEqual(self.magnification.calls[-2:], [("MagShowSystemCursor", True), "MagUninitialize"])

	def test_theTestersCurtainOnFromNvdasSettingsGoesOffForGood(self):
		# The tester's nvda.ini had the curtain on, so NVDA turned it on as it started. F11 turns it off, and NVDA's
		# settings with it, as NVDA's own key does: NVDA starts without it next time.
		curtain = self.startNvda(curtainOn=True)
		self.assertTrue(curtain.enabled)
		self.assertEqual(screenShade.toggle(), "Screen curtain off")
		self.assertFalse(curtain.enabled)
		self.assertFalse(self.settings["enabled"])
		self.setUp()
		curtain = self.startNvda(curtainOn=True)
		self.nvdasKey()
		self.assertEqual((curtain.enabled, self.settings["enabled"]), (False, False))
		self.assertEqual(self.said, [("Screen curtain disabled", Spri.NOW)])

	def test_nvdasToggleSoundsPlayAsWithNvdasKey(self):
		self.settings["playToggleSounds"] = True
		self.startNvda()
		screenShade.toggle()
		screenShade.toggle()
		self.assertEqual(self.played, [os.path.join(NVDA_APP_DIR, "waves", "screenCurtainOn.wav"), os.path.join(NVDA_APP_DIR, "waves", "screenCurtainOff.wav")])

	def test_printScreenIsTheSameCommand(self):
		self.assertEqual(jawsMigrator.LAYER_GESTURES["kb:f11"], "toggleScreenShade")
		self.assertEqual(jawsMigrator.LAYER_GESTURES["kb:printScreen"], "toggleScreenShade")


class WarningTests(CurtainCase):
	"""NVDA's "Always show a warning when enabling Screen Curtain", checked as NVDA comes: its warning comes first."""

	def setUp(self):
		super().setUp()
		self.settings["warnOnLoad"] = True
		self.curtain = self.startNvda()

	def test_nvdasWarningFirst(self):
		self.assertIsNone(screenShade.toggle())
		self.assertEqual(self.said, [])
		self.assertFalse(self.curtain.enabled)
		self.assertEqual(len(WarnOnLoadDialog.made), 1)
		dialog = WarnOnLoadDialog.made[0]
		self.assertIs(dialog.settings, self.settings, "the dialog's check box writes NVDA's own setting")
		self.assertIs(dialog.parent, self.gui.mainFrame)
		self.assertEqual([entry[0] for entry in self.modal], [dialog])

	def test_yesTurnsItOn(self):
		screenShade.toggle()
		_dialog, callback = self.modal[0]
		callback(self.wx.YES)
		self.assertEqual([timer.milliseconds for timer in self.wx.timers], [100], "as NVDA waits after its warning")
		self.fireTimers()
		self.assertTrue(self.curtain.enabled)
		self.assertFalse(self.settings["enabled"])
		self.assertEqual(self.said, [("Screen curtain on", Spri.NOW)])
		self.assertIsNone(screenShade._warning)

	def test_noLeavesItOffWithoutAWord(self):
		screenShade.toggle()
		self.modal[0][1](self.wx.NO)
		self.fireTimers()
		self.assertFalse(self.curtain.enabled)
		self.assertEqual(self.said, [])
		self.assertIsNone(screenShade._warning)

	def test_pressedAgainTheWarningIsReadAgain(self):
		screenShade.toggle()
		self.assertIsNone(screenShade.toggle())
		dialog = WarnOnLoadDialog.made[0]
		self.assertEqual(len(WarnOnLoadDialog.made), 1, "no second warning")
		self.assertEqual(dialog.raised, 1)
		self.assertEqual(self.cancelled, [True])
		self.assertEqual(self.spoken, [(self.foreground, "focus"), (self.focus, "focus")])
		self.assertEqual(self.said, [])

	def test_nvdasOwnWarningOpen(self):
		# NVDA+Control+Escape opened NVDA's own warning; F11 brings it back instead of opening another.
		self.nvdasKey()
		self.assertEqual(len(WarnOnLoadDialog.made), 1)
		self.assertIsNone(screenShade.toggle())
		self.assertEqual(len(WarnOnLoadDialog.made), 1)
		self.assertEqual(WarnOnLoadDialog.made[0].raised, 1)


class RefusalTests(CurtainCase):
	def test_notAvailable(self):
		self.assertIsNone(self.package.screenCurtain)
		self.assertEqual(screenShade.toggle(), "Screen curtain not available")
		self.assertEqual(self.said, [("Screen curtain not available", Spri.NOW)])
		self.said.clear()
		self.nvdasKey()
		self.assertEqual(self.said, [("Screen curtain not available", Spri.NOW)], "NVDA's own words")

	def test_whileNvdaRecognizesContent(self):
		curtain = self.startNvda()
		self.focus = RefreshableRecogResultNVDAObject()
		message = "Cannot enable screen curtain while performing content recognition"
		self.assertEqual(screenShade.toggle(), message)
		self.assertFalse(curtain.enabled)
		self.said.clear()
		self.nvdasKey()
		self.assertEqual(self.said, [(message, Spri.NOW)], "NVDA's own key refuses the same way")

	def test_theScreenDidNotGoBlack(self):
		# NVDA's own check: the curtain counts as on only when the screen is black; it tries three times.
		curtain = self.startNvda()
		self.black = False
		self.assertEqual(screenShade.toggle(), "Could not enable screen curtain")
		self.assertFalse(curtain.enabled)
		self.assertEqual(self.magnification.calls.count("MagInitialize"), 3)
		self.assertEqual(self.said, [("Could not enable screen curtain", Spri.NOW)])

	def test_couldNotTurnItOff(self):
		curtain = self.startNvda(curtainOn=True)
		self.magnification.failUninitialize = True
		self.assertEqual(screenShade.toggle(), "Could not disable screen curtain")
		self.assertEqual(self.said, [("Could not disable screen curtain", Spri.NOW)])
		self.assertEqual(self.log.errors, ["jawsMigrator: could not turn the screen curtain off"])


# -- NVDA+Shift+J, then Shift+F11 ---------------------------------------------------------------------------------------


class ReportTests(CurtainCase):
	def reports(self):
		"""What Shift+F11 says, and what NVDA's own command for it says."""
		self.said.clear()
		mine = screenShade.report()
		self.nvdaCommands.script_reportScreenCurtainState(None)
		self.assertEqual(self.said[0], (mine, Spri.NOW))
		return mine, self.said[1][0]

	def test_off(self):
		self.startNvda()
		self.assertEqual(self.reports(), ("Screen curtain off", "Screen curtain disabled"))

	def test_onUntilNvdaRestarts(self):
		self.startNvda()
		screenShade.toggle()
		self.assertEqual(self.reports(), ("Screen curtain on", "Temporary Screen curtain, enabled until next restart"))

	def test_onEachTimeNvdaStarts(self):
		# As the tester's NVDA started: "Make screen black" checked in NVDA's Settings.
		self.startNvda(curtainOn=True)
		self.assertEqual(self.reports(), ("Screen curtain on. NVDA turns it on each time it starts.", "Screen curtain enabled"))

	def test_notAvailable(self):
		self.assertEqual(self.reports(), ("Screen curtain not available", "Screen curtain not available"))


# -- the layer --------------------------------------------------------------------------------------------------------


class LayerTests(unittest.TestCase):
	def test_theLayersKeys(self):
		rows = {script: (gestures, key, words) for gestures, script, key, words in jawsMigrator.LAYER_COMMANDS}
		self.assertEqual(rows["toggleScreenShade"], (("kb:f11", "kb:printScreen"), "F11 or Print Screen", "turn the screen curtain on or off, as JAWS's Screen Shade."))
		self.assertEqual(rows["reportScreenShade"], (("kb:shift+f11",), "Shift+F11", "say whether the screen curtain is on."))
		self.assertIn("F11 or Print Screen, turn the screen curtain on or off, as JAWS's Screen Shade.", jawsMigrator.LAYER_HELP_LINES)
		self.assertIn("Shift+F11, say whether the screen curtain is on.", jawsMigrator.LAYER_HELP_LINES)

	def test_theScriptsRunTheModule(self):
		plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		calls = []
		with mock.patch.object(screenShade, "toggle", lambda: calls.append("toggle")), mock.patch.object(screenShade, "report", lambda: calls.append("report")):
			plugin.script_toggleScreenShade(None)
			plugin.script_reportScreenShade(None)
		self.assertEqual(calls, ["toggle", "report"])
		self.assertIn("as JAWS's Insert+Space, F11 turns Screen Shade on or off", jawsMigrator.GlobalPlugin.script_toggleScreenShade.__doc__)
		self.assertIn("Says whether the screen curtain is on", jawsMigrator.GlobalPlugin.script_reportScreenShade.__doc__)

	def test_theReportSpeaksInSpeechOnDemand(self):
		# As NVDA's own report (speakOnDemand=True): it reads something out, so NVDA's on-demand speech says it.
		import ast

		with open(jawsMigrator.__file__, encoding="utf-8") as file:
			tree = ast.parse(file.read())
		decorators = {
			node.name: {keyword.arg: getattr(keyword.value, "value", None) for decorator in node.decorator_list for keyword in getattr(decorator, "keywords", [])}
			for node in ast.walk(tree)
			if isinstance(node, ast.FunctionDef) and node.name in ("script_toggleScreenShade", "script_reportScreenShade")
		}
		self.assertIs(decorators["script_reportScreenShade"].get("speakOnDemand"), True)
		self.assertNotIn("speakOnDemand", decorators["script_toggleScreenShade"], "as NVDA's own toggle")

	def test_theWordsAreJawsWithNvdasName(self):
		self.assertEqual(screenShade.ON, screenShade.JAWS_ON.replace("Shade", "curtain"))
		self.assertEqual(screenShade.OFF, screenShade.JAWS_OFF.replace("Shade", "curtain"))

	def test_theReadmeNamesTheKeys(self):
		with open(os.path.join(os.path.dirname(__file__), "..", "README.md"), encoding="utf-8") as file:
			text = file.read()
		self.assertIn("| F11 or Print Screen |", text)
		self.assertIn("| Shift+F11 |", text)
		self.assertIn('Say "Screen curtain on" when NVDA starts with the screen curtain on', text)


# -- as NVDA starts ---------------------------------------------------------------------------------------------------


class StartupTests(unittest.TestCase):
	"""NVDA 2026.2 starting in the tester's Outlook, with the screen curtain on from its settings."""

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
		# NVDA's own extensionPoints.Action (test_v129_speechHistory's, word for word there).
		self.core = types.ModuleType("core")
		self.core.postNvdaStartup = type(nvda.extensions.pre_speech)()
		self.curtain = types.SimpleNamespace(enabled=True, settings={"enabled": True, "warnOnLoad": True, "playToggleSounds": False})
		package = types.ModuleType("screenCurtain")
		package.screenCurtain = self.curtain
		speech = types.ModuleType("speech")
		speech.speak = nvda.speak
		speech.cancelSpeech = nvda.cancelSpeech
		speech.Spri = nvda.priorities.Spri
		inputCore = sys.modules["inputCore"]
		self.decider = Decider()
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
		)
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		self.addCleanup(screenShade.stop)
		self.starting = True
		self.stateData = {}
		self.plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		self.plugin._sleepApps = set()
		self.plugin._changeRepeats = None
		self.plugin._screenShade = None

	def startPlugin(self):
		"""The plugin's start: NVDA starts its global plugins before it queues its first focus. Another add-on started
		after the assistant registers for the same notices, after the assistant's handlers."""
		self.plugin._screenCurtainAtStart()
		self.othersHeard = []
		self.otherStarted = lambda: self.othersHeard.append("postNvdaStartup")
		self.otherCanceled = lambda: self.othersHeard.append("speechCanceled")
		self.core.postNvdaStartup.register(self.otherStarted)
		self.nvda.extensions.speechCanceled.register(self.otherCanceled)

	def handlers(self, action) -> list:
		return list(action.handlers)

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

	def heard(self):
		self.nvda.synth.finish()
		return self.nvda.synth.heard()

	def test_saidAfterWhereYouAre(self):
		self.startNvda()
		heard = self.heard()
		self.assertEqual(heard[0][0], "Inbox - Outlook - Outlook", "NVDA's own first words, as in the tester's log")
		self.assertEqual(heard[-1], ["Screen curtain on"])
		self.assertEqual(sum(utterance == ["Screen curtain on"] for utterance in heard), 1)
		self.assertFalse(screenShade.isWaiting(), "said, and done")
		# The plugin's next focus event finds it done, and no focus event goes to it after that.
		self.focusEvent(self.tab.message)
		self.assertIsNone(self.plugin._screenShade)
		self.assertEqual(sum(utterance == ["Screen curtain on"] for utterance in self.heard()), 1)
		self.assertEqual(self.handlers(self.core.postNvdaStartup), [self.otherStarted], "the other add-on's stays")
		self.assertEqual(self.decider.handlers, [])
		self.assertEqual(self.handlers(self.nvda.extensions.speechCanceled), [self.otherCanceled])
		# The window's foreground event stopped speech as NVDA started, then NVDA notified postNvdaStartup.
		self.assertEqual(self.othersHeard, ["speechCanceled", "postNvdaStartup"])

	def test_withTheAssistant136NothingWasSaid(self):
		# The tester's log: with the check box off (as with 1.36, which has none), NVDA says nothing about the curtain.
		self.stateData = {screenShade.STATE_KEY: False}
		self.startNvda()
		heard = self.heard()
		self.assertEqual(heard[0][0], "Inbox - Outlook - Outlook")
		self.assertNotIn(["Screen curtain on"], heard)
		self.assertIsNone(self.plugin._screenShade)

	def test_aWindowChangeStopsItThenItIsSaidAfterTheNextFocus(self):
		self.startPlugin()
		self.focusEvent(self.tab.message)
		# Before the synthesizer got to it, Edge came to the front, and its foreground event stopped NVDA's speech.
		self.tab.window.name = "GitHub - Microsoft Edge"
		self.tab.foreground = self.tab.window
		self.focusEvent(self.tab.commentBox)
		heard = self.heard()
		self.assertEqual(heard[-1], ["Screen curtain on"])
		self.assertEqual(sum(utterance == ["Screen curtain on"] for utterance in heard), 1)
		self.assertFalse(screenShade.isWaiting())

	def test_aKeyStopsItForGood(self):
		self.startPlugin()
		self.focusEvent(self.tab.message)
		self.assertTrue(self.decider.decide(gesture="kb:downArrow"))
		# NVDA's own cancelSpeech goes through every handler of speechCanceled, the other add-on's after the assistant's.
		self.othersHeard.clear()
		self.nvda.cancelSpeech()
		self.assertEqual(self.othersHeard, ["speechCanceled"])
		self.focusEvent(self.tab.message)
		self.assertNotIn(["Screen curtain on"], self.heard())
		self.assertFalse(screenShade.isWaiting())
		# The assistant's handlers go once NVDA has finished with its notification.
		self.assertIn(screenShade._onSpeechCanceled, self.handlers(self.nvda.extensions.speechCanceled))
		self.wx.runPending()
		self.assertEqual(self.handlers(self.nvda.extensions.speechCanceled), [self.otherCanceled])
		self.assertEqual(self.decider.handlers, [])

	def test_notSaidMoreThanThreeTimes(self):
		self.startPlugin()
		for _ in range(screenShade.MOST_TRIES):
			self.focusEvent(self.tab.message)
			self.othersHeard.clear()
			self.nvda.cancelSpeech()
			self.assertEqual(self.othersHeard, ["speechCanceled"])
		self.assertFalse(screenShade.isWaiting())
		self.wx.runPending()
		self.assertEqual(self.handlers(self.nvda.extensions.speechCanceled), [self.otherCanceled])
		self.focusEvent(self.tab.message)
		self.assertNotIn(["Screen curtain on"], self.heard())

	def test_notWhenNvdaReloadsItsPlugins(self):
		self.starting = False
		self.startNvda()
		self.assertNotIn(["Screen curtain on"], self.heard())
		self.assertEqual(self.handlers(self.core.postNvdaStartup), [self.otherStarted])

	def test_notWhenTheCurtainIsOff(self):
		self.curtain.enabled = False
		self.startNvda()
		self.assertNotIn(["Screen curtain on"], self.heard())

	def test_notWhenTurnedOffBeforeItIsSaid(self):
		self.startPlugin()
		self.curtain.enabled = False
		self.focusEvent(self.tab.message)
		self.assertNotIn(["Screen curtain on"], self.heard())
		self.assertFalse(screenShade.isWaiting())

	def test_withoutAFocusEventItIsSaidAfterNvdaStarted(self):
		# NVDA gives global plugins no focus event in a program in sleep mode.
		self.startPlugin()
		self.core.postNvdaStartup.notify()
		self.assertEqual(self.othersHeard, ["postNvdaStartup"], "NVDA's notification went on to the other add-on")
		fallback = [timer for timer in self.wx.timers if timer.milliseconds == screenShade.FALLBACK_MS]
		self.assertEqual(len(fallback), 1)
		fallback[0].fire()
		self.assertEqual(self.heard(), [["Screen curtain on"]])

	def test_theFallbackWaitsForTheFocus(self):
		self.startNvda()
		for timer in list(self.wx.timers):
			timer.fire()
		self.assertEqual(sum(utterance == ["Screen curtain on"] for utterance in self.heard()), 1)

	def test_givesUpAfterThirtySeconds(self):
		self.startPlugin()
		self.core.postNvdaStartup.notify()
		giveUp = [timer for timer in self.wx.timers if timer.milliseconds == screenShade.GIVE_UP_MS]
		giveUp[0].fire()
		self.assertFalse(screenShade.isWaiting())
		self.focusEvent(self.tab.message)
		self.assertNotIn(["Screen curtain on"], self.heard())

	def test_thePluginsEndStopsIt(self):
		import inspect

		self.startPlugin()
		self.assertIs(self.plugin._screenShade, screenShade)
		self.assertIn("screenShade.stop()", inspect.getsource(jawsMigrator.GlobalPlugin.terminate))
		screenShade.stop()
		self.assertFalse(screenShade.isWaiting())
		self.assertEqual(self.handlers(self.core.postNvdaStartup), [self.otherStarted])
		self.assertEqual(self.decider.handlers, [])

	def test_theCheckBoxIsOnAsItComes(self):
		self.assertTrue(screenShade.wanted({}))
		self.assertFalse(screenShade.wanted({screenShade.STATE_KEY: False}))
		self.assertIs(jawsMigrator.state.DEFAULTS[screenShade.STATE_KEY], True)


# -- JAWS 2026's own files --------------------------------------------------------------------------------------------


class JawsTests(unittest.TestCase):
	@needsJaws
	def test_jawsKeysAfterInsertSpace(self):
		jkm = jawsFiles.readIni(os.path.join(JAWS_SCRIPTS, "enu", "Default.JKM"))
		keys = {key for key, value in jkm.section("Common Keys").items() if value.lower() == "screenshadetoggle" and key.lower().startswith("insert+space&")}
		self.assertEqual({key.split("&", 1)[1].lower() for key in keys}, {"f11", "printscreen"})
		layer = {gesture.split(":", 1)[1].lower() for gesture, script in jawsMigrator.LAYER_GESTURES.items() if script == "toggleScreenShade"}
		self.assertEqual(layer, {"f11", "printscreen"}, "the same keys after NVDA+Shift+J")

	@needsJaws
	def test_jawsSaysScreenShadeOnAndOff(self):
		with open(os.path.join(JAWS_SCRIPTS, "default.jss"), encoding="latin-1") as file:
			source = file.read().replace("\r\n", "\n")
		script = source.split("script ScreenShadeToggle()", 1)[1].split("endScript", 1)[0]
		self.assertIn("ToggleScreenShade ()", script)
		self.assertIn("longMessage = cmsgScreenShadeOn_L", script)
		self.assertIn("longMessage = cmsgScreenShadeOff_L", script)
		self.assertIn("sayMessage (OT_STATUS, longMessage, shortMessage)", script)
		with open(os.path.join(JAWS_SCRIPTS, "common.jsm"), encoding="latin-1") as file:
			messages = file.read().replace("\r\n", "\n")
		self.assertIn(f"@cmsgScreenShadeOn_L\n{screenShade.JAWS_ON}\n", messages)
		self.assertIn(f"@cmsgScreenShadeOff_L\n{screenShade.JAWS_OFF}\n", messages)

	@needsJaws
	def test_noJawsSettingTurnsItOnAtStart(self):
		with open(os.path.join(JAWS_SETTINGS, "DEFAULT.JCF"), encoding="latin-1") as file:
			self.assertNotIn("shade", file.read().lower())


# -- NVDA 2026.2's own code ---------------------------------------------------------------------------------------------


class NvdasOwnCodeTests(unittest.TestCase):
	def read(self, *path):
		with open(os.path.join(nvdaSource(), *path), encoding="utf-8") as file:
			return file.read().replace("\r\n", "\n")

	def test_theCodeIsNvdas(self):
		for name, path in NVDA_CODE_FILES.items():
			text = self.read(*path.split("/"))
			block = globals()[name].strip("\n")
			self.assertTrue(block in text or textwrap.indent(block, "\t") in text, name)

	def test_nvdasReportHasNoKey(self):
		text = self.read("globalCommands.py")
		decorator = text.split("\tdef script_reportScreenCurtainState", 1)[0].rsplit("@script(", 1)[1]
		self.assertNotIn("gesture", decorator)
		self.assertIn('gesture="kb:NVDA+control+escape"', text.split("\tdef script_toggleScreenCurtain", 1)[0].rsplit("@script(", 1)[1])

	def test_nvdaStartsTheCurtainThenPluginsThenItsFirstFocus(self):
		text = self.read("core.py")
		main = text.split("\ndef main():", 1)[1]
		order = [
			main.index("screenCurtain.initialize()"),
			main.index("globalPluginHandler.initialize()"),
			main.index("queueHandler.queueFunction(queueHandler.eventQueue, _setInitialFocus)"),
			main.index("queueHandler.queueFunction(queueHandler.eventQueue, _doPostNvdaStartupAction)"),
		]
		self.assertEqual(order, sorted(order))

	def test_nvdaHandlesTheWindowBeforeGlobalPlugins(self):
		text = self.read("eventHandler.py")
		self.assertLess(text.index("if isGainFocus and not doPreGainFocus(obj, sleepMode=sleepMode):"), text.index("\t\t\t_EventExecuter(eventName, obj, kwargs)"))
		executer = text.split("class _EventExecuter", 1)[1].split("\ndef ", 1)[0]
		self.assertLess(executer.index("globalPluginHandler.runningPlugins"), executer.index("appModule"))


if __name__ == "__main__":
	unittest.main()
