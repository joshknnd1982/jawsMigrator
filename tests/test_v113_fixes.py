# Unit tests for version 1.13, from a tester's reports on version 1.12 (issues 1, 4, 6, 7 and 8):
# - quickNavHeadings: pressing H, NVDA said "main landmark" before a heading ("It identifies headings
#   as main landmark. JAWS doesn't do this"), and 1.12 had put the level before the heading's text,
#   where JAWS says the text first ("Feels to good to be true, visited, heading level 2");
# - listCoordinates: File Explorer said "Data (D:), row 2, column 1, 3 of 3", where JAWS says "Data (D:)";
# - autoFormsMode: Tab from GitHub's title box went to the editor's "Write" tab, NVDA stayed in focus mode,
#   and the letters typed there went to the page, whose S opened its search; the editor's toolbar, next,
#   is in focus mode too. JAWS's virtual cursor stays on both;
# - backspaceEcho: Backspace in Notepad holding a 3-million-character log said nothing: NVDA gave up
#   waiting for the caret after 100 ms, then Notepad deleted. JAWS says the character at once.
# The imitation NVDA below does what NVDA 2026.2 does, as far as these go: speech.getControlFieldSpeech
# with _shouldSpeakContentFirst (landmarks, regions and lists say what they are as NVDA enters them,
# articles, headings and links after their text), speakTextInfo with its notes of the fields NVDA is in,
# browseMode's TextInfoQuickNavItem.report, speech.speech._objectSpeech_calculateAllowedProps, and
# BrowseModeTreeInterceptor.shouldPassThrough with inputCore.decide_executeGesture. The pages are the tester's, as the logs have them. The
# assistant's register, unregister and wrappers are the real ones.
# Run: python -m unittest tests.test_v113_fixes -v

import enum
import functools
import importlib
import importlib.util
import os
import sys
import threading
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import autoFormsMode, backspaceEcho, listCoordinates, quickNavHeadings, state  # noqa: E402


class OutputReason(enum.Enum):
	FOCUS = "focus"
	QUICKNAV = "quickNav"
	CARET = "caret"
	QUERY = "query"


class Role(enum.Enum):
	LANDMARK = "landmark"
	REGION = "region"
	LIST = "list"
	LISTITEM = "list item"
	ARTICLE = "article"
	SECTION = "section"
	TABLE = "table"
	TABLECELL = "cell"
	HEADING = "heading"
	LINK = "link"
	BUTTON = "button"
	EDITABLETEXT = "edit"
	TAB = "tab"
	RADIOBUTTON = "radio button"
	TOGGLEBUTTON = "toggle button"
	MENUBUTTON = "menu button"
	CHECKBOX = "check box"

	@property
	def displayString(self):
		return self.value


class State(enum.Enum):
	VISITED = "visited"
	INTERNAL_LINK = "same page"
	EDITABLE = "editable"
	READONLY = "read only"


CONTAINER, SINGLELINE, CELL, LAYOUT = "container", "singleLine", "cell", "layout"


class Field(dict):
	"""A control field of a browse mode document (textInfos.ControlField)."""

	PRESCAT_CONTAINER, PRESCAT_SINGLELINE, PRESCAT_CELL, PRESCAT_LAYOUT = CONTAINER, SINGLELINE, CELL, LAYOUT

	def getPresentationCategory(self, ancestors, formatConfig, reason=None, extraDetail=False):
		"""ControlField.getPresentationCategory, for these roles."""
		role = self["role"]
		if role in (Role.LANDMARK, Role.REGION, Role.LIST, Role.ARTICLE, Role.TABLE):
			return CONTAINER
		if role == Role.TABLECELL:
			return CELL
		if role in (Role.HEADING, Role.LINK, Role.BUTTON, Role.EDITABLETEXT):
			return SINGLELINE
		return LAYOUT


def field(role, **attributes):
	return Field(role=role, states=attributes.pop("states", set()), **attributes)


def _shouldSpeakContentFirst(reason, role, presCat, attrs, tableID, states):
	"""NVDA 2026.2's speech._shouldSpeakContentFirst."""
	never = (Role.EDITABLETEXT, Role.LIST, Role.LANDMARK, Role.REGION)
	return (
		reason in [OutputReason.FOCUS, OutputReason.QUICKNAV]
		and (presCat != CONTAINER or role == Role.ARTICLE)
		and role not in never
		and not tableID
		and State.EDITABLE not in states
	)


def fieldWords(attrs, reason):
	"""What NVDA says a field is: "main landmark"; "Community actions", "region"; "list", "with 2 items"; "heading", "level 2"."""
	role = attrs["role"]
	named = [attrs["name"]] if attrs.get("name") and reason in (OutputReason.FOCUS, OutputReason.QUICKNAV) else []
	if role == Role.LANDMARK:
		return named + [f"{attrs['landmark']} landmark"]
	if role == Role.TABLECELL:
		return [f"row {attrs['row']}", f"column {attrs['column']}"]
	words = named + [state.value for state in (State.VISITED, State.INTERNAL_LINK) if state in attrs["states"]]
	words.append(role.value)
	if attrs.get("items"):
		words.append(f"with {attrs['items']} items")
	if attrs.get("level"):
		words.append(f"level {attrs['level']}")
	if attrs.get("description") and reason in (OutputReason.FOCUS, OutputReason.QUICKNAV):
		words.append(attrs["description"])
	return words


def getControlFieldSpeech(attrs, ancestorAttrs, fieldType, formatConfig=None, extraDetail=False, reason=None):
	"""NVDA 2026.2's speech.getControlFieldSpeech, as far as the order goes."""
	presCat = attrs.getPresentationCategory(ancestorAttrs, formatConfig, reason=reason)
	if presCat == LAYOUT:
		return []
	role, states = attrs["role"], attrs["states"]
	if role == Role.TABLECELL:
		return fieldWords(attrs, reason) if fieldType == "start_addedToControlFieldStack" else []
	speakContentFirst = _shouldSpeakContentFirst(reason, role, presCat, attrs, None, states)
	speakWithinForLine = presCat == SINGLELINE
	if (
		(speakContentFirst and fieldType in ("end_relative", "end_inControlFieldStack"))
		or (not speakContentFirst and fieldType in ("start_addedToControlFieldStack", "start_relative"))
		or (speakWithinForLine and not speakContentFirst and fieldType == "start_inControlFieldStack")
	):
		return fieldWords(attrs, reason)
	return []


spoken = []


def speakTextInfo(info, reason=OutputReason.QUERY, **kwargs):
	"""NVDA 2026.2's speech.speakTextInfo (getTextInfoSpeech): the fields NVDA was in, then the new ones, the text, and the ends."""
	document, fields = info.obj, info.fields
	previous = getattr(document, "_speakTextInfoState", None) or []
	common = 0
	for old, new in zip(previous, fields):
		if old.get("uniqueID") != new.get("uniqueID"):
			break
		common += 1
	sequence = []
	for count in range(common):
		sequence += info.getControlFieldSpeech(fields[count], fields[:count], "start_inControlFieldStack", None, False, reason)
	for count in range(common, len(fields)):
		sequence += info.getControlFieldSpeech(fields[count], fields[:count], "start_addedToControlFieldStack", None, False, reason)
	sequence.append(info.text)
	# Every field NVDA entered is now one it is in, so each says what it is here if it says it after its text.
	for count in reversed(range(len(fields))):
		sequence += info.getControlFieldSpeech(fields[count], fields[:count], "end_inControlFieldStack", None, False, reason)
	document._speakTextInfoState = list(fields)
	spoken.append(sequence)
	return True


