# Struktura katalogów

Aplikacja startuje z `main.py`. Okna i późniejsza logika mieszkają w pakiecie `subksef`, żeby kolejne opcje nie rosły w jednym pliku.

```
main.py                      # tylko start: wx.App i pokazanie okna
docs/struktura.md            # ta instrukcja
docs/epp.md                  # jak działa plik EPP Subiekta
subksef/
  __init__.py
  invoice/
    __init__.py
    fa3.py                   # odczyt faktury FA z XML
    epp.py                   # odczyt dokumentów z pliku EPP
  conversion/
    __init__.py
    convert.py               # XML na EPP i EPP na XML
  ui/
    __init__.py
    main_frame.py            # okno główne
    preview_frame.py         # podgląd faktury
```

## Co gdzie trafia

- `main.py` uruchamia aplikację. Nie dodawaj tu ekranów ani przetwarzania plików.
- Nowe okno lub zakładka to osobny plik w `subksef/ui/`.
- Odczyt faktury z XML i pliku EPP jest w `subksef/invoice/`. Okno tylko pokazuje wynik.
- Opis formatu EPP jest w `docs/epp.md`.
- Przepisanie XML na EPP i EPP na XML jest w `subksef/conversion/`. Przycisk w oknie tylko je wywołuje.
- Opis układu i zasad zostaje w `docs/`.

## Uruchomienie

Z katalogu projektu:

```bash
uv run python main.py
```
