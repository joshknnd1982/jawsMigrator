# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Repair the ClassicSpeech voices that versions 1.0 to 1.2 of the assistant wrote.

Those versions stored the JAWS rate, pitch and volume as fixed values in every ClassicSpeech
Voice Profile category and in every voice of the schemes they made. ClassicSpeech applies such
values whenever that category or item speaks, so speech sped up, slowed down or changed pitch
in places, whatever the user had set in NVDA. From version 1.3 only the person (the voice or
variant) carries over, and the user's NVDA rate, pitch and volume apply everywhere.

This takes those fixed values out again. It only touches what those versions wrote: voices in
the schemes named "... (from JAWS)", "... (your JAWS scheme)" and "JAWS voice aliases", and
Voice Profile categories that hold all three of rate, pitch and volume, as those versions
always wrote them. A voice that then only selects the voice NVDA already speaks with is
removed. The caller backs up NVDA's settings first.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from . import classicSounds

#: Bumped when a new repair is needed; kept in state.json as "voicesRepaired".
REPAIR_VERSION = 1
STATE_KEY = "voicesRepaired"
PROSODY = ("rate", "pitch", "volume", "inflection")
_SELECTORS = ("voice", "variant")


def isAssistantScheme(name: str) -> bool:
	lowered = str(name or "").strip().lower()
	return lowered.endswith("(from jaws)") or lowered.endswith("(your jaws scheme)") or lowered == "jaws voice aliases"


def _selects(record: dict) -> dict:
	baseline = record.get("baseline") if isinstance(record.get("baseline"), dict) else {}
	overrides = record.get("overrides") if isinstance(record.get("overrides"), dict) else {}
	chosen = {key: baseline[key] for key in _SELECTORS if key in baseline}
	chosen.update({key: value for key, value in overrides.items() if key in _SELECTORS})
	return chosen


def stripRecord(record, configured: dict | None) -> tuple[dict | None, bool]:
	"""``(record, changed)``: the record without fixed prosody, or None when it no longer changes anything.

	``configured`` is NVDA's saved settings for the record's synthesizer, or None when unknown.
	"""
	if not isinstance(record, dict) or not isinstance(record.get("overrides"), dict):
		return record, False
	overrides = {key: value for key, value in record["overrides"].items() if key not in PROSODY}
	changed = len(overrides) != len(record["overrides"])
	repaired = {"baseline": dict(record.get("baseline") or {}), "overrides": overrides}
	chosen = _selects(repaired)
	extra = {key: value for key, value in overrides.items() if key not in _SELECTORS}
	if not extra:
		if not chosen:
			return None, True
		if configured is not None and all(str(configured.get(key)) == str(value) for key, value in chosen.items()):
			return None, True
	return repaired, changed


@dataclass
class RepairResult:
	schemes: list = field(default_factory=list)
	items: int = 0
	voiceProfiles: list = field(default_factory=list)
	failed: list = field(default_factory=list)

	@property
	def changed(self) -> bool:
		return bool(self.items or self.voiceProfiles)


def schemesNeedingRepair(configDir: str) -> list[str]:
	"""Folders of the assistant's schemes that still have fixed rate, pitch or volume in a voice."""
	found = []
	for folderName, schemeName, data in classicSounds.schemeFolders(classicSounds.schemesRoot(configDir)):
		if not isAssistantScheme(schemeName):
			continue
		for settings in data["items"].values():
			voice = settings.get("voice") if isinstance(settings, dict) else None
			records = (voice or {}).get("bySynth") if isinstance(voice, dict) else None
			if isinstance(records, dict) and any(isinstance(r, dict) and any(key in (r.get("overrides") or {}) for key in PROSODY) for r in records.values()):
				found.append(folderName)
				break
	return found


def repairSchemes(configDir: str, configuredFor, result: RepairResult, log=None) -> None:
	"""Take fixed prosody out of the voices in the assistant's schemes. ``configuredFor(synth)`` gives NVDA's saved settings."""
	root = classicSounds.schemesRoot(configDir)
	for folderName, schemeName, data in classicSounds.schemeFolders(root):
		if not isAssistantScheme(schemeName):
			continue
		items = data["items"]
		changed = False
		for itemId in list(items):
			settings = items[itemId]
			voice = settings.get("voice") if isinstance(settings, dict) else None
			records = voice.get("bySynth") if isinstance(voice, dict) else None
			if not isinstance(records, dict):
				continue
			for synthName in list(records):
				repaired, recordChanged = stripRecord(records[synthName], configuredFor(synthName))
				if not recordChanged:
					continue
				changed = True
				result.items += 1
				if repaired is None:
					del records[synthName]
				else:
					records[synthName] = repaired
				if log:
					log(f"  {schemeName}: {itemId} ({synthName}) -> {'voice removed, it changed nothing but rate, pitch or volume' if repaired is None else 'person kept: ' + json.dumps(_selects(repaired))}")
			if not records:
				del settings["voice"]
			if not settings:
				del items[itemId]
		if changed:
			try:
				classicSounds._writeScheme(os.path.join(root, folderName), data)
				result.schemes.append(schemeName)
			except OSError as error:
				result.failed.append(f"{schemeName}: {error}")


def voiceProfilesNeedingRepair(section) -> bool:
	return bool(_profileRepairs(_registry(section)))


def _registry(section) -> dict:
	raw = section.get("voiceProfileData", "{}")
	if isinstance(raw, dict):
		return dict(raw)
	try:
		value = json.loads(raw or "{}")
	except (TypeError, ValueError):
		return {}
	return value if isinstance(value, dict) else {}


def _profileRepairs(registry: dict) -> list[tuple[str, str]]:
	"""``(synth, category)`` of the Voice Profile records versions 1.0 to 1.2 wrote."""
	found = []
	for synthName, categories in registry.items():
		if not isinstance(categories, dict):
			continue
		for category, record in categories.items():
			overrides = record.get("overrides") if isinstance(record, dict) else None
			if isinstance(overrides, dict) and {"rate", "pitch", "volume"} <= set(overrides):
				found.append((synthName, category))
	return found


def repairVoiceProfiles(section, configuredFor, result: RepairResult, log=None) -> None:
	registry = _registry(section)
	for synthName, category in _profileRepairs(registry):
		repaired, _changed = stripRecord(registry[synthName][category], configuredFor(synthName))
		if repaired is None:
			del registry[synthName][category]
		else:
			registry[synthName][category] = repaired
		result.voiceProfiles.append(f"{synthName}: {category}")
		if log:
			log(f"  Voice Profile {category} ({synthName}) -> {'removed, it only held rate, pitch and volume' if repaired is None else 'person kept: ' + json.dumps(_selects(repaired))}")
	if result.voiceProfiles:
		for synthName in [name for name, categories in registry.items() if isinstance(categories, dict) and not categories]:
			del registry[synthName]
		section["voiceProfileData"] = json.dumps(registry, ensure_ascii=False, separators=(",", ":"))
