"""
Scraper Supermago — Playwright (plataforma WD Commerce)
Usa browser headless pois os produtos são renderizados via JavaScript.
URL de busca: https://www.supermago.com.br/pesquisa?t={query}&p={page}
"""

import time
import logging
import re
from dataclasses import dataclass
from typing import Iterator
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("scraper.supermago")

BASE_URL = "https://www.supermago.com.br"


@dataclass
class RawProduct:
    external_id: str
    name: str
    brand: str
    price: float | None
    price_unit: str | None
    image_url: str | None
    product_url: str
    in_stock: bool
    market_slug: str = "supermago"


def _parse_price(text: str) -> float | None:
    """Converte 'R$ 39,90' → 39.90"""
    try:
        cleaned = re.sub(r"[^\d,]", "", text).replace(",", ".")
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def _parse_card(card) -> RawProduct | None:
    try:
        external_id = card.get("data-pid", "")

        name_el = card.select_one("h3.name")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            return None

        price_el = card.select_one("strong.sale-price span")
        price = _parse_price(price_el.get_text(strip=True)) if price_el else None

        stock_el = card.select_one("div.wd-buy-button[data-stock]")
        in_stock = int(stock_el.get("data-stock", 0)) > 0 if stock_el else False

        img_el = card.select_one("img[src]")
        image_url = img_el.get("src") if img_el else None
        if image_url and image_url.startswith("//"):
            image_url = "https:" + image_url

        link_el = card.select_one("a[href]")
        product_url = BASE_URL + link_el.get("href", "") if link_el else BASE_URL

        return RawProduct(
            external_id=external_id,
            name=name,
            brand="",
            price=price,
            price_unit="un",
            image_url=image_url,
            product_url=product_url,
            in_stock=in_stock,
        )
    except Exception as e:
        log.warning(f"Erro ao parsear card: {e}")
        return None


def search(query: str, max_pages: int = 10, delay: float = 2.0) -> Iterator[RawProduct]:
    """
    Busca produtos no Supermago usando Playwright (browser headless).

    Args:
        query: termo de busca (ex: 'leite')
        max_pages: limite de páginas
        delay: pausa entre páginas em segundos

    Yields:
        RawProduct para cada produto encontrado
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="pt-BR",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        # Bloqueia recursos desnecessários pra carregar mais rápido
        page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())
        page.route("**/{analytics,gtm,facebook,doubleclick}**", lambda r: r.abort())

        try:
            for page_num in range(1, max_pages + 1):
                url = f"{BASE_URL}/pesquisa?t={query}&p={page_num}"
                log.info(f"Buscando '{query}' — página {page_num}")

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    # Aguarda os cards de produto aparecerem
                    page.wait_for_selector("[data-pid]", timeout=15000)
                except PlaywrightTimeout:
                    log.warning("Timeout aguardando produtos — encerrando.")
                    break

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                cards = soup.select("[data-pid]")

                if not cards:
                    log.info("Sem produtos nesta página — encerrando.")
                    break

                found = 0
                for card in cards:
                    product = _parse_card(card)
                    if product:
                        found += 1
                        yield product

                log.info(f"  → {found} produtos extraídos")

                # Verifica paginação
                next_btn = page.query_selector("a.next-page, a[rel='next'], .pagination .next, li.next a")
                if not next_btn:
                    log.info("Última página atingida.")
                    break

                time.sleep(delay)

        finally:
            browser.close()


# ── Teste rápido ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.supermago.com.br/pesquisa?t=leite&p=1", wait_until="domcontentloaded")
        try:
            page.wait_for_selector("[data-pid]", timeout=15000)
        except:
            print("TIMEOUT: data-pid não encontrado!")
        
        html = page.content()
        browser.close()

    # Salva o HTML pra inspeção
    with open("C:/Users/natal/OneDrive/Documentos/Store Project/store-project/debug_supermago.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML salvo! Tamanho: {len(html)} caracteres")
    
    # Testa o seletor
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("[data-pid]")
    print(f"Cards [data-pid] encontrados: {len(cards)}")
    if cards:
        print("Primeiro card HTML:")
        print(cards[0].prettify()[:500])

    results = list(search("leite", max_pages=1))

    print(f"\nProdutos encontrados: {len(results)}\n")
    for p in results[:5]:
        preco = f"R$ {p.price:.2f}" if p.price else "sem preço"
        estoque = "em estoque" if p.in_stock else "sem estoque"
        print(f"  [{p.external_id}] {p.name}")
        print(f"    Preço: {preco} | {estoque}")
        print(f"    URL: {p.product_url}")
        print()