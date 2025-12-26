from flask import Flask, request, jsonify, render_template_string
import os, zipfile, subprocess, shutil, json, uuid, threading, time, signal, psutil
import requests
from datetime import datetime

app = Flask(__name__)

# Папки
UPLOADS = 'uploads'
PROJECTS = 'projects'
DB_FILE = 'hosts.json'
PROCESSES_FILE = 'processes.json'

# Авто-пинг
PING_URL = "https://fffftfytyufj.onrender.com"
PING_INTERVAL = 240  # 4 минуты

# Создаем папки
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(PROJECTS, exist_ok=True)

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>/host</title>
    <meta charset="UTF-8">
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{background:#0a0a0a;color:#aaa;font-family:'Courier New',monospace;font-size:13px;padding:15px}
        .container{max-width:700px;margin:0 auto}
        h1{color:#666;font-size:16px;margin-bottom:15px;padding-bottom:5px;border-bottom:1px solid #222}
        .box{background:#111;border:1px solid #222;padding:15px;margin-bottom:15px}
        input,button{padding:6px;margin:4px 0;width:100%;background:#0a0a0a;border:1px solid #333;color:#aaa;font-family:'Courier New'}
        button{background:#222;cursor:pointer}
        button:hover{background:#2a2a2a}
        .btn-sm{padding:4px 8px;width:auto;margin-right:5px;font-size:12px}
        .btn-red{background:#1a0a0a;border-color:#522}
        .btn-green{background:#0a1a0a;border-color:#252}
        .host{border:1px solid #222;padding:12px;margin:8px 0;background:#111}
        .host-header{display:flex;justify-content:space-between;margin-bottom:8px}
        .host-name{color:#888;font-weight:bold}
        .status{padding:2px 6px;font-size:11px;border-radius:1px}
        .running{background:#0a2a0a;color:#5c5;border:1px solid #1a3a1a}
        .stopped{background:#2a0a0a;color:#c55;border:1px solid #3a1a1a}
        .command{background:#0a0a0a;border-left:2px solid #333;padding:4px 8px;margin:6px 0;color:#8af}
        .info{color:#555;font-size:11px;margin-top:5px}
        .no-projects{text-align:center;padding:30px;color:#444;border:1px dashed #222}
        .actions{margin-top:8px}
        .ping-status{position:fixed;top:10px;right:10px;color:#555;font-size:11px}
    </style>
</head>
<body>
    <div class="ping-status" id="pingStatus">ping: --</div>
    
    <div class="container">
        <h1>/host</h1>
        
        <div class="box">
            <input type="file" id="file" accept=".zip">
            <input type="text" id="command" placeholder="python bot.py" value="python main.py">
            <button onclick="upload()">upload & start</button>
        </div>
        
        <div id="hosts">
            <div class="no-projects">no active hosts</div>
        </div>
    </div>
    
    <script>
    async function upload() {
        const fileInput = document.getElementById('file');
        const cmdInput = document.getElementById('command');
        
        if(!fileInput.files[0]) return alert('select zip');
        if(!fileInput.files[0].name.endsWith('.zip')) return alert('only zip');
        if(!cmdInput.value.trim()) return alert('enter command');
        
        const form = new FormData();
        form.append('file', fileInput.files[0]);
        form.append('command', cmdInput.value);
        
        try {
            const res = await fetch('/upload', {method: 'POST', body: form});
            const data = await res.json();
            
            if(data.success) {
                fileInput.value = '';
                loadHosts();
            } else {
                alert('error: ' + data.error);
            }
        } catch(e) {
            alert('network error');
        }
    }
    
    async function loadHosts() {
        try {
            const res = await fetch('/hosts');
            const hosts = await res.json();
            
            const container = document.getElementById('hosts');
            
            if(hosts.length === 0) {
                container.innerHTML = '<div class="no-projects">no active hosts</div>';
                return;
            }
            
            let html = '';
            hosts.forEach(host => {
                html += `
                <div class="host">
                    <div class="host-header">
                        <div class="host-name">${host.name.replace('.zip', '')}</div>
                        <div class="status ${host.status}">${host.status}</div>
                    </div>
                    <div class="command">${host.command}</div>
                    <div class="info">id: ${host.id} | started: ${host.created}</div>
                    <div class="info">pid: ${host.pid || 'none'}</div>
                    <div class="actions">
                        <button class="btn-sm btn-red" onclick="control('${host.id}', 'stop')">stop</button>
                        <button class="btn-sm btn-green" onclick="control('${host.id}', 'start')">start</button>
                        <button class="btn-sm" onclick="del('${host.id}')">delete</button>
                    </div>
                </div>
                `;
            });
            
            container.innerHTML = html;
        } catch(e) {
            console.error(e);
        }
    }
    
    async function control(id, action) {
        await fetch(`/${id}/${action}`, {method: 'POST'});
        setTimeout(loadHosts, 1000);
    }
    
    async function del(id) {
        if(confirm('delete host?')) {
            await fetch(`/${id}/delete`, {method: 'POST'});
            setTimeout(loadHosts, 1000);
        }
    }
    
    // Функция пинга
    async function pingServer() {
        try {
            const start = Date.now();
            const res = await fetch('/ping');
            const data = await res.json();
            const latency = Date.now() - start;
            
            document.getElementById('pingStatus').innerHTML = 
                `ping: ${latency}ms | ${data.time}`;
            document.getElementById('pingStatus').style.color = '#5c5';
        } catch(e) {
            document.getElementById('pingStatus').innerHTML = 'ping: offline';
            document.getElementById('pingStatus').style.color = '#c55';
        }
    }
    
    // Запускаем
    setInterval(loadHosts, 3000);
    setInterval(pingServer, 10000); // Пинг каждые 10 сек
    loadHosts();
    pingServer();
    </script>
</body>
</html>
'''

def save_json(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_hosts(hosts):
    save_json(hosts, DB_FILE)

def load_hosts():
    return load_json(DB_FILE)

def save_processes(procs):
    save_json(procs, PROCESSES_FILE)

def load_processes():
    return load_json(PROCESSES_FILE)

def is_process_alive(pid):
    """Проверяет жив ли процесс"""
    try:
        if pid and psutil.pid_exists(pid):
            process = psutil.Process(pid)
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except:
        pass
    return False

def start_process(pid, command, project_dir):
    """Запускает процесс и возвращает его PID"""
    try:
        # Сохраняем stdout/stderr в файлы
        stdout_file = os.path.join(project_dir, 'stdout.log')
        stderr_file = os.path.join(project_dir, 'stderr.log')
        
        with open(stdout_file, 'w') as out, open(stderr_file, 'w') as err:
            process = subprocess.Popen(
                command.split(),
                cwd=project_dir,
                stdout=out,
                stderr=err,
                text=True,
                start_new_session=True
            )
        
        # Сохраняем PID
        processes = load_processes()
        processes.append({
            'project_id': pid,
            'pid': process.pid,
            'command': command,
            'started': time.time()
        })
        save_processes(processes)
        
        return process.pid
    except Exception as e:
        print(f"Start process error: {e}")
        return None

def stop_process(project_id):
    """Останавливает процесс по project_id"""
    processes = load_processes()
    for proc in processes[:]:
        if proc['project_id'] == project_id:
            try:
                if is_process_alive(proc['pid']):
                    os.kill(proc['pid'], signal.SIGTERM)
                    time.sleep(0.5)
                    if is_process_alive(proc['pid']):
                        os.kill(proc['pid'], signal.SIGKILL)
            except:
                pass
            processes.remove(proc)
    save_processes(processes)
    return True

def restore_processes():
    """Восстанавливаем процессы при старте сервера"""
    hosts = load_hosts()
    processes = load_processes()
    
    # Удаляем мертвые процессы
    alive_processes = []
    for proc in processes:
        if is_process_alive(proc['pid']):
            alive_processes.append(proc)
        else:
            # Обновляем статус хоста
            for host in hosts:
                if host['id'] == proc['project_id']:
                    host['status'] = 'stopped'
    
    save_processes(alive_processes)
    save_hosts(hosts)
    
    # Запускаем stopped хосты
    for host in hosts:
        if host.get('status') == 'running':
            project_dir = os.path.join(PROJECTS, host['id'])
            if os.path.exists(project_dir):
                # Проверяем нет ли уже живого процесса
                has_alive = False
                for proc in alive_processes:
                    if proc['project_id'] == host['id'] and is_process_alive(proc['pid']):
                        has_alive = True
                        break
                
                if not has_alive:
                    print(f"Restarting: {host['name']}")
                    new_pid = start_process(host['id'], host['command'], project_dir)
                    if new_pid:
                        host['pid'] = new_pid
                        host['status'] = 'running'
    
    save_hosts(hosts)

# Функция авто-пинга
def auto_ping():
    """Автоматический пинг сервера каждые 4 минуты"""
    print(f"🚀 Авто-пинг запущен для {PING_URL}")
    while True:
        try:
            response = requests.get(PING_URL, timeout=10)
            print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] Пинг. Статус: {response.status_code}")
        except Exception as e:
            print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] Ошибка: {e}")
        time.sleep(PING_INTERVAL)

# Запускаем авто-пинг в отдельном потоке
ping_thread = threading.Thread(target=auto_ping, daemon=True)
ping_thread.start()

@app.route('/')
def home():
    return render_template_string(HTML)

@app.route('/ping')
def ping():
    """Эндпоинт для пинга"""
    return jsonify({
        'status': 'ok',
        'time': datetime.now().strftime('%H:%M:%S'),
        'server': 'Python Host',
        'url': PING_URL
    })

@app.route('/upload', methods=['POST'])
def upload():
    try:
        file = request.files['file']
        command = request.form['command'].strip()
        
        if not file.filename.endswith('.zip'):
            return jsonify({'success': False, 'error': 'only zip files'})
        
        # Создаем проект
        project_id = str(uuid.uuid4())[:8]
        
        # Сохраняем ZIP
        zip_path = os.path.join(UPLOADS, f'{project_id}_{file.filename}')
        file.save(zip_path)
        
        # Распаковываем
        project_dir = os.path.join(PROJECTS, project_id)
        os.makedirs(project_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(project_dir)
        
        # Запускаем процесс
        pid = start_process(project_id, command, project_dir)
        
        if not pid:
            return jsonify({'success': False, 'error': 'failed to start process'})
        
        # Сохраняем хост
        host = {
            'id': project_id,
            'name': file.filename,
            'command': command,
            'status': 'running',
            'pid': pid,
            'created': time.strftime('%H:%M:%S')
        }
        
        hosts = load_hosts()
        hosts.append(host)
        save_hosts(hosts)
        
        return jsonify({'success': True, 'id': project_id})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/hosts')
def get_hosts():
    hosts = load_hosts()
    
    # Обновляем статусы
    for host in hosts:
        if host.get('pid') and is_process_alive(host['pid']):
            host['status'] = 'running'
        else:
            host['status'] = 'stopped'
            host['pid'] = None
    
    save_hosts(hosts)
    return jsonify(hosts)

@app.route('/<project_id>/<action>', methods=['POST'])
def control_host(project_id, action):
    try:
        hosts = load_hosts()
        host = next((h for h in hosts if h['id'] == project_id), None)
        
        if not host:
            return jsonify({'success': False, 'error': 'host not found'})
        
        project_dir = os.path.join(PROJECTS, project_id)
        
        if action == 'stop':
            stop_process(project_id)
            host['status'] = 'stopped'
            host['pid'] = None
            
        elif action == 'start':
            # Останавливаем если уже запущен
            stop_process(project_id)
            
            # Запускаем заново
            if os.path.exists(project_dir):
                pid = start_process(project_id, host['command'], project_dir)
                if pid:
                    host['pid'] = pid
                    host['status'] = 'running'
                else:
                    return jsonify({'success': False, 'error': 'failed to start'})
            else:
                return jsonify({'success': False, 'error': 'project files missing'})
        
        save_hosts(hosts)
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/<project_id>/delete', methods=['POST'])
def delete_host(project_id):
    try:
        # Останавливаем
        stop_process(project_id)
        
        # Удаляем из БД
        hosts = [h for h in load_hosts() if h['id'] != project_id]
        save_hosts(hosts)
        
        # Удаляем процессы
        processes = [p for p in load_processes() if p['project_id'] != project_id]
        save_processes(processes)
        
        # Удаляем файлы
        project_dir = os.path.join(PROJECTS, project_id)
        if os.path.exists(project_dir):
            shutil.rmtree(project_dir)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Инициализация при старте
if __name__ == '__main__':
    restore_processes()
    app.run(host='0.0.0.0', port=5000)
else:
    # Для gunicorn
    restore_processes()
