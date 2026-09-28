# Unit tests for version 1.36, from a tester's request (issue 35, "Another thing to consider"): "Have it run several test
# on several sites including sites like www.amazon.com ETC. see if there are differences. if there are major
# differences do we let them alone or fix them?", and "Note it should do tests with both Jaws and NVDA."
# JAWS 2026 and NVDA 2026.2 with the assistant 1.35 (in a settings folder of its own, with the settings a migration of
# JAWS gives NVDA) were run on the maintainer's computer, on Edge 154, with copies of Amazon's home page, Amazon's search
# results for "usb c cable", Wikipedia's "Screen reader", BBC News, a BBC News article and the assistant's GitHub page,
# the same 59 keys on each. JAWS said, for its quick keys:
#     B   "Delivering to Williamstown 17098 Update location Button"          (Amazon)
#     C   "Search in Combo box collapsed All Departments ..."                 (Amazon)
#     I   "Link Donate"                                                       (Wikipedia)
#     G   "British Broadcasting Corporation Link Graphic"                     (BBC)
#     L   "list of 6 items"                                                   (GitHub)
#     R   "Global navigation region"                                          (GitHub)
#     T   "table with 3 columns and 8 rows | Folders and files | Column 1, Row 1 | Name"   (GitHub)
# NVDA said every landmark, region and list the move entered first:
#     B   "banner region, Primary, navigation region, Delivering to Williamstown 17098, Update location, button"
#     C   "banner region, Primary, navigation region, search region, Search in, combo box, collapsed, ..."
#     I   "banner region, Personal tools, navigation region, list of 3 items, Donate, link"
#     G   "banner region, British Broadcasting Corporation, graphic, link"
#     L   "banner region, Global, navigation region, list of 6 items, Platform, button, collapsed"
#     D   "banner region, Primary, navigation region, Amazon, link"
#     T   "main region, Folders and files, table, with 8 rows and 3 columns, row 1, column 1, Name"
# The assistant had done this for H (1.13) and E (1.31) only. The maintainer chose to have every quick key say only
# what it moves to (quick navigation wrapping and JAWS's words for tables were left as NVDA has them).
# - quickNavHeadings: on a web page (a virtual buffer, where an item has the page's identifier for its element),
#   quick navigation to anything leaves out the containers and table cells around it; the element and what is in it
#   are said as NVDA says them.
# The imitation NVDA is NVDA 2026.2's own code, word for word, as tests/test_v134_webRegions.py and the tests it builds
# on took it (speakTextInfo, getTextInfoSpeech, getControlFieldSpeech, TextInfo.getControlFieldSpeech,
# TextInfoQuickNavItem.report, the tester's settings). The assistant's code (quickNavHeadings, webRegions) is the real one.
# Run: python -m unittest tests.test_v136_quickNavItems -v

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v134_webRegions as v134  # noqa: E402

v131, v126, v125 = v134.v131, v134.v126, v134.v125

from jawsMigrator import quickNavHeadings, webRegions  # noqa: E402

Role, State, OutputReason = v126.Role, v126.State, v126.OutputReason
spoken = v126.spoken
field, landmark, link = v126.field, v134.landmark, v134.link


class VirtualBufferQuickNavItem(v125.VirtualBufferQuickNavItem):
	"""NVDA's virtualBuffers.VirtualBufferQuickNavItem: TextInfoQuickNavItem's report, and the page's identifier for the
	element it moved to, as NVDA 2026.2 sets it in __init__ (VBuf_getIdentifierFromControlFieldNode gives two ints)."""

	def __init__(self, itemType, document, textInfo, uniqueID):
		super().__init__(itemType, document, textInfo, OutputReason.QUICKNAV)
		self.vbufFieldIdentifier = (v126.EDGE_WINDOW, uniqueID)


# The pages' containers, as Edge gives them to NVDA's virtual buffer.
BANNER = landmark("banner", 1)
PRIMARY_NAV = landmark("navigation", 2, name="Primary")
SEARCH = landmark("search", 3)
PERSONAL_NAV = landmark("navigation", 4, name="Personal tools")
LIST_3 = field(Role.LIST, 5, (State.READONLY,), _childcontrolcount=3)
GLOBAL_NAV = landmark("navigation", 6, name="Global")
LIST_6 = field(Role.LIST, 7, (State.READONLY,), _childcontrolcount=6)
MAIN = landmark("main", 8)
PRIME_LIST = field(Role.LIST, 9, (State.READONLY,), _childcontrolcount=8)

