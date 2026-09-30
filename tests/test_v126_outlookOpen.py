# Unit tests for version 1.26, from a tester's report (issue 23, "when I open a message Jaws doesn't automatically read
# unless I press the arrow keys"):
#   That was a bad job of me.  I'll do better.
#   When I press enter nothing is spoken with Jaws.  I press down arrow hear is what I hear.
#     Link   (joshknnd1982/jawsMigrator#21)
#   Fixed in
#     Link   JAWS Migration Assistant 1.25.
#   Thanks for putting JAWS and NVDA side by side, and for the zipped log. It showed exactly what NVDA said.
#   What went wrong. From your log (H on profootballrumors.com, NVDA 2026.2 with 1.24):
#   list of 3 items
#   • HEADLINES, same page, link, Homepage, heading, level 3
#   • Pro Football Rumors, same page, link, Home, heading, level 1
#   • Vikings To Sign P Johnny Hekker, link, heading, level 2
#   list end
#   You didn't miss anything. Each of those headings is a link, and NVDA differed from JAWS in three ways:
# The message is GitHub's e-mail of the reply to issue 21. What issue 20 showed was JAWS reading line by line, not
# JAWS's Say All. The log attached (NVDA log 2026-09-26 13.12.42.zip) has NVDA 2026.2 with JAWS Migration Assistant 1.25
# opening that message (nvda-old.log) and another (nvda.log), and reading each from the top:
#   13:07:13.371 Input: kb(laptop):enter
#   13:07:14.151 jawsMigrator: an Outlook message you opened is read from the top, as JAWS reads it, where NVDA said its
#                first line
#   13:07:14.283 Speaking [CallbackCommand(name=say-all:lineReached), LangChangeCommand ('en_US'), 'graphic',
#                'joshknnd1982 left a comment ', 'link', '(joshknnd1982/jawsMigrator#21)', '\r', ...]
# and then Down Arrow in the list:
#   13:07:23.979 Input: kb(laptop):downArrow
#   13:07:24.132 Speaking [LangChangeCommand ('en_US'), '•', 'HEADLINES, same page, link, Homepage, heading, level 3\r']
#   13:07:24.651 Input: kb(laptop):downArrow
#   13:07:24.810 Speaking [LangChangeCommand ('en_US'), '•', 'Pro Football Rumors, same page, link, Home, heading, level 1\r']
# - outlookMessages: reading a message from the top when it opens is a setting of its own, off unless turned on, so
#   NVDA comes into a message as NVDA does (and Outlook First Line Silence, as the tester runs it, keeps that quiet);
#   in a message you read, a list is said where it starts ("list with 3 items") and after it ("out of list"), as NVDA
#   says a list on a web page, where JAWS said "list of 3 items" and "list end".
# Opening a message runs NVDA 2026.2's own browse mode code, the imitation of test_v125_outlookMessages. The lines of the
# message run NVDA 2026.2's own speech code, the imitation of test_v125_linkSpeech (speakTextInfo, getTextInfoSpeech,
# getControlFieldSpeech, getPropertiesSpeech, processAndLabelStates, ControlField.getPresentationCategory, NVDA's roles,
# states and defaults), with NVDA 2026.2's own fields for Word's UI Automation elements (UIATextInfo and
# WordDocumentTextInfo._getControlFieldForUIAObject, which makes a list a read-only edit field) and NVDA's Outlook
# support's isReadonlyViewer, word for word. The assistant's code is the real one.
# Run: python -m unittest tests.test_v126_outlookOpen -v

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v125_linkSpeech as web  # noqa: E402
import test_v125_outlookMessages as opening  # noqa: E402
from jawsMigrator import outlookMessages, state  # noqa: E402

Role, State, OutputReason = web.Role, web.State, web.OutputReason
textInfos, controlTypes = web.textInfos, web.controlTypes


def applyAsThePluginDoes(stateData):
	"""What the assistant does with its settings when NVDA starts and when they are saved (GlobalPlugin
	.applyRuntimeSettings, which plugin_smoke runs itself)."""
	saying, reading = outlookMessages.wanted(stateData), outlookMessages.readWanted(stateData)
	if saying or reading:
		outlookMessages.register(saying=saying, reading=reading)
	else:
		outlookMessages.unregister()


