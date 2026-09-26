# Unit tests for version 1.24, from a tester's report (issue 18): "It says page one section 1 when in a outlook
# message. Jaws doesn't say that." The tester was writing a message in classic Outlook, Office 16.0.20326, which NVDA
# reads through UI Automation ("Using UIA due to suitable Office version: (16, 0, 20326)"). The log attached to the
# issue (NVDA log 2026-09-26 09.15.29.zip) shows:
# 09:15:00.432 Input: kb(laptop):control+home
# 09:15:00.600 Speaking [LangChangeCommand ('en_US'), 'page 1', 'section 1', 'Have you set it to auto check yet?  I didn’t
#              know a human is behind this 😊  lol.  \r']
# and its nvda-old.log the same at 08:33:35, Enter after "answers:" at the top of a reply ('page 1', 'section 1'
# alone), and at 08:34:43, Up Arrow into another reply ('page 1', 'section 1', 'That is now fixed as you can see.\r').
# NVDA's Outlook support leaves page numbers out only through Word's object model (appModules/outlook.py,
# OutlookWordDocument.ignorePageNumbers). Through UI Automation, WordDocumentTextInfo asks Word for the page and section
# of each line, and speech.getFormatFieldSpeech says them when they differ from what it said last. JAWS says no page,
# section or column while Outlook is active (WordFunc.jss, PageSectionColumnChangedEvent, "|| OutlookIsActive()").
# - outlookPages: in Outlook, NVDA's UI Automation text of a Word document has no page, section or text column numbers.
#   Word itself keeps them, and the rest of the formatting is as before.
# The imitation NVDA runs NVDA 2026.2's own WordDocumentTextInfo.getTextWithFields and _getFormatFieldAtRange,
# RootProxyTextInfo.getTextWithFields and speech.getFormatFieldSpeech, word for word, with the Document Formatting
# defaults of NVDA's configSpec, against an imitation of Word's text through UI Automation. The assistant's code is the
# real one.
# Run: python -m unittest tests.test_v124_outlookPages -v

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

from jawsMigrator import outlookPages, state  # noqa: E402


#: NVDA 2026.2, source/NVDAObjects/UIA/wordDocument.py, UIACustomAttributeID, word for word.
NVDA_CUSTOM_ATTRIBUTE_ID = r'''
class UIACustomAttributeID(enum.IntEnum):
	LINE_NUMBER = 0
	PAGE_NUMBER = 1
	COLUMN_NUMBER = 2
	SECTION_NUMBER = 3
	BOOKMARK_NAME = 4
	COLUMNS_IN_SECTION = 5
	EXPAND_COLLAPSE_STATE = 6
'''


#: NVDA 2026.2, source/NVDAObjects/UIA/wordDocument.py, EXPAND_COLLAPSE_STATE, word for word.
NVDA_EXPAND_COLLAPSE_STATE = r'''
class EXPAND_COLLAPSE_STATE(enum.IntEnum):
	COLLAPSED = 0
	EXPANDED = 1
'''