class TextInfo:
	"""A part of the page: the fields it is in, and its text (textInfos.TextInfo)."""

	def __init__(self, obj, fields, text):
		self.obj, self.fields, self.text = obj, fields, text

	def getControlFieldSpeech(self, attrs, ancestorAttrs, fieldType, formatConfig=None, extraDetail=False, reason=None):
		# textInfos.TextInfo.getControlFieldSpeech goes through the speech package, with its arguments in order.
		return sys.modules["speech"].getControlFieldSpeech(attrs, ancestorAttrs, fieldType, formatConfig, extraDetail, reason)


class TextInfoQuickNavItem:
	"""NVDA 2026.2's browseMode.TextInfoQuickNavItem."""

	def __init__(self, itemType, document, textInfo, outputReason=OutputReason.QUICKNAV):
		self.itemType, self.document, self.textInfo, self.outputReason = itemType, document, textInfo, outputReason

	def report(self, readUnit=None):
		sys.modules["speech"].speakTextInfo(self.textInfo, reason=self.outputReason)


class VirtualBufferQuickNavItem(TextInfoQuickNavItem):
	"""virtualBuffers.VirtualBufferQuickNavItem, what Edge and Chrome's quick navigation makes: it has NVDA's report."""


#: NVDA's own functions, to check what the assistant puts in their place and gives back.
NVDA_REPORT = vars(TextInfoQuickNavItem)["report"]
NVDA_FIELD_SPEECH = getControlFieldSpeech


class Document:
	"""A browse mode document."""


VISITED = {State.VISITED}
SAME_PAGE = {State.INTERNAL_LINK}


def testersPages():
	"""The tester's pages, as NVDA read them with H in the logs of issues 1 and 8."""
	avMain = field(Role.LANDMARK, landmark="main", uniqueID=1)
	mlbBanner = field(Role.LANDMARK, landmark="banner", uniqueID=2)
	mlbMain = field(Role.LANDMARK, landmark="main", uniqueID=3)
	rdRegion = field(Role.REGION, name="Community actions", uniqueID=4)
	rdMain = field(Role.LANDMARK, landmark="main", uniqueID=5)
	rdList = field(Role.LIST, items=2, uniqueID=6)
	rdArticle = field(Role.ARTICLE, uniqueID=7)
	return {
		"Welcome to AppleVis": [avMain, field(Role.HEADING, level=1, uniqueID=10)],
		"Getting Started": [avMain, field(Role.HEADING, level=2, uniqueID=11)],
		"MLB Trade Rumors": [mlbBanner, field(Role.HEADING, level=1, uniqueID=12), field(Role.LINK, states=SAME_PAGE, description="Home", uniqueID=13)],
		"Giants Claim Camilo Doval": [mlbMain, field(Role.SECTION, uniqueID=14), field(Role.HEADING, level=2, uniqueID=15), field(Role.LINK, uniqueID=16)],
		"r/Visible": [rdRegion, field(Role.HEADING, level=1, uniqueID=17)],
		# The link holds the heading here: the tester's log said "visited, link" before "heading" with 1.12.
		"New speedtest megathread": [rdMain, rdList, field(Role.LISTITEM, uniqueID=18), field(Role.LINK, states=VISITED, uniqueID=19), field(Role.HEADING, level=2, uniqueID=20)],
		"My only regret joining Visible": [rdMain, rdArticle, field(Role.HEADING, level=2, uniqueID=21), field(Role.LINK, states=VISITED, description="Author: u/Fuspo14 11 hr. ago", uniqueID=22)],
		"12 comments": [rdMain, rdArticle, field(Role.HEADING, level=3, uniqueID=23)],
		"Scores": [avMain, field(Role.TABLE, uniqueID=24), field(Role.TABLECELL, row=1, column=2, uniqueID=25), field(Role.HEADING, level=3, uniqueID=26)],
	}


