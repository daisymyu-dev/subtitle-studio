"""Loopback entry point for source checkouts and the portable Windows build."""

import argparse
import logging
import os
import sys
import threading
import webbrowser

from studio.runtime import VERSION, asset_root, data_root, prepare_data


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # A frozen executable cannot invoke itself as `python -m yt_dlp`.
    # Dispatch before imports, CLI parsing, logging, or application state writes.
    if argv[:1] == ['--internal-ytdlp']:
        import yt_dlp
        return yt_dlp.main(argv[1:])
    parser = argparse.ArgumentParser(description='Subtitle Studio: local, loopback-only subtitle learning.')
    parser.add_argument('--version', action='version', version=f'Subtitle Studio {VERSION}')
    parser.add_argument('--check-runtime', action='store_true', help='Check bundled libraries offline, then exit')
    parser.add_argument('--open', action='store_true', help='Open the local page')
    parser.add_argument('--port', type=int, default=8765, help='First loopback port to try (default: 8765)')
    parser.add_argument('--data-dir', help='Local writable data folder (overrides SUBTITLE_STUDIO_DATA_DIR)')
    args = parser.parse_args(argv)
    if args.check_runtime:
        import json
        from studio.runtime import check_runtime
        print(json.dumps(check_runtime()), flush=True)
        return 0
    if not 1 <= args.port <= 65526:
        parser.error('--port must be between 1 and 65526')
    try:
        root = data_root(args.data_dir)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    prepare_data(root)
    logging.basicConfig(filename=root / 'studio.log', encoding='utf-8', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    from studio.server import make_server
    for port in range(args.port, args.port + 10):
        address = f'http://127.0.0.1:{port}'
        try:
            server = make_server(root, port, web_root=asset_root() / 'web')
            break
        except OSError:
            continue
    else:
        raise RuntimeError('No free local port found.')
    logging.info('Listening on loopback port %s', port)
    if args.open:
        threading.Timer(.4, lambda: webbrowser.open(address)).start()
    if sys.stdout:
        print(address, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        logging.exception('Startup failed')
        if os.name == 'nt' and '--open' in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, 'Subtitle Studio could not start. Check studio.log in the selected data folder.', 'Subtitle Studio', 16)
        raise
