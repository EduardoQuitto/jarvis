# J.A.R.V.I.S. — Hardware Specifications

## Current Hardware

### JARVIS Server
- **CPU:** Intel Core i3-3220
- **RAM:** 8 GB
- **Storage:** HDD 500 GB
- **OS:** Ubuntu Server
- **Role:** 24/7 gateway, Home Assistant, Docker, automations, scheduler, Wake-on-LAN, device monitoring, central memory
- **Constraints:** Must remain lightweight. Do NOT run heavy LLM, vision, Whisper, or intensive processing on this node.

### NODE 2 (Development Machine)
- **CPU:** Intel Core i5-7400
- **RAM:** 8 GB
- **Storage:** SSD ~222 GB + HDD 500 GB
- **GPU:** NVIDIA GTX 650 Ti
- **Role:** Development, testing, auxiliary tasks, Windows Agent
- **Note:** Originally a Pentium G3260. Upgraded to i5-7400. The codebase is designed to be portable and not optimized for any specific hardware.

---

## Planned Hardware

### JARVIS Core
- **CPU:** Intel Core i5-14400
- **RAM:** 32 GB
- **Storage:** SSD NVMe 1 TB
- **GPU:** Integrated initially (dedicated GPU not required — CPU is the primary path)
- **Role:** LLM (Ollama), STT (speech-to-text), TTS (text-to-speech), vision, reasoning, agents, heavy processing

### JARVIS Mobile
- **Device:** Samsung Galaxy S20 FE
- **SoC:** Snapdragon 865
- **RAM:** 6 GB
- **Role:** Voice, notifications, sensors, camera, microphone, ADB, Android control

### JARVIS Panel
- **Device:** Samsung Galaxy Tab E
- **OS:** Android 4.4.4
- **Role:** Dashboard, telemetry, status, alerts, tasks (extremely lightweight interface)

---

## Architecture Principle

Never create an architecture that depends exclusively on a specific machine when it can be decoupled. Components must have clear interfaces (e.g., JARVIS Core → LLM API, not JARVIS Core → specific model embedded in code).
