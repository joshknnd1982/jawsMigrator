# Unit tests for version 1.20, from a tester's answer to question 6 about version 1.19 (issue 11): NVDA+F7 on a GitHub
# page right after it loads, and again after Alt+Left. The tester's log of 25 September, 15:52 to 15:58, shows three
# things JAWS doesn't do:
# - linksList: Alt+Left from a GitHub issue went to Edge's New Tab page, which has no links. NVDA+F7 opened an empty
#   Elements List: "Elements List dialog", "tree view", and nothing at Down Arrow. The tester wrote down "It said element
#   tree view." JAWS's Insert+F7 says "no links" there (Virtual.jss, SelectALinkDialog and ReportLinksNotAvailable;
#   common.jsm, cmsgNoLinks) and opens nothing. Now NVDA says so too.
# - linksList: on the page of the tester's repositories the list opened on "Current page Repositories (48), 10 of 128",
#   the tester chose "reply-to-sender-outlook" and pressed Enter, went back with Alt+Left, and NVDA+F7 opened on
#   "Current page Repositories (48), 10 of 128" again. NVDA activates a link from its list without moving its browse mode
#   cursor there, so the cursor, and the place Browse Mode Caret Fix keeps for Alt+Left, stayed on Repositories. Now
#   activating a link from the list moves the cursor to it first, as Move to does.
# - elementsList: when GitHub changed the page as NVDA filled the list, NVDA filled it again, and said "Skip to content
#   level 1, 1 of 69" three times, then "Skip to content, 1 of 69". Now NVDA says the item once.
# The imitation NVDA is test_v117_fixes' (NVDA 2026.2's ElementsListDialog.initElementType and filter,
# VirtualBufferQuickNavItem and VirtualBufferTextInfo, word for word), with NVDA 2026.2's own
# BrowseModeTreeInterceptor.script_elementsList and _get_ElementsListDialog, ElementsListDialog.ELEMENT_TYPES and
# onAction, TextInfoQuickNavItem.activate and moveTo, BrowseModeDocumentTreeInterceptor._activatePosition,
# IAccessible.isDuplicateIAccessibleEvent and IAccessibleHandler.processFocusNVDAEvent, word for word. The focus events
# come from Windows itself: a real tree view made as NVDA makes its Elements List's (a wx.TreeCtrl, with the focus while
# NVDA fills it), filled by NVDA's own initElementType and filter through the assistant's real wrappers, read through
# MSAA as NVDA reads it. Browse Mode Caret Fix is imitated: it keeps the place of browse mode's cursor when NVDA
# activates a link (its _patched_activatePosition), and puts the cursor back there at Alt+Left. The assistant's code is
# the real one.
# Run: python -m unittest tests.test_v120_fixes -v

import ctypes
import enum
import os
import sys
import threading
import time
import types
import unittest
from ctypes import wintypes
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import wx  # noqa: E402

import test_v117_fixes as v117  # noqa: E402
import test_v119_fixes as v119  # noqa: E402
from jawsMigrator import elementsList, linksList  # noqa: E402

Element = v117.Element

#: Edge's New Tab page, where Alt+Left from the GitHub issue went at 15:53:19: "main landmark, search landmark, button,
#: Search", and no link.
NEW_TAB = [Element(1, "landmark", "main"), Element(2, "landmark", "search"), Element(3, "button", "Search")]
#: The page of the tester's repositories (github.com/joshknnd1982?tab=repositories), its first links and the one chosen.
REPOSITORIES = [
	Element(1, "link", "Skip to content"),
	Element(2, "link", "Homepage"),
	Element(9, "link", "Overview"),
	Element(10, "link", "Repositories (48)"),
	Element(11, "link", "Projects"),
	Element(12, "link", "Packages"),
	Element(20, "heading", "joshknnd1982", level=1),
	Element(21, "link", "jawsMigrator"),
	Element(32, "link", "reply-to-sender-outlook"),
	Element(66, "link", "rommix0/DECtalk-DTC-01-SAPI5"),
]


def _(text):
	return text


class OutputReason(enum.Enum):
	"""NVDA's controlTypes.OutputReason, as far as moving goes."""

	FOCUS = "focus"
	QUICKNAV = "quicknav"


class State(enum.Enum):
	FOCUSABLE = "focusable"


controlTypes = types.ModuleType("controlTypes")
controlTypes.OutputReason, controlTypes.State = OutputReason, State


def reportPassThrough(treeInterceptor, onlyIfChanged=True):
	"""NVDA's browseMode.reportPassThrough: says "focus mode" or "browse mode" when it changed; nothing here changes it."""


class Collapsing:
	"""NVDA's OffsetsTextInfo.collapse, word for word, for test_v117_fixes' TextInfo."""

	def collapse(self, end=False):
		if not end:
			self._endOffset = self._startOffset
		else:
			self._startOffset = self._endOffset


class MainFrame:
	"""NVDA's gui.mainFrame, as far as its dialogs go."""

	prevFocus = None

	def prePopup(self):
		pass

	def postPopup(self):
		pass


def nvdaCode(source, name, namespace):
	"""Compile NVDA's own ``source`` against the imitation NVDA, and give back ``name`` from it."""
	scope = dict(namespace)
	exec(source, scope)
	return scope[name]


