# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""JAWS synthesizers and voice profiles, and their nearest NVDA equivalents.

A JAWS voice profile (``.vpf``) has one section per language and context, such as
``[enu-Global]`` or ``[enu-PCCursor]``, holding the rate, pitch, volume,
punctuation level and person (voice name) for that context. Values are in the
JAWS units of the profile's synthesizer: Eloquence rate runs 0 to 148, SAPI 5
uses 0 to 20, DECtalk uses words per minute, and so on. JAWS shows each one as a
percentage of that range (Eloquence rate 95 shows as 64%), and NVDA's settings
are percentages, so the percentage carries over: JAWS 64% becomes NVDA 64%. Where
a synthesizer's JAWS range isn't known, the value is not migrated at all.

The user's copy of a profile only holds what they changed; it is layered over the
shared copy, as JAWS does. Nothing in this module needs NVDA.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from . import jawsFiles

#: JAWS voice contexts, in the order JAWS lists them.
CONTEXTS = ("Global", "PCCursor", "JAWSCursor", "Keyboard", "MenuAndDialog", "Message")

CONTEXT_LABELS = {
	"Global": "Global (everything not listed below)",
	"PCCursor": "PC cursor",
	"JAWSCursor": "JAWS cursor",
	"Keyboard": "Keyboard (typed characters)",
	"MenuAndDialog": "Menus and dialogs",
	"Message": "JAWS messages",
}

#: How JAWS voice contexts become ClassicSpeech Voice Profile categories.
CLASSIC_SPEECH_CONTEXTS = {
	"focusNavigation": "PCCursor",
	"reviewObjectNavigation": "JAWSCursor",
	# The JAWS cursor follows the mouse, so mouse speech takes the JAWS cursor voice.
	"mouse": "JAWSCursor",
	"keyboardEntry": "Keyboard",
	"systemNotifications": "Message",
}


@dataclass(frozen=True)
class ParameterRange:
	"""One JAWS synthesizer setting's range, in the synthesizer's own units, as JAWS stores it.

	JAWS shows the value as a percentage of this range; that percentage becomes NVDA's.
	"""

	minimum: float
	maximum: float
	#: JAWS's factory default, for reports.
	default: float = 0

	def toPercent(self, value) -> int | None:
		if value is None or self.maximum <= self.minimum:
			return None
		value = max(self.minimum, min(self.maximum, float(value)))
		return int(round((value - self.minimum) * 100.0 / (self.maximum - self.minimum)))


#: A JAWS setting that is already a percentage.
PERCENT = ParameterRange(0, 100, 50)


@dataclass(frozen=True)
class JawsSynthInfo:
	"""What the assistant knows about one JAWS synthesizer driver."""

	#: Short family name used to look for an NVDA equivalent.
	family: str
	label: str
	#: JAWS ranges; None where the range isn't known, so the setting is not migrated.
	rate: ParameterRange | None = None
	pitch: ParameterRange | None = None
	volume: ParameterRange | None = None
	#: Words to look for in NVDA synthesizer names and descriptions.
	nvdaDriverWords: tuple = ()
	#: Words to look for in SAPI 5 and OneCore voice names and vendors.
	voiceWords: tuple = ()
	#: NVDA drivers that speak the same voices directly.
	nvdaDrivers: tuple = ()


_ELOQUENCE_WORDS = ("eloquence", "ibmeci", "ibmtts", "ibm tts", "eci", "viavoice", "via voice", "outloud", "eti-eloquence")
_SAPI_RATE = ParameterRange(0, 20, 10)

