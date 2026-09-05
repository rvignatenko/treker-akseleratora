#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Раскладывает папку команды по единой структуре и приводит имена к одному виду.

По умолчанию НИЧЕГО не двигает — печатает план. Двигает только с ключом --go,
и тогда же кладёт рядом карту отката.

    python3 razlozhit.py "<команда>"          # показать план
    python3 razlozhit.py "<команда>" --go     # выполнить
    python3 razlozhit.py --vse                # план по всем командам

Правило имени: ГГММДД-<Команда>-<Тип>[-суффикс].расширение
Дата впереди — папка сортируется хронологически сама, план и расшифровка одной
встречи всегда стоят рядом.

Автор: Роман Игнатенко, https://t.me/ignatenko_roman
"""
import json, re, shutil, sys, unicodedata as ud
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from nastrojka import prochitat, koren, papka_komandy, podpapki, najti_komandu  # noqa: E402

NFC = lambda s: ud.normalize('NFC', str(s))

MEDIA = {'.webm', '.mov', '.mp4', '.m4v', '.mp3', '.wav', '.m4a'}
TEKST = {'.txt', '.srt', '.vtt'}
DOK = {'.docx', '.doc', '.pdf', '.rtf'}
TABLICY = {'.xlsx', '.xls', '.csv'}
KARTINKI = {'.png', '.jpg', '.jpeg', '.heic'}

# ДС, ДС+ТМ1, ТМ7, знакомство — и всё это в любом регистре
TIP = re.compile(r'(ДС\s*\+\s*ТМ\d+|ТМ\s*\d+|ДС|знакомств\w*|интенсив)', re.I)
DATA_V_IMENI = re.compile(r'(?<!\d)(\d{6})(?!\d)')
SNIMOK_EKRANA = re.compile(r'^(?:Screenshot|Снимок экрана)[ _](\d{4}-\d{2}-\d{2})[ _]', re.I)
PLAN = re.compile(r'план|plan', re.I)


def normalizovat_tip(syroj: str) -> str:
    """«тм 4» и «ТМ4» — один и тот же тип встречи."""
    t = NFC(syroj).strip().upper().replace(' ', '')
    t = t.replace('ЗНАКОМСТВА', 'ЗНАКОМСТВО').replace('ЗНАКОМСТВЕ', 'ЗНАКОМСТВО')
    return t.replace('ЗНАКОМСТВО', 'знакомство').replace('ИНТЕНСИВ', 'интенсив')


def data_fajla(f: Path) -> str:
    """ГГММДД из имени, иначе из даты изменения файла."""
    m = DATA_V_IMENI.search(f.name)
    if m:
        return m.group(1)
    m = SNIMOK_EKRANA.match(NFC(f.name))
    if m:
        return datetime.strptime(m.group(1), '%Y-%m-%d').strftime('%y%m%d')
    return datetime.fromtimestamp(f.stat().st_mtime).strftime('%y%m%d')


def sobrat_kalendar(fajly: list) -> dict:
    """Тип встречи → дата. Опора — файлы, где в имени есть и дата, и тип."""
    kalendar = {}
    for f in fajly:
        t = TIP.search(NFC(f.name))
        d = DATA_V_IMENI.search(f.name)
        if not (t and d):
            continue
        tip, data = normalizovat_tip(t.group(1)), d.group(1)
        kalendar.setdefault(tip, {}).setdefault(data, []).append(f.name)
    itog, konflikty = {}, []
    for tip, daty in kalendar.items():
        if len(daty) == 1:
            itog[tip] = next(iter(daty))
        else:
            # Побеждает дата, которая встречается чаще: планы обычно называют верно,
            # а записи иногда приезжают со старой датой.
            luchshaya = max(daty, key=lambda d: len(daty[d]))
            itog[tip] = luchshaya
            konflikty.append((tip, {d: daty[d] for d in daty}, luchshaya))
    po_datam = {}
    for tip, data in itog.items():
        po_datam.setdefault(data, []).append(tip)
    return itog, {d: t[0] for d, t in po_datam.items() if len(t) == 1}, konflikty


def plan_dlya_komandy(cfg: dict, komanda: dict) -> tuple:
    baza = papka_komandy(cfg, komanda)
    imya = komanda['nazvanie']
    s = cfg['struktura_komandy']
    plan_suf = cfg.get('imena', {}).get('plan_suffiks', '-план')
    if not baza.exists():
        return baza, [], [f'папки команды нет: {baza}'], []

    svoi = [f for f in sorted(baza.rglob('*'))
            if f.is_file() and f.name != '.DS_Store' and not f.name.startswith('~$')
            and f.relative_to(baza).parts[0] not in podpapki(cfg)]
    kalendar, po_datam, konflikty = sobrat_kalendar(svoi)

    # нумерация скриншотов внутри одного дня
    po_dnyam = {}
    for f in svoi:
        if f.suffix.lower() in KARTINKI:
            po_dnyam.setdefault(data_fajla(f), []).append(f)
    for d in po_dnyam:
        po_dnyam[d].sort(key=lambda x: x.stat().st_mtime)

    hody, voprosy = [], []
    for f in svoi:
        rel, ext, nazv = f.relative_to(baza), f.suffix.lower(), NFC(f.name)
        t = TIP.search(nazv)
        tip = normalizovat_tip(t.group(1)) if t else None
        data = kalendar.get(tip) or data_fajla(f)

        if 'дневник' in nazv.lower() or 'diary' in nazv.lower():
            hody.append((f, baza / s['dnevniki'] / f.name)); continue
        if ext in TABLICY:
            hody.append((f, baza / s['kompaniya'] / f.name)); continue
        if ext in KARTINKI:
            den = data_fajla(f)
            tip_snimka = tip or po_datam.get(den)
            if not tip_snimka:
                voprosy.append(f'{rel}: снимок от {den}, но встречи в этот день не нашлось — '
                               'оставил на месте')
                continue
            nn = po_dnyam[den].index(f) + 1
            hody.append((f, baza / s['zapisi'] / f'{den}-{imya}-{tip_snimka}-{nn:02d}{ext}')); continue
        if not tip:
            podskazka = ''
            m = re.search(r'(\d{2})[.\-](\d{2})[.\-](\d{2})', f.stem)
            if m:
                podskazka = (f' Похоже на встречу {m.group(1)}.{m.group(2)}.20{m.group(3)} — '
                             f'переименуй в {m.group(3)}{m.group(2)}{m.group(1)}-{imya}-ТМN{ext}')
            voprosy.append(f'{rel}: в имени нет типа встречи (ДС, ТМ2 …) — оставил на месте.{podskazka}')
            continue
        if ext in DOK and PLAN.search(nazv):
            hody.append((f, baza / s['vstrechi'] / f'{data}-{imya}-{tip}{plan_suf}{ext}')); continue
        if ext in TEKST:
            hody.append((f, baza / s['vstrechi'] / f'{data}-{imya}-{tip}{ext}')); continue
        if ext in MEDIA:
            hody.append((f, baza / s['zapisi'] / f'{data}-{imya}-{tip}{ext}')); continue
        voprosy.append(f'{rel}: не понял, что это за файл — оставил на месте')

    celi = [NFC(str(c)) for _, c in hody]
    stolknoveniya = sorted({c for c in celi if celi.count(c) > 1})
    return baza, hody, voprosy, (konflikty, stolknoveniya)


def vypolnit(cfg: dict, komandy: list, delat: bool) -> int:
    vsego, problem = 0, 0
    otkat = []
    for komanda in komandy:
        baza, hody, voprosy, (konflikty, stolknoveniya) = plan_dlya_komandy(cfg, komanda)
        print('=' * 72)
        print(f'{komanda["nazvanie"]} — перемещений: {len(hody)}')
        for src, dst in hody:
            print(f'   {src.relative_to(baza)}  ⇒  {dst.relative_to(baza)}')
        for tip, daty, vybrana in konflikty:
            print(f'   ⚠️  У «{tip}» в именах разные даты: '
                  + '; '.join(f'{d} ({len(v)} файл.)' for d, v in daty.items())
                  + f' — взял {vybrana}. Проверь, какая настоящая.')
            problem += 1
        for v in voprosy:
            print('   ?  ' + v); problem += 1
        for s in stolknoveniya:
            print('   ‼️  два файла метят в одно имя: ' + s); problem += 1
        if delat and not stolknoveniya:
            for src, dst in hody:
                dst.parent.mkdir(parents=True, exist_ok=True)
                otkat.append([str(dst), str(src)])
                shutil.move(str(src), str(dst))
            for sub in podpapki(cfg):
                (baza / sub).mkdir(exist_ok=True)
            opornye = set(podpapki(cfg))
            for p in sorted(baza.rglob('*'), key=lambda x: -len(x.parts)):
                if p.name in opornye and p.parent == baza:
                    continue
                if p.is_dir() and not any(c.name != '.DS_Store' for c in p.iterdir()):
                    for c in p.iterdir():
                        c.unlink()
                    p.rmdir()
                    print('   убрана пустая папка:', p.relative_to(baza))
        elif delat and stolknoveniya:
            print('   ✋ ничего не двигаю: сначала разведи столкнувшиеся имена.')
        vsego += len(hody)
    print('=' * 72)
    if delat and otkat:
        f = koren(cfg) / f'razlozhit-otkat-{datetime.now():%y%m%d-%H%M}.json'
        with open(f, 'w', encoding='utf-8') as fh:
            json.dump(otkat, fh, ensure_ascii=False, indent=1)
        print('карта отката:', f)
    print(f'Всего перемещений: {vsego}; мест, где нужен твой глаз: {problem}')
    print('ВЫПОЛНЕНО' if delat else 'Это только план. Чтобы выполнить — добавь --go')
    return 0


def main() -> int:
    argv = [a for a in sys.argv[1:] if not a.startswith('--')]
    kljuchi = {a for a in sys.argv[1:] if a.startswith('--')}
    cfg = prochitat()
    if '--vse' in kljuchi or not argv:
        komandy = cfg['komandy']
    else:
        komandy = [najti_komandu(cfg, argv[0])]
    return vypolnit(cfg, komandy, '--go' in kljuchi)


if __name__ == '__main__':
    sys.exit(main())
