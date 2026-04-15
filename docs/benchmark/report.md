# LR-AutoTag Vision Model Benchmark

**Datum:** 2026-04-15
**System:** 12 vCPUs (QEMU Virtual CPU version 2.5+), 21.2 GB RAM, GPU: Tesla P40
**Prompt:** V2 mit Chain-of-Thought (siehe `backend/app/pipeline/ollama_client.py`)
**Timeout:** 1800s pro Request
**Bilder:** 5 Wikimedia-Commons-Testbilder (Sunset, Makro, Nachtstadt, SW-Portrait, Herbstwald)

---

## Timing-Übersicht

| Modell | Params | 01_sunset | 02_macro | 03_night_city | 04_portrait_bw | 05_forest_autumn | Ø |
|---|---|---|---|---|---|---|---|
| `llava-phi3` | 3.8B | 22s | 4s | 6s | 11s | 4s | 9s |
| `gemma3:4b` | 4B | 20s | 4s | 6s | 4s | 4s | 7s |
| `llava:7b` | 7B | 28s | 4s | 4s | 5s | 5s | 9s |
| `bakllava` | 7B | 33s | 2s | 2s | 2s | 2s | 8s |
| `llava-llama3` | 8B | 109s | 82s | 15s | 12s | 83s | 60s |
| `minicpm-v` | 8B | 36s | 4s | 4s | 7s | 4s | 11s |
| `llama3.2-vision` | 11B | 44s | 11s | 14s | 13s | 13s | 19s |
| `llava:13b` | 13B | 40s | 12s | 9s | 9s | 9s | 16s |
| `gemma3:27b` | 27B | 60s | 16s | 16s | 16s | 14s | 24s |
| `gemma4:26b` | 26B | 73s | 49s | 71s | 1030s | 53s | 255s |
| `llava:34b` | 34B | 260s | 23s | 23s | 23s | 21s | 70s |
| `gemma4:31b-it-q4_K_M` | 31B | 172s | 113s | 238s | 111s | 100s | 147s |

---

## Qualitäts-Scoring

Jedes Bild hat bekannte Ground-Truth-Checks (erwartete Keywords, verbotene Halluzinationen, erwartete Perspektive/Technik). Score = Anzahl bestandener Checks / Gesamtzahl Checks.

| Modell | 01_sunset | 02_macro | 03_night_city | 04_portrait_bw | 05_forest_autumn | Gesamt |
|---|---|---|---|---|---|---|
| `llava-phi3` | 3/4 | 1/5 | 4/5 | 0/5 | 3/3 | **11/22** |
| `gemma3:4b` | 2/4 | 1/5 | 4/5 | 4/5 | 3/3 | **14/22** |
| `llava:7b` | 2/4 | 2/5 | 2/5 | 3/5 | 3/3 | **12/22** |
| `bakllava` | 1/4 | 1/5 | 1/5 | 1/5 | 0/3 | **4/22** |
| `llava-llama3` | 1/4 | 1/5 | 1/5 | 0/5 | 0/3 | **3/22** |
| `minicpm-v` | 1/4 | 4/5 | 2/5 | 5/5 | 2/3 | **14/22** |
| `llama3.2-vision` | 3/4 | 3/5 | 2/5 | 4/5 | 3/3 | **15/22** |
| `llava:13b` | 2/4 | 4/5 | 3/5 | 5/5 | 3/3 | **17/22** |
| `gemma3:27b` | 1/4 | 4/5 | 3/5 | 5/5 | 3/3 | **16/22** |
| `gemma4:26b` | 1/4 | 4/5 | 5/5 | 1/5 | 3/3 | **14/22** |
| `llava:34b` | 1/4 | 4/5 | 1/5 | 2/5 | 2/3 | **10/22** |
| `gemma4:31b-it-q4_K_M` | 1/4 | 4/5 | 4/5 | 5/5 | 3/3 | **17/22** |

---

## Keywords pro Bild (Detailansicht)

### 01_sunset.jpg
_Panorama of Spanish town Cómpeta at golden-hour sunset_

**llava-phi3** (22s, 14 kws, score 3/4):
  Wohnhaus, Baum, Gebäude, Dorf, Hügel, Tal, Berge, Morgen, Frühling, Sonnig, Friedlich, Gegenlicht, Normalperspektive, Makro

