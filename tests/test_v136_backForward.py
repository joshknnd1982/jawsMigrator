# Unit tests for version 1.36, from a tester's report (issue 32, "Issue with differences when going back on a
# website"). On reddit.com's r/Visible in Edge, the tester pressed H to a post, Enter, read the post with H and the
# arrow keys, and pressed Alt+Left. JAWS 2026 said (its speech history, as the tester pasted it):
#     What Phones Work Best On Visible?  visited  heading level 2  Link
#     ...
#     Back
#     Going back
#     visited  Link  I currently have the Pixel 8 Pro, and I'm getting ready to upgrade. ...
# NVDA 2026.2 with JAWS Migration Assistant 1.35 and Browse Mode Caret Fix 3.0.24 said (NVDA log 2026-09-27
# 23.06.58.zip, nvda.log):
#     23:06:10.979 Input: kb(laptop):h
#     23:06:10.984 Speaking ['What Phones Work Best On Visible?', 'visited', 'heading', 'level 2', 'link', 'Author: u/Pikachufourtytwo 2 hr. ago']
#     23:06:13.107 Input: kb(laptop):enter
#     23:06:13.186 Browse Mode Caret Fix: saved link activation docKey='https://www.reddit.com/r/Visible/' stackDepth=1
#     23:06:13.674 Browse Mode Caret Fix: moved newly opened Reddit post to document top
#     (then Edge's "Loading page" and "Loading complete", and ClassicSpeech's page summary)
#     23:06:18.499 Input: kb(laptop):h
#     23:06:18.502 Speaking ['Post Title: What Phones Work Best On Visible?', 'heading', 'level 1']
#     23:06:19.787 Input: kb(laptop):downArrow
#     23:06:19.791 Speaking ['link', 'Question']
#     (two more lines of the post)
#     23:06:22.043 Input: kb(laptop):downArrow
#     23:06:22.046 Speaking ["Samsung phones have trouble. Are there any other phones that have issues? Any phone you've never had an issue with?"]
#     23:06:25.762 Browse Mode Caret Fix: saw Back navigation gesture; target document is 'https://www.reddit.com/r/Visible/'
#     23:06:25.762 Input: kb(laptop):alt+leftArrow
#     23:06:26.021 Browse Mode Caret Fix: refreshed NVDA focus cache; document key is 'https://www.reddit.com/r/Visible/comments/1wrr8xg/what_phones_work_best_on_visible/'
#     23:06:26.560 Browse Mode Caret Fix: restore lookup docKey='https://www.reddit.com/r/Visible/' stackDepth=1
#     23:06:26.630 Browse Mode Caret Fix: restored saved position
# and then nothing, until the tester's next key 6 seconds later.
# - backForward: Alt+Left and Alt+Right say "Back" and "Forward", as JAWS's GoBack and GoForward scripts do
#   (IA2Browser.jss, msgBack1_L and msgForward1_L in ie.jsm), and turn focus mode off as they turn forms mode off.
#   Reddit puts the subreddit back in the same page and changes its address; once it and browse mode's caret are
#   still, NVDA reads the line at the caret, as JAWS read the line at its cursor. "Going back" is Edge's own
#   notification, which the tester's MSEdgeDiscardAnnouncements keeps silent as it comes.
#   Run live on the maintainer's computer (Edge 154, a copy of the subreddit and a plain two-page site), JAWS 2026 said
#   "Back", "Going back", then on the plain site "Plain page one" and "heading level 2, Link, Go to page two", the
#   link it had followed. NVDA 2026.2 with Browse Mode Caret Fix said "Back" and then nothing on the plain site either:
#   Edge keeps the pages you leave, NVDA keeps reading them, and going back to one, Browse Mode Caret Fix gave NVDA its
#   focus itself (api.setFocusObject), so NVDA dropped the browser's focus event and never came into the page. Going
#   forward to a kept page, NVDA got no focus event at all and stayed in the page it had left. Now NVDA comes into a
#   page it didn't, as eventHandler.doPreGainFocus has it do, or takes the browser's focus with a focus event.
# - linkSpeech: quick navigation says no description of a link or heading, as JAWS's virtual cursor says none
#   (Default.jcf [VirtualCursorVerbosity] DescribedBy=1|0|0 and ElementDescription=0|0|0: off at Medium). Tab says a
#   link's description and title, as JAWS 2026 did live (issue 35 for a title).
# The imitation NVDA is tests/test_v125_linkSpeech.py's: NVDA 2026.2's own speakTextInfo, getTextInfoSpeech,
# getControlFieldSpeech and TextInfoQuickNavItem.report, word for word, with the tester's settings, with NVDA's focus
# event as eventHandler.doPreGainFocus has it and its speech.extensions.pre_speech. NVDA's own
# event_treeInterceptor_gainFocus for a page it comes back to is tests/test_v134_pageFirstLine.py's. Browse Mode Caret
# Fix 3.0.24, which the tester runs, is its own code, word for word (BROWSE_MODE_CARET_FIX, checked against its source
# when it is here). NVDA's core queue and clock are one imitation clock, so the page's timing is the log's. The
# assistant's code (backForward, linkSpeech, quickNavHeadings) is the real one.
# Run: python -m unittest tests.test_v136_backForward -v

import heapq
import itertools
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

# NVDA 2026.2's speech code, roles, states and settings, taken there word for word.
import test_v125_linkSpeech as v125  # noqa: E402

# NVDA 2026.2's event_treeInterceptor_gainFocus, word for word, on its object and text speech.
import test_v134_pageFirstLine as v134  # noqa: E402

from jawsMigrator import backForward, linkSpeech, quickNavHeadings, state  # noqa: E402

Role, State, OutputReason = v125.Role, v125.State, v125.OutputReason
textInfos, spoken = v125.textInfos, v125.spoken
heading, link, landmark = v125.heading, v125.link, v125.landmark

