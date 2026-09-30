# Unit tests for version 1.48 (built first as 1.42, never released under it), from issue 45, "Make NVDA remote easier to use?". The tester was asked what exactly they wanted
# and how NVDA should behave, and answered "I'm open to suggestions on this." So the assistant guesses, from NVDA 2026.2's own
# Remote Access: it is off until "Enable Remote Access" is checked; NVDA+Alt+R opens a dialog with Mode, Server, Host, Key
# and Generate Key, and its Host has no default; and only NVDA+Alt+R and NVDA+Alt+Tab have keys. JAWS's Insert+Alt+T
# (Default.JKM [Tandem keys], StartOrEndTandemSession) starts a Tandem session for the computer to be controlled, or ends it,
# and asks for nothing.
# - NVDA+Shift+J, then T turns Remote Access on where it is off, connects this computer as the one to be controlled to the
#   assistant's server with a key of its own, and puts NVDA's own link on the clipboard; where a session runs, it ends it
#   (ShareTests, StartOrEndTests, RemoteOffTests).
# - Shift+T connects with the link on the clipboard through NVDA's own verifyAndConnect, which asks first (JoinTests).
# - Control+T copies the link again, through NVDA's own copyLink (LinkTests).
# - A server that can't be reached is said, once, and the attempt ends; NVDA itself tries again in silence (WatchTests).
# - The server is a setting, nvdaremote.com (the example in NVDA's user guide) to begin with (ServerTests), and JAWS's
#   Insert+Alt+T goes to T's command in a migration's key map (WiringTests).
# NVDA 2026.2's own connectionInfo.py and protocol.py run here (tests/nvda2026_2, with a small shim for Python 3.10: NVDA
# runs Python 3.13). What is imitated: NVDA's RemoteClient (the same methods and properties, as source/_remoteClient/client.py
# has them), its transport's extension points (NVDA goes through an extension point's handlers as they are, so a handler taken
# out meanwhile fails), wx (CallAfter is run by the test), config and the clipboard.
# Run: python -m unittest tests.test_v148_remoteAccess -v

import collections
import enum
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import jawsKeyMap, remoteAccess, state  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "nvda2026_2", "_remoteClient")


def _loadNvdaFile(package, name):
	"""NVDA 2026.2's own source/_remoteClient/<name>.py, with the two Python 3.11 names its imports need under 3.10."""
	with open(os.path.join(FIXTURES, name + ".py"), encoding="utf-8") as stream:
		source = stream.read()
	if sys.version_info < (3, 11):
		source = source.replace(
			"from enum import StrEnum",
			"from enum import Enum\n\n\nclass StrEnum(str, Enum):\n\tdef __str__(self):\n\t\treturn str(self.value)\n",
		)
		source = source.replace("from typing import Self", "Self = object")
	module = types.ModuleType(f"{package.__name__}.{name}")
	module.__package__ = package.__name__
	module.__file__ = os.path.join(FIXTURES, name + ".py")
	sys.modules[module.__name__] = module
	setattr(package, name, module)
	exec(compile(source, module.__file__, "exec"), module.__dict__)
	return module


class Action:
	"""NVDA's extensionPoints.Action: handlers kept by key, notified as they are (a handler that takes another out while
	NVDA goes through them raises "OrderedDict mutated during iteration"), and a handler not registered is passed over."""

	def __init__(self):
		self._handlers = collections.OrderedDict()

	def register(self, handler):
		self._handlers[(handler.__module__, handler.__qualname__)] = handler

	def unregister(self, handler):
		return self._handlers.pop((handler.__module__, handler.__qualname__), None) is not None

	def notify(self, **kwargs):
		for handler in self._handlers.values():
			handler(**kwargs)


class FakeTransport:
	def __init__(self):
		self.connected = False
		self.successfulConnects = 0
		self.transportConnected = Action()
		self.transportConnectionFailed = Action()
		self.reconnectorThread = types.SimpleNamespace(running=True)


class FakeSession:
	def __init__(self, info):
		self.info = info

	def getConnectionInfo(self):
		return self.info


class FakeClient:
	"""NVDA 2026.2's RemoteClient, as far as the assistant uses it: isConnected is a method, isConnecting a property."""

	def __init__(self, world):
		self.world = world
		self.calls = []
		self.followerTransport = self.leaderTransport = None
		self.followerSession = self.leaderSession = None
		self._connecting = False

	def isConnected(self):
		transport = self.followerTransport or self.leaderTransport
		return transport.connected if transport is not None else False

	@property
	def isConnecting(self):
		transport = self.followerTransport or self.leaderTransport
		return self._connecting or (not self.isConnected() and transport is not None and transport.reconnectorThread.running)

	def connect(self, info):
		self.calls.append(("connect", info))
		if self.world.connectFails:
			raise OSError("no")
		self._connecting = True
		transport = FakeTransport()
		if info.mode == self.world.connectionInfo.ConnectionMode.FOLLOWER:
			self.followerTransport, self.followerSession = transport, FakeSession(info)
		else:
			self.leaderTransport, self.leaderSession = transport, FakeSession(info)

	def verifyAndConnect(self, info):
		self.calls.append(("verifyAndConnect", info))

	def doDisconnect(self):
		self.calls.append(("doDisconnect",))

	def disconnect(self, *, _silent=False):
		self.calls.append(("disconnect", _silent))
		self.followerTransport = self.leaderTransport = None
		self.followerSession = self.leaderSession = None
		self._connecting = False

	def copyLink(self):
		self.calls.append(("copyLink",))
		session = self.leaderSession or self.followerSession
		if session is None:
			self.world.ui.delayedMessage("Not connected")
			return
		self.world.clipboard = str(session.getConnectionInfo().getURLToConnect())
		self.world.ui.delayedMessage("Copied link")


