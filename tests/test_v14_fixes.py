# Unit tests for the fixes of version 1.4, from a tester's report on version 1.3:
# - no sound when NVDA exits (Screen Curtain's off sound) after a migration (exitSounds);
# - Insert+J opens the NVDA menu in the JAWS Laptop layout, where Caps Lock+J says the previous word
#   (keyPlan.InsertKey, insertKeys, and other add-ons' keystrokes in nvdaApply.gestureBoundScripts);
# - "6:02 PM" is read as a time, not "6 colon 02" (numberSymbols);
# - JAWS's Eloquence rate keeps its speed in NVDA (voices.eciRatePercent, rateRepair);
# - the restore dialog says what comes back, such as "clickable" on web pages (restorePreview).
# Run: python -m unittest tests.test_v14_fixes -v

import collections
import dataclasses
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import (  # noqa: E402
	exitSounds,
	insertKeys,
	jawsFiles,
	keyPlan,
	nvdaApply,
	numberSymbols,
	rateRepair,
	restorePreview,
	voices,
)

VK_INSERT = 0x2D
VK_CAPITAL = 0x14
WAVES = r"C:\Program Files\NVDA\waves"

LAPTOP_JKM = (
	"[Keyboard Layouts]\nDesktop=Common\nLaptop=Common\n"
	"[Common Keys]\nJAWSKey+H=HotKeyHelp\nJAWSKey+J=JAWSWindow\nJAWSKey+T=SayWindowTitle\n"
	"[Laptop Keys]\nJAWSKey+H=SaySentence\nInsert+h=HotKeyHelp\nInsert+H=HotKeyHelp\nJAWSKey+J=SayPriorWord\nInsert+J=JAWSWindow\n"
	"[Classic Laptop Keys]\nJAWSKey+T=JAWSWindow\n"
	"[Laptop Modifiers]\nCapsLock=14|3|0|0|0|0|0x4000\n[Desktop Modifiers]\nInsert=17|3|0|2|0|0|0x4020800\n"
	"[Classic Laptop Modifiers]\nInsert=17|3|0|2|0|0|0x4020800\n"
)


def _jkm(text: str) -> jawsFiles.IniFile:
	folder = tempfile.mkdtemp()
	path = os.path.join(folder, "Default.jkm")
	with open(path, "w", encoding="utf-8") as stream:
		stream.write(text)
	return jawsFiles.readIni(path)


# -- the exit sound ---------------------------------------------------------------------------


class ExitSoundTests(unittest.TestCase):
	def test_recognises_nvdas_screen_curtain_off_sound(self):
		self.assertTrue(exitSounds.isScreenCurtainOffSound(os.path.join(WAVES, "screenCurtainOff.wav"), WAVES))
		self.assertTrue(exitSounds.isScreenCurtainOffSound(r"waves\screenCurtainOff.wav", WAVES))
		self.assertTrue(exitSounds.isScreenCurtainOffSound("waves/SCREENCURTAINOFF.WAV", WAVES))
		self.assertFalse(exitSounds.isScreenCurtainOffSound(os.path.join(WAVES, "screenCurtainOn.wav"), WAVES))
		self.assertFalse(exitSounds.isScreenCurtainOffSound(os.path.join(WAVES, "exit.wav"), WAVES))
		# A scheme's own sound of that name is not NVDA's.
		self.assertFalse(exitSounds.isScreenCurtainOffSound(r"C:\Users\me\AppData\Roaming\nvda\ClassicSpeech\Schemes\JAWS\Sounds\screenCurtainOff.wav", WAVES))
		self.assertFalse(exitSounds.isScreenCurtainOffSound(None, WAVES))

	def test_only_after_a_migration_with_the_exit_sound_off(self):
		migrated = {"lastMigration": {"when": "2026-09-23T18:00:00"}}
		self.assertTrue(exitSounds.wanted(migrated, soundsOff=True))
		self.assertFalse(exitSounds.wanted(migrated, soundsOff=False))
		self.assertFalse(exitSounds.wanted({"lastMigration": {}}, soundsOff=True))
		sounds = {"classicNvdaSounds": {"schemes": {"JAWS": {"items": {"nvdaSound.browseMode": {}}}}}}
		self.assertTrue(exitSounds.wanted(sounds, soundsOff=True))

	def test_leaves_out_only_the_screen_curtain_sound(self):
		played = []
		nvwave = types.SimpleNamespace(playWaveFile=lambda fileName, asynchronous=True, isSpeechWaveFileCommand=False: played.append(fileName))
		self.assertTrue(exitSounds.silenceWhileExiting(WAVES, nvwave))
		nvwave.playWaveFile(os.path.join(WAVES, "screenCurtainOff.wav"))
		nvwave.playWaveFile(fileName=os.path.join(WAVES, "screenCurtainOff.wav"), asynchronous=False)
		nvwave.playWaveFile(os.path.join(WAVES, "exit.wav"), asynchronous=False)
		nvwave.playWaveFile(r"C:\Users\me\Sounds\BlindsUpOnly.wav")
		self.assertEqual(played, [os.path.join(WAVES, "exit.wav"), r"C:\Users\me\Sounds\BlindsUpOnly.wav"])
		wrapper = nvwave.playWaveFile
		self.assertTrue(exitSounds.silenceWhileExiting(WAVES, nvwave))
		self.assertIs(nvwave.playWaveFile, wrapper, "wrapped once")


