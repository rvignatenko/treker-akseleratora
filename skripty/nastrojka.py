#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Мастер развёртывания трекерского проекта.

Умеет три вещи:
  --interaktivno   задать вопросы в терминале и собрать nastrojki.json
  (без ключей)     прочитать nastrojki.json и создать структуру папок
  --proverit       проверить настройки: что не заполнено, куда не достучаться

Ничего не удаляет и не перезаписывает: существующие папки и файлы оставляет как есть.

Автор: Роман Игнатенко, https://t.me/ignatenko_roman
"""
import json, os, sys, unicodedata as ud
from pathlib import Path

NFC = lambda s: ud.normalize('NFC', str(s))
KORNI = ('nastrojki.json',)


def najti_nastrojki(start: Path = None) -> Path:
    """Ищет nastrojki.json в текущей папке и выше — как это делают git и npm."""
    p = (start or Path.cwd()).resolve()
    for kandidat in [p, *p.parents]:
        for imya in KORNI:
            f = kandidat / imya
            if f.exists():
                return f
    raise SystemExit('Не нашёл nastrojki.json ни здесь, ни выше. '
                     'Разверни проект: python3 nastrojka.py --interaktivno')


def prochitat(put: Path = None) -> dict:
    f = put or najti_nastrojki()
    with open(f, encoding='utf-8') as fh:
        cfg = json.load(fh)
    cfg['_koren'] = str(f.parent)
    cfg['_fajl'] = str(f)
    return cfg


def koren(cfg: dict) -> Path:
    return Path(cfg['_koren'])


def papka_komandy(cfg: dict, komanda: dict) -> Path:
    return koren(cfg) / komanda['papka_lokalno']


def podpapki(cfg: dict) -> list:
    s = cfg['struktura_komandy']
    return [s['vstrechi'], s['zapisi'], s['dnevniki'], s['kompaniya']]


def najti_komandu(cfg: dict, obrazec: str) -> dict:
    """По коду или по куску названия. Регистр и форма Unicode не мешают."""
    o = NFC(obrazec).lower()
    tochnye = [k for k in cfg['komandy'] if k['kod'].lower() == o]
    if tochnye:
        return tochnye[0]
    pohozhie = [k for k in cfg['komandy'] if o in NFC(k['nazvanie']).lower()]
    if len(pohozhie) == 1:
        return pohozhie[0]
    if not pohozhie:
        imena = ', '.join(k['nazvanie'] for k in cfg['komandy'])
        raise SystemExit(f'Команда «{obrazec}» не найдена. Есть: {imena}')
    imena = ', '.join(k['nazvanie'] for k in pohozhie)
    raise SystemExit(f'«{obrazec}» подходит сразу нескольким: {imena}. Уточни.')


# ─────────────────────────────── создание структуры ───────────────────────────────

GITIGNORE = """# Записи и звук — тяжёлые, в репозиторий не кладём
*.webm
*.mp4
*.mov
*.m4v
*.mp3
*.wav
# Ключи
.env
# Мусор macOS и Office
.DS_Store
~$*
"""

ENV_PRIMER = """# Скопируй в .env рядом и впиши настоящие значения.
# .env лежит в .gitignore и наружу не уходит.

# Ключ сервиса расшифровки, если пользуешься облачным.
GLADIA_API_KEY=

