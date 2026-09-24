# Runs a complete migration of this computer's JAWS settings into an imitation NVDA in a
# temporary folder, then checks what was written. Nothing outside the temporary folder changes.
# Needs wxPython and JAWS (or JAWS settings) on this computer.
# Run: python tests/integration_migration.py

import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(__file__))

import wx  # noqa: E402

import fakeNvda  # noqa: E402


def main():
	app = wx.App()
	app.SetAppName("jawsMigrator integration test")
	frame = wx.Frame(None)
	root = tempfile.mkdtemp(prefix="jawsMigrator-test-")
	configDir, appDir = fakeNvda.makeNvdaFolders(root)
	conf, current = fakeNvda.install(configDir, appDir, frame)
	from jawsMigrator import backup, classicSounds, jawsIndex, migrator, nvdaApply, state, systemCheck, wavUtil

	# An add-on with settings in its own folder and in NVDA's settings folder, as many add-ons have.
	someAddon = os.path.join(configDir, "addons", "someAddon")
	os.makedirs(someAddon)
	with open(os.path.join(someAddon, "manifest.ini"), "w", encoding="utf-8") as stream:
		stream.write('name = someAddon\nsummary = "Some add-on"\nversion = 1.0\n')
	with open(os.path.join(someAddon, "settings.json"), "w", encoding="utf-8") as stream:
		stream.write('{"volume": 1}')
	os.makedirs(os.path.join(configDir, "someAddonData"))
	with open(os.path.join(configDir, "someAddonData", "data.txt"), "w", encoding="utf-8") as stream:
		stream.write("original data")
	# An earlier migration (version 1.2) put the JAWS settings into a profile that turns on when NVDA starts.
	earlierProfile = os.path.join(configDir, "profiles", "JAWS settings.ini")
	earlierValues = {"speech": {"ibmeci": {"rate": 100}}, "documentFormatting": {"reportClickable": False}}
	os.makedirs(os.path.dirname(earlierProfile))
	with open(earlierProfile, "w", encoding="utf-8") as stream:
		json.dump(earlierValues, stream)
	state.update({"jawsProfileName": "JAWS settings", "activateJawsProfileAtStartup": True})
	conf.manualActivateProfile("JAWS settings")
	# It also left empty application profiles, one for a web site that can never turn a profile on.
	for leftover in ("JAWS - theoldreader.com", "JAWS - explorer"):
		open(os.path.join(configDir, "profiles", leftover + ".ini"), "w").close()
	conf.triggersToProfiles["app:explorer"] = "JAWS - explorer"
	keptProfile = os.path.join(configDir, "profiles", "JAWS - youtube.ini")
	with open(keptProfile, "w", encoding="utf-8") as stream:
		json.dump({"documentFormatting": {"reportHeadings": False}}, stream)

	nvdaApply.scriptExists = lambda module, className, script: True
	facts = systemCheck.gatherFacts()
	facts.classicSpeech.installed = True
	facts.classicSpeech.usable = True
	jaws = facts.jaws[0]
	index = jawsIndex.buildIndex(jaws, jaws.primaryLanguage, facts.leasey)
	options = migrator.MigrationOptions(jaws=jaws, language=jaws.primaryLanguage, sounds=True)
	plan = migrator.buildPlan(options, index, facts, inNvda=True)
	options.sleepApps = [name for name, _exes in plan.sleepCandidates]
	print("Application settings: profiles", {name: plan.appExecutables.get(name) for name in plan.appSettings}, "skipped", plan.appSkipped, "sleep", plan.sleepCandidates)
	choices = (options.activeClassicScheme, options.classicVoices)
	# The user chooses the scheme to turn on and the ClassicSpeech Voice Profiles; here they choose both.
	options.activeClassicScheme = plan.jawsSchemeName()
	options.classicVoices = True
	print("Plan: settings", len(plan.settings.changes), "keys", len(plan.keys.bindings), "profiles", [p.name for p in plan.selectedProfiles()], "schemes", len(plan.selectedSchemes()))
	progress = []
	finished = {}
	migration = migrator.Migration(plan, progress=progress.append, done=lambda result: finished.setdefault("result", result))
	migration.start()
	deadline = time.time() + 180
	while "result" not in finished and time.time() < deadline:
		wx.Yield()
		time.sleep(0.02)
	result = finished.get("result")
	failures = []

	def check(condition, message):
		print(("PASS " if condition else "FAIL ") + message)
		if not condition:
			failures.append(message)

	check(result is not None, "the migration finished")
	if result is None:
		return 1
	print("Progress:", progress)
	print("Messages:", result.messages[:12])
	check(result.succeeded, f"no error ({result.error})")
	check(result.backup is not None and os.path.isdir(result.backup.path), "a backup was made")
	# By default the JAWS settings go into NVDA's normal configuration.
	check(options.target == migrator.TARGET_NORMAL, "a migration writes into NVDA's normal configuration by default")
	normal = json.load(open(os.path.join(configDir, "nvda.ini"), encoding="utf-8"))
	check(normal.get("keyboard", {}).get("keyboardLayout") in ("laptop", "desktop"), f"keyboard layout set in the normal configuration: {normal.get('keyboard', {}).get('keyboardLayout')}")
	check(normal.get("speech", {}).get("synth") == "ibmeci", f"the normal configuration speaks with IBMTTS: {normal.get('speech', {}).get('synth')}")
	ibm = normal.get("speech", {}).get("ibmeci", {})
	check(choices == ("", False), f"a migration turns on no scheme and no Voice Profiles unless the user chooses them: {choices}")
	# JAWS keeps Eloquence's speed, 95 (shown as 64 percent). IBMTTS gives its rate percentages speeds 40 to 156,
	# so JAWS's speed is NVDA's 47, not 64 (which would be speed 114, faster than JAWS).
	check(ibm.get("rate") == 47 and ibm.get("pitch") == 65 and ibm.get("variant") == "1", f"Eloquence Reed at JAWS's speed 95 (NVDA 47) in the normal configuration: {ibm}")
	check(conf.base.get("general", {}).get("playStartAndExitSounds") is False, "NVDA plays no sounds when it starts or exits, as JAWS")
	# The earlier JAWS profile: kept as it was, no longer turned on at startup, and off now.
	check(json.load(open(earlierProfile, encoding="utf-8")) == earlierValues, "the earlier JAWS settings profile is kept as it was")
	check(nvdaApply.activeManualProfile() is None, f"the earlier JAWS settings profile was turned off: {nvdaApply.activeManualProfile()}")
	state.forget()
	check(state.get("activateJawsProfileAtStartup") is False, "the earlier JAWS settings profile no longer turns on when NVDA starts")
	retired = [message for message in result.messages if "no longer turns on when NVDA starts" in message]
	reportText = open(result.reportPath, encoding="utf-8").read() if os.path.isfile(result.reportPath) else ""
	check(retired and "no longer turns on when NVDA starts" in reportText, f"the messages and the report say so: {retired}")
	# Application profiles: only for programs NVDA can recognize, and none that would hold nothing.
	profilesFolder = os.path.join(configDir, "profiles")
	# The profiles this migration made; "JAWS - youtube" is the earlier one kept for its settings.
	appProfiles = [name[:-4] for name in os.listdir(profilesFolder) if name.startswith(migrator.APP_PROFILE_PREFIX) and name.endswith(".ini") and name != "JAWS - youtube.ini"]
	empty = []
	for name in appProfiles:
		text = open(os.path.join(profilesFolder, name + ".ini"), encoding="utf-8").read()
		values = json.loads(text) if text.strip() else {}
		values.pop("schemaVersion", None)
		if not values:
			empty.append(name)
	check(not empty, f"no empty application profiles: made {appProfiles}, empty {empty}")
	leftovers = [name for name in ("JAWS - theoldreader.com", "JAWS - explorer") if os.path.exists(os.path.join(profilesFolder, name + ".ini"))]
	check(not leftovers and "app:explorer" not in conf.triggersToProfiles, f"empty profiles an earlier migration left are removed, with their triggers: {leftovers}")
	check(os.path.isfile(keptProfile), "a profile from an earlier migration that holds settings is kept")
	triggered = set(conf.triggersToProfiles.values())
	check(all(name in triggered or any(name in message for message in result.messages) for name in appProfiles), f"each application profile turns on in its program, or the report says why: {conf.triggersToProfiles}")
	check(all(any(configName in message for message in result.messages) for configName in plan.appSkipped), f"application settings NVDA can't use are listed: {plan.appSkipped}")
	classic = conf.base.get("classicSpeech", {})
	registry = json.loads(classic.get("voiceProfileData", "{}"))
	written = registry.get("ibmeci", {})
	check(sorted(written) == ["mouse", "reviewObjectNavigation"], f"ClassicSpeech Voice Profiles only where JAWS uses another person: {sorted(written)}")
	review = written.get("reviewObjectNavigation", {})
	check(review.get("overrides") == {"variant": "5"}, f"JAWS cursor voice is Glen, with no fixed rate, pitch or volume: {review.get('overrides')}")
	schemes = os.path.join(configDir, "ClassicSpeech", "Schemes")
	names = sorted(os.listdir(schemes)) if os.path.isdir(schemes) else []
	check(len(names) >= 20, f"{len(names)} scheme folders written")
	rent = os.path.join(schemes, "Web RentACrowd (from JAWS)", "scheme.json")
	if os.path.isfile(rent):
		data = json.load(open(rent, encoding="utf-8"))
		link = data["items"].get("state.INTERNAL_LINK") or data["items"].get("role.LINK", {})
		check("voice" in link and "ibmeci" in link["voice"]["bySynth"], f"Rent-A-Crowd link voice for IBMTTS: {link}")
		voiced = [record for settings in data["items"].values() for record in (settings.get("voice") or {}).get("bySynth", {}).values()]
		prosody = [record for record in voiced if set(record.get("overrides", {})) - {"voice", "variant"}]
		check(voiced and not prosody, f"{len(voiced)} scheme voices, none with a fixed rate, pitch or volume: {prosody[:2]}")
	logFile = os.path.join(result.outputFolder, "debug.log")
	logText = open(logFile, encoding="utf-8").read() if os.path.isfile(logFile) else ""
	check("== Voice ==" in logText and "rate 95" in logText and "Input gestures" in logText and "== end ==" in logText, f"a detailed debug log was written: {len(logText.splitlines())} lines")
	check("-> normal configuration" in logText and "no longer turns on when NVDA starts" in logText, "the debug log names the configuration each setting went to, and the earlier profile")
	sounds = os.path.join(schemes, "SayAll Text With Sounds (from JAWS)", "Sounds")
	check(os.path.isdir(sounds) and len(os.listdir(sounds)) > 3, f"sound scheme sounds copied: {os.listdir(sounds) if os.path.isdir(sounds) else None}")
	switches = json.loads(classic.get("schemeData", "{}"))
	check(switches.get("activeScheme") == options.activeClassicScheme, f"active ClassicSpeech scheme: {switches}")
	gestures = open(os.path.join(configDir, "gestures.ini"), encoding="utf-8").read()
	check(result.gesturesAdded > 50 and "toggleScreenCurtain" in gestures, f"{result.gesturesAdded} gestures added, user's own gesture kept")
	check(os.path.isfile(os.path.join(result.outputFolder, "gestures.ini.before-migration")), "gestures.ini copied before the migration")
	state.forget()
	saved = json.load(open(os.path.join(configDir, "jawsMigrator", "state.json"), encoding="utf-8"))
	check(sorted(saved.get("sleepApps", [])) == sorted(options.sleepApps and ["baseball", "football", "freightfate", "press"]), f"sleep apps: {saved.get('sleepApps')}")
	record = saved.get("classicNvdaSounds") or {}
	schemeFolders = [name for name in os.listdir(schemes) if os.path.isfile(os.path.join(schemes, name, "scheme.json"))]
	check(
		len(record.get("sounds", {})) >= 10 and len(record.get("schemes", {})) == len(schemeFolders),
		f"JAWS sounds for {len(record.get('sounds', {}))} NVDA sounds, through {len(record.get('schemes', {}))} of {len(schemeFolders)} ClassicSpeech schemes",
	)
	activeFolder = os.path.join(schemes, options.activeClassicScheme)

	def activeItems():
		return json.load(open(os.path.join(activeFolder, "scheme.json"), encoding="utf-8"))["items"]

	focusSound = activeItems().get("nvdaSound.focusMode", {}).get("sound", "")
	check(bool(focusSound) and wavUtil.isPlayable(os.path.join(activeFolder, focusSound)), f"the active scheme plays {focusSound} when NVDA switches to focus mode")
	library = os.path.join(schemes, classicSounds.JAWS_SOUNDS_SCHEME, "Sounds")
	libraryCount = len(os.listdir(library)) if os.path.isdir(library) else 0
	check(libraryCount == len(classicSounds.uniqueSounds(index.wavFiles())), f"every JAWS sound was copied into ClassicSpeech: {libraryCount}")
	nvdaCopies = os.path.join(configDir, "jawsMigrator", "nvdaSounds")
	check(os.path.isdir(nvdaCopies) and any(os.listdir(os.path.join(nvdaCopies, name)) for name in os.listdir(nvdaCopies)), "a copy of NVDA's own sounds is kept")
	check(os.path.isfile(result.reportPath), f"report written: {result.reportPath}")
	check(bool(result.archiveFolder) and os.path.isdir(result.archiveFolder), "JAWS settings archived")
	check(os.path.isfile(os.path.join(result.outputFolder, "jaws-index.json")), "index saved")
	voicesFiles = [name for name in os.listdir(result.outputFolder) if name.endswith(".classicspeech-voices")]
	packages = [name for name in os.listdir(result.outputFolder) if name.endswith(".classicspeech-scheme")]
	check(voicesFiles and packages, f"{len(voicesFiles)} voice files and {len(packages)} scheme packages exported")
	backedUp = {entry["relative"] for entry in result.backup.files}
	check(
		{"addons/someAddon/settings.json", "someAddonData/data.txt", "nvda.ini"} <= backedUp and result.backup.original,
		f"the backup holds add-ons and their settings, and is the original: {len(backedUp)} files, add-ons {[a['name'] for a in result.backup.addons]}",
	)

	# NVDA's own sounds back, and JAWS sounds again, quickly, outside a migration.
	outcome = migrator.restoreNvdaSounds()
	print("Restore NVDA's own sounds:", outcome.message)
	check(outcome.succeeded and not any(key.startswith("nvdaSound.") for key in activeItems()), "restoring NVDA's own sounds takes every JAWS sound out of the schemes")
	check(len(os.listdir(library)) == libraryCount, "the JAWS sounds copied into ClassicSpeech stay")
	check(not classicSounds.isApplied(state.get(classicSounds.STATE_KEY)), "the record of JAWS sounds is cleared")
	backupsBefore = len(backup.listBackups(os.path.join(configDir, "jawsMigrator")))
	outcome = migrator.useJawsSounds(facts)
	print("Use JAWS sounds:", outcome.message)
	check(outcome.succeeded and "nvdaSound.browseMode" in activeItems(), "JAWS sounds can be turned on again in one step")
	check(len(backup.listBackups(os.path.join(configDir, "jawsMigrator"))) == backupsBefore + 1, "NVDA's settings and add-ons are backed up first")

	# Afterwards an add-on is installed (as the recommended ones are), and add-on settings change.
	pending = os.path.join(configDir, "addons", "customLabels.pendingInstall")
	os.makedirs(pending)
	with open(os.path.join(pending, "manifest.ini"), "w", encoding="utf-8") as stream:
		stream.write("name = customLabels\nversion = 2.0\n")
	with open(os.path.join(configDir, "addonsState.json"), "w", encoding="utf-8") as stream:
		json.dump({"pendingInstallsSet": ["customLabels"]}, stream)
	with open(os.path.join(someAddon, "settings.json"), "w", encoding="utf-8") as stream:
		stream.write('{"volume": 9}')
	with open(os.path.join(configDir, "someAddonData", "data.txt"), "w", encoding="utf-8") as stream:
		stream.write("changed data")

	# Undo everything from the backup.
	backupsBefore = len(backup.listBackups(os.path.join(configDir, "jawsMigrator")))
	outcome = migrator.restore(result.backup)
	print("Restore:", outcome.message)
	check(not os.path.isdir(pending) and outcome.restartNeeded, "restore removed the add-on installed after the backup")
	check(open(os.path.join(someAddon, "settings.json"), encoding="utf-8").read() == '{"volume": 1}', "restore put the add-on's own settings back")
	check(open(os.path.join(configDir, "someAddonData", "data.txt"), encoding="utf-8").read() == "original data", "restore put the add-on's data back")
	check(outcome.failed == [], f"nothing failed: {outcome.failed}")
	check(json.load(open(os.path.join(configDir, "nvda.ini"), encoding="utf-8")).get("speech", {}).get("synth") == "espeak", "restore put the normal configuration back")
	check(json.load(open(earlierProfile, encoding="utf-8")) == earlierValues, "restore kept the earlier JAWS settings profile, as the backup has it")
	state.forget()
	check(state.get("activateJawsProfileAtStartup") is True, "restore put back its startup setting")
	check(not os.path.isdir(os.path.join(schemes, "Web RentACrowd (from JAWS)")), "restore removed the schemes")
	check("toggleScreenCurtain" in open(os.path.join(configDir, "gestures.ini"), encoding="utf-8").read() and "elementsList" not in open(os.path.join(configDir, "gestures.ini"), encoding="utf-8").read(), "restore put gestures.ini back")
	check(len(backup.listBackups(os.path.join(configDir, "jawsMigrator"))) == backupsBefore + 1, "a safety backup was made before restoring")
	print()
	print(f"{len(failures)} failures" if failures else "All checks passed")
	shutil.rmtree(root, ignore_errors=True)
	frame.Destroy()
	return 1 if failures else 0


if __name__ == "__main__":
	sys.exit(main())
