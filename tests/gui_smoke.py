# Drives the migration wizard through every step outside NVDA, with stand-ins for NVDA's modules.
# Needs wxPython and a JAWS installation (or JAWS settings) on this computer. Nothing is changed:
# the wizard stops at its last step before the migration would start.
# Run: python tests/gui_smoke.py

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

import wx  # noqa: E402

import nvdaStubs  # noqa: E402

messages = nvdaStubs.spoken


def stubModules(frame):
	nvdaStubs.install(frame)


def pump(seconds=0.2):
	end = time.time() + seconds
	while time.time() < end:
		wx.Yield()
		time.sleep(0.01)


def main():
	app = wx.App()
	frame = wx.Frame(None)
	stubModules(frame)
	from jawsMigrator import nvdaApply, systemCheck
	from jawsMigrator.gui import wizard

	nvdaApply.scriptExists = lambda module, className, script: True
	facts = systemCheck.gatherFacts()
	facts.synths = [("ibmeci", "IBMTTS"), ("sapi5", "Microsoft Speech API version 5"), ("oneCore", "Windows OneCore voices"), ("espeak", "eSpeak NG")]
	facts.configWritable = True
	facts.classicSpeech.installed = True
	facts.classicSpeech.usable = True
	facts.classicSpeech.version = "1.16"
	dialog = wizard.MigrationWizard(frame, facts)
	dialog.Show()
	pump()
	visited = []
	for _step in range(15):
		page = dialog.pages[dialog.current]
		visited.append(page.title)
		if page is dialog.summaryPage:
			break
		dialog.onNext(None)
		deadline = time.time() + 60
		while dialog.busy and time.time() < deadline:
			pump(0.1)
		pump()
	print("Visited:", " > ".join(visited))
	plan = dialog.plan
	options = plan.options
	print("Scope:", options.scope, "| target:", options.target, options.profileName)
	print("Voice choice:", plan.chosenVoice.label if plan.chosenVoice else None)
	print("Profiles:", [p.name for p in plan.selectedProfiles()])
	print("Schemes chosen:", len(plan.selectedSchemes()), "active:", options.activeClassicScheme)
	print("Keys:", len(plan.keys.bindings), "| sounds:", options.sounds, "| add-ons:", options.addonsToInstall)
	print()
	print(dialog.summaryText())
	print()
	print("Message boxes:", nvdaStubs.boxes[:5])
	print("Spoken:", nvdaStubs.spoken[:20])
	dialog.Destroy()
	frame.Destroy()
	app.ExitMainLoop()


if __name__ == "__main__":
	main()
