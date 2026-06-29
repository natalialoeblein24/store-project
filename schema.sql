-- ===========================================
-- Comparador de Preços — Schema PostgreSQL
-- ===========================================

CREATE TABLE IF NOT EXISTS markets (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,   -- ex: 'zaffari', 'supermago'
    base_url    TEXT NOT NULL,
    active      BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Produtos crus exatamente como vieram do scraper
CREATE TABLE IF NOT EXISTS raw_products (
    id          SERIAL PRIMARY KEY,
    market_id   INT NOT NULL REFERENCES markets(id),
    external_id TEXT,                  -- id do produto no sistema deles
    name        TEXT NOT NULL,
    price       DECIMAL(10,2),
    price_unit  TEXT,                  -- ex: 'kg', 'un', 'L'
    brand       TEXT,
    image_url   TEXT,
    product_url TEXT,
    scraped_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (market_id, external_id)
);

-- Produto canônico: representa o "mesmo produto" entre mercados
CREATE TABLE IF NOT EXISTS canonical_products (
    id              SERIAL PRIMARY KEY,
    canonical_name  TEXT NOT NULL,     -- ex: 'Leite Integral Piá 1L'
    brand           TEXT,
    weight_g        INT,               -- peso normalizado em gramas
    volume_ml       INT,               -- volume normalizado em ml
    category        TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Liga raw_products ao canonical (muitos pra um)
CREATE TABLE IF NOT EXISTS product_matches (
    id              SERIAL PRIMARY KEY,
    raw_id          INT NOT NULL REFERENCES raw_products(id),
    canonical_id    INT NOT NULL REFERENCES canonical_products(id),
    confidence      FLOAT,             -- 0.0 a 1.0
    matched_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (raw_id)
);

-- Histórico de preços por canonical + mercado
CREATE TABLE IF NOT EXISTS price_history (
    id              SERIAL PRIMARY KEY,
    canonical_id    INT NOT NULL REFERENCES canonical_products(id),
    market_id       INT NOT NULL REFERENCES markets(id),
    price           DECIMAL(10,2) NOT NULL,
    recorded_at     TIMESTAMPTZ DEFAULT now()
);

-- Índices pra performance nas queries mais comuns
CREATE INDEX IF NOT EXISTS idx_raw_products_market    ON raw_products(market_id);
CREATE INDEX IF NOT EXISTS idx_raw_products_scraped   ON raw_products(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_price_history_canonical ON price_history(canonical_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_matches_canonical ON product_matches(canonical_id);

-- Mercados iniciais
INSERT INTO markets (name, slug, base_url) VALUES
    ('Zaffari',   'zaffari',   'https://zaffari.vtexcommercestable.com.br'),
    ('Supermago', 'supermago', 'https://www.supermago.com.br')
ON CONFLICT (slug) DO NOTHING;
