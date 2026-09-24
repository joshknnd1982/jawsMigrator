# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""A control's type and state said once, when a web page repeats them in the control's label.

Some web pages write what a screen reader says about a control into the control's label. On
visible.com, a payment option is labelled "As low as $49.97/mo for 36 months 0% APR + taxes, radio
button checked 1 of 2", and the page rewrites that label whenever the option is checked. NVDA reads
the label, then says the control's type and state itself, so a tester heard "radio button checked
1 of 2, radio button, checked".

As NVDA speaks, the page's copy is taken off the end of the label when:

- the end of the label is a control type followed only by states and a position, in NVDA's own
  words: "radio button", then "checked" or "not checked", and "1 of 2" (a type may also be spelled
  as English pages often do, such as "checkbox" or "dropdown");
- there is a state or a position after the type, so a button labelled "Close button" keeps its label;
- NVDA itself says that control type, or one of those states, right next to the label: after it
  when NVDA names the control, before it when NVDA reads the control's line;
- something is left of the label.

What remains is what NVDA says for a control whose label doesn't repeat those words: the label, then
NVDA's own type and state, which are right even when the page forgets to update its copy. The words
are NVDA's, in NVDA's language, so a page in another language is left alone. It runs before other
add-ons' speech filters, such as ClassicSpeech's, which can turn NVDA's words into sounds. Nothing
is written anywhere; it works while the assistant runs, unless it is turned off in NVDA's Settings,
JAWS Migration Assistant.
"""

from __future__ import annotations

import re

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "sayTypeAndStateOnce"

#: NVDA's control types (controlTypes.Role) that pages write into a control's label.
ROLES = (
	"BUTTON",
	"TOGGLEBUTTON",
	"MENUBUTTON",
	"DROPDOWNBUTTON",
	"DROPDOWNBUTTONGRID",
	"SPLITBUTTON",
	"RADIOBUTTON",
	"CHECKBOX",
	"SWITCH",
	"COMBOBOX",
	"EDITABLETEXT",
	"PASSWORDEDIT",
	"SPINBUTTON",
	"SLIDER",
	"LINK",
	"TAB",
	"MENUITEM",
	"CHECKMENUITEM",
	"RADIOMENUITEM",
	"LISTITEM",
	"TREEVIEWITEM",
)
#: The states (controlTypes.State) NVDA says for those controls.
STATES = (
	"CHECKED",
	"HALFCHECKED",
	"SELECTED",
	"PRESSED",
	"HALF_PRESSED",
	"ON",
	"EXPANDED",
	"COLLAPSED",
	"UNAVAILABLE",
	"REQUIRED",
	"INVALID_ENTRY",
	"READONLY",
	"PROTECTED",
	"MULTILINE",
	"AUTOCOMPLETE",
	"VISITED",
	"INTERNAL_LINK",
	"HASPOPUP",
	"HASPOPUP_DIALOG",
	"HASPOPUP_GRID",
	"HASPOPUP_LIST",
	"HASPOPUP_TREE",
	"SORTED_ASCENDING",
	"SORTED_DESCENDING",
	"MULTISELECTABLE",
	"CLICKABLE",
)
#: States NVDA also says in the negative: "not checked", "not selected", "not pressed", "off".
NEGATIVE_STATES = ("CHECKED", "SELECTED", "PRESSED", "ON")
#: Control types as English pages often spell them, besides NVDA's own words ("check box", "combo box").
#: Only a state NVDA says next to the label can confirm them, so they change nothing in another language.
ENGLISH_ROLE_WORDS = (
	"checkbox",
	"radiobutton",
	"combobox",
	"dropdown",
	"drop-down",
	"drop down",
	"listbox",
	"list box",
	"textbox",
	"text box",
	"text field",
	"edit field",
	"edit box",
	"toggle",
)
#: A position as NVDA says it in English, and as pages write it: "1 of 2".
ENGLISH_POSITION = r"\d+\s+of\s+\d+"

ROLE = "role"
STATE = "state"
POSITION = "position"

#: What may stand between a label and the control words a page put after it, and between those words.
_SEPARATOR = r"[\s,;:.\-\N{EN DASH}\N{EM DASH}/|()\[\]]"
_SEPARATOR_CHARS = frozenset(",;:.-/|()[]\N{EN DASH}\N{EM DASH}")
#: Taken off the end of what is left of the label. Closing brackets stay: they belong to the label.
_TRAILING = " \t\r\n\N{NO-BREAK SPACE}\N{THIN SPACE}\N{NARROW NO-BREAK SPACE},;:.-\N{EN DASH}\N{EM DASH}/|(["
#: At most this many control words are taken off one label: a type, states and a position.
_MOST_WORDS = 6
#: Longer text than this, spoken by NVDA next to a label, is never only control words.
_LONGEST_CONTROL_TEXT = 60
_WORD = re.compile(r"\w")

_vocabulary: Vocabulary | None = None
_registered = False
_failed = False


def _log():
	from logHandler import log

	return log


def _normalize(text: str) -> str:
	return " ".join(str(text).lower().split())


def _isSeparator(character: str) -> bool:
	return character.isspace() or character in _SEPARATOR_CHARS


def _lastWord(text: str) -> str:
	"""The last word of ``text``, in lower case, without the separators around it."""
	end = len(text)
	while end and _isSeparator(text[end - 1]):
		end -= 1
	start = end
	while start and not _isSeparator(text[start - 1]):
		start -= 1
	return text[start:end].lower()


def _pattern(words: str) -> str:
	"""A pattern for ``words``, with any spacing between them."""
	return r"\s+".join(re.escape(part) for part in words.split())


class Vocabulary:
	"""The words NVDA says for a control's type, states and position, and how to find them in a label."""

	def __init__(self, roles, states, positions=(ENGLISH_POSITION,)):
		#: {words in lower case: ROLE or STATE}
		self.kinds: dict[str, str] = {}
		for kind, words in ((STATE, states), (ROLE, roles)):
			for word in words:
				normal = _normalize(word) if word else ""
				if normal:
					self.kinds[normal] = kind
		positions = [pattern for pattern in dict.fromkeys(positions) if pattern]
		self._positions = [re.compile(pattern, re.IGNORECASE) for pattern in positions]
		# Longest first, so "not checked" is found before "checked", and "radio button" before "button".
		words = sorted(self.kinds, key=len, reverse=True)
		alternatives = [_pattern(word) for word in words] + positions
		self._closing = None
		if alternatives:
			# One control word at the very end of a text, after a separator or at its start.
			self._closing = re.compile(rf"(?:(?<={_SEPARATOR})|^)({'|'.join(alternatives)}){_SEPARATOR}*$", re.IGNORECASE)
		self._lastWords = {_lastWord(word) for word in words}

	def kindOf(self, words: str) -> str | None:
		"""ROLE, STATE or POSITION for words NVDA says, or None."""
		normal = _normalize(words)
		kind = self.kinds.get(normal)
		if kind is None and normal[-1:].isdigit() and any(pattern.fullmatch(normal) for pattern in self._positions):
			kind = POSITION
		return kind

	def _mayEndWithControlWords(self, text: str) -> bool:
		word = _lastWord(text)
		return bool(word) and (word in self._lastWords or word[-1].isdigit())

	def _takeOffEnd(self, text: str, untilRole: bool):
		"""Take control words off the end of ``text``: ``(what is left, [(kind, words)] in their order)``.

		With ``untilRole``, the words end with the first control type found, going back from the end,
		so a label that ends in a state word ("Turn on", "Enable add-on") keeps it. Each state is taken
		once, and one type and one position at most.
		"""
		rest = text
		found: list[tuple[str, str]] = []
		if self._closing is None:
			return rest, found
		while len(found) < _MOST_WORDS:
			match = self._closing.search(rest)
			if match is None:
				break
			words = _normalize(match.group(1))
			kind = self.kinds.get(words, POSITION)
			if (kind, words) in found or (kind != STATE and any(taken == kind for taken, _ in found)):
				break
			found.append((kind, words))
			rest = rest[: match.start()]
			if untilRole and kind == ROLE:
				break
		found.reverse()
		return rest, found

	def splitLabel(self, text: str):
		"""``(label, [(kind, words)])``: a label without the control type, states and position at its end.

		The words start with a control type; without one, nothing is taken off and the list is empty.
		"""
		if not self._mayEndWithControlWords(text):
			return text, []
		rest, found = self._takeOffEnd(text, untilRole=True)
		if not found or found[0][0] != ROLE:
			return text, []
		return rest.rstrip(_TRAILING), found

	def controlWords(self, text: str):
		"""The control words ``text`` is made of, as ``[(kind, words)]``, or None when it says anything else."""
		if len(text) > _LONGEST_CONTROL_TEXT:
			return None
		kind = self.kindOf(text)
		if kind is not None:
			return [(kind, _normalize(text))]
		if not self._mayEndWithControlWords(text):
			return None
		rest, found = self._takeOffEnd(text, untilRole=False)
		if found and not _WORD.search(rest):
			return found
		return None


