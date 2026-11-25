# Webseiten aus dem Informatikunterricht

Sammlung von Tafelbildern, Simulationen und Programmen, veröffentlicht über GitHub Pages:
**https://t-pohl.github.io/websiten-schule/**

Startseite → Klasse → Reihe → Seite. Jede Seite liegt unter `<klasse>/<reihe>/<id>/index.html`.

## Pflege

Die Übersichtsseiten (`index.html` auf Ebene Start, Klasse und Reihe) werden aus `katalog.json`
erzeugt und nie von Hand geändert.

```bash
python3 werkzeug/seite.py vorschlag PFAD/ZUR/DATEI.html     # Klasse/Reihe/Titel aus dem Pfad ableiten
python3 werkzeug/seite.py eintragen --klasse 10hf --reihe informatisches-problemloesen \
        --id schatzkiste --titel "Die Schatzkiste" [--datei X.html] ...
python3 werkzeug/seite.py veroeffentlichen -m "..." --warte-auf "Merkmal" --url 10hf/.../schatzkiste/
```

Tafelbilder werden mit `tafelbild bau X.tafel.json --oeffentlich -o <klasse>/<reihe>/<id>/index.html`
direkt hierher gebaut (ohne Lehrer-Notizen).

## Grenzen

GitHub empfiehlt höchstens 1 GB pro Repo und lehnt Dateien ab 100 MB ab. `seite.py pruefen`
warnt ab 25 MB pro Datei und ab 500 MB Repo-Größe.

## Lizenzen

- `7/entwurf-und-blockbasierte-implementierung/maehroboter-lab/` basiert auf dem Open Roberta Lab
  (Apache License 2.0, https://github.com/OpenRoberta/openroberta-lab), Hinweise in der Seite.
- Tafelbilder enthalten Darstellung und Simulationen des Interaktiven Lehrbuchs (informatik-buch.info).
