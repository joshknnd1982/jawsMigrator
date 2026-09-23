# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""JAWS Speech and Sounds schemes (``.smf``) as ClassicSpeech Speech and Sound Schemes.

A JAWS scheme tells JAWS, for each control type, control state, text attribute
and web attribute, whether to speak it normally, speak it in another voice
(a voice alias), play a sound instead, or say nothing. ClassicSpeech schemes
hold the same kind of choices per NVDA role, state and formatting item. This
module turns one into the other; the voices are resolved later against the
synthesizer NVDA will use, because voice aliases change pitch and rate relative
to the current voice.

Behaviors in a JAWS scheme entry ``behavior|data1|data2|data3|data4``:
0 ignore, 1 speak (data1 is a voice alias, optionally ``alias:text``),
2 play the sound in data2, 3 speak the text in the voice alias in data3,
4 speak in the language in data4.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import jawsFiles, voices

#: JAWS window types (WT_ constants from HJConst.jsh) -> ClassicSpeech item ids.
CONTROL_TYPE_ITEMS = {
	1: "role.BUTTON",
	2: "role.COMBOBOX",
	3: "role.EDITABLETEXT",
	4: "role.LIST",
	5: "role.SCROLLBAR",
	6: "role.STATICTEXT",
	7: "role.TOOLBAR",
	8: "role.STATUSBAR",
	11: "role.SLIDER",
	12: "role.SPINBUTTON",
	13: "role.POPUPMENU",
	18: "role.DIALOG",
	19: "role.RADIOBUTTON",
	20: "role.CHECKBOX",
	21: "role.GROUPING",
	22: "role.CHECKBOX",
	24: "role.GRAPHIC",
	25: "role.GRAPHIC",
	29: "role.TABCONTROL",
	30: "role.LIST",
	31: "role.TREEVIEW",
	36: "role.MENUBAR",
	41: "role.COMBOBOX",
	42: "role.PASSWORDEDIT",
	47: "role.LINK",
	52: "role.FRAME",
	53: "role.DOCUMENT",
	55: "role.LISTITEM",
	56: "role.TREEVIEWITEM",
	57: "role.LISTITEM",
	60: "state.INTERNAL_LINK",
	63: "role.FRAME",
	64: "role.TABLECELL",
	66: "role.EDITABLETEXT",
	68: "role.HEADING.1",
	69: "role.HEADING.2",
	70: "role.HEADING.3",
	71: "role.HEADING.4",
	72: "role.HEADING.5",
	73: "role.HEADING.6",
	76: "role.DROPDOWNBUTTON",
	78: "role.SPLITBUTTON",
	80: "role.TABLEROW",
	81: "role.TABLECOLUMN",
	82: "role.TABLEROWHEADER",
	83: "role.TABLECOLUMNHEADER",
	85: "role.LIST",
	86: "role.LISTITEM",
	91: "role.FOOTNOTE",
	94: "role.EMBEDDEDOBJECT",
	99: "role.PARAGRAPH",
	100: "role.TOGGLEBUTTON",
	103: "role.REGION",
	104: "role.ARTICLE",
	105: "landmark.banner",
	106: "landmark.complementary",
	107: "landmark.contentinfo",
	108: "landmark.form",
	109: "landmark.main",
	110: "landmark.navigation",
	111: "landmark.search",
	115: "role.TABLE",
	116: "role.PROPERTYPAGE",
	120: "role.FIGURE",
}

#: JAWS control states (CTRL_ constants) -> ClassicSpeech item ids.
CONTROL_STATE_ITEMS = {
	0x0001: "state.CHECKED",
	0x0002: "state.CHECKED.off",
	0x0008: "state.UNAVAILABLE",
	0x0010: "state.HASPOPUP",
	0x0020: "state.PRESSED",
	0x0040: "state.EXPANDED",
	0x0080: "state.COLLAPSED",
	0x0100: "state.SELECTED",
	0x0800: "state.EXPANDED",
	0x1000: "state.COLLAPSED",
	0x4000: "state.VISITED",
	0x8000: "state.HALFCHECKED",
	0x10000: "state.READONLY",
	0x20000: "state.REQUIRED",
}

#: JAWS text attribute combinations -> ClassicSpeech formatting item ids.
ATTRIBUTE_ITEMS = {
	0x3: "fmt.bold",
	0x5: "fmt.italic",
	0x9: "fmt.underline",
	0x11: "fmt.strikethrough",
	0x21: "role.GRAPHIC",
	0x41: "fmt.highlightColor",
	0x401: "fmt.doubleStrikethrough",
	0x801: "fmt.superscript",
	0x1001: "fmt.subscript",
	0x88001: "role.LINK",
	0x208001: "fmt.spellingError",
	0x1008001: "fmt.grammarError",
	0x4008001: "fmt.inserted",
	0x8008001: "fmt.deleted",
	0x10008001: "fmt.revised",
	0x40008001: "fmt.comment",
	0x200008001: "fmt.hidden",
	0x400008001: "fmt.marked",
	0x4000008001: "fmt.comment.resolved",
	0x8000008001: "fmt.comment.draft",
	0x20000008001: "fmt.bookmark",
}

