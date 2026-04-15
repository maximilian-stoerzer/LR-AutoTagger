# Wie findet man 1 Foto unter 100.000 ohne Keyword? — Wie ich meine Fotobibliothek mit lokaler KI retten will

Ich fotografiere seit über 20 Jahren. Was als Hobby mit einer kleinen Kompaktkamera begann, wurde über die Jahre zur ernsthaften Leidenschaft — Reisen, Landschaften, Street, Makro, Portraits. Irgendwann stand die Zahl im Lightroom-Katalog bei 100.000 Bildern. Ja, ich habe tatsächlich noch alle.

Und ich finde nichts.

Das Foto vom Sonnenuntergang in Island? Irgendwo zwischen 2004 und 2007, vermutlich im Sommer. Die Makroaufnahme der Biene auf der lila Blüte? Keine Ahnung, welcher Ordner. Die nächtliche Skyline-Aufnahme mit Langzeitbelichtung? Liegt sicher irgendwo in „2006-Reise", aber in welchem der 40 Unterordner? Oder war es 2007?

Seien wir ehrlich: Disziplin und ein konsistenter Tagging-Workflow sind die größte Herausforderung für jeden Hobbyfotografen. Lightroom Classic bietet fantastische Suchfunktionen — Stichwortbäume, Smart-Sammlungen, Metadatenfilter. Aber nur, wenn die Bilder auch verschlagwortet sind. Bei 100.000 Bildern macht man das nicht mal eben an einem Wochenende nach.

## Die Idee: KI soll es richten

Die Idee lag auf der Hand: ein Vision-Modell, das jedes Bild analysiert und automatisch mit passenden deutschen Keywords versieht. Objekte, Szenen, Stimmung, Lichtsituation, Perspektive, Technik — alles, wonach man später suchen würde.

Die Idee ist natürlich nicht neu. Übrigens - die Idee hatte ich auch schon als ChatGPT gerade herauskam. Auch damals habe ich ein paar Links zu "Systemen" bekommen. Der Clou - kein einziger der Links war valide - alle waren von ChatGPT erfunden. Nun ja, inzwischen sind ein paar Monate vergangen.

Wie sieht es heute aus? Eine kurze Marktrecherche zeigt: es gibt durchaus kommerzielle Lösungen. Excire Search ist ein ausgereiftes Lightroom-Plugin, das Bilder lokal per KI analysiert und Keywords direkt in den Katalog schreibt — genau das, was ich suche. ON1 Photo Keyword AI macht Ähnliches, allerdings als Standalone-App außerhalb von Lightroom (Keywords werden über XMP-Dateien ausgetauscht). Der Haken: Excire kostet knapp 120 Euro, ON1 rund 80 Euro, und die Keywords sind primär auf Englisch. Für eine deutsche Fotobibliothek mit fotografisch-technischen Suchbegriffen wie „Gegenlicht", „Froschperspektive" oder „Goldene Stunde" ist das nicht ideal.

Aber schließlich gibt es Claude Code. Und die Lust am Experimentieren.

## Ein Wochenendprojekt: LR AutoTagger

Also habe ich mir ein eigenes Lightroom-Plugin gebaut. „LR AutoTagger" — ein FastAPI-Backend in Python, dazu ein Lua-Plugin für Lightroom Classic, das Vorschaubilder an den Server schickt und die zurückgelieferten Keywords direkt in den Katalog schreibt. Dazu Reverse Geocoding per GPS-Daten, Brennweiten-Klassifikation aus den EXIF-Daten und eine Sonnenstand-Berechnung für „Goldene Stunde" und „Blaue Stunde".

Mit Claude Code war der Prototyp tatsächlich an einem Wochenende lauffähig. Die Architektur ist einfach: das Plugin exportiert ein Vorschaubild, der Server analysiert es, die Keywords kommen zurück. Aber eine zentrale Frage blieb offen: welches Modell nimmt man für die Bildanalyse?

## Option 1: Kommerzielle APIs

Die naheliegende Lösung: eines der großen Frontier-Modelle über die API ansprechen. GPT-4o, Claude Sonnet, Gemini — alle können Bilder analysieren und würden die Aufgabe vermutlich souverän lösen. Aber was kostet das bei 100.000 Bildern?

Eine Überschlagsrechnung (Bild auf 1024 px skaliert, ca. 200 Tokens Output pro Bild):

