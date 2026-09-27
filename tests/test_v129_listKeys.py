# Unit tests for version 1.29, from a tester's suggestion (issue 27): "When using Jaws pressing insert f7 only brings up
# links. should we Make the Jaws migrator do the same? Right now under NVDA pressing NVDA gives you the following
# choices: Links radio button checked Alt+k, Headings radio button checked Alt+h, Form fields radio button checked
# Alt+f, Buttons radio button checked Alt+b, Landmarks radio button checked Alt+d".
# JAWS 2026 has a list of one kind for each of its keys (Default.JKM, [virtual keys]): Insert+F7 SelectALink (its Links
# List), Insert+F6 SelectAHeading (Heading List), Insert+F5 SelectAFormField (Select a Form Field), Control+Insert+B
# SelectAButtonFormField (Select a Button) and Control+Insert+R SelectaRegion (Document Regions). The migration gives each
# to NVDA's Elements List, which has every kind, with radio buttons to choose, and opens on the kind chosen last. Now
# (linksList) each JAWS list key opens the Elements List on its own kind alone, with JAWS's title and no radio buttons,
# and a page with none of that kind gets JAWS's words instead of a list.
# The Elements List here is NVDA 2026.2's own, word for word: browseMode.ElementsListDialog, whole, and
# BrowseModeTreeInterceptor._get_ElementsListDialog and script_elementsList, pulled out of release-2026.2's browseMode.py
# with ast by a script. Its window is a real wx.Dialog, made by NVDA's own __init__ through the assistant's real wrapper,
# and read through Windows as NVDA reads it: the dialog's name, and whether each radio button can be seen and used. Only
# NVDA's helpers around it are imitated (its gui.guiHelper sizers, DPI scaling and context help), and ShowModal shows the
# dialog without waiting, so the test can read it.
# Run: python -m unittest tests.test_v129_listKeys -v

import collections
import ctypes
import itertools
import os
import sys
import textwrap
import types
import unittest
from ctypes import wintypes
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import wx  # noqa: E402

from jawsMigrator import elementsList, linksList  # noqa: E402

# -- NVDA 2026.2's own code, word for word (browseMode.py) ---------------------------------------------------------------

