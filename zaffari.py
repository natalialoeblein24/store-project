"""
Scraper Zaffari — API VTEX
Documentação VTEX: https://developers.vtex.com/docs/api-reference/search-api
"""

import httpx
import time
import logging
from dataclasses import dataclass
from typing import Iterator

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("scraper.zaffari")

BASE_URL = "https://zaffari.vtexcommercestable.com.br"
PAGE_SIZE = 50  # máximo permitido pela VTEX


@dataclass
class RawProduct:
    external_id: str
    name: str
    brand: str
    price: float | None
    price_unit: str | None
    image_url: str | None
    product_url: str
    market_slug: str = "zaffari"


def _parse_price(item: dict) -> tuple[float | None, str | None]:
    """Extrai preço e unidade — ficam dentro de items[0].sellers na API do Zaffari."""
    try:
        sku = item["items"][0]                    # primeiro SKU do produto
        seller = sku["sellers"][0]                # seller principal
        offer = seller["commertialOffer"]
        price = offer.get("Price") or offer.get("ListPrice")
        unit = sku.get("measurementUnit", "un")
        return float(price), unit
    except (KeyError, IndexError, TypeError):
        return None, None


def _parse_product(item: dict) -> RawProduct:
    price, unit = _parse_price(item)
    image_url = None
    if item.get("items"):
        images = item["items"][0].get("images", [])
        if images:
            image_url = images[0].get("imageUrl")

    return RawProduct(
        external_id=item.get("productId", ""),
        name=item.get("productName", ""),
        brand=item.get("brand", ""),
        price=price,
        price_unit=unit,
        image_url=image_url,
        product_url=f"https://www.zaffari.com.br/{item.get('linkText', '')}/p",
    )


def search(query: str, max_pages: int = 5, delay: float = 1.5) -> Iterator[RawProduct]:
    """
    Busca produtos no Zaffari por termo.

    Args:
        query: termo de busca (ex: 'leite')
        max_pages: limite de páginas pra não sobrecarregar
        delay: pausa entre requisições em segundos

    Yields:
        RawProduct para cada produto encontrado
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0)",
        "Accept": "application/json",
    }

    with httpx.Client(headers=headers, timeout=15) as client:
        for page in range(max_pages):
            start = page * PAGE_SIZE
            end = start + PAGE_SIZE - 1

            url = (
                f"{BASE_URL}/api/catalog_system/pub/products/search"
                f"?ft={query}&_from={start}&_to={end}"
            )

            log.info(f"Buscando '{query}' — página {page + 1} ({start}–{end})")

            try:
                resp = client.get(url)
                resp.raise_for_status()
                products = resp.json()
            except httpx.HTTPError as e:
                log.error(f"Erro na requisição: {e}")
                break

            if not products:
                log.info("Sem mais produtos — encerrando.")
                break

            for item in products:
                yield _parse_product(item)

            if len(products) < PAGE_SIZE:
                break  # última página

            time.sleep(delay)


def search_all_categories(
    categories: list[str], delay: float = 1.5
) -> Iterator[RawProduct]:
    """Busca múltiplas categorias em sequência."""
    for category in categories:
        log.info(f"=== Iniciando categoria: {category} ===")
        yield from search(category, delay=delay)
        time.sleep(delay * 2)


# ── Teste rápido ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Testando scraper Zaffari...\n")

    results = list(search("leite", max_pages=1))

    print(f"Produtos encontrados: {len(results)}\n")
    for p in results[:5]:
        preco = f"R$ {p.price:.2f}" if p.price else "sem preço"
        print(f"  [{p.external_id}] {p.name}")
        print(f"    Marca: {p.brand} | Preço: {preco} | Unidade: {p.price_unit}")
        print(f"    URL: {p.product_url}")
        print()