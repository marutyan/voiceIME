"""用語集を教師LLMで作るためのプロンプト。

候補を出させる段階（GEN）と、候補の読みと表記の扱いを見直させる段階（REVIEW）の2段で使う。
"""

# 分野ごとの小分類。小分類ごとに候補を出させ、偏りなく多くの用語を集めるために使う。
SUBAREAS: dict[str, list[str]] = {
    "ml-research": [
        "画像認識・物体検出・セグメンテーションのモデルとアーキテクチャ名（例：ResNet、YOLO、Mask R-CNN）",
        "自然言語処理と大規模言語モデルのモデル名・手法名（例：BERT、GPT-4、LoRA、RLHF）",
        "画像生成・3次元復元・動画のモデルと手法（例：Stable Diffusion、NeRF、Gaussian Splatting）",
        "深層学習の層・活性化関数・正規化・損失関数・最適化手法の英字表記の名前（例：ReLU、LayerNorm、AdamW、Focal Loss）",
        "機械学習と深層学習の英字の略語（例：CNN、RNN、GAN、VAE、MLP、SGD、ViT）",
        "評価指標とその略語（例：mAP、IoU、FID、BLEU、PSNR、F1）",
        "データセットとベンチマークの名前（例：ImageNet、COCO、KITTI、MMLU）",
        "機械学習のライブラリ・フレームワーク・実験管理ツール（例：PyTorch、JAX、timm、Weights & Biases、Hydra）",
        "学会・論文誌・論文サイトと研究コミュニティの名前（例：CVPR、NeurIPS、arXiv、OpenReview）",
        "深層学習の学習と推論の高速化・分散学習・量子化の技術名（例：FSDP、DeepSpeed、FlashAttention、ONNX、TensorRT）",
        "PyTorchやHugging Faceでよく使うクラス名・関数名・引数名（例：DataLoader、nn.Module、AutoTokenizer、state_dict）",
    ],
    "programming": [
        "プログラミング言語（例：Python、Rust、TypeScript、Go）",
        "Webのフロントエンドのフレームワークとライブラリ（例：React、Next.js、Vue、Tailwind CSS）",
        "バックエンドのフレームワークとライブラリ（例：Django、FastAPI、Spring Boot、Express）",
        "データ処理・科学計算のライブラリ（例：NumPy、pandas、Polars、SciPy、Matplotlib）",
        "パッケージ管理・ビルド・実行環境のツール（例：pip、uv、npm、Poetry、Cargo、CMake）",
        "エディタ・IDE・ターミナル・シェル（例：VS Code、Vim、Neovim、zsh、tmux）",
        "バージョン管理とコードレビューのツールと用語（例：Git、GitHub、pull request、rebase、PR）",
        "テスト・Lint・型検査・フォーマッタ（例：pytest、Jest、ESLint、Ruff、mypy）",
        "プログラミングでよく使う英字の略語と書式（例：API、SDK、JSON、YAML、regex、CLI）",
        "コードの中でよく使う英字の識別子・キーワード・メソッド名（例：async、await、useEffect、print、None、self）",
        "モバイルとデスクトップのアプリ開発の技術（例：Swift、SwiftUI、Kotlin、Flutter、Electron）",
    ],
    "cloud-infra": [
        "AWSのサービス名（例：EC2、S3、Lambda、SageMaker）",
        "Google CloudとAzureのサービス名（例：BigQuery、Cloud Run、Vertex AI、Azure Functions）",
        "コンテナとオーケストレーション（例：Docker、Kubernetes、Helm、Podman）",
        "CI/CDとインフラのコード化（例：GitHub Actions、Terraform、Ansible、Argo CD）",
        "データベースとキャッシュとメッセージキュー（例：PostgreSQL、MySQL、Redis、Kafka）",
        "監視・ログ・可観測性のツール（例：Prometheus、Grafana、Datadog、Sentry）",
        "ネットワークとセキュリティの英字の略語とプロトコル（例：DNS、TCP、VPC、SSH、TLS、OAuth）",
        "OS・Linuxディストリビューション・Webサーバー・GPU環境（例：Ubuntu、Nginx、CUDA、Slurm）",
    ],
    "it-products": [
        "AIのチャットとコーディング支援のサービス名（例：ChatGPT、Claude、Gemini、Copilot、Cursor）",
        "チャット・会議・文書作成・業務のSaaS（例：Slack、Zoom、Notion、Figma、Jira）",
        "パソコン・スマートフォン・周辺機器の製品名（例：MacBook、iPhone、iPad、AirPods、ThinkPad）",
        "OS・ブラウザ・一般のソフトウェア名（例：macOS、Windows、Chrome、Safari、Excel）",
        "IT企業・半導体企業の名前で英字で書くもの（例：Google、NVIDIA、OpenAI、Microsoft）",
        "動画・音楽・SNS・Webサービス（例：YouTube、Spotify、X、Discord、Qiita）",
        "GPU・CPU・チップと計算機のハードウェアの製品名（例：A100、H100、RTX 4090、M3 Pro、Ryzen）",
        "クラウドストレージ・パスワード管理・開発者向けWebサービス（例：Google Drive、Dropbox、1Password、Vercel、Hugging Face Hub）",
    ],
}

