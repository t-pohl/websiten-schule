#!/usr/bin/env python3
"""Sammlung der Schul-Webseiten: Katalog pflegen, Uebersichten bauen, veroeffentlichen.

    seite.py vorschlag DATEI.html                 Vorgaben (Klasse, Reihe, Titel ...) aus dem Pfad ableiten
    seite.py eintragen --klasse K --reihe R --id ID --titel T [--beschreibung B] [--datum D]
                       [--klasse-titel KT] [--reihe-titel RT] [--art A] [--datei X.html]
    seite.py entfernen --klasse K --reihe R --id ID
    seite.py bauen                                 Uebersichtsseiten aus katalog.json erzeugen
    seite.py pruefen                               Katalog und Dateien abgleichen, Groessen pruefen
    seite.py veroeffentlichen -m TEXT [--warte-auf MERKMAL] [--url PFAD]

Jede Seite liegt unter <klasse>/<reihe>/<id>/index.html. Die Uebersichten (index.html auf
Stufe Start, Klasse, Reihe) werden nur aus katalog.json erzeugt und nie von Hand geaendert.
Nur Standardbibliothek.
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KATALOG = REPO / 'katalog.json'
BASIS_URL = 'https://t-pohl.github.io/websiten-schule/'
SEITEN_TITEL = 'Informatik im Unterricht'
UNTERTITEL = 'Tafelbilder, Simulationen und Programme aus dem Unterricht'
CO_AUTHOR = 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
GESPERRT = '0_Daten_Klasse'          # Schuelerdaten: nie veroeffentlichen
WARN_DATEI_MB = 25
FEHLER_DATEI_MB = 95                 # GitHub lehnt ab 100 MB ab
WARN_REPO_MB = 500                   # GitHub empfiehlt hoechstens 1 GB
ARTEN = {'tafelbild': 'Tafelbild', 'simulation': 'Simulation', 'programm': 'Programm',
         'wettbewerb': 'Wettbewerb', 'arbeitsblatt': 'Arbeitsblatt', 'seite': 'Seite'}
FARBEN = ['daten', 'systeme', 'algorithmen', 'ki', 'sicherheit', 'theorie']


class Fehler(Exception):
    pass


# ---------------------------------------------------------------- Namen

def umlaute(text):
    """ae/oe/ue -> ae/oe/ue-Umlaute, ausser nach q (Queue) und ue nach e/a (neue, Mauer)."""
    text = re.sub(r'(?<![qQ])ae', 'ä', text)
    text = re.sub(r'(?<![qQ])oe', 'ö', text)
    text = re.sub(r'(?<![qQeEaA])ue', 'ü', text)
    text = re.sub(r'\bAe', 'Ä', text)
    text = re.sub(r'\bOe', 'Ö', text)
    text = re.sub(r'\bUe', 'Ü', text)
    return text


def slug(text):
    t = text.lower()
    for a, b in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')):
        t = t.replace(a, b)
    t = re.sub(r'[^a-z0-9]+', '-', t).strip('-')
    return t or 'seite'


def klasse_titel(kid):
    return 'Klasse ' + kid.upper()


def klasse_schluessel(kid):
    m = re.match(r'(\d+)(.*)', kid)
    return (int(m.group(1)), m.group(2)) if m else (999, kid)


def datum_de(d):
    try:
        return dt.date.fromisoformat(d).strftime('%d.%m.%Y')
    except (TypeError, ValueError):
        return d or ''


def gesperrt(pfad):
    return GESPERRT in Path(pfad).resolve().parts


# ---------------------------------------------------------------- Katalog

def katalog_lesen():
    if not KATALOG.exists():
        return {'klassen': []}
    return json.loads(KATALOG.read_text(encoding='utf-8'))


def katalog_schreiben(kat):
    kat['klassen'].sort(key=lambda k: klasse_schluessel(k['id']))
    for k in kat['klassen']:
        k['reihen'].sort(key=lambda r: r['titel'].lower())
        for r in k['reihen']:
            r['seiten'].sort(key=lambda s: (s.get('datum') or '', s['titel']))
    KATALOG.write_text(json.dumps(kat, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def finde(liste, id_):
    return next((x for x in liste if x['id'] == id_), None)


# ---------------------------------------------------------------- vorschlag

def vorschlag(datei):
    p = Path(datei).resolve()
    if gesperrt(p):
        raise Fehler(f'{p} liegt in {GESPERRT}/ (Schuelerdaten) und wird nicht veroeffentlicht.')
    teile = p.parts
    klasse = reihe = datum = None
    if 'Eigener_Unterricht' in teile:
        i = teile.index('Eigener_Unterricht')
        rest = teile[i + 1:]
        if len(rest) >= 1:
            klasse = rest[0]
        if len(rest) >= 3:
            reihe = rest[1]
        for t in rest:
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', t):
                datum = t
                break
    kat = katalog_lesen()
    v = {'klasse': None, 'reihe': None}
    if klasse:
        kid = klasse.lower()
        k = finde(kat['klassen'], kid)
        v['klasse'] = {'id': kid, 'titel': k['titel'] if k else klasse_titel(kid), 'neu': k is None}
    if reihe:
        rid = slug(reihe.replace('_', ' '))
        k = finde(kat['klassen'], v['klasse']['id']) if v['klasse'] else None
        r = finde(k['reihen'], rid) if k else None
        v['reihe'] = {'id': rid, 'titel': r['titel'] if r else umlaute(reihe.replace('_', ' ')), 'neu': r is None}
    titel, beschreibung, art = p.stem, '', 'seite'
    if p.suffix == '.html' and p.exists():
        text = p.read_text(encoding='utf-8', errors='replace')
        m = re.search(r'<title>(.*?)</title>', text, re.S | re.I)
        if m and m.group(1).strip():
            titel = html.unescape(m.group(1).strip())
        q = re.search(r'<script type="application/json" id="tafelbild-quelle">(.*?)</script>', text, re.S)
        if q:
            art = 'tafelbild'
            try:
                notiz = json.loads(q.group(1).replace('<\\/', '</')).get('notiz', '')
            except ValueError:
                notiz = ''
            notiz = re.sub(r'^[^–]*\d{4}\s*–\s*', '', notiz)          # "10HF, 26.11.2026 – " weg
            beschreibung = re.split(r'(?<=[a-zäöüß0-9])\.\s', notiz, maxsplit=1)[0].rstrip('.')
    sid = slug(re.sub(r'\.tafel$', '', p.stem).replace('_', ' '))
    v['seite'] = {'id': sid, 'titel': titel, 'beschreibung': beschreibung, 'datum': datum, 'art': art}
    if v['klasse'] and v['reihe']:
        ziel = f"{v['klasse']['id']}/{v['reihe']['id']}/{sid}/"
        k = finde(kat['klassen'], v['klasse']['id'])
        r = finde(k['reihen'], v['reihe']['id']) if k else None
        v['seite']['vorhanden'] = bool(r and finde(r['seiten'], sid))
        v['ziel'] = str(REPO / ziel / 'index.html')
        v['url'] = BASIS_URL + ziel
    return v


# ---------------------------------------------------------------- eintragen / entfernen

def eintragen(a):
    for name in ('klasse', 'reihe', 'id'):
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', getattr(a, name)):
            raise Fehler(f'--{name} "{getattr(a, name)}": nur Kleinbuchstaben, Ziffern und "-".')
    if a.art not in ARTEN:
        raise Fehler(f'--art muss eins von {", ".join(ARTEN)} sein.')
    ordner = REPO / a.klasse / a.reihe / a.id
    if a.datei:
        if gesperrt(a.datei):
            raise Fehler(f'{a.datei} liegt in {GESPERRT}/ (Schuelerdaten) und wird nicht veroeffentlicht.')
        ordner.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(a.datei, ordner / 'index.html')
    if not (ordner / 'index.html').exists():
        raise Fehler(f'{ordner}/index.html fehlt: erst bauen (tafelbild bau ... -o) oder --datei angeben.')
    kat = katalog_lesen()
    k = finde(kat['klassen'], a.klasse)
    if not k:
        k = {'id': a.klasse, 'titel': a.klasse_titel or klasse_titel(a.klasse), 'reihen': []}
        kat['klassen'].append(k)
    elif a.klasse_titel:
        k['titel'] = a.klasse_titel
    r = finde(k['reihen'], a.reihe)
    if not r:
        r = {'id': a.reihe, 'titel': a.reihe_titel or umlaute(a.reihe.replace('-', ' ').title()), 'seiten': []}
        k['reihen'].append(r)
    elif a.reihe_titel:
        r['titel'] = a.reihe_titel
    s = finde(r['seiten'], a.id)
    neu = s is None
    if neu:
        s = {'id': a.id}
        r['seiten'].append(s)
    s.update({'titel': a.titel, 'beschreibung': a.beschreibung or s.get('beschreibung', ''),
              'datum': a.datum or s.get('datum', ''), 'art': a.art})
    katalog_schreiben(kat)
    bauen()
    print(f"{'Eingetragen' if neu else 'Aktualisiert'}: {a.klasse}/{a.reihe}/{a.id}/ -> {BASIS_URL}{a.klasse}/{a.reihe}/{a.id}/")


def entfernen(a):
    kat = katalog_lesen()
    k = finde(kat['klassen'], a.klasse)
    r = finde(k['reihen'], a.reihe) if k else None
    s = finde(r['seiten'], a.id) if r else None
    if not s:
        raise Fehler(f'{a.klasse}/{a.reihe}/{a.id} steht nicht im Katalog.')
    r['seiten'].remove(s)
    if not r['seiten']:
        k['reihen'].remove(r)
    if not k['reihen']:
        kat['klassen'].remove(k)
    shutil.rmtree(REPO / a.klasse / a.reihe / a.id, ignore_errors=True)
    katalog_schreiben(kat)
    bauen()
    print(f'Entfernt: {a.klasse}/{a.reihe}/{a.id}/')


# ---------------------------------------------------------------- bauen

def farbe(id_):
    return FARBEN[int(hashlib.md5(id_.encode()).hexdigest(), 16) % len(FARBEN)]


def e(t):
    return html.escape(str(t or ''))


def seite_html(tiefe, titel, krumen, inhalt):
    vor = '../' * tiefe
    leiste = ''
    if krumen:
        teile = [f'<a href="{vor}">Start</a>']
        for i, (text, href) in enumerate(krumen):
            teile.append(f'<a href="{href}">{e(text)}</a>' if href else f'<span aria-current="page">{e(text)}</span>')
        leiste = '<nav class="krumen" aria-label="Pfad">' + ' <span class="trenner">›</span> '.join(teile) + '</nav>'
    kopf = SEITEN_TITEL if not krumen else f'{titel} · {SEITEN_TITEL}'
    return f'''<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{e(kopf)}</title>
  <link rel="stylesheet" href="{vor}stil.css">
</head>
<body>
  <header class="leiste"><a class="marke" href="{vor}"><span class="marke-name">Informatik</span><span class="marke-punkt">.</span><span class="marke-zusatz">Unterricht</span></a></header>
  <main>
    {leiste}
    <h1>{e(titel)}</h1>
{inhalt}
  </main>
</body>
</html>
'''


def zahl(n, eins, mehr):
    return f'{n} {eins if n == 1 else mehr}'


def bauen():
    kat = katalog_lesen()
    klassen = [k for k in sorted(kat['klassen'], key=lambda k: klasse_schluessel(k['id']))
               if any(r['seiten'] for r in k['reihen'])]
    # Start
    kacheln = []
    for k in klassen:
        n_r = sum(1 for r in k['reihen'] if r['seiten'])
        n_s = sum(len(r['seiten']) for r in k['reihen'])
        kacheln.append(f'''      <a class="stufen-kachel" href="{k['id']}/">
        <span class="stufen-kachel-titel">{e(k['titel'])}</span>
        <span class="stufen-kachel-sub">{zahl(n_r, 'Reihe', 'Reihen')}</span>
        <span class="stufen-kachel-zahl">{zahl(n_s, 'Seite', 'Seiten')}</span>
      </a>''')
    inhalt = f'    <p class="einleitung">{e(UNTERTITEL)}</p>\n    <div class="kacheln">\n' + '\n'.join(kacheln) + '\n    </div>'
    if not kacheln:
        inhalt = '    <p class="einleitung">Noch keine Seiten.</p>'
    (REPO / 'index.html').write_text(seite_html(0, SEITEN_TITEL, [], inhalt), encoding='utf-8')
    gebaut = 1
    for k in klassen:
        reihen = [r for r in sorted(k['reihen'], key=lambda r: r['titel'].lower()) if r['seiten']]
        kacheln = []
        for r in reihen:
            letzte = max((s.get('datum') or '' for s in r['seiten']), default='')
            text = f'zuletzt {datum_de(letzte)}' if letzte else ''
            kacheln.append(f'''      <a class="feld-kachel bereich-{farbe(r['id'])}" href="{r['id']}/">
        <span class="feld-kachel-bereich">Reihe</span>
        <span class="feld-kachel-titel">{e(r['titel'])}</span>
        <span class="feld-kachel-text">{e(text)}</span>
        <span class="feld-kachel-marke">{zahl(len(r['seiten']), 'Seite', 'Seiten')}</span>
      </a>''')
        inhalt = '    <div class="kacheln">\n' + '\n'.join(kacheln) + '\n    </div>'
        (REPO / k['id']).mkdir(exist_ok=True)
        (REPO / k['id'] / 'index.html').write_text(
            seite_html(1, k['titel'], [(k['titel'], None)], inhalt), encoding='utf-8')
        gebaut += 1
        for r in reihen:
            kacheln = []
            for s in sorted(r['seiten'], key=lambda s: (s.get('datum') or '', s['titel'])):
                kacheln.append(f'''      <a class="feld-kachel bereich-{farbe(r['id'])}" href="{s['id']}/">
        <span class="feld-kachel-bereich">{e(datum_de(s.get('datum')))}</span>
        <span class="feld-kachel-titel">{e(s['titel'])}</span>
        <span class="feld-kachel-text">{e(s.get('beschreibung'))}</span>
        <span class="feld-kachel-marke">{e(ARTEN.get(s.get('art'), 'Seite'))}</span>
      </a>''')
            inhalt = '    <div class="kacheln">\n' + '\n'.join(kacheln) + '\n    </div>'
            (REPO / k['id'] / r['id']).mkdir(exist_ok=True)
            (REPO / k['id'] / r['id'] / 'index.html').write_text(
                seite_html(2, r['titel'], [(k['titel'], '../'), (r['titel'], None)], inhalt), encoding='utf-8')
            gebaut += 1
    print(f'Uebersichten gebaut: {gebaut}')


# ---------------------------------------------------------------- pruefen

def pruefen():
    fehler, hinweise = [], []
    kat = katalog_lesen()
    bekannt = set()
    for k in kat['klassen']:
        for r in k['reihen']:
            for s in r['seiten']:
                rel = f"{k['id']}/{r['id']}/{s['id']}"
                bekannt.add(rel)
                if not (REPO / rel / 'index.html').exists():
                    fehler.append(f'{rel}/index.html fehlt (steht im Katalog).')
    for f in REPO.glob('*/*/*/index.html'):
        rel = str(f.parent.relative_to(REPO))
        if rel not in bekannt and not rel.startswith(('.git', 'werkzeug')):
            hinweise.append(f'{rel}/ steht nicht im Katalog (verwaist).')
    for f in REPO.rglob('*'):
        if '.git' in f.parts or not f.is_file():
            continue
        mb = f.stat().st_size / 1e6
        if mb > FEHLER_DATEI_MB:
            fehler.append(f'{f.relative_to(REPO)}: {mb:.0f} MB, GitHub lehnt Dateien ab 100 MB ab.')
        elif mb > WARN_DATEI_MB:
            hinweise.append(f'{f.relative_to(REPO)}: {mb:.0f} MB, gross (Video?).')
    repo_mb = None
    try:
        aus = subprocess.run(['git', 'count-objects', '-v'], cwd=REPO, capture_output=True, text=True, check=True).stdout
        werte = dict(z.split(': ') for z in aus.strip().splitlines())
        repo_mb = (int(werte.get('size', 0)) + int(werte.get('size-pack', 0))) / 1024
        if repo_mb > WARN_REPO_MB:
            hinweise.append(f'Repo hat {repo_mb:.0f} MB (GitHub empfiehlt hoechstens 1 GB): an ein zweites Repo denken.')
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        pass
    for h in hinweise:
        print('Hinweis:', h)
    for f in fehler:
        print('FEHLER:', f)
    n = len(bekannt)
    print(f'{n} Seiten im Katalog' + (f', Repo {repo_mb:.1f} MB' if repo_mb is not None else '')
          + (', alles in Ordnung.' if not fehler else f', {len(fehler)} Fehler.'))
    return not fehler


# ---------------------------------------------------------------- veroeffentlichen

def git(*args, check=True):
    return subprocess.run(['git', *args], cwd=REPO, capture_output=True, text=True, check=check)


def warten(url, merkmal, minuten=6):
    print(f'Warte auf {url} ...', flush=True)
    ende = time.time() + minuten * 60
    while time.time() < ende:
        try:
            req = urllib.request.Request(f'{url}?t={int(time.time())}', headers={'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(req, timeout=20) as r:
                if merkmal in r.read().decode('utf-8', errors='replace'):
                    print(f'Online: {url}')
                    return True
        except Exception:
            pass
        time.sleep(15)
    print(f'Nach {minuten} min noch nicht online: {url}')
    return False


def veroeffentlichen(a):
    if git('remote', check=False).stdout.strip():
        r = git('pull', '--rebase', '--autostash', check=False)
        if r.returncode:
            raise Fehler('git pull --rebase ging schief:\n' + r.stdout + r.stderr)
    bauen()
    if not pruefen():
        raise Fehler('Pruefung fehlgeschlagen, nichts veroeffentlicht.')
    git('add', '-A')
    if git('diff', '--cached', '--quiet', check=False).returncode:
        git('commit', '-q', '-m', f'{a.m}\n\n{CO_AUTHOR}')
        r = git('push', '-q', check=False)
        if r.returncode:
            raise Fehler('git push ging schief:\n' + r.stdout + r.stderr)
        print('Committet und gepusht:', git('log', '-1', '--format=%h %s').stdout.strip())
    else:
        print('Nichts zu committen.')
    if a.warte_auf:
        url = BASIS_URL + (a.url or '').lstrip('/')
        return warten(url, a.warte_auf)
    return True


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(prog='seite.py', description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='befehl')
    p = sub.add_parser('vorschlag', help='Vorgaben aus dem Pfad ableiten')
    p.add_argument('datei')
    p = sub.add_parser('eintragen', help='Seite eintragen oder aktualisieren')
    for n in ('--klasse', '--reihe', '--id', '--titel'):
        p.add_argument(n, required=True)
    p.add_argument('--beschreibung', default='')
    p.add_argument('--datum', default='')
    p.add_argument('--klasse-titel')
    p.add_argument('--reihe-titel')
    p.add_argument('--art', default='tafelbild')
    p.add_argument('--datei', help='HTML-Datei, die nach <klasse>/<reihe>/<id>/index.html kopiert wird')
    p = sub.add_parser('entfernen', help='Seite aus Katalog und Repo nehmen')
    for n in ('--klasse', '--reihe', '--id'):
        p.add_argument(n, required=True)
    sub.add_parser('bauen', help='Uebersichtsseiten erzeugen')
    sub.add_parser('pruefen', help='Katalog und Dateien pruefen')
    p = sub.add_parser('veroeffentlichen', help='bauen, pruefen, committen, pushen, warten')
    p.add_argument('-m', required=True, help='Commit-Nachricht')
    p.add_argument('--warte-auf', help='Text, den die Seite online enthalten muss')
    p.add_argument('--url', help='Pfad unter der Basis-URL, z. B. 10hf/reihe/id/')
    a = ap.parse_args(argv)
    try:
        if a.befehl == 'vorschlag':
            print(json.dumps(vorschlag(a.datei), ensure_ascii=False, indent=2))
        elif a.befehl == 'eintragen':
            eintragen(a)
        elif a.befehl == 'entfernen':
            entfernen(a)
        elif a.befehl == 'bauen':
            bauen()
        elif a.befehl == 'pruefen':
            return 0 if pruefen() else 1
        elif a.befehl == 'veroeffentlichen':
            return 0 if veroeffentlichen(a) else 1
        else:
            ap.print_help()
            return 2
        return 0
    except Fehler as ex:
        print(f'Fehler: {ex}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
