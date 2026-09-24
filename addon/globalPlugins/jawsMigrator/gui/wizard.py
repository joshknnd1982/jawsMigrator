# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""The JAWS Migration Assistant wizard.

One dialog, one step at a time, with Back, Next and Cancel. Each step is a group
of labeled standard controls; moving to a step says its name and puts focus on its
first control. Nothing changes until the Migrate button on the last step, and the
migration itself starts by backing up NVDA's settings.
"""

from __future__ import annotations

import os
import threading

import wx

from .. import addonUpdates, backup, classicSounds, debugLog, jawsIndex, keyPlan, migrator, nvdaEnv, safety, selection, systemCheck, voices
from .common import BORDER, TITLE, WRAP_WIDTH, checkListClass, enableWithLabel, labeled, messageBox, openFile, readOnlyText, showText, speak

KEEP_VOICE_LABEL = "Don't change NVDA's synthesizer or voice"
LEAVE_SCHEME_LABEL = "None: don't turn on a scheme, ClassicSpeech stays as it is"


def _log():
	try:
		from logHandler import log

		return log
	except Exception:  # pragma: no cover
		import logging

		return logging.getLogger("jawsMigrator")


class Page(wx.Panel):
	title = ""

	def __init__(self, wizard, parent):
		super().__init__(parent)
		self.wizard = wizard
		self.box = wx.StaticBoxSizer(wx.VERTICAL, self, self.title)
		outer = wx.BoxSizer(wx.VERTICAL)
		outer.Add(self.box, proportion=1, flag=wx.EXPAND | wx.ALL, border=4)
		self.SetSizer(outer)
		self.firstControl = None
		#: Paragraphs said with the step's name when it is shown (see intro): Tab never reaches them.
		self.notes = []
		self.build(self.box.GetStaticBox())

	@property
	def plan(self) -> migrator.MigrationPlan | None:
		return self.wizard.plan

	def parentForControls(self):
		return self.box.GetStaticBox()

	def add(self, control, proportion=0):
		self.box.Add(control, proportion=proportion, flag=wx.EXPAND | wx.TOP, border=4)
		if self.firstControl is None and control.AcceptsFocus():
			self.firstControl = control
		return control

	def text(self, label: str, spoken: bool = False):
		"""A paragraph, wrapped to the width of the step. A ``spoken`` one is said with the step's name."""
		control = wx.StaticText(self.parentForControls(), label=label)
		control.Wrap(WRAP_WIDTH)
		self.box.Add(control, flag=wx.EXPAND | wx.TOP, border=6)
		if spoken:
			self.notes.append(control)
		return control

	def setText(self, control, label: str):
		"""Change a paragraph made by ``text``; an ``&`` in it, as in a folder name, is shown as it is."""
		control.SetLabel(label.replace("&", "&&"))
		control.Wrap(WRAP_WIDTH)

	def intro(self) -> str:
		"""The step's spoken paragraphs, as one line of speech."""
		return " ".join(" ".join(note.GetLabelText().split()) for note in self.notes if note.IsShown() and note.GetLabelText().strip())

	def labeled(self, label: str, controlClass, *args, proportion: int = 0, **kwargs):
		"""Make a label, then its control with ``controlClass(parent, *args, **kwargs)``; returns the control.

		The label must come first: Windows names a control after the static text just before it, and the
		label's access key moves focus to the control after it.
		"""
		control = labeled(self.parentForControls(), self.box, label, controlClass, *args, proportion=proportion, **kwargs)
		if self.firstControl is None:
			self.firstControl = control
		return control

	def build(self, parent):
		pass

	def selectButtons(self, checkList, isAvailable=None):
		"""Add Select all and Select none buttons that work on ``checkList``.

		Select all checks only the items ``isAvailable(index)`` allows, which are the ones that can be migrated;
		Select none clears every item.
		"""
		row = wx.BoxSizer(wx.HORIZONTAL)
		selectAll = wx.Button(self.parentForControls(), label="Select &all")
		selectNone = wx.Button(self.parentForControls(), label="Select n&one")
		row.Add(selectAll, flag=wx.RIGHT, border=6)
		row.Add(selectNone)
		self.box.Add(row, flag=wx.TOP, border=4)

		def setAll(checked: bool):
			count = 0
			for index in range(checkList.GetCount()):
				usable = isAvailable is None or isAvailable(index)
				checkList.Check(index, checked and usable)
				if usable or not checked:
					count += 1
			speak(f"{count} items {'selected' if checked else 'cleared'}")
			self.onChecksChanged()

		selectAll.Bind(wx.EVT_BUTTON, lambda event: setAll(True))
		selectNone.Bind(wx.EVT_BUTTON, lambda event: setAll(False))
		return selectAll, selectNone

	def onChecksChanged(self):
		pass

	def isRelevant(self) -> bool:
		return True

	def onShow(self):
		pass

	def canLeave(self) -> bool:
		return True

	def collect(self, options: migrator.MigrationOptions):
		pass

	def focus(self):
		if self.firstControl is not None:
			self.firstControl.SetFocus()


# -- steps -------------------------------------------------------------------------------------


class SystemPage(Page):
	title = "System check"

	def build(self, parent):
		facts = self.wizard.facts
		self.checks = self.labeled("&System check results:", readOnlyText)
		self.checks.SetValue(systemCheck.checksAsText(systemCheck.runChecks(facts)))
		candidates = facts.jawsWithSettings or facts.jaws
		self.installations = candidates
		self.jawsChoice = self.labeled("JAWS &version to migrate from:", wx.Choice, choices=[j.displayName + ("" if j.programInstalled else " (settings only)") for j in candidates])
		self.jawsChoice.SetSelection(0 if candidates else wx.NOT_FOUND)
		self.languageChoice = self.labeled("JAWS settings &language:", wx.Choice)
		self.jawsChoice.Bind(wx.EVT_CHOICE, lambda event: self._fillLanguages())
		self._fillLanguages()

	def _fillLanguages(self):
		index = self.jawsChoice.GetSelection()
		languages = self.installations[index].settingsLanguages if 0 <= index < len(self.installations) else []
		if not languages:
			languages = ["enu"]
		self.languageChoice.SetItems(languages)
		self.languageChoice.SetSelection(0)

	def focus(self):
		self.checks.SetFocus()
		self.checks.SetInsertionPoint(0)

	def canLeave(self) -> bool:
		problems = systemCheck.blockingProblems(self.wizard.facts)
		if problems:
			messageBox("The migration cannot run here:\n" + "\n".join(problems), TITLE, wx.OK | wx.ICON_ERROR, self.wizard)
			return False
		if self.jawsChoice.GetSelection() < 0:
			messageBox("There are no JAWS settings to migrate.", TITLE, wx.OK | wx.ICON_ERROR, self.wizard)
			return False
		return True

	@property
	def selectedJaws(self):
		return self.installations[self.jawsChoice.GetSelection()]

	@property
	def selectedLanguage(self) -> str:
		return self.languageChoice.GetStringSelection() or "enu"