#: Each quick key's item: (item type, the element's identifier, the line as Edge gives it).
ITEMS = {
	# Amazon: the location button in the banner's Primary navigation.
	"button": ("button", 20, [BANNER, PRIMARY_NAV, field(Role.BUTTON, 20, (State.FOCUSABLE,)), "Delivering to Williamstown 17098 Update location"]),
	# Amazon: the search box's department list, in the search landmark in the banner's navigation.
	"combo": ("comboBox", 21, [BANNER, PRIMARY_NAV, SEARCH, field(Role.COMBOBOX, 21, (State.FOCUSABLE, State.COLLAPSED), name="Search in"), "All Departments"]),
	# Wikipedia: the first item of the Personal tools list in the banner.
	"listItem": ("listItem", 22, [BANNER, PERSONAL_NAV, LIST_3, field(Role.LISTITEM, 22), link(23), "Donate"]),
	# Amazon: a graphic in a link, in a list in the main landmark.
	"graphic": ("graphic", 24, [MAIN, PRIME_LIST, field(Role.LISTITEM, 25), link(26), field(Role.GRAPHIC, 24, name="Prime Big Deals drop Oct 6-7 Exclusively for members")]),
	# GitHub: the list of the global navigation in the banner; the line is its first button.
	"list": ("list", 7, [BANNER, GLOBAL_NAV, LIST_6, field(Role.LISTITEM, 27), field(Role.BUTTON, 28, (State.FOCUSABLE, State.COLLAPSED)), "Platform"]),
	# Amazon: D to the Primary navigation, in the banner; the line is its first link.
	"landmark": ("landmark", 2, [BANNER, PRIMARY_NAV, link(29), "Amazon"]),
	# The same link, with K.
	"link": ("link", 29, [BANNER, PRIMARY_NAV, link(29), "Amazon"]),
}


class QuickNavCase(unittest.TestCase):
	def setUp(self):
		v134.patchNvda(self)
		self.addCleanup(self._restore)
		self.page = v134.Page()

	def _restore(self):
		quickNavHeadings.unregister()
		quickNavHeadings._replaced.clear()
		quickNavHeadings._failed = False
		quickNavHeadings._local.reports = None

	def asTheTesterHasIt(self):
		"""The tester's assistant, 1.35: web regions in JAWS's words, headings and edit fields without what they are in."""
		webRegions.register()
		quickNavHeadings.register()

	def press(self, name, identified=True):
		"""The quick key to the item: NVDA's _quickNavScript makes the item, and its report says it (a page that has said
		nothing yet: NVDA's cache of what browse mode's cursor is in is empty)."""
		itemType, uniqueID, parts = ITEMS[name]
		self.page._speakTextInfoState = None
		info = v134.ChromeVBufTextInfo(self.page, parts)
		if identified:
			item = VirtualBufferQuickNavItem(itemType, self.page, info, uniqueID)
		else:
			item = v125.VirtualBufferQuickNavItem(itemType, self.page, info, OutputReason.QUICKNAV)
		spoken.clear()
		item.report()
		self.assertEqual(len(spoken), 1, spoken)
		return spoken[0]