class World:
	"""The parts of NVDA around the assistant's module, as source/_remoteClient/__init__.py and settingsDialogs's Remote
	Access panel leave them."""

	def __init__(self):
		self.said = []
		self.delayed = []
		self.after = []
		self.clipboard = ""
		#: NVDA's api.copyToClip returns False where the clipboard is held by another program, and raises for other failures.
		self.clipboardFails = False
		self.clipboardRaises = False
		#: How many calls find the clipboard held before it is free.
		self.clipboardBusyFor = 0
		self.connectFails = False
		self.initializeFails = False
		self.initializeCalls = 0
		self.secure = False
		self.conf = {"remote": {"enabled": False}}
		self.package = types.ModuleType("_remoteClient")
		self.package.__path__ = [FIXTURES]
		self.package._remoteClient = None
		self.package.initialize = self._initialize
		self.package.remoteRunning = lambda: self.package._remoteClient is not None
		sys.modules["_remoteClient"] = self.package
		self.protocol = _loadNvdaFile(self.package, "protocol")
		self.connectionInfo = _loadNvdaFile(self.package, "connectionInfo")
		self.ui = types.ModuleType("ui")
		self.ui.message = self.said.append
		self.ui.delayedMessage = self.delayed.append
		self.api = types.ModuleType("api")
		self.api.copyToClip = self._copyToClip
		self.api.getClipData = self._getClipData
		self.config = types.ModuleType("config")
		self.config.conf = self.conf
		self.globalVars = types.ModuleType("globalVars")
		self.globalVars.appArgs = types.SimpleNamespace(secure=False)

	def _initialize(self):
		self.initializeCalls += 1
		if self.initializeFails:
			raise RuntimeError("no")
		if not self.conf["remote"]["enabled"]:
			return
		self.package._remoteClient = FakeClient(self)

	def _copyToClip(self, text):
		"""api.copyToClip(text, notify=False) -> bool, as NVDA 2026.2's source/api.py has it."""
		if self.clipboardRaises:
			raise OSError("clipboard busy")
		if self.clipboardFails:
			return False
		if self.clipboardBusyFor:
			self.clipboardBusyFor -= 1
			return False
		if not isinstance(text, str) or len(text) == 0:
			return False
		self.clipboard = text
		return True

	def _getClipData(self):
		if self.clipboardBusyFor:
			self.clipboardBusyFor -= 1
			raise OSError("clipboard busy")
		if not isinstance(self.clipboard, str) or self.clipboard == "":
			raise OSError("Clipboard not text")
		return self.clipboard

	def modules(self):
		return {
			"_remoteClient": self.package,
			"_remoteClient.protocol": self.protocol,
			"_remoteClient.connectionInfo": self.connectionInfo,
			"ui": self.ui,
			"api": self.api,
			"config": self.config,
			"globalVars": self.globalVars,
		}

	@property
	def client(self):
		return self.package._remoteClient

	def turnOn(self):
		self.conf["remote"]["enabled"] = True
		self._initialize()
		return self.client

	def runQueued(self):
		"""wx.CallAfter's functions, run, as they are once NVDA's own notification has finished."""
		while self.after:
			function, args = self.after.pop(0)
			function(*args)


class RemoteCase(unittest.TestCase):
	def setUp(self):
		self.world = World()
		patcher = mock.patch.dict(sys.modules, self.world.modules())
		patcher.start()
		self.addCleanup(patcher.stop)
		import wx

		later = mock.patch.object(wx, "CallAfter", side_effect=lambda function, *args: self.world.after.append((function, args)))
		later.start()
		self.addCleanup(later.stop)
		self.addCleanup(remoteAccess.stop)
		self.state = {}

	@property
	def said(self):
		return self.world.said

	def info(self):
		"""What the client was given to connect with."""
		return [call[1] for call in self.world.client.calls if call[0] == "connect"][-1]


class ServerTests(unittest.TestCase):
	def test_theServerBeginsAsNvdasOwnExample(self):
		self.assertEqual(remoteAccess.DEFAULT_SERVER, "nvdaremote.com")
		self.assertEqual(state.DEFAULTS[remoteAccess.STATE_KEY], "nvdaremote.com")
		self.assertEqual(remoteAccess.server({}), "nvdaremote.com")
		self.assertEqual(remoteAccess.server(None), "nvdaremote.com")

	def test_whatTheUserWroteIsKeptAsAHost(self):
		for written, kept in (
			("example.com", "example.com"),
			("  example.com:1234 ", "example.com:1234"),
			("https://example.com/", "example.com"),
			("nvdaremote://example.com:99", "example.com:99"),
			("", "nvdaremote.com"),
			("   ", "nvdaremote.com"),
			("///", "nvdaremote.com"),
		):
			self.assertEqual(remoteAccess.server({remoteAccess.STATE_KEY: written}), kept, written)
		self.assertEqual(remoteAccess.server({remoteAccess.STATE_KEY: 5}), "nvdaremote.com")

	def test_hostAndPort(self):
		self.assertEqual(remoteAccess.hostAndPort("example.com"), ("example.com", 6837))
		self.assertEqual(remoteAccess.hostAndPort("example.com:1234"), ("example.com", 1234))
		self.assertEqual(remoteAccess.hostAndPort("[::1]:22"), ("::1", 22))
		for bad in ("", ":1234", "example.com:port", "example.com:99999"):
			with self.assertRaises(ValueError, msg=bad):
				remoteAccess.hostAndPort(bad)

	def test_theSettingIsKeptAndRead(self):
		self.assertIsInstance(state.DEFAULTS[remoteAccess.STATE_KEY], str, "state.load keeps a value only of its default's type")


