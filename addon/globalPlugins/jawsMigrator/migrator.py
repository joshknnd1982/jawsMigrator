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
import shutil
import threading
from dataclasses import dataclass, field

from . import (
	backup,
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
	target: str = TARGET_PROFILE
	profileName: str = DEFAULT_PROFILE_NAME
	activateAtStartup: bool = True
	activateNow: bool = True
	settings: bool = True
	appProfiles: bool = True
	sleepApps: list = field(default_factory=list)
	voice: bool = True
	#: Index into the plan's voice options; -1 keeps NVDA's synthesizer and voice.
	voiceChoice: int = 0
	classicVoices: bool = True
	classicSchemes: bool = True
	classicSettings: bool = True
	#: Name of the converted scheme to turn on in ClassicSpeech, or "" to leave its choice alone.
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
	sounds: bool = False
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
	appSettings: dict = field(default_factory=dict)
	appExecutables: dict = field(default_factory=dict)
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


def _configExecutables(index: jawsIndex.JawsIndex, configName: str) -> list[str]:
	names = index.configNames().get(configName.lower(), [])
	return names or [configName.lower()]


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

	# Settings Center, for all applications.
	plan.settings = settingsMap.mapSettings(source, merged, classicSpeech=classic, userKeys=_userKeys(index))

	# Settings for single applications: only the user's own, never JAWS's stock application files.
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
			plan.appExecutables[configName] = _configExecutables(index, configName)
			if result.sleepMode:
				plan.sleepCandidates.append((configName, plan.appExecutables[configName]))
			if [change for change in result.changes if change.target == settingsMap.NVDA]:
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
		if not options.activeClassicScheme:
			for converted in plan.schemes:
				if converted.title.lower() == plan.jawsActiveScheme.lower():
					options.activeClassicScheme = converted.name

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
			userIni = jawsFiles.readIni(userFile.path)
			sharedIni = jawsFiles.readIni(sharedFile.path) if sharedFile else jawsFiles.IniFile()
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
				ini = jawsFiles.readIni(shared.path)
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
	)
	plan.keys.applicationKeys = applicationKeys


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
	soundsCopied: list = field(default_factory=list)
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
		self._say("Saving NVDA's current settings")
		try:
			from . import nvdaApply

			nvdaApply.saveConfig()
		except Exception:
			_log().warning("jawsMigrator: could not save the configuration before the backup", exc_info=True)
		thread = threading.Thread(target=self._fileWork, name="jawsMigratorFiles", daemon=True)
		thread.start()

	def _say(self, message: str):
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
			_log().exception("jawsMigrator: backup failed")
			self.result.error = f"NVDA's settings could not be backed up, so nothing was changed. {error}"
			self._later(self._done, self.result)
			return
		try:
			if options.archive:
				self._later(self._say, "Copying your JAWS settings into the migration archive")
				self._archive()
			if options.sounds and plan.sounds:
				self._later(self._say, "Copying JAWS sounds")
				self._copySounds()
			if plan.classicSpeech and options.classicSchemes and plan.schemes:
				self._later(self._say, "Preparing JAWS sound schemes for ClassicSpeech")
				self._stageSchemeSounds()
			plan.index.writeJson(os.path.join(self.result.outputFolder, "jaws-index.json"))
			with open(os.path.join(self.result.outputFolder, "jaws-index.txt"), "w", encoding="utf-8") as stream:
				stream.write(plan.index.asText(options.scope))
		except Exception as error:
			_log().exception("jawsMigrator: copying files failed")
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

	def _copySounds(self):
		from . import wavUtil

		folder = nvdaEnv.addonDataDir("sounds")
		os.makedirs(folder, exist_ok=True)
		for choice in self.plan.sounds:
			destination = os.path.join(folder, choice.event.nvdaName + ".wav")
			try:
				how = wavUtil.copyPlayable(choice.jawsPath, destination)
				self.result.soundsCopied.append((choice, destination, how))
			except (OSError, wavUtil.WavError) as error:
				self.result.messages.append(f"{choice.event.label}: {choice.jawsName} could not be used ({error})")

	def _stageSchemeSounds(self):
		# Sounds are copied while building items in the main thread (fast); nothing heavy here yet.
		os.makedirs(self._stagingFolder, exist_ok=True)

	# -- main thread ---------------------------------------------------------------------

	def _nvdaWork(self):
		from . import nvdaApply

		try:
			self._applyEverything()
		except Exception as error:
			_log().exception("jawsMigrator: the migration failed; restoring the backup")
			self.result.error = f"The migration stopped because of an error: {error}"
			self._rollBack()
		try:
			from . import report

			self.result.reportPath = report.writeReport(self.plan, self.result)
		except Exception:
			_log().exception("jawsMigrator: the report could not be written")
		try:
			nvdaApply.invalidateClassicSpeechCaches()
		except Exception:
			pass
		self._done(self.result)

	def _rollBack(self):
		from . import nvdaApply, state

		info = self.result.backup
		if info is None:
			return
		try:
			backup.restoreBackup(info, nvdaEnv.configDir(), nvdaEnv.addonDataDir())
			state.forget()
			nvdaApply.resetToSavedConfiguration()
			self.result.rolledBack = True
			self.result.messages.append("Your previous NVDA settings were restored from the backup.")
		except Exception as error:
			_log().exception("jawsMigrator: restoring the backup failed")
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
		voiceChoice = plan.chosenVoice
		globalContext = plan.globalContext

		self._say("Applying JAWS settings to NVDA")
		with nvdaApply.writingTo(profileName):
			if options.settings:
				applied, failed = nvdaApply.applySettings(plan.finalSettingChanges(), None)
				result.applied.extend(applied)
				result.failed.extend(failed)
			synthName = nvdaApply.currentSynthName()
			baseValues = {}
			if options.voice and globalContext is not None:
				level = voices.PUNCTUATION_TO_SYMBOL_LEVEL.get(globalContext.punctuation) if globalContext.punctuation is not None else None
				if level is not None:
					try:
						nvdaApply.setValue(config.conf, ("speech", "symbolLevel"), level)
						result.applied.append(settingsMap.SettingChange(settingsMap.NVDA, ("speech", "symbolLevel"), level, f"Punctuation level: {voices.PUNCTUATION_NAMES.get(globalContext.punctuation)}", "JAWS voice profile"))
					except Exception as error:
						result.failed.append((settingsMap.SettingChange(settingsMap.NVDA, ("speech", "symbolLevel"), level, "Punctuation level", "JAWS voice profile"), str(error)))
				if voiceChoice is not None and plan.voiceProfile is not None:
					self._say(f"Switching NVDA to {voiceChoice.label}")
					baseValues = voices.scaledVoiceSettings(plan.voiceProfile, globalContext)
					languageCode = jawsFiles.languageCodeForLcid(jawsFiles.lcidFromText(globalContext.synthLanguage)) or jawsFiles.JAWS_LANGUAGES.get(options.language, (None, None))[1]
					messages = nvdaApply.applyVoice(voiceChoice.driver, voiceChoice.voiceId or voiceChoice.voiceName, globalContext.voiceName, languageCode, baseValues)
					result.messages.extend(f"Voice: {message}" for message in messages)
					synthName = nvdaApply.currentSynthName()
			if options.voice:
				self._writeOtherVoiceProfiles()
			if options.settings:
				perSynth = [change for change in plan.settings.changes if change.perSynth]
				applied, failed = nvdaApply.applySettings(perSynth, synthName)
				result.applied.extend(applied)
				result.failed.extend(failed)
			# Everything that belongs to the synthesizer the JAWS voices now use.
			if plan.classicSpeech and (options.classicVoices or options.classicSchemes):
				self._say("Copying JAWS voices and schemes into ClassicSpeech")
				self._writeClassicSpeech(baseValues)
			if options.dictionaries:
				voiceEntries = [entry for dictionaryPlan in plan.chosenDictionaries() for entry in dictionaryPlan.voiceEntries]
				if voiceEntries and voiceChoice is not None:
					added, error = nvdaApply.addDictionaryEntries("voice", voiceEntries)
					result.voiceDictionaryEntries += added
					if error:
						result.messages.append(error)
		if plan.classicSpeech and options.classicSettings:
			applied, failed = nvdaApply.applyClassicSpeechSettings(plan.settings.changes)
			result.applied.extend(applied)
			result.failed.extend(failed)
		nvdaApply.saveConfig()

		# Settings for single applications.
		if options.appProfiles:
			for configName, mapping in plan.appSettings.items():
				appProfile = f"{APP_PROFILE_PREFIX}{configName}"
				with nvdaApply.writingTo(appProfile):
					applied, failed = nvdaApply.applySettings(mapping.changes, None)
				for executable in plan.appExecutables.get(configName, [configName.lower()]):
					nvdaApply.setProfileTrigger(executable, appProfile)
				result.appProfiles.append((appProfile, plan.appExecutables.get(configName, []), len(applied)))
				result.failed.extend(failed)

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
			result.messages.extend(f"Gesture {binding.gesture} could not be added: {error}" for binding, error in failed)

		# The assistant's own settings: sleeping applications, sounds, the JAWS profile.
		updates = {}
		if options.sleepApps:
			sleepApps = set(state.get("sleepApps") or [])
			for configName in options.sleepApps:
				for executable in plan.appExecutables.get(configName, [configName.lower()]):
					sleepApps.add(executable.lower())
			updates["sleepApps"] = sorted(sleepApps)
		if options.sounds and result.soundsCopied:
			replacements = dict(state.get("soundReplacements") or {})
			for choice, destination, _how in result.soundsCopied:
				replacements[choice.event.nvdaName] = destination
			updates["soundReplacements"] = replacements
			updates["jawsSoundsEnabled"] = True
		if profileName:
			updates["jawsProfileName"] = profileName
			updates["activateJawsProfileAtStartup"] = bool(options.activateAtStartup)
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
		result.restartRecommended = bool(plan.classicSpeech and (options.classicSchemes or options.classicSettings))

	def _writeClassicSpeech(self, baseValues: dict):
		import synthDriverHandler

		from . import classicSpeechWriter, nvdaApply

		plan = self.plan
		options = plan.options
		result = self.result
		facts = plan.facts
		section = nvdaApply.classicSpeechSection()
		synth = synthDriverHandler.getSynth()
		descriptions = {driver.lower(): description for driver, description in facts.synths}
		resolvers = []
		for profilePlan in plan.selectedProfiles():
			option = profilePlan.option
			globalContext = profilePlan.contexts.get("Global")
			values = voices.scaledVoiceSettings(profilePlan.profile, globalContext) if globalContext else {}
			if profilePlan.primary and synth is not None and synth.name.lower() == option.driver.lower():
				resolver = classicSpeechWriter.LiveVoiceResolver(synth, profilePlan.synth, baseValues or values)
			else:
				knownVoices, knownVariants = voices.knownVoices(option.driver, facts.sapiVoices, facts.oneCoreVoices, facts.speechPlatformVoices)
				resolver = classicSpeechWriter.VoiceResolver(
					option.driver,
					descriptions.get(option.driver.lower(), option.driverDescription),
					profilePlan.synth,
					values,
					knownVoices,
					knownVariants,
				)
			aliases = profilePlan.aliases
			if options.voiceAliases is not None:
				wanted = {name.lower() for name in options.voiceAliases}
				aliases = {name: value for name, value in aliases.items() if name.lower() in wanted}
			resolvers.append((resolver, aliases))
			if options.classicVoices:
				records = {}
				for category, context in voices.CLASSIC_SPEECH_CONTEXTS.items():
					voiceContext = profilePlan.contexts.get(context) or globalContext
					if voiceContext is None:
						continue
					record, note = resolver.contextRecord(profilePlan.profile, voiceContext)
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
				result.schemesWritten.append((converted.name, len(items), folder, notes))
			active = options.activeClassicScheme
			if active and any(name == active for name, *_rest in result.schemesWritten):
				classicSpeechWriter.setSchemeSwitches(section, active, enable=True)
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
				values,
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

	The current settings and add-ons are backed up first, so the restore can be undone. The file
	work runs in the background while NVDA keeps responding; then NVDA reloads its settings.
	"""
	from . import nvdaApply, state

	manager = nvdaApply.addonManager()

	def work():
		before = backup.createBackup(
			nvdaEnv.configDir(),
			nvdaEnv.addonDataDir(),
			"",
			f"Before restoring the backup from {info.label}",
			nvdaEnv.nvdaVersion(),
			_addonVersion(),
		)
		return before, backup.restoreBackup(info, nvdaEnv.configDir(), nvdaEnv.addonDataDir(), addons=manager)

	before, result = nvdaApply.runWithProgress(work, "Restoring NVDA's settings and add-ons. Please wait.")
	state.forget()
	nvdaApply.resetToSavedConfiguration()
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


def recommendedAddonStates(facts: systemCheck.SystemFacts) -> list:
	"""``(StoreAddon, AddonState or None)`` for each add-on the assistant recommends."""
	return [(addon, nvdaEnv.addonState(addon.addonId, facts.addons)) for addon in managers.RECOMMENDED_ADDONS]
