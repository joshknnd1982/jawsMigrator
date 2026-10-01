"""Down Arrow and Enter in quick succession, before the first key's script has finished."""
import time
from rig2 import Scenario

s = Scenario()
s.fresh()
s.newLog()
a = s.driver("gesture", name="downArrow")
b = s.driver("gesture", name="enter")
print("down:", a.get("handled"), "enter:", b.get("handled"))
time.sleep(2.5)
sent = s.driver("sent")["sent"]
print("sent to the page:", [x for x in sent if x["kind"] == "key"], "mouse:", [x for x in sent if x["kind"] == "mouse"])
s.mouseToPage(sent)
time.sleep(1)
print("page:", s.page())
s.show("Speaking|suggestionLists", 250)
