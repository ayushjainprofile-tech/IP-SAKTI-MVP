import urllib.request
import re

url = "https://raw.githubusercontent.com/Anshika-Jain446/ip-shakti-final/main/ip-sakti-mvp/backend/main.py"
req = urllib.request.urlopen(url)
text = req.read().decode('utf-8')

with open("ref_main.py", "w") as f:
    f.write(text)

with open("ref_grep.txt", "w") as f:
    for i, line in enumerate(text.split("\n")):
        if "evaluate_confidence" in line or "domain_scores" in line:
            f.write(f"{i+1}: {line}\n")
