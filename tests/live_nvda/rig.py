"""Drives the private-desktop NVDA (through its driver plugin) and the Edge on that desktop (through DevTools)."""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
for folder in (os.path.join(HERE, "pylib"), HERE):  # pylib: python -m pip install --target pylib websocket-client
	sys.path.insert(0, folder)
import websocket  # noqa: E402

from joinlog import entries  # noqa: E402

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
}
VK = {0x28: "downArrow", 0x26: "upArrow", 0x25: "leftArrow", 0x27: "rightArrow", 0x0D: "enter", 0x1B: "escape", 0x09: "tab", 0x20: "space", 0x08: "backspace"}


class Cdp:
	def __init__(self, port=9444):
		self.port = port
		self._id = 0
		self.connect()

	def connect(self):
		targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json"))
		pages = [t for t in targets if t["type"] == "page"]
		page = next((t for t in pages if "visible.com" in t["url"]), pages[0])
		self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], max_size=None, timeout=60)

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
		if down:
			params = dict(type="keyDown", key=key, code=code, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
			if text:
				params["text"] = text
			self.send("Input.dispatchKeyEvent", **params)
		if up:
			self.send("Input.dispatchKeyEvent", type="keyUp", key=key, code=code, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)

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
			f'"{EDGE}" --user-data-dir="{os.path.join(HERE, "edgeprofile")}" --remote-debugging-port=9444 '
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
