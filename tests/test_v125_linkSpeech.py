# Unit tests for version 1.25, from a tester's report (issue 21, "What Jaws says on websites"). On
# www.profootballrumors.com the tester pressed H, and JAWS said:
#     HEADLINES   heading level 3     Link
#     Pro Football Rumors   heading level 1     Link
#     Vikings To Sign P Johnny Hekker   heading level 2     Link
# NVDA 2026.2 with JAWS Migration Assistant 1.24 said (NVDA log 2026-09-26 11.57.32.zip, nvda.log):
#     11:57:21.733 Input: kb(laptop):h
#     11:57:21.736 Speaking ['HEADLINES', 'same page', 'link', 'Homepage', 'heading', 'level 3']
#     11:57:24.020 Input: kb(laptop):control+home
#     11:57:24.024 Speaking ['same page', 'link', 'Skip to content']
#     11:57:24.651 Input: kb(laptop):h
#     11:57:24.655 Speaking ['HEADLINES', 'same page', 'link', 'Homepage', 'heading', 'level 3']
#     11:57:26.140 Input: kb(laptop):h
#     11:57:26.143 Speaking ['Pro Football Rumors', 'same page', 'link', 'Home', 'heading', 'level 1']
#     11:57:27.484 Input: kb(laptop):h
#     11:57:27.488 Speaking ['Vikings To Sign P Johnny Hekker', 'link', 'heading', 'level 2']
# The page has <h3><a href="/" title="Homepage">Headlines</a></h3> (in capitals on the screen), <a
# href="https://www.profootballrumors.com/" title="Home" rel="home"> in the banner's heading, and <h2
# class="entry-title"><a href="https://www.profootballrumors.com/2026/09/vikings-to-sign-p-johnny-hekker-2"> in its main
# part. On reddit.com (issue 8) JAWS said "Feels to good to be true  visited    heading level 2".
# - linkSpeech: "same page" only for a link to a place on the page (JAWS's "Identify same page links"), a link's
#   title isn't said (JAWS says a link's screen text), and when quick navigation moves to a heading with a link, the
#   link's states come before the heading and "link" after it.
# - settingsMap: NVDA's "Report link type", whose only type is "same page", comes from JAWS's "Identify same page
#   links", not from "Identify link type" (mail, FTP and news links).
# The imitation NVDA runs NVDA 2026.2's own code, word for word, taken from the release-2026.2 sources by script:
# speakTextInfo and getTextInfoSpeech with their helpers, getControlFieldSpeech, _shouldSpeakContentFirst,
# getPropertiesSpeech, controlTypes.processAndLabelStates, textInfos' Field, ControlField (getPresentationCategory),
# FieldCommand and TextInfo.getControlFieldSpeech, utils.urlUtils.getLinkType and isSamePageURL, browseMode's
# BrowseModeTreeInterceptor.getLinkTypeInDocument and TextInfoQuickNavItem.report, the link part of the virtual buffer's
# GeckoVBufTextInfo._normalizeControlField, and Firefox's and Chrome's _calculateDescriptionFrom; NVDA's roles, states
# and default settings are read from its role.py, state.py and configSpec.py. The pages are the tester's, as Edge
# gives them to NVDA's virtual buffer. The assistant's code (linkSpeech, quickNavHeadings, settingsMap) is the real one.
# Run: python -m unittest tests.test_v125_linkSpeech -v

import __future__
import copy
import enum
import functools
import itertools
import os
import sys
import textwrap
import types
import unicodedata
import unittest
import weakref
from unittest import mock
from urllib.parse import ParseResult, urlparse, urlunparse

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import jawsFiles, linkSpeech, quickNavHeadings, settingsMap, state  # noqa: E402


#: NVDA 2026.2, source/controlTypes/outputReason.py, OutputReason, word for word.
NVDA_OUTPUT_REASON = r'''
class OutputReason(Enum):
	"""Specify the reason that a given piece of output was generated."""

	#: An object to be reported due to a focus change or similar.
	FOCUS = auto()
	#: An ancestor of the focus object to be reported due to a focus change or similar.
	FOCUSENTERED = auto()
	#: An item under the mouse.
	MOUSE = auto()
	#: A response to a user query.
	QUERY = auto()
	#: Reporting a change to an object.
	CHANGE = auto()
	#: A generic, screen reader specific message.
	MESSAGE = auto()
	#: Text reported as part of a say all.
	SAYALL = auto()
	#: Content reported due to caret movement or similar.
	CARET = auto()
	#: No output, but any state should be cached as if output had occurred.
	ONLYCACHE = auto()

	QUICKNAV = auto()
'''


#: NVDA 2026.2, source/controlTypes/descriptionFrom.py, DescriptionFrom, word for word.
NVDA_DESCRIPTION_FROM = r'''
class DescriptionFrom(Enum):
	"""Values to use within NVDA to denote possible values for DescriptionFrom.
	These are used to determine how the source of the 'description' property if an NVDAObject.
	"""

	UNKNOWN = auto()
	ARIA_DESCRIPTION = "aria-description"
	ARIA_DESCRIBED_BY = "aria-describedby"
	RUBY_ANNOTATION = "ruby-annotation"
	SUMMARY = "summary"
	TABLE_CAPTION = "table-caption"
	TOOLTIP = "tooltip"  # (either via @title or aria-describedby + role="tooltip")
	BUTTON_LABEL = "button-label"
'''


#: NVDA 2026.2, source/virtualBuffers/gecko_ia2.py, Gecko_ia2_TextInfo._calculateDescriptionFrom, word for word.
NVDA_GECKO_DESCRIPTION_FROM = r'''
def _calculateDescriptionFrom(self, attrs: textInfos.ControlField) -> controlTypes.DescriptionFrom:
	"""Overridable calculation of DescriptionFrom
	Match behaviour of NVDAObjects.IAccessible.mozilla.Mozilla._get_descriptionFrom
	@param attrs: source attributes for the TextInfo
	@return: the origin for accDescription.
	@remarks: Firefox does not yet have a 'IAccessible2::attribute_description-from'
		(IA2 attribute "description-from").
		We can infer that the origin of accDescription is 'aria-description' because Firefox will include
		a 'IAccessible2::attribute_description' (IA2 attribute "description") when the aria-description
		HTML attribute is used.
		If 'IAccessible2::attribute_description' matches the accDescription value, we can infer that
		aria-description was the original source.
	"""
	IA2Attr_desc = attrs.get("IAccessible2::attribute_description")
	accDesc = attrs.get("description")
	if not IA2Attr_desc or accDesc != IA2Attr_desc:
		return controlTypes.DescriptionFrom.UNKNOWN
	else:
		return controlTypes.DescriptionFrom.ARIA_DESCRIPTION
'''


#: NVDA 2026.2, source/NVDAObjects/IAccessible/chromium.py, ChromeVBufTextInfo._calculateDescriptionFrom, word for word.
NVDA_CHROME_DESCRIPTION_FROM = r'''
def _calculateDescriptionFrom(self, attrs) -> controlTypes.DescriptionFrom:
	"""Overridable calculation of DescriptionFrom
	@param attrs: source attributes for the TextInfo
	@return: the origin for accDescription.
	@note: Chrome provides 'IAccessible2::attribute_description-from' which declares the origin used for
		accDescription. Chrome also provides `IAccessible2::attribute_description` to maintain compatibility
		with FireFox.
	"""
	ia2attrDescriptionFrom = attrs.get("IAccessible2::attribute_description-from")
	try:
		return controlTypes.DescriptionFrom(ia2attrDescriptionFrom)
	except ValueError:
		if ia2attrDescriptionFrom:
			log.debugWarning(f"Unknown 'description-from' IA2Attribute value: {ia2attrDescriptionFrom}")
	# fallback to Firefox approach
	return super()._calculateDescriptionFrom(attrs)
'''


#: NVDA 2026.2, source/speech/types.py, GeneratorWithReturn, word for word.
NVDA_GENERATOR_WITH_RETURN = r'''
class GeneratorWithReturn(Iterable):
	"""Helper class, used with generator functions to access the 'return' value after there are no more values
	to iterate over.
	"""

	def __init__(self, gen: Iterable, defaultReturnValue=None):
		self.gen = gen
		self.returnValue = defaultReturnValue
		self.iterationFinished = False

	def __iter__(self):
		self.returnValue = yield from self.gen
		self.iterationFinished = True
'''


#: NVDA 2026.2, source/speech/speech.py, BLANK_CHUNK_CHARS, word for word.
NVDA_BLANK_CHUNK_CHARS = r'''
BLANK_CHUNK_CHARS = frozenset((" ", "\n", "\r", "\0", "\xa0"))
'''


#: NVDA 2026.2, source/speech/speech.py, isBlank, word for word.
NVDA_IS_BLANK = r'''
def isBlank(text):
	"""Determine whether text should be reported as blank.
	@param text: The text in question.
	@type text: str
	@return: C{True} if the text is blank, C{False} if not.
	@rtype: bool
	"""
	return not text or set(text) <= BLANK_CHUNK_CHARS
'''


#: NVDA 2026.2, source/speech/languageHandling.py, shouldMakeLangChangeCommand, word for word.
NVDA_LANG_CHANGE = r'''
def shouldMakeLangChangeCommand() -> bool:
	"""Determines if NVDA should get the language of the text been read."""
	return config.conf["speech"]["autoLanguageSwitching"] or config.conf["speech"]["reportLanguage"]
'''


#: NVDA 2026.2, source/controlTypes/state.py, STATES_SORTED, word for word.
NVDA_STATES_SORTED = r'''
STATES_SORTED = frozenset([State.SORTED, State.SORTED_ASCENDING, State.SORTED_DESCENDING])
'''


#: NVDA 2026.2, source/controlTypes/state.py, STATES_LINK_TYPE, word for word.
NVDA_STATES_LINK_TYPE = r'''
STATES_LINK_TYPE = frozenset([State.INTERNAL_LINK])
'''


#: NVDA 2026.2, source/controlTypes/role.py, clickableRoles, word for word.
NVDA_CLICKABLE_ROLES = r'''
clickableRoles: Set[Role] = {
	Role.LINK,
	Role.BUTTON,
	Role.CHECKBOX,
	Role.RADIOBUTTON,
	Role.TOGGLEBUTTON,
	Role.MENUITEM,
	Role.TAB,
	Role.SLIDER,
	Role.DOCUMENT,
	Role.CHECKMENUITEM,
	Role.RADIOMENUITEM,
}
'''


#: NVDA 2026.2, source/controlTypes/role.py, silentValuesForRoles, word for word.
NVDA_SILENT_VALUES = r'''
silentValuesForRoles: Set[Role] = {
	Role.CHECKBOX,
	Role.RADIOBUTTON,
	Role.LINK,
	Role.MENUITEM,
	Role.APPLICATION,
	Role.BUSY_INDICATOR,
}
'''


#: NVDA 2026.2, source/textInfos/__init__.py, Field, word for word.
NVDA_FIELD = r'''
class Field(dict):
	"""Provides information about a piece of text."""
'''


#: NVDA 2026.2, source/textInfos/__init__.py, FormatField, word for word.
NVDA_FORMAT_FIELD = r'''
class FormatField(Field):
	"""Provides information about the formatting of text; e.g. font information and hyperlinks."""
'''


#: NVDA 2026.2, source/textInfos/__init__.py, ControlField, word for word.
NVDA_CONTROL_FIELD = r'''
class ControlField(Field):
	"""Provides information about a control which encompasses text.
	For example, a piece of text might be contained within a table, button, form, etc.
	This field contains information about such a control, such as its role, name and description.
	"""

	#: This field is usually a single line item; e.g. a link or heading.
	PRESCAT_SINGLELINE = "singleLine"
	#: This field is a marker; e.g. a separator or footnote.
	PRESCAT_MARKER = "marker"
	#: This field is a container, usually multi-line.
	PRESCAT_CONTAINER = "container"
	#: This field is a section of a larger container which is adjacent to another similar section;
	#: e.g. a table cell.
	PRESCAT_CELL = "cell"
	#: This field is just for layout.
	PRESCAT_LAYOUT = None

	def getPresentationCategory(
		self,
		ancestors,
		formatConfig,
		reason=OutputReason.CARET,
		extraDetail=False,
	):
		role = self.get("role", controlTypes.Role.UNKNOWN)
		states = self.get("states", set())

		# Honour verbosity configuration.
		if role in (
			controlTypes.Role.TABLE,
			controlTypes.Role.TABLECELL,
			controlTypes.Role.TABLEROWHEADER,
			controlTypes.Role.TABLECOLUMNHEADER,
		):
			# The user doesn't want layout tables.
			# Find the nearest table.
			if role == controlTypes.Role.TABLE:
				# This is the nearest table.
				table = self
			else:
				# Search ancestors for the nearest table.
				for anc in reversed(ancestors):
					if anc.get("role") == controlTypes.Role.TABLE:
						table = anc
						break
				else:
					table = None
			if (
				not table
				or (not formatConfig["includeLayoutTables"] and table.get("table-layout", None))
				or table.get("isHidden", False)
			):
				return self.PRESCAT_LAYOUT

		name = self.get("name")
		landmark = self.get("landmark")
		if reason in (
			OutputReason.CARET,
			OutputReason.SAYALL,
			OutputReason.FOCUS,
			OutputReason.QUICKNAV,
		) and (
			(role == controlTypes.Role.LINK and not formatConfig["reportLinks"])
			or (role == controlTypes.Role.GRAPHIC and not formatConfig["reportGraphics"])
			or (role == controlTypes.Role.HEADING and not formatConfig["reportHeadings"])
			or (role == controlTypes.Role.BLOCKQUOTE and not formatConfig["reportBlockQuotes"])
			or (role == controlTypes.Role.GROUPING and (not name or not formatConfig["reportGroupings"]))
			or (
				role
				in (
					controlTypes.Role.TABLE,
					controlTypes.Role.TABLECELL,
					controlTypes.Role.TABLEROWHEADER,
					controlTypes.Role.TABLECOLUMNHEADER,
				)
				and not formatConfig["reportTables"]
			)
			or (
				role in (controlTypes.Role.LIST, controlTypes.Role.LISTITEM)
				and controlTypes.State.READONLY in states
				and not formatConfig["reportLists"]
			)
			or (role == controlTypes.Role.ARTICLE and not formatConfig["reportArticles"])
			or (role == controlTypes.Role.MARKED_CONTENT and not formatConfig["reportHighlight"])
			or (
				role in (controlTypes.Role.FRAME, controlTypes.Role.INTERNALFRAME)
				and not formatConfig["reportFrames"]
			)
			or (
				role in (controlTypes.Role.DELETED_CONTENT, controlTypes.Role.INSERTED_CONTENT)
				and not formatConfig["reportRevisions"]
			)
			or ((role == controlTypes.Role.LANDMARK or landmark) and not formatConfig["reportLandmarks"])
			or (role == controlTypes.Role.REGION and (not name or not formatConfig["reportLandmarks"]))
			or (
				role in {controlTypes.Role.FIGURE, controlTypes.Role.CAPTION}
				and not formatConfig["reportFigures"]
			)
		):
			# This is just layout as far as the user is concerned.
			return self.PRESCAT_LAYOUT

		if (
			role
			in (
				controlTypes.Role.DELETED_CONTENT,
				controlTypes.Role.INSERTED_CONTENT,
				controlTypes.Role.LINK,
				controlTypes.Role.HEADING,
				controlTypes.Role.BUTTON,
				controlTypes.Role.RADIOBUTTON,
				controlTypes.Role.CHECKBOX,
				controlTypes.Role.SWITCH,
				controlTypes.Role.GRAPHIC,
				controlTypes.Role.CHART,
				controlTypes.Role.MENUITEM,
				controlTypes.Role.TAB,
				controlTypes.Role.COMBOBOX,
				controlTypes.Role.SLIDER,
				controlTypes.Role.SPINBUTTON,
				controlTypes.Role.PROGRESSBAR,
				controlTypes.Role.BUSY_INDICATOR,
				controlTypes.Role.TOGGLEBUTTON,
				controlTypes.Role.MENUBUTTON,
				controlTypes.Role.TREEVIEW,
				controlTypes.Role.CHECKMENUITEM,
				controlTypes.Role.RADIOMENUITEM,
			)
			or (
				role == controlTypes.Role.EDITABLETEXT
				and controlTypes.State.MULTILINE not in states
				and (controlTypes.State.READONLY not in states or controlTypes.State.FOCUSABLE in states)
			)
			or (role == controlTypes.Role.LIST and controlTypes.State.READONLY not in states)
		):
			return self.PRESCAT_SINGLELINE
		elif role in (
			controlTypes.Role.SEPARATOR,
			controlTypes.Role.FOOTNOTE,
			controlTypes.Role.ENDNOTE,
			controlTypes.Role.EMBEDDEDOBJECT,
			controlTypes.Role.MATH,
		) or (extraDetail and role == controlTypes.Role.LISTITEM):
			return self.PRESCAT_MARKER
		elif role in (controlTypes.Role.APPLICATION, controlTypes.Role.DIALOG):
			# Applications and dialogs should be reported as markers when embedded within content, but not when they themselves are the root
			return self.PRESCAT_MARKER if ancestors else self.PRESCAT_LAYOUT
		elif role in (
			controlTypes.Role.TABLECELL,
			controlTypes.Role.TABLECOLUMNHEADER,
			controlTypes.Role.TABLEROWHEADER,
		):
			return self.PRESCAT_CELL
		elif (
			role
			in (
				controlTypes.Role.BLOCKQUOTE,
				controlTypes.Role.GROUPING,
				controlTypes.Role.FIGURE,
				controlTypes.Role.CAPTION,
				controlTypes.Role.REGION,
				controlTypes.Role.FRAME,
				controlTypes.Role.INTERNALFRAME,
				controlTypes.Role.TOOLBAR,
				controlTypes.Role.MENUBAR,
				controlTypes.Role.POPUPMENU,
				controlTypes.Role.TABLE,
				controlTypes.Role.ARTICLE,
				controlTypes.Role.MARKED_CONTENT,
			)
			or (
				role == controlTypes.Role.EDITABLETEXT
				and (controlTypes.State.READONLY not in states or controlTypes.State.FOCUSABLE in states)
				and controlTypes.State.MULTILINE in states
			)
			or (role == controlTypes.Role.LIST and controlTypes.State.READONLY in states)
			or (role == controlTypes.Role.LANDMARK or landmark)
			or (controlTypes.State.FOCUSABLE in states and controlTypes.State.EDITABLE in states)
		):
			return self.PRESCAT_CONTAINER

		# If the author has provided specific role text, then this should be presented either as container or singleLine depending on whether the field is block or not.
		if self.get("roleText"):
			if self.get("isBlock"):
				return self.PRESCAT_CONTAINER
			else:
				return self.PRESCAT_SINGLELINE

		return self.PRESCAT_LAYOUT
'''


