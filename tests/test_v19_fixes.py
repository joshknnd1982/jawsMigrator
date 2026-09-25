# Unit tests for version 1.9, from a tester's report on version 1.8: NVDA kept reading a temperature
# monitor's system tray icon, whose name the program changes every few seconds (trayChanges). The
# imitation NVDA below does what NVDA 2026.2 does, as far as the focus's name goes:
# NVDAObject.event_nameChange, which says the focus's name again when it changes and updates braille;
# speech.getObjectPropertiesSpeech with its notes of what was said (_speakObjectPropertiesCache);
# objects that keep what they read until NVDA's core cycle ends; and inputCore.decide_executeGesture,
# which NVDA asks before it runs each key press. The windows are those of Windows 11 25H2, as on the
# tester's computer, and of Windows 10. The notices come in the order of the tester's NVDA log. The
# assistant's own event handlers (GlobalPlugin.event_*) are the real ones.
# Run: python -m unittest tests.test_v19_fixes -v

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import changeRepeats, state, trayChanges  # noqa: E402

#: The temperature monitor's icon in the tester's log, as NVDA said it at 09:29:10, 09:29:13 and 09:29:17.
TEMPERATURES = [
	f"CPU 129.9 F; Drive C Temperature 113.0 F; Drive D Temperatur... CPU {cpu} F; Drive C Temperature 113.0 F; Drive D Temperatur..."
	for cpu in ("123.6", "126.1", "121.6")
]

GA_PARENT = 1
GA_ROOT = 2
DESKTOP = 0x10010
#: {window: (class, parent)}, as Windows has them.
WINDOWS = {
	DESKTOP: ("#32769", None),
	# Windows 11 25H2: the tray's icons, the programs' buttons and the Start button are UI Automation elements of InputSite.
	0x301BA: ("Shell_TrayWnd", DESKTOP),
	0x1027E: ("Windows.UI.Composition.DesktopWindowContentBridge", 0x301BA),
	0x10280: ("Windows.UI.Input.InputSite.WindowClass", 0x1027E),
	0x301B6: ("TrayNotifyWnd", 0x301BA),
	# Windows 11's hidden icons, and the taskbar on another monitor.
	0x50A10: ("TopLevelWindowForOverflowXamlIsland", DESKTOP),
	0x50A12: ("Windows.UI.Composition.DesktopWindowContentBridge", 0x50A10),
	0x50A14: ("Windows.UI.Input.InputSite.WindowClass", 0x50A12),
	0x60B10: ("Shell_SecondaryTrayWnd", DESKTOP),
	0x60B12: ("Windows.UI.Composition.DesktopWindowContentBridge", 0x60B10),
	0x60B14: ("Windows.UI.Input.InputSite.WindowClass", 0x60B12),
	# Windows 10: the tray's icons, the clock, the hidden icons, and the running programs.
	0x20100: ("Shell_TrayWnd", DESKTOP),
	0x20102: ("TrayNotifyWnd", 0x20100),
	0x20104: ("SysPager", 0x20102),
	0x20106: ("ToolbarWindow32", 0x20104),
	0x20108: ("TrayClockWClass", 0x20102),
	0x2010A: ("ReBarWindow32", 0x20100),
	0x2010C: ("MSTaskSwWClass", 0x2010A),
	0x2010E: ("MSTaskListWClass", 0x2010C),
	0x20200: ("NotifyIconOverflowWindow", DESKTOP),
	0x20202: ("ToolbarWindow32", 0x20200),
	# Any other program: File Explorer.
	0x40300: ("CabinetWClass", DESKTOP),
	0x40302: ("DirectUIHWND", 0x40300),
}
WINDOWS_11_TASKBAR = 0x10280
WINDOWS_11_HIDDEN_ICONS = 0x50A14
WINDOWS_11_OTHER_TASKBAR = 0x60B14
WINDOWS_10_ICONS = 0x20106
WINDOWS_10_CLOCK = 0x20108
WINDOWS_10_PROGRAMS = 0x2010E
WINDOWS_10_HIDDEN_ICONS = 0x20202
EXPLORER = 0x40302


