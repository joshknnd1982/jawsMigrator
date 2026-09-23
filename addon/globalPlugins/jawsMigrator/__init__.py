# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""JAWS Migration Assistant: brings a JAWS user's settings, voices, sounds and keystrokes into NVDA.

This global plugin adds the assistant to NVDA's Tools menu and Settings dialog,
offers its commands as a layer after NVDA+Shift+J (each command can also get
its own gesture in Input Gestures), and keeps the migrated behavior working
while NVDA runs: JAWS sound effects in place of NVDA's sounds, sleep mode in
the applications where JAWS slept, and the JAWS settings profile at startup.
"""

from __future__ import annotations

import functools
import os

import addonHandler
import globalPluginHandler
import gui
import inputCore
import scriptHandler
import tones
import ui
import wx
from scriptHandler import script

from . import jawsDetect, jawsDocs, jawsFiles, jawsKeyMap, keyPlan, nvdaEnv, state, systemCheck, updater
from .gui.common import TITLE, messageBox, openFile

try:
	addonHandler.initTranslation()
except Exception:
	pass

CATEGORY = TITLE

#: Commands available after NVDA+Shift+J.
LAYER_GESTURES = {
	"kb:m": "openAssistant",
	"kb:p": "toggleJawsProfile",
	"kb:k": "jawsKeystrokeHelp",
	"kb:s": "toggleJawsSounds",
	"kb:r": "openReport",
	"kb:b": "restoreBackup",
	"kb:u": "checkForUpdates",
	"kb:i": "systemSummary",
	"kb:h": "layerHelp",
	"kb:f1": "layerHelp",
}

LAYER_HELP = (
	"JAWS Migration Assistant commands, after NVDA+Shift+J: "
	"M, open the migration assistant. "
	"P, turn the JAWS settings profile on or off. "
	"K, hear what a JAWS keystroke does in NVDA. "
	"S, turn JAWS sound effects on or off. "
	"R, open the last migration report. "
	"B, restore NVDA settings from a backup. "
	"U, check for updates. "
	"I, JAWS, Windows and NVDA versions on this computer. "
	"H, this help. Escape leaves the layer."
)


def _log():
	from logHandler import log

	return log


def _finally(function, final):
	@functools.wraps(function)
	def wrapper(*args, **kwargs):
		try:
			return function(*args, **kwargs)
		finally:
			final()

	return wrapper


class SoundReplacer:
	"""Plays the migrated JAWS sounds in place of NVDA's own sounds, without touching NVDA's files."""

	def __init__(self):
		self._registered = False
		self._replacements: dict = {}
		self._waves = os.path.normcase(os.path.normpath(nvdaEnv.wavesFolder())) if nvdaEnv.wavesFolder() else ""

	def configure(self, enabled: bool, replacements: dict):
		self._replacements = {name.lower(): path for name, path in (replacements or {}).items() if path and os.path.isfile(path)}
		wanted = enabled and bool(self._replacements)
		try:
			import nvwave

			if wanted and not self._registered:
				nvwave.decide_playWaveFile.register(self._decide)
				self._registered = True
			elif not wanted and self._registered:
				nvwave.decide_playWaveFile.unregister(self._decide)
				self._registered = False
		except Exception:
			_log().debugWarning("jawsMigrator: sound replacement unavailable", exc_info=True)

	def _decide(self, fileName=None, asynchronous=True, isSpeechWaveFileCommand=False, **kwargs):
		try:
			if not fileName or not self._waves:
				return True
			path = os.path.normcase(os.path.normpath(fileName))
			if os.path.dirname(path) != self._waves:
				return True
			name = os.path.splitext(os.path.basename(path))[0].lower()
			replacement = self._replacements.get(name)
			if not replacement:
				return True
			import nvwave

			nvwave.playWaveFile(replacement, asynchronous=asynchronous)
			return False
		except Exception:
			_log().debugWarning("jawsMigrator: could not play a JAWS sound", exc_info=True)
			return True

	def stop(self):
		self.configure(False, {})


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = CATEGORY

	def __init__(self):
		super().__init__()
		self._secure = nvdaEnv.isSecureMode()
		self._layerActive = False
		self._busy = False
		self._menu = None
		self._menuItem = None
		self._sleepApps: set = set()
		self._keymapCache = None
		self.sounds = SoundReplacer()
		self.updater = updater.UpdateChecker()
		if self._secure:
			return
		self.applyRuntimeSettings()
		self._createMenu()
		try:
			from .gui import settingsPanel

			settingsPanel.JawsMigratorSettingsPanel.plugin = self
			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(settingsPanel.JawsMigratorSettingsPanel)
		except Exception:
			_log().exception("jawsMigrator: could not add the settings panel")
		self.updater.scheduleAutomaticCheck()
		wx.CallLater(2000, self._activateProfileAtStartup)
		if not state.get("welcomeShown"):
			# Once, after installation: give NVDA time to finish starting and speaking first.
			wx.CallLater(10000, self._firstRun)

	def terminate(self):
		self.updater.stop()
		self.sounds.stop()
		try:
			from .gui import settingsPanel

			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(settingsPanel.JawsMigratorSettingsPanel)
			settingsPanel.JawsMigratorSettingsPanel.plugin = None
		except Exception:
			pass
		try:
			if self._menuItem is not None:
				gui.mainFrame.sysTrayIcon.toolsMenu.Remove(self._menuItem)
		except Exception:
			pass
		super().terminate()

	# -- start up ----------------------------------------------------------------------

	def applyRuntimeSettings(self):
		"""Apply the assistant's own settings: JAWS sounds and sleeping applications."""
		data = state.load()
		self.sounds.configure(bool(data.get("jawsSoundsEnabled")), data.get("soundReplacements") or {})
		self._sleepApps = {str(name).lower() for name in data.get("sleepApps") or []}

	def _activateProfileAtStartup(self):
		try:
			name = state.get("jawsProfileName")
			if name and state.get("activateJawsProfileAtStartup") and name in nvdaEnv.profileNames():
				from . import nvdaApply

				if nvdaApply.activeManualProfile() is None:
					nvdaApply.activateProfile(name)
		except Exception:
			_log().exception("jawsMigrator: could not turn on the JAWS settings profile")

	def _firstRun(self):
		if state.get("welcomeShown"):
			return
		state.set("welcomeShown", True)
		self.openAssistant(firstRun=True)

	def _createMenu(self):
		try:
			toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
			self._menu = wx.Menu()
			items = (
				("&Migrate JAWS settings to NVDA...", self.onMenuOpen),
				("&Restore NVDA settings from a backup...", lambda event: self.openRestore()),
				("Open the last migration &report", lambda event: self.openLastReport()),
				("What does a &JAWS keystroke do in NVDA?", lambda event: wx.CallLater(300, self._startKeystrokeHelp)),
				("Check for &updates", lambda event: self.checkForUpdates()),
				("&Help", lambda event: self.openHelp()),
			)
			for label, handler in items:
				item = self._menu.Append(wx.ID_ANY, label)
				gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, handler, item)
			self._menuItem = toolsMenu.AppendSubMenu(self._menu, "&JAWS Migration Assistant")
		except Exception:
			_log().exception("jawsMigrator: could not add the Tools menu")

	# -- actions -------------------------------------------------------------------------

	def onMenuOpen(self, event):
		self.openAssistant()

	def openAssistant(self, firstRun: bool = False):
		if self._secure or self._busy:
			return
		self._busy = True
		ui.message("JAWS Migration Assistant. Checking this computer.")
		wx.CallLater(150, self._openAssistantNow, firstRun)

	def _openAssistantNow(self, firstRun: bool):
		try:
			facts = systemCheck.gatherFacts()
			description = f"Windows: {facts.windows}.\nNVDA: {facts.nvdaVersion}."
			if not facts.jaws:
				messageBox(
					"JAWS is not installed on this computer, and no JAWS settings were found, "
					f"so there is nothing to migrate.\n\n{description}\n\n"
					"You can open the JAWS Migration Assistant again later from the NVDA menu, Tools.",
					TITLE,
					wx.OK | wx.ICON_INFORMATION,
				)
				return
			if not facts.installedJaws:
				versions = ", ".join(f"JAWS {jaws.version}" for jaws in facts.jaws)
				if messageBox(
					f"JAWS is not installed on this computer, but settings from {versions} were found.\n\n"
					f"{description}\n\nDo you want to migrate those settings to NVDA anyway?",
					TITLE,
					wx.YES | wx.NO | wx.ICON_QUESTION,
				) != wx.YES:
					return
			elif firstRun:
				newest = facts.installedJaws[0]
				if messageBox(
					f"{newest.displayName} is installed on this computer.\n\n{description}\n\n"
					"Do you want to bring your JAWS settings, voices, sounds and keystrokes into NVDA now? "
					"Nothing changes until you confirm on the last step, and NVDA's settings are backed up first.\n\n"
					"You can also start later from the NVDA menu, Tools, JAWS Migration Assistant.",
					TITLE,
					wx.YES | wx.NO | wx.ICON_QUESTION,
				) != wx.YES:
					return
			from .gui import wizard

			wizard.runWizard(facts)
			self.applyRuntimeSettings()
		except Exception:
			_log().exception("jawsMigrator: the assistant failed")
			messageBox("The JAWS Migration Assistant ran into an error. Details are in the NVDA log.", TITLE, wx.OK | wx.ICON_ERROR)
		finally:
			self._busy = False

	def openRestore(self):
		from .gui import restoreDialog

		restoreDialog.showRestoreDialog()
		self.applyRuntimeSettings()

	def openLastReport(self):
		path = state.get("lastReport") or ""
		if path and os.path.isfile(path) and openFile(path):
			return
		messageBox("There is no migration report yet.", TITLE)

	def checkForUpdates(self):
		self.updater.check(manual=True)

	def openHelp(self):
		try:
			addon = addonHandler.getCodeAddon()
			path = addon.getDocFilePath()
			if path:
				openFile(path)
				return
		except Exception:
			pass
		messageBox(LAYER_HELP, TITLE)

	# -- sleeping where JAWS slept ----------------------------------------------------------

	def _checkSleep(self, obj):
		if not self._sleepApps:
			return
		try:
			appModule = obj.appModule
			if appModule is not None and not appModule.sleepMode and appModule.appName.lower() in self._sleepApps:
				appModule.sleepMode = True
		except Exception:
			pass

	def event_foreground(self, obj, nextHandler):
		self._checkSleep(obj)
		nextHandler()

	def event_gainFocus(self, obj, nextHandler):
		self._checkSleep(obj)
		nextHandler()

	# -- the command layer ------------------------------------------------------------------

	def getScript(self, gesture):
		if not self._layerActive:
			return super().getScript(gesture)
		found = super().getScript(gesture)
		if found is None:
			found = self.script_layerUnknown
		return _finally(found, self._leaveLayer)

	def _leaveLayer(self):
		self._layerActive = False
		self.clearGestureBindings()
		self.bindGestures(self._GlobalPlugin__gestures)

	@script(
		description="Starts a layer of JAWS Migration Assistant commands; press H after it to hear them",
		gesture="kb:NVDA+shift+j",
	)
	def script_commandLayer(self, gesture):
		if self._layerActive:
			self._leaveLayer()
			return
		if self._secure:
			return
		self._layerActive = True
		self.bindGestures(LAYER_GESTURES)
		tones.beep(660, 40)

	def script_layerUnknown(self, gesture):
		tones.beep(220, 60)

	@script(description="Opens the JAWS Migration Assistant")
	def script_openAssistant(self, gesture):
		wx.CallAfter(self.openAssistant)

	@script(description="Turns the NVDA configuration profile holding your JAWS settings on or off")
	def script_toggleJawsProfile(self, gesture):
		from . import nvdaApply

		name = state.get("jawsProfileName")
		if not name or name not in nvdaEnv.profileNames():
			ui.message("There is no JAWS settings profile. Migrate your JAWS settings into a profile first.")
			return
		if nvdaApply.activeManualProfile() == name:
			nvdaApply.activateProfile(None)
			ui.message(f"{name} profile off")
		elif nvdaApply.activateProfile(name):
			ui.message(f"{name} profile on")

	@script(description="Turns JAWS sound effects in place of NVDA's sounds on or off")
	def script_toggleJawsSounds(self, gesture):
		replacements = state.get("soundReplacements") or {}
		if not replacements:
			ui.message("No JAWS sound effects were migrated. Choose them in the JAWS Migration Assistant.")
			return
		enabled = not state.get("jawsSoundsEnabled")
		state.set("jawsSoundsEnabled", enabled)
		self.applyRuntimeSettings()
		ui.message("JAWS sound effects on" if enabled else "JAWS sound effects off, NVDA sounds on")

	@script(description="Opens the report of the last JAWS migration")
	def script_openReport(self, gesture):
		wx.CallAfter(self.openLastReport)

	@script(description="Restores NVDA's settings from a backup made by the JAWS Migration Assistant")
	def script_restoreBackup(self, gesture):
		wx.CallAfter(self.openRestore)

	@script(description="Checks for JAWS Migration Assistant updates")
	def script_checkForUpdates(self, gesture):
		self.checkForUpdates()

	@script(description="Reports the JAWS, Windows and NVDA versions found on this computer")
	def script_systemSummary(self, gesture):
		installations = jawsDetect.findJawsInstallations()
		jaws = "; ".join(j.displayName + ("" if j.programInstalled else ", settings only") for j in installations) or "JAWS is not installed"
		running = " JAWS is running." if jawsDetect.isJawsRunning() else ""
		ui.message(f"{jaws}.{running} {jawsDetect.windowsVersionDescription()}. NVDA {nvdaEnv.nvdaVersion()}.")

	@script(description="Lists the commands of the JAWS Migration Assistant layer")
	def script_layerHelp(self, gesture):
		ui.message(LAYER_HELP)

	# -- the JAWS keystroke helper ----------------------------------------------------------

	@script(description="Tells you what a JAWS keystroke does in NVDA: press this, then the JAWS keystroke")
	def script_jawsKeystrokeHelp(self, gesture):
		self._startKeystrokeHelp()

	def _jawsKeymap(self):
		"""JAWS's merged default key map, its keyboard layout and script descriptions, cached."""
		if self._keymapCache is not None:
			return self._keymapCache
		installations = [j for j in jawsDetect.findJawsInstallations() if j.programInstalled] or jawsDetect.findJawsInstallations()
		if not installations:
			return None
		jaws = installations[0]
		language = jaws.primaryLanguage or "enu"
		files = []
		for path in (os.path.join(jaws.sharedScriptsLanguageDir(language), "Default.jkm"), os.path.join(jaws.userLanguageDir(language), "Default.jkm")):
			if os.path.isfile(path):
				try:
					files.append(jawsFiles.readIni(path))
				except OSError:
					pass
		if not files:
			return None
		jkm = jawsFiles.mergeIni(*files)
		layout = "desktop"
		for path in (os.path.join(jaws.sharedLanguageDir(language), "Default.jcf"), os.path.join(jaws.userLanguageDir(language), "Default.jcf")):
			try:
				value = jawsFiles.readIni(path, inlineComments=True).get("options", "KeyboardType")
			except OSError:
				value = None
			if value:
				layout = "laptop" if "laptop" in value.lower() else "desktop"
		docs = jawsDocs.readJsd([os.path.join(jaws.sharedScriptsLanguageDir(language), "default.jsd")])
		self._keymapCache = (jaws, keyPlan.buildReverseMap(jkm, layout), docs, layout)
		return self._keymapCache

	def _startKeystrokeHelp(self):
		try:
			keymap = self._jawsKeymap()
		except Exception:
			_log().exception("jawsMigrator: could not read the JAWS key map")
			keymap = None
		if keymap is None:
			ui.message("No JAWS key map was found on this computer.")
			return
		ui.message(f"Press a {keymap[0].displayName} keystroke to hear what it does in NVDA, or Escape to cancel.")
		inputCore.manager._captureFunc = self._captureKeystroke

	def _captureKeystroke(self, gesture):
		if gesture.isModifier:
			return True
		inputCore.manager._captureFunc = None
		identifiers = [identifier.lower() for identifier in gesture.normalizedIdentifiers]
		if "kb:escape" in identifiers:
			wx.CallAfter(ui.message, "Cancelled")
			return False
		wx.CallAfter(self._describeKeystroke, gesture)
		return False

	def _describeKeystroke(self, gesture):
		jaws, reverseMap, docs, _layout = self._jawsKeymap()
		keyName = gesture.displayName
		matches = keyPlan.describeJawsKeystroke(gesture, reverseMap)
		parts = []
		if not matches:
			parts.append(f"{keyName} does nothing special in JAWS.")
		for jawsKey, jawsScript, _section in matches[:2]:
			parts.append(f"In JAWS, {jawsKey} runs {jawsDocs.describe(docs, jawsScript)}.")
			targets = jawsKeyMap.getNvdaTargets(jawsScript)
			if targets:
				module, className, nvdaScript, description = targets[0]
				from . import nvdaApply

				gestures = nvdaApply.gesturesForScript(module, className, nvdaScript)
				where = f" Press {', or '.join(gestures[:3])}." if gestures else " It has no keystroke yet; assign one in NVDA's Input Gestures dialog."
				parts.append(f"In NVDA: {description}.{where}")
			else:
				parts.append("NVDA has no command that does the same.")
		try:
			nvdaScript = scriptHandler.findScript(gesture)
		except Exception:
			nvdaScript = None
		if nvdaScript is not None and getattr(nvdaScript, "__doc__", None):
			parts.append(f"In NVDA, {keyName} now does: {nvdaScript.__doc__.strip()}")
		elif matches:
			parts.append(f"In NVDA, {keyName} has no command of its own.")
		ui.message(" ".join(parts))
