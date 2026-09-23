# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Every JAWS manager, where it keeps its data, and what NVDA can do with it.

The list follows the JAWS "Run JAWS Manager" dialog (INSERT+F2). Each manager
records the files and INI sections that hold its settings, how the assistant
migrates them, and which NVDA Add-on Store add-on (if any) covers what NVDA
itself cannot. Anything that cannot be converted is still copied into the
migration archive so no customization is lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: How much of a manager's data NVDA can use.
FULL = "full"
PARTIAL = "partial"
ARCHIVE = "archive"


@dataclass(frozen=True)
class Manager:
	id: str
	name: str
	jawsPurpose: str
	nvdaResult: str
	migration: str
	#: File extensions (lower case, no dot) that belong to this manager.
	extensions: tuple = ()
	#: Exact file names (lower case) that belong to this manager.
	fileNames: tuple = ()
	#: Folder names (lower case) whose contents belong to this manager.
	folders: tuple = ()
	#: Substrings (lower case) of ``.jcf`` section names that belong to this manager.
	jcfSections: tuple = ()
	#: ``(section, key)`` pairs (lower case) in ``.jcf`` files that belong to this manager.
	jcfKeys: tuple = ()
	#: Add-on Store ids that add what NVDA lacks for this manager.
	helperAddons: tuple = field(default_factory=tuple)


