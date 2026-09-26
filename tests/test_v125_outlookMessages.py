# Unit tests for version 1.25, from a tester's report (issue 20): "What Jaws says when opening an outlook message.
# comparing what Jaws and Nvda say." The tester opened a forwarded message in classic Outlook, Office 16.0.20326, which
# NVDA reads through UI Automation, and pasted what JAWS said, with no key pressed:
#   From:
#     Send Mail Link   nvda-addons@nvda-addons.groups.io
#   <   Send Mail Link   nvda-addons@nvda-addons.groups.io>
#   On Behalf Of Alireza Mamani via groups.io
#   …
#   Today, I am writing to introduce an add-on I have been working on over the past few days called Auto Braille.
#   What it does is simply bring automatic language switching to braille in NVDA — ...
# JAWS read the message from the top as it opened: its Outlook scripts start Say All when a read-only message's document
# loads (Outlook.jss, DocumentLoadedEvent), as JAWS's Outlook.jcf has it (MessageSayAllVerbosity=1), with no window
# title (SpeakWindowTitlesForVirtualMessages is off). The log attached to the issue (NVDA log 2026-09-26 11.53.09.zip)
# shows NVDA saying nothing as the message opened (Outlook First Line Silence dropped the title, "document" and the
# first line NVDA says with "Automatic Say All on page load" off, as the tester has it), then:
# 11:51:00.454 Input: kb(laptop):control+home
# 11:51:00.708 Speaking ['heading level 1', 'From: ', 'link', 'nvda-addons@nvda-addons.groups.io', 'heading level 1', ' <',
#              'link', 'nvda-addons@nvda-addons.groups.io', 'heading level 1', '> On Behalf Of Alireza Mamani via groups.io\r']
# and with the arrow keys "heading level 1, From: ", "link, nvda-addons@nvda-addons.groups.io", "heading level 1,  <".
# - outlookMessages: an Outlook message you read is read from the top when it opens, where NVDA said the line at the
#   caret; a link to a mailto: address is "send mail link"; text Word calls a heading only for its outline level, not
#   its style, as the From line of a quoted message, is said without "heading level 1".
# The imitation NVDA runs NVDA 2026.2's own code, word for word: browse mode coming into a document
# (BrowseModeDocumentTreeInterceptor.event_treeInterceptor_gainFocus), NVDA's Outlook support's test of a message you
# read (OutlookUIAWordDocument._get_isReadonlyViewer), the fields NVDA makes of Word's UI Automation elements and
# formatting (UIATextInfo._getControlFieldForUIAObject, UIAControlTypesWhereNameIsContent and _getFormatFieldHeadings,
# WordDocumentTextInfo._getControlFieldForUIAObject and _getFormatFieldAtRange), its speech of them
# (speech.getControlFieldSpeech, getPropertiesSpeech, _shouldSpeakContentFirst, getFormatFieldSpeech,
# textInfos.ControlField.getPresentationCategory, controlTypes' silentRolesOnFocus and silentValuesForRoles) and braille
# (braille.getPropertiesBraille), with the Document Formatting defaults of NVDA's configSpec and the tester's changes to
# them. The assistant's code is the real one.
# Since 1.26, reading a message from the top when it opens is a setting of its own, off unless turned on (issue 23: the
# tester's JAWS reads a message only with the arrow keys), so these tests turn it on: register(reading=True).
# Run: python -m unittest tests.test_v125_outlookMessages -v

import enum
import os
import re
import sys
import textwrap
import types
import typing
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import outlookMessages, state  # noqa: E402


#: NVDA 2026.2, source/browseMode.py, BrowseModeDocumentTreeInterceptor.event_treeInterceptor_gainFocus, word for word.
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
	braille.handler.handleGainFocus(self)
'''


#: NVDA 2026.2, source/appModules/outlook.py, OutlookUIAWordDocument._get_isReadonlyViewer, word for word.
NVDA_OUTLOOK_UIA_READONLY_VIEWER = r'''
def _get_isReadonlyViewer(self):
	return controlTypes.State.READONLY in self.states
'''


#: NVDA 2026.2, source/NVDAObjects/UIA/__init__.py, UIATextInfo.UIAControlTypesWhereNameIsContent, word for word.
NVDA_UIA_NAME_IS_CONTENT = r'''
UIAControlTypesWhereNameIsContent = {
	UIAHandler.UIA_ButtonControlTypeId,
	UIAHandler.UIA_HyperlinkControlTypeId,
	UIAHandler.UIA_ImageControlTypeId,
	UIAHandler.UIA_MenuItemControlTypeId,
	UIAHandler.UIA_TabItemControlTypeId,
	UIAHandler.UIA_TextControlTypeId,
	UIAHandler.UIA_SplitButtonControlTypeId,
}
'''


#: NVDA 2026.2, source/NVDAObjects/UIA/__init__.py, UIATextInfo._getControlFieldForUIAObject, word for word.
NVDA_UIA_CONTROL_FIELD = r'''
def _getControlFieldForUIAObject(
	self,
	obj: "UIA",
	isEmbedded=False,
	startOfNode=False,
	endOfNode=False,
) -> textInfos.ControlField:
	"""
	Fetch control field information for the given UIA NVDAObject.
	@param obj: the NVDAObject the control field is for.
	@param isEmbedded: True if this NVDAObject is for a leaf node (has no useful children).
	@param startOfNode: True if the control field represents the very start of this object.
	@param endOfNode: True if the control field represents the very end of this object.
	@return: The control field for this object
	"""
	role = obj.role
	field = textInfos.ControlField()
	# Ensure this controlField is unique to the object
	runtimeID = field["runtimeID"] = obj.UIAElement.getRuntimeId()
	field["_startOfNode"] = startOfNode
	field["_endOfNode"] = endOfNode
	field["role"] = obj.role
	states = obj.states
	# The user doesn't care about certain states, as they are obvious.
	states.discard(controlTypes.State.EDITABLE)
	states.discard(controlTypes.State.MULTILINE)
	states.discard(controlTypes.State.FOCUSED)
	field["states"] = states
	field["nameIsContent"] = nameIsContent = (
		obj.UIAElement.cachedControlType in self.UIAControlTypesWhereNameIsContent
	)
	if not nameIsContent:
		field["name"] = obj.name
	field["description"] = obj.description
	field["level"] = obj.positionInfo.get("level")
	if role == controlTypes.Role.TABLE:
		field["table-id"] = runtimeID
		try:
			field["table-rowcount"] = obj.rowCount
			field["table-columncount"] = obj.columnCount
		except NotImplementedError:
			pass
	if role in (
		controlTypes.Role.TABLECELL,
		controlTypes.Role.DATAITEM,
		controlTypes.Role.TABLECOLUMNHEADER,
		controlTypes.Role.TABLEROWHEADER,
		controlTypes.Role.HEADERITEM,
	):
		try:
			field["table-rownumber"] = obj.rowNumber
			field["table-rowsspanned"] = obj.rowSpan
			field["table-columnnumber"] = obj.columnNumber
			field["table-columnsspanned"] = obj.columnSpan
			field["table-id"] = obj.table.UIAElement.getRuntimeId()
			field["role"] = controlTypes.Role.TABLECELL
			field["table-columnheadertext"] = obj.columnHeaderText
			field["table-rowheadertext"] = obj.rowHeaderText
		except NotImplementedError:
			pass
	return field
'''


#: NVDA 2026.2, source/NVDAObjects/UIA/__init__.py, UIATextInfo._getFormatFieldHeadings, word for word.
NVDA_UIA_FORMAT_FIELD_HEADINGS = r'''
def _getFormatFieldHeadings(self, fetch: Callable[[int], int], formatField: textInfos.FormatField):
	styleIDValue = fetch(UIAHandler.UIA_StyleIdAttributeId)
	# #9842: styleIDValue can sometimes be a pointer to IUnknown.
	# In Python 3, comparing an int with a pointer raises a TypeError.
	if (
		isinstance(styleIDValue, int)
		and UIAHandler.StyleId_Heading1 <= styleIDValue <= UIAHandler.StyleId_Heading9
	):
		formatField["heading-level"] = (styleIDValue - UIAHandler.StyleId_Heading1) + 1
'''


#: NVDA 2026.2, source/NVDAObjects/UIA/wordDocument.py, WordDocumentTextInfo._getControlFieldForUIAObject, word for word.
NVDA_WORD_CONTROL_FIELD = r'''
def _getControlFieldForUIAObject(
	self,
	obj: "WordDocumentNode",
	isEmbedded=False,
	startOfNode=False,
	endOfNode=False,
):
	# Ignore strange editable text fields surrounding most inner fields (links, table cells etc)
	automationId = obj.UIAAutomationId
	field = super(WordDocumentTextInfo, self)._getControlFieldForUIAObject(
		obj,
		isEmbedded=isEmbedded,
		startOfNode=startOfNode,
		endOfNode=endOfNode,
	)
	if automationId.startswith("UIA_AutomationId_Word_Page_"):
		field["page-number"] = automationId.rsplit("_", 1)[-1]
	elif obj.UIAElement.cachedControlType == UIAHandler.UIA_GroupControlTypeId and obj.name:
		field["role"] = controlTypes.Role.EMBEDDEDOBJECT
		field["alwaysReportName"] = True
	elif obj.role == controlTypes.Role.MATH:
		field["mathml"] = obj.mathMl
	elif obj.UIAElement.cachedControlType == UIAHandler.UIA_CustomControlTypeId and obj.name:
		# Include foot note and endnote identifiers
		field["content"] = obj.name
		field["role"] = controlTypes.Role.LINK
	if obj.role == controlTypes.Role.LIST or obj.role == controlTypes.Role.EDITABLETEXT:
		field["states"].add(controlTypes.State.READONLY)
		if obj.role == controlTypes.Role.LIST:
			# To stay compatible with the older MS Word implementation, don't expose lists in word documents as actual lists. This suppresses announcement of entering and exiting them.
			# Note that bullets and numbering are still announced of course.
			# Eventually we'll want to stop suppressing this, but for now this is more confusing than good (as in many cases announcing of new bullets when pressing enter causes exit and then enter to be spoken).
			field["role"] = controlTypes.Role.EDITABLETEXT
	if obj.role == controlTypes.Role.GRAPHIC:
		# Label graphics with a description before name as name seems to be auto-generated (E.g. "rectangle")
		field["content"] = (
			field.pop("description", None) or obj.description or field.pop("name", None) or obj.name
		)
	# #11430: Read-only tables, such as in the Outlook message viewer
	# should be treated as layout tables,
	# if they have either 1 column or 1 row.
	if (
		obj.appModule.appName == "outlook"
		and obj.role == controlTypes.Role.TABLE
		and controlTypes.State.READONLY in obj.states
		and (obj.rowCount <= 1 or obj.columnCount <= 1)
	):
		field["table-layout"] = True
	return field