**gemma3:4b** (20s, 8 kws, score 2/4):
  Horizont, Meer, Sonnenuntergang, Nachmittag, Sonnig, Friedlich, Weiches Licht, Normalperspektive

**llava:7b** (28s, 11 kws, score 2/4):
  Stadt, Haus, Stadt, Stadt, Morgen, Sommer, Sonnig, Friedlich, Hartes Licht, Normalperspektive, Bewegungsunschaerfe

**bakllava** (33s, 2 kws, score 1/4):
  100% original, no manipulation

**llava-llama3** (109s, 5 kws, score 1/4):
  Stadt, Berge, Hillside, Mountainside, Cityscape

**minicpm-v** (36s, 5 kws, score 1/4):
  Stadt, Berg, Haus, Garten, Sommer

**llama3.2-vision** (44s, 19 kws, score 3/4):
  Haeuser, Baeume, Weg, Stadt, Landschaft, Berg, Wald, Morgen, Abend, Sommer, Herbst, Sonnig, Bewoelt, Friedlich, Romantisch, Gegenlicht, Weiches Licht, Draufsicht, Natuerliches Licht

**llava:13b** (40s, 13 kws, score 2/4):
  Häuser, Berg, Dorf, Berge, Natur, Gebirge, Mittag, Früling, Sonnig, Friedlich, Hartes Licht, Normalperspektive, Bokeh

**gemma3:27b** (60s, 16 kws, score 1/4):
  Dorf, Haeuser, Berge, Landschaft, Vegetation, Suedlaendische Szene, Bergdorf, Huegel, Nachmittag, Fruehling, Sonnig, Friedlich, Majestaetisch, Natuerliches Licht, Weiches Licht, Vogelperspektive

**gemma4:26b** (73s, 17 kws, score 1/4):
  Dorf, Berge, Häuser, Vegetation, Terrassen, Bergdorf, Landschaft, Hügel, Gebirge, Nachmittag, Sommer, Sonnig, Friedlich, Majestaetisch, Seitenlicht, Natuerliches Licht, Vogelperspektive

**llava:34b** (260s, 11 kws, score 1/4):
  Morgen, Sonnig, Freiheit, Stadt, Haus, Gebirge, Trees, Dorffluge, Natur, Landschaft, Friedlich

**gemma4:31b-it-q4_K_M** (172s, 18 kws, score 1/4):
  Dorf, Häuser, Berge, Hügel, Vegetation, Landschaft, Siedlung, Natur, Gebirge, Nachmittag, Frühling, Sonnig, Friedlich, Majestätisch, Seitenlicht, Natuerliches Licht, Hartes Licht, Aufsicht

### 02_macro.jpg
_Macro shot of a bee on a purple flower (ForestWander, CC BY-SA)_

**llava-phi3** (4s, 13 kws, score 1/5):
  Hase, Blume, Melancholisch, Natur, Vormittag, Frühling, Bewoelkt, 0.45, 1, 2, 3, 1, 1

**gemma3:4b** (4s, 8 kws, score 1/5):
  Friedlich, Natur, Blumen, Nachmittag, Frühling, Sonnenlicht, Weiches Licht, Normalperspektive

**llava:7b** (4s, 9 kws, score 2/5):
  Biene, Blumen, Blumen, Morgen, Sommer, Sonnig, Friedlich, Hartes Licht, Normalperspektive

**bakllava** (2s, 4 kws, score 1/5):
  0.24, 0.78, 0.36, 0.9

**llava-llama3** (82s, 5 kws, score 1/5):
  Blume, Blaat, Flower, Flowers, Flowerpot

**minicpm-v** (4s, 5 kws, score 4/5):
  Bienen, Blumen, Makro, Sommer, Sonnig

**llama3.2-vision** (11s, 11 kws, score 3/5):
  Bee, Flower, Nature, Green, Day, Summer, Sunny, Friedlich, Diffuses Licht, Normalperspektive, Makro

**llava:13b** (12s, 17 kws, score 4/5):
  Blume, Bienen, Natur, Gärten, Freiland, Garten, Mittag, Vormittag, Frühling, Sonnig, Bedeckt, Friedlich, Hartes Licht, Normalperspektive, Normalperspektive, Makro, Bokeh

