#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка готовности перед встречей и общая картина по всем командам.

Отвечает на вопросы, которые иначе всплывают в последний момент:
у какой записи нет расшифровки, к какой встрече не написан план,
когда последний раз снимали дневник команды, сколько осталось до финала.

    python3 sostoyanie.py            # по всем командам
    python3 sostoyanie.py "<команда>"

Автор: Роман Игнатенко, https://t.me/ignatenko_roman
"""
import re, sys, unicodedata as ud
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from nastrojka import prochitat, papka_komandy, najti_komandu  # noqa: E402

NFC = lambda s: ud.normalize('NFC', str(s))
MEDIA = {'.webm', '.mov', '.mp4', '.m4v', '.mp3', '.wav', '.m4a'}
IMYA = re.compile(r'^(\d{6})-(.+?)-(ДС\+ТМ\d+|ТМ\d+|ДС|знакомство|интенсив)(-.*)?$', re.I)


def data_snimka(f: Path) -> datetime:
    """Дату берём из имени снимка: файл могли переписать, а имя не врёт."""
    for obrazec in ('%Y-%m-%dT%H-%M-%S', '%Y-%m-%dT%H-%M'):
        try:
            return datetime.strptime(f.stem, obrazec)
        except ValueError:
            continue
    return datetime.fromtimestamp(f.stat().st_mtime)


def razobrat(f: Path):
    m = IMYA.match(NFC(f.stem))
    return (m.group(1), m.group(3)) if m else None


def po_komande(cfg, komanda) -> list:
    s = cfg['struktura_komandy']
    baza = papka_komandy(cfg, komanda)
    stroki = []
    if not baza.exists():
        return [f'  ⚠️  папки команды нет: {baza}']

    vstrechi = baza / s['vstrechi']
    zapisi = baza / s['zapisi']
    dnevniki = baza / s['dnevniki']

    sobytiya = {}
    for f in list(vstrechi.glob('*')) + list(zapisi.glob('*')):
        if not f.is_file():
            continue
        r = razobrat(f)
        if not r:
            stroki.append(f'  ?  имя не по схеме: {f.parent.name}/{f.name}')
            continue
        data, tip = r
        e = sobytiya.setdefault((data, tip), {'plan': False, 'tekst': False, 'zapis': False, 'snimki': 0})
        suf = NFC(f.stem).lower()
        if f.suffix.lower() in MEDIA:
            e['zapis'] = True
        elif f.suffix.lower() == '.txt':
            e['tekst'] = True
        elif f.suffix.lower() in {'.docx', '.doc', '.pdf'} and 'план' in suf:
            e['plan'] = True
        elif f.suffix.lower() in {'.png', '.jpg', '.jpeg'}:
            e['snimki'] += 1

    if not sobytiya:
        stroki.append('  — встреч в папке не найдено')
    for (data, tip) in sorted(sobytiya):
        e = sobytiya[(data, tip)]
        d = f'20{data[:2]}-{data[2:4]}-{data[4:]}'
        bedy = []
        if e['zapis'] and not e['tekst']:
            bedy.append('НЕТ РАСШИФРОВКИ')
        if e['tekst'] and not e['zapis']:
            bedy.append('нет записи')
        if not e['plan']:
            bedy.append('нет плана')
        znak = '⚠️ ' if 'НЕТ РАСШИФРОВКИ' in bedy else ('·  ' if bedy else '✓  ')
        stroki.append(f'  {znak}{d}  {tip:8} ' + ('; '.join(bedy) if bedy else 'всё на месте'))

    papka_k = cfg.get('imena', {}).get('papka_kontrolya', '_kontrol-dnevnika')
    snimki = sorted((dnevniki / papka_k).rglob('*.json')) or sorted(dnevniki.rglob('*.json'))
    if snimki:
        posl = data_snimka(snimki[-1])
        dnej = (datetime.now() - posl).days
        stroki.append(f'  {"⚠️ " if dnej > 7 else "·  "}снимок дневника команды: {posl:%d.%m}, {dnej} дн. назад')
    else:
        stroki.append('  ⚠️  снимков дневника команды нет — не видно, ведёт ли команда его сама')

    rd = list(dnevniki.glob('*дневник трекера*'))
    if rd:
        posl = datetime.fromtimestamp(rd[0].stat().st_mtime)
        dnej = (datetime.now() - posl).days
        stroki.append(f'  {"⚠️ " if dnej > 10 else "·  "}рабочий дневник трекера правился {posl:%d.%m} '
                      f'({dnej} дн. назад)')
    else:
        stroki.append('  ⚠️  рабочего дневника трекера нет')

    if not komanda.get('lpr'):
        stroki.append('  ·  первое лицо не записано в настройках')
    return stroki


def main() -> int:
    cfg = prochitat()
    argv = [a for a in sys.argv[1:] if not a.startswith('--')]
    komandy = [najti_komandu(cfg, argv[0])] if argv else cfg['komandy']

    a = cfg.get('akselerator', {})
    print(f'\n{a.get("nazvanie", "Акселератор")} — состояние на {date.today():%d.%m.%Y}')
    if a.get('cel'):
        print(f'Цель: {a["cel"]}')
    for kljuch, podpis in (('demo_den', 'демо-день'), ('final', 'финал')):
        if a.get(kljuch):
            try:
                d = datetime.strptime(a[kljuch], '%Y-%m-%d').date()
                hvost = '' if a.get('demo_den_podtverzhden', True) or kljuch != 'demo_den' \
                    else ' (дата не подтверждена)'
                print(f'До {podpis}: {(d - date.today()).days} дн., {d:%d.%m.%Y}{hvost}')
            except ValueError:
                pass
    if a.get('obeschano_organizatorami'):
        print('Организаторы обещали: ' + '; '.join(a['obeschano_organizatorami']))

    for komanda in komandy:
        print(f'\n── {komanda["nazvanie"]}')
        for s in po_komande(cfg, komanda):
            print(s)
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
