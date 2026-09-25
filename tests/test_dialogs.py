# Tests for the assistant's dialogs, outside NVDA, with stand-ins for NVDA's modules:
# - every control that needs a label has it just before it, so Windows and NVDA name the control after
#   it and the label's access key reaches it (and, where comtypes is available, NVDA's name is checked);
# - no two controls of a dialog, or of a wizard step with its Back and Next buttons, share an access key;
# - what was fixed in the dialogs stays fixed.
# Tests that need a migration plan read this computer's JAWS settings (read only) and are skipped where
# there are none. The assistant's state and logs go to a temporary folder, never NVDA's settings folder.
# Run: python -m unittest tests.test_dialogs   (or: python -m unittest discover -s tests -p "test_*.py")

import importlib.util
import os
import re
import shutil
import sys
import tempfile
import time
import types
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import wx  # noqa: E402

import nvdaStubs  # noqa: E402

_saved = {}
_app = None
_frame = None
_configDir = None

#: Controls that get their name from the label just before them; buttons, check boxes and radio buttons name themselves.
LABELED = (wx.TextCtrl, wx.Choice, wx.ComboBox, wx.ListBox)


# -- stand-ins for NVDA's Settings dialog, as far as the assistant's panel uses it -------------------------


class _ButtonHelper:
	def __init__(self, orientation):
		self.sizer = wx.BoxSizer(orientation)

	def addButton(self, parent, **kwargs):
		button = wx.Button(parent, **kwargs)
		self.sizer.Add(button)
		return button


class _BoxSizerHelper:
	def __init__(self, parent, sizer=None, orientation=wx.VERTICAL):
		self.parent = parent
		self.sizer = sizer if sizer is not None else wx.BoxSizer(orientation)

	def addItem(self, item, **kwargs):
		self.sizer.Add(item.sizer if isinstance(item, _ButtonHelper) else item)
		return item

	def addLabeledControl(self, labelText, wxCtrlClass, **kwargs):
		# As NVDA's LabeledControlHelper: the label first, then the control.
		self.sizer.Add(wx.StaticText(self.parent, label=labelText))
		control = wxCtrlClass(self.parent, **kwargs)
		self.sizer.Add(control)
		return control


class _SettingsPanel(wx.Panel):
	def __init__(self, parent):
		super().__init__(parent)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.makeSettings(sizer)
		self.SetSizer(sizer)


class _SettingsDialog(wx.Dialog):
	"""NVDA's Settings dialog: OK saves every panel and closes (hidden at once, destroyed later), unless a setting is not valid."""

	valid = True

	def __init__(self, parent):
		super().__init__(parent, title="NVDA Settings")
		from jawsMigrator.gui import settingsPanel

		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(wx.StaticText(self, label="&Categories:"))
		self.categories = wx.ListBox(self, choices=["General", "JAWS Migration Assistant"])
		sizer.Add(self.categories)
		self.panel = settingsPanel.JawsMigratorSettingsPanel(self)
		sizer.Add(self.panel)
		sizer.Add(self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL | wx.APPLY))
		self.SetSizerAndFit(sizer)
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)

	def onOk(self, event):
		if not self.valid:
			return
		self.panel.onSave()
		self.DestroyLater()


def setUpModule():
	global _app, _frame, _configDir
	_app = wx.App()
	_frame = wx.Frame(None)
	_configDir = tempfile.mkdtemp(prefix="jawsMigrator-dialogs-")
	for name in ("globalVars", "gui.guiHelper", "gui.settingsDialogs"):
		_saved[name] = sys.modules.get(name)
	gui = sys.modules.get("gui")
	_saved["gui"] = {name: getattr(gui, name) for name in ("mainFrame", "messageBox") if gui is not None and hasattr(gui, name)}
	nvdaStubs.install(_frame)
	globalVars = types.ModuleType("globalVars")
	globalVars.appDir = ""
	globalVars.appArgs = types.SimpleNamespace(secure=False, configPath=_configDir)
	sys.modules["globalVars"] = globalVars
	guiHelper = types.ModuleType("gui.guiHelper")
	guiHelper.BoxSizerHelper, guiHelper.ButtonHelper = _BoxSizerHelper, _ButtonHelper
	settingsDialogs = types.ModuleType("gui.settingsDialogs")
	settingsDialogs.SettingsPanel, settingsDialogs.SettingsDialog = _SettingsPanel, _SettingsDialog
	gui = sys.modules["gui"]
	gui.guiHelper, gui.settingsDialogs = guiHelper, settingsDialogs
	sys.modules["gui.guiHelper"], sys.modules["gui.settingsDialogs"] = guiHelper, settingsDialogs
	from jawsMigrator import nvdaEnv, state

	assert os.path.normcase(nvdaEnv.configDir()) == os.path.normcase(_configDir), "the tests must use a temporary settings folder"
	state.forget()


