"""Join each NVDA log header line with its body into one line, optionally filter with a regex, print."""
import re
import sys

HEADER = re.compile(r"^(IO|DEBUGWARNING|DEBUG|INFO|WARNING|ERROR|CRITICAL|IO) - (.*?) \((\d\d:\d\d:\d\d\.\d+)\) - (.*?) \((\d+)\):\s*$")


def entries(path):
	current = None
	with open(path, encoding="utf-8", errors="replace") as handle:
		for raw in handle:
			line = raw.rstrip("\r\n")
			match = HEADER.match(line)
			if match:
				if current:
					yield current
				current = {"level": match.group(1), "where": match.group(2), "time": match.group(3), "thread": match.group(4), "body": []}
			elif current is not None:
				current["body"].append(line)
	if current:
		yield current


def main():
	path = sys.argv[1]
	pattern = re.compile(sys.argv[2], re.I) if len(sys.argv) > 2 else None
	limit = int(sys.argv[3]) if len(sys.argv) > 3 else 400
	for entry in entries(path):
		body = " | ".join(entry["body"])
		line = f"{entry['time']} {entry['level']} {entry['where']}: {body}"
		if pattern is None or pattern.search(line):
			print(line[:limit])


if __name__ == "__main__":
	main()
