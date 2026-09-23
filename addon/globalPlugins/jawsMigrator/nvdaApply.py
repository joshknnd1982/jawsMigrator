# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Changes to the running NVDA: settings, profiles, voices, dictionaries, symbols, gestures.

Everything here goes through NVDA's own interfaces, so values are validated the
way NVDA's settings dialogs validate them and NVDA uses the result straight
away. These functions must run in NVDA's main thread.
"""

from __future__ import annotations

import contextlib
import os

from . import settingsMap


def _log():
	from logHandler import log

	return log


# -- configuration profiles -------------------------------------------------------------


@contextlib.contextmanager
def writingTo(profileName: str | None):
	"""Make NVDA write settings into ``profileName``, or the normal configuration when None.

	Profile triggers are suspended and any manually activated profile is put back afterwards,
	so NVDA ends up exactly as it was, apart from the settings that were written.
	"""
	import config

	conf = config.conf
	previousManual = None
	if len(conf.profiles) > 1 and getattr(conf.profiles[-1], "manual", False):
		previousManual = conf.profiles[-1].name
	triggersWereEnabled = conf.profileTriggersEnabled
	conf.disableProfileTriggers()
	try:
		if profileName:
			if profileName not in conf.listProfiles():
				conf.createProfile(profileName)
			conf.manualActivateProfile(profileName)
		else:
			conf.manualActivateProfile(None)
		yield conf
		conf.save()
	finally:
		try:
			conf.manualActivateProfile(previousManual)
		except Exception:
			_log().exception("jawsMigrator: could not reactivate profile %s", previousManual)
			conf.manualActivateProfile(None)
		if triggersWereEnabled:
			conf.enableProfileTriggers()


def setValue(conf, path: tuple, value) -> None:
	"""Set ``conf[path[0]]...[path[-1]] = value`` in the profile being written.

	NVDA raises KeyError for a section no profile has yet, such as the settings of a
	synthesizer that has never been used, so missing sections are created first.
	"""
	section = conf
	for part in path[:-1]:
		try:
			section = section[part]
		except KeyError:
			section[part] = {}
			section = section[part]
	section[path[-1]] = value


def applySettings(changes: list, synthName: str | None) -> tuple[list, list]:
	"""Apply NVDA setting changes in the profile being written. Returns ``(applied, failed)``."""
	import config

	applied = []
	failed = []
	for change in changes:
		if change.target != settingsMap.NVDA:
			continue
		path = change.path
		if change.perSynth:
			if not synthName:
				failed.append((change, "no synthesizer to apply it to"))
				continue
			path = ("speech", synthName) + tuple(path)
		try:
			setValue(config.conf, path, change.value)
			applied.append(change)
		except Exception as error:
			_log().debugWarning("jawsMigrator: could not set %s", ".".join(path), exc_info=True)
			failed.append((change, str(error) or error.__class__.__name__))
	return applied, failed


def setProfileTrigger(appName: str, profileName: str) -> bool:
	"""Make ``profileName`` turn on in the application ``appName`` (its executable name)."""
	import config

	try:
		config.conf.triggersToProfiles[f"app:{appName.lower()}"] = profileName
		config.conf.saveProfileTriggers()
		return True
	except Exception:
		_log().exception("jawsMigrator: could not add a profile trigger for %s", appName)
		return False


def activateProfile(profileName: str | None) -> bool:
	import config

	try:
		if profileName and profileName not in config.conf.listProfiles():
			return False
		config.conf.manualActivateProfile(profileName or None)
		return True
	except Exception:
		_log().exception("jawsMigrator: could not activate profile %s", profileName)
		return False


def activeManualProfile() -> str | None:
	import config

	profiles = config.conf.profiles
	if len(profiles) > 1 and getattr(profiles[-1], "manual", False):
		return profiles[-1].name
	return None


# -- synthesizer and voice ----------------------------------------------------------------


def switchSynth(name: str) -> bool:
	import synthDriverHandler

	synth = synthDriverHandler.getSynth()
	if synth is not None and synth.name == name:
		return True
	return bool(synthDriverHandler.setSynth(name))


def _supported(synth) -> set:
	return {setting.id for setting in synth.supportedSettings}


def applyVoice(driver: str, voiceId: str, jawsVoiceName: str, languageCode: str | None, values: dict) -> list[str]:
	"""Switch to ``driver`` and set its voice, variant, rate, pitch and volume. Returns messages."""
	import synthDriverHandler

	from . import voices

	messages = []
	if not switchSynth(driver):
		current = synthDriverHandler.getSynth()
		return [f"NVDA could not load the {driver} synthesizer, so it stays with {current.description if current else 'its current synthesizer'}."]
	synth = synthDriverHandler.getSynth()
	supported = _supported(synth)
	if "voice" in supported:
		chosen = None
		try:
			available = {vid: (info.displayName, getattr(info, "language", None)) for vid, info in synth.availableVoices.items()}
		except Exception:
			available = {}
		if voiceId and voiceId in available:
			chosen = voiceId
		if chosen is None and voiceId:
			for vid, (name, _language) in available.items():
				if name.lower() == voiceId.lower():
					chosen = vid
		if chosen is None:
			chosen = voices.matchVoice(available, jawsVoiceName, languageCode)
		if chosen and chosen != synth.voice:
			try:
				synth.voice = chosen
				messages.append(f"Voice: {available.get(chosen, (chosen,))[0]}")
			except Exception as error:
				messages.append(f"The voice could not be selected: {error}")
	if "variant" in supported and jawsVoiceName:
		try:
			variants = {vid: info.displayName for vid, info in synth.availableVariants.items()}
		except Exception:
			variants = {}
		variant = voices.matchVariant(variants, jawsVoiceName)
		if variant:
			try:
				synth.variant = variant
				messages.append(f"Variant: {variants[variant]}")
			except Exception as error:
				messages.append(f"The variant could not be selected: {error}")
	for settingId in ("rate", "pitch", "volume"):
		if settingId in values and settingId in supported:
			try:
				setattr(synth, settingId, int(values[settingId]))
				messages.append(f"{settingId.capitalize()}: {int(values[settingId])}")
			except Exception as error:
				messages.append(f"{settingId.capitalize()} could not be set: {error}")
	synth.saveSettings()
	return messages


def snapshot(synth) -> dict:
	result = {}
	for setting in synth.supportedSettings:
		if setting.id.startswith("_"):
			continue
		try:
			value = getattr(synth, setting.id)
		except Exception:
			continue
		if isinstance(value, (bool, int, float, str)) or value is None:
			result[setting.id] = value
	return result


def restoreSnapshot(synth, values: dict) -> None:
	order = [key for key in ("voice", "variant") if key in values] + [key for key in values if key not in ("voice", "variant")]
	for key in order:
		try:
			setattr(synth, key, values[key])
		except Exception:
			pass


def voiceRecord(synth, voiceId: str | None, variantId: str | None, values: dict) -> dict:
	"""A ClassicSpeech voice record: the voice's own settings plus the changes JAWS made."""
	original = snapshot(synth)
	try:
		if voiceId:
			try:
				synth.voice = voiceId
			except Exception:
				pass
		baseline = snapshot(synth)
	finally:
		restoreSnapshot(synth, original)
	overrides = {}
	if variantId and baseline.get("variant") != variantId:
		overrides["variant"] = variantId
	for key, value in values.items():
		if key in baseline and baseline.get(key) != value:
			overrides[key] = value
	return {"baseline": baseline, "overrides": overrides}


