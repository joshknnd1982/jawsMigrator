# Unit tests for version 1.19, from a tester's answers to questions about version 1.18 (issue 11):
# - linksList: the tester pasted what JAWS's Links List (Insert+F7) says on a github.com release page: "Skip to content,
#   1 of 34", "Homepage ( g then d ), 2 of 34", "Current Page Code, 10 of 34", "joshknnd1982 Alt+ArrowUp, 19 of 34".
#   In the tester's log NVDA's Elements List (NVDA+F7) said "Skip to content; same page, 1 of 50, level 0" and
#   "Homepage ( g then d ); visited, 2 of 50, level 0". A link is now labelled as JAWS labels it, and a list where no
#   item is under another has no "level 0".
# - typingWatch: typing in Windows 11's Notepad with NVDA's log open, the tester heard nothing, and letters and spaces
#   went missing from the text. NVDA's debug log now says which keys the program typed late or never, and where NVDA's
#   main thread was meanwhile.
# The labels come from NVDA 2026.2's own browseMode.TextInfoQuickNavItem._getLabelForProperties, word for word, on
# test_v117_fixes' imitation NVDA (NVDA 2026.2's initElementType, filter, VirtualBufferQuickNavItem and
# VirtualBufferTextInfo, word for word). Only controlTypes.processAndLabelStates is imitated, for what these pages have:
# NVDA keeps visited and same page for a link only, and labels each state in its own words. The level is read by NVDA
# 2026.2's own TreeViewItem._get_treeview_hItem, _get_treeview_level and _get_positionInfo
# (NVDAObjects/IAccessible/sysTreeView32.py), word for word, from a real Windows tree view made as NVDA makes its
# Elements List's (a wx.TreeCtrl with its root hidden), through Windows' MSAA, as NVDA reads it: Windows gives the top
# of such a tree the value 0. What NVDA says of it is NVDA 2026.2's own code from getObjectSpeech and
# getPropertiesSpeech (speech/speech.py), word for word. The keys and typed characters are those of the tester's log
# of 25 September, 10:38:35 to 10:38:52, where Notepad typed "meg" for "message". The assistant's code is the real one.
# Run: python -m unittest tests.test_v119_fixes -v

import collections
import ctypes
import enum
import logging
import os
import sys
import threading
import types
import unittest
from ctypes import wintypes
from typing import Any, Callable
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import wx  # noqa: E402

import test_v117_fixes as v117  # noqa: E402
from jawsMigrator import elementsList, linksList, typingWatch  # noqa: E402

#: What JAWS's Links List said on the page, as the tester pasted it (the first eight links, and two further on).
JAWS_SAID = [
	"Skip to content",
	"Homepage ( g then d )",
	"joshknnd1982",
	"jawsEloquenceTyping",
	"Current Page Code",
	"Issues",
	"joshknnd1982 Alt+ArrowUp",
	"Commit f9aba63 Alt+ArrowUp",
]


class Labelled(enum.Enum):
	@property
	def displayString(self):
		return self.value


class Role(Labelled):
	"""NVDA's controlTypes.Role, as far as these pages go, in NVDA's words."""

	LINK = "link"
	BUTTON = "button"
	TOGGLEBUTTON = "toggle button"
	DROPDOWNBUTTON = "drop down button"
	SPLITBUTTON = "split button"
	MENUBUTTON = "menu button"
	DROPDOWNBUTTONGRID = "drop down button grid"
	TREEVIEWBUTTON = "tree view button"
	EDITABLETEXT = "edit"
	HEADING = "heading"
	TREEVIEWITEM = "tree view item"
	LISTITEM = "list item"


class State(Labelled):
	"""NVDA's controlTypes.State, as far as these pages go, in NVDA's words."""

	VISITED = "visited"
	INTERNAL_LINK = "same page"
	PRESSED = "pressed"


class IsCurrent(enum.Enum):
	"""NVDA's controlTypes.IsCurrent, with its words (controlTypes/isCurrent.py)."""

	NO = "false"
	YES = "true"
	PAGE = "page"
	STEP = "step"

	@property
	def displayString(self):
		return {"false": "", "true": "current", "page": "current page", "step": "current step"}[self.value]


def processAndLabelStates(role, states, reason):
	"""NVDA's controlTypes.processAndLabelStates, imitated for these pages: visited and same page are a link's only."""
	states = set(states or ())
	if role != Role.LINK:
		states.discard(State.VISITED)
		states.discard(State.INTERNAL_LINK)
	return [state.displayString for state in sorted(states, key=lambda state: state.value)]


controlTypes = types.ModuleType("controlTypes")
controlTypes.Role, controlTypes.State, controlTypes.IsCurrent = Role, State, IsCurrent
controlTypes.processAndLabelStates = processAndLabelStates
OutputReason = types.SimpleNamespace(FOCUS="focus")
aria = types.SimpleNamespace(landmarkRoles={"main": "main"})


def _(text):
	return text


def nvdaCode(source, name, namespace):
	"""Compile NVDA's own ``source`` in ``namespace``, and give back ``name`` from it."""
	namespace = dict(namespace)
	exec(source, namespace)
	return namespace[name]


