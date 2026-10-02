# Problemy przy konwersji XML → EPP

Notatka z rzeczywistych faktur KSeF (m.in. Nelli Fashion, Koppol) i importu do Subiekta GT. Dotyczy ścieżki XML FA(3) → plik EDI++ `.epp`.

## 1. Enter w nazwie firmy psuje plik EPP

W XML nazwa sprzedawcy lub nabywcy bywa złamana na dwie linie, np.:

```xml
<Nazwa>NELLI FASHION 
VACHE YEGHIAZARYAN</Nazwa>
```

EPP wymaga **jednego wiersza na jeden rekord**. Znak nowej linii w polu tekstowym rozbijał `[INFO]`, nagłówek dokumentu i kartotekę kontrahentów. Subiekt widział uszkodzony plik i go nie wczytywał.

**Naprawa w programie:** przed zapisem do EPP wszystkie teksty są spłaszczane do jednej linii (`_one_line` w `subksef/conversion/convert.py`).

## 2. Program zapisywał FS zamiast FZ

Faktury z KSeF dla CYFROTEX-u to **zakupy**: nabywcą jest firma z Subiekta, sprzedawcą dostawca.

Program domyślnie stawiał dokument sprzedaży `FS`, bo:

- numer typu `FV/420/2026` nie ma prefiksu `FZ`,
- numer typu `FS 451/P/2026` pochodzi z Subiekta **dostawcy** i myląco wygląda jak sprzedaż u nas.

Skutek: w `[INFO]` trafiał sprzedawca (dostawca), a nie CYFROTEX. Do Subiekta CYFROTEX-u powinien wejść dokument zakupu.

**Naprawa w programie:** przy XML → EPP dokument jest wymuszany jako `FZ`, z `[INFO]` = nabywca i kontrahent = sprzedawca. Prefiks `FS`/`FZ` w numerze z XML jest odcinany przed zapisem.

## 3. Puste kody towarów → kolizja z kartoteką Subiekta (`P1`, `P2`…)

Gdy w XML nie ma `Indeks`, program wcześniej generował krótkie kody `P1`, `P2`, `P3`, `P4`.

W Subiekcie takie symbole często **już istnieją** (np. `P1` = Zakolanówki). Przy imporcie Subiekt bierze towar **ze swojej kartoteki po symbolu**, a nie nazwę z pliku EPP. Na fakturze pojawiała się zła nazwa przy poprawnej cenie i ilości.

**Naprawa w programie:** przy braku indeksu używany jest GTIN (jeśli jest), a w przeciwnym razie unikalny symbol `KS…` (hash z nazwy, ceny i pozycji), żeby nie kolidować z krótkimi kodami w Subiekcie.

**Zalecenie użytkownika:** i tak lepiej w **Edycji** podmienić pozycje na właściwe kody z bazy `towary`, albo dodać je w **Niedodane**, zanim konwertujesz do EPP.

## 4. Dopasowanie po nazwie bywa zbyt szerokie

Automatyczne (żółte) dopasowanie łączy pozycję faktury z towarem w `towary.sqlite`, gdy:

- zgadza się cena netto po rabacie,
- w nazwach jest wspólne słowo (np. `poduszka`, `kołdra`).

Nie sprawdza rozmiaru ani pełnego opisu. Przykład: `Poduszka poliester 38/42` może trafić na `poduszka 3,60` w bazie tylko dlatego, że jest słowo „poduszka” i ta sama cena.

To **nie** jest to samo, co kolizja `P1` w Subiekcie. Żółta podmiana działa w Edycji Subksef i zapisuje się w tabeli `podmiany`; dopiero potem konwersja używa kodu i nazwy z bazy.

Przy wątpliwości: w Edycji usuń żółtą podmianę (−) albo wybierz towar ręcznie (Dodaj).

## 5. Inne rzeczy, które warto mieć na uwadze

| Temat | Stan |
|---|---|
| Magazyn w EPP | Symbol magazynu jest pusty — w niektórych bazach Subiekta import wymaga kodu magazynu z ich kartoteki. |
| Cel komunikacji | Zapisujemy `1` (jak eksport Subiekt–Subiekt z pozycjami). W niektórych plikach Subiekta bywa `3`. |
| Forma płatności | Zapisujemy nazwę (`przelew` / `gotówka`) i termin przy przelewie. W eksportach Subiekta nazwa formy bywa pusta. |
| Baza `towary.sqlite` | Leży w `data/` obok programu / exe. Podmiana samego `.exe` jej nie kasuje. |
| Budowa `.exe` | Tylko na Windowsie: `uv run pyinstaller --noconfirm --windowed --name Subksef main.py`. Na inny PC kopiować cały folder `dist\Subksef`. |

## Przykładowe faktury, na których to wyszło

- `6782913277-…-55.xml` — Nelli Fashion: Enter w nazwie, brak prefiksu FZ w numerze `FV/420/2026`.
- `5511123953-…-56.xml` — Koppol: Enter w nazwach, numer `FS 451/P/2026`, brak indeksów towarów → wcześniej `P1`…`P4` i kolizja w Subiekcie.

## Gdzie jest logika zapisu EPP

Plik: `subksef/conversion/convert.py`.

Opis formatu EPP: `docs/epp.md`.
