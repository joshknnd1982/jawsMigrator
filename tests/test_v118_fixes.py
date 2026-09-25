# Unit tests for version 1.18, from a tester's reports on version 1.17 (issue 11):
# - elementsList: with 1.17 the tester pressed Alt+Left in Edge's Downloads panel, whose document stopped being ready,
#   and NVDA+F7 three seconds later. NVDA had no browse mode command for the key and gave Edge F7, its caret browsing
#   key: "Turn on caret browsing?". JAWS's Insert+F7 never reaches the program. A key of the Elements List now never
#   does either: NVDA opens the list once a loading document is ready, or says what JAWS says. And an element the page
#   took away is left out of the list, where 1.17 left the list empty when that happened at each of its three tries.
# - startupFocus: "Copilot pinned" when NVDA starts. Control+Alt+N, the key of NVDA's desktop shortcut, leaves the
#   focus on the taskbar (nvaccess/nvda#13028); JAWS, started with its own desktop shortcut's key, goes back to the
#   window you were in, and now NVDA does too, before it says where the focus is.
# The imitation NVDA is test_v117_fixes' (NVDA 2026.2's ElementsListDialog.initElementType and filter,
# VirtualBufferQuickNavItem and VirtualBufferTextInfo, word for word), with NVDA 2026.2's GlobalGestureMap.add and
# getScriptsForGesture (without their docstrings), BrowseModeTreeInterceptor's own gestures and core._setInitialFocus,
# word for word, and the tree
# interceptor step of scriptHandler._yieldObjectsForFindScript. Windows' windows are imitated for startupFocus, in the
# order of the screen, as the tester's taskbar and a Notepad window. The assistant's code is the real one.
# Run: python -m unittest tests.test_v118_fixes -v

import os
import sys
import types
import typing
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v117_fixes as v117  # noqa: E402
from jawsMigrator import elementsList, startupFocus  # noqa: E402

LINKS = ["Skip to content; same page", "Homepage; visited", "Issues (10); visited", "Pull requests", "What's new in 1.15; same page", "Updates; same page"]


# -- elements the page takes away ----------------------------------------------------------------------------------


