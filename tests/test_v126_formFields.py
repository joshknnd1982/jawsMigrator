# Unit tests for version 1.26, from a tester's report (issue 22, "What jaws says when replying to a reddit post"). On
# a reddit post in Edge the tester pressed E to the reply box, then Enter, and JAWS said:
#       edit
#     blank
#     placeholder
#     Join the conversation
# NVDA 2026.2 with JAWS Migration Assistant 1.24 said (NVDA log 2026-09-26 12.50.56.zip, nvda.log):
#     12:48:50.288 Input: kb(laptop):e
#     12:48:50.292 Speaking ['main landmark', 'edit', 'multi line', 'Join the conversation']
#     12:48:51.359 Input: kb(laptop):enter
#     12:48:51.857 Speaking ['main landmark', CancellableSpeech (still valid)]
#     12:48:51.911 HOOK INPUT: ['Join the conversation', 'edit', 'multi line', CancellableSpeech (still valid), 'blank']
# (the HOOK lines are ClassicSpeech's: what NVDA said before ClassicSpeech put "blank" before "multi line"). On GitHub's
# new issue page it said (HOOK INPUT, NVDA's own):
#     12:50:14.170 ['Add a title', 'edit', 'required', CancellableSpeech (still valid), 'Title', CancellableSpeech (still valid), 'blank']
#     12:50:35.689 ['Markdown value', 'edit', 'multi line', 'Markdown input: edit mode selected.', CancellableSpeech (still valid), 'Type your description here…', CancellableSpeech (still valid), 'blank']
# JAWS 2026's scripts for Edge, Chrome and Firefox (IA2Browser.jss, HandleSayObjectForEdit, which SayObjectTypeAndText
# calls for the focus and for Insert+Tab) say an empty edit field as its name and type, its states, cmsgBlank1
# ("blank"), cmsgPlaceholder ("placeholder") and the placeholder, then its description. Edge makes a box with no label
# but a placeholder a name from the placeholder and says so (IAccessible2 attribute "name-from:placeholder",
# Chromium's AXPlatformNodeBase::ComputeAttributes), without a "placeholder" attribute (Blink's
# AXNodeObject::Placeholder gives none when the name came from it); JAWS said no name. JAWS's Default.jcf has
# AnnounceMultilineEdit=0 ("Determines if Multi-line edit control type is announced or not"), so JAWS says "edit".
# - formFields: an empty edit field on a web page is said with "blank", then "placeholder" and its placeholder, then its
#   description; a name made from the placeholder is said there, not as the name; NVDA says no "multi line" for an
#   edit field; and as the focus moves within a page, NVDA doesn't say again what browse mode's cursor was in.
# The imitation NVDA runs NVDA 2026.2's own code, word for word, taken from the release-2026.2 sources by script:
# getObjectSpeech, _objectSpeech_calculateAllowedProps, getObjectPropertiesSpeech, _getPlaceholderSpeechIfTextEmpty,
# speakObject and speech.types._flattenNestedSequences; NVDAObject's presentationType, isPresentableFocusAncestor,
# roleText, _isTextEmpty, reportFocus, event_focusEntered and event_gainFocus; Ia2Web's placeholder,
# isPresentableFocusAncestor, roleText and landmark; BrowseModeDocumentTreeInterceptor's event_gainFocus,
# _replayFocusEnteredEvents, _shouldIgnoreFocus and _postGainFocus; Gecko_ia2's getIdentifierFromNVDAObject and
# _shouldIgnoreFocus; api's getFocusAncestors and getFocusDifferenceLevel; controlTypes.silentRolesOnFocus and
# aria.landmarkRoles. getTextInfoSpeech, speakTextInfo, getPropertiesSpeech, getControlFieldSpeech and the rest of
# NVDA's speech code, with NVDA's roles, states and default settings, are the ones tests/test_v125_linkSpeech.py took
# from the same sources. The page is the tester's, as Edge gives it to NVDA. The assistant's code (formFields and the
# global plugin's event_gainFocus) is the real one.
# Run: python -m unittest tests.test_v126_formFields -v

import enum
import itertools
import os
import sys
import textwrap
import types
import typing
import unicodedata
import unittest
import weakref
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

# NVDA 2026.2's speech code and its roles, states and settings, taken there word for word.
import test_v125_linkSpeech as v125  # noqa: E402

import jawsMigrator  # noqa: E402
from jawsMigrator import formFields, state  # noqa: E402


#: NVDA 2026.2, source/speech/speech.py, getObjectSpeech, word for word.
NVDA_OBJECT_SPEECH = r'''
def getObjectSpeech(
	obj: "NVDAObjects.NVDAObject",
	reason: OutputReason = OutputReason.QUERY,
	_prefixSpeechCommand: Optional[SpeechCommand] = None,
) -> SpeechSequence:
	if objectBelowLockScreenAndWindowsIsLocked(obj):
		return []
	role = obj.role
	# Choose when we should report the content of this object's textInfo, rather than just the object's value
	import browseMode

	shouldReportTextContent = not (
		# focusEntered or mouse should never present text content
		reason in (OutputReason.FOCUSENTERED, OutputReason.MOUSE)
		# The rootNVDAObject of a browseMode document in browse mode (not passThrough)
		# should never present text content
		or (
			isinstance(obj.treeInterceptor, browseMode.BrowseModeDocumentTreeInterceptor)
			and not obj.treeInterceptor.passThrough
			and obj == obj.treeInterceptor.rootNVDAObject
		)
		# objects that do not report as having navigableText should not report their text content either
		or not obj._hasNavigableText
	)

	allowProperties = _objectSpeech_calculateAllowedProps(reason, shouldReportTextContent, obj.role)

	if reason == OutputReason.FOCUSENTERED:
		# Aside from excluding some properties, focus entered should be spoken like focus.
		reason = OutputReason.FOCUS

	sequence = getObjectPropertiesSpeech(
		obj,
		reason=reason,
		_prefixSpeechCommand=_prefixSpeechCommand,
		**allowProperties,
	)
	if reason == OutputReason.ONLYCACHE:
		return sequence
	if shouldReportTextContent:
		try:
			info = obj.makeTextInfo(textInfos.POSITION_SELECTION)
		except (NotImplementedError, RuntimeError):
			info = None
		if info and not info.isCollapsed:
			# if there is selected text, then there is a value and we do not report placeholder
			sequence.extend(getPreselectedTextSpeech(info.text))
		else:
			if not info:
				info = obj.makeTextInfo(textInfos.POSITION_FIRST)
			info.expand(textInfos.UNIT_LINE)
			textEmpty, placeholderSeq = _getPlaceholderSpeechIfTextEmpty(obj, reason)
			sequence.extend(placeholderSeq)
			speechGen = getTextInfoSpeech(
				info,
				unit=textInfos.UNIT_LINE,
				reason=OutputReason.CARET,
			)
			sequence.extend(_flattenNestedSequences(speechGen))
	elif role == controlTypes.Role.MATH:
		import mathPres

		if mathPres.speechProvider:
			try:
				sequence.extend(
					mathPres.speechProvider.getSpeechForMathMl(obj.mathMl),
				)
			except (NotImplementedError, LookupError):
				pass
	return sequence
'''


#: NVDA 2026.2, source/speech/speech.py, _objectSpeech_calculateAllowedProps, word for word.
NVDA_ALLOWED_PROPS = r'''
def _objectSpeech_calculateAllowedProps(
	reason: OutputReason,
	shouldReportTextContent: bool,
	objRole: controlTypes.Role,
) -> dict[str, bool]:
	allowProperties = {
		"name": True,
		"role": True,
		"roleText": True,
		"states": True,
		"errorMessage": True,
		"value": True,
		"description": True,
		"hasDetails": config.conf["annotations"]["reportDetails"],
		"detailsRoles": config.conf["annotations"]["reportDetails"],
		"descriptionFrom": config.conf["annotations"]["reportAriaDescription"],
		"keyboardShortcut": True,
		"positionInfo_level": True,
		"positionInfo_indexInGroup": True,
		"positionInfo_similarItemsInGroup": True,
		"cellCoordsText": True,
		"rowNumber": True,
		"columnNumber": True,
		"includeTableCellCoords": True,
		"columnCount": True,
		"rowCount": True,
		"rowHeaderText": True,
		"columnHeaderText": True,
		"rowSpan": True,
		"columnSpan": True,
		"current": True,
	}
	if reason in (OutputReason.FOCUSENTERED, OutputReason.MOUSE):
		allowProperties["value"] = False
		# #15826: For containers, there are cases where the shortcut key can be defined but not working (e.g.
		# GROUPING). The safest strategy is then to remove the shortcut keys of containers except in the known
		# cases where it is working and useful. The only such known case is the one of LIST.
		if not objRole == controlTypes.Role.LIST:
			allowProperties["keyboardShortcut"] = False
		allowProperties["positionInfo_level"] = False
	if reason == OutputReason.MOUSE:
		# Name is often part of the text content when mouse tracking.
		allowProperties["name"] = False
		allowProperties["description"] = False
		allowProperties["positionInfo_indexInGroup"] = False
		allowProperties["positionInfo_similarItemsInGroup"] = False
	if not config.conf["presentation"]["reportObjectDescriptions"]:
		allowProperties["description"] = False
	if not config.conf["presentation"]["reportKeyboardShortcuts"]:
		allowProperties["keyboardShortcut"] = False
	if not config.conf["presentation"]["reportObjectPositionInformation"]:
		allowProperties["positionInfo_level"] = False
		allowProperties["positionInfo_indexInGroup"] = False
		allowProperties["positionInfo_similarItemsInGroup"] = False
	if reason != OutputReason.QUERY:
		allowProperties["rowCount"] = False
		allowProperties["columnCount"] = False
	formatConf = config.conf["documentFormatting"]
	if not formatConf["reportTableCellCoords"]:
		allowProperties["cellCoordsText"] = False
		# rowNumber and columnNumber might be needed even if we're not reporting coordinates.
		allowProperties["includeTableCellCoords"] = False
	if formatConf["reportTableHeaders"] not in (ReportTableHeaders.ROWS_AND_COLUMNS, ReportTableHeaders.ROWS):
		allowProperties["rowHeaderText"] = False
	if formatConf["reportTableHeaders"] not in (
		ReportTableHeaders.ROWS_AND_COLUMNS,
		ReportTableHeaders.COLUMNS,
	):
		allowProperties["columnHeaderText"] = False
	if not formatConf["reportTables"] or (
		not formatConf["reportTableCellCoords"]
		and formatConf["reportTableHeaders"] in (ReportTableHeaders.OFF, ReportTableHeaders.COLUMNS)
	):
		# We definitely aren't reporting any table row info at all.
		allowProperties["rowNumber"] = False
		allowProperties["rowSpan"] = False
	if not formatConf["reportTables"] or (
		not formatConf["reportTableCellCoords"]
		and formatConf["reportTableHeaders"] in (ReportTableHeaders.OFF, ReportTableHeaders.ROWS)
	):
		# We definitely aren't reporting any table column info at all.
		allowProperties["columnNumber"] = False
		allowProperties["columnSpan"] = False
	if shouldReportTextContent:
		allowProperties["value"] = False
	return allowProperties
'''


