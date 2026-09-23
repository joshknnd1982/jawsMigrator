# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Readers for the file formats JAWS keeps its settings in.

JAWS stores nearly everything as Windows INI-style text:

* ``.jcf`` configuration (Settings Center, Quick Settings, window class reassignments...)
* ``.jkm`` key maps (Keyboard Manager, Navigation Quick Keys)
* ``.vpf`` voice profiles
* ``.smf`` speech and sounds schemes
* ``.jgf`` graphics labels, ``.jff``/``.jfd`` frames, ``jfw.ini``, ``.qs``/``.qsm`` quick settings data

and dictionaries as ``.jdf`` files, one entry per line, where the first character of
the line is the field delimiter.

The files come in several encodings: UTF-8 with or without a byte order mark,
UTF-16, and the Windows ANSI code page for older files. Nothing here depends on NVDA,
so these readers can be tested on their own.
"""

from __future__ import annotations

import os
import re
from collections import OrderedDict
from dataclasses import dataclass, field

#: Files larger than this are never read in full; JAWS settings files are small.
MAX_TEXT_BYTES = 16 * 1024 * 1024


def decodeBytes(data: bytes) -> str:
	"""Decode the bytes of a JAWS text file, whatever encoding it was written in."""
	if data.startswith(b"\xef\xbb\xbf"):
		return data[3:].decode("utf-8", "replace")
	if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
		return data.decode("utf-16", "replace")
	# UTF-16 without a byte order mark: every other byte of ASCII text is zero.
	if len(data) >= 4 and data[1:2] == b"\x00" and data[3:4] == b"\x00" and data[0:1] != b"\x00":
		try:
			return data.decode("utf-16-le")
		except UnicodeDecodeError:
			pass
	try:
		return data.decode("utf-8")
	except UnicodeDecodeError:
		return data.decode("cp1252", "replace")


def readText(path: str) -> str:
	"""Read a JAWS text file. Raises OSError when it can't be read."""
	with open(path, "rb") as stream:
		data = stream.read(MAX_TEXT_BYTES + 1)
	if len(data) > MAX_TEXT_BYTES:
		raise OSError(f"{path} is too large to be a JAWS settings file")
	return decodeBytes(data).replace("\x00", "")


def parseInt(value, default=None):
	"""Read an integer the way JAWS writes one.

	Accepts ``1``, ``" 1 "``, ``1;`` (a stray semicolon JAWS leaves in some files),
	``1 ; comment``, ``0x1F`` and ``-5``. Returns ``default`` for anything else.
	"""
	if value is None:
		return default
	if isinstance(value, bool):
		return int(value)
	if isinstance(value, int):
		return value
	text = str(value).strip()
	text = text.split(";", 1)[0].strip()
	if not text:
		return default
	try:
		if text.lower().startswith(("0x", "-0x")):
			return int(text, 16)
		return int(text)
	except ValueError:
		match = re.match(r"^-?\d+", text)
		if match:
			return int(match.group(0))
		return default


def stripInlineComment(value: str) -> str:
	"""Remove a trailing ``; comment`` that follows whitespace, as in ``Enable=1   ; 1=Enabled``."""
	match = re.search(r"\s;", value)
	if match:
		value = value[: match.start()]
	return value.strip()


@dataclass
class IniSection:
	"""One ``[section]`` of a JAWS INI-style file. Keys are case-insensitive, as in JAWS."""

	name: str
	#: lower-cased key -> (key as written, value)
	entries: "OrderedDict[str, tuple[str, str]]" = field(default_factory=OrderedDict)
	#: Every ``(key as written, value)`` line in file order, repeated keys included, or None.
	#: Only kept for files read with ``keepRepeatedKeys`` (symbol files reuse ``symbolN`` keys).
	lines: "list[tuple[str, str]] | None" = None

	def get(self, key: str, default=None):
		entry = self.entries.get(key.lower())
		return entry[1] if entry is not None else default

	def getInt(self, key: str, default=None):
		return parseInt(self.get(key), default)

	def set(self, key: str, value: str) -> None:
		self.entries[key.lower()] = (key, value)
		if self.lines is not None:
			self.lines.append((key, value))

	def __contains__(self, key: str) -> bool:
		return key.lower() in self.entries

	def __len__(self) -> int:
		return len(self.entries)

	def items(self):
		"""``(key as written, value)`` pairs in file order."""
		return list(self.entries.values())

	def allItems(self):
		"""Every ``(key as written, value)`` line in file order, repeated keys included when they were kept.

		For a section read without ``keepRepeatedKeys`` this is the same as :meth:`items`.
		"""
		return list(self.lines) if self.lines is not None else self.items()

	def keys(self):
		return [key for key, _value in self.entries.values()]