#: Browse Mode Caret Fix 3.0.24's globalPlugins/browseModeCaretFix/__init__.py, word for word.
BROWSE_MODE_CARET_FIX = r'''# -*- coding: utf-8 -*-
"""Browse Mode Caret Fix (3.0.24).

Restores the browse-mode caret after Alt+Left in Microsoft Edge, including
single-page applications whose virtual buffer is not rebuilt by navigation.
Once a day, updater.py checks GitHub for a newer release of the add-on.
"""

import time
from urllib.parse import urlsplit, urlunsplit

import api
import browseMode
import controlTypes
import core
import globalPluginHandler
import inputCore
import scriptHandler
import textInfos
from logHandler import log
from NVDAObjects import NVDAObject

from . import updater

ADDON_LOG_PREFIX = "Browse Mode Caret Fix"

_FINGERPRINT_PROBE_LINES = 12
_MAX_SAVED_POSITIONS_PER_DOCUMENT = 20
_NAVIGATION_TIMEOUT_SECONDS = 5.0
_FAST_POLL_WINDOW_SECONDS = 3.0
_FAST_POLL_MS = 50
_SLOW_POLL_MS = 200
_FOCUS_CACHE_REFRESH_AFTER_SECONDS = 0.20
_FOCUS_CACHE_REFRESH_INTERVAL_SECONDS = 0.20

# Normalized document ID -> activation positions, newest last.
_savedPositionStacks = {}
# Chronological source-document keys for link activations. The newest one is
# the exact document a Back operation should return to.
_backTargetKeys = []
_pendingNavigation = None
_navigationSerial = 0
_pendingRedditOpen = None
_redditOpenSerial = 0

_originalActivatePosition = None


def _isEdgeFocus():
	try:
		obj = api.getFocusObject()
		return bool(obj and obj.appModule and obj.appModule.appName == "msedge")
	except Exception:
		return False


def _getNavigationDirection(gesture):
	"""Return -1 for Alt+Left, 1 for Alt+Right, or 0 otherwise."""
	try:
		identifiers = gesture.normalizedIdentifiers
	except Exception:
		identifiers = ()
	for identifier in identifiers or ():
		try:
			keys = identifier.casefold().split(":", 1)[1]
		except (AttributeError, IndexError):
			continue
		parts = set(keys.split("+"))
		if parts == {"alt", "leftarrow"}:
			return -1
		if parts == {"alt", "rightarrow"}:
			return 1
	return 0


def _getRawDocId(treeInterceptor):
	try:
		return treeInterceptor.documentConstantIdentifier
	except Exception:
		return None


def _normalizeDocId(docId):
	"""Make fragment-only history entries share one caret-position key."""
	if not isinstance(docId, str) or not docId.strip():
		return None
	docId = docId.strip()
	try:
		parts = urlsplit(docId)
		if parts.scheme and parts.netloc:
			return urlunsplit((
				parts.scheme.casefold(),
				parts.netloc.casefold(),
				parts.path,
				parts.query,
				"",
			))
	except (TypeError, ValueError):
		pass
	return docId.split("#", 1)[0]


def _getDocKey(treeInterceptor):
	return _normalizeDocId(_getRawDocId(treeInterceptor))


def _isRedditPostUrl(docId):
	if not isinstance(docId, str):
		return False
	try:
		parts = urlsplit(docId)
		host = parts.netloc.casefold().split(":", 1)[0]
		pathParts = [part.casefold() for part in parts.path.split("/") if part]
		return (
			(host == "reddit.com" or host.endswith(".reddit.com"))
			and "comments" in pathParts
		)
	except (TypeError, ValueError):
		return False


def _getLineFingerprint(info):
	try:
		lineInfo = info.copy()
		lineInfo.expand(textInfos.UNIT_LINE)
		return lineInfo.text.strip()
	except Exception:
		return ""


def _scheduleNextAttempt(callback, pending):
	"""Keep only one lightweight timer outstanding for this operation."""
	now = time.monotonic()
	remaining = pending["deadline"] - now
	if remaining <= 0:
		return False
	delay = (
		_FAST_POLL_MS
		if now - pending["started"] < _FAST_POLL_WINDOW_SECONDS
		else _SLOW_POLL_MS
	)
	delay = min(delay, max(1, int(remaining * 1000)))
	core.callLater(delay, callback, pending["token"])
	return True


def _isLinkPosition(info):
	"""Avoid filling the history stack when buttons and form controls activate."""
	try:
		obj = info.NVDAObjectAtStart
		for _ in range(6):
			if obj is None:
				break
			if obj.role == controlTypes.Role.LINK:
				return True
			obj = obj.parent
	except Exception:
		pass

	try:
		probe = info.copy()
		probe.expand(textInfos.UNIT_CHARACTER)
		for item in probe.getTextWithFields():
			if (
				isinstance(item, textInfos.FieldCommand)
				and item.command == "controlStart"
				and item.field
				and item.field.get("role") == controlTypes.Role.LINK
			):
				return True
	except Exception:
		pass
	return False


def _saveActivationPosition(treeInterceptor, info, docKey=None):
	if docKey is None:
		docKey = _getDocKey(treeInterceptor)
	if docKey is None:
		log.debug("%s: skipped save because document ID is unavailable" % ADDON_LOG_PREFIX)
		return
	try:
		entry = {
			"bookmark": info.bookmark,
			"fingerprint": _getLineFingerprint(info),
		}
	except Exception:
		log.debug("%s: could not capture activation position" % ADDON_LOG_PREFIX, exc_info=True)
		return

	stack = _savedPositionStacks.setdefault(docKey, [])
	stack.append(entry)
	_backTargetKeys.append(docKey)
	if len(stack) > _MAX_SAVED_POSITIONS_PER_DOCUMENT:
		del stack[:-_MAX_SAVED_POSITIONS_PER_DOCUMENT]
	if len(_backTargetKeys) > 100:
		del _backTargetKeys[:-100]
	log.debug(
		"%s: saved link activation docKey=%r stackDepth=%d"
		% (ADDON_LOG_PREFIX, docKey, len(stack))
	)


def _attemptPendingRedditOpen(token):
	global _pendingRedditOpen
	pending = _pendingRedditOpen
	if not pending or pending.get("token") != token:
		return
	timedOut = time.monotonic() >= pending["deadline"]
	if not _isEdgeFocus():
		if timedOut:
			_pendingRedditOpen = None
		else:
			_scheduleNextAttempt(_attemptPendingRedditOpen, pending)
		return
	try:
		treeInterceptor = api.getFocusObject().treeInterceptor
		if not isinstance(treeInterceptor, browseMode.BrowseModeDocumentTreeInterceptor):
			raise AttributeError("focus has no browse-mode treeInterceptor")
	except Exception:
		if timedOut:
			_pendingRedditOpen = None
		else:
			_scheduleNextAttempt(_attemptPendingRedditOpen, pending)
		return

	rawDocId = _getRawDocId(treeInterceptor)
	if rawDocId == pending.get("startRawDocId") or not _isRedditPostUrl(rawDocId):
		if timedOut:
			_pendingRedditOpen = None
		else:
			_scheduleNextAttempt(_attemptPendingRedditOpen, pending)
		return
	try:
		first = treeInterceptor.makeTextInfo(textInfos.POSITION_FIRST)
		treeInterceptor.selection = first
		treeInterceptor.rootNVDAObject.setFocus()
	except Exception:
		log.debug("%s: Reddit top-position attempt failed; will retry" % ADDON_LOG_PREFIX, exc_info=True)
		if timedOut:
			_pendingRedditOpen = None
		else:
			_scheduleNextAttempt(_attemptPendingRedditOpen, pending)
		return
	log.debug("%s: moved newly opened Reddit post to document top" % ADDON_LOG_PREFIX)
	_pendingRedditOpen = None


def _trackRedditPostOpen(startRawDocId):
	global _pendingRedditOpen, _redditOpenSerial
	try:
		parts = urlsplit(startRawDocId)
		host = parts.netloc.casefold().split(":", 1)[0]
		if host != "reddit.com" and not host.endswith(".reddit.com"):
			return
	except (AttributeError, TypeError, ValueError):
		return
	_redditOpenSerial += 1
	token = _redditOpenSerial
	now = time.monotonic()
	_pendingRedditOpen = {
		"token": token,
		"startRawDocId": startRawDocId,
		"started": now,
		"deadline": now + _NAVIGATION_TIMEOUT_SECONDS,
	}
	core.callLater(_FAST_POLL_MS, _attemptPendingRedditOpen, token)


def _patched_activatePosition(treeInterceptor, *args, **kwargs):
	"""Save only genuine link activations, then let NVDA activate normally."""
	info = None
	startRawDocId = _getRawDocId(treeInterceptor)
	startDocKey = _normalizeDocId(startRawDocId)
	try:
		candidate = treeInterceptor.selection.copy()
		if _isLinkPosition(candidate):
			info = candidate
	except Exception:
		log.debug("%s: link-position check failed" % ADDON_LOG_PREFIX, exc_info=True)

	result = _originalActivatePosition(treeInterceptor, *args, **kwargs)
	if info is not None:
		_saveActivationPosition(treeInterceptor, info, startDocKey)
		_trackRedditPostOpen(startRawDocId)
	return result


def _findFingerprintNearBookmark(info, fingerprint):
	if not fingerprint or _getLineFingerprint(info) == fingerprint:
		return info
	for distance in range(1, _FINGERPRINT_PROBE_LINES + 1):
		for direction in (-1, 1):
			probe = info.copy()
			try:
				if not probe.move(textInfos.UNIT_LINE, direction * distance):
					continue
			except Exception:
				continue
			if _getLineFingerprint(probe) == fingerprint:
				log.debug(
					"%s: fingerprint matched %d line(s) from bookmark"
					% (ADDON_LOG_PREFIX, direction * distance)
				)
				return probe
	log.debug("%s: fingerprint not found near bookmark; using bookmark" % ADDON_LOG_PREFIX)
	return info


def _restoreForTreeInterceptor(treeInterceptor):
	docKey = _getDocKey(treeInterceptor)
	stack = _savedPositionStacks.get(docKey) or []
	log.debug(
		"%s: restore lookup docKey=%r stackDepth=%d"
		% (ADDON_LOG_PREFIX, docKey, len(stack))
	)
	if not stack:
		return False

	# Peek first so a transient virtual-buffer failure doesn't destroy the
	# only saved position. Pop only after the selection was applied.
	entry = stack[-1]
	try:
		info = treeInterceptor.makeTextInfo(entry["bookmark"])
		info = _findFingerprintNearBookmark(info, entry.get("fingerprint"))
		treeInterceptor.selection = info
		treeInterceptor.rootNVDAObject.setFocus()
	except Exception:
		log.debug("%s: restore attempt failed; will retry" % ADDON_LOG_PREFIX, exc_info=True)
		return False

	stack.pop()
	if not stack:
		_savedPositionStacks.pop(docKey, None)
	log.debug("%s: restored saved position" % ADDON_LOG_PREFIX)
	return True


def _refreshNvdaFocusCache(pending):
	"""Refresh NVDA's cached focus without physically moving Windows focus."""
	now = time.monotonic()
	if now - pending["started"] < _FOCUS_CACHE_REFRESH_AFTER_SECONDS:
		return None
	if now - pending.get("lastCacheRefresh", 0.0) < _FOCUS_CACHE_REFRESH_INTERVAL_SECONDS:
		return None
	pending["lastCacheRefresh"] = now
	try:
		freshFocus = NVDAObject.objectWithFocus()
		if freshFocus is None or not api.setFocusObject(freshFocus):
			return None
		treeInterceptor = getattr(freshFocus, "treeInterceptor", None)
		log.debug(
			"%s: refreshed NVDA focus cache; document key is %r"
			% (ADDON_LOG_PREFIX, _getDocKey(treeInterceptor))
		)
		return treeInterceptor
	except Exception:
		log.debug("%s: NVDA focus-cache refresh failed" % ADDON_LOG_PREFIX, exc_info=True)
		return None


def _attemptPendingNavigation(token):
	global _pendingNavigation
	pending = _pendingNavigation
	if not pending or pending.get("token") != token or pending.get("restoring"):
		return
	timedOut = time.monotonic() >= pending["deadline"]
	if not _isEdgeFocus():
		if timedOut:
			_pendingNavigation = None
		else:
			_scheduleNextAttempt(_attemptPendingNavigation, pending)
		return

	try:
		treeInterceptor = api.getFocusObject().treeInterceptor
		if not isinstance(treeInterceptor, browseMode.BrowseModeDocumentTreeInterceptor):
			raise AttributeError("focus has no browse-mode treeInterceptor")
	except Exception:
		if timedOut:
			log.debug("%s: navigation ended without a browse-mode document" % ADDON_LOG_PREFIX)
			_pendingNavigation = None
		else:
			_scheduleNextAttempt(_attemptPendingNavigation, pending)
		return

	targetDocKey = pending.get("targetDocKey")
	currentDocKey = _getDocKey(treeInterceptor)
	if currentDocKey != targetDocKey:
		refreshedTreeInterceptor = _refreshNvdaFocusCache(pending)
		if isinstance(refreshedTreeInterceptor, browseMode.BrowseModeDocumentTreeInterceptor):
			treeInterceptor = refreshedTreeInterceptor
			currentDocKey = _getDocKey(treeInterceptor)

	elapsed = time.monotonic() - pending["started"]
	# Restore only in the exact source document recorded at link activation.
	navigationReady = currentDocKey == targetDocKey and elapsed >= 0.15
	if not navigationReady:
		if timedOut:
			log.debug("%s: destination buffer did not appear before timeout" % ADDON_LOG_PREFIX)
			_pendingNavigation = None
		else:
			_scheduleNextAttempt(_attemptPendingNavigation, pending)
		return

	pending["restoring"] = True
	try:
		restored = _restoreForTreeInterceptor(treeInterceptor)
	finally:
		pending["restoring"] = False
	if restored:
		if _backTargetKeys and _backTargetKeys[-1] == targetDocKey:
			_backTargetKeys.pop()
		_pendingNavigation = None
	elif timedOut:
		log.debug("%s: no saved position became available after navigation" % ADDON_LOG_PREFIX)
		_pendingNavigation = None
	else:
		_scheduleNextAttempt(_attemptPendingNavigation, pending)


def _onDecideExecuteGesture(gesture):
	"""Observe Back/Forward via NVDA's extension point without blocking it."""
	global _navigationSerial, _pendingNavigation, _pendingRedditOpen
	try:
		direction = _getNavigationDirection(gesture)
		if not direction or not _isEdgeFocus():
			return True
		_pendingRedditOpen = None
		if direction > 0:
			return True
		if not _backTargetKeys:
			log.debug("%s: saw Back, but no saved link activation exists" % ADDON_LOG_PREFIX)
			return True
		_navigationSerial += 1
		token = _navigationSerial
		now = time.monotonic()
		_pendingNavigation = {
			"token": token,
			"direction": direction,
			"started": now,
			"deadline": now + _NAVIGATION_TIMEOUT_SECONDS,
			"targetDocKey": _backTargetKeys[-1],
			"lastCacheRefresh": 0.0,
			"restoring": False,
		}
		log.debug(
			"%s: saw Back navigation gesture; target document is %r"
			% (ADDON_LOG_PREFIX, _backTargetKeys[-1])
		)
		core.callLater(_FAST_POLL_MS, _attemptPendingNavigation, token)
	except Exception:
		# A gesture observer must never interfere with NVDA input.
		log.debug("%s: navigation gesture observer failed" % ADDON_LOG_PREFIX, exc_info=True)
	return True


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		global _originalActivatePosition

		_originalActivatePosition = browseMode.BrowseModeDocumentTreeInterceptor._activatePosition

		browseMode.BrowseModeDocumentTreeInterceptor._activatePosition = _patched_activatePosition
		inputCore.decide_executeGesture.register(_onDecideExecuteGesture)
		# The add-on has no settings of its own, so the update settings get a panel to themselves.
		updater.start(settingsPanel=True)

	@scriptHandler.script(
		# Translators: Description of a command, shown in the Input Gestures dialog.
		description=_("Checks for Browse Mode Caret Fix updates"),
		# Translators: Category of this add-on's commands in the Input Gestures dialog.
		category=_("Browse Mode Caret Fix"),
	)
	def script_checkForUpdates(self, gesture):
		updater.checkForUpdates()

	def terminate(self):
		global _pendingNavigation, _pendingRedditOpen
		updater.stop()
		_pendingNavigation = None
		_pendingRedditOpen = None
		try:
			inputCore.decide_executeGesture.unregister(_onDecideExecuteGesture)
		except Exception:
			pass
		if _originalActivatePosition is not None:
			browseMode.BrowseModeDocumentTreeInterceptor._activatePosition = _originalActivatePosition
		super(GlobalPlugin, self).terminate()
'''
#: The name NVDA loads it by.
CARET_FIX_MODULE = "globalPlugins.browseModeCaretFix"