class SourcePage(Page):
	title = "Which JAWS settings"

	def build(self, parent):
		self.scopes = [jawsIndex.BOTH, jawsIndex.USER, jawsIndex.SHARED]
		self.radio = wx.RadioBox(
			parent,
			label="&Migrate:",
			choices=[
				"Your settings and the shared settings, as JAWS uses them (recommended)",
				"Only your settings: just what you changed in JAWS",
				"Only the shared settings, which apply to everyone on this computer",
			],
			majorDimension=1,
			style=wx.RA_SPECIFY_COLS,
		)
		self.add(self.radio)
		self.paths = self.text("")

	def onShow(self):
		jaws = self.wizard.systemPage.selectedJaws
		language = self.wizard.systemPage.selectedLanguage
		self.setText(
			self.paths,
			f"Your JAWS settings: {jaws.userLanguageDir(language)}\n"
			f"Shared JAWS settings: {jaws.sharedLanguageDir(language)}\n"
			f"Your NVDA settings are backed up before anything changes.",
		)
		self.Layout()

	@property
	def scope(self) -> str:
		return self.scopes[self.radio.GetSelection()]


class FoundPage(Page):
	title = "What was found"

	def build(self, parent):
		self.found = self.labeled("&Found on this computer:", readOnlyText)
		self.viewIndex = self.add(wx.Button(parent, label="View the full JAWS settings &index..."))
		self.viewIndex.Bind(wx.EVT_BUTTON, self._onViewIndex)

	def onShow(self):
		plan = self.plan
		if plan is None:
			return
		facts = plan.facts
		index = plan.index
		lines = [f"{index.jaws.displayName}, language {index.language}, {jawsIndex.SOURCE_LABELS[plan.options.scope]}.", ""]
		lines.append("JAWS managers and settings:")
		for label, count, items in index.summaryByManager(plan.options.scope):
			lines.append(f"  {label}: {count} files" + (f", {items} entries" if items else ""))
		lines.append("")
		lines.append(f"{len(index.wavFiles())} JAWS sound files.")
		if index.leasey.found:
			lines.append("Leasey was found; its settings are left out.")
		lines.append("")
		lines.append("JAWS synthesizers and what NVDA can use instead:")
		for synth in index.synths:
			options = voices.findNvdaEquivalents(synth.shortName, "", facts.synths, facts.sapiVoices, facts.oneCoreVoices, limit=2)
			where = "; ".join(option.label for option in options) if options else "nothing equivalent on this computer"
			lines.append(f"  {synth.longName}{' (remote sessions only)' if synth.remoteOnly else ''}: {where}")
		eloquence = voices.eloquenceAvailable(facts.synths, facts.sapiVoices)
		lines.append("")
		if eloquence:
			lines.append(f"Eloquence or IBM ViaVoice found: {len(eloquence)}, for example {eloquence[0]}.")
		else:
			lines.append("No Eloquence or IBM ViaVoice engine was found for NVDA.")
		lines.append("")
		if plan.classicSpeech:
			lines.append(f"ClassicSpeech {facts.classicSpeech.version} is installed: JAWS voice profiles, voice aliases and schemes can be copied into it.")
		else:
			lines.append("ClassicSpeech is not installed: every setting NVDA itself supports is migrated.")
		lines.append("")
		lines.append(f"Voice profiles: {len(plan.profiles)}, of which {sum(1 for p in plan.profiles if p.available)} have an NVDA synthesizer here.")
		lines.append(f"Speech and sounds schemes: {len(plan.schemes)}.")
		lines.append(f"Settings Center options with an NVDA equivalent: {len(plan.settings.changes)}.")
		lines.append(f"Keystrokes that can become NVDA gestures: {len(plan.keys.bindings)}.")
		if plan.keyboardLayouts:
			names = ", ".join(layout.name + (" (the one your JAWS uses)" if layout.id == plan.jawsKeyboardLayout else "") for layout in plan.keyboardLayouts)
			lines.append(f"JAWS keyboard layouts: {names}.")
		self.found.SetValue("\n".join(lines))

	def focus(self):
		self.found.SetFocus()
		self.found.SetInsertionPoint(0)

	def _onViewIndex(self, event):
		if self.plan is not None:
			showText(self.wizard, "JAWS settings index", self.plan.index.asText(self.plan.options.scope))


class ChoosePage(Page):
	title = "Choose what to migrate"

	def build(self, parent):
		self.note = self.text("", spoken=True)
		self.list = self.labeled("&Migrate these:", checkListClass(), size=(640, 280), proportion=1)
		self.selectButtons(self.list)
		self.keys = []
		self.sleepChoice = None
		#: The plan sleepChoice belongs to: reading the JAWS settings again (Back, another JAWS or scope) makes a new one.
		self._sleepFor = None

	def onShow(self):
		plan = self.plan
		if plan is None:
			return
		options = plan.options
		if self._sleepFor is not plan:
			self._sleepFor = plan
			self.sleepChoice = list(options.sleepApps) if options.selectionApplied else [name for name, _exes in plan.sleepCandidates]
		self.setText(
			self.note,
			"Narrowed by your saved choice in NVDA menu, Preferences, JAWS Migration Assistant settings."
			if options.selectionApplied
			else "Tip: to pick single settings, schemes, voice profiles and voice aliases, use NVDA menu, Preferences, JAWS Migration Assistant settings.",
		)
		entries = []
		entries.append(("settings", f"Settings Center: {len(plan.settings.changes)} options with an NVDA equivalent", options.settings and bool(plan.settings.changes)))
		if plan.profiles:
			chosenProfiles = options.voiceProfiles is None or bool(options.voiceProfiles)
			entries.append(("voice", f"Voices: synthesizer, voice, rate, pitch, volume and punctuation from {sum(1 for p in plan.profiles if p.available)} voice profiles", options.voice and chosenProfiles))
		if plan.appSettings:
			entries.append(("appProfiles", f"Settings for single applications: up to {len(plan.appSettings)} NVDA profiles that turn on in those applications", options.appProfiles))
		if plan.sleepCandidates and (self.sleepChoice or not options.selectionApplied):
			names = ", ".join(self.sleepChoice or [name for name, _exes in plan.sleepCandidates])
			entries.append(("sleepApps", f"Make NVDA sleep where JAWS slept: {names}", bool(self.sleepChoice)))
		userRules = sum(len(d.defaultEntries) + len(d.voiceEntries) for d in plan.dictionaries if d.source.scope == jawsIndex.USER)
		sharedRules = sum(len(d.defaultEntries) + len(d.voiceEntries) for d in plan.dictionaries if d.source.scope == jawsIndex.SHARED)
		entries.append(("dictionaries", f"Dictionary Manager: {userRules} of your pronunciation rules", options.dictionaries))
		if sharedRules:
			entries.append(("sharedDictionaries", f"Also add {sharedRules} of Freedom Scientific's own pronunciation rules (more rules slow speech slightly)", plan.options.sharedDictionaries))
		entries.append(("symbols", f"Punctuation and symbols you changed: {len(plan.symbols)}", options.symbols))
		if plan.jawsSymbolDefaults:
			entries.append(("jawsSymbolNames", f"Use JAWS's names for all {len(plan.jawsSymbolDefaults)} punctuation symbols (exclaim, semi colon...)", plan.options.jawsSymbolNames))
		entries.append(("keyboard", f"Keyboard commands: {len(plan.keys.bindings)} JAWS keystrokes as NVDA input gestures", options.keyboard))
		entries.append(("archive", "Keep a copy of your JAWS settings with NVDA's settings (recommended)", options.archive))
		previous = {key: self.list.IsChecked(i) for i, key in enumerate(self.keys)} if self.keys else {}
		self.keys = [key for key, _label, _checked in entries]
		self.list.SetItems([label for _key, label, _checked in entries])
		for i, (key, _label, checked) in enumerate(entries):
			self.list.Check(i, previous.get(key, checked))
		self.list.SetSelection(0)

	#: Choices assumed before the list has been shown, so the step count is right from the start.
	DEFAULTS = {"voice": True, "keyboard": True}

	def checked(self, key: str) -> bool:
		if not self.keys:
			return self.DEFAULTS.get(key, False)
		return key in self.keys and self.list.IsChecked(self.keys.index(key))

	def collect(self, options):
		options.settings = self.checked("settings")
		options.voice = self.checked("voice")
		options.appProfiles = self.checked("appProfiles")
		options.sleepApps = list(self.sleepChoice or []) if self.checked("sleepApps") else []
		options.dictionaries = self.checked("dictionaries")
		options.sharedDictionaries = self.checked("sharedDictionaries")
		options.symbols = self.checked("symbols")
		options.jawsSymbolNames = self.checked("jawsSymbolNames")
		options.keyboard = self.checked("keyboard")
		options.archive = self.checked("archive")