# -- Insert and Caps Lock keystrokes -----------------------------------------------------------


def _plan(text=LAPTOP_JKM, layout="laptop", nvdaLayout="laptop", boundScripts=None, overrideConflicts=False, layouts=None):
	return keyPlan.planKeys(
		_jkm(text),
		layout,
		boundScripts=boundScripts,
		scriptExists=None,
		overrideConflicts=overrideConflicts,
		layouts=layouts,
		nvdaLayout=nvdaLayout,
	)


def _bound(entries):
	"""A boundScripts function answering ``{gesture keys: [(module, class, script, identifier, source)]}``."""

	def boundScripts(gesture):
		wanted = nvdaApply._splitGesture(gesture)[1]
		return [entry for keys, found in entries.items() if keys == wanted for entry in found]

	return boundScripts


class InsertKeyPlanTests(unittest.TestCase):
	def test_insert_j_opens_the_nvda_menu_and_caps_lock_j_keeps_its_command(self):
		plan = _plan()
		keys = {key.jawsKey.lower(): key for key in plan.insertKeys}
		self.assertEqual(len(plan.insertKeys), 2, "Insert+h and Insert+H are one keystroke")
		self.assertEqual(set(keys), {"insert+h", "insert+j"})
		key = keys["insert+j"]
		self.assertEqual((key.gesture, key.module, key.className, key.script), ("kb(laptop):NVDA+j", "globalCommands", "GlobalCommands", "showGui"))
		self.assertEqual((key.capsLockKey, key.capsLockScript), ("JAWSKey+J", "SayPriorWord"))
		self.assertIn("with Insert", key.label)
		# Caps Lock+J keeps the gesture: nothing is bound, as NVDA has no "say prior word".
		self.assertFalse([binding for binding in plan.bindings if binding.gesture.lower().endswith("nvda+j")])

	def test_only_for_the_layout_that_uses_caps_lock(self):
		desktop = _plan(layout="desktop", nvdaLayout="desktop")
		self.assertEqual(desktop.insertKeys, [])
		# Classic Laptop's JAWS key is Insert, and its keystrokes don't work in the Laptop layout.
		both = _plan(layouts=["laptop", "classic laptop"])
		self.assertNotIn("JAWSKey+T", [key.jawsKey for key in both.insertKeys])

	def test_the_users_own_gesture_wins(self):
		bound = _bound({"j+nvda": [("globalCommands", "GlobalCommands", "reportCurrentFocus", "kb:NVDA+j", "user")]})
		plan = _plan(boundScripts=bound)
		self.assertNotIn("Insert+J", [key.jawsKey for key in plan.insertKeys])
		reason = [item for item in plan.skipped if item.jawsKey == "Insert+J"][0]
		self.assertEqual(reason.kind, keyPlan.SKIP_CONFLICT)
		self.assertIn("your NVDA input gestures", reason.reason)

	def test_another_addons_keystroke_is_not_taken(self):
		bound = _bound({"j+nvda": [("globalPlugins.goldenCursor", "GlobalPlugin", "jumpToPosition", "kb:NVDA+j", "addon")]})
		plan = _plan(boundScripts=bound)
		self.assertNotIn("Insert+J", [key.jawsKey for key in plan.insertKeys])
		reason = [item for item in plan.skipped if item.jawsKey == "Insert+J"][0]
		self.assertIn("goldenCursor", reason.reason)

	def test_nvdas_own_command_only_when_asked(self):
		bound = _bound({"j+nvda": [("globalCommands", "GlobalCommands", "reportAppModuleInfo", "kb(laptop):NVDA+j", "class")]})
		kept = _plan(boundScripts=bound)
		self.assertNotIn("Insert+J", [key.jawsKey for key in kept.insertKeys])
		taken = _plan(boundScripts=bound, overrideConflicts=True)
		key = [key for key in taken.insertKeys if key.jawsKey == "Insert+J"][0]
		self.assertEqual(key.replaces, ["reportAppModuleInfo"])

	def test_the_assistants_caps_lock_binding_is_not_a_conflict(self):
		# A repair after version 1.3: gestures.ini already has the Caps Lock command the migration bound.
		text = LAPTOP_JKM.replace("JAWSKey+J=SayPriorWord", "JAWSKey+J=LeftMouseButton")
		bound = _bound({"j+nvda": [("globalCommands", "GlobalCommands", "leftMouseClick", "kb(laptop):NVDA+j", "user")]})
		plan = _plan(text, boundScripts=bound)
		key = [key for key in plan.insertKeys if key.jawsKey == "Insert+J"][0]
		self.assertEqual(key.script, "showGui")

	def test_conflicts_name_the_other_addon_and_unbind_it_when_asked(self):
		text = "[Common Keys]\nJAWSKey+T=SayWindowTitle\n"
		bound = _bound({"nvda+t": [("globalPlugins.windowState", "GlobalPlugin", "announce", "kb:NVDA+t", "addon")]})
		plan = _plan(text, layout="desktop", nvdaLayout="desktop", boundScripts=bound)
		reason = [item for item in plan.skipped if item.jawsKey == "JAWSKey+T"][0]
		self.assertIn("the add-on windowState (announce)", reason.reason)
		plan = _plan(text, layout="desktop", nvdaLayout="desktop", boundScripts=bound, overrideConflicts=True)
		binding = plan.bindings[0]
		self.assertIn(("globalPlugins.windowState", "GlobalPlugin"), binding.unbind)

	def test_describe_gesture(self):
		self.assertEqual(keyPlan.describeGesture("kb:NVDA+j"), "NVDA+j")
		self.assertEqual(keyPlan.describeGesture("kb(desktop):NVDA+j"), "NVDA+j, only in NVDA's desktop keyboard layout")


