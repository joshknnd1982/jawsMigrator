# Unit tests for the parts of the JAWS Migration Assistant that do not need NVDA.
# They use small made-up JAWS files, so they run anywhere.
# Run: python -m unittest discover -s tests -p "test_*.py"

import json
import os
import shutil
import struct
import sys
import tempfile
import types
import unittest
import wave

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import (  # noqa: E402
	backup,
	classicSounds,
	dictMap,
	jawsDocs,
	jawsFiles,
	keyPlan,
	migrator,
	safety,
	schemeMap,
	selection,
	settingsMap,
	soundMap,
	storeAddons,
	symbolMap,
	updater,
	voices,
	wavUtil,
)


class Temp(unittest.TestCase):
	def setUp(self):
		self.folder = tempfile.mkdtemp(prefix="jawsMigrator-unit-")

	def tearDown(self):
		shutil.rmtree(self.folder, ignore_errors=True)

	def write(self, name, text, encoding="utf-8"):
		path = os.path.join(self.folder, name)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, "w", encoding=encoding, newline="\r\n") as stream:
			stream.write(text)
		return path


class JawsFilesTests(Temp):
	def test_encodings(self):
		text = "[options]\nTypingEcho=2\n"
		for encoding in ("utf-8", "utf-8-sig", "utf-16", "cp1252"):
			path = self.write(f"{encoding}.jcf", text, encoding)
			self.assertEqual(jawsFiles.readIni(path).getInt("options", "typingecho"), 2, encoding)

	def test_ini_details(self):
		ini = jawsFiles.parseIni(
			"; comment\n[Options]\nEnable=1   ; 1=Enabled\nStructuredModeReverseOrder=1;\n[Common Keys]\nShift+==AddButton\n",
			inlineComments=True,
		)
		self.assertEqual(ini.get("options", "enable"), "1")
		self.assertEqual(ini.getInt("OPTIONS", "StructuredModeReverseOrder"), 1)
		self.assertEqual(ini.get("common keys", "shift+"), "=AddButton")

	def test_merge_user_over_shared(self):
		shared = jawsFiles.parseIni("[options]\nTypingEcho=1\nVerbosity=0\n")
		user = jawsFiles.parseIni("[options]\ntypingecho=3\n")
		merged = jawsFiles.mergeIni(shared, user)
		self.assertEqual(merged.getInt("options", "TypingEcho"), 3)
		self.assertEqual(merged.getInt("options", "Verbosity"), 0)

	def test_jdf(self):
		rules = jawsFiles.parseJdf(".reposition*.re position.0x09.*.*.0.0.\n,.freedom.com,dot freedom,*,*,*,1,0,\n.Wave.Waiff.0x07.Eloquence Software.*.0.0.\n")
		self.assertEqual(len(rules), 3)
		self.assertTrue(rules[0].isRootWord)
		self.assertTrue(rules[1].caseSensitive)
		self.assertEqual(rules[2].synthesizer, "Eloquence Software")
		self.assertTrue(jawsFiles.languageMatches("0x09", 0x0409))
		self.assertFalse(jawsFiles.languageMatches("0x07", 0x0409))
		self.assertTrue(jawsFiles.languageMatches("*", 0x0409))


class VoicesTests(Temp):
	def test_ranges(self):
		self.assertEqual(voices.JAWS_SYNTHS["eloq"].rate.toPercent(95), 95)
		self.assertEqual(voices.JAWS_SYNTHS["sapi 5x"].rate.toPercent(10), 50)
		self.assertEqual(voices.JAWS_SYNTHS["sapi 5x"].rate.toPercent(20), 100)
		self.assertEqual(voices.JAWS_SYNTHS["dtsoft"].rate.toPercent(250), 50)

	def test_profile_layering_and_contexts(self):
		shared = self.write(
			"shared/Eloquence.vpf",
			"[Options]\nPrimarySynthesizer=eloq\n[enu-Global]\nRate=57\nPitch=65\nPunctuation=2\nVoiceName=Reed\nParent=None\n"
			"[enu-JAWSCursor]\nPitch=58\nVoiceName=Glen\nParent=Global\n[enu-Voice Aliases]\nLinkVoice=Shelly\n",
		)
		user = self.write("user/Eloquence.VPF", "[ENU-Global]\nRate=95\n[ENU-JAWSCursor]\nRate=95\n")
		profile = voices.loadVoiceProfile("Eloquence", shared, user)
		self.assertEqual(profile.primarySynthesizer, "eloq")
		cursor = profile.context("enu", "JAWSCursor")
		self.assertEqual((cursor.rate, cursor.pitch, cursor.voiceName, cursor.punctuation), (95, 58, "Glen", 2))
		self.assertEqual(profile.voiceAliases("enu")["LinkVoice"], "Shelly")

	def test_aliases(self):
		groups = voices.parseVoiceAlias("Samantha Premium High|0|0;*|15%|0")
		self.assertEqual([g["person"] for g in groups], ["Samantha Premium High", "*"])
		self.assertEqual(groups[1]["pitch"], (15.0, True))
		self.assertTrue(voices.aliasIsNeutral("*|0|0;*|0|0"))
		self.assertFalse(voices.aliasIsNeutral("Rocko|5%|0"))
		self.assertEqual(voices.applyDelta(65, (20.0, True), voices.PERCENT), 78)

	def test_matching(self):
		variants = {"1": "Reed", "2": "Shelley", "5": "Glen", "6": "FastFlo"}
		self.assertEqual(voices.matchVariant(variants, "Shelly"), "2")
		self.assertEqual(voices.matchVariant(variants, "Glen"), "5")
		self.assertEqual(voices.matchVariant(variants, "Bobby"), "6")
		options = voices.findNvdaEquivalents(
			"eloq",
			"Reed",
			[("ibmeci", "IBMTTS"), ("sapi5", "Microsoft Speech API version 5")],
			[{"name": "ViaVoice Reed", "vendor": "IBM", "language": "de_DE", "driver": "sapi5"}, {"name": "Outloud Reed", "vendor": "IBM", "language": "en_US", "driver": "sapi5"}],
			[],
			languageCode="en_US",
		)
		self.assertEqual(options[0].driver, "ibmeci")
		self.assertEqual(options[1].voiceName, "Outloud Reed")


