# Tests for version 1.48, from issue 45, "Make NVDA remote easier to use?". The tester pressed NVDA+Shift+J, then Shift+T and
# Control+T, and "nothing happens. It just beeps at me.": the log shows the layer's beep for a key it has no command for. The
# commands were built for 1.42 but never released (another change took the number), so 1.43 to 1.45 had no T, Shift+T or
# Control+T. 1.48 has them, and these tests are the check the first build lacked: test_v148_remoteAccess runs the assistant
# against an imitation of NVDA's RemoteClient, and this file runs it against NVDA 2026.2's real network code.
#
# NVDA 2026.2's own source/_remoteClient/transport.py (RelayTransport, ConnectorThread), serializer.py, connectionInfo.py and
# protocol.py, and source/extensionPoints, run here from tests/nvda2026_2, with a small shim for Python 3.10 (NVDA runs
# Python 3.13). What stands in for the rest of NVDA: logHandler, wx (CallAfter is run by the test), config, the clipboard,
# and the relay server, a small TLS server on this computer (NVDA's own needs the cryptography package) with a certificate
# made here by openssl; the fingerprint of the certificate is trusted in config as NVDA's own certificate question trusts it,
# as the tester's NVDA trusts nvdaremote.com. The RemoteClient is the methods of source/_remoteClient/client.py that connect
# and disconnect, over the real transport.
# - A server no one answers: T says it once and the attempt ends, and NVDA's own five-second retries stop (UnreachableTests).
# - T connects through a server, the link it puts on the clipboard is one Shift+T joins with, and the server sees the two
#   computers join the same channel, one as controlled and one as controlling (SessionTests).
# - A connection that drops after it was made is not said to be unreachable, and T pressed again closes the connection.
# Run: python -m unittest tests.test_v148_remoteTransport -v

import hashlib
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import remoteAccess  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "nvda2026_2")
#: How long the tests wait for NVDA's own threads.
WAIT = 12


def _shimmed(source):
	if sys.version_info < (3, 11):
		source = source.replace(
			"from enum import StrEnum",
			"from enum import Enum\n\n\nclass StrEnum(str, Enum):\n\tdef __str__(self):\n\t\treturn str(self.value)\n",
		)
		# typing.Self is Python 3.11's, and only in annotations.
		source = source.replace("from typing import Self", "Self = object")
		source = source.replace(", Self,", ",")
		if "Self" in source and "Self = object" not in source:
			source = "Self = object\n" + source
	return source


def _load(name, path, package=None, asPackage=False):
	"""NVDA 2026.2's own source file ``path`` as module ``name``."""
	with open(path, encoding="utf-8") as stream:
		source = _shimmed(stream.read())
	module = types.ModuleType(name)
	module.__file__ = path
	if asPackage:
		module.__path__ = [os.path.dirname(path)]
		module.__package__ = name
	else:
		module.__package__ = name.rpartition(".")[0]
	sys.modules[name] = module
	if package is not None:
		setattr(package, name.rpartition(".")[2], module)
	exec(compile(source, path, "exec"), module.__dict__)
	return module


class _Log:
	def __getattr__(self, name):
		return lambda *args, **kwargs: None


def _openssl():
	found = shutil.which("openssl")
	if found:
		return found
	for candidate in (r"C:\Program Files\Git\usr\bin\openssl.exe", r"C:\Program Files\Git\mingw64\bin\openssl.exe"):
		if os.path.exists(candidate):
			return candidate
	return None


def _freePort():
	with socket.socket() as probe:
		probe.bind(("127.0.0.1", 0))
		return probe.getsockname()[1]