class ElementsThePageTookAwayTests(v117.ImitationNvdaTestCase):
	def test_aPageThatNeverHoldsStill(self):
		# 1.17: three listings, each with a link gone before its name was read, left the list empty. Now the list holds
		# what is still on the page, as JAWS's Links List does, and there is nothing to say.
		elementsList.register()
		self.document.meanwhile.extend([v117.takeAway(12), v117.takeAway(40), v117.takeAway(41)])
		dialog = self.openList()
		self.assertEqual(dialog.labels(), ["Skip to content; same page", "Homepage; visited", "Issues (10); visited"])
		self.assertTrue(dialog.activateButton.Enabled and dialog.moveButton.Enabled, "Enter activates the link")
		self.assertEqual(self.later, [], "nothing to say")
		self.assertEqual(nvdaStubs.spoken, [])

	def test_nvdaAloneStopsInTheFilterBox(self):
		# Typing in the Filter box reads every name again (NVDA's filter): a link gone since stops NVDA there.
		dialog = self.openList()
		v117.takeAway(12)(self.page)
		with self.assertRaises(LookupError):
			dialog.filter("i")

	def test_typingInTheFilterBoxAfterALinkWentAway(self):
		elementsList.register()
		dialog = self.openList()
		v117.takeAway(12)(self.page)
		v117.alertAbove(self.page)
		dialog.filter("i")
		self.assertEqual(dialog.labels(), ["Skip to content; same page", "Homepage; visited", "Issues (10); visited", "What's new in 1.15; same page"])
		dialog.filter("")
		self.assertEqual(dialog.labels(), [label for label in LINKS if label != "Pull requests"], "and it stays out")

	def test_aHeadingUnderOneTakenAway(self):
		elementsList.register()
		dialog = self.openList("heading")
		self.page.elements.remove(self.page.byIdentifier(52))
		dialog.filter("")
		self.assertEqual(
			dialog.parentLabels(),
			{"jawsMigrator": None, "What's new in 1.15": "jawsMigrator", "Choosing what to import": "jawsMigrator"},
			"a heading under one taken away comes under the one above that",
		)

	def test_theElementTheListStartsOnWentAway(self):
		# NVDA starts the list on the element at the caret; when the page took it away, on the one before it.
		self.document.caret = self.page.offsets()[12][0]
		elementsList.register()
		dialog = self.openList()
		self.assertEqual(dialog.tree.selection["label"], "Pull requests")
		v117.takeAway(12)(self.page)
		dialog.filter("", newElementType=True)
		self.assertEqual(dialog.tree.selection["label"], "Issues (10); visited")

	def test_everyLinkTakenAway(self):
		elementsList.register()
		def takeAwayEveryLink(page):
			page.elements[:] = [element for element in page.elements if element.itemType != "link"]

		self.document.meanwhile.append(takeAwayEveryLink)
		dialog = self.openList()
		self.assertEqual(dialog.labels(), [])
		self.assertFalse(dialog.activateButton.Enabled or dialog.moveButton.Enabled, "Escape closes the dialog")
		self.assertEqual(self.later, [])

	def test_nothingComesUnderAHeadingTakenAway(self):
		elementsList.register()
		items = list(self.document._iterNodesByType("heading"))
		self.page.elements.remove(self.page.byIdentifier(52))
		self.assertFalse(items[3].isChild(items[2]))
		self.assertTrue(elementsList.isGone(items[2]))
		self.assertFalse(elementsList.isGone(items[3]))

	def test_anotherErrorStillLeavesTheListEmpty(self):
		# Filling the list failing three times for another reason: the list opens empty, and NVDA says why.
		elementsList.register()
		with mock.patch.object(self.document, "_iterNodesByType", side_effect=RuntimeError("broken")):
			dialog = self.openList()
		self.assertEqual(dialog.labels(), [])
		self.runLater()
		self.assertEqual(nvdaStubs.spoken, [elementsList.PAGE_CHANGED])

	def test_filterIsGivenBack(self):
		original = vars(v117.ElementsListDialog)["filter"]
		elementsList.register()
		self.assertTrue(elementsList._isOurs(vars(v117.ElementsListDialog)["filter"]))
		elementsList.unregister()
		self.assertIs(vars(v117.ElementsListDialog)["filter"], original)


# -- the Elements List's key where NVDA has no browse mode document ------------------------------------------------


def nvdaCode(source, name, namespace=None):
	namespace = dict(namespace or {})
	exec(source, namespace)
	return namespace[name]


def normalizeGestureIdentifier(identifier):
	return identifier.lower()


# NVDA 2026.2's inputCore.GlobalGestureMap.add and getScriptsForGesture, word for word.
GLOBAL_GESTURE_MAP = (
	"class GlobalGestureMap:\n"
	"	def __init__(self):\n"
	"		self._map = {}\n"
	"\n"
	"	def add(\n"
	"		self,\n"
	"		gesture: str,\n"
	"		module: str,\n"
	"		className: str,\n"
	"		script: Optional[ScriptNameT],\n"
	"		replace: bool = False,\n"
	"	):\n"
	"		gesture = normalizeGestureIdentifier(gesture)\n"
	"		try:\n"
	"			scripts = self._map[gesture]\n"
	"		except KeyError:\n"
	"			scripts = self._map[gesture] = []\n"
	"		if replace:\n"
	"			del scripts[:]\n"
	"		scripts.append((module, className, script))\n"
	"\n"
	"	def getScriptsForGesture(self, gesture: str) -> Generator[InputGestureScriptT, None, None]:\n"
	"		try:\n"
	"			scripts = self._map[gesture]\n"
	"		except KeyError:\n"
	"			return\n"
	"		for moduleName, className, scriptName in scripts:\n"
	"			try:\n"
	"				module = sys.modules[moduleName]\n"
	"			except KeyError:\n"
	"				continue\n"
	"			try:\n"
	"				cls = getattr(module, className)\n"
	"			except AttributeError:\n"
	"				continue\n"
	"			yield cls, scriptName\n"
)
GlobalGestureMap = nvdaCode(
	GLOBAL_GESTURE_MAP,
	"GlobalGestureMap",
	{"sys": sys, "Optional": typing.Optional, "ScriptNameT": str, "Generator": typing.Generator, "InputGestureScriptT": tuple, "normalizeGestureIdentifier": normalizeGestureIdentifier},
)


