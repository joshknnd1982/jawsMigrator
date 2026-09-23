# Tests for the NVDA integration and safety fixes: add-on restores left to NVDA's restart,
# ClassicSpeech settings never written while it isn't running, the voice dictionary following the
# voice, sleep mode, profile triggers, the command layer's busy guard, rollbacks, JAWS sounds
# records, the safety backup, disabled add-ons, the normal configuration, profile names, timers,
# the normal configuration as the default target, and application profiles.
# Everything runs against the imitation NVDA in tests/fakeNvda.py, in temporary folders.
# Run: python -B -m unittest tests.test_integration_fixes -v

import json
import os
import shutil
import stat
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import fakeNvda  # noqa: E402
import nvdaStubs  # noqa: E402


def fakeAddon(name="ClassicSpeech", version="1.10", path=r"X:\nvda\addons\ClassicSpeech", **flags):
	"""An add-on as NVDA's addonHandler lists it."""
	values = {"isDisabled": False, "isPendingRemove": False, "isPendingInstall": False, "isRunning": True, "isBlocked": False}
	values.update(flags)
	return types.SimpleNamespace(name=name, manifest={"summary": name, "version": version}, path=path, **values)


class FakeNvdaTest(unittest.TestCase):
	"""A fresh imitation NVDA over a temporary settings folder for every test."""

	classicSpeechRunning = True

	def setUp(self):
		self.root = tempfile.mkdtemp(prefix="jawsMigrator-fixes-")
		self.addCleanup(shutil.rmtree, self.root, True)
		self.configDir, self.appDir = fakeNvda.makeNvdaFolders(self.root)
		self.conf, self.current = fakeNvda.install(self.configDir, self.appDir, None, classicSpeechRunning=self.classicSpeechRunning)
		from jawsMigrator import state

		state.forget()
		self.addCleanup(state.forget)

	def writeProfile(self, name, values):
		folder = os.path.join(self.configDir, "profiles")
		os.makedirs(folder, exist_ok=True)
		path = os.path.join(folder, name + ".ini")
		with open(path, "w", encoding="utf-8") as stream:
			json.dump(values, stream)
		return path

	def addonFolder(self, folder, name, version, files=None):
		path = os.path.join(self.configDir, "addons", folder)
		os.makedirs(path, exist_ok=True)
		with open(os.path.join(path, "manifest.ini"), "w", encoding="utf-8") as stream:
			stream.write(f'name = {name}\nsummary = "{name}"\nversion = {version}\n')
		for relative, text in (files or {}).items():
			with open(os.path.join(path, relative), "w", encoding="utf-8") as stream:
				stream.write(text)
		return path


# -- finding 1: add-on changes from a restore are finished by NVDA when it restarts ----------------


