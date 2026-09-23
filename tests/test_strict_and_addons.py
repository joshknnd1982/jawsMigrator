# Unit tests for version 1.3's stricter JAWS mapping and for getting the newest add-ons.
# They use small made-up JAWS files and fake downloads, so they run anywhere.
# Run: python -m unittest tests.test_strict_and_addons -v

import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import addonUpdates, jawsFiles, nvdaEnv, schemeMap, settingsMap, storeAddons, updater  # noqa: E402


def ini(text):
	return jawsFiles.parseIni(text, inlineComments=True)


def values(result):
	return {change.key: change.value for change in result.changes}


#: JAWS's shared web verbosity table, as JAWS 2026 ships it (Medium level).
SHARED_WEB = (
	"[VirtualCursorVerbosity]\nVirtualCursorVerbosityLevel=1\nList=1|1|0\nTableOrGrid=1|1|1\nFrame=1|0|0\n"
	"ClickableElements=1|0|0\nMainRegion=1|1|0\nBannerRegion=1|0|0\n"
)


class ClickableTests(unittest.TestCase):
	"""NVDA says "clickable" only where JAWS does: at the High web verbosity level, by default."""

	def test_medium_level_is_not_clickable(self):
		shared = ini(SHARED_WEB)
		result = values(settingsMap.mapSettings(shared, shared, effective=True))
		self.assertIs(result["documentFormatting.reportClickable"], False)
		self.assertIs(result["documentFormatting.reportFrames"], False)
		self.assertIs(result["documentFormatting.reportLists"], True)
		self.assertIs(result["documentFormatting.reportLandmarks"], True)

	def test_high_level_is_clickable(self):
		text = SHARED_WEB.replace("VirtualCursorVerbosityLevel=1", "VirtualCursorVerbosityLevel=2")
		result = values(settingsMap.mapSettings(ini(text), ini(text), effective=True))
		self.assertIs(result["documentFormatting.reportClickable"], True)

	def test_older_jaws_without_the_row_uses_jaws_defaults(self):
		old = ini("[options]\nTypingEcho=1\n")
		result = values(settingsMap.mapSettings(old, old, effective=True))
		self.assertIs(result["documentFormatting.reportClickable"], False, "JAWS announces clickable only at High")
		self.assertIs(result["documentFormatting.reportFrames"], False)
		self.assertIs(result["documentFormatting.reportTables"], True)

	def test_your_settings_only_leaves_unchanged_rows(self):
		user = ini("[options]\nTypingEcho=1\n")
		merged = jawsFiles.mergeIni(ini(SHARED_WEB), user)
		result = values(settingsMap.mapSettings(user, merged))
		self.assertNotIn("documentFormatting.reportClickable", result)

	def test_a_changed_level_brings_every_row_at_that_level(self):
		user = ini("[VirtualCursorVerbosity]\nVirtualCursorVerbosityLevel=2\n")
		merged = jawsFiles.mergeIni(ini(SHARED_WEB), user)
		result = values(settingsMap.mapSettings(user, merged))
		self.assertIs(result["documentFormatting.reportClickable"], True)
		self.assertIs(result["documentFormatting.reportFrames"], True)

	def test_a_changed_verbosity_brings_its_output_modes(self):
		shared = ini("[options]\nVerbosity=0\n[OutputModes]\nTOOL_TIP=1|0|0|Tool Tip\n")
		user = ini("[options]\nVerbosity=2\n")
		result = values(settingsMap.mapSettings(user, jawsFiles.mergeIni(shared, user)))
		self.assertIs(result["presentation.reportTooltips"], False, "the Advanced column of the shared row")