# NVDA 2026.2's browseMode.BrowseModeTreeInterceptor.__gestures, word for word, and the script it names.
BrowseModeTreeInterceptor = nvdaCode(
	"class BrowseModeTreeInterceptor:\n"
	"	def __init__(self, isReady=True):\n"
	"		self.isReady = isReady\n"
	"		self.isAlive = True\n"
	"		self.passThrough = False\n"
	"		self.opened = 0\n"
	"\n"
	"	def script_elementsList(self, gesture):\n"
	"		self.opened += 1\n"
	"\n"
	"	__gestures = {\n"
	"		\"kb:NVDA+f7\": \"elementsList\",\n"
	"		\"kb:enter\": \"activatePosition\",\n"
	"		\"kb:numpadEnter\": \"activatePosition\",\n"
	"		\"kb:space\": \"activatePosition\",\n"
	"		\"kb:NVDA+shift+space\": \"toggleSingleLetterNav\",\n"
	"		\"kb:escape\": \"disablePassThrough\",\n"
	"		\"kb:control+enter\": \"passThrough\",\n"
	"		\"kb:control+numpadEnter\": \"passThrough\",\n"
	"		\"kb:shift+enter\": \"passThrough\",\n"
	"		\"kb:shift+numpadEnter\": \"passThrough\",\n"
	"		\"kb:control+shift+enter\": \"passThrough\",\n"
	"		\"kb:control+shift+numpadEnter\": \"passThrough\",\n"
	"		\"kb:alt+enter\": \"passThrough\",\n"
	"		\"kb:alt+numpadEnter\": \"passThrough\",\n"
	"		\"kb:applications\": \"passThrough\",\n"
	"		\"kb:shift+applications\": \"passThrough\",\n"
	"		\"kb:shift+f10\": \"passThrough\",\n"
	"	}\n",
	"BrowseModeTreeInterceptor",
)


class Focus:
	"""NVDA's focus object: the Downloads panel's link the tester was on, or a control outside any document."""

	def __init__(self, treeInterceptor=None, sleepMode=False):
		self.treeInterceptor = treeInterceptor
		self.sleepMode = sleepMode


class KeyGesture:
	"""NVDA's KeyboardInputGesture, as NVDA+F7 on the laptop layout: its identifiers, and the script NVDA finds for it."""

	def __init__(self, key, focus, isModifier=False):
		self.identifiers = [f"kb(laptop):{key}", f"kb:{key}"]
		self.normalizedIdentifiers = [identifier.lower() for identifier in self.identifiers]
		self.isModifier = isModifier
		self.focus = focus

	@property
	def script(self):
		# scriptHandler._yieldObjectsForFindScript, NVDA 2026.2: a tree interceptor's scripts only while it is ready.
		treeInterceptor = self.focus.treeInterceptor
		if not (treeInterceptor and treeInterceptor.isReady):
			return None
		for identifier in self.normalizedIdentifiers:
			for cls, scriptName in sys.modules["inputCore"].manager.userGestureMap.getScriptsForGesture(identifier):
				if isinstance(treeInterceptor, cls):
					return getattr(treeInterceptor, f"script_{scriptName}") if scriptName else None
		gestures = vars(BrowseModeTreeInterceptor)["_BrowseModeTreeInterceptor__gestures"]
		ownGestures = {identifier.lower() for identifier, name in gestures.items() if name == "elementsList"}
		if ownGestures.intersection(self.normalizedIdentifiers):
			return treeInterceptor.script_elementsList
		return None