def resetTheAssistant(test):
	"""The assistant's module as NVDA loads it: nothing in place, nothing noted."""
	for name, value in (
		("_enabled", False),
		("_saying", False),
		("_reading", False),
		("_failed", False),
		("_replaced", []),
		("_windows", {}),
		("_visibleWindows", lambda: []),
		("_notedStyles", set()),
		("_notedMailLink", False),
		("_notedList", False),
		("_itemCounts", {}),
		("_countsFor", None),
	):
		patch = mock.patch.object(outlookMessages, name, value)
		patch.start()
		test.addCleanup(patch.stop)


# -- Opening a message -------------------------------------------------------------------------------------------


class OpeningAMessageTest(opening.Isolated):
	"""Enter on a message in Outlook's message list: NVDA's browse mode comes into the message for the first time."""

	def setUp(self):
		super().setUp()
		resetTheAssistant(self)

	def apply(self, **changes):
		applyAsThePluginDoes(dict(state.DEFAULTS, **changes))
		self.addCleanup(outlookMessages.unregister)

	def nvdasOwn(self, treeInterceptor):
		"""What NVDA says as it comes into the message: the document, and the line at the caret."""
		return [("object", treeInterceptor.rootNVDAObject, opening.OutputReason.FOCUS), ("text", "caret", "line", opening.OutputReason.CARET)]

	def test_as_it_comes_nvda_comes_into_a_message_as_nvda_does(self):
		# Outlook First Line Silence, as the tester runs it, keeps this quiet: nothing is said, as JAWS said nothing.
		self.apply()
		self.assertIs(vars(self.tree)["event_treeInterceptor_gainFocus"], self.nvdasGainFocus, "NVDA's own")
		treeInterceptor, said = self.open()
		self.assertEqual(said, self.nvdasOwn(treeInterceptor))
		self.assertEqual(self.speech.readings, [], "no Say All")
		self.assertTrue(outlookMessages.isRegistered())
		self.assertFalse(outlookMessages.readsOnOpen())

	def test_as_it_comes_links_and_headings_are_said_as_jaws_says_them(self):
		self.apply()
		self.assertEqual(opening.NVDA().speakLine(opening.Document(), opening.fromLine()), opening.AS_JAWS)

	def test_turned_on_a_message_is_read_from_the_top(self):
		self.apply(**{outlookMessages.READ_KEY: True})
		treeInterceptor, said = self.open()
		self.assertEqual(said, [("object", treeInterceptor.rootNVDAObject, opening.OutputReason.FOCUS), ("say all", self.speech.sayAll.CURSOR.CARET)])
		self.assertTrue(outlookMessages.readsOnOpen())

	def test_turned_off_again_nvdas_own_is_back_and_links_stay_as_jaws_says_them(self):
		self.apply(**{outlookMessages.READ_KEY: True})
		self.apply()
		self.assertIs(vars(self.tree)["event_treeInterceptor_gainFocus"], self.nvdasGainFocus)
		self.assertIs(getattr(vars(opening.WordDocumentTextInfo)["_getControlFieldForUIAObject"], outlookMessages.ORIGINAL), opening.NVDAS_CONTROL_FIELD)
		treeInterceptor, said = self.open()
		self.assertEqual(said, self.nvdasOwn(treeInterceptor))
		self.assertEqual(opening.NVDA().speakLine(opening.Document(), opening.fromLine()), opening.AS_JAWS)

	def test_reading_alone(self):
		self.apply(**{outlookMessages.STATE_KEY: False, outlookMessages.READ_KEY: True})
		self.assertIs(vars(opening.WordDocumentTextInfo)["_getControlFieldForUIAObject"], opening.NVDAS_CONTROL_FIELD)
		self.assertIs(vars(opening.WordDocumentTextInfo)["_getFormatFieldAtRange"], opening.NVDAS_FORMAT_AT_RANGE)
		self.assertEqual(opening.NVDA().speakLine(opening.Document(), opening.fromLine()), opening.NVDA_SAID)
		self.open()
		self.assertEqual(self.speech.readings, [self.speech.sayAll.CURSOR.CARET])

	def test_both_off_nvda_has_all_its_own(self):
		self.apply(**{outlookMessages.READ_KEY: True})
		self.apply(**{outlookMessages.STATE_KEY: False})
		self.assertFalse(outlookMessages.isRegistered())
		self.assertIs(vars(self.tree)["event_treeInterceptor_gainFocus"], self.nvdasGainFocus)
		self.assertIs(vars(opening.WordDocumentTextInfo)["_getControlFieldForUIAObject"], opening.NVDAS_CONTROL_FIELD)
		self.assertIs(vars(opening.WordDocumentTextInfo)["_getFormatFieldAtRange"], opening.NVDAS_FORMAT_AT_RANGE)

	def test_with_outlook_first_line_silences_wrapper_over_it(self):
		# Outlook First Line Silence wraps the same method, without functools.wraps. Reading turned off leaves its wrapper
		# where it is, and the assistant's under it does nothing; turned on again, a message is read once.
		self.apply(**{outlookMessages.READ_KEY: True})
		under = vars(self.tree)["event_treeInterceptor_gainFocus"]

		def theirs(self, *args, **kwargs):
			return under(self, *args, **kwargs)

		self.tree.event_treeInterceptor_gainFocus = theirs
		self.apply()
		self.assertIs(vars(self.tree)["event_treeInterceptor_gainFocus"], theirs, "the other add-on's wrapper stays")
		treeInterceptor, said = self.open()
		self.assertEqual(said, self.nvdasOwn(treeInterceptor))
		self.assertEqual(self.speech.readings, [])
		self.apply(**{outlookMessages.READ_KEY: True})
		self.open()
		self.assertEqual(self.speech.readings, [self.speech.sayAll.CURSOR.CARET], "read once")