class AddonPluginGestureTests(unittest.TestCase):
	def test_other_addons_are_listed_and_this_one_is_not(self):
		def script_jumpToPosition(self, gesture):
			pass

		def script_commandLayer(self, gesture):
			pass

		other = type("GlobalPlugin", (), {"__module__": "globalPlugins.goldenCursor"})()
		other._gestureMap = {"kb:j+nvda": script_jumpToPosition, "kb:nvda+x": None}
		mine = type("GlobalPlugin", (), {"__module__": nvdaApply.__package__})()
		mine._gestureMap = {"kb:j+nvda": script_commandLayer}
		fake = types.SimpleNamespace(runningPlugins={other, mine})
		with mock.patch.dict(sys.modules, {"globalPluginHandler": fake}):
			found = nvdaApply._addonPluginGestures("kb(laptop):NVDA+j")
		self.assertEqual(found, [("globalPlugins.goldenCursor", "GlobalPlugin", "jumpToPosition", "kb:j+nvda", "addon")])


def _gesture(modifier, identifiers):
	return types.SimpleNamespace(modifiers={(modifier, True)}, normalizedIdentifiers=list(identifiers))


class InsertKeyRuntimeTests(unittest.TestCase):
	def setUp(self):
		keyboardHandler = types.SimpleNamespace(isNVDAModifierKey=lambda vk, extended: vk in (VK_INSERT, VK_CAPITAL))
		winUser = types.SimpleNamespace(VK_INSERT=VK_INSERT)
		patcher = mock.patch.dict(sys.modules, {"keyboardHandler": keyboardHandler, "winUser": winUser})
		patcher.start()
		self.addCleanup(patcher.stop)
		key = keyPlan.InsertKey("kb(laptop):NVDA+j", "globalCommands", "GlobalCommands", "showGui", "Open the NVDA menu", "Insert+J", "JAWSWindow", "Laptop Keys", "JAWSKey+J", "SayPriorWord")
		self.table = insertKeys.load({"insertKeys": insertKeys.toState([key], lambda gesture: ["globalCommands.GlobalCommands.leftMouseClick"])})

	def test_table_round_trip(self):
		self.assertEqual(list(self.table), ["kb(laptop):j+nvda"])
		self.assertEqual(self.table["kb(laptop):j+nvda"]["userScripts"], ["globalCommands.GlobalCommands.leftMouseClick"])
		self.assertEqual(insertKeys.load({"insertKeys": {"kb:x": {"gesture": "kb:x"}}}), {}, "incomplete entries are dropped")
		self.assertEqual(insertKeys.load({"insertKeys": []}), {})

	def test_only_with_insert(self):
		identifiers = ("kb(laptop):j+nvda", "kb:j+nvda")
		self.assertIsNotNone(insertKeys.entryFor(_gesture(VK_INSERT, identifiers), self.table))
		self.assertIsNone(insertKeys.entryFor(_gesture(VK_CAPITAL, identifiers), self.table))
		self.assertIsNone(insertKeys.entryFor(_gesture(VK_INSERT, ("kb(desktop):j+nvda", "kb:j+nvda")), self.table))
		self.assertIsNone(insertKeys.entryFor(types.SimpleNamespace(normalizedIdentifiers=list(identifiers)), self.table), "not a keyboard gesture")

	def test_a_new_user_gesture_wins(self):
		entry = self.table["kb(laptop):j+nvda"]
		self.assertFalse(insertKeys.userChanged(entry, ["globalCommands.GlobalCommands.leftMouseClick"]))
		self.assertFalse(insertKeys.userChanged(entry, []))
		self.assertTrue(insertKeys.userChanged(entry, ["globalCommands.GlobalCommands.reportCurrentFocus"]))

	def test_resolves_like_nvda(self):
		class GlobalCommands:
			def script_showGui(self, gesture):
				return "menu"

		class BrowseModeTreeInterceptor:
			passThrough = False

			def script_nextHeading(self, gesture):
				return "heading"

		commands = GlobalCommands()
		document = BrowseModeTreeInterceptor()
		focus = types.SimpleNamespace(treeInterceptor=document)
		modules = {
			"api": types.SimpleNamespace(getFocusObject=lambda: focus, getFocusAncestors=lambda: []),
			"globalCommands": types.SimpleNamespace(GlobalCommands=GlobalCommands, commands=commands),
			"browseMode": types.SimpleNamespace(BrowseModeTreeInterceptor=BrowseModeTreeInterceptor),
		}
		with mock.patch.dict(sys.modules, modules):
			self.assertEqual(insertKeys.resolve({"module": "globalCommands", "className": "GlobalCommands", "script": "showGui"})(None), "menu")
			entry = {"module": "browseMode", "className": "BrowseModeTreeInterceptor", "script": "nextHeading"}
			self.assertEqual(insertKeys.resolve(entry)(None), "heading")
			document.passThrough = True
			self.assertIsNone(insertKeys.resolve(entry), "in focus mode, NVDA doesn't run browse mode commands either")


