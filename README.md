# Chai Hai Order Receiver

Customers text an order on WhatsApp (English / Punjabi, any spelling). Claude parses it, the owner approves it
on WhatsApp, approved orders land in Supabase and a Google Sheet.

**Start with `SETUP.md`.**

## Layout
| Path | What it is |
| --- | --- |
| `app/catalog.py` | The 7 flavours and starter aliases |
| `app/schema.py` | Shape of a parsed message (Pydantic) |
| `app/parser.py` | Prompt + Claude API call + validation |
| `app/service.py` | All order logic: new, merge, cancel, approve, reject, correct |
| `app/whatsapp.py` | Read webhooks, verify signature, send messages |
| `app/store.py` / `app/store_supabase.py` | In-memory store (tests) / Supabase store (production) |
| `app/sheets.py` | Google Sheets row writer |
| `app/main.py` | FastAPI webhook |
| `db/schema.sql` | Supabase tables + seed data |
| `tests/` | 33 offline tests + 75 live parser cases |

## Commands
    source .venv/bin/activate
    pip install -r requirements.txt
    pytest                                  # offline tests (live ones skip without a key)
    pytest tests/test_parser_live.py -v     # real Claude calls
    uvicorn app.main:app --reload           # run locally