class ElementsListKeyTests(unittest.TestCase):
	def setUp(self):
		self.focus = Focus()
		self.queued = []
		self.later = []
		self.clock = [1000.0]
		inputCore = sys.modules["inputCore"]
		self.manager = types.SimpleNamespace(userGestureMap=GlobalGestureMap(), localeGestureMap=GlobalGestureMap(), isInputHelpActive=False)
		browseModule = types.ModuleType("browseMode")
		browseModule.BrowseModeTreeInterceptor = BrowseModeTreeInterceptor
		modules = {
			"browseMode": browseModule,
			"api": types.SimpleNamespace(getFocusObject=lambda: self.focus),
			"queueHandler": types.SimpleNamespace(eventQueue="eventQueue", queueFunction=lambda queue, function, *args: self.queued.append((function, args))),
			"core": types.SimpleNamespace(callLater=lambda delay, function, *args: self.later.append((delay, function, args))),
		}
		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		managerPatcher = mock.patch.object(inputCore, "manager", self.manager)
		managerPatcher.start()
		self.addCleanup(managerPatcher.stop)
		clock = mock.patch.object(elementsList.time, "monotonic", lambda: self.clock[0])
		clock.start()
		self.addCleanup(clock.stop)
		self.addCleanup(elementsList.unregister)
		nvdaStubs.spoken.clear()
		elementsList._failed = False

	def press(self, key="NVDA+f7", isModifier=False):
		"""A key press: NVDA asks its deciders, then runs the script it finds, or gives the key to the program."""
		gesture = KeyGesture(key, self.focus, isModifier)
		if not sys.modules["inputCore"].decide_executeGesture.decide(gesture=gesture):
			return "kept"
		return "script" if gesture.script else "program"

	def runCore(self, seconds=0.0):
		"""NVDA's core: what was queued, then what is due by ``seconds`` from now, as time goes on."""
		for function, args in self.queued[:]:
			self.queued.remove((function, args))
			function(*args)
		end = self.clock[0] + seconds
		while self.later and self.clock[0] < end:
			delay, function, args = self.later.pop(0)
			self.clock[0] += delay / 1000
			function(*args)

	def test_nvdaAloneGivesEdgeF7(self):
		self.focus.treeInterceptor = BrowseModeTreeInterceptor(isReady=False)
		self.assertEqual(self.press(), "program", "Edge gets F7: Turn on caret browsing?")

	def test_theTestersKeyStaysFromEdge(self):
		# The Downloads panel's document, no longer ready, and never ready again: NVDA waits three seconds, then says so.
		downloads = BrowseModeTreeInterceptor(isReady=False)
		self.focus.treeInterceptor = downloads
		elementsList.register()
		self.assertEqual(self.press(), "kept")
		self.runCore(seconds=2.9)
		self.assertEqual(nvdaStubs.spoken, [], "still waiting for the document")
		self.runCore(seconds=0.5)
		self.assertEqual(nvdaStubs.spoken, [elementsList.NOT_IN_DOCUMENT])
		self.assertEqual(downloads.opened, 0)
		self.assertEqual(self.later, [], "and no more waiting")

	def test_aDocumentThatBecomesReady(self):
		page = BrowseModeTreeInterceptor(isReady=False)
		self.focus.treeInterceptor = page
		elementsList.register()
		self.assertEqual(self.press(), "kept")
		self.runCore(seconds=0.3)
		page.isReady = True
		self.runCore(seconds=0.3)
		self.assertEqual(page.opened, 1, "the list opens once the page is ready")
		self.assertEqual(nvdaStubs.spoken, [])
		self.assertEqual(self.later, [])

	def test_theFocusMovesToAReadyPage(self):
		elementsList.register()
		self.focus.treeInterceptor = BrowseModeTreeInterceptor(isReady=False)
		self.press()
		self.runCore(seconds=0.2)
		page = BrowseModeTreeInterceptor()
		self.focus = Focus(page)
		self.runCore(seconds=0.2)
		self.assertEqual(page.opened, 1)

	def test_noDocumentAtAll(self):
		# In Notepad, say: NVDA says what JAWS says for Insert+F7 at once, and F7 doesn't reach Notepad.
		elementsList.register()
		self.assertEqual(self.press(), "kept")
		self.runCore()
		self.assertEqual(nvdaStubs.spoken, [elementsList.NOT_IN_DOCUMENT])
		self.assertEqual(self.later, [])

	def test_anotherKeyEndsTheWait(self):
		page = BrowseModeTreeInterceptor(isReady=False)
		self.focus.treeInterceptor = page
		elementsList.register()
		self.press()
		self.runCore(seconds=0.2)
		self.assertEqual(self.press("downArrow"), "program")
		page.isReady = True
		self.runCore(seconds=1)
		self.assertEqual(page.opened, 0, "the list doesn't open after the tester has gone on")
		self.assertEqual(nvdaStubs.spoken, [])

	def test_aModifierAloneDoesntEndTheWait(self):
		page = BrowseModeTreeInterceptor(isReady=False)
		self.focus.treeInterceptor = page
		elementsList.register()
		self.press()
		self.runCore(seconds=0.2)
		self.press("shift", isModifier=True)
		page.isReady = True
		self.runCore(seconds=0.2)
		self.assertEqual(page.opened, 1)

	def test_aReadyDocumentIsLeftToNvda(self):
		page = BrowseModeTreeInterceptor()
		page.passThrough = True
		self.focus.treeInterceptor = page
		elementsList.register()
		self.assertEqual(self.press(), "script", "NVDA opens its list, in focus mode too")
		self.assertEqual(self.queued, [])

	def test_otherKeysAreLeftAlone(self):
		elementsList.register()
		for key in ("f7", "NVDA+f6", "alt+leftArrow", "e"):
			self.assertEqual(self.press(key), "program", key)
		self.assertEqual(self.queued, [])

	def test_aJawsKeyTheMigrationGaveTheList(self):
		# JAWS's Insert+F6 (headings list), as the migration binds it: F6 would put Edge's focus in its address bar.
		self.manager.userGestureMap.add("kb:NVDA+f6", "browseMode", "BrowseModeTreeInterceptor", "elementsList")
		elementsList.register()
		self.assertEqual(self.press("NVDA+f6"), "kept")
		self.runCore()
		self.assertEqual(nvdaStubs.spoken, [elementsList.NOT_IN_DOCUMENT])

	def test_aKeyTheUserTookAway(self):
		self.manager.userGestureMap.add("kb:NVDA+f7", "browseMode", "BrowseModeTreeInterceptor", None)
		elementsList.register()
		self.assertEqual(self.press(), "program", "the user unbound NVDA+F7 from the Elements List")

	def test_inputHelpAndSleepMode(self):
		elementsList.register()
		self.manager.isInputHelpActive = True
		self.assertEqual(self.press(), "program", "input help says what the key does")
		self.manager.isInputHelpActive = False
		self.focus.sleepMode = True
		self.assertEqual(self.press(), "program", "in sleep mode every key goes to the program")

	def test_unregister(self):
		elementsList.register()
		elementsList.register()
		deciders = sys.modules["inputCore"].decide_executeGesture.handlers
		self.assertEqual(deciders.count(elementsList.decideGesture), 1)
		elementsList.unregister()
		self.assertNotIn(elementsList.decideGesture, deciders)
		self.assertEqual(self.press(), "program")


