# Unit tests for version 1.17, from a tester's report on version 1.15 (issue 11):
# - elementsList: on the jawsMigrator page on github.com, NVDA+F7 a quarter of a second after "Page ready", as the
#   page said "alert", stopped NVDA 2026.2 with a LookupError halfway through making its Elements List. The dialog was
#   left unseen with the focus in it: Enter activated the Issues link behind it, Escape and NVDA+F7 did nothing, and
#   only Alt+Tab got the tester out. The page had changed between NVDA finding its links and reading their names.
# The imitation NVDA below runs NVDA 2026.2's own code for this, word for word: ElementsListDialog's initElementType
# and filter (browseMode.py), VirtualBufferQuickNavItem (virtualBuffers/__init__.py), and VirtualBufferTextInfo's
# _getControlFieldAttribs and _getOffsetsFromFieldIdentifier, with NVDAHelper's virtual buffer calls answered from an
# imitation page, which can change between NVDA's two steps. Only _getLabelForProperties is shorter: it reads the
# element's name and states, as NVDA's does. The assistant's register, unregister and wrappers are the real ones.
# Run: python -m unittest tests.test_v117_fixes -v

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import elementsList  # noqa: E402

DOC_HANDLE = 65544
UNIT_CHARACTER = "character"
POSITION_CARET = "caret"


class Element:
	"""A link, button or heading of the page, as NVDA's virtual buffer has it."""

	def __init__(self, identifier, itemType, text, level=None, states=()):
		self.identifier, self.itemType, self.text, self.level, self.states = identifier, itemType, text, level, frozenset(states)

	def attributes(self):
		attrs = {"controlIdentifier_docHandle": str(DOC_HANDLE), "controlIdentifier_ID": str(self.identifier), "name": self.text, "states": self.states}
		if self.level is not None:
			attrs["level"] = str(self.level)
		return attrs


class Page:
	"""The web page in NVDA's virtual buffer: its elements one after another, each followed by a line break."""

	def __init__(self, elements):
		self.elements = list(elements)
		#: How many times NVDA asked where an element is now (VBuf_getControlFieldNodeWithIdentifier).
		self.lookups = 0

	def offsets(self):
		places, at = {}, 0
		for element in self.elements:
			places[element.identifier] = (at, at + len(element.text))
			at += len(element.text) + 1
		return places

	def text(self, start, end):
		return "".join(element.text + "\n" for element in self.elements)[start:end]

	def at(self, offset):
		for element in self.elements:
			start, end = self.offsets()[element.identifier]
			if start <= offset <= end:
				return element
		return None

	def byIdentifier(self, identifier):
		return next((element for element in self.elements if element.identifier == identifier), None)


# The tester's page, as NVDA found it: the links NVDA+F7 lists, in the order of the page.
REPOSITORY = [
	Element(1, "link", "Skip to content", states={"same page"}),
	Element(2, "link", "Homepage", states={"visited"}),
	Element(11, "link", "Issues (10)", states={"visited"}),
	Element(12, "link", "Pull requests"),
	Element(40, "link", "What's new in 1.15", states={"same page"}),
	Element(41, "link", "Updates", states={"same page"}),
]
#: What GitHub put in the page just before the tester pressed NVDA+F7: an alert above the links.
ALERT = Element(900, "alert", "Copied!")
HEADINGS = [
	Element(50, "heading", "jawsMigrator", level=1),
	Element(51, "heading", "What's new in 1.15", level=2),
	Element(52, "heading", "Using the assistant", level=2),
	Element(53, "heading", "Choosing what to import", level=3),
]


class FieldCommand:
	"""NVDA's textInfos.FieldCommand."""

	def __init__(self, command, field):
		self.command, self.field = command, field


class Offsets:
	"""NVDA's textInfos.offsets.Offsets."""

	def __init__(self, startOffset, endOffset):
		self.startOffset, self.endOffset = startOffset, endOffset


class CInt:
	"""ctypes.c_int, which NVDAHelper's functions fill in through ctypes.byref."""

	def __init__(self, value=0):
		self.value = value


