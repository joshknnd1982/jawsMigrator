# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""No sound while NVDA exits after a JAWS migration, as JAWS plays none when it exits.

A migration turns NVDA's "Play sounds when starting or exiting NVDA" off, because JAWS plays no
sound when it starts or exits. NVDA still played one: when Screen Curtain is on, NVDA turns it off
as it exits (``screenCurtain.terminate`` disables it), and with "Play sound when toggling Screen
Curtain" on, that plays the Screen Curtain off sound. Through ClassicSpeech it is even JAWS's
Screen Shade off sound. It is meant for turning the curtain off by hand, which still plays it.

So while NVDA exits, and only then, the assistant leaves that one sound out. NVDA's global plugins
stop before NVDA turns the curtain off, so ``silenceWhileExiting`` wraps ``nvwave.playWaveFile``
from the plugin's ``terminate``, around ClassicSpeech's own wrapper: the Screen Curtain sound is
recognised by NVDA's file name, before ClassicSpeech swaps in a scheme's sound. Nothing is
written anywhere, and NVDA's own exit sound, when the user turns it back on, is never touched.
"""

from __future__ import annotations

import functools
import os

#: NVDA's sound for turning Screen Curtain off, in its ``waves`` folder.
SCREEN_CURTAIN_OFF = "screencurtainoff.wav"
_WRAPPED_MARK = "_jawsMigratorExitSilence"


def _log():
	from logHandler import log

	return log


def nvdaIsExiting() -> bool:
	"""True once NVDA has started to exit (or restart), rather than reloading its plugins."""
	try:
		import core

		return bool(getattr(core, "_hasShutdownBeenTriggered", False))
	except Exception:
		return False


def startAndExitSoundsOff() -> bool:
	"""Whether NVDA's "Play sounds when starting or exiting NVDA" is off."""
	try:
		import config

		value = config.conf["general"]["playStartAndExitSounds"]
	except Exception:
		return False
	if isinstance(value, str):
		return value.strip().lower() not in ("1", "true", "yes", "on")
	return not bool(value)


def wanted(stateData: dict, soundsOff: bool) -> bool:
	"""Whether NVDA should exit without a sound: after a migration or JAWS sounds, with its exit sound off."""
	from . import classicSounds

	if not soundsOff or not isinstance(stateData, dict):
		return False
	return bool(stateData.get("lastMigration")) or classicSounds.isApplied(stateData.get(classicSounds.STATE_KEY))


def isScreenCurtainOffSound(fileName, wavesFolder: str) -> bool:
	"""Whether ``fileName`` is NVDA's own Screen Curtain off sound (absolute, or relative to NVDA's folder)."""
	if not isinstance(fileName, str) or not fileName:
		return False
	path = fileName.replace("/", "\\")
	if os.path.basename(path).lower() != SCREEN_CURTAIN_OFF:
		return False
	folder = os.path.dirname(path)
	if not os.path.isabs(path):
		return os.path.normcase(folder) == os.path.normcase("waves")
	return bool(wavesFolder) and os.path.normcase(os.path.normpath(folder)) == os.path.normcase(os.path.normpath(wavesFolder))


def silenceWhileExiting(wavesFolder: str, nvwaveModule=None) -> bool:
	"""Leave NVDA's Screen Curtain off sound out from now on. Only called while NVDA exits.

	Returns True when the sound is left out (it may already have been).
	"""
	if nvwaveModule is None:
		try:
			import nvwave as nvwaveModule
		except Exception:
			return False
	original = getattr(nvwaveModule, "playWaveFile", None)
	if original is None:
		return False
	if getattr(original, _WRAPPED_MARK, False):
		return True

	@functools.wraps(original)
	def playWaveFile(*args, **kwargs):
		fileName = args[0] if args else kwargs.get("fileName")
		if isScreenCurtainOffSound(fileName, wavesFolder):
			try:
				_log().debug("jawsMigrator: NVDA is exiting, so the Screen Curtain off sound is left out, as JAWS plays no sound when it exits")
			except Exception:
				pass
			return None
		return original(*args, **kwargs)

	setattr(playWaveFile, _WRAPPED_MARK, True)
	nvwaveModule.playWaveFile = playWaveFile
	return True
