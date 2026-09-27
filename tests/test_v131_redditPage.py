# Unit tests for version 1.31, from a tester's report (issue 30, "issue with how NVDA reads certain things on Reddit").
# The tester opened a reddit post in Edge and pressed E twice. NVDA 2026.2 with JAWS Migration Assistant said (NVDA's
# speech history, as the tester pasted it):
#     Worst three days of my life : r/Visible and 1 more page - Profile 1 - Microsoft​ Edge  window
#     Worst three days of my life : r/Visible - Microsoft Edge  region
#     Worst three days of my life : r/Visible  document  https://www.reddit.com/r/Visible/comments/1wrqr5q/worst_three_days_of_my_life/
#     link  Skip to main content
#     banner landmark  navigation landmark  search landmark  Remove r/Visible filter and expand search to all of Reddit  edit  Search in ⁨r/Visible⁩
#     main landmark  edit  Join the conversation
# On a copy of the page (reddit's search box as www.redditstatic.com's scripts build it: an input in a label, in the
# shadow root of faceplate-search-input, with the scope chip; the reply box a field with a placeholder), JAWS 2026 on
# the maintainer's computer, driven through its API (FreedomSci.JawsApi) with its Speech History copied after each step,
# said:
#     as the page opened: "Worst three days of my life : r/Visible - Microsoft Edge", that again with "page",
#     "Worst three days of my life : r/Visible", "Page has 4 Regions, 1 heading and 3 links"
#     E: "Remove r/Visible filter and expand search to all of Reddit, Edit, blank, placeholder, Search in ⁨r/Visible⁩"
#     E: "Join the conversation, edit, blank" (the copy's box has a name Edge made from its placeholder)
# and on reddit the tester's JAWS said "edit, blank, placeholder, Join the conversation" for E to the reply box (issue 22).
# NVDA said the page's address and "region" because it read Edge through UI Automation that time: Edge's frame around
# the page, class BrowserRootView, has the ARIA role "region" there (read from Edge 154 with UI Automation on the same
# computer), and NVDAObjects.UIA.chromium.ChromiumUIADocument's value is the address, where IAccessible2's Document
# has none.
# - browserPages: Edge's and Chrome's window is said by its name, a page by its title, without "window", "document" or
#   the address, and Edge's frame isn't said.
# - quickNavHeadings: E says an edit field without the containers around it, and an empty one with "blank", then
#   "placeholder" and its placeholder.
# The imitation NVDA is NVDA 2026.2's own code, word for word, as tests/test_v125_linkSpeech.py and
# tests/test_v126_formFields.py took it from the release-2026.2 sources: speakObject, getObjectSpeech,
# getObjectPropertiesSpeech, getPropertiesSpeech, NVDAObject.reportFocus and event_focusEntered, speakTextInfo,
# getTextInfoSpeech, getControlFieldSpeech, TextInfo.getControlFieldSpeech and TextInfoQuickNavItem.report, with NVDA's
# roles, states, landmarks and the tester's settings. The assistant's code is the real one.
# Run: python -m unittest tests.test_v131_redditPage -v

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

# NVDA 2026.2's speech and object code, and its roles, states and settings, taken there word for word.
import test_v126_formFields as v126  # noqa: E402

v125 = v126.v125

import jawsMigrator  # noqa: E402
from jawsMigrator import browserPages, formFields, quickNavHeadings, state  # noqa: E402

Role, State, OutputReason = v126.Role, v126.State, v126.OutputReason
spoken = v126.spoken

TITLE = "Worst three days of my life : r/Visible"
WINDOW_NAME = "Worst three days of my life : r/Visible and 1 more page - Profile 1 - Microsoft​ Edge"
FRAME_NAME = "Worst three days of my life : r/Visible - Microsoft Edge"
URL = "https://www.reddit.com/r/Visible/comments/1wrqr5q/worst_three_days_of_my_life/"
REMOVE = "Remove r/Visible filter and expand search to all of Reddit"
SEARCH_IN = "Search in ⁨r/Visible⁩"
REPLY = "Join the conversation"