class SettingsMapTests(unittest.TestCase):
	def mapping(self, text, classic=False, user=None):
		ini = jawsFiles.parseIni(text, inlineComments=True)
		userKeys = {(s.name.lower(), k.lower()) for s in jawsFiles.parseIni(user or "").sections.values() for k in s.keys()}
		result = settingsMap.mapSettings(ini, ini, classicSpeech=classic, userKeys=userKeys)
		return result, {change.key: change.value for change in result.changes}

	def test_core_options(self):
		_result, values = self.mapping(
			"[options]\nTypingEcho=3\nKeyboardType=Laptop\nJAWSInsertKey=3\nVerbosity=2\n"
			"[OutputModes]\nACCESS_KEY=1|1|0|Access Key\n[NonJCFOptions]\nTblHeaders=1\nSayAllOnDocumentLoad=0\n"
			"[HTML]\nDocumentPresentationMode=0\n[FormsMode]\nAutoFormsMode=1\n",
		)
		self.assertEqual(values["keyboard.speakTypedCharacters"], 1)
		self.assertEqual(values["keyboard.speakTypedWords"], 1)
		self.assertEqual(values["keyboard.keyboardLayout"], "laptop")
		self.assertEqual(values["keyboard.NVDAModifierKeys"], 7)
		self.assertFalse(values["presentation.reportKeyboardShortcuts"])
		self.assertEqual(values["documentFormatting.reportTableHeaders"], 2)
		self.assertFalse(values["virtualBuffers.autoSayAllOnPageLoad"])
		self.assertFalse(values["virtualBuffers.useScreenLayout"])
		self.assertTrue(values["virtualBuffers.autoPassThroughOnCaretMove"])

	def test_defaults_that_would_hide_information(self):
		_result, values = self.mapping("[options]\nDetailsAnnouncement=0\n")
		self.assertNotIn("annotations.reportDetails", values)
		_result, values = self.mapping("[options]\nDetailsAnnouncement=0\n", user="[options]\nDetailsAnnouncement=0\n")
		self.assertIn("annotations.reportDetails", values)

	def test_classic_speech_and_sleep(self):
		result, values = self.mapping("[options]\nVerbosity=1\nMixedCase=1\nNumbers=1\nSleepMode=1\n", classic=True)
		self.assertEqual(values["defaultProfile"], "Intermediate")
		self.assertTrue(values["textProcessingData.splitMixedCaseWords"])
		self.assertEqual(values["numberProcessingData.numberProcessingMode"], "singleDigits")
		self.assertTrue(result.sleepMode)


class DictMapTests(unittest.TestCase):
	def test_entries(self):
		rules = jawsFiles.parseJdf(".reposition*.re position.*.*.*.0.0.\n.<<.double left.*.*.*.0.0.\n.vfo.v f o.*.*.*.0.0.\n.chime..*.*.*.0.0.chime.wav.\n.Wave.Waiff.0x07.*.*.0.0.\n")
		conversion = dictMap.convertRules(rules, "Default.jdf", 0x0409)
		lines = [entry.asLine() for entry in conversion.entries]
		self.assertIn("\\breposition\tre position\t0\t1", lines)
		self.assertIn("<<\tdouble left\t0\t0", lines)
		self.assertIn("vfo\tv f o\t0\t2", lines)
		self.assertEqual(len(conversion.skipped), 2)


class SymbolMapTests(Temp):
	def test_levels_and_merge(self):
		section = jawsFiles.parseIni("[0x409]\nsymbol1=! 11000000 exclaim!\nsymbol2=# 11111101 number\nsymbol18== 11111100 equals\n").section("0x409")
		symbols = symbolMap.parseSymbols(section)
		self.assertEqual(symbols["!"].nvdaLevel, "all")
		self.assertEqual(symbols["!"].spokenText, "exclaim")
		self.assertEqual(symbols["#"].nvdaLevel, "some")
		self.assertIn("=", symbols)
		path = self.write("symbols-en.dic", "complexSymbols:\r\nx\ty\r\n\r\nsymbols:\r\n?\t-\t-\talways\r\n#\thash\tall\t-\r\n")
		symbolMap.mergeIntoSymbolFile(path, {"#": symbols["#"]})
		with open(path, encoding="utf-8-sig") as stream:
			text = stream.read()
		self.assertIn("complexSymbols:", text)
		self.assertIn("?\t-\t-\talways", text)
		self.assertIn("\\#\tnumber\tsome\t-", text)


class SchemeMapTests(unittest.TestCase):
	def test_rent_a_crowd_style(self):
		smf = jawsFiles.parseIni(
			"[Information]\nTitle=Web Test\n[ControlType Behavior Table]\n47=3|NormalVoice||LinkVoice|\n68=2|NormalVoice|h1a.wav||\n"
			"[Attribute Behavior Table]\n0X88001=1|MessageVoice|||\n0X3=1|BoldVoice|||\n",
		)
		aliases = {"LinkVoice": "Shelly", "MessageVoice": "Glen|0|0", "BoldVoice": "*|0|0", "HeadingLevel2Voice": "Rocko|10%|0"}
		scheme = schemeMap.convertScheme(smf, "x.smf", lambda name: "C:\\sounds\\" + name, aliases)
		self.assertEqual(scheme.items["role.LINK"].voiceAlias, "LinkVoice")
		self.assertTrue(scheme.items["role.HEADING.1"].sound.endswith("h1a.wav"))
		self.assertNotIn("fmt.bold", scheme.items)
		aliasScheme = schemeMap.aliasScheme(aliases)
		self.assertIn("role.HEADING.2", aliasScheme.items)
		self.assertIn("role.LINK", aliasScheme.items)


