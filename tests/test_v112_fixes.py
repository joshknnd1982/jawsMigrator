# Unit tests for version 1.12, from a tester's report on version 1.10: pressing H on a football news
# site, NVDA said "main landmark, Texans' Nico Collins Likely To Miss Week 3, link, heading, level 2",
# the heading's level last (headingOrder). The imitation NVDA below does what NVDA 2026.2 does, as far
# as the order goes: speech._shouldSpeakContentFirst, which puts a heading's or a link's text before
# what it is for quick navigation and the focus; getControlFieldSpeech, which asks it for each field
# NVDA reads and says a field's type as its text starts or once it ends; speakTextInfo, with its notes
# of the fields NVDA is in (the fields of the last thing it read); and browseMode's
# TextInfoQuickNavItem.report, which quick navigation and the Elements List call. The page is the
# tester's, and the expected words are the ones in the tester's NVDA log. The assistant's register,
# unregister and wrappers are the real ones.
# Run: python -m unittest tests.test_v112_fixes -v

import enum
import functools
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

from jawsMigrator import headingOrder, state  # noqa: E402

TEXANS = "Texans\N{RIGHT SINGLE QUOTATION MARK} Nico Collins Likely To Miss Week 3"


class OutputReason(enum.Enum):
	FOCUS = "focus"
	QUICKNAV = "quickNav"
	CARET = "caret"
	QUERY = "query"


class Role(enum.Enum):
	LANDMARK = "landmark"
	SECTION = "section"
	ARTICLE = "article"
	HEADING = "heading"
	LINK = "link"
	BUTTON = "button"
	EDITABLETEXT = "edit"


INTERNAL_LINK = "same page"
EDITABLE = "editable"
CONTAINER, SINGLELINE, LAYOUT = "container", "singleLine", "layout"


class Field(dict):
	"""A control field of a browse mode document (textInfos.ControlField)."""


def field(role, **attributes):
	return Field(role=role, states=attributes.pop("states", set()), **attributes)


def presentationCategory(attrs):
	"""ControlField.getPresentationCategory, for these roles: landmarks and articles hold other fields."""
	role = attrs["role"]
	if role in (Role.LANDMARK, Role.ARTICLE):
		return CONTAINER
	if role in (Role.HEADING, Role.LINK, Role.BUTTON, Role.EDITABLETEXT):
		return SINGLELINE
	return LAYOUT


def _shouldSpeakContentFirst(reason, role, presCat, attrs, tableID, states):
	"""NVDA 2026.2's speech._shouldSpeakContentFirst."""
	never = (Role.EDITABLETEXT, Role.LANDMARK)
	return (
		reason in [OutputReason.FOCUS, OutputReason.QUICKNAV]
		and (presCat != CONTAINER or role == Role.ARTICLE)
		and role not in never
		and not tableID
		and EDITABLE not in states
	)


def fieldWords(attrs, reason):
	"""What NVDA says a field is: "main landmark"; "heading", "level 2"; "same page", "link" and its title."""
	role = attrs["role"]
	if role == Role.LANDMARK:
		return [f"{attrs['landmark']} landmark"]
	words = [name for name in (INTERNAL_LINK,) if name in attrs["states"]]
	words.append(role.value)
	if attrs.get("level"):
		words.append(f"level {attrs['level']}")
	if attrs.get("description") and reason in (OutputReason.FOCUS, OutputReason.QUICKNAV):
		words.append(attrs["description"])
	return words


def getControlFieldSpeech(attrs, ancestorAttrs, fieldType, reason=None):
	"""NVDA 2026.2's speech.getControlFieldSpeech, as far as the order goes.

	Like NVDA's, it looks _shouldSpeakContentFirst up in its module each time, where the assistant's is.
	"""
	presCat = presentationCategory(attrs)
	if presCat == LAYOUT:
		return []
	role, states = attrs["role"], attrs["states"]
	speakContentFirst = SPEECH._shouldSpeakContentFirst(reason, role, presCat, attrs, None, states)
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
		sequence += info.getControlFieldSpeech(fields[count], fields[:count], "start_inControlFieldStack", reason=reason)
	for count in range(common, len(fields)):
		sequence += info.getControlFieldSpeech(fields[count], fields[:count], "start_addedToControlFieldStack", reason=reason)
	sequence.append(info.text)
	for count in reversed(range(len(fields))):
		sequence += info.getControlFieldSpeech(fields[count], fields[:count], "end_inControlFieldStack", reason=reason)
	document._speakTextInfoState = list(fields)
	spoken.append(sequence)
	return True


