# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Settings Center: JAWS options (``.jcf``) and the NVDA settings that match them.

Each rule reads one or more JAWS options and produces NVDA configuration
changes, so that NVDA announces what JAWS announces, and nothing more. Rules
fire for options present in the JAWS file being migrated: with JAWS's full
settings (the user's layered over the shared ones), that is every option JAWS
uses, and where an older JAWS has no entry at all, JAWS's own default applies.
Migrating "your settings only" changes only what you changed in JAWS, except
that a changed verbosity level brings every row of its table at that level.
Options that decide how others are read (the verbosity levels, for instance)
are looked up in the full layered configuration. Font, color and attribute
announcements follow the speech and sounds scheme JAWS uses, as JAWS itself
no longer reads its old Format and Text options.

Options with no NVDA equivalent are returned as "not migrated" with the reason,
for the report. When ClassicSpeech is installed, options it supports
(verbosity levels, number and text processing) are mapped into its settings too.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import jawsFiles

NVDA = "nvda"
CLASSIC_SPEECH = "classicSpeech"

#: JAWS verbosity levels, which are also ClassicSpeech's verbosity profile names.
VERBOSITY_LEVELS = ("Beginner", "Intermediate", "Advanced")

#: JAWS web verbosity levels (``[VirtualCursorVerbosity] VirtualCursorVerbosityLevel``).
WEB_LEVEL_NAMES = {0: "Low", 1: "Medium", 2: "High"}
#: JAWS's default web verbosity level: Medium.
JAWS_WEB_VERBOSITY_LEVEL = 1

#: JAWS's own web verbosity table (Default.JCF, JAWS 2026), listed as High|Medium|Low, 1 announce.
#: Used for rows a JAWS configuration doesn't have at all, as older JAWS versions don't.
JAWS_WEB_VERBOSITY_DEFAULTS = {
	"List": "1|1|0",
	"TableOrGrid": "1|1|1",
	"Frame": "1|0|0",
	"Figure": "1|1|0",
	"BlockQuotation": "1|1|0",
	"GroupBox": "1|1|0",
	"ArticleRegion": "1|1|0",
	"ClickableElements": "1|0|0",
	"Region": "1|1|0",
	"MainRegion": "1|1|0",
	"NavigationRegion": "1|1|0",
	"BannerRegion": "1|0|0",
	"ComplementaryRegion": "1|0|0",
	"ContentInfoRegion": "1|0|0",
	"FormRegion": "1|0|0",
	"SearchRegion": "1|0|0",
}

#: The web verbosity rows NVDA reports as landmarks and regions.
LANDMARK_ROWS = ("Region", "MainRegion", "NavigationRegion", "BannerRegion", "ComplementaryRegion", "ContentInfoRegion", "FormRegion", "SearchRegion")

#: JAWS's own Output Modes rows (Default.JCF, JAWS 2026), listed as Beginner|Intermediate|Advanced.
JAWS_OUTPUT_MODE_DEFAULTS = {
	"ACCESS_KEY": "1|1|1|Access Key",
	"TOOL_TIP": "0|0|0|Tool Tip",
	"HELP_BALLOON": "1|1|1|Help Balloon",
	"ANNOUNCE_POSITION_AND_COUNT": "1|2|0|Announce Position and Count when navigating in lists",
}

#: ``[options]`` keys JAWS no longer reads: its speech and sounds schemes replaced them (HJConst.jsh).
OBSOLETE_FORMAT_OPTIONS = ("FormatAndText", "Font", "PointSize", "TextColor", "BackgroundColor", "Attributes")

#: JAWS attribute codes, ored with Text (0x1), for the attributes NVDA calls font attributes:
#: bold, italic, underline and strikeout.
_FONT_ATTRIBUTE_CODES = ((0x2, 0x3), (0x4, 0x5), (0x8, 0x9), (0x10, 0x11))


@dataclass
class SettingChange:
	target: str
	#: Section path and key, such as ``("keyboard", "speakTypedCharacters")``.
	path: tuple
	value: object
	label: str
	source: str
	#: True for settings kept per synthesizer (``speech.<synth>.capPitchChange``); the synthesizer is filled in later.
	perSynth: bool = False

	@property
	def key(self) -> str:
		return ".".join(str(part) for part in self.path)


@dataclass
class NotMigrated:
	section: str
	key: str
	value: str
	reason: str


@dataclass
class MappingResult:
	changes: list = field(default_factory=list)
	notMigrated: list = field(default_factory=list)
	#: ``(section, key)`` pairs, lower case, that some rule used.
	handled: set = field(default_factory=set)
	sleepMode: bool = False
	voiceProfileName: str = ""
	schemeName: str = ""
	sayAllSchemeName: str = ""
	keyboardLayout: str = ""
	#: JAWS's own keyboard layout name, lower case: ``desktop``, ``laptop``, ``classic laptop``...
	jawsKeyboardLayout: str = ""

	def add(self, target, path, value, label, source, perSynth=False):
		# A later rule for the same setting replaces an earlier one.
		self.changes = [change for change in self.changes if not (change.target == target and change.path == tuple(path))]
		self.changes.append(SettingChange(target, tuple(path), value, label, source, perSynth))


def nvdaKeyLabel(modifiers: int) -> str:
	"""``NVDA key: Caps Lock, numpad Insert`` for NVDA's NVDAModifierKeys bits."""
	names = [name for bit, name in ((1, "Caps Lock"), (2, "numpad Insert"), (4, "extended Insert")) if modifiers & bit]
	return "NVDA key: " + ", ".join(names)


class _Reader:
	"""Looks options up in the file being migrated, and in the full layered settings for context."""

	def __init__(self, source: jawsFiles.IniFile, context: jawsFiles.IniFile | None, result: MappingResult):
		self.source = source
		self.context = context or source
		self.result = result

	def has(self, section: str, key: str) -> bool:
		sect = self.source.section(section)
		return sect is not None and key in sect

	def raw(self, section: str, key: str):
		"""The value in the file being migrated, or None. Marks it as handled."""
		if not self.has(section, key):
			return None
		self.result.handled.add((section.lower(), key.lower()))
		return self.source.get(section, key)

	def int(self, section: str, key: str):
		return jawsFiles.parseInt(self.raw(section, key))

	def contextInt(self, section: str, key: str, default=None):
		return jawsFiles.parseInt(self.context.get(section, key), default)

	def contextRaw(self, section: str, key: str, default=None):
		return self.context.get(section, key, default)

	def src(self, section: str, key: str) -> str:
		return f"[{section}] {key}={self.source.get(section, key)}"


def _levelValue(raw, index: int):
	"""Read one level from a JAWS ``beginner|intermediate|advanced|label`` table entry."""
	if raw is None:
		return None
	parts = str(raw).split("|")
	if index >= len(parts):
		return None
	return jawsFiles.parseInt(parts[index])


def _schemeBehavior(section, key: str):
	"""The behavior number of ``key`` in a scheme table section, or None when the table doesn't list it."""
	if section is None:
		return None
	for name, value in section.items():
		if name.lower() == key.lower():
			return jawsFiles.parseInt(str(value).split("|")[0])
	return None


def schemeAnnounces(scheme: jawsFiles.IniFile, table: str) -> bool:
	"""Whether a JAWS scheme announces the items of ``table`` (font names, font sizes, colors).

	A scheme's ``default`` key decides for every item it doesn't list; with no default, or no
	table at all, JAWS speaks the item.
	"""
	behavior = _schemeBehavior(scheme.section(table), "default")
	return behavior is None or behavior != 0


def schemeAnnouncesFontAttributes(scheme: jawsFiles.IniFile) -> bool:
	"""Whether a JAWS scheme announces bold, italic, underline or strikeout text."""
	section = scheme.section("Attribute Behavior Table")
	if section is None:
		return True
	default = _schemeBehavior(section, "default")
	listed = {}
	for key, value in section.items():
		code = jawsFiles.parseInt(key)
		if code is not None:
			listed[code] = jawsFiles.parseInt(str(value).split("|")[0])
	for codes in _FONT_ATTRIBUTE_CODES:
		behavior = next((listed[code] for code in codes if code in listed), default)
		if behavior is None or behavior != 0:
			return True
	return False


def _dotsToShape(dots) -> int | None:
	"""JAWS cursor dots such as ``78`` become NVDA's cell bit mask (dot 1 = 1 ... dot 8 = 128)."""
	text = str(dots or "").strip()
	if not text or not text.isdigit():
		return None
	shape = 0
	for digit in set(text):
		number = int(digit)
		if 1 <= number <= 8:
			shape |= 1 << (number - 1)
	return shape or None


def mapSettings(
	source: jawsFiles.IniFile,
	context: jawsFiles.IniFile | None = None,
	classicSpeech: bool = False,
	isApplication: bool = False,
	userKeys: set | None = None,
	effective: bool = False,
	scheme: jawsFiles.IniFile | None = None,
	schemeChosen: bool = False,
) -> MappingResult:
	"""Map one JAWS configuration file (already layered as wanted) to NVDA settings.

	``userKeys`` holds the ``(section, key)`` pairs, lower case, that the user set in their own
	JAWS files. A few JAWS defaults would silence information NVDA gives by default (object
	descriptions, for example); those are only migrated when the user chose them in JAWS.

	``effective`` is True when ``source`` is JAWS's whole configuration as JAWS runs it, so
	JAWS's own defaults stand in for rows an older JAWS doesn't have. ``scheme`` is the speech
	and sounds scheme JAWS uses; ``schemeChosen`` says whether its choice is part of this
	migration, in which case NVDA's font, color and attribute announcements follow it.
	"""
	result = MappingResult()
	r = _Reader(source, context, result)
	add = result.add

	def userChose(section: str, key: str) -> bool:
		return userKeys is not None and (section.lower(), key.lower()) in userKeys

	# -- speech and keyboard ---------------------------------------------------------
	typingEcho = r.int("options", "TypingEcho")
	if typingEcho is not None:
		characters = typingEcho in (1, 3)
		words = typingEcho in (2, 3)
		source_ = r.src("options", "TypingEcho")
		add(NVDA, ("keyboard", "speakTypedCharacters"), 1 if characters else 0, "Speak typed characters: " + ("only in edit controls" if characters else "off"), source_)
		add(NVDA, ("keyboard", "speakTypedWords"), 1 if words else 0, "Speak typed words: " + ("only in edit controls" if words else "off"), source_)

	value = r.int("options", "TypingInterrupt")
	if value is not None:
		add(NVDA, ("keyboard", "speechInterruptForCharacters"), bool(value), f"Speech interrupt for typed characters: {'on' if value else 'off'}", r.src("options", "TypingInterrupt"))

	screenEcho = r.int("options", "ScreenEcho")
	liveRegions = r.int("HTML", "AnnounceLiveRegionUpdates")
	if screenEcho is not None or liveRegions is not None:
		enabled = bool(screenEcho) if screenEcho is not None else bool(liveRegions)
		if screenEcho is not None and liveRegions is not None:
			enabled = bool(screenEcho) or bool(liveRegions)
		sources = [r.src(s, k) for s, k in (("options", "ScreenEcho"), ("HTML", "AnnounceLiveRegionUpdates")) if r.has(s, k)]
		add(NVDA, ("presentation", "reportDynamicContentChanges"), enabled, f"Report dynamic content changes: {'on' if enabled else 'off'}", "; ".join(sources))

	keyboardType = r.raw("options", "KeyboardType")
	if keyboardType:
		layout = "laptop" if "laptop" in keyboardType.lower() else "desktop"
		result.keyboardLayout = layout
		result.jawsKeyboardLayout = " ".join(keyboardType.split()).lower()
		add(NVDA, ("keyboard", "keyboardLayout"), layout, f"Keyboard layout: {layout}", r.src("options", "KeyboardType"))
	insertKeys = r.int("options", "JAWSInsertKey")
	if insertKeys is not None or keyboardType:
		if insertKeys is None:
			insertKeys = r.contextInt("options", "JAWSInsertKey", 3)
		layoutName = (keyboardType or r.contextRaw("options", "KeyboardType", "Desktop") or "").lower()
		# Caps Lock is the JAWS key only in the Laptop layout (Classic Laptop uses Insert).
		capsLock = " ".join(layoutName.split()) == "laptop"
		modifiers = (2 if insertKeys in (1, 3) else 0) | (4 if insertKeys in (2, 3) else 0) | (1 if capsLock else 0)
		if not modifiers:
			modifiers = 6
		add(NVDA, ("keyboard", "NVDAModifierKeys"), modifiers, nvdaKeyLabel(modifiers), "JAWS key: " + (r.src("options", "JAWSInsertKey") if r.has("options", "JAWSInsertKey") else "keyboard layout " + layoutName))

	value = r.int("options", "IndicateMistypedWord")
	if value is not None:
		add(NVDA, ("keyboard", "alertForSpellingErrors"), bool(value), f"Play sound for spelling errors while typing: {'on' if value else 'off'}", r.src("options", "IndicateMistypedWord"))

	raw = r.raw("options", "AllowRapidSkimRead")
	if raw is not None:
		result.notMigrated.append(
			NotMigrated(
				"options",
				"AllowRapidSkimRead",
				raw,
				"Tells JAWS whether a document can be read in full at once (0 in Google Docs); it is not a skim reading "
				"preference, so NVDA's 'Allow skim reading in Say All' is left as it is.",
			),
		)

	value = r.int("options", "LanguageDetection")
	if value is not None:
		add(NVDA, ("speech", "autoLanguageSwitching"), bool(value), f"Automatic language switching: {'on' if value else 'off'}", r.src("options", "LanguageDetection"))
	value = r.int("options", "GeneralizeDialect")
	if value is not None:
		add(NVDA, ("speech", "autoDialectSwitching"), not bool(value), f"Automatic dialect switching: {'off' if value else 'on'}", r.src("options", "GeneralizeDialect"))

	value = r.int("options", "PhoneticCharAfterPause")
	if value is not None:
		add(NVDA, ("speech", "delayedCharacterDescriptions"), value > 0, f"Delayed descriptions for characters on cursor movement: {'on' if value > 0 else 'off'}", r.src("options", "PhoneticCharAfterPause"))

	indicateCaps = r.int("options", "IndicateCaps")
	case = r.int("options", "Case")
	if indicateCaps is not None or case is not None:
		off = (indicateCaps == 0) or (case == 0)
		if off:
			sources = [r.src(s, k) for s, k in (("options", "IndicateCaps"), ("options", "Case")) if r.has(s, k)]
			add(NVDA, ("capPitchChange",), 0, "Capital pitch change: 0 (JAWS did not indicate capitals)", "; ".join(sources), perSynth=True)
		else:
			result.notMigrated.append(NotMigrated("options", "IndicateCaps", str(indicateCaps), "JAWS raises the pitch for capitals, as NVDA already does; NVDA's setting is kept."))

	value = r.int("options", "Dictionary")
	if value is not None and value == 0:
		add(NVDA, ("speech", "speechDictionaries"), [], "Speech dictionaries: none (JAWS dictionary processing was off)", r.src("options", "Dictionary"))

	value = r.int("options", "Indentation")
	if value is not None:
		add(NVDA, ("documentFormatting", "reportLineIndentation"), 1 if value else 0, f"Report line indentation: {'speech' if value else 'off'}", r.src("options", "Indentation"))

	# Font, color and attribute announcements: JAWS no longer reads its old Format and Text
	# options; the speech and sounds scheme in use decides, so NVDA follows that scheme.
	for key in OBSOLETE_FORMAT_OPTIONS:
		raw = r.raw("options", key)
		if raw is not None:
			result.notMigrated.append(NotMigrated("options", key, raw, "JAWS no longer uses this option: the speech and sounds scheme in use decides what is announced."))
	schemeTitle = (scheme.get("Information", "Title") or "in use") if scheme is not None else ""
	schemeUsed = scheme is not None and schemeChosen and not isApplication
	if schemeUsed:
		for table, path, label in (
			("Font Name Behavior Table", ("documentFormatting", "reportFontName"), "Report font name"),
			("Font Size Behavior Table", ("documentFormatting", "reportFontSize"), "Report font size"),
			("Color Behavior Table", ("documentFormatting", "reportColor"), "Report color"),
		):
			enabled = schemeAnnounces(scheme, table)
			add(NVDA, path, enabled, f"{label}: {'on' if enabled else 'off'}", f"JAWS scheme {schemeTitle}, {table.replace(' Behavior Table', '')} table")
	marking = r.int("Braille", "BrailleShowMarking")
	if schemeUsed or marking is not None:
		# JAWS's default scheme, Classic, announces none of these attributes.
		speechBit = 1 if scheme is not None and schemeAnnouncesFontAttributes(scheme) else 0
		brailleMarking = marking if marking is not None else r.contextInt("Braille", "BrailleShowMarking", 0)
		brailleBit = 2 if (brailleMarking or 0) & (2 | 4 | 8) else 0
		mode = speechBit | brailleBit
		names = {0: "off", 1: "speech", 2: "braille", 3: "speech and braille"}
		sources = [f"JAWS scheme {schemeTitle}, Attribute table" if scheme is not None else "JAWS's default scheme, Classic"]
		if marking is not None:
			sources.append(r.src("Braille", "BrailleShowMarking"))
		add(NVDA, ("documentFormatting", "fontAttributeReporting"), mode, f"Font attributes: {names[mode]}", "; ".join(sources))

	value = r.int("options", "ProgressBarUpdateInterval")
	if value is not None:
		mode = "off" if value == 0 else "speak"
		add(NVDA, ("presentation", "progressBarUpdates", "progressBarOutputMode"), mode, f"Progress bar output: {mode}", r.src("options", "ProgressBarUpdateInterval"))

	for key, path, label, explicitOnly in (
		("MouseSpeechEnabled", ("mouse", "enableMouseTracking"), "Mouse tracking", False),
		("MouseEchoSpeaksControlTypeAndState", ("mouse", "reportObjectRoleOnMouseEnter"), "Report role when mouse enters object", False),
		("MouseEchoScreenLocationTones", ("mouse", "audioCoordinatesOnMouseMove"), "Play audio coordinates when mouse moves", False),
		("SayCursorShapeChange", ("mouse", "reportMouseShapeChanges"), "Report mouse shape changes", False),
		("TouchTypingMode", ("touch", "touchTyping"), "Touch typing mode", False),
		("confirmWhenExitingJAWS", ("general", "askToExit"), "Ask before exiting NVDA", False),
		("AutomaticNotificationOfUpdates", ("update", "autoCheck"), "Automatically check for NVDA updates", False),
		("DetailsAnnouncement", ("annotations", "reportDetails"), "Report details in browse mode", True),
	):
		if explicitOnly and not userChose("options", key):
			if r.has("options", key):
				r.raw("options", key)
				result.notMigrated.append(NotMigrated("options", key, str(r.source.get("options", key)), "JAWS default kept out: NVDA gives this information by default."))
			continue
		value = r.int("options", key)
		if value is not None:
			add(NVDA, path, bool(value), f"{label}: {'on' if value else 'off'}", r.src("options", key))

	# JAWS keeps the virtual cursor and table detection options in [OSM]; older files may have them in [options].
	section = "OSM" if r.has("OSM", "UseVirtualPCCursor") else "options"
	value = r.int(section, "UseVirtualPCCursor")
	if value is not None:
		# 0 off; 1 on; 2 and 3 on, except in nested panes or ARIA applications.
		add(NVDA, ("virtualBuffers", "enableOnPageLoad"), bool(value), f"Enable browse mode on page load: {'on' if value else 'off'}", r.src(section, "UseVirtualPCCursor"))
	section = "OSM" if r.has("OSM", "TableDetection") else "options"
	value = r.int(section, "TableDetection")
	if value is not None:
		# 0 announces every table, 1 only data tables.
		add(NVDA, ("documentFormatting", "includeLayoutTables"), value == 0, f"Include layout tables: {'yes' if value == 0 else 'no'}", r.src(section, "TableDetection"))

	value = r.int("options", "MouseSpeechEchoUnit")
	if value is not None:
		unit = {0: "character", 1: "word", 2: "line", 3: "paragraph"}.get(value)
		if unit:
			add(NVDA, ("mouse", "mouseTextUnit"), unit, f"Mouse text unit resolution: {unit}", r.src("options", "MouseSpeechEchoUnit"))

	value = r.int("options", "LowerOtherAppsVolumeWhileJAWSIsRunning")
	if value is not None:
		add(NVDA, ("audio", "audioDuckingMode"), 2 if value else 0, f"Audio ducking: {'always duck' if value else 'no ducking'}", r.src("options", "LowerOtherAppsVolumeWhileJAWSIsRunning"))

	value = r.int("options", "SleepMode")
	if value:
		result.sleepMode = True
		result.handled.add(("options", "sleepmode"))

	profileName = r.raw("Voice Profiles", "ActiveVoiceProfileName")
	if profileName:
		result.voiceProfileName = profileName.strip()
	scheme = r.raw("options", "Scheme")
	if scheme:
		result.schemeName = scheme.strip()
	sayAllScheme = r.raw("options", "SayAllScheme")
	if sayAllScheme:
		result.sayAllSchemeName = sayAllScheme.strip()
	r.raw("options", "Synthesizer")

	# -- verbosity (Output Modes) --------------------------------------------------------
	verbosity = r.contextInt("options", "Verbosity", 0)
	if verbosity not in (0, 1, 2):
		verbosity = 0
	verbosityChanged = r.has("options", "Verbosity")
	if verbosityChanged:
		r.raw("options", "Verbosity")
		if classicSpeech:
			add(CLASSIC_SPEECH, ("defaultProfile",), VERBOSITY_LEVELS[verbosity], f"ClassicSpeech verbosity: {VERBOSITY_LEVELS[verbosity]}", r.src("options", "Verbosity"))
	for key, path, label in (
		("ACCESS_KEY", ("presentation", "reportKeyboardShortcuts"), "Report object shortcut keys"),
		("TOOL_TIP", ("presentation", "reportTooltips"), "Report tooltips"),
		("HELP_BALLOON", ("presentation", "reportHelpBalloons"), "Report notifications (help balloons)"),
		("ANNOUNCE_POSITION_AND_COUNT", ("presentation", "reportObjectPositionInformation"), "Report object position information"),
	):
		raw = r.raw("OutputModes", key)
		where = f"[OutputModes] {key}, {VERBOSITY_LEVELS[verbosity]} level"
		if raw is None and (effective or verbosityChanged):
			# A changed verbosity level brings JAWS's row at that level; an older JAWS without the row uses JAWS's default.
			raw = r.contextRaw("OutputModes", key)
			if raw is None:
				raw = JAWS_OUTPUT_MODE_DEFAULTS.get(key)
				where = f"JAWS's default for {key}, {VERBOSITY_LEVELS[verbosity]} level"
		level = _levelValue(raw, verbosity)
		if level is not None:
			add(NVDA, path, level != 0, f"{label}: {'on' if level else 'off'}", where)
	raw = r.raw("OutputModes", "CONTROL_DESCRIPTION")
	if raw is not None and userChose("OutputModes", "CONTROL_DESCRIPTION"):
		level = _levelValue(raw, verbosity)
		if level is not None:
			add(NVDA, ("presentation", "reportObjectDescriptions"), level != 0, f"Report object descriptions: {'on' if level else 'off'}", f"[OutputModes] CONTROL_DESCRIPTION, {VERBOSITY_LEVELS[verbosity]} level")
	if classicSpeech:
		tokens = {
			"name": "CONTROL_NAME",
			"role": "CONTROL_TYPE",
			"state": "ITEM_STATE",
			"position": "ANNOUNCE_POSITION_AND_COUNT",
			"description": "CONTROL_DESCRIPTION",
			"tooltip": "TOOL_TIP",
			"hotkey": "ACCESS_KEY",
		}
		for token, key in tokens.items():
			raw = r.raw("OutputModes", key)
			if raw is None:
				continue
			for index, levelName in enumerate(VERBOSITY_LEVELS):
				level = _levelValue(raw, index)
				if level is None:
					continue
				add(
					CLASSIC_SPEECH,
					("profileData", levelName, "enabledTokens", token),
					level != 0,
					f"ClassicSpeech {levelName} verbosity, speak {token}: {'yes' if level else 'no'}",
					f"[OutputModes] {key}",
				)
	for key in ("TUTOR", "SMART_HELP", "APP_START", "JAWS_MESSAGE", "TOASTS", "SCREEN_MESSAGE"):
		raw = r.raw("OutputModes", key)
		if raw is not None:
			result.notMigrated.append(NotMigrated("OutputModes", key, raw, "NVDA has no separate setting for this JAWS message type."))

	# -- browse mode (virtual cursor) -----------------------------------------------------
	# JAWS reads each row of its web verbosity table at the web verbosity level (Low, Medium or
	# High); NVDA gets what JAWS announces at that level, and nothing more. Rows are High|Medium|Low.
	levelChanged = r.has("VirtualCursorVerbosity", "VirtualCursorVerbosityLevel")
	r.raw("VirtualCursorVerbosity", "VirtualCursorVerbosityLevel")
	vcLevel = r.contextInt("VirtualCursorVerbosity", "VirtualCursorVerbosityLevel", JAWS_WEB_VERBOSITY_LEVEL)
	if vcLevel not in WEB_LEVEL_NAMES:
		vcLevel = JAWS_WEB_VERBOSITY_LEVEL
	levelName = WEB_LEVEL_NAMES[vcLevel]
	columnIndex = 2 - vcLevel

	def webRow(key: str):
		"""``(announce, where)`` for one web verbosity row as JAWS reads it, or ``(None, "")``."""
		if r.has("VirtualCursorVerbosity", key):
			return _levelValue(r.raw("VirtualCursorVerbosity", key), columnIndex), f"[VirtualCursorVerbosity] {key}, {levelName} web verbosity"
		if not (effective or levelChanged):
			return None, ""
		raw = r.contextRaw("VirtualCursorVerbosity", key)
		if raw is not None:
			return _levelValue(raw, columnIndex), f"[VirtualCursorVerbosity] {key}, {levelName} web verbosity"
		return _levelValue(JAWS_WEB_VERBOSITY_DEFAULTS.get(key), columnIndex), f"JAWS's default for {key}, {levelName} web verbosity"

	for key, path, label in (
		("List", ("documentFormatting", "reportLists"), "Report lists"),
		("TableOrGrid", ("documentFormatting", "reportTables"), "Report tables"),
		("Frame", ("documentFormatting", "reportFrames"), "Report frames"),
		("Figure", ("documentFormatting", "reportFigures"), "Report figures and captions"),
		("BlockQuotation", ("documentFormatting", "reportBlockQuotes"), "Report block quotes"),
		("GroupBox", ("documentFormatting", "reportGroupings"), "Report groupings"),
		("ArticleRegion", ("documentFormatting", "reportArticles"), "Report articles"),
		("ClickableElements", ("documentFormatting", "reportClickable"), "Report if clickable"),
	):
		level, where = webRow(key)
		if level is not None:
			add(NVDA, path, bool(level), f"{label}: {'on' if level else 'off'}", where)
	landmarkLevels = [level for level, _where in (webRow(key) for key in LANDMARK_ROWS) if level is not None]
	if landmarkLevels:
		enabled = any(landmarkLevels)
		add(NVDA, ("documentFormatting", "reportLandmarks"), enabled, f"Report landmarks and regions: {'on' if enabled else 'off'}", f"[VirtualCursorVerbosity] regions, {levelName} web verbosity")

	value = r.int("HTML", "HeadingIndication")
	if value is not None:
		add(NVDA, ("documentFormatting", "reportHeadings"), value != 0, f"Report headings: {'on' if value else 'off'}", r.src("HTML", "HeadingIndication"))
	value = r.int("HTML", "IncludeGraphics")
	if value is not None:
		add(NVDA, ("documentFormatting", "reportGraphics"), value != 0, f"Report graphics: {'on' if value else 'off'}", r.src("HTML", "IncludeGraphics"))
	value = r.int("HTML", "IdentifyLinkType")
	if value is not None:
		add(NVDA, ("documentFormatting", "reportLinkType"), bool(value), f"Report link type: {'on' if value else 'off'}", r.src("HTML", "IdentifyLinkType"))
	value = r.int("HTML", "MaxLineLength")
	if value is not None and value > 0:
		add(NVDA, ("virtualBuffers", "maxLineLength"), value, f"Maximum number of characters on one line: {value}", r.src("HTML", "MaxLineLength"))
	value = r.int("HTML", "LinesPerPage")
	if value is not None and value > 0:
		add(NVDA, ("virtualBuffers", "linesPerPage"), value, f"Maximum lines per page: {value}", r.src("HTML", "LinesPerPage"))
	value = r.int("HTML", "DocumentPresentationMode")
	if value is not None:
		add(NVDA, ("virtualBuffers", "useScreenLayout"), value != 0, f"Use screen layout: {'on' if value else 'off (each link on its own line, as in JAWS simple layout)'}", r.src("HTML", "DocumentPresentationMode"))
	for section in ("NonJCFOptions", "HTML"):
		value = r.int(section, "SayAllOnDocumentLoad")
		if value is not None:
			add(NVDA, ("virtualBuffers", "autoSayAllOnPageLoad"), bool(value), f"Automatic Say All on page load: {'on' if value else 'off'}", r.src(section, "SayAllOnDocumentLoad"))
			break

	value = r.int("FormsMode", "AutoFormsMode")
	if value is not None:
		add(NVDA, ("virtualBuffers", "autoPassThroughOnFocusChange"), bool(value), f"Automatic focus mode for focus changes: {'on' if value else 'off'}", r.src("FormsMode", "AutoFormsMode"))
		add(NVDA, ("virtualBuffers", "autoPassThroughOnCaretMove"), bool(value), f"Automatic focus mode for caret movement: {'on' if value else 'off'}", r.src("FormsMode", "AutoFormsMode"))
	value = r.int("FormsMode", "IndicateFormsModeWithSounds")
	if value is not None:
		add(NVDA, ("virtualBuffers", "passThroughAudioIndication"), bool(value), f"Audio indication of focus and browse modes: {'on' if value else 'off'}", r.src("FormsMode", "IndicateFormsModeWithSounds"))

	value = r.int("NonJCFOptions", "TblHeaders")
	if value is not None:
		headers = {0: 0, 1: 2, 2: 3, 3: 1, 4: 1}.get(value, 1)
		names = {0: "off", 1: "rows and columns", 2: "rows", 3: "columns"}
		add(NVDA, ("documentFormatting", "reportTableHeaders"), headers, f"Report table row and column headers: {names[headers]}", r.src("NonJCFOptions", "TblHeaders"))
	value = r.int("NonJCFOptions", "DefaultVCursorCellCoordinatesAnnouncement")
	if value is not None:
		add(NVDA, ("documentFormatting", "reportTableCellCoords"), bool(value), f"Report table cell coordinates: {'on' if value else 'off'}", r.src("NonJCFOptions", "DefaultVCursorCellCoordinatesAnnouncement"))

	# -- braille --------------------------------------------------------------------------
	value = r.int("Braille", "BrailleMode")
	if value is not None:
		mode = "speechOutput" if value == 2 else "followCursors"
		add(NVDA, ("braille", "mode"), mode, "Braille mode: " + ("speech output" if value == 2 else "follow cursors"), r.src("Braille", "BrailleMode"))
	value = r.int("Braille", "WordWrap")
	if value is not None:
		add(NVDA, ("braille", "wordWrap"), bool(value), f"Avoid splitting words when possible: {'on' if value else 'off'}", r.src("Braille", "WordWrap"))
	value = r.int("Braille", "NavByParagraph")
	if value is not None:
		add(NVDA, ("braille", "readByParagraph"), bool(value), f"Read by paragraph: {'on' if value else 'off'}", r.src("Braille", "NavByParagraph"))
	for key in ("BraillePCCursorBlinkRate", "BrailleCursorBlinkRate"):
		value = r.int("Braille", key)
		if value is not None:
			rate = max(200, min(2000, value))
			add(NVDA, ("braille", "cursorBlinkRate"), rate, f"Braille cursor blink rate: {rate} ms", r.src("Braille", key))
			break
	allDots = r.int("Braille", "AllDotsBrailleCursor")
	focusDots = _dotsToShape(r.raw("Braille", "BraillePCCursorDots"))
	if allDots:
		focusDots = 255
	if focusDots:
		add(NVDA, ("braille", "cursorShapeFocus"), focusDots, "Braille cursor shape for focus: JAWS PC cursor dots", "[Braille] BraillePCCursorDots")
	reviewDots = _dotsToShape(r.raw("Braille", "BrailleJAWSCursorDots"))
	if reviewDots:
		add(NVDA, ("braille", "cursorShapeReview"), reviewDots, "Braille cursor shape for review: JAWS cursor dots", "[Braille] BrailleJAWSCursorDots")
	value = r.int("Braille", "MessageTime")
	if value is not None and value > 0:
		seconds = max(1, min(20, int(round(value / 1000.0))))
		add(NVDA, ("braille", "messageTimeout"), seconds, f"Braille message timeout: {seconds} seconds", r.src("Braille", "MessageTime"))
	value = r.int("Braille", "BrailleMessages")
	if value is not None:
		add(NVDA, ("braille", "showMessages"), 1 if value else 0, "Show braille messages: " + ("use timeout" if value else "disabled"), r.src("Braille", "BrailleMessages"))
	value = r.int("Braille", "AutoAdvanceInterval")
	if value is not None and value > 0:
		# JAWS advances a whole display at a time; NVDA scrolls in cells per second. Assume 40 cells.
		rate = max(1.0, min(20.0, round(40.0 / (value / 1000.0), 1)))
		add(NVDA, ("braille", "autoScrollRate"), rate, f"Automatic scroll rate: {rate} cells per second (from {value} ms per 40-cell display)", r.src("Braille", "AutoAdvanceInterval"))
	_mapBrailleTables(r, result)

	# -- ClassicSpeech text and number processing --------------------------------------------
	if classicSpeech:
		value = r.int("options", "MixedCase")
		if value is not None:
			add(CLASSIC_SPEECH, ("textProcessingData", "splitMixedCaseWords"), bool(value), f"ClassicSpeech: split mixed case words: {'on' if value else 'off'}", r.src("options", "MixedCase"))
		value = r.int("options", "SpellAlphanumericData")
		if value is not None:
			mode = {0: "off", 1: "spell", 2: "phonetic"}.get(value, "off")
			add(CLASSIC_SPEECH, ("textProcessingData", "spellAlphanumericData"), mode, f"ClassicSpeech: spell alphanumeric data: {mode}", r.src("options", "SpellAlphanumericData"))
		value = r.int("options", "Filter")
		if value is not None and 3 <= value <= 6:
			add(CLASSIC_SPEECH, ("textProcessingData", "repeatedCharacterMode"), str(value), f"ClassicSpeech: repeated characters after {value}", r.src("options", "Filter"))
		value = r.int("options", "IndicateNewlinesAndParagraphs")
		if value is not None:
			add(CLASSIC_SPEECH, ("textProcessingData", "announceNewLinesDuringSayAll"), bool(value & 8), f"ClassicSpeech: announce new lines during Say All: {'on' if value & 8 else 'off'}", r.src("options", "IndicateNewlinesAndParagraphs"))
		value = r.int("options", "IndicateSelected")
		if value is not None:
			mode = {0: "none", 1: "selected", 2: "notSelected", 3: "both"}.get(value)
			if mode:
				add(CLASSIC_SPEECH, ("textProcessingData", "listItemStateReporting"), mode, f"ClassicSpeech: list item state reporting: {mode}", r.src("options", "IndicateSelected"))
		numbers = r.int("options", "Numbers")
		if numbers is not None:
			mode = {0: "synthesizer", 1: "singleDigits", 2: "pairs", 3: "fullNumbers", 4: "fullNumbers"}.get(numbers, "synthesizer")
			add(CLASSIC_SPEECH, ("numberProcessingData", "numberProcessingMode"), mode, f"ClassicSpeech: number processing: {mode}", r.src("options", "Numbers"))
		# JAWS applies "Speak single digits if number contains N or more digits" whatever the number
		# processing is (0 leaves it to the synthesizer), exactly as ClassicSpeech does.
		threshold = r.int("options", "SingleDigitThreshold")
		if threshold is not None:
			value = str(threshold) if 5 <= threshold <= 8 else "synthesizer"
			add(CLASSIC_SPEECH, ("numberProcessingData", "singleDigitsIfNumberContains"), value, f"ClassicSpeech: single digits if number contains {value}", r.src("options", "SingleDigitThreshold"))
		value = r.int("options", "SayDollars")
		if value is not None:
			mode = "dollarsAndCents" if value else "native"
			add(CLASSIC_SPEECH, ("numberProcessingData", "currencyProcessing"), mode, f"ClassicSpeech: currency: {mode}", r.src("options", "SayDollars"))
		value = r.int("options", "SayNumericDates")
		if value is not None:
			mode = {0: "native", 1: "some", 2: "full"}.get(value, "native")
			add(CLASSIC_SPEECH, ("numberProcessingData", "numericDateProcessing"), mode, f"ClassicSpeech: numeric dates: {mode}", r.src("options", "SayNumericDates"))
		value = r.int("options", "UseSystemLocaleForDateFormatInformation")
		if value is not None:
			add(CLASSIC_SPEECH, ("numberProcessingData", "useWindowsDateFormat"), bool(value), f"ClassicSpeech: use the Windows date format: {'on' if value else 'off'}", r.src("options", "UseSystemLocaleForDateFormatInformation"))
		value = r.int("NonJCFOptions", "AnnouncePageElementsOnLoad")
		if value is not None:
			add(CLASSIC_SPEECH, ("pageSummaryData", "automaticReportOnPageLoad"), bool(value), f"ClassicSpeech: page summary on load: {'on' if value else 'off'}", r.src("NonJCFOptions", "AnnouncePageElementsOnLoad"))

	# JAWS plays no sound when it starts or exits. NVDA's option is in its normal configuration only.
	if not isApplication:
		add(NVDA, ("general", "playStartAndExitSounds"), False, "Play sounds when starting or exiting NVDA: off, as JAWS plays none", "JAWS plays no sounds when it starts or exits")

	# -- everything else ---------------------------------------------------------------------
	_collectNotMigrated(source, result, isApplication)
	return result


_BRAILLE_TABLES_ENGLISH = {
	# (contracted state, eight dot) -> (output table, input table)
	(0, True): ("en-us-comp8-ext.utb", "en-us-comp8-ext.utb"),
	(0, False): ("en-us-comp6.ctb", "en-us-comp6.ctb"),
	(1, True): ("en-ueb-g2.ctb", "en-us-comp8-ext.utb"),
	(1, False): ("en-ueb-g2.ctb", "en-us-comp6.ctb"),
	(2, True): ("en-ueb-g2.ctb", "en-ueb-g2.ctb"),
	(2, False): ("en-ueb-g2.ctb", "en-ueb-g2.ctb"),
}


def _mapBrailleTables(r: _Reader, result: MappingResult) -> None:
	section = r.source.section("Braille Profiles")
	if section is None:
		return
	primary = (r.contextRaw("Braille", "PrimaryBrailleProfile", "enu") or "enu").lower()
	raw = None
	for key, value in section.items():
		if key.lower() == primary:
			raw = value
			result.handled.add(("braille profiles", key.lower()))
	if raw is None:
		return
	state = jawsFiles.parseInt(raw.split("|")[0], 0)
	eightDot = bool(r.contextInt("Braille", "EightDotBraille", 1))
	r.raw("Braille", "EightDotBraille")
	if not primary.startswith("en"):
		result.notMigrated.append(NotMigrated("Braille Profiles", primary, raw, "Only English braille tables are chosen automatically; choose yours in NVDA's Braille settings."))
		return
	output, inputTable = _BRAILLE_TABLES_ENGLISH.get((state, eightDot), _BRAILLE_TABLES_ENGLISH[(0, eightDot)])
	names = {0: "computer braille", 1: "contracted braille output", 2: "contracted braille input and output"}
	result.add(NVDA, ("braille", "translationTable"), output, f"Braille output table: {output} ({names.get(state, '')})", f"[Braille Profiles] {primary}={raw}")
	result.add(NVDA, ("braille", "inputTable"), inputTable, f"Braille input table: {inputTable}", f"[Braille Profiles] {primary}={raw}")


#: JAWS sections that belong to another manager or have nothing NVDA can use.
_NOT_SETTINGS_SECTIONS = {
	"windowclasses": "Window Class Reassign: kept in the migration archive.",
	"msaaclasses": "Technical JAWS setting for how JAWS reads a window class.",
	"msaa classes": "Technical JAWS setting for how JAWS reads a window class.",
	"genericuiaclasses": "Technical JAWS setting for how JAWS reads a window class.",
	"osm": "Technical settings for the JAWS off-screen model, which NVDA does not use.",
	"keylabels": "JAWS key names; NVDA names keys itself.",
	"system keylabels": "JAWS key names; NVDA names keys itself.",
	"highlight colors": "Custom Highlight Assign: kept in the migration archive.",
	"research it options": "Research It: kept in the migration archive.",
	"research it exclusions": "Research It: kept in the migration archive.",
	"research it phrase history": "Research It: kept in the migration archive.",
	"messagecenter": "Message Center: nothing to migrate.",
	"commandssearch": "Commands Search: NVDA's Input Gestures dialog can be searched instead.",
	"information": "Description of the file.",
}


def _collectNotMigrated(source: jawsFiles.IniFile, result: MappingResult, isApplication: bool) -> None:
	for section in source.sections.values():
		lowered = section.name.lower()
		reason = _NOT_SETTINGS_SECTIONS.get(lowered)
		for key, value in section.items():
			if (lowered, key.lower()) in result.handled:
				continue
			if reason is None and ("-" in section.name and section.name.lower().split("-", 1)[1].endswith("context")):
				text = "Old per-synthesizer voice setting; voice profiles are migrated instead."
			elif reason is None and lowered.startswith("braille") or lowered in ("focus", "focus40", "focusxt40", "focusxt80", "focusxt14"):
				text = "Braille display setting with no NVDA equivalent."
			else:
				text = reason or "NVDA has no equivalent setting."
			result.notMigrated.append(NotMigrated(section.name, key, value, text))
