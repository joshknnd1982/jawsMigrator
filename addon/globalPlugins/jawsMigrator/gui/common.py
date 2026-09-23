# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Small helpers shared by the assistant's dialogs."""

from __future__ import annotations

import os

import wx

TITLE = "JAWS Migration Assistant"
BORDER = 10
TEXT_SIZE = (640, 280)


def mainFrame():
	try:
		import gui

		return gui.mainFrame
	except Exception:
		return None


def prePopup():
	frame = mainFrame()
	if frame is not None and hasattr(frame, "prePopup"):
		frame.prePopup()


def postPopup():
	frame = mainFrame()
	if frame is not None and hasattr(frame, "postPopup"):
		frame.postPopup()


def messageBox(message: str, caption: str = TITLE, style: int = wx.OK | wx.ICON_INFORMATION, parent=None) -> int:
	"""A message box NVDA reads in full, returning the button chosen (wx.OK, wx.YES, wx.NO...)."""
	try:
		import gui

		return gui.messageBox(message, caption, style, parent or gui.mainFrame)
	except Exception:
		prePopup()
		try:
			return wx.MessageBox(message, caption, style, parent)
		finally:
			postPopup()


def labeled(parent, sizer, label: str, control):
	"""Add a label followed by its control; the label names the control for screen readers."""
	text = wx.StaticText(parent, label=label)
	sizer.Add(text, flag=wx.TOP, border=6)
	sizer.Add(control, flag=wx.EXPAND | wx.TOP, border=2)
	return control


def readOnlyText(parent, value: str = "", size=TEXT_SIZE):
	"""A read-only multiline box that NVDA reads line by line, word by word or character by character."""
	return wx.TextCtrl(parent, value=value, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP | wx.HSCROLL, size=size)


def openFile(path: str) -> bool:
	try:
		os.startfile(path)  # noqa: S606 - opens the report in the user's browser or editor
		return True
	except OSError:
		return False


def speak(message: str) -> None:
	try:
		import ui

		ui.message(message)
	except Exception:
		pass


class TextViewer(wx.Dialog):
	"""Shows long text in a read-only box with a Close button."""

	def __init__(self, parent, title: str, text: str):
		super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.text = labeled(self, sizer, "&Text:", readOnlyText(self, text, size=(700, 420)))
		close = wx.Button(self, wx.ID_CLOSE, "&Close")
		close.Bind(wx.EVT_BUTTON, lambda event: self.EndModal(wx.ID_CLOSE))
		sizer.Add(close, flag=wx.ALIGN_RIGHT | wx.TOP, border=8)
		outer = wx.BoxSizer(wx.VERTICAL)
		outer.Add(sizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=BORDER)
		self.SetSizerAndFit(outer)
		self.SetEscapeId(wx.ID_CLOSE)
		self.CentreOnScreen()
		self.text.SetFocus()
		self.text.SetInsertionPoint(0)


def showText(parent, title: str, text: str) -> None:
	prePopup()
	try:
		dialog = TextViewer(parent or mainFrame(), title, text)
		try:
			dialog.ShowModal()
		finally:
			dialog.Destroy()
	finally:
		postPopup()
