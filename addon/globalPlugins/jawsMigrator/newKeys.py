# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Once after an update: the JAWS keystrokes of commands the assistant learned since the last migration.

A migration gives JAWS's keystrokes to the NVDA commands that do the same (see keyPlan and jawsKeyMap). A JAWS command
the assistant learns later, such as Insert+Control+V, which says the program's version (version 1.30, see appVersion),
has no keystroke for someone who migrated before: its keystroke was left out then, as nothing in NVDA did the same.

So once after the update, a little after NVDA starts, the assistant plans the keystrokes of those JAWS commands as the
last migration planned its own: from the JAWS key map on the computer, for the JAWS keyboard layouts that migration
brought over, and with a keystroke NVDA uses for something else only when that migration was allowed to take NVDA's
keystrokes. Insert+Control+V is NVDA's keystroke for its speech settings, so it says the program's version only then;
Control+Insert+Windows+V, which NVDA doesn't use, copies the version details either way. Another add-on's keystroke is
taken only in the same way. A keystroke you gave a command of your own in NVDA's Input Gestures dialog stays yours, even
where that migration was allowed to take NVDA's keystrokes: you chose it after that migration. NVDA's settings are
backed up first, the debug log lists what was added and what wasn't, and NVDA says which keystrokes now work.

Without a migration of keystrokes, nothing is added: a migration adds them with the others. A migration made by this
version counts them as done (see migrator).
"""

from __future__ import annotations

import threading

from . import debugLog, jawsKeyMap, keyPlan, nvdaEnv

#: The JAWS commands the assistant learned since its first migrations: their name (lower case) -> the version that
#: brought them, and what NVDA says their keystroke now does.
NEW_SCRIPTS = {
	"sayappversion": ("1.30", "the name and version of the program you are in; twice, the version details"),
	"showversiondetails": ("1.30", "the version details"),
	"putversiondetailsonclipboard": ("1.30", "copy the version details"),
}
#: The JAWS commands of NEW_SCRIPTS that are done: their keystrokes added, or none to add (state.json).
STATE_KEY = "newKeysAdded"


def doneScripts(stateData) -> set:
	value = stateData.get(STATE_KEY) if isinstance(stateData, dict) else None
	return {str(name).lower() for name in value} if isinstance(value, list) else set()


def pending(stateData) -> list:
	"""The JAWS commands whose keystrokes are still to be added after an update."""
	finished = doneScripts(stateData)
	return sorted(name for name in NEW_SCRIPTS if name not in finished)


def _markDone(scripts) -> None:
	from . import state

	state.set(STATE_KEY, sorted(doneScripts(state.load()) | set(scripts)))


def planNewKeys(jkm, jawsLayout: str, migration: dict, scripts, boundScripts=None, scriptExists=None, nvdaLayout=None) -> keyPlan.KeyPlan:
	"""The keystrokes of the JAWS commands ``scripts``, planned as the last migration (``migration``, as state.json has
	it) planned its own: its JAWS keyboard layouts and its choice about NVDA's own keystrokes."""
	plan = keyPlan.planKeys(
		jkm,
		jawsLayout,
		boundScripts=boundScripts,
		scriptExists=scriptExists,
		overrideConflicts=bool(migration.get("overrideConflicts")),
		layouts=migration.get("keyboardLayouts") or None,
		nvdaLayout=nvdaLayout,
	)
	wanted = {str(name).lower() for name in scripts}

	def isWanted(item) -> bool:
		return jawsKeyMap.normalizeScriptName(item.jawsScript) in wanted

	plan.bindings = [binding for binding in plan.bindings if isWanted(binding)]
	plan.skipped = [item for item in plan.skipped if isWanted(item)]
	if boundScripts is not None:
		# A migration may take a keystroke from a command of your own, when you let it take NVDA's; you gave this one yours
		# after that migration, so it stays yours.
		kept = []
		for binding in plan.bindings:
			yours = sorted({str(entry[2]) for entry in boundScripts(binding.gesture) if len(entry) > 4 and entry[4] == "user" and entry[2]})
			if yours:
				reason = f"you gave this keystroke a command of your own in NVDA's Input Gestures dialog ({', '.join(yours)})"
				plan.skipped.append(keyPlan.SkippedKey(binding.jawsKey, binding.jawsScript, binding.section, reason, keyPlan.SKIP_CONFLICT))
			else:
				kept.append(binding)
		plan.bindings = kept
	# An Insert keystroke of the Laptop layout that runs another command than Caps Lock's would need the migration's
	# table of them (see insertKeys); none of these commands has one in JAWS's key maps.
	plan.insertKeys = []
	return plan


