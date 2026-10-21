# Standalone Seed Reflection Walkthrough

This project has been separated into its own completely independent directory. It has **zero dependencies** on the Seed Reflections Code Indexer repository and relies only on Python's built-in standard library to serve files and run backend API endpoints.

## Features Implemented in Standalone Environment

1.  **Independent Seed Queue Manager**:
    *   Tracks seeds entirely locally inside a local JSON store `seeds.json`.
    *   Creates, reads, and updates seeds via a clean Python API.
2.  **API Session Endpoint**:
    *   Secures platform API keys server-side using `.env`.
    *   Requests widget session tokens from the Seed Signature service and returns them to the frontend widget client.
3.  **Cryptographic Signature Persistence**:
    *   Updates the local seed database `seeds.json` with the cryptographic signature ID and verification certificate URL when completed.
4.  **Static Server**:
    *   Serves the consumer dashboard, admin dashboard, index pages, assets, and JS dynamically under the same port (`8476`), preventing CORS and cross-port resolution issues.

## How to Run the App

1.  Open the folder:
    `c:\Users\SEEDN\Downloads\seed-reflection-isolated`
2.  Run the server:
    *   Double-click the **`start.bat`** file.
3.  View the dashboard in your browser at:
    [http://localhost:8476/consumer](http://localhost:8476/consumer)
