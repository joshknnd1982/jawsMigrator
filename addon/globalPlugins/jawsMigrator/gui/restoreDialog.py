# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Restore NVDA's settings from one of the assistant's backups."""

from __future__ import annotations

import wx

from .. import backup, migrator, nvdaEnv, restorePreview
from .common import BORDER, TITLE, labeled, messageBox, openFile, postPopup, prePopup, speak

#: The restore dialog while it is open, so asking for it again brings it forward instead of opening a second one.
_openDialog = None


class RestoreDialog(wx.Dialog):
	def __init__(self, parent):
		super().__init__(parent, title=f"{TITLE}: Restore NVDA settings", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.backups = backup.listBackups(nvdaEnv.addonDataDir())
		sizer = wx.BoxSizer(wx.VERTICAL)
		intro = wx.StaticText(
			self,
			label=(
				"Choose a backup to put back. NVDA's settings, input gestures, speech dictionaries, symbols, "
				"configuration profiles, ClassicSpeech settings, add-ons and the add-ons' settings return to how they "
				"were when it was made. With a backup from before a migration, NVDA behaves as it did then, for example "
				"saying \"clickable\" on web pages again; Restore lists what you will notice before it changes anything. "
				"Your settings and add-ons from right now are backed up first, so a restore can be undone too."
			),
		)
		intro.Wrap(600)
		sizer.Add(intro)
		self.list = labeled(self, sizer, "&Backups, newest first:", wx.ListBox, choices=[info.label for info in self.backups], size=(600, 200))
		if self.backups:
			self.list.SetSelection(0)
		buttons = wx.BoxSizer(wx.HORIZONTAL)
		self.restoreButton = wx.Button(self, label="&Restore")
		self.openButton = wx.Button(self, label="&Open backup folder")
		self.deleteButton = wx.Button(self, label="&Delete backup")
		closeButton = wx.Button(self, wx.ID_CLOSE, label="&Close")
		for button in (self.restoreButton, self.openButton, self.deleteButton, closeButton):
			buttons.Add(button, flag=wx.RIGHT, border=6)
		sizer.Add(buttons, flag=wx.TOP, border=8)
		self.restoreButton.Bind(wx.EVT_BUTTON, self.onRestore)
		self.openButton.Bind(wx.EVT_BUTTON, self.onOpen)
		self.deleteButton.Bind(wx.EVT_BUTTON, self.onDelete)
		closeButton.Bind(wx.EVT_BUTTON, lambda event: self.EndModal(wx.ID_CLOSE))
		self.SetEscapeId(wx.ID_CLOSE)
		outer = wx.BoxSizer(wx.VERTICAL)
		outer.Add(sizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=BORDER)
		self.SetSizerAndFit(outer)
		self.CentreOnScreen()
		self._update()
		self.list.SetFocus()

	def _selected(self):
		index = self.list.GetSelection()
		return self.backups[index] if 0 <= index < len(self.backups) else None

	def _update(self):
		hasBackup = self._selected() is not None
		for button in (self.restoreButton, self.openButton, self.deleteButton):
			button.Enable(hasBackup)

	def onRestore(self, event):
		info = self._selected()
		if info is None:
			return
		problems = backup.verifyBackup(info)
		if problems:
			messageBox("This backup is damaged and cannot be restored:\n" + "\n".join(problems[:10]), TITLE, wx.OK | wx.ICON_ERROR, self)
			return
		if info.version < 2:
			details = "\n\nThis backup was made by version 1.0 of the assistant and holds NVDA's settings only; add-ons are not changed."
		else:
			try:
				from .. import nvdaApply

				actions = backup.planAddonRestore(info, nvdaApply.addonManager().installed())
			except Exception:
				actions = []
			shown = [action.description for action in actions[:12]]
			if len(actions) > 12:
				shown.append(f"and {len(actions) - 12} more")
			details = ("\n\nAdd-ons, finished when NVDA restarts:\n" + "\n".join(shown)) if shown else "\n\nYour add-ons are already as they were in this backup."
		# NVDA's own behaviour comes back with its settings: say what will sound different, and where it is set.
		noticed = restorePreview.describe(info.path)
		if noticed:
			details = "\n\nYou will notice:\n" + "\n".join(noticed[:8]) + details
		if messageBox(
			f"Restore NVDA's settings, add-ons and add-on settings from {info.label}? Your current settings and add-ons are backed up first.{details}",
			TITLE,
			wx.YES | wx.NO | wx.ICON_QUESTION,
			self,
		) != wx.YES:
			return
		try:
			outcome = migrator.restore(info)
		except Exception as error:
			messageBox(f"The backup could not be restored: {error}", TITLE, wx.OK | wx.ICON_ERROR, self)
			return
		if outcome.restartNeeded:
			if messageBox(outcome.message + "\n\nRestart NVDA now to finish putting back the add-ons?", TITLE, wx.YES | wx.NO | wx.ICON_QUESTION, self) == wx.YES:
				self.EndModal(wx.ID_OK)
				try:
					import core

					wx.CallLater(500, core.restart)
				except Exception:
					pass
				return
		else:
			messageBox(outcome.message + " Restart NVDA if anything still sounds different.", TITLE, wx.OK | wx.ICON_INFORMATION, self)
		self.EndModal(wx.ID_OK)

	def onOpen(self, event):
		info = self._selected()
		if info is not None:
			openFile(info.path)

	def onDelete(self, event):
		info = self._selected()
		if info is None:
			return
		if messageBox(f"Delete the backup from {info.label}? It cannot be restored afterwards.", TITLE, wx.YES | wx.NO | wx.ICON_WARNING, self) != wx.YES:
			return
		backup.deleteBackup(info)
		index = self.list.GetSelection()
		del self.backups[index]
		self.list.Delete(index)
		if self.backups:
			self.list.SetSelection(min(index, len(self.backups) - 1))
		self._update()


def showRestoreDialog():
	global _openDialog
	import gui

	if _openDialog:
		# Asked for again while it is open, for example with NVDA+Shift+J then B.
		_openDialog.Raise()
		speak("The restore dialog is already open.")
		return
	if not backup.listBackups(nvdaEnv.addonDataDir()):
		messageBox("There are no backups yet. The assistant makes one each time it migrates JAWS settings.", TITLE)
		return
	prePopup()
	try:
		dialog = RestoreDialog(gui.mainFrame)
		_openDialog = dialog
		try:
			dialog.ShowModal()
		finally:
			_openDialog = None
			dialog.Destroy()
	finally:
		postPopup()
