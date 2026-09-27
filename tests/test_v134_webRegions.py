# Unit tests for version 1.34, from a tester's report (issue 30, "issue with how NVDA reads certain things on Reddit").
# With 1.33 the tester Alt+Tabbed between Outlook and Edge's windows and pasted what NVDA said, and asked: "Do you
# think we should have it match? I think if it does Claude should do tests with Jaws to make sure I'm not missing
# anything." He had been asked (issue 30, 1.33) whether NVDA should use JAWS's words for landmarks and groups: on the
# GitHub tab his JAWS said "MainRegion" and "new Comment group", where NVDA said "main landmark" and "new Comment
# grouping".
# JAWS 2026 was run on the maintainer's computer, on Edge 154 with copies of the tester's reddit and GitHub pages,
# driven through its API (FreedomSci.JawsApi), with its speech history copied after each key. It said:
#     Tab through the GitHub copy:        "BannerRegion", "Global NavigationRegion", "Homepage Link"
#                                         "MainRegion", "new Comment group", "Add a comment edit" ...
#     Alt+Tab back to the GitHub tab:     ... "MainRegion", "new Comment group", "Paste, drop, or click to add files Button"
#     Alt+Tab back to a reply box:        ... "MainRegion", "Reply FormRegion", "Join the conversation edit"
#     Tab out of the reddit copy's reply: "ContentInfoRegion", "Reddit Rules Link"
#     Down Arrow through the reddit copy: "same page link Skip to main content", "Reddit navigation region",
#         "Link Reddit Home", ..., "Link Log In", "Reddit navigation region end", "Primary navigation region",
#         "list of 2 items", "• Link Home", "• Link Popular", "list end", "Primary navigation region end",
#         "main region", "heading level 1 I've had data issues ...", "My data stops working ...",
#         "Community actions region", "Upvote Button", "Share Button", "Community actions region end",
#         "Join the conversation", "Join the conversation edit", "Comment by visible_help article",
#         "Try resetting your network settings.", "Comment by visible_help article end", "main region end"
#     Down Arrow through the GitHub copy: ..., "group start new Comment", "Add a comment", "Add a comment edit ...",
#         "group end new Comment", "main region end"
# The banner, the search form, the reply form, the complementary region and the footer weren't named with the arrow
# keys: JAWS's Default.jcf, [VirtualCursorVerbosity] at Medium, has MainRegion and NavigationRegion 1, BannerRegion,
# ComplementaryRegion, ContentInfoRegion, FormRegion and SearchRegion 0. jfw.exe has "List of %d items" and "list end";
# FsDomSrv.dll has "group start %s" and "group end %s".
# - webRegions: on web pages, what browse mode says for a field of the page's text and what NVDA says for an object the
#   focus comes into use JAWS's words for regions, groups, lists and articles.
# The imitation NVDA is NVDA 2026.2's own code, word for word, as tests/test_v125_linkSpeech.py and
# tests/test_v126_formFields.py took it: speakTextInfo, getTextInfoSpeech, getControlFieldSpeech,
# TextInfo.getControlFieldSpeech, getObjectSpeech, getObjectPropertiesSpeech, getPropertiesSpeech, Ia2Web's roleText
# and landmark, aria.landmarkRoles, NVDA's roles and states and the tester's settings. The assistant's code is the real one.
# Run: python -m unittest tests.test_v134_webRegions -v

import os
import sys
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
from jawsMigrator import state, webRegions  # noqa: E402

Role, State, OutputReason = v126.Role, v126.State, v126.OutputReason
spoken = v126.spoken
field = v126.field


class Gecko_ia2_TextInfo(v131.PageRange):
	"""NVDA's virtualBuffers.gecko_ia2.Gecko_ia2_TextInfo, the text of Edge's, Chrome's and Firefox's pages: it has
	textInfos.TextInfo's getControlFieldSpeech, as in NVDA."""


class ChromeVBufTextInfo(Gecko_ia2_TextInfo):
	"""NVDAObjects.IAccessible.chromium.ChromeVBufTextInfo: Edge's page's text."""


def landmark(kind, uniqueID, **attributes):
	return field(Role.LANDMARK, uniqueID, landmark=kind, **attributes)


def link(uniqueID, *states):
	return field(Role.LINK, uniqueID, (State.LINKED, State.FOCUSABLE, *states))


