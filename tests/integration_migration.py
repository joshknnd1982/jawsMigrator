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
	from jawsMigrator import backup, jawsIndex, migrator, nvdaApply, state, systemCheck

	nvdaApply.scriptExists = lambda module, className, script: True
	facts = systemCheck.gatherFacts()
	facts.classicSpeech.installed = True
	facts.classicSpeech.usable = True
	jaws = facts.jaws[0]
	index = jawsIndex.buildIndex(jaws, jaws.primaryLanguage, facts.leasey)
	options = migrator.MigrationOptions(jaws=jaws, language=jaws.primaryLanguage, sounds=True)
	plan = migrator.buildPlan(options, index, facts, inNvda=True)
	options.sleepApps = [name for name, _exes in plan.sleepCandidates]
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
	check(os.path.isfile(os.path.join(configDir, "profiles", "JAWS settings.ini")), "the JAWS settings profile was created")
	profile = json.load(open(os.path.join(configDir, "profiles", "JAWS settings.ini"), encoding="utf-8"))
	check(profile.get("keyboard", {}).get("keyboardLayout") in ("laptop", "desktop"), f"keyboard layout set in the profile: {profile.get('keyboard', {}).get('keyboardLayout')}")
	check(profile.get("speech", {}).get("synth") == "ibmeci", f"the profile speaks with IBMTTS: {profile.get('speech', {}).get('synth')}")
	ibm = profile.get("speech", {}).get("ibmeci", {})
	check(ibm.get("rate") == 95 and ibm.get("variant") == "1", f"Eloquence Reed at rate 95 in the profile: {ibm}")
	check(conf.base.get("speech", {}).get("synth") == "espeak", "the normal configuration kept its synthesizer")
	classic = conf.base.get("classicSpeech", {})
	registry = json.loads(classic.get("voiceProfileData", "{}"))
	check("ibmeci" in registry and "reviewObjectNavigation" in registry["ibmeci"], f"ClassicSpeech voice profiles for IBMTTS: {list(registry.get('ibmeci', {}))}")
	review = registry.get("ibmeci", {}).get("reviewObjectNavigation", {})
	check(review.get("overrides", {}).get("variant") == "5" or review.get("baseline", {}).get("variant") == "5", f"JAWS cursor voice is Glen: {review}")
	schemes = os.path.join(configDir, "ClassicSpeech", "Schemes")
	names = sorted(os.listdir(schemes)) if os.path.isdir(schemes) else []
	check(len(names) >= 20, f"{len(names)} scheme folders written")
	rent = os.path.join(schemes, "Web RentACrowd (from JAWS)", "scheme.json")
	if os.path.isfile(rent):
		data = json.load(open(rent, encoding="utf-8"))
		link = data["items"].get("state.INTERNAL_LINK") or data["items"].get("role.LINK", {})
		check("voice" in link and "ibmeci" in link["voice"]["bySynth"], f"Rent-A-Crowd link voice for IBMTTS: {link}")
		heading = data["items"].get("role.HEADING.1", {})
		print("  heading 1 voice:", heading)
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
	check(len(saved.get("soundReplacements", {})) >= 10 and saved.get("jawsSoundsEnabled"), f"JAWS sounds: {len(saved.get('soundReplacements', {}))}")
	check(os.path.isfile(result.reportPath), f"report written: {result.reportPath}")
	check(bool(result.archiveFolder) and os.path.isdir(result.archiveFolder), "JAWS settings archived")
	check(os.path.isfile(os.path.join(result.outputFolder, "jaws-index.json")), "index saved")
	voicesFiles = [name for name in os.listdir(result.outputFolder) if name.endswith(".classicspeech-voices")]
	packages = [name for name in os.listdir(result.outputFolder) if name.endswith(".classicspeech-scheme")]
	check(voicesFiles and packages, f"{len(voicesFiles)} voice files and {len(packages)} scheme packages exported")

	# Undo everything from the backup.
	message = migrator.restore(result.backup)
	print("Restore:", message)
	check(not os.path.isfile(os.path.join(configDir, "profiles", "JAWS settings.ini")), "restore removed the JAWS settings profile")
	check(not os.path.isdir(os.path.join(schemes, "Web RentACrowd (from JAWS)")), "restore removed the schemes")
	check("toggleScreenCurtain" in open(os.path.join(configDir, "gestures.ini"), encoding="utf-8").read() and "elementsList" not in open(os.path.join(configDir, "gestures.ini"), encoding="utf-8").read(), "restore put gestures.ini back")
	check(len(backup.listBackups(os.path.join(configDir, "jawsMigrator"))) == 2, "a safety backup was made before restoring")
	print()
	print(f"{len(failures)} failures" if failures else "All checks passed")
	shutil.rmtree(root, ignore_errors=True)
	frame.Destroy()
	return 1 if failures else 0


if __name__ == "__main__":
	sys.exit(main())