#: NVDA 2026.2, source/textInfos/__init__.py, FieldCommand, word for word.
NVDA_FIELD_COMMAND = r'''
class FieldCommand(object):
	"""A command indicating a L{Field} in a sequence of text and fields.
	When retrieving text with its associated fields, a L{TextInfo} provides a sequence of text strings and L{FieldCommand}s.
	A command indicates the start or end of a control or that the formatting of the text has changed.
	"""

	def __init__(self, command: str, field: Optional[Union[ControlField, FormatField]]):
		"""Constructor.
		@param command: The command; one of:
			"controlStart", indicating the start of a L{ControlField};
			"controlEnd", indicating the end of a L{ControlField}; or
			"formatChange", indicating a L{FormatField} change.
		@param field: The field associated with this command; may be C{None} for controlEnd.
		"""
		if command not in ("controlStart", "controlEnd", "formatChange"):
			raise ValueError("Unknown command: %s" % command)
		elif command == "controlStart" and not isinstance(field, ControlField):
			raise ValueError("command: %s needs a controlField" % command)
		elif command == "formatChange" and not isinstance(field, FormatField):
			raise ValueError("command: %s needs a formatField" % command)
		self.command = command
		self.field = field

	def __repr__(self):
		return "FieldCommand %s with %s" % (self.command, self.field)
'''


#: NVDA 2026.2, source/textInfos/__init__.py, TextInfo.getControlFieldSpeech, word for word.
NVDA_TEXT_INFO_CONTROL_FIELD_SPEECH = r'''
def getControlFieldSpeech(
	self,
	attrs: ControlField,
	ancestorAttrs: List[Field],
	fieldType: str,
	formatConfig: Optional[Dict[str, bool]] = None,
	extraDetail: bool = False,
	reason: Optional[OutputReason] = None,
) -> SpeechSequence:
	# Import late to avoid circular import.
	import speech

	sequence = speech.getControlFieldSpeech(
		attrs,
		ancestorAttrs,
		fieldType,
		formatConfig,
		extraDetail,
		reason,
	)
	_logBadSequenceTypes(sequence)
	return sequence
'''


#: NVDA 2026.2, source/speech/speech.py, SpeakTextInfoState, word for word.
NVDA_SPEAK_TEXT_INFO_STATE = r'''
class SpeakTextInfoState(object):
	"""Caches the state of speakTextInfo such as the current controlField stack, current formatfield and indentation."""

	__slots__ = [
		"objRef",
		"controlFieldStackCache",
		"formatFieldAttributesCache",
		"indentationCache",
	]

	def __init__(self, obj):
		if isinstance(obj, SpeakTextInfoState):
			oldState = obj
			self.objRef = oldState.objRef
		else:
			self.objRef = weakref.ref(obj)
			oldState = getattr(obj, "_speakTextInfoState", None)
		self.controlFieldStackCache = list(oldState.controlFieldStackCache) if oldState else []
		self.formatFieldAttributesCache = oldState.formatFieldAttributesCache if oldState else {}
		self.indentationCache = oldState.indentationCache if oldState else ""

	def updateObj(self):
		obj = self.objRef()
		if obj:
			obj._speakTextInfoState = self.copy()

	def copy(self):
		return self.__class__(self)
'''


#: NVDA 2026.2, source/speech/speech.py, speakTextInfo, word for word.
NVDA_SPEAK_TEXT_INFO = r'''
def speakTextInfo(
	info: textInfos.TextInfo,
	useCache: Union[bool, SpeakTextInfoState] = True,
	formatConfig: Dict[str, bool] = None,
	unit: Optional[str] = None,
	reason: OutputReason = OutputReason.QUERY,
	_prefixSpeechCommand: Optional[SpeechCommand] = None,
	onlyInitialFields: bool = False,
	suppressBlanks: bool = False,
	priority: Optional[Spri] = None,
) -> bool:
	speechGen = getTextInfoSpeech(
		info,
		useCache,
		formatConfig,
		unit,
		reason,
		_prefixSpeechCommand,
		onlyInitialFields,
		suppressBlanks,
	)

	speechGen = GeneratorWithReturn(speechGen)
	for seq in speechGen:
		speak(seq, priority=priority)
	return speechGen.returnValue
'''


#: NVDA 2026.2, source/speech/speech.py, getTextInfoSpeech, word for word.
NVDA_TEXT_INFO_SPEECH = r'''
def getTextInfoSpeech(  # noqa: C901
	info: textInfos.TextInfo,
	useCache: Union[bool, SpeakTextInfoState] = True,
	formatConfig: dict[str, bool | int] | None = None,
	unit: Optional[str] = None,
	reason: OutputReason = OutputReason.QUERY,
	_prefixSpeechCommand: Optional[SpeechCommand] = None,
	onlyInitialFields: bool = False,
	suppressBlanks: bool = False,
) -> Generator[SpeechSequence, None, bool]:
	if isinstance(useCache, SpeakTextInfoState):
		speakTextInfoState = useCache
	elif useCache:
		speakTextInfoState = SpeakTextInfoState(info.obj)
	else:
		speakTextInfoState = None
	extraDetail = unit in (textInfos.UNIT_CHARACTER, textInfos.UNIT_WORD)
	if not formatConfig:
		formatConfig = config.conf["documentFormatting"]
	formatConfig = formatConfig.copy()
	if extraDetail:
		formatConfig["extraDetail"] = True
	reportIndentation = (
		unit == textInfos.UNIT_LINE and formatConfig["reportLineIndentation"] != ReportLineIndentation.OFF
	)
	# For performance reasons, when navigating by paragraph or table cell, spelling errors will not be announced.
	if unit in (textInfos.UNIT_PARAGRAPH, textInfos.UNIT_CELL) and reason == OutputReason.CARET:
		formatConfig["reportSpellingErrors2"] = 0

	# Fetch the last controlFieldStack, or make a blank one
	controlFieldStackCache = speakTextInfoState.controlFieldStackCache if speakTextInfoState else []
	formatFieldAttributesCache = speakTextInfoState.formatFieldAttributesCache if speakTextInfoState else {}
	textWithFields = info.getTextWithFields(formatConfig)
	# We don't care about node bounds, especially when comparing fields.
	# Remove them.
	for command in textWithFields:
		if not isinstance(command, textInfos.FieldCommand):
			continue
		field = command.field
		if not field:
			continue
		try:
			del field["_startOfNode"]
		except KeyError:
			pass
		try:
			del field["_endOfNode"]
		except KeyError:
			pass

	# Make a new controlFieldStack and formatField from the textInfo's initialFields
	newControlFieldStack: List[textInfos.ControlField] = []
	newFormatField = textInfos.FormatField()
	initialFields = []
	for field in textWithFields:
		if isinstance(field, textInfos.FieldCommand) and field.command in ("controlStart", "formatChange"):
			initialFields.append(field.field)
		else:
			break
	if len(initialFields) > 0:
		del textWithFields[0 : len(initialFields)]
	endFieldCount = 0
	for field in reversed(textWithFields):
		if isinstance(field, textInfos.FieldCommand) and field.command == "controlEnd":
			endFieldCount += 1
		else:
			break
	if endFieldCount > 0:
		del textWithFields[0 - endFieldCount :]
	for field in initialFields:
		if isinstance(field, textInfos.ControlField):
			newControlFieldStack.append(field)
		elif isinstance(field, textInfos.FormatField):
			newFormatField.update(field)
		else:
			raise ValueError("unknown field: %s" % field)
	# Calculate how many fields in the old and new controlFieldStacks are the same
	commonFieldCount = 0
	for count in range(min(len(newControlFieldStack), len(controlFieldStackCache))):
		# #2199: When comparing controlFields try using uniqueID if it exists before resorting to compairing the entire dictionary
		oldUniqueID = controlFieldStackCache[count].get("uniqueID")
		newUniqueID = newControlFieldStack[count].get("uniqueID")
		if ((oldUniqueID is not None or newUniqueID is not None) and newUniqueID == oldUniqueID) or (
			newControlFieldStack[count] == controlFieldStackCache[count]
		):
			commonFieldCount += 1
		else:
			break

	speechSequence: SpeechSequence = []
	# #2591: Only if the reason is not focus, Speak the exit of any controlFields not in the new stack.
	# We don't do this for focus because hearing "out of list", etc. isn't useful when tabbing or using quick navigation and makes navigation less efficient.
	if reason not in [OutputReason.FOCUS, OutputReason.QUICKNAV]:
		endingBlock = False
		for count in reversed(range(commonFieldCount, len(controlFieldStackCache))):
			fieldSequence = info.getControlFieldSpeech(
				controlFieldStackCache[count],
				controlFieldStackCache[0:count],
				"end_removedFromControlFieldStack",
				formatConfig,
				extraDetail,
				reason=reason,
			)
			if fieldSequence:
				speechSequence.extend(fieldSequence)
			if not endingBlock and reason == OutputReason.SAYALL:
				endingBlock = bool(int(controlFieldStackCache[count].get("isBlock", 0)))
		if endingBlock:
			speechSequence.append(EndUtteranceCommand())
	# The TextInfo should be considered blank if we are only exiting fields (i.e. we aren't
	# entering any new fields and there is no text).
	shouldConsiderTextInfoBlank = True

	if _prefixSpeechCommand is not None:
		assert isinstance(_prefixSpeechCommand, SpeechCommand)
		speechSequence.append(_prefixSpeechCommand)

	# Get speech text for any fields that are in both controlFieldStacks, if extra detail is not requested
	if not extraDetail:
		for count in range(commonFieldCount):
			field = newControlFieldStack[count]
			fieldSequence = info.getControlFieldSpeech(
				field,
				newControlFieldStack[0:count],
				"start_inControlFieldStack",
				formatConfig,
				extraDetail,
				reason=reason,
			)
			if fieldSequence:
				speechSequence.extend(fieldSequence)
				shouldConsiderTextInfoBlank = False
			if field.get("role") == controlTypes.Role.MATH:
				shouldConsiderTextInfoBlank = False
				_extendSpeechSequence_addMathForTextInfo(speechSequence, info, field)

	# When true, we are inside a clickable field, and should therefore not announce any more new clickable fields
	inClickable = False
	# Get speech text for any fields in the new controlFieldStack that are not in the old controlFieldStack
	for count in range(commonFieldCount, len(newControlFieldStack)):
		field = newControlFieldStack[count]
		if not inClickable and formatConfig["reportClickable"]:
			states = field.get("states")
			if states and controlTypes.State.CLICKABLE in states:
				# We entered the most outer clickable, so announce it, if we won't be announcing anything else interesting for this field
				presCat = field.getPresentationCategory(newControlFieldStack[0:count], formatConfig, reason)
				if not presCat or presCat is field.PRESCAT_LAYOUT:
					speechSequence.append(controlTypes.State.CLICKABLE.displayString)
					shouldConsiderTextInfoBlank = False
				inClickable = True
		fieldSequence = info.getControlFieldSpeech(
			field,
			newControlFieldStack[0:count],
			"start_addedToControlFieldStack",
			formatConfig,
			extraDetail,
			reason=reason,
		)
		if fieldSequence:
			speechSequence.extend(fieldSequence)
			shouldConsiderTextInfoBlank = False
		if field.get("role") == controlTypes.Role.MATH:
			shouldConsiderTextInfoBlank = False
			_extendSpeechSequence_addMathForTextInfo(speechSequence, info, field)
		commonFieldCount += 1

	# Fetch the text for format field attributes that have changed between what was previously cached, and this textInfo's initialFormatField.
	fieldSequence = info.getFormatFieldSpeech(
		newFormatField,
		formatFieldAttributesCache,
		formatConfig,
		reason=reason,
		unit=unit,
		extraDetail=extraDetail,
		initialFormat=True,
	)
	if fieldSequence:
		speechSequence.extend(fieldSequence)
	language = None
	if languageHandling.shouldMakeLangChangeCommand():
		language = newFormatField.get("language")
		speechSequence.append(LangChangeCommand(language))
		lastLanguage = language
	isWordOrCharUnit = unit in (textInfos.UNIT_CHARACTER, textInfos.UNIT_WORD)
	firstText = ""
	if len(textWithFields) > 0:
		firstField = textWithFields[0]
		if isinstance(firstField, str):
			firstText = firstField.strip() if not firstField.isspace() else firstField
	if onlyInitialFields or (
		isWordOrCharUnit
		and (len(firstText) == 1 or len(unicodeNormalize(firstText)) == 1)
		and all(_isControlEndFieldCommand(x) for x in itertools.islice(textWithFields, 1, None))
	):
		if reason != OutputReason.ONLYCACHE:
			yield from _getTextInfoSpeech_considerSpelling(
				unit,
				onlyInitialFields,
				textWithFields,
				reason,
				speechSequence,
				language,
			)
		if useCache:
			_getTextInfoSpeech_updateCache(
				useCache,
				speakTextInfoState,
				newControlFieldStack,
				formatFieldAttributesCache,
			)
		return False

	# Similar to before, but If the most inner clickable is exited, then we allow announcing clickable for the next lot of clickable fields entered.
	inClickable = False
	# Move through the field commands, getting speech text for all controlStarts, controlEnds and formatChange commands
	# But also keep newControlFieldStack up to date as we will need it for the ends
	# Add any text to a separate list, as it must be handled differently.
	# Also make sure that LangChangeCommand objects are added before any controlField or formatField speech
	relativeSpeechSequence = []
	inTextChunk = False
	allIndentation = ""
	indentationDone = False
	for command in textWithFields:
		if isinstance(command, str):
			# Text should break a run of clickables
			inClickable = False
			if reportIndentation and not indentationDone:
				indentation, command = splitTextIndentation(command)
				# Combine all indentation into one string for later processing.
				allIndentation += indentation
				if command:
					# There was content after the indentation, so there is no more indentation.
					indentationDone = True
			if command:
				if inTextChunk:
					relativeSpeechSequence[-1] += command
				else:
					relativeSpeechSequence.append(command)
					inTextChunk = True
		elif isinstance(command, textInfos.FieldCommand):
			newLanguage = None
			if command.command == "controlStart":
				# Control fields always start a new chunk, even if they have no field text.
				inTextChunk = False
				fieldSequence = []
				if not inClickable and formatConfig["reportClickable"]:
					states = command.field.get("states")
					if states and controlTypes.State.CLICKABLE in states:
						# We have entered an outer most clickable or entered a new clickable after exiting a previous one
						# Announce it if there is nothing else interesting about the field, but not if the user turned it off.
						presCat = command.field.getPresentationCategory(
							newControlFieldStack[0:],
							formatConfig,
							reason,
						)
						if not presCat or presCat is command.field.PRESCAT_LAYOUT:
							fieldSequence.append(controlTypes.State.CLICKABLE.displayString)
						inClickable = True
				fieldSequence.extend(
					info.getControlFieldSpeech(
						command.field,
						newControlFieldStack,
						"start_relative",
						formatConfig,
						extraDetail,
						reason=reason,
					),
				)
				newControlFieldStack.append(command.field)
			elif command.command == "controlEnd":
				# Exiting a controlField should break a run of clickables
				inClickable = False
				# Control fields always start a new chunk, even if they have no field text.
				inTextChunk = False
				fieldSequence = info.getControlFieldSpeech(
					newControlFieldStack[-1],
					newControlFieldStack[0:-1],
					"end_relative",
					formatConfig,
					extraDetail,
					reason=reason,
				)
				del newControlFieldStack[-1]
				if commonFieldCount > len(newControlFieldStack):
					commonFieldCount = len(newControlFieldStack)
			elif command.command == "formatChange":
				fieldSequence = info.getFormatFieldSpeech(
					command.field,
					formatFieldAttributesCache,
					formatConfig,
					reason=reason,
					unit=unit,
					extraDetail=extraDetail,
				)
				if fieldSequence:
					inTextChunk = False
				if languageHandling.shouldMakeLangChangeCommand():
					newLanguage = command.field.get("language")
					if lastLanguage != newLanguage:
						# The language has changed, so this starts a new text chunk.
						inTextChunk = False
			if not inTextChunk:
				if fieldSequence:
					if languageHandling.shouldMakeLangChangeCommand() and lastLanguage is not None:
						# Fields must be spoken in the default language.
						relativeSpeechSequence.append(LangChangeCommand(None))
						lastLanguage = None
					relativeSpeechSequence.extend(fieldSequence)
				if command.command == "controlStart" and command.field.get("role") == controlTypes.Role.MATH:
					_extendSpeechSequence_addMathForTextInfo(relativeSpeechSequence, info, command.field)
				if languageHandling.shouldMakeLangChangeCommand() and newLanguage != lastLanguage:
					relativeSpeechSequence.append(LangChangeCommand(newLanguage))
					lastLanguage = newLanguage
	if (
		reportIndentation
		and speakTextInfoState
		and (
			# either not ignoring blank lines
			not formatConfig["ignoreBlankLinesForRLI"]
			# or line isn't completely blank
			or any(not (set(t) <= LINE_END_CHARS) for t in textWithFields if isinstance(t, str))
		)
		and allIndentation != speakTextInfoState.indentationCache
	):
		indentationSpeech = getIndentationSpeech(allIndentation, formatConfig)
		if languageHandling.shouldMakeLangChangeCommand() and speechSequence[-1].lang is not None:
			# Indentation must be spoken in the default language,
			# but the initial format field specified a different language.
			# Insert the indentation before the LangChangeCommand.
			langChange = speechSequence.pop()
			speechSequence.extend(indentationSpeech)
			speechSequence.append(langChange)
		else:
			speechSequence.extend(indentationSpeech)
		if speakTextInfoState:
			speakTextInfoState.indentationCache = allIndentation
	# Don't add this text if it is blank.
	relativeBlank = True
	for x in relativeSpeechSequence:
		if isinstance(x, str) and not isBlank(x):
			relativeBlank = False
			break
	if not relativeBlank:
		speechSequence.extend(relativeSpeechSequence)
		shouldConsiderTextInfoBlank = False

	# Finally get speech text for any fields left in new controlFieldStack that are common with the old controlFieldStack (for closing), if extra detail is not requested
	if languageHandling.shouldMakeLangChangeCommand() and lastLanguage is not None:
		speechSequence.append(
			LangChangeCommand(None),
		)
		lastLanguage = None
	if not extraDetail:
		for count in reversed(range(min(len(newControlFieldStack), commonFieldCount))):
			fieldSequence = info.getControlFieldSpeech(
				newControlFieldStack[count],
				newControlFieldStack[0:count],
				"end_inControlFieldStack",
				formatConfig,
				extraDetail,
				reason=reason,
			)
			if fieldSequence:
				speechSequence.extend(fieldSequence)
				shouldConsiderTextInfoBlank = False

	# If there is nothing that should cause the TextInfo to be considered
	# non-blank, blank should be reported, unless we are doing a say all.
	if not suppressBlanks and reason != OutputReason.SAYALL and shouldConsiderTextInfoBlank:
		# Translators: This is spoken when the line is considered blank.
		speechSequence.append(_("blank"))

	# Cache a copy of the new controlFieldStack for future use
	if useCache:
		_getTextInfoSpeech_updateCache(
			useCache,
			speakTextInfoState,
			newControlFieldStack,
			formatFieldAttributesCache,
		)

	if reason == OutputReason.ONLYCACHE or not speechSequence:
		return False

	yield speechSequence
	return True
'''


