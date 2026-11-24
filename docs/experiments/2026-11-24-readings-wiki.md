# 日本語版WikipediaとWikidataから集めた技術用語の読み

集めた読みは [wiki.jsonl](../../data/text/custom-sources/wiki.jsonl) にまとめた。抽出コードと照会結果は [runs/readings-wiki](../../runs/readings-wiki/) に保存した。

| 資料 | 読みの組 | 表記 | 既存表記の追加読み | 新規表記の読み | 新規表記 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 日本語版Wikipedia | 5,558 | 5,452 | 231 | 5,327 | 5,238 |
| Wikidata | 427 | 398 | 32 | 395 | 369 |
| 統合後 | 5,881 | 5,742 | 256 | 5,625 | 5,506 |

統合時に重複した読みの組は104件。用語集2ファイルの英字表記は正規化後で31,133件だった。 [集計JSON](../../runs/readings-wiki/summary.json)

## 日本語版Wikipedia

2026年11月24日に、2026年11月1日版の公開ダンプ `jawiki-20261101-pages-articles.xml.bz2` を1接続で取得した。圧縮ファイルは4,782,309,586バイトで、公開SHA-1 `e1a1173c8ae5a844ab5fe89ff457f9c7b178b68d` と一致した。サーバーのCPUで全3,123,022ページを逐次走査した。通常の記事は1,525,534件、転送は958,497件、カテゴリは326,285件だった。中間結果を17,679,830バイトに圧縮して手元に転送し、SHA-256の一致を確認した。 [ダンプの一覧](https://dumps.wikimedia.org/jawiki/20261101/) [公開チェックサム](https://dumps.wikimedia.org/jawiki/20261101/jawiki-20261101-sha1sums.txt)

記事本文の原則はCC BY-SA 4.0とGFDLで、一部にCC BY-SAのみの文章などがある。成果物には表記、読み、根拠の種類、記事名、記事のURLを記録した。記事の本文は保存対象から外した。記事版を抽出できた場合は、該当する旧版へのリンクを記録した。 [ダンプのライセンス](https://dumps.wikimedia.org/legal.html) [Wikimedia Foundation利用規約 §7](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content)

記事名か冒頭の太字にある英字表記について、直後の括弧、明示された読み、仮名の主見出しに併記された英字を拾った。略記の読みとしては、冒頭で略記が明示された一語の製品名などを採った。用語集にある表記はカテゴリを問わず照合し、転送先の同表記や仮名記事名も見た。同名の別対象を避けるため、既存語は記事名またはカテゴリから技術用語と確認できた候補を採った。用語集にない表記は、記事に付いたカテゴリと直上2階層に計算機・ソフトウェア・電子工学などの技術カテゴリがあるものから採った。人物、企業、放送番組、ゲーム作品などは直接付いたカテゴリで除いた。

### 無作為抽出30件

| 表記 | 読み | 用語集 | 根拠 |
| --- | --- | --- | --- |
| `Eclipse` | イクリプス | 既存 | [「Eclipse (統合開発環境)」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=110359849) |
| `Zemax OpticStudio` | ゼマックスオプティックスタジオ | 新規 | [「Zemax OpticStudio」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=101828152) |
| `98NOTE` | キュウハチノート | 新規 | [「98NOTE」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=107153425) |
| `ARROWS Tab FJT21` | アローズタブエフジェイティニーイチ | 新規 | [「FJT21」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=96982730) |
| `Yibit` | ヨビビット | 新規 | [「ヨビビット」（仮名の見出しと併記）](https://ja.wikipedia.org/w/index.php?oldid=102395154) |
| `Disqus` | ディスカス | 新規 | [「Disqus」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=98191768) |
| `Turion II` | テュリオンツー | 新規 | [「Turion II」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=106947016) |
| `Parallels Virtuozzo Containers` | パラレルスバーチュオッゾコンテナ | 新規 | [「Parallels Virtuozzo Containers」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=107522980) |
| `Power.org` | パワードットオーグ | 新規 | [「Power.org」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=108944659) |
| `DocuPortal` | ドキュポータル | 新規 | [「DocuPortal」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=110037700) |
| `NOS:Network Operating System` | ネットワークオペレーティングシステム | 新規 | [「ネットワークオペレーティングシステム」（仮名の見出しと併記）](https://ja.wikipedia.org/w/index.php?oldid=109455818) |
| `Narcissus` | ナルシサス | 新規 | [「Narcissus」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=74944354) |
| `SPOT` | スポット | 新規 | [「スポット (通信機器)」（仮名の見出しと併記）](https://ja.wikipedia.org/w/index.php?oldid=105439806) |
| `GnomeBaker` | グノームベイカー | 新規 | [「GnomeBaker」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=109787050) |
| `Bonjour` | ボンジュール | 新規 | [「Bonjour」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=111446039) |
| `1chipMSX` | ワンチップエムエスエックス | 新規 | [「1チップMSX」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=107278173) |
| `Talby` | タルビー | 新規 | [「Talby」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=110663192) |
| `SolidDB` | ソリッドディービー | 新規 | [「SolidDB」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=81001004) |
| `AxKit` | アックスキット | 新規 | [「AxKit」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=104596547) |
| `docomo NEXT series GALAXY NEXUS SC-04D` | ドコモネクストシリーズギャラクシーネクサスエスシィーゼロヨンディー | 新規 | [「SC-04D」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=107128697) |
| `WebXR Device API` | ウェブエックスアールデバイスエーピーアイ | 新規 | [「WebXR Device API」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=82207928) |
| `OpenMusic` | オープンミュージック | 新規 | [「OpenMusic」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=106511088) |
| `Intel Core M` | インテルコアエム | 新規 | [「Intel Core M」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=108401910) |
| `Apache Axis2` | アパッチアクシスツー | 新規 | [「Apache Axis2」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=110073092) |
| `SignalNow Professional` | シグナルナウプロフェッショナル | 新規 | [「SignalNow Professional」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=103519927) |
| `Ludia` | ルディア | 新規 | [「Ludia」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=108274589) |
| `testbed` | テストベッド | 新規 | [「テストベッド」（仮名の見出しと併記）](https://ja.wikipedia.org/w/index.php?oldid=104457504) |
| `Google Classroom` | グーグルクラスルーム | 新規 | [「Google Classroom」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=106770270) |
| `Blackmagic Fusion` | ブラックマジックフュージョン | 新規 | [「Blackmagic Fusion」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=110259667) |
| `Bonite` | ボニット | 新規 | [「Bonite」（英字の直後）](https://ja.wikipedia.org/w/index.php?oldid=108052167) |

## Wikidata

2026年11月24日17:17〜18:30（JST）に公開のWikidata Query Serviceを照会した。分類ごとの取得を3件の一括照会に分けた。対象外の分類を全体から探索する照会が時間切れになったため、取得済みの英語ラベルと仮名の組に対応する公開ID 869件を4組に分けて再照会した。固定版の識別子は応答に含まれないため、3件の応答と対象外IDの一覧を [取得時のデータ](../../runs/readings-wiki/wikidata-inputs.tar.gz) に保存した。項目のラベル、別名、分類はCC0で再配布できる。 [Wikidataのデータ取得方法とライセンス](https://www.wikidata.org/wiki/Wikidata:Data_access) [公開照会の利用上限](https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual#Query_limits)

ソフトウェア、プログラミング言語、通信プロトコル、ファイル形式などの分類を `P31` で指定した。会議・論文誌・規格は、主題 `P921` に関連分野が設定されたものを照会した。人物・企業・ゲーム作品などとの重複分類を除き、英語ラベルと日本語ラベル・別名を取得した。ローマ字に直した仮名との類似度は、訳語や別製品名が混じるのを減らすために用いた。根拠欄に項目ID、ラベルか別名か、分類ID、項目へのURLを記録した。

### 無作為抽出30件

| 表記 | 読み | 用語集 | 根拠 |
| --- | --- | --- | --- |
| `ZAIKO` | ザイコ | 新規 | [Q111182314「ZAIKO」日本語別名 (P31=Q620615)](https://www.wikidata.org/wiki/Q111182314) |
| `DingTalk` | ディントーク | 新規 | [Q55609616「DingTalk」日本語別名 (P31=Q620615)](https://www.wikidata.org/wiki/Q55609616) |
| `Shiira` | シイラ | 新規 | [Q1149857「Shiira」日本語ラベル (P31=Q6368)](https://www.wikidata.org/wiki/Q1149857) |
| `Abema` | アベマ | 新規 | [Q105741063「Abema」日本語別名 (P31=Q620615)](https://www.wikidata.org/wiki/Q105741063) |
| `Animation:Master` | アニメーションマスター | 新規 | [Q2653036「Animation:Master」日本語ラベル (P31=Q7397)](https://www.wikidata.org/wiki/Q2653036) |
| `Shazam` | シャザム | 新規 | [Q1195495「Shazam」日本語別名 (P31=Q620615)](https://www.wikidata.org/wiki/Q1195495) |
| `Wikibase` | ウィキベース | 新規 | [Q16354758「Wikibase」日本語ラベル (P31=Q1130645)](https://www.wikidata.org/wiki/Q16354758) |
| `Smallworld` | スモールワールド | 新規 | [Q1376225「Smallworld」日本語ラベル (P31=Q7397)](https://www.wikidata.org/wiki/Q1376225) |
| `Cookpad` | クックパッド | 新規 | [Q131319373「Cookpad」日本語ラベル (P31=Q620615)](https://www.wikidata.org/wiki/Q131319373) |
| `Portmap` | ポートマッパー | 新規 | [Q1412477「Portmap」日本語別名 (P31=Q7397)](https://www.wikidata.org/wiki/Q1412477) |
| `mozc` | モズク | 新規 | [Q114801359「mozc」日本語別名 (P31=Q620615)](https://www.wikidata.org/wiki/Q114801359) |
| `NeoOffice` | ネオオフィス | 新規 | [Q1361518「NeoOffice」日本語別名 (P31=Q166142)](https://www.wikidata.org/wiki/Q1361518) |
| `DELISH KITCHEN` | デリッシュキッチン | 新規 | [Q131323271「DELISH KITCHEN」日本語ラベル (P31=Q620615)](https://www.wikidata.org/wiki/Q131323271) |
| `Urbit` | アービット | 新規 | [Q64919023「Urbit」日本語ラベル (P31=Q7397)](https://www.wikidata.org/wiki/Q64919023) |
| `Minecraft data pack` | マインクラフトノデタパ | 新規 | [Q116908523「Minecraft data pack」日本語別名 (P31=Q235557)](https://www.wikidata.org/wiki/Q116908523) |
| `Mesen` | メセン | 新規 | [Q100995275「Mesen」日本語ラベル (P31=Q202871)](https://www.wikidata.org/wiki/Q100995275) |
| `Waze` | ワズ | 新規 | [Q942327「Waze」日本語ラベル (P31=Q620615)](https://www.wikidata.org/wiki/Q942327) |
| `PeerCast` | ピアカス | 新規 | [Q1191945「PeerCast」日本語別名 (P31=Q341)](https://www.wikidata.org/wiki/Q1191945) |
| `Flickr` | フリッカー | 新規 | [Q103204「Flickr」日本語別名 (P31=Q620615)](https://www.wikidata.org/wiki/Q103204) |
| `Baidu Tieba` | バイドゥティエバー | 新規 | [Q837827「Baidu Tieba」日本語別名 (P31=Q620615)](https://www.wikidata.org/wiki/Q837827) |
| `WikiData Remote editor` | ウィキデータリモートエディタ | 新規 | [Q74832502「WikiData Remote editor」日本語ラベル (P31=Q341)](https://www.wikidata.org/wiki/Q74832502) |
| `Taobao` | タオバオ | 新規 | [Q2117484「Taobao」日本語別名 (P31=Q620615)](https://www.wikidata.org/wiki/Q2117484) |
| `Aarogya Setu` | アローギャセツ | 新規 | [Q90565214「Aarogya Setu」日本語ラベル (P31=Q620615)](https://www.wikidata.org/wiki/Q90565214) |
| `Piccoma` | ピッコマ | 新規 | [Q118315782「Piccoma」日本語ラベル (P31=Q620615)](https://www.wikidata.org/wiki/Q118315782) |
| `Panoweaver` | パノウィーヴァー | 新規 | [Q11239337「Panoweaver」日本語別名 (P31=Q166142)](https://www.wikidata.org/wiki/Q11239337) |
| `Archivematica` | アーカイブマティカ | 新規 | [Q37610516「Archivematica」日本語ラベル (P31=Q341)](https://www.wikidata.org/wiki/Q37610516) |
| `Corel Ventura` | コーレルヴェントゥーラ | 新規 | [Q1132555「Corel Ventura」日本語ラベル (P31=Q7397)](https://www.wikidata.org/wiki/Q1132555) |
| `radiko` | ラジコ | 新規 | [Q10859793「radiko」日本語別名 (P31=Q620615)](https://www.wikidata.org/wiki/Q10859793) |
| `Mitsumori Lab` | ミツモリラボ | 新規 | [Q139603414「Mitsumori Lab」日本語ラベル (P31=Q7397)](https://www.wikidata.org/wiki/Q139603414) |
| `Greenfield` | グリーンフィールド | 新規 | [Q105580759「Greenfield」日本語ラベル (P31=Q7397)](https://www.wikidata.org/wiki/Q105580759) |

## 照合と集計

表記の比較ではNFKCで正規化し、大文字小文字と連続空白をそろえた。読みはカタカナにそろえ、空白と中点を外して長音を保った。両用語集に同じ組がある場合と、英数字を一字ずつ読んだ場合を除外した。新規表記からは、OS付属の英単語リストで見つかる一般語だけで構成された表記も除外した。両資料から同じ組を得た場合は、日本語版Wikipediaの根拠を出力に採用した。

種の再現率は、長音を含む正規化済みの組が出力に一致した割合。表記で数える場合は、その表記に示された読みのうち1つ以上が一致すれば1件とした。種は抽出条件に用いず、出力後に照合した。両資料の無作為抽出は、資料内で重複をまとめた後、統合前の候補から固定seed `20261124` で各30件を選んだ。

| 資料 | 表記の再現率 | 読みの組の再現率 | 追加対象の表記 | 追加対象の読みの組 |
| --- | ---: | ---: | ---: | ---: |
| 日本語版Wikipedia | 7/99（7.1%） | 7/118（5.9%） | 7/45（15.6%） | 7/50（14.0%） |
| Wikidata | 1/99（1.0%） | 1/118（0.8%） | 1/45（2.2%） | 1/50（2.0%） |
| 統合後 | 8/99（8.1%） | 8/118（6.8%） | 8/45（17.8%） | 8/50（16.0%） |

種は99表記・118組。うち67組は用語集に登録済みで、1組は一字読みだった。残る50組を追加対象とした。

一致した組は`curl`（カール）、`GUI`（グイ）、`PostgreSQL`（ポスグレ）、`Qt`（キュート）、`SIGGRAPH`（シーグラフ）、`SQL`（シークェル）、`Svelte`（スベルト）、`tuple`（タプル）。 `ICLR`（アイクリア）と `IJCAI`（イジカイ）は今回の出力に一致する組がなかった。 `K8s` には資料にあったクバネティス、クバネテス、クーベネティスを収録した。

Wikidataでは別名に通称や旧名が混じるため、音の類似度で選んだ候補にも表記と読みのずれが残り得る。Wikipediaでは、冒頭以外の説明、未対応のテンプレート、カテゴリ未設定で分野を確認できない記事を取りこぼす。仮名記事への転送は、転送先に冒頭で読みの対応を抽出できた記事を対象にした。新規表記の選別はカテゴリと英単語リストに基づくため、一般語との境界には曖昧さが残る。個々の読みの使用頻度と発音の一致は未検証。

## 検証

ダンプと中間結果のチェックサムを照合した。中間結果 `facts-compact.jsonl.zst` のSHA-256は `ea7a63adf29ec7089b452827742b3dcb2398d19c54e4444e488cf20c53f1655a`。冒頭7構文、転送、カテゴリ、同名、英字の一字読みを入力例で確認した。全出力について5項目の形式、長音を含むカタカナ、重複、既存用語集との一致、一字読み、根拠URLの形式を検査した。保存した入力から2回生成し、JSONLと集計JSONがバイト単位で一致した。検証後、サーバーから取得したダンプを削除した。

## 再実行

ダンプの走査から再実行する場合は、サーバーに新しい作業ディレクトリを作り、公開ダンプと以下の3ファイルを置く。中間結果を再利用する場合は、手元のworktreeでの手順から始める。 [scan_dump.sh](../../runs/readings-wiki/scan_dump.sh) [extract_jawiki.py](../../runs/readings-wiki/extract_jawiki.py) [compact_jawiki.py](../../runs/readings-wiki/compact_jawiki.py)

```sh
nice -n 15 bash scan_dump.sh
nice -n 15 python3 compact_jawiki.py facts.jsonl.gz facts-compact.jsonl.gz
nice -n 15 gzip -dc facts-compact.jsonl.gz | nice -n 15 zstd -q -10 -o facts-compact.jsonl.zst
wc -c facts-compact.jsonl.zst
sha256sum facts-compact.jsonl.zst
```

手元のworktreeでは、サーバーでサイズを確認した中間結果を転送し、Wikidataの取得済み応答を展開する。 `seed_tsv` は受領した種ファイルの絶対パスを指定する。

```sh
input_dir=$(mktemp -d)
main_root=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
scp faculty:voiceime-work-readings-wiki/facts-compact.jsonl.zst "$input_dir/"
shasum -a 256 "$input_dir/facts-compact.jsonl.zst"
zstd -dc "$input_dir/facts-compact.jsonl.zst" | gzip -c > "$input_dir/facts-compact.jsonl.gz"
tar -xzf runs/readings-wiki/wikidata-inputs.tar.gz -C "$input_dir"
mkdir -p data/text/custom-sources
PYTHONPATH=src "$main_root/.venv/bin/python" runs/readings-wiki/build_readings.py \
  --wikipedia "$input_dir/facts-compact.jsonl.gz" \
  --wikidata "$input_dir"/wikidata-{base,technical,research}.tsv \
  --wikidata-excluded "$input_dir/wikidata-excluded.tsv" \
  --glossary "$main_root/data/text/glossary.jsonl" "$main_root/data/text/glossary-v2.jsonl" \
  --seed "$seed_tsv" --english-words /usr/share/dict/words \
  --output data/text/custom-sources/wiki.jsonl --summary runs/readings-wiki/summary.json
```
