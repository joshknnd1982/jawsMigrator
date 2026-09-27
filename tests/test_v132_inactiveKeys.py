# Unit tests for version 1.32, from a tester's issue 29 after version 1.30: "It has been more then a minute and insert
# control V still brings up NVDA speech settings." Their log (NVDA 2026.2, jawsMigrator 1.30, NVDA's laptop keyboard
# layout) showed why: newKeys wrote "not added: Control+JAWSKey+V=SayAppVersion [Common Keys]: your NVDA input gestures
# (gestures.ini) assign this keystroke to sayProductNameAndVersion, and a new gesture can't take their place". Their
# gestures.ini gives NVDA+Control+V to the add-on Say Product Name and Version 2026.4.16, and the log also says
# "Disabling add-on sayProductNameAndVersion": the add-on is off. NVDA passes over a binding for a global plugin that
# isn't running, so the key opened NVDA's speech settings, as every "Input: kb(laptop):control+NVDA+v" in the log did.
# - nvdaApply.gestureBoundScripts calls such a binding "inactive" (nvdaApply._inactiveBinding); keyPlan doesn't let it
#   keep the keystroke, and lets a JAWS command take NVDA's own command from under it: while it ran, the key wasn't
#   NVDA's command for that user.
# - newKeys plans 1.30's commands once more after the update, for a keystroke such a binding still holds.
# NVDA 2026.2's own scriptHandler and GlobalGestureMap run here, from test_v130_appVersion (checked word for word there,
# NvdasOwnCodeTests), with the keys as NVDA's laptop keyboard layout names them. What is imitated: the add-on Say
# Product Name and Version (its module, class and script name are the add-on's), the tester's Outlook, and NVDA's own
# NVDA+Control+V (its speech settings), as in test_v130_appVersion.
# Run: python -m unittest tests.test_v132_inactiveKeys -v

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v130_appVersion as v130  # noqa: E402

from jawsMigrator import gestureRepair, jawsFiles, keyPlan, migrator, newKeys, nvdaApply, state  # noqa: E402

#: What the tester's log said 1.30 did with Insert+Control+V.
TESTERS_LOG = (
	"not added: Control+JAWSKey+V=SayAppVersion [Common Keys]: your NVDA input gestures (gestures.ini) assign this keystroke "
	"to sayProductNameAndVersion, and a new gesture can't take their place"
)
#: The add-on's global plugin, as its gestures.ini binding names it (globalPlugins/sayProductNameAndVersion.py, class
#: GlobalPlugin, script_sayProductNameAndVersion; its own keystroke is NVDA+Shift+V).
ADDON = ("globalPlugins.sayProductNameAndVersion", "GlobalPlugin", "sayProductNameAndVersion")
#: What the tester heard in Outlook from Insert+Control+V, as JAWS says it.
OUTLOOK = "Microsoft Outlook Subscription Version 16.0.20326.20158"
ANNOUNCED = "JAWS Migration Assistant: 1 more JAWS keystroke works in NVDA. NVDA+control+v, the name and version of the program you are in; twice, the version details."


class LaptopKey(v130.Key):
	"""A key as NVDA's laptop keyboard layout gives it to scriptHandler: ``kb(laptop):`` first, then ``kb:``."""

	def __init__(self, gesture, normalize):
		super().__init__(gesture, normalize)
		main = gesture.split(":", 1)[1]
		self.normalizedIdentifiers = [normalize(f"kb(laptop):{main}"), normalize(f"kb:{main}")]


class LaptopConf(v130.Conf):
	def __getitem__(self, key):
		return {"keyboard": {"keyboardLayout": "laptop"}}[key]


def addonModule():
	"""The add-on, turned on: its module, whose global plugin says the version its own way."""
	module = types.ModuleType(ADDON[0])

	class GlobalPlugin(sys.modules["globalPluginHandler"].GlobalPlugin):
		def __init__(self):
			super().__init__()
			self.pressed = 0
			self._gestureMap = {"kb:nvda+shift+v": self.script_sayProductNameAndVersion}

		def script_sayProductNameAndVersion(self, gesture):
			self.pressed += 1

	GlobalPlugin.__module__ = ADDON[0]
	module.GlobalPlugin = GlobalPlugin
	return module


