#!/usr/bin/env python3

import argparse
import curses
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from typing import List, Tuple, Optional

TMDB_API_KEY = None
API_BASE = "https://api.themoviedb.org/3"
VIDKING_BASE = "https://www.vidking.net/embed"
CONFIG_PATH = os.path.expanduser('~/.tmdb_api_key')


def load_saved_api_key() -> Optional[str]:
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return f.read().strip() or None
    except OSError:
        return None


def save_api_key(api_key: str) -> None:
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            f.write(api_key.strip() + '\n')
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


class TUIState:
    def __init__(self):
        self.state = "SEARCH"
        self.search_query = ""
        self.selected_index = 0
        self.scroll_offset = 0
        self.results: List[Tuple[str, int, str, str]] = []
        self.seasons: List[Tuple[int, str, str]] = []
        self.episodes: List[Tuple[int, str, str]] = []
        self.tv_id: Optional[int] = None
        self.season_num: Optional[int] = None


def tmdb_request(endpoint: str, params: dict = None) -> dict:
    params = params or {}
    params['api_key'] = TMDB_API_KEY
    url = f"{API_BASE}{endpoint}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode())
    except Exception:
        return {}


def play_movie(tmdb_id: int):
    url = f"{VIDKING_BASE}/movie/{tmdb_id}?autoPlay=true&color=5865f2"
    open_url(url)


def get_browser_command() -> Optional[str]:
    candidates = [os.environ.get('BROWSER'), 'brave', 'google-chrome', 'chromium', 'chromium-browser', 'firefox', 'xdg-open']
    for cmd in candidates:
        if not cmd:
            continue
        if shutil.which(cmd):
            return cmd
    return None


