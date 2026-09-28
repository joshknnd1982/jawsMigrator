# Unit tests for version 1.40, from a tester's report (issue 38, "is this how Jaws pronounces things when you go
# back?"). On reddit.com's r/Visible in Edge, with JAWS Migration Assistant 1.38, the tester pressed H to a post, Enter,
# Down Arrow, H, and Alt+Left. NVDA 2026.2 said (NVDA log 2026-09-28 13.21.14.zip, nvda.log):
#     13:20:40.746 Speaking ['link', 'heading', 'level 2', 'Bi-weekly Megathread for referral codes - please only post codes here']
#     13:20:45.883 Speaking ['Downgrading is a nightmare', 'visited', 'heading', 'level 2', 'link']
#     13:20:47.380 Browse Mode Caret Fix: saved link activation docKey='https://www.reddit.com/r/Visible/' stackDepth=4
#     13:20:47.881 Browse Mode Caret Fix: moved newly opened Reddit post to document top
#     13:20:51.259 Speaking ['main region end', 'Downgrading is a nightmare : r/Visible']
#     13:20:52.841 Speaking ['Post Title: Downgrading is a nightmare', 'heading', 'level 1']
#     13:20:55.133 Input: kb(laptop):alt+leftArrow
#     13:20:55.135 Speaking ['Back']
#     13:20:55.217 Speaking ['Going back']
#     13:20:55.669 Browse Mode Caret Fix: restored saved position
#     13:20:56.076 Speaking ['main region end', 'main region', 'heading', 'level 2', 'visited', 'link', 'Downgrading is a nightmare']
#     13:20:56.078 jawsMigrator: after Back or Forward, the page changed its address without loading, so NVDA reads the line at the caret, ...
# JAWS 2026 was run live on the maintainer's computer (Edge 154, driven through FreedomSci.JawsApi, its speech history
# copied after each script), on a copy of the subreddit and a plain two-page site:
#     SayLine and Down Arrow on the post's title (a link in a heading): "visited  heading level 2  Link  Downgrading is a nightmare"
#     SayLine and Down Arrow on a highlight (a heading in a link):     "heading level 2  Link  Bi-weekly Megathread ..."
#     SayLine on a heading:                                            "heading level 1  r/Visible"
#     GoBack on the plain site (Alt+Left): "Back", "Going back", "Loading page", "Loading complete", "Plain page one",
#         "visited  heading level 2  Link  Go to page two"; in 3 of 5 runs "Plain page two" (the page it had left) and
#         "main region end" came before the line, never "main region".
# JAWS's DocumentLoadedEvent calls SayLine after GoBack and GoForward (Default.JSS, BackForward), and SayLine names no
# region. Two things differ:
# - backForward: the line after Back was read against the fields NVDA kept from the post, and reddit draws the
#   subreddit in a new main region, so NVDA said the post's main region end and the subreddit's start. Now the line is
#   read as NVDA+Up Arrow reads it (the line's own fields kept first, OutputReason.ONLYCACHE), as JAWS's SayLine.
# - linkSpeech: reading a line, NVDA said "heading, level 2, visited, link" for a link in a heading and "link, heading,
#   level 2" for a heading in a link. JAWS says the link's states, the heading, then "Link", either way.
# The imitation NVDA is tests/test_v136_backForward.py's: NVDA 2026.2's own speakTextInfo, getTextInfoSpeech,
# getControlFieldSpeech and TextInfo.getControlFieldSpeech, word for word (tests/test_v125_linkSpeech.py), with the
# tester's settings, and Browse Mode Caret Fix 3.0.24's own code. The assistant's code (backForward, linkSpeech,
# quickNavHeadings, webRegions) is the real one.
# Run: python -m unittest tests.test_v140_backLine -v

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v136_backForward as v136  # noqa: E402

v125 = v136.v125

from jawsMigrator import backForward, linkSpeech, webRegions  # noqa: E402