# NVDA 2026.2's browseMode.TextInfoQuickNavItem._getLabelForProperties, word for word.
NVDA_GET_LABEL = nvdaCode(
	"def _getLabelForProperties(self, labelPropertyGetter: Callable[[str], Any]):\n"
	"\t\"\"\"\n"
	"\tFetches required properties for this L{TextInfoQuickNavItem} and constructs a label to be shown in an elements list.\n"
	"\tThis can be used by subclasses to implement the L{label} property.\n"
	"\t@Param labelPropertyGetter: A callable taking 1 argument, specifying the property to fetch.\n"
	"\t\tFor example, if L{itemType} is landmark, the callable must return the landmark type when \"landmark\" is passed as the property argument.\n"
	"\t\tAlternative property names might be name or value.\n"
	"\t\tThe callable must return None if the property doesn't exist.\n"
	"\t\tAn expected callable might be get method on a L{Dict},\n"
	"\t\tor \"lambda property: getattr(self.obj, property, None)\" for an L{NVDAObject}.\n"
	"\t\"\"\"\n"
	"\tcontent = self.textInfo.text.strip()\n"
	"\tif self.itemType == \"heading\":\n"
	"\t\t# Output: displayed text of the heading.\n"
	"\t\treturn content\n"
	"\tlabelParts = None\n"
	"\tname = labelPropertyGetter(\"name\")\n"
	"\tif self.itemType == \"landmark\":\n"
	"\t\tlandmark = aria.landmarkRoles.get(labelPropertyGetter(\"landmark\"))\n"
	"\t\t# Example output: main menu; navigation\n"
	"\t\tlabelParts = (name, landmark)\n"
	"\telse:\n"
	"\t\trole: controlTypes.Role | int = labelPropertyGetter(\"role\")\n"
	"\t\trole = controlTypes.Role(role)\n"
	"\t\troleText = role.displayString\n"
	"\t\t# Translators: Reported label in the elements list for an element which which has no name and value\n"
	"\t\tunlabeled = _(\"Unlabeled\")\n"
	"\t\trealStates = labelPropertyGetter(\"states\")\n"
	"\t\tlabeledStates = \" \".join(controlTypes.processAndLabelStates(role, realStates, OutputReason.FOCUS))\n"
	"\t\tif self.itemType == \"formField\":\n"
	"\t\t\tif role in (\n"
	"\t\t\t\tcontrolTypes.Role.BUTTON,\n"
	"\t\t\t\tcontrolTypes.Role.DROPDOWNBUTTON,\n"
	"\t\t\t\tcontrolTypes.Role.TOGGLEBUTTON,\n"
	"\t\t\t\tcontrolTypes.Role.SPLITBUTTON,\n"
	"\t\t\t\tcontrolTypes.Role.MENUBUTTON,\n"
	"\t\t\t\tcontrolTypes.Role.DROPDOWNBUTTONGRID,\n"
	"\t\t\t\tcontrolTypes.Role.TREEVIEWBUTTON,\n"
	"\t\t\t):\n"
	"\t\t\t\t# Example output: Mute; toggle button; pressed\n"
	"\t\t\t\tlabelParts = (content or name or unlabeled, roleText, labeledStates)\n"
	"\t\t\telse:\n"
	"\t\t\t\t# Example output: Find a repository...; edit; has auto complete; NVDA\n"
	"\t\t\t\tlabelParts = (name or unlabeled, roleText, labeledStates, content)\n"
	"\t\telif self.itemType in (\"link\", \"button\"):\n"
	"\t\t\t# Example output: You have unread notifications; visited\n"
	"\t\t\tlabelParts = (content or name or unlabeled, labeledStates)\n"
	"\tif labelParts:\n"
	"\t\tlabel = \"; \".join(lp for lp in labelParts if lp)\n"
	"\telse:\n"
	"\t\tlabel = content\n"
	"\treturn label",
	"_getLabelForProperties",
	{"controlTypes": controlTypes, "OutputReason": OutputReason, "aria": aria, "_": _, "Callable": Callable, "Any": Any},
)


class Link(v117.Element):
	"""A link (or other element) of the page, with what NVDA's copy of a page has for it besides its name and states."""

	def __init__(self, identifier, text, states=(), current=None, shortcut=None, role=Role.LINK, itemType="link"):
		super().__init__(identifier, itemType, text, states=states)
		self.role, self.current, self.shortcut = role, current, shortcut

	def attributes(self):
		attrs = super().attributes()
		attrs["role"] = self.role
		# NVDA's virtual buffer has a keyboardShortcut for every node, empty without one (gecko_ia2.cpp), and "current"
		# only where the page marks the node as current (virtualBuffers/gecko_ia2.py, _getNormalizedCurrentAttrs).
		attrs["keyboardShortcut"] = self.shortcut or ""
		if self.current is not None:
			attrs["current"] = self.current
		return attrs