# -- the Elements List, and the page it lists ---------------------------------------------------------------------------


#: Each Elements List made, and whether it came up.
made = []


class ElementsListDialog(v117.ElementsListDialog):
	"""NVDA 2026.2's browseMode.ElementsListDialog, without its window: what NVDA's __init__ makes, then fills."""

	lastSelectedElementType = 0

	def __init__(self, document):
		super().__init__(document)
		self.shown = self.closed = False
		made.append(self)
		# The end of NVDA's __init__: the list is filled with the kind of element chosen last.
		self.initElementType(self.ELEMENT_TYPES[self.lastSelectedElementType][0])

	def ShowModal(self):
		self.shown = True

	def Destroy(self):
		pass

	def Close(self):
		self.closed = True

	def selected(self):
		"""The item the list is on, as NVDA says it: its label and its place ("10 of 128")."""
		item = self.tree.selection
		return (item["label"], f"{self.tree.items.index(item) + 1} of {len(self.tree.items)}") if item else None

	def choose(self, label):
		"""Arrow or type to an item of the list."""
		self.tree.SelectItem(next(item for item in self.tree.items if item["label"] == label))


# NVDA 2026.2's ElementsListDialog.ELEMENT_TYPES and onAction, word for word.
ElementsListDialog.ELEMENT_TYPES = nvdaCode(
	"ELEMENT_TYPES = (\n"
	"	# Translators: The label of a radio button to select the type of element\n"
	"	# in the browse mode Elements List dialog.\n"
	"	(\"link\", _(\"Lin&ks\")),\n"
	"	# Translators: The label of a radio button to select the type of element\n"
	"	# in the browse mode Elements List dialog.\n"
	"	(\"heading\", _(\"&Headings\")),\n"
	"	# Translators: The label of a radio button to select the type of element\n"
	"	# in the browse mode Elements List dialog.\n"
	"	(\"formField\", _(\"&Form fields\")),\n"
	"	# Translators: The label of a radio button to select the type of element\n"
	"	# in the browse mode Elements List dialog.\n"
	"	(\"button\", _(\"&Buttons\")),\n"
	"	# Translators: The label of a radio button to select the type of element\n"
	"	# in the browse mode Elements List dialog.\n"
	"	(\"landmark\", _(\"Lan&dmarks\")),\n"
	")\n",
	"ELEMENT_TYPES",
	{"_": _},
)
#: What NVDA runs after a delay (core.callLater): the Move to button's move.
later = []
gui = types.SimpleNamespace(mainFrame=MainFrame())
ElementsListDialog.onAction = nvdaCode(
	"def onAction(self, activate):\n"
	"	prevFocus = gui.mainFrame.prevFocus\n"
	"	self.Close()\n"
	"	# Save off the last selected element type on to the class so its used in initialization next time.\n"
	"	self.__class__.lastSelectedElementType = self.lastSelectedElementType\n"
	"	item = self.tree.GetSelection()\n"
	"	item = self.tree.GetItemData(item).item\n"
	"	if activate:\n"
	"		item.activate()\n"
	"	else:\n"
	"\n"
	"		def move():\n"
	"			speech.cancelSpeech()\n"
	"			# Avoid double announce if item.obj is about to gain focus.\n"
	"			if not (\n"
	"				self.document.passThrough\n"
	"				and getattr(item, \"obj\", False)\n"
	"				and item.obj != prevFocus\n"
	"				and controlTypes.State.FOCUSABLE in item.obj.states\n"
	"			):\n"
	"				# #8831: Report before moving because moving might change the focus, which\n"
	"				# might mutate the document, potentially invalidating info if it is\n"
	"				# offset-based.\n"
	"				item.report()\n"
	"			item.moveTo()\n"
	"\n"
	"		# We must use core.callLater rather than wx.CallLater to ensure that the callback runs within NVDA's core pump.\n"
	"		# If it didn't, and it directly or indirectly called wx.Yield, it could start executing NVDA's core pump from within the yield, causing recursion.\n"
	"		core.callLater(100, move)\n",
	"onAction",
	{
		"gui": gui,
		"controlTypes": controlTypes,
		"speech": types.SimpleNamespace(cancelSpeech=lambda: None),
		"core": types.SimpleNamespace(callLater=lambda delay, function, *args: later.append((function, args))),
	},
)

# NVDA 2026.2's TextInfoQuickNavItem.activate and moveTo, word for word.
_ITEM = {"controlTypes": controlTypes, "OutputReason": OutputReason, "reportPassThrough": reportPassThrough}
NVDA_ACTIVATE = nvdaCode(
	"def activate(self):\n"
	"	self.textInfo.obj._activatePosition(info=self.textInfo)\n",
	"activate",
	_ITEM,
)
NVDA_MOVE_TO = nvdaCode(
	"def moveTo(self):\n"
	"	if self.document.passThrough and getattr(self, \"obj\", False):\n"
	"		if controlTypes.State.FOCUSABLE in self.obj.states:\n"
	"			self.obj.setFocus()\n"
	"			return\n"
	"		self.document.passThrough = False\n"
	"		reportPassThrough(self.document)\n"
	"	info = self.textInfo.copy()\n"
	"	info.collapse()\n"
	"	self.document._set_selection(info, reason=OutputReason.QUICKNAV)\n",
	"moveTo",
	_ITEM,
)
#: The gestures NVDA's scripts are run with: NVDA+F7 on the laptop layout, as in the tester's log.
NVDA_F7 = types.SimpleNamespace(identifiers=["kb(laptop):NVDA+f7"])
wxForScripts = types.SimpleNamespace(CallAfter=lambda function, *args: function(*args))

