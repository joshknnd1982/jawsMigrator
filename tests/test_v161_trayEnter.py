# Unit tests for issue 52: Enter on a system tray icon doesn't always click it (trayEnter).
# Windows sends a program NIN_KEYSELECT for Enter on its icon, not the click a mouse gives, and many programs answer only
# the mouse. With the assistant, Enter on a program's icon clicks it with the mouse. The windows and UI Automation classes
# and IDs are those read from Windows 11 build 26300 (the taskbar of this computer) and the windows of Windows 10, as in
# test_v19_fixes. The imitation of NVDA below makes an object's class from the classes chosen for it, as NVDA does, and
# finds a key's script in the classes' __gestures, as NVDA's ScriptableObject does.
# Run: python -m unittest tests.test_v161_trayEnter -v

import contextlib
import enum
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import state, trayEnter  # noqa: E402

from test_v19_fixes import (  # noqa: E402
	EXPLORER,
	WINDOWS,
	WINDOWS_10_CLOCK,
	WINDOWS_10_HIDDEN_ICONS,
	WINDOWS_10_ICONS,
	WINDOWS_10_PROGRAMS,
	WINDOWS_11_HIDDEN_ICONS,
	WINDOWS_11_OTHER_TASKBAR,
	WINDOWS_11_TASKBAR,
	getAncestor,
)

#: Windows 11's TrayNotifyWnd, the window at the middle of each of the tray's icons (WindowFromPoint), and a window
#: of another program that covers the tray.
WINDOWS_11_TRAY_NOTIFY = 0x301B6
COVERING_WINDOW = 0x40300


class Role(enum.Enum):
	BUTTON = "button"
	CLOCK = "clock"
	LIST = "list"


class NVDAObject:
	"""NVDA's NVDAObject, as far as its classes and scripts go."""

	def __init__(self, name, windowHandle, location, uiaClass=None, automationId=None, role=Role.BUTTON):
		self.name = name
		self.windowHandle = windowHandle
		self.location = location
		self.role = role
		if uiaClass is not None:
			self.UIAElement = types.SimpleNamespace(cachedClassName=uiaClass)
			self.UIAAutomationId = automationId

	def getScript(self, gestureId):
		"""ScriptableObject.getScript: the script the classes' __gestures bind the key to, or None."""
		for cls in type(self).__mro__:
			gestures = vars(cls).get(f"_{cls.__name__}__gestures") or {}
			for identifier, scriptName in gestures.items():
				if identifier.lower() == gestureId.lower():
					return getattr(self, f"script_{scriptName}")
		return None


class Gesture:
	def __init__(self, identifier):
		self.identifier = identifier
		self.sent = 0

	def send(self):
		self.sent += 1


class Screen:
	"""The mouse pointer and what NVDA's mouseHandler and winUser do with it."""

	def __init__(self):
		self.pointer = (200, 300)
		self.clicks = []
		self.moves = []
		self.ignoring = False
		self.unfollowedMoves = 0
		self.windowAt = {}
		self.timers = []

	@contextlib.contextmanager
	def ignoreInjection(self):
		self.ignoring = True
		try:
			yield
		finally:
			self.ignoring = False

	def setCursorPos(self, x, y):
		self.pointer = (x, y)
		self.moves.append((x, y))
		if not self.ignoring:
			self.unfollowedMoves += 1

	def getCursorPos(self):
		return list(self.pointer)

	def doPrimaryClick(self, releaseDelay=None):
		self.clicks.append(self.pointer)

	def later(self, seconds, function):
		timer = types.SimpleNamespace(seconds=seconds, function=function, stopped=False)
		timer.Stop = lambda: setattr(timer, "stopped", True)
		self.timers.append(timer)
		return timer

	def runTimers(self):
		for timer in list(self.timers):
			self.timers.remove(timer)
			if not timer.stopped:
				timer.function()


# The middle of each icon in the tests is on its tray's window, as on Windows (WindowFromPoint).
TASKBAR_ICON = (1337, 958, 32, 48)
HIDDEN_ICON = (1200, 800, 40, 40)
OTHER_TASKBAR_ICON = (3257, 958, 32, 48)
WINDOWS_10_ICON = (1500, 1050, 24, 30)
WINDOWS_10_HIDDEN_ICON = (1450, 950, 24, 24)


def middle(location):
	left, top, width, height = location
	return left + width // 2, top + height // 2


