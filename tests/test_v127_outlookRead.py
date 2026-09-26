# Unit tests for version 1.27, from a tester's answer on issue 23 ("When I open a message Jaws doesn't automatically
# read unless I press the arrow keys"). Asked whether JAWS's "Messages Automatically Read" was checked, the tester found
# it in Outlook's QuickSettings (Insert+V), Reading Options: "Messages Automatically Read  not checked". JAWS 2026 keeps
# that option in the application's settings: Outlook 2007.qs, which Outlook.qs includes, has
# ReadingOptions.MessagesAutomaticallyRead as [NonJCFOptions] MessageSayAllVerbosity, and Outlook.jss reads it with
# GetNonJCFOption("MessageSayAllVerbosity") to start Say All when a message opens (ShouldMessageSayAll). JAWS 2026's own
# SETTINGS\enu\Outlook.jcf has MessageSayAllVerbosity=1, so the tester's own Outlook.jcf turns it off. Version 1.26 gave
# reading a message as it opens a check box of its own, off unless turned on; nothing took it from JAWS.
# - settingsMap.mapOutlookSettings: a migration takes the option into that check box, the user's Outlook.jcf over
#   JAWS's own, as JAWS layers them. "Your settings only" takes it only from the user's file, "shared settings only"
#   only from JAWS's.
# - migrator: it is in the plan with the Settings Center options, so the wizard lists it and it can be left out, and a
#   migration writes it into the assistant's settings (state.json), which the assistant applies after the wizard.
# - report: the report lists it.
# The JAWS files are made in a temporary folder, as JAWS 2026 has them; one test reads JAWS 2026's own files when they
# are on this computer. The migration runs against the imitation NVDA in tests/fakeNvda.py.
# Run: python -m unittest tests.test_v127_outlookRead -v

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import fakeNvda  # noqa: E402
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import (  # noqa: E402
	jawsDetect,
	jawsFiles,
	jawsIndex,
	migrator,
	outlookMessages,
	selection,
	settingsMap,
	systemCheck,
)

#: JAWS 2026's own SETTINGS\enu\Outlook.jcf, the lines around the option (lines 126-131).
SHARED_OUTLOOK_JCF = """[NonJCFOptions]
; set to 0 to comply with other products and eexpected Office365 behavoirs, can enable in QuickSettings:
MessageHeaderVerbosity=0
MessageTitleVerbosity=1
MessageElementsVerbosity=1
; set to 1 to comply with other products and expected Office365 behaviors, can enable in QuickSettings:
MessageSayAllVerbosity=1
MessageLinkCountIndication=0
InformationBarVerbosity=1

[Information]
Title=Outlook
"""
#: The tester's Outlook.jcf, as QuickSettings writes it with "Messages Automatically Read" not checked.
TESTER_OUTLOOK_JCF = "[NonJCFOptions]\nMessageSayAllVerbosity=0\n"
#: JAWS 2026's ConfigNames.ini: classic Outlook is outlook.exe, new Outlook olk.exe.
CONFIG_NAMES = "[ConfigNames]\noutlook=Outlook\nolk=Outlook Modern\n"
#: What the settings list says, from JAWS's option.
READ_ON = 'Read an Outlook message from the top when it opens: on, as JAWS\'s "Messages Automatically Read"'
READ_OFF = 'Read an Outlook message from the top when it opens: off, as JAWS\'s "Messages Automatically Read"'


def readChange(plan_or_result):
	"""The planned change of the assistant's read-on-open setting, or None."""
	result = getattr(plan_or_result, "settings", plan_or_result)
	matches = [change for change in result.changes if change.target == settingsMap.ASSISTANT and change.key == outlookMessages.READ_KEY]
	return matches[0] if matches else None


