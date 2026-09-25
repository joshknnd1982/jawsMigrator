# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""The JAWS Migration Assistant category in NVDA's Settings dialog."""

from __future__ import annotations

import os

import wx

import gui
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel

from .. import (
	autoFormsMode,
	backspaceEcho,
	documentPolling,
	driveLetters,
	labelRepeats,
	layerSound,
	linksList,
	listCoordinates,
	listPosition,
	nvdaEnv,
	quickNavHeadings,
	startupFocus,
	state,
	trayChanges,
)
from .common import checkListClass, openFile


class JawsMigratorSettingsPanel(SettingsPanel):
	title = "JAWS Migration Assistant"
	#: Set by the global plugin so buttons can reach its actions.
	plugin = None

	def makeSettings(self, settingsSizer):
		helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		# NVDA's Settings dialog itself uses Alt+C (Categories) and Alt+A (Apply), so no access key here does.
		self.autoUpdate = helper.addItem(wx.CheckBox(self, label="Check for JAWS Migration Assistant &updates automatically"))
		self.autoUpdate.SetValue(bool(state.get("checkForUpdatesAutomatically")))
		checkNow = helper.addItem(wx.Button(self, label="Check for updates &now"))
		checkNow.Bind(wx.EVT_BUTTON, lambda event: self._run("checkForUpdates"))

		profileName = state.get("jawsProfileName") or ""
		profileExists = bool(profileName) and profileName in nvdaEnv.profileNames()
		label = f'Turn on the "{profileName}" profile when NVDA &starts' if profileExists else "Turn on the JAWS settings profile when NVDA &starts (no profile yet)"
		self.atStartup = helper.addItem(wx.CheckBox(self, label=label))
		self.atStartup.SetValue(bool(state.get("activateJawsProfileAtStartup")) and profileExists)
		self.atStartup.Enable(profileExists)
		# Some web pages put "radio button checked 1 of 2" in a control's label, which NVDA would say twice.
		self.sayOnce = helper.addItem(wx.CheckBox(self, label="Say a control's type and state &once, even when its label repeats them"))
		self.sayOnce.SetValue(labelRepeats.wanted(state.load()))
		# A temperature monitor changes its system tray icon's name every few seconds, which NVDA would read each time.
		self.quietTray = helper.addItem(wx.CheckBox(self, label="Say a system &tray icon when you move to it, not each time its program changes it"))
		self.quietTray.SetValue(trayChanges.wanted(state.load()))
		# Control+Alt+N, the key of NVDA's desktop shortcut, leaves the focus on the taskbar ("Copilot pinned");
		# JAWS, started with its own desktop shortcut's key, goes back to the window you were in.
		self.backFromTaskbar = helper.addItem(
			wx.CheckBox(self, label="When NVDA starts with the focus on the taskbar, as Control+Alt+N leaves it, go back to the window you were in"),
		)
		self.backFromTaskbar.SetValue(startupFocus.wanted(state.load()))
		# NVDA's H says "main landmark" before a heading in the page's main part; JAWS's H says the heading alone.
		self.headingAlone = helper.addItem(
			wx.CheckBox(self, label="When &quick navigation moves to a heading, don't say the landmark, region or list it is in"),
		)
		self.headingAlone.SetValue(quickNavHeadings.wanted(state.load()))
		# File Explorer's drives, Alt+Tab's windows and Outlook's messages have a row and column; JAWS never says them.
		self.listNoCoordinates = helper.addItem(
			wx.CheckBox(self, label="Lea&ve out the row and column numbers of items in lists, such as drives, files and messages"),
		)
		self.listNoCoordinates.SetValue(listCoordinates.wanted(state.load()))
		# NVDA says "3 of 3" wherever the focus goes; JAWS's Alt+Tab says a window's name alone, and its File Explorer
		# script says the position only when you move from item to item.
		self.positionLikeJaws = helper.addItem(
			wx.CheckBox(self, label="Don't say the position, such as 3 of 3, in Alt+Tab or when you come to a list in &File Explorer"),
		)
		self.positionLikeJaws.SetValue(listPosition.wanted(state.load()))
		# At its "most" symbol level NVDA says "Data left paren D colon right paren" for a drive; JAWS says "Data (D".
		self.driveLetter = helper.addItem(
			wx.CheckBox(self, label="Say a drive's name as &JAWS does, without the colon and parenthesis after its letter, as in Data (D:)"),
		)
		self.driveLetter.SetValue(driveLetters.wanted(state.load()))
		# NVDA says nothing for Backspace when a slow program deletes after NVDA stopped waiting; JAWS says it at once.
		self.backspaceSlow = helper.addItem(
			wx.CheckBox(self, label="Say what Backspac&e deletes, even when the program is slow to delete it"),
		)
		self.backspaceSlow.SetValue(backspaceEcho.wanted(state.load()))
		# Enhanced Control Support, as it comes, reads the focused control's value every 50 ms: a document's whole text.
		# With a large file in Notepad, that froze NVDA.
		self.documentsUnpolled = helper.addItem(
			wx.CheckBox(
				self,
				label="Keep Enhanced Control Support from reading a document's whole te&xt 20 times a second, which can freeze NVDA in a large file",
			),
		)
		self.documentsUnpolled.SetValue(documentPolling.wanted(state.load()))
		# NVDA uses focus mode on a web page's tabs and toolbars, so letters go to the page; JAWS stays in its virtual cursor.
		self.tabsBrowse = helper.addItem(wx.CheckBox(self, label="Stay in &browse mode when you Tab to a tab or a toolbar button on a web page"))
		self.tabsBrowse.SetValue(autoFormsMode.wanted(state.load()))
		# NVDA's Elements List says "Homepage; visited, 2 of 50, level 0"; JAWS's Links List says "Homepage, 2 of 34",
		# with "Current Page" before a link marked as current and a link's shortcut key after it.
		self.linksJaws = helper.addItem(
			wx.CheckBox(
				self,
				label="Show links in NVDA's Elements List as JAWS's Links List does: current page and shortcut keys, without visited, same page or level 0",
			),
		)
		self.linksJaws.SetValue(linksList.wanted(state.load()))
		# NVDA+Shift+J starts the assistant's commands with JAWS's layered keystroke sound, or with a beep.
		self.playLayerSound = helper.addItem(wx.CheckBox(self, label="Play JAWS's layered &keystroke sound for NVDA+Shift+J, instead of a beep"))
		self.playLayerSound.SetValue(layerSound.wanted(state.load()))

		from .. import classicSounds

		classic = nvdaEnv.classicSpeechInfo()
		record = state.get(classicSounds.STATE_KEY) or {}
		status = classicSounds.statusText(record)
		if not classic.installed:
			status += " JAWS sounds play through ClassicSpeech, which is not installed."
		elif not classic.usable:
			status += f" JAWS sounds play through ClassicSpeech, which isn't running now ({classic.describe})."
		helper.addItem(wx.StaticText(self, label="JAWS sounds: " + status))
		soundButtons = guiHelper.ButtonHelper(wx.HORIZONTAL)
		# Using or restoring sounds changes NVDA's settings (the start and exit sounds), so NVDA's Settings
		# dialog is saved and closed first, as for the assistant's other windows.
		useSounds = soundButtons.addButton(self, label="Use JAWS soun&ds in place of NVDA's")
		useSounds.Bind(wx.EVT_BUTTON, lambda event: self._run("useJawsSounds", closeSettings=True))
		restoreSounds = soundButtons.addButton(self, label="Restore NVDA's o&wn sounds")
		restoreSounds.Bind(wx.EVT_BUTTON, lambda event: self._run("restoreNvdaSounds", closeSettings=True))
		copySounds = soundButtons.addButton(self, label="Cop&y all JAWS sounds into ClassicSpeech")
		copySounds.Bind(wx.EVT_BUTTON, lambda event: self._run("copyJawsSounds"))
		helper.addItem(soundButtons)
		classicButtons = guiHelper.ButtonHelper(wx.HORIZONTAL)
		installClassic = classicButtons.addButton(
			self,
			label="Update ClassicSpeec&h to its newest version..." if classic.installed else "Install ClassicSpeec&h...",
		)
		installClassic.Bind(wx.EVT_BUTTON, lambda event: self._run("installClassicSpeech", closeSettings=True))
		helper.addItem(classicButtons)
		usable = classic.installed and classic.usable
		useSounds.Enable(usable)
		copySounds.Enable(usable)
		restoreSounds.Enable(classicSounds.isApplied(record))

		self.sleepList = helper.addLabeledControl(
			"Applications where NVDA s&leeps, as JAWS did (clear one to stop):",
			checkListClass(),
			choices=[],
		)
		self._showSleepApps()

		# These open the assistant's own windows, which change NVDA's settings and the assistant's state, so they
		# save and close NVDA's Settings dialog first (see _saveAndCloseSettings).
		chooseButtons = guiHelper.ButtonHelper(wx.HORIZONTAL)
		choose = chooseButtons.addButton(self, label="Choose which JAWS &items to import...")
		choose.Bind(wx.EVT_BUTTON, lambda event: self._run("openImportSettings", closeSettings=True))
		gestures = chooseButtons.addButton(self, label="Open NVDA's Input &Gestures dialog")
		gestures.Bind(wx.EVT_BUTTON, lambda event: self._run("openInputGestures"))
		helper.addItem(chooseButtons)

		buttons = guiHelper.ButtonHelper(wx.HORIZONTAL)
		openWizard = buttons.addButton(self, label="Open the JAWS &Migration Assistant...")
		openWizard.Bind(wx.EVT_BUTTON, lambda event: self._run("openAssistant", closeSettings=True))
		restore = buttons.addButton(self, label="&Restore NVDA settings from a backup...")
		restore.Bind(wx.EVT_BUTTON, lambda event: self._run("openRestore", closeSettings=True))
		report = buttons.addButton(self, label="Open the last migration re&port")
		report.Bind(wx.EVT_BUTTON, self._onReport)
		helper.addItem(buttons)
		self._rememberShown()

	def _showSleepApps(self):
		"""List the applications where NVDA sleeps now, every one checked."""
		self.sleepApps = list(state.get("sleepApps") or [])
		self.sleepList.Set(self.sleepApps)
		for index in range(len(self.sleepApps)):
			self.sleepList.Check(index, True)
		self.sleepList.Enable(bool(self.sleepApps))

	def _rememberShown(self):
		"""The values the panel showed, so that onSave writes only what the user changed in it."""
		self._shownAutoUpdate = self.autoUpdate.GetValue()
		self._shownAtStartup = self.atStartup.GetValue()
		self._shownSayOnce = self.sayOnce.GetValue()
		self._shownQuietTray = self.quietTray.GetValue()
		self._shownBackFromTaskbar = self.backFromTaskbar.GetValue()
		self._shownHeadingAlone = self.headingAlone.GetValue()
		self._shownListNoCoordinates = self.listNoCoordinates.GetValue()
		self._shownPositionLikeJaws = self.positionLikeJaws.GetValue()
		self._shownDriveLetter = self.driveLetter.GetValue()
		self._shownBackspaceSlow = self.backspaceSlow.GetValue()
		self._shownDocumentsUnpolled = self.documentsUnpolled.GetValue()
		self._shownTabsBrowse = self.tabsBrowse.GetValue()
		self._shownLinksJaws = self.linksJaws.GetValue()
		self._shownPlayLayerSound = self.playLayerSound.GetValue()

	def _run(self, action: str, closeSettings: bool = False):
		plugin = type(self).plugin
		if plugin is None:
			return
		if closeSettings and not self._saveAndCloseSettings():
			return
		# Runs once NVDA's Settings dialog has finished with this button press.
		wx.CallAfter(getattr(plugin, action))

	def _saveAndCloseSettings(self) -> bool:
		"""Press OK in NVDA's Settings dialog, as its Enter key does. True once the dialog has closed.

		The migration assistant, a restore and the choice of JAWS items change NVDA's settings and the
		assistant's state. If NVDA's Settings dialog stayed open behind them, pressing its OK button afterwards
		would save the values its panels showed before, over those changes. When a setting on another panel is
		not valid, NVDA says so and stays open, and nothing else opens.
		"""
		dialog = self.GetTopLevelParent()
		try:
			from gui.settingsDialogs import SettingsDialog
		except ImportError:
			return True
		if not isinstance(dialog, SettingsDialog):
			return True
		dialog.ProcessEvent(wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_OK))
		# NVDA hides the dialog at once and destroys it a moment later.
		return not dialog.IsShown()

	def _onReport(self, event):
		path = state.get("lastReport") or ""
		if path and os.path.isfile(path):
			openFile(path)
		else:
			gui.messageBox("There is no migration report yet.", "JAWS Migration Assistant", wx.OK | wx.ICON_INFORMATION, self)

	def onSave(self):
		# Only what was changed here, on top of the assistant's state as it is now: a migration or a restore
		# may have changed that state since this panel was made, and it must not be put back.
		updates = {}
		if self.autoUpdate.GetValue() != self._shownAutoUpdate:
			updates["checkForUpdatesAutomatically"] = self.autoUpdate.GetValue()
		if self.atStartup.IsEnabled() and self.atStartup.GetValue() != self._shownAtStartup:
			updates["activateJawsProfileAtStartup"] = self.atStartup.GetValue()
		if self.sayOnce.GetValue() != self._shownSayOnce:
			updates[labelRepeats.STATE_KEY] = self.sayOnce.GetValue()
		if self.quietTray.GetValue() != self._shownQuietTray:
			updates[trayChanges.STATE_KEY] = self.quietTray.GetValue()
		if self.backFromTaskbar.GetValue() != self._shownBackFromTaskbar:
			updates[startupFocus.STATE_KEY] = self.backFromTaskbar.GetValue()
		if self.headingAlone.GetValue() != self._shownHeadingAlone:
			updates[quickNavHeadings.STATE_KEY] = self.headingAlone.GetValue()
		if self.listNoCoordinates.GetValue() != self._shownListNoCoordinates:
			updates[listCoordinates.STATE_KEY] = self.listNoCoordinates.GetValue()
		if self.positionLikeJaws.GetValue() != self._shownPositionLikeJaws:
			updates[listPosition.STATE_KEY] = self.positionLikeJaws.GetValue()
		if self.driveLetter.GetValue() != self._shownDriveLetter:
			updates[driveLetters.STATE_KEY] = self.driveLetter.GetValue()
		if self.backspaceSlow.GetValue() != self._shownBackspaceSlow:
			updates[backspaceEcho.STATE_KEY] = self.backspaceSlow.GetValue()
		if self.documentsUnpolled.GetValue() != self._shownDocumentsUnpolled:
			updates[documentPolling.STATE_KEY] = self.documentsUnpolled.GetValue()
		if self.tabsBrowse.GetValue() != self._shownTabsBrowse:
			updates[autoFormsMode.STATE_KEY] = self.tabsBrowse.GetValue()
		if self.linksJaws.GetValue() != self._shownLinksJaws:
			updates[linksList.STATE_KEY] = self.linksJaws.GetValue()
		if self.playLayerSound.GetValue() != self._shownPlayLayerSound:
			updates[layerSound.STATE_KEY] = self.playLayerSound.GetValue()
		cleared = {name for index, name in enumerate(self.sleepApps) if not self.sleepList.IsChecked(index)}
		if cleared:
			updates["sleepApps"] = [name for name in state.get("sleepApps") or [] if name not in cleared]
		if updates:
			state.update(updates)
		# After Apply the dialog stays open: from now on it shows, and compares with, what was saved.
		self._showSleepApps()
		self._rememberShown()
		plugin = type(self).plugin
		if plugin is not None:
			plugin.applyRuntimeSettings()