class KeyPlanTests(unittest.TestCase):
	jkm = jawsFiles.parseIni(
		"[Common Keys]\nJAWSKey+T=SayWindowTitle\nJAWSKey+Shift+B=SayBatteryLevel\nUpArrow=SayPriorLine\nJAWSKey+Space&H=ShowSpeechHistory\n"
		"[Laptop Keys]\nCapsLock+PageDown=SayBottomLineOfWindow\n[DESKTOP Keys]\nJAWSKey+PageDown=SayBottomLineOfWindow\n"
		"[Quick Navigation Keys]\nr=MoveToNextRegion\na=MoveToNextRadioButton\n",
	)

	def test_plan(self):
		plan = keyPlan.planKeys(self.jkm, "laptop")
		gestures = {binding.gesture: binding.script for binding in plan.bindings}
		self.assertEqual(gestures.get("kb:NVDA+t"), "title")
		self.assertEqual(gestures.get("kb(laptop):NVDA+pageDown"), "reportStatusLine")
		self.assertEqual(gestures.get("kb:r"), "nextLandmark")
		self.assertEqual(gestures.get("kb:a"), "nextRadioButton")
		kinds = {item.jawsKey: item.kind for item in plan.skipped}
		self.assertEqual(kinds["UpArrow"], keyPlan.SKIP_PASSTHROUGH)
		self.assertEqual(kinds["JAWSKey+Space&H"], keyPlan.SKIP_UNCONVERTIBLE)
		self.assertEqual(kinds["JAWSKey+PageDown"], keyPlan.SKIP_LAYOUT)

	def test_conflicts(self):
		bound = {"kb:NVDA+t": [("globalCommands", "GlobalCommands", "title")], "kb:NVDA+shift+b": [("globalCommands", "GlobalCommands", "other")]}
		plan = keyPlan.planKeys(self.jkm, "desktop", boundScripts=lambda gesture: bound.get(gesture, []))
		kinds = {item.jawsKey: item.kind for item in plan.skipped}
		self.assertEqual(kinds["JAWSKey+T"], keyPlan.SKIP_SAME)
		self.assertEqual(kinds["JAWSKey+Shift+B"], keyPlan.SKIP_CONFLICT)
		plan = keyPlan.planKeys(self.jkm, "desktop", boundScripts=lambda gesture: bound.get(gesture, []), overrideConflicts=True)
		self.assertIn("kb:NVDA+shift+b", [binding.gesture for binding in plan.bindings])

	def test_reverse_map(self):
		reverse = keyPlan.buildReverseMap(self.jkm, "laptop")
		self.assertEqual(reverse["kb:nvda+t"][0][1], "SayWindowTitle")

	#: A key map with every kind of JAWS keyboard layout, as in JAWS 2026's Default.jkm.
	layoutsJkm = jawsFiles.parseIni(
		"[Keyboard Layouts]\nDesktop=Common\nLaptop=Common\nKinesis=Common\nPAC Mate=Laptop\n"
		"[Common Keys]\nJAWSKey+T=SayWindowTitle\n"
		"[Classic Laptop Keys]\nAlt+Shift+N=SayBottomLineOfWindow\n"
		"[Laptop Keys]\nCapsLock+PageDown=SayBottomLineOfWindow\n"
		"[DESKTOP Keys]\nJAWSKey+PageDown=SayBottomLineOfWindow\n"
		"[Kinesis keys]\nJAWSKey+PageDown=SayBottomLineOfWindow\n"
		"[PAC Mate Keys]\nJAWSKey+Q=SayBottomLineOfWindow\n"
		"[Laptop Modifiers]\nCapsLock=14|3|0|0|0|0|0x4000\n[Classic Laptop Modifiers]\nInsert=17|3|0|2|0|0|0x4020800\n",
	)

	def test_layouts_found(self):
		layouts = {layout.id: layout for layout in keyPlan.keyboardLayouts(self.layoutsJkm)}
		self.assertEqual(sorted(layouts), ["classic laptop", "desktop", "kinesis", "laptop"])
		self.assertEqual((layouts["laptop"].nvdaLayout, layouts["laptop"].capsLock), ("laptop", True))
		self.assertEqual((layouts["classic laptop"].nvdaLayout, layouts["classic laptop"].capsLock), ("laptop", False))
		self.assertEqual((layouts["kinesis"].nvdaLayout, layouts["desktop"].nvdaLayout), ("desktop", "desktop"))
		self.assertEqual(keyPlan.layoutId(" Classic  Laptop "), "classic laptop")

	def test_layouts_chosen(self):
		plan = keyPlan.planKeys(self.layoutsJkm, "Laptop")
		sections = {binding.gesture: binding.section for binding in plan.bindings}
		self.assertEqual(sections.get("kb(laptop):NVDA+pageDown"), "Laptop Keys")
		self.assertNotIn("kb(desktop):NVDA+pageDown", sections)
		self.assertEqual({item.section for item in plan.skipped if item.kind == keyPlan.SKIP_LAYOUT}, {"Classic Laptop Keys", "DESKTOP Keys", "Kinesis keys"})
		plan = keyPlan.planKeys(self.layoutsJkm, "Laptop", layouts=["desktop", "laptop", "classic laptop", "kinesis"])
		sections = {binding.gesture: binding.section for binding in plan.bindings}
		self.assertEqual(sections.get("kb(desktop):NVDA+pageDown"), "DESKTOP Keys")
		self.assertEqual(sections.get("kb(laptop):NVDA+pageDown"), "Laptop Keys")
		self.assertEqual(sections.get("kb(laptop):alt+shift+n"), "Classic Laptop Keys")
		duplicates = [item for item in plan.skipped if item.kind == keyPlan.SKIP_DUPLICATE]
		self.assertEqual([item.section for item in duplicates], ["Kinesis keys"])
		# The layout in use wins when two JAWS layouts share an NVDA layout.
		plan = keyPlan.planKeys(self.layoutsJkm, "Kinesis", layouts=["desktop", "kinesis"])
		sections = {binding.gesture: binding.section for binding in plan.bindings}
		self.assertEqual(sections.get("kb(desktop):NVDA+pageDown"), "Kinesis keys")
		reverse = keyPlan.buildReverseMap(self.layoutsJkm, "laptop", ["desktop"])
		self.assertIn("kb(desktop):nvda+pagedown", reverse)
		self.assertIn("kb(laptop):nvda+pagedown", reverse)