#: NVDA 2026.2, source/speech/speech.py, LINE_END_CHARS, word for word.
NVDA_LINE_END_CHARS = r'''
LINE_END_CHARS = frozenset(("\r", "\n"))
'''


#: NVDA 2026.2, source/speech/speech.py, _isControlEndFieldCommand, word for word.
NVDA_IS_CONTROL_END = r'''
def _isControlEndFieldCommand(command: Union[str, textInfos.FieldCommand]):
	return isinstance(command, textInfos.FieldCommand) and command.command == "controlEnd"
'''


#: NVDA 2026.2, source/speech/speech.py, _getTextInfoSpeech_considerSpelling, word for word.
NVDA_CONSIDER_SPELLING = r'''
def _getTextInfoSpeech_considerSpelling(
	unit: Optional[textInfos.TextInfo],
	onlyInitialFields: bool,
	textWithFields: textInfos.TextInfo.TextWithFieldsT,
	reason: OutputReason,
	speechSequence: SpeechSequence,
	language: str,
) -> Generator[SpeechSequence, None, None]:
	if onlyInitialFields or speechSequence:
		yield speechSequence
	if not onlyInitialFields:
		spellingSequence = list(
			getSpellingSpeech(
				textWithFields[0],
				locale=language,
			),
		)
		logBadSequenceTypes(spellingSequence)
		yield spellingSequence
		if (
			reason == OutputReason.CARET
			and unit == textInfos.UNIT_CHARACTER
			and config.conf["speech"]["delayedCharacterDescriptions"]
		):
			descriptionSequence = list(
				getSingleCharDescription(
					textWithFields[0],
					locale=language,
				),
			)
			yield descriptionSequence
'''


#: NVDA 2026.2, source/speech/speech.py, _getTextInfoSpeech_updateCache, word for word.
NVDA_UPDATE_CACHE = r'''
def _getTextInfoSpeech_updateCache(
	useCache: Union[bool, SpeakTextInfoState],
	speakTextInfoState: SpeakTextInfoState,
	newControlFieldStack: List[textInfos.ControlField],
	formatFieldAttributesCache: textInfos.Field,
):
	speakTextInfoState.controlFieldStackCache = newControlFieldStack
	speakTextInfoState.formatFieldAttributesCache = formatFieldAttributesCache
	if not isinstance(useCache, SpeakTextInfoState):
		speakTextInfoState.updateObj()
'''


#: NVDA 2026.2, source/speech/speech.py, _shouldSpeakContentFirst, word for word.
NVDA_CONTENT_FIRST = r'''
def _shouldSpeakContentFirst(
	reason: OutputReason,
	role: int,
	presCat: str,
	attrs: textInfos.ControlField,
	tableID: Any,
	states: Iterable[int],
) -> bool:
	"""
	Determines whether or not to speak the content before the controlField information.
	Helper function for getControlFieldSpeech.
	"""
	_neverSpeakContentFirstRoles = (
		controlTypes.Role.EDITABLETEXT,
		controlTypes.Role.COMBOBOX,
		controlTypes.Role.TREEVIEW,
		controlTypes.Role.LIST,
		controlTypes.Role.LANDMARK,
		controlTypes.Role.REGION,
	)
	return (
		reason in [OutputReason.FOCUS, OutputReason.QUICKNAV]
		and (
			# the category is not a container, unless it's an article (#11103)
			presCat != attrs.PRESCAT_CONTAINER or role == controlTypes.Role.ARTICLE
		)
		and role not in _neverSpeakContentFirstRoles
		and not tableID
		and controlTypes.State.EDITABLE not in states
	)
'''


