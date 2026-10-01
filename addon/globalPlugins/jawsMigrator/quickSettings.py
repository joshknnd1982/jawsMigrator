# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""JAWS's Quick Settings, Insert+V: the settings of the program you are in, the ones NVDA can do.

A tester pressed Insert+V in Outlook and nothing happened (issue 40): "Run a test with Jaws pressing Insert V will bring
up the quick settings for that program. Example outlook ETC. Should these be added? if so how will you do the live
tests? this is a big project I suspect."

What JAWS 2026 does (read from its own files and run live, see the tests): Insert+V, or Caps Lock+V in the Laptop
layout, runs the script QuickSettings (Default.JKM). It opens a window called "QuickSettings - <name>", where the name
is JAWS's for the program you are in: its configuration's (ConfigNames.ini has olk=Outlook Modern), or the program's own
(notepad, msedge). The window has a Search box, a tree of categories with a row for each setting, and beside the tree
the controls of the setting you are on: a check box or a list. Apply, OK, Cancel, Escape and closing the window all save what you changed, and ask nothing (watched in JAWS 2026 in
Notepad: each left a changed Typing Echo in notepad.JCF). What it shows comes from Default.QS and the program's own .qs file (msedge.qs includes Chrome.qs, which includes Browser.qs
and IA2Browser.qs; Outlook.qs includes Outlook 2007.qs, which includes WORDClassic.qs), each setting with the .jcf option
it reads and writes, or a script of QuickSet.jss that does. It saves for the program alone: a setting is written to the
program's own .jcf (FT_CURRENT_JCF). Some categories show only where they apply: Virtual Cursor Options while a web page
or another document is in the virtual cursor or in forms mode (QuickSettingDisabledEvent: isVirtualPcCursor () ||
IsFormsModeActive ()), Braille Options with a braille display.

What NVDA does, from this version: the same command opens the same window, with the same categories, setting names and
choices, for the settings NVDA can do (README: QuickSettings has what is in and what isn't). A setting JAWS shows that NVDA
has nothing for is left out, not shown to do nothing, as the assistant maps JAWS strictly (settingsMap). A setting saves
for the program alone as JAWS's does: into the NVDA configuration profile that turns on in the program (NVDA's own
profile for it if it has one, otherwise "JAWS - <name>", which the assistant makes and turns on there, as a migration
does for the settings a JAWS application file holds). Most settings are ones a migration already maps from the same .jcf
option, so a choice and the migration agree by construction (settingsMap.mapSettings works out each choice); the few a
migration has no rule for (Punctuation, Messages Automatically Read) are worked out here, and the Semi-Auto choice of
Auto Forms Mode is worked out in settingsMap beside the others.

Reading it back is the same rule the other way: the choice whose NVDA settings all equal NVDA's now, in the program's
profile over the normal configuration. Where two of JAWS's choices are one thing in NVDA (Graphics Show's Tagged and
All, Headings Announce's On and Heading and Level, Table Titles' Both and Only Marked Headers), the one you chose last is
shown, kept in state.json (CHOICES_KEY) for as long as it still gives NVDA's settings. Where none gives them, as when
NVDA's own setting has a value JAWS has no word for, nothing is selected and the window says so.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field

from . import debugLog, jawsFiles, settingsMap

#: The assistant's setting (state.json) that remembers the last choice made for each setting: {setting ID: JAWS value}.
CHOICES_KEY = "quickSettingsChoices"
#: What JAWS titles the window: "QuickSettings - notepad".
TITLE = "QuickSettings"
#: JAWS's name for the application whose settings the window holds, in a title: the program's name, as NVDA names it.
NO_PROGRAM = "Windows"


@dataclass(frozen=True)
class Choice:
	#: The JAWS value (what JAWS writes to its .jcf for it).
	value: str
	#: JAWS's word for it, from its Quick Settings (Default.QSM, Browser.QSM).
	label: str


#: A check box is a setting with two values, 0 not checked and 1 checked.
CHECK_BOX = (Choice("0", "not checked"), Choice("1", "checked"))


