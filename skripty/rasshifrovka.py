#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Расшифровка записей встреч. Кладёт .txt рядом с записью.

    python3 rasshifrovka.py "<путь к записи>"
    python3 rasshifrovka.py --vse           # всё, у чего ещё нет расшифровки
    python3 rasshifrovka.py --chto          # только показать, что не расшифровано

Способ выбирается в nastrojki.json → rasshifrovka.sposob:
  gladia          — облачный сервис, разделяет говорящих. Ключ берётся из
                    переменной среды, в настройки его класть нельзя.
  whisper-lokalno — локальная модель. Бесплатно и приватно, но долго
                    и без разделения говорящих.
  vneshnij        — свой инструмент, вызывается командой из настроек.

Про сеть. Если работаешь через VPN, часть сервисов нужно звать мимо тоннеля,
часть — обязательно через него. Ошибки при неверной маршрутизации обычно НЕ
будет: будет отказ, похожий на неверный ключ, или молчание. Списки адресов
задаются в nastrojki.json → set. Здесь используется curl с ключом --interface:
он честно уводит запрос мимо тоннеля, в отличие от питоновских обходов,
которые не действуют на дочерние процессы.

Автор: Роман Игнатенко, https://t.me/ignatenko_roman
"""
import json, os, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from nastrojka import prochitat, koren, papka_komandy  # noqa: E402

MEDIA = {'.webm', '.mov', '.mp4', '.m4v', '.mp3', '.wav', '.m4a'}
GLADIA = 'https://api.gladia.io'


# ─────────────────────────────── сеть ───────────────────────────────

def curl_dlya(cfg: dict, adres: str) -> list:
    """Собирает начало команды curl с учётом того, как ходит этот адрес."""
    s = cfg.get('set', {})
    komanda = ['curl', '--silent', '--show-error', '--fail-with-body', '--max-time', '900']
    if not s.get('vpn'):
        return komanda
    host = adres.split('//')[-1].split('/')[0]
    mimo = any(h and h in host for h in s.get('mimo_tonnelya', []))
    if mimo and s.get('interfejs_obhoda'):
        komanda += ['--interface', s['interfejs_obhoda']]
    return komanda


def pozvat(komanda: list) -> str:
    p = subprocess.run(komanda, capture_output=True, text=True)
    if p.returncode != 0:
        hvost = (p.stdout or p.stderr or '').strip()[:400]
        raise RuntimeError(f'curl вернул {p.returncode}: {hvost}')
    return p.stdout


# ─────────────────────────────── Gladia ───────────────────────────────

def gladia(cfg: dict, fajl: Path) -> str:
    r = cfg['rasshifrovka']
    peremennaya = r.get('kljuch_iz_peremennoj', 'GLADIA_API_KEY')
    kljuch = os.environ.get(peremennaya)
    if not kljuch:
        raise SystemExit(
            f'Пустая переменная {peremennaya}. Положи ключ в файл .env рядом с настройками\n'
            f'  {peremennaya}=твой-ключ\n'
            'и подгрузи его перед запуском:  set -a; source .env; set +a')

    zagolovok = ['-H', f'x-gladia-key: {kljuch}']
    otvet = json.loads(pozvat(curl_dlya(cfg, GLADIA) + zagolovok +
                              ['-F', f'audio=@{fajl}', f'{GLADIA}/v2/upload']))
    ssylka = otvet.get('audio_url') or otvet.get('url')
    if not ssylka:
        raise RuntimeError(f'Сервис не вернул ссылку на загруженный файл: {otvet}')

    zadanie = {'audio_url': ssylka,
               'diarization': bool(r.get('diarizaciya', True)),
               'language': r.get('yazyk', 'ru')}
    postavleno = json.loads(pozvat(curl_dlya(cfg, GLADIA) + zagolovok +
                                   ['-H', 'Content-Type: application/json',
                                    '-d', json.dumps(zadanie),
                                    f'{GLADIA}/v2/pre-recorded']))
    adres_rezultata = postavleno.get('result_url')
    if not adres_rezultata:
        raise RuntimeError(f'Сервис не принял задание: {postavleno}')

    print('   отдал на расшифровку, жду…', flush=True)
    for popytka in range(360):
        time.sleep(5)
        rezultat = json.loads(pozvat(curl_dlya(cfg, adres_rezultata) + zagolovok + [adres_rezultata]))
        status = rezultat.get('status')
        if status == 'done':
            return sobrat_tekst(rezultat)
        if status == 'error':
            raise RuntimeError(f'Расшифровка не удалась: {rezultat.get("error_code")} '
                               f'{str(rezultat)[:300]}')
        if popytka % 12 == 0 and popytka:
            print(f'   всё ещё считает, прошло {popytka * 5 // 60} мин', flush=True)
    raise RuntimeError('Расшифровка не закончилась за полчаса — проверь задание в кабинете сервиса.')



def sobrat_tekst(rezultat: dict) -> str:
    r = rezultat.get('result', rezultat)
    t = r.get('transcription', {})
    repliki = t.get('utterances') or []
    if repliki:
        stroki = []
        proshlyj = None
        for u in repliki:
            kto = u.get('speaker')
            kto = f'Говорящий {kto}' if kto is not None else 'Говорящий'
            nachalo = float(u.get('start', 0))
            metka = f'[{int(nachalo // 60):02d}:{int(nachalo % 60):02d}]'
            if kto != proshlyj:
                stroki.append(f'\n{kto} {metka}')
                proshlyj = kto
            stroki.append(u.get('text', '').strip())
        return '\n'.join(stroki).strip()
    return (t.get('full_transcript') or '').strip()


# ─────────────────────────────── whisper и внешний ───────────────────────────────

def whisper_lokalno(cfg: dict, fajl: Path) -> str:
    r = cfg['rasshifrovka']
    vyvod = fajl.parent / f'.whisper-{fajl.stem}'
    vyvod.mkdir(exist_ok=True)
    komanda = ['whisper', str(fajl), '--model', r.get('model_whisper', 'large-v3'),
               '--language', r.get('yazyk', 'ru'), '--output_format', 'txt',
               '--output_dir', str(vyvod)]
    p = subprocess.run(komanda, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f'whisper вернул {p.returncode}: {(p.stderr or "")[-400:]}')
    gotovye = list(vyvod.glob('*.txt'))
    if not gotovye:
        raise RuntimeError('whisper отработал, но .txt не появился')
    tekst = gotovye[0].read_text(encoding='utf-8')
    for f in vyvod.iterdir():
        f.unlink()
    vyvod.rmdir()
    return tekst.strip()


def vneshnij(cfg: dict, fajl: Path) -> str:
    shablon = cfg['rasshifrovka'].get('komanda_vneshnyaya', '')
    if '{fajl}' not in shablon:
        raise SystemExit('В настройках rasshifrovka.komanda_vneshnyaya нет подстановки {fajl}.')
    komanda = shablon.replace('{fajl}', str(fajl))
    p = subprocess.run(komanda, shell=True, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f'Инструмент вернул {p.returncode}: {(p.stderr or p.stdout)[-400:]}')
    ryadom = fajl.with_suffix('.txt')
    if ryadom.exists():
        return ryadom.read_text(encoding='utf-8').strip()
    return p.stdout.strip()


SPOSOBY = {'gladia': gladia, 'whisper-lokalno': whisper_lokalno, 'vneshnij': vneshnij}


# ─────────────────────────────── обход файлов ───────────────────────────────

def kuda_klast(cfg: dict, zapis: Path) -> Path:
    """Расшифровка ложится в папку встреч: она рабочая, её читают глазами.
    Запись остаётся в папке записей, куда почти никто не заходит."""
    s = cfg['struktura_komandy']
    if zapis.parent.name == s['zapisi']:
        return zapis.parent.parent / s['vstrechi'] / (zapis.stem + '.txt')
    return zapis.with_suffix('.txt')


def nerasshifrovannye(cfg: dict) -> list:
    """Записи, у которых ещё нет расшифровки."""
    nashlos = []
    for komanda in cfg['komandy']:
        baza = papka_komandy(cfg, komanda)
        # смотрим и папку записей, и корень: туда падают файлы, которые ещё не разложены
        for papka in (baza / cfg['struktura_komandy']['zapisi'], baza):
            if not papka.exists():
                continue
            for f in sorted(papka.iterdir()):
                if f.is_file() and f.suffix.lower() in MEDIA and not kuda_klast(cfg, f).exists():
                    nashlos.append(f)
    return nashlos


def main() -> int:
    cfg = prochitat()
    argv = [a for a in sys.argv[1:] if not a.startswith('--')]
    kljuchi = {a for a in sys.argv[1:] if a.startswith('--')}
    sposob = cfg['rasshifrovka'].get('sposob', 'vneshnij')
    if sposob not in SPOSOBY:
        raise SystemExit(f'Неизвестный способ расшифровки «{sposob}». '
                         f'Возможные: {", ".join(SPOSOBY)}')

    if argv:
        fajly = [Path(a).expanduser().resolve() for a in argv]
    else:
        fajly = nerasshifrovannye(cfg)

    if '--chto' in kljuchi or (not argv and not fajly):
        if not fajly:
            print('Нерасшифрованных записей нет.')
        else:
            print(f'Ждут расшифровки ({len(fajly)}):')
            for f in fajly:
                mb = f.stat().st_size / 1024 / 1024
                print(f'  {mb:7.0f} МБ  {f.relative_to(koren(cfg))}')
        return 0

    oshibok = 0
    for f in fajly:
        cel = kuda_klast(cfg, f)
        if cel.exists() and '--zanovo' not in kljuchi:
            print(f'· уже расшифровано, пропускаю: {f.name}')
            continue
        print(f'→ {f.name} ({f.stat().st_size / 1024 / 1024:.0f} МБ), способ: {sposob}')
        try:
            tekst = SPOSOBY[sposob](cfg, f)
        except Exception as e:  # noqa: BLE001 — сообщение важнее типа
            print(f'   ✗ не вышло: {e}')
            oshibok += 1
            continue
        if not tekst.strip():
            print('   ✗ сервис вернул пустой текст')
            oshibok += 1
            continue
        cel.parent.mkdir(parents=True, exist_ok=True)
        cel.write_text(tekst, encoding='utf-8')
        print(f'   ✓ {cel.relative_to(koren(cfg))} ({len(tekst)} знаков)')
    return 1 if oshibok else 0


if __name__ == '__main__':
    sys.exit(main())