#: NVDA 2026.2, source/speech/speech.py, getControlFieldSpeech, word for word.
NVDA_CONTROL_FIELD_SPEECH = r'''
def getControlFieldSpeech(  # noqa: C901
	attrs: textInfos.ControlField,
	ancestorAttrs: List[textInfos.Field],
	fieldType: str,
	formatConfig: Optional[Dict[str, bool]] = None,
	extraDetail: bool = False,
	reason: Optional[OutputReason] = None,
) -> SpeechSequence:
	if attrs.get("isHidden"):
		return []
	if not formatConfig:
		formatConfig = config.conf["documentFormatting"]

	presCat = attrs.getPresentationCategory(
		ancestorAttrs,
		formatConfig,
		reason=reason,
		extraDetail=extraDetail,
	)
	childControlCount = int(attrs.get("_childcontrolcount", "0"))
	role = attrs.get("role", controlTypes.Role.UNKNOWN)
	if reason in [OutputReason.FOCUS, OutputReason.QUICKNAV] or attrs.get("alwaysReportName", False):
		name = attrs.get("name", "")
	else:
		name = ""
	states = attrs.get("states", set())
	keyboardShortcut = attrs.get("keyboardShortcut", "")
	isCurrent = attrs.get("current", controlTypes.IsCurrent.NO)
	hasDetails = attrs.get("hasDetails", False)
	detailsRoles: _AnnotationRolesT = attrs.get("detailsRoles", tuple())
	placeholderValue = attrs.get("placeholder", None)
	errorMessage = None
	if State.INVALID_ENTRY in states:
		errorMessage = attrs.get("errorMessage", None)
	value = attrs.get("value", "")

	description: Optional[str] = None
	_descriptionFrom = attrs.get("_description-from", controlTypes.DescriptionFrom.UNKNOWN)
	_descriptionIsContent: bool = attrs.get("descriptionIsContent", False)
	_reportDescriptionAsAnnotation: bool = (
		# Don't report other sources of description like "title" all the time
		# The usages of these is not consistent and often does not seem to have
		# Screen Reader users in mind
		config.conf["annotations"]["reportAriaDescription"]
		and not _descriptionIsContent
		and controlTypes.DescriptionFrom.ARIA_DESCRIPTION == _descriptionFrom
		and reason
		in (
			OutputReason.FOCUS,
			OutputReason.QUICKNAV,
			OutputReason.CARET,
			OutputReason.SAYALL,
		)
	)
	if (
		(
			config.conf["presentation"]["reportObjectDescriptions"]
			and not _descriptionIsContent
			and reason in [OutputReason.FOCUS, OutputReason.QUICKNAV]
		)
		or (
			# 'alwaysReportDescription' provides symmetry with 'alwaysReportName'.
			# Not used internally, but may be used by addons.
			attrs.get("alwaysReportDescription", False)
		)
		or _reportDescriptionAsAnnotation
	):
		description = attrs.get("description")

	level = attrs.get("level", None)

	if presCat != attrs.PRESCAT_LAYOUT:
		tableID = attrs.get("table-id")
	else:
		tableID = None

	roleText = attrs.get("roleText")
	landmark = attrs.get("landmark")
	if roleText:
		roleTextSequence = [roleText]
	elif role == controlTypes.Role.LANDMARK and landmark:
		roleTextSequence = [
			f"{aria.landmarkRoles[landmark]} {controlTypes.Role.LANDMARK.displayString}",
		]
	else:
		roleTextSequence = getPropertiesSpeech(reason=reason, role=role)
	stateTextSequence = getPropertiesSpeech(reason=reason, states=states, _role=role)
	keyboardShortcutSequence = []
	if config.conf["presentation"]["reportKeyboardShortcuts"]:
		keyboardShortcutSequence = getPropertiesSpeech(
			reason=reason,
			keyboardShortcut=keyboardShortcut,
		)
	isCurrentSequence = getPropertiesSpeech(reason=reason, current=isCurrent)
	hasDetailsSequence = getPropertiesSpeech(reason=reason, hasDetails=hasDetails, detailsRoles=detailsRoles)
	placeholderSequence = getPropertiesSpeech(reason=reason, placeholder=placeholderValue)
	errorMessageSequence = getPropertiesSpeech(reason=reason, errorMessage=errorMessage)
	nameSequence = getPropertiesSpeech(reason=reason, name=name)
	valueSequence = getPropertiesSpeech(reason=reason, value=value, _role=role)
	descriptionSequence = []
	if description is not None:
		descriptionSequence = getPropertiesSpeech(
			reason=reason,
			description=description,
		)
	levelSequence = getPropertiesSpeech(reason=reason, positionInfo_level=level)

	# Determine under what circumstances this node should be spoken.
	# speakEntry: Speak when the user enters the control.
	# speakWithinForLine: When moving by line, speak when the user is already within the control.
	# speakExitForLine: When moving by line, speak when the user exits the control.
	# speakExitForOther: When moving by word or character, speak when the user exits the control.
	speakEntry = speakWithinForLine = speakExitForLine = speakExitForOther = False
	if presCat == attrs.PRESCAT_SINGLELINE:
		speakEntry = True
		speakWithinForLine = True
		speakExitForOther = True
	elif presCat in (attrs.PRESCAT_MARKER, attrs.PRESCAT_CELL):
		speakEntry = True
	elif presCat == attrs.PRESCAT_CONTAINER:
		speakEntry = True
		speakExitForLine = bool(
			attrs.get("roleText") or role != controlTypes.Role.LANDMARK,
		)
		speakExitForOther = True

	# Determine the order of speech.
	# speakContentFirst: Speak the content before the control field info.
	speakContentFirst = _shouldSpeakContentFirst(reason, role, presCat, attrs, tableID, states)
	# speakStatesFirst: Speak the states before the role.
	speakStatesFirst = role == controlTypes.Role.LINK

	containerContainsText = ""  #: used for item counts for lists

	# Determine what text to speak.
	# Special cases
	if (
		childControlCount
		and fieldType == "start_addedToControlFieldStack"
		and role == controlTypes.Role.LIST
		and controlTypes.State.READONLY in states
	):
		# List.
		# #7652: containerContainsText variable is set here, but the actual generation of all other output is
		# handled further down in the general cases section.
		# This ensures that properties such as name, states and level etc still get reported appropriately.
		containerContainsText = (
			# Translators: Number of items in a list (example output: list with 5 items).
			ngettext("with %s item", "with %s items", childControlCount) % childControlCount
		)
	elif fieldType == "start_addedToControlFieldStack" and role == controlTypes.Role.TABLE and tableID:
		# Table.
		rowCount = attrs.get("table-rowcount-presentational") or attrs.get("table-rowcount")
		columnCount = attrs.get("table-columncount-presentational") or attrs.get("table-columncount")
		tableSeq = nameSequence[:]
		tableSeq.extend(roleTextSequence)
		tableSeq.extend(stateTextSequence)
		tableSeq.extend(
			getPropertiesSpeech(
				_tableID=tableID,
				rowCount=rowCount,
				columnCount=columnCount,
			),
		)
		tableSeq.extend(levelSequence)
		types.logBadSequenceTypes(tableSeq)
		return tableSeq
	elif (
		nameSequence
		and reason in [OutputReason.FOCUS, OutputReason.QUICKNAV]
		and fieldType == "start_addedToControlFieldStack"
		and role
		in (
			controlTypes.Role.GROUPING,
			controlTypes.Role.PROPERTYPAGE,
			controlTypes.Role.LANDMARK,
			controlTypes.Role.REGION,
		)
	):
		# #10095, #3321, #709: Report the name and description of groupings (such as fieldsets) and tab pages
		# #13307: report the label for landmarks and regions
		nameAndRole = nameSequence[:]
		if (
			role
			not in (
				controlTypes.Role.LANDMARK,
				controlTypes.Role.REGION,
			)
			or config.conf["documentFormatting"]["reportLandmarks"]
		):
			nameAndRole.extend(roleTextSequence)
		types.logBadSequenceTypes(nameAndRole)
		return nameAndRole
	elif (
		fieldType in ("start_addedToControlFieldStack", "start_relative")
		and role
		in (
			controlTypes.Role.TABLECELL,
			controlTypes.Role.TABLECOLUMNHEADER,
			controlTypes.Role.TABLEROWHEADER,
		)
		and tableID
	):
		# Table cell.
		reportTableHeaders = formatConfig["reportTableHeaders"]
		reportTableCellCoords = formatConfig["reportTableCellCoords"]
		getProps = {
			"rowNumber": (attrs.get("table-rownumber-presentational") or attrs.get("table-rownumber")),
			"columnNumber": (
				attrs.get("table-columnnumber-presentational") or attrs.get("table-columnnumber")
			),
			"rowSpan": attrs.get("table-rowsspanned"),
			"columnSpan": attrs.get("table-columnsspanned"),
			"includeTableCellCoords": reportTableCellCoords,
		}
		if reportTableHeaders in (ReportTableHeaders.ROWS_AND_COLUMNS, ReportTableHeaders.ROWS):
			getProps["rowHeaderText"] = attrs.get("table-rowheadertext")
		if reportTableHeaders in (ReportTableHeaders.ROWS_AND_COLUMNS, ReportTableHeaders.COLUMNS):
			getProps["columnHeaderText"] = attrs.get("table-columnheadertext")
		tableCellSequence = getPropertiesSpeech(_tableID=tableID, **getProps)
		tableCellSequence.extend(stateTextSequence)
		tableCellSequence.extend(isCurrentSequence)
		tableCellSequence.extend(hasDetailsSequence)
		types.logBadSequenceTypes(tableCellSequence)
		return tableCellSequence

	content = attrs.get("content")
	# General cases.
	if (
		speakEntry
		and (
			(speakContentFirst and fieldType in ("end_relative", "end_inControlFieldStack"))
			or (not speakContentFirst and fieldType in ("start_addedToControlFieldStack", "start_relative"))
		)
	) or (
		speakWithinForLine
		and not speakContentFirst
		and not extraDetail
		and fieldType == "start_inControlFieldStack"
	):
		out = []
		if content and speakContentFirst:
			out.append(content)
		if placeholderValue:
			if valueSequence:
				log.error(
					f"valueSequence exists when expected none: "
					f"valueSequence: {valueSequence!r} placeholderSequence: {placeholderSequence!r}",
				)
			valueSequence = placeholderSequence

		# Avoid speaking name twice. Which may happen if this controlfield is labelled by
		# one of it's internal fields. We determine this by checking for 'labelledByContent'.
		# An example of this situation is a checkbox element that has aria-labelledby pointing to a child
		# element.
		if (
			# Don't speak name when labelledByContent. It will be spoken by the subsequent controlFields instead.
			attrs.get("IAccessible2::attribute_explicit-name", False)
			and attrs.get("labelledByContent", False)
		):
			log.debug("Skipping name sequence: control field is labelled by content")
		else:
			out.extend(nameSequence)

		out.extend(stateTextSequence if speakStatesFirst else roleTextSequence)
		out.extend(roleTextSequence if speakStatesFirst else stateTextSequence)
		out.append(containerContainsText)
		out.extend(isCurrentSequence)
		out.extend(hasDetailsSequence)
		out.extend(valueSequence)
		out.extend(descriptionSequence)
		out.extend(levelSequence)
		out.extend(keyboardShortcutSequence)
		if content and not speakContentFirst:
			out.append(content)
		out.extend(errorMessageSequence)

		types.logBadSequenceTypes(out)
		return out
	elif (
		fieldType
		in (
			"end_removedFromControlFieldStack",
			"end_relative",
		)
		and roleTextSequence
		and ((not extraDetail and speakExitForLine) or (extraDetail and speakExitForOther))
	):
		if all(isinstance(item, str) for item in roleTextSequence):
			joinedRoleText = " ".join(roleTextSequence)
			out = [
				# Translators: Indicates end of something (example output: at the end of a list, speaks out of list).
				_("out of %s") % joinedRoleText,
			]
		else:
			out = roleTextSequence

		types.logBadSequenceTypes(out)
		return out

	# Special cases
	elif not speakEntry and fieldType in ("start_addedToControlFieldStack", "start_relative"):
		out = []
		if isCurrent != controlTypes.IsCurrent.NO:
			out.extend(isCurrentSequence)
		if hasDetails:
			out.extend(hasDetailsSequence)
		if descriptionSequence and _reportDescriptionAsAnnotation:
			out.extend(descriptionSequence)
		# Speak expanded / collapsed / level for treeview items (in ARIA treegrids)
		if role == controlTypes.Role.TREEVIEWITEM:
			if controlTypes.State.EXPANDED in states:
				out.extend(
					getPropertiesSpeech(reason=reason, states={controlTypes.State.EXPANDED}, _role=role),
				)
			elif controlTypes.State.COLLAPSED in states:
				out.extend(
					getPropertiesSpeech(reason=reason, states={controlTypes.State.COLLAPSED}, _role=role),
				)
			if levelSequence:
				out.extend(levelSequence)
		if role == controlTypes.Role.GRAPHIC and content:
			out.append(content)
		types.logBadSequenceTypes(out)
		return out
	else:
		return []
'''


#: NVDA 2026.2, source/speech/speech.py, getPropertiesSpeech, word for word.
NVDA_PROPERTIES_SPEECH = r'''
def getPropertiesSpeech(  # noqa: C901
	reason: OutputReason = OutputReason.QUERY,
	**propertyValues,
) -> SpeechSequence:
	textList: SpeechSequence = []
	name: Optional[str] = propertyValues.get("name")
	if name:
		textList.append(name)
	if "role" in propertyValues:
		role: controlTypes.Role = propertyValues["role"]
		speakRole = True
	elif "_role" in propertyValues:
		speakRole = False
		role: controlTypes.Role = propertyValues["_role"]
	else:
		speakRole = False
		role = controlTypes.Role.UNKNOWN
	role = controlTypes.Role(role)
	value: Optional[str] = (
		propertyValues.get("value") if role not in controlTypes.silentValuesForRoles else None
	)
	cellCoordsText: Optional[str] = propertyValues.get("cellCoordsText")
	rowNumber = propertyValues.get("rowNumber")
	columnNumber = propertyValues.get("columnNumber")
	includeTableCellCoords = propertyValues.get("includeTableCellCoords", True)

	if role == controlTypes.Role.CHARTELEMENT:
		speakRole = False
	roleText: Optional[str] = propertyValues.get("roleText")
	if (
		speakRole
		and (
			roleText
			or reason
			not in (
				OutputReason.SAYALL,
				OutputReason.CARET,
				OutputReason.FOCUS,
				OutputReason.QUICKNAV,
			)
			or not (name or value or cellCoordsText or rowNumber or columnNumber)
			or role not in controlTypes.silentRolesOnFocus
		)
		and (
			role != controlTypes.Role.MATH
			or reason
			not in (
				OutputReason.CARET,
				OutputReason.SAYALL,
			)
		)
	):
		textList.append(roleText if roleText else role.displayString)
	if value:
		textList.append(value)
	states = propertyValues.get("states")
	realStates = propertyValues.get("_states", states)
	negativeStates = propertyValues.get("negativeStates", set())
	# If the caller didn't want states, states will be None.
	# However, empty states means the caller still wants states, but the object
	# had no states; e.g. an unchecked check box with no other states.
	if states is not None or negativeStates:
		if states is None:
			# processAndLabelStates won't accept None for states.
			states = set()
		labelStates = controlTypes.processAndLabelStates(role, realStates, reason, states, negativeStates)
		textList.extend(labelStates)
	# sometimes description key is present but value is None
	description: Optional[str] = propertyValues.get("description")
	if description:
		textList.append(description)
	# sometimes keyboardShortcut key is present but value is None
	keyboardShortcut: Optional[str] = propertyValues.get("keyboardShortcut")
	textList.extend(getKeyboardShortcutsSpeech(keyboardShortcut))
	if includeTableCellCoords and cellCoordsText:
		textList.append(cellCoordsText)
	if cellCoordsText or rowNumber or columnNumber:
		tableID = propertyValues.get("_tableID")
		# Always treat the table as different if there is no tableID.
		sameTable = tableID and tableID == _speechState.oldTableID
		# Don't update the oldTableID if no tableID was given.
		if tableID and not sameTable:
			_speechState.oldTableID = tableID
		# When fetching row and column span
		# default the values to 1 to make further checks a lot simpler.
		# After all, a table cell that has no rowspan implemented is assumed to span one row.
		rowSpan = propertyValues.get("rowSpan") or 1
		columnSpan = propertyValues.get("columnSpan") or 1
		if rowNumber and (
			not sameTable or rowNumber != _speechState.oldRowNumber or rowSpan != _speechState.oldRowSpan
		):
			rowHeaderText: Optional[str] = propertyValues.get("rowHeaderText")
			if rowHeaderText:
				textList.append(rowHeaderText)
			if includeTableCellCoords and not cellCoordsText:
				# Translators: Speaks current row number (example output: row 3).
				rowNumberTranslation: str = _("row %s") % rowNumber
				textList.append(rowNumberTranslation)
				if rowSpan > 1 and columnSpan <= 1:
					# Translators: Speaks the row span added to the current row number (example output: through 5).
					rowSpanAddedTranslation: str = _("through {endRow}").format(
						endRow=rowNumber + rowSpan - 1,
					)
					textList.append(rowSpanAddedTranslation)
			_speechState.oldRowNumber = rowNumber
			_speechState.oldRowSpan = rowSpan
		if columnNumber and (
			not sameTable
			or columnNumber != _speechState.oldColumnNumber
			or columnSpan != _speechState.oldColumnSpan
		):
			columnHeaderText: Optional[str] = propertyValues.get("columnHeaderText")
			if columnHeaderText:
				textList.append(columnHeaderText)
			if includeTableCellCoords and not cellCoordsText:
				# Translators: Speaks current column number (example output: column 3).
				colNumberTranslation: str = _("column %s") % columnNumber
				textList.append(colNumberTranslation)
				if columnSpan > 1 and rowSpan <= 1:
					# Translators: Speaks the column span added to the current column number (example output: through 5).
					colSpanAddedTranslation: str = _("through {endCol}").format(
						endCol=columnNumber + columnSpan - 1,
					)
					textList.append(colSpanAddedTranslation)
			_speechState.oldColumnNumber = columnNumber
			_speechState.oldColumnSpan = columnSpan
		if includeTableCellCoords and not cellCoordsText and rowSpan > 1 and columnSpan > 1:
			# Translators: Speaks the row and column span added to the current row and column numbers
			# (example output: through row 5 column 3).
			rowColSpanTranslation: str = _("through row {row} column {column}").format(
				row=rowNumber + rowSpan - 1,
				column=columnNumber + columnSpan - 1,
			)
			textList.append(rowColSpanTranslation)
	rowCount = propertyValues.get("rowCount", 0)
	columnCount = propertyValues.get("columnCount", 0)
	rowAndColumnCountText = _rowAndColumnCountText(rowCount, columnCount)
	if rowAndColumnCountText:
		textList.append(rowAndColumnCountText)
	if rowCount or columnCount:
		# The caller is entering a table, so ensure that it is treated as a new table, even if the previous table was the same.
		_speechState.oldTableID = None

	# speak isCurrent property EG aria-current
	isCurrent = propertyValues.get("current", controlTypes.IsCurrent.NO)
	if isCurrent != controlTypes.IsCurrent.NO:
		textList.append(isCurrent.displayString)

	# are there further details
	hasDetails = propertyValues.get("hasDetails", False)
	if hasDetails:
		detailsRoles: _AnnotationRolesT = propertyValues.get("detailsRoles", tuple())
		if detailsRoles:
			roleStrings = (role.displayString if role else _("details") for role in detailsRoles)
			for roleString in roleStrings:
				textList.append(
					# Translators: Speaks when there are further details/annotations that can be fetched manually.
					# %s specifies the type of details (e.g. "comment, suggestion, details")
					_("has %s") % roleString,
				)
		else:
			textList.append(
				# Translators: Speaks when there are further details/annotations that can be fetched manually.
				_("has details"),
			)

	placeholder: Optional[str] = propertyValues.get("placeholder", None)
	if placeholder:
		textList.append(placeholder)
	indexInGroup = propertyValues.get("positionInfo_indexInGroup", 0)
	similarItemsInGroup = propertyValues.get("positionInfo_similarItemsInGroup", 0)
	if 0 < indexInGroup <= similarItemsInGroup:
		# Translators: Spoken to indicate the position of an item in a group of items (such as a list).
		# {number} is replaced with the number of the item in the group.
		# {total} is replaced with the total number of items in the group.
		itemPosTranslation: str = _("{number} of {total}").format(
			number=indexInGroup,
			total=similarItemsInGroup,
		)
		textList.append(itemPosTranslation)
	if "positionInfo_level" in propertyValues:
		level = propertyValues.get("positionInfo_level", None)
		role = propertyValues.get("role", None)
		if level is not None:
			# Translators: Speaks the item level in treeviews (example output: level 2).
			levelTranslation: str = _("level %s") % level
			if (
				role in (controlTypes.Role.TREEVIEWITEM, controlTypes.Role.LISTITEM)
				and level != _speechState.oldTreeLevel
			):
				textList.insert(0, levelTranslation)
				_speechState.oldTreeLevel = level
			else:
				textList.append(levelTranslation)

	errorMessage: str | None = propertyValues.get("errorMessage", None)
	if errorMessage:
		textList.append(errorMessage)
	types.logBadSequenceTypes(textList)
	return textList
'''