@dataclass(frozen=True)
class Item:
	#: JAWS's ID of the setting in its .qs files (Default.QS, Browser.qs), which the tests find there.
	id: str
	#: JAWS's name for it.
	name: str
	#: The JAWS option it reads and writes: ``[section] key`` of the program's .jcf.
	section: str
	key: str
	choices: tuple = CHECK_BOX
	#: The programs (NVDA's app module names) it is for; none: every program, as Default.QS.
	programs: tuple = ()
	#: True where what a choice means depends on JAWS's own tables (a verbosity level's rows).
	tables: bool = False
	#: The NVDA settings it sets, as ``section.key`` names, where the JAWS option it is comes with others (a migration
	#: reads every table of JAWS at once; a choice of one level is only what that level's rows are).
	only: tuple = ()
	#: ``mapper(ini, result)`` where settingsMap.mapSettings has no rule for the option.
	mapper: object = None

	@property
	def isCheckBox(self) -> bool:
		return self.choices is CHECK_BOX


@dataclass(frozen=True)
class Category:
	id: str
	name: str
	#: Its settings (Item) and categories inside it, in JAWS's order.
	children: tuple = ()
	#: Where JAWS shows it: "" everywhere; BROWSE only where a document is in browse mode (JAWS's virtual cursor or forms
	#: mode); BRAILLE only with a braille display.
	needs: str = ""


#: What a category needs: see Category.needs.
BROWSE = "browse"
BRAILLE = "braille"


@dataclass(frozen=True)
class Context:
	#: NVDA's name for the program (its executable's name without ".exe"), as JAWS names it in the title.
	program: str = ""
	#: Whether a document is in browse mode or focus mode over one (a tree interceptor): JAWS's virtual cursor or forms mode.
	browse: bool = False
	#: Whether a braille display is connected.
	braille: bool = False
	#: JAWS's name for the program, its configuration's (ConfigNames.ini: olk is "Outlook Modern"); the program's own name
	#: where JAWS has none or isn't here.
	name: str = ""

	@property
	def jawsName(self) -> str:
		return self.name or self.program


def _punctuation(ini, result) -> None:
	from . import voices

	value = jawsFiles.parseInt(ini.get("options", "Punctuation"))
	level = voices.PUNCTUATION_TO_SYMBOL_LEVEL.get(value)
	if level is not None:
		name = voices.PUNCTUATION_NAMES.get(value)
		result.add(settingsMap.NVDA, ("speech", "symbolLevel"), level, f"Punctuation level: {name}", f"[options] Punctuation={value}")


def _messagesAutomaticallyRead(ini, result) -> None:
	settingsMap.mapOutlookSettings(ini, None, result)


#: What User Verbosity sets: the rows of JAWS's Output Modes table NVDA has settings for.
USER_VERBOSITY = (
	"presentation.reportKeyboardShortcuts",
	"presentation.reportTooltips",
	"presentation.reportHelpBalloons",
	"presentation.reportObjectPositionInformation",
)
#: What the Virtual Cursor Verbosity Level sets: the rows of JAWS's web verbosity table NVDA has settings for.
WEB_LEVEL = (
	"documentFormatting.reportLists",
	"documentFormatting.reportTables",
	"documentFormatting.reportFrames",
	"documentFormatting.reportFigures",
	"documentFormatting.reportBlockQuotes",
	"documentFormatting.reportGroupings",
	"documentFormatting.reportArticles",
	"documentFormatting.reportClickable",
	"documentFormatting.reportLandmarks",
)