def currentSynthName() -> str:
	import synthDriverHandler

	synth = synthDriverHandler.getSynth()
	return synth.name if synth else ""


# -- speech dictionaries ----------------------------------------------------------------------


def _dictionaryTypes():
	try:
		from speechDictHandler.types import DictionaryType, EntryType, SpeechDictEntry

		return DictionaryType, EntryType, SpeechDictEntry
	except Exception:
		return None, None, None


def liveDictionary(kind: str):
	"""NVDA's in-memory ``default`` or ``voice`` dictionary, or None."""
	DictionaryType, _EntryType, _SpeechDictEntry = _dictionaryTypes()
	if DictionaryType is not None:
		try:
			from speechDictHandler import definitions

			wanted = DictionaryType.DEFAULT if kind == "default" else DictionaryType.VOICE
			for definition in definitions._speechDictDefinitions:
				if definition.source == wanted:
					return definition.dictionary
		except Exception:
			_log().debugWarning("jawsMigrator: speech dictionary definitions unavailable", exc_info=True)
	try:
		import speechDictHandler

		return speechDictHandler.dictionaries[kind]
	except Exception:
		return None


def addDictionaryEntries(kind: str, entries: list) -> tuple[int, str]:
	"""Add converted entries to NVDA's default or current voice dictionary and save it."""
	dictionary = liveDictionary(kind)
	if dictionary is None:
		return 0, "NVDA's speech dictionary could not be opened."
	_DictionaryType, EntryType, SpeechDictEntry = _dictionaryTypes()
	if SpeechDictEntry is None:
		try:
			from speechDictHandler import SpeechDictEntry
		except Exception:
			return 0, "NVDA's speech dictionary entries could not be created."
	existing = {(e.pattern if e.caseSensitive else e.pattern.lower(), int(e.type)) for e in dictionary}
	added = 0
	for entry in entries:
		key = (entry.pattern if entry.caseSensitive else entry.pattern.lower(), entry.type)
		if key in existing:
			continue
		entryType = EntryType(entry.type) if EntryType is not None else entry.type
		try:
			dictionary.append(
				SpeechDictEntry(entry.pattern, entry.replacement, entry.comment, caseSensitive=entry.caseSensitive, type=entryType),
			)
			existing.add(key)
			added += 1
		except Exception:
			_log().debugWarning("jawsMigrator: dictionary entry rejected: %r", entry.pattern, exc_info=True)
	if added:
		dictionary.save()
	return added, ""


