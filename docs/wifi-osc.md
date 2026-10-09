# MT5931発振器の待ち時間設定

APを停止した状態で、MT5931へ安定待ち時間0のSET_OSCコマンドを送信できます。
通常起動では自動送信しません。

```sh
python tools/uart.py apstop --port COM3 --log <external-log-path>
python tools/uart.py wifi-osc --port COM3 --log <external-log-path>
```

コマンドはUART byte `0x06`です。AP、peer、AIS接続、待機中の送信がなく、
HIFが正常で全送信creditが戻っている場合だけ受け付けます。
同じapplication実行中に再送しません。失敗時も自動再送しません。

`transferred`はSDIO送信とcredit返却の確認です。設定の読戻し、発振器の
実際の待ち時間、無線速度の改善を示しません。
既存radioへのRAM application置換では設定が残る可能性があります。
設定なしとの比較にはradioの電源再投入が必要です。
