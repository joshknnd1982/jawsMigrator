# Unit tests for version 1.21, from a tester's report (issue 13): reading an article on profootballrumors.com in Edge,
# the tester heard a player's name and the word "job" said wrongly. NVDA's log shows the text as NVDA had it before its
# speech dictionaries changed it ("Speaking [...]"), so it can't show what NVDA said. Freedom Scientific's own dictionary
# for the Bible program Theophilos (JAWS 2026, SETTINGS\enu\Theophilos.jdf, line 40) has "Job" -> "jobe", not
# case-sensitive, for the Book of Job, and JAWS uses it only in Theophilos. Versions 1.0 to 1.20 put the rules of every
# JAWS application dictionary into NVDA's default dictionary, where they change speech in every program: "job" became
# "jobe", Excel.jdf's "a" -> "eigh" changed every "a" (three times in the article the tester read), and Outlook.jdf's
# "\133" (an ellipsis) -> "dot dot dot" changed every ellipsis. The
# tester's default dictionary has 608 rules; JAWS 2026's shared dictionaries make 393 of them, and its Eloquence rules
# the 28 of the tester's voice dictionary, so the rest are the tester's own JAWS rules.
# - appDicts: each JAWS application dictionary is a file of its own, used only while the focus is in its programs,
#   before NVDA's own dictionaries, as JAWS uses an application's dictionary before its default one.
# - dictRepair: the rules versions 1.0 to 1.20 put in NVDA's default and voice dictionaries move into those files.
# - migrator: a migration writes them there.
# - appDicts: when NVDA logs at its debug level, the log names each dictionary rule that changes what NVDA says.
# The imitation NVDA is NVDA's own speechDictHandler, word for word: from NVDA 2026.2, SpeechDictEntry, SpeechDict,
# SpeechDictDefinition, _selectRegexEngine and processText, with its builtin.dic; from NVDA 2026.1, the add-on's oldest,
# SpeechDictEntry, SpeechDict and processText. NVDA 2026.2 compiles whole-word entries with the regex module, which this
# Python lacks; the stand-in is re, which gives the same results for this text. The dictionaries are NVDA's in the order
# NVDA 2026.2 makes them (definitions._addSpeechDictionaries): temporary, voice, default, built-in. The rules of the
# JAWS files are Freedom Scientific's own, at their lines in JAWS 2026. The assistant's code is the real one.
# Run: python -m unittest tests.test_v121_fixes -v

import codecs
import enum
import fnmatch
import logging
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass, field
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import (  # noqa: E402
	appDicts,
	dictMap,
	dictRepair,
	jawsDetect,
	jawsFiles,
	jawsIndex,
	migrator,
	nvdaApply,
	nvdaEnv,
	systemCheck,
)

# -- NVDA's own code ---------------------------------------------------------------------------------------------------

