# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Plan a migration from what was found, then carry it out safely.

``buildPlan`` works out everything that would change, without changing
anything, so the wizard can show it before the user agrees. ``Migration``
carries the plan out: first a backup of NVDA's settings and a copy of the
JAWS settings (the archive), then the changes. If a change fails badly, the
backup is put back and NVDA reloads its saved settings, so a failed migration
leaves NVDA as it was.
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import threading
from dataclasses import dataclass, field

from . import (
	backup,
	classicSounds,
	debugLog,
	dictMap,
	jawsDetect,
	jawsFiles,
	jawsIndex,
	keyPlan,
	managers,
	nvdaEnv,
	schemeMap,
	settingsMap,
	soundMap,
	symbolMap,
	safety,
	systemCheck,
	voices,
)

TARGET_PROFILE = "profile"
TARGET_NORMAL = "normal"
DEFAULT_PROFILE_NAME = "JAWS settings"
APP_PROFILE_PREFIX = "JAWS - "


def _log():
	try:
		from logHandler import log

		return log
	except Exception:  # pragma: no cover
		import logging

		return logging.getLogger("jawsMigrator")


@dataclass
class MigrationOptions:
	jaws: jawsDetect.JawsInstallation
	language: str
	scope: str = jawsIndex.BOTH
	#: NVDA's normal configuration by default: a manually activated profile holding the JAWS settings is
	#: replaced as soon as anything else (an add-on, the user) turns on another profile by hand.
	target: str = TARGET_NORMAL
	profileName: str = DEFAULT_PROFILE_NAME
	activateAtStartup: bool = True
	activateNow: bool = True
	settings: bool = True
	appProfiles: bool = True
	sleepApps: list = field(default_factory=list)
	voice: bool = True
	#: Index into the plan's voice options; -1 keeps NVDA's synthesizer and voice.
	voiceChoice: int = 0
	#: The voices of JAWS's contexts (JAWS cursor, messages...) as ClassicSpeech Voice Profiles; the user chooses it.
	classicVoices: bool = False
	classicSchemes: bool = True
	classicSettings: bool = True
	#: Name of the converted scheme to turn on in ClassicSpeech, or "" to leave ClassicSpeech as it is.
	#: Only ever the user's choice: a migration never turns a scheme on by itself.
	activeClassicScheme: str = ""
	dictionaries: bool = True
	appDictionaries: bool = True
	sharedDictionaries: bool = False
	symbols: bool = True
	jawsSymbolNames: bool = False
	keyboard: bool = True
	#: JAWS keyboard layouts whose own keystrokes become NVDA gestures (``desktop``, ``laptop``,
	#: ``classic laptop``...); None takes the layout JAWS uses.
	keyboardLayouts: list | None = None
	#: NVDA's keyboard layout after the migration: ``desktop``, ``laptop``, "" to keep NVDA's,
	#: or None to follow JAWS (and the keyboard layouts chosen).
	nvdaKeyboardLayout: str | None = None
	quickNavLetters: bool = True
	overrideConflicts: bool = False
	#: JAWS sounds in place of NVDA's own sounds, through ClassicSpeech (see classicSounds).
	sounds: bool = False
	#: Every JAWS sound copied into ClassicSpeech, as the scheme JAWS Sounds (from JAWS).
	allSounds: bool = True
	archive: bool = True
	addonsToInstall: list = field(default_factory=list)
	#: Names of the JAWS voice profiles to migrate; None migrates every one NVDA has a synthesizer for.
	voiceProfiles: list | None = None
	#: Names of the converted schemes to copy into ClassicSpeech; None copies them all.
	schemes: list | None = None
	#: Names of the JAWS voice aliases to carry into ClassicSpeech; None carries them all.
	voiceAliases: list | None = None
	#: True once the user's saved choice of items (JAWS Migration Assistant settings) narrowed the plan.
	selectionApplied: bool = False


@dataclass
class ProfilePlan:
	"""One JAWS voice profile and the NVDA synthesizer that will speak with its settings."""

	name: str
	profile: voices.VoiceProfile
	contexts: dict
	aliases: dict
	option: voices.NvdaVoiceOption | None
	primary: bool = False
	userCopy: bool = False
	#: Set when another JAWS profile already uses the same NVDA synthesizer.
	sharedWith: str = ""

	@property
	def synth(self) -> voices.JawsSynthInfo:
		return self.profile.synth

	@property
	def available(self) -> bool:
		return self.option is not None and not self.sharedWith

	def describe(self) -> str:
		target = self.option.label if self.option else "no NVDA synthesizer for it on this computer"
		text = f"{self.name} ({self.synth.label}) -> {target}"
		if self.sharedWith:
			text += f" (NVDA's {self.option.driver} already takes the {self.sharedWith} profile)"
		return text


@dataclass
class DictionaryPlan:
	label: str
	source: jawsIndex.IndexedFile
	conversion: dictMap.DictConversion
	#: Entries for the default dictionary, and for the voice dictionary of the migrated voice.
	defaultEntries: list = field(default_factory=list)
	voiceEntries: list = field(default_factory=list)


@dataclass
class MigrationPlan:
	options: MigrationOptions
	index: jawsIndex.JawsIndex
	facts: systemCheck.SystemFacts
	settings: settingsMap.MappingResult = field(default_factory=settingsMap.MappingResult)
	#: ``{configuration name: MappingResult}``: JAWS settings for single applications that become NVDA profiles.
	appSettings: dict = field(default_factory=dict)
	#: ``{configuration name: [program names NVDA knows the application by]}``, never empty.
	appExecutables: dict = field(default_factory=dict)
	#: ``{configuration name: why}``: JAWS application settings NVDA could never turn on (web sites, parts of Windows...).
	appSkipped: dict = field(default_factory=dict)
	sleepCandidates: list = field(default_factory=list)
	voiceProfile: voices.VoiceProfile | None = None
	voiceProfileName: str = ""
	voiceContexts: dict = field(default_factory=dict)
	voiceOptions: list = field(default_factory=list)
	jawsSynthName: str = ""
	schemes: list = field(default_factory=list)
	aliases: dict = field(default_factory=dict)
	jawsActiveScheme: str = ""
	dictionaries: list = field(default_factory=list)
	symbols: dict = field(default_factory=dict)
	symbolSources: list = field(default_factory=list)
	#: JAWS's own names for every symbol, used when the user asks for them.
	jawsSymbolDefaults: dict = field(default_factory=dict)
	jawsSymbolDefaultsSource: str = ""
	keys: keyPlan.KeyPlan = field(default_factory=keyPlan.KeyPlan)
	#: The JAWS keyboard layout in use (``laptop``, ``classic laptop``...) and every layout the key map has.
	jawsKeyboardLayout: str = "desktop"
	keyboardLayouts: list = field(default_factory=list)
	sounds: list = field(default_factory=list)
	missingSounds: list = field(default_factory=list)
	scripts: list = field(default_factory=list)
	#: Every JAWS voice profile found, primary first.
	profiles: list = field(default_factory=list)

	def selectedProfiles(self) -> list:
		wanted = self.options.voiceProfiles
		return [p for p in self.profiles if p.available and (wanted is None or p.name in wanted)]

	def chosenDictionaries(self) -> list:
		options = self.options
		chosen = []
		for dictionaryPlan in self.dictionaries:
			isDefault = os.path.splitext(dictionaryPlan.source.name)[0].lower() == "default"
			if dictionaryPlan.source.scope == jawsIndex.SHARED and not options.sharedDictionaries:
				continue
			if not isDefault and not options.appDictionaries:
				continue
			chosen.append(dictionaryPlan)
		return chosen

	def chosenSymbols(self) -> dict:
		symbols = {}
		if self.options.jawsSymbolNames:
			symbols.update(self.jawsSymbolDefaults)
		symbols.update(self.symbols)
		return symbols

	def chosenKeyboardLayouts(self) -> list:
		wanted = self.options.keyboardLayouts
		if wanted is None:
			return [layout for layout in self.keyboardLayouts if layout.id == self.jawsKeyboardLayout]
		return [layout for layout in self.keyboardLayouts if layout.id in wanted]

	def settingChange(self, key: str, target: str = settingsMap.NVDA):
		"""The planned change of one setting, such as ``keyboard.keyboardLayout``, or None."""
		return next((change for change in self.settings.changes if change.target == target and change.key == key), None)

	def nvdaKeyboardLayout(self) -> str:
		"""NVDA's keyboard layout after the migration: ``desktop``, ``laptop``, or "" when it stays as it is."""
		options = self.options
		if options.nvdaKeyboardLayout is not None:
			return options.nvdaKeyboardLayout
		change = self.settingChange("keyboard.keyboardLayout")
		if change is None:
			return ""
		chosen = self.chosenKeyboardLayouts() if options.keyboard else []
		if chosen and self.jawsKeyboardLayout not in [layout.id for layout in chosen]:
			# Only other layouts' keystrokes were chosen: NVDA uses the layout they work in.
			return chosen[0].nvdaLayout
		return str(change.value)

	def finalSettingChanges(self) -> list:
		"""The setting changes to apply, with NVDA's keyboard layout and NVDA keys fitted to the keyboard choices."""
		changes = [change for change in self.settings.changes if not (change.target == settingsMap.NVDA and change.key == "keyboard.keyboardLayout")]
		layout = self.nvdaKeyboardLayout()
		original = self.settingChange("keyboard.keyboardLayout")
		if layout:
			if original is not None and original.value == layout:
				changes.append(original)
			else:
				changes.append(settingsMap.SettingChange(settingsMap.NVDA, ("keyboard", "keyboardLayout"), layout, f"Keyboard layout: {layout}", "chosen in the JAWS Migration Assistant"))
		modifiers = self.settingChange("keyboard.NVDAModifierKeys")
		if modifiers is not None and self.options.keyboard and self.keyboardLayouts:
			# Caps Lock is an NVDA key when the keystrokes of a Caps Lock layout (Laptop) come over.
			capsLock = any(layout.capsLock for layout in self.chosenKeyboardLayouts())
			value = (int(modifiers.value) & ~1) | (1 if capsLock else 0) or 6
			if value != modifiers.value:
				changes = [change if change is not modifiers else settingsMap.SettingChange(settingsMap.NVDA, modifiers.path, value, settingsMap.nvdaKeyLabel(value), modifiers.source) for change in changes]
		return changes

	def jawsSchemeName(self) -> str:
		"""The name of the converted scheme JAWS itself was using, or ""."""
		for converted in self.schemes:
			if self.jawsActiveScheme and converted.title.lower() == self.jawsActiveScheme.lower():
				return converted.name
		return ""

	def selectedSchemes(self) -> list:
		wanted = self.options.schemes
		return [s for s in self.schemes if wanted is None or s.name in wanted]

	@property
	def classicSpeech(self) -> bool:
		return self.facts.classicSpeech.installed and self.facts.classicSpeech.usable

	@property
	def languageLcid(self) -> int | None:
		return jawsFiles.JAWS_LANGUAGES.get(self.options.language, (None, None))[0]

	@property
	def chosenVoice(self) -> voices.NvdaVoiceOption | None:
		if not self.options.voice or self.options.voiceChoice < 0 or self.options.voiceChoice >= len(self.voiceOptions):
			return None
		return self.voiceOptions[self.options.voiceChoice]

	@property
	def globalContext(self) -> voices.VoiceContext | None:
		return self.voiceContexts.get("Global")