# -- the tester's pages ---------------------------------------------------------------------------------------------

SUBREDDIT = "https://www.reddit.com/r/Visible/"
POST = "https://www.reddit.com/r/Visible/comments/1wrr8xg/what_phones_work_best_on_visible/"
SPEEDTEST = "https://www.reddit.com/r/Visible/comments/1wap8bj/new_speedtest_megathread_please_only_post/"
AUTHOR = "Author: u/Pikachufourtytwo 2 hr. ago"
PREVIEW = (
	"I currently have the Pixel 8 Pro, and I'm getting ready to upgrade. I'm looking for a phone that works really well on "
	"the service. I was looking into OnePlus (but they don't seem to be around anymore), but they don't work on Visible "
	"for some reason. I've seen the odd post here and there saying Samsung phones have trouble. Are there any other "
	"phones that have issues? Any phone you've never had an issue with? Any help would be great."
)
MAIN = landmark("main", 2)
#: The subreddit's lines, as Edge gives them to NVDA's virtual buffer: the post's title is a link in a heading, with the
#: post's author and age as its description (reddit's aria-describedby), and its first lines a link under it.
FEED = [
	[link(SUBREDDIT + "#main-content", 10), "Skip to main content"],
	[heading(1, 11), "r/Visible"],
	[MAIN, heading(2, 12), link(SPEEDTEST, 13, visited=True), "New speedtest megathread - please only post speedtests here."],
	[MAIN, heading(1, 14), "Feed"],
	[MAIN, heading(2, 15), link(POST, 16, visited=True, description=AUTHOR, descriptionFrom="aria-describedby"), "What Phones Work Best On Visible?"],
	[MAIN, link(POST, 17, visited=True), PREVIEW],
]
TITLE_LINE, PREVIEW_LINE = 4, 5
#: The post, as the tester read it.
POST_PAGE = [
	[link(POST + "#main-content", 20), "Skip to main content"],
	[MAIN, heading(1, 21), "Post Title: What Phones Work Best On Visible?"],
	[MAIN, link(SUBREDDIT + "?f=flair_name%3A%22Question%22", 22), "Question"],
	[MAIN, "I currently have the Pixel 8 Pro, and I'm getting ready to upgrade. I'm looking for a phone that works really well on the service. I was looking into "],
	[MAIN, "OnePlus (but they don't seem to be around anymore), but they don't work on Visible for some reason. I've seen the odd post here and there saying "],
	[MAIN, "Samsung phones have trouble. Are there any other phones that have issues? Any phone you've never had an issue with?"],
]

SUBREDDIT_TITLE = "This is a subreddit for Visible"
POST_TITLE = "What Phones Work Best On Visible? : r/Visible"