# NVDA 2026.2's speechDictHandler/types.py: _selectRegexEngine, SpeechDictEntry, SpeechDict and SpeechDictDefinition,
# word for word.
NVDA_2026_2_TYPES = r'''
def _selectRegexEngine(entryType: "EntryType") -> ModuleType:
	"""Return the regex module to use for compiling a SpeechDictEntry of the
	given type.

	Word-boundary entry types always use the `regex` module under VERSION1
	semantics so combining marks are included in \\w. The REGEXP type uses
	`regex` only when the ``speechDictsUseModernRegex`` feature flag is enabled.
	Other types use the stdlib `re` module.
	"""
	if entryType in (
		EntryType.WORD,
		EntryType.PART_OF_WORD,
		EntryType.START_OF_WORD,
		EntryType.END_OF_WORD,
	):
		return regex
	if entryType is EntryType.REGEXP and config.conf["featureFlag"]["speechDictsUseModernRegex"]:
		return regex
	return re


@dataclass
class SpeechDictEntry:
	pattern: str
	"""The pattern to match."""
	replacement: str
	"""The replacement string."""
	comment: str = ""
	"""A comment associated with this entry."""
	caseSensitive: bool = True
	"""Whether the match is case sensitive."""
	type: EntryType = EntryType.ANYWHERE
	"""The type of the entry."""
	compiled: "re.Pattern[str] | regex.Pattern[str]" = field(init=False)
	"""The compiled regular expression. May be a `re.Pattern` or a
	`regex.Pattern` depending on the entry type."""

	def __post_init__(self):
		engine = _selectRegexEngine(self.type)
		flags = engine.UNICODE
		if engine is regex:
			flags |= regex.VERSION1
		if not self.caseSensitive:
			flags |= engine.IGNORECASE
		match self.type:
			case EntryType.REGEXP:
				tempPattern = self.pattern
			case EntryType.WORD:
				tempPattern = rf"\b{engine.escape(self.pattern)}\b"
			case EntryType.PART_OF_WORD:
				escaped = engine.escape(self.pattern)
				tempPattern = rf"(?<=\w){escaped}|{escaped}(?=\w)"
			case EntryType.START_OF_WORD:
				tempPattern = rf"\b{engine.escape(self.pattern)}(?=\w)"
			case EntryType.END_OF_WORD:
				tempPattern = rf"(?<=\w){engine.escape(self.pattern)}\b"
			case EntryType.UNIX:
				# fnmatch.translate appends \Z to the end of the pattern; discard that anchor.
				translated = fnmatch.translate(self.pattern)
				suffix = r"\Z"
				if translated.endswith(suffix):
					tempPattern = translated.removesuffix(suffix)
				else:
					tempPattern = translated
			case _:
				tempPattern = engine.escape(self.pattern)
				self.type = EntryType.ANYWHERE  # Ensure sane values.
		self.compiled = engine.compile(tempPattern, flags)

	def sub(self, text: str) -> str:
		if self.type == EntryType.REGEXP:
			replacement = self.replacement
		else:
			# Escape the backslashes for non-regexp replacements
			replacement = self.replacement.replace("\\", "\\\\")
		return self.compiled.sub(replacement, text)


class SpeechDict(list[SpeechDictEntry]):
	fileName: str | None = None

	def __repr__(self) -> str:
		return f"{self.__class__.__name__} ({len(self)} entries, fileName={self.fileName})"

	def load(self, fileName: str, raiseOnError: bool = False) -> None:
		self.fileName = fileName
		comment = ""
		self.clear()
		log.debug("Loading speech dictionary %r...", fileName)
		if not os.path.isfile(fileName):
			msg = f"file {fileName!r} not found."
			if raiseOnError:
				raise FileNotFoundError(msg)
			log.debug(msg)
			return
		with open(fileName, encoding="utf_8_sig", errors="replace") as file:
			for line in file:
				if line.isspace():
					comment = ""
					continue
				line = line.rstrip("\r\n")
				if line.startswith("#"):
					if comment:
						comment += " "
					comment += line[1:]
				else:
					temp = line.split("\t")
					if len(temp) == 4:
						pattern = temp[0].replace(r"\#", "#")
						replace = temp[1].replace(r"\#", "#")
						try:
							dictionaryEntry = SpeechDictEntry(
								pattern,
								replace,
								comment,
								caseSensitive=bool(int(temp[2])),
								type=EntryType(int(temp[3])),
							)
							self.append(dictionaryEntry)
						except Exception as e:
							msg = f"Dictionary {fileName!r} entry invalid for {line!r}"
							if raiseOnError:
								raise ValueError(msg) from e
							log.exception(msg)
						comment = ""
					else:
						msg = f"can't parse line {line!r}"
						if raiseOnError:
							raise ValueError(msg)
						log.warning(msg)
			log.debug("%d loaded records.", len(self))

	def save(self, fileName: str | None = None):
		if not shouldWriteToDisk():
			log.debugWarning("Not writing dictionary, as shouldWriteToDisk returned False.")
			return
		if not fileName:
			fileName = getattr(self, "fileName", None)
		if not fileName:
			return
		dirName = os.path.dirname(fileName)
		if not os.path.isdir(dirName):
			os.makedirs(dirName)
		with open(fileName, "w", encoding="utf_8_sig", errors="replace") as file:
			for entry in self:
				if entry.comment:
					file.write(f"#{entry.comment}\n")
				pattern = entry.pattern.replace("#", r"\#")
				replacement = entry.replacement.replace("#", r"\#")
				file.write(f"{pattern}\t{replacement}\t{entry.caseSensitive:d}\t{entry.type:d}\n")

	def sub(self, text: str) -> str:
		invalidEntries = []
		for index, entry in enumerate(self):
			try:
				text = entry.sub(text)
			except (re.error, regex.error):
				dictName = self.fileName or DictionaryType.TEMP.value
				log.exception("Invalid dictionary entry %d in %r: %r", index + 1, dictName, entry.pattern)
				invalidEntries.append(index)
		for index in reversed(invalidEntries):
			del self[index]
		return text


@dataclass(frozen=True, kw_only=True)
class SpeechDictDefinition:
	"""An abstract class for a speech dictionary definition."""

	name: str
	"""The name of the dictionary."""

	path: str | None = None
	"""The path to the dictionary."""

	source: DictionaryType | str
	"""The source of the dictionary."""

	displayName: str | None = None
	"""The translatable name of the dictionary.
	When not provided, the dictionary can not be visible to the end user.
	"""

	mandatory: bool = False
	"""Whether this dictionary is mandatory.
	Mandatory dictionaries are always enabled."""

	dictionary: SpeechDict = field(init=False, repr=False, compare=False, default_factory=SpeechDict)

	def __post_init__(self):
		if not self.displayName and not self.mandatory:
			raise ValueError("A non-mandatory dictionary without a display name is unsupported")
		if self.path:
			self.dictionary.load(self.path, raiseOnError=self.source not in DictionaryType)

	@property
	def readOnly(self) -> bool:
		"""Whether this dictionary is read-only."""
		return self.source not in DictionaryType

	@property
	def userVisible(self) -> bool:
		"""Whether this dictionary is visible to end users (i.e. in the GUI).
		Mandatory dictionaries are hidden.
		"""
		return not self.mandatory and bool(self.displayName)

	@property
	def enabled(self) -> bool:
		return self.mandatory or self.name in config.conf["speech"]["speechDictionaries"]

	def sub(self, text: str) -> str:
		"""Applies the dictionary to the given text.
		:param text: The text to apply the dictionary to.
		:return: The text after applying the dictionary.
		"""
		return self.dictionary.sub(text)
'''

# NVDA 2026.2's speechDictHandler/__init__.py: processText, word for word.
NVDA_2026_2_PROCESS_TEXT = r'''
def processText(text: str) -> str:
	"""Processes the given text through all speech dictionaries.
	:param text: The text to process.
	:returns: The processed text.
	"""
	if not globalVars.speechDictionaryProcessing:
		return text
	for definition in definitions._speechDictDefinitions:
		if not definition.enabled:
			continue
		text = definition.sub(text)
	return text
'''

