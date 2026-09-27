# Unit tests for version 1.34, from a tester's report (issue 30, "issue with how NVDA reads certain things on Reddit").
# With 1.33 the tester Alt+Tabbed to an Edge window with a reddit post NVDA hadn't read yet, and NVDA said (the
# tester's paste, and the log's "Speaking" lines):
#     I've had data issues ... : r/Visible and 1 more page - Profile 1 - Microsoft Edge
#     I've had data issues ... : r/Visible
#     same page  link  Skip to main content
# JAWS 2026, on the maintainer's computer with Edge 154 and a copy of the post (driven through its API, speech history
# copied after each step), said the window's name and the page's title, and no line. Coming back to a page it had
# read, JAWS said the line at its cursor ("same page link Skip to main content", where the cursor was left on it), as
# NVDA does. But JAWS's cursor starts on the page's title, which Control+Home says, where NVDA's caret starts on the
# page's first line. NVDA says the line at the caret as it comes into a page
# (browseMode.BrowseModeDocumentTreeInterceptor.event_treeInterceptor_gainFocus).
# - browserPages: the first time NVDA comes into an Edge or Chrome page in browse mode, with the focus on the page
#   itself and the caret on its first line, NVDA says the page's title without that line.
# The imitation NVDA is NVDA 2026.2's own code, word for word: event_treeInterceptor_gainFocus from release-2026.2's
# browseMode.py (checked against it by NvdasOwnCodeTests when NVDA_SOURCE is set), with the object and text speech of
# tests/test_v126_formFields.py (speakObject, getObjectSpeech, speakTextInfo, getTextInfoSpeech,
# getControlFieldSpeech...) and NVDA's own BrowseModeDocumentTreeInterceptor.event_gainFocus. The assistant's code is
# the real one.
# Run: python -m unittest tests.test_v134_pageFirstLine -v

import os
import sys
import textwrap
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v131_redditPage as v131  # noqa: E402

v126 = v131.v126
v125 = v131.v125

import jawsMigrator  # noqa: E402
from jawsMigrator import browserPages  # noqa: E402

Role, State, OutputReason = v126.Role, v126.State, v126.OutputReason
spoken = v126.spoken
field = v126.field

NVDA_TREE_INTERCEPTOR_GAIN_FOCUS = r'''
def event_treeInterceptor_gainFocus(self):
	doSayAll = False
	hadFirstGainFocus = self._hadFirstGainFocus
	if not hadFirstGainFocus:
		# This treeInterceptor is gaining focus for the first time.
		# Fake a focus event on the focus object, as the treeInterceptor may have missed the actual focus event.
		focus = api.getFocusObject()
		self.event_gainFocus(focus, lambda: focus.event_gainFocus())
		if not self.passThrough:
			# We only set the caret position if in browse mode.
			# If in focus mode, the document must have forced the focus somewhere,
			# so we don't want to override it.
			# Update the cached document constant identifier
			# so it can be saved with the last caret position on termination.
			# As the original property may not be available as the document will be already dead.
			# Updating here is necessary as the identifier could have dynamically changed since initial load,
			# such as with  a SPA (single page app)
			self._lastCachedDocumentConstantIdentifier = self.documentConstantIdentifier
			initialPos = self._getInitialCaretPos()
			if initialPos:
				self.selection = self.makeTextInfo(initialPos)
			reportPassThrough(self)
			doSayAll = config.conf["virtualBuffers"]["autoSayAllOnPageLoad"]
		self._hadFirstGainFocus = True

	if not self.passThrough:
		if doSayAll:
			speech.speakObjectProperties(
				self.rootNVDAObject,
				name=True,
				states=True,
				reason=OutputReason.FOCUS,
			)
			sayAll.SayAllHandler.readText(sayAll.CURSOR.CARET)
		else:
			# Speak it like we would speak focus on any other document object.
			# This includes when entering the treeInterceptor for the first time:
			if not hadFirstGainFocus:
				speech.speakObject(self.rootNVDAObject, reason=OutputReason.FOCUS)
			else:
				# And when coming in from an outside object
				# #4069 But not when coming up from a non-rendered descendant.
				ancestors = api.getFocusAncestors()
				fdl = api.getFocusDifferenceLevel()
				try:
					tl = ancestors.index(self.rootNVDAObject)
				except ValueError:
					tl = len(ancestors)
				if fdl <= tl:
					speech.speakObject(self.rootNVDAObject, reason=OutputReason.FOCUS)
			info = self.selection
			if not info.isCollapsed:
				speech.speakPreselectedText(info.text)
			else:
				info.expand(textInfos.UNIT_LINE)
				speech.speakTextInfo(info, reason=OutputReason.CARET, unit=textInfos.UNIT_LINE)

	reportPassThrough(self)
	braille.handler.handleGainFocus(self)'''