#: The plain two-page site of the live run: page one's second heading is a link to page two.
ONE, TWO = "http://127.0.0.1:8732/plain/one.html", "http://127.0.0.1:8732/plain/two.html"
ONE_TITLE, TWO_TITLE = "Plain page one", "Plain page two"
ONE_LINES = [
	[heading(1, 50), "Plain page one"],
	["A page that loads the usual way."],
	[heading(2, 51), link(TWO, 52), "Go to page two"],
	["A line after the link."],
]
LINK_LINE = 2
TWO_LINES = [
	[heading(1, 60), "Plain page two"],
	["First line of page two."],
	["Second line of page two."],
]

#: What NVDA said, as the log has it, up to Alt+Left.
LOGGED = [
	["What Phones Work Best On Visible?", "visited", "heading", "level 2", "link", AUTHOR],
	["Post Title: What Phones Work Best On Visible?", "heading", "level 1"],
	["link", "Question"],
	["I currently have the Pixel 8 Pro, and I'm getting ready to upgrade. I'm looking for a phone that works really well on the service. I was looking into "],
	["OnePlus (but they don't seem to be around anymore), but they don't work on Visible for some reason. I've seen the odd post here and there saying "],
	["Samsung phones have trouble. Are there any other phones that have issues? Any phone you've never had an issue with?"],
]


# -- the imitation NVDA and Edge ------------------------------------------------------------------------------------


class Clock:
	"""NVDA's core queue and time: core.callLater, queueHandler.queueFunction and time.monotonic, on one clock."""

	def __init__(self):
		self.now = 1000.0
		self._tasks = []
		self._order = itertools.count()

	def monotonic(self):
		return self.now

	def callLater(self, delay, function, *args, **kwargs):
		heapq.heappush(self._tasks, (self.now + delay / 1000, next(self._order), function, args, kwargs))

	def queueFunction(self, queue, function, *args, **kwargs):
		self.callLater(0, function, *args, **kwargs)

	def run(self, seconds):
		end = self.now + seconds
		while self._tasks and self._tasks[0][0] <= end:
			when, _order, function, args, kwargs = heapq.heappop(self._tasks)
			self.now = max(self.now, when)
			function(*args, **kwargs)
		self.now = end


class BrowseModeDocumentTreeInterceptor:
	"""browseMode.BrowseModeDocumentTreeInterceptor, as far as the assistant and Browse Mode Caret Fix ask it."""

	passThrough = False
	isAlive = True
	isReady = True


class Obj:
	"""An NVDA object: its role, name, program and the page it is in. setFocus moves Windows' focus to it, and the
	browser sends a focus event for it."""

	def __init__(self, nvda, role, page=None, appName="msedge", name=None):
		self.nvda, self.role, self.treeInterceptor, self.name = nvda, role, page, name
		self.appModule = types.SimpleNamespace(appName=appName)

	def setFocus(self):
		self.nvda.windowsFocus = self
		self.nvda.browserFocusEvent(self)


class Page(v125.ChromeVBuf, BrowseModeDocumentTreeInterceptor):
	"""An Edge page in NVDA's virtual buffer: its address, title, its lines with the fields Edge gives, and browse mode's
	caret, on a line. Reddit changes the address and the lines in place; NVDA's buffer keeps the caret's offset."""

	def __init__(self, nvda, url, lines, title=SUBREDDIT_TITLE):
		super().__init__(url)
		self.nvda = nvda
		self.lines, self.caret = list(lines), 0
		self.rootNVDAObject = Obj(nvda, Role.DOCUMENT, self, name=title)

	@property
	def documentConstantIdentifier(self):
		return self.documentURL

	def makeTextInfo(self, position):
		if position == textInfos.POSITION_CARET:
			return Line(self, self.caret)
		if position == textInfos.POSITION_FIRST:
			return Line(self, 0)
		# A bookmark: the line.
		return Line(self, position)

	@property
	def selection(self):
		return Line(self, self.caret)

	@selection.setter
	def selection(self, info):
		self.caret = info.index

	def show(self, url, lines, title=None):
		"""The page's own code changes its address, what it shows, and its title."""
		self.documentURL, self.lines = url, list(lines)
		self.caret = min(self.caret, len(self.lines) - 1)
		if title is not None:
			self.rootNVDAObject.name = title


class KeptPage(Page):
	"""A page Edge keeps as you leave it (its back/forward cache), which NVDA keeps reading. As NVDA comes into it again
	(event_treeInterceptor_gainFocus, which eventHandler.doPreGainFocus calls), NVDA says its title and the line at the
	caret: browseMode's own code, for a page it had come into before, in CameBackTests."""

	def event_treeInterceptor_gainFocus(self):
		self.nvda.cameInto.append(self)
		self.nvda.say([self.rootNVDAObject.name])
		self.nvda.speech.speakTextInfo(Line(self, self.caret), unit=textInfos.UNIT_LINE, reason=OutputReason.CARET)


class Line(v125.ChromeVBufTextInfo):
	"""A line of the page, as NVDA's virtual buffer gives it: its fields and text; a bookmark is the line."""

	def __init__(self, page, index):
		self.index = max(0, min(index, len(page.lines) - 1))
		super().__init__(page, page.lines[self.index])

	@property
	def bookmark(self):
		return self.index

	@property
	def text(self):
		return "".join(part for part in self.parts if isinstance(part, str))

	def copy(self):
		return Line(self.obj, self.index)

	def collapse(self, end=False):
		pass

	def expand(self, unit):
		pass

	def move(self, unit, direction, endPoint=None):
		index = max(0, min(self.index + direction, len(self.obj.lines) - 1))
		moved, self.index = index - self.index, index
		self.parts = self.obj.lines[index]
		return moved

	def compareEndPoints(self, other, which):
		return (self.index > other.index) - (self.index < other.index)

	@property
	def NVDAObjectAtStart(self):
		roles = [part["IAccessible::role"] for part in self.parts if isinstance(part, dict)]
		return types.SimpleNamespace(role=roles[-1] if roles else Role.STATICTEXT, parent=None)


class Key:
	"""A key NVDA's keyboard hook got, on the tester's laptop layout, with no command of NVDA's for it in Edge's page."""

	isModifier = False
	script = None

	def __init__(self, name):
		self.name = name
		self.normalizedIdentifiers = [f"kb(laptop):{name}".lower(), f"kb:{name}".lower()]


class Reddit:
	"""reddit.com's own code in Edge: a post opens, and Back puts the subreddit back, in the same page (history.pushState
	and popstate), as long after the key as the tester's log shows."""

	def __init__(self, nvda, page):
		self.nvda, self.page = nvda, page

	def activate(self, treeInterceptor, *args, **kwargs):
		"""NVDA's _activatePosition, which Browse Mode Caret Fix wraps: Enter clicks the link, and the post opens."""
		self.nvda.clock.callLater(480, self.page.show, POST, POST_PAGE)

	def back(self):
		self.nvda.clock.callLater(790, self.page.show, SUBREDDIT, FEED, SUBREDDIT_TITLE)

	def forward(self):
		pass


class PlainSite:
	"""Edge on the live run's plain two-page site: Enter loads page two, which NVDA comes into with the browser's focus
	event. Back and Forward bring back the page Edge kept, and move Windows' focus into it, but NVDA got no focus event
	for it in the live run: its focus stayed in the page it had left."""

	def __init__(self, nvda):
		self.nvda = nvda
		self.one = KeptPage(nvda, ONE, ONE_LINES, ONE_TITLE)
		self.two = None

	def activate(self, treeInterceptor, *args, **kwargs):
		self.nvda.clock.callLater(100, self.load)

	def load(self):
		self.two = KeptPage(self.nvda, TWO, TWO_LINES, TWO_TITLE)
		self.nvda.windowsFocus = self.two.rootNVDAObject
		self.nvda.browserFocusEvent(self.two.rootNVDAObject)

	def back(self):
		self.nvda.clock.callLater(150, self.show, self.one)

	def forward(self):
		self.nvda.clock.callLater(150, self.show, self.two)

	def show(self, page):
		self.nvda.windowsFocus = page.rootNVDAObject


class PreSpeech:
	"""NVDA's speech.extensions.pre_speech, an extensionPoints.Action: speech.speak notifies it with what NVDA says."""

	def __init__(self):
		self.handlers = []

	def register(self, handler):
		if handler not in self.handlers:
			self.handlers.append(handler)

	def unregister(self, handler):
		if handler in self.handlers:
			self.handlers.remove(handler)

	def notify(self, **kwargs):
		for handler in list(self.handlers):
			handler(**kwargs)


