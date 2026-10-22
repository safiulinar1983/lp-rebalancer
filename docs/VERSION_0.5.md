# LP Rebalancer — v0.5.0

**Назначение:** запуск на Base mainnet с реальными USD-ценами из Chainlink и
возможностью сменить пул внутри DEX без правок кода.

## Что сделано

- **Mainnet по умолчанию:** `config.yaml` переключён на `network: 8453`, профиль
  `8453` содержит проверенные адреса Uniswap V3 и PancakeSwap V3. `.env.example`
  и `.env` используют `BASE_RPC_URL=https://mainnet.base.org`. `strategy.mode`
  остаётся `DRY_RUN` до готовности параметров.
- **Оракул по адресу токена:** `oracle.feeds` — отображение «адрес токена пула →
  фид Chainlink». Порядок токенов в пуле (`token0`/`token1`) больше не влияет на
  цены, поэтому смена пула не требует перестановки настроек оракула. Значение —
  адрес фида или `{address, max_age_seconds}`; `oracle.max_age_seconds` служит
  значением по умолчанию.
- **USDC из Chainlink:** на Base mainnet цена USDC читается из фида USDC/USD
  (`0x7e860098F58bBFC8648a4311b374B1D669a2bc6B`), а не подставляется как `$1`.
  У фида heartbeat 24 часа, поэтому для него задано окно устаревания
  `172800` секунд: с прежними `3600` он почти всегда считался бы устаревшим
  (проверено на mainnet: возраст ответа ~21 час).
- **ETH/USD для газа:** `monitor_position.resolve_native_price_usd` берёт цену
  ETH из фида `weth.address`. `blockchain.gas.resolve_native_token_price_usd`
  удалён, `RebalanceCycle` получает `native_price_usd` явно, поэтому газ в USD
  оценивается и для пулов без WETH (например USDC/cbBTC).
  `scripts/open_position.py::_gas_preflight` больше не требует цен токенов пула.
- **Явные стейблкоины:** `oracle.stablecoins` — список токенов, которые
  оцениваются в `$1` при отсутствии фида (нужно только для Base Sepolia, где
  фида USDC/USD нет). Если фида нет и токен не в списке — ошибка с адресом
  токена; спот-цена пула вместо USD-цены не подставляется. Один и тот же токен
  нельзя одновременно указать в `feeds` и `stablecoins`.
- **Цены по пулу:** `resolve_token_prices(w3, config, token0, token1)`;
  `scripts/rebalance.py` читает токены из состояния пула перед резолвом цен.
- **Сторож пула (`pool_guard.py`):** опциональные `pool.expected_fee`,
  `pool.expected_token0`, `pool.expected_token1`. Значения сверяются с
  состоянием, прочитанным из сети, до резолва цен и подготовки транзакций, так
  что опечатка в `pool.address` при ручной смене пула останавливает бота сразу.
  Сравнение токенов регистронезависимое и позиционное (в порядке, который
  печатает `scripts/monitor_pool.py`); незаданное значение не проверяется;
  одинаковые `expected_token0`/`expected_token1` отвергаются при загрузке
  конфигурации. Ошибка называет пул, `dexes.<dex>.pool` и обе стороны каждого
  несовпадения. Страж включён в `scripts/rebalance.py` (а значит и в
  `scripts/watch.py`), `scripts/open_position.py`, `scripts/mint_position.py`,
  `scripts/monitor_pool.py` и `monitor_position.py`.
- **Документация:** README описывает `oracle.feeds`, окно устаревания фида и
  пошаговую смену пула (`dexes.<dex>.pool.address` + `expected_*` + фиды +
  очистка `token_id`).

## Проверено на mainnet (read-only)

- `network=base`, `dex=uniswap_v3`, пул `0xd0b53D…F224` (WETH/USDC, fee 500):
  ETH/USD = 2410.09, USDC/USD = 0.99985, native price = 2410.09.
- Смена только `pool.address` на `0xfBB6Eed8…43ef` (USDC/cbBTC, fee 500)
  читается корректно: `token0` = USDC (6), `token1` = cbBTC (8), цена
  `81994.18` USDC за 1 cbBTC, диапазон ±1 % `(-67200, -66990)`, газ в USD
  считается по ETH/USD. Uniswap V3 Base имеет пулы USDC/cbBTC во всех fee
  tiers (100/500/3000/10000).
- `scripts/open_position.py --dry-run --amount-usd 24` доходит до проверки
  баланса кошелька, то есть цены Chainlink и расчёт лимитов проходят.
- Страж пула: чтение активного пула `0xd0b53D…F224` с настройками из
  `config.yaml` проходит; подмена только `pool.address` на `0xfBB6Eed8…43ef`
  блокируется (`token0 is …USDC, expected …WETH; token1 is …cbBTC, expected
  …USDC`), неверный `expected_fee: 3000` блокируется, перестановка
  `expected_token0`/`expected_token1` тоже блокируется. `scripts/rebalance.py`
  проходит стража и доходит до поиска NFT (позиции пока нет), `open_position.py`
  — до проверки баланса кошелька.

## Тесты

- `tests/test_config.py` — разбор `oracle.feeds` (адрес фида и отображение,
  переопределение окна, ошибки адресов, список стейблкоинов, конфликт
  `feeds`/`stablecoins`, пустая секция).
- `tests/test_monitor_prices.py` — цены по адресу токена, обратный порядок
  токенов, регистронезависимость, отдельные окна устаревания, `$1` только для
  явных стейблкоинов, ошибка с адресом токена, цена газа из фида WETH.
- `tests/test_rebalance_cycle.py` — газ блокируется без цены ETH и считается для
  пула без WETH.
- `tests/test_pool_guard.py` — совпадение пула, регистронезависимые адреса,
  неверный `fee`, неверный токен, все несовпадения сразу, незаданные и частично
  заданные ожидания, однократное чтение пула и блокировка чужого пула.
- `tests/test_config.py` — дополнительно разбор `pool.expected_*`, значения по
  умолчанию (не заданы), отрицательный/нечисловой `fee`, невалидный адрес
  токена, одинаковые токены, а также стражи активного mainnet-пула.

Полный набор: **409 passed**.

## Ограничения

- Значения стратегии (`check_interval`, `fee_threshold_usd`,
  `max_gas_cost_usd`, `min_eth_balance`) не пересматривались: они обсуждаются
  перед запуском.
- `strategy.mode` остаётся `DRY_RUN`; `LIVE` включается вручную после
  пополнения кошелька и выбора `token_id`.
- Для пулов без WETH (cbBTC и др.) нет скрипта обёртки: нужный токен должен уже
  лежать в кошельке.

## Технологии

- Python 3.14
- Web3.py 7.x
- Chainlink Price Feeds (Base mainnet)
- Uniswap V3 / PancakeSwap V3
- Base / Base Sepolia
- Pytest