class SettingsStrictnessTests(unittest.TestCase):
	def test_rapid_skim_read_is_not_a_preference(self):
		result = settingsMap.mapSettings(ini("[options]\nAllowRapidSkimRead=1\n"))
		self.assertNotIn("keyboard.allowSkimReadingInSayAll", values(result))
		self.assertTrue(any(item.key == "AllowRapidSkimRead" for item in result.notMigrated))

	def test_virtual_cursor_and_tables_come_from_osm(self):
		result = values(settingsMap.mapSettings(ini("[OSM]\nUseVirtualPCCursor=0\nTableDetection=0\n")))
		self.assertIs(result["virtualBuffers.enableOnPageLoad"], False)
		self.assertIs(result["documentFormatting.includeLayoutTables"], True)

	def test_six_dot_computer_braille_uses_a_table_nvda_has(self):
		text = "[Braille]\nPrimaryBrailleProfile=enu\nEightDotBraille=0\n[Braille Profiles]\nenu=0|20|US|US|0|0|0\n"
		result = values(settingsMap.mapSettings(ini(text), ini(text)))
		self.assertEqual(result["braille.translationTable"], "en-us-comp6.ctb")
		self.assertEqual(result["braille.inputTable"], "en-us-comp6.ctb")

	def test_single_digits_follow_jaws_whatever_the_number_processing(self):
		text = "[options]\nNumbers=0\nSingleDigitThreshold=5\n"
		result = values(settingsMap.mapSettings(ini(text), ini(text), classicSpeech=True))
		self.assertEqual(result["numberProcessingData.singleDigitsIfNumberContains"], "5")
		self.assertEqual(result["numberProcessingData.numberProcessingMode"], "synthesizer")

	def test_old_format_options_are_not_used(self):
		result = settingsMap.mapSettings(ini("[options]\nFormatAndText=1\nFont=1\nAttributes=1\n"))
		self.assertNotIn("documentFormatting.reportFontName", values(result))
		self.assertEqual({item.key for item in result.notMigrated} & {"FormatAndText", "Font", "Attributes"}, {"FormatAndText", "Font", "Attributes"})

	def test_font_and_attribute_reporting_follow_the_scheme(self):
		classic = ini(
			"[Information]\nTitle=Classic\n[Attribute Behavior Table]\n0X801=1|MessageVoice|||\ndefault=0|MessageVoice|||\n"
			"[Font Name Behavior Table]\ndefault=0|MessageVoice|||\n[Font Size Behavior Table]\ndefault=0|MessageVoice|||\n"
			"[Color Behavior Table]\ndefault=0|MessageVoice|||\n",
		)
		result = values(settingsMap.mapSettings(ini("[options]\nScheme=Classic\n"), scheme=classic, schemeChosen=True))
		self.assertIs(result["documentFormatting.reportFontName"], False)
		self.assertIs(result["documentFormatting.reportColor"], False)
		self.assertEqual(result["documentFormatting.fontAttributeReporting"], 0)
		attributes = ini(
			"[Information]\nTitle=Classic (Attributes and Font Info)\n[Attribute Behavior Table]\ndefault=1|MessageVoice|||\n"
			"[Font Name Behavior Table]\ndefault=1|MessageVoice|||\n",
		)
		result = values(settingsMap.mapSettings(ini("[Braille]\nBrailleShowMarking=2\n"), scheme=attributes, schemeChosen=True))
		self.assertIs(result["documentFormatting.reportFontName"], True)
		self.assertIs(result["documentFormatting.reportColor"], True, "no Color table: JAWS speaks colors")
		self.assertEqual(result["documentFormatting.fontAttributeReporting"], 3, "speech from the scheme, braille from the marking")

	def test_a_scheme_not_chosen_changes_nothing(self):
		scheme = ini("[Attribute Behavior Table]\ndefault=1|MessageVoice|||\n")
		result = values(settingsMap.mapSettings(ini("[options]\nTypingEcho=1\n"), scheme=scheme, schemeChosen=False))
		self.assertNotIn("documentFormatting.fontAttributeReporting", result)
		self.assertNotIn("documentFormatting.reportFontName", result)