#: NVDA 2026.2, source/NVDAObjects/UIA/wordDocument.py, WordDocumentTextInfo.getTextWithFields, word for word.
NVDA_WORD_GET_TEXT_WITH_FIELDS = r'''
def getTextWithFields(  # noqa: C901
	self,
	formatConfig: Optional[Dict] = None,
) -> textInfos.TextInfo.TextWithFieldsT:
	fields = None
	# #11043: when a non-collapsed text range is positioned within a blank table cell
	# MS Word does not return the table  cell as an enclosing element,
	# Thus NVDa thinks the range is not inside the cell.
	# This can be detected by asking for the first 2 characters of the range's text,
	# Which will either be an empty string, or the single end-of-row mark.
	# Anything else means it is not on an empty table cell,
	# or the range really does span more than the cell itself.
	# If this situation is detected,
	# copy and collapse the range, and fetch the content from that instead,
	# As a collapsed range on an empty cell does correctly return the table cell as its first enclosing element.
	if not self.isCollapsed:
		rawText = self._rangeObj.GetText(2)
		if not rawText or rawText == END_OF_ROW_MARK:
			r = self.copy()
			r.end = r.start
			fields = super(WordDocumentTextInfo, r).getTextWithFields(formatConfig=formatConfig)
	if fields is None:
		fields = super().getTextWithFields(formatConfig=formatConfig)
	if len(fields) == 0:
		# Nothing to do... was probably a collapsed range.
		return fields

	# MS Word tries to produce speakable math content within equations.
	# However, using math presentation providers with the exposed mathml property on the equation is much nicer.
	# But, we therefore need to remove the inner math content if reading by line
	if not formatConfig or not formatConfig.get("extraDetail"):
		# We really only want to remove content if we can guarantee that a math presentation provider is available.
		if mathPres.speechProvider or mathPres.brailleProvider:
			curLevel = 0
			mathLevel = None
			mathStartIndex = None
			index = 0
			# we delete items from 'fields' in the loop, so we can't use a for loop
			while index < len(fields):
				field = fields[index]
				if isinstance(field, textInfos.FieldCommand) and field.command == "controlStart":
					curLevel += 1
					if field.field.get("mathml"):
						mathLevel = curLevel
						mathStartIndex = index
				elif isinstance(field, textInfos.FieldCommand) and field.command == "controlEnd":
					if curLevel == mathLevel and field.field.get("mathml"):
						del fields[mathStartIndex + 1 : index]
						index = mathStartIndex + 1
					curLevel -= 1
				index += 1

	# Sometimes embedded objects and graphics In MS Word can cause a controlStart then a controlEnd with no actual formatChange / text in the middle.
	# SpeakTextInfo always expects that the first lot of controlStarts will always contain some text.
	# Therefore ensure that the first lot of controlStarts does contain some text by inserting a blank formatChange and empty string in this case.
	for index in range(len(fields)):
		field = fields[index]
		if isinstance(field, textInfos.FieldCommand) and field.command == "controlStart":
			continue
		elif isinstance(field, textInfos.FieldCommand) and field.command == "controlEnd":
			formatChange = textInfos.FieldCommand("formatChange", textInfos.FormatField())
			fields.insert(index, formatChange)
			fields.insert(index + 1, "")
		break
	##7971: Microsoft Word exposes list bullets as part of the actual text.
	# This then confuses NVDA's braille cursor routing as it expects that there is a one-to-one mapping between characters in the text string and   unit character moves.
	# Therefore, detect when at the start of a list, and strip the bullet from the text string, placing it in the text's formatField as line-prefix.
	listItemStarted = False
	lastFormatField = None
	for index in range(len(fields)):
		field = fields[index]
		if isinstance(field, textInfos.FieldCommand) and field.command == "controlStart":
			if field.field.get("role") == controlTypes.Role.LISTITEM and field.field.get("_startOfNode"):
				# We are in the start of a list item.
				listItemStarted = True
		elif isinstance(field, textInfos.FieldCommand) and field.command == "formatChange":
			# This is the most recent formatField we have seen.
			lastFormatField = field.field
		elif listItemStarted and isinstance(field, str):
			# This is the first text string within the list.
			# Remove the text up to the first space, and store it as line-prefix which NVDA will appropriately speak/braille as a bullet.
			try:
				spaceIndex = field.index(" ")
			except ValueError:
				log.debugWarning("No space found in this text string")
				break
			prefix = field[0:spaceIndex]
			fields[index] = field[spaceIndex + 1 :]
			lastFormatField["line-prefix"] = prefix
			# Let speech know that line-prefix is safe to be spoken always, as it will only be exposed on the very first formatField on the list item.
			lastFormatField["line-prefix_speakAlways"] = True
			break
		else:
			# Not a controlStart, formatChange or text string. Nothing to do.
			break
	# Fill in page number attributes where NVDA expects
	# Get page number from control field (automation ID), which is reliable.
	# Only use page numbers from control fields, not format fields,
	# as format fields may have invalid values from Custom Attributes API.
	page = None
	if (
		len(fields) > 0
		and isinstance(fields[0], textInfos.FieldCommand)
		and fields[0].command == "controlStart"
		and isinstance(fields[0].field, textInfos.ControlField)
	):
		page = fields[0].field.get("page-number")
		# Convert to int to match the type used by Custom Attributes API
		# Control fields extract page numbers as strings from automation IDs
		if page is not None:
			try:
				page = int(page)
			except (ValueError, TypeError):
				page = None
	if page is not None:
		# Propagate control field page number to format fields that don't already have one.
		# This serves as a fallback when the Custom Attributes API returns invalid values,
		# particularly when navigating backwards to the first line of a page.
		for field in fields:
			if isinstance(field, textInfos.FieldCommand) and isinstance(
				field.field,
				textInfos.FormatField,
			):
				# Only set if not already set by Custom Attributes API
				if "page-number" not in field.field:
					field.field["page-number"] = page
	# MS Word can sometimes return a higher ancestor in its textRange's children.
	# E.g. a table inside a table header.
	# This does not cause a loop, but does cause information to be doubled
	# Detect these duplicates and remove them from the generated fields.
	seenStarts = set()
	pendingRemoves = []
	index = 0
	for index, field in enumerate(fields):
		if isinstance(field, textInfos.FieldCommand) and field.command == "controlStart":
			runtimeID = field.field["runtimeID"]
			if not runtimeID:
				continue
			if runtimeID in seenStarts:
				pendingRemoves.append(field.field)
			else:
				seenStarts.add(runtimeID)
		elif seenStarts:
			seenStarts.clear()
	index = 0
	while index < len(fields):
		field = fields[index]
		if isinstance(field, textInfos.FieldCommand) and any(x is field.field for x in pendingRemoves):
			del fields[index]
		else:
			index += 1
	return fields
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


#: NVDA 2026.2, source/treeInterceptorHandler.py, RootProxyTextInfo.getTextWithFields, word for word.
NVDA_ROOT_PROXY_GET_TEXT_WITH_FIELDS = r'''
def getTextWithFields(self, formatConfig: Optional[Dict] = None) -> textInfos.TextInfo.TextWithFieldsT:
	return self.innerTextInfo.getTextWithFields(formatConfig=formatConfig)
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