**gemma3:27b** (16s, 17 kws, score 4/5):
  Biene, Blume, Insekt, Pflanze, Nektar, Sommer, Sonnig, Friedlich, Vertraeumt, Natuerliches Licht, Weiches Licht, Makro, Bokeh, Vogelperspektive, Vormittag, Lila, Bluehen

**gemma4:26b** (49s, 12 kws, score 4/5):
  Biene, Blüte, Natur, Wiese, Sommer, Friedlich, Lebhaft, Weiches Licht, Natürliches Licht, Schrägsicht, Makro, Bokeh

**llava:34b** (23s, 12 kws, score 4/5):
  Bienenkopf, Blume, Natur, Garten, Feld, Morgen, Frühling, Sonnig, Friedlich, Weiches Licht, Normalperspektive, Makro

**gemma4:31b-it-q4_K_M** (113s, 19 kws, score 4/5):
  Biene, Blume, Blüte, Insekt, Pflanze, Natur, Bestäubung, Garten, Wiese, Mittag, Sommer, Sonnig, Friedlich, Lebhaft, Natürliches Licht, Weiches Licht, Schrägsicht, Makro, Bokeh

### 03_night_city.jpg
_Manhattan skyline from Jersey City at night, reflections on Hudson_

**llava-phi3** (6s, 29 kws, score 4/5):
  Objekte, Burj Khalifa, Empire State Building, One World Trade Center, Chrysler Building, MetLife Building, Szene, Nacht, Melancholisch, Umgebung, Hafen, Wasser, Tageszeit, Abend, Daemmerung, Jahreszeit, Sommer, Wetter, Bewoelkt, Stimmung, Melancholisch, Lichtsituation, Gegenlicht, Hartes Licht, Perspektive, Normalperspektive, Technik, Makro, Langzeitbelichtung

**gemma3:4b** (6s, 24 kws, score 4/5):
  Dunkelheit, Meer, Nacht, Abend, Stille, Melancholisch, Einsam, Weitläufig, Horizont, Lichtstrahlen, Natürliches Licht, Dämmerung, Ruhe, Kühle, Silhouetten, Tiefe, Wasser, Reflexion, Atmosphärisch, Nebel, Distant, Fern, Normalperspektive, Langzeitbelichtung

**llava:7b** (4s, 9 kws, score 2/5):
  Stadt, Nacht, See, Morgengrauen, Herbst, Bedeckt, Dramatisch, Hartes Licht, Normalperspektive

**bakllava** (2s, 1 kws, score 1/5):
  12/15/16

**llava-llama3** (15s, 30 kws, score 1/5):
  {
"Objekte": [
"Skyscraper, Cityscape, Skyline, Buildings"
], Szenen": [
"Nighttime, Morn, Dusk, Noon, Evening, Morning, Midday, Afternoon, Night, Dawn, Dusk, Daybreak, Sunrise, Sunset, Winter, Spring, Summer, Autumn, Winter"
], Umgebungen": [
"City, River, Ocean, Mountains, Trees, Grass, Rocks

**minicpm-v** (4s, 5 kws, score 2/5):
  Stadtlandschaft, Nachtlicht, Hochhäuser, Memorial, Dämmerung

**llama3.2-vision** (14s, 20 kws, score 2/5):
  Skyline, Stadt, Wolkenkratzer, Stadt, Stadtlandschaft, Stadt, Stadtlandschaft, Abend, Dämmerung, Herbst, Winter, Bewölkung, Nebel, Dramatisch, Melancholisch, Gegenlicht, Hartes Licht, Vogelperspektive, Schwarz-Weiss, Langzeitbelichtung

**llava:13b** (9s, 16 kws, score 3/5):
  Stadt, Hochhaus, Turm, Nacht, Abend, Dunkelheit, Wasser, Horizont, Nacht, Herbst, Bedeckt, Melancholisch, Hartes Licht, Oberlicht, Normalperspektive, Schwarzweiss

**gemma3:27b** (16s, 17 kws, score 3/5):
  Wolkenkratzer, Stadtbild, New York, Hudson River, Lichtstrahlen, Stadt, Wasser, Abend, Herbst, Bedeckt, Dramatisch, Majestaetisch, Kunstlicht, Natuerliches Licht, Frontlicht, Untersicht, Langzeitbelichtung