class KeyTests(unittest.TestCase):
	def test_aKeyIsLongAndReadableAloud(self):
		key = remoteAccess.makeKey()
		self.assertEqual(len(key), remoteAccess.KEY_LENGTH)
		self.assertTrue(set(key) <= set(remoteAccess.KEY_ALPHABET), key)
		self.assertFalse(set("01ilo") & set(remoteAccess.KEY_ALPHABET), "no character read out as another")

	def test_everyKeyIsNew(self):
		keys = {remoteAccess.makeKey() for _ in range(500)}
		self.assertEqual(len(keys), 500)

	def test_theKeyComesFromTheSystemsRandomSource(self):
		with mock.patch.object(remoteAccess.secrets, "choice", side_effect=lambda alphabet: alphabet[0]) as choice:
			self.assertEqual(remoteAccess.makeKey(), remoteAccess.KEY_ALPHABET[0] * remoteAccess.KEY_LENGTH)
		self.assertEqual(choice.call_count, remoteAccess.KEY_LENGTH)


class LinkTextTests(unittest.TestCase):
	LINK = "nvdaremote://nvdaremote.com:6837?key=abc234&mode=master"

	def test_aLinkAloneOrInAMessage(self):
		self.assertEqual(remoteAccess.findLink(self.LINK), self.LINK)
		self.assertEqual(remoteAccess.findLink(f"Hi, please use {self.LINK} thanks"), self.LINK)
		self.assertEqual(remoteAccess.findLink(f"Use {self.LINK}."), self.LINK)
		self.assertEqual(remoteAccess.findLink(f"<{self.LINK}>"), self.LINK)
		self.assertEqual(remoteAccess.findLink(f"({self.LINK})"), self.LINK)
		self.assertEqual(remoteAccess.findLink(f"first\n{self.LINK}\nsecond"), self.LINK)
		self.assertEqual(remoteAccess.findLink(self.LINK.upper().replace("NVDAREMOTE://", "NVDAREMOTE://")), self.LINK.upper())

	def test_noLink(self):
		for text in ("", "nothing here", "https://example.com", "nvdaremote", None, 5):
			self.assertIsNone(remoteAccess.findLink(text), repr(text))


