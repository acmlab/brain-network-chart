# Docker Deployment

Run the full Brain Network Chart stack (frontend + backend + BIDS pipeline) with Docker Compose — no manual environment setup required.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac / Windows) or Docker Engine (Linux)
- A [FreeSurfer license](https://surfer.nmr.mgh.harvard.edu/registration.html) file (free, required for neuroimaging pipelines)

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url>
cd brain-network-chart

# 2. Configure paths
cp docker/.env.example docker/.env
#    Edit docker/.env and set your data directories and FreeSurfer license path

# 3. Build and start
docker compose -f docker/docker-compose.yml --env-file docker/.env up --build -d

# 4. Open in browser
#    http://localhost:8080
```

## Configuration

Copy `.env.example` to `.env` and edit the following variables:

| Variable | Description | Example |
|---|---|---|
| `DATA_INPUT_PATH` | Directory containing raw DICOM data | `/data/dicom` |
| `DATA_OUTPUT_PATH` | Directory for pipeline output (BIDS, derivatives) | `/data/output` |
| `FS_LICENSE_PATH` | Path to your FreeSurfer `license.txt` | `~/freesurfer/license.txt` |
| `USER_TAG` | Username tag used in output directory structure | `jsmith` |

## Services

| Service | Port | Description |
|---|---|---|
| `frontend` | **8080** | React web interface (served by nginx) |
| `backend` | internal 8005 | MCP analysis server (DICOM→BIDS, statistics, LLM) |
| `bids-runner` | **7789** | Local agent for running neuroimaging pipelines |

## Common Commands

```bash
# Start all services
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d

# View logs
docker compose -f docker/docker-compose.yml logs -f

# View logs for a specific service
docker compose -f docker/docker-compose.yml logs -f backend

# Stop all services
docker compose -f docker/docker-compose.yml down

# Rebuild after code changes
docker compose -f docker/docker-compose.yml --env-file docker/.env up --build -d

# Start only frontend + backend (without BIDS pipeline runner)
docker compose -f docker/docker-compose.yml up backend frontend -d
```

## Notes

- **BIDS pipeline** (`bids-runner`) requires access to the Docker socket (`/var/run/docker.sock`) to launch neuroimaging containers (fMRIPrep, QSIPrep, etc.) on your behalf. If Docker socket access is not available, start only `backend` and `frontend`.
- **Windows (Docker Desktop)**: The Docker socket path is different. In `docker-compose.yml`, comment out the Linux socket line and uncomment the Windows pipe line under `bids-runner` volumes.
- **LLM (Ollama)**: The backend expects an Ollama instance at `localhost:11434` for series classification. If unavailable, the agent falls back to regex-based classification automatically.
- **Container images** for the neuroimaging pipeline (~24 GB: fMRIPrep, XCP-D, QSIPrep, QSIRecon) are downloaded on first use inside `bids-runner`. This is a one-time download.

## File Structure

```
docker/
├── .env.example        # Configuration template
├── docker-compose.yml  # Service orchestration
├── Dockerfile.backend  # Python backend image
├── Dockerfile.frontend # React + nginx image
├── nginx.conf          # nginx reverse proxy config
└── README.md           # This file
```
