# Unit tests for version 1.36, from a tester's request (issue 35, "Another thing to consider"): tests on several sites
# with both JAWS and NVDA. JAWS 2026 and NVDA 2026.2 with the assistant 1.35 were run side by side on copies of Amazon's
# home page and search results, Wikipedia, BBC News, a BBC article and GitHub (see tests/test_v136_quickNavItems.py).
# It showed a fault of 1.33's: the first time NVDA comes into an Edge or Chrome page, browserPages says the page's title
# without its first line, as JAWS, whose cursor starts on the title. But NVDA's caret stays on that first line, so:
#     the first Down Arrow:  JAWS "same page link Skip to content" (BBC News)  NVDA the second line, "button, collapsed,
#                            Open menu": the first line was never said
#     H:                     JAWS "Skip to, heading level 2" (Amazon)          NVDA "Keyboard shortcuts, heading, level 2",
#                            the second heading: NVDA looks for the next heading after the caret
#     Tab:                   JAWS "Skip to content" (BBC News)                 NVDA "Open menu, button, collapsed"
# - browserPages: while browse mode's caret is still where it was when NVDA held the first line back, the Down Arrow says
#   that line and leaves the caret there, and a quick navigation key or Tab goes to an element the line starts with.
# The imitation NVDA is NVDA 2026.2's own code, word for word: CursorManager._caretMovementScriptHelper (cursorManager.py),
# BrowseModeTreeInterceptor._quickNavScript and BrowseModeDocumentTreeInterceptor._tabOverride (browseMode.py), checked
# against release-2026.2 by NvdasOwnCodeTests when NVDA_SOURCE is set, on tests/test_v134_pageFirstLine.py's page (NVDA's
# event_treeInterceptor_gainFocus) and tests/test_v126_formFields.py's speech. The assistant's code is the real one.
# Run: python -m unittest tests.test_v136_firstLine -v

import ast
import os
import sys
import textwrap
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v134_pageFirstLine as v134  # noqa: E402

v131, v126, v125 = v134.v131, v134.v126, v134.v125

from jawsMigrator import browserPages  # noqa: E402

Role, State, OutputReason = v126.Role, v126.State, v126.OutputReason
textInfos = v126.textInfos
spoken = v126.spoken
field = v126.field

#: NVDA 2026.2, source/cursorManager.py, CursorManager._caretMovementScriptHelper, word for word.
NVDA_CARET_MOVEMENT = r'''
def _caretMovementScriptHelper(
	self,
	gesture,
	unit,
	direction=None,
	posConstant=textInfos.POSITION_SELECTION,
	posUnit=None,
	posUnitEnd=False,
	extraDetail=False,
	handleSymbols=False,
):
	if isScriptWaiting():
		# Moving / reporting is quite costly, so we don't want to do it if there are more scripts waiting.
		# Otherwise, NVDA could become unusable while it processes many backed up scripts.
		return
	oldInfo = self.makeTextInfo(posConstant)
	info = oldInfo.copy()
	info.collapse(end=self.isTextSelectionAnchoredAtStart)
	if self.isTextSelectionAnchoredAtStart and not oldInfo.isCollapsed:
		info.move(textInfos.UNIT_CHARACTER, -1)
	if posUnit is not None:
		# expand and collapse to ensure that we are aligned with the end of the intended unit
		info.expand(posUnit)
		try:
			info.collapse(end=posUnitEnd)
		except RuntimeError:
			# MS Word has a "virtual linefeed" at the end of the document which can cause RuntimeError to be raised.
			# In this case it can be ignored.
			# See #7009
			pass
		if posUnitEnd:
			info.move(textInfos.UNIT_CHARACTER, -1)
	if direction is not None:
		info.expand(unit)
		info.collapse(end=posUnitEnd)
		if info.move(unit, direction) == 0 and isinstance(self, DocumentWithPageTurns):
			try:
				self.turnPage(previous=direction < 0)
			except RuntimeError:
				pass
			else:
				info = self.makeTextInfo(
					textInfos.POSITION_FIRST if direction > 0 else textInfos.POSITION_LAST,
				)
	# #10343: Speak before setting selection because setting selection might
	# move the focus, which might mutate the document, potentially invalidating
	# info if it is offset-based.
	selection = info.copy()
	info.expand(unit)
	if not willSayAllResume(gesture):
		speech.speakTextInfo(info, unit=unit, reason=controlTypes.OutputReason.CARET)
	if not oldInfo.isCollapsed:
		speech.speakSelectionChange(oldInfo, selection)
	self.selection = selection
'''