class SchemeVoiceScopeTests(unittest.TestCase):
	"""A voice JAWS uses only for its announcement never reads the text in ClassicSpeech."""

	def convert(self, text):
		aliases = {"MessageVoice": "Glen|0|0", "LinkVoice": "Rocko|0|0", "NormalVoice": "*|0|0"}
		return schemeMap.convertScheme(ini(text), "Test.smf", lambda name: None, aliases)

	def test_announcement_voice_does_not_read_link_text(self):
		scheme = self.convert("[ControlType Behavior Table]\n47=1|NormalVoice||LinkVoice|\n[Attribute Behavior Table]\n0X88001=1|MessageVoice|||\n")
		self.assertNotIn("role.LINK", scheme.items)
		self.assertTrue(any("voice was left out" in note for note in scheme.notConverted))

	def test_text_voice_reads_link_text(self):
		scheme = self.convert("[ControlType Behavior Table]\n47=3|NormalVoice||LinkVoice|\n")
		self.assertEqual(scheme.items["role.LINK"].voiceAlias, "LinkVoice")

	def test_announcement_voice_for_a_state_is_kept(self):
		scheme = self.convert("[ControlState Behavior Table]\n16384=1|MessageVoice|||\n")
		self.assertEqual(scheme.items["state.VISITED"].voiceAlias, "MessageVoice")

	def test_clickable_sound_is_left_out(self):
		found = schemeMap.convertScheme(ini("[HTML Attribute Behavior Table]\nonclick=2|NormalVoice:clickable|OnClick1.wav||\n"), "T.smf", lambda name: "C:\\x\\" + name, {})
		self.assertNotIn("state.CLICKABLE", found.items)
		self.assertTrue(any("sound was left out" in note for note in found.notConverted))


class VersionTests(unittest.TestCase):
	def test_versions(self):
		self.assertEqual(addonUpdates.versionKey("v1.16"), (1, 16))
		self.assertEqual(addonUpdates.versionKey("2.0-beta"), (2, 0))
		self.assertIsNone(addonUpdates.versionKey("dev"))
		self.assertEqual(addonUpdates.compareVersions("1.16", "1.15"), 1)
		self.assertEqual(addonUpdates.compareVersions("1.2", "1.2.0"), 0)
		self.assertEqual(addonUpdates.compareVersions("20260826.0.0", "20261001.0.0"), -1)
		self.assertIsNone(addonUpdates.compareVersions("1.0", "dev"))

	def test_decide(self):
		self.assertEqual(addonUpdates.decide("X", "", "1.0", "GitHub"), (True, ""))
		self.assertTrue(addonUpdates.decide("X", "1.0", "1.1", "GitHub")[0])
		fetch, why = addonUpdates.decide("X", "1.1", "1.1", "GitHub")
		self.assertFalse(fetch)
		self.assertIn("already the newest", why)
		self.assertFalse(addonUpdates.decide("X", "2.0", "1.9", "GitHub")[0], "never a downgrade")
		self.assertFalse(addonUpdates.decide("X", "dev", "1.9", "GitHub")[0], "a version that can't be compared is left alone")

	def test_installed_versions(self):
		addons = [
			nvdaEnv.AddonState("ClassicSpeech", version="1.15", pendingRemove=True, running=True),
			nvdaEnv.AddonState("ClassicSpeech", version="1.16", pendingInstall=True),
			nvdaEnv.AddonState("customLabels", version="2.0"),
			nvdaEnv.AddonState("gone", version="1.0", pendingRemove=True),
		]
		self.assertEqual(addonUpdates.installedVersions(addons), {"classicspeech": "1.16", "customlabels": "2.0"})

	def test_addon_status(self):
		addons = [
			nvdaEnv.AddonState("ClassicSpeech", version="1.15", pendingRemove=True, running=True),
			nvdaEnv.AddonState("ClassicSpeech", version="1.16", pendingInstall=True),
			nvdaEnv.AddonState("customLabels", version="2.0", disabled=True),
			nvdaEnv.AddonState("gone", version="1.0", pendingRemove=True),
		]
		self.assertEqual(addonUpdates.addonStatus("classicspeech", addons), (addonUpdates.INSTALLED, "1.16"))
		self.assertEqual(addonUpdates.addonStatus("customLabels", addons), (addonUpdates.DISABLED, "2.0"))
		self.assertEqual(addonUpdates.addonStatus("gone", addons), (addonUpdates.REMOVING, "1.0"))
		self.assertEqual(addonUpdates.addonStatus("controlUsageAssistant", addons), (addonUpdates.MISSING, ""))
		self.assertEqual([addon.addonId for addon in addonUpdates.neededAddons()][:2], ["ClassicSpeech", "enhancedControlSupport"])


