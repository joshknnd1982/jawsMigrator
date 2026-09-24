# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""JAWS Migration Assistant: brings a JAWS user's settings, voices, sounds and keystrokes into NVDA.

This global plugin adds the assistant to NVDA's Tools menu and Settings dialog,
offers its commands as a layer after NVDA+Shift+J (each command can also get
its own gesture in Input Gestures), and keeps the migrated behavior working
while NVDA runs: JAWS sound effects in place of NVDA's sounds, sleep mode in
the applications where JAWS slept, and the JAWS settings profile at startup.
It also has NVDA say a control's type and state once when a web page repeats
them in the control's label (see labelRepeats), and NVDA+Shift+J plays JAWS's
layered keystroke sound (see layerSound).
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

from . import debugLog, insertKeys, jawsDetect, jawsDocs, jawsFiles, jawsKeyMap, keyPlan, nvdaEnv, state, systemCheck, updater
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
	"kb:c": "installClassicSpeech",
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
	"C, install ClassicSpeech, or update it to its newest version. "
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
		#: JAWS keystrokes that differ with Insert and with Caps Lock as the JAWS key (see insertKeys).
		self._insertKeys: dict = {}
		self._keymapCache = None
		self.updater = updater.UpdateChecker()
		if self._secure:
			return
		try:
			self.applyRuntimeSettings()
		except Exception:
			# The assistant's menus, settings and commands must work even when one of its own settings can't apply.
			debugLog.error("could not apply the assistant's own settings")
		try:
			import config

			# Reloading NVDA's configuration rebuilds its symbol dictionaries, without JAWS's rule for times.
			config.post_configReset.register(self._onConfigReset)
		except Exception:
			debugLog.error("could not follow NVDA's configuration reloads")
		self._createMenu()
		try:
			from .gui import settingsPanel

			settingsPanel.JawsMigratorSettingsPanel.plugin = self
			nvdaGui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(settingsPanel.JawsMigratorSettingsPanel)
		except Exception:
			debugLog.error("could not add the settings panel")
		self.updater.scheduleAutomaticCheck()
		self._startupProfileTimer = wx.CallLater(2000, self._activateProfileAtStartup)
		# Voices written by versions 1.0 to 1.2 get their fixed rate, pitch and volume taken out, once.
		self._repairTimer = wx.CallLater(20000, self._repairVoices)
		if not state.get("welcomeShown"):
			# Once, after installation: give NVDA time to finish starting and speaking first.
			self._firstRunTimer = wx.CallLater(10000, self._firstRun)

	def terminate(self):
		self._silenceExit()
		self.updater.stop()
		# Nothing this instance scheduled may run once NVDA has unloaded it (for example after reloading plugins).
		for name in ("_startupProfileTimer", "_firstRunTimer", "_repairTimer"):
			try:
				timer = getattr(self, name, None)
				if timer is not None:
					timer.Stop()
			except Exception:
				pass
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
		try:
			import config

			config.post_configReset.unregister(self._onConfigReset)
		except Exception:
			pass
		try:
			from . import numberSymbols

			numberSymbols.unregister()
		except Exception:
			pass
		try:
			from . import labelRepeats

			labelRepeats.unregister()
		except Exception:
			pass
		super().terminate()

	def _onConfigReset(self, factoryDefaults=False):
		# NVDA sets up its symbol dictionaries again after this notification, in the same call.
		wx.CallAfter(self.applyRuntimeSettings)

	# -- start up ----------------------------------------------------------------------

	def applyRuntimeSettings(self):
		"""Apply the assistant's own settings: the applications where NVDA sleeps, JAWS's Insert keystrokes,
		JAWS's rule for a colon between digits, a control's type and state said once, and the layer's sound.

		Each one is applied on its own: one that fails is logged, and never keeps the others from working.
		"""
		data = state.load()
		if data.get("jawsSoundsEnabled") or data.get("soundReplacements"):
			# Version 1.1 played JAWS sounds itself. They play through ClassicSpeech now (classicSounds).
			state.update({"jawsSoundsEnabled": False, "soundReplacements": {}})
			_log().info("jawsMigrator: JAWS sounds now play through ClassicSpeech; version 1.1's own sound replacement is off")
		self._sleepApps = {str(name).lower() for name in data.get("sleepApps") or []}
		self._insertKeys = insertKeys.load(data)
		try:
			from . import numberSymbols

			# A restore can bring back settings from before any migration; the rule follows.
			if numberSymbols.wanted(data):
				numberSymbols.register()
			else:
				numberSymbols.unregister()
		except Exception:
			debugLog.error("could not apply JAWS's rule for a colon between digits")
		try:
			from . import labelRepeats

			# Not a JAWS setting: it keeps NVDA from saying what a web page already put in a control's label.
			if labelRepeats.wanted(data):
				labelRepeats.register()
			else:
				labelRepeats.unregister()
		except Exception:
			debugLog.error("could not apply saying a control's type and state once")
		try:
			from . import layerSound

			# A migration or a restore can change which JAWS the layer's sound comes from; look again next time.
			layerSound.forget()
		except Exception:
			debugLog.error("could not reset the layer's sound")

	def _silenceExit(self):
		"""While NVDA exits after a migration, leave out the Screen Curtain sound it plays then (see exitSounds)."""
		if self._secure:
			return
		try:
			from . import exitSounds

			if exitSounds.nvdaIsExiting() and exitSounds.wanted(state.load(), exitSounds.startAndExitSoundsOff()):
				exitSounds.silenceWhileExiting(nvdaEnv.wavesFolder())
		except Exception:
			debugLog.error("could not keep NVDA silent as it exits")

	def _repairVoices(self):
		"""Once, after an update: repair what versions 1.0 to 1.3 wrote, then explain their JAWS profile.

		The repairs run one after another, each after its own backup where it changes NVDA's settings.
		Meanwhile the assistant counts as busy, so no migration, restore or sounds change runs at the same time.
		"""
		self._repairTimer = None
		if self._busy:
			self._repairTimer = wx.CallLater(60000, self._repairVoices)
			return
		from . import dictRepair, gestureRepair, migrator, rateRepair

		def insertKeysRepair(announce, done=None):
			def reload():
				self._insertKeys = insertKeys.load(state.load())
				if done is not None:
					done()

			insertKeys.repairOnce(self._jawsKeymapFiles, announce, reload)

		steps = [
			("the repair of ClassicSpeech voices", migrator.repairClassicSpeechVoices),
			("the repair of dictionary rules", dictRepair.repairOnce),
			("the repair of keystrokes", gestureRepair.repairOnce),
			("the Insert keystrokes of the JAWS Laptop layout", insertKeysRepair),
			("the repair of the Eloquence rate", lambda announce, done=None: rateRepair.repairOnce(announce, migrator._backupFirst, done)),
		]
		self._busy = True
		self._runRepairs(steps)

	def _runRepairs(self, steps):
		if not steps:
			self._busy = False
			self._repairTimer = wx.CallLater(5000, self._profileNotice)
			return
		(what, repair), rest = steps[0], steps[1:]
		from . import migrator

		following = migrator.callOnce(lambda: wx.CallAfter(self._runRepairs, rest))
		try:
			repair(lambda message: ui.message(message), done=following)
		except Exception:
			debugLog.error(f"{what} failed")
			following()

	def _profileNotice(self):
		"""Once: tell a user of versions 1.0 to 1.2 why their separate JAWS profile switches off, and what to do."""
		self._repairTimer = None
		name = state.get("jawsProfileName")
		if state.get("profileNoticeShown") or not name or not state.get("activateJawsProfileAtStartup"):
			return
		if self._busy or self._secure:
			self._repairTimer = wx.CallLater(60000, self._profileNotice)
			return
		state.set("profileNoticeShown", True)
		if name not in nvdaEnv.profileNames():
			return
		answer = messageBox(
			f'Your JAWS settings are in the NVDA configuration profile "{name}", which the JAWS Migration Assistant turns on '
			"when NVDA starts. NVDA can have only one profile turned on this way, and some add-ons, such as Custom Browse Mode, "
			"turn on their own profile, which switches yours off. Your JAWS settings then stop applying: speech can change "
			'speed, and NVDA says things JAWS doesn\'t, such as "clickable" on web pages.\n\n'
			"To keep your JAWS settings on all the time, migrate again and choose NVDA's normal configuration, now the "
			"recommended choice. NVDA's settings are backed up first, and the profile then no longer turns on by itself.\n\n"
			"Open the JAWS Migration Assistant now?",
			TITLE,
			wx.YES | wx.NO | wx.ICON_INFORMATION,
		)
		debugLog.note(f"explained the separate profile {name}; open the assistant: {answer == wx.YES}")
		if answer == wx.YES:
			self.openAssistant()

	def openDebugLog(self):
		path = debugLog.generalLogPath()
		if path and os.path.isfile(path):
			openFile(path)
		else:
			messageBox(f"There is no debug log yet. It will be at {path}. Each migration also writes debug.log in its own folder.", TITLE, wx.OK | wx.ICON_INFORMATION)

	def _activateProfileAtStartup(self):
		try:
			name = state.get("jawsProfileName")
			if name and state.get("activateJawsProfileAtStartup") and name in nvdaEnv.profileNames():
				from . import nvdaApply

				if nvdaApply.activeManualProfile() is None:
					nvdaApply.activateProfile(name)
		except Exception:
			debugLog.error("could not turn on the JAWS settings profile")

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
				("&Install or update ClassicSpeech...", lambda event: self.installClassicSpeech()),
				("&Restore NVDA settings from a backup...", lambda event: self.openRestore()),
				("Open the last migration &report", lambda event: self.openLastReport()),
				("What does a &JAWS keystroke do in NVDA?", lambda event: wx.CallLater(300, self._startKeystrokeHelp)),
				("Check for &updates", lambda event: self.checkForUpdates()),
				("Open the &debug log", lambda event: self.openDebugLog()),
				("&Help", lambda event: self.openHelp()),
			)
			for label, handler in items:
				item = self._menu.Append(wx.ID_ANY, label)
				nvdaGui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, handler, item)
			self._menuItem = toolsMenu.AppendSubMenu(self._menu, "&JAWS Migration Assistant")
		except Exception:
			debugLog.error("could not add the Tools menu")
		try:
			preferencesMenu = nvdaGui.mainFrame.sysTrayIcon.preferencesMenu
			self._preferencesItem = preferencesMenu.Append(
				wx.ID_ANY,
				"&JAWS Migration Assistant settings...",
				"Choose which JAWS settings, schemes, voice profiles and voice aliases to import",
			)
			nvdaGui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, lambda event: self.openImportSettings(), self._preferencesItem)
		except Exception:
			debugLog.error("could not add the Preferences menu item")

	# -- actions -------------------------------------------------------------------------

	def onMenuOpen(self, event):
		self.openAssistant()

	def _nvdaSettingsDialogOpen(self) -> str:
		"""The title of an open NVDA settings dialog (Settings, Input Gestures, a speech dictionary...), or "".

		Closed with OK, such a dialog saves everything it shows, which would undo what the assistant
		changed meanwhile: settings, keystrokes or dictionary rules.
		"""
		try:
			from gui.settingsDialogs import SettingsDialog

			created = SettingsDialog.DialogState.CREATED
			for dialog, dialogState in list(SettingsDialog._instances.items()):
				if dialogState == created and dialog.IsShown():
					return dialog.GetTitle() or "an NVDA settings dialog"
		except Exception:
			pass
		return ""

	def _refuseWhileSettingsOpen(self, action: str) -> bool:
		"""Say why ``action`` can't start while an NVDA settings dialog is open. True when it was refused."""
		title = self._nvdaSettingsDialogOpen()
		if not title:
			return False
		ui.message(
			f"Close {title} first. When you press OK there, it saves the settings it shows, which would undo {action}.",
		)
		return True

	def openAssistant(self, firstRun: bool = False):
		if self._secure:
			return
		if self._busy:
			ui.message("The JAWS Migration Assistant is already open.")
			return
		if self._refuseWhileSettingsOpen("the migration"):
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
			if not facts.classicSpeech.installed:
				# ClassicSpeech carries JAWS schemes, voice aliases and sounds; offer its newest version first.
				from .gui import classicSpeechOffer

				if classicSpeechOffer.offerInstall(automatic=True):
					# It runs after NVDA restarts; the assistant is opened again then.
					self._factsCache = None
					return
			from .gui import wizard

			wizard.runWizard(facts)
			# A migration changes NVDA's synthesizers, profiles and add-ons; check again next time.
			self._factsCache = None
			self.applyRuntimeSettings()
		except Exception:
			debugLog.error("the assistant failed")
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
			debugLog.error("the settings dialog failed")
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
			debugLog.error("the JAWS sounds action failed")
			messageBox(f"That could not be done, and NVDA's sounds were not changed: {error}", TITLE, wx.OK | wx.ICON_ERROR)
		finally:
			self._busy = False

	def _offerClassicSpeech(self) -> None:
		"""JAWS sounds need ClassicSpeech, which is missing: offer to install its newest version."""
		from .gui import classicSpeechOffer

		if classicSpeechOffer.offerInstall(automatic=False):
			self._factsCache = None

	def installClassicSpeech(self):
		"""Install ClassicSpeech, or update it to its newest release, after backing up."""
		if self._secure:
			return
		if self._busy:
			ui.message("The JAWS Migration Assistant is busy. Finish or close it first.")
			return
		self._busy = True
		try:
			from .gui import classicSpeechOffer

			classicSpeechOffer.installOrUpdate()
		except Exception as error:
			debugLog.error("installing ClassicSpeech failed")
			messageBox(f"ClassicSpeech could not be installed: {error}", TITLE, wx.OK | wx.ICON_ERROR)
		finally:
			self._factsCache = None
			self._busy = False

	def useJawsSounds(self):
		"""Play JAWS sounds in place of NVDA's own sounds, through ClassicSpeech, after backing up."""
		from . import backup, migrator

		if self._refuseWhileSettingsOpen("the change of sounds"):
			return

		def action():
			facts = self._facts()
			if not facts.classicSpeech.installed:
				self._offerClassicSpeech()
				return None
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

		if self._refuseWhileSettingsOpen("the change of sounds"):
			return
		self._soundsAction(migrator.restoreNvdaSounds, "Restoring NVDA's own sounds")

	def copyJawsSounds(self):
		"""Copy every JAWS sound into ClassicSpeech, as the scheme JAWS Sounds (from JAWS)."""
		from . import migrator

		def action():
			facts = self._facts()
			if not facts.classicSpeech.installed:
				self._offerClassicSpeech()
				return None
			return migrator.copyAllJawsSounds(facts)

		self._soundsAction(action, "Copying all JAWS sounds into ClassicSpeech")

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
			debugLog.error("could not open the Input Gestures dialog")

	def openRestore(self):
		if self._secure:
			return
		# A restore must never run while a migration, a JAWS sounds action or another restore changes the same files.
		if self._busy:
			ui.message("The JAWS Migration Assistant is busy. Finish or close it first.")
			return
		if self._refuseWhileSettingsOpen("the restore"):
			return
		from .gui import restoreDialog

		self._busy = True
		try:
			restoreDialog.showRestoreDialog()
		finally:
			self._busy = False
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
			# Once per run of the application: when the user turns sleep mode off (NVDA+Shift+Z), NVDA sends
			# the focus event again, and sleep mode must stay off.
			if appModule is None or getattr(appModule, "_jawsMigratorSlept", False):
				return
			if appModule.appName.lower() in self._sleepApps:
				appModule._jawsMigratorSlept = True
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
			if self._insertKeys:
				# Insert+J and Caps Lock+J are both NVDA+J: with Insert, the JAWS Insert keystroke's command
				# runs; with Caps Lock, NVDA goes on to find the command as usual (see insertKeys).
				found = insertKeys.scriptFor(gesture, self._insertKeys)
				if found is not None:
					return found
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
		# The sound JAWS plays when a layered keystroke starts (Insert+Space), or a beep where JAWS has none.
		if not self._playLayerSound():
			tones.beep(660, 40)

	def _playLayerSound(self) -> bool:
		"""JAWS's layered keystroke sound (see layerSound). False when there is none or it can't play."""
		try:
			from . import layerSound

			return layerSound.play()
		except Exception:
			debugLog.error("could not play JAWS's layered keystroke sound")
			return False

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

	@script(description="Installs ClassicSpeech, or updates it to its newest version, from GitHub")
	def script_installClassicSpeech(self, gesture):
		wx.CallAfter(self.installClassicSpeech)

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

	def _jawsKeymapSource(self):
		"""``(JAWS installation, merged default key map, keyboard layout in use)``, or None without JAWS."""
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
		return jaws, jkm, layout

	def _jawsKeymapFiles(self):
		"""``(merged default key map, JAWS keyboard layout in use)``, or None (see insertKeys.repairOnce)."""
		source = self._jawsKeymapSource()
		return None if source is None else (source[1], source[2])

	def _jawsKeymap(self):
		"""JAWS's merged default key map, its keyboard layout and script descriptions, cached."""
		if self._keymapCache is not None:
			return self._keymapCache
		source = self._jawsKeymapSource()
		if source is None:
			return None
		jaws, jkm, layout = source
		language = jaws.primaryLanguage or "enu"
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
			debugLog.error("could not read the JAWS key map")
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
			# The keystroke matters: paragraph commands on keys that aren't quick navigation keys have their own target.
			targets = jawsKeyMap.getNvdaTargets(jawsScript, jawsKey)
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
