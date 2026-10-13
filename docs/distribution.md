# 導入

## SPIプログラマで書込む

1. **最初に元のSPI（S25FL164K、8MiB）を全部読み出して保管します。** 標準ファームへ戻すのに使います。
   読出しは2回行い、2つが一致することを確認してください。
2. 書込みイメージを用意します。次のどちらかです。

   - リリースの`tuvl01-spi-8MiB.bin`を使います。`SHA256SUMS.txt`と照合してください。
   - 自分でビルドします。[ビルド手順](build.md)の環境（WSLのUbuntu、`python3 tools/bootstrap.py`済み）で次を実行します。

   ```powershell
   python tools/build_release.py --out release                 # firmware/ のデータを使う
   python tools/build_release.py 元ダンプ.BIN --out release    # 自分の機体のダンプから取り出して使う
   ```

   `firmware/`のデータはSHA-256を検査し、一致しなければ止まります。ダンプを渡した場合はそこから取り出します。
   単独起動版（`make AUTOSERVE=1`）をビルドし、loaderとapplicationの位置・CRC、単独起動版であることを検査してから、
   `release/tuvl01-spi-8MiB.bin`と`SHA256SUMS.txt`（あれば`BonDriver_TUVL01.dll`も）を出力します。
3. `tuvl01-spi-8MiB.bin`をS25FL164Kへ、チップ全体に書込みます。**読み戻して、書込んだイメージと一致することを確認します。**
4. 組み立てて電源を入れます。約25秒でAPが上がります。LEDは、起動中が赤、待機中（未接続）が緑のゆっくりした点滅、接続中が緑の点灯です。
5. PCのWi-Fiを`TUVL01`（open）へ接続し、TVTestを`BonDriver_TUVL01.dll`で起動します（[チューナー](tuner.md)）。

標準ファームのSPIで中身があるのは、loader領域（先頭8KiB）と標準アプリ（`0x40000`以降）だけです。
8MiB全体を置き換えると標準アプリは消えます。標準ファームに戻すときは、保管した元ダンプを書き戻します。

## UARTで更新する

本ファームのloaderが入っている機体では、UARTでapplicationを入れ替えられます。

```powershell
python tools/uart.py recover --port COMx --log logs/update.bin
python tools/uart.py upload --port COMx --image app-autoserve.img --log logs/update.bin
python tools/uart.py save --port COMx --log logs/update.bin
```

loaderは電源投入後5秒以内にUARTへ1バイト受信すると、待機に残ります（[image仕様](images-and-recovery.md)）。

## 自分の機体のダンプからデータを取り出す

MT5931のradio firmwareとMN885521のPSEQは、標準ファームのSPI内にそのまま入っています。
元ダンプから`firmware/`へ取り出せます（版が違うダンプはSHA-256が一致せず、拒否されます）。

```powershell
python tools/extract_vendor.py 元ダンプ.BIN
```