# -- a colon between digits --------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, kw_only=True)
class _FakeDefinition:
	name: str
	path: str
	source: str = "builtin"
	displayName: str | None = None
	allowComplexSymbols: bool = False
	mandatory: bool = False
	symbols: dict = dataclasses.field(init=False, repr=False, compare=False, default=None)

	def __post_init__(self):
		object.__setattr__(self, "symbols", {})

	@property
	def availableLocales(self):
		return {"en": "en", "de": "de"}

	def getSymbols(self, locale):
		if locale not in self.symbols:
			self.symbols[locale] = self._initSymbols(locale)
		return self.symbols[locale]

	def _initSymbols(self, locale):
		if locale not in self.availableLocales:
			raise FileNotFoundError(locale)
		symbols = _FakeSymbols()
		symbols.symbols[":"] = _FakeSymbol(":", None, {"en": "colon", "de": "Doppelpunkt"}[locale])
		return symbols


class _FakeSymbols:
	def __init__(self, filename=None):
		self.complexSymbols = collections.OrderedDict()
		self.symbols = collections.OrderedDict()


@dataclasses.dataclass
class _FakeSymbol:
	identifier: str
	pattern: str | None = None
	replacement: str | None = None
	level: int | None = None
	preserve: int | None = None
	displayName: str | None = None