def reloadDefaultDictionary() -> None:
	dictionary = liveDictionary("default")
	path = getattr(dictionary, "fileName", None)
	if dictionary is not None and path:
		try:
			dictionary.load(path)
		except Exception:
			_log().debugWarning("jawsMigrator: could not reload the default dictionary", exc_info=True)


# -- symbols ------------------------------------------------------------------------------------


def speechLocale() -> str:
	try:
		import speech

		language = speech.getCurrentLanguage()
	except Exception:
		language = "en"
	try:
		import characterProcessing

		for locale in (language, language.split("_", 1)[0]):
			try:
				characterProcessing._localeSpeechSymbolProcessors.fetchLocaleData(locale, fallback=False)
				return locale
			except LookupError:
				continue
	except Exception:
		pass
	return language.split("_", 1)[0]


def symbolsFile(locale: str) -> str:
	try:
		from NVDAState import WritePaths

		return WritePaths.getSymbolsConfigFile(locale)
	except Exception:
		from . import nvdaEnv

		return os.path.join(nvdaEnv.configDir(), f"symbols-{locale}.dic")


def reloadSymbols() -> None:
	try:
		import characterProcessing

		characterProcessing.terminate()
		characterProcessing.initialize()
	except Exception:
		_log().debugWarning("jawsMigrator: could not reload speech symbols", exc_info=True)


# -- input gestures ------------------------------------------------------------------------------


def addGestures(bindings: list) -> tuple[int, list]:
	"""Bind gestures in NVDA's user gesture map and save gestures.ini.

	``bindings`` holds objects with ``gesture``, ``module``, ``className`` and ``script``;
	``script`` None unbinds the gesture for that class.
	"""
	import inputCore

	gestureMap = inputCore.manager.userGestureMap
	added = 0
	failed = []
	for binding in bindings:
		try:
			gestureMap.add(binding.gesture, binding.module, binding.className, binding.script)
			added += 1
		except Exception as error:
			failed.append((binding, str(error)))
	if added:
		gestureMap.save()
	return added, failed


def _splitGesture(identifier: str) -> tuple[str, str]:
	prefix, _sep, main = identifier.lower().partition(":")
	return prefix, "+".join(sorted(main.split("+")))


def _sameKeys(first: str, second: str) -> bool:
	"""Whether two gestures fire on the same key press: ``kb:`` applies to both keyboard layouts."""
	prefixA, mainA = _splitGesture(first)
	prefixB, mainB = _splitGesture(second)
	if mainA != mainB:
		return False
	if not (prefixA.startswith("kb") and prefixB.startswith("kb")):
		return prefixA == prefixB
	return prefixA == prefixB or prefixA == "kb" or prefixB == "kb"