class TextInfo:
	"""A part of the page: the fields it is in, and its text (textInfos.TextInfo)."""

	def __init__(self, obj, fields, text):
		self.obj, self.fields, self.text = obj, fields, text

	def getControlFieldSpeech(self, attrs, ancestorAttrs, fieldType, formatConfig=None, extraDetail=False, reason=None):
		# textInfos.TextInfo.getControlFieldSpeech goes through the speech package.
		return sys.modules["speech"].getControlFieldSpeech(attrs, ancestorAttrs, fieldType, reason=reason)


class TextInfoQuickNavItem:
	"""NVDA 2026.2's browseMode.TextInfoQuickNavItem."""

	def __init__(self, itemType, document, textInfo, outputReason=OutputReason.QUICKNAV):
		self.itemType, self.document, self.textInfo, self.outputReason = itemType, document, textInfo, outputReason

	def report(self, readUnit=None):
		# NVDA's own: the readUnit for tables and edit fields is left out here, as a heading is read whole.
		sys.modules["speech"].speakTextInfo(self.textInfo, reason=self.outputReason)


class VirtualBufferQuickNavItem(TextInfoQuickNavItem):
	"""virtualBuffers.VirtualBufferQuickNavItem, what Edge and Chrome's quick navigation makes: it has NVDA's report."""


#: NVDA's own report, to check what the assistant puts in its place and gives back.
NVDA_REPORT = vars(TextInfoQuickNavItem)["report"]


SPEECH = types.ModuleType("speech.speech")
SPEECH._shouldSpeakContentFirst = _shouldSpeakContentFirst
SPEECH.getControlFieldSpeech = getControlFieldSpeech
SPEECH.speakTextInfo = speakTextInfo


class Document:
	"""The browse mode document of the tester's page."""


def testersPage():
	"""The tester's page, as NVDA read it at 22:51:12 to 22:51:15: three headings, each a link."""
	banner = field(Role.LANDMARK, landmark="banner", uniqueID=1)
	main = field(Role.LANDMARK, landmark="main", uniqueID=2)
	return {
		"HEADLINES": [field(Role.HEADING, level=3, uniqueID=10), field(Role.LINK, states={INTERNAL_LINK}, description="Homepage", uniqueID=11)],
		"Pro Football Rumors": [banner, field(Role.HEADING, level=1, uniqueID=12), field(Role.LINK, states={INTERNAL_LINK}, description="Home", uniqueID=13)],
		TEXANS: [main, field(Role.SECTION, uniqueID=20), field(Role.HEADING, level=2, uniqueID=21), field(Role.LINK, uniqueID=22)],
	}


#: What NVDA said in the tester's log for H, at 22:51:12.572, 22:51:13.083 and 22:51:15.458.
TESTERS_LOG = [
	["HEADLINES", "same page", "link", "Homepage", "heading", "level 3"],
	["banner landmark", "Pro Football Rumors", "same page", "link", "Home", "heading", "level 1"],
	["main landmark", TEXANS, "link", "heading", "level 2"],
]
#: The same, level first: the order NVDA reads each heading in with the arrow keys.
LEVEL_FIRST = [
	["heading", "level 3", "same page", "link", "Homepage", "HEADLINES"],
	["banner landmark", "heading", "level 1", "same page", "link", "Home", "Pro Football Rumors"],
	["main landmark", "heading", "level 2", "link", TEXANS],
]


