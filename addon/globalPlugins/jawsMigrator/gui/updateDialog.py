# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.
# The same dialog ClassicSpeech (https://github.com/joshknnd1982/classicspeech-nvda, GPL 2) uses for its updates.

"""The dialog that offers an update, with its release notes to read.

A message box speaks its whole text once and there is nothing to move through
afterwards, so the "What's new" part of a release would go by in one breath.
Here the notes are a read-only multiline box: NVDA treats it as text, so it can
be read line by line, word by word or character by character, reviewed, selected
and copied. Focus starts in it, and Tab reaches the buttons.
"""

from __future__ import annotations

import wx

from .common import BORDER, postPopup, prePopup

NOTES_SIZE = (620, 260)


class UpdateOfferDialog(wx.Dialog):
	def __init__(self, parent, title, summary, notes, question="", installLabel="", closeLabel=""):
		super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		sizer = wx.BoxSizer(wx.VERTICAL)
		if summary:
			sizer.Add(self._paragraph(summary), flag=wx.BOTTOM, border=6)
		sizer.Add(wx.StaticText(self, label="&What's new:"))
		self.notes = wx.TextCtrl(self, value=notes or "", style=wx.TE_MULTILINE | wx.TE_READONLY, size=NOTES_SIZE)
		sizer.Add(self.notes, proportion=1, flag=wx.EXPAND | wx.TOP, border=2)
		if question:
			sizer.Add(self._paragraph(question), flag=wx.TOP, border=6)
		buttons = wx.BoxSizer(wx.HORIZONTAL)
		self.installButton = None
		if installLabel:
			self.installButton = wx.Button(self, id=wx.ID_YES, label=installLabel)
			buttons.Add(self.installButton, flag=wx.RIGHT, border=8)
			self.installButton.Bind(wx.EVT_BUTTON, lambda event: self.EndModal(wx.ID_YES))
			self.installButton.SetDefault()
		self.closeButton = wx.Button(self, id=wx.ID_CANCEL, label=closeLabel or "&Close")
		self.closeButton.Bind(wx.EVT_BUTTON, lambda event: self.EndModal(wx.ID_CANCEL))
		buttons.Add(self.closeButton)
		sizer.Add(buttons, flag=wx.TOP | wx.ALIGN_RIGHT, border=8)
		outer = wx.BoxSizer(wx.VERTICAL)
		outer.Add(sizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=BORDER)
		self.SetSizerAndFit(outer)
		self.CentreOnScreen()
		self.Bind(wx.EVT_CHAR_HOOK, self._onCharHook)
		self.notes.SetFocus()
		self.notes.SetInsertionPoint(0)

	def _paragraph(self, text):
		label = wx.StaticText(self, label=text)
		try:
			label.Wrap(NOTES_SIZE[0])
		except Exception:
			pass
		return label

	def _onCharHook(self, event):
		if event.GetKeyCode() == wx.WXK_ESCAPE:
			self.EndModal(wx.ID_CANCEL)
			return
		event.Skip()


def showUpdateOffer(title, summary, notes, question="", installLabel="", closeLabel=""):
	"""Show the dialog and return the button chosen. Runs from wx's event loop, never NVDA's core queue."""
	import gui

	parent = gui.mainFrame
	prePopup()
	try:
		dialog = UpdateOfferDialog(parent, title, summary, notes, question=question, installLabel=installLabel, closeLabel=closeLabel)
		try:
			return dialog.ShowModal()
		finally:
			dialog.Destroy()
	finally:
		postPopup()