# NVDA 2026.2's BrowseModeTreeInterceptor._get_ElementsListDialog and script_elementsList, word for word.
BrowseModeTreeInterceptor = nvdaCode(
	"class BrowseModeTreeInterceptor(Document):\n"
	"	def _get_ElementsListDialog(self):\n"
	"		return ElementsListDialog\n"
	"\n"
	"	def script_elementsList(self, gesture):\n"
	"		# We need this to be a modal dialog, but it mustn't block this script.\n"
	"		def run():\n"
	"			gui.mainFrame.prePopup()\n"
	"			d = self.ElementsListDialog(self)\n"
	"			d.ShowModal()\n"
	"			d.Destroy()\n"
	"			gui.mainFrame.postPopup()\n"
	"\n"
	"		wx.CallAfter(run)\n"
	"\n"
	"	# Translators: the description for the Elements List command in browse mode.\n"
	"	script_elementsList.__doc__ = _(\"Lists various types of elements in this document\")\n"
	"	script_elementsList.ignoreTreeInterceptorPassThrough = True\n",
	"BrowseModeTreeInterceptor",
	{"Document": v117.Document, "ElementsListDialog": ElementsListDialog, "gui": gui, "wx": wxForScripts, "_": _},
)
# NVDA makes a property of each _get_ method (baseObject.AutoPropertyType).
BrowseModeTreeInterceptor.ElementsListDialog = property(BrowseModeTreeInterceptor._get_ElementsListDialog)


class BrowseModeDocumentTreeInterceptor(BrowseModeTreeInterceptor):
	"""NVDA's browse mode document for the page, as the Elements List activates and moves: its cursor is the caret."""

	passThrough = False

	def __init__(self, page, caret=0):
		super().__init__(page, caret)
		#: What was activated, and how browse mode's cursor was moved.
		self.activated, self.moves = [], []

	@property
	def selection(self):
		return self.makeTextInfo(v117.POSITION_CARET)

	def _set_selection(self, info, reason=None):
		# CursorManager's: the caret goes there (browse mode's scrolls the page there and chooses the mode, too).
		self.caret = info._startOffset
		self.moves.append(reason)

	def at(self, info):
		element = self.page.at(info._startOffset)
		return element.text if element is not None else None

	def _activateNVDAObject(self, obj):
		self.activated.append(obj)


# NVDA 2026.2's BrowseModeDocumentTreeInterceptor._activatePosition, word for word; the object at a link's start is the
# link, and browse mode's own _activatePosition activates it (BrowseModeTreeInterceptor._activatePosition, for a link).
BrowseModeDocumentTreeInterceptor._activatePosition = nvdaCode(
	"def _activatePosition(self, obj=None, info=None):\n"
	"	if info:\n"
	"		obj = info.NVDAObjectAtStart\n"
	"		if not obj:\n"
	"			return\n"
	"	super(BrowseModeDocumentTreeInterceptor, self)._activatePosition(obj=obj)\n",
	"_activatePosition",
	{"BrowseModeDocumentTreeInterceptor": BrowseModeDocumentTreeInterceptor},
)
BrowseModeTreeInterceptor._activatePosition = lambda self, obj=None: self._activateNVDAObject(obj)
#: NVDA's textInfo.NVDAObjectAtStart, for test_v117_fixes' TextInfo: the element there.
NVDA_OBJECT_AT_START = property(lambda self: self.obj.at(self))


class WithBrowseModeCaretFix(BrowseModeDocumentTreeInterceptor):
	"""The page with Browse Mode Caret Fix, as the tester has it: where browse mode's cursor was when NVDA activated a
	link is kept (its _patched_activatePosition, which reads the cursor and keeps it when it is at a link), and Alt+Left
	puts the cursor back there."""

	def __init__(self, page, caret=0):
		super().__init__(page, caret)
		self.kept = []

	def _activatePosition(self, *args, **kwargs):
		cursor = self.selection
		element = self.page.at(cursor._startOffset)
		if element is not None and element.itemType == "link":
			self.kept.append(cursor._startOffset)
		return super()._activatePosition(*args, **kwargs)

	def back(self):
		"""Alt+Left, back to this page: Browse Mode Caret Fix restores the cursor it kept."""
		self.caret = self.kept.pop()


def offsetOf(page, text):
	for element in page.elements:
		if element.text == text:
			return page.offsets()[element.identifier][0]
	raise LookupError(text)