#: NVDA 2026.2, source/speech/speech.py, getObjectPropertiesSpeech, word for word.
NVDA_OBJECT_PROPERTIES_SPEECH = r'''
def getObjectPropertiesSpeech(  # noqa: C901
	obj: "NVDAObjects.NVDAObject",
	reason: OutputReason = OutputReason.QUERY,
	_prefixSpeechCommand: Optional[SpeechCommand] = None,
	**allowedProperties,
) -> SpeechSequence:
	if objectBelowLockScreenAndWindowsIsLocked(obj):
		return []
	# Fetch the values for all wanted properties
	newPropertyValues = {}
	positionInfo = None
	for name, value in allowedProperties.items():
		if name == "includeTableCellCoords":
			# This is verbosity info.
			newPropertyValues[name] = value
		elif name.startswith("positionInfo_") and value:
			if positionInfo is None:
				positionInfo = obj.positionInfo
		elif value and name == "current":
			# getPropertiesSpeech names this "current", but the NVDAObject property is
			# named "isCurrent", it's type should always be controltypes.IsCurrent
			newPropertyValues["current"] = obj.isCurrent

		elif value and name == "hasDetails":
			newPropertyValues["hasDetails"] = bool(obj.annotations)
		elif value and name == "detailsRoles":
			newPropertyValues["detailsRoles"] = obj.annotations.roles if obj.annotations else tuple()
		elif (
			value
			and name == "descriptionFrom"
			and (obj.descriptionFrom == controlTypes.DescriptionFrom.ARIA_DESCRIPTION)
		):
			newPropertyValues["_description-from"] = obj.descriptionFrom
			newPropertyValues["description"] = obj.description
		# Error messages should only be spoken when the input is marked invalid.
		elif name == "errorMessage" and value and State.INVALID_ENTRY not in obj.states:
			newPropertyValues["errorMessage"] = None
		elif value:
			# Certain properties such as row and column numbers have presentational versions, which should be used for speech if they are available.
			# Therefore redirect to those values first if they are available, falling back to the normal properties if not.
			names = [name]
			if name == "rowNumber":
				names.insert(0, "presentationalRowNumber")
			elif name == "columnNumber":
				names.insert(0, "presentationalColumnNumber")
			elif name == "rowCount":
				names.insert(0, "presentationalRowCount")
			elif name == "columnCount":
				names.insert(0, "presentationalColumnCount")
			for tryName in names:
				try:
					newPropertyValues[name] = getattr(obj, tryName)
				except NotImplementedError:
					continue
				break

	if (
		newPropertyValues.get("description")  # has a value
		and newPropertyValues.get("name") == newPropertyValues.get("description")  # value is equal to name
		and reason != controlTypes.OutputReason.CHANGE  # if the value has changed, report it.
	):
		del newPropertyValues["description"]  # prevent duplicate speech due to description matching name

	if positionInfo:
		if allowedProperties.get("positionInfo_level", False) and "level" in positionInfo:
			newPropertyValues["positionInfo_level"] = positionInfo["level"]
		if allowedProperties.get("positionInfo_indexInGroup", False) and "indexInGroup" in positionInfo:
			newPropertyValues["positionInfo_indexInGroup"] = positionInfo["indexInGroup"]
		if (
			allowedProperties.get("positionInfo_similarItemsInGroup", False)
			and "similarItemsInGroup" in positionInfo
		):
			newPropertyValues["positionInfo_similarItemsInGroup"] = positionInfo["similarItemsInGroup"]
	# Fetched the cached properties and update them with the new ones
	oldCachedPropertyValues = getattr(obj, "_speakObjectPropertiesCache", {}).copy()
	cachedPropertyValues = oldCachedPropertyValues.copy()
	cachedPropertyValues.update(newPropertyValues)
	obj._speakObjectPropertiesCache = cachedPropertyValues
	# If we should only cache we can stop here
	if reason == OutputReason.ONLYCACHE:
		return []
	# If only speaking change, then filter out all values that havn't changed
	if reason == OutputReason.CHANGE:
		for name in set(newPropertyValues) & set(oldCachedPropertyValues):
			if newPropertyValues[name] == oldCachedPropertyValues[name]:
				del newPropertyValues[name]
			elif name == "states":  # states need specific handling
				oldStates = oldCachedPropertyValues[name]
				newStates = newPropertyValues[name]
				newPropertyValues["states"] = newStates - oldStates
				newPropertyValues["negativeStates"] = oldStates - newStates

	# properties such as states or value need to know the role to speak properly,
	# give it as a _ name
	newPropertyValues["_role"] = newPropertyValues.get("role", obj.role)

	# The real states are needed also, as the states entry might be filtered.
	newPropertyValues["_states"] = obj.states
	if "rowNumber" in newPropertyValues or "columnNumber" in newPropertyValues:
		# We're reporting table cell info, so pass the table ID.
		try:
			newPropertyValues["_tableID"] = obj.tableID
		except NotImplementedError:
			pass
	if allowedProperties.get("placeholder", False):
		newPropertyValues["placeholder"] = obj.placeholder
	# When speaking an object due to a focus change, the 'selected' state should not be reported if only one item is selected.
	# This is because that one item will be the focused object, and saying selected is redundant.
	# Rather, 'unselected' will be spoken for an unselected object if 1 or more items are selected.
	states = newPropertyValues.get("states")
	if states is not None and reason == OutputReason.FOCUS:
		if (
			controlTypes.State.SELECTABLE in states
			and controlTypes.State.FOCUSABLE in states
			and controlTypes.State.SELECTED in states
			and obj.selectionContainer
			and obj.selectionContainer.getSelectedItemsCount(2) == 1
		):
			# We must copy the states set and  put it back in newPropertyValues otherwise mutating the original states set in-place will wrongly change the cached states.
			# This would then cause 'selected' to be announced as a change when any other state happens to change on this object in future.
			states = states.copy()
			states.discard(controlTypes.State.SELECTED)
			states.discard(controlTypes.State.SELECTABLE)
			newPropertyValues["states"] = states
	# Get the speech text for the properties we want to speak, and then speak it
	speechSequence = getPropertiesSpeech(reason=reason, **newPropertyValues)

	if speechSequence:
		if _prefixSpeechCommand is not None:
			speechSequence.insert(0, _prefixSpeechCommand)
		from eventHandler import _getFocusLossCancellableSpeechCommand

		cancelCommand = _getFocusLossCancellableSpeechCommand(obj, reason)
		if cancelCommand is not None:
			speechSequence.append(cancelCommand)
	return speechSequence
'''


#: NVDA 2026.2, source/speech/speech.py, _getPlaceholderSpeechIfTextEmpty, word for word.
NVDA_PLACEHOLDER_SPEECH = r'''
def _getPlaceholderSpeechIfTextEmpty(
	obj,
	reason: OutputReason,
) -> Tuple[bool, SpeechSequence]:
	"""Attempt to get speech for placeholder attribute if text for 'obj' is empty. Don't report the placeholder
	 value unless the text is empty, because it is confusing to hear the current value (presumably typed by the
	 user) *and* the placeholder. The placeholder should "disappear" once the user types a value.
	:return: `(True, SpeechSequence)` if text for obj was considered empty and we attempted to get speech for the
		placeholder value. `(False, [])` if text for obj was not considered empty.
	"""
	textEmpty = obj._isTextEmpty
	if textEmpty:
		return True, getObjectPropertiesSpeech(obj, reason=reason, placeholder=True)
	return False, []
'''


#: NVDA 2026.2, source/speech/speech.py, speakObject, word for word.
NVDA_SPEAK_OBJECT = r'''
def speakObject(
	obj,
	reason: OutputReason = OutputReason.QUERY,
	_prefixSpeechCommand: Optional[SpeechCommand] = None,
	priority: Optional[Spri] = None,
):
	sequence = getObjectSpeech(
		obj,
		reason,
		_prefixSpeechCommand,
	)
	if sequence:
		speak(sequence, priority=priority)
'''