class KeyboardChoiceTests(unittest.TestCase):
	def plan(self, keyboardType):
		from jawsMigrator import jawsDetect

		options = migrator.MigrationOptions(jaws=jawsDetect.JawsInstallation("2026"), language="enu")
		plan = migrator.MigrationPlan(options=options, index=None, facts=None)
		plan.settings = settingsMap.mapSettings(jawsFiles.parseIni(f"[options]\nKeyboardType={keyboardType}\nJAWSInsertKey=3\n"))
		plan.jawsKeyboardLayout = keyPlan.layoutId(keyboardType)
		plan.keyboardLayouts = keyPlan.keyboardLayouts(KeyPlanTests.layoutsJkm)
		return plan

	def values(self, plan):
		return {change.key: change.value for change in plan.finalSettingChanges()}

	def test_follows_jaws(self):
		values = self.values(self.plan("Laptop"))
		self.assertEqual((values["keyboard.keyboardLayout"], values["keyboard.NVDAModifierKeys"]), ("laptop", 7))
		values = self.values(self.plan("Classic Laptop"))
		self.assertEqual((values["keyboard.keyboardLayout"], values["keyboard.NVDAModifierKeys"]), ("laptop", 6))

	def test_other_layout_chosen(self):
		plan = self.plan("Laptop")
		plan.options.keyboardLayouts = ["desktop"]
		values = self.values(plan)
		# NVDA uses the layout the chosen keystrokes work in; Caps Lock only comes with the Laptop layout.
		self.assertEqual((values["keyboard.keyboardLayout"], values["keyboard.NVDAModifierKeys"]), ("desktop", 6))
		self.assertEqual(plan.settingChange("keyboard.keyboardLayout").value, "laptop")

	def test_explicit_choice_and_keep(self):
		plan = self.plan("Desktop")
		plan.options.keyboardLayouts = ["desktop", "laptop"]
		values = self.values(plan)
		self.assertEqual((values["keyboard.keyboardLayout"], values["keyboard.NVDAModifierKeys"]), ("desktop", 7))
		plan.options.nvdaKeyboardLayout = ""
		self.assertNotIn("keyboard.keyboardLayout", self.values(plan))
		plan.options.nvdaKeyboardLayout = "laptop"
		self.assertEqual(self.values(plan)["keyboard.keyboardLayout"], "laptop")
		plan.options.keyboard = False
		self.assertEqual(self.values(plan)["keyboard.NVDAModifierKeys"], 6)


class BackupTests(Temp):
	def test_round_trip(self):
		config = os.path.join(self.folder, "nvda")
		addon = os.path.join(config, "jawsMigrator")
		waves = os.path.join(self.folder, "waves")
		for relative, text in (("nvda.ini", "a=1"), ("profiles/Work.ini", "w=1"), ("speechDicts/default.dic", "x\ty\t0\t0")):
			self.write(os.path.join("nvda", relative), text)
		os.makedirs(waves)
		with open(os.path.join(waves, "start.wav"), "wb") as stream:
			stream.write(b"RIFF")
		info = backup.createBackup(config, addon, waves, "test")
		self.write("nvda/nvda.ini", "a=2")
		self.write("nvda/gestures.ini", "new")
		self.write("nvda/profiles/JAWS settings.ini", "j")
		backup.restoreBackup(info, config, addon)
		with open(os.path.join(config, "nvda.ini"), encoding="utf-8") as stream:
			self.assertEqual(stream.read().strip(), "a=1")
		self.assertFalse(os.path.exists(os.path.join(config, "gestures.ini")))
		self.assertFalse(os.path.exists(os.path.join(config, "profiles", "JAWS settings.ini")))
		self.assertTrue(os.path.exists(os.path.join(config, "profiles", "Work.ini")))
		self.assertEqual(info.nvdaSounds, 1)