JAWS_SYNTHS = {
	"eloq": JawsSynthInfo(
		"eloquence",
		"Eloquence",
		# JAWS 2026 shows Eloquence rate 95 as 64 percent, and its default 57; pitch and volume are Eloquence's own 0 to 100.
		rate=ParameterRange(0, 148, 57),
		pitch=ParameterRange(0, 100, 65),
		volume=ParameterRange(0, 100, 100),
		nvdaDriverWords=_ELOQUENCE_WORDS,
		voiceWords=("eloquence", "eti", "viavoice", "via voice", "ibm", "outloud"),
		nvdaDrivers=("ibmeci", "eloquence", "eci", "ttseloquence"),
	),
	# JAWS "SAPI 5X" loads 32-bit voices; NVDA 2026 reaches those through its sapi5_32 driver.
	"sapi 5x": JawsSynthInfo("sapi5", "SAPI 5 (32-bit)", rate=_SAPI_RATE, pitch=_SAPI_RATE, volume=PERCENT, nvdaDrivers=("sapi5_32", "sapi5")),
	"sapi 5x 64": JawsSynthInfo("sapi5", "SAPI 5 64-bit", rate=_SAPI_RATE, pitch=_SAPI_RATE, volume=PERCENT, nvdaDrivers=("sapi5", "sapi5_32")),
	"msmobile": JawsSynthInfo("onecore", "Microsoft Mobile (OneCore)", rate=_SAPI_RATE, pitch=_SAPI_RATE, volume=PERCENT, nvdaDrivers=("oneCore",)),
	"vocalizerexpressive": JawsSynthInfo(
		"vocalizer",
		"Vocalizer Expressive",
		rate=ParameterRange(50, 400, 100),
		volume=ParameterRange(0, 100, 70),
		nvdaDriverWords=("vocalizer",),
		voiceWords=("vocalizer", "nuance", "cerence"),
		nvdaDrivers=("vocalizer_expressive", "vocalizer_expressive2", "vocalizer"),
	),
	"vocalizer": JawsSynthInfo(
		"vocalizer",
		"Vocalizer Direct",
		rate=ParameterRange(50, 400, 100),
		volume=ParameterRange(0, 100, 70),
		nvdaDriverWords=("vocalizer",),
		voiceWords=("vocalizer", "nuance", "cerence"),
		nvdaDrivers=("vocalizer_expressive", "vocalizer"),
	),
	"realspeak": JawsSynthInfo(
		"realspeak",
		"RealSpeak Solo Direct",
		rate=ParameterRange(0, 100, 50),
		volume=ParameterRange(0, 100, 75),
		nvdaDriverWords=("realspeak", "vocalizer"),
		voiceWords=("realspeak", "scansoft", "nuance"),
	),
	"dtsoft": JawsSynthInfo(
		"dectalk",
		"DECtalk Access32 Software",
		rate=ParameterRange(75, 600, 250),
		pitch=ParameterRange(50, 350, 122),
		volume=ParameterRange(0, 100, 77),
		nvdaDriverWords=("dectalk",),
		voiceWords=("dectalk",),
		nvdaDrivers=("dectalk",),
	),
	"keynote": JawsSynthInfo(
		"keynote",
		"Keynote Gold / BrailleNote",
		rate=ParameterRange(0, 400, 200),
		pitch=ParameterRange(0, 255, 76),
		volume=ParameterRange(0, 255, 255),
		nvdaDriverWords=("bestspeech", "keynote", "bst"),
		voiceWords=("bestspeech", "keynote", "bst"),
		nvdaDrivers=("bestspeech",),
	),
	"jsdbltlk": JawsSynthInfo(
		"doubletalk",
		"DoubleTalk LT / LiteTalk",
		rate=ParameterRange(0, 9, 6),
		pitch=ParameterRange(0, 99, 50),
		volume=ParameterRange(0, 9, 6),
		nvdaDriverWords=("doubletalk",),
		voiceWords=("doubletalk",),
	),
	"accentsa": JawsSynthInfo(
		"accent",
		"Accent",
		rate=ParameterRange(0, 9, 5),
		pitch=ParameterRange(0, 9, 5),
		volume=ParameterRange(0, 9, 9),
		nvdaDriverWords=("accent",),
	),
	"apollo2": JawsSynthInfo(
		"apollo",
		"Apollo 2",
		rate=ParameterRange(0, 9, 5),
		pitch=ParameterRange(0, 15, 8),
		volume=ParameterRange(0, 15, 9),
		nvdaDriverWords=("apollo",),
	),
	"bns": JawsSynthInfo(
		"bns",
		"Braille 'n Speak",
		rate=ParameterRange(0, 26, 13),
		pitch=ParameterRange(0, 50, 25),
		volume=ParameterRange(0, 9, 5),
		nvdaDriverWords=("braille 'n speak", "bns"),
	),
	"info37am": JawsSynthInfo("infovox", "Infovox", nvdaDriverWords=("infovox",), voiceWords=("infovox",)),
	"dtalker": JawsSynthInfo(
		"dtalker",
		"DTalker",
		rate=ParameterRange(0, 14, 7),
		pitch=ParameterRange(0, 6, 3),
		nvdaDriverWords=("dtalker",),
		voiceWords=("dtalker", "create system"),
	),
}
for _name in ("dte", "jsdtu", "jsdtu64"):
	JAWS_SYNTHS[_name] = JAWS_SYNTHS["dtsoft"]