#: The ctypes NVDA's own code below is compiled against.
ctypes = types.SimpleNamespace(c_int=CInt, byref=lambda value: value)


class LocalLib:
	"""NVDAHelper.localLib's virtual buffer functions, answered from the page."""

	def __init__(self, page):
		self.page = page

	def VBuf_getIdentifierFromControlFieldNode(self, handle, node, docHandle, ID):
		docHandle.value, ID.value = DOC_HANDLE, node.identifier

	def VBuf_getControlFieldNodeWithIdentifier(self, handle, docHandle, ID, node):
		self.page.lookups += 1
		node.value = self.page.byIdentifier(ID) if docHandle == DOC_HANDLE else None

	def VBuf_getFieldNodeOffsets(self, handle, node, start, end):
		start.value, end.value = self.page.offsets()[node.value.identifier]


class NodeHandle:
	"""NVDA's VBufRemote_nodeHandle_t."""

	def __init__(self):
		self.value = None

	def __bool__(self):
		return self.value is not None


class TextInfo:
	"""NVDA's VirtualBufferTextInfo: a range of the page, from one offset to another."""

	def __init__(self, obj, startOffset, endOffset):
		self.obj, self._startOffset, self._endOffset = obj, startOffset, endOffset

	@property
	def text(self):
		return self.obj.page.text(self._startOffset, self._endOffset)

	def copy(self):
		return TextInfo(self.obj, self._startOffset, self._endOffset)

	def expand(self, unit):
		assert unit == UNIT_CHARACTER
		self._endOffset = self._startOffset + 1

	def getTextWithFields(self):
		"""The fields at the range's first character: the element that starts or goes on there, then its text."""
		element = self.obj.page.at(self._startOffset)
		fields = []
		if element is not None:
			fields.append(FieldCommand("controlStart", element.attributes()))
		fields.append(self.text)
		return fields

	def compareEndPoints(self, other, which):
		mine = self._startOffset if which.startswith("start") else self._endOffset
		theirs = other._startOffset if which.endswith("Start") else other._endOffset
		return (mine > theirs) - (mine < theirs)

	def isOverlapping(self, other):
		return self._startOffset < other._endOffset and other._startOffset < self._endOffset


class TextInfoQuickNavItem:
	"""NVDA 2026.2's browseMode.TextInfoQuickNavItem, as far as the Elements List uses it."""

	def __init__(self, itemType, document, textInfo):
		self.textInfo = textInfo
		self.itemType = itemType
		self.document = document

	@property
	def label(self):
		return self.textInfo.text.strip()

	def isChild(self, parent):
		if parent.textInfo.isOverlapping(self.textInfo):
			return True
		return False

	@property
	def isAfterSelection(self):
		caret = self.document.makeTextInfo(POSITION_CARET)
		return self.textInfo.compareEndPoints(caret, "startToStart") > 0

	def _getLabelForProperties(self, labelPropertyGetter):
		"""Shorter than NVDA's: a heading is its text; anything else its name, then its states, as "Issues (10); visited"."""
		content = self.textInfo.text.strip()
		if self.itemType == "heading":
			return content
		name = labelPropertyGetter("name")
		states = labelPropertyGetter("states")
		return "; ".join([name or content] + sorted(states or ()))


# The imitation NVDA's own modules, as NVDA's code below uses them. NVDAHelper's functions answer from each test's page.
browseMode = types.SimpleNamespace(TextInfoQuickNavItem=TextInfoQuickNavItem)
textInfos = types.SimpleNamespace(offsets=types.SimpleNamespace(Offsets=Offsets), FieldCommand=FieldCommand, UNIT_CHARACTER=UNIT_CHARACTER)
VBufRemote_nodeHandle_t = NodeHandle
NVDAHelper = types.SimpleNamespace(localLib=None)


def nvdaCode(source, name):
	"""Compile NVDA's own ``source`` against the imitation NVDA, and give back ``name`` from it."""
	namespace = dict(globals())
	exec(source, namespace)
	return namespace[name]