#: NVDA 2026.2, source/browseMode.py, BrowseModeTreeInterceptor._quickNavScript, word for word.
NVDA_QUICK_NAV_SCRIPT = r'''
def _quickNavScript(self, gesture, itemType, direction, errorMessage, readUnit):
	if itemType == "notLinkBlock":
		iterFactory = self._iterNotLinkBlock
	elif itemType == "textParagraph":
		punctuationMarksRegex = re.compile(
			config.conf["virtualBuffers"]["textParagraphRegex"],
		)

		def paragraphFunc(info: textInfos.TextInfo) -> bool:
			return punctuationMarksRegex.search(info.text) is not None

		def iterFactory(
			direction: str,
			pos: textInfos.TextInfo,
		) -> Generator[TextInfoQuickNavItem, None, None]:
			return self._iterSimilarParagraph(
				kind="textParagraph",
				paragraphFunction=paragraphFunc,
				desiredValue=True,
				direction=_Movement(direction),
				pos=pos,
			)
	elif itemType == "verticalParagraph":

		def paragraphFunc(info: textInfos.TextInfo) -> int | None:
			try:
				return info.location[0]
			except (AttributeError, TypeError):
				return None

		def iterFactory(
			direction: str,
			pos: textInfos.TextInfo,
		) -> Generator[TextInfoQuickNavItem, None, None]:
			return self._iterSimilarParagraph(
				kind="verticalParagraph",
				paragraphFunction=paragraphFunc,
				desiredValue=None,
				direction=_Movement(direction),
				pos=pos,
			)
	elif itemType in ["sameStyle", "differentStyle"]:

		def iterFactory(
			direction: documentBase._Movement,
			info: textInfos.TextInfo | None,
		) -> Generator[TextInfoQuickNavItem, None, None]:
			return self._iterTextStyle(itemType, direction, info)
	else:
		iterFactory = lambda direction, info: self._iterNodesByType(itemType, direction, info)  # noqa: E731
	info = self.selection
	try:
		item = next(iterFactory(direction, info))
	except NotImplementedError:
		# Translators: a message when a particular quick nav command is not supported in the current document.
		ui.message(_("Not supported in this document"))
		return
	except StopIteration:
		ui.message(errorMessage)
		return
	# #8831: Report before moving because moving might change the focus, which
	# might mutate the document, potentially invalidating info if it is
	# offset-based.
	if not gesture or not willSayAllResume(gesture):
		item.report(readUnit=readUnit)
	item.moveTo()
'''