#: The tester's page, the release page of jawsEloquenceTyping 2.5.2 on github.com, as far as the tester pasted it.
RELEASE_PAGE = [
	Link(1, "Skip to content", states={State.INTERNAL_LINK}),
	Link(2, "Homepage ( g then d )", states={State.VISITED}),
	Link(3, "joshknnd1982", states={State.VISITED}),
	Link(4, "jawsEloquenceTyping", states={State.VISITED}),
	Link(10, "Code", current=IsCurrent.PAGE),
	Link(11, "Issues"),
	Link(19, "joshknnd1982", states={State.VISITED}, shortcut="Alt+ArrowUp"),
	Link(21, "Commit f9aba63", shortcut="Alt+ArrowUp"),
	Link(30, "Mute", states={State.PRESSED}, role=Role.TOGGLEBUTTON, itemType="button"),
]
#: What NVDA 2026.2 labels them, as in the tester's log ("Homepage ( g then d ); visited").
NVDA_SAID = [
	"Skip to content; same page",
	"Homepage ( g then d ); visited",
	"joshknnd1982; visited",
	"jawsEloquenceTyping; visited",
	"Code",
	"Issues",
	"joshknnd1982; visited",
	"Commit f9aba63",
]


class LinksTestCase(v117.ImitationNvdaTestCase):
	def setUp(self):
		super().setUp()
		self.page.elements[:] = RELEASE_PAGE + v117.HEADINGS
		quickNavItem = v117.TextInfoQuickNavItem
		shorter = vars(quickNavItem)["_getLabelForProperties"]
		quickNavItem._getLabelForProperties = NVDA_GET_LABEL
		self.addCleanup(setattr, quickNavItem, "_getLabelForProperties", shorter)
		sys.modules["browseMode"].TextInfoQuickNavItem = quickNavItem
		patcher = mock.patch.dict(sys.modules, {"controlTypes": controlTypes})
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(self._restoreLinks)
		linksList._failed = False

	def _restoreLinks(self):
		linksList.unregister()
		linksList._replaced.clear()
		linksList._failed = False


class LinksAsInJawsTests(LinksTestCase):
	def test_nvdaAlone(self):
		# As in the tester's log: the states after the text, no "current page", no shortcut key.
		self.assertEqual(self.openList().labels(), NVDA_SAID)

	def test_asJawssLinksList(self):
		linksList.register()
		labels = self.openList().labels()
		self.assertEqual(labels, ["Skip to content", "Homepage ( g then d )", "joshknnd1982", "jawsEloquenceTyping", "Current page Code", "Issues", "joshknnd1982 Alt+ArrowUp", "Commit f9aba63 Alt+ArrowUp"])
		self.assertEqual([label.lower() for label in labels], [label.lower() for label in JAWS_SAID], "the words JAWS says")

	def test_buttonsAndHeadingsKeepNvdasLabels(self):
		linksList.register()
		self.assertEqual(self.openList("button").labels(), ["Mute; pressed"])
		self.assertEqual(self.openList("heading").labels(), ["jawsMigrator", "What's new in 1.15", "Using the assistant", "Choosing what to import"])

	def test_theFilterBoxFindsWhatTheListShows(self):
		linksList.register()
		dialog = self.openList()
		dialog.filter("alt")
		self.assertEqual(dialog.labels(), ["joshknnd1982 Alt+ArrowUp", "Commit f9aba63 Alt+ArrowUp"])
		dialog.filter("current")
		self.assertEqual(dialog.labels(), ["Current page Code"])
		dialog.filter("visited")
		self.assertEqual(dialog.labels(), [], "visited isn't in the list any more")

	def test_aLinkThePageTookAway(self):
		# With 1.18's Elements List: a link gone before its label is read is still left out.
		elementsList.register()
		linksList.register()
		self.document.meanwhile.append(v117.takeAway(3))
		self.assertEqual(self.openList().labels(), ["Skip to content", "Homepage ( g then d )", "jawsEloquenceTyping", "Current page Code", "Issues", "joshknnd1982 Alt+ArrowUp", "Commit f9aba63 Alt+ArrowUp"])

	def test_turnedOff(self):
		linksList.register()
		self.assertTrue(linksList._isOurs(vars(v117.TextInfoQuickNavItem)["_getLabelForProperties"]))
		linksList.unregister()
		self.assertIs(vars(v117.TextInfoQuickNavItem)["_getLabelForProperties"], NVDA_GET_LABEL)
		self.assertEqual(self.openList().labels(), NVDA_SAID)

	def test_anotherAddOnsWrapperOverTheAssistants(self):
		import functools

		linksList.register()
		ours = vars(v117.TextInfoQuickNavItem)["_getLabelForProperties"]

		@functools.wraps(ours)
		def theirs(self, getter):
			return ours(self, getter)

		v117.TextInfoQuickNavItem._getLabelForProperties = theirs
		linksList.unregister()
		self.assertIs(vars(v117.TextInfoQuickNavItem)["_getLabelForProperties"], theirs, "another add-on's own stays")
		linksList.register()
		self.assertIs(vars(v117.TextInfoQuickNavItem)["_getLabelForProperties"], theirs, "and nothing is wrapped twice")
		self.assertEqual(self.openList().labels()[4], "Current page Code")

	def test_whatThePageMarksALinkAs(self):
		self.assertEqual(linksList.jawsLabel("Code", IsCurrent.PAGE, ""), "Current page Code")
		self.assertEqual(linksList.jawsLabel("Shipping", IsCurrent.STEP, None), "Current step Shipping")
		self.assertEqual(linksList.jawsLabel("Code", IsCurrent.NO, ""), "Code")
		self.assertEqual(linksList.jawsLabel("Code", None, " Alt+ArrowUp "), "Code Alt+ArrowUp")
		self.assertEqual(linksList.jawsLabel("Code", "false", ""), "Code", "an attribute NVDA didn't make its own")


