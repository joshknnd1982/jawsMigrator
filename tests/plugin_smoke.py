# Loads the global plugin the way NVDA does, with stand-ins for NVDA's modules and real wx menus,
# and checks what it adds: the Tools submenu, NVDA menu, Preferences, JAWS Migration Assistant
# settings, the Settings panel, the NVDA+Shift+J commands; and that unloading takes it all away.
# Needs wxPython. NVDA's settings folder is a temporary one; nothing else is read or written.
# Run: python tests/plugin_smoke.py

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
		import jawsMigrator

		# Only the menus are wanted here, not the first-run offer or the update check.
		jawsMigrator.state.set("welcomeShown", True)
		jawsMigrator.state.set("checkForUpdatesAutomatically", False)
		plugin = jawsMigrator.GlobalPlugin()
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
	finally:
		frame.Destroy()
		shutil.rmtree(configDir, ignore_errors=True)
	print(f"{len(failures)} failed" if failures else "All checks passed")
	return 1 if failures else 0


if __name__ == "__main__":
	sys.exit(main())