class TesterTests(unittest.TestCase):
	"""The tester's steps on reddit, with NVDA 2026.2's own speech code and Browse Mode Caret Fix's own code."""

	def setUp(self):
		self.clock = Clock()
		self.focus = self.windowsFocus = None
		self.passThroughReports = []
		self.browseMode = types.ModuleType("browseMode")
		self.browseMode.BrowseModeTreeInterceptor = v125.BrowseModeTreeInterceptor
		self.browseMode.BrowseModeDocumentTreeInterceptor = BrowseModeDocumentTreeInterceptor
		self.browseMode.TextInfoQuickNavItem = v125.TextInfoQuickNavItem
		self.browseMode.reportPassThrough = lambda treeInterceptor, onlyIfChanged=True: self.passThroughReports.append(treeInterceptor.passThrough)
		self.speech = types.ModuleType("speech")
		self.speech.getControlFieldSpeech = v125.NVDA_FIELD_SPEECH
		self.speech.getPropertiesSpeech = v125.speechScope["getPropertiesSpeech"]
		self.speech.speakTextInfo = v125.speechScope["speakTextInfo"]
		# NVDA's speakObject for a page, as browserPages has NVDA say it: its title (NVDA's own: CameBackTests).
		self.speech.speakObject = lambda obj, reason=None, **kwargs: self.say([obj.name])
		# NVDA's speech.speak notifies pre_speech with what it says, and ui.message speaks through it.
		self.preSpeech = PreSpeech()
		speechExtensions = types.ModuleType("speech.extensions")
		speechExtensions.pre_speech = self.preSpeech
		self.speech.extensions = speechExtensions
		speak = mock.patch.dict(v125.speechScope, {"speak": self.say})
		speak.start()
		self.addCleanup(speak.stop)
		self.cameInto = []
		eventHandler = types.ModuleType("eventHandler")
		eventHandler.queueEvent = lambda eventName, obj, **kwargs: self.clock.queueFunction(None, self.gainFocus, obj)
		api = types.ModuleType("api")
		api.getFocusObject = lambda: self.focus
		api.setFocusObject = self.setFocusObject
		nvdaObjects = types.ModuleType("NVDAObjects")
		nvdaObjects.NVDAObject = types.SimpleNamespace(objectWithFocus=lambda: self.windowsFocus)
		core = types.ModuleType("core")
		core.callLater = self.clock.callLater
		queueHandler = types.ModuleType("queueHandler")
		queueHandler.eventQueue, queueHandler.queueFunction = object(), self.clock.queueFunction
		ui = types.ModuleType("ui")
		ui.message = lambda text: self.say([text])
		globalPlugins = types.ModuleType("globalPlugins")
		globalPlugins.__path__ = []
		modules = mock.patch.dict(
			sys.modules,
			{
				"api": api,
				"browseMode": self.browseMode,
				"core": core,
				"queueHandler": queueHandler,
				"ui": ui,
				"NVDAObjects": nvdaObjects,
				"virtualBuffers": v125.virtualBuffers,
				"speech": self.speech,
				"speech.extensions": speechExtensions,
				"eventHandler": eventHandler,
				"controlTypes": v125.controlTypes,
				"config": v125.config,
				"textInfos": textInfos,
				"globalPlugins": globalPlugins,
				f"{CARET_FIX_MODULE}.updater": types.ModuleType(f"{CARET_FIX_MODULE}.updater"),
			},
		)
		modules.start()
		self.addCleanup(modules.stop)
		for name, value in (("POSITION_CARET", "caret"), ("POSITION_FIRST", "first")):
			patcher = mock.patch.object(textInfos, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)
		inputHelp = mock.patch.object(sys.modules["inputCore"].manager, "isInputHelpActive", False, create=True)
		inputHelp.start()
		self.addCleanup(inputHelp.stop)
		clock = mock.patch.object(backForward, "time", types.SimpleNamespace(monotonic=self.clock.monotonic))
		clock.start()
		self.addCleanup(clock.stop)
		v125.NVDA_REPORT.__globals__["speech"] = self.speech
		self.addCleanup(self._restoreNvda)
		v125.config.conf = v125.testersConfig()
		self.decider = sys.modules["inputCore"].decide_executeGesture
		self.page = Page(self, SUBREDDIT, FEED)
		self.reddit = self.site = Reddit(self, self.page)
		# Browse mode in the page: NVDA's focus is the page itself.
		self.focus = self.windowsFocus = self.page.rootNVDAObject
		self.caretFix = None
		spoken.clear()

	def _restoreNvda(self):
		backForward.unregister()
		linkSpeech.unregister()
		quickNavHeadings.unregister()
		if self.caretFix is not None:
			self.decider.unregister(self.caretFix._onDecideExecuteGesture)
		self.speech.getControlFieldSpeech = v125.NVDA_FIELD_SPEECH
		v125.TextInfoQuickNavItem.report = v125.NVDA_REPORT
		v125.BrowseModeTreeInterceptor.getLinkTypeInDocument = v125.NVDA_LINK_TYPE
		v125.TextInfo.getControlFieldSpeech = v125.NVDA_TEXT_FIELD_SPEECH
		if "report" in vars(v125.VirtualBufferQuickNavItem):
			del v125.VirtualBufferQuickNavItem.report
		for module in (linkSpeech, quickNavHeadings, backForward):
			if hasattr(module, "_replaced"):
				module._replaced.clear()
			module._failed = False
		v125.NVDA_REPORT.__globals__["speech"] = None
		v125.config.conf = v125.testersConfig()

	# -- NVDA ------------------------------------------------------------------------------------------------------

	def setFocusObject(self, obj):
		self.focus = obj
		return True

	def say(self, sequence, priority=None):
		"""NVDA's speech.speak: pre_speech hears it, and the log's "Speaking" line has its words."""
		self.preSpeech.notify(speechSequence=sequence)
		v125.speak(sequence, priority)

	def browserFocusEvent(self, obj):
		"""The browser's focus event: NVDA drops one for the object that already has its focus, and queues the rest."""
		if obj is not self.focus:
			self.clock.queueFunction(None, self.gainFocus, obj)

	def gainFocus(self, obj):
		"""NVDA's focus event, as eventHandler.doPreGainFocus has it: coming into another page, NVDA comes into it
		(event_treeInterceptor_gainFocus). In browse mode, the page itself gaining the focus says nothing else."""
		before = getattr(self.focus, "treeInterceptor", None)
		self.focus = obj
		page = getattr(obj, "treeInterceptor", None)
		if page is not before and page is not None and page.isReady and hasattr(page, "event_treeInterceptor_gainFocus"):
			page.event_treeInterceptor_gainFocus()

	def withCaretFix(self):
		"""Browse Mode Caret Fix 3.0.24, as NVDA loads it, with its hook on NVDA's decide_executeGesture."""
		module = types.ModuleType(CARET_FIX_MODULE)
		module.__package__, module.__path__ = CARET_FIX_MODULE, []
		module._ = lambda text: text
		sys.modules[CARET_FIX_MODULE] = module
		exec(compile(BROWSE_MODE_CARET_FIX, "<Browse Mode Caret Fix 3.0.24>", "exec"), vars(module))
		module.time = types.SimpleNamespace(monotonic=self.clock.monotonic)
		# Its GlobalPlugin puts its wrapper in the place of browse mode's _activatePosition, and watches the keys.
		module._originalActivatePosition = self.site.activate
		self.decider.register(module._onDecideExecuteGesture)
		self.caretFix = module
		return module

	def asTheTesterHasIt(self, version="1.36"):
		"""The assistant as the tester runs it: quick navigation says a heading without what it is in, links as JAWS
		says them, and, from 1.36, Back and Forward. 1.35's linkSpeech still said a link's description."""
		quickNavHeadings.register()
		linkSpeech.register()
		if version == "1.35":
			patcher = mock.patch.object(linkSpeech, "asJaws", lambda attrs, reason: linkSpeech.withoutTitle(attrs))
			patcher.start()
			self.addCleanup(patcher.stop)
		else:
			backForward.register()

	def press(self, name):
		"""A key: NVDA's decide_executeGesture handlers see it, then it does what it does."""
		key = Key(name)
		self.assertTrue(self.decider.decide(gesture=key), f"{name} goes on")
		# No command of NVDA's: the key goes to Edge, which goes back or forward.
		if name == "alt+leftArrow":
			self.site.back()
		elif name == "alt+rightArrow":
			self.site.forward()
		return key

	def quickNav(self, index):
		"""H: NVDA's quick navigation moves the caret to the heading and reports it."""
		self.press("h")
		self.page.caret = index
		v125.VirtualBufferQuickNavItem("heading", self.page, Line(self.page, index)).report()

	def arrow(self):
		"""Down Arrow: NVDA moves browse mode's caret a line down and says the line."""
		self.press("downArrow")
		self.page.caret += 1
		self.speech.speakTextInfo(Line(self.page, self.page.caret), unit=textInfos.UNIT_LINE, reason=OutputReason.CARET)

	def theTestersSteps(self):
		"""H to the post's title, Enter, H, the arrow keys to the post's last line, then Alt+Left, 7 seconds of it."""
		self.quickNav(TITLE_LINE)
		self.press("enter")
		if self.caretFix is not None:
			self.caretFix._patched_activatePosition(self.page)
		else:
			self.reddit.activate(self.page)
		self.clock.run(5)
		self.quickNav(1)
		for _line in range(4):
			self.arrow()
		self.press("alt+leftArrow")
		self.clock.run(7)
		return list(spoken)

	# -- the tester's report ---------------------------------------------------------------------------------------

	def test_nvdaSaidWhatTheLogSays(self):
		self.withCaretFix()
		self.asTheTesterHasIt("1.35")
		self.assertEqual(self.theTestersSteps(), LOGGED, "and nothing after Alt+Left")
		self.assertEqual(self.page.caret, TITLE_LINE, "Browse Mode Caret Fix put the caret back on the post's title")

	def test_saidAsJawsSaysIt(self):
		self.withCaretFix()
		self.asTheTesterHasIt()
		said = self.theTestersSteps()
		self.assertEqual(said[0], ["What Phones Work Best On Visible?", "visited", "heading", "level 2", "link"], 'JAWS: "What Phones Work Best On Visible?  visited  heading level 2  Link"')
		self.assertEqual(said[1:6], LOGGED[1:])
		self.assertEqual(
			said[6:],
			[
				# JAWS's GoBack: "Back". Edge's "Going back" is the tester's MSEdgeDiscardAnnouncements' to say.
				["Back"],
				# The line Browse Mode Caret Fix put the caret back on, the post's title. JAWS read the line at its cursor,
				# SayLine, which JAWS 2026 said live as "visited heading level 2 Link ..." (issue 38, from 1.40).
				["visited", "heading", "level 2", "link", "What Phones Work Best On Visible?"],
			],
		)
		self.assertEqual(self.page.caret, TITLE_LINE)
		self.assertEqual(self.passThroughReports, [], "browse mode all along")

	def test_readAfterBrowseModeCaretFixIsDone(self):
		# Browse Mode Caret Fix puts the caret back once the address is the subreddit's again; the line is read after it,
		# not the line NVDA's buffer had the caret on as reddit changed the page.
		self.withCaretFix()
		self.asTheTesterHasIt()
		self.theTestersSteps()
		with mock.patch.object(backForward, "_log") as log:
			self.page.show(POST, POST_PAGE)
			self.page.caret = 5
			spoken.clear()
			self.caretFix._backTargetKeys.append(backForward.address(self.page).replace(POST, SUBREDDIT))
			self.caretFix._savedPositionStacks[SUBREDDIT] = [{"bookmark": TITLE_LINE, "fingerprint": "What Phones Work Best On Visible?"}]
			self.press("alt+leftArrow")
			self.clock.run(0.85)
			self.assertEqual(spoken, [["Back"]], "the subreddit is back; Browse Mode Caret Fix has only just put the caret back")
			self.clock.run(6)
		self.assertEqual(spoken, [["Back"], ["visited", "heading", "level 2", "link", "What Phones Work Best On Visible?"]])
		said = [call.args[0] for call in log.return_value.debug.call_args_list]
		self.assertTrue(any("reads the line at the caret" in line and "What Phones Work Best On Visible?" in line for line in said), said)

	def test_withoutBrowseModeCaretFix(self):
		# Without Browse Mode Caret Fix, NVDA's buffer keeps the caret's offset as reddit changes the page: the line there
		# is read, once the page is still.
		self.asTheTesterHasIt()
		said = self.theTestersSteps()
		self.assertEqual(said[-2:], [["Back"], ["visited", "link", PREVIEW]])

	def test_1_35WithoutBrowseModeCaretFix(self):
		self.asTheTesterHasIt("1.35")
		self.assertEqual(self.theTestersSteps(), LOGGED)

	# -- what NVDA says itself -------------------------------------------------------------------------------------

	def test_aPageThatLoads(self):
		# Most sites load a page on Back: the browser's focus event brings NVDA into it, and NVDA says its title and the
		# line at its caret itself. Nothing is said twice.
		self.asTheTesterHasIt()
		self.page.show(POST, POST_PAGE, POST_TITLE)
		loaded = KeptPage(self, SUBREDDIT, FEED)
		loaded.caret = TITLE_LINE

		def load():
			self.windowsFocus = loaded.rootNVDAObject
			self.browserFocusEvent(loaded.rootNVDAObject)

		self.reddit.back = lambda: self.clock.callLater(600, load)
		self.press("alt+leftArrow")
		self.clock.run(7)
		self.assertEqual(self.cameInto, [loaded], "once, by NVDA's own focus event")
		self.assertEqual(spoken[:2], [["Back"], [SUBREDDIT_TITLE]])
		self.assertEqual(len(spoken), 3)
		self.assertEqual(spoken[2][-1], "What Phones Work Best On Visible?")

	def test_thePageMovesTheFocus(self):
		# A page that puts the focus on a link as it comes back: NVDA says the link, and its caret goes there. That is
		# not read again.
		self.asTheTesterHasIt()
		self.page.show(POST, POST_PAGE, POST_TITLE)
		self.page.caret = 5

		def back():
			self.page.show(SUBREDDIT, FEED, SUBREDDIT_TITLE)
			self.page.caret = PREVIEW_LINE
			self.focus = self.windowsFocus = Obj(self, Role.LINK, self.page)
			# Browse mode says the link that has the focus.
			self.say([PREVIEW, "visited", "link"])

		self.reddit.back = lambda: self.clock.callLater(500, back)
		self.press("alt+leftArrow")
		self.clock.run(7)
		self.assertEqual(spoken, [["Back"], [PREVIEW, "visited", "link"]])

	# -- a page Edge kept (the live run's plain site) --------------------------------------------------------------

	def onThePlainSite(self, caretFix=True, version="1.36"):
		"""The live run: page one, H to "Go to page two", Enter; page two loads and NVDA comes into it."""
		self.site = PlainSite(self)
		self.page = self.site.one
		self.page._hadFirstGainFocus = True
		self.focus = self.windowsFocus = self.page.rootNVDAObject
		if caretFix:
			self.withCaretFix()
		self.asTheTesterHasIt(version)
		self.quickNav(LINK_LINE)
		self.press("enter")
		if caretFix:
			self.caretFix._patched_activatePosition(self.page)
		else:
			self.site.activate(self.page)
		self.clock.run(2)
		self.assertIs(self.focus, self.site.two.rootNVDAObject, "NVDA came into page two")
		spoken.clear()
		self.cameInto.clear()

	def test_goingBackToAKeptPage(self):
		# Browse Mode Caret Fix gives NVDA page one's focus itself and puts the caret back on the link; NVDA drops the
		# browser's focus event and never comes into the page. Now NVDA says the page and the line at the caret, as it
		# does coming into a page. (NVDA's own event would say the line alone here: CameBackTests.)
		self.onThePlainSite()
		with mock.patch.object(backForward, "_log") as log:
			self.press("alt+leftArrow")
			self.clock.run(7)
		self.assertEqual(self.cameInto, [], "not NVDA's own event, for a page NVDA had come into")
		self.assertEqual(self.site.one.caret, LINK_LINE, "where Browse Mode Caret Fix put the caret back")
		# JAWS: "Back", "Going back", "Loading page", "Loading complete", "Plain page one", "heading level 2, Link, Go to
		# page two".
		self.assertEqual(spoken[:2], [["Back"], [ONE_TITLE]])
		self.assertEqual(spoken[2][-1], "Go to page two")
		self.assertEqual(len(spoken), 3)
		said = [call.args[0] for call in log.return_value.debug.call_args_list]
		self.assertTrue(any("comes into it now" in line and ONE_TITLE in line for line in said), said)

	def test_aPageNvdaNeverCameInto(self):
		# NVDA's focus went to a page NVDA never came into: NVDA's own event, which says the page and its line and puts
		# the caret where NVDA left it.
		self.asTheTesterHasIt()
		fresh = KeptPage(self, ONE, ONE_LINES, ONE_TITLE)
		fresh._hadFirstGainFocus = False
		self.site.back = lambda: self.clock.callLater(300, self.setFocusObject, fresh.rootNVDAObject)
		self.press("alt+leftArrow")
		self.clock.run(7)
		self.assertEqual(self.cameInto, [fresh])
		self.assertEqual(spoken[:2], [["Back"], [ONE_TITLE]])
		self.assertEqual(len(spoken), 3)

	def test_goingBackToAKeptPageWith1_35(self):
		# The live run: "Back" wasn't said, and then nothing.
		self.onThePlainSite(version="1.35")
		self.press("alt+leftArrow")
		self.clock.run(7)
		self.assertEqual(spoken, [])
		self.assertIs(self.focus, self.site.one.rootNVDAObject, "Browse Mode Caret Fix gave NVDA the page's focus")
		self.assertEqual(self.cameInto, [], "but NVDA never came into it")

	def test_forwardToAKeptPage(self):
		# Going forward, the browser's focus moved into page two with no focus event NVDA got: NVDA's focus stayed in
		# page one. NVDA takes the browser's focus with a focus event of its own, and comes into page two with it.
		self.onThePlainSite()
		self.press("alt+leftArrow")
		self.clock.run(7)
		spoken.clear()
		self.cameInto.clear()
		self.press("alt+rightArrow")
		self.clock.run(0.7)
		self.assertEqual(spoken, [["Forward"]], "NVDA waits a moment for a focus event of the browser's own")
		self.clock.run(7)
		self.assertEqual(self.cameInto, [self.site.two])
		self.assertIs(self.focus, self.site.two.rootNVDAObject)
		self.assertEqual(spoken[:2], [["Forward"], [TWO_TITLE]])
		self.assertEqual(len(spoken), 3)

	def test_backWithoutBrowseModeCaretFix(self):
		# Without Browse Mode Caret Fix, NVDA's focus stays in page two after Back, as after Forward.
		self.onThePlainSite(caretFix=False)
		self.press("alt+leftArrow")
		self.clock.run(7)
		self.assertEqual(self.cameInto, [self.site.one])
		self.assertEqual(spoken[:2], [["Back"], [ONE_TITLE]])
		self.assertEqual(spoken[2][-1], "Go to page two", "the caret where NVDA left it")

	def test_theBrowsersFocusInTheSamePage(self):
		# The browser's focus is in the page NVDA's is in: NVDA's focus isn't behind, and nothing is queued.
		self.asTheTesterHasIt()
		self.windowsFocus = Obj(self, Role.LINK, self.page)
		self.press("alt+leftArrow")
		self.clock.run(7)
		self.assertEqual(spoken, [["Back"]])
		self.assertIs(self.focus, self.page.rootNVDAObject)

	def test_anotherKeyFirst(self):
		self.asTheTesterHasIt()
		self.page.show(POST, POST_PAGE)
		self.press("alt+leftArrow")
		self.clock.run(0.3)
		self.press("downArrow")
		self.clock.run(7)
		self.assertEqual(spoken, [["Back"]], "the key the user pressed says what it says")

	def test_noPreviousPage(self):
		# Edge says "Can't go back, no previous page": the address stays, and NVDA says nothing more.
		self.asTheTesterHasIt()
		self.reddit.back = lambda: None
		with mock.patch.object(backForward, "_log") as log:
			self.press("alt+leftArrow")
			self.clock.run(7)
		self.assertEqual(spoken, [["Back"]])
		said = [call.args[0] for call in log.return_value.debug.call_args_list]
		self.assertTrue(any("didn't change" in line for line in said), said)

	def test_goingToAnotherProgram(self):
		self.asTheTesterHasIt()
		self.page.show(POST, POST_PAGE)
		self.press("alt+leftArrow")
		self.clock.run(0.2)
		self.focus = Obj(self, Role.WINDOW, appName="outlook")
		self.clock.run(7)
		self.assertEqual(spoken, [["Back"]])

	# -- the keys --------------------------------------------------------------------------------------------------

	def test_forward(self):
		self.asTheTesterHasIt()
		self.press("alt+rightArrow")
		self.clock.run(7)
		self.assertEqual(spoken, [["Forward"]])

	def test_focusModeOff(self):
		# JAWS's GoBack turns forms mode off; NVDA leaves focus mode for browse mode, with its sound or word.
		self.asTheTesterHasIt()
		self.page.show(POST, POST_PAGE)
		self.page.caret = 5
		self.page.passThrough = True
		self.focus = Obj(self, Role.EDITABLETEXT, self.page)
		self.press("alt+leftArrow")
		self.clock.run(7)
		self.assertIs(self.page.passThrough, False)
		self.assertEqual(self.passThroughReports, [False])
		self.assertEqual(spoken[0], ["Back"])

	def test_theBrowsersOwnControls(self):
		# In Edge's address bar there is no page to read: "Back" alone, as JAWS's script says it anywhere in the browser.
		self.asTheTesterHasIt()
		self.focus = Obj(self, Role.EDITABLETEXT)
		self.press("alt+leftArrow")
		self.clock.run(7)
		self.assertEqual(spoken, [["Back"]])

	def test_chromeAndFirefox(self):
		self.asTheTesterHasIt()
		for appName in ("chrome", "firefox"):
			spoken.clear()
			self.focus = Obj(self, Role.DOCUMENT, appName=appName)
			self.press("alt+leftArrow")
			self.clock.run(1)
			self.assertEqual(spoken, [["Back"]], appName)

	def test_otherPrograms(self):
		self.asTheTesterHasIt()
		for appName in ("explorer", "outlook", "winword", "notepad"):
			self.focus = Obj(self, Role.WINDOW, appName=appName)
			self.press("alt+leftArrow")
			self.press("alt+rightArrow")
		self.clock.run(7)
		self.assertEqual(spoken, [], "File Explorer's Back is its own")

	def test_aCommandOnTheKey(self):
		# NVDA or an add-on has a command for Alt+Left here: that command does what it does.
		self.asTheTesterHasIt()
		key = Key("alt+leftArrow")
		key.script = lambda gesture: None
		self.assertTrue(self.decider.decide(gesture=key))
		self.clock.run(7)
		self.assertEqual(spoken, [])

	def test_inputHelp(self):
		self.asTheTesterHasIt()
		sys.modules["inputCore"].manager.isInputHelpActive = True
		self.press("alt+leftArrow")
		self.clock.run(7)
		self.assertEqual(spoken, [])

	def test_otherKeysGoOn(self):
		self.asTheTesterHasIt()
		for name in ("leftArrow", "alt+tab", "control+leftArrow", "alt+shift+leftArrow", "h", "alt+downArrow"):
			self.press(name)
		self.clock.run(7)
		self.assertEqual(spoken, [])

	def test_turnedOff(self):
		self.asTheTesterHasIt()
		backForward.unregister()
		self.assertNotIn(backForward.decideGesture, self.decider.handlers)
		self.page.show(POST, POST_PAGE)
		self.press("alt+leftArrow")
		self.clock.run(7)
		self.assertEqual(spoken, [], "as 1.35")
		backForward.register()
		backForward.register()
		self.assertEqual(self.decider.handlers.count(backForward.decideGesture), 1, "on again, once")

	# -- quick navigation and descriptions -------------------------------------------------------------------------

	def test_aDescriptionIsntSaidInQuickNavigation(self):
		self.asTheTesterHasIt()
		self.quickNav(TITLE_LINE)
		self.assertEqual(spoken, [["What Phones Work Best On Visible?", "visited", "heading", "level 2", "link"]])
		spoken.clear()
		v125.VirtualBufferQuickNavItem("link", self.page, Line(self.page, TITLE_LINE)).report()
		self.assertNotIn(AUTHOR, spoken[0], "K")
		# The log names a description it left out, once.
		linkSpeech._loggedDescriptions.clear()
		self.addCleanup(linkSpeech._loggedDescriptions.clear)
		with mock.patch.object(linkSpeech, "_log") as log:
			self.quickNav(TITLE_LINE)
			self.quickNav(TITLE_LINE)
		said = [call.args[0] for call in log.return_value.debug.call_args_list]
		self.assertEqual(sum("doesn't say a link's or heading's description" in line and AUTHOR in line for line in said), 1, said)

	def test_tabStillSaysIt(self):
		# JAWS says a description when the focus moves (its focus speech), as NVDA does; so does NVDA+Tab.
		self.asTheTesterHasIt()
		self.speech.speakTextInfo(Line(self.page, TITLE_LINE), reason=OutputReason.FOCUS)
		self.assertIn(AUTHOR, spoken[0])

	def test_aHeadingsOwnDescription(self):
		self.asTheTesterHasIt()
		self.page.lines = [[MAIN, dict(heading(2, 30), description="Pinned by moderators"), "Rules"]]
		self.quickNav(0)
		self.assertEqual(spoken, [["Rules", "heading", "level 2"]])

	def test_theArrowKeysAsBefore(self):
		# NVDA says no description of a link as the caret moves (only aria-description, NVDA's own setting); unchanged.
		self.asTheTesterHasIt()
		self.page.caret = TITLE_LINE - 1
		self.arrow()
		self.assertNotIn(AUTHOR, spoken[-1])