#: Where each piece of NVDA's code is, in NVDA 2026.2's source.
NVDA_CODE_FILES = {"NVDA_TREE_INTERCEPTOR_GAIN_FOCUS": "browseMode.py"}

TITLE = "I've had data issues for the past 3 days since I switched from total wireless to visible. I need help : r/Visible"
SIRIUS_TITLE = "College Football Playoffs & Bowls Radio: Listen Live | SiriusXM"
URL = "https://www.reddit.com/r/Visible/comments/1wrqr5q/ive_had_data_issues/"
EDGE = v131.EDGE

#: The post's first lines, as Edge gives them to NVDA's virtual buffer.
LINES = [
	("skip", [field(Role.LINK, 20, (State.LINKED, State.FOCUSABLE, State.INTERNAL_LINK)), "Skip to main content"]),
	("home", [field(Role.LINK, 21, (State.LINKED, State.FOCUSABLE)), "Reddit Home"]),
	("post", ["Showing channels for myStreaming & Most Radios."]),
]
#: What NVDA says for each line at the caret.
SKIP = ["same page", "link", "Skip to main content"]
POST = ["Showing channels for myStreaming & Most Radios."]

#: What NVDA's event_treeInterceptor_gainFocus reads besides the page: the Say All it starts, if it does.
sayAllStarted = []
treeInterceptorScope = {
	"api": v126.api,
	"speech": v126.speechPackage,
	"config": v126.config,
	"OutputReason": OutputReason,
	"textInfos": v126.textInfos,
	"sayAll": types.SimpleNamespace(
		SayAllHandler=types.SimpleNamespace(readText=lambda cursor: sayAllStarted.append(cursor)),
		CURSOR=types.SimpleNamespace(CARET="caret"),
	),
	"reportPassThrough": lambda treeInterceptor, *args, **kwargs: None,
	"braille": types.SimpleNamespace(handler=types.SimpleNamespace(handleGainFocus=lambda obj: None)),
}
#: NVDA's browseMode.BrowseModeDocumentTreeInterceptor: its event_treeInterceptor_gainFocus, on NVDA's event_gainFocus
#: for a page (test_v126_formFields' EdgePage, NVDA's virtualBuffers.gecko_ia2.Gecko_ia2).
BrowseModeDocumentTreeInterceptor = v125.nvdaMethods(
	"BrowseModeDocumentTreeInterceptor",
	[v126.EdgePage],
	[NVDA_TREE_INTERCEPTOR_GAIN_FOCUS],
	treeInterceptorScope,
)
NVDA_GAIN_FOCUS = vars(BrowseModeDocumentTreeInterceptor)["event_treeInterceptor_gainFocus"]


class Line(v131.PageRange):
	"""A line of the page (Gecko_ia2_TextInfo): the caret, collapsed, until NVDA expands it to its line."""

	def __init__(self, page, index):
		super().__init__(page, page.pageLines[index][1])
		self.index = index

	isCollapsed = True

	def expand(self, unit):
		assert unit == v126.textInfos.UNIT_LINE

	def compareEndPoints(self, other, which):
		assert which == "startToStart"
		return (self.index > other.index) - (self.index < other.index)


