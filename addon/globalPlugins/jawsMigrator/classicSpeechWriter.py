# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Write JAWS voices and schemes into ClassicSpeech, in ClassicSpeech's own formats.

* Voice Profiles: each JAWS voice context (PC cursor, JAWS cursor, keyboard,
  messages) becomes the matching ClassicSpeech category for the synthesizer NVDA
  speaks with, stored in ``classicSpeech.voiceProfileData`` as ClassicSpeech does.
* Speech and Sound Schemes: each converted JAWS scheme becomes a folder under
  ``ClassicSpeech\\Schemes`` with its ``scheme.json`` and its sounds, and a
  ``.classicspeech-scheme`` package that can be imported on another computer.
* Voice aliases: every alias a scheme uses is turned into a ClassicSpeech voice
  for that synthesizer: the alias's person (Reed, Glen, Shelley...) becomes the
  matching NVDA voice or variant. When the person is missing, the alias's
  fallback is used, as JAWS does.

Only the person carries over, never a rate, pitch or volume. JAWS changes those
by percentages of the current voice, but ClassicSpeech keeps fixed values, which
would override the rate, pitch and volume the user sets in NVDA wherever the
voice is used. So the user's own NVDA settings apply everywhere. A voice that
would select the person NVDA already speaks with is left out.

Must run in NVDA's main thread, with the target synthesizer active.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile

from . import debugLog, nvdaApply, safety, schemeMap, voices, wavUtil

VOICES_FORMAT = "ClassicSpeech voice profiles"
SCHEME_FORMAT = "ClassicSpeech scheme"
PACKAGE_FORMAT = "ClassicSpeech scheme package"
PACKAGE_MANIFEST = "classicspeech-scheme.json"
_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _log():
	from logHandler import log

	return log


def _loadJson(text, default):
	if isinstance(text, dict):
		return text
	try:
		value = json.loads(text or "")
		return value if isinstance(value, type(default)) else default
	except (TypeError, ValueError):
		return default


def folderNameFor(name: str) -> str:
	cleaned = _INVALID_NAME.sub("_", name).strip().rstrip(".") or "Scheme"
	return cleaned[:80]


# -- voices ---------------------------------------------------------------------------


class VoiceResolver:
	"""Turns JAWS persons (Reed, Glen, a SAPI voice...) into one NVDA synthesizer's voice or variant.

	This base class works from the voices NVDA's configuration and the registry describe,
	without loading the synthesizer. ``LiveVoiceResolver`` works with the synthesizer NVDA is
	speaking with. ``currentVoice`` and ``currentVariant`` are the ones NVDA speaks with, so a
	person that is already speaking needs no ClassicSpeech voice.
	"""

	def __init__(self, driverName: str, driverDescription: str, jawsSynth: voices.JawsSynthInfo, knownVoices=None, knownVariants=None, currentVoice=None, currentVariant=None):
		self.driverName = driverName
		self.driverDescription = driverDescription or driverName
		self.jawsSynth = jawsSynth
		self.voices = dict(knownVoices or {})
		self.variants = dict(knownVariants or {})
		self.currentVoice = currentVoice
		self.currentVariant = currentVariant

	def person(self, name: str) -> tuple[str | None, str | None]:
		"""``(voiceId, variantId)`` for a JAWS person, or ``(None, None)`` when the synthesizer lacks it."""
		if not name or name == "*":
			return None, None
		if self.variants:
			variant = voices.matchVariant(self.variants, name)
			if variant:
				return None, variant
		if self.voices:
			for voiceId, (displayName, _language) in self.voices.items():
				if voices._voiceNameMatches(displayName, name):
					return voiceId, None
		return None, None

	def isCurrent(self, voiceId: str | None, variantId: str | None) -> bool:
		sameVoice = voiceId is None or str(voiceId) == str(self.currentVoice)
		sameVariant = variantId is None or str(variantId) == str(self.currentVariant)
		return sameVoice and sameVariant

	def record(self, voiceId: str | None, variantId: str | None) -> dict:
		"""A ClassicSpeech record that selects a voice or variant, as ClassicSpeech's editor makes one."""
		baseline = {}
		if voiceId:
			baseline["voice"] = voiceId
		if variantId:
			baseline["variant"] = variantId
		return {"baseline": baseline, "overrides": {"variant": variantId} if variantId else {}}

	def _personRecord(self, name: str) -> tuple[dict | None, str]:
		voiceId, variantId = self.person(name)
		if not (voiceId or variantId):
			return None, f"{name} is not available in {self.driverDescription}, so the current voice is kept"
		if self.isCurrent(voiceId, variantId):
			return None, f"{name} is the voice NVDA already speaks with"
		return self.record(voiceId, variantId), name

	def contextRecord(self, context: voices.VoiceContext) -> tuple[dict | None, str]:
		"""The ClassicSpeech voice for a JAWS voice context (JAWS cursor, messages...): its person, or None."""
		if not context.voiceName:
			return None, "the context has no voice of its own"
		return self._personRecord(context.voiceName)

	def aliasRecord(self, aliasValue: str) -> tuple[dict | None, str]:
		"""The ClassicSpeech voice for a JAWS voice alias: the first of its persons this synthesizer has, or None."""
		groups = voices.parseVoiceAlias(aliasValue)
		dropped = [voices.aliasChanges(group) for group in groups if voices.aliasChanges(group)]
		kept = f"; its {dropped[0]} is left to NVDA's own settings" if dropped else ""
		for group in groups:
			if group["person"] == "*":
				return None, "the alias keeps the current voice" + kept
			voiceId, variantId = self.person(group["person"])
			if voiceId or variantId:
				record, note = self._personRecord(group["person"])
				return record, note + kept
		return None, f"none of the alias's persons is available in {self.driverDescription}, so the current voice is kept"


