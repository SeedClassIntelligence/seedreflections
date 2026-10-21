# Build & Run Instructions

### Prerequisites
* Python 3.14+
* `python -m pip install -r requirements.txt`

### Launching the Application
1. Start the local server:
   ```bash
   python server.py
   ```
2. Open the dashboard in your browser:
   `http://localhost:8476/consumer`

### Container
```bash
docker compose up --build
```

All mutable data is stored in `/data`. Hosted and enterprise deployments must set `SEED_REFLECTIONS_PUBLIC_ORIGIN` to the exact browser origin. See `.env.example` for every supported runtime boundary.