# NVDA 2026.1's speechDictHandler/__init__.py: its entry types, SpeechDictEntry, SpeechDict, dictTypes and processText,
# word for word.
NVDA_2026_1 = r'''
dictTypes = (
	"temp",
	"voice",
	"default",
	"builtin",
)  # ordered by their priority E.G. voice specific speech dictionary is processed before the default

ENTRY_TYPE_ANYWHERE = 0  # String can match anywhere
ENTRY_TYPE_WORD = 2  # String must have word boundaries on both sides to match
ENTRY_TYPE_REGEXP = 1  # Regular expression


class SpeechDictEntry:
	def __init__(self, pattern, replacement, comment, caseSensitive=True, type=ENTRY_TYPE_ANYWHERE):
		self.pattern = pattern
		flags = re.U
		if not caseSensitive:
			flags |= re.IGNORECASE
		if type == ENTRY_TYPE_REGEXP:
			tempPattern = pattern
		elif type == ENTRY_TYPE_WORD:
			tempPattern = r"\b" + re.escape(pattern) + r"\b"
		else:
			tempPattern = re.escape(pattern)
			type = ENTRY_TYPE_ANYWHERE  # Insure sane values.
		self.compiled = re.compile(tempPattern, flags)
		self.replacement = replacement
		self.comment = comment
		self.caseSensitive = caseSensitive
		self.type = type

	def sub(self, text: str) -> str:
		if self.type == ENTRY_TYPE_REGEXP:
			replacement = self.replacement
		else:
			# Escape the backslashes for non-regexp replacements
			replacement = self.replacement.replace("\\", "\\\\")
		return self.compiled.sub(replacement, text)


class SpeechDict(list):
	fileName = None

	def load(self, fileName):
		self.fileName = fileName
		comment = ""
		del self[:]
		log.debug("Loading speech dictionary '%s'..." % fileName)
		if not os.path.isfile(fileName):
			log.debug("file '%s' not found." % fileName)
			return
		file = codecs.open(fileName, "r", "utf_8_sig", errors="replace")
		for line in file:
			if line.isspace():
				comment = ""
				continue
			line = line.rstrip("\r\n")
			if line.startswith("#"):
				if comment:
					comment += " "
				comment += line[1:]
			else:
				temp = line.split("\t")
				if len(temp) == 4:
					pattern = temp[0].replace(r"\#", "#")
					replace = temp[1].replace(r"\#", "#")
					try:
						dictionaryEntry = SpeechDictEntry(
							pattern,
							replace,
							comment,
							caseSensitive=bool(int(temp[2])),
							type=int(temp[3]),
						)
						self.append(dictionaryEntry)
					except Exception as e:
						log.exception(
							'Dictionary ("%s") entry invalid for "%s" error raised: "%s"'
							% (fileName, line, e),
						)
					comment = ""
				else:
					log.warning("can't parse line '%s'" % line)
		log.debug("%d loaded records." % len(self))
		file.close()
		return

	def save(self, fileName=None):
		if not shouldWriteToDisk():
			log.debugWarning("Not writing dictionary, as shouldWriteToDisk returned False.")
			return
		if not fileName:
			fileName = getattr(self, "fileName", None)
		if not fileName:
			return
		dirName = os.path.dirname(fileName)
		if not os.path.isdir(dirName):
			os.makedirs(dirName)
		file = codecs.open(fileName, "w", "utf_8_sig", errors="replace")
		for entry in self:
			if entry.comment:
				file.write("#%s\r\n" % entry.comment)
			file.write(
				"%s\t%s\t%s\t%s\r\n"
				% (
					entry.pattern.replace("#", r"\#"),
					entry.replacement.replace("#", r"\#"),
					int(entry.caseSensitive),
					entry.type,
				),
			)
		file.close()

	def sub(self, text):
		invalidEntries = []
		for index, entry in enumerate(self):
			try:
				text = entry.sub(text)
			except re.error as exc:
				dictName = self.fileName or "temporary dictionary"
				log.error(f'Invalid dictionary entry {index + 1} in {dictName}: "{entry.pattern}", {exc}')
				invalidEntries.append(index)
			for index in reversed(invalidEntries):
				del self[index]
		return text


def processText(text):
	if not globalVars.speechDictionaryProcessing:
		return text
	for type in dictTypes:
		text = dictionaries[type].sub(text)
	return text
'''

# NVDA 2026.2's builtin.dic, line by line.
BUILTIN_DIC = (
	'#break up words that use a capital letter to denote another word\r\n'
	'([a-z])([A-Z])\t\\1 \\2\t1\t1\r\n'
	'#Break away a word starting with a capital from a fully uppercase word\r\n'
	'([A-Z])([A-Z][a-z])\t\\1 \\2\t1\t1\r\n'
	'#Break words that have numbers at the end\r\n'
	'((?:(?=\\D)\\w)+)(\\d+)\t\\1 \\2\t1\t1\r\n'
)


class EntryType(enum.IntEnum):
	"""NVDA 2026.2's speechDictHandler.types.EntryType: its values (a DisplayStringIntEnum there)."""

	ANYWHERE = 0
	REGEXP = 1
	WORD = 2
	PART_OF_WORD = 3
	START_OF_WORD = 4
	END_OF_WORD = 5
	UNIX = 6


class DictionaryType(str, enum.Enum):
	"""NVDA 2026.2's speechDictHandler.types.DictionaryType: its values (a DisplayStringStrEnum there)."""

	TEMP = "temp"
	VOICE = "voice"
	DEFAULT = "default"
	BUILTIN = "builtin"


#: The regex module, as NVDA 2026.2 uses it, from re.
regex = types.SimpleNamespace(
	compile=re.compile,
	escape=re.escape,
	error=re.error,
	UNICODE=re.UNICODE,
	IGNORECASE=re.IGNORECASE,
	VERSION1=0,
)

_log = logging.getLogger("nvda")
_log.debugWarning = _log.debug


def readText(path: str) -> str:
	with open(path, encoding="utf_8_sig") as stream:
		return stream.read()


def readBytes(path: str) -> bytes:
	with open(path, "rb") as stream:
		return stream.read()