ANNOTATION_ITEMS = {
	"spelling": "fmt.spellingError",
	"grammar": "fmt.grammarError",
	"revision": "fmt.revised",
	"comment": "fmt.comment",
	"bookmark": "fmt.bookmark",
	"insertion": "fmt.inserted",
	"deletion": "fmt.deleted",
}

INDENTATION_ITEMS = {
	"justifiedleft": "fmt.align.left",
	"justifiedcenter": "fmt.align.center",
	"justifiedright": "fmt.align.right",
	"justifiedleftandright": "fmt.align.justify",
}

HTML_ATTRIBUTE_ITEMS = {
	"onclick": "state.CLICKABLE",
}

#: Voice alias names that always mean "the current voice".
_NEUTRAL_ALIASES = {"*", ""}

#: Where each JAWS voice alias belongs in ClassicSpeech when no scheme says otherwise.
#: Aliases for cursors and messages are covered by Voice Profiles; capitals and spelling by NVDA itself.
ALIAS_ITEMS = {
	"boldvoice": ("fmt.bold",),
	"italicvoice": ("fmt.italic",),
	"underlinevoice": ("fmt.underline",),
	"strikeoutvoice": ("fmt.strikethrough",),
	"doublestrikeoutvoice": ("fmt.doubleStrikethrough",),
	"graphicvoice": ("role.GRAPHIC",),
	"highlightvoice": ("fmt.highlightColor", "fmt.marked"),
	"superscriptvoice": ("fmt.superscript",),
	"subscriptvoice": ("fmt.subscript",),
	"headervoice": ("role.HEADING",),
	"headinglevel1voice": ("role.HEADING.1",),
	"headinglevel2voice": ("role.HEADING.2",),
	"headinglevel3voice": ("role.HEADING.3",),
	"headinglevel4voice": ("role.HEADING.4",),
	"headinglevel5voice": ("role.HEADING.5",),
	"headinglevel6voice": ("role.HEADING.6",),
	"linkvoice": ("role.LINK",),
	"quotationvoice": ("role.BLOCKQUOTE",),
}

#: Aliases with no ClassicSpeech item, and where their effect goes instead.
ALIASES_ELSEWHERE = {
	"pccursorvoice": "the PC cursor voice profile (ClassicSpeech Focus and navigation)",
	"jawscursorvoice": "the JAWS cursor voice profile (ClassicSpeech Review and Mouse)",
	"messagevoice": "the message voice profile (ClassicSpeech System and notifications) and scheme items that use it",
	"keyboardvoice": "the keyboard voice profile (ClassicSpeech Keyboard entry)",
	"menuanddialogvoice": "the menu and dialog voice profile",
	"globalvoice": "NVDA's own voice settings",
	"normalvoice": "NVDA's own voice settings",
	"singlecapvoice": "NVDA's capital pitch change",
	"allcapsvoice": "NVDA's capital pitch change",
	"smallcapsvoice": "NVDA's capital pitch change",
	"spellingvoice": "NVDA's spelling, which has no separate voice",
}


@dataclass
class SchemeItem:
	itemId: str
	#: Absolute path of a JAWS sound, or "".
	sound: str = ""
	soundOnly: bool = False
	#: Voice alias name to resolve, or "".
	voiceAlias: str = ""
	source: str = ""


@dataclass
class ConvertedScheme:
	name: str
	title: str
	sourcePath: str
	items: dict = field(default_factory=dict)
	notConverted: list = field(default_factory=list)
	missingSounds: list = field(default_factory=list)

	@property
	def soundCount(self) -> int:
		return sum(1 for item in self.items.values() if item.sound)


def _behavior(value: str) -> tuple[int | None, list[str]]:
	fields = (value or "").split("|")
	return jawsFiles.parseInt(fields[0]), [field_.strip() for field_ in fields[1:]] + ["", "", "", ""]


def _aliasName(data: str) -> str:
	return (data or "").split(":", 1)[0].strip()