class FullBackupTests(Temp):
	def addon(self, config, folder, name, version, files=None):
		self.write(
			os.path.join("nvda", "addons", folder, "manifest.ini"),
			f'name = {name}\nsummary = "{name}"\ndescription = """A test add-on.\nversion = 99\n"""\nversion = {version}\n',
		)
		for relative, text in (files or {}).items():
			self.write(os.path.join("nvda", "addons", folder, relative), text)

	def read(self, *parts):
		with open(os.path.join(self.folder, *parts), encoding="utf-8") as stream:
			return stream.read()

	def test_everything_backed_up_and_put_back(self):
		import json

		config = os.path.join(self.folder, "nvda")
		data = os.path.join(config, "jawsMigrator")
		self.write("nvda/nvda.ini", "a=1")
		self.write("nvda/macintalk/voice.dat", "voice data")
		self.write("nvda/updates/nvda_update.exe", "x")
		self.write("nvda/addonStore/_dl/waiting.nvda-addon", "x")
		self.write("nvda/addonStore/_cachedLatestAddons.json", "{}")
		self.addon(config, "keep", "keep", "1.0", {"settings.json": '{"a": 1}', "__pycache__/x.pyc": "c"})
		self.addon(config, "old", "old", "2.0")
		self.addon(config, "gone", "gone", "1.0")
		self.addon(config, "jawsMigrator", "jawsMigrator", "1.1")
		self.write("nvda/addonsState.json", json.dumps({"disabledAddons": ["old"], "overrideCompatibility": ["gone"]}))
		self.assertEqual(backup.estimateBackup(config, data)[0], 7)
		first = backup.createBackup(config, data, "", "first", original=True)
		relatives = {entry["relative"] for entry in first.files}
		self.assertTrue({"macintalk/voice.dat", "addons/keep/settings.json", "addonsState.json", "addons/gone/manifest.ini"} <= relatives)
		self.assertFalse([r for r in relatives if r.startswith(("updates/", "addonStore/_dl/", "addonStore/_cached", "addons/jawsMigrator", "jawsMigrator/")) or "__pycache__" in r])
		self.assertEqual({a["name"]: a["version"] for a in first.addons}, {"gone": "1.0", "keep": "1.0", "old": "2.0"})
		self.assertEqual(backup.verifyBackup(first, thorough=True), [])
		# A second backup links the unchanged files to the first instead of copying them.
		second = backup.createBackup(config, data, "", "second")
		self.assertEqual((second.copiedSize, len(second.files)), (0, len(first.files)))
		self.assertTrue(os.path.samefile(os.path.join(first.path, "config", "macintalk", "voice.dat"), os.path.join(second.path, "config", "macintalk", "voice.dat")))
		self.assertEqual(backup.pruneBackups(data, keep=0), 1)
		self.assertEqual([info.reason for info in backup.listBackups(data)], ["first"])
		self.assertIn("before the first JAWS migration", backup.listBackups(data)[0].label)
		# Afterwards: settings changed, an add-on updated, one removed, one new, one waiting to install.
		self.write("nvda/addons/keep/settings.json", '{"a": 2}')
		self.write("nvda/macintalk/voice.dat", "changed!!!")
		self.write("nvda/profiles/JAWS settings.ini", "j")
		shutil.rmtree(os.path.join(config, "addons", "gone"))
		shutil.rmtree(os.path.join(config, "addons", "old"))
		self.addon(config, "old", "old", "3.0")
		self.addon(config, "newer", "newer", "1.0")
		self.addon(config, "customLabels.pendingInstall", "customLabels", "1.0")
		self.write("nvda/addonsState.json", json.dumps({"pendingInstallsSet": ["customLabels"]}))
		manager = backup.FileAddonManager(config)
		planned = {(action.name, action.kind) for action in backup.planAddonRestore(first, manager.installed())}
		self.assertEqual(planned, {("customLabels", backup.REMOVE), ("newer", backup.REMOVE), ("gone", backup.REINSTALL), ("old", backup.REINSTALL)})
		result = backup.restoreBackup(first, config, data, addons=manager)
		self.assertEqual(result.failed, [])
		self.assertTrue(result.restartNeeded)
		self.assertEqual(self.read("nvda", "macintalk", "voice.dat"), "voice data")
		self.assertEqual(self.read("nvda", "addons", "keep", "settings.json"), '{"a": 1}')
		self.assertFalse(os.path.exists(os.path.join(config, "profiles", "JAWS settings.ini")))
		self.assertFalse(os.path.exists(os.path.join(config, "addons", "customLabels.pendingInstall")))
		self.assertIn("version = 1.0", self.read("nvda", "addons", "gone.pendingInstall", "manifest.ini"))
		self.assertIn("version = 2.0", self.read("nvda", "addons", "old.pendingInstall", "manifest.ini"))
		self.assertTrue(os.path.isdir(os.path.join(config, "addons", "jawsMigrator")))
		state = backup.readAddonState(config)
		self.assertEqual(sorted(state["pendingRemovesSet"]), ["newer", "old"])
		self.assertEqual(sorted(state["pendingInstallsSet"]), ["gone", "old"])
		self.assertEqual((state["PENDING_OVERRIDE_COMPATIBILITY"], state["disabledAddons"]), (["gone"], ["old"]))
		# A damaged copy in the backup is never put back.
		with open(os.path.join(first.path, "config", "macintalk", "voice.dat"), "w", encoding="utf-8") as stream:
			stream.write("xxxxx data")
		self.write("nvda/macintalk/voice.dat", "different!")
		result = backup.restoreBackup(first, config, data)
		self.assertTrue(any("damaged" in problem for problem in result.failed))
		self.assertEqual(self.read("nvda", "macintalk", "voice.dat"), "different!")


