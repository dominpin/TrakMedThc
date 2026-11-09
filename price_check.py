"""Monitor cen suszu S-Lab w aptekach w Krakowie (GdziePoLek.pl) z powiadomieniami ntfy.

Strona produktu GdziePoLek jest renderowana po stronie serwera i zawiera pelny stan
aplikacji w `window.staticContext` (JSON). Wystarczy wiec jedno zapytanie HTTP na
produkt - bez przegladarki, Selenium ani przewijania strony.
"""

import json
import math
import os
import re
import sys
import time
from datetime import date

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path: str) -> None:
    """Wczytuje proste pary KEY=VALUE z pliku .env (zmienne srodowiskowe maja pierwszenstwo)."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    except OSError:
        pass


_load_dotenv(os.path.join(BASE_DIR, ".env"))

# S-Lab na GdziePoLek (stan 2026-11-09) ma tylko dwa susze: THC 18% i THC 22%.
# Jedyny inny produkt S-Lab z THC to ekstrakt (Cannabis extractum normatum THC 2,7%,
# id 136860) - inna postac leku, dlatego nie jest sledzony.
PRODUCTS = {
    "THC18": "https://www.gdziepolek.pl/produkty/117668/cannabis-flos-s-lab-thc-18-cbd-1-marihuana-lecznicza-medyczna/apteki/w-krakowie",
    "THC22": "https://www.gdziepolek.pl/produkty/121591/cannabis-flos-s-lab-thc-22-cbd-1-marihuana-lecznicza-medyczna/apteki/w-krakowie",
}

# Konfiguracja: zmienne srodowiskowe lub plik .env (patrz README.md).
NTFY_TOPIC = os.environ.get("NTFY_TOPIC") or "YOUR_NTFY_TOPIC_HERE"

# Punkt odniesienia do liczenia odleglosci - ustaw GEO_LAT / GEO_LON (np. w .env).
def _coord(name: str, placeholder: str) -> float:
    raw = os.environ.get(name) or placeholder
    try:
        return float(raw)
    except ValueError:
        sys.exit(f"Ustaw zmienna {name} (liczba, np. w pliku .env) - obecnie: {raw}")

GEO_LAT = _coord("GEO_LAT", "YOUR_LATITUDE_HERE")
GEO_LON = _coord("GEO_LON", "YOUR_LONGITUDE_HERE")

INTERVAL_S = 600
MIN_PRICE, MAX_PRICE = 10.0, 200.0  # zl/g - odrzuca oczywiste bledy danych

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9",
}

STATE_MARKER = "window.staticContext = "

# Zakresy emoji (i selektory wariantow) usuwane z tresci powiadomien.
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF\U0000FE0F\U0000200D]"
)
POROWNANIE_RE = re.compile(r"-porownanie-", re.IGNORECASE)

session = requests.Session()
session.headers.update(HEADERS)


class FetchError(Exception):
    """Nie udalo sie pobrac lub odczytac strony (to nie to samo co brak ofert)."""


def price_file(label: str) -> str:
    return os.path.join(BASE_DIR, f"lowest_price_krakow_{label.removeprefix('THC')}.txt")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M')}] {msg}")


# --------------------------------------------------------------------------- ntfy

def clean(text: str) -> str:
    text = EMOJI_RE.sub("", text)
    text = POROWNANIE_RE.sub("", text)
    return text.strip()


def send_notification(title: str, message: str) -> None:
    # Publikacja w formacie JSON: UTF-8 bez kombinowania z kodowaniem naglowkow,
    # brak pola "tags" (ntfy zamienia tagi na emoji).
    payload = {
        "topic": NTFY_TOPIC,
        "title": clean(title),
        "message": clean(message),
        "priority": 4,  # high
    }
    try:
        resp = session.post("https://ntfy.sh/", json=payload, timeout=15)
        resp.raise_for_status()
        print(f"Powiadomienie wyslane (status {resp.status_code})")
    except requests.RequestException as e:
        print(f"Blad ntfy: {e!r}")


# ----------------------------------------------------------------------- scraping

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_state(url: str) -> dict:
    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as e:
        raise FetchError(f"blad sieci: {e!r}") from e

    if resp.status_code != 200:
        hint = " (Cloudflare)" if "Just a moment" in resp.text[:2000] else ""
        raise FetchError(f"HTTP {resp.status_code}{hint}")

    start = resp.text.find(STATE_MARKER)
    if start < 0:
        raise FetchError("brak window.staticContext - zmienil sie uklad strony?")
    try:
        state, _ = json.JSONDecoder().raw_decode(resp.text, start + len(STATE_MARKER))
        return state["reduxState"]
    except (ValueError, KeyError) as e:
        raise FetchError(f"nie mozna odczytac staticContext: {e!r}") from e


def fetch_offers(url: str) -> list[dict]:
    """Zwraca oferty posortowane rosnaco po cenie (pusta lista = brak ofert)."""
    state = load_state(url)
    try:
        product = state["product"]["data"][0]
        pharmacies = state["pharmacies"]["data"]
    except (KeyError, IndexError, TypeError) as e:
        raise FetchError(f"nieoczekiwana struktura danych: {e!r}") from e

    pv_id = product.get("selectedPvId") or product["DefaultProductVariantId"]
    variant = next((v for v in product.get("Variants", []) if v["Id"] == pv_id), {})
    pack_grams = variant.get("NoOfUnits") or 0
    today = date.today().isoformat()

    offers = []
    for ph in pharmacies:
        offer = (ph.get("Offers") or {}).get(str(pv_id))
        if not offer:
            continue

        # Ceny za gram dla partii z data waznosci ("krotkie daty") - tylko niewygasle.
        prices = [
            e["price"] for e in (offer.get("exp") or [])
            if e.get("price") is not None and (e.get("date") or today) >= today
        ]
        # Cena standardowa podawana za cale opakowanie.
        if offer.get("p") and pack_grams:
            prices.append(offer["p"] / pack_grams)

        prices = [round(p, 2) for p in prices if MIN_PRICE <= p <= MAX_PRICE]
        if not prices:
            continue

        lat, lng = ph.get("Lat"), ph.get("Lng")
        offers.append({
            "pharmacy": ph.get("Name", "").strip(),
            "address": " ".join(", ".join(x for x in (ph.get("Street"), ph.get("City")) if x).split()),
            "strains": (offer.get("inf") or "").strip(),
            "best_price": min(prices),
            "km": haversine_km(GEO_LAT, GEO_LON, lat, lng) if lat and lng else None,
        })

    offers.sort(key=lambda o: (o["best_price"], o["km"] if o["km"] is not None else math.inf))
    return offers


# ------------------------------------------------------------------------ storage

def load_previous_price(label: str) -> float:
    try:
        with open(price_file(label), encoding="utf-8") as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        return math.inf


def save_price(label: str, price: float) -> None:
    with open(price_file(label), "w", encoding="utf-8") as f:
        f.write(str(price))


# ------------------------------------------------------------------------- output

def km_str(km) -> str:
    return f"{km:.2f} km" if km is not None else "?"


def print_table(label: str, offers: list[dict]) -> None:
    sep = "-" * 86
    print(f"\n{sep}\n  {label}\n{'APTEKA':<34} {'ADRES':<30} {'CENA':>10} {'KM':>7}\n{sep}")
    for o in offers:
        km = f"{o['km']:.2f}" if o["km"] is not None else "?"
        print(f"{o['pharmacy'][:34]:<34} {o['address'][:30]:<30} {o['best_price']:>5.2f} zl/g {km:>7}")


def build_comparison(prices: dict[str, float]) -> str:
    known = sorted((p, label) for label, p in prices.items() if p < math.inf)
    if len(known) < 2:
        return ""
    cheapest = known[0][0]
    lines = []
    for label in PRODUCTS:
        if label not in prices or prices[label] == math.inf:
            continue
        p = prices[label]
        marker = "<<< TANSZY" if p == cheapest and known[1][0] != cheapest else ""
        lines.append(f"{label}: {p:.2f} zl/g  {marker}".rstrip())
    diff = known[1][0] - cheapest
    lines.append(f"Roznica: {diff:.2f} zl/g" if diff > 0 else "Ceny rowne")
    return "\n".join(lines)


def offer_details(best: dict) -> str:
    lines = [best["pharmacy"]]
    if best["address"]:
        lines.append(best["address"])
    if best["strains"]:
        lines.append(f"Odmiana: {best['strains']}")
    lines.append(f"Cena: {best['best_price']:.2f} zl/g")
    lines.append(f"Odleglosc: {km_str(best['km'])}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- main

def main() -> None:
    fetched: dict[str, list[dict]] = {}

    for label, url in PRODUCTS.items():
        try:
            offers = fetch_offers(url)
        except FetchError as e:
            # Blad pobrania nie oznacza znikniecia ofert - nie ruszamy zapisanej ceny.
            log(f"{label}: Nie udalo sie pobrac danych ({e}) - sprobuje w nastepnym cyklu")
            continue

        if not offers:
            old_price = load_previous_price(label)
            if old_price < math.inf:
                save_price(label, math.inf)
                log(f"{label}: Oferty zniknely (bylo {old_price:.2f} zl/g) - powiadomienie przyjdzie gdy wroca")
            else:
                log(f"{label}: Nie znaleziono ofert.")
            continue

        fetched[label] = offers
        print_table(label, offers)

    current_prices = {
        label: fetched[label][0]["best_price"] if label in fetched else load_previous_price(label)
        for label in PRODUCTS
    }
    comparison = build_comparison(current_prices)
    if comparison:
        print(f"\n{comparison}\n")
    footer = f"\n\n{comparison}" if comparison else ""

    for label, offers in fetched.items():
        best = offers[0]
        new_price = best["best_price"]
        old_price = load_previous_price(label)

        if old_price == math.inf:
            save_price(label, new_price)
            log(f"{label}: Pierwsze uruchomienie / oferty wrocily - {new_price:.2f} zl/g")
            send_notification(
                f"{label} Start: {new_price:.2f} zl/g",
                offer_details(best) + footer,
            )
        elif new_price != old_price:
            save_price(label, new_price)
            direction = "NIZEJ" if new_price < old_price else "WYZEJ"
            log(f"{label}: Zmiana! {old_price:.2f} -> {new_price:.2f} zl/g ({direction})")
            send_notification(
                f"{label} {direction}: {new_price:.2f} zl/g (bylo {old_price:.2f})",
                offer_details(best) + f"\nPoprzednio: {old_price:.2f} zl/g" + footer,
            )
        else:
            log(f"{label}: Najnizsza cena {new_price:.2f} zl/g (bez zmian)")


if __name__ == "__main__":
    # Log trafia do pliku przez przekierowanie - wymuszamy UTF-8 zamiast strony kodowej konsoli.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    try:
        while True:
            try:
                main()
            except Exception as e:
                log(f"BLAD w main(): {e!r} - ponawiam za {INTERVAL_S // 60} minut")
            print(f"Czekam {INTERVAL_S // 60} minut...\n", flush=True)
            time.sleep(INTERVAL_S)
    except KeyboardInterrupt:
        print("\nZatrzymano.")