#: What the tester's NVDA said, line by line, as the tester pasted it (issue 30).
TESTERS_NVDA = {
	"window": [WINDOW_NAME, "window"],
	"frame": [FRAME_NAME, "region"],
	"page": [TITLE, "document", URL],
	"search": ["banner landmark", "navigation landmark", "search landmark", REMOVE, "edit", SEARCH_IN],
	"reply": ["main landmark", "edit", REPLY],
}
#: What JAWS said for E (the copy's search box, and the tester's reply box, issue 22), in NVDA's words for the type.
JAWS_SEARCH = [REMOVE, "edit", "blank", "placeholder", SEARCH_IN]
JAWS_REPLY = ["edit", "blank", "placeholder", REPLY]
#: What JAWS said for E to the copy's reply box, whose name Edge made from its placeholder.
JAWS_REPLY_NAMED = [REPLY, "edit", "blank"]

EDGE = types.SimpleNamespace(appName="msedge")
EDIT_STATES = (State.FOCUSABLE, State.EDITABLE, State.MULTILINE)
SEARCH_STATES = (State.FOCUSABLE, State.EDITABLE)


def patchNvda(testCase):
	"""NVDA's modules, as the assistant and NVDA's own code import them, for the length of a test."""
	browseMode = types.ModuleType("browseMode")
	browseMode.BrowseModeDocumentTreeInterceptor = v126.BrowseModeDocumentTreeInterceptor
	browseMode.TextInfoQuickNavItem = v125.TextInfoQuickNavItem
	modules = mock.patch.dict(
		sys.modules,
		{
			"speech": v126.speechPackage,
			"speech.speech": v126.speechModule,
			"controlTypes": v126.controlTypes,
			"config": v126.config,
			"textInfos": v126.textInfos,
			"browseMode": browseMode,
			"api": v126.api,
			"eventHandler": v126.eventHandler,
			"aria": v126.aria,
		},
	)
	modules.start()
	testCase.addCleanup(modules.stop)
	testCase.addCleanup(restoreNvda)
	# NVDA's report finds the speech package as a module global, as NVDA's browseMode imports it.
	v125.NVDA_REPORT.__globals__["speech"] = v126.speechPackage
	v126.config.conf = v125.testersConfig()
	spoken.clear()


def restoreNvda():
	"""Whatever a test put over NVDA's own goes, so the next test starts from NVDA as it is."""
	for module in (browserPages, quickNavHeadings, formFields):
		module.unregister()
		module._replaced.clear()
		module._failed = False
	formFields._local.heard = None
	formFields._local.field = None
	quickNavHeadings._local.reports = None
	v126.speechScope.update(v126.NVDA_OWN)
	for name in ("getControlFieldSpeech", "speakObject", "getPropertiesSpeech"):
		setattr(v126.speechPackage, name, v126.speechScope[name])
	v125.TextInfoQuickNavItem.report = v125.NVDA_REPORT
	v125.NVDA_REPORT.__globals__["speech"] = None
	v126.config.conf = v125.testersConfig()


# -- E on the post ------------------------------------------------------------------------------------------------


class PageRange(v126.PageText):
	"""A range of the page in NVDA's virtual buffer, with its text (Gecko_ia2_TextInfo.text)."""

	@property
	def text(self):
		return "".join(part for part in self.parts if isinstance(part, str))


def landmark(name, uniqueID):
	return v126.field(Role.LANDMARK, uniqueID, landmark=name)


BANNER, NAVIGATION, SEARCH, MAIN = landmark("banner", 3), landmark("navigation", 4), landmark("search", 5), landmark("main", 2)
#: The post's lines, as Edge gives them to NVDA's virtual buffer. Gecko_ia2_TextInfo._normalizeControlField gives an
#: empty field its placeholder (IAccessible2's "placeholder"); an empty field holds a space.
LINES = {
	# The search box, empty: its name from the label around it (the scope chip's "Remove" button), its placeholder.
	"search": [BANNER, NAVIGATION, SEARCH, v126.field(Role.EDITABLETEXT, 20, SEARCH_STATES, name=REMOVE, **{"IAccessible2::attribute_placeholder": SEARCH_IN}), " "],
	# The same box with something typed in it: no placeholder.
	"typed": [BANNER, NAVIGATION, SEARCH, v126.field(Role.EDITABLETEXT, 21, SEARCH_STATES, name=REMOVE), "visible plans"],
	# The reply box, as it is before Enter: no name, the placeholder "Join the conversation".
	"reply": [MAIN, v126.field(Role.EDITABLETEXT, 30, EDIT_STATES, **{"IAccessible2::attribute_placeholder": REPLY}), " "],
	# The copy's reply box: a name Edge made from the placeholder, and so no "placeholder" of its own.
	"named": [MAIN, v126.field(Role.EDITABLETEXT, 31, EDIT_STATES, name=REPLY, **{"IAccessible2::attribute_name-from": "placeholder"}), " "],
	# The menu button in the banner, for B, and the post's title, for H.
	"menu": [BANNER, NAVIGATION, v126.field(Role.BUTTON, 40, (State.FOCUSABLE,), name="Open menu")],
	"title": [MAIN, v126.field(Role.HEADING, 41, level="1"), "Worst three days of my life"],
}