# -- "level 0" ------------------------------------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32")
user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SendMessageW.restype = wintypes.LPARAM
#: NVDA's watchdog, as far as a tree view item uses it: a message to the tree view, answered by Windows.
watchdog = types.SimpleNamespace(cancellableSendMessage=lambda hwnd, msg, wParam, lParam: user32.SendMessageW(hwnd, msg, wParam, lParam))
# NVDA 2026.2's constants for tree views (NVDAObjects/IAccessible/sysTreeView32.py).
TV_FIRST = 0x1100
TVGN_ROOT = 0
TVGN_CHILD = 4
TREE_VIEW = {
	"watchdog": watchdog,
	"TVM_MAPACCIDTOHTREEITEM": TV_FIRST + 42,
	"TVM_GETNEXTITEM": TV_FIRST + 10,
	"TVGN_NEXT": 1,
	"TVGN_PREVIOUS": 2,
}


class IAccessible:
	"""NVDA's NVDAObjects.IAccessible.IAccessible, as far as a tree view item uses it.

	NVDA makes a property of each _get_ method (baseObject.AutoPropertyType); here the properties find them by name,
	so that a class NVDA makes from the classes chosen for an object (overlay classes first) finds the first one.
	"""

	windowClassName = "SysTreeView32"

	def __init__(self, windowHandle, IAccessibleObject, IAccessibleChildID):
		self.windowHandle, self.IAccessibleObject, self.IAccessibleChildID = windowHandle, IAccessibleObject, IAccessibleChildID

	processID = property(lambda self: os.getpid())
	positionInfo = property(lambda self: self._get_positionInfo())
	treeview_hItem = property(lambda self: self._get_treeview_hItem())
	treeview_level = property(lambda self: self._get_treeview_level())

	def _get_positionInfo(self):
		return {}


# NVDA 2026.2's TreeViewItem._get_treeview_hItem, _get_treeview_level and _get_positionInfo, word for word.
TreeViewItem = type("TreeViewItem", (IAccessible,), {})
TREE_VIEW["TreeViewItem"] = TreeViewItem
for _name, _source in (
	(
		"_get_treeview_hItem",
		"def _get_treeview_hItem(self):\n"
		"\tif not hasattr(self, \"_treeview_hItem\"):\n"
		"\t\tself._treeview_hItem = watchdog.cancellableSendMessage(\n"
		"\t\t\tself.windowHandle,\n"
		"\t\t\tTVM_MAPACCIDTOHTREEITEM,\n"
		"\t\t\tself.IAccessibleChildID,\n"
		"\t\t\t0,\n"
		"\t\t)\n"
		"\t\tif not self._treeview_hItem:\n"
		"\t\t\t# Tree views from comctl < 6.0 use the hItem as the child ID.\n"
		"\t\t\tself._treeview_hItem = self.IAccessibleChildID\n"
		"\treturn self._treeview_hItem",
	),
	(
		"_get_treeview_level",
		"def _get_treeview_level(self):\n"
		"\treturn int(self.IAccessibleObject.accValue(self.IAccessibleChildID))",
	),
	(
		"_get_positionInfo",
		"def _get_positionInfo(self):\n"
		"\tif self.IAccessibleChildID == 0:\n"
		"\t\treturn super(TreeViewItem, self)._get_positionInfo()\n"
		"\tinfo = {}\n"
		"\tinfo[\"level\"] = self.treeview_level\n"
		"\thItem = self.treeview_hItem\n"
		"\tif not hItem:\n"
		"\t\treturn info\n"
		"\tnewItem = hItem\n"
		"\tindex = 0\n"
		"\twhile newItem > 0:\n"
		"\t\tindex += 1\n"
		"\t\tnewItem = watchdog.cancellableSendMessage(\n"
		"\t\t\tself.windowHandle,\n"
		"\t\t\tTVM_GETNEXTITEM,\n"
		"\t\t\tTVGN_PREVIOUS,\n"
		"\t\t\tnewItem,\n"
		"\t\t)\n"
		"\tnewItem = hItem\n"
		"\tnumItems = index - 1\n"
		"\twhile newItem > 0:\n"
		"\t\tnumItems += 1\n"
		"\t\tnewItem = watchdog.cancellableSendMessage(self.windowHandle, TVM_GETNEXTITEM, TVGN_NEXT, newItem)\n"
		"\tinfo[\"indexInGroup\"] = index\n"
		"\tinfo[\"similarItemsInGroup\"] = numItems\n"
		"\treturn info",
	),
):
	setattr(TreeViewItem, _name, nvdaCode(_source, _name, TREE_VIEW))

