# native USB

SH726A USB0のdevice用EP0 vendor protocolを実装しています。
実機での列挙、転送、実行、永続更新は未確認です。現在の操作経路は[UART](uart.md)です。

## 動作条件

USB peripheral用48MHz clock、DM0/DP0 pin設定、VBUS検出、D+ pull-up制御が必要です。
VBUS readbackだけではclockやD+/D−経路の動作を保証しません。
USBだけでのCPU給電は保証しません。初回試験はバッテリー接続状態を使用します。
board設定は`src/board.c`、初期化とdescriptorは`src/usb.c`を参照してください。
register仕様は[Renesas SH726A/SH726B hardware manual](https://www.renesas.com/en/document/mah/sh726a-group-sh726b-group-users-manual-hardware)が基準です。

## PC側

VID `0xffff`、PID `0x0001`は実験用識別子であり、正式な製品IDではありません。
Windowsは対象deviceにWinUSB、PCツールはPyUSBとlibusbが必要です。
列挙とdriver設定が成立した環境でのみ使用できます。

```powershell
python tools/host.py info
python tools/host.py cycle build/app.img
```

`recover`、`upload`、`save`、`load`、`run`も実装されています。
詳細な引数は`python tools/host.py --help`を参照してください。
`save`はSPIを書き換えます。[image仕様](images-and-recovery.md)の保護範囲を適用します。
handoff時はUSBを再初期化するため、application実行中のsession維持は保証しません。