class ImitationNvdaTestCase(unittest.TestCase):
	def setUp(self):
		textInfosPackage = types.ModuleType("textInfos")
		offsets = types.ModuleType("textInfos.offsets")
		offsets.Offsets = v117.Offsets
		textInfosPackage.offsets = offsets
		virtualBuffers = types.ModuleType("virtualBuffers")
		virtualBuffers.VirtualBufferQuickNavItem = v117.VirtualBufferQuickNavItem
		browseModule = types.ModuleType("browseMode")
		browseModule.TextInfoQuickNavItem = v117.TextInfoQuickNavItem
		browseModule.BrowseModeTreeInterceptor = BrowseModeTreeInterceptor
		browseModule.BrowseModeDocumentTreeInterceptor = BrowseModeDocumentTreeInterceptor
		browseModule.ElementsListDialog = ElementsListDialog
		modules = {
			"textInfos": textInfosPackage,
			"textInfos.offsets": offsets,
			"virtualBuffers": virtualBuffers,
			"browseMode": browseModule,
			"controlTypes": controlTypes,
		}
		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		for owner, name, value in (
			(v117.TextInfoQuickNavItem, "activate", NVDA_ACTIVATE),
			(v117.TextInfoQuickNavItem, "moveTo", NVDA_MOVE_TO),
			(v117.TextInfo, "collapse", Collapsing.collapse),
			(v117.TextInfo, "NVDAObjectAtStart", NVDA_OBJECT_AT_START),
		):
			attribute = mock.patch.object(owner, name, value, create=True)
			attribute.start()
			self.addCleanup(attribute.stop)
		self.addCleanup(setattr, ElementsListDialog, "lastSelectedElementType", 0)
		self.addCleanup(self._restore)
		made.clear()
		later.clear()
		nvdaStubs.spoken.clear()
		linksList._failed = False

	def _restore(self):
		linksList.unregister()
		linksList._replaced.clear()
		linksList._failed = False

	def page(self, elements, at=None, document=BrowseModeDocumentTreeInterceptor):
		page = v117.Page(elements)
		v117.NVDAHelper.localLib = v117.LocalLib(page)
		return document(page, caret=offsetOf(page, at) if at else 0)

	def elementsList(self, document):
		"""NVDA+F7: the Elements List that came up, or None."""
		before = len(made)
		document.script_elementsList(NVDA_F7)
		dialogs = [dialog for dialog in made[before:] if dialog.shown]
		return dialogs[-1] if dialogs else None


# -- a page without links ----------------------------------------------------------------------------------------------


class PageWithoutLinksTests(ImitationNvdaTestCase):
	def test_nvdaAloneOpensAnEmptyList(self):
		# NVDA alone, as in the tester's log at 15:53:21: "Elements List dialog", "tree view", and nothing else.
		dialog = self.elementsList(self.page(NEW_TAB))
		self.assertIsNotNone(dialog)
		self.assertEqual(dialog.labels(), [])
		self.assertIsNone(dialog.selected(), "Down Arrow said nothing")
		self.assertEqual(nvdaStubs.spoken, [])

	def test_noLinksAsJawsSays(self):
		linksList.register()
		self.assertIsNone(self.elementsList(self.page(NEW_TAB)), "no list comes up")
		self.assertEqual(made, [], "NVDA doesn't make one either")
		self.assertEqual(nvdaStubs.spoken, ["no links"])

	def test_scriptStaysNvdas(self):
		# NVDA runs it in browse and focus mode alike, and Input Help and Input Gestures describe it as before.
		linksList.register()
		script = BrowseModeTreeInterceptor.script_elementsList
		self.assertTrue(script.ignoreTreeInterceptorPassThrough)
		self.assertEqual(script.__doc__, "Lists various types of elements in this document")
		self.assertEqual(script.__name__, "script_elementsList")

	def test_aPageWithLinksOpensAsBefore(self):
		linksList.register()
		dialog = self.elementsList(self.page(REPOSITORIES))
		self.assertEqual(dialog.selected(), ("Skip to content", "1 of 9"))
		self.assertEqual(nvdaStubs.spoken, [])

	def test_aListLeftOnAnotherKindOpensAsBefore(self):
		# The tester chose Headings in the list and moved to one: NVDA opens the list on headings next time, and on a page
		# without headings it opens as before, empty, so that Links, Buttons or Landmarks can be chosen there.
		linksList.register()
		ElementsListDialog.lastSelectedElementType = 1
		dialog = self.elementsList(self.page(NEW_TAB))
		self.assertIsNotNone(dialog)
		self.assertEqual(dialog.labels(), [])
		self.assertEqual(nvdaStubs.spoken, [])
		ElementsListDialog.lastSelectedElementType = 3
		self.assertEqual(self.elementsList(self.page(NEW_TAB)).labels(), ["Search"])

	def test_whenNvdaCantTell(self):
		# The assistant's look for a link fails (the page changed meanwhile): NVDA opens its list as before.
		linksList.register()
		document = self.page(NEW_TAB)
		looks = []
		iterNodesByType = document._iterNodesByType

		def lookedAt(itemType, *args, **kwargs):
			looks.append(itemType)
			if len(looks) == 1:
				raise RuntimeError("the page changed")
			return iterNodesByType(itemType, *args, **kwargs)

		with mock.patch.object(document, "_iterNodesByType", lookedAt):
			dialog = self.elementsList(document)
		self.assertEqual((looks, dialog.labels(), nvdaStubs.spoken), (["link", "link"], [], []))

	def test_aKeyPressedWhileThePageLoaded(self):
		# Version 1.18 opens the list once a loading page is ready (elementsList.withoutDocument): "no links" there too.
		linksList.register()
		document = self.page(NEW_TAB)
		focus = types.SimpleNamespace(treeInterceptor=document)
		with mock.patch.object(elementsList, "_readyDocument", lambda obj: obj.treeInterceptor), mock.patch.dict(
			sys.modules, {"api": types.SimpleNamespace(getFocusObject=lambda: focus)}
		):
			elementsList.withoutDocument(elementsList._gestures)
		self.assertEqual((made, nvdaStubs.spoken), ([], ["no links"]))

	def test_turnedOff(self):
		linksList.register()
		linksList.unregister()
		self.assertIsNotNone(self.elementsList(self.page(NEW_TAB)))
		self.assertEqual(nvdaStubs.spoken, [])