NVDA_ELEMENTS_LIST_DIALOG = (
	"class ElementsListDialog(\n"
	"\tDpiScalingHelperMixinWithoutInit,\n"
	"\tgui.contextHelp.ContextHelpMixin,\n"
	"\twx.Dialog,  # wxPython does not seem to call base class initializer, put last in MRO\n"
	"):\n"
	"\thelpId = \"ElementsList\"\n"
	"\tELEMENT_TYPES = (\n"
	"\t\t# Translators: The label of a radio button to select the type of element\n"
	"\t\t# in the browse mode Elements List dialog.\n"
	"\t\t(\"link\", _(\"Lin&ks\")),\n"
	"\t\t# Translators: The label of a radio button to select the type of element\n"
	"\t\t# in the browse mode Elements List dialog.\n"
	"\t\t(\"heading\", _(\"&Headings\")),\n"
	"\t\t# Translators: The label of a radio button to select the type of element\n"
	"\t\t# in the browse mode Elements List dialog.\n"
	"\t\t(\"formField\", _(\"&Form fields\")),\n"
	"\t\t# Translators: The label of a radio button to select the type of element\n"
	"\t\t# in the browse mode Elements List dialog.\n"
	"\t\t(\"button\", _(\"&Buttons\")),\n"
	"\t\t# Translators: The label of a radio button to select the type of element\n"
	"\t\t# in the browse mode Elements List dialog.\n"
	"\t\t(\"landmark\", _(\"Lan&dmarks\")),\n"
	"\t)\n"
	"\n"
	"\tElement = collections.namedtuple(\"Element\", (\"item\", \"parent\"))\n"
	"\n"
	"\tlastSelectedElementType = 0\n"
	"\n"
	"\tshouldSuspendConfigProfileTriggers = True\n"
	"\n"
	"\tdef __init__(self, document):\n"
	"\t\tsuper().__init__(\n"
	"\t\t\tparent=gui.mainFrame,\n"
	"\t\t\t# Translators: The title of the browse mode Elements List dialog.\n"
	"\t\t\ttitle=_(\"Elements List\"),\n"
	"\t\t)\n"
	"\t\tself.document = document\n"
	"\t\tmainSizer = wx.BoxSizer(wx.VERTICAL)\n"
	"\t\tcontentsSizer = wx.BoxSizer(wx.VERTICAL)\n"
	"\n"
	"\t\tchild = wx.RadioBox(\n"
	"\t\t\tself,\n"
	"\t\t\twx.ID_ANY,\n"
	"\t\t\t# Translators: The label of a group of radio buttons to select the type of element\n"
	"\t\t\t# in the browse mode Elements List dialog.\n"
	"\t\t\tlabel=_(\"Type:\"),\n"
	"\t\t\tchoices=tuple(et[1] for et in self.ELEMENT_TYPES),\n"
	"\t\t)\n"
	"\t\tchild.SetSelection(self.lastSelectedElementType)\n"
	"\t\tchild.Bind(wx.EVT_RADIOBOX, self.onElementTypeChange)\n"
	"\t\tcontentsSizer.Add(child, flag=wx.EXPAND)\n"
	"\t\tcontentsSizer.AddSpacer(gui.guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)\n"
	"\n"
	"\t\tself.tree = wx.TreeCtrl(\n"
	"\t\t\tself,\n"
	"\t\t\tsize=self.scaleSize(\n"
	"\t\t\t\t(500, 300),\n"
	"\t\t\t),  # height is chosen to ensure the dialog will fit on an 800x600 screen\n"
	"\t\t\tstyle=wx.TR_HAS_BUTTONS\n"
	"\t\t\t| wx.TR_HIDE_ROOT\n"
	"\t\t\t| wx.TR_LINES_AT_ROOT\n"
	"\t\t\t| wx.TR_SINGLE\n"
	"\t\t\t| wx.TR_EDIT_LABELS,\n"
	"\t\t)\n"
	"\t\tself.tree.Bind(wx.EVT_SET_FOCUS, self.onTreeSetFocus)\n"
	"\t\tself.tree.Bind(wx.EVT_CHAR, self.onTreeChar)\n"
	"\t\tself.tree.Bind(wx.EVT_TREE_BEGIN_LABEL_EDIT, self.onTreeLabelEditBegin)\n"
	"\t\tself.tree.Bind(wx.EVT_TREE_END_LABEL_EDIT, self.onTreeLabelEditEnd)\n"
	"\t\tself.treeRoot = self.tree.AddRoot(\"root\")\n"
	"\t\tcontentsSizer.Add(self.tree, flag=wx.EXPAND)\n"
	"\t\tcontentsSizer.AddSpacer(gui.guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)\n"
	"\n"
	"\t\t# Translators: The label of an editable text field to filter the elements\n"
	"\t\t# in the browse mode Elements List dialog.\n"
	"\t\tfilterText = _(\"Filter b&y:\")\n"
	"\t\tlabeledCtrl = gui.guiHelper.LabeledControlHelper(self, filterText, wx.TextCtrl)\n"
	"\t\tself.filterEdit = labeledCtrl.control\n"
	"\t\tself.filterEdit.Bind(wx.EVT_TEXT, self.onFilterEditTextChange)\n"
	"\t\tcontentsSizer.Add(labeledCtrl.sizer)\n"
	"\t\tcontentsSizer.AddSpacer(gui.guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)\n"
	"\n"
	"\t\tbHelper = gui.guiHelper.ButtonHelper(wx.HORIZONTAL)\n"
	"\t\t# Translators: The label of a button to activate an element in the browse mode Elements List dialog.\n"
	"\t\t# Beware not to set an accelerator that would collide with other controls in this dialog, such as an\n"
	"\t\t# element type radio label.\n"
	"\t\tself.activateButton = bHelper.addButton(self, label=_(\"Activate\"))\n"
	"\t\tself.activateButton.Bind(wx.EVT_BUTTON, lambda evt: self.onAction(True))\n"
	"\n"
	"\t\t# Translators: The label of a button to move to an element\n"
	"\t\t# in the browse mode Elements List dialog.\n"
	"\t\tself.moveButton = bHelper.addButton(self, label=_(\"&Move to\"))\n"
	"\t\tself.moveButton.Bind(wx.EVT_BUTTON, lambda evt: self.onAction(False))\n"
	"\t\tbHelper.addButton(self, id=wx.ID_CANCEL)\n"
	"\n"
	"\t\tcontentsSizer.Add(bHelper.sizer, flag=wx.ALIGN_RIGHT)\n"
	"\n"
	"\t\tmainSizer.Add(contentsSizer, border=gui.guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL)\n"
	"\t\tmainSizer.Fit(self)\n"
	"\t\tself.SetSizer(mainSizer)\n"
	"\n"
	"\t\tself.tree.SetFocus()\n"
	"\t\tself.initElementType(self.ELEMENT_TYPES[self.lastSelectedElementType][0])\n"
	"\t\tself.CentreOnScreen()\n"
	"\n"
	"\tdef onElementTypeChange(self, evt):\n"
	"\t\telementType = evt.GetInt()\n"
	"\t\t# We need to make sure this gets executed after the focus event.\n"
	"\t\t# Otherwise, NVDA doesn't seem to get the event.\n"
	"\t\tqueueHandler.queueFunction(\n"
	"\t\t\tqueueHandler.eventQueue,\n"
	"\t\t\tself.initElementType,\n"
	"\t\t\tself.ELEMENT_TYPES[elementType][0],\n"
	"\t\t)\n"
	"\t\tself.lastSelectedElementType = elementType\n"
	"\n"
	"\tdef initElementType(self, elType):\n"
	"\t\tif elType in (\"link\", \"button\"):\n"
	"\t\t\t# Links and buttons can be activated.\n"
	"\t\t\tself.activateButton.Enable()\n"
	"\t\t\tself.SetAffirmativeId(self.activateButton.GetId())\n"
	"\t\telse:\n"
	"\t\t\t# No other element type can be activated.\n"
	"\t\t\tself.activateButton.Disable()\n"
	"\t\t\tself.SetAffirmativeId(self.moveButton.GetId())\n"
	"\n"
	"\t\t# Gather the elements of this type.\n"
	"\t\tself._elements = []\n"
	"\t\tself._initialElement = None\n"
	"\n"
	"\t\tparentElements = []\n"
	"\t\tisAfterSelection = False\n"
	"\t\tfor item in self.document._iterNodesByType(elType):\n"
	"\t\t\t# Find the parent element, if any.\n"
	"\t\t\tfor parent in reversed(parentElements):\n"
	"\t\t\t\tif item.isChild(parent.item):\n"
	"\t\t\t\t\tbreak\n"
	"\t\t\t\telse:\n"
	"\t\t\t\t\t# We're not a child of this parent, so this parent has no more children and can be removed from the stack.\n"
	"\t\t\t\t\tparentElements.pop()\n"
	"\t\t\telse:\n"
	"\t\t\t\t# No parent found, so we're at the root.\n"
	"\t\t\t\t# Note that parentElements will be empty at this point, as all parents are no longer relevant and have thus been removed from the stack.\n"
	"\t\t\t\tparent = None\n"
	"\n"
	"\t\t\telement = self.Element(item, parent)\n"
	"\t\t\tself._elements.append(element)\n"
	"\n"
	"\t\t\tif not isAfterSelection:\n"
	"\t\t\t\tisAfterSelection = item.isAfterSelection\n"
	"\t\t\t\tif not isAfterSelection:\n"
	"\t\t\t\t\t# The element immediately preceding or overlapping the caret should be the initially selected element.\n"
	"\t\t\t\t\t# Since we have not yet passed the selection, use this as the initial element.\n"
	"\t\t\t\t\ttry:\n"
	"\t\t\t\t\t\tself._initialElement = self._elements[-1]\n"
	"\t\t\t\t\texcept IndexError:\n"
	"\t\t\t\t\t\t# No previous element.\n"
	"\t\t\t\t\t\tpass\n"
	"\n"
	"\t\t\t# This could be the parent of a subsequent element, so add it to the parents stack.\n"
	"\t\t\tparentElements.append(element)\n"
	"\n"
	"\t\t# Start with no filtering.\n"
	"\t\tself.filterEdit.ChangeValue(\"\")\n"
	"\t\tself.filter(\"\", newElementType=True)\n"
	"\n"
	"\tdef filter(self, filterText, newElementType=False):\n"
	"\t\t# If this is a new element type, use the element nearest the cursor.\n"
	"\t\t# Otherwise, use the currently selected element.\n"
	"\t\t# #8753: wxPython 4 returns \"invalid tree item\" when the tree view is empty, so use initial element if appropriate.\n"
	"\t\ttry:\n"
	"\t\t\tdefaultElement = (\n"
	"\t\t\t\tself._initialElement if newElementType else self.tree.GetItemData(self.tree.GetSelection())\n"
	"\t\t\t)\n"
	"\t\texcept:  # noqa: E722\n"
	"\t\t\tdefaultElement = self._initialElement\n"
	"\t\t# Clear the tree.\n"
	"\t\tself.tree.DeleteChildren(self.treeRoot)\n"
	"\n"
	"\t\t# Populate the tree with elements matching the filter text.\n"
	"\t\telementsToTreeItems = {}\n"
	"\t\tdefaultItem = None\n"
	"\t\tmatched = False\n"
	"\t\t# Do case-insensitive matching by lowering both filterText and each element's text.\n"
	"\t\tfilterText = filterText.lower()\n"
	"\t\tfor element in self._elements:\n"
	"\t\t\tlabel = element.item.label\n"
	"\t\t\tif filterText and filterText not in label.lower():\n"
	"\t\t\t\tcontinue\n"
	"\t\t\tmatched = True\n"
	"\t\t\tparent = element.parent\n"
	"\t\t\tif parent:\n"
	"\t\t\t\tparent = elementsToTreeItems.get(parent)\n"
	"\t\t\titem = self.tree.AppendItem(parent or self.treeRoot, label)\n"
	"\t\t\tself.tree.SetItemData(item, element)\n"
	"\t\t\telementsToTreeItems[element] = item\n"
	"\t\t\tif element == defaultElement:\n"
	"\t\t\t\tdefaultItem = item\n"
	"\n"
	"\t\tself.tree.ExpandAll()\n"
	"\n"
	"\t\tif not matched:\n"
	"\t\t\t# No items, so disable the buttons.\n"
	"\t\t\tself.activateButton.Disable()\n"
	"\t\t\tself.moveButton.Disable()\n"
	"\t\t\treturn\n"
	"\n"
	"\t\t# If there's no default item, use the first item in the tree.\n"
	"\t\tself.tree.SelectItem(defaultItem or self.tree.GetFirstChild(self.treeRoot)[0])\n"
	"\t\t# Enable the button(s).\n"
	"\t\t# If the activate button isn't the default button, it is disabled for this element type and shouldn't be enabled here.\n"
	"\t\tif self.AffirmativeId == self.activateButton.Id:\n"
	"\t\t\tself.activateButton.Enable()\n"
	"\t\tself.moveButton.Enable()\n"
	"\n"
	"\tdef onTreeSetFocus(self, evt):\n"
	"\t\t# Start with no search.\n"
	"\t\tself._searchText = \"\"\n"
	"\t\tself._searchCallLater = None\n"
	"\t\tevt.Skip()\n"
	"\n"
	"\tdef onTreeChar(self, evt):\n"
	"\t\tkey = evt.KeyCode\n"
	"\n"
	"\t\tif key == wx.WXK_RETURN:\n"
	"\t\t\t# The enter key should be propagated to the dialog and thus activate the default button,\n"
	"\t\t\t# but this is broken (wx ticket #3725).\n"
	"\t\t\t# Therefore, we must catch the enter key here.\n"
	"\t\t\t# Activate the current default button.\n"
	"\t\t\tevt = wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_ANY)\n"
	"\t\t\tbutton = self.FindWindowById(self.AffirmativeId)\n"
	"\t\t\tif button.Enabled:\n"
	"\t\t\t\tbutton.ProcessEvent(evt)\n"
	"\t\t\telse:\n"
	"\t\t\t\twx.Bell()\n"
	"\n"
	"\t\telif key == wx.WXK_F2:\n"
	"\t\t\titem = self.tree.GetSelection()\n"
	"\t\t\tif item:\n"
	"\t\t\t\tself.tree.EditLabel(item)\n"
	"\t\t\t\tevt.Skip()\n"
	"\n"
	"\t\telif key >= wx.WXK_START or key == wx.WXK_BACK:\n"
	"\t\t\t# Non-printable character.\n"
	"\t\t\tself._searchText = \"\"\n"
	"\t\t\tevt.Skip()\n"
	"\n"
	"\t\telse:\n"
	"\t\t\t# Search the list.\n"
	"\t\t\t# We have to implement this ourselves, as tree views don't accept space as a search character.\n"
	"\t\t\tchar = chr(evt.UnicodeKey).lower()\n"
	"\t\t\t# IF the same character is typed twice, do the same search.\n"
	"\t\t\tif self._searchText != char:\n"
	"\t\t\t\tself._searchText += char\n"
	"\t\t\tif self._searchCallLater:\n"
	"\t\t\t\tself._searchCallLater.Restart()\n"
	"\t\t\telse:\n"
	"\t\t\t\tself._searchCallLater = wx.CallLater(1000, self._clearSearchText)\n"
	"\t\t\tself.search(self._searchText)\n"
	"\n"
	"\tdef onTreeLabelEditBegin(self, evt):\n"
	"\t\titem = self.tree.GetSelection()\n"
	"\t\tselectedItemType = self.tree.GetItemData(item).item\n"
	"\t\tif not selectedItemType.isRenameAllowed:\n"
	"\t\t\tevt.Veto()\n"
	"\n"
	"\tdef onTreeLabelEditEnd(self, evt):\n"
	"\t\tselectedItemNewName = evt.GetLabel()\n"
	"\t\titem = self.tree.GetSelection()\n"
	"\t\tselectedItemType = self.tree.GetItemData(item).item\n"
	"\t\tselectedItemType.rename(selectedItemNewName)\n"
	"\n"
	"\tdef _clearSearchText(self):\n"
	"\t\tself._searchText = \"\"\n"
	"\n"
	"\tdef search(self, searchText):\n"
	"\t\titem = self.tree.GetSelection()\n"
	"\t\tif not item:\n"
	"\t\t\t# No items.\n"
	"\t\t\treturn\n"
	"\n"
	"\t\t# First try searching from the current item.\n"
	"\t\t# Failing that, search from the first item.\n"
	"\t\titems = itertools.chain(\n"
	"\t\t\tself._iterReachableTreeItemsFromItem(item),\n"
	"\t\t\tself._iterReachableTreeItemsFromItem(self.tree.GetFirstChild(self.treeRoot)[0]),\n"
	"\t\t)\n"
	"\t\tif len(searchText) == 1:\n"
	"\t\t\t# If only a single character has been entered, skip (search after) the current item.\n"
	"\t\t\tnext(items)\n"
	"\n"
	"\t\tfor item in items:\n"
	"\t\t\tif self.tree.GetItemText(item).lower().startswith(searchText):\n"
	"\t\t\t\tself.tree.SelectItem(item)\n"
	"\t\t\t\treturn\n"
	"\n"
	"\t\t# Not found.\n"
	"\t\twx.Bell()\n"
	"\n"
	"\tdef _iterReachableTreeItemsFromItem(self, item):\n"
	"\t\twhile item:\n"
	"\t\t\tyield item\n"
	"\n"
	"\t\t\tchildItem = self.tree.GetFirstChild(item)[0]\n"
	"\t\t\tif childItem and self.tree.IsExpanded(item):\n"
	"\t\t\t\t# Has children and is reachable, so recurse.\n"
	"\t\t\t\tfor childItem in self._iterReachableTreeItemsFromItem(childItem):\n"
	"\t\t\t\t\tyield childItem\n"
	"\n"
	"\t\t\titem = self.tree.GetNextSibling(item)\n"
	"\n"
	"\tFILTER_TIMER_DELAY_MS = 300\n"
	"\n"
	"\t@debounceLimiter(\n"
	"\t\tcooldownTimeMs=FILTER_TIMER_DELAY_MS,\n"
	"\t\tdelayTimeMs=FILTER_TIMER_DELAY_MS,\n"
	"\t\trunImmediateFirstCall=False,\n"
	"\t)\n"
	"\tdef _scheduleFilter(self, filterText: str) -> None:\n"
	"\t\tself.filter(filterText)\n"
	"\n"
	"\tdef onFilterEditTextChange(self, evt: wx.CommandEvent) -> None:\n"
	"\t\tself._scheduleFilter(self.filterEdit.GetValue())\n"
	"\t\tevt.Skip()\n"
	"\n"
	"\tdef onAction(self, activate):\n"
	"\t\tprevFocus = gui.mainFrame.prevFocus\n"
	"\t\tself.Close()\n"
	"\t\t# Save off the last selected element type on to the class so its used in initialization next time.\n"
	"\t\tself.__class__.lastSelectedElementType = self.lastSelectedElementType\n"
	"\t\titem = self.tree.GetSelection()\n"
	"\t\titem = self.tree.GetItemData(item).item\n"
	"\t\tif activate:\n"
	"\t\t\titem.activate()\n"
	"\t\telse:\n"
	"\n"
	"\t\t\tdef move():\n"
	"\t\t\t\tspeech.cancelSpeech()\n"
	"\t\t\t\t# Avoid double announce if item.obj is about to gain focus.\n"
	"\t\t\t\tif not (\n"
	"\t\t\t\t\tself.document.passThrough\n"
	"\t\t\t\t\tand getattr(item, \"obj\", False)\n"
	"\t\t\t\t\tand item.obj != prevFocus\n"
	"\t\t\t\t\tand controlTypes.State.FOCUSABLE in item.obj.states\n"
	"\t\t\t\t):\n"
	"\t\t\t\t\t# #8831: Report before moving because moving might change the focus, which\n"
	"\t\t\t\t\t# might mutate the document, potentially invalidating info if it is\n"
	"\t\t\t\t\t# offset-based.\n"
	"\t\t\t\t\titem.report()\n"
	"\t\t\t\titem.moveTo()\n"
	"\n"
	"\t\t\t# We must use core.callLater rather than wx.CallLater to ensure that the callback runs within NVDA's core pump.\n"
	"\t\t\t# If it didn't, and it directly or indirectly called wx.Yield, it could start executing NVDA's core pump from within the yield, causing recursion.\n"
	"\t\t\tcore.callLater(100, move)\n"
)
NVDA_GET_ELEMENTS_LIST_DIALOG = (
	"def _get_ElementsListDialog(self):\n"
	"\treturn ElementsListDialog\n"
)
NVDA_SCRIPT_ELEMENTS_LIST = (
	"def script_elementsList(self, gesture):\n"
	"\t# We need this to be a modal dialog, but it mustn't block this script.\n"
	"\tdef run():\n"
	"\t\tgui.mainFrame.prePopup()\n"
	"\t\td = self.ElementsListDialog(self)\n"
	"\t\td.ShowModal()\n"
	"\t\td.Destroy()\n"
	"\t\tgui.mainFrame.postPopup()\n"
	"\n"
	"\twx.CallAfter(run)\n"
	"\n"
	"# Translators: the description for the Elements List command in browse mode.\n"
	"script_elementsList.__doc__ = _(\"Lists various types of elements in this document\")\n"
	"script_elementsList.ignoreTreeInterceptorPassThrough = True\n"
)
#: Where NVDA_ELEMENTS_LIST_DIALOG, NVDA_GET_ELEMENTS_LIST_DIALOG and NVDA_SCRIPT_ELEMENTS_LIST are in NVDA's source.
NVDA_CODE_FILE = "browseMode.py"
#: virtualBuffers/adobeAcrobat.py's ElementsListDialog: links and headings only.
NVDA_ADOBE_ELEMENT_TYPES = "ELEMENT_TYPES = browseMode.ElementsListDialog.ELEMENT_TYPES[0:2]"


