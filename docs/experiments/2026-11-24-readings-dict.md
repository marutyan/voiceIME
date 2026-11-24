# 公開辞書からIT用語の特殊読みを集める

12資料から、表記と読みの重複を除いて3,167組を採った。内訳は用語集内の別読み470組と、用語集外の2,697組（2,539語）。用語集外では `POODLE=プードル`、`EBCDIC=エビシディック`、`i.LINK=アイリンク` などを得た。WDICの2資料を集計から外すと386組で、用語集外は168語だった。

種で指定された読みの回収は13/118組（11.0%）、1つ以上の指定読みを回収した表記は13/99語（13.1%）。既存の用語集では、長音符を区別しない比較で種の64組をすでに照合できた。既存分を除いた54組のうち、今回13組（24.1%）を追加した。公開辞書側にあった読みを、既存読みで除外する前に数えると56/118組だった。

種は99語118組。1語に複数の読みがある場合は別々に数えた。出力との比較は表記とカタカナを正規化した後に完全一致で行い、長音符も含めて比較した。入力にした2版は32,873行で、抽出対象の英字表記は重複を除いて31,301語だった。

| 資料 | 採用した組 | 用語集内の組 | 用語集外の組 | 用語集外の語 | 種の組 | 種の語 | 既存読み除外前の種の組 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `neologd` | 236 | 135 | 101 | 93 | 5/118 | 5/99 | 36/118 |
| `sudachidict` | 224 | 121 | 103 | 103 | 5/118 | 5/99 | 37/118 |
| `sudachi-synonyms` | 36 | 23 | 13 | 12 | 0/118 | 0/99 | 2/118 |
| `unidic` | 15 | 6 | 9 | 9 | 0/118 | 0/99 | 6/118 |
| `ipadic` | 0 | 0 | 0 | 0 | 0/118 | 0/99 | 0/118 |
| `alkana` | 7 | 7 | 0 | 0 | 2/118 | 2/99 | 19/118 |
| `jst-thesaurus` | 0 | 0 | 0 | 0 | 0/118 | 0/99 | 0/118 |
| `ipsj-wordlist` | 0 | 0 | 0 | 0 | 0/118 | 0/99 | 0/118 |
| `jmdict` | 106 | 30 | 76 | 70 | 4/118 | 4/99 | 20/118 |
| `skk` | 42 | 9 | 33 | 29 | 2/118 | 2/99 | 17/118 |
| `wdic-tech` | 1,561 | 183 | 1,378 | 1,315 | 3/118 | 3/99 | 18/118 |
| `wdic-telecom` | 1,304 | 113 | 1,191 | 1,136 | 1/118 | 1/99 | 5/118 |

追加できた種は`CSRF=シーサーフ`、`GNU=グヌー`、`GUI=グイ`、`IAM=アイアム`、`IaaS=イアース`、`PNG=ピング`、`PoC=ポック`、`SIGGRAPH=シーグラフ`、`SQL=シークェル`、`Svelte=スベルト`、`chmod=チェンジモード`、`chown=チェンジオウン`、`regex=レジェックス`。種は既存読みとの差分を見つけやすい項目を集めた一覧で、抽出した辞書全体の正しさの測定には使っていない。

`ICLR=アイクリア`、`IJCAI=イジカイ`、`nginx=エンジンエックス`、`K8s=クーバネティス` は今回の出力に含まれない。WDICは2015年版なので、古い規格や製品が多く、新しい研究会議やツールの読みは資料に限りがある。辞書への登録は、現在の発話での頻度や音声入力の精度を示さない。

## 採用条件