for _name in ("jsttalk", "jsttusb", "jsttu64"):
	JAWS_SYNTHS[_name] = JawsSynthInfo(
		"tripletalk",
		"Triple Talk",
		rate=ParameterRange(0, 9, 6),
		pitch=ParameterRange(0, 99, 50),
		volume=ParameterRange(0, 9, 6),
		nvdaDriverWords=("tripletalk", "triple talk"),
	)
for _name in ("vwvt", "vwvt-e"):
	JAWS_SYNTHS[_name] = JawsSynthInfo(
		"voiceware",
		"VoiceText",
		rate=ParameterRange(50, 400, 100),
		pitch=ParameterRange(50, 200, 100),
		nvdaDriverWords=("voicetext", "voiceware"),
		voiceWords=("voicetext", "voiceware"),
	)
JAWS_SYNTHS["profivox"] = JawsSynthInfo("profivox", "Profivox", nvdaDriverWords=("profivox",), voiceWords=("profivox",))


def synthInfo(shortName: str) -> JawsSynthInfo:
	"""What is known about a JAWS synthesizer by its short name (``eloq``, ``SAPI 5X``...)."""
	key = (shortName or "").strip().lower()
	if key in JAWS_SYNTHS:
		return JAWS_SYNTHS[key]
	return JawsSynthInfo(key or "unknown", shortName or "Unknown synthesizer", nvdaDriverWords=(key,) if key else ())


# -- JAWS synthesizer list ----------------------------------------------------------


@dataclass
class JawsSynth:
	"""A synthesizer JAWS is set up to use, from jfw.ini."""

	slot: str  # "Synth1"
	shortName: str  # "eloq"
	longName: str  # "Eloquence Software"
	driver: str  # "eloq"
	remoteOnly: bool = False

	@property
	def info(self) -> JawsSynthInfo:
		return synthInfo(self.shortName)


def readJawsSynths(jfwIni: jawsFiles.IniFile | None) -> list[JawsSynth]:
	"""Synthesizers listed in jfw.ini, local ones first, then those only for remote sessions."""
	result = []
	if jfwIni is None:
		return result
	for sectionName, remote in (("Synthesizers", False), ("Remote Access Synthesizers", True)):
		section = jfwIni.section(sectionName)
		if section is None:
			continue
		slots = sorted(
			{m.group(1) for key in section.keys() if (m := re.match(r"(?i)^(synth\d+)name$", key))},
			key=lambda slot: int(re.sub(r"\D", "", slot) or 0),
		)
		for slot in slots:
			shortName = section.get(slot + "Name", "")
			if not shortName:
				continue
			if any(existing.shortName.lower() == shortName.lower() for existing in result):
				continue
			result.append(
				JawsSynth(
					slot=slot,
					shortName=shortName,
					longName=section.get(slot + "LongName", shortName),
					driver=section.get(slot + "Driver", ""),
					remoteOnly=remote,
				),
			)
	return result


def activeJawsSynth(synths: list[JawsSynth], jfwIni: jawsFiles.IniFile | None, synthesizerOption: str | None) -> JawsSynth | None:
	"""The synthesizer named by the ``Synthesizer=Synth1`` option of default.jcf."""
	slot = (synthesizerOption or "").strip()
	if jfwIni is not None and slot:
		section = jfwIni.section("Synthesizers")
		shortName = section.get(slot + "Name") if section else None
		if shortName:
			for synth in synths:
				if synth.shortName.lower() == shortName.lower():
					return synth
	local = [synth for synth in synths if not synth.remoteOnly]
	return local[0] if local else None


# -- voice profiles -------------------------------------------------------------------


@dataclass
class VoiceContext:
	language: str
	context: str
	rate: int | None = None
	pitch: int | None = None
	volume: int | None = None
	punctuation: int | None = None
	voiceName: str = ""
	synthLanguage: str = ""
	spellRateDelta: int | None = None
	upperCasePitchDelta: int | None = None
	parent: str = ""

	def describe(self) -> str:
		parts = []
		if self.voiceName:
			parts.append(f"voice {self.voiceName}")
		for label, value in (("rate", self.rate), ("pitch", self.pitch), ("volume", self.volume)):
			if value is not None:
				parts.append(f"{label} {value}")
		if self.punctuation is not None:
			parts.append(f"punctuation {PUNCTUATION_NAMES.get(self.punctuation, self.punctuation)}")
		return ", ".join(parts) or "JAWS defaults"


