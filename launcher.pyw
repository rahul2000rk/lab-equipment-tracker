import os, sys, socket, time, threading, subprocess, webbrowser
D = os.path.dirname(os.path.abspath(__file__)); os.chdir(D); sys.path.insert(0, D)
if sys.stdout is None: sys.stdout = open(os.devnull, 'w')
if sys.stderr is None: sys.stderr = open(os.devnull, 'w')
import app
def up():
    s = socket.socket(); s.settimeout(.3)
    try: s.connect(('127.0.0.1', app.PORT)); return True
    except OSError: return False
    finally: s.close()
started = not up()
if started:
    app.init(); threading.Thread(target=lambda: app.app.run(host='127.0.0.1', port=app.PORT, threaded=True), daemon=True).start()
    for _ in range(40):
        if up(): break
        time.sleep(.2)
if '--server' not in sys.argv:
    url = f'http://127.0.0.1:{app.PORT}'
    for p in (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
              r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'):
        if os.path.exists(p): subprocess.Popen([p, '--app=' + url, '--window-size=1280,820']); break
    else: webbrowser.open(url)
if started: threading.Event().wait()   # keep serving (needed for Funnel / other users)
