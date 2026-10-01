"""Issue 49 (version 1.56) in a real NVDA: the tester's profiles, Settings, Speech, the settings ring and audio ducking.

The private NVDA is set up with ``python setup_issue49.py`` (its voice is a silent copy of Eloquence64RS 19.1.4's profile handling;
see that file) and started or restarted with ``python restart_nvda.py``. Then, from this folder, one of:

    python setup_issue49.py off      && python restart_nvda.py && python -m scenarios.s60 control
    python setup_issue49.py          && python restart_nvda.py && python -m scenarios.s60 fixed
    python setup_issue49.py ask      && python restart_nvda.py && python -m scenarios.s60 question

control  The tester's steps without the assistant's change: the voice's volume while typing in Edge (the migration's "JAWS - msedge"
         is turned on) and while reading a page (Custom Browse Mode's "browseMode" is on top of it), Settings opened from Edge with
         the volume turned down, and the page again.
fixed    The same steps with it, then the settings ring on a page, and the assistant's audio ducking key.
question The question about settings that already differ, asked once after NVDA starts, answered through its own dialog.
user     A profile of the user's own turned on by hand, with Settings, Speech opened on it: its volume is its own, and stays in it.

What is real: NVDA 2026.2's configuration profiles, its Settings dialog and its Speech panel (opened on the Speech category,
its Volume slider moved with the slider's own event, OK pressed), its settings ring scripts, and the assistant's code. What is
done by hand: Edge's profile is turned on and off with NVDA's own ProfileTrigger (what its app switching does), and
"browseMode" with config.conf.manualActivateProfile (what Custom Browse Mode does in browse mode); no Edge page is used.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from rig import Rig  # noqa: E402

PRELUDE = '''
import builtins, sys, types, config, wx, gui, synthDriverHandler, globalVars

if not hasattr(builtins, "T49"):
	class Edge(config.ProfileTrigger):
		spec = "app:msedge"

	class Tools:
		def __init__(self):
			self.edge = Edge()
			self.inEdge = False
			self.dialog = None

		def stack(self):
			return [(getattr(p, "name", None) or "normal configuration") + ("*" if getattr(p, "manual", False) else "") for p in config.conf.profiles]

		def typing(self):
			config.conf.manualActivateProfile(None)
			if not self.inEdge:
				self.edge.enter()
				self.inEdge = True

		def reading(self):
			if not self.inEdge:
				self.edge.enter()
				self.inEdge = True
			config.conf.manualActivateProfile("browseMode")

		def away(self):
			config.conf.manualActivateProfile(None)
			if self.inEdge:
				self.edge.exit()
				self.inEdge = False

		def held(self):
			out = {}
			for name in ("JAWS - msedge", "browseMode", "kitchen games"):
				profile = config.conf._getProfile(name)
				section = profile["speech"].get("eloquence", {}) if "speech" in profile else {}
				out[name] = {k: section[k] for k in ("volume", "rate", "pitch") if k in section}
			base = config.conf.profiles[0]["speech"].get("eloquence", {})
			out["base"] = {k: base[k] for k in ("volume", "rate", "pitch") if k in base}
			return out

		def look(self):
			synth = synthDriverHandler.getSynth()
			module = sys.modules.get("synthDrivers.eloquence")
			copies = {" > ".join(n): s.get("volume") for n, s in getattr(module, "_profile_settings_by_stack", {}).items()}
			return {"stack": self.stack(), "voice": synth.volume, "config": config.conf["speech"]["eloquence"]["volume"], "held": self.held(), "copies": copies}

		def open(self):
			gui.mainFrame.prePopup()
			dialog = gui.settingsDialogs.NVDASettingsDialog(gui.mainFrame, initialCategory=gui.settingsDialogs.SpeechSettingsPanel)
			dialog.Show()
			gui.mainFrame.postPopup()
			self.dialog = dialog
			panel = dialog.currentCategory
			return {"title": dialog.GetTitle(), "volumeSlider": panel.voicePanel.volumeSlider.GetValue()}

		def slide(self, value):
			slider = self.dialog.currentCategory.voicePanel.volumeSlider
			slider.SetValue(value)
			event = wx.CommandEvent(wx.wxEVT_SLIDER, slider.GetId())
			event.SetEventObject(slider)
			event.SetInt(value)
			slider.GetEventHandler().ProcessEvent(event)
			return synthDriverHandler.getSynth().volume

		def ok(self):
			self.dialog.onOk(wx.CommandEvent(wx.wxEVT_BUTTON, wx.ID_OK))
			self.dialog = None

		def ring(self, steps):
			import globalCommands
			commands = globalCommands.commands
			guard = 0
			while globalVars.settingsRing.currentSettingName.replace("&", "") != "Volume" and guard < 10:
				commands.script_nextSynthSetting(None)
				guard += 1
			for step in steps:
				(commands.script_increaseSynthSetting if step > 0 else commands.script_decreaseSynthSetting)(None)
			return synthDriverHandler.getSynth().volume

		def duck(self):
			# This NVDA is not an installed copy, so it can't duck: only that Windows call is imitated here, so that the assistant's
			# own toggle, and NVDA's configuration, run.
			import audioDucking
			from globalPlugins.jawsMigrator import duckingToggle
			applied = []
			audioDucking.isAudioDuckingSupported = lambda: True
			audioDucking.setAudioDuckingMode = lambda mode: applied.append(int(mode))
			toggled = duckingToggle.toggle()
			base = config.conf.profiles[0].get("audio", {}).get("audioDuckingMode")
			browse = dict(config.conf._getProfile("browseMode").get("audio", {}))
			effective = {name: None for name in ("normal", "typing", "reading")}
			self.away()
			effective["normal"] = config.conf["audio"]["audioDuckingMode"]
			self.typing()
			effective["typing"] = config.conf["audio"]["audioDuckingMode"]
			self.reading()
			effective["reading"] = config.conf["audio"]["audioDuckingMode"]
			return {"toggled": toggled, "applied": applied, "base": base, "browseMode": browse, "ducking in each place": effective}

		def save(self):
			config.conf.save()
			folder = globalVars.appArgs.configPath
			out = {}
			for label, path in (("nvda.ini", "nvda.ini"), ("JAWS - msedge.ini", os.path.join("profiles", "JAWS - msedge.ini")), ("browseMode.ini", os.path.join("profiles", "browseMode.ini"))):
				text = open(os.path.join(folder, path), encoding="utf-8").read()
				out[label] = [line.strip() for line in text.splitlines() if "volume" in line or "audioDucking" in line or line.strip().startswith("[")]
			return out

	import os
	builtins.T49 = Tools()
'''


def run(r, code, timeout=30):
	out = r.driver("eval", code=PRELUDE + "\n" + code, timeout=timeout)
	if "error" in out:
		print(out["error"])
		raise SystemExit("the code failed in NVDA")
	return out["result"]


def show(title, value):
	print(f"## {title}")
	print("   " + json.dumps(value, indent=None))
	sys.stdout.flush()


def check(condition, message):
	print(("   ok   " if condition else "   FAIL ") + message)
	if not condition:
		check.failed += 1


check.failed = 0


def flow(r, fixed):
	"""The tester's steps. Returns the voice's volume while reading a page after Settings, from Edge, turned it down."""
	show("NVDA starts", run(r, "result = T49.look()"))
	run(r, "T49.typing()")
	typing = run(r, "result = T49.look()")
	show("typing in Edge (JAWS - msedge on)", typing)
	run(r, "T49.reading()")
	reading = run(r, "result = T49.look()")
	show("reading a page (browseMode on top)", reading)
	check(typing["voice"] == 80 and reading["voice"] == 100, "the tester's files: 80 while typing, 100 while reading")
	run(r, "T49.typing()")
	show("Settings opened from Edge (NVDA says: Editing profile JAWS - msedge)", run(r, "result = T49.open()"))
	show("the volume slider moved to 70", run(r, "result = T49.slide(70)"))
	run(r, "T49.ok()")
	after = run(r, "result = T49.look()")
	show("OK pressed, still in Edge", after)
	check(after["voice"] == 70, "typing: 70")
	run(r, "T49.reading()")
	page = run(r, "result = T49.look()")
	show("the page again", page)
	return after, page


def control(r):
	after, page = flow(r, False)
	check(page["voice"] == 100, "reading: LOUDER than the 70 that was set (the tester's report)")
	run(r, "T49.typing()")
	back = run(r, "result = T49.look()")
	show("typing again", back)
	check(back["voice"] == 70, "typing: 70 again")


def fixed(r):
	after, page = flow(r, True)
	check(page["voice"] == 70, "reading: 70, as set")
	check(page["held"]["JAWS - msedge"] == {} and page["held"]["browseMode"] == {}, "neither profile holds a volume now")
	check(str(page["held"]["base"].get("volume")) == "70", "the normal configuration does")
	check(set(page["copies"].values()) == {70} or set(map(str, page["copies"].values())) == {"70"}, "Eloquence's copy for each set of profiles is 70")
	for place, code in (("outside Edge", "T49.away()"), ("typing in Edge", "T49.typing()"), ("reading a page", "T49.reading()"), ("outside Edge", "T49.away()")):
		run(r, code)
		look = run(r, "result = T49.look()")
		check(look["voice"] == 70, f"{place}: {look['stack']} gives {look['voice']}")
	run(r, "T49.reading()")
	show("settings ring on a page: Volume, decrease twice", run(r, "result = T49.ring([-1, -1])"))
	look = run(r, "result = T49.look()")
	show("after the ring", look)
	check(look["voice"] == 60 and look["held"]["browseMode"] == {} and str(look["held"]["base"].get("volume")) == "60", "ring: 60 in the normal configuration, none in browseMode")
	for place, code in (("typing in Edge", "T49.typing()"), ("outside Edge", "T49.away()"), ("reading a page", "T49.reading()")):
		run(r, code)
		check(run(r, "result = T49.look()")["voice"] == 60, f"{place}: 60")
	run(r, "T49.reading()")
	ducking = run(r, "result = T49.duck()")
	show("audio ducking turned on on a page (NVDA+Shift+J, D)", ducking)
	check(ducking["toggled"] and "audioDuckingMode" not in ducking["browseMode"], "ducking: turned on, and not held by browseMode")
	check(all(str(v) == "1" for v in ducking["ducking in each place"].values()), "ducking: on outside Edge, in Edge and on a page")
	show("files, after NVDA saves its settings", run(r, "result = T49.save()"))


def user(r):
	run(r, "T49.away()")
	run(r, 'config.conf.manualActivateProfile("kitchen games")')
	show("a profile of the user's own turned on by hand", run(r, "result = T49.look()"))
	show("Settings opened on it", run(r, "result = T49.open()"))
	show("the volume slider moved to 55", run(r, "result = T49.slide(55)"))
	run(r, "T49.ok()")
	look = run(r, "result = T49.look()")
	show("OK pressed", look)
	check(look["voice"] == 55 and look["held"]["kitchen games"] == {"volume": 55}, "55 is in the user's own profile, and is the volume while it is on")
	check(look["held"]["JAWS - msedge"] == {"volume": "80"} and look["held"]["browseMode"] == {"volume": "100"} and look["held"]["base"].get("volume") == "100", "the other profiles and the normal configuration are as they were")
	run(r, "config.conf.manualActivateProfile(None)")
	back = run(r, "result = T49.look()")
	show("the profile turned off", back)
	check(back["voice"] == 100, "outside it: 100, as before")
	run(r, "T49.typing()")
	check(run(r, "result = T49.look()")["voice"] == 80, "typing in Edge: 80, as before")


def question(r):
	print("   waiting for the question (20 seconds after NVDA starts)...")
	found = None
	for _ in range(60):
		found = run(r, '''
dialogs = [w for w in wx.GetTopLevelWindows() if isinstance(w, wx.SingleChoiceDialog) and w.IsShown()]
result = None
if dialogs:
	d = dialogs[0]
	boxes = [c for c in d.GetChildren() if isinstance(c, wx.ListBox)]
	result = {"title": d.GetTitle(), "text": [c.GetLabel() for c in d.GetChildren() if isinstance(c, wx.StaticText)], "choices": boxes[0].GetStrings() if boxes else None}
''')
		if found:
			break
		time.sleep(1)
	show("the question", found)
	check(found is not None, "the question was asked")
	if not found:
		return
	run(r, "T49.typing()")
	show("typing in Edge, before the answer", run(r, "result = T49.look()"))
	run(r, "T49.reading()")
	show("reading, before the answer", run(r, "result = T49.look()"))
	run(r, '''
d = [w for w in wx.GetTopLevelWindows() if isinstance(w, wx.SingleChoiceDialog) and w.IsShown()][0]
d.SetSelection(0)
d.EndModal(wx.ID_OK)
result = d.GetSelection()
''')
	time.sleep(4)
	for place, code in (("reading", "T49.reading()"), ("typing in Edge", "T49.typing()"), ("outside Edge", "T49.away()")):
		run(r, code)
		look = run(r, "result = T49.look()")
		show(f"after the answer, {place}", look)
		check(look["voice"] == 80, f"{place}: 80, the first choice")
	state = json.load(open(os.path.join(HERE, "cfg", "jawsMigrator", "state.json"), encoding="utf-8"))
	show("what the assistant kept of the answer", state.get("evenSpeechAsked"))
	r.show("Speaking \\[.*everywhere|jawsMigrator.*(eloquence|speech)", 400)


def main():
	which = sys.argv[1] if len(sys.argv) > 1 else "fixed"
	r = Rig()
	print("driver:", r.driver("ping"))
	r.newLog()
	{"control": control, "fixed": fixed, "question": question, "user": user}[which](r)
	print()
	print("FAILED" if check.failed else "all checks ok", f"({which})")
	if which != "question":
		r.show("jawsMigrator.*(speech|volume|eloquence|everywhere)|ERROR", 400)


if __name__ == "__main__":
	main()
