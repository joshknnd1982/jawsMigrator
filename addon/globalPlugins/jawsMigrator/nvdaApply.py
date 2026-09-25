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

from . import backup, nvdaEnv, safety, settingsMap


def _log():
	from logHandler import log

	return log


# -- configuration profiles -------------------------------------------------------------

#: What NVDA's Configuration Profiles dialog calls the base configuration.
NORMAL_CONFIGURATION = "normal configuration"


def existingProfileName(name: str | None) -> str | None:
	"""The existing configuration profile called ``name``, spelled as it is on disk, or None.

	A profile is a file, and Windows file names ignore case: when "JAWS settings" exists,
	"jaws settings" is that profile, and NVDA would refuse to create it again.
	"""
	if not name:
		return None
	import config

	wanted = name.lower()
	for existing in config.conf.listProfiles():
		if existing.lower() == wanted:
			return existing
	return None


def _profilePath(profileName: str) -> str:
	return os.path.join(nvdaEnv.configDir(), "profiles", f"{profileName}.ini")


@contextlib.contextmanager
def writingTo(profileName: str | None):
	"""Make NVDA write settings into ``profileName``, or the normal configuration when None.

	Profile triggers are suspended and any manually activated profile is put back afterwards,
	so NVDA ends up exactly as it was, apart from the settings that were written. An existing
	profile whose name differs only in case is the one written to.
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
			existing = existingProfileName(profileName)
			if existing is None:
				safety.checkWritable(_profilePath(profileName))
				conf.createProfile(profileName)
			else:
				profileName = existing
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


def getValue(path: tuple):
	"""NVDA's current value of a setting, or None when it has none."""
	try:
		import config

		section = config.conf
		for part in path:
			section = section[part]
		return section
	except Exception:
		return None


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


def writingConfigurationName() -> str:
	"""The configuration NVDA writes settings to now: the active profile's name, or the normal configuration."""
	import config

	profiles = config.conf.profiles
	if len(profiles) > 1:
		return str(getattr(profiles[-1], "name", "") or NORMAL_CONFIGURATION)
	return NORMAL_CONFIGURATION


def normalConfigurationOnly(path) -> bool:
	"""Whether NVDA keeps the setting at ``path`` in its normal configuration only (ConfigManager.BASE_ONLY_SECTIONS)."""
	import config

	return bool(path) and path[0] in getattr(config.conf, "BASE_ONLY_SECTIONS", ())


def applySettings(changes: list, synthName: str | None) -> tuple[list, list]:
	"""Apply NVDA setting changes in the configuration being written (see ``writingTo``). Returns ``(applied, failed)``.

	While a profile is being written, settings NVDA keeps in its normal configuration only (such as
	"Play sounds when starting or exiting NVDA") are left out, because setting them would change the
	normal configuration that a profile leaves as it is. They come back in ``failed``, saying why.
	"""
	import config

	writingProfile = len(config.conf.profiles) > 1
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
		if writingProfile and normalConfigurationOnly(path):
			failed.append(
				(
					change,
					f'NVDA keeps this setting in its normal configuration only, and these settings went into the profile "{writingConfigurationName()}", '
					"so your normal configuration was left as it is",
				),
			)
			continue
		try:
			setValue(config.conf, path, change.value)
			applied.append(change)
		except Exception as error:
			_log().debugWarning("jawsMigrator: could not set %s", ".".join(path), exc_info=True)
			failed.append((change, str(error) or error.__class__.__name__))
	return applied, failed


#: What ``setProfileTrigger`` did.
TRIGGER_SET = "set"
TRIGGER_KEPT = "kept"
TRIGGER_FAILED = "failed"