'''


#: NVDA 2026.2, source/NVDAObjects/UIA/wordDocument.py, WordDocumentTextInfo._getFormatFieldAtRange, word for word.
NVDA_WORD_FORMAT_FIELD_AT_RANGE = r'''
def _getFormatFieldAtRange(self, textRange, formatConfig, ignoreMixedValues=False):
	formatField = super()._getFormatFieldAtRange(
		textRange,
		formatConfig,
		ignoreMixedValues=ignoreMixedValues,
	)
	if not formatField:
		return formatField
	if UIARemote.isSupported():
		docElement = self.obj.UIAElement
		if formatConfig["reportLineNumber"]:
			lineNumber = UIARemote.msWord_getCustomAttributeValue(
				docElement,
				textRange,
				UIACustomAttributeID.LINE_NUMBER,
			)
			if isinstance(lineNumber, int):
				formatField.field["line-number"] = lineNumber
		if formatConfig["reportPage"]:
			pageNumber = UIARemote.msWord_getCustomAttributeValue(
				docElement,
				textRange,
				UIACustomAttributeID.PAGE_NUMBER,
			)
			# Only use valid page numbers (>= 1). Word returns -1 when the value is not available,
			# particularly when navigating backwards to the first line of a page.
			# In such cases, we fall back to the control field page number in getTextWithFields.
			if isinstance(pageNumber, int) and pageNumber > 0:
				formatField.field["page-number"] = pageNumber
			sectionNumber = UIARemote.msWord_getCustomAttributeValue(
				docElement,
				textRange,
				UIACustomAttributeID.SECTION_NUMBER,
			)
			if isinstance(sectionNumber, int):
				formatField.field["section-number"] = sectionNumber
			if False:
				# #13511: Fetching of text-column-number is disabled
				# as it causes Microsoft Word 16.0.1493 and newer to crash!!
				# This should only be reenabled for versions identified not to crash.
				textColumnNumber = UIARemote.msWord_getCustomAttributeValue(
					docElement,
					textRange,
					UIACustomAttributeID.COLUMN_NUMBER,
				)
				if isinstance(textColumnNumber, int):
					formatField.field["text-column-number"] = textColumnNumber
		# #18279: It is only safe to fetch the expand/collapse state in MS Word 16.0.18226 or later,
		# as earlier versions that support Custom attribute Values but not this particular argument will crash.
		try:
			officeVersion = tuple(int(x) for x in self.obj.appModule.productVersion.split(".")[:3])
		except Exception:
			log.error("Unable to parse Office version", exc_info=True)
			officeVersion = (0, 0, 0)
		if officeVersion >= (16, 0, 18226):
			expandCollapseState = UIARemote.msWord_getCustomAttributeValue(
				docElement,
				textRange,
				UIACustomAttributeID.EXPAND_COLLAPSE_STATE,
			)
			if expandCollapseState == EXPAND_COLLAPSE_STATE.COLLAPSED:
				formatField.field["collapsed"] = True
			elif expandCollapseState == EXPAND_COLLAPSE_STATE.EXPANDED:
				formatField.field["collapsed"] = False
	return formatField
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


