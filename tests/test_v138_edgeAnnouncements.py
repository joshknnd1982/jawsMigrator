# Unit tests for version 1.38, from a tester's log (issue 32, their comment of 28 September 2026 with NVDA's log of
# 10:55): "I can't find the edge settings". The assistant's answer had sent them to NVDA's Settings, "Microsoft Edge
# discard announcements" category. Opened from Edge at 10:53, NVDA's Settings had 49 categories and none of them was it:
# M went Magnifier, Mouse, Math, and Down Arrow from General went past where it would be. At 10:51:34, as the "Open"
# dialog they had attached their earlier log with closed, NVDA's log said "application msedge closed"
# (appModuleHandler.cleanup): that dialog's Edge process had ended.
# - edgeAnnouncements: after NVDA lets go of the app modules of processes that ended, the MS Edge Discard Announcements
#   add-on's category is put back while an Edge process with its app module still runs.
# The imitation NVDA is NVDA 2026.2's own appModuleHandler.cleanup, word for word (checked against release-2026.2 by
# NvdasOwnCodeTests when NVDA_SOURCE is set), and the add-on's AppModule.__init__ and terminate are MSEdgeDiscardAnnouncements
# 0.11.0's, word for word (checked when MSEDGE_DISCARD_SOURCE is set to a folder with its source). The assistant's code
# is the real one.
# Run: python -m unittest tests.test_v138_edgeAnnouncements -v

import ast
import os
import sys
import textwrap
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import edgeAnnouncements  # noqa: E402

#: NVDA 2026.2, source/appModuleHandler.py, cleanup, word for word.
NVDA_CLEANUP = r'''
def cleanup():
	"""Removes any appModules from the cache whose process has died."""
	for deadMod in [mod for mod in runningTable.values() if not mod.isAlive]:
		log.debug("application %s closed" % deadMod.appName)
		del runningTable[deadMod.processID]
		if deadMod in set(
			o.appModule for o in api.getFocusAncestors() + [api.getFocusObject()] if o and o.appModule
		):
			if hasattr(deadMod, "event_appLoseFocus"):
				deadMod.event_appLoseFocus()
		import eventHandler

		eventHandler.handleAppTerminate(deadMod)
		try:
			deadMod.terminate()
		except:  # noqa: E722
			log.exception("Error terminating app module %r" % deadMod)
'''

#: MSEdgeDiscardAnnouncements 0.11.0, addon/appModules/msedge/__init__.py, AppModule.__init__, word for word.
ADDON_INIT = r'''
def __init__(self, processID, appName):
    super().__init__(processID, appName)
    self.loadEventConfigs()
    categoryClasses = gui.settingsDialogs.NVDASettingsDialog.categoryClasses
    if MSEdgeDiscardAnnouncementsPanel not in categoryClasses:
        categoryClasses.append(MSEdgeDiscardAnnouncementsPanel)
'''

#: MSEdgeDiscardAnnouncements 0.11.0, addon/appModules/msedge/__init__.py, AppModule.terminate, word for word.
ADDON_TERMINATE = r'''
def terminate(self):
    super().terminate()
    categoryClasses = gui.settingsDialogs.NVDASettingsDialog.categoryClasses
    if MSEdgeDiscardAnnouncementsPanel in categoryClasses:
        gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(MSEdgeDiscardAnnouncementsPanel)
'''


class NVDASettingsDialog:
	#: The categories of NVDA's Settings, as NVDA 2026.2 has them before add-ons add theirs (the first few).
	categoryClasses = []


settingsDialogs = types.ModuleType("gui.settingsDialogs")
settingsDialogs.NVDASettingsDialog = NVDASettingsDialog
gui = types.ModuleType("gui")
gui.settingsDialogs = settingsDialogs


class MSEdgeDiscardAnnouncementsPanel:
	"""The add-on's panel: its title is its summary, "Microsoft Edge discard announcements"."""

	title = "Microsoft Edge discard announcements"


