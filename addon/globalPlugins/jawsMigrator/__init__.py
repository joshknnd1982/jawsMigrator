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
import time

import addonHandler
import globalPluginHandler
# NVDA's gui, under a name of its own: importing this add-on's own gui package (below) binds
# the name "gui" in this module to that package, which would hide NVDA's.
import gui as nvdaGui
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
	"kb:o": "openImportSettings",
	"kb:g": "openInputGestures",
	"kb:p": "toggleJawsProfile",
	"kb:k": "jawsKeystrokeHelp",
	"kb:s": "toggleJawsSounds",
	"kb:a": "copyJawsSounds",
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
	"O, JAWS Migration Assistant settings: choose which JAWS items to import. "
	"G, open NVDA's Input Gestures dialog. "
	"P, turn the JAWS settings profile on or off. "
	"K, hear what a JAWS keystroke does in NVDA. "
	"S, JAWS sounds in place of NVDA's own, on or off, through ClassicSpeech. "
	"A, copy all JAWS sounds into ClassicSpeech. "
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


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = CATEGORY

	def __init__(self):
		super().__init__()
		self._secure = nvdaEnv.isSecureMode()
		self._layerActive = False
		self._busy = False
		self._menu = None
		self._menuItem = None
		self._preferencesItem = None
		self._factsCache = None
		self._sleepApps: set = set()
		self._keymapCache = None
		self.updater = updater.UpdateChecker()
		if self._secure:
			return
		self.applyRuntimeSettings()
		self._createMenu()
		try:
			from .gui import settingsPanel

			settingsPanel.JawsMigratorSettingsPanel.plugin = self
			nvdaGui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(settingsPanel.JawsMigratorSettingsPanel)
		except Exception:
			_log().exception("jawsMigrator: could not add the settings panel")
		self.updater.scheduleAutomaticCheck()
		wx.CallLater(2000, self._activateProfileAtStartup)
		if not state.get("welcomeShown"):
			# Once, after installation: give NVDA time to finish starting and speaking first.
			wx.CallLater(10000, self._firstRun)

	def terminate(self):
		self.updater.stop()
		try:
			from .gui import settingsPanel

			nvdaGui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(settingsPanel.JawsMigratorSettingsPanel)
			settingsPanel.JawsMigratorSettingsPanel.plugin = None
		except Exception:
			pass
		try:
			if self._menuItem is not None:
				nvdaGui.mainFrame.sysTrayIcon.toolsMenu.Remove(self._menuItem)
		except Exception:
			pass
		try:
			if self._preferencesItem is not None:
				nvdaGui.mainFrame.sysTrayIcon.preferencesMenu.Remove(self._preferencesItem)
		except Exception:
			pass
		super().terminate()

	# -- start up ----------------------------------------------------------------------

	def applyRuntimeSettings(self):
		"""Apply the assistant's own settings: the applications where NVDA sleeps."""
		data = state.load()
		if data.get("jawsSoundsEnabled") or data.get("soundReplacements"):
			# Version 1.1 played JAWS sounds itself. They play through ClassicSpeech now (classicSounds).
			state.update({"jawsSoundsEnabled": False, "soundReplacements": {}})
			_log().info("jawsMigrator: JAWS sounds now play through ClassicSpeech; version 1.1's own sound replacement is off")
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
			toolsMenu = nvdaGui.mainFrame.sysTrayIcon.toolsMenu
			self._menu = wx.Menu()
			items = (
				("&Migrate JAWS settings to NVDA...", self.onMenuOpen),
				("&Choose what to import...", lambda event: self.openImportSettings()),
				("Use JAWS &sounds in place of NVDA's sounds", lambda event: self.useJawsSounds()),
				("Restore NVDA's &own sounds", lambda event: self.restoreNvdaSounds()),
				("Copy &all JAWS sounds into ClassicSpeech", lambda event: self.copyJawsSounds()),
				("&Restore NVDA settings from a backup...", lambda event: self.openRestore()),
				("Open the last migration &report", lambda event: self.openLastReport()),
				("What does a &JAWS keystroke do in NVDA?", lambda event: wx.CallLater(300, self._startKeystrokeHelp)),
				("Check for &updates", lambda event: self.checkForUpdates()),
				("&Help", lambda event: self.openHelp()),
			)
			for label, handler in items:
				item = self._menu.Append(wx.ID_ANY, label)
				nvdaGui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, handler, item)
			self._menuItem = toolsMenu.AppendSubMenu(self._menu, "&JAWS Migration Assistant")
		except Exception:
			_log().exception("jawsMigrator: could not add the Tools menu")
		try:
			preferencesMenu = nvdaGui.mainFrame.sysTrayIcon.preferencesMenu
			self._preferencesItem = preferencesMenu.Append(
				wx.ID_ANY,
				"&JAWS Migration Assistant settings...",
				"Choose which JAWS settings, schemes, voice profiles and voice aliases to import",
			)
			nvdaGui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, lambda event: self.openImportSettings(), self._preferencesItem)
		except Exception:
			_log().exception("jawsMigrator: could not add the Preferences menu item")

	# -- actions -------------------------------------------------------------------------

	def onMenuOpen(self, event):
		self.openAssistant()

	def openAssistant(self, firstRun: bool = False):
		if self._secure:
			return
		if self._busy:
			ui.message("The JAWS Migration Assistant is already open.")
			return
		self._busy = True
		ui.message("JAWS Migration Assistant. Checking this computer.")
		wx.CallLater(150, self._openAssistantNow, firstRun)

	#: How long a System Check stays fresh for the settings dialog and the wizard, in seconds.
	FACTS_LIFETIME = 300

	def _facts(self, fresh: bool = False):
		cached = self._factsCache
		if not fresh and cached is not None and time.monotonic() - cached[0] < self.FACTS_LIFETIME:
			return cached[1]
		facts = systemCheck.gatherFacts()
		self._factsCache = (time.monotonic(), facts)
		return facts

	def _openAssistantNow(self, firstRun: bool):
		try:
			facts = self._facts()
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
			# A migration changes NVDA's synthesizers, profiles and add-ons; check again next time.
			self._factsCache = None
			self.applyRuntimeSettings()
		except Exception:
			_log().exception("jawsMigrator: the assistant failed")
			messageBox("The JAWS Migration Assistant ran into an error. Details are in the NVDA log.", TITLE, wx.OK | wx.ICON_ERROR)
		finally:
			self._busy = False

	def openImportSettings(self):
		"""JAWS Migration Assistant settings: choose which JAWS items to import."""
		if self._secure:
			return
		if self._busy:
			ui.message("The JAWS Migration Assistant is already open. Finish or close it first.")
			return
		from .gui import importDialog

		existing = importDialog.ImportSettingsDialog.current()
		if existing is not None:
			existing.Raise()
			existing.SetFocus()
			return
		self._busy = True
		ui.message("JAWS Migration Assistant settings. Reading your JAWS settings.")
		wx.CallLater(150, self._openImportSettingsNow)

	def _openImportSettingsNow(self):
		try:
			facts = self._facts()
			if not facts.jaws:
				messageBox(
					"JAWS is not installed on this computer, and no JAWS settings were found, so there is nothing to choose from.\n\n"
					f"Windows: {facts.windows}.\nNVDA: {facts.nvdaVersion}.",
					TITLE,
					wx.OK | wx.ICON_INFORMATION,
				)
				return
			from .gui import importDialog

			importDialog.showImportSettings(facts, self)
		except Exception:
			_log().exception("jawsMigrator: the settings dialog failed")
			messageBox("The JAWS Migration Assistant settings could not be opened. Details are in the NVDA log.", TITLE, wx.OK | wx.ICON_ERROR)
		finally:
			self._busy = False

	# -- JAWS sounds, through ClassicSpeech ------------------------------------------------

	def _soundsAction(self, action, announcement: str):
		if self._secure:
			return
		if self._busy:
			ui.message("The JAWS Migration Assistant is busy. Finish or close it first.")
			return
		self._busy = True
		ui.message(announcement)
		wx.CallLater(150, self._runSoundsAction, action)

	def _runSoundsAction(self, action):
		try:
			outcome = action()
			if outcome is not None:
				messageBox(outcome.message, TITLE, wx.OK | (wx.ICON_INFORMATION if outcome.succeeded else wx.ICON_WARNING))
		except Exception as error:
			_log().exception("jawsMigrator: the JAWS sounds action failed")
			messageBox(f"That could not be done, and NVDA's sounds were not changed: {error}", TITLE, wx.OK | wx.ICON_ERROR)
		finally:
			self._busy = False

	def useJawsSounds(self):
		"""Play JAWS sounds in place of NVDA's own sounds, through ClassicSpeech, after backing up."""
		from . import backup, migrator

		def action():
			facts = self._facts()
			problem = migrator.soundsProblem(facts)
			if problem:
				return migrator.SoundsOutcome(problem, False)
			size = f" The backup copies about {backup.sizeText(facts.backupBytes)}, which can take a minute." if facts.backupBytes > 50 * 1024 * 1024 else ""
			if messageBox(
				"Play JAWS sounds in place of NVDA's own sounds, through ClassicSpeech? Focus and browse mode, spelling errors, "
				"auto-suggestions, the screen curtain, Remote Access and logged errors then sound as in JAWS.\n\n"
				"NVDA's settings, add-ons and add-on settings are backed up first, and a copy of NVDA's own sounds is kept; NVDA's "
				f"own sound files are never changed.{size} You can restore NVDA's own sounds at any time.",
				TITLE,
				wx.YES | wx.NO | wx.ICON_QUESTION,
			) != wx.YES:
				return None
			return migrator.useJawsSounds(facts)

		self._soundsAction(action, "JAWS sounds for NVDA")

	def restoreNvdaSounds(self):
		"""Put NVDA's own sounds back: take out the JAWS sounds the assistant gave ClassicSpeech."""
		from . import migrator

		self._soundsAction(migrator.restoreNvdaSounds, "Restoring NVDA's own sounds")

	def copyJawsSounds(self):
		"""Copy every JAWS sound into ClassicSpeech, as the scheme JAWS Sounds (from JAWS)."""
		from . import migrator

		self._soundsAction(lambda: migrator.copyAllJawsSounds(self._facts()), "Copying all JAWS sounds into ClassicSpeech")

	def toggleJawsSounds(self):
		from . import classicSounds

		if classicSounds.isApplied(state.get(classicSounds.STATE_KEY)):
			self.restoreNvdaSounds()
		else:
			self.useJawsSounds()

	def openInputGestures(self):
		"""Open NVDA's own Input Gestures dialog."""
		try:
			wx.CallAfter(nvdaGui.mainFrame.onInputGesturesCommand, None)
		except Exception:
			_log().exception("jawsMigrator: could not open the Input Gestures dialog")

	def openRestore(self):
		from .gui import restoreDialog

		restoreDialog.showRestoreDialog()
		self._factsCache = None
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

	@script(description="Opens JAWS Migration Assistant settings, to choose which JAWS settings, schemes, voice profiles and voice aliases to import")
	def script_openImportSettings(self, gesture):
		wx.CallAfter(self.openImportSettings)

	@script(description="Opens NVDA's Input Gestures dialog, from the JAWS Migration Assistant")
	def script_openInputGestures(self, gesture):
		self.openInputGestures()

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

	@script(description="Plays JAWS sounds in place of NVDA's own sounds, through ClassicSpeech, or restores NVDA's own sounds")
	def script_toggleJawsSounds(self, gesture):
		wx.CallAfter(self.toggleJawsSounds)

	@script(description="Copies all JAWS sounds into ClassicSpeech, as the scheme JAWS Sounds (from JAWS)")
	def script_copyJawsSounds(self, gesture):
		wx.CallAfter(self.copyJawsSounds)

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
				layout = keyPlan.layoutId(value)
		# The JAWS keyboard layouts the last migration brought over, besides the one in use.
		migrated = state.get("lastMigration") or {}
		layouts = migrated.get("keyboardLayouts") if isinstance(migrated, dict) else None
		docs = jawsDocs.readJsd([os.path.join(jaws.sharedScriptsLanguageDir(language), "default.jsd")])
		self._keymapCache = (jaws, keyPlan.buildReverseMap(jkm, layout, layouts or None), docs, layout)
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