@dataclass
class IniFile:
	"""A parsed JAWS INI-style file. Section names are case-insensitive."""

	path: str | None = None
	sections: "OrderedDict[str, IniSection]" = field(default_factory=OrderedDict)

	def section(self, name: str) -> IniSection | None:
		return self.sections.get(name.lower())

	def ensureSection(self, name: str) -> IniSection:
		section = self.sections.get(name.lower())
		if section is None:
			section = self.sections[name.lower()] = IniSection(name)
		return section

	def get(self, sectionName: str, key: str, default=None):
		section = self.section(sectionName)
		if section is None:
			return default
		return section.get(key, default)

	def getInt(self, sectionName: str, key: str, default=None):
		return parseInt(self.get(sectionName, key), default)

	def __contains__(self, sectionName: str) -> bool:
		return sectionName.lower() in self.sections

	def sectionNames(self):
		return [section.name for section in self.sections.values()]

	def entryCount(self) -> int:
		return sum(len(section) for section in self.sections.values())


_SECTION_LINE = re.compile(r"^\s*\[(?P<name>.*)\]\s*(?:;.*)?$")


def parseIni(text: str, path: str | None = None, inlineComments: bool = False, keepRepeatedKeys: bool = False) -> IniFile:
	"""Parse JAWS INI-style text.

	Lines starting with ``;`` are comments. Keys are split from values at the first
	``=`` that is not the first character, so a key map line for the equals key still
	parses. When a key repeats within a section, the last value wins, which is how
	JAWS itself reads these files. ``inlineComments`` strips ``value ; comment`` tails,
	which JAWS writes in ``.jcf`` and ``jfw.ini`` but never in key maps or schemes.

	``keepRepeatedKeys`` also keeps every line of each section, repeated keys included, in
	file order (:meth:`IniSection.allItems`). Symbol files need it: some number two different
	symbols with the same ``symbolN`` key. Lookups by key still give the last value.
	"""
	result = IniFile(path=path)
	current = None
	for rawLine in text.splitlines():
		line = rawLine.strip()
		if not line or line.startswith(";"):
			continue
		match = _SECTION_LINE.match(line)
		if match and "=" not in line.split("]", 1)[0][1:]:
			current = result.ensureSection(match.group("name").strip())
			if keepRepeatedKeys and current.lines is None:
				current.lines = []
			continue
		separator = line.find("=", 1)
		if separator < 0:
			continue
		key = line[:separator].strip()
		value = line[separator + 1 :].strip()
		if inlineComments:
			value = stripInlineComment(value)
		if current is None:
			# Keys before any section header: keep them in an unnamed section.
			current = result.ensureSection("")
			if keepRepeatedKeys and current.lines is None:
				current.lines = []
		current.set(key, value)
	return result


def readIni(path: str, inlineComments: bool = False, keepRepeatedKeys: bool = False) -> IniFile:
	return parseIni(readText(path), path=path, inlineComments=inlineComments, keepRepeatedKeys=keepRepeatedKeys)


def mergeIni(*files: IniFile | None) -> IniFile:
	"""Merge INI files, later files overriding earlier ones key by key.

	This is how JAWS layers a user's settings over the shared settings: the user
	file only contains what the user changed.
	"""
	merged = IniFile(path=None)
	for iniFile in files:
		if iniFile is None:
			continue
		for section in iniFile.sections.values():
			target = merged.ensureSection(section.name)
			for key, value in section.items():
				target.set(key, value)
	return merged


# -- dictionaries ------------------------------------------------------------------