def _(text):
	return text


# -- what NVDA's dialog uses around it, imitated --------------------------------------------------------------------------


class DpiScalingHelperMixinWithoutInit:
	"""NVDA's gui.dpiScalingHelper.DpiScalingHelperMixinWithoutInit, at 100 %."""

	def scaleSize(self, size):
		return size


class ContextHelpMixin:
	"""NVDA's gui.contextHelp.ContextHelpMixin, without F1."""


class LabeledControlHelper:
	"""NVDA's gui.guiHelper.LabeledControlHelper, as the Elements List's Filter box uses it: a label, then the control."""

	def __init__(self, parent, labelText, wxCtrlClass, **kwargs):
		self.label = wx.StaticText(parent, label=labelText)
		self.control = wxCtrlClass(parent, **kwargs)
		self.sizer = wx.BoxSizer(wx.HORIZONTAL)
		self.sizer.Add(self.label, flag=wx.ALIGN_CENTER_VERTICAL)
		self.sizer.AddSpacer(10)
		self.sizer.Add(self.control)


class ButtonHelper:
	"""NVDA's gui.guiHelper.ButtonHelper: buttons side by side."""

	def __init__(self, orientation):
		self.sizer = wx.BoxSizer(orientation)

	def addButton(self, *args, **kwargs):
		button = wx.Button(*args, **kwargs)
		if self.sizer.GetItemCount():
			self.sizer.AddSpacer(10)
		self.sizer.Add(button)
		return button


