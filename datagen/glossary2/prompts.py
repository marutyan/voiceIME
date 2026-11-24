"""用語集v2を教師LLMで作るためのプロンプトと、候補を集める分野の一覧。

段階は3つ：分野を細かい話題に分けさせる（TOPICS）、話題ごとに用語を挙げさせる（GEN）、
公開の一覧から取った種とLLMが挙げた語をまとめて見直させる（REVIEW）。
"""

# 候補を挙げさせる分野（分野の説明 → 用語集のcategory）。課題で指定された分野を、話題に分けやすい大きさで並べる。
# 各分野を教師LLMに細かい話題へ分けさせ、話題ごとに用語を挙げさせる。
AREAS: dict[str, str] = {
    # ML・CV・NLP・音声の研究
    "物体検出（DETR系、YOLO系、R-CNN系、アンカー、マッチング、NMS、補助損失、評価指標を含む）": "ml-research",
    "歩行者検出・群衆の検出・人物の再識別・追跡（データセット、手法、Miss Rateなどの指標）": "ml-research",
    "画像分類と画像の基盤モデル（CNN、ViT、自己教師あり学習、CLIP系）": "ml-research",
    "セグメンテーション（セマンティック、インスタンス、パノプティック、SAM系）": "ml-research",
    "3次元ビジョン（点群、深度推定、NeRF、Gaussian Splatting、SLAM、SfM）": "ml-research",
    "動画理解・動作認識・姿勢推定・顔認識": "ml-research",
    "画像生成と動画生成（拡散モデル、GAN、VAE、フローマッチング、制御の手法）": "ml-research",
    "自動運転とロボティクスの研究（BEV、Occupancy、模倣学習、VLA）": "ml-research",
    "大規模言語モデルのモデル名とモデルの系列（オープンと商用）": "ml-research",
    "LLMの学習手法（事前学習、指示チューニング、RLHF、DPO、PEFT、LoRA系）": "ml-research",
    "LLMの推論・高速化・量子化・サービング（KVキャッシュ、投機的デコード、GPTQ、AWQ）": "ml-research",
    "RAG・エージェント・プロンプトの手法とフレームワーク": "ml-research",
    "自然言語処理の古典的な手法とモデル（word2vec、BERT系、系列ラベリング、構文解析）": "ml-research",
    "マルチモーダルモデル（VLM、画像と言語、音声と言語）": "ml-research",
    "音声認識・音声合成・話者認識・音声処理のモデルと手法": "ml-research",
    "強化学習のアルゴリズムと環境": "ml-research",
    "グラフニューラルネットワークと推薦システム": "ml-research",
    "時系列予測・異常検知・表形式データの機械学習（GBDT系を含む）": "ml-research",
    "ニューラルネットワークの層・ブロック・アーキテクチャの部品": "ml-research",
    "活性化関数・正規化・初期化・正則化の手法": "ml-research",
    "損失関数の名前（検出、分類、距離学習、生成、蒸留）": "ml-research",
    "最適化手法・学習率スケジューラ・学習の安定化の手法": "ml-research",
    "評価指標の名前と略語（分類、検出、セグメンテーション、生成、NLP、音声、検索）": "ml-research",
    "画像・動画・3次元・自動運転のデータセットとベンチマーク": "ml-research",
    "NLP・LLM・コードのデータセットとベンチマーク": "ml-research",
    "音声・マルチモーダル・その他のデータセットとベンチマーク": "ml-research",
    "機械学習の学習の枠組み（転移学習、メタ学習、連合学習、継続学習、ドメイン適応）の手法名": "ml-research",
    "説明可能性・頑健性・敵対的攻撃・公平性の手法": "ml-research",
    "ハイパーパラメータ探索・AutoML・実験管理のツールと手法（Optunaなど）": "ml-research",
    "機械学習・CV・NLP・音声の国際会議、論文誌、ワークショップ、論文の投稿と査読の仕組み": "ml-research",
    "数学・統計・最適化で英字のまま書く語と略語（KL、SVD、PCA、MCMC、ELBOなど）": "ml-research",
    "分散学習と大規模学習の技術（データ並列、ZeRO、FSDP、Megatron）": "ml-research",
    "PyTorch・TensorFlow・JAXのクラス名・関数名・モジュール名": "ml-research",
    "Hugging Faceのライブラリとクラス名、モデルハブの用語": "ml-research",
    # プログラミング
    "プログラミング言語とその処理系・方言": "programming",
    "Pythonの標準ライブラリのモジュール名と関数名": "programming",
    "Pythonの人気ライブラリ（Web、CLI、非同期、テスト、データ処理、可視化）": "programming",
    "JavaScriptとTypeScriptのフレームワーク・ライブラリ・ランタイム": "programming",
    "Reactのエコシステム（フック名、状態管理、ルーティング、UIライブラリ）": "programming",
    "Webフロントエンドのビルドツール・CSSフレームワーク・テストツール": "programming",
    "Rustのクレートとツール": "programming",
    "Goのパッケージとツール": "programming",
    "SwiftとAppleのフレームワーク（SwiftUI、UIKit、Combine、Core ML など）": "programming",
    "Java・Kotlin・C#・C++のフレームワークとライブラリ": "programming",
    "データ処理・科学計算・可視化・ノートブックのツール": "programming",
    "パッケージ管理・ビルド・依存関係の管理のツール": "programming",
    "Unix・Linuxのコマンドとシェルの組み込みコマンド": "programming",
    "Gitのコマンドとサブコマンド、GitHubとGitLabの機能": "programming",
    "エディタ・IDE・ターミナル・開発者向けのアプリ": "programming",
    "テスト・Lint・フォーマッタ・型検査・静的解析のツール": "programming",
    "ソフトウェア開発の英字で書く慣用語と略語（pull request、rebase、CI/CD、LGTM、WIPなど）": "programming",
    "Web技術の規格・プロトコル・データ形式・API（HTTP、REST、GraphQL、WebSocket、JSON）": "programming",
    "文字コード・ファイル形式・画像や動画や音声の形式とコーデック": "programming",
    "設計手法・アーキテクチャパターン・開発手法の英字で書く略語（DDD、TDD、MVC、SOLID）": "programming",
    "モバイルアプリとデスクトップアプリの開発技術": "programming",
    "ゲームエンジン・グラフィックスAPI・GPUプログラミング（CUDA、Vulkan、Metal、Unity）": "programming",
    # クラウドとインフラ
    "AWSのサービス名": "cloud-infra",
    "Google Cloudのサービス名": "cloud-infra",
    "Microsoft Azureのサービス名": "cloud-infra",
    "その他のクラウドとPaaS（Cloudflare、Vercel、Netlify、Fly.io、さくらのクラウドなど）": "cloud-infra",
    "コンテナ・Kubernetesとそのエコシステム（リソースの種類、ツール）": "cloud-infra",
    "CI/CD・インフラのコード化・構成管理のツール": "cloud-infra",
    "データベース・検索エンジン・キャッシュ・ベクトルデータベース": "cloud-infra",
    "データ基盤・ETL・ストリーム処理・ワークフロー管理のツール": "cloud-infra",
    "監視・ログ・可観測性・インシデント対応のツール": "cloud-infra",
    "ネットワークのプロトコルと略語": "cloud-infra",
    "セキュリティ・認証・暗号の規格と略語とツール": "cloud-infra",
    "OS・Linuxディストリビューション・仮想化・ファイルシステム": "cloud-infra",
    "HPC・GPUクラスタ・ジョブ管理（Slurm、InfiniBand、NCCL）": "cloud-infra",
    "MLOpsとモデル配信の基盤（Kubeflow、MLflow、Triton、Ray）": "cloud-infra",
    # IT製品・企業
    "AIの企業・研究所・スタートアップの名前": "it-products",
    "生成AIのサービスとアプリ（チャット、画像生成、コーディング支援、音声）": "it-products",
    "IT企業・半導体企業・ハードウェア企業の名前": "it-products",
    "GPU・CPU・アクセラレータ・チップの製品名と型番": "it-products",
    "パソコン・スマートフォン・タブレット・周辺機器の製品名": "it-products",
    "OS・ブラウザ・オフィスソフト・一般のアプリ": "it-products",
    "チャット・会議・プロジェクト管理・文書のSaaS": "it-products",
    "開発者向けのWebサービスとSaaS（ホスティング、決済、認証、メール送信）": "it-products",
    "動画・音楽・SNS・ニュース・技術情報のWebサービス": "it-products",
    "IT・電子機器の規格と略語（USB、Wi-Fi、HDMI、NVMe、Bluetooth）": "it-products",
}