#: NVDA 2026.2, source/speech/speech.py, _shouldSpeakContentFirst, word for word.
NVDA_SPEAK_CONTENT_FIRST = r'''
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


#: NVDA 2026.2, source/speech/speech.py, getFormatFieldSpeech, word for word.
NVDA_FORMAT_FIELD_SPEECH = r'''
def getFormatFieldSpeech(  # noqa: C901
	attrs: textInfos.Field,
	attrsCache: Optional[textInfos.Field] = None,
	formatConfig: Optional[Dict[str, bool]] = None,
	reason: Optional[OutputReason] = None,
	unit: Optional[str] = None,
	extraDetail: bool = False,
	initialFormat: bool = False,
) -> SpeechSequence:
	if not formatConfig:
		formatConfig = config.conf["documentFormatting"]
	textList = []
	if formatConfig["reportTables"]:
		tableInfo = attrs.get("table-info")
		oldTableInfo = attrsCache.get("table-info") if attrsCache is not None else None
		tableSequence = getTableInfoSpeech(
			tableInfo,
			oldTableInfo,
			extraDetail=extraDetail,
		)
		if tableSequence:
			textList.extend(tableSequence)
	if formatConfig["reportPage"]:
		pageNumber = attrs.get("page-number")
		oldPageNumber = attrsCache.get("page-number") if attrsCache is not None else None
		if pageNumber and pageNumber != oldPageNumber:
			# Translators: Indicates the page number in a document.
			# %s will be replaced with the page number.
			text = _("page %s") % pageNumber
			textList.append(text)
		sectionNumber = attrs.get("section-number")
		oldSectionNumber = attrsCache.get("section-number") if attrsCache is not None else None
		if sectionNumber and sectionNumber != oldSectionNumber:
			# Translators: Indicates the section number in a document.
			# %s will be replaced with the section number.
			text = _("section %s") % sectionNumber
			textList.append(text)

		textColumnCount = attrs.get("text-column-count")
		oldTextColumnCount = attrsCache.get("text-column-count") if attrsCache is not None else None
		textColumnNumber = attrs.get("text-column-number")
		oldTextColumnNumber = attrsCache.get("text-column-number") if attrsCache is not None else None

		# Because we do not want to report the number of columns when a document is just opened and there is only
		# one column. This would be verbose, in the standard case.
		# column number has changed, or the columnCount has changed
		# but not if the columnCount is 1 or less and there is no old columnCount.
		if (
			(textColumnNumber and textColumnNumber != oldTextColumnNumber)
			or (textColumnCount and textColumnCount != oldTextColumnCount)
		) and not (textColumnCount and int(textColumnCount) <= 1 and oldTextColumnCount == None):  # noqa: E711
			if textColumnNumber and textColumnCount:
				# Translators: Indicates the text column number in a document.
				# {0} will be replaced with the text column number.
				# {1} will be replaced with the number of text columns.
				text = _("column {0} of {1}").format(textColumnNumber, textColumnCount)
				textList.append(text)
			elif textColumnCount:
				# Translators: Indicates the text column number in a document.
				# %s will be replaced with the number of text columns.
				text = ngettext("%s column", "%s columns", textColumnCount) % textColumnCount
				textList.append(text)
			elif textColumnNumber:
				# Translators: Indicates the text column number in a document.
				text = _("column {columnNumber}").format(columnNumber=textColumnNumber)
				textList.append(text)

	sectionBreakType = attrs.get("section-break")
	if sectionBreakType:
		if sectionBreakType == "0":  # Continuous section break.
			text = _("continuous section break")
		elif sectionBreakType == "1":  # New column section break.
			text = _("new column section break")
		elif sectionBreakType == "2":  # New page section break.
			text = _("new page section break")
		elif sectionBreakType == "3":  # Even pages section break.
			text = _("even pages section break")
		elif sectionBreakType == "4":  # Odd pages section break.
			text = _("odd pages section break")
		else:
			text = ""
		textList.append(text)
	columnBreakType = attrs.get("column-break")
	if columnBreakType:
		textList.append(_("column break"))
	if formatConfig["reportHeadings"]:
		headingLevel = attrs.get("heading-level")
		oldHeadingLevel = attrsCache.get("heading-level") if attrsCache is not None else None
		# headings should be spoken not only if they change, but also when beginning to speak lines or paragraphs
		# Ensuring a similar experience to if a heading was a controlField
		if headingLevel and (
			initialFormat
			and (
				reason in [OutputReason.FOCUS, OutputReason.QUICKNAV]
				or unit in (textInfos.UNIT_LINE, textInfos.UNIT_PARAGRAPH)
			)
			or headingLevel != oldHeadingLevel
		):
			# Translators: Speaks the heading level (example output: heading level 2).
			text = _("heading level %d") % headingLevel
			textList.append(text)
	collapsed = attrs.get("collapsed")
	oldCollapsed = attrsCache.get("collapsed") if attrsCache is not None else None
	# collapsed state should be spoken when beginning to speak lines or paragraphs
	# Ensuring a similar experience to if  it was a state on  a controlField
	if collapsed and (
		initialFormat
		and (
			reason in [OutputReason.FOCUS, OutputReason.QUICKNAV]
			or unit in (textInfos.UNIT_LINE, textInfos.UNIT_PARAGRAPH)
		)
		or collapsed != oldCollapsed
	):
		textList.append(State.COLLAPSED.displayString)
	if formatConfig["reportStyle"]:
		style = attrs.get("style")
		oldStyle = attrsCache.get("style") if attrsCache is not None else None
		if style != oldStyle:
			if style:
				# Translators: Indicates the style of text.
				# A style is a collection of formatting settings and depends on the application.
				# %s will be replaced with the name of the style.
				text = _("style %s") % style
			else:
				# Translators: Indicates that text has reverted to the default style.
				# A style is a collection of formatting settings and depends on the application.
				text = _("default style")
			textList.append(text)
	if formatConfig["reportCellBorders"] != ReportCellBorders.OFF:
		borderStyle = attrs.get("border-style")
		oldBorderStyle = attrsCache.get("border-style") if attrsCache is not None else None
		if (borderStyle or oldBorderStyle is not None) and borderStyle != oldBorderStyle:
			if borderStyle:
				text = borderStyle
			else:
				# Translators: Indicates that cell does not have border lines.
				text = _("no border lines")
			textList.append(text)
	if formatConfig["reportFontName"]:
		fontFamily = attrs.get("font-family")
		oldFontFamily = attrsCache.get("font-family") if attrsCache is not None else None
		if fontFamily and fontFamily != oldFontFamily:
			textList.append(fontFamily)
		fontName = attrs.get("font-name")
		oldFontName = attrsCache.get("font-name") if attrsCache is not None else None
		if fontName and fontName != oldFontName:
			textList.append(fontName)
	if formatConfig["reportFontSize"]:
		fontSize = attrs.get("font-size")
		oldFontSize = attrsCache.get("font-size") if attrsCache is not None else None
		if fontSize and fontSize != oldFontSize:
			textList.append(fontSize)
	if formatConfig["reportColor"]:
		color = attrs.get("color")
		oldColor = attrsCache.get("color") if attrsCache is not None else None
		backgroundColor = attrs.get("background-color")
		oldBackgroundColor = attrsCache.get("background-color") if attrsCache is not None else None
		backgroundColor2 = attrs.get("background-color2")
		oldBackgroundColor2 = attrsCache.get("background-color2") if attrsCache is not None else None
		bgColorChanged = backgroundColor != oldBackgroundColor or backgroundColor2 != oldBackgroundColor2
		bgColorText = backgroundColor.name if isinstance(backgroundColor, colors.RGB) else backgroundColor
		if backgroundColor2:
			bg2Name = backgroundColor2.name if isinstance(backgroundColor2, colors.RGB) else backgroundColor2
			# Translators: Reported when there are two background colors.
			# This occurs when, for example, a gradient pattern is applied to a spreadsheet cell.
			# {color1} will be replaced with the first background color.
			# {color2} will be replaced with the second background color.
			bgColorText = _("{color1} to {color2}").format(color1=bgColorText, color2=bg2Name)
		if color and backgroundColor and color != oldColor and bgColorChanged:
			textList.append(
				# Translators: Reported when both the text and background colors change.
				# {color} will be replaced with the text color.
				# {backgroundColor} will be replaced with the background color.
				_("{color} on {backgroundColor}").format(
					color=color.name if isinstance(color, colors.RGB) else color,
					backgroundColor=bgColorText,
				),
			)
		elif color and color != oldColor:
			# Translators: Reported when the text color changes (but not the background color).
			# {color} will be replaced with the text color.
			textList.append(_("{color}").format(color=color.name if isinstance(color, colors.RGB) else color))
		elif backgroundColor and bgColorChanged:
			# Translators: Reported when the background color changes (but not the text color).
			# {backgroundColor} will be replaced with the background color.
			textList.append(_("{backgroundColor} background").format(backgroundColor=bgColorText))
		backgroundPattern = attrs.get("background-pattern")
		oldBackgroundPattern = attrsCache.get("background-pattern") if attrsCache is not None else None
		if (
			backgroundPattern or oldBackgroundPattern is not None
		) and backgroundPattern != oldBackgroundPattern:
			if not backgroundPattern:
				# Translators: A type of background pattern in Microsoft Excel.
				# No pattern
				backgroundPattern = _("none")
			textList.append(_("background pattern {pattern}").format(pattern=backgroundPattern))
	if formatConfig["reportLineNumber"]:
		lineNumber = attrs.get("line-number")
		oldLineNumber = attrsCache.get("line-number") if attrsCache is not None else None
		if lineNumber is not None and lineNumber != oldLineNumber:
			# Translators: Indicates the line number of the text.
			# %s will be replaced with the line number.
			text = _("line %s") % lineNumber
			textList.append(text)
	if formatConfig["reportRevisions"]:
		# Insertion
		revision = attrs.get("revision-insertion")
		oldRevision = attrsCache.get("revision-insertion") if attrsCache is not None else None
		if (revision or oldRevision is not None) and revision != oldRevision:
			text = (
				# Translators: Reported when text is marked as having been inserted
				_("inserted")
				if revision
				# Translators: Reported when text is no longer marked as having been inserted.
				else _("not inserted")
			)
			textList.append(text)
		revision = attrs.get("revision-deletion")
		oldRevision = attrsCache.get("revision-deletion") if attrsCache is not None else None
		if (revision or oldRevision is not None) and revision != oldRevision:
			text = (
				# Translators: Reported when text is marked as having been deleted
				_("deleted")
				if revision
				# Translators: Reported when text is no longer marked as having been  deleted.
				else _("not deleted")
			)
			textList.append(text)
		revision = attrs.get("revision")
		oldRevision = attrsCache.get("revision") if attrsCache is not None else None
		if (revision or oldRevision is not None) and revision != oldRevision:
			if revision:
				# Translators: Reported when text is revised.
				text = _("revised %s") % revision
			else:
				# Translators: Reported when text is not revised.
				text = _("no revised %s") % oldRevision
			textList.append(text)
	if formatConfig["reportHighlight"]:
		# marked text
		marked = attrs.get("marked")
		oldMarked = attrsCache.get("marked") if attrsCache is not None else None
		if (marked or oldMarked is not None) and marked != oldMarked:
			text = (
				# Translators: Reported when text is marked
				_("marked")
				if marked
				# Translators: Reported when text is no longer marked
				else _("not marked")
			)
			textList.append(text)
		# color-highlighted text in Word
		hlColor = attrs.get("highlight-color")
		oldHlColor = attrsCache.get("highlight-color") if attrsCache is not None else None
		if (hlColor or oldHlColor is not None) and hlColor != oldHlColor:
			colorName = hlColor.name if isinstance(hlColor, colors.RGB) else hlColor
			text = (
				# Translators: Reported when text is color-highlighted
				_("highlighted in {color}").format(color=colorName)
				if hlColor
				# Translators: Reported when text is no longer marked
				else _("not highlighted")
			)
			textList.append(text)
	if formatConfig["reportEmphasis"]:
		# strong text
		strong = attrs.get("strong")
		oldStrong = attrsCache.get("strong") if attrsCache is not None else None
		if (strong or oldStrong is not None) and strong != oldStrong:
			text = (
				# Translators: Reported when text is marked as strong (e.g. bold)
				_("strong")
				if strong
				# Translators: Reported when text is no longer marked as strong (e.g. bold)
				else _("not strong")
			)
			textList.append(text)
		# emphasised text
		emphasised = attrs.get("emphasised")
		oldEmphasised = attrsCache.get("emphasised") if attrsCache is not None else None
		if (emphasised or oldEmphasised is not None) and emphasised != oldEmphasised:
			text = (
				# Translators: Reported when text is marked as emphasised
				_("emphasised")
				if emphasised
				# Translators: Reported when text is no longer marked as emphasised
				else _("not emphasised")
			)
			textList.append(text)
	if formatConfig["fontAttributeReporting"] & OutputMode.SPEECH:
		bold = attrs.get("bold")
		oldBold = attrsCache.get("bold") if attrsCache is not None else None
		if (bold or oldBold is not None) and bold != oldBold:
			text = (
				# Translators: Reported when text is bolded.
				_("bold")
				if bold
				# Translators: Reported when text is not bolded.
				else _("no bold")
			)
			textList.append(text)
		italic = attrs.get("italic")
		oldItalic = attrsCache.get("italic") if attrsCache is not None else None
		if (italic or oldItalic is not None) and italic != oldItalic:
			# Translators: Reported when text is italicized.
			text = (
				_("italic")
				if italic
				# Translators: Reported when text is not italicized.
				else _("no italic")
			)
			textList.append(text)
		strikethrough = attrs.get("strikethrough")
		oldStrikethrough = attrsCache.get("strikethrough") if attrsCache is not None else None
		if (strikethrough or oldStrikethrough is not None) and strikethrough != oldStrikethrough:
			if strikethrough:
				text = (
					# Translators: Reported when text is formatted with double strikethrough.
					# See http://en.wikipedia.org/wiki/Strikethrough
					_("double strikethrough")
					if strikethrough == "double"
					# Translators: Reported when text is formatted with strikethrough.
					# See http://en.wikipedia.org/wiki/Strikethrough
					else _("strikethrough")
				)
			else:
				# Translators: Reported when text is formatted without strikethrough.
				# See http://en.wikipedia.org/wiki/Strikethrough
				text = _("no strikethrough")
			textList.append(text)
		underline = attrs.get("underline")
		oldUnderline = attrsCache.get("underline") if attrsCache is not None else None
		if (underline or oldUnderline is not None) and underline != oldUnderline:
			text = (
				# Translators: Reported when text is underlined.
				_("underlined")
				if underline
				# Translators: Reported when text is not underlined.
				else _("not underlined")
			)
			textList.append(text)
		hidden = attrs.get("hidden")
		oldHidden = attrsCache.get("hidden") if attrsCache is not None else None
		if (hidden or oldHidden is not None) and hidden != oldHidden:
			text = (
				# Translators: Reported when text is hidden.
				_("hidden")
				if hidden
				# Translators: Reported when text is not hidden.
				else _("not hidden")
			)
			textList.append(text)
	if formatConfig["reportSuperscriptsAndSubscripts"]:
		textPosition = attrs.get("text-position", TextPosition.UNDEFINED)
		attrs["text-position"] = textPosition
		oldTextPosition = attrsCache.get("text-position") if attrsCache is not None else None
		if textPosition != oldTextPosition and (
			textPosition in [TextPosition.SUPERSCRIPT, TextPosition.SUBSCRIPT]
			or (
				textPosition == TextPosition.BASELINE
				and (oldTextPosition is not None and oldTextPosition != TextPosition.UNDEFINED)
			)
		):
			textList.append(textPosition.displayString)
	if formatConfig["reportAlignment"]:
		textAlign = attrs.get("text-align")
		oldTextAlign = attrsCache.get("text-align") if attrsCache is not None else None
		if textAlign and textAlign != oldTextAlign:
			textList.append(textAlign.displayString)
		verticalAlign = attrs.get("vertical-align")
		oldVerticalAlign = attrsCache.get("vertical-align") if attrsCache is not None else None
		if verticalAlign and verticalAlign != oldVerticalAlign:
			textList.append(verticalAlign.displayString)
	if formatConfig["reportParagraphIndentation"]:
		indentLabels = {
			"left-indent": (
				# Translators: the label for paragraph format left indent
				_("left indent"),
				# Translators: the message when there is no paragraph format left indent
				_("no left indent"),
			),
			"right-indent": (
				# Translators: the label for paragraph format right indent
				_("right indent"),
				# Translators: the message when there is no paragraph format right indent
				_("no right indent"),
			),
			"hanging-indent": (
				# Translators: the label for paragraph format hanging indent
				_("hanging indent"),
				# Translators: the message when there is no paragraph format hanging indent
				_("no hanging indent"),
			),
			"first-line-indent": (
				# Translators: the label for paragraph format first line indent
				_("first line indent"),
				# Translators: the message when there is no paragraph format first line indent
				_("no first line indent"),
			),
		}
		for attr, (label, noVal) in indentLabels.items():
			newVal = attrs.get(attr)
			oldVal = attrsCache.get(attr) if attrsCache else None
			if (newVal or oldVal is not None) and newVal != oldVal:
				if newVal:
					textList.append("%s %s" % (label, newVal))
				else:
					textList.append(noVal)
	if formatConfig["reportLineSpacing"]:
		lineSpacing = attrs.get("line-spacing")
		oldLineSpacing = attrsCache.get("line-spacing") if attrsCache is not None else None
		if (lineSpacing or oldLineSpacing is not None) and lineSpacing != oldLineSpacing:
			# Translators: a type of line spacing (E.g. single line spacing)
			textList.append(_("line spacing %s") % lineSpacing)
	if formatConfig["reportLinks"]:
		link = attrs.get("link")
		oldLink = attrsCache.get("link") if attrsCache is not None else None
		if (link or oldLink is not None) and link != oldLink:
			text = _("link") if link else _("out of %s") % _("link")
			textList.append(text)
	if formatConfig["reportComments"]:
		comment = attrs.get("comment")
		oldComment = attrsCache.get("comment") if attrsCache is not None else None
		if (comment or oldComment is not None) and comment != oldComment:
			if comment:
				if comment is textInfos.CommentType.DRAFT:
					# Translators: Reported when text contains a draft comment.
					text = _("has draft comment")
				elif comment is textInfos.CommentType.RESOLVED:
					# Translators: Reported when text contains a resolved comment.
					text = _("has resolved comment")
				else:  # generic
					# Translators: Reported when text contains a generic comment.
					text = _("has comment")
				textList.append(text)
			elif extraDetail:
				# Translators: Reported when text no longer contains a comment.
				text = _("out of comment")
				textList.append(text)
	if formatConfig["reportBookmarks"]:
		bookmark = attrs.get("bookmark")
		oldBookmark = attrsCache.get("bookmark") if attrsCache is not None else None
		if (bookmark or oldBookmark is not None) and bookmark != oldBookmark:
			if bookmark:
				# Translators: Reported when text contains a bookmark
				text = _("bookmark")
				textList.append(text)
			elif extraDetail:
				# Translators: Reported when text no longer contains a bookmark
				text = _("out of bookmark")
				textList.append(text)
	if formatConfig["reportSpellingErrors2"]:
		invalidSpelling = attrs.get("invalid-spelling")
		oldInvalidSpelling = attrsCache.get("invalid-spelling") if attrsCache is not None else None
		if (invalidSpelling or oldInvalidSpelling is not None) and invalidSpelling != oldInvalidSpelling:
			texts = []
			if invalidSpelling:
				if formatConfig["reportSpellingErrors2"] & ReportSpellingErrors.SOUND.value:
					texts.append(WaveFileCommand(r"waves\textError.wav"))
				if formatConfig["reportSpellingErrors2"] & ReportSpellingErrors.SPEECH.value:
					# Translators: Reported when text contains a spelling error.
					texts.append(_("spelling error"))
			elif extraDetail and _shouldReportOutOfError(formatConfig):
				# Translators: Reported when moving out of text containing a spelling error.
				texts.append(_("out of spelling error"))
			textList.extend(texts)
		invalidGrammar = attrs.get("invalid-grammar")
		oldInvalidGrammar = attrsCache.get("invalid-grammar") if attrsCache is not None else None
		if (invalidGrammar or oldInvalidGrammar is not None) and invalidGrammar != oldInvalidGrammar:
			texts = []
			if invalidGrammar:
				if formatConfig["reportSpellingErrors2"] & ReportSpellingErrors.SOUND.value:
					texts.append(WaveFileCommand(r"waves\textError.wav"))
				if formatConfig["reportSpellingErrors2"] & ReportSpellingErrors.SPEECH.value:
					# Translators: Reported when text contains a grammar error.
					texts.append(_("grammar error"))
			elif extraDetail and _shouldReportOutOfError(formatConfig):
				# Translators: Reported when moving out of text containing a grammar error.
				texts.append(_("out of grammar error"))
			textList.extend(texts)
	# The line-prefix formatField attribute contains the text for a bullet or number for a list item, when the bullet or number does not appear in the actual text content.
	# Normally this attribute could be repeated across formatFields within a list item and therefore is not safe to speak when the unit is word or character.
	# However, some implementations (such as MS Word with UIA) do limit its useage to the very first formatField of the list item.
	# Therefore, they also expose a line-prefix_speakAlways attribute to allow its usage for any unit.
	linePrefix_speakAlways = attrs.get("line-prefix_speakAlways", False)
	if linePrefix_speakAlways or unit in (
		textInfos.UNIT_LINE,
		textInfos.UNIT_SENTENCE,
		textInfos.UNIT_PARAGRAPH,
		textInfos.UNIT_READINGCHUNK,
	):
		linePrefix = attrs.get("line-prefix")
		if linePrefix:
			textList.append(linePrefix)
	if attrsCache is not None:
		attrsCache.clear()
		attrsCache.update(attrs)
	types.logBadSequenceTypes(textList)
	return textList