# -- activating a link from the list -------------------------------------------------------------------------------------


class ActivatingTests(ImitationNvdaTestCase):
	def followTestersSteps(self, document):
		"""The tester's steps at 15:57:14: NVDA+F7 on the page of their repositories, R to reply-to-sender-outlook, Enter;
		the link opens its page. Then Alt+Left, and NVDA+F7 again: what the list is on then."""
		dialog = self.elementsList(document)
		self.assertEqual(dialog.selected(), ("Repositories (48)", "4 of 9"), "the list starts on the link at browse mode's cursor")
		dialog.choose("reply-to-sender-outlook")
		dialog.onAction(True)
		self.assertTrue(dialog.closed)
		self.assertEqual(document.activated, ["reply-to-sender-outlook"])
		document.back()
		return self.elementsList(document).selected()

	def test_nvdaAloneComesBackOnTheLinkItWasOn(self):
		# As in the tester's log at 15:58:06: "Current page Repositories (48), 10 of 128".
		document = self.page(REPOSITORIES, at="Repositories (48)", document=WithBrowseModeCaretFix)
		self.assertEqual(self.followTestersSteps(document), ("Repositories (48)", "4 of 9"))
		self.assertEqual(document.moves, [])

	def test_comesBackOnTheLinkActivated(self):
		linksList.register()
		document = self.page(REPOSITORIES, at="Repositories (48)", document=WithBrowseModeCaretFix)
		self.assertEqual(self.followTestersSteps(document), ("reply-to-sender-outlook", "8 of 9"))
		self.assertEqual(document.moves, [OutputReason.QUICKNAV], "moved as Move to moves, once")
		self.assertEqual(nvdaStubs.spoken, [], "and nothing said of it: the page the link opens is next")

	def test_movedBeforeItIsActivated(self):
		linksList.register()
		document = self.page(REPOSITORIES, at="Repositories (48)")
		cursors = []
		activate = document._activateNVDAObject
		document._activateNVDAObject = lambda obj: (cursors.append(document.at(document.selection)), activate(obj))
		dialog = self.elementsList(document)
		dialog.choose("jawsMigrator")
		dialog.onAction(True)
		self.assertEqual(cursors, ["jawsMigrator"])

	def test_focusModeActivatesAsBefore(self):
		linksList.register()
		document = self.page(REPOSITORIES, at="Repositories (48)")
		document.passThrough = True
		dialog = self.elementsList(document)
		dialog.choose("jawsMigrator")
		dialog.onAction(True)
		self.assertEqual((document.activated, document.moves), (["jawsMigrator"], []))
		self.assertEqual(document.at(document.selection), "Repositories (48)")

	def test_moveToAsBefore(self):
		linksList.register()
		document = self.page(REPOSITORIES, at="Repositories (48)")
		reported = []
		with mock.patch.object(v117.TextInfoQuickNavItem, "report", lambda item, readUnit=None: reported.append(item.label), create=True):
			dialog = self.elementsList(document)
			dialog.choose("Projects")
			dialog.onAction(False)
			for function, args in later:
				function(*args)
		self.assertEqual((reported, document.moves, document.activated), (["Projects"], [OutputReason.QUICKNAV], []))

	def test_activatedEvenWhenTheCursorCantMove(self):
		linksList.register()
		document = self.page(REPOSITORIES, at="Repositories (48)")
		document._set_selection = mock.Mock(side_effect=RuntimeError("the page changed"))
		dialog = self.elementsList(document)
		dialog.choose("jawsMigrator")
		dialog.onAction(True)
		self.assertEqual(document.activated, ["jawsMigrator"])

	def test_turnedOff(self):
		linksList.register()
		linksList.unregister()
		document = self.page(REPOSITORIES, at="Repositories (48)", document=WithBrowseModeCaretFix)
		self.assertEqual(self.followTestersSteps(document), ("Repositories (48)", "4 of 9"))
		self.assertIs(vars(v117.TextInfoQuickNavItem)["activate"], NVDA_ACTIVATE)


# -- the item said once when NVDA fills the list again -----------------------------------------------------------------