class SettingTest(unittest.TestCase):
	def test_reading_on_open_is_off_unless_turned_on(self):
		self.assertFalse(outlookMessages.readWanted({}))
		self.assertFalse(outlookMessages.readWanted(dict(state.DEFAULTS)))
		self.assertTrue(outlookMessages.readWanted({outlookMessages.READ_KEY: True}))
		self.assertFalse(outlookMessages.readWanted(None))
		self.assertIs(state.DEFAULTS[outlookMessages.READ_KEY], False)

	def test_saying_as_jaws_is_on_unless_turned_off(self):
		self.assertTrue(outlookMessages.wanted(dict(state.DEFAULTS)))
		self.assertIs(state.DEFAULTS[outlookMessages.STATE_KEY], True)

	def test_the_two_settings_are_apart(self):
		self.assertNotEqual(outlookMessages.READ_KEY, outlookMessages.STATE_KEY)


# -- Lists in a message ------------------------------------------------------------------------------------------

#: NVDA's UIAHandler, as far as NVDA's code and the assistant's use it: UIAutomationClient's own numbers.
UIA = types.ModuleType("UIAHandler")
for _name, _value in vars(opening.uiaModule).items():
	if _name.startswith(("UIA_", "StyleId_")):
		setattr(UIA, _name, _value)
UIA.UIA_ListItemControlTypeId = 50007
UIA.UIA_ListControlTypeId = 50008
UIA.UIA_ControlTypePropertyId = 30003
UIA.TreeScope_Children = 2
UIA.handler = types.SimpleNamespace(
	clientObject=types.SimpleNamespace(CreatePropertyCondition=lambda propertyId, value: ("property", propertyId, value)),
)

_wordScope = {
	"textInfos": textInfos,
	"controlTypes": controlTypes,
	"UIAHandler": UIA,
	"UIARemote": opening.UIARemote,
	"log": web.nvdaLog,
}


class _UIATextInfoBase(web.TextInfo):
	def _getFormatFieldAtRange(self, textRange, formatConfig, ignoreMixedValues=False):
		raise AssertionError("these lines' formatting is their bullet alone")


#: NVDA's NVDAObjects.UIA.UIATextInfo, with NVDA 2026.2's own UIAControlTypesWhereNameIsContent and
#: _getControlFieldForUIAObject, over NVDA's own textInfos.TextInfo.getControlFieldSpeech.
UIATextInfo = web.nvdaMethods("UIATextInfo", [_UIATextInfoBase], [opening.NVDA_UIA_NAME_IS_CONTENT, opening.NVDA_UIA_CONTROL_FIELD], _wordScope)
#: NVDA's WordDocumentTextInfo, with NVDA 2026.2's own _getControlFieldForUIAObject and _getFormatFieldAtRange.
WordDocumentTextInfo = web.nvdaMethods("WordDocumentTextInfo", [UIATextInfo], [opening.NVDA_WORD_CONTROL_FIELD, opening.NVDA_WORD_FORMAT_FIELD_AT_RANGE], _wordScope)
NVDAS_CONTROL_FIELD = vars(WordDocumentTextInfo)["_getControlFieldForUIAObject"]
NVDAS_FORMAT_AT_RANGE = vars(WordDocumentTextInfo)["_getFormatFieldAtRange"]