'''


#: NVDA 2026.2, source/textInfos/__init__.py, ControlField.getPresentationCategory, word for word.
NVDA_PRESENTATION_CATEGORY = r'''
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


#: NVDA 2026.2, source/controlTypes/role.py, silentRolesOnFocus and silentValuesForRoles, word for word.
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
NVDA_SILENT_VALUES_FOR_ROLES = r'''
silentValuesForRoles: Set[Role] = {
	Role.CHECKBOX,
	Role.RADIOBUTTON,
	Role.LINK,
	Role.MENUITEM,
	Role.APPLICATION,
	Role.BUSY_INDICATOR,
}
'''


#: NVDA 2026.2, source/braille.py, getPropertiesBraille, word for word.
NVDA_PROPERTIES_BRAILLE = r'''
def getPropertiesBraille(**propertyValues) -> str:  # noqa: C901
	textList = []
	name = propertyValues.get("name")
	if name:
		textList.append(name)
	role: Optional[Union[controlTypes.Role, int]] = propertyValues.get("role")
	roleText = propertyValues.get("roleText")
	states = propertyValues.get("states")
	positionInfo = propertyValues.get("positionInfo")
	level = positionInfo.get("level") if positionInfo else None
	childControlCount = positionInfo.get("childControlCount") if positionInfo else None
	cellCoordsText = propertyValues.get("cellCoordsText")
	rowNumber = propertyValues.get("rowNumber")
	columnNumber = propertyValues.get("columnNumber")
	# When fetching row and column span
	# default the values to 1 to make further checks a lot simpler.
	# After all, a table cell that has no rowspan implemented is assumed to span one row.
	rowSpan = propertyValues.get("rowSpan") or 1
	columnSpan = propertyValues.get("columnSpan") or 1
	includeTableCellCoords = propertyValues.get("includeTableCellCoords", True)
	if role is not None and not roleText:
		role = controlTypes.Role(role)
		if role == controlTypes.Role.HEADING and level:
			# Translators: Displayed in braille for a heading with a level.
			# %s is replaced with the level.
			roleText = _("h%s") % level
			level = None
		elif role == controlTypes.Role.LINK and states and controlTypes.State.VISITED in states:
			states = states.copy()
			states.discard(controlTypes.State.VISITED)
			# Translators: Displayed in braille for a link which has been visited.
			roleText = _("vlnk")
		elif role == controlTypes.Role.LIST:
			if (
				states
				and controlTypes.State.MULTISELECTABLE in states
				and config.conf["presentation"]["reportMultiSelect"]
			):
				# Collapse the list role and multiselectable state into a single role text.
				# Note that for other cases where this state is found, regular processing with
				# controlTypes.processAndLabelStates will discard the state if necessary.
				states = states.copy()
				states.discard(controlTypes.State.MULTISELECTABLE)
				# Translators: Displayed in braille for a multi select list.
				roleText = _("mslst")
			else:
				roleText = roleLabels.get(role, role.displayString)
			if childControlCount:
				roleText += childControlCount
				childControlCount = None

		elif (
			name or cellCoordsText or rowNumber or columnNumber
		) and role in controlTypes.silentRolesOnFocus:
			roleText = None
		else:
			roleText = roleLabels.get(role, role.displayString)
	elif role is None:
		role = propertyValues.get("_role")
	value = propertyValues.get("value")
	if value and role not in controlTypes.silentValuesForRoles:
		textList.append(value)
	if states is not None:
		textList.extend(
			controlTypes.processAndLabelStates(
				role,
				states,
				controlTypes.OutputReason.FOCUS,
				states,
				None,
				positiveStateLabels,
				negativeStateLabels,
			),
		)
	if roleText:
		textList.append(roleText)

	errorMessage = propertyValues.get("errorMessage")
	if errorMessage:
		textList.append(errorMessage)

	description = propertyValues.get("description")
	if description:
		textList.append(description)
	hasDetails = propertyValues.get("hasDetails")
	if hasDetails:
		textList.append(_getAnnotationProperty(propertyValues))
	keyboardShortcut = propertyValues.get("keyboardShortcut")
	if keyboardShortcut:
		textList.append(keyboardShortcut)
	if positionInfo:
		indexInGroup = positionInfo.get("indexInGroup")
		similarItemsInGroup = positionInfo.get("similarItemsInGroup")
		if indexInGroup and similarItemsInGroup:
			# Translators: Brailled to indicate the position of an item in a group of items (such as a list).
			# {number} is replaced with the number of the item in the group.
			# {total} is replaced with the total number of items in the group.
			textList.append(_("{number} of {total}").format(number=indexInGroup, total=similarItemsInGroup))

		if level is not None:
			# Translators: Displayed in braille when an object (e.g. a tree view item) has a hierarchical level.
			# %s is replaced with the level.
			textList.append(_("lv %s") % positionInfo["level"])

	if rowNumber:
		if includeTableCellCoords and not cellCoordsText:
			if rowSpan > 1:
				# Translators: Displayed in braille for the table cell row numbers when a cell spans multiple rows.
				# Occurences of %s are replaced with the corresponding row numbers.
				rowStr = _("r{rowNumber}-{rowSpan}").format(
					rowNumber=rowNumber,
					rowSpan=rowNumber + rowSpan - 1,
				)
			else:
				# Translators: Displayed in braille for a table cell row number.
				# %s is replaced with the row number.
				rowStr = _("r{rowNumber}").format(rowNumber=rowNumber)
			textList.append(rowStr)
	if columnNumber:
		columnHeaderText = propertyValues.get("columnHeaderText")
		if columnHeaderText:
			textList.append(columnHeaderText)
		if includeTableCellCoords and not cellCoordsText:
			if columnSpan > 1:
				# Translators: Displayed in braille for the table cell column numbers when a cell spans multiple columns.
				# Occurences of %s are replaced with the corresponding column numbers.
				columnStr = _("c{columnNumber}-{columnSpan}").format(
					columnNumber=columnNumber,
					columnSpan=columnNumber + columnSpan - 1,
				)
			else:
				# Translators: Displayed in braille for a table cell column number.
				# %s is replaced with the column number.
				columnStr = _("c{columnNumber}").format(columnNumber=columnNumber)
			textList.append(columnStr)
	isCurrent = propertyValues.get("current", controlTypes.IsCurrent.NO)
	if isCurrent != controlTypes.IsCurrent.NO:
		textList.append(isCurrent.displayString)
	placeholder = propertyValues.get("placeholder", None)
	if placeholder:
		textList.append(placeholder)
	if includeTableCellCoords and cellCoordsText:
		textList.append(cellCoordsText)
	return TEXT_SEPARATOR.join([x for x in textList if x])
'''


#: NVDA 2026.2, source/config/configSpec.py, the [documentFormatting] section, word for word: NVDA's defaults.
NVDA_DOCUMENT_FORMATTING_SPEC = r'''
[documentFormatting]
	# These settings affect what information is reported when you navigate
	# to text where the formatting  or placement has changed
	detectFormatAfterCursor = boolean(default=false)
	reportFontName = boolean(default=false)
	reportFontSize = boolean(default=false)
	# 0: Off, 1: Speech, 2: Braille, 3: Speech and Braille
	fontAttributeReporting = integer(0, 3, default=0)
	reportRevisions = boolean(default=true)
	reportEmphasis = boolean(default=false)
	reportHighlight = boolean(default=true)
	reportSuperscriptsAndSubscripts = boolean(default=false)
	reportColor = boolean(default=False)
	reportTransparentColor = boolean(default=False)
	reportAlignment = boolean(default=false)
	reportLineSpacing = boolean(default=false)
	reportStyle = boolean(default=false)
	# Bitwise combination of none, some or all values of ReportSpellingErrors
	# 1: Speech, 2: Sound, 4: Braille
	reportSpellingErrors2 = integer(min=0, max=7, default=1)
	reportPage = boolean(default=true)
	reportLineNumber = boolean(default=False)
	# 0: Off, 1: Speech, 2: Tones, 3: Both Speech and Tones
	reportLineIndentation = integer(0, 3, default=0)
	ignoreBlankLinesForRLI = boolean(default=False)
	# Duration of indentation beeps, in milliseconds
	indentToneDuration = integer(min=10, max=2000, default=40)
	reportParagraphIndentation = boolean(default=False)
	reportTables = boolean(default=true)
	includeLayoutTables = boolean(default=False)
	# 0: Off, 1: Rows and columns, 2: Rows, 3: Columns
	reportTableHeaders = integer(0, 3, default=1)
	reportTableCellCoords = boolean(default=True)
	# 0: Off, 1: style, 2: color and style
	reportCellBorders = integer(0, 2, default=0)
	reportLinks = boolean(default=true)
	reportLinkType = boolean(default=true)
	reportGraphics = boolean(default=True)
	reportComments = boolean(default=true)
	reportBookmarks = boolean(default=true)
	reportLists = boolean(default=true)
	reportHeadings = boolean(default=true)
	reportBlockQuotes = boolean(default=true)
	reportGroupings = boolean(default=true)
	reportLandmarks = boolean(default=true)
	reportArticles = boolean(default=false)
	reportFrames = boolean(default=true)
	reportFigures = boolean(default=true)
	reportClickable = boolean(default=true)
'''