class ClassicSoundsTests(Temp):
	def wav(self, *parts, frames=b"\x01\x00" * 50):
		path = os.path.join(self.folder, *parts)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with wave.open(path, "wb") as out:
			out.setnchannels(1)
			out.setsampwidth(2)
			out.setframerate(11025)
			out.writeframes(frames)
		return path

	def imaWav(self, *parts):
		# The one-block IMA ADPCM file of WavTests, which NVDA can't play until it is converted.
		fmt = struct.pack("<HHIIHH", wavUtil.WAVE_FORMAT_IMA_ADPCM, 1, 8000, 4000, 8, 4) + struct.pack("<HH", 2, 9)
		data = struct.pack("<hBB", 0, 0, 0) + bytes([0x11, 0x22, 0x77, 0x00])
		riff = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
		path = os.path.join(self.folder, *parts)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, "wb") as stream:
			stream.write(b"RIFF" + struct.pack("<I", len(riff)) + riff)
		return path

	def scheme(self, config, folder, items=None):
		path = os.path.join(config, "ClassicSpeech", "Schemes", folder)
		os.makedirs(path, exist_ok=True)
		with open(os.path.join(path, "scheme.json"), "w", encoding="utf-8") as stream:
			json.dump({"format": "ClassicSpeech scheme", "version": 1, "name": folder, "items": items or {}, "custom": {}, "extra": "kept"}, stream)
		return path

	def items(self, folder):
		return classicSounds.readScheme(folder)["items"]

	def test_every_jaws_sound_copied(self):
		config = os.path.join(self.folder, "nvda")
		sounds = [
			types.SimpleNamespace(path=self.wav("jaws", "shared", "Click.wav"), name="Click.wav", scope="shared"),
			types.SimpleNamespace(path=self.wav("jaws", "user", "click.wav", frames=b"\x05\x00" * 10), name="click.wav", scope="user"),
			types.SimpleNamespace(path=self.imaWav("jaws", "shared", "Compressed.wav"), name="Compressed.wav", scope="shared"),
		]
		result = classicSounds.importAllSounds(sounds, config)
		self.assertEqual((result.sounds, result.converted, result.failed), (2, 1, []))
		folder = os.path.join(config, "ClassicSpeech", "Schemes", classicSounds.JAWS_SOUNDS_SCHEME)
		self.assertEqual(result.folder, folder)
		copied = {name.lower(): os.path.join(folder, "Sounds", name) for name in os.listdir(os.path.join(folder, "Sounds"))}
		self.assertEqual(sorted(copied), ["click.wav", "compressed.wav"])
		with wave.open(copied["click.wav"]) as sound:
			self.assertEqual(sound.getnframes(), 10, "the user's own copy of a JAWS sound wins, as in JAWS")
		self.assertTrue(wavUtil.isPlayable(copied["compressed.wav"]))
		self.assertEqual(classicSounds.readScheme(folder)["name"], classicSounds.JAWS_SOUNDS_SCHEME)
		# Copying again keeps what the user set up in the scheme.
		scheme = classicSounds.readScheme(folder)
		scheme["items"]["role.LINK"] = {"sound": "Sounds/Click.wav", "soundOnly": False}
		classicSounds._writeScheme(folder, scheme)
		classicSounds.importAllSounds(sounds, config)
		self.assertIn("role.LINK", self.items(folder))

	def test_jaws_sounds_for_nvda_sounds_and_back(self):
		config = os.path.join(self.folder, "nvda")
		events = {event.nvdaName: event for event in soundMap.SOUND_EVENTS}
		focus = self.wav("jaws", "Boink2.wav")
		choices = [
			soundMap.SoundChoice(events["focusMode"], focus, "Boink2.wav"),
			soundMap.SoundChoice(events["browseMode"], self.wav("jaws", "Boink1.wav", frames=b"\x02\x00" * 60), "Boink1.wav"),
		]
		default = self.scheme(config, "Default")
		classic = self.scheme(config, "Classic (from JAWS)", {"nvdaSound.browseMode": {"sound": "Sounds/mine.wav", "soundOnly": False}, "role.LINK": {"sound": "Sounds/link.wav"}})
		self.wav("nvda", "ClassicSpeech", "Schemes", "Classic (from JAWS)", "Sounds", "mine.wav", frames=b"\x09\x00" * 5)
		shutil.copyfile(focus, os.path.join(classic, "Sounds", "Boink2.wav"))
		result = classicSounds.applyNvdaSounds(choices, config)
		self.assertEqual((result.added, result.kept, result.failed), (3, ["Classic (from JAWS): browseMode"], []))
		self.assertEqual(self.items(default)["nvdaSound.focusMode"]["sound"], "Sounds/Boink2.wav")
		self.assertTrue(os.path.isfile(os.path.join(default, "Sounds", "Boink1.wav")))
		classicItems = self.items(classic)
		self.assertEqual(classicItems["nvdaSound.browseMode"]["sound"], "Sounds/mine.wav", "a sound the scheme already had is kept")
		self.assertEqual(classicItems["nvdaSound.focusMode"]["sound"], "Sounds/Boink2.wav", "an identical sound already there is reused")
		self.assertEqual(classicSounds.readScheme(classic)["extra"], "kept")
		record = result.record
		self.assertTrue(classicSounds.isApplied(record))
		self.assertEqual(record["schemes"]["Classic (from JAWS)"]["files"], {})
		self.assertEqual(record["sounds"], {"focusMode": "Boink2.wav", "browseMode": "Boink1.wav"})
		self.assertIn("2 of NVDA's sounds", classicSounds.statusText(record))
		self.assertEqual(classicSounds.applyNvdaSounds(choices, config, record).added, 0, "applying again adds nothing")
		# ClassicSpeech's switch: on by default, and turned on and off only when it changes.
		section = {"schemeData": json.dumps({"version": 2, "enabled": False, "activeScheme": "Default"})}
		self.assertTrue(classicSounds.enableSchemes(section))
		self.assertFalse(classicSounds.enableSchemes(section))
		self.assertEqual(json.loads(section["schemeData"])["activeScheme"], "Default")
		self.assertTrue(classicSounds.schemesEnabled({}))
		# The user changes one sound in ClassicSpeech; restoring NVDA's sounds leaves it.
		changed = classicSounds.readScheme(default)
		changed["items"]["nvdaSound.browseMode"] = {"sound": "Sounds/other.wav", "soundOnly": False}
		classicSounds._writeScheme(default, changed)
		self.wav("nvda", "ClassicSpeech", "Schemes", "Default", "Sounds", "other.wav", frames=b"\x07\x00" * 7)
		restored = classicSounds.restoreNvdaSounds(config, record)
		self.assertEqual((restored.removed, restored.kept, restored.failed), (2, ["Default: browseMode"], []))
		self.assertEqual(sorted(self.items(default)), ["nvdaSound.browseMode"])
		self.assertFalse(os.path.exists(os.path.join(default, "Sounds", "Boink2.wav")), "the sounds it copied go")
		self.assertFalse(os.path.exists(os.path.join(default, "Sounds", "Boink1.wav")))
		self.assertEqual(sorted(self.items(classic)), ["nvdaSound.browseMode", "role.LINK"])
		self.assertTrue(os.path.exists(os.path.join(classic, "Sounds", "Boink2.wav")), "a sound that was there before stays")
		self.assertTrue(classicSounds.disableSchemes(section))
		self.assertFalse(classicSounds.schemesEnabled(section))

	def test_no_scheme_yet_and_nvda_sounds_copied(self):
		config = os.path.join(self.folder, "nvda")
		events = {event.nvdaName: event for event in soundMap.SOUND_EVENTS}
		result = classicSounds.applyNvdaSounds([soundMap.SoundChoice(events["textError"], self.wav("jaws", "BuzzerShort.wav"), "BuzzerShort.wav")], config)
		self.assertEqual(result.schemes, ["Default"], "ClassicSpeech's Default scheme is made when there is none")
		self.assertIn("nvdaSound.textError", self.items(os.path.join(config, "ClassicSpeech", "Schemes", "Default")))
		waves = os.path.dirname(self.wav("NVDA", "waves", "browseMode.wav"))
		self.wav("NVDA", "waves", "focusMode.wav")
		copies = classicSounds.backupNvdaSounds(waves, os.path.join(config, "jawsMigrator"), "2026.2.0")
		self.assertEqual(sorted(os.listdir(copies)), ["browseMode.wav", "focusMode.wav"])
		self.assertTrue(copies.endswith(os.path.join("nvdaSounds", "2026.2.0")))