# 分野1つあたりに作らせる細かい話題の数と、話題1つあたりに挙げさせる用語の数。
# 80分野 × 25話題 × 50語 = 約10万の候補になり、重複と見直しの後に3〜5万語を残す見込み。
N_TOPICS_PER_AREA = 25
N_TERMS_PER_TOPIC = 50

TOPICS_SYSTEM = """あなたは日本のソフトウェアエンジニアと機械学習の研究者が使う技術用語に詳しい編集者です。
音声入力ソフトの用語集を作るため、分野を細かい話題に分けます。
出力は、話題を表す短い日本語の文字列を並べたJSON配列だけにする。前置きや説明は書かない。"""

TOPICS_USER = """次の分野を、互いに重ならない細かい話題に{n}個分けてください。
各話題は、その話題の中で英字の用語を50個ほど挙げられる程度の広さにしてください（広すぎず、狭すぎず）。
話題の例として、代表的な用語を括弧で2〜3個添えてください。

分野：{area}"""

# 話題の2回目の依頼で足す文。1回目の話題を示し、重ならない別の話題を挙げさせる。
TOPICS_USER_MORE = """

次の話題はすでに使いました。これらと重ならない別の話題を挙げてください：
{known}"""

GEN_SYSTEM = """あなたは日本のソフトウェアエンジニアと機械学習の研究者が使う技術用語に詳しい編集者です。
音声入力ソフトの用語集を作っています。日本語の文の中でも英字で書くのが普通の技術用語を集め、日本人のエンジニアが実際に口にする読みをカタカナで付けます。

規則：
- 用語は、日本語の文中でも英字で書くのが普通の語だけにする（製品名、サービス名、ライブラリ名、コマンド名、略語、手法やモデルやデータセットの固有名、クラス名、論文や開発で英字のまま書く専門用語の句）。
- 「データ」「モデル」「サーバー」「ファイル」「リスト」のように、日本語の文中で普通カタカナで書く外来語は入れない。
- 表記（surface）は公式の綴りと大文字小文字にする（例：PyTorch、iPhone、macOS、scikit-learn、Hungarian Matching）。
- 読み（readings）は、日本人が会話で実際に言う形をカタカナで書く。複数の言い方が広く使われていれば全部書く（例：YOLO → ["ヨーロー", "ヨロ"]、SQL → ["エスキューエル", "シークエル"]）。
- 略語をアルファベット1文字ずつ読む場合は、その通りに書く（例：CNN → ["シーエヌエヌ"]、AWS → ["エーダブリューエス"]）。
- 数字を含む場合は、実際の言い方で書く（例：GPT-4 → ["ジーピーティーフォー"]、H100 → ["エイチヒャク"]）。
- 読みにはカタカナと長音「ー」だけを使い、スペースや中黒「・」を入れない。
- 実在する語だけを書く。存在を確信できない語は書かない。

出力は、次の形のオブジェクトを並べたJSON配列だけにする。前置きや説明は書かない。
{"surface": "PyTorch", "readings": ["パイトーチ"]}"""