def module(name, **attributes):
	result = types.ModuleType(name)
	for key, value in attributes.items():
		setattr(result, key, value)
	return result


class ImitationNvda:
	"""NVDA with its speech dictionaries from a settings folder, and the focus in one program.

	``speak(text)`` is what NVDA's speech.speech.processText does with the dictionaries: it calls
	``speechDictHandler.processText(text)``, looking the function up in the module each time.
	"""

	version = "2026.2"

	def __init__(self, root):
		self.configDir = os.path.join(root, "nvda")
		self.appDir = os.path.join(root, "NVDA program")
		os.makedirs(os.path.join(self.configDir, "speechDicts"), exist_ok=True)
		os.makedirs(self.appDir, exist_ok=True)
		self.defaultPath = os.path.join(self.configDir, "speechDicts", "default.dic")
		self.voicePath = os.path.join(self.configDir, "speechDicts", "voiceDicts.v1", "eloquence", "eloquence-American English.dic")
		with open(os.path.join(self.appDir, "builtin.dic"), "w", encoding="utf_8_sig", newline="") as stream:
			stream.write(BUILTIN_DIC)
		self.program = "msedge"
		self.globalVars = module("globalVars", speechDictionaryProcessing=True)
		self.api = module("api", getFocusObject=lambda: self._focusObject())
		self.config = module("config", conf=self.conf())
		self._saved = {}
		self._patches = []

	def conf(self):
		return {"speech": {"speechDictionaries": ["default", "voice"]}, "featureFlag": {"speechDictsUseModernRegex": False}}

	def _focusObject(self):
		return types.SimpleNamespace(appModule=types.SimpleNamespace(appName=self.program))

	def modules(self) -> dict:
		namespace = {
			"__name__": "speechDictHandler.types",
			"dataclass": dataclass,
			"field": field,
			"fnmatch": fnmatch,
			"ModuleType": types.ModuleType,
			"os": os,
			"re": re,
			"regex": regex,
			"config": self.config,
			"log": _log,
			"shouldWriteToDisk": lambda: True,
			"EntryType": EntryType,
			"DictionaryType": DictionaryType,
		}
		exec(NVDA_2026_2_TYPES, namespace)
		Definition = namespace["SpeechDictDefinition"]
		# NVDA's VoiceSpeechDictDefinition finds its file from the synthesizer and voice: Eloquence, American English.
		self.dictionaries = [
			Definition(name=DictionaryType.TEMP.value, source=DictionaryType.TEMP, mandatory=True, displayName="Temporary dictionary"),
			Definition(name=DictionaryType.VOICE.value, source=DictionaryType.VOICE, path=self.voicePath, displayName="Voice dictionary"),
			Definition(name=DictionaryType.DEFAULT.value, source=DictionaryType.DEFAULT, path=self.defaultPath, displayName="Default Dictionary"),
			Definition(name=DictionaryType.BUILTIN.value, source=DictionaryType.BUILTIN, path=os.path.join(self.appDir, "builtin.dic"), mandatory=True),
		]
		definitions = module("speechDictHandler.definitions", _speechDictDefinitions=self.dictionaries)
		processNamespace = {"globalVars": self.globalVars, "definitions": definitions}
		exec(NVDA_2026_2_PROCESS_TEXT, processNamespace)
		typesModule = module(
			"speechDictHandler.types",
			**{name: namespace[name] for name in ("SpeechDict", "SpeechDictEntry", "SpeechDictDefinition")},
			EntryType=EntryType,
			DictionaryType=DictionaryType,
		)
		package = module("speechDictHandler", processText=processNamespace["processText"], definitions=definitions, types=typesModule)
		return {
			"speechDictHandler": package,
			"speechDictHandler.types": typesModule,
			"speechDictHandler.definitions": definitions,
		}

	def __enter__(self):
		replaced = dict(self.modules(), globalVars=self.globalVars, api=self.api, config=self.config, logHandler=module("logHandler", log=_log))
		for name in set(replaced) | {"speechDictHandler.types", "speechDictHandler.definitions"}:
			self._saved[name] = sys.modules.get(name)
			if replaced.get(name) is None:
				sys.modules.pop(name, None)
			else:
				sys.modules[name] = replaced[name]
		patch = mock.patch.object(nvdaEnv, "configDir", lambda: self.configDir)
		patch.start()
		self._patches.append(patch)
		appDicts.reload()
		return self

	def __exit__(self, *exc):
		appDicts.unregister()
		for patch in reversed(self._patches):
			patch.stop()
		for name, value in self._saved.items():
			if value is None:
				sys.modules.pop(name, None)
			else:
				sys.modules[name] = value
		appDicts.reload()
		return False

	def speak(self, text: str) -> str:
		return sys.modules["speechDictHandler"].processText(text)

	def reload(self) -> None:
		"""NVDA reads its dictionary files again, as the assistant has it do after a repair."""
		for definition in self.dictionaries:
			if definition.path:
				definition.dictionary.load(definition.path)

	def defaultDictionary(self):
		return self.dictionaries[2].dictionary


class ImitationNvda2026_1(ImitationNvda):
	"""NVDA 2026.1: its dictionaries are speechDictHandler.dictionaries, in the order of dictTypes, with no setting to
	turn one off."""

	version = "2026.1"

	def conf(self):
		return {"speech": {}}

	def modules(self) -> dict:
		package = module("speechDictHandler")
		namespace = vars(package)
		namespace.update({"re": re, "os": os, "codecs": codecs, "log": _log, "shouldWriteToDisk": lambda: True, "globalVars": self.globalVars})
		exec(NVDA_2026_1, namespace)
		# NVDA 2026.1's initialize and loadVoiceDict.
		package.dictionaries = {kind: package.SpeechDict() for kind in package.dictTypes}
		package.dictionaries["default"].load(self.defaultPath)
		package.dictionaries["builtin"].load(os.path.join(self.appDir, "builtin.dic"))
		package.dictionaries["voice"].load(self.voicePath)
		self.package = package
		return {"speechDictHandler": package}

	def reload(self) -> None:
		for kind in ("default", "voice", "builtin"):
			dictionary = self.package.dictionaries[kind]
			dictionary.load(dictionary.fileName)

	def defaultDictionary(self):
		return self.package.dictionaries["default"]