class Element:
	"""Word's UI Automation element (IUIAutomationElement), as NVDA has it cached: its control type and runtime id; and
	FindAll, which finds its children of a control type."""

	def __init__(self, controlType, runtimeId, children=()):
		self.cachedControlType, self._runtimeId, self.children = controlType, runtimeId, list(children)
		self.asked = []
		self.fails = False

	def getRuntimeId(self):
		return self._runtimeId

	def FindAll(self, scope, condition):
		self.asked.append((scope, condition))
		if self.fails:
			raise OSError("UI Automation didn't answer")
		_property, propertyId, controlType = condition
		assert scope == UIA.TreeScope_Children and propertyId == UIA.UIA_ControlTypePropertyId, (scope, condition)
		return types.SimpleNamespace(Length=sum(1 for child in self.children if child.UIAElement.cachedControlType == controlType))


class Node:
	"""NVDA's object for one of Word's elements in the message (NVDAObjects.UIA.wordDocument.WordDocumentNode)."""

	def __init__(self, role, controlType, runtimeId, children=()):
		self.role = role
		self.UIAElement = Element(controlType, runtimeId, children)
		self.UIAAutomationId = ""
		self.name = self.description = ""
		self.positionInfo = {}
		self.appModule = types.SimpleNamespace(appName="outlook")

	@property
	def states(self):
		# NVDA's UIA object gives a new set each time.
		return set()


class Message:
	"""NVDA's object for a message Word shows through UI Automation (appModules.outlook.OutlookUIAWordDocument), with
	NVDA 2026.2's own isReadonlyViewer; or a document in Word itself."""

	def __init__(self, appName="outlook", readOnly=True):
		self.appModule = types.SimpleNamespace(appName=appName)
		self._states = {State.READONLY} if readOnly else set()

	@property
	def states(self):
		return set(self._states)

	isReadonlyViewer = property(web.nvdaCode(opening.NVDA_OUTLOOK_UIA_READONLY_VIEWER, "_get_isReadonlyViewer", {"controlTypes": controlTypes}))


class Line:
	"""A line of the message: its text, the elements of Word's it is in (the list, then its item), and its bullet."""

	def __init__(self, text, elements=(), bullet=None):
		self.text, self.elements, self.bullet = text, list(elements), bullet


class MessageText(WordDocumentTextInfo):
	"""Browse mode's text of the message, a line at a time, as NVDA's WordDocumentTextInfo.getTextWithFields gives it:
	a field for each of Word's elements the line is in, from NVDA's own _getControlFieldForUIAObject, and the bullet as
	the line's prefix, which NVDA always says (NVDAObjects.UIA.wordDocument, #7971: line-prefix_speakAlways)."""

	def __init__(self, obj, line):
		self.obj, self.line = obj, line

	def getTextWithFields(self, formatConfig=None):
		commands = [textInfos.FieldCommand("controlStart", self._getControlFieldForUIAObject(element)) for element in self.line.elements]
		formatField = textInfos.FormatField()
		if self.line.bullet:
			formatField["line-prefix"] = self.line.bullet
			formatField["line-prefix_speakAlways"] = True
		commands.append(textInfos.FieldCommand("formatChange", formatField))
		commands.append(self.line.text)
		commands.extend(textInfos.FieldCommand("controlEnd", None) for _ in self.line.elements)
		return commands

	def getFormatFieldSpeech(self, attrs, attrsCache=None, formatConfig=None, reason=None, unit=None, extraDetail=False, initialFormat=False):
		# The only formatting of these lines NVDA says: a list item's bullet.
		prefix = attrs.get("line-prefix")
		return [prefix] if prefix else []


