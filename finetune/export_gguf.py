#!/usr/bin/env python3
"""
finetune/export_gguf.py
Exporte le modèle mergé en GGUF Q4_K_M puis l'importe dans Ollama.

Usage (sur le PC fixe) :
    python finetune/export_gguf.py --model finetune/output/<run>/model_merged

Usage (importer sur le Mac M2) :
    # Copie le .gguf sur le Mac (scp / clé USB), puis :
    ollama create smartwear-fashion -f finetune/Modelfile

Prérequis :
    git clone https://github.com/ggerganov/llama.cpp  (dans ~/llama.cpp)
    cd ~/llama.cpp && pip install -r requirements.txt
    cmake -B build -DLLAMA_CUDA=ON && cmake --build build --config Release -j
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_LLAMA_CPP = os.environ.get("LLAMA_CPP_PATH", str(Path.home() / "llama.cpp"))
DEFAULT_QUANT     = "Q4_K_M"   # bon équilibre taille/qualité pour Ollama
MODELFILE_TEMPLATE = """FROM ./{gguf_filename}

# Paramètres d'inférence SmartWear Fashion LLM
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER repeat_penalty 1.1
PARAMETER num_ctx 2048

SYSTEM \"\"\"Tu es SmartWear, un assistant expert en mode et vestimentaire.
Tu connais les collections de Mango, Nike, Jules, Le Coq Sportif, Kappa, Lotto et Sergio Tacchini.
Tu aides les utilisateurs à trouver des vêtements, composer des tenues et donner des conseils de style.
Réponds toujours en français, de manière concise et utile.\"\"\"
"""


def run(cmd: list, **kwargs):
    print(f"$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, check=True, **kwargs)
    return result


def find_convert_script(llama_cpp: str) -> str:
    candidates = [
        os.path.join(llama_cpp, "convert_hf_to_gguf.py"),
        os.path.join(llama_cpp, "convert-hf-to-gguf.py"),
        os.path.join(llama_cpp, "convert.py"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError(
        f"Script de conversion non trouvé dans {llama_cpp}.\n"
        "Clone llama.cpp : git clone https://github.com/ggerganov/llama.cpp"
    )


def main():
    parser = argparse.ArgumentParser(description="Export GGUF + import Ollama")
    parser.add_argument("--model",      required=True, help="Dossier model_merged (HF format)")
    parser.add_argument("--llama-cpp",  default=DEFAULT_LLAMA_CPP, help="Dossier llama.cpp")
    parser.add_argument("--quant",      default=DEFAULT_QUANT, help="Quantization (Q4_K_M, Q5_K_M, Q8_0…)")
    parser.add_argument("--output",     default=None, help="Fichier .gguf de sortie")
    parser.add_argument("--ollama-name", default="smartwear-fashion", help="Nom du modèle dans Ollama")
    parser.add_argument("--skip-ollama", action="store_true", help="Ne pas importer dans Ollama")
    args = parser.parse_args()

    model_dir  = Path(args.model).resolve()
    llama_cpp  = Path(args.llama_cpp).resolve()
    gguf_out   = Path(args.output) if args.output else model_dir.parent / f"smartwear-fashion-{args.quant}.gguf"
    gguf_f32   = model_dir.parent / "smartwear-fashion-f16.gguf"

    print(f"\n{'='*60}")
    print(f"  Export GGUF — SmartWear Fashion LLM")
    print(f"  Modèle    : {model_dir}")
    print(f"  Quantization : {args.quant}")
    print(f"  Sortie    : {gguf_out}")
    print(f"{'='*60}\n")

    # ── 1. Conversion HF → GGUF F16 ──────────────────────────────────────────
    convert_script = find_convert_script(str(llama_cpp))
    print(f"[1/3] Conversion HF → GGUF (f16)…")
    run([
        sys.executable, convert_script,
        str(model_dir),
        "--outfile", str(gguf_f32),
        "--outtype", "f16",
    ])
    print(f"      GGUF F16 → {gguf_f32}\n")

    # ── 2. Quantification ────────────────────────────────────────────────────
    quantize_bin = llama_cpp / "build" / "bin" / "llama-quantize"
    if not quantize_bin.exists():
        quantize_bin = llama_cpp / "quantize"   # fallback ancien chemin
    if not quantize_bin.exists():
        raise FileNotFoundError(
            f"llama-quantize introuvable dans {llama_cpp}/build/bin/\n"
            "Compile llama.cpp : cmake -B build -DLLAMA_CUDA=ON && cmake --build build --config Release -j"
        )

    print(f"[2/3] Quantification {args.quant}…")
    run([str(quantize_bin), str(gguf_f32), str(gguf_out), args.quant])
    print(f"      GGUF {args.quant} → {gguf_out}\n")

    # Nettoyer le F16 intermédiaire
    gguf_f32.unlink(missing_ok=True)

    # ── 3. Générer le Modelfile Ollama ────────────────────────────────────────
    modelfile_path = gguf_out.parent / "Modelfile"
    modelfile_content = MODELFILE_TEMPLATE.format(gguf_filename=gguf_out.name)
    modelfile_path.write_text(modelfile_content, encoding="utf-8")
    print(f"[3/3] Modelfile généré → {modelfile_path}\n")

    # ── 4. Import dans Ollama (optionnel) ─────────────────────────────────────
    if not args.skip_ollama:
        if shutil.which("ollama") is None:
            print("Ollama non trouvé dans le PATH — import ignoré.")
            print(f"Pour importer manuellement :")
            print(f"  ollama create {args.ollama_name} -f {modelfile_path}")
        else:
            print(f"Import dans Ollama sous le nom '{args.ollama_name}'…")
            run(["ollama", "create", args.ollama_name, "-f", str(modelfile_path)],
                cwd=str(gguf_out.parent))
            print(f"\nModèle disponible dans Ollama !")
            print(f"  ollama run {args.ollama_name}")

    print(f"\n{'='*60}")
    print(f"  Export terminé !")
    print(f"  GGUF  : {gguf_out}  ({gguf_out.stat().st_size / 1e9:.2f} GB)")
    print(f"\n  Pour utiliser dans l'app Flask :")
    print(f"  → Copie le .gguf sur le Mac M2")
    print(f"  → ollama create {args.ollama_name} -f Modelfile")
    print(f"  → Mets OLLAMA_MODEL={args.ollama_name} dans ton .env")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