#: NVDA 2026.2, source/browseMode.py, BrowseModeDocumentTreeInterceptor._tabOverride, word for word.
NVDA_TAB_OVERRIDE = r'''
def _tabOverride(self, direction):
	"""Override the tab order if the virtual  caret is not within the currently focused node.
	This is done because many nodes are not focusable and it is thus possible for the virtual caret to be unsynchronised with the focus.
	In this case, we want tab/shift+tab to move to the next/previous focusable node relative to the virtual caret.
	If the virtual caret is within the focused node, the tab/shift+tab key should be passed through to allow normal tab order navigation.
	Note that this method does not pass the key through itself if it is not overridden. This should be done by the calling script if C{False} is returned.
	@param direction: The direction in which to move.
	@type direction: str
	@return: C{True} if the tab order was overridden, C{False} if not.
	@rtype: bool
	"""
	if self._lastCaretMoveWasFocus:
		# #5227: If the caret was last moved due to a focus change, don't override tab.
		# This ensures that tabbing behaves as expected after tabbing hits an iframe document.
		return False
	focus = api.getFocusObject()
	try:
		focusInfo = self.makeTextInfo(focus)
	except:  # noqa: E722
		return False
	# We only want to override the tab order if the caret is not within the focused node.
	caretInfo = self.makeTextInfo(textInfos.POSITION_CARET)
	# Only check that the caret is within the focus for things that ar not documents
	# As for documents we should always override
	if focus.role != controlTypes.Role.DOCUMENT or controlTypes.State.EDITABLE in focus.states:
		# Expand to one character, as isOverlapping() doesn't yield the desired results with collapsed ranges.
		caretInfo.expand(textInfos.UNIT_CHARACTER)
		if focusInfo.isOverlapping(caretInfo):
			return False
	# If we reach here, we do want to override tab/shift+tab if possible.
	# Find the next/previous focusable node.
	try:
		item = next(self._iterNodesByType("focusable", direction, caretInfo))
	except StopIteration:
		return False
	obj = item.obj
	newInfo = item.textInfo
	if obj == api.getFocusObject():
		# This node is already focused, so we need to move to and speak this node here.
		newCaret = newInfo.copy()
		newCaret.collapse()
		self._set_selection(newCaret, reason=OutputReason.FOCUS)
		if self.passThrough:
			obj.event_gainFocus()
		else:
			speech.speakTextInfo(newInfo, reason=OutputReason.FOCUS)
	else:
		# This node doesn't have the focus, so just set focus to it. The gainFocus event will handle the rest.
		obj.setFocus()
	return True
'''

NVDA_CODE = {
	"NVDA_CARET_MOVEMENT": ("cursorManager.py", "CursorManager", "_caretMovementScriptHelper"),
	"NVDA_QUICK_NAV_SCRIPT": ("browseMode.py", "BrowseModeTreeInterceptor", "_quickNavScript"),
	"NVDA_TAB_OVERRIDE": ("browseMode.py", "BrowseModeDocumentTreeInterceptor", "_tabOverride"),
}

#: The page's first lines, as Edge gives them to NVDA's virtual buffer: BBC News's and Amazon's, one after the other.
LINES = [
	[field(Role.LINK, 20, (State.LINKED, State.FOCUSABLE, State.INTERNAL_LINK)), "Skip to content"],
	[field(Role.BUTTON, 21, (State.FOCUSABLE, State.COLLAPSED)), "Open menu"],
	[field(Role.HEADING, 22, level="2"), "Keyboard shortcuts"],
	["Top stories"],
]
SKIP = ["same page", "link", "Skip to content"]
MENU = ["button", "collapsed", "Open menu"]
#: What quick navigation finds for its item types, as NVDA's virtual buffer does (VBuf_findNodeByAttributes).
KINDS = {
	"link": lambda attrs: attrs["IAccessible::role"] == Role.LINK,
	"button": lambda attrs: attrs["IAccessible::role"] == Role.BUTTON,
	"heading": lambda attrs: attrs["IAccessible::role"] == Role.HEADING,
	"focusable": lambda attrs: State.FOCUSABLE in attrs["IAccessible::states"],
	"table": lambda attrs: False,
}

#: What NVDA's message function (ui.message) was given.
messages = []
waiting = []


class Spot(v131.PageRange):
	"""A range of the page in NVDA's virtual buffer (Gecko_ia2_TextInfo), in whole lines: ``start`` to ``end``."""

	def __init__(self, page, start, end=None):
		self.obj, self.start = page, start
		self.end = start if end is None else end

	@property
	def parts(self):
		if self.start >= len(self.obj.pageLines):
			return []
		parts = self.obj.pageLines[self.start]
		return parts if self.end > self.start else [part for part in parts if not isinstance(part, str)]

	@parts.setter
	def parts(self, value):
		pass

	@property
	def isCollapsed(self):
		return self.start == self.end

	def copy(self):
		return Spot(self.obj, self.start, self.end)

	def collapse(self, end=False):
		if end:
			self.start = self.end
		else:
			self.end = self.start

	def expand(self, unit):
		self.end = min(self.start + 1, len(self.obj.pageLines))

	def move(self, unit, direction, endPoint=None):
		if endPoint == "end":
			old, self.end = self.end, max(self.start, min(self.end + direction, len(self.obj.pageLines)))
			return self.end - old
		old = self.start
		self.start = self.end = max(0, min(self.start + direction, len(self.obj.pageLines) - 1))
		return self.start - old

	def compareEndPoints(self, other, which):
		mine, theirs = (self.start, other.start) if which == "startToStart" else (self.end, other.end)
		return (mine > theirs) - (mine < theirs)

	def setEndPoint(self, other, which):
		assert which == "endToEnd"
		self.end = other.end

	def isOverlapping(self, other):
		return self.start < other.end and other.start < self.end


