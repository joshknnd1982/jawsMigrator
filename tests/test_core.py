# Unit tests for the parts of the JAWS Migration Assistant that do not need NVDA.
# They use small made-up JAWS files, so they run anywhere.
# Run: python -m unittest discover -s tests -p "test_*.py"

import os
import shutil
import struct
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import (  # noqa: E402
	backup,
	dictMap,
	jawsDocs,
	jawsFiles,
	keyPlan,
	safety,
	schemeMap,
	settingsMap,
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


if __name__ == "__main__":
	unittest.main()
