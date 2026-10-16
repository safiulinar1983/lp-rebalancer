# LP Rebalancer — v0.3.5

**Назначение:** рефакторинг и консолидация кода перед реализацией бизнес-логики
ребалансировки. Поведение стратегии, плана ребалансировки и расчётов обмена не
менялось.

## Что сделано

- **Единый источник ABI:** `blockchain/abis.py` (`POOL_ABI`, `ERC20_ABI`,
  `WETH_ABI`, `CHAINLINK_ABI`, `POSITION_MANAGER_ABI`). Локальные копии ABI
  удалены из модулей и скриптов.
- **Общие константы точности:** `blockchain/precision.py` (`PRECISION`,
  `LOG_PRECISION`, `Q96`, `TICK_BASE`).
- **Общие модели данных:** `blockchain/positions.py` (`Position`),
  `blockchain/token_balances.py` (`TokenBalances`); `strategy.Position`
  сохранён как реэкспорт для совместимости.
- **Единое подключение к RPC:** `blockchain.rpc.connect()` проверяет соединение
  и `chain_id`; используется `monitor_position.py` и скриптами вместо
  повторяющихся проверок.
- **Конфигурация без float:** `config.load_config()` возвращает `Decimal` для
  `range_half_width` и `fee_threshold_usd`, ищет `config.yaml` рядом с модулем и
  поддерживает необязательный `weth.address`.
- **Скрипты перенесены в `scripts/`:** `monitor_pool.py`, `list_positions.py`
  (только чтение) и `wrap_weth.py`, `approve_weth.py`, `mint_position.py`
  (транзакции, требуют `PRIVATE_KEY`). У них есть `main()`, argparse и никаких
  побочных эффектов при импорте.
- **Документация:** README обновлён до v0.3.5 со структурой проекта.

## Явно исправлено

- `monitor_position.py` больше не подставляет спот-цену пула вместо
  отсутствующего `oracle.token1_usd_feed`, а завершает работу с понятной ошибкой.
- Удалена мёртвая функция `tick_to_price` из скрипта монитора.
- `storage/sqlite_store.py` больше не наследуется от протоколов; протоколы в
  `storage/interfaces.py` стали `runtime_checkable` и описывают реальные
  сигнатуры возвращаемых значений.

## Ограничения

- Полный автоматический ребалансер не реализован.
- `strategy.mode` пока только читается конфигурацией и не влияет на поведение.

## Технологии

- Python 3.14
- Web3.py 7.x
- PancakeSwap V3
- Base / Base Sepolia
- Pytest

## Следующий этап

Реализация полного цикла ребалансировки: сбор комиссий, закрытие позиции,
обмен, открытие новой позиции.
