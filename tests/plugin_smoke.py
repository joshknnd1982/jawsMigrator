# Loads the global plugin the way NVDA does, with stand-ins for NVDA's modules and real wx menus,
# and checks what it adds: the Tools submenu, NVDA menu, Preferences, JAWS Migration Assistant
# settings, the Settings panel, the NVDA+Shift+J commands and their sound (or the beep, when chosen),
# the check that has NVDA say a control's type and state once, the one that has NVDA say a system tray
# icon when the focus moves to it (with its note of each key press), the one that has quick navigation
# say a heading without the landmark it is in, the one that leaves out a list item's row and column, the
# one that says what Backspace deletes in a slow program, the one that keeps browse mode on a web page's tabs and toolbar buttons (with its notes of each focus and Tab), the guard that keeps the
# focus in Outlook when NVDA waits for it, the focus and change notices it passes on to NVDA; and that
# unloading takes it all away.
# Needs wxPython. NVDA's settings folder is a temporary one. JAWS's layered keystroke sound is read
# from this computer's JAWS, if there is one; nothing else is read or written.
# Run: python tests/plugin_smoke.py

import collections
import dataclasses
import enum
import os
import shutil
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(__file__))

import wx  # noqa: E402

import nvdaStubs  # noqa: E402

failures = []


def check(condition, message):
	print(("ok   " if condition else "FAIL ") + message)
	if not condition:
		failures.append(message)


class TrayIcon(wx.EvtHandler):
	def __init__(self):
		super().__init__()
		self.toolsMenu = wx.Menu()
		self.preferencesMenu = wx.Menu()
		self.preferencesMenu.Append(wx.ID_ANY, "&Settings...")


class SpeechFilter:
	"""NVDA's speech.extensions.filter_speechSequence: handlers run in their order."""

	def __init__(self):
		self._handlers = collections.OrderedDict()

	def register(self, handler):
		self._handlers[id(handler)] = handler

	def unregister(self, handler):
		return self._handlers.pop(id(handler), None) is not None

	def moveToEnd(self, handler, last=False):
		self._handlers.move_to_end(id(handler), last=last)
		return True

	@property
	def handlers(self):
		yield from self._handlers.values()


class Labelled(enum.Enum):
	@property
	def displayString(self):
		return self.value

	@property
	def negativeDisplayString(self):
		return "not " + self.value


def getControlFieldSpeech(attrs, ancestorAttrs, fieldType, formatConfig=None, extraDetail=False, reason=None):
	"""NVDA's speech for a field of a browse mode document (speech.getControlFieldSpeech)."""
	return []


def _objectSpeech_calculateAllowedProps(reason, shouldReportTextContent, objRole):
	"""What NVDA may say about an object it reads (speech.speech._objectSpeech_calculateAllowedProps)."""
	return {"includeTableCellCoords": True, "cellCoordsText": True}


def processText(locale, text, symbolLevel, normalize=False):
	"""NVDA's speech dictionaries, then its symbols (speech.speech.processText), as far as the smoke test goes."""
	return text.replace(":)", " smiley ")


@dataclasses.dataclass(frozen=True, kw_only=True)
class SymbolDictionaryDefinition:
	"""NVDA's characterProcessing.SymbolDictionaryDefinition, as far as the assistant's symbol rules go."""

	name: str
	path: str
	source: str = "builtin"
	allowComplexSymbols: bool = False
	mandatory: bool = False


class TextInfoQuickNavItem:
	"""NVDA's browseMode.TextInfoQuickNavItem."""

	def report(self, readUnit=None):
		pass


class BrowseModeTreeInterceptor:
	"""NVDA's browseMode.BrowseModeTreeInterceptor."""

	passThrough = False

	def shouldPassThrough(self, obj, reason=None):
		return True


class EditableText:
	"""NVDA's editableText.EditableText, as far as Backspace goes."""

	def _backspaceScriptHelper(self, unit, gesture):
		pass

	def _hasCaretMoved(self, bookmark, retryInterval=0.01, timeout=None, origWord=None):
		return (False, None)