class AddonChangesWaitForRestartTests(FakeNvdaTest):
	def test_reloading_the_configuration_leaves_pending_addon_changes_to_nvda(self):
		from jawsMigrator import nvdaApply

		addonHandler = sys.modules["addonHandler"]
		calls = []
		addonHandler.initialize = lambda: calls.append("initialize")
		self.addCleanup(delattr, addonHandler, "initialize")
		# core.resetConfiguration runs addonHandler.initialize, which finishes pending installs and removals.
		sys.modules["core"].resetConfiguration = lambda: addonHandler.initialize()
		nvdaApply.resetToSavedConfiguration()
		self.assertEqual(calls, [], "NVDA's add-on start-up work did not run while NVDA and its add-ons run")
		addonHandler.initialize()
		self.assertEqual(calls, ["initialize"], "afterwards addonHandler.initialize is NVDA's own again")

	def test_restore_records_addon_changes_only_after_nvda_reloaded_its_settings(self):
		from jawsMigrator import backup, migrator, nvdaApply, nvdaEnv

		self.addonFolder("someAddon", "someAddon", "1.0")
		info = backup.createBackup(self.configDir, nvdaEnv.addonDataDir(), "", "before")
		# Afterwards the add-on is updated and another one installed.
		self.addonFolder("someAddon", "someAddon", "2.0")
		self.addonFolder("newer", "newer", "1.0")
		staged = os.path.join(self.configDir, "addons", "someAddon.pendingInstall")
		seen = {}
		reset = nvdaApply.resetToSavedConfiguration

		def watchedReset():
			seen["staged"] = os.path.isdir(staged)
			seen["state"] = backup.readAddonState(self.configDir)
			reset()

		nvdaApply.resetToSavedConfiguration = watchedReset
		try:
			outcome = migrator.restore(info)
		finally:
			nvdaApply.resetToSavedConfiguration = reset
		self.assertFalse(seen["staged"], "no add-on was waiting to be installed while NVDA reloaded")
		self.assertNotIn("newer", seen["state"].get("pendingRemovesSet", []), "nor waiting to be removed")
		self.assertTrue(os.path.isdir(staged), "the older version waits for NVDA's restart")
		self.assertIn("newer", backup.readAddonState(self.configDir)["pendingRemovesSet"])
		self.assertTrue(outcome.restartNeeded)
		self.assertIn("finished when NVDA restarts", outcome.message)


# -- finding 2: ClassicSpeech's settings are never written into nvda.ini --------------------------


class ClassicSpeechNotRunningTests(FakeNvdaTest):
	classicSpeechRunning = False

	def test_its_settings_are_never_written_into_nvda_ini(self):
		from jawsMigrator import nvdaApply

		self.assertFalse(nvdaApply.classicSpeechRunning())
		with self.assertRaises(nvdaApply.ClassicSpeechNotRunning):
			nvdaApply.classicSpeechSection()
		with self.assertRaises(nvdaApply.ClassicSpeechNotRunning):
			nvdaApply.applyClassicSpeechSettings([])
		self.assertNotIn("classicSpeech", self.conf.base)

	def test_restoring_nvda_sounds_is_refused_and_changes_nothing(self):
		from jawsMigrator import backup, classicSounds, migrator, nvdaEnv, state

		# Installed but disabled: NVDA doesn't run it this session.
		sys.modules["addonHandler"].getAvailableAddons = lambda *args, **kwargs: [fakeAddon(isDisabled=True, isRunning=False)]
		record = {"version": 1, "schemes": {"Default": {"name": "Default", "items": {"nvdaSound.focusMode": {"sound": "Sounds/focus.wav", "sha256": "x"}}, "files": {}}}, "sounds": {"focusMode": "focus.wav"}, "enabledSchemes": True}
		state.set(classicSounds.STATE_KEY, record)
		backups = len(backup.listBackups(nvdaEnv.addonDataDir()))
		outcome = migrator.restoreNvdaSounds()
		self.assertFalse(outcome.succeeded)
		self.assertIn("Nothing was changed", outcome.message)
		self.assertEqual(state.get(classicSounds.STATE_KEY), record, "the record stays, so it can be finished later")
		self.assertEqual(len(backup.listBackups(nvdaEnv.addonDataDir())), backups)
		self.assertNotIn("classicSpeech", self.conf.base)

	def test_jaws_sounds_are_refused_when_it_does_not_run(self):
		from jawsMigrator import migrator

		facts = types.SimpleNamespace(classicSpeech=types.SimpleNamespace(installed=True, usable=True), jaws=[object()], jawsWithSettings=[])
		outcome = migrator.useJawsSounds(facts)
		self.assertFalse(outcome.succeeded)
		self.assertIn("Nothing was changed", outcome.message)
		self.assertNotIn("classicSpeech", self.conf.base)