# NVDA 2026.2's VirtualBufferTextInfo._getControlFieldAttribs and _getOffsetsFromFieldIdentifier, word for word.
for _name in ("_getControlFieldAttribs", "_getOffsetsFromFieldIdentifier"):
	setattr(
		TextInfo,
		_name,
		nvdaCode(
			"def _getControlFieldAttribs(self, docHandle, id):\n"
			"	info = self.copy()\n"
			"	info.expand(textInfos.UNIT_CHARACTER)\n"
			"	for field in reversed(info.getTextWithFields()):\n"
			"		if not (isinstance(field, textInfos.FieldCommand) and field.command == \"controlStart\"):\n"
			"			# Not a control field.\n"
			"			continue\n"
			"		attrs = field.field\n"
			"		if (\n"
			"			int(attrs[\"controlIdentifier_docHandle\"]) == docHandle\n"
			"			and int(attrs[\"controlIdentifier_ID\"]) == id\n"
			"		):\n"
			"			return attrs\n"
			"	raise LookupError\n"
			"\n"
			"def _getOffsetsFromFieldIdentifier(self, docHandle, ID):\n"
			"	node = VBufRemote_nodeHandle_t()\n"
			"	NVDAHelper.localLib.VBuf_getControlFieldNodeWithIdentifier(\n"
			"		self.obj.VBufHandle,\n"
			"		docHandle,\n"
			"		ID,\n"
			"		ctypes.byref(node),\n"
			"	)\n"
			"	if not node:\n"
			"		raise LookupError\n"
			"	start = ctypes.c_int()\n"
			"	end = ctypes.c_int()\n"
			"	NVDAHelper.localLib.VBuf_getFieldNodeOffsets(\n"
			"		self.obj.VBufHandle,\n"
			"		node,\n"
			"		ctypes.byref(start),\n"
			"		ctypes.byref(end),\n"
			"	)\n"
			"	return start.value, end.value\n",
			_name,
		),
	)


# NVDA 2026.2's virtualBuffers.VirtualBufferQuickNavItem, word for word.
VirtualBufferQuickNavItem = nvdaCode(
	"class VirtualBufferQuickNavItem(browseMode.TextInfoQuickNavItem):\n"
	"	def __init__(self, itemType, document, vbufNode, startOffset, endOffset):\n"
	"		textInfo = document.makeTextInfo(textInfos.offsets.Offsets(startOffset, endOffset))\n"
	"		super(VirtualBufferQuickNavItem, self).__init__(itemType, document, textInfo)\n"
	"		docHandle = ctypes.c_int()\n"
	"		ID = ctypes.c_int()\n"
	"		NVDAHelper.localLib.VBuf_getIdentifierFromControlFieldNode(\n"
	"			document.VBufHandle,\n"
	"			vbufNode,\n"
	"			ctypes.byref(docHandle),\n"
	"			ctypes.byref(ID),\n"
	"		)\n"
	"		self.vbufFieldIdentifier = (docHandle.value, ID.value)\n"
	"		self.vbufNode = vbufNode\n"
	"\n"
	"	@property\n"
	"	def obj(self):\n"
	"		return self.document.getNVDAObjectFromIdentifier(*self.vbufFieldIdentifier)\n"
	"\n"
	"	@property\n"
	"	def label(self):\n"
	"		attrs = {}\n"
	"\n"
	"		def propertyGetter(prop):\n"
	"			if not attrs:\n"
	"				# Lazily fetch the attributes the first time they're needed.\n"
	"				# We do this because we don't want to do this if they're not needed at all.\n"
	"				attrs.update(\n"
	"					self.textInfo._getControlFieldAttribs(\n"
	"						self.vbufFieldIdentifier[0],\n"
	"						self.vbufFieldIdentifier[1],\n"
	"					),\n"
	"				)\n"
	"			return attrs.get(prop)\n"
	"\n"
	"		return self._getLabelForProperties(propertyGetter)\n"
	"\n"
	"	def isChild(self, parent):\n"
	"		if self.itemType == \"heading\":\n"
	"			try:\n"
	"				if int(\n"
	"					self.textInfo._getControlFieldAttribs(\n"
	"						self.vbufFieldIdentifier[0],\n"
	"						self.vbufFieldIdentifier[1],\n"
	"					)[\"level\"],\n"
	"				) > int(\n"
	"					parent.textInfo._getControlFieldAttribs(\n"
	"						parent.vbufFieldIdentifier[0],\n"
	"						parent.vbufFieldIdentifier[1],\n"
	"					)[\"level\"],\n"
	"				):\n"
	"					return True\n"
	"			except (KeyError, ValueError, TypeError):\n"
	"				return False\n"
	"		return super(VirtualBufferQuickNavItem, self).isChild(parent)\n",
	"VirtualBufferQuickNavItem",
)


