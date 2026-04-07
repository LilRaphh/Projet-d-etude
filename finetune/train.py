#!/usr/bin/env python3
"""
finetune/train.py
Fine-tuning QLoRA avec Unsloth — RTX 5070 Ti (CUDA, Windows/Linux)

Usage (sur le PC fixe) :
    pip install -r finetune/requirements.txt
    python -m finetune.prepare_dataset          # génère finetune/data/train.jsonl
    python finetune/train.py                    # lance le fine-tuning
    python finetune/train.py --model unsloth/Meta-Llama-3.1-8B-Instruct --epochs 3

Sortie : finetune/output/<run_name>/  (adaptateurs LoRA + modèle mergé)
"""
import argparse
import json
import os
from pathlib import Path
from datetime import datetime

# ── Config par défaut ─────────────────────────────────────────────────────────
DEFAULT_MODEL   = "unsloth/Meta-Llama-3.1-8B-Instruct"
DEFAULT_DATA    = str(Path(__file__).parent / "data" / "train.jsonl")
DEFAULT_VAL     = str(Path(__file__).parent / "data" / "val.jsonl")
DEFAULT_OUTPUT  = str(Path(__file__).parent / "output")
MAX_SEQ_LEN     = 2048
LORA_RANK       = 32       # 16 = léger / 32 = bon équilibre / 64 = max qualité
LORA_ALPHA      = 64       # en général = 2 × rank
LORA_DROPOUT    = 0.05
BATCH_SIZE      = 4        # 5070 Ti 16GB → 4 confortable, monter à 6 si stable
GRAD_ACCUM      = 4        # batch effectif = BATCH_SIZE × GRAD_ACCUM = 16
LEARNING_RATE   = 2e-4
WARMUP_RATIO    = 0.05
EPOCHS          = 3
SAVE_STEPS      = 200
EVAL_STEPS      = 200


def parse_args():
    p = argparse.ArgumentParser(description="Fine-tuning SmartWear Fashion LLM")
    p.add_argument("--model",    default=DEFAULT_MODEL,  help="Modèle Hugging Face base")
    p.add_argument("--data",     default=DEFAULT_DATA,   help="Train JSONL")
    p.add_argument("--val",      default=DEFAULT_VAL,    help="Val JSONL")
    p.add_argument("--output",   default=DEFAULT_OUTPUT, help="Dossier de sortie")
    p.add_argument("--epochs",   default=EPOCHS,   type=int)
    p.add_argument("--rank",     default=LORA_RANK, type=int, help="Rang LoRA")
    p.add_argument("--batch",    default=BATCH_SIZE, type=int)
    p.add_argument("--lr",       default=LEARNING_RATE, type=float)
    p.add_argument("--max-seq",  default=MAX_SEQ_LEN, type=int)
    p.add_argument("--run-name", default=None, help="Nom du run (défaut: timestamp)")
    return p.parse_args()


def load_sharegpt_dataset(path: str):
    """Charge un JSONL ShareGPT et le convertit en Dataset HuggingFace."""
    from datasets import Dataset

    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return Dataset.from_list(rows)


def format_conversation(example, tokenizer):
    """Applique le chat template du tokenizer sur une conversation ShareGPT."""
    messages = []
    for turn in example["conversations"]:
        role = "user" if turn["from"] == "human" else "assistant"
        messages.append({"role": role, "content": turn["value"]})
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}


def main():
    args = parse_args()
    run_name = args.run_name or datetime.now().strftime("smartwear_%Y%m%d_%H%M")
    output_dir = os.path.join(args.output, run_name)

    print(f"\n{'='*60}")
    print(f"  SmartWear Fashion LLM — Fine-tuning")
    print(f"  Modèle  : {args.model}")
    print(f"  Run     : {run_name}")
    print(f"  Output  : {output_dir}")
    print(f"{'='*60}\n")

    # ── 1. Charger modèle + tokenizer avec Unsloth ────────────────────────────
    try:
        from unsloth import FastLanguageModel
    except ImportError:
        raise SystemExit(
            "Unsloth non installé. Lance : pip install -r finetune/requirements.txt"
        )

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_seq,
        dtype=None,           # auto-detect (bf16 sur 5070 Ti)
        load_in_4bit=True,    # QLoRA 4-bit
    )

    # ── 2. Appliquer LoRA ─────────────────────────────────────────────────────
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.rank,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=args.rank * 2,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        use_gradient_checkpointing="unsloth",  # économise ~30% de VRAM
        random_state=42,
    )

    print(f"Paramètres entraînables : {model.num_parameters(only_trainable=True):,}")
    print(f"Paramètres totaux       : {model.num_parameters():,}")

    # ── 3. Dataset ────────────────────────────────────────────────────────────
    train_ds = load_sharegpt_dataset(args.data)
    val_ds   = load_sharegpt_dataset(args.val) if os.path.exists(args.val) else None

    train_ds = train_ds.map(
        lambda ex: format_conversation(ex, tokenizer),
        remove_columns=train_ds.column_names,
    )
    if val_ds:
        val_ds = val_ds.map(
            lambda ex: format_conversation(ex, tokenizer),
            remove_columns=val_ds.column_names,
        )

    print(f"Train : {len(train_ds)} exemples")
    print(f"Val   : {len(val_ds) if val_ds else 0} exemples")

    # ── 4. Entraînement ───────────────────────────────────────────────────────
    from trl import SFTTrainer
    from transformers import TrainingArguments

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=GRAD_ACCUM,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=WARMUP_RATIO,
        bf16=True,                   # bf16 natif sur 5070 Ti (Blackwell)
        fp16=False,
        logging_steps=20,
        save_steps=SAVE_STEPS,
        eval_steps=EVAL_STEPS if val_ds else None,
        evaluation_strategy="steps" if val_ds else "no",
        save_total_limit=2,
        load_best_model_at_end=bool(val_ds),
        report_to="none",            # mettre "wandb" si tu veux tracker
        run_name=run_name,
        dataloader_num_workers=2,
        optim="adamw_8bit",          # économise encore de la VRAM
        seed=42,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        dataset_text_field="text",
        max_seq_length=args.max_seq,
        args=training_args,
        packing=True,    # pack plusieurs courts exemples → GPU + efficace
    )

    print("\nDémarrage de l'entraînement…\n")
    trainer_stats = trainer.train()

    # ── 5. Sauvegarder les adaptateurs LoRA ──────────────────────────────────
    lora_path = os.path.join(output_dir, "lora_adapters")
    model.save_pretrained(lora_path)
    tokenizer.save_pretrained(lora_path)
    print(f"\nAdaptateurs LoRA sauvegardés → {lora_path}")

    # ── 6. Merger + sauvegarder le modèle complet (pour export GGUF) ─────────
    print("Merge LoRA dans le modèle base…")
    model.save_pretrained_merged(
        os.path.join(output_dir, "model_merged"),
        tokenizer,
        save_method="merged_16bit",   # fp16 pour GGUF ensuite
    )
    print(f"Modèle mergé → {output_dir}/model_merged")

    # ── Résumé ────────────────────────────────────────────────────────────────
    secs = trainer_stats.metrics.get("train_runtime", 0)
    print(f"\n{'='*60}")
    print(f"  Entraînement terminé en {secs/60:.1f} min")
    print(f"  Loss finale : {trainer_stats.metrics.get('train_loss', '?'):.4f}")
    print(f"  Prochaine étape : python finetune/export_gguf.py --model {output_dir}/model_merged")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
