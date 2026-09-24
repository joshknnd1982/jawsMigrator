# Every module the add-on imports must exist in the NVDA it runs in. NVDA ships its own copy of Python
# with only part of the standard library, in library.zip, so a module these tests import without trouble
# can be missing there: version 1.5 imported filecmp, and NVDA didn't load the add-on at all.
# The modules are read from the NVDA installed on this computer; without one, the test is skipped.
# Run: python -m unittest tests.test_nvda_runtime -v

import ast
import os
import sys
import unittest
import zipfile

ADDON = os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins")
#: Where NVDA is installed; the NVDA_DIR environment variable can point elsewhere.
NVDA_FOLDERS = [os.environ.get("NVDA_DIR", ""), os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "NVDA")]
#: Modules built into NVDA's Python itself (python313.dll), which have no file of their own.
BUILT_IN = set(sys.builtin_module_names) | {"_sha2", "_tokenize", "_typing"}


def nvdaFolder():
	for folder in NVDA_FOLDERS:
		if folder and os.path.isfile(os.path.join(folder, "library.zip")):
			return folder
	return None


def nvdaModules(folder):
	"""The top-level modules and packages NVDA's Python can import."""
	names = set(BUILT_IN)
	with zipfile.ZipFile(os.path.join(folder, "library.zip")) as library:
		for entry in library.namelist():
			first = entry.split("/", 1)[0]
			names.add(first[: -len(".pyc")] if first.endswith(".pyc") else first)
	for entry in os.listdir(folder):
		path = os.path.join(folder, entry)
		if os.path.isdir(path):
			names.add(entry)
		elif entry.lower().endswith(".pyd"):
			# Extension modules: _ctypes.pyd, and wx._core.pyd for a module inside a package.
			names.add(entry.split(".", 1)[0])
	return names


def addonImports():
	"""``{module: [(file, line)]}`` for every module the add-on imports by name, not its own modules."""
	found = {}
	for folder, dirs, files in os.walk(ADDON):
		dirs[:] = [name for name in dirs if name != "__pycache__"]
		for name in files:
			if not name.endswith(".py"):
				continue
			path = os.path.join(folder, name)
			with open(path, encoding="utf-8") as stream:
				tree = ast.parse(stream.read(), path)
			for node in ast.walk(tree):
				if isinstance(node, ast.Import):
					modules = [alias.name for alias in node.names]
				elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
					modules = [node.module]
				else:
					continue
				for module in modules:
					found.setdefault(module.split(".")[0], []).append((os.path.relpath(path, ADDON), node.lineno))
	return found


class NvdaRuntimeTests(unittest.TestCase):
	def test_every_import_exists_in_nvda(self):
		folder = nvdaFolder()
		if folder is None:
			self.skipTest("NVDA is not installed on this computer")
		available = nvdaModules(folder)
		imports = addonImports()
		self.assertIn("os", imports, "the add-on's imports were read")
		self.assertIn("shutil", available, "NVDA's modules were read")
		missing = {module: places for module, places in imports.items() if module not in available and module != "__future__"}
		self.assertEqual(missing, {}, f"not in NVDA's Python ({folder}): {missing}")


if __name__ == "__main__":
	unittest.main()