class TestersCase(v130.KeysCase):
	"""The tester's NVDA as 1.30 left it: the add-on's binding, the add-on off, NVDA's laptop layout."""

	def setUp(self):
		super().setUp()
		self.said = []
		self.done = []
		self.backups = []
		sys.modules["config"].conf = LaptopConf(profiles=[types.SimpleNamespace(name=None)])
		# NVDA's running global plugins: scriptHandler asks them, and the assistant looks at them.
		self.running = self.scriptHandler.globalPluginHandler.runningPlugins
		patcher = mock.patch.object(sys.modules["globalPluginHandler"], "runningPlugins", self.running, create=True)
		patcher.start()
		self.addCleanup(patcher.stop)

		def backupFirst(reason):
			self.backups.append(reason)
			return types.SimpleNamespace(path="backup")

		class Thread:
			# The backup runs at once here, where NVDA runs it in the background.
			def __init__(self, target, name=None, daemon=None):
				self.target = target

			def start(self):
				self.target()

		for patcher in (
			mock.patch.object(migrator, "_backupFirst", side_effect=backupFirst),
			mock.patch.object(newKeys.threading, "Thread", Thread),
			mock.patch("wx.CallAfter", side_effect=lambda function, *args: function(*args)),
			mock.patch.object(newKeys.nvdaEnv, "shouldWriteToDisk", return_value=True),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def giveTheKeyToTheAddOn(self, identifier="kb:NVDA+control+v"):
		self.userMap.add(identifier, *ADDON)

	def as130LeftIt(self, overrideConflicts=False, layouts=("laptop",)):
		"""state.json and gestures.ini after 1.30's newKeys, as the tester's log shows it."""
		state.set("lastMigration", {"when": "2026-09-23T20:43:59", "keyboardLayouts": list(layouts), "overrideConflicts": overrideConflicts})
		state.set(newKeys.STATE_KEY, sorted(newKeys.NEW_SCRIPTS))
		self.userMap.add("kb:NVDA+control+windows+v", "globalPlugins.jawsMigrator", "GlobalPlugin", "copyVersionDetails")

	def addOnce(self, jawsLayout="laptop", text=v130.JAWS_KEYS):
		newKeys.addOnce(lambda: (jawsFiles.parseIni(text), jawsLayout), self.said.append, lambda: self.done.append(True))

	def press(self, gesture):
		key = LaptopKey(gesture, self.normalize)
		script = self.scriptHandler._findScript(key)
		self.assertIsNotNone(script, gesture)
		self.scriptHandler.executeScript(script, key)
		return script

	def bound(self, gesture="kb:NVDA+control+v"):
		return [entry for entry in self.userMap._map.get(self.normalize(gesture), [])]

	def fresh(self, again: bool) -> None:
		"""A new start for the next round of a loop: the first round has setUp's own."""
		if again:
			self.doCleanups()
			self.setUp()

	def turnOn(self):
		"""The add-on turned on: NVDA imports it and runs its global plugin."""
		module = addonModule()
		patcher = mock.patch.dict(sys.modules, {ADDON[0]: module})
		patcher.start()
		self.addCleanup(patcher.stop)
		plugin = module.GlobalPlugin()
		self.running.insert(0, plugin)
		self.addCleanup(self.running.remove, plugin)
		return plugin


class TestersNvdaTests(TestersCase):
	def test_whatTheTesterHad(self):
		# NVDA passes over the add-on's binding: Insert+Control+V opens NVDA's speech settings, as in the tester's log.
		self.giveTheKeyToTheAddOn()
		self.as130LeftIt()
		self.press("kb:NVDA+control+v")
		self.assertEqual(self.commands.opened, ["speech settings"])
		self.assertEqual(self.nvda.said(), [])
		# 1.30 took the binding for the tester's own: the same words as their log.
		with mock.patch.object(nvdaApply, "_inactiveBinding", return_value=False):
			plan = self.plan(layout="laptop")
		skipped = [item for item in plan.skipped if item.jawsScript == "SayAppVersion"]
		self.assertEqual([f"not added: {item.jawsKey}={item.jawsScript} [{item.section}]: {item.reason}" for item in skipped], [TESTERS_LOG])

	def test_afterTheUpdate(self):
		for overrideConflicts in (False, True):
			with self.subTest(overrideConflicts=overrideConflicts):
				self.fresh(overrideConflicts)
				try:
					self.giveTheKeyToTheAddOn()
					self.as130LeftIt(overrideConflicts)
					self.addOnce()
					self.assertEqual(self.said, [ANNOUNCED])
					self.assertEqual(self.done, [True])
					self.assertEqual(len(self.backups), 1)
					self.assertEqual(self.bound(), [ADDON, ("globalPlugins.jawsMigrator", "GlobalPlugin", "sayAppVersion")])
					self.assertTrue(state.get(newKeys.RECHECK_KEY))
					# Insert+Control+V says the version, as in JAWS...
					script = self.press("kb:NVDA+control+v")
					self.assertEqual(script.__name__, "script_sayAppVersion")
					self.assertEqual(self.nvda.said(), [OUTLOOK])
					# ... pressed twice, it shows the version details...
					self.press("kb:NVDA+control+v")
					self.assertEqual([title for _message, title, _close, _copy in self.shown], ["Version Details"])
					self.assertEqual(self.commands.opened, [])
					# ... and once only.
					self.addOnce()
					self.assertEqual((len(self.said), len(self.backups), self.done), (1, 1, [True, True]))
				finally:
					self.doCleanups()

	def test_aBindingForTheLaptopLayoutOnly(self):
		self.giveTheKeyToTheAddOn("kb(laptop):NVDA+control+v")
		self.as130LeftIt()
		self.addOnce()
		self.assertEqual(self.said, [ANNOUNCED.replace("NVDA+control+v,", "NVDA+control+v, only in NVDA's laptop keyboard layout,")])
		self.assertEqual(self.userMap._map[self.normalize("kb(laptop):NVDA+control+v")][-1], ("globalPlugins.jawsMigrator", "GlobalPlugin", "sayAppVersion"))
		self.press("kb:NVDA+control+v")
		self.assertEqual(self.nvda.said(), [OUTLOOK])

	def test_theDebugLog(self):
		notes = []
		self.giveTheKeyToTheAddOn()
		self.as130LeftIt()
		with mock.patch.object(newKeys.debugLog, "note", side_effect=notes.append):
			self.addOnce()
		self.assertIn("planned again, for a keystroke gestures.ini gives to an add-on that is off: putversiondetailsonclipboard, sayappversion, showversiondetails", notes)
		self.assertIn(
			"kb:NVDA+control+v -> globalPlugins.jawsMigrator.GlobalPlugin.sayAppVersion (JAWS Control+JAWSKey+V=SayAppVersion, [Common Keys]); gestures.ini "
			"also gives it to globalPlugins.sayProductNameAndVersion.GlobalPlugin.sayProductNameAndVersion, which NVDA passes over: its add-on is off or removed",
			notes,
		)
		# What 1.30 decided otherwise is not listed again.
		self.assertFalse([note for note in notes if note.startswith("not added")])

	@v130.needsJaws
	def test_jawsDefaultKeyMap(self):
		with open(os.path.join(v130.JAWS_SCRIPTS, "enu", "Default.JKM"), encoding="utf-8-sig", errors="replace") as f:
			text = f.read()
		for layouts in (("laptop",), ("desktop",), ("desktop", "laptop")):
			with self.subTest(layouts=layouts):
				self.fresh(layouts != ("laptop",))
				try:
					self.giveTheKeyToTheAddOn()
					self.as130LeftIt(layouts=layouts)
					self.addOnce(jawsLayout=layouts[0], text=text)
					self.assertEqual(self.said, [ANNOUNCED])
					self.press("kb:NVDA+control+v")
					self.assertEqual(self.nvda.said(), [OUTLOOK])
				finally:
					self.doCleanups()


class OtherNvdaTests(TestersCase):
	def test_theAddOnTurnedOn(self):
		# A binding that runs stays yours: the add-on says the version its own way.
		plugin = self.turnOn()
		self.giveTheKeyToTheAddOn()
		self.as130LeftIt(overrideConflicts=True)
		self.addOnce()
		self.assertEqual((self.said, self.backups, self.done), ([], [], [True]))
		self.assertEqual(self.bound(), [ADDON])
		self.press("kb:NVDA+control+v")
		self.assertEqual((plugin.pressed, self.commands.opened), (1, []))
		plan = self.plan(layout="laptop", overrideConflicts=True)
		skipped = [item for item in plan.skipped if item.jawsScript == "SayAppVersion"]
		self.assertEqual([item.reason for item in skipped], [TESTERS_LOG.split(": ", 2)[2]])

	def test_aScriptTheAddOnNoLongerHas(self):
		# The add-on is on, but its binding names a script it doesn't have: NVDA goes on to its own command.
		self.turnOn()
		self.userMap.add("kb:NVDA+control+v", ADDON[0], ADDON[1], "sayVersionTheOldWay")
		self.press("kb:NVDA+control+v")
		self.assertEqual(self.commands.opened, ["speech settings"])
		self.as130LeftIt()
		self.addOnce()
		self.assertEqual(self.said, [ANNOUNCED])

	def test_alreadyAddedBy130(self):
		self.giveTheKeyToTheAddOn()
		self.as130LeftIt(overrideConflicts=True)
		self.userMap.add("kb:NVDA+control+v", "globalPlugins.jawsMigrator", "GlobalPlugin", "sayAppVersion")
		self.addOnce()
		self.assertEqual((self.said, self.backups, self.done), ([], [], [True]))
		self.assertTrue(state.get(newKeys.RECHECK_KEY))

	def test_aKeyYouTookAwayStaysAway(self):
		# 1.30 added Insert+Control+V, and it was taken off it since: with no inactive binding there, 1.32 leaves it.
		self.as130LeftIt(overrideConflicts=True)
		self.addOnce()
		self.assertEqual((self.said, self.backups, self.done), ([], [], [True]))
		self.press("kb:NVDA+control+v")
		self.assertEqual(self.commands.opened, ["speech settings"])

	def test_yourOwnCommandStays(self):
		self.giveTheKeyToTheAddOn()
		self.userMap.add("kb:NVDA+control+v", "globalCommands", "GlobalCommands", "reportCurrentLine")
		self.as130LeftIt(overrideConflicts=True)
		self.addOnce()
		self.assertEqual(self.said, [])
		self.assertNotIn(("globalPlugins.jawsMigrator", "GlobalPlugin", "sayAppVersion"), self.bound())

	def test_anotherAddOnsKeystroke(self):
		# A running add-on that binds NVDA+Control+V itself keeps it, unless NVDA's keystrokes may be taken.
		class GlobalPlugin(sys.modules["globalPluginHandler"].GlobalPlugin):
			def script_mine(self, gesture):
				pass

		GlobalPlugin.__module__ = "globalPlugins.other"
		other = GlobalPlugin()
		other._gestureMap = {"kb:nvda+control+v": other.script_mine}
		self.running.append(other)
		self.addCleanup(self.running.remove, other)
		self.giveTheKeyToTheAddOn()
		self.as130LeftIt(overrideConflicts=False)
		self.addOnce()
		self.assertEqual(self.said, [])
		plan = self.plan(layout="laptop", overrideConflicts=True)
		self.assertEqual([b.unbind for b in plan.bindings if b.script == "sayAppVersion"], [[("globalPlugins.other", "GlobalPlugin")]])

	def test_anUnbindingOfAnAddOnThatIsOff(self):
		# Taking a keystroke from an add-on gives it back to NVDA, not to the JAWS command.
		self.userMap.add("kb:NVDA+control+v", ADDON[0], ADDON[1], None)
		plan = self.plan(layout="laptop")
		self.assertEqual([b.script for b in plan.bindings if b.script == "sayAppVersion"], [])

	def test_aFirstUpdateFrom129(self):
		# Nothing added yet: newKeys plans all three, and the add-on's binding doesn't keep the key.
		self.giveTheKeyToTheAddOn()
		state.set("lastMigration", {"when": "2026-09-23T20:43:59", "keyboardLayouts": ["laptop"], "overrideConflicts": False})
		self.addOnce()
		self.assertEqual(
			self.said,
			[
				"JAWS Migration Assistant: 2 more JAWS keystrokes work in NVDA. NVDA+control+v, the name and version of the program you "
				"are in; twice, the version details. NVDA+control+windows+v, copy the version details.",
			],
		)
		self.assertEqual(newKeys.pending(state.load()), [])
		self.assertEqual(newKeys.toRecheck(state.load()), [])

	def test_aMigration(self):
		# A migration made now plans it the same way, and counts the recheck done.
		self.giveTheKeyToTheAddOn()
		plan = self.plan(layout="laptop")
		self.assertEqual([(b.gesture, b.replaces) for b in plan.bindings if b.script == "sayAppVersion"], [("kb:NVDA+control+v", ["activateVoiceDialog"])])
		with open(migrator.__file__, encoding="utf-8") as f:
			self.assertIn("updates[newKeys.RECHECK_KEY] = True", f.read())
		self.assertIs(state.DEFAULTS[newKeys.RECHECK_KEY], False)
		state.set(newKeys.STATE_KEY, sorted(newKeys.NEW_SCRIPTS))
		self.assertEqual(newKeys.toRecheck(state.load()), sorted(newKeys.RECHECKED))
		state.set(newKeys.RECHECK_KEY, True)
		state.forget()
		self.assertEqual(newKeys.toRecheck(state.load()), [])

	def test_noMigratedKeystrokes(self):
		self.giveTheKeyToTheAddOn()
		state.set("lastMigration", {"when": "2026-09-23T20:43:59", "keyboardLayouts": [], "overrideConflicts": False})
		state.set(newKeys.STATE_KEY, sorted(newKeys.NEW_SCRIPTS))
		self.addOnce()
		self.assertEqual((self.said, self.backups, self.done), ([], [], [True]))
		self.assertTrue(state.get(newKeys.RECHECK_KEY))

	def test_aFailedBackupTriesAgain(self):
		self.giveTheKeyToTheAddOn()
		self.as130LeftIt()
		with mock.patch.object(migrator, "_backupFirst", side_effect=OSError("disk full")):
			self.addOnce()
		self.assertEqual(self.said, [])
		self.assertFalse(state.get(newKeys.RECHECK_KEY))
		self.addOnce()
		self.assertEqual(self.said, [ANNOUNCED])


class InactiveBindingTests(TestersCase):
	def test_whatNvdaPassesOver(self):
		inactive = nvdaApply._inactiveBinding
		# The add-on is off: NVDA hasn't loaded its module.
		self.assertTrue(inactive(*ADDON))
		self.assertTrue(inactive(ADDON[0], ADDON[1], None))
		# Loaded, but not running (its plugin failed to start).
		with mock.patch.dict(sys.modules, {ADDON[0]: addonModule()}):
			self.assertTrue(inactive(*ADDON))
		plugin = self.turnOn()
		self.assertFalse(inactive(*ADDON))
		self.assertFalse(inactive(ADDON[0], ADDON[1], None))
		self.assertFalse(inactive(ADDON[0], ADDON[1], "kb:NVDA+shift+v"))
		self.assertTrue(inactive(ADDON[0], ADDON[1], "noSuchScript"))
		self.assertTrue(inactive(ADDON[0], "OtherClass", ADDON[2]))
		self.assertEqual(plugin.pressed, 0)
		# The assistant's own, NVDA's classes and app modules, which NVDA loads later, count as they are.
		self.assertFalse(inactive("globalPlugins.jawsMigrator", "GlobalPlugin", "sayAppVersion"))
		self.assertFalse(inactive("globalCommands", "GlobalCommands", "activateVoiceDialog"))
		self.assertFalse(inactive("appModules.outlook", "AppModule", "anything"))
		# Where the running plugins can't be read, nothing is passed over.
		with mock.patch.dict(sys.modules, {"globalPluginHandler": types.SimpleNamespace()}):
			self.assertFalse(inactive("globalPlugins.gone", "GlobalPlugin", "x"))

	def test_theSourceIsInactive(self):
		self.giveTheKeyToTheAddOn()
		found = nvdaApply.gestureBoundScripts("kb(laptop):NVDA+control+v")
		self.assertIn((*ADDON, "kb:control+nvda+v", keyPlan.INACTIVE), found)
		self.turnOn()
		self.assertIn((*ADDON, "kb:control+nvda+v", "user"), nvdaApply.gestureBoundScripts("kb(laptop):NVDA+control+v"))

	def test_theRepairDoesntCountIt(self):
		self.giveTheKeyToTheAddOn()
		binding = ("kb:NVDA+control+v", "globalPlugins.jawsMigrator", "GlobalPlugin", "sayAppVersion")
		taken = gestureRepair._takenCommands(binding, nvdaApply.gestureBoundScripts, set())
		self.assertEqual(taken, {layout: ["activateVoiceDialog"] for layout in taken})
		self.assertNotIn("sayProductNameAndVersion", str(taken))


if __name__ == "__main__":
	unittest.main()
