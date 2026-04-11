# Benchmark Image Sources

The five JPEG images in this directory are used by the opt-in vision
benchmark (`tests/nfa/test_vision_benchmark.py`). They were sourced
from Wikimedia Commons because their licences allow redistribution in
a source repository without a separate asset store.

| File | Wikimedia title | Licence |
|---|---|---|
| `01_sunset.jpg` | [Cómpeta Complete Panorama View Golden Hour 02 2014](https://commons.wikimedia.org/wiki/File:C%C3%B3mpeta_Complete_Panorama_View_Golden_Hour_02_2014.jpg) | CC BY-SA / PD — see Commons page |
| `02_macro.jpg` | [Bee-Purple-Flower-Macro ForestWander](https://commons.wikimedia.org/wiki/File:Bee-Purple-Flower-Macro_ForestWander.jpg) | CC BY-SA 3.0 US (ForestWander) |
| `03_night_city.jpg` | [Lower Manhattan from Jersey City September 2020 panorama](https://commons.wikimedia.org/wiki/File:Lower_Manhattan_from_Jersey_City_September_2020_panorama.jpg) | CC BY-SA / PD — see Commons page |
| `04_portrait_bw.jpg` | [Elderly man in Rhodes, Greece (black and white)](https://commons.wikimedia.org/wiki/File:Elderly_man_in_Rhodes,_Greece_(black_and_white).jpg) | CC BY-SA / PD — see Commons page |
| `05_forest_autumn.jpg` | [Autumn Forest Path with Tall Trees](https://commons.wikimedia.org/wiki/File:Autumn_Forest_Path_with_Tall_Trees.jpg) | CC BY-SA / PD — see Commons page |

All images are thumbnails (max ~1280 px long edge) downloaded via the
Wikimedia Commons API with an identifying User-Agent. They were picked
for category coverage: a golden-hour landscape, a macro close-up, a
night skyline, a black-and-white portrait, and an autumn forest scene
— together they exercise most entries in the Ollama prompt whitelists
(Lichtsituation, Perspektive, Technik, Tageszeit, Jahreszeit).

If you remove an image here, also remove its reference from
`test_vision_benchmark.py` (the test parametrises over whatever `*.jpg`
files are found in this directory, so deleting is sufficient).
