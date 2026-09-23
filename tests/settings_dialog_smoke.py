# Drives JAWS Migration Assistant settings (NVDA menu, Preferences) outside NVDA, with stand-ins
# for NVDA's modules: the Show filter, Select all, Select none, single check boxes, the Check for
# updates and Input Gestures buttons, saving, and the wizard using the saved choice.
# Needs wxPython and JAWS settings on this computer. The choice is saved in a temporary folder,
# never in NVDA's real settings folder, and the wizard stops before migrating.
# Run: python tests/settings_dialog_smoke.py

import os
import shutil
import sys
import tempfile
import time
import types

sys.path.insert(0, os.path.dirname(__file__))

import wx  # noqa: E402

import nvdaStubs  # noqa: E402

failures = []


def check(condition, message):
	print(("ok   " if condition else "FAIL ") + message)
	if not condition:
		failures.append(message)


def pump(seconds=0.2):
	end = time.time() + seconds
	while time.time() < end:
		wx.Yield()
		time.sleep(0.01)


def fire(control, eventType, index=None):
	event = wx.CommandEvent(eventType.typeId, control.GetId())
	event.SetEventObject(control)
	if index is not None:
		event.SetInt(index)
	control.GetEventHandler().ProcessEvent(event)
	pump(0.05)


def click(button):
	fire(button, wx.EVT_BUTTON)


def show(dialog, category):
	index = dialog.categoryKeys.index(category)
	dialog.category.SetSelection(index)
	fire(dialog.category, wx.EVT_CHOICE, index)


def toggle(dialog, index, checked):
	dialog.list.Check(index, checked)
	fire(dialog.list, wx.EVT_CHECKLISTBOX, index)


def waitForPlan(dialog, seconds=180):
	deadline = time.time() + seconds
	while dialog.plan is None and time.time() < deadline and "could not" not in dialog.status.GetLabel():
		pump(0.1)
	return dialog.plan is not None


class FakePlugin:
	def __init__(self):
		self.calls = []

	def checkForUpdates(self):
		self.calls.append("checkForUpdates")

	def openInputGestures(self):
		self.calls.append("openInputGestures")

	def openAssistant(self):
		self.calls.append("openAssistant")


def gatherFacts():
	from jawsMigrator import systemCheck

	facts = systemCheck.gatherFacts()
	facts.synths = [("ibmeci", "IBMTTS"), ("sapi5", "Microsoft Speech API version 5"), ("oneCore", "Windows OneCore voices"), ("espeak", "eSpeak NG")]
	facts.configWritable = True
	facts.classicSpeech.installed = True
	facts.classicSpeech.usable = True
	facts.classicSpeech.version = "1.16"
	return facts


