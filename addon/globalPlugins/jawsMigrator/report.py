# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""The migration report: what changed, what was kept, and what could not move.

The report is written as HTML, with a heading for each part so it is quick to
move through in browse mode, and as plain text. It is kept with the migration's
other files in ``jawsMigrator\\migrations\\<date>`` in NVDA's settings folder.
"""

from __future__ import annotations

import collections
import datetime
import html
import os

from . import jawsIndex, managers, safety, settingsMap, voices


def _e(text) -> str:
	return html.escape(str(text), quote=True)


class _Builder:
	def __init__(self):
		self.html = []
		self.text = []

	def heading(self, level: int, text: str):
		self.html.append(f"<h{level}>{_e(text)}</h{level}>")
		self.text.append("")
		self.text.append(("=" if level <= 2 else "-") * 3 + " " + text)

	def paragraph(self, text: str):
		self.html.append(f"<p>{_e(text)}</p>")
		self.text.append(text)

	def items(self, lines, limit: int | None = None):
		lines = list(lines)
		shown = lines if limit is None else lines[:limit]
		if not shown:
			return
		self.html.append("<ul>")
		for line in shown:
			self.html.append(f"<li>{_e(line)}</li>")
			self.text.append(f"  - {line}")
		if limit is not None and len(lines) > limit:
			more = f"... and {len(lines) - limit} more."
			self.html.append(f"<li>{_e(more)}</li>")
			self.text.append(f"  {more}")
		self.html.append("</ul>")


def build(plan, result) -> tuple[str, str]:
	"""Return ``(html, text)`` for a migration."""
	options = plan.options
	index = plan.index
	facts = plan.facts
	b = _Builder()
	b.heading(1, "JAWS Migration Assistant report")
	b.paragraph(f"Created {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} on {facts.windows}, NVDA {facts.nvdaVersion}.")
	b.paragraph(f"Migrated from {index.jaws.displayName}, language {options.language}, {jawsIndex.SOURCE_LABELS.get(options.scope, options.scope)}.")
	target = f'the NVDA configuration profile "{options.profileName}"' if options.target == "profile" else "NVDA's normal configuration"
	b.paragraph(f"Settings were written to {target}.")
	if result.error:
		b.heading(2, "The migration did not finish")
		b.paragraph(result.error)
	if result.rolledBack:
		b.paragraph("Your previous NVDA settings were put back from the backup, so nothing was changed.")
	if result.messages:
		b.heading(2, "Messages")
		b.items(result.messages)

	if result.succeeded:
		b.heading(2, "JAWS")
		b.paragraph(safety.UNINSTALL_NOTE)
	b.heading(2, "Safety copies")
	if result.backup is not None:
		b.paragraph(f"Backup of your NVDA settings (restore it from NVDA menu, Tools, JAWS Migration Assistant): {result.backup.path}")
		info = result.backup
		if info.version >= 2:
			from . import backup as backupModule

			b.paragraph(
				f"It holds NVDA's whole settings folder: {len(info.files):,} files ({backupModule.sizeText(info.totalSize)}), including "
				f"{len(info.addons)} add-ons and their settings. {backupModule.sizeText(info.copiedSize)} were copied; the rest are "
				"shared with the previous backup." + (" It is kept for good, as your NVDA before the first JAWS migration." if info.original else ""),
			)
			if info.skipped:
				b.paragraph("These files were in use by another program and could not be backed up:")
				b.items((f"{item['relative']}: {item['reason']}" for item in info.skipped), limit=50)
	if result.archiveFolder:
		b.paragraph(f"Copy of your JAWS settings: {result.archiveFolder}")
	b.paragraph(f"Files made by this migration: {result.outputFolder}")

	# Settings Center
	b.heading(2, "Settings Center")
	nvdaChanges = [c for c in result.applied if c.target == settingsMap.NVDA]
	classicChanges = [c for c in result.applied if c.target == settingsMap.CLASSIC_SPEECH]
	b.paragraph(f"{len(nvdaChanges)} NVDA settings and {len(classicChanges)} ClassicSpeech settings were set.")
	b.heading(3, "NVDA settings")
	b.items(f"{change.label} (from {change.source})" for change in nvdaChanges)
	if classicChanges:
		b.heading(3, "ClassicSpeech settings")
		b.items(change.label for change in classicChanges)
	if result.failed:
		b.heading(3, "Settings NVDA did not accept")
		b.items(f"{change.label}: {error}" for change, error in result.failed)
	notMigrated = plan.settings.notMigrated
	if notMigrated:
		b.heading(3, "JAWS options with no NVDA equivalent")
		bySection = collections.OrderedDict()
		for item in notMigrated:
			bySection.setdefault(item.section, []).append(item)
		lines = []
		for section, items in bySection.items():
			if section.lower() in ("options", "html", "formsmode", "nonjcfoptions", "outputmodes", "virtualcursorverbosity", "braille"):
				lines.extend(f"[{section}] {item.key}={item.value}: {item.reason}" for item in items)
			else:
				lines.append(f"[{section}]: {len(items)} entries. {items[0].reason}")
		b.items(lines, limit=300)

	# Applications
	if plan.appSettings or plan.sleepCandidates:
		b.heading(2, "Settings for single applications")
		for profileName, executables, count in result.appProfiles:
			b.paragraph(f'Profile "{profileName}" ({count} settings) turns on in: {", ".join(executables)}.')
		if options.sleepApps:
			b.paragraph("NVDA now sleeps, as JAWS did, in: " + ", ".join(options.sleepApps) + ". Change this in NVDA's settings, JAWS Migration Assistant.")

	# Voices
	b.heading(2, "Voices")
	if plan.voiceProfile is None:
		b.paragraph("No JAWS voice profile was found.")
	else:
		b.paragraph(f"JAWS voice profile: {plan.voiceProfileName}, synthesizer {voices.synthInfo(plan.jawsSynthName).label}.")
		b.items(f"{voices.CONTEXT_LABELS.get(name, name)}: {context.describe()}" for name, context in plan.voiceContexts.items())
		chosen = plan.chosenVoice
		if chosen is not None:
			b.paragraph(f"NVDA now uses {chosen.label} ({chosen.reason}).")
		else:
			b.paragraph("NVDA's synthesizer and voice were not changed.")
		if result.voiceProfilesWritten:
			b.heading(3, "ClassicSpeech Voice Profiles")
			b.items(f"{category}: JAWS {voices.CONTEXT_LABELS.get(context, context)} ({note})" for category, context, note in result.voiceProfilesWritten)
		if plan.aliases:
			b.heading(3, "JAWS voice aliases")
			b.items(f"{name} = {value}" for name, value in plan.aliases.items())
	eloquence = voices.eloquenceAvailable(facts.synths, facts.sapiVoices)
	if eloquence:
		b.paragraph("Eloquence and IBM ViaVoice engines NVDA can use: " + "; ".join(eloquence[:10]) + ("..." if len(eloquence) > 10 else ""))

	# Synthesizers
	b.heading(2, "JAWS synthesizers and their NVDA equivalents")
	lines = []
	for synth in index.synths:
		options_ = voices.findNvdaEquivalents(synth.shortName, "", facts.synths, facts.sapiVoices, facts.oneCoreVoices, limit=3)
		where = "; ".join(option.label for option in options_) if options_ else "no equivalent found on this computer"
		lines.append(f"{synth.longName}{' (remote sessions)' if synth.remoteOnly else ''}: {where}")
	b.items(lines)

	# Schemes
	if result.schemesWritten:
		b.heading(2, "Speech and sounds schemes in ClassicSpeech")
		for name, count, folder, notes in result.schemesWritten:
			active = " (turned on)" if name == options.activeClassicScheme else ""
			b.paragraph(f"{name}{active}: {count} items.")
			b.items(notes, limit=20)

	# Dictionaries
	if plan.dictionaries:
		b.heading(2, "Dictionary Manager")
		b.paragraph(f"{result.dictionaryEntries} rules added to NVDA's default dictionary, {result.voiceDictionaryEntries} to the voice dictionary.")
		for dictionaryPlan in plan.dictionaries:
			skipped = collections.Counter(item.reason for item in dictionaryPlan.conversion.skipped)
			b.paragraph(f"{dictionaryPlan.label}: {len(dictionaryPlan.defaultEntries) + len(dictionaryPlan.voiceEntries)} rules converted.")
			b.items(f"{count} skipped: {reason}" for reason, count in skipped.most_common())

	# Symbols
	if plan.symbols:
		b.heading(2, "Punctuation and symbols")
		b.paragraph(f"{result.symbols} symbols written to NVDA's symbol pronunciation, from {', '.join(plan.symbolSources)}.")

	# Keyboard
	b.heading(2, "Keyboard Manager and Navigation Quick Keys")
	b.paragraph(f"{result.gesturesAdded} JAWS keystrokes became NVDA input gestures. gestures.ini was backed up first.")
	if plan.keyboardLayouts:
		chosenLayouts = plan.chosenKeyboardLayouts() if plan.options.keyboard else []
		found = ", ".join(layout.name + (" (in use)" if layout.id == plan.jawsKeyboardLayout else "") for layout in plan.keyboardLayouts)
		b.paragraph(f"JAWS keyboard layouts found: {found}. Keystrokes brought over from: {', '.join(layout.name for layout in chosenLayouts) or 'none'}.")
		layout = plan.nvdaKeyboardLayout() if plan.options.settings else ""
		b.paragraph(f"NVDA's keyboard layout: {layout}." if layout else "NVDA's keyboard layout was left as it was.")
	b.items((binding.label + f" [{binding.gesture}]" for binding in plan.keys.bindings), limit=400)
	skippedKinds = collections.Counter(item.kind for item in plan.keys.skipped)
	labels = {
		"same": "already the same in NVDA",
		"conflict": "NVDA uses the keystroke for something else",
		"noEquivalent": "JAWS commands NVDA does not have",
		"unconvertible": "keystrokes NVDA cannot represent (layered, braille, MAGic)",
		"passthrough": "standard Windows keys NVDA handles itself",
		"otherLayout": "for JAWS keyboard layouts that were not chosen",
		"duplicate": "already taken by the keystrokes of another chosen JAWS keyboard layout",
		"quickNavOff": "quick navigation letters not chosen",
		"leasey": "Leasey keystrokes, ignored",
	}
	b.items(f"{count} {labels.get(kind, kind)}" for kind, count in skippedKinds.most_common())
	conflicts = [item for item in plan.keys.skipped if item.kind == "conflict"]
	if conflicts:
		b.heading(3, "Keystrokes kept for NVDA")
		b.items((f"{item.jawsKey} ({item.jawsScript}): {item.reason}" for item in conflicts), limit=200)
	missing = [item for item in plan.keys.skipped if item.kind == "noEquivalent"]
	if missing:
		b.heading(3, "JAWS commands without an NVDA equivalent")
		b.items((f"{item.jawsKey}: {item.jawsScript}" for item in missing), limit=200)
	if plan.keys.applicationKeys:
		b.heading(3, "Keystrokes in application key maps")
		for name, entries in plan.keys.applicationKeys.items():
			b.paragraph(f"{name}: " + "; ".join(f"{key}={script}" for key, script in entries[:40]))

	# Sounds
	b.heading(2, "Sounds")
	if options.sounds and result.soundsCopied:
		b.items(f"{choice.event.label}: {choice.jawsName} ({how})" for choice, _path, how in result.soundsCopied)
	else:
		b.paragraph("NVDA's own sounds were kept.")
	b.paragraph(f"{len(index.wavFiles())} JAWS sound files were found.")

	# Scripts
	if plan.scripts:
		b.heading(2, "Your JAWS scripts")
		b.paragraph("JAWS scripts cannot run in NVDA. They are kept in the archive; look for an NVDA add-on that does the same, or ask an NVDA add-on developer.")
		b.items(f"{name}: " + ", ".join(scripts) for name, scripts in plan.scripts)

	# Managers
	b.heading(2, "Every JAWS manager")
	counts = collections.Counter(f.managerId for f in index.filesFor(options.scope))
	for manager in managers.MANAGERS:
		b.heading(3, manager.name)
		b.paragraph(f"In JAWS: {manager.jawsPurpose}")
		b.paragraph(f"In NVDA: {manager.nvdaResult}")
		b.paragraph(f"Files found: {counts.get(manager.id, 0)}.")

	# Recommended add-ons
	b.heading(2, "Recommended add-ons")
	for addon in managers.RECOMMENDED_ADDONS:
		chosen = addon.addonId in options.addonsToInstall
		b.paragraph(f"{addon.name}: {addon.why} " + ("You chose to install it." if chosen else f"If it is not installed: {addon.ifNotInstalled}"))

	# Index summary
	b.heading(2, "Index of JAWS settings")
	b.items(f"{label}: {count} files" + (f", {items} entries" if items else "") for label, count, items in index.summaryByManager(options.scope))
	if index.leasey.found:
		b.paragraph("Leasey was found and its settings were ignored: " + "; ".join(index.leasey.evidence[:5]))

	body = "\n".join(b.html)
	page = (
		'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
		"<title>JAWS Migration Assistant report</title>\n"
		"<style>body{font-family:Segoe UI,Arial,sans-serif;max-width:60em;margin:1em auto;padding:0 1em;line-height:1.5}</style>\n"
		f"</head>\n<body>\n{body}\n</body>\n</html>\n"
	)
	return page, "\n".join(b.text).strip() + "\n"


def writeReport(plan, result) -> str:
	page, text = build(plan, result)
	safety.checkWritable(result.outputFolder)
	os.makedirs(result.outputFolder, exist_ok=True)
	htmlPath = os.path.join(result.outputFolder, "report.html")
	with open(htmlPath, "w", encoding="utf-8") as stream:
		stream.write(page)
	with open(os.path.join(result.outputFolder, "report.txt"), "w", encoding="utf-8") as stream:
		stream.write(text)
	try:
		from . import state

		state.set("lastReport", htmlPath)
	except Exception:
		pass
	return htmlPath