#: NVDA's speech state: the level of the tree view item it spoke last.
_speechState = types.SimpleNamespace(oldTreeLevel=None)
#: What NVDA says, and where: NVDA 2026.2's getObjectSpeech (its positionInfo) and getPropertiesSpeech (its words),
#: word for word from "if positionInfo:" and from "indexInGroup = ", for a tree view item it speaks as the focus.
spokenPosition = nvdaCode(
	"def spokenPosition(obj, role):\n"
	"\tallowedProperties = {\"positionInfo_level\": True, \"positionInfo_indexInGroup\": True, \"positionInfo_similarItemsInGroup\": True}\n"
	"\tnewPropertyValues = {\"role\": role}\n"
	"\tpositionInfo = obj.positionInfo\n"
	"\tif positionInfo:\n"
	"\t\tif allowedProperties.get(\"positionInfo_level\", False) and \"level\" in positionInfo:\n"
	"\t\t\tnewPropertyValues[\"positionInfo_level\"] = positionInfo[\"level\"]\n"
	"\t\tif allowedProperties.get(\"positionInfo_indexInGroup\", False) and \"indexInGroup\" in positionInfo:\n"
	"\t\t\tnewPropertyValues[\"positionInfo_indexInGroup\"] = positionInfo[\"indexInGroup\"]\n"
	"\t\tif (\n"
	"\t\t\tallowedProperties.get(\"positionInfo_similarItemsInGroup\", False)\n"
	"\t\t\tand \"similarItemsInGroup\" in positionInfo\n"
	"\t\t):\n"
	"\t\t\tnewPropertyValues[\"positionInfo_similarItemsInGroup\"] = positionInfo[\"similarItemsInGroup\"]\n"
	"\tpropertyValues = newPropertyValues\n"
	"\ttextList = []\n"
	"\tindexInGroup = propertyValues.get(\"positionInfo_indexInGroup\", 0)\n"
	"\tsimilarItemsInGroup = propertyValues.get(\"positionInfo_similarItemsInGroup\", 0)\n"
	"\tif 0 < indexInGroup <= similarItemsInGroup:\n"
	"\t\t# Translators: Spoken to indicate the position of an item in a group of items (such as a list).\n"
	"\t\t# {number} is replaced with the number of the item in the group.\n"
	"\t\t# {total} is replaced with the total number of items in the group.\n"
	"\t\titemPosTranslation: str = _(\"{number} of {total}\").format(\n"
	"\t\t\tnumber=indexInGroup,\n"
	"\t\t\ttotal=similarItemsInGroup,\n"
	"\t\t)\n"
	"\t\ttextList.append(itemPosTranslation)\n"
	"\tif \"positionInfo_level\" in propertyValues:\n"
	"\t\tlevel = propertyValues.get(\"positionInfo_level\", None)\n"
	"\t\trole = propertyValues.get(\"role\", None)\n"
	"\t\tif level is not None:\n"
	"\t\t\t# Translators: Speaks the item level in treeviews (example output: level 2).\n"
	"\t\t\tlevelTranslation: str = _(\"level %s\") % level\n"
	"\t\t\tif (\n"
	"\t\t\t\trole in (controlTypes.Role.TREEVIEWITEM, controlTypes.Role.LISTITEM)\n"
	"\t\t\t\tand level != _speechState.oldTreeLevel\n"
	"\t\t\t):\n"
	"\t\t\t\ttextList.insert(0, levelTranslation)\n"
	"\t\t\t\t_speechState.oldTreeLevel = level\n"
	"\t\t\telse:\n"
	"\t\t\t\ttextList.append(levelTranslation)\n"
	"\treturn textList\n",
	"spokenPosition",
	{"_": _, "controlTypes": controlTypes, "_speechState": _speechState},
)


class ElementsListDialog(wx.Dialog):
	"""NVDA's browseMode.ElementsListDialog, as far as its tree goes, made as NVDA 2026.2 makes it."""

	def __init__(self):
		super().__init__(None, title="Elements List")
		self.tree = wx.TreeCtrl(
			self,
			size=(500, 300),
			style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT | wx.TR_SINGLE | wx.TR_EDIT_LABELS,
		)
		self.treeRoot = self.tree.AddRoot("root")


def _msaa(windowHandle):
	"""Windows' IAccessible for the window's client area, as NVDA gets it."""
	import comtypes.client

	comtypes.client.GetModule("oleacc.dll")
	from comtypes.gen.Accessibility import IAccessible as MSAA

	pointer = ctypes.POINTER(MSAA)()
	ctypes.oledll.oleacc.AccessibleObjectFromWindow(windowHandle, -4, ctypes.byref(MSAA._iid_), ctypes.byref(pointer))
	return pointer


