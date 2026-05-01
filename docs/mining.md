# Bitcoin Solo Mining — How It Works

## The Lottery Analogy

Bitcoin mining is a computational lottery. Every ~10 minutes the network awards 3.125 BTC (plus transaction fees) to whoever first finds a hash below the current difficulty target. With one NanoFury NF2 at ~2 GH/s against a ~700 EH/s global network:

```
P(win per block) ≈ 2 × 10⁹ / (700 × 10¹⁸) ≈ 3 × 10⁻¹²

Expected wait ≈ 1 / P × 10 min ≈ 11 million years
```

This is done for the lottery experience and the philosophical point that even a single device has a non-zero chance.

## Pool: solo.ckpool.org

This setup uses [ckpool's solo endpoint](https://solo.ckpool.org). It is a pool in name only — it does no share splitting. Every hash you compute is credited fully to you. If you find a block, **you keep 100% of the reward**.

ckpool handles:
- Stratum protocol relay to the Bitcoin network
- Submitting your found block to the network
- Providing a stats dashboard at `https://solo.ckpool.org/?worker=<your-address>`

## What Happens When You Find a Block

1. Your NanoFury produces a valid SHA-256d hash below the current target.
2. BFGMiner submits it to ckpool via the Stratum protocol.
3. ckpool broadcasts the block to the Bitcoin network.
4. The coinbase transaction in that block sends **3.125 BTC + all transaction fees** directly to `MINER_WALLET`.
5. After 100 confirmations (~16 hours), the coins are spendable.
6. The Bitcoin blockchain stores this permanently — no ckpool database, no intermediary.

## Wallet — Where Funds Land

The `MINER_WALLET` in `.env` is a native SegWit (bech32) Bitcoin address (`bc1q...`). **Whoever controls the private key for that address can spend the coins.**

### Getting a Wallet

You need a wallet that gives you full control of your private keys (seed phrase). Options in order of recommendation for self-custody:

| Wallet | Type | Notes |
|--------|------|-------|
| [Sparrow Wallet](https://sparrowwallet.com) | Desktop, full control | Connects to own node or public server; best for privacy |
| [Electrum](https://electrum.org) | Desktop, lightweight | Battle-tested, no full node needed |
| [Bitcoin Core](https://bitcoin.org/en/bitcoin-core/) | Desktop, full node | Most trustless; requires ~600 GB disk |
| Ledger / Trezor | Hardware wallet | Best security; generate address on device |

**Never use an exchange address** (Coinbase, Kraken, etc.) as `MINER_WALLET`. Exchanges control the private key. If you find a block, the coins arrive at the exchange and may be subject to KYC/AML holds.

### Finding Your Address

In any of the above wallets, look for "Receive" → copy the address starting with `bc1q`. Paste it into `.env` as `MINER_WALLET`.

### Checking for Wins

```bash
# Replace with your address
curl -s "https://mempool.space/api/address/bc1q.../txs" | jq '.[].value'
```

Or visit `https://mempool.space/address/<your-address>` in a browser.

## ckpool Stats Dashboard

```
https://solo.ckpool.org/?worker=<MINER_WALLET>
```

Shows submitted shares, estimated hashrate, and any blocks found. The page updates every few minutes.
