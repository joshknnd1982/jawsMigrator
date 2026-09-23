# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Dictionary Manager rules (``.jdf``) as NVDA speech dictionary entries.

JAWS matches whole words unless the word ends in ``*``, which makes it a root:
``reposition*`` changes "reposition", "repositions" and "repositioning", keeping
the ending. NVDA gets a whole-word entry for plain words, an "anywhere" entry for
rules made of symbols (whole-word matching needs letters at both ends), and a
regular expression anchored at the start of a word for roots, which keeps the
ending exactly as JAWS does.

Rules for another language are skipped. Rules for one synthesizer are kept for
that synthesizer's voice dictionary. Rules that only play a sound cannot be
migrated, because NVDA dictionaries only replace text.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from . import jawsFiles, safety

#: NVDA speech dictionary entry types (speechDictHandler.types.EntryType).
TYPE_ANYWHERE = 0
TYPE_REGEXP = 1
TYPE_WORD = 2


@dataclass
class DictEntry:
	pattern: str
	replacement: str
	caseSensitive: bool
	type: int
	comment: str
	#: JAWS synthesizer long name when the rule is for one synthesizer, else "".
	jawsSynthesizer: str = ""
	jawsVoice: str = ""
	source: jawsFiles.JdfEntry | None = None

	def key(self) -> tuple:
		return (self.pattern if self.caseSensitive else self.pattern.lower(), self.type)

	def asLine(self) -> str:
		"""The entry as a line of an NVDA ``.dic`` file."""
		pattern = self.pattern.replace("#", r"\#")
		replacement = self.replacement.replace("#", r"\#")
		return f"{pattern}\t{replacement}\t{int(self.caseSensitive)}\t{int(self.type)}"


@dataclass
class Skipped:
	entry: jawsFiles.JdfEntry
	reason: str


@dataclass
class DictConversion:
	entries: list = field(default_factory=list)
	skipped: list = field(default_factory=list)


def _isWordCharacter(character: str) -> bool:
	return bool(re.match(r"\w", character or ""))


def convertEntry(entry: jawsFiles.JdfEntry, fileLabel: str) -> tuple[DictEntry | None, str]:
	"""Convert one JAWS rule. Returns ``(entry, "")`` or ``(None, reason)``."""
	word = entry.word
	replacement = entry.replacement
	if not word.strip():
		return None, "The rule has no word."
	if entry.sound and not replacement.strip():
		return None, f"JAWS plays {entry.sound} instead of speaking the word; NVDA dictionaries cannot play sounds."
	if not replacement.strip():
		# JAWS rules with no replacement only change the word's sound or language; in NVDA they would delete the word.
		return None, "The rule only changes the sound or language JAWS uses for the word."
	if replacement.lower().endswith(".wav"):
		return None, f"JAWS plays {replacement}; NVDA dictionaries cannot play sounds."
	comment = f"From JAWS {fileLabel}"
	if entry.lineNumber:
		comment += f", line {entry.lineNumber}"
	if "*" in word.strip("*") or entry.isRootWord or word.startswith("*"):
		# A JAWS wildcard: a root word (reposition*) or a wildcard inside the word.
		startsWithWildcard = word.startswith("*")
		endsWithWildcard = word.endswith("*")
		parts = [part for part in word.strip("*").split("*")]
		body = r"\w*".join(re.escape(part) for part in parts)
		prefix = "" if startsWithWildcard or not _isWordCharacter(parts[0][:1]) else r"\b"
		suffix = "" if endsWithWildcard or not _isWordCharacter(parts[-1][-1:]) else r"\b"
		pattern = prefix + body + suffix
		result = DictEntry(
			pattern=pattern,
			replacement=replacement.replace("\\", "\\\\"),
			caseSensitive=entry.caseSensitive,
			type=TYPE_REGEXP,
			comment=comment + f" (root word {word})",
		)
	elif _isWordCharacter(word[0]) and _isWordCharacter(word[-1]):
		result = DictEntry(word, replacement, entry.caseSensitive, TYPE_WORD, comment)
	else:
		result = DictEntry(word, replacement, entry.caseSensitive, TYPE_ANYWHERE, comment)
	if entry.synthesizer not in ("", "*"):
		result.jawsSynthesizer = entry.synthesizer
		result.jawsVoice = "" if entry.voice in ("", "*") else entry.voice
	result.source = entry
	return result, ""


def convertRules(
	rules: list[jawsFiles.JdfEntry],
	fileLabel: str,
	languageLcid: int | None,
	existing: set | None = None,
) -> DictConversion:
	"""Convert the rules of one ``.jdf`` for NVDA, keeping one entry per word."""
	conversion = DictConversion()
	seen = set(existing or ())
	for rule in rules:
		if not jawsFiles.languageMatches(rule.language, languageLcid):
			conversion.skipped.append(Skipped(rule, f"The rule is for another language ({rule.language})."))
			continue
		entry, reason = convertEntry(rule, fileLabel)
		if entry is None:
			conversion.skipped.append(Skipped(rule, reason))
			continue
		key = entry.key() + (entry.jawsSynthesizer.lower(),)
		if key in seen:
			conversion.skipped.append(Skipped(rule, "NVDA's dictionary already has this word."))
			continue
		seen.add(key)
		conversion.entries.append(entry)
	return conversion


# -- NVDA dictionary files ------------------------------------------------------------


def readDicPatterns(path: str) -> set:
	"""``(pattern, type)`` keys of the entries already in an NVDA ``.dic`` file."""
	keys = set()
	try:
		with open(path, encoding="utf_8_sig", errors="replace") as stream:
			for line in stream:
				line = line.rstrip("\r\n")
				if not line or line.startswith("#"):
					continue
				fields = line.split("\t")
				if len(fields) != 4:
					continue
				pattern = fields[0].replace(r"\#", "#")
				try:
					caseSensitive = bool(int(fields[2]))
					entryType = int(fields[3])
				except ValueError:
					continue
				keys.add((pattern if caseSensitive else pattern.lower(), entryType, ""))
	except OSError:
		pass
	return keys


def appendToDicFile(path: str, entries: list[DictEntry], heading: str) -> int:
	"""Add entries to the end of an NVDA ``.dic`` file, creating it when needed."""
	if not entries:
		return 0
	safety.checkWritable(path)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	existing = ""
	if os.path.isfile(path):
		with open(path, encoding="utf_8_sig", errors="replace") as stream:
			existing = stream.read()
	with open(path, "w", encoding="utf_8_sig", errors="replace") as stream:
		if existing:
			stream.write(existing.rstrip("\r\n") + "\n\n")
		for index, entry in enumerate(entries):
			comment = entry.comment if index else f"{heading}. {entry.comment}"
			stream.write(f"#{comment}\n")
			stream.write(entry.asLine() + "\n")
	return len(entries)
