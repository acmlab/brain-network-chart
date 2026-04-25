# CIVET Skill Endpoints

Run the FastAPI server with your preferred ASGI runner, for example:

```sh
uvicorn mcp_server.server:app --reload
```

Inspect a CIVET subject folder:

```sh
curl -X POST http://127.0.0.1:8000/inspect_civet_folder \
  -H 'Content-Type: application/json' \
  -d '{"subject_dir": "/path/to/civet/subject"}'
```

Run QC checks:

```sh
curl -X POST http://127.0.0.1:8000/run_civet_qc_check \
  -H 'Content-Type: application/json' \
  -d '{"qc_file": "/path/to/qc.csv", "subject_id": "sub-001"}'
```

Summarize a cortical thickness map:

```sh
curl -X POST http://127.0.0.1:8000/load_cortical_thickness_map \
  -H 'Content-Type: application/json' \
  -d '{"thickness_file": "/path/to/thickness.txt"}'
```

The manual endpoint schema is available at:

```sh
curl http://127.0.0.1:8000/api/schema
```