# -- NVDA started with the focus on the taskbar --------------------------------------------------------------------


class Window:
	def __init__(self, className, title="", process=4000, visible=True, minimized=False, enabled=True, cloaked=False, style=0, owner=0, size=True, focus=None):
		self.className, self.title, self.process = className, title, process
		self.visible, self.minimized, self.enabled, self.cloaked = visible, minimized, enabled, cloaked
		self.style, self.owner, self.size = style, owner, size
		#: What NVDA says for the focus in this window, when it is in the foreground.
		self.focus = focus or title
		self.lastPopup = None
		self.children = []


class Windows:
	"""Windows' top-level windows, from the top of the screen's order down, as startupFocus asks about them."""

	def __init__(self, windows, foreground, shell=None, allows=True):
		self.windows = {number: window for number, window in enumerate(windows, start=100)}
		self.numbers = {id(window): number for number, window in self.windows.items()}
		self._foreground = self.number(foreground)
		self._shell = self.number(shell) if shell is not None else 0
		self.allows = allows
		self.madeForeground = []

	def number(self, window):
		return self.numbers[id(window)] if window is not None else 0

	def foreground(self):
		return self._foreground

	def setForeground(self, window):
		self.madeForeground.append(window)
		if self.allows:
			self._foreground = window
		return self.allows

	def zOrder(self):
		return iter(self.windows)

	def className(self, window):
		return self.windows[window].className

	def processId(self, window):
		return self.windows[window].process

	def isVisible(self, window):
		return self.windows[window].visible

	def isEnabled(self, window):
		return self.windows[window].enabled

	def isMinimized(self, window):
		return self.windows[window].minimized

	def isCloaked(self, window):
		return self.windows[window].cloaked

	def extendedStyle(self, window):
		return self.windows[window].style

	def hasTitle(self, window):
		return bool(self.windows[window].title)

	def hasSize(self, window):
		return self.windows[window].size

	def rootOwner(self, window):
		owner = self.windows[window].owner
		while owner and self.windows[owner].owner:
			owner = self.windows[owner].owner
		return owner or window

	def lastActivePopup(self, window):
		popup = self.windows[window].lastPopup
		return self.number(popup) if popup is not None else window

	def shellWindow(self):
		return self._shell

	def child(self, parent, className):
		return 1 if className in self.windows[parent].children else 0

	def topLevel(self, className):
		return (number for number, window in self.windows.items() if window.className == className)