GEN_USER = """次の話題について、日本のエンジニアや研究者が会話、チャット、文書で使う英字の用語を{n}個挙げてください。
有名なものから、その分野の人なら知っている専門的なものまで含めてください。

分野：{area}
話題：{topic}"""

# 2回目の依頼で足す文。1回目にその話題で挙がった語を示し、別の語を挙げさせる。
GEN_USER_MORE = """

この話題では次の語をすでに集めました。これら以外の語を挙げてください（より専門的な語、派生した手法やモデル、関連するツールやデータセットなど）：
{known}"""

REVIEW_SYSTEM = """あなたは日本のソフトウェアエンジニアと機械学習の研究者が使う技術用語に詳しい校閲者です。
音声入力ソフトの用語集の候補を見直します。候補は公開の一覧（パッケージ名、モデル名、データセット名など）や、別のAIが挙げた語です。各候補について次を判断してください。

1. keep：次をすべて満たすなら true。
   - 実在する（存在を確信できない、架空の可能性がある語は false）。
   - 日本のエンジニアや研究者が、会話、チャット、文書でその名前を口にしたり書いたりすることがある程度に知られている（一覧にあっても、依存関係として入るだけで話題にならない内部のパッケージ、型定義だけのパッケージ、個人のモデルやデータセットなどは false）。
   - 技術、IT、研究に関する語である。
2. surface：日本語の文中でその語を書くときの表記。公式の綴りと大文字小文字にする。パッケージ名やリポジトリ名やモデルのIDは、文中で呼ぶ名前にする（例："meta-llama/Llama-3.1-8B-Instruct" → "Llama 3.1"、"google-bert/bert-base-uncased" → "BERT"、"facebook/detr-resnet-50" → "DETR"）。
3. readings：日本人のエンジニアが会話で実際に言う読みをカタカナで全部（1〜4個）。カタカナと長音「ー」だけを使う。略語を1文字ずつ読む場合はその通りに書く（例：CNN → "シーエヌエヌ"）。数字は実際の言い方で書く。候補に読みの案があっても、不自然なら直す。
4. style：日本語の文の中でどう書くのが普通か。
   - "latin"：ほぼ必ず英字で書く（例：PyTorch、AWS、iPhone、DataLoader、CNN、Hungarian Matching）。
   - "either"：英字でもカタカナでも普通に書かれる（例：Docker／ドッカー、Linux／リナックス）。
   - "katakana"：日本語の文の中では普通カタカナや日本語で書く（例：Data／データ、Server／サーバー、Batch Normalization／バッチ正規化、Commit／コミット）。
5. kind：
   - "name"：製品、サービス、ライブラリ、ツール、企業、モデル、手法、データセット、ベンチマーク、学会、規格などの固有の名前。
   - "abbrev"：略語・頭字語（例：CNN、API、IoU）。
   - "code"：コードやコマンドに現れる識別子（クラス名、関数名、コマンド名、引数名。例：DataLoader、useEffect、grep）。
   - "term"：固有の名前ではないが、技術分野で英字のまま書くことが多い専門用語の句（例：Hungarian Matching、auxiliary loss、pull request、Average Precision）。
   - "common"：一般の英単語や、日本語の文では普通訳語やカタカナで書く語（例：Approve、State、Reviewer、Distributed Training）。
6. category：
   - "ml-research"：機械学習・画像認識・音声・NLPの研究（モデル、手法、指標、損失、データセット、学会、数学の語、機械学習のライブラリ）
   - "programming"：プログラミング言語、ライブラリ、フレームワーク、開発ツール、コマンド、コードの識別子、開発の慣用語
   - "cloud-infra"：クラウドのサービス、インフラ、ネットワーク、データベース、OS、運用のツール
   - "it-products"：一般のIT製品、サービス、アプリ、ハードウェア、企業
7. fame：知られている程度。1：分野を問わずエンジニアの多くが知っている。2：その分野の人なら知っている。3：一部の専門家だけが知っている。

出力は、入力と同じ順で、入力の番号 i を付けた次の形のオブジェクトを並べたJSON配列だけにする。前置きや説明は書かない。
{"i": 0, "keep": true, "surface": "PyTorch", "readings": ["パイトーチ"], "style": "latin", "kind": "name", "category": "ml-research", "fame": 1}"""