#: What NVDA's END_OF_ROW_MARK holds (source/NVDAObjects/UIA/wordDocument.py).
END_OF_ROW_MARK = "\x07"
#: What the tester changed in NVDA's Document Formatting settings (the config in the log); the rest are NVDA's defaults.
TESTERS_CHANGES = {"autoLanguageSwitching": False, "reportLandmarks": True, "reportFrames": False, "reportArticles": True, "reportClickable": False}
#: The lines of the tester's log.
CONTROL_HOME = "Have you set it to auto check yet?  I didn’t know a human is behind this 😊  lol.  \r"
REPLY = "That is now fixed as you can see.\r"


def nvdaCode(source, name, namespace):
	"""Compile NVDA's own ``source`` against the imitation NVDA, and give back ``name`` from it."""
	scope = dict(namespace)
	exec(source, scope)
	return scope[name]


def nvdaDefaults(spec):
	"""NVDA's default Document Formatting settings, read from its configSpec."""
	defaults = {}
	for line in spec.splitlines():
		match = re.match(r"\s*(\w+) = \w+\(.*default=(\w+)\)", line)
		if match:
			name, value = match.groups()
			defaults[name] = {"true": True, "false": False}[value.lower()] if value.lower() in ("true", "false") else int(value)
	return defaults


class Field(dict):
	"""NVDA's textInfos.Field."""


class FormatField(Field):
	"""NVDA's textInfos.FormatField."""


class ControlField(Field):
	"""NVDA's textInfos.ControlField."""


class FieldCommand:
	"""NVDA's textInfos.FieldCommand."""

	def __init__(self, command, field):
		self.command, self.field = command, field

	def __repr__(self):
		return f"FieldCommand({self.command!r}, {self.field!r})"