class ShareTests(RemoteCase):
	def test_remoteAccessOffIsTurnedOnAsNvdasSettingsDoAndTheLinkIsOnTheClipboard(self):
		self.assertIsNone(self.world.client)
		self.assertTrue(remoteAccess.share(self.state))
		self.assertTrue(self.world.conf["remote"]["enabled"], "the setting Enable Remote Access is checked, kept")
		self.assertEqual(self.world.initializeCalls, 1, "NVDA's own initialize, with no restart")
		self.assertEqual(self.said, [remoteAccess.TURNED_ON + " " + remoteAccess.WAITING])
		info = self.info()
		self.assertEqual((info.hostname, info.port), ("nvdaremote.com", 6837))
		self.assertEqual(info.mode, self.world.connectionInfo.ConnectionMode.FOLLOWER, "this computer is the one controlled")
		self.assertEqual(len(info.key), remoteAccess.KEY_LENGTH)
		self.assertFalse(info.insecure)

	def test_theLinkIsNvdasOwnAndForTheOtherComputer(self):
		remoteAccess.share(self.state)
		info = self.info()
		link = self.world.clipboard
		self.assertEqual(link, info.getURLToConnect(), "NVDA's own link")
		# NVDA leaves Remote Access's own port out of a link.
		self.assertTrue(link.startswith("nvdaremote://nvdaremote.com?"), link)
		self.assertIn("mode=master", link, "the other person controls")
		self.assertIn("key=" + info.key, link)
		parsed = self.world.connectionInfo.ConnectionInfo.fromURL(link)
		self.assertEqual((parsed.hostname, parsed.port, parsed.key), ("nvdaremote.com", 6837, info.key))
		self.assertEqual(parsed.mode, self.world.connectionInfo.ConnectionMode.LEADER)

	def test_eachSessionHasAKeyOfItsOwn(self):
		remoteAccess.share(self.state)
		first = self.info().key
		self.world.client.disconnect()
		remoteAccess.share(self.state)
		self.assertNotEqual(self.info().key, first)

	def test_remoteAccessAlreadyOnIsNotTurnedOnAgain(self):
		self.world.turnOn()
		self.world.initializeCalls = 0
		remoteAccess.share(self.state)
		self.assertEqual(self.world.initializeCalls, 0)
		self.assertEqual(self.said, [remoteAccess.WAITING], "no word about turning it on")

	def test_theServerIsTheSettings(self):
		remoteAccess.share({remoteAccess.STATE_KEY: "relay.example.org:1234"})
		info = self.info()
		self.assertEqual((info.hostname, info.port), ("relay.example.org", 1234))
		self.assertTrue(self.world.clipboard.startswith("nvdaremote://relay.example.org:1234?"))

	def test_whereTheLinkCantBeCopiedTheServerAndKeyAreSaid(self):
		# api.copyToClip says False, it doesn't raise, where another program holds the clipboard (1.48: the link was said
		# to be on the clipboard all the same).
		self.world.clipboardFails = True
		self.assertTrue(remoteAccess.share(self.state), "the connection is made all the same")
		key = self.info().key
		self.assertEqual(self.said, [remoteAccess.TURNED_ON + " " + remoteAccess.NO_CLIPBOARD.format(server="nvdaremote.com", key=key)])
		self.assertEqual(self.world.clipboard, "", "and the link is not said to be there")

	def test_aClipboardThatRaisesIsSaidTheSameWay(self):
		self.world.clipboardRaises = True
		remoteAccess.share(self.state)
		key = self.info().key
		self.assertEqual(self.said, [remoteAccess.TURNED_ON + " " + remoteAccess.NO_CLIPBOARD.format(server="nvdaremote.com", key=key)])

	def test_aClipboardHeldForAMomentTakesTheLinkWhenItIsFree(self):
		self.world.clipboardBusyFor = remoteAccess.CLIPBOARD_TRIES - 1
		remoteAccess.share(self.state)
		self.assertEqual(self.said, [remoteAccess.TURNED_ON + " " + remoteAccess.WAITING])
		self.assertEqual(self.world.clipboard, self.info().getURLToConnect())

	def test_secureModeStartsNothing(self):
		self.world.globalVars.appArgs.secure = True
		self.assertFalse(remoteAccess.share(self.state))
		self.assertEqual(self.said, [remoteAccess.SECURE_MODE])
		self.assertFalse(self.world.conf["remote"]["enabled"], "the setting is left as it was")
		self.assertIsNone(self.world.client)
		self.assertEqual(self.world.clipboard, "")

	def test_aServerNoOneCanUseIsSaidAndNothingChanges(self):
		self.assertFalse(remoteAccess.share({remoteAccess.STATE_KEY: ":1234"}))
		self.assertEqual(self.said, [remoteAccess.UNREACHABLE.format(server=":1234")])
		self.assertFalse(self.world.conf["remote"]["enabled"])

	def test_remoteAccessThatWontStartIsNotLeftOn(self):
		self.world.initializeFails = True
		self.assertFalse(remoteAccess.share(self.state))
		self.assertEqual(self.said, [remoteAccess.CANT_START])
		self.assertFalse(self.world.conf["remote"]["enabled"], "not left checked where it isn't running")

	def test_remoteAccessThatDoesntComeUpIsNotLeftOnEither(self):
		self.world.package.initialize = lambda: None
		self.assertFalse(remoteAccess.share(self.state))
		self.assertEqual(self.said, [remoteAccess.CANT_START])
		self.assertFalse(self.world.conf["remote"]["enabled"])

	def test_aConnectionNVDARefusesIsSaid(self):
		self.world.turnOn()
		self.world.connectFails = True
		self.assertFalse(remoteAccess.share(self.state))
		self.assertEqual(self.said, [remoteAccess.CANT_START])
		self.assertEqual(self.world.clipboard, "", "no link for a session that isn't there")

	def test_isConnectingAsAPropertyOrAMethodBothWork(self):
		# NVDA 2026.2 has isConnected() as a method and isConnecting as a property; another version may differ.
		client = self.world.turnOn()
		self.assertFalse(remoteAccess.isActive())
		remoteAccess.share(self.state)
		self.assertTrue(remoteAccess.isActive(), "connecting")

		class Other(FakeClient):
			isConnected = False

			def isConnecting(self):
				return self.answer

		other = Other(self.world)
		self.world.package._remoteClient = other
		other.answer = False
		self.assertFalse(remoteAccess.isActive(), "a property or a method, not connected, not connecting")
		other.answer = True
		self.assertTrue(remoteAccess.isActive())
		other.isConnected = True
		other.answer = False
		self.assertTrue(remoteAccess.isActive(), "connected")