#: Where the JAWS settings can go, in the order the Target step lists them; the first is chosen at first.
TARGET_CHOICES = (
	(migrator.TARGET_NORMAL, "In NVDA's normal configuration, replacing the matching settings (recommended)"),
	(migrator.TARGET_PROFILE, "In a separate NVDA configuration profile; your normal settings stay as they are"),
)


class TargetPage(Page):
	title = "Where the JAWS settings go"

	def build(self, parent):
		self.radio = wx.RadioBox(
			parent,
			label="&Put the JAWS settings:",
			choices=[label for _target, label in TARGET_CHOICES],
			majorDimension=1,
			style=wx.RA_SPECIFY_COLS,
		)
		self.radio.SetSelection(0)
		self.add(self.radio)
		self.text(
			"Why the normal configuration is recommended: NVDA can have only one profile turned on by hand. Add-ons such as "
			"Custom Browse Mode turn on a profile of their own and switch a JAWS settings profile off, so speech and verbosity "
			"change back and forth. Settings you change while that profile is on also go into it. Either way, NVDA's settings "
			"are backed up first.",
			spoken=True,
		)
		# Access keys: N is the Next button's.
		self.name = self.labeled("Profile na&me:", wx.TextCtrl, value=migrator.DEFAULT_PROFILE_NAME)
		self.atStartup = self.add(wx.CheckBox(parent, label="Turn the profile on &every time NVDA starts"))
		self.atStartup.SetValue(True)
		self.now = self.add(wx.CheckBox(parent, label="Turn the profile on &when the migration finishes"))
		self.now.SetValue(True)
		self.radio.Bind(wx.EVT_RADIOBOX, lambda event: self._update())
		self._update()

	@property
	def target(self) -> str:
		index = self.radio.GetSelection()
		return TARGET_CHOICES[index][0] if 0 <= index < len(TARGET_CHOICES) else TARGET_CHOICES[0][0]

	def _update(self):
		enabled = self.target == migrator.TARGET_PROFILE
		enableWithLabel(self.name, enabled)
		for control in (self.atStartup, self.now):
			control.Enable(enabled)

	def canLeave(self) -> bool:
		if self.target == migrator.TARGET_PROFILE:
			name = self.name.GetValue().strip()
			if not name or any(character in name for character in '\\/:*?"<>|'):
				messageBox('Type a profile name without any of these characters: \\ / : * ? " < > |', TITLE, wx.OK | wx.ICON_ERROR, self.wizard)
				self.name.SetFocus()
				return False
		return True

	def collect(self, options):
		options.target = self.target
		options.profileName = self.name.GetValue().strip() or migrator.DEFAULT_PROFILE_NAME
		options.activateAtStartup = self.atStartup.GetValue()
		options.activateNow = self.now.GetValue()


class VoicePage(Page):
	title = "Voices"

	def build(self, parent):
		self.summary = self.labeled("JAWS voice profile in &use:", readOnlyText, size=(640, 120))
		self.choice = self.labeled("NVDA &voice for your JAWS voice:", wx.Choice)
		self.profiles = self.labeled(
			"JAWS voice &profiles to migrate (each becomes the settings of its NVDA synthesizer):",
			checkListClass(),
			size=(640, 180),
			proportion=1,
		)
		self.selectButtons(self.profiles, self._usable)
		self.profileNames = []

	def _usable(self, index: int) -> bool:
		"""Whether the profile can be migrated, as the plan's selectedProfiles decides."""
		profilePlan = self.plan.profiles[index]
		if profilePlan.primary:
			# Your JAWS voice gets the NVDA voice chosen above, which may be none ("don't change").
			selection = self.choice.GetSelection()
			return 0 <= selection < len(self.plan.voiceOptions) and not profilePlan.sharedWith
		return profilePlan.available

	def isRelevant(self) -> bool:
		plan = self.plan
		return plan is not None and bool(plan.profiles) and self.wizard.choosePage.checked("voice")

	def onShow(self):
		plan = self.plan
		lines = []
		if plan.voiceProfile is not None:
			lines.append(f"{plan.voiceProfileName}, for {voices.synthInfo(plan.jawsSynthName).label}:")
			for name, context in plan.voiceContexts.items():
				lines.append(f"  {voices.CONTEXT_LABELS.get(name, name)}: {context.describe()}")
		eloquence = voices.eloquenceAvailable(plan.facts.synths, plan.facts.sapiVoices)
		if plan.jawsSynthName.lower() == "eloq":
			lines.append("")
			lines.append("Eloquence or IBM ViaVoice for NVDA: " + ("; ".join(eloquence[:4]) if eloquence else "none found. Install the IBMTTS add-on or an Eloquence SAPI 5 voice to keep Eloquence."))
		self.summary.SetValue("\n".join(lines))
		labels = [option.label + f" ({option.reason})" for option in plan.voiceOptions] + [KEEP_VOICE_LABEL]
		self.choice.SetItems(labels)
		keepVoice = plan.options.voiceChoice < 0 or not plan.voiceOptions
		self.choice.SetSelection(len(labels) - 1 if keepVoice else min(plan.options.voiceChoice, len(labels) - 2))
		self._fillProfiles()

	def _fillProfiles(self):
		plan = self.plan
		previous = {name: self.profiles.IsChecked(i) for i, name in enumerate(self.profileNames)} if self.profileNames else {}
		self.profileNames = [p.name for p in plan.profiles]
		self.profiles.SetItems([("Your JAWS voice: " if p.primary else "") + p.describe() for p in plan.profiles])
		wanted = plan.options.voiceProfiles
		for i, profilePlan in enumerate(plan.profiles):
			default = (profilePlan.available or profilePlan.primary) if wanted is None else profilePlan.name in wanted
			self.profiles.Check(i, previous.get(profilePlan.name, default))

	def collect(self, options):
		selection = self.choice.GetSelection()
		options.voiceChoice = selection if 0 <= selection < len(self.plan.voiceOptions) else -1
		options.voiceProfiles = [name for i, name in enumerate(self.profileNames) if self.profiles.IsChecked(i)]
		# The primary profile's NVDA voice follows the choice above.
		for profilePlan in self.plan.profiles:
			if profilePlan.primary:
				profilePlan.option = self.plan.chosenVoice


