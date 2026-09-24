# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""JAWS keystrokes that do one thing with Insert and another with Caps Lock as the JAWS key.

In the JAWS Laptop layout Caps Lock is the JAWS key, but Insert still works for many desktop
keystrokes: Insert+J opens the JAWS window while Caps Lock+J says the previous word, and Insert+H
lists keystrokes while Caps Lock+H says the sentence. NVDA calls both keys NVDA+J, so one gesture in
gestures.ini can't do both. The Caps Lock keystroke keeps the gesture (see ``keyPlan``), and the
assistant's global plugin runs the Insert keystroke's command itself when the NVDA key held down
is Insert: NVDA tells them apart by the key in ``gesture.modifiers``.

The table is kept in state.json by the migration (and worked out once for migrations made by
version 1.3 and earlier, see ``repairOnce``). Each entry remembers the user's input gestures for
those keys when it was made; once the user assigns the keystroke to something else in NVDA's
Input Gestures dialog, their choice runs for Insert too.
"""

from __future__ import annotations

import importlib

STATE_KEY = "insertKeys"
VERSION_KEY = "insertKeysVersion"
#: 1: version 1.4 worked out the Insert keystrokes.
VERSION = 1
_FIELDS = ("gesture", "module", "className", "script")


def _log():
	from logHandler import log

	return log


def normalize(identifier: str) -> str:
	"""A gesture identifier as NVDA normalizes it (``inputCore.normalizeGestureIdentifier``)."""
	prefix, _sep, main = str(identifier).strip().lower().partition(":")
	return f"{prefix}:{'+'.join(sorted(main.split('+')))}"


def load(stateData) -> dict:
	"""The usable entries of the table in state.json, by normalized gesture."""
	table = stateData.get(STATE_KEY) if isinstance(stateData, dict) else None
	if not isinstance(table, dict):
		return {}
	result = {}
	for identifier, entry in table.items():
		if isinstance(entry, dict) and all(isinstance(entry.get(field), str) and entry.get(field) for field in _FIELDS):
			result[normalize(identifier)] = entry
	return result


def userScripts(gesture: str) -> list[str]:
	"""``module.Class.script`` for each binding of the keys of ``gesture`` in the user's gestures.ini."""
	import inputCore

	from . import nvdaApply

	found = set()
	try:
		for identifier, scripts in getattr(inputCore.manager.userGestureMap, "_map", {}).items():
			if not nvdaApply._sameKeys(identifier, gesture):
				continue
			for module, className, script in scripts:
				found.add(f"{module}.{className}.{script}")
	except Exception:
		pass
	return sorted(found)


def toState(keys, userScriptsFor=None) -> dict:
	"""The table for state.json from ``keyPlan.InsertKey`` items."""
	table = {}
	for key in keys:
		table[normalize(key.gesture)] = {
			"gesture": key.gesture,
			"module": key.module,
			"className": key.className,
			"script": key.script,
			"description": key.description,
			"jawsKey": key.jawsKey,
			"jawsScript": key.jawsScript,
			"capsLockKey": key.capsLockKey,
			"capsLockScript": key.capsLockScript,
			"userScripts": list(userScriptsFor(key.gesture)) if userScriptsFor is not None else [],
		}
	return table


def insertHeld(gesture) -> bool:
	"""Whether the NVDA key held down for a keyboard gesture is Insert (numpad or extended), not Caps Lock."""
	modifiers = getattr(gesture, "modifiers", None)
	if not modifiers:
		return False
	try:
		import keyboardHandler
		import winUser
	except Exception:
		return False
	for vkCode, extended in list(modifiers):
		try:
			if vkCode == winUser.VK_INSERT and keyboardHandler.isNVDAModifierKey(vkCode, extended):
				return True
		except Exception:
			continue
	return False


def entryFor(gesture, table: dict):
	"""The table entry for a keyboard gesture made with Insert as the NVDA key, or None."""
	if not table or not insertHeld(gesture):
		return None
	for identifier in getattr(gesture, "normalizedIdentifiers", ()) or ():
		entry = table.get(normalize(identifier))
		if entry is not None:
			return entry
	return None


def userChanged(entry: dict, currentUserScripts) -> bool:
	"""Whether the user bound these keys to something new since the entry was made."""
	recorded = set(entry.get("userScripts") or [])
	return bool(set(currentUserScripts) - recorded)