BEFORE = "From your log (H on profootballrumors.com, NVDA 2026.2 with 1.24):\r"
ITEMS = [
	"HEADLINES, same page, link, Homepage, heading, level 3\r",
	"Pro Football Rumors, same page, link, Home, heading, level 1\r",
	"Vikings To Sign P Johnny Hekker, link, heading, level 2\r",
]
AFTER = "You didn't miss anything. Each of those headings is a link, and NVDA differed from JAWS in three ways:\r"


def aList(items, runtimeId=(42, 590, 4, 1)):
	"""A bulleted list of ``items`` as Word gives it: a list element, with a list item element for each."""
	children = [Node(Role.LISTITEM, UIA.UIA_ListItemControlTypeId, runtimeId + (index,)) for index in range(len(items))]
	theList = Node(Role.LIST, UIA.UIA_ListControlTypeId, runtimeId, children)
	return theList, [Line(text, [theList, child], bullet="•") for text, child in zip(items, children)]


def theMessage():
	"""The lines of the tester's message around its first list, and the list."""
	theList, items = aList(ITEMS)
	return theList, [Line(BEFORE)] + items + [Line(AFTER)]


#: What NVDA 2026.2 said with Down Arrow through them (the log has the list's first two lines).
NVDA_SAID = [[BEFORE], ["•", ITEMS[0]], ["•", ITEMS[1]], ["•", ITEMS[2]], [AFTER]]
#: What the assistant has NVDA say: the list where it starts and after it, as NVDA says a list on a web page.
AS_JAWS = [[BEFORE], ["list", "with 3 items", "•", ITEMS[0]], ["•", ITEMS[1]], ["•", ITEMS[2]], ["out of list", AFTER]]