def gestureBoundScripts(gesture: str) -> list:
	"""``(module, class, script)`` that NVDA or the user already bind to the keys of ``gesture``."""
	import inputCore

	results = []
	for gestureMap in (inputCore.manager.userGestureMap, inputCore.manager.localeGestureMap):
		try:
			for identifier, scripts in getattr(gestureMap, "_map", {}).items():
				if _sameKeys(identifier, gesture):
					results.extend(tuple(entry) for entry in scripts)
		except Exception:
			pass
	for cls in _gestureClasses():
		for base in cls.__mro__:
			# Gestures a class binds itself, including those from @script decorators.
			gestures = base.__dict__.get(f"_{base.__name__}__gestures")
			if not isinstance(gestures, dict):
				continue
			for identifier, scriptName in gestures.items():
				try:
					if scriptName and _sameKeys(identifier, gesture):
						results.append((cls.__module__, cls.__name__, str(scriptName)))
				except Exception:
					continue
	# A user "None" binding removes NVDA's own; don't count what the user already unbound.
	unbound = {(module, className) for module, className, script in results if script is None}
	return [entry for entry in results if entry[2] is not None and (entry[0], entry[1]) not in unbound]


def _gestureClasses() -> list:
	classes = []
	for moduleName, className in (
		("globalCommands", "GlobalCommands"),
		("browseMode", "BrowseModeTreeInterceptor"),
		("cursorManager", "CursorManager"),
		("documentBase", "DocumentWithTableNavigation"),
	):
		try:
			module = __import__(moduleName, fromlist=[className])
			classes.append(getattr(module, className))
		except Exception:
			continue
	return classes


def scriptExists(module: str, className: str, script: str) -> bool:
	try:
		imported = __import__(module, fromlist=[className])
		cls = getattr(imported, className)
		return callable(getattr(cls, f"script_{script}", None))
	except Exception:
		return False


def gesturesForScript(module: str, className: str, script: str) -> list[str]:
	"""Gestures NVDA currently binds to a script, as display text such as ``NVDA+f7``."""
	import inputCore

	found = []
	try:
		mappings = inputCore.manager.getAllGestureMappings()
		for category in mappings.values():
			for info in category.values():
				if info.moduleName == module and info.className == className and info.scriptName == script:
					for gesture in info.gestures:
						try:
							source, main = inputCore.getDisplayTextForGestureIdentifier(gesture)
							found.append(main)
						except Exception:
							found.append(gesture)
	except Exception:
		_log().debugWarning("jawsMigrator: could not read gesture mappings", exc_info=True)
	return found


# -- ClassicSpeech ------------------------------------------------------------------------------


def classicSpeechSection():
	"""ClassicSpeech's settings, kept in NVDA's base configuration while NVDA runs."""
	try:
		import importlib

		core = importlib.import_module("globalPlugins._speech_core.settings.config_core")
		return core._ensure_classic_speech_section()
	except Exception:
		_log().debugWarning("jawsMigrator: ClassicSpeech's settings helper is unavailable", exc_info=True)
	import config

	base = config.conf.profiles[0]
	if "classicSpeech" not in base:
		base["classicSpeech"] = {}
	return base["classicSpeech"]


def applyClassicSpeechSettings(changes: list) -> tuple[list, list]:
	applied = []
	failed = []
	section = classicSpeechSection()
	for change in changes:
		if change.target != settingsMap.CLASSIC_SPEECH:
			continue
		try:
			target = section
			for part in change.path[:-1]:
				if part not in target:
					target[part] = {}
				target = target[part]
			target[change.path[-1]] = change.value
			applied.append(change)
		except Exception as error:
			failed.append((change, str(error)))
	return applied, failed


def invalidateClassicSpeechCaches() -> None:
	import importlib

	for moduleName, function in (
		("globalPlugins._speech_core.schemes.store", "invalidate_runtime_cache"),
		("globalPlugins._speech_core.schemes.runtime", "invalidate_runtime_cache"),
		("globalPlugins._speech_core.schemes.runtime", "clear_sound_cache"),
	):
		try:
			getattr(importlib.import_module(moduleName), function)()
		except Exception:
			pass


def saveConfig() -> None:
	import config

	config.conf.save()


def resetToSavedConfiguration() -> None:
	"""Reload NVDA's settings from disk, as NVDA+control+r does."""
	import core

	core.resetConfiguration()
	reloadDefaultDictionary()