EVENT_OBJECT_FOCUS = 0x8005
#: The winEvents NVDA 2026.2 passes on for an object, less those it drops for a tree's items (location changes, other
#: than the caret's) and "destroy", which it handles at once: focus, show, hide, selection (with add, remove and
#: within), state, name, description and value changes.
NVDA_EVENTS = {0x8005, 0x8002, 0x8003, 0x8006, 0x8007, 0x8008, 0x8009, 0x800A, 0x800C, 0x800D, 0x800E}
_WinEventProc = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
_user32 = ctypes.WinDLL("user32")
_user32.SetWinEventHook.restype = wintypes.HANDLE
_user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, _WinEventProc, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
_user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
_user32.GetFocus.restype = wintypes.HWND
_user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
_user32.TranslateMessage.argtypes = _user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]


class IAccessible:
	"""NVDA's NVDAObjects.IAccessible.IAccessible, for a focus event, as far as NVDA decides whether to take it.

	NVDA's own check (_get_shouldAllowIAccessibleFocusEvent) lets the focus event through when the object or one of its
	ancestors is focused. In NVDA the Elements List is the foreground window, so Windows says its tree is focused, and
	each focus event from the tree goes through, as the tester's log shows. Here the dialog is never shown, and Windows
	says a window is focused only in the foreground window, so the check is whether the tree has the focus of NVDA's
	thread (GetFocus). Properties find each class's value by name, as NVDA's do.
	"""

	windowClassName = "SysTreeView32"

	def __init__(self, windowHandle, IAccessibleObject, IAccessibleChildID, event_windowHandle=None, event_objectID=None, event_childID=None):
		self.windowHandle, self.IAccessibleObject, self.IAccessibleChildID = windowHandle, IAccessibleObject, IAccessibleChildID
		self.event_windowHandle, self.event_objectID, self.event_childID = event_windowHandle, event_objectID, event_childID

	processID = property(lambda self: os.getpid())

	@property
	def name(self):
		try:
			return self.IAccessibleObject.accName(self.IAccessibleChildID)
		except Exception:
			return None

	@property
	def shouldAllowIAccessibleFocusEvent(self):
		return _user32.GetFocus() == self.windowHandle


# NVDA 2026.2's IAccessible.isDuplicateIAccessibleEvent, word for word.
IAccessible.isDuplicateIAccessibleEvent = nvdaCode(
	"def isDuplicateIAccessibleEvent(self, obj):\n"
	"	\"\"\"Compaires the object of an event to self to see if the event should be treeted as duplicate.\"\"\"\n"
	"	# MSAA child elements do not have unique winEvent params as a childID could be reused if an element was deleted etc\n"
	"	if self.IAccessibleChildID > 0:\n"
	"		return False\n"
	"	return (\n"
	"		obj.event_windowHandle == self.event_windowHandle\n"
	"		and obj.event_objectID == self.event_objectID\n"
	"		and obj.event_childID == self.event_childID\n"
	"	)\n",
	"isDuplicateIAccessibleEvent",
	{},
)


class EventHandler:
	"""NVDA's eventHandler, as far as focus events are queued: what NVDA will say, in order."""

	def __init__(self):
		self.lastQueuedFocusObject = None
		self.queued = []

	def queueEvent(self, eventName, obj):
		self.queued.append(obj)
		if eventName == "gainFocus":
			self.lastQueuedFocusObject = obj


eventHandler = EventHandler()
NVDAObjects = types.SimpleNamespace(IAccessible=types.SimpleNamespace(IAccessible=IAccessible))
# NVDA 2026.2's IAccessibleHandler.processFocusNVDAEvent, word for word.
processFocusNVDAEvent = nvdaCode(
	"def processFocusNVDAEvent(obj, force=False):\n"
	"	\"\"\"Processes a focus NVDA event.\n"
	"	If the focus event is valid, it is queued.\n"
	"	@param obj: the NVDAObject the focus event is for\n"
	"	@type obj: L{NVDAObjects.NVDAObject}\n"
	"	@param force: If True, the shouldAllowIAccessibleFocusEvent property of the object is ignored.\n"
	"	@type force: boolean\n"
	"	@return: C{True} if the focus event is valid and was queued, C{False} otherwise.\n"
	"	@rtype: boolean\n"
	"	\"\"\"\n"
	"	if not force and isinstance(obj, NVDAObjects.IAccessible.IAccessible):\n"
	"		focus = eventHandler.lastQueuedFocusObject\n"
	"		if isinstance(focus, NVDAObjects.IAccessible.IAccessible) and focus.isDuplicateIAccessibleEvent(obj):\n"
	"			if isMSAADebugLoggingEnabled():\n"
	"				log.debug(f\"Dropping duplicate IAccessible focus event for {obj}\")\n"
	"			return True\n"
	"		if not obj.shouldAllowIAccessibleFocusEvent:\n"
	"			if isMSAADebugLoggingEnabled():\n"
	"				log.debug(f\"IAccessible focus event not allowed by {obj}\")\n"
	"			return False\n"
	"	eventHandler.queueEvent(\"gainFocus\", obj)\n"
	"	return True\n",
	"processFocusNVDAEvent",
	{"NVDAObjects": NVDAObjects, "eventHandler": eventHandler, "isMSAADebugLoggingEnabled": lambda: False, "log": None},
)