# -- planning -----------------------------------------------------------------------------


def _userKeys(index: jawsIndex.JawsIndex) -> set:
	user = index.defaultJcf(jawsIndex.USER)
	return {(section.name.lower(), key.lower()) for section in user.sections.values() for key in section.keys()}


def _activeScheme(index: jawsIndex.JawsIndex, merged, scope: str, userKeys: set) -> tuple:
	"""The speech and sounds scheme JAWS uses, as ``(IniFile or None, chosen)``.

	JAWS names it in ``[options] Scheme`` (Classic by default) and finds it by file name, the
	user's copy first. ``chosen`` says whether the scheme belongs in this migration: always with
	JAWS's full or shared settings, and with "your settings only" when the user picked the
	scheme or keeps their own copy of it.
	"""
	name = (merged.get("options", "Scheme", "") or "Classic").strip()
	files = sorted(index.byExtension("smf", jawsIndex.BOTH), key=lambda f: f.scope != jawsIndex.USER)
	matches = [f for f in files if os.path.splitext(f.name)[0].lower() == name.lower()]
	if not matches:
		for indexed in files:
			try:
				title = jawsFiles.readIni(indexed.path).get("Information", "Title") or ""
			except OSError:
				continue
			if title.strip().lower() == name.lower():
				matches.append(indexed)
	for indexed in matches:
		try:
			ini = jawsFiles.readIni(indexed.path)
		except OSError:
			continue
		chosen = scope != jawsIndex.USER or ("options", "scheme") in userKeys or indexed.scope == jawsIndex.USER
		return ini, chosen
	return None, False


#: JAWS keeps a web site's own settings under the site's domain, such as theoldreader.com.
_WEB_SITE = re.compile(
	r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+"
	r"(?:com|net|org|edu|gov|mil|int|info|biz|io|co|app|dev|ai|me|tv|online|site|web|news|blog|shop|store|cloud|live|[a-z]{2})$",
	re.IGNORECASE,
)
#: How NVDA knows an application: its program's file name without ".exe" (appModule.appName).
_PROGRAM_NAME = re.compile(r"^[a-z0-9][^<>:\"/\\|?*!\x00-\x1f]*$", re.IGNORECASE)


def _windowsLibrary(name: str) -> bool:
	"""Whether ``name`` is a part of Windows, a library such as shell32.dll, rather than a program."""
	root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
	system = os.path.join(root, "System32")
	if not os.path.isfile(os.path.join(system, name + ".dll")):
		return False
	return not any(os.path.isfile(os.path.join(folder, name + ".exe")) for folder in (system, root))


def appExecutables(index: jawsIndex.JawsIndex, configName: str) -> tuple[list[str], str]:
	"""``(program names, "")`` NVDA can turn a profile on in, for a JAWS application configuration; ``([], why)`` when there are none.

	NVDA knows an application by its program's file name without ".exe", and turns profiles on with
	triggers ``app:<that name>``. JAWS's ConfigNames.ini maps program (and library) names to
	configurations; otherwise JAWS uses the configuration named after the program. Settings for a web
	site, for parts of Windows, or under a name no program can have could never turn on in NVDA.
	"""
	mapped = index.configNames().get(configName.lower(), [])
	if mapped:
		names = []
		libraries = []
		for name in mapped:
			name = name.strip()
			if name.lower().endswith(".exe"):
				name = name[:-4]
			# "regex" starts a ConfigNames line that matches web addresses, not programs.
			if not _PROGRAM_NAME.match(name) or name.lower() == "regex":
				continue
			if _windowsLibrary(name):
				libraries.append(name)
			elif name.lower() not in names:
				names.append(name.lower())
		if names:
			return names, ""
		if libraries:
			return [], f"JAWS uses these settings in parts of Windows ({', '.join(libraries)}), not in a program NVDA can switch profiles for"
		return [], f"JAWS uses these settings for {', '.join(mapped)}, which NVDA does not know as programs"
	if _WEB_SITE.match(configName):
		return [], f"these are JAWS settings for the web site {configName}; NVDA switches profiles for programs, not for web sites"
	name = configName.strip()
	if not _PROGRAM_NAME.match(name):
		return [], f"{configName} is not the name of a program, so NVDA could never switch to a profile for it"
	if _windowsLibrary(name):
		return [], f"{configName} is a part of Windows, not a program NVDA can switch profiles for"
	return [name.lower()], ""


def _planProfiles(plan: MigrationPlan, index: jawsIndex.JawsIndex, facts: systemCheck.SystemFacts, options: MigrationOptions) -> list:
	"""A ProfilePlan for every JAWS voice profile, the active one first."""
	scope = options.scope if options.scope != jawsIndex.USER else jawsIndex.BOTH
	userProfiles = {name.lower() for name in index.voiceProfileNames(jawsIndex.USER)}
	names = index.voiceProfileNames(scope)
	if options.scope == jawsIndex.USER:
		names = [name for name in names if name.lower() in userProfiles] or names
	# Which JAWS synthesizers each profile is for: locally installed ones first, then remote-only ones.
	localSynths = {synth.shortName.lower() for synth in index.synths if not synth.remoteOnly}
	remoteSynths = {synth.shortName.lower() for synth in index.synths if synth.remoteOnly}

	def priority(name: str):
		profile = index.voiceProfile(name, scope)
		synthName = (profile.primarySynthesizer if profile else "").lower()
		return (
			name.lower() != plan.voiceProfileName.lower(),
			name.lower() not in userProfiles,
			0 if synthName in localSynths else 1 if synthName in remoteSynths else 2,
			name.lower(),
		)

	ordered = sorted(names, key=priority)
	result = []
	takenDrivers: dict = {}
	for name in ordered:
		profile = plan.voiceProfile if name.lower() == plan.voiceProfileName.lower() and plan.voiceProfile else index.voiceProfile(name, scope)
		if profile is None:
			continue
		languages = profile.languages()
		language = options.language if options.language in languages else (languages[0] if languages else options.language)
		contexts = {}
		for context in voices.CONTEXTS:
			if profile.hasContext(language, context) or context == "Global":
				contexts[context] = profile.context(language, context)
		globalContext = contexts.get("Global")
		languageCode = jawsFiles.languageCodeForLcid(jawsFiles.lcidFromText(globalContext.synthLanguage)) if globalContext else None
		languageCode = languageCode or jawsFiles.JAWS_LANGUAGES.get(options.language, (None, None))[1]
		installedDrivers = {driver.lower() for driver, _description in facts.synths}
		candidates = voices.findNvdaEquivalents(
			profile.primarySynthesizer,
			globalContext.voiceName if globalContext else "",
			facts.synths,
			facts.sapiVoices,
			facts.oneCoreVoices,
			languageCode=languageCode,
		)
		primary = bool(plan.voiceProfileName) and name.lower() == plan.voiceProfileName.lower()
		option = None
		if primary:
			option = plan.chosenVoice
		else:
			option = next((c for c in candidates if c.driver.lower() in installedDrivers or not installedDrivers), None)
		profilePlan = ProfilePlan(
			name=name,
			profile=profile,
			contexts=contexts,
			aliases=profile.voiceAliases(language),
			option=option,
			primary=primary,
			userCopy=name.lower() in userProfiles,
		)
		if option is not None:
			driver = option.driver.lower()
			if driver in takenDrivers:
				profilePlan.sharedWith = takenDrivers[driver]
			else:
				takenDrivers[driver] = name
		result.append(profilePlan)
	return result