class LiveVoiceResolver(VoiceResolver):
	"""A resolver for the synthesizer NVDA is speaking with."""

	def __init__(self, synth, jawsSynth: voices.JawsSynthInfo):
		supported = {setting.id for setting in synth.supportedSettings}
		knownVoices = {}
		knownVariants = {}
		if "voice" in supported:
			try:
				knownVoices = {vid: (info.displayName, getattr(info, "language", None)) for vid, info in synth.availableVoices.items()}
			except Exception:
				knownVoices = {}
		if "variant" in supported:
			try:
				knownVariants = {vid: info.displayName for vid, info in synth.availableVariants.items()}
			except Exception:
				knownVariants = {}
		super().__init__(
			synth.name,
			synth.description,
			jawsSynth,
			knownVoices,
			knownVariants,
			currentVoice=getattr(synth, "voice", None) if "voice" in supported else None,
			currentVariant=getattr(synth, "variant", None) if "variant" in supported else None,
		)
		self.synth = synth

	def record(self, voiceId: str | None, variantId: str | None) -> dict:
		return nvdaApply.voiceRecord(self.synth, voiceId, variantId)


def writeVoiceProfiles(section, synthName: str, records: dict) -> None:
	"""Store ``{category: record}`` for one synthesizer in ClassicSpeech's voiceProfileData."""
	registry = _loadJson(section.get("voiceProfileData", "{}"), {})
	target = registry.setdefault(synthName, {})
	target.update(records)
	section["voiceProfileData"] = json.dumps(registry, ensure_ascii=False, separators=(",", ":"))


def writeVoicesFile(path: str, synthName: str, records: dict) -> None:
	"""A ``.classicspeech-voices`` file that ClassicSpeech can import (Voice Profiles, Import)."""
	payload = {"format": VOICES_FORMAT, "version": 1, "synthesizers": {synthName: records}}
	safety.checkWritable(path)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w", encoding="utf-8") as stream:
		json.dump(payload, stream, ensure_ascii=False, indent="\t")


# -- schemes ----------------------------------------------------------------------------