class Relay:
	"""A relay server on this computer: TLS with a certificate of its own, and the messages each client sends, one JSON line
	each, as NVDA's serializer makes them."""

	def __init__(self, certFile, keyFile):
		self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
		self.context.load_cert_chain(certFile, keyFile)
		with open(certFile, encoding="ascii") as stream:
			der = ssl.PEM_cert_to_DER_cert(stream.read())
		self.fingerprint = hashlib.sha256(der).hexdigest().lower()
		self.listener = socket.socket()
		self.listener.bind(("127.0.0.1", 0))
		self.listener.listen(8)
		self.port = self.listener.getsockname()[1]
		self.lock = threading.Lock()
		self.messages = []
		self.clients = []
		self.closedClients = 0
		threading.Thread(target=self._accept, daemon=True).start()

	def _accept(self):
		while True:
			try:
				raw, _address = self.listener.accept()
			except OSError:
				return
			threading.Thread(target=self._serve, args=(raw,), daemon=True).start()

	def _serve(self, raw):
		try:
			connection = self.context.wrap_socket(raw, server_side=True)
		except (ssl.SSLError, OSError):
			raw.close()
			return
		with self.lock:
			self.clients.append(connection)
		buffer = b""
		try:
			while True:
				data = connection.recv(4096)
				if not data:
					break
				buffer += data
				while b"\n" in buffer:
					line, _sep, buffer = buffer.partition(b"\n")
					with self.lock:
						self.messages.append(json.loads(line))
		except (OSError, ValueError):
			pass
		finally:
			with self.lock:
				self.closedClients += 1
			try:
				connection.close()
			except OSError:
				pass

	def joins(self):
		with self.lock:
			return [m for m in self.messages if m.get("type") == "join"]

	def dropClients(self):
		with self.lock:
			clients = list(self.clients)
		for connection in clients:
			try:
				connection.shutdown(socket.SHUT_RDWR)
			except OSError:
				pass
			try:
				connection.close()
			except OSError:
				pass

	def close(self):
		self.listener.close()
		self.dropClients()


class Client:
	"""NVDA 2026.2's RemoteClient (source/_remoteClient/client.py), the methods that connect and disconnect, over the real
	RelayTransport: connect, connectAsFollower and connectAsLeader, disconnect, isConnected, isConnecting, verifyAndConnect with
	the user's yes, and doDisconnect with no confirmation dialog."""

	def __init__(self, package):
		self.package = package
		self.transport = package.transport
		self.serializer = package.serializer
		self.connectionInfo = package.connectionInfo
		self.followerTransport = self.leaderTransport = None
		self.followerSession = self.leaderSession = None
		self._connecting = False
		self.disconnects = []

	def _session(self, transport, info):
		return types.SimpleNamespace(transport=transport, close=transport.close, getConnectionInfo=lambda: info)

	def connect(self, info):
		self._connecting = True
		transport = self.transport.RelayTransport.create(connectionInfo=info, serializer=self.serializer.JSONSerializer())
		if info.mode == self.connectionInfo.ConnectionMode.LEADER:
			self.leaderSession, self.leaderTransport = self._session(transport, info), transport
		else:
			self.followerSession, self.followerTransport = self._session(transport, info), transport
		transport.reconnectorThread.start()

	def verifyAndConnect(self, info):
		# The question "Do you wish to control the computer on server ... with key ...?", answered yes.
		self.connect(info)

	def doDisconnect(self):
		self.disconnect()

	def disconnect(self, *, _silent=False):
		self.disconnects.append(_silent)
		self._connecting = False
		if self.leaderSession is not None:
			self.leaderSession.close()
			self.leaderSession = self.leaderTransport = None
		if self.followerSession is not None:
			self.followerSession.close()
			self.followerSession = self.followerTransport = None

	@property
	def _transport(self):
		return self.followerTransport or self.leaderTransport

	def isConnected(self):
		return self._transport.connected if self._transport is not None else False

	@property
	def isConnecting(self):
		return self._connecting or (
			not self.isConnected() and self._transport is not None and self._transport.reconnectorThread.running
		)


