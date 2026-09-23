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
  matching NVDA voice or variant, and its pitch and rate changes are applied to
  the migrated voice. When the person is missing, the alias's fallback is used,
  as JAWS does.

Must run in NVDA's main thread, with the target synthesizer active.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile

from . import nvdaApply, safety, schemeMap, voices, wavUtil

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
	"""Turns JAWS persons, pitches and rates into NVDA values for one synthesizer.

	This base class works from the voices NVDA's configuration and the registry
	describe, without loading the synthesizer. ``LiveVoiceResolver`` works with the
	synthesizer NVDA is speaking with and records its native values too.
	"""

	def __init__(self, driverName: str, driverDescription: str, jawsSynth: voices.JawsSynthInfo, baseValues: dict, knownVoices=None, knownVariants=None):
		self.driverName = driverName
		self.driverDescription = driverDescription or driverName
		self.jawsSynth = jawsSynth
		self.baseValues = dict(baseValues)
		self.voices = dict(knownVoices or {})
		self.variants = dict(knownVariants or {})

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

	def record(self, voiceId: str | None, variantId: str | None, values: dict) -> dict:
		"""A ClassicSpeech record: the voice and variant to select, then the changes."""
		baseline = {}
		if voiceId:
			baseline["voice"] = voiceId
		if variantId:
			baseline["variant"] = variantId
		overrides = {key: value for key, value in values.items() if value is not None}
		return {"baseline": baseline, "overrides": overrides}

	def contextRecord(self, profile: voices.VoiceProfile, context: voices.VoiceContext) -> tuple[dict, str]:
		values = voices.scaledVoiceSettings(profile, context)
		voiceId, variantId = self.person(context.voiceName)
		note = context.voiceName or "current voice"
		if context.voiceName and not (voiceId or variantId):
			note = f"{context.voiceName} is not available in {self.driverDescription}; the current voice is used"
		return self.record(voiceId, variantId, values), note

	def aliasRecord(self, aliasValue: str) -> tuple[dict, str]:
		groups = voices.parseVoiceAlias(aliasValue)
		chosen = None
		voiceId = variantId = None
		for group in groups:
			if group["person"] == "*":
				chosen = group
				break
			voiceId, variantId = self.person(group["person"])
			if voiceId or variantId:
				chosen = group
				break
		note = ""
		if chosen is None:
			chosen = groups[0]
			note = f"{chosen['person']} is not available in {self.driverDescription}; the current voice is used"
		values = {}
		for key, parameter in (("pitch", self.jawsSynth.pitch), ("rate", self.jawsSynth.rate)):
			base = self.baseValues.get(key)
			if base is None:
				continue
			values[key] = voices.applyDelta(base, chosen[key], parameter)
		return self.record(voiceId, variantId, values), note or (chosen["person"] if chosen["person"] != "*" else "current voice")


class LiveVoiceResolver(VoiceResolver):
	"""A resolver for the synthesizer NVDA is speaking with, recording each voice's native values."""

	def __init__(self, synth, jawsSynth: voices.JawsSynthInfo, baseValues: dict):
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
		super().__init__(synth.name, synth.description, jawsSynth, baseValues, knownVoices, knownVariants)
		self.synth = synth

	def record(self, voiceId: str | None, variantId: str | None, values: dict) -> dict:
		return nvdaApply.voiceRecord(self.synth, voiceId, variantId, values)


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
				if value is None or voices.aliasIsNeutral(value):
					continue
				record, note = resolver.aliasRecord(value)
				bySynth[resolver.driverName] = record
				if note and "not available" in note:
					notes.append(f"{itemId} ({resolver.driverDescription}): {note}")
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