class Tree:
	"""The dialog's wx.TreeCtrl, as far as NVDA's filter uses it."""

	def __init__(self):
		self.items = []
		self.selection = None

	def GetSelection(self):
		if self.selection is None:
			raise RuntimeError("invalid tree item")
		return self.selection

	def GetItemData(self, item):
		return item["data"]

	def DeleteChildren(self, root):
		self.items.clear()
		self.selection = None

	def AppendItem(self, parent, label):
		item = {"label": label, "parent": parent, "data": None}
		self.items.append(item)
		return item

	def SetItemData(self, item, data):
		item["data"] = data

	def ExpandAll(self):
		pass

	def SelectItem(self, item):
		self.selection = item

	def GetFirstChild(self, root):
		return (self.items[0] if self.items else None, None)


class Button:
	def __init__(self, id):
		self.Id, self.Enabled = id, True

	def Enable(self):
		self.Enabled = True

	def Disable(self):
		self.Enabled = False

	def GetId(self):
		return self.Id


class FilterEdit:
	def __init__(self):
		self.value = None

	def ChangeValue(self, value):
		self.value = value


class ElementsListDialog:
	"""NVDA 2026.2's browseMode.ElementsListDialog, without its window: what NVDA's __init__ makes before filling it."""

	Element = __import__("collections").namedtuple("Element", ("item", "parent"))

	def __init__(self, document):
		self.document = document
		self.tree = Tree()
		self.treeRoot = "root"
		self.filterEdit = FilterEdit()
		self.activateButton, self.moveButton = Button(1), Button(2)
		self.AffirmativeId = None
		# NVDA's __init__ ends here: self.initElementType(...), then self.CentreOnScreen().

	def SetAffirmativeId(self, id):
		self.AffirmativeId = id

	def labels(self):
		return [item["label"] for item in self.tree.items]

	def parentLabels(self):
		return {item["label"]: item["parent"]["label"] if isinstance(item["parent"], dict) else None for item in self.tree.items}