def bundle(folder, name, version):
	path = os.path.join(folder, f"{name}-{version}.nvda-addon")
	with zipfile.ZipFile(path, "w") as archive:
		archive.writestr("manifest.ini", f'name = {name}\nsummary = "{name}"\nversion = {version}\n')
	return path


class FetchNewestTests(unittest.TestCase):
	def setUp(self):
		self.folder = tempfile.mkdtemp()
		self.saved = (updater.fetchLatestRelease, updater.downloadRelease, storeAddons.fetchEntries, storeAddons.download, storeAddons.install)
		self.installed = []
		self.downloads = []

		def fetchLatestRelease(version, repository, session=None, product=updater.PRODUCT):
			self.assertEqual(repository, "joshknnd1982/classicspeech-nvda")
			return updater.Release(version="1.16", name="ClassicSpeech 1.16", notes="", pageUrl="", addonName="ClassicSpeech-1.16.nvda-addon")

		def downloadRelease(release, version, repository, folder, session=None):
			self.downloads.append(release.version)
			return bundle(folder, "ClassicSpeech", release.version)

		def fetchEntries(wanted, language="en"):
			entries = {}
			for addonId in wanted:
				if addonId == "missing":
					continue
				entries[addonId] = storeAddons.StoreEntry(addonId, addonId, "3.0", "https://example.invalid/x", "0" * 64, "stable")
			return entries

		def download(entry, folder):
			self.downloads.append(entry.addonId)
			return bundle(folder, entry.addonId, entry.version)

		updater.fetchLatestRelease = fetchLatestRelease
		updater.downloadRelease = downloadRelease
		storeAddons.fetchEntries = fetchEntries
		storeAddons.download = download
		storeAddons.install = lambda path: self.installed.append(os.path.basename(path))

	def tearDown(self):
		updater.fetchLatestRelease, updater.downloadRelease, storeAddons.fetchEntries, storeAddons.download, storeAddons.install = self.saved
		shutil.rmtree(self.folder, ignore_errors=True)

	def test_newest_versions_only_where_needed(self):
		addons = [
			nvdaEnv.AddonState("ClassicSpeech", version="1.15", running=True),
			nvdaEnv.AddonState("customLabels", version="3.0"),
			nvdaEnv.AddonState("customNotifications", version="2.5"),
		]
		wanted = ["ClassicSpeech", "customLabels", "customNotifications", "controlUsageAssistant", "missing"]
		fetched = addonUpdates.fetchNewest(wanted, self.folder, addons)
		self.assertEqual(sorted(item.addonId for item in fetched.downloads), ["ClassicSpeech", "controlUsageAssistant", "customNotifications"])
		self.assertTrue(any("customLabels 3.0 is already the newest" in note for note in fetched.notes), fetched.notes)
		self.assertTrue(any(error.startswith("missing:") for error in fetched.errors), fetched.errors)
		messages, errors = addonUpdates.installDownloads(fetched.downloads)
		self.assertEqual(errors, [])
		self.assertEqual(len(self.installed), 3)
		self.assertTrue(any("updated from version 1.15 to 1.16" in message for message in messages), messages)
		for item in fetched.downloads:
			self.assertFalse(os.path.exists(item.path), "each download is deleted after installing")

	def test_a_download_that_is_another_addon_is_refused(self):
		path = bundle(self.folder, "somethingElse", "1.0")
		item = addonUpdates.Download("ClassicSpeech", "ClassicSpeech", "1.16", path, "", addonUpdates.GITHUB)
		messages, errors = addonUpdates.installDownloads([item])
		self.assertEqual(messages, [])
		self.assertEqual(self.installed, [])
		self.assertIn("somethingElse", errors[0])
		self.assertFalse(os.path.exists(path))