def debounceLimiter(**kwargs):
	"""NVDA's utils.debounce.debounceLimiter: the Filter box filters at once here."""
	return lambda function: function


#: What NVDA runs after a delay (core.callLater): the Move to button's move.
later = []
app = wx.GetApp() or wx.App(False)


class MainFrame(wx.Frame):
	"""NVDA's gui.mainFrame, as far as its dialogs go: their parent, and the popups around them."""

	prevFocus = None

	def prePopup(self):
		pass

	def postPopup(self):
		pass


gui = types.SimpleNamespace(
	mainFrame=MainFrame(None),
	contextHelp=types.SimpleNamespace(ContextHelpMixin=ContextHelpMixin),
	guiHelper=types.SimpleNamespace(
		LabeledControlHelper=LabeledControlHelper,
		ButtonHelper=ButtonHelper,
		SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS=10,
		BORDER_FOR_DIALOGS=10,
	),
)
State = types.SimpleNamespace(FOCUSABLE="focusable")
_DIALOG_NAMES = {
	"wx": wx,
	"gui": gui,
	"_": _,
	"collections": collections,
	"itertools": itertools,
	"DpiScalingHelperMixinWithoutInit": DpiScalingHelperMixinWithoutInit,
	"debounceLimiter": debounceLimiter,
	"queueHandler": types.SimpleNamespace(eventQueue="eventQueue", queueFunction=lambda queue, function, *args, **kwargs: function(*args, **kwargs)),
	"speech": types.SimpleNamespace(cancelSpeech=lambda: None),
	"core": types.SimpleNamespace(callLater=lambda delay, function, *args, **kwargs: later.append(function)),
	"controlTypes": types.SimpleNamespace(State=State),
}