class CommentType(enum.Enum):
	GENERIC = "generic"
	DRAFT = "draft"
	RESOLVED = "resolved"


textInfos = types.ModuleType("textInfos")
textInfos.Field, textInfos.FormatField, textInfos.ControlField, textInfos.FieldCommand = Field, FormatField, ControlField, FieldCommand
textInfos.TextInfo = types.SimpleNamespace(TextWithFieldsT=list)
textInfos.CommentType = CommentType
textInfos.UNIT_CHARACTER, textInfos.UNIT_LINE, textInfos.UNIT_SENTENCE = "character", "line", "sentence"
textInfos.UNIT_PARAGRAPH, textInfos.UNIT_READINGCHUNK = "paragraph", "readingChunk"


class Role(enum.Enum):
	LISTITEM = "list item"


class OutputReason(enum.Enum):
	FOCUS = "focus"
	QUICKNAV = "quickNav"
	CARET = "caret"
	SAYALL = "sayAll"


class State(enum.Enum):
	COLLAPSED = "collapsed"

	@property
	def displayString(self):
		return self.value


class ReportCellBorders(enum.IntEnum):
	OFF = 0
	STYLE = 1
	COLOR_AND_STYLE = 2


class OutputMode(enum.IntFlag):
	SPEECH = 1
	BRAILLE = 2


class ReportSpellingErrors(enum.IntFlag):
	SPEECH = 1
	SOUND = 2
	BRAILLE = 4


controlTypes = types.SimpleNamespace(Role=Role, OutputReason=OutputReason, State=State)
nvdaLog = nvdaStubs.logging.getLogger("nvda")
wordIds = {"enum": enum}
UIACustomAttributeID = nvdaCode(NVDA_CUSTOM_ATTRIBUTE_ID, "UIACustomAttributeID", wordIds)
EXPAND_COLLAPSE_STATE = nvdaCode(NVDA_EXPAND_COLLAPSE_STATE, "EXPAND_COLLAPSE_STATE", wordIds)


class Line:
	"""A line of a Word document, as Word gives it through UI Automation: its text, and the page, section and line
	number it is on."""

	def __init__(self, text, page=1, section=1, number=1):
		self.text, self.page, self.section, self.number = text, page, section, number


class Range:
	"""Word's UI Automation text range for a line (IUIAutomationTextRange), as far as NVDA asks it here."""

	def __init__(self, line):
		self.line = line

	def GetText(self, maxLength):
		return self.line.text if maxLength < 0 else self.line.text[:maxLength]


class Word:
	"""Word's custom text attributes, as NVDA fetches them with UI Automation's remote operations (UIAHandler.remote):
	the page, section and line number of a range. Word gives -1 for a page it can't tell."""

	def __init__(self):
		self.pageUnknown = False

	def isSupported(self):
		return True

	def msWord_getCustomAttributeValue(self, docElement, textRange, customAttribID):
		line = textRange.line
		if customAttribID == UIACustomAttributeID.PAGE_NUMBER:
			return -1 if self.pageUnknown else line.page
		if customAttribID == UIACustomAttributeID.SECTION_NUMBER:
			return line.section
		if customAttribID == UIACustomAttributeID.LINE_NUMBER:
			return line.number
		return None


word = Word()


class Document:
	"""NVDA's object for a Word document it reads through UI Automation: the text of a message in classic Outlook
	(appModules.outlook.OutlookUIAWordDocument), or a document in Word."""

	def __init__(self, appName="outlook", pageElements=True):
		self.appModule = types.SimpleNamespace(appName=appName, productVersion="16.0.20326.20000")
		self.UIAElement = object()
		#: Whether Word's UI Automation tree has the page around the text, an element whose automation id is
		#: UIA_AutomationId_Word_Page_1: NVDA gives the line that page's number from it.
		self.pageElements = pageElements
		#: What NVDA noted of the formatting it said last in this document (speech's formatFieldAttributesCache).
		self.formatCache = Field()