REVIEW_USER = """次の候補を見直してください。hint は候補の出どころです。

{items}"""

GENERAL_SYSTEM = """あなたは日本語とIT技術の両方に詳しい校閲者です。
音声入力ソフトの用語集で、カタカナの読みを聞いたときに英字の用語へ書き換えます。読みが日本語の普通の言葉でもあると、関係のない話まで英字に書き換えてしまいます。
各用語について、その読み（カタカナ）が、日本語の日常の会話や技術の会話で「この用語とは別の意味の普通の言葉」として頻繁に使われるかを判断してください。

- general を true にするのは、その読みを聞いた日本人が、多くの場合この用語ではなく普通の言葉の意味に取るものだけ。
  例：Click（クリック）、Rich（リッチ）、just（ジャスト）、auto（オート）、Edge（エッジ）、Pixel（ピクセル）、Flow（フロー）、Express（エクスプレス）、Timer（タイマー）、Event（イベント）、Result（リザルト）、src（ソース）、Drone（ドローン）、Cloud Storage（クラウドストレージ）、Celery（セロリ）、Perl（パール）、Illustrator（イラストレーター）
- 普通の言葉と同じ綴りの英単語から付いた名前でも、カタカナの読みが日本語の会話で普通の言葉としてはあまり使われないなら false にする。
  例：Transformer（トランスフォーマー）、Whisper（ウィスパー）、Adam（アダム）、YOLO（ヨーロー）、CLIP（クリップ）、BERT（バート）、LoRA（ローラ）、Llama（ラマ）、Kinetics（キネティクス）、Airflow（エアフロー）、Bash（バッシュ）
- 複数の語からなる名前（ROUGE-L、CLIP Embedding、Vanilla Transformer）や、英字を1文字ずつ読む略語（GIL、PP）は、全体の読みが普通の言葉でなければ false にする。
- 判断に迷う場合は false にする。

出力は、入力と同じ順で、入力の番号 i を付けた次の形のオブジェクトを並べたJSON配列だけにする。前置きや説明は書かない。
{"i": 0, "general": false}"""

GENERAL_USER = """次の用語の読みを判断してください。

{items}"""