**gemma4:26b** (71s, 16 kws, score 5/5):
  Wolkenkratzer, Skyline, Wasser, Lichtstrahl, Stadtlandschaft, Nachtaufnahme, Stadt, Fluss, Nacht, Dramatisch, Majestaetisch, Lichtstrahlen, Kunstlicht, Hell-Dunkel, Normalperspektive, Langzeitbelichtung

**llava:34b** (23s, 28 kws, score 1/5):
  New York City, Skyline, Cityscape, Skyscrapers, Buildings, Nighttime, Dusk, Lights, Reflection, Water, River, Harbor, Hudson River, East River, Manhattan, City Lights, Skyline at Night, Urban Landscape, Metropolitan Area, Downtown, Financial District, Central Park, Empire State Building, One World Trade Center, Brooklyn Bridge, Statue of Liberty, City at Dusk, City at Night

**gemma4:31b-it-q4_K_M** (238s, 19 kws, score 4/5):
  Wolkenkratzer, Skyline, Wasser, One World Trade Center, Lichtstrahl, Stadtpanorama, Stadtbild, Stadt, Hafen, Daemmerung, Herbst, Sonnig, Majestaetisch, Friedlich, Kunstlicht, Natuerliches Licht, Lichtstrahlen, Normalperspektive, Langzeitbelichtung

### 04_portrait_bw.jpg
_B&W portrait of elderly man in Rhodes, Greece_

**llava-phi3** (11s, 30 kws, score 0/5):
  Buch, Telefon, Walze, CDs, Radio, Kino, Laden, Restaurant, Café, Büro, Straße, Garten, Zimmer, Halle, Keller, Morgen, Vormittag, Nachmittag, Abend, Nacht, Frühling, Sommer, Herbst, Winter, Bewölkt, Regen, Nebel, Sturm, Dunst, Melancholisch

**gemma3:4b** (4s, 10 kws, score 4/5):
  Schwarzweiss, Melancholisch, Einsam, Dunkelheit, Nebel, Langzeitbelichtung, Normalperspektive, Weiches Licht, Tageslicht, Stimmungsvoll

**llava:7b** (5s, 11 kws, score 3/5):
  Mann, Kaffeehaus, Gesellschaft, Kaffeeshop, Vormittag, Herbst, Bedeckt, Friedlich, Hartes Licht, Normalperspektive, Schwarzweiß

**bakllava** (2s, 0 kws, score 1/5):
  

**llava-llama3** (12s, 30 kws, score 0/5):
  Boxen, Stuhl, Morgengrauen, Vormittag, Mittag, Nacht, Winter, Fruehling, Sommer, Herbst, Morgengrauen, Vormittag, Mittag, Nacht, Winter, Fruehling, Sommer, Herbst, Sonnig, Bewoelcht, Bedeckt, Regen, Schnee, Nebl, Gewitter, Wind, Sturm, Dunst, Dramatisch, Melancholisch

**minicpm-v** (7s, 14 kws, score 5/5):
  Mann, Zeitzeiger, Sitzplatz, Straßencafé, Stadtpark, Vormittag, Herbst, Winter, Bedeckt, Melancholisch, Nostalgisch, Weiches Licht, Normalperspektive, Schwarzweiss

**llama3.2-vision** (13s, 15 kws, score 4/5):
  Menschen, Sitzbank, Hintergrund, Menschen, Sitzbank, Hintergrund, Morgen, Sommer, Sonnig, Melancholisch, Einsam, Hartes Licht, Weiches Licht, Normalperspektive, Schwarzweiss

**llava:13b** (9s, 13 kws, score 5/5):
  Mann, Stuhl, Raum, Gespräch, Laden, Strasse, Abend, Herbst, Bedeckt, Melancholisch, Hartes Licht, Normalperspektive, Schwarzweiss

**gemma3:27b** (16s, 16 kws, score 5/5):
  Mann, Aelterer Herr, Denker, Armlehne, Uhr, Café, Strassenszene, Nachmittag, Sommer, Bewoelkt, Melancholisch, Nostalgisch, Seitenlicht, Weiches Licht, Normalperspektive, Schwarzweiss

**gemma4:26b** (1030s, 0 kws, score 1/5):
  