# NVDA 2026.2's ElementsListDialog.initElementType and filter, word for word.
for _name in ("initElementType", "filter"):
	setattr(
		ElementsListDialog,
		_name,
		nvdaCode(
			"def initElementType(self, elType):\n"
			"	if elType in (\"link\", \"button\"):\n"
			"		# Links and buttons can be activated.\n"
			"		self.activateButton.Enable()\n"
			"		self.SetAffirmativeId(self.activateButton.GetId())\n"
			"	else:\n"
			"		# No other element type can be activated.\n"
			"		self.activateButton.Disable()\n"
			"		self.SetAffirmativeId(self.moveButton.GetId())\n"
			"\n"
			"	# Gather the elements of this type.\n"
			"	self._elements = []\n"
			"	self._initialElement = None\n"
			"\n"
			"	parentElements = []\n"
			"	isAfterSelection = False\n"
			"	for item in self.document._iterNodesByType(elType):\n"
			"		# Find the parent element, if any.\n"
			"		for parent in reversed(parentElements):\n"
			"			if item.isChild(parent.item):\n"
			"				break\n"
			"			else:\n"
			"				# We're not a child of this parent, so this parent has no more children and can be removed from the stack.\n"
			"				parentElements.pop()\n"
			"		else:\n"
			"			# No parent found, so we're at the root.\n"
			"			# Note that parentElements will be empty at this point, as all parents are no longer relevant and have thus been removed from the stack.\n"
			"			parent = None\n"
			"\n"
			"		element = self.Element(item, parent)\n"
			"		self._elements.append(element)\n"
			"\n"
			"		if not isAfterSelection:\n"
			"			isAfterSelection = item.isAfterSelection\n"
			"			if not isAfterSelection:\n"
			"				# The element immediately preceding or overlapping the caret should be the initially selected element.\n"
			"				# Since we have not yet passed the selection, use this as the initial element.\n"
			"				try:\n"
			"					self._initialElement = self._elements[-1]\n"
			"				except IndexError:\n"
			"					# No previous element.\n"
			"					pass\n"
			"\n"
			"		# This could be the parent of a subsequent element, so add it to the parents stack.\n"
			"		parentElements.append(element)\n"
			"\n"
			"	# Start with no filtering.\n"
			"	self.filterEdit.ChangeValue(\"\")\n"
			"	self.filter(\"\", newElementType=True)\n"
			"\n"
			"def filter(self, filterText, newElementType=False):\n"
			"	# If this is a new element type, use the element nearest the cursor.\n"
			"	# Otherwise, use the currently selected element.\n"
			"	# #8753: wxPython 4 returns \"invalid tree item\" when the tree view is empty, so use initial element if appropriate.\n"
			"	try:\n"
			"		defaultElement = (\n"
			"			self._initialElement if newElementType else self.tree.GetItemData(self.tree.GetSelection())\n"
			"		)\n"
			"	except:  # noqa: E722\n"
			"		defaultElement = self._initialElement\n"
			"	# Clear the tree.\n"
			"	self.tree.DeleteChildren(self.treeRoot)\n"
			"\n"
			"	# Populate the tree with elements matching the filter text.\n"
			"	elementsToTreeItems = {}\n"
			"	defaultItem = None\n"
			"	matched = False\n"
			"	# Do case-insensitive matching by lowering both filterText and each element's text.\n"
			"	filterText = filterText.lower()\n"
			"	for element in self._elements:\n"
			"		label = element.item.label\n"
			"		if filterText and filterText not in label.lower():\n"
			"			continue\n"
			"		matched = True\n"
			"		parent = element.parent\n"
			"		if parent:\n"
			"			parent = elementsToTreeItems.get(parent)\n"
			"		item = self.tree.AppendItem(parent or self.treeRoot, label)\n"
			"		self.tree.SetItemData(item, element)\n"
			"		elementsToTreeItems[element] = item\n"
			"		if element == defaultElement:\n"
			"			defaultItem = item\n"
			"\n"
			"	self.tree.ExpandAll()\n"
			"\n"
			"	if not matched:\n"
			"		# No items, so disable the buttons.\n"
			"		self.activateButton.Disable()\n"
			"		self.moveButton.Disable()\n"
			"		return\n"
			"\n"
			"	# If there's no default item, use the first item in the tree.\n"
			"	self.tree.SelectItem(defaultItem or self.tree.GetFirstChild(self.treeRoot)[0])\n"
			"	# Enable the button(s).\n"
			"	# If the activate button isn't the default button, it is disabled for this element type and shouldn't be enabled here.\n"
			"	if self.AffirmativeId == self.activateButton.Id:\n"
			"		self.activateButton.Enable()\n"
			"	self.moveButton.Enable()\n",
			_name,
		),
	)


class Document:
	"""NVDA's virtual buffer for the page: its tree interceptor, as the Elements List uses it."""

	VBufHandle = 7

	def __init__(self, page, caret=0):
		self.page = page
		self.caret = caret
		#: What the page does after NVDA has found the elements, before it reads their names: called once per listing.
		self.meanwhile = []

	def makeTextInfo(self, position):
		if position == POSITION_CARET:
			return TextInfo(self, self.caret, self.caret)
		return TextInfo(self, position.startOffset, position.endOffset)

	def _iterNodesByType(self, itemType):
		"""NVDA's _iterNodesByType: every element of the type, where it is in the page now; then, the page may change."""
		places = self.page.offsets()
		for element in list(self.page.elements):
			if element.itemType == itemType:
				yield VirtualBufferQuickNavItem(itemType, self, element, *places[element.identifier])
		if self.meanwhile:
			self.meanwhile.pop(0)(self.page)