#: NVDA 2026.2's own initElementType and filter, as test_v117_fixes has them (the assistant's wrappers are put around
#: the dialog's own below, and taken off after each test).
NVDA_FILL = getattr(vars(v117.ElementsListDialog)["initElementType"], elementsList.ORIGINAL, vars(v117.ElementsListDialog)["initElementType"])
NVDA_FILTER = getattr(vars(v117.ElementsListDialog)["filter"], elementsList.ORIGINAL, vars(v117.ElementsListDialog)["filter"])


class RealElementsListDialog(wx.Dialog):
	"""NVDA 2026.2's browseMode.ElementsListDialog with its real tree, made as NVDA's __init__ makes it: the tree gets the
	focus, then NVDA's own initElementType fills it, before the dialog appears."""

	Element = v117.ElementsListDialog.Element
	initElementType = NVDA_FILL
	filter = NVDA_FILTER

	def __init__(self, parent, document):
		super().__init__(parent, title="Elements List")
		self.document = document
		self.tree = wx.TreeCtrl(
			self,
			size=(500, 300),
			style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT | wx.TR_SINGLE | wx.TR_EDIT_LABELS,
		)
		self.treeRoot = self.tree.AddRoot("root")
		self.filterEdit = v117.FilterEdit()
		self.activateButton, self.moveButton = v117.Button(1), v117.Button(2)
		self.tree.SetFocus()
		self.initElementType("link")


