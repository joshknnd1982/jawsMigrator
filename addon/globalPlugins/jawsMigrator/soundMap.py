# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Which JAWS sound effect stands in for each of NVDA's own sounds.

NVDA's sounds live in its program folder (``waves``), which only an
administrator may change, so NVDA's files are never touched. Instead
ClassicSpeech plays the chosen JAWS sounds in place of NVDA's (``classicSounds``);
restoring NVDA's sounds, or turning ClassicSpeech's schemes off, brings them back.

Where the user changed a JAWS sound in Settings Center (for instance the forms
mode sounds), their choice is used.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import jawsFiles


@dataclass(frozen=True)
class SoundEvent:
	#: NVDA's sound file name without ``.wav``.
	nvdaName: str
	label: str
	#: ``(section, key)`` of the JAWS option naming the sound, when JAWS has one.
	jawsOption: tuple | None
	#: The JAWS sound used when the option is absent.
	jawsDefault: str
	jawsLabel: str


SOUND_EVENTS = (
	SoundEvent("browseMode", "Switching to browse mode", ("FormsMode", "ExitFormsModeSound"), "boink1.wav", "leaving forms mode"),
	SoundEvent("focusMode", "Switching to focus mode", ("FormsMode", "EnterFormsModeSound"), "boink2.wav", "entering forms mode"),
	SoundEvent("textError", "Spelling error", ("options", "ProofingErrorEnteredSound"), "BuzzerShort.wav", "proofing error"),
	SoundEvent("suggestionsOpened", "Auto-suggestions appear", None, "OutlookAutocompleteEnterSound.wav", "auto-complete list opens"),
	SoundEvent("suggestionsClosed", "Auto-suggestions close", None, "OutlookAutocompleteExitSound.wav", "auto-complete list closes"),
	SoundEvent("screenCurtainOn", "Screen curtain turned on", None, "BlindsDownOnly.wav", "Screen Shade on"),
	SoundEvent("screenCurtainOff", "Screen curtain turned off", None, "BlindsUpOnly.wav", "Screen Shade off"),
	SoundEvent("connected", "Remote Access connected", ("Tandem", "TandemConnectSound"), "TandemConnect.wav", "Tandem connected"),
	SoundEvent("controlled", "Remote Access: ready to be controlled", ("Tandem", "TandemConnectSound"), "TandemConnect.wav", "Tandem connected"),
	SoundEvent("controlling", "Remote Access: another computer joined", ("Tandem", "TandemConnectSound"), "TandemConnect.wav", "Tandem connected"),
	SoundEvent("disconnected", "Remote Access disconnected", ("Tandem", "TandemDisconnectSound"), "TandemDisconnect.wav", "Tandem disconnected"),
	SoundEvent("error", "Error written to the NVDA log", None, "BuzzerLong.wav", "error buzzer"),
)

#: NVDA sounds with no JAWS counterpart; NVDA keeps its own.
UNMATCHED_NVDA_SOUNDS = {
	"start": "NVDA starting",
	"exit": "NVDA exiting",
	"clipboardPush": "Remote Access sending the clipboard",
	"clipboardReceive": "Remote Access receiving the clipboard",
}


@dataclass
class SoundChoice:
	event: SoundEvent
	jawsPath: str
	jawsName: str
	fromOption: str = ""


def chooseSounds(jcf: jawsFiles.IniFile, findSound) -> tuple[list[SoundChoice], list[str]]:
	"""Pick the JAWS sound for each NVDA sound.

	``findSound(name)`` returns the path of a JAWS sound file or None. Returns the
	choices and a list of explanations for sounds that could not be matched.
	"""
	choices = []
	missing = []
	for event in SOUND_EVENTS:
		name = event.jawsDefault
		fromOption = ""
		if event.jawsOption:
			configured = jcf.get(*event.jawsOption)
			if configured:
				configured = configured.strip().strip('"')
				fromOption = f"[{event.jawsOption[0]}] {event.jawsOption[1]}={configured}"
				if configured:
					name = configured
		path = findSound(name)
		if path is None and name != event.jawsDefault:
			path = findSound(event.jawsDefault)
		if path is None:
			missing.append(f"{event.label}: the JAWS sound {name} was not found")
			continue
		choices.append(SoundChoice(event, path, name, fromOption))
	return choices, missing