#: What the tester changed in NVDA's Document Formatting settings (the config in the log); the rest are NVDA's defaults.
TESTERS_CHANGES = {"autoLanguageSwitching": False, "reportLandmarks": True, "reportFrames": False, "reportArticles": True, "reportClickable": False}
#: The tester's presentation settings (the config in the log): object descriptions on; keyboard shortcuts as NVDA comes.
TESTERS_PRESENTATION = {"reportObjectDescriptions": True, "reportKeyboardShortcuts": True, "reportMultiSelect": True}
#: The line of the tester's message, and its address.
ADDRESS = "nvda-addons@nvda-addons.groups.io"
ON_BEHALF = "> On Behalf Of Alireza Mamani via groups.io\r"
#: What NVDA 2026.2 said for the line at Control+Home (the log, without its LangChangeCommand).
NVDA_SAID = ["heading level 1", "From: ", "link", ADDRESS, "heading level 1", " <", "link", ADDRESS, "heading level 1", ON_BEHALF]
#: The same line as the assistant has NVDA say it; JAWS said "From: Send Mail Link nvda-addons@... < Send Mail Link
#: nvda-addons@...> On Behalf Of Alireza Mamani via groups.io".
AS_JAWS = ["From: ", "send mail link", ADDRESS, " <", "send mail link", ADDRESS, ON_BEHALF]


def nvdaCode(source, name, namespace):
	"""Compile NVDA's own ``source`` against the imitation NVDA, and give back ``name`` from it."""
	scope = dict(namespace)
	exec(source, scope)
	return scope[name]


def indented(source):
	return textwrap.indent(source, "\t")


def nvdaDefaults(spec):
	"""NVDA's default Document Formatting settings, read from its configSpec."""
	defaults = {}
	for line in spec.splitlines():
		match = re.match(r"\s*(\w+) = \w+\(.*default=(\w+)\)", line)
		if match:
			name, value = match.groups()
			defaults[name] = {"true": True, "false": False}[value.lower()] if value.lower() in ("true", "false") else int(value)
	return defaults


# -- The imitation NVDA -------------------------------------------------------------------------------------------

ALL_NVDA_CODE = [value for name, value in dict(globals()).items() if name.startswith("NVDA_") and isinstance(value, str)]


def membersNamed(prefix, *extra):
	"""The members of one of NVDA's enums that its code here uses (``Role.LINK``), and ``extra``."""
	found = set(extra)
	for source in ALL_NVDA_CODE:
		found.update(re.findall(rf"\b{prefix}\.([A-Z][A-Z0-9_]*)\b", source))
	return sorted(found)


class Labelled(enum.Enum):
	"""An NVDA enum whose members say themselves: Role.LINK is "link", State.VISITED "visited"."""

	@property
	def displayString(self):
		return self.value

	@property
	def negativeDisplayString(self):
		return "not " + self.value


def labels(prefix, *extra, **spoken):
	names = membersNamed(prefix, *extra)
	return {name: spoken.get(name, name.lower().replace("_", " ")) for name in names}


Role = Labelled("Role", labels("Role", "DOCUMENT", "PANE", "ROOTPANE", "STATICTEXT", "BORDER", READONLY="read only"))
State = Labelled("State", labels("State", "READONLY", "LINKED", "FOCUSABLE", READONLY="read only"))


class OutputReason(enum.Enum):
	FOCUS = "focus"
	QUICKNAV = "quickNav"
	CARET = "caret"
	SAYALL = "sayAll"
	QUERY = "query"
	ONLYCACHE = "onlyCache"


class DescriptionFrom(enum.Enum):
	UNKNOWN = "unknown"
	ARIA_DESCRIPTION = "aria-description"
	TOOLTIP = "tooltip"


class IsCurrent(Labelled):
	NO = ""


class ReportTableHeaders(enum.IntEnum):
	OFF = 0
	ROWS_AND_COLUMNS = 1
	ROWS = 2
	COLUMNS = 3


class ReportCellBorders(enum.IntEnum):
	OFF = 0
	STYLE = 1
	COLOR_AND_STYLE = 2


class OutputMode(enum.IntFlag):
	SPEECH = 1
	BRAILLE = 2


class ReportSpellingErrors(enum.IntFlag):
	OFF = 0
	SPEECH = 1
	SOUND = 2
	BRAILLE = 4


def processAndLabelStates(role, states, reason, positiveStates=None, negativeStates=None, positiveStateLabelDict={}, negativeStateLabelDict={}):
	"""NVDA's controlTypes.processAndLabelStates, as far as the fields here go: the imitation's links have no states."""
	return [state.displayString for state in sorted(positiveStates or (), key=lambda state: state.name)]


controlTypes = types.SimpleNamespace(Role=Role, State=State, OutputReason=OutputReason, DescriptionFrom=DescriptionFrom, IsCurrent=IsCurrent)
controlTypes.processAndLabelStates = processAndLabelStates
controlTypes.silentRolesOnFocus = nvdaCode(NVDA_SILENT_ROLES_ON_FOCUS, "silentRolesOnFocus", {"Set": typing.Set, "Role": Role})
controlTypes.silentValuesForRoles = nvdaCode(NVDA_SILENT_VALUES_FOR_ROLES, "silentValuesForRoles", {"Set": typing.Set, "Role": Role})


class Field(dict):
	"""NVDA's textInfos.Field."""


class FormatField(Field):
	"""NVDA's textInfos.FormatField."""


class ControlField(Field):
	"""NVDA's textInfos.ControlField, with its own getPresentationCategory."""

	PRESCAT_SINGLELINE = "singleLine"
	PRESCAT_MARKER = "marker"
	PRESCAT_CONTAINER = "container"
	PRESCAT_CELL = "cell"
	PRESCAT_LAYOUT = None


class FieldCommand:
	"""NVDA's textInfos.FieldCommand."""

	def __init__(self, command, field):
		self.command, self.field = command, field

	def __repr__(self):
		return f"FieldCommand({self.command!r}, {self.field!r})"


textInfos = types.ModuleType("textInfos")
textInfos.Field, textInfos.FormatField, textInfos.ControlField, textInfos.FieldCommand = Field, FormatField, ControlField, FieldCommand
textInfos.TextInfo = types.SimpleNamespace(TextWithFieldsT=list)
textInfos.UNIT_CHARACTER, textInfos.UNIT_LINE, textInfos.UNIT_SENTENCE = "character", "line", "sentence"
textInfos.UNIT_PARAGRAPH, textInfos.UNIT_READINGCHUNK = "paragraph", "readingChunk"
textInfos.CommentType = enum.Enum("CommentType", "GENERIC DRAFT RESOLVED")
ControlField.getPresentationCategory = nvdaCode(NVDA_PRESENTATION_CATEGORY, "getPresentationCategory", {"OutputReason": OutputReason, "controlTypes": controlTypes})


class UIAHandler:
	"""The UI Automation ids NVDA uses here (UIAutomationClient's own numbers)."""

	UIA_StyleNameAttributeId = 40033
	UIA_StyleIdAttributeId = 40034
	StyleId_Custom = 70000
	StyleId_Heading1 = 70001
	StyleId_Heading2 = 70002
	StyleId_Heading9 = 70009
	StyleId_Normal = 70012
	UIA_ButtonControlTypeId = 50000
	UIA_HyperlinkControlTypeId = 50005
	UIA_ImageControlTypeId = 50006
	UIA_MenuItemControlTypeId = 50011
	UIA_TabItemControlTypeId = 50019
	UIA_TextControlTypeId = 50020
	UIA_CustomControlTypeId = 50025
	UIA_GroupControlTypeId = 50026
	UIA_SplitButtonControlTypeId = 50031


#: NVDA's UIAHandler module, with the same ids, for the assistant to import.
uiaModule = types.ModuleType("UIAHandler")
for _name, _value in vars(UIAHandler).items():
	if _name.startswith(("UIA_", "StyleId_")):
		setattr(uiaModule, _name, _value)


class Settings:
	"""NVDA's config.conf, as far as the code here reads it: the tester's settings."""

	def __init__(self):
		self.conf = {
			"documentFormatting": dict(nvdaDefaults(NVDA_DOCUMENT_FORMATTING_SPEC), **TESTERS_CHANGES),
			"presentation": dict(TESTERS_PRESENTATION),
			"annotations": {"reportAriaDescription": True, "reportDetails": True},
			"virtualBuffers": {"autoSayAllOnPageLoad": False},
		}


config = Settings()
nvdaLog = nvdaStubs.logging.getLogger("nvda")


def _(text):
	return text


def ngettext(one, many, count):
	return one if count == 1 else many


speechTypes = types.SimpleNamespace(logBadSequenceTypes=lambda sequence: None)
speechState = types.SimpleNamespace(oldTableID=None, oldRowNumber=None, oldRowSpan=None, oldColumnNumber=None, oldColumnSpan=None, oldTreeLevel=None)
speechNamespace = {
	"textInfos": textInfos,
	"controlTypes": controlTypes,
	"config": config,
	"OutputReason": OutputReason,
	"ReportTableHeaders": ReportTableHeaders,
	"ReportCellBorders": ReportCellBorders,
	"ReportSpellingErrors": ReportSpellingErrors,
	"OutputMode": OutputMode,
	"State": State,
	"Optional": typing.Optional,
	"Dict": typing.Dict,
	"List": typing.List,
	"Any": typing.Any,
	"Iterable": typing.Iterable,
	"SpeechSequence": list,
	"_AnnotationRolesT": tuple,
	"_speechState": speechState,
	"_rowAndColumnCountText": lambda rowCount, columnCount: None,
	"getKeyboardShortcutsSpeech": lambda keyboardShortcut: [keyboardShortcut] if keyboardShortcut else [],
	"getTableInfoSpeech": lambda tableInfo, oldTableInfo, extraDetail=False: [],
	"aria": types.SimpleNamespace(landmarkRoles={}),
	"log": nvdaLog,
	"types": speechTypes,
	"WaveFileCommand": lambda fileName: fileName,
	"_shouldReportOutOfError": lambda formatConfig: False,
	"_": _,
	"ngettext": ngettext,
}
for _source, _name in (
	(NVDA_PROPERTIES_SPEECH, "getPropertiesSpeech"),
	(NVDA_SPEAK_CONTENT_FIRST, "_shouldSpeakContentFirst"),
	(NVDA_CONTROL_FIELD_SPEECH, "getControlFieldSpeech"),
	(NVDA_FORMAT_FIELD_SPEECH, "getFormatFieldSpeech"),
):
	speechNamespace[_name] = nvdaCode(_source, _name, speechNamespace)