PUNCTUATION_NAMES = {0: "none", 1: "some", 2: "most", 3: "all"}
#: JAWS punctuation level -> NVDA symbol level (characterProcessing.SymbolLevel).
PUNCTUATION_TO_SYMBOL_LEVEL = {0: 0, 1: 100, 2: 200, 3: 300}


@dataclass
class VoiceProfile:
	name: str
	primarySynthesizer: str = ""
	primaryLanguage: str = "*"
	#: Merged sections, shared first then the user's changes.
	ini: jawsFiles.IniFile = field(default_factory=jawsFiles.IniFile)
	sources: list = field(default_factory=list)

	@property
	def synth(self) -> JawsSynthInfo:
		return synthInfo(self.primarySynthesizer)

	def languages(self) -> list[str]:
		found = []
		for name in self.ini.sectionNames():
			match = re.match(r"^([A-Za-z]{3})-(\w+)$", name)
			if match and match.group(2) in CONTEXTS and match.group(1).lower() not in found:
				found.append(match.group(1).lower())
		return found

	def context(self, language: str, context: str) -> VoiceContext:
		"""The settings for one context, with values it doesn't set taken from its parent (normally Global)."""
		chain = []
		name = context
		seen = set()
		while name and name.lower() not in seen and name.lower() != "none":
			seen.add(name.lower())
			section = self.ini.section(f"{language}-{name}")
			if section is None:
				break
			chain.append(section)
			name = section.get("Parent", "")
			if not name and context != "Global" and name != "Global":
				name = "Global"
		result = VoiceContext(language=language, context=context)
		for section in reversed(chain):
			for attribute, key in (
				("rate", "Rate"),
				("pitch", "Pitch"),
				("volume", "Volume"),
				("punctuation", "Punctuation"),
				("spellRateDelta", "SpellRateDelta"),
				("upperCasePitchDelta", "UpperCasePitchDelta"),
			):
				value = section.getInt(key)
				if value is not None:
					setattr(result, attribute, value)
			for attribute, key in (("voiceName", "VoiceName"), ("synthLanguage", "SynthLangString"), ("parent", "Parent")):
				value = section.get(key)
				if value:
					setattr(result, attribute, value.strip())
		return result

	def voiceAliases(self, language: str) -> dict:
		section = self.ini.section(f"{language}-Voice Aliases")
		return dict(section.items()) if section else {}

	def hasContext(self, language: str, context: str) -> bool:
		return self.ini.section(f"{language}-{context}") is not None


def loadVoiceProfile(name: str, sharedPath: str | None, userPath: str | None) -> VoiceProfile:
	"""Load a voice profile, layering the user's copy over the shared copy."""
	files = []
	sources = []
	for path in (sharedPath, userPath):
		if path and os.path.isfile(path):
			try:
				files.append(jawsFiles.readIni(path))
				sources.append(path)
			except OSError:
				continue
	merged = jawsFiles.mergeIni(*files)
	profile = VoiceProfile(name=name, ini=merged, sources=sources)
	profile.primarySynthesizer = merged.get("Options", "PrimarySynthesizer", "") or ""
	profile.primaryLanguage = merged.get("Options", "PrimaryLanguage", "*") or "*"
	return profile


def findVoiceProfileFiles(folders: list[str]) -> dict:
	"""``{lower-case profile name: path}`` for every ``.vpf`` in ``folders``; later folders win."""
	found = {}
	for folder in folders:
		try:
			names = os.listdir(folder)
		except OSError:
			continue
		for name in names:
			if name.lower().endswith(".vpf"):
				found[os.path.splitext(name)[0].lower()] = os.path.join(folder, name)
	return found