def resolve(entry: dict):
	"""The script of the object NVDA would run the entry's command on now, or None.

	The same objects NVDA asks for a script, in its order: browse mode (unless in focus mode, as NVDA
	does), the focused control and its ancestors, then NVDA's global commands.
	"""
	import api
	import globalCommands

	try:
		cls = getattr(importlib.import_module(entry["module"]), entry["className"])
	except Exception:
		return None
	name = f"script_{entry['script']}"
	focus = api.getFocusObject()
	treeInterceptor = getattr(focus, "treeInterceptor", None) if focus is not None else None
	candidates = []
	if treeInterceptor is not None:
		candidates.append(treeInterceptor)
	if focus is not None:
		candidates.append(focus)
		try:
			candidates.extend(reversed(api.getFocusAncestors()))
		except Exception:
			pass
	candidates.append(globalCommands.commands)
	for obj in candidates:
		if not isinstance(obj, cls):
			continue
		function = getattr(obj, name, None)
		if function is None:
			continue
		if obj is treeInterceptor and getattr(obj, "passThrough", False) and not getattr(function, "ignoreTreeInterceptorPassThrough", False):
			continue
		return function
	return None


def scriptFor(gesture, table: dict):
	"""The command to run for a keystroke made with Insert, or None to let NVDA find one as usual."""
	entry = entryFor(gesture, table)
	if entry is None:
		return None
	if userChanged(entry, userScripts(entry["gesture"])):
		return None
	try:
		return resolve(entry)
	except Exception:
		_log().debugWarning("jawsMigrator: the Insert keystroke's command could not be found", exc_info=True)
		return None


def describe(entry: dict) -> str:
	"""How the report and the keystroke helper describe an entry."""
	return (
		f"{entry.get('jawsKey')}: {entry.get('description') or entry.get('script')}, when you hold Insert. "
		f"With Caps Lock, {entry.get('capsLockKey')} ({entry.get('capsLockScript')}) works as before."
	)


def planFromJaws(jkm, jawsLayout: str, layouts, nvdaLayout: str | None, overrideConflicts: bool = False) -> list:
	"""The Insert keystrokes for a JAWS key map, as a migration plans them. In NVDA only."""
	from . import keyPlan, nvdaApply

	plan = keyPlan.planKeys(
		jkm,
		jawsLayout,
		boundScripts=nvdaApply.gestureBoundScripts,
		scriptExists=nvdaApply.scriptExists,
		overrideConflicts=overrideConflicts,
		layouts=layouts or None,
		nvdaLayout=nvdaLayout,
	)
	return plan.insertKeys


def repairOnce(keymapFiles, announce, done=None) -> None:
	"""Once, after updating from version 1.3 or earlier: work out the Insert keystrokes of the last migration.

	``keymapFiles()`` returns ``(jkm, JAWS layout in use)`` or None. Only the assistant's own table in
	state.json changes; NVDA's settings and gestures.ini are not touched. ``done()`` is called at the end.
	"""
	from . import debugLog, state

	try:
		if state.get(VERSION_KEY) >= VERSION:
			return
		migrated = state.get("lastMigration") or {}
		layouts = migrated.get("keyboardLayouts") if isinstance(migrated, dict) else None
		if not layouts:
			# No keystrokes were migrated, so there are none to add.
			state.set(VERSION_KEY, VERSION)
			return
		found = keymapFiles()
		if found is None:
			debugLog.note("the Insert keystrokes of the last migration can't be worked out: JAWS's key map was not found")
			state.set(VERSION_KEY, VERSION)
			return
		jkm, jawsLayout = found
		import config

		nvdaLayout = config.conf["keyboard"]["keyboardLayout"]
		keys = planFromJaws(jkm, jawsLayout, layouts, nvdaLayout, bool(migrated.get("overrideConflicts")))
		table = toState(keys, userScripts)
		state.update({STATE_KEY: table, VERSION_KEY: VERSION})
		debugLog.section("The Insert keystrokes of the JAWS Laptop layout")
		for key in keys:
			debugLog.note(f"{key.gesture} with Insert -> {key.module}.{key.className}.{key.script} (JAWS {key.jawsKey}={key.jawsScript}); Caps Lock keeps {key.capsLockKey}={key.capsLockScript}")
		if keys:
			example = next((key for key in keys if key.script == "showGui"), keys[0])
			announce(
				f"JAWS Migration Assistant: {len(keys)} keystrokes of the JAWS Laptop layout now work with Insert as in JAWS, "
				f"such as {example.jawsKey}, {example.description.lower()}. Caps Lock keystrokes work as before.",
			)
	except Exception:
		debugLog.error("the Insert keystrokes could not be worked out")
	finally:
		if done is not None:
			done()
