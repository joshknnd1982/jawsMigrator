# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""JAWS Migration Assistant settings: choose exactly which JAWS items to import.

Opened from NVDA's Preferences menu. Every JAWS setting, speech and sound scheme,
voice profile and voice alias the assistant found is listed with a check box.
Select all and Select none work on the items shown, so a whole category can be
turned on or off at once. The choice is saved and used by every migration. The
dialog also checks for updates on GitHub and opens NVDA's Input Gestures dialog.
"""

from __future__ import annotations

import threading
import weakref

import wx

from .. import debugLog, jawsIndex, migrator, selection
from .common import BORDER, TITLE, checkListClass, enableWithLabel, messageBox, speak

EVERYTHING = "everything"


def _log():
	try:
		from logHandler import log

		return log
	except Exception:  # pragma: no cover
		import logging

		return logging.getLogger("jawsMigrator")


class ImportSettingsDialog(wx.Dialog):
	_instance = None

	@classmethod
	def current(cls):
		dialog = cls._instance() if cls._instance else None
		return dialog if dialog is not None and not getattr(dialog, "_closed", False) else None

	def __init__(self, parent, facts, plugin=None):
		super().__init__(parent, title=f"{TITLE} settings", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		ImportSettingsDialog._instance = weakref.ref(self)
		self.facts = facts
		self.plugin = plugin
		self.plan = None
		self.items: list[selection.ImportItem] = []
		self.shown: list[selection.ImportItem] = []
		self.selection = selection.load()
		self._dirty = False
		self._closed = False

		sizer = wx.BoxSizer(wx.VERTICAL)
		intro = wx.StaticText(
			self,
			label=(
				"Choose which JAWS settings, speech and sound schemes, voice profiles and voice aliases to import into NVDA. "
				"Your choice is saved and used every time you migrate. JAWS itself is never changed."
			),
		)
		intro.Wrap(640)
		sizer.Add(intro)
		self.status = wx.StaticText(self, label="Reading your JAWS settings. Please wait.")
		sizer.Add(self.status, flag=wx.TOP, border=6)

		# Each access key is used once: Alt+S saves, Alt+H goes to Show, Alt+I to the items, Alt+W imports.
		sizer.Add(wx.StaticText(self, label="S&how:"), flag=wx.TOP, border=8)
		self.categoryKeys = [EVERYTHING] + [key for key, _label in selection.CATEGORIES]
		self.category = wx.Choice(self, choices=["Everything"] + [label for _key, label in selection.CATEGORIES])
		self.category.SetSelection(0)
		sizer.Add(self.category, flag=wx.EXPAND | wx.TOP, border=2)

		sizer.Add(wx.StaticText(self, label="&Items to import:"), flag=wx.TOP, border=8)
		self.list = checkListClass()(self, size=(640, 300))
		sizer.Add(self.list, proportion=1, flag=wx.EXPAND | wx.TOP, border=2)

		selectRow = wx.BoxSizer(wx.HORIZONTAL)
		self.selectAllButton = wx.Button(self, label="Select &all")
		self.selectNoneButton = wx.Button(self, label="Select &none")
		selectRow.Add(self.selectAllButton, flag=wx.RIGHT, border=6)
		selectRow.Add(self.selectNoneButton)
		sizer.Add(selectRow, flag=wx.TOP, border=6)

		actionRow = wx.BoxSizer(wx.HORIZONTAL)
		self.importButton = wx.Button(self, label="Import the selected items no&w...")
		self.updatesButton = wx.Button(self, label="Check for &updates")
		self.gesturesButton = wx.Button(self, label="Open NVDA's Input &Gestures dialog")
		for button in (self.importButton, self.updatesButton, self.gesturesButton):
			actionRow.Add(button, flag=wx.RIGHT, border=6)
		sizer.Add(actionRow, flag=wx.TOP, border=10)

		closeRow = wx.BoxSizer(wx.HORIZONTAL)
		self.saveButton = wx.Button(self, wx.ID_OK, label="&Save and close")
		self.closeButton = wx.Button(self, wx.ID_CANCEL, label="Close without saving")
		closeRow.Add(self.saveButton, flag=wx.RIGHT, border=6)
		closeRow.Add(self.closeButton)
		sizer.Add(closeRow, flag=wx.TOP | wx.ALIGN_RIGHT, border=10)

		outer = wx.BoxSizer(wx.VERTICAL)
		outer.Add(sizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=BORDER)
		self.SetSizerAndFit(outer)
		self.SetMinSize((700, 560))
		self.CentreOnScreen()

		self.category.Bind(wx.EVT_CHOICE, lambda event: self._fill())
		self.list.Bind(wx.EVT_CHECKLISTBOX, self._onCheck)
		self.selectAllButton.Bind(wx.EVT_BUTTON, lambda event: self._selectShown(True))
		self.selectNoneButton.Bind(wx.EVT_BUTTON, lambda event: self._selectShown(False))
		self.importButton.Bind(wx.EVT_BUTTON, self._onImport)
		self.updatesButton.Bind(wx.EVT_BUTTON, self._onUpdates)
		self.gesturesButton.Bind(wx.EVT_BUTTON, self._onGestures)
		self.saveButton.Bind(wx.EVT_BUTTON, self._onSave)
		self.closeButton.Bind(wx.EVT_BUTTON, lambda event: self._close())
		self.Bind(wx.EVT_CLOSE, lambda event: self._close())
		self.Bind(wx.EVT_CHAR_HOOK, self._onCharHook)
		self.SetEscapeId(wx.ID_CANCEL)
		self._enableLists(False)
		self.updatesButton.SetFocus()
		self._startLoading()

	# -- loading ---------------------------------------------------------------------------

	def _enableLists(self, enabled: bool):
		for control in (self.category, self.list):
			enableWithLabel(control, enabled)
		for control in (self.selectAllButton, self.selectNoneButton, self.importButton, self.saveButton):
			control.Enable(enabled)

	def _startLoading(self):
		facts = self.facts
		candidates = facts.jawsWithSettings or facts.jaws
		if not candidates:
			self.status.SetLabel("No JAWS settings were found on this computer.")
			return
		jaws = candidates[0]
		language = jaws.primaryLanguage or (jaws.settingsLanguages[0] if jaws.settingsLanguages else "enu")
		options = migrator.MigrationOptions(jaws=jaws, language=language)

		def work():
			try:
				index = jawsIndex.buildIndex(jaws, language, facts.leasey)
				outcome = migrator.buildPlan(options, index, facts, inNvda=True)
			except Exception as error:
				debugLog.error("could not read the JAWS settings")
				outcome = error
			wx.CallAfter(self._loaded, outcome)

		threading.Thread(target=work, name="jawsMigratorSelection", daemon=True).start()

	def _loaded(self, outcome):
		if self._closed:
			return
		if isinstance(outcome, Exception):
			self.status.SetLabel(f"Your JAWS settings could not be read: {outcome}")
			speak("Your JAWS settings could not be read.")
			return
		self.plan = outcome
		self.items = selection.buildItems(outcome)
		self._enableLists(True)
		self._fill()
		self._updateStatus()
		speak(f"{self.plan.index.jaws.displayName}. {self.status.GetLabel()}")
		# Move to the list unless the user already went to another button while waiting.
		if wx.Window.FindFocus() in (None, self, self.updatesButton):
			self.list.SetFocus()

	# -- the list -----------------------------------------------------------------------------

	def _currentCategory(self) -> str:
		index = self.category.GetSelection()
		return self.categoryKeys[index] if 0 <= index < len(self.categoryKeys) else EVERYTHING

	def _label(self, item: selection.ImportItem, category: str) -> str:
		text = item.label
		if category == EVERYTHING:
			text = f"{selection.CATEGORY_LABELS[item.category]}: {text}"
		if not item.available:
			text += f" (not available: {item.reason})"
		return text

	def _fill(self):
		category = self._currentCategory()
		self.shown = [item for item in self.items if category == EVERYTHING or item.category == category]
		self.list.SetItems([self._label(item, category) for item in self.shown])
		for index, item in enumerate(self.shown):
			self.list.Check(index, self.selection.isSelected(item))
		if self.shown:
			self.list.SetSelection(0)
		self._updateStatus()

	def _updateStatus(self):
		if not self.items:
			return
		text = selection.summary(self.items, self.selection) + "."
		category = self._currentCategory()
		if category != EVERYTHING:
			shownChosen = sum(1 for item in self.shown if self.selection.isSelected(item))
			shownUsable = sum(1 for item in self.shown if item.available)
			text = f"{selection.CATEGORY_LABELS[category]}: {shownChosen} of {shownUsable} selected. In all, {text}"
		self.status.SetLabel(text)

	def _onCheck(self, event):
		# NVDA's check list box tells NVDA about the change in its own handler of this event.
		event.Skip()
		index = event.GetInt()
		if not 0 <= index < len(self.shown):
			return
		item = self.shown[index]
		if not item.available:
			self.list.Check(index, False)
			speak(f"Not available: {item.reason}")
			return
		self.selection.set(item, self.list.IsChecked(index))
		self._dirty = True
		self._updateStatus()

	def _selectShown(self, selected: bool):
		count = 0
		for index, item in enumerate(self.shown):
			if not item.available:
				continue
			self.selection.set(item, selected)
			self.list.Check(index, selected)
			count += 1
		self._dirty = True
		self._updateStatus()
		speak(f"{count} items {'selected' if selected else 'cleared'}. {self.status.GetLabel()}")

	# -- buttons -----------------------------------------------------------------------------

	def _save(self):
		if self.items:
			self.selection.customized = True
			selection.save(self.selection)
			self._dirty = False

	def _onSave(self, event):
		self._save()
		speak("Saved")
		self._close(force=True)

	def _onImport(self, event):
		if not self.items or not any(self.selection.isSelected(item) for item in self.items):
			messageBox("Select at least one item to import.", TITLE, wx.OK | wx.ICON_INFORMATION, self)
			return
		self._save()
		plugin = self.plugin
		self._close(force=True)
		if plugin is not None:
			wx.CallAfter(plugin.openAssistant)

	def _onUpdates(self, event):
		if self.plugin is not None:
			self.plugin.checkForUpdates()

	def _onGestures(self, event):
		if self.plugin is not None:
			self.plugin.openInputGestures()

	def _onCharHook(self, event):
		if event.GetKeyCode() == wx.WXK_ESCAPE:
			self._close()
			return
		event.Skip()

	def _close(self, force: bool = False):
		if self._closed:
			return
		if self._dirty and not force:
			answer = messageBox("Save your choice of JAWS items before closing?", TITLE, wx.YES | wx.NO | wx.CANCEL | wx.ICON_QUESTION, self)
			if answer == wx.CANCEL:
				return
			if answer == wx.YES:
				self._save()
		self._closed = True
		self.Destroy()


def showImportSettings(facts, plugin=None):
	"""Open the dialog, or bring the open one forward."""
	import gui

	existing = ImportSettingsDialog.current()
	if existing is not None:
		existing.Raise()
		existing.SetFocus()
		return existing
	gui.mainFrame.prePopup()
	try:
		dialog = ImportSettingsDialog(gui.mainFrame, facts, plugin)
		dialog.Show()
	finally:
		gui.mainFrame.postPopup()
	return dialog