def parseVoiceAlias(value: str) -> list[dict]:
	"""Read a JAWS voice alias such as ``Samantha Premium High|0|0;*|15%|0``.

	Each ``;``-separated group is ``person|pitch|rate``. JAWS uses the first group whose
	person the synthesizer has, so later groups are fallbacks; ``*`` means the current
	voice, which is always available. Pitch and rate are changes from the current voice,
	written as a percentage (``15%``) or in the synthesizer's own units.
	Returns the groups in order as ``{"person": str, "pitch": (value, isPercent), "rate": (value, isPercent)}``.
	"""
	groups = []
	for group in (value or "").split(";"):
		if not group.strip():
			continue
		fields = group.split("|")
		parsed = {"person": fields[0].strip() or "*"}
		for index, name in ((1, "pitch"), (2, "rate")):
			raw = fields[index].strip() if len(fields) > index else "0"
			isPercent = raw.endswith("%")
			try:
				number = float(raw.rstrip("%").strip() or 0)
			except ValueError:
				number = 0.0
			parsed[name] = (number, isPercent)
		groups.append(parsed)
	if not groups:
		groups.append({"person": "*", "pitch": (0.0, False), "rate": (0.0, False)})
	return groups


def aliasIsNeutral(value: str) -> bool:
	"""True when an alias keeps the current voice.

	Only an alias's person carries over into ClassicSpeech (see classicSpeechWriter), so an
	alias that only changes pitch or rate (``*|20%|0``) changes nothing there.
	"""
	return parseVoiceAlias(value)[0]["person"] == "*"


def aliasChanges(group: dict) -> str:
	"""The pitch and rate changes of one alias group, as text, such as ``pitch +5%``."""
	parts = []
	for name in ("pitch", "rate"):
		amount, isPercent = group[name]
		if amount:
			parts.append(f"{name} {amount:+g}{'%' if isPercent else ''}")
	return ", ".join(parts)


#: JAWS Eloquence person names that the NVDA drivers spell differently.
PERSON_SYNONYMS = {
	"shelly": ("shelley",),
}


# -- NVDA equivalents -----------------------------------------------------------------


@dataclass
class NvdaVoiceOption:
	"""An NVDA synthesizer (and possibly a voice in it) that can stand in for a JAWS synthesizer."""

	driver: str
	driverDescription: str
	voiceName: str = ""
	voiceId: str = ""
	reason: str = ""
	score: int = 0

	@property
	def label(self) -> str:
		text = self.driverDescription or self.driver
		if self.voiceName:
			text += f": {self.voiceName}"
		return text


def _matchesAny(text: str, words) -> bool:
	lowered = (text or "").lower()
	for word in words:
		word = word.lower()
		if len(word) <= 3:
			if re.search(r"(^|[^a-z])" + re.escape(word) + r"([^a-z]|$)", lowered):
				return True
		elif word in lowered:
			return True
	return False