def convertScheme(ini: jawsFiles.IniFile, path: str, findSound, aliases: dict) -> ConvertedScheme:
	"""Convert one JAWS scheme.

	``findSound(name)`` finds a JAWS sound file; ``aliases`` is ``{alias name: alias value}``
	from the voice profile, used to tell which aliases really change the voice.
	"""
	title = ini.get("Information", "Title") or os.path.splitext(os.path.basename(path))[0]
	scheme = ConvertedScheme(name=f"{title} (from JAWS)", title=title, sourcePath=path)
	lowerAliases = {name.lower(): value for name, value in aliases.items()}

	def aliasChangesVoice(alias: str) -> bool:
		if alias.lower() in _NEUTRAL_ALIASES:
			return False
		value = lowerAliases.get(alias.lower())
		if value is None:
			return False
		return not voices.aliasIsNeutral(value)

	def addEntry(itemId: str, value: str, source: str):
		behavior, data = _behavior(value)
		if behavior is None:
			return
		if itemId in scheme.items:
			# Tables are read most specific first: a link's control type entry beats the
			# hypertext attribute entry that JAWS also consults.
			return
		if behavior == 2:
			soundName = data[1]
			soundPath = findSound(soundName) if soundName else None
			if soundPath is None:
				scheme.missingSounds.append(f"{source}: {soundName or 'no sound named'}")
				return
			scheme.items[itemId] = SchemeItem(itemId, sound=soundPath, soundOnly=True, source=source)
		elif behavior in (1, 3):
			alias = _aliasName(data[2] if behavior == 3 else data[0])
			if aliasChangesVoice(alias):
				scheme.items[itemId] = SchemeItem(itemId, voiceAlias=alias, source=source)
			if behavior == 1 and ":" in data[0]:
				scheme.notConverted.append(f"{source}: JAWS says \"{data[0].split(':', 1)[1]}\"; ClassicSpeech keeps NVDA's wording.")
		elif behavior == 0:
			scheme.notConverted.append(f"{source}: JAWS says nothing here; ClassicSpeech schemes cannot silence an item.")
		elif behavior == 4:
			scheme.notConverted.append(f"{source}: JAWS switches language here; NVDA does this automatically.")

	section = ini.section("ControlType Behavior Table")
	for key, value in section.items() if section else ():
		number = jawsFiles.parseInt(key)
		if number in CONTROL_TYPE_ITEMS:
			addEntry(CONTROL_TYPE_ITEMS[number], value, f"Control type {key}")
	section = ini.section("ControlState Behavior Table")
	for key, value in section.items() if section else ():
		number = jawsFiles.parseInt(key)
		if number in CONTROL_STATE_ITEMS:
			addEntry(CONTROL_STATE_ITEMS[number], value, f"Control state {key}")
	section = ini.section("Attribute Behavior Table")
	for key, value in section.items() if section else ():
		number = jawsFiles.parseInt(key)
		if number in ATTRIBUTE_ITEMS:
			addEntry(ATTRIBUTE_ITEMS[number], value, f"Attribute {key}")
	for sectionName, table in (
		("Annotation Behavior Table", ANNOTATION_ITEMS),
		("Indentation Behavior Table", INDENTATION_ITEMS),
		("HTML Attribute Behavior Table", HTML_ATTRIBUTE_ITEMS),
	):
		section = ini.section(sectionName)
		for key, value in section.items() if section else ():
			itemId = table.get(key.lower())
			if itemId:
				addEntry(itemId, value, f"{sectionName.replace(' Behavior Table', '')} {key}")
	for sectionName, prefix in (("Font Name Behavior Table", "fmt.fontName."), ("Font Size Behavior Table", "fmt.fontSize."), ("Style Behavior Table", "fmt.styleName.")):
		section = ini.section(sectionName)
		for key, value in section.items() if section else ():
			if key.lower() == "default":
				continue
			addEntry(prefix + " ".join(key.split()).lower(), value, f"{sectionName.replace(' Behavior Table', '')} {key}")
	return scheme


def isSoundScheme(ini: jawsFiles.IniFile) -> bool:
	"""Whether a scheme plays any sounds (worth copying into ClassicSpeech)."""
	for section in ini.sections.values():
		for _key, value in section.items():
			behavior, _data = _behavior(value)
			if behavior == 2:
				return True
	return False


def aliasScheme(aliases: dict) -> ConvertedScheme:
	"""A scheme giving every JAWS voice alias that changes the voice its natural ClassicSpeech item."""
	scheme = ConvertedScheme(name="JAWS voice aliases", title="JAWS voice aliases", sourcePath="")
	for name, value in aliases.items():
		lowered = name.lower()
		if voices.aliasIsNeutral(value):
			continue
		items = ALIAS_ITEMS.get(lowered)
		if items:
			for itemId in items:
				scheme.items[itemId] = SchemeItem(itemId, voiceAlias=name, source=f"Voice alias {name}={value}")
		elif lowered in ALIASES_ELSEWHERE:
			scheme.notConverted.append(f"{name}: covered by {ALIASES_ELSEWHERE[lowered]}.")
		else:
			scheme.notConverted.append(f"{name}={value}: ClassicSpeech has no matching item.")
	return scheme