#: NVDA 2026.2, source/speech/speech.py, _rowAndColumnCountText, word for word.
NVDA_ROW_AND_COLUMN_COUNT = r'''
def _rowAndColumnCountText(rowCount: int, columnCount: int) -> Optional[str]:
	if rowCount and columnCount:
		rowCountTranslation: str = _rowCountText(rowCount)
		colCountTranslation: str = _columnCountText(columnCount)
		# Translators: Main part of the compound string to speak number of columns and rows in a table
		# Example: If the reported compound string is "with 3 rows and 2 columns", {rowCountTranslation} will be
		# replaced by "3 rows" and {colCountTranslation} by "2 columns"
		return _("with {rowCountTranslation} and {colCountTranslation}").format(
			rowCountTranslation=rowCountTranslation,
			colCountTranslation=colCountTranslation,
		)
	elif columnCount and not rowCount:
		# Translators: Speaks number of columns (example output: with 4 columns).
		return ngettext("with %s column", "with %s columns", columnCount) % columnCount
	elif rowCount and not columnCount:
		# Translators: Speaks number of rows (example output: with 2 rows).
		return ngettext("with %s row", "with %s rows", rowCount) % rowCount
	return None
'''


#: NVDA 2026.2, source/controlTypes/processAndLabelStates.py, _processPositiveStates, word for word.
NVDA_POSITIVE_STATES = r'''
def _processPositiveStates(
	role: Role,
	states: set[State],
	reason: OutputReason,
	positiveStates: set[State] | None = None,
) -> set[State]:
	"""Processes the states for an object and returns the positive states to output for a specified reason.
	For example, if C{State.CHECKED} is in the returned states, it means that the processed object is checked.
	:param role: The role of the object to process states for (e.g. C{Role.CHECKBOX}).
	:param states: The raw states for an object to process.
	:param reason: The reason to process the states (e.g. C{OutputReason.FOCUS}).
	:param positiveStates: Used for C{OutputReason.CHANGE}, specifies states changed from negative to
	positive.
	:return: The processed positive states.
	"""
	positiveStates = positiveStates.copy() if positiveStates is not None else states.copy()
	# The user never cares about certain states.
	if role == Role.EDITABLETEXT:
		positiveStates.discard(State.EDITABLE)
	if role != Role.LINK:
		positiveStates.discard(State.VISITED)
		positiveStates.discard(State.INTERNAL_LINK)
	positiveStates.discard(State.SELECTABLE)
	if not config.conf["presentation"]["reportMultiSelect"] or role in (
		Role.LISTITEM,
		Role.TREEVIEWITEM,
		Role.MENUITEM,
		Role.TABLEROW,
		Role.TABLECELL,
		Role.CHECKBOX,
	):
		positiveStates.discard(State.MULTISELECTABLE)
	positiveStates.discard(State.FOCUSABLE)
	positiveStates.discard(State.CHECKABLE)
	if State.DRAGGING in positiveStates:
		# It's obvious that the control is draggable if it's being dragged.
		positiveStates.discard(State.DRAGGABLE)
	if role == Role.COMBOBOX:
		# Combo boxes inherently have a popup, so don't report it.
		positiveStates.discard(State.HASPOPUP)
	if not config.conf["documentFormatting"]["reportClickable"] or role in clickableRoles:
		# This control is clearly clickable according to its role,
		# or reporting clickable just isn't useful,
		# or the user has explicitly requested no reporting clickable
		positiveStates.discard(State.CLICKABLE)
	if not config.conf["documentFormatting"]["reportLinkType"]:
		for state in STATES_LINK_TYPE:
			positiveStates.discard(state)
	if reason == OutputReason.QUERY:
		return positiveStates
	positiveStates.discard(State.DEFUNCT)
	positiveStates.discard(State.MODAL)
	positiveStates.discard(State.FOCUSED)
	positiveStates.discard(State.OFFSCREEN)
	positiveStates.discard(State.INVISIBLE)
	positiveStates.discard(State.INDETERMINATE)
	if reason != OutputReason.CHANGE:
		positiveStates.discard(State.LINKED)
		if (
			role
			in (
				Role.LISTITEM,
				Role.TREEVIEWITEM,
				Role.MENUITEM,
				Role.TABLEROW,
				Role.CHECKBOX,
			)
			and State.SELECTABLE in states
		):
			positiveStates.discard(State.SELECTED)
	if role not in (Role.EDITABLETEXT, Role.CHECKBOX):
		positiveStates.discard(State.READONLY)
	if role == Role.CHECKBOX:
		positiveStates.discard(State.PRESSED)
	if role == Role.MENUITEM and State.HASPOPUP in positiveStates:
		# The user doesn't usually care if a submenu is expanded or collapsed.
		positiveStates.discard(State.COLLAPSED)
		positiveStates.discard(State.EXPANDED)
	if State.FOCUSABLE not in states:
		positiveStates.discard(State.EDITABLE)
	return positiveStates
'''


#: NVDA 2026.2, source/controlTypes/processAndLabelStates.py, _processNegativeStates, word for word.
NVDA_NEGATIVE_STATES = r'''
def _processNegativeStates(
	role: Role,
	states: Set[State],
	reason: OutputReason,
	negativeStates: Optional[Set[State]] = None,
) -> Set[State]:
	"""Processes the states for an object and returns the negative states to output for a specified reason.
	For example, if C{State.CHECKED} is in the returned states, it means that the processed object is not
	checked.
	@param role: The role of the object to process states for (e.g. C{Role.CHECKBOX}).
	@param states: The raw states for an object to process.
	@param reason: The reason to process the states (e.g. C{OutputReason.FOCUS)}.
	@param negativeStates: Used for C{OutputReason.CHANGE}, specifies states changed from positive to
	negative.
	@return: The processed negative states.
	"""
	if reason == OutputReason.CHANGE and not isinstance(negativeStates, set):
		raise TypeError("negativeStates must be a set for this reason")
	speakNegatives = set()
	# Add the negative selected state if the control is selectable,
	# but only if it is reported for the reason of focus, or this is a change to the focused object.
	# The condition stops "not selected" from being spoken in some broken controls
	# when the state change for the previous focus is issued before the focus change.
	if (
		# Only include if the object is actually selectable
		State.SELECTABLE in states
		# Only include if the object is focusable (E.g. ARIA grid cells, but not standard html tables)
		and State.FOCUSABLE in states
		# Only include  if reporting the focus or when states are changing on the focus.
		# This is to avoid exposing it for things like caret movement in browse mode.
		and (reason == OutputReason.FOCUS or (reason == OutputReason.CHANGE and State.FOCUSED in states))
		and role
		in (
			Role.LISTITEM,
			Role.TREEVIEWITEM,
			Role.TABLEROW,
			Role.TABLECELL,
			Role.TABLECOLUMNHEADER,
			Role.TABLEROWHEADER,
			Role.CHECKBOX,
		)
	):
		speakNegatives.add(State.SELECTED)
	# Restrict "not checked" in a similar way to "not selected".
	if (
		(role in (Role.CHECKBOX, Role.RADIOBUTTON, Role.CHECKMENUITEM) or State.CHECKABLE in states)
		and (State.HALFCHECKED not in states)
		and (reason != OutputReason.CHANGE or State.FOCUSED in states)
	):
		speakNegatives.add(State.CHECKED)
	if role == Role.TOGGLEBUTTON and State.HALF_PRESSED not in states:
		speakNegatives.add(State.PRESSED)
	if role is Role.SWITCH and State.ON not in states:
		speakNegatives.add(State.ON)
	if reason == OutputReason.CHANGE:
		# We want to speak this state only if it is changing to negative.
		speakNegatives.add(State.DROPTARGET)
		# We were given states which have changed to negative.
		# Return only those supplied negative states which should be spoken;
		# i.e. the states in both sets.
		speakNegatives &= negativeStates
		# #6946: if HALFCHECKED is present but CHECKED isn't, we should make sure we add CHECKED to speakNegatives.
		if State.HALFCHECKED in negativeStates and State.CHECKED not in states:
			speakNegatives.add(State.CHECKED)
		if State.HALF_PRESSED in negativeStates and State.PRESSED not in states:
			speakNegatives.add(State.PRESSED)

		if STATES_SORTED & negativeStates and not STATES_SORTED & states:
			# If the object has just stopped being sorted, just report not sorted.
			# The user doesn't care how it was sorted before.
			speakNegatives.add(State.SORTED)
		return speakNegatives
	else:
		# This is not a state change; only positive states were supplied.
		# Return all negative states which should be spoken, excluding the positive states.
		return speakNegatives - states
'''


#: NVDA 2026.2, source/controlTypes/processAndLabelStates.py, processAndLabelStates, word for word.
NVDA_LABEL_STATES = r'''
def processAndLabelStates(
	role: Role,
	states: Set[State],
	reason: OutputReason,
	positiveStates: Optional[Set[State]] = None,
	negativeStates: Optional[Set[State]] = None,
	positiveStateLabelDict: Dict[State, str] = {},
	negativeStateLabelDict: Dict[State, str] = {},
) -> List[str]:
	"""Processes the states for an object and returns the appropriate state labels for both positive and
	negative states.
	@param role: The role of the object to process states for (e.g. C{Role.CHECKBOX}).
	@param states: The raw states for an object to process.
	@param reason: The reason to process the states (e.g. C{OutputReason.FOCUS}).
	@param positiveStates: Used for C{OutputReason.CHANGE}, specifies states changed from negative to
	positive.
	@param negativeStates: Used for C{OutputReason.CHANGE}, specifies states changed from positive to
	negative.
	@param positiveStateLabelDict: Dictionary containing state identifiers as keys and associated positive
	labels as their values.
	@param negativeStateLabelDict: Dictionary containing state identifiers as keys and associated negative
	labels as their values.
	@return: The labels of the relevant positive and negative states.
	"""
	mergedStateLabels = []
	positiveStates = _processPositiveStates(role, states, reason, positiveStates)
	negativeStates = _processNegativeStates(role, states, reason, negativeStates)
	for state in sorted(positiveStates | negativeStates):
		if state in positiveStates:
			mergedStateLabels.append(positiveStateLabelDict.get(state, state.displayString))
		elif state in negativeStates:
			mergedStateLabels.append(negativeStateLabelDict.get(state, state.negativeDisplayString))
	return mergedStateLabels
'''


#: NVDA 2026.2, source/utils/urlUtils.py, getLinkType, word for word.
NVDA_GET_LINK_TYPE = r'''
def getLinkType(targetURL: str, rootURL: str) -> controlTypes.State | None:
	"""Returns the link type corresponding to a given URL.

	:param targetURL: The URL of the link destination
	:param rootURL: The root URL of the page
	:return: A controlTypes.State corresponding to the link type, or C{None} if the state cannot be determined
	"""
	if not targetURL or not rootURL:
		log.debug(f"getLinkType: Either targetUrl {targetURL} or rootUrl {rootURL} is empty.")
		return None
	if isSamePageURL(targetURL, rootURL):
		log.debug(f"getLinkType: {targetURL} is an internal link.")
		return controlTypes.State.INTERNAL_LINK
	log.debug(f"getLinkType: {targetURL} type is unknown.")
	return None
'''


#: NVDA 2026.2, source/utils/urlUtils.py, isSamePageURL, word for word.
NVDA_SAME_PAGE_URL = r'''
def isSamePageURL(targetURLOnPage: str, rootURL: str) -> bool:
	"""Returns whether a given URL belongs to the same page as another URL.

	:param targetURLOnPage: The URL that should be on the same page as `rootURL`
	:param rootURL: The root URL of the page
	:return: Whether `targetURLOnPage` belongs to the same page as `rootURL`
	"""
	if not targetURLOnPage or not rootURL:
		return False

	validSchemes = ("http", "https", "file")
	# Parse the URLs
	try:
		parsedTargetURLOnPage: ParseResult = urlparse(targetURLOnPage)
	except ValueError:
		log.debugWarning(f"Invalid target URL: {targetURLOnPage}", exc_info=True)
		return False
	if parsedTargetURLOnPage.scheme not in validSchemes:
		return False
	try:
		parsedRootURL: ParseResult = urlparse(rootURL)
	except ValueError:
		log.debugWarning(f"Invalid root URL: {rootURL}", exc_info=True)
		return False
	if parsedRootURL.scheme not in validSchemes:
		return False

	# Reconstruct URLs without schemes and without fragments for comparison
	targetURLOnPageWithoutFragments = urlunparse(parsedTargetURLOnPage._replace(scheme="", fragment=""))
	rootURLWithoutFragments = urlunparse(parsedRootURL._replace(scheme="", fragment=""))

	fragmentInvalidChars: str = "/"  # Characters not considered valid in fragments
	return targetURLOnPageWithoutFragments == rootURLWithoutFragments and not any(
		char in parsedTargetURLOnPage.fragment for char in fragmentInvalidChars
	)
'''


#: NVDA 2026.2, source/browseMode.py, BrowseModeTreeInterceptor.getLinkTypeInDocument, word for word.
NVDA_LINK_TYPE_IN_DOCUMENT = r'''
def getLinkTypeInDocument(self, url: str) -> controlTypes.State | None:
	"""Returns the type of a link in the document, or C{None} if the link type cannot be determined."""
	return urlUtils.getLinkType(url, self.documentURL)
'''


#: NVDA 2026.2, source/browseMode.py, TextInfoQuickNavItem.report, word for word.
NVDA_QUICK_NAV_REPORT = r'''
def report(self, readUnit=None):
	info = self.textInfo
	# If we are dealing with a form field, ensure we don't read the whole content if it's an editable text.
	if self.itemType == "formField":
		if self.obj.role == controlTypes.Role.EDITABLETEXT:
			readUnit = textInfos.UNIT_LINE
	if readUnit:
		fieldInfo = info.copy()
		info.collapse()
		info.move(readUnit, 1, endPoint="end")
		if info.compareEndPoints(fieldInfo, "endToEnd") > 0:
			# We've expanded past the end of the field, so limit to the end of the field.
			info.setEndPoint(fieldInfo, "endToEnd")
	speech.speakTextInfo(info, reason=self.outputReason)
'''


#: NVDA 2026.2, source/virtualBuffers/gecko_ia2.py, the link part of GeckoVBufTextInfo._normalizeControlField, word for word.
NVDA_GECKO_LINK = r'''
if role == controlTypes.Role.LINK:
	if controlTypes.State.LINKED not in states:
		# This is a named link destination, not a link which can be activated. The user doesn't care about these.
		role = controlTypes.Role.TEXTFRAME
	elif (value := attrs.get("IAccessible::value")) is not None and (
		linkType := self.obj.getLinkTypeInDocument(value)
	) is not None:
		states.add(linkType)
'''