class StartOrEndTests(RemoteCase):
	def test_noSessionStartsOne(self):
		self.assertTrue(remoteAccess.startOrEnd(self.state))
		self.assertEqual([call[0] for call in self.world.client.calls], ["connect"])

	def test_aSessionBeingSetUpIsEnded(self):
		remoteAccess.startOrEnd(self.state)
		self.said.clear()
		self.assertTrue(remoteAccess.startOrEnd(self.state))
		self.assertEqual([call[0] for call in self.world.client.calls], ["connect", "doDisconnect"])
		self.assertEqual(self.said, [], "NVDA's own words and sound, and its confirmation while controlled, say it")

	def test_aSessionThatIsRunningIsEnded(self):
		client = self.world.turnOn()
		client.connect(self.world.connectionInfo.ConnectionInfo("example.com", "master", "key"))
		client.leaderTransport.connected = True
		client._connecting = False
		self.assertTrue(remoteAccess.startOrEnd(self.state))
		self.assertEqual(client.calls[-1], ("doDisconnect",))

	def test_remoteAccessOnWithNoSessionStartsOne(self):
		client = self.world.turnOn()
		self.assertTrue(remoteAccess.startOrEnd(self.state))
		self.assertEqual([call[0] for call in client.calls], ["connect"])

	def test_endWhereRemoteAccessIsOffSaysSo(self):
		self.assertFalse(remoteAccess.end())
		self.assertEqual(self.said, [remoteAccess.NOT_RUNNING])

	def test_endThatFailsIsLoggedNotRaised(self):
		client = self.world.turnOn()
		client.doDisconnect = mock.Mock(side_effect=RuntimeError("no"))
		self.assertFalse(remoteAccess.end())


class JoinTests(RemoteCase):
	LINK = "nvdaremote://relay.example.org:1234?key=abcdefg&mode=master"

	def test_theLinkGoesToNvdasOwnConfirmation(self):
		self.world.clipboard = f"Please use {self.LINK}."
		self.assertTrue(remoteAccess.join())
		call = self.world.client.calls[-1]
		self.assertEqual(call[0], "verifyAndConnect", "NVDA asks first, as for any link, and only then connects")
		info = call[1]
		self.assertEqual((info.hostname, info.port, info.key), ("relay.example.org", 1234, "abcdefg"))
		self.assertEqual(info.mode, self.world.connectionInfo.ConnectionMode.LEADER)
		self.assertNotIn("connect", [c[0] for c in self.world.client.calls], "nothing connects without the yes")
		self.assertEqual(self.said, [])

	def test_aClipboardHeldForAMomentIsReadWhenItIsFree(self):
		self.world.clipboard = self.LINK
		self.world.clipboardBusyFor = remoteAccess.CLIPBOARD_TRIES - 1
		self.assertTrue(remoteAccess.join())
		self.assertEqual(self.world.client.calls[-1][0], "verifyAndConnect")

	def test_remoteAccessOffIsTurnedOnFirst(self):
		self.world.clipboard = self.LINK
		remoteAccess.join()
		self.assertTrue(self.world.conf["remote"]["enabled"])
		self.assertEqual(self.world.initializeCalls, 1)

	def test_theLinkShareMadeIsOneJoinTakes(self):
		remoteAccess.share(self.state)
		mine = self.info()
		link = self.world.clipboard
		# The other computer.
		other = World()
		other.clipboard = link
		with mock.patch.dict(sys.modules, other.modules()):
			other.turnOn()
			self.assertTrue(remoteAccess.join())
		info = other.client.calls[-1][1]
		self.assertEqual((info.hostname, info.port, info.key), (mine.hostname, mine.port, mine.key))
		self.assertEqual(info.mode, other.connectionInfo.ConnectionMode.LEADER)

	def test_noLinkOnTheClipboardIsSaid(self):
		for text in ("", "some text", "https://example.com"):
			self.said.clear()
			self.world.clipboard = text
			self.assertFalse(remoteAccess.join(), text)
			self.assertEqual(self.said, [remoteAccess.NO_LINK], text)
		self.assertFalse(self.world.conf["remote"]["enabled"], "nothing was turned on for nothing")

	def test_aLinkNVDACantUseIsSaid(self):
		for text in ("nvdaremote://?key=abc&mode=master", "nvdaremote://example.com?mode=master", "nvdaremote://example.com?key=abc&mode=boss"):
			self.said.clear()
			self.world.clipboard = text
			self.assertFalse(remoteAccess.join(), text)
			self.assertEqual(self.said, [remoteAccess.BAD_LINK], text)
		self.assertFalse(self.world.conf["remote"]["enabled"])

	def test_secureModeJoinsNothing(self):
		self.world.globalVars.appArgs.secure = True
		self.world.clipboard = self.LINK
		self.assertFalse(remoteAccess.join())
		self.assertEqual(self.said, [remoteAccess.SECURE_MODE])
		self.assertIsNone(self.world.client)

	def test_remoteAccessThatWontStartIsSaid(self):
		self.world.clipboard = self.LINK
		self.world.initializeFails = True
		self.assertFalse(remoteAccess.join())
		self.assertEqual(self.said, [remoteAccess.CANT_START])
		self.assertFalse(self.world.conf["remote"]["enabled"])


class LinkTests(RemoteCase):
	def test_controlTCopiesTheLinkAgainWithNvdasOwnWords(self):
		remoteAccess.share(self.state)
		link = self.world.clipboard
		self.world.clipboard = "something else"
		self.assertTrue(remoteAccess.copyLink())
		self.assertEqual(self.world.clipboard, link)
		self.assertEqual(self.world.delayed, ["Copied link"])

	def test_noSessionIsNvdasNotConnected(self):
		self.world.turnOn()
		remoteAccess.copyLink()
		self.assertEqual(self.world.delayed, ["Not connected"])

	def test_remoteAccessOffSaysHowToStartOne(self):
		self.assertFalse(remoteAccess.copyLink())
		self.assertEqual(self.said, [remoteAccess.NOT_RUNNING])