class LevelTests(unittest.TestCase):
	def setUp(self):
		self.app = wx.GetApp() or wx.App()
		self.dialogs = []
		browseModule = types.ModuleType("browseMode")
		browseModule.ElementsListDialog = ElementsListDialog
		browseModule.TextInfoQuickNavItem = v117.TextInfoQuickNavItem
		sysTreeView32 = types.ModuleType("NVDAObjects.IAccessible.sysTreeView32")
		sysTreeView32.TreeViewItem = TreeViewItem
		modules = {
			"browseMode": browseModule,
			"controlTypes": controlTypes,
			"NVDAObjects": types.ModuleType("NVDAObjects"),
			"NVDAObjects.IAccessible": types.ModuleType("NVDAObjects.IAccessible"),
			"NVDAObjects.IAccessible.sysTreeView32": sysTreeView32,
		}
		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		linksList._overlay = None
		linksList._failed = False
		_speechState.oldTreeLevel = None
		self.addCleanup(self._restore)

	def _restore(self):
		linksList.unregister()
		linksList._replaced.clear()
		linksList._overlay = None
		for dialog in self.dialogs:
			dialog.Destroy()

	def elementsList(self, labels, nested=()):
		"""An Elements List holding ``labels``, those in ``nested`` under the one before them."""
		dialog = ElementsListDialog()
		self.dialogs.append(dialog)
		parent = None
		for label in labels:
			under = parent if label in nested and parent is not None else dialog.treeRoot
			item = dialog.tree.AppendItem(under, label)
			if label not in nested:
				parent = item
		dialog.tree.ExpandAll()
		return dialog

	def items(self, dialog):
		"""NVDA's objects for the tree's items, in order: NVDA makes each one's class from the classes chosen for it,
		the assistant's first. Each item's MSAA child ID is the one Windows maps it to, as NVDA's navigation finds it."""
		handle = dialog.tree.GetHandle()
		msaa = _msaa(handle)
		send = watchdog.cancellableSendMessage
		objects = []
		pending = [send(handle, TV_FIRST + 10, TVGN_ROOT, 0)]
		while pending:
			hItem = pending.pop()
			if hItem <= 0:
				continue
			childID = send(handle, TV_FIRST + 43, hItem, 0)
			obj = IAccessible(handle, msaa, childID)
			clsList = [TreeViewItem, IAccessible]
			linksList.chooseOverlay(obj, clsList)
			objects.append(clsList[0](handle, msaa, childID))
			# The next item, then the first under this one, which comes first.
			pending.append(send(handle, TV_FIRST + 10, TREE_VIEW["TVGN_NEXT"], hItem))
			pending.append(send(handle, TV_FIRST + 10, TVGN_CHILD, hItem))
		return objects

	def test_windowsNumbersTheTopOfTheList0(self):
		# NVDA alone, as in the tester's log: every link at level 0.
		dialog = self.elementsList(["Skip to content", "Homepage ( g then d )", "joshknnd1982"])
		items = self.items(dialog)
		self.assertEqual([item.positionInfo for item in items], [{"level": 0, "indexInGroup": index, "similarItemsInGroup": 3} for index in (1, 2, 3)])
		self.assertEqual(spokenPosition(items[0], Role.TREEVIEWITEM), ["level 0", "1 of 3"])
		self.assertEqual(spokenPosition(items[1], Role.TREEVIEWITEM), ["2 of 3", "level 0"])

	def test_noLevelWhereNoItemIsUnderAnother(self):
		linksList.register()
		dialog = self.elementsList(["Skip to content", "Homepage ( g then d )", "joshknnd1982"])
		items = self.items(dialog)
		self.assertTrue(all(isinstance(item, linksList.overlayClass()) for item in items))
		self.assertEqual(items[1].positionInfo, {"indexInGroup": 2, "similarItemsInGroup": 3})
		self.assertEqual(spokenPosition(items[0], Role.TREEVIEWITEM), ["1 of 3"])
		self.assertEqual(spokenPosition(items[1], Role.TREEVIEWITEM), ["2 of 3"])

	def test_levelsStayWhereHeadingsAreUnderOthers(self):
		linksList.register()
		dialog = self.elementsList(["jawsMigrator", "What's new in 1.15", "Using the assistant"], nested=("What's new in 1.15", "Using the assistant"))
		items = self.items(dialog)
		self.assertEqual([item.positionInfo["level"] for item in items], [0, 1, 1])

	def test_aFilterThatLeavesEveryItemAtTheTop(self):
		# NVDA's filter puts an item whose parent it leaves out at the top of the list.
		linksList.register()
		dialog = self.elementsList(["jawsMigrator", "What's new in 1.15"], nested=("What's new in 1.15",))
		dialog.tree.DeleteChildren(dialog.treeRoot)
		dialog.tree.AppendItem(dialog.treeRoot, "What's new in 1.15")
		self.assertNotIn("level", self.items(dialog)[0].positionInfo)

	def test_otherTreeViewsKeepTheirLevels(self):
		linksList.register()
		frame = wx.Dialog(None, title="Not the Elements List")
		self.dialogs.append(frame)
		tree = wx.TreeCtrl(frame, style=wx.TR_HIDE_ROOT)
		tree.AppendItem(tree.AddRoot("root"), "Ethernet")
		obj = IAccessible(tree.GetHandle(), _msaa(tree.GetHandle()), 1)
		clsList = [TreeViewItem, IAccessible]
		linksList.chooseOverlay(obj, clsList)
		self.assertEqual(clsList, [TreeViewItem, IAccessible])
		clsList = [IAccessible]
		dialog = self.elementsList(["Skip to content"])
		linksList.chooseOverlay(IAccessible(dialog.tree.GetHandle(), None, 1), clsList)
		self.assertEqual(clsList, [IAccessible], "only a tree view item gets the assistant's class")

	def test_turnedOff(self):
		linksList.register()
		items = self.items(self.elementsList(["Skip to content", "Homepage ( g then d )"]))
		linksList.unregister()
		self.assertEqual(items[0].positionInfo["level"], 0, "an item made before says its level again")
		self.assertEqual(self.items(self.elementsList(["Issues"]))[0].__class__, TreeViewItem)

	def test_onlyOnNvdasMainThread(self):
		linksList.register()
		dialog = self.elementsList(["Skip to content"])
		answers = []
		thread = threading.Thread(target=lambda: answers.append(linksList.levelSaysNothing(dialog.tree.GetHandle())))
		thread.start()
		thread.join()
		self.assertEqual(answers, [False], "wx is for NVDA's main thread only")
		self.assertTrue(linksList.levelSaysNothing(dialog.tree.GetHandle()))


