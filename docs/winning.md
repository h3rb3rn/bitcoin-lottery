# Was tun wenn ein Block gefunden wurde?

Wenn `Found Blocks` im Dashboard über 0 steigt, wurden **3.125 BTC + alle Transaktionsgebühren** des Blocks direkt an `MINER_WALLET` gesendet. Der Betrag liegt auf der Bitcoin-Blockchain, permanent und unveränderlich.

## Schritt 1 — Fund bestätigen

Warte auf 100 Confirmations (~16 Stunden). Erst dann sind die Coins ausgebbar.

```bash
# Aktuellen Stand der Adresse direkt von der Blockchain abfragen
curl -s https://mempool.space/api/address/<MINER_WALLET> | python3 -m json.tool

# Oder im Browser:
# https://mempool.space/address/<MINER_WALLET>
```

Im Dashboard unter „Gefundene Blöcke" ist der BTC-Kurs zum Fundzeitpunkt dokumentiert — wichtig für die Steuer.

## Schritt 2 — Wallet öffnen

Öffne das Wallet, das den privaten Schlüssel für `MINER_WALLET` kontrolliert. Das Guthaben erscheint dort automatisch sobald der Block bestätigt ist.

| Wallet-Typ | Vorgehen |
|------------|----------|
| **Hardware Wallet** (Ledger/Trezor) | Gerät anschließen, Hersteller-App öffnen |
| **Sparrow / Electrum** | Programm starten, Wallet laden |
| **Seed Phrase** | Seed Phrase in kompatibles Wallet eingeben (niemals online, niemals in Browser-Extensions) |

**Seed Phrase niemals fotografieren, per Cloud synchronisieren oder per Messenger versenden.**

## Schritt 3 — Optionen

### Halten

Nichts tun. Die Coins bleiben sicher in der Wallet. Kurs-Exposure bleibt bestehen.

### Verkaufen via Exchange

1. Account bei einer regulierten Exchange anlegen (Kraken, Bitstamp, Coinbase)
2. KYC (Ausweisverifikation) abschließen — bei Beträgen dieser Größe obligatorisch
3. Deposit-Adresse der Exchange kopieren
4. **Zuerst einen kleinen Testbetrag senden** und bestätigen, dass er ankam
5. Dann den Hauptbetrag senden
6. Auf der Exchange in EUR umtauschen und auf ein Bankkonto auszahlen

Große Beträge nicht in einer einzigen Transaktion senden, falls die Exchange Einzahlungslimits hat.

### Peer-to-Peer verkaufen

Über [Bisq](https://bisq.network) oder [HodlHodl](https://hodlhodl.com) ohne KYC. Für große Beträge komplexer und weniger liquide als eine Exchange.

## Steuerliche Einordnung (Deutschland)

Bitcoin aus Mining gilt in Deutschland als **gewerbliche oder private Einkünfte** — je nach Umfang der Tätigkeit.

| Sachverhalt | Regelung |
|-------------|---------|
| Wert beim Fund | Marktkurs am Tag des Erhalts → Kostenbasis (im Dashboard dokumentiert) |
| Haltefrist < 1 Jahr | Gewinn bei Verkauf steuerpflichtig (Einkommensteuer) |
| Haltefrist ≥ 1 Jahr | Verkauf steuerfrei (§ 23 EStG, Privatpersonen) |
| Gewerblicher Betrieb | Abweichende Regeln, Gewerbesteuer möglich |

Das Dashboard speichert den BTC-Kurs zum Fundzeitpunkt — dieser Wert dient als Nachweis der Kostenbasis gegenüber dem Finanzamt.

**Für verbindliche steuerliche Auskunft einen Steuerberater konsultieren.**

## Sicherheitshinweise

- Keine Informationen über den Fund in sozialen Medien oder öffentlichen Chats teilen — zieht Betrugsversuche an
- Bei Unsicherheit über den Verwahrungsweg einen Bitcoin-erfahrenen Treuhänder oder Anwalt hinzuziehen
- Exchange-Auszahlungen auf bekannte Bankkonten beschränken