# Если расшифровываешь другим сервисом — добавь его ключ сюда же
# и укажи имя переменной в nastrojki.json → rasshifrovka.kljuch_iz_peremennoj
"""


def sozdat_strukturu(cfg: dict) -> None:
    k = koren(cfg)
    sozdano, bylo = [], 0
    for komanda in cfg['komandy']:
        baza = papka_komandy(cfg, komanda)
        for sub in podpapki(cfg):
            p = baza / sub
            if p.exists():
                bylo += 1
            else:
                p.mkdir(parents=True)
                sozdano.append(str(p.relative_to(k)))
    for trek in cfg.get('treki', []):
        p = k / 'Образовательный трек' / trek['papka']
        if not p.exists():
            p.mkdir(parents=True)
            sozdano.append(str(p.relative_to(k)))
    obschee = k / 'Образовательный трек' / 'Общее'
    if cfg.get('treki') and not obschee.exists():
        obschee.mkdir(parents=True)
        sozdano.append(str(obschee.relative_to(k)))

    for imya, soderzhimoe in (('.gitignore', GITIGNORE), ('.env.primer', ENV_PRIMER)):
        f = k / imya
        if not f.exists():
            f.write_text(soderzhimoe, encoding='utf-8')
            sozdano.append(imya)

    print(f'Создано папок и файлов: {len(sozdano)}; уже было: {bylo}')
    for s in sozdano:
        print('  +', s)


# ─────────────────────────────── проверка ───────────────────────────────

def proverit(cfg: dict) -> int:
    bed = []
    a = cfg.get('akselerator', {})
    if not a.get('cel') or 'Одной фразой' in str(a.get('cel')):
        bed.append('Не названа цель акселератора — без неё не с чем сверять цели команд.')
    if not a.get('demo_den'):
        bed.append('Не указана дата демо-дня. Если её не назвали организаторы — так и запиши, '
                   'и поставь demo_den_podtverzhden: false.')
    if not cfg.get('komandy'):
        bed.append('Не заведено ни одной команды.')

    kody_trekov = {t['kod'] for t in cfg.get('treki', [])}
    for komanda in cfg.get('komandy', []):
        imya = komanda.get('nazvanie', komanda.get('kod', '?'))
        if komanda.get('trek') not in kody_trekov:
            bed.append(f'{imya}: поток «{komanda.get("trek")}» не описан в treki.')
        p = papka_komandy(cfg, komanda)
        if not p.exists():
            bed.append(f'{imya}: локальной папки нет — {p}')
        setevaya = komanda.get('papka_setevaya')
        if not setevaya:
            bed.append(f'{imya}: не указана сетевая папка. Дневник команды читать неоткуда.')
        elif not Path(setevaya).exists():
            bed.append(f'{imya}: сетевая папка недоступна — {setevaya}. '
                       'Облачный диск не смонтирован или путь изменился.')
        if not komanda.get('lpr'):
            bed.append(f'{imya}: не записано первое лицо. Это главный риск любого трека — '
                       'заполни, чтобы было видно, ходит оно на встречи или нет.')

    r = cfg.get('rasshifrovka', {})
    if r.get('sposob') == 'gladia':
        peremennaya = r.get('kljuch_iz_peremennoj', 'GLADIA_API_KEY')
        if not os.environ.get(peremennaya):
            bed.append(f'Выбрана расшифровка через Gladia, но переменная {peremennaya} пуста. '
                       'Положи ключ в .env и подгрузи его перед запуском.')
    elif r.get('sposob') == 'vneshnij' and '{fajl}' not in str(r.get('komanda_vneshnyaya', '')):
        bed.append('Для внешнего инструмента расшифровки в komanda_vneshnyaya нужен '
                   'подстановочный {fajl}.')

    s = cfg.get('set', {})
    if s.get('vpn') and not (s.get('mimo_tonnelya') or s.get('cherez_tonnel')):
        bed.append('Указано, что работаешь через VPN, но не сказано, какие адреса идут мимо '
                   'тоннеля. Это класс поломок, которые врут успехом, — заполни списки.')

    if bed:
        print('Проверка нашла, что поправить:')
        for b in bed:
            print('  ⚠️ ', b)
    else:
        print('Проверка прошла: настройки заполнены, папки на месте, доступы видны.')
    return 1 if bed else 0


# ─────────────────────────────── интервью ───────────────────────────────

def sprosit(vopros: str, po_umolchaniyu: str = '') -> str:
    hvost = f' [{po_umolchaniyu}]' if po_umolchaniyu else ''
    otvet = input(f'{vopros}{hvost}: ').strip()
    return otvet or po_umolchaniyu


def sprosit_da(vopros: str, po_umolchaniyu: bool = False) -> bool:
    d = 'да' if po_umolchaniyu else 'нет'
    return sprosit(f'{vopros} (да/нет)', d).lower().startswith(('д', 'y', 'l'))


def interviyu() -> dict:
    print('\nРазвёртывание трекерского проекта. Отвечай коротко, всё можно поправить потом\n'
          'руками в nastrojki.json.\n')

    cfg = {'akselerator': {}, 'treki': [], 'komandy': [], 'rasshifrovka': {}, 'set': {}, 'ritm': {}}
    a = cfg['akselerator']
    a['nazvanie'] = sprosit('Название акселератора')
    a['organizator'] = sprosit('Кто организатор')
    print('\nЦель акселератора — это маяк, с которым потом сверяются цели всех команд.\n'
          'Одной фразой и по возможности с измеримым результатом.')
    a['cel'] = sprosit('Цель акселератора')
    a['start'] = sprosit('Дата старта (ГГГГ-ММ-ДД)')
    a['final'] = sprosit('Дата финала (ГГГГ-ММ-ДД)')
    a['demo_den'] = sprosit('Дата демо-дня, если названа')
    a['demo_den_podtverzhden'] = bool(a['demo_den']) and sprosit_da('Дата демо-дня подтверждена')
    a['obeschano_organizatorami'] = []
    print('\nЧто организаторы обещали командам (консультации экспертов, B2B-встречи, гранты).\n'
          'Пустая строка — закончить. Это станет чек-листом: обещанное имеет привычку не приходить.')
    while True:
        o = sprosit('  обещание')
        if not o:
            break
        a['obeschano_organizatorami'].append(o)

    n_trekov = int(sprosit('\nСколько потоков (отраслевых треков) в программе', '1'))
    for i in range(n_trekov):
        print(f'\n— Поток {i + 1}')
        nazvanie = sprosit('  Название потока')
        cfg['treki'].append({
            'kod': sprosit('  Короткий код латиницей', f'trek-{i + 1}'),
            'nazvanie': nazvanie,
            'papka': sprosit('  Имя папки для его материалов', nazvanie),
            'materialy': sprosit('  Адрес, куда организаторы выкладывают записи занятий'),
            'prefiks_fajlov': sprosit('  Префикс имён файлов этого потока, если есть', ''),
        })

    n_komand = int(sprosit('\nСколько у тебя команд', '1'))
    kody = [t['kod'] for t in cfg['treki']]
    for i in range(n_komand):
        print(f'\n— Команда {i + 1}')
        nazvanie = sprosit('  Название команды')
        trek = kody[0] if len(kody) == 1 else sprosit(f'  Поток ({"/".join(kody)})', kody[0])
        papka_treka = next((t['papka'] for t in cfg['treki'] if t['kod'] == trek), '')
        cfg['komandy'].append({
            'kod': sprosit('  Короткий код латиницей', f'komanda-{i + 1}'),
            'nazvanie': nazvanie,
            'trek': trek,
            'papka_lokalno': sprosit('  Локальная папка', f'{papka_treka}/{nazvanie}'.strip('/')),
            'papka_setevaya': sprosit('  Папка команды на сетевом диске (полный путь)'),
            'lpr': sprosit('  Первое лицо: имя и должность'),
            'uchastniki': [u.strip() for u in sprosit('  Кто ходит на встречи, через запятую').split(',') if u.strip()],
        })

    print('\n— Шаблоны документации организаторов')
    cfg['shablony'] = {
        'diagnosticheskaya_sessiya': sprosit('  Шаблон диагностической сессии (путь или пусто)'),
        'dnevnik_komandy': sprosit('  Шаблон дневника команды (путь или пусто)'),
    }
    cfg['dnevnik_komandy'] = {
        'fajl_soderzhit': sprosit('  Как называется файл дневника у команд на диске (кусок имени)',
                                  'Дневник команды'),
        'list_kartochka': sprosit('  Лист с карточкой компании (номер или кусок имени)', '1'),
        'list_vstrechi': sprosit('  Лист со встречами', '2'),
        'list_gipotezy': sprosit('  Лист с гипотезами', '3'),
        'cvet_trekera': sprosit('  Каким цветом трекер пишет свои дописи (RGB)', 'FFFF0000'),
        'stroki_vstrech': [3, 20],
        'stroki_gipotez': [8, 20],
        'kolonki_vstrech': {},
    }

    print('\n— Расшифровка встреч')
    print('  gladia         — облако, платит по минутам, есть бесплатная квота, разделяет говорящих')
    print('  whisper-lokalno — бесплатно и приватно, но нужен мощный компьютер и время')
    print('  vneshnij       — у тебя уже есть свой инструмент, вызовем его командой')
    sposob = sprosit('  Чем расшифровываем', 'gladia')
    cfg['rasshifrovka'] = {
        'sposob': sposob,
        'yazyk': sprosit('  Язык записей', 'ru'),
        'diarizaciya': sprosit_da('  Разделять говорящих по ролям', True),
    }
    if sposob == 'gladia':
        print('\n  Ключ в настройки НЕ пишем: он попадёт в репозиторий и утечёт.')
        print('  Положи его в файл .env рядом, строкой GLADIA_API_KEY=…')
        cfg['rasshifrovka']['kljuch_iz_peremennoj'] = sprosit('  Имя переменной с ключом', 'GLADIA_API_KEY')
    elif sposob == 'whisper-lokalno':
        cfg['rasshifrovka']['model_whisper'] = sprosit('  Модель', 'large-v3')
    else:
        cfg['rasshifrovka']['komanda_vneshnyaya'] = sprosit(
            '  Команда запуска, где {fajl} — путь к записи', '/путь/к/инструменту {fajl}')

    print('\n— Сеть')
    vpn = sprosit_da('  Работаешь через VPN или тоннель', False)
    cfg['set'] = {'vpn': vpn, 'mimo_tonnelya': [], 'cherez_tonnel': [], 'interfejs_obhoda': ''}
    if vpn:
        print('  Это важнее, чем кажется. Российские сервисы часто отказывают запросам из-за границы,\n'
              '  а зарубежные — запросам из России. Ошибки при этом не будет: будет молчаливое враньё.')
        cfg['set']['mimo_tonnelya'] = [h.strip() for h in sprosit(
            '  Какие адреса должны идти МИМО тоннеля, через запятую').split(',') if h.strip()]
        cfg['set']['cherez_tonnel'] = [h.strip() for h in sprosit(
            '  Какие обязательно ЧЕРЕЗ тоннель, через запятую').split(',') if h.strip()]
        cfg['set']['interfejs_obhoda'] = sprosit('  Сетевой интерфейс для обхода', 'en0')

    print('\n— Ритм встреч')
    cfg['ritm'] = {
        'den_nedeli': sprosit('  День недели', 'пятница'),
        'vremya': sprosit('  Время', '14:00'),
        'dlitelnost_min': int(sprosit('  Длительность, минут', '60')),
        'minimum_min': int(sprosit('  Жёсткий минимум, минут', '45')),
    }

    cfg['struktura_komandy'] = {
        'vstrechi': '1-Встречи', 'zapisi': '2-Записи',
        'dnevniki': '3-Дневники', 'kompaniya': '4-О компании',
    }
    cfg['imena'] = {
        'vstrecha': '{data}-{komanda}-{tip}',
        'plan_suffiks': '-план',
        'rabochij_dnevnik': 'Рабочий дневник трекера - {komanda}.docx',
        'reestr_dnevnika': 'reestr.md',
    }
    return cfg


ALGORITM = """
Как это работает дальше
───────────────────────
1. Один чат Claude Code — одна команда. Не смешивай: контекст чата это память
   о команде, и в общем чате она превращается в кашу.