class QuickNavItem(v125.TextInfoQuickNavItem):
	"""virtualBuffers.VirtualBufferQuickNavItem: NVDA's report, and moveTo and obj as NVDA's virtual buffer has them."""

	def __init__(self, itemType, page, line):
		super().__init__(itemType, page, Spot(page, line, line + 1), OutputReason.QUICKNAV)
		self.line = line

	def moveTo(self):
		self.document.selection = Spot(self.document, self.line)

	@property
	def obj(self):
		return self.document.objects[self.line]


scope = dict(
	v134.treeInterceptorScope,
	isScriptWaiting=lambda: bool(waiting),
	willSayAllResume=lambda gesture: False,
	DocumentWithPageTurns=type("DocumentWithPageTurns", (), {}),
	ui=types.SimpleNamespace(message=messages.append),
	controlTypes=v126.controlTypes,
	_=lambda text: text,
)
#: NVDA's page class with the three methods from NVDA's own code, on test_v134_pageFirstLine's page.
NvdaPage = v125.nvdaMethods(
	"BrowseModeDocumentTreeInterceptor",
	[v134.BrowseModeDocumentTreeInterceptor],
	[NVDA_CARET_MOVEMENT, NVDA_QUICK_NAV_SCRIPT, NVDA_TAB_OVERRIDE],
	scope,
)
NVDA_OWN = {name: vars(NvdaPage)[name] for name in ("_caretMovementScriptHelper", "_quickNavScript", "_tabOverride")}
# NVDA's speech package, as browseMode and cursorManager import it (the speech functions the harness has).
NVDA_OWN["_caretMovementScriptHelper"].__globals__["speech"] = v126.speechPackage


class ChromeVBuf(NvdaPage):
	"""NVDAObjects.IAccessible.chromium.ChromeVBuf: Edge's page, with a caret that moves line by line."""

	isTextSelectionAnchoredAtStart = True
	_lastCaretMoveWasFocus = False

	def __init__(self, root):
		super().__init__(root, {})
		root.treeInterceptor = self
		self.pageLines = LINES
		self.caretLine = 0
		self._hadFirstGainFocus = False
		self.documentConstantIdentifier = v134.URL
		self.objects = {line: v131.browserObject(v126.WebObject, 20 + line, Role.LINK) for line in range(len(LINES))}
		self.focused = []
		for line, obj in self.objects.items():
			obj.setFocus = lambda line=line: self.focused.append(line)

	def _getInitialCaretPos(self):
		return None

	def makeTextInfo(self, position):
		if position in (textInfos.POSITION_CARET, textInfos.POSITION_SELECTION):
			return Spot(self, self.caretLine)
		if position == textInfos.POSITION_FIRST:
			return Spot(self, 0)
		for line, obj in self.objects.items():
			if position is obj:
				return Spot(self, line, line + 1)
		return Spot(self, 0, len(LINES))

	@property
	def selection(self):
		return Spot(self, self.caretLine)

	@selection.setter
	def selection(self, info):
		self.caretLine = info.start

	def _set_selection(self, info, reason=None):
		self.caretLine = info.start

	def _iterNodesByType(self, itemType, direction="next", pos=None):
		"""As NVDA's virtual buffer: the next element after where ``pos`` starts (from the top without ``pos``)."""
		found = KINDS[itemType]
		lines = range(len(LINES)) if direction == "next" else range(len(LINES) - 1, -1, -1)
		for line in lines:
			if pos is not None and ((direction == "next" and line <= pos.start) or (direction == "previous" and line >= pos.start)):
				continue
			first = next((part for part in LINES[line] if isinstance(part, dict)), None)
			if first is not None and found(first):
				yield QuickNavItem(itemType, self, line)