def alertAbove(page):
	"""GitHub's alert, put above the links: every link after it moves along in NVDA's copy of the page."""
	page.elements.insert(0, ALERT)


def takeAway(identifier):
	def change(page):
		page.elements.remove(page.byIdentifier(identifier))

	return change


#: What the assistant puts in the place of NVDA's own (filter since version 1.18).
WRAPPED = (
	(VirtualBufferQuickNavItem, "label"),
	(VirtualBufferQuickNavItem, "isChild"),
	(ElementsListDialog, "initElementType"),
	(ElementsListDialog, "filter"),
)


class ImitationNvdaTestCase(unittest.TestCase):
	def setUp(self):
		self.page = Page(REPOSITORY + HEADINGS)
		self.document = Document(self.page)
		self.later = []
		wx = types.ModuleType("wx")
		wx.CallLater = lambda delay, function, *args: self.later.append((delay, function, args))
		textInfosPackage = types.ModuleType("textInfos")
		offsets = types.ModuleType("textInfos.offsets")
		offsets.Offsets = Offsets
		textInfosPackage.offsets = offsets
		virtualBuffers = types.ModuleType("virtualBuffers")
		virtualBuffers.VirtualBufferQuickNavItem = VirtualBufferQuickNavItem
		browseModule = types.ModuleType("browseMode")
		browseModule.ElementsListDialog = ElementsListDialog
		self.originals = {
			"label": vars(VirtualBufferQuickNavItem)["label"],
			"isChild": vars(VirtualBufferQuickNavItem)["isChild"],
			"initElementType": vars(ElementsListDialog)["initElementType"],
			"filter": vars(ElementsListDialog)["filter"],
		}
		modules = {"wx": wx, "textInfos": textInfosPackage, "textInfos.offsets": offsets, "virtualBuffers": virtualBuffers, "browseMode": browseModule}
		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		NVDAHelper.localLib = LocalLib(self.page)
		self.addCleanup(self._restore)
		nvdaStubs.spoken.clear()
		elementsList._failed = False

	def _restore(self):
		elementsList.unregister()
		elementsList._replaced.clear()
		elementsList._failed = False
		for owner, name in WRAPPED:
			setattr(owner, name, self.originals[name])

	def openList(self, elType="link"):
		"""NVDA+F7: NVDA makes its dialog, then fills it with the elements of the chosen type."""
		dialog = ElementsListDialog(self.document)
		dialog.initElementType(elType)
		return dialog

	def runLater(self):
		later, self.later[:] = list(self.later), []
		for delay, function, args in later:
			function(*args)