# -- the tester's JAWS -------------------------------------------------------------------------------------------------

#: Rules of Freedom Scientific's own dictionaries (JAWS 2026, SETTINGS\enu), at their lines there.
JAWS_RULES = {
	"Default.JDF": {4: ".Kamala.Comma le.0x09.Eloquence Software.*.0.0.", 84: ".homepage*.home page.0x09.*.*.0.0."},
	"Theophilos.jdf": {40: ".Job.jobe.0x09.*.*.0.0."},
	"Excel.jdf": {1: ".a.eigh.0x09.*.*.0.0."},
	"Outlook.jdf": {1: ".\\133.dot dot dot.0x09.*.*.0.0."},
}
#: JAWS 2026's ConfigNames.ini lines for them: the program each configuration is for.
CONFIG_NAMES = "[ConfigNames]\ntheophil=Theophilos\nExcel=Excel\noutlook=Outlook\n"
#: A rule the user made in NVDA's own Default dictionary dialog.
USER_RULE = "#my own rule\nNVDA\tN V D A\t1\t2\n"
#: The words from the article, and the tester's note.
NOTE = "the word job isn't being spoken right"
ARTICLE = "he deals with a concussion"


def makeJaws(root: str) -> tuple:
	"""A JAWS 2026 with Freedom Scientific's rules above, in ``root``: (installation, index)."""
	jaws = jawsDetect.JawsInstallation(
		version="2026",
		userRoot=os.path.join(root, "user", "2026"),
		sharedRoot=os.path.join(root, "shared", "2026"),
		primaryLanguage="enu",
	)
	shared = os.path.join(jaws.sharedSettingsDir, "enu")
	os.makedirs(shared)
	os.makedirs(os.path.join(jaws.userSettingsDir, "enu"))
	for name, rules in JAWS_RULES.items():
		lines = [rules.get(number, "") for number in range(1, max(rules) + 1)]
		with open(os.path.join(shared, name), "w", encoding="utf-8") as stream:
			stream.write("\n".join(lines) + "\n")
	with open(os.path.join(shared, "ConfigNames.ini"), "w", encoding="utf-8") as stream:
		stream.write(CONFIG_NAMES)
	return jaws, jawsIndex.buildIndex(jaws, "enu")


def programsOf(index) -> dict:
	"""The programs of each application dictionary, as the repair finds them in JAWS's ConfigNames.ini."""
	return {name: migrator.appExecutables(index, name)[0] for name in ("Theophilos", "Excel", "Outlook")}


def migrateAs120(nvda, index) -> None:
	"""What version 1.20 did with JAWS's dictionaries, with JAWS's Eloquence: buildPlan's step, then the migration's.

	Every .jdf, the default one first, went into NVDA's default dictionary, and its rules for JAWS's synthesizer into the
	voice dictionary, through nvdaApply.addDictionaryEntries (the real one, unchanged since).
	"""
	seen = set(dictMap.readDicPatterns(nvda.defaultPath))
	defaultEntries, voiceEntries = [], []
	for indexed in sorted(index.byExtension("jdf", jawsIndex.BOTH), key=lambda f: (f.scope != jawsIndex.USER, os.path.splitext(f.name)[0].lower() != "default")):
		label = ("your " if indexed.scope == jawsIndex.USER else "shared ") + indexed.name
		conversion = dictMap.convertRules(jawsFiles.readJdf(indexed.path), label, 0x409, seen)
		for entry in conversion.entries:
			seen.add(entry.key() + (entry.jawsSynthesizer.lower(),))
			if not entry.jawsSynthesizer:
				defaultEntries.append(entry)
			elif entry.jawsSynthesizer.lower() == "eloquence software":
				voiceEntries.append(entry)
	# The migration adds the voice's rules first, then the default dictionary's.
	nvdaApply.addDictionaryEntries("voice", voiceEntries)
	nvdaApply.addDictionaryEntries("default", defaultEntries)


class _Tester:
	"""NVDA with the tester's dictionaries as version 1.20 left them."""

	Nvda = ImitationNvda

	def setUp(self):
		self.root = tempfile.mkdtemp(prefix="jawsMigrator-v121-")
		self.jaws, self.index = makeJaws(os.path.join(self.root, "jaws"))
		self.nvda = self.Nvda(self.root)
		with open(self.nvda.defaultPath, "w", encoding="utf_8_sig") as stream:
			stream.write(USER_RULE)
		self.nvda.__enter__()
		migrateAs120(self.nvda, self.index)
		self.before = readText(self.nvda.defaultPath)

	def tearDown(self):
		self.nvda.__exit__(None, None, None)
		shutil.rmtree(self.root, ignore_errors=True)

	def repair(self):
		result = dictRepair.repairDictionaries(self.nvda.configDir, programs=programsOf(self.index))
		# As the assistant does after the repair: NVDA reads its files again, and the assistant its own.
		self.nvda.reload()
		appDicts.register()
		return result

	def speakIn(self, program: str, text: str) -> str:
		self.nvda.program = program
		return self.nvda.speak(text)