def findNvdaEquivalents(
	jawsSynthName: str,
	jawsVoiceName: str,
	nvdaSynths: list[tuple[str, str]],
	sapiVoices: list[dict],
	oneCoreVoices: list[dict],
	languageCode: str | None = None,
	limit: int = 10,
) -> list[NvdaVoiceOption]:
	"""NVDA synthesizers and voices that could replace a JAWS synthesizer, best first.

	``nvdaSynths`` is NVDA's synthesizer list as ``(name, description)``.
	``sapiVoices`` and ``oneCoreVoices`` are ``{"name": ..., "vendor": ..., "language": ...}``.
	Eloquence and IBM ViaVoice are looked for both as NVDA add-on drivers and as SAPI 5 voices.
	"""
	info = synthInfo(jawsSynthName)
	options: list[NvdaVoiceOption] = []
	available = {name.lower(): (name, description) for name, description in nvdaSynths}

	wantedLanguage = (languageCode or "").lower().replace("-", "_")

	def languageBonus(voice: dict) -> int:
		language = (voice.get("language") or "").lower().replace("-", "_")
		if not wantedLanguage or not language:
			return 0
		if language == wantedLanguage:
			return 10
		if language.split("_", 1)[0] == wantedLanguage.split("_", 1)[0]:
			return 5
		return -30

	def add(option: NvdaVoiceOption):
		for existing in options:
			if existing.driver == option.driver and existing.voiceName == option.voiceName:
				existing.score = max(existing.score, option.score)
				return
		options.append(option)

	for rank, driver in enumerate(info.nvdaDrivers):
		if driver.lower() in available and info.family not in ("sapi5", "onecore"):
			name, description = available[driver.lower()]
			add(NvdaVoiceOption(name, description, reason=f"NVDA driver for {info.label}", score=100 - rank))
	if info.nvdaDriverWords:
		for name, description in nvdaSynths:
			if name.lower() in ("sapi5", "sapi5_32", "onecore", "sapi4", "silence", "espeak", "auto"):
				continue
			if _matchesAny(name, info.nvdaDriverWords) or _matchesAny(description, info.nvdaDriverWords):
				add(NvdaVoiceOption(name, description, reason=f"NVDA add-on synthesizer matching {info.label}", score=90))

	def voiceMatches(voice, words) -> bool:
		return _matchesAny(voice.get("name", ""), words) or _matchesAny(voice.get("vendor", ""), words)

	def driverDescription(driver: str) -> str:
		defaults = {
			"sapi5": "Microsoft Speech API version 5",
			"sapi5_32": "Microsoft Speech API version 5 (32-bit voices)",
			"onecore": "Windows OneCore voices",
		}
		return available.get(driver.lower(), (driver, defaults.get(driver.lower(), driver)))[1]

	oneCoreDescription = driverDescription("oneCore")

	if info.family == "sapi5":
		for voice in sapiVoices:
			if jawsVoiceName and _voiceNameMatches(voice.get("name", ""), jawsVoiceName):
				driver = voice.get("driver") or info.nvdaDrivers[0]
				add(NvdaVoiceOption(driver, driverDescription(driver), voice.get("name", ""), voice.get("id", ""), "Same SAPI 5 voice", 95 + languageBonus(voice)))
		for rank, driver in enumerate(info.nvdaDrivers):
			if driver.lower() in available:
				name, description = available[driver.lower()]
				add(NvdaVoiceOption(name, description, reason="SAPI 5, as JAWS used", score=60 - rank))
	elif info.family == "onecore":
		for voice in oneCoreVoices:
			if jawsVoiceName and _voiceNameMatches(voice.get("name", ""), jawsVoiceName):
				add(NvdaVoiceOption("oneCore", oneCoreDescription, voice.get("name", ""), voice.get("id", ""), "Same Windows voice", 95 + languageBonus(voice)))
		if "onecore" in available:
			add(NvdaVoiceOption(available["onecore"][0], oneCoreDescription, reason="Windows OneCore voices, as JAWS used", score=70))
	elif info.voiceWords:
		for voice in sapiVoices:
			if voiceMatches(voice, info.voiceWords):
				score = (80 if (jawsVoiceName and _voiceNameMatches(voice.get("name", ""), jawsVoiceName)) else 70) + languageBonus(voice)
				driver = voice.get("driver") or "sapi5"
				add(
					NvdaVoiceOption(
						driver,
						driverDescription(driver),
						voice.get("name", ""),
						voice.get("id", ""),
						f"SAPI 5 voice for {info.label}",
						score,
					),
				)
	options.sort(key=lambda option: option.score, reverse=True)
	return options[:limit]


def _voiceNameMatches(candidate: str, jawsVoiceName: str) -> bool:
	candidate = (candidate or "").lower()
	wanted = (jawsVoiceName or "").lower().replace("microsoft", "").strip()
	return bool(wanted) and wanted in candidate


def eloquenceAvailable(nvdaSynths: list[tuple[str, str]], sapiVoices: list[dict]) -> list[str]:
	"""Human-readable list of Eloquence and IBM ViaVoice engines NVDA can use on this computer."""
	found = []
	for name, description in nvdaSynths:
		if _matchesAny(name, _ELOQUENCE_WORDS) or _matchesAny(description, _ELOQUENCE_WORDS):
			found.append(f"NVDA synthesizer: {description} ({name})")
	for voice in sapiVoices:
		if _matchesAny(voice.get("name", ""), JAWS_SYNTHS["eloq"].voiceWords) or _matchesAny(voice.get("vendor", ""), ("ibm", "eloquence", "eti", "code factory")):
			found.append(f"SAPI 5 voice: {voice.get('name')}")
	return found


#: IBMTTS (ibmeci) variant ids for JAWS Eloquence person names.
ELOQUENCE_VARIANTS = {
	"reed": "1",
	"shelley": "2",
	"sandy": "3",
	"rocko": "4",
	"glen": "5",
	"shelly": "2",
	"grandma": "7",
	"grandpa": "8",
}