def buildPlan(options: MigrationOptions, index: jawsIndex.JawsIndex, facts: systemCheck.SystemFacts, inNvda: bool = True) -> MigrationPlan:
	plan = MigrationPlan(options=options, index=index, facts=facts)
	scope = options.scope
	merged = index.defaultJcf(jawsIndex.BOTH)
	source = index.defaultJcf(scope)
	classic = plan.classicSpeech

	# Settings Center, for all applications. With JAWS's full or shared settings, NVDA follows JAWS
	# as it runs, JAWS's own defaults included; with "your settings only", just what the user changed.
	userKeys = _userKeys(index)
	scheme, schemeChosen = _activeScheme(index, merged, scope, userKeys)
	plan.settings = settingsMap.mapSettings(
		source,
		merged,
		classicSpeech=classic,
		userKeys=userKeys,
		effective=scope != jawsIndex.USER,
		scheme=scheme,
		schemeChosen=schemeChosen,
	)

	# Settings for single applications: only the user's own, never JAWS's stock application files.
	# NVDA turns profiles on for programs only, so settings for web sites and parts of Windows are listed, not migrated.
	if scope in (jawsIndex.USER, jawsIndex.BOTH):
		for configName in index.applicationJcfNames(jawsIndex.USER):
			found = index.find(configName + ".jcf", jawsIndex.USER)
			if found is None:
				continue
			try:
				appIni = jawsFiles.readIni(found.path, inlineComments=True)
			except OSError:
				continue
			if index.leasey.found and jawsDetect.hasLeaseyMarker(found.relative):
				continue
			result = settingsMap.mapSettings(appIni, jawsFiles.mergeIni(merged, appIni), classicSpeech=False, isApplication=True)
			hasNvdaSettings = any(change.target == settingsMap.NVDA for change in result.changes)
			if not (result.sleepMode or hasNvdaSettings):
				continue
			executables, why = appExecutables(index, configName)
			if not executables:
				plan.appSkipped[configName] = why
				continue
			plan.appExecutables[configName] = executables
			if result.sleepMode:
				plan.sleepCandidates.append((configName, executables))
			if hasNvdaSettings:
				plan.appSettings[configName] = result

	# Voice profile.
	profileName = plan.settings.voiceProfileName or merged.get("Voice Profiles", "ActiveVoiceProfileName", "") or ""
	jfwSynth = voices.activeJawsSynth(index.synths, index.jfwIni, merged.get("options", "Synthesizer"))
	if not profileName and jfwSynth is not None:
		for name in index.voiceProfileNames(jawsIndex.BOTH):
			candidate = index.voiceProfile(name)
			if candidate and candidate.primarySynthesizer.lower() == jfwSynth.shortName.lower():
				profileName = name
				break
	if profileName:
		plan.voiceProfile = index.voiceProfile(profileName, scope if scope != jawsIndex.USER else jawsIndex.BOTH)
		plan.voiceProfileName = profileName
	if plan.voiceProfile is not None:
		plan.jawsSynthName = plan.voiceProfile.primarySynthesizer or (jfwSynth.shortName if jfwSynth else "")
		languages = plan.voiceProfile.languages()
		language = options.language if options.language in languages else (languages[0] if languages else options.language)
		for context in voices.CONTEXTS:
			if plan.voiceProfile.hasContext(language, context) or context == "Global":
				plan.voiceContexts[context] = plan.voiceProfile.context(language, context)
		plan.aliases = plan.voiceProfile.voiceAliases(language)
		globalContext = plan.voiceContexts.get("Global")
		languageCode = None
		if globalContext is not None:
			languageCode = jawsFiles.languageCodeForLcid(jawsFiles.lcidFromText(globalContext.synthLanguage))
		languageCode = languageCode or jawsFiles.JAWS_LANGUAGES.get(options.language, (None, None))[1]
		plan.voiceOptions = voices.findNvdaEquivalents(
			plan.jawsSynthName,
			globalContext.voiceName if globalContext else "",
			facts.synths,
			facts.sapiVoices,
			facts.oneCoreVoices,
			languageCode=languageCode,
		)
	elif jfwSynth is not None:
		plan.jawsSynthName = jfwSynth.shortName
		plan.voiceOptions = voices.findNvdaEquivalents(jfwSynth.shortName, "", facts.synths, facts.sapiVoices, facts.oneCoreVoices)

	# Every other JAWS voice profile, so all of them can be migrated.
	plan.profiles = _planProfiles(plan, index, facts, options)
	unionAliases = {}
	for profilePlan in plan.profiles:
		for name, value in profilePlan.aliases.items():
			if name not in unionAliases or voices.aliasIsNeutral(unionAliases[name]):
				unionAliases[name] = value

	# Speech and sounds schemes, for ClassicSpeech.
	plan.jawsActiveScheme = plan.settings.schemeName or merged.get("options", "Scheme", "") or ""
	if classic:
		schemeFiles = index.byExtension("smf", jawsIndex.BOTH)
		seenTitles = set()
		# The user's schemes first, so they win over shared ones with the same title.
		for indexed in sorted(schemeFiles, key=lambda f: f.scope != jawsIndex.USER):
			try:
				ini = jawsFiles.readIni(indexed.path)
			except OSError:
				continue
			converted = schemeMap.convertScheme(ini, indexed.path, index.soundFile, unionAliases or plan.aliases)
			if converted.title.lower() in seenTitles:
				continue
			if indexed.scope == jawsIndex.USER:
				converted.name = f"{converted.title} (your JAWS scheme)"
			seenTitles.add(converted.title.lower())
			plan.schemes.append(converted)
		aliasScheme = schemeMap.aliasScheme(unionAliases or plan.aliases)
		if aliasScheme.items:
			plan.schemes.append(aliasScheme)

	# Dictionaries.
	existing = dictMap.readDicPatterns(os.path.join(facts.configDir or nvdaEnv.configDir(), "speechDicts", "default.dic"))
	jdfFiles = []
	for indexed in index.byExtension("jdf", jawsIndex.BOTH):
		if indexed.scope == jawsIndex.USER and scope == jawsIndex.SHARED:
			continue
		jdfFiles.append(indexed)
	seen = set(existing)
	jawsSynthNames = {plan.jawsSynthName.lower()} | {s.longName.lower() for s in index.synths if s.shortName.lower() == plan.jawsSynthName.lower()}
	for indexed in sorted(jdfFiles, key=lambda f: (f.scope != jawsIndex.USER, os.path.splitext(f.name)[0].lower() != "default")):
		try:
			rules = jawsFiles.readJdf(indexed.path)
		except OSError:
			continue
		label = ("your " if indexed.scope == jawsIndex.USER else "shared ") + indexed.name
		conversion = dictMap.convertRules(rules, label, plan.languageLcid, seen)
		dictionaryPlan = DictionaryPlan(label, indexed, conversion)
		for entry in conversion.entries:
			seen.add(entry.key() + (entry.jawsSynthesizer.lower(),))
			if not entry.jawsSynthesizer:
				dictionaryPlan.defaultEntries.append(entry)
			elif entry.jawsSynthesizer.lower() in jawsSynthNames:
				dictionaryPlan.voiceEntries.append(entry)
			else:
				conversion.skipped.append(dictMap.Skipped(entry.source, f"The rule is only for the JAWS synthesizer {entry.jawsSynthesizer}."))
		plan.dictionaries.append(dictionaryPlan)

	# Punctuation and symbols.
	sblNames = {f.name.lower() for f in index.byExtension("sbl", jawsIndex.USER)}
	for name in sorted(sblNames):
		userFile = index.find(name, jawsIndex.USER)
		sharedFile = index.find(name, jawsIndex.SHARED)
		if userFile is None:
			continue
		try:
			userIni = symbolMap.readSymbolFile(userFile.path)
			sharedIni = symbolMap.readSymbolFile(sharedFile.path) if sharedFile else jawsFiles.IniFile()
		except OSError:
			continue
		userSymbols = symbolMap.parseSymbols(symbolMap.languageSection(userIni, plan.languageLcid, options.language))
		sharedSymbols = symbolMap.parseSymbols(symbolMap.languageSection(sharedIni, plan.languageLcid, options.language))
		changed = symbolMap.changedSymbols(sharedSymbols, userSymbols)
		if changed:
			plan.symbols.update(changed)
			plan.symbolSources.append(userFile.relative)
	if True:
		synthFile = {"eloq": "eloq.sbl", "sapi 5x": "SAPI 5x.sbl", "sapi 5x 64": "SAPI 5x 64.sbl", "msmobile": "MSMobile.sbl"}.get(plan.jawsSynthName.lower(), "default.sbl")
		shared = index.find(synthFile, jawsIndex.SHARED) or index.find("default.sbl", jawsIndex.SHARED)
		if shared is not None:
			try:
				ini = symbolMap.readSymbolFile(shared.path)
				plan.jawsSymbolDefaults = symbolMap.parseSymbols(symbolMap.languageSection(ini, plan.languageLcid, options.language))
				plan.jawsSymbolDefaultsSource = shared.relative
			except OSError:
				pass

	# Keyboard: the JAWS keyboard layout in use, every layout the key map has, and the keystrokes.
	plan.jawsKeyboardLayout = keyPlan.layoutId(plan.settings.jawsKeyboardLayout or merged.get("options", "KeyboardType", "Desktop"))
	plan.keyboardLayouts = keyPlan.keyboardLayouts(index.defaultJkm(scope))
	planKeyboard(plan, inNvda)
	plan.keys.applicationKeys = keyPlan.applicationKeyMaps(index.byExtension("jkm", jawsIndex.USER if scope != jawsIndex.SHARED else jawsIndex.SHARED))

	# Sounds.
	plan.sounds, plan.missingSounds = soundMap.chooseSounds(merged, index.soundFile)

	# Scripts the user wrote, for the report.
	for indexed in index.byExtension("jss", jawsIndex.USER):
		try:
			text = jawsFiles.readText(indexed.path)
		except OSError:
			continue
		names = jawsIndex._SCRIPT_DEFINITION.findall(text)
		plan.scripts.append((indexed.relative, names))
	return plan


def planKeyboard(plan: MigrationPlan, inNvda: bool = False) -> None:
	"""Work out ``plan.keys`` for the chosen JAWS keyboard layouts and keyboard options."""
	options = plan.options
	boundScripts = scriptExists = None
	if inNvda:
		from . import nvdaApply

		boundScripts = nvdaApply.gestureBoundScripts
		scriptExists = nvdaApply.scriptExists
	applicationKeys = plan.keys.applicationKeys
	plan.keys = keyPlan.planKeys(
		plan.index.defaultJkm(options.scope),
		plan.jawsKeyboardLayout,
		boundScripts=boundScripts,
		scriptExists=scriptExists,
		quickNavLetters=options.quickNavLetters,
		overrideConflicts=options.overrideConflicts,
		leaseyActive=plan.index.leasey.found,
		layouts=[layout.id for layout in plan.chosenKeyboardLayouts()],
		# NVDA's layout is only known when the migration sets it in the normal configuration; in a
		# profile, or left alone, NVDA may use either layout.
		nvdaLayout=(plan.nvdaKeyboardLayout() if options.settings and options.target != TARGET_PROFILE else "") or None,
	)
	plan.keys.applicationKeys = applicationKeys


# -- the debug log -----------------------------------------------------------------------


def _logApplied(applied: list, failed: list, prefix: str = "") -> None:
	"""Log the settings just applied, with the configuration NVDA wrote them to. Call it while that configuration is being written."""
	from . import nvdaApply

	try:
		where = nvdaApply.writingConfigurationName()
	except Exception:
		where = "unknown configuration"
	for change in applied:
		debugLog.note(f"{prefix}{change.key} = {change.value!r} -> {where} ({change.label}; from {change.source})")
	for change, reason in failed:
		debugLog.note(f"{prefix}NOT SET {change.key} = {change.value!r} (in {where}): {reason}")