class ClassicSpeechUsableTests(FakeNvdaTest):
	def info(self, *copies):
		from jawsMigrator import nvdaEnv

		return nvdaEnv.classicSpeechInfo(list(copies))

	def test_usable_only_while_it_runs_and_is_not_being_removed(self):
		from jawsMigrator.nvdaEnv import AddonState

		self.assertTrue(self.info(AddonState("ClassicSpeech", "ClassicSpeech", "1.10", running=True)).usable)
		for copy, words in (
			(AddonState("ClassicSpeech", "ClassicSpeech", "1.10", disabled=True), "disabled"),
			(AddonState("ClassicSpeech", "ClassicSpeech", "1.10", blocked=True), "incompatible"),
			(AddonState("ClassicSpeech", "ClassicSpeech", "1.10", running=True, pendingRemove=True), "will be removed"),
			(AddonState("ClassicSpeech", "ClassicSpeech", "1.11", pendingInstall=True), "will be installed"),
		):
			info = self.info(copy)
			self.assertTrue(info.installed)
			self.assertFalse(info.usable, words)
			self.assertIn(words, info.describe)

	def test_right_after_an_update_the_running_copy_is_usable(self):
		from jawsMigrator import nvdaEnv

		# NVDA lists the old copy (running, marked for removal) and the new one, whose isRunning NVDA
		# also reports as True because it only looks at the installed folder.
		sys.modules["addonHandler"].getAvailableAddons = lambda *args, **kwargs: [
			fakeAddon(version="1.10", isPendingRemove=True),
			fakeAddon(version="1.11", path=r"X:\nvda\addons\ClassicSpeech.pendingInstall", isPendingInstall=True),
		]
		info = nvdaEnv.classicSpeechInfo()
		self.assertTrue(info.usable)
		self.assertEqual((info.version, info.pendingVersion), ("1.10", "1.11"))
		self.assertIn("version 1.11 starts after NVDA restarts", info.describe)
		waiting = [addon for addon in nvdaEnv.installedAddons() if addon.pendingInstall]
		self.assertFalse(waiting[0].running)


class RestoringNvdaSoundsTests(FakeNvdaTest):
	def test_backs_up_first_and_keeps_what_could_not_be_taken_out(self):
		from jawsMigrator import backup, classicSounds, migrator, nvdaEnv, state

		folder = os.path.join(self.configDir, "ClassicSpeech", "Schemes", "Default")
		os.makedirs(os.path.join(folder, "Sounds"))
		with open(os.path.join(folder, "Sounds", "focus.wav"), "wb") as stream:
			stream.write(b"RIFF....WAVE")
		digest = classicSounds._sha256(os.path.join(folder, "Sounds", "focus.wav"))
		schemeFile = os.path.join(folder, "scheme.json")
		with open(schemeFile, "w", encoding="utf-8") as stream:
			json.dump({"format": "ClassicSpeech scheme", "version": 1, "name": "Default", "items": {"nvdaSound.focusMode": {"sound": "Sounds/focus.wav", "soundOnly": False}}}, stream)
		state.set(classicSounds.STATE_KEY, {"version": 1, "schemes": {"Default": {"name": "Default", "items": {"nvdaSound.focusMode": {"sound": "Sounds/focus.wav", "sha256": digest}}, "files": {"Sounds/focus.wav": digest}}}, "sounds": {"focusMode": "focus.wav"}})
		backups = len(backup.listBackups(nvdaEnv.addonDataDir()))
		os.chmod(schemeFile, stat.S_IREAD)  # kept open or locked by another program
		self.addCleanup(os.chmod, schemeFile, stat.S_IWRITE | stat.S_IREAD)
		outcome = migrator.restoreNvdaSounds()
		self.assertEqual(len(backup.listBackups(nvdaEnv.addonDataDir())), backups + 1, "NVDA's settings are backed up first")
		self.assertFalse(outcome.succeeded)
		self.assertIn("Try Restore NVDA's own sounds again", outcome.message)
		remaining = state.get(classicSounds.STATE_KEY)
		self.assertTrue(classicSounds.isApplied(remaining), "what couldn't be taken out stays recorded")
		os.chmod(schemeFile, stat.S_IWRITE | stat.S_IREAD)
		outcome = migrator.restoreNvdaSounds()
		self.assertTrue(outcome.succeeded, outcome.message)
		self.assertFalse(classicSounds.isApplied(state.get(classicSounds.STATE_KEY)))
		self.assertNotIn("nvdaSound.focusMode", classicSounds.readScheme(folder)["items"])
		self.assertFalse(os.path.exists(os.path.join(folder, "Sounds", "focus.wav")))