# The reddit copy's containers, as Edge gives them to NVDA's virtual buffer (Gecko_ia2_TextInfo._normalizeControlField
# gives a landmark its "landmark", and a named form, which Edge gives the role form, "form" too).
BANNER = landmark("banner", 1)
REDDIT_NAV = landmark("navigation", 2, name="Reddit")
SEARCH = landmark("search", 3)
PRIMARY_NAV = landmark("navigation", 4, name="Primary")
LIST = field(Role.LIST, 5, (State.READONLY,), _childcontrolcount=2)
MAIN = landmark("main", 6)
ACTIONS = field(Role.REGION, 7, name="Community actions")
REPLY_FORM = field(Role.FORM, 8, name="Reply", landmark="form")
COMMENT = field(Role.ARTICLE, 9, name="Comment by visible_help")
ASIDE = landmark("complementary", 10, name="About Community")
FOOTER = landmark("contentinfo", 11)
# The GitHub copy's.
GLOBAL_NAV = landmark("navigation", 12, name="Global")
NEW_COMMENT = field(Role.GROUPING, 13, name="new Comment")

#: The reddit copy, line by line, as the arrow keys read it (edit fields are left out: E and quickNavHeadings are theirs).
REDDIT = [
	("skip", [link(20, State.INTERNAL_LINK), "Skip to main content"]),
	("home", [BANNER, REDDIT_NAV, link(21), "Reddit Home"]),
	("login", [BANNER, REDDIT_NAV, link(22), "Log In"]),
	("popularHome", [PRIMARY_NAV, LIST, field(Role.LISTITEM, 23), link(24), "Home"]),
	("popular", [PRIMARY_NAV, LIST, field(Role.LISTITEM, 25), link(26), "Popular"]),
	("title", [MAIN, field(Role.HEADING, 27, level="1"), "I've had data issues"]),
	("post", [MAIN, "My data stops working every afternoon."]),
	("upvote", [MAIN, ACTIONS, field(Role.BUTTON, 28, (State.FOCUSABLE,)), "Upvote"]),
	("share", [MAIN, ACTIONS, field(Role.BUTTON, 29, (State.FOCUSABLE,)), "Share"]),
	("reply", [MAIN, REPLY_FORM, "Join the conversation"]),
	("comment", [MAIN, COMMENT, "Try resetting your network settings."]),
	("about", [ASIDE, field(Role.HEADING, 30, level="2"), "r/Visible"]),
	("rules", [FOOTER, link(31), "Reddit Rules"]),
]
#: The GitHub copy, around its comment box.
GITHUB = [
	("paragraph", [MAIN, "What NVDA says when a reddit post opens in Edge."]),
	("label", [MAIN, NEW_COMMENT, "Add a comment"]),
	("after", [MAIN, "Terms"]),
	("footer", [FOOTER, link(40), "Terms"]),
]


def patchNvda(testCase):
	"""NVDA's modules, as the assistant and NVDA's own code import them, for the length of a test."""
	v131.patchNvda(testCase)
	gecko = types.ModuleType("virtualBuffers.gecko_ia2")
	gecko.Gecko_ia2_TextInfo = Gecko_ia2_TextInfo
	ia2Web = types.ModuleType("NVDAObjects.IAccessible.ia2Web")
	ia2Web.Ia2Web = v126.Ia2Web
	modules = mock.patch.dict(
		sys.modules,
		{
			"virtualBuffers": types.ModuleType("virtualBuffers"),
			"virtualBuffers.gecko_ia2": gecko,
			"NVDAObjects": types.ModuleType("NVDAObjects"),
			"NVDAObjects.IAccessible": types.ModuleType("NVDAObjects.IAccessible"),
			"NVDAObjects.IAccessible.ia2Web": ia2Web,
		},
	)
	modules.start()
	testCase.addCleanup(modules.stop)
	testCase.addCleanup(restoreNvda)


def restoreNvda():
	webRegions.unregister()
	webRegions._replaced.clear()
	webRegions._failed = False
	webRegions._logged.clear()
	for cls in (Gecko_ia2_TextInfo, ChromeVBufTextInfo):
		vars(cls).get("getControlFieldSpeech") and delattr(cls, "getControlFieldSpeech")
	v126.speechScope["getObjectPropertiesSpeech"] = NVDA_OBJECT_PROPERTIES