def buildSchemeItems(converted: schemeMap.ConvertedScheme, resolvers: list, soundsFolder: str) -> tuple[dict, list]:
	"""ClassicSpeech items for a converted scheme, copying its sounds into ``soundsFolder``.

	``resolvers`` is a list of ``(VoiceResolver, aliases)``: one per migrated JAWS voice
	profile, so each voice alias gets a voice for every NVDA synthesizer that
	stands in for a JAWS synthesizer.
	"""
	items = {}
	notes = []
	usedSounds: dict = {}
	for itemId, item in converted.items.items():
		settings = {}
		if item.sound:
			fileName = os.path.basename(item.sound)
			if fileName.lower() not in usedSounds:
				try:
					wavUtil.copyPlayable(item.sound, os.path.join(soundsFolder, fileName))
					usedSounds[fileName.lower()] = fileName
				except (OSError, wavUtil.WavError) as error:
					notes.append(f"{itemId}: sound {fileName} skipped ({error})")
					continue
			settings["sound"] = "Sounds/" + usedSounds[fileName.lower()]
			settings["soundOnly"] = bool(item.soundOnly)
		if item.voiceAlias:
			bySynth = {}
			for resolver, aliases in resolvers:
				value = {name.lower(): text for name, text in aliases.items()}.get(item.voiceAlias.lower())
				if value is None:
					continue
				record, note = resolver.aliasRecord(value)
				debugLog.note(f"  {converted.name}: {itemId} voice alias {item.voiceAlias}={value} for {resolver.driverName}: {'person ' + note if record else note}")
				if record is None:
					if "not available" in note:
						notes.append(f"{itemId} ({resolver.driverDescription}): {note}")
					continue
				bySynth[resolver.driverName] = record
			if bySynth:
				settings["voice"] = {"enabled": True, "engine": "", "bySynth": bySynth}
			elif not resolvers:
				notes.append(f"{itemId}: voice alias {item.voiceAlias} needs a synthesizer")
		items[itemId] = settings if settings else {}
	# Items with nothing to store are left out, as ClassicSpeech does.
	return {itemId: settings for itemId, settings in items.items() if settings}, notes


def writeSchemeFolder(schemesRoot: str, name: str, items: dict, soundsSource: str) -> str:
	"""Create or replace ``Schemes\\<name>`` with ``scheme.json`` and its Sounds folder."""
	folder = safety.checkWritable(os.path.join(schemesRoot, folderNameFor(name)))
	os.makedirs(folder, exist_ok=True)
	if soundsSource and os.path.isdir(soundsSource):
		target = os.path.join(folder, "Sounds")
		os.makedirs(target, exist_ok=True)
		for fileName in os.listdir(soundsSource):
			source = os.path.join(soundsSource, fileName)
			if os.path.isfile(source):
				with open(source, "rb") as reader, open(os.path.join(target, fileName), "wb") as writer:
					writer.write(reader.read())
	payload = {
		"format": SCHEME_FORMAT,
		"version": 1,
		"name": name,
		"items": items,
		"custom": {"fonts": [], "fontSizes": [], "styles": [], "classes": []},
	}
	handle, temporary = tempfile.mkstemp(prefix=".scheme-", suffix=".tmp", dir=folder)
	with os.fdopen(handle, "w", encoding="utf-8") as stream:
		json.dump(payload, stream, ensure_ascii=False, indent="\t")
	os.replace(temporary, os.path.join(folder, "scheme.json"))
	return folder


def writeSchemePackage(path: str, name: str, items: dict, soundsSource: str) -> None:
	"""A ``.classicspeech-scheme`` package for ClassicSpeech's Import scheme button."""
	safety.checkWritable(path)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	payload = {
		"format": PACKAGE_FORMAT,
		"version": 1,
		"name": name,
		"items": items,
		"custom": {"fonts": [], "fontSizes": [], "styles": [], "classes": []},
	}
	with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
		package.writestr(PACKAGE_MANIFEST, json.dumps(payload, ensure_ascii=False, indent="\t"))
		if soundsSource and os.path.isdir(soundsSource):
			for fileName in sorted(os.listdir(soundsSource)):
				source = os.path.join(soundsSource, fileName)
				if os.path.isfile(source):
					package.write(source, "Sounds/" + fileName)


def setSchemeSwitches(section, activeScheme: str | None, enable: bool) -> None:
	"""Choose ClassicSpeech's active scheme and turn schemes on, as its settings dialog does."""
	switches = _loadJson(section.get("schemeData", "{}"), {})
	if not isinstance(switches, dict):
		switches = {}
	switches["version"] = 2
	if activeScheme:
		switches["activeScheme"] = activeScheme
	if enable:
		switches["enabled"] = True
	switches.setdefault("enabled", False)
	switches.setdefault("activeScheme", "Default")
	section["schemeData"] = json.dumps(switches, ensure_ascii=False, separators=(",", ":"))