# -- keys a program types late or not at all ------------------------------------------------------------------------


class EditableText:
	"""NVDA's editableText.EditableText."""


class Notepad(EditableText):
	"""Windows 11 Notepad's document, where NVDA hears typing from Notepad."""

	treeInterceptor = None
	appModule = types.SimpleNamespace(appName="notepad")


def key(character, name=None, isCharacter=True):
	"""NVDA 2026.2's KeyboardInputGesture for a key that types ``character``, as far as the assistant reads it."""
	return types.SimpleNamespace(vkCode=0x41, isModifier=False, isCharacter=isCharacter, character=character, mainKeyName=name or character)


#: The tester's log, 25 September, 10:38:35 to 10:38:52: the keys typing "a outlook message" in Notepad ("key"), and
#: the characters Notepad typed ("typed"), from NVDA's speech of each (seconds after 10:38). NVDA's watchdog said
#: "Potential freeze" at 36.999, 38.572 and 39.526. Notepad's text then read "In a outlook meg outlook silence".
TESTERS_TYPING = [
	(35.981, "key", "o"), (36.189, "key", "u"), (36.381, "key", "t"), (37.229, "key", "l"), (37.646, "typed", "o"),
	(37.653, "key", "o"), (37.821, "key", "o"), (38.109, "key", "k"), (38.341, "key", " "), (38.685, "key", "m"),
	(38.810, "typed", "u"), (38.812, "typed", "t"), (38.821, "key", "e"), (39.125, "key", "s"), (39.301, "key", "s"),
	(39.661, "key", "a"), (39.695, "typed", "l"), (39.700, "typed", "o"), (39.704, "typed", "o"), (39.706, "typed", "k"),
	(39.709, "typed", " "), (39.711, "typed", "m"), (39.715, "typed", "e"), (39.965, "key", "g"), (40.213, "key", "e"),
	(40.421, "key", " "), (40.604, "typed", "g"), (50.270, "key", None), (51.933, "key", None),
]