def nvdaCode(source, name, namespace):
	"""Compile NVDA's own ``source`` against the imitation NVDA, and give back ``name`` from it."""
	scope = dict(namespace)
	exec(compile(source, f"<NVDA 2026.2 browseMode.{name}>", "exec"), scope)
	return scope[name]


ElementsListDialog = nvdaCode(NVDA_ELEMENTS_LIST_DIALOG, "ElementsListDialog", _DIALOG_NAMES)

#: Each Elements List that came up.
shown = []


class ShownElementsListDialog(ElementsListDialog):
	"""NVDA's Elements List, which comes up without being put on the screen or waiting for it to close, so that the test
	can read it as Windows has it and other tests keep the foreground; nothing else differs."""

	def ShowModal(self):
		shown.append(self)
		return wx.ID_OK

	def Destroy(self):
		# When the test is done with it.
		pass


class AdobeElementsListDialog(ShownElementsListDialog):
	"""virtualBuffers.adobeAcrobat's Elements List: links and headings only."""


_adobe = {}
exec(NVDA_ADOBE_ELEMENT_TYPES, {"browseMode": types.SimpleNamespace(ElementsListDialog=ElementsListDialog)}, _adobe)
AdobeElementsListDialog.ELEMENT_TYPES = _adobe["ELEMENT_TYPES"]


class TreeInterceptor:
	"""NVDA's tree interceptor, as far as the Elements List goes."""

	passThrough = False


_SCRIPT_SOURCE = (
	"class BrowseModeTreeInterceptor(TreeInterceptor):\n"
	+ textwrap.indent(NVDA_GET_ELEMENTS_LIST_DIALOG, "\t")
	+ "\n"
	+ textwrap.indent(NVDA_SCRIPT_ELEMENTS_LIST, "\t")
)
# NVDA's script runs its dialog with wx.CallAfter, which comes at once here.
BrowseModeTreeInterceptor = nvdaCode(
	_SCRIPT_SOURCE,
	"BrowseModeTreeInterceptor",
	{
		"TreeInterceptor": TreeInterceptor,
		"ElementsListDialog": ShownElementsListDialog,
		"gui": gui,
		"wx": types.SimpleNamespace(CallAfter=lambda function, *args: function(*args)),
		"_": _,
	},
)
# NVDA makes a property of each _get_ method (baseObject.AutoPropertyType).
BrowseModeTreeInterceptor.ElementsListDialog = property(BrowseModeTreeInterceptor._get_ElementsListDialog)


class Element:
	"""An element of the page: its kind, text and, for a heading, its level."""

	def __init__(self, itemType, text, level=None):
		self.itemType, self.text, self.level = itemType, text, level


class QuickNavItem:
	"""NVDA's quick navigation item for an element, as the Elements List reads it."""

	#: Browse mode's cursor is at the top of the page, so the list starts on its first item.
	isAfterSelection = True

	def __init__(self, document, element):
		self.document, self.element, self.itemType = document, element, element.itemType

	@property
	def label(self):
		return self.element.text

	def isChild(self, parent):
		# NVDA's TextInfoQuickNavItem.isChild: a heading comes under a heading of a lower level.
		if self.itemType != "heading":
			return False
		return self.element.level > parent.element.level

	def report(self):
		pass

	def moveTo(self):
		self.document.moves.append(self.element.text)

	def activate(self):
		self.document.activated.append(self.element.text)


class BrowseModeDocumentTreeInterceptor(BrowseModeTreeInterceptor):
	"""NVDA's browse mode document for a page."""

	def __init__(self, elements):
		self.elements = elements
		self.moves, self.activated = [], []

	def _iterNodesByType(self, itemType, direction="next", pos=None):
		for element in self.elements:
			if element.itemType == itemType:
				yield QuickNavItem(self, element)


class AdobeDocument(BrowseModeDocumentTreeInterceptor):
	"""A PDF in Adobe Reader: its Elements List has links and headings only."""

	ElementsListDialog = AdobeElementsListDialog


class ExcelBrowseMode(BrowseModeTreeInterceptor):
	"""Excel's browse mode, which is a BrowseModeTreeInterceptor but not a document."""

	def __init__(self, elements):
		self.elements = elements

	_iterNodesByType = BrowseModeDocumentTreeInterceptor._iterNodesByType


class TextInfoQuickNavItem:
	"""NVDA's browseMode.TextInfoQuickNavItem, which the assistant's links part changes; not used by these pages."""

	def _getLabelForProperties(self, labelPropertyGetter):
		return labelPropertyGetter("name")

	def activate(self):
		pass


#: A news page with every kind of element.
PAGE = [
	Element("landmark", "banner"),
	Element("link", "Skip to content"),
	Element("heading", "HEADLINES", level=1),
	Element("link", "Homepage"),
	Element("heading", "Bills Sign Tight End", level=2),
	Element("link", "Read more"),
	Element("formField", "Search, edit"),
	Element("button", "Search"),
	Element("landmark", "main"),
	Element("heading", "Latest Rumors", level=2),
	Element("button", "Subscribe"),
	Element("landmark", "content info"),
]
#: Edge's New Tab page: landmarks and a search button, no link and no heading.
NEW_TAB = [Element("landmark", "main"), Element("landmark", "search"), Element("formField", "Search the web, edit"), Element("button", "Search")]


def key(*identifiers):
	"""A key press, as NVDA's KeyboardInputGesture gives its identifiers."""
	return types.SimpleNamespace(identifiers=list(identifiers), displayName=identifiers[0].partition(":")[2])


#: JAWS's keys, as NVDA has them after the migration (Insert or Caps Lock are NVDA's key).
INSERT_F7 = key("kb(desktop):NVDA+f7", "kb:NVDA+f7")
CAPS_LOCK_F7 = key("kb(laptop):NVDA+f7", "kb:NVDA+f7")
INSERT_F6 = key("kb(desktop):NVDA+f6", "kb:NVDA+f6")
INSERT_F5 = key("kb(desktop):NVDA+f5", "kb:NVDA+f5")
CONTROL_INSERT_B = key("kb(desktop):control+NVDA+b", "kb:control+NVDA+b")
CONTROL_INSERT_R = key("kb(desktop):NVDA+control+r", "kb:NVDA+control+r")
KINESIS_INSERT_SLASH = key("kb(desktop):NVDA+/", "kb:NVDA+/")
#: A key the user gave NVDA's Elements List in Input Gestures, which isn't one of JAWS's.
OTHER_KEY = key("kb(desktop):NVDA+shift+e", "kb:NVDA+shift+e")