#: NVDA 2026.2, source/speech/types.py, _flattenNestedSequences, word for word.
NVDA_FLATTEN = r'''
def _flattenNestedSequences(
	nestedSequences: Union[Iterable[SpeechSequence], GeneratorWithReturn],
) -> Generator[SequenceItemT, Any, Optional[bool]]:
	"""Turns [[a,b,c],[d,e]] into [a,b,c,d,e]"""
	yield from (i for seq in nestedSequences for i in seq)
	if isinstance(nestedSequences, GeneratorWithReturn):
		return nestedSequences.returnValue
	return None
'''


#: NVDA 2026.2, source/controlTypes/role.py, silentRolesOnFocus, word for word.
NVDA_SILENT_ROLES_ON_FOCUS = r'''
silentRolesOnFocus: Set[Role] = {
	Role.PANE,
	Role.ROOTPANE,
	Role.FRAME,
	Role.UNKNOWN,
	Role.APPLICATION,
	Role.TABLECELL,
	Role.LISTITEM,
	Role.MENUITEM,
	Role.CHECKMENUITEM,
	Role.TREEVIEWITEM,
	Role.STATICTEXT,
	Role.BORDER,
}
'''


#: NVDA 2026.2, source/aria.py, landmarkRoles, word for word.
NVDA_LANDMARK_ROLES = r'''
landmarkRoles: Dict[str, str] = {
	# Translators: Reported for the banner landmark, normally found on web pages.
	"banner": pgettext("aria", "banner"),
	# Translators: Reported for the complementary landmark, normally found on web pages.
	"complementary": pgettext("aria", "complementary"),
	# Translators: Reported for the contentinfo landmark, normally found on web pages.
	"contentinfo": pgettext("aria", "content info"),
	# Translators: Reported for the main landmark, normally found on web pages.
	"main": pgettext("aria", "main"),
	# Translators: Reported for the navigation landmark, normally found on web pages.
	"navigation": pgettext("aria", "navigation"),
	# Translators: Reported for the search landmark, normally found on web pages.
	"search": pgettext("aria", "search"),
	# Translators: Reported for the form landmark, normally found on web pages.
	"form": pgettext("aria", "form"),
}
'''


#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject.presType_unavailable, word for word.
NVDA_PRES_TYPE_UNAVAILABLE = r'''
presType_unavailable = "unavailable"
'''


#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject.presType_layout, word for word.
NVDA_PRES_TYPE_LAYOUT = r'''
presType_layout = "layout"
'''


#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject.presType_content, word for word.
NVDA_PRES_TYPE_CONTENT = r'''
presType_content = "content"
'''


#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject._get_presentationType, word for word.
NVDA_PRESENTATION_TYPE = r'''
def _get_presentationType(self):
	states = self.states
	if controlTypes.State.INVISIBLE in states:
		return self.presType_unavailable
	role = self.role
	landmark = self.landmark
	if (role in (controlTypes.Role.LANDMARK, controlTypes.Role.REGION) or landmark) and not config.conf[
		"documentFormatting"
	]["reportLandmarks"]:
		return self.presType_layout

	roleText = self.roleText
	if roleText:
		# If roleText is set, the object is very likely to communicate something relevant to the user.
		return self.presType_content

	# Static text should be content only if it really use usable text
	if role == controlTypes.Role.STATICTEXT:
		text = self.makeTextInfo(textInfos.POSITION_ALL).text
		return self.presType_content if text and not text.isspace() else self.presType_layout

	if role in (
		controlTypes.Role.UNKNOWN,
		controlTypes.Role.PANE,
		controlTypes.Role.TEXTFRAME,
		controlTypes.Role.ROOTPANE,
		controlTypes.Role.LAYEREDPANE,
		controlTypes.Role.SCROLLPANE,
		controlTypes.Role.SPLITPANE,
		controlTypes.Role.SECTION,
		controlTypes.Role.PARAGRAPH,
		controlTypes.Role.TITLEBAR,
		controlTypes.Role.LABEL,
		controlTypes.Role.WHITESPACE,
		controlTypes.Role.BORDER,
	):
		return self.presType_layout
	name = self.name
	description = self.description
	# #15324: Some builds of Microsoft Office expose a space character as the name of unlabeled groupings.
	# trying to force NVDA to announce them.
	if name and name.isspace():
		name = None
	if description and description.isspace():
		description = None
	if not name and not description:
		if role in (
			controlTypes.Role.WINDOW,
			controlTypes.Role.PANEL,
			controlTypes.Role.PROPERTYPAGE,
			controlTypes.Role.TEXTFRAME,
			controlTypes.Role.GROUPING,
			controlTypes.Role.OPTIONPANE,
			controlTypes.Role.INTERNALFRAME,
			controlTypes.Role.FORM,
			controlTypes.Role.TABLEBODY,
			controlTypes.Role.REGION,
		):
			return self.presType_layout
		if role == controlTypes.Role.TABLE and not config.conf["documentFormatting"]["reportTables"]:
			return self.presType_layout
		if role in (
			controlTypes.Role.TABLEROW,
			controlTypes.Role.TABLECOLUMN,
			controlTypes.Role.TABLECELL,
		) and (
			not config.conf["documentFormatting"]["reportTables"]
			or not config.conf["documentFormatting"]["reportTableCellCoords"]
		):
			return self.presType_layout
	return self.presType_content
'''


#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject._get_isPresentableFocusAncestor, word for word.
NVDA_PRESENTABLE_ANCESTOR = r'''
def _get_isPresentableFocusAncestor(self):
	"""Determine if this object should be presented to the user in the focus ancestry.
	@return: C{True} if it should be presented in the focus ancestry, C{False} if not.
	@rtype: bool
	"""
	if self.presentationType in (self.presType_layout, self.presType_unavailable):
		return False
	if self.role in (
		controlTypes.Role.TREEVIEWITEM,
		controlTypes.Role.LISTITEM,
		controlTypes.Role.PROGRESSBAR,
		controlTypes.Role.EDITABLETEXT,
	):
		return False
	return True
'''


#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject._get_roleText, word for word.
NVDA_ROLE_TEXT = r'''
def _get_roleText(self) -> typing.Optional[str]:
	"""
	A custom role string for this object, which is used for braille and speech presentation, which will override the standard label for this object's role property.
	No string is provided by default, meaning that NVDA will fall back to using role.
	Examples of where this property might be overridden are shapes in Powerpoint, or ARIA role descriptions.
	"""
	if self.landmark and self.landmark in aria.landmarkRoles:
		return f"{aria.landmarkRoles[self.landmark]} {controlTypes.Role.LANDMARK.displayString}"
	return None
'''


#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject._get_landmark, word for word.
NVDA_OBJECT_LANDMARK = r'''
def _get_landmark(self) -> typing.Optional[str]:
	"""If this object represents an ARIA landmark, fetches the ARIA landmark role.
	@return: ARIA landmark role else None
	"""
	return None
'''


#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject._get__isTextEmpty, word for word.
NVDA_IS_TEXT_EMPTY = r'''
def _get__isTextEmpty(self):
	"""
	@return C{True} if the text contained in the object is considered empty by the underlying implementation. In most cases this will match {isCollapsed}, however some implementations may consider a single space or line feed as an empty range.
	"""
	ti = self.makeTextInfo(textInfos.POSITION_FIRST)
	ti.move(textInfos.UNIT_CHARACTER, 1, endPoint="end")
	return ti.isCollapsed
'''


#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject.reportFocus, word for word.
NVDA_REPORT_FOCUS = r'''
def reportFocus(self):
	"""Announces this object in a way suitable such that it gained focus."""
	speech.speakObject(self, reason=controlTypes.OutputReason.FOCUS)
'''


#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject.event_focusEntered, word for word.
NVDA_FOCUS_ENTERED = r'''
def event_focusEntered(self):
	if self.role in (controlTypes.Role.MENUBAR, controlTypes.Role.POPUPMENU, controlTypes.Role.MENUITEM):
		speech.cancelSpeech()
		return
	if self.isPresentableFocusAncestor:
		speech.speakObject(self, reason=controlTypes.OutputReason.FOCUSENTERED)
'''


#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject.event_gainFocus, word for word.
NVDA_OBJECT_GAIN_FOCUS = r'''
def event_gainFocus(self):
	"""
	This code is executed if a gain focus event is received by this object.
	"""
	self.reportFocus()
	braille.handler.handleGainFocus(self)
	brailleInput.handler.handleGainFocus(self)
	vision.handler.handleGainFocus(self)
'''


#: NVDA 2026.2, source/NVDAObjects/IAccessible/ia2Web.py, Ia2Web._get_placeholder, word for word.
NVDA_IA2WEB_PLACEHOLDER = r'''
def _get_placeholder(self):
	placeholder = self.IA2Attributes.get("placeholder", None)
	return placeholder
'''


#: NVDA 2026.2, source/NVDAObjects/IAccessible/ia2Web.py, Ia2Web._get_isPresentableFocusAncestor, word for word.
NVDA_IA2WEB_PRESENTABLE_ANCESTOR = r'''
def _get_isPresentableFocusAncestor(self):
	if self.role == controlTypes.Role.TABLEROW:
		# It is not useful to present IAccessible2 table rows in the focus ancestry as  cells contain row and column information anyway.
		# Also presenting the rows would cause duplication of information
		return False
	return super(Ia2Web, self).isPresentableFocusAncestor
'''


#: NVDA 2026.2, source/NVDAObjects/IAccessible/ia2Web.py, Ia2Web._get_roleText, word for word.
NVDA_IA2WEB_ROLE_TEXT = r'''
def _get_roleText(self):
	roleText = self.IA2Attributes.get("roledescription")
	if roleText:
		return roleText
	return super().roleText
'''


