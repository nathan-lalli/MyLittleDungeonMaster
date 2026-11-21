#!/usr/bin/env bash
# Baseline installer for a Raspberry Pi 4 running 64-bit Raspberry Pi OS (Lite is fine).
# Run per node; see README "Topologies" for which parts each node needs.
#   ROLE=all|brain|voice  ./scripts/setup_pi.sh
# NOTE: written from documentation, not tested on your hardware. Read it before running.
set -euo pipefail
ROLE="${ROLE:-all}"
sudo apt update
sudo apt install -y git build-essential cmake python3-venv python3-pip libportaudio2 alsa-utils libcurl4-openssl-dev

if [[ "$ROLE" == "all" || "$ROLE" == "brain" ]]; then
  [[ -d ~/llama.cpp ]] || git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
  cmake -S ~/llama.cpp -B ~/llama.cpp/build -DCMAKE_BUILD_TYPE=Release
  cmake --build ~/llama.cpp/build --config Release -j4 --target llama-server llama-bench
  mkdir -p ~/models
  echo ">> Put a GGUF in ~/models (see README model shortlist), then edit scripts/llama-server.service."
fi

if [[ "$ROLE" == "all" || "$ROLE" == "voice" ]]; then
  [[ -d ~/whisper.cpp ]] || git clone https://github.com/ggml-org/whisper.cpp ~/whisper.cpp
  (cd ~/whisper.cpp && sh ./models/download-ggml-model.sh base.en && cmake -B build && cmake --build build -j4 --config Release)
  python3 -m venv ~/dm-venv
  ~/dm-venv/bin/pip install -r "$(dirname "$0")/../requirements.txt" piper-tts
  mkdir -p ~/voices
  echo ">> Download a Piper voice (.onnx + .onnx.json) into ~/voices, e.g. en_US-lessac-medium, from the rhasspy/piper-voices repo on Hugging Face."
fi
echo "Done. Next: arecord -l / aplay -l to confirm your USB audio device, then python -m dm.main --text"