# -- finding 3: voice dictionary rules go into the chosen voice's dictionary ---------------------


class VoiceDictionaryTests(FakeNvdaTest):
	def test_rules_for_the_voice_go_into_the_chosen_voices_dictionary(self):
		from jawsMigrator import nvdaApply

		self.assertTrue(sys.modules["synthDriverHandler"].setSynth("ibmeci"))
		before = nvdaApply.liveDictionary("voice").fileName
		self.assertIn("65536", before, "IBMTTS starts with its first voice")
		messages = nvdaApply.applyVoice("ibmeci", "65537", "", None, {})
		self.assertIn("Voice: British English", messages)
		dictionary = nvdaApply.liveDictionary("voice")
		self.assertIn("65537", dictionary.fileName, "NVDA loaded the chosen voice's dictionary")
		entry = types.SimpleNamespace(pattern="JAWS", replacement="jaws", comment="", caseSensitive=False, type=0)
		self.assertEqual(nvdaApply.addDictionaryEntries("voice", [entry]), (1, ""))
		self.assertTrue(os.path.isfile(dictionary.fileName))
		self.assertFalse(os.path.isfile(before), "the other voice's dictionary is left alone")


# -- finding 4: sleep mode can be turned off --------------------------------------------------------


class SleepModeTests(FakeNvdaTest):
	def test_sleep_mode_is_set_once_so_the_user_can_turn_it_off(self):
		import jawsMigrator

		plugin = types.SimpleNamespace(_sleepApps={"notepad"})
		app = types.SimpleNamespace(appName="Notepad", sleepMode=False)
		focus = types.SimpleNamespace(appModule=app)
		jawsMigrator.GlobalPlugin._checkSleep(plugin, focus)
		self.assertTrue(app.sleepMode)
		# NVDA+Shift+Z: NVDA turns sleep mode off and sends the focus event again.
		app.sleepMode = False
		jawsMigrator.GlobalPlugin._checkSleep(plugin, focus)
		self.assertFalse(app.sleepMode, "sleep mode stays off")
		# The program started again: sleep mode comes back, as in JAWS.
		again = types.SimpleNamespace(appModule=types.SimpleNamespace(appName="notepad", sleepMode=False))
		jawsMigrator.GlobalPlugin._checkSleep(plugin, again)
		self.assertTrue(again.appModule.sleepMode)


# -- findings 5 and 6: profile triggers ---------------------------------------------------------------


class ProfileTriggerTests(FakeNvdaTest):
	def test_another_profiles_trigger_is_never_taken_over(self):
		from jawsMigrator import nvdaApply

		self.writeProfile("Word", {"speech": {"rate": 40}})
		self.conf.triggersToProfiles["app:winword"] = "Word"
		self.assertEqual(nvdaApply.setProfileTrigger("WINWORD", "JAWS - WINWORD"), (nvdaApply.TRIGGER_KEPT, "Word"))
		self.assertEqual(self.conf.triggersToProfiles["app:winword"], "Word")
		# A trigger for a profile that no longer exists is nobody's.
		self.conf.triggersToProfiles["app:notepad"] = "Gone"
		self.assertEqual(nvdaApply.setProfileTrigger("notepad", "JAWS - notepad"), (nvdaApply.TRIGGER_SET, ""))
		# The assistant's own trigger, from an earlier migration, is kept up to date.
		self.writeProfile("JAWS - notepad", {})
		self.assertEqual(nvdaApply.setProfileTrigger("notepad", "JAWS - Notepad"), (nvdaApply.TRIGGER_SET, ""))
		self.assertEqual(self.conf.triggersToProfiles["app:notepad"], "JAWS - Notepad")

	def test_triggers_are_read_again_after_files_were_put_back(self):
		from jawsMigrator import nvdaApply

		self.assertEqual(nvdaApply.setProfileTrigger("notepad", "JAWS - notepad"), (nvdaApply.TRIGGER_SET, ""))
		# A backup puts profileTriggers.ini back as it was: without that trigger.
		with open(os.path.join(self.configDir, "profileTriggers.ini"), "w", encoding="utf-8") as stream:
			json.dump({}, stream)
		self.assertIn("app:notepad", self.conf.triggersToProfiles)
		nvdaApply.resetToSavedConfiguration()
		self.assertEqual(self.conf.triggersToProfiles, {})