class WatchTests(RemoteCase):
	def start(self):
		remoteAccess.share(self.state)
		self.said.clear()
		return self.world.client.followerTransport

	def test_aServerThatCantBeReachedIsSaidOnceAndTheAttemptEnds(self):
		transport = self.start()
		transport.transportConnectionFailed.notify()
		self.assertEqual(self.said, [], "said after NVDA's notification, not in it")
		self.world.runQueued()
		self.assertEqual(self.said, [remoteAccess.UNREACHABLE.format(server="nvdaremote.com")])
		self.assertEqual(self.world.client.calls[-1], ("disconnect", True), "NVDA's own disconnect, without its word")
		self.assertIsNone(self.world.client.followerTransport)
		self.assertFalse(remoteAccess.isActive())

	def test_theServerNamedIsTheOneChosen(self):
		remoteAccess.share({remoteAccess.STATE_KEY: "relay.example.org:1234"})
		self.said.clear()
		self.world.client.followerTransport.transportConnectionFailed.notify()
		self.world.runQueued()
		self.assertEqual(self.said, [remoteAccess.UNREACHABLE.format(server="relay.example.org:1234")])

	def test_noHandlerIsTakenOutWhileNvdaGoesThroughThem(self):
		# NVDA's own extension point raises where a handler unregisters while it is being notified.
		transport = self.start()
		transport.transportConnectionFailed.notify()
		self.assertEqual(len(transport.transportConnectionFailed._handlers), 1)
		self.world.runQueued()
		self.assertEqual(len(transport.transportConnectionFailed._handlers), 0)
		self.assertEqual(len(transport.transportConnected._handlers), 0)

	def test_aSecondFailureIsNotSaidAgain(self):
		transport = self.start()
		transport.transportConnectionFailed.notify()
		transport.transportConnectionFailed.notify()
		self.world.runQueued()
		self.assertEqual(len(self.said), 1)

	def test_aConnectionMadeEndsTheWatch(self):
		transport = self.start()
		transport.connected = True
		transport.successfulConnects = 1
		transport.transportConnected.notify()
		self.world.runQueued()
		self.assertEqual(len(transport.transportConnectionFailed._handlers), 0)
		self.assertEqual(len(transport.transportConnected._handlers), 0)
		transport.transportConnectionFailed.notify()
		self.world.runQueued()
		self.assertEqual(self.said, [], "a connection that was lost is NVDA's to say")

	def test_aFailureAfterAConnectionIsNotOurs(self):
		transport = self.start()
		transport.successfulConnects = 1
		transport.transportConnectionFailed.notify()
		self.world.runQueued()
		self.assertEqual(self.said, [])
		self.assertNotIn(("disconnect", True), self.world.client.calls)

	def test_aTransportNVDAHasSinceReplacedIsLeftAlone(self):
		# NVDA's certificate question ends the transport and, once answered, connects with a new one.
		transport = self.start()
		self.world.client.followerTransport = None
		transport.transportConnectionFailed.notify()
		self.world.runQueued()
		self.assertEqual(self.said, [])
		self.assertEqual([call[0] for call in self.world.client.calls], ["connect"])

	def test_theSessionEndedByTheUserFirstIsLeftAlone(self):
		transport = self.start()
		self.world.client.disconnect()
		self.world.client.calls.clear()
		transport.transportConnectionFailed.notify()
		self.world.runQueued()
		self.assertEqual(self.said, [])
		self.assertEqual(self.world.client.calls, [])

	def test_aNewSessionWatchesTheNewTransportOnly(self):
		first = self.start()
		self.world.client.disconnect()
		second = self.start()
		self.assertEqual(len(first.transportConnectionFailed._handlers), 0)
		self.assertEqual(len(second.transportConnectionFailed._handlers), 1)

	def test_stopTakesTheWatchOut(self):
		transport = self.start()
		remoteAccess.stop()
		self.assertEqual(len(transport.transportConnectionFailed._handlers), 0)
		self.assertEqual(len(transport.transportConnected._handlers), 0)
		remoteAccess.stop()

	def test_aClientThatTakesNoSilentFlagStillEndsTheAttempt(self):
		transport = self.start()
		calls = []

		def disconnect():
			calls.append("disconnect")
			self.world.client.followerTransport = None

		self.world.client.disconnect = disconnect
		transport.transportConnectionFailed.notify()
		self.world.runQueued()
		self.assertEqual(calls, ["disconnect"])
		self.assertEqual(self.said, [remoteAccess.UNREACHABLE.format(server="nvdaremote.com")])


