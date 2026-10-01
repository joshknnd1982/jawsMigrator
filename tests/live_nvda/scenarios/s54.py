"""Control+Z after a choice (issue 47, 1.56): the text typed before is put back and the page shows its suggestions again.

A: choose the eighth, Control+Z, Down Arrow at once (the page brings its suggestions back a moment later), Down Arrow, Enter.
B: choose the eighth, type a letter, Control+Z: the key is the page's own.
C: Control+Z with nothing chosen: the page's own.
D: choose the eighth, Up Arrow and Down Arrow (NVDA's own automatic focus mode takes it out of the field), Control+Z.
E: choose the eighth, Control+Z twice: the second is the page's own.
"""
import time

from rig2 import Scenario

s = Scenario()


def chooseEighth():
    s.fresh()
    for key in ["downArrow"] * 8 + ["enter"]:
        s.press(key, wait=0.8, show=False)
    time.sleep(0.5)
    s.newLog()


def mark():
    return len(s.cdp.js("window.__log"))


def events(start):
    return [(e["what"], e.get("value") or e.get("count") or "") for e in s.cdp.js("window.__log")[start:]]


print("=== A: choose the eighth, Control+Z, Down Arrow at once, Down Arrow, Enter")
chooseEighth()
m = mark()
print("   page before:", s.page())
s.press("control+z", wait=0.3)
print("   page after Control+Z:", s.page())
s.press("downArrow", wait=0.8)
s.press("downArrow", wait=0.8)
s.press("enter", wait=1.0)
print("   page at the end:", s.page(), "events:", events(m))

print("=== B: choose the eighth, type a letter, Control+Z")
chooseEighth()
s.cdp.type("x")
time.sleep(0.8)
m = mark()
print("   page before:", s.page())
s.press("control+z", wait=0.8)
print("   page after:", s.page(), "events:", events(m))

print("=== C: Control+Z with nothing chosen")
s.fresh()
m = mark()
s.press("control+z", wait=0.8)
print("   page after:", s.page(), "events:", events(m))

print("=== D: choose the eighth, Up Arrow, Down Arrow, Control+Z")
chooseEighth()
for key in ("upArrow", "downArrow"):
    s.press(key, wait=0.8, show=False)
print("   nvda:", s.nvda())
m = mark()
s.press("control+z", wait=0.8)
print("   page after:", s.page(), "events:", events(m))
print("   nvda:", s.nvda())

print("=== E: choose the eighth, Control+Z twice")
chooseEighth()
s.press("control+z", wait=1.5)
m = mark()
s.press("control+z", wait=0.8)
print("   page after the second:", s.page(), "events since:", events(m))