def open_url(url: str):
    browser = get_browser_command()
    if browser is None:
        print('Error: no browser found to open the URL.')
        return

    if browser in ('brave', 'google-chrome', 'chromium', 'chromium-browser'):
        subprocess.Popen([browser, '--password-store=basic', f'--app={url}'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen([browser, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def play_episode(tmdb_id: int, season: int, episode: int):
    url = f"{VIDKING_BASE}/tv/{tmdb_id}/{season}/{episode}?autoPlay=true&color=5865f2&nextEpisode=true&episodeSelector=true"
    open_url(url)


def perform_search(state: TUIState, query: str):
    state.results = []
    if not query:
        return
    data = tmdb_request("/search/multi", {"query": query})
    if 'results' not in data:
        return
    filtered = [item for item in data['results']
                if item.get('media_type') in ('movie', 'tv')]
    filtered.sort(key=lambda x: x.get('popularity', 0.0), reverse=True)
    for item in filtered:
        media_type = item.get('media_type')
        item_id = item.get('id')
        title = item.get('title') or item.get('name', '')
        release_date = item.get('release_date') or item.get('first_air_date', '')
        year = release_date.split('-')[0] if release_date else 'N/A'
        state.results.append((media_type, item_id, title, year))
    state.state = "RESULTS"
    state.selected_index = 0
    state.scroll_offset = 0


def load_seasons(state: TUIState, tv_id: int):
    state.seasons = []
    data = tmdb_request(f"/tv/{tv_id}")
    if 'seasons' not in data:
        return
    for season in reversed(data['seasons']):
        num = season.get('season_number')
        name = season.get('name', '')
        air_date = season.get('air_date', '')
        year = air_date.split('-')[0] if air_date else 'N/A'
        state.seasons.append((num, name, year))
    state.tv_id = tv_id
    state.state = "SEASONS"
    state.selected_index = 0
    state.scroll_offset = 0


def load_episodes(state: TUIState, tv_id: int, season_num: int):
    state.episodes = []
    data = tmdb_request(f"/tv/{tv_id}/season/{season_num}")
    if 'episodes' not in data:
        return
    for ep in data['episodes']:
        num = ep.get('episode_number')
        name = ep.get('name', '')
        air_date = ep.get('air_date', '')
        year = air_date.split('-')[0] if air_date else 'N/A'
        state.episodes.append((num, name, year))
    state.season_num = season_num
    state.state = "EPISODES"
    state.selected_index = 0
    state.scroll_offset = 0


def get_current_list(state: TUIState):
    if state.state == "RESULTS":
        return state.results
    elif state.state == "SEASONS":
        return state.seasons
    elif state.state == "EPISODES":
        return state.episodes
    return []


def ensure_visible(state: TUIState, visible_lines: int):
    lst = get_current_list(state)
    if not lst:
        state.scroll_offset = 0
        return
    if state.selected_index < state.scroll_offset:
        state.scroll_offset = state.selected_index
    elif state.selected_index >= state.scroll_offset + visible_lines:
        state.scroll_offset = state.selected_index - visible_lines + 1
    if state.scroll_offset < 0:
        state.scroll_offset = 0


def main(stdscr):
    state = TUIState()

    curses.curs_set(0)
    stdscr.keypad(True)
    curses.noecho()
    curses.mousemask(curses.ALL_MOUSE_EVENTS)

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        # Search bar
        stdscr.addstr(0, 0, f"Search: {state.search_query}"[:width-1])

        # Content area
        content_start = 1
        content_end = height - 2
        visible_lines = content_end - content_start

        lst = get_current_list(state)
        ensure_visible(state, visible_lines)

        # Draw items
        if state.state != "SEARCH":
            if lst:
                start = state.scroll_offset
                end = min(start + visible_lines, len(lst))
                for i in range(start, end):
                    y = content_start + (i - start)
                    if state.state == "RESULTS":
                        media_type, _, title, year = lst[i]
                        prefix = "🎬" if media_type == "movie" else "📺"
                        line = f"{prefix} {title} ({year})"
                    elif state.state == "SEASONS":
                        num, name, year = lst[i]
                        line = f"Season {num}: {name} ({year})"
                    else:  # EPISODES
                        num, name, year = lst[i]
                        line = f"Ep {num}: {name} ({year})"
                    if i == state.selected_index:
                        stdscr.attron(curses.A_REVERSE)
                        stdscr.addstr(y, 0, line[:width-1])
                        stdscr.attroff(curses.A_REVERSE)
                    else:
                        stdscr.addstr(y, 0, line[:width-1])
            else:
                stdscr.addstr(content_start, 0, "No results found.")

        # Scroll indicator
        if lst and len(lst) > visible_lines:
            pct = int((state.scroll_offset / max(1, len(lst) - visible_lines)) * 100)
            stdscr.addstr(content_start, max(0, width-6), f"{pct:3}%")

        # Status bar - centered
        status_line = height - 1
        status = "-- tmdb Search --"
        x = max(0, (width - len(status)) // 2)
        stdscr.addstr(status_line, x, status)

        # Cursor for search
        if state.state == "SEARCH":
            curses.curs_set(1)
            stdscr.move(0, min(8 + len(state.search_query), width - 1))
        else:
            curses.curs_set(0)

        stdscr.refresh()

        # Input
        key = stdscr.getch()

        if key == curses.KEY_MOUSE:
            try:
                _, mx, my, _, bstate = curses.getmouse()
                lst = get_current_list(state)
                idx = state.scroll_offset + (my - content_start) if content_start <= my < content_end else -1

                if bstate & curses.BUTTON1_CLICKED:
                    if my == 0:
                        state.state = "SEARCH"
                        state.selected_index = 0
                        state.scroll_offset = 0
                    elif 0 <= idx < len(lst):
                        state.selected_index = idx
                        if state.state == "RESULTS":
                            media_type, item_id, _, _ = lst[idx]
                            if media_type == 'tv':
                                load_seasons(state, item_id)
                        elif state.state == "SEASONS":
                            num, _, _ = lst[idx]
                            load_episodes(state, state.tv_id, num)
                    elif my >= content_end:
                        if state.state == "RESULTS":
                            state.state = "SEARCH"
                        elif state.state == "SEASONS":
                            state.state = "RESULTS"
                            state.seasons = []
                        elif state.state == "EPISODES":
                            state.state = "SEASONS"
                            state.episodes = []
                        state.selected_index = 0
                        state.scroll_offset = 0
            except curses.error:
                pass

        elif key in (27, 17):  # Esc or Ctrl-Q
            break

        elif key == ord('/'):
            state.state = "SEARCH"
            state.search_query = ""
            state.selected_index = 0
            state.scroll_offset = 0
            state.results = []
            state.seasons = []
            state.episodes = []
            state.tv_id = None
            state.season_num = None

        elif state.state == "SEARCH":
            if key in (curses.KEY_ENTER, 10, 13):
                if state.search_query:
                    perform_search(state, state.search_query)
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                state.search_query = state.search_query[:-1]
            elif key == 23:  # Ctrl-W
                state.search_query = state.search_query.rstrip().rsplit(' ', 1)[0] if ' ' in state.search_query.rstrip() else ''
            elif 32 <= key <= 126:
                state.search_query += chr(key)

        elif state.state in ("RESULTS", "SEASONS", "EPISODES"):
            lst = get_current_list(state)
            if not lst:
                continue

            if key == curses.KEY_UP and state.selected_index > 0:
                state.selected_index -= 1
            elif key == curses.KEY_DOWN and state.selected_index < len(lst) - 1:
                state.selected_index += 1
            elif key == curses.KEY_PPAGE:
                state.selected_index = max(0, state.selected_index - visible_lines)
            elif key == curses.KEY_NPAGE:
                state.selected_index = min(len(lst) - 1, state.selected_index + visible_lines)
            elif key == curses.KEY_HOME:
                state.selected_index = 0
            elif key == curses.KEY_END:
                state.selected_index = len(lst) - 1
            elif key in (curses.KEY_ENTER, 10, 13, curses.KEY_RIGHT):
                if state.state == "RESULTS" and lst:
                    media_type, item_id, _, _ = lst[state.selected_index]
                    if media_type == 'movie':
                        play_movie(item_id)
                    else:
                        load_seasons(state, item_id)
                elif state.state == "SEASONS" and lst:
                    num, _, _ = lst[state.selected_index]
                    load_episodes(state, state.tv_id, num)
                elif state.state == "EPISODES" and lst:
                    play_episode(state.tv_id, state.season_num,
                                lst[state.selected_index][0])
            elif key == curses.KEY_LEFT:
                if state.state == "RESULTS":
                    state.state = "SEARCH"
                elif state.state == "SEASONS":
                    state.state = "RESULTS"
                    state.seasons = []
                elif state.state == "EPISODES":
                    state.state = "SEASONS"
                    state.episodes = []
                state.selected_index = 0
                state.scroll_offset = 0


def get_tmdb_api_key() -> str:
    parser = argparse.ArgumentParser(description='TMDB search interface')
    parser.add_argument('--api-key', help='TMDB API key')
    parser.add_argument('--save-api-key', action='store_true',
                        help='Save the provided API key to ~/.tmdb_api_key')
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get('TMDB_API_KEY') or load_saved_api_key()
    if api_key:
        api_key = api_key.strip()
        if args.api_key and args.save_api_key:
            save_api_key(api_key)
        return api_key

    try:
        api_key = input('Enter TMDB API key: ').strip()
    except EOFError:
        api_key = ''

    if not api_key:
        print('Error: TMDB API key is required. Set TMDB_API_KEY, use --api-key, or save one using --save-api-key.')
        sys.exit(1)

    save_api_key(api_key)
    return api_key


if __name__ == "__main__":
    TMDB_API_KEY = get_tmdb_api_key()
    curses.wrapper(main)