class CameBackTests(unittest.TestCase):
	"""NVDA 2026.2's own event_treeInterceptor_gainFocus, which the assistant has NVDA run for a page NVDA's focus went
	to without NVDA coming into it: for a page NVDA had come into before, its title and the line at the caret, as JAWS
	reads a page you go back to. The imitation NVDA is tests/test_v134_pageFirstLine.py's."""

	setUp = v134.PageFirstLineTests.setUp
	_noAssistantsEvent = v134.PageFirstLineTests._noAssistantsEvent
	focusOn = v134.PageFirstLineTests.focusOn
	comeInto = v134.PageFirstLineTests.comeInto

	def test_aPageNvdaHadComeInto(self):
		page = v134.ChromeVBuf(self.root, caretLine=1)
		page._hadFirstGainFocus = True
		self.assertEqual(self.comeInto(page), [[v134.TITLE, "document"], ["link", "Reddit Home"]])

	def test_theLineAloneWhenTheFocusDidntComeFromOutside(self):
		# NVDA's own rule (#4069): the title only when NVDA's focus came from outside the page. After Browse Mode Caret
		# Fix gave NVDA the page's focus and the browser's focus event for the page followed, NVDA took it that its
		# focus hadn't: live, NVDA's own event said "link, Go to page two" alone, where JAWS said the title first.
		page = v134.ChromeVBuf(self.root, caretLine=1)
		page._hadFirstGainFocus = True
		v134.v126.globalVars.focusDifferenceLevel = 2
		self.assertEqual(self.comeInto(page), [["link", "Reddit Home"]])

	def test_withTheAssistantsPageTitle(self):
		v134.browserPages.register()
		page = v134.ChromeVBuf(self.root, caretLine=1)
		page._hadFirstGainFocus = True
		self.assertEqual(self.comeInto(page), [[v134.TITLE], ["link", "Reddit Home"]], "the title without \"document\"")


