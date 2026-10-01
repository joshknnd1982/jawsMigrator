# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""What the assistant asks of classic Outlook while NVDA speaks a message is asked once, and never for long.

A tester (issue 40, "It is also very slow with the option checked to read the message") sent NVDA's log of a picture-heavy
newsletter opened in classic Outlook 16.0.20326 (UI Automation). NVDA's watchdog wrote "Recovered from potential freeze after
7.0 seconds", "5.0 seconds" and, with Down Arrow pressed in a message of 73,022 characters with 18 links, "Recovered from freeze
after 12.5 seconds"; the Python stack it listed for NVDA's main thread was inside a UI Automation call for a line of the
message, and the same lines of the assistant's own debug log said where the time went: "read the HTML of an Outlook message"
at 15:51:08.562, and "asked Word's object model for the links of an Outlook message" at 15:51:13.621, five seconds later, with
only the assistant's code between them. Outlook answered each question of its object model in about 35 milliseconds (a message
of 18 links and nine pictures took about 145 questions), where the same two lines of the log for the small message the tester
opened first are 0.05 seconds apart (15:49:37.167 and .218). A message that size makes Outlook's own thread busy, and everything
NVDA asks of it waits, on NVDA's main thread, while NVDA is in the middle of a key press.

The assistant asked a lot, and asked it again for each line:

* A link with no text (unlabeledLinks, 1.49): for each such link NVDA said, it asked Outlook which message was shown
  (Application.Inspectors, each inspector's caption, its item, its EntryID: about eight questions) before it looked in its
  cache of messages, and Word for the message's hyperlinks (Count and the first and last address: four more); and the first
  time, for every hyperlink of the message, its address, its type, its range's pictures and the picture's texts and its screen
  tip: about eight questions each, for links whose names the message's HTML had already given.
* A line of pictures (outlookPictures, 1.44): for each such line, a range from a point on the screen and up to a dozen questions
  about it, whether Word had an answer for the last such line or not, and as many more for the debug log when it had none.
* Each link and list NVDA said in a message you read: whether the message is one you read, which is a question of UI Automation.

Reading a message from the top, which the tester had turned on, is where it is felt most: Say All asks all of this for each of
its lines, one after another, so the reading stopped between lines for as long as Outlook took for them. With Down Arrow it is
the same on each key.

So now, everything asked of Outlook for the links and pictures of a message is:

* Asked once for each time a message takes the focus. ``reading`` is what the assistant has learned of the message that has the
  focus: which message it is, the names its HTML gives its links, the names Word's object model gives them, whether it is one
  you read. It is kept while the same NVDA object has the focus in the same window with the same title (a message you come
  back to is a new focus, and is asked about again; the assistant's own caches of a message's HTML and of Word's answers, which
  are kept for some messages, answer that without asking Outlook for them again), and for ten minutes at most.
* Asked for a short time. Word's object model is asked about each link of a message for at most half a second, in the order of
  the message, and only for the links whose names nothing else gave; what it had by then is kept. A picture's text is asked of
  Word for each line of pictures until one answer takes longer than a third of a second (healthy Outlooks answer in a few
  hundredths): that answer is used, and Word isn't asked for the pictures of that message again. What couldn't be asked is what
  NVDA said before: a link with no text is named by where it goes, and a picture is said as NVDA says it. The debug log says
  when that happened, and how long Outlook took.

The code here needs only the standard library (NVDA's ``api`` and ``winUser`` are asked for when needed), so the tests load it
without NVDA.
"""

from __future__ import annotations

import threading
import time

#: How long, in seconds, Word's object model is asked about the links of a message, in all.
WORD_BUDGET = 0.5
#: How long, in seconds, one question about a picture may take before Word isn't asked about that message's pictures again.
SLOW_ASK = 0.35
#: How long, in seconds, what was learned of a message is kept for.
MAX_AGE = 600.0

#: The time, which the tests replace.
clock = time.monotonic

_lock = threading.RLock()


class Reading:
	"""What the assistant has learned of the message that has the focus, which it asks Outlook for once.

	``labels``: the names the message's HTML gives its links, or None while it hasn't been asked (unlabeledLinks.Labels).
	``words``: the names Word's object model gives them, or None. ``readOnly``: whether the message is one you read, or None.
	``picturesOff``: Word answered a question about a picture slowly, so it isn't asked about this message's pictures again."""

	__slots__ = ("focus", "window", "title", "made", "labels", "words", "readOnly", "picturesOff")

	def __init__(self, focus, window, title):
		self.focus, self.window, self.title = focus, window, title
		self.made = clock()
		self.labels = self.words = self.readOnly = None
		self.picturesOff = False

	def isFor(self, focus, window, title) -> bool:
		"""Whether this is what was learned of the message shown in ``window``, titled ``title``, while ``focus`` has the focus.
		An object whose window can't be told (0) is taken to be in this message's, and says what the window is where this
		doesn't know yet: the document and the links in it are asked about, and must not each drive the other's reading out."""
		if self.focus is not focus or clock() - self.made >= MAX_AGE:
			return False
		if not window:
			return True
		if not self.window:
			self.window, self.title = window, title
			return True
		return self.window == window and self.title == title


#: The reading kept: the one of the object that has the focus.
_current = None


def focusObject():
	"""The NVDA object that has the focus, or None where that can't be told (the tests replace this)."""
	try:
		import api

		return api.getFocusObject()
	except Exception:
		return None


def windowOf(holder) -> tuple:
	"""(the top window of ``holder``'s window, its title), or (0, "") where that can't be told. Both are answered by Windows
	without asking the window's program, so they don't wait for Outlook."""
	try:
		import winUser

		handle = holder.windowHandle
		window = winUser.getAncestor(handle, winUser.GA_ROOT) or handle
		return window, (winUser.getWindowText(window) or "").strip()
	except Exception:
		return 0, ""


def reading(holder) -> Reading:
	"""What the assistant has learned of the message shown in ``holder``'s window (an NVDA object in it, such as a link or the
	document) while the same object has had the focus: a new one, which knows nothing yet, for another object, window or title,
	after ten minutes, and where the focus can't be told."""
	global _current
	focus = focusObject()
	window, title = windowOf(holder)
	if focus is None:
		return Reading(None, window, title)
	with _lock:
		current = _current
		if current is not None and current.isFor(focus, window, title):
			return current
		_current = Reading(focus, window, title)
		return _current


def readOnly(holder, ask) -> bool:
	"""Whether the message shown in ``holder`` is one you read, which ``ask()`` tells (a question of UI Automation): asked once
	for each time the message takes the focus."""
	kept = reading(holder)
	if kept.readOnly is None:
		kept.readOnly = bool(ask())
	return kept.readOnly


class Deadline:
	"""A time in seconds that work may take: ``over`` says when it has."""

	def __init__(self, seconds: float):
		self.seconds = seconds
		self.started = clock()

	def over(self) -> bool:
		return clock() - self.started >= self.seconds

	def took(self) -> float:
		return clock() - self.started


def reset() -> None:
	"""Forget what was learned (for the tests, and when the assistant is turned off and on)."""
	global _current
	with _lock:
		_current = None