def getAncestor(window, flags):
	if window not in WINDOWS or window == DESKTOP:
		return 0
	if flags == GA_PARENT:
		return WINDOWS[window][1]
	while WINDOWS[window][1] != DESKTOP:
		window = WINDOWS[window][1]
	return window


winUser = types.SimpleNamespace(
	GA_PARENT=GA_PARENT,
	GA_ROOT=GA_ROOT,
	getAncestor=getAncestor,
	getClassName=lambda window: WINDOWS.get(window, ("", None))[0],
)


class Control:
	"""What a program shows now: its icon's name, which it changes when it likes."""

	def __init__(self, name):
		self.name = name


class NVDAObject:
	"""NVDA's object for a control: it keeps what it read until the core cycle ends."""

	def __init__(self, nvda, control, windowHandle, uiaClass=None, role="button", position=None):
		self.nvda = nvda
		self.control = control
		self.windowHandle = windowHandle
		if uiaClass is not None:
			self.UIAElement = types.SimpleNamespace(cachedClassName=uiaClass)
		self.roleText = role
		self.position = position
		self.appModule = None
		self.treeInterceptor = None
		self._read = {}
		nvda.objects.append(self)

	@property
	def name(self):
		if "name" not in self._read:
			self._read["name"] = self.control.name
		return self._read["name"]


class Nvda:
	def __init__(self, plugin):
		self.plugin = plugin
		self.objects = []
		self.spoken = []
		self.brailled = []
		self.focus = None
		self.clock = 1000.0

	def endCycle(self):
		for obj in self.objects:
			obj._read.clear()

	def propertiesSpeech(self, obj, reason):
		"""speech.getObjectPropertiesSpeech, for the name."""
		new = {"name": obj.name}
		old = dict(getattr(obj, "_speakObjectPropertiesCache", {}))
		obj._speakObjectPropertiesCache = {**old, **new}
		if reason == "change" and "name" in old and old["name"] == new["name"]:
			return []
		return [new["name"]]

	def speak(self, sequence):
		if sequence:
			self.spoken.append(sequence)

	def _now(self):
		return mock.patch.object(trayChanges.time, "monotonic", return_value=self.clock)

	def gainFocus(self, obj, after=0.0):
		"""The focus moves: the assistant's handler, then NVDA's object says it."""
		self.clock += after
		self.focus = obj

		def nvdaObject():
			self.speak(self.propertiesSpeech(obj, "focus") + [obj.roleText] + ([obj.position] if obj.position else []))
			self.brailled.append(obj.name)

		with self._now():
			self.plugin.event_gainFocus(obj, nvdaObject)
		self.endCycle()

	def nameChange(self, obj, name, after=0.0):
		"""The program changes the name, and its notice comes in: the assistant, then NVDAObject.event_nameChange."""
		self.clock += after
		obj.control.name = name
		calls = []

		def nvdaObject():
			calls.append("nameChange")
			if obj is self.focus:
				self.speak(self.propertiesSpeech(obj, "change"))
			self.brailled.append(obj.name)

		with self._now():
			self.plugin.event_nameChange(obj, nvdaObject)
		assert calls == ["nameChange"], "NVDA handles every notice, once"
		self.endCycle()

	def press(self, key, after=0.0):
		"""A key press: NVDA asks inputCore.decide_executeGesture before it runs it, in its keyboard thread."""
		self.clock += after
		with self._now():
			ran = sys.modules["inputCore"].decide_executeGesture.decide(gesture=key)
		assert ran, "NVDA runs every key press"

	def reportFocus(self, after=0.0):
		"""NVDA+Tab: the focus as it is now."""
		self.press("kb:NVDA+tab", after)
		obj = self.focus
		self.speak(self.propertiesSpeech(obj, "query") + [obj.roleText] + ([obj.position] if obj.position else []))
		self.endCycle()


