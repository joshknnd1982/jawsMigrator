"""The field says it controls nothing (as it once did here, after a retype): the list next to it is found instead."""
import time
from rig2 import Scenario

s = Scenario()
s.fresh()
s.driver("eval", code="""
from globalPlugins.jawsMigrator import suggestionLists
suggestionLists._realControls = suggestionLists._controls
suggestionLists._controls = lambda field: []
result = 'controls patched to say nothing'
""")
print(s.driver("eval", code="""
import api
from globalPlugins.jawsMigrator import suggestionLists
field = api.getFocusObject()
box, options = suggestionLists._suggestionList(field)
result = {'controls': len(suggestionLists._controls(field)), 'found': box.name if box else None, 'options': len(options)}
"""))
s.press("downArrow")
s.press("downArrow")
for i in range(5):
    s.press("downArrow", show=False)
s.press("enter")
print("page after Enter:", s.page())
s.driver("eval", code="""
from globalPlugins.jawsMigrator import suggestionLists
suggestionLists._controls = suggestionLists._realControls
result = 'restored'
""")
