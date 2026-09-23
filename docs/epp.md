# Plik EPP Subiekta

Plik `.epp` to eksport z Subiekta GT w formacie EDI++. Nie jest to XML. To tekst podzielony na sekcje, a pola w wierszu są rozdzielone przecinkami. Tekst w cudzysłowie może zawierać przecinek.

Przykład `AAAA.epp` ma wersję formatu **1.11**, stronę kodową **Windows-1250** i jeden dokument: fakturę zakupu **FZ 107/09/2026**.

## Jak czytać plik

Sekcja zaczyna się etykietą w osobnej linii. Dane są w kolejnych liniach, aż do następnej etykiety. Na końcu pliku jest pusta linia.

```
[INFO]
...dane całego pliku...

[NAGLOWEK]
...jeden dokument albo nazwa kartoteki...

[ZAWARTOSC]
...pozycje albo wiersze kartoteki...
```

`[INFO]` jest zawsze pierwsza i opisuje cały plik. Potem pary `[NAGLOWEK]` i `[ZAWARTOSC]` idą po kolei. Najpierw dokumenty, potem kartoteki: kontrahenci, towary, cennik, grupy.

Daty w polach liczbowych mają postać `rrrrmmddggmmss`, na przykład `20260902000000` to 2 września 2026. Czas bywa wyzerowany.

## Nagłówek pliku

W `AAAA.epp` nadawcą jest firma z Subiekta:

| Pole | Wartość |
|---|---|
| Wersja | 1.11 |
| Cel komunikacji | 3, inny cel |
| Strona kodowa | 1250, Windows |
| Program | Subiekt GT |
| Nadawca | EWA RUDNIK ,,EWA'', NIP 868-119-44-22 |
| Adres | Rynek 10, 32-720 Nowy Wiśnicz |
| Magazyn | 303, Magazyn 2026 |
| Kto wykonał | Szef, 22 września 2026, 12:23 |

Przy fakturze zakupu ta firma jest nabywcą. Przy fakturze sprzedaży byłaby sprzedawcą.

## Dokument

Nagłówek dokumentu ma stałą kolejność pól, niezależnie od typu. Pierwsze pole to symbol:

| Symbol | Znaczenie |
|---|---|
| FZ | faktura zakupu |
| FS | faktura sprzedaży |
| KFZ / KFS | korekta zakupu / sprzedaży |
| PZ / WZ | przyjęcie / wydanie zewnętrzne |
| PA | paragon |

W przykładzie jest `FZ`. Ważne pola z tego pliku:

| Pole | Wartość w AAAA.epp |
|---|---|
| Numer wewnętrzny | 107 |
| Numer u dostawcy | 12/09/2026 |
| Pełny numer | 107/09/2026 |
| Kontrahent | F.H.FOKUS TOMASZ OSTROWSKI, NIP 7272144277, Łódź |
| Kategoria | Zakup towarów lub usług |
| Wystawienie, sprzedaż, otrzymanie | 2026-09-02 |
| Pozycje | 2 |
| Netto / VAT / brutto | 832,00 / 191,36 / 1 023,36 PLN |
| Termin płatności | 2026-09-28 |
| Zapłacono / do zapłaty | 0,00 / 1 023,36 |
| Waluta i kurs | PLN, 1,0000 |

Nazwa formy płatności jest w tym pliku pusta. Status rozszerzony ma wartość 3, czyli płatność automatyczna na fakturze zakupu.

Przy zakupie (`FZ`, `PZ` i korekty zakupu) kontrahent z nagłówka jest sprzedawcą, a firma z `[INFO]` nabywcą. Przy sprzedaży jest odwrotnie.

## Pozycje

Przy eksporcie Subiekt–Subiekt `[ZAWARTOSC]` tuż po dokumencie to lista towarów, nie tabela stawek VAT. Nazwa towaru nie leży w pozycji. Jest w późniejszej kartotece `TOWARY`, po kodzie.

Pozycja z przykładu:

| Pole | Żakiet | Spodnie |
|---|---|---|
| Lp | 1 | 2 |
| Kod | 397 | Z773Y |
| Nazwa z kartoteki | ŻAKIET 109 | Spodnie 99 |
| Ilość | 4 szt. | 4 szt. |
| Cena netto | 109,00 | 99,00 |
| VAT | 23% | 23% |
| Wartość netto | 436,00 | 396,00 |
| VAT kwota | 100,28 | 91,08 |
| Brutto | 536,28 | 487,08 |

Suma pozycji zgadza się z nagłówkiem: 832,00 netto, 191,36 VAT, 1 023,36 brutto.

Kod paskowy w kartotece tego pliku jest pusty.

## Co jest dalej w pliku

Po dokumencie idą kartoteki. Podgląd bierze z nich tylko nazwy i kody towarów. Reszta zostaje w pliku i na razie nie jest pokazywana:

- `KONTRAHENCI`, `GRUPYKONTRAHENTOW`, `CECHYKONTRAHENTOW`, `DODATKOWEKONTRAHENTOW`
- `TOWARY`, `CENNIK`, `GRUPYTOWAROW`, `CECHYTOWAROW`, `DODATKOWETOWAROW`
- `TOWARYKODYCN`, `TOWARYGRUPYJPKVAT`
- `DATYZAKONCZENIA`, `WYMAGALNOSCMPP`, `DOKUMENTYZNACZNIKIJPKVAT`
- puste sekcje: numery nabywców, przyczyny korekt, dokumenty fiskalne, opłaty, WSTO, daty ujęcia korekt

W jednym pliku może być wiele dokumentów, każdy jako własna para nagłówka i zawartości. Podgląd pokazuje je po kolei.