**llava:34b** (23s, 11 kws, score 2/5):
  Mensch, Restaurant, Stuhl, Tisch, Nachmittag, Herbst, Sonnig, Friedlich, Weiches Licht, Normalperspektive, Natürliches Licht

**gemma4:31b-it-q4_K_M** (111s, 19 kws, score 5/5):
  Mann, Uhr, Hemd, Stuhl, Schild, Porträt, Alltag, Außenbereich, Café, Nachmittag, Sommer, Sonnig, Melancholisch, Nostalgisch, Seitenlicht, Natuerliches Licht, Normalperspektive, Schwarzweiss, Bokeh

### 05_forest_autumn.jpg
_Autumn forest path with tall deciduous trees_

**llava-phi3** (4s, 12 kws, score 3/3):
  Baum, Baum, Baum, Wald, Grasland, Morgen, Herbst, Sonnig, Melancholisch, Gegenlicht, Normalperspektive, Schwarzweiss

**gemma3:4b** (4s, 10 kws, score 3/3):
  Herbst, Wald, Lichtung, Dämmerung, Friedlich, Melancholisch, Nebel, Weiches Licht, Natürliches Licht, Normalperspektive

**llava:7b** (5s, 11 kws, score 3/3):
  Baum, Wald, Morgengrauen, Wald, Morgengrauen, Herbst, Bedeckt, Friedlich, Hartes Licht, Normalperspektive, Langzeitbelichtung

**bakllava** (2s, 1 kws, score 0/3):
  1. The sky is white and cloudy.

**llava-llama3** (83s, 30 kws, score 0/3):
  {
"Objekte": [
"Auflaeder, Blaeser, Dreher, Erdmesser, Gabeln, Hobelzusammensteller, Knicklöffel, Knickmesswerkzeuge, Knickständer, Knickzusammensteller, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer, Knickzusammensetzer

**minicpm-v** (4s, 5 kws, score 2/3):
  Wald, Pfad, Bäume, Herbst, Sonnenuntergang

**llama3.2-vision** (13s, 15 kws, score 3/3):
  Bäume, Weg, Morgen, Natur, Wald, Nacht, Morgen, Herbst, Sonnig, Friedlich, Majestätisch, Gegenlicht, Weiches Licht, Normalperspektive, Naturlicht

**llava:13b** (9s, 13 kws, score 3/3):
  Baum, Straße, Wald, Park, Natur, Landeinheit, Morgengrauen, Herbst, Bedeckt, Einsam, Hartes Licht, Draufsicht, Normalperspektive

**gemma3:27b** (14s, 14 kws, score 3/3):
  Wald, Baum, Gras, Pfad, Busch, Herbst, Dunst, Abend, Friedlich, Melancholisch, Natuerliches Licht, Diffuses Licht, Normalperspektive, Seitenlicht

**gemma4:26b** (53s, 18 kws, score 3/3):
  Bäume, Birken, Kiefern, Pfad, Gras, Waldlandschaft, Natur, Wald, Wiese, Morgen, Herbst, Sonnig, Dunst, Friedlich, Vertraemt, Seitenlicht, Natuerliches Licht, Normalperspektive

**llava:34b** (21s, 11 kws, score 2/3):
  Bäume, Pflanzen, Natur, Wald, Feld, Morgen, Herbst, Melancholisch, Gegenlicht, Froschperspektive, Bokeh

**gemma4:31b-it-q4_K_M** (100s, 16 kws, score 3/3):
  Wald, Bäume, Weg, Gras, Birken, Natur, Landschaft, Waldrand, Nachmittag, Herbst, Sonnig, Friedlich, Nostalgisch, Seitenlicht, Natuerliches Licht, Normalperspektive

---

## Methodik

- Jedes Modell wird sequenziell getestet (model-outer, image-inner), damit das Modell einmal geladen wird und warm bleibt.
- Temperature = 0.1 für reproduzierbare Ergebnisse.
- Der Prompt ist identisch für alle Modelle (V2 mit Chain-of-Thought).
- Scoring basiert auf manuell definierten Ground-Truth-Checks pro Bild (expected keywords, forbidden hallucinations, expected perspective/technique).
- Alle Rohdaten (inkl. vollständige Ollama-Timings) liegen als JSON in `results/`.

---

## Fazit

_TODO: manuell ergänzen nach Sichtung der Ergebnisse._