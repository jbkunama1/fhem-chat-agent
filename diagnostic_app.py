import asyncio
import json
from fastapi import Depends, HTTPException
from jsonschema import validate, ValidationError
import ui_app as ui

app = ui.app
core = ui.core

class DeviceError(ValueError):
    def __init__(self, phase, code):
        self.phase = phase
        self.code = code
        super().__init__(code)

def failure(phase, exc):
    return DeviceError(phase, 'timeout' if isinstance(exc, TimeoutError) else 'failed')

def payload(response):
    if getattr(response, 'isError', False):
        raise DeviceError('tool_response', 'mcp_tool_error')
    value = getattr(response, 'structuredContent', None)
    texts = [p.text for p in response.content if getattr(p, 'type', '') == 'text']
    combined = json.dumps(value, ensure_ascii=False) if value is not None else '\n'.join(texts)
    lower = combined.lower()
    if 'connection refused' in lower or 'errno 111' in lower:
        raise DeviceError('fhem_connection', 'connection_refused')
    if 'fhem connection failed' in lower:
        raise DeviceError('fhem_connection', 'connection_failed')
    if value is None:
        value = json.loads('\n'.join(texts))
    for _ in range(4):
        if isinstance(value, dict) and 'result' in value and isinstance(value['result'], (str, dict, list)):
            value = value['result']
        elif isinstance(value, str):
            value = json.loads(value)
        else:
            break
    return value

async def devices():
    async with ui.cache_lock:
        if ui.cache['expires'] > ui.time.monotonic():
            return ui.cache['devices']
        if not core.MCP_URL:
            raise DeviceError('configuration', 'missing_mcp_url')
        try:
            tools = await core.discover()
        except Exception as exc:
            raise failure('discovery', exc) from None
        tool = tools.get('fhem_list_devices')
        if not tool:
            raise DeviceError('tool_selection', 'missing_fhem_list_devices')
        if not core.readonly('fhem_list_devices'):
            raise DeviceError('tool_selection', 'not_readonly')
        try:
            validate({}, tool['function']['parameters'])
        except ValidationError:
            raise DeviceError('arguments', 'empty_arguments_invalid') from None
        except Exception:
            raise DeviceError('arguments', 'invalid_schema') from None
        try:
            async with asyncio.timeout(25):
                async with core.mcp_session() as session:
                    response = await session.call_tool('fhem_list_devices', {})
        except Exception as exc:
            raise failure('tool_call', exc) from None
        try:
            rows = ui.unpack(payload(response))
            result = ui.normalize(rows)
            if rows and not result:
                raise DeviceError('normalization', 'no_valid_device_records')
        except DeviceError:
            raise
        except Exception:
            raise DeviceError('parsing', 'unsupported_device_format') from None
        ui.cache.update(devices=result, expires=ui.time.monotonic()+30)
        return result

ui.devices = devices
original_diagnostics = ui.diagnostics

@app.exception_handler(DeviceError)
async def device_error(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503, content={'detail': {'phase': exc.phase, 'code': exc.code}})

app.router.routes[:] = [r for r in app.router.routes if getattr(r, 'path', None) not in ('/api/diagnostics', '/api/devices')]

@app.get('/api/devices')
async def find_devices(q: str = ui.Query(default='', max_length=120), owner=Depends(core.auth)):
    matches = ui.search(await devices(), q)
    return {'devices': matches[:30], 'total': len(matches), 'cache_seconds': 30}

@app.post('/api/diagnostics')
async def diagnostics(owner=Depends(core.auth)):
    async def inspect():
        try:
            async with asyncio.timeout(75):
                rows = await devices()
            return {'status': 'ok', 'devices': len(rows), 'cache_seconds': 30}
        except DeviceError as exc:
            return {'status': 'error', 'phase': exc.phase, 'code': exc.code}
        except Exception as exc:
            return {'status': 'error', 'phase': 'device_check', 'code': 'timeout' if isinstance(exc, TimeoutError) else 'failed'}
    result = await inspect()
    # Reuse existing non-FHEM checks without a second device request.
    async def cached_result():
        return []
    # Call the original checks through a copied function-global mapping.
    import types
    scope = dict(original_diagnostics.__globals__, devices=cached_result)
    checks = types.FunctionType(original_diagnostics.__code__, scope)
    state = await checks(owner)
    state['fhem_via_mcp'] = result
    try:
        tools = await core.discover()
        state['mcp']['tools'] = [{'name': name, 'required': spec['function']['parameters'].get('required', [])} for name, spec in sorted(tools.items())]
    except Exception:
        state['mcp']['tool_metadata'] = 'unavailable'
    return state