Role, State, OutputReason = v125.Role, v125.State, v125.OutputReason
textInfos, spoken = v125.textInfos, v125.spoken
heading, link, landmark = v125.heading, v125.link, v125.landmark

SUBREDDIT = v136.SUBREDDIT
POST = "https://www.reddit.com/r/Visible/comments/1wscx0s/downgrading_is_a_nightmare/"
LIKE = "https://www.reddit.com/r/Visible/comments/1wsdcwf/i_like_visible/"
BIWEEKLY = "https://www.reddit.com/r/Visible/comments/1wsff5a/biweekly_megathread_for_referral_codes_please/"
AUTHOR = "Author: u/tekdemon 4 hr. ago"
TITLE = "Downgrading is a nightmare"
HIGHLIGHT = "Bi-weekly Megathread for referral codes - please only post codes here"


def feed(main):
	"""The subreddit's lines in its main region ``main``: reddit draws a new one each time it shows the subreddit."""
	return [
		[link(SUBREDDIT + "#main-content", 10), "Skip to main content"],
		[main, heading(1, 11), "r/Visible"],
		# A highlight: the link holds the heading.
		[main, link(BIWEEKLY, 12), heading(2, 13), HIGHLIGHT],
		[main, link(BIWEEKLY, 14), "16 votes • 209 comments"],
		[main, heading(1, 15), "Feed"],
		[main, heading(2, 16), link(LIKE, 17, visited=True, description="Author: u/radargru 4 hr. ago", descriptionFrom="aria-describedby"), "I like visible ..."],
		# A post's title: the heading holds the link, with the author and age as its description.
		[main, heading(2, 18), link(POST, 19, visited=True, description=AUTHOR, descriptionFrom="aria-describedby"), TITLE],
		[main, link(POST, 20, visited=True), "I tried to downgrade my plan and it took three chats."],
	]


RVISIBLE, HIGHLIGHT_LINE, VOTES_LINE, FEED_LINE, LIKE_LINE, TITLE_LINE, PREVIEW_LINE = 1, 2, 3, 4, 5, 6, 7
MAIN_FIRST, MAIN_POST, MAIN_BACK = landmark("main", 2), landmark("main", 30), landmark("main", 40)
#: The post, as the tester read it: its page title above its main region.
POST_PAGE = [
	[link(POST + "#main-content", 21), "Skip to main content"],
	[TITLE + " : r/Visible"],
	[MAIN_POST, heading(1, 22), "Post Title: " + TITLE],
	[MAIN_POST, "I tried to downgrade my plan and it took three chats."],
]
POST_TITLE_LINE = 2

#: What NVDA said in the log, from H to the post's title.
LOGGED = [
	[TITLE, "visited", "heading", "level 2", "link"],
	["main region end", TITLE + " : r/Visible"],
	["Post Title: " + TITLE, "heading", "level 1"],
	["Back"],
	["Going back"],
	["main region end", "main region", "heading", "level 2", "visited", "link", TITLE],
]


def readLineAsIn138(document):
	"""backForward.readLine in 1.36 to 1.39: the line, as NVDA says it when the caret moves there."""
	info = document.makeTextInfo(textInfos.POSITION_CARET)
	info.expand(textInfos.UNIT_LINE)
	sys.modules["speech"].speakTextInfo(info, unit=textInfos.UNIT_LINE, reason=OutputReason.CARET)


class Reddit:
	"""reddit.com's own code in Edge: the post opens in the same page, and Back draws the subreddit again, in a new main
	region. Edge says "Going back" (the tester set MS Edge Discard Announcements to say it)."""

	def __init__(self, nvda, page):
		self.nvda, self.page = nvda, page

	def activate(self, treeInterceptor, *args, **kwargs):
		self.nvda.clock.callLater(480, self.page.show, POST, POST_PAGE, TITLE + " : r/Visible")

	def back(self):
		self.nvda.clock.callLater(82, self.nvda.say, ["Going back"])
		self.nvda.clock.callLater(400, self.page.show, SUBREDDIT, feed(MAIN_BACK), v136.SUBREDDIT_TITLE)

	def forward(self):
		pass


