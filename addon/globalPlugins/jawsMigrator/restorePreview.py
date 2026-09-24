# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""What a restore changes that a JAWS user notices, said before restoring.

A restore puts NVDA's settings back exactly as they were in the backup. For the backup taken before
the first migration, that means NVDA's own behaviour comes back where the migration had made NVDA
behave like JAWS: NVDA says "clickable" before clickable items on web pages again, its punctuation
level and speech rate go back, and so on. Uninstalling the assistant afterwards doesn't change that,
and neither ClassicSpeech nor the assistant add the words: they are NVDA's own settings.

So the restore dialog lists the noticeable settings that will change, comparing NVDA's normal
configuration now with the backup's nvda.ini, and says where each one is set, so a user who wants
to keep one knows where to change it after the restore.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

_SECTION = re.compile(r"^(\[+)\s*(.*?)\s*(\]+)$")


def readNvdaIni(path: str) -> dict:
	"""nvda.ini as nested dictionaries of text values (ConfigObj's format, with ``[[subsections]]``).

	Missing or unreadable: an empty dictionary, which is what NVDA's defaults are.
	"""
	try:
		with open(path, encoding="utf-8-sig", errors="replace") as stream:
			lines = stream.read().splitlines()
	except OSError:
		return {}
	root: dict = {}
	stack = [root]
	for raw in lines:
		line = raw.strip()
		if not line or line.startswith("#"):
			continue
		match = _SECTION.match(line)
		if match:
			depth = len(match.group(1))
			if depth != len(match.group(3)) or depth > len(stack):
				continue
			del stack[depth:]
			section = stack[-1].setdefault(match.group(2), {})
			if not isinstance(section, dict):
				section = stack[-1][match.group(2)] = {}
			stack.append(section)
			continue
		key, sep, value = line.partition("=")
		if not sep:
			continue
		value = value.strip()
		if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
			value = value[1:-1]
		stack[-1][key.strip()] = value
	return root


def _get(tree: dict, path: tuple):
	node = tree
	for part in path:
		if not isinstance(node, dict) or part not in node:
			return None
		node = node[part]
	return node


def _bool(value, default: bool) -> bool:
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	return str(value).strip().lower() in ("1", "true", "yes", "on")


def _int(value, default):
	if value is None:
		return default
	try:
		return int(str(value).strip())
	except ValueError:
		return default


_SYMBOL_LEVELS = {0: "none", 100: "some", 200: "most", 300: "all", 1000: "character"}
_MODIFIER_KEYS = ((1, "Caps Lock"), (2, "numpad Insert"), (4, "extended Insert"))


def _modifierText(value: int) -> str:
	names = [name for bit, name in _MODIFIER_KEYS if value & bit]
	return ", ".join(names) or "none"


@dataclass(frozen=True)
class Change:
	text: str


def _clickable(current: dict, backup: dict):
	path = ("documentFormatting", "reportClickable")
	now, then = _bool(_get(current, path), True), _bool(_get(backup, path), True)
	if now == then:
		return None
	if then:
		return Change(
			'NVDA says "clickable" before clickable items on web pages again, as NVDA does unless told not to (NVDA menu, '
			"Preferences, Settings, Document Formatting, the Clickable check box).",
		)
	return Change('NVDA stops saying "clickable" on web pages (NVDA menu, Preferences, Settings, Document Formatting, Clickable).')


def _symbolLevel(current: dict, backup: dict):
	path = ("speech", "symbolLevel")
	now, then = _int(_get(current, path), 100), _int(_get(backup, path), 100)
	if now == then:
		return None
	return Change(f"Punctuation level: {_SYMBOL_LEVELS.get(now, now)} becomes {_SYMBOL_LEVELS.get(then, then)} (NVDA menu, Preferences, Settings, Speech).")


def _synthAndRate(current: dict, backup: dict):
	synthNow = _get(current, ("speech", "synth")) or "auto"
	synthThen = _get(backup, ("speech", "synth")) or "auto"
	changes = []
	if synthNow != synthThen:
		changes.append(Change(f"Synthesizer: {synthNow} becomes {synthThen}."))
	elif synthThen != "auto":
		now, then = _int(_get(current, ("speech", synthThen, "rate")), 50), _int(_get(backup, ("speech", synthThen, "rate")), 50)
		if now != then:
			changes.append(Change(f"Speech rate: {now} becomes {then} (NVDA menu, Preferences, Settings, Speech)."))
	return changes


def _keyboard(current: dict, backup: dict):
	changes = []
	now, then = _get(current, ("keyboard", "keyboardLayout")) or "desktop", _get(backup, ("keyboard", "keyboardLayout")) or "desktop"
	if now != then:
		changes.append(Change(f"Keyboard layout: {now} becomes {then} (NVDA menu, Preferences, Settings, Keyboard)."))
	now, then = _int(_get(current, ("keyboard", "NVDAModifierKeys")), 6), _int(_get(backup, ("keyboard", "NVDAModifierKeys")), 6)
	if now != then:
		changes.append(Change(f"NVDA keys: {_modifierText(now)} become {_modifierText(then)}."))
	return changes


def _startExitSounds(current: dict, backup: dict):
	path = ("general", "playStartAndExitSounds")
	now, then = _bool(_get(current, path), True), _bool(_get(backup, path), True)
	if now == then:
		return None
	return Change("NVDA plays its sounds when it starts and exits again." if then else "NVDA stops playing sounds when it starts and exits.")


_CHECKS = (_clickable, _symbolLevel, _synthAndRate, _keyboard, _startExitSounds)


def changes(current: dict, backup: dict) -> list[str]:
	"""The noticeable differences between NVDA's normal configuration now and a backup's, in words."""
	found = []
	for check in _CHECKS:
		result = check(current, backup)
		if result is None:
			continue
		for change in result if isinstance(result, list) else [result]:
			found.append(change.text)
	return found


def _plain(section) -> dict:
	"""A ConfigObj section as nested dictionaries of text values."""
	result = {}
	try:
		items = list(section.items())
	except Exception:
		return result
	for key, value in items:
		result[str(key)] = _plain(value) if hasattr(value, "items") else ("" if value is None else str(value))
	return result


def currentNormalConfiguration() -> dict:
	"""NVDA's normal configuration now, as the values it holds itself. In NVDA only."""
	import config

	return _plain(config.conf.profiles[0])


def backupNvdaIni(backupPath: str) -> dict:
	return readNvdaIni(os.path.join(backupPath, "config", "nvda.ini"))


def describe(backupPath: str) -> list[str]:
	"""What restoring the backup at ``backupPath`` changes that a user notices, or [] when it can't be told."""
	try:
		return changes(currentNormalConfiguration(), backupNvdaIni(backupPath))
	except Exception:
		return []