def _fakeCharacterProcessing():
	module = types.ModuleType("characterProcessing")
	module.SymbolDictionaryDefinition = _FakeDefinition
	module.SpeechSymbols = _FakeSymbols
	module.SpeechSymbol = _FakeSymbol
	module.SymbolLevel = types.SimpleNamespace(ALL=300)
	module.SYMPRES_NOREP = 2
	module.cleared = 0

	def clearSpeechSymbols():
		module.cleared += 1

	module.clearSpeechSymbols = clearSpeechSymbols
	module._symbolDictionaryDefinitions = [_FakeDefinition(name="cldr", path="{locale}"), _FakeDefinition(name="builtin", path="{locale}", mandatory=True), _FakeDefinition(name="user", path="{locale}", source="user", mandatory=True)]
	return module


class NumberSymbolTests(unittest.TestCase):
	def test_pattern(self):
		self.assertEqual(numberSymbols.matches("Received Wed 9/23/2026 6:06 PM"), [":"])
		self.assertEqual(numberSymbols.matches("10:30:15"), [":", ":"])
		self.assertEqual(numberSymbols.matches("Subject: Learning; ratio a:b; 6: 02"), [])

	def test_only_after_a_migration(self):
		self.assertTrue(numberSymbols.wanted({"lastMigration": {"when": "now"}}))
		self.assertFalse(numberSymbols.wanted({"lastMigration": {}}))
		self.assertFalse(numberSymbols.wanted(None))

	def test_registers_before_the_users_symbols_and_unregisters(self):
		fake = _fakeCharacterProcessing()
		with mock.patch.dict(sys.modules, {"characterProcessing": fake}):
			try:
				self.assertTrue(numberSymbols.register())
				self.assertTrue(numberSymbols.register(), "registering twice does nothing more")
				names = [definition.name for definition in fake._symbolDictionaryDefinitions]
				self.assertEqual(names, ["cldr", "builtin", numberSymbols.DEFINITION_NAME, "user"])
				definition = fake._symbolDictionaryDefinitions[2]
				english = definition.getSymbols("en")
				self.assertEqual(english.complexSymbols, {numberSymbols.IDENTIFIER: numberSymbols.PATTERN})
				symbol = english.symbols[numberSymbols.IDENTIFIER]
				self.assertEqual((symbol.replacement, symbol.level, symbol.preserve), ("colon", 300, 2))
				self.assertEqual(definition.getSymbols("de").symbols[numberSymbols.IDENTIFIER].replacement, "Doppelpunkt")
				with self.assertRaises(FileNotFoundError, msg="like NVDA's built-in symbols, no data for en_US"):
					definition.getSymbols("en_US")
				# NVDA+Control+R rebuilds NVDA's list without the rule; registering again puts it back.
				fake._symbolDictionaryDefinitions[:] = [item for item in fake._symbolDictionaryDefinitions if item.name != numberSymbols.DEFINITION_NAME]
				self.assertTrue(numberSymbols.register())
				self.assertEqual([item.name for item in fake._symbolDictionaryDefinitions], ["cldr", "builtin", numberSymbols.DEFINITION_NAME, "user"])
			finally:
				numberSymbols.unregister()
			self.assertEqual([definition.name for definition in fake._symbolDictionaryDefinitions], ["cldr", "builtin", "user"])
			self.assertFalse(numberSymbols.isRegistered())
			self.assertEqual(fake.cleared, 3)


# -- the Eloquence rate ------------------------------------------------------------------------