class TestersPageTests(ImitationNvdaTestCase):
	def test_nvdaAloneStopsHalfway(self):
		# 1.15: the alert moves the links along between NVDA finding them and reading their names.
		self.document.meanwhile.append(alertAbove)
		with self.assertRaises(LookupError):
			self.openList()

	def test_theTestersPageIsListed(self):
		elementsList.register()
		self.document.meanwhile.append(alertAbove)
		dialog = self.openList()
		self.assertEqual(
			dialog.labels(),
			["Skip to content; same page", "Homepage; visited", "Issues (10); visited", "Pull requests", "What's new in 1.15; same page", "Updates; same page"],
		)
		self.assertTrue(dialog.activateButton.Enabled and dialog.moveButton.Enabled, "Enter activates the link, and the list closes")
		self.assertEqual(self.later, [], "nothing more to say")

	def test_aLinkIsActivatedWhereItIsNow(self):
		# Activating or moving to an element from the list goes to its offsets in NVDA's copy of the page.
		elementsList.register()
		self.document.meanwhile.append(alertAbove)
		dialog = self.openList()
		self.assertEqual(self.document.meanwhile, [], "the page changed while NVDA filled the list")
		issues = next(element.item for element in dialog._elements if element.item.vbufFieldIdentifier[1] == 11)
		self.assertEqual((issues.textInfo._startOffset, issues.textInfo._endOffset), self.page.offsets()[11])
		self.assertEqual(issues.textInfo.text, "Issues (10)")

	def test_theListIsFilledAgainWhenThePageChanged(self):
		# NVDA fills its list again once an element had moved: the second time, every element is where it is now.
		elementsList.register()
		self.document.meanwhile.append(alertAbove)
		with mock.patch.object(elementsList, "_log") as log:
			with mock.patch.object(self.document, "_iterNodesByType", wraps=self.document._iterNodesByType) as listing:
				dialog = self.openList()
				calls = listing.call_args_list
		self.assertEqual(len(calls), 2, "listed again once")
		self.assertTrue(any("fills it again" in str(call) for call in log().debug.call_args_list))
		for element in dialog._elements:
			self.assertEqual((element.item.textInfo._startOffset, element.item.textInfo._endOffset), self.page.offsets()[element.item.vbufFieldIdentifier[1]])

	def test_headingsUnderEachOther(self):
		self.assertEqual(self.openList("heading").parentLabels(), self.expectedHeadings(), "NVDA alone, on a page that stays still")
		self.document.meanwhile.append(alertAbove)
		self.assertNotEqual(self.openList("heading").parentLabels(), self.expectedHeadings(), "NVDA alone reads headings where they were")
		self.page.elements.remove(ALERT)
		elementsList.register()
		self.assertEqual(self.openList("heading").parentLabels(), self.expectedHeadings(), "a page that stays still")
		self.document.meanwhile.append(alertAbove)
		self.assertEqual(self.openList("heading").parentLabels(), self.expectedHeadings(), "and one that changes meanwhile")

	def test_aHeadingThePageTookAway(self):
		elementsList.register()
		self.document.meanwhile.append(takeAway(52))
		dialog = self.openList("heading")
		self.assertEqual(dialog.parentLabels(), {"jawsMigrator": None, "What's new in 1.15": "jawsMigrator", "Choosing what to import": "What's new in 1.15"})

	def test_headingsWithNvdaAlone(self):
		# NVDA's own isChild for headings lets a LookupError through too: its except has KeyError, ValueError and TypeError.
		items = list(self.document._iterNodesByType("heading"))
		alertAbove(self.page)
		with self.assertRaises(LookupError):
			items[1].isChild(items[0])
		elementsList.register()
		self.assertTrue(items[1].isChild(items[0]), "a level 2 heading comes under the level 1 heading before it")
		self.assertFalse(items[2].isChild(items[1]), "and not under another level 2 heading")

	def expectedHeadings(self):
		return {"jawsMigrator": None, "What's new in 1.15": "jawsMigrator", "Using the assistant": "jawsMigrator", "Choosing what to import": "Using the assistant"}

	def test_aLinkThePageTookAway(self):
		# Its name can't be read anywhere: NVDA lists the page again, without it.
		elementsList.register()
		self.document.meanwhile.append(takeAway(12))
		dialog = self.openList()
		self.assertEqual(dialog.labels(), ["Skip to content; same page", "Homepage; visited", "Issues (10); visited", "What's new in 1.15; same page", "Updates; same page"])
		self.assertEqual(self.later, [])

	# 1.17's test_aPageThatNeverHoldsStill (a link gone at each of three listings left the list empty) is in
	# test_v118_fixes: since 1.18 NVDA lists the links still there.

	def test_aPageThatMovesItsLinksEachTime(self):
		# A page that changes while NVDA lists it, every time, without taking anything away: the list is complete.
		elementsList.register()
		for number in range(elementsList.ATTEMPTS):
			self.document.meanwhile.append(lambda page, number=number: page.elements.insert(0, Element(900 + number, "alert", "Copied!")))
		dialog = self.openList()
		self.assertEqual(len(dialog.labels()), len(REPOSITORY))
		self.assertIn("Issues (10); visited", dialog.labels())
		self.assertEqual(self.later, [], "nothing more to say")

	def test_nothingChangesOnAStillPage(self):
		# NVDA's own list, filled once, without one question more to the page.
		nvdasOwn = self.openList().labels()
		elementsList.register()
		self.page.lookups = 0
		with mock.patch.object(self.document, "_iterNodesByType", wraps=self.document._iterNodesByType) as listing:
			dialog = self.openList()
		self.assertEqual(dialog.labels(), nvdasOwn)
		self.assertEqual(listing.call_count, 1)
		self.assertEqual(self.page.lookups, 0)

	def test_anotherErrorIsLeftToNvda(self):
		# Only a LookupError means the element isn't where NVDA found it.
		elementsList.register()
		item = next(iter(self.document._iterNodesByType("link")))
		with mock.patch.object(TextInfo, "_getControlFieldAttribs", side_effect=RuntimeError("broken")):
			with self.assertRaises(RuntimeError):
				item.label
		self.assertEqual(self.page.lookups, 0)


