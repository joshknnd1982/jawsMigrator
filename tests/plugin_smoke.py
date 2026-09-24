# Loads the global plugin the way NVDA does, with stand-ins for NVDA's modules and real wx menus,
# and checks what it adds: the Tools submenu, NVDA menu, Preferences, JAWS Migration Assistant
# settings, the Settings panel, the NVDA+Shift+J commands and their sound, the check that has NVDA
# say a control's type and state once; and that unloading takes it all away.
# Needs wxPython. NVDA's settings folder is a temporary one. JAWS's layered keystroke sound is read
# from this computer's JAWS, if there is one; nothing else is read or written.
# Run: python tests/plugin_smoke.py

import collections
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


def installSpeech():
	"""NVDA's speech extension points and control words, as far as the assistant uses them."""
	speech = types.ModuleType("speech")
	speech.extensions = types.ModuleType("speech.extensions")
	speech.extensions.filter_speechSequence = SpeechFilter()
	speech.speech = types.ModuleType("speech.speech")
	speech.speech.getPropertiesSpeech = lambda reason=None, **values: ["1 of 2"]
	controlTypes = types.ModuleType("controlTypes")
	controlTypes.Role = Labelled("Role", {"RADIOBUTTON": "radio button", "BUTTON": "button"})
	controlTypes.State = Labelled("State", {"CHECKED": "checked"})
	for module in (speech, speech.extensions, speech.speech, controlTypes):
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
		jawsMigrator.state.set(labelRepeats.STATE_KEY, False)
		plugin.applyRuntimeSettings()
		check(not labelRepeats.isRegistered() and list(speechFilter.handlers) == [otherAddon], "turned off in the Settings panel, NVDA's speech is left alone")
		jawsMigrator.state.set(labelRepeats.STATE_KEY, True)
		plugin.applyRuntimeSettings()
		check(labelRepeats.isRegistered(), "and on again")
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
			plugin.terminate()

		for name in ("layerSound", "labelRepeats"):
			delattr(jawsMigrator, name)
			sys.modules[f"jawsMigrator.{name}"] = None
		try:
			loadsAnyway("with modules NVDA can't load", ("beep", 660, 40))
		finally:
			for name in ("layerSound", "labelRepeats"):
				del sys.modules[f"jawsMigrator.{name}"]

		def broken(*args, **kwargs):
			raise RuntimeError("broken for the test")

		steps = [(jawsMigrator.GlobalPlugin, name) for name in ("applyRuntimeSettings", "_followConfigResets", "_scheduleStartupTasks")]
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
