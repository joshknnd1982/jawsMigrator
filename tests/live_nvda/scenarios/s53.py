"""After a choice (issue 47, 1 October): what brings the list back? Editing the text by key, native undo, and setting the field's text
through accessibility (IAccessible's accValue), which is how the add-on could put back what was typed."""
import time

from rig2 import Scenario

s = Scenario()


def chooseEighth():
    s.fresh()
    for key in ["downArrow"] * 8 + ["enter"]:
        s.press(key, wait=0.8, show=False)
    time.sleep(0.5)


def events(start):
    log = s.cdp.js("window.__log")
    return [(e["what"], e.get("value") or e.get("count") or "") for e in log[start:]]


def mark():
    return len(s.cdp.js("window.__log"))


def settle(seconds=1.6):
    time.sleep(seconds)


print("=== A: Backspace once")
chooseEighth()
m = mark()
s.cdp.key("backspace")
settle()
print("page:", s.page(), "events:", events(m))

print("=== B: Control+A and the street typed again")
chooseEighth()
m = mark()
s.cdp.key("control+a")
s.cdp.type("241 w pine st")
settle()
print("page:", s.page(), "events:", events(m))

print("=== C: native undo (Control+Z) after the choice")
chooseEighth()
m = mark()
s.cdp.key("control+z")
settle()
print("page:", s.page(), "events:", events(m))

print("=== D: accValue set to what was typed (on NVDA's main thread)")
chooseEighth()
m = mark()
result = s.driver(
    "eval",
    code="""
field = api.getFocusObject()
try:
    before = field.value
    field.IAccessibleObject.accValue[field.IAccessibleChildID] = "241 w pine st"
    result = {"ok": True, "before": before}
except Exception as e:
    result = {"ok": False, "error": type(e).__name__ + ": " + str(e)}
""",
)
print("driver:", result)
settle(2.0)
print("page:", s.page(), "events:", events(m))
print("nvda focus value:", s.nvda()["focus"])