class HeadingOrderTests(unittest.TestCase):
	def setUp(self):
		self.browseMode = types.ModuleType("browseMode")
		self.browseMode.TextInfoQuickNavItem = TextInfoQuickNavItem
		self.speech = types.ModuleType("speech")
		self.speech.speech = SPEECH
		self.speech.getControlFieldSpeech = getControlFieldSpeech
		self.speech.speakTextInfo = speakTextInfo
		controlTypes = types.ModuleType("controlTypes")
		controlTypes.OutputReason = OutputReason
		modules = mock.patch.dict(sys.modules, {"browseMode": self.browseMode, "speech": self.speech, "speech.speech": SPEECH, "controlTypes": controlTypes})
		modules.start()
		self.addCleanup(modules.stop)
		self.addCleanup(self._restoreNvda)
		self.page = Document()
		self.parts = testersPage()
		spoken.clear()
		headingOrder._failed = False

	def _restoreNvda(self):
		headingOrder.unregister()
		# Whatever a test put over NVDA's own goes, so the next test starts from NVDA as it is.
		SPEECH._shouldSpeakContentFirst = _shouldSpeakContentFirst
		TextInfoQuickNavItem.report = NVDA_REPORT
		headingOrder._replaced.clear()
		headingOrder._failed = False

	def part(self, text):
		return TextInfo(self.page, self.parts[text], text)

	def press(self, itemType, text, itemClass=VirtualBufferQuickNavItem, reason=OutputReason.QUICKNAV):
		"""Quick navigation to the item: NVDA's _quickNavScript reports it, then moves there."""
		spoken.clear()
		itemClass(itemType, self.page, self.part(text), reason).report()
		self.assertEqual(len(spoken), 1)
		return spoken[0]

	def arrow(self, text):
		spoken.clear()
		speakTextInfo(self.part(text), reason=OutputReason.CARET)
		return spoken[0]

	def threePressesOfH(self):
		"""Control+Home, then H three times, as in the tester's log."""
		self.page._speakTextInfoState = None
		return [self.press("heading", text) for text in ("HEADLINES", "Pro Football Rumors", TEXANS)]

	# -- the tester's report -------------------------------------------------------------------

	def test_nvdaAloneSaysTheHeadingsLevelLast(self):
		self.assertEqual(self.threePressesOfH(), TESTERS_LOG, "NVDA 2026.2 says the tester's log lines")

	def test_quickNavigationSaysTheLevelFirst(self):
		headingOrder.register()
		self.assertEqual(self.threePressesOfH(), LEVEL_FIRST)
		# The same words, in the order the arrow keys read the heading's line in.
		for text in ("HEADLINES", "Pro Football Rumors", TEXANS):
			self.page._speakTextInfoState = None
			arrowed = [word for word in self.arrow(text) if word not in ("Homepage", "Home")]
			self.page._speakTextInfoState = None
			said = [word for word in self.press("heading", text) if word not in ("Homepage", "Home")]
			self.assertEqual(said, arrowed)

	def test_everyWayQuickNavigationReportsAHeading(self):
		headingOrder.register()
		# 1 to 9 move to a heading of that level; NVDA's own TextInfoQuickNavItem and the Elements List's Move to report the same.
		for itemType in ["heading"] + [f"heading{level}" for level in range(1, 10)]:
			for itemClass in (VirtualBufferQuickNavItem, TextInfoQuickNavItem):
				self.page._speakTextInfoState = None
				self.assertEqual(self.press(itemType, TEXANS, itemClass), LEVEL_FIRST[2], itemType)
		self.page._speakTextInfoState = None
		spoken.clear()
		VirtualBufferQuickNavItem("heading", self.page, self.part(TEXANS)).report()
		self.assertEqual(spoken, [LEVEL_FIRST[2]], "the Elements List's Move to: report() with NVDA's own reason")

	def test_theCaretAlreadyInTheHeading(self):
		# Shift+H with the caret inside a heading goes to its start: NVDA was in the heading and the link already.
		headingOrder.register()
		self.page._speakTextInfoState = None
		self.arrow(TEXANS)
		self.assertEqual(self.press("heading", TEXANS), ["heading", "level 2", "link", TEXANS])

	# -- only headings, only quick navigation ------------------------------------------------

	def test_everythingElseKeepsNvdasOrder(self):
		headingOrder.register()
		for itemType in ("link", "unvisitedLink", "formField", "button", "landmark", "headingless", "", None):
			self.page._speakTextInfoState = None
			self.assertEqual(self.press(itemType, TEXANS), TESTERS_LOG[2], f"K and the other quick navigation keys: {itemType!r}")
		self.page._speakTextInfoState = None
		self.assertEqual(self.press("heading", TEXANS, reason=OutputReason.FOCUS), TESTERS_LOG[2], "a heading reported as the focus")
		self.page._speakTextInfoState = None
		spoken.clear()
		speakTextInfo(self.part(TEXANS), reason=OutputReason.FOCUS)
		self.assertEqual(spoken, [TESTERS_LOG[2]], "Tab to the link in the heading")
		self.page._speakTextInfoState = None
		self.assertEqual(self.arrow(TEXANS), LEVEL_FIRST[2], "the arrow keys, as always")

	def test_headingItemTypes(self):
		for itemType in ["heading"] + [f"heading{level}" for level in range(1, 10)]:
			self.assertTrue(headingOrder.isHeading(types.SimpleNamespace(itemType=itemType)), itemType)
		for itemType in ("link", "headingless", "headings", "Heading", "", None, 2):
			self.assertFalse(headingOrder.isHeading(types.SimpleNamespace(itemType=itemType)), itemType)
		self.assertFalse(headingOrder.isHeading(object()), "an item without a type")

	# -- the setting --------------------------------------------------------------------------

	def test_onUnlessTurnedOff(self):
		self.assertTrue(headingOrder.wanted({}))
		self.assertTrue(headingOrder.wanted({headingOrder.STATE_KEY: True}))
		self.assertFalse(headingOrder.wanted({headingOrder.STATE_KEY: False}))
		self.assertFalse(headingOrder.wanted(None))
		self.assertIs(state.DEFAULTS[headingOrder.STATE_KEY], True)

	def test_turnedOffNvdaHasItsOwnBack(self):
		headingOrder.register()
		self.assertTrue(headingOrder.isRegistered())
		self.assertIs(SPEECH._shouldSpeakContentFirst.__wrapped__, _shouldSpeakContentFirst)
		self.assertIs(TextInfoQuickNavItem.report.__wrapped__, NVDA_REPORT)
		self.assertNotIn("report", vars(VirtualBufferQuickNavItem), "subclasses keep using the one report")
		headingOrder.unregister()
		self.assertFalse(headingOrder.isRegistered())
		self.assertIs(SPEECH._shouldSpeakContentFirst, _shouldSpeakContentFirst)
		self.assertIs(TextInfoQuickNavItem.report, NVDA_REPORT)
		self.assertEqual(self.threePressesOfH(), TESTERS_LOG)
		headingOrder.register()
		headingOrder.register()
		self.assertIs(SPEECH._shouldSpeakContentFirst.__wrapped__, _shouldSpeakContentFirst, "registered twice, wrapped once")
		self.assertEqual(self.threePressesOfH(), LEVEL_FIRST)

	def test_anotherAddonsWrapperOverTheAssistants(self):
		headingOrder.register()
		ours = TextInfoQuickNavItem.report
		calls = []

		@functools.wraps(ours)
		def otherAddon(item, *args, **kwargs):
			calls.append(item.itemType)
			return ours(item, *args, **kwargs)

		TextInfoQuickNavItem.report = otherAddon
		self.assertEqual(self.threePressesOfH(), LEVEL_FIRST)
		headingOrder.unregister()
		self.assertIs(TextInfoQuickNavItem.report, otherAddon, "the other add-on's wrapper stays")
		self.assertIs(SPEECH._shouldSpeakContentFirst, _shouldSpeakContentFirst, "NVDA's decision is back")
		self.assertEqual(self.threePressesOfH(), TESTERS_LOG, "the assistant's report, still inside it, does nothing")
		headingOrder.register()
		self.assertIs(TextInfoQuickNavItem.report, otherAddon, "and the assistant doesn't wrap it a second time")
		self.assertEqual(self.threePressesOfH(), LEVEL_FIRST)
		self.assertEqual(len(calls), 9)

	def test_nvdaReloadsItsPlugins(self):
		# NVDA+Control+F3 loads the add-on again, a new copy of the module, while another add-on's wrapper
		# still holds the old copy's report, which does nothing any more.
		headingOrder.register()
		ours = TextInfoQuickNavItem.report

		@functools.wraps(ours)
		def otherAddon(item, *args, **kwargs):
			return ours(item, *args, **kwargs)

		TextInfoQuickNavItem.report = otherAddon
		headingOrder.unregister()
		spec = importlib.util.spec_from_file_location("jawsMigrator.headingOrderLoadedAgain", headingOrder.__file__)
		again = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(again)
		again.register()
		try:
			self.assertIsNot(TextInfoQuickNavItem.report, otherAddon, "the new copy puts its own in place")
			self.assertEqual(self.threePressesOfH(), LEVEL_FIRST)
		finally:
			again.unregister()
		self.assertIs(TextInfoQuickNavItem.report, otherAddon)
		self.assertEqual(self.threePressesOfH(), TESTERS_LOG)

	# -- whatever goes wrong, NVDA goes on as usual --------------------------------------------

	def test_aReportThatFailsLeavesNothingBehind(self):
		headingOrder.register()
		broken = TextInfo(self.page, self.parts[TEXANS], TEXANS)
		broken.getControlFieldSpeech = mock.Mock(side_effect=RuntimeError("the document went away"))
		with self.assertRaises(RuntimeError, msg="NVDA's own error, as without the assistant"):
			VirtualBufferQuickNavItem("heading", self.page, broken).report()
		self.page._speakTextInfoState = None
		self.assertEqual(self.press("link", TEXANS), TESTERS_LOG[2], "the next link is read as NVDA reads it")

	def test_aHeadingOnAnotherThreadChangesNothingHere(self):
		headingOrder.register()
		entered, release = threading.Event(), threading.Event()
		other = Document()

		def slowReport():
			class Slow(TextInfo):
				def getControlFieldSpeech(self, *args, **kwargs):
					entered.set()
					release.wait(5)
					return super().getControlFieldSpeech(*args, **kwargs)

			VirtualBufferQuickNavItem("heading", other, Slow(other, self.parts[TEXANS], TEXANS)).report()

		thread = threading.Thread(target=slowReport)
		thread.start()
		try:
			self.assertTrue(entered.wait(5))
			self.page._speakTextInfoState = None
			self.assertEqual(self.press("link", TEXANS), TESTERS_LOG[2])
		finally:
			release.set()
			thread.join(5)

	def test_nvdaWithoutTheDecisionIsLeftAlone(self):
		del SPEECH._shouldSpeakContentFirst
		try:
			with self.assertLogs("nvda", level="DEBUG") as logged:
				headingOrder.register()
			self.assertIs(TextInfoQuickNavItem.report, NVDA_REPORT, "nothing is wrapped for nothing to change")
			self.assertTrue(any("reads headings as NVDA does" in line for line in logged.output), logged.output)
		finally:
			SPEECH._shouldSpeakContentFirst = _shouldSpeakContentFirst

	def test_whatTheLogSays(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			headingOrder.register()
			self.threePressesOfH()
			self.page._speakTextInfoState = None
			self.press("link", TEXANS)
		lines = [line for line in logged.output if "jawsMigrator" in line]
		self.assertEqual(sum("quick navigation says a heading's level before its text" in line for line in lines), 2, lines)
		self.assertEqual(sum("quick navigation moved to a heading (heading), so NVDA says its level before its text" in line for line in lines), 3, lines)


if __name__ == "__main__":
	unittest.main()
