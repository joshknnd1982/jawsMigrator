"""Drives the private-desktop NVDA (through its driver plugin) and the Edge on that desktop (through DevTools)."""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
for folder in (os.path.join(HERE, "pylib"), HERE):  # pylib: python -m pip install --target pylib websocket-client (optional)
	sys.path.insert(0, folder)
try:
	import websocket  # noqa: E402
except ImportError:  # nothing is installed: _MiniSocket below is all DevTools needs
	websocket = None

from joinlog import entries  # noqa: E402

#: The DevTools port and the page this rig uses. Two rigs at once (two sessions) need their own desktop name (mkconfig.py) and port, or
#: the second NVDA ends the first: NVDA's single instance is per desktop. JM_RIG_PAGE can be a local page (pages/address.html) so that
#: nothing is typed into a live site.
PORT = int(os.environ.get("JM_RIG_PORT", "9444"))
PAGE = os.environ.get("JM_RIG_PAGE", "https://www.visible.com/shop/home-internet")

CFG = os.path.join(HERE, "cfg")
CMD = os.path.join(CFG, "driver", "cmd.json")
RES = os.path.join(CFG, "driver", "res.json")
LOG = os.path.join(HERE, "nvda.log")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

KEYS = {
	# name: (key, code, vk, text)
	"downArrow": ("ArrowDown", "ArrowDown", 0x28, None),
	"upArrow": ("ArrowUp", "ArrowUp", 0x26, None),
	"leftArrow": ("ArrowLeft", "ArrowLeft", 0x25, None),
	"rightArrow": ("ArrowRight", "ArrowRight", 0x27, None),
	"enter": ("Enter", "Enter", 0x0D, "\r"),
	"escape": ("Escape", "Escape", 0x1B, None),
	"tab": ("Tab", "Tab", 0x09, None),
	"space": (" ", "Space", 0x20, " "),
	"backspace": ("Backspace", "Backspace", 0x08, None),
	"control+a": ("a", "KeyA", 0x41, None),
	"control+z": ("z", "KeyZ", 0x5A, None),
}
#: What the browser does for a key with Control held: DevTools only runs an editing command when it is named.
COMMANDS = {"control+a": ["selectAll"], "control+z": ["undo"]}
VK = {0x28: "downArrow", 0x26: "upArrow", 0x25: "leftArrow", 0x27: "rightArrow", 0x0D: "enter", 0x1B: "escape", 0x09: "tab", 0x20: "space", 0x08: "backspace"}


class _MiniSocket:
	"""Just enough of a WebSocket client for DevTools' text messages, so that nothing has to be installed (websocket-client is used if it is)."""

	def __init__(self, url, timeout=60):
		import base64
		import socket
		from urllib.parse import urlparse

		parts = urlparse(url)
		self.sock = socket.create_connection((parts.hostname, parts.port or 80), timeout=timeout)
		key = base64.b64encode(os.urandom(16)).decode()
		path = parts.path + (("?" + parts.query) if parts.query else "")
		self.sock.sendall(
			(
				f"GET {path} HTTP/1.1\r\nHost: {parts.hostname}:{parts.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
				f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
			).encode()
		)
		response = b""
		while b"\r\n\r\n" not in response:
			chunk = self.sock.recv(4096)
			if not chunk:
				raise ConnectionError("DevTools closed the connection")
			response += chunk
		head, _, self._buffer = response.partition(b"\r\n\r\n")
		if b" 101 " not in head.split(b"\r\n")[0]:
			raise ConnectionError(head.decode("utf-8", "replace"))

	def _frame(self, opcode, data):
		import struct

		header = bytearray([0x80 | opcode])
		size = len(data)
		if size < 126:
			header.append(0x80 | size)
		elif size < 65536:
			header.append(0x80 | 126)
			header += struct.pack(">H", size)
		else:
			header.append(0x80 | 127)
			header += struct.pack(">Q", size)
		mask = os.urandom(4)
		header += mask
		self.sock.sendall(bytes(header) + bytes(byte ^ mask[index % 4] for index, byte in enumerate(data)))

	def send(self, text):
		self._frame(1, text.encode("utf-8"))

	def _read(self, count):
		while len(self._buffer) < count:
			chunk = self.sock.recv(65536)
			if not chunk:
				raise ConnectionError("DevTools closed the connection")
			self._buffer += chunk
		data, self._buffer = self._buffer[:count], self._buffer[count:]
		return data

	def recv(self):
		import struct

		message = b""
		while True:
			first, second = self._read(2)
			opcode, size = first & 0x0F, second & 0x7F
			if size == 126:
				size = struct.unpack(">H", self._read(2))[0]
			elif size == 127:
				size = struct.unpack(">Q", self._read(8))[0]
			payload = self._read(size)  # a server's frames are not masked
			if opcode == 8:
				raise ConnectionError("DevTools closed the connection")
			if opcode == 9:
				self._frame(10, payload)
			elif opcode in (0, 1, 2):
				message += payload
				if first & 0x80:
					return message.decode("utf-8", "replace")

	def close(self):
		try:
			self.sock.close()
		except OSError:
			pass