class QuickNavHeadingsTests(unittest.TestCase):
	def setUp(self):
		self.browseMode = types.ModuleType("browseMode")
		self.browseMode.TextInfoQuickNavItem = TextInfoQuickNavItem
		self.speech = types.ModuleType("speech")
		self.speech.getControlFieldSpeech = getControlFieldSpeech
		self.speech.speakTextInfo = speakTextInfo
		controlTypes = types.ModuleType("controlTypes")
		controlTypes.OutputReason, controlTypes.Role, controlTypes.State = OutputReason, Role, State
		config = types.ModuleType("config")
		config.conf = {"documentFormatting": {"reportLandmarks": True}}
		modules = mock.patch.dict(sys.modules, {"browseMode": self.browseMode, "speech": self.speech, "controlTypes": controlTypes, "config": config})
		modules.start()
		self.addCleanup(modules.stop)
		self.addCleanup(self._restoreNvda)
		self.page = Document()
		self.parts = testersPages()
		spoken.clear()
		quickNavHeadings._failed = False

	def _restoreNvda(self):
		quickNavHeadings.unregister()
		# Whatever a test put over NVDA's own goes, so the next test starts from NVDA as it is.
		self.speech.getControlFieldSpeech = getControlFieldSpeech
		TextInfoQuickNavItem.report = NVDA_REPORT
		quickNavHeadings._replaced.clear()
		quickNavHeadings._failed = False

	def part(self, text):
		return TextInfo(self.page, self.parts[text], text)

	def press(self, itemType, text, itemClass=VirtualBufferQuickNavItem, reason=OutputReason.QUICKNAV):
		"""Quick navigation to the item: NVDA's _quickNavScript reports it."""
		spoken.clear()
		itemClass(itemType, self.page, self.part(text), reason).report()
		self.assertEqual(len(spoken), 1)
		return spoken[0]

	def arrow(self, text):
		spoken.clear()
		speakTextInfo(self.part(text), reason=OutputReason.CARET)
		return spoken[0]

	def fresh(self):
		self.page._speakTextInfoState = None

	# -- the tester's reports ----------------------------------------------------------------------

	def test_nvdaAloneSaysWhatAHeadingIsInFirst(self):
		self.fresh()
		self.assertEqual(self.press("heading", "Welcome to AppleVis"), ["main landmark", "Welcome to AppleVis", "heading", "level 1"])
		self.fresh()
		self.assertEqual(self.press("heading", "r/Visible"), ["Community actions", "region", "r/Visible", "heading", "level 1"])
		self.assertEqual(
			self.press("heading", "New speedtest megathread"),
			["main landmark", "list", "with 2 items", "New speedtest megathread", "heading", "level 2", "visited", "link"],
		)
		self.fresh()
		self.assertEqual(
			self.press("heading", "My only regret joining Visible"),
			["main landmark", "My only regret joining Visible", "visited", "link", "Author: u/Fuspo14 11 hr. ago", "heading", "level 2", "article"],
			"an article is said after its heading, as NVDA reads it text first",
		)

	def test_quickNavigationSaysTheHeadingAlone(self):
		quickNavHeadings.register()
		self.fresh()
		self.assertEqual(self.press("heading", "Welcome to AppleVis"), ["Welcome to AppleVis", "heading", "level 1"], "issue 1: no main landmark")
		self.assertEqual(self.press("heading", "Getting Started"), ["Getting Started", "heading", "level 2"])
		self.fresh()
		self.assertEqual(self.press("heading", "MLB Trade Rumors"), ["MLB Trade Rumors", "same page", "link", "Home", "heading", "level 1"])
		self.assertEqual(self.press("heading", "Giants Claim Camilo Doval"), ["Giants Claim Camilo Doval", "link", "heading", "level 2"])
		self.fresh()
		self.assertEqual(self.press("heading", "r/Visible"), ["r/Visible", "heading", "level 1"], "no Community actions region")
		self.assertEqual(
			self.press("heading", "New speedtest megathread"),
			["New speedtest megathread", "heading", "level 2", "visited", "link"],
			"no main landmark or list; the link around the heading stays",
		)
		self.fresh()
		self.assertEqual(
			self.press("heading", "My only regret joining Visible"),
			["My only regret joining Visible", "visited", "link", "Author: u/Fuspo14 11 hr. ago", "heading", "level 2"],
			"issue 8: the text first, as JAWS says it; no article after it",
		)
		self.assertEqual(self.press("heading", "12 comments"), ["12 comments", "heading", "level 3"], "the same article again: still not said")
		self.fresh()
		self.assertEqual(self.press("heading3", "Scores"), ["Scores", "heading", "level 3"], "no table, no row and column")

	def test_everyWayQuickNavigationReportsAHeading(self):
		quickNavHeadings.register()
		# 1 to 9 move to a heading of that level; NVDA's own TextInfoQuickNavItem and the Elements List's Move to report the same.
		for itemType in ["heading"] + [f"heading{level}" for level in range(1, 10)]:
			for itemClass in (VirtualBufferQuickNavItem, TextInfoQuickNavItem):
				self.fresh()
				self.assertEqual(self.press(itemType, "Welcome to AppleVis", itemClass), ["Welcome to AppleVis", "heading", "level 1"], itemType)

	def test_everythingElseKeepsWhatItIsIn(self):
		quickNavHeadings.register()
		for itemType in ("link", "landmark", "formField", "button", "headingless", "", None):
			self.fresh()
			self.assertEqual(
				self.press(itemType, "Giants Claim Camilo Doval"),
				["main landmark", "Giants Claim Camilo Doval", "link", "heading", "level 2"],
				f"K, D and the other quick navigation keys: {itemType!r}",
			)
		self.fresh()
		self.assertEqual(
			self.press("heading", "Welcome to AppleVis", reason=OutputReason.FOCUS),
			["main landmark", "Welcome to AppleVis", "heading", "level 1"],
			"a heading reported as the focus",
		)
		self.fresh()
		self.assertEqual(self.arrow("Welcome to AppleVis"), ["main landmark", "heading", "level 1", "Welcome to AppleVis"], "the arrow keys")
		self.fresh()
		self.press("heading", "Welcome to AppleVis")
		self.assertEqual(self.arrow("Getting Started"), ["heading", "level 2", "Getting Started"], "after H, NVDA knows it is in the landmark")

	def test_headingItemTypes(self):
		for itemType in ["heading"] + [f"heading{level}" for level in range(1, 10)]:
			self.assertTrue(quickNavHeadings.isHeading(types.SimpleNamespace(itemType=itemType)), itemType)
		for itemType in ("link", "headingless", "headings", "Heading", "", None, 2):
			self.assertFalse(quickNavHeadings.isHeading(types.SimpleNamespace(itemType=itemType)), itemType)
		self.assertFalse(quickNavHeadings.isHeading(object()), "an item without a type")

	def test_version112sOrderIsGone(self):
		# 1.12 put a heading's level before its text: JAWS says the text first (issue 8).
		with self.assertRaises(ImportError):
			importlib.import_module("jawsMigrator.headingOrder")
		self.assertNotIn("sayHeadingLevelFirst", state.DEFAULTS)
		quickNavHeadings.register()
		self.fresh()
		said = self.press("heading", "Giants Claim Camilo Doval")
		self.assertLess(said.index("Giants Claim Camilo Doval"), said.index("heading"))

	# -- the setting --------------------------------------------------------------------------

	def test_onUnlessTurnedOff(self):
		self.assertTrue(quickNavHeadings.wanted({}))
		self.assertTrue(quickNavHeadings.wanted({quickNavHeadings.STATE_KEY: True}))
		self.assertFalse(quickNavHeadings.wanted({quickNavHeadings.STATE_KEY: False}))
		self.assertFalse(quickNavHeadings.wanted(None))
		self.assertIs(state.DEFAULTS[quickNavHeadings.STATE_KEY], True)

	def test_turnedOffNvdaHasItsOwnBack(self):
		quickNavHeadings.register()
		self.assertTrue(quickNavHeadings.isRegistered())
		self.assertIs(self.speech.getControlFieldSpeech.__wrapped__, getControlFieldSpeech)
		self.assertIs(TextInfoQuickNavItem.report.__wrapped__, NVDA_REPORT)
		self.assertNotIn("report", vars(VirtualBufferQuickNavItem), "subclasses keep using the one report")
		quickNavHeadings.unregister()
		self.assertFalse(quickNavHeadings.isRegistered())
		self.assertIs(self.speech.getControlFieldSpeech, getControlFieldSpeech)
		self.assertIs(TextInfoQuickNavItem.report, NVDA_REPORT)
		self.fresh()
		self.assertEqual(self.press("heading", "Welcome to AppleVis"), ["main landmark", "Welcome to AppleVis", "heading", "level 1"])
		quickNavHeadings.register()
		quickNavHeadings.register()
		self.assertIs(self.speech.getControlFieldSpeech.__wrapped__, getControlFieldSpeech, "registered twice, wrapped once")
		self.fresh()
		self.assertEqual(self.press("heading", "Welcome to AppleVis"), ["Welcome to AppleVis", "heading", "level 1"])

	def test_classicSpeechsWrapperOverTheAssistants(self):
		# ClassicSpeech's heading continuity wraps the same speech.getControlFieldSpeech after the assistant starts.
		quickNavHeadings.register()
		ours = self.speech.getControlFieldSpeech
		calls = []

		@functools.wraps(ours)
		def classicSpeech(attrs, ancestors, fieldType, *args, **kwargs):
			calls.append(fieldType)
			return ours(attrs, ancestors, fieldType, *args, **kwargs)

		self.speech.getControlFieldSpeech = classicSpeech
		self.fresh()
		self.assertEqual(self.press("heading", "Welcome to AppleVis"), ["Welcome to AppleVis", "heading", "level 1"])
		self.assertTrue(calls)
		quickNavHeadings.unregister()
		self.assertIs(self.speech.getControlFieldSpeech, classicSpeech, "the other add-on's wrapper stays")
		self.fresh()
		self.assertEqual(self.press("heading", "Welcome to AppleVis"), ["main landmark", "Welcome to AppleVis", "heading", "level 1"], "the assistant's, still inside it, does nothing")
		quickNavHeadings.register()
		self.assertIs(self.speech.getControlFieldSpeech, classicSpeech, "and the assistant doesn't wrap it a second time")
		self.fresh()
		self.assertEqual(self.press("heading", "Welcome to AppleVis"), ["Welcome to AppleVis", "heading", "level 1"])

	def test_nvdaReloadsItsPlugins(self):
		# NVDA+Control+F3 loads the add-on again, a new copy of the module, while another add-on's wrapper
		# still holds the old copy's report, which does nothing any more.
		quickNavHeadings.register()
		ours = TextInfoQuickNavItem.report

		@functools.wraps(ours)
		def otherAddon(item, *args, **kwargs):
			return ours(item, *args, **kwargs)

		TextInfoQuickNavItem.report = otherAddon
		quickNavHeadings.unregister()
		spec = importlib.util.spec_from_file_location("jawsMigrator.quickNavHeadingsLoadedAgain", quickNavHeadings.__file__)
		again = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(again)
		again.register()
		try:
			self.assertIsNot(TextInfoQuickNavItem.report, otherAddon, "the new copy puts its own in place")
			self.fresh()
			self.assertEqual(self.press("heading", "Welcome to AppleVis"), ["Welcome to AppleVis", "heading", "level 1"])
		finally:
			again.unregister()
		self.assertIs(TextInfoQuickNavItem.report, otherAddon)
		self.fresh()
		self.assertEqual(self.press("heading", "Welcome to AppleVis"), ["main landmark", "Welcome to AppleVis", "heading", "level 1"])

	# -- whatever goes wrong, NVDA goes on as usual --------------------------------------------

	def test_aReportThatFailsLeavesNothingBehind(self):
		quickNavHeadings.register()
		broken = TextInfo(self.page, self.parts["Welcome to AppleVis"], "Welcome to AppleVis")
		broken.getControlFieldSpeech = mock.Mock(side_effect=RuntimeError("the document went away"))
		self.fresh()
		with self.assertRaises(RuntimeError, msg="NVDA's own error, as without the assistant"):
			VirtualBufferQuickNavItem("heading", self.page, broken).report()
		self.fresh()
		self.assertEqual(self.press("link", "Giants Claim Camilo Doval"), ["main landmark", "Giants Claim Camilo Doval", "link", "heading", "level 2"], "the next link is read as NVDA reads it")

	def test_aFieldThatCantBeCheckedIsSaid(self):
		quickNavHeadings.register()
		self.fresh()
		with mock.patch.object(quickNavHeadings, "_isAround", side_effect=RuntimeError("gone")):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				said = self.press("heading", "Welcome to AppleVis")
		self.assertEqual(said, ["main landmark", "Welcome to AppleVis", "heading", "level 1"], "NVDA's own words")
		self.assertTrue(any("could not tell what a heading is in" in line for line in logged.output), logged.output)

	def test_aHeadingOnAnotherThreadChangesNothingHere(self):
		quickNavHeadings.register()
		entered, release = threading.Event(), threading.Event()
		other = Document()

		def slowReport():
			class Slow(TextInfo):
				def getControlFieldSpeech(self, *args, **kwargs):
					entered.set()
					release.wait(5)
					return super().getControlFieldSpeech(*args, **kwargs)

			VirtualBufferQuickNavItem("heading", other, Slow(other, self.parts["Welcome to AppleVis"], "Welcome to AppleVis")).report()

		thread = threading.Thread(target=slowReport)
		thread.start()
		try:
			self.assertTrue(entered.wait(5))
			self.fresh()
			self.assertEqual(self.press("link", "Giants Claim Camilo Doval"), ["main landmark", "Giants Claim Camilo Doval", "link", "heading", "level 2"])
		finally:
			release.set()
			thread.join(5)

	def test_nvdaWithoutFieldSpeechIsLeftAlone(self):
		del self.speech.getControlFieldSpeech
		with self.assertLogs("nvda", level="DEBUG") as logged:
			quickNavHeadings.register()
		self.assertIs(TextInfoQuickNavItem.report, NVDA_REPORT, "nothing is wrapped for nothing to change")
		self.assertTrue(any("says headings as NVDA does" in line for line in logged.output), logged.output)

	def test_whatTheLogSays(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			quickNavHeadings.register()
			self.fresh()
			self.press("heading", "r/Visible")
			self.press("heading", "New speedtest megathread")
			self.press("heading", "12 comments")
			self.fresh()
			self.press("link", "Giants Claim Camilo Doval")
		lines = [line for line in logged.output if "jawsMigrator" in line]
		self.assertEqual(sum("quick navigation says a heading without the landmark, region or list it is in" in line for line in lines), 2, lines)
		moved = [line for line in lines if "quick navigation moved to a heading" in line]
		self.assertEqual(len(moved), 3, lines)
		self.assertIn("so NVDA doesn't say what it is in: Community actions region", moved[0])
		self.assertIn("main landmark; list with 2 items", moved[1])
		self.assertIn("in: article", moved[2], "the main landmark was entered by the H before")


# -- list items: no row and column ---------------------------------------------------------------------


def _objectSpeech_calculateAllowedProps(reason, shouldReportTextContent, objRole):
	"""NVDA 2026.2's speech.speech._objectSpeech_calculateAllowedProps, with "Cell coordinates" on."""
	return {"name": True, "rowNumber": True, "columnNumber": True, "includeTableCellCoords": True, "cellCoordsText": True}


class ListCoordinatesTests(unittest.TestCase):
	def setUp(self):
		self.speechModule = types.ModuleType("speech.speech")
		self.speechModule._objectSpeech_calculateAllowedProps = _objectSpeech_calculateAllowedProps
		speechPackage = types.ModuleType("speech")
		speechPackage.speech = self.speechModule
		controlTypes = types.ModuleType("controlTypes")
		controlTypes.OutputReason, controlTypes.Role = OutputReason, Role
		modules = mock.patch.dict(sys.modules, {"speech": speechPackage, "speech.speech": self.speechModule, "controlTypes": controlTypes})
		modules.start()
		self.addCleanup(modules.stop)
		self.addCleanup(self._restoreNvda)
		listCoordinates._failed = False
		listCoordinates._logged = False

	def _restoreNvda(self):
		listCoordinates.unregister()
		self.speechModule._objectSpeech_calculateAllowedProps = _objectSpeech_calculateAllowedProps
		listCoordinates._replaced.clear()
		listCoordinates._failed = False

	def allowed(self, role, reason=OutputReason.FOCUS):
		return self.speechModule._objectSpeech_calculateAllowedProps(reason, False, role)

	def test_aListItemHasNoRowAndColumn(self):
		# Issue 4: "Data (D:), row 2, column 1, 3 of 3" in File Explorer, where JAWS says "Data (D:)".
		listCoordinates.register()
		for reason in (OutputReason.FOCUS, OutputReason.CARET, OutputReason.QUICKNAV):
			allowed = self.allowed(Role.LISTITEM, reason)
			self.assertFalse(allowed["includeTableCellCoords"], reason)
			self.assertFalse(allowed["cellCoordsText"], reason)
			self.assertTrue(allowed["rowNumber"] and allowed["columnNumber"], "NVDA still notes the table, as with Cell coordinates off")
			self.assertTrue(allowed["name"])

	def test_nvdaTabAndTableCellsKeepThem(self):
		listCoordinates.register()
		self.assertTrue(self.allowed(Role.LISTITEM, OutputReason.QUERY)["includeTableCellCoords"], "NVDA+Tab says the row and column")
		for role in (Role.TABLECELL, Role.BUTTON, Role.HEADING):
			self.assertTrue(self.allowed(role)["includeTableCellCoords"], role)
			self.assertTrue(self.allowed(role)["cellCoordsText"], role)

	def test_theSetting(self):
		self.assertTrue(listCoordinates.wanted({}))
		self.assertFalse(listCoordinates.wanted({listCoordinates.STATE_KEY: False}))
		self.assertFalse(listCoordinates.wanted(None))
		self.assertIs(state.DEFAULTS[listCoordinates.STATE_KEY], True)

	def test_turnedOffNvdaHasItsOwnBack(self):
		listCoordinates.register()
		listCoordinates.register()
		self.assertIs(self.speechModule._objectSpeech_calculateAllowedProps.__wrapped__, _objectSpeech_calculateAllowedProps, "registered twice, wrapped once")
		listCoordinates.unregister()
		self.assertIs(self.speechModule._objectSpeech_calculateAllowedProps, _objectSpeech_calculateAllowedProps)
		self.assertTrue(self.allowed(Role.LISTITEM)["includeTableCellCoords"])

	def test_anotherAddonsWrapperOverTheAssistants(self):
		listCoordinates.register()
		ours = self.speechModule._objectSpeech_calculateAllowedProps

		@functools.wraps(ours)
		def otherAddon(*args, **kwargs):
			return ours(*args, **kwargs)

		self.speechModule._objectSpeech_calculateAllowedProps = otherAddon
		listCoordinates.unregister()
		self.assertIs(self.speechModule._objectSpeech_calculateAllowedProps, otherAddon)
		self.assertTrue(self.allowed(Role.LISTITEM)["includeTableCellCoords"], "the assistant's, still inside it, does nothing")
		listCoordinates.register()
		self.assertIs(self.speechModule._objectSpeech_calculateAllowedProps, otherAddon, "not wrapped a second time")
		self.assertFalse(self.allowed(Role.LISTITEM)["includeTableCellCoords"])

	def test_whatTheLogSaysOnce(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			listCoordinates.register()
			for _ in range(3):
				self.allowed(Role.LISTITEM)
		lines = [line for line in logged.output if "jawsMigrator" in line]
		self.assertEqual(sum("NVDA says a list item without its row and column numbers" in line for line in lines), 1, lines)
		self.assertEqual(sum("a list item's row and column numbers are left out" in line for line in lines), 1, lines)

	def test_nvdaWithoutTheFunctionIsLeftAlone(self):
		del self.speechModule._objectSpeech_calculateAllowedProps
		with self.assertLogs("nvda", level="DEBUG") as logged:
			listCoordinates.register()
		self.assertTrue(any("says a list item's row and column as it does" in line for line in logged.output), logged.output)
		self.speechModule._objectSpeech_calculateAllowedProps = _objectSpeech_calculateAllowedProps


# -- a web page's tabs and toolbar buttons: browse mode, as JAWS's Auto Forms Mode ------------------------


class BrowseModeTreeInterceptor:
	"""NVDA 2026.2's browseMode.BrowseModeTreeInterceptor, as far as its choice of mode goes."""

	SWITCH_TO_PASS_THROUGH_ON_FOCUS_ROLES = frozenset({Role.TAB, Role.RADIOBUTTON, Role.LISTITEM})

	def __init__(self):
		self.passThrough = False

	def shouldPassThrough(self, obj, reason=None):
		if reason == OutputReason.QUICKNAV:
			return False
		if State.EDITABLE in obj.states or obj.role == Role.EDITABLETEXT:
			return True
		if reason == OutputReason.FOCUS:
			if obj.role in self.SWITCH_TO_PASS_THROUGH_ON_FOCUS_ROLES:
				return True
			# Anything in a toolbar: NVDA walks up the object's parents.
			if getattr(obj, "inToolbar", False):
				return True
		return False


class MSHTML(BrowseModeTreeInterceptor):
	"""A subclass with its own choice, which asks NVDA's (virtualBuffers.MSHTML)."""

	def shouldPassThrough(self, obj, reason=None):
		return super().shouldPassThrough(obj, reason=reason)


NVDA_PASS_THROUGH = vars(BrowseModeTreeInterceptor)["shouldPassThrough"]


def control(role, name="", states=(), inToolbar=False):
	return types.SimpleNamespace(role=role, name=name, states=set(states), inToolbar=inToolbar)


class Gesture:
	"""A key press as NVDA's decide_executeGesture passes it: NVDA's names for it."""

	def __init__(self, *identifiers):
		self.normalizedIdentifiers = list(identifiers)


TAB = Gesture("kb(laptop):tab", "kb:tab")
SHIFT_TAB = Gesture("kb(laptop):shift+tab", "kb:shift+tab")


class Decider:
	"""NVDA's inputCore.decide_executeGesture: NVDA runs a gesture only when every handler says True."""

	def __init__(self):
		self.handlers = []

	def register(self, handler):
		self.handlers.append(handler)

	def unregister(self, handler):
		if handler in self.handlers:
			self.handlers.remove(handler)

	def decide(self, **kwargs):
		return all(handler(**kwargs) for handler in list(self.handlers))


class AutoFormsModeTests(unittest.TestCase):
	def setUp(self):
		browseMode = types.ModuleType("browseMode")
		browseMode.BrowseModeTreeInterceptor = BrowseModeTreeInterceptor
		controlTypes = types.ModuleType("controlTypes")
		controlTypes.OutputReason, controlTypes.Role, controlTypes.State = OutputReason, Role, State
		self.inputCore = types.ModuleType("inputCore")
		self.inputCore.decide_executeGesture = Decider()
		modules = mock.patch.dict(sys.modules, {"browseMode": browseMode, "controlTypes": controlTypes, "inputCore": self.inputCore})
		modules.start()
		self.addCleanup(modules.stop)
		self.addCleanup(self._restoreNvda)
		autoFormsMode._failed = False
		self.clock = [1000.0]
		clock = mock.patch.object(autoFormsMode.time, "monotonic", lambda: self.clock[0])
		clock.start()
		self.addCleanup(clock.stop)
		self.document = BrowseModeTreeInterceptor()
		self.title = control(Role.EDITABLETEXT, "Add a title", {State.EDITABLE})
		self.write = control(Role.TAB, "Write")
		self.preview = control(Role.TAB, "Preview")
		self.bold = control(Role.BUTTON, "Bold", inToolbar=True)
		self.italic = control(Role.BUTTON, "Italic", inToolbar=True)
		self.body = control(Role.EDITABLETEXT, "Markdown value", {State.EDITABLE})

	def _restoreNvda(self):
		autoFormsMode.unregister()
		BrowseModeTreeInterceptor.shouldPassThrough = NVDA_PASS_THROUGH
		autoFormsMode._replaced.clear()
		autoFormsMode._failed = False

	def press(self, gesture):
		"""A key press: NVDA asks decide_executeGesture before running it."""
		self.assertTrue(self.inputCore.decide_executeGesture.decide(gesture=gesture), "NVDA always runs the key")
		self.clock[0] += 0.05

	def focus(self, obj, document=None):
		"""The focus moves to obj: the plugin notes it, then NVDA's browse mode chooses the mode, as event_gainFocus does."""
		document = document or self.document
		autoFormsMode.noteFocus(obj)
		document.passThrough = document.shouldPassThrough(obj, reason=OutputReason.FOCUS)
		self.clock[0] += 0.05
		return document.passThrough

	# -- the tester's report: GitHub's new issue form ----------------------------------------------

	def test_nvdaAloneStaysInFocusMode(self):
		self.assertTrue(self.focus(self.title))
		self.press(TAB)
		self.assertTrue(self.focus(self.write), "issue 7: letters typed on the Write tab go to the page")
		self.press(TAB)
		self.assertTrue(self.focus(self.bold), "and on the toolbar's buttons")

	def test_tabThroughGitHubsEditor(self):
		autoFormsMode.register()
		self.assertTrue(self.focus(self.title), "the title box: focus mode, as always")
		self.press(TAB)
		self.assertFalse(self.focus(self.write), "the Write tab: browse mode, as JAWS's virtual cursor")
		self.assertFalse(
			self.document.shouldPassThrough(self.write, reason=OutputReason.FOCUS),
			"NVDA asks again as it moves its caret there (_set_selection): the same answer",
		)
		self.press(TAB)
		self.assertFalse(self.focus(self.bold), "the toolbar's first button: browse mode, as JAWS's Auto Forms Mode")
		self.press(TAB)
		self.assertTrue(self.focus(self.body), "the text box: focus mode, to type the description")
		self.press(SHIFT_TAB)
		self.assertFalse(self.focus(self.bold), "Shift+Tab back to the toolbar: browse mode")

	def test_fromOneTabToAnother(self):
		autoFormsMode.register()
		self.focus(self.title)
		self.focus(self.write)
		# Enter on the Preview tab in browse mode moves the focus there: browse mode stays.
		self.assertFalse(self.focus(self.preview))
		# NVDA+Space on a tab, then the arrow keys between tabs: focus mode stays.
		self.document.passThrough = True
		self.assertTrue(self.focus(self.write))
		self.assertTrue(self.focus(self.preview))

	def test_theArrowKeysInAToolbar(self):
		autoFormsMode.register()
		self.focus(self.title)
		self.press(TAB)
		self.focus(self.bold)
		# NVDA+Space on the toolbar, then the arrow keys from button to button, however quick: NVDA's own choice, focus mode.
		self.press(Gesture("kb(laptop):NVDA+space", "kb:NVDA+space"))
		self.document.passThrough = True
		self.press(Gesture("kb(laptop):rightArrow", "kb:rightArrow"))
		self.assertTrue(self.focus(self.italic))
		# Long after Tab, with no other key, a focus change isn't Tab's either.
		self.press(TAB)
		self.clock[0] += autoFormsMode.AFTER_TAB + 1
		self.assertTrue(self.focus(self.bold))
		# A click or the page moving the focus to a toolbar button: NVDA's choice too.
		self.assertTrue(self.focus(self.bold))

	def test_otherKeysAreNotTab(self):
		autoFormsMode.register()
		for gesture in (Gesture("kb:control+tab"), Gesture("kb:alt+tab"), Gesture("kb:NVDA+tab"), Gesture("kb:t"), Gesture(), object()):
			autoFormsMode._tabPressed = None
			self.assertTrue(autoFormsMode.noteGesture(gesture))
			self.assertIsNone(autoFormsMode._tabPressed, getattr(gesture, "normalizedIdentifiers", None))
		self.assertTrue(autoFormsMode.noteGesture(None), "NVDA runs every key, whatever it is")

	def test_nvdaSpaceTheCaretAndQuickNavigationChooseAsNvdaDoes(self):
		autoFormsMode.register()
		self.focus(self.title)
		self.press(TAB)
		autoFormsMode.noteFocus(self.write)
		for obj in (self.write, self.bold):
			for reason in (None, OutputReason.CARET, OutputReason.QUICKNAV):
				self.assertEqual(
					self.document.shouldPassThrough(obj, reason=reason),
					NVDA_PASS_THROUGH(self.document, obj, reason=reason),
					f"NVDA's own answer: {obj.name}, {reason}",
				)

	def test_everythingElseAsNvdaDoes(self):
		autoFormsMode.register()
		for obj in (
			control(Role.RADIOBUTTON, "Yes"),
			control(Role.LISTITEM, "Option"),
			control(Role.EDITABLETEXT, "Body", {State.EDITABLE}),
			control(Role.TAB, "Editable tab", {State.EDITABLE}),
			control(Role.EDITABLETEXT, "Search in a toolbar", {State.EDITABLE}, inToolbar=True),
			control(Role.RADIOBUTTON, "A radio button in a toolbar", inToolbar=True),
		):
			self.focus(control(Role.BUTTON, "Submit"))
			self.press(TAB)
			self.assertTrue(self.focus(obj), obj.name)
		self.press(TAB)
		self.assertFalse(self.focus(control(Role.BUTTON, "Submit")), "a button outside a toolbar: browse mode, as always")

	def test_everyToolbarControlJawsLeavesFormsModeFor(self):
		autoFormsMode.register()
		for role in (Role.BUTTON, Role.TOGGLEBUTTON, Role.MENUBUTTON, Role.CHECKBOX):
			self.focus(self.title)
			self.press(TAB)
			self.assertFalse(self.focus(control(role, role.value, inToolbar=True)), role)

	def test_aSubclassAsksNvdasChoice(self):
		autoFormsMode.register()
		document = MSHTML()
		self.focus(self.title, document)
		self.press(TAB)
		self.assertFalse(self.focus(self.write, document))
		self.press(TAB)
		self.assertFalse(self.focus(self.bold, document))

	def test_theSetting(self):
		self.assertTrue(autoFormsMode.wanted({}))
		self.assertFalse(autoFormsMode.wanted({autoFormsMode.STATE_KEY: False}))
		self.assertFalse(autoFormsMode.wanted(None))
		self.assertIs(state.DEFAULTS[autoFormsMode.STATE_KEY], True)

	def test_turnedOffNvdaHasItsOwnBack(self):
		autoFormsMode.register()
		autoFormsMode.register()
		self.assertIs(BrowseModeTreeInterceptor.shouldPassThrough.__wrapped__, NVDA_PASS_THROUGH, "registered twice, wrapped once")
		self.assertEqual(self.inputCore.decide_executeGesture.handlers, [autoFormsMode.noteGesture], "and key presses noted once")
		autoFormsMode.unregister()
		self.assertIs(BrowseModeTreeInterceptor.shouldPassThrough, NVDA_PASS_THROUGH)
		self.assertEqual(self.inputCore.decide_executeGesture.handlers, [], "key presses are no longer noted")
		self.focus(self.title)
		self.press(TAB)
		self.assertTrue(self.focus(self.write))
		autoFormsMode.noteFocus(self.title)
		self.assertEqual(autoFormsMode._roles, (None, None), "turned off, the focus isn't noted")

	def test_anotherAddonsWrapperOverTheAssistants(self):
		autoFormsMode.register()
		ours = BrowseModeTreeInterceptor.shouldPassThrough

		@functools.wraps(ours)
		def otherAddon(self, obj, reason=None):
			return ours(self, obj, reason=reason)

		BrowseModeTreeInterceptor.shouldPassThrough = otherAddon
		autoFormsMode.unregister()
		self.assertIs(BrowseModeTreeInterceptor.shouldPassThrough, otherAddon)
		self.focus(self.title)
		self.assertTrue(self.focus(self.write), "the assistant's, still inside it, does nothing")
		autoFormsMode.register()
		self.assertIs(BrowseModeTreeInterceptor.shouldPassThrough, otherAddon, "not wrapped a second time")
		self.focus(self.title)
		self.assertFalse(self.focus(self.write))

	def test_whatCantBeCheckedGetsNvdasChoice(self):
		autoFormsMode.register()

		class Gone:
			states = set()
			name = "gone"

			@property
			def role(self):
				raise RuntimeError("the object went away")

		self.focus(self.title)
		autoFormsMode.noteFocus(Gone())
		self.assertEqual(autoFormsMode._roles[1], None, "an object whose role can't be read is noted without one")
		autoFormsMode.noteFocus(self.write)
		autoFormsMode._roles = None
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.assertTrue(self.document.shouldPassThrough(self.write, reason=OutputReason.FOCUS), "NVDA's own answer")
		self.assertTrue(any("could not keep browse mode on a web page's tab or toolbar button" in line for line in logged.output), logged.output)
		autoFormsMode._roles = (None, None)

	def test_nvdaWithoutKeyPressNotesStillKeepsTabs(self):
		del self.inputCore.decide_executeGesture
		with self.assertLogs("nvda", level="DEBUG") as logged:
			autoFormsMode.register()
		self.assertTrue(any("can't tell which focus changes Tab made" in line for line in logged.output), logged.output)
		self.focus(self.title)
		self.assertFalse(self.focus(self.write), "a tab still keeps browse mode")
		self.assertTrue(self.focus(self.bold), "a toolbar button: NVDA's choice, as nothing says Tab was pressed")

	def test_whatTheLogSays(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			autoFormsMode.register()
			self.focus(self.title)
			self.press(TAB)
			self.focus(self.write)
			self.document.shouldPassThrough(self.write, reason=OutputReason.FOCUS)
			self.press(TAB)
			self.focus(self.bold)
		lines = [line for line in logged.output if "jawsMigrator" in line]
		self.assertEqual(sum("NVDA stays in browse mode on a web page's tabs and toolbar buttons, as JAWS does" in line for line in lines), 1, lines)
		self.assertEqual(sum("the focus moved to a tab from outside its tab list ('Write'), so NVDA stays in browse mode there" in line for line in lines), 1, lines)
		self.assertEqual(sum("the focus moved to a toolbar's button or check box with Tab ('Bold')" in line for line in lines), 1, lines)


# -- Backspace in a slow program: what it deletes is said ----------------------------------------------


class Clock:
	"""time.monotonic and time.sleep for the tests: sleeping moves the clock, and the program works meanwhile."""

	def __init__(self):
		self.now = 100.0
		self.program = None

	def monotonic(self):
		return self.now

	def sleep(self, seconds):
		self.now += seconds
		if self.program is not None:
			self.program.work()


class Program:
	"""Windows 11 Notepad with a huge document: Backspace deletes ``delay`` seconds after the key."""

	def __init__(self, clock, text, caret, delay, readOnly=False):
		self.clock, self.text, self.caret, self.delay, self.readOnly = clock, text, caret, delay, readOnly
		self.deleteAt = None
		self.deletedAt = None
		self.word = False
		clock.program = self

	def backspace(self, word=False):
		self.deleteAt, self.word = self.clock.now + self.delay, word

	def work(self):
		if self.deleteAt is None or self.clock.now < self.deleteAt:
			return
		self.deleteAt = None
		if self.readOnly or not self.caret:
			return
		start = self.caret - 1
		while self.word and start > 0 and self.text[start - 1] != " ":
			start -= 1
		self.text = self.text[:start] + self.text[self.caret :]
		self.caret = start
		self.deletedAt = self.clock.now


class Range:
	"""A UIA text range: offsets, and a bookmark that compares equal whatever was deleted before it."""

	def __init__(self, program, start, end):
		self.program, self.start, self.end = program, start, end

	def copy(self):
		return Range(self.program, self.start, self.end)

	@property
	def bookmark(self):
		return "caret"

	def move(self, unit, direction, endPoint=None):
		position = self.end if endPoint == "end" else self.start
		target = max(0, min(len(self.program.text), position + direction))
		if endPoint == "start":
			self.start = target
		elif endPoint == "end":
			self.end = target
		else:
			self.start = self.end = target
		return target - position

	def expand(self, unit):
		if unit == "word":
			while self.start > 0 and self.program.text[self.start - 1] != " ":
				self.start -= 1
			self.end = self.start
			while self.end < len(self.program.text) and self.program.text[self.end] != " ":
				self.end += 1
		else:
			self.end = min(len(self.program.text), self.start + 1)

	@property
	def text(self):
		return self.program.text[self.start : self.end]


said = []
scriptWaiting = [False]


class EditableText:
	"""NVDA 2026.2's editableText.EditableText, as far as Backspace goes (_backspaceScriptHelper and _hasCaretMoved)."""

	def __init__(self, program):
		self.program = program

	@property
	def states(self):
		return {State.READONLY} if self.program.readOnly else set()

	def makeTextInfo(self, position):
		return Range(self.program, self.program.caret, self.program.caret)

	def _hasCaretMoved(self, bookmark, retryInterval=0.01, timeout=None, origWord=None):
		clock = self.program.clock
		timeout = 0.1 if timeout is None else timeout
		start = clock.now
		while True:
			if scriptWaiting[0]:
				return (False, None)
			info = self.makeTextInfo("caret")
			deletedAt = self.program.deletedAt
			# A caret event counts only within 60 ms of the key; the bookmark never shows a deletion.
			if deletedAt is not None and deletedAt - start <= 0.06:
				return (True, info)
			if info.bookmark != bookmark:
				return (True, info)
			if clock.now - start >= timeout:
				return (False, info)
			clock.sleep(retryInterval)

	def _backspaceScriptHelper(self, unit, gesture):
		oldInfo = self.makeTextInfo("caret")
		oldBookmark = oldInfo.bookmark
		testInfo = oldInfo.copy()
		if testInfo.move("character", -1) < 0:
			testInfo.expand(unit)
			delChunk = testInfo.text
		else:
			delChunk = ""
		gesture.send()
		caretMoved, newInfo = self._hasCaretMoved(oldBookmark)
		if not caretMoved:
			return
		said.append(("message" if len(delChunk) > 1 else "spell", delChunk))

	def script_caret_backspaceCharacter(self, gesture):
		self._backspaceScriptHelper("character", gesture)

	def script_caret_backspaceWord(self, gesture):
		self._backspaceScriptHelper("word", gesture)


NVDA_HELPER = vars(EditableText)["_backspaceScriptHelper"]
NVDA_WAIT = vars(EditableText)["_hasCaretMoved"]


class Key:
	def __init__(self, program, word=False):
		self.program, self.word = program, word

	def send(self):
		self.program.backspace(self.word)


class BackspaceEchoTests(unittest.TestCase):
	def setUp(self):
		self.clock = Clock()
		editable = types.ModuleType("editableText")
		editable.EditableText = EditableText
		textInfosModule = types.ModuleType("textInfos")
		textInfosModule.POSITION_CARET, textInfosModule.UNIT_CHARACTER = "caret", "character"
		controlTypes = types.ModuleType("controlTypes")
		controlTypes.State = State
		scriptHandler = types.ModuleType("scriptHandler")
		scriptHandler.isScriptWaiting = lambda: scriptWaiting[0]
		self.alive = []
		watchdog = types.ModuleType("watchdog")
		watchdog.alive = lambda: self.alive.append(self.clock.now)
		modules = mock.patch.dict(
			sys.modules,
			{"editableText": editable, "textInfos": textInfosModule, "controlTypes": controlTypes, "scriptHandler": scriptHandler, "watchdog": watchdog},
		)
		modules.start()
		self.addCleanup(modules.stop)
		clock = mock.patch.object(backspaceEcho, "time", types.SimpleNamespace(monotonic=self.clock.monotonic, sleep=self.clock.sleep))
		clock.start()
		self.addCleanup(clock.stop)
		self.addCleanup(self._restoreNvda)
		backspaceEcho._failed = False
		said.clear()
		scriptWaiting[0] = False

	def _restoreNvda(self):
		backspaceEcho.unregister()
		EditableText._backspaceScriptHelper = NVDA_HELPER
		EditableText._hasCaretMoved = NVDA_WAIT
		backspaceEcho._replaced.clear()
		backspaceEcho._failed = False

	def press(self, text="its ide", caret=7, delay=0.2, word=False, readOnly=False):
		"""Backspace (or Control+Backspace) in the program: what NVDA says, and how long NVDA's script took."""
		said.clear()
		program = Program(self.clock, text, caret, delay, readOnly)
		document = EditableText(program)
		started = self.clock.now
		key = Key(program, word)
		if word:
			document.script_caret_backspaceWord(key)
		else:
			document.script_caret_backspaceCharacter(key)
		return list(said), round(self.clock.now - started, 3)

	# -- the tester's report -------------------------------------------------------------------

	def test_nvdaAloneIsSilentInSlowNotepad(self):
		self.assertEqual(self.press(delay=0.2)[0], [], "issue 2: NVDA gave up after 100 ms, then Notepad deleted")
		self.assertEqual(self.press(delay=0.01)[0], [("spell", "e")], "a quick program: its caret event came in time")

	def test_theDeletedCharacterIsSaid(self):
		backspaceEcho.register()
		for delay in (0.12, 0.2, 0.35, 0.49):
			spoken, took = self.press(delay=delay)
			self.assertEqual(spoken, [("spell", "e")], delay)
			self.assertLess(took, delay + 0.05, "said as soon as the program deleted")
		self.assertEqual(self.press(delay=0.25, word=True)[0], [("message", "ide")], "Control+Backspace: the word")
		self.assertTrue(self.alive, "NVDA's watchdog hears that NVDA isn't frozen while it waits")

	def test_quickProgramsAsNvdaSaysThem(self):
		backspaceEcho.register()
		self.assertEqual(self.press(delay=0.01), ([("spell", "e")], 0.01), "no longer wait")

	def test_theWaitHasAnEnd(self):
		backspaceEcho.register()
		spoken, took = self.press(delay=0.8)
		self.assertEqual(spoken, [], "deleted after 0.5 s: NVDA and the assistant gave up")
		self.assertLessEqual(took, 0.1 + backspaceEcho.EXTRA_WAIT + backspaceEcho.STEP + 0.02)

	def test_nothingToDeleteNoLongerWait(self):
		backspaceEcho.register()
		self.assertEqual(self.press(readOnly=True), ([], 0.1), "a read-only field: NVDA's own wait only")
		self.assertEqual(self.press(caret=0), ([], 0.1), "the start of the text")

	def test_anotherKeyWaiting(self):
		backspaceEcho.register()
		scriptWaiting[0] = True
		self.assertEqual(self.press(delay=0.2), ([], 0.0), "NVDA says only what the last key did")

	def test_anotherKeyDuringTheWait(self):
		backspaceEcho.register()
		tick = self.clock.sleep
		started = self.clock.now

		def sleep(seconds):
			tick(seconds)
			# Backspace again 150 ms after the first, before Notepad deleted (at 300 ms): NVDA says only the last.
			if self.clock.now - started >= 0.15:
				scriptWaiting[0] = True

		self.clock.sleep = sleep
		with mock.patch.object(backspaceEcho, "time", types.SimpleNamespace(monotonic=self.clock.monotonic, sleep=sleep)):
			spoken, took = self.press(delay=0.3)
		self.assertEqual(spoken, [])
		self.assertLess(took, 0.2, "the assistant stopped waiting at once")

	# -- the setting --------------------------------------------------------------------------

	def test_theSetting(self):
		self.assertTrue(backspaceEcho.wanted({}))
		self.assertFalse(backspaceEcho.wanted({backspaceEcho.STATE_KEY: False}))
		self.assertFalse(backspaceEcho.wanted(None))
		self.assertIs(state.DEFAULTS[backspaceEcho.STATE_KEY], True)

	def test_turnedOffNvdaHasItsOwnBack(self):
		backspaceEcho.register()
		backspaceEcho.register()
		self.assertIs(EditableText._hasCaretMoved.__wrapped__, NVDA_WAIT, "registered twice, wrapped once")
		self.assertIs(EditableText._backspaceScriptHelper.__wrapped__, NVDA_HELPER)
		backspaceEcho.unregister()
		self.assertIs(EditableText._hasCaretMoved, NVDA_WAIT)
		self.assertIs(EditableText._backspaceScriptHelper, NVDA_HELPER)
		self.assertEqual(self.press(delay=0.2)[0], [])

	def test_anotherAddonsWrapperOverTheAssistants(self):
		backspaceEcho.register()
		ours = EditableText._backspaceScriptHelper

		@functools.wraps(ours)
		def otherAddon(self, unit, gesture):
			return ours(self, unit, gesture)

		EditableText._backspaceScriptHelper = otherAddon
		backspaceEcho.unregister()
		self.assertIs(EditableText._backspaceScriptHelper, otherAddon, "the other add-on's wrapper stays")
		self.assertIs(EditableText._hasCaretMoved, NVDA_WAIT)
		self.assertEqual(self.press(delay=0.2)[0], [], "the assistant's, still inside it, does nothing")
		backspaceEcho.register()
		self.assertIs(EditableText._backspaceScriptHelper, otherAddon, "not wrapped a second time")
		self.assertEqual(self.press(delay=0.2)[0], [("spell", "e")])

	def test_whateverFailsNvdaGoesOn(self):
		backspaceEcho.register()
		with mock.patch.object(backspaceEcho, "_around", side_effect=RuntimeError("the program went away")):
			self.assertEqual(self.press(delay=0.2), ([], 0.1), "NVDA's own Backspace, and wait")
		with mock.patch.object(backspaceEcho, "_waitForDeletion", side_effect=RuntimeError("broken")):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				self.assertEqual(self.press(delay=0.2)[0], [])
		self.assertTrue(any("could not tell whether Backspace deleted anything" in line for line in logged.output), logged.output)

	def test_nvdaWithoutTheWaitIsLeftAlone(self):
		del EditableText._hasCaretMoved
		try:
			with self.assertLogs("nvda", level="DEBUG") as logged:
				backspaceEcho.register()
			self.assertIs(vars(EditableText)["_backspaceScriptHelper"], NVDA_HELPER, "nothing is wrapped for nothing to extend")
			self.assertTrue(any("Backspace works as it does in NVDA" in line for line in logged.output), logged.output)
		finally:
			EditableText._hasCaretMoved = NVDA_WAIT

	def test_whatTheLogSays(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			backspaceEcho.register()
			self.press(delay=0.25)
			self.press(delay=0.01)
		lines = [line for line in logged.output if "jawsMigrator" in line]
		self.assertEqual(sum("Backspace says what it deletes in slow programs too" in line for line in lines), 2, lines)
		deleted = [line for line in lines if "the program deleted the character" in line]
		self.assertEqual(len(deleted), 1, lines)
		self.assertIn("ms after NVDA stopped waiting for the caret, so NVDA says it, as JAWS does", deleted[0])


if __name__ == "__main__":
	unittest.main()