class JawsTest(unittest.TestCase):
	"""A JAWS 2026 in a temporary folder, with Freedom Scientific's Outlook.jcf."""

	def setUp(self):
		self.root = tempfile.mkdtemp(prefix="jawsMigrator-v127-")
		self.addCleanup(shutil.rmtree, self.root, True)
		self.jaws = jawsDetect.JawsInstallation(
			version="2026",
			userRoot=os.path.join(self.root, "user", "2026"),
			sharedRoot=os.path.join(self.root, "shared", "2026"),
			primaryLanguage="enu",
		)
		self.shared = os.path.join(self.jaws.sharedSettingsDir, "enu")
		self.user = os.path.join(self.jaws.userSettingsDir, "enu")
		os.makedirs(self.shared)
		os.makedirs(self.user)
		self.write(self.shared, "Outlook.jcf", SHARED_OUTLOOK_JCF)
		self.write(self.shared, "ConfigNames.ini", CONFIG_NAMES)
		self.write(self.shared, "Default.jcf", "[options]\nTypingEcho=1\n")
		self.configDir = os.path.join(self.root, "nvda")
		os.makedirs(self.configDir)

	def write(self, folder, name, text):
		with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\r\n") as stream:
			stream.write(text)

	def plan(self, scope=jawsIndex.BOTH):
		options = migrator.MigrationOptions(jaws=self.jaws, language="enu", scope=scope)
		index = jawsIndex.buildIndex(self.jaws, "enu")
		return migrator.buildPlan(options, index, systemCheck.SystemFacts(configDir=self.configDir), inNvda=False)


class MappingTests(JawsTest):
	def test_the_testers_jaws_reads_no_message_as_it_opens(self):
		# Issue 23: the tester's own Outlook.jcf has it off, over JAWS's own, which has it on.
		self.write(self.user, "Outlook.jcf", TESTER_OUTLOOK_JCF)
		change = readChange(self.plan())
		self.assertIsNotNone(change)
		self.assertIs(change.value, False)
		self.assertEqual(change.path, (outlookMessages.READ_KEY,))
		self.assertEqual(change.label, READ_OFF)
		self.assertEqual(change.source, "your Outlook.jcf, [NonJCFOptions] MessageSayAllVerbosity=0")

	def test_jaws_as_it_comes_reads_a_message_as_it_opens(self):
		change = readChange(self.plan())
		self.assertIs(change.value, True)
		self.assertEqual(change.label, READ_ON)
		self.assertEqual(change.source, "JAWS's shared Outlook.jcf, [NonJCFOptions] MessageSayAllVerbosity=1")

	def test_the_users_own_on_over_jaws_off(self):
		self.write(self.shared, "Outlook.jcf", SHARED_OUTLOOK_JCF.replace("MessageSayAllVerbosity=1", "MessageSayAllVerbosity=0"))
		self.write(self.user, "Outlook.jcf", "[nonjcfoptions]\nmessagesayallverbosity=1\n")
		change = readChange(self.plan())
		self.assertIs(change.value, True)
		self.assertEqual(change.source, "your Outlook.jcf, [NonJCFOptions] MessageSayAllVerbosity=1")

	def test_a_users_outlook_jcf_without_the_option_leaves_jaws_own(self):
		# QuickSettings writes only what the user changed; a user file with other options has JAWS's value.
		self.write(self.user, "Outlook.jcf", "[NonJCFOptions]\nMessageHeaderVerbosity=1\n")
		self.assertIs(readChange(self.plan()).value, True)

	def test_your_settings_only(self):
		# Only what the user changed in JAWS: nothing when the user never changed it.
		self.assertIsNone(readChange(self.plan(jawsIndex.USER)))
		self.write(self.user, "Outlook.jcf", TESTER_OUTLOOK_JCF)
		self.assertIs(readChange(self.plan(jawsIndex.USER)).value, False)

	def test_shared_settings_only(self):
		self.write(self.user, "Outlook.jcf", TESTER_OUTLOOK_JCF)
		change = readChange(self.plan(jawsIndex.SHARED))
		self.assertIs(change.value, True)
		self.assertTrue(change.source.startswith("JAWS's shared"))

	def test_no_outlook_settings_changes_nothing(self):
		os.remove(os.path.join(self.shared, "Outlook.jcf"))
		self.assertIsNone(readChange(self.plan()))
		# New Outlook's settings are for olk.exe, which NVDA's Outlook support isn't for.
		self.write(self.shared, "Outlook Modern.jcf", SHARED_OUTLOOK_JCF)
		self.assertIsNone(readChange(self.plan()))

	def test_a_value_jaws_writes_oddly(self):
		result = settingsMap.MappingResult()
		settingsMap.mapOutlookSettings(jawsFiles.parseIni("[NonJCFOptions]\nMessageSayAllVerbosity=0 ;\n", inlineComments=True), None, result)
		self.assertIs(readChange(result).value, False)
		result = settingsMap.MappingResult()
		settingsMap.mapOutlookSettings(jawsFiles.parseIni("[NonJCFOptions]\nMessageSayAllVerbosity=\n"), jawsFiles.parseIni(SHARED_OUTLOOK_JCF, inlineComments=True), result)
		self.assertIs(readChange(result).value, True, "a value JAWS can't read leaves JAWS's own")

	def test_nvda_and_classic_speech_leave_it_alone(self):
		# Only the assistant writes it: NVDA's configuration and ClassicSpeech's take their own targets.
		self.assertNotIn(settingsMap.ASSISTANT, (settingsMap.NVDA, settingsMap.CLASSIC_SPEECH))
		self.assertEqual(outlookMessages.READ_KEY, "readOutlookMessagesOnOpen")


