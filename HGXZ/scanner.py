from __future__ import annotations

import logging
import re
from pathlib import Path

from .download import probe_media, validate_media
from .state import StateDB

LOG = logging.getLogger('HGXZ')

ALBUM_DIR_RE = re.compile(r'^(.*?)\s*\[huangguo-(\d+)\]$')
EPISODE_RE = re.compile(r'\.S01E(\d+)\.\w+$', re.I)


def scan_existing(root: Path, state: StateDB,
                  minimum_duration: float = 10.0,
                  validate: bool = True) -> dict:
    """Walk the media root, find previously downloaded videos by the
    ``[huangguo-{id}]`` directory naming convention, and register them in the
    state database so subsequent syncs treat them as already downloaded."""

    result = {
        'albums_found': 0,
        'episodes_found': 0,
        'episodes_valid': 0,
        'episodes_invalid': 0,
        'errors': 0,
    }

    if not root.is_dir():
        LOG.warning('media root does not exist: %s', root)
        return result

    for category_dir in sorted(root.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith('.'):
            continue
        category_name = category_dir.name

        for album_dir in sorted(category_dir.iterdir()):
            if not album_dir.is_dir():
                continue
            match = ALBUM_DIR_RE.match(album_dir.name)
            if not match:
                continue

            title = match.group(1).strip()
            album_id = int(match.group(2))
            result['albums_found'] += 1

            season_dir = album_dir / 'Season 01'
            search_dir = season_dir if season_dir.is_dir() else album_dir

            episodes: list[tuple[int, Path]] = []
            for f in sorted(search_dir.iterdir()):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in ('.mp4', '.mkv', '.ts'):
                    continue
                ep_match = EPISODE_RE.search(f.name)
                if ep_match:
                    episodes.append((int(ep_match.group(1)), f))
                    result['episodes_found'] += 1

            if not episodes:
                LOG.debug('album=%s title=%s has no episode files', album_id, title)
                state.upsert_album(album_id, category_name, title, 0, False,
                                   str(album_dir))
                continue

            max_ep = max(ep_num for ep_num, _ in episodes)
            state.upsert_album(album_id, category_name, title, max_ep, False,
                               str(album_dir))

            for ep_num, ep_path in episodes:
                if state.episode_done(album_id, ep_num):
                    result['episodes_valid'] += 1
                    continue
                if validate:
                    try:
                        info = probe_media(ep_path)
                        if validate_media(info, minimum_duration):
                            state.mark_episode(album_id, ep_num, str(ep_path), 'done')
                            result['episodes_valid'] += 1
                        else:
                            state.mark_episode(album_id, ep_num, str(ep_path), 'failed')
                            result['episodes_invalid'] += 1
                            LOG.warning('invalid media: album=%s ep=%s info=%s',
                                        album_id, ep_num, info)
                    except Exception as exc:
                        result['errors'] += 1
                        LOG.warning('probe error: album=%s ep=%s error=%s',
                                    album_id, ep_num, exc)
                else:
                    state.mark_episode(album_id, ep_num, str(ep_path), 'done')
                    result['episodes_valid'] += 1

            LOG.info('scanned album=%s title=%s episodes=%d', album_id, title,
                     len(episodes))

    LOG.info('scan_existing complete: %s', result)
    return result