class BackForwardTests(unittest.TestCase):
	def test_keys(self):
		for name, goes in (("alt+leftArrow", -1), ("alt+rightArrow", 1), ("ALT+LEFTARROW", -1)):
			self.assertEqual(backForward.direction(Key(name)), goes, name)
		for name in ("leftArrow", "alt+shift+leftArrow", "control+alt+leftArrow", "alt+upArrow", "backspace", "alt+numpad4"):
			self.assertEqual(backForward.direction(Key(name)), 0, name)
		self.assertEqual(backForward.direction("kb:alt+leftArrow"), 0, "not a gesture")
		self.assertEqual(backForward.direction(types.SimpleNamespace(normalizedIdentifiers=None)), 0)

	def test_modifiersAloneArentAKey(self):
		count = backForward._gestures
		backForward.decideGesture(gesture=types.SimpleNamespace(isModifier=True))
		self.assertEqual(backForward._gestures, count)
		backForward.decideGesture(gesture=Key("a"))
		self.assertEqual(backForward._gestures, count + 1)

	def test_onUnlessTurnedOff(self):
		self.assertTrue(backForward.wanted({}))
		self.assertTrue(backForward.wanted({backForward.STATE_KEY: True}))
		self.assertFalse(backForward.wanted({backForward.STATE_KEY: False}))
		self.assertFalse(backForward.wanted(None))
		self.assertIs(state.DEFAULTS[backForward.STATE_KEY], True)

	def test_browsers(self):
		self.assertEqual(backForward.BROWSERS, {"msedge", "chrome", "firefox"})