MANAGERS = (
	Manager(
		"commandsSearch",
		"Commands Search",
		"Finds JAWS commands by name (INSERT+SPACE, J).",
		"NVDA's Input Gestures dialog (NVDA+N, Preferences, Input gestures) has a filter box that does the same job. "
		"Your Commands Search aliases and ignore lists are kept in the migration archive.",
		ARCHIVE,
		folders=("commandssearch",),
		jcfSections=("commandssearch",),
	),
	Manager(
		"customHighlight",
		"Custom Highlight Assign",
		"Tells JAWS which text and background colors mean 'highlighted' in an application.",
		"NVDA has no color-based highlight detection. The colors are kept in the migration archive and listed in the report.",
		ARCHIVE,
		jcfSections=("highlight colors", "custom highlight"),
	),
	Manager(
		"customizeListView",
		"Customize List View",
		"Reorders, renames or silences list view columns in an application.",
		"NVDA reads every column in order and has no per-list customization. "
		"Your list view customizations are kept in the migration archive.",
		ARCHIVE,
		jcfSections=("listview", "list view", "customlistview"),
	),
	Manager(
		"dictionaryManager",
		"Dictionary Manager",
		"Pronunciation rules (.jdf) for all applications or one application.",
		"Rules become entries in NVDA's default speech dictionary, or its voice dictionary when a rule is for one voice. "
		"JAWS root-word rules (word*) keep matching every word that starts with the root.",
		FULL,
		extensions=("jdf",),
	),
	Manager(
		"flexibleWeb",
		"Flexible Web",
		"Hides or reorders parts of web pages and starts reading at a chosen place.",
		"NVDA cannot hide web page content. The Flexible Web database is kept in the migration archive. "
		"Custom Browse Mode from the Add-on Store can switch NVDA profiles when browse mode is on.",
		ARCHIVE,
		fileNames=("flexibleweb.db",),
		helperAddons=("customBrowseMode",),
	),
	Manager(
		"frameViewer",
		"Frame Viewer",
		"Screen areas (.jff, .jfd) that JAWS watches and speaks when they change.",
		"NVDA has no frames; it reports changing content through its dynamic content setting. "
		"Your frames are kept in the migration archive.",
		ARCHIVE,
		extensions=("jff", "jfd"),
	),
	Manager(
		"graphicsLabeler",
		"Graphics Labeler",
		"Names for unlabeled graphics (.jgf).",
		"NVDA cannot match graphics by their pixels. Labels are kept in the migration archive. "
		"Custom Labels from the Add-on Store lets you name unlabeled controls again in NVDA.",
		ARCHIVE,
		extensions=("jgf",),
		helperAddons=("CustomLabels",),
	),
	Manager(
		"keyboardManager",
		"Keyboard Manager",
		"Which keystrokes run which JAWS scripts (.jkm).",
		"Keystrokes for JAWS commands that NVDA also has become NVDA input gestures, after gestures.ini is backed up. "
		"Keystrokes for JAWS-only scripts are listed in the report.",
		PARTIAL,
		extensions=("jkm",),
	),
	Manager(
		"markColorsInBraille",
		"Mark Colors in Braille",
		"Marks chosen text colors and attributes on the braille display.",
		"NVDA can show font attributes in braille. When JAWS marked bold, italic or underline, NVDA's "
		"font attribute reporting is set to include braille. Color marking has no NVDA equivalent.",
		PARTIAL,
		jcfKeys=(("braille", "braillemarkcolors"), ("braille", "brailleshowmarking")),
	),
	Manager(
		"messageCenter",
		"Message Center",
		"News and tips from Freedom Scientific.",
		"Nothing to migrate: the messages are Freedom Scientific news. They are kept in the migration archive.",
		ARCHIVE,
		folders=("messagecenter",),
		jcfSections=("messagecenter",),
	),
	Manager(
		"navigationQuickKeys",
		"Navigation Quick Keys",
		"Single-letter keys for moving around web pages and documents.",
		"NVDA's browse mode has quick navigation keys too. Where a JAWS letter moves to a different element than NVDA's, "
		"the JAWS letter is assigned to that element in browse mode, if you choose to migrate keyboard commands.",
		PARTIAL,
		jcfKeys=(("options", "quickkeynavigationmode"),),
	),
	Manager(
		"notificationHistory",
		"Notification History",
		"A history of Windows notifications, and rules for which ones JAWS speaks.",
		"NVDA reads notifications as they arrive. Custom Notifications from the Add-on Store lets you choose how "
		"they are read. Your notification history and rules are kept in the migration archive.",
		ARCHIVE,
		folders=("notifications",),
		helperAddons=("customNotifications",),
	),
	Manager(
		"promptCreate",
		"Prompt Create",
		"Your own names for controls that have none (INSERT+CTRL+TAB).",
		"Custom Labels from the Add-on Store gives NVDA the same ability. Your prompts are kept in the migration archive "
		"and listed in the report so you can re-create them.",
		ARCHIVE,
		extensions=("jsi",),
		jcfSections=("prompt", "custom label", "customlabel"),
		helperAddons=("CustomLabels",),
	),
	Manager(
		"quickSettings",
		"Quick Settings",
		"Settings for the current application (INSERT+V).",
		"Quick Settings saves into the application's .jcf file, which the Settings Center migration reads. "
		"Settings for one application become an NVDA configuration profile that turns on in that application.",
		PARTIAL,
		extensions=("qs", "qsm"),
		jcfSections=("nonjcfoptions",),
	),
	Manager(
		"researchIt",
		"Research It",
		"Looks words up in online sources.",
		"NVDA has no built-in lookup tool. Research It options and rules are kept in the migration archive.",
		ARCHIVE,
		extensions=("rul", "qry"),
		folders=("rulesets",),
		jcfSections=("research it",),
	),
	Manager(
		"scriptManager",
		"Script Manager",
		"JAWS scripts (.jss source, .jsb compiled, .jsh headers, .jsd documentation, .jsm messages).",
		"JAWS scripts cannot run in NVDA; NVDA add-ons are written in Python. Your script sources are kept in the migration "
		"archive, and the report lists every custom script so you can look for an NVDA add-on that does the same.",
		ARCHIVE,
		extensions=("jss", "jsb", "jsh", "jsd", "jsm"),
	),
	Manager(
		"settingsCenter",
		"Settings Center",
		"Nearly every JAWS option (.jcf), for all applications or for one application, plus voice profiles, "
		"speech and sounds schemes and punctuation.",
		"Each option with an NVDA equivalent is set in NVDA: speech, typing echo, keyboard layout, browse mode, "
		"document formatting, mouse echo, braille and more. Options for one application become an NVDA configuration "
		"profile for that application. Applications where JAWS was set to sleep make NVDA sleep there too.",
		FULL,
		extensions=("jcf", "vpf", "smf", "sbl", "chr"),
	),
	Manager(
		"skimReading",
		"Skim Reading Tool",
		"Reads the first line or sentence of each paragraph, or text matching your rules.",
		"NVDA can let navigation continue Say All (Keyboard settings, 'Allow skim reading in Say All'), which is set when "
		"JAWS rapid skim reading was on. Skim reading rules are kept in the migration archive.",
		PARTIAL,
		jcfSections=("skim",),
		jcfKeys=(("options", "allowrapidskimread"), ("options", "skimreadingindication")),
	),
	Manager(
		"windowClassReassign",
		"Window Class Reassign",
		"Tells JAWS to treat an unknown window class as a standard control.",
		"NVDA has no built-in way to do this. Enhanced Control Support from the Add-on Store adds support for more controls. "
		"Your reassignments are kept in the migration archive and listed in the report.",
		ARCHIVE,
		jcfSections=("windowclasses",),
		helperAddons=("enhancedControlSupport",),
	),
)