class ChoiceTests(JawsTest):
	def test_listed_with_the_settings_and_can_be_left_out(self):
		self.write(self.user, "Outlook.jcf", TESTER_OUTLOOK_JCF)
		plan = self.plan()
		items = {item.key: item for item in selection.buildItems(plan)}
		key = f"setting:{settingsMap.ASSISTANT}:{outlookMessages.READ_KEY}"
		self.assertIn(key, items)
		item = items[key]
		self.assertEqual(item.category, selection.SETTINGS)
		self.assertTrue(item.default)
		self.assertEqual(item.label, f"{READ_OFF} (JAWS: your Outlook.jcf, [NonJCFOptions] MessageSayAllVerbosity=0)")
		chosen = selection.Selection()
		chosen.set(item, False)
		selection.apply(plan, chosen)
		self.assertIsNone(readChange(plan))
		self.assertIn("general.playStartAndExitSounds", [change.key for change in plan.settings.changes], "the rest stay")

	def test_in_the_plan_nvda_writes(self):
		plan = self.plan()
		self.assertIn(readChange(plan), plan.finalSettingChanges())


class MigrationTests(JawsTest):
	"""The migration, carried out against the imitation NVDA."""

	def setUp(self):
		super().setUp()
		nvdaRoot = os.path.join(self.root, "fakeNvda")
		self.nvdaConfigDir, appDir = fakeNvda.makeNvdaFolders(nvdaRoot)
		self.conf, _current = fakeNvda.install(self.nvdaConfigDir, appDir, None)
		from jawsMigrator import state

		self.state = state
		state.forget()
		self.addCleanup(state.forget)

	def migrate(self, returnPlan=False, **choices):
		options = migrator.MigrationOptions(
			jaws=self.jaws,
			language="enu",
			voice=False,
			classicSchemes=False,
			classicSettings=False,
			dictionaries=False,
			symbols=False,
			keyboard=False,
			appProfiles=False,
			archive=False,
		)
		for name, value in choices.items():
			setattr(options, name, value)
		index = jawsIndex.buildIndex(self.jaws, "enu")
		plan = migrator.buildPlan(options, index, systemCheck.SystemFacts(configDir=self.nvdaConfigDir), inNvda=False)
		migration = migrator.Migration(plan)
		migration._applyEverything()
		return (plan, migration.result) if returnPlan else migration.result

	def test_the_testers_migration_turns_it_off(self):
		self.state.set(outlookMessages.READ_KEY, True)
		self.write(self.user, "Outlook.jcf", TESTER_OUTLOOK_JCF)
		result = self.migrate()
		self.assertIs(self.state.load().get(outlookMessages.READ_KEY), False)
		self.assertFalse(outlookMessages.readWanted(self.state.load()))
		self.assertTrue(outlookMessages.wanted(self.state.load()), "links, lists and headings stay as JAWS says them")
		self.assertIn(READ_OFF, [change.label for change in result.applied])
		# Saved in the assistant's file, where the assistant reads it when NVDA starts.
		from jawsMigrator import nvdaEnv

		with open(os.path.join(nvdaEnv.addonDataDir(), "state.json"), encoding="utf-8") as stream:
			self.assertIs(json.load(stream)[outlookMessages.READ_KEY], False)
		self.assertNotIn(outlookMessages.READ_KEY, json.dumps(self.conf.base), "not in NVDA's configuration")

	def test_jaws_as_it_comes_turns_it_on(self):
		result = self.migrate()
		self.assertTrue(outlookMessages.readWanted(self.state.load()))
		self.assertIn(READ_ON, [change.label for change in result.applied])

	def test_without_settings_center_it_stays_as_it_was(self):
		self.write(self.user, "Outlook.jcf", TESTER_OUTLOOK_JCF)
		self.state.set(outlookMessages.READ_KEY, True)
		self.migrate(settings=False)
		self.assertIs(self.state.get(outlookMessages.READ_KEY), True)

	def test_the_report_lists_it(self):
		from jawsMigrator import report

		self.write(self.user, "Outlook.jcf", TESTER_OUTLOOK_JCF)
		plan, result = self.migrate(returnPlan=True)
		_html, text = report.build(plan, result)
		self.assertIn("The assistant's own settings (NVDA's Settings, JAWS Migration Assistant)", text)
		self.assertIn(f"{READ_OFF} (from your Outlook.jcf, [NonJCFOptions] MessageSayAllVerbosity=0)", text)