class TrayEnterTests(unittest.TestCase):
	def setUp(self):
		self.screen = screen = Screen()
		self.focus = None
		winUser = types.SimpleNamespace(
			GA_PARENT=1,
			GA_ROOT=2,
			getAncestor=getAncestor,
			getClassName=lambda window: WINDOWS.get(window, ("", None))[0],
			getCursorPos=screen.getCursorPos,
			setCursorPos=screen.setCursorPos,
		)
		screen.windowAt = {
			middle(TASKBAR_ICON): WINDOWS_11_TRAY_NOTIFY,
			middle(HIDDEN_ICON): WINDOWS_11_HIDDEN_ICONS,
			middle(OTHER_TASKBAR_ICON): WINDOWS_11_OTHER_TASKBAR,
			middle(WINDOWS_10_ICON): WINDOWS_10_ICONS,
			middle(WINDOWS_10_HIDDEN_ICON): WINDOWS_10_HIDDEN_ICONS,
		}
		modules = {
			"winUser": winUser,
			"api": types.SimpleNamespace(getFocusObject=lambda: self.focus),
			"mouseHandler": types.SimpleNamespace(ignoreInjection=screen.ignoreInjection, doPrimaryClick=screen.doPrimaryClick),
			"controlTypes": types.SimpleNamespace(Role=Role),
			"NVDAObjects": types.SimpleNamespace(NVDAObject=NVDAObject),
		}
		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		for name, replacement in (("_windowAt", lambda x, y: screen.windowAt.get((x, y), 0)), ("_later", screen.later), ("_overlay", None)):
			patcher = mock.patch.object(trayEnter, name, replacement)
			patcher.start()
			self.addCleanup(patcher.stop)
		trayEnter._away = None
		trayEnter._timer = None
		trayEnter._clicked = None
		trayEnter.register()
		self.addCleanup(trayEnter.unregister)

	def make(self, *args, **kwargs):
		"""The object NVDA makes: its class from the classes the plugins chose (NVDAObject.__new__), with the focus on it."""
		obj = NVDAObject(*args, **kwargs)
		classes = [NVDAObject]
		trayEnter.chooseOverlay(obj, classes)
		if len(classes) > 1:
			obj.__class__ = type("Dynamic_" + "".join(cls.__name__ for cls in classes), tuple(classes), {})
		self.focus = obj
		return obj

	def windows11Icon(self, name="Discord", location=TASKBAR_ICON, window=WINDOWS_11_TASKBAR):
		return self.make(name, window, location, uiaClass="SystemTray.NormalButton", automationId=trayEnter.PROGRAM_ICON_ID)

	def press(self, obj, key="kb:enter"):
		"""NVDA's run of a key on the focus: its script, or the key on to Windows."""
		gesture = Gesture(key)
		script = obj.getScript(key)
		if script is None:
			gesture.send()
		else:
			script(gesture)
		return gesture

	def test_enter_clicks_a_programs_icon_in_the_middle(self):
		icon = self.windows11Icon()
		gesture = self.press(icon)
		self.assertEqual(self.screen.clicks, [middle(TASKBAR_ICON)], "a click of the primary button in the middle of the icon")
		self.assertEqual(gesture.sent, 0, "Windows doesn't get Enter as well: the program would get both")
		self.assertEqual(self.screen.unfollowedMoves, 0, "NVDA's mouse tracking doesn't say what the pointer moves to")
		self.assertEqual(self.screen.pointer, middle(TASKBAR_ICON), "the pointer stays on the icon a moment")
		self.assertEqual([timer.seconds for timer in self.screen.timers], [trayEnter.POINTER_STAYS])
		self.screen.runTimers()
		self.assertEqual(self.screen.pointer, (200, 300), "then goes back where it was")
		self.assertEqual(self.screen.unfollowedMoves, 0)

	def test_the_keypads_enter_too_and_space_is_left_to_windows(self):
		icon = self.windows11Icon()
		self.assertEqual(self.press(icon, "kb:numpadEnter").sent, 0)
		self.assertEqual(len(self.screen.clicks), 1)
		self.assertEqual(self.press(icon, "kb:space").sent, 1, "Space still gives Windows' own keyboard notice")
		self.assertEqual(len(self.screen.clicks), 1)

	def test_enter_twice_quickly_is_a_double_click_and_the_pointer_goes_back_once(self):
		icon = self.windows11Icon()
		self.press(icon)
		self.press(icon)
		self.assertEqual(self.screen.clicks, [middle(TASKBAR_ICON)] * 2, "two clicks on one place: Windows makes them a double click")
		self.assertEqual([timer.stopped for timer in self.screen.timers], [True, False], "the pointer stays on for the second")
		self.screen.runTimers()
		self.assertEqual(self.screen.pointer, (200, 300), "and goes back where it was before the first")

	def test_a_second_enter_after_the_user_moved_the_mouse_puts_it_back_there(self):
		icon = self.windows11Icon()
		self.press(icon)
		self.screen.pointer = (640, 480)
		self.press(icon)
		self.screen.runTimers()
		self.assertEqual(self.screen.pointer, (640, 480), "where the user left it, not where it was before the first Enter")

	def test_the_pointer_goes_back_when_the_focus_moves(self):
		icon = self.windows11Icon()
		self.press(icon)
		trayEnter.focusMoved(icon)
		self.assertEqual(self.screen.pointer, middle(TASKBAR_ICON), "the focus coming back to the icon leaves it on for a double click")
		again = NVDAObject("Discord", WINDOWS_11_TASKBAR, TASKBAR_ICON, "SystemTray.NormalButton", trayEnter.PROGRAM_ICON_ID)
		with mock.patch.object(NVDAObject, "__eq__", lambda self, other: self.name == other.name and self.windowHandle == other.windowHandle):
			trayEnter.focusMoved(again)
		self.assertEqual(self.screen.pointer, middle(TASKBAR_ICON), "and so does a new object NVDA makes for the same icon")
		trayEnter.focusMoved(NVDAObject("Discord", EXPLORER, (0, 0, 800, 600), role=Role.LIST))
		self.assertEqual(self.screen.pointer, (200, 300), "the program's window has the focus: the pointer goes back at once")
		self.assertTrue(self.screen.timers[0].stopped)

	def test_the_plugin_puts_the_pointer_back_as_the_focus_moves(self):
		plugin = object.__new__(jawsMigrator.GlobalPlugin)
		plugin._sleepApps = set()
		plugin._trayEnter = trayEnter
		plugin._changeRepeats = None
		self.press(self.windows11Icon())
		window = NVDAObject("Discord", EXPLORER, (0, 0, 800, 600), role=Role.LIST)
		window.appModule = None
		window.treeInterceptor = None
		handled = []
		with mock.patch.object(jawsMigrator.GlobalPlugin, "_checkSleep", lambda self, obj: None):
			plugin.event_gainFocus(window, lambda: handled.append(True))
		self.assertEqual(handled, [True])
		self.assertEqual(self.screen.pointer, (200, 300))

	def test_a_click_that_fails_puts_the_pointer_back_and_gives_enter_to_windows(self):
		icon = self.windows11Icon()

		def broken(releaseDelay=None):
			raise OSError("no mouse")

		with mock.patch.object(sys.modules["mouseHandler"], "doPrimaryClick", broken), mock.patch.object(trayEnter, "_log"):
			self.assertEqual(self.press(icon).sent, 1)
		self.assertEqual(self.screen.pointer, (200, 300), "the pointer isn't left on the icon")

	def test_after_a_click_windows_never_gets_enter_too(self):
		icon = self.windows11Icon()
		with mock.patch.object(trayEnter, "_later", side_effect=RuntimeError("no timer")), mock.patch.object(trayEnter, "_log") as log:
			log.return_value.debug.side_effect = RuntimeError("no log")
			gesture = self.press(icon)
		self.assertEqual(gesture.sent, 0, "the program got the click; Enter as well would be twice")
		self.assertEqual(self.screen.clicks, [middle(TASKBAR_ICON)])
		self.assertEqual(self.screen.pointer, (200, 300), "with no timer, the pointer goes back at once")

	def test_a_pointer_the_user_moved_is_left_where_it_is(self):
		icon = self.windows11Icon()
		self.press(icon)
		self.screen.pointer = (640, 480)
		self.screen.runTimers()
		self.assertEqual(self.screen.pointer, (640, 480))

	def test_every_programs_icon(self):
		places = [
			("Windows 11, the taskbar", lambda: self.windows11Icon()),
			("Windows 11, the hidden icons", lambda: self.windows11Icon(location=HIDDEN_ICON, window=WINDOWS_11_HIDDEN_ICONS)),
			("Windows 11, the taskbar on another monitor", lambda: self.windows11Icon(location=OTHER_TASKBAR_ICON, window=WINDOWS_11_OTHER_TASKBAR)),
			("Windows 10, the tray", lambda: self.make("Discord", WINDOWS_10_ICONS, WINDOWS_10_ICON)),
			("Windows 10, the hidden icons", lambda: self.make("Discord", WINDOWS_10_HIDDEN_ICONS, WINDOWS_10_HIDDEN_ICON)),
		]
		for where, icon in places:
			with self.subTest(where):
				obj = icon()
				self.screen.clicks.clear()
				self.assertEqual(self.press(obj).sent, 0)
				self.assertEqual(self.screen.clicks, [middle(obj.location)])
				self.screen.runTimers()

	def test_the_trays_own_buttons_and_everything_else_are_left_to_windows(self):
		others = [
			("Windows 11, Show Hidden Icons", lambda: self.make("Show Hidden Icons", WINDOWS_11_TASKBAR, (1305, 958, 32, 48), "SystemTray.NormalButton", "SystemTrayIcon")),
			("Windows 11, the clock", lambda: self.make("Clock 7:28 PM", WINDOWS_11_TASKBAR, (1465, 958, 63, 48), "SystemTray.OmniButton", "SystemTrayIcon")),
			("Windows 11, the network icon", lambda: self.make("Network", WINDOWS_11_TASKBAR, (1373, 958, 24, 48), "SystemTray.AccentButton", "SystemTrayIcon")),
			("Windows 11, a program's taskbar button", lambda: self.make("Claude - 1 running window", WINDOWS_11_TASKBAR, (790, 958, 90, 48), "Taskbar.TaskListButtonAutomationPeer", "")),
			("Windows 11, the Start button", lambda: self.make("Start", WINDOWS_11_TASKBAR, (657, 958, 45, 48), "ToggleButton", "StartButton")),
			("Windows 10, the clock", lambda: self.make("7:28 PM", WINDOWS_10_CLOCK, (1490, 1050, 60, 30), role=Role.CLOCK)),
			("Windows 10, a program's taskbar button", lambda: self.make("Claude", WINDOWS_10_PROGRAMS, (500, 1050, 60, 30))),
			("Windows 10, the tray's toolbar itself", lambda: self.make("User Promoted Notification Area", WINDOWS_10_ICONS, (1400, 1050, 100, 30), role=Role.LIST)),
			("File Explorer", lambda: self.make("Sort", EXPLORER, (100, 100, 40, 20), "SystemTray.NormalButton", trayEnter.PROGRAM_ICON_ID)),
		]
		for where, make in others:
			with self.subTest(where):
				obj = make()
				self.assertNotIsInstance(obj, trayEnter.overlayClass())
				self.assertEqual(self.press(obj).sent, 1)
				self.assertEqual(self.screen.clicks, [])

	def test_an_icon_that_isnt_on_the_screen_gets_enter(self):
		for where, location in (("no place", None), ("no size", (1337, 958, 0, 0))):
			with self.subTest(where):
				icon = self.windows11Icon(location=TASKBAR_ICON)
				icon.location = location
				self.assertEqual(self.press(icon).sent, 1)
				self.assertEqual(self.screen.clicks, [])
				self.assertEqual(self.screen.moves, [], "the pointer isn't moved")

	def test_an_icon_something_covers_gets_enter(self):
		icon = self.windows11Icon()
		self.screen.windowAt[middle(TASKBAR_ICON)] = COVERING_WINDOW
		self.assertEqual(self.press(icon).sent, 1, "a click would land on the other window")
		self.assertEqual(self.screen.clicks, [])

	def test_after_the_focus_moved_enter_goes_on(self):
		icon = self.windows11Icon()
		self.focus = None
		self.assertEqual(self.press(icon).sent, 1)
		self.assertEqual(self.screen.clicks, [])

	def test_turned_off_in_the_settings(self):
		self.assertTrue(trayEnter.wanted(dict(state.DEFAULTS)), "on unless turned off")
		self.assertFalse(trayEnter.wanted({trayEnter.STATE_KEY: False}))
		made = self.windows11Icon()
		trayEnter.unregister()
		self.assertEqual(self.press(made).sent, 1, "an icon NVDA made before goes on to Windows")
		self.assertNotIsInstance(self.windows11Icon(), trayEnter.overlayClass(), "and a new one gets nothing")
		self.assertEqual(self.screen.clicks, [])

	def test_turning_it_off_puts_the_pointer_back(self):
		self.press(self.windows11Icon())
		trayEnter.unregister()
		self.assertEqual(self.screen.pointer, (200, 300))

	def test_anything_that_goes_wrong_gives_enter_to_windows(self):
		icon = self.windows11Icon()
		with mock.patch.object(trayEnter, "_clickAt", side_effect=OSError("no mouse")), mock.patch.object(trayEnter, "_log"):
			self.assertEqual(self.press(icon).sent, 1)

	def test_the_plugin_gives_the_class_only_while_it_is_on(self):
		plugin = object.__new__(jawsMigrator.GlobalPlugin)
		plugin._trayEnter = trayEnter
		obj = NVDAObject("Discord", WINDOWS_11_TASKBAR, TASKBAR_ICON, "SystemTray.NormalButton", trayEnter.PROGRAM_ICON_ID)
		classes = [NVDAObject]
		plugin.chooseNVDAObjectOverlayClasses(obj, classes)
		self.assertIs(classes[0], trayEnter.overlayClass())
		plugin._trayEnter = None
		classes = [NVDAObject]
		plugin.chooseNVDAObjectOverlayClasses(obj, classes)
		self.assertEqual(classes, [NVDAObject])


if __name__ == "__main__":
	unittest.main()