getControlFieldSpeech = speechNamespace["getControlFieldSpeech"]
getFormatFieldSpeech = speechNamespace["getFormatFieldSpeech"]
getPropertiesBraille = nvdaCode(
	NVDA_PROPERTIES_BRAILLE,
	"getPropertiesBraille",
	{
		"controlTypes": controlTypes,
		"config": config,
		"Optional": typing.Optional,
		"Union": typing.Union,
		"_": _,
		# NVDA 2026.2's braille.roleLabels, for a link.
		"roleLabels": {Role.LINK: "lnk"},
		"positiveStateLabels": {},
		"negativeStateLabels": {},
		"_getAnnotationProperty": lambda propertyValues: "",
		"TEXT_SEPARATOR": " ",
	},
)


def brailleOfField(field):
	"""How NVDA's braille shows a link's field where it starts: braille.getControlFieldBraille takes
	``roleText = field.get("roleTextBraille", field.get("roleText"))`` and gives it to getPropertiesBraille with the
	field's role and states (as _getControlFieldForReportStart does)."""
	roleText = field.get("roleTextBraille", field.get("roleText"))
	return getPropertiesBraille(role=field.get("role"), roleText=roleText, states=field.get("states"))


# -- Word's text through UI Automation -----------------------------------------------------------------------------


class Element:
	"""Word's UI Automation element for a link, as NVDA has it cached for its fields (IUIAutomationElement)."""

	def __init__(self, controlType, runtimeId):
		self.cachedControlType, self._runtimeId = controlType, runtimeId

	def getRuntimeId(self):
		return self._runtimeId


class Node:
	"""NVDA's object for an element of Word's text (NVDAObjects.UIA.wordDocument.WordDocumentNode): a link, whose
	value is where it goes (Word gives a link's address as its UI Automation value)."""

	def __init__(self, value, appName="outlook", controlType=UIAHandler.UIA_HyperlinkControlTypeId, role=Role.LINK, name="", runtimeId=(42, 1)):
		self.value, self.role, self.name = value, role, name
		self.appModule = types.SimpleNamespace(appName=appName)
		self.UIAElement = Element(controlType, runtimeId)
		self.UIAAutomationId = ""
		self.description = ""
		self.positionInfo = {}

	@property
	def states(self):
		# NVDA's UIA object gives a new set each time.
		return set()


class Run:
	"""A run of Word's text with one style (IUIAutomationTextRange): its text, UI Automation's StyleId for it and its
	style's name, and the link it is in."""

	def __init__(self, text, styleId=UIAHandler.StyleId_Normal, styleName="Normal", link=None):
		self.text, self.styleId, self.styleName, self.link = text, styleId, styleName, link
		self.asked = []

	def GetAttributeValue(self, attributeId):
		self.asked.append(attributeId)
		if attributeId == UIAHandler.UIA_StyleNameAttributeId:
			return self.styleName
		if attributeId == UIAHandler.UIA_StyleIdAttributeId:
			return self.styleId
		return None


#: UI Automation's value for an attribute a range has more than one of (UIAHandler.handler.ReservedMixedAttributeValue).
MIXED = object()
HEADING = UIAHandler.StyleId_Heading1


def fromLine(styleName="Normal", styleId=HEADING, address="mailto:" + ADDRESS):
	"""The From line of the message the tester's forwarded message quotes, as Word gives it: Word's Normal style with
	an outline level, which UI Automation calls heading 1, and two links in Word's Hyperlink style."""
	return [
		Run("From: ", styleId, styleName),
		Run(ADDRESS, UIAHandler.StyleId_Custom, "Hyperlink", link=Node(address, runtimeId=(42, 1))),
		Run(" <", styleId, styleName),
		Run(ADDRESS, UIAHandler.StyleId_Custom, "Hyperlink", link=Node(address, runtimeId=(42, 2))),
		Run(ON_BEHALF, styleId, styleName),
	]


class UIARemote:
	"""UI Automation remote operations, which Word's page numbers need; not here."""

	@staticmethod
	def isSupported():
		return False


class UIATextInfo:
	"""NVDA's NVDAObjects.UIA.UIATextInfo: NVDA 2026.2's own control fields and headings; the formatting of a run is
	its heading, as NVDA fetches it with the tester's settings (none of the others are on)."""

	UIAControlTypesWhereNameIsContent = nvdaCode(NVDA_UIA_NAME_IS_CONTENT, "UIAControlTypesWhereNameIsContent", {"UIAHandler": UIAHandler})

	def __init__(self, obj):
		self.obj = obj

	def _getFormatFieldAtRange(self, textRange, formatConfig, ignoreMixedValues=False):
		formatField = FormatField()
		if formatConfig["reportStyle"]:
			formatField["style"] = textRange.GetAttributeValue(UIAHandler.UIA_StyleNameAttributeId)
		if formatConfig["reportHeadings"]:
			self._getFormatFieldHeadings(textRange.GetAttributeValue, formatField)
		return FieldCommand("formatChange", formatField)


UIATextInfo._getControlFieldForUIAObject = nvdaCode(
	NVDA_UIA_CONTROL_FIELD,
	"_getControlFieldForUIAObject",
	{"textInfos": textInfos, "controlTypes": controlTypes},
)
UIATextInfo._getFormatFieldHeadings = nvdaCode(
	NVDA_UIA_FORMAT_FIELD_HEADINGS,
	"_getFormatFieldHeadings",
	{"textInfos": textInfos, "UIAHandler": UIAHandler, "Callable": typing.Callable},
)
#: NVDA's WordDocumentTextInfo, with NVDA 2026.2's own _getControlFieldForUIAObject and _getFormatFieldAtRange.
WordDocumentTextInfo = nvdaCode(
	"class WordDocumentTextInfo(UIATextInfo):\n" + indented(NVDA_WORD_CONTROL_FIELD) + indented(NVDA_WORD_FORMAT_FIELD_AT_RANGE),
	"WordDocumentTextInfo",
	{
		"UIATextInfo": UIATextInfo,
		"UIAHandler": UIAHandler,
		"controlTypes": controlTypes,
		"UIARemote": UIARemote,
		"log": nvdaLog,
	},
)
#: NVDA's own methods, which the assistant wraps.
NVDAS_CONTROL_FIELD = vars(WordDocumentTextInfo)["_getControlFieldForUIAObject"]
NVDAS_FORMAT_AT_RANGE = vars(WordDocumentTextInfo)["_getFormatFieldAtRange"]


class Document:
	"""NVDA's object for a Word document it reads through UI Automation: a message in classic Outlook
	(appModules.outlook.OutlookUIAWordDocument, with NVDA 2026.2's own isReadonlyViewer), or a document in Word."""

	def __init__(self, appName="outlook", readOnly=True):
		self.appModule = types.SimpleNamespace(appName=appName, productVersion="16.0.20326.20000")
		self.role = Role.DOCUMENT
		self.name = ""
		self._states = {State.READONLY} if readOnly else set()

	@property
	def states(self):
		return set(self._states)

	isReadonlyViewer = property(nvdaCode(NVDA_OUTLOOK_UIA_READONLY_VIEWER, "_get_isReadonlyViewer", {"controlTypes": controlTypes}))


class NVDA:
	"""The imitation NVDA saying a line of Word's text, as speech.getTextInfoSpeech does, as far as these fields go: the
	formatting before the text (initialFormat) and at each change, against what it said last in the document; each
	field where it starts and ends; and the text. NVDA drops the empty strings its field speech leaves (speech.speak)."""

	def __init__(self):
		self.formatConfig = config.conf["documentFormatting"]

	def fields(self, info, line):
		"""What WordDocumentTextInfo.getTextWithFields gives for ``line``: a link's field around its text, and each
		run's formatting before its text."""
		fields = []
		for run in line:
			if run.link:
				fields.append(FieldCommand("controlStart", info._getControlFieldForUIAObject(run.link)))
			fields.append(info._getFormatFieldAtRange(run, self.formatConfig))
			fields.append(run.text)
			if run.link:
				fields.append(FieldCommand("controlEnd", None))
		return fields

	def speakLine(self, document, line, reason=OutputReason.CARET):
		info = WordDocumentTextInfo(document)
		cache = FormatField()
		spoken, stack = [], []
		initialFormat = True
		for item in self.fields(info, line):
			if isinstance(item, str):
				spoken.append(item)
				initialFormat = False
			elif item.command == "formatChange":
				spoken.extend(getFormatFieldSpeech(item.field, cache, self.formatConfig, reason=reason, unit=textInfos.UNIT_LINE, initialFormat=initialFormat))
			elif item.command == "controlStart":
				spoken.extend(getControlFieldSpeech(item.field, list(stack), "start_addedToControlFieldStack", self.formatConfig, False, reason))
				stack.append(item.field)
			else:
				field = stack.pop()
				spoken.extend(getControlFieldSpeech(field, list(stack), "end_removedFromControlFieldStack", self.formatConfig, False, reason))
		return [item for item in spoken if item != ""]


# -- Browse mode coming into a message -----------------------------------------------------------------------------


class Position:
	"""A position in browse mode's text of the message (treeInterceptorHandler.RootProxyTextInfo)."""

	def __init__(self, obj, position, isCollapsed=True):
		self.obj, self.position, self.isCollapsed = obj, position, isCollapsed
		self.text = "From: nvda-addons@nvda-addons.groups.io" if not isCollapsed else ""
		self.unit = None

	def expand(self, unit):
		self.unit = unit


class Speech:
	"""NVDA's speech package, as browse mode uses it when it comes into a document: what it is asked to say."""

	def __init__(self):
		self.said = []
		self.module = types.ModuleType("speech")
		self.module.speakObject = lambda obj, reason=None, **kwargs: self.said.append(("object", obj, reason))
		self.module.speakObjectProperties = lambda obj, reason=None, **kwargs: self.said.append(("properties", obj, reason, tuple(sorted(kwargs))))
		self.module.speakTextInfo = self.speakTextInfo
		self.module.speakPreselectedText = lambda text, **kwargs: self.said.append(("selected", text))
		self.sayAll = types.ModuleType("speech.sayAll")
		self.sayAll.CURSOR = enum.IntEnum("CURSOR", {"CARET": 0, "REVIEW": 1, "TABLE": 2})
		self.readings = []
		self.readTextFails = False

		def readText(cursor, **kwargs):
			if self.readTextFails:
				raise RuntimeError("no say all")
			self.readings.append(cursor)
			self.said.append(("say all", cursor))

		self.sayAll.SayAllHandler = types.SimpleNamespace(readText=readText, isRunning=lambda: bool(self.readings))
		self.module.sayAll = self.sayAll

	def speakTextInfo(self, info, useCache=True, formatConfig=None, unit=None, reason=OutputReason.QUERY, **kwargs):
		self.said.append(("text", info.position, unit, reason))
		return True


class BrowseModeDocumentTreeInterceptor:
	"""NVDA's browseMode.BrowseModeDocumentTreeInterceptor for a message: NVDA 2026.2's own
	event_treeInterceptor_gainFocus, which the first time it comes into a document places the caret, then reads the
	document with "Automatic Say All on page load", or says the document and the line at the caret."""

	def __init__(self, root, passThrough=False, selected=False):
		self.rootNVDAObject = root
		self.passThrough = passThrough
		self._hadFirstGainFocus = False
		self.selection = Position(self, "caret", isCollapsed=not selected)
		self.documentConstantIdentifier = None
		self.focusEvents = []

	def event_gainFocus(self, obj, nextHandler):
		self.focusEvents.append(obj)

	def _getInitialCaretPos(self):
		# UI Automation's browse mode for Word starts where Word's caret is: the top of a message that has just opened.
		return None

	def makeTextInfo(self, position):
		return Position(self, position)