NVDA_OBJECT_PROPERTIES = v126.speechScope["getObjectPropertiesSpeech"]


class Page:
	"""Edge's page in browse mode, as NVDA's speech asks it: the cache of what the cursor is in is kept on it."""

	def getLinkTypeInDocument(self, url):
		return None


class WebRegionsCase(unittest.TestCase):
	def setUp(self):
		patchNvda(self)
		self.page = Page()

	def read(self, lines, reason=OutputReason.CARET):
		"""The arrow keys (or Say All) line by line from the top, or Tab to each line's innermost field (``FOCUS``), as
		browse mode says them: NVDA's speakTextInfo for the caret, or for the focus."""
		said = {}
		for name, parts in lines:
			spoken.clear()
			info = ChromeVBufTextInfo(self.page, parts)
			if reason == OutputReason.FOCUS:
				v126.speechPackage.speakTextInfo(info, reason=reason)
			else:
				v126.speechPackage.speakTextInfo(info, unit=v126.textInfos.UNIT_LINE, reason=reason)
			self.assertLessEqual(len(spoken), 1)
			said[name] = spoken[0] if spoken else []
		return said

	def objectSpeech(self, obj, reason=OutputReason.FOCUSENTERED):
		"""What NVDA says for an object of the page the focus comes into (NVDAObject.event_focusEntered), or for the focus."""
		return [item for item in v126.speechScope["getObjectSpeech"](obj, reason=reason) if isinstance(item, str) and item]


# -- the arrow keys ---------------------------------------------------------------------------------------------------


class ReadingTests(WebRegionsCase):
	def test_nvdaSaysItsOwnWords(self):
		said = self.read(REDDIT)
		self.assertEqual(said["home"], ["banner landmark", "navigation landmark", "link", "Reddit Home"])
		self.assertEqual(said["popularHome"], ["navigation landmark", "list", "with 2 items", "link", "Home"])
		self.assertEqual(said["title"], ["out of list", "main landmark", "heading", "level 1", "I've had data issues"])
		self.assertEqual(said["upvote"], ["region", "button", "Upvote"])
		self.assertEqual(said["reply"], ["out of region", "form", "Join the conversation"])
		self.assertEqual(said["comment"], ["out of form", "article", "Try resetting your network settings."])
		self.assertEqual(said["about"], ["out of article", "complementary landmark", "heading", "level 2", "r/Visible"])
		self.assertEqual(said["rules"], ["content info landmark", "link", "Reddit Rules"])

	def test_saidAsJawsSaysIt(self):
		webRegions.register()
		self.assertEqual(
			self.read(REDDIT),
			{
				"skip": ["same page", "link", "Skip to main content"],
				# JAWS: "Reddit navigation region"; no banner, no search region.
				"home": ["Reddit", "navigation region", "link", "Reddit Home"],
				"login": ["link", "Log In"],
				# JAWS: "Reddit navigation region end", "Primary navigation region", "list of 2 items".
				"popularHome": ["Reddit", "navigation region end", "Primary", "navigation region", "list of 2 items", "link", "Home"],
				"popular": ["link", "Popular"],
				# JAWS: "list end", "Primary navigation region end", "main region".
				"title": ["list end", "Primary", "navigation region end", "main region", "heading", "level 1", "I've had data issues"],
				"post": ["My data stops working every afternoon."],
				# JAWS: "Community actions region".
				"upvote": ["Community actions", "region", "button", "Upvote"],
				"share": ["button", "Share"],
				# JAWS: "Community actions region end", then the reply box's line: no form region.
				"reply": ["Community actions", "region end", "Join the conversation"],
				# JAWS: "Comment by visible_help article".
				"comment": ["Comment by visible_help", "article", "Try resetting your network settings."],
				# JAWS: "Comment by visible_help article end", "main region end"; no complementary region.
				"about": ["Comment by visible_help", "article end", "main region end", "heading", "level 2", "r/Visible"],
				# No content info region.
				"rules": ["link", "Reddit Rules"],
			},
		)

	def test_aGroupAsJawsSaysIt(self):
		# NVDA names a grouping only for the focus and quick navigation.
		self.assertEqual(self.read(GITHUB)["label"], ["grouping", "Add a comment"])
		webRegions.register()
		self.page = Page()
		said = self.read(GITHUB)
		# JAWS: "group start new Comment", "Add a comment" ... "group end new Comment", "main region end".
		self.assertEqual(said["label"], ["group start", "new Comment", "Add a comment"])
		self.assertEqual(said["after"], ["group end", "new Comment", "Terms"])
		self.assertEqual(said["footer"], ["main region end", "link", "Terms"])

	def test_sayAllNamesEveryRegion(self):
		# JAWS named the form and search regions in Say All on the copy (1.31's live test).
		webRegions.register()
		said = self.read(REDDIT, OutputReason.SAYALL)
		self.assertEqual(said["home"], ["banner region", "Reddit", "navigation region", "link", "Reddit Home"])
		self.assertEqual(said["reply"], ["Community actions", "region end", "Reply", "form region", "Join the conversation"])
		self.assertEqual(said["rules"], ["About Community", "complementary region end", "content info region", "link", "Reddit Rules"])

	def test_whatNvdasSettingsLeaveOutStaysOut(self):
		webRegions.register()
		conf = v126.config.conf["documentFormatting"]
		conf.update(reportLandmarks=False, reportLists=False, reportArticles=False)
		said = self.read(REDDIT)
		self.assertEqual(said["home"], ["link", "Reddit Home"])
		self.assertEqual(said["popularHome"], ["link", "Home"])
		self.assertEqual(said["title"], ["heading", "level 1", "I've had data issues"])
		self.assertEqual(said["comment"], ["Try resetting your network settings."])
		self.assertEqual(said["about"], ["heading", "level 2", "r/Visible"])

	def test_aRoleOfThePagesOwnIsNvdas(self):
		webRegions.register()
		custom = landmark("main", 50, roleText="story")
		said = self.read([("in", [custom, "Once"]), ("out", ["upon a time"])])
		self.assertEqual(said["in"], ["story", "Once"])
		self.assertEqual(said["out"], ["out of story", "upon a time"])