@dataclass
class JdfEntry:
	"""One Dictionary Manager rule."""

	word: str
	replacement: str
	#: ``*`` for every language, otherwise a language id such as ``0x09`` or ``0x409``.
	language: str = "*"
	#: ``*`` for every synthesizer, otherwise a JAWS synthesizer's long name.
	synthesizer: str = "*"
	voice: str = "*"
	caseSensitive: bool = False
	#: The next field as JAWS wrote it; JAWS uses it for how the rule matches.
	matchFlags: str = "0"
	#: Anything after the known fields (such as a sound file), kept as written.
	extra: list = field(default_factory=list)
	sourceFile: str = ""
	lineNumber: int = 0

	@property
	def isRootWord(self) -> bool:
		"""True for ``reposition*``, which JAWS applies to every word starting with ``reposition``."""
		return self.word.endswith("*") and len(self.word) > 1

	@property
	def sound(self) -> str:
		for value in [self.replacement, *self.extra]:
			if value.lower().endswith(".wav"):
				return value
		return ""


_CHARACTER_CODE = re.compile(r"\\([0-9]+)")
#: The largest character code, 0x10FFFF, has seven digits.
_MAX_CODE_DIGITS = 7


def decodeCharacterCodes(text: str) -> str:
	r"""Turn the ``\NNN`` character codes of a JAWS dictionary rule into the characters they stand for.

	The number is decimal: ``\8211`` is the character U+2013 (an en dash). Codes 128 to 159 are
	Windows-1252 characters, as JAWS's own rules use them: ``\150`` is also an en dash and ``\145``
	a left single quotation mark. A backslash that is not followed by digits is kept as it is, and
	so is a code no character has (``\0``, surrogates, anything above U+10FFFF).
	"""
	if "\\" not in text:
		return text

	def character(match) -> str:
		digits = match.group(1)
		if len(digits) > _MAX_CODE_DIGITS:
			return match.group(0)
		number = int(digits)
		if 128 <= number <= 159:
			try:
				return bytes([number]).decode("cp1252")
			except UnicodeDecodeError:
				# 0x81, 0x8D, 0x8F, 0x90 and 0x9D have no Windows-1252 character; Windows keeps the code.
				return chr(number)
		if number == 0 or number > 0x10FFFF or 0xD800 <= number <= 0xDFFF:
			return match.group(0)
		return chr(number)

	return _CHARACTER_CODE.sub(character, text)


def parseJdf(text: str, path: str | None = None) -> list[JdfEntry]:
	"""Parse a JAWS dictionary (``.jdf``).

	Each line is ``<d>word<d>replacement<d>language<d>synthesizer<d>voice<d>case<d>flags<d>``
	where ``<d>`` is whatever character the line starts with (usually a period).
	Older files only have ``<d>word<d>replacement<d>``. The word and the replacement may
	name characters by code, such as ``\\8211`` (see :func:`decodeCharacterCodes`).
	"""
	entries = []
	for lineNumber, rawLine in enumerate(text.splitlines(), start=1):
		line = rawLine.rstrip("\r\n")
		if len(line) < 3 or line.strip() == "":
			continue
		delimiter = line[0]
		if delimiter.isalnum() or delimiter.isspace():
			continue
		parts = line[1:].split(delimiter)
		# A well-formed line ends with the delimiter, leaving an empty last part.
		if parts and parts[-1] == "":
			parts = parts[:-1]
		if len(parts) < 2 or not parts[0]:
			continue
		entry = JdfEntry(
			word=decodeCharacterCodes(parts[0]),
			replacement=decodeCharacterCodes(parts[1]),
			sourceFile=path or "",
			lineNumber=lineNumber,
		)
		if len(parts) > 2 and parts[2]:
			entry.language = parts[2]
		if len(parts) > 3 and parts[3]:
			entry.synthesizer = parts[3]
		if len(parts) > 4 and parts[4]:
			entry.voice = parts[4]
		if len(parts) > 5:
			entry.caseSensitive = parseInt(parts[5], 0) == 1
		if len(parts) > 6:
			entry.matchFlags = parts[6] or "0"
		if len(parts) > 7:
			entry.extra = [part for part in parts[7:] if part]
		entries.append(entry)
	return entries


def readJdf(path: str) -> list[JdfEntry]:
	return parseJdf(readText(path), path=path)