def clean(speechSequence, vocabulary: Vocabulary):
	"""``speechSequence`` with the control words a label repeats taken off, where NVDA says them itself.

	Returns the sequence itself when nothing changes, otherwise a new list; commands stay where they are.
	"""
	items = speechSequence if isinstance(speechSequence, list) else list(speechSequence)
	# NVDA's own sequences have empty strings and commands between the words; they separate nothing.
	texts = [index for index, item in enumerate(items) if isinstance(item, str) and _WORD.search(item)]
	if len(texts) < 2:
		return items
	words = [vocabulary.controlWords(items[index]) for index in texts]
	result = None
	for position, index in enumerate(texts):
		if words[position] is not None:
			continue
		# The types and states NVDA says for the control, right after the label or right before it.
		spoken = set()
		for step in (1, -1):
			neighbour = position + step
			while 0 <= neighbour < len(texts) and words[neighbour] is not None:
				spoken.update(said for kind, said in words[neighbour] if kind != POSITION)
				neighbour += step
		if not spoken:
			continue
		label = items[index]
		rest, repeated = vocabulary.splitLabel(label)
		if len(repeated) < 2 or not _WORD.search(rest):
			continue
		if not spoken.intersection(said for kind, said in repeated if kind != POSITION):
			continue
		if result is None:
			result = list(items)
		result[index] = rest
		try:
			_log().debug(f"jawsMigrator: NVDA says the type and state itself, so the label's own copy is left out: {label!r} -> {rest!r}")
		except Exception:
			pass
	return result if result is not None else items