class ClassicSpeechPage(Page):
	title = "ClassicSpeech"

	def build(self, parent):
		self.text("ClassicSpeech is installed, so JAWS voice profiles, voice aliases and speech and sounds schemes can be copied into it.", spoken=True)
		self.schemes = self.labeled("JAWS speech and sound &schemes to copy:", checkListClass(), size=(640, 200), proportion=1)
		self.selectButtons(self.schemes)
		self.schemes.Bind(wx.EVT_CHECKLISTBOX, self._onSchemeChecked)
		self.active = self.labeled("Scheme to &turn on in ClassicSpeech (only if you choose one):", wx.Choice)
		self.voicesBox = self.add(wx.CheckBox(parent, label="Also use the voices JAWS uses for the JAWS cursor and messages, as ClassicSpeech &Voice Profiles"))
		self.voicesBox.SetValue(False)
		self.text(
			"Only the person carries over, such as Glen. Your NVDA rate, pitch and volume apply everywhere, so speech stays even. "
			"Unless you choose a scheme, NVDA keeps speaking and sounding as it does now.",
			spoken=True,
		)
		self.activeNames = []
		self.settingsBox = self.add(wx.CheckBox(parent, label="Copy JAWS verbosity, number and text &processing settings into ClassicSpeech"))
		self.settingsBox.SetValue(True)
		self.schemeNames = []
		self._firstShow = True

	def isRelevant(self) -> bool:
		return self.plan is not None and self.plan.classicSpeech

	def onShow(self):
		plan = self.plan
		previous = {name: self.schemes.IsChecked(i) for i, name in enumerate(self.schemeNames)} if self.schemeNames else {}
		self.schemeNames = [scheme.name for scheme in plan.schemes]
		labels = []
		for scheme in plan.schemes:
			voiceItems = sum(1 for item in scheme.items.values() if item.voiceAlias)
			labels.append(f"{scheme.name}: {scheme.soundCount} sounds, {voiceItems} voices")
		self.schemes.SetItems(labels)
		wanted = plan.options.schemes
		for i, name in enumerate(self.schemeNames):
			self.schemes.Check(i, previous.get(name, True if wanted is None else name in wanted))
		if self._firstShow:
			self._firstShow = False
			self.voicesBox.SetValue(plan.options.classicVoices)
			self.settingsBox.SetValue(plan.options.classicSettings)
		self._fillActive(plan.options.activeClassicScheme)

	def _activeName(self) -> str:
		index = self.active.GetSelection()
		return self.activeNames[index] if 0 <= index < len(self.activeNames) else ""

	def _fillActive(self, wanted: str):
		"""Offer the schemes being copied: only a copied scheme can be turned on."""
		jawsScheme = self.plan.jawsSchemeName()
		copied = [name for index, name in enumerate(self.schemeNames) if self.schemes.IsChecked(index)]
		self.activeNames = [""] + copied
		self.active.SetItems([LEAVE_SCHEME_LABEL] + [name + (" (the scheme JAWS uses)" if name == jawsScheme else "") for name in copied])
		self.active.SetSelection(self.activeNames.index(wanted) if wanted in self.activeNames else 0)

	def _onSchemeChecked(self, event):
		event.Skip()
		self.onChecksChanged()

	def onChecksChanged(self):
		wanted = self._activeName()
		self._fillActive(wanted)
		if wanted and wanted not in self.activeNames:
			speak(f"{wanted} is no longer turned on, as it is not copied.")

	def collect(self, options):
		options.schemes = [name for i, name in enumerate(self.schemeNames) if self.schemes.IsChecked(i)]
		options.classicSchemes = bool(options.schemes)
		options.activeClassicScheme = self._activeName()
		options.classicVoices = self.voicesBox.GetValue()
		options.classicSettings = self.settingsBox.GetValue()


class SoundsPage(Page):
	title = "Sound effects"

	def build(self, parent):
		self.details = self.labeled("&JAWS sounds for NVDA's sounds:", readOnlyText, size=(640, 180))
		self.radio = wx.RadioBox(
			parent,
			label="&Play JAWS sounds in place of NVDA's sounds?",
			choices=["No, keep NVDA's own sounds", "Yes, play the JAWS sounds, through ClassicSpeech"],
			majorDimension=1,
			style=wx.RA_SPECIFY_COLS,
		)
		self.add(self.radio)
		self.allSounds = self.add(wx.CheckBox(parent, label="&Copy every JAWS sound into ClassicSpeech"))
		self.text(
			"ClassicSpeech plays the JAWS sounds, in every one of its schemes. NVDA's own sound files are never changed, and a copy of "
			"them is kept. Switch between JAWS sounds and NVDA's own at any time with NVDA+Shift+J then S, or from NVDA menu, Tools, "
			"JAWS Migration Assistant.",
			spoken=True,
		)

	def onShow(self):
		plan = self.plan
		allSounds = classicSounds.uniqueSounds(plan.index.wavFiles())
		lines = [f"{len(allSounds)} JAWS sound files were found.", ""]
		for choice in plan.sounds:
			lines.append(f"{choice.event.label}: {choice.jawsName} (JAWS plays it for {choice.event.jawsLabel})")
		if plan.missingSounds:
			lines.append("")
			lines.extend(plan.missingSounds)
		lines.append("")
		lines.append("NVDA keeps its own sounds for starting, exiting and the Remote Access clipboard, which JAWS has no sounds for.")
		self.details.SetValue("\n".join(lines))
		self.radio.SetSelection(1 if plan.options.sounds else 0)
		self.radio.EnableItem(1, bool(plan.sounds))
		self.allSounds.SetLabel(f"&Copy all {len(allSounds)} JAWS sounds into ClassicSpeech, as the scheme {classicSounds.JAWS_SOUNDS_SCHEME}")
		self.allSounds.SetValue(plan.options.allSounds)

	def isRelevant(self) -> bool:
		# JAWS sounds play through ClassicSpeech; without it this step is left out.
		return self.plan is not None and self.plan.classicSpeech and bool(self.plan.index.wavFiles())

	def focus(self):
		self.radio.SetFocus()

	def collect(self, options):
		options.sounds = self.radio.GetSelection() == 1 and bool(self.plan.sounds)
		options.allSounds = self.allSounds.GetValue()


#: NVDA's keyboard layouts, and keeping the one NVDA uses.
NVDA_LAYOUTS = (("desktop", "Desktop"), ("laptop", "Laptop"), ("", "Keep NVDA's current keyboard layout"))


