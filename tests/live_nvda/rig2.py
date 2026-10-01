"""Scenario helpers on top of rig.py: set the page up the way a tester's keys do, and replay what NVDA presses."""
import time

from rig import PAGE, Cdp, Rig, VK

ADDRESS = "241 w pine st"


class Scenario(Rig):
	def __init__(self):
		super().__init__()
		self.cdp = Cdp()
		self.cdp.send("Page.enable")
		self.cdp.send("Emulation.setFocusEmulationEnabled", enabled=True)

	def dpr(self):
		return float(self.cdp.js("window.devicePixelRatio"))

	def docOrigin(self):
		doc = self.driver("eval", code="""
import api
doc = api.getFocusObject().treeInterceptor
result = list(doc.rootNVDAObject.location)
""")["result"]
		return doc[0], doc[1]

	def fresh(self, typed=ADDRESS, mode="focus"):
		"""Load the page again, focus the address field in NVDA as E and Enter do, type the address."""
		self.cdp.send("Page.navigate", url=PAGE)
		time.sleep(9 if "visible.com" in PAGE else 3)
		self.cdp.js("document.querySelector('#address-input').focus(); 1")
		time.sleep(0.5)
		self.driver("syncFocus", find="Enter your home address")
		time.sleep(3)
		if typed:
			self.cdp.type(typed)
			for _ in range(60):
				time.sleep(0.5)
				if self.page()["dropdown"] == "block":
					break
			time.sleep(1.5)
		self.newLog()

	def where(self):
		"""The page's origin on the screen and its scale, asked before a key so that a press can be replayed at once (None if NVDA can't say)."""
		try:
			return self.docOrigin(), self.dpr()
		except Exception:
			return None

	def mouseToPage(self, sent, where=None):
		"""Replay a recorded mouse press on the page, at the place NVDA's pointer was."""
		cursor = None
		pressed = False
		for item in sent:
			if item["kind"] == "mouse" and not pressed:
				pressed = True
				cursor = tuple(item["cursor"])
		if not pressed or not cursor:
			return None
		(ox, oy), d = where or (self.docOrigin(), self.dpr())
		x, y = (cursor[0] - ox) / d, (cursor[1] - oy) / d
		self.cdp.mouseClick(x, y)
		return {"screen": cursor, "client": (round(x, 1), round(y, 1))}

	def press(self, name, wait=1.5, show=True):
		where = self.where()
		self.newLog()
		info = self.driver("gesture", name=name)
		# A press NVDA makes with the mouse reaches the page at once, so it is replayed as soon as it is recorded (the page can change
		# in the 1.5 seconds a key is given); what a key sends is read after the wait, as before.
		deadline = time.time() + wait
		while True:
			sent = self.driver("sent")["sent"]
			if any(item["kind"] == "mouse" for item in sent) or time.time() >= deadline:
				break
			time.sleep(0.05)
		forwarded = []
		for item in sent:
			if item["kind"] == "key" and not (item["flags"] & 2):
				key = VK.get(item["vk"])
				if key:
					forwarded.append(key)
		# Control and Z sent together (a key NVDA passes on with gesture.send()).
		pressedKeys = [item["vk"] for item in sent if item["kind"] == "key" and not (item["flags"] & 2)]
		if 0x5A in pressedKeys and any(vk in pressedKeys for vk in (0x11, 0xA2, 0xA3)):
			forwarded.append("control+z")
		if info.get("passedThrough"):
			forwarded = [name]
		for key in forwarded:
			self.cdp.key(key)
		clicked = self.mouseToPage(sent, where)
		info["forwardedToPage"] = forwarded
		info["mouse"] = clicked
		if forwarded or clicked:
			time.sleep(wait)
		if show:
			print(f"## {name}: script={info.get('script')} handled={info.get('handled')} toPage={forwarded} mouse={clicked}")
			self.show("Speaking \\[|jawsMigrator|DRIVER|ERROR|DEBUGWARNING.*(suggest|jawsMigrator)", 330)
		return info

	def page(self):
		return self.cdp.js("""(() => {
		  const box = document.querySelector('#address-dropdown');
		  return {active: document.activeElement.id || document.activeElement.className, value: document.querySelector('#address-input').value,
		    dropdown: box ? getComputedStyle(box).display : null, options: document.querySelectorAll('#address-dropdown [role=option]').length};
		})()""")

	def nvda(self):
		res = self.driver("focus")
		doc = res.get("doc") or {}
		focus = res.get("focus") or {}
		return {
			"focus": (focus.get("role"), focus.get("name"), focus.get("value")),
			"passThrough": doc.get("passThrough"),
			"caretLine": doc.get("caretLine"),
			"caretObj": (doc.get("caretObj") or {}).get("role") if isinstance(doc.get("caretObj"), dict) else doc.get("caretObj"),
		}