class QuickKeysTests(QuickNavCase):
	def test_nvdaSaidWhatTheRunShowed(self):
		webRegions.register()
		self.assertEqual(self.press("button"), ["banner region", "Primary", "navigation region", "Delivering to Williamstown 17098 Update location", "button"])
		self.assertEqual(self.press("combo"), ["banner region", "Primary", "navigation region", "search region", "Search in", "combo box", "collapsed", "All Departments"])
		self.assertEqual(self.press("listItem"), ["banner region", "Personal tools", "navigation region", "list of 3 items", "Donate", "link"])
		self.assertEqual(self.press("landmark"), ["banner region", "Primary", "navigation region", "Amazon", "link"])

	def test_onlyWhatQuickNavigationMovesTo(self):
		self.asTheTesterHasIt()
		# JAWS: "Delivering to Williamstown 17098 Update location Button", "Search in Combo box collapsed", "Link Donate".
		self.assertEqual(self.press("button"), ["Delivering to Williamstown 17098 Update location", "button"])
		self.assertEqual(self.press("combo"), ["Search in", "combo box", "collapsed", "All Departments"])
		self.assertEqual(self.press("listItem"), ["Donate", "link"])
		self.assertEqual(self.press("link"), ["Amazon", "link"])

	def test_aLinkAroundAGraphicIsStillSaid(self):
		# JAWS: "... Link Graphic": a link isn't a container; the list and the main region are.
		self.asTheTesterHasIt()
		self.assertEqual(self.press("graphic"), ["Prime Big Deals drop Oct 6-7 Exclusively for members", "graphic", "link"])

	def test_aContainerItIsItselfIsSaid(self):
		# L: the list itself and what is in it, without the navigation and banner around it (JAWS: "list of 6 items").
		self.asTheTesterHasIt()
		self.assertEqual(self.press("list"), ["list of 6 items", "Platform", "button", "collapsed"])
		# D: the landmark itself, its name and its first line, without the banner (JAWS: "Primary navigation region").
		self.assertEqual(self.press("landmark"), ["Primary", "navigation region", "Amazon", "link"])

	def test_withoutWebRegionsNvdasWordsAreKept(self):
		quickNavHeadings.register()
		self.assertEqual(self.press("listItem"), ["Donate", "link"])
		self.assertEqual(self.press("list"), ["list", "with 6 items", "Platform", "button", "collapsed"])

	def test_anItemWithoutThePagesIdentifierIsAsBefore(self):
		# Quick navigation outside a virtual buffer (Word, or a page read through UI Automation) has no identifier.
		self.asTheTesterHasIt()
		self.assertEqual(self.press("button", identified=False), ["banner region", "Primary", "navigation region", "Delivering to Williamstown 17098 Update location", "button"])

	def say(self, parts, reason):
		"""The arrow keys (the line, for the caret) or Tab (for the focus) to ``parts``, as browse mode says them."""
		self.page._speakTextInfoState = None
		spoken.clear()
		info = v134.ChromeVBufTextInfo(self.page, parts)
		if reason == OutputReason.CARET:
			v126.speechPackage.speakTextInfo(info, unit=v126.textInfos.UNIT_LINE, reason=reason)
		else:
			v126.speechPackage.speakTextInfo(info, reason=reason)
		return spoken[0]

	def test_theArrowKeysAndTabAreAsBefore(self):
		webRegions.register()
		reasons = (OutputReason.CARET, OutputReason.FOCUS)
		before = {(name, reason): self.say(ITEMS[name][2], reason) for name in ITEMS for reason in reasons}
		quickNavHeadings.register()
		for name in ITEMS:
			for reason in reasons:
				self.assertEqual(self.say(ITEMS[name][2], reason), before[name, reason], (name, reason))
		# Tab to the button in the banner still says the banner and the navigation (JAWS: "BannerRegion", "Primary
		# NavigationRegion"), and reading says the navigation and its end, as before.
		self.assertEqual(self.say(ITEMS["button"][2], OutputReason.FOCUS), ["banner region", "Primary", "navigation region", "Delivering to Williamstown 17098 Update location", "button"])
		self.assertEqual(self.say(ITEMS["button"][2], OutputReason.CARET), ["Primary", "navigation region", "button", "Delivering to Williamstown 17098 Update location"])

	def test_turnedOffNvdasOwnIsBack(self):
		self.asTheTesterHasIt()
		quickNavHeadings.unregister()
		self.assertEqual(self.press("button"), ["banner region", "Primary", "navigation region", "Delivering to Williamstown 17098 Update location", "button"])


class IdentifierTests(unittest.TestCase):
	def test_itemField(self):
		item = type("Item", (), {"vbufFieldIdentifier": (65802, 20)})()
		self.assertEqual(quickNavHeadings.itemField(item), (65802, 20))
		self.assertIsNone(quickNavHeadings.itemField(object()))
		self.assertIsNone(quickNavHeadings.itemField(type("Item", (), {"vbufFieldIdentifier": ("x", 1)})()))

	def test_fieldIdentifier(self):
		# NVDA's virtual buffer gives a field's identifier as text.
		self.assertEqual(quickNavHeadings.fieldIdentifier({"controlIdentifier_docHandle": "65802", "controlIdentifier_ID": "20"}), (65802, 20))
		self.assertIsNone(quickNavHeadings.fieldIdentifier({"role": Role.BUTTON}))
		self.assertIsNone(quickNavHeadings.fieldIdentifier(None))


if __name__ == "__main__":
	unittest.main()