NVDA_PROCESS = 1234
#: The tester's Windows 11: a tool window on top of everything, the taskbar, then the windows in the order last used.
def testersWindows():
	osd = Window("JUCE_1a0d855f99c", "QA OSD", style=startupFocus.WS_EX_TOOLWINDOW)
	taskbar = Window("Shell_TrayWnd", focus="Copilot pinned, button")
	nvda = Window("wxWindowNR", "NVDA", process=NVDA_PROCESS)
	notepad = Window("Notepad", "Untitled - Notepad", focus="Text editor, blank")
	settings = Window("ApplicationFrameWindow", "Settings", cloaked=True)
	edge = Window("Chrome_WidgetWin_1", "Issue #11 - Microsoft Edge")
	desktop = Window("Progman", "Program Manager", focus="Desktop, list")
	desktop.children.append(startupFocus.DESKTOP_VIEW)
	return types.SimpleNamespace(osd=osd, taskbar=taskbar, nvda=nvda, notepad=notepad, settings=settings, edge=edge, desktop=desktop)


# NVDA 2026.2's core._setInitialFocus, word for word.
SET_INITIAL_FOCUS = (
	"def _setInitialFocus():\n"
	"	\"\"\"Sets the initial focus if no focus event was received at startup.\"\"\"\n"
	"	import eventHandler\n"
	"	import api\n"
	"\n"
	"	if eventHandler.lastQueuedFocusObject:\n"
	"		# The focus has already been set or a focus event is pending.\n"
	"		return\n"
	"	try:\n"
	"		focus = api.getDesktopObject().objectWithFocus()\n"
	"		if focus:\n"
	"			eventHandler.queueEvent(\"gainFocus\", focus)\n"
	"	except:  # noqa: E722\n"
	"		log.exception(\"Error retrieving initial focus\")\n"
)