class Cdp:
	def __init__(self, port=PORT):
		self.port = port
		self._id = 0
		self.connect()

	def connect(self):
		targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json"))
		pages = [t for t in targets if t["type"] == "page"]
		want = PAGE.split("#")[0]
		page = next((t for t in pages if t["url"].split("#")[0] == want), None) or next((t for t in pages if "visible.com" in t["url"]), pages[0])
		url = page["webSocketDebuggerUrl"]
		self.ws = websocket.create_connection(url, max_size=None, timeout=60) if websocket else _MiniSocket(url, timeout=60)

	def send(self, method, **params):
		self._id += 1
		mid = self._id
		self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
		while True:
			message = json.loads(self.ws.recv())
			if message.get("id") == mid:
				if "error" in message:
					raise RuntimeError(f"{method}: {message['error']}")
				return message.get("result", {})

	def js(self, expression):
		result = self.send("Runtime.evaluate", expression=expression, returnByValue=True)
		if "exceptionDetails" in result:
			raise RuntimeError(json.dumps(result["exceptionDetails"])[:500])
		return result["result"].get("value")

	def key(self, name, down=True, up=True):
		if name not in KEYS and len(name) == 1:
			KEYS[name] = (name, "Key" + name.upper(), ord(name.upper()), name)
		key, code, vk, text = KEYS[name]
		held = {"modifiers": 2} if name.startswith("control+") else {}
		if down:
			params = dict(type="rawKeyDown" if held else "keyDown", key=key, code=code, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk, **held)
			if text:
				params["text"] = text
			if name in COMMANDS:
				params["commands"] = COMMANDS[name]
			self.send("Input.dispatchKeyEvent", **params)
		if up:
			self.send("Input.dispatchKeyEvent", type="keyUp", key=key, code=code, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk, **held)

	def type(self, text, delay=0.07):
		for ch in text:
			self.send("Input.dispatchKeyEvent", type="keyDown", key=ch, text=ch, unmodifiedText=ch)
			self.send("Input.dispatchKeyEvent", type="keyUp", key=ch)
			time.sleep(delay)

	def mouseClick(self, x, y):
		self.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
		self.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", buttons=1, clickCount=1)
		self.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", buttons=0, clickCount=1)