class TesterWithNvda2026_2(_Tester, unittest.TestCase):
	def test_version_1_20_said_jobe_everywhere(self):
		# As the tester heard it in Edge: Theophilos's rule, and Excel's.
		self.assertIn("From JAWS shared Theophilos.jdf, line 40", self.before)
		self.assertEqual(self.speakIn("msedge", NOTE), "the word jobe isn't being spoken right")
		self.assertEqual(self.speakIn("msedge", ARTICLE), "he deals with eigh concussion")
		self.assertEqual(self.speakIn("msedge", "Bears \u2026 Chicago"), "Bears dot dot dot Chicago")

	def test_the_log_names_the_rule(self):
		# The next log says which rule changed "job", even before the repair.
		appDicts.register()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.speakIn("msedge", NOTE)
		lines = [line for line in logged.output if "speech dictionary rules change" in line]
		self.assertEqual(len(lines), 1, logged.output)
		self.assertIn(f"{NOTE!r}", lines[0])
		self.assertIn("'Job' -> 'jobe' (default dictionary: From JAWS shared Theophilos.jdf, line 40)", lines[0])

	def test_no_log_without_debug(self):
		appDicts.register()
		with self.assertLogs("nvda", level="INFO") as logged:
			_log.info("marker")
			self.speakIn("msedge", NOTE)
		self.assertEqual(logged.output, ["INFO:nvda:marker"])

	def test_repair_moves_each_application_rule_to_its_program(self):
		result = self.repair()
		self.assertEqual(result.moved, {"Theophilos": 1, "Excel": 1, "Outlook": 1})
		self.assertEqual(result.failed, [])
		self.assertEqual(self.speakIn("msedge", NOTE), NOTE)
		self.assertEqual(self.speakIn("msedge", ARTICLE), ARTICLE)
		self.assertEqual(self.speakIn("msedge", "Bears \u2026 Chicago"), "Bears \u2026 Chicago")
		# As JAWS: each rule in its own program.
		self.assertEqual(self.speakIn("theophil", "the Book of Job"), "the Book of jobe")
		self.assertEqual(self.speakIn("excel", "column a"), "column eigh")
		self.assertEqual(self.speakIn("outlook", "Bears \u2026 Chicago"), "Bears dot dot dot Chicago")
		self.assertEqual(self.speakIn("excel", NOTE), NOTE)
		# JAWS's default dictionary stays everywhere, and so does the user's own rule.
		for program in ("msedge", "theophil", "excel"):
			self.assertEqual(self.speakIn(program, "Homepage of NVDA"), "home page of N V D A")

	def test_repair_keeps_everything_else(self):
		self.repair()
		after = readText(self.nvda.defaultPath)
		self.assertNotIn(".jdf, line", after.replace("Default.JDF, line", ""))
		self.assertTrue(after.startswith(USER_RULE), after)
		entries = [(entry.pattern, entry.replacement, entry.comment) for entry in self.nvda.defaultDictionary()]
		self.assertEqual(
			entries,
			[("NVDA", "N V D A", "my own rule"), (r"\bhomepage", "home page", "From JAWS shared Default.JDF, line 84 (root word homepage*)")],
		)
		# The voice dictionary keeps JAWS's default rule for Eloquence.
		voice = readText(self.nvda.voicePath)
		self.assertIn("Kamala\tComma le\t0\t2", voice)

	def test_new_files_are_read_by_nvda(self):
		result = self.repair()
		theophilos = appDicts.path("Theophilos", self.nvda.configDir)
		self.assertIn(theophilos, result.applicationFiles)
		self.assertEqual(appDicts.readPrograms(theophilos), ["theophil"])
		dictionary = sys.modules["speechDictHandler"].types.SpeechDict()
		dictionary.load(theophilos)
		self.assertEqual(
			[(entry.pattern, entry.replacement, entry.caseSensitive, int(entry.type), entry.comment) for entry in dictionary],
			[("Job", "jobe", False, 2, "From JAWS shared Theophilos.jdf, line 40")],
		)
		text = readText(theophilos)
		self.assertTrue(text.startswith("#JAWS's dictionary for Theophilos. JAWS uses these rules only in Theophilos"), text)

	def test_repair_runs_once(self):
		self.assertTrue(dictRepair.needsRepair(self.nvda.configDir))
		self.repair()
		self.assertFalse(dictRepair.needsRepair(self.nvda.configDir))
		files = {name: readBytes(os.path.join(root, name)) for root, _dirs, names in os.walk(self.nvda.configDir) for name in names}
		again = dictRepair.repairDictionaries(self.nvda.configDir, programs=programsOf(self.index))
		self.assertEqual((again.files, again.moved, again.rewritten), ([], {}, 0))
		self.assertEqual(files, {name: readBytes(os.path.join(root, name)) for root, _dirs, names in os.walk(self.nvda.configDir) for name in names})

	def test_application_rule_comes_before_the_default_dictionary(self):
		# As in JAWS, the application's rule wins over a default rule for the same word.
		self.repair()
		with open(self.nvda.defaultPath, "a", encoding="utf-8") as stream:
			stream.write("#another rule of the user's\nJob\twork\t0\t2\n")
		self.nvda.reload()
		self.assertEqual(self.speakIn("theophil", "the Book of Job"), "the Book of jobe")
		self.assertEqual(self.speakIn("msedge", NOTE), "the word work isn't being spoken right")

	def test_not_when_nvda_dictionaries_are_off(self):
		self.repair()
		self.nvda.globalVars.speechDictionaryProcessing = False
		self.assertEqual(self.speakIn("theophil", "the Book of Job"), "the Book of Job")
		self.nvda.globalVars.speechDictionaryProcessing = True
		self.nvda.config.conf["speech"]["speechDictionaries"] = ["voice"]
		self.assertEqual(self.speakIn("theophil", "the Book of Job"), "the Book of Job")

	def test_moved_message(self):
		result = self.repair()
		self.assertEqual(
			dictRepair.movedMessage(result),
			"JAWS Migration Assistant moved 3 speech dictionary rules from JAWS's dictionaries for Excel, Outlook and Theophilos "
			"out of NVDA's default dictionary. As in JAWS, they now change speech only in those programs.",
		)


