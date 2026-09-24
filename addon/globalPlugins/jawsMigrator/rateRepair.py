# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""A one-time repair of the Eloquence rate that versions 1.0 to 1.3 set from JAWS.

Those versions made JAWS's Eloquence rate NVDA's rate as a percentage of JAWS's range (0 to 148).
But JAWS keeps Eloquence's own speed there, and NVDA's Eloquence drivers start their range at speed
40, so speech was faster than in JAWS: JAWS's 111 (75%) became NVDA's 75, speed 122 with the
Eloquence add-on, where 65 is JAWS's speed 111 (see voices.eciRatePercent).

Where NVDA's rate for an Eloquence driver is still exactly what those versions made of one of the
user's JAWS Eloquence rates, it becomes the rate with that JAWS speed, in the normal configuration
and in the "JAWS settings" profile of versions 1.0 to 1.2. A rate changed since is the user's and
stays. NVDA's settings are backed up first.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from . import debugLog, nvdaEnv, voices

REPAIR_VERSION = 1
STATE_KEY = "eloquenceRateRepaired"
#: How versions 1.0 to 1.3 read JAWS's Eloquence rate: a percentage of 0 to 148.
OLD_RANGE = voices.ParameterRange(0, 148, 57)


@dataclass
class RateFix:
	#: None for the normal configuration, else the profile's name.
	profile: str | None
	driver: str
	old: int
	new: int
	jawsRate: int

	@property
	def where(self) -> str:
		return f'the profile "{self.profile}"' if self.profile else "the normal configuration"


def planFixes(jawsRates, configured) -> list[RateFix]:
	"""The rates to repair.

	``jawsRates`` are the Global rates of the user's JAWS Eloquence voice profiles, in JAWS's units;
	``configured`` is ``[(profile or None, driver, rate, eciRange, boost)]`` for NVDA's Eloquence drivers.
	"""
	fixes = []
	for profile, driver, rate, eciRange, boost in configured:
		if rate is None or not eciRange:
			continue
		for jawsRate in sorted(set(jawsRates)):
			if OLD_RANGE.toPercent(jawsRate) != rate:
				continue
			new = voices.eciRatePercent(jawsRate, eciRange, boost)
			if new is not None and new != rate:
				fixes.append(RateFix(profile, driver, rate, new, int(jawsRate)))
			break
	return fixes


def jawsEloquenceRates() -> list[int]:
	"""The Global rates of every JAWS voice profile for Eloquence on this computer, in JAWS's units."""
	from . import jawsDetect, jawsIndex

	rates = set()
	for jaws in jawsDetect.findJawsInstallations():
		for language in jaws.settingsLanguages or [jaws.primaryLanguage or "enu"]:
			try:
				index = jawsIndex.buildIndex(jaws, language)
				names = index.voiceProfileNames(jawsIndex.BOTH)
			except Exception:
				continue
			for name in names:
				try:
					profile = index.voiceProfile(name, jawsIndex.BOTH)
				except Exception:
					continue
				if profile is None or profile.synth.family != "eloquence":
					continue
				for profileLanguage in profile.languages():
					rate = profile.context(profileLanguage, "Global").rate
					if rate is not None:
						rates.add(int(round(float(rate))))
	return sorted(rates)


def _rawRate(section, driver: str):
	"""The rate stored for ``driver`` in one profile's own settings, or None."""
	try:
		value = section["speech"][driver]["rate"]
	except Exception:
		return None
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def configuredRates() -> list:
	"""``[(profile or None, driver, rate)]`` for NVDA's Eloquence drivers, as the configurations hold them."""
	import config

	from . import nvdaApply, state

	found = []
	places = [(None, config.conf.profiles[0])]
	name = nvdaApply.existingProfileName(state.get("jawsProfileName") or "")
	if name:
		try:
			places.append((name, config.conf.getProfile(name)))
		except Exception:
			pass
	for profile, section in places:
		try:
			drivers = list(section["speech"].keys())
		except Exception:
			continue
		for driver in drivers:
			if not voices.isEciDriver(driver):
				continue
			rate = _rawRate(section, driver)
			if rate is not None:
				found.append((profile, driver, rate))
	return found


def repairOnce(announce, backupFirst, done=None) -> None:
	"""Once, after updating from versions 1.0 to 1.3: give NVDA's Eloquence rate JAWS's speed. Main thread.

	``backupFirst(reason)`` backs NVDA's settings up and returns the backup; it runs in the background,
	as does reading the JAWS voice profiles. ``done()`` is called on the main thread at the end.
	"""
	from . import migrator, nvdaApply, state

	finished = migrator.callOnce(done)
	started = False
	try:
		if state.get(STATE_KEY) >= REPAIR_VERSION or not nvdaEnv.shouldWriteToDisk():
			return
		if not state.get("lastMigration"):
			state.set(STATE_KEY, REPAIR_VERSION)
			return
		configured = []
		for profile, driver, rate in configuredRates():
			eciRange, boost = nvdaApply.eciRateRange(driver)
			configured.append((profile, driver, rate, eciRange, boost))
		if not configured:
			state.set(STATE_KEY, REPAIR_VERSION)
			return

		def work():
			outcome = None
			try:
				fixes = planFixes(jawsEloquenceRates(), configured)
				if fixes:
					outcome = (fixes, backupFirst("Before giving NVDA's Eloquence rate the speed of the JAWS rate"))
				else:
					outcome = ([], None)
			except Exception as error:
				debugLog.error("the Eloquence rate repair could not start")
				outcome = error
			import wx

			wx.CallAfter(finish, outcome)

		def finish(outcome):
			try:
				_apply(outcome, announce)
			finally:
				finished()

		threading.Thread(target=work, name="jawsMigratorRateRepair", daemon=True).start()
		started = True
	except Exception:
		debugLog.error("the Eloquence rate repair failed")
	finally:
		if not started:
			finished()


def _apply(outcome, announce) -> None:
	import config
	import synthDriverHandler

	from . import nvdaApply, state

	if isinstance(outcome, Exception):
		debugLog.note(f"the Eloquence rate was not repaired; it is tried again next time NVDA starts: {outcome}")
		return
	fixes, backupInfo = outcome
	if not fixes:
		state.set(STATE_KEY, REPAIR_VERSION)
		return
	debugLog.section("Giving NVDA's Eloquence rate the speed of the JAWS rate")
	done = []
	for fix in fixes:
		try:
			with nvdaApply.writingTo(fix.profile):
				nvdaApply.setValue(config.conf, ("speech", fix.driver, "rate"), fix.new)
			done.append(fix)
			debugLog.note(f"speech.{fix.driver}.rate {fix.old} -> {fix.new} in {fix.where} (JAWS Eloquence rate {fix.jawsRate}); backup {backupInfo.path if backupInfo else ''}")
		except Exception:
			debugLog.error(f"the {fix.driver} rate in {fix.where} could not be changed")
	nvdaApply.saveConfig()
	try:
		synth = synthDriverHandler.getSynth()
		if synth is not None and any(fix.driver == synth.name for fix in done):
			synth.loadSettings(onlyChanged=True)
	except Exception:
		debugLog.error("the synthesizer did not take the new rate yet; it does after NVDA restarts")
	state.set(STATE_KEY, REPAIR_VERSION)
	if done:
		first = done[0]
		announce(
			f"JAWS Migration Assistant: NVDA's speech rate is now {first.new}, the same speed as your JAWS rate. "
			f"The earlier migration had set {first.old}, which made NVDA speak faster than JAWS. NVDA's settings were backed up first.",
		)