#: JAWS's Quick Settings (Default.QS, Default.QSM, Browser.qs, Browser.QSM, Outlook 2007.qs), the ones NVDA can do, in
#: JAWS's order and with JAWS's words.
GENERAL_OPTIONS = Category(
	"GeneralOptions",
	"General Options",
	children=(
		Item(
			"GeneralOptions.UserVerbosity",
			"User Verbosity",
			"options",
			"Verbosity",
			(Choice("0", "Beginner"), Choice("1", "Intermediate"), Choice("2", "Advanced")),
			tables=True,
			only=USER_VERBOSITY,
		),
		Item("GeneralOptions.ProgressBars", "Progress Bars", "options", "ProgressBarUpdateInterval", (Choice("1", "Spoken"), Choice("0", "Silent"))),
	),
)
READING_OPTIONS = Category(
	"ReadingOptions",
	"Reading Options",
	children=(
		Item("ReadingOptions.LanguageDetectChange", "Language Detect Change", "options", "LanguageDetection"),
		Item(
			"ReadingOptions.MessagesAutomaticallyRead",
			"Messages Automatically Read",
			"NonJCFOptions",
			"MessageSayAllVerbosity",
			programs=("outlook",),
			mapper=_messagesAutomaticallyRead,
		),
	),
)
EDITING_OPTIONS = Category(
	"EditingOptions",
	"Editing Options",
	children=(
		Item(
			"EditingOptions.TypingEcho",
			"Typing Echo",
			"options",
			"TypingEcho",
			(Choice("0", "None"), Choice("1", "Characters"), Choice("2", "Words"), Choice("3", "Both Characters and Words")),
		),
		Item(
			"EditingOptions.Punctuation",
			"Punctuation",
			"options",
			"Punctuation",
			(Choice("0", "None"), Choice("1", "Some"), Choice("2", "Most"), Choice("3", "All")),
			mapper=_punctuation,
		),
		Item("EditingOptions.Indentation", "Indentation", "options", "Indentation", (Choice("0", "Ignore"), Choice("1", "Indicate"))),
	),
)
VIRTUAL_CURSOR_OPTIONS = Category(
	"VirtualCursorOptions",
	"Virtual Cursor Options",
	needs=BROWSE,
	children=(
		Item(
			"VirtualCursorOptions.VirtualCursorVerbosityLevel",
			"Virtual Cursor Verbosity Level",
			"VirtualCursorVerbosity",
			"VirtualCursorVerbosityLevel",
			(Choice("0", "Low"), Choice("1", "Medium"), Choice("2", "High")),
			tables=True,
			only=WEB_LEVEL,
		),
		Category(
			"VirtualCursorOptions.FormsOptions",
			"Forms Options",
			children=(
				Item(
					"VirtualCursorOptions.FormsOptions.AutoFormsMode",
					"Auto Forms Mode",
					"FormsMode",
					"AutoFormsMode",
					(Choice("0", "Manual"), Choice("1", "Auto"), Choice("2", "SemiAuto")),
				),
				Item("VirtualCursorOptions.FormsOptions.UseSound", "Use Sound", "FormsMode", "IndicateFormsModeWithSounds"),
			),
		),
		Category(
			"VirtualCursorOptions.GeneralOptions",
			"General Options",
			children=(
				Item("VirtualCursorOptions.GeneralOptions.DocumentAutomaticallyReads", "Document and Web Pages automatically read when loaded", "HTML", "SayAllOnDocumentLoad"),
				Item(
					"VirtualCursorOptions.GeneralOptions.DocumentPresentation",
					"Document Presentation Mode",
					"HTML",
					"DocumentPresentationMode",
					(Choice("0", "Simple Layout"), Choice("1", "Screen Layout")),
				),
				Item("VirtualCursorOptions.GeneralOptions.AnnounceLiveRegionUpdates", "Announce live region updates", "HTML", "AnnounceLiveRegionUpdates"),
			),
		),
		Category(
			"VirtualCursorOptions.GraphicsOptions",
			"Graphics Options",
			children=(
				Item(
					"VirtualCursorOptions.GraphicsOptions.GraphicsShow",
					"Graphics Show",
					"HTML",
					"IncludeGraphics",
					(Choice("0", "None"), Choice("1", "Tagged"), Choice("2", "All")),
				),
			),
		),
		Category(
			"VirtualCursorOptions.LinksOptions",
			"Links Options",
			children=(Item("VirtualCursorOptions.LinksOptions.LinksIdentifySamePage", 'Links Identify "Same Page"', "HTML", "IdentifySamePageLinks"),),
		),
		Category(
			"VirtualCursorOptions.HeadingAndFrameOptions",
			"Heading and Frame Options",
			children=(
				Item(
					"VirtualCursorOptions.HeadingAndFrameOptions.HeadingsAnnounce",
					"Headings Announce",
					"HTML",
					"HeadingIndication",
					(Choice("0", "Off"), Choice("1", "On"), Choice("2", "Heading and Level")),
				),
			),
		),
		Category(
			"VirtualCursorOptions.TableOptions",
			"Table Options",
			children=(
				Item("VirtualCursorOptions.TableOptions.LayoutTables", "Layout Tables Ignore", "OSM", "TableDetection"),
				Item(
					"VirtualCursorOptions.TableOptions.TableTitles",
					"Table Titles",
					"NonJCFOptions",
					"TblHeaders",
					(Choice("0", "Off"), Choice("1", "Row"), Choice("2", "Column"), Choice("3", "Both Row and Column"), Choice("4", "Only Marked Headers")),
				),
				Item(
					"VirtualCursorOptions.TableOptions.CellCoordinatesAnnouncement",
					"Cell Coordinates Announcement",
					"NonJCFOptions",
					"DefaultVCursorCellCoordinatesAnnouncement",
				),
			),
		),
	),
)
BRAILLE_OPTIONS = Category(
	"BrailleOptions",
	"Braille Options",
	needs=BRAILLE,
	children=(
		Category("BrailleOptions.PanningOptions", "Panning Options", children=(Item("BrailleOptions.PanningOptions.WordWrap", "Word Wrap", "Braille", "WordWrap"),)),
		Item("BrailleOptions.FlashMessages", "Flash Messages", "Braille", "BrailleMessages"),
	),
)
#: The tree, in the order JAWS shows a browser's: the virtual cursor's options first, the braille display's last.
CATEGORIES = (VIRTUAL_CURSOR_OPTIONS, GENERAL_OPTIONS, READING_OPTIONS, EDITING_OPTIONS, BRAILLE_OPTIONS)