class RealCase(unittest.TestCase):
	def setUp(self):
		if sys.platform != "win32":
			self.skipTest("NVDA's transport uses Windows socket options")
		self.said = []
		self.after = []
		self.clipboard = ""
		self.trusted = {}
		self.conf = {"remote": {"enabled": True, "trustedCertificates": self.trusted}}

		modules = {}
		logHandler = types.ModuleType("logHandler")
		logHandler.log = _Log()
		modules["logHandler"] = logHandler
		nvdaState = types.ModuleType("NVDAState")
		nvdaState._allowDeprecatedAPI = lambda: True
		modules["NVDAState"] = nvdaState
		speech = types.ModuleType("speech")
		commands = types.ModuleType("speech.commands")
		for name in ("SynthCommand", "EndUtteranceCommand", "BreakCommand", "CharacterModeCommand", "LangChangeCommand"):
			setattr(commands, name, type(name, (), {}))
		speech.commands = commands
		modules["speech"], modules["speech.commands"] = speech, commands
		ui = types.ModuleType("ui")
		ui.message = self.said.append
		ui.delayedMessage = self.said.append
		api = types.ModuleType("api")
		api.copyToClip = self._copyToClip
		api.getClipData = lambda: self.clipboard
		config = types.ModuleType("config")
		config.conf = self.conf
		globalVars = types.ModuleType("globalVars")
		globalVars.appArgs = types.SimpleNamespace(secure=False)
		modules.update({"ui": ui, "api": api, "config": config, "globalVars": globalVars})

		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)

		_load("extensionPoints.util", os.path.join(FIXTURES, "extensionPoints", "util.py"))
		extensionPoints = _load(
			"extensionPoints", os.path.join(FIXTURES, "extensionPoints", "__init__.py"), asPackage=True,
		)
		sys.modules["extensionPoints"].util = sys.modules["extensionPoints.util"]
		self.extensionPoints = extensionPoints
		rc = os.path.join(FIXTURES, "_remoteClient")
		package = types.ModuleType("_remoteClient")
		package.__path__ = [rc]
		package._remoteClient = None
		package.initialize = lambda: None
		sys.modules["_remoteClient"] = package
		configuration = types.ModuleType("_remoteClient.configuration")
		configuration.getRemoteConfig = lambda: self.conf["remote"]
		configuration._isDebugForRemoteClient = lambda: False
		sys.modules["_remoteClient.configuration"] = configuration
		package.configuration = configuration
		for name in ("protocol", "connectionInfo", "serializer", "transport"):
			_load(f"_remoteClient.{name}", os.path.join(rc, name + ".py"), package)
		self.package = package

		import wx

		later = mock.patch.object(wx, "CallAfter", side_effect=lambda function, *args, **kwargs: self.after.append((function, args, kwargs)))
		later.start()
		self.addCleanup(later.stop)
		self.clients = []
		self.addCleanup(self._endClients)
		self.addCleanup(remoteAccess.stop)
		self.client = self.newClient()
		package._remoteClient = self.client

	def newClient(self):
		client = Client(self.package)
		self.clients.append(client)
		return client

	def _endClients(self):
		for client in self.clients:
			client.disconnect(_silent=True)

	def _copyToClip(self, text):
		self.clipboard = text
		return True

	def pump(self, until, timeout=WAIT):
		"""Run what NVDA's threads handed to wx.CallAfter, until ``until()`` or the time is up. Returns ``until()``."""
		end = time.monotonic() + timeout
		while True:
			while self.after:
				function, args, kwargs = self.after.pop(0)
				function(*args, **kwargs)
			if until():
				return True
			if time.monotonic() > end:
				return False
			time.sleep(0.02)

	def settle(self, seconds):
		self.pump(lambda: False, seconds)


class UnreachableTests(RealCase):
	def test_aServerNoOneAnswersIsSaidOnceAndNVDAsRetriesStop(self):
		port = _freePort()
		address = f"127.0.0.1:{port}"
		self.assertTrue(remoteAccess.share({remoteAccess.STATE_KEY: address}))
		self.assertEqual(self.said, [remoteAccess.WAITING])
		transport = self.client.followerTransport
		connector = transport.reconnectorThread
		self.assertTrue(remoteAccess.isActive(), "NVDA is trying: the session is being set up")
		self.assertTrue(self.pump(lambda: len(self.said) > 1), "the failure is said")
		self.assertEqual(self.said[1], remoteAccess.UNREACHABLE.format(server=address))
		self.assertIsNone(self.client.followerTransport, "the attempt has ended")
		self.assertFalse(remoteAccess.isActive())
		self.assertEqual(self.client.disconnects, [True], "NVDA's own disconnect, without its 'Disconnected' sound")
		# NVDA's own thread tries again every five seconds, for ever; it has been told to stop.
		connector.join(WAIT)
		self.assertFalse(connector.is_alive(), "NVDA's retries have stopped")
		self.settle(0.5)
		self.assertEqual(len(self.said), 2, "and nothing more is said")


