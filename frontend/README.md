# Frontend

Vite + React (JavaScript). One page: upload a photo, watch its status, and compare the photo with the transcription and the corrected code.

## Run

```
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173.

## Mock vs real backend

One flag in `frontend/.env.development` controls this:

```
VITE_USE_MOCK=true    # in-browser mock, no backend needed (current default)
VITE_USE_MOCK=false   # real Flask API
```

Restart `npm run dev` after changing it. Vite only reads `.env` files at startup.

**Mock mode** (`src/mockApi.js`): nothing leaves the browser. Each upload moves through `queued` (about 2.5s), then `processing` (about 5s), then a final state. You pick the final state from the "Mock scenario" dropdown:
- ready, no corrected code
- ready, syntax error + corrected code
- error

Mock images are placeholders in `public/mock/`. The photo you upload is ignored.

**Real mode**: start Flask on port 5000 first. The Vite dev proxy forwards `/api/*` to `http://localhost:5000` (see `vite.config.js`), so the browser makes same-origin requests and Flask needs no CORS setup. The frontend never talks to the Meta API and never sees `MODEL_API_KEY`.

## Files

- `src/api.js`: the mock/real switch and the fetch calls (`POST /api/submissions`, `GET /api/submissions/:id`)
- `src/mockApi.js`: mock responses, shaped exactly like the contract in CLAUDE.md section 12
- `src/App.jsx`: upload form, polling (every 1.5s, stops at `ready` or `error`), and the review layout
- `src/CodeBlock.jsx`: code with line numbers; highlights `uncertain_lines` (1-indexed)

## Debugging

The "Raw JSON" section at the bottom shows the last response body and which request produced it. If the page looks wrong but the JSON looks right, the bug is in the frontend. If the JSON is wrong, the bug is in the backend. If a request fails (for example a non-2xx status or Flask not running), the page shows a red banner and stops polling.