def browseModeModule(speech):
	"""NVDA's browseMode, with NVDA 2026.2's own event_treeInterceptor_gainFocus compiled against ``speech``, and the
	modules the assistant imports."""
	tree = type("BrowseModeDocumentTreeInterceptor", (BrowseModeDocumentTreeInterceptor,), {})
	tree.event_treeInterceptor_gainFocus = nvdaCode(
		NVDA_TREE_INTERCEPTOR_GAIN_FOCUS,
		"event_treeInterceptor_gainFocus",
		{
			"api": types.SimpleNamespace(getFocusObject=lambda: None, getFocusAncestors=lambda: [], getFocusDifferenceLevel=lambda: 0),
			"config": config,
			"speech": speech.module,
			"sayAll": speech.sayAll,
			"OutputReason": OutputReason,
			"textInfos": textInfos,
			"reportPassThrough": lambda treeInterceptor: None,
			"braille": types.SimpleNamespace(handler=types.SimpleNamespace(handleGainFocus=lambda obj: None)),
		},
	)
	browseMode = types.ModuleType("browseMode")
	browseMode.BrowseModeDocumentTreeInterceptor = tree
	return browseMode


def nvdaModules(speech, wordText=WordDocumentTextInfo):
	"""NVDA's modules, for the assistant to find: browse mode, speech, textInfos, controlTypes, and NVDA's UI Automation
	support for Word."""
	wordDocument = types.ModuleType("NVDAObjects.UIA.wordDocument")
	wordDocument.WordDocumentTextInfo = wordText
	modules = {
		"browseMode": browseModeModule(speech),
		"speech": speech.module,
		"speech.sayAll": speech.sayAll,
		"textInfos": textInfos,
		"controlTypes": controlTypes,
		"config": config,
		"UIAHandler": uiaModule,
		"NVDAObjects": types.ModuleType("NVDAObjects"),
		"NVDAObjects.UIA": types.ModuleType("NVDAObjects.UIA"),
		"NVDAObjects.UIA.wordDocument": wordDocument,
	}
	return modules


class Isolated(unittest.TestCase):
	"""Each test starts with the assistant off, NVDA's own methods in place, the tester's settings, and nothing logged."""

	def setUp(self):
		self.speech = Speech()
		self.modules = nvdaModules(self.speech)
		self.tree = self.modules["browseMode"].BrowseModeDocumentTreeInterceptor
		self.nvdasGainFocus = vars(self.tree)["event_treeInterceptor_gainFocus"]
		patches = [
			mock.patch.dict(sys.modules, self.modules),
			mock.patch.object(outlookMessages, "_enabled", False),
			mock.patch.object(outlookMessages, "_saying", False),
			mock.patch.object(outlookMessages, "_reading", False),
			mock.patch.object(outlookMessages, "_failed", False),
			mock.patch.object(outlookMessages, "_replaced", []),
			mock.patch.object(outlookMessages, "_notedStyles", set()),
			mock.patch.object(outlookMessages, "_notedMailLink", False),
			mock.patch.dict(config.conf["documentFormatting"], dict(nvdaDefaults(NVDA_DOCUMENT_FORMATTING_SPEC), **TESTERS_CHANGES)),
			mock.patch.dict(config.conf["virtualBuffers"], {"autoSayAllOnPageLoad": False}),
		]
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		self.addCleanup(setattr, WordDocumentTextInfo, "_getControlFieldForUIAObject", NVDAS_CONTROL_FIELD)
		self.addCleanup(setattr, WordDocumentTextInfo, "_getFormatFieldAtRange", NVDAS_FORMAT_AT_RANGE)
		self.nvda = NVDA()

	def turnOn(self):
		outlookMessages.register(reading=True)
		self.addCleanup(outlookMessages.unregister)

	def open(self, message=None, **kwargs):
		"""Open a message: browse mode comes into it for the first time. Gives back what NVDA was asked to say."""
		treeInterceptor = self.tree(message or Document(), **kwargs)
		treeInterceptor.event_treeInterceptor_gainFocus()
		return treeInterceptor, list(self.speech.said)


class OpeningAMessageTest(Isolated):
	def test_nvda_alone_says_the_document_and_the_line_at_the_caret(self):
		# What the tester's Outlook First Line Silence then dropped, so NVDA said nothing.
		treeInterceptor, said = self.open()
		self.assertEqual(said, [("object", treeInterceptor.rootNVDAObject, OutputReason.FOCUS), ("text", "caret", "line", OutputReason.CARET)])

	def test_the_message_is_read_from_the_top_as_jaws_reads_it(self):
		self.turnOn()
		treeInterceptor, said = self.open()
		self.assertEqual(
			said,
			[("object", treeInterceptor.rootNVDAObject, OutputReason.FOCUS), ("say all", self.speech.sayAll.CURSOR.CARET)],
			"NVDA reads from the caret where it said the line at it, as NVDA+Down Arrow does",
		)
		self.assertTrue(treeInterceptor._hadFirstGainFocus)
		self.assertIs(self.speech.module.speakTextInfo.__func__, Speech.speakTextInfo, "NVDA's speakTextInfo is back")

	def test_the_debug_log_says_so(self):
		self.turnOn()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.open()
		self.assertTrue(any("an Outlook message you opened is read from the top, as JAWS reads it" in line for line in logged.output), logged.output)

	def test_nvda_reading_it_already_reads_it_once(self):
		# "Automatic Say All on page load" on: NVDA reads it itself, and the assistant adds nothing.
		config.conf["virtualBuffers"]["autoSayAllOnPageLoad"] = True
		self.turnOn()
		treeInterceptor, said = self.open()
		self.assertEqual(self.speech.readings, [self.speech.sayAll.CURSOR.CARET])
		self.assertEqual(said[0][:3], ("properties", treeInterceptor.rootNVDAObject, OutputReason.FOCUS))

	def test_coming_back_to_an_open_message_is_as_before(self):
		self.turnOn()
		treeInterceptor, _said = self.open()
		self.speech.said.clear()
		treeInterceptor.event_treeInterceptor_gainFocus()
		self.assertEqual(self.speech.said, [("object", treeInterceptor.rootNVDAObject, OutputReason.FOCUS), ("text", "caret", "line", OutputReason.CARET)])
		self.assertEqual(len(self.speech.readings), 1, "read once, when it opened")

	def test_a_message_you_write_isnt_read(self):
		# NVDA reads Outlook messages in browse mode only when they are ones you read (isReadonlyViewer); should browse
		# mode come into one you write, it is said as NVDA says it.
		self.turnOn()
		treeInterceptor, said = self.open(Document(readOnly=False))
		self.assertEqual(said, [("object", treeInterceptor.rootNVDAObject, OutputReason.FOCUS), ("text", "caret", "line", OutputReason.CARET)])

	def test_word_and_other_programs_are_as_before(self):
		self.turnOn()
		for appName in ("winword", "msedge"):
			with self.subTest(appName=appName):
				self.speech.said.clear()
				treeInterceptor, said = self.open(Document(appName))
				self.assertEqual(said, [("object", treeInterceptor.rootNVDAObject, OutputReason.FOCUS), ("text", "caret", "line", OutputReason.CARET)])
		self.assertEqual(self.speech.readings, [])

	def test_focus_mode_reads_nothing(self):
		self.turnOn()
		_treeInterceptor, said = self.open(passThrough=True)
		self.assertEqual(said, [])

	def test_selected_text_is_said_as_before(self):
		self.turnOn()
		_treeInterceptor, said = self.open(selected=True)
		self.assertEqual(said[-1], ("selected", "From: nvda-addons@nvda-addons.groups.io"))
		self.assertEqual(self.speech.readings, [])

	def test_when_say_all_fails_nvda_says_the_line(self):
		self.turnOn()
		self.speech.readTextFails = True
		with self.assertLogs("nvda", level="DEBUG") as logged:
			treeInterceptor, said = self.open()
		self.assertEqual(said, [("object", treeInterceptor.rootNVDAObject, OutputReason.FOCUS), ("text", "caret", "line", OutputReason.CARET)])
		self.assertTrue(any("could not read an Outlook message from the top" in line for line in logged.output), logged.output)

	def test_with_another_addons_wrapper_around_it(self):
		# Outlook First Line Silence wraps the same method, before or after the assistant, without functools.wraps.
		def wrap(tree):
			original = vars(tree)["event_treeInterceptor_gainFocus"]

			def wrapper(self, *args, **kwargs):
				return original(self, *args, **kwargs)

			tree.event_treeInterceptor_gainFocus = wrapper
			return wrapper

		for addonFirst in (True, False):
			with self.subTest(addonFirst=addonFirst):
				self.speech.said.clear()
				self.speech.readings.clear()
				self.tree.event_treeInterceptor_gainFocus = self.nvdasGainFocus
				if addonFirst:
					wrap(self.tree)
				outlookMessages.register(reading=True)
				if not addonFirst:
					theirs = wrap(self.tree)
				try:
					self.open()
					self.assertEqual(self.speech.readings, [self.speech.sayAll.CURSOR.CARET])
					self.assertNotIn(("text", "caret", "line", OutputReason.CARET), self.speech.said)
				finally:
					outlookMessages.unregister()
				if not addonFirst:
					self.assertIs(vars(self.tree)["event_treeInterceptor_gainFocus"], theirs, "the other add-on's wrapper stays")
					self.speech.said.clear()
					self.open()
					self.assertIn(("text", "caret", "line", OutputReason.CARET), self.speech.said, "and the assistant's does nothing")
					outlookMessages.register(reading=True)
					self.speech.readings.clear()
					self.open()
					self.assertEqual(self.speech.readings, [self.speech.sayAll.CURSOR.CARET], "turned on again, read once")
					outlookMessages.unregister()