1. 元のリポジトリの `glossary.jsonl` と `glossary-v2.jsonl` を読み、同一表記の読みを合わせた。表記と読みをNFKCでそろえ、読みはカタカナに変換して中点と空白を除いた。出力には長音符を残した。既存の音声入力で長音の有無を区別せずに照合するため、長音符の有無だけが違う読みは追加件数から除いた。表記の大小文字だけが異なる場合は、候補が1つに決まるときに用語集の表記を使った。
2. 英字、数字、記号の読みを順につないだだけの候補は除いた。辞書に現れる文字名の揺れや、複数桁の数字を位取りで読む場合も同じ扱いにした。略語の日本語訳や、説明を付け足した読みは除いた。
3. 用語集にない表記には、辞書のITタグ、技術分野の区分、または見出しを確認した記録を求めた。略語、数字・記号を含む綴り、語中の大文字を手がかりとし、ソフトウェア・言語の分類で裏づけられる名前も対象にした。綴りが一致するだけの人名、地名、一般の企業名は除いた。
4. 一般辞書の用語集内の読みは、分野が明示された辞書で同じ読みに当たるか、既存読みと仮名列全体が近い場合に採った。SKKの英字入力による変換は対訳を含むため、分野の裏づけがある組か、個別に確認した組だけを採った。alkanaは用語集内だけに使い、英語の発音を仮名で示した候補は別資料の一致、個別確認、またはFOLDOCの技術見出しとの一致と既存読みの近さを求めた。
5. [個別に確認した組](../../runs/readings-dict/reviewed.tsv)はITで指すものを記録した。[除外した組](../../runs/readings-dict/rejected.tsv)には同綴語、説明の混入、独立した読みとして採る根拠が足りない例を記録した。たとえば、`BSD` の通貨コードを除き、`GNU` はプロジェクトがgを発音すると明記しているので、`ヌー` と `ニュー` を除いた。 [GNUの公式発音](https://www.gnu.org/gnu/pronunciation.html)

## 資料の版と利用条件

すべて2026年11月24日（JST）に取得した。入力ファイルの取得先とSHA-256は[入力一覧](../../runs/readings-dict/inputs.tsv)にある。

| 出力ファイル名 | 資料と版 | 利用条件 | 抽出方法と出典 |
| --- | --- | --- | --- |
| `neologd.jsonl` | mecab-ipadic-NEologd、`abc61e33d8be3d0ead202e6b1df064c72d5ccf11` | Apache-2.0。はてなキーワード等の出典に関する記載を含む | `seed/` のCSVアーカイブ12点の名詞の表記と読み欄を照合。人名・地域・組織を除いた。 [配布元](https://github.com/neologd/mecab-ipadic-neologd/tree/abc61e33d8be3d0ead202e6b1df064c72d5ccf11/seed) [COPYING](https://github.com/neologd/mecab-ipadic-neologd/blob/abc61e33d8be3d0ead202e6b1df064c72d5ccf11/COPYING) |
| `sudachidict.jsonl` | SudachiDict Full、V1、20261015 | Apache-2.0。UniDic・NEologdの出典と条件は `LEGAL` を参照 | Small・Core・NotCoreの3 CSV。見出しが空なら解析用表記を取り、`ReadingForm` を使用。付与された同義語IDのITタグも照合した。 [配布元](https://github.com/WorksApplications/SudachiDict) [CSV仕様](https://github.com/WorksApplications/Sudachi/blob/develop/docs/user_dict_v1.md) [LEGAL](https://github.com/WorksApplications/SudachiDict/blob/830bf9e1313f6f75235ba87ee041e144dbcad8c1/LEGAL) |
| `sudachi-synonyms.jsonl` | Sudachi同義語辞書、`830bf9e1313f6f75235ba87ee041e144dbcad8c1` | SudachiDictと同じApache-2.0 | グループ番号、語彙素番号、語形種別、略語番号が同じ行のうち、英字原綴りと仮名の代表・異表記を結んだ。誤表記と展開無効の行を除いた。 [仕様とライセンス](https://github.com/WorksApplications/SudachiDict/blob/830bf9e1313f6f75235ba87ee041e144dbcad8c1/docs/synonyms.md) |
| `unidic.jsonl` | 現代書き言葉UniDic、MeCab用2.1.2ソース版 | GPL-2.0、LGPL-2.1、修正BSDの選択。ソース同梱の `COPYING` と `BSD` を確認 | `lex.csv` の名詞表記と発音形 `pron`。人名・地名を除いた。 [国立国語研究所・バックナンバー](https://clrd.ninjal.ac.jp/unidic/back_number.html) |
| `ipadic.jsonl` | MeCab IPAdic 2.7.0-20070801 | NAISTの許諾条件とICOT Free Softwareの無保証条項 | 全CSVを照合。採用条件をすべて満たす追加読みは0件だった。 [MeCab配布元](https://taku910.github.io/mecab/) [使用したアーカイブのCOPYING](https://github.com/lindera/mecab-ipadic/blob/2.7.0-20070801/COPYING) |
| `alkana.jsonl` | alkana.py、`34937eb84fc0ac7c7c6482844a2b887c728da681` | GPL-2.0。元データはBilingual Emacspeak Projectの `bep-eng.dic` | `alkana/data.py` の表記と仮名。英語の発音を示す資料なので、単独で日本語の慣用読みを確認できない候補は除いた。 [データ](https://github.com/cod-sushi/alkana.py/blob/34937eb84fc0ac7c7c6482844a2b887c728da681/alkana/data.py) [ライセンス](https://github.com/cod-sushi/alkana.py/blob/34937eb84fc0ac7c7c6482844a2b887c728da681/LICENSE) |
| `jst-thesaurus.jsonl` | 科学技術用語形態素解析辞書、JSTシソーラス2015。CSVは2019-05-17公開分 | CC BY-SA 4.0。MeCab user dictionary for science technology term © National Bioscience Database Center | 計算機科学 `EG01` の項目。仮名の読み欄がなければ自動生成の発音欄も調べた。英字表記の多くが一字読みで、採用は0件だった。 [提供元の説明と利用許諾](https://dbarchive.biosciencedbc.jp/data/mecab/LATEST/README_e.html) |
| `ipsj-wordlist.jsonl` | 情報処理学会 情報入試委員会「情報科全教科書用語リスト」第1版、2024-04-10 CSV | 用語データはCC BY-SA 4.0 | 用語欄に英字と仮名が2表記だけ並ぶ行を解析。対訳または今回の対象外の音写を除くと採用は0件だった。 [公開元](https://sites.google.com/a.ipsj.or.jp/ipsjjn/resources/wordlist) [使用したCSVの配布元](https://github.com/code4fukui/ipsj-words/tree/e5885efb7d2a7f4835f66181eb541946b37a7c77) |
| `jmdict.jsonl` | JMdict 2026-11-23、英語版JSON `3.6.2+20261123231529` | CC BY-SA 4.0。Jim Breen、Electronic Dictionary Research and Development Group | 計算機・電気・電子の意味に属する英字見出しと、その意味・表記に対応する仮名。 [配布版](https://github.com/scriptin/jmdict-simplified/releases/tag/3.6.2%2B20261123231529) [利用許諾](https://www.edrdg.org/edrdg/licence.html) |
| `skk.jsonl` | SKK-JISYO.L、`0a164e6b990c5eb5b59eb7d8789f08865dc2f644` | GPL-2.0-or-later | 仮名キーから英字への変換を優先。英字キーから仮名への組は別資料または個別確認で絞った。 [辞書と著作権表示](https://github.com/skk-dev/dict/blob/0a164e6b990c5eb5b59eb7d8789f08865dc2f644/SKK-JISYO.L) [利用許諾](https://github.com/skk-dev/dict/blob/0a164e6b990c5eb5b59eb7d8789f08865dc2f644/committers.md) |
| `wdic-tech.jsonl` | 「電算用語の基礎知識」、2015年後期版 | 通信用語の基礎知識編纂委員会の独自条件。詳細は下記 | 個人・企業・一般家電の分類を除き、英字見出しと `yomi` 欄を抽出。 [配布とマニュアル](https://www.wdic.org/download.shtml) [Webのポリシー](https://www.wdic.org/policy.shtml) |
| `wdic-telecom.jsonl` | 「通信用語の基礎知識」、2015年後期版 | 通信用語の基礎知識編纂委員会の独自条件。詳細は下記 | 通信プロトコル・技術・電話の分類を対象にした。企業、団体、放送、掲示板などの分類を除き、英字見出しと `yomi` 欄を抽出。 [配布とマニュアル](https://www.wdic.org/download.shtml) [Webのポリシー](https://www.wdic.org/policy.shtml) |

WDICの配布マニュアル `WDICALL.MAN` の「取り扱いについて」では、非営利の転載に版の更新条件があり、インターネット転載には通知を求めている。営利利用には事前連絡が必要とされている。今回の成果物に残したのは表記・読み・項目名と資料名だけで、辞書本文は含めていない。WDIC由来のデータは他資料の採否に使っていない。公開や営利利用に向けた権利者への確認は未実施である。 [配布マニュアル](https://www.wdic.org/file/wdc152.7z)

FOLDOCは一般辞書で同綴語を判断する補助に使った。版はアーカイブの `Dictionary` の更新時刻（2026-07-24 UTC）で記録した。GFDL 1.1以降で、変更不可の節や表紙文の指定はない。技術分類が付いた見出しだけを参照し、英語の発音表記からカタカナは生成していない。 [配布元](https://foldoc.org/source.html) [利用許諾](https://foldoc.org/Free+On-line+Dictionary)

e-Wordsは公開の一括配布を確認できず、会員規約で自動操作を禁じているため取得対象から外した。Jargon Fileの日本語訳は翻訳について明示された利用許諾を確認できなかったため採らなかった。 [e-Words会員規約](https://e-words.jp/p/s-termsofuse.html) [Jargon File日本語訳のソース](https://github.com/solaito/jargon-i18n)

## 再現手順

手元のPCで作業する。元のリポジトリの用語集フォルダと、照合用の種TSVの位置を指定する。WDICのPPMd圧縮はこのMacの `bsdtar` で一部読み出せなかったため、作業用ディレクトリで公式の7-Zip 26.06の `7zz` を使った。読み出した原文はそのままメモリ上で解析する。 [7-Zip公式ダウンロード](https://www.7-zip.org/download.html)

```bash
input_dir=$(mktemp -d /private/tmp/public-readings-dict.XXXXXX)
glossary_dir=../../voiceIME/data/text
seed_tsv=/path/to/seed.tsv
seven_zip=/path/to/7zz

(
  set -e
  while IFS=$'\t' read -r file sha url; do
    curl --fail --silent --show-error --location --max-time 180 \
      --user-agent DictionaryResearch/1.0 --output "$input_dir/$file" "$url"
    printf '%s  %s\n' "$sha" "$input_dir/$file" | shasum -a 256 -c -
    sleep 1
  done < runs/readings-dict/inputs.tsv
)

python3 runs/readings-dict/extract.py \
  --inputs "$input_dir" --seven-zip "$seven_zip" \
  --glossary "$glossary_dir/glossary.jsonl" "$glossary_dir/glossary-v2.jsonl" \
  --seed "$seed_tsv" --output data/text/custom-sources \
  --report runs/readings-dict/counts.json
```

## 無作為抽出

各資料の採用行を表記と読みで整列し、乱数seed `20261124` で最大30件を重複なく抽出した。件数が30件に満たない資料は全件を載せた。「新」は用語集にない表記を示す。

### neologd

| 表記 | 読み | 新 |
| --- | --- | --- |
| `Windows Millennium Edition` | ウィンドウズミレニアムエディション | 新 |
| `DaaS` | ダース | 新 |
| `SunOS` | サンオーエス | 新 |
| `10base5` | テンベースゴ | 新 |
| `ARP` | アープ |  |
| `word2vec` | ワードツーベック |  |
| `WinRT` | ウインアールティー |  |
| `TEEDA` | ティーダ | 新 |
| `ColdFusion` | コールドフュージョン | 新 |
| `jEdit` | ジェイエディット |  |
| `SJIS` | エスジス | 新 |
| `NetBIOS` | ネットバイオス | 新 |
| `Olympus` | オリンポス |  |
| `DOS/V` | ドスブイ | 新 |
| `WHATWG` | ワットダブリュジー |  |
| `Mediator` | メディエイター |  |
| `Mac OS X` | マックオーエステン | 新 |
| `Wi-Fi` | ワィファイ |  |
| `YAML` | ヤメル |  |
| `RAS` | ラス |  |
| `GNU Screen` | ジーエヌユースクリーン |  |
| `AutoCAD` | オウトキャド |  |
| `Windows 2000` | ウインドウズニセン | 新 |
| `UCS-4` | ユーエスシーフォー |  |
| `warez` | ウェアーズ | 新 |
| `RegExp` | レゲックスピー |  |
| `RAM` | ラム |  |
| `Ableton Live` | エイブルトンライヴ |  |
| `CouchDB` | カウチデービー |  |
| `Sendmail` | センドメイル |  |

### sudachidict

| 表記 | 読み | 新 |
| --- | --- | --- |
| `iNTERNET` | インターネット | 新 |
| `Embedding` | エンベッディング |  |
| `TextMate` | テキストメート |  |
| `ACOS` | アコス | 新 |
| `BASIC` | ベーシック | 新 |
| `warez` | ウェアーズ | 新 |
| `Zabbix` | ザッビックス |  |
| `UNDO` | アンドゥ | 新 |
| `DaaS` | ダース | 新 |
| `Shift-JIS` | シフトジス | 新 |
| `Ponte Vecchio` | ポンテヴェキオ |  |
| `QuickTime` | クイックタイム | 新 |
| `ESTABLISHED` | エスタブリッシュド |  |
| `WebObjects` | ウェブオブジェクツ | 新 |
| `PRAM` | ピーラム | 新 |
| `PASCAL` | パスカル | 新 |
| `WinRT` | ウインアールティー |  |
| `SMTP-AUTH` | エスエムティーピーオウス |  |
| `IRIX` | アイリックス | 新 |
| `BlueJ` | ブルージェー |  |
| `VisualWorks` | ビジュアルワークス | 新 |
| `twine` | トゥワイン |  |
| `SPARC` | スパーク | 新 |
| `SJIS` | エスジス | 新 |
| `BROBA` | ブローバ | 新 |
| `E-MAIL` | イーメール | 新 |
| `SunOS` | サンオーエス | 新 |
| `PhpStorm` | ピーエッチピーストーム |  |
| `JavaServer Faces` | ジャバサーバーフェイシィズ | 新 |
| `Ableton Live` | エイブルトンライヴ |  |

### sudachi-synonyms

| 表記 | 読み | 新 |
| --- | --- | --- |
| `MS-DOS` | エムエスドス | 新 |
| `Authorization` | オーソリゼーション |  |
| `DaaS` | ダース | 新 |
| `Internet Explorer` | インターネットエクスプローラー | 新 |
| `WINS` | ウインズ | 新 |
| `OLE` | オーレ |  |
| `Gymnasium` | ギムナジウム |  |
| `SimplE` | シンプル |  |
| `Netscape Navigator` | ネットスケープナビゲーター | 新 |
| `MindMup` | マインドマップ | 新 |
| `W-SIM` | ダブリューシム | 新 |
| `Reflex` | レフレックス |  |
| `Internet Explorer` | インターネットエクスプローラ | 新 |
| `scraper` | スクレーパー |  |
| `suffix` | サフィクス |  |
| `Spinnaker` | スピンネーカー |  |
| `PASCAL` | パスカル | 新 |
| `BROBA` | ブローバ | 新 |
| `Fennel` | フェンネル |  |
| `Volatility` | ボラティリティー |  |
| `Java` | ジャヴァ |  |
| `Ogg` | オッグ |  |
| `Runway` | ランウエイ |  |
| `Makefile` | メークファイル |  |
| `tracing` | トレーシング |  |
| `scraper` | スクレーパ |  |
| `prefix` | プレフィクス |  |
| `Remix` | リミックス |  |
| `Runway` | ランウェー |  |
| `Volatility` | ボラティリティ |  |

### unidic

| 表記 | 読み | 新 |
| --- | --- | --- |
| `TRON` | トロン | 新 |
| `BASIC` | ベーシック | 新 |
| `RISC` | リスク | 新 |
| `AEGIS` | イージス | 新 |
| `Remix` | リミックス |  |
| `UniDic` | ユニディック |  |
| `LOGO` | ロゴ | 新 |
| `POP` | ポップ | 新 |
| `ATIS` | エーティス |  |
| `CASE` | ケース | 新 |
| `JPEG` | ジェーペグ |  |
| `JTAG` | ジェータグ |  |
| `SOHO` | ソーホー | 新 |
| `RAM` | ラム |  |
| `ENIAC` | エニアック | 新 |

### ipadic

採用0件。

### alkana

| 表記 | 読み | 新 |
| --- | --- | --- |
| `regex` | レジェックス |  |
| `ATOK` | エイトック |  |
| `ARP` | アープ |  |
| `RAM` | ラム |  |
| `JavaScript` | ジャヴァスクリプト |  |
| `PostScript` | ポウストゥスクリプト |  |
| `Svelte` | スベルト |  |

### jst-thesaurus

採用0件。

### ipsj-wordlist

採用0件。

### jmdict

| 表記 | 読み | 新 |
| --- | --- | --- |
| `mux` | マックス |  |
| `CardBus` | カードバス | 新 |
| `UPSERT` | アップサート | 新 |
| `AJAX` | エイジャックス |  |
| `ASPI` | アスピー | 新 |
| `iCOMP` | アイコンプ | 新 |
| `UUENCODE` | ユーユーエンコード | 新 |
| `CASE` | ケイス | 新 |
| `SNOBOL` | スノボル | 新 |
| `NetBIOS` | ネットバイオス | 新 |
| `PCDOS` | ピーシードス | 新 |
| `COM` | コム | 新 |
| `NOS` | ノス | 新 |
| `MS-DOS` | エムエスドス | 新 |
| `RIP` | リップ | 新 |
| `EDIFACT` | エディファクト | 新 |
| `AppleTalk` | アップルトーク | 新 |
| `i.LINK` | アイリンク | 新 |
| `SATA` | エスアタ |  |
| `RAS` | ラス |  |
| `ATAPI` | アタピー | 新 |
| `CASE` | ケース | 新 |
| `Scala` | スケーラ |  |
| `NaN` | ナン | 新 |
| `FLOSS` | フロス | 新 |
| `ARPANET` | アルパネット | 新 |
| `RAM` | ラム |  |
| `IaaS` | イアース |  |
| `SIG` | シグ | 新 |
| `ENIAC` | エニアック | 新 |

### skk

| 表記 | 読み | 新 |
| --- | --- | --- |
| `FLOSS` | フロス | 新 |
| `AEGIS` | イージス | 新 |
| `BASIC` | ベーシック | 新 |
| `ELIZA` | イライザ | 新 |
| `RIP` | リップ | 新 |
| `SIG` | シグ | 新 |
| `FAT` | ファット | 新 |
| `RAM` | ラム |  |
| `QuickTime` | クイックタイム | 新 |
| `HaaS` | ハース | 新 |
| `CASE` | ケイス | 新 |
| `PASCAL` | パスカル | 新 |
| `NaN` | ナン | 新 |
| `WINS` | ウインズ | 新 |
| `LAMP` | ランプ | 新 |
| `Java` | ジャヴァ |  |
| `ATOK` | エイトック |  |
| `TeX` | テック |  |
| `LOGO` | ロゴ | 新 |
| `GNU` | グヌー |  |
| `ELIZA` | エリザ | 新 |
| `TRON` | トロン | 新 |
| `POP` | ポップ | 新 |
| `kByte` | キロバイト | 新 |
| `VAN` | ヴァン | 新 |
| `WINS` | ウィンズ | 新 |
| `IAM` | アイアム |  |
| `LAP` | ラップ | 新 |
| `OLE` | オーレ |  |
| `TWAIN` | トウェイン |  |

### wdic-tech

| 表記 | 読み | 新 |
| --- | --- | --- |
| `Fastboot interface` | ファストブートインターフェイスグーグルユーエスビーアイディー | 新 |
| `favicon.ico` | ファビコンドットアイスィーオウ | 新 |
| `.book` | ドットブック | 新 |
| `Android 4.0` | アンドロイドヨンテンゼロ | 新 |
| `exFAT` | イーエックスファット |  |
| `int8_t` | イントハチアンダースコアティー |  |
| `Dolby Digital` | ドルビーディジタル |  |
| `Windows Millennium` | ウィンドウズミレニアム | 新 |
| `RAD` | ラッド | 新 |
| `Registered DIMM` | レジスタードディム | 新 |
| `FAT32` | ファットサンジュウニ |  |
| `xwnmo` | エックスウンモ | 新 |
| `PCI Express Mini Card` | ピースィーアイエクスプレスミニカード | 新 |
| `OpenJane` | オープンジェーン | 新 |
| `WAV` | ワブ | 新 |
| `KERNEL32.DLL` | カーネルサンジュウニドットディーエルエル | 新 |
| `Bourne Shell` | ボーンシェル | 新 |
| `rlogin` | アーログイン |  |
| `#pragma` | シャーププラグマ |  |
| `Win2k` | ウィンニケー | 新 |
| `VirtualDub` | バーチャルダブ | 新 |
| `Asio` | アジオ |  |
| `DynaBook` | ダイナブック | 新 |
| `__float128` | アンダースコアアンダースコアフロートヒャクニジュウハチ | 新 |
| `Photoshop Elements` | フォトショップエレメンツ | 新 |
| `MIW` | ミウ | 新 |
| `ASM` | アスム |  |
| `winipcfg` | ウィンアイピーコンフィグ | 新 |
| `macOS` | マックオウエス |  |
| `Transaction-safe FAT` | トランザクションセーフファット | 新 |

### wdic-telecom

| 表記 | 読み | 新 |
| --- | --- | --- |
| `EMOBILE G4` | イーモバイルジーフォー | 新 |
| `.com` | ドットコム | 新 |
| `10GBASE-LW` | テンギガベースエルダブリュー | 新 |
| `CP50222` | コードページゴーゼロニーニーニ | 新 |
| `image/png` | イメージピング |  |
| `TCP Fast Open` | ティースィーピーファストオプション |  |
| `Ultra3-SCSI` | ウルトラスリースクージ | 新 |
| `DSLAM` | ディーエスラム | 新 |
| `SPDY` | スピーディー | 新 |
| `SDAP` | エスダップ |  |
| `application/xhtml+xml` | アプリケーションエックスエイチティーエムエルプラスエックスエムエル | 新 |
| `IEEE 802.11p` | アイトリプルイーハチゼロニーテンイチイチピー | 新 |
| `Adobe-Japan1` | アドビジャパンイチ | 新 |
| `.asia` | ドットアジア | 新 |
| `audio/vorbis` | オーディオヴォルビス | 新 |
| `application/atom+xml` | アプリケーションアトムプラスエックスエムエル | 新 |
| `6LoWPAN` | スィックスロウパン |  |
| `Cat5e` | カテゴリーファイブイー |  |
| `Snapdragon 200` | スナップドラゴンニヒャク | 新 |
| `ISO-2022-JP-3-compatible` | アイソニーマルニーニージェイピースリーコンパチブル | 新 |
| `100BASE-FX` | ヒャクベースエフエックス | 新 |
| `WiFi` | ワイファイ | 新 |
| `Message-ID` | メッセージアイディー | 新 |
| `audio/x-wav` | オーディオエックスワブ | 新 |
| `IEEE 802.16d` | アイトリプルイーハチゼロニーテンイチロクディー | 新 |
| `AQUOS PHONE es` | アクオスフォンエス | 新 |
| `AVC-LAN` | エイヴィースィーラン | 新 |
| `WMLScript` | ダブリューエムエルスクリプト | 新 |
| `IEEE 802.22` | アイトリプルイーハチゼロニーテンイチイチエイ | 新 |
| `DTCP-IP` | ディーティースィーピーオーバーアイピー | 新 |

## 検証

- 入力16ファイルのSHA-256を照合した。NEologdはアーカイブ内の12個のseedが公式リポジトリのblobと一致した。主な配布アーカイブは一括取得し、手元のCPUで解析した。
- 12ファイルすべてのJSONLについて、フィールド、カタカナ形式、用語集との関係、重複の有無、採用件数、SHA-256を確認した。WDICの無作為抽出60件では、根拠に示した見出しの `yomi` 欄と読みが一致した。
- 同じ入力で出力先を変えて再実行し、JSONLと集計がバイト単位で一致した。出力は合計551,853バイト。コードの構文確認と `ruff check` が通った。
- 抽出結果は [data/text/custom-sources](../../data/text/custom-sources/) にある。既存の `.gitignore` によりGit管理外。集計と採用根拠の照合用データは [counts.json](../../runs/readings-dict/counts.json) にある。
