# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""NVDA+Shift+J, then D turns audio ducking on or off, as JAWS's Insert+Space, D does.

A tester asked for it (issue 33, Question 6). JAWS's ToggleAudioDucking (Default.JSS; Default.JKM [Common Keys],
Insert+Space&D) is on or off. On, JAWS lowers other programs' sound while it speaks, and says "Duck other audio"
(msgAudioDucking_On); off, "Do not duck other audio" (msgAudioDucking_Off). Its layer help says "Audio ducking toggle
on/off = D."

NVDA has three modes (audioDucking.AudioDuckingMode): no ducking, "Duck when outputting speech and sounds", which is
what JAWS's on does, and "Always duck". NVDA's own NVDA+Shift+D goes through all three. D after NVDA+Shift+J goes
between the two JAWS has: from no ducking to ducking while NVDA speaks, and from either kind of ducking to none, with
JAWS's words. As NVDA's own command, it keeps the mode in NVDA's configuration (audio, audioDuckingMode), and says
NVDA's "Audio ducking not supported" where NVDA can't duck, as in a portable copy of NVDA.
"""

from __future__ import annotations

#: What JAWS says (Default.jsb): msgAudioDucking_On and msgAudioDucking_Off.
ON = "Duck other audio"
OFF = "Do not duck other audio"
#: NVDA's own words where it can't duck (globalCommands.script_cycleAudioDuckingMode).
NOT_SUPPORTED = "Audio ducking not supported"


def _say(message: str) -> None:
	try:
		import ui

		ui.message(message)
	except Exception:
		pass


def nextMode(current, modes):
	"""The mode after ``current``, as JAWS's toggle: none -> ducking while NVDA speaks, any ducking -> none."""
	return modes.OUTPUTTING if int(current) == int(modes.NONE) else modes.NONE


def toggle() -> bool:
	"""Turn audio ducking on or off and say so as JAWS does. True when it changed."""
	import audioDucking
	import config

	if not audioDucking.isAudioDuckingSupported() or audioDucking._isAudioDuckingSuspended():
		_say(NOT_SUPPORTED)
		return False
	modes = audioDucking.AudioDuckingMode
	mode = nextMode(config.conf["audio"]["audioDuckingMode"], modes)
	# As NVDA's own script_cycleAudioDuckingMode.
	audioDucking.setAudioDuckingMode(mode)
	config.conf["audio"]["audioDuckingMode"] = int(mode)
	try:
		from . import evenSpeech

		# NVDA wrote the mode into the profile turned on last: on a web page that is Custom Browse Mode's, and ducking would
		# be on or off on pages alone, as the speech volume was (issue 49). A migration sets NVDA's ducking from JAWS's one
		# option for it (settingsMap).
		evenSpeech.afterChange(("audio",), "audioDuckingMode", int(mode))
	except Exception:
		pass
	_say(OFF if int(mode) == int(modes.NONE) else ON)
	return True