class NvdasOwnCodeTests(unittest.TestCase):
	"""The fixtures are NVDA 2026.2's files, word for word, when NVDA_SOURCE is set to a folder with its source."""

	def test_theFixturesAreNvdasFiles(self):
		source = os.environ.get("NVDA_SOURCE")
		if not source or not os.path.isdir(os.path.join(source, "source", "_remoteClient")):
			raise unittest.SkipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
		for name in ("connectionInfo.py", "protocol.py"):
			with open(os.path.join(source, "source", "_remoteClient", name), encoding="utf-8") as own, open(os.path.join(FIXTURES, name), encoding="utf-8") as fixture:
				self.assertEqual(fixture.read().replace("\r\n", "\n"), own.read().replace("\r\n", "\n"), name)

	def test_theLinkNvdaMakesIsTheLinkTheModuleReads(self):
		world = World()
		info = world.connectionInfo.ConnectionInfo("nvdaremote.com", world.connectionInfo.ConnectionMode.FOLLOWER, "abc234")
		link = info.getURLToConnect()
		self.assertEqual(link, "nvdaremote://nvdaremote.com?key=abc234&mode=master", "NVDA leaves its own port out")
		self.assertEqual(world.connectionInfo.ConnectionInfo("nvdaremote.com", "slave", "abc234", port=1234).getURLToConnect(), "nvdaremote://nvdaremote.com:1234?key=abc234&mode=master")
		self.assertEqual(remoteAccess.findLink(f"Link: {link}."), link)
		self.assertEqual(remoteAccess.LINK_PREFIX, world.protocol.URL_PREFIX)
		self.assertEqual(remoteAccess.DEFAULT_PORT, world.protocol.SERVER_PORT)
		self.assertEqual(remoteAccess.hostAndPort("example.com:1234"), world.protocol.addressToHostPort("example.com:1234"))
		self.assertEqual(remoteAccess.hostAndPort("example.com"), world.protocol.addressToHostPort("example.com"))


class WiringTests(unittest.TestCase):
	def commands(self):
		return {entry[1]: entry for entry in jawsMigrator.LAYER_COMMANDS}

	def test_theLayerHasTheThreeKeys(self):
		commands = self.commands()
		self.assertEqual(commands["startOrEndRemoteSession"][0], ("kb:t",))
		self.assertEqual(commands["joinRemoteSession"][0], ("kb:shift+t",))
		self.assertEqual(commands["copyRemoteLink"][0], ("kb:control+t",))
		self.assertEqual([commands[name][2] for name in ("startOrEndRemoteSession", "joinRemoteSession", "copyRemoteLink")], ["T", "Shift+T", "Control+T"])
		for name in ("startOrEndRemoteSession", "joinRemoteSession", "copyRemoteLink"):
			self.assertTrue(callable(getattr(jawsMigrator.GlobalPlugin, f"script_{name}", None)), name)
			self.assertIn(f"{commands[name][2]}, ", " ".join(jawsMigrator.LAYER_HELP_LINES))

	def test_theHelpSaysWhatTIsFor(self):
		words = self.commands()["startOrEndRemoteSession"][3]
		self.assertIn("Insert+Alt+T", words)
		self.assertIn("link", words)
		self.assertIn("clipboard", words)

	def test_theCommandsCallTheModule(self):
		plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		with mock.patch.object(remoteAccess, "startOrEnd") as startOrEnd, mock.patch.object(remoteAccess, "join") as join, mock.patch.object(remoteAccess, "copyLink") as copyLink:
			plugin.script_startOrEndRemoteSession(None)
			plugin.script_joinRemoteSession(None)
			plugin.script_copyRemoteLink(None)
		startOrEnd.assert_called_once_with(state.load())
		join.assert_called_once_with()
		copyLink.assert_called_once_with()

	def test_aFailureInTheModuleIsNotRaisedIntoNvda(self):
		plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		with mock.patch.object(remoteAccess, "startOrEnd", side_effect=RuntimeError), mock.patch.object(remoteAccess, "join", side_effect=RuntimeError), mock.patch.object(remoteAccess, "copyLink", side_effect=RuntimeError):
			plugin.startOrEndRemoteSession()
			plugin.joinRemoteSession()
			plugin.copyRemoteLink()

	def test_thePluginsEndStopsTheWatch(self):
		with open(jawsMigrator.__file__, encoding="utf-8") as stream:
			text = stream.read()
		terminate = text[text.index("\tdef terminate(self):"):]
		terminate = terminate[: terminate.index("\n\tdef ")]
		self.assertIn("remoteAccess.stop()", terminate)

	def test_jawsInsertAltTGoesToTheAssistantsCommand(self):
		target = jawsKeyMap.SCRIPT_MAP["startorendtandemsession"]
		self.assertEqual(target[:3], (jawsKeyMap.ASSISTANT_MODULE, jawsKeyMap.ASSISTANT_CLASS, "startOrEndRemoteSession"))
		# The other Tandem key, Toggle Tandem Mode, stays NVDA's own.
		self.assertEqual(jawsKeyMap.SCRIPT_MAP["toggletandemmode"][:3], ("globalCommands", "GlobalCommands", "sendKeys"))
		self.assertTrue(callable(getattr(jawsMigrator.GlobalPlugin, f"script_{target[2]}")))

	def test_jawsTandemKeysAreTheOnesTheModuleTellsOf(self):
		jkm = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Freedom Scientific", "JAWS", "2026", "Scripts", "enu", "Default.JKM")
		if not os.path.isfile(jkm):
			raise unittest.SkipTest("JAWS 2026 isn't installed here")
		with open(jkm, encoding="utf-8", errors="replace") as stream:
			text = stream.read()
		section = text[text.index("[Tandem keys]"):].split("\n\n", 1)[0]
		self.assertIn("Alt+Insert+T=StartOrEndTandemSession", section)
		self.assertIn("Alt+JAWSKey+T=StartOrEndTandemSession", section)