#: NVDA 2026.2, source/controlTypes/role.py: each Role, its value and its label (_roleLabels).
NVDA_ROLES = {
	'UNKNOWN': (0, 'unknown'),
	'WINDOW': (1, 'window'),
	'TITLEBAR': (2, 'title bar'),
	'PANE': (3, 'pane'),
	'DIALOG': (4, 'dialog'),
	'CHECKBOX': (5, 'check box'),
	'RADIOBUTTON': (6, 'radio button'),
	'STATICTEXT': (7, 'text'),
	'EDITABLETEXT': (8, 'edit'),
	'BUTTON': (9, 'button'),
	'MENUBAR': (10, 'menu bar'),
	'MENUITEM': (11, 'menu item'),
	'POPUPMENU': (12, 'menu'),
	'COMBOBOX': (13, 'combo box'),
	'LIST': (14, 'list'),
	'LISTITEM': (15, 'list item'),
	'GRAPHIC': (16, 'graphic'),
	'HELPBALLOON': (17, 'help balloon'),
	'TOOLTIP': (18, 'tool tip'),
	'LINK': (19, 'link'),
	'TREEVIEW': (20, 'tree view'),
	'TREEVIEWITEM': (21, 'tree view item'),
	'TAB': (22, 'tab'),
	'TABCONTROL': (23, 'tab control'),
	'SLIDER': (24, 'slider'),
	'PROGRESSBAR': (25, 'progress bar'),
	'SCROLLBAR': (26, 'scroll bar'),
	'STATUSBAR': (27, 'status bar'),
	'TABLE': (28, 'table'),
	'TABLECELL': (29, 'cell'),
	'TABLECOLUMN': (30, 'column'),
	'TABLEROW': (31, 'row'),
	'TABLECOLUMNHEADER': (32, 'column header'),
	'TABLEROWHEADER': (33, 'row header'),
	'FRAME': (34, 'frame'),
	'TOOLBAR': (35, 'tool bar'),
	'DROPDOWNBUTTON': (36, 'drop down button'),
	'CLOCK': (37, 'clock'),
	'SEPARATOR': (38, 'separator'),
	'FORM': (39, 'form'),
	'HEADING': (40, 'heading'),
	'HEADING1': (41, 'heading 1'),
	'HEADING2': (42, 'heading 2'),
	'HEADING3': (43, 'heading 3'),
	'HEADING4': (44, 'heading 4'),
	'HEADING5': (45, 'heading 5'),
	'HEADING6': (46, 'heading 6'),
	'PARAGRAPH': (47, 'paragraph'),
	'BLOCKQUOTE': (48, 'block quote'),
	'TABLEHEADER': (49, 'table header'),
	'TABLEBODY': (50, 'table body'),
	'TABLEFOOTER': (51, 'table footer'),
	'DOCUMENT': (52, 'document'),
	'ANIMATION': (53, 'animation'),
	'APPLICATION': (54, 'application'),
	'BOX': (55, 'box'),
	'GROUPING': (56, 'grouping'),
	'PROPERTYPAGE': (57, 'property page'),
	'CANVAS': (58, 'canvas'),
	'CAPTION': (59, 'caption'),
	'CHECKMENUITEM': (60, 'check menu item'),
	'DATEEDITOR': (61, 'date edit'),
	'ICON': (62, 'icon'),
	'DIRECTORYPANE': (63, 'directory pane'),
	'EMBEDDEDOBJECT': (64, 'embedded object'),
	'ENDNOTE': (65, 'end note'),
	'FOOTER': (66, 'footer'),
	'FOOTNOTE': (67, 'foot note'),
	'GLASSPANE': (69, 'glass pane'),
	'HEADER': (70, 'header'),
	'IMAGEMAP': (71, 'image map'),
	'INPUTWINDOW': (72, 'input window'),
	'LABEL': (73, 'label'),
	'NOTE': (74, 'note'),
	'PAGE': (75, 'page'),
	'RADIOMENUITEM': (76, 'radio menu item'),
	'LAYEREDPANE': (77, 'layered pane'),
	'REDUNDANTOBJECT': (78, 'redundant object'),
	'ROOTPANE': (79, 'root pane'),
	'EDITBAR': (80, 'edit bar'),
	'TERMINAL': (82, 'terminal'),
	'RICHEDIT': (83, 'rich edit'),
	'RULER': (84, 'ruler'),
	'SCROLLPANE': (85, 'scroll pane'),
	'SECTION': (86, 'section'),
	'SHAPE': (87, 'shape'),
	'SPLITPANE': (88, 'split pane'),
	'VIEWPORT': (89, 'view port'),
	'TEAROFFMENU': (90, 'tear off menu'),
	'TEXTFRAME': (91, 'text frame'),
	'TOGGLEBUTTON': (92, 'toggle button'),
	'BORDER': (93, 'border'),
	'CARET': (94, 'caret'),
	'CHARACTER': (95, 'character'),
	'CHART': (96, 'chart'),
	'CURSOR': (97, 'cursor'),
	'DIAGRAM': (98, 'diagram'),
	'DIAL': (99, 'dial'),
	'DROPLIST': (100, 'drop list'),
	'SPLITBUTTON': (101, 'split button'),
	'MENUBUTTON': (102, 'menu button'),
	'DROPDOWNBUTTONGRID': (103, 'drop down button grid'),
	'MATH': (104, 'math'),
	'GRIP': (105, 'grip'),
	'HOTKEYFIELD': (106, 'hot key field'),
	'INDICATOR': (107, 'indicator'),
	'SPINBUTTON': (108, 'spin button'),
	'SOUND': (109, 'sound'),
	'WHITESPACE': (110, 'white space'),
	'TREEVIEWBUTTON': (111, 'tree view button'),
	'IPADDRESS': (112, 'IP address'),
	'DESKTOPICON': (113, 'desktop icon'),
	'INTERNALFRAME': (115, 'frame'),
	'DESKTOPPANE': (116, 'desktop pane'),
	'OPTIONPANE': (117, 'option pane'),
	'COLORCHOOSER': (118, 'color chooser'),
	'FILECHOOSER': (119, 'file chooser'),
	'FILLER': (120, 'filler'),
	'MENU': (121, 'menu'),
	'PANEL': (122, 'panel'),
	'PASSWORDEDIT': (123, 'password edit'),
	'FONTCHOOSER': (124, 'font chooser'),
	'LINE': (125, 'line'),
	'FONTNAME': (126, 'font name'),
	'FONTSIZE': (127, 'font size'),
	'BOLD': (128, 'bold'),
	'ITALIC': (129, 'italic'),
	'UNDERLINE': (130, 'underline'),
	'FGCOLOR': (131, 'foreground color'),
	'BGCOLOR': (132, 'background color'),
	'SUPERSCRIPT': (133, 'superscript'),
	'SUBSCRIPT': (134, 'subscript'),
	'STYLE': (135, 'style'),
	'INDENT': (136, 'indent'),
	'ALIGNMENT': (137, 'alignment'),
	'ALERT': (138, 'alert'),
	'DATAGRID': (139, 'data grid'),
	'DATAITEM': (140, 'data item'),
	'HEADERITEM': (141, 'header item'),
	'THUMB': (142, 'thumb control'),
	'CALENDAR': (143, 'calendar'),
	'VIDEO': (144, 'video'),
	'AUDIO': (145, 'audio'),
	'CHARTELEMENT': (146, 'chart element'),
	'DELETED_CONTENT': (147, 'deleted'),
	'INSERTED_CONTENT': (148, 'inserted'),
	'LANDMARK': (149, 'landmark'),
	'ARTICLE': (150, 'article'),
	'REGION': (151, 'region'),
	'FIGURE': (152, 'figure'),
	'MARKED_CONTENT': (153, 'highlighted'),
	'BUSY_INDICATOR': (154, 'busy indicator'),
	'COMMENT': (155, 'comment'),
	'SUGGESTION': (156, 'suggestion'),
	'DEFINITION': (157, 'definition'),
	'SWITCH': (158, 'switch'),
}


#: NVDA 2026.2, source/controlTypes/state.py: each State, its value (setBit) and its labels (_stateLabels,
#: _negativeStateLabels).
NVDA_STATES = {
	'UNAVAILABLE': (1, 'unavailable', None),
	'FOCUSED': (2, 'focused', None),
	'SELECTED': (4, 'selected', 'not selected'),
	'BUSY': (8, 'busy', None),
	'PRESSED': (16, 'pressed', 'not pressed'),
	'CHECKED': (32, 'checked', 'not checked'),
	'HALFCHECKED': (64, 'half checked', None),
	'READONLY': (128, 'read only', None),
	'EXPANDED': (256, 'expanded', None),
	'COLLAPSED': (512, 'collapsed', None),
	'INVISIBLE': (1024, 'invisible', None),
	'VISITED': (2048, 'visited', None),
	'LINKED': (4096, 'linked', None),
	'HASPOPUP': (8192, 'subMenu', None),
	'PROTECTED': (16384, 'protected', None),
	'REQUIRED': (32768, 'required', None),
	'DEFUNCT': (65536, 'defunct', None),
	'INVALID_ENTRY': (131072, 'invalid entry', None),
	'MODAL': (262144, 'modal', None),
	'AUTOCOMPLETE': (524288, 'has auto complete', None),
	'MULTILINE': (1048576, 'multi line', None),
	'ICONIFIED': (2097152, 'iconified', None),
	'OFFSCREEN': (4194304, 'off screen', None),
	'SELECTABLE': (8388608, 'selectable', None),
	'FOCUSABLE': (16777216, 'focusable', None),
	'CLICKABLE': (33554432, 'clickable', None),
	'EDITABLE': (67108864, 'editable', None),
	'CHECKABLE': (134217728, 'checkable', None),
	'DRAGGABLE': (268435456, 'draggable', None),
	'DRAGGING': (536870912, 'dragging', None),
	'DROPTARGET': (1073741824, 'drop target', 'done dragging'),
	'SORTED': (2147483648, 'sorted', None),
	'SORTED_ASCENDING': (4294967296, 'sorted ascending', None),
	'SORTED_DESCENDING': (8589934592, 'sorted descending', None),
	'HASLONGDESC': (17179869184, 'has long description', None),
	'PINNED': (34359738368, 'pinned', None),
	'HASFORMULA': (68719476736, 'has formula', None),
	'HASCOMMENT': (137438953472, 'has comment', None),
	'OBSCURED': (274877906944, 'obscured', None),
	'CROPPED': (549755813888, 'cropped', None),
	'OVERFLOWING': (1099511627776, 'overflowing', None),
	'UNLOCKED': (2199023255552, 'unlocked', None),
	'HAS_ARIA_DETAILS': (4398046511104, None, None),
	'HASNOTE': (8796093022208, 'has note', None),
	'INDETERMINATE': (17592186044416, None, None),
	'HALF_PRESSED': (35184372088832, 'half pressed', None),
	'ON': (70368744177664, 'on', 'off'),
	'HASPOPUP_DIALOG': (140737488355328, 'opens dialog', None),
	'HASPOPUP_GRID': (281474976710656, 'opens grid', None),
	'HASPOPUP_LIST': (562949953421312, 'opens list', None),
	'HASPOPUP_TREE': (1125899906842624, 'opens tree', None),
	'INTERNAL_LINK': (2251799813685248, 'same page', None),
	'MULTISELECTABLE': (4503599627370496, 'multi-select', None),
}


#: NVDA 2026.2, source/config/configSpec.py: the defaults of the settings these functions read.
NVDA_DEFAULTS = {
	'speech': {
		'autoLanguageSwitching': True,
		'reportLanguage': False,
	},
	'presentation': {
		'reportKeyboardShortcuts': True,
		'reportObjectPositionInformation': True,
		'guessObjectPositionInformationWhenUnavailable': False,
		'reportMultiSelect': False,
		'reportTooltips': False,
		'reportHelpBalloons': True,
		'reportObjectDescriptions': True,
		'reportDynamicContentChanges': True,
		'reportAutoSuggestionsWithSound': True,
	},
	'documentFormatting': {
		'detectFormatAfterCursor': False,
		'reportFontName': False,
		'reportFontSize': False,
		'fontAttributeReporting': 0,
		'reportRevisions': True,
		'reportEmphasis': False,
		'reportHighlight': True,
		'reportSuperscriptsAndSubscripts': False,
		'reportColor': False,
		'reportTransparentColor': False,
		'reportAlignment': False,
		'reportLineSpacing': False,
		'reportStyle': False,
		'reportSpellingErrors2': 1,
		'reportPage': True,
		'reportLineNumber': False,
		'reportLineIndentation': 0,
		'ignoreBlankLinesForRLI': False,
		'indentToneDuration': 40,
		'reportParagraphIndentation': False,
		'reportTables': True,
		'includeLayoutTables': False,
		'reportTableHeaders': 1,
		'reportTableCellCoords': True,
		'reportCellBorders': 0,
		'reportLinks': True,
		'reportLinkType': True,
		'reportGraphics': True,
		'reportComments': True,
		'reportBookmarks': True,
		'reportLists': True,
		'reportHeadings': True,
		'reportBlockQuotes': True,
		'reportGroupings': True,
		'reportLandmarks': True,
		'reportArticles': False,
		'reportFrames': True,
		'reportFigures': True,
		'reportClickable': True,
	},
	'annotations': {
		'reportDetails': True,
		'reportAriaDescription': True,
	},
}


# -- the imitation NVDA --------------------------------------------------------------------------------------------

nvdaLog = nvdaStubs.logging.getLogger("nvda")


def nvdaCode(source, name, namespace):
	"""Compile NVDA's own ``source`` in ``namespace``, the imitation NVDA, and give back ``name`` from it. Annotations
	aren't evaluated, as they needn't be to run NVDA's code."""
	code = compile(source, f"<NVDA 2026.2: {name}>", "exec", flags=__future__.annotations.compiler_flag, dont_inherit=True)
	exec(code, namespace)
	return namespace[name]


def nvdaMethods(className, bases, sources, namespace):
	"""A class made of NVDA's own methods: their sources go in the class's body, so that super() works in them."""
	body = "".join(textwrap.indent(source, "\t") for source in sources)
	namespace = dict(namespace, **{base.__name__: base for base in bases})
	return nvdaCode(f"class {className}({', '.join(base.__name__ for base in bases)}):\n{body}", className, namespace)


def displayEnum(name, table, negative=False):
	"""NVDA's Role or State: each member with its value and its label (``displayString``), as NVDA 2026.2 has them."""
	members = enum.IntEnum(name, {member: row[0] for member, row in table.items()})
	members.displayString = property(lambda self: table[self.name][1])
	if negative:
		# NVDA's State.negativeDisplayString: its own label, or "not" and the positive one.
		members.negativeDisplayString = property(lambda self: table[self.name][2] or f"not {table[self.name][1]}")
	return members


Role = displayEnum("Role", NVDA_ROLES)
State = displayEnum("State", NVDA_STATES, negative=True)
OutputReason = nvdaCode(NVDA_OUTPUT_REASON, "OutputReason", {"Enum": enum.Enum, "auto": enum.auto})
DescriptionFrom = nvdaCode(NVDA_DESCRIPTION_FROM, "DescriptionFrom", {"Enum": enum.Enum, "auto": enum.auto})


class IsCurrent(enum.Enum):
	"""NVDA's controlTypes.IsCurrent, as far as a page that marks nothing current goes."""

	NO = "false"


#: NVDA's settings: its defaults, with what the tester changed (the config in the log).
TESTERS_SETTINGS = {
	"speech": {"autoLanguageSwitching": True},
	"presentation": {"reportObjectDescriptions": True},
	"documentFormatting": {"reportLandmarks": True, "reportFrames": False, "reportArticles": True, "reportClickable": False},
	"annotations": {},
}


def testersConfig():
	conf = {section: dict(values) for section, values in NVDA_DEFAULTS.items()}
	for section, values in TESTERS_SETTINGS.items():
		conf[section].update(values)
	return conf


config = types.ModuleType("config")
config.conf = testersConfig()

controlTypes = types.ModuleType("controlTypes")
controlTypes.Role, controlTypes.State, controlTypes.OutputReason = Role, State, OutputReason
controlTypes.DescriptionFrom, controlTypes.IsCurrent = DescriptionFrom, IsCurrent
stateScope = {"Role": Role, "State": State, "OutputReason": OutputReason, "config": config}
controlTypes.STATES_SORTED = nvdaCode(NVDA_STATES_SORTED, "STATES_SORTED", stateScope)
controlTypes.STATES_LINK_TYPE = nvdaCode(NVDA_STATES_LINK_TYPE, "STATES_LINK_TYPE", stateScope)
nvdaCode(NVDA_CLICKABLE_ROLES, "clickableRoles", stateScope)
controlTypes.silentValuesForRoles = nvdaCode(NVDA_SILENT_VALUES, "silentValuesForRoles", stateScope)
nvdaCode(NVDA_POSITIVE_STATES, "_processPositiveStates", stateScope)
nvdaCode(NVDA_NEGATIVE_STATES, "_processNegativeStates", stateScope)
controlTypes.processAndLabelStates = nvdaCode(NVDA_LABEL_STATES, "processAndLabelStates", stateScope)

