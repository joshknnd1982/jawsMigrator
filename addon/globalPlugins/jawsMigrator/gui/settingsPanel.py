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
from .common import openFile


class JawsMigratorSettingsPanel(SettingsPanel):
	title = "JAWS Migration Assistant"
	#: Set by the global plugin so buttons can reach its actions.
	plugin = None

	def makeSettings(self, settingsSizer):
		helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.autoUpdate = helper.addItem(wx.CheckBox(self, label="Check for JAWS Migration Assistant updates &automatically"))
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
			status += " JAWS sounds play through ClassicSpeech, which is disabled."
		helper.addItem(wx.StaticText(self, label="JAWS sounds: " + status))
		soundButtons = guiHelper.ButtonHelper(wx.HORIZONTAL)
		useSounds = soundButtons.addButton(self, label="Use JAWS soun&ds in place of NVDA's")
		useSounds.Bind(wx.EVT_BUTTON, lambda event: self._run("useJawsSounds"))
		restoreSounds = soundButtons.addButton(self, label="Restore NVDA's o&wn sounds")
		restoreSounds.Bind(wx.EVT_BUTTON, lambda event: self._run("restoreNvdaSounds"))
		copySounds = soundButtons.addButton(self, label="Cop&y all JAWS sounds into ClassicSpeech")
		copySounds.Bind(wx.EVT_BUTTON, lambda event: self._run("copyJawsSounds"))
		helper.addItem(soundButtons)
		usable = classic.installed and classic.usable
		useSounds.Enable(usable)
		copySounds.Enable(usable)
		restoreSounds.Enable(classicSounds.isApplied(record))

		self.sleepApps = list(state.get("sleepApps") or [])
		self.sleepList = helper.addLabeledControl(
			"Applications where NVDA s&leeps, as JAWS did (clear one to stop):",
			wx.CheckListBox,
			choices=self.sleepApps,
		)
		for index in range(len(self.sleepApps)):
			self.sleepList.Check(index, True)
		if not self.sleepApps:
			self.sleepList.Enable(False)

		chooseButtons = guiHelper.ButtonHelper(wx.HORIZONTAL)
		choose = chooseButtons.addButton(self, label="&Choose which JAWS items to import...")
		choose.Bind(wx.EVT_BUTTON, lambda event: self._run("openImportSettings"))
		gestures = chooseButtons.addButton(self, label="Open NVDA's Input &Gestures dialog")
		gestures.Bind(wx.EVT_BUTTON, lambda event: self._run("openInputGestures"))
		helper.addItem(chooseButtons)

		buttons = guiHelper.ButtonHelper(wx.HORIZONTAL)
		openWizard = buttons.addButton(self, label="Open the JAWS &Migration Assistant...")
		openWizard.Bind(wx.EVT_BUTTON, lambda event: self._run("openAssistant"))
		restore = buttons.addButton(self, label="&Restore NVDA settings from a backup...")
		restore.Bind(wx.EVT_BUTTON, lambda event: self._run("openRestore"))
		report = buttons.addButton(self, label="Open the last migration re&port")
		report.Bind(wx.EVT_BUTTON, self._onReport)
		helper.addItem(buttons)

	def _run(self, action: str):
		plugin = type(self).plugin
		if plugin is None:
			return
		# Let NVDA's Settings dialog close its modal state first.
		wx.CallAfter(getattr(plugin, action))

	def _onReport(self, event):
		path = state.get("lastReport") or ""
		if path and os.path.isfile(path):
			openFile(path)
		else:
			gui.messageBox("There is no migration report yet.", "JAWS Migration Assistant", wx.OK | wx.ICON_INFORMATION, self)

	def onSave(self):
		keptApps = [name for index, name in enumerate(self.sleepApps) if self.sleepList.IsChecked(index)]
		state.update(
			{
				"checkForUpdatesAutomatically": self.autoUpdate.GetValue(),
				"activateJawsProfileAtStartup": self.atStartup.GetValue() if self.atStartup.IsEnabled() else state.get("activateJawsProfileAtStartup"),
				"sleepApps": keptApps,
			},
		)
		plugin = type(self).plugin
		if plugin is not None:
			plugin.applyRuntimeSettings()