# -- JAWS's and Browse Mode Caret Fix's own files --------------------------------------------------------------------

JAWS = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Freedom Scientific", "JAWS", "2026")


def jawsFile(*parts):
	with open(os.path.join(JAWS, *parts), encoding="utf-8-sig", errors="replace") as f:
		return f.read().replace("\r\n", "\n")


@unittest.skipUnless(os.path.isdir(os.path.join(JAWS, "Scripts")), "JAWS 2026 isn't installed here")
class JawsOwnFilesTests(unittest.TestCase):
	"""What the assistant does, as JAWS 2026's own files have it."""

	def test_theKeys(self):
		for name in ("msedge.jkm", "Chrome.jkm", "firefox.jkm"):
			lines = jawsFile("Scripts", "enu", name).split("\n")
			for line in ("Alt+LeftArrow=GoBack", "Alt+ExtendedLeftArrow=GoBack", "Alt+RightArrow=GoForward", "Alt+ExtendedRightArrow=GoForward"):
				self.assertIn(line, lines, name)

	def test_theWords(self):
		messages = jawsFile("Scripts", "ie.jsm")
		self.assertIn(f"@msgBack1_L\n{backForward.BACK}\n@@", messages)
		self.assertIn(f"@msgForward1_L\n{backForward.FORWARD}\n@@", messages)
		self.assertIn('include "IE.jsm"', jawsFile("Scripts", "IA2Browser.jss"))

	def test_formsModeOff(self):
		scripts = jawsFile("Scripts", "IA2Browser.jss")
		for name, message in (("GoBack", "msgBack1_L"), ("GoForward", "msgForward1_L")):
			body = scripts.split(f"Script {name} ()", 1)[1].split("EndScript", 1)[0]
			self.assertIn(f"SayFormattedMessage (ot_STATUS, {message}, cmsgSilent)", body, name)
			self.assertIn("TurnOffFormsMode ()", body, name)

	def test_descriptionsOffAtMedium(self):
		verbosity = jawsFile("SETTINGS", "enu", "Default.jcf").split("[VirtualCursorVerbosity]", 1)[1].split("\n[", 1)[0].split("\n")
		# High|Medium|Low: JAWS comes at Medium (webRegions reads the same table).
		self.assertIn("DescribedBy=1|0|0", verbosity)
		self.assertIn("ElementDescription=0|0|0", verbosity)
		self.assertIn("Alt+JAWSKey+R=SayDescribedByText", jawsFile("Scripts", "enu", "Chrome.jkm").split("\n"))


def caretFixSource():
	"""Browse Mode Caret Fix's own __init__.py: ADDONS_SOURCE/browseModeCaretFix (the .nvda-addon unpacked), or its
	checkout beside this one."""
	candidates = []
	if os.environ.get("ADDONS_SOURCE"):
		candidates.append(os.path.join(os.environ["ADDONS_SOURCE"], "browseModeCaretFix", "globalPlugins", "browseModeCaretFix", "__init__.py"))
	candidates.append(os.path.join(os.path.dirname(__file__), "..", "..", "allmyaddons", "browseModeCaretFix", "addon", "globalPlugins", "browseModeCaretFix", "__init__.py"))
	return next((path for path in candidates if os.path.isfile(path)), None)


class CaretFixOwnCodeTests(unittest.TestCase):
	def test_itIsBrowseModeCaretFixsCode(self):
		path = caretFixSource()
		if path is None:
			self.skipTest("Browse Mode Caret Fix's source isn't here (set ADDONS_SOURCE)")
		with open(path, encoding="utf-8") as f:
			text = f.read().replace("\r\n", "\n")
		if '"""Browse Mode Caret Fix (3.0.24).' not in text:
			self.skipTest("a newer Browse Mode Caret Fix is here: check what backForward reads of it (_pendingNavigation)")
		self.assertEqual(BROWSE_MODE_CARET_FIX, text)

	def test_whatTheAssistantReadsOfIt(self):
		# backForward waits while Browse Mode Caret Fix has a navigation pending.
		self.assertEqual(backForward.CARET_FIX, CARET_FIX_MODULE)
		self.assertIn(f"\n{backForward.CARET_FIX_PENDING} = None\n", BROWSE_MODE_CARET_FIX)
		self.assertIn(f"\t\t\t_pendingNavigation = None\n", BROWSE_MODE_CARET_FIX)


if __name__ == "__main__":
	unittest.main()