class Rig:
	def __init__(self):
		# A result is found by this number in a file's name, so a run must never reuse a number an older run's file has (milliseconds:
		# a run asks for far fewer than a thousand results a second).
		self.n = int(time.time() * 1000)
		self.cdp = None
		self.logPos = os.path.getsize(LOG) if os.path.exists(LOG) else 0

	# -- processes on the private desktop
	def spawn(self, label, cmd):
		path = os.path.join(HERE, f"spawn-{int(time.time() * 1000)}.json")
		with open(path, "w", encoding="utf-8") as stream:
			json.dump({"label": label, "cmd": cmd}, stream)
		time.sleep(2)

	def startEdge(self, url="about:blank"):
		cmd = (
			f'"{EDGE}" --user-data-dir="{os.path.join(HERE, "edgeprofile")}" --remote-debugging-port={PORT} '
			"--remote-allow-origins=* --no-first-run --no-default-browser-check --disable-gpu --force-renderer-accessibility "
			"--window-position=0,0 --window-size=1280,1000 " + url
		)
		self.spawn("edge", cmd)
		for _ in range(40):
			try:
				self.cdp = Cdp()
				return
			except Exception:
				time.sleep(0.5)
		raise RuntimeError("Edge's DevTools never answered")

	# -- the NVDA driver
	def driver(self, op, timeout=20, **kw):
		self.n += 1
		with open(CMD + ".tmp", "w", encoding="utf-8") as stream:
			json.dump(dict(kw, op=op, id=self.n), stream)
		for attempt in range(50):
			try:
				os.replace(CMD + ".tmp", CMD)
				break
			except PermissionError:
				time.sleep(0.05)
		deadline = time.time() + timeout
		path = os.path.join(CFG, "driver", "res-%s.json" % self.n)
		while time.time() < deadline:
			try:
				with open(path, encoding="utf-8") as stream:
					res = json.load(stream)
				return res["result"]
			except Exception:
				pass
			time.sleep(0.1)
		raise TimeoutError(f"driver did not answer {op}")

	# -- the NVDA log
	def newLog(self, pattern=None, limit=260, quiet=True):
		"""Entries written since the last call (optionally filtered), as short lines."""
		out = []
		if not os.path.exists(LOG):
			return out
		size = os.path.getsize(LOG)
		with open(LOG, "rb") as stream:
			stream.seek(self.logPos)
			data = stream.read(size - self.logPos)
		self.logPos = size
		text = data.decode("utf-8", "replace")
		header = re.compile(r"^(IO|DEBUGWARNING|DEBUG|INFO|WARNING|ERROR|CRITICAL) - (.*?) \((\d\d:\d\d:\d\d\.\d+)\) - (.*?) \((\d+)\):\s*$")
		current = None
		items = []
		for line in text.splitlines():
			match = header.match(line)
			if match:
				if current:
					items.append(current)
				current = [match.group(3), match.group(1), match.group(2), []]
			elif current is not None:
				current[3].append(line)
		if current:
			items.append(current)
		rx = re.compile(pattern, re.I) if pattern else None
		noise = re.compile(r"featureFlag|speechDictHandler|braille|hwPortUtils|autoSettings|garbageHandler|synthDriver|_getAvailableAddons|deprecat", re.I)
		for time_, level, where, body in items:
			line = f"{time_} {level} {where}: {' | '.join(body)}"
			if rx and not rx.search(line):
				continue
			if quiet and not rx and noise.search(line):
				continue
			out.append(line[:limit])
		return out

	def show(self, pattern=None, limit=260):
		for line in self.newLog(pattern, limit):
			print("   LOG", line)

	# -- keys: through NVDA's real gesture handling, then what the app would have received goes to Edge
	def press(self, name, wait=1.2, show=True):
		self.newLog()
		info = self.driver("gesture", name=name)
		time.sleep(wait)
		sent = self.driver("sent")["sent"]
		forwarded = []
		for item in sent:
			if item["kind"] == "key" and not (item["flags"] & 2):
				key = VK.get(item["vk"])
				if key:
					forwarded.append(key)
		if info.get("passedThrough"):
			forwarded = [name]
		# What NVDA sent or passed through reaches the page.
		for key in forwarded:
			self.cdp.key(key)
		other = [s for s in sent if s["kind"] in ("mouse", "cursor")]
		info["forwardedToPage"] = forwarded
		info["mouseOrCursor"] = other
		if forwarded:
			time.sleep(wait)
		if show:
			print(f"## {name}: script={info.get('script')} handled={info.get('handled')} forwardedToPage={forwarded} mouse={other}")
			self.show("Speaking \\[|jawsMigrator|DRIVER|gainFocus|ERROR|DEBUGWARNING.*(suggest|jawsMigrator)", 330)
		return info