GEN_SYSTEM = """あなたは日本のソフトウェアエンジニアと機械学習の研究者が使う技術用語に詳しい編集者です。
音声入力ソフトの用語集を作っています。日本語の文の中でも英字で書くのが普通の技術用語を集め、日本人のエンジニアが実際に口にする読みをカタカナで付けます。

規則：
- 用語は、日本語の文中でも英字で書くのが普通の語だけにする（製品名、サービス名、ライブラリ名、略語、手法やモデルの固有名、クラス名など）。
- 「データ」「モデル」「サーバー」「ファイル」のように、日本語の文中で普通カタカナで書く外来語は入れない。
- 表記（surface）は公式の綴りと大文字小文字にする（例：PyTorch、iPhone、macOS、scikit-learn）。
- 読み（readings）は、日本人が会話で実際に言う形をカタカナで書く。複数の言い方が広く使われていれば全部書く（例：YOLO → ["ヨーロー", "ヨロ"]、SQL → ["エスキューエル", "シークエル"]、Kubernetes → ["クバネティス", "クーベネティス", "クーバネティス"]）。
- 略語をアルファベット1文字ずつ読む場合は、その通りに書く（例：CNN → ["シーエヌエヌ"]、AWS → ["エーダブリューエス"]）。
- 数字を含む場合は、実際の言い方で書く（例：GPT-4 → ["ジーピーティーフォー", "ジーピーティーヨン"]、H100 → ["エイチヒャク"]）。
- 読みにはカタカナと長音「ー」だけを使い、スペースや中黒「・」を入れない。
- 実在し、広く使われている用語だけを書く。

出力は、次の形のオブジェクトを並べたJSON配列だけにする。前置きや説明は書かない。
{"surface": "PyTorch", "readings": ["パイトーチ"]}"""

GEN_USER = """次の小分類から、日本のエンジニアや研究者が会話やチャットでよく使う用語を{n}個挙げてください。
有名なものから、やや専門的なものまで含めてください。例に挙げた語以外も多く含めてください。

小分類：{subarea}"""

GEN_USER_EXCLUDE = """

次の語はすでに集めたので、これら以外の語を挙げてください：
{known}"""

REVIEW_SYSTEM = """あなたは日本のソフトウェアエンジニアと機械学習の研究者が使う技術用語に詳しい校閲者です。
音声入力ソフトの用語集の候補を見直します。各用語について次を判断してください。

1. keep：実在し、広く使われている技術用語・製品名なら true。実在が疑わしい、綴りが誤っている、一般の英単語で技術用語として使わない場合は false。
2. surface：公式の綴りと大文字小文字。誤りがあれば直す。
3. readings：日本人のエンジニアが会話で実際に言う読みをカタカナで全部。不自然な読みは消し、よく使われる言い方が抜けていれば足す。カタカナと長音「ー」だけを使う。
4. style：日本語の文の中でどう書くのが普通か。
   - "latin"：ほぼ必ず英字で書く（例：PyTorch、AWS、iPhone、DataLoader、CNN）。
   - "either"：英字でもカタカナでも普通に書かれる（例：Transformer／トランスフォーマー、Docker／ドッカー、Linux／リナックス）。
   - "katakana"：日本語の文の中では普通カタカナで書く（例：Data／データ、Server／サーバー、Fine-tuning／ファインチューニング）。

出力は、入力と同じ順で、次の形のオブジェクトを並べたJSON配列だけにする。前置きや説明は書かない。
{"surface": "PyTorch", "keep": true, "readings": ["パイトーチ"], "style": "latin"}"""

REVIEW_USER = """次の用語の候補を見直してください。

{items}"""

CLASSIFY_SYSTEM = """あなたは日本のソフトウェアエンジニアと機械学習の研究者が使う技術用語に詳しい校閲者です。
各用語について、種類（kind）と分野（category）を判断してください。

kind：
- "name"：製品、サービス、ライブラリ、フレームワーク、プログラミング言語、ツール、企業、モデル、手法、データセット、ベンチマーク、学会、規格などの固有の名前（例：PyTorch、Notion、Flask、ResNet、LayerNorm、ImageNet、CVPR、Docker Compose）。
- "abbrev"：略語・頭字語（例：CNN、API、IAM、mAP）。
- "code"：コードやコマンドに現れる識別子（クラス名、関数名、メソッド名、キーワード、コマンド名、引数名。例：DataLoader、useEffect、async、state_dict）。
- "common"：固有の名前ではない一般の英単語や英語の普通名詞句（例：Approve、State、Stub、Reviewer、Rolling Update、Best Paper Award、Distributed Training、Control Plane）。日本語の文では普通カタカナや日本語で書く。

category：
- "ml-research"：機械学習・画像認識・深層学習の研究（モデル、手法、指標、データセット、学会、機械学習のライブラリ）
- "programming"：プログラミング言語、ライブラリ、フレームワーク、開発ツール、コードの識別子
- "cloud-infra"：クラウドのサービス、インフラ、ネットワーク、データベース、OS、運用のツール
- "it-products"：一般のIT製品、サービス、アプリ、ハードウェア、企業

出力は、入力と同じ順で、次の形のオブジェクトを並べたJSON配列だけにする。前置きや説明は書かない。
{"surface": "PyTorch", "kind": "name", "category": "ml-research"}"""

CLASSIFY_USER = """次の用語の種類と分野を判断してください。

{items}"""