# -- finding 7: a restore waits for the assistant ------------------------------------------------------


class RestoreBusyTests(FakeNvdaTest):
	def test_restore_is_refused_while_busy_and_keeps_the_assistant_busy(self):
		import jawsMigrator
		from jawsMigrator.gui import restoreDialog

		plugin = types.SimpleNamespace(
			_secure=False,
			_busy=True,
			_factsCache=None,
			applyRuntimeSettings=lambda: None,
			_refuseWhileSettingsOpen=lambda action: False,
		)
		seen = []
		shown = restoreDialog.showRestoreDialog
		restoreDialog.showRestoreDialog = lambda: seen.append(plugin._busy)
		self.addCleanup(setattr, restoreDialog, "showRestoreDialog", shown)
		jawsMigrator.GlobalPlugin.openRestore(plugin)
		self.assertEqual(seen, [], "no restore while a migration or a JAWS sounds action runs")
		self.assertIn("busy", nvdaStubs.spoken[-1])
		plugin._busy = False
		jawsMigrator.GlobalPlugin.openRestore(plugin)
		self.assertEqual(seen, [True], "the assistant is busy while the restore dialog is open")
		self.assertFalse(plugin._busy)

	def test_restore_waits_for_nvda_settings_dialogs(self):
		import jawsMigrator
		from jawsMigrator.gui import restoreDialog

		plugin = types.SimpleNamespace(
			_secure=False,
			_busy=False,
			_factsCache=None,
			applyRuntimeSettings=lambda: None,
			_refuseWhileSettingsOpen=lambda action: True,
		)
		seen = []
		shown = restoreDialog.showRestoreDialog
		restoreDialog.showRestoreDialog = lambda: seen.append(True)
		self.addCleanup(setattr, restoreDialog, "showRestoreDialog", shown)
		jawsMigrator.GlobalPlugin.openRestore(plugin)
		self.assertEqual(seen, [], "no restore while an NVDA settings dialog could save its old values over it")
		self.assertFalse(plugin._busy)


# -- finding 8: a partial rollback is not reported as complete ----------------------------------------


class RollbackTests(FakeNvdaTest):
	def test_a_rollback_with_failures_says_so(self):
		from jawsMigrator import backup, migrator, nvdaEnv

		migration = migrator.Migration(types.SimpleNamespace())
		migration.result.backup = backup.createBackup(self.configDir, nvdaEnv.addonDataDir(), "", "before")
		restoreBackup = backup.restoreBackup
		backup.restoreBackup = lambda *args, **kwargs: backup.RestoreResult(failed=["nvda.ini: in use by another program"])
		self.addCleanup(setattr, backup, "restoreBackup", restoreBackup)
		migration._rollBack()
		self.assertFalse(migration.result.rolledBack)
		self.assertTrue(any("could not be put back" in message and "nvda.ini: in use" in message for message in migration.result.messages), migration.result.messages)
		self.assertFalse(any(message == "Your previous NVDA settings were restored from the backup." for message in migration.result.messages))


# -- finding 10: the safety backup before a restore holds unsaved settings -----------------------------