# -- reading the dialog as Windows has it --------------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32")
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindowLongW.restype = ctypes.c_long
_ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumChildWindows.argtypes = (wintypes.HWND, _ENUM, wintypes.LPARAM)
GWL_STYLE = -16
#: A window's own styles (WinUser.h): shown, and unavailable. MSAA's STATE_SYSTEM_INVISIBLE and UNAVAILABLE, which NVDA
#: reads, come from them, and Tab and access keys pass over a window without the first or with the second.
WS_VISIBLE = 0x10000000
WS_DISABLED = 0x08000000
BS_TYPEMASK = 0xF
RADIO_STYLES = (0x4, 0x9)  # BS_RADIOBUTTON, BS_AUTORADIOBUTTON


def windowText(hwnd) -> str:
	buffer = ctypes.create_unicode_buffer(256)
	user32.GetWindowTextW(hwnd, buffer, 256)
	return buffer.value


def radioButtons(dialog):
	"""The dialog's radio buttons as Windows has them, which is what NVDA reads: [(text, shown, available)]."""
	found = []

	def each(hwnd, lParam):
		buffer = ctypes.create_unicode_buffer(64)
		user32.GetClassNameW(hwnd, buffer, 64)
		style = user32.GetWindowLongW(hwnd, GWL_STYLE)
		if buffer.value == "Button" and style & BS_TYPEMASK in RADIO_STYLES:
			found.append((windowText(hwnd), bool(style & WS_VISIBLE), not style & WS_DISABLED))
		return True

	user32.EnumChildWindows(dialog.GetHandle(), _ENUM(each), 0)
	return found


def items(dialog):
	"""The list's items as NVDA's tree shows them: each item's text, indented under the one it is under."""
	tree = dialog.tree
	result = []

	def walk(parent, depth):
		item, cookie = tree.GetFirstChild(parent)
		while item.IsOk():
			result.append("  " * depth + tree.GetItemText(item))
			walk(item, depth + 1)
			item, cookie = tree.GetNextChild(parent, cookie)

	walk(dialog.treeRoot, 0)
	return result


def selected(dialog):
	item = dialog.tree.GetSelection()
	return dialog.tree.GetItemText(item) if item.IsOk() else None


class ListKeysTestCase(unittest.TestCase):
	def setUp(self):
		browseModule = types.ModuleType("browseMode")
		browseModule.BrowseModeTreeInterceptor = BrowseModeTreeInterceptor
		browseModule.BrowseModeDocumentTreeInterceptor = BrowseModeDocumentTreeInterceptor
		browseModule.ElementsListDialog = ElementsListDialog
		browseModule.TextInfoQuickNavItem = TextInfoQuickNavItem
		patcher = mock.patch.dict(sys.modules, {"browseMode": browseModule})
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(self._restore)
		nvdaStubs.spoken.clear()
		shown.clear()
		later.clear()
		linksList._failed = False

	def _restore(self):
		for dialog in shown:
			wx.Dialog.Destroy(dialog)
		shown.clear()
		wx.Yield()
		self.assertFalse(linksList._failed, "nothing failed")
		linksList.unregister()
		linksList._replaced.clear()
		linksList._failed = False
		linksList._opening = None
		ElementsListDialog.lastSelectedElementType = 0
		# NVDA's onAction keeps the kind on the dialog's own class, which is a subclass here.
		for cls in (ShownElementsListDialog, AdobeElementsListDialog):
			if "lastSelectedElementType" in vars(cls):
				delattr(cls, "lastSelectedElementType")

	def press(self, gesture, document):
		"""Press ``gesture`` in ``document``, where it opens the Elements List: the list that came up, or None."""
		before = len(shown)
		document.script_elementsList(gesture)
		self.assertLessEqual(len(shown), before + 1)
		return shown[-1] if len(shown) > before else None

	def assertJawsList(self, dialog, title, expected):
		self.assertIsNotNone(dialog, f"no {title} came up")
		self.assertEqual(windowText(dialog.GetHandle()), title, "NVDA says the dialog's name as it opens")
		self.assertEqual(items(dialog), expected)
		buttons = radioButtons(dialog)
		self.assertEqual(len(buttons), 5, buttons)
		self.assertTrue(all(not visible and not enabled for _text, visible, enabled in buttons), f"no radio button to Tab to or press: {buttons}")

	def assertNvdasOwnList(self, dialog, opensOn, expected):
		self.assertIsNotNone(dialog)
		self.assertEqual(windowText(dialog.GetHandle()), "Elements List")
		self.assertEqual(items(dialog), expected)
		buttons = radioButtons(dialog)
		self.assertEqual([text for text, _visible, _enabled in buttons], ["Lin&ks", "&Headings", "&Form fields", "&Buttons", "Lan&dmarks"])
		self.assertTrue(all(visible and enabled for _text, visible, enabled in buttons), buttons)
		checked = [child for child in dialog.GetChildren() if isinstance(child, wx.RadioBox)][0].GetSelection()
		self.assertEqual(ElementsListDialog.ELEMENT_TYPES[checked][0], opensOn)


LINKS = ["Skip to content", "Homepage", "Read more"]
HEADINGS = ["HEADLINES", "  Bills Sign Tight End", "  Latest Rumors"]


# -- JAWS's list keys -----------------------------------------------------------------------------------------------------