class LinkTest(Isolated):
	def said(self, line, document=None):
		return self.nvda.speakLine(document or Document(), line)

	def test_nvda_alone_says_link_and_heading_level_1(self):
		self.assertEqual(self.said(fromLine()), NVDA_SAID, "NVDA 2026.2 says the line as in the tester's log")

	def test_the_line_as_jaws_says_it(self):
		self.turnOn()
		self.assertEqual(self.said(fromLine()), AS_JAWS)

	def test_a_link_to_a_web_page_is_a_link(self):
		self.turnOn()
		self.assertEqual(self.said([Run("Auto Braille", UIAHandler.StyleId_Custom, "Hyperlink", link=Node("https://github.com/"))]), ["link", "Auto Braille"])

	def test_any_case_of_mailto(self):
		self.turnOn()
		self.assertEqual(self.said([Run(ADDRESS, UIAHandler.StyleId_Custom, "Hyperlink", link=Node(" MailTo:" + ADDRESS))]), ["send mail link", ADDRESS])

	def test_link_type_off_in_nvda_says_link(self):
		# NVDA's "Link type" unchecked: NVDA says no kind of link, so "link", as JAWS says "Link" with "Identify link type" off.
		self.turnOn()
		config.conf["documentFormatting"]["reportLinkType"] = False
		self.assertEqual(self.said(fromLine(styleName="Normal"))[1], "link")

	def test_links_off_in_nvda_say_nothing(self):
		self.turnOn()
		config.conf["documentFormatting"]["reportLinks"] = False
		self.assertEqual(self.said(fromLine()), ["From: ", ADDRESS, " <", ADDRESS, ON_BEHALF])

	def test_word_itself_is_as_before(self):
		self.turnOn()
		wordLine = [Run(ADDRESS, UIAHandler.StyleId_Custom, "Hyperlink", link=Node("mailto:" + ADDRESS, appName="winword"))]
		self.assertEqual(self.said(wordLine, Document("winword")), ["link", ADDRESS])

	def test_a_footnote_is_a_link_as_before(self):
		# Word's footnote and endnote marks: NVDA makes them links with their name as content, and no address.
		self.turnOn()
		info = WordDocumentTextInfo(Document())
		field = info._getControlFieldForUIAObject(Node(None, controlType=UIAHandler.UIA_CustomControlTypeId, role=Role.UNKNOWN, name="1"))
		self.assertEqual(field["role"], Role.LINK)
		self.assertNotIn("roleText", field)

	def test_braille_shows_the_link_as_before(self):
		self.turnOn()
		info = WordDocumentTextInfo(Document())
		field = info._getControlFieldForUIAObject(Node("mailto:" + ADDRESS))
		self.assertEqual(field["roleText"], "send mail link")
		self.assertEqual(brailleOfField(field), "lnk", "braille shows a link as NVDA does")
		withoutBraille = dict(field)
		del withoutBraille["roleTextBraille"]
		self.assertEqual(brailleOfField(withoutBraille), "send mail link", "which roleText alone would have changed")

	def test_the_debug_log_names_the_address_once(self):
		self.turnOn()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.said(fromLine())
			self.said(fromLine())
		notes = [line for line in logged.output if "send mail link" in line]
		self.assertEqual(len(notes), 1, logged.output)
		self.assertIn(repr("mailto:" + ADDRESS), notes[0])


class HeadingTest(Isolated):
	def said(self, line, document=None):
		return self.nvda.speakLine(document or Document(), line)

	def test_a_heading_style_is_said_as_a_heading(self):
		self.turnOn()
		headline = [Run("HEADLINES\r", UIAHandler.StyleId_Heading1, "Heading 1")]
		self.assertEqual(self.said(headline), ["heading level 1", "HEADLINES\r"])
		german = [Run("Nachrichten\r", UIAHandler.StyleId_Heading2, "Überschrift 2")]
		self.assertEqual(self.said(german), ["heading level 2", "Nachrichten\r"])

	def test_a_heading_level_in_another_style_isnt(self):
		self.turnOn()
		for styleName in ("Normal", "Standard", "Plain Text", "Heading 10"):
			with self.subTest(styleName=styleName):
				self.assertEqual(self.said([Run("From: someone\r", HEADING, styleName)]), ["From: someone\r"])

	def test_a_range_of_more_than_one_style_is_as_before(self):
		self.turnOn()
		self.assertEqual(self.said([Run("From: someone\r", HEADING, MIXED)]), ["heading level 1", "From: someone\r"])

	def test_word_itself_is_as_before(self):
		self.turnOn()
		self.assertEqual(self.said([Run("From: someone\r", HEADING, "Normal")], Document("winword")), ["heading level 1", "From: someone\r"])

	def test_with_styles_on_nvda_asks_word_nothing_more(self):
		self.turnOn()
		config.conf["documentFormatting"]["reportStyle"] = True
		run = Run("From: someone\r", HEADING, "Normal")
		self.assertEqual(self.said([run]), ["style Normal", "From: someone\r"])
		self.assertEqual(run.asked.count(UIAHandler.UIA_StyleNameAttributeId), 1, "only NVDA's own question")

	def test_headings_off_in_nvda_ask_word_nothing(self):
		self.turnOn()
		config.conf["documentFormatting"]["reportHeadings"] = False
		run = Run("From: someone\r", HEADING, "Normal")
		self.assertEqual(self.said([run]), ["From: someone\r"])
		self.assertEqual(run.asked, [])

	def test_the_debug_log_names_each_style_once(self):
		self.turnOn()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.said(fromLine())
			self.said([Run("HEADLINES\r", HEADING, "Heading 1")])
			self.said([Run("HEADLINES\r", HEADING, "Heading 1")])
		dropped = [line for line in logged.output if "isn't said as heading level 1" in line]
		kept = [line for line in logged.output if "is said as heading level 1" in line]
		self.assertEqual(len(dropped), 1, logged.output)
		self.assertIn("'Normal'", dropped[0])
		self.assertEqual(len(kept), 1, logged.output)
		self.assertIn("'Heading 1'", kept[0])

	def test_turned_off_nvda_says_them_as_it_does(self):
		self.turnOn()
		outlookMessages.unregister()
		self.assertIs(vars(WordDocumentTextInfo)["_getFormatFieldAtRange"], NVDAS_FORMAT_AT_RANGE)
		self.assertIs(vars(WordDocumentTextInfo)["_getControlFieldForUIAObject"], NVDAS_CONTROL_FIELD)
		self.assertEqual(self.said(fromLine()), NVDA_SAID)


class IsHeadingStyleTest(unittest.TestCase):
	def test_names(self):
		for name, level, expected in (
			("Heading 1", 1, True),
			("heading 3", 3, True),
			("Überschrift 1", 1, True),
			("Titre 2", 2, True),
			("見出し 1", 1, True),
			("Heading 1,H1", 1, True),
			("Heading 1", 2, False),
			("Heading 12", 1, False),
			("Normal", 1, False),
			("MsoNormal", 1, False),
		):
			with self.subTest(name=name, level=level):
				self.assertIs(outlookMessages.isHeadingStyle(name, level), expected)


class RegisterTest(Isolated):
	def test_register_and_unregister(self):
		outlookMessages.register(reading=True)
		self.assertTrue(outlookMessages.isRegistered())
		installed = {name: vars(owner)[name] for owner, name in ((self.tree, "event_treeInterceptor_gainFocus"), (WordDocumentTextInfo, "_getControlFieldForUIAObject"), (WordDocumentTextInfo, "_getFormatFieldAtRange"))}
		self.assertIs(getattr(installed["event_treeInterceptor_gainFocus"], outlookMessages.ORIGINAL), self.nvdasGainFocus)
		self.assertIs(getattr(installed["_getControlFieldForUIAObject"], outlookMessages.ORIGINAL), NVDAS_CONTROL_FIELD)
		self.assertIs(getattr(installed["_getFormatFieldAtRange"], outlookMessages.ORIGINAL), NVDAS_FORMAT_AT_RANGE)
		outlookMessages.register(reading=True)
		self.assertIs(vars(self.tree)["event_treeInterceptor_gainFocus"], installed["event_treeInterceptor_gainFocus"], "registered twice, wrapped once")
		outlookMessages.unregister()
		self.assertFalse(outlookMessages.isRegistered())
		self.assertIs(vars(self.tree)["event_treeInterceptor_gainFocus"], self.nvdasGainFocus)
		self.assertIs(vars(WordDocumentTextInfo)["_getControlFieldForUIAObject"], NVDAS_CONTROL_FIELD)
		self.assertIs(vars(WordDocumentTextInfo)["_getFormatFieldAtRange"], NVDAS_FORMAT_AT_RANGE)

	def test_without_nvdas_uia_support_for_word_messages_are_still_read(self):
		with mock.patch.dict(sys.modules, {"NVDAObjects.UIA.wordDocument": None}):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				outlookMessages.register(reading=True)
		self.addCleanup(outlookMessages.unregister)
		self.assertTrue(outlookMessages.isRegistered())
		self.assertTrue(any("can't change how NVDA says links, lists and headings in Outlook messages" in line for line in logged.output), logged.output)
		self.open()
		self.assertEqual(self.speech.readings, [self.speech.sayAll.CURSOR.CARET])

	def test_an_nvda_without_the_event_still_says_links_and_headings_as_jaws(self):
		bare = type("BrowseModeDocumentTreeInterceptor", (), {})
		browseMode = types.ModuleType("browseMode")
		browseMode.BrowseModeDocumentTreeInterceptor = bare
		with mock.patch.dict(sys.modules, {"browseMode": browseMode}):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				outlookMessages.register(reading=True)
		self.addCleanup(outlookMessages.unregister)
		self.assertNotIn("event_treeInterceptor_gainFocus", vars(bare))
		self.assertTrue(any("NVDA has no BrowseModeDocumentTreeInterceptor.event_treeInterceptor_gainFocus" in line for line in logged.output), logged.output)
		self.assertTrue(outlookMessages.isRegistered())
		self.assertEqual(NVDA().speakLine(Document(), fromLine()), AS_JAWS)

	def test_what_couldnt_be_put_in_place_is_put_in_place_later(self):
		# NVDA's UI Automation support for Word wasn't there the first time: turned on again, it is.
		with mock.patch.dict(sys.modules, {"NVDAObjects.UIA.wordDocument": None}):
			outlookMessages.register(reading=True)
		self.addCleanup(outlookMessages.unregister)
		self.assertIs(vars(WordDocumentTextInfo)["_getFormatFieldAtRange"], NVDAS_FORMAT_AT_RANGE)
		outlookMessages.register(reading=True)
		self.assertIs(getattr(vars(WordDocumentTextInfo)["_getFormatFieldAtRange"], outlookMessages.ORIGINAL), NVDAS_FORMAT_AT_RANGE)
		self.assertEqual(NVDA().speakLine(Document(), fromLine()), AS_JAWS)

	def test_an_nvda_without_its_text_and_roles_changes_nothing(self):
		with mock.patch.dict(sys.modules, {"textInfos": None}):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				outlookMessages.register(reading=True)
		self.assertFalse(outlookMessages.isRegistered())
		self.assertIs(vars(self.tree)["event_treeInterceptor_gainFocus"], self.nvdasGainFocus)
		self.assertIs(vars(WordDocumentTextInfo)["_getFormatFieldAtRange"], NVDAS_FORMAT_AT_RANGE)
		self.assertTrue(any("can't have NVDA read Outlook messages as JAWS does" in line for line in logged.output), logged.output)


class SettingTest(unittest.TestCase):
	def test_on_unless_turned_off(self):
		self.assertTrue(outlookMessages.wanted({}))
		self.assertTrue(outlookMessages.wanted(dict(state.DEFAULTS)))
		self.assertFalse(outlookMessages.wanted({outlookMessages.STATE_KEY: False}))
		self.assertFalse(outlookMessages.wanted(None))
		self.assertIs(state.DEFAULTS[outlookMessages.STATE_KEY], True)

	def test_nvdas_defaults(self):
		# The tester's config changes none of these: NVDA says headings, links and their type, and doesn't read a
		# document when it opens (the tester's "Automatic Say All on page load" is off, from JAWS's web setting).
		defaults = nvdaDefaults(NVDA_DOCUMENT_FORMATTING_SPEC)
		self.assertIs(defaults["reportHeadings"], True)
		self.assertIs(defaults["reportLinks"], True)
		self.assertIs(defaults["reportLinkType"], True)
		self.assertIs(defaults["reportStyle"], False)


if __name__ == "__main__":
	unittest.main()