class RestoreSafetyBackupTests(FakeNvdaTest):
	def test_settings_changed_in_this_session_are_in_the_safety_backup(self):
		from jawsMigrator import backup, migrator, nvdaEnv

		self.conf.save()
		older = backup.createBackup(self.configDir, nvdaEnv.addonDataDir(), "", "older")
		self.conf.base["speech"]["rate"] = 77  # changed in NVDA's settings, not saved yet
		outcome = migrator.restore(older)
		before = backup.listBackups(nvdaEnv.addonDataDir())[0]
		self.assertIn(before.name, outcome.message)
		with open(os.path.join(before.path, "config", "nvda.ini"), encoding="utf-8") as stream:
			self.assertEqual(json.load(stream)["speech"]["rate"], 77)


# -- finding 11: a disabled add-on put back over an installed copy -------------------------------------


class AddonPlanTests(FakeNvdaTest):
	def test_what_happens_to_a_disabled_addon_is_described_as_nvda_does_it(self):
		from jawsMigrator import backup

		info = backup.BackupInfo(path="x", addons=[{"name": "old", "version": "1.0", "folder": "old", "pendingInstall": False}], addonState={"disabledAddons": ["old"]})
		[action] = backup.planAddonRestore(info, [backup.AddonRecord("old", "2.0", r"X:\nvda\addons\old")])
		self.assertEqual(action.kind, backup.REINSTALL)
		self.assertIn("disable it again", action.description)
		self.assertNotIn("disabled as it was", action.description)
		[action] = backup.planAddonRestore(info, [])
		self.assertIn("disabled as it was", action.description)


# -- findings 12 and 13: profiles ----------------------------------------------------------------------


class ProfileWritingTests(FakeNvdaTest):
	def test_a_profile_leaves_the_normal_configuration_alone(self):
		from jawsMigrator import nvdaApply, settingsMap

		change = settingsMap.SettingChange(settingsMap.NVDA, ("general", "playStartAndExitSounds"), False, "Play sounds when starting or exiting NVDA: off", "test")
		with nvdaApply.writingTo("JAWS settings"):
			applied, failed = nvdaApply.applySettings([change], None)
		self.assertEqual(applied, [])
		self.assertIn("normal configuration only", failed[0][1])
		self.assertNotIn("general", self.conf.base)
		with nvdaApply.writingTo(None):
			applied, failed = nvdaApply.applySettings([change], None)
		self.assertEqual((applied, failed), ([change], []))
		self.assertIs(self.conf.base["general"]["playStartAndExitSounds"], False)

	def test_a_profile_name_differing_only_in_case_is_the_same_profile(self):
		from jawsMigrator import nvdaApply

		self.writeProfile("JAWS Settings", {})
		with nvdaApply.writingTo("jaws settings"):
			self.assertEqual(nvdaApply.writingConfigurationName(), "JAWS Settings")
		self.assertTrue(nvdaApply.activateProfile("JAWS SETTINGS"))
		self.assertEqual(nvdaApply.activeManualProfile(), "JAWS Settings")


# -- finding 14: timers stop when NVDA unloads the plugin ------------------------------------------------


class TrayIcon:
	def __init__(self, wx):
		self.toolsMenu = wx.Menu()
		self.preferencesMenu = wx.Menu()
		self.handler = wx.EvtHandler()

	def Bind(self, *args, **kwargs):
		self.handler.Bind(*args, **kwargs)


#: wxPython's application, made once for the whole test run.
_wxApp = None