#: NVDA 2026.2, source/NVDAObjects/IAccessible/ia2Web.py, Ia2Web._get_landmark, word for word.
NVDA_IA2WEB_LANDMARK = r'''
def _get_landmark(self):
	xmlRoles = self.IA2Attributes.get("xml-roles", "").split(" ")
	landmark = next((xr for xr in xmlRoles if xr in aria.landmarkRoles), None)
	if landmark and self.IAccessibleRole != IA2.IA2_ROLE_LANDMARK and landmark != xmlRoles[0]:
		# Ignore the landmark role
		landmark = None
	if landmark:
		return landmark
	return super().landmark
'''


#: NVDA 2026.2, source/browseMode.py, BrowseModeDocumentTreeInterceptor._shouldIgnoreFocus, word for word.
NVDA_SHOULD_IGNORE_FOCUS = r'''
def _shouldIgnoreFocus(self, obj):
	"""Determines whether focus on a given object should be ignored.
	@param obj: The object in question.
	@type obj: L{NVDAObjects.NVDAObject}
	@return: C{True} if focus on L{obj} should be ignored, C{False} otherwise.
	@rtype: bool
	"""
	return False
'''


#: NVDA 2026.2, source/browseMode.py, BrowseModeDocumentTreeInterceptor._postGainFocus, word for word.
NVDA_POST_GAIN_FOCUS = r'''
def _postGainFocus(self, obj):
	"""Executed after a gainFocus within the browseMode document.
	This will not be executed if L{event_gainFocus} determined that it should abort and call nextHandler.
	@param obj: The object that gained focus.
	@type obj: L{NVDAObjects.NVDAObject}
	"""
'''


#: NVDA 2026.2, source/browseMode.py, BrowseModeDocumentTreeInterceptor._replayFocusEnteredEvents, word for word.
NVDA_REPLAY_FOCUS_ENTERED = r'''
def _replayFocusEnteredEvents(self):
	# We blocked the focusEntered events because we were in browse mode,
	# but now that we've switched to focus mode, we need to fire them.
	for parent in api.getFocusAncestors()[api.getFocusDifferenceLevel() :]:
		try:
			parent.event_focusEntered()
		except:  # noqa: E722
			log.exception("Error executing focusEntered event: %s" % parent)
'''


#: NVDA 2026.2, source/browseMode.py, BrowseModeDocumentTreeInterceptor.event_gainFocus, word for word.
NVDA_DOCUMENT_GAIN_FOCUS = r'''
def event_gainFocus(self, obj, nextHandler):
	enteringFromOutside = self._enteringFromOutside
	self._enteringFromOutside = False
	if not self.isReady:
		if self.passThrough:
			self._replayFocusEnteredEvents()
			nextHandler()
		return
	# If a control has been expanded by the collapseOrExpandControl script, and this focus event is for it,
	# disable passThrough and report the control, as the control has obviously been collapsed again.
	# Note that whether or not this focus event was for that control, the last expanded control is forgotten, so that only the next focus event for the browseMode document can handle the collapsed control.
	lastExpandedControl = self.currentExpandedControl
	self.currentExpandedControl = None
	if self.passThrough and obj == lastExpandedControl:
		self.passThrough = False
		reportPassThrough(self)
		nextHandler()
		return
	if enteringFromOutside and not self.passThrough and self._lastFocusObj == obj:
		# We're entering the document from outside (not returning from an inside object/application; #3145)
		# and this was the last non-root node with focus, so ignore this focus event.
		# Otherwise, if the user switches away and back to this document, the cursor will jump to this node.
		# This is not ideal if the user was positioned over a node which cannot receive focus.
		# #17501: Even though we're ignoring this event, we still need to call
		# _postGainFocus. This does things such as initialize auto select detection
		# for editable text controls. Without this, the focus object might not
		# behave correctly (e.g. text selection changes might not be reported) if the
		# user switches to focus mode with this object still focused.
		self._postGainFocus(obj)
		return
	if obj == self.rootNVDAObject:
		if self.passThrough:
			self._replayFocusEnteredEvents()
			return nextHandler()
		return
	if not self.passThrough and self._shouldIgnoreFocus(obj):
		return

	# If the previous focus object was removed, we might hit a false positive for overlap detection.
	# Track the previous focus target so that we can account for this scenario.
	previousFocusObjIsDefunct = False
	if self._lastFocusObj:
		try:
			states = self._lastFocusObj.states
			previousFocusObjIsDefunct = controlTypes.State.DEFUNCT in states
		except Exception:
			log.debugWarning(
				"Error fetching states when checking for defunct object. Treating object as defunct anyway.",
				exc_info=True,
			)
			previousFocusObjIsDefunct = True

	self._lastFocusObj = obj

	try:
		focusInfo = self.makeTextInfo(obj)
	except:  # noqa: E722
		# This object is not in the treeInterceptor, even though it resides beneath the document.
		# Automatic pass through should be enabled in certain circumstances where this occurs.
		if not self.passThrough and self.shouldPassThrough(obj, reason=OutputReason.FOCUS):
			self.passThrough = True
			reportPassThrough(self)
			self._replayFocusEnteredEvents()
		return nextHandler()

	# Save off and clear any previous object that was focused by NVDA
	# and waiting on a focus event.
	objPendingFocusBeforeActivate = self._objPendingFocusBeforeActivate
	self._objPendingFocusBeforeActivate = None

	# We do not want to speak the new focus and update the caret if...
	if not self._hadFirstGainFocus or previousFocusObjIsDefunct:
		# still initializing  or the old focus is dead.
		isOverlapping = False
	else:
		# if this focus event was caused by NVDA setting the focus itself
		# due to activation or applications key etc.
		isOverlapping = obj == objPendingFocusBeforeActivate

	if not isOverlapping:
		# The virtual caret is not within the focus node.
		oldPassThrough = self.passThrough
		passThrough = self.shouldPassThrough(obj, reason=OutputReason.FOCUS)
		if not oldPassThrough and (passThrough or sayAll.SayAllHandler.isRunning()):
			# If pass-through is disabled, cancel speech, as a focus change should cause page reading to stop.
			# This must be done before auto-pass-through occurs, as we want to stop page reading even if pass-through will be automatically enabled by this focus change.
			speech.cancelSpeech()
		self.passThrough = passThrough
		if not self.passThrough:
			# We read the info from the browseMode document  instead of the control itself.
			speech.speakTextInfo(focusInfo, reason=OutputReason.FOCUS)
			# However, we still want to update the speech property cache so that property changes will be spoken properly.
			speech.speakObject(obj, controlTypes.OutputReason.ONLYCACHE)
			# As we do not call nextHandler which would trigger the vision framework to handle gain focus,
			# we need to call it manually here.
			vision.handler.handleGainFocus(obj)
		else:
			# Although we are going to speak the object rather than textInfo content, we still need to silently speak the textInfo content so that the textInfo speech cache is updated correctly.
			# Not doing this would cause  later browseMode speaking to either not speak controlFields it had entered, or speak controlField exits after having already exited.
			# See #7435 for a discussion on this.
			speech.speakTextInfo(focusInfo, reason=OutputReason.ONLYCACHE)
			self._replayFocusEnteredEvents()
			nextHandler()
		focusInfo.collapse()
		if self._focusEventMustUpdateCaretPosition:
			self._set_selection(focusInfo, reason=OutputReason.FOCUS)
	else:
		# The virtual caret was already at the focused node.
		if not self.passThrough:
			# This focus change was caused by a virtual caret movement, so don't speak the focused node to avoid double speaking.
			# However, we still want to update the speech property cache so that property changes will be spoken properly.
			speech.speakObject(obj, OutputReason.ONLYCACHE)
			if (
				objPendingFocusBeforeActivate
				and obj == objPendingFocusBeforeActivate
				and obj is not objPendingFocusBeforeActivate
			):
				# With auto focus focusable elements disabled, when the user activates
				# an element (e.g. by pressing enter) or presses a key which we pass
				# through (e.g. control+enter), we call _focusLastFocusableObject.
				# However, the activation/key press might cause a property change
				# before we get the focus event, so NVDA's normal reporting of
				# changes to the focus won't pick it up.
				# The speech property cache on _objPendingFocusBeforeActivate reflects
				# the properties before the activation/key, so use that to speak any
				# changes.
				speech.speakObject(
					objPendingFocusBeforeActivate,
					OutputReason.CHANGE,
				)
		else:
			self._replayFocusEnteredEvents()
			return nextHandler()

	self._postGainFocus(obj)
'''


#: NVDA 2026.2, source/virtualBuffers/gecko_ia2.py, Gecko_ia2.getIdentifierFromNVDAObject, word for word.
NVDA_GECKO_IDENTIFIER = r'''
def getIdentifierFromNVDAObject(self, obj):
	docHandle = obj.windowHandle
	ID = obj.IA2UniqueID
	return docHandle, ID
'''


#: NVDA 2026.2, source/virtualBuffers/gecko_ia2.py, Gecko_ia2._shouldIgnoreFocus, word for word.
NVDA_GECKO_SHOULD_IGNORE_FOCUS = r'''
def _shouldIgnoreFocus(self, obj):
	if obj.role == controlTypes.Role.DOCUMENT and controlTypes.State.EDITABLE not in obj.states:
		return True
	return super(Gecko_ia2, self)._shouldIgnoreFocus(obj)
'''


#: NVDA 2026.2, source/api.py, getFocusAncestors, word for word.
NVDA_FOCUS_ANCESTORS = r'''
def getFocusAncestors():
	"""An array of NVDAObjects that are all parents of the object which currently has focus"""
	return globalVars.focusAncestors
'''


#: NVDA 2026.2, source/api.py, getFocusDifferenceLevel, word for word.
NVDA_FOCUS_DIFFERENCE_LEVEL = r'''
def getFocusDifferenceLevel():
	return globalVars.focusDifferenceLevel
'''


