# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""The QuickSettings window, JAWS's Insert+V: the settings of the program you are in, in a tree, one at a time.

As JAWS's window has it: a Search box, a tree called Settings with a row for each setting, the control of the setting you
are on (a check box or a list) and what it does, and the buttons Apply, OK and Cancel. What it holds and saves is in
quickSettings.

Cancel, Escape and closing the window keep what you changed and ask nothing, as JAWS's do (1.51).

As in JAWS's tree, Space on a setting changes it without a Tab to its control: a check box is checked or not, a list goes to
the next choice (issue 40).
"""

from __future__ import annotations

import wx

from .. import debugLog, quickSettings
from .common import BORDER, TEXT_SIZE, labeled, mainFrame, postPopup, prePopup, readOnlyText, speak

#: The height, in lines, of the box that says what a setting does in NVDA.
EFFECT_SIZE = (TEXT_SIZE[0], 70)


class QuickSettingsDialog(wx.Dialog):
	def __init__(self, parent, session: quickSettings.Session, onSaved=None):
		super().__init__(parent, title=session.title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.session = session
		#: Called after settings were saved, with what was saved (the plugin applies the assistant's own settings then).
		self.onSaved = onSaved
		#: The setting the check box or the list shows.
		self.current = None
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.search = labeled(self, sizer, "&Search:", wx.TextCtrl)
		self.search.Bind(wx.EVT_TEXT, self._onSearch)
		self.tree = labeled(self, sizer, "S&ettings:", wx.TreeCtrl, style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_SINGLE, size=(TEXT_SIZE[0], 260), proportion=1)
		self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self._onSelect)
		self.tree.Bind(wx.EVT_KEY_DOWN, self._onTreeKey)
		self.check = wx.CheckBox(self, label="")
		self.check.Bind(wx.EVT_CHECKBOX, self._onChecked)
		sizer.Add(self.check, flag=wx.TOP, border=8)
		self.listLabel = wx.StaticText(self, label="")
		sizer.Add(self.listLabel, flag=wx.TOP, border=8)
		self.list = wx.Choice(self)
		self.list.Bind(wx.EVT_CHOICE, self._onListChoice)
		sizer.Add(self.list, flag=wx.EXPAND | wx.TOP, border=2)
		self.effectLabel = wx.StaticText(self, label="What this does in &NVDA:")
		sizer.Add(self.effectLabel, flag=wx.TOP, border=8)
		self.effect = readOnlyText(self, "", size=EFFECT_SIZE)
		sizer.Add(self.effect, flag=wx.EXPAND | wx.TOP, border=2)
		self._sizer = sizer
		buttons = wx.BoxSizer(wx.HORIZONTAL)
		self.apply = wx.Button(self, wx.ID_APPLY, "&Apply")
		self.apply.Bind(wx.EVT_BUTTON, self._onApply)
		self.ok = wx.Button(self, wx.ID_OK, "OK")
		self.ok.Bind(wx.EVT_BUTTON, self._onOk)
		self.ok.SetDefault()
		cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")
		# Cancel, Escape (the escape ID) and closing the window keep what you changed, as they do in JAWS (issue 40).
		self.Bind(wx.EVT_BUTTON, self._onCancel, id=wx.ID_CANCEL)
		self.Bind(wx.EVT_CLOSE, self._onCancel)
		for button in (self.apply, self.ok, cancel):
			buttons.Add(button, flag=wx.LEFT, border=6)
		sizer.Add(buttons, flag=wx.ALIGN_RIGHT | wx.TOP, border=10)
		outer = wx.BoxSizer(wx.VERTICAL)
		outer.Add(sizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=BORDER)
		self.SetSizerAndFit(outer)
		self.SetEscapeId(wx.ID_CANCEL)
		self.CentreOnScreen()
		self._fillTree("")
		self.tree.SetFocus()

	# -- the tree ---------------------------------------------------------------------------------------------------

	def _fillTree(self, query: str) -> None:
		"""The tree of categories and settings; with a search, only the settings whose name has it, in their categories."""
		words = query.strip().lower()
		self.tree.DeleteAllItems()
		root = self.tree.AddRoot("Settings")
		selected = None

		def matching(child):
			if isinstance(child, quickSettings.Category):
				return any(matching(inner) for inner in child.children)
			return words in child.name.lower()

		def add(parent, category):
			nonlocal selected
			node = self.tree.AppendItem(parent, category.name)
			self.tree.SetItemData(node, category)
			for child in category.children:
				if words and not matching(child):
					continue
				if isinstance(child, quickSettings.Category):
					add(node, child)
					continue
				row = self.tree.AppendItem(node, self.session.rowText(child))
				self.tree.SetItemData(row, child)
				if selected is None:
					selected = row
			self.tree.Expand(node)

		for category in self.session.categories:
			if not words or matching(category):
				add(root, category)
		if selected is None:
			first, _cookie = self.tree.GetFirstChild(root)
			selected = first if first.IsOk() else None
		if selected is not None:
			self.tree.SelectItem(selected)
		else:
			self._show(None)

	def _rowFor(self, item):
		"""The tree row of a setting, or None where a search left it out."""
		stack = [self.tree.GetRootItem()]
		while stack:
			node = stack.pop()
			child, cookie = self.tree.GetFirstChild(node)
			while child.IsOk():
				if self.tree.GetItemData(child) is item:
					return child
				stack.append(child)
				child, cookie = self.tree.GetNextChild(node, cookie)
		return None

	def _onSearch(self, event) -> None:
		if self:
			self._fillTree(self.search.GetValue())
		event.Skip()

	def _onSelect(self, event) -> None:
		if not self or not self.tree:
			# The window is going: its tree tells of the rows it drops.
			return
		data = self.tree.GetItemData(event.GetItem()) if event.GetItem().IsOk() else None
		self._show(data if isinstance(data, quickSettings.Item) else None, data if isinstance(data, quickSettings.Category) else None)
		event.Skip()

	# -- the control of the setting you are on ------------------------------------------------------------------------

	def _show(self, item, category=None) -> None:
		self.current = item
		self._sizer.Show(self.check, False)
		self._sizer.Show(self.listLabel, False)
		self._sizer.Show(self.list, False)
		if item is None:
			if category is not None:
				count = len(quickSettings.items((category,)))
				text = f"{category.name}: {count} setting{'' if count == 1 else 's'}. Arrow down to a setting, then press Space to change it, or Tab to its control."
			else:
				text = "No setting has that in its name."
			self.effect.SetValue(text)
		else:
			self._fillControl(item)
			if item.isCheckBox:
				self._sizer.Show(self.check, True)
			else:
				self._sizer.Show(self.listLabel, True)
				self._sizer.Show(self.list, True)
			self.effect.SetValue(self.session.effect(item))
		self.Layout()

	def _fillControl(self, item) -> None:
		"""Have the check box or the list say what is chosen for ``item`` now."""
		value = self.session.chosen.get(item.id)
		if item.isCheckBox:
			self.check.SetLabel(item.name)
			self.check.SetValue(value == "1")
		else:
			self.listLabel.SetLabel(f"{item.name}:")
			self.list.Set([choice.label for choice in item.choices])
			index = next((number for number, choice in enumerate(item.choices) if choice.value == value), wx.NOT_FOUND)
			self.list.SetSelection(index)

	def _onTreeKey(self, event) -> None:
		"""Space on a setting in the tree changes it, as in JAWS's tree, where it toggles a check box with no Tab to it
		first (issue 40): a check box is checked or not, and a setting with several choices goes to the next, from the
		last round to the first."""
		item = self.current
		if event.GetKeyCode() != wx.WXK_SPACE or event.HasAnyModifiers() or item is None:
			event.Skip()
			return
		if item.isCheckBox:
			value = "0" if self.session.chosen.get(item.id) == "1" else "1"
		else:
			values = [choice.value for choice in item.choices]
			chosen = self.session.chosen.get(item.id)
			value = values[(values.index(chosen) + 1) % len(values)] if chosen in values else values[0]
		self._chosen(value)
		self._fillControl(item)
		# The row's new text is what a screen reader would say as the row changes; say the new choice too, as the check
		# box does when you press Space on it.
		speak(self.session.valueText(item))

	def _chosen(self, value: str) -> None:
		item = self.current
		if item is None:
			return
		self.session.choose(item, value)
		row = self._rowFor(item)
		if row is not None:
			self.tree.SetItemText(row, self.session.rowText(item))
		self.effect.SetValue(self.session.effect(item))

	def _onChecked(self, event) -> None:
		self._chosen("1" if self.check.GetValue() else "0")
		event.Skip()

	def _onListChoice(self, event) -> None:
		index = self.list.GetSelection()
		if self.current is not None and index != wx.NOT_FOUND:
			self._chosen(self.current.choices[index].value)
		event.Skip()

	# -- saving ---------------------------------------------------------------------------------------------------------

	def _save(self) -> bool:
		"""Save what was chosen; False when it could not be."""
		if not self.session.changes():
			return True
		try:
			saved = self.session.save()
		except Exception:
			debugLog.error("could not save the QuickSettings choices")
			speak("The QuickSettings choices could not be saved. NVDA's log says why.")
			return False
		speak(quickSettings.confirmation(self.session.context, saved))
		if self.onSaved is not None:
			try:
				self.onSaved(saved)
			except Exception:
				debugLog.error("could not apply the assistant's settings after QuickSettings")
		return not saved.failed

	def _onApply(self, event) -> None:
		self._save()

	def _onOk(self, event) -> None:
		if self._save():
			self.EndModal(wx.ID_OK)

	def _onCancel(self, event) -> None:
		"""Cancel, Escape and closing the window save what you changed and close, with no question, as JAWS's window does.

		Watched in JAWS 2026 (27.6.18) in Notepad: after Space changed Typing Echo, Escape, the Cancel button and the
		window's Close each closed the window without asking anything, and each left the change in notepad.JCF
		(TypingEcho=2). JAWS has the text "Do you want to save them?" but showed none of it there. A save that fails is
		said, and the window closes all the same, so there is always a way out."""
		self._save()
		self.EndModal(wx.ID_CANCEL)


def show(session: quickSettings.Session, onSaved=None, parent=None) -> int:
	"""Open the window and wait for it to close, as NVDA opens its own settings dialogs."""
	prePopup()
	try:
		dialog = QuickSettingsDialog(parent or mainFrame(), session, onSaved)
		try:
			return dialog.ShowModal()
		finally:
			dialog.Destroy()
	finally:
		postPopup()