class PluginTimerTests(unittest.TestCase):
	def test_nothing_scheduled_runs_after_nvda_unloads_the_plugin(self):
		import wx

		global _wxApp
		_wxApp = wx.GetApp() or wx.App()
		frame = wx.Frame(None)
		self.addCleanup(frame.Destroy)
		configDir = tempfile.mkdtemp(prefix="jawsMigrator-timers-")
		self.addCleanup(shutil.rmtree, configDir, True)
		nvdaStubs.install(frame)
		writePaths = types.SimpleNamespace(configDir=configDir)
		sys.modules["NVDAState"] = types.SimpleNamespace(WritePaths=writePaths, shouldWriteToDisk=lambda: True)
		sys.modules["globalVars"] = types.SimpleNamespace(appDir="", appArgs=types.SimpleNamespace(secure=False, configPath=configDir))
		frame.sysTrayIcon = TrayIcon(wx)
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
		import jawsMigrator

		jawsMigrator.state.forget()
		self.addCleanup(jawsMigrator.state.forget)
		jawsMigrator.state.update({"welcomeShown": False, "checkForUpdatesAutomatically": False})
		plugin = jawsMigrator.GlobalPlugin()
		timers = [plugin._startupProfileTimer, plugin._firstRunTimer, plugin._repairTimer]
		self.assertTrue(all(timer.IsRunning() for timer in timers))
		plugin.terminate()
		self.assertFalse(any(timer.IsRunning() for timer in timers), "the first-run offer, the startup profile and the repair never fire")


# -- the normal configuration by default, and an earlier JAWS profile -----------------------------------


class NormalConfigurationTests(FakeNvdaTest):
	def test_the_normal_configuration_is_the_default_target(self):
		from jawsMigrator import jawsDetect, migrator

		options = migrator.MigrationOptions(jaws=jawsDetect.JawsInstallation("2026"), language="enu")
		self.assertEqual(options.target, migrator.TARGET_NORMAL)

	def test_an_earlier_jaws_profile_no_longer_turns_on_at_startup(self):
		from jawsMigrator import migrator, nvdaApply, state

		path = self.writeProfile("JAWS settings", {"speech": {"rate": 100}})
		state.update({"jawsProfileName": "JAWS settings", "activateJawsProfileAtStartup": True})
		self.conf.manualActivateProfile("JAWS settings")
		migration = migrator.Migration(types.SimpleNamespace())
		updates = {}
		migration._retireEarlierJawsProfile(updates)
		self.assertEqual(updates, {"activateJawsProfileAtStartup": False})
		self.assertIsNone(nvdaApply.activeManualProfile(), "turned off now")
		self.assertTrue(os.path.isfile(path), "never deleted")
		[message] = migration.result.messages
		self.assertIn("no longer turns on when NVDA starts", message)
		self.assertIn("turned off now", message)

	def test_an_earlier_jaws_profile_turned_on_by_hand_is_only_mentioned(self):
		from jawsMigrator import migrator, nvdaApply, state

		self.writeProfile("JAWS settings", {"speech": {"rate": 100}})
		state.update({"jawsProfileName": "JAWS settings", "activateJawsProfileAtStartup": False})
		self.conf.manualActivateProfile("JAWS settings")
		migration = migrator.Migration(types.SimpleNamespace())
		updates = {}
		migration._retireEarlierJawsProfile(updates)
		self.assertEqual(updates, {})
		self.assertEqual(nvdaApply.activeManualProfile(), "JAWS settings")
		self.assertIn("right now", migration.result.messages[0])


# -- application profiles -----------------------------------------------------------------------------------