def setProfileTrigger(appName: str, profileName: str) -> tuple[str, str]:
	"""Make ``profileName`` turn on in the application ``appName``: its program's name, without ".exe".

	Returns ``(TRIGGER_SET, "")`` when done. A trigger that already turns on another existing profile
	is the user's and is never taken over: nothing changes, and ``(TRIGGER_KEPT, that profile)`` comes
	back. ``(TRIGGER_FAILED, reason)`` when NVDA could not save it.
	"""
	import config

	spec = f"app:{appName.lower()}"
	try:
		triggers = config.conf.triggersToProfiles
		current = triggers.get(spec)
		if current and current != profileName:
			owner = existingProfileName(current)
			if owner is not None and owner.lower() != profileName.lower():
				return TRIGGER_KEPT, owner
		safety.checkWritable(os.path.join(nvdaEnv.configDir(), "profileTriggers.ini"))
		triggers[spec] = profileName
		config.conf.saveProfileTriggers()
		return TRIGGER_SET, ""
	except Exception as error:
		_log().exception("jawsMigrator: could not add a profile trigger for %s", appName)
		return TRIGGER_FAILED, str(error) or error.__class__.__name__


def _holdsValues(section, top: bool = True) -> bool:
	# dict.items: the stored values, without ConfigObj's interpolation.
	for key, value in dict.items(section):
		if top and key == "schemaVersion":
			continue
		if isinstance(value, dict):
			if _holdsValues(value, top=False):
				return True
		else:
			return True
	return False


def profileFileHoldsSettings(path: str) -> bool:
	"""Whether a profile file holds any setting besides its ``schemaVersion``. True when it can't be read.

	NVDA's profile files are ConfigObj files: ``[section]`` headers, ``key = value`` lines and ``#`` comments.
	"""
	try:
		with open(path, encoding="utf-8-sig", errors="replace") as stream:
			lines = stream.read().splitlines()
	except OSError:
		return True
	inSection = False
	for line in lines:
		text = line.strip()
		if not text or text.startswith("#"):
			continue
		if text.startswith("["):
			inSection = True
			continue
		key = text.split("=", 1)[0].strip()
		if inSection or key != "schemaVersion":
			return True
	return False


def profileHoldsSettings(profileName: str) -> bool:
	"""Whether a configuration profile holds any setting of its own.

	NVDA only writes a setting into a profile when it differs from the configuration below it, so a
	profile given nothing but the normal configuration's values holds only its ``schemaVersion``.
	A profile NVDA has loaded is checked as NVDA holds it, one it hasn't loaded as its file is; one
	that can be read neither way counts as holding settings, so it is never taken for empty.
	"""
	import config

	try:
		profile = config.conf.getProfile(profileName)
	except (KeyError, AttributeError):
		return profileFileHoldsSettings(_profilePath(profileName))
	return _holdsValues(profile)


def deleteProfile(profileName: str) -> bool:
	"""Delete a configuration profile and its triggers, as NVDA's Configuration Profiles dialog does."""
	import config

	try:
		safety.checkWritable(_profilePath(profileName))
		config.conf.deleteProfile(profileName)
		return True
	except Exception:
		_log().exception("jawsMigrator: could not delete the profile %s", profileName)
		return False


def activateProfile(profileName: str | None) -> bool:
	import config

	try:
		if profileName:
			profileName = existingProfileName(profileName)
			if profileName is None:
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


def selectVoice(synth, voiceId: str) -> None:
	"""Select a voice the way NVDA's own settings do, so NVDA also loads that voice's speech dictionary.

	Setting ``synth.voice`` alone keeps the dictionary of the voice NVDA had before; rules added to the
	voice dictionary would then be saved into that other voice's file.
	"""
	import synthDriverHandler

	change = getattr(synthDriverHandler, "changeVoice", None)
	if change is None:
		synth.voice = voiceId
	else:
		change(synth, voiceId)


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
				selectVoice(synth, chosen)
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


def voiceRecord(synth, voiceId: str | None, variantId: str | None) -> dict:
	"""A ClassicSpeech voice record that selects a voice or variant, as ClassicSpeech's own editor makes one.

	The baseline is that voice's own settings, which ClassicSpeech only shows; it applies just
	the voice and variant. Nothing else is overridden, so the rate, pitch and volume the user
	sets in NVDA apply to this voice too.
	"""
	original = snapshot(synth)
	try:
		if voiceId:
			try:
				synth.voice = voiceId
			except Exception:
				pass
		if variantId:
			try:
				synth.variant = variantId
			except Exception:
				pass
		baseline = snapshot(synth)
	finally:
		restoreSnapshot(synth, original)
	return {"baseline": baseline, "overrides": {"variant": variantId} if variantId else {}}


