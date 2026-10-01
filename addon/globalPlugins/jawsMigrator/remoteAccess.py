# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""NVDA's Remote Access in one key, as JAWS's Tandem is (issue 45).

The tester asked "Is it possible to make NVDA remote easier to use?" and, asked what exactly they wanted, answered "I'm
open to suggestions on this." So this is a guess at what a JAWS user finds hard, from NVDA 2026.2's own Remote Access
(source/_remoteClient, globalCommands, the user guide's Remote Access chapter):

- It is off until "Enable Remote Access" is checked in NVDA's Settings, and until then NVDA+Alt+R says only "Action
  unavailable when Remote Access is disabled".
- NVDA+Alt+R opens the Connect to Another Computer dialog: Mode, Server, Host, Key and a Generate Key button (which
  connects to the host to be given a key). The Host has no default, and the other person needs the host and the key.
- Only NVDA+Alt+R and NVDA+Alt+Tab have keys. Disconnect, Copy link, Mute remote, Send clipboard and Send Control+Alt+Delete
  have none.

JAWS's Insert+Alt+T (Default.JKM [Tandem keys], StartOrEndTandemSession) starts a Tandem session for the computer to be
controlled, or ends the session, and asks for nothing. After NVDA+Shift+J:

- T does that. Where no session is running, it turns Remote Access on if it is off (as the Enable Remote Access check
  box does, with no restart), makes a long key of its own (the key is the session's name and its password, so it must be
  hard to guess; NVDA's Generate Key needs no more than that), connects this computer as the one to be controlled to
  the Remote Access server in the assistant's settings, and puts NVDA's own link, nvdaremote://, on the clipboard, for
  the person who will control this computer. Where a session is running or being set up, it ends it (NVDA's own
  disconnect, with its confirmation while controlled).
- Shift+T is the other computer's key: the link on the clipboard, as NVDA's own link handler does. NVDA asks "Do you
  wish to control the computer on server ... with key ...?" first (verifyAndConnect), as it does for a link opened from
  outside NVDA, so a link someone sent can't connect this computer without a yes.
- Control+T puts the link to the session on the clipboard again (NVDA's own Copy link).

JAWS's own Insert+Alt+T, in a migration's key map, goes to T's command (see jawsKeyMap, startorendtandemsession).

The server. NVDA has none set (its Host field is empty). NVDA's user guide gives nvdaremote.com as its example of a
relay server, and the assistant's settings hold the one T uses; nvdaremote.com is only what it starts with. The
server sees the session's traffic as any Remote Access relay does; nothing here changes that.

Only NVDA's own code makes the connection (RemoteClient.connect, verifyAndConnect, copyLink, doDisconnect); this module
chooses what to hand it. It does nothing where NVDA runs in secure mode, where NVDA itself allows no new session.
"""

from __future__ import annotations

import re
import secrets
import time
import urllib.parse

#: The assistant's setting (state.json): the Remote Access server T connects to.
STATE_KEY = "remoteAccessServer"
#: What the setting starts with: the relay server NVDA's user guide names as its example.
DEFAULT_SERVER = "nvdaremote.com"
#: Remote Access's own port (source/_remoteClient/protocol.py SERVER_PORT).
DEFAULT_PORT = 6837
#: The start of NVDA's links (protocol.URL_PREFIX).
LINK_PREFIX = "nvdaremote://"
#: The letters and digits of a session key: no 0, 1, l, o or i, which are mixed up when the key is read out.
KEY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
#: 31 characters make 20 of them about 99 bits, far more than the key needs to be hard to guess.
KEY_LENGTH = 20
#: Another program (a clipboard manager, a speech-on-copy add-on) can hold the clipboard for a moment: NVDA's api.copyToClip
#: then returns False, not an error, so the link is tried a few times before it is said not to be there.
CLIPBOARD_TRIES = 4
CLIPBOARD_WAIT = 0.05

#: What NVDA says or the assistant says. NVDA's own words are NVDA's (pgettext "remote").
TURNED_ON = "Remote Access turned on."
WAITING = "Waiting for someone to control this computer. The link is on the clipboard: send it to them."
NO_CLIPBOARD = "Couldn't copy the link. Give the other person the server, {server}, and the key, {key}."
SECURE_MODE = "NVDA can't start a Remote Access session in secure mode."
NO_LINK = "There is no Remote Access link on the clipboard. Copy the link the other person sent, then try again."
BAD_LINK = "The link on the clipboard isn't a Remote Access link NVDA can use."
UNREACHABLE = (
	"Can't reach {server}. Check that this computer is online, or choose another server in NVDA's Settings, "
	"JAWS Migration Assistant."
)
NOT_RUNNING = "Remote Access is off. Press NVDA+Shift+J, then T to start a session."
CANT_START = "NVDA can't turn Remote Access on."

_failed = False
#: The transport being watched for a first connection that fails, and the server's name for what is said then.
_watched = None
_watchedServer = ""


def _log():
	from logHandler import log

	return log


def _failure(what: str) -> None:
	global _failed
	if _failed:
		return
	_failed = True
	try:
		_log().debugWarning(f"jawsMigrator: {what}", exc_info=True)
	except Exception:
		pass


def _say(message: str) -> None:
	try:
		import ui

		ui.message(message)
	except Exception:
		pass


def server(stateData: dict | None = None) -> str:
	"""The Remote Access server T connects to, as the user wrote it (host, or host:port), without a scheme or slashes."""
	value = stateData.get(STATE_KEY) if isinstance(stateData, dict) else None
	if not isinstance(value, str):
		return DEFAULT_SERVER
	value = value.strip()
	value = re.sub(r"^[A-Za-z][A-Za-z0-9+.-]*://", "", value).strip("/ ")
	return value or DEFAULT_SERVER


def hostAndPort(address: str) -> tuple[str, int]:
	"""``host`` or ``host:port`` as (host, port), as NVDA's protocol.addressToHostPort, with Remote Access's own port where
	none is given. Raises ValueError for an address with no host."""
	parts = urllib.parse.urlparse("//" + address)
	try:
		port = parts.port
	except ValueError:
		raise ValueError(f"{address!r} has no usable port")
	if not parts.hostname:
		raise ValueError(f"{address!r} has no host")
	return parts.hostname, port or DEFAULT_PORT


def makeKey() -> str:
	"""A new session key, from the system's own random source."""
	return "".join(secrets.choice(KEY_ALPHABET) for _ in range(KEY_LENGTH))


def findLink(text: str) -> str | None:
	"""The first Remote Access link in ``text`` (a message may have words and punctuation around it), or None."""
	if not isinstance(text, str):
		return None
	found = re.search(re.escape(LINK_PREFIX) + r"[^\s<>\"']+", text, re.IGNORECASE)
	if found is None:
		return None
	return found.group(0).rstrip(".,;:)]}")


def _value(attribute):
	"""What NVDA's client gives as a method in one version and a property in another (isConnected, isConnecting)."""
	return attribute() if callable(attribute) else attribute


def _isSecure() -> bool:
	try:
		import globalVars

		return bool(globalVars.appArgs.secure)
	except Exception:
		return False


def _client():
	"""NVDA's running Remote Access client, or None while Remote Access is off."""
	import _remoteClient

	return getattr(_remoteClient, "_remoteClient", None)


def isActive() -> bool:
	"""Whether a Remote Access session is running or being set up."""
	client = _client()
	if client is None:
		return False
	try:
		return bool(_value(client.isConnected) or _value(getattr(client, "isConnecting", False)))
	except Exception:
		_failure("could not tell whether a Remote Access session is running")
		return False


def _turnOn():
	"""Remote Access on, as NVDA's Remote Access settings do when Enable Remote Access is checked and saved: the setting
	kept, and the client started, with no restart. Returns (client, turnedOn), or (None, False)."""
	client = _client()
	if client is not None:
		return client, False
	try:
		import _remoteClient
		import config

		remote = config.conf["remote"]
		remote["enabled"] = True
	except Exception:
		_failure("could not turn Remote Access on")
		return None, False
	try:
		_remoteClient.initialize()
		client = _client()
	except Exception:
		_failure("could not start NVDA's Remote Access")
		client = None
	if client is None:
		# Not left on where it isn't running.
		try:
			remote["enabled"] = False
		except Exception:
			pass
		return None, False
	return client, True


# -- T -----------------------------------------------------------------------------------------------------------------


def startOrEnd(stateData: dict) -> bool:
	"""T: end the session that is running or being set up, or start one for this computer to be controlled. Returns
	whether it did either."""
	if isActive():
		return end()
	return share(stateData)


def end() -> bool:
	"""NVDA's own disconnect: the same words and sounds, and the same confirmation while this computer is controlled."""
	client = _client()
	if client is None:
		_say(NOT_RUNNING)
		return False
	try:
		client.doDisconnect()
	except Exception:
		_failure("could not end the Remote Access session")
		return False
	return True


def share(stateData: dict) -> bool:
	"""Connect this computer as the one to be controlled, and put the link for the person who will control it on the
	clipboard. Returns whether the connection was started."""
	if _isSecure():
		_say(SECURE_MODE)
		return False
	address = server(stateData)
	try:
		host, port = hostAndPort(address)
	except ValueError:
		_failure(f"the Remote Access server {address!r} isn't usable")
		_say(UNREACHABLE.format(server=address))
		return False
	client, turnedOn = _turnOn()
	if client is None:
		_say(CANT_START)
		return False
	try:
		from _remoteClient.connectionInfo import ConnectionInfo, ConnectionMode

		info = ConnectionInfo(hostname=host, mode=ConnectionMode.FOLLOWER, key=makeKey(), port=port)
		client.connect(info)
	except Exception:
		_failure("could not start the Remote Access session")
		_say(CANT_START)
		return False
	_watch(client, address)
	prefix = TURNED_ON + " " if turnedOn else ""
	if not _copyToClipboard(info.getURLToConnect()):
		_failure("could not put the Remote Access link on the clipboard")
		_say(prefix + NO_CLIPBOARD.format(server=address, key=info.key))
		return True
	_say(prefix + WAITING)
	return True


# -- Shift+T -----------------------------------------------------------------------------------------------------------


def join() -> bool:
	"""Shift+T: control another computer with the link on the clipboard. NVDA asks the user to confirm first. Returns
	whether NVDA was handed the link."""
	if _isSecure():
		_say(SECURE_MODE)
		return False
	link = findLink(_clipboardText())
	if link is None:
		_say(NO_LINK)
		return False
	try:
		from _remoteClient.connectionInfo import ConnectionInfo

		info = ConnectionInfo.fromURL(link)
	except Exception:
		_say(BAD_LINK)
		return False
	client, _turnedOn = _turnOn()
	if client is None:
		_say(CANT_START)
		return False
	try:
		# NVDA's own question, "Do you wish to control the computer on server ... with key ...?", and then its connection.
		client.verifyAndConnect(info)
	except Exception:
		_failure("could not hand the Remote Access link to NVDA")
		_say(CANT_START)
		return False
	return True


def _copyToClipboard(text: str) -> bool:
	"""Whether ``text`` is on the clipboard. NVDA's api.copyToClip says False where it couldn't write it (the clipboard
	is held by another program) as well as raising for other failures; either way it is tried again a few times."""
	for attempt in range(CLIPBOARD_TRIES):
		if attempt:
			time.sleep(CLIPBOARD_WAIT)
		try:
			import api

			if api.copyToClip(text) is True:
				return True
		except Exception:
			pass
	return False


def _clipboardText() -> str:
	for attempt in range(CLIPBOARD_TRIES):
		if attempt:
			time.sleep(CLIPBOARD_WAIT)
		try:
			import api

			text = api.getClipData()
		except Exception:
			continue
		if text:
			return text
	return ""


# -- Control+T ---------------------------------------------------------------------------------------------------------


def copyLink() -> bool:
	"""Control+T: NVDA's own Copy link, with its "Copied link" and its "Not connected"."""
	client = _client()
	if client is None:
		_say(NOT_RUNNING)
		return False
	try:
		client.copyLink()
	except Exception:
		_failure("could not copy the Remote Access link")
		return False
	return True


# -- a server that can't be reached ----------------------------------------------------------------------------------


def _watch(client, address: str) -> None:
	"""NVDA tells the user nothing when the computer to be controlled can't reach its server: it tries again every five
	seconds, in silence. The first failure, before any connection, is said and the attempt ends."""
	global _watched, _watchedServer
	unwatch()
	transport = getattr(client, "followerTransport", None)
	if transport is None:
		return
	try:
		transport.transportConnectionFailed.register(_onConnectionFailed)
		transport.transportConnected.register(_onConnected)
	except Exception:
		_failure("could not watch the Remote Access connection")
		return
	_watched, _watchedServer = transport, address


def unwatch() -> None:
	"""Stop watching (also when the plugin ends)."""
	global _watched, _watchedServer
	transport, _watched, _watchedServer = _watched, None, ""
	if transport is None:
		return
	for point, handler in (("transportConnectionFailed", _onConnectionFailed), ("transportConnected", _onConnected)):
		try:
			getattr(transport, point).unregister(handler)
		except Exception:
			pass


def _later(function, *args) -> None:
	# NVDA's transport notifies from its connection thread, and goes through the handlers as they are: a handler taken out
	# meanwhile stops its loop ("OrderedDict mutated during iteration").
	import wx

	wx.CallAfter(function, *args)


def _onConnectionFailed(*args, **kwargs) -> None:
	transport = _watched
	if transport is not None:
		_later(_connectionFailed, transport)


def _onConnected(*args, **kwargs) -> None:
	if _watched is not None:
		_later(unwatch)


def _connectionFailed(transport) -> None:
	if transport is not _watched:
		return
	address = _watchedServer
	unwatch()
	client = _client()
	if client is None or getattr(client, "followerTransport", None) is not transport:
		return
	if getattr(transport, "successfulConnects", 1):
		return
	try:
		try:
			client.disconnect(_silent=True)
		except TypeError:
			client.disconnect()
	except Exception:
		_failure("could not end the Remote Access attempt that found no server")
	_say(UNREACHABLE.format(server=address))


def stop() -> None:
	"""The plugin ends."""
	unwatch()