def describePlan(plan: MigrationPlan) -> None:
	"""Write everything a migration found and is about to do into the debug log."""
	options = plan.options
	facts = plan.facts
	index = plan.index
	debugLog.section("Computer")
	debugLog.note(f"Windows: {getattr(facts, 'windows', '')}; NVDA {getattr(facts, 'nvdaVersion', '')}; ClassicSpeech: {facts.classicSpeech.describe}")
	debugLog.note(f"NVDA synthesizers: {getattr(facts, 'synths', [])}")
	debugLog.note(f"JAWS: {index.jaws.displayName}; language {options.language}; files indexed: {len(index.files)}; Leasey found: {index.leasey.found}")
	debugLog.section("Choices")
	for name, value in sorted(vars(options).items()):
		if name != "jaws":
			debugLog.note(f"{name} = {debugLog.describe(value)}")
	debugLog.section("Voice")
	if plan.voiceProfile is not None:
		info = plan.voiceProfile.synth
		debugLog.note(f"JAWS voice profile {plan.voiceProfileName}, synthesizer {plan.jawsSynthName} ({info.label}); JAWS ranges: rate {info.rate}, pitch {info.pitch}, volume {info.volume}")
		for name, context in plan.voiceContexts.items():
			debugLog.note(f"  {name}: {context.describe()} (JAWS values rate {context.rate}, pitch {context.pitch}, volume {context.volume}) -> NVDA {voices.scaledVoiceSettings(plan.voiceProfile, context)}")
	chosen = plan.chosenVoice
	debugLog.note(f"NVDA voice: {chosen.label if chosen else 'NVDA keeps its own synthesizer and voice'}")
	for profilePlan in plan.profiles:
		debugLog.note(f"  voice profile {profilePlan.describe()}; available {profilePlan.available}; aliases {len(profilePlan.aliases)}")
	debugLog.section("Settings")
	for change in plan.finalSettingChanges():
		debugLog.note(f"{change.target}: {change.key} = {change.value!r} ({change.label}; from {change.source})")
	for item in plan.settings.notMigrated[:300]:
		debugLog.note(f"not migrated: {item}")
	debugLog.section("Schemes and sounds")
	for converted in plan.schemes:
		debugLog.note(f"{converted.name}: {len(converted.items)} items, {converted.soundCount} sounds, not converted {len(converted.notConverted)}, missing sounds {converted.missingSounds}")
	for choice in plan.sounds:
		debugLog.note(f"NVDA sound {choice.event.nvdaName} <- JAWS {choice.jawsName} ({choice.jawsPath}) {choice.fromOption}")
	for missing in plan.missingSounds:
		debugLog.note(f"sound not found: {missing}")
	debugLog.section("Keyboard")
	debugLog.note(f"JAWS layout in use {plan.jawsKeyboardLayout}; layouts {[layout.id for layout in plan.keyboardLayouts]}; chosen {[layout.id for layout in plan.chosenKeyboardLayouts()]}; NVDA layout {plan.nvdaKeyboardLayout()!r}")
	debugLog.note(f"{len(plan.keys.bindings)} keystrokes to add; skipped by kind: " + ", ".join(f"{kind} {plan.keys.countSkipped(kind)}" for kind in sorted({item.kind for item in plan.keys.skipped})))
	debugLog.section("Dictionaries, symbols, applications")
	for dictionaryPlan in plan.dictionaries:
		debugLog.note(f"{dictionaryPlan.label}: {len(dictionaryPlan.defaultEntries)} default and {len(dictionaryPlan.voiceEntries)} voice entries, {len(dictionaryPlan.conversion.skipped)} skipped")
	debugLog.note(f"{len(plan.symbols)} symbols changed by the user; {len(plan.jawsSymbolDefaults)} JAWS symbol names")
	for name, mapping in plan.appSettings.items():
		debugLog.note(f"application {name} (NVDA knows it as {plan.appExecutables.get(name)}): {[(change.key, change.value) for change in mapping.changes]}")
	for name, why in plan.appSkipped.items():
		debugLog.note(f"application settings not migrated: {name}: {why}")
	debugLog.note(f"sleep candidates {plan.sleepCandidates}")


# -- carrying it out ------------------------------------------------------------------------


@dataclass
class MigrationResult:
	backup: backup.BackupInfo | None = None
	archiveFolder: str = ""
	outputFolder: str = ""
	applied: list = field(default_factory=list)
	failed: list = field(default_factory=list)
	messages: list = field(default_factory=list)
	gesturesAdded: int = 0
	dictionaryEntries: int = 0
	voiceDictionaryEntries: int = 0
	symbols: int = 0
	schemesWritten: list = field(default_factory=list)
	voiceProfilesWritten: list = field(default_factory=list)
	appProfiles: list = field(default_factory=list)
	#: JAWS sounds given to ClassicSpeech's schemes in place of NVDA's (classicSounds.SoundsResult), or None.
	nvdaSounds: object = None
	#: Every JAWS sound copied into ClassicSpeech (classicSounds.ImportResult), or None.
	allSounds: object = None
	rolledBack: bool = False
	error: str = ""
	reportPath: str = ""
	restartRecommended: bool = False

	@property
	def succeeded(self) -> bool:
		return not self.error and not self.rolledBack


def _stamp() -> str:
	return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _addonVersion() -> str:
	try:
		import addonHandler

		return str(addonHandler.getCodeAddon().manifest["version"])
	except Exception:
		return ""


