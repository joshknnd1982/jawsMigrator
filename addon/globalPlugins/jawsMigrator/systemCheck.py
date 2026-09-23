# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""The System Check: what this computer has, and whether a migration can run on it.

Every fact the assistant later relies on is gathered here first, from the
running system rather than from assumptions: the Windows version and
architecture, the NVDA copy (installed, portable or Microsoft Store) and whether
its configuration folder can be written, each JAWS version with its program,
settings folders and languages, whether JAWS is running, Leasey, ClassicSpeech,
and the synthesizers NVDA can use. Problems are reported in plain language with
what the assistant will do about them.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field

from . import jawsDetect, nvdaEnv

OK = "ok"
NOTE = "note"
WARNING = "warning"
PROBLEM = "problem"

LEVEL_LABELS = {OK: "OK", NOTE: "Note", WARNING: "Warning", PROBLEM: "Problem"}

#: NVDA 2026.1 is the first version this add-on supports.
MINIMUM_NVDA = (2026, 1)
#: Windows 10 22H2.
MINIMUM_WINDOWS_BUILD = 19045
#: Room needed for a backup of NVDA's settings and sounds plus the migration archive.
MINIMUM_FREE_BYTES = 200 * 1024 * 1024


@dataclass
class Check:
	level: str
	title: str
	detail: str = ""

	def asText(self) -> str:
		text = f"{LEVEL_LABELS.get(self.level, self.level)}: {self.title}"
		if self.detail:
			text += f"\n    {self.detail}"
		return text


@dataclass
class SystemFacts:
	windows: str = ""
	windowsBuild: int = 0
	architecture: str = ""
	userName: str = ""
	appData: str = ""
	nvdaVersion: str = ""
	nvdaVersionTuple: tuple = (0, 0, 0)
	nvdaInstalled: bool = False
	nvdaAppX: bool = False
	nvdaSecure: bool = False
	configDir: str = ""
	configWritable: bool = False
	freeBytes: int = -1
	profiles: list = field(default_factory=list)
	gesturesFileExists: bool = False
	jaws: list = field(default_factory=list)
	jawsRunning: bool = False
	leasey: jawsDetect.LeaseyInfo = field(default_factory=jawsDetect.LeaseyInfo)
	classicSpeech: nvdaEnv.ClassicSpeechInfo = field(default_factory=nvdaEnv.ClassicSpeechInfo)
	addons: list = field(default_factory=list)
	synths: list = field(default_factory=list)
	currentSynth: dict = field(default_factory=dict)
	sapiVoices: list = field(default_factory=list)
	oneCoreVoices: list = field(default_factory=list)
	speechPlatformVoices: list = field(default_factory=list)

	@property
	def installedJaws(self) -> list:
		return [jaws for jaws in self.jaws if jaws.programInstalled]

	@property
	def jawsWithSettings(self) -> list:
		return [jaws for jaws in self.jaws if jaws.hasUserSettings or jaws.hasSharedSettings]


