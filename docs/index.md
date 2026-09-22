```python exec="on"
from pathlib import Path

readme = Path("README.md").read_text(encoding="utf-8")
feedback = readme.replace(
    "https://15r10nk.github.io/matchify/latest/", ""
).splitlines()

admonitions = {
    "NOTE": ("note", None),
    "TIP": ("tip", None),
    "IMPORTANT": ("warning", "Important"),
    "WARNING": ("warning", None),
    "CAUTION": ("danger", "Caution"),
}

i = 0
while i < len(feedback):
    line = feedback[i]
    kind = line.removeprefix("> [!").removesuffix("]")
    if line == f"> [!{kind}]" and kind in admonitions:
        style, title = admonitions[kind]
        title_suffix = f' "{title}"' if title else ""
        print(f"!!! {style}{title_suffix}")
        i += 1
        while i < len(feedback) and (
            feedback[i] == ">" or feedback[i].startswith("> ")
        ):
            print(f"    {feedback[i].removeprefix('> ').removeprefix('>')}")
            i += 1
        continue
    print(line)
    i += 1
```
