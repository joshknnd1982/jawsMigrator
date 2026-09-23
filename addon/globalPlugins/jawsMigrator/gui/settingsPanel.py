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

from .. import nvdaEnv, state
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