class FirstLineCase(unittest.TestCase):
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
				"scriptHandler": types.SimpleNamespace(isScriptWaiting=scope["isScriptWaiting"], willSayAllResume=scope["willSayAllResume"]),
			},
		)
		modules.start()
		self.addCleanup(modules.stop)
		self.addCleanup(self._restore)
		v126.config.conf["virtualBuffers"] = {"autoSayAllOnPageLoad": False}
		messages.clear()
		waiting.clear()
		self.window = v131.browserObject(v126.WebObject, 0, Role.WINDOW, v131.WINDOW_NAME)
		self.root = v131.browserObject(v126.WebObject, 1, Role.DOCUMENT, v134.TITLE, value=None, states=(State.FOCUSABLE, State.READONLY))
		v126.globalVars.focusObject = self.root
		v126.globalVars.focusAncestors = [self.window]
		v126.globalVars.focusDifferenceLevel = 1
		self.page = ChromeVBuf(self.root)

	def _restore(self):
		browserPages.unregister()
		browserPages._replaced.clear()
		browserPages._failed = False
		for name in ("event_treeInterceptor_gainFocus", *NVDA_OWN):
			if name in vars(ChromeVBuf):
				delattr(ChromeVBuf, name)

	def open(self):
		"""NVDA comes into the page for the first time."""
		spoken.clear()
		self.page.event_treeInterceptor_gainFocus()
		return list(spoken)

	def down(self):
		spoken.clear()
		self.page._caretMovementScriptHelper(None, textInfos.UNIT_LINE, 1)
		return list(spoken)

	def quickNav(self, itemType, direction="next"):
		spoken.clear()
		messages.clear()
		self.page._quickNavScript(None, itemType, direction, f"no {direction} {itemType}", None)
		return list(spoken) or list(messages)

	def tab(self):
		spoken.clear()
		self.page.focused.clear()
		if not self.page._tabOverride("next"):
			return "passed to the page"
		return self.page.focused