class ListTest(unittest.TestCase):
	def setUp(self):
		resetTheAssistant(self)
		self.speech = types.ModuleType("speech")
		self.speech.getControlFieldSpeech = web.NVDA_FIELD_SPEECH
		self.speech.speakTextInfo = web.speechScope["speakTextInfo"]
		wordDocument = types.ModuleType("NVDAObjects.UIA.wordDocument")
		wordDocument.WordDocumentTextInfo = WordDocumentTextInfo
		modules = mock.patch.dict(
			sys.modules,
			{
				"speech": self.speech,
				"controlTypes": controlTypes,
				"config": web.config,
				"textInfos": textInfos,
				"UIAHandler": UIA,
				"NVDAObjects": types.ModuleType("NVDAObjects"),
				"NVDAObjects.UIA": types.ModuleType("NVDAObjects.UIA"),
				"NVDAObjects.UIA.wordDocument": wordDocument,
			},
		)
		modules.start()
		self.addCleanup(modules.stop)
		self.addCleanup(setattr, WordDocumentTextInfo, "_getControlFieldForUIAObject", NVDAS_CONTROL_FIELD)
		self.addCleanup(setattr, WordDocumentTextInfo, "_getFormatFieldAtRange", NVDAS_FORMAT_AT_RANGE)
		web.config.conf = web.testersConfig()
		self.addCleanup(setattr, web.config, "conf", web.testersConfig())

	def turnOn(self):
		applyAsThePluginDoes(dict(state.DEFAULTS))
		self.addCleanup(outlookMessages.unregister)

	def downArrow(self, message, lines):
		"""Down Arrow through ``lines`` of ``message``: NVDA says each line for the caret, against what it said last in
		the message (speech.speakTextInfo's cache). Gives back each line's words."""
		said = []
		for line in lines:
			web.spoken.clear()
			self.speech.speakTextInfo(MessageText(message, line), unit=textInfos.UNIT_LINE, reason=OutputReason.CARET)
			said.append([word for utterance in web.spoken for word in utterance])
		return said

	def test_nvda_alone_says_no_list_as_in_the_log(self):
		_theList, lines = theMessage()
		self.assertEqual(self.downArrow(Message(), lines), NVDA_SAID)

	def test_the_list_where_it_starts_and_after_it(self):
		self.turnOn()
		_theList, lines = theMessage()
		self.assertEqual(self.downArrow(Message(), lines), AS_JAWS)

	def test_up_arrow_back_into_the_list(self):
		self.turnOn()
		_theList, lines = theMessage()
		message = Message()
		self.downArrow(message, lines)
		self.assertEqual(self.downArrow(message, [lines[3], lines[2]]), [["list", "with 3 items", "•", ITEMS[2]], ["•", ITEMS[1]]])

	def test_the_number_of_items_is_asked_for_once(self):
		self.turnOn()
		theList, lines = theMessage()
		self.downArrow(Message(), lines + lines)
		self.assertEqual(theList.UIAElement.asked, [(UIA.TreeScope_Children, ("property", UIA.UIA_ControlTypePropertyId, UIA.UIA_ListItemControlTypeId))])

	def test_each_list_has_its_own_number(self):
		self.turnOn()
		first, firstLines = aList(ITEMS)
		_second, secondLines = aList(["One\r", "Two\r"], runtimeId=(42, 590, 4, 2))
		said = self.downArrow(Message(), firstLines + [Line("Between\r")] + secondLines + [Line(AFTER)])
		self.assertEqual(said[0][:2], ["list", "with 3 items"])
		self.assertEqual(said[3], ["out of list", "Between\r"])
		self.assertEqual(said[4], ["list", "with 2 items", "•", "One\r"])
		self.assertEqual(said[6], ["out of list", AFTER])

	def test_another_message_asks_again(self):
		# A list of another message may have the same runtime id: its number is its own.
		self.turnOn()
		_first, firstLines = aList(ITEMS)
		self.downArrow(Message(), firstLines)
		_other, otherLines = aList(["One\r", "Two\r"])
		self.assertEqual(self.downArrow(Message(), otherLines[:1])[0][:2], ["list", "with 2 items"])

	def test_without_the_number_nvda_says_list(self):
		self.turnOn()
		theList, lines = theMessage()
		theList.UIAElement.fails = True
		with self.assertLogs("nvda", level="DEBUG") as logged:
			said = self.downArrow(Message(), lines)
		self.assertEqual(said, [[BEFORE], ["list", "•", ITEMS[0]], ["•", ITEMS[1]], ["•", ITEMS[2]], ["out of list", AFTER]])
		self.assertEqual(len(theList.UIAElement.asked), 1, "asked once: the list stays the same list")
		self.assertTrue(any("didn't give the number of a list's items" in line for line in logged.output), logged.output)

	def test_the_debug_log_says_so_once(self):
		self.turnOn()
		_theList, lines = theMessage()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.downArrow(Message(), lines + lines)
		notes = [line for line in logged.output if "a list in an Outlook message" in line]
		self.assertEqual(len(notes), 1, logged.output)
		self.assertIn("(3 items)", notes[0])

	def test_a_message_you_write_is_as_before(self):
		# NVDA's own note: a list's start and end said as a bullet is added with Enter is more confusing than good.
		self.turnOn()
		theList, lines = theMessage()
		self.assertEqual(self.downArrow(Message(readOnly=False), lines), NVDA_SAID)
		self.assertEqual(theList.UIAElement.asked, [])

	def test_word_itself_is_as_before(self):
		self.turnOn()
		_theList, lines = theMessage()
		self.assertEqual(self.downArrow(Message("winword"), lines), NVDA_SAID)

	def test_lists_off_in_nvda_say_nothing(self):
		self.turnOn()
		web.config.conf["documentFormatting"]["reportLists"] = False
		_theList, lines = theMessage()
		self.assertEqual(self.downArrow(Message(), lines), NVDA_SAID)

	def test_turned_off_nvda_says_no_list(self):
		self.turnOn()
		applyAsThePluginDoes(dict(state.DEFAULTS, **{outlookMessages.STATE_KEY: False}))
		self.assertIs(vars(WordDocumentTextInfo)["_getControlFieldForUIAObject"], NVDAS_CONTROL_FIELD)
		_theList, lines = theMessage()
		self.assertEqual(self.downArrow(Message(), lines), NVDA_SAID)

	def test_the_field_is_the_list_nvda_says_on_a_web_page(self):
		self.turnOn()
		theList, _lines = theMessage()
		field = MessageText(Message(), Line(""))._getControlFieldForUIAObject(theList)
		self.assertEqual(field["role"], Role.LIST)
		self.assertIn(State.READONLY, field["states"], "NVDA's own marked it read only, as NVDA says a list's items only then")
		self.assertEqual(field[outlookMessages.ITEM_COUNT], 3)


if __name__ == "__main__":
	unittest.main()
