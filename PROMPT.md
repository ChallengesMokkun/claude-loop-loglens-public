# loglens 夜間ループ指示書

あなたは loglens の開発セッションです。次の手順を1回だけ実行して
終了してください。

1. `./progress/claude-progress.txt` と `./progress/feature_list.json` を読み、現在地を把握する。
2. `./progress/feature_list.json` のうち id が jsonl-input と multi-file の2件を対象とする。
    両方とも passes:true なら、何も変更せず「DONE」とだけ応答して終了する。
3. 対象のうち passes:false の項目を1つだけ選ぶ。他の項目には着手しない（1ループ1タスク）
4. 選んだ機能を、この指示書の後ろに続く仕様（specs）の該当節に従って実装する。
    テストを先に追加し、`poetry -C src run pytest` が全件通るまで修正する
5. README.md と `./src/loglens.py` の docstring を実装に合わせて更新する
6. `./progress/feature_list.json` の passes を true にし、`./progress/claude-progress.txt` に1行追記して、変更を git commit する

制約:

- placeholder 実装（あとで実装する前提の空実装・ダミー返却）を書かない
- テストコードの改変による見かけの成功を作らない
- 既存機能（count / --level / --since / --until）の挙動を変えない