class GeneralSettingsPanel:
	title = "General"


class BaseAppModule:
	"""appModuleHandler.AppModule."""

	def __init__(self, processID, appName):
		self.processID = processID
		self.appName = appName
		self.alive = True

	@property
	def isAlive(self):
		return self.alive

	def terminate(self):
		pass


appModuleHandler = types.ModuleType("appModuleHandler")
appModuleHandler.AppModule = BaseAppModule
appModuleHandler.runningTable = {}
log = mock.Mock()
api = types.ModuleType("api")
api.getFocusAncestors = lambda: []
api.getFocusObject = lambda: None
eventHandler = types.ModuleType("eventHandler")
eventHandler.handleAppTerminate = lambda mod: None
_cleanupNamespace = {"runningTable": appModuleHandler.runningTable, "log": log, "api": api}
exec(NVDA_CLEANUP, _cleanupNamespace)
appModuleHandler.cleanup = _cleanupNamespace["cleanup"]
appModuleHandler.cleanup.__module__ = "appModuleHandler"

# The add-on's app module (appModules.msedge), with its own __init__ and terminate, in a class as the add-on has them
# (their super() needs it); its settings are left out.
_addonNamespace = {
	"appModuleHandler": appModuleHandler,
	"gui": gui,
	"MSEdgeDiscardAnnouncementsPanel": MSEdgeDiscardAnnouncementsPanel,
}
exec(
	"class AppModule(appModuleHandler.AppModule):\n"
	+ textwrap.indent(ADDON_INIT.strip(), "    ")
	+ "\n\n"
	+ textwrap.indent(ADDON_TERMINATE.strip(), "    ")
	+ "\n\n    def loadEventConfigs(self):\n        pass\n",
	_addonNamespace,
)
AppModule = _addonNamespace["AppModule"]
msedge = types.ModuleType("appModules.msedge")
msedge.AppModule = AppModule
msedge.MSEdgeDiscardAnnouncementsPanel = MSEdgeDiscardAnnouncementsPanel

#: What NVDA's builtin app module for Edge has without the add-on: no panel.
builtinMsedge = types.ModuleType("appModules.msedge")


class BuiltinAppModule(BaseAppModule):
	pass


builtinMsedge.AppModule = BuiltinAppModule


class _Stubbed(unittest.TestCase):
	module = msedge

	def setUp(self):
		patcher = mock.patch.dict(
			sys.modules,
			{
				"appModuleHandler": appModuleHandler,
				"gui": gui,
				"gui.settingsDialogs": settingsDialogs,
				"api": api,
				"eventHandler": eventHandler,
				"appModules.msedge": self.module,
			},
		)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(edgeAnnouncements.unregister)
		appModuleHandler.runningTable.clear()
		NVDASettingsDialog.categoryClasses[:] = [GeneralSettingsPanel]

	def start(self, processID, cls=AppModule):
		mod = cls(processID, "msedge")
		appModuleHandler.runningTable[processID] = mod
		return mod

	def categories(self):
		return [panel.title for panel in NVDASettingsDialog.categoryClasses]


class TheTestersLogTests(_Stubbed):
	def test_aFileDialogsProcessTookTheCategoryAway(self):
		# As the tester's NVDA had it: Edge's own process, and the one of the "Open" dialog they attached a file with.
		self.start(11472)
		dialog = self.start(20196)
		self.assertEqual(self.categories(), ["General", "Microsoft Edge discard announcements"])
		dialog.alive = False
		appModuleHandler.cleanup()
		log.debug.assert_called_with("application msedge closed")
		# Edge still runs, and its add-on's category is gone.
		self.assertEqual(list(appModuleHandler.runningTable), [11472])
		self.assertEqual(self.categories(), ["General"])