#: NVDA's own report, choice of mode and Backspace, before the assistant puts its own in their place.
NVDA_REPORT = vars(TextInfoQuickNavItem)["report"]
NVDA_PASS_THROUGH = vars(BrowseModeTreeInterceptor)["shouldPassThrough"]
NVDA_BACKSPACE = vars(EditableText)["_backspaceScriptHelper"]
NVDA_CARET_WAIT = vars(EditableText)["_hasCaretMoved"]


def installSpeech():
	"""NVDA's speech extension points, control words and speech order, and browse mode's quick navigation report,
	as far as the assistant uses them."""
	speech = types.ModuleType("speech")
	speech.extensions = types.ModuleType("speech.extensions")
	speech.extensions.filter_speechSequence = SpeechFilter()
	speech.speech = types.ModuleType("speech.speech")
	speech.speech.getPropertiesSpeech = lambda reason=None, **values: ["1 of 2"]
	speech.speech._objectSpeech_calculateAllowedProps = _objectSpeech_calculateAllowedProps
	speech.speech.processText = processText
	speech.getControlFieldSpeech = getControlFieldSpeech
	controlTypes = types.ModuleType("controlTypes")
	controlTypes.Role = Labelled(
		"Role",
		{"RADIOBUTTON": "radio button", "BUTTON": "button", "HEADING": "heading", "LIST": "list", "LISTITEM": "list item", "TAB": "tab"},
	)
	controlTypes.State = Labelled("State", {"CHECKED": "checked", "EDITABLE": "editable"})
	controlTypes.OutputReason = enum.Enum("OutputReason", "FOCUS QUICKNAV CARET QUERY")
	browseMode = types.ModuleType("browseMode")
	browseMode.TextInfoQuickNavItem = TextInfoQuickNavItem
	browseMode.BrowseModeTreeInterceptor = BrowseModeTreeInterceptor
	editableText = types.ModuleType("editableText")
	editableText.EditableText = EditableText
	characterProcessing = types.ModuleType("characterProcessing")
	characterProcessing.SymbolDictionaryDefinition = SymbolDictionaryDefinition
	characterProcessing.SymbolLevel = types.SimpleNamespace(MOST=200, ALL=300)
	characterProcessing._symbolDictionaryDefinitions = [SymbolDictionaryDefinition(name="builtin", path=""), SymbolDictionaryDefinition(name="user", path="")]
	characterProcessing.clearSpeechSymbols = lambda: None
	for module in (speech, speech.extensions, speech.speech, controlTypes, browseMode, editableText, characterProcessing):
		sys.modules[module.__name__] = module
	return speech.extensions.filter_speechSequence


def installSounds():
	"""NVDA's nvwave and tones, recording what plays."""
	played = []
	sys.modules["nvwave"] = types.SimpleNamespace(playWaveFile=lambda fileName, asynchronous=True: played.append(fileName))
	sys.modules["tones"].beep = lambda hz, length, *args, **kwargs: played.append(("beep", hz, length))
	return played


def installNvda(frame, configDir):
	nvdaStubs.install(frame)
	globalVars = types.ModuleType("globalVars")
	globalVars.appDir = ""
	globalVars.appArgs = types.SimpleNamespace(secure=False, configPath=configDir)
	sys.modules["globalVars"] = globalVars
	frame.sysTrayIcon = TrayIcon()
	frame.opened = []
	frame.onInputGesturesCommand = lambda event: frame.opened.append("inputGestures")
	gui = sys.modules["gui"]
	gui.mainFrame = frame
	settingsDialogs = types.ModuleType("gui.settingsDialogs")
	settingsDialogs.NVDASettingsDialog = types.SimpleNamespace(categoryClasses=[])
	settingsDialogs.SettingsPanel = type("SettingsPanel", (), {})
	guiHelper = types.ModuleType("gui.guiHelper")
	guiHelper.BoxSizerHelper = guiHelper.ButtonHelper = object
	for name, module in (("settingsDialogs", settingsDialogs), ("guiHelper", guiHelper)):
		sys.modules[f"gui.{name}"] = module
		setattr(gui, name, module)

	def fetchAppModule(processID, appName):
		return types.SimpleNamespace(processID=processID, appName=appName)

	sys.modules["appModuleHandler"] = types.SimpleNamespace(fetchAppModule=fetchAppModule, nvdaFetchAppModule=fetchAppModule, runningTable={})
	return settingsDialogs