class Migration:
	"""Carries out a plan: file work in a background thread, NVDA changes in the main thread."""

	def __init__(self, plan: MigrationPlan, progress=None, done=None):
		self.plan = plan
		self.result = MigrationResult()
		self._progress = progress or (lambda message: None)
		self._done = done or (lambda result: None)
		stamp = _stamp()
		self.result.outputFolder = nvdaEnv.addonDataDir("migrations", stamp)
		self._stagingFolder = os.path.join(self.result.outputFolder, "staging")

	# Called from the main thread.
	def start(self):
		debugLog.start(os.path.join(self.result.outputFolder, debugLog.LOG_NAME), f"Migration from {self.plan.index.jaws.displayName}")
		try:
			describePlan(self.plan)
		except Exception:
			debugLog.error("the plan could not be described")
		self._say("Saving NVDA's current settings")
		try:
			from . import nvdaApply

			nvdaApply.saveConfig()
		except Exception:
			_log().warning("jawsMigrator: could not save the configuration before the backup", exc_info=True)
		thread = threading.Thread(target=self._fileWork, name="jawsMigratorFiles", daemon=True)
		thread.start()

	def _say(self, message: str):
		debugLog.note(f"Step: {message}")
		try:
			self._progress(message)
		except Exception:
			pass

	def _later(self, function, *args):
		import wx

		wx.CallAfter(function, *args)

	# -- background thread --------------------------------------------------------------

	def _fileWork(self):
		plan = self.plan
		options = plan.options
		try:
			safety.checkWritable(self.result.outputFolder)
			os.makedirs(self.result.outputFolder, exist_ok=True)
			self._later(self._say, "Backing up NVDA's settings, add-ons and add-on settings")
			dataDir = nvdaEnv.addonDataDir()
			self.result.backup = backup.createBackup(
				nvdaEnv.configDir(),
				dataDir,
				nvdaEnv.wavesFolder(),
				f"Before migrating from {plan.index.jaws.displayName}",
				nvdaEnv.nvdaVersion(),
				_addonVersion(),
				# The very first one is kept for good: NVDA as it was before any JAWS migration.
				original=not backup.hasOriginal(dataDir),
				progress=lambda message: self._later(self._say, message),
			)
			backup.pruneBackups(dataDir, keep=15)
		except Exception as error:
			debugLog.error("backup failed")
			self.result.error = f"NVDA's settings could not be backed up, so nothing was changed. {error}"
			self._later(self._finish)
			return
		info = self.result.backup
		debugLog.note(f"Backup {info.path}: {len(info.files)} files, {info.totalSize} bytes, {info.copiedSize} copied, {len(info.addons)} add-ons, original {info.original}, skipped {info.skipped}")
		try:
			if options.archive:
				self._later(self._say, "Copying your JAWS settings into the migration archive")
				self._archive()
			if plan.classicSpeech and options.allSounds and plan.index.wavFiles():
				self._later(self._say, "Copying every JAWS sound into ClassicSpeech")
				self.result.allSounds = classicSounds.importAllSounds(plan.index.wavFiles(), nvdaEnv.configDir())
				self.result.messages.extend(self.result.allSounds.failed)
			if plan.classicSpeech and options.classicSchemes and plan.schemes:
				self._later(self._say, "Preparing JAWS sound schemes for ClassicSpeech")
				self._stageSchemeSounds()
			plan.index.writeJson(os.path.join(self.result.outputFolder, "jaws-index.json"))
			with open(os.path.join(self.result.outputFolder, "jaws-index.txt"), "w", encoding="utf-8") as stream:
				stream.write(plan.index.asText(options.scope))
		except Exception as error:
			debugLog.error("copying files failed")
			self.result.messages.append(f"Some files could not be copied: {error}")
		self._later(self._nvdaWork)

	def _archive(self):
		index = self.plan.index
		target = safety.checkWritable(os.path.join(nvdaEnv.addonDataDir("archive"), f"JAWS {index.jaws.version} {_stamp()}"))
		self.result.archiveFolder = target
		sources = []
		if self.plan.options.scope in (jawsIndex.USER, jawsIndex.BOTH):
			sources.append((index.jaws.userRoot, "Your settings"))
		if self.plan.options.scope in (jawsIndex.SHARED, jawsIndex.BOTH):
			sources.append((index.jaws.sharedSettingsDir, "Shared settings"))
		for folder, label in sources:
			if not os.path.isdir(folder):
				continue
			destination = os.path.join(target, label)
			for current, dirs, files in os.walk(folder):
				dirs[:] = [d for d in dirs if d.lower() not in ("transient-focus", "transient-session")]
				for name in files:
					path = os.path.join(current, name)
					relative = os.path.relpath(path, folder)
					if index.leasey.found and jawsDetect.hasLeaseyMarker(relative):
						continue
					try:
						copied = safety.checkWritable(os.path.join(destination, relative))
						os.makedirs(os.path.dirname(copied), exist_ok=True)
						# copyfile reads the JAWS file and writes only the copy.
						shutil.copyfile(path, copied)
					except OSError as error:
						self.result.messages.append(f"Not archived: {relative} ({error})")

	def _stageSchemeSounds(self):
		# Sounds are copied while building items in the main thread (fast); nothing heavy here yet.
		os.makedirs(self._stagingFolder, exist_ok=True)

	# -- main thread ---------------------------------------------------------------------

	def _nvdaWork(self):
		from . import nvdaApply

		try:
			self._applyEverything()
		except Exception as error:
			debugLog.error("the migration failed; restoring the backup")
			self.result.error = f"The migration stopped because of an error: {error}"
			self._rollBack()
		try:
			from . import report

			self.result.reportPath = report.writeReport(self.plan, self.result)
		except Exception:
			debugLog.error("the report could not be written")
		try:
			nvdaApply.invalidateClassicSpeechCaches()
		except Exception:
			pass
		self._finish()

	def _finish(self):
		result = self.result
		debugLog.section("Result")
		debugLog.note(f"succeeded {result.succeeded}, rolled back {result.rolledBack}, error {result.error!r}, report {result.reportPath}")
		for change, reason in result.failed:
			debugLog.note(f"not applied: {change.target} {change.key} = {change.value!r}: {reason}")
		for message in result.messages:
			debugLog.note(f"message: {message}")
		debugLog.stop()
		self._done(result)

	def _rollBack(self):
		from . import nvdaApply, state

		info = self.result.backup
		if info is None:
			return
		try:
			debugLog.section(f"Rolling back to the backup {info.path}")
			restored = backup.restoreBackup(info, nvdaEnv.configDir(), nvdaEnv.addonDataDir())
			debugLog.note(f"put back {restored.restored}; removed {restored.removed}; failed {restored.failed}")
			state.forget()
			nvdaApply.resetToSavedConfiguration()
			if restored.failed:
				# Only a complete rollback may say NVDA is as it was.
				self.result.rolledBack = False
				self.result.messages.append(
					f"Your previous NVDA settings were put back from the backup, except {len(restored.failed)} items that could not be put back: "
					+ "; ".join(restored.failed[:10])
					+ f". Use NVDA menu, Tools, JAWS Migration Assistant, Restore NVDA settings from a backup, and choose the backup from {info.label}.",
				)
			else:
				self.result.rolledBack = True
				self.result.messages.append("Your previous NVDA settings were restored from the backup.")
		except Exception as error:
			debugLog.error("restoring the backup failed")
			self.result.messages.append(
				f"Restoring the backup also failed ({error}). Use NVDA menu, Tools, JAWS Migration Assistant, "
				"Restore NVDA settings, and choose the newest backup.",
			)

	def _applyEverything(self):
		import config

		from . import nvdaApply, state

		plan = self.plan
		options = plan.options
		result = self.result
		profileName = options.profileName.strip() if options.target == TARGET_PROFILE else None
		if profileName:
			# An existing profile whose name differs only in case is the same file: write into it.
			profileName = nvdaApply.existingProfileName(profileName) or profileName
		voiceChoice = plan.chosenVoice
		globalContext = plan.globalContext
		# ClassicSpeech's settings can only be changed while it runs; the plan was made from the System Check.
		classicSpeech = plan.classicSpeech
		if classicSpeech and not nvdaApply.classicSpeechRunning():
			classicSpeech = False
			message = "ClassicSpeech isn't running in this NVDA session, so nothing was written to its settings. Enable it, restart NVDA and run the migration again for your JAWS voices, schemes and sounds."
			result.messages.append(message)
			debugLog.note(message)

		self._say("Applying JAWS settings to NVDA")
		with nvdaApply.writingTo(profileName):
			debugLog.section(f"Settings, written to {nvdaApply.writingConfigurationName()}")
			if options.settings:
				applied, failed = nvdaApply.applySettings(plan.finalSettingChanges(), None)
				result.applied.extend(applied)
				result.failed.extend(failed)
				_logApplied(applied, failed)
			synthName = nvdaApply.currentSynthName()
			baseValues = {}
			if options.voice and globalContext is not None:
				level = voices.PUNCTUATION_TO_SYMBOL_LEVEL.get(globalContext.punctuation) if globalContext.punctuation is not None else None
				if level is not None:
					try:
						nvdaApply.setValue(config.conf, ("speech", "symbolLevel"), level)
						result.applied.append(settingsMap.SettingChange(settingsMap.NVDA, ("speech", "symbolLevel"), level, f"Punctuation level: {voices.PUNCTUATION_NAMES.get(globalContext.punctuation)}", "JAWS voice profile"))
						debugLog.note(f"speech.symbolLevel = {level!r} -> {nvdaApply.writingConfigurationName()} (JAWS voice profile punctuation)")
					except Exception as error:
						result.failed.append((settingsMap.SettingChange(settingsMap.NVDA, ("speech", "symbolLevel"), level, "Punctuation level", "JAWS voice profile"), str(error)))
				if voiceChoice is not None and plan.voiceProfile is not None:
					self._say(f"Switching NVDA to {voiceChoice.label}")
					baseValues = voices.scaledVoiceSettings(plan.voiceProfile, globalContext)
					languageCode = jawsFiles.languageCodeForLcid(jawsFiles.lcidFromText(globalContext.synthLanguage)) or jawsFiles.JAWS_LANGUAGES.get(options.language, (None, None))[1]
					messages = nvdaApply.applyVoice(voiceChoice.driver, voiceChoice.voiceId or voiceChoice.voiceName, globalContext.voiceName, languageCode, baseValues)
					result.messages.extend(f"Voice: {message}" for message in messages)
					debugLog.note(f"NVDA voice {voiceChoice.label} -> {nvdaApply.writingConfigurationName()}: from JAWS {plan.voiceProfileName} Global ({globalContext.describe()}), NVDA values {baseValues}: {messages}")
					synthName = nvdaApply.currentSynthName()
			if options.voice:
				self._writeOtherVoiceProfiles()
			if options.settings:
				perSynth = [change for change in plan.settings.changes if change.perSynth]
				applied, failed = nvdaApply.applySettings(perSynth, synthName)
				result.applied.extend(applied)
				result.failed.extend(failed)
				_logApplied(applied, failed, f"{synthName}: ")
			# Everything that belongs to the synthesizer the JAWS voices now use.
			if classicSpeech and (options.classicVoices or options.classicSchemes):
				self._say("Copying JAWS voices and schemes into ClassicSpeech")
				self._writeClassicSpeech()
			if options.dictionaries:
				voiceEntries = [entry for dictionaryPlan in plan.chosenDictionaries() for entry in dictionaryPlan.voiceEntries]
				if voiceEntries and voiceChoice is not None:
					added, error = nvdaApply.addDictionaryEntries("voice", voiceEntries)
					result.voiceDictionaryEntries += added
					if error:
						result.messages.append(error)
		if classicSpeech and options.classicSettings:
			applied, failed = nvdaApply.applyClassicSpeechSettings(plan.settings.changes)
			result.applied.extend(applied)
			result.failed.extend(failed)
			for change in applied:
				debugLog.note(f"ClassicSpeech {change.key} = {change.value!r} -> ClassicSpeech's own settings ({change.label})")
			for change, reason in failed:
				debugLog.note(f"ClassicSpeech NOT SET {change.key} = {change.value!r}: {reason}")
		nvdaApply.saveConfig()

		# Settings for single applications, in profiles NVDA turns on in those programs.
		if options.appProfiles:
			for configName, why in plan.appSkipped.items():
				message = f"JAWS settings for {configName} were not made into an NVDA profile: {why}."
				result.messages.append(message)
				debugLog.note(message)
			for configName, mapping in plan.appSettings.items():
				executables = plan.appExecutables.get(configName) or []
				if executables:
					self._writeAppProfile(configName, mapping, executables)
			self._removeEmptyEarlierAppProfiles()

		# Dictionaries used by every voice.
		if options.dictionaries:
			defaultEntries = [entry for dictionaryPlan in plan.chosenDictionaries() for entry in dictionaryPlan.defaultEntries]
			if defaultEntries:
				self._say("Adding JAWS dictionary rules")
				added, error = nvdaApply.addDictionaryEntries("default", defaultEntries)
				result.dictionaryEntries += added
				if error:
					result.messages.append(error)

		# Punctuation and symbols.
		chosenSymbols = plan.chosenSymbols()
		if (options.symbols or options.jawsSymbolNames) and chosenSymbols:
			locale = nvdaApply.speechLocale()
			result.symbols = symbolMap.mergeIntoSymbolFile(nvdaApply.symbolsFile(locale), chosenSymbols if options.symbols else plan.jawsSymbolDefaults)
			nvdaApply.reloadSymbols()

		# Keyboard.
		if options.keyboard and plan.keys.bindings:
			self._say("Adding JAWS keystrokes as NVDA input gestures")
			gesturesBackup = os.path.join(nvdaEnv.configDir(), "gestures.ini")
			if os.path.isfile(gesturesBackup):
				shutil.copy2(gesturesBackup, os.path.join(self.result.outputFolder, "gestures.ini.before-migration"))
			added, failed = nvdaApply.addGestures(plan.keys.bindings)
			result.gesturesAdded = added
			debugLog.section("Input gestures")
			for binding in plan.keys.bindings:
				debugLog.note(f"{binding.gesture} -> {binding.module}.{binding.className}.{binding.script} (JAWS {binding.jawsKey}={binding.jawsScript}, [{binding.section}])")
			for binding, error in failed:
				debugLog.note(f"not added: {binding.gesture}: {error}")
			result.messages.extend(f"Gesture {binding.gesture} could not be added: {error}" for binding, error in failed)

		# JAWS sounds in place of NVDA's own, through ClassicSpeech; NVDA's files are never changed.
		if classicSpeech and options.sounds and plan.sounds:
			self._say("Playing JAWS sounds in place of NVDA's sounds, through ClassicSpeech")
			classicSounds.backupNvdaSounds(nvdaEnv.wavesFolder(), nvdaEnv.addonDataDir(), nvdaEnv.nvdaVersion())
			soundsResult = classicSounds.applyNvdaSounds(plan.sounds, nvdaEnv.configDir(), state.get(classicSounds.STATE_KEY))
			if classicSounds.enableSchemes(nvdaApply.classicSpeechSection()):
				soundsResult.record["enabledSchemes"] = True
				nvdaApply.saveConfig()
			nvdaApply.invalidateClassicSpeechCaches()
			result.nvdaSounds = soundsResult
			result.messages.extend(soundsResult.failed)

		# The assistant's own settings: sleeping applications, sounds, the JAWS profile.
		updates = {}
		if options.sleepApps:
			sleepApps = set(state.get("sleepApps") or [])
			for configName in options.sleepApps:
				# Only programs NVDA can recognize; web sites and parts of Windows were left out when planning.
				for executable in plan.appExecutables.get(configName) or []:
					sleepApps.add(executable.lower())
			updates["sleepApps"] = sorted(sleepApps)
		if result.nvdaSounds is not None:
			updates[classicSounds.STATE_KEY] = result.nvdaSounds.record
		if profileName:
			updates["jawsProfileName"] = profileName
			updates["activateJawsProfileAtStartup"] = bool(options.activateAtStartup)
		else:
			self._retireEarlierJawsProfile(updates)
		updates["lastMigration"] = {
			"when": datetime.datetime.now().isoformat(timespec="seconds"),
			"jaws": plan.index.jaws.displayName,
			"target": profileName or "normal configuration",
			"keyboardLayouts": [layout.id for layout in plan.chosenKeyboardLayouts()] if options.keyboard else [],
		}
		if result.backup is not None:
			updates["lastBackup"] = result.backup.path
		state.update(updates)
		if profileName and options.activateNow:
			nvdaApply.activateProfile(profileName)
		result.restartRecommended = bool(classicSpeech and (options.classicSchemes or options.classicSettings))

	def _writeAppProfile(self, configName: str, mapping, executables: list) -> None:
		"""Write one application's JAWS settings into its own profile, and have NVDA turn it on in that program.

		A profile that ends up holding nothing (every value the same as the normal configuration's)
		only switches NVDA's profiles for nothing, so it is deleted and gets no trigger. A trigger that
		turns on another existing profile is the user's, and is left as it is.
		"""
		from . import nvdaApply

		result = self.result
		appProfile = f"{APP_PROFILE_PREFIX}{configName}"
		appProfile = nvdaApply.existingProfileName(appProfile) or appProfile
		with nvdaApply.writingTo(appProfile):
			debugLog.section(f"Settings for {configName}, written to {nvdaApply.writingConfigurationName()}")
			applied, failed = nvdaApply.applySettings(mapping.changes, None)
			_logApplied(applied, failed, f"{configName}: ")
		result.failed.extend(failed)
		if not nvdaApply.profileHoldsSettings(appProfile):
			removed = nvdaApply.deleteProfile(appProfile)
			message = f"The JAWS settings for {configName} are the same as NVDA's normal configuration, so it needs no profile of its own"
			message += f'; the empty profile "{appProfile}" was removed.' if removed else f'. The empty profile "{appProfile}" could not be removed; delete it in NVDA\'s Configuration Profiles dialog.'
			result.messages.append(message)
			debugLog.note(message)
			return
		turnsOn = []
		for executable in executables:
			outcome, detail = nvdaApply.setProfileTrigger(executable, appProfile)
			if outcome == nvdaApply.TRIGGER_SET:
				turnsOn.append(executable)
				continue
			if outcome == nvdaApply.TRIGGER_KEPT:
				message = (
					f'NVDA already turns on your profile "{detail}" in {executable}, so that was left as it is, and "{appProfile}" '
					"does not turn on there by itself. Turn it on by hand, or change the trigger in NVDA's Configuration Profiles dialog."
				)
			else:
				message = f'"{appProfile}" could not be set to turn on in {executable}: {detail}'
			result.messages.append(message)
			debugLog.note(message)
		debugLog.note(f"profile {appProfile}: {len(applied)} settings; turns on in {turnsOn or 'no program'}")
		result.appProfiles.append((appProfile, turnsOn, len(applied)))

	def _removeEmptyEarlierAppProfiles(self) -> None:
		"""Delete the empty "JAWS - program" profiles earlier migrations left, so NVDA stops switching to them.

		Versions 1.0 to 1.2 made a profile for every JAWS application file, even one holding nothing NVDA
		uses, and for web sites and parts of Windows that can never turn a profile on. Each switch makes
		NVDA and its synthesizer reload their settings for nothing. Only empty profiles are deleted, with
		their triggers; a profile holding any setting is kept. All of them are in the backup.
		"""
		from . import nvdaApply

		written = {name.lower() for name, *_rest in self.result.appProfiles}
		removed = []
		for name in nvdaEnv.profileNames():
			if not name.startswith(APP_PROFILE_PREFIX) or name.lower() in written:
				continue
			if nvdaApply.profileHoldsSettings(name):
				continue
			if nvdaApply.deleteProfile(name):
				removed.append(name)
		if removed:
			message = (
				f"{len(removed)} empty profiles from an earlier migration were removed, so NVDA no longer switches to them "
				f"for nothing: {', '.join(removed)}."
			)
			self.result.messages.append(message)
			debugLog.note(message)

	def _retireEarlierJawsProfile(self, updates: dict) -> None:
		"""The JAWS settings now go into the normal configuration: an earlier JAWS profile stops turning on at startup.

		NVDA has one manually activated profile at a time. One turned on at startup hides the normal
		configuration's JAWS settings, and it is itself replaced as soon as an add-on or the user turns
		on another profile by hand. The profile is kept: it is in the backup, and the user can delete it.
		"""
		from . import nvdaApply, state

		earlier = str(state.get("jawsProfileName") or "")
		if not earlier:
			return
		existing = nvdaApply.existingProfileName(earlier)
		active = existing is not None and nvdaApply.activeManualProfile() == existing
		if state.get("activateJawsProfileAtStartup"):
			updates["activateJawsProfileAtStartup"] = False
			turnedOff = active and nvdaApply.activateProfile(None)
			message = f'Your JAWS settings are now in NVDA\'s normal configuration, so the profile "{earlier}" from an earlier migration no longer turns on when NVDA starts'
			message += ", and it was turned off now." if turnedOff else "."
			if existing is not None:
				message += " The profile itself is kept, and it is in the backup; delete it in NVDA's Configuration Profiles dialog if you no longer want it."
		elif active:
			message = (
				f'NVDA is using the profile "{existing}" right now, which may hold other values for the settings just migrated. '
				"Turn it off with NVDA+Shift+J then P, or in NVDA's Configuration Profiles dialog, to use your JAWS settings."
			)
		else:
			return
		self.result.messages.append(message)
		debugLog.note(message)

	def _writeClassicSpeech(self):
		import synthDriverHandler

		from . import classicSpeechWriter, nvdaApply

		plan = self.plan
		options = plan.options
		result = self.result
		facts = plan.facts
		section = nvdaApply.classicSpeechSection()
		synth = synthDriverHandler.getSynth()
		descriptions = {driver.lower(): description for driver, description in facts.synths}
		debugLog.section("ClassicSpeech: voices (the person only) and schemes")
		resolvers = []
		for profilePlan in plan.selectedProfiles():
			option = profilePlan.option
			globalContext = profilePlan.contexts.get("Global")
			if profilePlan.primary and synth is not None and synth.name.lower() == option.driver.lower():
				resolver = classicSpeechWriter.LiveVoiceResolver(synth, profilePlan.synth)
			else:
				knownVoices, knownVariants = voices.knownVoices(option.driver, facts.sapiVoices, facts.oneCoreVoices, facts.speechPlatformVoices)
				resolver = classicSpeechWriter.VoiceResolver(
					option.driver,
					descriptions.get(option.driver.lower(), option.driverDescription),
					profilePlan.synth,
					knownVoices,
					knownVariants,
				)
				resolver.currentVoice, resolver.currentVariant = resolver.person(globalContext.voiceName if globalContext else "")
			debugLog.note(f"JAWS {profilePlan.name} -> {resolver.driverName}: NVDA speaks with voice {resolver.currentVoice!r}, variant {resolver.currentVariant!r}")
			aliases = profilePlan.aliases
			if options.voiceAliases is not None:
				wanted = {name.lower() for name in options.voiceAliases}
				aliases = {name: value for name, value in aliases.items() if name.lower() in wanted}
			resolvers.append((resolver, aliases))
			if options.classicVoices:
				records = {}
				for category, context in voices.CLASSIC_SPEECH_CONTEXTS.items():
					voiceContext = profilePlan.contexts.get(context)
					if voiceContext is None:
						continue
					record, note = resolver.contextRecord(voiceContext)
					debugLog.note(f"  Voice Profile {category}, from JAWS {context} ({voiceContext.describe()}): {'person ' + note if record else 'nothing written: ' + note}")
					if record is None:
						continue
					records[category] = record
					result.voiceProfilesWritten.append((f"{profilePlan.name} -> {resolver.driverDescription}: {category}", context, note))
				if records:
					classicSpeechWriter.writeVoiceProfiles(section, resolver.driverName, records)
					classicSpeechWriter.writeVoicesFile(
						os.path.join(result.outputFolder, f"JAWS {classicSpeechWriter.folderNameFor(profilePlan.name)} voice profiles ({resolver.driverName}).classicspeech-voices"),
						resolver.driverName,
						records,
					)
		if options.classicSchemes and plan.schemes:
			schemesRoot = os.path.join(nvdaEnv.configDir(), "ClassicSpeech", "Schemes")
			for converted in plan.selectedSchemes():
				soundsFolder = os.path.join(self._stagingFolder, classicSpeechWriter.folderNameFor(converted.name), "Sounds")
				os.makedirs(soundsFolder, exist_ok=True)
				items, notes = classicSpeechWriter.buildSchemeItems(converted, resolvers, soundsFolder)
				folder = classicSpeechWriter.writeSchemeFolder(schemesRoot, converted.name, items, soundsFolder)
				classicSpeechWriter.writeSchemePackage(
					os.path.join(result.outputFolder, classicSpeechWriter.folderNameFor(converted.name) + ".classicspeech-scheme"),
					converted.name,
					items,
					soundsFolder,
				)
				if not items:
					notes = notes + ["JAWS speaks everything normally in this scheme, so it changes nothing in ClassicSpeech."]
				debugLog.note(f"Scheme {converted.name}: {len(items)} items written to {folder}")
				result.schemesWritten.append((converted.name, len(items), folder, notes))
		active = options.activeClassicScheme
		if active and any(name == active for name, *_rest in result.schemesWritten):
			# Only ever because the user chose it.
			classicSpeechWriter.setSchemeSwitches(section, active, enable=True)
			debugLog.note(f"The user chose to turn on the scheme {active} in ClassicSpeech")
		else:
			debugLog.note("No ClassicSpeech scheme was turned on: ClassicSpeech stays as it was")
		shutil.rmtree(self._stagingFolder, ignore_errors=True)

	def _writeOtherVoiceProfiles(self):
		"""Save every other selected JAWS voice profile as NVDA's settings for its synthesizer."""
		from . import classicSpeechWriter

		plan = self.plan
		facts = plan.facts
		descriptions = {driver.lower(): description for driver, description in facts.synths}
		for profilePlan in plan.selectedProfiles():
			if profilePlan.primary:
				continue
			option = profilePlan.option
			globalContext = profilePlan.contexts.get("Global")
			if globalContext is None:
				continue
			values = voices.scaledVoiceSettings(profilePlan.profile, globalContext)
			knownVoices, knownVariants = voices.knownVoices(option.driver, facts.sapiVoices, facts.oneCoreVoices, facts.speechPlatformVoices)
			resolver = classicSpeechWriter.VoiceResolver(
				option.driver,
				descriptions.get(option.driver.lower(), option.driverDescription),
				profilePlan.synth,
				knownVoices,
				knownVariants,
			)
			self._writeSynthSettings(resolver, profilePlan, option, values)

	def _writeSynthSettings(self, resolver, profilePlan, option, values: dict):
		"""NVDA's own settings for a synthesizer that is not loaded, from a JAWS voice profile.

		They take effect whenever NVDA is switched to that synthesizer.
		"""
		from . import nvdaApply

		import config

		globalContext = profilePlan.contexts.get("Global")
		voiceId, variantId = resolver.person(globalContext.voiceName if globalContext else "")
		if option.voiceId:
			voiceId = option.voiceId
		changes = dict(values)
		if voiceId:
			changes["voice"] = voiceId
		if variantId:
			changes["variant"] = variantId
		written = []
		for key, value in changes.items():
			try:
				nvdaApply.setValue(config.conf, ("speech", option.driver, key), value)
				written.append(f"{key} {value}")
			except Exception as error:
				self.result.messages.append(f"{profilePlan.name}: {option.driver} {key} could not be set ({error})")
		if written:
			self.result.messages.append(f"JAWS {profilePlan.name} voice profile saved as NVDA's {resolver.driverDescription} settings: " + ", ".join(written))
			debugLog.note(f"speech.{option.driver}: {', '.join(written)} -> {nvdaApply.writingConfigurationName()} (JAWS voice profile {profilePlan.name})")