def tearDownModule():
	from jawsMigrator import state

	state.forget()
	for name in ("globalVars", "gui.guiHelper", "gui.settingsDialogs"):
		if _saved.get(name) is None:
			sys.modules.pop(name, None)
		else:
			sys.modules[name] = _saved[name]
	gui = sys.modules["gui"]
	for name in ("guiHelper", "settingsDialogs"):
		if hasattr(gui, name):
			delattr(gui, name)
	for name, value in _saved["gui"].items():
		setattr(gui, name, value)
	_frame.Destroy()
	pump(0.05)
	shutil.rmtree(_configDir, ignore_errors=True)


# -- helpers ----------------------------------------------------------------------------------------------------


def pump(seconds=0.1):
	end = time.time() + seconds
	while time.time() < end:
		wx.Yield()
		time.sleep(0.01)


def descendants(window):
	for child in window.GetChildren():
		yield child
		yield from descendants(child)


def accessKey(label: str):
	match = re.search("&(.)", label.replace("&&", ""))
	return match.group(1).lower() if match else None


def labelProblems(window) -> list:
	"""Controls that need a label and don't have one with an access key just before them."""
	problems = []
	for control in descendants(window):
		if isinstance(control, LABELED):
			label = control.GetPrevSibling()
			if not isinstance(label, wx.StaticText) or not accessKey(label.GetLabel()):
				problems.append(f"{type(control).__name__} after {label.GetLabel() if label is not None else None!r}")
	return problems


def accessKeys(window) -> list:
	"""``(key, label)`` for every access key in ``window``."""
	keys = []
	for control in descendants(window):
		if isinstance(control, (wx.StaticText, wx.Button, wx.CheckBox, wx.RadioBox, wx.RadioButton)):
			key = accessKey(control.GetLabel())
			if key:
				keys.append((key, control.GetLabel()))
	return keys


def duplicates(keys) -> dict:
	byKey = {}
	for key, label in keys:
		byKey.setdefault(key, []).append(label)
	return {key: labels for key, labels in byKey.items() if len(labels) > 1}


def oleaccNames(window) -> dict:
	"""{label: the name Windows gives the control after it} for the shown labeled controls in ``window``."""
	import ctypes

	from comtypes import BSTR, COMMETHOD, GUID, HRESULT, dispid
	from comtypes.automation import IDispatch, VARIANT

	class IAccessible(IDispatch):
		_iid_ = GUID("{618736E0-3C3D-11CF-810C-00AA00389B71}")
		_methods_ = [
			COMMETHOD([dispid(-5000), "propget"], HRESULT, "accParent", (["out", "retval"], ctypes.POINTER(ctypes.POINTER(IDispatch)), "p")),
			COMMETHOD([dispid(-5001), "propget"], HRESULT, "accChildCount", (["out", "retval"], ctypes.POINTER(ctypes.c_long), "p")),
			COMMETHOD([dispid(-5002), "propget"], HRESULT, "accChild", (["in"], VARIANT, "c"), (["out", "retval"], ctypes.POINTER(ctypes.POINTER(IDispatch)), "p")),
			COMMETHOD([dispid(-5003), "propget"], HRESULT, "accName", (["in", "optional"], VARIANT, "c"), (["out", "retval"], ctypes.POINTER(BSTR), "p")),
		]

	names = {}
	for control in descendants(window):
		if isinstance(control, LABELED) and control.IsShownOnScreen():
			pointer = ctypes.POINTER(IAccessible)()
			ctypes.oledll.oleacc.AccessibleObjectFromWindow(ctypes.c_void_p(control.GetHandle()), ctypes.c_long(-4), ctypes.byref(IAccessible._iid_), ctypes.byref(pointer))
			names[control.GetPrevSibling().GetLabelText()] = pointer.accName(0)
	return names


def comtypesAvailable() -> bool:
	return sys.platform == "win32" and importlib.util.find_spec("comtypes") is not None


def emptyFacts():
	from jawsMigrator import systemCheck

	return systemCheck.SystemFacts()


def nextLabel(wizard, page) -> str:
	"""The Next button's label on ``page``, as MigrationWizard._show sets it."""
	return "&Migrate" if page is wizard.summaryPage else "&Close" if page is wizard.donePage else "&Next >"


def stepKeys(wizard, page) -> list:
	keys = accessKeys(page) + [("b", "< &Back"), (accessKey(nextLabel(wizard, page)), nextLabel(wizard, page))]
	return keys


# -- labels and access keys -------------------------------------------------------------------------------------