def eciRateRange(driver: str) -> tuple:
	"""``((minRate, maxRate), rate boost)`` of an NVDA Eloquence driver; ``(None, 1.0)`` for other drivers.

	The range is the driver's own ``minRate`` and ``maxRate`` where its module has them, else the known
	one (see voices.ECI_RATE_RANGES). The boost is the driver's rate boost multiplier while rate boost
	is on in NVDA's settings for it, else 1.
	"""
	import sys

	from . import voices

	if not voices.isEciDriver(driver):
		return None, 1.0
	eciRange = voices.ECI_RATE_RANGES.get(driver.lower(), voices.DEFAULT_ECI_RATE_RANGE)
	boost = 1.0
	try:
		import synthDriverHandler

		cls = synthDriverHandler._getSynthDriver(driver)
		module = sys.modules.get(cls.__module__)
		low, high = getattr(module, "minRate", None), getattr(module, "maxRate", None)
		if isinstance(low, int) and isinstance(high, int) and not isinstance(low, bool) and high > low:
			eciRange = (low, high)
		multiplier = getattr(cls, "RATE_BOOST_MULTIPLIER", None)
		if multiplier and getValue(("speech", driver, "rateBoost")) is True:
			boost = float(multiplier)
	except Exception:
		_log().debugWarning(f"jawsMigrator: the rate range of the {driver} synthesizer is not known; using {eciRange}", exc_info=True)
	return eciRange, boost


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
	"""Have NVDA read its symbol files again.

	NVDA builds its list of symbol dictionaries anew, so JAWS's rule for a colon between digits and the
	rule for a drive's letter go back in when they were there (see numberSymbols and driveLetters).
	"""
	try:
		import characterProcessing

		characterProcessing.terminate()
		characterProcessing.initialize()
	except Exception:
		_log().debugWarning("jawsMigrator: could not reload speech symbols", exc_info=True)
	from . import driveLetters, numberSymbols

	for rule in (numberSymbols, driveLetters):
		if rule.isRegistered():
			rule.register()


# -- input gestures ------------------------------------------------------------------------------


