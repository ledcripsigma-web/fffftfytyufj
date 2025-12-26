from flask import Flask, request, jsonify, render_template_string
import os, zipfile, subprocess, shutil, json, uuid, threading, time

app = Flask(__name__)

UPLOADS = 'uploads'
PROJECTS = 'projects'
DB_FILE = 'hosts.json'

os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(PROJECTS, exist_ok=True)

processes = {}

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>/host</title>
    <meta charset="UTF-8">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            background: #1a1a1a;
            color: #ccc;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.4;
            padding: 20px;
        }
        
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        
        h1 {
            color: #888;
            font-size: 18px;
            font-weight: normal;
            margin-bottom: 20px;
            border-bottom: 1px solid #333;
            padding-bottom: 5px;
        }
        
        .upload-box {
            background: #222;
            border: 1px solid #333;
            padding: 20px;
            margin-bottom: 20px;
        }
        
        input[type="file"] {
            background: #1a1a1a;
            border: 1px solid #333;
            color: #ccc;
            padding: 8px;
            width: 100%;
            margin-bottom: 10px;
            font-family: 'Courier New', monospace;
        }
        
        input[type="text"] {
            background: #1a1a1a;
            border: 1px solid #333;
            color: #ccc;
            padding: 8px;
            width: 100%;
            margin-bottom: 10px;
            font-family: 'Courier New', monospace;
        }
        
        .btn {
            background: #333;
            color: #ccc;
            border: 1px solid #444;
            padding: 8px 16px;
            cursor: pointer;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            display: inline-block;
            margin-right: 5px;
            margin-bottom: 5px;
        }
        
        .btn:hover {
            background: #3a3a3a;
            border-color: #555;
        }
        
        .btn-red {
            background: #2a1a1a;
            border-color: #522;
        }
        
        .btn-red:hover {
            background: #3a2a2a;
        }
        
        .host-list {
            margin-top: 20px;
        }
        
        .host-item {
            background: #222;
            border: 1px solid #333;
            padding: 15px;
            margin-bottom: 10px;
        }
        
        .host-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .host-name {
            color: #aaa;
            font-weight: bold;
        }
        
        .host-status {
            padding: 2px 8px;
            font-size: 11px;
            border-radius: 2px;
        }
        
        .status-running {
            background: #1a2a1a;
            color: #5c5;
            border: 1px solid #2a3a2a;
        }
        
        .status-stopped {
            background: #2a1a1a;
            color: #c55;
            border: 1px solid #3a2a2a;
        }
        
        .host-command {
            background: #1a1a1a;
            border: 1px solid #333;
            padding: 6px 10px;
            margin: 8px 0;
            font-family: 'Courier New', monospace;
            color: #8af;
        }
        
        .host-info {
            color: #666;
            font-size: 12px;
            margin-top: 8px;
        }
        
        .no-projects {
            color: #666;
            text-align: center;
            padding: 40px 20px;
            border: 1px dashed #333;
        }
        
        .actions {
            margin-top: 10px;
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>/host</h1>
        
        <div class="upload-box">
            <input type="file" id="file" accept=".zip">
            <input type="text" id="command" placeholder="python bot.py" value="python main.py">
            <button class="btn" onclick="upload()">upload</button>
        </div>
        
        <div id="hosts">
            <div class="no-projects">no projects</div>
        </div>
    </div>
    
    <script>
    async function upload() {
        const file = document.getElementById('file').files[0];
        const cmd = document.getElementById('command').value.trim();
        
        if (!file) {
            alert('select zip');
            return;
        }
        if (!file.name.endsWith('.zip')) {
            alert('only zip');
            return;
        }
        if (!cmd) {
            alert('enter command');
            return;
        }
        
        const form = new FormData();
        form.append('file', file);
        form.append('command', cmd);
        
        try {
            const res = await fetch('/upload', {method: 'POST', body: form});
            const data = await res.json();
            
            if (data.success) {
                document.getElementById('file').value = '';
                load();
            } else {
                alert('error: ' + data.error);
            }
        } catch (e) {
            alert('network error');
        }
    }
    
    async function load() {
        try {
            const res = await fetch('/hosts');
            const hosts = await res.json();
            
            const container = document.getElementById('hosts');
            
            if (hosts.length === 0) {
                container.innerHTML = '<div class="no-projects">no projects</div>';
                return;
            }
            
            let html = '<div class="host-list">';
            
            hosts.forEach(host => {
                html += `
                <div class="host-item">
                    <div class="host-header">
                        <div class="host-name">${host.name.replace('.zip', '')}</div>
                        <div class="host-status ${host.status}">${host.status}</div>
                    </div>
                    <div class="host-command">${host.command}</div>
                    <div class="host-info">id: ${host.id} | created: ${host.created}</div>
                    <div class="actions">
                        <button class="btn" onclick="control('${host.id}', 'stop')">stop</button>
                        <button class="btn" onclick="restart('${host.id}')">restart</button>
                        <button class="btn btn-red" onclick="del('${host.id}')">delete</button>
                    </div>
                </div>
                `;
            });
            
            html += '</div>';
            container.innerHTML = html;
        } catch (e) {
            console.error(e);
        }
    }
    
    async function control(id, action) {
        await fetch(`/${id}/${action}`, {method: 'POST'});
        load();
    }
    
    async function restart(id) {
        await fetch(`/${id}/restart`, {method: 'POST'});
        load();
    }
    
    async function del(id) {
        if (confirm('delete?')) {
            await fetch(`/${id}/delete`, {method: 'POST'});
            load();
        }
    }
    
    // Автообновление каждые 5 секунд
    setInterval(load, 5000);
    load();
    </script>
</body>
</html>
'''

def load_hosts():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_hosts(hosts):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(hosts, f, indent=2, ensure_ascii=False)

def auto_start_all():
    """Автостарт всех проектов при запуске сервера"""
    hosts = load_hosts()
    for host in hosts:
        try:
            pid = host['id']
            project_dir = os.path.join(PROJECTS, pid)
            
            if os.path.exists(project_dir):
                proc = subprocess.Popen(
                    host['command'].split(),
                    cwd=project_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                processes[pid] = proc
                host['status'] = 'running'
                
                def monitor(p=proc, h_id=pid):
                    p.wait()
                    if h_id in processes:
                        del processes[h_id]
                    hosts = load_hosts()
                    for h in hosts:
                        if h['id'] == h_id:
                            h['status'] = 'stopped'
                            break
                    save_hosts(hosts)
                
                threading.Thread(target=monitor, daemon=True).start()
        except:
            host['status'] = 'stopped'
    
    save_hosts(hosts)

@app.route('/')
def home():
    return render_template_string(HTML)

@app.route('/upload', methods=['POST'])
def upload():
    try:
        file = request.files['file']
        cmd = request.form['command'].strip()
        pid = str(uuid.uuid4())[:8]
        
        # Сохраняем ZIP
        zip_path = os.path.join(UPLOADS, f'{pid}_{file.filename}')
        file.save(zip_path)
        
        # Распаковываем
        project_dir = os.path.join(PROJECTS, pid)
        os.makedirs(project_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(project_dir)
        
        # Запускаем
        proc = subprocess.Popen(
            cmd.split(),
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        processes[pid] = proc
        
        # Сохраняем в БД
        host = {
            'id': pid,
            'name': file.filename,
            'command': cmd,
            'status': 'running',
            'created': time.strftime('%H:%M:%S'),
            'pid': proc.pid
        }
        
        hosts = load_hosts()
        hosts.append(host)
        save_hosts(hosts)
        
        # Мониторинг в фоне
        def monitor():
            proc.wait()
            if pid in processes:
                del processes[pid]
            hosts = load_hosts()
            for h in hosts:
                if h['id'] == pid:
                    h['status'] = 'stopped'
                    break
            save_hosts(hosts)
        
        threading.Thread(target=monitor, daemon=True).start()
        return jsonify({'success': True, 'id': pid})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/hosts')
def get_hosts():
    hosts = load_hosts()
    
    for host in hosts:
        pid = host['id']
        if pid in processes:
            proc = processes[pid]
            host['status'] = 'running' if proc.poll() is None else 'stopped'
        else:
            host['status'] = 'stopped'
    
    save_hosts(hosts)
    return jsonify(hosts)

@app.route('/<pid>/stop', methods=['POST'])
def stop(pid):
    try:
        if pid in processes:
            proc = processes[pid]
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except:
                proc.kill()
            del processes[pid]
        
        hosts = load_hosts()
        for host in hosts:
            if host['id'] == pid:
                host['status'] = 'stopped'
                break
        
        save_hosts(hosts)
        return jsonify({'success': True})
    except:
        return jsonify({'success': False})

@app.route('/<pid>/restart', methods=['POST'])
def restart(pid):
    try:
        # Останавливаем если запущен
        if pid in processes:
            proc = processes[pid]
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except:
                proc.kill()
            del processes[pid]
        
        hosts = load_hosts()
        host = next((h for h in hosts if h['id'] == pid), None)
        
        if not host:
            return jsonify({'success': False, 'error': 'not found'})
        
        project_dir = os.path.join(PROJECTS, pid)
        if not os.path.exists(project_dir):
            return jsonify({'success': False, 'error': 'files missing'})
        
        # Перезапускаем
        proc = subprocess.Popen(
            host['command'].split(),
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        processes[pid] = proc
        host['status'] = 'running'
        save_hosts(hosts)
        
        def monitor():
            proc.wait()
            if pid in processes:
                del processes[pid]
            hosts = load_hosts()
            for h in hosts:
                if h['id'] == pid:
                    h['status'] = 'stopped'
                    break
            save_hosts(hosts)
        
        threading.Thread(target=monitor, daemon=True).start()
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/<pid>/delete', methods=['POST'])
def delete(pid):
    try:
        # Останавливаем
        if pid in processes:
            proc = processes[pid]
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except:
                proc.kill()
            del processes[pid]
        
        # Удаляем из БД
        hosts = [h for h in load_hosts() if h['id'] != pid]
        save_hosts(hosts)
        
        # Удаляем файлы
        project_dir = os.path.join(PROJECTS, pid)
        if os.path.exists(project_dir):
            shutil.rmtree(project_dir)
        
        return jsonify({'success': True})
    except:
        return jsonify({'success': False})

# Запускаем все проекты при старте
auto_start_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