class LabelAndAccessKeyTests(unittest.TestCase):
	def test_everyWizardStepLabelsItsControls(self):
		from jawsMigrator.gui import wizard

		dialog = wizard.MigrationWizard(_frame, emptyFacts())
		try:
			for page in dialog.pages:
				with self.subTest(step=page.title):
					self.assertEqual(labelProblems(page), [])
					self.assertEqual(duplicates(stepKeys(dialog, page)), {})
		finally:
			dialog.Destroy()

	def test_dialogsLabelTheirControls(self):
		from jawsMigrator import backup
		from jawsMigrator.gui import common, importDialog, restoreDialog, updateDialog

		original = backup.listBackups
		backup.listBackups = lambda folder: [types.SimpleNamespace(label=f"2026-09-2{i}, before migrating", path=_configDir, version=2) for i in range(2)]
		dialogs = []
		try:
			dialogs.append(common.TextViewer(_frame, "JAWS settings index", "one\ntwo"))
			dialogs.append(restoreDialog.RestoreDialog(_frame))
			dialogs.append(updateDialog.UpdateOfferDialog(_frame, "Update", "1.3 is available.", "notes", question="Install it?", installLabel="&Download and install", closeLabel="&Not now"))
			dialogs.append(importDialog.ImportSettingsDialog(_frame, emptyFacts()))
			for dialog in dialogs:
				dialog.Show()
			pump(0.2)
			for dialog in dialogs:
				with self.subTest(dialog=type(dialog).__name__):
					self.assertEqual(labelProblems(dialog), [])
					self.assertEqual(duplicates(accessKeys(dialog)), {})
					if comtypesAvailable():
						for label, name in oleaccNames(dialog).items():
							self.assertEqual(name, label, "Windows names the control after its label")
		finally:
			backup.listBackups = original
			for dialog in dialogs:
				if isinstance(dialog, importDialog.ImportSettingsDialog):
					dialog._closed = True
				dialog.Destroy()

	def test_settingsPanelLeavesNvdasOwnAccessKeys(self):
		from jawsMigrator import state

		state.update({"sleepApps": ["winword"]})
		dialog = _SettingsDialog(_frame)
		try:
			self.assertEqual(labelProblems(dialog.panel), [])
			# NVDA's Settings dialog has &Categories and &Apply.
			self.assertEqual(duplicates(accessKeys(dialog.panel) + [("c", "&Categories:"), ("a", "&Apply")]), {})
		finally:
			dialog.Destroy()

	def test_disabledControlsDisableTheirLabels(self):
		from jawsMigrator.gui import wizard

		dialog = wizard.MigrationWizard(_frame, emptyFacts())
		try:
			name = dialog.targetPage.name
			self.assertFalse(name.IsEnabled())
			self.assertFalse(name.GetPrevSibling().IsEnabled(), "a disabled label's access key does nothing, instead of jumping past the field")
		finally:
			dialog.Destroy()


# -- the wizard, without a plan -------------------------------------------------------------------------------


