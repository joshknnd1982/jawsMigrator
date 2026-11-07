"""Issue 51 (1.60): X to a topping of pizzahut.com's pizza builder, then Space, on the stand-in page (pages/pizzahut.html).

The tester: "When I press x to check the box the check boxes don't get checked." NVDA's browse mode shows each topping as one line, the
outer check box's label, and Space clicks that outer div, which does nothing; the real check box is inside it, and NVDA's document doesn't
have it. His NVDA has automatic focus mode for focus changes and for caret movement off (issue 50), as the config here should.

    set JM_RIG_PAGE=file:///C:/Users/joshk/jawsMigrator/tests/live_nvda/pages/pizzahut.html
    python -u -m scenarios.s62 [letters]

A: the assistant's fix turned off (NVDA alone): X, X to Pepperoni, Space. Pepperoni stays unchecked, the page saw a click on the outer div.
B: his steps with 1.60: X to Garlic-Parm, X to Pepperoni, Space (checked, "checked" said), Space again (unchecked, "not checked").
C: X three times to Bacon, Enter (Enter activates as Space does).
D: Garlic-Parm Hut Blend, the check box the page made focusable: Space works as NVDA has it, through the div itself.
E: what NVDA's document has around Pepperoni (its lines), before and after it is checked.
F: Tab, five times, after Pepperoni is checked: what the page focuses and what NVDA says (its placement and Extra are inside the outer check box).
G: B with the events a real desktop gives NVDA (this one gives none): Chrome focuses the check box it activates, so NVDA gets a focus event for
   the check box inside; Space again, with the focus on it already, gives NVDA a state change for it. What NVDA says, once each.
H: Pepperoni added (with G's focus event), then the focus moved to its Extra switch, as Tab would (browse mode's cursor stays on the
   topping), and Space: Extra is switched on, the topping stays on.
"""
import json
import sys
import time

from rig2 import Scenario

s = Scenario()
which = sys.argv[1].lower() if len(sys.argv) > 1 else "abcdefgh"
PLUGIN = "globalPlugins.jawsMigrator.innerControls"


def speech():
	return [line.split("Speaking ", 1)[1][:200] for line in s.newLog("Speaking \\[", limit=500)]


def page():
	return s.cdp.js("""(() => ({
	  checked: Object.fromEntries([...document.querySelectorAll('[role=checkbox][aria-label]')].map(d => [d.getAttribute('aria-label').split(' checkbox')[0], d.getAttribute('aria-checked')])),
	  log: window.__log.map(e => e.what + ' ' + (e.name || '') + ' ' + (e.on === undefined ? (e.target || '') : e.on)),
	}))()""")


def fresh():
	"""The page again, the focus on its document in NVDA (as coming into the page does), the caret at the top."""
	s.cdp.send("Page.navigate", url=s.cdp.js("location.href"))
	time.sleep(3)
	s.driver("syncFocus")
	time.sleep(2.5)
	s.press("control+home", wait=0.8, show=False)
	s.newLog()


def key(name, wait=1.0):
	s.newLog()
	s.press(name, wait=wait, show=False)
	time.sleep(1.2)
	said = speech()
	print(f"   {name}: said {said}")
	return said


def lines():
	out = s.driver("lines", before=1, after=3)
	return json.dumps(out)[:900]


def setFix(on):
	code = f"import {PLUGIN} as m\n" + ("m.register()" if on else "m.unregister()") + "\nresult = m.isRegistered()"
	print("   fix on:", s.driver("eval", code=code)["result"])


if "a" in which:
	print("== A: NVDA alone (the fix turned off)")
	setFix(False)
	fresh()
	key("x")
	key("x")
	key("space")
	print("   page:", page())
	setFix(True)

if "b" in which:
	print("== B: his steps with 1.60")
	fresh()
	key("x")
	key("x")
	key("space")
	print("   page:", page())
	s.show("jawsMigrator.*innerControls|jawsMigrator: .*check box", 330)
	key("space")
	print("   page:", page())

if "c" in which:
	print("== C: Enter on Bacon")
	fresh()
	for _ in range(3):
		key("x")
	key("enter")
	print("   page:", page())

if "d" in which:
	print("== D: Garlic-Parm, the check box the page made focusable")
	fresh()
	key("x")
	key("space")
	print("   page:", page())

if "e" in which:
	print("== E: NVDA's document at Pepperoni")
	fresh()
	key("x")
	key("x")
	print("   lines:", lines())
	key("space")
	time.sleep(1)
	print("   lines after Space:", lines())
	print("   focus:", s.nvda())

if "f" in which:
	print("== F: Tab after Pepperoni is checked (its placement and Extra are inside the outer check box)")
	fresh()
	key("x")
	key("x")
	key("space")
	for _ in range(5):
		info = s.press("tab", wait=1.0, show=False)
		time.sleep(0.8)
		active = s.cdp.js("(() => { const a = document.activeElement; return a.getAttribute('aria-label') || a.textContent.trim().slice(0, 40) || a.tagName })()")
		print(f"   tab: toPage={info.get('forwardedToPage')} page focus={active!r} said {speech()}")
	print("   nvda:", s.nvda())

EVENT = """
import eventHandler
import {plugin} as m
doc = api.getFocusObject().treeInterceptor
wrapper = doc.currentNVDAObject
inner = m.innerControl(wrapper)
focus = api.getFocusObject()
# NVDA gives an event for the focus to its focus object (IAccessibleHandler), not to a new object for it.
eventHandler.queueEvent("{event}", focus if inner == focus else inner)
result = describe(inner)
"""


def event(name):
	r = s.driver("eval", code=EVENT.format(plugin=PLUGIN, event=name))["result"]
	print(f"   queued {name} for:", (r or {}).get("role"), (r or {}).get("states"))


def spaceWith(name):
	"""Space, and the event Chrome sends for it on a real desktop, as soon as the page has the change."""
	s.newLog()
	s.driver("gesture", name="space")
	time.sleep(0.05)
	event(name)
	time.sleep(2.5)
	print("   said:", speech())
	print("   page:", page())


if "g" in which:
	print("== G: with a real desktop's events")
	fresh()
	key("x")
	key("x")
	print("-- Space: Chrome focuses the check box inside")
	spaceWith("gainFocus")
	print("   focus:", s.nvda())
	print("-- Space again: the focus is on it, so Chrome sends a state change")
	spaceWith("stateChange")
	print("-- X to Bacon and Space: the focus moves from Pepperoni's check box to Bacon's")
	key("x")
	spaceWith("gainFocus")


if "h" in which:
	print("== H: Space on the Extra switch, Tabbed to")
	fresh()
	key("x")
	key("x")
	spaceWith("gainFocus")
	code = """
import eventHandler
doc = api.getFocusObject().treeInterceptor
wrapper = doc.currentNVDAObject
found = []
def walk(o, depth=0):
	for c in o.children:
		if c.name and c.name.startswith("Extra"):
			found.append(c)
		if depth < 8:
			walk(c, depth + 1)
walk(wrapper)
eventHandler.queueEvent("gainFocus", found[0])
result = describe(found[0])
"""
	r = s.driver("eval", code=code)["result"]
	print("   focus moved to:", r.get("role"), r.get("name"), r.get("states"))
	time.sleep(1.5)
	print("   said:", speech())
	print("   nvda:", s.nvda())
	spaceWith("stateChange")
