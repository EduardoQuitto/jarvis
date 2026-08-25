# J.A.R.V.I.S. — Network Topology

## Overview

JARVIS is designed as a distributed system running across multiple nodes on a local network. Each node has a specific role and communicates via HTTP/REST.

## Current Topology

```
                    +-------------------+
                    |   Local Network   |
                    |   (192.168.x.x)   |
                    +---------+---------+
                              |
              +---------------+---------------+
              |                               |
     +--------+--------+           +---------+---------+
     | JARVIS Server    |           | NODE 2 (dev)      |
     | (i3 / Ubuntu)    |           | (i5-7400 / Win)   |
     | Port 8000        |           | Port 8000          |
     +------------------+           +-------------------+
              |                               |
     Home Assistant                  FastAPI Server
     Automations                     Tool Execution
     Scheduler                       Windows Agent
     Wake-on-LAN                     Telemetry
```

## Node Communication

- **Protocol:** HTTP/REST (FastAPI)
- **Authentication:** Bearer token via `Authorization` header
- **Default port:** 8000 (configurable via `JARVIS_PORT`)
- **Default bind:** 127.0.0.1 (localhost only; change `JARVIS_HOST` for network access)

## Security Considerations

- All management and tool routes require authentication
- API key validation uses constant-time comparison (`hmac.compare_digest`)
- Anti-SSRF protection blocks requests to private/loopback IPs by default
- LAN access can be opted-in via `JARVIS_NET_ALLOW_PRIVATE_NETWORKS` (CIDR ranges)

## Future Topology

When JARVIS Core (i5-14400) is available:

```
JARVIS Server (24/7)  <-->  JARVIS Core (LLM/STT/TTS)
        |                           |
  Home Assistant              Local LLM (Ollama)
  Automations                 Voice Pipeline
  Scheduler                   Vision
  Wake-on-LAN                 Heavy Processing
        |                           |
  JARVIS Mobile            JARVIS Panel
  (Galaxy S20 FE)          (Galaxy Tab E)
```