2. Перед каждой встречей: снимок дневника команды  →  план встречи.
      python3 skripty/snimok-dnevnika.py "<команда>"
      python3 skripty/sostoyanie.py
   Дальше просишь Claude собрать план — он читает методику, прошлые расшифровки
   и материалы образовательного трека, которые команда успела услышать.
3. После встречи: кладёшь запись в папку команды и говоришь «разложи и расшифруй».
      python3 skripty/razlozhit.py "<команда>"
      python3 skripty/rasshifrovka.py "<путь к записи>"
   Затем Claude дописывает рабочий дневник трекера: что просил спросить →
   что реально вышло → супервизия.
4. Раз в неделю — сводка по всем командам для организаторов.
5. Что обещали организаторы и не сделали — записывается сразу, с датой запроса.
   К финалу это единственный документ, который у тебя есть на этот разговор.

Подробно — в README.md и в папке metodika/.
"""


def main() -> int:
    argv = sys.argv[1:]
    if '--interaktivno' in argv:
        cfg = interviyu()
        put = Path.cwd() / 'nastrojki.json'
        if put.exists():
            print(f'\n{put} уже есть. Сохраняю рядом как nastrojki.novye.json — сверь и замени сам.')
            put = Path.cwd() / 'nastrojki.novye.json'
        with open(put, 'w', encoding='utf-8') as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        print(f'\nНастройки записаны: {put}')
        cfg['_koren'] = str(put.parent)
        sozdat_strukturu(cfg)
        print(ALGORITM)
        return 0

    cfg = prochitat()
    if '--proverit' in argv:
        return proverit(cfg)
    sozdat_strukturu(cfg)
    print(ALGORITM)
    return 0


if __name__ == '__main__':
    sys.exit(main())