def _plugin():
	"""The assistant's global plugin, as far as its event handlers go."""
	plugin = object.__new__(jawsMigrator.GlobalPlugin)
	plugin._sleepApps = set()
	plugin._changeRepeats = changeRepeats
	plugin._trayChanges = trayChanges
	return plugin


class TrayTests(unittest.TestCase):
	def setUp(self):
		self.nvda = Nvda(_plugin())
		patcher = mock.patch.dict(sys.modules, {"winUser": winUser, "api": types.SimpleNamespace(getFocusObject=lambda: self.nvda.focus)})
		patcher.start()
		self.addCleanup(patcher.stop)
		# Registered afresh: a plugin another test made may have registered it before NVDA's decider was there.
		trayChanges.unregister()
		trayChanges.register()
		self.addCleanup(trayChanges.unregister)

	def icon(self, name, window=WINDOWS_11_TASKBAR, uiaClass="SystemTray.NormalButton", **kwargs):
		return NVDAObject(self.nvda, Control(name), window, uiaClass, **kwargs)

	def _startOnTheTestersIcon(self):
		"""NVDA starts with the focus on the temperature monitor's icon, then the program changes it twice."""
		nvda = self.nvda
		icon = self.icon(TEMPERATURES[0], position="1 of 5")
		nvda.gainFocus(icon)
		nvda.nameChange(icon, TEMPERATURES[1], after=2.3)
		nvda.nameChange(icon, TEMPERATURES[2], after=4.7)
		return icon

	def test_the_testers_temperature_monitor_is_read_once(self):
		self._startOnTheTestersIcon()
		self.assertEqual(self.nvda.spoken, [[TEMPERATURES[0], "button", "1 of 5"]], "NVDA says the icon once, as the focus arrives")
		self.assertEqual(self.nvda.brailled, TEMPERATURES, "braille shows every change")

	def test_nvda_alone_reads_every_change(self):
		# What NVDA does without the assistant, or with this turned off: the tester's log.
		trayChanges.unregister()
		self._startOnTheTestersIcon()
		self.assertEqual(self.nvda.spoken, [[TEMPERATURES[0], "button", "1 of 5"], [TEMPERATURES[1]], [TEMPERATURES[2]]])

	def test_nvda_tab_reads_it_as_it_is_now(self):
		self._startOnTheTestersIcon()
		self.nvda.reportFocus(after=2.0)
		self.assertEqual(self.nvda.spoken[-1], [TEMPERATURES[2], "button", "1 of 5"])
		self.assertEqual(len(self.nvda.spoken), 2)

	def test_a_key_press_on_the_icon_is_answered_once(self):
		nvda = self.nvda
		volume = self.icon("Volume Speakers (Realtek(R) Audio): 18%", uiaClass="SystemTray.OmniButtonCenter")
		nvda.gainFocus(volume, after=1.0)
		nvda.press("kb:volumeUp", after=3.0)
		nvda.nameChange(volume, "Volume Speakers (Realtek(R) Audio): 20%", after=0.2)
		self.assertEqual(nvda.spoken[-1], ["Volume Speakers (Realtek(R) Audio): 20%"], "the key press may have made the change")
		nvda.nameChange(volume, "Volume Speakers (Realtek(R) Audio): 21%", after=0.3)
		self.assertEqual(len(nvda.spoken), 2, "once for each key press")
		nvda.press("kb:volumeUp", after=2.0)
		nvda.nameChange(volume, "Volume Speakers (Realtek(R) Audio): 23%", after=0.2)
		self.assertEqual(nvda.spoken[-1], ["Volume Speakers (Realtek(R) Audio): 23%"])
		self.assertEqual(len(nvda.spoken), 3)

	def test_a_notice_with_nothing_new_leaves_the_key_press_for_the_change(self):
		nvda = self.nvda
		volume = self.icon("Volume Speakers (Realtek(R) Audio): 18%", uiaClass="SystemTray.OmniButtonCenter")
		nvda.gainFocus(volume)
		nvda.press("kb:volumeUp", after=3.0)
		nvda.nameChange(volume, "Volume Speakers (Realtek(R) Audio): 18%", after=0.1)
		nvda.nameChange(volume, "Volume Speakers (Realtek(R) Audio): 20%", after=0.1)
		self.assertEqual(nvda.spoken[-1], ["Volume Speakers (Realtek(R) Audio): 20%"])

	def test_not_a_while_after_the_key_press(self):
		nvda = self.nvda
		icon = self.icon(TEMPERATURES[0], position="1 of 5")
		nvda.gainFocus(icon)
		nvda.press("kb:control", after=1.0)
		nvda.press("kb:NVDA+f12", after=0.5)
		nvda.nameChange(icon, TEMPERATURES[1], after=trayChanges.AFTER_KEY_PRESS + 0.1)
		self.assertEqual(len(nvda.spoken), 1)

	def test_not_after_the_key_press_that_moved_the_focus_there(self):
		nvda = self.nvda
		nvda.gainFocus(NVDAObject(nvda, Control("Items View"), EXPLORER, "UIItemsView", role="list"))
		# Windows+B: the focus moves to the tray's first icon, which changes a moment later.
		nvda.press("kb:windows+b", after=2.0)
		icon = self.icon(TEMPERATURES[0], position="1 of 5")
		nvda.gainFocus(icon, after=0.1)
		nvda.nameChange(icon, TEMPERATURES[1], after=0.4)
		self.assertEqual(nvda.spoken, [["Items View", "list"], [TEMPERATURES[0], "button", "1 of 5"]])
		# The Right Arrow key moves on; the next icon changes at once.
		nvda.press("kb:rightArrow", after=1.0)
		clock = self.icon("Clock 9:18 PM 9/24/2026", uiaClass="SystemTray.OmniButton")
		nvda.gainFocus(clock, after=0.1)
		nvda.nameChange(clock, "Clock 9:19 PM 9/24/2026", after=0.2)
		self.assertEqual(nvda.spoken[-1], ["Clock 9:18 PM 9/24/2026", "button"])

	def test_every_part_of_the_tray(self):
		nvda = self.nvda
		places = [
			("Windows 11, the clock", self.icon("Clock 9:18 PM 9/24/2026", uiaClass="SystemTray.OmniButton"), "Clock 9:19 PM 9/24/2026"),
			("Windows 11, the network icon", self.icon("Network JoshKennedy Internet access", uiaClass="SystemTray.AccentButton"), "Network JoshKennedy No internet access"),
			("Windows 11, hidden icons", self.icon(TEMPERATURES[0], window=WINDOWS_11_HIDDEN_ICONS), TEMPERATURES[1]),
			("Windows 11, the taskbar on another monitor", self.icon("Clock 9:18 PM 9/24/2026", window=WINDOWS_11_OTHER_TASKBAR, uiaClass="SystemTray.OmniButton"), "Clock 9:19 PM 9/24/2026"),
			("Windows 10, a program's icon", self.icon(TEMPERATURES[0], window=WINDOWS_10_ICONS, uiaClass=None), TEMPERATURES[1]),
			("Windows 10, the clock", self.icon("9:18 PM 9/24/2026", window=WINDOWS_10_CLOCK, uiaClass=None, role="clock"), "9:19 PM 9/24/2026"),
			("Windows 10, hidden icons", self.icon(TEMPERATURES[0], window=WINDOWS_10_HIDDEN_ICONS, uiaClass=None), TEMPERATURES[1]),
		]
		for where, obj, changed in places:
			with self.subTest(where):
				nvda.gainFocus(obj, after=5.0)
				spoken = len(nvda.spoken)
				nvda.nameChange(obj, changed, after=3.0)
				self.assertTrue(trayChanges.isTrayIcon(obj))
				self.assertEqual(len(nvda.spoken), spoken, f"{where}: not read again")
				self.assertEqual(nvda.brailled[-1], changed)

	def test_everything_else_is_read_as_before(self):
		nvda = self.nvda
		others = [
			("Windows 11, a program's taskbar button", self.icon("Claude - 1 running window", uiaClass="Taskbar.TaskListButtonAutomationPeer"), "Claude - 2 running windows"),
			("Windows 11, the Start button", self.icon("Start", uiaClass="ToggleButton"), "Start, 1 new"),
			("Windows 10, a program's taskbar button", self.icon("Claude", window=WINDOWS_10_PROGRAMS, uiaClass=None), "Claude - 2 windows"),
			("File Explorer", self.icon("Sort", window=EXPLORER, uiaClass="SystemTray.NormalButton"), "Sort by name"),
			("a window that is gone", self.icon("Close", window=0x7FFF0), "Closed"),
		]
		for where, obj, changed in others:
			with self.subTest(where):
				nvda.gainFocus(obj, after=5.0)
				nvda.nameChange(obj, changed, after=3.0)
				self.assertFalse(trayChanges.isTrayIcon(obj))
				self.assertEqual(nvda.spoken[-1], [changed], f"{where}: NVDA reads the change")

	def test_an_icon_without_the_focus_is_left_alone(self):
		nvda = self.nvda
		nvda.gainFocus(NVDAObject(nvda, Control("Items View"), EXPLORER, "UIItemsView", role="list"))
		icon = self.icon(TEMPERATURES[0])
		icon._speakObjectPropertiesCache = {"name": TEMPERATURES[0]}
		nvda.nameChange(icon, TEMPERATURES[1], after=3.0)
		self.assertEqual(icon._speakObjectPropertiesCache, {"name": TEMPERATURES[0]})
		self.assertEqual(len(nvda.spoken), 1)

	def test_turned_off_in_the_settings(self):
		self.assertTrue(trayChanges.wanted(dict(state.DEFAULTS)), "on unless turned off")
		self.assertFalse(trayChanges.wanted({trayChanges.STATE_KEY: False}))
		decider = sys.modules["inputCore"].decide_executeGesture
		self.assertIn(trayChanges.noteGesture, decider.handlers)
		trayChanges.unregister()
		self.assertFalse(trayChanges.isRegistered())
		self.assertNotIn(trayChanges.noteGesture, decider.handlers, "key presses are no longer noted")
		icon = self.icon(TEMPERATURES[0])
		self.nvda.gainFocus(icon)
		self.nvda.nameChange(icon, TEMPERATURES[1], after=3.0)
		self.assertEqual(self.nvda.spoken[-1], [TEMPERATURES[1]])

	def test_never_in_the_way_of_nvda(self):
		nvda = self.nvda
		# NVDA runs every key press, whatever goes wrong in the assistant.
		with mock.patch.dict(sys.modules, {"api": None}):
			self.assertTrue(trayChanges.noteGesture("kb:a"))
		self.assertTrue(sys.modules["inputCore"].decide_executeGesture.decide(gesture="kb:a"))

		# A notice NVDA can't place: NVDA handles it as usual, and nothing is changed.
		class Broken(NVDAObject):
			@property
			def windowHandle(self):
				raise RuntimeError("broken for the test")

			@windowHandle.setter
			def windowHandle(self, value):
				pass

		broken = Broken(nvda, Control("Speakers: 18%"), WINDOWS_11_TASKBAR, "SystemTray.OmniButtonCenter")
		with mock.patch.object(trayChanges, "_log"):
			nvda.gainFocus(broken)
			nvda.nameChange(broken, "Speakers: 20%", after=3.0)
		self.assertEqual(nvda.spoken[-1], ["Speakers: 20%"])
		# Without the module, or without anything set up, NVDA still gets the notice.
		calls = []
		plugin = nvda.plugin
		plugin._trayChanges = None
		plugin.event_nameChange(broken, lambda: calls.append("nameChange"))
		bare = object.__new__(jawsMigrator.GlobalPlugin)
		bare._changeRepeats = None
		bare.event_nameChange(broken, lambda: calls.append("nameChange"))
		self.assertEqual(calls, ["nameChange", "nameChange"])


if __name__ == "__main__":
	unittest.main()