class ClassicSpeechOfferTests(unittest.TestCase):
	"""The offer dialog: its text box is named by the label before it, and it can say not to offer again."""

	@classmethod
	def setUpClass(cls):
		import wx

		cls.app = wx.App.Get() or wx.App()

	def make(self, automatic):
		from jawsMigrator.gui import classicSpeechOffer

		dialog = classicSpeechOffer.ClassicSpeechOfferDialog(None, "Summary.", "&About ClassicSpeech:", classicSpeechOffer.EXPLANATION, "&Install ClassicSpeech", automatic)
		self.addCleanup(dialog.Destroy)
		return dialog

	def test_label_comes_before_its_text(self):
		import wx

		dialog = self.make(automatic=False)
		children = list(dialog.GetChildren())
		position = children.index(dialog.details)
		self.assertIsInstance(children[position - 1], wx.StaticText)
		self.assertEqual(children[position - 1].GetLabel(), "&About ClassicSpeech:")
		self.assertEqual(dialog.installButton.GetId(), wx.ID_YES)
		self.assertIsNone(dialog.dontOffer, "asked for, it is always offered")
		self.assertIn("newest release", dialog.details.GetValue())

	def test_automatic_offer_can_be_turned_off(self):
		dialog = self.make(automatic=True)
		self.assertFalse(dialog.dontOfferAgain)
		dialog.dontOffer.SetValue(True)
		self.assertTrue(dialog.dontOfferAgain)


class DictionaryRepairTests(unittest.TestCase):
	"""Rules versions 1.0 to 1.2 wrote are repaired once; the user's own rules are never touched."""

	OLD = (
		"#JAWS dictionary rules. From JAWS Default.jdf, line 3\n"
		"AN:\taccount number\t0\t0\n"
		"#From JAWS Default.jdf, line 4\n"
		"hello\thi\t0\t2\n"
		"\n"
		"#My own rule\n"
		"St.\tSaint\t0\t0\n"
		"#From JAWS x.jdf, line 9 (root word ***)\n"
		"\tstars\t0\t1\n"
		"#From JAWS y.jdf, line 2\n"
		"\tgone\t0\t1\n"
	)

	def test_repair_text(self):
		from jawsMigrator import dictRepair

		repaired, changed = dictRepair.repairText(self.OLD)
		self.assertEqual(changed, 3)
		lines = repaired.splitlines()
		self.assertIn("\\bAN:\taccount number\t0\t1", lines)
		self.assertIn("hello\thi\t0\t2", lines, "a right rule stays")
		self.assertIn("St.\tSaint\t0\t0", lines, "the user's own rule stays exactly as it is")
		self.assertIn("#My own rule", lines)
		self.assertIn("***\tstars\t0\t0", lines, "the asterisks come back from the comment")
		self.assertNotIn("\tgone\t0\t1", lines, "an empty pattern with nothing to keep is dropped")
		self.assertFalse(any("line 2" in line for line in lines), "with its comment")
		self.assertEqual(dictRepair.repairText(repaired)[1], 0, "repairing twice changes nothing")

	def test_repair_files(self):
		from jawsMigrator import dictRepair

		folder = tempfile.mkdtemp()
		try:
			voices = os.path.join(folder, "speechDicts", "voiceDicts.v1", "ibmeci")
			os.makedirs(voices)
			default = os.path.join(folder, "speechDicts", "default.dic")
			with open(default, "w", encoding="utf_8_sig") as stream:
				stream.write(self.OLD)
			untouched = os.path.join(voices, "ibmeci-enu.dic")
			with open(untouched, "w", encoding="utf_8_sig") as stream:
				stream.write("#mine\nfoo\tbar\t0\t0\n")
			before = os.path.getmtime(untouched)
			self.assertTrue(dictRepair.needsRepair(folder))
			result = dictRepair.repairDictionaries(folder)
			self.assertEqual((result.files, result.rewritten, result.failed), ([default], 3, []))
			self.assertFalse(dictRepair.needsRepair(folder))
			self.assertEqual(os.path.getmtime(untouched), before, "files without the assistant's rules are not rewritten")
		finally:
			shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
	unittest.main()
