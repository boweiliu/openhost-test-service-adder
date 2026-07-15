"""Accumulator service consumer.

Calls the accumulator service via the OpenHost router. Has a simple HTML page
with a form to add numbers, and shows the current accumulated value.

Service calls go through:
    POST http://$OPENHOST_ROUTER_URL/api/services/v2/call/accumulator/add
    GET  http://$OPENHOST_ROUTER_URL/api/services/v2/call/accumulator/value
"""

import json
import os

import aiohttp.web

ROUTER_URL = os.environ.get("OPENHOST_ROUTER_URL", "http://localhost:8080")
APP_TOKEN = os.environ.get("OPENHOST_APP_TOKEN", "")
APP_NAME = os.environ.get("OPENHOST_APP_NAME", "adder")

SERVICE_SHORTNAME = "accumulator"


def _json_response(data: dict, status: int = 200) -> aiohttp.web.Response:
    return aiohttp.web.Response(
        text=json.dumps(data),
        content_type="application/json",
        status=status,
    )


async def _call_service(method: str, path: str, body: dict | None = None) -> dict:
    """Call the accumulator service through the router."""
    url = f"{ROUTER_URL}/api/services/v2/call/{SERVICE_SHORTNAME}/{path}"
    headers = {"Authorization": f"Bearer {APP_TOKEN}"}
    print(f"Calling service: {method} {url}", flush=True)
    async with aiohttp.ClientSession() as session:
        kwargs = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        async with session.request(method, url, **kwargs) as resp:
            status = resp.status
            try:
                data = await resp.json()
            except (aiohttp.ContentTypeError, ValueError):
                text = await resp.text()
                data = {"raw": text}
            print(f"Service response ({status}): {json.dumps(data)}", flush=True)
            return {"status": status, "body": data}


async def handle_health(request: aiohttp.web.Request) -> aiohttp.web.Response:
    return _json_response({"status": "ok"})


async def handle_root(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """HTML dashboard with a form to add numbers."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{APP_NAME}</title>
    <style>
        body {{ font-family: system-ui, sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; }}
        h1 {{ color: #333; }}
        .card {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 16px 0; }}
        input[type="number"] {{ font-size: 20px; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; width: 120px; }}
        button {{ font-size: 20px; padding: 8px 20px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; margin-left: 8px; }}
        button:hover {{ background: #1d4ed8; }}
        button:disabled {{ background: #9ca3af; cursor: not-allowed; }}
        .value {{ font-size: 36px; font-weight: bold; color: #2563eb; }}
        .result {{ margin-top: 12px; padding: 12px; border-radius: 6px; }}
        .result.success {{ background: #ecfdf5; color: #065f46; }}
        .result.error {{ background: #fef2f2; color: #991b1b; }}
        .info {{ color: #666; font-size: 14px; margin-top: 24px; }}
        code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 4px; }}
    </style>
</head>
<body>
    <h1>➕ Adder (Consumer)</h1>

    <div class="card">
        <p>Current accumulated value (from accumulator service):</p>
        <div class="value" id="value">—</div>
    </div>

    <div class="card">
        <p>Add a number:</p>
        <input type="number" id="number" value="1" />
        <button id="addBtn" onclick="addNumber()">Add</button>
        <div id="result"></div>
    </div>

    <p class="info">
        This app <strong>consumes</strong> the accumulator service (<code>shortname: accumulator</code>).<br>
        It calls <code>{ROUTER_URL}/api/services/v2/call/accumulator/...</code> via the OpenHost router.
    </p>

    <script>
        async function fetchValue() {{
            try {{
                const resp = await fetch('/value');
                const data = await resp.json();
                document.getElementById('value').textContent = data.value;
            }} catch (e) {{
                document.getElementById('value').textContent = '— (error)';
            }}
        }}

        async function addNumber() {{
            const btn = document.getElementById('addBtn');
            const input = document.getElementById('number');
            const resultDiv = document.getElementById('result');
            const number = parseInt(input.value);

            btn.disabled = true;
            btn.textContent = 'Adding...';
            resultDiv.innerHTML = '';

            try {{
                const resp = await fetch('/add', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ number }})
                }});
                const data = await resp.json();
                if (resp.ok) {{
                    resultDiv.innerHTML = `<div class="result success">✅ Success! New value: <strong>${{data.value}}</strong></div>`;
                }} else {{
                    const error = data.error || data.body?.error || 'Unknown error';
                    resultDiv.innerHTML = `<div class="result error">❌ Error: ${{error}}</div>`;
                    if (data.status === 403) {{
                        resultDiv.innerHTML += `<div class="result error" style="margin-top:8px">Permission required. Make sure the "add" grant is approved for this app in the OpenHost dashboard.</div>`;
                    }}
                }}
            }} catch (e) {{
                resultDiv.innerHTML = `<div class="result error">❌ Request failed: ${{e.message}}</div>`;
            }} finally {{
                btn.disabled = false;
                btn.textContent = 'Add';
                fetchValue();
            }}
        }}

        fetchValue();
        setInterval(fetchValue, 3000);
    </script>
</body>
</html>"""
    return aiohttp.web.Response(text=html, content_type="text/html")


async def handle_get_value(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Proxy GET /value to the accumulator service."""
    result = await _call_service("GET", "value")
    return _json_response(result["body"], status=result["status"])


async def handle_add(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Proxy POST /add to the accumulator service."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, aiohttp.ContentTypeError):
        return _json_response({"error": "invalid JSON"}, status=400)

    number = body.get("number")
    if not isinstance(number, (int, float)):
        return _json_response({"error": "body must contain a numeric 'number' field"}, status=400)

    result = await _call_service("POST", "add", {"number": int(number)})
    return _json_response(result["body"], status=result["status"])


def create_app() -> aiohttp.web.Application:
    app = aiohttp.web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/", handle_root)
    app.router.add_get("/value", handle_get_value)
    app.router.add_post("/add", handle_add)
    return app


if __name__ == "__main__":
    app = create_app()
    print("Adder server listening on :8080", flush=True)
    aiohttp.web.run_app(app, host="0.0.0.0", port=8080, print=None)