#: How NVDA's value may differ from a choice's and still be that choice: ``{path: same(current, wanted)}``. Only where
#: JAWS's word covers more than one NVDA value: Indicate, however NVDA does it; Characters, in every program or in edit
#: controls alone; Spoken, with or without the beeps (beeps alone are not silence); Flash Messages, for a time or until
#: dismissed.
SAME_AS = {
	("documentFormatting", "reportLineIndentation"): lambda current, wanted: bool(current) == bool(wanted),
	("keyboard", "speakTypedCharacters"): lambda current, wanted: bool(current) == bool(wanted),
	("keyboard", "speakTypedWords"): lambda current, wanted: bool(current) == bool(wanted),
	("presentation", "progressBarUpdates", "progressBarOutputMode"): lambda current, wanted: current in ("speak", "both") if wanted == "speak" else current == wanted,
	("braille", "showMessages"): lambda current, wanted: bool(current) == bool(wanted),
}


def jawsNameFor(program: str, configNames) -> str:
	"""JAWS's name for ``program``, from its ConfigNames.ini (``configNames``, an IniFile, or None); "" when it has none.

	The file's lines are ``exeName=configurationName``, or ``exeName:version=configurationName`` for one version of a
	program; a line that starts ``regex:`` is for web addresses."""
	section = configNames.section("ConfigNames") if configNames is not None else None
	if section is None:
		return ""
	found = ""
	for key, value in section.items():
		name, _separator, version = key.partition(":")
		if name.strip().lower() == program.lower() and name.strip().lower() != "regex" and value.strip():
			if not version:
				return value.strip()
			found = found or value.strip()
	return found


def items(categories=CATEGORIES) -> list:
	"""Every setting of ``categories``, in the order of the tree."""
	found = []
	for category in categories:
		for child in category.children:
			found.extend(items((child,)) if isinstance(child, Category) else [child])
	return found


def itemById(settingId: str):
	return next((item for item in items() if item.id == settingId), None)


def available(item: Item, context: Context) -> bool:
	return not item.programs or context.program.lower() in item.programs


