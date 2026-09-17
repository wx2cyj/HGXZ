from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import json
import logging
import logging.handlers
import threading
import time
import re

from .core import (Episode, build_episode_filename, parse_category_html,
                   parse_detail_html, sanitize_filename, write_episode_nfo,
                   write_tvshow_nfo)
from .download import download_hls, probe_media, validate_media
from .cover import valid_cover, write_cover
from .site import HuangguoClient
from .state import StateDB

LOG = logging.getLogger('HGXZ')


class Archiver:
    def __init__(self, config: dict):
        self.config = config
        site = config['site']
        self.client = HuangguoClient(
            site['base_url'],
            float(site.get('request_interval', 2)),
            int(site.get('timeout', 30)),
            backup_urls=site.get('backup_urls', []),
        )
        self.root = Path(config['download']['root'])
        self.state = StateDB(Path(config['state']['database']))
        self.retries = int(config['download'].get('retries', 3))
        self.minimum_duration = float(config['download'].get('minimum_duration', 10))
        self.recheck_days = float(config['download'].get('recheck_days', 7))
        self.failure_cooldown_hours = float(config['download'].get('failure_cooldown_hours', 24))
        self.episode_timeout = float(config['download'].get('episode_timeout', 1800))

    def close(self):
        self.state.close()

    def discover(self) -> list[tuple[int, dict]]:
        seen: set[int] = set()
        out: list[tuple[int, dict]] = []
        for category in self.config['site']['categories']:
            page = 1
            category_ids: list[int] = []
            while True:
                path = category['path'] if page == 1 else category['path'].rstrip('/') + f'/{page}/'
                html = self.client.get_text(path)
                ids = parse_category_html(html)
                fresh = [i for i in ids if i not in category_ids]
                category_ids.extend(fresh)
                total_match = re.search(r'data-channel-panel=["\']latest["\'][^>]*data-panel-total=["\'](\d+)', html)
                total = int(total_match.group(1)) if total_match else len(category_ids)
                if len(category_ids) >= total or not fresh:
                    break
                page += 1
            LOG.info('category=%s discovered=%d', category['name'], len(category_ids))
            for album_id in category_ids:
                if album_id not in seen:
                    seen.add(album_id)
                    out.append((album_id, category))
        return out

    def _album_dir(self, album, category: dict) -> Path:
        return self.root / sanitize_filename(category['library']) / f'{sanitize_filename(album.title)} [huangguo-{album.id}]'

    def _complete_and_fresh(self, album_id: int) -> bool:
        row = self.state.album_row(album_id)
        if row is None or not row['ended'] or row['episode_count'] < 1:
            return False
        if not self.state.album_is_complete(album_id, row['episode_count']):
            return False
        if not row['last_checked_at']:
            return False
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(row['last_checked_at'])
        except ValueError:
            return False
        return age.total_seconds() < self.recheck_days * 86400

    def _sync_cover(self, album, poster: Path) -> None:
        try:
            cover_url = self.client.cover_url(album.id) or album.cover_url
            if cover_url:
                write_cover(self.client.get_bytes(cover_url), poster)
        except Exception as exc:
            LOG.warning('album=%s cover download failed: %s', album.id, exc)

    def sync_album(self, album_id: int, category: dict, *,
                   metadata_only: bool = False,
                   max_episodes: int | None = None,
                   force: bool = False) -> dict:
        html = self.client.get_text(f'/detail/{album_id}/')
        album = parse_detail_html(album_id, category['name'], html)
        if album.category != category['name']:
            LOG.warning('skip album=%s expected=%s actual=%s',
                        album.id, category['name'], album.category)
            return {'album_id': album.id, 'skipped': True,
                    'expected_category': category['name'],
                    'actual_category': album.category}
        album_dir = self._album_dir(album, category)
        self.state.upsert_album(album.id, album.category, album.title,
                                album.episode_count, album.ended,
                                str(album_dir))
        season_dir = album_dir / 'Season 01'
        season_dir.mkdir(parents=True, exist_ok=True)
        write_tvshow_nfo(album_dir / 'tvshow.nfo', album)
        poster = album_dir / 'poster.jpg'
        if not valid_cover(poster):
            self._sync_cover(album, poster)
        limit = album.episode_count if max_episodes is None else min(album.episode_count, max_episodes)
        done = 0
        failed_episodes: list[int] = []
        for number in range(1, limit + 1):
            video = season_dir / build_episode_filename(album.title, number)
            nfo = video.with_suffix('.nfo')
            ep = Episode(album.id, number, f'S01E{number:02d}', album.plot)
            write_episode_nfo(nfo, album, ep)
            if metadata_only:
                continue
            if self.state.episode_done(album.id, number):
                done += 1
                continue
            if video.exists():
                try:
                    if validate_media(probe_media(video), self.minimum_duration):
                        self.state.mark_episode(album.id, number, str(video), 'done')
                        done += 1
                        continue
                except Exception:
                    pass
            if not force:
                failed_at = self.state.episode_failed_at(album.id, number)
                if failed_at:
                    try:
                        age = datetime.now(timezone.utc) - datetime.fromisoformat(failed_at)
                    except ValueError:
                        age = None
                    if age is not None and age.total_seconds() < self.failure_cooldown_hours * 3600:
                        LOG.info('album=%s ep=%s in cooldown, skipping', album.id, number)
                        continue
            last = None
            for attempt in range(1, self.retries + 1):
                try:
                    url = self.client.play_url(album.id, number)
                    download_hls(url, video, self.client.base_url + '/',
                                 self.minimum_duration, timeout=self.episode_timeout)
                    self.state.mark_episode(album.id, number, str(video), 'done')
                    done += 1
                    break
                except Exception as exc:
                    last = exc
                    LOG.warning('album=%s ep=%s attempt=%s failed=%s',
                                album.id, number, attempt, exc)
                    if attempt < self.retries:
                        time.sleep([30, 120, 600][min(attempt - 1, 2)])
            else:
                self.state.mark_episode(album.id, number, str(video), 'failed')
                failed_episodes.append(number)
                LOG.error('album=%s ep=%s giving up after %s attempts: %s',
                          album.id, number, self.retries, last)
        result = {'album': asdict(album), 'directory': str(album_dir),
                  'episodes_done': done, 'metadata_only': metadata_only}
        if failed_episodes:
            result['failed_episodes'] = failed_episodes
            LOG.error('album=%s finished with %d failed episodes: %s',
                      album.id, len(failed_episodes), failed_episodes)
        return result

    def scan(self, *, metadata_only=False, only_id=None,
             max_albums=None, max_episodes=None):
        found = self.discover()
        force = bool(only_id)
        if only_id:
            chosen = [(i, c) for i, c in found if i == only_id]
            if not chosen:
                chosen = [(only_id, self.config['site']['categories'][0])]
            found = chosen
        if max_albums:
            found = found[:max_albums]
        results = []
        failures = 0
        skipped_complete = 0
        for album_id, category in found:
            if not force and self._complete_and_fresh(album_id):
                skipped_complete += 1
                continue
            try:
                result = self.sync_album(
                    album_id, category, metadata_only=metadata_only,
                    max_episodes=max_episodes, force=force)
                results.append(result)
                if result.get('failed_episodes'):
                    failures += 1
            except Exception as exc:
                failures += 1
                LOG.exception('sync album %s failed: %s', album_id, exc)
        episodes_done = sum(r.get('episodes_done', 0) for r in results)
        LOG.info('sync finished synced=%d failures=%d skipped=%d episodes=%d',
                 len(results), failures, skipped_complete, episodes_done)
        return results, failures


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def run_daemon(config: dict, schedule: str, web_port: int = 8080) -> int:
    from .web.app import create_app, set_shared_state
    from .web.log_handler import LogBuffer
    import uvicorn

    log_buf = LogBuffer()
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    log_buf.setFormatter(formatter)
    root_logger = logging.getLogger('HGXZ')
    root_logger.addHandler(log_buf)

    log_dir_str = config.get('log', {}).get('directory', '')
    if log_dir_str:
        log_dir = Path(log_dir_str)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_dir / 'hgxz.log', when='midnight', backupCount=30,
            encoding='utf-8')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    archiver = Archiver(config)
    archiver_ref = [archiver]
    set_shared_state(archiver.state, log_buf, archiver_ref)

    from .web.app import _sync_status

    try:
        hour, minute = (int(part) for part in schedule.split(':'))
    except ValueError:
        LOG.error('invalid --schedule %r, expected HH:MM', schedule)
        return 1

    def sync_loop():
        while True:
            _sync_status['running'] = True
            try:
                archiver.scan()
                _sync_status['last_sync'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                _sync_status['last_error'] = None
            except Exception as exc:
                _sync_status['last_error'] = str(exc)
                LOG.exception('sync failed')
            finally:
                _sync_status['running'] = False

            now = datetime.now()
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            LOG.info('next sync at %s (%.0f seconds from now)',
                     target.strftime('%Y-%m-%d %H:%M:%S'), wait_seconds)
            deadline = time.monotonic() + wait_seconds
            while time.monotonic() < deadline:
                time.sleep(30)

    sync_thread = threading.Thread(target=sync_loop, daemon=True, name='sync-daemon')
    sync_thread.start()

    LOG.info('WebUI starting on port %s', web_port)
    app = create_app()
    uvicorn.run(app, host='0.0.0.0', port=web_port, log_level='warning')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog='HGXZ', description='黄果下载')
    parser.add_argument('--config', default='/config/config.json')
    parser.add_argument('--metadata-only', action='store_true')
    parser.add_argument('--only-id', type=int)
    parser.add_argument('--max-albums', type=int)
    parser.add_argument('--max-episodes', type=int)
    parser.add_argument('--rebuild-covers', action='store_true')
    parser.add_argument('--scan-existing', action='store_true',
                        help='扫描媒体目录，将已有视频注册到状态库')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--daemon', action='store_true',
                        help='常驻运行：启动后同步一次，之后每天定时同步，同时开启 WebUI')
    parser.add_argument('--schedule', default='03:30',
                        help='--daemon 模式下的每日同步时间 HH:MM')
    parser.add_argument('--port', type=int, default=8080,
                        help='WebUI 端口（默认 8080）')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    config = load_config(Path(args.config))

    if args.daemon:
        return run_daemon(config, args.schedule, args.port)

    if args.scan_existing:
        from .scanner import scan_existing
        state = StateDB(Path(config['state']['database']))
        try:
            result = scan_existing(
                Path(config['download']['root']), state,
                float(config['download'].get('minimum_duration', 10)))
        finally:
            state.close()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.rebuild_covers:
        from .rebuild_covers import rebuild
        site = config['site']
        client = HuangguoClient(
            site['base_url'],
            float(site.get('request_interval', 2)),
            int(site.get('timeout', 30)),
            backup_urls=site.get('backup_urls', []),
        )
        result = rebuild(Path(config['download']['root']), client)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['failed'] == 0 else 1

    archiver = Archiver(config)
    try:
        results, failures = archiver.scan(
            metadata_only=args.metadata_only, only_id=args.only_id,
            max_albums=args.max_albums, max_episodes=args.max_episodes)
    finally:
        archiver.close()
    if args.json:
        print(json.dumps({'results': results, 'failures': failures},
                         ensure_ascii=False, indent=2))
    return 0 if failures == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