class KeysPage(Page):
	title = "Keyboard commands"

	def build(self, parent):
		self.migrate = self.add(wx.CheckBox(parent, label="&Migrate JAWS keyboard commands to NVDA input gestures (gestures.ini is backed up first)"))
		self.migrate.SetValue(True)
		self.layouts = self.labeled(
			"JAWS keyboard &layouts to bring over (each one's keystrokes work when NVDA uses the matching keyboard layout):",
			checkListClass(),
			size=(640, 100),
		)
		self.layoutButtons = self.selectButtons(self.layouts)
		self.nvdaLayout = self.labeled("NVDA keyboard la&yout after the migration:", wx.Choice, choices=[label for _value, label in NVDA_LAYOUTS])
		self.nvdaLayout.Bind(wx.EVT_CHOICE, self._onNvdaLayout)
		self.layouts.Bind(wx.EVT_CHECKLISTBOX, self._onLayoutChecked)
		self.layoutIds = []
		self._shownFor = None
		self._nvdaLayoutChosen = False
		self.quickNav = self.add(wx.CheckBox(parent, label="Use JAWS &quick navigation letters in browse mode"))
		self.quickNav.SetValue(True)
		self.override = self.add(wx.CheckBox(parent, label="When NVDA already uses a keystroke for something else, use the JAWS &command instead"))
		self.details = self.labeled("&Keystrokes that will be added:", readOnlyText, size=(640, 160), proportion=1)
		for box in (self.quickNav, self.override):
			box.Bind(wx.EVT_CHECKBOX, lambda event: self._replan())
		self.migrate.Bind(wx.EVT_CHECKBOX, lambda event: self._update())

	def isRelevant(self) -> bool:
		return self.plan is not None and self.wizard.choosePage.checked("keyboard")

	def onShow(self):
		plan = self.plan
		if self._shownFor is not plan:
			# First visit with this plan: start from the saved choice or JAWS's own layout.
			self._shownFor = plan
			self._nvdaLayoutChosen = plan.options.nvdaKeyboardLayout is not None
			self.migrate.SetValue(plan.options.keyboard)
			self.quickNav.SetValue(plan.options.quickNavLetters)
			chosen = {layout.id for layout in plan.chosenKeyboardLayouts()}
			self.layoutIds = [layout.id for layout in plan.keyboardLayouts]
			self.layouts.SetItems([layout.describe(layout.id == plan.jawsKeyboardLayout) for layout in plan.keyboardLayouts])
			for index, layout in enumerate(plan.keyboardLayouts):
				self.layouts.Check(index, layout.id in chosen)
			if self.layoutIds:
				self.layouts.SetSelection(0)
		self._showNvdaLayout()
		self._replan()

	def _checkedLayouts(self) -> list:
		return [layoutId for index, layoutId in enumerate(self.layoutIds) if self.layouts.IsChecked(index)]

	def _layoutApplies(self) -> bool:
		"""NVDA's keyboard layout is one of the Settings Center options, so it only changes when those are migrated."""
		return self.wizard.choosePage.checked("settings")

	def _showNvdaLayout(self):
		value = self.plan.nvdaKeyboardLayout() if self._layoutApplies() else ""
		values = [value for value, _label in NVDA_LAYOUTS]
		self.nvdaLayout.SetSelection(values.index(value) if value in values else len(values) - 1)

	def _onNvdaLayout(self, event):
		self._nvdaLayoutChosen = True
		self.plan.options.nvdaKeyboardLayout = NVDA_LAYOUTS[self.nvdaLayout.GetSelection()][0]
		self._replan()

	def _onLayoutChecked(self, event):
		event.Skip()
		self.onChecksChanged()

	def onChecksChanged(self):
		self.plan.options.keyboardLayouts = self._checkedLayouts()
		if not self._nvdaLayoutChosen:
			# NVDA's layout follows the JAWS layouts chosen until the user picks one.
			self._showNvdaLayout()
		self._replan()

	def _update(self):
		enabled = self.migrate.GetValue()
		enableWithLabel(self.layouts, enabled)
		for control in (*self.layoutButtons, self.quickNav, self.override):
			control.Enable(enabled)
		enableWithLabel(self.nvdaLayout, enabled and self._layoutApplies())

	def _replan(self):
		plan = self.plan
		options = plan.options
		options.quickNavLetters = self.quickNav.GetValue()
		options.overrideConflicts = self.override.GetValue()
		if self.layoutIds:
			options.keyboardLayouts = self._checkedLayouts()
		try:
			migrator.planKeyboard(plan, inNvda=True)
		except Exception:
			_log().debugWarning("jawsMigrator: keystrokes could not be planned again", exc_info=True)
		lines = []
		applies = self._layoutApplies()
		if not applies:
			lines.append(
				"NVDA's keyboard layout stays as it is: it is one of the Settings Center options, which are not being migrated. "
				"To change it here, go back to Choose what to migrate and check Settings Center.",
			)
		nvdaLayout = plan.nvdaKeyboardLayout() if applies else ""
		for layout in plan.chosenKeyboardLayouts():
			# When NVDA's layout stays as it is, it may be either one, so every layout gets the note.
			if not applies or (nvdaLayout and layout.nvdaLayout != nvdaLayout):
				lines.append(f"Note: the {layout.name} keystrokes only work when NVDA's keyboard layout is {layout.nvdaLayout} (NVDA menu, Preferences, Settings, Keyboard).")
		if lines:
			lines.append("")
		lines.append(f"{len(plan.keys.bindings)} keystrokes will be added:")
		lines.extend(f"  {binding.label} [{keyPlan.describeGesture(binding.gesture)}]" for binding in plan.keys.bindings)
		if plan.keys.insertKeys:
			lines.append("")
			lines.append(
				f"{len(plan.keys.insertKeys)} JAWS keystrokes do one thing with Insert and another with Caps Lock. NVDA can't tell the "
				"two apart, so the Caps Lock keystroke gets the gesture, and the JAWS Migration Assistant runs the Insert command when you hold Insert:",
			)
			lines.extend(f"  {key.label} [{keyPlan.describeGesture(key.gesture)}]" for key in plan.keys.insertKeys)
		same = plan.keys.countSkipped("same")
		conflicts = plan.keys.countSkipped("conflict")
		missing = plan.keys.countSkipped("noEquivalent")
		lines.append("")
		lines.append(f"{same} are already the same in NVDA. {conflicts} are kept for NVDA's own commands. {missing} JAWS commands have no NVDA equivalent; the report lists them.")
		self.details.SetValue("\n".join(lines))
		self._update()

	def collect(self, options):
		options.keyboard = self.migrate.GetValue()
		options.quickNavLetters = self.quickNav.GetValue()
		options.overrideConflicts = self.override.GetValue()
		if self.layoutIds:
			options.keyboardLayouts = self._checkedLayouts()
		if self._nvdaLayoutChosen and self._layoutApplies():
			# Otherwise the choice shows "keep", and the one made earlier is kept for when Settings Center is checked again.
			options.nvdaKeyboardLayout = NVDA_LAYOUTS[self.nvdaLayout.GetSelection()][0]