class SafetyTests(unittest.TestCase):
	def test_jaws_folders_refused(self):
		saved = safety._roots
		try:
			safety._roots = [os.path.normcase(os.path.abspath(r"C:\ProgramData\Freedom Scientific"))]
			with self.assertRaises(safety.JawsProtectedError):
				safety.checkWritable(r"C:\ProgramData\Freedom Scientific\JAWS\2026\SETTINGS\enu\x.jcf")
			self.assertTrue(safety.checkWritable(r"C:\Users\someone\AppData\Roaming\nvda\x"))
		finally:
			safety._roots = saved


class WavTests(Temp):
	def test_pcm_copy_and_ima_decode(self):
		source = os.path.join(self.folder, "pcm.wav")
		with wave.open(source, "wb") as out:
			out.setnchannels(1)
			out.setsampwidth(2)
			out.setframerate(11025)
			out.writeframes(b"\x00\x00" * 100)
		self.assertEqual(wavUtil.copyPlayable(source, os.path.join(self.folder, "copy.wav")), "copied")
		# A one-block IMA ADPCM file: header predictor 0, index 0, then 4 bytes of nibbles.
		fmt = struct.pack("<HHIIHH", wavUtil.WAVE_FORMAT_IMA_ADPCM, 1, 8000, 4000, 8, 4) + struct.pack("<HH", 2, 9)
		data = struct.pack("<hBB", 0, 0, 0) + bytes([0x11, 0x22, 0x77, 0x00])
		riff = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
		ima = os.path.join(self.folder, "ima.wav")
		with open(ima, "wb") as stream:
			stream.write(b"RIFF" + struct.pack("<I", len(riff)) + riff)
		self.assertEqual(wavUtil.copyPlayable(ima, os.path.join(self.folder, "ima-pcm.wav")), "converted")
		with wave.open(os.path.join(self.folder, "ima-pcm.wav"), "rb") as result:
			self.assertEqual(result.getnframes(), 9)


class UpdaterAndStoreTests(unittest.TestCase):
	def test_versions(self):
		self.assertTrue(updater.isNewer("v1.1", "1.0"))
		self.assertFalse(updater.isNewer("1.0", "1.0.0"))
		self.assertEqual(updater.checksumFromFile("A" * 64 + "  x.nvda-addon"), "a" * 64)
		release = updater.releaseFromGithub(
			{
				"tag_name": "v1.2",
				"body": "## New\n- **Faster**",
				"assets": [{"name": "jawsMigrator-1.2.nvda-addon", "browser_download_url": "u", "size": 5}, {"name": "jawsMigrator-1.2.nvda-addon.sha256", "browser_download_url": "c"}],
			},
		)
		self.assertEqual((release.version, release.addonUrl, release.checksumUrl), ("1.2", "u", "c"))
		self.assertEqual(updater.notesAsText(release.notes), "New\n- Faster")

	def test_store_selection(self):
		catalog = [
			{"addonId": "CustomLabels", "channel": "beta", "addonVersionName": "3", "addonVersionNumber": {"major": 3}, "URL": "b", "sha256": "b" * 64, "minNVDAVersion": {"major": 2025}, "lastTestedVersion": {"major": 2026, "minor": 2}},
			{"addonId": "CustomLabels", "channel": "stable", "addonVersionName": "2", "addonVersionNumber": {"major": 2}, "URL": "s", "sha256": "a" * 64, "minNVDAVersion": {"major": 2025}, "lastTestedVersion": {"major": 2026, "minor": 2}},
			{"addonId": "tooNew", "channel": "stable", "addonVersionName": "9", "URL": "n", "sha256": "c" * 64, "minNVDAVersion": {"major": 2099}, "lastTestedVersion": {"major": 2099}},
		]
		picked = storeAddons.pickEntries(catalog, ["CustomLabels", "tooNew"])
		self.assertEqual(picked["CustomLabels"].url, "s")
		self.assertNotIn("tooNew", picked)