def restoreLatestBackup() -> str:
	"""Restore the newest backup. Main thread only. Returns what happened."""
	backups = backup.listBackups(nvdaEnv.addonDataDir())
	if not backups:
		return "There is no backup to restore."
	return restore(backups[0]).message


@dataclass
class RestoreOutcome:
	message: str
	#: Add-ons were changed; NVDA finishes that when it restarts.
	restartNeeded: bool = False
	failed: list = field(default_factory=list)


def restore(info: backup.BackupInfo) -> RestoreOutcome:
	"""Put a backup back: NVDA's settings, add-ons and add-on settings. Main thread only.

	The current settings and add-ons are backed up first, so the restore can be undone; settings
	changed in this session and not saved yet are saved first, so the backup has them too. The file
	work runs in the background while NVDA keeps responding; then NVDA reloads its settings. Only
	after that are the add-on changes recorded, so NVDA finishes them when it restarts, never while
	those add-ons run.
	"""
	from . import nvdaApply, state

	manager = nvdaApply.addonManager()
	try:
		nvdaApply.saveConfig()
	except Exception:
		debugLog.error("NVDA's settings could not be saved before the restore")

	def work():
		before = backup.createBackup(
			nvdaEnv.configDir(),
			nvdaEnv.addonDataDir(),
			"",
			f"Before restoring the backup from {info.label}",
			nvdaEnv.nvdaVersion(),
			_addonVersion(),
		)
		# Files only; add-ons come after NVDA has reloaded its settings (below).
		return before, backup.restoreBackup(info, nvdaEnv.configDir(), nvdaEnv.addonDataDir())

	debugLog.section(f"Restoring the backup {info.path}")
	before, result = nvdaApply.runWithProgress(work, "Restoring NVDA's settings. Please wait.")
	debugLog.note(f"safety backup {before.path}; put back {result.restored}; removed {result.removed}; failed {result.failed}")
	state.forget()
	nvdaApply.resetToSavedConfiguration()
	if info.version >= 2:
		try:
			nvdaApply.runWithProgress(lambda: backup.restoreAddons(info, manager, result), "Putting NVDA's add-ons back as they were. Please wait.")
		except Exception as error:
			debugLog.error("the add-ons could not be put back")
			result.failed.append(f"add-ons: {error}")
		debugLog.note(f"add-ons, finished when NVDA restarts: {[(action.name, action.kind) for action in result.addonActions]}; failed {result.failed}")
	lines = [f"Put back {len(result.restored)} files and removed {len(result.removed)} from the backup of {info.label}."]
	if info.version < 2:
		lines.append("That backup holds NVDA's settings only, so add-ons were not changed.")
	elif result.addonActions:
		lines.append("Add-ons, finished when NVDA restarts: " + "; ".join(action.description for action in result.addonActions) + ".")
	else:
		lines.append("Your add-ons were already as they were in the backup.")
	if result.failed:
		lines.append(f"{len(result.failed)} items could not be put back: " + "; ".join(result.failed[:5]) + ".")
	lines.append(f"Your settings and add-ons from before the restore were saved as the backup {before.name}, so this can be undone.")
	return RestoreOutcome(" ".join(lines), result.restartNeeded, result.failed)


