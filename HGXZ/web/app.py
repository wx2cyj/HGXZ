from __future__ import annotations

import asyncio
import json
import logging
import queue
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..state import StateDB
from .log_handler import LogBuffer

LOG = logging.getLogger('HGXZ')

_state_db: StateDB | None = None
_log_buffer: LogBuffer | None = None
_archiver_ref: list = []
_sync_status: dict = {'running': False, 'last_sync': None, 'last_error': None}

STATIC_DIR = Path(__file__).parent / 'static'


def set_shared_state(state: StateDB, log_buf: LogBuffer, archiver_holder: list) -> None:
    global _state_db, _log_buffer, _archiver_ref
    _state_db = state
    _log_buffer = log_buf
    _archiver_ref = archiver_holder


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(title='HGXZ - 黄果下载', lifespan=lifespan)

    app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')

    @app.get('/', response_class=HTMLResponse)
    async def index():
        return FileResponse(STATIC_DIR / 'index.html')

    @app.get('/api/dashboard')
    async def dashboard():
        if not _state_db:
            return JSONResponse({'error': 'not ready'}, 503)
        stats = _state_db.dashboard_stats()
        stats['sync'] = _sync_status
        return stats

    @app.get('/api/albums')
    async def albums(
        category: str | None = Query(None),
        status: str | None = Query(None),
        search: str | None = Query(None),
    ):
        if not _state_db:
            return JSONResponse({'error': 'not ready'}, 503)
        return _state_db.all_albums(category=category, status=status, search=search)

    @app.get('/api/albums/{album_id}')
    async def album_detail(album_id: int):
        if not _state_db:
            return JSONResponse({'error': 'not ready'}, 503)
        result = _state_db.album_with_episodes(album_id)
        if not result:
            return JSONResponse({'error': 'not found'}, 404)
        return result

    @app.post('/api/sync')
    async def trigger_sync(album_id: int | None = None):
        if _sync_status['running']:
            return JSONResponse({'error': '同步正在进行中'}, 409)
        if not _archiver_ref:
            return JSONResponse({'error': 'not ready'}, 503)

        import threading
        def _run():
            _sync_status['running'] = True
            _sync_status['last_error'] = None
            try:
                archiver = _archiver_ref[0]
                archiver.scan(only_id=album_id)
                from datetime import datetime
                _sync_status['last_sync'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            except Exception as exc:
                _sync_status['last_error'] = str(exc)
                LOG.exception('manual sync failed: %s', exc)
            finally:
                _sync_status['running'] = False

        threading.Thread(target=_run, daemon=True, name='manual-sync').start()
        return {'status': 'started', 'album_id': album_id}

    @app.post('/api/retry-failed')
    async def retry_failed(album_id: int | None = None):
        if not _state_db:
            return JSONResponse({'error': 'not ready'}, 503)
        count = _state_db.reset_failed(album_id)
        return {'reset': count}

    @app.post('/api/scan-existing')
    async def scan_existing_api():
        if _sync_status['running']:
            return JSONResponse({'error': '同步正在进行中'}, 409)
        if not _archiver_ref:
            return JSONResponse({'error': 'not ready'}, 503)

        import threading
        def _run():
            _sync_status['running'] = True
            _sync_status['last_error'] = None
            try:
                from ..scanner import scan_existing
                archiver = _archiver_ref[0]
                result = scan_existing(archiver.root, archiver.state,
                                       archiver.minimum_duration)
                LOG.info('scan existing result: %s', result)
            except Exception as exc:
                _sync_status['last_error'] = str(exc)
                LOG.exception('scan existing failed: %s', exc)
            finally:
                _sync_status['running'] = False

        threading.Thread(target=_run, daemon=True, name='scan-existing').start()
        return {'status': 'started'}

    @app.get('/api/logs')
    async def get_logs(n: int = Query(200, le=2000)):
        if not _log_buffer:
            return []
        return _log_buffer.recent(n)

    @app.get('/api/sync-status')
    async def sync_status():
        return _sync_status

    @app.websocket('/ws/logs')
    async def ws_logs(websocket: WebSocket):
        if not _log_buffer:
            await websocket.close(code=1011)
            return
        await websocket.accept()
        sub = _log_buffer.subscribe()
        try:
            while True:
                try:
                    entry = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: sub.get(timeout=1.0))
                    await websocket.send_json(entry)
                except queue.Empty:
                    try:
                        await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
                    except (asyncio.TimeoutError, WebSocketDisconnect):
                        pass
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            _log_buffer.unsubscribe(sub)

    return app