class AddonsPage(Page):
	title = "Add-ons"

	def build(self, parent):
		self.text(
			"ClassicSpeech and these add-ons do things NVDA does not do on its own, which JAWS users often rely on. "
			"The assistant always gets an add-on's newest version: ClassicSpeech from its GitHub releases, the others from "
			"the NVDA Add-on Store. After the migration, each download is checked against its published checksum and "
			"installed by NVDA; add-ons you already have are updated only when a newer version exists. They start, or "
			"switch to their new version, after NVDA restarts. What each add-on does is in the box after the check boxes.",
			spoken=True,
		)
		#: {add-on id: check box}; a checked box installs the add-on, or updates it to its newest version.
		self.boxes = {}
		#: Ids whose check box updates an add-on that is already installed.
		self.updates = set()
		about = []
		for addon in addonUpdates.neededAddons():
			status, version = addonUpdates.addonStatus(addon.addonId, self.wizard.facts.addons)
			if status == addonUpdates.MISSING:
				box = self.add(wx.CheckBox(parent, label=f"Install {addon.name}"))
				self.boxes[addon.addonId] = box
				about.append(f"{addon.name}: not installed.\nWhat it does: {addon.why}\nIf you don't install it: {addon.ifNotInstalled}")
			elif status == addonUpdates.INSTALLED:
				box = self.add(wx.CheckBox(parent, label=f"Update {addon.name} to its newest version, if there is one (you have {version})"))
				box.SetValue(True)
				self.boxes[addon.addonId] = box
				self.updates.add(addon.addonId)
				about.append(f"{addon.name} {version}: installed.\nWhat it does: {addon.why}")
			elif status == addonUpdates.DISABLED:
				about.append(f"{addon.name} {version}: installed, but turned off in NVDA's Add-on Store, so the assistant leaves it as it is.\nWhat it does: {addon.why}")
			else:
				about.append(f"{addon.name} {version}: being removed when NVDA restarts, so the assistant leaves it as it is.")
		# A wrapped read-only box: Tab reaches it, and NVDA reads it line by line.
		self.about = self.labeled(
			"&About these add-ons:",
			wx.TextCtrl,
			value="\n\n".join(about),
			style=wx.TE_MULTILINE | wx.TE_READONLY,
			size=(640, 180),
		)

	def focus(self):
		if self.boxes:
			next(iter(self.boxes.values())).SetFocus()
		else:
			self.about.SetFocus()
			self.about.SetInsertionPoint(0)

	def collect(self, options):
		options.addonsToInstall = [addonId for addonId, box in self.boxes.items() if box.GetValue()]


class SummaryPage(Page):
	title = "Ready to migrate"

	def build(self, parent):
		self.summary = self.labeled("&What will happen:", readOnlyText, size=(640, 300), proportion=1)

	def onShow(self):
		self.summary.SetValue(self.wizard.summaryText())

	def focus(self):
		self.summary.SetFocus()
		self.summary.SetInsertionPoint(0)


class ProgressPage(Page):
	title = "Migrating"

	def build(self, parent):
		self.log = self.labeled("&Progress:", readOnlyText, size=(640, 300), proportion=1)

	def append(self, message: str):
		self.log.AppendText(message + "\n")

	def focus(self):
		self.log.SetFocus()


class DonePage(Page):
	title = "Finished"

	def build(self, parent):
		self.result = self.labeled("&Result:", readOnlyText, size=(640, 300), proportion=1)
		# Access keys: R is the result's, C the Close button's.
		self.openReport = self.add(wx.Button(parent, label="Open the migration re&port"))
		self.openReport.Bind(wx.EVT_BUTTON, self._onOpenReport)
		self.openFolder = self.add(wx.Button(parent, label="Open the folder with the migration's &files"))
		self.openFolder.Bind(wx.EVT_BUTTON, self._onOpenFolder)
		self.restart = self.add(wx.Button(parent, label="Restart &NVDA now"))
		self.restart.Bind(wx.EVT_BUTTON, self._onRestart)

	def focus(self):
		self.result.SetFocus()
		self.result.SetInsertionPoint(0)

	def _onOpenReport(self, event):
		result = self.wizard.result
		if result is None:
			return
		if not result.reportPath:
			# For example when NVDA's settings could not be backed up, and the migration stopped before it began.
			messageBox("No report was written for this migration. What happened is in the result on this page.", TITLE, wx.OK | wx.ICON_INFORMATION, self.wizard)
		elif not openFile(result.reportPath):
			messageBox(f"The report is at {result.reportPath}", TITLE, parent=self.wizard)

	def _onOpenFolder(self, event):
		result = self.wizard.result
		if result is None:
			return
		folder = result.outputFolder
		if not folder or not os.path.isdir(folder) or not openFile(folder):
			messageBox(f"The folder with the migration's files could not be opened: {folder or 'there is none'}.", TITLE, wx.OK | wx.ICON_INFORMATION, self.wizard)

	def _onRestart(self, event):
		self.wizard.EndModal(wx.ID_OK)
		try:
			import core

			wx.CallLater(500, core.restart)
		except Exception:
			pass


# -- the dialog ------------------------------------------------------------------------------


