# trakmedthc

Monitor cen medycznej marihuany **S-Lab THC 18% i THC 22%** w aptekach na
[GdziePoLek.pl](https://www.gdziepolek.pl). Co 10 minut sprawdza najnizsza cene za gram
i wysyla powiadomienie przez [ntfy](https://ntfy.sh), gdy cena sie zmieni.

Skonfigurowany domyslnie dla aptek w **Krakowie**. Inne miasto: zmien adresy w `PRODUCTS`
(koncowka `/apteki/w-krakowie` -> np. `/apteki/w-warszawie`) oraz wspolrzedne `GEO_LAT` / `GEO_LON`.

## Funkcje

- **Szybkie** - cykl dla obu produktow trwa ok. 1,4 s. Dane sa czytane wprost z `window.staticContext`
  (JSON osadzony w HTML strony), wiec nie jest potrzebna przegladarka ani Selenium - tylko `requests`.
- **Wlasne odleglosci** - dystans do apteki liczony wzorem Haversine'a od Twoich wspolrzednych.
- **Czytelne alerty ntfy** - nazwa apteki, adres, odmiany, cena, odleglosc i porownanie THC18 vs THC22;
  bez emoji.
- Blad pobrania (np. blokada Cloudflare) nie jest traktowany jak "oferty zniknely".

## Instalacja

Wymagany Python 3.9+.

```
pip install requests
```

## Konfiguracja

Zmienne srodowiskowe lub plik `.env` obok `price_check.py` (zmienne srodowiskowe maja pierwszenstwo):

| Zmienna      | Opis                              | Domyslnie              |
|--------------|-----------------------------------|------------------------|
| `NTFY_TOPIC` | temat ntfy (zasubskrybuj go w aplikacji ntfy) | `YOUR_NTFY_TOPIC_HERE` |
| `GEO_LAT`    | szerokosc geograficzna            | `YOUR_LATITUDE_HERE` (wymagane) |
| `GEO_LON`    | dlugosc geograficzna              | `YOUR_LONGITUDE_HERE` (wymagane) |

```
NTFY_TOPIC=YOUR_NTFY_TOPIC_HERE
GEO_LAT=YOUR_LATITUDE_HERE
GEO_LON=YOUR_LONGITUDE_HERE
```

Wybierz trudny do odgadniecia temat - kazdy, kto go zna, moze czytac Twoje powiadomienia.

## Uruchomienie

Jednorazowo na pierwszym planie:

```
python price_check.py
```

W tle na Windows (autostart):

1. Uruchom `setup.bat` - zainstaluje `requests`, zapyta o temat i wspolrzedne (zapisze `.env`),
   doda autostart i uruchomi monitor.
2. Reczne uruchomienie w tle: `wscript apteka_autostart.vbs` (log trafia do `apteka.log`).

Ostatnie najnizsze ceny sa zapisywane w `lowest_price_*.txt` - przy pierwszym uruchomieniu
dostaniesz powiadomienie "Start", potem tylko przy zmianie ceny.

## Uwagi

Skrypt czyta publicznie dostepne strony GdziePoLek. Nie naduzywaj czestotliwosci zapytan.
Ceny i dostepnosc maja charakter informacyjny.