# -- JAWS sounds through ClassicSpeech, outside a migration ----------------------------------


@dataclass
class SoundsOutcome:
	message: str
	succeeded: bool = True


def soundsProblem(facts: systemCheck.SystemFacts) -> str:
	"""Why JAWS sounds can't be used on this computer, or "" when they can."""
	info = facts.classicSpeech
	if not info.installed:
		return (
			"JAWS sounds play through ClassicSpeech, which is not installed. Install ClassicSpeech "
			"(https://github.com/joshknnd1982/classicspeech-nvda), restart NVDA, then try again. Nothing was changed."
		)
	if not info.usable:
		return (
			"JAWS sounds play through ClassicSpeech, which is installed but isn't running in this NVDA session "
			"(it is disabled, being removed, incompatible, or waiting for NVDA to restart). Enable it in NVDA's Add-on Store, "
			"restart NVDA, then try again. Nothing was changed."
		)
	if not (facts.jawsWithSettings or facts.jaws):
		return "No JAWS settings were found on this computer, so there are no JAWS sounds to use. Nothing was changed."
	return ""


def _jawsIndexFor(facts: systemCheck.SystemFacts) -> jawsIndex.JawsIndex:
	jaws = (facts.jawsWithSettings or facts.jaws)[0]
	language = jaws.primaryLanguage or (jaws.settingsLanguages[0] if jaws.settingsLanguages else "enu")
	return jawsIndex.buildIndex(jaws, language, facts.leasey)


def _backupFirst(reason: str) -> backup.BackupInfo:
	dataDir = nvdaEnv.addonDataDir()
	info = backup.createBackup(
		nvdaEnv.configDir(),
		dataDir,
		nvdaEnv.wavesFolder(),
		reason,
		nvdaEnv.nvdaVersion(),
		_addonVersion(),
		original=not backup.hasOriginal(dataDir),
	)
	backup.pruneBackups(dataDir, keep=15)
	return info


def useJawsSounds(facts: systemCheck.SystemFacts) -> SoundsOutcome:
	"""Play JAWS sounds in place of NVDA's own, through ClassicSpeech. Main thread only.

	NVDA's settings, add-ons and add-on settings are backed up first, and NVDA's own sounds are
	copied; the file work runs in the background while NVDA keeps responding.
	"""
	from . import nvdaApply, state

	problem = soundsProblem(facts)
	if problem:
		return SoundsOutcome(problem, False)
	if not nvdaApply.classicSpeechRunning():
		# The System Check may be a few minutes old; ClassicSpeech's settings can only change while it runs.
		return SoundsOutcome("JAWS sounds play through ClassicSpeech, which isn't running in this NVDA session. Enable it in NVDA's Add-on Store, restart NVDA, then try again. Nothing was changed.", False)
	earlier = state.get(classicSounds.STATE_KEY) or {}

	def work():
		index = _jawsIndexFor(facts)
		choices, missing = classicSounds.soundChoices(index)
		if not choices:
			raise OSError("none of the JAWS sounds for NVDA's sounds were found")
		before = _backupFirst("Before playing JAWS sounds in place of NVDA's sounds")
		copies = classicSounds.backupNvdaSounds(nvdaEnv.wavesFolder(), nvdaEnv.addonDataDir(), nvdaEnv.nvdaVersion())
		return before, copies, missing, classicSounds.applyNvdaSounds(choices, nvdaEnv.configDir(), earlier)

	debugLog.section("Using JAWS sounds in place of NVDA's")
	before, copies, missing, result = nvdaApply.runWithProgress(work, "Setting up JAWS sounds for NVDA. Please wait.")
	record = result.record
	turnedOn = classicSounds.enableSchemes(nvdaApply.classicSpeechSection())
	if turnedOn:
		record["enabledSchemes"] = True
	# JAWS plays no sound when it starts or exits; neither does NVDA while it uses JAWS sounds.
	if nvdaApply.getValue(("general", "playStartAndExitSounds")) is True:
		nvdaApply.setValue(__import__("config").conf, ("general", "playStartAndExitSounds"), False)
		record["startExitSounds"] = True
	debugLog.note(f"backup {before.path}; NVDA's sounds copied to {copies}; schemes {result.schemes}; added {result.added}; kept {result.kept}; failed {result.failed}; missing {missing}; ClassicSpeech schemes turned on {turnedOn}; start and exit sounds turned off {bool(record.get('startExitSounds'))}")
	state.set(classicSounds.STATE_KEY, record)
	nvdaApply.invalidateClassicSpeechCaches()
	nvdaApply.saveConfig()
	sounds = record.get("sounds") or {}
	lines = [f"JAWS sounds now play in place of {len(sounds)} of NVDA's sounds, through {len(result.schemes)} ClassicSpeech schemes. For example, focus mode plays {sounds.get('focusMode', 'a JAWS sound')} and browse mode {sounds.get('browseMode', 'a JAWS sound')}."]
	if record.get("startExitSounds"):
		lines.append("NVDA no longer plays sounds when it starts or exits, as JAWS plays none.")
	if turnedOn:
		lines.append("ClassicSpeech's speech and sound schemes were turned on, as JAWS sounds need them.")
	if result.kept:
		lines.append(f"{len(result.kept)} NVDA sounds that a scheme already had its own sound for were left as they are.")
	if missing or result.failed:
		lines.append("Not used: " + "; ".join((missing + result.failed)[:5]) + ".")
	lines.append(f"NVDA's own sound files are never changed; a copy of them is in {copies}. NVDA's settings and add-ons were backed up first, as {before.name}.")
	lines.append("To hear NVDA's own sounds again, press NVDA+Shift+J then S, or use NVDA menu, Tools, JAWS Migration Assistant, Restore NVDA's own sounds.")
	return SoundsOutcome(" ".join(lines))