class RegistrationTests(ImitationNvdaTestCase):
	def test_registerAndUnregister(self):
		elementsList.register()
		self.assertTrue(elementsList.isRegistered())
		for owner, name in WRAPPED:
			self.assertTrue(elementsList._isOurs(vars(owner)[name]), name)
		self.assertIsInstance(vars(VirtualBufferQuickNavItem)["label"], property)
		elementsList.unregister()
		self.assertFalse(elementsList.isRegistered())
		for owner, name in WRAPPED:
			self.assertIs(vars(owner)[name], self.originals[name], name)

	def test_registeredOnce(self):
		elementsList.register()
		elementsList.register()
		self.assertEqual(len(elementsList._replaced), len(WRAPPED))
		elementsList.unregister()
		elementsList.register()
		self.assertEqual(len(elementsList._replaced), len(WRAPPED))
		self.assertIs(vars(ElementsListDialog)["initElementType"].__wrapped__, self.originals["initElementType"], "wrapped once")

	def test_anotherAddonsWrapperStays(self):
		elementsList.register()
		ours = vars(ElementsListDialog)["initElementType"]

		def theirs(self, *args, **kwargs):
			return ours(self, *args, **kwargs)

		theirs.__wrapped__ = ours
		ElementsListDialog.initElementType = theirs
		elementsList.unregister()
		self.assertIs(vars(ElementsListDialog)["initElementType"], theirs, "another add-on's wrapper, put over the assistant's, stays")
		self.document.meanwhile.append(alertAbove)
		with self.assertRaises(LookupError, msg="and the assistant's inside it does nothing once turned off"):
			self.openList()
		elementsList.register()
		self.assertIs(vars(ElementsListDialog)["initElementType"], theirs, "turned on again, it isn't wrapped twice")

	def test_withoutVirtualBuffers(self):
		# NVDA without the class the assistant knows: the dialog is still never left half made.
		del sys.modules["virtualBuffers"].VirtualBufferQuickNavItem
		elementsList.register()
		self.assertTrue(elementsList._failed)
		self.assertTrue(elementsList._isOurs(vars(ElementsListDialog)["initElementType"]))
		self.document.meanwhile.extend([alertAbove])
		dialog = self.openList()
		self.assertEqual(len(dialog.labels()), len(REPOSITORY), "listed again, once the page held still")

	def test_turnedOffAssistantLeavesNvdaAlone(self):
		elementsList.register()
		wrapped = vars(ElementsListDialog)["initElementType"]
		elementsList._enabled = False
		try:
			self.document.meanwhile.append(alertAbove)
			with self.assertRaises(LookupError):
				wrapped(ElementsListDialog(self.document), "link")
		finally:
			elementsList._enabled = True

	def test_relocateWithoutThePage(self):
		item = next(iter(self.document._iterNodesByType("link")))
		self.page.elements.clear()
		self.assertFalse(elementsList.relocate(item), "an element the page took away isn't anywhere")
		item.vbufFieldIdentifier = None
		self.assertFalse(elementsList.relocate(item))


if __name__ == "__main__":
	unittest.main()
