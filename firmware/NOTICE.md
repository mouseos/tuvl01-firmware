# メーカー製binary

これらはSH726A applicationとは別のチップで使用するデータです。
ビルド時にhashを確認してimageへ組み込みます。ビルドに外部SPI dumpは不要です。

TUVL01標準ファームのSPI NOR（S25FL164K）に入っているデータです。MIT licenseの対象外です。

## MT5931

`mt5931.bin`はMT5931内部へロードするradio firmwareです。

- サイズ: 136576B
- SHA256: `06d43badbb669700c7cf94924c43a40779b428f3ceec8756813b0aaec2b4a68d`
- CRC32: `1061bd8e`
- MT5931転送先: `0xff900000`
- 標準ファームのSPI内`0x103650`にそのまま存在します（`tools/extract_vendor.py`が同じ位置から取り出します）。

ホスト側MT5931ドライバのソースは、このbinary自体のソースではありません。

## MN885521

`mn885521-pseq.bin`は内部へ転送するPSEQパッチ30レコードです。
内部ROM全体やSH726A用実行コードではありません。
各レコードは開始位置2B、payload、期待パリティ1Bです。
`mn885521-pseq.json`に転送先bank、境界、hashを記載します。

- サイズ: 4341B（payload合計4251B）
- SHA256: `fb67866165fedb7eceea6a4f26fc797314f2ef8f3a7d1f7bb730dc6ecc651751`
- 標準ファームのSPI内`0xffe94`にそのまま存在します。

ビルド時に検証してC表現へ変換します。I2C転送・検査は独立MCU側のC実装です。