# -- languages -----------------------------------------------------------------------

#: JAWS three-letter language folders -> (Windows LCID, NVDA/ISO language code)
JAWS_LANGUAGES = {
	"enu": (0x0409, "en_US"),
	"eng": (0x0809, "en_GB"),
	"enc": (0x1009, "en_CA"),
	"ena": (0x0C09, "en_AU"),
	"deu": (0x0407, "de_DE"),
	"des": (0x0807, "de_CH"),
	"fra": (0x040C, "fr_FR"),
	"frc": (0x0C0C, "fr_CA"),
	"esn": (0x0C0A, "es_ES"),
	"esp": (0x040A, "es_ES"),
	"esm": (0x080A, "es_MX"),
	"ita": (0x0410, "it_IT"),
	"ptb": (0x0416, "pt_BR"),
	"ptg": (0x0816, "pt_PT"),
	"nld": (0x0413, "nl_NL"),
	"nlb": (0x0813, "nl_BE"),
	"sve": (0x041D, "sv_SE"),
	"nor": (0x0414, "nb_NO"),
	"dan": (0x0406, "da_DK"),
	"fin": (0x040B, "fi_FI"),
	"hun": (0x040E, "hu_HU"),
	"plk": (0x0415, "pl_PL"),
	"csy": (0x0405, "cs_CZ"),
	"sky": (0x041B, "sk_SK"),
	"trk": (0x041F, "tr_TR"),
	"ukr": (0x0422, "uk_UA"),
	"rus": (0x0419, "ru_RU"),
	"arb": (0x0401, "ar_SA"),
	"heb": (0x040D, "he_IL"),
	"kkz": (0x043F, "kk_KZ"),
	"lvi": (0x0426, "lv_LV"),
	"chs": (0x0804, "zh_CN"),
	"cht": (0x0404, "zh_TW"),
	"jpn": (0x0411, "ja_JP"),
	"kor": (0x0412, "ko_KR"),
	"isl": (0x040F, "is_IS"),
	"cat": (0x0403, "ca_ES"),
	"glc": (0x0456, "gl_ES"),
	"ell": (0x0408, "el_GR"),
}

#: Windows LCIDs -> NVDA language codes, for voice profiles that name a language by LCID.
LCID_LANGUAGES = {lcid: code for lcid, code in JAWS_LANGUAGES.values()}
LCID_LANGUAGES.update({0x040A: "es_ES", 0x0C0A: "es_ES", 0x0816: "pt_PT", 0x0C04: "zh_HK"})


def lcidFromText(text) -> int | None:
	"""Read a JAWS language id: ``0x409``, ``0x09``, ``1033``. ``*`` and empty give None."""
	if text is None:
		return None
	value = str(text).strip()
	if not value or value == "*":
		return None
	number = parseInt(value)
	if number is None or number < 0:
		return None
	return number


def primaryLanguageId(lcid: int) -> int:
	"""The primary language part of an LCID: 0x0409 and 0x0809 are both 0x09 (English)."""
	return lcid & 0x3FF


def languageCodeForLcid(lcid: int | None) -> str | None:
	if lcid is None:
		return None
	if lcid in LCID_LANGUAGES:
		return LCID_LANGUAGES[lcid]
	primary = primaryLanguageId(lcid)
	for known, code in LCID_LANGUAGES.items():
		if primaryLanguageId(known) == primary:
			return code.split("_", 1)[0]
	return None


def languageMatches(entryLanguage, wantedLcid: int | None) -> bool:
	"""Whether a rule restricted to ``entryLanguage`` applies to the language ``wantedLcid``.

	A rule for all languages always applies. A rule for a primary language (``0x09``)
	applies to every dialect of it; a rule for a full LCID applies to that dialect.
	"""
	ruleLcid = lcidFromText(entryLanguage)
	if ruleLcid is None or wantedLcid is None:
		return True
	if ruleLcid <= 0x3FF:
		return primaryLanguageId(wantedLcid) == ruleLcid
	return ruleLcid == wantedLcid or primaryLanguageId(ruleLcid) == primaryLanguageId(wantedLcid)


def fileExtension(path: str) -> str:
	return os.path.splitext(path)[1].lower().lstrip(".")