class StartupFocusTests(unittest.TestCase):
	def setUp(self):
		self.starting = True
		self.spokenFocus = []
		tracking = types.SimpleNamespace(isInitializationComplete=lambda: not self.starting)
		self.eventHandler = types.SimpleNamespace(lastQueuedFocusObject=None, queueEvent=lambda name, obj: self.spokenFocus.append(obj))
		modules = {
			"NVDAState": types.SimpleNamespace(_TrackNVDAInitialization=tracking),
			"globalVars": types.SimpleNamespace(appPid=NVDA_PROCESS),
			"eventHandler": self.eventHandler,
		}
		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		startupFocus._failed = False

	def windows(self, order, foreground, **kwargs):
		w = testersWindows()
		windows = Windows([getattr(w, name) for name in order], getattr(w, foreground), shell=w.desktop if "desktop" in order else None, **kwargs)
		return w, windows

	def nvdaSaysAtStart(self, windows):
		"""NVDA's _setInitialFocus, after its plugins started: what it says, the focus in the foreground window."""
		desktopObject = types.SimpleNamespace(objectWithFocus=lambda: windows.windows[windows.foreground()].focus)
		sys.modules["api"] = types.SimpleNamespace(getDesktopObject=lambda: desktopObject)
		try:
			nvdaCode(SET_INITIAL_FOCUS, "_setInitialFocus", {"log": mock.Mock()})()
		finally:
			del sys.modules["api"]
		return self.spokenFocus[-1]

	ALL = ("osd", "taskbar", "nvda", "notepad", "settings", "edge", "desktop")

	def test_nvdaAloneSaysCopilotPinned(self):
		w, windows = self.windows(self.ALL, "taskbar")
		self.assertEqual(self.nvdaSaysAtStart(windows), "Copilot pinned, button")

	def test_controlAltNInNotepad(self):
		w, windows = self.windows(self.ALL, "taskbar")
		self.assertEqual(startupFocus.atStart(windows), windows.number(w.notepad))
		self.assertEqual(self.nvdaSaysAtStart(windows), "Text editor, blank", "NVDA says where you were, as JAWS does")

	def test_theSecondMonitorsTaskbar(self):
		w, windows = self.windows(self.ALL, "taskbar")
		w.taskbar.className = "Shell_SecondaryTrayWnd"
		self.assertEqual(startupFocus.atStart(windows), windows.number(w.notepad))

	def test_notOnTheTaskbar(self):
		# NVDA's own restart (NVDA+Q) leaves the focus in the window you were in: nothing to do.
		w, windows = self.windows(self.ALL, "edge")
		self.assertEqual(startupFocus.atStart(windows), 0)
		self.assertEqual(windows.madeForeground, [])

	def test_notWhenNvdaReloadsItsPlugins(self):
		self.starting = False
		w, windows = self.windows(self.ALL, "taskbar")
		self.assertEqual(startupFocus.atStart(windows), 0, "you may have put the focus on the taskbar yourself")
		self.assertEqual(windows.madeForeground, [])

	def test_everyWindowMinimized(self):
		w, windows = self.windows(self.ALL, "taskbar")
		w.notepad.minimized = w.edge.minimized = True
		self.assertEqual(startupFocus.atStart(windows), windows.number(w.desktop), "Windows+D, then Control+Alt+N")
		self.assertEqual(self.nvdaSaysAtStart(windows), "Desktop, list")

	def test_theDesktopInAWorkerW(self):
		w, windows = self.windows(("taskbar", "desktop"), "taskbar")
		w.desktop.children.clear()
		worker = Window("WorkerW")
		worker.children.append(startupFocus.DESKTOP_VIEW)
		windows.windows[999] = worker
		self.assertEqual(startupFocus.atStart(windows), 999)

	def test_windowsNotToGoBackTo(self):
		# Tool windows, NVDA's own, other virtual desktops' and suspended Store apps', hidden, empty or untitled windows.
		w, windows = self.windows(self.ALL, "taskbar")
		w.notepad.cloaked = True
		w.edge.visible = False
		self.assertEqual(startupFocus.atStart(windows), windows.number(w.desktop))
		for name, change in (
			("style", startupFocus.WS_EX_NOACTIVATE),
			("title", ""),
			("size", False),
			("enabled", False),
		):
			w, windows = self.windows(("taskbar", "notepad", "desktop"), "taskbar")
			setattr(w.notepad, name, change)
			self.assertEqual(startupFocus.windowYouWereIn(windows, NVDA_PROCESS), 0, name)
		w, windows = self.windows(("taskbar", "notepad"), "taskbar")
		w.notepad.style = startupFocus.WS_EX_TOOLWINDOW | startupFocus.WS_EX_APPWINDOW
		self.assertEqual(startupFocus.windowYouWereIn(windows, NVDA_PROCESS), windows.number(w.notepad), "a tool window Alt+Tab lists")

	def test_aDialogAboveItsWindow(self):
		# Notepad's Find dialog is kept above Notepad; you were in Notepad itself when you pressed Control+Alt+N.
		w = testersWindows()
		find = Window("#32770", "Find")
		windows = Windows([w.taskbar, find, w.notepad, w.desktop], w.taskbar, shell=w.desktop)
		find.owner = windows.number(w.notepad)
		self.assertEqual(startupFocus.windowYouWereIn(windows, NVDA_PROCESS), windows.number(w.notepad))
		w.notepad.lastPopup = find
		self.assertEqual(startupFocus.windowYouWereIn(windows, NVDA_PROCESS), windows.number(find), "and in Find when you were in Find")

	def test_aWindowWhoseOwnerIsMinimized(self):
		w, windows = self.windows(("taskbar", "notepad", "edge"), "taskbar")
		w.edge.minimized = True
		w.notepad.owner = windows.number(w.edge)
		self.assertEqual(startupFocus.windowYouWereIn(windows, NVDA_PROCESS), 0)

	def test_windowsDoesntAllowIt(self):
		w, windows = self.windows(self.ALL, "taskbar", allows=False)
		self.assertEqual(startupFocus.atStart(windows), 0)
		self.assertEqual(windows.madeForeground, [windows.number(w.notepad)])
		self.assertEqual(self.nvdaSaysAtStart(windows), "Copilot pinned, button", "as NVDA alone")

	def test_nothingToGoBackTo(self):
		w, windows = self.windows(("taskbar",), "taskbar")
		self.assertEqual(startupFocus.atStart(windows), 0)

	def test_aFailureIsLogged(self):
		w, windows = self.windows(self.ALL, "taskbar")
		with mock.patch.object(windows, "zOrder", side_effect=OSError("gone")):
			self.assertEqual(startupFocus.atStart(windows), 0)
		self.assertTrue(startupFocus._failed)

	def test_wanted(self):
		self.assertTrue(startupFocus.wanted({}))
		self.assertFalse(startupFocus.wanted({startupFocus.STATE_KEY: False}))
		self.assertFalse(startupFocus.wanted(None))

	@unittest.skipUnless(sys.platform == "win32", "Windows only")
	def test_thisComputersWindows(self):
		# Windows' own functions, as startupFocus declares them, on this computer's windows: read only.
		windows = startupFocus.Win32()
		foreground = windows.foreground()
		self.assertIsInstance(windows.className(foreground) if foreground else "", str)
		listed = list(windows.zOrder())
		self.assertTrue(listed, "top-level windows")
		for window in listed[:50]:
			self.assertIsInstance(startupFocus.canBeYours(windows, window, os.getpid()), bool)
		self.assertIsInstance(startupFocus.desktop(windows), int)


if __name__ == "__main__":
	unittest.main()
