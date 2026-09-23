# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Punctuation: JAWS symbol files (``.sbl``) as NVDA symbol pronunciations.

A JAWS symbol line is ``symbolN=<char> <flags> <text>``. The eight flag bits are
four pairs, for the All, Most, Some and None punctuation levels from left to
right; the first bit of a pair means "speak the text" at that level. So the
lowest JAWS level at which a symbol is spoken becomes its NVDA level: None ->
none, Some -> some, Most -> most, All -> all, never -> only when reading
characters.

Only symbols the user changed (their copy of a ``.sbl`` differs from the shared
copy) are migrated unless JAWS's own names are asked for. They go into NVDA's
user symbol file for the speech language, merged with what is already there.
"""

from __future__ import annotations

import codecs
import os
import re
from dataclasses import dataclass

from . import jawsFiles, safety

#: JAWS punctuation groups, left to right in the flags.
_LEVEL_ORDER = ("all", "most", "some", "none")
#: From least to most verbose: the first level at which a symbol is spoken wins.
_NVDA_LEVELS = (("none", "none"), ("some", "some"), ("most", "most"), ("all", "all"))


@dataclass
class JawsSymbol:
	character: str
	flags: str
	text: str

	@property
	def nvdaLevel(self) -> str:
		bits = self.flags.ljust(8, "0")
		spokenAt = {level: bits[index * 2] == "1" for index, level in enumerate(_LEVEL_ORDER)}
		for jawsLevel, nvdaLevel in _NVDA_LEVELS:
			if spokenAt[jawsLevel]:
				return nvdaLevel
		return "char"

	@property
	def spokenText(self) -> str:
		"""The words JAWS says, without the symbol JAWS adds back at the end for intonation."""
		text = self.text.strip()
		if len(text) > 1 and text.endswith(self.character) and not text.endswith(" " + self.character):
			text = text[: -len(self.character)].strip()
		return text

	@property
	def keepsSymbol(self) -> bool:
		text = self.text.strip()
		return len(text) > 1 and text.endswith(self.character)


_SYMBOL_LINE = re.compile(r"^(?P<char>\S+)\s+(?P<flags>[01]{8})\s*(?P<text>.*)$")


def parseSymbols(section: jawsFiles.IniSection | None) -> dict:
	"""``{character: JawsSymbol}`` for one language section of a ``.sbl`` file."""
	result = {}
	if section is None:
		return result
	for key, value in section.items():
		if not key.lower().startswith("symbol"):
			continue
		match = _SYMBOL_LINE.match(value.strip())
		if match is None:
			# The "=" symbol shows up as "symbol18== 11111100 equals": the key split takes one "=".
			match = _SYMBOL_LINE.match("=" + value.strip()) if value.startswith("=") else None
			if match is None:
				continue
		character = match.group("char")
		if character.lower().startswith("u+"):
			try:
				character = chr(int(character[2:], 16))
			except ValueError:
				continue
		result[character] = JawsSymbol(character, match.group("flags"), match.group("text"))
	return result


def languageSection(ini: jawsFiles.IniFile, lcid: int | None, jawsLanguage: str) -> jawsFiles.IniSection | None:
	"""Find the section for a language: ``[0x409]`` in synthesizer files, ``[enu]`` in default.sbl."""
	if ini.section(jawsLanguage):
		return ini.section(jawsLanguage)
	if lcid is not None:
		for name in (f"0x{lcid:x}", f"0x{lcid:X}", f"0x{lcid:04x}", str(lcid)):
			section = ini.section(name)
			if section is not None:
				return section
	return None


def changedSymbols(shared: dict, user: dict) -> dict:
	"""Symbols the user added or changed."""
	changed = {}
	for character, symbol in user.items():
		original = shared.get(character)
		if original is None or original.flags != symbol.flags or original.text.strip() != symbol.text.strip():
			changed[character] = symbol
	return changed


# -- NVDA symbol files ----------------------------------------------------------------

_ESCAPES = {"\0": "\\0", "\t": "\\t", "\n": "\\n", "\r": "\\r", "\f": "\\f", "\v": "\\v", "#": "\\#", "\\": "\\\\"}


def _identifier(character: str) -> str:
	if character and character[0] in _ESCAPES:
		return _ESCAPES[character[0]] + character[1:]
	return character


def mergeIntoSymbolFile(path: str, symbols: dict) -> int:
	"""Add or replace symbols in an NVDA user symbols file (``symbols-<locale>.dic``).

	Lines already in the file for other symbols, and its complex symbols, are kept as written.
	Returns the number of symbols written.
	"""
	if not symbols:
		return 0
	safety.checkWritable(path)
	complexLines: list[str] = []
	symbolLines: list[str] = []
	section = None
	if os.path.isfile(path):
		with codecs.open(path, "r", "utf_8_sig", errors="replace") as stream:
			for line in stream.read().splitlines():
				stripped = line.strip()
				if stripped == "complexSymbols:":
					section = "complex"
					continue
				if stripped == "symbols:":
					section = "symbols"
					continue
				if not stripped:
					continue
				(complexLines if section == "complex" else symbolLines).append(line)
	wanted = {_identifier(character): symbol for character, symbol in symbols.items()}
	kept = [line for line in symbolLines if line.split("\t", 1)[0] not in wanted]
	for identifier, symbol in wanted.items():
		preserve = "always" if symbol.keepsSymbol else "-"
		kept.append(f"{identifier}\t{symbol.spokenText or '-'}\t{symbol.nvdaLevel}\t{preserve}")
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with codecs.open(path, "w", "utf_8_sig", errors="replace") as stream:
		if complexLines:
			stream.write("complexSymbols:\r\n")
			for line in complexLines:
				stream.write(line + "\r\n")
			stream.write("\r\n")
		stream.write("symbols:\r\n")
		for line in kept:
			stream.write(line + "\r\n")
	return len(wanted)