# -- the imitation NVDA --------------------------------------------------------------------------------------------

nvdaCode = v125.nvdaCode
nvdaMethods = v125.nvdaMethods
nvdaLog = v125.nvdaLog
notHere = v125.notHere

Role = v125.displayEnum("Role", v125.NVDA_ROLES)
State = v125.displayEnum("State", v125.NVDA_STATES, negative=True)
OutputReason = nvdaCode(v125.NVDA_OUTPUT_REASON, "OutputReason", {"Enum": enum.Enum, "auto": enum.auto})
DescriptionFrom = nvdaCode(v125.NVDA_DESCRIPTION_FROM, "DescriptionFrom", {"Enum": enum.Enum, "auto": enum.auto})
IsCurrent = v125.IsCurrent

#: NVDA's settings: its defaults, with what the tester changed (the config in the log: the same as for issue 21).
config = types.ModuleType("config")
config.conf = v125.testersConfig()

controlTypes = types.ModuleType("controlTypes")
controlTypes.Role, controlTypes.State, controlTypes.OutputReason = Role, State, OutputReason
controlTypes.DescriptionFrom, controlTypes.IsCurrent = DescriptionFrom, IsCurrent
stateScope = {"Role": Role, "State": State, "OutputReason": OutputReason, "config": config}
controlTypes.STATES_SORTED = nvdaCode(v125.NVDA_STATES_SORTED, "STATES_SORTED", stateScope)
controlTypes.STATES_LINK_TYPE = nvdaCode(v125.NVDA_STATES_LINK_TYPE, "STATES_LINK_TYPE", stateScope)
nvdaCode(v125.NVDA_CLICKABLE_ROLES, "clickableRoles", stateScope)
controlTypes.silentValuesForRoles = nvdaCode(v125.NVDA_SILENT_VALUES, "silentValuesForRoles", stateScope)
controlTypes.silentRolesOnFocus = nvdaCode(NVDA_SILENT_ROLES_ON_FOCUS, "silentRolesOnFocus", stateScope)
nvdaCode(v125.NVDA_POSITIVE_STATES, "_processPositiveStates", stateScope)
nvdaCode(v125.NVDA_NEGATIVE_STATES, "_processNegativeStates", stateScope)
controlTypes.processAndLabelStates = nvdaCode(v125.NVDA_LABEL_STATES, "processAndLabelStates", stateScope)

aria = types.ModuleType("aria")
aria.landmarkRoles = nvdaCode(NVDA_LANDMARK_ROLES, "landmarkRoles", {"pgettext": lambda context, text: text})

textInfos = types.ModuleType("textInfos")
fieldScope = {"controlTypes": controlTypes, "OutputReason": OutputReason}
textInfos.Field = nvdaCode(v125.NVDA_FIELD, "Field", fieldScope)
textInfos.FormatField = nvdaCode(v125.NVDA_FORMAT_FIELD, "FormatField", fieldScope)
textInfos.ControlField = nvdaCode(v125.NVDA_CONTROL_FIELD, "ControlField", fieldScope)
textInfos.FieldCommand = nvdaCode(v125.NVDA_FIELD_COMMAND, "FieldCommand", fieldScope)
textInfos.UNIT_CHARACTER, textInfos.UNIT_WORD, textInfos.UNIT_LINE = "character", "word", "line"
textInfos.UNIT_PARAGRAPH, textInfos.UNIT_CELL = "paragraph", "cell"
textInfos.POSITION_FIRST, textInfos.POSITION_CARET, textInfos.POSITION_SELECTION = "first", "caret", "selection"


class TextInfo:
	"""NVDA's textInfos.TextInfo, as far as NVDA's speech asks it: NVDA's own getControlFieldSpeech. A web page's text
	has no formatting NVDA says as it comes."""

	getControlFieldSpeech = nvdaCode(
		v125.NVDA_TEXT_INFO_CONTROL_FIELD_SPEECH,
		"getControlFieldSpeech",
		{"_logBadSequenceTypes": lambda sequence: True},
	)

	def getFormatFieldSpeech(self, attrs, attrsCache=None, formatConfig=None, reason=None, unit=None, extraDetail=False, initialFormat=False):
		return []


textInfos.TextInfo = TextInfo

SpeechCommand, LangChangeCommand, EndUtteranceCommand = v125.SpeechCommand, v125.LangChangeCommand, v125.EndUtteranceCommand


class CancellableSpeech(SpeechCommand):
	"""NVDA's speech.commands._CancellableSpeechCommand, "CancellableSpeech (still valid)" in the log."""


#: What NVDA said, as its log shows it: each utterance's words.
spoken = []


def speak(sequence, priority=None):
	"""NVDA's speech.speak, as its log's "Speaking" line has it: the words, without the empty ones speak() leaves out."""
	spoken.append([item for item in sequence if isinstance(item, str) and item])


#: NVDA's speech/speech.py, in a module of its own as in NVDA: what the assistant puts in NVDA's place goes there, and
#: NVDA's functions find it there.
speechModule = types.ModuleType("speech.speech")
speechScope = vars(speechModule)
speechScope.update(
	{
		"config": config,
		"controlTypes": controlTypes,
		"textInfos": textInfos,
		"OutputReason": OutputReason,
		"State": State,
		"weakref": weakref,
		"itertools": itertools,
		"unicodeNormalize": lambda text: unicodedata.normalize("NFKC", text),
		"languageHandling": types.SimpleNamespace(
			shouldMakeLangChangeCommand=nvdaCode(v125.NVDA_LANG_CHANGE, "shouldMakeLangChangeCommand", {"config": config}),
		),
		"LangChangeCommand": LangChangeCommand,
		"EndUtteranceCommand": EndUtteranceCommand,
		"SpeechCommand": SpeechCommand,
		"ReportLineIndentation": v125.ReportLineIndentation,
		"ReportTableHeaders": v125.ReportTableHeaders,
		"splitTextIndentation": notHere,
		"getIndentationSpeech": notHere,
		"getSpellingSpeech": notHere,
		"getSingleCharDescription": notHere,
		"_extendSpeechSequence_addMathForTextInfo": notHere,
		# No text is selected in these fields.
		"getPreselectedTextSpeech": notHere,
		# The tester's computer isn't locked.
		"objectBelowLockScreenAndWindowsIsLocked": lambda obj, *args, **kwargs: False,
		"aria": aria,
		"log": nvdaLog,
		"_": lambda text: text,
		"ngettext": lambda one, many, count: one if count == 1 else many,
		"types": types.SimpleNamespace(logBadSequenceTypes=lambda sequence, raiseExceptionOnError=False: True),
		"logBadSequenceTypes": lambda sequence, raiseExceptionOnError=False: True,
		# NVDA's speech.shortcutKeys.getKeyboardShortcutsSpeech says nothing for a field without a shortcut key.
		"getKeyboardShortcutsSpeech": lambda keyboardShortcut: [keyboardShortcut] if keyboardShortcut else [],
		"_speechState": types.SimpleNamespace(oldTableID=None, oldRowNumber=None, oldRowSpan=None, oldColumnNumber=None, oldColumnSpan=None, oldTreeLevel=None),
		"speak": speak,
		"Iterable": object,
	},
)
for source, name in (
	(v125.NVDA_GENERATOR_WITH_RETURN, "GeneratorWithReturn"),
	(v125.NVDA_BLANK_CHUNK_CHARS, "BLANK_CHUNK_CHARS"),
	(v125.NVDA_IS_BLANK, "isBlank"),
	(v125.NVDA_SPEAK_TEXT_INFO_STATE, "SpeakTextInfoState"),
	(v125.NVDA_LINE_END_CHARS, "LINE_END_CHARS"),
	(v125.NVDA_IS_CONTROL_END, "_isControlEndFieldCommand"),
	(v125.NVDA_CONSIDER_SPELLING, "_getTextInfoSpeech_considerSpelling"),
	(v125.NVDA_UPDATE_CACHE, "_getTextInfoSpeech_updateCache"),
	(v125.NVDA_TEXT_INFO_SPEECH, "getTextInfoSpeech"),
	(v125.NVDA_SPEAK_TEXT_INFO, "speakTextInfo"),
	(v125.NVDA_CONTENT_FIRST, "_shouldSpeakContentFirst"),
	(v125.NVDA_ROW_AND_COLUMN_COUNT, "_rowAndColumnCountText"),
	(v125.NVDA_PROPERTIES_SPEECH, "getPropertiesSpeech"),
	(v125.NVDA_CONTROL_FIELD_SPEECH, "getControlFieldSpeech"),
	(NVDA_FLATTEN, "_flattenNestedSequences"),
	(NVDA_ALLOWED_PROPS, "_objectSpeech_calculateAllowedProps"),
	(NVDA_OBJECT_PROPERTIES_SPEECH, "getObjectPropertiesSpeech"),
	(NVDA_PLACEHOLDER_SPEECH, "_getPlaceholderSpeechIfTextEmpty"),
	(NVDA_OBJECT_SPEECH, "getObjectSpeech"),
	(NVDA_SPEAK_OBJECT, "speakObject"),
):
	nvdaCode(source, name, speechScope)

#: NVDA's own, to check what the assistant puts in their place and gives back.
NVDA_OWN = {name: speechScope[name] for name in (formFields.OBJECT_SPEECH, formFields.PROPERTIES_SPEECH, formFields.PLACEHOLDER_SPEECH)}