class ChromeVBuf(BrowseModeDocumentTreeInterceptor):
	"""NVDAObjects.IAccessible.chromium.ChromeVBuf, Edge's and Chrome's page in NVDA's virtual buffer: it has
	browseMode's event_treeInterceptor_gainFocus, as in NVDA."""

	def __init__(self, root, caretLine=0):
		super().__init__(root, {})
		root.treeInterceptor = self
		self.pageLines = LINES
		self.caretLine = caretLine
		self._hadFirstGainFocus = False
		self.documentConstantIdentifier = URL

	def _getInitialCaretPos(self):
		# No caret position NVDA kept for the page: a page NVDA hasn't read in this run.
		return None

	def makeTextInfo(self, position):
		if position == v126.textInfos.POSITION_FIRST:
			return Line(self, 0)
		return super().makeTextInfo(position)

	@property
	def selection(self):
		return Line(self, self.caretLine)


class PageFirstLineTests(unittest.TestCase):
	def setUp(self):
		v131.patchNvda(self)
		chromium = types.ModuleType("NVDAObjects.IAccessible.chromium")
		chromium.ChromeVBuf = ChromeVBuf
		modules = mock.patch.dict(
			sys.modules,
			{
				"NVDAObjects": types.ModuleType("NVDAObjects"),
				"NVDAObjects.IAccessible": types.ModuleType("NVDAObjects.IAccessible"),
				"NVDAObjects.IAccessible.chromium": chromium,
			},
		)
		modules.start()
		self.addCleanup(modules.stop)
		self.addCleanup(self._noAssistantsEvent)
		v126.config.conf["virtualBuffers"] = {"autoSayAllOnPageLoad": False}
		sayAllStarted.clear()
		self.window = v131.browserObject(v126.WebObject, 0, Role.WINDOW, v131.WINDOW_NAME)
		self.root = v131.browserObject(v126.WebObject, 1, Role.DOCUMENT, TITLE, value=None, states=(State.FOCUSABLE, State.READONLY))
		self.focusOn(self.root)

	def _noAssistantsEvent(self):
		if "event_treeInterceptor_gainFocus" in vars(ChromeVBuf):
			del ChromeVBuf.event_treeInterceptor_gainFocus

	def focusOn(self, obj):
		v126.globalVars.focusObject = obj
		v126.globalVars.focusAncestors = [self.window]
		v126.globalVars.focusDifferenceLevel = 1

	def comeInto(self, page):
		"""NVDA's focus comes into the page (eventHandler.doPreGainFocus calls event_treeInterceptor_gainFocus)."""
		spoken.clear()
		page.event_treeInterceptor_gainFocus()
		return list(spoken)

	def test_nvdaSaysTheFirstLine(self):
		self.assertEqual(self.comeInto(ChromeVBuf(self.root)), [[TITLE, "document"], SKIP])

	def test_theTitleAloneAsJawsSaysIt(self):
		browserPages.register()
		# The tester's log with 1.33: the title, then "same page, link, Skip to main content"; JAWS: the title alone.
		self.assertEqual(self.comeInto(ChromeVBuf(self.root)), [[TITLE]])

	def test_aCaretFurtherDownIsSaid(self):
		# The tester's SiriusXM window: NVDA's caret started on "Showing channels for myStreaming & Most Radios."
		browserPages.register()
		self.root.name = SIRIUS_TITLE
		self.assertEqual(self.comeInto(ChromeVBuf(self.root, caretLine=2)), [[SIRIUS_TITLE], POST])

	def test_comingBackSaysTheLineAsJawsDoes(self):
		# JAWS, coming back to a page with its cursor left on the skip link: the title, then "same page link Skip to
		# main content".
		browserPages.register()
		page = ChromeVBuf(self.root)
		self.comeInto(page)
		self.assertEqual(self.comeInto(page), [[TITLE], SKIP])

	def test_focusModeAndSayAllAreNvdas(self):
		browserPages.register()
		page = ChromeVBuf(self.root)
		page.passThrough = True
		# In focus mode NVDA says the page as the focus (its own event_gainFocus) and no line.
		self.assertEqual(self.comeInto(page), [[TITLE]])
		v126.config.conf["virtualBuffers"]["autoSayAllOnPageLoad"] = True
		root = v131.browserObject(v126.WebObject, 2, Role.DOCUMENT, TITLE, value=None, states=(State.FOCUSABLE, State.READONLY))
		self.focusOn(root)
		spoken.clear()
		with mock.patch.object(v126.speechPackage, "speakObjectProperties", lambda obj, **kwargs: spoken.append([obj.name]), create=True):
			ChromeVBuf(root).event_treeInterceptor_gainFocus()
		self.assertEqual(spoken, [[TITLE]])
		self.assertEqual(sayAllStarted, ["caret"])

	def test_theFocusOnAFieldIsNvdas(self):
		# The page put the focus on something in it: NVDA says the line at the caret, as before.
		browserPages.register()
		link = v131.browserObject(v126.WebObject, 3, Role.LINK, "Skip to main content")
		self.focusOn(link)
		page = ChromeVBuf(self.root)
		with mock.patch.object(page, "event_gainFocus", lambda obj, nextHandler: None):
			self.assertEqual(self.comeInto(page), [[TITLE], SKIP])

	def test_otherProgramsAreAsBefore(self):
		browserPages.register()
		self.root.appModule = types.SimpleNamespace(appName="firefox")
		self.assertEqual(self.comeInto(ChromeVBuf(self.root)), [[TITLE, "document"], SKIP])

	def test_turnedOffNvdasOwnIsBack(self):
		browserPages.register()
		self.assertIn("event_treeInterceptor_gainFocus", vars(ChromeVBuf))
		self.assertEqual(self.comeInto(ChromeVBuf(self.root)), [[TITLE]])
		browserPages.unregister()
		self.assertNotIn("event_treeInterceptor_gainFocus", vars(ChromeVBuf))
		self.assertIs(vars(BrowseModeDocumentTreeInterceptor)["event_treeInterceptor_gainFocus"], NVDA_GAIN_FOCUS)
		self.assertEqual(self.comeInto(ChromeVBuf(self.root)), [[TITLE, "document"], SKIP])
		# On and off again: the assistant's is put there once.
		browserPages.register()
		browserPages.register()
		self.assertEqual(self.comeInto(ChromeVBuf(self.root)), [[TITLE]])

	def test_aClassWithItsOwnIsLeftAlone(self):
		def theirs(self):
			return NVDA_GAIN_FOCUS(self)

		ChromeVBuf.event_treeInterceptor_gainFocus = theirs
		browserPages.register()
		self.assertIs(vars(ChromeVBuf)["event_treeInterceptor_gainFocus"], theirs)
		self.assertEqual(self.comeInto(ChromeVBuf(self.root)), [[TITLE], SKIP])
		browserPages.unregister()
		self.assertIs(vars(ChromeVBuf)["event_treeInterceptor_gainFocus"], theirs)


