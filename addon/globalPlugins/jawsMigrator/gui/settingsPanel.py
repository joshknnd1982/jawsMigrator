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
	backForward,
	backspaceEcho,
	browserPages,
	documentPolling,
	documentValues,
	driveLetters,
	emptyAlerts,
	exitMessage,
	fieldEdges,
	formFields,
	labelRepeats,
	layerSound,
	linkSpeech,
	linksList,
	listBounds,
	listCoordinates,
	listPosition,
	notificationHistory,
	nvdaEnv,
	outlookMessages,
	outlookPages,
	outlookPictures,
	outlookRows,
	outlookStatusBar,
	pageReady,
	profileSwitches,
	quickNavHeadings,
	screenShade,
	speechHistory,
	startMessage,
	startupFocus,
	state,
	trayChanges,
	webRegions,
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
		# NVDA's H says "main landmark" before a heading in the page's main part; JAWS's H says the heading alone. JAWS's
		# E says the edit field alone, and "blank, placeholder" and the placeholder for an empty one. On a web page, JAWS's
		# other quick keys (B, C, G, L, I, R, T...) say the element alone too (issue 35).
		self.headingAlone = helper.addItem(
			wx.CheckBox(
				self,
				label='When &quick navigation moves to a heading, a button or anything else, don\'t say the landmark, region or list it is in, and say "blank, placeholder" for an empty edit field',
			),
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
		# NVDA listens for a focused document's Value, its whole text, which Windows 11's Notepad builds at every key.
		self.documentsNoValue = helper.addItem(
			wx.CheckBox(
				self,
				label="Keep NVDA from having a document build its whole text at every key, which slows typing in a large file",
			),
		)
		self.documentsNoValue.SetValue(documentValues.wanted(state.load()))
		# NVDA uses focus mode on a web page's tabs and toolbars, so letters go to the page; JAWS stays in its virtual cursor.
		self.tabsBrowse = helper.addItem(wx.CheckBox(self, label="Stay in &browse mode when you Tab to a tab or a toolbar button on a web page"))
		self.tabsBrowse.SetValue(autoFormsMode.wanted(state.load()))
		# NVDA's Elements List says "Homepage; visited, 2 of 50, level 0"; JAWS's Links List says "Homepage, 2 of 34",
		# with "Current Page" before a link marked as current and a link's shortcut key after it. On a page without links JAWS
		# says "no links", and the list starts on the link at the cursor, which is the link you activated when you come back.
		self.linksJaws = helper.addItem(
			wx.CheckBox(
				self,
				label=(
					"Show links in NVDA's Elements List as JAWS's Links List does: current page and shortcut keys, without visited, "
					'same page or level 0; "no links" on a page without links; activating a link moves to it'
				),
			),
		)
		self.linksJaws.SetValue(linksList.wanted(state.load()))
		# JAWS has a list of one kind for each of its keys (Insert+F7 its Links List); NVDA's Elements List has every kind,
		# with radio buttons to choose, and opens on the kind chosen last.
		self.listKeysJaws = helper.addItem(
			wx.CheckBox(
				self,
				label=(
					"Open a list of one kind for each JAWS list key, as JAWS does: Insert+F7 links, Insert+F6 headings, "
					"Insert+F5 form fields, Control+Insert+B buttons, Control+Insert+R regions"
				),
			),
		)
		self.listKeysJaws.SetValue(linksList.keysWanted(state.load()))
		# GitHub adds an alert with nothing in it as its page loads; NVDA said "alert" alone, JAWS says nothing.
		self.quietEmptyAlerts = helper.addItem(
			wx.CheckBox(self, label='Don\'t say "alert" for an alert with nothing in it, as on GitHub pages'),
		)
		self.quietEmptyAlerts.SetValue(emptyAlerts.wanted(state.load()))
		# NVDA's automatic focus mode for caret movement goes on past a field at its start or end with any caret key;
		# JAWS's Auto Forms Mode stays in it, but for Up or Down Arrow in a field of one line.
		self.stayInFields = helper.addItem(
			wx.CheckBox(
				self,
				label="Stay in an edit field on a web page when the arrow keys reach its start or end; only Up and Down Arrow leave a field of one line",
			),
		)
		self.stayInFields.SetValue(fieldEdges.wanted(state.load()))
		# End or Down Arrow in Outlook's message list made NVDA say the message left, as unread, before the one moved to;
		# JAWS says only the message you move to.
		self.outlookLeftMessage = helper.addItem(
			wx.CheckBox(self, label="When you move in Outlook's message list, say only the message you come to, not the one you leave"),
		)
		self.outlookLeftMessage.SetValue(outlookRows.wanted(state.load()))
		# NVDA said "page 1, section 1" at the first line it read in an Outlook message (through UI Automation);
		# JAWS says no page or section in Outlook.
		self.outlookNoPages = helper.addItem(wx.CheckBox(self, label="Don't say page and section numbers in Outlook messages"))
		self.outlookNoPages.SetValue(outlookPages.wanted(state.load()))
		# NVDA said "link" or "blank" for each picture in an e-mail made of pictures; JAWS says their alternative text (issue 42).
		self.outlookPictures = helper.addItem(
			wx.CheckBox(self, label="Say the alternative text of a picture in an Outlook message, as JAWS does"),
		)
		self.outlookPictures.SetValue(outlookPictures.wanted(state.load()))
		# JAWS said "Send Mail Link" for an address, "list of 3 items" and "list end" around a list, and no heading for
		# the From line of the message it quoted; NVDA said "link", no list, and "heading level 1, From:".
		self.outlookAsJaws = helper.addItem(
			wx.CheckBox(
				self,
				label='Say Outlook messages as JAWS does: "send mail link" for an e-mail address, where lists start and end, and no heading for the From line of a quoted message',
			),
		)
		self.outlookAsJaws.SetValue(outlookMessages.wanted(state.load()))
		# JAWS's "Messages automatically read": the tester's JAWS reads a message only with the arrow keys (issue 23),
		# so this is off unless turned on.
		self.outlookReadOnOpen = helper.addItem(
			wx.CheckBox(self, label="Read an Outlook message from the top when it opens, as JAWS's \"Messages automatically read\" does"),
		)
		self.outlookReadOnOpen.SetValue(outlookMessages.readWanted(state.load()))
		# JAWS's Insert+Page Down in Outlook said "Items in View 2,675", "Unread Items in View 1,135" and "Zoom 10%"; NVDA
		# said "Status Bar", then the view buttons with their tooltips and the zoom slider with its buttons too (issue 26).
		self.outlookStatusBar = helper.addItem(
			wx.CheckBox(self, label="Read Outlook's status bar as JAWS does: its items and zoom, without the view and zoom buttons"),
		)
		self.outlookStatusBar.SetValue(outlookStatusBar.wanted(state.load()))
		# The Columns Review add-on, as it comes, says "List top" at a list's first item, as File Explorer opens a folder,
		# and "List bottom" at its last; JAWS says the item alone.
		self.quietListBounds = helper.addItem(
			wx.CheckBox(self, label='Keep Columns Review from saying "List top" and "List bottom" at the ends of a list'),
		)
		self.quietListBounds.SetValue(listBounds.wanted(state.load()))
		# Each Alt+Tab into or out of Edge held NVDA up for two seconds or more (issue 31): Columns Review and Emoticons, as
		# they come, took about a second at each of NVDA's configuration profile switches.
		self.quickProfileSwitches = helper.addItem(
			wx.CheckBox(
				self,
				label="Keep Columns Review and Emoticons from holding NVDA up each time you switch programs or browse mode turns on or off",
			),
		)
		self.quickProfileSwitches.SetValue(profileSwitches.wanted(state.load()))
		# NVDA said "HEADLINES, same page, link, Homepage, heading, level 3" for a heading on a web page; JAWS said
		# "HEADLINES, heading level 3, Link": no "same page" for a link to the page itself, no title, the heading first.
		self.linksAsJaws = helper.addItem(
			wx.CheckBox(
				self,
				label='Say links on web pages as JAWS does: "same page" only for a link to a place on the page, no link titles, and "link" after a heading',
			),
		)
		self.linksAsJaws.SetValue(linkSpeech.wanted(state.load()))
		# NVDA said "main landmark", then "Join the conversation, edit, multi line, blank" for reddit's reply box; JAWS
		# said "edit, blank, placeholder, Join the conversation".
		self.formFieldsAsJaws = helper.addItem(
			wx.CheckBox(
				self,
				label='Say edit fields on web pages as JAWS does: "blank, placeholder" and the placeholder, no "multi line", and no landmark you were already in',
			),
		)
		self.formFieldsAsJaws.SetValue(formFields.wanted(state.load()))
		# NVDA said "... - Microsoft Edge, window", "... - Microsoft Edge, region" and "..., document" with the page's
		# address as a reddit post opened (issue 30); JAWS said the titles alone.
		self.browserPagesAsJaws = helper.addItem(
			wx.CheckBox(
				self,
				label='Say Edge and Chrome windows and pages as JAWS does: their titles, without "window", "document", the address or Edge\'s "region"',
			),
		)
		self.browserPagesAsJaws.SetValue(browserPages.wanted(state.load()))
		# ClassicSpeech's "Notify when page is ready" said nothing for some pages (issues 43 and 44): a page the browser
		# said had loaded before NVDA had its buffer ready.
		self.pageReadyForEveryPage = helper.addItem(
			wx.CheckBox(
				self,
				label="Say ClassicSpeech's \"Page ready\" message and page summary for every page that loads, also one that finishes loading before NVDA is ready for it",
			),
		)
		self.pageReadyForEveryPage.SetValue(pageReady.wanted(state.load()))
		# JAWS said "MainRegion" and "new Comment group" where NVDA said "main landmark" and "new Comment grouping"
		# (issue 30), and, reading, "list of 2 items", "list end" and "main region end", and no banner or search region.
		self.webRegionsAsJaws = helper.addItem(
			wx.CheckBox(
				self,
				label='Say regions, groups and lists on web pages with JAWS\'s words: "main region", "group", "list of 2 items", "main region end"',
			),
		)
		self.webRegionsAsJaws.SetValue(webRegions.wanted(state.load()))
		# NVDA said nothing after Alt+Left on reddit (issue 32); JAWS said "Back", then the line its cursor was on.
		self.backForwardAsJaws = helper.addItem(
			wx.CheckBox(
				self,
				label='Say "Back" and "Forward" for Alt+Left and Alt+Right in web browsers, and read the line a page comes back to, as JAWS does',
			),
		)
		self.backForwardAsJaws.SetValue(backForward.wanted(state.load()))
		# JAWS keeps the last 500 things it said for Insert+Space, then H; the assistant's layer has the same keys.
		self.keepSpeechHistory = helper.addItem(
			wx.CheckBox(self, label="Keep what NVDA says, for NVDA+Shift+J then H, as JAWS's speech history"),
		)
		self.keepSpeechHistory.SetValue(speechHistory.wanted(state.load()))
		# JAWS keeps the notifications it gets for Insert+Space, then N and Shift+N (issue 33).
		self.keepNotificationHistory = helper.addItem(
			wx.CheckBox(self, label="Keep the notifications Windows and programs send, for NVDA+Shift+J then N, as JAWS's notification history"),
		)
		self.keepNotificationHistory.SetValue(notificationHistory.wanted(state.load()))
		# JAWS says "JAWS" as it starts, with no option for it; NVDA starts without a word (issue 41).
		self.sayReady = helper.addItem(
			wx.CheckBox(self, label='Say "NVDA is ready." when NVDA starts, and don\'t let a key stop it'),
		)
		self.sayReady.SetValue(startMessage.wanted(state.load()))
		# JAWS's Insert+F4 says "Unloading JAWS" where its JAWS Messages are on; NVDA exits without a word (issue 34).
		self.sayUnloading = helper.addItem(
			wx.CheckBox(self, label='Say "Unloading NVDA" as NVDA exits, as JAWS says "Unloading JAWS"'),
		)
		self.sayUnloading.SetValue(exitMessage.wanted(state.load()))
		# NVDA turns the screen curtain on as it starts and says so only on a braille display (issue 37).
		self.sayScreenCurtainAtStart = helper.addItem(
			wx.CheckBox(self, label='Say "Screen curtain on" when NVDA starts with the screen curtain on'),
		)
		self.sayScreenCurtainAtStart.SetValue(screenShade.wanted(state.load()))
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
		self._shownDocumentsNoValue = self.documentsNoValue.GetValue()
		self._shownTabsBrowse = self.tabsBrowse.GetValue()
		self._shownLinksJaws = self.linksJaws.GetValue()
		self._shownListKeysJaws = self.listKeysJaws.GetValue()
		self._shownQuietEmptyAlerts = self.quietEmptyAlerts.GetValue()
		self._shownStayInFields = self.stayInFields.GetValue()
		self._shownOutlookLeftMessage = self.outlookLeftMessage.GetValue()
		self._shownOutlookNoPages = self.outlookNoPages.GetValue()
		self._shownOutlookPictures = self.outlookPictures.GetValue()
		self._shownOutlookAsJaws = self.outlookAsJaws.GetValue()
		self._shownOutlookReadOnOpen = self.outlookReadOnOpen.GetValue()
		self._shownOutlookStatusBar = self.outlookStatusBar.GetValue()
		self._shownQuietListBounds = self.quietListBounds.GetValue()
		self._shownQuickProfileSwitches = self.quickProfileSwitches.GetValue()
		self._shownLinksAsJaws = self.linksAsJaws.GetValue()
		self._shownFormFieldsAsJaws = self.formFieldsAsJaws.GetValue()
		self._shownBrowserPagesAsJaws = self.browserPagesAsJaws.GetValue()
		self._shownPageReadyForEveryPage = self.pageReadyForEveryPage.GetValue()
		self._shownWebRegionsAsJaws = self.webRegionsAsJaws.GetValue()
		self._shownBackForwardAsJaws = self.backForwardAsJaws.GetValue()
		self._shownKeepSpeechHistory = self.keepSpeechHistory.GetValue()
		self._shownKeepNotificationHistory = self.keepNotificationHistory.GetValue()
		self._shownSayReady = self.sayReady.GetValue()
		self._shownSayUnloading = self.sayUnloading.GetValue()
		self._shownSayScreenCurtainAtStart = self.sayScreenCurtainAtStart.GetValue()
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
		if self.documentsNoValue.GetValue() != self._shownDocumentsNoValue:
			updates[documentValues.STATE_KEY] = self.documentsNoValue.GetValue()
		if self.tabsBrowse.GetValue() != self._shownTabsBrowse:
			updates[autoFormsMode.STATE_KEY] = self.tabsBrowse.GetValue()
		if self.linksJaws.GetValue() != self._shownLinksJaws:
			updates[linksList.STATE_KEY] = self.linksJaws.GetValue()
		if self.listKeysJaws.GetValue() != self._shownListKeysJaws:
			updates[linksList.KEYS_KEY] = self.listKeysJaws.GetValue()
		if self.quietEmptyAlerts.GetValue() != self._shownQuietEmptyAlerts:
			updates[emptyAlerts.STATE_KEY] = self.quietEmptyAlerts.GetValue()
		if self.stayInFields.GetValue() != self._shownStayInFields:
			updates[fieldEdges.STATE_KEY] = self.stayInFields.GetValue()
		if self.outlookLeftMessage.GetValue() != self._shownOutlookLeftMessage:
			updates[outlookRows.STATE_KEY] = self.outlookLeftMessage.GetValue()
		if self.outlookNoPages.GetValue() != self._shownOutlookNoPages:
			updates[outlookPages.STATE_KEY] = self.outlookNoPages.GetValue()
		if self.outlookPictures.GetValue() != self._shownOutlookPictures:
			updates[outlookPictures.STATE_KEY] = self.outlookPictures.GetValue()
		if self.outlookAsJaws.GetValue() != self._shownOutlookAsJaws:
			updates[outlookMessages.STATE_KEY] = self.outlookAsJaws.GetValue()
		if self.outlookReadOnOpen.GetValue() != self._shownOutlookReadOnOpen:
			updates[outlookMessages.READ_KEY] = self.outlookReadOnOpen.GetValue()
		if self.outlookStatusBar.GetValue() != self._shownOutlookStatusBar:
			updates[outlookStatusBar.STATE_KEY] = self.outlookStatusBar.GetValue()
		if self.quietListBounds.GetValue() != self._shownQuietListBounds:
			updates[listBounds.STATE_KEY] = self.quietListBounds.GetValue()
		if self.quickProfileSwitches.GetValue() != self._shownQuickProfileSwitches:
			updates[profileSwitches.STATE_KEY] = self.quickProfileSwitches.GetValue()
		if self.linksAsJaws.GetValue() != self._shownLinksAsJaws:
			updates[linkSpeech.STATE_KEY] = self.linksAsJaws.GetValue()
		if self.formFieldsAsJaws.GetValue() != self._shownFormFieldsAsJaws:
			updates[formFields.STATE_KEY] = self.formFieldsAsJaws.GetValue()
		if self.browserPagesAsJaws.GetValue() != self._shownBrowserPagesAsJaws:
			updates[browserPages.STATE_KEY] = self.browserPagesAsJaws.GetValue()
		if self.pageReadyForEveryPage.GetValue() != self._shownPageReadyForEveryPage:
			updates[pageReady.STATE_KEY] = self.pageReadyForEveryPage.GetValue()
		if self.webRegionsAsJaws.GetValue() != self._shownWebRegionsAsJaws:
			updates[webRegions.STATE_KEY] = self.webRegionsAsJaws.GetValue()
		if self.backForwardAsJaws.GetValue() != self._shownBackForwardAsJaws:
			updates[backForward.STATE_KEY] = self.backForwardAsJaws.GetValue()
		if self.keepSpeechHistory.GetValue() != self._shownKeepSpeechHistory:
			updates[speechHistory.STATE_KEY] = self.keepSpeechHistory.GetValue()
		if self.keepNotificationHistory.GetValue() != self._shownKeepNotificationHistory:
			updates[notificationHistory.STATE_KEY] = self.keepNotificationHistory.GetValue()
		if self.sayReady.GetValue() != self._shownSayReady:
			updates[startMessage.STATE_KEY] = self.sayReady.GetValue()
		if self.sayUnloading.GetValue() != self._shownSayUnloading:
			updates[exitMessage.STATE_KEY] = self.sayUnloading.GetValue()
		if self.sayScreenCurtainAtStart.GetValue() != self._shownSayScreenCurtainAtStart:
			updates[screenShade.STATE_KEY] = self.sayScreenCurtainAtStart.GetValue()
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
