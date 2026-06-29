"""
Normalização e match de produtos entre mercados.

Estratégia em dois estágios:
  1. Normalização textual (remove ruído, padroniza unidades)
  2. TF-IDF similarity pra agrupar produtos similares
"""

import re
import unicodedata
import logging
from dataclasses import dataclass
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

log = logging.getLogger("matcher")

# Mapeamento de unidades para forma canônica
UNIT_MAP = {
    # Volume
    r"(\d+)\s*ml": lambda m: f"{m.group(1)}ml",
    r"(\d+[\.,]?\d*)\s*l\b": lambda m: f"{int(float(m.group(1).replace(',', '.')) * 1000)}ml",
    r"(\d+[\.,]?\d*)\s*litros?": lambda m: f"{int(float(m.group(1).replace(',', '.')) * 1000)}ml",
    # Peso
    r"(\d+)\s*g\b": lambda m: f"{m.group(1)}g",
    r"(\d+[\.,]?\d*)\s*kg": lambda m: f"{int(float(m.group(1).replace(',', '.')) * 1000)}g",
    r"(\d+[\.,]?\d*)\s*quilos?": lambda m: f"{int(float(m.group(1).replace(',', '.')) * 1000)}g",
}

# Palavras a remover que não agregam ao match
STOPWORDS = {
    "com", "de", "da", "do", "das", "dos", "e", "em", "para", "por",
    "sem", "ao", "aos", "um", "uma", "uns", "umas", "pack", "fardo",
    "caixa", "cx", "pct", "pacote", "emb", "embalagem", "lata", "garrafa",
    "tetrapak", "tetra", "pak", "unidade", "und", "un",
}


@dataclass
class NormalizedProduct:
    original_name: str
    normalized: str       # texto limpo pra comparação
    brand: str
    quantity: str         # ex: '1000ml', '500g'
    market_slug: str
    external_id: str
    price: float | None


def remove_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def normalize_units(text: str) -> str:
    """Padroniza unidades de medida no texto."""
    for pattern, replacement in UNIT_MAP.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def extract_quantity(text: str) -> str:
    """Extrai a quantidade/peso/volume do nome."""
    patterns = [
        r"\d+\s*ml", r"\d+\s*g\b", r"\d+[\.,]?\d*\s*kg",
        r"\d+[\.,]?\d*\s*l\b", r"\d+[\.,]?\d*\s*litros?",
        r"\d+\s*un\b", r"\d+\s*unidades?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip().lower()
    return ""


def normalize(name: str, brand: str = "", market_slug: str = "", external_id: str = "", price: float | None = None) -> NormalizedProduct:
    """
    Normaliza um nome de produto para comparação.

    Exemplo:
        'Leite Integral Piá 1L Caixa' → 'leite integral pia 1000ml'
    """
    text = name.lower()
    text = remove_accents(text)
    text = normalize_units(text)

    # Remove caracteres especiais exceto letras, números e espaços
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # Remove stopwords
    tokens = [t for t in text.split() if t not in STOPWORDS and len(t) > 1]

    quantity = extract_quantity(name)

    return NormalizedProduct(
        original_name=name,
        normalized=" ".join(tokens),
        brand=remove_accents(brand.lower()),
        quantity=quantity,
        market_slug=market_slug,
        external_id=external_id,
        price=price,
    )


class ProductMatcher:
    """
    Agrupa produtos similares de diferentes mercados usando TF-IDF.

    Uso:
        matcher = ProductMatcher(threshold=0.75)
        groups = matcher.match(products_list)
    """

    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),   # unigramas e bigramas
            min_df=1,
            analyzer="word",
        )

    def match(self, products: list[NormalizedProduct]) -> list[list[NormalizedProduct]]:
        """
        Agrupa produtos similares.

        Returns:
            Lista de grupos, cada grupo contendo produtos equivalentes de mercados diferentes.
        """
        if not products:
            return []

        texts = [p.normalized for p in products]
        tfidf_matrix = self.vectorizer.fit_transform(texts)
        similarity = cosine_similarity(tfidf_matrix)

        # Union-Find simples pra agrupar
        n = len(products)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            parent[find(x)] = find(y)

        for i in range(n):
            for j in range(i + 1, n):
                # Só agrupa se for de mercados diferentes (evita duplicatas do mesmo mercado)
                if (similarity[i, j] >= self.threshold and
                        products[i].market_slug != products[j].market_slug):
                    union(i, j)

        # Monta os grupos
        groups: dict[int, list[NormalizedProduct]] = {}
        for i, product in enumerate(products):
            root = find(i)
            groups.setdefault(root, []).append(product)

        # Retorna apenas grupos com produtos de mais de um mercado
        result = []
        for group in groups.values():
            markets = {p.market_slug for p in group}
            if len(markets) > 1:
                result.append(group)
            else:
                result.append(group)  # inclui todos por ora, filtra na exibição

        log.info(f"Match: {n} produtos → {len(result)} grupos")
        return result

    def best_price(self, group: list[NormalizedProduct]) -> NormalizedProduct | None:
        """Retorna o produto com menor preço do grupo."""
        with_price = [p for p in group if p.price is not None]
        return min(with_price, key=lambda p: p.price) if with_price else None


# ── Teste rápido ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    samples = [
        ("Leite Integral Piá 1L", "Piá", "zaffari", "001", 5.99),
        ("Leite Integral Pia 1 Litro Caixa", "Piá", "supermago", "A01", 5.49),
        ("Leite Semi Desnatado Piá 1L", "Piá", "zaffari", "002", 6.10),
        ("Arroz Branco Tio João 5kg", "Tio João", "zaffari", "003", 28.90),
        ("Arroz Branco Tio Joao 5 kg", "Tio João", "supermago", "B01", 27.50),
        ("Café Pilão Torrado Moído 500g", "Pilão", "zaffari", "004", 18.90),
        ("Cafe Pilao Torrado e Moido 500g", "Pilão", "supermago", "C01", 17.80),
    ]

    normalized = [normalize(name, brand, market, eid, price)
                  for name, brand, market, eid, price in samples]

    print("Produtos normalizados:")
    for p in normalized:
        print(f"  '{p.original_name}' → '{p.normalized}' [{p.quantity}]")

    print("\nMatch de produtos:\n")
    matcher = ProductMatcher(threshold=0.70)
    groups = matcher.match(normalized)

    for i, group in enumerate(groups, 1):
        print(f"Grupo {i}:")
        for p in group:
            preco = f"R$ {p.price:.2f}" if p.price else "—"
            print(f"  [{p.market_slug}] {p.original_name} → {preco}")
        best = matcher.best_price(group)
        if best:
            print(f"  ✓ Melhor preço: {best.market_slug} — R$ {best.price:.2f}")
        print()