class JsdTests(unittest.TestCase):
	def test_docs(self):
		docs = jawsDocs.parseJsd(":Script SayWindowTitle\n:Synopsis Speaks the title of the window\n:Function Helper\n:Synopsis internal\n")
		self.assertEqual(jawsDocs.describe(docs, "SayWindowTitle"), "Speaks the title of the window")
		self.assertEqual(jawsDocs.describe(docs, "MoveToNextRegion"), "Move To Next Region")


class SelectionTests(unittest.TestCase):
	def plan(self):
		from jawsMigrator import jawsDetect

		options = migrator.MigrationOptions(jaws=jawsDetect.JawsInstallation("2026"), language="enu")
		plan = migrator.MigrationPlan(options=options, index=None, facts=None)
		plan.settings = settingsMap.mapSettings(jawsFiles.parseIni("[options]\nTypingEcho=1\nKeyboardType=Laptop\n"))
		plan.schemes = [schemeMap.ConvertedScheme("Web RentACrowd (from JAWS)", "Web RentACrowd", ""), schemeMap.ConvertedScheme("Classic (from JAWS)", "Classic", "")]
		eloquence = voices.VoiceProfile(name="Eloquence", primarySynthesizer="eloq")
		mobile = voices.VoiceProfile(name="Microsoft Mobile", primarySynthesizer="MSMobile")
		apollo = voices.VoiceProfile(name="Apollo 2", primarySynthesizer="apollo2")
		plan.profiles = [
			migrator.ProfilePlan("Eloquence", eloquence, {}, {"LinkVoice": "Shelly", "NormalVoice": "*|0|0"}, voices.NvdaVoiceOption("ibmeci", "IBMTTS"), primary=True),
			migrator.ProfilePlan("Microsoft Mobile", mobile, {}, {"LinkVoice": "*|15%|0", "HeadingLevel1Voice": "*|5%|0"}, voices.NvdaVoiceOption("oneCore", "OneCore")),
			migrator.ProfilePlan("Apollo 2", apollo, {}, {}, None),
		]
		plan.sleepCandidates = [("baseball", ["baseball"])]
		plan.sounds = ["start.wav"]
		plan.jawsKeyboardLayout = "laptop"
		plan.keyboardLayouts = keyPlan.keyboardLayouts(KeyPlanTests.layoutsJkm)
		plan.facts =type("Facts", (), {"classicSpeech": type("Classic", (), {"installed": True, "usable": True})()})()
		return plan

	def test_items(self):
		items = {item.key: item for item in selection.buildItems(self.plan())}
		self.assertIn("setting:nvda:keyboard.speakTypedCharacters", items)
		self.assertIn("scheme:Web RentACrowd (from JAWS)", items)
		self.assertFalse(items["profile:Apollo 2"].available)
		self.assertIn("alias:LinkVoice", items)
		self.assertIn("alias:HeadingLevel1Voice", items)
		self.assertNotIn("alias:NormalVoice", items)
		self.assertFalse(items["other:sounds"].default)
		self.assertIn("sleep:baseball", items)
		self.assertEqual(items["setting:nvda:keyboard.keyboardLayout"].category, selection.KEYBOARD)
		self.assertEqual(items["setting:nvda:keyboard.speakTypedCharacters"].category, selection.KEYBOARD)
		self.assertTrue(items["keyboard:layout:laptop"].default)
		self.assertFalse(items["keyboard:layout:desktop"].default)
		self.assertIn("keyboard:layout:classic laptop", items)

	def test_keyboard_layouts_chosen(self):
		plan = self.plan()
		items = {item.key: item for item in selection.buildItems(plan)}
		chosen = selection.Selection()
		chosen.set(items["keyboard:layout:desktop"], True)
		chosen.set(items["keyboard:quickNav"], False)
		selection.apply(plan, chosen)
		self.assertEqual(plan.options.keyboardLayouts, ["desktop", "laptop"])
		self.assertFalse(plan.options.quickNavLetters)
		self.assertTrue(plan.options.keyboard)
		self.assertEqual([layout.name for layout in plan.chosenKeyboardLayouts()], ["Desktop", "Laptop"])

	def test_choice_round_trip_and_apply(self):
		plan = self.plan()
		items = {item.key: item for item in selection.buildItems(plan)}
		chosen = selection.Selection()
		chosen.set(items["setting:nvda:keyboard.keyboardLayout"], False)
		chosen.set(items["scheme:Classic (from JAWS)"], False)
		chosen.set(items["alias:HeadingLevel1Voice"], False)
		chosen.set(items["profile:Eloquence"], False)
		chosen.set(items["other:sounds"], True)
		chosen.set(items["sleep:baseball"], False)
		restored = selection.Selection.fromDict(chosen.toDict())
		selection.apply(plan, restored)
		keys = [change.key for change in plan.settings.changes]
		self.assertNotIn("keyboard.keyboardLayout", keys)
		self.assertIn("keyboard.speakTypedCharacters", keys)
		self.assertEqual(plan.options.schemes, ["Web RentACrowd (from JAWS)"])
		self.assertEqual(plan.options.voiceAliases, ["LinkVoice"])
		self.assertEqual(plan.options.voiceProfiles, ["Microsoft Mobile"])
		self.assertEqual(plan.options.voiceChoice, -1)
		self.assertTrue(plan.options.sounds)
		self.assertEqual(plan.options.sleepApps, [])
		self.assertTrue(plan.options.selectionApplied)

	def test_untouched_choice_changes_nothing(self):
		plan = self.plan()
		selection.apply(plan, selection.Selection())
		self.assertIsNone(plan.options.schemes)
		self.assertFalse(plan.options.selectionApplied)


if __name__ == "__main__":
	unittest.main()