# -- Tab, and the focus coming into a page -----------------------------------------------------------------------


class FocusTests(WebRegionsCase):
	def test_tabSaysEveryRegionAsJawsDoes(self):
		webRegions.register()
		said = self.read(REDDIT, OutputReason.FOCUS)
		# JAWS: "BannerRegion", "Global NavigationRegion", "Homepage Link".
		self.assertEqual(said["home"], ["banner region", "Reddit", "navigation region", "Reddit Home", "link"])
		self.assertEqual(said["popularHome"], ["Primary", "navigation region", "list of 2 items", "Home", "link"])
		# JAWS: "MainRegion".
		self.assertEqual(said["title"], ["main region", "I've had data issues", "heading", "level 1"])
		# JAWS: "Reply FormRegion".
		self.assertEqual(said["reply"], ["Reply", "form region", "Join the conversation"])
		# JAWS: "ContentInfoRegion", "Reddit Rules Link".
		self.assertEqual(said["rules"], ["content info region", "Reddit Rules", "link"])
		self.assertEqual(self.read(GITHUB, OutputReason.FOCUS)["label"], ["new Comment", "group", "Add a comment"])

	def test_theTestersGitHubTab(self):
		# The tester's GitHub tab (issue 30, 1.32): NVDA said "main landmark", "new Comment grouping"; JAWS
		# "MainRegion", "new Comment group".
		main = v126.WebObject(60, Role.LANDMARK, "", attributes={"xml-roles": "main"})
		group = v126.WebObject(61, Role.GROUPING, "new Comment")
		self.assertEqual([self.objectSpeech(main), self.objectSpeech(group)], [["main landmark"], ["new Comment", "grouping"]])
		webRegions.register()
		self.assertEqual([self.objectSpeech(main), self.objectSpeech(group)], [["main region"], ["new Comment", "group"]])

	def test_everyLandmarkTheFocusComesInto(self):
		webRegions.register()
		for xmlRole, role, name, words in (
			("banner", Role.LANDMARK, "", ["banner region"]),
			("navigation", Role.LANDMARK, "Global", ["Global", "navigation region"]),
			("search", Role.LANDMARK, "", ["search region"]),
			("form", Role.FORM, "Reply", ["Reply", "form region"]),
			("complementary", Role.LANDMARK, "About Community", ["About Community", "complementary region"]),
			("contentinfo", Role.LANDMARK, "", ["content info region"]),
		):
			obj = v126.WebObject(70, role, name, attributes={"xml-roles": xmlRole})
			self.assertEqual(self.objectSpeech(obj), words, xmlRole)

	def test_otherObjectsAreAsBefore(self):
		webRegions.register()
		# A grouping of a Windows dialog, a region of the page, and a landmark with a role of the page's own.
		self.assertEqual(self.objectSpeech(v126.WindowsObject(80, Role.GROUPING, "Options")), ["Options", "grouping"])
		self.assertEqual(self.objectSpeech(v126.WebObject(81, Role.REGION, "Community actions")), ["Community actions", "region"])
		story = v126.WebObject(82, Role.LANDMARK, "", attributes={"xml-roles": "main", "roledescription": "story"})
		self.assertEqual(self.objectSpeech(story), ["story"])
		# NVDA+Tab (QUERY) is NVDA's.
		main = v126.WebObject(83, Role.LANDMARK, "", attributes={"xml-roles": "main"})
		self.assertEqual(self.objectSpeech(main, OutputReason.QUERY), ["main landmark"])