class TypingTests(unittest.TestCase):
	def setUp(self):
		self.now = 0.0
		self.asleep = False
		self.focus = Notepad()
		self.unicode = False
		modules = {
			"api": types.SimpleNamespace(getFocusObject=lambda: self.focus),
			"editableText": types.SimpleNamespace(EditableText=EditableText),
			"keyboardHandler": types.SimpleNamespace(shouldUseToUnicodeEx=lambda focus: self.unicode),
			"watchdog": types.SimpleNamespace(isCoreAsleep=lambda: self.asleep),
		}
		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		clock = mock.patch.object(typingWatch, "time", types.SimpleNamespace(monotonic=lambda: self.now))
		clock.start()
		self.addCleanup(clock.stop)
		typingWatch._waiting.clear()
		typingWatch._lastStack = -100.0
		typingWatch._registered = True
		typingWatch._failed = False
		# The tester's NVDA logs at its debug level; typingWatch does nothing at another.
		logger = logging.getLogger("nvda")
		self.addCleanup(logger.setLevel, logger.level)
		logger.setLevel(logging.DEBUG)
		self.addCleanup(self._restore)

	def _restore(self):
		typingWatch._registered = False
		typingWatch._waiting.clear()

	def press(self, at, gesture):
		self.now = at
		self.assertIs(typingWatch.noteKey(gesture=gesture), True, "the key always goes on")

	def replay(self, events):
		for at, what, character in events:
			if what == "key":
				self.press(at, key(character) if character is not None else key("", "upArrow", isCharacter=False))
			else:
				self.now = at
				typingWatch.typed(character)

	def lines(self, logs):
		return [record.getMessage() for record in logs.records]

	def test_theTestersMessage(self):
		with self.assertLogs("nvda", level="DEBUG") as logs:
			self.replay(TESTERS_TYPING)
		lines = self.lines(logs)
		lost = [line for line in lines if "never typed" in line]
		self.assertEqual(
			[line.split(", pressed")[0] for line in lost],
			["jawsMigrator: notepad never typed 's'", "jawsMigrator: notepad never typed 's'", "jawsMigrator: notepad never typed 'a'", "jawsMigrator: notepad never typed 'e'", "jawsMigrator: notepad never typed ' '"],
			"Notepad typed \"meg\" for \"message\", then a space: s, s, a and e are missing, and NVDA heard no space",
		)
		self.assertTrue(lost[0].endswith("; it typed 'g', pressed after it"), lost[0])
		self.assertIn("jawsMigrator: notepad typed 'u' 2621 ms after the key", lines)
		first = next(line for line in lines if "hasn't typed" in line)
		self.assertTrue(
			first.startswith("jawsMigrator: notepad hasn't typed 'o', pressed 1248 ms ago, 'u', pressed 1040 ms ago, 't', pressed 848 ms ago; NVDA's main thread was busy in:\n  at "),
			first,
		)
		self.assertIn("  at replay (", first, "where the main thread was")
		self.assertEqual(list(typingWatch._waiting), [])

	def test_theMainThreadIdle(self):
		self.asleep = True
		with self.assertLogs("nvda", level="DEBUG") as logs:
			self.press(0.0, key("s"))
			self.press(0.7, key("o"))
		self.assertEqual(self.lines(logs), ["jawsMigrator: notepad hasn't typed 's', pressed 700 ms ago; NVDA's main thread was idle, waiting for something to do"])

	def test_whereTheMainThreadIsOnceASecond(self):
		with self.assertLogs("nvda", level="DEBUG") as logs:
			for at, character in ((0.0, "a"), (0.6, "b"), (1.2, "c"), (1.4, "d"), (1.8, "e")):
				self.press(at, key(character))
		lines = self.lines(logs)
		self.assertEqual([("main thread" in line) for line in lines], [True, False, True])

	def test_typedPromptlyNothingIsLogged(self):
		with self.assertNoLogs("nvda", level="DEBUG"):
			for at, character in ((0.0, "h"), (0.2, "i")):
				self.press(at, key(character))
				self.now = at + 0.05
				typingWatch.typed(character)
			self.press(0.9, key(" "))
			self.now = 0.95
			typingWatch.typed(" ")
		self.assertEqual(list(typingWatch._waiting), [])

	def test_nothingAtAnotherLogLevel(self):
		logger = logging.getLogger("nvda")
		level = logger.level
		logger.setLevel(logging.INFO)
		self.addCleanup(logger.setLevel, level)
		self.press(0.0, key("s"))
		self.press(3.0, key("o"))
		self.assertEqual(list(typingWatch._waiting), [])

	def test_notWatched(self):
		with self.assertNoLogs("nvda", level="DEBUG"):
			self.focus = types.SimpleNamespace(treeInterceptor=None, appModule=None)
			self.press(0.0, key("s"))
			self.focus = Notepad()
			self.focus.treeInterceptor = types.SimpleNamespace(passThrough=False)
			self.press(0.1, key("h"))
			self.focus.treeInterceptor = None
			self.unicode = True
			self.press(0.2, key("a"))
			self.unicode = False
			self.press(0.3, key("s", isCharacter=False))
			self.press(0.4, types.SimpleNamespace(isModifier=True, isCharacter=False))
			self.press(0.5, "kb:a")
		self.assertEqual(list(typingWatch._waiting), [], "browse mode, NVDA's own typed characters, commands and modifiers")

	def test_inFocusModeOnAWebPage(self):
		self.focus.treeInterceptor = types.SimpleNamespace(passThrough=True)
		self.press(0.0, key("s"))
		self.assertEqual([entry[1] for entry in typingWatch._waiting], ["s"])

	def test_theKeyGoesOnWhateverHappens(self):
		def broken():
			raise RuntimeError("no focus")

		sys.modules["api"].getFocusObject = broken
		with self.assertLogs("nvda", level="DEBUG"):
			self.press(0.0, key("s"))

	def test_nvda2026_1(self):
		# NVDA 2026.1's KeyboardInputGesture has no character: the key's own name, for a letter, a digit or space.
		def old(name):
			return types.SimpleNamespace(vkCode=0x41, isModifier=False, isCharacter=True, mainKeyName=name)

		self.press(0.0, old("s"))
		self.press(0.1, old("space"))
		self.press(0.2, old("1"))
		self.press(0.3, old("'"))
		self.assertEqual([entry[1] for entry in typingWatch._waiting], ["s", " ", "1"])
		with self.assertNoLogs("nvda", level="DEBUG"):
			self.now = 0.35
			typingWatch.typed("S")
			typingWatch.typed(" ")
			typingWatch.typed("1")
		self.assertEqual(list(typingWatch._waiting), [])

	def test_registered(self):
		typingWatch._registered = False
		decider = sys.modules["inputCore"].decide_executeGesture
		typingWatch.register()
		self.assertEqual(decider.handlers.count(typingWatch.noteKey), 1)
		self.assertTrue(decider.decide(gesture=key("s")))
		typingWatch.unregister()
		self.assertNotIn(typingWatch.noteKey, decider.handlers)
		self.assertEqual(list(typingWatch._waiting), [])


if __name__ == "__main__":
	unittest.main()