class TesterWithNvda2026_1(_Tester, unittest.TestCase):
	Nvda = ImitationNvda2026_1

	def test_version_1_20_said_jobe_everywhere(self):
		self.assertEqual(self.speakIn("msedge", NOTE), "the word jobe isn't being spoken right")

	def test_repair_moves_each_application_rule_to_its_program(self):
		result = self.repair()
		self.assertEqual(result.moved, {"Theophilos": 1, "Excel": 1, "Outlook": 1})
		self.assertEqual(self.speakIn("msedge", NOTE), NOTE)
		self.assertEqual(self.speakIn("msedge", ARTICLE), ARTICLE)
		self.assertEqual(self.speakIn("theophil", "the Book of Job"), "the Book of jobe")
		self.assertEqual(self.speakIn("excel", "column a"), "column eigh")
		self.assertEqual(self.speakIn("msedge", "Homepage of NVDA"), "home page of N V D A")

	def test_the_log_names_the_rule(self):
		appDicts.register()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.speakIn("msedge", NOTE)
		self.assertTrue(any("'Job' -> 'jobe' (default dictionary: From JAWS shared Theophilos.jdf, line 40)" in line for line in logged.output), logged.output)


# -- a migration -------------------------------------------------------------------------------------------------------


class MigrationTests(unittest.TestCase):
	def setUp(self):
		self.root = tempfile.mkdtemp(prefix="jawsMigrator-v121-")
		self.jaws, self.index = makeJaws(os.path.join(self.root, "jaws"))
		self.configDir = os.path.join(self.root, "nvda")
		os.makedirs(self.configDir)

	def tearDown(self):
		shutil.rmtree(self.root, ignore_errors=True)

	def plan(self, index=None, jaws=None):
		options = migrator.MigrationOptions(jaws=jaws or self.jaws, language="enu", scope=jawsIndex.BOTH, sharedDictionaries=True)
		return migrator.buildPlan(options, index or self.index, systemCheck.SystemFacts(configDir=self.configDir), inNvda=False)

	def test_application_rules_are_for_their_programs_only(self):
		plan = self.plan()
		byName = {dictionaryPlan.source.name: dictionaryPlan for dictionaryPlan in plan.dictionaries}
		theophilos = byName["Theophilos.jdf"]
		self.assertEqual((theophilos.configName, theophilos.programs), ("Theophilos", ["theophil"]))
		self.assertEqual([(entry.pattern, entry.replacement) for entry in theophilos.appEntries], [("Job", "jobe")])
		self.assertEqual((theophilos.defaultEntries, theophilos.voiceEntries), ([], []))
		self.assertEqual([(entry.pattern, entry.replacement) for entry in byName["Excel.jdf"].appEntries], [("a", "eigh")])
		self.assertEqual(byName["Excel.jdf"].programs, ["excel"])
		default = byName["Default.JDF"]
		self.assertEqual(default.configName, "")
		self.assertEqual([(entry.pattern, entry.replacement) for entry in default.defaultEntries], [(r"\bhomepage", "home page")])
		self.assertEqual(sum(dictionaryPlan.ruleCount() for dictionaryPlan in plan.chosenDictionaries()), 4)

	def test_same_word_in_the_default_and_an_application_dictionary(self):
		# Each dictionary keeps its own rule for the word, as JAWS keeps both.
		with open(os.path.join(self.jaws.sharedSettingsDir, "enu", "Default.JDF"), "a", encoding="utf-8") as stream:
			stream.write(".Job.work.0x09.*.*.0.0.\n")
		index = jawsIndex.buildIndex(self.jaws, "enu")
		byName = {dictionaryPlan.source.name: dictionaryPlan for dictionaryPlan in self.plan(index).dictionaries}
		self.assertIn(("Job", "work"), [(entry.pattern, entry.replacement) for entry in byName["Default.JDF"].defaultEntries])
		self.assertEqual([(entry.pattern, entry.replacement) for entry in byName["Theophilos.jdf"].appEntries], [("Job", "jobe")])

	def test_rules_already_in_the_program_file_are_not_added_again(self):
		plan = self.plan()
		theophilos = next(d for d in plan.dictionaries if d.configName == "Theophilos")
		self.assertEqual(appDicts.writeRules("Theophilos", theophilos.programs, theophilos.appEntries, self.configDir), 1)
		again = next(d for d in self.plan().dictionaries if d.configName == "Theophilos")
		self.assertEqual(again.appEntries, [])
		self.assertEqual([skipped.reason for skipped in again.conversion.skipped], ["NVDA's dictionary already has this word."])

	def test_application_nvda_does_not_know(self):
		# JAWS's Windows OS configuration is for parts of Windows (shell32...), which NVDA can't tell apart.
		shared = os.path.join(self.jaws.sharedSettingsDir, "enu")
		with open(os.path.join(shared, "Windows OS.jdf"), "w", encoding="utf-8") as stream:
			stream.write(".file(s).files.0x09.*.*.0.0.\n")
		with open(os.path.join(shared, "ConfigNames.ini"), "a", encoding="utf-8") as stream:
			stream.write("shell32=Windows OS\n")
		index = jawsIndex.buildIndex(self.jaws, "enu")
		windows = next(d for d in self.plan(index).dictionaries if d.configName == "Windows OS")
		self.assertEqual((windows.programs, windows.appEntries), ([], []))
		self.assertEqual(len(windows.conversion.skipped), 1)
		self.assertTrue(windows.conversion.skipped[0].reason.startswith("The rule is for Windows OS only, where NVDA can't use it: "), windows.conversion.skipped[0].reason)

	@unittest.skipUnless(
		os.path.isfile(os.path.join(jawsDetect.programDataFolder(), "Freedom Scientific", "JAWS", "2026", "SETTINGS", "enu", "Theophilos.jdf")),
		"needs JAWS 2026's own files",
	)
	def test_jaws_2026_itself(self):
		jaws = next(j for j in jawsDetect.findJawsInstallations() if j.version == "2026")
		index = jawsIndex.buildIndex(jaws, "enu")
		byName = {d.source.name.lower(): d for d in self.plan(index, jaws).dictionaries if d.source.scope == jawsIndex.SHARED}
		theophilos = byName["theophilos.jdf"]
		self.assertEqual(theophilos.programs, ["theophil"])
		job = next(entry for entry in theophilos.appEntries if entry.pattern == "Job")
		self.assertEqual((job.replacement, job.caseSensitive, job.type, job.comment), ("jobe", False, dictMap.TYPE_WORD, "From JAWS shared Theophilos.jdf, line 40"))
		self.assertEqual(byName["excel.jdf"].programs, ["excel"])
		self.assertIn(("a", "eigh"), [(entry.pattern, entry.replacement) for entry in byName["excel.jdf"].appEntries])
		for dictionaryPlan in byName.values():
			if dictionaryPlan.configName:
				self.assertEqual(dictionaryPlan.defaultEntries + dictionaryPlan.voiceEntries, [], dictionaryPlan.label)
		self.assertEqual(dictRepair.programsFor(["Theophilos", "Excel"]), {"Theophilos": ["theophil"], "Excel": ["excel"]})