class JawsListTests(ListKeysTestCase):
	def setUp(self):
		super().setUp()
		linksList.register(links=False, keys=True)

	def test_insertF7ListsTheLinksAlone(self):
		# The tester's Insert+F7: JAWS's Links List, "Links List dialog", links and nothing to choose.
		self.assertJawsList(self.press(INSERT_F7, BrowseModeDocumentTreeInterceptor(PAGE)), "Links List", LINKS)
		self.assertEqual(nvdaStubs.spoken, [])

	def test_capsLockF7AsWell(self):
		self.assertJawsList(self.press(CAPS_LOCK_F7, BrowseModeDocumentTreeInterceptor(PAGE)), "Links List", LINKS)

	def test_eachKeyItsOwnList(self):
		for gesture, title, expected in (
			(INSERT_F6, "Heading List", HEADINGS),
			(INSERT_F5, "Select a Form Field", ["Search, edit"]),
			(CONTROL_INSERT_B, "Select a Button", ["Search", "Subscribe"]),
			(CONTROL_INSERT_R, "Document Regions", ["banner", "main", "content info"]),
			(KINESIS_INSERT_SLASH, "Links List", LINKS),
		):
			with self.subTest(title):
				self.assertJawsList(self.press(gesture, BrowseModeDocumentTreeInterceptor(PAGE)), title, expected)

	def test_whateverKindTheListWasLeftOn(self):
		# NVDA's own list opens on the kind chosen last: the tester had left it on buttons.
		ElementsListDialog.lastSelectedElementType = 3
		self.assertJawsList(self.press(INSERT_F7, BrowseModeDocumentTreeInterceptor(PAGE)), "Links List", LINKS)
		self.assertJawsList(self.press(INSERT_F6, BrowseModeDocumentTreeInterceptor(PAGE)), "Heading List", HEADINGS)

	def test_theListStillWorks(self):
		# Down Arrow, then Enter in JAWS's Heading List moves to the heading; the Filter box finds by name.
		document = BrowseModeDocumentTreeInterceptor(PAGE)
		dialog = self.press(INSERT_F6, document)
		self.assertEqual(selected(dialog), "HEADLINES")
		self.assertFalse(dialog.activateButton.IsEnabled(), "a heading is moved to, not activated")
		dialog.filterEdit.SetValue("rumors")
		dialog.filter("rumors")
		self.assertEqual(items(dialog), ["Latest Rumors"])
		dialog.onAction(False)
		for move in later:
			move()
		self.assertEqual(document.moves, ["Latest Rumors"])
		# And Enter on a link activates it.
		document = BrowseModeDocumentTreeInterceptor(PAGE)
		dialog = self.press(INSERT_F7, document)
		self.assertTrue(dialog.activateButton.IsEnabled())
		dialog.onAction(True)
		self.assertEqual(document.activated, ["Skip to content"])

	def test_nvdasOwnListKeepsItsKind(self):
		# NVDA keeps the kind of the list you last moved from (onAction, on the dialog's class), to open its own list on
		# it next time. JAWS's Heading List leaves that as it was.
		document = BrowseModeDocumentTreeInterceptor(PAGE)
		self.press(INSERT_F6, document).onAction(False)
		self.assertEqual(ShownElementsListDialog.lastSelectedElementType, 0)
		self.assertNvdasOwnList(self.press(OTHER_KEY, document), "link", LINKS)
		# In NVDA's own list, choosing Headings and moving to one keeps headings, as NVDA does, and Insert+F7 still
		# lists the links.
		dialog = shown[-1]
		dialog.onElementTypeChange(types.SimpleNamespace(GetInt=lambda: 1))
		self.assertEqual(items(dialog), HEADINGS)
		dialog.onAction(False)
		self.assertEqual(ShownElementsListDialog.lastSelectedElementType, 1)
		self.assertJawsList(self.press(INSERT_F7, document), "Links List", LINKS)
		self.assertNvdasOwnList(self.press(OTHER_KEY, document), "heading", HEADINGS)

	def test_anotherKeyOpensNvdasOwnList(self):
		# A key the user gave the Elements List in Input Gestures has NVDA's list with every kind, where it was left.
		ElementsListDialog.lastSelectedElementType = 1
		self.assertNvdasOwnList(self.press(OTHER_KEY, BrowseModeDocumentTreeInterceptor(PAGE)), "heading", HEADINGS)
		dialog = self.press(key("br(freedomScientific):leftWizWheelPress"), BrowseModeDocumentTreeInterceptor(PAGE))
		self.assertEqual(windowText(dialog.GetHandle()), "Elements List", "a braille display's key too")
		self.assertIsNone(linksList.keyKind(BrowseModeDocumentTreeInterceptor(PAGE), None), "and a script run without a key")

	def test_aKindTheDocumentsListDoesntHave(self):
		# A PDF's Elements List has links and headings only: Insert+F5 opens NVDA's own list there.
		document = AdobeDocument(PAGE)
		dialog = self.press(INSERT_F7, document)
		self.assertEqual((windowText(dialog.GetHandle()), items(dialog)), ("Links List", LINKS))
		self.assertIsNone(linksList.keyKind(document, INSERT_F5))
		dialog = self.press(INSERT_F5, document)
		self.assertEqual(windowText(dialog.GetHandle()), "Elements List")
		self.assertEqual(len(radioButtons(dialog)), 2)

	def test_notADocument(self):
		# Excel's browse mode isn't a document: its keys mean other things in JAWS, and NVDA's own list opens.
		self.assertIsNone(linksList.keyKind(ExcelBrowseMode(PAGE), INSERT_F7))
		self.assertEqual(windowText(self.press(INSERT_F7, ExcelBrowseMode(PAGE)).GetHandle()), "Elements List")


class NoneOfThatKindTests(ListKeysTestCase):
	def setUp(self):
		super().setUp()
		linksList.register(links=False, keys=True)

	def test_jawsWordsAndNoList(self):
		# Edge's New Tab page has no link and no heading: JAWS says so and opens nothing.
		for gesture, said in (
			(INSERT_F7, "no links"),
			(INSERT_F6, "No headings found"),
		):
			with self.subTest(said):
				nvdaStubs.spoken.clear()
				self.assertIsNone(self.press(gesture, BrowseModeDocumentTreeInterceptor(NEW_TAB)))
				self.assertEqual(nvdaStubs.spoken, [said])
		self.assertIsNone(linksList._opening)

	def test_eachKind(self):
		for gesture, said in (
			(INSERT_F5, "no form fields were found"),
			(CONTROL_INSERT_B, "no buttons were found"),
			(CONTROL_INSERT_R, "No regions were found on the page"),
		):
			with self.subTest(said):
				nvdaStubs.spoken.clear()
				self.assertIsNone(self.press(gesture, BrowseModeDocumentTreeInterceptor([Element("link", "Home")])))
				self.assertEqual(nvdaStubs.spoken, [said])

	def test_whatThePageHasOpens(self):
		self.assertJawsList(self.press(CONTROL_INSERT_R, BrowseModeDocumentTreeInterceptor(NEW_TAB)), "Document Regions", ["main", "search"])
		self.assertEqual(nvdaStubs.spoken, [])