class UIATextInfo:
	"""NVDA's NVDAObjects.UIA.UIATextInfo, as far as a line of Word's text goes: the page it is in, as a control field
	with the page's number where Word's tree has one (WordDocumentTextInfo._getControlFieldForUIAObject), then the line's
	formatting from UI Automation's own attributes, here its font, then its text."""

	isCollapsed = False

	def __init__(self, obj, line):
		self.obj, self.line, self._rangeObj = obj, line, Range(line)

	def copy(self):
		return type(self)(self.obj, self.line)

	def getTextWithFields(self, formatConfig=None):
		if not formatConfig:
			formatConfig = NVDA.defaults()
		page = ControlField(runtimeID=(42, 4, self.line.page))
		if self.obj.pageElements:
			page["page-number"] = f"UIA_AutomationId_Word_Page_{self.line.page}".rsplit("_", 1)[-1]
		return [
			FieldCommand("controlStart", page),
			self._getFormatFieldAtRange(self._rangeObj, formatConfig),
			self.line.text,
			FieldCommand("controlEnd", None),
		]

	def _getFormatFieldAtRange(self, textRange, formatConfig, ignoreMixedValues=False):
		return FieldCommand("formatChange", FormatField({"font-name": "Aptos", "font-size": "12 pt"}))


def indented(source):
	return textwrap.indent(source, "\t")


#: NVDA's WordDocumentTextInfo, with NVDA 2026.2's own getTextWithFields and _getFormatFieldAtRange.
WordDocumentTextInfo = nvdaCode(
	"class WordDocumentTextInfo(UIATextInfo):\n" + indented(NVDA_WORD_GET_TEXT_WITH_FIELDS) + indented(NVDA_WORD_FORMAT_FIELD_AT_RANGE),
	"WordDocumentTextInfo",
	{
		"UIATextInfo": UIATextInfo,
		"Optional": typing.Optional,
		"Dict": typing.Dict,
		"textInfos": textInfos,
		"END_OF_ROW_MARK": END_OF_ROW_MARK,
		"mathPres": types.SimpleNamespace(speechProvider=None, brailleProvider=None),
		"controlTypes": controlTypes,
		"log": nvdaLog,
		"UIARemote": word,
		"UIACustomAttributeID": UIACustomAttributeID,
		"EXPAND_COLLAPSE_STATE": EXPAND_COLLAPSE_STATE,
	},
)
#: NVDA's own getTextWithFields, which the assistant wraps.
NVDAS_OWN = vars(WordDocumentTextInfo)["getTextWithFields"]


class RootProxyTextInfo:
	"""NVDA's treeInterceptorHandler.RootProxyTextInfo: the text of browse mode in a message you read, which is its
	document's text."""

	def __init__(self, innerTextInfo):
		self.innerTextInfo = innerTextInfo


RootProxyTextInfo.getTextWithFields = nvdaCode(
	NVDA_ROOT_PROXY_GET_TEXT_WITH_FIELDS,
	"getTextWithFields",
	{"Optional": typing.Optional, "Dict": typing.Dict, "textInfos": textInfos},
)


def getTableInfoSpeech(tableInfo, oldTableInfo, extraDetail=False):
	"""NVDA's speech.getTableInfoSpeech, outside a table: nothing."""
	return []


