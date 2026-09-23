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

from .. import backup, classicSounds, jawsIndex, managers, migrator, nvdaEnv, safety, selection, systemCheck, voices
from .common import BORDER, TITLE, messageBox, openFile, readOnlyText, showText, speak

KEEP_VOICE_LABEL = "Don't change NVDA's synthesizer or voice"
LEAVE_SCHEME_LABEL = "Leave ClassicSpeech's current scheme"


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

	def text(self, label: str):
		control = wx.StaticText(self.parentForControls(), label=label)
		self.box.Add(control, flag=wx.EXPAND | wx.TOP, border=6)
		return control

	def labeled(self, label: str, control, proportion=0):
		self.box.Add(wx.StaticText(self.parentForControls(), label=label), flag=wx.TOP, border=6)
		self.box.Add(control, proportion=proportion, flag=wx.EXPAND | wx.TOP, border=2)
		if self.firstControl is None:
			self.firstControl = control
		return control

	def build(self, parent):
		pass

	def selectButtons(self, checkList, isAvailable=None):
		"""Add Select all and Select none buttons that work on ``checkList``."""
		row = wx.BoxSizer(wx.HORIZONTAL)
		selectAll = wx.Button(self.parentForControls(), label="Select &all")
		selectNone = wx.Button(self.parentForControls(), label="Select n&one")
		row.Add(selectAll, flag=wx.RIGHT, border=6)
		row.Add(selectNone)
		self.box.Add(row, flag=wx.TOP, border=4)

		def setAll(checked: bool):
			count = 0
			for index in range(checkList.GetCount()):
				if isAvailable is not None and not isAvailable(index):
					continue
				checkList.Check(index, checked)
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
		self.checks = self.labeled("&System check results:", readOnlyText(parent))
		self.checks.SetValue(systemCheck.checksAsText(systemCheck.runChecks(facts)))
		candidates = facts.jawsWithSettings or facts.jaws
		self.installations = candidates
		self.jawsChoice = self.labeled("JAWS &version to migrate from:", wx.Choice(parent, choices=[j.displayName + ("" if j.programInstalled else " (settings only)") for j in candidates]))
		self.jawsChoice.SetSelection(0 if candidates else wx.NOT_FOUND)
		self.languageChoice = self.labeled("JAWS settings &language:", wx.Choice(parent))
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
		self.paths.SetLabel(
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
		self.found = self.labeled("&Found on this computer:", readOnlyText(parent))
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
		self.note = self.text("")
		self.list = self.labeled("&Migrate these:", wx.CheckListBox(parent, size=(640, 280)), proportion=1)
		self.selectButtons(self.list)
		self.keys = []
		self.sleepChoice = None

	def onShow(self):
		plan = self.plan
		if plan is None:
			return
		options = plan.options
		if self.sleepChoice is None:
			self.sleepChoice = list(options.sleepApps) if options.selectionApplied else [name for name, _exes in plan.sleepCandidates]
		self.note.SetLabel(
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
			entries.append(("appProfiles", f"Settings for single applications: {len(plan.appSettings)} NVDA profiles that turn on in those applications", options.appProfiles))
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


class TargetPage(Page):
	title = "Where the JAWS settings go"

	def build(self, parent):
		self.radio = wx.RadioBox(
			parent,
			label="&Put the JAWS settings:",
			choices=[
				"In a separate NVDA configuration profile; your normal settings stay as they are (recommended)",
				"In NVDA's normal configuration, replacing the matching settings",
			],
			majorDimension=1,
			style=wx.RA_SPECIFY_COLS,
		)
		self.add(self.radio)
		self.name = self.labeled("Profile &name:", wx.TextCtrl(parent, value=migrator.DEFAULT_PROFILE_NAME))
		self.atStartup = self.add(wx.CheckBox(parent, label="Turn the profile on &every time NVDA starts"))
		self.atStartup.SetValue(True)
		self.now = self.add(wx.CheckBox(parent, label="Turn the profile on &now, when the migration finishes"))
		self.now.SetValue(True)
		self.radio.Bind(wx.EVT_RADIOBOX, lambda event: self._update())
		self._update()

	def _update(self):
		enabled = self.radio.GetSelection() == 0
		for control in (self.name, self.atStartup, self.now):
			control.Enable(enabled)

	def canLeave(self) -> bool:
		if self.radio.GetSelection() == 0:
			name = self.name.GetValue().strip()
			if not name or any(character in name for character in '\\/:*?"<>|'):
				messageBox('Type a profile name without any of these characters: \\ / : * ? " < > |', TITLE, wx.OK | wx.ICON_ERROR, self.wizard)
				self.name.SetFocus()
				return False
		return True

	def collect(self, options):
		options.target = migrator.TARGET_PROFILE if self.radio.GetSelection() == 0 else migrator.TARGET_NORMAL
		options.profileName = self.name.GetValue().strip() or migrator.DEFAULT_PROFILE_NAME
		options.activateAtStartup = self.atStartup.GetValue()
		options.activateNow = self.now.GetValue()


class VoicePage(Page):
	title = "Voices"

	def build(self, parent):
		self.summary = self.labeled("JAWS voice profile in &use:", readOnlyText(parent, size=(640, 120)))
		self.choice = self.labeled("NVDA &voice for your JAWS voice:", wx.Choice(parent))
		self.profiles = self.labeled(
			"JAWS voice &profiles to migrate (each becomes the settings of its NVDA synthesizer):",
			wx.CheckListBox(parent, size=(640, 180)),
			proportion=1,
		)
		self.selectButtons(self.profiles, lambda index: self.plan.profiles[index].option is not None)
		self.profileNames = []

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
		self.text("ClassicSpeech is installed, so JAWS voice profiles, voice aliases and speech and sounds schemes can be copied into it.")
		self.schemes = self.labeled("JAWS speech and sound &schemes to copy:", wx.CheckListBox(parent, size=(640, 200)), proportion=1)
		self.selectButtons(self.schemes)
		self.active = self.labeled("Scheme to &turn on in ClassicSpeech:", wx.Choice(parent))
		self.voicesBox = self.add(wx.CheckBox(parent, label="Copy JAWS voice profiles and voice aliases into ClassicSpeech &Voice Profiles"))
		self.voicesBox.SetValue(True)
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
		choices = [LEAVE_SCHEME_LABEL] + self.schemeNames
		self.active.SetItems(choices)
		wanted = plan.options.activeClassicScheme
		self.active.SetSelection(choices.index(wanted) if wanted in choices else 0)

	def collect(self, options):
		options.schemes = [name for i, name in enumerate(self.schemeNames) if self.schemes.IsChecked(i)]
		options.classicSchemes = bool(options.schemes)
		selection = self.active.GetStringSelection()
		options.activeClassicScheme = "" if selection == LEAVE_SCHEME_LABEL else selection
		options.classicVoices = self.voicesBox.GetValue()
		options.classicSettings = self.settingsBox.GetValue()


class SoundsPage(Page):
	title = "Sound effects"

	def build(self, parent):
		self.details = self.labeled("&JAWS sounds for NVDA's sounds:", readOnlyText(parent, size=(640, 180)))
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
			wx.CheckListBox(parent, size=(640, 100)),
		)
		self.layoutButtons = self.selectButtons(self.layouts)
		self.nvdaLayout = self.labeled("NVDA keyboard la&yout after the migration:", wx.Choice(parent, choices=[label for _value, label in NVDA_LAYOUTS]))
		self.nvdaLayout.Bind(wx.EVT_CHOICE, self._onNvdaLayout)
		self.layouts.Bind(wx.EVT_CHECKLISTBOX, lambda event: self.onChecksChanged())
		self.layoutIds = []
		self._shownFor = None
		self._nvdaLayoutChosen = False
		self.quickNav = self.add(wx.CheckBox(parent, label="Use JAWS &quick navigation letters in browse mode"))
		self.quickNav.SetValue(True)
		self.override = self.add(wx.CheckBox(parent, label="When NVDA already uses a keystroke for something else, use the JAWS &command instead"))
		self.details = self.labeled("&Keystrokes that will be added:", readOnlyText(parent, size=(640, 220)), proportion=1)
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

	def _showNvdaLayout(self):
		value = self.plan.nvdaKeyboardLayout()
		values = [value for value, _label in NVDA_LAYOUTS]
		self.nvdaLayout.SetSelection(values.index(value) if value in values else len(values) - 1)

	def _onNvdaLayout(self, event):
		self._nvdaLayoutChosen = True
		self.plan.options.nvdaKeyboardLayout = NVDA_LAYOUTS[self.nvdaLayout.GetSelection()][0]
		self._replan()

	def onChecksChanged(self):
		self.plan.options.keyboardLayouts = self._checkedLayouts()
		if not self._nvdaLayoutChosen:
			# NVDA's layout follows the JAWS layouts chosen until the user picks one.
			self._showNvdaLayout()
		self._replan()

	def _update(self):
		enabled = self.migrate.GetValue()
		for control in (self.layouts, *self.layoutButtons, self.nvdaLayout, self.quickNav, self.override):
			control.Enable(enabled)

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
		nvdaLayout = plan.nvdaKeyboardLayout()
		for layout in plan.chosenKeyboardLayouts():
			if nvdaLayout and layout.nvdaLayout != nvdaLayout:
				lines.append(f"Note: the {layout.name} keystrokes only work when NVDA's keyboard layout is {layout.nvdaLayout} (NVDA menu, Preferences, Settings, Keyboard).")
		if lines:
			lines.append("")
		lines.append(f"{len(plan.keys.bindings)} keystrokes will be added:")
		lines.extend(f"  {binding.label} [{binding.gesture}]" for binding in plan.keys.bindings)
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
		if self._nvdaLayoutChosen:
			options.nvdaKeyboardLayout = NVDA_LAYOUTS[self.nvdaLayout.GetSelection()][0]


class AddonsPage(Page):
	title = "Recommended add-ons"

	def build(self, parent):
		self.text(
			"These add-ons from the NVDA Add-on Store do things NVDA does not do on its own, which JAWS users often rely on. "
			"Choose the ones to install; NVDA downloads them from the Add-on Store, checks them, and installs them after the migration. "
			"They start after NVDA restarts.",
		)
		self.boxes = {}
		for addon in managers.RECOMMENDED_ADDONS:
			state = nvdaEnv.addonState(addon.addonId, self.wizard.facts.addons)
			if state is not None and state.usable:
				self.text(f"{addon.name} is already installed ({state.version}). {addon.why}")
				continue
			box = self.add(wx.CheckBox(parent, label=f"Install &{addon.name}" if len(self.boxes) == 0 else f"Install {addon.name}"))
			self.boxes[addon.addonId] = box
			self.text(f"What it does: {addon.why}")
			self.text(f"If you don't install it: {addon.ifNotInstalled}")

	def focus(self):
		if self.boxes:
			next(iter(self.boxes.values())).SetFocus()
		else:
			self.wizard.nextButton.SetFocus()

	def collect(self, options):
		options.addonsToInstall = [addonId for addonId, box in self.boxes.items() if box.GetValue()]


class SummaryPage(Page):
	title = "Ready to migrate"

	def build(self, parent):
		self.summary = self.labeled("&What will happen:", readOnlyText(parent, size=(640, 300)), proportion=1)

	def onShow(self):
		self.summary.SetValue(self.wizard.summaryText())

	def focus(self):
		self.summary.SetFocus()
		self.summary.SetInsertionPoint(0)


class ProgressPage(Page):
	title = "Migrating"

	def build(self, parent):
		self.log = self.labeled("&Progress:", readOnlyText(parent, size=(640, 300)), proportion=1)

	def append(self, message: str):
		self.log.AppendText(message + "\n")

	def focus(self):
		self.log.SetFocus()


class DonePage(Page):
	title = "Finished"

	def build(self, parent):
		self.result = self.labeled("&Result:", readOnlyText(parent, size=(640, 300)), proportion=1)
		self.openReport = self.add(wx.Button(parent, label="Open the migration &report"))
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
		if result and result.reportPath and not openFile(result.reportPath):
			messageBox(f"The report is at {result.reportPath}", TITLE, parent=self.wizard)

	def _onOpenFolder(self, event):
		result = self.wizard.result
		if result and result.outputFolder:
			openFile(result.outputFolder)

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
		self.SetMinSize((720, 520))
		self.SetSize((760, 600))
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
		self.Layout()
		speak(stepText)
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
					_log().exception("jawsMigrator: the saved choice of items could not be applied")
				outcome = plan
			except Exception as error:
				_log().exception("jawsMigrator: indexing failed")
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
		chosen = plan.chosenVoice
		if options.voice:
			lines.append(f"Voice: {chosen.label}." if chosen else "NVDA's synthesizer and voice are not changed.")
			selected = plan.selectedProfiles()
			lines.append(f"{len(selected)} JAWS voice profiles are migrated: " + ", ".join(p.name for p in selected) + ".")
		if plan.classicSpeech and (options.classicSchemes or options.classicVoices):
			lines.append(f"ClassicSpeech gets {len(plan.selectedSchemes()) if options.classicSchemes else 0} schemes" + (" and the JAWS voice profiles and voice aliases." if options.classicVoices else "."))
			if options.activeClassicScheme:
				lines.append(f"The scheme {options.activeClassicScheme} is turned on in ClassicSpeech.")
		if options.appProfiles and plan.appSettings:
			lines.append(f"{len(plan.appSettings)} application profiles are made.")
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
		if not plan.classicSpeech:
			lines.append("NVDA keeps its own sounds: JAWS sounds play through ClassicSpeech, which is not installed.")
		else:
			lines.append("JAWS sounds play in place of NVDA's sounds, through ClassicSpeech; NVDA's own sounds are copied first." if options.sounds else "NVDA keeps its own sounds.")
			if options.allSounds and plan.index.wavFiles():
				lines.append(f"All {len(classicSounds.uniqueSounds(plan.index.wavFiles()))} JAWS sounds are copied into ClassicSpeech, as the scheme {classicSounds.JAWS_SOUNDS_SCHEME}.")
		if options.addonsToInstall:
			names = [addon.name for addon in managers.RECOMMENDED_ADDONS if addon.addonId in options.addonsToInstall]
			lines.append("Then these add-ons are installed from the Add-on Store: " + ", ".join(names) + ".")
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
		from .. import storeAddons

		wanted = list(self.plan.options.addonsToInstall)
		self._progress("Looking the recommended add-ons up in the NVDA Add-on Store")
		language = nvdaEnv.languageCode()
		folder = nvdaEnv.addonDataDir("downloads")

		def work():
			outcome = []
			try:
				entries = storeAddons.fetchEntries(wanted, language)
			except Exception as error:
				wx.CallAfter(self._addonsDownloaded, [], [str(error)])
				return
			errors = []
			for addonId in wanted:
				entry = entries.get(addonId)
				if entry is None:
					errors.append(f"{addonId}: no version for this NVDA in the Add-on Store")
					continue
				wx.CallAfter(self._progress, f"Downloading {entry.name} {entry.version}")
				try:
					outcome.append((entry, storeAddons.download(entry, folder)))
				except Exception as error:
					errors.append(str(error))
			wx.CallAfter(self._addonsDownloaded, outcome, errors)

		threading.Thread(target=work, name="jawsMigratorAddons", daemon=True).start()

	def _addonsDownloaded(self, downloads, errors):
		from .. import storeAddons

		for entry, path in downloads:
			self._progress(f"Installing {entry.name}")
			try:
				storeAddons.install(path)
				self.result.messages.append(f"{entry.name} {entry.version} was installed from the Add-on Store; it starts after NVDA restarts.")
				self.result.restartRecommended = True
			except Exception as error:
				errors.append(f"{entry.name}: {error}")
			finally:
				try:
					os.remove(path)
				except OSError:
					pass
		for error in errors:
			self.result.messages.append(f"Add-on not installed: {error}")
		try:
			from .. import report

			self.result.reportPath = report.writeReport(self.plan, self.result)
		except Exception:
			pass
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
			lines.append("Your NVDA settings were put back as they were.")
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
		if result.backup is not None:
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