class EditFieldTests(unittest.TestCase):
	"""E on the tester's post, with NVDA 2026.2's own speech code."""

	def setUp(self):
		patchNvda(self)
		self.page = v126.EdgePage(v126.WebObject(1, Role.DOCUMENT, name=TITLE, states=(State.FOCUSABLE, State.READONLY)), {})

	def asTheTesterHasIt(self):
		"""The tester's assistant before 1.31: edit fields as JAWS says them for the focus (formFields), headings alone."""
		formFields.register()

	def press(self, line, itemType="edit"):
		"""Quick navigation to the line's field: NVDA's _quickNavScript moves there and reports it, on a page that
		hasn't said anything yet (NVDA's cache of what browse mode's cursor is in is empty)."""
		spoken.clear()
		self.page._speakTextInfoState = None
		v125.VirtualBufferQuickNavItem(itemType, self.page, PageRange(self.page, LINES[line]), OutputReason.QUICKNAV).report()
		self.assertEqual(len(spoken), 1, spoken)
		return spoken[0]

	def test_nvdaSaidWhatTheTesterHeard(self):
		self.asTheTesterHasIt()
		self.assertEqual(self.press("search"), TESTERS_NVDA["search"])
		self.assertEqual(self.press("reply"), TESTERS_NVDA["reply"])

	def test_saidAsJawsSaysIt(self):
		self.asTheTesterHasIt()
		quickNavHeadings.register()
		self.assertEqual(self.press("search"), JAWS_SEARCH)
		self.assertEqual(self.press("reply"), JAWS_REPLY)
		self.assertEqual(self.press("named"), JAWS_REPLY_NAMED)

	def test_blankAfterTheStatesNvdaSays(self):
		# Without formFields NVDA says "multi line"; "blank" comes after the states, as JAWS says it after them.
		quickNavHeadings.register()
		self.assertEqual(self.press("reply"), ["edit", "multi line", "blank", "placeholder", REPLY])

	def test_aFieldWithTextIsSaidAsNvdaSaysIt(self):
		self.asTheTesterHasIt()
		quickNavHeadings.register()
		self.assertEqual(self.press("typed"), [REMOVE, "edit", "visible plans"])

	def test_otherItemsAndTheArrowKeysAreAsBefore(self):
		self.asTheTesterHasIt()
		quickNavHeadings.register()
		self.assertEqual(self.press("menu", "button"), ["banner landmark", "navigation landmark", "Open menu", "button"])
		self.assertEqual(self.press("title", "heading"), ["Worst three days of my life", "heading", "level 1"])
		spoken.clear()
		self.page._speakTextInfoState = None
		v126.speechPackage.speakTextInfo(PageRange(self.page, LINES["search"]), unit=v126.textInfos.UNIT_LINE, reason=OutputReason.CARET)
		# NVDA's own for the arrow keys: the landmarks, and the field without its name (getControlFieldSpeech says a
		# field's name for the focus and quick navigation).
		self.assertEqual(spoken, [["banner landmark", "navigation landmark", "search landmark", "edit", SEARCH_IN]])

	def test_turnedOffNvdasOwnAreBack(self):
		quickNavHeadings.register()
		self.assertIs(v126.speechPackage.getControlFieldSpeech.__wrapped__, v126.speechScope["getControlFieldSpeech"])
		self.assertIs(vars(v125.TextInfoQuickNavItem)["report"].__wrapped__, v125.NVDA_REPORT)
		quickNavHeadings.unregister()
		self.assertIs(v126.speechPackage.getControlFieldSpeech, v126.speechScope["getControlFieldSpeech"])
		self.assertIs(vars(v125.TextInfoQuickNavItem)["report"], v125.NVDA_REPORT)
		self.assertEqual(self.press("search"), TESTERS_NVDA["search"])

	def test_withBlank(self):
		fieldAttrs = {"role": Role.EDITABLETEXT, "states": set(SEARCH_STATES), "placeholder": SEARCH_IN}
		self.assertEqual(quickNavHeadings.withBlank([REMOVE, "edit", SEARCH_IN, "a description"], fieldAttrs, OutputReason.QUICKNAV), [REMOVE, "edit", "blank", "placeholder", SEARCH_IN, "a description"])
		# A role text of the page's own (aria-roledescription) is the field's type.
		fieldAttrs = {"role": Role.EDITABLETEXT, "states": set(), "roleText": "search box"}
		self.assertEqual(quickNavHeadings.withBlank(["search box"], fieldAttrs, OutputReason.QUICKNAV), ["search box", "blank"])


