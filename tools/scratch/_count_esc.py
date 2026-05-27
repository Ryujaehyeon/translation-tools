import pathlib
count = 0
files = []
root = pathlib.Path(r"c:\Users\yjhg1\Documents\Paradox Interactive\Stellaris\mod\integrated_korean_translation_pack\localisation\korean")
for f in root.rglob("*.yml"):
    if ".bak" in f.name:
        continue
    text = f.read_text(encoding="utf-8-sig")
    needle = chr(92) + "n"
    if needle in text:
        n = text.count(needle)
        files.append((f.name, n))
        count += n
for name, n in sorted(files, key=lambda x: -x[1])[:30]:
    print(f"{n:4d}  {name}")
print(f"total: {count}")
