# Wi-Fi

## 対応範囲

MT5931をSDIO経由で操作し、同梱radio firmwareをロードします。
open APは単一peer、DHCP、ARP、ICMP echo、UDP echo、TS送信に対応します。
AP側IPは`192.168.74.1`、PCへ割り当てるIPは`192.168.74.2`です。
APに接続するPCを通常のinfrastructure clientとして登録します。Wi-Fi Directのgroup clientには対応しません。
WPA2 stationでの保護されたIP通信は未対応です。

## open AP起動

application実行後に同じUARTポートへ順に実行します。`COMx`は実際のポートへ変更してください。

```powershell
python tools/uart.py wifi --port COMx --log logs/wifi.bin
python tools/uart.py wifi-clock --port COMx --log logs/wifi.bin
python tools/uart.py mac --port COMx --log logs/wifi.bin
python tools/uart.py capability --port COMx --log logs/wifi.bin
python tools/uart.py board --port COMx --log logs/wifi.bin
python tools/uart.py ap --port COMx --log logs/wifi.bin
```

PCのWi-Fi選択から起動したopen APへ接続します。識別情報はUART出力で確認してください。
終了は`python tools/uart.py apstop --port COMx --log logs/wifi.bin`です。
AP・stream停止後にchannelやrateなどの設定を変更します。

`tools/wifi_connect.py`はWindowsで一時接続、DHCP・ping・UDP確認、TS受信、元profileへの復帰を行います。
`--interface`と`--restore-profile`を指定し、詳細は`--help`を参照してください。
既存profileの秘密情報をexportしません。

## radio状態と制限

CPUリセットやloaderへの復帰だけでMT5931が初期状態へ戻るとは限りません。
fresh loadは全136576B転送、download OK、WLAN_READY、driver ownershipを検査します。
already-ready状態は完全reload成功と同一ではありません。
`wifi-restart`はCHIP_RSTとreloadの診断操作です。すべての停止状態からの回復は保証しません。

SDIO command・RX/TX処理はtimeoutとcredit管理を使用します。
radio停止時は未完了commandを繰り返さず、AP/streamを停止して状態を確認してください。
フルセグ転送速度はチューナー取得、SDIO、radio TX、PC受信に依存し、保証値はありません。

## RSN実験機能

wpa_supplicant 2.12のRSN部分をソースからビルドします。
揮発性UART資格情報入力、EAPOL、MT5931鍵コマンド、AIS association試行の接続層を実装しています。
protectionと非zero RSCは未実装です。WPA2/IP接続が成立する機能として使用しないでください。

```powershell
python tools/wpa_uart.py --port COMx --ssid AP_NAME --bssid 02:11:22:33:44:55 --channel 6
python tools/wpa_uart.py --port COMx --join-trial
python tools/wpa_uart.py --port COMx --close
```

BSSIDとchannelは実際のAPを指定します。passwordは対話入力です。
PCでPBKDF2-SHA1によりPMKを作り、OSのentropyを利用します。
資格情報はSPI・通常logへ保存しません。protocol versionは1、targetは7B、credential packetは148Bです。
`--resync`でUART資格情報protocolを同期できます。

radioへの鍵削除転送だけでは削除ACKを確認したことにはなりません。
cleanup未解決の場合はfailure latchで再試行を拒否します。
`--join-trial`は試行後にsessionをcloseし、保護されたdata通信へ移行しません。

## 診断インターフェース

`tools/uart.py --help`に全commandを列挙しています。
`wifi-stats`、`wifi-nic-stats`、`wifi-station-stats`、`wifi-link`は状態確認、
`scan`は受信scan、`wifi-rx-*`は受信診断です。
rate・HT・channel・queue・TX window・polling関連commandは実験用設定です。
運用条件を満たさない変更はtarget側で拒否します。設定選択の成功は通信成功や速度向上を保証しません。

[発振器の待ち時間設定](wifi-osc.md)は、AP停止中に明示的に送る診断commandです。


### TS送信の完了通知

`wifi-ts-feedback`で16datagramごとのTX完了通知要求を切り替えます。
単一フレームとaggregateの双方に対応し、通常は無効です。

```sh
python tools/uart.py wifi-ts-feedback --port COMx --log <external-log-path>
python tools/uart.py wifi-stats --port COMx --log <external-log-path>
```

`requested`は要求数、`completed`は受信した通知数、`pending`は未通知数です。
radio firmwareがdataの通知を返さない場合もあり、通知なしを送信失敗と
断定しないでください。credit返却は無線送信やPC受信の成功を示しません。
aggregateのサンプル枠が満杯でもTS送信は継続します。
