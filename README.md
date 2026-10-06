# LP Rebalancer

Local cross-platform agent for one PancakeSwap V3 concentrated-liquidity
position on Base.

## Current stage

Stage 1 only:

- connect to Base Mainnet RPC;
- read chain ID;
- read latest block number;
- fail closed if the connected chain is not Base Mainnet.

No wallet, private key, transaction, pool or LP-position logic exists yet.

## Requirements

- Python 3.11+ recommended
- macOS / Windows / Linux

## macOS / Linux

```bash
cd lp-rebalancer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## Windows PowerShell

```powershell
cd lp-rebalancer
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

## Tests

```bash
pytest -q
```

Expected result:

```text
2 passed
```

## Security

Never commit `.env`, private keys, seed phrases or wallet secrets.
The Stage 1 code does not require a private key.