class AppProfileTests(FakeNvdaTest):
	def index(self, configNames=None):
		return types.SimpleNamespace(configNames=lambda: configNames or {})

	def test_only_programs_nvda_can_recognize(self):
		from jawsMigrator import migrator

		index = self.index({"windows os": ["shell32", "SHLWAPI", "shcore"], "chrome": ["chrome"], "whatsapp": ["5319275A.51895FA4EA97F!App", "WhatsApp.exe"]})
		self.assertEqual(migrator.appExecutables(index, "Chrome"), (["chrome"], ""))
		self.assertEqual(migrator.appExecutables(index, "WhatsApp"), (["whatsapp"], ""))
		for name in ("theoldreader.com", "Web.WhatsApp.com"):
			names, why = migrator.appExecutables(index, name)
			self.assertEqual(names, [])
			self.assertIn("web site", why)
		names, why = migrator.appExecutables(index, "Windows OS")
		self.assertEqual(names, [])
		self.assertIn("parts of Windows", why)
		names, why = migrator.appExecutables(index, "_core.cp312-win_amd64")
		self.assertEqual(names, [])
		self.assertIn("not the name of a program", why)
		self.assertEqual(migrator.appExecutables(index, "Deal or no deal"), (["deal or no deal"], ""))
		self.assertEqual(migrator.appExecutables(index, "1password"), (["1password"], ""))

	def test_empty_profiles_are_removed_and_other_profiles_triggers_kept(self):
		from jawsMigrator import migrator, nvdaApply, settingsMap

		migration = migrator.Migration(types.SimpleNamespace())
		same = settingsMap.SettingChange(settingsMap.NVDA, ("keyboard", "keyboardLayout"), "desktop", "Keyboard layout: desktop", "test")
		migration._writeAppProfile("notepad", types.SimpleNamespace(changes=[same]), ["notepad"])
		self.assertIsNone(nvdaApply.existingProfileName("JAWS - notepad"), "a profile the same as the normal configuration is removed")
		self.assertEqual((self.conf.triggersToProfiles, migration.result.appProfiles), ({}, []))
		self.assertIn("needs no profile", migration.result.messages[-1])
		laptop = settingsMap.SettingChange(settingsMap.NVDA, ("keyboard", "keyboardLayout"), "laptop", "Keyboard layout: laptop", "test")
		migration._writeAppProfile("notepad", types.SimpleNamespace(changes=[laptop]), ["notepad"])
		self.assertEqual(self.conf.triggersToProfiles, {"app:notepad": "JAWS - notepad"})
		self.assertEqual(migration.result.appProfiles, [("JAWS - notepad", ["notepad"], 1)])
		with open(os.path.join(self.configDir, "profiles", "JAWS - notepad.ini"), encoding="utf-8") as stream:
			self.assertEqual(json.load(stream)["keyboard"]["keyboardLayout"], "laptop")
		# Word already turns on the user's own profile: that trigger stays the user's.
		self.writeProfile("Word", {"speech": {"rate": 40}})
		self.conf.triggersToProfiles["app:winword"] = "Word"
		migration._writeAppProfile("WINWORD", types.SimpleNamespace(changes=[laptop]), ["winword"])
		self.assertEqual(self.conf.triggersToProfiles["app:winword"], "Word")
		self.assertEqual(migration.result.appProfiles[-1], ("JAWS - WINWORD", [], 1))
		self.assertIn('already turns on your profile "Word"', migration.result.messages[-1])

	def test_the_debug_log_names_the_configuration_each_setting_went_to(self):
		from jawsMigrator import debugLog, migrator, nvdaApply, settingsMap

		path = os.path.join(self.root, "debug.log")
		debugLog.start(path, "test")
		try:
			laptop = settingsMap.SettingChange(settingsMap.NVDA, ("keyboard", "keyboardLayout"), "laptop", "Keyboard layout: laptop", "test")
			with nvdaApply.writingTo(None):
				migrator._logApplied(*nvdaApply.applySettings([laptop], None))
			desktop = settingsMap.SettingChange(settingsMap.NVDA, ("keyboard", "keyboardLayout"), "desktop", "Keyboard layout: desktop", "test")
			with nvdaApply.writingTo("JAWS - notepad"):
				migrator._logApplied(*nvdaApply.applySettings([desktop], None), "notepad: ")
		finally:
			debugLog.stop()
		with open(path, encoding="utf-8") as stream:
			text = stream.read()
		self.assertIn("keyboard.keyboardLayout = 'laptop' -> normal configuration", text)
		self.assertIn("notepad: keyboard.keyboardLayout = 'desktop' -> JAWS - notepad", text)


if __name__ == "__main__":
	unittest.main()
