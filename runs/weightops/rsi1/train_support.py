"""用語差し替え行を条件Dの学習へ追加し、損失対象の語だけに語彙射影を行う。"""

import random

import torch
from transformers import Trainer

from train import IGNORE_INDEX, tokenize_pair
from voiceime.formatter.glossary import entry_from_record
from voiceime.formatter.prompt import FormatterInput


class AugmentedDataset(torch.utils.data.Dataset):
    """固定した3入力と一覧を渡し、設定された率で正解語だけを一覧から抜く。"""

    def __init__(self, rows, tokenizer, args):
        self.rows = rows
        self.tokenizer = tokenizer
        self.drop = args.glossary_drop_prob
        self.max_length = args.max_length

    def __len__(self):
        """用語を差し替えた行の数を返す。"""
        return len(self.rows)

    def __getitem__(self, index):
        """拡張データに書き出した入力を、そのまま条件Dの形式でトークン化する。"""
        row = self.rows[index]
        inputs = FormatterInput(first_pass=row["first_pass"], combined_text=row["combined_text"],
                                qwen_hypothesis=row["qwen_hypothesis"] or None)
        glossary = row["glossary"]
        if self.drop:
            gold = set(row["terms"])
            rng = random.Random(int(torch.randint(0, 2**31 - 1, (1,)).item()))
            glossary = [entry for entry in glossary
                        if entry["surface"] not in gold or rng.random() >= self.drop]
        return tokenize_pair(self.tokenizer, inputs, [entry_from_record(entry) for entry in glossary],
                             row["target_text"], self.max_length)


class ProjectedLossTrainer(Trainer):
    """正解応答を予測する位置だけを語彙へ射影し、条件Dと同じ損失を計算する。"""

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        """promptとpadでは射影結果が使われないため、語彙次元へ展開する前に除く。"""
        labels = inputs["labels"][:, 1:]
        active = labels != IGNORE_INDEX

        def select_hidden(_module, args):
            """[batch, token, hidden]から、正解応答の直前位置を[正解トークン数, hidden]へ集める。"""
            return (args[0][:, :-1][active],)

        hook = model.get_output_embeddings().register_forward_pre_hook(select_hidden)
        try:
            return super().compute_loss(
                model, {**inputs, "shift_labels": labels[active]},
                return_outputs=return_outputs, num_items_in_batch=num_items_in_batch,
            )
        finally:
            hook.remove()