| Modell | Input/Output pro 1M Tokens | Geschätzte Kosten für 100k Bilder |
|---|---|---|
| **GPT-4o** | $2,50 / $10,00 | ca. $350–400 |
| **Claude Sonnet 4.6** | $3,00 / $15,00 | ca. $500–800 |
| **Gemini 2.5 Flash** | $0,15 / $0,60 | ca. $20–30 |
| **Gemini 2.5 Pro** | $1,25 / $10,00 | ca. $200–300 |

*(Hinweis: Grobe Schätzungen. Die tatsächlichen Kosten hängen von der Bildauflösung, der Tokenisierung des jeweiligen Anbieters und der Länge des Prompts ab. Keine Gewähr für die Zahlen.)*

Gemini Flash ist erstaunlich günstig. GPT-4o und Claude Sonnet liegen im mittleren dreistelligen Bereich — machbar, aber für ein Hobbyprojekt nicht gerade ein Schnäppchen.

Doch es gibt ein zweites Problem, das schwerer wiegt als die Kosten: **Will ich wirklich alle meine privaten Fotos an einen Cloud-Dienst schicken?** Familienfotos, Bilder von Freunden, von meinem Zuhause — 20 Jahre meines Lebens, abgebildet in 100.000 Aufnahmen? Eher nicht.

## Option 2: Lokale Modelle mit Ollama

Also Plan B: Open-Source Vision-Modelle, die lokal auf meinem eigenen Server laufen. Kein Cloud-Upload, keine Abo-Kosten, volle Kontrolle. Total souverän! Ollama macht das Deployment denkbar einfach — Modell herunterladen, Prompt schicken, fertig.

Aber welches der verfügbaren Modelle kann das überhaupt? Mein Prompt ist nicht trivial: zehn verschiedene Kategorien, davon mehrere mit kontrollierten Vokabularen (Whitelists), Antwort auf Deutsch, Ausgabe als strukturiertes JSON. Das ist anspruchsvoller als ein simples „Beschreibe dieses Bild".

## Das Experiment: Neun Modelle im Direktvergleich

Ich habe neun lokal ausführbare Vision-Modelle getestet — von 1,4 bis 13 Milliarden Parameter. Alle mit demselben Prompt, denselben fünf Testbildern und einer transparenten Scoring-Methodik.

**Die Testbilder** (alle unter Creative-Commons-Lizenzen von Wikimedia Commons):