class RefilledListTests(unittest.TestCase):
	def setUp(self):
		self.app = wx.GetApp() or wx.App()
		# NVDA's own window, which its dialogs belong to (gui.mainFrame), never shown.
		self.frame = wx.Frame(None, title="NVDA")
		self.addCleanup(self.frame.Destroy)
		textInfosPackage = types.ModuleType("textInfos")
		offsets = types.ModuleType("textInfos.offsets")
		offsets.Offsets = v117.Offsets
		textInfosPackage.offsets = offsets
		virtualBuffers = types.ModuleType("virtualBuffers")
		virtualBuffers.VirtualBufferQuickNavItem = v117.VirtualBufferQuickNavItem
		browseModule = types.ModuleType("browseMode")
		browseModule.ElementsListDialog = RealElementsListDialog
		nvdaObjects = types.ModuleType("NVDAObjects")
		nvdaIAccessible = types.ModuleType("NVDAObjects.IAccessible")
		nvdaIAccessible.IAccessible = IAccessible
		nvdaObjects.IAccessible = nvdaIAccessible
		modules = {
			"textInfos": textInfosPackage,
			"textInfos.offsets": offsets,
			"virtualBuffers": virtualBuffers,
			"browseMode": browseModule,
			"NVDAObjects": nvdaObjects,
			"NVDAObjects.IAccessible": nvdaIAccessible,
			"wx": wx,
		}
		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.originals = {name: vars(owner)[name] for owner, name in self.wrapped()}
		self.addCleanup(self._restore)
		eventHandler.__init__()
		elementsList._failed = False
		elementsList._goneItem = None
		self.winEvents = []
		self._callback = _WinEventProc(lambda hook, event, window, objectID, childID, thread, at: self.winEvents.append((event, window, objectID, childID)))
		self.hook = _user32.SetWinEventHook(1, 0x7FFFFFFF, None, self._callback, os.getpid(), 0, 0)
		self.addCleanup(_user32.UnhookWinEvent, self.hook)

	@staticmethod
	def wrapped():
		return (
			(v117.VirtualBufferQuickNavItem, "label"),
			(v117.VirtualBufferQuickNavItem, "isChild"),
			(RealElementsListDialog, "initElementType"),
			(RealElementsListDialog, "filter"),
		)

	def _restore(self):
		elementsList.unregister()
		elementsList._replaced.clear()
		elementsList._failed = False
		elementsList._goneItem = None
		for owner, name in self.wrapped():
			setattr(owner, name, self.originals[name])

	def pumpWinEvents(self):
		"""Windows gives NVDA's winEvent hook its events as NVDA's main thread takes its messages, after the list is filled."""
		message = wintypes.MSG()
		end = time.monotonic() + 0.3
		while time.monotonic() < end:
			while _user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
				_user32.TranslateMessage(ctypes.byref(message))
				_user32.DispatchMessageW(ctypes.byref(message))
			time.sleep(0.01)

	def processFocusWinEvent(self, window, objectID, childID, chooseOverlay):
		"""NVDA's processFocusWinEvent: NVDA's object for the event (winEventToNVDAEvent), with the classes the assistant
		chooses for it first (NVDAObjects.DynamicNVDAObjectType), then processFocusNVDAEvent."""
		obj = IAccessible(window, v119._msaa(window), childID, event_windowHandle=window, event_objectID=objectID, event_childID=childID)
		clsList = [IAccessible]
		if chooseOverlay:
			chooseOverlay(obj, clsList)
		obj.__class__ = type("DynamicIAccessible", tuple(clsList), {})
		return processFocusNVDAEvent(obj)

	def said(self, tree, chooseOverlay=None):
		"""The items of ``tree`` NVDA takes a focus event for, in order.

		NVDA 2026.2 hooks the kinds of winEvent it has a name for (internalWinEventHandler.winEventIDsToNVDAEventNames),
		handles "destroy" at once, and keeps the newest four focus events of a cycle (OrderedWinEventLimiter,
		maxFocusItems=4). Then IAccessibleHandler.pumpAll takes, of focus events one after another, the newest one
		processFocusWinEvent takes; any other event, as the selection event Windows fires with each focus, ends the run.
		"""
		handle = tree.GetHandle()
		events = [event for event in self.winEvents if event[1] == handle and event[0] in NVDA_EVENTS]
		focusEvents = [index for index, event in enumerate(events) if event[0] == EVENT_OBJECT_FOCUS]
		events = [event for index, event in enumerate(events) if event[0] != EVENT_OBJECT_FOCUS or index in focusEvents[-4:]]
		focusWinEvents = []
		for winEvent in events + [(0, handle, 0, 0)]:
			if winEvent[0] == EVENT_OBJECT_FOCUS:
				focusWinEvents.append(winEvent)
				continue
			for focusWinEvent in reversed(focusWinEvents):
				if self.processFocusWinEvent(*focusWinEvent[1:], chooseOverlay):
					break
			focusWinEvents = []
		return [(obj.event_childID, obj.name) for obj in eventHandler.queued if obj.event_childID]

	def openTestersList(self):
		"""NVDA+F7 on the tester's page as GitHub puts its alert above the links (15:56:04): NVDA fills its list, the page
		changes, and the assistant has NVDA fill it again."""
		page = v117.Page(REPOSITORIES)
		v117.NVDAHelper.localLib = v117.LocalLib(page)
		document = v117.Document(page)
		document.meanwhile.append(v117.alertAbove)
		elementsList.register()
		fills = []
		fill = RealElementsListDialog.filter
		with mock.patch.object(RealElementsListDialog, "filter", lambda dialog, *args, **kwargs: (fills.append(args), fill(dialog, *args, **kwargs))[1]):
			dialog = RealElementsListDialog(self.frame, document)
		self.addCleanup(dialog.Destroy)
		self.assertEqual(len(fills), 2, "filled again, as the page changed")
		self.pumpWinEvents()
		return dialog

	def test_version119SaidTheItemFourTimes(self):
		# As in the tester's log at 15:56:05: three items of the first list, gone by then, and the item of the second.
		dialog = self.openTestersList()
		said = self.said(dialog.tree)
		self.assertEqual([name for childID, name in said], [None, None, None, "Skip to content"], "Windows no longer knows the first three")
		live = dialog.tree.GetSelection()
		self.assertEqual(said[-1][0], elementsList._sendMessage(dialog.tree.GetHandle(), elementsList.TVM_MAPHTREEITEMTOACCID, int(live.GetID())))

	def test_saidOnce(self):
		dialog = self.openTestersList()
		selected = dialog.tree.GetSelection()
		self.assertEqual(dialog.tree.GetItemText(selected), "Skip to content")
		said = self.said(dialog.tree, elementsList.chooseOverlay)
		self.assertEqual([name for childID, name in said], ["Skip to content"])

	def test_arrowingInTheListAsBefore(self):
		dialog = self.openTestersList()
		self.said(dialog.tree, elementsList.chooseOverlay)
		self.winEvents.clear()
		first = dialog.tree.GetSelection()
		dialog.tree.SelectItem(dialog.tree.GetNextSibling(first))
		self.pumpWinEvents()
		self.assertEqual([name for childID, name in self.said(dialog.tree, elementsList.chooseOverlay)][-1:], ["Homepage"])

	def test_otherTreeViewsAsBefore(self):
		elementsList.register()
		other = wx.Dialog(self.frame, title="Not the Elements List")
		self.addCleanup(other.Destroy)
		tree = wx.TreeCtrl(other, style=wx.TR_HIDE_ROOT)
		root = tree.AddRoot("root")
		tree.SetFocus()
		for labels in (["Ethernet"], ["Wi-Fi", "Bluetooth"]):
			tree.DeleteChildren(root)
			items = [tree.AppendItem(root, label) for label in labels]
			tree.SelectItem(items[0])
		self.pumpWinEvents()
		said = self.said(tree, elementsList.chooseOverlay)
		self.assertEqual([name for childID, name in said][-1:], ["Wi-Fi"])
		self.assertGreater(len(said), 1, "a tree that isn't the Elements List keeps each focus event")

	def test_itemsAllGone(self):
		# Nothing selected: NVDA says what it can, as before.
		elementsList.register()
		dialog = self.openTestersList()
		dialog.tree.DeleteChildren(dialog.treeRoot)
		self.assertFalse(elementsList.isGoneItem(dialog.tree.GetHandle(), 1))

	def test_onlyOnNvdasMainThread(self):
		dialog = self.openTestersList()
		clsLists = []

		def choose():
			clsList = [IAccessible]
			elementsList.chooseOverlay(IAccessible(dialog.tree.GetHandle(), None, 1, event_childID=1), clsList)
			clsLists.append(clsList)

		thread = threading.Thread(target=choose)
		thread.start()
		thread.join()
		self.assertEqual(clsLists, [[IAccessible]], "wx is for NVDA's main thread only")

	def test_turnedOff(self):
		dialog = self.openTestersList()
		elementsList.unregister()
		self.assertEqual(len(self.said(dialog.tree, elementsList.chooseOverlay)), 4)


if __name__ == "__main__":
	unittest.main()