def addGestures(bindings: list) -> tuple[int, list]:
	"""Bind gestures in NVDA's user gesture map and save gestures.ini.

	``bindings`` holds objects with ``gesture``, ``module``, ``className`` and ``script``;
	``script`` None unbinds the gesture for that class. An optional ``unbind`` list of
	``(module, class)`` also unbinds the gesture for those classes, whose own binding NVDA
	would otherwise find first (see keyPlan.GestureBinding).
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
			continue
		for module, className in getattr(binding, "unbind", None) or ():
			try:
				gestureMap.add(binding.gesture, module, className, None)
			except Exception as error:
				failed.append((binding, f"{module}.{className} could not be unbound: {error}"))
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
	"""What NVDA or the user already bind to the keys of ``gesture``.

	Returns ``(module, class, script, identifier, source)`` tuples. ``identifier`` is the gesture
	identifier of that binding (a ``kb(laptop):`` one only works in NVDA's laptop keyboard layout);
	``source`` is ``"user"`` (gestures.ini), ``"locale"``, ``"class"`` (the class binds it itself,
	named after the class that does) or ``"addon"`` (another add-on's global plugin binds it).
	``script`` is None where a gesture map unbinds the keystroke for that class; keyPlan leaves out
	what is unbound.
	"""
	import inputCore

	results = []
	for source, gestureMap in (("user", inputCore.manager.userGestureMap), ("locale", inputCore.manager.localeGestureMap)):
		try:
			for identifier, scripts in getattr(gestureMap, "_map", {}).items():
				if _sameKeys(identifier, gesture):
					results.extend((module, className, script, identifier, source) for module, className, script in scripts)
		except Exception:
			pass
	seen = set()
	for cls in _gestureClasses():
		for base in cls.__mro__:
			# Gestures a class binds itself, including those from @script decorators.
			gestures = base.__dict__.get(f"_{base.__name__}__gestures")
			if not isinstance(gestures, dict):
				continue
			for identifier, scriptName in gestures.items():
				try:
					if scriptName and _sameKeys(identifier, gesture):
						entry = (base.__module__, base.__name__, str(scriptName), identifier, "class")
						if entry not in seen:
							seen.add(entry)
							results.append(entry)
				except Exception:
					continue
	for entry in _addonPluginGestures(gesture):
		if entry not in seen:
			seen.add(entry)
			results.append(entry)
	return results


def _addonPluginGestures(gesture: str) -> list:
	"""``(module, class, script, identifier, "addon")`` for the keys of ``gesture`` in other add-ons' global plugins.

	NVDA asks every running global plugin before the focused control, browse mode and globalCommands,
	so another add-on's keystroke would win over a new binding for those. This add-on is left out.
	"""
	results = []
	try:
		import globalPluginHandler

		plugins = list(globalPluginHandler.runningPlugins)
	except Exception:
		return results
	for plugin in plugins:
		cls = type(plugin)
		if cls.__module__ == __package__:
			continue
		try:
			gestureMap = dict(getattr(plugin, "_gestureMap", {}) or {})
		except Exception:
			continue
		for identifier, function in gestureMap.items():
			try:
				if function is None or not _sameKeys(identifier, gesture):
					continue
				name = getattr(function, "__name__", "") or ""
				script = name[len("script_"):] if name.startswith("script_") else name
				results.append((cls.__module__, cls.__name__, script or "?", identifier, "addon"))
			except Exception:
				continue
	return results


def _gestureClasses() -> list:
	"""The NVDA classes whose own gestures a JAWS keystroke may clash with.

	Their base classes are searched too; the subclasses are listed because they bind gestures
	of their own (NVDA+F5 refreshes browse mode documents in VirtualBuffer).
	"""
	classes = []
	for moduleName, className in (
		("globalCommands", "GlobalCommands"),
		("browseMode", "BrowseModeTreeInterceptor"),
		("browseMode", "BrowseModeDocumentTreeInterceptor"),
		("virtualBuffers", "VirtualBuffer"),
		("cursorManager", "CursorManager"),
		("documentBase", "DocumentWithTableNavigation"),
		("editableText", "EditableText"),
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

	def classGestures() -> list:
		# The gestures the class binds to the script itself, less those gestures.ini unbinds for it.
		try:
			cls = getattr(__import__(module, fromlist=[className]), className)
		except Exception:
			return []
		normalize = getattr(inputCore, "normalizeGestureIdentifier", str.lower)
		unbound = set()
		try:
			for identifier, scripts in getattr(inputCore.manager.userGestureMap, "_map", {}).items():
				if (module, className, None) in [tuple(entry) for entry in scripts]:
					unbound.add(identifier)
		except Exception:
			pass
		result = []
		seen = set()
		for base in cls.__mro__:
			gestures = base.__dict__.get(f"_{base.__name__}__gestures")
			if not isinstance(gestures, dict):
				continue
			for identifier, scriptName in gestures.items():
				try:
					normalized = normalize(identifier)
				except Exception:
					continue
				if normalized in seen:
					# A subclass binds these keys to something else.
					continue
				seen.add(normalized)
				if scriptName == script and normalized not in unbound:
					result.append(normalized)
		return result

	identifiers = []
	try:
		mappings = inputCore.manager.getAllGestureMappings()
		for category in mappings.values():
			for info in category.values():
				if info.moduleName == module and info.className == className and info.scriptName == script:
					identifiers.extend(info.gestures)
	except Exception:
		_log().debugWarning("jawsMigrator: could not read gesture mappings", exc_info=True)
	if not identifiers:
		# NVDA only lists the commands of what has the focus: browse mode and table commands are
		# missing outside a browse mode document, though their keys work there.
		identifiers = classGestures()
	found = []
	for gesture in identifiers:
		try:
			_source, main = inputCore.getDisplayTextForGestureIdentifier(gesture)
			found.append(main)
		except Exception:
			found.append(gesture)
	return found


# -- ClassicSpeech ------------------------------------------------------------------------------


class ClassicSpeechNotRunning(RuntimeError):
	"""ClassicSpeech doesn't run in this NVDA session, so its settings can't be changed through NVDA."""


def _classicSpeechSettingsModule():
	try:
		import importlib

		return importlib.import_module("globalPlugins._speech_core.settings.config_core")
	except Exception:
		return None


def classicSpeechRunning() -> bool:
	"""Whether ClassicSpeech's code runs in this NVDA session, keeping its settings in NVDA's configuration."""
	return hasattr(_classicSpeechSettingsModule(), "_ensure_classic_speech_section")


def classicSpeechSection():
	"""ClassicSpeech's settings, which it keeps in NVDA's base configuration while it runs.

	Raises ClassicSpeechNotRunning when it doesn't run. Its settings are then only in its own
	ClassicSpeech\\settings.ini, and a ``[classicSpeech]`` section written into nvda.ini would be taken
	by ClassicSpeech, the next time it starts, for settings of an old version, and moved over that file.
	"""
	core = _classicSpeechSettingsModule()
	if not hasattr(core, "_ensure_classic_speech_section"):
		raise ClassicSpeechNotRunning(
			"ClassicSpeech isn't running in this NVDA session, so its settings were not changed. "
			"Enable ClassicSpeech in NVDA's Add-on Store, restart NVDA, then try again.",
		)
	return core._ensure_classic_speech_section()


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


@contextlib.contextmanager
def _addonChangesLeftForRestart():
	"""Keep add-on installs, removals, enables and disables pending while NVDA reloads its configuration.

	``core.resetConfiguration`` runs ``addonHandler.initialize``, which does what NVDA does when it
	starts: it finishes pending removals and installs (``getAvailableAddons(refresh=True,
	isFirstLoad=True)``, running add-ons' uninstall tasks) and applies pending disables. Done now,
	that would delete or replace add-ons that are loaded and running. NVDA does it when it restarts.
	``addonHandler.terminate`` does nothing, so NVDA's add-on state stays as it was.
	"""
	try:
		import addonHandler
	except ImportError:
		yield
		return
	original = getattr(addonHandler, "initialize", None)
	if original is None:
		yield
		return

	def initializeLater():
		_log().info("jawsMigrator: add-on changes stay pending until NVDA restarts")

	addonHandler.initialize = initializeLater
	try:
		yield
	finally:
		addonHandler.initialize = original


def reloadProfileTriggers() -> None:
	"""Read profileTriggers.ini again. NVDA reads it only when it starts, not when it reloads its configuration."""
	import config

	load = getattr(config.conf, "_loadProfileTriggers", None)
	if load is None:
		return
	try:
		load()
	except Exception:
		_log().exception("jawsMigrator: could not reload the configuration profile triggers")


def resetToSavedConfiguration() -> None:
	"""Reload NVDA's settings from disk, as NVDA+control+r does.

	Unlike NVDA+control+r, add-on changes waiting for a restart stay waiting, and the profile
	triggers are read again, since the files may have just been put back from a backup.
	"""
	import core

	with _addonChangesLeftForRestart():
		core.resetConfiguration()
	reloadProfileTriggers()
	reloadDefaultDictionary()


# -- add-ons and long work, for restoring backups ------------------------------------------


class NvdaAddonManager(backup.AddonManager):
	"""Installs, removes, enables and disables add-ons through NVDA's own add-on handling.

	It does what NVDA's Add-on Store does: removals and installs are recorded in NVDA's add-on
	state and finish when NVDA restarts; add-ons still waiting to be installed are removed at once.
	"""

	def __init__(self):
		self._cache = None

	def _addons(self, name: str | None = None, refresh: bool = False) -> list:
		import addonHandler

		if refresh or self._cache is None:
			self._cache = list(addonHandler.getAvailableAddons(refresh=True))
		return [addon for addon in self._cache if name is None or addon.name.lower() == name.lower()]

	@staticmethod
	def _waitingToInstall(addon) -> bool:
		import addonHandler

		return addon.path.lower().endswith(addonHandler.ADDON_PENDINGINSTALL_SUFFIX.lower())

	def installed(self) -> list:
		records = []
		for addon in self._addons(refresh=True):
			waiting = self._waitingToInstall(addon)
			disabled = (addon.isDisabled or addon.isPendingDisable) and not addon.isPendingEnable
			records.append(backup.AddonRecord(addon.name, addon.version, addon.path, waiting, not waiting and addon.isPendingRemove, disabled))
		return records

	def remove(self, name: str) -> None:
		import addonHandler
		from addonStore.models.status import AddonStateCategory

		addons = self._addons(name)
		for addon in addons:
			if self._waitingToInstall(addon):
				if addon.isInstalled:
					# An update waiting to replace an installed copy: NVDA would still install it at restart.
					addon.completeRemove()
					addonHandler.state[AddonStateCategory.PENDING_INSTALL].discard(addon.name)
				else:
					addon.requestRemove()
		for addon in addons:
			if not self._waitingToInstall(addon) and os.path.isdir(addon.path):
				addon.requestRemove()
		self._cache = None

	def cancelRemove(self, name: str) -> None:
		import addonHandler
		from addonStore.models.status import AddonStateCategory

		addonHandler.state[AddonStateCategory.PENDING_REMOVE].discard(name)

	def stageInstall(self, name: str, source: str, disabled: bool, overrideCompatibility: bool) -> None:
		import shutil

		import addonHandler
		from addonStore.models.status import AddonStateCategory

		target = safety.checkWritable(os.path.join(nvdaEnv.configDir(), "addons", name + addonHandler.ADDON_PENDINGINSTALL_SUFFIX))
		if os.path.isdir(target):
			shutil.rmtree(target)
		shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
		state = addonHandler.state
		state[AddonStateCategory.PENDING_INSTALL].add(name)
		if disabled:
			state[AddonStateCategory.DISABLED].add(name)
		if overrideCompatibility:
			state[AddonStateCategory.PENDING_OVERRIDE_COMPATIBILITY].add(name)
		self._cache = None

	def setEnabled(self, name: str, enabled: bool) -> None:
		for addon in self._addons(name):
			if not self._waitingToInstall(addon):
				addon.enable(enabled)

	def save(self) -> None:
		import addonHandler

		addonHandler.state.save()
		addonHandler.getAvailableAddons(refresh=True)


def addonManager() -> backup.AddonManager:
	"""NVDA's own add-on handling when NVDA runs; the files alone otherwise (outside NVDA, and in tests)."""
	try:
		import addonHandler
		from addonStore.models import status

		if hasattr(status, "AddonStateCategory") and hasattr(addonHandler, "state") and hasattr(addonHandler, "ADDON_PENDINGINSTALL_SUFFIX"):
			return NvdaAddonManager()
	except ImportError:
		pass
	return backup.FileAddonManager(nvdaEnv.configDir())


def runWithProgress(function, message: str):
	"""Run ``function`` in a background thread while NVDA shows a progress dialog and keeps responding.

	Returns what ``function`` returns, and raises what it raised. Outside NVDA it just runs it.
	"""
	try:
		import gui
		import systemUtils
	except ImportError:
		return function()
	try:
		dialog = gui.IndeterminateProgressDialog(gui.mainFrame, "JAWS Migration Assistant", message)
	except Exception:
		dialog = None
	try:
		return systemUtils.ExecAndPump(function).funcRes
	finally:
		if dialog is not None:
			dialog.done()