def matchVariant(variants: dict, jawsVoiceName: str) -> str | None:
	"""Pick the NVDA variant id whose name matches the JAWS person (``Reed`` -> ``1`` in IBMTTS)."""
	wanted = (jawsVoiceName or "").strip().lower()
	if not wanted:
		return None
	for variantId, name in variants.items():
		if str(name).strip().lower() == wanted:
			return variantId
	for variantId, name in variants.items():
		if wanted in str(name).strip().lower():
			return variantId
	for synonym in PERSON_SYNONYMS.get(wanted, ()):
		for variantId, name in variants.items():
			if str(name).strip().lower() == synonym or synonym in str(name).strip().lower():
				return variantId
	if wanted in ELOQUENCE_VARIANTS and ELOQUENCE_VARIANTS[wanted] in variants:
		return ELOQUENCE_VARIANTS[wanted]
	return None


def matchVoice(voices: dict, jawsVoiceName: str, languageCode: str | None) -> str | None:
	"""Pick the NVDA voice id for a JAWS person name and language.

	``voices`` is ``{id: (displayName, language)}``. A name match wins; otherwise a voice in
	the same language; otherwise None (keep the current voice).
	"""
	if jawsVoiceName:
		for voiceId, (name, _language) in voices.items():
			if _voiceNameMatches(name, jawsVoiceName):
				return voiceId
	if languageCode:
		wanted = languageCode.lower().replace("-", "_")
		for voiceId, (_name, language) in voices.items():
			if (language or "").lower().replace("-", "_") == wanted:
				return voiceId
		primary = wanted.split("_", 1)[0]
		for voiceId, (_name, language) in voices.items():
			if (language or "").lower().replace("-", "_").split("_", 1)[0] == primary:
				return voiceId
	return None


def scaledVoiceSettings(profile: VoiceProfile, context: VoiceContext) -> dict:
	"""NVDA 0 to 100 values for a JAWS context: ``{"rate": 57, "pitch": 65, "volume": 100}``."""
	info = profile.synth
	result = {}
	for name, parameter in (("rate", info.rate), ("pitch", info.pitch), ("volume", info.volume)):
		if parameter is None:
			# The JAWS range of this setting isn't known for this synthesizer: leave NVDA's.
			continue
		percent = parameter.toPercent(getattr(context, name))
		if percent is not None:
			result[name] = percent
	return result


# -- voices of synthesizers that are not loaded --------------------------------------------

#: IBMTTS (ibmeci) voice ids are Eloquence language dialect numbers.
ECI_DIALECTS = {
	"en_US": 0x00010000,
	"en_GB": 0x00010001,
	"es_ES": 0x00020000,
	"es_MX": 0x00020001,
	"fr_FR": 0x00030000,
	"fr_CA": 0x00030001,
	"de_DE": 0x00040000,
	"it_IT": 0x00050000,
	"zh_CN": 0x00060000,
	"zh_TW": 0x00060001,
	"pt_BR": 0x00070000,
	"ja_JP": 0x00080000,
	"fi_FI": 0x00090000,
	"ko_KR": 0x000A0000,
	"zh_HK": 0x000B0001,
	"nl_NL": 0x000C0000,
	"nb_NO": 0x000D0000,
	"sv_SE": 0x000E0000,
	"da_DK": 0x000F0000,
}
IBMTTS_VARIANTS = {"1": "Reed", "2": "Shelley", "3": "Sandy", "4": "Rocko", "5": "Glen", "6": "FastFlo", "7": "Grandma", "8": "Grandpa"}


def knownVoices(driver: str, sapiVoices: list, oneCoreVoices: list, speechPlatformVoices: list | None = None) -> tuple[dict, dict]:
	"""``({voice id: (name, language)}, {variant id: name})`` for a driver, without loading it.

	Known for SAPI 5, OneCore, the Speech Platform and IBMTTS; empty for drivers whose
	voices are only known once they run.
	"""
	name = (driver or "").lower()
	if name in ("sapi5", "sapi5_32"):
		wanted = [voice for voice in sapiVoices if (voice.get("driver") or "sapi5") == name] or list(sapiVoices)
		return {voice["id"]: (voice.get("name", ""), voice.get("language") or None) for voice in wanted if voice.get("id")}, {}
	if name == "onecore":
		return {voice["id"]: (voice.get("name", ""), voice.get("language") or None) for voice in oneCoreVoices if voice.get("id")}, {}
	if name == "mssp":
		return {voice["id"]: (voice.get("name", ""), voice.get("language") or None) for voice in speechPlatformVoices or [] if voice.get("id")}, {}
	if name == "ibmeci":
		return {str(number): (language, language) for language, number in ECI_DIALECTS.items()}, dict(IBMTTS_VARIANTS)
	return {}, {}