def announcement(bindings: list) -> str:
	parts = []
	order = list(NEW_SCRIPTS)
	for binding in sorted(bindings, key=lambda binding: order.index(jawsKeyMap.normalizeScriptName(binding.jawsScript))):
		what = NEW_SCRIPTS.get(jawsKeyMap.normalizeScriptName(binding.jawsScript), ("", binding.description))[1]
		parts.append(f"{keyPlan.describeGesture(binding.gesture)}, {what}")
	count = len(bindings)
	return f"JAWS Migration Assistant: {count} more JAWS {'keystroke works' if count == 1 else 'keystrokes work'} in NVDA. " + ". ".join(parts) + "."


def addOnce(keymapFiles, announce, done=None) -> None:
	"""Once after an update: add the keystrokes of the JAWS commands learned since the last migration.

	Main thread; the backup runs in the background. ``keymapFiles()`` returns ``(JAWS's key map, the JAWS layout in
	use)`` or None; ``announce(message)`` tells the user, and ``done()`` is called on the main thread at the end,
	whether or not anything was added.
	"""
	from . import migrator

	finished = migrator.callOnce(done)
	started = False
	try:
		started = _start(keymapFiles, announce, finished)
	except Exception:
		debugLog.error("the keystrokes of JAWS commands new since the last migration could not be added")
	finally:
		if not started:
			finished()


def _start(keymapFiles, announce, finished) -> bool:
	"""Start adding; True when a backup started in the background, which calls ``finished`` at its end."""
	from . import state

	todo = pending(state.load())
	if not todo or not nvdaEnv.shouldWriteToDisk():
		return False
	migration = state.get("lastMigration")
	if not isinstance(migration, dict) or not migration.get("keyboardLayouts"):
		# No keystrokes were migrated; a migration adds these with the others.
		_markDone(todo)
		return False
	found = keymapFiles()
	if found is None:
		debugLog.note("the keystrokes of JAWS commands new since the last migration weren't added: JAWS's key map was not found")
		_markDone(todo)
		return False
	jkm, jawsLayout = found
	import config

	from . import nvdaApply

	plan = planNewKeys(jkm, jawsLayout, migration, todo, nvdaApply.gestureBoundScripts, nvdaApply.scriptExists, config.conf["keyboard"]["keyboardLayout"])
	debugLog.section("Keystrokes of JAWS commands new since the last migration")
	for item in plan.skipped:
		debugLog.note(f"not added: {item.jawsKey}={item.jawsScript} [{item.section}]: {item.reason}")
	if not plan.bindings:
		_markDone(todo)
		return False

	def finish(outcome):
		try:
			_finish(outcome)
		finally:
			finished()

	def _finish(outcome):
		if isinstance(outcome, Exception):
			debugLog.note(f"the backup failed, so no keystroke was added; they are tried again next time NVDA starts: {outcome}")
			return
		added, failed = nvdaApply.addGestures(plan.bindings)
		for binding in plan.bindings:
			debugLog.note(f"{binding.gesture} -> {binding.module}.{binding.className}.{binding.script} (JAWS {binding.jawsKey}={binding.jawsScript}, [{binding.section}])")
		for binding, error in failed:
			debugLog.note(f"not added: {binding.gesture}: {error}")
		if failed:
			debugLog.note("not every keystroke could be added; they are tried again next time NVDA starts")
		else:
			_markDone(todo)
		debugLog.note(f"added {added} keystrokes; backup {getattr(outcome, 'path', '')}")
		addedBindings = [binding for binding in plan.bindings if binding not in [item for item, _error in failed]]
		if addedBindings:
			announce(announcement(addedBindings))

	def work():
		from . import migrator

		try:
			outcome = migrator._backupFirst("Before adding the keystrokes of JAWS commands new since the last migration")
		except Exception as error:
			debugLog.error("the backup before adding keystrokes failed")
			outcome = error
		import wx

		wx.CallAfter(finish, outcome)

	threading.Thread(target=work, name="jawsMigratorNewKeys", daemon=True).start()
	return True