def main():
	app = wx.App()
	app.SetAppName("jawsMigratorPluginSmoke")
	frame = wx.Frame(None)
	configDir = tempfile.mkdtemp(prefix="jawsMigrator-plugin-")
	try:
		settingsDialogs = installNvda(frame, configDir)
		speechFilter = installSpeech()
		played = installSounds()
		import jawsMigrator

		# Only the menus are wanted here, not the first-run offer or the update check.
		jawsMigrator.state.set("welcomeShown", True)
		jawsMigrator.state.set("checkForUpdatesAutomatically", False)
		from jawsMigrator import labelRepeats

		# Another add-on's speech filter, such as ClassicSpeech's, already in place.
		def otherAddon(sequence):
			return sequence

		speechFilter.register(otherAddon)
		plugin = jawsMigrator.GlobalPlugin()
		handlers = list(speechFilter.handlers)
		check(labelRepeats.isRegistered() and handlers == [labelRepeats._speechFilter, otherAddon], "a control's type and state are said once, checked before other add-ons' speech filters")
		spoken = speechFilter._handlers[id(labelRepeats._speechFilter)](["As low as $49.97/mo, radio button checked 1 of 2", "radio button", "checked"])
		check(spoken == ["As low as $49.97/mo", "radio button", "checked"], f"the tester's radio button: {spoken}")
		from jawsMigrator import changeRepeats

		check(changeRepeats.isRegistered() and plugin._changeRepeats is changeRepeats, "what activating a control changed is said once, with it")
		jawsMigrator.state.set(labelRepeats.STATE_KEY, False)
		plugin.applyRuntimeSettings()
		check(not labelRepeats.isRegistered() and list(speechFilter.handlers) == [otherAddon], "turned off in the Settings panel, NVDA's speech is left alone")
		check(not changeRepeats.isRegistered(), "and so are NVDA's change notices")
		jawsMigrator.state.set(labelRepeats.STATE_KEY, True)
		plugin.applyRuntimeSettings()
		check(labelRepeats.isRegistered() and changeRepeats.isRegistered(), "and on again")
		# A system tray icon is said when the focus moves to it; NVDA's key presses are noted, and always run.
		from jawsMigrator import trayChanges

		decider = sys.modules["inputCore"].decide_executeGesture
		check(trayChanges.isRegistered() and plugin._trayChanges is trayChanges, "a system tray icon is said when the focus moves to it")
		# Browse mode on a web page's tabs and toolbar buttons notes Tab too (see autoFormsMode, below).
		check(trayChanges.noteGesture in decider.handlers and decider.decide(gesture="kb:a"), "each key press is noted, and NVDA runs it")
		jawsMigrator.state.set(trayChanges.STATE_KEY, False)
		plugin.applyRuntimeSettings()
		check(not trayChanges.isRegistered() and trayChanges.noteGesture not in decider.handlers, "turned off in the Settings panel, key presses are no longer noted")
		jawsMigrator.state.set(trayChanges.STATE_KEY, True)
		plugin.applyRuntimeSettings()
		check(trayChanges.isRegistered() and decider.handlers.count(trayChanges.noteGesture) == 1, "and on again, once")
		# Quick navigation says a heading without what it is in, a list item has no row and column, and a web page's
		# tabs and toolbar buttons stay in browse mode: NVDA's field speech, quick navigation report, what NVDA may say
		# about an object, and its choice of mode.
		from jawsMigrator import autoFormsMode, backspaceEcho, listCoordinates, listPosition, quickNavHeadings

		speechPackage, speechModule = sys.modules["speech"], sys.modules["speech.speech"]
		nvdaFieldSpeech, nvdaAllowed = getControlFieldSpeech, _objectSpeech_calculateAllowedProps

		def wrapped():
			return (
				getattr(speechPackage.getControlFieldSpeech, "__wrapped__", None) is nvdaFieldSpeech
				and getattr(TextInfoQuickNavItem.report, "__wrapped__", None) is NVDA_REPORT
				and getattr(speechModule._objectSpeech_calculateAllowedProps, "__wrapped__", None) is nvdaAllowed
				and getattr(BrowseModeTreeInterceptor.shouldPassThrough, "__wrapped__", None) is NVDA_PASS_THROUGH
				and getattr(EditableText._backspaceScriptHelper, "__wrapped__", None) is NVDA_BACKSPACE
				and getattr(EditableText._hasCaretMoved, "__wrapped__", None) is NVDA_CARET_WAIT
			)

		def nvdasOwn():
			return (
				speechPackage.getControlFieldSpeech is nvdaFieldSpeech
				and TextInfoQuickNavItem.report is NVDA_REPORT
				and speechModule._objectSpeech_calculateAllowedProps is nvdaAllowed
				and BrowseModeTreeInterceptor.shouldPassThrough is NVDA_PASS_THROUGH
				and EditableText._backspaceScriptHelper is NVDA_BACKSPACE
				and EditableText._hasCaretMoved is NVDA_CARET_WAIT
			)

		def allRegistered():
			return (
				quickNavHeadings.isRegistered()
				and listCoordinates.isRegistered()
				and listPosition.isRegistered()
				and listCoordinates._positionRule is listPosition.leaveOutPosition
				and autoFormsMode.isRegistered()
				and backspaceEcho.isRegistered()
			)

		check(allRegistered() and wrapped() and plugin._autoFormsMode is autoFormsMode, "headings, list items and their positions, Backspace and web page tabs as in JAWS")
		check(decider.handlers.count(autoFormsMode.noteGesture) == 1, "Tab is noted, once")
		for module in (quickNavHeadings, listCoordinates, listPosition, autoFormsMode, backspaceEcho):
			jawsMigrator.state.set(module.STATE_KEY, False)
		plugin.applyRuntimeSettings()
		check(
			not quickNavHeadings.isRegistered()
			and not listCoordinates.isRegistered()
			and not listPosition.isRegistered()
			and not autoFormsMode.isRegistered()
			and not backspaceEcho.isRegistered()
			and nvdasOwn(),
			"turned off in the Settings panel, NVDA's own are back",
		)
		for module in (quickNavHeadings, listCoordinates, listPosition, autoFormsMode, backspaceEcho):
			jawsMigrator.state.set(module.STATE_KEY, True)
		plugin.applyRuntimeSettings()
		check(allRegistered() and wrapped(), "and on again, wrapped once")
		# The focus a tab gets from anything but a tab keeps browse mode: the plugin notes each focus first.
		roles = sys.modules["controlTypes"].Role
		tab = types.SimpleNamespace(role=roles.TAB, states=set(), name="Write", appModule=None, treeInterceptor=None)
		button = types.SimpleNamespace(role=roles.BUTTON, states=set(), name="Title", appModule=None, treeInterceptor=None)
		document = BrowseModeTreeInterceptor()
		focus = sys.modules["controlTypes"].OutputReason.FOCUS
		plugin.event_gainFocus(button, lambda: None)
		plugin.event_gainFocus(tab, lambda: None)
		check(document.shouldPassThrough(tab, reason=focus) is False, "Tab from another control to a tab: browse mode")
		document.passThrough = True
		plugin.event_gainFocus(tab, lambda: None)
		check(document.shouldPassThrough(tab, reason=focus) is True, "from a tab to a tab in focus mode: focus mode stays")
		# Enhanced Control Support keeps its timer off documents NVDA follows. NVDA may import it after the assistant.
		from jawsMigrator import documentPolling

		enhancedControlSupport = types.ModuleType(documentPolling.MODULE)
		enhancedControlSupport.TimerMixin = type("TimerMixin", (), {})

		def shouldUseTimerMixin(conf, obj, clsList):
			return True

		enhancedControlSupport.shouldUseTimerMixin = shouldUseTimerMixin
		check(documentPolling.isRegistered() and not documentPolling.isInstalled(), "without Enhanced Control Support there is nothing to change")
		sys.modules[documentPolling.MODULE] = enhancedControlSupport
		app.ProcessPendingEvents()
		check(
			documentPolling.isInstalled() and enhancedControlSupport.shouldUseTimerMixin.__wrapped__ is shouldUseTimerMixin,
			"loaded after the assistant, Enhanced Control Support leaves its timer off documents once NVDA has loaded every plugin",
		)
		jawsMigrator.state.set(documentPolling.STATE_KEY, False)
		plugin.applyRuntimeSettings()
		check(not documentPolling.isRegistered() and enhancedControlSupport.shouldUseTimerMixin is shouldUseTimerMixin, "turned off in the Settings panel, it has its own choice back")
		jawsMigrator.state.set(documentPolling.STATE_KEY, True)
		plugin.applyRuntimeSettings()
		check(enhancedControlSupport.shouldUseTimerMixin.__wrapped__ is shouldUseTimerMixin, "and on again, wrapped once")
		# A drive's ":)" is taken out before NVDA's speech dictionaries, and left out by a symbol rule of its own.
		from jawsMigrator import driveLetters

		symbolDefinitions = sys.modules["characterProcessing"]._symbolDictionaryDefinitions
		check(
			driveLetters.isRegistered()
			and driveLetters.isGuardingSpeech()
			and speechModule.processText.__wrapped__ is processText
			and [definition.name for definition in symbolDefinitions][-2:] == [driveLetters.DEFINITION_NAME, "user"],
			"a drive's \":)\" is taken out before NVDA's speech dictionaries, and its symbol rule comes before the user's symbols",
		)
		said = speechModule.processText("en_US", "Data (D:)", 200)
		check(said == "Data (D" and speechModule.processText("en_US", "Great :) thanks", 200) == "Great  smiley  thanks", f"Data (D:) at most: {said!r}; a smiley in text as before")
		jawsMigrator.state.set(driveLetters.STATE_KEY, False)
		plugin.applyRuntimeSettings()
		check(not driveLetters.isRegistered() and speechModule.processText is processText and driveLetters.DEFINITION_NAME not in [d.name for d in symbolDefinitions], "turned off in the Settings panel, NVDA's own are back")
		jawsMigrator.state.set(driveLetters.STATE_KEY, True)
		plugin.applyRuntimeSettings()
		check(speechModule.processText.__wrapped__ is processText, "and on again, wrapped once")
		# Opening Outlook puts the focus in Outlook: NVDA's Outlook support is guarded as NVDA loads it.
		from jawsMigrator import outlookFocus

		appModuleHandler = sys.modules["appModuleHandler"]
		check(
			outlookFocus.isRegistered() and appModuleHandler.fetchAppModule.__wrapped__ is appModuleHandler.nvdaFetchAppModule,
			"NVDA's Outlook support is guarded as NVDA loads it",
		)
		check(appModuleHandler.fetchAppModule(4242, "notepad").appName == "notepad", "and NVDA still loads every application's support")
		# The focus and NVDA's change notices go on to NVDA, once each.
		handled = []
		control = types.SimpleNamespace(appModule=None, treeInterceptor=None, _speakObjectPropertiesCache={})
		for event in ("gainFocus", "stateChange", "IA2AttributeChange", "nameChange"):
			getattr(plugin, f"event_{event}")(control, lambda event=event: handled.append(event))
		check(handled == ["gainFocus", "stateChange", "IA2AttributeChange", "nameChange"], f"NVDA handles every notice: {handled}")
		# NVDA+Shift+J: JAWS's layered keystroke sound, when this computer has JAWS, or a beep.
		from jawsMigrator import jawsDetect, layerSound

		jawsSound = layerSound.jawsLayerSound(jawsDetect.findJawsInstallations())
		plugin.script_commandLayer(None)
		if jawsSound:
			copy = layerSound.copyPath()
			check(played == [copy] and copy.startswith(configDir) and os.path.isfile(copy), f"NVDA+Shift+J plays a copy of {jawsSound}: {played}")
		else:
			check(played == [("beep", 660, 40)], f"without a JAWS layered keystroke sound, NVDA+Shift+J beeps: {played}")
		check(plugin._layerActive, "NVDA+Shift+J starts the layer")
		# NVDA's script decorator gathers the plugin's own gestures there; leaving the layer binds them again.
		plugin._GlobalPlugin__gestures = {"kb:NVDA+shift+j": "commandLayer"}
		plugin.script_commandLayer(None)
		check(not plugin._layerActive and len(played) == 1, "pressed again, it leaves the layer quietly")
		# The beep, when chosen in NVDA's Settings, JAWS Migration Assistant; saving there applies the settings again.
		played.clear()
		jawsMigrator.state.set(layerSound.STATE_KEY, False)
		plugin.applyRuntimeSettings()
		plugin.script_commandLayer(None)
		check(played == [("beep", 660, 40)] and plugin._layerActive, f"with the beep chosen, NVDA+Shift+J beeps: {played}")
		plugin.script_commandLayer(None)
		played.clear()
		jawsMigrator.state.set(layerSound.STATE_KEY, True)
		plugin.applyRuntimeSettings()
		plugin.script_commandLayer(None)
		check(played == ([layerSound.copyPath()] if jawsSound else [("beep", 660, 40)]), f"and JAWS's sound again when chosen: {played}")
		plugin.script_commandLayer(None)
		tray = frame.sysTrayIcon
		preferences = [item.GetItemLabelText() for item in tray.preferencesMenu.GetMenuItems()]
		check("JAWS Migration Assistant settings..." in preferences, f"NVDA menu, Preferences: {preferences}")
		tools = tray.toolsMenu.GetMenuItems()
		submenu = [item.GetItemLabelText() for item in tools[0].GetSubMenu().GetMenuItems()] if tools else []
		check("Choose what to import..." in submenu and "Migrate JAWS settings to NVDA..." in submenu, f"NVDA menu, Tools, JAWS Migration Assistant: {submenu}")
		soundItems = ("Use JAWS sounds in place of NVDA's sounds", "Restore NVDA's own sounds", "Copy all JAWS sounds into ClassicSpeech")
		check(all(item in submenu for item in soundItems), "the JAWS sounds actions are in the Tools submenu")
		check(settingsDialogs.NVDASettingsDialog.categoryClasses and settingsDialogs.NVDASettingsDialog.categoryClasses[0].__name__ == "JawsMigratorSettingsPanel", "the Settings panel is registered")
		calls = []
		plugin.openImportSettings = lambda: calls.append("openImportSettings")
		tray.ProcessEvent(wx.CommandEvent(wx.EVT_MENU.typeId, plugin._preferencesItem.GetId()))
		check(calls == ["openImportSettings"], "Preferences, JAWS Migration Assistant settings opens the settings dialog")
		plugin.openInputGestures()
		for _ in range(5):
			wx.Yield()
		check(frame.opened == ["inputGestures"], "NVDA's Input Gestures dialog opens")
		layer = jawsMigrator.LAYER_GESTURES
		check(layer.get("kb:o") == "openImportSettings" and layer.get("kb:g") == "openInputGestures", "NVDA+Shift+J then O and G")
		check(layer.get("kb:s") == "toggleJawsSounds" and layer.get("kb:a") == "copyJawsSounds", "NVDA+Shift+J then S and A")
		# Without ClassicSpeech, JAWS sounds are refused and nothing changes.
		from jawsMigrator import migrator

		facts = types.SimpleNamespace(classicSpeech=types.SimpleNamespace(installed=False, usable=False), jaws=[object()], jawsWithSettings=[])
		outcome = migrator.useJawsSounds(facts)
		check(not outcome.succeeded and "ClassicSpeech" in outcome.message, f"JAWS sounds need ClassicSpeech: {outcome.message[:70]}...")
		check(not migrator.copyAllJawsSounds(facts).succeeded, "copying all JAWS sounds needs ClassicSpeech too")
		check(not migrator.restoreNvdaSounds().succeeded, "restoring NVDA's sounds when nothing was changed says so")
		check(all(hasattr(plugin, f"script_{name}") for name in set(layer.values())), "every layer command has a script")
		plugin.terminate()
		check([item.GetItemLabelText() for item in tray.preferencesMenu.GetMenuItems()] == ["Settings..."], "unloading removes the Preferences item")
		check(not tray.toolsMenu.GetMenuItems(), "unloading removes the Tools submenu")
		check(not settingsDialogs.NVDASettingsDialog.categoryClasses, "unloading removes the Settings panel")
		check(not labelRepeats.isRegistered() and list(speechFilter.handlers) == [otherAddon], "unloading stops checking NVDA's speech")
		check(not changeRepeats.isRegistered() and plugin._changeRepeats is None, "and NVDA's change notices")
		check(not trayChanges.isRegistered() and plugin._trayChanges is None and not decider.handlers, "and NVDA's key presses")
		check(
			not quickNavHeadings.isRegistered()
			and not listCoordinates.isRegistered()
			and not listPosition.isRegistered()
			and not backspaceEcho.isRegistered()
			and nvdasOwn(),
			"and NVDA's field speech, quick navigation report, object speech, Backspace and choice of mode",
		)
		check(not autoFormsMode.isRegistered() and plugin._autoFormsMode is None, "and the note of each focus")
		check(
			not documentPolling.isRegistered() and enhancedControlSupport.shouldUseTimerMixin is shouldUseTimerMixin,
			"and Enhanced Control Support's own choice of its timer",
		)
		del sys.modules[documentPolling.MODULE]
		check(
			not driveLetters.isRegistered() and speechModule.processText is processText and driveLetters.DEFINITION_NAME not in [d.name for d in symbolDefinitions],
			"and NVDA's processText and symbol dictionaries",
		)
		check(not outlookFocus.isRegistered() and appModuleHandler.fetchAppModule is appModuleHandler.nvdaFetchAppModule, "and NVDA's Outlook support")
		# Version 1.5 imported a module NVDA's own Python doesn't have, and NVDA didn't load the assistant at all:
		# nothing in the Tools or Preferences menus, no NVDA+Shift+J, nothing in Input Gestures. A module that
		# can't load, or a step of the assistant's start that fails, now costs only that one feature.
		def loadsAnyway(why, sound):
			played.clear()
			plugin = jawsMigrator.GlobalPlugin()
			preferences = [item.GetItemLabelText() for item in tray.preferencesMenu.GetMenuItems()]
			check(
				"JAWS Migration Assistant settings..." in preferences and tray.toolsMenu.GetMenuItems() and settingsDialogs.NVDASettingsDialog.categoryClasses,
				f"{why}, the assistant still loads, with its Preferences item, Tools submenu and Settings panel",
			)
			plugin.script_commandLayer(None)
			check(plugin._layerActive and played == [sound], f"and NVDA+Shift+J starts the layer, with {sound}: {played}")
			handled = []
			control = types.SimpleNamespace(appModule=None, treeInterceptor=None)
			for event in ("gainFocus", "stateChange", "IA2AttributeChange", "nameChange"):
				getattr(plugin, f"event_{event}")(control, lambda event=event: handled.append(event))
			check(len(handled) == 4, f"and NVDA handles the focus and every change notice: {handled}")
			plugin.terminate()

		unloadable = (
			"layerSound",
			"labelRepeats",
			"changeRepeats",
			"trayChanges",
			"quickNavHeadings",
			"listCoordinates",
			"listPosition",
			"driveLetters",
			"autoFormsMode",
			"backspaceEcho",
			"documentPolling",
			"outlookFocus",
		)
		for name in unloadable:
			delattr(jawsMigrator, name)
			sys.modules[f"jawsMigrator.{name}"] = None
		try:
			loadsAnyway("with modules NVDA can't load", ("beep", 660, 40))
		finally:
			for name in unloadable:
				del sys.modules[f"jawsMigrator.{name}"]

		def broken(*args, **kwargs):
			raise RuntimeError("broken for the test")

		steps = [(jawsMigrator.GlobalPlugin, name) for name in ("applyRuntimeSettings", "_keepOutlookFocus", "_followConfigResets", "_scheduleStartupTasks")]
		steps.append((jawsMigrator.updater.UpdateChecker, "scheduleAutomaticCheck"))
		saved = [(owner, name, getattr(owner, name)) for owner, name in steps]
		for owner, name in steps:
			setattr(owner, name, broken)
		try:
			loadsAnyway("with every other step of its start failing", layerSound.copyPath() if jawsSound else ("beep", 660, 40))
		finally:
			for owner, name, original in saved:
				setattr(owner, name, original)
	finally:
		frame.Destroy()
		shutil.rmtree(configDir, ignore_errors=True)
	print(f"{len(failures)} failed" if failures else "All checks passed")
	return 1 if failures else 0


if __name__ == "__main__":
	sys.exit(main())