def tree(context: Context) -> list:
	"""The categories of ``context``, with only the settings and categories that have something to show, as JAWS builds them."""

	def build(category):
		if (category.needs == BROWSE and not context.browse) or (category.needs == BRAILLE and not context.braille):
			return None
		shown = tuple(
			found
			for found in (build(child) if isinstance(child, Category) else (child if available(child, context) else None) for child in category.children)
			if found is not None
		)
		return Category(category.id, category.name, shown, category.needs) if shown else None

	return [found for found in (build(category) for category in CATEGORIES) if found is not None]


# -- what a choice does in NVDA -------------------------------------------------------------------------------------


def nvdaChanges(item: Item, value: str, jawsSettings=None) -> list:
	"""The settings of NVDA and of the assistant that the choice ``value`` of ``item`` is.

	They are what a migration makes of the same JAWS option (settingsMap.mapSettings), for a program's own file. Where
	they depend on JAWS's own tables, ``jawsSettings`` is JAWS's Default.jcf as JAWS runs it, the choice put over it;
	without one, JAWS's tables as JAWS comes."""
	ini = jawsFiles.IniFile()
	ini.ensureSection(item.section).set(item.key, value)
	if item.mapper is not None:
		result = settingsMap.MappingResult()
		item.mapper(ini, result)
	else:
		context = jawsFiles.mergeIni(jawsSettings, ini) if jawsSettings is not None else ini
		result = settingsMap.mapSettings(ini, context, isApplication=True, effective=item.tables)
	return [
		change
		for change in result.changes
		if change.target in (settingsMap.NVDA, settingsMap.ASSISTANT) and (not item.only or ".".join(change.path) in item.only)
	]


def _sameValue(path, current, wanted) -> bool:
	same = SAME_AS.get(tuple(path))
	if same is not None:
		return bool(same(current, wanted))
	return current == wanted


def matches(changes: list, getValue) -> bool:
	"""Whether every setting of ``changes`` is what ``getValue(target, path)`` says it is now."""
	if not changes:
		return False
	for change in changes:
		current = getValue(change.target, change.path)
		if not isinstance(current, (bool, int, str)) or not _sameValue(change.path, current, change.value):
			return False
	return True


def currentValue(item: Item, getValue, jawsSettings=None, remembered=None):
	"""The JAWS value of the choice of ``item`` that NVDA's settings are now, or None when none is.

	Where two choices are the same in NVDA, ``remembered``, the choice made last, wins when it still is."""
	found = [choice.value for choice in item.choices if matches(nvdaChanges(item, choice.value, jawsSettings), getValue)]
	if not found:
		return None
	return remembered if remembered in found else found[0]


def choiceLabel(item: Item, value) -> str:
	return next((choice.label for choice in item.choices if choice.value == value), "")


def describe(item: Item, value: str, jawsSettings=None) -> str:
	"""What the choice does in NVDA, in words, one line for each NVDA setting it sets."""
	changes = nvdaChanges(item, value, jawsSettings)
	if not changes:
		return "NVDA has nothing to set for this choice."
	return "In NVDA: " + "; ".join(change.label for change in changes) + "."


# -- reading and saving in NVDA -------------------------------------------------------------------------------------


def nvdaValue(target: str, path):
	"""NVDA's value of a setting now, or the assistant's."""
	if target == settingsMap.ASSISTANT:
		from . import state

		return state.get(path[0])
	from . import nvdaApply

	return nvdaApply.getValue(tuple(path))


@dataclass(frozen=True)
class Target:
	#: The profile the settings of the program go in: its name as NVDA has it, or the name to make.
	name: str
	#: Whether it exists already.
	exists: bool
	#: Whether NVDA turns a profile on in the program already: this one, or one of the user's.
	triggered: bool