textInfos = types.ModuleType("textInfos")
fieldScope = {"controlTypes": controlTypes, "OutputReason": OutputReason}
textInfos.Field = nvdaCode(NVDA_FIELD, "Field", fieldScope)
textInfos.FormatField = nvdaCode(NVDA_FORMAT_FIELD, "FormatField", fieldScope)
textInfos.ControlField = nvdaCode(NVDA_CONTROL_FIELD, "ControlField", fieldScope)
textInfos.FieldCommand = nvdaCode(NVDA_FIELD_COMMAND, "FieldCommand", fieldScope)
textInfos.UNIT_CHARACTER, textInfos.UNIT_WORD, textInfos.UNIT_LINE = "character", "word", "line"
textInfos.UNIT_PARAGRAPH, textInfos.UNIT_CELL = "paragraph", "cell"


def notHere(*args, **kwargs):
	raise AssertionError("NVDA doesn't get here for these pages: no indentation, spelling or math")


class ReportLineIndentation(enum.IntEnum):
	"""NVDA's config.configFlags.ReportLineIndentation."""

	OFF = 0


class ReportTableHeaders(enum.IntEnum):
	"""NVDA's config.configFlags.ReportTableHeaders."""

	OFF = 0
	ROWS_AND_COLUMNS = 1
	ROWS = 2
	COLUMNS = 3


class SpeechCommand:
	"""NVDA's speech.commands.SpeechCommand."""


class LangChangeCommand(SpeechCommand):
	"""NVDA's speech.commands.LangChangeCommand."""

	def __init__(self, lang):
		self.lang = lang


class EndUtteranceCommand(SpeechCommand):
	"""NVDA's speech.commands.EndUtteranceCommand."""


#: What NVDA said, as its log shows it: each utterance's words.
spoken = []


def speak(sequence, priority=None):
	"""NVDA's speech.speak, as its log's "Speaking" line has it: the words, without the empty ones speak() leaves out
	(a LangChangeCommand is not a word)."""
	spoken.append([item for item in sequence if isinstance(item, str) and item])


languageHandling = types.SimpleNamespace()
languageHandling.shouldMakeLangChangeCommand = nvdaCode(NVDA_LANG_CHANGE, "shouldMakeLangChangeCommand", {"config": config})

#: NVDA's speech/speech.py, the functions these pages use, in one module as in NVDA.
speechScope = {
	"config": config,
	"controlTypes": controlTypes,
	"textInfos": textInfos,
	"OutputReason": OutputReason,
	"State": State,
	"weakref": weakref,
	"itertools": itertools,
	"unicodeNormalize": lambda text: unicodedata.normalize("NFKC", text),
	"languageHandling": languageHandling,
	"LangChangeCommand": LangChangeCommand,
	"EndUtteranceCommand": EndUtteranceCommand,
	"SpeechCommand": SpeechCommand,
	"ReportLineIndentation": ReportLineIndentation,
	"ReportTableHeaders": ReportTableHeaders,
	"splitTextIndentation": notHere,
	"getIndentationSpeech": notHere,
	"getSpellingSpeech": notHere,
	"getSingleCharDescription": notHere,
	"_extendSpeechSequence_addMathForTextInfo": notHere,
	# NVDA's aria.landmarkRoles, for the landmarks on these pages.
	"aria": types.SimpleNamespace(landmarkRoles={"banner": "banner", "main": "main", "navigation": "navigation", "complementary": "complementary", "contentinfo": "content info"}),
	"log": nvdaLog,
	"_": lambda text: text,
	"ngettext": lambda one, many, count: one if count == 1 else many,
	"types": types.SimpleNamespace(logBadSequenceTypes=lambda sequence, raiseExceptionOnError=False: True),
	"logBadSequenceTypes": lambda sequence, raiseExceptionOnError=False: True,
	# NVDA's speech.shortcutKeys.getKeyboardShortcutsSpeech says nothing for a field without a shortcut key.
	"getKeyboardShortcutsSpeech": lambda keyboardShortcut: [keyboardShortcut] if keyboardShortcut else [],
	"_speechState": types.SimpleNamespace(oldTableID=None, oldRowNumber=None, oldRowSpan=None, oldColumnNumber=None, oldColumnSpan=None, oldTreeLevel=None),
	"speak": speak,
}
speechScope["Iterable"] = object
for source, name in (
	(NVDA_GENERATOR_WITH_RETURN, "GeneratorWithReturn"),
	(NVDA_BLANK_CHUNK_CHARS, "BLANK_CHUNK_CHARS"),
	(NVDA_IS_BLANK, "isBlank"),
	(NVDA_SPEAK_TEXT_INFO_STATE, "SpeakTextInfoState"),
	(NVDA_LINE_END_CHARS, "LINE_END_CHARS"),
	(NVDA_IS_CONTROL_END, "_isControlEndFieldCommand"),
	(NVDA_CONSIDER_SPELLING, "_getTextInfoSpeech_considerSpelling"),
	(NVDA_UPDATE_CACHE, "_getTextInfoSpeech_updateCache"),
	(NVDA_TEXT_INFO_SPEECH, "getTextInfoSpeech"),
	(NVDA_SPEAK_TEXT_INFO, "speakTextInfo"),
	(NVDA_CONTENT_FIRST, "_shouldSpeakContentFirst"),
	(NVDA_ROW_AND_COLUMN_COUNT, "_rowAndColumnCountText"),
	(NVDA_PROPERTIES_SPEECH, "getPropertiesSpeech"),
	(NVDA_CONTROL_FIELD_SPEECH, "getControlFieldSpeech"),
):
	nvdaCode(source, name, speechScope)

#: NVDA's own, to check what the assistant puts in their place and gives back.
NVDA_FIELD_SPEECH = speechScope["getControlFieldSpeech"]

urlScope = {"controlTypes": controlTypes, "log": nvdaLog, "ParseResult": ParseResult, "urlparse": urlparse, "urlunparse": urlunparse}
nvdaCode(NVDA_SAME_PAGE_URL, "isSamePageURL", urlScope)
urlUtils = types.SimpleNamespace(getLinkType=nvdaCode(NVDA_GET_LINK_TYPE, "getLinkType", urlScope))
browseScope = {"controlTypes": controlTypes, "urlUtils": urlUtils, "textInfos": textInfos}


class BrowseModeTreeInterceptor:
	"""NVDA's browseMode.BrowseModeTreeInterceptor: the document's address, and NVDA's getLinkTypeInDocument."""

	documentURL = None
	getLinkTypeInDocument = nvdaCode(NVDA_LINK_TYPE_IN_DOCUMENT, "getLinkTypeInDocument", dict(browseScope))


NVDA_LINK_TYPE = vars(BrowseModeTreeInterceptor)["getLinkTypeInDocument"]


class ChromeVBuf(BrowseModeTreeInterceptor):
	"""Edge's page in NVDA's virtual buffer (virtualBuffers.gecko_ia2.GeckoVBuf, NVDAObjects.IAccessible.chromium.ChromeVBuf)."""

	def __init__(self, url):
		self.documentURL = url


class TextInfoQuickNavItem:
	"""NVDA's browseMode.TextInfoQuickNavItem, with NVDA's report."""

	def __init__(self, itemType, document, textInfo, outputReason=OutputReason.QUICKNAV):
		self.itemType, self.document, self.textInfo, self.outputReason = itemType, document, textInfo, outputReason

	report = nvdaCode(NVDA_QUICK_NAV_REPORT, "report", dict(browseScope, speech=None))


NVDA_REPORT = vars(TextInfoQuickNavItem)["report"]
# NVDA's report finds the speech package as a module global, as NVDA's browseMode imports it.
NVDA_REPORT.__globals__["speech"] = None


class VirtualBufferQuickNavItem(TextInfoQuickNavItem):
	"""virtualBuffers.VirtualBufferQuickNavItem, what Edge's quick navigation makes: it has TextInfoQuickNavItem's report."""


virtualBuffers = types.ModuleType("virtualBuffers")
virtualBuffers.VirtualBufferQuickNavItem = VirtualBufferQuickNavItem


class TextInfo:
	"""NVDA's textInfos.TextInfo, as far as getTextInfoSpeech asks it: its fields and text, and NVDA's own
	getControlFieldSpeech. A web page's text has no formatting NVDA says as it comes."""

	getControlFieldSpeech = nvdaCode(
		NVDA_TEXT_INFO_CONTROL_FIELD_SPEECH,
		"getControlFieldSpeech",
		{"_logBadSequenceTypes": lambda sequence: True},
	)

	def getFormatFieldSpeech(self, attrs, attrsCache=None, formatConfig=None, reason=None, unit=None, extraDetail=False, initialFormat=False):
		return []


textInfos.TextInfo = TextInfo
NVDA_TEXT_FIELD_SPEECH = vars(TextInfo)["getControlFieldSpeech"]


class GeckoVBufTextInfo(TextInfo):
	"""NVDA's virtualBuffers.gecko_ia2.Gecko_ia2_TextInfo: a range of the page, with the fields Edge's virtual buffer
	gives for it. ``parts`` is a list of fields (as Edge gives them: dicts) and strings; a field holds what follows it,
	up to the end, or to a None that closes it."""

	_calculateDescriptionFrom = nvdaCode(NVDA_GECKO_DESCRIPTION_FROM, "_calculateDescriptionFrom", {"controlTypes": controlTypes})

	def __init__(self, obj, parts):
		self.obj, self.parts = obj, parts

	def _normalizeControlField(self, attrs):
		"""As NVDA 2026.2's Gecko_ia2_TextInfo._normalizeControlField does for what is on these pages: where the
		description comes from, the role and states (NVDA's own link part), the level and the landmark."""
		attrs["_description-from"] = self._calculateDescriptionFrom(attrs)
		role = attrs.pop("IAccessible::role")
		states = set(attrs.pop("IAccessible::states", ()))
		role = normalizeLink(self, attrs, role, states)
		attrs["role"] = role
		attrs["states"] = states
		level = attrs.get("IAccessible2::attribute_level", "")
		if level != "" and level is not None:
			attrs["level"] = level
		return attrs

	def getTextWithFields(self, formatConfig=None):
		commands = []
		open_ = 0
		for part in self.parts:
			if part is None:
				commands.append(textInfos.FieldCommand("controlEnd", None))
				open_ -= 1
			elif isinstance(part, str):
				commands.append(part)
			else:
				commands.append(textInfos.FieldCommand("controlStart", textInfos.ControlField(self._normalizeControlField(dict(part)))))
				open_ += 1
		commands.extend(textInfos.FieldCommand("controlEnd", None) for _ in range(open_))
		return commands


#: NVDA 2026.2's link part of Gecko_ia2_TextInfo._normalizeControlField, as a function of what it reads and changes.
normalizeLink = nvdaCode(
	"def normalizeLink(self, attrs, role, states):\n" + textwrap.indent(NVDA_GECKO_LINK, "\t") + "\treturn role\n",
	"normalizeLink",
	{"controlTypes": controlTypes},
)
#: Chrome's and Edge's: where a description comes from is in the IA2 attribute "description-from".
ChromeVBufTextInfo = nvdaMethods("ChromeVBufTextInfo", [GeckoVBufTextInfo], [NVDA_CHROME_DESCRIPTION_FROM], {"controlTypes": controlTypes, "log": nvdaLog})


# -- the tester's pages -------------------------------------------------------------------------------------------

HOME = "https://www.profootballrumors.com/"
LINKED = [State.LINKED, State.FOCUSABLE]


def landmark(name, uniqueID):
	return {"IAccessible::role": Role.LANDMARK, "landmark": name, "uniqueID": uniqueID}


def heading(level, uniqueID):
	return {"IAccessible::role": Role.HEADING, "IAccessible2::attribute_level": str(level), "uniqueID": uniqueID}


def link(href, uniqueID, title=None, visited=False, description=None, descriptionFrom=None):
	"""A link as Edge gives it: its address, and its title as its description ("description-from" tooltip)."""
	attrs = {"IAccessible::role": Role.LINK, "IAccessible::states": LINKED + ([State.VISITED] if visited else []), "IAccessible::value": href, "uniqueID": uniqueID}
	if title is not None:
		attrs["description"], attrs["IAccessible2::attribute_description-from"] = title, "tooltip"
	if description is not None:
		attrs["description"] = description
		if descriptionFrom:
			attrs["IAccessible2::attribute_description-from"] = descriptionFrom
	return attrs


BANNER = landmark("banner", 1)
MAIN = landmark("main", 2)

#: What H, Control+Home and the arrow keys read on www.profootballrumors.com.
FOOTBALL = {
	"skip": [link(HOME + "#content", 10), "Skip to content"],
	"headlines": [heading(3, 11), link("https://www.profootballrumors.com/", 12, title="Homepage"), "HEADLINES"],
	"site": [BANNER, heading(1, 13), link(HOME, 14, title="Home"), "Pro Football Rumors"],
	"vikings": [MAIN, heading(2, 15), link(HOME + "2026/09/vikings-to-sign-p-johnny-hekker-2", 16), "Vikings To Sign P Johnny Hekker"],
	# Not on the tester's page: a link that ends before its heading does, and one to the top of the page ("#").
	"byline": [MAIN, heading(2, 17), link(HOME + "2026/09/story", 18), "Story", None, " by Sam Robinson"],
	"top": [link(HOME + "#", 19), "Back to top"],
}