class TurnedOffTests(ListKeysTestCase):
	def test_nvdasOwnList(self):
		# Only the links part of the assistant's Elements List: Insert+F6 opens NVDA's list on the kind it was left on.
		linksList.register(links=True, keys=False)
		self.assertNvdasOwnList(self.press(INSERT_F6, BrowseModeDocumentTreeInterceptor(PAGE)), "link", LINKS)
		self.assertFalse(linksList._isOurs(vars(ElementsListDialog)["__init__"]), "NVDA's own __init__")

	def test_turnedOffAfterwards(self):
		linksList.register(links=True, keys=True)
		self.assertTrue(linksList._isOurs(vars(ElementsListDialog)["__init__"]))
		linksList.register(links=True, keys=False)
		self.assertFalse(linksList._isOurs(vars(ElementsListDialog)["__init__"]), "NVDA's own dialog is back at once")
		self.assertTrue(linksList._isOurs(vars(BrowseModeTreeInterceptor)["script_elementsList"]), "the links part keeps its script")
		self.assertNvdasOwnList(self.press(INSERT_F7, BrowseModeDocumentTreeInterceptor(PAGE)), "link", LINKS)
		linksList.unregister()
		self.assertFalse(linksList._isOurs(vars(BrowseModeTreeInterceptor)["script_elementsList"]))

	def test_listKeysAlone(self):
		# The links part turned off, the list keys on: NVDA's labels and activation are its own, the list keys still work.
		linksList.register(links=False, keys=True)
		self.assertFalse(linksList._isOurs(vars(TextInfoQuickNavItem)["_getLabelForProperties"]))
		self.assertFalse(linksList._isOurs(vars(TextInfoQuickNavItem)["activate"]))
		self.assertJawsList(self.press(INSERT_F6, BrowseModeDocumentTreeInterceptor(PAGE)), "Heading List", HEADINGS)

	def test_bothTogether(self):
		# As the assistant comes: "no links" for a list that opens on links, and the Links List for Insert+F7.
		linksList.register(links=True, keys=True)
		self.assertIsNone(self.press(INSERT_F7, BrowseModeDocumentTreeInterceptor(NEW_TAB)))
		self.assertEqual(nvdaStubs.spoken, ["no links"], "said once")
		self.assertJawsList(self.press(INSERT_F7, BrowseModeDocumentTreeInterceptor(PAGE)), "Links List", LINKS)
		self.assertTrue(linksList._isOurs(vars(TextInfoQuickNavItem)["_getLabelForProperties"]))

	def test_settings(self):
		self.assertTrue(linksList.keysWanted({}), "on unless turned off")
		self.assertFalse(linksList.keysWanted({linksList.KEYS_KEY: False}))
		self.assertTrue(linksList.wanted({linksList.KEYS_KEY: False}), "a setting of its own")
		from jawsMigrator import state

		self.assertIs(state.DEFAULTS[linksList.KEYS_KEY], True)


class KeysTests(unittest.TestCase):
	def test_theKeysAsTheMigrationConvertsThem(self):
		# The migration gives these keys to the Elements List (jawsKeyMap), converted the same way.
		from jawsMigrator import jawsKeyMap

		for jawsKey, script, kind in linksList.JAWS_LIST_KEYS:
			with self.subTest(jawsKey):
				targets = jawsKeyMap.getNvdaTargets(script, jawsKey)
				self.assertEqual(targets[0][:3], ("browseMode", "BrowseModeTreeInterceptor", "elementsList"))
				gesture = jawsKeyMap.jawsKeyToNvdaGesture(jawsKey, "common")
				self.assertEqual(linksList.keyKinds()[linksList._normalized(gesture)[1]], kind)
		self.assertEqual(
			linksList.keyKinds(),
			{"f7+nvda": "link", "/+nvda": "link", "f6+nvda": "heading", "f5+nvda": "formField", "b+control+nvda": "button", "control+nvda+r": "landmark"},
		)

	def test_jawsOwnKeys(self):
		# JAWS 2026's Default.JKM, when JAWS is on this computer.
		path = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Freedom Scientific", "JAWS", "2026", "Scripts", "enu", "Default.JKM")
		if not os.path.isfile(path):
			self.skipTest("JAWS 2026 isn't on this computer")
		with open(path, encoding="utf-8-sig", errors="replace") as f:
			lines = [line.strip() for line in f]
		for jawsKey, script, _kind in linksList.JAWS_LIST_KEYS:
			self.assertIn(f"{jawsKey}={script}".lower(), {line.lower() for line in lines}, jawsKey)

	def test_everyKindIsNvdas(self):
		self.assertEqual(set(linksList.TITLES), {kind for kind, _label in ElementsListDialog.ELEMENT_TYPES})
		self.assertEqual(set(linksList.NONE_FOUND), set(linksList.TITLES))


class LoadingPageTests(ListKeysTestCase):
	def test_theKeyIsKeptForWhenThePageIsReady(self):
		# Version 1.18 opens the list once a loading page is ready (elementsList.withoutDocument), with the key pressed.
		linksList.register(links=True, keys=True)
		document = BrowseModeDocumentTreeInterceptor(PAGE)
		focus = types.SimpleNamespace(treeInterceptor=document)
		with mock.patch.object(elementsList, "_readyDocument", lambda obj: obj.treeInterceptor), mock.patch.dict(
			sys.modules, {"api": types.SimpleNamespace(getFocusObject=lambda: focus)}
		):
			elementsList.withoutDocument(elementsList._gestures, None, INSERT_F6)
		self.assertJawsList(shown[-1], "Heading List", HEADINGS)

	def test_decideGesturePassesTheKey(self):
		queued = []
		queueHandler = types.SimpleNamespace(eventQueue="events", queueFunction=lambda queue, function, *args: queued.append((function, args)))
		inputCore = types.SimpleNamespace(manager=types.SimpleNamespace(isInputHelpActive=False))
		gesture = types.SimpleNamespace(isModifier=False, script=None, identifiers=["kb:NVDA+f6"])
		focus = types.SimpleNamespace(sleepMode=False)
		with mock.patch.object(elementsList, "_enabled", True), mock.patch.object(elementsList, "opensElementsList", lambda g: True), mock.patch.dict(
			sys.modules,
			{"queueHandler": queueHandler, "inputCore": inputCore, "api": types.SimpleNamespace(getFocusObject=lambda: focus)},
		):
			self.assertFalse(elementsList.decideGesture(gesture=gesture))
		self.assertEqual(queued, [(elementsList.withoutDocument, (elementsList._gestures, None, gesture))])


class NvdasOwnCodeTests(unittest.TestCase):
	def test_theCodeIsNvdas(self):
		# Each piece is in NVDA 2026.2's source, at the margin or as a method, when a copy of it is around: set NVDA_SOURCE
		# to its source folder.
		source = os.environ.get("NVDA_SOURCE")
		if not source:
			self.skipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
		with open(os.path.join(source, NVDA_CODE_FILE), encoding="utf-8") as f:
			text = f.read().replace("\r\n", "\n")
		self.assertIn(NVDA_ELEMENTS_LIST_DIALOG, text)
		for block in (NVDA_GET_ELEMENTS_LIST_DIALOG, NVDA_SCRIPT_ELEMENTS_LIST):
			self.assertIn(textwrap.indent(block, "\t", lambda line: line.strip() != ""), text)
		with open(os.path.join(source, "virtualBuffers", "adobeAcrobat.py"), encoding="utf-8") as f:
			self.assertIn("\t" + NVDA_ADOBE_ELEMENT_TYPES + "\n", f.read().replace("\r\n", "\n"))


if __name__ == "__main__":
	unittest.main()