def targetProfile(context: Context) -> Target:
	"""The profile for the settings of the program: the one NVDA turns on in it, or the one to make.

	NVDA's own profile for the program, a migration's "JAWS - <configuration>" or one of the user's, keeps what the user
	gave the program. Without one, "JAWS - <configuration>" is made for it, as a migration makes it: named for JAWS's
	configuration ("JAWS - Outlook" for outlook.exe), turned on by the program ("app:outlook")."""
	import config

	from . import nvdaApply
	from .migrator import APP_PROFILE_PREFIX

	spec = f"app:{context.program.lower()}"
	current = config.conf.triggersToProfiles.get(spec)
	existing = nvdaApply.existingProfileName(current) if current else None
	if existing is not None:
		return Target(existing, True, True)
	name = f"{APP_PROFILE_PREFIX}{context.jawsName}"
	found = nvdaApply.existingProfileName(name)
	return Target(found or name, found is not None, False)


@contextlib.contextmanager
def viewing(profileName):
	"""NVDA's settings as they are in the program whose profile is ``profileName`` (its own settings over the normal
	configuration), while the block runs. Nothing is created, and nothing is saved."""
	import config

	from . import nvdaApply

	conf = config.conf
	previousManual = nvdaApply.activeManualProfile()
	triggersWereEnabled = conf.profileTriggersEnabled
	conf.disableProfileTriggers()
	try:
		existing = nvdaApply.existingProfileName(profileName) if profileName else None
		conf.manualActivateProfile(existing)
		yield
	finally:
		try:
			conf.manualActivateProfile(previousManual)
		except Exception:
			debugLog.error("could not activate the profile that was on again")
			conf.manualActivateProfile(None)
		if triggersWereEnabled:
			conf.enableProfileTriggers()


def readAll(context: Context, jawsSettings=None) -> dict:
	"""``{setting ID: JAWS value or None}`` for the settings of ``context``, as they are in NVDA in the program."""
	from . import state

	remembered = state.get(CHOICES_KEY)
	remembered = remembered if isinstance(remembered, dict) else {}
	shown = items(tree(context))
	profile = targetProfile(context).name if context.program else None
	with viewing(profile):
		return {item.id: currentValue(item, nvdaValue, jawsSettings, remembered.get(item.id)) for item in shown}


@dataclass
class Saved:
	#: The profile the settings of NVDA went in, or "" when there were none.
	profile: str = ""
	#: The settings written to NVDA, and those it couldn't take, with why: ``(change, reason)``.
	applied: list = field(default_factory=list)
	failed: list = field(default_factory=list)
	#: The assistant's own settings that changed.
	assistant: list = field(default_factory=list)
	#: What became of the profile's trigger: "" when nothing needed doing, else what the assistant tells the user.
	notice: str = ""
	#: True when the profile was made for this and held nothing, so it was taken away again.
	removedEmpty: bool = False

	@property
	def count(self) -> int:
		return len(self.applied) + len(self.assistant)


def save(context: Context, selections: dict, jawsSettings=None) -> Saved:
	"""Save the choices ``selections``, ``{setting ID: JAWS value}``, for the program, as Apply in JAWS's window does.

	The settings of NVDA go in the program's profile (see the module's help); the assistant's own, in state.json."""
	from . import nvdaApply, state

	saved = Saved()
	forNvda = []
	shown = {item.id for item in items(tree(context))}
	for settingId, value in selections.items():
		item = itemById(settingId)
		if item is None or item.id not in shown:
			continue
		for change in nvdaChanges(item, value, jawsSettings):
			if change.target == settingsMap.ASSISTANT:
				saved.assistant.append(change)
			else:
				forNvda.append(change)
	if forNvda:
		target = targetProfile(context)
		saved.profile = target.name
		with nvdaApply.writingTo(target.name):
			debugLog.section(f"Quick Settings for {context.jawsName}, written to {nvdaApply.writingConfigurationName()}")
			saved.applied, saved.failed = nvdaApply.applySettings(forNvda, None)
		if not target.exists and not nvdaApply.profileHoldsSettings(target.name):
			# Every choice was what NVDA does already: a profile of nothing would only make NVDA switch for nothing.
			saved.removedEmpty = nvdaApply.deleteProfile(target.name)
		elif not target.triggered:
			outcome, detail = nvdaApply.setProfileTrigger(context.program, target.name)
			if outcome == nvdaApply.TRIGGER_KEPT:
				saved.notice = f'NVDA already turns on your profile "{detail}" in {context.program}, so "{target.name}" does not turn on there by itself.'
			elif outcome == nvdaApply.TRIGGER_FAILED:
				saved.notice = f'"{target.name}" could not be set to turn on in {context.program}: {detail}'
		for change in saved.applied:
			debugLog.note(f"quick settings: {'.'.join(change.path)} = {change.value!r} -> {saved.profile}")
		for change, reason in saved.failed:
			debugLog.note(f"quick settings: {'.'.join(change.path)} could not be set: {reason}")
	if saved.assistant:
		state.update({change.path[0]: change.value for change in saved.assistant})
		for change in saved.assistant:
			debugLog.note(f"quick settings: the assistant's {change.path[0]} = {change.value!r}")
	remembered = state.get(CHOICES_KEY)
	remembered = dict(remembered) if isinstance(remembered, dict) else {}
	remembered.update({settingId: value for settingId, value in selections.items() if itemById(settingId) is not None})
	state.set(CHOICES_KEY, remembered)
	return saved