class NVDA:
	"""The imitation NVDA: its Document Formatting settings as the tester has them, and its speech of a line."""

	@staticmethod
	def defaults():
		return dict(nvdaDefaults(NVDA_DOCUMENT_FORMATTING_SPEC), **TESTERS_CHANGES)

	def __init__(self):
		self.formatConfig = self.defaults()
		self.getFormatFieldSpeech = nvdaCode(
			NVDA_FORMAT_FIELD_SPEECH,
			"getFormatFieldSpeech",
			{
				"config": types.SimpleNamespace(conf={"documentFormatting": self.formatConfig}),
				"textInfos": textInfos,
				"Optional": typing.Optional,
				"Dict": typing.Dict,
				"OutputReason": OutputReason,
				"SpeechSequence": list,
				"getTableInfoSpeech": getTableInfoSpeech,
				"State": State,
				"ReportCellBorders": ReportCellBorders,
				"OutputMode": OutputMode,
				"ReportSpellingErrors": ReportSpellingErrors,
				"WaveFileCommand": lambda fileName: fileName,
				"_shouldReportOutOfError": lambda formatConfig: False,
				"_": lambda text: text,
				"ngettext": lambda one, many, count: one if count == 1 else many,
				"types": types.SimpleNamespace(logBadSequenceTypes=lambda sequence: None),
			},
		)

	def speakLine(self, info, onlyInitialFields=False, reason=OutputReason.CARET):
		"""NVDA's speech.speakTextInfo for the line at the caret (getTextInfoSpeech), as far as its formatting goes:
		what getFormatFieldSpeech says for the line's formatting, against what NVDA noted of the formatting it said
		last in this document, then the text. After Enter, NVDA says only the formatting (onlyInitialFields)."""
		cache = info.innerTextInfo.obj.formatCache if isinstance(info, RootProxyTextInfo) else info.obj.formatCache
		spoken = []
		for item in info.getTextWithFields(self.formatConfig):
			if isinstance(item, FieldCommand) and item.command == "formatChange":
				spoken.extend(
					self.getFormatFieldSpeech(item.field, cache, self.formatConfig, reason=reason, unit=textInfos.UNIT_LINE, initialFormat=True)
				)
			elif isinstance(item, str) and not onlyInitialFields:
				spoken.append(item)
		return spoken


def wordDocumentModule(textInfoClass):
	"""NVDA's NVDAObjects.UIA.wordDocument, with its packages, and NVDA's textInfos, for the assistant to find."""
	module = types.ModuleType("NVDAObjects.UIA.wordDocument")
	module.WordDocumentTextInfo = textInfoClass
	return {
		"textInfos": textInfos,
		"NVDAObjects": types.ModuleType("NVDAObjects"),
		"NVDAObjects.UIA": types.ModuleType("NVDAObjects.UIA"),
		"NVDAObjects.UIA.wordDocument": module,
	}


class Isolated(unittest.TestCase):
	"""Each test starts with the assistant off, NVDA's own method in place and nothing logged yet."""

	def setUp(self):
		word.pageUnknown = False
		patches = [
			mock.patch.dict(sys.modules, wordDocumentModule(WordDocumentTextInfo)),
			mock.patch.object(outlookPages, "_enabled", False),
			mock.patch.object(outlookPages, "_failed", False),
			mock.patch.object(outlookPages, "_logged", False),
			mock.patch.object(outlookPages, "_replaced", []),
		]
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		self.addCleanup(setattr, WordDocumentTextInfo, "getTextWithFields", NVDAS_OWN)
		self.nvda = NVDA()