def nvdaVocabulary() -> Vocabulary:
	"""NVDA's words for control types, states and positions, in NVDA's language."""
	import controlTypes

	roles = [controlTypes.Role[name].displayString for name in ROLES if name in controlTypes.Role.__members__]
	roles += ENGLISH_ROLE_WORDS
	states = [controlTypes.State[name].displayString for name in STATES if name in controlTypes.State.__members__]
	states += [controlTypes.State[name].negativeDisplayString for name in NEGATIVE_STATES if name in controlTypes.State.__members__]
	return Vocabulary(roles, states, (ENGLISH_POSITION, _nvdaPosition()))


def _nvdaPosition() -> str:
	"""NVDA's "1 of 2" in its language, as a pattern, or "" when it can't be told."""
	try:
		from speech.speech import getPropertiesSpeech

		spoken = getPropertiesSpeech(positionInfo_indexInGroup=1, positionInfo_similarItemsInGroup=2)
		sample = " ".join(item for item in spoken if isinstance(item, str))
	except Exception:
		return ""
	if sample.count("1") != 1 or sample.count("2") != 1:
		return ""
	return _pattern(sample).replace("1", r"\d+").replace("2", r"\d+")


def wanted(stateData: dict) -> bool:
	"""Whether a control's type and state are said once: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def _speechFilter(speechSequence):
	"""NVDA's filter_speechSequence handler. It must never keep NVDA from speaking."""
	global _failed
	if not isinstance(speechSequence, list):
		speechSequence = list(speechSequence)
	vocabulary = _vocabulary
	if vocabulary is None:
		return speechSequence
	try:
		return clean(speechSequence, vocabulary)
	except Exception:
		if not _failed:
			_failed = True
			try:
				_log().debugWarning("jawsMigrator: could not check a label for a repeated control type and state", exc_info=True)
			except Exception:
				pass
		return speechSequence


def register() -> bool:
	"""Check what NVDA speaks from now on. Returns whether the check is in place."""
	global _vocabulary, _registered
	try:
		from speech.extensions import filter_speechSequence

		if _vocabulary is None:
			_vocabulary = nvdaVocabulary()
		if not _registered:
			filter_speechSequence.register(_speechFilter)
			_registered = True
		# First, before other add-ons' filters: ClassicSpeech's can turn NVDA's words for a control into a sound.
		moveToEnd = getattr(filter_speechSequence, "moveToEnd", None)
		if moveToEnd is not None:
			moveToEnd(_speechFilter, last=False)
	except Exception:
		try:
			_log().debugWarning("jawsMigrator: a control's type and state can't be said once", exc_info=True)
		except Exception:
			pass
		return False
	return True


def unregister() -> None:
	"""Stop checking what NVDA speaks."""
	global _registered
	if not _registered:
		return
	_registered = False
	try:
		from speech.extensions import filter_speechSequence

		filter_speechSequence.unregister(_speechFilter)
	except Exception:
		try:
			_log().debugWarning("jawsMigrator: could not stop checking labels for a repeated control type and state", exc_info=True)
		except Exception:
			pass


def isRegistered() -> bool:
	return _registered