class WizardTests(unittest.TestCase):
	def setUp(self):
		from jawsMigrator.gui import wizard

		self.wizard = wizard.MigrationWizard(_frame, emptyFacts())

	def tearDown(self):
		self.wizard.Destroy()
		pump(0.05)

	def test_targetPutsTheSettingsInNvdasNormalConfigurationByDefault(self):
		from jawsMigrator import migrator

		page = self.wizard.targetPage
		self.assertEqual(page.target, migrator.TARGET_NORMAL)
		self.assertIn("normal configuration", page.radio.GetStringSelection())
		self.assertTrue(page.radio.GetStringSelection().endswith("(recommended)"))
		self.assertNotIn("recommended", page.radio.GetString(1))
		note = page.intro()
		for words in ("only one profile turned on by hand", "Custom Browse Mode", "go into it", "backed up first"):
			self.assertIn(words, note)
		self.assertFalse(any(control.IsEnabled() for control in (page.name, page.atStartup, page.now)))
		options = types.SimpleNamespace()
		page.collect(options)
		self.assertEqual(options.target, migrator.TARGET_NORMAL)
		page.radio.SetSelection(1)
		page._update()
		self.assertTrue(all(control.IsEnabled() for control in (page.name, page.name.GetPrevSibling(), page.atStartup, page.now)))
		page.collect(options)
		self.assertEqual(options.target, migrator.TARGET_PROFILE)

	def test_selectAllChecksOnlyItemsThatCanBeMigrated(self):
		from jawsMigrator.gui import wizard

		class ListPage(wizard.Page):
			title = "List"

			def build(self, parent):
				self.list = self.labeled("&Items:", wx.CheckListBox, choices=["one", "cannot", "two"])
				self.buttons = self.selectButtons(self.list, lambda index: index != 1)

		page = ListPage(self.wizard, self.wizard.book)
		page.list.Check(1, True)
		selectAll, selectNone = page.buttons
		selectAll.ProcessEvent(wx.CommandEvent(wx.wxEVT_BUTTON, selectAll.GetId()))
		self.assertEqual([page.list.IsChecked(i) for i in range(3)], [True, False, True])
		self.assertEqual(nvdaStubs.spoken[-1], "2 items selected")
		selectNone.ProcessEvent(wx.CommandEvent(wx.wxEVT_BUTTON, selectNone.GetId()))
		self.assertEqual([page.list.IsChecked(i) for i in range(3)], [False, False, False])

	def _finish(self, **fields):
		from jawsMigrator import migrator

		self.wizard.result = migrator.MigrationResult(outputFolder=os.path.join(_configDir, "no such folder"), **fields)
		self.wizard._finish()
		return self.wizard.donePage.result.GetValue()

	def test_finishedStepClosesWithEscapeAndSaysWhenThereIsNoReport(self):
		self._finish()
		self.assertFalse(self.wizard.cancelButton.IsEnabled())
		self.assertEqual(self.wizard.GetEscapeId(), self.wizard.nextButton.GetId(), "Escape presses Close")
		boxes = len(nvdaStubs.boxes)
		self.wizard.donePage._onOpenReport(None)
		self.assertEqual(len(nvdaStubs.boxes), boxes + 1)
		self.assertIn("No report was written", nvdaStubs.boxes[-1])
		self.wizard.donePage._onOpenFolder(None)
		self.assertIn("could not be opened", nvdaStubs.boxes[-1])

	def test_rolledBackMigrationListsNothingAsDone(self):
		text = self._finish(error="The migration stopped because of an error: boom", rolledBack=True, applied=[object()], gesturesAdded=12, dictionaryEntries=3)
		self.assertIn("put back as they were", text)
		for claim in ("settings were set", "input gestures", "dictionary rules were added", "To undo everything"):
			self.assertNotIn(claim, text)
		text = self._finish(applied=[object()], gesturesAdded=12)
		self.assertIn("1 settings were set", text)
		self.assertIn("12 JAWS keystrokes are now NVDA input gestures", text)

	def test_onlyCopiedSchemesCanBeTurnedOn(self):
		scheme = lambda name: types.SimpleNamespace(name=name, soundCount=1, items={})  # noqa: E731
		options = types.SimpleNamespace(schemes=None, classicVoices=False, classicSettings=True, activeClassicScheme="Web (from JAWS)")
		self.wizard.plan = types.SimpleNamespace(schemes=[scheme("Classic (from JAWS)"), scheme("Web (from JAWS)")], options=options, jawsSchemeName=lambda: "Classic (from JAWS)")
		page = self.wizard.classicPage
		try:
			page.onShow()
			self.assertEqual(page._activeName(), "Web (from JAWS)")
			self.assertEqual(page.active.GetCount(), 3)
			page.schemes.Check(1, False)
			event = wx.CommandEvent(wx.wxEVT_CHECKLISTBOX, page.schemes.GetId())
			event.SetInt(1)
			page.schemes.ProcessEvent(event)
			self.assertEqual(page.active.GetCount(), 2, "the scheme that is not copied is no longer offered")
			self.assertEqual(page._activeName(), "")
			self.assertIn("no longer turned on", nvdaStubs.spoken[-1])
			page.collect(options)
			self.assertEqual((options.schemes, options.activeClassicScheme), (["Classic (from JAWS)"], ""))
		finally:
			self.wizard.plan = None


# -- the settings panel -----------------------------------------------------------------------------------------