class OutlookMessageTest(Isolated):
	def setUp(self):
		super().setUp()
		outlookPages.register()
		self.addCleanup(outlookPages.unregister)

	def said(self, document, line, **kwargs):
		return self.nvda.speakLine(WordDocumentTextInfo(document, line), **kwargs)

	def nvdaAlone(self, document, line, **kwargs):
		"""What NVDA 2026.2 says for the same line without the assistant."""
		outlookPages.unregister()
		try:
			return self.said(document, line, **kwargs)
		finally:
			outlookPages.register()

	def test_control_home_said_page_1_section_1_first(self):
		# 09:15:00: Control+Home in the message the tester was writing.
		self.assertEqual(
			self.nvdaAlone(Document(), Line(CONTROL_HOME)),
			["page 1", "section 1", CONTROL_HOME],
			"NVDA 2026.2 says the page and section first, as in the tester's log",
		)

	def test_control_home_says_the_line_alone(self):
		self.assertEqual(self.said(Document(), Line(CONTROL_HOME)), [CONTROL_HOME])

	def test_up_arrow_into_a_reply(self):
		# 08:34:43: Up Arrow in a reply, just after its window opened.
		self.assertEqual(self.nvdaAlone(Document(), Line(REPLY)), ["page 1", "section 1", REPLY])
		self.assertEqual(self.said(Document(), Line(REPLY)), [REPLY])

	def test_enter_in_a_reply_says_nothing_more(self):
		# 08:33:35: Enter after "answers:" at the top of a reply (Control+R). NVDA says only the formatting it hasn't said
		# yet in the new line, which was
		# "page 1, section 1" alone; at the next Enter (08:34:12) it said nothing, as it does now at the first.
		self.assertEqual(self.nvdaAlone(Document(), Line("\r"), onlyInitialFields=True), ["page 1", "section 1"])
		self.assertEqual(self.said(Document(), Line("\r"), onlyInitialFields=True), [])

	def test_the_next_page_isnt_said_either(self):
		message = Document()
		self.assertEqual(self.said(message, Line("Dear Josh,\r")), ["Dear Josh,\r"])
		self.assertEqual(self.said(message, Line("Thanks.\r", page=2)), ["Thanks.\r"])
		alone = Document()
		self.nvdaAlone(alone, Line("Dear Josh,\r"))
		self.assertEqual(self.nvdaAlone(alone, Line("Thanks.\r", page=2)), ["page 2", "Thanks.\r"], "NVDA 2026.2 says the new page")

	def test_a_message_you_read_in_browse_mode(self):
		message = Document()
		self.assertEqual(self.nvda.speakLine(RootProxyTextInfo(WordDocumentTextInfo(message, Line(REPLY)))), [REPLY])

	def test_from_either_of_words_page_numbers(self):
		# Word gives a page's number twice: as a text attribute, and as the page element around the text. When the
		# attribute is -1, NVDA uses the element's; without the element, it has the attribute's.
		for pageUnknown, pageElements in ((True, True), (False, False)):
			with self.subTest(pageUnknown=pageUnknown, pageElements=pageElements):
				word.pageUnknown = pageUnknown
				self.assertEqual(self.nvdaAlone(Document(pageElements=pageElements), Line(REPLY)), ["page 1", "section 1", REPLY])
				self.assertEqual(self.said(Document(pageElements=pageElements), Line(REPLY)), [REPLY])

	def test_word_itself_keeps_them(self):
		self.assertEqual(self.said(Document("winword"), Line(CONTROL_HOME)), ["page 1", "section 1", CONTROL_HOME])

	def test_the_rest_of_the_formatting_is_kept(self):
		# The tester's NVDA doesn't say line numbers; with them on, NVDA still says them in Outlook.
		self.nvda.formatConfig["reportLineNumber"] = True
		info = WordDocumentTextInfo(Document(), Line(REPLY, number=3))
		self.assertEqual(self.nvda.speakLine(info), ["line 3", REPLY])
		fields = info.getTextWithFields(self.nvda.formatConfig)
		self.assertEqual(fields[1].field, {"font-name": "Aptos", "font-size": "12 pt", "line-number": 3})
		self.assertEqual(fields[0].field.get("page-number"), "1", "the page around the text is as NVDA made it")
		self.assertEqual([item.command for item in fields if isinstance(item, FieldCommand)], ["controlStart", "formatChange", "controlEnd"])

	def test_page_numbers_off_in_nvda_say_nothing_either_way(self):
		self.nvda.formatConfig["reportPage"] = False
		self.assertEqual(self.nvdaAlone(Document(), Line(REPLY)), [REPLY])
		self.assertEqual(self.said(Document(), Line(REPLY)), [REPLY])

	def test_logged_once_for_the_debug_log(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.said(Document(), Line(CONTROL_HOME))
			self.said(Document(), Line(REPLY))
		notes = [line for line in logged.output if "page and section numbers are left out of an Outlook message" in line]
		self.assertEqual(len(notes), 1, logged.output)
		self.assertIn("[('page-number', 1), ('section-number', 1)]", notes[0])

	def test_when_it_cant_tell_nvda_says_them_and_it_is_logged_once(self):
		class Broken(Document):
			@property
			def appModule(self):
				raise RuntimeError("the app module has gone")

			@appModule.setter
			def appModule(self, value):
				pass

		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.assertEqual(self.said(Broken(), Line(REPLY)), ["page 1", "section 1", REPLY])
			self.assertEqual(self.said(Broken(), Line(REPLY)), ["page 1", "section 1", REPLY])
		failures = [line for line in logged.output if "could not leave page and section numbers out of an Outlook message" in line]
		self.assertEqual(len(failures), 1, logged.output)

	def test_turned_off_nvda_says_them_as_it_does(self):
		outlookPages.unregister()
		self.assertIs(vars(WordDocumentTextInfo)["getTextWithFields"], NVDAS_OWN, "NVDA has its own method back")
		self.assertEqual(self.said(Document(), Line(REPLY)), ["page 1", "section 1", REPLY])

	def test_another_addons_wrapper_is_kept(self):
		ours = vars(WordDocumentTextInfo)["getTextWithFields"]

		def theirs(self, *args, **kwargs):
			return ours(self, *args, **kwargs)

		theirs.__wrapped__ = ours
		WordDocumentTextInfo.getTextWithFields = theirs
		outlookPages.unregister()
		self.assertIs(vars(WordDocumentTextInfo)["getTextWithFields"], theirs, "the other add-on's wrapper stays")
		self.assertEqual(self.said(Document(), Line(REPLY)), ["page 1", "section 1", REPLY], "and the assistant's does nothing")
		outlookPages.register()
		self.assertIs(vars(WordDocumentTextInfo)["getTextWithFields"], theirs, "turned on again, nothing is wrapped twice")
		self.assertEqual(self.said(Document(), Line(REPLY)), [REPLY])


class RegisterTest(Isolated):
	def test_register_and_unregister(self):
		outlookPages.register()
		self.assertTrue(outlookPages.isRegistered())
		installed = vars(WordDocumentTextInfo)["getTextWithFields"]
		self.assertIsNot(installed, NVDAS_OWN)
		self.assertIs(getattr(installed, outlookPages.ORIGINAL), NVDAS_OWN)
		outlookPages.register()
		self.assertIs(vars(WordDocumentTextInfo)["getTextWithFields"], installed, "registered twice, wrapped once")
		outlookPages.unregister()
		self.assertFalse(outlookPages.isRegistered())
		self.assertIs(vars(WordDocumentTextInfo)["getTextWithFields"], NVDAS_OWN)

	def test_without_nvdas_uia_support_for_word_nothing_changes(self):
		with mock.patch.dict(sys.modules, {"NVDAObjects.UIA.wordDocument": None}):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				outlookPages.register()
		self.assertFalse(outlookPages.isRegistered())
		self.assertTrue(any("can't leave page and section numbers out of Outlook messages" in line for line in logged.output), logged.output)

	def test_an_nvda_without_the_method_changes_nothing(self):
		bare = type("WordDocumentTextInfo", (), {})
		with mock.patch.dict(sys.modules, wordDocumentModule(bare)):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				outlookPages.register()
		self.assertFalse(outlookPages.isRegistered())
		self.assertNotIn("getTextWithFields", vars(bare))
		self.assertTrue(any("NVDA has no WordDocumentTextInfo.getTextWithFields" in line for line in logged.output), logged.output)


class SettingTest(unittest.TestCase):
	def test_on_unless_turned_off(self):
		self.assertTrue(outlookPages.wanted({}))
		self.assertTrue(outlookPages.wanted(dict(state.DEFAULTS)))
		self.assertFalse(outlookPages.wanted({outlookPages.STATE_KEY: False}))
		self.assertFalse(outlookPages.wanted(None))
		self.assertIs(state.DEFAULTS[outlookPages.STATE_KEY], True)

	def test_nvdas_defaults_say_page_numbers(self):
		# The tester's config changes none of these, so NVDA says page numbers, as it comes.
		defaults = NVDA.defaults()
		self.assertIs(defaults["reportPage"], True)
		self.assertIs(defaults["reportLineNumber"], False)


if __name__ == "__main__":
	unittest.main()