class TesterPageTests(unittest.TestCase):
	"""The tester's pages, read with NVDA 2026.2's own speech code."""

	def setUp(self):
		self.browseMode = types.ModuleType("browseMode")
		self.browseMode.BrowseModeTreeInterceptor = BrowseModeTreeInterceptor
		self.browseMode.TextInfoQuickNavItem = TextInfoQuickNavItem
		self.speech = types.ModuleType("speech")
		self.speech.getControlFieldSpeech = NVDA_FIELD_SPEECH
		self.speech.getPropertiesSpeech = speechScope["getPropertiesSpeech"]
		self.speech.speakTextInfo = speechScope["speakTextInfo"]
		modules = mock.patch.dict(
			sys.modules,
			{
				"browseMode": self.browseMode,
				"virtualBuffers": virtualBuffers,
				"speech": self.speech,
				"controlTypes": controlTypes,
				"config": config,
				"textInfos": textInfos,
			},
		)
		modules.start()
		self.addCleanup(modules.stop)
		NVDA_REPORT.__globals__["speech"] = self.speech
		self.addCleanup(self._restoreNvda)
		config.conf = testersConfig()
		self.page = ChromeVBuf(HOME)
		spoken.clear()

	def _restoreNvda(self):
		linkSpeech.unregister()
		quickNavHeadings.unregister()
		# Whatever a test put over NVDA's own goes, so the next test starts from NVDA as it is.
		self.speech.getControlFieldSpeech = NVDA_FIELD_SPEECH
		TextInfoQuickNavItem.report = NVDA_REPORT
		BrowseModeTreeInterceptor.getLinkTypeInDocument = NVDA_LINK_TYPE
		TextInfo.getControlFieldSpeech = NVDA_TEXT_FIELD_SPEECH
		if "report" in vars(VirtualBufferQuickNavItem):
			del VirtualBufferQuickNavItem.report
		for module in (linkSpeech, quickNavHeadings):
			module._replaced.clear()
			module._failed = False
		NVDA_REPORT.__globals__["speech"] = None
		config.conf = testersConfig()

	def asTheTesterHasIt(self):
		"""JAWS Migration Assistant 1.24: quick navigation says a heading without what it is in."""
		quickNavHeadings.register()

	def part(self, name, pages=FOOTBALL, textInfoClass=ChromeVBufTextInfo):
		return textInfoClass(self.page, pages[name])

	def press(self, name, itemType="heading", pages=FOOTBALL, reason=OutputReason.QUICKNAV, textInfoClass=ChromeVBufTextInfo):
		"""Quick navigation to the item: NVDA's _quickNavScript moves there and reports it."""
		spoken.clear()
		VirtualBufferQuickNavItem(itemType, self.page, self.part(name, pages, textInfoClass), reason).report()
		self.assertEqual(len(spoken), 1)
		return spoken[0]

	def line(self, name, pages=FOOTBALL):
		"""An arrow key, or Control+Home, to the line: NVDA says it for the caret."""
		spoken.clear()
		self.speech.speakTextInfo(self.part(name, pages), unit=textInfos.UNIT_LINE, reason=OutputReason.CARET)
		return spoken[0]

	def focus(self, name, pages=FOOTBALL):
		"""Tab to the link: browse mode says it for the focus."""
		spoken.clear()
		self.speech.speakTextInfo(self.part(name, pages), reason=OutputReason.FOCUS)
		return spoken[0]

	def theTestersKeys(self):
		"""The tester's keys, in the order of the log: H, Control+Home, H, H, H."""
		return [self.press("headlines"), self.line("skip"), self.press("headlines"), self.press("site"), self.press("vikings")]

	# -- the tester's report ---------------------------------------------------------------------------------------

	def test_nvdaSaidWhatTheLogSays(self):
		self.asTheTesterHasIt()
		self.assertEqual(
			self.theTestersKeys(),
			[
				["HEADLINES", "same page", "link", "Homepage", "heading", "level 3"],
				["same page", "link", "Skip to content"],
				["HEADLINES", "same page", "link", "Homepage", "heading", "level 3"],
				["Pro Football Rumors", "same page", "link", "Home", "heading", "level 1"],
				["Vikings To Sign P Johnny Hekker", "link", "heading", "level 2"],
			],
			"the imitation NVDA says what the tester's NVDA said",
		)

	def test_saidAsJawsSaysIt(self):
		self.asTheTesterHasIt()
		linkSpeech.register()
		self.assertEqual(
			self.theTestersKeys(),
			[
				["HEADLINES", "heading", "level 3", "link"],
				["same page", "link", "Skip to content"],
				["HEADLINES", "heading", "level 3", "link"],
				["Pro Football Rumors", "heading", "level 1", "link"],
				["Vikings To Sign P Johnny Hekker", "heading", "level 2", "link"],
			],
			'JAWS: "HEADLINES heading level 3 Link", "Pro Football Rumors heading level 1 Link", "Vikings To Sign P Johnny Hekker heading level 2 Link"',
		)

	def test_theSameWithoutQuickNavHeadings(self):
		# Turned off in the Settings panel, quick navigation says the landmark again; the link is still said as JAWS says it.
		linkSpeech.register()
		self.assertEqual(self.press("site"), ["banner landmark", "Pro Football Rumors", "heading", "level 1", "link"])
		self.assertEqual(self.press("vikings"), ["main landmark", "Vikings To Sign P Johnny Hekker", "heading", "level 2", "link"])

	def test_eitherOrderOfRegistering(self):
		linkSpeech.register()
		self.asTheTesterHasIt()
		self.assertEqual(self.press("site"), ["Pro Football Rumors", "heading", "level 1", "link"])
		self.assertEqual(self.press("vikings"), ["Vikings To Sign P Johnny Hekker", "heading", "level 2", "link"])

	# -- "same page" -----------------------------------------------------------------------------------------------

	def test_samePageOnlyForAPlaceOnThePage(self):
		linkSpeech.register()
		self.assertEqual(self.line("skip"), ["same page", "link", "Skip to content"], "#content: a place on the page")
		self.assertEqual(self.focus("skip"), ["Skip to content", "same page", "link"], "Tab to it: the same")
		self.assertEqual(self.line("top"), ["same page", "link", "Back to top"], '"#" alone: the top of the page')
		self.assertEqual(self.line("headlines"), ["heading", "level 3", "link", "HEADLINES"], "the home page, on the home page")
		self.assertEqual(self.line("vikings"), ["main landmark", "heading", "level 2", "link", "Vikings To Sign P Johnny Hekker"])

	def test_nvdaAloneSaysSamePageForThePageItself(self):
		self.assertEqual(self.line("headlines"), ["heading", "level 3", "same page", "link", "HEADLINES"])
		self.assertEqual(self.page.getLinkTypeInDocument(HOME), State.INTERNAL_LINK)
		linkSpeech.register()
		self.assertIsNone(self.page.getLinkTypeInDocument(HOME))
		self.assertIsNone(self.page.getLinkTypeInDocument(HOME + "?page=2"), "a different page")
		self.assertEqual(self.page.getLinkTypeInDocument(HOME + "#content"), State.INTERNAL_LINK)
		self.assertEqual(self.page.getLinkTypeInDocument(HOME + "#"), State.INTERNAL_LINK)
		self.assertIsNone(self.page.getLinkTypeInDocument("https://www.mlbtraderumors.com/#content"), "another site")

	def test_reportLinkTypeOff(self):
		# NVDA's own "Report link type" still decides whether "same page" is said at all.
		config.conf["documentFormatting"]["reportLinkType"] = False
		linkSpeech.register()
		self.assertEqual(self.line("skip"), ["link", "Skip to content"])

	# -- a link's title --------------------------------------------------------------------------------------------

	def test_aLinksTitleIsntSaid(self):
		self.assertEqual(self.focus("headlines"), ["HEADLINES", "same page", "link", "Homepage", "heading", "level 3"])
		self.assertEqual(self.press("headlines", itemType="link"), ["HEADLINES", "same page", "link", "Homepage", "heading", "level 3"])
		linkSpeech.register()
		self.assertEqual(self.focus("headlines"), ["HEADLINES", "link", "heading", "level 3"], "Tab")
		self.assertEqual(self.press("headlines", itemType="link"), ["HEADLINES", "link", "heading", "level 3"], "K")

	def test_otherDescriptionsAreSaid(self):
		pages = {
			"described": [heading(2, 30), link(HOME + "a", 31, description="Author: u/Fuspo14 11 hr. ago", descriptionFrom="aria-describedby"), "My only regret joining Visible"],
			"aria": [link(HOME + "b", 32, description="Opens a new window", descriptionFrom="aria-description"), "Scores"],
		}
		linkSpeech.register()
		self.assertEqual(self.focus("aria", pages), ["Scores", "link", "Opens a new window"])
		self.assertEqual(self.press("described", pages=pages), ["My only regret joining Visible", "heading", "level 2", "link", "Author: u/Fuspo14 11 hr. ago"])

	def test_firefoxCantTellATitle(self):
		# Firefox gives no "description-from": NVDA can't tell a title from aria-describedby, so it is said as before.
		linkSpeech.register()
		self.assertEqual(
			self.press("headlines", textInfoClass=GeckoVBufTextInfo),
			["HEADLINES", "heading", "level 3", "link", "Homepage"],
		)

	def test_theFieldNvdaKeepsIsntChanged(self):
		linkSpeech.register()
		field = textInfos.ControlField(ChromeVBufTextInfo(self.page, [])._normalizeControlField(dict(FOOTBALL["headlines"][1])))
		self.assertIs(field["_description-from"], DescriptionFrom.TOOLTIP)
		without = linkSpeech.withoutTitle(field)
		self.assertIsInstance(without, textInfos.ControlField)
		self.assertNotIn("description", without)
		self.assertEqual(field["description"], "Homepage", "NVDA's own field keeps its title, for braille and the rest")

	# -- the order after a heading ---------------------------------------------------------------------------------

	def test_redditsHeadings(self):
		# Issue 8: JAWS said "Feels to good to be true  visited    heading level 2". Reddit's post titles are links in a
		# heading, and some headings are in a link; the tester's JAWS said "visited" before the heading.
		reddit = {
			"inHeading": [MAIN, {"IAccessible::role": Role.ARTICLE, "uniqueID": 40}, heading(2, 41), link("https://www.reddit.com/r/Visible/comments/1", 42, visited=True), "Feels to good to be true"],
			"aroundHeading": [MAIN, link("https://www.reddit.com/r/Visible/comments/2", 43, visited=True), heading(2, 44), "New speedtest megathread"],
		}
		self.page = ChromeVBuf("https://www.reddit.com/r/Visible/")
		self.asTheTesterHasIt()
		self.assertEqual(self.press("inHeading", pages=reddit), ["Feels to good to be true", "visited", "link", "heading", "level 2"])
		self.assertEqual(self.press("aroundHeading", pages=reddit), ["New speedtest megathread", "heading", "level 2", "visited", "link"])
		linkSpeech.register()
		self.assertEqual(self.press("inHeading", pages=reddit), ["Feels to good to be true", "visited", "heading", "level 2", "link"])
		self.assertEqual(self.press("aroundHeading", pages=reddit), ["New speedtest megathread", "visited", "heading", "level 2", "link"])

	def test_everyWayQuickNavigationReportsAHeading(self):
		self.asTheTesterHasIt()
		linkSpeech.register()
		for itemType in ["heading"] + [f"heading{level}" for level in range(1, 10)]:
			spoken.clear()
			VirtualBufferQuickNavItem(itemType, self.page, self.part("vikings")).report()
			self.assertEqual(spoken, [["Vikings To Sign P Johnny Hekker", "heading", "level 2", "link"]], itemType)
		# Quick navigation outside a web page's virtual buffer (a document NVDA reads through UI Automation) is NVDA's.
		spoken.clear()
		TextInfoQuickNavItem("heading", self.page, self.part("vikings")).report()
		self.assertEqual(spoken, [["Vikings To Sign P Johnny Hekker", "link", "heading", "level 2"]])

	def test_otherKeysKeepNvdasOrder(self):
		self.asTheTesterHasIt()
		linkSpeech.register()
		self.assertEqual(self.press("vikings", itemType="link"), ["main landmark", "Vikings To Sign P Johnny Hekker", "link", "heading", "level 2"], "K")
		self.assertEqual(self.focus("vikings"), ["Vikings To Sign P Johnny Hekker", "link", "heading", "level 2"], "Tab: NVDA knows it is in the landmark")
		self.assertEqual(self.line("vikings"), ["heading", "level 2", "link", "Vikings To Sign P Johnny Hekker"], "the arrow keys")

	def test_aLinkThatEndsBeforeItsHeading(self):
		self.asTheTesterHasIt()
		linkSpeech.register()
		self.assertEqual(self.press("byline"), ["Story", "link", " by Sam Robinson", "heading", "level 2"], "said where NVDA says it")

	def test_headingsOrLinksNotReported(self):
		self.asTheTesterHasIt()
		linkSpeech.register()
		config.conf["documentFormatting"]["reportHeadings"] = False
		self.assertEqual(self.press("vikings"), ["Vikings To Sign P Johnny Hekker", "link"])
		config.conf["documentFormatting"]["reportHeadings"] = True
		config.conf["documentFormatting"]["reportLinks"] = False
		self.assertEqual(self.press("vikings"), ["Vikings To Sign P Johnny Hekker", "heading", "level 2"])

	def test_theLogSaysWhatChanged(self):
		self.asTheTesterHasIt()
		linkSpeech.register()
		with mock.patch.object(linkSpeech, "_log") as log:
			self.press("vikings")
		said = [call.args[0] for call in log.return_value.debug.call_args_list]
		self.assertTrue(any('says the heading before "link"' in line and line.endswith(": heading, level 2, link") for line in said), said)

	# -- turned on and off -----------------------------------------------------------------------------------------

	def nvdasOwn(self):
		return (
			vars(BrowseModeTreeInterceptor)["getLinkTypeInDocument"] is NVDA_LINK_TYPE
			and vars(TextInfo)["getControlFieldSpeech"] is NVDA_TEXT_FIELD_SPEECH
			and "report" not in vars(VirtualBufferQuickNavItem)
		)

	def test_turnedOffNvdaHasItsOwnBack(self):
		self.asTheTesterHasIt()
		linkSpeech.register()
		self.assertFalse(self.nvdasOwn())
		self.assertTrue(linkSpeech._isOurs(vars(VirtualBufferQuickNavItem)["report"]))
		linkSpeech.unregister()
		self.assertTrue(self.nvdasOwn())
		self.assertEqual(self.press("headlines"), ["HEADLINES", "same page", "link", "Homepage", "heading", "level 3"])

	def test_quickNavHeadingsIsLeftAlone(self):
		# linkSpeech changes none of what quickNavHeadings changes, so either can be turned off in the Settings panel
		# and give NVDA its own back, in any order.
		for first, second in ((quickNavHeadings, linkSpeech), (linkSpeech, quickNavHeadings)):
			quickNavHeadings.register()
			linkSpeech.register()
			self.assertIs(self.speech.getControlFieldSpeech.__wrapped__, NVDA_FIELD_SPEECH)
			self.assertIs(vars(TextInfoQuickNavItem)["report"].__wrapped__, NVDA_REPORT)
			first.unregister()
			second.unregister()
			self.assertTrue(self.nvdasOwn(), first.__name__)
			self.assertIs(self.speech.getControlFieldSpeech, NVDA_FIELD_SPEECH, first.__name__)
			self.assertIs(vars(TextInfoQuickNavItem)["report"], NVDA_REPORT, first.__name__)

	def test_anotherAddonOnTop(self):
		linkSpeech.register()
		theirs = TextInfo.getControlFieldSpeech

		@functools.wraps(theirs)
		def anotherAddon(*args, **kwargs):
			return theirs(*args, **kwargs)

		TextInfo.getControlFieldSpeech = anotherAddon
		self.assertEqual(self.press("vikings"), ["main landmark", "Vikings To Sign P Johnny Hekker", "heading", "level 2", "link"])
		linkSpeech.unregister()
		self.assertIs(vars(TextInfo)["getControlFieldSpeech"], anotherAddon, "the other add-on's is left in place")
		linkSpeech.register()
		self.assertIs(vars(TextInfo)["getControlFieldSpeech"], anotherAddon, "not put over it a second time")
		self.assertEqual(self.press("vikings"), ["Vikings To Sign P Johnny Hekker", "heading", "level 2", "link"], "NVDA knows it is in the landmark")


class LinkSpeechTests(unittest.TestCase):
	def test_placeOnPage(self):
		for url in ("https://www.profootballrumors.com/#content", "https://example.com/page#", "#top"):
			self.assertTrue(linkSpeech.isPlaceOnPage(url), url)
		for url in ("https://www.profootballrumors.com/", "https://example.com/page?x=1", "", None, 3):
			self.assertFalse(linkSpeech.isPlaceOnPage(url), url)

	def test_headingItemTypes(self):
		for itemType in ["heading"] + [f"heading{level}" for level in range(1, 10)]:
			self.assertTrue(linkSpeech.isHeading(types.SimpleNamespace(itemType=itemType)), itemType)
		for itemType in ("link", "headingless", "Heading", "", None):
			self.assertFalse(linkSpeech.isHeading(types.SimpleNamespace(itemType=itemType)), itemType)

	def test_onUnlessTurnedOff(self):
		self.assertTrue(linkSpeech.wanted({}))
		self.assertTrue(linkSpeech.wanted({linkSpeech.STATE_KEY: True}))
		self.assertFalse(linkSpeech.wanted({linkSpeech.STATE_KEY: False}))
		self.assertFalse(linkSpeech.wanted(None))
		self.assertIs(state.DEFAULTS[linkSpeech.STATE_KEY], True)


class SamePageSettingTests(unittest.TestCase):
	"""NVDA's "Report link type" names same page links only: JAWS's "Identify same page links"."""

	def reportLinkType(self, jcf):
		result = settingsMap.mapSettings(jawsFiles.parseIni(jcf))
		values = {change.key: change.value for change in result.changes}
		return values.get("documentFormatting.reportLinkType", "unchanged"), result

	def test_identifySamePageLinks(self):
		self.assertIs(self.reportLinkType("[HTML]\nIdentifySamePageLinks=1\n")[0], True)
		self.assertIs(self.reportLinkType("[HTML]\nIdentifySamePageLinks=0\n")[0], False)

	def test_identifyLinkTypeIsntSamePage(self):
		value, result = self.reportLinkType("[HTML]\nIdentifyLinkType=0\n")
		self.assertEqual(value, "unchanged", "JAWS's link types are mail, FTP and news links")
		self.assertIn(("HTML", "IdentifyLinkType"), {(item.section, item.key) for item in result.notMigrated})
		self.assertIs(self.reportLinkType("[HTML]\nIdentifyLinkType=0\nIdentifySamePageLinks=1\n")[0], True)


if __name__ == "__main__":
	unittest.main()