class TesterTests(unittest.TestCase):
	"""The tester's steps on reddit, with NVDA 2026.2's own speech code, Browse Mode Caret Fix's own code, and the
	assistant's quick navigation, links, regions and Back as the tester has them."""

	def setUp(self):
		v136.TesterTests.setUp(self)
		self.page = v136.Page(self, SUBREDDIT, feed(MAIN_FIRST))
		self.reddit = self.site = Reddit(self, self.page)
		self.focus = self.windowsFocus = self.page.rootNVDAObject
		# webRegions says a web page's regions with JAWS's words, on the text of Edge's pages.
		gecko = types.ModuleType("virtualBuffers.gecko_ia2")
		gecko.Gecko_ia2_TextInfo = v125.GeckoVBufTextInfo
		speechModule = types.ModuleType("speech.speech")
		speechModule.getObjectPropertiesSpeech = lambda obj, reason=None, **kwargs: []
		self.speech.speech = speechModule
		ia2Web = types.ModuleType("NVDAObjects.IAccessible.ia2Web")
		ia2Web.Ia2Web = type("Ia2Web", (), {})
		modules = mock.patch.dict(
			sys.modules,
			{
				"aria": types.SimpleNamespace(landmarkRoles=v125.speechScope["aria"].landmarkRoles),
				"virtualBuffers.gecko_ia2": gecko,
				"speech.speech": speechModule,
				"NVDAObjects.IAccessible": types.ModuleType("NVDAObjects.IAccessible"),
				"NVDAObjects.IAccessible.ia2Web": ia2Web,
			},
		)
		modules.start()
		self.addCleanup(modules.stop)
		self.addCleanup(self._restoreRegions)
		# The log names each kind of line once while NVDA runs.
		linkSpeech._loggedLines.clear()

	def _restoreRegions(self):
		webRegions.unregister()
		webRegions._replaced.clear()
		webRegions._failed = False
		if "getControlFieldSpeech" in vars(v125.GeckoVBufTextInfo):
			del v125.GeckoVBufTextInfo.getControlFieldSpeech
		linkSpeech._local.lineInner = None

	_restoreNvda = v136.TesterTests._restoreNvda
	setFocusObject = v136.TesterTests.setFocusObject
	say = v136.TesterTests.say
	browserFocusEvent = v136.TesterTests.browserFocusEvent
	gainFocus = v136.TesterTests.gainFocus
	withCaretFix = v136.TesterTests.withCaretFix
	press = v136.TesterTests.press
	quickNav = v136.TesterTests.quickNav

	def asTheTesterHasIt(self, version="1.40"):
		"""The assistant as the tester runs it: quick navigation, links, regions and Back as JAWS has them. Up to 1.39
		the line after Back was read against the page left, and a line's link and heading were said in NVDA's order."""
		v136.TesterTests.asTheTesterHasIt(self)
		webRegions.register()
		self.assertTrue(webRegions.isRegistered())
		self.assertFalse(webRegions._failed, "webRegions is on Edge's page text")
		if version != "1.40":
			for name, value in (("readLine", readLineAsIn138),):
				patcher = mock.patch.object(backForward, name, value)
				patcher.start()
				self.addCleanup(patcher.stop)
			patcher = mock.patch.object(linkSpeech, "_lineTogether", lambda *args, **kwargs: None)
			patcher.start()
			self.addCleanup(patcher.stop)

	def startOn(self, index):
		"""The caret on a line NVDA has read, as the tester's was: NVDA keeps what that line is in."""
		self.page.caret = index
		self.speech.speakTextInfo(v136.Line(self.page, index), unit=textInfos.UNIT_LINE, reason=OutputReason.CARET)
		spoken.clear()

	def arrow(self, direction=1):
		"""Down Arrow or Up Arrow: NVDA moves browse mode's caret a line and says the line."""
		self.press("downArrow" if direction > 0 else "upArrow")
		self.page.caret += direction
		self.speech.speakTextInfo(v136.Line(self.page, self.page.caret), unit=textInfos.UNIT_LINE, reason=OutputReason.CARET)
		return spoken[-1]

	def theTestersSteps(self):
		"""H to the post's title, Enter, Down Arrow, H, then Alt+Left, 7 seconds of it."""
		self.quickNav(TITLE_LINE)
		self.press("enter")
		self.caretFix._patched_activatePosition(self.page)
		self.clock.run(5)
		self.assertEqual(self.page.caret, 0, "Browse Mode Caret Fix moved the post's page to its top")
		self.arrow()
		self.quickNav(POST_TITLE_LINE)
		self.press("alt+leftArrow")
		self.clock.run(7)
		return list(spoken)

	# -- the tester's report ---------------------------------------------------------------------------------------

	def test_nvdaSaidWhatTheLogSays(self):
		self.withCaretFix()
		self.asTheTesterHasIt("1.39")
		self.assertEqual(self.theTestersSteps(), LOGGED)
		self.assertEqual(self.page.caret, TITLE_LINE, "Browse Mode Caret Fix put the caret back on the post's title")

	def test_backSaidAsJawsSaysIt(self):
		self.withCaretFix()
		self.asTheTesterHasIt()
		with mock.patch.object(linkSpeech, "_log") as log:
			said = self.theTestersSteps()
		self.assertEqual(said[:5], LOGGED[:5], "the same up to Back and Edge's Going back")
		# JAWS's SayLine: "visited  heading level 2  Link  Downgrading is a nightmare", no region.
		self.assertEqual(said[5:], [["visited", "heading", "level 2", "link", TITLE]])
		self.assertEqual(self.page.caret, TITLE_LINE)
		noted = [call.args[0] for call in log.return_value.debug.call_args_list]
		self.assertTrue(any("heading and a link" in line and "visited, heading, level 2, link" in line for line in noted), noted)

	def test_theNextLinesAfterBack(self):
		# NVDA keeps the line's own fields: the next line in the same main region is said without it, and leaving it is
		# said as the arrow keys say it (JAWS: "main region end").
		self.withCaretFix()
		self.asTheTesterHasIt()
		self.theTestersSteps()
		spoken.clear()
		self.assertEqual(self.arrow(), ["visited", "link", "I tried to downgrade my plan and it took three chats."])
		self.page.caret = RVISIBLE
		self.speech.speakTextInfo(v136.Line(self.page, RVISIBLE), unit=textInfos.UNIT_LINE, reason=OutputReason.CARET)
		self.assertEqual(spoken[-1], ["heading", "level 1", "r/Visible"])
		self.assertEqual(self.arrow(-1), ["main region end", "same page", "link", "Skip to main content"])

	def test_lineAfterBackWithoutBrowseModeCaretFix(self):
		# Without Browse Mode Caret Fix, NVDA's buffer keeps the caret's offset as reddit changes the page: the line there,
		# the highlight, is read without the regions, as JAWS's SayLine: "heading level 2  Link  Bi-weekly ...".
		self.asTheTesterHasIt()
		self.quickNav(TITLE_LINE)
		self.press("enter")
		self.reddit.activate(self.page)
		self.clock.run(5)
		self.quickNav(POST_TITLE_LINE)
		self.press("alt+leftArrow")
		self.clock.run(7)
		self.assertEqual(self.page.caret, HIGHLIGHT_LINE)
		self.assertEqual(spoken[-3:], [["Back"], ["Going back"], ["heading", "level 2", "link", HIGHLIGHT]])

	def test_aHeadingLineAfterBack(self):
		# JAWS's SayLine on a heading: "heading level 1  r/Visible".
		self.asTheTesterHasIt()
		self.page.show(POST, POST_PAGE)
		self.page.caret = POST_TITLE_LINE
		self.speech.speakTextInfo(v136.Line(self.page, POST_TITLE_LINE), unit=textInfos.UNIT_LINE, reason=OutputReason.CARET)
		self.page.show(SUBREDDIT, feed(MAIN_BACK))
		self.page.caret = RVISIBLE
		spoken.clear()
		backForward.readLine(self.page)
		self.assertEqual(spoken, [["heading", "level 1", "r/Visible"]])

	def test_asIn1_39TheLineWasReadAgainstThePost(self):
		self.asTheTesterHasIt("1.39")
		self.page.show(POST, POST_PAGE)
		self.page.caret = POST_TITLE_LINE
		self.speech.speakTextInfo(v136.Line(self.page, POST_TITLE_LINE), unit=textInfos.UNIT_LINE, reason=OutputReason.CARET)
		self.page.show(SUBREDDIT, feed(MAIN_BACK))
		self.page.caret = RVISIBLE
		spoken.clear()
		backForward.readLine(self.page)
		self.assertEqual(spoken, [["main region end", "main region", "heading", "level 1", "r/Visible"]])

	# -- the arrow keys ----------------------------------------------------------------------------------------------

	def test_arrowingAsTheLogSays(self):
		# 13:20:40.746: Up Arrow from "16 votes" to the highlight.
		self.asTheTesterHasIt("1.39")
		self.startOn(VOTES_LINE)
		self.assertEqual(self.arrow(-1), ["link", "heading", "level 2", HIGHLIGHT])
		self.startOn(FEED_LINE)
		self.assertEqual(self.arrow(), ["heading", "level 2", "visited", "link", "I like visible ..."])

	def test_arrowingAsJawsSaysIt(self):
		self.asTheTesterHasIt()
		self.startOn(VOTES_LINE)
		# JAWS: "heading level 2  Link  Bi-weekly Megathread ...", then "Link  16 votes • 209 comments".
		self.assertEqual(self.arrow(-1), ["heading", "level 2", "link", HIGHLIGHT])
		self.assertEqual(self.arrow(), ["link", "16 votes • 209 comments"])
		self.assertEqual(self.arrow(), ["heading", "level 1", "Feed"])
		# JAWS: "heading level 2  Link  I like visible ..." (not visited in the live run), "visited  heading level 2  Link
		# Downgrading is a nightmare", "visited  Link  I tried to downgrade ...".
		self.assertEqual(self.arrow(), ["visited", "heading", "level 2", "link", "I like visible ..."])
		self.assertEqual(self.arrow(), ["visited", "heading", "level 2", "link", TITLE])
		self.assertEqual(self.arrow(), ["visited", "link", "I tried to downgrade my plan and it took three chats."])

	def test_notVisited(self):
		self.asTheTesterHasIt()
		self.page.lines[LIKE_LINE] = [MAIN_FIRST, heading(2, 16), link(LIKE, 17), "I like visible ..."]
		self.startOn(FEED_LINE)
		self.assertEqual(self.arrow(), ["heading", "level 2", "link", "I like visible ..."])

	def test_eachFieldOnce(self):
		# The inner field is said with the outer, once: NVDA's own ask for it says nothing, and nothing is left over for
		# the next line.
		self.asTheTesterHasIt()
		self.startOn(LIKE_LINE)
		for _line in range(2):
			self.arrow()
		self.assertEqual(spoken[-2:], [["visited", "heading", "level 2", "link", TITLE], ["visited", "link", "I tried to downgrade my plan and it took three chats."]])
		self.assertIsNone(getattr(linkSpeech._local, "lineInner", None))

	def test_aLinkThatIsNotAtTheLinesStart(self):
		# A heading whose link comes after some text: the link is inside the line, not where it starts, and is said where
		# NVDA says it.
		self.asTheTesterHasIt()
		self.page.lines.append([MAIN_FIRST, heading(2, 50), "Read: ", link(POST, 51, visited=True), "the post"])
		self.startOn(len(self.page.lines) - 2)
		self.assertEqual(self.arrow(), ["heading", "level 2", "Read: ", "visited", "link", "the post"])

	def test_quickNavigationAsBefore(self):
		# H: "Downgrading is a nightmare  visited  heading level 2  Link" (JAWS), as in the log.
		self.asTheTesterHasIt()
		self.quickNav(TITLE_LINE)
		self.quickNav(HIGHLIGHT_LINE)
		self.assertEqual(spoken, [[TITLE, "visited", "heading", "level 2", "link"], [HIGHLIGHT, "heading", "level 2", "link"]])

	def test_turnedOff(self):
		# Links said as NVDA says them (Settings, JAWS Migration Assistant): NVDA's own order.
		self.asTheTesterHasIt()
		linkSpeech.unregister()
		self.startOn(VOTES_LINE)
		self.assertEqual(self.arrow(-1), ["link", "heading", "level 2", HIGHLIGHT])
		self.startOn(LIKE_LINE)
		self.assertEqual(self.arrow(), ["heading", "level 2", "visited", "link", TITLE])

	def test_characterByCharacter(self):
		# Moving by character or word, NVDA asks for the fields with extraDetail, and says them as it does.
		self.asTheTesterHasIt()
		info = v136.Line(self.page, TITLE_LINE)
		fields = [item.field for item in info.getTextWithFields() if isinstance(item, textInfos.FieldCommand)]
		formatConfig = dict(v125.config.conf["documentFormatting"], extraDetail=True)
		with mock.patch.object(linkSpeech, "_innerAtLineStart", side_effect=AssertionError("not looked at")):
			said = info.getControlFieldSpeech(fields[1], fields[:1], "start_addedToControlFieldStack", formatConfig, True, OutputReason.CARET)
		self.assertEqual(said, v125.NVDA_TEXT_FIELD_SPEECH(info, fields[1], fields[:1], "start_addedToControlFieldStack", formatConfig, True, OutputReason.CARET))

	def test_aFailureSaysNvdasOwn(self):
		# If the line can't be read again, NVDA says it as it does, and the log says why once.
		self.asTheTesterHasIt()
		self.startOn(LIKE_LINE)
		with mock.patch.object(linkSpeech, "_innerAtLineStart", side_effect=RuntimeError("gone")), mock.patch.object(linkSpeech, "_log"):
			self.assertEqual(self.arrow(), ["heading", "level 2", "visited", "link", TITLE])
		self.assertTrue(linkSpeech._failed)


# -- JAWS's own files -------------------------------------------------------------------------------------------------


@unittest.skipUnless(os.path.isdir(os.path.join(v136.JAWS, "Scripts")), "JAWS 2026 isn't installed here")
class JawsOwnFilesTests(unittest.TestCase):
	"""JAWS 2026's scripts: GoBack and GoForward set BackForward, and the document's load then says the line with
	SayLine, which names no region."""

	def test_goBackSaysTheLineWithSayLine(self):
		ia2Browser = v136.jawsFile("Scripts", "IA2Browser.jss")
		for script in ("Script GoBack ()", "Script GoForward ()"):
			start = ia2Browser.index(script)
			self.assertIn("let BackForward = 1", ia2Browser[start : ia2Browser.index("EndScript", start)])
		default = v136.jawsFile("Scripts", "Default.JSS")
		start = default.index("Void Function DocumentLoadedEvent ()")
		body = default[start : default.index("EndFunction", start)]
		self.assertIn("if BackForward == 1 then\n\tSayLine()\n\tlet BackForward=0\n\treturn", body)


if __name__ == "__main__":
	unittest.main()