def testDialog(frame, configDir):
	from jawsMigrator import nvdaEnv, selection, state
	from jawsMigrator.gui import importDialog

	check(os.path.normcase(nvdaEnv.configDir()) == os.path.normcase(configDir), "the choice is saved in a temporary folder")
	facts = gatherFacts()
	plugin = FakePlugin()
	dialog = importDialog.showImportSettings(facts, plugin)
	check(dialog.GetTitle() == "JAWS Migration Assistant settings", f"title: {dialog.GetTitle()}")
	check(importDialog.showImportSettings(facts, plugin) is dialog, "opening it again brings the open dialog forward")
	check(not dialog.list.IsEnabled() and dialog.updatesButton.IsEnabled(), "while reading JAWS, only the update, gestures and close buttons work")
	check(waitForPlan(dialog), f"JAWS settings read: {dialog.status.GetLabel()}")
	items = dialog.items
	byCategory = {key: [item for item in items if item.category == key] for key, _label in selection.CATEGORIES}
	for key, label in selection.CATEGORIES:
		group = byCategory[key]
		print(f"     {label}: {len(group)} items, {sum(1 for item in group if item.available)} can be imported here")
	for key in (selection.SETTINGS, selection.SCHEMES, selection.PROFILES, selection.ALIASES):
		check(bool(byCategory[key]), f"found {key}")
	check(dialog.list.GetCount() == len(items), "Show: Everything lists every item")

	for index, key in enumerate(dialog.categoryKeys):
		show(dialog, key)
		expected = len(items) if key == importDialog.EVERYTHING else len(byCategory[key])
		check(dialog.list.GetCount() == expected, f"Show: {dialog.category.GetString(index)} lists {expected} items")

	show(dialog, selection.ALIASES)
	click(dialog.selectNoneButton)
	check(not any(dialog.list.IsChecked(i) for i in range(dialog.list.GetCount())), "Select none clears every voice alias shown")
	check(not any(dialog.selection.isSelected(item) for item in byCategory[selection.ALIASES]), "... and the saved choice agrees")
	click(dialog.selectAllButton)
	check(all(dialog.list.IsChecked(i) for i, item in enumerate(dialog.shown) if item.available), "Select all checks every voice alias shown")

	show(dialog, importDialog.EVERYTHING)
	click(dialog.selectNoneButton)
	check(selection.summary(items, dialog.selection).startswith("0 of "), f"Select none with Everything shown: {dialog.status.GetLabel()}")
	click(dialog.selectAllButton)
	usable = sum(1 for item in items if item.available)
	check(selection.summary(items, dialog.selection) == f"{usable} of {usable} items selected", f"Select all with Everything shown: {dialog.status.GetLabel()}")

	turnedOff = []
	for category in (selection.SETTINGS, selection.SCHEMES, selection.ALIASES, selection.PROFILES):
		show(dialog, category)
		for index, item in enumerate(dialog.shown):
			if item.available:
				toggle(dialog, index, False)
				turnedOff.append(item)
				break
	check(all(not dialog.selection.isSelected(item) for item in turnedOff), "single items turned off: " + ", ".join(item.key for item in turnedOff))

	show(dialog, selection.KEYBOARD)
	layoutRows = {item.key[len("keyboard:layout:") :]: index for index, item in enumerate(dialog.shown) if item.key.startswith("keyboard:layout:")}
	check(len(layoutRows) >= 2, "JAWS keyboard layouts listed: " + ", ".join(layoutRows))
	check(any(item.key == "setting:nvda:keyboard.keyboardLayout" for item in dialog.shown), "NVDA's keyboard layout setting is under Keyboard settings and layouts")
	wantedLayouts = [layoutId for layoutId in layoutRows if layoutId in ("desktop", "laptop")]
	for layoutId, index in layoutRows.items():
		toggle(dialog, index, layoutId in wantedLayouts)
	check(sorted(layoutId for layoutId, index in layoutRows.items() if dialog.list.IsChecked(index)) == sorted(wantedLayouts), f"layouts chosen: {wantedLayouts}")
	unavailable = next((item for item in items if not item.available), None)
	if unavailable is not None:
		show(dialog, unavailable.category)
		index = dialog.shown.index(unavailable)
		toggle(dialog, index, True)
		check(not dialog.list.IsChecked(index), f"an item that cannot be imported stays unchecked: {unavailable.label}")

	click(dialog.updatesButton)
	click(dialog.gesturesButton)
	check(plugin.calls == ["checkForUpdates", "openInputGestures"], f"Check for updates and Input Gestures buttons: {plugin.calls}")
	click(dialog.saveButton)
	pump(0.3)
	check(importDialog.ImportSettingsDialog.current() is None, "Save and close closes the dialog")
	check(os.path.isfile(os.path.join(configDir, "jawsMigrator", "state.json")), "state.json written to the temporary folder")
	state.forget()
	saved = selection.load()
	check(saved.customized and all(item.key in saved.excluded for item in turnedOff), "the choice is saved and reads back after a restart")

	dialog = importDialog.showImportSettings(facts, plugin)
	check(waitForPlan(dialog), "reopened")
	check(all(not dialog.selection.isSelected(item) for item in turnedOff), "the reopened dialog shows the saved choice")
	show(dialog, selection.OTHER)
	sounds = next(index for index, item in enumerate(dialog.shown) if item.key == "other:sounds")
	if dialog.shown[sounds].available:
		toggle(dialog, sounds, True)
		boxesBefore = len(nvdaStubs.boxes)
		click(dialog.closeButton)
		pump(0.3)
		check(len(nvdaStubs.boxes) > boxesBefore and "Save your choice" in nvdaStubs.boxes[-1], "closing with changes asks whether to save them")
		state.forget()
		check("other:sounds" in selection.load().included, "answering Yes saves the change")
		dialog = importDialog.showImportSettings(facts, plugin)
		check(waitForPlan(dialog), "reopened again")
	click(dialog.importButton)
	pump(0.3)
	check(importDialog.ImportSettingsDialog.current() is None and plugin.calls[-1] == "openAssistant", "Import the selected items now saves, closes and opens the migration assistant")
	return facts, turnedOff, wantedLayouts


