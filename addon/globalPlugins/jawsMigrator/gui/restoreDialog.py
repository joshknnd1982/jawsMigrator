# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Restore NVDA's settings from one of the assistant's backups."""

from __future__ import annotations

import wx

from .. import backup, migrator, nvdaEnv
from .common import BORDER, TITLE, labeled, messageBox, openFile, postPopup, prePopup


class RestoreDialog(wx.Dialog):
	def __init__(self, parent):
		super().__init__(parent, title=f"{TITLE}: Restore NVDA settings", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.backups = backup.listBackups(nvdaEnv.addonDataDir())
		sizer = wx.BoxSizer(wx.VERTICAL)
		intro = wx.StaticText(
			self,
			label=(
				"Choose a backup to put back. NVDA's settings, input gestures, speech dictionaries, symbols, "
				"configuration profiles and ClassicSpeech settings return to how they were when it was made. "
				"Your settings from right now are backed up first, so a restore can be undone too."
			),
		)
		intro.Wrap(600)
		sizer.Add(intro)
		self.list = labeled(self, sizer, "&Backups, newest first:", wx.ListBox(self, choices=[info.label for info in self.backups], size=(600, 200)))
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
		if messageBox(
			f"Restore NVDA's settings from {info.label}? Your current settings are backed up first.",
			TITLE,
			wx.YES | wx.NO | wx.ICON_QUESTION,
			self,
		) != wx.YES:
			return
		try:
			message = migrator.restore(info)
		except Exception as error:
			messageBox(f"The backup could not be restored: {error}", TITLE, wx.OK | wx.ICON_ERROR, self)
			return
		messageBox(message + " Restart NVDA if anything still sounds different.", TITLE, wx.OK | wx.ICON_INFORMATION, self)
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
	import gui

	if not backup.listBackups(nvdaEnv.addonDataDir()):
		messageBox("There are no backups yet. The assistant makes one each time it migrates JAWS settings.", TITLE)
		return
	prePopup()
	try:
		dialog = RestoreDialog(gui.mainFrame)
		try:
			dialog.ShowModal()
		finally:
			dialog.Destroy()
	finally:
		postPopup()