# -- the files and the hook --------------------------------------------------------------------------------------------


class FileTests(unittest.TestCase):
	def setUp(self):
		self.configDir = tempfile.mkdtemp(prefix="jawsMigrator-v121-")

	def tearDown(self):
		shutil.rmtree(self.configDir, ignore_errors=True)

	def entry(self, pattern, replacement, comment="From JAWS shared Outlook.jdf, line 1"):
		return dictMap.DictEntry(pattern, replacement, False, dictMap.TYPE_WORD, comment)

	def test_source_configuration(self):
		cases = {
			"From JAWS shared Theophilos.jdf, line 40": "Theophilos",
			"From JAWS your Default.JDF, line 3": "Default",
			"From JAWS shared Teams.JdF, line 2 (whole word Ctrl,)": "Teams",
			"From JAWS your youtube.com.jdf, line 1": "youtube.com",
			"From JAWS shared Internet Explorer.jdf, line 9 (root word frame*)": "Internet Explorer",
			"my own rule": None,
			"": None,
		}
		for comment, expected in cases.items():
			self.assertEqual(appDicts.sourceConfiguration(comment), expected, comment)
		self.assertTrue(appDicts.isApplicationRule("From JAWS shared Theophilos.jdf, line 40"))
		self.assertFalse(appDicts.isApplicationRule("From JAWS your Default.JDF, line 3"))
		self.assertFalse(appDicts.isApplicationRule("my own rule"))

	def test_programs_are_added_and_rules_kept_once(self):
		self.assertEqual(appDicts.writeRules("Outlook", ["outlook"], [self.entry("memo", "note")], self.configDir), 1)
		self.assertEqual(appDicts.writeRules("Outlook", ["mapir", "outlook"], [self.entry("memo", "note"), self.entry("fwd", "forward")], self.configDir), 1)
		path = appDicts.path("Outlook", self.configDir)
		self.assertEqual(appDicts.readPrograms(path), ["outlook", "mapir"])
		text = readText(path)
		self.assertEqual(text.count("memo\tnote"), 1)
		self.assertEqual(text.count("#Programs:"), 1)
		with ImitationNvda(self.configDir):
			self.assertEqual(sorted(appDicts.load(self.configDir)), ["mapir", "outlook"])

	def test_a_file_for_no_program_is_used_nowhere(self):
		appDicts.writeRules("Windows OS", [], [self.entry("file(s)", "files")], self.configDir)
		path = appDicts.path("Windows OS", self.configDir)
		self.assertEqual(appDicts.readPrograms(path), [])
		self.assertIn("NVDA does not know as a program, so NVDA uses them nowhere", readText(path))
		with ImitationNvda(self.configDir):
			self.assertEqual(appDicts.load(self.configDir), {})

	def test_hook_in_place_once_and_taken_out(self):
		with ImitationNvda(self.configDir) as nvda:
			package = sys.modules["speechDictHandler"]
			original = package.processText
			self.assertTrue(appDicts.register())
			installed = package.processText
			self.assertIsNot(installed, original)
			self.assertTrue(appDicts.register())
			self.assertIs(package.processText, installed)
			self.assertTrue(appDicts.isRegistered())
			self.assertEqual(nvda.speak("the Book of Job"), "the Book of Job")
			appDicts.unregister()
			self.assertIs(package.processText, original)
			self.assertFalse(appDicts.isRegistered())

	def test_another_add_on_wrapping_it(self):
		import functools

		with ImitationNvda(self.configDir):
			package = sys.modules["speechDictHandler"]
			appDicts.register()
			ours = package.processText

			@functools.wraps(ours)
			def theirs(text):
				return ours(text)

			package.processText = theirs
			self.assertTrue(appDicts.register())
			self.assertIs(package.processText, theirs)
			appDicts.unregister()
			# Their wrapper stays: taking ours out from under it would drop theirs.
			self.assertIs(package.processText, theirs)


if __name__ == "__main__":
	unittest.main()