class SettingsPanelTests(unittest.TestCase):
	def setUp(self):
		from jawsMigrator import state
		from jawsMigrator.gui import settingsPanel

		state.update(
			{
				"sleepApps": ["baseball"],
				"jawsProfileName": "",
				"activateJawsProfileAtStartup": False,
				"checkForUpdatesAutomatically": True,
				"sayTypeAndStateOnce": True,
				"quietTrayIconChanges": True,
				"sayHeadingAlone": True,
				"listItemsWithoutCoordinates": True,
				"positionLikeJawsInExplorer": True,
				"driveLetterLikeJaws": True,
				"sayWhatBackspaceDeletes": True,
				"documentsWithoutControlSupportTimer": True,
				"browseModeOnTabsAndToolbars": True,
				"playJawsLayerSound": True,
			},
		)
		self.calls = []
		settingsPanel.JawsMigratorSettingsPanel.plugin = types.SimpleNamespace(
			openAssistant=lambda: self.calls.append("openAssistant"),
			openRestore=lambda: self.calls.append("openRestore"),
			openImportSettings=lambda: self.calls.append("openImportSettings"),
			applyRuntimeSettings=lambda: self.calls.append("applyRuntimeSettings"),
		)
		self.dialog = _SettingsDialog(_frame)
		self.dialog.Show()

	def tearDown(self):
		from jawsMigrator.gui import settingsPanel

		settingsPanel.JawsMigratorSettingsPanel.plugin = None
		if self.dialog:
			self.dialog.Destroy()
		pump(0.05)

	def test_okAfterAMigrationKeepsWhatTheMigrationSaved(self):
		from jawsMigrator import state

		# While the panel is open, a migration adds applications and turns the profile on at startup
		# (and a restore of the assistant's state could turn saying a control's type and state once off).
		state.update(
			{
				"sleepApps": ["baseball", "winword"],
				"jawsProfileName": "JAWS settings",
				"activateJawsProfileAtStartup": True,
				"sayTypeAndStateOnce": False,
				"quietTrayIconChanges": False,
				"sayHeadingAlone": False,
				"listItemsWithoutCoordinates": False,
				"positionLikeJawsInExplorer": False,
				"driveLetterLikeJaws": False,
				"sayWhatBackspaceDeletes": False,
				"documentsWithoutControlSupportTimer": False,
				"browseModeOnTabsAndToolbars": False,
				"playJawsLayerSound": False,
			},
		)
		self.dialog.panel.onSave()
		state.forget()
		self.assertEqual(state.get("sleepApps"), ["baseball", "winword"])
		self.assertTrue(state.get("activateJawsProfileAtStartup"))
		self.assertTrue(state.get("checkForUpdatesAutomatically"))
		self.assertFalse(state.get("sayTypeAndStateOnce"), "a check box the user didn't change saves nothing")
		self.assertFalse(state.get("quietTrayIconChanges"), "a check box the user didn't change saves nothing")
		self.assertFalse(state.get("sayHeadingAlone"), "a check box the user didn't change saves nothing")
		self.assertFalse(state.get("listItemsWithoutCoordinates"), "a check box the user didn't change saves nothing")
		self.assertFalse(state.get("positionLikeJawsInExplorer"), "a check box the user didn't change saves nothing")
		self.assertFalse(state.get("driveLetterLikeJaws"), "a check box the user didn't change saves nothing")
		self.assertFalse(state.get("sayWhatBackspaceDeletes"), "a check box the user didn't change saves nothing")
		self.assertFalse(state.get("documentsWithoutControlSupportTimer"), "a check box the user didn't change saves nothing")
		self.assertFalse(state.get("browseModeOnTabsAndToolbars"), "a check box the user didn't change saves nothing")
		self.assertFalse(state.get("playJawsLayerSound"), "a check box the user didn't change saves nothing")

	def test_sayingTypeAndStateOnceIsSavedAndApplied(self):
		from jawsMigrator import labelRepeats, state

		panel = self.dialog.panel
		self.assertEqual(panel.sayOnce.GetLabel(), "Say a control's type and state &once, even when its label repeats them")
		self.assertTrue(panel.sayOnce.GetValue(), "on unless turned off")
		panel.sayOnce.SetValue(False)
		self.calls.clear()
		panel.onSave()
		state.forget()
		self.assertFalse(state.get(labelRepeats.STATE_KEY))
		self.assertEqual(self.calls, ["applyRuntimeSettings"], "the assistant stops checking labels at once")
		panel.sayOnce.SetValue(True)
		panel.onSave()
		state.forget()
		self.assertTrue(state.get(labelRepeats.STATE_KEY))

	def test_quietTrayIconsAreSavedAndApplied(self):
		from jawsMigrator import state, trayChanges

		panel = self.dialog.panel
		self.assertEqual(panel.quietTray.GetLabel(), "Say a system &tray icon when you move to it, not each time its program changes it")
		self.assertTrue(panel.quietTray.GetValue(), "on unless turned off")
		panel.quietTray.SetValue(False)
		self.calls.clear()
		panel.onSave()
		state.forget()
		self.assertFalse(state.get(trayChanges.STATE_KEY))
		self.assertEqual(self.calls, ["applyRuntimeSettings"], "NVDA reads every change of a tray icon from now on")
		panel.quietTray.SetValue(True)
		panel.onSave()
		state.forget()
		self.assertTrue(state.get(trayChanges.STATE_KEY))

	def _checkBoxIsSavedAndApplied(self, checkBox, label, stateKey, applied):
		from jawsMigrator import state

		self.assertEqual(checkBox.GetLabel(), label)
		self.assertTrue(checkBox.GetValue(), "on unless turned off")
		checkBox.SetValue(False)
		self.calls.clear()
		self.dialog.panel.onSave()
		state.forget()
		self.assertFalse(state.get(stateKey))
		self.assertEqual(self.calls, ["applyRuntimeSettings"], applied)
		checkBox.SetValue(True)
		self.dialog.panel.onSave()
		state.forget()
		self.assertTrue(state.get(stateKey))

	def test_headingAloneIsSavedAndApplied(self):
		from jawsMigrator import quickNavHeadings

		self._checkBoxIsSavedAndApplied(
			self.dialog.panel.headingAlone,
			"When &quick navigation moves to a heading, don't say the landmark, region or list it is in",
			quickNavHeadings.STATE_KEY,
			"quick navigation says what a heading is in again, at once",
		)

	def test_listItemsWithoutCoordinatesIsSavedAndApplied(self):
		from jawsMigrator import listCoordinates

		self._checkBoxIsSavedAndApplied(
			self.dialog.panel.listNoCoordinates,
			"Lea&ve out the row and column numbers of items in lists, such as drives, files and messages",
			listCoordinates.STATE_KEY,
			"NVDA says a list item's row and column again, at once",
		)

	def test_positionLikeJawsIsSavedAndApplied(self):
		from jawsMigrator import listPosition

		self._checkBoxIsSavedAndApplied(
			self.dialog.panel.positionLikeJaws,
			"Don't say the position, such as 3 of 3, in Alt+Tab or when you come to a list in &File Explorer",
			listPosition.STATE_KEY,
			"NVDA says the position in File Explorer and Alt+Tab again, at once",
		)

	def test_driveLetterLikeJawsIsSavedAndApplied(self):
		from jawsMigrator import driveLetters

		self._checkBoxIsSavedAndApplied(
			self.dialog.panel.driveLetter,
			"Say a drive's name as &JAWS does, without the colon and parenthesis after its letter, as in Data (D:)",
			driveLetters.STATE_KEY,
			"NVDA says the colon and parenthesis after a drive letter again, at once",
		)

	def test_backspaceInSlowProgramsIsSavedAndApplied(self):
		from jawsMigrator import backspaceEcho

		self._checkBoxIsSavedAndApplied(
			self.dialog.panel.backspaceSlow,
			"Say what Backspac&e deletes, even when the program is slow to delete it",
			backspaceEcho.STATE_KEY,
			"Backspace is silent again where NVDA doesn't see the caret move in time, at once",
		)

	def test_documentsWithoutControlSupportTimerIsSavedAndApplied(self):
		from jawsMigrator import documentPolling

		self._checkBoxIsSavedAndApplied(
			self.dialog.panel.documentsUnpolled,
			"Keep Enhanced Control Support from reading a document's whole te&xt 20 times a second, which can freeze NVDA in a large file",
			documentPolling.STATE_KEY,
			"Enhanced Control Support checks documents again, at once",
		)

	def test_browseModeOnTabsAndToolbarsIsSavedAndApplied(self):
		from jawsMigrator import autoFormsMode

		self._checkBoxIsSavedAndApplied(
			self.dialog.panel.tabsBrowse,
			"Stay in &browse mode when you Tab to a tab or a toolbar button on a web page",
			autoFormsMode.STATE_KEY,
			"NVDA goes to focus mode on tabs and toolbars again, at once",
		)

	def test_version112sLevelFirstSettingIsGone(self):
		from jawsMigrator import state

		panel = self.dialog.panel
		self.assertFalse(hasattr(panel, "headingFirst"))
		self.assertNotIn("sayHeadingLevelFirst", state.DEFAULTS, "a state.json from 1.12 keeps the key, which nothing reads")
		labels = [child.GetLabel() for child in panel.GetChildren() if isinstance(child, wx.CheckBox)]
		self.assertFalse([label for label in labels if "level" in label.lower()], labels)

	def test_layerSoundChoiceIsSavedAndApplied(self):
		from jawsMigrator import layerSound, state

		panel = self.dialog.panel
		self.assertEqual(panel.playLayerSound.GetLabel(), "Play JAWS's layered &keystroke sound for NVDA+Shift+J, instead of a beep")
		self.assertTrue(panel.playLayerSound.GetValue(), "checked unless the beep was chosen")
		panel.playLayerSound.SetValue(False)
		self.calls.clear()
		panel.onSave()
		state.forget()
		self.assertFalse(state.get(layerSound.STATE_KEY))
		self.assertEqual(self.calls, ["applyRuntimeSettings"], "NVDA+Shift+J beeps from now on")
		panel.playLayerSound.SetValue(True)
		panel.onSave()
		state.forget()
		self.assertTrue(state.get(layerSound.STATE_KEY))

	def test_clearingAnApplicationRemovesOnlyThatOne(self):
		from jawsMigrator import state

		panel = self.dialog.panel
		panel.sleepList.Check(0, False)
		state.update({"sleepApps": ["baseball", "winword"]})
		panel.autoUpdate.SetValue(False)
		panel.onSave()
		state.forget()
		self.assertEqual(state.get("sleepApps"), ["winword"])
		self.assertFalse(state.get("checkForUpdatesAutomatically"))
		self.assertEqual(panel.sleepApps, ["winword"], "after Apply the panel lists what is saved")

	def _press(self, label):
		button = next(control for control in descendants(self.dialog.panel) if isinstance(control, wx.Button) and control.GetLabel() == label)
		button.ProcessEvent(wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId()))
		pump(0.1)

	def test_assistantWindowsOpenOnlyAfterNvdasSettingsAreSavedAndClosed(self):
		for label, action in (
			("Open the JAWS &Migration Assistant...", "openAssistant"),
			("&Restore NVDA settings from a backup...", "openRestore"),
			("Choose which JAWS &items to import...", "openImportSettings"),
		):
			with self.subTest(button=label):
				self.dialog = self.dialog or _SettingsDialog(_frame)
				self.dialog.Show()
				self.calls.clear()
				self._press(label)
				self.assertFalse(self.dialog.IsShown() if self.dialog else False, "NVDA's Settings dialog closed first")
				self.assertEqual(self.calls, ["applyRuntimeSettings", action], "its panels were saved, then the window opened")
				pump(0.1)
				self.dialog = None

	def test_nothingOpensWhileASettingIsNotValid(self):
		self.dialog.valid = False
		self._press("Open the JAWS &Migration Assistant...")
		self.assertTrue(self.dialog.IsShown())
		self.assertEqual(self.calls, [])