MANAGERS_BY_ID = {manager.id: manager for manager in MANAGERS}


@dataclass(frozen=True)
class StoreAddon:
	"""An NVDA Add-on Store add-on that helps someone coming from JAWS."""

	addonId: str
	name: str
	why: str
	ifNotInstalled: str


RECOMMENDED_ADDONS = (
	StoreAddon(
		"enhancedControlSupport",
		"Enhanced Control Support",
		"Adds NVDA support for controls it does not recognize on its own, like JAWS Window Class Reassign.",
		"Controls that JAWS only read because you reassigned their window class may stay silent or be read as 'unknown' "
		"in NVDA. Your reassignments are still kept in the migration archive.",
	),
	StoreAddon(
		"CustomLabels",
		"Custom Labels",
		"Lets you add your own labels to unlabeled controls and change existing ones, like JAWS Prompt Create "
		"and custom labels.",
		"Unlabeled buttons and graphics you named in JAWS will be read without your names in NVDA. "
		"Your JAWS labels are listed in the report so you can re-create them later.",
	),
	StoreAddon(
		"customBrowseMode",
		"Custom Browse Mode",
		"Turns on an NVDA configuration profile whenever browse mode is active, so web pages can have their own "
		"verbosity, like JAWS's separate web settings.",
		"Browse mode uses the same settings as everything else, as NVDA normally does. Nothing is lost.",
	),
	StoreAddon(
		"customNotifications",
		"Custom Notifications",
		"Chooses how NVDA reads Windows notifications: the whole text, just the application, speech, braille or both, "
		"like the JAWS notification settings.",
		"NVDA keeps reading every notification in full, its normal behavior. Your JAWS notification history is kept "
		"in the migration archive.",
	),
)

RECOMMENDED_BY_ID = {addon.addonId: addon for addon in RECOMMENDED_ADDONS}


# -- file classification -------------------------------------------------------------

#: Categories for files that belong to no manager.
OTHER_CATEGORIES = {
	"sounds": "Sound files",
	"voiceProfiles": "Voice profiles",
	"schemes": "Speech and sounds schemes",
	"symbols": "Punctuation and symbols",
	"braille": "Braille settings",
	"placeMarkers": "PlaceMarkers",
	"system": "JAWS program settings",
	"other": "Other files",
}

_CATEGORY_BY_EXTENSION = {
	"wav": "sounds",
	"vpf": "voiceProfiles",
	"smf": "schemes",
	"sbl": "symbols",
	"chr": "symbols",
	"jbs": "braille",
	"jbt": "braille",
	"jbd": "braille",
	"ptm": "placeMarkers",
	"ini": "system",
	"xml": "system",
	"txt": "other",
	"json": "other",
}


def classifyFile(relativePath: str) -> tuple[str, str]:
	"""Return ``(managerId or "", category)`` for a JAWS settings file.

	``relativePath`` is relative to a settings or scripts root, such as ``enu\\Default.jkm``.
	"""
	normalized = relativePath.replace("/", "\\").lower()
	parts = normalized.split("\\")
	name = parts[-1]
	extension = name.rsplit(".", 1)[-1] if "." in name else ""
	folders = parts[:-1]
	for manager in MANAGERS:
		if name in manager.fileNames or any(folder in manager.folders for folder in folders):
			return manager.id, manager.name
	if "placemarkers" in folders:
		return "", "placeMarkers"
	if "sounds" in folders and extension == "wav":
		return "", "sounds"
	if "voiceprofiles" in folders:
		return "settingsCenter", "voiceProfiles"
	for manager in MANAGERS:
		if extension and extension in manager.extensions:
			if extension == "vpf":
				return manager.id, "voiceProfiles"
			if extension == "smf":
				return manager.id, "schemes"
			if extension in ("sbl", "chr"):
				return manager.id, "symbols"
			return manager.id, manager.name
	return "", _CATEGORY_BY_EXTENSION.get(extension, "other")


def managersForJcfSection(sectionName: str) -> list[str]:
	lowered = sectionName.lower()
	return [manager.id for manager in MANAGERS if any(part in lowered for part in manager.jcfSections)]
