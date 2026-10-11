# loglens

ログファイルのレベル別件数を集計する CLI。

## 使い方

    python3 loglens.py count app.log
    python3 loglens.py count app.log --level ERROR
    python3 loglens.py count app.log --since 09:00:00 --until 17:30:00

`--level` は ERROR / WARN / INFO / OTHER のいずれかを指定します。

`--since` / `--until` は `HH:MM:SS` 形式で時刻範囲を指定します（両端を含む）。
どちらか一方だけの指定も可能です。範囲を指定した場合、タイムスタンプを
持たない OTHER の行は集計対象外になります。

## JSON Lines 入力

拡張子が `.jsonl` のファイルは JSON Lines（1行 = 1つの JSON オブジェクト）として読み込みます。

    python3 loglens.py count app.jsonl
    python3 loglens.py count app.jsonl --level ERROR --since 09:00:00

各行は `"timestamp"`（`2026-07-18 09:12:01` 形式）、`"level"`（ERROR / WARN / INFO）、
`"message"`（文字列）のキーを持ちます。JSON として不正な行、キーが欠けた行、
レベルが3種以外の行は OTHER として数えます。空行はスキップします。
`--level` / `--since` / `--until` はテキスト形式と同じ挙動で併用できます。

## 複数ファイル入力

`count` には複数のファイルを渡せます。全ファイルの件数を合算し、1つの集計として
従来と同じ形式で表示します（ファイル別の内訳は表示しません）。

    python3 loglens.py count a.log b.jsonl
    python3 loglens.py count a.log b.jsonl --level ERROR --since 09:00:00

`.log` と `.jsonl` は混在でき、形式はファイルごとに拡張子で判定します。
`--level` / `--since` / `--until` はすべてのファイルに適用されます。
存在しないファイルが含まれる場合はエラーを表示して終了コード 1 で終了します。

## 頻出メッセージ上位表示

`--top N` を付けると、レベル別集計の後にメッセージの出現件数の上位 N 件を
「件数 メッセージ」の形式で1行ずつ表示します。

    python3 loglens.py count app.log --top 3
    python3 loglens.py count a.log b.jsonl --top 5 --level ERROR --since 09:00:00

件数が同じメッセージはログで先に出現した順に並びます。N がメッセージの種類数より
大きい場合はある分だけ表示します。N には1以上の整数を指定します。
`--level` / `--since` / `--until` / `.jsonl` 入力 / 複数ファイルと併用でき、
絞り込み後の行を集計対象とします（`--level` 指定時はそのレベルの行のみ）。
OTHER の行（形式外の行）は集計に含めません。

## JSON 出力

`--format json` を付けると、集計結果を JSON オブジェクト1つ（インデント2）で出力します。
既定は `--format text` で、従来の表示と変わりません。

    python3 loglens.py count app.log --format json
    python3 loglens.py count a.log b.jsonl --format json --top 3 --since 09:00:00

キーは `"counts"`（ERROR / WARN / INFO / OTHER の件数）、`"total"` の順で、
`--top N` 併用時は最後に `"top"`（`{"count": 件数, "message": "メッセージ"}` の上位順リスト）を追加します。

    {
      "counts": {
        "ERROR": 3,
        "WARN": 4,
        "INFO": 11,
        "OTHER": 2
      },
      "total": 20
    }

`--level` / `--since` / `--until` / `.jsonl` 入力 / 複数ファイルと併用でき、絞り込み・合算後の
集計結果を出力します。`--level` 指定時は `"counts"` にそのレベルだけを入れ、`"total"` はその件数です。

## CSV 出力

`--format csv` を付けると、集計結果を CSV で出力します。1行目はヘッダ `level,count` で、
以降に ERROR / WARN / INFO / OTHER / TOTAL の順で「レベル,件数」を出力します。

    python3 loglens.py count app.log --format csv
    python3 loglens.py count a.log b.jsonl --format csv --top 3 --since 09:00:00

`--top N` 併用時は空行を1行おき、ヘッダ `count,message` に続けて上位順に「件数,メッセージ」を出力します。
カンマや引用符を含むメッセージは標準の CSV 引用ルール（ダブルクォート囲み）で出力します。

    level,count
    ERROR,3
    WARN,4
    INFO,11
    OTHER,2
    TOTAL,20

`--level` / `--since` / `--until` / `.jsonl` 入力 / 複数ファイルと併用でき、絞り込み・合算後の
集計結果を出力します。`--level` 指定時はそのレベルの行と TOTAL 行（その件数）だけを出力します。

## 正規表現フィルタ

`--regex PATTERN` を付けると、メッセージ部分が Python の正規表現 PATTERN に一致する行だけを
集計対象にします（`re.search` による部分一致・大文字小文字は区別）。

    python3 loglens.py count app.log --regex "timeout|refused"
    python3 loglens.py count a.log b.jsonl --regex "^GET" --top 3 --format json

メッセージを持たない OTHER の行（形式外の行）は、`--regex` 指定時は集計対象外になります。
`--level` / `--since` / `--until` / `--top` / `--format json` / `--format csv` / `.jsonl` 入力 /
複数ファイルと併用でき、すべての絞り込みを満たす行だけを集計します。
不正なパターンを指定した場合は、パターンと理由を標準エラーに表示して終了コード 2 で終了します。

## 時間帯別集計

`--stats` を付けると、レベル別集計の後に空行を1行おき、行が1件以上ある時間帯だけを
「HH時 N件」の形式（HH は 00〜23 の2桁）で時刻順に表示します。

    python3 loglens.py count app.log --stats
    python3 loglens.py count a.log b.jsonl --stats --level ERROR --since 09:00:00

対象は `--level` / `--since` / `--until` / `--regex` の絞り込み適用後の行で、タイムスタンプを
持たない OTHER の行は時間帯集計に含めません。`--format json` と併用すると、`"stats"`
キー（`{"HH": 件数}` 形式・出現した時間帯のみ・時刻順）を出力の最後に追加します。
`--format csv` との併用は非対応で、エラーを標準エラーに表示して終了コード 2 で終了します。
`--stats` を指定しない場合の出力は変わりません。

## ファイル書き出し

`--output PATH` を付けると、標準出力に出すはずの内容（`--format text` / `json` / `csv` すべて）を
そのまま PATH に書き出し、標準出力には `wrote: PATH` の1行だけを表示します。

    python3 loglens.py count app.log --output result.txt
    python3 loglens.py count app.log --format json --output result.json

書き出しは UTF-8・末尾に改行ありで、既存ファイルは上書きします。PATH の親ディレクトリが
存在しない場合はエラーを標準エラーに表示して終了コード 2 で終了します。
`--output` を指定しないときの出力は従来と変わりません。