@unittest.skipUnless(_openssl(), "openssl makes the test server's certificate")
class SessionTests(RealCase):
	@classmethod
	def setUpClass(cls):
		cls.directory = tempfile.mkdtemp(prefix="jawsMigratorRelay")
		cls.cert = os.path.join(cls.directory, "cert.pem")
		cls.key = os.path.join(cls.directory, "key.pem")
		subprocess.run(
			[_openssl(), "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", cls.key, "-out", cls.cert,
			 "-days", "2", "-subj", "/CN=localhost"],
			check=True, capture_output=True, timeout=60,
		)

	@classmethod
	def tearDownClass(cls):
		shutil.rmtree(cls.directory, ignore_errors=True)

	def setUp(self):
		super().setUp()
		self.relay = Relay(self.cert, self.key)
		self.addCleanup(self.relay.close)
		self.address = f"127.0.0.1:{self.relay.port}"
		# The certificate is the one NVDA's own question trusted for this server, as for nvdaremote.com on the tester's.
		self.trusted[self.address] = self.relay.fingerprint
		self.state = {remoteAccess.STATE_KEY: self.address}

	def link(self):
		return remoteAccess.findLink(self.clipboard)

	def test_tConnectsThroughTheServerAsTheControlledComputerWithTheKeyInTheLink(self):
		self.assertTrue(remoteAccess.share(self.state))
		self.assertEqual(self.said, [remoteAccess.WAITING])
		self.assertTrue(self.pump(lambda: self.relay.joins()), "the server gets the join message")
		key = self.client.followerTransport.channel
		join = self.relay.joins()[0]
		self.assertEqual((join["channel"], join["connection_type"]), (key, "slave"))
		versions = [m for m in self.relay.messages if m.get("type") == "protocol_version"]
		self.assertEqual(versions[0]["version"], 2)
		link = self.link()
		self.assertIn("key=" + key, link)
		self.assertIn("mode=master", link, "the other computer controls")
		self.assertTrue(self.client.isConnected())
		self.assertTrue(remoteAccess.isActive())
		self.assertEqual(self.client.followerTransport.successfulConnects, 1)
		self.settle(0.3)
		self.assertIsNone(remoteAccess._watched, "the first connection ends the watch for one that can't be reached")
		self.assertEqual(self.said, [remoteAccess.WAITING])

	def test_theLinkTMadeIsTheOneShiftTJoinsWith(self):
		remoteAccess.share(self.state)
		self.assertTrue(self.pump(lambda: self.relay.joins()))
		link = self.link()
		mine = self.client
		# The other computer: its own NVDA, its own clipboard with the link sent to it.
		other = self.newClient()
		self.package._remoteClient = other
		self.clipboard = f"Please use {link} to control my computer."
		self.assertTrue(remoteAccess.join())
		self.assertTrue(self.pump(lambda: len(self.relay.joins()) == 2), "the other computer joins too")
		joins = self.relay.joins()
		self.assertEqual(len({j["channel"] for j in joins}), 1, "both are in the same channel, the key in the link")
		self.assertEqual(joins[0]["channel"], mine.followerTransport.channel)
		self.assertEqual(sorted(j["connection_type"] for j in joins), ["master", "slave"])
		self.assertTrue(self.pump(lambda: other.isConnected()))
		self.assertIsNotNone(other.leaderTransport, "the other computer controls")
		self.assertIsNone(other.followerTransport)

	def test_aConnectionThatDropsAfterItWasMadeIsNotSaidToBeUnreachable(self):
		remoteAccess.share(self.state)
		self.assertTrue(self.pump(lambda: self.client.isConnected()))
		self.settle(0.3)
		self.relay.dropClients()
		self.assertTrue(self.pump(lambda: not self.client.isConnected(), 5), "the drop reaches NVDA's transport")
		self.settle(1)
		self.assertEqual(self.said, [remoteAccess.WAITING], "nothing said: NVDA's own reconnecting is its own")
		self.assertIsNotNone(self.client.followerTransport, "and the session isn't ended for it")

	def test_tPressedAgainClosesTheConnection(self):
		remoteAccess.startOrEnd(self.state)
		self.assertTrue(self.pump(lambda: self.client.isConnected()))
		self.assertTrue(remoteAccess.isActive())
		closedBefore = self.relay.closedClients
		self.assertTrue(remoteAccess.startOrEnd(self.state), "it ends the session instead of starting another")
		self.assertIsNone(self.client.followerTransport)
		self.assertFalse(remoteAccess.isActive())
		self.assertEqual(len(self.relay.joins()), 1, "no second session was started")
		self.assertTrue(self.pump(lambda: self.relay.closedClients > closedBefore, 5), "the server sees the connection close")


if __name__ == "__main__":
	unittest.main()