| | | |
|---|---|---|
| ![01_sunset](../../backend/tests/nfa/fixtures/benchmark_images/01_sunset.jpg) | ![02_macro](../../backend/tests/nfa/fixtures/benchmark_images/02_macro.jpg) | ![03_night_city](../../backend/tests/nfa/fixtures/benchmark_images/03_night_city.jpg) |
| *Sonnenuntergang, Cómpeta* | *Makro: Biene auf Blüte* | *Manhattan bei Nacht* |
| [Tuxyso](https://commons.wikimedia.org/wiki/File:C%C3%B3mpeta_Complete_Panorama_View_Golden_Hour_02_2014.jpg) / CC BY-SA 3.0 | [ForestWander](https://commons.wikimedia.org/wiki/File:Bee-Purple-Flower-Macro_ForestWander.jpg) / CC BY-SA 3.0 US | [King of Hearts](https://commons.wikimedia.org/wiki/File:Lower_Manhattan_from_Jersey_City_September_2020_panorama.jpg) / CC BY-SA 4.0 |
| ![04_portrait_bw](../../backend/tests/nfa/fixtures/benchmark_images/04_portrait_bw.jpg) | ![05_forest_autumn](../../backend/tests/nfa/fixtures/benchmark_images/05_forest_autumn.jpg) | |
| *SW-Portrait* | *Herbstwald* | |
| [Martin Hricko](https://commons.wikimedia.org/wiki/File:Elderly_man_in_Rhodes,_Greece_(black_and_white).jpg) / CC BY 3.0 | [Vovogov90](https://commons.wikimedia.org/wiki/File:Autumn_Forest_Path_with_Tall_Trees.jpg) / CC0 (Public Domain) | |

Fünf völlig unterschiedliche Motive: Gegenlicht, Makro, Nachtaufnahme, Schwarzweiß-Portrait, Herbstlandschaft. Die Frage war: welches Modell erkennt nicht nur „Hund" und „Strand", sondern auch „Gegenlicht", „Froschperspektive" und „Langzeitbelichtung"?

**Setup:** CPU-only VM mit 12 vCPUs und 14,5 GB RAM — keine GPU, weil meine Nvidia P40 (... the bitter the boy ...) wegen eines Thermo-Problems gerade deaktiviert ist. Kein Luxus-Setup, sondern ein realistischer Worst Case.

**Die Ergebnisse:**

| Modell | Parameter | Ø Zeit/Bild | Score | Sprache |
|---|---|---|---|---|
| **LLaVA 13B** | 13B | **440 s** | **68 %** | Deutsch |
| Llama 3.2 Vision | 11B | 937 s | 68 % | Inkonsistent |
| MiniCPM-V | 8B | 1.300 s | 68 % | Deutsch ~ |
| LLaVA-Phi3 | 3,8B | 279 s | 55 % | Deutsch |
| LLaVA 7B | 7B | 287 s | 55 % | Deutsch |
| Gemma 3 4B | 4B | 372 s | 50 % | Deutsch |
| BakLLaVA | 7B | 247 s | 18 % | Gemischt |
| Moondream | 1,4B | — | — | Timeout |

![Qualität vs. Geschwindigkeit](chart_speed_vs_quality.svg)

**Der klare Gewinner: LLaVA 13B.** Gleiche Qualität wie die beiden nächsten Konkurrenten (Llama 3.2 Vision, MiniCPM-V), aber zwei- bis dreimal schneller. Und — entscheidend für meinen Anwendungsfall — zuverlässig auf Deutsch.

Spannend war auch, was *nicht* funktioniert hat. BakLLaVA, obwohl technisch verwandt mit LLaVA, lieferte Antworten wie „100% original, no manipulation" statt Keywords — offenbar für eine völlig andere Aufgabe trainiert. Moondream (nur 1,4B Parameter) war schlicht überfordert mit dem komplexen 10-Kategorien-Prompt.

## Die unbequeme Wahrheit: CPU reicht nicht

Die Benchmark-Ergebnisse zeigen aber auch eine Erkenntnis, die ich lieber nicht gehabt hätte: **Auf CPU ist Batch-Verschlagwortung nicht praxistauglich.** LLaVA 13B braucht auf meiner VM rund 7 Minuten pro Bild. Bei 100.000 Bildern wäre das über ein Jahr Rechenzeit.

| Szenario | Zeit pro Bild | 100.000 Bilder |
|---|---|---|
| CPU-only (12 vCPUs) | ~440 s | ~1,4 Jahre |
| GPU (Nvidia P40, erwartet) | ~6–12 s | **7–14 Tage** |

Eine GPU verwandelt das System von einem Experiment in ein Produktionswerkzeug. Die Nvidia P40 gibt es gebraucht ab ca. 275 Euro — im Vergleich zu den kommerziellen Plugins also kein Schnäppchen --- aber dafür kann man damit noch viele andere tolle Experimente machen!

## Fazit: Ein Wochenende, Claude Code und eine GPU-Einkaufsliste

Was ich an diesem Projekt am meisten schätze: die Mischung aus konkretem Nutzen und Experimentierspaß. Claude Code macht es möglich, ein Projekt wie dieses — Lightroom-Plugin, Backend-API, Bildanalyse-Pipeline, Benchmark-Framework — in einem Wochenende von der Idee zum lauffähigen System zu bringen. Nicht perfekt, aber funktional.

Der nächste Schritt ist klar: Server im Keller aufrüsten. Sobald meine GPU-Karte wieder läuft teste ich auch noch zwei größere Modelle, die auf CPU leider gar nicht laufen — LLaVA-Next (34B) und InternVL2 (26B). Wenn die auf einer GPU dieselbe Qualitätssteigerung bringen wie der Sprung von 7B auf 13B, wird es richtig spannend.

Bis dahin tagge ich meine Bilder zumindest im interaktiven Modus — einzeln, bei Bedarf, mit LLaVA 13B auf CPU. Immerhin: die Nadel im Heuhaufen wird langsam sichtbar.

---

*Die Testbilder stammen von Wikimedia Commons unter Creative-Commons-Lizenzen. Der vollständige technische Benchmark mit Rohdaten und Methodik ist als Open-Source-Dokumentation verfügbar. API-Preise sind Schätzwerte basierend auf den offiziellen Preislisten von OpenAI, Anthropic und Google (Stand April 2026).*

---

#KI #KünstlicheIntelligenz #Fotografie #Lightroom #MachineLearning #OpenSource #Ollama #LLaVA #VisionModels #Bildanalyse #Automatisierung #SideProject #ClaudeCode #AITools #Hobbyprojekt #Photography #LocalAI #PrivacyFirst