# -- the page opening -----------------------------------------------------------------------------------------------


def browserObject(base, uniqueID, role, name="", value="", appModule=EDGE, UIAClass=None, states=()):
	"""An object of Edge's window, as NVDA gets it: IAccessible2's (WebObject) or UI Automation's (WindowsObject, an
	NVDAObject that isn't IAccessible2's)."""
	obj = base(uniqueID, role, name=name, states=states)
	obj.value = value
	obj.appModule = appModule
	obj.windowClassName = "Chrome_WidgetWin_1"
	obj.UIAElement = types.SimpleNamespace(cachedClassName=UIAClass) if UIAClass else None
	return obj


class PageOpeningTests(unittest.TestCase):
	"""The tester's post opening in Edge, with NVDA 2026.2's own object speech."""

	def setUp(self):
		patchNvda(self)
		self.window = browserObject(v126.WebObject, 0, Role.WINDOW, WINDOW_NAME)
		# Through UI Automation: Edge's frame around the page, and the page with its address as its value.
		self.frame = browserObject(v126.WindowsObject, 100, Role.REGION, FRAME_NAME, UIAClass=browserPages.FRAME_CLASS)
		self.uiaPage = browserObject(v126.WindowsObject, 1, Role.DOCUMENT, TITLE, value=URL, UIAClass="", states=(State.FOCUSABLE, State.READONLY))
		# Through IAccessible2: the page has no value (ia2Web.Document.value is None).
		self.ia2Page = browserObject(v126.WebObject, 1, Role.DOCUMENT, TITLE, value=None, states=(State.FOCUSABLE, State.READONLY))

	def open(self, page, frame=True):
		"""NVDA's focus coming into Edge and to the page: the window's focus, the frame the focus enters (only through UI
		Automation), then the page's focus."""
		spoken.clear()
		self.window.reportFocus()
		if frame:
			self.frame.event_focusEntered()
		page.reportFocus()
		return list(spoken)

	def test_nvdaSaidWhatTheTesterHeard(self):
		self.assertEqual(self.open(self.uiaPage), [TESTERS_NVDA["window"], TESTERS_NVDA["frame"], TESTERS_NVDA["page"]])

	def test_saidAsJawsSaysIt(self):
		browserPages.register()
		self.assertEqual(self.open(self.uiaPage), [[WINDOW_NAME], [TITLE]])
		# Through IAccessible2 NVDA said the window and the page with their roles; now their names alone.
		browserPages.unregister()
		self.assertEqual(self.open(self.ia2Page, frame=False), [[WINDOW_NAME, "window"], [TITLE, "document"]])
		browserPages.register()
		self.assertEqual(self.open(self.ia2Page, frame=False), [[WINDOW_NAME], [TITLE]])

	def test_chromeToo(self):
		browserPages.register()
		chrome = types.SimpleNamespace(appName="chrome")
		for obj in (self.window, self.frame, self.uiaPage):
			obj.appModule = chrome
		self.assertEqual(self.open(self.uiaPage), [[WINDOW_NAME], [TITLE]])

	def test_otherProgramsAreAsBefore(self):
		browserPages.register()
		for appName in ("firefox", "code", "notepad"):
			other = types.SimpleNamespace(appName=appName)
			for obj in (self.window, self.frame, self.uiaPage):
				obj.appModule = other
			self.assertEqual(self.open(self.uiaPage), [TESTERS_NVDA["window"], TESTERS_NVDA["frame"], TESTERS_NVDA["page"]], appName)
		browserObject(v126.WebObject, 5, Role.WINDOW, "Untitled - Notepad", appModule=None).reportFocus()
		self.assertEqual(spoken[-1], ["Untitled - Notepad", "window"])

	def test_nvdaTabAndAPageWithoutATitleAreAsBefore(self):
		untitled = browserObject(v126.WindowsObject, 2, Role.DOCUMENT, "", value=URL, UIAClass="")

		def said():
			spoken.clear()
			# NVDA+Tab: NVDA's reportCurrentFocus says the focus for a query.
			v126.speechPackage.speakObject(self.uiaPage, reason=OutputReason.QUERY)
			untitled.reportFocus()
			return list(spoken)

		nvdas = said()
		self.assertEqual(nvdas, [[TITLE, "document", URL, "read only"], ["document", URL]])
		browserPages.register()
		self.assertEqual(said(), nvdas)

	def test_aRegionOnThePageIsStillSaid(self):
		# A region the page itself has (reddit's "Community actions") is said as the focus enters it; only Edge's
		# frame, class BrowserRootView, isn't.
		browserPages.register()
		region = browserObject(v126.WindowsObject, 7, Role.REGION, "Community actions", UIAClass="flex items-center")
		spoken.clear()
		region.event_focusEntered()
		self.assertEqual(spoken, [["Community actions", "region"]])

	def test_statesAreStillSaid(self):
		browserPages.register()
		busy = browserObject(v126.WindowsObject, 3, Role.DOCUMENT, TITLE, value=URL, UIAClass="", states=(State.FOCUSABLE, State.READONLY, State.BUSY))
		spoken.clear()
		busy.reportFocus()
		self.assertEqual(spoken, [[TITLE, "busy"]])

	def test_turnedOffNvdasOwnIsBack(self):
		nvdas = v126.speechPackage.speakObject
		browserPages.register()
		self.assertIs(v126.speechPackage.speakObject.__wrapped__, nvdas)
		browserPages.register()
		self.assertIs(v126.speechPackage.speakObject.__wrapped__, nvdas, "wrapped once")
		browserPages.unregister()
		self.assertIs(v126.speechPackage.speakObject, nvdas)
		self.assertEqual(self.open(self.uiaPage), [TESTERS_NVDA["window"], TESTERS_NVDA["frame"], TESTERS_NVDA["page"]])

	def test_anotherAddonsWrapperIsKept(self):
		# An add-on that put its own speakObject around the assistant's: turning the assistant off leaves both in place,
		# and turning it on again doesn't wrap it twice.
		nvdas = v126.speechPackage.speakObject
		browserPages.register()
		ours = v126.speechPackage.speakObject

		def theirs(obj, *args, **kwargs):
			return ours(obj, *args, **kwargs)

		theirs.__wrapped__ = ours
		v126.speechPackage.speakObject = theirs
		browserPages.unregister()
		self.assertIs(v126.speechPackage.speakObject, theirs)
		browserPages.register()
		self.assertIs(v126.speechPackage.speakObject, theirs)
		self.assertEqual(self.open(self.uiaPage), [[WINDOW_NAME], [TITLE]])
		v126.speechPackage.speakObject = nvdas


class SettingTests(unittest.TestCase):
	def test_onUnlessTurnedOff(self):
		self.assertTrue(browserPages.wanted({}))
		self.assertTrue(browserPages.wanted(dict(state.DEFAULTS)))
		self.assertFalse(browserPages.wanted({browserPages.STATE_KEY: False}))
		self.assertTrue(quickNavHeadings.wanted({}))
		self.assertFalse(quickNavHeadings.wanted({quickNavHeadings.STATE_KEY: False}))

	def test_theTwoModulesChangeDifferentFunctions(self):
		# Two parts of the assistant never put their own in the place of the same NVDA function (see the 1.25 notes):
		# browserPages has speech.speakObject, which no other part has.
		source = os.path.join(os.path.dirname(jawsMigrator.__file__))
		users = []
		for name in os.listdir(source):
			if name.endswith(".py"):
				with open(os.path.join(source, name), encoding="utf-8") as file:
					if '"speakObject"' in file.read():
						users.append(name)
		self.assertEqual(users, ["browserPages.py"])


if __name__ == "__main__":
	unittest.main()