class FirstLineTests(FirstLineCase):
	def test_nvdaNeverSaidTheFirstLine(self):
		# 1.35: the title, then the Down Arrow reads the second line; H and Tab go past the first line's link.
		browserPages.register()
		for name in NVDA_OWN:
			delattr(ChromeVBuf, name)
		self.assertEqual(self.open(), [[v134.TITLE]])
		self.assertEqual(self.down(), [MENU])

	def test_theDownArrowSaysTheFirstLine(self):
		# JAWS: the title as the page opens, then "same page link Skip to content", then "Open menu Button collapsed".
		browserPages.register()
		self.assertEqual(self.open(), [[v134.TITLE]])
		self.assertEqual(self.down(), [SKIP])
		self.assertEqual(self.page.caretLine, 0)
		self.assertEqual(self.down(), [MENU])
		self.assertEqual(self.page.caretLine, 1)

	def test_quickNavigationFindsWhatTheFirstLineStartsWith(self):
		browserPages.register()
		self.open()
		self.assertEqual(self.quickNav("link"), [["Skip to content", "same page", "link"]])
		self.assertEqual(self.page.caretLine, 0)
		# Now the first line has been said: the next link is after it, as NVDA has it.
		self.assertEqual(self.quickNav("link"), ["no next link"])

	def test_quickNavigationToSomethingFurtherDownIsNvdas(self):
		browserPages.register()
		self.open()
		self.assertEqual(self.quickNav("button"), [["Open menu", "button", "collapsed"]])
		self.assertEqual(self.page.caretLine, 1)
		# And once the caret has moved, the Down Arrow is NVDA's.
		self.assertEqual(self.down(), [["heading", "level 2", "Keyboard shortcuts"]])

	def test_tabGoesToWhatTheFirstLineStartsWith(self):
		# JAWS's Tab after the page opens: "Skip to content"; NVDA's went to the next one, "Open menu".
		browserPages.register()
		self.open()
		self.assertEqual(self.tab(), [0])

	def test_withoutTheAssistantTabGoesPast(self):
		self.open()
		self.assertEqual(self.tab(), [1])

	def test_onlyUntilTheCaretMoves(self):
		browserPages.register()
		self.open()
		self.page.caretLine = 2
		self.assertEqual(self.down(), [["Top stories"]])
		self.page.caretLine = 0
		self.assertEqual(self.down(), [MENU])
		# From the button, NVDA's Tab finds nothing further down, and passes Tab to the page.
		self.assertEqual(self.tab(), "passed to the page")

	def test_otherKeysForgetIt(self):
		browserPages.register()
		self.open()
		# Up Arrow (NVDA's own), then Down: NVDA's.
		self.page._caretMovementScriptHelper(None, textInfos.UNIT_LINE, -1)
		self.assertEqual(self.down(), [MENU])

	def test_previousIsNvdas(self):
		browserPages.register()
		self.open()
		self.assertEqual(self.quickNav("link", "previous"), ["no previous link"])
		self.assertEqual(self.down(), [MENU])

	def test_withKeysWaitingNothingIsSaidOrMoved(self):
		browserPages.register()
		self.open()
		waiting.append(True)
		self.assertEqual(self.down(), [])
		self.assertEqual(self.page.caretLine, 0)

	def test_focusModeIsNvdas(self):
		browserPages.register()
		self.open()
		self.page.passThrough = True
		self.assertEqual(self.down(), [MENU])

	def test_aPageWhoseFirstLineWasSaidIsNvdas(self):
		# Coming back to a page: NVDA says the line at the caret, so nothing is held back.
		browserPages.register()
		self.page._hadFirstGainFocus = True
		self.open()
		self.assertEqual(self.tab(), [1])
		self.assertEqual(self.down(), [MENU])

	def test_turnedOffNvdasOwnAreBack(self):
		browserPages.register()
		for name in NVDA_OWN:
			self.assertIn(name, vars(ChromeVBuf))
		browserPages.unregister()
		for name in NVDA_OWN:
			self.assertNotIn(name, vars(ChromeVBuf))
			self.assertIs(getattr(ChromeVBuf, name), NVDA_OWN[name])

	def test_aClassWithItsOwnIsLeftAlone(self):
		def theirs(self, direction):
			return False

		ChromeVBuf._tabOverride = theirs
		browserPages.register()
		self.assertIs(vars(ChromeVBuf)["_tabOverride"], theirs)
		self.assertIn("_quickNavScript", vars(ChromeVBuf))
		browserPages.unregister()
		self.assertIs(vars(ChromeVBuf)["_tabOverride"], theirs)


class SettingTests(unittest.TestCase):
	def test_noOtherPartChangesThese(self):
		# Two parts of the assistant never put their own in the place of the same NVDA function (see the 1.25 notes).
		import jawsMigrator

		source = os.path.dirname(jawsMigrator.__file__)
		for name in ("_caretMovementScriptHelper", "_quickNavScript", "_tabOverride"):
			users = []
			for fileName in sorted(os.listdir(source)):
				if fileName.endswith(".py"):
					with open(os.path.join(source, fileName), encoding="utf-8") as file:
						if f'"{name}"' in file.read():
							users.append(fileName)
			self.assertEqual(users, ["browserPages.py"], name)


class NvdasOwnCodeTests(unittest.TestCase):
	def test_theCodeIsNvdas(self):
		# Each piece is in NVDA 2026.2's source, as a method, when a copy of it is around: set NVDA_SOURCE to its
		# source folder.
		source = os.environ.get("NVDA_SOURCE")
		if not source:
			self.skipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
		for name, (path, className, method) in NVDA_CODE.items():
			with open(os.path.join(source, path), encoding="utf-8") as file:
				text = file.read()
			tree = ast.parse(text)
			found = None
			for node in ast.walk(tree):
				if isinstance(node, ast.ClassDef) and node.name == className:
					for item in node.body:
						if isinstance(item, ast.FunctionDef) and item.name == method:
							found = textwrap.dedent(ast.get_source_segment(text, item, padded=True))
			self.assertEqual(globals()[name].strip(), (found or "").strip(), name)


if __name__ == "__main__":
	unittest.main()