class LayerKeysTests(unittest.TestCase):
	"""The tester's keys, pressed as NVDA dispatches them: NVDA+Shift+J, then Shift+T ("nothing happens. It just beeps at me"),
	and NVDA+Shift+J, then Control+T. NVDA 2026.2's own baseObject.ScriptableObject bindGesture, clearGestureBindings,
	bindGestures and getScript, word for word, hold the plugin's bindings; the plugin's own getScript and layer run as they are."""

	class Key:
		"""A key as NVDA's keyboard handler gives it to getScript: its identifiers, the laptop layout's first."""

		def __init__(self, main):
			self.normalizedIdentifiers = [f"kb(laptop):{main}".lower(), f"kb:{main}".lower()]

	def setUp(self):
		normalize = lambda identifier: identifier.lower()  # noqa: E731

		def bindGesture(self, gestureIdentifier, scriptName):
			scriptAttrName = "script_%s" % scriptName
			func = getattr(self.__class__, scriptAttrName, None)
			if not func:
				raise LookupError(f"No such script on class {self.__class__.__name__}. Couldn't find attribute: {scriptAttrName}")
			self._gestureMap[normalize(gestureIdentifier)] = func

		def clearGestureBindings(self):
			self._gestureMap.clear()

		def bindGestures(self, gestureMap):
			for gestureIdentifier, scriptName in gestureMap.items():
				if scriptName:
					try:
						self.bindGesture(gestureIdentifier, scriptName)
					except LookupError:
						pass

		def getScript(self, gesture):
			for identifier in gesture.normalizedIdentifiers:
				try:
					return self._gestureMap[identifier].__get__(self, self.__class__)
				except KeyError:
					continue
			else:
				return None

		# The plugin's own base class: every test file installs its stubs again, with a new one.
		base = jawsMigrator.GlobalPlugin.__bases__[0]
		for name, function in (("bindGesture", bindGesture), ("clearGestureBindings", clearGestureBindings), ("bindGestures", bindGestures), ("getScript", getScript)):
			patcher = mock.patch.object(base, name, function, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)
		plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		plugin._gestureMap = {}
		plugin._secure = False
		plugin._layerActive = False
		plugin._insertKeys = {}
		plugin._GlobalPlugin__gestures = {"kb:NVDA+shift+j": "commandLayer"}
		plugin.bindGestures(plugin._GlobalPlugin__gestures)
		self.plugin = plugin
		beep = mock.patch.object(jawsMigrator.tones, "beep")
		self.beep = beep.start()
		self.addCleanup(beep.stop)
		sound = mock.patch.object(jawsMigrator.GlobalPlugin, "_playLayerSound", return_value=True)
		sound.start()
		self.addCleanup(sound.stop)

	def press(self, main):
		"""Dispatch a key: the script NVDA finds for it, run, or None where NVDA finds none."""
		script = self.plugin.getScript(self.Key(main))
		if script is not None:
			script(None)
		return script

	def startLayer(self):
		self.assertIsNotNone(self.press("NVDA+shift+j"), "NVDA+Shift+J starts the layer")
		self.assertTrue(self.plugin._layerActive)

	def test_aKeyTheLayerHasNoCommandForBeepsAsTheTestersDid(self):
		# 1.45's layer had no Shift+T, Control+T or Alt+J: the tester's log has tones.beep at pitch 220 for 60 ms for each.
		remote = ("startOrEndRemoteSession", "joinRemoteSession", "copyRemoteLink")
		layerOf145 = {gesture: script for gesture, script in jawsMigrator.LAYER_GESTURES.items() if script not in remote}
		for key in ("shift+t", "control+t", "alt+j"):
			self.beep.reset_mock()
			with mock.patch.object(jawsMigrator, "LAYER_GESTURES", layerOf145):
				self.startLayer()
				script = self.press(key)
			self.assertEqual(script.__name__, "script_layerUnknown", key)
			self.beep.assert_called_once_with(220, 60)
			self.assertFalse(self.plugin._layerActive, "and the layer is left")

	def test_aKeyWithNoCommandStillBeepsNow(self):
		self.startLayer()
		self.press("alt+j")
		self.beep.assert_called_once_with(220, 60)

	def test_tShiftTAndControlTReachTheirCommands(self):
		for key, name in (("t", "startOrEnd"), ("shift+t", "join"), ("control+t", "copyLink")):
			self.beep.reset_mock()
			self.startLayer()
			with mock.patch.object(remoteAccess, name) as command:
				script = self.press(key)
			self.assertIsNotNone(script, key)
			command.assert_called_once()
			self.beep.assert_not_called()
			self.assertFalse(self.plugin._layerActive, f"{key} leaves the layer, as every layer command does")

	def test_theKeysDoNothingOutsideTheLayer(self):
		self.assertIsNone(self.press("t"))
		self.assertIsNone(self.press("shift+t"))
		self.assertIsNone(self.press("control+t"))


class SettingsPanelTests(unittest.TestCase):
	def test_thePanelHasTheServerField(self):
		path = os.path.join(os.path.dirname(jawsMigrator.__file__), "gui", "settingsPanel.py")
		with open(path, encoding="utf-8") as stream:
			text = stream.read()
		self.assertIn("self.remoteServer = helper.addLabeledControl(", text)
		self.assertIn("remoteAccess.STATE_KEY", text)
		self.assertIn("self._shownRemoteServer", text)


if __name__ == "__main__":
	unittest.main()