class KeepPanelTests(_Stubbed):
	def test_theCategoryStaysWhileEdgeRuns(self):
		edgeAnnouncements.register()
		self.start(11472)
		dialog = self.start(20196)
		dialog.alive = False
		appModuleHandler.cleanup()
		self.assertEqual(list(appModuleHandler.runningTable), [11472])
		self.assertEqual(self.categories(), ["General", "Microsoft Edge discard announcements"])
		# Once, not twice.
		appModuleHandler.cleanup()
		self.assertEqual(self.categories(), ["General", "Microsoft Edge discard announcements"])

	def test_goneWhenEdgeIsClosed(self):
		edgeAnnouncements.register()
		browser = self.start(11472)
		dialog = self.start(20196)
		browser.alive = dialog.alive = False
		appModuleHandler.cleanup()
		self.assertEqual(appModuleHandler.runningTable, {})
		self.assertEqual(self.categories(), ["General"])

	def test_putBackWhenTheAssistantStarts(self):
		# Lost before the assistant started (NVDA+Control+F3 reloads the plugins).
		self.start(11472)
		dialog = self.start(20196)
		dialog.alive = False
		appModuleHandler.cleanup()
		self.assertEqual(self.categories(), ["General"])
		edgeAnnouncements.register()
		self.assertEqual(self.categories(), ["General", "Microsoft Edge discard announcements"])

	def test_offLeavesNvdasOwn(self):
		original = vars(appModuleHandler)["cleanup"]
		edgeAnnouncements.register()
		installed = vars(appModuleHandler)["cleanup"]
		self.assertIsNot(installed, original)
		self.assertEqual(installed.__name__, "cleanup")
		edgeAnnouncements.register()
		self.assertIs(vars(appModuleHandler)["cleanup"], installed)
		edgeAnnouncements.unregister()
		self.assertIs(vars(appModuleHandler)["cleanup"], original)
		self.start(11472)
		dialog = self.start(20196)
		dialog.alive = False
		appModuleHandler.cleanup()
		self.assertEqual(self.categories(), ["General"])


class WithoutTheAddonTests(_Stubbed):
	module = builtinMsedge

	def test_nothingWithNvdasOwnAppModuleForEdge(self):
		edgeAnnouncements.register()
		self.start(11472, BuiltinAppModule)
		dialog = self.start(20196, BuiltinAppModule)
		dialog.alive = False
		appModuleHandler.cleanup()
		self.assertEqual(self.categories(), ["General"])
		self.assertFalse(edgeAnnouncements.keepPanel())


#: Where each piece of code above is: NVDA 2026.2's source (NVDA_SOURCE) or the add-on's (MSEDGE_DISCARD_SOURCE):
#: (variable, file, class or None for a function at the margin, function).
CODE = {
	"NVDA_CLEANUP": ("NVDA_SOURCE", "appModuleHandler.py", None, "cleanup"),
	"ADDON_INIT": ("MSEDGE_DISCARD_SOURCE", "addon/appModules/msedge/__init__.py", 'AppModule', "__init__"),
	"ADDON_TERMINATE": ("MSEDGE_DISCARD_SOURCE", "addon/appModules/msedge/__init__.py", 'AppModule', "terminate"),
}


def _find(path, className, name):
	with open(path, encoding="utf-8") as file:
		text = file.read()
	tree = ast.parse(text)
	body = tree.body
	if className is not None:
		body = next((node.body for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == className), [])
	for item in body:
		if isinstance(item, ast.FunctionDef) and item.name == name:
			return textwrap.dedent(ast.get_source_segment(text, item, padded=True))
	return ""


class CodeTests(unittest.TestCase):
	def test_theCodeIsNvdasAndTheAddons(self):
		checked = 0
		for name, (variable, path, className, function) in CODE.items():
			source = os.environ.get(variable)
			if not source:
				continue
			self.assertEqual(globals()[name].strip(), _find(os.path.join(source, path), className, function).strip(), name)
			checked += 1
		if not checked:
			self.skipTest("neither NVDA_SOURCE nor MSEDGE_DISCARD_SOURCE is set")


if __name__ == "__main__":
	unittest.main()
