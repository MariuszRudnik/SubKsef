# Subksef

Aplikacja desktopowa do podglądu i konwersji faktur między plikiem XML KSeF (schemat FA) a plikiem EPP z Subiekta GT.

Program jest open source. Repozytorium jest publiczne: można je przeglądać, sklonować i pobrać jako archiwum ZIP.

## Co robi

- Otwiera fakturę XML albo plik `.epp`.
- Pokazuje nagłówek: numer, daty, sprzedawcę, nabywcę, netto, VAT, brutto i płatność.
- Pod spodem wyświetla przewijaną tabelę pozycji.
- Przepisuje XML na EPP oraz EPP na XML. Ścieżka pliku wynikowego ustawia się sama.

## Pobranie

```bash
git clone https://github.com/MariuszRudnik/SubKsef.git
cd SubKsef
```

Archiwum ZIP jest na stronie repozytorium, w menu **Code → Download ZIP**.

## Uruchomienie

Potrzebny jest Python 3.14 i [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python main.py
```

## Układ kodu

Opis katalogów jest w [docs/struktura.md](docs/struktura.md). Format pliku EPP jest opisany w [docs/epp.md](docs/epp.md).

## Licencja

Projekt jest udostępniony na licencji MIT. Treść jest w pliku [LICENSE](LICENSE).
