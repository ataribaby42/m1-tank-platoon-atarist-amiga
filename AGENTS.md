# Pravidla práce v projektu

Emulátor spouštěj a testuj na pozadí tak, aby uživatele nerušil na ploše. Používej samostatnou skrytou instanci, nepřepínej okna do popředí a nepřebírej vstup z klávesnice ani myši. Nezasahuj do uživatelovy již spuštěné instance emulátoru. Pokud ověření vyžaduje viditelné okno nebo zásah uživatele, nejdříve vysvětli potřebu a domluv se s uživatelem.

Do adresáře output ukládej pouze výsledné obrazy disků: ADF pro Amigu a ST pro Atari ST. Samostatné změněné herní soubory, kontrolní zprávy a testovací náhledy ponechávej v analysis. Editovatelné PNG včetně atlasů a palety patří do gfx v kořeni projektu.

Udržované build skripty a assemblerové patche jsou v src. Vždy sestavuj pouze kompletní sadu všech fixů a změn příkazem `python src/build_all.py`; jediný finální výstup je `output/M1TankPlatoon_modded.adf`. Samostatnou variantu DarkGreen už nevytvářej. Starší příkazy `python src/build_dark_green.py` a `python src/build_zoom_f3.py` jsou kompatibilní vstupy do stejného kompletního sestavení. Samostatný převod PNG a atlasů provádí `python src/build_assets.py`. Mezivýsledky jsou v analysis/build. Neobnovuj staré předávací skripty v analysis ani ruční postup; návod a závislosti jsou v src/CTI_ME.txt a src/requirements.txt. Build nesmí přepisovat vstupní PNG.

Výše uvedený výchozí build je pro Amigu. Atari ST sestavuj příkazem `python src/build_all.py --platform st` nebo `python src/build_st.py`; výsledkem je pouze `output/M1TankPlatoon_modded.st`. Vstup je původní `assets/M1 Tank Platoon.st`, grafika je společná v gfx a mezivýsledky patří do analysis/build/st. Samostatný převod ST grafiky provádí `python src/build_st_assets.py`. Příkaz `python src/build_all.py --platform all` sestaví obě platformy. ST build nesmí měnit hotový ADF a naopak.

Windows wrapper `build.bat` v kořeni bez parametrů spouští úplné sestavení obou platforem. Parametry `--platform amiga` a `--platform st` předává přímo do src/build_all.py. Adresáře output a release jsou zahrnuté do Gitu; analysis, .tools a původní vstupní diskety v assets jsou ignorované.