#: NVDA's speech package: its speech.speech module, and the functions it takes from it as NVDA starts.
speechPackage = types.ModuleType("speech")
speechPackage.speech = speechModule
for name in ("getObjectSpeech", "speakObject", "speakTextInfo", "getTextInfoSpeech", "getControlFieldSpeech", "getPropertiesSpeech"):
	setattr(speechPackage, name, speechScope[name])
#: How often NVDA cut speech short.
cancelled = []
speechPackage.cancelSpeech = lambda: cancelled.append(True)

eventHandler = types.ModuleType("eventHandler")


def _getFocusLossCancellableSpeechCommand(obj, reason):
	"""NVDA's eventHandler._getFocusLossCancellableSpeechCommand: the focus's speech gets a command that cuts it short
	once the focus has moved on ("CancellableSpeech (still valid)" in the log); nothing else gets one."""
	return CancellableSpeech() if reason == OutputReason.FOCUS else None


eventHandler._getFocusLossCancellableSpeechCommand = _getFocusLossCancellableSpeechCommand

#: NVDA's globalVars, as far as the focus goes, and NVDA's api functions that read it.
globalVars = types.SimpleNamespace(focusObject=None, focusAncestors=[], focusDifferenceLevel=0)
api = types.ModuleType("api")
vars(api)["globalVars"] = globalVars
nvdaCode(NVDA_FOCUS_ANCESTORS, "getFocusAncestors", vars(api))
nvdaCode(NVDA_FOCUS_DIFFERENCE_LEVEL, "getFocusDifferenceLevel", vars(api))
api.getFocusObject = lambda: globalVars.focusObject

#: Braille, braille input and vision take the focus too; nothing of theirs is checked here.
handlers = types.SimpleNamespace(handler=types.SimpleNamespace(handleGainFocus=lambda obj: None))


class AutoProperties(type):
	"""NVDA's baseObject.AutoPropertyObject, as far as these objects go: a method _get_x makes a property x."""

	def __new__(metaclass, name, bases, namespace):
		for key, value in list(namespace.items()):
			if key.startswith("_get_") and callable(value):
				namespace[key[len("_get_") :]] = property(value)
		return super().__new__(metaclass, name, bases, namespace)


class AutoPropertyObject(metaclass=AutoProperties):
	pass


objectScope = {
	"controlTypes": controlTypes,
	"config": config,
	"textInfos": textInfos,
	"aria": aria,
	"speech": speechPackage,
	"braille": handlers,
	"brailleInput": handlers,
	"vision": handlers,
	"typing": typing,
}
NVDAObject = nvdaMethods(
	"NVDAObject",
	[AutoPropertyObject],
	[
		NVDA_PRES_TYPE_UNAVAILABLE,
		NVDA_PRES_TYPE_LAYOUT,
		NVDA_PRES_TYPE_CONTENT,
		NVDA_PRESENTATION_TYPE,
		NVDA_PRESENTABLE_ANCESTOR,
		NVDA_ROLE_TEXT,
		NVDA_OBJECT_LANDMARK,
		NVDA_IS_TEXT_EMPTY,
		NVDA_REPORT_FOCUS,
		NVDA_FOCUS_ENTERED,
		NVDA_OBJECT_GAIN_FOCUS,
	],
	objectScope,
)
#: IAccessible2's role for a landmark (IA2_ROLE_LANDMARK, IA2CommonTypes.idl).
IA2 = types.SimpleNamespace(IA2_ROLE_LANDMARK=0x436)
Ia2Web = nvdaMethods(
	"Ia2Web",
	[NVDAObject],
	[NVDA_IA2WEB_PLACEHOLDER, NVDA_IA2WEB_PRESENTABLE_ANCESTOR, NVDA_IA2WEB_ROLE_TEXT, NVDA_IA2WEB_LANDMARK],
	dict(objectScope, IA2=IA2),
)

#: Edge's window for the page (Chrome_RenderWidgetHostHWND).
EDGE_WINDOW = 0x2A0C42


class ScreenObject:
	"""What a program tells NVDA about one of its objects, and the text it holds."""

	#: What NVDA asks a web object that isn't a table cell, which NVDA's IAccessible answers with NotImplementedError.
	NOT_A_CELL = frozenset(
		(
			"cellCoordsText",
			"rowNumber",
			"presentationalRowNumber",
			"columnNumber",
			"presentationalColumnNumber",
			"rowCount",
			"presentationalRowCount",
			"columnCount",
			"presentationalColumnCount",
			"rowHeaderText",
			"columnHeaderText",
			"rowSpan",
			"columnSpan",
		),
	)

	def __init__(self, uniqueID, role, name="", states=(), attributes=None, description="", text="", IAccessibleRole=None):
		self.windowHandle, self.IA2UniqueID = EDGE_WINDOW, uniqueID
		self.role, self.name, self._states = role, name, frozenset(states)
		self.IA2Attributes = dict(attributes or {})
		self.IAccessibleRole = IAccessibleRole
		self.description = description
		self.descriptionFrom = DescriptionFrom.ARIA_DESCRIBED_BY if description else DescriptionFrom.UNKNOWN
		self.text = text
		self.value = ""
		self.keyboardShortcut = ""
		self.positionInfo = {}
		self.isCurrent = IsCurrent.NO
		self.annotations = None
		self.errorMessage = None
		self._hasNavigableText = role == Role.EDITABLETEXT
		self.treeInterceptor = None

	def __getattr__(self, name):
		if name in ScreenObject.NOT_A_CELL:
			raise NotImplementedError(name)
		raise AttributeError(name)

	@property
	def states(self):
		return set(self._states)

	def __eq__(self, other):
		"""NVDA's IAccessible._isEqual: the same object of the same window."""
		return isinstance(other, ScreenObject) and (self.windowHandle, self.IA2UniqueID) == (other.windowHandle, other.IA2UniqueID)

	__hash__ = object.__hash__

	def makeTextInfo(self, position):
		# The caret is at the start of the field, with nothing selected, as it is when the focus moves in.
		return FieldText(self, 0, 0)

	def event_gainFocus(self):
		# NVDA's NVDAObject.event_gainFocus, as a bound method nextHandler can call.
		return NVDAObject.event_gainFocus(self)


class WebObject(ScreenObject, Ia2Web):
	"""An object of Edge's page, as NVDA gets it through IAccessible2 (NVDAObjects.IAccessible.chromium.Chromium)."""


class WindowsObject(ScreenObject, NVDAObject):
	"""An object NVDA doesn't get through IAccessible2, such as a Windows edit field: it has no placeholder
	(NVDAObject.placeholder)."""

	placeholder = None


class FieldText(TextInfo):
	"""NVDA's IA2TextTextInfo for an edit field's own text: one line, no fields in it."""

	def __init__(self, obj, start, end):
		self.obj, self.start, self.end = obj, start, end

	@property
	def isCollapsed(self):
		return self.start == self.end

	@property
	def text(self):
		return self.obj.text[self.start : self.end]

	def copy(self):
		return FieldText(self.obj, self.start, self.end)

	def collapse(self, end=False):
		if end:
			self.start = self.end
		else:
			self.end = self.start

	def expand(self, unit):
		# One line: the whole text.
		self.start, self.end = 0, len(self.obj.text)

	def move(self, unit, direction, endPoint=None):
		assert unit == textInfos.UNIT_CHARACTER and direction == 1 and endPoint == "end"
		moved = 1 if self.end < len(self.obj.text) else 0
		self.end += moved
		return moved

	def getTextWithFields(self, formatConfig=None):
		return [self.text] if self.text else []


class PageText(TextInfo):
	"""A range of the page in NVDA's virtual buffer (virtualBuffers.gecko_ia2.Gecko_ia2_TextInfo). ``parts`` is a list of
	fields (dicts, as Edge's virtual buffer gives them) and strings; a field holds what follows it, up to the end."""

	def __init__(self, obj, parts):
		self.obj, self.parts = obj, list(parts)

	def _normalizeControlField(self, attrs):
		"""As NVDA 2026.2's Gecko_ia2_TextInfo._normalizeControlField does for what is on this page: the role and
		states, and the placeholder of a field that holds only a space (_getPlaceholderAttribute)."""
		attrs["role"] = attrs.pop("IAccessible::role")
		attrs["states"] = set(attrs.pop("IAccessible::states", ()))
		placeholder = attrs.get("IAccessible2::attribute_placeholder")
		if placeholder:
			attrs["placeholder"] = placeholder
		return attrs

	def getTextWithFields(self, formatConfig=None):
		commands = []
		open_ = 0
		for part in self.parts:
			if isinstance(part, str):
				commands.append(part)
			else:
				commands.append(textInfos.FieldCommand("controlStart", textInfos.ControlField(self._normalizeControlField(dict(part)))))
				open_ += 1
		commands.extend(textInfos.FieldCommand("controlEnd", None) for _ in range(open_))
		return commands

	def collapse(self, end=False):
		self.parts = [part for part in self.parts if not isinstance(part, str)]


documentScope = {
	"controlTypes": controlTypes,
	"OutputReason": OutputReason,
	"speech": speechPackage,
	"api": api,
	"log": nvdaLog,
	"vision": handlers,
	"sayAll": types.SimpleNamespace(SayAllHandler=types.SimpleNamespace(isRunning=lambda: False)),
	"reportPassThrough": lambda treeInterceptor, *args, **kwargs: None,
}
#: NVDA's browseMode.BrowseModeDocumentTreeInterceptor: how a web page takes a focus event.
BrowseModeDocumentTreeInterceptor = nvdaMethods(
	"BrowseModeDocumentTreeInterceptor",
	[],
	[NVDA_SHOULD_IGNORE_FOCUS, NVDA_POST_GAIN_FOCUS, NVDA_REPLAY_FOCUS_ENTERED, NVDA_DOCUMENT_GAIN_FOCUS],
	documentScope,
)
#: NVDA's virtualBuffers.gecko_ia2.Gecko_ia2, the virtual buffer of Edge's page.
Gecko_ia2 = nvdaMethods("Gecko_ia2", [BrowseModeDocumentTreeInterceptor], [NVDA_GECKO_IDENTIFIER, NVDA_GECKO_SHOULD_IGNORE_FOCUS], documentScope)