def restoreNvdaSounds() -> SoundsOutcome:
	"""Take out the JAWS sounds the assistant gave ClassicSpeech's schemes, so NVDA plays its own again. Main thread only."""
	from . import nvdaApply, state

	record = state.get(classicSounds.STATE_KEY) or {}
	if not classicSounds.isApplied(record):
		return SoundsOutcome("NVDA already plays its own sounds; the assistant hasn't set up JAWS sounds for them.", False)
	running = nvdaApply.classicSpeechRunning()
	if nvdaEnv.classicSpeechInfo().installed and not running:
		# Its switch is in its settings, which can only be changed while it runs; half a restore would leave it on.
		return SoundsOutcome(
			"ClassicSpeech is installed but isn't running in this NVDA session (it is disabled, incompatible, or waiting for NVDA to restart), "
			"so NVDA's own sounds can't be put back yet. Nothing was changed. JAWS sounds only play through ClassicSpeech, so they don't play "
			"while it isn't running. When it runs again, use Restore NVDA's own sounds.",
			False,
		)
	configDir = nvdaEnv.configDir()

	def work():
		before = _backupFirst("Before restoring NVDA's own sounds")
		return before, classicSounds.restoreNvdaSounds(configDir, record)

	debugLog.section("Restoring NVDA's own sounds")
	before, result = nvdaApply.runWithProgress(work, "Restoring NVDA's own sounds. Please wait.")
	turnedOff = False
	if record.get("enabledSchemes") and running:
		turnedOff = classicSounds.disableSchemes(nvdaApply.classicSpeechSection())
	startExitBack = False
	if record.get("startExitSounds") and nvdaApply.getValue(("general", "playStartAndExitSounds")) is False:
		nvdaApply.setValue(__import__("config").conf, ("general", "playStartAndExitSounds"), True)
		startExitBack = True
	# What could not be taken out (a scheme that couldn't be written) stays recorded, so a later restore finishes it.
	remaining = _soundsStillApplied(configDir, record)
	debugLog.note(f"backup {before.path}; schemes {result.schemes}; removed {result.removed}; kept {result.kept}; failed {result.failed}; ClassicSpeech schemes turned off {turnedOff}; start and exit sounds back {startExitBack}; still applied {sorted(remaining.get('schemes', {}))}")
	state.set(classicSounds.STATE_KEY, remaining)
	nvdaApply.invalidateClassicSpeechCaches()
	nvdaApply.saveConfig()
	if classicSounds.isApplied(remaining):
		lines = [
			f"JAWS sounds were taken out of {len(result.schemes)} ClassicSpeech schemes, but not out of "
			+ ", ".join(entry.get("name") or folder for folder, entry in remaining["schemes"].items())
			+ ", which could not be changed. Try Restore NVDA's own sounds again later.",
		]
	else:
		lines = [f"NVDA's own sounds are back: JAWS sounds were taken out of {len(result.schemes)} ClassicSpeech schemes."]
	if turnedOff:
		lines.append("ClassicSpeech's speech and sound schemes are off again, as they were before.")
	if startExitBack:
		lines.append("NVDA plays its sounds when it starts and exits again.")
	if result.kept:
		lines.append(f"Left as you changed them in ClassicSpeech: {', '.join(result.kept[:6])}" + (f" and {len(result.kept) - 6} more." if len(result.kept) > 6 else "."))
	if result.failed:
		lines.append("; ".join(result.failed[:5]) + ".")
	lines.append(f"NVDA's settings and add-ons were backed up first, as {before.name}.")
	return SoundsOutcome(" ".join(lines), not classicSounds.isApplied(remaining))


def _soundsStillApplied(configDir: str, record) -> dict:
	"""The part of a JAWS sounds record still in ClassicSpeech's schemes after a restore, or {}.

	These are items exactly as the assistant gave them (same place, same sound), which a restore
	takes out unless the scheme could not be written. Items the user changed, and schemes renamed or
	deleted since, are the user's now and are not kept.
	"""
	record = classicSounds._cleanRecord(record)
	root = classicSounds.schemesRoot(configDir)
	current = {folderName: (schemeName, data) for folderName, schemeName, data in classicSounds.schemeFolders(root)}
	byName = {schemeName.lower(): folderName for folderName, (schemeName, _data) in current.items()}
	remaining = {}
	for folderName, entry in record["schemes"].items():
		recordedName = str(entry.get("name") or "")
		target = folderName if folderName in current and (not recordedName or current[folderName][0].lower() == recordedName.lower()) else None
		target = target or byName.get(recordedName.lower())
		if target is None:
			continue
		folder = os.path.join(root, target)
		items = current[target][1]["items"]
		still = {}
		for itemId, added in entry["items"].items():
			settings = items.get(itemId)
			if not isinstance(settings, dict) or not settings.get("sound") or not isinstance(added, dict):
				continue
			voice = settings.get("voice") if isinstance(settings.get("voice"), dict) else {}
			path = classicSounds._soundPath(folder, settings["sound"])
			if voice.get("enabled") or os.path.normcase(path) != os.path.normcase(classicSounds._soundPath(folder, added.get("sound"))):
				continue
			try:
				unchanged = os.path.isfile(path) and bool(added.get("sha256")) and classicSounds._sha256(path) == added["sha256"]
			except OSError:
				unchanged = False
			if unchanged:
				still[itemId] = added
		if still:
			remaining[target] = dict(entry, items=still)
	if not remaining:
		return {}
	return {key: value for key, value in record.items() if key not in ("schemes", "enabledSchemes", "startExitSounds")} | {"schemes": remaining}


def copyAllJawsSounds(facts: systemCheck.SystemFacts) -> SoundsOutcome:
	"""Copy every JAWS sound into ClassicSpeech, as the scheme JAWS Sounds (from JAWS). Main thread only."""
	from . import nvdaApply

	problem = soundsProblem(facts)
	if problem:
		return SoundsOutcome(problem, False)

	def work():
		index = _jawsIndexFor(facts)
		wavFiles = index.wavFiles()
		if not wavFiles:
			raise OSError("no JAWS sound files were found")
		before = _backupFirst("Before copying every JAWS sound into ClassicSpeech")
		return before, classicSounds.importAllSounds(wavFiles, nvdaEnv.configDir())

	debugLog.section("Copying every JAWS sound into ClassicSpeech")
	before, result = nvdaApply.runWithProgress(work, "Copying every JAWS sound into ClassicSpeech. Please wait.")
	nvdaApply.invalidateClassicSpeechCaches()
	debugLog.note(f"backup {before.path}; {result.sounds} sounds in {result.folder}, {result.converted} converted, failed {result.failed}")
	lines = [f"{result.sounds} JAWS sounds are now in ClassicSpeech, in the scheme {classicSounds.JAWS_SOUNDS_SCHEME}, folder {os.path.join(result.folder, classicSounds.SOUNDS_FOLDER)}."]
	if result.converted:
		lines.append(f"{result.converted} were converted so NVDA can play them.")
	if result.failed:
		lines.append(f"{len(result.failed)} could not be copied: " + "; ".join(result.failed[:5]) + ".")
	lines.append(f"Choose them for any item in ClassicSpeech's Speech and Sound Schemes. NVDA's settings and add-ons were backed up first, as {before.name}.")
	return SoundsOutcome(" ".join(lines), result.sounds > 0)


def _configuredVoice(synthName: str) -> dict | None:
	"""NVDA's saved voice and variant for a synthesizer, or None when it has none."""
	try:
		import config

		section = config.conf["speech"][synthName]
	except Exception:
		return None
	values = {}
	for key in ("voice", "variant"):
		try:
			values[key] = section[key]
		except Exception:
			pass
	return values


def callOnce(function):
	"""A function that calls ``function`` (if any) the first time it is called, and never again."""
	called = []

	def wrapper():
		if called or function is None:
			return
		called.append(True)
		function()

	return wrapper


def repairClassicSpeechVoices(announce, done=None) -> None:
	"""Once, after updating from versions 1.0 to 1.2: take the fixed rate, pitch and volume out of the
	ClassicSpeech voices those versions wrote, after a backup. Main thread; the backup runs in the background.
	``done()`` is called on the main thread when the repair is over, whether or not it did anything.
	"""
	finished = callOnce(done)
	started = False
	try:
		started = _repairClassicSpeechVoices(announce, finished)
	finally:
		if not started:
			finished()


def _repairClassicSpeechVoices(announce, finished) -> bool:
	"""Start the repair; True when a backup started in the background, which calls ``finished`` at its end."""
	from . import classicRepair, nvdaApply, state

	if state.get(classicRepair.STATE_KEY) == classicRepair.REPAIR_VERSION or not nvdaEnv.shouldWriteToDisk():
		return False
	if not nvdaEnv.classicSpeechInfo().installed:
		state.set(classicRepair.STATE_KEY, classicRepair.REPAIR_VERSION)
		return False
	if not nvdaApply.classicSpeechRunning():
		# Its Voice Profiles are in its settings, which can only be read and changed while it runs.
		debugLog.note("ClassicSpeech isn't running, so its voices are repaired the next time NVDA starts with it running")
		return False
	configDir = nvdaEnv.configDir()
	schemes = classicRepair.schemesNeedingRepair(configDir)
	profiles = classicRepair.voiceProfilesNeedingRepair(nvdaApply.classicSpeechSection())
	if not schemes and not profiles:
		state.set(classicRepair.STATE_KEY, classicRepair.REPAIR_VERSION)
		return False
	debugLog.section("Repairing the ClassicSpeech voices of an earlier migration")
	debugLog.note(f"schemes {schemes}; Voice Profiles to repair {profiles}")

	def finish(outcome):
		try:
			_finishVoicesRepair(outcome)
		finally:
			finished()

	def _finishVoicesRepair(outcome):
		if isinstance(outcome, Exception):
			debugLog.note(f"the backup failed, so nothing was repaired; it is tried again next time NVDA starts: {outcome}")
			return
		result = classicRepair.RepairResult()
		try:
			classicRepair.repairSchemes(configDir, _configuredVoice, result, debugLog.note)
			classicRepair.repairVoiceProfiles(nvdaApply.classicSpeechSection(), _configuredVoice, result, debugLog.note)
			nvdaApply.invalidateClassicSpeechCaches()
			nvdaApply.saveConfig()
		except Exception:
			debugLog.error("the ClassicSpeech voices could not be repaired")
			return
		state.set(classicRepair.STATE_KEY, classicRepair.REPAIR_VERSION)
		debugLog.note(f"repaired {result.items} scheme voices in {result.schemes} and Voice Profiles {result.voiceProfiles}; failed {result.failed}; backup {outcome.path}")
		if result.changed:
			announce(
				"JAWS Migration Assistant repaired the ClassicSpeech voices from your earlier JAWS migration: "
				"they now keep your NVDA rate, pitch and volume, so speech stays even.",
			)

	def work():
		try:
			outcome = _backupFirst("Before repairing the ClassicSpeech voices of an earlier migration")
		except Exception as error:
			debugLog.error("the backup before the repair failed")
			outcome = error
		import wx

		wx.CallAfter(finish, outcome)

	threading.Thread(target=work, name="jawsMigratorRepair", daemon=True).start()
	return True


def recommendedAddonStates(facts: systemCheck.SystemFacts) -> list:
	"""``(StoreAddon, AddonState or None)`` for each add-on the assistant recommends."""
	return [(addon, nvdaEnv.addonState(addon.addonId, facts.addons)) for addon in managers.RECOMMENDED_ADDONS]