def windowsArchitecture() -> str:
	machine = (os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE") or platform.machine() or "").upper()
	return {"AMD64": "64-bit (x64)", "ARM64": "64-bit (ARM64)", "X86": "32-bit (x86)"}.get(machine, machine or "unknown")


def gatherFacts(includeVoices: bool = True) -> SystemFacts:
	"""Collect everything the System Check reports. Runs in NVDA's main thread (it asks SAPI for voices)."""
	facts = SystemFacts()
	facts.windows = jawsDetect.windowsVersionDescription()
	facts.windowsBuild = jawsDetect.windowsBuild()
	facts.architecture = windowsArchitecture()
	facts.userName = jawsDetect.currentUserName()
	facts.appData = jawsDetect.appDataFolder()
	facts.nvdaVersion = nvdaEnv.nvdaVersion()
	facts.nvdaVersionTuple = nvdaEnv.nvdaVersionTuple()
	facts.nvdaInstalled = nvdaEnv.isInstalledCopy()
	facts.nvdaAppX = nvdaEnv.isAppX()
	facts.nvdaSecure = nvdaEnv.isSecureMode()
	facts.configDir = nvdaEnv.configDir()
	facts.configWritable = nvdaEnv.shouldWriteToDisk() and nvdaEnv.isWritable(nvdaEnv.addonDataDir())
	facts.freeBytes = nvdaEnv.freeSpace(facts.configDir)
	facts.profiles = nvdaEnv.profileNames()
	facts.gesturesFileExists = os.path.isfile(os.path.join(facts.configDir, "gestures.ini"))
	facts.jaws = jawsDetect.findJawsInstallations()
	facts.jawsRunning = jawsDetect.isJawsRunning()
	facts.leasey = jawsDetect.detectLeasey(facts.jaws)
	facts.addons = nvdaEnv.installedAddons()
	facts.classicSpeech = nvdaEnv.classicSpeechInfo(facts.addons)
	facts.synths = nvdaEnv.synthList()
	facts.currentSynth = nvdaEnv.currentSynth()
	if includeVoices:
		facts.sapiVoices = nvdaEnv.sapi5Voices()
		facts.oneCoreVoices = nvdaEnv.oneCoreVoices()
		facts.speechPlatformVoices = nvdaEnv.speechPlatformVoices()
	return facts


def _folderReadable(folder: str) -> bool | None:
	"""True or False for an existing folder, None when it does not exist."""
	if not os.path.isdir(folder):
		return None
	try:
		os.listdir(folder)
		return True
	except OSError:
		return False


def runChecks(facts: SystemFacts, profileName: str = "JAWS settings") -> list[Check]:
	checks: list[Check] = []
	add = checks.append

	# Windows
	level = OK if facts.windowsBuild == 0 or facts.windowsBuild >= MINIMUM_WINDOWS_BUILD else WARNING
	detail = f"Signed in as {facts.userName}." if facts.userName else ""
	if level == WARNING:
		detail += " This Windows is older than Windows 10 22H2, which NVDA 2026 expects; some features may not work."
	add(Check(level, f"Windows: {facts.windows}, {facts.architecture}", detail.strip()))
	if facts.appData.startswith("\\\\"):
		add(
			Check(
				NOTE,
				"Your Windows profile is on a network (roaming profile)",
				f"JAWS and NVDA settings are read from and written to {facts.appData}.",
			),
		)

	# NVDA
	if tuple(facts.nvdaVersionTuple[:2]) < MINIMUM_NVDA and facts.nvdaVersionTuple != (0, 0, 0):
		add(Check(PROBLEM, f"NVDA {facts.nvdaVersion} is too old", "The JAWS Migration Assistant needs NVDA 2026.1 or later."))
	else:
		kind = "installed copy" if facts.nvdaInstalled else "portable copy"
		if facts.nvdaAppX:
			kind = "Microsoft Store copy"
		add(Check(OK, f"NVDA {facts.nvdaVersion} ({kind})", f"Settings folder: {facts.configDir}"))
	if not facts.nvdaInstalled and not facts.nvdaAppX:
		add(
			Check(
				NOTE,
				"This is a portable copy of NVDA",
				"Migrated settings go into this portable copy only. Run the assistant from your installed NVDA too if you use both.",
			),
		)
	if facts.nvdaAppX:
		add(
			Check(
				WARNING,
				"Add-ons cannot be installed into the Microsoft Store version of NVDA",
				"Recommended add-ons will be listed, but you will need the regular NVDA to install them.",
			),
		)
	if facts.nvdaSecure:
		add(Check(PROBLEM, "NVDA is running on a secure screen", "Settings cannot be changed here. Sign in to Windows first."))
	if not facts.configWritable:
		add(
			Check(
				PROBLEM,
				"NVDA's settings folder cannot be written",
				f"{facts.configDir} is read-only or NVDA was started with settings saving disabled. Nothing can be migrated.",
			),
		)
	if 0 <= facts.freeBytes < MINIMUM_FREE_BYTES:
		add(
			Check(
				WARNING,
				"Low disk space",
				f"Only {facts.freeBytes // (1024 * 1024)} MB free where NVDA keeps its settings. The backup may not fit.",
			),
		)
	if profileName.lower() in (name.lower() for name in facts.profiles):
		add(
			Check(
				NOTE,
				f'An NVDA configuration profile named "{profileName}" already exists',
				"If you choose to migrate into a separate profile, it is backed up and then updated.",
			),
		)
	add(
		Check(
			OK,
			"Your NVDA settings will be backed up before anything changes",
			"nvda.ini, profiles, input gestures, speech dictionaries, symbols, ClassicSpeech settings and NVDA's own sounds.",
		),
	)

	# JAWS
	if not facts.jaws:
		add(Check(PROBLEM, "JAWS is not installed on this computer", "No JAWS program, registry entries or settings folders were found."))
	else:
		for jaws in facts.jaws:
			if jaws.programInstalled:
				title = f"{jaws.displayName} is installed in {jaws.installDir}"
				level = OK
			else:
				title = f"JAWS {jaws.version} settings were found, but the JAWS program is not installed"
				level = NOTE
			languages = ", ".join(jaws.settingsLanguages) or "none"
			userState = _folderReadable(jaws.userSettingsDir)
			sharedState = _folderReadable(jaws.sharedSettingsDir)
			parts = [
				"Your settings: " + (jaws.userSettingsDir if userState else ("not found" if userState is None else "cannot be read")),
				"Shared settings: " + (jaws.sharedSettingsDir if sharedState else ("not found" if sharedState is None else "cannot be read")),
				f"Settings languages: {languages}",
			]
			add(Check(level, title, "\n    ".join(parts)))
			if userState is None:
				add(
					Check(
						NOTE,
						f"JAWS {jaws.version} has no personal settings for {facts.userName or 'this Windows user'}",
						"Only the shared settings, which apply to everyone on this computer, can be migrated.",
					),
				)
			elif userState is False or sharedState is False:
				add(
					Check(
						WARNING,
						f"Some JAWS {jaws.version} settings cannot be read",
						"Windows denied access to a settings folder. Files that cannot be read are skipped and listed in the report.",
					),
				)
			if len(jaws.settingsLanguages) > 1:
				add(
					Check(
						NOTE,
						f"JAWS {jaws.version} has settings in more than one language",
						f"You can choose which one to migrate: {languages}.",
					),
				)
		if len(facts.jaws) > 1:
			add(Check(NOTE, "More than one JAWS version was found", "The newest is selected; you can choose another."))
		if facts.jawsRunning:
			add(
				Check(
					WARNING,
					"JAWS is running",
					"The assistant only reads JAWS files, so JAWS keeps working. Running two screen readers at once "
					"can make both hard to use; you may want to close JAWS first.",
				),
			)
	if facts.leasey.found:
		add(
			Check(
				NOTE,
				"Leasey from Hartgen Consultancy was found; its settings will be ignored",
				"Leasey files, scripts and keystrokes are left out of the migration. Found: "
				+ "; ".join(facts.leasey.evidence[:5]),
			),
		)

	# Speech
	if facts.classicSpeech.installed:
		level = OK if facts.classicSpeech.usable else WARNING
		detail = "JAWS voice profiles and speech and sounds schemes will be copied into ClassicSpeech."
		if not facts.classicSpeech.usable:
			detail = "ClassicSpeech is disabled or being removed, so JAWS voice profiles and schemes cannot be copied into it."
		add(Check(level, f"ClassicSpeech {facts.classicSpeech.version} is installed", detail))
	else:
		add(
			Check(
				NOTE,
				"ClassicSpeech is not installed",
				"Everything NVDA supports natively is migrated. Per-cursor voices and JAWS speech and sounds schemes need ClassicSpeech.",
			),
		)
	if facts.synths:
		current = facts.currentSynth.get("description") or facts.currentSynth.get("name") or "unknown"
		add(Check(OK, f"NVDA can use {len(facts.synths)} synthesizers; it is speaking with {current}"))
	voiceCount = len(facts.sapiVoices) + len(facts.oneCoreVoices) + len(facts.speechPlatformVoices)
	if voiceCount:
		add(
			Check(
				OK,
				f"{voiceCount} Windows voices found",
				f"SAPI 5: {len(facts.sapiVoices)}, OneCore: {len(facts.oneCoreVoices)}, Speech Platform: {len(facts.speechPlatformVoices)}.",
			),
		)
	return checks


def hasProblems(checks: list[Check]) -> bool:
	return any(check.level == PROBLEM for check in checks)


def blockingProblems(facts: SystemFacts) -> list[str]:
	"""Problems that stop a migration from running at all."""
	problems = []
	if facts.nvdaSecure:
		problems.append("NVDA is running on a secure screen.")
	if not facts.configWritable:
		problems.append("NVDA's settings folder cannot be written.")
	if tuple(facts.nvdaVersionTuple[:2]) < MINIMUM_NVDA and facts.nvdaVersionTuple != (0, 0, 0):
		problems.append("NVDA is older than 2026.1.")
	return problems


def checksAsText(checks: list[Check]) -> str:
	return "\n".join(check.asText() for check in checks)