class EdgePage(Gecko_ia2):
	"""A page in Edge, in browse mode: NVDA's virtual buffer of it, with the text of each object on it."""

	def __init__(self, root, lines):
		self.rootNVDAObject = root
		#: {IA2UniqueID: the parts of the page's text for the object}
		self.lines = lines
		self.isReady = True
		self.passThrough = False
		self.currentExpandedControl = None
		self._enteringFromOutside = False
		self._lastFocusObj = None
		self._objPendingFocusBeforeActivate = None
		self._hadFirstGainFocus = True
		self._focusEventMustUpdateCaretPosition = True
		self.caret = None

	def makeTextInfo(self, obj):
		return PageText(self, self.lines[obj.IA2UniqueID])

	def shouldPassThrough(self, obj, reason=None):
		# NVDA's BrowseModeDocumentTreeInterceptor.shouldPassThrough, for what is on this page: an editable field that
		# isn't read-only puts NVDA in focus mode.
		return obj.role == Role.EDITABLETEXT and State.READONLY not in obj.states

	def _set_selection(self, info, reason=None):
		self.caret = info


class Plugin:
	"""The assistant's global plugin, as far as its event_gainFocus goes: its own, with nothing else of it running."""

	_autoFormsMode = None
	_changeRepeats = None
	event_gainFocus = jawsMigrator.GlobalPlugin.event_gainFocus

	def __init__(self, formFieldsModule=None):
		self._formFields = formFieldsModule

	def _checkSleep(self, obj):
		pass


# -- the tester's pages ------------------------------------------------------------------------------------------

EDIT_STATES = (State.FOCUSABLE, State.EDITABLE, State.MULTILINE)
REPLY = "Join the conversation"
#: What the tester typed into the box (their log).
TYPED = "If you know you have a problem with a model don't activate them until this is resolved."


def field(role, uniqueID, states=(), **attributes):
	"""A field of the virtual buffer, as Edge gives it: its role, states and IAccessible2 attributes, and which object it
	is (controlIdentifier_docHandle and controlIdentifier_ID)."""
	attrs = {
		"IAccessible::role": role,
		"IAccessible::states": set(states),
		"controlIdentifier_docHandle": str(EDGE_WINDOW),
		"controlIdentifier_ID": str(uniqueID),
	}
	attrs.update(attributes)
	return attrs


class RedditPost:
	"""The tester's reddit post in Edge: the page, its banner with a link, its main landmark, and in it the reply box.

	Before Enter, the box is "Join the conversation" in grey, which browse mode shows as an empty field with that
	placeholder. Enter makes the page put its editor in its place, with the focus, as the log shows (NVDA got errors
	from the object that went away): an empty box whose name Edge made from the placeholder."""

	def __init__(self):
		self.root = WebObject(1, Role.DOCUMENT, name="Ported line totally dead on S21 : r/Visible", states=(State.FOCUSABLE, State.READONLY))
		self.banner = WebObject(5, Role.LANDMARK, attributes={"xml-roles": "banner"}, IAccessibleRole=IA2.IA2_ROLE_LANDMARK)
		self.home = WebObject(6, Role.LINK, name="Home", states=(State.FOCUSABLE, State.LINKED))
		self.main = WebObject(2, Role.LANDMARK, attributes={"xml-roles": "main"}, IAccessibleRole=IA2.IA2_ROLE_LANDMARK)
		self.collapsed = WebObject(30, Role.EDITABLETEXT, states=EDIT_STATES, attributes={"placeholder": REPLY})
		self.box = WebObject(
			40,
			Role.EDITABLETEXT,
			name=REPLY,
			states=EDIT_STATES + (State.FOCUSED,),
			attributes={"name-from": "placeholder", "explicit-name": "true", "xml-roles": "textbox"},
		)
		mainField = field(Role.LANDMARK, 2, landmark="main")
		bannerField = field(Role.LANDMARK, 5, landmark="banner")
		self.page = EdgePage(
			self.root,
			{
				6: [bannerField, field(Role.LINK, 6, (State.FOCUSABLE, State.LINKED), name="Home"), "Home"],
				30: [mainField, field(Role.EDITABLETEXT, 30, EDIT_STATES, **{"IAccessible2::attribute_placeholder": REPLY}), " "],
				40: [
					mainField,
					field(Role.EDITABLETEXT, 40, EDIT_STATES + (State.FOCUSED,), name=REPLY, **{"IAccessible2::attribute_name-from": "placeholder"}),
					" ",
				],
			},
		)
		for obj in (self.root, self.banner, self.home, self.main, self.collapsed, self.box):
			obj.treeInterceptor = self.page
		#: The Edge window around the page.
		self.window = WebObject(0, Role.WINDOW)

	def moveTo(self, obj):
		"""Quick navigation to ``obj`` in browse mode (E for the box, Tab for the link): NVDA's report of its line
		(TextInfoQuickNavItem.report has speech.speakTextInfo say the line, for quick navigation)."""
		speechPackage.speakTextInfo(self.page.makeTextInfo(obj), reason=OutputReason.QUICKNAV)
		# NVDA remembers the focusable object at browse mode's cursor, to know it again when its focus event comes.
		self.page._objPendingFocusBeforeActivate = obj

	def focus(self, obj, plugin, previousFocus=None):
		"""The focus moves to ``obj``: api.setFocusObject works out its ancestors and where they part from the last
		focus's (by default the page itself, where browse mode leaves the focus), then NVDA hands the focus event to
		the global plugin, the page, and ``obj``."""
		previousFocus = previousFocus or self.root
		ancestors = [self.window, self.root, self.main]
		oldLine = [self.window, self.root] if previousFocus == self.root else [self.window, self.root, previousFocus]
		level = 0
		while level < min(len(ancestors), len(oldLine)) and ancestors[level] == oldLine[level]:
			level += 1
		globalVars.focusObject, globalVars.focusAncestors, globalVars.focusDifferenceLevel = obj, ancestors, level
		plugin.event_gainFocus(obj, lambda: self.page.event_gainFocus(obj, obj.event_gainFocus))


def fieldsHeard(page):
	"""The identifiers of the fields in NVDA's cache of what browse mode's cursor is in."""
	return {int(field["controlIdentifier_ID"]) for field in page._speakTextInfoState.controlFieldStackCache}


class NvdaTestCase(unittest.TestCase):
	def setUp(self):
		browseMode = types.ModuleType("browseMode")
		browseMode.BrowseModeDocumentTreeInterceptor = BrowseModeDocumentTreeInterceptor
		modules = mock.patch.dict(
			sys.modules,
			{
				"speech": speechPackage,
				"speech.speech": speechModule,
				"controlTypes": controlTypes,
				"config": config,
				"textInfos": textInfos,
				"browseMode": browseMode,
				"api": api,
				"eventHandler": eventHandler,
				"aria": aria,
			},
		)
		modules.start()
		self.addCleanup(modules.stop)
		self.addCleanup(self._restoreNvda)
		config.conf = v125.testersConfig()
		globalVars.focusObject, globalVars.focusAncestors, globalVars.focusDifferenceLevel = None, [], 0
		spoken.clear()
		cancelled.clear()

	def _restoreNvda(self):
		formFields.unregister()
		# Whatever a test put over NVDA's own goes, so the next test starts from NVDA as it is.
		speechScope.update(NVDA_OWN)
		formFields._replaced.clear()
		formFields._failed = False
		formFields._local.heard = None
		formFields._local.field = None
		config.conf = v125.testersConfig()


