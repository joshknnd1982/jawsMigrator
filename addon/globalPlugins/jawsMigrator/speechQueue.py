# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""What NVDA's speech manager still has to say, and whether something NVDA was asked to say reached the synthesizer.

NVDA asks its speech manager (speech.manager.SpeechManager, speech._manager) to say something, and the manager says
it when the synthesizer is free. What NVDA says for the focus carries a command (speech.commands.
_CancellableSpeechCommand, "CancellableSpeech (still valid)" in NVDA's log) that tells the manager whether it is
still worth saying. When the focus moves on, the manager drops what isn't (``_buildNextUtterance`` and
``_doRemoveCancelledSpeechCommands``), and NVDA's cancelSpeech drops everything it hasn't said yet. The manager keeps
each sequence in its queues (``_priQueues``, ``pendingSequences``) from the time it is asked until the synthesizer has
said it, and gives the command the number of its utterance (``_utteranceIndex``) as it sends it to the synthesizer
(``_checkForCancellations``).

So, from the commands in what NVDA was asked to say, this tells: whether NVDA is still saying it or has yet to
(stillToSay), and whether NVDA dropped it without saying it (neverSaid). Nothing here changes NVDA's speech: it reads
the manager's queues, and asks a command only what the manager itself asks it (isCancelled). Anything it can't tell
counts as said, so nothing is ever left out by mistake.
"""

from __future__ import annotations


def _cancellableClass():
	try:
		from speech.commands import _CancellableSpeechCommand

		return _CancellableSpeechCommand
	except Exception:
		return None


def cancellables(sequence) -> tuple:
	"""The commands in ``sequence`` by which NVDA's speech manager drops it once it isn't worth saying."""
	cancellable = _cancellableClass()
	if cancellable is None:
		return ()
	return tuple(item for item in sequence or () if isinstance(item, cancellable))


def pending() -> set | None:
	"""The commands (their id()) in the sequences NVDA's speech manager has yet to say or is saying, or None when
	they can't be told."""
	try:
		import speech

		manager = speech._manager
		commands = set()
		for queue in list(manager._priQueues.values()):
			for sequence in list(getattr(queue, "pendingSequences", ()) or ()):
				if isinstance(sequence, list):
					commands.update(id(item) for item in sequence)
		return commands
	except Exception:
		return None


def _isDropped(command) -> bool:
	"""Whether what ``command`` came with is no longer worth saying, as NVDA's speech manager asks it
	(_CancellableSpeechCommand.isCancelled: once it isn't, it never is again)."""
	try:
		return bool(command.isCancelled)
	except Exception:
		return False


def _wasSent(command) -> bool:
	"""Whether NVDA's speech manager sent the utterance with ``command`` to the synthesizer."""
	return getattr(command, "_utteranceIndex", None) is not None


def stillToSay(commands) -> bool:
	"""Whether NVDA is still saying, or has yet to say, what these commands came with (and hasn't dropped it)."""
	if not commands:
		return False
	queued = pending()
	if queued is None:
		return False
	return any(id(command) in queued and not _isDropped(command) for command in commands)


def neverSaid(commands, queued: set | None = None) -> bool:
	"""Whether NVDA dropped what these commands came with before the synthesizer said any of it: the focus had moved
	on, or NVDA cut speech short. False when it was said, is still to be said, or it can't be told. ``queued``:
	pending(), when asking for many."""
	if not commands:
		return False
	if all(_wasSent(command) for command in commands):
		return False
	if queued is None:
		queued = pending()
		if queued is None:
			return False
	return not any(id(command) in queued for command in commands)