class SettingTests(unittest.TestCase):
	def test_browseModesOwnClassIsOutlookMessages(self):
		# Two parts of the assistant never put their own in the place of the same NVDA function (see the 1.25 notes):
		# outlookMessages has browseMode's event_treeInterceptor_gainFocus; browserPages puts one on the classes of
		# Edge's and Chrome's pages, which take browseMode's.
		source = os.path.dirname(jawsMigrator.__file__)
		users = []
		for name in sorted(os.listdir(source)):
			if name.endswith(".py"):
				with open(os.path.join(source, name), encoding="utf-8") as file:
					if '"event_treeInterceptor_gainFocus"' in file.read():
						users.append(name)
		self.assertEqual(users, ["browserPages.py", "outlookMessages.py"])
		self.assertNotIn("browseMode", [module for module, _ in browserPages.PAGE_CLASSES])


class NvdasOwnCodeTests(unittest.TestCase):
	def test_theCodeIsNvdas(self):
		# Each piece is in NVDA 2026.2's source, as a method, when a copy of it is around: set NVDA_SOURCE to its
		# source folder.
		source = os.environ.get("NVDA_SOURCE")
		if not source:
			self.skipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
		for name, path in NVDA_CODE_FILES.items():
			with open(os.path.join(source, *path.split("/")), encoding="utf-8") as f:
				text = f.read().replace("\r\n", "\n")
			block = globals()[name].strip("\n")
			self.assertIn(textwrap.indent(block, "\t"), text, name)


if __name__ == "__main__":
	unittest.main()