def confirmation(context: Context, saved: Saved) -> str:
	"""What NVDA says once the choices are saved."""
	if not saved.count and not saved.failed:
		return "Nothing to save."
	parts = []
	if saved.applied:
		if saved.removedEmpty:
			parts.append(f"{context.jawsName} does these already, so no profile was needed")
		else:
			parts.append(f'Saved for {context.jawsName} in the profile "{saved.profile}"')
	if saved.assistant:
		parts.append("The assistant's setting is saved")
	if saved.failed:
		parts.append(f"{len(saved.failed)} could not be saved: {saved.failed[0][1]}")
	if saved.notice:
		parts.append(saved.notice)
	return ". ".join(parts) + "."


#: What a row says for a setting whose NVDA settings are none of JAWS's choices.
OWN_SETTING = "NVDA's own setting"


class Session:
	"""One open QuickSettings window: what it shows, what is chosen in it, and saving."""

	def __init__(self, context: Context, jawsSettings=None):
		self.context = context
		self.jawsSettings = jawsSettings
		self.categories = tree(context)
		#: ``{setting ID: JAWS value or None}`` as NVDA has them, and as chosen in the window.
		self.initial = readAll(context, jawsSettings)
		self.chosen = dict(self.initial)

	@property
	def title(self) -> str:
		return f"{TITLE} - {self.context.jawsName or NO_PROGRAM}"

	def items(self) -> list:
		return items(self.categories)

	def choose(self, item: Item, value: str) -> None:
		self.chosen[item.id] = value

	def changes(self) -> dict:
		"""``{setting ID: JAWS value}`` for what was chosen and isn't what NVDA has."""
		return {settingId: value for settingId, value in self.chosen.items() if value is not None and value != self.initial.get(settingId)}

	def valueText(self, item: Item) -> str:
		value = self.chosen.get(item.id)
		return OWN_SETTING if value is None else choiceLabel(item, value)

	def rowText(self, item: Item) -> str:
		"""The row of the tree: the setting and what it is now, so arrowing through the tree says both."""
		return f"{item.name}: {self.valueText(item)}"

	def effect(self, item: Item) -> str:
		"""What the window says under the setting: what the choice does in NVDA."""
		value = self.chosen.get(item.id)
		if value is None:
			return "NVDA's settings for this are not one of JAWS's choices. Choose one to change them."
		return describe(item, value, self.jawsSettings)

	def save(self) -> Saved:
		saved = save(self.context, self.changes(), self.jawsSettings)
		if saved.count or saved.failed:
			# What NVDA holds now is what was chosen, but for what NVDA could not take.
			failed = {".".join(change.path) for change, _reason in saved.failed}
			for settingId in self.changes():
				item = itemById(settingId)
				if item is not None and not any(".".join(change.path) in failed for change in nvdaChanges(item, self.chosen[settingId], self.jawsSettings)):
					self.initial[settingId] = self.chosen[settingId]
		return saved