# -- the assistant's part ---------------------------------------------------------------------------------------------


class TurningOffTests(WebRegionsCase):
	def test_nvdasOwnAreBack(self):
		webRegions.register()
		self.assertIn("getControlFieldSpeech", vars(Gecko_ia2_TextInfo))
		self.assertIsNot(v126.speechScope["getObjectPropertiesSpeech"], NVDA_OBJECT_PROPERTIES)
		webRegions.unregister()
		self.assertNotIn("getControlFieldSpeech", vars(Gecko_ia2_TextInfo))
		self.assertIs(v126.speechScope["getObjectPropertiesSpeech"], NVDA_OBJECT_PROPERTIES)
		self.assertEqual(self.read(REDDIT)["title"], ["out of list", "main landmark", "heading", "level 1", "I've had data issues"])

	def test_onAndOffAgain(self):
		webRegions.register()
		webRegions.unregister()
		webRegions.register()
		self.assertEqual(len(webRegions._replaced), 2)
		self.assertEqual(self.read(REDDIT)["home"], ["Reddit", "navigation region", "link", "Reddit Home"])

	def test_anotherAddonsWrapperIsKept(self):
		webRegions.register()
		ours = vars(Gecko_ia2_TextInfo)["getControlFieldSpeech"]

		def theirs(self, *args, **kwargs):
			return ours(self, *args, **kwargs)

		theirs.__wrapped__ = ours
		Gecko_ia2_TextInfo.getControlFieldSpeech = theirs
		webRegions.unregister()
		self.assertIs(vars(Gecko_ia2_TextInfo)["getControlFieldSpeech"], theirs)
		# Turned on again, it finds its own under theirs, and says JAWS's words again.
		webRegions.register()
		self.assertEqual(self.read(REDDIT)["home"], ["Reddit", "navigation region", "link", "Reddit Home"])

	def test_aFailureIsNvdas(self):
		webRegions.register()
		with mock.patch.object(webRegions, "fieldWords", side_effect=RuntimeError("broken")):
			self.assertEqual(self.read(REDDIT)["home"], ["banner landmark", "navigation landmark", "link", "Reddit Home"])


class SettingTests(unittest.TestCase):
	def test_onUnlessTurnedOff(self):
		self.assertTrue(webRegions.wanted({}))
		self.assertTrue(webRegions.wanted(dict(state.DEFAULTS)))
		self.assertFalse(webRegions.wanted({webRegions.STATE_KEY: False}))
		self.assertIn(webRegions.STATE_KEY, state.DEFAULTS)

	def test_noOtherPartChangesTheseFunctions(self):
		# Two parts of the assistant never put their own in the place of the same NVDA function (see the 1.25 notes).
		source = os.path.dirname(jawsMigrator.__file__)
		users = []
		for name in sorted(os.listdir(source)):
			if name.endswith(".py"):
				with open(os.path.join(source, name), encoding="utf-8") as file:
					text = file.read()
				if '"getObjectPropertiesSpeech"' in text or "Gecko_ia2_TextInfo" in text:
					users.append(name)
		self.assertEqual(users, ["webRegions.py"])


if __name__ == "__main__":
	unittest.main()