def testKeysPage(dialog, wantedLayouts):
	page = dialog.keysPage
	plan = dialog.plan
	checked = [page.layoutIds[index] for index in range(page.layouts.GetCount()) if page.layouts.IsChecked(index)]
	check(sorted(checked) == sorted(wantedLayouts), f"the Keyboard step starts with the saved layouts: {checked}")
	print("     Layouts on the Keyboard step:")
	for index in range(page.layouts.GetCount()):
		print(f"       [{'x' if page.layouts.IsChecked(index) else ' '}] {page.layouts.GetString(index)}")
	print(f"     NVDA keyboard layout shown: {page.nvdaLayout.GetStringSelection()}")
	sections = {binding.section.lower() for binding in plan.keys.bindings}
	for layout in plan.keyboardLayouts:
		if layout.id in wantedLayouts:
			check(layout.section.lower() in sections, f"keystrokes of the {layout.name} layout are planned")
		else:
			check(layout.section.lower() not in sections, f"keystrokes of the {layout.name} layout are left out")
	before = len(plan.keys.bindings)
	click(page.layoutButtons[0])
	check(len(plan.options.keyboardLayouts) == len(plan.keyboardLayouts) and len(plan.keys.bindings) >= before, f"Select all layouts: {len(plan.keys.bindings)} keystrokes")
	click(page.layoutButtons[1])
	check(plan.options.keyboardLayouts == [], f"Select none layouts: {len(plan.keys.bindings)} keystrokes, the common ones")
	for index, layoutId in enumerate(page.layoutIds):
		page.layouts.Check(index, layoutId in wantedLayouts)
	fire(page.layouts, wx.EVT_CHECKLISTBOX, 0)
	page.nvdaLayout.SetSelection(0)
	fire(page.nvdaLayout, wx.EVT_CHOICE, 0)
	check(plan.options.nvdaKeyboardLayout == "desktop", "choosing NVDA's desktop keyboard layout")
	values = {change.key: change.value for change in plan.finalSettingChanges()}
	check(values.get("keyboard.keyboardLayout") == "desktop", f"NVDA's keyboard layout becomes {values.get('keyboard.keyboardLayout')}")
	capsLock = any(layout.capsLock for layout in plan.chosenKeyboardLayouts())
	modifiers = values.get("keyboard.NVDAModifierKeys")
	check(modifiers is None or bool(modifiers & 1) == capsLock, f"Caps Lock is an NVDA key only with a Caps Lock layout: NVDA keys {modifiers}")


def testWizard(frame, facts, turnedOff, wantedLayouts):
	from jawsMigrator import nvdaApply
	from jawsMigrator.gui import wizard

	nvdaApply.scriptExists = lambda module, className, script: True
	dialog = wizard.MigrationWizard(frame, facts)
	dialog.Show()
	pump()
	visited = []
	for _step in range(15):
		page = dialog.pages[dialog.current]
		visited.append(page.title)
		if page is dialog.choosePage:
			check(dialog.choosePage.note.GetLabel().startswith("Narrowed by your saved choice"), "the wizard says it uses the saved choice")
		if page is dialog.keysPage:
			testKeysPage(dialog, wantedLayouts)
		if page is dialog.summaryPage:
			break
		dialog.onNext(None)
		deadline = time.time() + 180
		while dialog.busy and time.time() < deadline:
			pump(0.1)
		pump()
	print("     Wizard steps:", " > ".join(visited))
	plan = dialog.plan
	options = plan.options
	check(options.selectionApplied, "the wizard applied the saved choice")
	changeKeys = {f"setting:{change.target}:{change.key}" for change in plan.settings.changes}
	schemes = {f"scheme:{scheme.name}" for scheme in plan.selectedSchemes()}
	profiles = {f"profile:{profilePlan.name}" for profilePlan in plan.selectedProfiles()}
	aliases = {f"alias:{name}" for name in options.voiceAliases or ()}
	for item in turnedOff:
		check(item.key not in changeKeys | schemes | profiles | aliases, f"left out of the migration: {item.key}")
	check(options.sounds, "the JAWS sounds turned on in the settings dialog are migrated")
	check(dialog.keysPage in [dialog.pages[i] for i in dialog._relevantPages()], "the Keyboard step was shown")
	summary = dialog.summaryText()
	check("NVDA's keyboard layout becomes desktop." in summary, "the summary tells which keyboard layout NVDA gets")
	print()
	print(summary)
	dialog.Destroy()


def main():
	app = wx.App()
	app.SetAppName("jawsMigratorSettingsSmoke")
	frame = wx.Frame(None)
	configDir = tempfile.mkdtemp(prefix="jawsMigrator-settings-")
	nvdaStubs.install(frame)
	globalVars = types.ModuleType("globalVars")
	globalVars.appDir = ""
	globalVars.appArgs = types.SimpleNamespace(secure=False, configPath=configDir)
	sys.modules["globalVars"] = globalVars
	try:
		facts, turnedOff, wantedLayouts = testDialog(frame, configDir)
		testWizard(frame, facts, turnedOff, wantedLayouts)
	finally:
		frame.Destroy()
		shutil.rmtree(configDir, ignore_errors=True)
	print()
	print("Spoken:", nvdaStubs.spoken[:12])
	print(f"{len(failures)} failed" if failures else "All checks passed")
	return 1 if failures else 0


if __name__ == "__main__":
	sys.exit(main())