@unittest.skipUnless(
	os.path.isfile(os.path.join(jawsDetect.programDataFolder(), "Freedom Scientific", "JAWS", "2026", "SETTINGS", "enu", "Outlook.jcf")),
	"needs JAWS 2026's own files",
)
class Jaws2026Tests(unittest.TestCase):
	def test_jaws_2026s_own_outlook_settings(self):
		shared = os.path.join(jawsDetect.programDataFolder(), "Freedom Scientific", "JAWS", "2026", "SETTINGS", "enu", "Outlook.jcf")
		ini = jawsFiles.readIni(shared, inlineComments=True)
		result = settingsMap.MappingResult()
		settingsMap.mapOutlookSettings(None, ini, result)
		self.assertIs(readChange(result).value, True, "JAWS 2026 reads a message as it opens, as it comes")
		result = settingsMap.MappingResult()
		settingsMap.mapOutlookSettings(jawsFiles.parseIni(TESTER_OUTLOOK_JCF), ini, result)
		self.assertIs(readChange(result).value, False, "the tester's JAWS doesn't")

	def test_quick_settings_keep_it_in_outlook_jcf(self):
		scripts = os.path.join(jawsDetect.programDataFolder(), "Freedom Scientific", "JAWS", "2026", "Scripts")
		with open(os.path.join(scripts, "Outlook 2007.qs"), encoding="utf-8") as stream:
			text = stream.read()
		start = text.index('<Setting ID="ReadingOptions.MessagesAutomaticallyRead"')
		self.assertIn('<SettingsFile Section="NonJCFOptions" Name="MessageSayAllVerbosity" />', text[start : text.index("</Setting>", start)])
		with open(os.path.join(scripts, "Outlook.qs"), encoding="utf-8") as stream:
			self.assertIn('<Include File="Outlook 2007.qs" />', stream.read())


if __name__ == "__main__":
	unittest.main()