class MigrationWizard(wx.Dialog):
	def __init__(self, parent, facts: systemCheck.SystemFacts):
		super().__init__(parent, title=TITLE, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.facts = facts
		self.plan: migrator.MigrationPlan | None = None
		self.result = None
		self.busy = False
		self.migration = None
		self.book = wx.Simplebook(self)
		self.systemPage = SystemPage(self, self.book)
		self.sourcePage = SourcePage(self, self.book)
		self.foundPage = FoundPage(self, self.book)
		self.choosePage = ChoosePage(self, self.book)
		self.targetPage = TargetPage(self, self.book)
		self.voicePage = VoicePage(self, self.book)
		self.classicPage = ClassicSpeechPage(self, self.book)
		self.soundsPage = SoundsPage(self, self.book)
		self.keysPage = KeysPage(self, self.book)
		self.addonsPage = AddonsPage(self, self.book)
		self.summaryPage = SummaryPage(self, self.book)
		self.progressPage = ProgressPage(self, self.book)
		self.donePage = DonePage(self, self.book)
		self.pages = [
			self.systemPage,
			self.sourcePage,
			self.foundPage,
			self.choosePage,
			self.targetPage,
			self.voicePage,
			self.classicPage,
			self.soundsPage,
			self.keysPage,
			self.addonsPage,
			self.summaryPage,
			self.progressPage,
			self.donePage,
		]
		for page in self.pages:
			self.book.AddPage(page, page.title)
		self.current = 0
		buttons = wx.BoxSizer(wx.HORIZONTAL)
		self.backButton = wx.Button(self, label="< &Back")
		self.nextButton = wx.Button(self, label="&Next >")
		self.cancelButton = wx.Button(self, wx.ID_CANCEL, label="Cancel")
		buttons.Add(self.backButton, flag=wx.RIGHT, border=6)
		buttons.Add(self.nextButton, flag=wx.RIGHT, border=6)
		buttons.Add(self.cancelButton)
		self.backButton.Bind(wx.EVT_BUTTON, self.onBack)
		self.nextButton.Bind(wx.EVT_BUTTON, self.onNext)
		self.cancelButton.Bind(wx.EVT_BUTTON, self.onCancel)
		self.Bind(wx.EVT_CLOSE, self.onClose)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.book, proportion=1, flag=wx.EXPAND | wx.ALL, border=BORDER)
		sizer.Add(buttons, flag=wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER)
		self.SetSizerAndFit(sizer)
		# Room for the largest step, within the screen (the steps fit 1366 by 768).
		fitted = self.GetSize()
		display = wx.Display.GetFromWindow(self)
		area = wx.Display(display if display != wx.NOT_FOUND else 0).GetClientArea()
		width, height = min(max(fitted.width, 760), area.width), min(max(fitted.height, 600), area.height)
		self.SetMinSize((min(720, width), min(520, height)))
		self.SetSize((width, height))
		self.CentreOnScreen()
		self.nextButton.SetDefault()
		self._show(0)

	# -- navigation --------------------------------------------------------------------

	def _relevantPages(self):
		return [i for i, page in enumerate(self.pages) if page.isRelevant()]

	def _show(self, index: int):
		self.current = index
		page = self.pages[index]
		page.onShow()
		self.book.SetSelection(index)
		stepPages = [i for i in self._relevantPages() if self.pages[i] not in (self.progressPage, self.donePage)]
		if index in stepPages and self.plan is not None:
			stepText = f"Step {stepPages.index(index) + 1} of {len(stepPages)}: {page.title}"
		elif index in stepPages:
			# The number of steps is only known once the JAWS settings have been read.
			stepText = f"Step {stepPages.index(index) + 1}: {page.title}"
		else:
			stepText = page.title
		self.SetTitle(f"{TITLE} - {stepText}")
		self.backButton.Enable(index > 0 and page not in (self.progressPage, self.donePage))
		if page is self.summaryPage:
			self.nextButton.SetLabel("&Migrate")
		elif page is self.donePage:
			self.nextButton.SetLabel("&Close")
		else:
			self.nextButton.SetLabel("&Next >")
		self.nextButton.Enable(page is not self.progressPage)
		self.cancelButton.Enable(page not in (self.progressPage, self.donePage))
		# On the last step Cancel is off, so Escape (and Alt+F4) press Close instead.
		self.SetEscapeId(self.nextButton.GetId() if page is self.donePage else wx.ID_ANY)
		self.Layout()
		# The step's explanations are static text, which Tab never reaches, so they are said with its name.
		intro = page.intro()
		speak(f"{stepText}. {intro}" if intro else stepText)
		wx.CallAfter(page.focus)

	def _neighbor(self, step: int):
		relevant = self._relevantPages()
		position = relevant.index(self.current) if self.current in relevant else 0
		target = position + step
		if 0 <= target < len(relevant):
			return relevant[target]
		return None

	def onBack(self, event):
		if self.busy:
			return
		target = self._neighbor(-1)
		if target is not None:
			if self.plan is not None:
				self.pages[self.current].collect(self.plan.options)
			self._show(target)

	def onNext(self, event):
		if self.busy:
			return
		page = self.pages[self.current]
		if page is self.donePage:
			self.EndModal(wx.ID_OK)
			return
		if not page.canLeave():
			return
		if self.plan is not None:
			page.collect(self.plan.options)
		if page is self.sourcePage:
			self._startIndexing()
			return
		if page is self.summaryPage:
			self._startMigration()
			return
		target = self._neighbor(1)
		if target is not None:
			self._show(target)

	def onCancel(self, event):
		if self.busy:
			speak("Please wait until the current step finishes.")
			return
		self.EndModal(wx.ID_CANCEL)

	def onClose(self, event):
		if self.busy:
			speak("Please wait until the current step finishes.")
			event.Veto()
			return
		event.Skip()

	def _setBusy(self, busy: bool):
		self.busy = busy
		for button in (self.backButton, self.nextButton, self.cancelButton):
			button.Enable(not busy)

	# -- indexing -----------------------------------------------------------------------

	def _startIndexing(self):
		jaws = self.systemPage.selectedJaws
		language = self.systemPage.selectedLanguage
		scope = self.sourcePage.scope
		self._setBusy(True)
		speak("Indexing your JAWS settings. This takes a few seconds.")
		facts = self.facts
		options = migrator.MigrationOptions(jaws=jaws, language=language, scope=scope)

		def work():
			try:
				index = jawsIndex.buildIndex(jaws, language, facts.leasey)
				plan = migrator.buildPlan(options, index, facts, inNvda=True)
				try:
					saved = selection.load()
					if saved.customized:
						selection.apply(plan, saved)
						migrator.planKeyboard(plan, inNvda=True)
				except Exception:
					debugLog.error("the saved choice of items could not be applied")
				outcome = plan
			except Exception as error:
				debugLog.error("indexing failed")
				outcome = error
			wx.CallAfter(self._indexed, outcome)

		threading.Thread(target=work, name="jawsMigratorIndex", daemon=True).start()

	def _indexed(self, outcome):
		self._setBusy(False)
		if isinstance(outcome, Exception):
			messageBox(f"Your JAWS settings could not be read: {outcome}", TITLE, wx.OK | wx.ICON_ERROR, self)
			self._show(self.pages.index(self.sourcePage))
			return
		self.plan = outcome
		self._show(self.pages.index(self.foundPage))

	# -- summary ------------------------------------------------------------------------

	def _backupSizeText(self) -> str:
		facts = self.facts
		files, total, new = getattr(facts, "backupFiles", -1), getattr(facts, "backupTotal", -1), getattr(facts, "backupBytes", -1)
		if min(files, total, new) < 0:
			try:
				files, total, new = backup.estimateBackup(nvdaEnv.configDir(), nvdaEnv.addonDataDir())
			except Exception:
				return ""
		if files <= 0:
			return ""
		if new < total:
			return f" The backup holds {files:,} files ({backup.sizeText(total)}); {backup.sizeText(new)} of them changed since the last backup and are copied, the rest are shared with it."
		return f" The backup copies {files:,} files ({backup.sizeText(total)})."

	def summaryText(self) -> str:
		plan = self.plan
		options = plan.options
		lines = [f"Migrate {jawsIndex.SOURCE_LABELS[options.scope]} from {plan.index.jaws.displayName}.", ""]
		lines.append(
			"First, NVDA's settings, every add-on and the add-ons' own settings are backed up, including input gestures, dictionaries, "
			"profiles, ClassicSpeech settings and NVDA's sounds, so you can go back to them at any time." + self._backupSizeText(),
		)
		if options.target == migrator.TARGET_PROFILE:
			lines.append(f'The JAWS settings go into the NVDA profile "{options.profileName}".' + (" It turns on every time NVDA starts." if options.activateAtStartup else ""))
		else:
			lines.append("The JAWS settings go into NVDA's normal configuration.")
		if options.settings:
			lines.append(f"{len(plan.finalSettingChanges())} Settings Center options are set.")
			layout = plan.nvdaKeyboardLayout()
			lines.append(f"NVDA's keyboard layout becomes {layout}." if layout else "NVDA's keyboard layout is not changed.")
		elif options.keyboard:
			lines.append("NVDA's keyboard layout is not changed: it is one of the Settings Center options, which are not migrated.")
		chosen = plan.chosenVoice
		if options.voice:
			lines.append(f"Voice: {chosen.label}." if chosen else "NVDA's synthesizer and voice are not changed.")
			selected = plan.selectedProfiles()
			lines.append(f"{len(selected)} JAWS voice profiles are migrated: " + ", ".join(p.name for p in selected) + ".")
		if plan.classicSpeech and (options.classicSchemes or options.classicVoices):
			lines.append(f"ClassicSpeech gets {len(plan.selectedSchemes()) if options.classicSchemes else 0} schemes, with the persons of the JAWS voice aliases" + (", and the voices of the JAWS cursor and messages as Voice Profiles." if options.classicVoices else "."))
			# The migration only turns a scheme on when it copies that scheme.
			copied = {scheme.name for scheme in plan.selectedSchemes()} if options.classicSchemes else set()
			active = options.activeClassicScheme if options.activeClassicScheme in copied else ""
			lines.append(f"The scheme {active} is turned on in ClassicSpeech, as you chose." if active else "No scheme is turned on: ClassicSpeech keeps speaking and sounding as it does now.")
		if options.appProfiles and plan.appSettings:
			lines.append(
				f"Up to {len(plan.appSettings)} application profiles are made; one whose settings are the same as NVDA's normal "
				"configuration isn't needed and is left out.",
			)
		if options.appProfiles and plan.appSkipped:
			lines.append(
				f"{len(plan.appSkipped)} JAWS application settings can't become NVDA profiles, such as settings for web sites; "
				"the report lists them.",
			)
		if options.sleepApps:
			lines.append("NVDA sleeps in: " + ", ".join(options.sleepApps) + ".")
		if options.dictionaries:
			count = sum(len(d.defaultEntries) + len(d.voiceEntries) for d in plan.chosenDictionaries())
			lines.append(f"{count} dictionary rules are added.")
		symbols = plan.chosenSymbols() if options.symbols else (plan.jawsSymbolDefaults if options.jawsSymbolNames else {})
		if symbols:
			lines.append(f"{len(symbols)} punctuation symbols are set.")
		if options.keyboard:
			names = [layout.name for layout in plan.chosenKeyboardLayouts()]
			if names:
				layouts = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
				lines.append(f"{len(plan.keys.bindings)} JAWS keystrokes become NVDA input gestures, including those of the {layouts} keyboard layout{'s' if len(names) > 1 else ''}.")
			else:
				lines.append(f"{len(plan.keys.bindings)} JAWS keystrokes become NVDA input gestures, from the keys every JAWS keyboard layout shares.")
			if plan.keys.insertKeys:
				lines.append(f"{len(plan.keys.insertKeys)} more work with Insert as in JAWS, such as {plan.keys.insertKeys[0].jawsKey}, while Caps Lock keeps its own command.")
		if not plan.classicSpeech:
			lines.append("NVDA keeps its own sounds: JAWS sounds play through ClassicSpeech, which is not installed.")
		else:
			lines.append("JAWS sounds play in place of NVDA's sounds, through ClassicSpeech; NVDA's own sounds are copied first." if options.sounds else "NVDA keeps its own sounds.")
			if options.allSounds and plan.index.wavFiles():
				lines.append(f"All {len(classicSounds.uniqueSounds(plan.index.wavFiles()))} JAWS sounds are copied into ClassicSpeech, as the scheme {classicSounds.JAWS_SOUNDS_SCHEME}.")
		if options.addonsToInstall:
			chosen = [addon for addon in addonUpdates.neededAddons() if addon.addonId in options.addonsToInstall]
			updates = self.addonsPage.updates
			installs = [addon.name for addon in chosen if addon.addonId not in updates]
			refreshed = [addon.name for addon in chosen if addon.addonId in updates]
			if installs:
				lines.append("Then the newest versions of these add-ons are installed: " + ", ".join(installs) + ".")
			if refreshed:
				lines.append("These add-ons are updated to their newest versions, where a newer version exists: " + ", ".join(refreshed) + ".")
		if options.archive:
			lines.append("A copy of your JAWS settings is kept with NVDA's settings.")
		lines.append("")
		lines.append("Press Migrate to start. If anything goes wrong, your NVDA settings are put back automatically.")
		return "\n".join(lines)

	# -- migrating ------------------------------------------------------------------------

	def _startMigration(self):
		for page in self.pages:
			if page.isRelevant():
				page.collect(self.plan.options)
		self._show(self.pages.index(self.progressPage))
		self._setBusy(True)
		self.migration = migrator.Migration(self.plan, progress=self._progress, done=self._migrated)
		self.migration.start()

	def _progress(self, message: str):
		self.progressPage.append(message)
		speak(message)

	def _migrated(self, result):
		self.result = result
		if result.succeeded and self.plan.options.addonsToInstall:
			self._installAddons()
			return
		self._finish()

	def _installAddons(self):
		wanted = list(self.plan.options.addonsToInstall)
		self._progress("Getting the newest versions of the add-ons")
		language = nvdaEnv.languageCode()
		folder = nvdaEnv.addonDataDir("downloads")
		addons = nvdaEnv.installedAddons()
		names = {addon.addonId: addon.name for addon in addonUpdates.neededAddons()}

		def progress(message):
			wx.CallAfter(self._progress, message)

		def work():
			try:
				fetched = addonUpdates.fetchNewest(wanted, folder, addons, language, progress=progress, names=names)
			except Exception as error:
				debugLog.error("the add-ons could not be looked up")
				fetched = addonUpdates.Fetched(errors=[str(error) or error.__class__.__name__])
			wx.CallAfter(self._addonsDownloaded, fetched)

		threading.Thread(target=work, name="jawsMigratorAddons", daemon=True).start()

	def _addonsDownloaded(self, fetched):
		for item in fetched.downloads:
			self._progress(f"Installing {item.name} {item.version}")
		messages, errors = addonUpdates.installDownloads(fetched.downloads)
		self.result.messages.extend(messages)
		self.result.messages.extend(fetched.notes)
		for error in fetched.errors + errors:
			self.result.messages.append(f"Add-on not installed: {error}")
		if messages:
			self.result.restartRecommended = True
		try:
			from .. import report

			self.result.reportPath = report.writeReport(self.plan, self.result)
		except Exception:
			debugLog.error("the report could not be written again after installing add-ons")
		self._finish()

	def _finish(self):
		self._setBusy(False)
		result = self.result
		lines = []
		if result.succeeded:
			lines.append("The migration finished.")
			lines.append("")
			lines.append(safety.UNINSTALL_NOTE)
			lines.append("")
		else:
			lines.append(result.error or "The migration did not finish.")
		if result.rolledBack:
			# What was set before the error was put back too, so none of it is listed as done.
			lines.append("Your NVDA settings were put back as they were, so none of the migration's changes were kept.")
		else:
			if result.applied:
				lines.append(f"{len(result.applied)} settings were set.")
			if result.gesturesAdded:
				lines.append(f"{result.gesturesAdded} JAWS keystrokes are now NVDA input gestures.")
			if result.dictionaryEntries or result.voiceDictionaryEntries:
				lines.append(f"{result.dictionaryEntries + result.voiceDictionaryEntries} dictionary rules were added.")
			if result.schemesWritten:
				lines.append(f"{len(result.schemesWritten)} schemes were copied into ClassicSpeech.")
			if result.voiceProfilesWritten:
				lines.append(f"{len(result.voiceProfilesWritten)} ClassicSpeech voice profile categories were written.")
			if result.nvdaSounds is not None:
				lines.append(classicSounds.statusText(result.nvdaSounds.record))
			if result.allSounds is not None:
				lines.append(f"{result.allSounds.sounds} JAWS sounds were copied into ClassicSpeech, as the scheme {classicSounds.JAWS_SOUNDS_SCHEME}.")
		lines.extend(result.messages)
		if result.backup is not None and not result.rolledBack:
			lines.append("")
			lines.append("To undo everything, use NVDA menu, Tools, JAWS Migration Assistant, Restore NVDA settings from a backup.")
		if result.restartRecommended:
			lines.append("Restart NVDA so that every change takes effect.")
		self.donePage.result.SetValue("\n".join(lines))
		self.donePage.restart.Show(bool(result.restartRecommended))
		self._show(self.pages.index(self.donePage))


def runWizard(facts: systemCheck.SystemFacts) -> None:
	import gui

	gui.mainFrame.prePopup()
	try:
		dialog = MigrationWizard(gui.mainFrame, facts)
		try:
			dialog.ShowModal()
		finally:
			dialog.Destroy()
	finally:
		gui.mainFrame.postPopup()