# -- the restore dialog -------------------------------------------------------------------------------------------


class RestoreDialogTests(unittest.TestCase):
	def test_askingAgainBringsTheOpenDialogForward(self):
		from jawsMigrator.gui import restoreDialog

		open_ = wx.Dialog(_frame, title="restore")
		original = restoreDialog.RestoreDialog
		restoreDialog._openDialog = open_
		restoreDialog.RestoreDialog = lambda parent: self.fail("a second restore dialog was made")
		try:
			restoreDialog.showRestoreDialog()
			self.assertEqual(nvdaStubs.spoken[-1], "The restore dialog is already open.")
		finally:
			restoreDialog._openDialog = None
			restoreDialog.RestoreDialog = original
			open_.Destroy()


# -- with a plan made from this computer's JAWS settings ------------------------------------------------


class PlanTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		from jawsMigrator import jawsIndex, nvdaApply, systemCheck

		facts = systemCheck.gatherFacts()
		candidates = facts.jawsWithSettings or facts.jaws
		if not candidates:
			raise unittest.SkipTest("no JAWS settings on this computer")
		facts.synths = [("ibmeci", "IBMTTS"), ("sapi5", "Microsoft Speech API version 5"), ("oneCore", "Windows OneCore voices"), ("espeak", "eSpeak NG")]
		facts.configWritable = True
		facts.classicSpeech.installed = facts.classicSpeech.usable = True
		facts.classicSpeech.version = "1.16"
		cls.facts = facts
		cls.jaws = candidates[0]
		cls.language = cls.jaws.primaryLanguage or "enu"
		cls.index = jawsIndex.buildIndex(cls.jaws, cls.language, facts.leasey)
		cls._scriptExists = nvdaApply.scriptExists
		nvdaApply.scriptExists = lambda module, className, script: True

	@classmethod
	def tearDownClass(cls):
		from jawsMigrator import nvdaApply

		nvdaApply.scriptExists = cls._scriptExists

	def plan(self, scope=None):
		from jawsMigrator import jawsIndex, migrator

		options = migrator.MigrationOptions(jaws=self.jaws, language=self.language, scope=scope or jawsIndex.BOTH)
		return migrator.buildPlan(options, self.index, self.facts, inNvda=True)

	def setUp(self):
		from jawsMigrator.gui import wizard

		self.wizard = wizard.MigrationWizard(_frame, self.facts)
		self.wizard.Show()

	def tearDown(self):
		self.wizard.Destroy()
		pump(0.05)

	def show(self, page):
		self.wizard._show(self.wizard.pages.index(page))
		pump(0.05)

	def test_everyStepWithAPlanLabelsItsControlsForNvda(self):
		self.wizard.plan = self.plan()
		steps = [self.wizard.pages[i] for i in self.wizard._relevantPages() if self.wizard.pages[i] not in (self.wizard.progressPage, self.wizard.donePage)]
		for page in steps:
			with self.subTest(step=page.title):
				self.show(page)
				self.assertEqual(labelProblems(page), [])
				self.assertEqual(duplicates(stepKeys(self.wizard, page)), {})
				if comtypesAvailable():
					for label, name in oleaccNames(page).items():
						self.assertEqual(name, label, "NVDA reads the control with its own label")

	def test_sleepingApplicationsFollowTheJawsSettingsReadLast(self):
		from jawsMigrator import jawsIndex

		page = self.wizard.choosePage
		self.wizard.plan = self.plan(jawsIndex.SHARED)
		self.show(page)
		self.assertNotIn("sleepApps", page.keys, "the shared settings have no applications of their own")
		self.wizard.plan = plan = self.plan(jawsIndex.BOTH)
		if not plan.sleepCandidates:
			self.skipTest("JAWS sleeps in no application here")
		self.show(page)
		self.assertTrue(page.checked("sleepApps"))
		page.collect(plan.options)
		self.assertEqual(plan.options.sleepApps, [name for name, _exes in plan.sleepCandidates])

	def test_nvdaKeyboardLayoutIsOnlyOfferedWithSettingsCenter(self):
		self.wizard.plan = plan = self.plan()
		self.show(self.wizard.choosePage)
		keys = self.wizard.keysPage
		self.show(keys)
		self.assertTrue(keys.nvdaLayout.IsEnabled())
		self.wizard.choosePage.list.Check(self.wizard.choosePage.keys.index("settings"), False)
		self.wizard.choosePage.collect(plan.options)
		self.show(keys)
		self.assertFalse(keys.nvdaLayout.IsEnabled())
		self.assertFalse(keys.nvdaLayout.GetPrevSibling().IsEnabled())
		self.assertEqual(keys.nvdaLayout.GetStringSelection(), "Keep NVDA's current keyboard layout")
		self.assertTrue(keys.details.GetValue().startswith("NVDA's keyboard layout stays as it is"))
		self.assertIn("NVDA's keyboard layout is not changed: it is one of the Settings Center options", self.wizard.summaryText())

	def test_summaryTurnsOnOnlyASchemeThatIsCopied(self):
		self.wizard.plan = plan = self.plan()
		if len(plan.schemes) < 2:
			self.skipTest("fewer than two JAWS schemes here")
		plan.options.schemes = [plan.schemes[0].name]
		plan.options.activeClassicScheme = plan.schemes[1].name
		self.assertIn("No scheme is turned on", self.wizard.summaryText())
		plan.options.activeClassicScheme = plan.schemes[0].name
		self.assertIn(f"The scheme {plan.schemes[0].name} is turned on", self.wizard.summaryText())

	def test_voicesSelectAllChecksOnlyProfilesThatCanBeMigrated(self):
		self.wizard.plan = plan = self.plan()
		page = self.wizard.voicePage
		self.show(page)
		selectAll = next(control for control in descendants(page) if isinstance(control, wx.Button) and control.GetLabel() == "Select &all")
		selectAll.ProcessEvent(wx.CommandEvent(wx.wxEVT_BUTTON, selectAll.GetId()))
		page.collect(plan.options)
		self.assertEqual([p.name for p in plan.profiles if p.name in plan.options.voiceProfiles], [p.name for p in plan.profiles if p.available])

	def test_reportAfterARollbackSaysEverythingWasUndone(self):
		from jawsMigrator import migrator, report, settingsMap

		plan = self.plan()
		change = settingsMap.SettingChange(settingsMap.NVDA, ("speech", "symbolLevel"), 100, "Punctuation level: all", "JAWS")
		result = migrator.MigrationResult(error="The migration stopped because of an error: boom", rolledBack=True, applied=[change], gesturesAdded=5, outputFolder=_configDir)
		_html, text = report.build(plan, result)
		self.assertIn("that was undone too", text)
		self.assertNotIn("Settings were written to", text)
		self.assertNotIn("NVDA now uses", text)
		self.assertIn("5 JAWS keystrokes became NVDA input gestures. That was undone", text)

	def test_reportWithoutKeyboardCommandsListsNoKeystrokes(self):
		from jawsMigrator import migrator, report

		plan = self.plan()
		if not plan.keys.bindings:
			self.skipTest("no JAWS keystrokes here")
		plan.options.keyboard = False
		_html, text = report.build(plan, migrator.MigrationResult(outputFolder=_configDir))
		self.assertIn("JAWS keyboard commands were not migrated, as you chose", text)
		self.assertNotIn(plan.keys.bindings[0].label, text)
		self.assertNotIn("gestures.ini was backed up first", text)


if __name__ == "__main__":
	unittest.main()
