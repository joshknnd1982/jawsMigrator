"""Control+Z after a choice, repeated (issue 47, 1.57): choose a row, take the choice back, go into the suggestions again at once or after a
pause, choose another row. Counts the rounds in which the page, the speech and the page's events were all as they should be.

    python -u -m scenarios.s56 [rounds]
"""
import random
import sys
import time

from rig2 import ADDRESS, Scenario

rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 8
random.seed(157)
s = Scenario()


def speech(pattern="Speaking \\["):
    return [line.split("Speaking ", 1)[1] for line in s.newLog(pattern, limit=600)]


def options():
    return s.cdp.js("[...document.querySelectorAll('#address-dropdown [role=option]')].map(o => o.textContent)")


def events(start):
    return [(e["what"], e.get("value") or e.get("count") or "") for e in s.cdp.js("window.__log")[start:]]


ok = 0
problems = []
for number in range(1, rounds + 1):
    s.fresh()
    names = options()
    first = random.randint(2, 12)
    again = random.randint(1, 8)
    immediately = number % 2 == 1
    notes = []
    for _ in range(first):
        s.press("downArrow", wait=0.3, show=False)
    s.press("enter", wait=1.0, show=False)
    spoken = speech()
    if s.page()["value"] != names[first - 1] or not any("selected" in line for line in spoken):
        notes.append(f"choice of {first}: page {s.page()['value']!r}, said {spoken[-2:]}")
    mark = len(s.cdp.js("window.__log"))
    s.press("control+z", wait=0.2 if immediately else 1.2, show=False)
    spoken = speech()
    if f"Choice undone, {ADDRESS}" not in " ".join(spoken):
        notes.append(f"undo said {spoken}")
    if not immediately:
        shown = s.page()
        if shown["value"] != ADDRESS or shown["options"] != 20 or shown["dropdown"] != "block":
            notes.append(f"after the undo: {shown}")
    started = time.time()
    s.press("downArrow", wait=0.3, show=False)
    spoken = speech()
    wanted = f"Address suggestions, list, {names[0]}, 1 of 20"
    if wanted not in " ".join(spoken):
        notes.append(f"first Down Arrow after the undo said {spoken}")
    for _ in range(again - 1):
        s.press("downArrow", wait=0.3, show=False)
    s.press("enter", wait=1.0, show=False)
    spoken = speech()
    value = s.page()["value"]
    if value != names[again - 1] or not any("selected" in line for line in spoken):
        notes.append(f"second choice of {again}: page {value!r}, said {spoken[-2:]}")
    page_events = [e for e in events(mark) if e[0] in ("input", "select")]
    if page_events[:1] != [("input", ADDRESS)]:
        notes.append(f"events {page_events}")
    kind = "Down Arrow at once" if immediately else "Down Arrow after a pause"
    if notes:
        problems.append((number, kind, notes))
        print(f"round {number} ({kind}, rows {first} then {again}): PROBLEM {notes}")
    else:
        ok += 1
        print(f"round {number} ({kind}, rows {first} then {again}): ok")
print(f"{ok} of {rounds} rounds as they should be")