class ReplyBoxTests(NvdaTestCase):
	"""The tester's reply box on reddit, with NVDA 2026.2's own code."""

	def test_nvdaAloneSaysWhatTheLog(self):
		"""Without the assistant, NVDA says what the tester's log shows: E, then Enter."""
		post = RedditPost()
		post.moveTo(post.collapsed)
		post.focus(post.box, Plugin())
		self.assertEqual(
			spoken,
			[
				["main landmark", "edit", "multi line", REPLY],
				["main landmark"],
				[REPLY, "edit", "multi line", "blank"],
			],
		)

	def test_saidAsJawsSaysIt(self):
		"""With the assistant, Enter says what JAWS said: "edit, blank, placeholder, Join the conversation"."""
		formFields.register()
		post = RedditPost()
		post.moveTo(post.collapsed)
		self.assertEqual(spoken, [["main landmark", "edit", REPLY]])
		spoken.clear()
		post.focus(post.box, Plugin(formFields))
		self.assertEqual(spoken, [["edit", "blank", formFields.PLACEHOLDER, REPLY]])
		# NVDA went on as it does: focus mode, the caret at the box, and its caches of what it said.
		self.assertTrue(post.page.passThrough)
		self.assertEqual(fieldsHeard(post.page), {2, 40})
		self.assertEqual(post.main._speakObjectPropertiesCache["roleText"], "main landmark")

	def test_nvdaHasForgottenWhereTheCursorWasWhenItSaysTheLandmark(self):
		"""NVDA updates its cache of what browse mode's cursor is in to the focus before it says what the focus entered,
		so the assistant notes it as the focus event starts."""
		formFields.register()
		post = RedditPost()
		post.moveTo(post.home)
		seen = []
		replay = BrowseModeDocumentTreeInterceptor._replayFocusEnteredEvents

		def noting(page):
			seen.append(fieldsHeard(page))
			return replay(page)

		with mock.patch.object(BrowseModeDocumentTreeInterceptor, "_replayFocusEnteredEvents", noting):
			post.focus(post.box, Plugin(formFields))
		self.assertEqual(seen, [{2, 40}])
		# The cursor was on the banner's link, not in the main landmark: NVDA says it, as JAWS does coming into it.
		self.assertEqual(spoken[1:], [["main landmark"], ["edit", "blank", formFields.PLACEHOLDER, REPLY]])

	def test_focusFromAnotherWindowSaysTheLandmark(self):
		"""Coming back to the page from elsewhere, NVDA says what the focus is in, as it does."""
		formFields.register()
		post = RedditPost()
		post.moveTo(post.collapsed)
		spoken.clear()
		globalVars.focusObject = post.box
		globalVars.focusAncestors, globalVars.focusDifferenceLevel = [post.window, post.root, post.main], 1
		Plugin(formFields).event_gainFocus(post.box, lambda: post.page.event_gainFocus(post.box, post.box.event_gainFocus))
		self.assertIn(["main landmark"], spoken)
		self.assertEqual(spoken[-1], ["edit", "blank", formFields.PLACEHOLDER, REPLY])

	def test_withoutThePluginsNoteNvdaSaysTheLandmark(self):
		"""What the cursor was in is known only through the global plugin's focus event."""
		formFields.register()
		post = RedditPost()
		post.moveTo(post.collapsed)
		spoken.clear()
		post.focus(post.box, Plugin())
		self.assertEqual(spoken, [["main landmark"], ["edit", "blank", formFields.PLACEHOLDER, REPLY]])

	def test_nvdaTabSaysItAsJaws(self):
		"""NVDA+Tab (speech.speakObject for a query), as JAWS's Insert+Tab: no "multi line", and the placeholder after
		"blank". "focused" is NVDA's own, for a query."""
		post = RedditPost()
		speechPackage.speakObject(post.box, OutputReason.QUERY)
		self.assertEqual(spoken, [[REPLY, "edit", "focused", "multi line", "blank"]])
		spoken.clear()
		formFields.register()
		speechPackage.speakObject(post.box, OutputReason.QUERY)
		self.assertEqual(spoken, [["edit", "focused", "blank", formFields.PLACEHOLDER, REPLY]])

	def test_typedTextWithoutThePlaceholder(self):
		"""With the tester's reply typed in, JAWS says neither a name nor the placeholder; NVDA said the placeholder as
		the box's name."""
		post = RedditPost()
		post.box.text = TYPED
		speechPackage.speakObject(post.box, OutputReason.FOCUS)
		self.assertEqual(spoken, [[REPLY, "edit", "multi line", TYPED]])
		spoken.clear()
		formFields.register()
		speechPackage.speakObject(post.box, OutputReason.FOCUS)
		self.assertEqual(spoken, [["edit", TYPED]])

	def test_turnedOffNvdasOwnAreBack(self):
		formFields.register()
		self.assertTrue(formFields.isRegistered())
		formFields.unregister()
		self.assertFalse(formFields.isRegistered())
		for name, own in NVDA_OWN.items():
			self.assertIs(speechScope[name], own, name)
		post = RedditPost()
		post.moveTo(post.collapsed)
		post.focus(post.box, Plugin(formFields))
		self.assertEqual(spoken[1:], [["main landmark"], [REPLY, "edit", "multi line", "blank"]])

	def test_anotherAddOnsWrapperStays(self):
		"""Another add-on that puts its own around the assistant's keeps it; the assistant's does nothing while off,
		and isn't put in twice when turned on again."""
		formFields.register()
		ours = speechScope["getObjectSpeech"]

		def theirs(*args, **kwargs):
			return ours(*args, **kwargs)

		theirs.__wrapped__ = ours
		speechScope["getObjectSpeech"] = theirs
		formFields.unregister()
		self.assertIs(speechScope["getObjectSpeech"], theirs)
		post = RedditPost()
		speechPackage.speakObject(post.box, OutputReason.FOCUS)
		self.assertEqual(spoken, [[REPLY, "edit", "multi line", "blank"]])
		formFields.register()
		self.assertIs(speechScope["getObjectSpeech"], theirs)
		spoken.clear()
		speechPackage.speakObject(post.box, OutputReason.FOCUS)
		self.assertEqual(spoken, [["edit", "blank", formFields.PLACEHOLDER, REPLY]])


class GitHubFieldTests(NvdaTestCase):
	"""The fields of GitHub's new issue page the tester filled in, with a label and a placeholder of their own."""

	def title(self):
		return WebObject(
			50,
			Role.EDITABLETEXT,
			name="Add a title",
			states=(State.FOCUSABLE, State.EDITABLE, State.REQUIRED, State.FOCUSED),
			attributes={"placeholder": "Title", "name-from": "related-element", "explicit-name": "true"},
		)

	def markdown(self):
		return WebObject(
			51,
			Role.EDITABLETEXT,
			name="Markdown value",
			states=EDIT_STATES + (State.FOCUSED,),
			attributes={"placeholder": "Type your description here…", "name-from": "attribute", "explicit-name": "true"},
			description="Markdown input: edit mode selected.",
		)

	def test_nvdaAloneSaysWhatTheLog(self):
		speechPackage.speakObject(self.title(), OutputReason.FOCUS)
		speechPackage.speakObject(self.markdown(), OutputReason.FOCUS)
		self.assertEqual(
			spoken,
			[
				["Add a title", "edit", "required", "Title", "blank"],
				["Markdown value", "edit", "multi line", "Markdown input: edit mode selected.", "Type your description here…", "blank"],
			],
		)

	def test_placeholderAfterBlank(self):
		formFields.register()
		speechPackage.speakObject(self.title(), OutputReason.FOCUS)
		self.assertEqual(spoken, [["Add a title", "edit", "required", "blank", formFields.PLACEHOLDER, "Title"]])

	def test_descriptionAfterThePlaceholder(self):
		"""JAWS says an empty field's description last, after the placeholder."""
		formFields.register()
		speechPackage.speakObject(self.markdown(), OutputReason.FOCUS)
		self.assertEqual(
			spoken,
			[["Markdown value", "edit", "blank", formFields.PLACEHOLDER, "Type your description here…", "Markdown input: edit mode selected."]],
		)

	def test_textInTheFieldAsNvdaSaysIt(self):
		"""A field with text in it has no placeholder to say, and keeps NVDA's order (without "multi line")."""
		formFields.register()
		markdown = self.markdown()
		markdown.text = "This is to compare what Jaws and NVDA says."
		speechPackage.speakObject(markdown, OutputReason.FOCUS)
		self.assertEqual(spoken, [["Markdown value", "edit", "Markdown input: edit mode selected.", markdown.text]])


class OtherFieldTests(NvdaTestCase):
	def test_notAWebPage(self):
		"""An edit field NVDA doesn't read through IAccessible2 keeps NVDA's speech, but for "multi line"."""
		formFields.register()
		notepad = WindowsObject(60, Role.EDITABLETEXT, name="Text editor", states=EDIT_STATES + (State.FOCUSED,))
		del notepad.IA2Attributes
		speechPackage.speakObject(notepad, OutputReason.FOCUS)
		self.assertEqual(spoken, [["Text editor", "edit", "blank"]])

	def test_multiLineOnlyForEditFields(self):
		formFields.register()
		states = {State.MULTILINE, State.FOCUSABLE}
		values = {"states": states, "_role": Role.LIST}
		self.assertIs(formFields.withoutMultiLine(values), values)
		values = {"states": states, "negativeStates": {State.MULTILINE}, "role": Role.EDITABLETEXT, "_states": states}
		changed = formFields.withoutMultiLine(values)
		self.assertEqual(changed["states"], {State.FOCUSABLE})
		self.assertEqual(changed["negativeStates"], set())
		# NVDA's own sets are left as they were: NVDA keeps them.
		self.assertEqual(states, {State.MULTILINE, State.FOCUSABLE})
		self.assertIs(changed["_states"], states)

	def test_rearrange(self):
		self.assertEqual(
			formFields.rearrange(["Join the conversation", "edit", "blank"], "Join the conversation", "Join the conversation", True),
			["edit", "blank", "placeholder", "Join the conversation"],
		)
		# A name that isn't the first thing NVDA says stays: something else changed NVDA's speech.
		self.assertEqual(
			formFields.rearrange(["edit", "Join the conversation"], "Join the conversation", "Join the conversation", False),
			["edit", "Join the conversation"],
		)

	def test_withoutNvdasPlaceholderSpeechNvdasObjectSpeechStays(self):
		"""Where NVDA has no _getPlaceholderSpeechIfTextEmpty, a name made from the placeholder isn't left out, as it
		couldn't be said after "blank"; "multi line" still is."""
		del speechScope[formFields.PLACEHOLDER_SPEECH]
		with mock.patch.object(formFields, "_log"):
			formFields.register()
		self.assertIs(speechScope[formFields.OBJECT_SPEECH], NVDA_OWN[formFields.OBJECT_SPEECH])
		self.assertIsNot(speechScope[formFields.PROPERTIES_SPEECH], NVDA_OWN[formFields.PROPERTIES_SPEECH])


class SettingTests(unittest.TestCase):
	def test_onUnlessTurnedOff(self):
		self.assertTrue(state.DEFAULTS[formFields.STATE_KEY])
		self.assertTrue(formFields.wanted({}))
		self.assertTrue(formFields.wanted({formFields.STATE_KEY: True}))
		self.assertFalse(formFields.wanted({formFields.STATE_KEY: False}))
		self.assertFalse(formFields.wanted(None))


if __name__ == "__main__":
	unittest.main()