class EloquenceRateTests(unittest.TestCase):
	def test_speed_carries_over(self):
		# The tester's JAWS rate 111 (75%) is their own NVDA 64 or 65 with the Eloquence add-on (speeds 40 to 150).
		self.assertEqual(voices.eciRatePercent(111, (40, 150)), 65)
		self.assertEqual(voices.eciRatePercent(95, (40, 156)), 47)
		self.assertEqual(voices.eciRatePercent(57, (40, 150)), 15)
		self.assertEqual(voices.eciRatePercent(10, (40, 150)), 0)
		self.assertEqual(voices.eciRatePercent(200, (40, 150)), 100)
		self.assertEqual(voices.eciRatePercent(160, (40, 156), boost=1.6), 52)
		self.assertIsNone(voices.eciRatePercent(None, (40, 150)))

	def test_eloquence_drivers(self):
		for name in ("ibmeci", "eloquence", "Eloquence", "eci", "eloquence64"):
			self.assertTrue(voices.isEciDriver(name), name)
		for name in ("sapi5", "oneCore", "espeak", ""):
			self.assertFalse(voices.isEciDriver(name), name)

	def test_scaled_settings(self):
		profile = voices.VoiceProfile("Eloquence", primarySynthesizer="eloq")
		context = voices.VoiceContext("enu", "Global", rate=111, pitch=65, volume=100)
		self.assertEqual(voices.scaledVoiceSettings(profile, context), {"rate": 75, "pitch": 65, "volume": 100})
		self.assertEqual(voices.scaledVoiceSettings(profile, context, (40, 150)), {"rate": 65, "pitch": 65, "volume": 100})
		sapi = voices.VoiceProfile("SAPI", primarySynthesizer="sapi 5x")
		self.assertEqual(voices.scaledVoiceSettings(sapi, voices.VoiceContext("enu", "Global", rate=10), (40, 150))["rate"], 50, "only Eloquence")

	def test_repair_plan(self):
		configured = [(None, "eloquence", 75, (40, 150), 1.0), ("JAWS settings", "eloquence", 75, (40, 150), 1.0), (None, "ibmeci", 60, (40, 156), 1.0)]
		fixes = rateRepair.planFixes([111, 57], configured)
		self.assertEqual([(fix.profile, fix.driver, fix.old, fix.new, fix.jawsRate) for fix in fixes], [(None, "eloquence", 75, 65, 111), ("JAWS settings", "eloquence", 75, 65, 111)])
		self.assertEqual(fixes[1].where, 'the profile "JAWS settings"')
		# A rate the user changed since, or one already right, stays.
		self.assertEqual(rateRepair.planFixes([111], [(None, "eloquence", 70, (40, 150), 1.0)]), [])
		self.assertEqual(rateRepair.planFixes([111], [(None, "eloquence", 65, (40, 150), 1.0)]), [])
		self.assertEqual(rateRepair.planFixes([], configured), [])


# -- what a restore brings back ----------------------------------------------------------------


NVDA_INI_AFTER_MIGRATION = """schemaVersion = 24
[general]
	playStartAndExitSounds = False
[speech]
	synth = eloquence
	symbolLevel = 200
	[[eloquence]]
		rate = 75
[keyboard]
	keyboardLayout = laptop
	NVDAModifierKeys = 7
[documentFormatting]
	reportClickable = False
"""

NVDA_INI_BEFORE_MIGRATION = """schemaVersion = 24
[general]
	askToExit = True
[speech]
	synth = eloquence
	symbolLevel = 100
	[[eloquence]]
		rate = 64
[keyboard]
	NVDAModifierKeys = 7
[documentFormatting]
	reportLandmarks = False
"""


class RestorePreviewTests(unittest.TestCase):
	def _ini(self, text):
		folder = tempfile.mkdtemp()
		path = os.path.join(folder, "nvda.ini")
		with open(path, "w", encoding="utf-8") as stream:
			stream.write(text)
		return restorePreview.readNvdaIni(path)

	def test_reads_nested_sections(self):
		tree = self._ini(NVDA_INI_AFTER_MIGRATION)
		self.assertEqual(tree["speech"]["eloquence"]["rate"], "75")
		self.assertEqual(tree["documentFormatting"]["reportClickable"], "False")
		self.assertEqual(restorePreview.readNvdaIni(os.path.join(tempfile.mkdtemp(), "missing.ini")), {})

	def test_the_testers_restore(self):
		changes = restorePreview.changes(self._ini(NVDA_INI_AFTER_MIGRATION), self._ini(NVDA_INI_BEFORE_MIGRATION))
		self.assertTrue(changes[0].startswith('NVDA says "clickable" before clickable items on web pages again'), changes)
		self.assertIn("Punctuation level: most becomes some (NVDA menu, Preferences, Settings, Speech).", changes)
		self.assertIn("Speech rate: 75 becomes 64 (NVDA menu, Preferences, Settings, Speech).", changes)
		self.assertIn("Keyboard layout: laptop becomes desktop (NVDA menu, Preferences, Settings, Keyboard).", changes)
		self.assertIn("NVDA plays its sounds when it starts and exits again.", changes)
		self.assertFalse([change for change in changes if change.startswith("NVDA keys")], "the NVDA keys are the same")

	def test_nothing_to_say_for_the_same_settings(self):
		tree = self._ini(NVDA_INI_AFTER_MIGRATION)
		self.assertEqual(restorePreview.changes(tree, tree), [])


if __name__ == "__main__":
	unittest.main()
